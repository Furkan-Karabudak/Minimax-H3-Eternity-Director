"""Core protocol and data structure definitions for H3 Eternity Edition render_plan.

This module defines the schema, serialization, invariant validation, and instance-specific
timestamp locking engine used across H3 Eternity nodes (Start, Director, Sampler, Finalize).
"""

from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field
from datetime import datetime
import json
import logging
import os
import re
from typing import Any, Optional

_LOG = logging.getLogger("minimax_h3_eternity.render_plan")

RENDER_PLAN_TYPE = "RENDER_PLAN"
RENDER_PLAN_VERSION = "1.0.0"

# H3 Frame lattice invariants
VALID_OVERLAPS = (1, 5, 22, 39)
VALID_CONTINUATION_MODES = ("in_latent_freeze", "hybrid_keyframes", "golden_experience")
VALID_AUDIO_ANCHOR_MODES = ("in_latent_freeze + ref", "in_latent_freeze", "golden_experience", "ref", "overlap", "before", "off")
DEFAULT_OVERLAP = 22
DEFAULT_VIDEO_NAME_TEMPLATE = "vid_${date:yyyy-MM-dd}_${date:hh-mm-ss}"
DEFAULT_VIDEO_FORMAT = "video/ffv1-mkv"
DEFAULT_PIX_FMT = "bgra"
DEFAULT_AUDIO_FORMAT = "FLAC"

# Registry for per-node-instance timestamp locking
_NODE_INSTANCE_TIMESTAMPS: dict[str, datetime] = {}


def resolve_video_name(
    template: Optional[str],
    node_id: Optional[str] = None,
    custom_timestamp: Optional[datetime] = None,
) -> str:
    """Expand date/time tokens in video_name and lock them per Director node instance.

    Supported tokens:
        ${date:yyyy-MM-dd} -> 2026-08-30
        ${date:hh-mm-ss}   -> 19-30-00
        ${date:yyyy}       -> 2026
        ${date:MM}         -> 08
        ${date:dd}         -> 30
        ${date:hh}         -> 19
        ${date:mm}         -> 30
        ${date:ss}         -> 00

    Args:
        template: Pattern string, e.g. "vid_${date:yyyy-MM-dd}_${date:hh-mm-ss}".
                  If blank/whitespace, falls back to DEFAULT_VIDEO_NAME_TEMPLATE.
        node_id: Unique string identifier of the originating node instance.
        custom_timestamp: Optional explicit datetime to use.

    Returns:
        Expanded string with locked timestamp.
    """
    pattern = (template or "").strip()
    if not pattern:
        pattern = DEFAULT_VIDEO_NAME_TEMPLATE

    # Determine or retrieve instance locked timestamp
    key = str(node_id or "default_node")
    if custom_timestamp is not None:
        dt = custom_timestamp
    elif key in _NODE_INSTANCE_TIMESTAMPS:
        dt = _NODE_INSTANCE_TIMESTAMPS[key]
    else:
        dt = datetime.now()
        _NODE_INSTANCE_TIMESTAMPS[key] = dt

    # Replacements
    token_map = {
        r"\$\{date:yyyy-MM-dd\}": dt.strftime("%Y-%m-%d"),
        r"\$\{date:hh-mm-ss\}": dt.strftime("%H-%M-%S"),
        r"\$\{date:yyyy\}": dt.strftime("%Y"),
        r"\$\{date:MM\}": dt.strftime("%m"),
        r"\$\{date:dd\}": dt.strftime("%d"),
        r"\$\{date:hh\}": dt.strftime("%H"),
        r"\$\{date:mm\}": dt.strftime("%M"),
        r"\$\{date:ss\}": dt.strftime("%S"),
    }

    result = pattern
    for token_regex, val in token_map.items():
        result = re.sub(token_regex, val, result)

    # Sanitize invalid characters for filenames
    result = re.sub(r'[\\/:*?"<>|]', "_", result)
    return result


def clear_node_timestamp_cache(node_id: Optional[str] = None) -> None:
    """Clear timestamp cache for a specific node or all nodes."""
    if node_id is not None:
        _NODE_INSTANCE_TIMESTAMPS.pop(str(node_id), None)
    else:
        _NODE_INSTANCE_TIMESTAMPS.clear()


