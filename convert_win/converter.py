"""One entry point: convert a file to a format id, return the files written."""
import logging
import os
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


def convert_file(src, fmt_id, options, trash_original=False, cancel=None, notes=None):
    """`options` maps option group (audio, video, gif, image, doc, pdf) to its dict. Raises on failure.
    Warnings go to the `notes` list. The original is trashed only when the output is complete (no warning)."""
    notes = [] if notes is None else notes
    src = Path(os.path.abspath(src))  # absolute: a name starting with "-" or a "scheme:" prefix is never read as an option or URL
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
    if trash_original and warn:
        notes.append(f"{src.name}: original kept")
    elif trash_original:
        try:
            send2trash(str(src))
        except Exception as e:  # the output is good: report it, do not fail the file
            log.warning("recycle bin failed for %s: %s", src.name, scrub(e, src))
            notes.append(f"{src.name}: converted, but the original could not be moved to the Recycle Bin ({e})")
    return outs
