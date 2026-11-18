"""File type detection, output formats and option defaults. The only place that lists formats."""
from dataclasses import dataclass
from pathlib import Path

INPUTS = {
    "audio": "mp3 m4a aac wav aiff aif flac opus ogg oga wma ac3 wv mp2",
    "video": "mp4 mov webm mkv avi m4v wmv flv mpg mpeg 3gp",
    "image": "jpg jpeg png heic heif avif webp tif tiff gif bmp",
    "doc": "txt md markdown html htm rtf docx odt",
    "pdf": "pdf",
}
EXT_TYPE = {e: t for t, exts in INPUTS.items() for e in exts.split()}


@dataclass(frozen=True)
class Fmt:
    id: str
    label: str
    ext: str
    codec: str = ""  # ffmpeg encoder for audio and video, else unused


def _f(kind, *items):
    return {i[0]: Fmt(*i) for i in items}


OUTPUTS = {
    "audio": _f("audio",
        ("mp3", "MP3", "mp3", "libmp3lame"), ("m4a", "M4A (AAC)", "m4a", "aac"),
        ("wav", "WAV", "wav", "pcm"), ("aiff", "AIFF", "aiff", "pcm"), ("flac", "FLAC", "flac", "flac"),
        ("alac", "ALAC", "m4a", "alac"), ("opus", "Opus", "opus", "libopus"),
        ("ogg", "OGG Vorbis", "ogg", "libvorbis"), ("wma", "WMA", "wma", "wmav2"),
        ("ac3", "AC3", "ac3", "ac3"), ("wv", "WavPack", "wv", "wavpack"), ("mp2", "MP2", "mp2", "mp2")),
    "video": _f("video",
        ("mp4", "MP4 (H.264)", "mp4", "h264"), ("mp4-hevc", "MP4 (HEVC)", "mp4", "hevc"),
        ("mp4-av1", "MP4 (AV1)", "mp4", "av1"), ("mov", "MOV (ProRes 422)", "mov", "prores_ks"),
        ("webm", "WebM (VP9)", "webm", "libvpx-vp9"), ("mkv", "MKV (H.264)", "mkv", "h264"),
        ("gif", "Animated GIF", "gif", "gif")),
    "image": _f("image",
        ("jpg", "JPEG", "jpg"), ("png", "PNG", "png"), ("heic", "HEIC", "heic"), ("avif", "AVIF", "avif"),
        ("webp", "WebP", "webp"), ("tiff", "TIFF", "tiff"), ("gif", "GIF", "gif"), ("bmp", "BMP", "bmp"),
        ("pdf", "PDF", "pdf")),
    "doc": _f("doc",
        ("pdf", "PDF", "pdf"), ("docx", "DOCX", "docx"), ("odt", "ODT", "odt"), ("rtf", "RTF", "rtf"),
        ("txt", "Plain text", "txt"), ("html", "HTML", "html")),
    "pdf": _f("pdf", ("png", "PNG (one per page)", "png"), ("jpg", "JPEG (one per page)", "jpg"),
        ("txt", "Plain text", "txt")),
}

DEFAULTS = {
    "audio": {"bitrate": 192, "sample_rate": 0, "channels": 0, "bit_depth": 16, "audio_track": 1},
    "video": {"video_quality": "medium", "height": 0, "fps": 0, "keep_audio": True, "audio_track": 1, "subtitles": False,
              "hw": True},
    "gif": {"width": 480, "fps": 12},
    "image": {"quality": 90, "max_size": 0},
    "doc": {"page": "A4"},
    "pdf": {"dpi": 150},
}


def file_type(path):
    return EXT_TYPE.get(Path(path).suffix.lower().lstrip("."))


def outputs_for(paths):
    """Output formats valid for the whole selection; audio and video can be mixed (audio targets)."""
    types = {file_type(p) for p in paths}
    if not types or None in types:
        return []
    if types == {"audio", "video"}:
        types = {"audio"}
    if len(types) != 1:
        return []
    t = types.pop()
    own = {Path(p).suffix.lower().lstrip(".") for p in paths}
    return [f for f in OUTPUTS[t].values() if not (len(own) == 1 and f.ext in own and t in ("doc", "image"))]


def output_fmt(src, fmt_id):
    """Fmt for this file and format id. Video files asked for an audio id get the audio format."""
    t = file_type(src)
    if t == "video" and fmt_id not in OUTPUTS["video"]:
        t = "audio"
    if t is None or fmt_id not in OUTPUTS[t]:
        raise ValueError(f"cannot convert {Path(src).name} to {fmt_id}")
    return t, OUTPUTS[t][fmt_id]


def option_key(kind, fmt_id):
    return "gif" if kind == "video" and fmt_id == "gif" else kind


def unique_path(src, ext, tag=""):
    """Beside the original, never overwriting: name.ext, name 2.ext, name 3.ext.
    The name is reserved by creating an empty file (exclusive create): two processes cannot pick the same name, and a
    dangling link is never followed. The caller writes into it, or deletes it on failure."""
    src = Path(src)
    stem = f"{src.stem}{tag}"
    out = src.with_name(f"{stem}.{ext}")
    n = 2
    while True:
        try:
            with open(out, "xb"):
                return out
        except FileExistsError:
            out = src.with_name(f"{stem} {n}.{ext}")
            n += 1
