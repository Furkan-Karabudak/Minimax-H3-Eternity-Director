"""MiniMax H3 Reference to Video with Latent Inputs (Test).

Allows passing direct latent references alongside (or instead of) pixel-space
references to prevent quality degradation caused by repeated VAE encode/decode cycles.
"""

import math
import torch

import nodes
import comfy.model_management
import comfy.nested_tensor
import comfy.utils
import node_helpers
from comfy_api.latest import io

try:
    from comfy_extras.nodes_minimax_h3 import (
        CANVAS_MULTIPLE,
        BASE_SHORT_EDGE,
        MAX_PIXELS,
        REF_IMAGE_SHORT_EDGE,
        FPS,
        AUDIO_LATENT_FPS,
        align_frame_count,
        video_latent_t,
        temporal_shape,
        adapt_canvas,
        _resize,
        _empty_av_latent,
    )
except ImportError:
    try:
        from .nodes_minimax_h3 import (
            CANVAS_MULTIPLE,
            BASE_SHORT_EDGE,
            MAX_PIXELS,
            REF_IMAGE_SHORT_EDGE,
            FPS,
            AUDIO_LATENT_FPS,
            align_frame_count,
            video_latent_t,
            temporal_shape,
            adapt_canvas,
            _resize,
            _empty_av_latent,
        )
    except ImportError:
        from nodes_minimax_h3 import (
            CANVAS_MULTIPLE,
            BASE_SHORT_EDGE,
            MAX_PIXELS,
            REF_IMAGE_SHORT_EDGE,
            FPS,
            AUDIO_LATENT_FPS,
            align_frame_count,
            video_latent_t,
            temporal_shape,
            adapt_canvas,
            _resize,
            _empty_av_latent,
        )


def _collect_indexed_dict(d):
    """Extracts a dict mapping int index (0, 1, 2...) -> value from an autogrow dictionary,
    regardless of whether keys are prefixed like 'ref_video_0', 'ref_videos.ref_video_0',
    or 'ref_video_latents.ref_video_latent_0'.
    """
    res = {}
    if not d:
        return res
    for k, v in d.items():
        if v is None:
            continue
        suffix = k.rsplit("_", 1)[-1]
        try:
            idx = int(suffix)
            res[idx] = v
        except ValueError:
            pass
    return res


def _normalize_image_latent_4d(lat):
    """Ensure image latent tensor is 4D: [B, 24, H/16, W/16].

    MiniMax H3 treats 4D tensors as 2D spatial image conditioning.
    """
    if lat is None:
        return None
    if isinstance(lat, dict):
        lat = lat.get("samples", lat)
    if isinstance(lat, comfy.nested_tensor.NestedTensor) or hasattr(lat, "tensors") or isinstance(lat, (tuple, list)):
        lat = lat[0]

    if not isinstance(lat, torch.Tensor):
        return None

    if lat.ndim == 3:  # [C, H, W]
        lat = lat.unsqueeze(0)
    elif lat.ndim == 5:  # [B, C, T, H, W]
        lat = lat[:, :, 0, :, :]  # Squeeze temporal dimension for single image
    elif lat.ndim != 4:
        raise ValueError(f"Expected 3D, 4D, or 5D image latent, got shape {lat.shape}")

    return lat


def _normalize_video_latent_5d(lat):
    """Ensure video latent tensor is 5D: [B, 24, T, H/16, W/16].

    MiniMax H3 treats 5D tensors as 3D spatio-temporal video conditioning.
    """
    if lat is None:
        return None
    if isinstance(lat, dict):
        lat = lat.get("samples", lat)
    if isinstance(lat, comfy.nested_tensor.NestedTensor) or hasattr(lat, "tensors") or isinstance(lat, (tuple, list)):
        lat = lat[0]

    if not isinstance(lat, torch.Tensor):
        return None

    if lat.ndim == 3:  # [C, H, W]
        lat = lat.unsqueeze(0).unsqueeze(2)
    elif lat.ndim == 4:  # [B, C, H, W]
        lat = lat.unsqueeze(2)
    elif lat.ndim != 5:
        raise ValueError(f"Expected 3D, 4D, or 5D video latent, got shape {lat.shape}")

    return lat


