# Seamless long-form generation — design spec

**Status:** design only, not implemented. This documents what a *genuinely seamless* long-form
path would take, versus the current stitch-and-crossfade path.

---

## 1. Why stitching can never be seamless

The current long-form path (`_execute_windowed`) generates each window **independently** and
joins the results:

- window N+1 opens on window N's last decoded frame (the anchor), but that is the *only*
  constraint — one frame of video, nothing for audio;
- everything else in each window is a fresh, independent sample.

Two independent generations of "the same" moment **diverge**. Measured on a real 6-window
render (`docs/video/H3_Director_00047_`): across a seam the audio pre/post correlate only
**~0.46**, and each window's generated audio **tapers to near-silence at its own temporal
edges** (the model is unsure at the very start/end of the ~5 s it produces). No post-hoc
splice fills a hole where neither window produced confident content — the best we can do
(full-overlap equal-gain crossfade, shipped as `seam_audio=aligned`) turns an ~18 ms silence
*hole* into a soft ~−11 dB *dip*. Video has the same disease: the seam is a cut between two
divergent generations, resolution-bound (upstream measured join error 5.2× the median
frame-diff at 480×288, 2.3× at 1024×576).

**The only way to a true seam is to stop generating windows independently** and make
overlapping regions *share* their content. That is temporal MultiDiffusion.

---

## 2. The approach: temporal context-window co-denoising (MultiDiffusion)

Proven prior art: **AnimateDiff-Evolved's "Context Options"** generate arbitrarily long video
from a model trained on ~16 frames by sliding an overlapping context window across one long
latent and **averaging the model's prediction in the overlaps at every denoise step**. The
overlaps are forced to agree at each step, so the final latent is globally coherent — no
stitching, no crossfade. MultiDiffusion (Bar-Tal et al.) and FreeNoise are the underlying
references.

We apply the same idea to H3's **joint AV latent**, so both the video *and* the audio become
one continuous, coherent generation. Because the overlap latents converge to the *same*
values, decoding is seamless by construction — no edge tapers (the interior of the long latent
is never a window edge), no phase discontinuity, no dip.

### Core loop (one long latent, sliding window, per-step averaging)

```
latent = full_noise                      # NestedTensor(video[B,24,Tv,H/16,W/16], audio[B,32,2,Ta])
positions = plan_window_positions(...)    # overlapping [start,len] over the full length
conds     = [encode_conditioning(plan_timeline(tdata, pos)) for pos in positions]  # PRECOMPUTED once

for sigma in sigmas:                      # any sampler/sigmas — turbo, LoRA, all still apply
    accum_v, w_v = zeros_like(video), zeros(Tv)
    accum_a, w_a = zeros_like(audio), zeros(Ta)
    for pos, cond in zip(positions, conds):
        vslice, aslice = latent_slices_for(pos)         # slice BOTH streams (see §4)
        win = NestedTensor(video[..., vslice, :, :], audio[..., aslice])
        pred = model_denoise_step(win, sigma, cond)     # H3 forward on the window
        taper = raised_cosine(len(vslice))              # blend weight, 0 at window edges
        accum_v[..., vslice] += pred.video * taper;  w_v[vslice] += taper
        accum_a[..., aslice] += pred.audio * taper_a; w_a[aslice] += taper_a
    denoised = NestedTensor(accum_v / w_v, accum_a / w_a)   # MultiDiffusion average
    latent = sampler_step(latent, denoised, sigma)          # advance the whole latent
decode_once(latent)                                          # single VAE decode, seamless
```

