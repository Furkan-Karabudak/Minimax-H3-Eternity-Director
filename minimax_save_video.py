"""H3 Eternity - Save Video Node.

A high-fidelity, feature-rich video saving node supporting categorized video containers,
animations, image sequences, multiple embedded & external audio codecs, single-pass
muxing without intermediate disk clutter, and customizable metadata/naming.
"""

import os
import re
import sys
import json
import shutil
import datetime
import tempfile
import subprocess
from string import Template
from typing import List, Tuple, Dict, Any, Optional

import numpy as np
import torch
from PIL import Image, ExifTags
from PIL.PngImagePlugin import PngInfo

try:
    import folder_paths
except ImportError:
    class MockFolderPaths:
        @staticmethod
        def get_output_directory():
            return os.path.join(tempfile.gettempdir(), "comfy_output")
        @staticmethod
        def get_temp_directory():
            return os.path.join(tempfile.gettempdir(), "comfy_temp")
    folder_paths = MockFolderPaths()

try:
    from comfy.utils import ProgressBar
except ImportError:
    class ProgressBar:
        def __init__(self, total):
            self.total = total
        def update(self, n=1):
            pass


# ---------------------------------------------------------------------------
# FFmpeg Executable Discovery
# ---------------------------------------------------------------------------

def get_ffmpeg_path() -> Optional[str]:
    if "VHS_FORCE_FFMPEG_PATH" in os.environ:
        return os.environ.get("VHS_FORCE_FFMPEG_PATH")
    
    # Check imageio_ffmpeg
    try:
        from imageio_ffmpeg import get_ffmpeg_exe
        return get_ffmpeg_exe()
    except Exception:
        pass

    # Check system path
    sys_ffmpeg = shutil.which("ffmpeg")
    if sys_ffmpeg:
        return sys_ffmpeg

    # Check current directory
    if os.path.isfile("ffmpeg"):
        return os.path.abspath("ffmpeg")
    if os.path.isfile("ffmpeg.exe"):
        return os.path.abspath("ffmpeg.exe")

    return None


# ---------------------------------------------------------------------------
# Video Formats & Audio Codecs Master Mappings
# ---------------------------------------------------------------------------

VIDEO_FORMATS = [
    # Animations
    "animation/gif",
    "animation/ffmpeg-gif",
    "animation/webp",
    # Image Sequences
    "image_sequence/8bit-png",
    "image_sequence/16bit-png",
    # Videos
    "video/h264-mp4",
    "video/h265-mp4",
    "video/nvenc_av1-mp4",
    "video/nvenc_h264-mp4",
    "video/nvenc_hevc-mp4",
    "video/av1-webm",
    "video/webm",
    "video/ffv1-mkv",
    "video/ProRes",
]

AUDIO_FORMAT_MAP = {
    "animation": ["WAV (external)", "MP3 (external)", "FLAC (external)", "None"],
    "image_sequence": ["WAV (external)", "MP3 (external)", "FLAC (external)", "None"],
    "mp4": ["AAC", "Opus", "MP3", "FLAC", "ALAC", "WAV (external)", "MP3 (external)", "FLAC (external)", "None"],
    "webm": ["Opus", "Vorbis", "WAV (external)", "MP3 (external)", "FLAC (external)", "None"],
    "ffv1": ["FLAC", "PCM 16-bit (pcm_s16le)", "PCM 24-bit (pcm_s24le)", "Opus", "AAC", "MP3", "Vorbis", "WAV (external)", "MP3 (external)", "FLAC (external)", "None"],
    "prores": ["PCM 24-bit (pcm_s24le)", "PCM 16-bit (pcm_s16le)", "PCM 32-bit float (pcm_f32le)", "ALAC", "AAC", "WAV (external)", "MP3 (external)", "FLAC (external)", "None"],
}

AUDIO_SAMPLE_RATES = [
    "96000",
    "48000 (recommended)",
    "44100",
    "24000",
    "22050",
]

ALL_PIX_FMTS = [
    "bgra", "rgba64le", "yuv420p", "yuv420p10le", "p010le", "yuv422p", "yuv444p",
    "yuva420p", "yuva422p", "yuva444p", "yuv422p10le", "yuv444p10le",
    "yuv420p12le", "yuv422p12le", "yuv444p12le", "yuv420p14le", "yuv422p14le", "yuv444p14le",
    "yuv420p16le", "yuv422p16le", "yuv444p16le", "gray", "gray10le", "gray12le", "gray16le",
    "nv12", "bgr0", "rgb0"
]

