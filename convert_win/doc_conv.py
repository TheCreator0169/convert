"""Documents: TXT, MD, HTML, RTF, DOCX, ODT in; PDF, DOCX, ODT, RTF, TXT, HTML out. Qt's text engine is the hub."""
import html
from pathlib import Path

from PySide6.QtCore import QMarginsF
from PySide6.QtGui import QPageLayout, QPageSize, QPdfWriter, QTextCursor, QTextDocument, QTextDocumentWriter
from PySide6.QtWidgets import QApplication


def _strip_local_images(doc):
    """Drop every image that is not an inline data: URI. An <img src="file:///..."> in an untrusted HTML or Markdown
    file would otherwise pull a local file into the output (Qt's image handler reads local files by itself)."""
    spans = []
    b = doc.begin()
    while b.isValid():
        it = b.begin()
        while not it.atEnd():
            f = it.fragment()
            cf = f.charFormat()
            if cf.isImageFormat() and not cf.toImageFormat().name().startswith("data:"):
                spans.append((f.position(), f.length()))
            it += 1
        b = b.next()
    for pos, length in reversed(spans):
        cur = QTextCursor(doc)
        cur.setPosition(pos)
        cur.setPosition(pos + length, QTextCursor.KeepAnchor)
        cur.removeSelectedText()


def _read(path):
    raw = Path(path).read_bytes()
    if raw.startswith(b"\xff\xfe\x00\x00"):  # UTF-32 LE BOM (a UTF-16 text starting with NUL is not realistic)
        enc = "utf-32"
    elif raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        enc = "utf-16"
    else:
        enc = None
    if enc:
        try:
            return raw.decode(enc)
        except UnicodeDecodeError as e:  # never guess: a wrong guess would end with the original in the Recycle Bin
            raise RuntimeError(f"cannot decode {enc} text") from e
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1252", "replace")


def _docx_html(path):
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    d = docx.Document(str(path))

    def para(p):
        body = "".join(
            ("<b>" if r.bold else "") + ("<i>" if r.italic else "") + html.escape(r.text).replace("\n", "<br>")
            + ("</i>" if r.italic else "") + ("</b>" if r.bold else "") for r in p.runs)
        style = p.style.name if p.style is not None else ""
        lvl = style.split()[-1] if style.startswith("Heading ") and style.split()[-1].isdigit() else None
        return f"<h{lvl}>{body}</h{lvl}>" if lvl else f"<p>{body}</p>"

    out = []
    for el in d.element.body.iterchildren():
        if el.tag.endswith("}p"):
            out.append(para(Paragraph(el, d)))
        elif el.tag.endswith("}tbl"):
            rows = "".join("<tr>" + "".join(f"<td>{html.escape(c.text)}</td>" for c in r.cells) + "</tr>"
                           for r in Table(el, d).rows)
            out.append(f'<table border="1" cellspacing="0" cellpadding="4">{rows}</table>')
    return "".join(out)


def _odt_text(path):
    from odf import teletype
    from odf.opendocument import load

    paras = []

    def walk(node):
        for c in getattr(node, "childNodes", ()):
            if getattr(c, "qname", ("", ""))[1] in ("p", "h"):
                paras.append(teletype.extractText(c))
            else:
                walk(c)

    walk(load(str(path)).text)
    return "\n".join(paras)


def load(path):
    ext = Path(path).suffix.lower().lstrip(".")
    doc = QTextDocument()
    if ext in ("md", "markdown"):
        doc.setMarkdown(_read(path))
    elif ext in ("html", "htm"):
        doc.setHtml(_read(path))
    elif ext == "rtf":
        from striprtf.striprtf import rtf_to_text
        doc.setPlainText(rtf_to_text(_read(path)))  # shortcut: RTF formatting is dropped, text only
    elif ext == "docx":
        doc.setHtml(_docx_html(path))
    elif ext == "odt":
        doc.setPlainText(_odt_text(path))  # shortcut: ODT keeps text only (no styles, tables as lines)
    else:
        doc.setPlainText(_read(path))
    _strip_local_images(doc)
    return doc


def _blocks(doc):
    b = doc.begin()
    while b.isValid():
        runs = []
        it = b.begin()
        while not it.atEnd():
            f = it.fragment()
            cf = f.charFormat()
            runs.append((f.text().replace("\u2028", "\n").replace("\ufffc", ""), cf.fontWeight() >= 600,
                         cf.fontItalic()))
            it += 1
        yield b.blockFormat().headingLevel(), runs
        b = b.next()


def _write_docx(doc, dst):
    import docx

    d = docx.Document()
    for lvl, runs in _blocks(doc):
        p = d.add_heading(level=lvl) if lvl else d.add_paragraph()
        for text, bold, italic in runs:
            r = p.add_run(text)
            if not lvl:
                r.bold, r.italic = bold or None, italic or None
    d.save(str(dst))


def _rtf_text(s):
    out = []
    for c in s:
        if c in "\\{}":
            out.append("\\" + c)
        elif c == "\n":
            out.append("\\line ")
        elif ord(c) < 128:
            out.append(c)
        else:
            b = c.encode("utf-16-le")
            for i in range(0, len(b), 2):
                n = int.from_bytes(b[i:i + 2], "little")
                out.append(f"\\u{n - 65536 if n > 32767 else n}?")
    return "".join(out)


def _write_rtf(doc, dst):
    parts = ["{\\rtf1\\ansi\\deff0{\\fonttbl{\\f0 Calibri;}}\\f0\\fs22 "]
    for lvl, runs in _blocks(doc):
        parts.append("\\pard ")
        for text, bold, italic in runs:
            t = _rtf_text(text)
            parts.append("{" + ("\\b " if bold or lvl else "") + ("\\i " if italic else "") + t + "}")
        parts.append("\\par\n")
    parts.append("}")
    Path(dst).write_text("".join(parts), "ascii")


LOSSY_IN = {"rtf": "RTF formatting was dropped (text only)", "odt": "ODT styles and tables were dropped (text only)"}
DOCX_DROPPED = ("<w:hyperlink", "<w:drawing", "<w:pict", "<w:sdt")  # parts the DOCX reader does not carry over


def _docx_loses_content(path):
    import zipfile

    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8", "replace")
    return any(tag in xml for tag in DOCX_DROPPED)


def convert(src, dst, fmt, opts):
    """Returns a warning string when the source was read as plain text only, else None."""
    QApplication.instance() or QApplication(["convert"])  # QApplication, not QGuiApplication: the window needs that type
    doc = load(src)
    if fmt.id == "pdf":
        w = QPdfWriter(str(dst))
        w.setPageSize(QPageSize(QPageSize.Letter if opts["page"] == "Letter" else QPageSize.A4))
        w.setPageMargins(QMarginsF(15, 15, 15, 15), QPageLayout.Millimeter)
        doc.print_(w)
    elif fmt.id == "docx":
        _write_docx(doc, dst)
    elif fmt.id == "odt":
        if not QTextDocumentWriter(str(dst), b"odf").write(doc):
            raise RuntimeError("could not write ODT")
    elif fmt.id == "rtf":
        _write_rtf(doc, dst)
    elif fmt.id == "html":
        Path(dst).write_text(doc.toHtml(), "utf-8")
    else:
        Path(dst).write_text(doc.toPlainText(), "utf-8")
    ext = Path(src).suffix.lower().lstrip(".")
    if ext == "docx" and _docx_loses_content(src):
        return "images, links or content controls were not carried over"
    return LOSSY_IN.get(ext)
