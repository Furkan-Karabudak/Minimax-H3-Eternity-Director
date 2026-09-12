"""Multi-Clip Stitching and Audio Seam Engine for H3 Eternity Edition.

Provides lossless video frame concatenation, duplicate head-overlap trimming across
temporal lattice boundaries (1, 5, 22, 39 frames), and sample-accurate audio seam
engineering (smartseam, crossfade, declick, hard_cut) with absolute 0 ms A/V drift.
"""

from __future__ import annotations

import logging
import math
import os
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import torch
import torch.nn.functional as F

try:
    import av
    _HAVE_PYAV = True
except ImportError:
    _HAVE_PYAV = False

try:
    import safetensors.torch
    _HAVE_SAFETENSORS = True
except ImportError:
    _HAVE_SAFETENSORS = False

from ..H3Eternity_Director.render_plan import (
    DEFAULT_OVERLAP,
    VALID_OVERLAPS,
    SavedArtifact,
)

_LOG = logging.getLogger("minimax_h3_eternity.stitch_engine")

AUDIO_SR = 48000
VIDEO_FPS = 24.0


# -----------------------------------------------------------------------------
# Video Frame Loading & Fallback
# -----------------------------------------------------------------------------

def load_iteration_frames(
    artifact: dict[str, Any] | SavedArtifact,
    vae: Optional[Any] = None,
    target_fps: float = VIDEO_FPS,
    fallback_h: int = 768,
    fallback_w: int = 1344,
) -> torch.Tensor:
    """Loads video frames from lossless MKV or decodes from raw .latent Safetensors.

    Priority 1: Read directly from lossless FFV1/BGRA MKV via PyAV.
    Priority 2: Fallback to decoding uncompressed samples_video from Safetensors via VAE.

    Returns:
        torch.Tensor of shape [N, H, W, 3] in float32 [0.0, 1.0].
    """
    art_dict = artifact.to_dict() if isinstance(artifact, SavedArtifact) else artifact
    media_path = str(art_dict.get("media_path", "")).strip()
    latent_path = str(art_dict.get("latent_path", "")).strip()
    iter_idx = int(art_dict.get("iteration", 0))

    # Priority 1: PyAV Lossless Media Decode
    if media_path and os.path.isfile(media_path) and _HAVE_PYAV:
        try:
            frames: List[np.ndarray] = []
            with av.open(media_path) as container:
                if container.streams.video:
                    stream = container.streams.video[0]
                    stream.thread_type = "AUTO"
                    for frame in container.decode(stream):
                        rgb_frame = frame.reformat(format="rgb24").to_ndarray()
                        frames.append(rgb_frame)
            if frames:
                tensor_frames = torch.from_numpy(np.stack(frames, axis=0)).to(torch.float32) / 255.0
                _LOG.info("[H3.E - Finalize] Loaded %d frames from media %s", tensor_frames.shape[0], media_path)
                return tensor_frames
        except Exception as e:
            _LOG.warning("[H3.E - Finalize] Failed to decode MKV frames from '%s': %s", media_path, e)

    # Priority 2: Safetensors Latent + VAE Decode Fallback
    if latent_path and os.path.isfile(latent_path) and vae is not None:
        try:
            tensors: Optional[Dict[str, torch.Tensor]] = None
            if _HAVE_SAFETENSORS:
                try:
                    tensors = safetensors.torch.load_file(latent_path)
                except Exception as e:
                    _LOG.warning("[H3.E - Finalize] safetensors.load_file failed: %s, trying torch.load", e)
            if tensors is None:
                try:
                    tensors = torch.load(latent_path, map_location="cpu", weights_only=True)
                except Exception:
                    tensors = torch.load(latent_path, map_location="cpu")

            if isinstance(tensors, dict) and "samples_video" in tensors:
                zv = tensors["samples_video"]
                if zv.ndim == 5:
                    _LOG.info("[H3.E - Finalize] Fallback VAE decoding raw latent for iteration %d...", iter_idx)
                    try:
                        import nodes as comfy_nodes
                        vae_decoder = comfy_nodes.VAEDecode()
                        decoded = vae_decoder.decode(vae, {"samples": zv})[0]
                        return decoded.to(torch.float32).cpu()
                    except Exception:
                        if hasattr(vae, "decode"):
                            decoded = vae.decode(zv)
                            if isinstance(decoded, (tuple, list)):
                                decoded = decoded[0]
                            if decoded.ndim == 5:
                                # [B, C, T, H, W] -> [T, H, W, C]
                                decoded = decoded[0].permute(1, 2, 3, 0)
                            return decoded.to(torch.float32).cpu()
        except Exception as e:
            _LOG.error("[H3.E - Finalize] Fallback VAE decode failed for '%s': %s", latent_path, e)

    # Priority 3: Synthetic Blank Tensor Fallback (for testing / offline harness)
    delivered = int(art_dict.get("delivered_frames", 124))
    _LOG.warning(
        "[H3.E - Finalize] Video artifact could not be loaded for iteration %d "
        "(media: '%s', latent: '%s'). Returning synthetic blank frames.",
        iter_idx, media_path, latent_path
    )
    return torch.zeros((delivered, fallback_h, fallback_w, 3), dtype=torch.float32)


