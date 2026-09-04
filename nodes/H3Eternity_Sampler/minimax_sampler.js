import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

const SAMPLER_NODE_IDS = new Set([
  "H3Eternity_Sampler",
  "H3Eternity_SamplerAdvanced",
  "H3_Eternity_Sampler",
  "H3_Eternity_Sampler_Advanced"
]);
const DEFAULT_NODE_WIDTH = 400;
const PREVIEW_MIN_HEIGHT = 120;

// --------------------------------------------------------------------------------------
// Formats & Advanced Widgets Mappings (Identical to H3Eternity_SaveVideo)
// --------------------------------------------------------------------------------------
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
  "WAV": ["audio_sample_rate", "wav_bit_depth"],
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

const BASE_SAVE_WIDGETS = new Set(["filename", "video_format", "audio_format"]);

function cleanFormatName(fmt) {
  return (fmt || "").replace(/\s*\[default\]\s*/g, "").trim();
}

function nativeWidgetsHeight(node) {
  let height = 0;
  if (node?.widgets) {
    for (const w of node.widgets) {
      if (w.name === "preview" || w.type === "videopreview" ||
          w.name === "h3_status_tracker" || w.type === "status_tracker" ||
          w.hidden || w.type === "hidden") continue;
      height += 26;
    }
  }
  return height;
}

// --------------------------------------------------------------------------------------
// Dynamic Visibility & Options Update Engine
// --------------------------------------------------------------------------------------
function updateSamplerWidgetVisibility(node, forceResetHeight = false) {
  if (!node || !node.widgets) return;

  const advancedSaveWidget = node.widgets.find(w => w.name === "advanced_save" || w.name === "show_advanced");
  const videoFmtWidget = node.widgets.find(w => w.name === "video_format");
  const audioFmtWidget = node.widgets.find(w => w.name === "audio_format");

  const advancedSave = !!advancedSaveWidget?.value;
  const rawVideoFmt = videoFmtWidget?.value || "video/ffv1-mkv";
  const currentVideoFmt = cleanFormatName(rawVideoFmt);
  const rawAudioFmt = audioFmtWidget?.value || "FLAC";
  const currentAudioFmt = cleanFormatName(rawAudioFmt);

  const allowedVideoAdv = new Set(VIDEO_ADVANCED_WIDGETS[currentVideoFmt] || []);
  const allowedAudioAdv = new Set(AUDIO_ADVANCED_WIDGETS[currentAudioFmt] || ["audio_sample_rate"]);

  for (const w of node.widgets) {
    // Preserve custom DOM widgets
    if (w.name === "preview" || w.type === "videopreview" ||
        w.name === "h3_status_tracker" || w.type === "status_tracker") {
      continue;
    }

    if (!w._origType && w.type !== "hidden") {
      w._origType = w.type || "combo";
      w._origComputeSize = w.computeSize;
    }

    // 1. Base Save Widgets (filename, video_format, audio_format)
    if (BASE_SAVE_WIDGETS.has(w.name)) {
      if (advancedSave) {
        w.hidden = false;
        w.type = w._origType || "combo";
        w.computeSize = w._origComputeSize;
      } else {
        w.hidden = true;
        w.type = "hidden";
        w.computeSize = () => [0, -4];
      }
      continue;
    }

    // 2. Codec Advanced Settings (crf, preset, bitrate, pix_fmt, slices, flac_*, etc.)
    if (ALL_ADVANCED_NAMES.has(w.name)) {
      const isSampleRate = (w.name === "audio_sample_rate");
      const shouldShow = advancedSave && (isSampleRate || allowedVideoAdv.has(w.name) || allowedAudioAdv.has(w.name));

      if (shouldShow) {
        w.hidden = false;
        w.type = w._origType || "combo";
        w.computeSize = w._origComputeSize;
      } else {
        w.hidden = true;
        w.type = "hidden";
        w.computeSize = () => [0, -4];
      }
    }
  }

  const activeH = nativeWidgetsHeight(node);
  const statusH = node._statusWidget ? 85 : 0;
  const previewH = node._previewWidget ? PREVIEW_MIN_HEIGHT : 0;
  const chromeH = 50;
  const minRequiredH = activeH + statusH + previewH + chromeH;
  const defaultTargetH = activeH + statusH + previewH + chromeH + 60;

  const targetW = Math.max(node.size?.[0] || DEFAULT_NODE_WIDTH, DEFAULT_NODE_WIDTH);

  if (forceResetHeight) {
    node.size = [targetW, defaultTargetH];
    node.setSize?.(node.size);
  } else if (!node.size || node.size[1] < minRequiredH || (!node._userResized && node.size[1] > minRequiredH + 100)) {
    node.size = [targetW, defaultTargetH];
    node.setSize?.(node.size);
  }
  node.setDirtyCanvas?.(true, true);
}

