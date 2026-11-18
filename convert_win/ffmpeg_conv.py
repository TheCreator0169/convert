"""Audio and video through ffmpeg. build_args is pure so it can be tested without ffmpeg."""
from functools import lru_cache

from .process import find_tool, run

LOSSY = {"libmp3lame", "aac", "libopus", "libvorbis", "wmav2", "ac3", "mp2"}
CRF = {"h264": (18, 23, 28), "hevc": (20, 26, 32), "libvpx-vp9": (24, 31, 37), "av1": (25, 32, 40)}
HW = {"h264": ("h264_nvenc", "h264_qsv", "h264_amf"), "hevc": ("hevc_nvenc", "hevc_qsv", "hevc_amf")}
SOFT = {"h264": "libx264", "hevc": "libx265", "libvpx-vp9": "libvpx-vp9"}


@lru_cache(maxsize=1)
def usable_encoders(ffmpeg):
    """Encoders ffmpeg lists; hardware ones only if a 1-frame test encode works."""
    _, out, _ = run([ffmpeg, "-hide_banner", "-encoders"])
    listed = {ln.split()[1] for ln in out.splitlines() if ln.startswith(" V") or ln.startswith(" A")}
    ok = set(listed)
    for enc in {e for es in HW.values() for e in es} & listed:
        rc, _, _ = run([ffmpeg, "-v", "error", "-f", "lavfi", "-i", "testsrc=s=256x256:d=0.1", "-frames:v", "1",
                        "-c:v", enc, "-f", "null", "-"])
        if rc:
            ok.discard(enc)
    return frozenset(ok)


def _video_encoder(codec, hw, have):
    if hw:
        for e in HW.get(codec, ()):
            if e in have:
                return e
    if codec == "av1":
        return "libsvtav1" if "libsvtav1" in have else "libaom-av1"
    return SOFT.get(codec, codec)


def _quality_args(enc, crf):
    if "nvenc" in enc:
        return ["-rc", "vbr", "-cq", str(crf)]
    if "qsv" in enc:
        return ["-global_quality", str(crf)]
    if "amf" in enc:
        return ["-rc", "cqp", "-qp_i", str(crf), "-qp_p", str(crf)]
    if enc in ("libvpx-vp9", "libaom-av1"):
        return ["-crf", str(crf), "-b:v", "0"]
    return ["-crf", str(crf)]


def _audio_args(fmt, o):
    c = fmt.codec
    deep = o["bit_depth"] == 24
    if c == "pcm":
        end = "be" if fmt.id == "aiff" else "le"
        a = ["-c:a", f"pcm_s{24 if deep else 16}{end}"]
    elif c in ("flac", "alac"):
        a = ["-c:a", c, "-sample_fmt", ("s32" if deep else "s16") + ("p" if c == "alac" else "")]
        if deep:
            a += ["-bits_per_raw_sample", "24"]
    else:
        a = ["-c:a", c]
        if c in LOSSY:
            a += ["-b:a", f"{o['bitrate']}k"]
    if o["sample_rate"]:
        a += ["-ar", str(o["sample_rate"])]
    if o["channels"]:
        a += ["-ac", str(o["channels"])]
    return a


def build_args(ffmpeg, src, dst, kind, fmt, opts, have=frozenset()):
    """Argument list for one conversion. kind is "audio" or "video"; opts is the option dict for it."""
    head = [ffmpeg, "-y", "-v", "error", "-nostdin", "-i", src]
    if kind == "audio":
        return head + ["-vn", "-map", "0:a:0", "-map_metadata", "0"] + _audio_args(fmt, opts) + [dst]
    if fmt.id == "gif":
        vf = (f"fps={max(1, opts['fps'])},scale='min({opts['width']},iw)':-1:flags=lanczos,"
              "split[a][b];[a]palettegen[p];[b][p]paletteuse")
        return head + ["-an", "-vf", vf, "-loop", "0", dst]
    codec = fmt.codec
    q = {"high": 0, "medium": 1, "low": 2}.get(opts["video_quality"], 1)
    args = head + ["-map", "0:v:0"]
    if codec == "prores_ks":
        args += ["-c:v", codec, "-profile:v", "2", "-pix_fmt", "yuv422p10le"]
    else:
        enc = _video_encoder(codec, opts["hw"], have)
        args += ["-c:v", enc] + _quality_args(enc, CRF[codec][q]) + ["-pix_fmt", "yuv420p"]
        if enc == "libx265" or enc.startswith("hevc"):
            args += ["-tag:v", "hvc1"]
        if enc == "libaom-av1":
            args += ["-cpu-used", "6"]
    if opts["height"]:
        args += ["-vf", f"scale=-2:'min(ih,{opts['height']})'"]
    if opts["fps"]:
        args += ["-r", str(opts["fps"])]
    if opts["keep_audio"]:
        a = {"libvpx-vp9": "libopus", "prores_ks": "pcm_s16le"}.get(codec, "aac")
        args += ["-map", "0:a:0?", "-c:a", a] + ([] if a == "pcm_s16le" else ["-b:a", "192k"])
    else:
        args += ["-an"]
    if fmt.ext in ("mp4", "mov"):
        args += ["-movflags", "+faststart"]
    return args + [dst]


def convert(src, dst, kind, fmt, opts, cancel=None):
    ffmpeg = find_tool("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found: install it (winget install Gyan.FFmpeg) and restart Convert")
    have = usable_encoders(ffmpeg) if kind == "video" else frozenset()
    rc, _, err = run(build_args(ffmpeg, src, dst, kind, fmt, opts, have), cancel)
    if rc:
        raise RuntimeError(f"ffmpeg failed: {err.strip().splitlines()[-1] if err.strip() else rc}")