# -----------------------------------------------------------------------------
# Audio Loading & Decoding
# -----------------------------------------------------------------------------

def load_iteration_audio(
    artifact: dict[str, Any] | SavedArtifact,
    audio_vae: Optional[Any] = None,
    target_sr: int = AUDIO_SR,
) -> Optional[torch.Tensor]:
    """Loads stereo audio from FLAC, MKV, or decodes from raw samples_audio latent.

    Returns:
        torch.Tensor of shape [2, N_samples] in float32 at target_sr (48000 Hz),
        or None if no audio exists.
    """
    art_dict = artifact.to_dict() if isinstance(artifact, SavedArtifact) else artifact
    audio_path = str(art_dict.get("audio_path", "")).strip()
    media_path = str(art_dict.get("media_path", "")).strip()
    latent_path = str(art_dict.get("latent_path", "")).strip()
    iter_idx = int(art_dict.get("iteration", 0))

    # Priority 1: Standalone FLAC/WAV Audio Decode
    for path_candidate in [audio_path, media_path]:
        if path_candidate and os.path.isfile(path_candidate) and _HAVE_PYAV:
            try:
                blocks: List[torch.Tensor] = []
                with av.open(path_candidate) as container:
                    if container.streams.audio:
                        stream = container.streams.audio[0]
                        resampler = av.AudioResampler(format="fltp", layout="stereo", rate=target_sr)
                        for frame in container.decode(stream):
                            for out in resampler.resample(frame):
                                blocks.append(torch.from_numpy(out.to_ndarray()))
                        for out in resampler.resample(None):
                            blocks.append(torch.from_numpy(out.to_ndarray()))
                if blocks:
                    audio_tensor = torch.cat(blocks, dim=1).to(torch.float32)
                    _LOG.info("[H3.E - Finalize] Loaded %d audio samples from %s", audio_tensor.shape[1], path_candidate)
                    return audio_tensor
            except Exception as e:
                _LOG.warning("[H3.E - Finalize] Failed to decode audio from '%s': %s", path_candidate, e)

    # Priority 2: Safetensors samples_audio + Audio VAE Decode Fallback
    if latent_path and os.path.isfile(latent_path) and audio_vae is not None:
        try:
            tensors: Optional[Dict[str, torch.Tensor]] = None
            if _HAVE_SAFETENSORS:
                try:
                    tensors = safetensors.torch.load_file(latent_path)
                except Exception:
                    pass
            if tensors is None:
                try:
                    tensors = torch.load(latent_path, map_location="cpu", weights_only=True)
                except Exception:
                    tensors = torch.load(latent_path, map_location="cpu")

            if isinstance(tensors, dict) and "samples_audio" in tensors:
                za = tensors["samples_audio"]
                _LOG.info("[H3.E - Finalize] Fallback Audio VAE decoding for iteration %d...", iter_idx)
                try:
                    from ..H3Eternity_Director.minimax_core import audio_nodes as get_audio_nodes
                    an = get_audio_nodes()
                    if an and hasattr(an, "VAEDecodeAudio"):
                        decoded = an.VAEDecodeAudio.execute(audio_vae, {"samples": za})
                        if isinstance(decoded, dict) and "waveform" in decoded:
                            wf = decoded["waveform"]
                            if wf.ndim == 3:
                                wf = wf[0]
                            return wf.to(torch.float32).cpu()
                except Exception as e:
                    _LOG.warning("[H3.E - Finalize] Audio VAE decoding error: %s", e)
        except Exception as e:
            _LOG.warning("[H3.E - Finalize] Failed to load audio latent from '%s': %s", latent_path, e)

    return None


# -----------------------------------------------------------------------------
# Video Head-Overlap Trimming
# -----------------------------------------------------------------------------

def trim_head_overlap(frames: torch.Tensor, overlap_frames: int) -> torch.Tensor:
    """Drops the leading duplicate overlap frames from continuation iteration clips.

    Args:
        frames: Video tensor of shape [N, H, W, 3].
        overlap_frames: Number of head frames to drop (1, 5, 22, 39).

    Returns:
        Trimmed tensor of shape [max(1, N - overlap_frames), H, W, 3].
    """
    if overlap_frames <= 0 or frames.ndim != 4:
        return frames

    total_frames = frames.shape[0]
    if total_frames <= overlap_frames:
        _LOG.warning(
            "[H3.E - Finalize] Iteration clip length (%d) is <= overlap_frames (%d). "
            "Preserving final frame to avoid empty tensor.",
            total_frames, overlap_frames
        )
        return frames[-1:]

    trimmed = frames[overlap_frames:]
    _LOG.info("[H3.E - Finalize] Trimmed %d head frames (remaining: %d frames)", overlap_frames, trimmed.shape[0])
    return trimmed


