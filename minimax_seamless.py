"""MiniMax H3 Seamless Sampler (EXPERIMENTAL v0).

Temporal MultiDiffusion for H3: instead of generating windows independently and stitching,
this holds the whole clip as one AV latent and, at every denoise step, runs an overlapping
sliding window over it and AVERAGES the model's prediction in the overlaps — so overlapping
regions converge to the same content and the seam disappears (video AND audio) by construction.

See docs/SEAMLESS_LONGFORM_SPEC.md. This is a first cut meant to be run on a GPU and iterated;
it logs its window schedule and first-call shapes so failures are diagnosable. Scope of v0:
- ONE conditioning for the whole clip (per-window prompts come later);
- uniform averaging in overlaps (cosine taper later);
- no first/last keyframe anchors (use a prompt + references for the test).

Positioning is the crux and is validated offline in docs/seamless_positioning_poc.py: each
window's target video+audio RoPE t-coordinates are shifted by the window's GLOBAL temporal
offset so overlapping frames share identical positions. Requires block-aligned window starts
(video-latent frame index % 5 == 0).
"""

import logging
import math

import torch

import comfy.utils
import comfy.model_management
import comfy.ldm.minimax.model as h3m
from comfy_api.latest import io

from .minimax_core import core, samplers
from .minimax_director import _unpack

log = logging.getLogger(__name__)


# These two live in comfy_extras/nodes_minimax_h3.py (not comfy.ldm.minimax.model). Tiny and
# stable — defined here verbatim so the node has no dependency on a comfy_extras import path.
def _align_frame_count(n):
    while n % 17 != 5:
        n += 1
    return n


