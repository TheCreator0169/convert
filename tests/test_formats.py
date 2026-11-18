import tempfile
import unittest
from pathlib import Path

from convert_win import formats


class Formats(unittest.TestCase):
    def test_file_type(self):
        self.assertEqual(formats.file_type("a/B.MP3"), "audio")
        self.assertEqual(formats.file_type("x.heic"), "image")
        self.assertIsNone(formats.file_type("x.exe"))

    def test_outputs_same_type(self):
        ids = {f.id for f in formats.outputs_for(["a.wav", "b.flac"])}
        self.assertIn("mp3", ids)

    def test_audio_video_mix_gets_audio_targets(self):
        ids = {f.id for f in formats.outputs_for(["a.wav", "b.mp4"])}
        self.assertIn("mp3", ids)
        self.assertNotIn("mov", ids)

    def test_video_alone_offers_video_then_audio_targets(self):
        ids = [f.id for f in formats.outputs_for(["a.mp4"])]
        self.assertEqual((ids[0], ids[-1]), ("mp4", "mp2"))
        self.assertIn("mp3", ids)

    def test_mixed_families_offer_nothing(self):
        self.assertEqual(formats.outputs_for(["a.wav", "b.png"]), [])
        self.assertEqual(formats.outputs_for(["a.exe"]), [])
        self.assertEqual(formats.outputs_for([]), [])

    def test_same_extension_not_offered_for_images_and_docs(self):
        self.assertNotIn("png", {f.id for f in formats.outputs_for(["a.png"])})
        self.assertNotIn("txt", {f.id for f in formats.outputs_for(["a.txt"])})

    def test_video_to_audio_format(self):
        kind, fmt = formats.output_fmt("clip.mp4", "mp3")
        self.assertEqual((kind, fmt.ext), ("audio", "mp3"))
        with self.assertRaises(ValueError):
            formats.output_fmt("clip.png", "mp3")

    def test_unique_path_never_overwrites(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d, "song.wav")
            src.touch()
            Path(d, "song.mp3").touch()
            Path(d, "song 2.mp3").touch()
            self.assertEqual(formats.unique_path(src, "mp3").name, "song 3.mp3")


if __name__ == "__main__":
    unittest.main()
