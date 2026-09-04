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
                _LOG.info("[StitchEngine] Loaded %d frames from media %s", tensor_frames.shape[0], media_path)
                return tensor_frames
        except Exception as e:
            _LOG.warning("[StitchEngine] Failed to decode MKV frames from '%s': %s", media_path, e)

    # Priority 2: Safetensors Latent + VAE Decode Fallback
    if latent_path and os.path.isfile(latent_path) and vae is not None:
        try:
            tensors: Optional[Dict[str, torch.Tensor]] = None
            if _HAVE_SAFETENSORS:
                try:
                    tensors = safetensors.torch.load_file(latent_path)
                except Exception as e:
                    _LOG.warning("[StitchEngine] safetensors.load_file failed: %s, trying torch.load", e)
            if tensors is None:
                try:
                    tensors = torch.load(latent_path, map_location="cpu", weights_only=True)
                except Exception:
                    tensors = torch.load(latent_path, map_location="cpu")

            if isinstance(tensors, dict) and "samples_video" in tensors:
                zv = tensors["samples_video"]
                if zv.ndim == 5:
                    _LOG.info("[StitchEngine] Fallback VAE decoding raw latent for iteration %d...", iter_idx)
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
            _LOG.error("[StitchEngine] Fallback VAE decode failed for '%s': %s", latent_path, e)

    # Priority 3: Synthetic Blank Tensor Fallback (for testing / offline harness)
    delivered = int(art_dict.get("delivered_frames", 124))
    _LOG.warning(
        "[StitchEngine] Video artifact could not be loaded for iteration %d "
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
                    _LOG.info("[StitchEngine] Loaded %d audio samples from %s", audio_tensor.shape[1], path_candidate)
                    return audio_tensor
            except Exception as e:
                _LOG.warning("[StitchEngine] Failed to decode audio from '%s': %s", path_candidate, e)

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
                _LOG.info("[StitchEngine] Fallback Audio VAE decoding for iteration %d...", iter_idx)
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
                    _LOG.warning("[StitchEngine] Audio VAE decoding error: %s", e)
        except Exception as e:
            _LOG.warning("[StitchEngine] Failed to load audio latent from '%s': %s", latent_path, e)

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
            "[StitchEngine] Iteration clip length (%d) is <= overlap_frames (%d). "
            "Preserving final frame to avoid empty tensor.",
            total_frames, overlap_frames
        )
        return frames[-1:]

    trimmed = frames[overlap_frames:]
    _LOG.info("[StitchEngine] Trimmed %d head frames (remaining: %d frames)", overlap_frames, trimmed.shape[0])
    return trimmed


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
    strategy: str = "smartseam",
) -> torch.Tensor:
    """Splices two sequential audio clips across their mutual overlap window.

    Args:
        chunk_a: Preceding audio chunk [2, Na].
        chunk_b: Subsequent audio chunk [2, Nb].
        overlap_samples: Number of overlapping audio samples (O * 2000 at 48 kHz / 24 FPS).
        strategy: 'smartseam' | 'crossfade' | 'declick' | 'hard_cut'.

    Returns:
        Spliced audio tensor [2, Na + Nb - overlap_samples].
    """
    if chunk_a is None or chunk_a.shape[1] == 0:
        return chunk_b if chunk_b is not None else torch.zeros((2, 0), dtype=torch.float32)
    if chunk_b is None or chunk_b.shape[1] == 0:
        return chunk_a

    overlap_samples = max(0, min(overlap_samples, chunk_a.shape[1], chunk_b.shape[1]))
    if overlap_samples == 0 or strategy == "hard_cut":
        # Direct hard cut: drop exactly overlap_samples from chunk_b
        return torch.cat([chunk_a, chunk_b[:, overlap_samples:]], dim=1)

    if strategy == "declick":
        # Within the overlap span, apply a short 12ms (576 samples) equal-power ramp
        # at the transition point so total length remains exactly Na + Nb - overlap_samples.
        part_a = chunk_a[:, -overlap_samples:]
        part_b = chunk_b[:, :overlap_samples]
        fade_len = min(576, overlap_samples)
        if fade_len <= 1:
            return torch.cat([chunk_a, chunk_b[:, overlap_samples:]], dim=1)

        t = torch.linspace(0.0, math.pi / 2.0, fade_len, dtype=chunk_a.dtype, device=chunk_a.device)
        blended = torch.cos(t).unsqueeze(0) * part_a[:, :fade_len] + torch.sin(t).unsqueeze(0) * part_b[:, :fade_len]

        lead_a = chunk_a[:, :-overlap_samples] if chunk_a.shape[1] > overlap_samples else chunk_a[:, :0]
        tail_b = chunk_b[:, overlap_samples:] if chunk_b.shape[1] > overlap_samples else chunk_b[:, :0]
        overlap_stitched = torch.cat([blended, part_b[:, fade_len:]], dim=1)
        return torch.cat([lead_a, overlap_stitched, tail_b], dim=1)

    if strategy == "crossfade":
        # Full overlap equal-power blend across the entire overlap span
        lead_a = chunk_a[:, :-overlap_samples] if chunk_a.shape[1] > overlap_samples else chunk_a[:, :0]
        tail_b = chunk_b[:, overlap_samples:] if chunk_b.shape[1] > overlap_samples else chunk_b[:, :0]
        part_a = chunk_a[:, -overlap_samples:]
        part_b = chunk_b[:, :overlap_samples]

        t = torch.linspace(0.0, math.pi / 2.0, overlap_samples, dtype=chunk_a.dtype, device=chunk_a.device)
        blended = torch.cos(t).unsqueeze(0) * part_a + torch.sin(t).unsqueeze(0) * part_b
        return torch.cat([lead_a, blended, tail_b], dim=1)

    # Default: 'smartseam' (Adaptive Quietest-RMS Placement)
    # The overlap region is chunk_a[:, -overlap_samples:] and chunk_b[:, :overlap_samples]
    part_a = chunk_a[:, -overlap_samples:]
    part_b = chunk_b[:, :overlap_samples]

    # Energy envelope over 20ms sliding window (W = 960 samples at 48 kHz)
    w_size = min(960, overlap_samples)
    if w_size < 16 or overlap_samples < w_size:
        # Overlap window too small for windowed RMS search -> fallback to crossfade
        t = torch.linspace(0.0, math.pi / 2.0, overlap_samples, dtype=chunk_a.dtype, device=chunk_a.device)
        blended = torch.cos(t).unsqueeze(0) * part_a + torch.sin(t).unsqueeze(0) * part_b
        lead_a = chunk_a[:, :-overlap_samples]
        tail_b = chunk_b[:, overlap_samples:]
        return torch.cat([lead_a, blended, tail_b], dim=1)

    sq_energy = 0.5 * (part_a.pow(2).mean(dim=0) + part_b.pow(2).mean(dim=0))
    # 1D conv moving average
    kernel = torch.ones(1, 1, w_size, dtype=sq_energy.dtype, device=sq_energy.device) / float(w_size)
    env = F.conv1d(sq_energy.unsqueeze(0).unsqueeze(0), kernel).squeeze()

    # Quietest point s0
    min_idx = int(torch.argmin(env).item())
    s0 = min_idx + w_size // 2

    # Center a short crossfade of length fade_len <= w_size at s0
    fade_len = min(w_size, 960)
    half_fade = fade_len // 2
    f_start = max(0, s0 - half_fade)
    f_end = min(overlap_samples, f_start + fade_len)
    actual_fade = f_end - f_start

    t = torch.linspace(0.0, math.pi / 2.0, actual_fade, dtype=chunk_a.dtype, device=chunk_a.device)
    blended_slice = (
        torch.cos(t).unsqueeze(0) * part_a[:, f_start:f_end] +
        torch.sin(t).unsqueeze(0) * part_b[:, f_start:f_end]
    )

    # Reconstructed overlap zone:
    # [0 : f_start] from part_a, [f_start : f_end] blended, [f_end : overlap_samples] from part_b
    overlap_stitched = torch.cat([
        part_a[:, :f_start],
        blended_slice,
        part_b[:, f_end:],
    ], dim=1)

    lead_a = chunk_a[:, :-overlap_samples] if chunk_a.shape[1] > overlap_samples else chunk_a[:, :0]
    tail_b = chunk_b[:, overlap_samples:] if chunk_b.shape[1] > overlap_samples else chunk_b[:, :0]
    return torch.cat([lead_a, overlap_stitched, tail_b], dim=1)


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
        _LOG.info("[StitchEngine] Clamping audio duration (%d -> %d samples)", current_samples, target_samples)
        return audio_waveform[:, :target_samples]
    else:
        pad_amt = target_samples - current_samples
        _LOG.info("[StitchEngine] Padding audio duration with silence (%d -> %d samples)", current_samples, target_samples)
        return F.pad(audio_waveform, (0, pad_amt))


