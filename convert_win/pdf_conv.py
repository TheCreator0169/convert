"""PDF to PNG/JPEG (one file per page) or plain text, with PyMuPDF."""
from pathlib import Path

import pymupdf

from .formats import unique_path


def convert(src, fmt, opts):
    """Returns the list of files written."""
    outs = []
    with pymupdf.open(src) as doc:
        if fmt.id == "txt":
            dst = unique_path(src, "txt")
            dst.write_text("\n\n".join(p.get_text() for p in doc), "utf-8")
            return [dst]
        pad = len(str(doc.page_count))
        for n, page in enumerate(doc, 1):
            dst = unique_path(src, fmt.ext, f" p{n:0{pad}d}")
            page.get_pixmap(dpi=opts["dpi"]).save(dst)
            outs.append(dst)
    return outs
