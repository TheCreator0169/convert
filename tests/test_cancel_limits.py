"""v0.1.5: cancel stops image and document jobs between frames and pages; huge animations are refused; errors are readable."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pymupdf
from PIL import Image
from PySide6.QtWidgets import QApplication

from convert_win import image_conv, ui
from convert_win.converter import convert_file
from convert_win.formats import DEFAULTS
from convert_win.process import Cancelled


class FlipAfter:
    """A cancel flag that turns on after `n` looks: stands in for the user pressing Cancel mid-job."""

    def __init__(self, n):
        self.n, self.looks = n, 0

    def is_set(self):
        self.looks += 1
        return self.looks > self.n


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.opts = {k: {**v} for k, v in DEFAULTS.items()}
        self.addCleanup(self.tmp.cleanup)
        p = mock.patch("convert_win.converter.send2trash")
        self.trash = p.start()
        self.addCleanup(p.stop)

    def gif(self, frames=10, size=(20, 20)):
        src = self.dir / "anim.gif"
        ims = [Image.new("RGB", size, (i * 20 % 256, 0, 0)) for i in range(frames)]
        ims[0].save(src, save_all=True, append_images=ims[1:], duration=50, loop=0)
        return src


class CancelMidJob(Base):
    def test_image_job_stops_between_frames_and_leaves_nothing(self):
        src = self.gif()
        with self.assertRaises(Cancelled):
            convert_file(src, "webp", self.opts, trash_original=True, cancel=FlipAfter(4))
        self.assertEqual(list(self.dir.glob("anim*.webp")), [])
        self.trash.assert_not_called()
        self.assertTrue(src.exists())

    def test_document_job_stops_between_pages_and_leaves_nothing(self):
        src = self.dir / "long.txt"
        src.write_text("\n".join(f"Line {i}" for i in range(400)), "utf-8")
        with self.assertRaises(Cancelled):
            convert_file(src, "pdf", self.opts, trash_original=True, cancel=FlipAfter(3))
        self.assertEqual(list(self.dir.glob("long*.pdf")), [])
        self.trash.assert_not_called()

    def test_uncancelled_jobs_still_finish(self):
        (out,) = convert_file(self.gif(), "webp", self.opts, cancel=FlipAfter(10 ** 6))
        with Image.open(out) as im:
            self.assertEqual(im.n_frames, 10)


class FrameCaps(Base):
    def test_too_many_frames_is_refused_without_output(self):
        src = self.gif(frames=6)
        with mock.patch.object(image_conv, "MAX_FRAMES", 5):
            with self.assertRaisesRegex(RuntimeError, "animation too large"):
                convert_file(src, "pdf", self.opts, trash_original=True)
        self.assertEqual(list(self.dir.glob("anim*.pdf")), [])
        self.trash.assert_not_called()

    def test_too_many_pixels_is_refused(self):
        src = self.gif(frames=4, size=(100, 100))
        with mock.patch.object(image_conv, "MAX_FRAME_PIXELS", 39_999):
            with self.assertRaisesRegex(RuntimeError, "animation too large"):
                convert_file(src, "tiff", self.opts)

    def test_single_frame_target_ignores_the_cap(self):
        src = self.gif(frames=6)
        notes = []
        with mock.patch.object(image_conv, "MAX_FRAMES", 5):
            (out,) = convert_file(src, "png", self.opts, notes=notes)
        self.assertTrue(out.exists())
        self.assertTrue(any("first frame" in n for n in notes))


class ErrorDisplay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        cls.tmp = tempfile.TemporaryDirectory()
        os.environ["APPDATA"] = os.environ["LOCALAPPDATA"] = cls.tmp.name
        cls.app = QApplication.instance() or QApplication([])

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_one_line_per_failure_selectable_with_log_button(self):
        win = ui.Window()
        win.worker = mock.Mock()
        win.worker.cancelled = False
        win.worker.trash = False
        win._done([], [("a.png", "cannot identify image file"), ("b.png", "NotImplementedError")], [])
        text = win.msg.text()
        self.assertIn("2 failed:\n- a.png: cannot identify image file\n- b.png: NotImplementedError", text)
        self.assertTrue(win.msg.wordWrap())
        self.assertTrue(win.msg.textInteractionFlags() & ui.Qt.TextSelectableByMouse)
        self.assertFalse(win.logs_btn.isHidden())

    def test_log_button_hidden_when_nothing_failed(self):
        win = ui.Window()
        win.worker = mock.Mock()
        win.worker.cancelled = False
        win.worker.trash = False
        win._done(["x.png"], [], [])
        self.assertTrue(win.logs_btn.isHidden())

    def test_pressing_cancel_says_what_happens(self):
        win = ui.Window()
        win.worker = mock.Mock()
        win._cancel()
        self.assertIn("Cancelling", win.msg.text())
        win.worker = None


if __name__ == "__main__":
    unittest.main()
