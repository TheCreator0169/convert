import tempfile
import unittest
from pathlib import Path

from PIL import Image

from convert_win.converter import convert_file
from convert_win.formats import DEFAULTS


class ConvertImage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.opts = {k: dict(v) for k, v in DEFAULTS.items()}
        self.src = self.dir / "pic.png"
        Image.new("RGBA", (120, 80), (255, 0, 0, 128)).save(self.src)

    def tearDown(self):
        self.tmp.cleanup()

    def test_round_trip_every_target(self):
        for fid in ("jpg", "webp", "tiff", "gif", "bmp", "pdf", "heic", "avif"):
            with self.subTest(fid):
                (out,) = convert_file(self.src, fid, self.opts)
                self.assertGreater(out.stat().st_size, 0)
                self.assertEqual(out.suffix, "." + fid)
                if fid != "pdf":
                    with Image.open(out) as im:
                        self.assertEqual(im.size, (120, 80))

    def test_alpha_flattened_on_white_for_jpeg(self):
        (out,) = convert_file(self.src, "jpg", self.opts)
        with Image.open(out) as im:
            r, g, b = im.convert("RGB").getpixel((5, 5))
        self.assertGreater(g, 100)  # white-ish blend, not black

    def test_max_size(self):
        self.opts["image"]["max_size"] = 60
        (out,) = convert_file(self.src, "webp", self.opts)
        with Image.open(out) as im:
            self.assertEqual(max(im.size), 60)

    def test_original_untouched_and_second_run_numbered(self):
        convert_file(self.src, "webp", self.opts)
        (second,) = convert_file(self.src, "webp", self.opts)
        self.assertEqual(second.name, "pic 2.webp")
        self.assertTrue(self.src.exists())

    def test_failure_leaves_no_partial_file(self):
        bad = self.dir / "bad.png"
        bad.write_bytes(b"not an image")
        with self.assertRaises(Exception):
            convert_file(bad, "jpg", self.opts)
        self.assertEqual(list(self.dir.glob("bad*.jpg")), [])

    def test_trash_only_after_success(self):
        bad = self.dir / "bad.png"
        bad.write_bytes(b"nope")
        with self.assertRaises(Exception):
            convert_file(bad, "jpg", self.opts, trash_original=True)
        self.assertTrue(bad.exists())


if __name__ == "__main__":
    unittest.main()
