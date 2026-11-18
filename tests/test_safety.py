"""v0.1.1 safety: an original is trashed only when the output is complete; settings never crash."""
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import pymupdf
from PIL import Image

from convert_win import converter, settings
from convert_win.converter import convert_file
from convert_win.formats import DEFAULTS
from convert_win.process import Cancelled


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.opts = {k: {**v} for k, v in DEFAULTS.items()}
        self.trashed = []
        p = mock.patch.object(converter, "send2trash", lambda s: self.trashed.append(s))
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)


class PdfSafety(Base):
    def test_scanned_pdf_to_txt_fails_and_keeps_original(self):  # S1
        pdf = self.dir / "scan.pdf"
        Image.new("RGB", (100, 50), "white").save(pdf)
        with self.assertRaisesRegex(RuntimeError, "no text"):
            convert_file(pdf, "txt", self.opts, trash_original=True)
        self.assertEqual(self.trashed, [])
        self.assertEqual(list(self.dir.glob("scan*.txt")), [])

    def test_cancel_removes_partial_pages(self):  # S9
        pdf = self.dir / "three.pdf"
        d = pymupdf.open()
        for _ in range(3):
            d.new_page()
        d.save(pdf)
        d.close()
        ev = threading.Event()
        real = pymupdf.Page.get_pixmap

        def get(page, *a, **k):
            if page.number == 1:
                ev.set()
            return real(page, *a, **k)

        with mock.patch.object(pymupdf.Page, "get_pixmap", get):
            with self.assertRaises(Cancelled):
                convert_file(pdf, "png", self.opts, cancel=ev)
        self.assertEqual(list(self.dir.glob("three p*.png")), [])

    def test_cancel_before_start(self):  # S9
        img = self.dir / "a.png"
        Image.new("RGB", (5, 5)).save(img)
        ev = threading.Event()
        ev.set()
        with self.assertRaises(Cancelled):
            convert_file(img, "jpg", self.opts, cancel=ev)


class ImageSafety(Base):
    def test_multipage_tiff_to_pdf_keeps_all_pages(self):  # S2
        frames = [Image.new("RGB", (50, 50), c) for c in ("red", "green", "blue")]
        src = self.dir / "m.tif"
        frames[0].save(src, save_all=True, append_images=frames[1:])
        notes = []
        (out,) = convert_file(src, "pdf", self.opts, trash_original=True, notes=notes)
        with pymupdf.open(out) as d:
            self.assertEqual(d.page_count, 3)
        self.assertEqual(len(self.trashed), 1)
        self.assertEqual(notes, [])

    def test_animated_gif_to_webp_keeps_frames(self):  # S2
        frames = [Image.new("RGB", (20, 20), c) for c in ("red", "green")]
        src = self.dir / "a.gif"
        frames[0].save(src, save_all=True, append_images=frames[1:], duration=50, loop=0)
        (out,) = convert_file(src, "webp", self.opts)
        with Image.open(out) as im:
            self.assertEqual(im.n_frames, 2)

    def test_multiframe_to_single_frame_format_keeps_original(self):  # S2
        frames = [Image.new("RGB", (20, 20), c) for c in ("red", "green")]
        src = self.dir / "a.gif"
        frames[0].save(src, save_all=True, append_images=frames[1:])
        notes = []
        convert_file(src, "png", self.opts, trash_original=True, notes=notes)
        self.assertEqual(self.trashed, [])
        self.assertTrue(any("first frame" in n for n in notes))

    def test_exif_orientation_applied_and_metadata_kept(self):  # S3
        im = Image.new("RGB", (40, 20), "red")
        ex = im.getexif()
        ex[274] = 6
        ex[306] = "2020:01:02 03:04:05"
        src = self.dir / "rot.jpg"
        im.save(src, exif=ex)
        (out,) = convert_file(src, "png", self.opts)
        with Image.open(out) as o:
            self.assertEqual(o.size, (20, 40))
            self.assertEqual(o.getexif().get(306), "2020:01:02 03:04:05")
            self.assertNotIn(274, o.getexif())

    def test_trash_failure_is_a_note_not_a_failure(self):  # S4
        src = self.dir / "a.png"
        Image.new("RGB", (5, 5)).save(src)

        def boom(_):
            raise OSError("bin unavailable")

        notes = []
        with mock.patch.object(converter, "send2trash", boom):
            (out,) = convert_file(src, "webp", self.opts, trash_original=True, notes=notes)
        self.assertTrue(out.exists())
        self.assertTrue(any("Recycle Bin" in n for n in notes))


