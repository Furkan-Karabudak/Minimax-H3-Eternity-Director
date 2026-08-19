# Contributing

Help is welcome, and you do not need to be deep in ComfyUI internals to be useful. This
page has everything needed to make a change that can actually be merged.

## The most useful things you can do

**Report a bug** with enough in it to reproduce. The [issue
template](.github/ISSUE_TEMPLATE/bug_report.yml) asks for the three things that decide
whether a report is fixable: the **full traceback** from the ComfyUI console (not just the
last line), the **workflow JSON**, and the **exact model filenames**. For anything about
the timeline UI, set `window.MMXD_DEBUG = true` in the browser console and reload — it then
logs the timeline JSON on create, sync, save and configure, and that log is usually the
whole answer.

**Test on hardware this pack has never run on.** Everything here was developed and verified
on a single NVIDIA card. ROCm and Apple silicon are genuinely unknown territory, and a
report saying "this works" is as valuable as one saying it does not.

**Fix something.** Read on.

## Getting set up

The checkout *is* the install. Clone into `ComfyUI/custom_nodes/`, restart ComfyUI, and
your working tree is what runs — nothing is copied or built.

```
cd ComfyUI/custom_nodes
git clone https://github.com/seesee75-commits/ComfyUI-MiniMaxH3-Director
```

Where things are:

| File | What it owns |
|---|---|
| `minimax_plan.py` | timeline → plan. Metadata only, never touches pixels |
| `minimax_director.py` | the Director node |
| `minimax_preview.py` | the live sampling preview |
| `minimax_retake.py` | Retake Stitch |
| `minimax_enhance.py` | Enhance Prompt (the vision-model node) |
| `minimax_media.py` | media I/O and every HTTP route |
| `js/minimax_director.js` | the timeline editor, forked from LTX Director |
| `test_plan.py` | offline checks over the planner — it prints its own count |

Python changes need a ComfyUI restart. JavaScript changes need a browser reload with the
cache disabled.

## Before you open a pull request

Run these three. They are fast and they are what a reviewer runs first:

```
python test_plan.py
python -m compileall -q .
node --check js/minimax_director.js
```

`test_plan.py` needs no server and no GPU — `minimax_plan` imports nothing but `json` and
`logging`, on purpose. If you change how a timeline compiles, add a check to it; if an
existing check fails, that is the design telling you something, not noise to be edited
away.

For anything with a UI surface, **drive it the way a user would before calling it done.**
A previous feature passed every backend test and shipped unusable, because nothing had
ever opened the node and clicked on it. That lesson cost a release.

## Please do not touch

These three will get a pull request sent back, so it is worth knowing up front.

**`pyproject.toml`.** Pushing a change to it publishes straight to the Comfy Registry, and
the version has to be bumped in the same commit or the publish fails. Releases are the
maintainer's job — leave the file alone entirely and it will be handled when your change
goes out.

**`LICENSE`.** The GPL-3.0 text must stay verbatim.

**Node IDs.** `MiniMaxH3DirectorCS`, `MiniMaxH3PreviewOverrideCS`, `MiniMaxH3RetakeStitchCS`
and `MiniMaxH3EnhancePromptCS` keep the `CS` suffix forever. Renaming one breaks every
saved workflow that uses it. The display names already dropped it, which is fine.

## Four rules the code depends on

These are not style preferences — each one exists because breaking it caused a real bug.

**All timeline interpretation belongs in `minimax_plan.py`.** The Director node, the
`/minimax_director/compile_prompt` endpoint behind the live COMPILED PROMPT panel, and any
future consumer share it. That panel is only trustworthy because it cannot disagree with
what actually gets encoded. Duplicating planning logic into JavaScript or into a node
breaks that guarantee silently, which is the worst way for it to break.

**Prompt wording comes from MiniMax's guides, verbatim.** `VIDEO_PROMPT_WRITING_GUIDE_base_en.md`
and `..._ref_en.md` on the model's Hugging Face page are the source. The model was trained
on that text, so it is reproduced as written — including where the guides are internally
inconsistent. If a prompt string looks wrong, check the guide before changing it; that
sentence is probably a quote.

**The frontend coexists with the upstream LTX Director pack.** `js/minimax_director.js` is
a fork of `ltx_director.js`, and around 93 % of it is still unchanged upstream code, so
someone can easily have both packs loaded at once. HTTP routes are therefore namespaced
`/minimax_director*` (duplicate aiohttp routes collide outright), the CSS prefix is
`mmxd-`, and the `<style>` element has its own id. Two packs sharing one style element
means whichever loads last overwrites the other, which is exactly what used to happen.

That figure is about the editor file alone, and it is worth being precise about which way
it cuts: the backend — every `minimax_*.py`, roughly 3,500 lines — is new, and so are the
preview widget and the title healer. Across the package it is about 70 % inherited editor
and 30 % written here. Either way it is a derivative work of a GPL-3.0 project, which is
why the licence is not a choice.

**`toSave` in `js/minimax_director.js` is an allowlist.** Anything you add to the timeline
state must be listed there *and* in `parseInitial`, or it is silently dropped on the next
edit — which looks like the field working, right up until someone moves a segment.

## Licence and credit

This pack is **GPL-3.0**, and so is anything contributed to it. The timeline editor is a
fork of [LTX Director](https://github.com/WhatDreamsCost/WhatDreamsCost-ComfyUI) by
**WhatDreamsCost**, by way of the CS fork by **CGlide**. Those credits in the README and in
the file headers stay where they are.

## What happens to your pull request

It gets read, and you get an answer either way. Small, focused changes are easier to say
yes to than large ones — if you are planning something big, open an issue first so the
design can be agreed before you spend the time. A change that does not fit is not a
judgement on the work; sometimes it just pulls against something above.