def harmonize_and_blend_video_overlap(
    chunk_a: torch.Tensor,
    chunk_b: torch.Tensor,
    overlap_frames: int,
    harmonize_color: bool = True,
    smooth_blend: bool = True,
    anti_flashbang: bool = True,
) -> torch.Tensor:
    """Stitches two video clips across their mutual overlap window.

    Eliminates inter-clip flicker and color popping by:
    1. Estimating per-channel color statistics (mean and std) across mutual overlap frames.
    2. Calibrating chunk_b (gain and bias) to match chunk_a's color moment.
    3. Blending the mutual overlap frames with an equal-power cosine curve.

    Total delivered frames: Na + Nb - overlap_frames (exact 0 ms A/V match).

    Args:
        chunk_a: Preceding video tensor [Na, H, W, 3] in float32 [0.0, 1.0].
        chunk_b: Subsequent video tensor [Nb, H, W, 3] in float32 [0.0, 1.0].
        overlap_frames: Mutual temporal overlap frame count (1, 5, 22, 39).
        harmonize_color: Whether to normalize chunk_b color to chunk_a.
        smooth_blend: Whether to apply cosine cross-dissolve across overlap frames.
        anti_flashbang: Whether to suppress impulse luminance spikes across boundary.

    Returns:
        Assembled video tensor [Na + Nb - overlap_frames, H, W, 3].
    """
    if chunk_a is None or chunk_a.shape[0] == 0:
        return chunk_b if chunk_b is not None else torch.zeros((0, 768, 1344, 3), dtype=torch.float32)
    if chunk_b is None or chunk_b.shape[0] == 0:
        return chunk_a

    overlap_frames = max(0, min(overlap_frames, chunk_a.shape[0], chunk_b.shape[0]))
    if overlap_frames == 0:
        return torch.cat([chunk_a, chunk_b], dim=0)

    tail_a = chunk_a[-overlap_frames:]
    head_b = chunk_b[:overlap_frames]

    # 1. Color Harmonization
    if harmonize_color:
        mean_a = tail_a.mean(dim=(0, 1, 2), keepdim=True)
        std_a = tail_a.std(dim=(0, 1, 2), keepdim=True)
        mean_b = head_b.mean(dim=(0, 1, 2), keepdim=True)
        std_b = head_b.std(dim=(0, 1, 2), keepdim=True)

        gain = torch.clamp(std_a / (std_b + 1e-6), min=0.8, max=1.25)
        bias = torch.clamp(mean_a - gain * mean_b, min=-0.2, max=0.2)

        calibrated_b = torch.clamp(chunk_b * gain + bias, 0.0, 1.0)
        head_b = calibrated_b[:overlap_frames]
        tail_b = calibrated_b[overlap_frames:]
        _LOG.info(
            "[H3.E - Finalize] Color harmonized iteration seam: gain=[%.3f, %.3f, %.3f], bias=[%.3f, %.3f, %.3f]",
            float(gain[0, 0, 0, 0]), float(gain[0, 0, 0, 1]), float(gain[0, 0, 0, 2]),
            float(bias[0, 0, 0, 0]), float(bias[0, 0, 0, 1]), float(bias[0, 0, 0, 2]),
        )
    else:
        tail_b = chunk_b[overlap_frames:]

    # 2. Anti-Flashbang Overlap Boundary Equalization
    if anti_flashbang and overlap_frames > 1:
        lum_head = 0.299 * head_b[:, :, :, 0].mean(dim=(1, 2)) + \
                   0.587 * head_b[:, :, :, 1].mean(dim=(1, 2)) + \
                   0.114 * head_b[:, :, :, 2].mean(dim=(1, 2))
        last_i = overlap_frames - 1
        if last_i >= 1 and tail_b.shape[0] > 0:
            lum_next = 0.299 * tail_b[0, :, :, 0].mean() + \
                       0.587 * tail_b[0, :, :, 1].mean() + \
                       0.114 * tail_b[0, :, :, 2].mean()
            med = torch.median(torch.stack([lum_head[last_i - 1], lum_head[last_i], lum_next]))
            jump = torch.abs(lum_head[last_i] - med)
            if jump > 0.035:
                target = 0.5 * (lum_head[last_i - 1] + lum_next)
                gain = torch.clamp(target / (lum_head[last_i] + 1e-6), 0.70, 1.30)
                head_b[last_i] = torch.clamp(head_b[last_i] * gain, 0.0, 1.0)
                _LOG.info("[H3.E - Finalize] Anti-Flashbang equalized head_b boundary frame (jump=%.4f, gain=%.4f)", float(jump), float(gain))

    # 3. Smooth Overlap Blending
    if smooth_blend and overlap_frames > 1:
        t = torch.linspace(0.0, math.pi, overlap_frames, dtype=chunk_a.dtype, device=chunk_a.device)
        w = ((1.0 - torch.cos(t)) / 2.0).view(overlap_frames, 1, 1, 1)
        blended = (1.0 - w) * tail_a + w * head_b
    elif smooth_blend and overlap_frames == 1:
        blended = 0.5 * tail_a + 0.5 * head_b
    else:
        blended = tail_a

    lead_a = chunk_a[:-overlap_frames] if chunk_a.shape[0] > overlap_frames else chunk_a[:0]
    assembled = torch.cat([lead_a, blended, tail_b], dim=0)
    _LOG.info("[H3.E - Finalize] Blended %d overlap frames into assembled video (total: %d frames)",
              overlap_frames, assembled.shape[0])
    return assembled


