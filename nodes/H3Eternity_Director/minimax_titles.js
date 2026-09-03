// Drop the old " CS" suffix from nodes that were placed before the rename.
//
// LiteGraph serialises a node's title into the workflow, so a node created while the
// display name still ended in "CS" keeps showing it forever — renaming the node class
// does not reach back into saved graphs. This rewrites those stale titles on load, but
// only when the title is exactly the old default: a title the user typed themselves is
// theirs to keep.

const { app } = window.comfyAPI.app;

const RENAMED = {
  H3Eternity_Director: "H3 Eternity - Director",
  H3Eternity_PreviewOverride: "H3 Eternity - Preview Override",
  H3Eternity_RetakeStitch: "H3 Eternity - Retake Stitch",
  H3Eternity_EnhancePrompt: "H3 Eternity - Enhance Prompt",
  H3Eternity_SaveLastFrame: "H3 Eternity - Save Last Frame",
  H3Eternity_SeamlessSampler: "H3 Eternity - Seamless Sampler [experimental]",
  H3Eternity_Ref2VA: "H3 Eternity - Ref2VA",
  H3Eternity_SaveVideo: "H3 Eternity - Save Video",
  MiniMaxH3Director_Eternity: "H3 Eternity - Director",
  MiniMaxH3PreviewOverride_Eternity: "H3 Eternity - Preview Override",
  MiniMaxH3RetakeStitch_Eternity: "H3 Eternity - Retake Stitch",
  MiniMaxH3DirectorChain_Eternity: "H3 Eternity - Director Chain",
};

function healTitle(node) {
  const current = RENAMED[node?.type];
  if (!current || !node.title) return;
  if (node.title === current + " CS" || node.title === current + " -CS") {
    node.title = current;
    node.setDirtyCanvas?.(true, true);
  }
}

app.registerExtension({
  name: "H3Eternity.TitleCleanup",

  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (!RENAMED[nodeData.name]) return;
    const onConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function (info) {
      const out = onConfigure?.apply(this, arguments);
      healTitle(this);
      return out;
    };
  },

  // also catch graphs that were already on screen when this loaded
  async setup() {
    setTimeout(() => (app.graph?._nodes || []).forEach(healTitle), 0);
  },

  async afterConfigureGraph() {
    (app.graph?._nodes || []).forEach(healTitle);
  },
});
