"""Lossless Hybrid Latent Stitching Engine for MiniMax H3 Eternity Edition.

This module implements the dual-path continuity engine:
- Path B: Slices uncompressed PyTorch Safetensors .latent tensors from the previous iteration
  and injects them as un-denoised keyframes onto the target timeline RoPE coordinates via patch_layout.py.
- Path A: Subsamples previous lossless FFV1/BGRA media at 2 FPS into semantic visual reference frames
  for Qwen3-VL-32B text encoder alignment.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional, Tuple, List
import torch

try:
    import safetensors.torch
    _HAVE_SAFETENSORS = True
except ImportError:
    _HAVE_SAFETENSORS = False

from .render_plan import VALID_OVERLAPS, DEFAULT_OVERLAP
from .patch_layout import MC_KEY, MC_AUDIO_KEY, native_guides_active

_LOG = logging.getLogger("minimax_h3_eternity.hybrid_stitch")

# MiniMax H3 physical clock ratio: 40 Hz audio latent clock / 24 FPS video = 5/3
FRAME_RESCALE = 5.0 / 3.0
AUDIO_HZ = 40.0
VIDEO_FPS = 24.0


def get_latent_steps_for_overlap(overlap_frames: int) -> int:
    """Return the number of latent video tokens corresponding to an overlap span.
    
    Lattice rule: FRAME_PER_TOKEN = (1, 4, 4, 4, 4).
    1 frame  -> 1 step
    5 frames -> 2 steps
    22 frames -> 7 steps
    39 frames -> 12 steps
    """
    n = max(1, int(overlap_frames))
    if n <= 1:
        return 1
    if n <= 5:
        return 2
    return ((n - 5) // 17) * 5 + 2


def get_pixel_offsets_for_overlap(overlap_frames: int) -> List[int]:
    """Return the temporal pixel frame offsets for each latent step in an overlap window.
    
    Offsets correspond to the physical frame indices where un-denoised tokens are injected:
    1 frame  -> [0]
    5 frames -> [0, 1]
    22 frames -> [0, 1, 5, 9, 13, 17, 21]
    39 frames -> [0, 1, 5, 9, 13, 17, 21, 22, 26, 30, 34, 38]
    """
    steps = get_latent_steps_for_overlap(overlap_frames)
    if steps <= 0:
        return []
    offsets = []
    cursor = 0
    for k in range(steps):
        offsets.append(cursor)
        step_len = 1 if (k == 0 or (k >= 6 and (k - 1) % 5 == 0)) else 4
        cursor += step_len
    return offsets


def get_audio_steps_and_overhang(overlap_frames: int) -> Tuple[int, float]:
    """Compute discrete audio latent steps and fractional step overhang for an overlap span.
    
    Ideal audio steps = (5/3) * overlap_frames
    Quantized audio steps Ta = round(Ideal)
    Fractional Overhang delta = Ta - Ideal
    
    For 22 frames: Ideal = 36.6667, Ta = 37, Overhang = +0.333333
    For 5 frames:  Ideal = 8.3333,  Ta = 8,  Overhang = -0.333333
    For 39 frames: Ideal = 65.0000, Ta = 65, Overhang = 0.000000
    """
    n = max(1, int(overlap_frames))
    ideal = float(FRAME_RESCALE * n)
    ta = max(1, int(round(ideal)))
    overhang = float(ta - ideal)
    return ta, overhang


def get_audio_timeline_end_coord(overlap_frames: int) -> float:
    """Compute the RoPE timeline end frame coordinate for pinned audio continuation."""
    n = max(1, int(overlap_frames))
    _, overhang = get_audio_steps_and_overhang(n)
    return float(n + (overhang / FRAME_RESCALE))


try:
    import comfy.nested_tensor

    class EternityNestedTensor(comfy.nested_tensor.NestedTensor):
        """Extended NestedTensor that supports tuple unpacking and iteration."""
        def __iter__(self):
            return iter(self.tensors)

        def __len__(self):
            return len(self.tensors)
except Exception:
    class EternityNestedTensor:
        """Offline fallback stub for ComfyUI NestedTensor."""
        def __init__(self, tensors):
            self.tensors = list(tensors)
            self.is_nested = True

        def unbind(self):
            return self.tensors

        def __iter__(self):
            return iter(self.tensors)

        def __len__(self):
            return len(self.tensors)

        def __getitem__(self, idx):
            return self.tensors[idx]


def build_empty_av_latent(
    duration_frames: int,
    width: int,
    height: int,
    dtype: torch.dtype = torch.bfloat16,
    device: str = "cpu",
) -> dict[str, Any]:
    """Initialize an empty joint AV latent dictionary for the active iteration window.
    
    Args:
        duration_frames: Active iteration frame count (snapped to 17k+5).
        width: Canvas width in pixels (divisible by 32).
        height: Canvas height in pixels (divisible by 32).
        dtype: Tensor data type (default torch.bfloat16).
        device: Allocation device (default cpu).
        
    Returns:
        Latent dict conforming to ComfyUI H3 NestedTensor schema {"samples": EternityNestedTensor([zv, za])}.
    """
    n = max(5, int(duration_frames))
    tv = 2 if n <= 5 else ((n - 5) // 17) * 5 + 2
    ta = max(1, int(round(FRAME_RESCALE * n)))
    
    latent_h = max(1, height // 16)
    latent_w = max(1, width // 16)
    
    zv = torch.zeros((1, 24, tv, latent_h, latent_w), dtype=dtype, device=device)
    za = torch.zeros((1, 32, 2, ta), dtype=dtype, device=device)
    
    return {"samples": EternityNestedTensor([zv, za])}


def build_frozen_continuation_latent(
    previous_artifact: dict[str, Any] | list[dict[str, Any]],
    duration_frames: int,
    overlap_frames: int = DEFAULT_OVERLAP,
    audio_overlap_frames: Optional[int] = None,
    width: int = 1344,
    height: int = 768,
    fps: float = 24.0,
    dtype: torch.dtype = torch.bfloat16,
    device: str = "cpu",
    audio_anchor_mode: str = "in_latent_freeze + ref",
) -> dict[str, Any]:
    """Build a joint AV latent dictionary where preceding video & audio overlaps are physically frozen with noise_mask=0.
    
    Args:
        previous_artifact: SavedArtifact dictionary or list from preceding iteration.
        duration_frames: Total duration in timeline frames for this iteration.
        overlap_frames: Video overlap span in timeline frames (1, 5, 22, or 39).
        audio_overlap_frames: Audio overlap span in timeline frames.
        width: Canvas width in pixels.
        height: Canvas height in pixels.
        fps: Timeline frame rate.
        dtype: Tensor data type.
        device: Device to place latents on.
        audio_anchor_mode: Audio continuation mode ('in_latent_freeze + ref', 'in_latent_freeze', 'ref', 'overlap', 'off').
        
    Returns:
        Dict conforming to {"samples": EternityNestedTensor([zv, za]), "noise_mask": EternityNestedTensor([video_mask, audio_mask])}.
    """
    n = max(5, int(duration_frames))
    tv = 2 if n <= 5 else ((n - 5) // 17) * 5 + 2
    ta = max(1, int(round(FRAME_RESCALE * n)))
    
    latent_h = max(1, height // 16)
    latent_w = max(1, width // 16)
    
    zv = torch.zeros((1, 24, tv, latent_h, latent_w), dtype=dtype, device=device)
    za = torch.zeros((1, 32, 2, ta), dtype=dtype, device=device)
    
    video_mask = torch.ones_like(zv)
    audio_mask = torch.ones_like(za)
    
    # Resolve artifacts list and load previous latent tensors
    if isinstance(previous_artifact, list):
        last_artifact = previous_artifact[-1] if previous_artifact else {}
    elif isinstance(previous_artifact, dict):
        last_artifact = previous_artifact
    else:
        last_artifact = {}
        
    latent_path = last_artifact.get("latent_path", "")
    tensors = _load_latent_tensors(latent_path) if latent_path else None
    
    overlap_tv = get_latent_steps_for_overlap(overlap_frames) if overlap_frames else 0
    raw_audio_ov = audio_overlap_frames if audio_overlap_frames is not None else overlap_frames
    if audio_anchor_mode != "off" and raw_audio_ov:
        overlap_ta, _ = get_audio_steps_and_overhang(raw_audio_ov)
    else:
        overlap_ta = 0
    
    if tensors is not None:
        source_zv = tensors.get("samples_video")
        if source_zv is not None and source_zv.ndim == 5 and overlap_tv > 0:
            actual_tv = source_zv.shape[2]
            slice_tv = min(overlap_tv, actual_tv, tv)
            zv[:, :, :slice_tv] = source_zv[:, :, -slice_tv:].to(dtype=dtype, device=device)
            video_mask[:, :, :slice_tv] = 0.0
            _LOG.info("[H3.E - Director] In-Latent Video Freeze: pinned %d latent steps (%d frames) at mask=0.0",
                      slice_tv, overlap_frames)
                      
        source_za = tensors.get("samples_audio")
        if source_za is not None and source_za.ndim == 4 and overlap_ta > 0:
            actual_ta = source_za.shape[-1]
            slice_ta = min(overlap_ta, actual_ta, ta)
            za[:, :, :, :slice_ta] = source_za[:, :, :, -slice_ta:].to(dtype=dtype, device=device)
            audio_mask[:, :, :, :slice_ta] = 0.0
            _LOG.info("[H3.E - Director] In-Latent Audio Freeze: pinned %d audio steps at mask=0.0", slice_ta)
    else:
        _LOG.warning("[H3.E - Director] No previous latent found for In-Latent Freeze at '%s'. Using unmasked generation.", latent_path)
        
    return {
        "samples": EternityNestedTensor([zv, za]),
        "noise_mask": EternityNestedTensor([video_mask, audio_mask]),
    }


def _load_latent_tensors(latent_path: str) -> Optional[dict[str, torch.Tensor]]:
    """Helper to safely load Safetensors or PyTorch tensors dict from disk."""
    if not latent_path or not os.path.exists(latent_path):
        return None
    try:
        tensors = None
        if _HAVE_SAFETENSORS:
            try:
                tensors = safetensors.torch.load_file(latent_path)
            except Exception:
                tensors = None
        if tensors is None:
            try:
                tensors = torch.load(latent_path, map_location="cpu", weights_only=True)
            except Exception:
                tensors = torch.load(latent_path, map_location="cpu")
        return tensors if isinstance(tensors, dict) else None
    except Exception as e:
        _LOG.error("[H3.E - Director] Failed to load latent file '%s': %s", latent_path, e)
        return None


def extract_continuation_payload(
    previous_artifact: dict[str, Any] | list[dict[str, Any]],
    overlap_frames: int = DEFAULT_OVERLAP,
    audio_overlap_frames: Optional[int] = None,
    canvas_w: int = 1344,
    canvas_h: int = 768,
    fps: float = 24.0,
    audio_anchor_mode: str = "overlap",
    continuation_ref_mode: str = "latent_only",
    seed: int = 0,
    continuation_mode: str = "hybrid_keyframes",
    audio_ref_duration: int = 22,
) -> Tuple[List[dict[str, Any]], Optional[dict[str, Any]], List[torch.Tensor]]:
    """Extract Path B raw latent slices and Path A semantic reference frames from previous iteration.
    
    Args:
        previous_artifact: Single SavedArtifact dictionary or list of all historical SavedArtifacts.
        overlap_frames: Overlap span in timeline frames (1, 5, 22, or 39).
        audio_overlap_frames: Audio overlap span in timeline frames (defaults to overlap_frames).
        canvas_w: Current iteration target width.
        canvas_h: Current iteration target height.
        fps: Playback frame rate (default 24.0).
        audio_anchor_mode: Audio continuation placement mode ('in_latent_freeze + ref', 'in_latent_freeze', 'overlap', 'before', 'ref', 'off').
        continuation_ref_mode: Video continuation mode ('latent_only' or 'raw').
        seed: Random seed for deterministic continuation processing.
        continuation_mode: Continuation engine ('in_latent_freeze' or 'hybrid_keyframes').
        audio_ref_duration: Audio length in frames to extract for acoustic style reference (default 22).
        
    Returns:
        minimax_keyframes: List of keyframe dicts for patch_layout.py (Path B - Video).
        minimax_audio_ref: Audio reference dict for patch_layout.py (Path B - Audio).
        semantic_ref_frames: List of subsampled 2 FPS [1, H, W, 3] tensors for Qwen3-VL (Path A).
    """
    if isinstance(previous_artifact, list):
        artifacts_list = [a for a in previous_artifact if isinstance(a, dict)]
        last_artifact = artifacts_list[-1] if artifacts_list else {}
    elif isinstance(previous_artifact, dict):
        artifacts_list = [previous_artifact]
        last_artifact = previous_artifact
    else:
        artifacts_list = []
        last_artifact = {}

    latent_path = last_artifact.get("latent_path", "")
    media_path = last_artifact.get("media_path", "")
    
    tv_steps = get_latent_steps_for_overlap(overlap_frames)
    offsets = get_pixel_offsets_for_overlap(overlap_frames)
    
    # Resolve effective audio overlap (defaults to overlap_frames, max 120 frames / 5.0s)
    raw_audio_overlap = audio_overlap_frames if audio_overlap_frames is not None else overlap_frames
    effective_audio_overlap = max(1, min(int(raw_audio_overlap), 120))
    ta_steps, overhang = get_audio_steps_and_overhang(effective_audio_overlap)

    # In 'overlap' mode, continuation audio ends at timeline target overlap frame
    if audio_anchor_mode == "overlap":
        audio_end_coord = get_audio_timeline_end_coord(effective_audio_overlap)
    elif audio_anchor_mode == "before":
        audio_end_coord = 0.0
    else:
        audio_end_coord = 0.0
    
    minimax_keyframes: List[dict[str, Any]] = []
    minimax_audio_ref: Optional[dict[str, Any]] = None
    semantic_ref_frames: List[torch.Tensor] = []
    
    # -------------------------------------------------------------
    # PATH B: Exact Latent Physical Injection (Never Denoised)
    # -------------------------------------------------------------
    if continuation_mode == "in_latent_freeze":
        _LOG.info("[H3.E - Director] continuation_mode='in_latent_freeze': suppressing DiT keyframe tokens to avoid token duplication")
        minimax_keyframes = []

        # If audio_anchor_mode has '+ ref' or is 'ref' or 'golden_experience', extract unanchored acoustic style reference
        if audio_anchor_mode in ("in_latent_freeze + ref", "ref", "golden_experience"):
            eff_ref_dur = max(1, int(audio_ref_duration))
            ta_ref_steps, _ = get_audio_steps_and_overhang(eff_ref_dur)
            tensors = _load_latent_tensors(latent_path) if latent_path else None
            if tensors is not None:
                try:
                    audio_slices: List[torch.Tensor] = []
                    steps_needed = ta_ref_steps
                    for art in reversed(artifacts_list):
                        lpath = art.get("latent_path", "")
                        art_tensors = _load_latent_tensors(lpath) if lpath else None
                        if art_tensors is None:
                            continue
                        za = art_tensors.get("samples_audio")
                        if za is not None and za.ndim == 4:
                            avail_t = za.shape[3]
                            take_t = min(steps_needed, avail_t)
                            slice_za = za[:, :, :, -take_t:].clone()
                            audio_slices.insert(0, slice_za)
                            steps_needed -= take_t
                            if steps_needed <= 0:
                                break

                    za_tail = torch.cat(audio_slices, dim=-1) if audio_slices else None
                    if za_tail is not None and za_tail.shape[-1] > 0:
                        slice_len_a = za_tail.shape[-1]
                        minimax_audio_ref = {
                            "kind": "audio",
                            "ref_audio_t": slice_len_a,
                            "audio_latent": za_tail,
                            MC_AUDIO_KEY: 0.0,
                            "motion_context_audio_pixel_span": 0.0,
                            "anchor_mode": "ref",
                        }
                        _LOG.info(
                            "[H3.E - Director] In-Latent Freeze + Ref: Sliced %d audio latent steps across %d artifact(s) "
                            "(audio_ref_duration=%d frames, mode=ref)",
                            slice_len_a, len(audio_slices), eff_ref_dur
                        )
                except Exception as e:
                    _LOG.error("[H3.E - Director] Failed to slice audio reference in in_latent_freeze mode: %s", e)
            else:
                # Synthetic fallback for mock tests / offline harnesses
                dummy_a = torch.zeros((1, 32, 2, ta_ref_steps), dtype=torch.float32)
                minimax_audio_ref = {
                    "kind": "audio",
                    "ref_audio_t": ta_ref_steps,
                    "audio_latent": dummy_a,
                    MC_AUDIO_KEY: 0.0,
                    "motion_context_audio_pixel_span": 0.0,
                    "anchor_mode": "ref",
                }
    else:
        # continuation_mode == "hybrid_keyframes" (Legacy keyframe conditioning)
        tensors = _load_latent_tensors(latent_path) if latent_path else None
        if tensors is not None:
            try:
                z_video = tensors.get("samples_video")
                if z_video is not None and z_video.ndim == 5:
                    actual_tv = z_video.shape[2]
                    slice_len = min(tv_steps, actual_tv)
                    zv_tail = z_video[:, :, -slice_len:, :, :].clone()
                    for k in range(slice_len):
                        p_offset = offsets[k] if k < len(offsets) else k
                        minimax_keyframes.append({
                            "resolved_frame_index": p_offset,
                            MC_KEY: p_offset,
                            "motion_context_pixel_index": p_offset,
                            "latent": zv_tail[:, :, k:k+1, :, :],
                        })
                    _LOG.info("[H3.E - Director] Sliced %d video latent steps from previous artifact", slice_len)

                if audio_anchor_mode != "off":
                    eff_audio_mode = "ref" if audio_anchor_mode in ("in_latent_freeze + ref", "in_latent_freeze", "ref", "golden_experience") else audio_anchor_mode
                    if eff_audio_mode == "ref":
                        eff_ref_dur = max(1, int(audio_ref_duration))
                        steps_needed = get_audio_steps_and_overhang(eff_ref_dur)[0]
                        audio_end_coord = 0.0
                    else:
                        steps_needed = ta_steps

                    audio_slices: List[torch.Tensor] = []
                    for art in reversed(artifacts_list):
                        lpath = art.get("latent_path", "")
                        art_tensors = _load_latent_tensors(lpath) if lpath else None
                        if art_tensors is None:
                            continue
                        za = art_tensors.get("samples_audio")
                        if za is not None and za.ndim == 4:
                            avail_t = za.shape[3]
                            take_t = min(steps_needed, avail_t)
                            slice_za = za[:, :, :, -take_t:].clone()
                            audio_slices.insert(0, slice_za)
                            steps_needed -= take_t
                            if steps_needed <= 0:
                                break

                    za_tail = torch.cat(audio_slices, dim=-1) if audio_slices else None
                    if za_tail is not None and za_tail.shape[-1] > 0:
                        slice_len_a = za_tail.shape[-1]
                        minimax_audio_ref = {
                            "kind": "audio",
                            "ref_audio_t": slice_len_a,
                            "audio_latent": za_tail,
                            MC_AUDIO_KEY: float(audio_end_coord),
                            "motion_context_audio_pixel_span": float(audio_end_coord),
                            "anchor_mode": eff_audio_mode,
                        }
                        _LOG.info(
                            "[H3.E - Director] Sliced %d audio latent steps across %d artifact(s) "
                            "(mode=%s, end_coord=%.3f)",
                            slice_len_a, len(audio_slices), eff_audio_mode, audio_end_coord
                        )
            except Exception as e:
                _LOG.error("[H3.E - Director] Failed to process latent tensors: %s", e)
        else:
            _LOG.warning("[H3.E - Director] Latent file '%s' not found or Safetensors missing. Generating fallback synthetic tokens.", latent_path)
            latent_h = max(1, canvas_h // 16)
            latent_w = max(1, canvas_w // 16)
            dummy_v = torch.zeros((1, 24, tv_steps, latent_h, latent_w), dtype=torch.float32)
            dummy_a = torch.zeros((1, 32, 2, ta_steps), dtype=torch.float32)
            for k, p in enumerate(offsets):
                minimax_keyframes.append({
                    "resolved_frame_index": p,
                    MC_KEY: p,
                    "motion_context_pixel_index": p,
                    "latent": dummy_v[:, :, k:k+1, :, :],
                })
            if audio_anchor_mode != "off":
                eff_audio_mode = "ref" if audio_anchor_mode in ("in_latent_freeze + ref", "in_latent_freeze", "ref", "golden_experience") else audio_anchor_mode
                minimax_audio_ref = {
                    "kind": "audio",
                    "ref_audio_t": ta_steps,
                    "audio_latent": dummy_a,
                    MC_AUDIO_KEY: float(audio_end_coord),
                    "motion_context_audio_pixel_span": float(audio_end_coord),
                    "anchor_mode": eff_audio_mode,
                }
    
    # -------------------------------------------------------------
    # PATH A: Semantic Conditioning (Qwen3-VL-32B at 2 FPS)
    # -------------------------------------------------------------
    if continuation_ref_mode == "latent_only":
        _LOG.info("[H3.E - Director] continuation_ref_mode='latent_only': skipping Path A semantic video subsampling")
        semantic_ref_frames = []
    elif media_path and os.path.exists(media_path):
        try:
            from . import minimax_media as media
            delivered = int(last_artifact.get("delivered_frames", overlap_frames))
            start_sec = max(0.0, float(delivered - overlap_frames) / fps)
            dur_sec = float(overlap_frames) / fps
            
            rgb_tail = media.load_video_tensor(
                media_path, start_sec, dur_sec, out_fps=fps,
                max_short_edge=min(canvas_w, canvas_h)
            )
            if rgb_tail is not None and getattr(rgb_tail, "ndim", 0) == 4 and rgb_tail.shape[0] > 0:
                step = max(1, int(round(fps / 2.0)))  # 2 FPS sampling rate
                indices = list(range(0, rgb_tail.shape[0], step))
                semantic_ref_frames = [rgb_tail[i:i+1].cpu() for i in indices]
                _LOG.info("[H3.E - Director] Extracted %d semantic reference frames at 2 FPS", len(semantic_ref_frames))
        except Exception as e:
            _LOG.warning("[H3.E - Director] Could not load media '%s' for semantic subsampling: %s", media_path, e)
            semantic_ref_frames = []
    else:
        semantic_ref_frames = []
        
    return minimax_keyframes, minimax_audio_ref, semantic_ref_frames


def attach_hybrid_conditioning(
    conditioning: list,
    minimax_keyframes: list[dict[str, Any]],
    minimax_audio_ref: Optional[dict[str, Any]] = None,
    duration_frames: Optional[int] = None,
) -> list:
    """Attach keyframe and audio continuation metadata to a ComfyUI conditioning list."""
    if not conditioning or not isinstance(conditioning, list):
        return conditioning
    
    # Determine whether native guides API is active
    is_native = False
    try:
        is_native = native_guides_active()
    except Exception:
        is_native = False

    out = []
    for item in conditioning:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            out.append(item)
            continue
        
        emb, meta = item[0], dict(item[1]) if isinstance(item[1], dict) else {}
        
        # Merge keyframes
        existing_kfs = list(meta.get("minimax_keyframes", []))
        merged_kfs = existing_kfs + list(minimax_keyframes)
        
        # Audio continuation placement
        if minimax_audio_ref is not None:
            anchor_mode = minimax_audio_ref.get("anchor_mode", "before")
            if anchor_mode == "off":
                pass
            elif anchor_mode in ("ref", "in_latent_freeze + ref", "golden_experience"):
                # Unanchored acoustic style reference with 3D-RoPE boundary lock (end_frame=0.0)
                existing_refs = list(meta.get("minimax_refs", []))
                ref_copy = dict(minimax_audio_ref)
                ref_copy[MC_AUDIO_KEY] = 0.0
                ref_copy.pop("motion_context_audio_pixel_span", None)
                ref_copy.pop("motion_context_audio_pixel_index", None)
                ref_copy["anchor_mode"] = "ref"
                existing_refs.append(ref_copy)
                meta["minimax_refs"] = existing_refs
                _LOG.info("[H3.E - Director] Attached audio reference with 3D-RoPE boundary lock (end_frame=0.0)")
            elif is_native:
                # Under PR #15439 native guides mode, place audio continuation on the target timeline
                rt = int(minimax_audio_ref.get("ref_audio_t", 0))
                audio_latent = minimax_audio_ref.get("audio_latent")
                end_frame = float(minimax_audio_ref.get(MC_AUDIO_KEY, 0.0))
                if rt > 0 and audio_latent is not None:
                    audio_start = float(end_frame - (rt / FRAME_RESCALE))
                    audio_kf = {
                        "resolved_frame_index": audio_start,
                        MC_KEY: audio_start,
                        "audio_latent": audio_latent,
                    }
                    merged_kfs.append(audio_kf)
                    _LOG.info("[H3.E - Director] Attached native audio continuation guide (start=%.3f, end=%.3f, steps=%d, mode=%s)",
                              audio_start, end_frame, rt, anchor_mode)
            else:
                # Legacy mode: place in minimax_refs for _fixup_audio translation
                existing_refs = list(meta.get("minimax_refs", []))
                existing_refs.append(minimax_audio_ref)
                meta["minimax_refs"] = existing_refs
                _LOG.info("[H3.E - Director] Attached legacy audio continuation reference (end_frame=%.3f, steps=%d, mode=%s)",
                          float(minimax_audio_ref.get(MC_AUDIO_KEY, 0.0)),
                          int(minimax_audio_ref.get("ref_audio_t", 0)),
                          anchor_mode)

        if merged_kfs:
            meta["minimax_keyframes"] = merged_kfs
        elif "minimax_keyframes" in meta and not meta["minimax_keyframes"]:
            meta.pop("minimax_keyframes", None)

        if duration_frames is not None:
            meta["minimax_frame_count"] = int(duration_frames)

        out.append([emb, meta])
    
    return out
