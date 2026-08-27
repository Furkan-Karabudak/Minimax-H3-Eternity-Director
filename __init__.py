from comfy_api.latest import ComfyExtension, io
from typing_extensions import override

from .minimax_director import MiniMaxH3Director
from .minimax_enhance import MiniMaxH3EnhancePrompt
from .minimax_lastframe import MiniMaxH3SaveLastFrame
from .minimax_preview import MiniMaxH3PreviewOverride
from .minimax_ref2v_latent_test import MiniMaxH3ReferenceToVideo_test
from .minimax_retake import MiniMaxH3RetakeStitch
from .minimax_seamless import MiniMaxH3SeamlessSampler
from .minimax_save_video import H3_Eternity_Save_Video

# MiniMaxH3DirectorChain is deliberately NOT registered — see minimax_chain.py.
# The backend works; there is no usable way to give it a timeline, so it is withdrawn
# rather than shipped as a feature nobody can operate.


from . import minimax_media as media

class MinimaxH3DirectorEternityExtension(ComfyExtension):
    @override
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [MiniMaxH3Director, MiniMaxH3PreviewOverride,
                MiniMaxH3RetakeStitch, MiniMaxH3EnhancePrompt,
                MiniMaxH3SaveLastFrame, MiniMaxH3SeamlessSampler,
                MiniMaxH3ReferenceToVideo_test, H3_Eternity_Save_Video]


async def comfy_entrypoint() -> MinimaxH3DirectorEternityExtension:
    media._try_register_routes()
    return MinimaxH3DirectorEternityExtension()


NODE_CLASS_MAPPINGS = {
    "MiniMaxH3Director_Eternity": MiniMaxH3Director,
    "MiniMaxH3PreviewOverride_Eternity": MiniMaxH3PreviewOverride,
    "MiniMaxH3RetakeStitch_Eternity": MiniMaxH3RetakeStitch,
    "MiniMaxH3EnhancePrompt_Eternity": MiniMaxH3EnhancePrompt,
    "MiniMaxH3SaveLastFrame_Eternity": MiniMaxH3SaveLastFrame,
    "MiniMaxH3SeamlessSampler_Eternity": MiniMaxH3SeamlessSampler,
    "MiniMaxH3ReferenceToVideo_test": MiniMaxH3ReferenceToVideo_test,
    "H3_Eternity_Save_Video": H3_Eternity_Save_Video,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MiniMaxH3Director_Eternity": "MiniMax H3 Director - Eternity Edition",
    "MiniMaxH3PreviewOverride_Eternity": "MiniMax H3 Preview Override - Eternity Edition",
    "MiniMaxH3RetakeStitch_Eternity": "MiniMax H3 Retake Stitch - Eternity Edition",
    "MiniMaxH3EnhancePrompt_Eternity": "MiniMax H3 Enhance Prompt - Eternity Edition",
    "MiniMaxH3SaveLastFrame_Eternity": "MiniMax H3 Save Last Frame - Eternity Edition",
    "MiniMaxH3SeamlessSampler_Eternity": "MiniMax H3 Seamless Sampler (experimental) - Eternity Edition",
    "MiniMaxH3ReferenceToVideo_test": "MiniMax H3 Reference to Video test - Eternity Edition",
    "H3_Eternity_Save_Video": "H3 Eternity - Save Video",
}

WEB_DIRECTORY = "./js"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
