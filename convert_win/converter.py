"""One entry point: convert a file to a format id, return the files written."""
import logging
from pathlib import Path

from send2trash import send2trash

from . import doc_conv, ffmpeg_conv, image_conv, pdf_conv
from .formats import option_key, output_fmt, unique_path

log = logging.getLogger("convert")


def convert_file(src, fmt_id, options, trash_original=False, cancel=None):
    """`options` maps option group (audio, video, gif, image, doc, pdf) to its dict. Raises on failure."""
    src = Path(src)
    kind, fmt = output_fmt(src, fmt_id)
    opts = options[option_key(kind, fmt_id)]
    log.info("convert %s -> %s", src, fmt_id)
    if kind == "pdf":
        outs = pdf_conv.convert(src, fmt, opts)
    else:
        dst = unique_path(src, fmt.ext)
        try:
            if kind in ("audio", "video"):
                ffmpeg_conv.convert(src, dst, kind, fmt, opts, cancel)
            elif kind == "image":
                image_conv.convert(src, dst, fmt, opts)
            else:
                doc_conv.convert(src, dst, fmt, opts)
            if not dst.exists() or dst.stat().st_size == 0:
                raise RuntimeError("converter wrote no output")
        except BaseException:
            dst.unlink(missing_ok=True)
            raise
        outs = [dst]
    if trash_original:
        send2trash(str(src))
    return outs
