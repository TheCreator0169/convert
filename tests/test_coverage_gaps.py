"""v0.1.7: inputs and failure paths the older suites did not reach (every image input, text encodings, PDF pages, corrupt files, the CLI)."""
import contextlib
import gc
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pymupdf
from PIL import Image

from convert_win import main as cmain
from convert_win.converter import convert_file, describe
from convert_win.formats import DEFAULTS
from convert_win.process import find_tool, run

FFMPEG = find_tool("ffmpeg")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.opts = {k: dict(v) for k, v in DEFAULTS.items()}
        self.addCleanup(self.tmp.cleanup)

    def pdf(self, pages=3, name="in.pdf", text=True):
        doc = pymupdf.open()
        for i in range(pages):
            page = doc.new_page()
            if text:
                page.insert_text((72, 72), f"page {i + 1}")
        doc.save(self.dir / name)
        doc.close()
        return self.dir / name


class ImageInputs(Base):
    def test_every_input_type_converts_to_png(self):
        base = Image.new("RGB", (40, 30), (10, 120, 200))
        for ext in ("jpg", "tiff", "gif", "bmp", "webp", "heic", "avif"):
            with self.subTest(ext):
                src = self.dir / f"in.{ext}"
                base.save(src)
                (out,) = convert_file(src, "png", self.opts)
                with Image.open(out) as im:
                    self.assertEqual(im.size, (40, 30))

    def test_palette_and_cmyk_and_grayscale_inputs(self):
        for mode, ext in (("P", "png"), ("CMYK", "jpg"), ("CMYK", "tiff"), ("L", "png"), ("LA", "png"), ("I;16", "png")):
            with self.subTest(mode=mode, ext=ext):
                src = self.dir / f"{mode.replace(';', '')}.{ext}"
                Image.new(mode, (16, 16)).save(src)
                for fid in ("jpg", "webp"):
                    (out,) = convert_file(src, fid, self.opts)
                    self.assertGreater(out.stat().st_size, 0)


class TextInputs(Base):
    def test_utf16_and_utf8_bom_text_keep_their_characters(self):
        for name, data in (("u16.txt", "café €".encode("utf-16")), ("u8.txt", "café €".encode("utf-8-sig"))):
            with self.subTest(name):
                src = self.dir / name
                src.write_bytes(data)
                (out,) = convert_file(src, "html", self.opts)
                self.assertIn("café €", out.read_text("utf-8"))

    def test_markdown_extension_and_html_to_text(self):
        md = self.dir / "n.markdown"
        md.write_text("# Titre\n\ntexte **fort**", "utf-8")
        (out,) = convert_file(md, "txt", self.opts)
        self.assertIn("Titre", out.read_text("utf-8"))
        html = self.dir / "h.html"
        html.write_text("<h1>Salut</h1><p>le monde</p>", "utf-8")
        (out,) = convert_file(html, "txt", self.opts)
        self.assertIn("le monde", out.read_text("utf-8"))


class PdfInputs(Base):
    def test_one_file_per_page_with_padded_numbers(self):
        outs = convert_file(self.pdf(pages=12), "png", self.opts)
        self.assertEqual(len(outs), 12)
        self.assertEqual(outs[0].name, "in p01.png")
        self.assertEqual(outs[-1].name, "in p12.png")

    def test_jpeg_pages_and_dpi_change_the_size(self):
        src = self.pdf(pages=1)
        self.opts["pdf"]["dpi"] = 72
        (small,) = convert_file(src, "jpg", self.opts)
        self.opts["pdf"]["dpi"] = 144
        (big,) = convert_file(src, "jpg", self.opts)
        with Image.open(small) as a, Image.open(big) as b:
            self.assertEqual(a.format, "JPEG")
            self.assertEqual(b.width, a.width * 2)

    def test_text_of_a_blank_pdf_is_an_error_and_leaves_nothing(self):
        src = self.pdf(pages=2, text=False)
        with self.assertRaisesRegex(RuntimeError, "no text found"):
            convert_file(src, "txt", self.opts)
        self.assertEqual(list(self.dir.glob("*.txt")), [])

    def test_encrypted_pdf_fails_cleanly(self):
        doc = pymupdf.open()
        doc.new_page()
        doc.save(self.dir / "locked.pdf", encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="o", user_pw="u")
        doc.close()
        with self.assertRaises(Exception):
            convert_file(self.dir / "locked.pdf", "png", self.opts, trash_original=True)
        self.assertEqual(list(self.dir.glob("locked p*.png")), [])
        self.assertTrue((self.dir / "locked.pdf").exists())


