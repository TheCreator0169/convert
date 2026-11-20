"""Documents: TXT, MD, HTML, RTF, DOCX, ODT, DOC (text only) in; PDF, DOCX, ODT, RTF, TXT, HTML out. Qt's text engine is the hub."""
import html
import re
import zipfile
from pathlib import Path

from PySide6.QtCore import QMarginsF, QRectF, QSizeF
from PySide6.QtGui import (QAbstractTextDocumentLayout, QColor, QPageLayout, QPageSize, QPainter, QPalette, QPdfWriter,
                           QTextCursor, QTextDocument, QTextDocumentWriter, QTextListFormat, QTextTable)
from PySide6.QtWidgets import QApplication

from . import doc_binary
from .process import Cancelled

# stdlib zipfile inflates a whole member in one call otherwise (default cap 2 GB); with 16 MB each call yields at most 16 MB
zipfile.ZipExtFile.MAX_N = 1 << 24


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
MAX_UNZIPPED = 200_000_000  # bytes of all parts of one DOCX or ODT, by the declared sizes (checked before reading, not the real output)
MAX_ODT_IMAGE_HTML = 100_000_000  # characters of embedded <img> HTML per DOCX or ODT: an image used many times is paid for each use


def _check_unzipped(z):
    total = sum(i.file_size for i in z.infolist())
    if total > MAX_UNZIPPED:
        raise RuntimeError(f"file too large when unpacked: {total // 1_000_000} MB (limit {MAX_UNZIPPED // 1_000_000} MB)")