BASE_AUDIO_FORMATS = [
    "AAC",
    "Opus",
    "Vorbis",
    "FLAC",
    "ALAC",
    "PCM 16-bit (pcm_s16le)",
    "PCM 24-bit (pcm_s24le)",
    "PCM 32-bit float (pcm_f32le)",
    "WAV (external)",
    "MP3 (external)",
    "FLAC (external)",
    "MP3",
    "None",
]

ALL_AUDIO_FORMATS = BASE_AUDIO_FORMATS + [f"{f} [default]" for f in BASE_AUDIO_FORMATS]


def get_audio_formats_for_video(video_format: str) -> List[str]:
    if video_format.startswith("animation/"):
        return AUDIO_FORMAT_MAP["animation"]
    elif video_format.startswith("image_sequence/"):
        return AUDIO_FORMAT_MAP["image_sequence"]
    elif "webm" in video_format:
        return AUDIO_FORMAT_MAP["webm"]
    elif "ffv1" in video_format:
        return AUDIO_FORMAT_MAP["ffv1"]
    elif "ProRes" in video_format or "prores" in video_format:
        return AUDIO_FORMAT_MAP["prores"]
    else:  # mp4
        return AUDIO_FORMAT_MAP["mp4"]


def get_video_extension(video_format: str) -> str:
    if video_format in ("animation/gif", "animation/ffmpeg-gif"):
        return "gif"
    elif video_format == "animation/webp":
        return "webp"
    elif video_format in ("image_sequence/8bit-png", "image_sequence/16bit-png"):
        return "%05d.png"
    elif video_format == "video/ffv1-mkv":
        return "mkv"
    elif video_format == "video/ProRes":
        return "mov"
    elif "webm" in video_format:
        return "webm"
    else:
        return "mp4"


# ---------------------------------------------------------------------------
# Filename Resolution Logic
# ---------------------------------------------------------------------------

def resolve_filename(filename_input: str, output_dir: str, ext: str) -> Tuple[str, str, str]:
    """Resolves target folder, subfolder, and 2-digit auto-incrementing base name.

    - If filename is provided ('h3_video'): 'h3_video' -> 'h3_video_01' -> 'h3_video_02'
    - If filename is empty ('')           : '00' -> '01' -> '02'
    - Supports subfolders like 'scenes/take1'
    """
    filename_input = (filename_input or "").strip()
    if not filename_input:
        subfolder = ""
        base_name = ""
        is_empty_base = True
    else:
        subfolder = os.path.dirname(filename_input)
        base_name = os.path.basename(filename_input)
        is_empty_base = False

    target_dir = os.path.join(output_dir, subfolder) if subfolder else output_dir
    os.makedirs(target_dir, exist_ok=True)

    existing_files = os.listdir(target_dir)

    if is_empty_base:
        max_num = -1
        for f in existing_files:
            m = re.match(r"^(\d+)(?:[_\.\-]|$)", f)
            if m:
                try:
                    num = int(m.group(1))
                    if num > max_num:
                        max_num = num
                except ValueError:
                    pass
        next_num = max_num + 1
        final_base = f"{next_num:02d}"
    else:
        exact_match_exists = False
        max_num = 0
        pattern = re.compile(rf"^{re.escape(base_name)}(?:_(\d+))?(?:[_\.\-]|$)", re.IGNORECASE)
        for f in existing_files:
            m = pattern.match(f)
            if m:
                exact_match_exists = True
                if m.group(1):
                    try:
                        num = int(m.group(1))
                        if num > max_num:
                            max_num = num
                    except ValueError:
                        pass
        if not exact_match_exists:
            final_base = base_name
        else:
            next_num = max_num + 1
            final_base = f"{base_name}_{next_num:02d}"

    return target_dir, subfolder, final_base


# ---------------------------------------------------------------------------
# Audio Serialization & Codec Argument Helpers
# ---------------------------------------------------------------------------

def parse_sample_rate(sr_input: Any) -> int:
    if isinstance(sr_input, (int, float)):
        return int(sr_input)
    s = str(sr_input).split()[0].strip()
    try:
        return int(s)
    except ValueError:
        return 48000


