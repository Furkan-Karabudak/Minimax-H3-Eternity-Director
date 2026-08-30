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
from .render_plan import (
    RENDER_PLAN_TYPE,
    create_render_plan,
    deserialize_render_plan,
    compile_iterations_from_cuts,
)

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


def resolve_size(custom_width, custom_height, width=None, height=None):
    """Let a connected `width`/`height` stand in for the settings panel's box.

    The panel owns `custom_width`/`custom_height` and hides them, so a resolution node
    had no reachable socket to drive them through (issue #14). These two sockets are the
    same automation pattern as start/end/duration, and they carry the same hazard: a
    widget has a minimum, a wire has none, and 0 is what an upstream node hands over when
    its own value was never set. Zero pixels is a mistake worth naming here rather than
    six frames deep in the VAE — leaving the socket unconnected is how you ask for a
    canvas derived from the first image.
    """
    for name, value in (("width", width), ("height", height)):
        if value is None:
            continue
        if int(value) <= 0:
            raise ValueError(
                "MiniMax H3 Director: the connected '%s' is %d. It is an output size in "
                "pixels and has to be positive. Leave the socket unconnected to derive "
                "the canvas from the first image instead, and check the node feeding it "
                "— a value that was never set arrives here as 0." % (name, int(value)))
    if width is not None:
        custom_width = int(width)
    if height is not None:
        custom_height = int(height)
    return int(custom_width), int(custom_height)


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


def load_ref_image_tensors(slots, fit, ref_images=None):
    """Turn the planner's <Picture i> slots into tensors, in the order it numbered them.

    The slot vocabulary is minimax_plan's, so this is the one place that has to know what
    "char" / "input" / "timeline" mean and which frame of a video segment a keyframe role
    picks out. The chain node grew its own copy of this loop and the two drifted: that one
    ignored the ref_images socket entirely and never fitted a keyframe to the canvas, so a
    chained render silently dropped references the Director would have sent.

    `fit` scales a tensor to the resolved canvas. Only real keyframes go through it — a
    plain reference is not composited into the video, so cropping it to the output aspect
    would throw away reference the model could have used.
    """
    tensors = []
    input_cursor = 0
    for slot in slots:
        source = slot["source"]
        if source == "char":
            img = slot["image"]
            tensors.append(media.load_image_source(img.get("b64", ""), img.get("name", "")))
        elif source == "input":
            # planned from a count the caller supplied, so an unconnected socket here means
            # the plan and the caller disagree — skip rather than index into nothing
            if ref_images is None:
                continue
            tensors.append(ref_images[input_cursor:input_cursor + 1])
            input_cursor += 1
        else:
            tensor = slot["event"]["tensor"]
            if slot.get("keyframe") == plan.ROLE_LAST:
                tensors.append(fit(tensor[-1:]))
            elif slot.get("keyframe"):
                tensors.append(fit(tensor[:1]))
            else:
                tensors.append(tensor[:1])
    return tensors


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
# long-form chaining helpers (fork addition — see CUSTOM_ADDITIONS.md)
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


def _concat_audio_aligned(chunks, overlap_samples):
    """Join per-window audio by cross-fading across the WHOLE window overlap — the fix for the
    seam dropping to near-silence when H3 follows an <Audio> reference.

    Diagnosis (from waveform analysis of a real 6-window render): each window's generated audio
    tapers to near-silence at its own temporal edges — the model is unsure at the very start
    and end of the ~5s it generates — so window N fades out at its tail while window N+1 fades
    in at its head. A short cross-fade lands *inside* that combined dead zone and you hear an
    ~18 ms hole punched in otherwise-loud music at every seam.

    The two windows overlap by exactly one model frame (window N+1 opens on window N's last
    frame — the anchor), and that frame is NOT pre-cut in aligned mode. Cross-fading with
    equal gain across that full one-frame overlap makes each window's LOUD middle cover the
    OTHER's tapered edge: at the start of the overlap the weight is on window N (loud, its
    taper hasn't begun), at the end it's on window N+1 (loud, its taper is done). The shared
    frame is consumed rather than doubled, and the hole is filled.

    It cannot make a seam invisible: two independently-generated windows genuinely diverge in
    content at the boundary (~0.46 correlation measured), so a mild blend dip remains — but the
    silence hole becomes a soft, brief dip instead of a stutter. The caller locks the total to
    the video length afterwards, so consuming one frame per seam cannot drift A/V."""
    chunks = [c for c in chunks if c is not None and c.shape[1] > 0]
    if not chunks:
        return None
    out = chunks[0]
    for nxt in chunks[1:]:
        f = int(min(max(1, overlap_samples), out.shape[1], nxt.shape[1]))
        if f <= 1:
            out = torch.cat([out, nxt], dim=1)
            continue
        # Equal-gain (linear), not equal-power: the overlap is the SAME song-time in both
        # windows (a duplicated frame), so this is a transition between two takes of one moment,
        # not a blend of two independent blocks — equal-gain keeps the level flat across it.
        r = torch.linspace(0.0, 1.0, f, dtype=out.dtype)
        head = out[:, :out.shape[1] - f]
        blend = out[:, out.shape[1] - f:] * (1.0 - r) + nxt[:, :f] * r
        out = torch.cat([head, blend, nxt[:, f:]], dim=1)
    return out