def _docx_html(path):
    import base64
    import zipfile

    import docx
    from docx.oxml import parse_xml
    from docx.oxml.ns import qn
    from docx.text.paragraph import Paragraph
    from docx.text.run import Run

    with zipfile.ZipFile(path) as z:
        _check_unzipped(z)
    d = docx.Document(str(path))
    try:
        numbering = d.part.numbering_part.element
    except (KeyError, NotImplementedError):  # no numbering part (Google Docs, simple generators): python-docx cannot create one
        numbering = None
    notes = []  # footnote and endnote texts in reading order, shown as a numbered list at the end
    uris = {}  # relationship id -> data URI, encoded once per picture however many runs use it
    image_budget = [MAX_ODT_IMAGE_HTML]  # characters of <img> HTML for the whole document, as in ODT

    def note_text(kind, nid):
        part = next((x for x in d.part.package.iter_parts() if str(x.partname) == f"/word/{kind}s.xml"), None)
        if part is None:
            return ""
        el = next((n for n in parse_xml(part.blob) if n.get(qn("w:id")) == nid), None)
        return "" if el is None else " ".join("".join(t.itertext()) for t in el.iter(qn("w:t"))).strip()

    def run(r, p):
        rn = Run(r, p)
        s = html.escape(rn.text).replace("\n", "<br>")
        for rid in r.xpath(".//a:blip/@r:embed"):
            if rid not in uris:
                part = d.part.related_parts.get(rid)
                usable = part is not None and part.content_type in IMG_TYPES
                uris[rid] = f"data:{part.content_type};base64,{base64.b64encode(part.blob).decode()}" if usable else ""
            if uris[rid]:
                cx, cy = (r.xpath(f"string(.//wp:extent/@{a})") for a in ("cx", "cy"))
                size = f' width="{int(cx) // 9525}" height="{int(cy) // 9525}"' if cx.isdigit() and cy.isdigit() else ""
                tag = f'<img src="{uris[rid]}"{size}>'
                if len(tag) > image_budget[0]:  # fail loudly, as the ODT reader does: skipping would lose pictures
                    raise RuntimeError("too many or too large images in this document")
                image_budget[0] -= len(tag)
                s += tag
        for kind in ("footnote", "endnote"):
            for nid in r.xpath(f".//w:{kind}Reference/@w:id"):
                notes.append(note_text(kind, nid))
                s += f"<sup>[{len(notes)}]</sup>"
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

    def list_kind(p, name):  # (list tag, nesting level) or (None, 0)
        ppr = p._p.pPr
        num = ppr.numPr if ppr is not None else None
        if num is not None and num.numId is not None and num.numId.val and numbering is not None:
            lvl = num.ilvl.val if num.ilvl is not None else 0
            fmt = numbering.xpath(
                f'w:abstractNum[@w:abstractNumId=../w:num[@w:numId="{num.numId.val}"]/w:abstractNumId/@w:val]'
                f'/w:lvl[@w:ilvl="{lvl}"]/w:numFmt/@w:val')
            return ("ul" if fmt and fmt[0] == "bullet" else "ol"), min(lvl, 5)
        m = re.match(r"List (Bullet|Number)(?: (\d))?$", name)
        return (("ul" if m[1] == "Bullet" else "ol"), int(m[2] or 1) - 1) if m else (None, 0)

    def para(el):  # (list tag or None, level, html)
        p = Paragraph(el, d)
        body = inline(el, p)
        name = p.style.name if p.style is not None else ""
        m = HEADING.match(name)
        if m:
            return None, 0, f"<h{m[1]}>{body}</h{m[1]}>"
        kind, lvl = list_kind(p, name)
        return (kind, lvl, body) if kind else (None, 0, f"<p>{body}</p>")

    def items(children):
        for el in children:
            if el.tag == qn("w:p"):
                yield para(el)
            elif el.tag == qn("w:tbl"):
                yield None, 0, table(el)
            elif el.tag == qn("w:sdt"):
                content = el.find(qn("w:sdtContent"))
                if content is not None:
                    yield from items(content.iterchildren())

    def join(children):  # list paragraphs share <ul>/<ol>, nested by level
        out, stack = [], []
        for kind, lvl, h in items(children):
            depth = lvl + 1 if kind else 0
            while len(stack) > depth or (kind and len(stack) == depth and stack[-1] != kind):
                out.append(f"</{stack.pop()}>")
            while len(stack) < depth:
                stack.append(kind)
                out.append(f"<{kind}>")
            out.append(f"<li>{h}</li>" if kind else h)
        return "".join(out) + "".join(f"</{t}>" for t in reversed(stack))

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

    body = join(d.element.body.iterchildren())
    if notes:
        body += "<hr>" + "".join(f"<p>[{i}] {html.escape(t)}</p>" for i, t in enumerate(notes, 1))
    return body


ODF_NS = {"text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0", "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
          "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0", "style": "urn:oasis:names:tc:opendocument:xmlns:style:1.0",
          "fo": "urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0", "draw": "urn:oasis:names:tc:opendocument:xmlns:drawing:1.0",
          "xlink": "http://www.w3.org/1999/xlink"}
IMG_EXT = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif", "bmp": "image/bmp"}
MAX_PART = 50_000_000  # bytes of one unpacked ODT part: a zip bomb must not fill the memory


def _odt_html(path):
    import zipfile

    with zipfile.ZipFile(path) as z:  # closed on return: an open handle would block the Recycle Bin and the temp cleanup
        return _odt_from_zip(z)


