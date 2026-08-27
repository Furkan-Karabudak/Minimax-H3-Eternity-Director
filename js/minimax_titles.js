// Drop the old " CS" suffix from nodes that were placed before the rename.
//
// LiteGraph serialises a node's title into the workflow, so a node created while the
// display name still ended in "CS" keeps showing it forever — renaming the node class
// does not reach back into saved graphs. This rewrites those stale titles on load, but
// only when the title is exactly the old default: a title the user typed themselves is
// theirs to keep.

const { app } = window.comfyAPI.app;

const RENAMED = {
  MiniMaxH3Director_Eternity: "MiniMax H3 Director",
  MiniMaxH3PreviewOverride_Eternity: "MiniMax H3 Preview Override",
  MiniMaxH3RetakeStitch_Eternity: "MiniMax H3 Retake Stitch",
  MiniMaxH3DirectorChain_Eternity: "MiniMax H3 Director Chain",
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
  name: "MiniMaxH3.TitleCleanup",

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