def write_audio_to_wav(audio_dict: Dict[str, Any], wav_path: str, target_sr: int = 48000):
    """Writes ComfyUI AUDIO dict {'waveform': Tensor, 'sample_rate': int} to WAV, resampling if needed."""
    waveform = audio_dict["waveform"]
    src_sr = int(audio_dict.get("sample_rate", 48000))
    if isinstance(waveform, torch.Tensor):
        waveform = waveform.detach().cpu()
        if waveform.ndim == 3:
            waveform = waveform[0]  # [C, L]
        if waveform.ndim == 1:
            waveform = waveform.unsqueeze(0)

        if src_sr != target_sr:
            try:
                import torchaudio.functional as AF
                waveform = AF.resample(waveform, src_sr, target_sr)
            except Exception:
                pass

    try:
        import torchaudio
        torchaudio.save(wav_path, waveform, target_sr)
    except Exception:
        import wave
        np_audio = (waveform.numpy().T * 32767.0).clip(-32768, 32767).astype(np.int16)
        channels = waveform.shape[0]
        with wave.open(wav_path, "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(2)
            wf.setframerate(target_sr)
            wf.writeframes(np_audio.tobytes())


def build_audio_ffmpeg_args(audio_format: str, kwargs: Dict[str, Any], sample_rate: int = 48000) -> List[str]:
    """Builds FFmpeg audio encoding flags for embedded audio."""
    clean_format = audio_format.replace(" [default]", "").strip()
    if not clean_format or clean_format == "None" or clean_format.endswith("(external)"):
        return ["-an"]

    common_audio_args = ["-ar", str(sample_rate), "-ac", "2"]

    if clean_format == "AAC":
        bitrate = kwargs.get("aac_bitrate", "256k")
        profile = kwargs.get("aac_profile", "LC")
        profile_flag = "aac_low" if profile == "LC" else "aac_low"
        return ["-c:a", "aac", "-b:a", bitrate, "-profile:a", profile_flag] + common_audio_args

    elif clean_format == "Opus":
        bitrate = kwargs.get("opus_bitrate", "160k")
        vbr = kwargs.get("opus_vbr", "On (VBR)")
        vbr_flag = "on" if "On" in vbr else ("off" if "Off" in vbr else "constrained")
        content = kwargs.get("opus_content", "audio")
        complexity = str(kwargs.get("opus_complexity", 10))
        return ["-c:a", "libopus", "-b:a", bitrate, "-vbr", vbr_flag, "-application", content, "-compression_level", complexity] + common_audio_args

    elif clean_format == "Vorbis":
        mode = kwargs.get("vorbis_mode", "Quality (VBR)")
        if "Quality" in mode:
            q = str(kwargs.get("vorbis_quality", 6))
            return ["-c:a", "libvorbis", "-q:a", q] + common_audio_args
        else:
            b = kwargs.get("vorbis_bitrate", "192k")
            return ["-c:a", "libvorbis", "-b:a", b] + common_audio_args

    elif clean_format == "FLAC":
        bit_depth = kwargs.get("flac_bit_depth", "24-bit")
        sample_fmt = "s32" if "24" in bit_depth else "s16"
        comp = str(kwargs.get("flac_compression", 5))
        lpc = kwargs.get("flac_lpc", "High")
        lpc_passes = "2" if lpc == "High" else ("1" if lpc == "Medium" else "0")
        return ["-c:a", "flac", "-sample_fmt", sample_fmt, "-compression_level", comp, "-lpc_passes", lpc_passes] + common_audio_args

    elif clean_format == "ALAC":
        bit_depth = kwargs.get("alac_bit_depth", "24-bit")
        sample_fmt = "s32p" if "24" in bit_depth else "s16p"
        frame_size = str(kwargs.get("alac_frame_size", 4096))
        return ["-c:a", "alac", "-sample_fmt", sample_fmt, "-frame_size", frame_size] + common_audio_args

    elif clean_format == "PCM 16-bit (pcm_s16le)":
        return ["-c:a", "pcm_s16le"] + common_audio_args

    elif clean_format == "PCM 24-bit (pcm_s24le)":
        return ["-c:a", "pcm_s24le"] + common_audio_args

    elif clean_format == "PCM 32-bit float (pcm_f32le)":
        return ["-c:a", "pcm_f32le"] + common_audio_args

    elif clean_format == "MP3":
        bitrate = kwargs.get("mp3_bitrate", "320k")
        return ["-c:a", "libmp3lame", "-b:a", bitrate] + common_audio_args

    return ["-c:a", "aac", "-b:a", "256k"] + common_audio_args


def save_external_audio(temp_wav: str, target_audio_path: str, audio_format: str, kwargs: Dict[str, Any], ffmpeg_bin: str, sample_rate: int = 48000):
    """Encodes temporary WAV to standalone external audio file."""
    clean_format = audio_format.replace(" [default]", "").strip()
    common_audio_args = ["-ar", str(sample_rate), "-ac", "2"]
    if clean_format.startswith("WAV"):
        bit_depth = kwargs.get("wav_bit_depth", "24-bit")
        codec = "pcm_s32le" if "32" in bit_depth else ("pcm_s24le" if "24" in bit_depth else "pcm_s16le")
        cmd = [ffmpeg_bin, "-y", "-i", temp_wav, "-c:a", codec] + common_audio_args + [target_audio_path]
    elif clean_format.startswith("MP3"):
        bitrate = kwargs.get("mp3_bitrate", "320k")
        cmd = [ffmpeg_bin, "-y", "-i", temp_wav, "-c:a", "libmp3lame", "-b:a", bitrate] + common_audio_args + [target_audio_path]
    elif clean_format.startswith("FLAC"):
        bit_depth = kwargs.get("flac_bit_depth", "24-bit")
        sample_fmt = "s32" if "24" in bit_depth else "s16"
        comp = str(kwargs.get("flac_compression", 5))
        cmd = [ffmpeg_bin, "-y", "-i", temp_wav, "-c:a", "flac", "-sample_fmt", sample_fmt, "-compression_level", comp] + common_audio_args + [target_audio_path]
    else:
        cmd = [ffmpeg_bin, "-y", "-i", temp_wav, "-c:a", "pcm_s24le"] + common_audio_args + [target_audio_path]

    subprocess.run(cmd, check=True, capture_output=True)


# ---------------------------------------------------------------------------
# Video Codec Argument Helpers
# ---------------------------------------------------------------------------

_AV1_ENCODER_CACHE = None

def get_av1_encoder(ffmpeg_bin: Optional[str]) -> str:
    global _AV1_ENCODER_CACHE
    if _AV1_ENCODER_CACHE is not None:
        return _AV1_ENCODER_CACHE
    if not ffmpeg_bin:
        return "libsvtav1"
    try:
        res = subprocess.run([ffmpeg_bin, "-encoders"], capture_output=True, text=True, timeout=5)
        stdout = res.stdout or ""
        if "libsvtav1" in stdout:
            _AV1_ENCODER_CACHE = "libsvtav1"
        elif "libaom-av1" in stdout:
            _AV1_ENCODER_CACHE = "libaom-av1"
        elif "librav1e" in stdout:
            _AV1_ENCODER_CACHE = "librav1e"
        elif "av1_nvenc" in stdout:
            _AV1_ENCODER_CACHE = "av1_nvenc"
        else:
            _AV1_ENCODER_CACHE = "libsvtav1"
    except Exception:
        _AV1_ENCODER_CACHE = "libsvtav1"
    return _AV1_ENCODER_CACHE


def build_video_ffmpeg_args(video_format: str, kwargs: Dict[str, Any], has_alpha: bool = False) -> Tuple[List[str], Optional[str]]:
    """Builds video encoding FFmpeg arguments. Returns (main_args, fake_trc)."""
    if video_format == "video/h264-mp4":
        crf = str(kwargs.get("crf", 19))
        preset = kwargs.get("preset", "medium")
        pix_fmt = kwargs.get("pix_fmt", "yuv420p")
        return [
            "-c:v", "libx264", "-pix_fmt", pix_fmt, "-crf", crf, "-preset", preset,
            "-vf", "scale=out_color_matrix=bt709",
            "-color_range", "tv", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709"
        ], "bt709"

    elif video_format == "video/h265-mp4":
        crf = str(kwargs.get("crf", 23))
        preset = kwargs.get("preset", "medium")
        pix_fmt = kwargs.get("pix_fmt", "yuv420p10le")
        return [
            "-c:v", "libx265", "-pix_fmt", pix_fmt, "-crf", crf, "-preset", preset,
            "-vf", "scale=out_color_matrix=bt709",
            "-color_range", "tv", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709"
        ], "bt709"

    elif video_format == "video/nvenc_h264-mp4":
        bitrate_val = float(kwargs.get("bitrate", 20.0))
        bitrate = f"{bitrate_val:g}M"
        pix_fmt = kwargs.get("pix_fmt", "yuv420p")
        return [
            "-c:v", "h264_nvenc", "-b:v", bitrate, "-pix_fmt", pix_fmt,
            "-vf", "scale=out_color_matrix=bt709",
            "-color_range", "tv", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709"
        ], "bt709"

    elif video_format == "video/nvenc_hevc-mp4":
        bitrate_val = float(kwargs.get("bitrate", 15.0))
        bitrate = f"{bitrate_val:g}M"
        pix_fmt = kwargs.get("pix_fmt", "p010le")
        return [
            "-c:v", "hevc_nvenc", "-b:v", bitrate, "-pix_fmt", pix_fmt,
            "-vf", "scale=out_color_matrix=bt709",
            "-color_range", "tv", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709"
        ], "bt709"

    elif video_format == "video/nvenc_av1-mp4":
        bitrate_val = float(kwargs.get("bitrate", 10.0))
        bitrate = f"{bitrate_val:g}M"
        pix_fmt = kwargs.get("pix_fmt", "p010le")
        return [
            "-c:v", "av1_nvenc", "-b:v", bitrate, "-pix_fmt", pix_fmt,
            "-vf", "scale=out_color_matrix=bt709",
            "-color_range", "tv", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709"
        ], "bt709"

    elif video_format == "video/av1-webm":
        crf = str(kwargs.get("crf", 26))
        pix_fmt = kwargs.get("pix_fmt", "yuv420p10le")
        ffmpeg_bin = get_ffmpeg_path()
        encoder = get_av1_encoder(ffmpeg_bin)
        
        args = ["-c:v", encoder]
        if encoder == "libsvtav1":
            args += ["-crf", crf, "-pix_fmt", pix_fmt]
        elif encoder == "libaom-av1":
            args += ["-crf", crf, "-b:v", "0", "-cpu-used", "4", "-pix_fmt", pix_fmt]
        elif encoder == "librav1e":
            args += ["-qp", crf, "-pix_fmt", pix_fmt]
        elif encoder == "av1_nvenc":
            bitrate_val = float(kwargs.get("bitrate", 10.0))
            args += ["-b:v", f"{bitrate_val:g}M", "-pix_fmt", pix_fmt]
        else:
            args += ["-crf", crf, "-pix_fmt", pix_fmt]

        args += [
            "-vf", "scale=out_color_matrix=bt709",
            "-color_range", "tv", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709"
        ]
        return args, "bt709"

    elif video_format == "video/webm":
        crf = str(kwargs.get("crf", 30))
        pix_fmt = kwargs.get("pix_fmt", "yuv420p")
        return [
            "-c:v", "libvpx-vp9", "-crf", crf, "-b:v", "0", "-pix_fmt", pix_fmt,
            "-vf", "scale=out_color_matrix=bt709",
            "-color_range", "tv", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709"
        ], "bt709"

    elif video_format == "video/ffv1-mkv":
        level = str(kwargs.get("level", "3"))
        coder = str(kwargs.get("coder", "1"))
        context = str(kwargs.get("context", "1"))
        gop = str(kwargs.get("gop_size", 1))
        slices = str(kwargs.get("slices", "16"))
        slicecrc = str(kwargs.get("slicecrc", "1"))
        pix_fmt = kwargs.get("pix_fmt", "bgra")
        return [
            "-c:v", "ffv1", "-level", level, "-coder", coder, "-context", context,
            "-g", gop, "-slices", slices, "-slicecrc", slicecrc, "-pix_fmt", pix_fmt
        ], None

    elif video_format == "video/ProRes":
        prof = kwargs.get("profile", "hq")
        prof_map = {"lt": "1", "standard": "2", "hq": "3", "4444": "4", "4444xq": "5"}
        p_val = prof_map.get(prof, "3")
        args = ["-c:v", "prores_ks", "-profile:v", p_val]
        if prof in ("4444", "4444xq"):
            args += ["-pix_fmt", "yuva444p10le" if has_alpha else "yuv444p10le"]
        args += [
            "-vf", "scale=out_color_matrix=bt709",
            "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709"
        ]
        return args, "bt709"

    elif video_format == "animation/ffmpeg-gif":
        dither = kwargs.get("dither", "sierra2_4a")
        filt = f"[0:v] split [a][b]; [a] palettegen=reserve_transparent=on:transparency_color=ffffff [p]; [b][p] paletteuse=dither={dither}"
        return ["-filter_complex", filt], None

    elif video_format == "image_sequence/8bit-png":
        return ["-pix_fmt", "rgb24"], None

    elif video_format == "image_sequence/16bit-png":
        return ["-pix_fmt", "rgba64"], None

    return ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "19"], "bt709"


