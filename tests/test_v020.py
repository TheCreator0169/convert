"""v0.2.0: a multi-image HEIC converted to a single-image format gives one file per image (name_1, name_2, ...).

Synthetic HEIC files are written with pillow_heif in a temp folder. send2trash is mocked; APPDATA and LOCALAPPDATA point
at a temp folder for the CLI test. Classes are unittest.TestCase subclasses; FakeFrame is a helper (no tests).
"""
import contextlib
import io
import logging
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import pillow_avif  # noqa: F401  registers AVIF for writing the AVIF control file
import pillow_heif
from PIL import Image

from convert_win import converter, image_conv, main
from convert_win.converter import convert_file
from convert_win.formats import DEFAULTS
from convert_win.process import Cancelled

ORIENT = 274


def make_frame(size, colour, orientation=None):
    """A frame with an optional EXIF orientation tag (pillow_heif applies it when the file is read)."""
    im = Image.new("RGB", size, colour)
    if orientation is not None:
        ex = im.getexif()
        ex[ORIENT] = orientation
        im.info["exif"] = ex.tobytes()
    return im


def write_heic(path, frames):
    """Writes a HEIC with one image per frame (a single-image file when there is one frame)."""
    frames[0].save(path, save_all=len(frames) > 1, append_images=frames[1:])
    return path


def image_sizes(paths):
    sizes = []
    for p in paths:
        with Image.open(p) as im:
            sizes.append(im.size)
    return sizes


def close_log():
    """The convert logger keeps a FileHandler on the temp folder's log file: close it so the folder can be removed."""
    log = logging.getLogger("convert")
    for h in list(log.handlers):
        h.close()
        log.removeHandler(h)


class FakeFrame:
    """Stands in for a prepared frame whose save writes nothing: the empty-output check must catch it."""

    def save(self, dst, fmt, **kw):
        Path(dst).write_bytes(b"")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        env = mock.patch.dict(os.environ, {"APPDATA": self.tmp.name, "LOCALAPPDATA": self.tmp.name})
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(close_log)  # runs before the temp folder is removed: the CLI test opens the log file
        self.opts = {k: dict(v) for k, v in DEFAULTS.items()}
        self.trash = mock.patch("convert_win.converter.send2trash").start()
        self.addCleanup(mock.patch.stopall)
        self.src = self.dir / "multi.heic"
        write_heic(self.src, [make_frame((64, 40), (255, 0, 0)),
                              make_frame((32, 96), (0, 255, 0)),
                              make_frame((50, 50), (0, 0, 255))])

    def outputs(self, pattern="multi*.jpg"):
        return sorted(p.name for p in self.dir.glob(pattern))

    def everything(self):
        """Every file in the folder except the source: what a failed or cancelled run must leave behind."""
        return sorted(p.name for p in self.dir.iterdir() if p != self.src)


