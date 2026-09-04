"""Shared sampling, VAE decoding, and disk persistence helpers for H3 Eternity Samplers."""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import torch

try:
    import safetensors.torch
    _HAVE_SAFETENSORS = True
except ImportError:
    _HAVE_SAFETENSORS = False

try:
    import folder_paths
except ImportError:
    class MockFolderPaths:
        @staticmethod
        def get_output_directory():
            return os.path.join(tempfile.gettempdir(), "comfy_output")
        @staticmethod
        def get_temp_directory():
            return os.path.join(tempfile.gettempdir(), "comfy_temp")
        @staticmethod
        def get_input_directory():
            return os.path.join(tempfile.gettempdir(), "comfy_input")
    folder_paths = MockFolderPaths()

from ..H3Eternity_Director.render_plan import (
    DEFAULT_VIDEO_FORMAT,
    DEFAULT_PIX_FMT,
    DEFAULT_AUDIO_FORMAT,
    SavedArtifact,
)
from ..H3Eternity_Director.minimax_core import (
    samplers as get_custom_samplers,
    audio_nodes as get_audio_nodes,
)
from ..H3Eternity_SaveVideo.minimax_save_video import (
    get_ffmpeg_path,
    build_video_ffmpeg_args,
    build_audio_ffmpeg_args,
    write_audio_to_wav,
    save_external_audio,
    tensor_to_bytes,
)

_LOG = logging.getLogger("minimax_h3_eternity.sampler_common")


def resolve_vae_references(
    node_vae: Optional[Any],
    node_audio_vae: Optional[Any],
    plan: dict[str, Any],
) -> Tuple[Optional[Any], Optional[Any]]:
    """Resolves VAE and Audio VAE from node socket or fallback to render_plan."""
    eff_vae = node_vae if node_vae is not None else plan.get("vae")
    eff_audio_vae = node_audio_vae if node_audio_vae is not None else plan.get("audio_vae")
    return eff_vae, eff_audio_vae