def apply_seam_anti_flashbang(
    video: torch.Tensor,
    seam_indices: List[int],
    radius: int = 4,
    threshold: float = 0.035,
) -> torch.Tensor:
    """Eliminates sudden single-frame luminance bursts (flashbangs) and smooths auto-exposure across seams.

    Args:
        video: Assembled video tensor of shape [N, H, W, 3] in float32 [0.0, 1.0].
        seam_indices: List of cut/blend boundary frame indices.
        radius: Number of frames around each seam to inspect and equalize.
        threshold: Luminance spike threshold (default 0.035, ~9/255 pixel levels).

    Returns:
        Exposure-equalized video tensor.
    """
    if video is None or video.shape[0] < 3 or not seam_indices:
        return video

    total_frames = video.shape[0]
    lum = 0.299 * video[:, :, :, 0].mean(dim=(1, 2)) + \
          0.587 * video[:, :, :, 1].mean(dim=(1, 2)) + \
          0.114 * video[:, :, :, 2].mean(dim=(1, 2))

    for seam_idx in seam_indices:
        start_idx = max(1, seam_idx - radius)
        end_idx = min(total_frames - 1, seam_idx + radius + 1)

        # 1. Detect and suppress isolated impulse flashbang spikes
        for i in range(start_idx, end_idx):
            med = torch.median(lum[i - 1:i + 2])
            jump = torch.abs(lum[i] - med)
            if jump > threshold:
                target = 0.5 * (lum[i - 1] + lum[i + 1])
                gain = torch.clamp(target / (lum[i] + 1e-6), 0.10, 3.0)
                video[i] = torch.clamp(video[i] * gain, 0.0, 1.0)
                _LOG.info(
                    "[H3.E - Finalize] Anti-Flashbang suppressed luminance spike at frame %d: jump=%.4f, gain=%.4f",
                    i, float(jump), float(gain)
                )
                lum[i] = target

        # 2. Smooth auto-exposure transition across seam if step discontinuity exists
        if radius >= 2 and 0 < seam_idx < total_frames:
            pre_lum = lum[max(0, seam_idx - radius):seam_idx].mean()
            post_lum = lum[seam_idx:min(total_frames, seam_idx + radius)].mean()
            step_diff = post_lum - pre_lum
            if torch.abs(step_diff) > threshold:
                span = end_idx - start_idx
                if span > 1:
                    t = torch.linspace(0.0, 1.0, span, dtype=video.dtype, device=video.device)
                    fade_w = 0.5 * (1.0 + torch.cos(math.pi * t))
                    for idx_offset, k in enumerate(range(start_idx, end_idx)):
                        target_level = pre_lum * fade_w[idx_offset] + post_lum * (1.0 - fade_w[idx_offset])
                        g = torch.clamp(target_level / (lum[k] + 1e-6), 0.85, 1.18)
                        video[k] = torch.clamp(video[k] * g, 0.0, 1.0)
                        lum[k] = target_level

    return video


# -----------------------------------------------------------------------------
# Audio Seam Splicing Algorithms
# -----------------------------------------------------------------------------

def _equal_power_crossfade(
    chunk_a: torch.Tensor,
    chunk_b: torch.Tensor,
    fade_len: int,
) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """Generates an equal-power (sin/cos) crossfade between tail of chunk_a and head of chunk_b.

    Returns:
        (lead_a, blended, tail_b)
    """
    fade_len = max(1, min(fade_len, chunk_a.shape[1], chunk_b.shape[1]))
    lead_a = chunk_a[:, :-fade_len] if chunk_a.shape[1] > fade_len else chunk_a[:, :0]
    tail_b = chunk_b[:, fade_len:] if chunk_b.shape[1] > fade_len else chunk_b[:, :0]

    part_a = chunk_a[:, -fade_len:]
    part_b = chunk_b[:, :fade_len]

    t = torch.linspace(0.0, math.pi / 2.0, fade_len, dtype=chunk_a.dtype, device=chunk_a.device)
    w_a = torch.cos(t).unsqueeze(0)
    w_b = torch.sin(t).unsqueeze(0)

    blended = w_a * part_a + w_b * part_b
    return lead_a, blended, tail_b


