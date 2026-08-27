import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

const NODE_ID = "H3_Eternity_Save_Video";
const DEFAULT_NODE_WIDTH = 400;
const DEFAULT_NODE_HEIGHT = 460;
const PREVIEW_MIN_HEIGHT = 100;
const NODE_VERTICAL_CHROME = 70;

const AUDIO_FORMAT_MAP = {
  "animation/gif": ["WAV (external)", "MP3 (external)", "FLAC (external)", "None"],
  "animation/ffmpeg-gif": ["WAV (external)", "MP3 (external)", "FLAC (external)", "None"],
  "animation/webp": ["WAV (external)", "MP3 (external)", "FLAC (external)", "None"],
  "image_sequence/8bit-png": ["WAV (external)", "MP3 (external)", "FLAC (external)", "None"],
  "image_sequence/16bit-png": ["WAV (external)", "MP3 (external)", "FLAC (external)", "None"],
  "video/h264-mp4": ["AAC", "Opus", "MP3", "FLAC", "ALAC", "WAV (external)", "MP3 (external)", "FLAC (external)", "None"],
  "video/h265-mp4": ["AAC", "Opus", "MP3", "FLAC", "ALAC", "WAV (external)", "MP3 (external)", "FLAC (external)", "None"],
  "video/nvenc_av1-mp4": ["AAC", "Opus", "MP3", "FLAC", "ALAC", "WAV (external)", "MP3 (external)", "FLAC (external)", "None"],
  "video/nvenc_h264-mp4": ["AAC", "Opus", "MP3", "FLAC", "ALAC", "WAV (external)", "MP3 (external)", "FLAC (external)", "None"],
  "video/nvenc_hevc-mp4": ["AAC", "Opus", "MP3", "FLAC", "ALAC", "WAV (external)", "MP3 (external)", "FLAC (external)", "None"],
  "video/av1-webm": ["Opus", "Vorbis", "WAV (external)", "MP3 (external)", "FLAC (external)", "None"],
  "video/webm": ["Opus", "Vorbis", "WAV (external)", "MP3 (external)", "FLAC (external)", "None"],
  "video/ffv1-mkv": ["FLAC", "PCM 16-bit (pcm_s16le)", "PCM 24-bit (pcm_s24le)", "Opus", "AAC", "MP3", "Vorbis", "WAV (external)", "MP3 (external)", "FLAC (external)", "None"],
  "video/ProRes": ["PCM 24-bit (pcm_s24le)", "PCM 16-bit (pcm_s16le)", "PCM 32-bit float (pcm_f32le)", "ALAC", "AAC", "WAV (external)", "MP3 (external)", "FLAC (external)", "None"],
};

const DEFAULT_AUDIO_FORMAT = {
  "animation/gif": "WAV (external)",
  "animation/ffmpeg-gif": "WAV (external)",
  "animation/webp": "WAV (external)",
  "image_sequence/8bit-png": "WAV (external)",
  "image_sequence/16bit-png": "WAV (external)",
  "video/h264-mp4": "AAC",
  "video/h265-mp4": "AAC",
  "video/nvenc_av1-mp4": "AAC",
  "video/nvenc_h264-mp4": "AAC",
  "video/nvenc_hevc-mp4": "AAC",
  "video/av1-webm": "Opus",
  "video/webm": "Opus",
  "video/ffv1-mkv": "FLAC",
  "video/ProRes": "PCM 24-bit (pcm_s24le)",
};

const PIX_FMT_MAP = {
  "video/ffv1-mkv": {
    values: ["bgra", "rgba64le", "yuv420p", "yuv422p", "yuv444p", "yuva420p", "yuva422p", "yuva444p", "yuv420p10le", "yuv422p10le", "yuv444p10le", "yuv420p12le", "yuv422p12le", "yuv444p12le", "yuv420p14le", "yuv422p14le", "yuv444p14le", "yuv420p16le", "yuv422p16le", "yuv444p16le", "gray", "gray10le", "gray12le", "gray16le"],
    default: "bgra"
  },
  "video/h264-mp4": {
    values: ["yuv420p", "yuv420p10le", "yuv422p", "yuv444p", "yuv422p10le", "yuv444p10le", "nv12"],
    default: "yuv420p"
  },
  "video/h265-mp4": {
    values: ["yuv420p10le", "yuv420p", "yuv422p10le", "yuv444p10le", "yuv422p", "yuv444p"],
    default: "yuv420p10le"
  },
  "video/nvenc_h264-mp4": {
    values: ["yuv420p", "p010le", "yuv444p", "yuv444p16le", "bgr0", "rgb0"],
    default: "yuv420p"
  },
  "video/nvenc_hevc-mp4": {
    values: ["p010le", "yuv420p", "yuv444p", "yuv444p16le", "bgr0", "rgb0"],
    default: "p010le"
  },
  "video/nvenc_av1-mp4": {
    values: ["p010le", "yuv420p"],
    default: "p010le"
  },
  "video/webm": {
    values: ["yuv420p", "yuva420p", "yuv444p", "yuva444p"],
    default: "yuv420p"
  },
  "video/av1-webm": {
    values: ["yuv420p10le", "yuv420p", "yuv422p10le", "yuv444p10le"],
    default: "yuv420p10le"
  },
};

