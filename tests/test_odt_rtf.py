"""v0.1.4: ODT and RTF are read with structure (bold, italic, links, lists, tables), not as bare text."""
import tempfile
import unittest
import unittest.mock
import zipfile
from pathlib import Path

from convert_win import doc_conv
from convert_win.converter import convert_file
from convert_win.formats import DEFAULTS

TEXT = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
TABLE = "urn:oasis:names:tc:opendocument:xmlns:table:1.0"
OFFICE = "urn:oasis:names:tc:opendocument:xmlns:office:1.0"
STYLE = "urn:oasis:names:tc:opendocument:xmlns:style:1.0"
FO = "urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0"
XLINK = "http://www.w3.org/1999/xlink"


def make_odt(path, body, styles=""):
    xml = (f'<?xml version="1.0"?><office:document-content xmlns:office="{OFFICE}" xmlns:text="{TEXT}" xmlns:table="{TABLE}" '
           f'xmlns:style="{STYLE}" xmlns:fo="{FO}" xmlns:xlink="{XLINK}"><office:automatic-styles>{styles}</office:automatic-styles>'
           f"<office:body><office:text>{body}</office:text></office:body></office:document-content>")
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/vnd.oasis.opendocument.text")
        z.writestr("content.xml", xml)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.opts = {k: dict(v) for k, v in DEFAULTS.items()}
        self.addCleanup(self.tmp.cleanup)


class Odt(Base):
    def test_styles_links_lists_tables_footnotes(self):
        make_odt(self.dir / "a.odt", (
            '<text:h text:outline-level="2">Titre</text:h>'
            '<text:p>un <text:span text:style-name="B">gras</text:span> et <text:span text:style-name="I">italique</text:span> '
            f'<text:a xlink:href="https://example.com">lien</text:a><text:note><text:note-citation>1</text:note-citation>'
            "<text:note-body><text:p>la source</text:p></text:note-body></text:note></text:p>"
            '<text:list text:style-name="L"><text:list-item><text:p>point</text:p></text:list-item></text:list>'
            '<table:table><table:table-row><table:table-cell table:number-columns-spanned="2"><text:p>large</text:p></table:table-cell>'
            "<table:covered-table-cell/></table:table-row><table:table-row><table:table-cell><text:p>a</text:p></table:table-cell>"
            "<table:table-cell><text:p>b</text:p></table:table-cell></table:table-row></table:table>"),
            '<style:style style:name="B" style:family="text"><style:text-properties fo:font-weight="bold"/></style:style>'
            '<style:style style:name="I" style:family="text"><style:text-properties fo:font-style="italic"/></style:style>'
            '<text:list-style style:name="L"><text:list-level-style-number text:level="1"/></text:list-style>')
        out = doc_conv._odt_html(self.dir / "a.odt")
        for piece in ("<h2>Titre</h2>", "<b>gras</b>", "<i>italique</i>", '<a href="https://example.com">lien</a>', "<sup>[1]</sup>",
                      "<ol><li><p>point</p></li></ol>", 'colspan="2"', "[1] la source"):
            self.assertIn(piece, out)
        self.assertEqual(out.count("<td"), 3)  # the covered cell adds none

    def test_odt_to_docx_keeps_table_and_bold(self):
        import docx

        make_odt(self.dir / "b.odt", '<text:p><text:span text:style-name="B">gras</text:span></text:p>'
                 "<table:table><table:table-row><table:table-cell><text:p>x</text:p></table:table-cell></table:table-row></table:table>",
                 '<style:style style:name="B" style:family="text"><style:text-properties fo:font-weight="bold"/></style:style>')
        notes = []
        (out,) = convert_file(self.dir / "b.odt", "docx", self.opts, notes=notes)
        d = docx.Document(str(out))
        self.assertEqual(notes, [])
        self.assertEqual(d.tables[0].cell(0, 0).text, "x")
        self.assertTrue(any(r.bold and "gras" in r.text for p in d.paragraphs for r in p.runs))

    def test_round_trip_through_qt_odt_writer(self):
        src = self.dir / "w.html"
        src.write_text("<h1>T</h1><p>a <b>b</b></p><ul><li>l1</li></ul><table border='1'><tr><td>c</td></tr></table>", "utf-8")
        (odt,) = convert_file(src, "odt", self.opts)
        out = doc_conv._odt_html(odt)
        self.assertIn("<b>b</b>", out)  # Qt's writer turns headings into bold paragraphs and nests the table: only text is checked
        for word in ("T", "l1", "c"):
            self.assertIn(word, out)

    def test_oversized_part_is_refused(self):
        make_odt(self.dir / "big.odt", "<text:p>x</text:p>")
        with unittest.mock.patch.object(doc_conv, "MAX_PART", 10):
            with self.assertRaisesRegex(RuntimeError, "too large"):
                doc_conv._odt_html(self.dir / "big.odt")

    def test_entity_is_not_expanded(self):
        make_odt(self.dir / "x.odt", "<text:p>safe</text:p>")
        with zipfile.ZipFile(self.dir / "x.odt", "a") as z:
            z.writestr("styles.xml", '<?xml version="1.0"?><!DOCTYPE a [<!ENTITY e SYSTEM "file:///C:/Windows/win.ini">]>'
                       f'<office:document-styles xmlns:office="{OFFICE}"><x>&e;</x></office:document-styles>')
        self.assertNotIn("[fonts]", doc_conv._odt_html(self.dir / "x.odt"))


