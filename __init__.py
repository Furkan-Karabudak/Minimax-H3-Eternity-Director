from comfy_api.latest import ComfyExtension, io
from typing_extensions import override

from .nodes.H3Eternity_Director.minimax_director import MiniMaxH3Director
from .nodes.H3Eternity_EnhancePrompt.minimax_enhance import MiniMaxH3EnhancePrompt
from .nodes.H3Eternity_SaveLastFrame.minimax_lastframe import MiniMaxH3SaveLastFrame
from .nodes.H3Eternity_PreviewOverride.minimax_preview import MiniMaxH3PreviewOverride
from .nodes.H3Eternity_Ref2VA.minimax_ref2v_latent_test import MiniMaxH3ReferenceToVideo_test
from .nodes.H3Eternity_RetakeStitch.minimax_retake import MiniMaxH3RetakeStitch
from .nodes.H3Eternity_SeamlessSampler.minimax_seamless import MiniMaxH3SeamlessSampler
from .nodes.H3Eternity_SaveVideo.minimax_save_video import H3_Eternity_Save_Video

from .nodes.H3Eternity_Director import minimax_media as media

class MinimaxH3DirectorEternityExtension(ComfyExtension):
    @override
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [
            MiniMaxH3Director,
            MiniMaxH3PreviewOverride,
            MiniMaxH3RetakeStitch,
            MiniMaxH3EnhancePrompt,
            MiniMaxH3SaveLastFrame,
            MiniMaxH3SeamlessSampler,
            MiniMaxH3ReferenceToVideo_test,
            H3_Eternity_Save_Video,
        ]


async def comfy_entrypoint() -> MinimaxH3DirectorEternityExtension:
    media._try_register_routes()
    return MinimaxH3DirectorEternityExtension()


NODE_CLASS_MAPPINGS = {
    "H3Eternity_Director": MiniMaxH3Director,
    "H3Eternity_PreviewOverride": MiniMaxH3PreviewOverride,
    "H3Eternity_RetakeStitch": MiniMaxH3RetakeStitch,
    "H3Eternity_EnhancePrompt": MiniMaxH3EnhancePrompt,
    "H3Eternity_SaveLastFrame": MiniMaxH3SaveLastFrame,
    "H3Eternity_SeamlessSampler": MiniMaxH3SeamlessSampler,
    "H3Eternity_Ref2VA": MiniMaxH3ReferenceToVideo_test,
    "H3Eternity_SaveVideo": H3_Eternity_Save_Video,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "H3Eternity_Director": "H3 Eternity - Director",
    "H3Eternity_PreviewOverride": "H3 Eternity - Preview Override",
    "H3Eternity_RetakeStitch": "H3 Eternity - Retake Stitch",
    "H3Eternity_EnhancePrompt": "H3 Eternity - Enhance Prompt",
    "H3Eternity_SaveLastFrame": "H3 Eternity - Save Last Frame",
    "H3Eternity_SeamlessSampler": "H3 Eternity - Seamless Sampler [experimental]",
    "H3Eternity_Ref2VA": "H3 Eternity - Ref2VA",
    "H3Eternity_SaveVideo": "H3 Eternity - Save Video",
}

WEB_DIRECTORY = "./nodes"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