# -----------------------------------------------------------------------------
# High-Level Multi-Clip Assembly Orchestration
# -----------------------------------------------------------------------------

def assemble_multi_clip(
    plan: dict[str, Any],
    seam_audio: str = "smartseam",
    trim_head_overlap: bool = True,
    vae: Optional[Any] = None,
    audio_vae: Optional[Any] = None,
) -> Tuple[torch.Tensor, dict[str, Any]]:
    """Stitches all saved iteration clips into unified final_images and final_audio.

    Args:
        plan: Active render_plan dictionary containing canvas, iterations, and saved_artifacts.
        seam_audio: Audio stitching algorithm: 'smartseam', 'crossfade', 'declick', 'hard_cut'.
        trim_head_overlap: Whether to drop duplicate head overlap frames on continuation shots.
        vae: Video VAE for fallback latent decoding if media is missing.
        audio_vae: Audio VAE for fallback latent decoding.

    Returns:
        (final_images [Total_Frames, H, W, 3], final_audio {"waveform": [1, 2, N], "sample_rate": 48000})
    """
    canvas = plan.get("canvas", {})
    fps = float(canvas.get("fps", VIDEO_FPS))
    width = int(canvas.get("width", 1344))
    height = int(canvas.get("height", 768))

    saved_artifacts = list(plan.get("saved_artifacts", []))
    iterations = list(plan.get("iterations", []))

    # Sort artifacts by iteration index
    saved_artifacts.sort(key=lambda a: int(a.get("iteration", 0)))

    if not saved_artifacts:
        _LOG.warning("[StitchEngine] No saved artifacts found in render_plan. Returning blank sequence.")
        empty_images = torch.zeros((1, height, width, 3), dtype=torch.float32)
        empty_audio = {
            "waveform": torch.zeros((1, 2, AUDIO_SR), dtype=torch.float32),
            "sample_rate": AUDIO_SR,
        }
        return empty_images, empty_audio

    # Effective VAEs from socket or plan
    eff_vae = vae or plan.get("vae")
    eff_audio_vae = audio_vae or plan.get("audio_vae")

    video_chunks: List[torch.Tensor] = []
    audio_chunks: List[Tuple[Optional[torch.Tensor], int]] = []  # (waveform, overlap_lead_frames)

    for i, art in enumerate(saved_artifacts):
        iter_idx = int(art.get("iteration", i))

        # Determine overlap lead frames for this iteration
        overlap_frames = 0
        if i > 0 and trim_head_overlap:
            if iter_idx < len(iterations):
                overlap_frames = int(iterations[iter_idx].get("overlap_lead_frames", DEFAULT_OVERLAP))
            else:
                overlap_frames = int(art.get("overlap_lead_frames", DEFAULT_OVERLAP))
            if overlap_frames not in VALID_OVERLAPS:
                overlap_frames = DEFAULT_OVERLAP

        # 1. Load Video Frames
        raw_frames = load_iteration_frames(art, vae=eff_vae, target_fps=fps, fallback_h=height, fallback_w=width)
        trimmed_frames = trim_head_overlap_fn(raw_frames, overlap_frames) if i > 0 else raw_frames
        video_chunks.append(trimmed_frames)

        # 2. Load Audio Waveform
        raw_audio = load_iteration_audio(art, audio_vae=eff_audio_vae, target_sr=AUDIO_SR)
        audio_chunks.append((raw_audio, overlap_frames))

    # Concatenate Video
    final_images = torch.cat(video_chunks, dim=0)
    total_frames = final_images.shape[0]
    _LOG.info("[StitchEngine] Multi-clip video assembled: %d total frames (%s)", total_frames, final_images.shape)

    # Concatenate & Splice Audio
    accum_audio: Optional[torch.Tensor] = None
    for i, (chunk, overlap_frames) in enumerate(audio_chunks):
        if chunk is None:
            # Generate silence for missing audio chunk matching video frame length
            chunk_frames = video_chunks[i].shape[0] + (overlap_frames if i > 0 else 0)
            chunk_samples = int(round((float(chunk_frames) / fps) * float(AUDIO_SR)))
            chunk = torch.zeros((2, chunk_samples), dtype=torch.float32)

        if accum_audio is None:
            accum_audio = chunk
        else:
            overlap_samples = int(round((float(overlap_frames) / fps) * float(AUDIO_SR)))
            accum_audio = splice_audio_seam(
                chunk_a=accum_audio,
                chunk_b=chunk,
                overlap_samples=overlap_samples,
                strategy=seam_audio,
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
