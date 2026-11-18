"""v0.1.3: extra audio tracks and subtitles are reported and the original is kept."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from convert_win.converter import convert_file
from convert_win.formats import DEFAULTS
from convert_win.process import find_tool, run

FFMPEG = find_tool("ffmpeg")


@unittest.skipUnless(FFMPEG, "ffmpeg not installed")
class Tracks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        d = Path(cls.tmp.name)
        srt = d / "s.srt"
        srt.write_text("1\n00:00:00,000 --> 00:00:00,900\nhello\n", "utf-8")
        cls.multi = d / "multi.mkv"  # 1 video, 2 audio, 1 subtitle
        rc, _, err = run([FFMPEG, "-v", "error", "-f", "lavfi", "-i", "testsrc=s=160x120:d=1", "-f", "lavfi", "-i", "sine=d=1",
                          "-f", "lavfi", "-i", "sine=f=880:d=1", "-i", str(srt), "-map", "0", "-map", "1", "-map", "2",
                          "-map", "3", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-c:s", "srt",
                          "-shortest", str(cls.multi)])
        assert rc == 0, err
        cls.single = d / "one.wav"
        run([FFMPEG, "-v", "error", "-f", "lavfi", "-i", "sine=d=1", str(cls.single)])

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.opts = {k: dict(v) for k, v in DEFAULTS.items()}
        p = mock.patch("convert_win.converter.send2trash")
        self.trash = p.start()
        self.addCleanup(p.stop)
        self.notes = []

    def conv(self, src, fmt):
        with tempfile.TemporaryDirectory() as t:
            work = Path(t) / Path(src).name
            work.write_bytes(Path(src).read_bytes())
            convert_file(work, fmt, self.opts, trash_original=True, notes=self.notes)

    def test_two_audio_tracks_to_mp3_warns_and_keeps_original(self):
        self.conv(self.multi, "mp3")
        self.assertTrue(any("2 audio tracks" in n for n in self.notes), self.notes)
        self.trash.assert_not_called()

    def test_subtitles_and_extra_audio_to_mp4_warn(self):
        self.conv(self.multi, "mp4")
        text = " ".join(self.notes)
        self.assertIn("2 audio tracks", text)
        self.assertIn("subtitles were dropped", text)
        self.trash.assert_not_called()

    def test_audio_off_means_no_audio_warning(self):
        self.opts["video"]["keep_audio"] = False
        self.conv(self.multi, "mp4")
        self.assertNotIn("audio tracks", " ".join(self.notes))

    def test_single_track_no_warning_and_original_trashed(self):
        self.conv(self.single, "mp3")
        self.assertEqual(self.notes, [])
        self.trash.assert_called_once()


if __name__ == "__main__":
    unittest.main()
