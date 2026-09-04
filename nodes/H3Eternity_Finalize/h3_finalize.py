"""H3 Eternity - Finalize Node.

Monitors the active render_plan, orchestrates recursive loopback execution until all planned
iterations are rendered, and stitches all intermediate clips into unified final_images and final_audio.
"""

from __future__ import annotations

import copy
import logging
from typing import Any, Dict, List, Optional, Tuple
import torch

try:
    from comfy_api.latest import io
    _HAVE_COMFY_API = True
except ImportError:
    _HAVE_COMFY_API = False
    class _MockComfyNode:
        pass
    io = None

# ComfyUI Dynamic Graph Execution Support
try:
    from comfy_execution.graph_utils import GraphBuilder, is_link
    _HAVE_GRAPH_BUILDER = True
except ImportError:
    def is_link(obj: Any) -> bool:
        """Check if an object represents a ComfyUI graph wire [node_id, socket_idx]."""
        if not isinstance(obj, list) or len(obj) != 2:
            return False
        return isinstance(obj[0], str) and isinstance(obj[1], (int, float))

    class _FallbackNode:
        def __init__(self, node_id: str, class_type: str, inputs: dict):
            self.id = node_id
            self.class_type = class_type
            self.inputs = copy.deepcopy(inputs)
            self.override_display_id = None

        def out(self, index: int) -> list:
            return [self.id, int(index)]

        def set_input(self, key: str, value: Any) -> None:
            if value is None:
                self.inputs.pop(key, None)
            else:
                self.inputs[key] = value

        def get_input(self, key: str) -> Any:
            return self.inputs.get(key)

        def set_override_display_id(self, override_display_id: str) -> None:
            self.override_display_id = override_display_id

        def serialize(self) -> dict:
            serialized = {
                "class_type": self.class_type,
                "inputs": self.inputs,
            }
            if self.override_display_id is not None:
                serialized["override_display_id"] = self.override_display_id
            return serialized

    class GraphBuilder:
        """Fallback implementation of ComfyUI GraphBuilder for test harnesses."""
        _default_prefix_call_index = 0

        def __init__(self, prefix: Optional[str] = None):
            if prefix is None:
                GraphBuilder._default_prefix_call_index += 1
                self.prefix = f"g.{GraphBuilder._default_prefix_call_index}."
            else:
                self.prefix = prefix
            self.nodes: Dict[str, _FallbackNode] = {}
            self.id_gen = 1

        def node(self, class_type: str, id: Optional[str] = None, **kwargs: Any) -> _FallbackNode:
            if id is None:
                id = str(self.id_gen)
                self.id_gen += 1
            full_id = self.prefix + id
            if full_id in self.nodes:
                return self.nodes[full_id]
            node_obj = _FallbackNode(full_id, class_type, kwargs)
            self.nodes[full_id] = node_obj
            return node_obj

        def lookup_node(self, id: str) -> Optional[_FallbackNode]:
            full_id = self.prefix + id
            return self.nodes.get(full_id)

        def finalize(self) -> dict:
            output = {}
            for node_id, n in self.nodes.items():
                output[node_id] = n.serialize()
            return output

    _HAVE_GRAPH_BUILDER = True

from ..H3Eternity_Director.render_plan import (
    RENDER_PLAN_TYPE,
    advance_iteration,
    deserialize_render_plan,
    serialize_render_plan,
)
from .stitch_engine import assemble_multi_clip

_LOG = logging.getLogger("minimax_h3_eternity.finalize")


