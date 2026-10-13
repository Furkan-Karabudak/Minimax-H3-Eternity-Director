"""Eternity Studio Modular Nodes Registry."""
from typing import Dict, Type, Any, List

# When nodes are created, they will be registered here cleanly:
# from .node_concept import EternityConceptNode
# from .node_timeline import EternityTimelineNode
# from .node_preview import EternityPreviewNode

STUDIO_NODES: List[Type[Any]] = []

STUDIO_NODE_CLASS_MAPPINGS: Dict[str, Type[Any]] = {}

STUDIO_NODE_DISPLAY_NAME_MAPPINGS: Dict[str, str] = {}
