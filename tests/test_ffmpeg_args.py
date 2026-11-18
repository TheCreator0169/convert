import unittest

from convert_win import ffmpeg_conv as fc
from convert_win.formats import DEFAULTS, OUTPUTS


def args(kind, fid, have=frozenset(), **over):
    key = "gif" if fid == "gif" and kind == "video" else kind
    return fc.build_args("ffmpeg", "-in.mp4", "out", kind, OUTPUTS[kind][fid], {**DEFAULTS[key], **over}, have)


class FfmpegArgs(unittest.TestCase):
    def test_input_follows_dash_i_so_dash_names_are_safe(self):
        a = args("audio", "mp3")
        self.assertEqual(a[a.index("-i") + 1], "-in.mp4")

    def test_mp3_bitrate_and_no_video(self):
        a = args("audio", "mp3", bitrate=256)
        self.assertIn("-vn", a)
        self.assertEqual(a[a.index("-b:a") + 1], "256k")

    def test_lossless_has_no_bitrate(self):
        self.assertNotIn("-b:a", args("audio", "flac"))
        self.assertEqual(args("audio", "wav", bit_depth=24)[args("audio", "wav", bit_depth=24).index("-c:a") + 1],
                         "pcm_s24le")
        self.assertIn("pcm_s16be", args("audio", "aiff"))

    def test_sample_rate_and_channels(self):
        a = args("audio", "ogg", sample_rate=44100, channels=1)
        self.assertEqual((a[a.index("-ar") + 1], a[a.index("-ac") + 1]), ("44100", "1"))

    def test_h264_software_default_and_never_upscale(self):
        a = args("video", "mp4", height=720)
        self.assertEqual(a[a.index("-c:v") + 1], "libx264")
        self.assertIn("scale=-2:'min(ih,720)'", a)

    def test_hardware_only_when_available_and_enabled(self):
        self.assertEqual(args("video", "mp4", {"h264_nvenc"})[args("video", "mp4", {"h264_nvenc"}).index("-c:v") + 1],
                         "h264_nvenc")
        self.assertIn("libx264", args("video", "mp4", {"h264_nvenc"}, hw=False))
        self.assertIn("libx264", args("video", "mp4", frozenset()))

    def test_av1_falls_back_to_libaom(self):
        self.assertIn("libaom-av1", args("video", "mp4-av1"))
        self.assertIn("libsvtav1", args("video", "mp4-av1", {"libsvtav1"}))

    def test_no_audio_option(self):
        self.assertIn("-an", args("video", "mkv", keep_audio=False))

    def test_audio_track_is_mapped_by_number(self):
        self.assertIn("0:a:1", args("audio", "mp3", audio_track=2))
        self.assertIn("0:a:2?", args("video", "mp4", audio_track=3))
        self.assertIn("0:a:0", args("audio", "mp3"))

    def test_subtitles_codec_follows_the_container(self):
        for fid, codec in (("mp4", "mov_text"), ("mov", "mov_text"), ("webm", "webvtt"), ("mkv", "copy")):
            a = args("video", fid, subtitles=True)
            self.assertEqual((a[a.index("0:s?") - 1], a[a.index("-c:s") + 1]), ("-map", codec), fid)
        self.assertNotIn("-c:s", args("video", "mp4"))

    def test_gif_uses_palette(self):
        a = args("video", "gif")
        self.assertTrue(any("palettegen" in x for x in a))

    def test_prores(self):
        self.assertIn("prores_ks", args("video", "mov"))


if __name__ == "__main__":
    unittest.main()