def _odt_from_zip(z):
    """ODT (content.xml) to HTML: headings, paragraphs, bold/italic, links, lists, tables, footnotes, embedded pictures."""
    import base64

    from lxml import etree

    _check_unzipped(z)

    def q(prefix, name):
        return f"{{{ODF_NS[prefix]}}}{name}"

    parser = etree.XMLParser(resolve_entities=False, no_network=True)

    def part(name):
        if name not in z.namelist():
            return None
        if z.getinfo(name).file_size > MAX_PART:
            raise RuntimeError(f"ODT part {name} is too large")
        return z.read(name)

    content = etree.fromstring(part("content.xml") or b"<x/>", parser)
    styles_xml = part("styles.xml")
    roots = [content] + ([etree.fromstring(styles_xml, parser)] if styles_xml else [])
    styles, lists = {}, {}
    for root in roots:
        for st in root.iter(q("style", "style")):
            tp = st.find(q("style", "text-properties"))
            weight = None if tp is None else tp.get(q("fo", "font-weight"))
            slant = None if tp is None else tp.get(q("fo", "font-style"))
            styles[st.get(q("style", "name"))] = (
                st.get(q("style", "parent-style-name")),
                None if weight is None else weight == "bold", None if slant is None else slant == "italic")
        for ls in root.iter(q("text", "list-style")):
            first = next(iter(ls), None)
            numbered = first is not None and etree.QName(first).localname == "list-level-style-number"
            lists[ls.get(q("style", "name"))] = "ol" if numbered else "ul"

    def fmt(name):  # (bold, italic), following parent styles
        bold = italic = None
        for _ in range(8):
            if name not in styles:
                break
            parent, b, i = styles[name]
            bold = b if bold is None else bold
            italic = i if italic is None else italic
            name = parent
        return bool(bold), bool(italic)

    def wrap(body, b, i):
        return ("<b>" if b else "") + ("<i>" if i else "") + body + ("</i>" if i else "") + ("</b>" if b else "")

    notes = []
    images = {}  # href -> <img> html, or "" when not usable: each picture is decoded once
    image_budget = [MAX_ODT_IMAGE_HTML]

    def inline(el):
        out = html.escape(el.text or "")
        for c in el:
            if isinstance(c.tag, str):
                tag = etree.QName(c).localname
                if tag == "span":
                    out += wrap(inline(c), *fmt(c.get(q("text", "style-name"))))
                elif tag == "a":
                    href = c.get(q("xlink", "href"))
                    out += f'<a href="{html.escape(href, quote=True)}">{inline(c)}</a>' if href else inline(c)
                elif tag == "line-break":
                    out += "<br>"
                elif tag == "tab":
                    out += "&nbsp;" * 4
                elif tag == "s":
                    out += "&nbsp;" * int(c.get(q("text", "c")) or 1)
                elif tag == "note":
                    body = c.find(q("text", "note-body"))
                    notes.append(" ".join(t.strip() for t in body.itertext() if t.strip()) if body is not None else "")
                    out += f"<sup>[{len(notes)}]</sup>"
                elif tag == "image":
                    href = c.get(q("xlink", "href")) or ""
                    if href not in images:
                        mime = IMG_EXT.get(href.rsplit(".", 1)[-1].lower())
                        data = part(href) if mime and not href.startswith(("/", "..")) else None
                        images[href] = (f'<img src="data:{mime};base64,{base64.b64encode(data).decode()}">'
                                        if data and len(data) < 20_000_000 else "")
                    tag_html = images[href]
                    if tag_html:
                        if len(tag_html) > image_budget[0]:  # fail loudly: skipping would lose pictures and still trash the original
                            raise RuntimeError("too many or too large images in this document")
                        image_budget[0] -= len(tag_html)
                        out += tag_html
                elif tag not in ("note-citation", "note-body", "annotation", "bookmark", "bookmark-start", "bookmark-end"):
                    out += inline(c)
            out += html.escape(c.tail or "")
        return out

    def blocks(parent):
        out = []
        for c in parent:
            if not isinstance(c.tag, str):
                continue
            tag = etree.QName(c).localname
            if tag == "h":
                n = min(max(int(c.get(q("text", "outline-level")) or 1), 1), 6)
                out.append(f"<h{n}>{inline(c)}</h{n}>")
            elif tag == "p":
                out.append("<p>" + wrap(inline(c), *fmt(c.get(q("text", "style-name")))) + "</p>")
            elif tag == "list":
                kind = lists.get(c.get(q("text", "style-name")), "ul")
                items = "".join(f"<li>{blocks(li)}</li>" for li in c if isinstance(li.tag, str))
                out.append(f"<{kind}>{items}</{kind}>")
            elif tag == "table":
                rows = []
                for tr in c.iter(q("table", "table-row")):
                    cells = []
                    for tc in tr:
                        if tc.tag != q("table", "table-cell"):
                            continue  # covered-table-cell: swallowed by a span
                        cs, rs = tc.get(q("table", "number-columns-spanned")), tc.get(q("table", "number-rows-spanned"))
                        attrs = (f' colspan="{cs}"' if cs and cs != "1" else "") + (f' rowspan="{rs}"' if rs and rs != "1" else "")
                        cells.append(f"<td{attrs}>{blocks(tc)}</td>")
                    rows.append("<tr>" + "".join(cells) + "</tr>")
                out.append('<table border="1" cellspacing="0" cellpadding="4">' + "".join(rows) + "</table>")
            else:  # section, table of contents ...: look inside
                out.append(blocks(c))
        return "".join(out)

    body = content.find(f"{q('office', 'body')}/{q('office', 'text')}")
    result = blocks(body) if body is not None else ""
    if notes:
        result += "<hr>" + "".join(f"<p>[{i}] {html.escape(t)}</p>" for i, t in enumerate(notes, 1))
    return result