class DocSafety(Base):
    def test_utf16_text_decodes(self):  # S6
        src = self.dir / "u16.txt"
        src.write_bytes("héllo wörld".encode("utf-16"))
        (out,) = convert_file(src, "html", self.opts)
        self.assertIn("héllo wörld", out.read_text("utf-8"))

    def test_rtf_source_is_kept_with_a_warning(self):  # S7
        src = self.dir / "a.rtf"
        src.write_text(r"{\rtf1\ansi Hello}", "ascii")
        notes = []
        convert_file(src, "txt", self.opts, trash_original=True, notes=notes)
        self.assertEqual(self.trashed, [])
        self.assertTrue(any("text only" in n for n in notes))


class SettingsSafety(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = mock.patch.dict(os.environ, {"APPDATA": self.tmp.name, "LOCALAPPDATA": self.tmp.name})
        env.start()
        self.addCleanup(env.stop)
        (Path(self.tmp.name) / "Convert").mkdir()
        self.file = Path(self.tmp.name) / "Convert" / "settings.json"

    def write(self, data, enc="utf-8"):
        self.file.write_text(data if isinstance(data, str) else json.dumps(data), enc)

    def test_non_object_json(self):  # S5
        for raw in ("[]", "3", "null", "{bad"):
            self.write(raw)
            self.assertEqual(settings.load(), {"trash_originals": False, "options": DEFAULTS})

    def test_options_not_an_object(self):  # S5
        self.write({"options": [], "trash_originals": True})
        self.assertEqual(settings.load()["options"], DEFAULTS)

    def test_bom_is_read(self):  # S5
        self.write({"trash_originals": True}, "utf-8-sig")
        self.assertTrue(settings.load()["trash_originals"])

    def test_trash_needs_a_real_true(self):  # S5
        for v in ("false", "true", 1, "yes"):
            self.write({"trash_originals": v})
            self.assertFalse(settings.load()["trash_originals"], v)

    def test_wrong_type_and_unknown_keys_dropped(self):  # S5
        self.write({"options": {"video": {"keep_audio": 1, "fps": "fast", "bogus": 1}, "gif": {"fps": True}}})
        o = settings.load()["options"]
        self.assertIs(o["video"]["keep_audio"], DEFAULTS["video"]["keep_audio"])
        self.assertEqual(o["video"]["fps"], DEFAULTS["video"]["fps"])
        self.assertNotIn("bogus", o["video"])
        self.assertEqual(o["gif"]["fps"], DEFAULTS["gif"]["fps"])

    def test_good_values_survive(self):  # S5
        self.write({"options": {"video": {"fps": 24, "keep_audio": False}}})
        v = settings.load()["options"]["video"]
        self.assertEqual((v["fps"], v["keep_audio"]), (24, False))


class FfmpegArgsSafety(unittest.TestCase):
    def test_unknown_video_quality_and_zero_gif_fps(self):  # S5, S11
        from convert_win import ffmpeg_conv
        from convert_win.formats import output_fmt

        src = Path("a.mp4")
        kind, fmt = output_fmt(src, "gif")
        args = ffmpeg_conv.build_args("ffmpeg", src, Path("a.gif"), kind, fmt, {"width": 480, "fps": 0}, {})
        self.assertIn("fps=1,", " ".join(map(str, args)))
        kind, fmt = output_fmt(src, "mov")
        opts = {**DEFAULTS["video"], "video_quality": "best"}
        ffmpeg_conv.build_args("ffmpeg", src, Path("a.mov"), kind, fmt, opts, {})  # must not raise


if __name__ == "__main__":
    unittest.main()
