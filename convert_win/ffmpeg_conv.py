"""Audio and video through ffmpeg. build_args is pure so it can be tested without ffmpeg."""
import re
from functools import lru_cache

from .process import find_tool, run

LOSSY = {"libmp3lame", "aac", "libopus", "libvorbis", "wmav2", "ac3", "mp2"}
CRF = {"h264": (18, 23, 28), "hevc": (20, 26, 32), "libvpx-vp9": (24, 31, 37), "av1": (25, 32, 40)}
HW = {"h264": ("h264_nvenc", "h264_qsv", "h264_amf"), "hevc": ("hevc_nvenc", "hevc_qsv", "hevc_amf")}
SOFT = {"h264": "libx264", "hevc": "libx265", "libvpx-vp9": "libvpx-vp9"}
SUB_CODEC = {"mp4": "mov_text", "mov": "mov_text", "webm": "webvtt"}  # mkv keeps the stream as it is
BITMAP_SUBS = {"hdmv_pgs_subtitle", "dvd_subtitle", "dvb_subtitle", "xsub"}  # pictures, cannot become text


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
    # -protocol_whitelist file: a path that looks like a URL must never make ffmpeg touch the network
    head = [ffmpeg, "-y", "-v", "error", "-nostdin", "-protocol_whitelist", "file", "-i", src]
    if kind == "audio":
        return head + ["-vn", "-map", f"0:a:{opts['audio_track'] - 1}", "-map_metadata", "0"] + _audio_args(fmt, opts) + [dst]
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
        args += ["-map", f"0:a:{opts['audio_track'] - 1}?", "-c:a", a] + ([] if a == "pcm_s16le" else ["-b:a", "192k"])
    else:
        args += ["-an"]
    if opts["subtitles"]:
        args += ["-map", "0:s?", "-c:s", SUB_CODEC.get(fmt.ext, "copy")]
    if fmt.ext in ("mp4", "mov"):
        args += ["-movflags", "+faststart"]
    return args + [dst]


def _probe(ffmpeg, src):
    """(audio track count, subtitle codec names) of the input."""
    # no output file: ffmpeg lists the streams on stderr and exits 1, which is fine here
    _, _, err = run([ffmpeg, "-hide_banner", "-protocol_whitelist", "file", "-i", src])
    audio = len(re.findall(r"^\s+Stream #0:\d+\S*: Audio:", err, re.M))
    return audio, re.findall(r"^\s+Stream #0:\d+\S*: Subtitle: (\w+)", err, re.M)


def convert(src, dst, kind, fmt, opts, cancel=None):
    """Returns a warning string when audio tracks or subtitles were left out, else None."""
    ffmpeg = find_tool("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found: install it (winget install Gyan.FFmpeg) and restart Convert")
    n_audio, subs = _probe(ffmpeg, src)
    video = kind == "video" and fmt.id != "gif"
    uses_audio = kind == "audio" or (video and opts["keep_audio"])
    track = opts["audio_track"] if uses_audio else 1  # the gif options have none
    if uses_audio and track > max(n_audio, 1):
        raise RuntimeError(f"audio track {track} not found: the file has {n_audio}")
    out = []
    if uses_audio and n_audio > 1:
        out.append(f"{n_audio} audio tracks, only the first was kept" if track == 1
                   else f"{n_audio} audio tracks, only track {track} was kept")
    if video and subs:
        if opts["subtitles"] and fmt.ext != "mkv" and BITMAP_SUBS & set(subs):
            opts = {**opts, "subtitles": False}  # picture subtitles cannot be converted to text
            out.append("picture subtitles cannot go in " + fmt.ext.upper() + ", they were dropped (MKV keeps them)")
        elif not opts["subtitles"]:
            out.append("subtitles were dropped")
    have = usable_encoders(ffmpeg) if kind == "video" else frozenset()
    rc, _, err = run(build_args(ffmpeg, src, dst, kind, fmt, opts, have), cancel)
    if rc:
        raise RuntimeError(f"ffmpeg failed: {err.strip().splitlines()[-1] if err.strip() else rc}")
    return "; ".join(out) or None
