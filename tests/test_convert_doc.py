import tempfile
import unittest
from pathlib import Path

import docx
import pymupdf

from convert_win.converter import convert_file
from convert_win.formats import DEFAULTS


class ConvertDoc(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.opts = {k: dict(v) for k, v in DEFAULTS.items()}
        self.md = self.dir / "note.md"
        self.md.write_text("# Titre\n\nUn **gras** et du texte é à ü.\n\n- un\n- deux\n", "utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_md_to_pdf_has_text(self):
        (out,) = convert_file(self.md, "pdf", self.opts)
        with pymupdf.open(out) as d:
            text = d[0].get_text()
        self.assertIn("Titre", text)
        self.assertIn("é à ü", text)

    def test_letter_page_size(self):
        self.opts["doc"]["page"] = "Letter"
        (out,) = convert_file(self.md, "pdf", self.opts)
        with pymupdf.open(out) as d:
            self.assertAlmostEqual(d[0].rect.width, 612, delta=2)

    def test_md_to_docx_keeps_heading_and_bold(self):
        (out,) = convert_file(self.md, "docx", self.opts)
        d = docx.Document(str(out))
        self.assertTrue(any(p.style.name.startswith("Heading") and "Titre" in p.text for p in d.paragraphs))
        self.assertTrue(any(r.bold and "gras" in r.text for p in d.paragraphs for r in p.runs))

    def test_docx_round_trip_to_txt_with_table(self):
        src = self.dir / "t.docx"
        d = docx.Document()
        d.add_heading("Hello", 1)
        d.add_paragraph("body text")
        t = d.add_table(rows=1, cols=2)
        t.cell(0, 0).text, t.cell(0, 1).text = "a", "b"
        d.save(str(src))
        (out,) = convert_file(src, "txt", self.opts)
        s = out.read_text("utf-8")
        for w in ("Hello", "body text", "a", "b"):
            self.assertIn(w, s)

    def test_to_rtf_odt_html_txt(self):
        for fid in ("rtf", "odt", "html", "txt"):
            with self.subTest(fid):
                (out,) = convert_file(self.md, fid, self.opts)
                self.assertGreater(out.stat().st_size, 0)
        self.assertIn("\\u233?", (self.dir / "note.rtf").read_text("ascii"))  # é escaped, file stays ASCII

    def test_cp1252_text_file(self):
        src = self.dir / "old.txt"
        src.write_bytes("café".encode("cp1252"))
        (out,) = convert_file(src, "html", self.opts)
        self.assertIn("café", out.read_text("utf-8"))

    def test_pdf_to_png_per_page_and_txt(self):
        (pdf,) = convert_file(self.md, "pdf", self.opts)
        pngs = convert_file(pdf, "png", self.opts)
        self.assertEqual(len(pngs), 1)
        self.assertGreater(pngs[0].stat().st_size, 0)
        (txt,) = convert_file(pdf, "txt", self.opts)
        self.assertIn("Titre", txt.read_text("utf-8"))


if __name__ == "__main__":
    unittest.main()