function updateSamplerPixFmtOptions(node, forceReset = false) {
  if (!node || !node.widgets) return;
  const videoFmtWidget = node.widgets.find(w => w.name === "video_format");
  const pixFmtWidget = node.widgets.find(w => w.name === "pix_fmt");
  if (!videoFmtWidget || !pixFmtWidget) return;

  const currentVideoFmt = cleanFormatName(videoFmtWidget.value);
  const config = PIX_FMT_MAP[currentVideoFmt];
  if (!config) return;

  pixFmtWidget.options = pixFmtWidget.options || {};
  pixFmtWidget.options.values = config.values;

  if (forceReset || !config.values.includes(pixFmtWidget.value)) {
    pixFmtWidget.value = config.default;
  }
}

function updateSamplerAudioFormatOptions(node, forceResetToDefault = true) {
  if (!node || !node.widgets) return;
  const videoFmtWidget = node.widgets.find(w => w.name === "video_format");
  const audioFmtWidget = node.widgets.find(w => w.name === "audio_format");
  if (!videoFmtWidget || !audioFmtWidget) return;

  const currentVideoFmt = cleanFormatName(videoFmtWidget.value);
  const baseAllowed = AUDIO_FORMAT_MAP[currentVideoFmt] || AUDIO_FORMAT_MAP["video/ffv1-mkv"] || ["FLAC"];
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

// --------------------------------------------------------------------------------------
// Inject Custom Isolated Styles
// --------------------------------------------------------------------------------------
const SAMPLER_STYLES = `
  .h3-eternity-sampler-container {
    display: flex;
    flex-direction: column;
    width: 100%;
    box-sizing: border-box;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    gap: 6px;
    padding: 4px;
  }
  .h3-eternity-tracker-card {
    background: rgba(18, 22, 28, 0.85);
    border: 1px solid rgba(80, 140, 240, 0.25);
    border-radius: 6px;
    padding: 8px 10px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .h3-tracker-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 11px;
    font-weight: 600;
  }
  .h3-tracker-badge {
    background: linear-gradient(135deg, #1e3a8a, #3b82f6);
    color: #f8fafc;
    padding: 2px 7px;
    border-radius: 4px;
    letter-spacing: 0.5px;
    text-transform: uppercase;
  }
  .h3-tracker-status {
    color: #94a3b8;
    font-size: 11px;
  }
  .h3-progress-row {
    display: flex;
    flex-direction: column;
    gap: 3px;
  }
  .h3-progress-labels {
    display: flex;
    justify-content: space-between;
    font-size: 10px;
    color: #cbd5e1;
  }
  .h3-progress-bar {
    width: 100%;
    height: 6px;
    background: rgba(255, 255, 255, 0.08);
    border-radius: 3px;
    overflow: hidden;
  }
  .h3-progress-fill-total {
    height: 100%;
    width: 0%;
    background: linear-gradient(90deg, #3b82f6, #8b5cf6);
    transition: width 0.15s ease-out;
  }
  .h3-progress-fill-iter {
    height: 100%;
    width: 0%;
    background: linear-gradient(90deg, #06b6d4, #10b981);
    transition: width 0.15s ease-out;
  }
  .h3-save-video-preview-wrap {
    width: 100%;
    height: 100%;
    min-height: ${PREVIEW_MIN_HEIGHT}px;
    background: #000;
    border-radius: 6px;
    border: 1px solid #333;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    overflow: hidden;
    box-sizing: border-box;
    position: relative;
  }
  .h3-save-video-preview-content {
    width: 100%;
    flex: 1;
    min-height: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
    position: relative;
  }
  .h3-save-video-preview-content video,
  .h3-save-video-preview-content img {
    width: 100%;
    height: 100%;
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
    background: #000;
  }
  .h3-preview-placeholder {
    color: #666;
    font-size: 12px;
    font-style: italic;
    padding: 20px;
    user-select: none;
    text-align: center;
  }
  .h3-seq-controls {
    width: 100%;
    height: 28px;
    background: rgba(22, 22, 26, 0.95);
    border-top: 1px solid #333;
    display: none;
    align-items: center;
    justify-content: space-between;
    padding: 0 8px;
    box-sizing: border-box;
    gap: 8px;
    user-select: none;
  }
  .h3-seq-controls button {
    background: none;
    border: none;
    color: #fff;
    cursor: pointer;
    font-size: 12px;
    padding: 2px 6px;
    border-radius: 4px;
    line-height: 1;
  }
  .h3-seq-controls input[type="range"] {
    flex: 1;
    height: 4px;
    cursor: pointer;
    accent-color: #0ea5e9;
  }
  .h3-seq-controls span {
    color: #aaa;
    font-size: 11px;
    font-family: monospace;
    white-space: nowrap;
    min-width: 48px;
    text-align: right;
  }
`;

let samplerStyleEl = document.getElementById("h3-eternity-sampler-styles");
if (!samplerStyleEl) {
  samplerStyleEl = document.createElement("style");
  samplerStyleEl.id = "h3-eternity-sampler-styles";
  document.head.appendChild(samplerStyleEl);
}
samplerStyleEl.textContent = SAMPLER_STYLES;

// --------------------------------------------------------------------------------------
// Status Tracker DOM Widget
// --------------------------------------------------------------------------------------
function addStatusTrackerWidget(node) {
  if (node._statusWidget) return;

  const trackerContainer = document.createElement("div");
  trackerContainer.className = "h3-eternity-sampler-container";

  const card = document.createElement("div");
  card.className = "h3-eternity-tracker-card";

  const header = document.createElement("div");
  header.className = "h3-tracker-header";

  const badge = document.createElement("span");
  badge.className = "h3-tracker-badge";
  badge.textContent = "Iteration 1 / 1";

  const statusLabel = document.createElement("span");
  statusLabel.className = "h3-tracker-status";
  statusLabel.textContent = "Ready";

  header.appendChild(badge);
  header.appendChild(statusLabel);
  card.appendChild(header);

  // Total Progress
  const totalRow = document.createElement("div");
  totalRow.className = "h3-progress-row";
  const totalLabels = document.createElement("div");
  totalLabels.className = "h3-progress-labels";
  totalLabels.innerHTML = "<span>Total Plan Progress</span><span class='h3-total-pct'>0%</span>";
  const totalBar = document.createElement("div");
  totalBar.className = "h3-progress-bar";
  const totalFill = document.createElement("div");
  totalFill.className = "h3-progress-fill-total";
  totalBar.appendChild(totalFill);
  totalRow.appendChild(totalLabels);
  totalRow.appendChild(totalBar);
  card.appendChild(totalRow);

  // Iteration Progress
  const iterRow = document.createElement("div");
  iterRow.className = "h3-progress-row";
  const iterLabels = document.createElement("div");
  iterLabels.className = "h3-progress-labels";
  iterLabels.innerHTML = "<span>Iteration Step</span><span class='h3-iter-pct'>0 / 20</span>";
  const iterBar = document.createElement("div");
  iterBar.className = "h3-progress-bar";
  const iterFill = document.createElement("div");
  iterFill.className = "h3-progress-fill-iter";
  iterBar.appendChild(iterFill);
  iterRow.appendChild(iterLabels);
  iterRow.appendChild(iterBar);
  card.appendChild(iterRow);

  trackerContainer.appendChild(card);

  node._statusTracker = {
    badge,
    statusLabel,
    totalFill,
    totalPctText: totalLabels.querySelector(".h3-total-pct"),
    iterFill,
    iterPctText: iterLabels.querySelector(".h3-iter-pct"),
  };

  const widget = node.addDOMWidget("h3_status_tracker", "status_tracker", trackerContainer, {
    getValue() { return ""; },
    setValue() {},
  });
  widget.computeSize = () => [node.size?.[0] || DEFAULT_NODE_WIDTH, 85];
  node._statusWidget = widget;

  node._currentIteration = 0;
  node._totalIterations = 1;
}

// --------------------------------------------------------------------------------------
// High-Fidelity Video Preview Widget (Reference: H3Eternity_SaveVideo)
// --------------------------------------------------------------------------------------
function addVideoPreviewWidget(node) {
  if (node._previewWidget) return;

  const container = document.createElement("div");
  container.className = "h3-save-video-preview-wrap";

  const contentWrap = document.createElement("div");
  contentWrap.className = "h3-save-video-preview-content";

  const videoEl = document.createElement("video");
  videoEl.controls = true;
  videoEl.autoplay = false;
  videoEl.loop = true;
  videoEl.playsInline = true;
  videoEl.style.display = "none";

  const imgEl = document.createElement("img");
  imgEl.style.display = "none";

  const placeholder = document.createElement("div");
  placeholder.className = "h3-preview-placeholder";
  placeholder.textContent = "H3 Eternity Sampler Preview (Awaiting generation)";

  contentWrap.appendChild(videoEl);
  contentWrap.appendChild(imgEl);
  contentWrap.appendChild(placeholder);
  container.appendChild(contentWrap);

  // Sequence controls bar
  const seqControlsEl = document.createElement("div");
  seqControlsEl.className = "h3-seq-controls";

  const btnPlayPause = document.createElement("button");
  btnPlayPause.textContent = "▶";

  const slider = document.createElement("input");
  slider.type = "range";
  slider.min = "1";
  slider.max = "1";
  slider.value = "1";

  const frameLabel = document.createElement("span");
  frameLabel.textContent = "1 / 1";

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
      const fps = Number(node._lastPreviewData?.fps) || 24;
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
      return frames;
    } catch (e) {
      return null;
    }
  }

  node.updatePreview = function(previewData) {
    if (!previewData || !previewData.filename) {
      placeholder.style.display = "block";
      videoEl.style.display = "none";
      imgEl.style.display = "none";
      seqControlsEl.style.display = "none";
      return;
    }

    node._lastPreviewData = previewData;
    placeholder.style.display = "none";

    const filename = previewData.filename;
    const format = previewData.format || "";
    const isImageSequence = format.startsWith("image_sequence") || (previewData.base_pattern && Number(previewData.count) > 1);
    const isAnimation = format.startsWith("animation") || filename.match(/\.(gif|webp)$/i);
    const isSpecialTranscode = filename.match(/\.(mkv|mov)$/i) || format.includes("ffv1") || format.includes("ProRes") || format.includes("hevc");

    if (isImageSequence && Number(previewData.count) > 1 && previewData.base_pattern) {
      try { videoEl.pause(); } catch (e) {}
      videoEl.style.display = "none";

      const count = Number(previewData.count);
      const sub = previewData.subfolder || "";
      const pType = previewData.type || "temp";
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
      const srcUrl = api.apiURL(`/view?filename=${encodeURIComponent(filename)}&subfolder=${encodeURIComponent(previewData.subfolder || "")}&type=${encodeURIComponent(previewData.type || "temp")}&t=${Date.now()}`);
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

    } else {
      seqControlsEl.style.display = "none";
      let srcUrl;
      if (isSpecialTranscode) {
        srcUrl = api.apiURL(`/h3_eternity/viewvideo?filename=${encodeURIComponent(filename)}&subfolder=${encodeURIComponent(previewData.subfolder || "")}&type=${encodeURIComponent(previewData.type || "temp")}&t=${Date.now()}`);
      } else {
        srcUrl = api.apiURL(`/view?filename=${encodeURIComponent(filename)}&subfolder=${encodeURIComponent(previewData.subfolder || "")}&type=${encodeURIComponent(previewData.type || "temp")}&t=${Date.now()}`);
      }

      imgEl.style.display = "none";
      videoEl.src = srcUrl;
      videoEl.style.display = "block";
      videoEl.load();

      videoEl.onerror = () => {
        if (!videoEl.src.includes("/h3_eternity/viewvideo")) {
          const fallbackUrl = api.apiURL(`/h3_eternity/viewvideo?filename=${encodeURIComponent(filename)}&subfolder=${encodeURIComponent(previewData.subfolder || "")}&type=${encodeURIComponent(previewData.type || "temp")}&t=${Date.now()}`);
          videoEl.src = fallbackUrl;
          videoEl.load();
        }
      };
    }

    node.setDirtyCanvas?.(true, true);
  };
}