The taper weights (raised-cosine, zero at each window's edges) mean a window contributes most
at its confident center and nothing at its edges — so window edges are always covered by a
neighbor's center. That is precisely what kills the edge-taper hole.

---

## 3. Why H3 makes this tractable — and where it bites

Grounded in `comfy_extras/nodes_minimax_h3.py`, `comfy/ldm/minimax/model.py`,
`comfy/model_base.py`:

**Good news**
- **Standard ComfyUI sampling.** H3 is flow-matching (`ModelSamplingAV, CONST`) sampled through
  the normal guider/sampler path. A custom sampler *or* a `model_function_wrapper` slots in
  cleanly, and the user still wires their own SAMPLER + SIGMAS (turbo, LoRA unaffected).
- **RoPE with an explicit origin — positioning a window is trivial.** Positions are built by
  `PackedLayout` (`model.py:288`) as one packed sequence `[text][cond/ref rows][video][audio]`
  with `position_ids [S,3]` = (t, h, w) for rotary embedding. The temporal axis is
  `_video_t_grid(n, origin) = origin + cumsum(spans)` and `_audio_grid(cursor, …)` — **origin /
  cursor are free parameters**, so a window is placed globally by computing its origin. RoPE is
  relative, so within-window attention is correct; cross-window attention is dropped (the
  standard MultiDiffusion assumption, proven fine for AnimateDiff).
- **A fixed-vs-denoised row mask already exists.** `PackedLayout` marks each row
  `img_update`/`audio_update` (True = denoised, False = conditioning re-injected every step).
  That is the "never-denoised" hook — reusable for anchors and for pinning frames.
- **We already plan per-window.** `plan_timeline(tdata, pos, span, …)` gives the storyboard
  prompt slice, the ref-image slots, and the per-window audio-ref slice for any time range —
  exactly the per-position conditioning the loop needs.

**The hard parts**
- **✅ The video temporal origin is coupled to `text_len` — solved, PoC-validated.** In
  `PackedLayout` the video/audio cursor starts at `text_len` (+ ref advances), so a different
  prompt per window puts the **same global frame at a different RoPE coordinate** → overlaps
  ghost. **Fix (proven in `docs/seamless_positioning_poc.py`):** replace the origin with a
  **global, text-length-independent** one — `origin = B + global_video_coord(G)`, where `B` is a
  fixed base ≥ any window's `text_len` (so text never collides with video coords on the shared
  axis) and `global_video_coord(G)` is the exclusive-cumsum of `FRAME_RESCALE·FRAME_PER_TOKEN`
  up to the window's global start `G`. The PoC shows: as-is → overlap coords differ by 48.0;
  fixed origin → overlap coords **identical in both windows and equal to the global grid**.
  Requires reconstructing the cursor logic (don't call `PackedLayout` as-is), and windows must
  be **block-aligned (`G % 5 == 0`)** — the PoC also shows a G=17 start corrupting interior
  frames, because the span phase `FRAME_PER_TOKEN[k%5]` must match global.
- **Two streams, two temporal rates, block phase.** Video latent: `video_latent_t(n) =
  ((n-5)//17)*5 + 2` (**17 pixel ↔ 5 video-latent frames**, +2 base); audio linear at **40 fps**.
  And spans are keyed to `k % 5` (`FRAME_PER_TOKEN = (1,4,4,4,4)`), so **window starts must be on
  5-latent-frame (17-pixel) block boundaries** or the intra-window spacing desyncs from global.
  The +2 base means the very first block is special — handle it explicitly in the slicer.
- **Per-window conditioning inside one pass.** The Director's whole value is a *different* prompt
  per time range. A plain `model_function_wrapper` assumes one conditioning; per-window prompts
  mean the co-denoise loop applies the matching precomputed cond+layout to each window slice
  itself. **→ favors a custom sampler/guider over a model wrapper** for H3.
- **Averaging space for flow-matching.** Average the model's **denoised (x0-equivalent)**
  prediction, which ComfyUI exposes per step — not raw velocity. Video and audio carry different
  flow shifts (12.0 / 3.0); keep the streams' taper/averaging independent (already separate above).
- **Long-range drift.** MultiDiffusion keeps *local* overlaps consistent but can drift globally
  (H3 already loops/drifts past its trained length). **FreeNoise**-style noise init
  (repeat/shuffle the base noise across windows) is the known mitigation; add it in a later phase.

---

## 4. Latent geometry (concrete)

For a 30 s render at 1920×1088 (`length` snaps to 736 = 17k+5 grid):
- video latent: `[1, 24, 217, 68, 120]` (Tv = `video_latent_t(736)` = 217) ≈ **~850 MB fp16**
- audio latent: `[1, 32, 2, 1227]` (Ta = `round(736/24*40)`) — negligible

The full latent is resident throughout; the model only ever runs on **one window slice**
(~124 frames = 37 video-latent frames) at a time, so peak VRAM ≈ full latent (~0.85 GB) +
one window's activations + weights. Comfortable on 24 GB with the existing two-phase decode
discipline (free the DiT before the single final decode).

**Window schedule:** window length ∈ H3's trained set (124…362 frames), stride a whole number
of 17-frame blocks, overlap = length − stride. Start with **124-frame windows, ~68-frame
stride (≈45 % overlap)**. Windows and stride chosen so every slice lands on block boundaries
(mind the +2 base).

---

## 5. Compute & positioning

- **Cost:** ≈ `steps × num_window_positions`. Non-overlapping today = `steps × 6` for 30 s;
  ~45 % overlap ≈ `steps × 11` → **~1.8× sampling time**. A 45-min render → ~80 min. That is
  the price of true seamlessness; it is a *quality* mode, not the default.
- **Mode, not replacement.** Keep `aligned` (fast, soft-dip seams) as default. Add
  **`seamless`** as a distinct mode / sampler for final renders. Same node id, same outputs.
- **Degrades to today's behavior** if overlap = 0 (windows independent) — useful as a correctness
  check during bring-up.

---

## 6. Phased implementation plan

1. **Slicer + recompose, video-only, no averaging.** Prove block-aligned two-stream slicing of
   the NestedTensor and exact reconstruction (slice every window, write back, assert the latent
   is byte-identical with overlap=0). This de-risks the +2-base geometry before any denoising.
2. **Video-only MultiDiffusion.** Add per-step overlap averaging on the video stream; audio still
   stitched by `aligned`. Confirm the *video* seam disappears. Validates the co-denoise machinery
   and per-window conditioning end-to-end.
3. **Joint AV.** Extend averaging to the audio stream → seamless audio (the edge-taper hole and
   the 0.46-divergence both vanish, because the overlap is one shared generation). This is the
   payoff for the music-video use case (generated audio + dialogue/SFX, no seam).
4. **FreeNoise init for long-range consistency.** (Hard mid-timeline keyframes are *not* a free
   add — see below — so this phase is just the noise-init drift fix.)

Each phase is independently testable and shippable behind the `seamless` mode.

**Phase 1's positioning half is already done** — `docs/seamless_positioning_poc.py` proves the
text-length-independent global origin makes two different-prompt-length windows share identical
overlap `position_ids` (and matches the global grid), and that windows must start on `G % 5 == 0`
blocks. What remains for Phase 1 is the *tensor* half: block-aligned two-stream (video+audio)
slice/recompose of the NestedTensor with exact reconstruction at overlap=0.

---

## 7. Open questions — status after reading `comfy/ldm/minimax/model.py`

**Resolved**
- *Position scheme:* **RoPE** with an explicit `origin`/`cursor` (`_video_t_grid`, `_audio_grid`).
  Windows are placed by computing their global origin — no absolute-embedding surgery. ✓
- *Native keyframes:* **first/last only** — `PackedLayout` raises `ValueError` on any other
  `resolved_frame_index` (`model.py:314`). So the global first-frame anchor rides the first
  window, the last-frame anchor the last window; mid-timeline content is `refs` (positioned per
  window), exactly as today — **no regression, but also no free mid-timeline hard keyframes.**
  Arbitrary hard keyframes would need a custom latent-inpaint constraint (encode → pin the row →
  set its `img_update=False` so it's re-injected, never denoised). Separate feature. ✓
- *Fixed-vs-denoised mechanism:* the `img_update`/`audio_update` row masks. ✓

**Still to verify (prototype)**
- ~~The `text_len`-coupled temporal origin.~~ **Done — `docs/seamless_positioning_poc.py`.**
- **Averaging stability for flow-matching.** Does averaging two overlapping windows' denoised x0
  stay stable across the trajectory, especially early high-sigma steps? (May need to start
  averaging only below a sigma threshold, or blend the raw velocity instead — measure.)
- **Windowed attention on H3.** MultiDiffusion drops cross-window attention; proven fine for
  AnimateDiff, unverified on H3's single-stream packed-token DiT. Watch for boundary artifacts.

---

## 8. Fallbacks that need no model surgery (for reference)

If the co-denoise route proves too costly to land soon, two cheaper half-measures exist — both
strictly worse than §2, documented so they aren't re-discovered:
- **Overlap-generate + latent crossfade:** generate windows overlapping, crossfade in *latent*
  space before one decode. Still ghosts/dips (divergence is in the latent too). Marginal.
- **Tail-as-reference conditioning:** feed window N's last K frames as ref-image context so
  window N+1 continues them. Reduces *video* divergence; does nothing for audio (H3 has no
  "continue-from-these-samples" audio conditioning). Helps, not seamless.
