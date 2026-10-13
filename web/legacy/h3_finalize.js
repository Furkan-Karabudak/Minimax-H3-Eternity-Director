import { app } from "../../../scripts/app.js";

const comfyApp = app || window.comfyAPI?.app?.app;

function updateFinalizeVisibility(node) {
  if (!node || !node.widgets) return;

  const seamAudioWidget = node.widgets.find(w => w.name === "seam_audio");
  const fadeMsWidget = node.widgets.find(w => w.name === "seam_audio_fade_ms" || w.name === "seam_fade_ms");

  if (!seamAudioWidget || !fadeMsWidget) return;

  if (!fadeMsWidget._origType) {
    fadeMsWidget._origType = fadeMsWidget.type || "number";
    fadeMsWidget._origComputeSize = fadeMsWidget.computeSize;
  }

  const isInstant = (seamAudioWidget.value === "instant");

  if (isInstant) {
    fadeMsWidget.hidden = true;
    fadeMsWidget.type = "hidden";
    fadeMsWidget.computeSize = () => [0, -4];
  } else {
    fadeMsWidget.hidden = false;
    fadeMsWidget.type = fadeMsWidget._origType;
    if (fadeMsWidget._origComputeSize) {
      fadeMsWidget.computeSize = fadeMsWidget._origComputeSize;
    } else {
      delete fadeMsWidget.computeSize;
    }
  }

  if (typeof node.computeSize === "function") {
    const minH = node.computeSize()[1];
    if (node.size && node.size[1] !== minH) {
      node.setSize([node.size[0], minH]);
    }
  }

  node.setDirtyCanvas?.(true, true);
}

if (comfyApp) {
  comfyApp.registerExtension({
    name: "H3Eternity.Finalize",
    async beforeRegisterNodeDef(nodeType, nodeData) {
      if (nodeData.name !== "H3Eternity_Finalize") return;

      const onNodeCreated = nodeType.prototype.onNodeCreated;
      nodeType.prototype.onNodeCreated = function () {
        const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;
        const seamAudioWidget = this.widgets?.find(w => w.name === "seam_audio");
        if (seamAudioWidget) {
          const origCb = seamAudioWidget.callback;
          seamAudioWidget.callback = (val) => {
            if (origCb) origCb.call(seamAudioWidget, val);
            updateFinalizeVisibility(this);
          };
        }
        setTimeout(() => updateFinalizeVisibility(this), 10);
        return r;
      };

      const onConfigure = nodeType.prototype.onConfigure;
      nodeType.prototype.onConfigure = function () {
        const r = onConfigure ? onConfigure.apply(this, arguments) : undefined;
        const seamAudioWidget = this.widgets?.find(w => w.name === "seam_audio");
        if (seamAudioWidget && !seamAudioWidget._h3Hooked) {
          const origCb = seamAudioWidget.callback;
          seamAudioWidget.callback = (val) => {
            if (origCb) origCb.call(seamAudioWidget, val);
            updateFinalizeVisibility(this);
          };
          seamAudioWidget._h3Hooked = true;
        }
        setTimeout(() => updateFinalizeVisibility(this), 20);
        return r;
      };
    }
  });
}
