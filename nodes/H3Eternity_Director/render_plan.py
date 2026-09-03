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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CutMarker:
        raw_type = str(data.get("type", data.get("cut_type", "soft"))).lower()
        norm_type = "chain" if raw_type in ("chain", "hard") else "soft"
        frame = data.get("frame_index", data.get("frame", data.get("cut_frame", 0)))
        overlap = data.get("overlap_frames", data.get("overlap_duration", data.get("overlap", DEFAULT_OVERLAP)))
        return cls(
            id=str(data.get("id", "")),
            type=norm_type,
            time_seconds=float(data.get("time_seconds", 0.0)),
            frame_index=int(frame),
            overlap_frames=int(overlap),
        )


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
    is_chain_cut: bool = False
    is_hard_cut: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IterationDefinition:
        is_chain = bool(data.get("is_chain_cut", data.get("is_hard_cut", False)))
        return cls(
            index=int(data.get("index", 0)),
            type=str(data.get("type", "initial")),
            start_frame=int(data.get("start_frame", 0)),
            end_frame=int(data.get("end_frame", 0)),
            duration_frames=int(data.get("duration_frames", 0)),
            overlap_lead_frames=int(data.get("overlap_lead_frames", 0)),
            delivered_frames=int(data.get("delivered_frames", 0)),
            prompt=str(data.get("prompt", "")),
            is_chain_cut=is_chain,
            is_hard_cut=is_chain,
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
) -> list[dict[str, Any]]:
    """Compiles a list of IterationDefinition dicts from timeline total frames and cut markers.
    
    Iteration 0: 0 -> cut[0].frame_index (or total_frames if no cuts)
    Iteration i (i >= 1): (cut[i-1].frame_index - cut[i-1].overlap_frames) -> (cut[i].frame_index or total_frames)
    """
    sorted_cuts: list[CutMarker] = []
    if cuts:
        for c in cuts:
            cm = CutMarker.from_dict(c) if isinstance(c, dict) else c
            if 0 < cm.frame_index < total_frames:
                sorted_cuts.append(cm)
        sorted_cuts.sort(key=lambda x: x.frame_index)

    iterations: list[dict[str, Any]] = []

    if not sorted_cuts:
        iterations.append(
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
            ).to_dict()
        )
        return iterations

    # First iteration: 0 -> sorted_cuts[0].frame_index
    first_end = sorted_cuts[0].frame_index
    iterations.append(
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
        ).to_dict()
    )

    # Subsequent iterations
    for i, cut in enumerate(sorted_cuts):
        iter_idx = i + 1
        overlap = cut.overlap_frames
        start_f = max(0, cut.frame_index - overlap)
        
        if iter_idx < len(sorted_cuts):
            next_cut = sorted_cuts[iter_idx]
            end_f = next_cut.frame_index
        else:
            end_f = total_frames

        dur_f = end_f - start_f
        deliv_f = end_f - cut.frame_index
        is_chain = (cut.type.lower() in ("chain", "hard"))
        cut_type_str = "chain_iteration_cut" if is_chain else "soft_iteration_cut"

        iterations.append(
            IterationDefinition(
                index=iter_idx,
                type=cut_type_str,
                start_frame=start_f,
                end_frame=end_f,
                duration_frames=dur_f,
                overlap_lead_frames=overlap,
                delivered_frames=deliv_f,
                prompt=default_prompt,
                is_chain_cut=is_chain,
                is_hard_cut=is_chain,
            ).to_dict()
        )

    return iterations


def create_render_plan(
    node_id: str = "default",
    video_name_template: Optional[str] = None,
    width: int = 1344,
    height: int = 768,
    fps: float = 24.0,
    total_frames: int = 124,
    cuts: Optional[list[dict[str, Any] | CutMarker]] = None,
    iterations: Optional[list[dict[str, Any] | IterationDefinition]] = None,
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
        iters_list = compile_iterations_from_cuts(total_frames, cuts_list, fps=fps)

    total_iters = len(iters_list) if iters_list else 1

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
        "current_conditioning": None,
        "current_latent": None,
        "saved_artifacts": [],
        "completed": False,
    }


def serialize_render_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Extract a pure JSON-serializable copy of render_plan, omitting raw PyTorch tensors."""
    clean = copy.deepcopy(plan)
    clean.pop("current_conditioning", None)
    clean.pop("current_latent", None)
    return clean


def deserialize_render_plan(data: dict[str, Any]) -> dict[str, Any]:
    """Restore and validate a render_plan dictionary."""
    if not isinstance(data, dict):
        raise ValueError(f"render_plan must be a dictionary, got {type(data)}")
    
    plan = copy.deepcopy(data)
    plan.setdefault("version", RENDER_PLAN_VERSION)
    plan.setdefault("video_name", "vid_unnamed")
    plan.setdefault("node_id", "default")
    plan.setdefault("total_iterations", 1)
    plan.setdefault("current_iteration", 0)
    plan.setdefault("canvas", {"width": 1344, "height": 768, "fps": 24.0})
    plan.setdefault("cuts", [])
    plan.setdefault("iterations", [])
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
            _LOG.warning(f"Iteration duration {dur} does not strictly satisfy 17k+5 lattice rule.")

        overlap = int(it.get("overlap_lead_frames", 0))
        if overlap > 0 and overlap not in VALID_OVERLAPS:
            raise ValueError(f"overlap_lead_frames ({overlap}) must be one of {VALID_OVERLAPS}")


def get_current_iteration(plan: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Return the iteration dictionary for the active current_iteration index."""
    iterations = plan.get("iterations", [])
    current_idx = int(plan.get("current_iteration", 0))
    if 0 <= current_idx < len(iterations):
        return iterations[current_idx]
    return None


def advance_iteration(plan: dict[str, Any]) -> dict[str, Any]:
    """Advance current_iteration by 1, updating completion state."""
    new_plan = copy.copy(plan)
    cur = int(new_plan.get("current_iteration", 0))
    total = int(new_plan.get("total_iterations", 1))

    next_idx = cur + 1
    new_plan["current_iteration"] = next_idx
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
