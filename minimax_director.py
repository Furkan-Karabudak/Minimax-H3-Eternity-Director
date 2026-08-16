"""MiniMax H3 Director — a WYSIWYG timeline front-end for MiniMax H3.

The timeline editor (js/minimax_director.js) is a modified version of the LTX Director
editor by WhatDreamsCost (GPL-3.0, see LICENSE), by way of the CS fork by CGlide;
modified in 2026 for MiniMax H3. What changed is everything below the UI, because H3
conditions completely differently from LTX 2.3:

* LTX 2.3 gets per-segment prompts through a Prompt-Relay cross-attention mask.
  H3 is a single-stream packed DiT whose only attention is full self-attention with
  `mask=None` hardcoded, and whose Qwen3-VL text encoder was trained on *storyboard*
  prompts with explicit `[0s-1.5s]` shot markers. So timeline segments are compiled
  into that storyboard form — the model's own native mechanism for timed control,
  and exactly what the official H3 templates do.

* Keyframes: H3's PackedLayout only accepts anchors at frame 0 and frame_count-1, so
  timeline images resolve to first_frame / last_frame. Images in the middle become
  <Picture i> references instead (ref2va), the closest thing H3 offers.

* Audio: H3 generates native stereo audio jointly with the video, so there is no audio
  latent to inpaint. Imported audio becomes an <Audio j> reference for voice/music
  style, and is always also emitted on `combined_audio` for muxing.

* The reference-video track (the old IC-LoRA track) feeds <Video k> references.

Two conditioning paths, each with its own diffusion weights:
  Refs OFF -> t2va / fl2va  (minimax_h3_fl2va_*)
  Refs ON  -> ref2va        (minimax_h3_ref2va_*)

All timeline interpretation lives in minimax_plan.py so the live prompt preview and the
chain node cannot drift from what actually gets encoded.
"""

import json
import logging

import torch

import comfy.model_management
import comfy.utils
from comfy_api.latest import io

from . import minimax_media as media
from . import minimax_plan as plan
from .minimax_core import audio_nodes, core, samplers

AUDIO_SR = media.AUDIO_SR

log = logging.getLogger(__name__)

MODEL_FPS = plan.MODEL_FPS
DEFAULT_W, DEFAULT_H = 1344, 768
# Measured, not assumed: 32x32 renders end to end, 16x16 passes PackedLayout and then dies
# inside the video VAE, and anything under 8 leaves a zero-edged latent that takes core's
# PackedLayout down first. 32 is also H3's own step, which is why divisible_by defaults to
# it — with the defaults this floor is unreachable anyway.
MIN_CANVAS_EDGE = 32


# --------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------

def _unpack(out):
    """Normalise an io.NodeOutput / tuple / list into a plain tuple."""
    if out is None:
        return ()
    args = getattr(out, "args", None)
    if isinstance(args, (tuple, list)):
        return tuple(args)
    result = getattr(out, "result", None)
    if isinstance(result, (tuple, list)):
        return tuple(result)
    if isinstance(out, (tuple, list)):
        return tuple(out)
    if isinstance(out, dict) and isinstance(out.get("result"), (tuple, list)):
        return tuple(out["result"])
    return (out,)