// --------------------------------------------------------------------------------------
// ComfyUI Extension Definition (Mirrored Prototype Structure from SaveVideo)
// --------------------------------------------------------------------------------------
app.registerExtension({
  name: "H3Eternity_Sampler",

  async setup() {
    api.addEventListener("progress", (event) => {
      const detail = event?.detail;
      if (!detail || !detail.node) return;

      const runningNodeId = String(detail.node);
      const targetNode = app.graph?._nodes?.find(n => String(n.id) === runningNodeId && SAMPLER_NODE_IDS.has(n.comfyClass));
      if (!targetNode || !targetNode._statusTracker) return;

      const st = targetNode._statusTracker;
      const step = detail.value || 0;
      const maxSteps = detail.max || 1;

      const iterPct = Math.min(100, Math.round((step / maxSteps) * 100));
      st.iterFill.style.width = `${iterPct}%`;
      st.iterPctText.textContent = `${step} / ${maxSteps}`;

      const cur = targetNode._currentIteration || 0;
      const total = targetNode._totalIterations || 1;
      const totalPct = Math.min(100, Math.round(((cur * maxSteps + step) / (total * maxSteps)) * 100));
      st.totalFill.style.width = `${totalPct}%`;
      st.totalPctText.textContent = `${totalPct}%`;

      st.statusLabel.textContent = `Sampling step ${step}/${maxSteps}...`;
    });

    api.addEventListener("executing", (event) => {
      const runningNodeId = event?.detail ? String(event.detail) : null;
      if (!runningNodeId) return;

      const targetNode = app.graph?._nodes?.find(n => String(n.id) === runningNodeId && SAMPLER_NODE_IDS.has(n.comfyClass));
      if (targetNode && targetNode._statusTracker) {
        targetNode._statusTracker.statusLabel.textContent = "Denoising in progress...";
      }
    });
  },

  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (!SAMPLER_NODE_IDS.has(nodeData.name)) return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function() {
      const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;

      addStatusTrackerWidget(this);
      addVideoPreviewWidget(this);

      const videoFmtWidget = this.widgets?.find(w => w.name === "video_format");
      const audioFmtWidget = this.widgets?.find(w => w.name === "audio_format");
      const advancedSaveWidget = this.widgets?.find(w => w.name === "advanced_save" || w.name === "show_advanced");

      if (videoFmtWidget) {
        const origCallback = videoFmtWidget.callback;
        videoFmtWidget.callback = (val) => {
          if (val !== undefined) videoFmtWidget.value = val;
          origCallback?.(val);
          updateSamplerAudioFormatOptions(this, true);
          updateSamplerPixFmtOptions(this, true);
          updateSamplerWidgetVisibility(this);
        };
      }

      if (audioFmtWidget) {
        const origCallback = audioFmtWidget.callback;
        audioFmtWidget.callback = (val) => {
          if (val !== undefined) audioFmtWidget.value = val;
          origCallback?.(val);
          updateSamplerWidgetVisibility(this);
        };
      }

      if (advancedSaveWidget) {
        const origCallback = advancedSaveWidget.callback;
        advancedSaveWidget.callback = (val) => {
          if (val !== undefined) advancedSaveWidget.value = val;
          origCallback?.(val);
          updateSamplerWidgetVisibility(this, true);
        };
      }

      updateSamplerAudioFormatOptions(this, false);
      updateSamplerPixFmtOptions(this, false);
      updateSamplerWidgetVisibility(this, true);

      setTimeout(() => {
        updateSamplerAudioFormatOptions(this, false);
        updateSamplerPixFmtOptions(this, false);
        updateSamplerWidgetVisibility(this, true);
      }, 10);

      return r;
    };

    const onConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function() {
      const r = onConfigure ? onConfigure.apply(this, arguments) : undefined;
      setTimeout(() => {
        updateSamplerAudioFormatOptions(this, false);
        updateSamplerPixFmtOptions(this, false);
        updateSamplerWidgetVisibility(this, false);
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
      this._userResized = true;
      if (this._previewWidget && this._previewWidget.element) {
        let yOffset = this._previewWidget.last_y;
        if (!yOffset) {
          yOffset = 30;
          if (this.widgets) {
            for (let w of this.widgets) {
              if (w === this._previewWidget) break;
              if (w.hidden || w.type === "hidden") continue;
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

      if (message?.status && this._statusTracker) {
        this._currentIteration = message.status.current_iteration || 0;
        this._totalIterations = message.status.total_iterations || 1;
        const cur = this._currentIteration;
        const total = this._totalIterations;

        this._statusTracker.badge.textContent = `Iteration ${cur + 1} / ${total}`;
        this._statusTracker.statusLabel.textContent = (cur + 1 >= total) ? "Sampling Complete" : "Iteration Done";
        this._statusTracker.iterFill.style.width = "100%";
        this._statusTracker.totalFill.style.width = `${Math.round(((cur + 1) / total) * 100)}%`;
        this._statusTracker.totalPctText.textContent = `${Math.round(((cur + 1) / total) * 100)}%`;
      }

      const previewData = message?.videos?.[0] || message?.gifs?.[0];
      if (previewData && this.updatePreview) {
        this.updatePreview(previewData);
      }
    };
  },

  async nodeCreated(node) {
    if (!SAMPLER_NODE_IDS.has(node.comfyClass)) return;
    updateSamplerAudioFormatOptions(node, false);
    updateSamplerPixFmtOptions(node, false);
    updateSamplerWidgetVisibility(node, true);
  },

  async loadedGraphNode(node) {
    if (!SAMPLER_NODE_IDS.has(node.comfyClass)) return;
    setTimeout(() => {
      updateSamplerAudioFormatOptions(node, false);
      updateSamplerPixFmtOptions(node, false);
      updateSamplerWidgetVisibility(node, false);
    }, 20);
  }
});