class H3Eternity_Finalize:
    """Recursion controller and multi-iteration stitcher for H3 Eternity."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "render_plan": (RENDER_PLAN_TYPE, {
                    "tooltip": "Active render_plan from downstream H3 Eternity Sampler."
                }),
            },
            "optional": {
                "seam_audio": (["smartseam", "crossfade", "declick", "hard_cut"], {
                    "default": "smartseam",
                    "tooltip": "Audio stitching strategy across iteration seams: "
                               "smartseam (hides seam at quietest RMS point), "
                               "crossfade (full-overlap equal-power blend), "
                               "declick (12ms boundary smoothing), "
                               "hard_cut (abrupt transition for scene changes)."
                }),
                "trim_head_overlap": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "Automatically drop duplicate head overlap frames on continuation "
                               "iterations (O frames). Keep True for smooth, stutter-free playback."
                }),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
                "dynprompt": "DYNPROMPT",
            }
        }

    RETURN_TYPES = (RENDER_PLAN_TYPE, "IMAGE", "AUDIO")
    RETURN_NAMES = ("render_plan", "final_images", "final_audio")
    OUTPUT_TOOLTIPS = (
        "Updated render_plan (marked completed when the final iteration finishes).",
        "Fully stitched IMAGE batch across all iterations.",
        "Fully stitched and synchronized AUDIO track across all iterations.",
    )
    FUNCTION = "finalize"
    CATEGORY = "MiniMax H3 / Eternity"
    DESCRIPTION = (
        "Controls recursive iteration loopback to Start until all iterations are generated, "
        "then stitches intermediate clips end-to-end into final_images and final_audio."
    )

    def _explore_upstream(self, node_id: str, dynprompt: Any, upstream: dict[str, list[str]]) -> None:
        """Collect child-to-parent graph dependency mappings."""
        node_info = dynprompt.get_node(node_id)
        if not node_info or "inputs" not in node_info:
            return
        for k, v in node_info["inputs"].items():
            if is_link(v):
                parent_id = str(v[0])
                if parent_id not in upstream:
                    upstream[parent_id] = []
                    self._explore_upstream(parent_id, dynprompt, upstream)
                upstream[parent_id].append(str(node_id))

    def _collect_contained(self, node_id: str, upstream: dict[str, list[str]], contained: dict[str, bool]) -> None:
        """Recursively collect all node IDs between Start and Finalize."""
        if node_id not in upstream:
            return
        for child_id in upstream[node_id]:
            if child_id not in contained:
                contained[child_id] = True
                self._collect_contained(child_id, upstream, contained)

    def _find_upstream_start_node(
        self,
        dynprompt: Any,
        finalize_id: str,
        target_start_id: Optional[str] = None,
    ) -> Optional[str]:
        """Traces the active render_plan wire backwards to identify the originating H3Eternity_Start node."""
        if target_start_id:
            tid_str = str(target_start_id)
            node_info = dynprompt.get_node(tid_str)
            if node_info and ("H3Eternity_Start" in str(node_info.get("class_type", ""))):
                return tid_str

        curr = finalize_id
        visited = set()
        while curr and curr not in visited:
            visited.add(curr)
            node_info = dynprompt.get_node(curr)
            if not node_info:
                break
            cls_type = str(node_info.get("class_type", ""))
            if "H3Eternity_Start" in cls_type or cls_type == "H3Eternity_Start":
                return curr

            rplan_in = node_info.get("inputs", {}).get("render_plan")
            if is_link(rplan_in):
                curr = str(rplan_in[0])
            else:
                break
        return None

    def finalize(
        self,
        render_plan: dict[str, Any],
        seam_audio: str = "smartseam",
        trim_head_overlap: bool = True,
        unique_id: Optional[str] = None,
        dynprompt: Optional[Any] = None,
        **kwargs: Any,
    ) -> Tuple[dict[str, Any], torch.Tensor, dict[str, Any]] | dict[str, Any]:
        plan = deserialize_render_plan(render_plan)
        cur_idx = int(plan.get("current_iteration", 0))
        total_iters = int(plan.get("total_iterations", 1))

        _LOG.info("[H3Eternity_Finalize] Processing iteration %d/%d", cur_idx, total_iters)

        height = int(plan.get("canvas", {}).get("height", 768))
        width = int(plan.get("canvas", {}).get("width", 1344))
        empty_images = torch.zeros((1, height, width, 3), dtype=torch.float32)
        empty_audio = {
            "waveform": torch.zeros((1, 2, 48000), dtype=torch.float32),
            "sample_rate": 48000,
        }

        # ---------------------------------------------------------------------
        # BRANCH A: RECURSIVE LOOP CONTINUATION (cur_idx < total_iters - 1)
        # ---------------------------------------------------------------------
        if cur_idx < total_iters - 1:
            next_idx = cur_idx + 1
            updated_plan = advance_iteration(plan)
            _LOG.info("[H3Eternity_Finalize] Advancing to iteration %d/%d", next_idx, total_iters)

            # ComfyUI Dynamic GraphBuilder Expansion
            if dynprompt is not None and _HAVE_GRAPH_BUILDER and unique_id:
                try:
                    start_node_id = self._find_upstream_start_node(
                        dynprompt, str(unique_id), plan.get("start_node_id")
                    )
                    if start_node_id:
                        upstream: Dict[str, List[str]] = {}
                        self._explore_upstream(str(unique_id), dynprompt, upstream)

                        contained: Dict[str, bool] = {}
                        self._collect_contained(start_node_id, upstream, contained)
                        contained[str(unique_id)] = True
                        contained[start_node_id] = True

                        graph = GraphBuilder()
                        # 1. Clone all nodes in loop body
                        for nid in contained:
                            orig = dynprompt.get_node(nid)
                            clone_name = "Recurse" if nid == str(unique_id) else nid
                            cnode = graph.node(orig["class_type"], clone_name)
                            cnode.set_override_display_id(nid)

                        # 2. Rewire internal connections
                        for nid in contained:
                            orig = dynprompt.get_node(nid)
                            clone_name = "Recurse" if nid == str(unique_id) else nid
                            cnode = graph.lookup_node(clone_name)
                            for k, v in orig.get("inputs", {}).items():
                                if is_link(v) and str(v[0]) in contained:
                                    parent_clone_name = "Recurse" if str(v[0]) == str(unique_id) else str(v[0])
                                    parent = graph.lookup_node(parent_clone_name)
                                    cnode.set_input(k, parent.out(v[1]))
                                else:
                                    cnode.set_input(k, v)

                        # 3. Reseed the Start clone with next_idx and serialized render_plan
                        start_clone = graph.lookup_node(start_node_id)
                        start_clone.set_input("start_index", next_idx)
                        start_clone.set_input("render_plan", serialize_render_plan(updated_plan))

                        my_clone = graph.lookup_node("Recurse")
                        _LOG.info("[H3Eternity_Finalize] Successfully expanded GraphBuilder loop for iteration %d", next_idx)
                        return {
                            "result": (my_clone.out(0), my_clone.out(1), my_clone.out(2)),
                            "expand": graph.finalize(),
                        }
                except Exception as e:
                    _LOG.warning(
                        "[H3Eternity_Finalize] Dynamic graph expansion failed: %s. "
                        "Returning updated_plan for static runner fallback.", e
                    )

            # Fallback for offline tests or static runners without GraphBuilder
            return (updated_plan, empty_images, empty_audio)

        # ---------------------------------------------------------------------
        # BRANCH B: FINAL ITERATION COMPLETE (Assembly & Multi-Clip Stitching)
        # ---------------------------------------------------------------------
        _LOG.info("[H3Eternity_Finalize] Completed all %d iterations. Executing multi-clip assembly.", total_iters)
        final_images, final_audio = assemble_multi_clip(
            plan=plan,
            seam_audio=seam_audio,
            trim_head_overlap=trim_head_overlap,
            vae=plan.get("vae"),
            audio_vae=plan.get("audio_vae"),
        )
        plan["completed"] = True
        _LOG.info("[H3Eternity_Finalize] Assembly complete: %d video frames delivered.", final_images.shape[0])
        return (plan, final_images, final_audio)


# Modern ComfyUI V3 Schema extension wrapper if comfy_api is present
if _HAVE_COMFY_API:
    class H3Eternity_Finalize_V3(H3Eternity_Finalize, io.ComfyNode):
        @classmethod
        def define_schema(cls):
            return io.Schema(
                node_id="H3Eternity_Finalize",
                display_name="H3 Eternity - Finalize",
                category="MiniMax H3 / Eternity",
                description=cls.DESCRIPTION,
                inputs=[
                    io.Custom(RENDER_PLAN_TYPE).Input("render_plan", tooltip="Active render_plan from Sampler."),
                    io.Combo.Input("seam_audio", options=["smartseam", "crossfade", "declick", "hard_cut"],
                                   default="smartseam", tooltip="Audio stitching strategy across iteration seams."),
                    io.Boolean.Input("trim_head_overlap", default=True,
                                     tooltip="Drop duplicate head overlap frames on continuation shots."),
                ],
                outputs=[
                    io.Custom(RENDER_PLAN_TYPE).Output(display_name="render_plan"),
                    io.Image.Output(display_name="final_images"),
                    io.Custom("AUDIO").Output(display_name="final_audio"),
                ],
            )

        @classmethod
        def execute(
            cls,
            render_plan,
            seam_audio="smartseam",
            trim_head_overlap=True,
            unique_id=None,
            dynprompt=None,
            **kwargs,
        ) -> io.NodeOutput:
            instance = cls()
            out = instance.finalize(
                render_plan=render_plan,
                seam_audio=seam_audio,
                trim_head_overlap=trim_head_overlap,
                unique_id=unique_id,
                dynprompt=dynprompt,
                **kwargs,
            )
            if isinstance(out, dict) and "result" in out:
                return out
            return io.NodeOutput(out[0], out[1], out[2])
