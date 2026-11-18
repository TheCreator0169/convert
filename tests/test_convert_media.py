import tempfile
import unittest
from pathlib import Path

from convert_win.converter import convert_file
from convert_win.formats import DEFAULTS
from convert_win.process import find_tool, run

FFMPEG = find_tool("ffmpeg")


@unittest.skipUnless(FFMPEG, "ffmpeg not installed")
class ConvertMedia(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        d = Path(cls.tmp.name)
        cls.wav = d / "tone.wav"
        cls.mp4 = d / "clip.mp4"
        run([FFMPEG, "-v", "error", "-f", "lavfi", "-i", "sine=d=1", str(cls.wav)])
        run([FFMPEG, "-v", "error", "-f", "lavfi", "-i", "testsrc=s=320x240:d=1", "-f", "lavfi", "-i", "sine=d=1",
             "-pix_fmt", "yuv420p", "-shortest", str(cls.mp4)])

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.opts = {k: dict(v) for k, v in DEFAULTS.items()}

    def probe(self, f):
        rc, out, _ = run([find_tool("ffprobe"), "-v", "error", "-show_entries", "stream=codec_name,width",
                          "-of", "csv=p=0", str(f)])
        return out

    def test_audio_targets(self):
        for fid, codec in (("mp3", "mp3"), ("flac", "flac"), ("opus", "opus"), ("m4a", "aac"), ("ogg", "vorbis"),
                           ("alac", "alac"), ("aiff", "pcm_s16be")):
            with self.subTest(fid):
                (out,) = convert_file(self.wav, fid, self.opts)
                self.assertIn(codec, self.probe(out))
                out.unlink()

    def test_video_targets(self):
        for fid in ("mp4", "webm", "mkv", "gif"):
            with self.subTest(fid):
                (out,) = convert_file(self.mp4, fid, self.opts)
                self.assertGreater(out.stat().st_size, 0)
                out.unlink()

    def test_video_to_audio(self):
        (out,) = convert_file(self.mp4, "mp3", self.opts)
        self.assertIn("mp3", self.probe(out))
        out.unlink()

    def test_height_never_upscales(self):
        self.opts["video"]["height"] = 1080
        (out,) = convert_file(self.mp4, "mp4", self.opts)
        self.assertIn("320", self.probe(out))
        out.unlink()

    def test_bad_input_reports_and_leaves_no_file(self):
        bad = Path(self.tmp.name) / "bad.mp3"
        bad.write_bytes(b"not audio")
        with self.assertRaises(RuntimeError):
            convert_file(bad, "wav", self.opts)
        self.assertFalse(Path(self.tmp.name, "bad.wav").exists())

    def test_name_starting_with_dash(self):
        odd = Path(self.tmp.name) / "-odd.wav"
        odd.write_bytes(self.wav.read_bytes())
        (out,) = convert_file(odd, "mp3", self.opts)
        self.assertGreater(out.stat().st_size, 0)
        out.unlink()


if __name__ == "__main__":
    unittest.main()