const VIDEO_ADVANCED_WIDGETS = {
  "video/h264-mp4": ["crf", "preset", "pix_fmt"],
  "video/h265-mp4": ["crf", "preset", "pix_fmt"],
  "video/nvenc_h264-mp4": ["bitrate", "pix_fmt"],
  "video/nvenc_hevc-mp4": ["bitrate", "pix_fmt"],
  "video/nvenc_av1-mp4": ["bitrate", "pix_fmt"],
  "video/av1-webm": ["crf", "pix_fmt"],
  "video/webm": ["crf", "pix_fmt"],
  "video/ffv1-mkv": ["level", "coder", "context", "gop_size", "slices", "slicecrc", "pix_fmt"],
  "video/ProRes": ["profile"],
  "animation/ffmpeg-gif": ["dither"],
  "animation/webp": ["lossless"],
};

const AUDIO_ADVANCED_WIDGETS = {
  "AAC": ["audio_sample_rate", "aac_bitrate", "aac_control", "aac_profile"],
  "Opus": ["audio_sample_rate", "opus_bitrate", "opus_vbr", "opus_content", "opus_complexity"],
  "Vorbis": ["audio_sample_rate", "vorbis_mode", "vorbis_quality", "vorbis_bitrate"],
  "FLAC": ["audio_sample_rate", "flac_bit_depth", "flac_compression", "flac_lpc"],
  "FLAC (external)": ["audio_sample_rate", "flac_bit_depth", "flac_compression", "flac_lpc"],
  "ALAC": ["audio_sample_rate", "alac_bit_depth", "alac_frame_size"],
  "WAV (external)": ["audio_sample_rate", "wav_bit_depth"],
  "MP3": ["audio_sample_rate", "mp3_bitrate"],
  "MP3 (external)": ["audio_sample_rate", "mp3_bitrate"],
  "PCM 16-bit (pcm_s16le)": ["audio_sample_rate"],
  "PCM 24-bit (pcm_s24le)": ["audio_sample_rate"],
  "PCM 32-bit float (pcm_f32le)": ["audio_sample_rate"],
};

const ALL_ADVANCED_NAMES = new Set([
  "crf", "preset", "bitrate", "pix_fmt", "profile", "level", "coder", "context",
  "gop_size", "slices", "slicecrc", "dither", "lossless",
  "audio_sample_rate",
  "aac_bitrate", "aac_control", "aac_profile",
  "opus_bitrate", "opus_vbr", "opus_content", "opus_complexity",
  "vorbis_mode", "vorbis_quality", "vorbis_bitrate",
  "flac_bit_depth", "flac_compression", "flac_lpc",
  "alac_bit_depth", "alac_frame_size",
  "wav_bit_depth", "mp3_bitrate"
]);

function cleanFormatName(fmt) {
  return (fmt || "").replace(" [default]", "").trim();
}

function nativeWidgetsHeight(node) {
  let height = 0;
  if (node?.widgets) {
    for (const w of node.widgets) {
      if (w.name === "preview" || w.type === "videopreview" || w.hidden || w.type === "hidden") continue;
      height += 26;
    }
  }
  return height;
}

function updateWidgetVisibility(node, forceResetHeight = false) {
  if (!node || !node.widgets) return;

  const showAdvWidget = node.widgets.find(w => w.name === "show_advanced");
  const videoFmtWidget = node.widgets.find(w => w.name === "video_format");
  const audioFmtWidget = node.widgets.find(w => w.name === "audio_format");

  const showAdvanced = !!showAdvWidget?.value;
  const currentVideoFmt = videoFmtWidget?.value || "video/h264-mp4";
  const rawAudioFmt = audioFmtWidget?.value || "AAC";
  const currentAudioFmt = cleanFormatName(rawAudioFmt);

  const allowedVideoAdv = new Set(VIDEO_ADVANCED_WIDGETS[currentVideoFmt] || []);
  const allowedAudioAdv = new Set(AUDIO_ADVANCED_WIDGETS[currentAudioFmt] || ["audio_sample_rate"]);

  for (const w of node.widgets) {
    if (!ALL_ADVANCED_NAMES.has(w.name)) continue;

    if (!w._origType) {
      w._origType = w.type || "combo";
      w._origComputeSize = w.computeSize;
    }

    const isSampleRate = (w.name === "audio_sample_rate");
    const shouldShow = showAdvanced && (isSampleRate || allowedVideoAdv.has(w.name) || allowedAudioAdv.has(w.name));

    if (shouldShow) {
      w.hidden = false;
      w.type = w._origType;
      w.computeSize = w._origComputeSize;
    } else {
      w.hidden = true;
      w.type = "hidden";
      w.computeSize = () => [0, -4];
    }
  }

  const activeH = nativeWidgetsHeight(node);
  const minRequiredH = activeH + NODE_VERTICAL_CHROME + PREVIEW_MIN_HEIGHT;
  const defaultTargetH = activeH + NODE_VERTICAL_CHROME + 160;

  if (forceResetHeight) {
    node.size = [DEFAULT_NODE_WIDTH, defaultTargetH];
    node.setSize?.(node.size);
  } else if (!node.size || node.size[1] < minRequiredH) {
    node.size = [Math.max(node.size?.[0] || DEFAULT_NODE_WIDTH, DEFAULT_NODE_WIDTH), minRequiredH];
    node.setSize?.(node.size);
  }
  node.setDirtyCanvas?.(true, true);
}