@dataclass
class CutMarker:
    """Represents a timeline cut point between iterations."""
    id: str
    type: str  # "soft" (Soft Iteration Cut) | "chain" (Chain Iteration Cut)
    time_seconds: float
    frame_index: int
    overlap_frames: int = DEFAULT_OVERLAP
    audio_overlap_frames: int = DEFAULT_OVERLAP

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CutMarker:
        raw_type = str(data.get("type", data.get("cut_type", "soft"))).lower()
        norm_type = "chain" if raw_type in ("chain", "hard") else "soft"
        frame = int(data.get("frame_index", data.get("frame", data.get("cut_frame", 0))))
        overlap = int(data.get("overlap_frames", data.get("overlap_duration", data.get("overlap", DEFAULT_OVERLAP))))
        
        # Audio overlap is unified with video overlap frames
        audio_overlap = overlap

        return cls(
            id=str(data.get("id", "")),
            type=norm_type,
            time_seconds=float(data.get("time_seconds", 0.0)),
            frame_index=frame,
            overlap_frames=overlap,
            audio_overlap_frames=audio_overlap,
        )


def generate_iteration_seeds(master_seed: int, count: int) -> list[int]:
    """Generates `count` deterministic 64-bit pseudo-random seeds using SplitMix64."""
    state = int(master_seed or 0) & 0xFFFFFFFFFFFFFFFF
    seeds = []
    for _ in range(count):
        state = (state + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
        z = state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
        z = (z ^ (z >> 31)) & 0xFFFFFFFFFFFFFFFF
        seeds.append(z)
    return seeds


@dataclass
class IterationDefinition:
    """Defines a single iteration window slice on the timeline."""
    index: int
    type: str  # "initial" | "soft_iteration_cut" | "chain_iteration_cut"
    start_frame: int
    end_frame: int
    duration_frames: int
    overlap_lead_frames: int
    delivered_frames: int
    prompt: str
    audio_overlap_lead_frames: int = DEFAULT_OVERLAP
    is_chain_cut: bool = False
    is_hard_cut: bool = False
    seed: int = 0
    temporal_offset_seconds: float = 0.0
    rope_offset: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IterationDefinition:
        is_chain = bool(data.get("is_chain_cut", data.get("is_hard_cut", False)))
        overlap_lead = int(data.get("overlap_lead_frames", 0))
        return cls(
            index=int(data.get("index", 0)),
            type=str(data.get("type", "initial")),
            start_frame=int(data.get("start_frame", 0)),
            end_frame=int(data.get("end_frame", 0)),
            duration_frames=int(data.get("duration_frames", 0)),
            overlap_lead_frames=overlap_lead,
            delivered_frames=int(data.get("delivered_frames", 0)),
            prompt=str(data.get("prompt", "")),
            audio_overlap_lead_frames=int(data.get("audio_overlap_lead_frames", overlap_lead)),
            is_chain_cut=is_chain,
            is_hard_cut=is_chain,
            seed=int(data.get("seed", 0)),
            temporal_offset_seconds=float(data.get("temporal_offset_seconds", 0.0)),
            rope_offset=float(data.get("rope_offset", 0.0)),
        )


@dataclass
class SavedArtifact:
    """Records an intermediate saved artifact (latent, video/media, audio) per iteration."""
    iteration: int
    latent_path: str
    media_path: str
    audio_path: str
    seed: int
    format: str = DEFAULT_VIDEO_FORMAT
    pix_fmt: str = DEFAULT_PIX_FMT
    audio_format: str = DEFAULT_AUDIO_FORMAT
    delivered_frames: int = 124

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SavedArtifact:
        return cls(
            iteration=int(data.get("iteration", 0)),
            latent_path=str(data.get("latent_path", "")),
            media_path=str(data.get("media_path", "")),
            audio_path=str(data.get("audio_path", "")),
            seed=int(data.get("seed", 0)),
            format=str(data.get("format", DEFAULT_VIDEO_FORMAT)),
            pix_fmt=str(data.get("pix_fmt", DEFAULT_PIX_FMT)),
            audio_format=str(data.get("audio_format", DEFAULT_AUDIO_FORMAT)),
            delivered_frames=int(data.get("delivered_frames", 124)),
        )


def compile_iterations_from_cuts(
    total_frames: int,
    cuts: Optional[list[dict[str, Any] | CutMarker]] = None,
    fps: float = 24.0,
    default_prompt: str = "",
    temporal_rope_mode: str = "dynamic_spread_natural",
    eternity_seed: int = 0,
    override_video_overlap: Optional[int] = None,
    override_audio_overlap: Optional[int] = None,
) -> list[dict[str, Any]]:
    """Compiles a list of IterationDefinition dicts from timeline total frames and cut markers.

    Calculates deterministic seeds (SplitMix64) and 3D-RoPE temporal offsets (12.0s ceiling)
    for each iteration. Supports overriding video and audio overlaps globally (e.g. for golden_experience).
    """
    sorted_cuts: list[CutMarker] = []
    if cuts:
        for c in cuts:
            cm = CutMarker.from_dict(c) if isinstance(c, dict) else c
            if 0 < cm.frame_index < total_frames:
                sorted_cuts.append(cm)
        sorted_cuts.sort(key=lambda x: x.frame_index)

    raw_iterations: list[IterationDefinition] = []

    if not sorted_cuts:
        raw_iterations.append(
            IterationDefinition(
                index=0,
                type="initial",
                start_frame=0,
                end_frame=total_frames,
                duration_frames=total_frames,
                overlap_lead_frames=0,
                delivered_frames=total_frames,
                prompt=default_prompt,
                is_chain_cut=False,
                is_hard_cut=False,
            )
        )
    else:
        # First iteration: 0 -> sorted_cuts[0].frame_index
        first_end = sorted_cuts[0].frame_index
        raw_iterations.append(
            IterationDefinition(
                index=0,
                type="initial",
                start_frame=0,
                end_frame=first_end,
                duration_frames=first_end,
                overlap_lead_frames=0,
                delivered_frames=first_end,
                prompt=default_prompt,
                is_chain_cut=False,
                is_hard_cut=False,
            )
        )

        # Subsequent iterations
        for i, cut in enumerate(sorted_cuts):
            iter_idx = i + 1
            overlap = int(override_video_overlap) if override_video_overlap is not None else cut.overlap_frames
            start_f = max(0, cut.frame_index - overlap)
            audio_overlap = int(override_audio_overlap) if override_audio_overlap is not None else cut.overlap_frames

            if iter_idx < len(sorted_cuts):
                next_cut = sorted_cuts[iter_idx]
                end_f = next_cut.frame_index
            else:
                end_f = total_frames

            dur_f = end_f - start_f
            deliv_f = end_f - cut.frame_index
            is_chain = (cut.type.lower() in ("chain", "hard"))
            cut_type_str = "chain_iteration_cut" if is_chain else "soft_iteration_cut"

            raw_iterations.append(
                IterationDefinition(
                    index=iter_idx,
                    type=cut_type_str,
                    start_frame=start_f,
                    end_frame=end_f,
                    duration_frames=dur_f,
                    overlap_lead_frames=overlap,
                    delivered_frames=deliv_f,
                    prompt=default_prompt,
                    audio_overlap_lead_frames=audio_overlap,
                    is_chain_cut=is_chain,
                    is_hard_cut=is_chain,
                )
            )

    # Calculate deterministic SplitMix64 seeds per iteration
    num_iters = len(raw_iterations)
    seeds = generate_iteration_seeds(eternity_seed, num_iters)

    # 3D-RoPE Temporal Coordinate Calculations (12.0s Ceiling)
    MAX_ROPE_SEC = 12.0
    ROPE_HZ = 40.0

    dur_secs = [it.duration_frames / fps for it in raw_iterations]
    phys_starts = [it.start_frame / fps for it in raw_iterations]
    total_phys_end = (raw_iterations[-1].end_frame / fps) if raw_iterations else 0.0

    t_offsets: list[float] = [0.0] * num_iters

    if temporal_rope_mode == "static":
        t_offsets = [0.0] * num_iters
    elif temporal_rope_mode == "dynamic_spread_full":
        # Spans exactly 12.0s with uniform gap/overlap g across all transitions
        if num_iters <= 1:
            t_offsets = [0.0]
        else:
            sum_d = sum(dur_secs)
            g = (MAX_ROPE_SEC - sum_d) / float(num_iters - 1)
            cur_t = 0.0
            t_offsets[0] = 0.0
            for k in range(num_iters - 1):
                cur_t = max(0.0, cur_t + dur_secs[k] + g)
                t_offsets[k + 1] = cur_t
    elif temporal_rope_mode == "dynamic_spread_natural":
        # If natural end <= 12s, use exact natural timeline;
        # if natural end > 12s, smoothly compress using uniform inter-iteration overlap to end at 12s
        if total_phys_end <= MAX_ROPE_SEC or num_iters <= 1:
            t_offsets = [round(ps, 4) for ps in phys_starts]
        else:
            sum_d = sum(dur_secs)
            g = (MAX_ROPE_SEC - sum_d) / float(num_iters - 1)
            cur_t = 0.0
            t_offsets[0] = 0.0
            for k in range(num_iters - 1):
                cur_t = max(0.0, cur_t + dur_secs[k] + g)
                t_offsets[k + 1] = cur_t
    elif temporal_rope_mode == "timeline_sync":
        # 1:1 natural time, clamped at 12.0s ceiling
        t_offsets = [min(ps, max(0.0, MAX_ROPE_SEC - dur_secs[k])) for k, ps in enumerate(phys_starts)]
    elif temporal_rope_mode == "wrap":
        # Modulo 12.0s wrap
        t_offsets = [round(ps % MAX_ROPE_SEC, 4) for ps in phys_starts]
    else:
        # Default fallback to physical start
        t_offsets = [round(ps, 4) for ps in phys_starts]

    compiled_list: list[dict[str, Any]] = []
    for k in range(num_iters):
        it = raw_iterations[k]
        it.seed = seeds[k]
        it.temporal_offset_seconds = max(0.0, round(t_offsets[k], 4))
        it.rope_offset = round(it.temporal_offset_seconds * ROPE_HZ, 4)
        compiled_list.append(it.to_dict())

    return compiled_list


def create_render_plan(
    node_id: str = "default",
    video_name_template: Optional[str] = None,
    width: int = 1344,
    height: int = 768,
    fps: float = 24.0,
    total_frames: int = 124,
    cuts: Optional[list[dict[str, Any] | CutMarker]] = None,
    iterations: Optional[list[dict[str, Any] | IterationDefinition]] = None,
    temporal_rope_mode: str = "dynamic_spread_natural",
    eternity_seed: int = 0,
    audio_anchor_mode: str = "in_latent_freeze + ref",
    audio_ref_duration: int = 22,
    continuation_mode: str = "in_latent_freeze",
    video_overlap_duration: int = 5,
    audio_overlap_duration: int = 22,
) -> dict[str, Any]:
    """Create a new, initialized render_plan dictionary."""
    node_id_str = str(node_id)
    creation_dt = _NODE_INSTANCE_TIMESTAMPS.get(node_id_str, datetime.now())
    if node_id_str not in _NODE_INSTANCE_TIMESTAMPS:
        _NODE_INSTANCE_TIMESTAMPS[node_id_str] = creation_dt

    video_name = resolve_video_name(video_name_template, node_id=node_id_str, custom_timestamp=creation_dt)

    cuts_list: list[dict[str, Any]] = []
    if cuts:
        for c in cuts:
            if isinstance(c, CutMarker):
                cuts_list.append(c.to_dict())
            elif isinstance(c, dict):
                cuts_list.append(c)

    iters_list: list[dict[str, Any]] = []
    if iterations is not None:
        for it in iterations:
            if isinstance(it, IterationDefinition):
                iters_list.append(it.to_dict())
            elif isinstance(it, dict):
                iters_list.append(it)
    else:
        override_v = int(video_overlap_duration) if continuation_mode == "golden_experience" else None
        override_a = int(audio_overlap_duration) if audio_anchor_mode == "golden_experience" else None
        iters_list = compile_iterations_from_cuts(
            total_frames, cuts_list, fps=fps,
            temporal_rope_mode=temporal_rope_mode,
            eternity_seed=eternity_seed,
            override_video_overlap=override_v,
            override_audio_overlap=override_a,
        )

    total_iters = len(iters_list) if iters_list else 1

    first_seed = iters_list[0].get("seed", eternity_seed) if iters_list else eternity_seed
    first_rope = iters_list[0].get("rope_offset", 0.0) if iters_list else 0.0
    first_sec = iters_list[0].get("temporal_offset_seconds", 0.0) if iters_list else 0.0

    return {
        "version": RENDER_PLAN_VERSION,
        "video_name": video_name,
        "node_id": node_id_str,
        "creation_timestamp": creation_dt.isoformat(),
        "total_iterations": total_iters,
        "current_iteration": 0,
        "canvas": {
            "width": int(width),
            "height": int(height),
            "fps": float(fps),
            "total_frames": int(total_frames),
        },
        "cuts": cuts_list,
        "iterations": iters_list,
        "temporal_rope_mode": temporal_rope_mode,
        "eternity_seed": int(eternity_seed),
        "current_seed": int(first_seed),
        "current_rope_offset": float(first_rope),
        "current_temporal_offset_seconds": float(first_sec),
        "audio_anchor_mode": str(audio_anchor_mode),
        "audio_ref_duration": int(audio_ref_duration),
        "continuation_mode": str(continuation_mode),
        "video_overlap_duration": int(video_overlap_duration),
        "audio_overlap_duration": int(audio_overlap_duration),
        "continuation_ref_mode": "latent_only",
        "current_conditioning": None,
        "current_latent": None,
        "saved_artifacts": [],
        "completed": False,
    }


def serialize_render_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Extract a pure JSON-serializable copy of render_plan, omitting raw PyTorch tensors and model objects."""
    clean = copy.copy(plan)
    clean.pop("current_conditioning", None)
    clean.pop("current_latent", None)
    clean.pop("vae", None)
    clean.pop("audio_vae", None)
    return copy.deepcopy(clean)


def deserialize_render_plan(data: Union[dict[str, Any], str]) -> dict[str, Any]:
    """Restore and validate a render_plan dictionary or JSON string."""
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception as e:
            raise ValueError(f"Failed to parse render_plan JSON string: {e}") from e
    if not isinstance(data, dict):
        raise ValueError(f"render_plan must be a dictionary, got {type(data)}")
    
    vae = data.get("vae")
    audio_vae = data.get("audio_vae")
    cond = data.get("current_conditioning")
    lat = data.get("current_latent")

    data_copy = copy.copy(data)
    data_copy.pop("vae", None)
    data_copy.pop("audio_vae", None)
    data_copy.pop("current_conditioning", None)
    data_copy.pop("current_latent", None)

    plan = copy.deepcopy(data_copy)
    if cond is not None:
        plan["current_conditioning"] = cond
    if lat is not None:
        plan["current_latent"] = lat
    if vae is not None:
        plan["vae"] = vae
    if audio_vae is not None:
        plan["audio_vae"] = audio_vae

    plan.setdefault("version", RENDER_PLAN_VERSION)
    plan.setdefault("video_name", "vid_unnamed")
    plan.setdefault("node_id", "default")
    plan.setdefault("total_iterations", 1)
    plan.setdefault("current_iteration", 0)
    plan.setdefault("canvas", {"width": 1344, "height": 768, "fps": 24.0})
    plan.setdefault("cuts", [])
    plan.setdefault("iterations", [])
    plan.setdefault("audio_anchor_mode", "in_latent_freeze + ref")
    plan.setdefault("audio_ref_duration", 22)
    plan.setdefault("continuation_mode", "in_latent_freeze")
    plan.setdefault("video_overlap_duration", 5)
    plan.setdefault("audio_overlap_duration", 22)
    plan.setdefault("continuation_ref_mode", "latent_only")
    plan.setdefault("current_conditioning", None)
    plan.setdefault("current_latent", None)
    plan.setdefault("saved_artifacts", [])
    plan.setdefault("completed", False)
    return plan


def validate_render_plan(plan: dict[str, Any]) -> None:
    """Validate render_plan invariants against H3 mathematical rules.

    Raises:
        ValueError if any invariant is violated.
    """
    if not isinstance(plan, dict):
        raise ValueError("render_plan must be a dictionary.")

    total_iters = int(plan.get("total_iterations", 0))
    current_iter = int(plan.get("current_iteration", 0))
    if total_iters < 1:
        raise ValueError(f"total_iterations must be >= 1, got {total_iters}")
    if current_iter < 0 or current_iter >= total_iters:
        raise ValueError(f"current_iteration ({current_iter}) out of bounds [0, {total_iters - 1}]")

    canvas = plan.get("canvas", {})
    width = int(canvas.get("width", 0))
    height = int(canvas.get("height", 0))
    if width <= 0 or width % 32 != 0:
        raise ValueError(f"canvas width ({width}) must be positive and divisible by 32.")
    if height <= 0 or height % 32 != 0:
        raise ValueError(f"canvas height ({height}) must be positive and divisible by 32.")

    # Validate iterations if present
    iterations = plan.get("iterations", [])
    for it in iterations:
        dur = int(it.get("duration_frames", 0))
        if dur > 0 and dur % 17 != 5:
            _LOG.warning(f"[H3.E - Director] Iteration duration {dur} does not strictly satisfy 17k+5 lattice rule.")

        overlap = int(it.get("overlap_lead_frames", 0))
        if overlap > 0 and overlap not in VALID_OVERLAPS:
            raise ValueError(f"overlap_lead_frames ({overlap}) must be one of {VALID_OVERLAPS}")

    continuation_mode = plan.get("continuation_mode", "in_latent_freeze")
    if continuation_mode not in VALID_CONTINUATION_MODES:
        raise ValueError(f"continuation_mode must be one of {VALID_CONTINUATION_MODES}, got '{continuation_mode}'")

    audio_anchor_mode = plan.get("audio_anchor_mode", "in_latent_freeze + ref")
    if audio_anchor_mode not in VALID_AUDIO_ANCHOR_MODES:
        raise ValueError(f"audio_anchor_mode must be one of {VALID_AUDIO_ANCHOR_MODES}, got '{audio_anchor_mode}'")

    audio_ref_dur = int(plan.get("audio_ref_duration", 22))
    if audio_ref_dur < 1:
        raise ValueError(f"audio_ref_duration must be >= 1, got {audio_ref_dur}")

    video_ov_dur = int(plan.get("video_overlap_duration", 5))
    if video_ov_dur not in VALID_OVERLAPS:
        raise ValueError(f"video_overlap_duration ({video_ov_dur}) must be one of {VALID_OVERLAPS}")

    audio_ov_dur = int(plan.get("audio_overlap_duration", 22))
    if audio_ov_dur < 1:
        raise ValueError(f"audio_overlap_duration must be >= 1, got {audio_ov_dur}")


def get_current_iteration(plan: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Return the iteration dictionary for the active current_iteration index."""
    iterations = plan.get("iterations", [])
    current_idx = int(plan.get("current_iteration", 0))
    if 0 <= current_idx < len(iterations):
        return iterations[current_idx]
    return None


def advance_iteration(plan: dict[str, Any]) -> dict[str, Any]:
    """Advance current_iteration by 1, updating completion state and active iteration properties."""
    new_plan = copy.copy(plan)
    cur = int(new_plan.get("current_iteration", 0))
    total = int(new_plan.get("total_iterations", 1))

    next_idx = cur + 1
    new_plan["current_iteration"] = next_idx
    iterations = new_plan.get("iterations", [])
    if 0 <= next_idx < len(iterations):
        new_plan["current_seed"] = int(iterations[next_idx].get("seed", 0))
        new_plan["current_rope_offset"] = float(iterations[next_idx].get("rope_offset", 0.0))
        new_plan["current_temporal_offset_seconds"] = float(iterations[next_idx].get("temporal_offset_seconds", 0.0))
    if next_idx >= total:
        new_plan["completed"] = True
    return new_plan


def register_saved_artifact(plan: dict[str, Any], artifact: dict[str, Any] | SavedArtifact) -> dict[str, Any]:
    """Append a saved artifact to the plan's saved_artifacts list."""
    new_plan = copy.copy(plan)
    artifacts = list(new_plan.get("saved_artifacts", []))
    if isinstance(artifact, SavedArtifact):
        artifacts.append(artifact.to_dict())
    elif isinstance(artifact, dict):
        artifacts.append(artifact)
    new_plan["saved_artifacts"] = artifacts
    return new_plan
