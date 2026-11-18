"""PDF to PNG/JPEG (one file per page) or plain text, with PyMuPDF."""
import pymupdf

from .formats import unique_path
from .process import Cancelled


def convert(src, fmt, opts, cancel=None):
    """Returns the list of files written; removes partial output on any failure."""
    outs = []
    try:
        with pymupdf.open(src) as doc:
            if fmt.id == "txt":
                text = "\n\n".join(p.get_text() for p in doc)
                if not text.strip():
                    raise RuntimeError("no text found (scanned PDF?)")
                dst = unique_path(src, "txt")
                dst.write_text(text, "utf-8")
                outs.append(dst)
            else:
                pad = len(str(doc.page_count))
                for n, page in enumerate(doc, 1):
                    if cancel is not None and cancel.is_set():
                        raise Cancelled()
                    dst = unique_path(src, fmt.ext, f" p{n:0{pad}d}")
                    outs.append(dst)
                    page.get_pixmap(dpi=opts["dpi"]).save(dst)
        if not outs or any(not o.exists() or o.stat().st_size == 0 for o in outs):
            raise RuntimeError("converter wrote no output")
    except BaseException:
        for o in outs:
            o.unlink(missing_ok=True)
        raise
    return outs