class StillsConvert(Base):
    def test_single_image_heic_keeps_plain_name(self):
        single = self.dir / "one.heic"
        write_heic(single, [make_frame((40, 30), (9, 9, 9))])
        outs = convert_file(single, "jpg", self.opts, trash_original=True)
        self.assertEqual([p.name for p in outs], ["one.jpg"])
        self.assertEqual(image_sizes(outs), [(40, 30)])
        self.trash.assert_called_once()
        self.assertEqual(self.trash.call_args.args[0], os.path.abspath(single))

    def test_three_images_give_numbered_files(self):
        outs = convert_file(self.src, "jpg", self.opts)
        self.assertEqual([p.name for p in outs], ["multi_1.jpg", "multi_2.jpg", "multi_3.jpg"])
        self.assertEqual(self.outputs(), ["multi_1.jpg", "multi_2.jpg", "multi_3.jpg"])
        self.assertEqual(image_sizes(outs), [(64, 40), (32, 96), (50, 50)])
        for p in outs:
            self.assertGreater(p.stat().st_size, 0)
            with Image.open(p) as im:
                self.assertEqual(im.format, "JPEG")

    def test_each_image_keeps_its_own_size(self):
        outs = convert_file(self.src, "png", self.opts)
        self.assertEqual(image_sizes(outs), [(64, 40), (32, 96), (50, 50)])

    def test_exif_orientation_applied_per_image(self):
        # frame 1 is stored 64x40 with orientation 6 (turn 90 degrees): upright it is 40x64;
        # frame 3 is stored 60x30 with orientation 8 (turn 270): upright it is 30x60 (non-square, so the turn shows)
        oriented = self.dir / "turn.heic"
        write_heic(oriented, [make_frame((64, 40), (255, 0, 0), orientation=6),
                              make_frame((32, 96), (0, 255, 0)),
                              make_frame((60, 30), (0, 0, 255), orientation=8)])
        outs = convert_file(oriented, "jpg", self.opts)
        self.assertEqual(image_sizes(outs), [(40, 64), (32, 96), (30, 60)])
        for p in outs:
            with Image.open(p) as im:
                self.assertNotIn(ORIENT, im.getexif())  # the pixels are upright: no tag left to turn them again

    def test_original_trashed_once_after_every_file_is_written(self):
        seen = []
        self.trash.side_effect = lambda p: seen.append(self.outputs())
        convert_file(self.src, "jpg", self.opts, trash_original=True)
        self.trash.assert_called_once()
        self.assertEqual(seen, [["multi_1.jpg", "multi_2.jpg", "multi_3.jpg"]])

    def test_original_kept_when_trash_not_asked(self):
        convert_file(self.src, "jpg", self.opts, trash_original=False)
        self.trash.assert_not_called()
        self.assertTrue(self.src.exists())

    def test_second_run_does_not_overwrite(self):
        convert_file(self.src, "jpg", self.opts)
        first = {n: (self.dir / n).read_bytes() for n in self.outputs()}
        outs = convert_file(self.src, "jpg", self.opts)
        self.assertEqual([p.name for p in outs], ["multi_1 2.jpg", "multi_2 2.jpg", "multi_3 2.jpg"])
        for name, data in first.items():
            self.assertEqual((self.dir / name).read_bytes(), data)  # the earlier run's files are untouched
        self.assertEqual(len(self.outputs("multi*.jpg")), 6)

    def test_tiff_and_gif_keep_one_file_with_every_frame(self):
        for fid, ext in (("tiff", "tiff"), ("gif", "gif")):
            with self.subTest(fid):
                outs = convert_file(self.src, fid, self.opts)
                self.assertEqual([p.name for p in outs], [f"multi.{ext}"])
                with Image.open(outs[0]) as im:
                    self.assertEqual(getattr(im, "n_frames", 1), 3)
                    self.assertEqual(im.size, (64, 40))

    def test_avif_multi_frame_is_not_split(self):
        # AVIF keeps the first-frame behaviour: the split is for HEIC only (same-size frames: AVIF needs them)
        avif = self.dir / "anim.avif"
        frames = [Image.new("RGB", (48, 48), c) for c in [(255, 0, 0), (0, 255, 0), (0, 0, 255)]]
        frames[0].save(avif, save_all=True, append_images=frames[1:], duration=100)
        with Image.open(avif) as im:
            self.assertGreater(getattr(im, "n_frames", 1), 1, "control file must really be multi-frame")
        outs = convert_file(avif, "jpg", self.opts)
        self.assertEqual([p.name for p in outs], ["anim.jpg"])


class StillsLimits(Base):
    def assert_refused_clean(self, message):
        before = self.everything()
        with self.assertRaises(RuntimeError) as cm:
            convert_file(self.src, "jpg", self.opts, trash_original=True)
        self.assertIn(message, str(cm.exception))
        self.assertEqual(self.everything(), before)
        self.trash.assert_not_called()
        self.assertTrue(self.src.exists())

    def test_too_many_images_refused_with_message(self):
        with mock.patch.object(image_conv, "MAX_FRAMES", 2):
            self.assert_refused_clean("too many images in this HEIC: 3 (limit 2)")

    def test_too_many_pixels_refused_with_message(self):
        with mock.patch.object(image_conv, "MAX_FRAME_PIXELS", 1000):
            self.assert_refused_clean("too many pixels in this HEIC")

    def test_one_image_over_the_limit_is_skipped_others_written(self):
        # sizes 2560, 3072, 2500 pixels: the limit 2800 skips image 2 only
        with mock.patch.object(image_conv, "MAX_IMAGE_PIXELS", 2800):
            notes = []
            outs = convert_file(self.src, "jpg", self.opts, trash_original=True, notes=notes)
        self.assertEqual([p.name for p in outs], ["multi_1.jpg", "multi_3.jpg"])
        self.assertEqual(image_sizes(outs), [(64, 40), (50, 50)])
        self.assertTrue(any("images 2 of 3 skipped" in n for n in notes), notes)
        self.assertTrue(any("original kept" in n for n in notes), notes)
        self.trash.assert_not_called()
        self.assertTrue(self.src.exists())

    def test_every_image_over_the_limit_is_an_error_with_no_files(self):
        with mock.patch.object(image_conv, "MAX_IMAGE_PIXELS", 100):
            with self.assertRaises(RuntimeError) as cm:
                convert_file(self.src, "jpg", self.opts, trash_original=True)
        self.assertIn("no image could be converted", str(cm.exception))
        self.assertEqual(self.everything(), [])
        self.trash.assert_not_called()
        self.assertTrue(self.src.exists())

    def test_empty_output_is_an_error_and_nothing_is_left(self):
        with mock.patch.object(image_conv, "_prep", lambda im, fmt, opts: FakeFrame()):
            with self.assertRaises(RuntimeError) as cm:
                convert_file(self.src, "jpg", self.opts, trash_original=True)
        self.assertIn("converter wrote no output", str(cm.exception))
        self.assertEqual(self.everything(), [])
        self.trash.assert_not_called()


