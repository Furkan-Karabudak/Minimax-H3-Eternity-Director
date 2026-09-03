import { app } from "../../../scripts/app.js";

const SAMPLER_NODE_IDS = ["H3Eternity_Sampler", "H3Eternity_SamplerAdvanced"];

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

const BASE_SAVE_WIDGETS = new Set(["filename", "video_format", "audio_format"]);

function cleanFormatName(fmt) {
  return (fmt || "").replace(" [default]", "").trim();
}

function updateSamplerWidgetVisibility(node, forceResetHeight = false) {
  if (!node || !node.widgets) return;

  const advancedSaveWidget = node.widgets.find(w => w.name === "advanced_save");
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
    if (!w._origType) {
      w._origType = w.type || "combo";
      w._origComputeSize = w.computeSize;
    }

    if (BASE_SAVE_WIDGETS.has(w.name)) {
      if (advancedSave) {
        w.hidden = false;
        w.type = w._origType;
        w.computeSize = w._origComputeSize;
      } else {
        w.hidden = true;
        w.type = "hidden";
        w.computeSize = () => [0, -4];
      }
      continue;
    }

    if (ALL_ADVANCED_NAMES.has(w.name)) {
      const isSampleRate = (w.name === "audio_sample_rate");
      const shouldShow = advancedSave && (isSampleRate || allowedVideoAdv.has(w.name) || allowedAudioAdv.has(w.name));

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
  }

  // Recalculate node size based on currently visible widgets and slots
  const sz = node.computeSize ? node.computeSize() : [340, 200];
  const targetW = Math.max(node.size?.[0] || 340, sz[0], 340);
  const targetH = sz[1];

  node.size = [targetW, targetH];
  if (node.setSize) {
    node.setSize(node.size);
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
  const baseAllowed = AUDIO_FORMAT_MAP[currentVideoFmt] || AUDIO_FORMAT_MAP["video/ffv1-mkv"];
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

app.registerExtension({
  name: "H3Eternity.Sampler",
  async nodeCreated(node) {
    if (!SAMPLER_NODE_IDS.includes(node.comfyClass)) return;

    const advancedSaveWidget = node.widgets?.find(w => w.name === "advanced_save");
    const videoFmtWidget = node.widgets?.find(w => w.name === "video_format");
    const audioFmtWidget = node.widgets?.find(w => w.name === "audio_format");

    if (advancedSaveWidget) {
      const origCallback = advancedSaveWidget.callback;
      advancedSaveWidget.callback = function (value) {
        origCallback?.apply(this, arguments);
        updateSamplerWidgetVisibility(node, true);
      };
    }

    if (videoFmtWidget) {
      const origCallback = videoFmtWidget.callback;
      videoFmtWidget.callback = function (value) {
        origCallback?.apply(this, arguments);
        updateSamplerPixFmtOptions(node, true);
        updateSamplerAudioFormatOptions(node, true);
        updateSamplerWidgetVisibility(node, false);
      };
    }

    if (audioFmtWidget) {
      const origCallback = audioFmtWidget.callback;
      audioFmtWidget.callback = function (value) {
        origCallback?.apply(this, arguments);
        updateSamplerWidgetVisibility(node, false);
      };
    }

    updateSamplerPixFmtOptions(node, false);
    updateSamplerAudioFormatOptions(node, false);
    updateSamplerWidgetVisibility(node, true);

    setTimeout(() => {
      updateSamplerPixFmtOptions(node, false);
      updateSamplerAudioFormatOptions(node, false);
      updateSamplerWidgetVisibility(node, true);
    }, 20);

    setTimeout(() => {
      updateSamplerPixFmtOptions(node, false);
      updateSamplerAudioFormatOptions(node, false);
      updateSamplerWidgetVisibility(node, true);
    }, 100);
  },

  async loadedGraphNode(node) {
    if (!SAMPLER_NODE_IDS.includes(node.comfyClass)) return;
    setTimeout(() => {
      updateSamplerPixFmtOptions(node, false);
      updateSamplerAudioFormatOptions(node, false);
      updateSamplerWidgetVisibility(node, false);
    }, 50);
  }
});
