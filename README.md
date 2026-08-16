# ComfyUI MiniMax H3 Director — Extended

> ### A fork of [**ComfyUI MiniMax H3 Director**](https://github.com/seesee75-commits/ComfyUI-MiniMaxH3-Director) — genuinely excellent work.
>
> That node — by **seesee75-commits**, itself a port of **WhatDreamsCost**'s [LTX Director](https://github.com/WhatDreamsCost/WhatDreamsCost-ComfyUI) — is the entire foundation here: the timeline, the storyboard compiler, the live prompt preview. **Go star the original.** This fork keeps all of it and pushes hard on long-form video, the reference system, and dialogue. The [original documentation](#-original-readme) below still applies in full.

**A timeline editor for [MiniMax H3](https://huggingface.co/Comfy-Org/MiniMax-H3) inside ComfyUI.**
Drag images, videos and music onto tracks, trim them on a ruler, write a prompt per shot,
press Run — a storyboard instead of one prompt box, with the exact model prompt visible as
you edit.

[![license](https://img.shields.io/badge/license-GPL--3.0-blue)](LICENSE)
[![ComfyUI](https://img.shields.io/badge/ComfyUI-%E2%89%A5%200.30.0-1a1a1a)](https://github.com/comfyanonymous/ComfyUI)
[![fork](https://img.shields.io/badge/fork-Extended-brightgreen)](CUSTOM_ADDITIONS.md)

![The MiniMax H3 Director node](docs/images/director-node.png)

---

## What this fork adds

Full detail in [**CUSTOM_ADDITIONS.md**](CUSTOM_ADDITIONS.md). The headlines:

- **Long-form in one node.** Wire a `sampler` + `sigmas` and the Director renders *past H3's
  ~15s ceiling* on a single timeline, as evenly-split anchored windows — no second node, no
  JSON copy-paste. Your LoRAs and turbo schedule stay on the wire and apply to every window.
- **Two-phase decode.** Sampling and the heavy VAE decode are separated — anchor-frame decode
  in the loop, full decode once the DiT is freed — so long renders stay on the GPU instead of
  spilling to CPU and OOM-freezing the machine.
- **Seam handling.** 12 ms equal-power audio de-click, per-window audio-reference slicing, a
  length-matched `combined_audio` output, and amber **seam markers** on the timeline that
  segment edges snap to — so cuts land exactly on a window join.
- **Typed references.** Every reference slot is *Character / Animal / Object / Scene / Style*,
  and the `subject_definitions` line matches the type **and finally uses your description.**
- **Per-shot dialogue.** A dialogue section per shot (time · speaker · language · line) compiles
  to H3's own `<Subject N> (SN) says, <d>[Language] …</d>`, with ♪ markers on the timeline and
  hover-sync between markers and the editor rows.
- **Audio roles.** *Voice / Background Music / Ambient* — each written as its own `<Audio N>`
  definition instead of assuming every clip is a voice.
- **Gen-log output.** The `prompt` output is a full, saveable record — storyboard, timings,
  every reference filename, audio prompts, and a per-window breakdown.
- **UI & robustness.** Zoom no longer blanks on long timelines, zoom controls sit under the
  timeline, dropping a long song no longer balloons the render duration, sub-frame prompt-bleed
  at seams is eliminated, and a front-end performance pass.

> **Deploy after updating:** restart ComfyUI (backend) **and** hard-refresh the browser
> (frontend). If a node on the canvas looks stale after the input/output changes, right-click →
> **Fix node (recreate)**.

---

## <a id="-original-readme"></a>📖 Original documentation

Everything below is the upstream README — installation, usage, prompt format, retakes, the lot —
and all of it still applies to this fork.

---

## Contents

- [News](#news)
- [Why](#why)
- [What you get](#what-you-get)
- [Requirements](#requirements)
- [Installation](#installation)
- [Models](#models)
- [Quick start](#quick-start)
- [The timeline](#the-timeline)
- [Prompt format](#prompt-format)
- [Writing it yourself](#writing-it-yourself)
- [Live preview while sampling](#live-preview-while-sampling)
- [Writing the prompt for you](#writing-the-prompt-for-you)
- [Retake Mode](#retake-mode)
- [Longer than 15 seconds](#longer-than-15-seconds)
- [Troubleshooting](#troubleshooting)
- [Reporting a bug](#reporting-a-bug)
- [Contributing](#contributing)
- [Credits](#credits)
- [License](#license)

---

## News

**0.1.6** · 2026-08-10 — the compiled prompt can be written by hand and reverted, subject
slots go from 1 to 9, an audio clip can name whose voice it is, and the live preview lets
you choose between true speed and the shot's own frame rate.

**0.1.5** · 2026-08-06 — picture notes in `Refs ON` now use the reference guide's own
phrasing for frame anchors: `[Shot 1] begins from <Picture 1>`, `ends on`, and
`The keyframe of [Shot 2] corresponds to …`.

**0.1.4** · 2026-08-06 — `overall_soundscape` and `non_diegetic_music` have their own boxes
under the Global Prompt, and the alignment line's end mark can no longer name a moment past
the end of the video.

**0.1.3** · 2026-08-06 — new **MiniMax H3 Enhance Prompt** node: a local vision model turns
reference images plus a one-line idea into a prompt for the Director, and hands the same
images on so it describes exactly what H3 will condition on.

**0.1.2** · 2026-08-06 — reference images are numbered along the timeline again, and prompts
in `Refs OFF` now carry the image-alignment instruction MiniMax's guide requires. The
Director Chain node is withdrawn until it can actually be operated.

**0.1.1** · 2026-08-04 — only the checkpoint the toolbar asks for is loaded, instead of both
model inputs reading ~42 GB of weights to use half of them.

**0.1.0** · 2026-08-04 — first public release: the LTX Director timeline editor by
WhatDreamsCost, ported to MiniMax H3.

Full history in the [changelog](CHANGELOG.md).

---

## Why

MiniMax H3 generates video **and** audio jointly, takes reference images, videos and audio,
and anchors on a first and last frame. All of that is reachable through core ComfyUI
nodes — but you address it by hand-writing a storyboard prompt, counting frames onto a
17k+5 grid, and wiring conditioning nodes for every reference.

This node turns that into an editor. Segments on a track become shots with timestamps.
Images dropped on the track become keyframes or `<Picture i>` references. Audio becomes
either a reference or the muxed soundtrack. The prompt is compiled for you, live, and you
can read it before you spend a render on it.

## What you get

Four nodes, category **MiniMax H3**:

| Node | What it does |
|---|---|
| **MiniMax H3 Director** | The timeline. Outputs a patched `model`, the compiled `positive` conditioning, an empty joint AV `latent`, the muxed `combined_audio`, plus `fps` / `width` / `height` / `length` / `prompt` / `retake_info`. |
| **MiniMax H3 Preview Override** | Watch the whole shot denoise, not a single frozen frame. |
| **MiniMax H3 Retake Stitch** | Splices a regenerated range back into the base video. |
| **MiniMax H3 Enhance Prompt** | A local vision model writes the prompt from your reference images. |

Editing features carried over from LTX Director: main track, reference-video track, audio
track, ruler in seconds or frames, drag / resize / copy / paste, prompt zones per segment,
waveform preview, filename labels, gear menu, workspace folder, chunked upload for large
videos, drag-and-drop straight onto the node, and the `@char1` / `@char2` / `@char3`
character slots including the optional local VLM "Analyze" button (Ollama / LM Studio /
any OpenAI-compatible endpoint) with automatic VRAM release before a run.

## Requirements

* **ComfyUI ≥ 0.30.0** — H3 support, `comfy_api.latest` and the packed AV latent all
  landed in 0.30. Older builds will fail to load the nodes.
* **Python 3.10+** (ComfyUI's own environment; the portable build's `python_embeded` is fine).
* **No extra pip packages.** Everything the nodes import ships with ComfyUI already.
* **VRAM:** the fp8 checkpoints are ~21 GB on disk. 16 GB VRAM works with ComfyUI's
  offloading at 480p–768p; below that expect heavy swapping. The text encoder is a
  separate ~15 GB load.
* **Disk:** budget ~60 GB if you want both model paths plus the text encoder and VAEs.

## Installation

### Via ComfyUI Manager (recommended)

1. Open **Manager → Custom Nodes Manager**
2. Search for **MiniMax H3 Director**
3. **Install**, then restart ComfyUI and reload the browser tab.

Not listed yet? Use **Manager → Install via Git URL** and paste:

```
https://github.com/vomitselfie/ComfyUI-MiniMaxH3-Director-Extended
```

### Manual

Clone into your `custom_nodes` folder and restart:

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/vomitselfie/ComfyUI-MiniMaxH3-Director-Extended
```

On the Windows portable build the folder is
`ComfyUI_windows_portable\ComfyUI\custom_nodes`.

There is **nothing to pip install** — the package declares no third-party dependencies.

Then restart ComfyUI **and hard-reload the browser** (Ctrl+F5). The timeline is a
frontend extension; a stale cached `.js` is the single most common "node looks broken"
report.

### Updating

```bash
cd ComfyUI/custom_nodes/ComfyUI-MiniMaxH3-Director
git pull
```

## Models

Download from [🤗 Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3).
The example workflow carries download links, so ComfyUI can offer to fetch them for you.

**Put the files directly in these folders — no subfolder.** A file at
`models/diffusion_models/MiniMax-H3/…` will not match the example workflow.

```
ComfyUI/models/
├── diffusion_models/
│   ├── minimax_h3_fl2va_pruned_fp8_scaled.safetensors     21 GB   ← text/keyframe path
│   └── minimax_h3_ref2va_pruned_fp8_scaled.safetensors    21 GB   ← reference path
├── text_encoders/
│   └── qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors       15 GB
└── vae/
    ├── minimax_h3_video_vae_fp16.safetensors             4.9 GB
    └── minimax_h3_audio_vae_fp32.safetensors             0.6 GB
```

**The two diffusion checkpoints are not interchangeable — they are separate trainings:**

| Toolbar switch | Checkpoint | Use it for |
|---|---|---|
| **Refs OFF** | `minimax_h3_fl2va_*` | text→video, and first/last keyframes from the timeline |
| **Refs ON** | `minimax_h3_ref2va_*` | character slots, reference images, reference videos, reference audio |

Connect both to the Director's two model inputs and the toolbar switch picks the right
one. Connecting only one is fine — the node warns rather than silently using the wrong path.

Only the selected checkpoint is ever read from disk: the model inputs are lazy, so with
the toolbar on **Refs OFF** the `ref2va` loader never runs at all. Wiring both costs you
disk space, not RAM.

Other quantisations on the repo work too: `*_bf16` (66 GB, best quality),
`*_int8_convrot` (34 GB), `*_pruned_int8_convrot` (21 GB). The text encoder also comes as
`_bf16` and `_int8_convrot` if `nvfp4_awq` does not run on your GPU.

## Quick start

1. **Workflow → Open** → `example_workflows/MiniMax H3 Director.json`
   (or drag [`docs/images/workflow-overview.png`](docs/images/workflow-overview.png)
   onto the canvas — the same graph is embedded in that screenshot)
2. Fix any red nodes — usually the model dropdowns, if your filenames differ.
3. Double-click a segment on the main track and type what should happen.
4. Drag an image onto the track for a first-frame anchor (optional).
5. **Run.**

Read the **COMPILED PROMPT** panel under the timeline before running: it shows the exact
text the model will get, the shot count, the frame count and the reference tally, plus
warnings for the things that silently bite.

Defaults that matter, if you wire it yourself:

* `CLIPLoader` **type must be `minimax`**.
* Sampler `res_multistep`, scheduler `simple`, ~20 steps, through `BasicGuider` (no CFG).
  For reference-heavy `ref2va` prompts, `beta` or `normal` often beats `simple`.
* The joint latent goes to **both** `VAEDecode` (video VAE) **and** `VAEDecodeAudio`
  (audio VAE); each pulls its own half out. `CreateVideo` muxes them.
* Length snaps up to H3's 17k+5 frame grid at 24 fps — 5 s becomes 124 frames (5.17 s).
* Native canvas is a 768 px short edge, capped at 768×1344.

```
UNETLoader ×2 ─┐
CLIPLoader   ─┼→ MiniMax H3 Director ─┬→ model ──→ BasicGuider ─→ SamplerCustomAdvanced
VAELoader ×2 ─┘                       ├→ positive ┘                      │
                                      ├→ latent ─────────────────────────┘
                                      ├→ combined_audio → CreateVideo.audio
                                      └→ fps ───────────→ CreateVideo.fps
```

![The example workflow](docs/images/workflow-overview.png)

The example packs the sampler and the two decoders into subgraphs so the graph stays
readable; open them if you want to change sampler, scheduler or steps.

## The timeline

| Track | Drop this | Becomes |
|---|---|---|
| **Main** | images | first/last keyframe (Refs OFF) or `<Picture i>` (Refs ON) |
| **Main** | prompt zones | `[Shot N]` entries with timestamps |
| **Reference video** | video clips | `<Video k>` motion/style references |
| **Audio** | music, SFX | `<Audio j>` reference and/or the muxed soundtrack |

### Reference limits

From MiniMax's own model card — not from ComfyUI's node signatures, which are looser.
These are enforced, with a warning naming exactly what was dropped:

| Limit | Value |
|---|---|
| Reference images | ≤ 9 — the three character slots *and* the `ref_images` input share this pool |
| Reference videos | ≤ 3 clips, each 2–15 s, **≤ 15 s total** |
| Reference audio | ≤ 3 clips |
| **All types together** | **≤ 12 files** |

Output envelope: 4–15 s at 24 fps. Aspect ratios 21:9, 16:9, 4:3, 1:1, 3:4, 9:16.

Anything you drop on a track is uploaded to `ComfyUI/input/whatdreamscost/`. That is the
same folder LTX Director uses, deliberately — if you run both, assets and saved timelines
carry over between them.

### Character slots and the Analyze button

Drop a face or a full-body shot into `@char1` … `@char3` and write `@char1` in a prompt;
it expands to `<Subject 1>` (MiniMax notation) or `<Picture 1>` (ComfyUI notation) and the
image is attached as a reference. This is the **Refs ON (ref2va)** path.

**How many slots is up to you** — the stepper next to them goes from 1 to 9, starting at 3.
Each slot holds two images, and H3 takes nine reference images in total, so nine slots is
where it stops being useful rather than where the model gives up.

An **audio clip on the timeline can name whose voice it is**: pick a subject in the clip's
info panel and the prompt says so in the guide's own words — `<Audio 1> is the voice-timbre
reference for <Subject 1> (S1).` Leave it unset and the clip stays a general voice
reference, as before.

**Analyze** is optional and off the critical path. It sends the slot image to a local
vision model and pastes back a one-line description, so `@char1` still means something in
**Refs OFF** mode, where H3 gets no image at all. Nothing is installed for you and nothing
is sent anywhere unless you press the button.

To use it, run a vision model locally and point the gear menu's provider row at it:

| Provider | Default URL | Set up |
|---|---|---|
| Ollama | `http://127.0.0.1:11434` | `ollama pull qwen2.5vl:7b` — any vision model works, the field is free text |
| LM Studio | `http://127.0.0.1:1234` | load a vision model, start the local server |
| Custom | — | any OpenAI-compatible `/v1/chat/completions` endpoint |

The node also asks the server to release the model before a render, so the VLM is not still
in VRAM while H3 samples. Ollama takes `keep_alive: 0`; llama-server does too **in router
mode**, via `POST /models/unload`. A plain `llama-server -m model.gguf` has no such
endpoint — give it `--sleep-idle-seconds N` and it will let go by itself. LM Studio manages
residency on its own.

**Keyframes go on the first and last frame only.** H3's `PackedLayout` anchors exactly
those two positions; an image stranded in the middle of a window is reported in the
warnings rather than silently ignored.

## Prompt format

Gear menu → **Prompt Format**. The default is **MiniMax**, the notation from their own
`VIDEO_PROMPT_WRITING_GUIDE`:

```
subject_definitions: <Subject 1> is the character shown in <Picture 1>.

retention_analysis: Keep the identity, face and clothing of <Subject 1> consistent across every shot.

detailed_description: Live-action, cinematic. [Shot 1] the baker opens the shutters
[Shot 2] At 00:01.500, <Subject 1> lifts the loaf onto the counter

overall_soundscape: street ambience, a distant tram
non_diegetic_music: soft piano
```

The first shot carries no timestamp; every later cut carries a strictly increasing
`MM:SS.mmm` one. Sections appear only when there is something real to put in them.

The two sound sections have their own boxes under the Global Prompt. What you type there
goes straight into `overall_soundscape` and `non_diegetic_music`. Leave them empty and the
sections are omitted entirely — an empty heading is worse than none.

`Audio:` / `Sound:` / `SFX:` and `Music:` / `Score:` lines written in the prompt text are
still lifted into the same two sections, so older workflows and the Enhance node keep
working. A filled box wins over a lifted line.

**`<Subject N>` vs `<Picture N>`** is worth knowing: the guide reserves `<Subject N>` for
reusable content — a person, a place, a style — and `<Picture N>` for concrete frame
anchors. ComfyUI's tokenizer only ever labels images `<Picture i>`, so
`subject_definitions` binds the two. That is what lets a character keep one name across
every cut. `@char1` therefore expands to `<Subject 1>` here.

**ComfyUI** switches to `[0s-1.5s] …`, the notation the ComfyUI H3 templates use. Same
timeline, same references, only the wording changes — so it is a fair A/B.

### Writing it yourself

**EDIT** on the COMPILED PROMPT panel hands the text over to you. It starts as whatever the
timeline just compiled, so there is nothing to retype, and **REVERT** throws your version
away and compiles again. While it is on, the panel is titled `PROMPT (HAND-WRITTEN)` and
says that timeline edits no longer touch the text.

Only the text is yours. Which images, videos and audio clips are loaded still comes from the
timeline — the tokenizer numbers `<Picture i>` in the order the plan decided, and rewriting
a sentence cannot renumber that without invalidating what you just wrote. Your version is
kept as written rather than merged into the next recompile: an edit that vanished when you
nudged a segment would lose work without asking, and one that survived in silence would stop
matching the timeline you are looking at.

### Why a storyboard and not a per-segment mask

If you know LTX Director: its Prompt Relay builds a cross-attention mask so each segment
gets its own prompt. That cannot port. H3's DiT runs full self-attention over one packed
`[text | cond | audio | video]` sequence with `mask=None` hardcoded, so a relay mask would
have to span the entire sequence — several GB per attention call at 1344×768. The
storyboard is not a workaround: H3's Qwen3-VL encoder was trained on exactly this notation.

## Live preview while sampling

ComfyUI ships `latent_rgb_factors` for H3, so previews work — but `Latent2RGBPreviewer`
renders `x0[0, :, 0]`, the **first latent frame only**. You watch a still image while a
five-second shot is being sampled. KJNodes' Preview Override does the good version of
this, but its video paths are gated on LTX checks and nothing there unpacks H3's packed AV
latent, so on MiniMax it falls through to the same single frame.

**MiniMax H3 Preview Override** goes between the Director's `model` output and the sampler
and renders the whole shot as it denoises.

<img src="docs/images/preview-override-node.png" alt="The Preview Override node" width="360">


| Widget | What it does |
|---|---|
| `decode` | `latent2rgb (fast)` — one matmul, ~10 ms, rough colours. `vae (quality)` — the real decoder, true colours, real cost. |
| `preview_target` | `node` shows it on this node — always available. `sampler (VHS)` puts it in the sampler's usual preview slot and needs [VideoHelperSuite](https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite) installed; `both` does both. |
| `preview_frames` | Cap on **latent** frames used, thinned evenly across the shot, so it shortens nothing. The main cost knob. |
| `preview_fps` | The shot's frame rate. A FLOAT, so the Director's `fps` output wires straight in. |
| `playback` | `true speed` (default) spreads the sampled frames across the shot's real length, so the preview lasts as long as the finished clip. `source fps` plays them at `preview_fps` flat, like ComfyUI's own preview. |
| `max_resolution` | Long edge of the preview image, as a **target** — latent2rgb frames arrive at latent size (a 1344×768 shot is an 84×48 grid), so this upscales them smoothly. |
| `webp_quality` | Quality of the animation sent to the browser. |
| `every_n_steps` | Never preview more often than every N sampler steps. |
| `max_preview_overhead` | Share of render time previews may use, in percent (default 25). After a preview costing C seconds the next waits `C·(100/P − 1)` s. 0 disables. |
| `suppress_default_preview` | Hides ComfyUI's built-in single-frame preview. |

The time in the status line (`render 9.9s`) is **server-side**: how long ComfyUI took to
decode, scale and encode that preview. Not browser time, not the sampler. With
`latent2rgb` it is tens of milliseconds; with `vae (quality)` at 1344×768 it can be 20–25 s,
because the real decoder expands 37 latent frames into 124 output frames through a 5 GB
VAE. Capping the frame *rate* would not help — rate only sets playback speed. The cost
knobs are `preview_frames` (try 4–8 for VAE), `max_resolution` and `every_n_steps`.

**Why the badge says `4.7fps of 24`.** With `true speed` the rate is derived, not set: the
frames that survive thinning are spread across the shot's real length. In `latent2rgb`
there is one image per latent frame and H3 compresses time about 3.35×, so a 124-frame shot
has 37 images to show and the rate cannot pass `preview_fps / 3.35` — measured, 7.16 fps at
24. That is not a setting being ignored; other packs show a round 24 because they play the
same frames without correcting for the compression, which runs the preview 3.35× too fast.
Switch `playback` to `source fps` if that is the trade you want: motion at normal speed,
clip over early.

`vae (quality)` is the answer to "is there a small preview VAE, like LTX 2.3?" — there is
not. MiniMax has not released a TAESD-style decoder (`latent_format.taesd_decoder_name` is
`None`), so the choice is the cheap RGB approximation or the real video VAE.

<details>
<summary>Two non-obvious details, both of which produced real bugs here</summary>

**The latent is not the video.** `CFGGuider.sample` packs video and audio into one flat
tensor and only *then* wraps the callback with the nested view — and that wrapper sits
behind any `OUTER_SAMPLE` wrapper. What reaches a preview is the flat pack, which has to
be unpacked with core's `unpack_latents` first.

**Latent frames are not output frames.** H3 compresses time ~3.35× (17k+5 output frames
become 5k+2 latent frames), so a 124-frame shot is 37 latent frames. Playing those at 24
fps runs the preview three times too fast. The playback rate is derived from the *output*
duration — `shown_frames × fps ÷ output_frames` — so the preview lasts exactly as long as
the finished shot, thinning included.

</details>

## Writing the prompt for you

**MiniMax H3 Enhance Prompt** hands your reference images and a one-line idea to a local
vision model and gets back prompt text shaped for H3. The same images come out of its
`ref_images` output, so what the model described is exactly what H3 conditions on.

<img src="docs/images/enhance-prompt-node.png" alt="The Enhance Prompt node" width="380">

Ready-made graph: `example_workflows/MiniMax H3 Director + Enhance Prompt.json`.

```
LoadImage ─→ image0 ┐
LoadImage ─→ image1 ├→ Enhance Prompt ─┬→ prompt           → Director.global_prompt
                    ┘                  ├→ ref_images       → Director.ref_images
                                       └→ duration_seconds → Director.duration
```

Sockets grow as you connect, up to nine, and close the gap again when you disconnect.

| Widget | What it does |
|---|---|
| `idea` | What you want, in plain words. |
| `preset` | `global` writes scene, style, subjects and lighting and leaves the shots to your timeline. `storyboard` writes the whole shot sequence with timestamps — only for timelines whose segments carry no prompt text, or the two shot numberings collide. |
| `system_prompt` | Overrides the built-in instructions, which follow MiniMax's own prompt-writing guide. |
| `provider` / `base_url` / `model` | Ollama, LM Studio, or any OpenAI-compatible endpoint. `http://` is added if you leave it off; host and port only, no path. |
| `seed` | ComfyUI caches node outputs, so an unchanged input never re-asks the model. Change this to force a fresh answer. |
| `max_words` | Caps the description. MiniMax's guide puts it at 350–500 words. |
| `unload_after` | Frees the vision model's VRAM when done. Leave it on unless you are iterating. |
| `on_error` | `passthrough` hands your raw text on and warns, so a stopped Ollama does not kill a render. |

**It has to be a vision model.** A text-only model ignores your images without saying so.
`qwen2.5vl:7b` is a reasonable Ollama default; anything larger writes noticeably better
prompts. Expect 15–45 s per run, during which the queue is blocked.

**What it deliberately does not write:** section labels, `<Picture N>` numbering, or shot
markers in `global` mode. The Director compiles the structured MiniMax prompt and assigns
the reference numbers — a second set from the model would nest structure inside structure
and collide with the Director's own ordinals. The instructions forbid it and the output is
filtered anyway, because small models do not reliably obey.

**If the VLM and H3 share a GPU**, the vision model is evicted after each run
(`unload_after`). Ollama has no per-request device selection, so to put it on a different
card you set `CUDA_VISIBLE_DEVICES` on the Ollama *service*, not here.

## Retake Mode

Load a base video, turn on **Retake Mode** in the toolbar, mark a range: the Director
regenerates only that range, anchored on the base video's own frames either side of it.
The frame before the range becomes `first_frame`, the frame after becomes `last_frame` —
exactly what H3's first/last anchors are for, so the new material meets the old on both cuts.

Wire the Director's `retake_info` output into **MiniMax H3 Retake Stitch** together with
the decoded images (and audio) to get the full video back: base head + retake + base tail,
video and audio, resampled to 24 fps. `keep_base_audio` keeps the original soundtrack
across the whole thing instead of the generated one.

## Longer than 15 seconds

Not solved yet. There was a **Director Chain** node that rendered a long timeline as a
chain of anchored windows, and its sampling worked — but there was no usable way to hand
it a timeline, so it has been withdrawn rather than shipped as a feature nobody can
operate. The code stays in the repository; the reasoning is written down at the top of
`minimax_chain.py`.

Until it returns, H3's trained range is the limit: 4-15 s per render.

## Troubleshooting

**The nodes do not appear after installing.**
Restart ComfyUI fully and hard-reload the browser (Ctrl+F5). If they still do not appear,
look at the ComfyUI console during startup — an import error is printed there. Check your
ComfyUI version is ≥ 0.30.0.

**The node loads but the timeline is blank / looks like a plain widget list.**
Stale frontend cache. Ctrl+F5. In a private window it will look correct if that is the cause.

**`ERROR: clip input is invalid` / garbage output.**
`CLIPLoader` type must be set to **minimax**, not `stable_diffusion` or anything else.

**`vae.decode()` fails, or the video is noise but the audio is fine.**
The joint latent must go to `VAEDecode` with the **video** VAE and `VAEDecodeAudio` with
the **audio** VAE. Swapping the two VAEs is the usual cause.

**The finished video is a flat, featureless grey, but the audio is fine and the live
preview looked right.**
The latent is good and the video VAE is producing NaN. Flat grey — not noise, not black,
every pixel the same value — is what NaN looks like after clamping. `latent2rgb` previews
keep working because they never touch the VAE.

Confirm it in a minute instead of a full render: set the Preview Override's `decode` to
`vae (quality)`. That runs the same video VAE, so if the preview goes grey too, the VAE
is where it breaks.

The thing to try is precision. `minimax_h3_video_vae_fp16` runs in fp16, and ComfyUI's own
help text for `--fp16-vae` says it "might cause black images". Start ComfyUI with
**`--fp32-vae`**. fp32 is the *only* alternative here: ComfyUI declares this VAE's working
dtypes as `[float16, float32]`, so `--bf16-vae` silently gets you one of those two. The
decoder grows from ~4.9 GB to ~10 GB, which on a 16 GB card means partial offload and a
slower decode; `--cpu-vae` is the slow-but-certain fallback.

Reported once so far, on ROCm/Windows, where fp16 convolution kernels take different code
paths than on CUDA. Not reproduced on CUDA, and the fp32 remedy is not yet confirmed by
the reporter — if you hit this, please say whether it helped.

**Out of memory.**
Lower the resolution first (768 short edge is native, but 480 works), then `length`. With
`vae (quality)` previews, lower `preview_frames` to 4 — a VAE preview allocates as much as
a real decode. Consider the `_pruned_fp8_scaled` checkpoints if you are on `_bf16`.

**"neither model input is connected".**
The Director has two model inputs on purpose: `model (t2v/i2v)` for `fl2va` and
`model (ref2v)` for `ref2va`. Connect at least the one your toolbar switch selects.

**Images in the middle of the timeline seem ignored (Refs OFF).**
They are — H3 anchors first and last frame only. Switch to **Refs ON** and they become
`<Picture i>` references instead, or move them to the window edges.

**The generated clip is longer than I asked for.**
Length snaps up to the 17k+5 grid: 5, 22, 39, 56, 73, 90, 107, 124 … frames. 5 s → 124
frames → 5.17 s. This is the model's grid, not a bug.

## Reporting a bug

Open an [issue](https://github.com/vomitselfie/ComfyUI-MiniMaxH3-Director-Extended/issues). The three
things that make a report fixable:

1. the **full traceback** from the ComfyUI console (not just the last line),
2. the **workflow JSON** (Workflow → Export), and
3. which **model files** you loaded.

The issue form asks for exactly these. For anything about dragging, resizing or the
preview window, add the **browser** console (F12 → Console) too.

## Contributing

Pull requests are welcome, and so are reports from hardware this has never run on — every
line of it was verified on a single NVIDIA card, so ROCm and Apple silicon are unknown
territory. [CONTRIBUTING.md](CONTRIBUTING.md) has the layout, the three checks to run
before submitting, and the handful of rules that exist because breaking them caused a real
bug.

## Credits

The timeline editor is **[LTX Director](https://github.com/WhatDreamsCost/WhatDreamsCost-ComfyUI)
by [WhatDreamsCost](https://github.com/WhatDreamsCost)** — the editing model, the track
layout, the interaction design and the bulk of the frontend code are theirs. The CS fork
that this one branched from is by **[CGlide](https://github.com/CGlide)**.

This project is that editor with a MiniMax H3 backend: new conditioning, storyboard prompt
compilation, packed AV latents, preview and Retake — by
[seesee75](https://github.com/seesee75-commits).

MiniMax H3 by [MiniMax](https://huggingface.co/MiniMaxAI), ComfyUI packaging by
[Comfy-Org](https://huggingface.co/Comfy-Org).

## License

**GPL-3.0**, inherited from LTX Director — see [LICENSE](LICENSE). If you fork this,
your fork is GPL-3.0 too, and it must stay open.
