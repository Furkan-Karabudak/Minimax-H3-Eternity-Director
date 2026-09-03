import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

const NODE_ID = "H3Eternity_SaveVideo";
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
  const minRequiredH = activeH + 36 + PREVIEW_MIN_HEIGHT;
  const defaultTargetH = activeH + 36 + 220;

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
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    overflow: "hidden",
    boxSizing: "border-box",
    position: "relative",
  });

  const contentWrap = document.createElement("div");
  Object.assign(contentWrap.style, {
    width: "100%",
    flex: "1",
    minHeight: "0",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    overflow: "hidden",
    position: "relative",
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

  contentWrap.appendChild(videoEl);
  contentWrap.appendChild(imgEl);
  contentWrap.appendChild(placeholder);
  container.appendChild(contentWrap);

  // Image sequence controls bar
  const seqControlsEl = document.createElement("div");
  Object.assign(seqControlsEl.style, {
    width: "100%",
    height: "28px",
    background: "rgba(22, 22, 26, 0.95)",
    borderTop: "1px solid #333",
    display: "none",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "0 8px",
    boxSizing: "border-box",
    gap: "8px",
    userSelect: "none",
  });

  const btnPlayPause = document.createElement("button");
  btnPlayPause.textContent = "▶";
  Object.assign(btnPlayPause.style, {
    background: "none",
    border: "none",
    color: "#fff",
    cursor: "pointer",
    fontSize: "12px",
    padding: "2px 6px",
    borderRadius: "4px",
    lineHeight: "1",
  });

  const slider = document.createElement("input");
  slider.type = "range";
  slider.min = "1";
  slider.max = "1";
  slider.value = "1";
  Object.assign(slider.style, {
    flex: "1",
    height: "4px",
    cursor: "pointer",
    accentColor: "#0ea5e9",
  });

  const frameLabel = document.createElement("span");
  frameLabel.textContent = "1 / 1";
  Object.assign(frameLabel.style, {
    color: "#aaa",
    fontSize: "11px",
    fontFamily: "monospace",
    whiteSpace: "nowrap",
    minWidth: "48px",
    textAlign: "right",
  });

  seqControlsEl.appendChild(btnPlayPause);
  seqControlsEl.appendChild(slider);
  seqControlsEl.appendChild(frameLabel);
  container.appendChild(seqControlsEl);

  const previewWidget = node.addDOMWidget("preview", "videopreview", container, {
    serialize: false,
    hideOnZoom: false,
    getValue() { return container.value; },
    setValue(v) { container.value = v; }
  });

  node._previewWidget = previewWidget;
  previewWidget.element = container;
  previewWidget.container = container;
  previewWidget.videoEl = videoEl;
  previewWidget.imgEl = imgEl;
  previewWidget.placeholder = placeholder;
  previewWidget.seqControlsEl = seqControlsEl;

  previewWidget.computeSize = function(width) {
    return [width || DEFAULT_NODE_WIDTH, PREVIEW_MIN_HEIGHT];
  };

  let seqTimer = null;
  let isPlaying = false;
  let currentSeqIdx = 0;
  let currentSeqUrls = [];

  function stopSeqPlayback() {
    if (seqTimer) {
      clearInterval(seqTimer);
      seqTimer = null;
    }
    isPlaying = false;
    btnPlayPause.textContent = "▶";
  }

  function startSeqPlayback(fps = 24) {
    if (currentSeqUrls.length <= 1) return;
    stopSeqPlayback();
    isPlaying = true;
    btnPlayPause.textContent = "❚❚";
    const intervalMs = Math.max(10, Math.round(1000 / fps));

    seqTimer = setInterval(() => {
      currentSeqIdx = (currentSeqIdx + 1) % currentSeqUrls.length;
      imgEl.src = currentSeqUrls[currentSeqIdx];
      slider.value = String(currentSeqIdx + 1);
      frameLabel.textContent = `${currentSeqIdx + 1} / ${currentSeqUrls.length}`;
    }, intervalMs);
  }

  btnPlayPause.onclick = (e) => {
    e.stopPropagation();
    if (isPlaying) {
      stopSeqPlayback();
    } else {
      const fps = Number(node._lastPreviewData?.frame_rate) || 24;
      startSeqPlayback(fps);
    }
  };

  slider.oninput = (e) => {
    e.stopPropagation();
    stopSeqPlayback();
    const frameNum = Number(slider.value);
    currentSeqIdx = Math.max(0, Math.min(currentSeqUrls.length - 1, frameNum - 1));
    if (currentSeqUrls[currentSeqIdx]) {
      imgEl.src = currentSeqUrls[currentSeqIdx];
      frameLabel.textContent = `${currentSeqIdx + 1} / ${currentSeqUrls.length}`;
    }
  };

  async function decodeAnimFrames(blob, mimeType) {
    if (!window.ImageDecoder) return null;
    try {
      const buffer = await blob.arrayBuffer();
      const decoder = new ImageDecoder({ data: buffer, type: mimeType });
      await decoder.tracks.ready;

      const frames = [];
      let frameIdx = 0;

      while (true) {
        try {
          const { image } = await decoder.decode({ frameIndex: frameIdx });
          const canvas = document.createElement("canvas");
          canvas.width = image.displayWidth;
          canvas.height = image.displayHeight;
          const ctx = canvas.getContext("2d");
          ctx.drawImage(image, 0, 0);
          image.close();
          frames.push(canvas.toDataURL("image/png"));
          frameIdx++;
        } catch (decodeErr) {
          break;
        }
      }

      return frames.length > 1 ? frames : null;
    } catch (e) {
      console.warn("ImageDecoder animation decode error:", e);
      return null;
    }
  }

  node.updatePreview = function(previewData) {
    stopSeqPlayback();
    node._lastPreviewData = previewData;

    if (!previewData || !previewData.filename) {
      videoEl.style.display = "none";
      imgEl.style.display = "none";
      seqControlsEl.style.display = "none";
      placeholder.style.display = "block";
      return;
    }

    placeholder.style.display = "none";

    const filename = previewData.filename;
    const format = previewData.format || "";
    const isImageSequence = format.startsWith("image_sequence") || (previewData.base_pattern && Number(previewData.count) > 1);
    const isAnimation = format.startsWith("animation") || filename.match(/\.(gif|webp)$/i);
    const isSpecialTranscode = filename.match(/\.(mkv|mov)$/i) || format.includes("ffv1") || format.includes("ProRes") || format.includes("hevc");
    const isSingleImage = filename.match(/\.(png|jpg|jpeg)$/i) && !isSpecialTranscode && !isImageSequence && !isAnimation;

    if (isImageSequence && Number(previewData.count) > 1 && previewData.base_pattern) {
      try { videoEl.pause(); } catch (e) {}
      videoEl.style.display = "none";

      const count = Number(previewData.count);
      const sub = previewData.subfolder || "";
      const pType = previewData.type || "output";
      currentSeqUrls = [];
      const timestamp = Date.now();

      for (let i = 1; i <= count; i++) {
        const frameNumStr = String(i).padStart(5, '0');
        const frameName = previewData.base_pattern.replace('%05d', frameNumStr);
        const url = api.apiURL(`/view?filename=${encodeURIComponent(frameName)}&subfolder=${encodeURIComponent(sub)}&type=${encodeURIComponent(pType)}&t=${timestamp}`);
        currentSeqUrls.push(url);
        const preImg = new Image();
        preImg.src = url;
      }

      currentSeqIdx = 0;
      imgEl.src = currentSeqUrls[0];
      imgEl.style.display = "block";

      slider.min = "1";
      slider.max = String(count);
      slider.value = "1";
      frameLabel.textContent = `1 / ${count}`;
      btnPlayPause.textContent = "▶";
      seqControlsEl.style.display = "flex";

    } else if (isAnimation) {
      try { videoEl.pause(); } catch (e) {}
      videoEl.style.display = "none";
      const srcUrl = api.apiURL(`/view?filename=${encodeURIComponent(filename)}&subfolder=${encodeURIComponent(previewData.subfolder || "")}&type=${encodeURIComponent(previewData.type || "output")}&t=${Date.now()}`);
      const mime = filename.endsWith(".webp") ? "image/webp" : "image/gif";

      fetch(srcUrl).then(r => r.blob()).then(async (blob) => {
        const decoded = await decodeAnimFrames(blob, mime);
        if (decoded && decoded.length > 1) {
          currentSeqUrls = decoded;
          currentSeqIdx = 0;
          imgEl.src = currentSeqUrls[0];
          imgEl.style.display = "block";

          slider.min = "1";
          slider.max = String(decoded.length);
          slider.value = "1";
          frameLabel.textContent = `1 / ${decoded.length}`;
          btnPlayPause.textContent = "▶";
          seqControlsEl.style.display = "flex";
        } else {
          imgEl.src = srcUrl;
          imgEl.style.display = "block";
          seqControlsEl.style.display = "none";
        }
      }).catch(() => {
        imgEl.src = srcUrl;
        imgEl.style.display = "block";
        seqControlsEl.style.display = "none";
      });

    } else if (isSingleImage) {
      seqControlsEl.style.display = "none";
      const srcUrl = api.apiURL(`/view?filename=${encodeURIComponent(filename)}&subfolder=${encodeURIComponent(previewData.subfolder || "")}&type=${encodeURIComponent(previewData.type || "output")}&t=${Date.now()}`);
      try { videoEl.pause(); } catch (e) {}
      videoEl.style.display = "none";
      imgEl.src = srcUrl;
      imgEl.style.display = "block";
    } else {
      seqControlsEl.style.display = "none";
      let srcUrl;
      if (isSpecialTranscode) {
        srcUrl = api.apiURL(`/h3_eternity/viewvideo?filename=${encodeURIComponent(filename)}&subfolder=${encodeURIComponent(previewData.subfolder || "")}&type=${encodeURIComponent(previewData.type || "output")}&t=${Date.now()}`);
      } else {
        srcUrl = api.apiURL(`/view?filename=${encodeURIComponent(filename)}&subfolder=${encodeURIComponent(previewData.subfolder || "")}&type=${encodeURIComponent(previewData.type || "output")}&t=${Date.now()}`);
      }

      imgEl.style.display = "none";
      videoEl.src = srcUrl;
      videoEl.style.display = "block";
      videoEl.load();

      videoEl.onerror = () => {
        if (!videoEl.src.includes("/h3_eternity/viewvideo")) {
          const fallbackUrl = api.apiURL(`/h3_eternity/viewvideo?filename=${encodeURIComponent(filename)}&subfolder=${encodeURIComponent(previewData.subfolder || "")}&type=${encodeURIComponent(previewData.type || "output")}&t=${Date.now()}`);
          videoEl.src = fallbackUrl;
          videoEl.load();
        }
      };
    }

    node.setDirtyCanvas?.(true, true);
  };
}

app.registerExtension({
  name: "H3Eternity_SaveVideo",

  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== NODE_ID && nodeData.name !== "H3_Eternity_Save_Video") return;

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

    const onDrawForeground = nodeType.prototype.onDrawForeground;
    nodeType.prototype.onDrawForeground = function(ctx) {
      if (onDrawForeground) onDrawForeground.apply(this, arguments);

      if (this._previewWidget && this._previewWidget.element && this._previewWidget.last_y) {
        const remainingHeight = this.size[1] - this._previewWidget.last_y - 18;
        const currentHeight = parseFloat(this._previewWidget.element.style.height);
        const targetHeight = Math.max(PREVIEW_MIN_HEIGHT, remainingHeight);

        if (isNaN(currentHeight) || Math.abs(currentHeight - targetHeight) > 1) {
          this._previewWidget.element.style.height = `${targetHeight}px`;
        }
      }
    };

    const onResize = nodeType.prototype.onResize;
    nodeType.prototype.onResize = function(size) {
      if (onResize) onResize.apply(this, arguments);
      if (this._previewWidget && this._previewWidget.element) {
        let yOffset = this._previewWidget.last_y;
        if (!yOffset) {
          yOffset = 30;
          if (this.widgets) {
            for (let w of this.widgets) {
              if (w === this._previewWidget) break;
              yOffset += (w.computeSize ? w.computeSize()[1] : 20) + 4;
            }
          }
        }
        const remainingHeight = size[1] - yOffset - 18;
        this._previewWidget.element.style.height = `${Math.max(PREVIEW_MIN_HEIGHT, remainingHeight)}px`;
      }
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
