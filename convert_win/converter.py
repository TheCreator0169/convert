"""One entry point: convert a file to a format id, return the files written."""
import ctypes
import logging
import os
import re
from pathlib import Path

from send2trash import send2trash

from . import doc_conv, ffmpeg_conv, image_conv, pdf_conv
from .formats import option_key, output_fmt, unique_path
from .process import Cancelled

log = logging.getLogger("convert")


def describe(e):
    """Text for an error: some exceptions (NotImplementedError, KeyError()) carry no message."""
    return str(e) or type(e).__name__


def scrub(text, path):
    """Replace the folder of `path` in `text` so logs keep file names only."""
    folder = str(Path(os.path.abspath(path)).parent)
    # PIL quotes the path with repr(), which doubles the backslashes: scrub both spellings
    return str(text).replace(folder.replace("\\", "\\\\"), "...").replace(folder, "...")


def _drive_type(letter):
    """GetDriveTypeW on `letter:\\`. 4 means DRIVE_REMOTE (a mapped network drive). "unknown" when the call fails.
    Only the drive type is read: no share is opened."""
    try:
        return ctypes.WinDLL("kernel32").GetDriveTypeW(f"{letter}:\\")
    except Exception:
        return "unknown"


def _refusal(p):
    """Why `p` is refused, or None when it is allowed.
    "network": UNC, \\\\server\\share, \\\\?\\UNC\\..., //?/UNC/....
    "device": \\\\?\\GLOBALROOT\\..., \\\\?\\Global\\... (any), \\\\??\\..., \\\\.\\... (device paths).
    "remote": a mapped network drive, Z:\\... or \\\\?\\Z:\\..., when GetDriveTypeW says 4 (DRIVE_REMOTE).
    "unsupported": any other \\\\?\\ path, e.g. \\\\?\\PhysicalDrive0 or \\\\?\\PIPE\\...
    Allowed: local drives (C:\\..., \\\\?\\C:\\...), \\\\?\\Volume{GUID}\\..., \\\\wsl$\\ and \\\\wsl.localhost\\ (the Linux
    subsystem on this PC). A drive whose type cannot be read is allowed."""
    # absolute first: a relative name resolves against the working folder, which may itself be on a share
    # ASCII-only upper-casing: Unicode upper() turns U+017F into "S" and would let \\w<U+017F>l$ pass as WSL
    s = "".join(c.upper() if c < "\x80" else c for c in os.path.abspath(str(p)).replace("/", "\\"))
    if s.startswith("\\\\?\\"):
        rest = s[4:]
        if rest.startswith("UNC\\"):
            return "network"
        if rest.startswith(("GLOBALROOT\\", "GLOBAL\\")):
            return "device"
        if re.match(r"[A-Z]:(\\|$)", rest):
            return "remote" if _drive_type(rest[0]) == 4 else None
        if re.match(r"VOLUME\{[0-9A-F-]{36}\}(\\|$)", rest):
            return None
        return "unsupported"
    if s.startswith(("\\\\??\\", "\\\\.\\")):
        return "device"
    if s.startswith(("\\\\WSL$\\", "\\\\WSL.LOCALHOST\\")):  # the Linux subsystem on this PC: not a network share
        return None
    if s.startswith("\\\\"):
        return "network"
    if re.match(r"[A-Z]:", s):
        return "remote" if _drive_type(s[0]) == 4 else None
    return None


def _is_network_path(p):
    """True when `_refusal` refuses `p`. See `_refusal` for the rules."""
    return _refusal(p) is not None


def convert_file(src, fmt_id, options, trash_original=False, cancel=None, notes=None):
    """`options` maps option group (audio, video, gif, image, doc, pdf) to its dict. Raises on failure.
    Warnings go to the `notes` list. The original is trashed only when the output is complete (no warning)."""
    notes = [] if notes is None else notes
    src = Path(os.path.abspath(src))  # absolute: a name starting with "-" or a "scheme:" prefix is never read as an option or URL
    refusal = _refusal(src)  # refused before is_file(), which would touch the network
    if refusal:
        what = {"network": "network (UNC) paths are not supported",
                "remote": "mapped network drive paths are not supported",
                "device": "device paths are not supported",
                "unsupported": "this kind of path is not supported"}[refusal]
        raise ValueError(f"{what}: {src.name}")
    if not src.is_file():
        raise FileNotFoundError(f"not a file: {src.name}")
    kind, fmt = output_fmt(src, fmt_id)
    opts = options[option_key(kind, fmt_id)]
    log.info("convert %s -> %s", src.name, fmt_id)
    if cancel is not None and cancel.is_set():
        raise Cancelled()
    warn = None
    if kind == "pdf":
        outs, warn = pdf_conv.convert(src, fmt, opts, cancel)
    elif kind == "image" and image_conv.still_count(src, fmt) > 1:  # multi-image HEIC: name_1, name_2, ...
        outs, warn = image_conv.convert_stills(src, fmt, opts, cancel,
                                               lambda i: unique_path(src, fmt.ext, f"_{i}"))
    else:
        dst = unique_path(src, fmt.ext)
        try:
            if kind in ("audio", "video"):
                warn = ffmpeg_conv.convert(src, dst, kind, fmt, opts, cancel)
            elif kind == "image":
                warn = image_conv.convert(src, dst, fmt, opts, cancel)
            else:
                warn = doc_conv.convert(src, dst, fmt, opts, cancel)
            if not dst.exists() or dst.stat().st_size == 0:
                raise RuntimeError("converter wrote no output")
        except BaseException:
            dst.unlink(missing_ok=True)
            raise
        outs = [dst]
    if warn:
        notes.append(f"{src.name}: {warn}")
        log.warning("%s: %s", src.name, scrub(warn, src))
    if trash_original and warn:
        notes.append(f"{src.name}: original kept")
    elif trash_original:
        try:
            send2trash(str(src))
        except Exception as e:  # the output is good: report it, do not fail the file
            log.warning("recycle bin failed for %s: %s", src.name, scrub(e, src))
            notes.append(f"{src.name}: converted, but the original could not be moved to the Recycle Bin ({e})")
    return outs