class Rtf(Base):
    def html(self, rtf):
        return doc_conv._rtf_html(rtf)

    def test_bold_italic_and_paragraphs(self):
        out = self.html(r"{\rtf1\ansi{\fonttbl{\f0 Arial;}}\pard plain {\b gras}\b0  et {\i it}\par second\par}")
        self.assertIn("<b>gras</b>", out)
        self.assertIn("<i>it</i>", out)
        self.assertIn("<p>second</p>", out)
        self.assertNotIn("Arial", out)  # font table is not text

    def test_unicode_hex_and_escapes(self):
        out = self.html(r"{\rtf1\ansi\ansicpg1252\uc1 caf\u233?  \'e9t\'e9 \{x\} \u8364?}")
        self.assertIn("caf\u00e9", out)
        self.assertIn("\u00e9t\u00e9", out)
        self.assertIn("{x}", out)
        self.assertIn("\u20ac", out)
        self.assertNotIn("?", out)

    def test_hyperlink_field(self):
        out = self.html(r'{\rtf1{\field{\*\fldinst HYPERLINK "https://example.com"}{\fldrslt {\ul site}}}\par}')
        self.assertIn('<a href="https://example.com">site</a>', out)
        self.assertNotIn("HYPERLINK", out.replace('href="https://example.com"', ""))

    def test_table_rows_and_cells(self):
        out = self.html(r"{\rtf1\trowd\cellx1000\cellx2000 \intbl a\cell b\cell\row\trowd\cellx1000 \intbl c\cell\row after\par}")
        self.assertEqual(out.count("<tr>"), 2)
        self.assertIn("<td>a</td><td>b</td>", out)
        self.assertIn("<p>after</p>", out)

    def test_unknown_star_group_and_picture_are_skipped(self):
        out = self.html(r"{\rtf1 keep{\*\generator Word 16}{\pict\wmetafile8 0102aabb}\par}")
        self.assertEqual(out, "<p>keep</p>")

    def test_rtf_file_converts_with_a_warning_and_keeps_formatting(self):
        src = self.dir / "r.rtf"
        src.write_bytes(rb"{\rtf1\ansi {\b gras} texte\par}")
        notes = []
        (out,) = convert_file(src, "html", self.opts, trash_original=True, notes=notes)
        self.assertIn("font-weight", out.read_text("utf-8"))
        self.assertTrue(any("not carried over" in n for n in notes))


if __name__ == "__main__":
    unittest.main()
