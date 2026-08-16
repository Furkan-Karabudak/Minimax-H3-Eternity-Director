# Custom Additions — MiniMax H3 Director (fork)

Everything added on top of the upstream node, since branching out. Backend changes
(`minimax_director.py`, `minimax_plan.py`) need a **ComfyUI restart**; frontend
(`minimax_director.js`) needs a **hard-refresh** (Ctrl-Shift-R). If a node on the canvas
looks stale after the input/output changes below, right-click → **Fix node (recreate)**.

---

## Marquee: long-form chaining, in one node

Render **past H3's ~15s ceiling** on a single timeline — no second node, no JSON copy-paste.

- **Optional `sampler` + `sigmas` inputs.** Wire them and the Director samples internally,
  splitting the render into anchored windows (each opens on the previous window's last
  decoded frame). Leave them unwired → behaves exactly as before (emits `latent` for an
  external `SamplerCustomAdvanced`, keeps the live denoise preview).
- **New outputs `images` + `audio`** (decoded, concatenated). `None` in normal mode.
- **New widgets:** `noise_seed` (base seed, +index per window) and `window_seconds`
  (per-window length, clamped to H3's 4–15s trained range).
- **Even-distribution windows.** A 13s render at a 5s target → three 4.33s windows, not
  `[5, 5, 3]`. Failsafes keep every window inside 4–15s and sum exactly to the requested
  length (a 30s render at 5s = exactly 6 windows; at 15s = exactly 2).
- **LoRA + turbo intact.** LoRAs stay on the `model` wire; wire your 4-step turbo schedule
  into `sigmas` and every window gets the speedup.

## Two-phase decode (prevents the RAM crash)

Sampling and decoding are separated so decoding stays on the GPU instead of spilling to CPU
and OOM-freezing the machine:

1. **During the loop:** each window decodes *only its anchor frame* (cheap) to seed the next
   window, and stashes the latent.
2. **After the last window:** the DiT is freed **once**, then every stashed window is fully
   decoded on the GPU with the card to itself.

`tiled_vae_decode` toggle also exists (routes through `VAEDecodeTiled`) — but on a 24GB
card it can still fall back to CPU; the two-phase path is the real fix, leave tiling off.

## Seam handling

- **Audio declick:** 12ms equal-power cross-fade at every window seam (kills the splice pop).
- **Per-window audio references:** each window pulls the audio-reference slice matching *its*
  time range (previously every window used the segment's opening).
- **`combined_audio` matches the actual rendered length** — windows snap up on the frame
  grid, so the mixdown is built to the real output length and audio/video end together.
  Wire `combined_audio` (not the generated `audio`) when muxing your own track.
- **Timeline seam markers:** amber dashed lines mark where windows join; segment edges snap
  to them, so a cut or fade placed on a seam hides it.

## Reference subjects — typed

Each reference slot has a **type dropdown** — Character / Animal / Object / Scene & Background
/ Style — mapped to H3's own subject buckets. The compiled `subject_definitions` line matches
the type and **weaves in the slot's description** (previously dropped for image slots):

- Character → `<Subject 1> is the character shown in <Picture 1>, <desc>.`
- Scene → `<Subject 2> is the environment shown in <Picture 3>, <desc>.`
- Style → `<Subject 3> is the visual-style reference from <Picture 4>, <desc>.`

## Per-shot dialogue

A **Dialogue** section under the selected shot's prompt. **+ Line** adds rows: start-time
(s from shot start), speaker, language (typeable, with suggestions), and the line. Compiles
to H3's exact form inside the `[Shot N]` block, ordered by time:

```
<Subject 1> (S1) says, <d>[Japanese] …疲れた…</d>
```

- Speaker dropdown offers **only Character/Animal** slots.
- Each line drops a **♪ marker at the bottom of the timeline**, with a finely-dotted line
  rising up through the audio + reference-video tracks. Hovering a marker highlights its
  editor row and vice-versa.
- Coexists with a voice-timbre `<Audio N>` reference — the `(S1)` tag is shared, so audio =
  *how it sounds*, `<d>` = *the words*.

## Audio roles

Audio clips carry a **Type dropdown** — Voice / Dialogue, Background Music, Ambient / SFX.
The `<Audio N>` definition matches the role (voice-timbre reference vs background-music
reference vs ambient), and the "Voice of" subject binding only shows for Voice.

## Output / logging

The `prompt` output is now a **full gen-log**: canvas/frame metadata, global prompt, both
audio prompts, every reference filename (`<Picture>`/`<Video>`/`<Audio>`), the storyboard,
and — in chain mode — a per-window breakdown. Wire it into a "Save Text File" node to file
one log per render (point it at your video's folder to keep them together).

## UI / quality-of-life

- **Audio prompts** (`overall_soundscape` / `non_diegetic_music`) pulled into their own
  labeled section (were crammed in a strip under the global prompt).
- **5 reference slots** by default (was 3).
- **Zoom fixed:** the timeline canvas no longer blanks when zoomed in — the backing-store
  cap now accounts for `devicePixelRatio × graph zoom`. Zoom controls relocated **directly
  beneath the timeline** (were down in the player/guide-strength row).
- **Audio no longer grows the render duration:** dropping a long song no longer balloons
  `duration_frames` to the song's length (it still displays fully on the timeline).
- **Click a shot → its prompt field flashes**, tying the on-timeline block to the editor.
- **Florence-2** available as a reference-image captioner (alongside Ollama).
- Front-end perf pass: killed per-frame reflow, off-screen culling, `.find()`→`Map` in the
  render loop, memoized text-fitting, rAF-coalesced renders, listener cleanup.

## Removed inputs

`global_prompt`, `ref_images`, `ref_image_notes` sockets removed — the UI global prompt
reaches the backend via `timeline_data`, and the node's 9 internal reference slots cover
references.

---

## Storyboard format reference (unchanged, for context)

Segments compile to `[Shot N] At MM:SS.mmm, <text>` (first shot has no timestamp). The node
writes `[Shot N]` and the timestamp — **write only the shot content in each segment**, never
`[Shot 1]` yourself. Shot durations are implicit (next shot's start); a lone action in a
longer span, or several actions crammed in one short shot, will loop to fill — split actions
into contiguous timed segments to pace them.
