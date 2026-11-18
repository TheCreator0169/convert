"""v0.1.6: every audio and video format really converts, and the codec in the output is the one asked for."""
import tempfile
import unittest
from pathlib import Path

from convert_win.converter import convert_file
from convert_win.formats import DEFAULTS, OUTPUTS
from convert_win.process import find_tool, run

FFMPEG = find_tool("ffmpeg")
AUDIO_CODEC = {"mp3": "mp3", "m4a": "aac", "wav": "pcm_s16le", "aiff": "pcm_s16be", "flac": "flac", "alac": "alac",
               "opus": "opus", "ogg": "vorbis", "wma": "wmav2", "ac3": "ac3", "wv": "wavpack", "mp2": "mp2"}
VIDEO_CODEC = {"mp4": "h264", "mp4-hevc": "hevc", "mp4-av1": "av1", "mov": "prores", "webm": "vp9", "mkv": "h264"}


@unittest.skipUnless(FFMPEG, "ffmpeg not installed")
class Encoders(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls.tmp.name)
        cls.wav = cls.dir / "in.wav"
        cls.mp4 = cls.dir / "in.mp4"
        run([FFMPEG, "-v", "error", "-f", "lavfi", "-i", "sine=d=1", str(cls.wav)])
        run([FFMPEG, "-v", "error", "-f", "lavfi", "-i", "testsrc=s=160x120:d=1", "-f", "lavfi", "-i", "sine=d=1",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(cls.mp4)])

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def convert(self, src, fid, **over):
        opts = {k: dict(v) for k, v in DEFAULTS.items()}
        kind = "audio" if fid in AUDIO_CODEC else "video"
        opts[kind].update(over)
        (out,) = convert_file(src, fid, opts)
        self.addCleanup(out.unlink)
        _, _, err = run([FFMPEG, "-hide_banner", "-i", str(out)])
        return err

    def test_every_audio_format_from_audio_and_from_video(self):
        for fid, codec in AUDIO_CODEC.items():
            for src in (self.wav, self.mp4):
                with self.subTest(fid=fid, src=src.name):
                    self.assertIn(f"Audio: {codec}", self.convert(src, fid))

    def test_audio_formats_cover_the_list(self):
        self.assertEqual(set(AUDIO_CODEC), set(OUTPUTS["audio"]))

    def test_24_bit_lossless(self):
        for fid in ("wav", "flac", "alac"):
            with self.subTest(fid=fid):
                self.assertIn("24", self.convert(self.wav, fid, bit_depth=24).split("Audio:")[1].split("\n")[0])

    def test_every_video_format_has_its_codec_and_audio(self):
        for fid, codec in VIDEO_CODEC.items():
            with self.subTest(fid=fid):
                err = self.convert(self.mp4, fid, hw=False)
                self.assertIn(f"Video: {codec}", err)
                self.assertIn("Audio:", err)

    def test_video_formats_cover_the_list(self):
        self.assertEqual(set(VIDEO_CODEC) | {"gif"}, set(OUTPUTS["video"]))

    def test_no_audio_and_resize(self):
        err = self.convert(self.mp4, "mp4", hw=False, keep_audio=False, height=60)
        self.assertNotIn("Audio:", err)
        self.assertIn("x60", err)


if __name__ == "__main__":
    unittest.main()