class CorruptFiles(Base):
    def test_each_family_fails_without_output_and_keeps_the_original(self):
        cases = (("bad.pdf", "png"), ("bad.docx", "pdf"), ("bad.odt", "pdf"), ("bad.gif", "png"), ("bad.heic", "png"))
        if FFMPEG:
            cases += (("bad.mp3", "wav"), ("bad.mp4", "mp3"), ("bad.mkv", "mp4"))
        for name, fid in cases:
            with self.subTest(name):
                src = self.dir / name
                gc.collect()  # a failed PyMuPDF open keeps its file handle until the exception is collected
                for old in self.dir.iterdir():  # one family at a time
                    old.unlink()
                src.write_bytes(b"this is not a real file" * 20)
                with mock.patch("convert_win.converter.send2trash") as trash:
                    with self.assertRaises(Exception) as cm:
                        convert_file(src, fid, self.opts, trash_original=True)
                    trash.assert_not_called()
                shown = describe(cm.exception)
                del cm
                self.assertTrue(shown)
                self.assertTrue(src.exists())
                self.assertEqual([p.name for p in self.dir.iterdir() if p.name != name], [])
        gc.collect()

    @unittest.skipUnless(FFMPEG, "ffmpeg not installed")
    def test_silent_video_to_audio_is_an_error_not_an_empty_file(self):
        src = self.dir / "mute.mp4"
        rc, _, err = run([FFMPEG, "-v", "error", "-f", "lavfi", "-i", "testsrc=s=64x64:d=1", "-c:v", "libx264", "-pix_fmt",
                          "yuv420p", str(src)])
        self.assertEqual(rc, 0, err)
        with self.assertRaises(RuntimeError):
            convert_file(src, "mp3", self.opts)
        self.assertEqual(list(self.dir.glob("mute*.mp3")), [])


class Cli(Base):
    def call(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cmain.cli(argv)
        return code, out.getvalue(), err.getvalue()

    def setUp(self):
        super().setUp()
        p = mock.patch("convert_win.settings.load", return_value={"options": self.opts, "trash_originals": False})
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch("convert_win.settings.setup_logging")
        p.start()
        self.addCleanup(p.stop)

    def test_listing_names_every_family_and_exits_zero(self):
        code, out, _ = self.call([])
        self.assertEqual(code, 0)
        for fam in ("audio:", "video:", "image:", "doc:", "pdf:"):
            self.assertIn(fam, out)

    def test_success_prints_the_output_and_exits_zero(self):
        src = self.dir / "a.png"
        Image.new("RGB", (8, 8)).save(src)
        code, out, _ = self.call(["webp", str(src)])
        self.assertEqual(code, 0)
        self.assertIn("a.webp", out)

    def test_unknown_format_and_missing_file_exit_one_and_keep_going(self):
        src = self.dir / "a.png"
        Image.new("RGB", (8, 8)).save(src)
        code, out, err = self.call(["nope", str(src)])
        self.assertEqual(code, 1)
        self.assertIn("nope", err)
        code, out, err = self.call(["webp", str(self.dir / "missing.png"), str(src)])
        self.assertEqual(code, 1)
        self.assertIn("a.webp", out)  # the second file was still converted

    def test_menu_flags_dispatch_to_shell_integration(self):
        with mock.patch("convert_win.shell_integration.install") as i, mock.patch("convert_win.shell_integration.uninstall") as u, \
                mock.patch("convert_win.settings.setup_logging"):
            self.assertEqual(cmain.main(["--install-menu"]), 0)
            self.assertEqual(cmain.main(["--uninstall-menu"]), 0)
        i.assert_called_once()
        u.assert_called_once()


if __name__ == "__main__":
    unittest.main()