RTF_TOKEN = re.compile(r"\\([a-zA-Z]+)(-?\d+)? ?|\\'([0-9a-fA-F]{2})|\\([^a-zA-Z0-9])|([{}])|([^\\{}\r\n]+)|[\r\n]+")
RTF_SKIP = frozenset("fonttbl colortbl stylesheet info pict header footer headerl headerr headerf footerl footerr footerf footnote "
                     "generator listtable listoverridetable revtbl rsidtbl pntext listtext xmlnstbl themedata "
                     "colorschememapping datastore latentstyles".split())
RTF_CHARS = {"emdash": "\u2014", "endash": "\u2013", "bullet": "\u2022", "lquote": "\u2018", "rquote": "\u2019",
             "ldblquote": "\u201c", "rdblquote": "\u201d", "tab": "\u00a0" * 4}


def _rtf_html(text):
    """RTF to HTML: paragraphs, bold/italic, links, tables (\\trowd \\cell \\row), unicode and code page characters.
    Headings, lists, pictures and styles are not interpreted."""
    blocks, cur, rows, cells, instr = [], [], [], [], []
    stack, st = [], {"b": False, "i": False, "skip": False, "cap": False, "uc": 1, "href": None}
    state = {"skip_n": 0, "star": False, "row": False, "cp": "cp1252"}

    def flush_table():
        if rows:
            blocks.append('<table border="1" cellspacing="0" cellpadding="4">' + "".join(
                "<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows) + "</table>")
            rows.clear()

    def end_par():
        if state["row"]:
            cur.append("<br>")
            return
        flush_table()
        blocks.append("<p>" + "".join(cur) + "</p>")
        cur.clear()

    def out(s):
        if state["skip_n"]:
            drop, state["skip_n"] = min(state["skip_n"], len(s)), max(state["skip_n"] - len(s), 0)
            s = s[drop:]
        if not s or st["skip"]:
            return
        if st["cap"]:
            instr.append(s)
            return
        s = html.escape(s)
        s = ("<b>" if st["b"] else "") + ("<i>" if st["i"] else "") + s + ("</i>" if st["i"] else "") + ("</b>" if st["b"] else "")
        cur.append(f'<a href="{html.escape(st["href"], quote=True)}">{s}</a>' if st["href"] else s)

    for m in RTF_TOKEN.finditer(text):
        word, num, hexv, sym, brace, txt = m.groups()
        if brace == "{":
            stack.append(dict(st))
            state["star"] = False
        elif brace == "}":
            if stack:
                st.clear()
                st.update(stack.pop())
        elif word:
            if state["star"]:
                state["star"] = False
                if word == "fldinst":
                    st["cap"] = True
                    instr.clear()
                else:
                    st["skip"] = True
                continue
            n = None if num is None else int(num)
            if word in RTF_SKIP:
                st["skip"] = True
            elif word == "b":
                st["b"] = n != 0
            elif word == "i":
                st["i"] = n != 0
            elif word == "plain":
                st["b"] = st["i"] = False
            elif word == "par":
                end_par()
            elif word == "line":
                cur.append("<br>")
            elif word == "uc" and n is not None:
                st["uc"] = n
            elif word == "u" and n is not None:
                out(chr(n % 65536))
                state["skip_n"] = st["uc"]
            elif word == "ansicpg" and n:
                state["cp"] = f"cp{n}"
            elif word == "fldrslt":
                hm = re.search(r'HYPERLINK\s+"([^"]+)"', "".join(instr))
                st["href"] = hm[1] if hm else None
            elif word == "trowd":
                state["row"] = True
                cells.clear()
            elif word == "cell" and state["row"]:
                cells.append("".join(cur))
                cur.clear()
            elif word == "row":
                rows.append(list(cells))
                cells.clear()
                state["row"] = False
            elif word in RTF_CHARS:
                out(RTF_CHARS[word])
        elif hexv:
            if state["skip_n"]:
                state["skip_n"] -= 1
            else:
                try:
                    out(bytes([int(hexv, 16)]).decode(state["cp"]))
                except (UnicodeDecodeError, LookupError):
                    out("?")
        elif sym:
            if sym == "*":
                state["star"] = True
            elif sym in "\r\n":
                end_par()
            elif sym == "~":
                out("\u00a0")
            elif sym in "\\{}":
                out(sym)
        elif txt:
            out(txt)
    if cur or not blocks:
        end_par()
    flush_table()
    return "".join(blocks)


def _doc_kind(path):
    """What a file named .doc really is: 'ole', 'rtf', 'docx' or 'odt'. Anything else is refused."""
    kind = doc_binary.sniff(path)
    if kind == "docx":  # every zip starts with PK: a DOCX has word/document.xml, an ODT has the ODF mimetype
        try:
            with zipfile.ZipFile(path) as z:
                names = z.namelist()
                mime = z.read("mimetype") if "mimetype" in names and z.getinfo("mimetype").file_size < 1000 else b""
        except zipfile.BadZipFile as e:
            raise ValueError("not a Word document") from e
        if "word/document.xml" in names:
            return "docx"
        if mime.strip() == b"application/vnd.oasis.opendocument.text":
            return "odt"
        raise ValueError("not a Word document")
    if kind == "other":  # HTML, WordML, plain text, or any other file with a .doc name
        raise ValueError("not a Word document")
    return kind


def load(path, cancel=None):
    ext = Path(path).suffix.lower().lstrip(".")
    doc = QTextDocument()
    if ext in ("md", "markdown"):
        doc.setMarkdown(_read(path))
    elif ext in ("html", "htm"):
        doc.setHtml(_read(path))
    elif ext == "rtf":
        doc.setHtml(_rtf_html(_read(path)))
    elif ext == "docx":
        doc.setHtml(_docx_html(path))
    elif ext == "odt":
        doc.setHtml(_odt_html(path))
    elif ext == "doc":  # legacy Word: the content decides, a renamed RTF, DOCX or ODT is read as that
        kind = _doc_kind(path)
        if kind == "rtf":
            doc.setHtml(_rtf_html(_read(path)))
        elif kind == "docx":
            doc.setHtml(_docx_html(path))
        elif kind == "odt":
            doc.setHtml(_odt_html(path))
        else:
            doc.setPlainText(doc_binary.read_text(path, cancel))
    else:
        doc.setPlainText(_read(path))
    _strip_local_images(doc)
    return doc


def _print_pages(doc, w, cancel=None):
    """Draw page by page: QTextDocument.print_ stamps a page number at the bottom of every page.
    The palette is set here: drawContents would use the desktop one (white text in Windows dark mode)."""
    rect = w.pageLayout().paintRectPixels(w.resolution())
    doc.documentLayout().setPaintDevice(w)
    doc.setPageSize(QSizeF(rect.size()))
    pal = QPalette()
    pal.setColor(QPalette.Text, QColor("black"))
    pal.setColor(QPalette.Link, QColor("#0563C1"))
    painter = QPainter(w)
    try:
        for page in range(doc.pageCount()):
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            if page:
                w.newPage()
            ctx = QAbstractTextDocumentLayout.PaintContext()
            ctx.palette = pal
            ctx.clip = QRectF(0, page * rect.height(), rect.width(), rect.height())
            painter.save()
            painter.translate(0, -page * rect.height())  # QPdfWriter already offsets by the page margins
            doc.documentLayout().draw(painter, ctx)
            painter.restore()
    finally:
        painter.end()


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


def _data_uri_bytes(name):
    """Bytes of an inline data: image, else None (images from files are stripped at load)."""
    import base64
    head, _, body = name.partition(",")
    if not head.startswith("data:") or ";base64" not in head:
        return None
    try:
        return base64.b64decode(body)
    except ValueError:
        return None


def _add_link(p, text, url, bold, italic):
    from docx.opc.constants import RELATIONSHIP_TYPE as RT
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import RGBColor
    from docx.text.run import Run

    h = OxmlElement("w:hyperlink")
    h.set(qn("r:id"), p.part.relate_to(url, RT.HYPERLINK, is_external=True))
    r = OxmlElement("w:r")
    t = OxmlElement("w:t")
    t.text = text
    t.set(qn("xml:space"), "preserve")
    r.append(t)
    h.append(r)
    p._p.append(h)
    run = Run(r, p)
    run.font.color.rgb = RGBColor(0x05, 0x63, 0xC1)
    run.underline = True
    run.bold, run.italic = bold or None, italic or None


def _write_docx(doc, dst):
    import io

    import docx
    from docx.shared import Inches

    d = docx.Document()

    def runs(p, block, heading):
        it = block.begin()
        while not it.atEnd():
            f = it.fragment()
            cf = f.charFormat()
            if cf.isImageFormat():
                data = _data_uri_bytes(cf.toImageFormat().name())
                w = cf.toImageFormat().width()
                if data:
                    p.add_run().add_picture(io.BytesIO(data), width=Inches(w / 96) if w > 0 else None)
            else:
                text = f.text().replace(" ", "\n").replace("￼", "")
                bold, italic = cf.fontWeight() >= 600, cf.fontItalic()
                if cf.isAnchor() and cf.anchorHref() and text:
                    _add_link(p, text, cf.anchorHref(), bold, italic)
                elif text:
                    r = p.add_run(text)
                    if not heading:
                        r.bold, r.italic = bold or None, italic or None
            it += 1

    def paragraph(box, block, reuse):
        lvl = block.blockFormat().headingLevel()
        lst = block.textList()
        style = None
        if lvl:
            style = f"Heading {lvl}"
        elif lst is not None:
            ordered = lst.format().style() not in (QTextListFormat.ListDisc, QTextListFormat.ListCircle, QTextListFormat.ListSquare)
            level = min(max(lst.format().indent(), 1), 3)
            style = ("List Number" if ordered else "List Bullet") + (f" {level}" if level > 1 else "")
        p = box.paragraphs[0] if reuse else box.add_paragraph()
        if style:
            p.style = style
        runs(p, block, lvl)

    def table(box, qt):
        t = box.add_table(rows=qt.rows(), cols=qt.columns())
        t.style = "Table Grid"
        for r in range(qt.rows()):
            for c in range(qt.columns()):
                cell = qt.cellAt(r, c)
                if cell.row() != r or cell.column() != c:
                    continue  # covered by a merged cell
                target = t.cell(r, c)
                if cell.rowSpan() > 1 or cell.columnSpan() > 1:
                    target = target.merge(t.cell(r + cell.rowSpan() - 1, c + cell.columnSpan() - 1))
                walk(target, cell.begin(), True)

    def walk(box, it, in_cell):
        first = in_cell  # a new cell already holds one empty paragraph: write the first block into it
        while not it.atEnd():
            b = it.currentBlock()
            if b.isValid():
                paragraph(box, b, first)
                first = False
            elif isinstance(it.currentFrame(), QTextTable):
                table(box, it.currentFrame())
            it += 1

    walk(d, doc.rootFrame().begin(), False)
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


LOSSY_IN = {"rtf": "RTF headings, lists and pictures were not carried over",
            "doc": "formatting, tables and pictures were not carried over (text only)"}
DOCX_DROPPED = ("<w:pict", "<w:txbxContent", "<w:object")  # parts the DOCX reader skips


def _odt_loses_content(path):
    import zipfile

    from lxml import etree

    with zipfile.ZipFile(path) as z:
        _check_unzipped(z)
        if "content.xml" not in z.namelist():
            return False
        root = etree.fromstring(z.read("content.xml"), etree.XMLParser(resolve_entities=False, no_network=True))
    lost = ("custom-shape", "text-box", "object", "object-ole", "line", "rect", "ellipse", "polygon", "polyline", "path", "g", "connector")
    return next(root.iter(*(f"{{{ODF_NS['draw']}}}{n}" for n in lost)), None) is not None


def _odt_drops_pictures(path):
    """True when a draw:image will not be carried over: not an embedded png/jpg/gif/bmp under 20 MB (svg, emf, a remote link...).
    Same rules as _odt_from_zip, read from the declared sizes."""
    from lxml import etree

    with zipfile.ZipFile(path) as z:
        _check_unzipped(z)
        if "content.xml" not in z.namelist():
            return False
        root = etree.fromstring(z.read("content.xml"), etree.XMLParser(resolve_entities=False, no_network=True))
        names = set(z.namelist())
        for img in root.iter(f"{{{ODF_NS['draw']}}}image"):
            href = img.get(f"{{{ODF_NS['xlink']}}}href") or ""
            ok = (href.rsplit(".", 1)[-1].lower() in IMG_EXT and not href.startswith(("/", "..")) and href in names
                  and z.getinfo(href).file_size < 20_000_000)
            if not ok:
                return True
    return False


def _docx_loses_content(path):
    import zipfile

    with zipfile.ZipFile(path) as z:
        _check_unzipped(z)
        xml = z.read("word/document.xml").decode("utf-8", "replace")
        if any(n.lower().endswith((".emf", ".wmf", ".svg")) for n in z.namelist() if n.startswith("word/media/")):
            return True
    return any(tag in xml for tag in DOCX_DROPPED)


def convert(src, dst, fmt, opts, cancel=None):
    """Returns a warning string when part of the source was not carried over, else None. Cancel is checked per page."""
    QApplication.instance() or QApplication(["convert"])  # QApplication, not QGuiApplication: the window needs that type
    doc = load(src, cancel)
    if cancel is not None and cancel.is_set():
        raise Cancelled()
    if fmt.id == "pdf":
        w = QPdfWriter(str(dst))
        w.setPageSize(QPageSize(QPageSize.Letter if opts["page"] == "Letter" else QPageSize.A4))
        w.setPageMargins(QMarginsF(15, 15, 15, 15), QPageLayout.Millimeter)
        _print_pages(doc, w, cancel)
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
    if ext == "doc":  # the warning follows the content, as load() does
        ext = {"ole": "doc", "rtf": "rtf", "docx": "docx", "odt": "odt"}[_doc_kind(src)]
    if ext == "docx" and _docx_loses_content(src):
        return "text boxes, vector images or legacy objects were not carried over"
    if ext == "odt":
        lost = [msg for hit, msg in ((_odt_loses_content(src), "drawings and text boxes may not be carried over in full"),
                                     (_odt_drops_pictures(src), "pictures were not carried over")) if hit]
        if lost:
            return "; ".join(lost)
    return LOSSY_IN.get(ext)
