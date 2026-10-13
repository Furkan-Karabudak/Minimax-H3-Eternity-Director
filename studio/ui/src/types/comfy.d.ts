export interface ComfyApp {
  registerExtension(extension: ComfyExtension): void;
  graph: any;
  canvas: any;
  ui: any;
}

export interface ComfyExtension {
  name: string;
  init?: (app: ComfyApp) => void | Promise<void>;
  setup?: (app: ComfyApp) => void | Promise<void>;
  beforeRegisterNodeDef?: (nodeType: any, nodeData: any, app: ComfyApp) => void;
  nodeCreated?: (node: any, app: ComfyApp) => void;
  loadedGraphNode?: (node: any, app: ComfyApp) => void;
  settings?: any[];
}

declare global {
  interface Window {
    app?: ComfyApp;
    comfyAPI?: {
      app?: {
        app?: ComfyApp;
      };
    };
  }
}