def _video_latent_t(frame_count):
    return 2 if frame_count <= 5 else ((frame_count - 5) // 17) * 5 + 2


def _globalcoord(gv):
    """Global temporal coordinate of video-latent frame `gv` (exclusive cumsum of spans).
    Numerically equals the global audio-latent frame index too (both are 28.33 per 5-block)."""
    return float(sum(h3m.FRAME_RESCALE * h3m.FRAME_PER_TOKEN[k % 5] for k in range(int(gv))))


def _valid_vlt_at_least(target):
    """Smallest valid video_latent_t (2, 7, 12, … = 2+5k) that is >= target."""
    k = max(0, math.ceil((target - 2) / 5.0))
    return 2 + 5 * k


def _plan_windows(tv, win_lat, overlap_lat):
    """Block-aligned (start % 5 == 0) windows of `win_lat` video-latent frames covering [0, tv),
    stepping by (win_lat - overlap_lat) rounded to a multiple of 5. Last window clamped to the end."""
    win_lat = min(win_lat, tv)
    stride = max(5, ((win_lat - overlap_lat) // 5) * 5)
    starts = []
    g = 0
    while True:
        if g + win_lat >= tv:
            last = ((tv - win_lat) // 5) * 5
            last = max(0, last)
            if last not in starts:
                starts.append(last)
            break
        starts.append(g)
        g += stride
    return [(s, win_lat if s + win_lat <= tv else tv - s) for s in starts]


class MiniMaxH3SeamlessSampler(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3SeamlessSamplerCS",
            display_name="MiniMax H3 Seamless Sampler (experimental)",
            category="MiniMax H3",
            description="Temporal MultiDiffusion co-denoising for H3 — seamless long-form video+audio. "
                        "Wire a ReferenceToVideo/ImageToVideo (cond + AV latent) for the whole clip. v0.",
            inputs=[
                io.Model.Input("model", tooltip="H3 model (SigmaShift is applied here; drop external SigmaShift)."),
                io.Conditioning.Input("positive"),
                io.Latent.Input("latent", tooltip="The whole-clip AV latent (from ReferenceToVideo/ImageToVideo)."),
                io.Sampler.Input("sampler"),
                io.Sigmas.Input("sigmas"),
                io.Int.Input("noise_seed", default=0, min=0, max=0xffffffffffffffff),
                io.Float.Input("window_seconds", default=5.0, min=4.0, max=15.0, step=0.5,
                               tooltip="Co-denoise window length (H3's 4-15s trained range)."),
                io.Float.Input("overlap_seconds", default=2.0, min=0.5, max=8.0, step=0.5,
                               tooltip="Overlap between windows. More overlap = stronger seam consensus, more compute."),
                io.Float.Input("shift_video", default=12.0, min=0.01, max=100.0, step=0.01, optional=True),
                io.Float.Input("shift_audio", default=3.0, min=0.01, max=100.0, step=0.01, optional=True),
            ],
            outputs=[io.Latent.Output(display_name="latent", tooltip="Sampled AV latent — wire to VAEDecode.")],
        )

    @classmethod
    def execute(cls, model, positive, latent, sampler, sigmas, noise_seed,
                window_seconds, overlap_seconds, shift_video=12.0, shift_audio=3.0) -> io.NodeOutput:
        mm = core()
        sm = samplers()

        samples = latent["samples"]
        if not getattr(samples, "is_nested", False):
            raise ValueError("Seamless sampler needs a packed H3 AV latent (video+audio). "
                             "Feed the latent straight from ReferenceToVideo / ImageToVideo.")
        video0, audio0 = list(samples.unbind())[:2]
        tv = int(video0.shape[2])
        fps_lat = 24.0

        win_frames = _align_frame_count(max(5, int(round(window_seconds * fps_lat))))
        win_lat = _video_latent_t(win_frames)
        # overlap in latent frames ≈ overlap_seconds worth of video-latent frames
        ov_frames = max(1, int(round(overlap_seconds * fps_lat)))
        overlap_lat = max(5, _video_latent_t(_align_frame_count(ov_frames)))
        windows = _plan_windows(tv, win_lat, overlap_lat)

        log.info("[MiniMaxSeamless] full video-latent frames=%d | window=%d lat (%.1fs) | "
                 "overlap≈%d lat | %d windows: %s",
                 tv, win_lat, window_seconds, overlap_lat, len(windows),
                 ", ".join("[%d,%d)" % (s, s + n) for s, n in windows))
        for s, n in windows:
            if s % 5 != 0:
                raise ValueError("internal: window start %d not block-aligned (%%5)" % s)

        patched_model = _unpack(mm.MiniMaxH3SigmaShift.execute(
            model=model, shift_video=float(shift_video), shift_audio=float(shift_audio)))[0]
        m = patched_model.clone()

        state = {"first": True}

        def wrapper(apply_model, args):
            input_x = args["input"]          # [B, 1, Nv+Na] full, audio-scaled
            ts = args["timestep"]
            c = args["c"]
            if state["first"]:
                log.info("[MiniMaxSeamless] wrapper first call: input=%s | c keys=%s | "
                         "types: latent_shapes=%s minimax_payload=%s c_crossattn=%s",
                         tuple(input_x.shape), sorted(c.keys()),
                         type(c.get("latent_shapes")).__name__,
                         type(c.get("minimax_payload")).__name__,
                         type(c.get("c_crossattn")).__name__)
            shapes = list(c["latent_shapes"])
            payload = dict(c.get("minimax_payload") or {})
            text_len = int(c["c_crossattn"].shape[1])
            vfull, afull = comfy.utils.unpack_latents(input_x, shapes)  # [B,24,Tv,H,W], [B,32,2,Ta]
            B, Cv, Tvv, H, W = vfull.shape
            Ta = afull.shape[-1]

            if state["first"]:
                log.info("[MiniMaxSeamless] first model call: video=%s audio=%s text_len=%d shapes=%s",
                         tuple(vfull.shape), tuple(afull.shape), text_len, shapes)
                state["first"] = False

            acc_v = torch.zeros_like(vfull)
            acc_a = torch.zeros_like(afull)
            wsum_v = torch.zeros(Tvv, device=vfull.device, dtype=vfull.dtype)
            wsum_a = torch.zeros(Ta, device=afull.device, dtype=afull.dtype)

            for (gv, nv) in windows:
                ga = int(round(_globalcoord(gv)))
                na = int(round(_globalcoord(gv + nv))) - ga
                na = max(1, min(na, Ta - ga))
                if ga >= Ta:
                    continue
                vwin = vfull[:, :, gv:gv + nv].contiguous()
                awin = afull[:, :, :, ga:ga + na].contiguous()
                xw, shapes_w = comfy.utils.pack_latents([vwin, awin])

                layout = h3m.PackedLayout(text_len, nv, H, W, na,
                                          keyframes=None, refs=payload.get("refs"),
                                          frame_count=payload.get("frame_count"))
                off = _globalcoord(gv)
                if off != 0.0:
                    for a, b, kind in layout.segments:
                        if kind in ("video", "audio"):
                            layout.position_ids[a:b, 0] += off

                c_w = dict(c)
                c_w["latent_shapes"] = shapes_w
                c_w["minimax_payload"] = {**payload, "layout": layout}
                out_w = apply_model(xw, ts, **c_w)
                dv, da = comfy.utils.unpack_latents(out_w, shapes_w)

                acc_v[:, :, gv:gv + nv] += dv
                wsum_v[gv:gv + nv] += 1.0
                acc_a[:, :, :, ga:ga + na] += da
                wsum_a[ga:ga + na] += 1.0

            wsum_v = wsum_v.clamp(min=1.0)
            wsum_a = wsum_a.clamp(min=1.0)
            acc_v = acc_v / wsum_v.view(1, 1, Tvv, 1, 1)
            acc_a = acc_a / wsum_a.view(1, 1, 1, Ta)
            out, _ = comfy.utils.pack_latents([acc_v, acc_a])
            return out

        m.set_model_unet_function_wrapper(wrapper)

        guider = _unpack(sm.BasicGuider.execute(model=m, conditioning=positive))[0]
        noise = sm.Noise_RandomNoise(int(noise_seed))
        sampled = _unpack(sm.SamplerCustomAdvanced.execute(
            noise=noise, guider=guider, sampler=sampler, sigmas=sigmas, latent_image=latent))[0]

        # Free the DiT before handing the latent downstream, so the VAE decode node has the
        # whole card and does not fall back to CPU (the crash two-phase decode guards against
        # in the chaining path — which does NOT run here, since this node only samples).
        comfy.model_management.unload_all_models()
        comfy.model_management.soft_empty_cache()
        return io.NodeOutput(sampled)


NODE_CLASS_MAPPINGS = {"MiniMaxH3SeamlessSamplerCS": MiniMaxH3SeamlessSampler}
NODE_DISPLAY_NAME_MAPPINGS = {"MiniMaxH3SeamlessSamplerCS": "MiniMax H3 Seamless Sampler (experimental)"}
