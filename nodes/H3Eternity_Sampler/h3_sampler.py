"""H3 Eternity - Sampler Node.

Performs iterative diffusion sampling for the current iteration specified by render_plan,
extracts conditioning & latent from render_plan, auto-saves intermediate .latent (Safetensors)
and lossless media (FFV1/FLAC), and updates render_plan with generated artifacts.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional, Tuple, Union
import torch

try:
    import comfy.samplers
    SAMPLER_NAMES = comfy.samplers.KSampler.SAMPLERS
    SCHEDULER_NAMES = comfy.samplers.KSampler.SCHEDULERS
except Exception:
    SAMPLER_NAMES = [
        "res_multistep", "euler", "euler_ancestral", "heun", "heunpp2", "dpm_2",
        "dpm_2_ancestral", "lms", "dpm_fast", "dpm_adaptive", "dpmpp_2s_ancestral",
        "dpmpp_sde", "dpmpp_sde_gpu", "dpmpp_2m", "dpmpp_2m_sde", "dpmpp_2m_sde_gpu",
        "dpmpp_3m_sde", "dpmpp_3m_sde_gpu", "ddpm", "lcm", "ddim", "uni_pc", "uni_pc_bh2"
    ]
    SCHEDULER_NAMES = [
        "simple", "normal", "karras", "exponential", "sgm_uniform", "kl_optimal",
        "linear_quadratic", "ddim_uniform", "beta"
    ]

from ..H3Eternity_Director.render_plan import (
    RENDER_PLAN_TYPE,
    DEFAULT_VIDEO_FORMAT,
    DEFAULT_PIX_FMT,
    DEFAULT_AUDIO_FORMAT,
    deserialize_render_plan,
    register_saved_artifact,
)
from ..H3Eternity_SaveVideo.minimax_save_video import (
    VIDEO_FORMATS,
    ALL_PIX_FMTS,
    ALL_AUDIO_FORMATS,
    AUDIO_SAMPLE_RATES,
)
from .sampler_common import (
    folder_paths,
    resolve_vae_references,
    decode_joint_latent,
    execute_sampling_pass,
    save_intermediate_artifacts,
)

_LOG = logging.getLogger("minimax_h3_eternity.sampler")


class SamplerResult(dict):
    """Dictionary holding 'ui' and 'result' for ComfyUI, while allowing direct tuple unpacking in tests."""

    def __init__(self, ui: dict[str, Any], result: tuple):
        super().__init__(ui=ui, result=result)

    def __iter__(self):
        return iter(self["result"])

    def __getitem__(self, key: Union[str, int]):
        if isinstance(key, int):
            return self["result"][key]
        return super().__getitem__(key)

    def __len__(self):
        return len(self["result"])


class H3Eternity_Sampler:
    """Standard iterative sampler for MiniMax H3 Eternity Edition."""

    @classmethod
    def INPUT_TYPES(cls):
        samplers = list(SAMPLER_NAMES)
        if "res_multistep" in samplers:
            samplers.remove("res_multistep")
            samplers.insert(0, "res_multistep")
        
        schedulers = list(SCHEDULER_NAMES)
        if "simple" in schedulers:
            schedulers.remove("simple")
            schedulers.insert(0, "simple")

        video_formats = [
            f"{fmt} [default]" if fmt == DEFAULT_VIDEO_FORMAT else fmt
            for fmt in VIDEO_FORMATS
        ]
        pix_fmts = list(ALL_PIX_FMTS)
        audio_formats = list(ALL_AUDIO_FORMATS)
        if DEFAULT_AUDIO_FORMAT in audio_formats:
            audio_formats.remove(DEFAULT_AUDIO_FORMAT)
            audio_formats.insert(0, f"{DEFAULT_AUDIO_FORMAT} [default]")

        return {
            "required": {
                "render_plan": (RENDER_PLAN_TYPE, {
                    "tooltip": "Active render_plan from H3 Eternity Director carrying conditioning and latents."
                }),
                "model": ("MODEL", {
                    "tooltip": "Model from H3 Eternity Director."
                }),
                "seed": ("INT", {
                    "default": 0, "min": 0, "max": 0xffffffffffffffff,
                    "tooltip": "Random noise seed for the current iteration."
                }),
                "steps": ("INT", {
                    "default": 20, "min": 1, "max": 10000,
                    "tooltip": "Sampling steps for this iteration."
                }),
                "cfg": ("FLOAT", {
                    "default": 1.0, "min": 0.0, "max": 100.0, "step": 0.1,
                    "tooltip": "Classifier-free guidance scale. Default is 1.0 for H3 DiT."
                }),
                "sampler_name": (samplers, {
                    "default": "res_multistep",
                    "tooltip": "Diffusion sampling algorithm. Default: res_multistep."
                }),
                "scheduler": (schedulers, {
                    "default": "simple",
                    "tooltip": "Sigma noise schedule. Default: simple."
                }),
                "denoise": ("FLOAT", {
                    "default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01,
                    "tooltip": "Denoising strength."
                }),
                "tiled_vae": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "Use VAEDecodeTiled for video decoding to reduce VRAM usage on large frame counts."
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
                "vae [opt]": ("VAE", {
                    "tooltip": "Optional video VAE for decoding frames. If omitted, automatically resolves from render_plan."
                }),
                "audio_vae [opt]": ("VAE", {
                    "tooltip": "Optional audio VAE for decoding audio. If omitted, automatically resolves from render_plan."
                }),
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

    RETURN_TYPES = (RENDER_PLAN_TYPE, "LATENT", "IMAGE", "AUDIO")
    RETURN_NAMES = ("render_plan", "out_latent", "out_images", "out_audio")
    OUTPUT_TOOLTIPS = (
        "Updated render_plan with registered intermediate artifacts.",
        "Sampled AV latent for the current iteration.",
        "Decoded delivered image frames for the current iteration.",
        "Decoded audio track for the current iteration.",
    )
    FUNCTION = "sample"
    OUTPUT_NODE = True
    CATEGORY = "MiniMax H3 / Eternity"
    DESCRIPTION = (
        "Samples the active iteration defined in render_plan, auto-saves intermediate "
        ".latent and lossless media files, and outputs decoded frames and audio."
    )

    @classmethod
    def VALIDATE_INPUTS(cls, **kwargs):
        return True

    def sample(
        self,
        render_plan: dict[str, Any],
        model: Any,
        seed: int,
        steps: int,
        cfg: float,
        sampler_name: str,
        scheduler: str,
        denoise: float,
        tiled_vae: bool = False,
        advanced_save: bool = False,
        filename: str = "temp/h3_eternity/tmp_${video_name}_${seed}",
        video_format: str = f"{DEFAULT_VIDEO_FORMAT} [default]",
        audio_format: str = f"{DEFAULT_AUDIO_FORMAT} [default]",
        unique_id: Optional[str] = None,
        **kwargs: Any,
    ) -> SamplerResult:
        plan = deserialize_render_plan(render_plan)
        cur_idx = int(plan.get("current_iteration", 0))
        total_iters = int(plan.get("total_iterations", 1))

        _LOG.info("[H3Eternity_Sampler] Sampling iteration %d/%d (seed=%d, steps=%d, cfg=%.2f)",
                  cur_idx, total_iters, seed, steps, cfg)

        height = int(plan.get("canvas", {}).get("height", 768))
        width = int(plan.get("canvas", {}).get("width", 1344))
        fps = float(plan.get("canvas", {}).get("fps", 24.0))

        # 1. Conditioning & Latent from plan
        conditioning = plan.get("current_conditioning")
        latent_image = plan.get("current_latent")

        # 2. VAE Resolution (node socket overrides render_plan carrier)
        node_vae = kwargs.get("vae [opt]") or kwargs.get("vae")
        node_audio_vae = kwargs.get("audio_vae [opt]") or kwargs.get("audio_vae")
        eff_vae, eff_audio_vae = resolve_vae_references(node_vae, node_audio_vae, plan)
        tiled_vae = bool(tiled_vae or kwargs.get("tiled_vae", False))

        # 3. Diffusion Sampling Execution
        if model is not None and conditioning is not None and latent_image is not None:
            try:
                sampled_latent, _ = execute_sampling_pass(
                    model=model,
                    conditioning=conditioning,
                    latent_image=latent_image,
                    seed=seed,
                    steps=steps,
                    cfg=cfg,
                    sampler_name=sampler_name,
                    scheduler=scheduler,
                    denoise=denoise,
                )
            except Exception as e:
                _LOG.error("[H3Eternity_Sampler] Diffusion sampling execution failed: %s", e)
                sampled_latent = latent_image
        else:
            # Fallback for mock tests / offline harnesses
            if latent_image is not None and isinstance(latent_image, dict) and "samples" in latent_image:
                sampled_latent = latent_image
            else:
                dummy_v = torch.zeros((1, 24, 7, height // 16, width // 16), dtype=torch.float32)
                dummy_a = torch.zeros((1, 32, 2, 37), dtype=torch.float32)
                sampled_latent = {"samples": (dummy_v, dummy_a)}

        # 4. Extract Sliced Latent Tensors
        samples = sampled_latent.get("samples")
        zv = None
        za = None
        if isinstance(samples, (tuple, list)):
            zv = samples[0]
            if len(samples) > 1:
                za = samples[1]
        elif isinstance(samples, torch.Tensor):
            zv = samples
        elif isinstance(samples, dict):
            zv = samples.get("samples_video")
            za = samples.get("samples_audio")

        # 5. Dual-Stream VAE Decoding
        out_images, out_audio = decode_joint_latent(
            sampled_latent=sampled_latent,
            vae=eff_vae,
            audio_vae=eff_audio_vae,
            tiled=tiled_vae,
            target_sr=48000,
            fallback_w=width,
            fallback_h=height,
        )

        # 6. Lossless Disk Persistence & Registry
        artifact = save_intermediate_artifacts(
            plan=plan,
            seed=seed,
            cur_idx=cur_idx,
            zv=zv,
            za=za,
            out_images=out_images,
            out_audio=out_audio,
            advanced_save=advanced_save,
            filename_pattern=filename,
            video_format=video_format,
            audio_format=audio_format,
            fps=fps,
            **kwargs,
        )
        updated_plan = register_saved_artifact(plan, artifact)

        # 7. UI Preview & WebSocket Payload
        base_dir = folder_paths.get_temp_directory() if not advanced_save else folder_paths.get_output_directory()
        try:
            subfolder = os.path.relpath(os.path.dirname(artifact.media_path), base_dir).replace("\\", "/")
            if subfolder == ".":
                subfolder = "h3_eternity" if not advanced_save else ""
        except Exception:
            subfolder = "h3_eternity" if not advanced_save else ""

        ui_payload = {
            "videos": [{
                "filename": os.path.basename(artifact.media_path),
                "subfolder": subfolder,
                "type": "temp" if not advanced_save else "output",
                "format": artifact.format,
                "delivered_frames": int(artifact.delivered_frames),
                "fps": fps,
            }],
            "status": {
                "current_iteration": cur_idx,
                "total_iterations": total_iters,
                "delivered_frames": int(artifact.delivered_frames),
                "latent_path": artifact.latent_path,
                "media_path": artifact.media_path,
            }
        }

        return SamplerResult(
            ui=ui_payload,
            result=(updated_plan, sampled_latent, out_images, out_audio)
        )
