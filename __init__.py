"""Minimax H3 Eternity Edition (incorporating Eternity Studio & Legacy Director).

This entrypoint bridges:
1. Legacy nodes (quarantined in `legacy/` for backwards compatibility until 1.0)
2. Eternity Studio (clean-slate modular production suite in `studio/`)
3. Unified Web directory (`./web`) serving both legacy JS and modern Vite/Svelte frontend bundles
"""
from comfy_api.latest import ComfyExtension, io
from typing_extensions import override

# --- 1. Quarantined Legacy Suite ---
from .legacy import (
    LEGACY_NODES,
    LEGACY_NODE_CLASS_MAPPINGS,
    LEGACY_NODE_DISPLAY_NAME_MAPPINGS,
    init_legacy_routes,
)

# --- 2. Clean-Slate Eternity Studio Suite ---
from .studio import (
    STUDIO_NODES,
    STUDIO_NODE_CLASS_MAPPINGS,
    STUDIO_NODE_DISPLAY_NAME_MAPPINGS,
    init_studio_routes,
)


class MinimaxH3DirectorEternityExtension(ComfyExtension):
    @override
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        # Returns all legacy and studio nodes
        return LEGACY_NODES + STUDIO_NODES


async def comfy_entrypoint() -> MinimaxH3DirectorEternityExtension:
    init_legacy_routes()
    init_studio_routes()
    return MinimaxH3DirectorEternityExtension()


# V1 Node Mappings (Merged)
NODE_CLASS_MAPPINGS = {
    **LEGACY_NODE_CLASS_MAPPINGS,
    **STUDIO_NODE_CLASS_MAPPINGS,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    **LEGACY_NODE_DISPLAY_NAME_MAPPINGS,
    **STUDIO_NODE_DISPLAY_NAME_MAPPINGS,
}

# Unified web directory serving legacy scripts and Eternity Studio UI
WEB_DIRECTORY = "./web"

__all__ = [
    "NODE_CLASS_MAPPINGS",
    "NODE_DISPLAY_NAME_MAPPINGS",
    "WEB_DIRECTORY",
    "comfy_entrypoint",
]
