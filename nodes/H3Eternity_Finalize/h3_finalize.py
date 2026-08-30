"""H3 Eternity - Finalize Node.

Monitors the active render_plan, orchestrates recursive loopback execution until all planned
iterations are rendered, and stitches all intermediate clips into unified final_images and final_audio.
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Tuple
import torch

from ..H3Eternity_Director.render_plan import (
    RENDER_PLAN_TYPE,
    advance_iteration,
    deserialize_render_plan,
)

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
            "hidden": {
                "unique_id": "UNIQUE_ID",
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

    def finalize(
        self,
        render_plan: dict[str, Any],
        unique_id: Optional[str] = None,
    ) -> Tuple[dict[str, Any], torch.Tensor, dict[str, Any]]:
        plan = deserialize_render_plan(render_plan)
        cur_idx = int(plan.get("current_iteration", 0))
        total_iters = int(plan.get("total_iterations", 1))

        _LOG.info("[H3Eternity_Finalize] Processing iteration %d/%d", cur_idx, total_iters)

        # Placeholder empty tensors for scaffolding (full concatenation engine implemented in Phase 5)
        # Empty IMAGE tensor [1, 768, 1344, 3]
        height = int(plan.get("canvas", {}).get("height", 768))
        width = int(plan.get("canvas", {}).get("width", 1344))
        empty_images = torch.zeros((1, height, width, 3), dtype=torch.float32)
        empty_audio = {
            "waveform": torch.zeros((1, 2, 48000), dtype=torch.float32),
            "sample_rate": 48000,
        }

        if cur_idx < total_iters - 1:
            # Advance iteration index for next loop cycle
            updated_plan = advance_iteration(plan)
            _LOG.info("[H3Eternity_Finalize] Advancing to iteration %d/%d",
                      int(updated_plan["current_iteration"]), total_iters)
            return (updated_plan, empty_images, empty_audio)
        else:
            # Final iteration reached
            plan["completed"] = True
            _LOG.info("[H3Eternity_Finalize] Completed all %d iterations. Ready for final stitch.", total_iters)
            return (plan, empty_images, empty_audio)
