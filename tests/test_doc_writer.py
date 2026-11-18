"""v0.1.4: DOCX output keeps lists, tables, links and pictures; PDF output has no Qt page number."""
import base64
import io
import tempfile
import unittest
from pathlib import Path

import docx
import pymupdf
from PIL import Image

from convert_win.converter import convert_file
from convert_win.formats import DEFAULTS


def png_b64():
    b = io.BytesIO()
    Image.new("RGB", (40, 40), "red").save(b, "PNG")
    return base64.b64encode(b.getvalue()).decode()


class Writer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.opts = {k: dict(v) for k, v in DEFAULTS.items()}
        self.addCleanup(self.tmp.cleanup)

    def to_docx(self, name, text):
        src = self.dir / name
        src.write_text(text, "utf-8")
        (out,) = convert_file(src, "docx", self.opts)
        return docx.Document(str(out))

    def test_html_list_table_link_picture_reach_the_docx(self):
        d = self.to_docx("a.html", f'<h1>Titre</h1><p>see <a href="https://example.com/x">the site</a></p>'
                         f'<ul><li>one</li><li>two</li></ul><ol><li>first</li></ol>'
                         f'<table border="1"><tr><td>a</td><td>b</td></tr><tr><td colspan="2">wide</td></tr></table>'
                         f'<img src="data:image/png;base64,{png_b64()}" width="40" height="40">')
        styles = [p.style.name for p in d.paragraphs]
        self.assertIn("Heading 1", styles)
        self.assertEqual(styles.count("List Bullet"), 2)
        self.assertIn("List Number", styles)
        self.assertEqual(len(d.tables), 1)
        self.assertEqual(d.tables[0].cell(0, 1).text, "b")
        self.assertEqual(d.tables[0].cell(1, 0).text, "wide")
        self.assertEqual(d.tables[0].cell(1, 0)._tc, d.tables[0].cell(1, 1)._tc)  # merged
        self.assertEqual(len(d.inline_shapes), 1)
        self.assertEqual(len(d.element.xpath("//w:hyperlink")), 1)
        rel = [r for r in d.part.rels.values() if r.is_external]
        self.assertEqual(rel[0].target_ref, "https://example.com/x")

    def test_docx_round_trip_keeps_everything(self):
        d = self.to_docx("b.html", '<h2>T</h2><ul><li>x</li></ul><table><tr><td>c1</td><td>c2</td></tr></table>'
                         f'<p><a href="https://example.com">link</a></p><img src="data:image/png;base64,{png_b64()}">')
        first = self.dir / "first.docx"
        d.save(first)
        (pdf,) = convert_file(first, "pdf", self.opts)
        with pymupdf.open(pdf) as p:
            text = "".join(pg.get_text() for pg in p)
            self.assertEqual(sum(len(pg.get_images()) for pg in p), 1)
            self.assertEqual(sum(len(pg.get_links()) for pg in p), 1)
        for w in ("T", "x", "c1", "c2", "link"):
            self.assertIn(w, text)

    def test_nested_table_and_bold_italic(self):
        d = self.to_docx("c.html", '<table><tr><td><b>bold</b> <i>it</i><table><tr><td>inner</td></tr></table></td></tr></table>')
        outer = d.tables[0].cell(0, 0)
        self.assertEqual(len(outer.tables), 1)
        self.assertEqual(outer.tables[0].cell(0, 0).text, "inner")
        runs = [r for p in outer.paragraphs for r in p.runs]
        self.assertTrue(any(r.bold and "bold" in r.text for r in runs))
        self.assertTrue(any(r.italic and "it" in r.text for r in runs))


class PdfPageNumber(unittest.TestCase):
    def test_no_page_number_and_text_inside_margins(self):
        with tempfile.TemporaryDirectory() as t:
            src = Path(t) / "long.txt"
            src.write_text("\n".join(f"Line number {i} of the test document" for i in range(120)), "utf-8")
            (out,) = convert_file(src, "pdf", {k: dict(v) for k, v in DEFAULTS.items()})
            with pymupdf.open(out) as p:
                self.assertGreater(len(p), 1)
                for pg in p:
                    lines = [ln for ln in pg.get_text().split("\n") if ln.strip()]
                    self.assertTrue(all(ln.startswith("Line number") for ln in lines), lines[-2:])
                    words = pg.get_text("words")
                    self.assertGreater(min(w[0] for w in words), 40)
                    self.assertLess(max(w[3] for w in words), pg.rect.height - 40)
                self.assertIn("Line number 119", p[len(p) - 1].get_text())
                px = p[0].get_pixmap(dpi=40, colorspace=pymupdf.csGRAY)
                dark = sum(1 for v in px.samples if v < 100)
                self.assertGreater(dark, 100)  # text is drawn in black: in Windows dark mode it was once white (invisible)


if __name__ == "__main__":
    unittest.main()
