"""Documents: TXT, MD, HTML, RTF, DOCX, ODT in; PDF, DOCX, ODT, RTF, TXT, HTML out. Qt's text engine is the hub."""
import html
import re
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


HEADING = re.compile(r"^(?:heading|titre|überschrift|título|titolo)\s*([1-6])$", re.I)  # Word style names, English and localized
IMG_TYPES = {"image/png", "image/jpeg", "image/gif", "image/bmp"}  # what Qt can draw; emf/wmf/svg are not carried over


def _docx_html(path):
    import base64

    import docx
    from docx.oxml.ns import qn
    from docx.text.paragraph import Paragraph
    from docx.text.run import Run

    d = docx.Document(str(path))
    numbering = d.part.numbering_part.element

    def run(r, p):
        rn = Run(r, p)
        s = html.escape(rn.text).replace("\n", "<br>")
        for rid in r.xpath(".//a:blip/@r:embed"):
            part = d.part.related_parts.get(rid)
            if part is not None and part.content_type in IMG_TYPES:
                cx, cy = (r.xpath(f"string(.//wp:extent/@{a})") for a in ("cx", "cy"))
                size = f' width="{int(cx) // 9525}" height="{int(cy) // 9525}"' if cx.isdigit() and cy.isdigit() else ""
                s += f'<img src="data:{part.content_type};base64,{base64.b64encode(part.blob).decode()}"{size}>'
        return ("<b>" if rn.bold else "") + ("<i>" if rn.italic else "") + s + ("</i>" if rn.italic else "") + ("</b>" if rn.bold else "")

    def inline(el, p):
        out = []
        for c in el.iterchildren():
            if c.tag == qn("w:r"):
                out.append(run(c, p))
            elif c.tag == qn("w:hyperlink"):
                rid = c.get(qn("r:id"))
                href = d.part.rels[rid].target_ref if rid in d.part.rels else None
                inner = inline(c, p)
                out.append(f'<a href="{html.escape(href, quote=True)}">{inner}</a>' if href else inner)
            elif c.tag in (qn("w:ins"), qn("w:smartTag"), qn("w:customXml"), qn("w:fldSimple")):
                out.append(inline(c, p))
            elif c.tag == qn("w:sdt"):  # content control: keep what is inside
                content = c.find(qn("w:sdtContent"))
                out.append(inline(content, p) if content is not None else "")
        return "".join(out)

    def list_kind(p, name):
        ppr = p._p.pPr
        num = ppr.numPr if ppr is not None else None
        if num is not None and num.numId is not None and num.numId.val:
            lvl = num.ilvl.val if num.ilvl is not None else 0
            fmt = numbering.xpath(
                f'w:abstractNum[@w:abstractNumId=../w:num[@w:numId="{num.numId.val}"]/w:abstractNumId/@w:val]'
                f'/w:lvl[@w:ilvl="{lvl}"]/w:numFmt/@w:val')
            return "ul" if fmt and fmt[0] == "bullet" else "ol"
        return "ul" if name.startswith("List Bullet") else "ol" if name.startswith("List Number") else None

    def para(el):  # (list tag or None, html)
        p = Paragraph(el, d)
        body = inline(el, p)
        name = p.style.name if p.style is not None else ""
        m = HEADING.match(name)
        if m:
            return None, f"<h{m[1]}>{body}</h{m[1]}>"
        kind = list_kind(p, name)
        return (kind, body) if kind else (None, f"<p>{body}</p>")

    def items(children):
        for el in children:
            if el.tag == qn("w:p"):
                yield para(el)
            elif el.tag == qn("w:tbl"):
                yield None, table(el)
            elif el.tag == qn("w:sdt"):
                content = el.find(qn("w:sdtContent"))
                if content is not None:
                    yield from items(content.iterchildren())

    def join(children):  # consecutive list paragraphs share one <ul>/<ol>
        out, cur = [], None
        for kind, h in items(children):
            if kind != cur:
                out.append(f"</{cur}>" if cur else "")
                out.append(f"<{kind}>" if kind else "")
                cur = kind
            out.append(f"<li>{h}</li>" if kind else h)
        return "".join(out) + (f"</{cur}>" if cur else "")

    def table(tbl):
        rows, open_v = [], {}  # open_v: grid column -> the cell a vertical merge started in
        for tr in tbl.findall(qn("w:tr")):
            cells, col = [], 0
            for tc in tr.findall(qn("w:tc")):
                pr = tc.find(qn("w:tcPr"))
                span = int(pr.xpath("string(w:gridSpan/@w:val)") or 1) if pr is not None else 1
                vm = pr.find(qn("w:vMerge")) if pr is not None else None
                if vm is not None and vm.get(qn("w:val")) in (None, "continue"):
                    if col in open_v:
                        open_v[col]["rows"] += 1
                else:
                    cell = {"html": join(tc.iterchildren()), "span": span, "rows": 1}
                    cells.append(cell)
                    if vm is not None:
                        open_v[col] = cell
                col += span
            rows.append(cells)
        body = "".join("<tr>" + "".join(
            "<td" + (f' colspan="{c["span"]}"' if c["span"] > 1 else "") + (f' rowspan="{c["rows"]}"' if c["rows"] > 1 else "")
            + f'>{c["html"]}</td>' for c in cells) + "</tr>" for cells in rows)
        return f'<table border="1" cellspacing="0" cellpadding="4">{body}</table>'

    return join(d.element.body.iterchildren())


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
DOCX_DROPPED = ("<w:pict", "<w:txbxContent", "<w:footnoteReference", "<w:endnoteReference", "<w:object")  # parts the DOCX reader skips


def _docx_loses_content(path):
    import zipfile

    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8", "replace")
        if any(n.lower().endswith((".emf", ".wmf", ".svg")) for n in z.namelist() if n.startswith("word/media/")):
            return True
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
        return "text boxes, footnotes, vector images or legacy objects were not carried over"
    return LOSSY_IN.get(ext)
