# Custom Additions — MiniMax H3 Director (MV fork)

This fork tracks upstream **[ComfyUI MiniMax H3 Director](https://github.com/seesee75-commits/ComfyUI-MiniMaxH3-Director)**
closely and adds a **long-form rendering path** on top of it. As of this release it is
rebased onto **upstream 0.2.2**.

> **Alignment, not divergence.** Typed references, per-shot dialogue, audio roles, the
> guide-aligned compiled prompt (`subject_definitions` / `summary` / `retention_analysis` /
> `detailed_description` / `overall_soundscape` / `non_diegetic_music`), the summary box,
> resolution presets and the Save-Last-Frame node are **upstream's** — this fork adopts them
> as-is and stays aligned with their core concepts. Everything documented below is what this
> fork adds *on top* of that.

Backend changes (`minimax_director.py`) need a **ComfyUI restart**; frontend
(`minimax_director.js`) needs a **hard-refresh** (Ctrl-Shift-R). If a node on the canvas
looks stale after the input/output changes below, right-click → **Fix node (recreate)**.

---

## Marquee: long-form chaining, in one node

Render **past H3's ~15s ceiling** on a single timeline — no second node, no JSON copy-paste.

- **Optional `sampler` + `sigmas` inputs.** Wire them and the Director samples internally,
  splitting the render into anchored windows (each opens on the previous window's last
  decoded frame — a tensor that only exists after that window is sampled, which is why it
  can't be a static graph). Leave them unwired → behaves exactly like upstream (emits
  `latent` for an external `SamplerCustomAdvanced`, keeps the live denoise preview).
- **Two new outputs `images` + `audio`** (decoded, concatenated, de-clicked). Empty in normal
  mode. Wire `images` into `CreateVideo`; use `audio` for the generated soundtrack or
  `combined_audio` for your own track.
- **Three new widgets:** `noise_seed` (base seed, `+index` per window), `window_seconds`
  (per-window length, clamped to H3's 4–15s trained range), `tiled_vae_decode` (off by
  default — the two-phase decode below is the real memory fix).
- **Even-distribution windows.** A 13s render at a 5s target → three 4.33s windows, not
  `[5, 5, 3]`. Failsafes keep every window inside 4–15s and sum exactly to the requested
  length (a 30s render at 5s = exactly 6 windows; at 15s = exactly 2). No window lands below
  the trained floor, and the seams are evenly spaced.
- **LoRA + turbo intact.** LoRAs stay on the `model` wire; wire your 4-step turbo schedule
  into `sigmas` and every window gets the speedup.

Retake is single-window by definition and always takes the normal path.

## Two-phase decode (prevents the RAM crash)

Sampling and decoding are separated so decoding stays on the GPU instead of spilling to CPU
and OOM-freezing the machine on a long chain:

1. **During the loop:** each window decodes *only its anchor frame* (a cheap tail-decode) to
   seed the next window, and stashes the latent.
2. **After the last window:** the DiT is freed **once** (`unload_all_models`), then every
   stashed window is fully decoded on the GPU with the card to itself.

`tiled_vae_decode` also exists (routes through `VAEDecodeTiled`) — but on a 24 GB card it can
still fall back to CPU; the two-phase path is the real fix, so leave tiling off unless you're
on a small card.

## Audio: three use cases, one node

The Director covers all three ways you'd want audio on a long-form render — pick per workflow:

1. **Generate audio** (H3's native joint audio). Drop no audio clip. Keep the `audio` output.
   Set **`seam_audio` = `hard cut`**: each window is an independent take, and any blend would
   smear two unrelated textures.
2. **Provide audio to *guide* generation** (`<Audio N>` reference, ref2va). Drop an audio clip
   and set `use_custom_audio` **ON**; the model generates audio that *follows your track* —
   often reproducing it closely *plus* adding synchronized dialogue/SFX. Keep the `audio`
   output. Use **`seam_audio` = `aligned`** — the windows carry the same continuous track, so
   the seam is phase-matched before the join (see below).
3. **Passthrough** (your own track muxed over the video — the music-video flow). Wire
   **`combined_audio`** into `CreateVideo`. The generated audio is ignored, so `seam_audio`
   doesn't apply.

## Seam handling (audio) — `seam_audio`

Three ways to join per-window generated audio at a seam (generated `audio` output only):

- **`aligned`** *(default)* — **phase-matches the waveform before cross-fading.** When the
  audio reproduces a continuous track (case 2), two windows carry the *same* song but at a
  sub-sample phase offset; a blind blend of two mis-registered copies is exactly the
  flam/stutter you'd hear at every seam. This slides the next window against the tail of the
  running audio (small cross-correlation search), splices at the lag where the song lines up,
  then does an **equal-gain** (linear) cross-fade — equal-gain, not equal-power, because the
  two are now correlated, so equal-power would sum ~+3 dB and bump loudness. It also skips the
  fixed per-window audio cut and lets the correlation find the real overlap, then locks the
  total to the video length so A/V can't drift. *Offline check: RMS error through the join
  ~0.0006 vs ~0.43 for a blind cross-fade.*
- **`crossfade`** — fixed ~12 ms equal-power cross-fade, no alignment. For audio that's
  coherent but not a literal continuous track.
- **`hard cut`** — plain splice. Cleanest for purely generated audio (case 1), where each
  window is an independent take and any blend smears two unrelated textures.
- **Per-window audio references:** each window pulls the audio-reference slice matching *its*
  time range `[start, start+span)`, the same way its video reference is offset — so
  guided-generation audio (case 2) actually tracks your song across windows instead of
  restarting from the song's opening every window.
- **Duplicate seam frame dropped:** the opening frame of each chained window *is* the previous
  window's last frame; it's dropped on decode (video + the matching audio samples) so seams
  don't stutter.
- **`combined_audio` matches the actual rendered length.** Windows snap up on the frame grid,
  so the timeline mixdown is built to the real output length and audio/video end together.

> **On seam quality:** the *video* join is resolution-bound — upstream measured join error at
> 5.2× the median frame-to-frame difference at 480×288 but only 2.3× at 1024×576, so render at
> a real resolution for clean cuts. The generated-*audio* seam is inherent to per-window
> generation and no merge math removes it; for polished results, case 3 (mux your own track)
> sidesteps it entirely.

## Output / logging — long-form gen-log

In chaining mode the `prompt` output is a **clean, saveable record** instead of the same
payload repeated once per window. The shared context — style / global, subjects & references,
audio — is written **once**, then each window's **exact compiled prompt** is listed under its
label. Reads top-to-bottom as *what it looks like → who's in it → what it sounds like → the
prompt each window actually received*. Wire it into a "Save Text File" node for one log per
render. (Single-window mode returns upstream's compiled prompt directly, unchanged.)

## UI / quality-of-life (frontend)

- **Zoom no longer blanks.** The max-zoom ceiling and the canvas backing-store are both capped
  against the *backing* width (`cssWidth × devicePixelRatio × graph-zoom`), not the raw CSS
  width — so a long timeline no longer silently blanks the canvas when the graph itself is
  zoomed in or on a HiDPI / fractional-scaled display.
- **Click a shot → its prompt field flashes**, tying the on-timeline block to the editor field
  you type into.
- **Audio no longer grows the render duration.** Dropping (or pasting) a long song no longer
  balloons `duration_frames` to the track's length — a 30 s render stays 30 s. The clip still
  displays in full on the audio track; the render window stays exactly as set.
- **Generation seam markers + snapping.** Amber dashed lines mark where each chained window
  meets the next (`getWindowBoundaries()` mirrors the backend's `split_windows()` exactly, so
  a marker lands on the precise boundary frame). Segment edges snap to them with priority and
  a wider grab, so a cut or fade placed on a seam hides the join.
- **Zoom controls relocated** beneath the timeline they act on, instead of down in the
  player/guide-strength row where they read as belonging to the audio track.

### Planned (not in this release)

**Render-loop performance pass** (rAF-coalesced renders, off-screen culling, memoized
text-fitting, `Map` lookups in the hot path). Deferred deliberately: upstream rewrote the
render loop, so this is a diffuse change across ~90 `render()` call sites that can only be
validated by profiling a running editor — not worth a silent redraw regression until it's
done live with a profiler.

---

## Node identity

The node id is unchanged — **`MiniMaxH3DirectorCS`** — so existing workflows (including the
one embedded in an exported `.mp4`) keep loading. Only the package name, version and repo URLs
differ from upstream.