def decode_joint_latent(
    sampled_latent: dict[str, Any],
    vae: Optional[Any],
    audio_vae: Optional[Any],
    tiled: bool = False,
    target_sr: int = 48000,
    fallback_w: int = 1344,
    fallback_h: int = 768,
) -> Tuple[torch.Tensor, dict[str, Any]]:
    """Decodes joint AV latent into RGB image tensor and stereo audio dict.

    Guarantees isolation of video and audio streams so standard decoders
    do not crash on tuples or NestedTensors.
    """
    samples = sampled_latent.get("samples")
    zv = None
    za = None

    if isinstance(samples, (tuple, list)):
        zv = samples[0]
        if len(samples) > 1:
            za = samples[1]
    elif getattr(samples, "is_nested", False):
        parts = list(samples.unbind())
        zv = parts[0]
        if len(parts) > 1:
            za = parts[1]
    elif isinstance(samples, torch.Tensor):
        zv = samples
    elif isinstance(samples, dict):
        zv = samples.get("samples_video")
        za = samples.get("samples_audio")

    # 1. Video VAE Decoding
    if vae is not None and zv is not None:
        try:
            import nodes as comfy_nodes
            if tiled:
                try:
                    images = comfy_nodes.VAEDecodeTiled().decode(
                        vae, {"samples": zv}, tile_size=512, overlap=64,
                        temporal_size=32, temporal_overlap=8
                    )[0]
                except Exception as tiled_err:
                    _LOG.warning("[Sampler] Tiled VAE decode failed (%s) - falling back to full decode", tiled_err)
                    images = comfy_nodes.VAEDecode().decode(vae, {"samples": zv})[0]
            else:
                images = comfy_nodes.VAEDecode().decode(vae, {"samples": zv})[0]
            out_images = images.to(torch.float32).cpu()
        except Exception as e:
            _LOG.error("[Sampler] Video VAE decode error: %s", e)
            num_frames = 124
            if zv.ndim >= 3:
                num_frames = max(1, (zv.shape[2] - 2) // 5 * 17 + 5)
            out_images = torch.zeros((num_frames, fallback_h, fallback_w, 3), dtype=torch.float32)
    else:
        num_frames = 124
        if zv is not None and zv.ndim >= 3:
            num_frames = max(1, (zv.shape[2] - 2) // 5 * 17 + 5)
        _LOG.info("[Sampler] No Video VAE provided; emitting placeholder image tensor (%d frames)", num_frames)
        out_images = torch.zeros((num_frames, fallback_h, fallback_w, 3), dtype=torch.float32)

    # 2. Audio VAE Decoding
    if audio_vae is not None and za is not None:
        try:
            anodes = get_audio_nodes()
            raw_audio = anodes.VAEDecodeAudio.execute(vae=audio_vae, samples={"samples": za})
            args = getattr(raw_audio, "args", None) or getattr(raw_audio, "result", None) or raw_audio
            audio_dict = args[0] if isinstance(args, (tuple, list)) else args

            waveform = audio_dict.get("waveform")
            sr = int(audio_dict.get("sample_rate", target_sr))
            if isinstance(waveform, torch.Tensor):
                waveform = waveform.detach().cpu()
                if waveform.ndim == 3:
                    waveform = waveform[0]
                if waveform.ndim == 1:
                    waveform = waveform.unsqueeze(0)
                if waveform.shape[0] == 1:
                    waveform = waveform.repeat(2, 1)
                elif waveform.shape[0] > 2:
                    waveform = waveform[:2]

                if sr != target_sr:
                    try:
                        import torchaudio.functional as AF
                        waveform = AF.resample(waveform, sr, target_sr)
                    except Exception:
                        pass
                out_audio = {"waveform": waveform.unsqueeze(0).to(torch.float32), "sample_rate": target_sr}
            else:
                out_audio = {"waveform": torch.zeros((1, 2, target_sr * 5), dtype=torch.float32), "sample_rate": target_sr}
        except Exception as e:
            _LOG.error("[Sampler] Audio VAE decode error: %s", e)
            out_audio = {"waveform": torch.zeros((1, 2, target_sr * 5), dtype=torch.float32), "sample_rate": target_sr}
    else:
        out_audio = {"waveform": torch.zeros((1, 2, target_sr * 5), dtype=torch.float32), "sample_rate": target_sr}

    return out_images, out_audio


def execute_sampling_pass(
    model: Any,
    conditioning: list,
    latent_image: dict[str, Any],
    seed: int,
    steps: int,
    cfg: float,
    sampler_name: str,
    scheduler: str,
    denoise: float,
) -> Tuple[dict[str, Any], dict[str, Any]]:
    """Executes diffusion sampling using ComfyUI SamplerCustomAdvanced."""
    import comfy.samplers
    sm = get_custom_samplers()

    # 1. Guider
    if abs(float(cfg) - 1.0) < 1e-4:
        guider = sm.BasicGuider.execute(model=model, conditioning=conditioning)[0]
    else:
        # Build empty negative conditioning for CFG
        empty_cond = [[torch.zeros_like(conditioning[0][0]), {}]]
        guider = sm.CFGGuider.execute(
            model=model, positive=conditioning, negative=empty_cond, cfg=float(cfg)
        )[0]

    # 2. Noise & Sampler
    noise = sm.Noise_RandomNoise(int(seed))
    sampler_obj = comfy.samplers.KSampler(sampler_name)
    sigmas = comfy.samplers.calculate_sigmas(
        model.get_model_object("model_sampling"), scheduler, int(steps), denoise=float(denoise)
    )

    # 3. Denoising Call
    out = sm.SamplerCustomAdvanced.execute(
        noise=noise, guider=guider, sampler=sampler_obj, sigmas=sigmas, latent_image=latent_image
    )
    sampled = out[0] if isinstance(out, (tuple, list)) else out
    denoised = out[1] if isinstance(out, (tuple, list)) and len(out) > 1 else sampled

    return sampled, denoised


def save_intermediate_artifacts(
    plan: dict[str, Any],
    seed: int,
    cur_idx: int,
    zv: Optional[torch.Tensor],
    za: Optional[torch.Tensor],
    out_images: torch.Tensor,
    out_audio: dict[str, Any],
    advanced_save: bool = False,
    filename_pattern: str = "temp/h3_eternity/tmp_${video_name}_${seed}",
    video_format: str = f"{DEFAULT_VIDEO_FORMAT} [default]",
    audio_format: str = f"{DEFAULT_AUDIO_FORMAT} [default]",
    fps: float = 24.0,
    **kwargs: Any,
) -> SavedArtifact:
    """Saves uncompressed .latent Safetensors and lossless media for Path A & B continuation."""
    clean_video_format = video_format.replace(" [default]", "").strip()
    clean_audio_format = audio_format.replace(" [default]", "").strip()

    effective_format = clean_video_format if advanced_save else DEFAULT_VIDEO_FORMAT
    effective_pix_fmt = str(kwargs.get("pix_fmt", DEFAULT_PIX_FMT)) if advanced_save else DEFAULT_PIX_FMT
    effective_audio_fmt = clean_audio_format if advanced_save else DEFAULT_AUDIO_FORMAT

    video_name = plan.get("video_name", "vid")
    temp_base = (folder_paths.get_temp_directory() if folder_paths else None) or tempfile.gettempdir()
    temp_dir = os.path.join(temp_base, "h3_eternity")
    os.makedirs(temp_dir, exist_ok=True)

    # Resolve Base Filename
    if not advanced_save:
        base_name = f"tmp_{video_name}_{seed}_{cur_idx:05d}"
        target_dir = temp_dir
    else:
        # Template expansion
        resolved = filename_pattern
        resolved = resolved.replace("${video_name}", str(video_name))
        resolved = resolved.replace("${seed}", str(seed))
        resolved = resolved.replace("${index}", f"{cur_idx:05d}")
        resolved = resolved.replace("${iteration}", f"{cur_idx:05d}")

        target_dir = os.path.dirname(resolved)
        if not target_dir:
            target_dir = temp_dir
        elif not os.path.isabs(target_dir):
            out_base = (folder_paths.get_output_directory() if folder_paths else None) or tempfile.gettempdir()
            target_dir = os.path.join(out_base, target_dir)
        os.makedirs(target_dir, exist_ok=True)

        base_raw = os.path.basename(resolved) or f"tmp_{video_name}_{seed}"
        if not re.search(r"_\d{4,5}$", base_raw):
            base_name = f"{base_raw}_{cur_idx:05d}"
        else:
            base_name = base_raw

    # 1. Path B: Uncompressed Latent Safetensors Persistence
    latent_path = os.path.join(target_dir, f"{base_name}.latent")
    latent_tensors: Dict[str, torch.Tensor] = {}
    if zv is not None:
        latent_tensors["samples_video"] = zv.detach().contiguous().to(torch.bfloat16).cpu()
    if za is not None:
        latent_tensors["samples_audio"] = za.detach().contiguous().to(torch.bfloat16).cpu()

    if latent_tensors:
        if _HAVE_SAFETENSORS:
            try:
                safetensors.torch.save_file(latent_tensors, latent_path)
            except Exception as e:
                _LOG.warning("[Sampler] Safetensors save failed (%s), falling back to torch.save", e)
                torch.save(latent_tensors, latent_path)
        else:
            torch.save(latent_tensors, latent_path)

    # 2. Path A: Media (Video / Sequence) & Audio Persistence
    num_frames = out_images.shape[0] if getattr(out_images, "ndim", 0) == 4 else 124
    height = out_images.shape[1] if getattr(out_images, "ndim", 0) == 4 else 768
    width = out_images.shape[2] if getattr(out_images, "ndim", 0) == 4 else 1344

    ffmpeg_bin = get_ffmpeg_path()
    media_path = ""
    audio_path = os.path.join(target_dir, f"{base_name}.flac")

    # Temporary audio WAV for muxing
    temp_wav = os.path.join(temp_dir, f"tmp_audio_{base_name}.wav")
    has_audio = False
    try:
        write_audio_to_wav(out_audio, temp_wav, target_sr=48000)
        has_audio = os.path.exists(temp_wav) and os.path.getsize(temp_wav) > 44
    except Exception as e:
        _LOG.warning("[Sampler] Failed to write temporary WAV for audio: %s", e)

    # Encode Audio to FLAC
    if has_audio and ffmpeg_bin:
        try:
            save_external_audio(temp_wav, audio_path, "FLAC", kwargs, ffmpeg_bin, sample_rate=48000)
        except Exception as e:
            _LOG.warning("[Sampler] Failed to encode standalone FLAC audio: %s", e)

    # Encode Video / MKV
    if effective_format == "video/ffv1-mkv" or not advanced_save:
        media_path = os.path.join(target_dir, f"{base_name}.mkv")
        if ffmpeg_bin and out_images is not None and getattr(out_images, "ndim", 0) == 4:
            cmd = [
                ffmpeg_bin, "-y",
                "-f", "rawvideo",
                "-pix_fmt", "rgb24",
                "-s", f"{width}x{height}",
                "-r", str(fps),
                "-i", "-",
            ]
            if has_audio:
                cmd += ["-i", temp_wav]

            # Lossless FFV1 BGRA parameters
            level = str(kwargs.get("level", "3"))
            coder = str(kwargs.get("coder", "1"))
            context = str(kwargs.get("context", "1"))
            gop = str(kwargs.get("gop_size", 1))
            slices = str(kwargs.get("slices", "16"))
            slicecrc = str(kwargs.get("slicecrc", "1"))
            pix_fmt = str(kwargs.get("pix_fmt", "bgra"))

            cmd += [
                "-c:v", "ffv1", "-level", level, "-coder", coder, "-context", context,
                "-g", gop, "-slices", slices, "-slicecrc", slicecrc, "-pix_fmt", pix_fmt,
            ]
            if has_audio:
                cmd += ["-c:a", "flac", "-sample_fmt", "s32", "-ar", "48000", "-ac", "2", "-shortest"]
            else:
                cmd += ["-an"]

            cmd.append(media_path)

            try:
                proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                for i in range(num_frames):
                    proc.stdin.write(tensor_to_bytes(out_images[i]))
                proc.stdin.close()
                proc.communicate()
            except Exception as e:
                _LOG.error("[Sampler] FFmpeg lossless MKV encoding error: %s", e)
    else:
        # Custom format via minimax_save_video helpers
        ext = "mp4"
        if "webm" in effective_format:
            ext = "webm"
        elif "ProRes" in effective_format:
            ext = "mov"
        elif "mkv" in effective_format:
            ext = "mkv"
        media_path = os.path.join(target_dir, f"{base_name}.{ext}")

        if ffmpeg_bin and out_images is not None and getattr(out_images, "ndim", 0) == 4:
            video_args, _ = build_video_ffmpeg_args(effective_format, kwargs)
            audio_args = build_audio_ffmpeg_args(effective_audio_fmt, kwargs) if has_audio else ["-an"]
            cmd = [
                ffmpeg_bin, "-y",
                "-f", "rawvideo",
                "-pix_fmt", "rgb24",
                "-s", f"{width}x{height}",
                "-r", str(fps),
                "-i", "-",
            ]
            if has_audio:
                cmd += ["-i", temp_wav]
            cmd += video_args
            if has_audio:
                cmd += audio_args + ["-shortest"]
            cmd.append(media_path)

            try:
                proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                for i in range(num_frames):
                    proc.stdin.write(tensor_to_bytes(out_images[i]))
                proc.stdin.close()
                proc.communicate()
            except Exception as e:
                _LOG.error("[Sampler] FFmpeg custom encoding error: %s", e)

    # Clean up temp WAV
    if os.path.exists(temp_wav):
        try:
            os.remove(temp_wav)
        except Exception:
            pass

    return SavedArtifact(
        iteration=cur_idx,
        latent_path=latent_path,
        media_path=media_path,
        audio_path=audio_path,
        seed=seed,
        format=effective_format,
        pix_fmt=effective_pix_fmt,
        audio_format=effective_audio_fmt,
        delivered_frames=num_frames,
    )