function updatePixFmtOptions(node, forceReset = false) {
  if (!node || !node.widgets) return;
  const videoFmtWidget = node.widgets.find(w => w.name === "video_format");
  const pixFmtWidget = node.widgets.find(w => w.name === "pix_fmt");
  if (!videoFmtWidget || !pixFmtWidget) return;

  const currentVideoFmt = videoFmtWidget.value;
  const config = PIX_FMT_MAP[currentVideoFmt];
  if (!config) return;

  pixFmtWidget.options = pixFmtWidget.options || {};
  pixFmtWidget.options.values = config.values;

  if (forceReset || !config.values.includes(pixFmtWidget.value)) {
    pixFmtWidget.value = config.default;
  }
}

function updateAudioFormatOptions(node, forceResetToDefault = true) {
  if (!node || !node.widgets) return;
  const videoFmtWidget = node.widgets.find(w => w.name === "video_format");
  const audioFmtWidget = node.widgets.find(w => w.name === "audio_format");
  if (!videoFmtWidget || !audioFmtWidget) return;

  const currentVideoFmt = videoFmtWidget.value;
  const baseAllowed = AUDIO_FORMAT_MAP[currentVideoFmt] || AUDIO_FORMAT_MAP["video/h264-mp4"];
  const defaultAudio = DEFAULT_AUDIO_FORMAT[currentVideoFmt] || baseAllowed[0];

  const formattedOptions = baseAllowed.map(item => item === defaultAudio ? `${item} [default]` : item);

  audioFmtWidget.options = audioFmtWidget.options || {};
  audioFmtWidget.options.values = formattedOptions;

  const currentClean = cleanFormatName(audioFmtWidget.value);

  if (forceResetToDefault) {
    audioFmtWidget.value = `${defaultAudio} [default]`;
  } else {
    const matchingOption = formattedOptions.find(opt => cleanFormatName(opt) === currentClean);
    audioFmtWidget.value = matchingOption || `${defaultAudio} [default]`;
  }
}