def tensor_to_bytes(tensor: torch.Tensor) -> bytes:
    """Converts HWC float tensor [0, 1] to uint8 bytes."""
    np_arr = (tensor.detach().cpu().numpy() * 255.0 + 0.5).clip(0, 255).astype(np.uint8)
    return np_arr.tobytes()


# ---------------------------------------------------------------------------
# Node Implementation
# ---------------------------------------------------------------------------

class H3_Eternity_Save_Video:
    """High-fidelity Video Saving Node for MiniMax H3 and ComfyUI.

    Supports categorized video containers, animations, image sequences,
    multiple embedded/external audio codecs with customizable sample rate,
    and single-pass muxing without intermediate disk clutter.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "frame_rate": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 120.0, "step": 1.0}),
                "loop_count": ("INT", {"default": 0, "min": 0, "max": 100, "step": 1}),
                "filename": ("STRING", {"default": "h3_video"}),
                "video_format": (VIDEO_FORMATS, {"default": "video/h264-mp4"}),
                "audio_format": (ALL_AUDIO_FORMATS, {"default": "AAC"}),
                "pingpong": ("BOOLEAN", {"default": False}),
                "save_metadata_image": ("BOOLEAN", {"default": True, "tooltip": "Save first frame as PNG with workflow metadata embedded."}),
                "show_advanced": ("BOOLEAN", {"default": False, "tooltip": "Show advanced video & audio codec options in UI."}),
            },
            "optional": {
                "audio": ("AUDIO",),
                # Video Advanced Settings
                "crf": ("INT", {"default": 19, "min": 0, "max": 63, "step": 1}),
                "preset": (["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"], {"default": "medium"}),
                "bitrate": ("FLOAT", {"default": 20.0, "min": 0.1, "max": 999.0, "step": 0.5, "tooltip": "Bitrate in Mbps for NVENC codecs"}),
                "pix_fmt": (ALL_PIX_FMTS, {"default": "yuv420p"}),
                "profile": (["hq", "lt", "standard", "4444", "4444xq"], {"default": "hq"}),
                "level": (["3", "1", "0"], {"default": "3"}),
                "coder": (["1", "0", "2"], {"default": "1"}),
                "context": (["1", "0"], {"default": "1"}),
                "gop_size": ("INT", {"default": 1, "min": 1, "max": 300, "step": 1}),
                "slices": (["16", "4", "6", "9", "12", "20", "24", "30"], {"default": "16"}),
                "slicecrc": (["1", "0"], {"default": "1"}),
                "dither": (["sierra2_4a", "bayer", "heckbert", "floyd_steinberg", "sierra2", "sierra3", "burkes", "atkinson", "none"], {"default": "sierra2_4a"}),
                "lossless": ("BOOLEAN", {"default": True}),
                # Audio Advanced Settings
                "audio_sample_rate": (AUDIO_SAMPLE_RATES, {"default": "48000 (recommended)"}),
                "aac_bitrate": (["256k", "128k", "192k", "320k"], {"default": "256k"}),
                "aac_control": (["CBR", "VBR"], {"default": "CBR"}),
                "aac_profile": (["LC", "HE-AAC", "HE-AACv2", "LD", "ELD"], {"default": "LC"}),
                "opus_bitrate": (["160k", "64k", "96k", "128k", "192k", "256k", "320k"], {"default": "160k"}),
                "opus_vbr": (["On (VBR)", "Off (CBR)", "Constrained VBR"], {"default": "On (VBR)"}),
                "opus_content": (["audio", "voip", "lowdelay"], {"default": "audio"}),
                "opus_complexity": ("INT", {"default": 10, "min": 0, "max": 10, "step": 1}),
                "vorbis_mode": (["Quality (VBR)", "Bitrate (CBR)"], {"default": "Quality (VBR)"}),
                "vorbis_quality": ("INT", {"default": 6, "min": 0, "max": 10, "step": 1}),
                "vorbis_bitrate": (["192k", "128k", "160k", "256k", "320k"], {"default": "192k"}),
                "flac_bit_depth": (["24-bit", "16-bit"], {"default": "24-bit"}),
                "flac_compression": ("INT", {"default": 5, "min": 0, "max": 12, "step": 1}),
                "flac_lpc": (["High", "Medium", "Low", "None"], {"default": "High"}),
                "alac_bit_depth": (["24-bit", "16-bit"], {"default": "24-bit"}),
                "alac_frame_size": (["4096", "2048", "1024", "512"], {"default": "4096"}),
                "wav_bit_depth": (["24-bit", "16-bit", "32-bit float"], {"default": "24-bit"}),
                "mp3_bitrate": (["320k", "128k", "192k", "256k"], {"default": "320k"}),
            },
            "hidden": {
                "prompt": "PROMPT",
                "extra_pnginfo": "EXTRA_PNGINFO",
                "unique_id": "UNIQUE_ID",
            },
        }

    RETURN_TYPES = ("VHS_FILENAMES",)
    RETURN_NAMES = ("Filenames",)
    OUTPUT_NODE = True
    CATEGORY = "MiniMax H3"
    FUNCTION = "save_video"

    @classmethod
    def VALIDATE_INPUTS(cls, **kwargs):
        return True

    def save_video(
        self,
        images: torch.Tensor,
        frame_rate: float = 24.0,
        loop_count: int = 0,
        filename: str = "h3_video",
        video_format: str = "video/h264-mp4",
        audio_format: str = "AAC",
        pingpong: bool = False,
        save_metadata_image: bool = True,
        show_advanced: bool = False,
        audio_sample_rate: str = "48000 (recommended)",
        audio: Optional[Dict[str, Any]] = None,
        prompt: Optional[Dict[str, Any]] = None,
        extra_pnginfo: Optional[Dict[str, Any]] = None,
        unique_id: Optional[str] = None,
        **kwargs,
    ):
        if images is None or len(images) == 0:
            return {"ui": {"gifs": []}, "result": ((False, []),)}

        num_frames = images.shape[0]
        height, width = images.shape[1], images.shape[2]
        has_alpha = (images.shape[3] == 4) if images.ndim == 4 else False
        clean_audio_format = audio_format.replace(" [default]", "").strip()
        target_sr = parse_sample_rate(audio_sample_rate)

        # WebM container audio compatibility check
        if "webm" in video_format and not clean_audio_format.endswith("(external)") and clean_audio_format != "None":
            if clean_audio_format not in ("Opus", "Vorbis"):
                clean_audio_format = "Opus"

        ext = get_video_extension(video_format)
        output_dir = folder_paths.get_output_directory()
        target_dir, subfolder, final_base = resolve_filename(filename, output_dir, ext)

        output_files = []

        # -------------------------------------------------------------------
        # 1. First Frame Metadata Image (.png)
        # -------------------------------------------------------------------
        metadata = PngInfo()
        video_metadata = {}
        if prompt is not None:
            metadata.add_text("prompt", json.dumps(prompt))
            video_metadata["prompt"] = json.dumps(prompt)
        if extra_pnginfo is not None:
            for k, v in extra_pnginfo.items():
                metadata.add_text(k, json.dumps(v))
                video_metadata[k] = v
        metadata.add_text("CreationTime", datetime.datetime.now().isoformat(" ")[:19])

        first_image_file = f"{final_base}.png"
        first_image_path = os.path.join(target_dir, first_image_file)
        if save_metadata_image:
            first_frame_np = (images[0].detach().cpu().numpy() * 255.0 + 0.5).clip(0, 255).astype(np.uint8)
            Image.fromarray(first_frame_np).save(first_image_path, pnginfo=metadata, compress_level=4)
            output_files.append(first_image_path)

        # -------------------------------------------------------------------
        # 2. Audio Pre-Processing (Temp WAV)
        # -------------------------------------------------------------------
        temp_wav_path = None
        has_audio = (audio is not None and isinstance(audio, dict) and "waveform" in audio)
        is_external_audio = clean_audio_format.endswith("(external)")
        is_embedded_audio = (has_audio and not is_external_audio and clean_audio_format != "None")

        if has_audio and clean_audio_format != "None":
            temp_dir = folder_paths.get_temp_directory()
            os.makedirs(temp_dir, exist_ok=True)
            temp_wav_path = os.path.join(temp_dir, f"temp_audio_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.wav")
            write_audio_to_wav(audio, temp_wav_path, target_sr=target_sr)

        # -------------------------------------------------------------------
        # 3. Video / Animation / Sequence Generation
        # -------------------------------------------------------------------
        pbar = ProgressBar(num_frames)

        # Frame sequence generator supporting pingpong
        def get_frame_generator():
            indices = list(range(num_frames))
            if pingpong and num_frames > 2:
                indices = indices + list(range(num_frames - 2, 0, -1))
            for idx in indices:
                yield images[idx]

        target_video_file = f"{final_base}.{ext}" if "%" not in ext else f"{final_base}_{ext}"
        target_video_path = os.path.join(target_dir, target_video_file)

        ffmpeg_bin = get_ffmpeg_path()

        try:
            if video_format == "animation/gif":
                # Pillow GIF
                frames = [Image.fromarray((f.detach().cpu().numpy() * 255.0 + 0.5).clip(0, 255).astype(np.uint8)) for f in get_frame_generator()]
                for _ in range(num_frames):
                    pbar.update(1)
                frames[0].save(
                    target_video_path,
                    format="GIF",
                    save_all=True,
                    append_images=frames[1:],
                    duration=round(1000.0 / frame_rate),
                    loop=loop_count,
                    disposal=2,
                    compress_level=4,
                )
                output_files.append(target_video_path)

            elif video_format == "animation/webp":
                # Pillow WebP
                frames = [Image.fromarray((f.detach().cpu().numpy() * 255.0 + 0.5).clip(0, 255).astype(np.uint8)) for f in get_frame_generator()]
                for _ in range(num_frames):
                    pbar.update(1)
                exif = Image.Exif()
                exif[ExifTags.IFD.Exif] = {36867: datetime.datetime.now().isoformat(" ")[:19]}
                frames[0].save(
                    target_video_path,
                    format="WEBP",
                    save_all=True,
                    append_images=frames[1:],
                    duration=round(1000.0 / frame_rate),
                    loop=loop_count,
                    lossless=kwargs.get("lossless", True),
                    exif=exif,
                )
                output_files.append(target_video_path)

            else:
                # FFmpeg-based generation (Videos, MKV, MOV, WebM, PNG Sequences, FFmpeg-GIF)
                if ffmpeg_bin is None:
                    raise ProcessLookupError("FFmpeg executable not found. Please install ffmpeg or imageio-ffmpeg.")

                video_args, fake_trc = build_video_ffmpeg_args(video_format, kwargs, has_alpha)
                audio_args = build_audio_ffmpeg_args(clean_audio_format, kwargs, sample_rate=target_sr) if is_embedded_audio else ["-an"]

                cmd = [
                    ffmpeg_bin,
                    "-y",
                    "-f", "rawvideo",
                    "-pix_fmt", "rgba" if has_alpha else "rgb24",
                    "-s", f"{width}x{height}",
                    "-r", str(frame_rate),
                    "-i", "-",  # Video from stdin pipe:0
                ]

                if is_embedded_audio and temp_wav_path and os.path.exists(temp_wav_path):
                    cmd += ["-i", temp_wav_path]

                cmd += video_args
                if is_embedded_audio:
                    cmd += audio_args + ["-shortest"]

                cmd.append(target_video_path)

                proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )

                try:
                    for frame_tensor in get_frame_generator():
                        data = tensor_to_bytes(frame_tensor)
                        proc.stdin.write(data)
                        pbar.update(1)
                    proc.stdin.close()
                except (BrokenPipeError, OSError) as pipe_err:
                    try:
                        proc.stdin.close()
                    except Exception:
                        pass
                    _, stderr = proc.communicate()
                    err_msg = stderr.decode("utf-8", errors="backslashreplace") if stderr else str(pipe_err)
                    raise RuntimeError(f"FFmpeg encoding failed with code {proc.returncode or 1}:\n{err_msg}")

                _, stderr = proc.communicate()

                if proc.returncode != 0:
                    err_msg = stderr.decode("utf-8", errors="backslashreplace") if stderr else "Unknown error"
                    raise RuntimeError(f"FFmpeg process failed with code {proc.returncode}:\n{err_msg}")

                if "image_sequence" in video_format:
                    first_seq_file = os.path.join(target_dir, f"{final_base}_00001.png")
                    output_files.append(first_seq_file)
                else:
                    output_files.append(target_video_path)

            # -------------------------------------------------------------------
            # 4. External Audio Saving (if applicable)
            # -------------------------------------------------------------------
            if has_audio and is_external_audio and temp_wav_path and os.path.exists(temp_wav_path):
                if clean_audio_format.startswith("WAV"):
                    audio_ext = "wav"
                elif clean_audio_format.startswith("MP3"):
                    audio_ext = "mp3"
                elif clean_audio_format.startswith("FLAC"):
                    audio_ext = "flac"
                else:
                    audio_ext = "wav"

                ext_audio_file = f"{final_base}.{audio_ext}"
                ext_audio_path = os.path.join(target_dir, ext_audio_file)
                save_external_audio(temp_wav_path, ext_audio_path, clean_audio_format, kwargs, ffmpeg_bin, sample_rate=target_sr)
                output_files.append(ext_audio_path)

        finally:
            if temp_wav_path and os.path.exists(temp_wav_path):
                try:
                    os.remove(temp_wav_path)
                except Exception:
                    pass

        # -------------------------------------------------------------------
        # 5. UI Preview Payload
        # -------------------------------------------------------------------
        total_saved_frames = num_frames
        if pingpong and num_frames > 2:
            total_saved_frames = num_frames + (num_frames - 2)

        if "image_sequence" in video_format:
            primary_output_file = os.path.join(target_dir, f"{final_base}_00001.png")
            primary_output_filename = f"{final_base}_00001.png"
            preview = {
                "filename": primary_output_filename,
                "base_pattern": f"{final_base}_%05d.png",
                "count": total_saved_frames,
                "subfolder": subfolder,
                "type": "output",
                "format": video_format,
                "frame_rate": frame_rate,
                "workflow": first_image_file if save_metadata_image else None,
                "fullpath": primary_output_file,
            }
        else:
            primary_output_file = target_video_path
            primary_output_filename = os.path.basename(target_video_path)
            preview = {
                "filename": primary_output_filename,
                "subfolder": subfolder,
                "type": "output",
                "format": video_format,
                "frame_rate": frame_rate,
                "workflow": first_image_file if save_metadata_image else None,
                "fullpath": primary_output_file,
            }

        return {
            "ui": {
                "gifs": [preview],
                "videos": [{"filename": primary_output_filename, "subfolder": subfolder, "type": "output", "format": video_format}],
            },
            "result": ((True, output_files),),
        }


NODE_CLASS_MAPPINGS = {
    "H3_Eternity_Save_Video": H3_Eternity_Save_Video,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "H3_Eternity_Save_Video": "H3 Eternity - Save Video",
}
