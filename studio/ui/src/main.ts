import type { ComfyApp, ComfyExtension } from './types/comfy';
import { mount } from 'svelte';
import App from './App.svelte';

function resolveComfyApp(): ComfyApp | undefined {
  if (typeof window === 'undefined') return undefined;
  return window.comfyAPI?.app?.app || window.app;
}

const studioExtension: ComfyExtension = {
  name: "MinimaxH3.EternityStudio",

  async init(app: ComfyApp) {
    console.log("[Eternity Studio] Extension initializing (Svelte 5 + TS Suite)...");
  },

  async setup(app: ComfyApp) {
    console.log("[Eternity Studio] Extension setup ready.");
  },

  nodeCreated(node: any, app: ComfyApp) {
    // Hooks for future Eternity Studio nodes will be handled here
  }
};

// Auto-register with ComfyUI
const comfyApp = resolveComfyApp();
if (comfyApp && typeof comfyApp.registerExtension === 'function') {
  comfyApp.registerExtension(studioExtension);
} else {
  // If window.app isn't initialized yet, wait for DOMContentLoaded or polling
  window.addEventListener('DOMContentLoaded', () => {
    const delayedApp = resolveComfyApp();
    if (delayedApp && typeof delayedApp.registerExtension === 'function') {
      delayedApp.registerExtension(studioExtension);
    }
  });
}

export { studioExtension, mount, App };