class StillsCancel(Base):
    def test_cancel_between_images_removes_written_files(self):
        cancel = mock.Mock()
        cancel.is_set.return_value = False
        real = converter.unique_path
        reserved = []
        real_prep = image_conv._prep
        prepared = []

        def cancel_after_second(src, ext, tag=""):
            out = real(src, ext, tag)
            reserved.append(out)
            if len(reserved) == 2:  # the user presses Cancel while image 2 is being written
                cancel.is_set.return_value = True
            return out

        def count_prep(im, fmt, opts):
            prepared.append(1)
            return real_prep(im, fmt, opts)

        with mock.patch("convert_win.converter.unique_path", cancel_after_second), \
                mock.patch.object(image_conv, "_prep", count_prep):
            with self.assertRaises(Cancelled):
                convert_file(self.src, "jpg", self.opts, trash_original=True, cancel=cancel)
        # the check at the top of the loop stops before image 3 is decoded: exactly two images were prepared
        self.assertEqual(len(prepared), 2)
        self.assertEqual(self.everything(), [])
        self.trash.assert_not_called()
        self.assertTrue(self.src.exists())

    def test_cancel_during_preparation_of_an_image_is_caught_before_it_is_written(self):
        # the flag turns on while image 3 is being prepared: the check just before the save must stop it
        cancel = threading.Event()
        real_prep = image_conv._prep
        prepared = []

        def prep_then_cancel(im, fmt, opts):
            prepared.append(1)
            out = real_prep(im, fmt, opts)
            if len(prepared) == 3:
                cancel.set()
            return out

        with mock.patch.object(image_conv, "_prep", prep_then_cancel):
            with self.assertRaises(Cancelled):
                convert_file(self.src, "jpg", self.opts, trash_original=True, cancel=cancel)
        self.assertEqual(len(prepared), 3)
        self.assertEqual(self.everything(), [])
        self.trash.assert_not_called()

    def test_cancel_set_before_start_writes_nothing(self):
        cancel = mock.Mock()
        cancel.is_set.return_value = True
        with self.assertRaises(Cancelled):
            convert_file(self.src, "jpg", self.opts, trash_original=True, cancel=cancel)
        self.assertEqual(self.everything(), [])
        self.trash.assert_not_called()


class StillsCli(Base):
    def test_cli_lists_every_output(self):
        out = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main.main(["--cli", "jpg", str(self.src)])
        self.assertEqual(code, 0, err.getvalue())
        lines = [ln for ln in out.getvalue().splitlines() if ln.strip()]
        self.assertEqual(len(lines), 3, lines)
        for n, line in enumerate(lines, 1):
            self.assertIn(" -> ", line)
            self.assertTrue(line.endswith(f"multi_{n}.jpg"), line)


class StillsMetadata(Base):
    def test_exif_of_one_image_does_not_leak_to_the_next(self):
        """Reviewer finding: getexif() kept the tags of an earlier image when a later image had none."""
        first = Image.new("RGB", (40, 30), (255, 0, 0))
        ex = first.getexif()
        ex[271] = "MakerA"  # Make
        first.info["exif"] = ex.tobytes()
        second = Image.new("RGB", (40, 30), (0, 255, 0))  # no EXIF at all
        src = self.dir / "meta.heic"
        write_heic(src, [first, second])
        convert_file(str(src), "jpg", self.opts)
        with Image.open(self.dir / "meta_1.jpg") as a, Image.open(self.dir / "meta_2.jpg") as b:
            self.assertEqual(a.getexif().get(271), "MakerA")
            self.assertIsNone(b.getexif().get(271))


if __name__ == "__main__":
    unittest.main()
