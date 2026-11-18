"""v0.1.2 security hardening."""
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import pymupdf
from PIL import Image

from convert_win import ffmpeg_conv, pdf_conv, process, settings
from convert_win.converter import convert_file
from convert_win.formats import DEFAULTS, output_fmt, unique_path


class Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.opts = {k: {**v} for k, v in DEFAULTS.items()}
        self.addCleanup(self.tmp.cleanup)


class ToolLookup(Tmp):
    def test_planted_exe_in_current_folder_is_ignored(self):  # H1
        (self.dir / "ffmpeg.exe").write_bytes(b"MZ")
        elsewhere = self.dir / "empty"
        elsewhere.mkdir()
        old = os.getcwd()
        os.chdir(self.dir)
        self.addCleanup(os.chdir, old)
        with mock.patch.dict(os.environ, {"PATH": os.pathsep.join(["", ".", str(elsewhere)])}):
            os.environ.pop("NoDefaultCurrentDirectoryInExePath", None)  # absent on a normal Explorer launch
            self.assertIsNone(process.find_tool("ffmpeg"))

    def test_exe_on_an_absolute_path_entry_is_found(self):  # H1
        (self.dir / "ffmpeg.exe").write_bytes(b"MZ")
        with mock.patch.dict(os.environ, {"PATH": str(self.dir)}):
            self.assertEqual(Path(process.find_tool("ffmpeg")).name.lower(), "ffmpeg.exe")


class PathsAndUrls(Tmp):
    def test_ffmpeg_args_whitelist_files_only(self):  # H3
        kind, fmt = output_fmt(Path("a.wav"), "mp3")
        a = ffmpeg_conv.build_args("ffmpeg", Path("a.wav"), Path("a.mp3"), kind, fmt, DEFAULTS["audio"])
        self.assertEqual(a[a.index("-protocol_whitelist") + 1], "file")
        self.assertLess(a.index("-protocol_whitelist"), a.index("-i"))

    def test_missing_or_url_like_input_is_refused(self):  # H3
        for name in ("http://example.com/a.mp3", "nope.png", str(self.dir)):
            with self.assertRaises(FileNotFoundError, msg=name):
                convert_file(name, "jpg", self.opts)

    def test_name_starting_with_dash_works_from_a_relative_path(self):  # H3
        Image.new("RGB", (4, 4)).save(self.dir / "-pic.png")
        old = os.getcwd()
        os.chdir(self.dir)
        self.addCleanup(os.chdir, old)
        (out,) = convert_file("-pic.png", "jpg", self.opts)
        self.assertTrue(out.exists())


class UniquePath(Tmp):
    def test_name_is_reserved(self):  # H4
        src = self.dir / "a.png"
        first = unique_path(src, "jpg")
        second = unique_path(src, "jpg")
        self.assertTrue(first.exists())
        self.assertNotEqual(first, second)
        self.assertEqual(second.name, "a 2.jpg")

    def test_dangling_link_is_not_followed(self):  # H4
        target = self.dir / "gone.txt"
        link = self.dir / "a.jpg"
        try:
            os.symlink(target, link)
        except OSError:
            self.skipTest("symlinks need a privilege on this machine")
        self.assertEqual(unique_path(self.dir / "a.png", "jpg").name, "a 2.jpg")
        self.assertFalse(target.exists())


class PdfCaps(Tmp):
    def _pdf(self, pages, size=(100, 100)):
        d = pymupdf.open()
        for _ in range(pages):
            d.new_page(width=size[0], height=size[1])
        path = self.dir / "x.pdf"
        d.save(path)
        d.close()
        return path

    def test_huge_page_is_refused(self):  # H5
        pdf = self._pdf(1, (14400, 14400))
        self.opts["pdf"]["dpi"] = 300
        with self.assertRaisesRegex(RuntimeError, "too large"):
            convert_file(pdf, "png", self.opts)
        self.assertEqual(list(self.dir.glob("x p*.png")), [])

    def test_too_many_pages_is_refused(self):  # H5
        pdf = self._pdf(pdf_conv.MAX_PAGES + 1)
        with self.assertRaisesRegex(RuntimeError, "page limit"):
            convert_file(pdf, "png", self.opts)
        self.assertEqual(list(self.dir.glob("x p*.png")), [])


class LocalResources(Tmp):
    def test_html_cannot_embed_a_local_image(self):  # H6
        secret = self.dir / "secret.png"
        Image.new("RGB", (30, 30), "red").save(secret)
        page = self.dir / "p.html"
        page.write_text(f'<p>hi</p><img src="{secret.as_uri()}"><img src="secret.png">', "utf-8")
        (out,) = convert_file(page, "pdf", self.opts)
        with pymupdf.open(out) as d:
            self.assertEqual(sum(len(p.get_images()) for p in d), 0)

    def test_markdown_cannot_embed_a_local_image(self):  # H6
        secret = self.dir / "secret.png"
        Image.new("RGB", (30, 30), "red").save(secret)
        page = self.dir / "p.md"
        page.write_text("hi\n\n![x](" + secret.as_uri() + ")\n", "utf-8")
        (out,) = convert_file(page, "pdf", self.opts)
        with pymupdf.open(out) as d:
            self.assertEqual(sum(len(p.get_images()) for p in d), 0)


class LogScrub(unittest.TestCase):
    def test_folder_is_removed_from_logged_error_text(self):  # H7
        from convert_win.converter import scrub

        src = Path(tempfile.gettempdir()) / "photo.png"
        msg = f"cannot identify image file '{src}'"
        self.assertNotIn(str(src.parent), scrub(msg, src))
        self.assertIn("photo.png", scrub(msg, src))
        self.assertNotIn("Users", scrub(f"cannot identify image file {str(src)!r}", src))  # the repr() form


class LogRetention(Tmp):
    def test_old_logs_are_deleted_recent_kept(self):  # H7
        old, new = self.dir / "convert_20200101.log", self.dir / "convert_20991231.log"
        old.write_text("x")
        new.write_text("x")
        t = time.time() - 20 * 86400
        os.utime(old, (t, t))
        settings.prune_logs(self.dir)
        self.assertFalse(old.exists())
        self.assertTrue(new.exists())


if __name__ == "__main__":
    unittest.main()