def splice_audio_seam(
    chunk_a: torch.Tensor,
    chunk_b: torch.Tensor,
    overlap_samples: int,
    strategy: str = "crossfade_end",
    fade_ms: float = 12.0,
) -> torch.Tensor:
    """Splices two sequential audio clips across their mutual overlap window.

    Args:
        chunk_a: Preceding audio chunk [2, Na].
        chunk_b: Subsequent audio chunk [2, Nb].
        overlap_samples: Number of overlapping audio samples (O * 2000 at 48 kHz / 24 FPS).
        strategy: 'crossfade_end' (boundary micro-fade) | 'instant' (abrupt cut at boundary).
                  Legacy aliases 'smartseam', 'declick', 'crossfade', 'hard_cut' are also supported.
        fade_ms: Transition micro-fade duration in milliseconds (default 12.0 ms).

    Returns:
        Spliced audio tensor [2, Na + Nb - overlap_samples].
    """
    if chunk_a is None or chunk_a.shape[1] == 0:
        return chunk_b if chunk_b is not None else torch.zeros((2, 0), dtype=torch.float32)
    if chunk_b is None or chunk_b.shape[1] == 0:
        return chunk_a

    overlap_samples = max(0, min(overlap_samples, chunk_a.shape[1], chunk_b.shape[1]))
    if overlap_samples == 0 or strategy in ("instant", "hard_cut"):
        # Direct instant cut at video cut boundary: chunk_a plays until boundary, chunk_b starts at boundary
        return torch.cat([chunk_a, chunk_b[:, overlap_samples:]], dim=1)

    if strategy == "crossfade":
        # Full overlap equal-power blend across the entire overlap span
        lead_a = chunk_a[:, :-overlap_samples] if chunk_a.shape[1] > overlap_samples else chunk_a[:, :0]
        tail_b = chunk_b[:, overlap_samples:] if chunk_b.shape[1] > overlap_samples else chunk_b[:, :0]
        part_a = chunk_a[:, -overlap_samples:]
        part_b = chunk_b[:, :overlap_samples]

        t = torch.linspace(0.0, math.pi / 2.0, overlap_samples, dtype=chunk_a.dtype, device=chunk_a.device)
        blended = torch.cos(t).unsqueeze(0) * part_a + torch.sin(t).unsqueeze(0) * part_b
        return torch.cat([lead_a, blended, tail_b], dim=1)

    # Boundary-Exact Micro-Fade ('declick' and 'smartseam')
    # Video cut occurs at the END of overlap (chunk_a plays in full, chunk_b drops overlap_samples).
    # Audio matches video cut to the microsecond: chunk_a plays until cut, chunk_b starts at cut.
    # At the seam boundary, apply an equal-power micro-fade of length fade_len (default 12ms = 576 samples at 48kHz).
    fade_len = max(1, min(int(round(AUDIO_SR * (float(fade_ms) / 1000.0))), overlap_samples, chunk_a.shape[1], chunk_b.shape[1]))
    if fade_len <= 1:
        return torch.cat([chunk_a, chunk_b[:, overlap_samples:]], dim=1)

    part_a = chunk_a[:, -fade_len:]
    part_b = chunk_b[:, overlap_samples - fade_len : overlap_samples]

    t = torch.linspace(0.0, math.pi / 2.0, fade_len, dtype=chunk_a.dtype, device=chunk_a.device)
    blended = torch.cos(t).unsqueeze(0) * part_a + torch.sin(t).unsqueeze(0) * part_b

    lead_a = chunk_a[:, :-fade_len] if chunk_a.shape[1] > fade_len else chunk_a[:, :0]
    tail_b = chunk_b[:, overlap_samples:] if chunk_b.shape[1] > overlap_samples else chunk_b[:, :0]
    return torch.cat([lead_a, blended, tail_b], dim=1)


# -----------------------------------------------------------------------------
# Duration Locking (Zero A/V Drift)
# -----------------------------------------------------------------------------

def lock_audio_duration(
    audio_waveform: torch.Tensor,
    total_frames: int,
    fps: float = VIDEO_FPS,
    sample_rate: int = AUDIO_SR,
) -> torch.Tensor:
    """Clamps or pads audio waveform to match the exact target video duration.

    Target samples: round(total_frames / fps * sample_rate).
    Guarantees absolute 0 ms A/V synchronization drift across any number of iterations.
    """
    target_samples = max(0, int(round((float(total_frames) / float(fps)) * float(sample_rate))))
    current_samples = audio_waveform.shape[1]

    if current_samples == target_samples:
        return audio_waveform

    if current_samples > target_samples:
        _LOG.info("[H3.E - Finalize] Clamping audio duration (%d -> %d samples)", current_samples, target_samples)
        return audio_waveform[:, :target_samples]
    else:
        pad_amt = target_samples - current_samples
        _LOG.info("[H3.E - Finalize] Padding audio duration with silence (%d -> %d samples)", current_samples, target_samples)
        return F.pad(audio_waveform, (0, pad_amt))