function addVideoPreviewWidget(node) {
  const container = document.createElement("div");
  container.className = "h3_save_video_preview";
  Object.assign(container.style, {
    width: "100%",
    height: "100%",
    minHeight: "120px",
    background: "#000",
    borderRadius: "6px",
    border: "1px solid #333",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    overflow: "hidden",
    boxSizing: "border-box",
  });

  const videoEl = document.createElement("video");
  Object.assign(videoEl.style, {
    width: "100%",
    height: "100%",
    maxWidth: "100%",
    maxHeight: "100%",
    display: "none",
    objectFit: "contain",
    background: "#000",
  });
  videoEl.controls = true;
  videoEl.autoplay = false;
  videoEl.loop = true;
  videoEl.playsInline = true;

  const imgEl = document.createElement("img");
  Object.assign(imgEl.style, {
    width: "100%",
    height: "100%",
    maxWidth: "100%",
    maxHeight: "100%",
    display: "none",
    objectFit: "contain",
    background: "#000",
  });

  const placeholder = document.createElement("div");
  placeholder.textContent = "Video Preview";
  Object.assign(placeholder.style, {
    color: "#666",
    fontSize: "12px",
    fontStyle: "italic",
    padding: "20px",
    userSelect: "none",
  });

  container.appendChild(videoEl);
  container.appendChild(imgEl);
  container.appendChild(placeholder);

  const previewWidget = node.addDOMWidget("preview", "videopreview", container, {
    serialize: false,
    hideOnZoom: false,
    getValue() { return container.value; },
    setValue(v) { container.value = v; }
  });

  previewWidget.container = container;
  previewWidget.videoEl = videoEl;
  previewWidget.imgEl = imgEl;
  previewWidget.placeholder = placeholder;

  // Dynamic height calculation based on node.size[1]
  previewWidget.computeSize = function(width) {
    const nodeH = (node.size && node.size[1]) ? Number(node.size[1]) : DEFAULT_NODE_HEIGHT;
    const availableH = Math.max(PREVIEW_MIN_HEIGHT, nodeH - NODE_VERTICAL_CHROME - nativeWidgetsHeight(node));
    return [width || DEFAULT_NODE_WIDTH, availableH];
  };

  node.updatePreview = function(previewData) {
    if (!previewData || !previewData.filename) {
      videoEl.style.display = "none";
      imgEl.style.display = "none";
      placeholder.style.display = "block";
      return;
    }

    placeholder.style.display = "none";

    const filename = previewData.filename;
    const format = previewData.format || "";
    const isSpecialTranscode = filename.match(/\.(mkv|mov)$/i) || format.includes("ffv1") || format.includes("ProRes") || format.includes("hevc");
    const isImageOrAnim = filename.match(/\.(gif|webp|png|jpg|jpeg)$/i) && !isSpecialTranscode;

    if (isImageOrAnim) {
      const srcUrl = api.apiURL(`/view?filename=${encodeURIComponent(filename)}&subfolder=${encodeURIComponent(previewData.subfolder || "")}&type=${encodeURIComponent(previewData.type || "output")}&t=${Date.now()}`);
      videoEl.style.display = "none";
      imgEl.src = srcUrl;
      imgEl.style.display = "block";
    } else {
      let srcUrl;
      if (isSpecialTranscode) {
        srcUrl = api.apiURL(`/minimax/viewvideo?filename=${encodeURIComponent(filename)}&subfolder=${encodeURIComponent(previewData.subfolder || "")}&type=${encodeURIComponent(previewData.type || "output")}&t=${Date.now()}`);
      } else {
        srcUrl = api.apiURL(`/view?filename=${encodeURIComponent(filename)}&subfolder=${encodeURIComponent(previewData.subfolder || "")}&type=${encodeURIComponent(previewData.type || "output")}&t=${Date.now()}`);
      }

      imgEl.style.display = "none";
      videoEl.src = srcUrl;
      videoEl.style.display = "block";
      videoEl.load();

      videoEl.onerror = () => {
        if (!videoEl.src.includes("/minimax/viewvideo")) {
          const fallbackUrl = api.apiURL(`/minimax/viewvideo?filename=${encodeURIComponent(filename)}&subfolder=${encodeURIComponent(previewData.subfolder || "")}&type=${encodeURIComponent(previewData.type || "output")}&t=${Date.now()}`);
          videoEl.src = fallbackUrl;
          videoEl.load();
        }
      };
    }

    node.setDirtyCanvas?.(true, true);
  };
}

app.registerExtension({
  name: "MiniMaxH3.SaveVideo",

  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== NODE_ID) return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function() {
      const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;

      addVideoPreviewWidget(this);

      const videoFmtWidget = this.widgets?.find(w => w.name === "video_format");
      const audioFmtWidget = this.widgets?.find(w => w.name === "audio_format");
      const showAdvWidget = this.widgets?.find(w => w.name === "show_advanced");

      if (videoFmtWidget) {
        const origCallback = videoFmtWidget.callback;
        videoFmtWidget.callback = (val) => {
          origCallback?.(val);
          updateAudioFormatOptions(this, true);
          updatePixFmtOptions(this, true);
          updateWidgetVisibility(this);
        };
      }

      if (audioFmtWidget) {
        const origCallback = audioFmtWidget.callback;
        audioFmtWidget.callback = (val) => {
          origCallback?.(val);
          updateWidgetVisibility(this);
        };
      }

      if (showAdvWidget) {
        const origCallback = showAdvWidget.callback;
        showAdvWidget.callback = (val) => {
          origCallback?.(val);
          updateWidgetVisibility(this);
        };
      }

      updateAudioFormatOptions(this, false);
      updatePixFmtOptions(this, false);
      updateWidgetVisibility(this, true);

      return r;
    };

    const onConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function() {
      const r = onConfigure ? onConfigure.apply(this, arguments) : undefined;
      setTimeout(() => {
        updateAudioFormatOptions(this, false);
        updatePixFmtOptions(this, false);
        updateWidgetVisibility(this, false);
      }, 20);
      return r;
    };

    const onExecuted = nodeType.prototype.onExecuted;
    nodeType.prototype.onExecuted = function(message) {
      onExecuted?.apply(this, arguments);
      const previewData = message?.gifs?.[0] || message?.videos?.[0];
      if (previewData && this.updatePreview) {
        this.updatePreview(previewData);
      }
    };
  }
});