def _concat_audio_smartseam(chunks, overlaps, sr, fade_ms=20.0, gap_win_ms=20.0):
    """Join per-window waveforms, hiding each seam at the QUIETEST point in its overlap.

    Seamless mode co-denoises one clip, so window N and window N+1 carry the SAME song-time in
    their overlap: chunks[i]'s tail is the same moment as chunks[i+1]'s head. Two consequences:

      1. The splice does not have to sit at the overlap's geometric centre. That centre is
         content-blind and routinely lands on a loud vocal (measured: the geometric seam runs
         6-37 dB louder than the quietest point in the same overlap). We scan the overlap for the
         lowest short-time-RMS point of the two takes combined and put the seam there, where a cut
         is inaudible — the way a dialogue editor hides a splice in the gap between words.
      2. Because both sides are the same moment, a short equal-power cross-fade at that point
         splices cleanly instead of stuttering.

    chunks[i] : [2, Ni] decoded waveform for window i. overlaps[i] : how many samples chunks[i]
    and chunks[i+1] share (identical song-time). Returns [2, total]; the caller locks total to the
    video length, so consuming each overlap once cannot drift A/V.

    NOTE: a cross-correlation re-phase (WSOLA-lite) before the fade would further tighten the
    handful of seams that fall in continuous, gapless audio (no quiet point to hide in). Left out
    of v1 deliberately — the RMS-placement win is the large, measured one; xcorr is a refinement
    to add once this path is confirmed on a real render."""
    chunks = [c for c in chunks if c is not None and c.shape[1] > 0]
    if not chunks:
        return None
    out = chunks[0]
    for k in range(1, len(chunks)):
        nxt = chunks[k]
        ov = int(min(overlaps[k - 1], out.shape[1], nxt.shape[1]))
        if ov <= 2:
            out = torch.cat([out, nxt], dim=1)
            continue
        Lo = out.shape[1]
        a = out[:, Lo - ov:]        # accumulated tail (window k-1) over the overlap
        b = nxt[:, :ov]             # next window's head — same song-time as `a`
        # combined short-time energy of both takes; the seam wants to sit where BOTH are quiet
        sq = a.mean(0) ** 2 + b.mean(0) ** 2
        w = max(1, int(gap_win_ms * sr / 1000.0))
        if ov > 2 * w:
            cs = torch.cumsum(torch.nn.functional.pad(sq, (1, 0)), dim=0)
            env = (cs[w:] - cs[:-w]) / w                      # mean-sq over a sliding window
            s0 = int(torch.argmin(env).item()) + w // 2        # centre of the quietest window
        else:
            s0 = ov // 2
        f = int(min(fade_ms * sr / 1000.0, ov // 2))
        f = max(1, f)
        lo = min(max(s0 - f // 2, 0), ov - f)                  # clamp the fade inside the overlap
        ramp = torch.linspace(0.0, 1.0, f, dtype=out.dtype) * (torch.pi / 2.0)
        fo = torch.cos(ramp); fi = torch.sin(ramp)             # equal-power (constant energy)
        head = out[:, :Lo - ov + lo]
        blend = out[:, Lo - ov + lo:Lo - ov + lo + f] * fo + nxt[:, lo:lo + f] * fi
        out = torch.cat([head, blend, nxt[:, lo + f:]], dim=1)
    return out


def _seamless_indep_audio(audio_vae, indep, aranges, total):
    """Assemble the seamless clip's audio from INDEPENDENT per-window samples.

    The co-denoise poisons audio (audio latents can't be averaged like video, so they're
    hard-stitched in the shared latent and each window denoises its audio while seeing its
    neighbours' discontinuous audio — it compounds into tonal mush). Sampling each window on its
    own does not share the audio latent, so it stays clean. This decodes each independent window's
    audio and hands them to _concat_audio_smartseam, which hides each seam at the quietest point in
    the overlap. `indep[i]` is window i's independently-sampled latent (same object chained decodes
    per window). Returns [2, N] locked to the video length, or None to fall back."""
    if not indep or any(s is None for s in indep) or len(indep) != len(aranges):
        return None
    chunks, spfs, gas, nas = [], [], [], []
    for i, s in enumerate(indep):
        ga, na = aranges[i]
        wav, sr = _audio_to_stereo(_decode_audio(audio_vae, s))
        if wav is None:
            return None
        if sr != AUDIO_SR:
            try:
                import torchaudio
                wav = torchaudio.functional.resample(wav, sr, AUDIO_SR)
            except Exception:
                return None
        chunks.append(wav)
        spfs.append(wav.shape[1] / max(1, na))   # decoded samples per audio-latent frame
        gas.append(ga); nas.append(na)
    # overlap between consecutive windows, converted latent-frames -> samples
    overlaps = []
    for i in range(len(chunks) - 1):
        ov_frames = (gas[i] + nas[i]) - gas[i + 1]
        spf = (spfs[i] + spfs[i + 1]) / 2.0
        overlaps.append(max(0, int(round(ov_frames * spf))))
    out = _concat_audio_smartseam(chunks, overlaps, AUDIO_SR)
    if out is None:
        return None
    want = max(1, int(round(total / MODEL_FPS * AUDIO_SR)))   # lock to video length (no A/V drift)
    if out.shape[1] > want:
        out = out[:, :want]
    elif out.shape[1] < want:
        out = torch.nn.functional.pad(out, (0, want - out.shape[1]))
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
    """A human filename for one <Picture i> slot, for the generation log."""
    src = slot.get("source")
    if src == "char":
        return slot.get("image", {}).get("name", "") or "(subject slot)"
    if src == "input":
        return "(ref_images input)"
    ev = slot.get("event") or {}
    key = {plan.ROLE_FIRST: "first", plan.ROLE_LAST: "last"}.get(slot.get("keyframe"), "")
    name = ev.get("name") or ev.get("seg", {}).get("fileName", "") or "(timeline image)"
    return "%s%s" % (name, " [%s frame]" % key if key else "")


def _build_chain_log(tdata, first_p, windows, window_prompts, width, height, total, fps, long_mode="chained"):
    """A clean, saveable record of a long-form (chained) render.

    The shared context — style, subjects, references, audio — is written ONCE at the top
    (every window's compiled prompt repeats all of it, so a log that repeated it per window
    would be unreadable). Then each window's EXACT compiled prompt is listed below its label,
    so the record stays faithful to what H3 actually received. The single-window path returns
    upstream's compiled prompt directly and needs none of this."""
    first_p = first_p or {}
    L = ["==== MiniMax H3 Director — long-form generation log ===="]
    L.append("canvas %dx%d · %d frames (%.2fs @%.0ffps) · %s · %d %s window%s"
             % (width, height, total, total / MODEL_FPS, MODEL_FPS,
                first_p.get("mode", "?"), len(windows), long_mode, "" if len(windows) == 1 else "s"))

    def rule(title, dashes=24):
        L.append("")
        L.append("── %s %s" % (title, "─" * dashes))

    gp = (tdata.get("global_prompt", "") or tdata.get("retake_global_prompt", "") or "").strip()
    if gp:
        rule("STYLE (global)")
        L.append(gp)

    # subjects come from the timeline panel (source of truth); the reference ordinals come
    # from window 1's plan — the reference SET is global, so any window's is representative
    subs = tdata.get("subjects")
    if not isinstance(subs, list):
        subs = tdata.get("characters", []) or []
    slots = first_p.get("ref_image_slots") or []
    vids = first_p.get("ref_video_segs") or []
    auds = first_p.get("ref_audio_segs") or []
    if subs or slots or vids or auds:
        rule("SUBJECTS & REFERENCES", 16)
        for s in subs:
            desc = (s.get("description") or "").strip()
            if not desc:
                continue
            short = (s.get("shortName") or "").strip() or "subject"
            note = (s.get("retentionNote") or "").strip()
            L.append("  • %s (%s · %s) %s%s" % (
                short, plan.sanitize_kind(s.get("kind")),
                plan.sanitize_retention(s.get("retention")), desc,
                "  — %s" % note if note else ""))
        for i, slot in enumerate(slots):
            L.append("  <Picture %d>  %s" % (i + 1, _ref_slot_name(slot)))
        for i, seg in enumerate(vids):
            L.append("  <Video %d>    %s" % (i + 1, seg.get("fileName") or seg.get("videoFile", "")))
        for i, seg in enumerate(auds):
            L.append("  <Audio %d>    %s" % (i + 1, seg.get("fileName") or seg.get("audioFile", "")))

    soundscape = (tdata.get("overall_soundscape", "") or "").strip()
    music = (tdata.get("non_diegetic_music", "") or "").strip()
    if soundscape or music:
        rule("AUDIO", 32)
        if soundscape:
            L.append("  overall_soundscape: " + soundscape)
        if music:
            L.append("  non_diegetic_music: " + music)

    rule("WINDOWS — exact prompt sent to H3, per window", 4)
    for i, ((off, sp), wp) in enumerate(zip(windows, window_prompts)):
        L.append("")
        L.append("  ┌─ window %d/%d · %s–%s" % (
            i + 1, len(windows), plan.fmt_seconds(off / fps),
            plan.fmt_seconds((off + sp) / fps)))
        for line in (wp or "").splitlines():
            L.append("  │ " + line)
    return "\n".join(L)


# --------------------------------------------------------------------------------------
# seamless (temporal MultiDiffusion) helpers — see docs/SEAMLESS_LONGFORM_SPEC.md
# --------------------------------------------------------------------------------------
# These mirror H3's own latent geometry (comfy_extras/nodes_minimax_h3.py + ldm/minimax/model.py):
# 17 pixel frames <-> 5 video-latent frames (+2 base), audio linear at 40 latent-fps, and the
# per-token temporal spans keyed to k%5. `_globalcoord` is the exclusive cumsum of those spans,
# which is also (numerically) the global audio-latent frame index. Validated in
# docs/seamless_positioning_poc.py.

_H3_FRAME_PER_TOKEN = (1, 4, 4, 4, 4)
_H3_FRAME_RESCALE = 5.0 / 3.0


def _co_align(n):
    """Snap a pixel frame count up to H3's 17k+5 grid."""
    while n % 17 != 5:
        n += 1
    return n


def _co_vlt(frame_count):
    """Pixel frame count -> video-latent frame count."""
    return 2 if frame_count <= 5 else ((frame_count - 5) // 17) * 5 + 2


def _globalcoord(gv):
    """Global RoPE temporal coordinate of video-latent frame `gv` (exclusive cumsum of spans).
    Numerically equals the global audio-latent frame index (both ~28.33 per 5-frame block)."""
    return float(sum(_H3_FRAME_RESCALE * _H3_FRAME_PER_TOKEN[k % 5] for k in range(int(gv))))


def _plan_co_windows(tv, win_lat, overlap_lat):
    """Overlapping co-denoise windows over [0, tv) video-latent frames. Every start is snapped to
    a 5-latent (17-pixel) block boundary so the k%5 span phase matches the global grid — required
    for overlapping windows to share identical positions (the PoC's block-alignment rule)."""
    win_lat = min(win_lat, tv)
    stride = max(5, ((max(1, win_lat - overlap_lat)) // 5) * 5)
    starts, g = [], 0
    while True:
        if g + win_lat >= tv:
            last = max(0, ((tv - win_lat) // 5) * 5)
            if last not in starts:
                starts.append(last)
            break
        starts.append(g)
        g += stride
    return [(s, min(win_lat, tv - s)) for s in starts]


# --------------------------------------------------------------------------------------
# node
# --------------------------------------------------------------------------------------

class MiniMaxH3Director(io.ComfyNode):
    """Timeline editor -> MiniMax H3 storyboard conditioning + joint AV latent."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="H3Eternity_Director",
            display_name="H3 Eternity - Director",
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
                io.Custom(RENDER_PLAN_TYPE).Input("render_plan", optional=True,
                                tooltip="Active render_plan from H3 Eternity - Start or previous node."),
                io.Model.Input("model", display_name="model (t2v/i2v)", optional=True, lazy=True,
                               tooltip="The fl2va weights (minimax_h3_fl2va_*), used when the "
                                       "toolbar is on 'Refs OFF'. Connect both models and the "
                                       "node loads whichever the toolbar switch calls for — "
                                       "the other one is never read from disk."),
                io.Model.Input("model_ref2va", display_name="model (ref2v)", optional=True, lazy=True,
                               tooltip="The ref2va weights (minimax_h3_ref2va_*), used when the "
                                       "toolbar is on 'Refs ON'. Optional — with only one model "
                                       "connected that one is used either way."),
                io.Clip.Input("clip", optional=True, tooltip="Qwen3-VL-32B MiniMax text encoder (CLIPLoader type 'minimax')."),
                io.Vae.Input("vae", optional=True, tooltip="minimax_h3_video_vae — encodes keyframes and references."),
                io.Vae.Input("audio_vae", optional=True,
                             tooltip="minimax_h3_audio_vae. Only needed when audio references are used (ref2va)."),
                io.String.Input(
                    "global_prompt", multiline=True, default="", force_input=True, optional=True,
                    tooltip="Conditions the whole video: style, scene, characters. Written above the storyboard.",
                ),
                io.Image.Input("ref_images", optional=True,
                               tooltip="Extra <Picture i> references (single image or batch), appended after the "
                                       "character slots. ref2va only."),
                io.Float.Input("start", force_input=True, optional=True, default=0.0,
                               tooltip="Automation (connection-only). Window start in SECONDS."),
                io.Float.Input("end", force_input=True, optional=True, default=0.0,
                               tooltip="Automation (connection-only). Window end in SECONDS."),
                io.Float.Input("duration", force_input=True, optional=True, default=0.0,
                               tooltip="Automation (connection-only). Render length in SECONDS."),
                io.Int.Input("width", force_input=True, optional=True, default=0,
                             tooltip="Automation (connection-only). Output width in pixels, "
                                     "overriding the settings panel's Width. Wire a resolution "
                                     "node here; leave it unconnected to use the panel."),
                io.Int.Input("height", force_input=True, optional=True, default=0,
                             tooltip="Automation (connection-only). Output height. See width."),
                io.String.Input("ref_image_notes", multiline=True, default="", optional=True,
                                tooltip="One line per image on 'ref_images', describing what it "
                                        "is: 'the kitchen set', 'a storyboard reference for the "
                                        "opening'. Without a line the picture is still numbered "
                                        "but the prompt says nothing about it. Blank lines count, "
                                        "so line 3 always belongs to the third image."),
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
            ],
            outputs=[
                io.Custom(RENDER_PLAN_TYPE).Output(display_name="render_plan",
                                                   tooltip="Active render_plan carrying timeline cuts, iteration definitions, and metadata."),
                io.Model.Output(display_name="model"),
                io.Conditioning.Output(display_name="positive"),
                io.Latent.Output(display_name="latent", tooltip="Joint video+audio latent. Wire to SamplerCustomAdvanced or H3 Eternity - Sampler."),
                io.Audio.Output(display_name="combined_audio",
                                tooltip="Timeline audio mixdown. Wire into CreateVideo / H3 Eternity - Finalize to replace the generated audio."),
                io.Float.Output(display_name="fps", tooltip="Always 24.0 — H3's native output rate. Wire into CreateVideo."),
                io.Int.Output(display_name="width"),
                io.Int.Output(display_name="height"),
                io.Int.Output(display_name="length", tooltip="Frame count actually generated (snapped to the 17k+5 grid)."),
                io.String.Output(display_name="prompt", tooltip="The compiled storyboard prompt that was encoded."),
                io.String.Output(display_name="retake_info",
                                 tooltip="JSON describing the retake window. Wire into MiniMax H3 Retake Stitch "
                                         "to splice the result back into the base video. Empty when retake is off."),
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
                render_plan=None,
                sampler=None, sigmas=None, noise_seed=0, window_seconds=5.0,
                tiled_vae_decode=False, seam_audio="aligned",
                long_form_mode="chained", overlap_seconds=2.0,
                start=None, end=None, duration=None,
                width=None, height=None, **kwargs) -> io.NodeOutput:

        mm = core()
        tdata = plan.parse_timeline(timeline_data)
        fps = float(frame_rate) if frame_rate else 24.0

        win_start, duration_frames = resolve_window(
            tdata, fps, start_frame, duration_frames, start, end, duration)
        # resolved here, next to the window, so both automation paths are refused in the
        # same place — and before `width`/`height` are reused for the resolved canvas
        box_w, box_h = resolve_size(custom_width, custom_height, width, height)

        # --- long-form chaining (fork addition) -------------------------------------
        # A sampler + sigmas wired in means "render the whole timeline as chained windows,
        # sampling internally". Retake is single-window by definition (it splices one marked
        # range back into a base video), so it always takes the normal path below.
        if sampler is not None and sigmas is not None and not plan.retake_state(tdata):
            if long_form_mode == "seamless":
                return cls._execute_seamless(
                    mm, tdata, timeline_data, fps, win_start, duration_frames,
                    clip, vae, audio_vae, sampler, sigmas, noise_seed, window_seconds,
                    overlap_seconds, model=model, model_ref2va=model_ref2va,
                    global_prompt=global_prompt, use_custom_motion=use_custom_motion,
                    use_custom_audio=use_custom_audio, override_audio=override_audio,
                    ref_image_size=ref_image_size, shift_video=shift_video, shift_audio=shift_audio,
                    box_w=box_w, box_h=box_h, resize_method=resize_method,
                    divisible_by=divisible_by, img_compression=img_compression,
                    ref_images=ref_images, ref_image_notes=ref_image_notes,
                    tiled_vae_decode=tiled_vae_decode)
            return cls._execute_windowed(
                mm, tdata, timeline_data, fps, win_start, duration_frames,
                clip, vae, audio_vae, sampler, sigmas, noise_seed, window_seconds,
                model=model, model_ref2va=model_ref2va, global_prompt=global_prompt,
                use_custom_motion=use_custom_motion, use_custom_audio=use_custom_audio,
                override_audio=override_audio, ref_image_size=ref_image_size,
                shift_video=shift_video, shift_audio=shift_audio,
                box_w=box_w, box_h=box_h, resize_method=resize_method,
                divisible_by=divisible_by, img_compression=img_compression,
                ref_images=ref_images, ref_image_notes=ref_image_notes,
                tiled_vae_decode=tiled_vae_decode, seam_audio=seam_audio)

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
            # Not a limit and never was: nothing here caps the length, and longer windows
            # do render (issue #12). What leaves the model card's 4-15s envelope is the
            # quality, and the clock — attention is quadratic in sequence length, so the
            # render time climbs faster than the video does.
            log.warning("[MiniMaxDirector] %d frames (%.1fs) is past H3's trained range of "
                        "~%d-%d frames (the model card's 4-15s). It renders — expect drift "
                        "or looping, and a render time that climbs faster than the length. "
                        "For a dependable result shorten the timeline, or render it as "
                        "several windows and splice them together.",
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
        width, height = resolve_canvas(mm, box_w, box_h,
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
            ref_image_tensors = load_ref_image_tensors(p["ref_image_slots"], fit, ref_images)

            for seg in p["ref_video_segs"]:
                idx = len(ref_videos)
                seg_start = float(seg.get("start", 0))
                seg_len = float(seg.get("length", 1))
                offset = max(0.0, win_start - seg_start)
                trim = float(seg.get("trimStart", 0)) + offset
                # The segment's own length is the answer, capped only at the model card's
                # ceiling. It used to be floored at 2s as well, which meant trimming a clip
                # shorter than that silently handed the VAE *more* than was asked for —
                # the opposite of what someone trimming it down is trying to do. The
                # planner already warns when a clip is under the card's 2s minimum.
                clip_sec = min(plan.REF_VIDEO_MAX_SEC, (seg_len - offset) / fps)
                # Reference frames are VAE-encoded whole and then ride through every
                # sampling step, so their resolution is the largest single lever on memory:
                # halving the short edge is roughly a quarter of the footprint. Per clip,
                # because one reference may be carrying a look worth the pixels while
                # another is only carrying a camera move.
                short_edge = int(seg.get("refSize") or plan.REF_VIDEO_SHORT_EDGE)
                frames = media.load_video_tensor(
                    seg["videoFile"], trim / fps, clip_sec,
                    max_short_edge=short_edge,
                    max_pixels=int(short_edge * short_edge * plan.REF_VIDEO_ASPECT_BUDGET))
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

        # --- Synchronize or Initialize render_plan ---
        cuts_data = tdata.get("cuts", []) if isinstance(tdata, dict) else []
        total_timeline_frames = int(tdata.get("normalDurationFrames", duration_frames)) if isinstance(tdata, dict) else int(duration_frames)
        if render_plan is None:
            rplan = create_render_plan(
                node_id="director",
                width=int(width),
                height=int(height),
                fps=fps,
                total_frames=total_timeline_frames,
                cuts=cuts_data,
            )
        else:
            rplan = deserialize_render_plan(render_plan)
            rplan["width"] = int(width)
            rplan["height"] = int(height)
            rplan["fps"] = fps
            rplan["total_frames"] = total_timeline_frames
            rplan["cuts"] = cuts_data
            rplan["iterations"] = compile_iterations_from_cuts(
                total_frames=total_timeline_frames,
                cuts=cuts_data,
                fps=fps,
            )
            rplan["total_iterations"] = len(rplan["iterations"])

        return io.NodeOutput(rplan, patched_model, conditioning, latent, audio_out,
                             MODEL_FPS, int(width), int(height), int(length), prompt,
                             retake_info)

    # ------------------------------------------------------ long-form chaining

    @classmethod
    def _execute_windowed(cls, mm, tdata, timeline_data, fps, win_start, duration_frames,
                          clip, vae, audio_vae, sampler, sigmas, noise_seed, window_seconds,
                          model=None, model_ref2va=None, global_prompt="",
                          use_custom_motion=True, use_custom_audio=False, override_audio=False,
                          ref_image_size="match", shift_video=12.0, shift_audio=3.0,
                          box_w=0, box_h=0, resize_method="crop", divisible_by=32,
                          img_compression=0, ref_images=None, ref_image_notes="",
                          tiled_vae_decode=False, seam_audio="aligned") -> io.NodeOutput:
        """Render the whole render range as a chain of windows, sampling internally.

        Each window opens on the previous window's decoded last frame, which is a tensor that
        only exists after that window is sampled and decoded — so it cannot be expressed as a
        static graph and the sampling has to live here. Two-phase decode (anchor-only in the
        loop while the DiT is resident, full decode once after it is freed) keeps every decode
        on the GPU instead of spilling to CPU and exhausting system RAM on a long chain."""
        sm = samplers()

        if window_seconds < 4.0:
            log.warning("[MiniMaxDirector] window_seconds=%.2f is below H3's 4s trained floor "
                        "— using 5.0.", window_seconds)
            window_seconds = 5.0
        window_frames = max(1, int(round(window_seconds * fps)))
        # H3's trained 4-15s range, expressed in TIMELINE frames (windows are cut in timeline
        # frames, then each window's own plan snaps its length to the 24fps model grid).
        min_frames = max(1, int(round(plan.TRAINED_MIN_FRAMES * fps / MODEL_FPS)))
        max_frames = int(round(plan.TRAINED_MAX_FRAMES * fps / MODEL_FPS))
        windows = split_windows(duration_frames, window_frames, min_frames, max_frames)
        log.info("[MiniMaxDirector] long-form: %d frames -> %d window(s) of ~%.2fs",
                 duration_frames, len(windows), window_seconds)

        extra_refs = 0
        if ref_images is not None:
            try:
                extra_refs = int(ref_images.shape[0])
            except Exception:
                extra_refs = 0

        chosen_model = pick_model(model, model_ref2va, plan.ref_mode_from(tdata))
        patched_model = _unpack(mm.MiniMaxH3SigmaShift.execute(
            model=chosen_model, shift_video=float(shift_video),
            shift_audio=float(shift_audio)))[0]

        all_images, all_audio, window_prompts = [], [], []
        pending = []
        first_p = None
        last_conditioning = last_latent = None
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
            window_prompts.append(p["prompt"])
            if first_p is None:
                first_p = p

            for ev in p["events"]:
                ev["tensor"] = _load_event_tensor(ev, fps, cur_start)

            first_src = last_src = None
            for ev in p["events"]:
                if ev["role"] == plan.ROLE_FIRST:
                    first_src = ev["tensor"][:1]
                elif ev["role"] == plan.ROLE_LAST:
                    last_src = ev["tensor"][-1:]

            # canvas is fixed by the first window and held for the whole chain — a mid-chain
            # resolution change would break continuity and the frame concat at the end
            if width is None:
                canvas_src = first_src if first_src is not None else (
                    p["events"][0]["tensor"] if p["events"] else None)
                width, height = resolve_canvas(
                    mm, box_w, box_h, int(divisible_by), resize_method, canvas_src)
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

            # continuity: every window after the first opens on the previous window's last
            # frame, which outranks whatever the timeline put at this window's start
            if prev_last is not None:
                first_frame = prev_last
            else:
                first_frame = fit(first_src) if first_src is not None else None
            last_frame = fit(last_src) if last_src is not None else None

            if p["ref_mode_on"]:
                ref_image_tensors = load_ref_image_tensors(p["ref_image_slots"], fit, ref_images)
                ref_videos, ref_video_audios, ref_audios = {}, {}, {}

                for seg in p["ref_video_segs"]:
                    idx = len(ref_videos)
                    seg_start = float(seg.get("start", 0))
                    seg_len = float(seg.get("length", 1))
                    offs = max(0.0, cur_start - seg_start)
                    trim = float(seg.get("trimStart", 0)) + offs
                    clip_sec = min(plan.REF_VIDEO_MAX_SEC, (seg_len - offs) / fps)
                    short_edge = int(seg.get("refSize") or plan.REF_VIDEO_SHORT_EDGE)
                    frames = media.load_video_tensor(
                        seg["videoFile"], trim / fps, clip_sec,
                        max_short_edge=short_edge,
                        max_pixels=int(short_edge * short_edge * plan.REF_VIDEO_ASPECT_BUDGET))
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
                    # Each window references the slice of the audio track lined up with ITS
                    # time range [cur_start, cur_start+span), the same way the video ref above
                    # is offset — otherwise every window styles its audio off the segment's
                    # opening instead of the part that actually plays then.
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
            # to phase 2 — after the DiT is freed — which keeps decoding on the GPU instead of
            # spilling to CPU and exhausting system RAM.
            prev_last = _decode_anchor_frame(vae, sampled)
            pending.append({"latent": sampled, "index": index})

            log.info("[MiniMaxDirector] window %d/%d sampled (%s), anchor ready",
                     index + 1, len(windows), p["mode"])
            pbar.update(1)

        # --- Phase 2: free the DiT, then decode every window on the GPU ------------------
        # Sampling is done, so releasing the sampler model hands the VAE the whole card and
        # each full decode runs on the GPU instead of falling back to CPU (which pegged system
        # RAM and could hard-lock the machine). Freed ONCE here, not once per window.
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
            # keeping both would stutter on every seam. Video always drops it. Audio drops the
            # matching samples too EXCEPT in 'aligned' mode, where the correlation splice finds
            # the real overlap itself (a fixed cut here can skip real song when the generated
            # audio doesn't overlap by exactly one frame).
            drop = 1 if item["index"] > 0 else 0
            if drop and images.shape[0] > 1:
                images = images[drop:]
                if audio_chunk is not None and seam_audio != "aligned":
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
        want_audio = max(1, int(round(total / MODEL_FPS * AUDIO_SR)))
        if all_audio:
            if seam_audio == "aligned":
                # Cross-fade across the whole one-frame window overlap so each window's loud
                # middle covers the other's tapered (near-silent) edge — the fix for a seam
                # dropping out when H3 follows an <Audio> reference. Audio is NOT pre-cut per
                # window (see the decode loop), so the full overlap is still present to fade over.
                out_audio = _concat_audio_aligned(all_audio, int(round(AUDIO_SR / MODEL_FPS)))
            elif seam_audio == "crossfade":
                # Fixed ~12ms equal-power blend — coherent-but-not-identical audio.
                out_audio = _concat_audio_declick(all_audio, int(round(0.012 * AUDIO_SR)))
            else:  # "hard cut" — independent takes, any blend smears two unrelated textures
                out_audio = torch.cat(all_audio, dim=1)
            if out_audio is None:
                out_audio = torch.cat(all_audio, dim=1)
            # Lock length to the video: 'aligned' trims a variable few ms per seam, so pin the
            # end so A/V cannot drift (trim overrun, pad a shortfall with silence).
            if out_audio.shape[1] > want_audio:
                out_audio = out_audio[:, :want_audio]
            elif out_audio.shape[1] < want_audio:
                out_audio = torch.cat(
                    [out_audio, torch.zeros((out_audio.shape[0], want_audio - out_audio.shape[1]),
                                            dtype=out_audio.dtype)], dim=1)
        else:
            out_audio = torch.zeros((2, want_audio), dtype=torch.float32)

        # Build the timeline-audio mixdown to match the ACTUAL rendered length (windows snap
        # up on the frame grid, so the total drifts a little past what was requested). total
        # is output frames @24; build_combined_audio measures in timeline frames.
        audio_tl_frames = max(1, int(round(total / MODEL_FPS * fps)))
        combined_audio = media.build_combined_audio(
            timeline_data, int(win_start), audio_tl_frames, fps, override_audio=override_audio)

        prompt_txt = _build_chain_log(tdata, first_p, windows, window_prompts,
                                      width, height, total, fps)

        log.info("[MiniMaxDirector] chain finished: %d frames (%.2fs) at %dx%d",
                 total, total / MODEL_FPS, width, height)

        return io.NodeOutput(
            patched_model, last_conditioning, last_latent, combined_audio,
            MODEL_FPS, int(width), int(height), total, prompt_txt, "",
            out_images, {"waveform": out_audio.unsqueeze(0), "sample_rate": AUDIO_SR})

    # ----------------------------------------------- seamless (temporal MultiDiffusion)

    @staticmethod
    def _seamless_payload(meta):
        """Rebuild the minimax_payload the model forward expects from a window's conditioning
        metadata — mirrors comfy/model_base.py MiniMaxH3.extra_conds exactly."""
        payload = {}
        if meta.get("minimax_token_tags") is not None:
            payload["text_token_tags"] = meta["minimax_token_tags"]
        kf = meta.get("minimax_keyframes")
        if kf is not None:
            payload["keyframes"] = kf
            payload["frame_count"] = meta.get("minimax_frame_count")
            payload["cond_video_latents"] = [k["latent"] for k in kf]
        refs = meta.get("minimax_refs")
        if refs is not None:
            payload["refs"] = refs
            payload["cond_video_latents"] = [r["latent"] for r in refs if "latent" in r]
            payload["cond_audio_latents"] = [r["audio_latent"] for r in refs
                                             if r.get("audio_latent") is not None]
        if meta.get("minimax_visual_cond_noise_aug") is not None:
            payload["visual_cond_noise_aug"] = meta["minimax_visual_cond_noise_aug"]
        if meta.get("minimax_audio_cond_noise_aug") is not None:
            payload["audio_cond_noise_aug"] = meta["minimax_audio_cond_noise_aug"]
        return payload

    @classmethod
    def _execute_seamless(cls, mm, tdata, timeline_data, fps, win_start, duration_frames,
                          clip, vae, audio_vae, sampler, sigmas, noise_seed, window_seconds,
                          overlap_seconds, model=None, model_ref2va=None, global_prompt="",
                          use_custom_motion=True, use_custom_audio=False, override_audio=False,
                          ref_image_size="match", shift_video=12.0, shift_audio=3.0,
                          box_w=0, box_h=0, resize_method="crop", divisible_by=32,
                          img_compression=0, ref_images=None, ref_image_notes="",
                          tiled_vae_decode=False) -> io.NodeOutput:
        """Temporal MultiDiffusion: ONE full-clip latent, co-denoised over overlapping windows,
        each window conditioned on its OWN time-slice (the fix for whole-clip muddy audio). The
        overlaps are averaged every step so windows converge — no stitch, no seam. See
        docs/SEAMLESS_LONGFORM_SPEC.md."""
        import comfy.ldm.minimax.model as h3m
        sm = samplers()

        extra_refs = 0
        if ref_images is not None:
            try:
                extra_refs = int(ref_images.shape[0])
            except Exception:
                extra_refs = 0

        # --- canvas + full-clip latent from the whole-timeline plan --------------------
        whole = plan.plan_timeline(tdata, win_start, duration_frames, fps,
                                   global_prompt=global_prompt, use_custom_motion=use_custom_motion,
                                   use_custom_audio=use_custom_audio, override_audio=override_audio,
                                   extra_ref_image_count=extra_refs, ref_image_notes=ref_image_notes)
        for ev in whole["events"]:
            ev["tensor"] = _load_event_tensor(ev, fps, win_start)
        first_src = None
        for ev in whole["events"]:
            if ev["role"] == plan.ROLE_FIRST:
                first_src = ev["tensor"][:1]
                break
        canvas_src = first_src if first_src is not None else (
            whole["events"][0]["tensor"] if whole["events"] else None)
        width, height = resolve_canvas(mm, box_w, box_h, int(divisible_by), resize_method, canvas_src)
        if width < MIN_CANVAS_EDGE or height < MIN_CANVAS_EDGE:
            raise ValueError("MiniMax H3 Director: canvas %dx%d below the %dpx floor."
                             % (width, height, MIN_CANVAS_EDGE))

        def fit(t):
            out = media.resize_image(t, width, height, resize_method, int(divisible_by))
            if out.shape[1] != height or out.shape[2] != width:
                out = media.resize_image(out, width, height, "crop", int(divisible_by))
            if int(img_compression) > 0:
                out = media.compress_image(out, int(img_compression))
            return out

        length = whole["length"]
        if whole["ref_mode_on"]:
            full_out = mm.MiniMaxH3ReferenceToVideo.execute(
                clip=clip, vae=vae, audio_vae=audio_vae, prompt=whole["prompt"],
                width=width, height=height, length=length, ref_image_size=ref_image_size)
        else:
            full_out = mm.MiniMaxH3ImageToVideo.execute(
                clip=clip, vae=vae, prompt=whole["prompt"], width=width, height=height, length=length)
        full_cond, full_latent = _unpack(full_out)[:2]
        tv = int(list(full_latent["samples"].unbind())[0].shape[2])

        # --- co-denoise window schedule (video-latent frames, block-aligned) -----------
        win_lat = _co_vlt(_co_align(max(5, int(round(window_seconds * fps)))))
        ov_lat = max(1, _co_vlt(_co_align(max(1, int(round(overlap_seconds * fps))))))
        windows = _plan_co_windows(tv, win_lat, ov_lat)
        log.info("[MiniMaxSeamless] full=%d vlat · win=%d · ov=%d · %d windows: %s",
                 tv, win_lat, ov_lat, len(windows),
                 ", ".join("[%d,%d)" % (s, s + n) for s, n in windows))

        chosen_model = pick_model(model, model_ref2va, plan.ref_mode_from(tdata))
        patched_model = _unpack(mm.MiniMaxH3SigmaShift.execute(
            model=chosen_model, shift_video=float(shift_video), shift_audio=float(shift_audio)))[0]

        # --- per-window conditioning (each window's own time-slice) --------------------
        win_conds, window_prompts, log_windows, first_p = [], [], [], None
        for (gv, nv) in windows:
            cur_start = int(win_start) + int(round(gv / max(1, tv) * duration_frames))
            span = max(1, int(round(nv / max(1, tv) * duration_frames)))
            log_windows.append((cur_start - int(win_start), span))
            p = plan.plan_timeline(tdata, cur_start, span, fps, global_prompt=global_prompt,
                                   use_custom_motion=use_custom_motion, use_custom_audio=use_custom_audio,
                                   override_audio=override_audio, extra_ref_image_count=extra_refs,
                                   ref_image_notes=ref_image_notes)
            window_prompts.append(p["prompt"])
            if first_p is None:
                first_p = p
            for ev in p["events"]:
                ev["tensor"] = _load_event_tensor(ev, fps, cur_start)
            if p["ref_mode_on"]:
                ref_image_tensors = load_ref_image_tensors(p["ref_image_slots"], fit, ref_images)
                ref_videos, ref_video_audios, ref_audios = {}, {}, {}
                for seg in p["ref_video_segs"]:
                    idx = len(ref_videos)
                    seg_start = float(seg.get("start", 0)); seg_len = float(seg.get("length", 1))
                    offset = max(0.0, cur_start - seg_start)
                    trim = float(seg.get("trimStart", 0)) + offset
                    clip_sec = min(plan.REF_VIDEO_MAX_SEC, (seg_len - offset) / fps)
                    short_edge = int(seg.get("refSize") or plan.REF_VIDEO_SHORT_EDGE)
                    frames = media.load_video_tensor(
                        seg["videoFile"], trim / fps, clip_sec, max_short_edge=short_edge,
                        max_pixels=int(short_edge * short_edge * plan.REF_VIDEO_ASPECT_BUDGET))
                    if frames.shape[0] < 5:
                        continue
                    ref_videos["ref_video_%d" % idx] = frames
                    if override_audio:
                        ca = media.load_audio_segment(
                            {"audioFile": seg["videoFile"], "trimStart": trim,
                             "length": clip_sec * fps}, fps, file_key="audioFile")
                        if ca is not None:
                            ref_video_audios["ref_video_audio_%d" % idx] = ca
                for seg in p["ref_audio_segs"]:
                    seg_start = float(seg.get("start", 0)); seg_len = float(seg.get("length", 1))
                    offs = max(0.0, cur_start - seg_start)
                    if offs >= seg_len:
                        continue
                    win_seg = dict(seg)
                    win_seg["trimStart"] = float(seg.get("trimStart", 0)) + offs
                    win_seg["length"] = max(1.0, min(seg_len - offs, float(span)))
                    ca = media.load_audio_segment(win_seg, fps)
                    if ca is not None:
                        ref_audios["ref_audio_%d" % len(ref_audios)] = ca
                if (ref_audios or ref_video_audios) and audio_vae is None:
                    raise ValueError("MiniMax H3 Director: audio references need the audio VAE.")
                out = mm.MiniMaxH3ReferenceToVideo.execute(
                    clip=clip, vae=vae, audio_vae=audio_vae, prompt=p["prompt"],
                    width=width, height=height, length=p["length"], ref_image_size=ref_image_size,
                    ref_images={"ref_image_%d" % i: t for i, t in enumerate(ref_image_tensors)} or None,
                    ref_videos=ref_videos or None, ref_video_audios=ref_video_audios or None,
                    ref_audios=ref_audios or None)
            else:
                out = mm.MiniMaxH3ImageToVideo.execute(
                    clip=clip, vae=vae, prompt=p["prompt"], width=width, height=height, length=p["length"])
            unpacked = _unpack(out)
            cond = unpacked[0]
            ctx = cond[0][0]
            meta = cond[0][1] if len(cond[0]) > 1 else {}
            # Keep each window's own conditioning + latent. The seamless co-denoise poisons the
            # AUDIO (hard-stitched audio latents confuse each window's denoise into tonal mush), so
            # audio is re-sampled per window INDEPENDENTLY below — the one thing that comes out
            # clean — and only the VIDEO is taken from the co-denoise.
            win_conds.append({"context": ctx, "meta": meta, "text_len": int(ctx.shape[1]),
                              "gv": gv, "nv": nv, "cond": cond, "latent": unpacked[1]})

        # Audio ownership: audio latents CANNOT be averaged the way video can — blending two
        # windows' audio (each following a different slice of the track) decodes to noise. So each
        # audio-latent frame is assigned to exactly ONE window — the one whose center is nearest,
        # i.e. its confident middle, away from the tapered edges. Video is co-denoised (averaged),
        # audio is piecewise-single-window. Boundaries land at the midpoints between window centers.
        Ta_full = int(list(full_latent["samples"].unbind())[1].shape[-1])
        aranges = []
        for wc in win_conds:
            ga = int(round(_globalcoord(wc["gv"])))
            na = max(1, min(int(round(_globalcoord(wc["gv"] + wc["nv"]))) - ga, Ta_full - ga))
            aranges.append((ga, na))
        centers = [ga + na / 2.0 for (ga, na) in aranges]
        audio_own = []
        for i, (ga, na) in enumerate(aranges):
            lo = 0 if i == 0 else int(round((centers[i - 1] + centers[i]) / 2.0))
            hi = Ta_full if i == len(aranges) - 1 else int(round((centers[i] + centers[i + 1]) / 2.0))
            audio_own.append((max(lo, ga), min(hi, ga + na)))

        # Video crossfade weights: each window ramps 1->0 across its overlap with a neighbour so
        # the blend is a smooth LINEAR crossfade (weights sum to 1 per frame) instead of a flat
        # 50/50 average across the whole overlap — which motion-blurs the band. Each window then
        # dominates its own confident middle; the blur collapses to a thin transition.
        vweights = []
        for i, wc in enumerate(win_conds):
            gv, nv = wc["gv"], wc["nv"]
            w = torch.ones(nv, dtype=torch.float32)
            if i > 0:  # left overlap with previous window
                ramp = max(0, (win_conds[i - 1]["gv"] + win_conds[i - 1]["nv"]) - gv)
                if ramp > 1:
                    w[:ramp] = torch.linspace(0.0, 1.0, ramp)
            if i < len(win_conds) - 1:  # right overlap with next window
                ramp = max(0, (gv + nv) - win_conds[i + 1]["gv"])
                if ramp > 1:
                    w[nv - ramp:] = torch.linspace(1.0, 0.0, ramp)
            vweights.append(w)
        state = {"first": True}

        def wrapper(apply_model, args):
            input_x = args["input"]
            ts = args["timestep"]
            c = args["c"]
            shapes = list(c["latent_shapes"])
            vfull, afull = comfy.utils.unpack_latents(input_x, shapes)
            _, _, Tvv, H, W = vfull.shape
            Ta = afull.shape[-1]
            if state["first"]:
                r0 = cls._seamless_payload(win_conds[0]["meta"])
                bp = c.get("minimax_payload") or {}
                log.info("[MiniMaxSeamless] wrapper first call: video=%s audio=%s | %d windows | "
                         "window0 refs: %d video + %d audio conds | audio_scale=%s",
                         tuple(vfull.shape), tuple(afull.shape), len(win_conds),
                         len(r0.get("cond_video_latents") or []), len(r0.get("cond_audio_latents") or []),
                         bp.get("audio_scale"))
                state["first"] = False

            acc_v = torch.zeros_like(vfull); acc_a = torch.zeros_like(afull)

            for i, wc in enumerate(win_conds):
                gv, nv = wc["gv"], wc["nv"]
                ga, na = aranges[i]
                if ga >= Ta:
                    continue
                vwin = vfull[:, :, gv:gv + nv].contiguous()
                awin = afull[:, :, :, ga:ga + na].contiguous()
                xw, shapes_w = comfy.utils.pack_latents([vwin, awin])

                # Build the window's layout NORMALLY — no position shifting. Each window is a
                # separate RoPE-relative forward, so absolute position is invariant to its output;
                # continuity comes from the latent-space combine below. Block alignment (in the
                # schedule) keeps the temporal spacing consistent. Shifting the target away from
                # the refs only starved the audio reference of attention.
                payload = cls._seamless_payload(wc["meta"])
                # audio_scale + seed are model/sampler-derived (same for every window) — carry
                # them from the full-clip payload extra_conds already built. audio_scale is the
                # critical one: without it the forward runs the audio at scale 1.0 instead of the
                # sigma-shift value and the audio decodes to noise.
                base_payload = c.get("minimax_payload") or {}
                for k in ("audio_scale", "seed"):
                    if k in base_payload:
                        payload[k] = base_payload[k]
                payload["layout"] = h3m.PackedLayout(
                    wc["text_len"], nv, H, W, na, keyframes=payload.get("keyframes"),
                    refs=payload.get("refs"), frame_count=payload.get("frame_count"))

                c_w = dict(c)
                c_w["c_crossattn"] = wc["context"]
                c_w["latent_shapes"] = shapes_w
                c_w["minimax_payload"] = payload
                out_w = apply_model(xw, ts, **c_w)
                dv, da = comfy.utils.unpack_latents(out_w, shapes_w)
                # VIDEO: linear crossfade combine (weights sum to 1 per frame -> no division;
                # each window dominates its middle, blur collapses to a thin transition band)
                vw = vweights[i].to(vfull.device, vfull.dtype).view(1, 1, nv, 1, 1)
                acc_v[:, :, gv:gv + nv] += dv * vw
                # AUDIO: assign this window's owned slice only — never average (-> noise)
                olo, ohi = audio_own[i]
                if ohi > olo:
                    acc_a[:, :, :, olo:ohi] = da[:, :, :, olo - ga:ohi - ga]

            out, _ = comfy.utils.pack_latents([acc_v, acc_a])
            return out

        m = patched_model.clone()
        m.set_model_unet_function_wrapper(wrapper)
        guider = _unpack(sm.BasicGuider.execute(model=m, conditioning=full_cond))[0]
        noise = sm.Noise_RandomNoise(int(noise_seed))
        sampled = _unpack(sm.SamplerCustomAdvanced.execute(
            noise=noise, guider=guider, sampler=sampler, sigmas=sigmas, latent_image=full_latent))[0]

        # --- independent per-window audio (WHILE the DiT is still loaded) -----------------
        # The co-denoise gives beautiful VIDEO but poisons AUDIO (audio latents can't be averaged
        # like video, so they're hard-stitched in the shared latent and each window denoises its
        # audio while seeing its neighbours' discontinuous audio -> tonal mush). Independent samples
        # don't share the audio latent, so they stay clean (proven: the establishment window,
        # sampled alone, is pristine). Sample each window on its own here and take only its audio;
        # video still comes from the co-denoise. Also gives a clean window-0 video for the ghost fix.
        indep = []
        for i, wc in enumerate(win_conds):
            try:
                g = _unpack(sm.BasicGuider.execute(model=patched_model, conditioning=wc["cond"]))[0]
                s = _unpack(sm.SamplerCustomAdvanced.execute(
                    noise=sm.Noise_RandomNoise(int(noise_seed) + i), guider=g,
                    sampler=sampler, sigmas=sigmas, latent_image=wc["latent"]))[0]
            except Exception as e:
                log.warning("[MiniMaxSeamless] independent sample of window %d failed (%s)", i, e)
                s = None
            indep.append(s)

        # --- two-phase-style: free the DiT, then decode everything on the GPU ------------
        comfy.model_management.unload_all_models()
        comfy.model_management.soft_empty_cache()
        out_images = _decode_video(vae, sampled, tiled=tiled_vae_decode)
        total = int(out_images.shape[0])

        # AUDIO: assemble from the independent per-window samples, seams hidden at the quiet points.
        out_audio = None
        if audio_vae is not None:
            try:
                out_audio = _seamless_indep_audio(audio_vae, indep, aranges, total)
            except Exception as e:
                log.warning("[MiniMaxSeamless] independent-audio assembly failed (%s)", e)
                out_audio = None
            if out_audio is None:  # last resort: the co-denoise audio (poisoned, but not silence)
                audio_chunk, sr = _audio_to_stereo(_decode_audio(audio_vae, sampled))
                if audio_chunk is not None and sr != AUDIO_SR:
                    try:
                        import torchaudio
                        audio_chunk = torchaudio.functional.resample(audio_chunk, sr, AUDIO_SR)
                    except Exception:
                        pass
                out_audio = audio_chunk
        if out_audio is None:
            out_audio = torch.zeros(
                (2, max(1, int(round(total / MODEL_FPS * AUDIO_SR)))), dtype=torch.float32)

        # --- clean establishment (video) -------------------------------------------------
        # The co-denoise also ghosts window 1's reference image into its first ~2-3 s of VIDEO;
        # window 0's independent sample establishes it cleanly. Dissolve that clean video over the
        # seamless start across the window-1/window-2 overlap. Guarded: any failure leaves the
        # co-denoise video in place. (Audio already comes from the independent samples above.)
        if len(windows) > 1 and indep and indep[0] is not None:
            try:
                intro_images = _decode_video(vae, indep[0], tiled=tiled_vae_decode)
                F1 = int(intro_images.shape[0])
                ratio = total / max(1, tv)                    # pixel frames per video-latent frame
                ov_px = int(round(max(0, win_conds[0]["nv"] - windows[1][0]) * ratio))
                ov_px = max(0, min(ov_px, F1 - 1, out_images.shape[0] - F1))
                if 0 < F1 <= out_images.shape[0]:
                    seam = F1 - ov_px
                    merged = out_images.clone()
                    merged[:seam] = intro_images[:seam]        # clean intro replaces the ghosted start
                    if ov_px > 0:                              # dissolve into the seamless body
                        r = torch.linspace(0.0, 1.0, ov_px, dtype=out_images.dtype).view(-1, 1, 1, 1)
                        merged[seam:F1] = intro_images[seam:F1] * (1.0 - r) + out_images[seam:F1] * r
                    out_images = merged
                    log.info("[MiniMaxSeamless] clean intro video over first %d frames (overlap %d)",
                             F1, ov_px)
            except Exception as e:
                log.warning("[MiniMaxSeamless] clean-intro video composite failed (%s)", e)

        audio_tl_frames = max(1, int(round(total / MODEL_FPS * fps)))
        combined_audio = media.build_combined_audio(
            timeline_data, int(win_start), audio_tl_frames, fps, override_audio=override_audio)
        prompt_txt = _build_chain_log(tdata, first_p, log_windows, window_prompts, width, height, total, fps, long_mode="seamless")
        log.info("[MiniMaxSeamless] finished: %d frames (%.2fs) at %dx%d",
                 total, total / MODEL_FPS, width, height)
        return io.NodeOutput(
            patched_model, full_cond, sampled, combined_audio,
            MODEL_FPS, int(width), int(height), total, prompt_txt, "",
            out_images, {"waveform": out_audio.unsqueeze(0), "sample_rate": AUDIO_SR})


NODE_CLASS_MAPPINGS = {"H3Eternity_Director": MiniMaxH3Director}
NODE_DISPLAY_NAME_MAPPINGS = {"H3Eternity_Director": "H3 Eternity - Director"}
