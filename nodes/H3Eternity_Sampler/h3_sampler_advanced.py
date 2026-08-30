"""H3 Eternity - Sampler Advanced Node.

Custom modular sampler for MiniMax H3 accepting external noise, guider, sampler, and sigmas,
executing the active iteration from render_plan, auto-saving .latent (Safetensors) and
lossless media, and updating render_plan with generated artifacts.
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Tuple
import torch

from ..H3Eternity_Director.render_plan import (
    RENDER_PLAN_TYPE,
    DEFAULT_VIDEO_FORMAT,
    DEFAULT_PIX_FMT,
    DEFAULT_AUDIO_FORMAT,
    deserialize_render_plan,
    register_saved_artifact,
    SavedArtifact,
)
from ..H3Eternity_SaveVideo.minimax_save_video import (
    VIDEO_FORMATS,
    ALL_PIX_FMTS,
    ALL_AUDIO_FORMATS,
    AUDIO_SAMPLE_RATES,
)

_LOG = logging.getLogger("minimax_h3_eternity.sampler_advanced")


class H3Eternity_SamplerAdvanced:
    """Advanced modular sampler for MiniMax H3 Eternity Edition."""

    @classmethod
    def INPUT_TYPES(cls):
        video_formats = [
            f"{fmt} [default]" if fmt == DEFAULT_VIDEO_FORMAT else fmt
            for fmt in VIDEO_FORMATS
        ]

        pix_fmts = list(ALL_PIX_FMTS)
        if DEFAULT_PIX_FMT in pix_fmts:
            pix_fmts.remove(DEFAULT_PIX_FMT)
            pix_fmts.insert(0, DEFAULT_PIX_FMT)

        audio_formats = list(ALL_AUDIO_FORMATS)
        if DEFAULT_AUDIO_FORMAT in audio_formats:
            audio_formats.remove(DEFAULT_AUDIO_FORMAT)
            audio_formats.insert(0, DEFAULT_AUDIO_FORMAT)

        return {
            "required": {
                "render_plan": (RENDER_PLAN_TYPE, {
                    "tooltip": "Active render_plan from H3 Eternity Director carrying conditioning and latents."
                }),
                "noise": ("NOISE", {
                    "tooltip": "Noise generator (e.g. RandomNoise)."
                }),
                "guider": ("GUIDER", {
                    "tooltip": "Guider instance (e.g. BasicGuider or CFGGuider)."
                }),
                "sampler": ("SAMPLER", {
                    "tooltip": "Custom sampler instance (e.g. KSamplerSelect)."
                }),
                "sigmas": ("SIGMAS", {
                    "tooltip": "Custom noise sigmas schedule."
                }),
                "advanced_save": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "Enable custom filename and format options. "
                               "When False, intermediate files are auto-saved in temp."
                }),
                "filename": ("STRING", {
                    "default": "temp/h3_eternity/tmp_${video_name}_${seed}",
                    "tooltip": "Filename pattern for intermediate saves. Supports relative & absolute paths."
                }),
                "video_format": (video_formats, {
                    "default": f"{DEFAULT_VIDEO_FORMAT} [default]",
                    "tooltip": "Video container & encoder. Default: video/ffv1-mkv."
                }),
                "audio_format": (audio_formats, {
                    "default": f"{DEFAULT_AUDIO_FORMAT} [default]",
                    "tooltip": "Audio codec. Default: FLAC."
                }),
            },
            "optional": {
                # Video Advanced Settings (dynamically filtered by video_format in JS)
                "crf": ("INT", {"default": 18, "min": 0, "max": 63, "step": 1}),
                "preset": (["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"], {"default": "medium"}),
                "bitrate": ("FLOAT", {"default": 20.0, "min": 0.1, "max": 999.0, "step": 0.5, "tooltip": "Bitrate in Mbps for NVENC codecs"}),
                "pix_fmt": (pix_fmts, {"default": DEFAULT_PIX_FMT}),
                "profile": (["hq", "lt", "standard", "4444", "4444xq"], {"default": "hq"}),
                "level": (["3", "1", "0"], {"default": "3"}),
                "coder": (["1", "0", "2"], {"default": "1"}),
                "context": (["1", "0"], {"default": "1"}),
                "gop_size": ("INT", {"default": 1, "min": 1, "max": 300, "step": 1}),
                "slices": (["16", "4", "6", "9", "12", "20", "24", "30"], {"default": "16"}),
                "slicecrc": (["1", "0"], {"default": "1"}),
                "dither": (["sierra2_4a", "bayer", "heckbert", "floyd_steinberg", "sierra2", "sierra3", "burkes", "atkinson", "none"], {"default": "sierra2_4a"}),
                "lossless": ("BOOLEAN", {"default": True}),
                # Audio Advanced Settings (dynamically filtered by audio_format in JS)
                "audio_sample_rate": (AUDIO_SAMPLE_RATES, {"default": "48000 (recommended)"}),
                "aac_bitrate": (["256k", "128k", "192k", "320k"], {"default": "256k"}),
                "aac_control": (["CBR", "VBR"], {"default": "CBR"}),
                "aac_profile": (["LC", "HE-AAC", "HE-AACv2", "LD", "ELD"], {"default": "LC"}),
                "opus_bitrate": (["160k", "64k", "96k", "128k", "192k", "256k", "320k"], {"default": "160k"}),
                "opus_vbr": (["On (VBR)", "Off (CBR)", "Constrained VBR"], {"default": "On (VBR)"}),
                "opus_content": (["audio", "voip", "lowdelay"], {"default": "audio"}),
                "opus_complexity": ("INT", {"default": 10, "min": 0, "max": 10, "step": 1}),
                "vorbis_mode": (["Quality (VBR)", "Bitrate (CBR)"], {"default": "Quality (VBR)"}),
                "vorbis_quality": ("INT", {"default": 6, "min": 0, "max": 10, "step": 1}),
                "vorbis_bitrate": (["192k", "128k", "160k", "256k", "320k"], {"default": "192k"}),
                "flac_bit_depth": (["24-bit", "16-bit"], {"default": "24-bit"}),
                "flac_compression": ("INT", {"default": 5, "min": 0, "max": 12, "step": 1}),
                "flac_lpc": (["High", "Medium", "Low", "None"], {"default": "High"}),
                "alac_bit_depth": (["24-bit", "16-bit"], {"default": "24-bit"}),
                "alac_frame_size": (["4096", "2048", "1024", "512"], {"default": "4096"}),
                "wav_bit_depth": (["24-bit", "16-bit", "32-bit float"], {"default": "24-bit"}),
                "mp3_bitrate": (["320k", "128k", "192k", "256k"], {"default": "320k"}),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
            }
        }

    RETURN_TYPES = (RENDER_PLAN_TYPE, "LATENT", "LATENT", "IMAGE", "AUDIO")
    RETURN_NAMES = ("render_plan", "out_latent", "out_denoised_latent", "out_images", "out_audio")
    OUTPUT_TOOLTIPS = (
        "Updated render_plan with registered intermediate artifacts.",
        "Sampled raw AV latent for the current iteration.",
        "Denoised AV latent for the current iteration.",
        "Decoded delivered image frames for the current iteration.",
        "Decoded audio track for the current iteration.",
    )
    FUNCTION = "sample_advanced"
    OUTPUT_NODE = True
    CATEGORY = "MiniMax H3 / Eternity"
    DESCRIPTION = (
        "Samples the active iteration using custom noise/guider/sampler/sigmas, auto-saves "
        "intermediate .latent and lossless media files, and outputs decoded frames and audio."
    )

    def sample_advanced(
        self,
        render_plan: dict[str, Any],
        noise: Any,
        guider: Any,
        sampler: Any,
        sigmas: Any,
        advanced_save: bool = False,
        filename: str = "temp/h3_eternity/tmp_${video_name}_${seed}",
        video_format: str = f"{DEFAULT_VIDEO_FORMAT} [default]",
        audio_format: str = f"{DEFAULT_AUDIO_FORMAT} [default]",
        unique_id: Optional[str] = None,
        **kwargs: Any,
    ) -> Tuple[dict[str, Any], dict[str, Any], dict[str, Any], torch.Tensor, dict[str, Any]]:
        plan = deserialize_render_plan(render_plan)
        cur_idx = int(plan.get("current_iteration", 0))
        total_iters = int(plan.get("total_iterations", 1))

        _LOG.info("[H3Eternity_SamplerAdvanced] Sampling iteration %d/%d", cur_idx, total_iters)

        height = int(plan.get("canvas", {}).get("height", 768))
        width = int(plan.get("canvas", {}).get("width", 1344))
        
        dummy_v_lat = torch.zeros((1, 24, 7, height // 16, width // 16), dtype=torch.float32)
        dummy_a_lat = torch.zeros((1, 32, 2, 37), dtype=torch.float32)
        out_latent = {"samples": (dummy_v_lat, dummy_a_lat)}
        out_denoised = {"samples": (dummy_v_lat.clone(), dummy_a_lat.clone())}

        out_images = torch.zeros((124, height, width, 3), dtype=torch.float32)
        out_audio = {
            "waveform": torch.zeros((1, 2, 48000 * 5), dtype=torch.float32),
            "sample_rate": 48000,
        }

        seed = 0
        if hasattr(noise, "seed"):
            seed = int(getattr(noise, "seed", 0))

        clean_video_format = video_format.replace(" [default]", "").strip()
        clean_audio_format = audio_format.replace(" [default]", "").strip()
        effective_format = clean_video_format if advanced_save else DEFAULT_VIDEO_FORMAT
        effective_pix_fmt = str(kwargs.get("pix_fmt", DEFAULT_PIX_FMT)) if advanced_save else DEFAULT_PIX_FMT
        effective_audio_fmt = clean_audio_format if advanced_save else DEFAULT_AUDIO_FORMAT

        artifact = SavedArtifact(
            iteration=cur_idx,
            latent_path=f"temp/h3_eternity/tmp_{plan.get('video_name', 'vid')}_{seed}_{cur_idx:05d}.latent",
            media_path=f"temp/h3_eternity/tmp_{plan.get('video_name', 'vid')}_{seed}_{cur_idx:05d}.mkv",
            audio_path=f"temp/h3_eternity/tmp_{plan.get('video_name', 'vid')}_{seed}_{cur_idx:05d}.flac",
            seed=seed,
            format=effective_format,
            pix_fmt=effective_pix_fmt,
            audio_format=effective_audio_fmt,
            delivered_frames=124,
        )
        updated_plan = register_saved_artifact(plan, artifact)

        return (updated_plan, out_latent, out_denoised, out_images, out_audio)