# -----------------------------------------------------------------------------
# High-Level Multi-Clip Assembly Orchestration
# -----------------------------------------------------------------------------

def assemble_multi_clip(
    plan: dict[str, Any],
    seam_video: str = "smooth_blend",
    harmonize_color: bool = True,
    trim_head_overlap: bool = True,
    seam_audio: str = "crossfade_end",
    seam_audio_fade_ms: float = 12.0,
    vae: Optional[Any] = None,
    audio_vae: Optional[Any] = None,
    anti_flashbang: bool = True,
    **kwargs: Any,
) -> Tuple[torch.Tensor, dict[str, Any]]:
    """Stitches all saved iteration clips into unified final_images and final_audio.

    Args:
        plan: Active render_plan dictionary containing canvas, iterations, and saved_artifacts.
        seam_video: Video transition strategy: 'smooth_blend' (color-harmonized cosine cross-dissolve)
                    or 'hard_cut' (knife-edge drop of overlap frames).
        harmonize_color: Whether to normalize gain and bias across clips to eliminate VAE color shift.
        trim_head_overlap: Whether to drop/blend duplicate head overlap frames on continuation shots.
        seam_audio: Audio stitching algorithm: 'crossfade_end', 'instant' (or legacy aliases).
        seam_audio_fade_ms: Transition micro-fade duration in milliseconds (default: 12.0ms).
                    or 'hard_cut' (knife-edge drop of overlap frames).
        harmonize_color: Whether to normalize gain and bias across clips to eliminate VAE color shift.
        vae: Video VAE for fallback latent decoding if media is missing.
        audio_vae: Audio VAE for fallback latent decoding.

    Returns:
        (final_images [Total_Frames, H, W, 3], final_audio {"waveform": [1, 2, N], "sample_rate": 48000})
    """
    canvas = plan.get("canvas", {})
    fps = float(canvas.get("fps", VIDEO_FPS))
    width = int(canvas.get("width", 1344))
    height = int(canvas.get("height", 768))
    eff_fade_ms = float(kwargs.get("seam_fade_ms", seam_audio_fade_ms))

    saved_artifacts = list(plan.get("saved_artifacts", []))
    iterations = list(plan.get("iterations", []))

    # Sort artifacts by iteration index
    saved_artifacts.sort(key=lambda a: int(a.get("iteration", 0)))

    if not saved_artifacts:
        _LOG.warning("[H3.E - Finalize] No saved artifacts found in render_plan. Returning blank sequence.")
        empty_images = torch.zeros((1, height, width, 3), dtype=torch.float32)
        empty_audio = {
            "waveform": torch.zeros((1, 2, AUDIO_SR), dtype=torch.float32),
            "sample_rate": AUDIO_SR,
        }
        return empty_images, empty_audio

    # Effective VAEs from socket or plan
    eff_vae = vae or plan.get("vae")
    eff_audio_vae = audio_vae or plan.get("audio_vae")

    accum_video: Optional[torch.Tensor] = None
    chain_root_iter_idx: int = 0
    chain_root_mean: Optional[torch.Tensor] = None
    chain_root_std: Optional[torch.Tensor] = None
    audio_chunks: List[Tuple[Optional[torch.Tensor], int, int]] = []  # (waveform, overlap_lead_frames, raw_frame_count)
    timeline_segments: List[Dict[str, Any]] = []

    for i, art in enumerate(saved_artifacts):
        iter_idx = int(art.get("iteration", art.get("iteration_index", i)))
        shot_num = iter_idx + 1

        # Determine overlap lead frames and whether this is a hard scene cut
        overlap_frames = 0
        audio_overlap_frames = 0
        is_hard = False
        if iter_idx < len(iterations):
            is_hard = bool(iterations[iter_idx].get("is_hard_cut", iterations[iter_idx].get("is_chain_cut", False)))
            if i > 0 and trim_head_overlap:
                overlap_frames = int(iterations[iter_idx].get("overlap_lead_frames", DEFAULT_OVERLAP))
        else:
            is_hard = bool(art.get("is_hard_cut", art.get("is_chain_cut", False)))
            if i > 0 and trim_head_overlap:
                overlap_frames = int(art.get("overlap_lead_frames", DEFAULT_OVERLAP))

        if overlap_frames > 0 and overlap_frames not in VALID_OVERLAPS:
            overlap_frames = DEFAULT_OVERLAP
        audio_overlap_frames = 0 if is_hard else overlap_frames

        # 1. Load Video Frames
        raw_frames = load_iteration_frames(art, vae=eff_vae, target_fps=fps, fallback_h=height, fallback_w=width)

        if accum_video is None:
            accum_video = raw_frames
            n_raw = raw_frames.shape[0] if raw_frames is not None else 0
            timeline_segments.append({
                "type": "shot",
                "iteration": iter_idx,
                "shot_number": shot_num,
                "start_frame": 0,
                "end_frame": n_raw,
            })
            if raw_frames is not None and raw_frames.shape[0] > 0:
                chain_root_iter_idx = iter_idx
                root_anchor = raw_frames[0:1]
                chain_root_mean = root_anchor.mean(dim=(0, 1, 2), keepdim=True)
                chain_root_std = root_anchor.std(dim=(0, 1, 2), keepdim=True)
                _LOG.info(
                    "[H3.E - Finalize] Initialized Chain Root color anchor at Iteration %d (first frame baseline: mean=[%.3f, %.3f, %.3f], std=[%.3f, %.3f, %.3f])",
                    chain_root_iter_idx,
                    float(chain_root_mean[0, 0, 0, 0]), float(chain_root_mean[0, 0, 0, 1]), float(chain_root_mean[0, 0, 0, 2]),
                    float(chain_root_std[0, 0, 0, 0]), float(chain_root_std[0, 0, 0, 1]), float(chain_root_std[0, 0, 0, 2]),
                )
        elif is_hard:
            # Chain cut / Hard cut starts a new scene chain; reset color anchor to this clip's first frame
            n_prev = accum_video.shape[0] if accum_video is not None else 0
            if raw_frames is not None and raw_frames.shape[0] > 0:
                chain_root_iter_idx = iter_idx
                root_anchor = raw_frames[0:1]
                chain_root_mean = root_anchor.mean(dim=(0, 1, 2), keepdim=True)
                chain_root_std = root_anchor.std(dim=(0, 1, 2), keepdim=True)
                _LOG.info(
                    "[H3.E - Finalize] Chain cut detected at Iteration %d. Reset Chain Root color anchor (new baseline: mean=[%.3f, %.3f, %.3f], std=[%.3f, %.3f, %.3f])",
                    chain_root_iter_idx,
                    float(chain_root_mean[0, 0, 0, 0]), float(chain_root_mean[0, 0, 0, 1]), float(chain_root_mean[0, 0, 0, 2]),
                    float(chain_root_std[0, 0, 0, 0]), float(chain_root_std[0, 0, 0, 1]), float(chain_root_std[0, 0, 0, 2]),
                )
            accum_video = torch.cat([accum_video, raw_frames], dim=0)
            n_raw = raw_frames.shape[0] if raw_frames is not None else 0
            timeline_segments.append({
                "type": "shot",
                "iteration": iter_idx,
                "shot_number": shot_num,
                "start_frame": n_prev,
                "end_frame": n_prev + n_raw,
            })
        else:
            # Soft continuation: calibrate raw_frames against the current Chain Root's first frame
            if harmonize_color and chain_root_mean is not None and chain_root_std is not None and raw_frames.shape[0] > 0:
                cur_anchor = raw_frames[0:1]
                cur_mean = cur_anchor.mean(dim=(0, 1, 2), keepdim=True)
                cur_std = cur_anchor.std(dim=(0, 1, 2), keepdim=True)
                g = torch.clamp(chain_root_std / (cur_std + 1e-6), min=0.85, max=1.18)
                b = torch.clamp(chain_root_mean - g * cur_mean, min=-0.15, max=0.15)
                raw_frames = torch.clamp(raw_frames * g + b, 0.0, 1.0)
                _LOG.info(
                    "[H3.E - Finalize] Chain Root (iter %d) Color Anchor calibrated Iteration %d: gain=[%.3f, %.3f, %.3f], bias=[%.3f, %.3f, %.3f]",
                    chain_root_iter_idx, iter_idx,
                    float(g[0, 0, 0, 0]), float(g[0, 0, 0, 1]), float(g[0, 0, 0, 2]),
                    float(b[0, 0, 0, 0]), float(b[0, 0, 0, 1]), float(b[0, 0, 0, 2]),
                )

            n_prev = accum_video.shape[0] if accum_video is not None else 0
            if not trim_head_overlap or overlap_frames <= 0:
                accum_video = torch.cat([accum_video, raw_frames], dim=0)
                n_raw = raw_frames.shape[0] if raw_frames is not None else 0
                timeline_segments.append({
                    "type": "shot",
                    "iteration": iter_idx,
                    "shot_number": shot_num,
                    "start_frame": n_prev,
                    "end_frame": n_prev + n_raw,
                })
            elif seam_video == "hard_cut":
                trimmed = trim_head_overlap_fn(raw_frames, overlap_frames)
                accum_video = torch.cat([accum_video, trimmed], dim=0)
                n_trim = trimmed.shape[0] if trimmed is not None else 0
                timeline_segments.append({
                    "type": "shot",
                    "iteration": iter_idx,
                    "shot_number": shot_num,
                    "start_frame": n_prev,
                    "end_frame": n_prev + n_trim,
                })
            else:
                # Smooth cosine blending across mutual overlap window (without secondary localized bias)
                effective_overlap = min(overlap_frames, n_prev, raw_frames.shape[0] if raw_frames is not None else 0)
                if timeline_segments and timeline_segments[-1]["type"] == "shot":
                    prev_seg = timeline_segments[-1]
                    prev_shot = prev_seg["shot_number"]
                    prev_seg["end_frame"] = max(prev_seg["start_frame"], n_prev - effective_overlap)
                else:
                    prev_shot = shot_num - 1

                blend_start = max(0, n_prev - effective_overlap)
                blend_end = n_prev
                if effective_overlap > 0:
                    timeline_segments.append({
                        "type": "blend",
                        "from_iteration": iter_idx - 1,
                        "to_iteration": iter_idx,
                        "from_shot": prev_shot,
                        "to_shot": shot_num,
                        "start_frame": blend_start,
                        "end_frame": blend_end,
                        "overlap_frames": effective_overlap,
                    })

                accum_video = harmonize_and_blend_video_overlap(
                    chunk_a=accum_video,
                    chunk_b=raw_frames,
                    overlap_frames=overlap_frames,
                    harmonize_color=False,  # Already calibrated to Chain Root!
                    smooth_blend=True,
                    anti_flashbang=anti_flashbang,
                )
                n_new_total = accum_video.shape[0] if accum_video is not None else blend_end
                timeline_segments.append({
                    "type": "shot",
                    "iteration": iter_idx,
                    "shot_number": shot_num,
                    "start_frame": blend_end,
                    "end_frame": n_new_total,
                })

        # 2. Load Audio Waveform
        raw_audio = load_iteration_audio(art, audio_vae=eff_audio_vae, target_sr=AUDIO_SR)
        audio_chunks.append((raw_audio, audio_overlap_frames, raw_frames.shape[0]))

    final_images = accum_video if accum_video is not None else torch.zeros((1, height, width, 3), dtype=torch.float32)
    total_frames = final_images.shape[0]

    # 3. Anti-Flashbang Seam Smoothing & Auto-Exposure Transition
    if anti_flashbang and final_images.shape[0] > 3:
        seam_pts: List[int] = []
        for seg in timeline_segments:
            st = int(seg.get("start_frame", 0))
            if 0 < st < total_frames and st not in seam_pts:
                seam_pts.append(st)
            ed = int(seg.get("end_frame", 0))
            if 0 < ed < total_frames and ed not in seam_pts:
                seam_pts.append(ed)
        if seam_pts:
            final_images = apply_seam_anti_flashbang(final_images, seam_pts)

    if isinstance(plan, dict):
        plan["stitched_timeline"] = {
            "total_frames": total_frames,
            "segments": timeline_segments,
        }
    _LOG.info("[H3.E - Finalize] Multi-clip video assembled: %d total frames (%s)", total_frames, final_images.shape)

    # Concatenate & Splice Audio
    accum_audio: Optional[torch.Tensor] = None
    for i, (chunk, audio_overlap_f, raw_frame_count) in enumerate(audio_chunks):
        if chunk is None:
            # Generate silence for missing audio chunk matching video frame length
            chunk_samples = int(round((float(raw_frame_count) / fps) * float(AUDIO_SR)))
            chunk = torch.zeros((2, chunk_samples), dtype=torch.float32)

        if accum_audio is None:
            accum_audio = chunk
        else:
            overlap_samples = int(round((float(audio_overlap_f) / fps) * float(AUDIO_SR)))
            accum_audio = splice_audio_seam(
                chunk_a=accum_audio,
                chunk_b=chunk,
                overlap_samples=overlap_samples,
                strategy=seam_audio,
                fade_ms=eff_fade_ms,
            )

    if accum_audio is None or accum_audio.shape[1] == 0:
        target_samples = int(round((float(total_frames) / fps) * float(AUDIO_SR)))
        accum_audio = torch.zeros((2, target_samples), dtype=torch.float32)

    # Sample-accurate duration lock to video frame length
    locked_audio = lock_audio_duration(accum_audio, total_frames, fps=fps, sample_rate=AUDIO_SR)

    final_audio_payload = {
        "waveform": locked_audio.unsqueeze(0),  # [1, 2, N_samples]
        "sample_rate": AUDIO_SR,
    }

    return final_images, final_audio_payload


# Alias for backwards compatibility
trim_head_overlap_fn = trim_head_overlap
