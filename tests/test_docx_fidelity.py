"""v0.1.3: the DOCX reader keeps links, lists, pictures, tables (nested, merged), content controls, localized headings."""
import io
import tempfile
import unittest
from pathlib import Path

import docx
import pymupdf
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.shared import Cm
from PIL import Image

from convert_win import doc_conv
from convert_win.converter import convert_file
from convert_win.formats import DEFAULTS


def png():
    b = io.BytesIO()
    Image.new("RGB", (40, 40), "red").save(b, "PNG")
    return io.BytesIO(b.getvalue())


class Docx(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.opts = {k: {**v} for k, v in DEFAULTS.items()}
        self.addCleanup(self.tmp.cleanup)

    def html(self, d):
        src = self.dir / "t.docx"
        d.save(src)
        return doc_conv._docx_html(src)

    def test_hyperlink_text_and_target_kept(self):
        d = docx.Document()
        p = d.add_paragraph("see ")
        h = OxmlElement("w:hyperlink")
        h.set(qn("r:id"), d.part.relate_to("https://example.com/x", RT.HYPERLINK, is_external=True))
        r = OxmlElement("w:r")
        t = OxmlElement("w:t")
        t.text = "the site"
        r.append(t)
        h.append(r)
        p._p.append(h)
        out = self.html(d)
        self.assertIn('<a href="https://example.com/x">the site</a>', out)

    def test_content_control_text_kept(self):
        d = docx.Document()
        sdt = parse_xml(f'<w:sdt {nsdecls("w")}><w:sdtContent><w:p><w:r><w:t>inside control</w:t></w:r></w:p></w:sdtContent></w:sdt>')
        d.element.body.insert(0, sdt)
        self.assertIn("inside control", self.html(d))

    def test_picture_embedded_as_data_uri_and_survives_pdf(self):
        d = docx.Document()
        d.add_picture(png(), width=Cm(3))
        src = self.dir / "pic.docx"
        d.save(src)
        self.assertIn('src="data:image/png;base64,', doc_conv._docx_html(src))
        (out,) = convert_file(src, "pdf", self.opts)
        with pymupdf.open(out) as pdf:
            self.assertEqual(sum(len(p.get_images()) for p in pdf), 1)

    def test_french_heading_style_becomes_heading(self):
        d = docx.Document()
        d.styles.add_style("Titre 2", 1)
        d.add_paragraph("Mon titre", style="Titre 2")
        self.assertIn("<h2>Mon titre</h2>", self.html(d))

    def test_lists_become_ul_and_ol(self):
        d = docx.Document()
        d.add_paragraph("a", style="List Bullet")
        d.add_paragraph("b", style="List Bullet")
        d.add_paragraph("one", style="List Number")
        out = self.html(d)
        self.assertIn("<ul><li>a</li><li>b</li></ul>", out)
        self.assertIn("<ol><li>one</li></ol>", out)

    def test_nested_and_merged_table_cells(self):
        d = docx.Document()
        t = d.add_table(rows=2, cols=2)
        t.cell(0, 0).merge(t.cell(0, 1)).text = "wide"
        inner = t.cell(1, 0).add_table(rows=1, cols=1)
        inner.cell(0, 0).text = "nested"
        t.cell(1, 1).text = "right"
        out = self.html(d)
        self.assertIn('colspan="2"', out)
        self.assertEqual(out.count("wide"), 1)
        self.assertIn("nested", out)
        self.assertEqual(out.count("<table"), 2)

    def test_vertical_merge_gives_rowspan(self):
        d = docx.Document()
        t = d.add_table(rows=2, cols=1)
        t.cell(0, 0).merge(t.cell(1, 0)).text = "tall"
        out = self.html(d)
        self.assertIn('rowspan="2"', out)
        self.assertEqual(out.count("tall"), 1)

    def test_french_document_converts_to_pdf_with_every_element(self):  # roadmap "done when"
        d = docx.Document()
        d.styles.add_style("Titre 1", 1)
        d.add_paragraph("Rapport", style="Titre 1")
        p = d.add_paragraph("Voir ")
        h = OxmlElement("w:hyperlink")
        h.set(qn("r:id"), d.part.relate_to("https://example.com", RT.HYPERLINK, is_external=True))
        r = OxmlElement("w:r")
        t = OxmlElement("w:t")
        t.text = "le lien"
        r.append(t)
        h.append(r)
        p._p.append(h)
        d.add_paragraph("premier point", style="List Bullet")
        d.add_picture(png(), width=Cm(3))
        d.add_table(rows=1, cols=2).cell(0, 1).text = "cellule"
        src = self.dir / "fr.docx"
        d.save(src)
        notes = []
        (out,) = convert_file(src, "pdf", self.opts, notes=notes)
        self.assertEqual(notes, [])
        with pymupdf.open(out) as pdf:
            text = "".join(pg.get_text() for pg in pdf)
            self.assertEqual(sum(len(pg.get_images()) for pg in pdf), 1)
            self.assertEqual(sum(len(pg.get_links()) for pg in pdf), 1)
        for word in ("Rapport", "le lien", "premier point", "cellule"):
            self.assertIn(word, text)


if __name__ == "__main__":
    unittest.main()
