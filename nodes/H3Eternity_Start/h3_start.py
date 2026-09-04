"""H3 Eternity - Start Node.

Initializes or continues an H3 Eternity iteration loop. Emits the initial or current iteration
index and passes through the active render_plan carrier.
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Tuple

try:
    from comfy_api.latest import io
    _HAVE_COMFY_API = True
except ImportError:
    _HAVE_COMFY_API = False
    class _MockComfyNode:
        pass
    io = None

from ..H3Eternity_Director.render_plan import (
    RENDER_PLAN_TYPE,
    create_render_plan,
    deserialize_render_plan,
)

_LOG = logging.getLogger("minimax_h3_eternity.start")


class H3Eternity_Start:
    """Entry point for the H3 Eternity Edition recursive rendering loop."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "optional": {
                "render_plan": (RENDER_PLAN_TYPE, {
                    "rawLink": True,
                    "tooltip": "Loopback render_plan connection from H3 Eternity - Finalize, "
                               "or omitted on initial kickoff."
                }),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
                "prompt": "PROMPT",
                "start_index": ("INT", {"default": 0}),
            }
        }

    RETURN_TYPES = (RENDER_PLAN_TYPE, "INT")
    RETURN_NAMES = ("render_plan", "index")
    OUTPUT_TOOLTIPS = (
        "Active render_plan carrying timeline configurations and current iteration state.",
        "Current iteration index (0, 1, 2, ...).",
    )
    FUNCTION = "start"
    CATEGORY = "MiniMax H3 / Eternity"
    DESCRIPTION = (
        "Starts or resumes an H3 Eternity iteration loop. Emits the active render_plan "
        "and current iteration index for Director and downstream Samplers."
    )

    def start(
        self,
        render_plan: Optional[dict[str, Any]] = None,
        unique_id: Optional[str] = None,
        prompt: Optional[dict[str, Any]] = None,
        start_index: Optional[int] = None,
        **kwargs: Any,
    ) -> Tuple[dict[str, Any], int]:
        node_id = str(unique_id or "start_node")
        if render_plan is None:
            # First iteration kickoff
            plan = create_render_plan(node_id=node_id)
            plan["start_node_id"] = node_id
            current_index = 0 if start_index is None else int(start_index)
            plan["current_iteration"] = current_index
            _LOG.info("[H3Eternity_Start] Initialized new render_plan at iteration %d (node_id=%s)", current_index, node_id)
        else:
            plan = deserialize_render_plan(render_plan)
            if "start_node_id" not in plan and unique_id:
                plan["start_node_id"] = node_id
            if start_index is not None and int(start_index) > 0:
                current_index = int(start_index)
                plan["current_iteration"] = current_index
            else:
                current_index = int(plan.get("current_iteration", 0))
            _LOG.info(
                "[H3Eternity_Start] Continuing render_plan at iteration %d/%d (node_id=%s)",
                current_index, int(plan.get("total_iterations", 1)), plan.get("start_node_id", node_id)
            )

        return (plan, current_index)


# Modern ComfyUI V3 Schema extension wrapper if comfy_api is present
if _HAVE_COMFY_API:
    class H3Eternity_Start_V3(H3Eternity_Start, io.ComfyNode):
        @classmethod
        def define_schema(cls):
            return io.Schema(
                node_id="H3Eternity_Start",
                display_name="H3 Eternity - Start",
                category="MiniMax H3 / Eternity",
                description=cls.DESCRIPTION,
                inputs=[
                    io.Custom(RENDER_PLAN_TYPE).Input("render_plan", optional=True,
                                    tooltip="Loopback render_plan connection from H3 Eternity - Finalize."),
                ],
                outputs=[
                    io.Custom(RENDER_PLAN_TYPE).Output(display_name="render_plan"),
                    io.Int.Output(display_name="index"),
                ],
            )

        @classmethod
        def execute(cls, render_plan=None, unique_id=None, prompt=None, start_index=None, **kwargs) -> io.NodeOutput:
            instance = cls()
            out_plan, idx = instance.start(
                render_plan=render_plan, unique_id=unique_id, prompt=prompt, start_index=start_index, **kwargs
            )
            return io.NodeOutput(out_plan, idx)