def _snap(value, multiple):
    # Floor, not round — same as the LTX Director's snap() and media.resize_image(), so a
    # derived edge never grows past the box. 16:9 at height 768 lands on 1344, H3's native
    # canvas, instead of overshooting to 1376.
    return max(multiple, (int(value) // multiple) * multiple)


def resolve_canvas(mm, custom_width, custom_height, divisible_by, resize_method, first_image):
    """Pick the output canvas.

    With both dimensions set, the widgets are a *box*, not a verdict: the first timeline
    image is run through the chosen resize_method and the canvas becomes whatever comes
    out. That is what the LTX Director does, and it is why 'maintain aspect ratio' with a
    1024x1024 box gives a 16:9 image 1024x576 instead of a squashed square. Every other
    method returns the full box.
    """
    div = max(1, int(divisible_by))
    if custom_width > 0 and custom_height > 0:
        if first_image is not None:
            fitted = media.resize_image(first_image[:1], custom_width, custom_height,
                                        resize_method, div)
            return int(fitted.shape[2]), int(fitted.shape[1])
        return _snap(custom_width, div), _snap(custom_height, div)

    if first_image is not None:
        src_h, src_w = int(first_image.shape[1]), int(first_image.shape[2])
    else:
        src_w, src_h = DEFAULT_W, DEFAULT_H

    if custom_width > 0:
        w = _snap(custom_width, div)
        return w, _snap(src_h * w / max(1, src_w), div)
    if custom_height > 0:
        h = _snap(custom_height, div)
        return _snap(src_w * h / max(1, src_h), div), h

    # H3's own canvas policy: 768 short edge, 768*1344 area cap, per-axis round to 32
    return mm.adapt_canvas(src_w, src_h)


def resolve_window(tdata, fps, start_frame, duration_frames,
                   start=None, end=None, duration=None):
    """Resolve the render window, honouring automation inputs and retake mode.

    The automation sockets are the only route by which a nonsensical window reaches this
    node: the widgets carry minimums, a connected input carries none. A `duration` of 0 —
    what an upstream node hands over when its own value was never set — used to clamp to
    one timeline frame and then render five, a fifth of a second, without a word. Refuse
    it by name instead. Whatever breaks downstream on a window that short breaks a long
    way from the wire that caused it, which is the expensive kind of bug to report.
    """
    if start is not None:
        if float(start) < 0:
            raise ValueError(
                "MiniMax H3 Director: the connected 'start' is %.3gs. It is a position in "
                "seconds and cannot be negative." % float(start))
        start_frame = int(round(float(start) * fps))
    if end is not None:
        end_frame = int(round(float(end) * fps))
        if duration is None:
            if end_frame <= start_frame:
                raise ValueError(
                    "MiniMax H3 Director: the connected 'end' (%.3gs) is not after the "
                    "window start (%.3gs), so there is nothing to render. Both are in "
                    "seconds." % (float(end), start_frame / fps))
            duration_frames = end_frame - start_frame
    if duration is not None:
        if float(duration) <= 0:
            raise ValueError(
                "MiniMax H3 Director: the connected 'duration' is %.3gs, so there is "
                "nothing to render. It is a length in seconds — H3's trained range is "
                "4-15s. Check the node feeding it; a value that was never set arrives "
                "here as 0." % float(duration))
        duration_frames = max(1, int(round(float(duration) * fps)))

    retake = plan.retake_state(tdata)
    if retake:
        # the marked range replaces the panel window entirely
        return int(retake["start"]), max(1, int(retake["length"]))
    return int(start_frame), max(1, int(duration_frames))


def _load_event_tensor(ev, fps, win_start):
    """Decode the pixels behind one main-track segment, image or video."""
    seg = ev["seg"]
    if ev["kind"] == "video":
        seg_start = float(seg.get("start", 0))
        trim = float(seg.get("trimStart", 0)) + max(0.0, win_start - seg_start)
        return media.load_video_tensor(seg.get("imageFile", ""), trim / fps,
                                       float(seg.get("length", 1)) / fps)
    return media.load_image_tensor(seg)


class _Unconnected:
    """Distinguishes an empty optional socket from a lazy one that is merely unevaluated.

    ComfyUI passes None for both, so a plain `None` default cannot tell them apart.
    """
    def __repr__(self):
        return "<unconnected>"


_UNCONNECTED = _Unconnected()


def pick_model(model_fl2va, model_ref2va, ref_mode_on):
    """Choose the weights the toolbar switch calls for.

    fl2va and ref2va are separate checkpoints, so the switch that changes the conditioning
    path has to change the model too. Connect both and it is automatic; connect one and it
    is used either way, with a warning when that is the wrong one for the current path.
    """
    wanted, other = (model_ref2va, model_fl2va) if ref_mode_on else (model_fl2va, model_ref2va)
    label = "ref2va" if ref_mode_on else "fl2va"
    if wanted is not None:
        return wanted
    if other is not None:
        log.warning("[MiniMaxDirector] The toolbar is on '%s' but no %s model is connected — "
                    "using the other one. Load minimax_h3_%s_* for correct results.",
                    "Refs ON" if ref_mode_on else "Refs OFF", label, label)
        return other
    raise ValueError(
        "MiniMax H3 Director: no model connected. Wire a UNETLoader into 'model (t2v/i2v)' "
        "(minimax_h3_fl2va_*) and/or 'model (ref2v)' (minimax_h3_ref2va_*)."
    )


def _grab_base_frame(video_ref, frame_index, fps):
    """One frame out of the retake base video, by timeline frame index."""
    if frame_index < 0:
        return None
    frames = media.load_video_tensor(video_ref, frame_index / fps, 1.0 / MODEL_FPS)
    if frames is None or frames.shape[0] == 0:
        return None
    return frames[:1]


# --------------------------------------------------------------------------------------
# chaining helpers — sample/decode a timeline longer than one H3 shot as anchored windows
# (folded in from the withdrawn minimax_chain node so it runs on the live timeline)
# --------------------------------------------------------------------------------------

def _decode_video(vae, latent, tiled=False):
    """Core's VAEDecode — it unbinds the packed AV latent to the video stream first
    (`latent.unbind()[0]`), which vae.decode() cannot do on its own.

    `tiled` routes through VAEDecodeTiled (which does the same unbind) so a long window is
    decoded in spatial + temporal tiles. Decoding a whole 100+ frame window at once builds
    activation tensors too big for the VRAM left after the DiT is staged, and ComfyUI then
    offloads the decode to CPU — GPU idle, CPU/RAM pegged. Tiling bounds those activations
    so it stays on the GPU. Falls back to a full decode if the tiled path ever errors."""
    import nodes as comfy_nodes
    if tiled:
        try:
            images = comfy_nodes.VAEDecodeTiled().decode(
                vae, latent, tile_size=512, overlap=64,
                temporal_size=32, temporal_overlap=8)[0]
            return images.to(torch.float32).cpu()
        except Exception as e:
            log.warning("[MiniMaxDirector] tiled VAE decode failed (%s) — full decode instead.", e)
    images = comfy_nodes.VAEDecode().decode(vae, latent)[0]
    return images.to(torch.float32).cpu()


def _decode_anchor_frame(vae, latent, tail_latent_frames=4):
    """Decode ONLY the tail of a window's latent to recover its last pixel frame — the
    anchor that seeds the next window. The video stream is a NestedTensor entry shaped
    [B, C, T_lat, H, W]; we slice the last few latent frames off its temporal axis, rebuild
    the nested latent, and run it through the SAME VAEDecode path a full decode uses (so no
    new assumptions about the VAE) — just on a handful of frames. Cheap enough to run while
    the DiT is still resident, which is what lets the heavy full decode be deferred to one
    GPU pass after the DiT is freed. Falls back to a full decode on any error, so continuity
    is never silently lost."""
    import nodes as comfy_nodes
    try:
        samples = latent["samples"]
        sliced = latent
        if getattr(samples, "is_nested", False):
            parts = list(samples.unbind())
            video = parts[0]
            if video.dim() >= 3 and video.shape[2] > tail_latent_frames:
                import comfy.nested_tensor
                parts[0] = video[:, :, -tail_latent_frames:].contiguous()
                sliced = {"samples": comfy.nested_tensor.NestedTensor(tuple(parts))}
        elif samples.dim() >= 3 and samples.shape[2] > tail_latent_frames:
            sliced = {"samples": samples[:, :, -tail_latent_frames:].contiguous()}
        images = comfy_nodes.VAEDecode().decode(vae, sliced)[0]
        return images[-1:].to(torch.float32).cpu()
    except Exception as e:
        log.warning("[MiniMaxDirector] cheap anchor decode failed (%s) — full decode for anchor.", e)
        return _decode_video(vae, latent)[-1:]


def _decode_audio(audio_vae, latent):
    out = audio_nodes().VAEDecodeAudio.execute(vae=audio_vae, samples=latent)
    args = getattr(out, "args", None) or getattr(out, "result", None) or (out,)
    return args[0]


def _audio_to_stereo(audio):
    if audio is None:
        return None, AUDIO_SR
    waveform = audio.get("waveform")
    if waveform is None:
        return None, AUDIO_SR
    if waveform.ndim == 3:
        waveform = waveform[0]
    waveform = waveform.to(torch.float32).cpu()
    if waveform.shape[0] == 1:
        waveform = waveform.repeat(2, 1)
    elif waveform.shape[0] > 2:
        waveform = waveform[:2]
    return waveform, int(audio.get("sample_rate", AUDIO_SR))


def _concat_audio_declick(chunks, fade_samples):
    """Join per-window audio with a short equal-power cross-fade at each seam.

    Two independently-generated windows meet with a step discontinuity in the waveform —
    an audible click at every join. An equal-power (sin/cos) cross-fade ramps one out as
    the other ramps in; equal-power (not linear) because the two blocks are uncorrelated,
    so a linear blend would dip in power through the middle of the transition. The overlap
    shortens the total by `fade_samples` per seam — ~12ms, well below anything that reads
    as A/V drift — in exchange for a clean join."""
    chunks = [c for c in chunks if c is not None and c.shape[1] > 0]
    if not chunks:
        return None
    out = chunks[0]
    for nxt in chunks[1:]:
        f = int(min(fade_samples, out.shape[1], nxt.shape[1]))
        if f <= 1:
            out = torch.cat([out, nxt], dim=1)
            continue
        ramp = torch.linspace(0.0, 1.0, f, dtype=out.dtype) * (torch.pi / 2.0)
        fade_out = torch.cos(ramp)          # 1 -> 0, equal-power
        fade_in = torch.sin(ramp)           # 0 -> 1, equal-power
        head = out[:, :out.shape[1] - f]
        blend = out[:, out.shape[1] - f:] * fade_out + nxt[:, :f] * fade_in
        out = torch.cat([head, blend, nxt[:, f:]], dim=1)
    return out


def split_windows(duration_frames, window_frames, min_frames=1, max_frames=0):
    """Cut the render range into evenly-sized, in-range windows.

    Even distribution rather than "N full windows plus a stub": a 13s render at a 5s
    target becomes three 4.33s windows, not [5s, 5s, 3s] — so no window lands below H3's
    trained floor (which snaps up and looks under-animated) and the seams are evenly
    spaced. The windows sum EXACTLY to duration_frames and differ by at most one frame.

    Failsafes, so the caller never has to think about it:
      * fewer, slightly longer windows before any window drops below `min_frames`;
      * more windows before any window exceeds `max_frames` (H3's per-shot ceiling).
    With H3's 4-15s range both are always satisfiable at once (15 >= 2*4)."""
    D = max(1, int(duration_frames))
    W = max(1, int(window_frames))
    if max_frames:
        W = min(W, int(max_frames))
    if D <= W:
        return [(0, D)]

    count = (D + W - 1) // W                              # ceil(D / W)
    lo = max(1, int(min_frames))
    while count > 1 and D < lo * count:                  # a window would fall below the floor
        count -= 1
    if max_frames:                                        # ...but never above the ceiling
        hi = int(max_frames)
        count = max(count, (D + hi - 1) // hi)

    base, rem = divmod(D, count)                          # even split, remainder spread over the first windows
    windows, cursor = [], 0
    for i in range(count):
        span = base + (1 if i < rem else 0)
        windows.append((cursor, span))
        cursor += span
    return windows


def _ref_slot_name(slot):
    """A human filename for one <Picture i> slot, for the gen log."""
    src = slot.get("source")
    if src == "char":
        return slot.get("image", {}).get("name", "") or "(character slot)"
    if src == "input":
        return "(ref_images input)"
    ev = slot.get("event") or {}
    key = {plan.ROLE_FIRST: "first", plan.ROLE_LAST: "last"}.get(slot.get("keyframe"), "")
    name = ev.get("name") or ev.get("seg", {}).get("fileName", "") or "(timeline image)"
    return "%s%s" % (name, " [%s frame]" % key if key else "")


def _build_gen_log(p, tdata, global_prompt, width, height, length, fps,
                   window_prompts=None):
    """A complete, saveable record of one generation: settings, every reference file,
    the audio prompts, and the compiled storyboard. `prompt` output text — never encoded,
    so it is free to say more than the model sees."""
    L = []
    L.append("==== MiniMax H3 Director — generation log ====")
    L.append("canvas: %dx%d | %d frames (%.2fs @%.0ffps) | path: %s%s"
             % (width, height, length, length / MODEL_FPS, MODEL_FPS,
                p.get("mode", "?"), " | CHAINED %d windows" % len(window_prompts)
                if window_prompts else ""))

    gp = (global_prompt or "").strip()
    if gp:
        L.append("")
        L.append("-- global prompt --")
        L.append(gp)

    soundscape = (tdata.get("overall_soundscape", "") or "").strip()
    music = (tdata.get("non_diegetic_music", "") or "").strip()
    if soundscape or music:
        L.append("")
        L.append("-- audio --")
        if soundscape:
            L.append("overall_soundscape: " + soundscape)
        if music:
            L.append("non_diegetic_music: " + music)

    slots = p.get("ref_image_slots") or []
    vids = p.get("ref_video_segs") or []
    auds = p.get("ref_audio_segs") or []
    if slots or vids or auds:
        L.append("")
        L.append("-- references --")
        for i, slot in enumerate(slots):
            L.append("  <Picture %d>  %s" % (i + 1, _ref_slot_name(slot)))
        for i, seg in enumerate(vids):
            L.append("  <Video %d>    %s" % (i + 1, seg.get("fileName") or seg.get("videoFile", "")))
        for i, seg in enumerate(auds):
            L.append("  <Audio %d>    %s" % (i + 1, seg.get("fileName") or seg.get("audioFile", "")))
    else:
        # fl2va keyframes (no ref slots) — still worth recording their source files
        kf = []
        for ev in p.get("events") or []:
            if ev.get("role") == plan.ROLE_FIRST:
                kf.append("first: " + (ev.get("name") or "(image)"))
            elif ev.get("role") == plan.ROLE_LAST:
                kf.append("last:  " + (ev.get("name") or "(image)"))
        if kf:
            L.append("")
            L.append("-- keyframes --")
            L.extend("  " + k for k in kf)

    if window_prompts:
        L.append("")
        L.append("-- windows --")
        L.extend(window_prompts)
    else:
        L.append("")
        L.append("-- storyboard (encoded) --")
        L.append(p.get("prompt", ""))
    return "\n".join(L)


# --------------------------------------------------------------------------------------
# node
# --------------------------------------------------------------------------------------

class MiniMaxH3Director(io.ComfyNode):
    """Timeline editor -> MiniMax H3 storyboard conditioning + joint AV latent."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3DirectorCS",
            display_name="MiniMax H3 Director",
            category="MiniMax H3",
            description=(
                "Visual timeline for MiniMax H3. Segments become a storyboard prompt with "
                "[0s-1.5s] shot markers, timeline images become first/last keyframes (fl2va) "
                "or <Picture i> references (ref2va), the reference-video track becomes "
                "<Video k>, and audio clips become <Audio j> plus a muxable audio output. "
                "Retake Mode regenerates a marked range of a base video between its own "
                "surrounding frames."
            ),
            inputs=[
                # lazy: only the checkpoint the toolbar actually calls for gets loaded.
                # See check_lazy_status below — without it ComfyUI resolves both inputs
                # before the node runs and reads ~42 GB of weights to use half of them.
                io.Model.Input("model", display_name="model (t2v/i2v)", optional=True, lazy=True,
                               tooltip="The fl2va weights (minimax_h3_fl2va_*), used when the "
                                       "toolbar is on 'Refs OFF'. Connect both models and the "
                                       "node loads whichever the toolbar switch calls for — "
                                       "the other one is never read from disk."),
                io.Model.Input("model_ref2va", display_name="model (ref2v)", optional=True, lazy=True,
                               tooltip="The ref2va weights (minimax_h3_ref2va_*), used when the "
                                       "toolbar is on 'Refs ON'. Optional — with only one model "
                                       "connected that one is used either way."),
                io.Clip.Input("clip", tooltip="Qwen3-VL-32B MiniMax text encoder (CLIPLoader type 'minimax')."),
                io.Vae.Input("vae", tooltip="minimax_h3_video_vae — encodes keyframes and references."),
                io.Vae.Input("audio_vae", optional=True,
                             tooltip="minimax_h3_audio_vae. Only needed when audio references are used (ref2va)."),
                io.Float.Input("start_second", default=0.0, min=0.0, max=1000.0, step=0.01,
                               tooltip="Start of the render window, in seconds."),
                io.Float.Input("end_second", default=5.0, min=0.0, max=1000.0, step=0.01,
                               tooltip="End of the render window, in seconds."),
                io.Float.Input("duration_seconds", default=5.0, min=0.1, max=1000.0, step=0.01,
                               tooltip="Render length in seconds. Snapped up to H3's 17k+5 frame grid at 24 fps."),
                io.Int.Input("start_frame", default=0, min=0, max=10000, step=1,
                             tooltip="Start of the render window, in timeline frames."),
                io.Int.Input("end_frame", default=120, min=1, max=10000, step=1,
                             tooltip="End of the render window, in timeline frames."),
                io.Int.Input("duration_frames", default=120, min=1, max=10000, step=1,
                             tooltip="Render length in timeline frames (at the timeline's frame_rate)."),
                io.String.Input("timeline_data", default="",
                                tooltip="JSON state of the timeline editor (auto-managed; do not edit by hand)."),
                io.Boolean.Input("use_custom_audio", default=False, optional=True,
                                 tooltip="ON: timeline audio clips are used as <Audio j> references (ref2va). "
                                         "The mixdown is always available on combined_audio regardless."),
                io.Boolean.Input("use_custom_motion", default=True, optional=True,
                                 tooltip="ON: the reference-video track feeds <Video k> references (ref2va)."),
                io.Boolean.Input("inpaint_audio", default=True, optional=True,
                                 tooltip="Unused on H3 — audio is generated jointly with the video and cannot be inpainted."),
                io.String.Input("local_prompts", multiline=True, default="",
                                tooltip="Auto-populated from the timeline editor."),
                io.String.Input("segment_lengths", default="",
                                tooltip="Auto-populated from the timeline editor (pixel-space frame counts)."),
                io.Float.Input("frame_rate", default=24, min=1, max=240, step=1, optional=True,
                               tooltip="Timeline editing rate. Output is always 24 fps; times are converted via seconds."),
                io.Combo.Input("display_mode", options=["frames", "seconds"], default="seconds", optional=True,
                               tooltip="Show the ruler and segment ranges in frames or seconds."),
                io.String.Input("guide_strength", default="",
                                tooltip="Auto-populated from the timeline editor. H3 has no per-keyframe strength, so it is ignored."),
                io.Int.Input("custom_width", default=0, min=0, max=8192, step=1, optional=True,
                             tooltip="Output width. With height set too this is a BOX: 'maintain aspect ratio' "
                                     "keeps the first image's aspect inside it. 0 = derive from the image."),
                io.Int.Input("custom_height", default=0, min=0, max=8192, step=1, optional=True,
                             tooltip="Output height. See custom_width."),
                io.Combo.Input("resize_method",
                               options=["maintain aspect ratio", "stretch to fit", "pad", "pad green", "crop"],
                               default="crop", optional=True,
                               tooltip="How timeline images are fitted to the output canvas."),
                io.Int.Input("divisible_by", default=32, min=1, max=256, step=1, optional=True,
                             tooltip="Snap output dimensions to this multiple. H3 needs 32."),
                io.Int.Input("img_compression", default=0, min=0, max=100, step=1, optional=True,
                             tooltip="H.264 CRF baked into each keyframe. 0 = off (recommended for H3)."),
                io.Boolean.Input("override_audio", default=False, optional=True,
                                 tooltip="Use the reference video's own soundtrack as the timeline audio."),
                io.Combo.Input("ref_image_size", options=["match", "max"], default="match", optional=True,
                               tooltip="ref2va only. 'match' scales references to the output pixel area (fast); "
                                       "'max' keeps a 2048 px short edge for identity, at real speed cost."),
                io.Float.Input("shift_video", default=12.0, min=0.01, max=100.0, step=0.01, optional=True,
                               tooltip="Video flow sigma shift (H3 default 12.0)."),
                io.Float.Input("shift_audio", default=3.0, min=0.01, max=100.0, step=0.01, optional=True,
                               tooltip="Audio flow sigma shift (H3 default 3.0)."),
                # --- long-form chaining (optional) --------------------------------------
                # Wire a SAMPLER and SIGMAS and the Director samples internally, rendering a
                # timeline past H3's ~15s ceiling as a chain of anchored windows on THIS
                # timeline. Leave them unwired and the node behaves exactly as before
                # (emits `latent` for an external SamplerCustomAdvanced, with live preview).
                io.Sampler.Input("sampler", optional=True,
                                 tooltip="Chaining: wire a SAMPLER here to render >15s in-place. "
                                         "Needs SIGMAS too. Unwired = normal latent output."),
                io.Sigmas.Input("sigmas", optional=True,
                                tooltip="Chaining: the schedule sampled per window (e.g. a 4-step "
                                        "turbo schedule). Only used when 'sampler' is also wired."),
                io.Int.Input("noise_seed", default=0, min=0, max=0xffffffffffffffff,
                             control_after_generate=True, optional=True,
                             tooltip="Chaining only. Base seed; each window uses seed + its index."),
                io.Float.Input("window_seconds", default=5.0, min=4.0, max=15.0, step=0.125,
                               tooltip="Chaining only. Length of each window before anchoring the next. "
                                       "H3's trained range is ~4-15s; 5s is the most stable, 14.375s "
                                       "(345 frames) is the longest in-range window = fewest seams but "
                                       "more drift. Below ~4s snaps up and seams constantly — don't."),
                io.Boolean.Input("tiled_vae_decode", default=False, optional=True,
                                 tooltip="Chaining only. Decode each window in spatial + temporal tiles "
                                         "so it fits in VRAM and stays on the GPU. Turn ON if VAE decode "
                                         "pegs CPU/RAM while the GPU sits idle (the DiT left no room). "
                                         "Marginally slower per frame, but avoids the CPU-decode stall."),
                io.Float.Input("start", force_input=True, optional=True, default=0.0,
                               tooltip="Automation (connection-only). Window start in SECONDS."),
                io.Float.Input("end", force_input=True, optional=True, default=0.0,
                               tooltip="Automation (connection-only). Window end in SECONDS."),
                io.Float.Input("duration", force_input=True, optional=True, default=0.0,
                               tooltip="Automation (connection-only). Render length in SECONDS."),
            ],
            outputs=[
                io.Model.Output(display_name="model"),
                io.Conditioning.Output(display_name="positive"),
                io.Latent.Output(display_name="latent", tooltip="Joint video+audio latent. Wire to SamplerCustomAdvanced."),
                io.Audio.Output(display_name="combined_audio",
                                tooltip="Timeline audio mixdown. Wire into CreateVideo to replace the generated audio."),
                io.Float.Output(display_name="fps", tooltip="Always 24.0 — H3's native output rate. Wire into CreateVideo."),
                io.Int.Output(display_name="width"),
                io.Int.Output(display_name="height"),
                io.Int.Output(display_name="length", tooltip="Frame count actually generated (snapped to the 17k+5 grid)."),
                io.String.Output(display_name="prompt", tooltip="The compiled storyboard prompt that was encoded."),
                io.String.Output(display_name="retake_info",
                                 tooltip="JSON describing the retake window. Wire into MiniMax H3 Retake Stitch "
                                         "to splice the result back into the base video. Empty when retake is off."),
                io.Image.Output(display_name="images",
                                tooltip="Chaining only: all windows decoded and concatenated at 24fps. "
                                        "None in normal (external-sampler) mode."),
                io.Audio.Output(display_name="audio",
                                tooltip="Chaining only: generated audio, concatenated across windows. "
                                        "None in normal mode (use combined_audio / the sampler path)."),
            ],
        )

    # ------------------------------------------------------------ lazy models

    @classmethod
    def check_lazy_status(cls, timeline_data="", model=_UNCONNECTED,
                          model_ref2va=_UNCONNECTED, **_):
        """Ask for the one checkpoint the toolbar switch calls for, and only that one.

        fl2va and ref2va are ~21 GB each. Without this, ComfyUI resolves both inputs
        before execute() runs, so every render reads both from disk to throw one away —
        which is what pushed a 32 GB machine into a page-file crash (issue #2).

        `None` means *connected but not evaluated yet*, so it cannot be used to detect an
        empty socket; that is what the _UNCONNECTED sentinel is for. Same trick core uses
        in comfy_extras/nodes_logic.py.
        """
        ref_on = plan.ref_mode_from(plan.parse_timeline(timeline_data))
        order = ("model_ref2va", "model") if ref_on else ("model", "model_ref2va")
        have = {"model": model, "model_ref2va": model_ref2va}

        for name in order:                       # preferred first, then the fallback
            if have[name] is _UNCONNECTED:
                continue                         # nothing wired here, try the other
            return [name] if have[name] is None else []
        return []                                # neither connected: execute() raises

    # ---------------------------------------------------------------- execute

    @classmethod
    def execute(cls, clip, vae, start_second, end_second, duration_seconds,
                start_frame, end_frame, duration_frames, timeline_data,
                model=None, model_ref2va=None,
                local_prompts="", segment_lengths="", global_prompt="", guide_strength="",
                frame_rate=24, display_mode="seconds",
                custom_width=0, custom_height=0, resize_method="crop",
                divisible_by=32, img_compression=0, audio_vae=None,
                use_custom_audio=False, inpaint_audio=True, use_custom_motion=True,
                override_audio=False, ref_image_size="match",
                shift_video=12.0, shift_audio=3.0, ref_images=None, ref_image_notes="",
                sampler=None, sigmas=None, noise_seed=0, window_seconds=5.0,
                tiled_vae_decode=False,
                start=None, end=None, duration=None) -> io.NodeOutput:

        mm = core()
        tdata = plan.parse_timeline(timeline_data)
        fps = float(frame_rate) if frame_rate else 24.0

        win_start, duration_frames = resolve_window(
            tdata, fps, start_frame, duration_frames, start, end, duration)

        # Chaining: a SAMPLER + SIGMAS turn this into an internal sample->decode->anchor
        # loop over the same timeline. Retake mode owns its own short window, so it always
        # takes the normal path.
        if sampler is not None and sigmas is not None and not plan.retake_state(tdata):
            return cls._execute_windowed(
                mm, tdata, timeline_data, fps, win_start, duration_frames, clip, vae,
                audio_vae, sampler, sigmas, int(noise_seed), float(window_seconds),
                model=model, model_ref2va=model_ref2va, global_prompt=global_prompt,
                use_custom_motion=use_custom_motion, use_custom_audio=use_custom_audio,
                override_audio=override_audio, ref_image_size=ref_image_size,
                shift_video=shift_video, shift_audio=shift_audio,
                custom_width=custom_width, custom_height=custom_height,
                resize_method=resize_method, divisible_by=divisible_by,
                img_compression=img_compression, ref_images=ref_images,
                ref_image_notes=ref_image_notes, tiled_vae_decode=tiled_vae_decode)

        extra_refs = 0
        if ref_images is not None:
            try:
                extra_refs = int(ref_images.shape[0])
            except Exception:
                extra_refs = 0

        p = plan.plan_timeline(tdata, win_start, duration_frames, fps,
                               global_prompt=global_prompt,
                               use_custom_motion=use_custom_motion,
                               use_custom_audio=use_custom_audio,
                               override_audio=override_audio,
                               extra_ref_image_count=extra_refs,
                               ref_image_notes=ref_image_notes)

        length = p["length"]
        if length > plan.TRAINED_MAX_FRAMES:
            log.warning("[MiniMaxDirector] %d frames (%.1fs) is past H3's trained range of "
                        "~%d-%d frames (~4-15s). Expect drift, looping or a VRAM wall — "
                        "shorten the timeline, or render it as several windows and splice "
                        "them together.",
                        length, p["actual_seconds"], plan.TRAINED_MIN_FRAMES,
                        plan.TRAINED_MAX_FRAMES)
        elif length < plan.TRAINED_MIN_FRAMES:
            log.info("[MiniMaxDirector] %d frames (%.1fs) is below H3's trained range "
                     "(~%d frames / 5s). Fine for tests, weaker motion than a full shot.",
                     length, p["actual_seconds"], plan.TRAINED_MIN_FRAMES)
        if p["prompt_is_fallback"]:
            log.warning("[MiniMaxDirector] No prompt text on the timeline — falling back to 'video'.")
        for warning in p.get("ref_warnings") or []:
            log.warning("[MiniMaxDirector] %s", warning)

        retake = p["retake"]

        # --- load the pixels the plan calls for ------------------------------------
        for ev in p["events"]:
            ev["tensor"] = _load_event_tensor(ev, fps, win_start)

        first_src = last_src = None
        if retake:
            # anchor on the base video's own frames either side of the marked range
            first_src = _grab_base_frame(retake["video"], retake["start"] - 1, fps)
            tail_index = retake["start"] + retake["length"]
            if not retake["base_frames"] or tail_index < retake["base_frames"]:
                last_src = _grab_base_frame(retake["video"], tail_index, fps)
            if first_src is None and last_src is None:
                log.warning("[MiniMaxDirector] Retake: could not read anchor frames from '%s' "
                            "— falling back to a plain text-to-video window.", retake["video"])
        else:
            for ev in p["events"]:
                if ev["role"] == plan.ROLE_FIRST:
                    first_src = ev["tensor"][:1]
                elif ev["role"] == plan.ROLE_LAST:
                    last_src = ev["tensor"][-1:]

        # --- canvas -----------------------------------------------------------------
        canvas_src = first_src
        if canvas_src is None:
            canvas_src = p["events"][0]["tensor"] if p["events"] else None
        width, height = resolve_canvas(mm, int(custom_width), int(custom_height),
                                       int(divisible_by), resize_method, canvas_src)

        # Core's PackedLayout divides by `math.sqrt(latent_h * latent_w)`, so a zero-edged
        # latent takes it down with a bare "float division by zero" six frames deep, naming
        # nothing that would lead back here. A slightly larger canvas clears that and then
        # fails inside the video VAE instead. Neither is reachable with the default
        # divisible_by of 32; custom_width=4 with divisible_by=1 is (issue #4).
        if width < MIN_CANVAS_EDGE or height < MIN_CANVAS_EDGE:
            raise ValueError(
                "MiniMax H3 Director: the canvas came out %dx%d. H3 needs at least %dpx per "
                "side — below that its VAE has nothing left to work with and the failure "
                "surfaces deep in ComfyUI as a division by zero. Raise custom_width / "
                "custom_height, or raise divisible_by (32 is H3's own step)."
                % (width, height, MIN_CANVAS_EDGE))

        def fit(tensor):
            out = media.resize_image(tensor, width, height, resize_method, int(divisible_by))
            if out.shape[1] != height or out.shape[2] != width:
                # A later image with a different aspect than the one that set the canvas.
                # The canvas is already fixed, so cover-crop it to match exactly — otherwise
                # the core node would stretch the keyframe and distort it.
                out = media.resize_image(out, width, height, "crop", int(divisible_by))
            if int(img_compression) > 0:
                out = media.compress_image(out, int(img_compression))
            return out

        first_frame = fit(first_src) if first_src is not None else None
        last_frame = fit(last_src) if last_src is not None else None

        # --- reference payloads ------------------------------------------------------
        ref_image_tensors, ref_videos, ref_video_audios, ref_audios = [], {}, {}, {}
        if p["ref_mode_on"]:
            input_cursor = 0
            for slot in p["ref_image_slots"]:
                src = slot["source"]
                if src == "char":
                    img = slot["image"]
                    ref_image_tensors.append(
                        media.load_image_source(img.get("b64", ""), img.get("name", "")))
                elif src == "input":
                    ref_image_tensors.append(ref_images[input_cursor:input_cursor + 1])
                    input_cursor += 1
                else:
                    ev = slot["event"]
                    tensor = ev["tensor"]
                    if slot.get("keyframe") == plan.ROLE_LAST:
                        ref_image_tensors.append(fit(tensor[-1:]))
                    elif slot.get("keyframe"):
                        ref_image_tensors.append(fit(tensor[:1]))
                    else:
                        ref_image_tensors.append(tensor[:1])

            for seg in p["ref_video_segs"]:
                idx = len(ref_videos)
                seg_start = float(seg.get("start", 0))
                seg_len = float(seg.get("length", 1))
                offset = max(0.0, win_start - seg_start)
                trim = float(seg.get("trimStart", 0)) + offset
                clip_sec = min(plan.REF_VIDEO_MAX_SEC,
                               max(plan.REF_VIDEO_MIN_SEC, (seg_len - offset) / fps))
                frames = media.load_video_tensor(seg["videoFile"], trim / fps, clip_sec)
                if frames.shape[0] < 5:
                    log.warning("[MiniMaxDirector] Reference video '%s' is shorter than 5 "
                                "frames — skipped.", seg.get("fileName", seg["videoFile"]))
                    continue
                ref_videos["ref_video_%d" % idx] = frames
                if override_audio:
                    clip_audio = media.load_audio_segment(
                        {"audioFile": seg["videoFile"], "trimStart": trim,
                         "length": clip_sec * fps}, fps, file_key="audioFile")
                    if clip_audio is not None:
                        ref_video_audios["ref_video_audio_%d" % idx] = clip_audio

            for seg in p["ref_audio_segs"]:
                clip_audio = media.load_audio_segment(seg, fps)
                if clip_audio is not None:
                    ref_audios["ref_audio_%d" % len(ref_audios)] = clip_audio

            if first_frame is not None or last_frame is not None:
                log.info("[MiniMaxDirector] ref2va has no first/last keyframe slot — the "
                         "timeline keyframes were added as <Picture i> references instead.")
                first_frame = last_frame = None

        prompt = p["prompt"]
        log.info("[MiniMaxDirector] %s%s | %dx%d | %d frames (%.2fs @24fps) | %d shots | "
                 "refs: %d img / %d vid / %d audio",
                 p["mode"], " (retake)" if retake else "", width, height, length,
                 p["actual_seconds"], len(p["shots"]),
                 len(ref_image_tensors), len(ref_videos), len(ref_audios))
        # The full storyboard is one to two screens of text; the node's `prompt` output and
        # the COMPILED PROMPT panel both show it, so keep it out of the console by default.
        log.debug("[MiniMaxDirector] prompt:\n%s", prompt)

        # --- conditioning ------------------------------------------------------------
        if p["ref_mode_on"]:
            if (ref_audios or ref_video_audios) and audio_vae is None:
                raise ValueError(
                    "MiniMax H3 Director: audio references need the audio VAE. Connect "
                    "minimax_h3_audio_vae to the Director's 'audio_vae' input (or turn off "
                    "the audio track / Override Audio)."
                )
            out = mm.MiniMaxH3ReferenceToVideo.execute(
                clip=clip, vae=vae, audio_vae=audio_vae, prompt=prompt,
                width=width, height=height, length=length,
                ref_image_size=ref_image_size,
                ref_images={"ref_image_%d" % i: t for i, t in enumerate(ref_image_tensors)} or None,
                ref_videos=ref_videos or None,
                ref_video_audios=ref_video_audios or None,
                ref_audios=ref_audios or None,
            )
        else:
            middles = [e for e in p["events"] if e["role"] == plan.ROLE_MIDDLE]
            if middles:
                log.warning("[MiniMaxDirector] %d timeline image(s) sit in the middle of the "
                            "window. H3 only anchors keyframes at the first and last frame, so "
                            "they were ignored — switch the toolbar to 'Refs ON (ref2va)' to "
                            "use them as <Picture i> references.", len(middles))
            out = mm.MiniMaxH3ImageToVideo.execute(
                clip=clip, vae=vae, prompt=prompt,
                width=width, height=height, length=length,
                first_frame=first_frame, last_frame=last_frame,
            )

        conditioning, latent = _unpack(out)[:2]

        chosen_model = pick_model(model, model_ref2va, p["ref_mode_on"])
        patched_model = _unpack(mm.MiniMaxH3SigmaShift.execute(
            model=chosen_model, shift_video=float(shift_video),
            shift_audio=float(shift_audio)))[0]

        audio_out = media.build_combined_audio(
            timeline_data, win_start,
            max(1, int(round(p["actual_seconds"] * fps))), fps, override_audio=override_audio)

        retake_info = ""
        if retake:
            retake_info = json.dumps({
                "base_video": retake["video"],
                "timeline_fps": fps,
                "start_frame": retake["start"],
                "length_frames": retake["length"],
                "base_frames": retake["base_frames"],
                "generated_frames": length,
                "generated_fps": MODEL_FPS,
                "width": int(width), "height": int(height),
            })

        gen_log = _build_gen_log(p, tdata, global_prompt, width, height, length, fps)

        return io.NodeOutput(patched_model, conditioning, latent, audio_out,
                             MODEL_FPS, int(width), int(height), int(length), gen_log,
                             retake_info, None, None)

    # -------------------------------------------------- chaining (long-form) execute

    @classmethod
    def _execute_windowed(cls, mm, tdata, timeline_data, fps, win_start, duration_frames,
                          clip, vae, audio_vae, sampler, sigmas, noise_seed, window_seconds,
                          model=None, model_ref2va=None, global_prompt="",
                          use_custom_motion=True, use_custom_audio=False,
                          override_audio=False, ref_image_size="match",
                          shift_video=12.0, shift_audio=3.0, custom_width=0,
                          custom_height=0, resize_method="crop", divisible_by=32,
                          img_compression=0, ref_images=None, ref_image_notes="",
                          tiled_vae_decode=False) -> io.NodeOutput:
        """Render the timeline as a chain of in-range windows, each opening on the previous
        window's last decoded frame. Samples internally (SAMPLER + SIGMAS) because window
        N+1's anchor does not exist until window N is decoded — a static graph cannot express
        that. Folded in from the withdrawn minimax_chain node."""
        sm = samplers()

        extra_refs = 0
        if ref_images is not None:
            try:
                extra_refs = int(ref_images.shape[0])
            except Exception:
                extra_refs = 0

        # H3 is trained for ~4-15s. A window below that snaps up on the frame grid (a 1s
        # request becomes ~1.6s), so short windows both seam constantly AND overshoot the
        # requested duration. Refuse anything under 4s no matter where the value came from —
        # ComfyUI has been seen handing an optional widget its min instead of its default.
        window_seconds = float(window_seconds)
        if window_seconds < 4.0:
            log.warning("[MiniMaxDirector] window_seconds=%.2fs is below H3's trained range — "
                        "using 5.0s. Short windows seam on every join and chop the audio.",
                        window_seconds)
            window_seconds = 5.0

        window_frames = max(1, int(round(window_seconds * fps)))
        # Keep every window inside H3's trained range, expressed in this timeline's frames.
        min_frames = max(1, int(round(plan.TRAINED_MIN_FRAMES * fps / MODEL_FPS)))
        max_frames = max(min_frames, int(round(plan.TRAINED_MAX_FRAMES * fps / MODEL_FPS)))
        windows = split_windows(max(1, int(duration_frames)), window_frames,
                                min_frames=min_frames, max_frames=max_frames)
        avg_span = (duration_frames / len(windows)) if windows else 0
        log.info("[MiniMaxDirector] chaining %d evenly-split window(s), ~%.2fs each, over %.2fs total.",
                 len(windows), avg_span / fps, duration_frames / fps)

        ref_mode_on = plan.ref_mode_from(tdata)
        chosen_model = pick_model(model, model_ref2va, ref_mode_on)
        patched_model = _unpack(mm.MiniMaxH3SigmaShift.execute(
            model=chosen_model, shift_video=float(shift_video),
            shift_audio=float(shift_audio)))[0]

        all_images, all_audio, window_prompts = [], [], []
        pending = []   # phase-1 stashes each window's latent; phase-2 decodes them all at once
        last_conditioning = last_latent = last_p = None
        prev_last = None
        width = height = None
        pbar = comfy.utils.ProgressBar(len(windows))

        for index, (offset, span) in enumerate(windows):
            comfy.model_management.throw_exception_if_processing_interrupted()
            cur_start = int(win_start) + offset

            p = plan.plan_timeline(tdata, cur_start, span, fps,
                                   global_prompt=global_prompt,
                                   use_custom_motion=use_custom_motion,
                                   use_custom_audio=use_custom_audio,
                                   override_audio=override_audio,
                                   extra_ref_image_count=extra_refs,
                                   ref_image_notes=ref_image_notes)
            last_p = p

            for ev in p["events"]:
                ev["tensor"] = _load_event_tensor(ev, fps, cur_start)

            first_src = last_src = None
            for ev in p["events"]:
                if ev["role"] == plan.ROLE_FIRST:
                    first_src = ev["tensor"][:1]
                elif ev["role"] == plan.ROLE_LAST:
                    last_src = ev["tensor"][-1:]

            if width is None:
                canvas_src = first_src if first_src is not None else (
                    p["events"][0]["tensor"] if p["events"] else None)
                width, height = resolve_canvas(
                    mm, int(custom_width), int(custom_height), int(divisible_by),
                    resize_method, canvas_src)
                if width < MIN_CANVAS_EDGE or height < MIN_CANVAS_EDGE:
                    raise ValueError(
                        "MiniMax H3 Director: the canvas came out %dx%d — below H3's %dpx "
                        "floor. Raise custom_width/height or divisible_by."
                        % (width, height, MIN_CANVAS_EDGE))

            def fit(t):
                out = media.resize_image(t, width, height, resize_method, int(divisible_by))
                if out.shape[1] != height or out.shape[2] != width:
                    out = media.resize_image(out, width, height, "crop", int(divisible_by))
                if int(img_compression) > 0:
                    out = media.compress_image(out, int(img_compression))
                return out

            # continuity: every window after the first opens on the previous last frame,
            # which outranks whatever the timeline put there
            if prev_last is not None:
                first_frame = prev_last
            else:
                first_frame = fit(first_src) if first_src is not None else None
            last_frame = fit(last_src) if last_src is not None else None

            window_prompts.append("[window %d | %s-%s] %s" % (
                index + 1, plan.fmt_seconds(offset / fps),
                plan.fmt_seconds((offset + span) / fps), p["prompt"]))

            if p["ref_mode_on"]:
                ref_image_tensors, ref_videos, ref_video_audios, ref_audios = [], {}, {}, {}
                input_cursor = 0
                for slot in p["ref_image_slots"]:
                    src = slot["source"]
                    if src == "char":
                        img = slot["image"]
                        ref_image_tensors.append(
                            media.load_image_source(img.get("b64", ""), img.get("name", "")))
                    elif src == "input" and ref_images is not None:
                        ref_image_tensors.append(ref_images[input_cursor:input_cursor + 1])
                        input_cursor += 1
                    elif src == "timeline":
                        ev = slot["event"]
                        tensor = ev["tensor"]
                        if slot.get("keyframe") == plan.ROLE_LAST:
                            ref_image_tensors.append(fit(tensor[-1:]))
                        elif slot.get("keyframe"):
                            ref_image_tensors.append(fit(tensor[:1]))
                        else:
                            ref_image_tensors.append(tensor[:1])
                for seg in p["ref_video_segs"]:
                    idx = len(ref_videos)
                    seg_start = float(seg.get("start", 0))
                    seg_len = float(seg.get("length", 1))
                    offs = max(0.0, cur_start - seg_start)
                    trim = float(seg.get("trimStart", 0)) + offs
                    clip_sec = min(plan.REF_VIDEO_MAX_SEC,
                                   max(plan.REF_VIDEO_MIN_SEC, (seg_len - offs) / fps))
                    frames = media.load_video_tensor(seg["videoFile"], trim / fps, clip_sec)
                    if frames.shape[0] < 5:
                        continue
                    ref_videos["ref_video_%d" % idx] = frames
                    if override_audio:
                        clip_audio = media.load_audio_segment(
                            {"audioFile": seg["videoFile"], "trimStart": trim,
                             "length": clip_sec * fps}, fps, file_key="audioFile")
                        if clip_audio is not None:
                            ref_video_audios["ref_video_audio_%d" % idx] = clip_audio
                for seg in p["ref_audio_segs"]:
                    # Each window references the slice of the audio track that lines up with
                    # ITS time range [cur_start, cur_start+span), the same way the video ref
                    # above is offset — otherwise every window styles its audio off the
                    # segment's opening instead of the part that actually plays then.
                    seg_start = float(seg.get("start", 0))
                    seg_len = float(seg.get("length", 1))
                    offs = max(0.0, cur_start - seg_start)
                    if offs >= seg_len:
                        continue  # segment ends before this window — nothing to reference
                    win_seg = dict(seg)
                    win_seg["trimStart"] = float(seg.get("trimStart", 0)) + offs
                    win_seg["length"] = max(1.0, min(seg_len - offs, float(span)))
                    clip_audio = media.load_audio_segment(win_seg, fps)
                    if clip_audio is not None:
                        ref_audios["ref_audio_%d" % len(ref_audios)] = clip_audio

                # anchor the window as a <Picture> reference when there is a free slot
                if first_frame is not None and len(ref_image_tensors) < plan.MAX_REF_IMAGES:
                    ref_image_tensors.append(first_frame)

                if (ref_audios or ref_video_audios) and audio_vae is None:
                    raise ValueError(
                        "MiniMax H3 Director: audio references need the audio VAE. Connect "
                        "minimax_h3_audio_vae to 'audio_vae'.")
                out = mm.MiniMaxH3ReferenceToVideo.execute(
                    clip=clip, vae=vae, audio_vae=audio_vae, prompt=p["prompt"],
                    width=width, height=height, length=p["length"],
                    ref_image_size=ref_image_size,
                    ref_images={"ref_image_%d" % i: t for i, t in enumerate(ref_image_tensors)} or None,
                    ref_videos=ref_videos or None,
                    ref_video_audios=ref_video_audios or None,
                    ref_audios=ref_audios or None)
            else:
                out = mm.MiniMaxH3ImageToVideo.execute(
                    clip=clip, vae=vae, prompt=p["prompt"], width=width, height=height,
                    length=p["length"], first_frame=first_frame, last_frame=last_frame)

            conditioning, latent = _unpack(out)[:2]
            last_conditioning = conditioning

            guider = _unpack(sm.BasicGuider.execute(
                model=patched_model, conditioning=conditioning))[0]
            noise = sm.Noise_RandomNoise(int(noise_seed) + index)
            sampled = _unpack(sm.SamplerCustomAdvanced.execute(
                noise=noise, guider=guider, sampler=sampler, sigmas=sigmas,
                latent_image=latent))[0]
            last_latent = sampled

            # Phase 1: recover ONLY the anchor (this window's last frame) so the next window
            # can open on it, and stash the latent. The full, memory-heavy decode is deferred
            # to phase 2 below — after the DiT is freed — which keeps decoding on the GPU
            # instead of spilling to CPU and exhausting system RAM.
            prev_last = _decode_anchor_frame(vae, sampled)
            pending.append({"latent": sampled, "index": index})

            log.info("[MiniMaxDirector] window %d/%d sampled (%s), anchor ready",
                     index + 1, len(windows), p["mode"])
            pbar.update(1)

        # --- Phase 2: free the DiT, then decode every window on the GPU ------------------
        # Sampling is done, so releasing the sampler model hands the VAE the whole card and
        # each full decode runs on the GPU instead of falling back to CPU (which pegged
        # system RAM and could hard-lock the machine). Freed ONCE here, not once per window.
        comfy.model_management.unload_all_models()
        comfy.model_management.soft_empty_cache()

        pbar2 = comfy.utils.ProgressBar(len(pending))
        for item in pending:
            comfy.model_management.throw_exception_if_processing_interrupted()
            images = _decode_video(vae, item["latent"], tiled=tiled_vae_decode)
            audio_chunk = None
            if audio_vae is not None:
                audio_chunk, sr = _audio_to_stereo(_decode_audio(audio_vae, item["latent"]))
                if audio_chunk is not None and sr != AUDIO_SR:
                    try:
                        import torchaudio
                        audio_chunk = torchaudio.functional.resample(audio_chunk, sr, AUDIO_SR)
                    except Exception:
                        pass

            # the opening frame of a chained window IS the previous window's last frame —
            # keeping both would stutter on every seam
            drop = 1 if item["index"] > 0 else 0
            if drop and images.shape[0] > 1:
                images = images[drop:]
                if audio_chunk is not None:
                    cut = int(round(drop / MODEL_FPS * AUDIO_SR))
                    audio_chunk = audio_chunk[:, cut:]

            all_images.append(images)
            if audio_chunk is not None:
                all_audio.append(audio_chunk)
            log.info("[MiniMaxDirector] window %d/%d decoded: %d frames",
                     item["index"] + 1, len(pending), images.shape[0])
            pbar2.update(1)

        out_images = torch.cat(all_images, dim=0)
        total = int(out_images.shape[0])
        if all_audio:
            # ~12ms equal-power cross-fade at each window seam kills the splice click.
            declicked = _concat_audio_declick(all_audio, int(round(0.012 * AUDIO_SR)))
            out_audio = declicked if declicked is not None else torch.cat(all_audio, dim=1)
        else:
            out_audio = torch.zeros(
                (2, max(1, int(round(total / MODEL_FPS * AUDIO_SR)))), dtype=torch.float32)

        # Build the timeline-audio mixdown to match the ACTUAL rendered length (windows snap
        # up on the frame grid, so the total drifts a little past what was requested). total
        # is output frames @24; build_combined_audio measures in timeline frames.
        audio_tl_frames = max(1, int(round(total / MODEL_FPS * fps)))
        combined_audio = media.build_combined_audio(
            timeline_data, int(win_start), audio_tl_frames, fps, override_audio=override_audio)

        gen_log = _build_gen_log(last_p or {}, tdata, global_prompt, width, height,
                                 total, fps, window_prompts=window_prompts)
        log.info("[MiniMaxDirector] chain finished: %d frames (%.2fs) at %dx%d",
                 total, total / MODEL_FPS, width, height)

        return io.NodeOutput(
            patched_model, last_conditioning, last_latent, combined_audio,
            MODEL_FPS, int(width), int(height), total, gen_log, "",
            out_images, {"waveform": out_audio.unsqueeze(0), "sample_rate": AUDIO_SR})


NODE_CLASS_MAPPINGS = {"MiniMaxH3DirectorCS": MiniMaxH3Director}
NODE_DISPLAY_NAME_MAPPINGS = {"MiniMaxH3DirectorCS": "MiniMax H3 Director"}
