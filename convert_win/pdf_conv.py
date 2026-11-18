"""PDF to PNG/JPEG (one file per page) or plain text, with PyMuPDF."""
import pymupdf

from .formats import unique_path
from .process import Cancelled


MAX_PAGES = 500
MAX_PIXELS = 100_000_000  # per page: about 400 MB of RGB


def convert(src, fmt, opts, cancel=None):
    """Returns (files written, warning or None); removes partial output on any failure."""
    outs, warn = [], None
    try:
        with pymupdf.open(src) as doc:
            if fmt.id == "txt":
                texts = []
                for page in doc:
                    if cancel is not None and cancel.is_set():
                        raise Cancelled()
                    texts.append(page.get_text())
                empty = sum(not t.strip() for t in texts)
                if empty == len(texts):
                    raise RuntimeError("no text found (scanned PDF?)")
                if empty:
                    warn = f"{empty} of {len(texts)} page(s) had no text (scanned or blank)"
                dst = unique_path(src, "txt")
                outs.append(dst)
                dst.write_text("\n\n".join(texts), "utf-8")
            else:
                if doc.page_count > MAX_PAGES:
                    raise RuntimeError(f"{doc.page_count} pages: more than the {MAX_PAGES} page limit for images")
                pad = len(str(doc.page_count))
                scale = opts["dpi"] / 72
                for n, page in enumerate(doc, 1):
                    if cancel is not None and cancel.is_set():
                        raise Cancelled()
                    if page.rect.width * page.rect.height * scale * scale > MAX_PIXELS:
                        raise RuntimeError(f"page {n} is too large at {opts['dpi']} dpi: lower the resolution")
                    dst = unique_path(src, fmt.ext, f" p{n:0{pad}d}")
                    outs.append(dst)
                    page.get_pixmap(dpi=opts["dpi"]).save(dst)
        if not outs or any(not o.exists() or o.stat().st_size == 0 for o in outs):
            raise RuntimeError("converter wrote no output")
    except BaseException:
        for o in outs:
            o.unlink(missing_ok=True)
        raise
    return outs, warn