def _normalize_audio_latent_4d(lat):
    """Ensure audio latent tensor is 4D: [B, 32, 2, T_audio]."""
    if lat is None:
        return None
    if isinstance(lat, dict):
        lat = lat.get("samples", lat)
    if isinstance(lat, comfy.nested_tensor.NestedTensor) or hasattr(lat, "tensors") or isinstance(lat, (tuple, list)):
        lat = lat[1] if len(lat) > 1 else lat[0]

    if not isinstance(lat, torch.Tensor):
        return None

    if lat.ndim == 3:
        if lat.shape[0] == 32 and lat.shape[1] == 2:
            lat = lat.unsqueeze(0)
        elif lat.shape[1] == 32:
            lat = lat.unsqueeze(2).repeat(1, 1, 2, 1)
        else:
            lat = lat.unsqueeze(0)
    elif lat.ndim == 2:
        lat = lat.unsqueeze(0).unsqueeze(2).repeat(1, 1, 2, 1)
    elif lat.ndim != 4:
        raise ValueError(f"Expected 2D, 3D, or 4D audio latent, got shape {lat.shape}")

    return lat


class MiniMaxH3ReferenceToVideo_test(io.ComfyNode):
    """ref2va (Test): prompt + reference images / videos / audio (pixel and/or latent).

    References enter the presentation in fixed order: images, then videos,
    then standalone audio. If latent inputs are connected, they are directly
    passed to the DiT conditioning, bypassing VAE encoding for zero quality loss.
    """

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3ReferenceToVideo_test",
            description="<Picture i> / <Video k> / <Audio j> reference conditioning with direct Latent & Pixel inputs for MiniMax H3.",
            display_name="MiniMax H3 Reference to Video test - Eternity Edition",
            category="model/conditioning/minimax",
            inputs=[
                io.Clip.Input("clip"),
                io.Vae.Input("vae", optional=True, tooltip="Optional VAE for fallback pixel-to-latent encoding when latent inputs are not provided."),
                io.Vae.Input("audio_vae", optional=True, tooltip="Optional Audio VAE for fallback audio encoding."),
                io.String.Input("prompt", multiline=True, dynamic_prompts=True),
                io.Int.Input("width", default=1344, min=32, max=nodes.MAX_RESOLUTION, step=32),
                io.Int.Input("height", default=768, min=32, max=nodes.MAX_RESOLUTION, step=32),
                io.Int.Input("length", default=124, min=5, max=3600, step=17, tooltip="Frame count at 24 fps (124 = ~5s, trained range is ~124-362)"),
                io.Combo.Input("ref_image_size", options=["match", "max"], default="match",
                    tooltip="Reference image sizing. 'match' scales each ref (down only, keeping aspect) to generation pixel area; 'max' uses 2048px short edge."),
                # Pixel-space Autogrows
                io.Autogrow.Input("ref_images", optional=True,
                    template=io.Autogrow.TemplatePrefix(
                        input=io.Image.Input("ref_image", tooltip="Reference image (pixel space, for Qwen3-VL and fallback encoding)"),
                        prefix="ref_image_", min=0, max=9)),
                io.Autogrow.Input("ref_videos", optional=True,
                    template=io.Autogrow.TemplatePrefix(
                        input=io.Image.Input("ref_video", tooltip="Reference video frames (pixel space, for Qwen3-VL and fallback encoding)"),
                        prefix="ref_video_", min=0, max=3)),
                io.Autogrow.Input("ref_video_audios", optional=True,
                    template=io.Autogrow.TemplatePrefix(
                        input=io.Audio.Input("ref_video_audio", tooltip="Soundtrack of the same-numbered reference video (pixel audio)"),
                        prefix="ref_video_audio_", min=0, max=3)),
                io.Autogrow.Input("ref_audios", optional=True,
                    template=io.Autogrow.TemplatePrefix(
                        input=io.Audio.Input("ref_audio", tooltip="Standalone reference audio (pixel audio)"),
                        prefix="ref_audio_", min=0, max=3)),
                # Latent-space Autogrows
                io.Autogrow.Input("ref_image_latents", optional=True,
                    template=io.Autogrow.TemplatePrefix(
                        input=io.Latent.Input("ref_image_latent", tooltip="Direct latent reference for the same-numbered image (bypasses VAE encode)"),
                        prefix="ref_image_latent_", min=0, max=9)),
                io.Autogrow.Input("ref_video_latents", optional=True,
                    template=io.Autogrow.TemplatePrefix(
                        input=io.Latent.Input("ref_video_latent", tooltip="Direct latent reference for the same-numbered video (bypasses VAE encode)"),
                        prefix="ref_video_latent_", min=0, max=3)),
                io.Autogrow.Input("ref_video_audio_latents", optional=True,
                    template=io.Autogrow.TemplatePrefix(
                        input=io.Latent.Input("ref_video_audio_latent", tooltip="Direct audio latent reference for the video soundtrack"),
                        prefix="ref_video_audio_latent_", min=0, max=3)),
                io.Autogrow.Input("ref_audio_latents", optional=True,
                    template=io.Autogrow.TemplatePrefix(
                        input=io.Latent.Input("ref_audio_latent", tooltip="Direct audio latent reference for standalone audio"),
                        prefix="ref_audio_latent_", min=0, max=3)),
            ],
            outputs=[io.Conditioning.Output(display_name="positive"), io.Latent.Output()],
        )

    @staticmethod
    def _encode_ref_audio(audio_vae, audio):
        if audio_vae is None:
            raise ValueError("Audio VAE is required when pixel reference audio is provided without a direct audio latent.")
        import torchaudio
        waveform = audio["waveform"]  # [B, C, L]
        sr = audio["sample_rate"]
        vae_sr = getattr(audio_vae, "audio_sample_rate", 32000)
        if sr != vae_sr:
            waveform = torchaudio.functional.resample(waveform, sr, vae_sr)
        z = audio_vae.encode(waveform[:1].movedim(1, -1))  # [1, 32, 2, T]
        return z, z.shape[-1]

    @classmethod
    def execute(cls, clip, vae, audio_vae, prompt, width, height, length, ref_image_size="match",
                ref_images=None, ref_videos=None, ref_video_audios=None, ref_audios=None,
                ref_image_latents=None, ref_video_latents=None, ref_video_audio_latents=None, ref_audio_latents=None) -> io.NodeOutput:
        latent, frame_count = _empty_av_latent(width, height, length)

        ref_items = []   # for the tokenizer presentation, in request order
        ref_blocks = []  # for the DiT payload, same order

        img_dict = _collect_indexed_dict(ref_images)
        img_lat_dict = _collect_indexed_dict(ref_image_latents)
        all_image_indices = sorted(set(img_dict.keys()) | set(img_lat_dict.keys()))

        for idx in all_image_indices:
            img = img_dict.get(idx)
            in_lat = img_lat_dict.get(idx)

            if img is None and in_lat is None:
                continue

            z = None
            th, tw = 0, 0

            if in_lat is not None:
                z = _normalize_image_latent_4d(in_lat)
                if z is not None:
                    th = z.shape[-2] * 16
                    tw = z.shape[-1] * 16

            if img is not None:
                h, w = img.shape[1], img.shape[2]
                if ref_image_size == "match":
                    scale = min(1.0, math.sqrt((width * height) / (w * h)))
                else:
                    scale = min(1.0, REF_IMAGE_SHORT_EDGE / min(w, h))
                calc_tw = max(CANVAS_MULTIPLE, round(w * scale / CANVAS_MULTIPLE) * CANVAS_MULTIPLE)
                calc_th = max(CANVAS_MULTIPLE, round(h * scale / CANVAS_MULTIPLE) * CANVAS_MULTIPLE)
                resized = _resize(img[:1], calc_tw, calc_th, "disabled")
                ref_items.append({"type": "image", "data": resized})
                if z is None:
                    if vae is None:
                        raise ValueError("VAE is required to encode pixel reference images when direct latents are not connected.")
                    z = vae.encode(resized)
                    tw, th = calc_tw, calc_th
            else:
                ref_items.append({"type": "image"})

            if z is not None:
                ref_blocks.append({"kind": "image", "latent_h": th // 16, "latent_w": tw // 16, "latent": z})

        vid_dict = _collect_indexed_dict(ref_videos)
        vid_lat_dict = _collect_indexed_dict(ref_video_latents)
        aud_dict = _collect_indexed_dict(ref_video_audios)
        aud_lat_dict = _collect_indexed_dict(ref_video_audio_latents)
        all_vid_indices = sorted(set(vid_dict.keys()) | set(vid_lat_dict.keys()))

        for idx in all_vid_indices:
            video_frames = vid_dict.get(idx)
            in_lat = vid_lat_dict.get(idx)
            soundtrack = aud_dict.get(idx)
            in_audio_lat = aud_lat_dict.get(idx)

            if video_frames is None and in_lat is None:
                continue

            z = None
            cw, ch = 0, 0

            if in_lat is not None:
                z = _normalize_video_latent_5d(in_lat)
                if z is not None:
                    ch = z.shape[-2] * 16
                    cw = z.shape[-1] * 16

            if video_frames is not None:
                vh, vw = video_frames.shape[1], video_frames.shape[2]
                calc_cw, calc_ch = adapt_canvas(vw, vh)
                if vw * vh < calc_cw * calc_ch:
                    calc_cw = max(CANVAS_MULTIPLE, round(vw / CANVAS_MULTIPLE) * CANVAS_MULTIPLE)
                    calc_ch = max(CANVAS_MULTIPLE, round(vh / CANVAS_MULTIPLE) * CANVAS_MULTIPLE)
                frames = _resize(video_frames, calc_cw, calc_ch, "disabled")
                if frames.shape[0] > frame_count:
                    frames = frames[:frame_count]
                n = frames.shape[0]
                if n < 5:
                    raise ValueError("MiniMax H3 reference videos need at least 5 frames (~0.2s at 24 fps)")
                while n % 17 != 5:
                    n -= 1
                frames = frames[:n]

                if z is None:
                    if vae is None:
                        raise ValueError("VAE is required to encode pixel reference videos when direct latents are not connected.")
                    z = vae.encode(frames)
                    cw, ch = calc_cw, calc_ch

            audio_latent = None
            ref_audio_t = 0
            if in_audio_lat is not None:
                audio_latent = _normalize_audio_latent_4d(in_audio_lat)
                if audio_latent is not None:
                    ref_audio_t = audio_latent.shape[-1]
                    ref_items.append({"type": "audio"})
            elif soundtrack is not None:
                audio_latent, ref_audio_t = cls._encode_ref_audio(audio_vae, soundtrack)
                ref_items.append({"type": "audio"})

            if video_frames is not None:
                sample_idx = list(range(0, frames.shape[0], FPS // 2))
                qwen_frames = frames[sample_idx]
                ref_items.append({"type": "video", "data": qwen_frames,
                                  "timestamps": [i / 2.0 for i in range(len(sample_idx))]})
            else:
                ref_items.append({"type": "video"})

            if z is not None:
                ref_blocks.append({
                    "kind": "video_audio" if ref_audio_t else "video",
                    "latent_t": z.shape[2],
                    "latent_h": ch // 16,
                    "latent_w": cw // 16,
                    "ref_audio_t": ref_audio_t,
                    "latent": z,
                    "audio_latent": audio_latent,
                })

        standalone_aud_dict = _collect_indexed_dict(ref_audios)
        standalone_aud_lat_dict = _collect_indexed_dict(ref_audio_latents)
        all_aud_indices = sorted(set(standalone_aud_dict.keys()) | set(standalone_aud_lat_dict.keys()))

        for idx in all_aud_indices:
            audio = standalone_aud_dict.get(idx)
            in_lat = standalone_aud_lat_dict.get(idx)

            if audio is None and in_lat is None:
                continue

            audio_latent = None
            ref_audio_t = 0
            if in_lat is not None:
                audio_latent = _normalize_audio_latent_4d(in_lat)
                if audio_latent is not None:
                    ref_audio_t = audio_latent.shape[-1]
            elif audio is not None:
                audio_latent, ref_audio_t = cls._encode_ref_audio(audio_vae, audio)

            if audio_latent is not None:
                ref_items.append({"type": "audio"})
                ref_blocks.append({
                    "kind": "audio",
                    "ref_audio_t": ref_audio_t,
                    "audio_latent": audio_latent,
                })

        tokens = clip.tokenize(prompt, minimax_ref_items=ref_items)
        cond = clip.encode_from_tokens_scheduled(tokens)
        if ref_blocks:
            cond = node_helpers.conditioning_set_values(cond, {"minimax_refs": ref_blocks})
        return io.NodeOutput(cond, latent)


NODE_CLASS_MAPPINGS = {"MiniMaxH3ReferenceToVideo_test": MiniMaxH3ReferenceToVideo_test}
NODE_DISPLAY_NAME_MAPPINGS = {"MiniMaxH3ReferenceToVideo_test": "H3 Eternity [TEST] - Ref2VA Latent"}
