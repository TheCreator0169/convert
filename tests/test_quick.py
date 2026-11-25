import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from convert_win import main, quick, settings
from convert_win.formats import INPUTS, QUICK, Fmt, quick_fmt

# ignore_cleanup_errors: the settings log handler keeps its file open until exit (Windows cannot delete it then)
_tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)


def setUpModule():
    # no real conversion and no real tray: convert_file and notify are patched in every test that runs quick.run
    os.environ["APPDATA"] = os.environ["LOCALAPPDATA"] = _tmp.name


class FormatsQuick(unittest.TestCase):
    def test_quick_keys_are_the_input_types(self):
        self.assertEqual(set(QUICK), set(INPUTS))

    def test_every_quick_id_resolves(self):
        for t, ids in QUICK.items():
            for fid in ids:
                fmt = quick_fmt(t, fid)
                self.assertIsInstance(fmt, Fmt, f"{t}/{fid}")

    def test_video_audio_id_resolves_to_the_audio_format(self):
        self.assertEqual(quick_fmt("video", "mp3").codec, "libmp3lame")
        self.assertEqual(quick_fmt("video", "mp4").codec, "h264")

    def test_id_outside_the_quick_list_is_refused(self):
        with self.assertRaises(ValueError):
            quick_fmt("doc", "mp3")


class QuickRun(unittest.TestCase):
    def setUp(self):
        # a fresh folder per test; no cleanup: the settings log handler keeps its file open (Windows)
        fresh = tempfile.mkdtemp(dir=_tmp.name)
        env = mock.patch.dict(os.environ, {"APPDATA": fresh, "LOCALAPPDATA": fresh})
        env.start()
        self.addCleanup(env.stop)
        self.dir = Path(tempfile.mkdtemp(dir=_tmp.name))
        self.notify = mock.patch.object(quick, "notify").start()
        self.addCleanup(mock.patch.stopall)

    def path(self, name):
        return str(self.dir / name)

    def convert(self, side_effect=None):
        p = mock.patch("convert_win.converter.convert_file", side_effect=side_effect)
        m = p.start()
        self.addCleanup(p.stop)
        return m

    def last_error_flag(self):
        return self.notify.call_args.kwargs.get("error", False)

    def assert_usage_error(self, argv):
        conv = self.convert()
        self.assertEqual(quick.run(argv), 2, argv)
        conv.assert_not_called()
        self.assertTrue(self.notify.called)
        self.assertTrue(self.last_error_flag())

    def test_no_files(self):
        self.assert_usage_error([])
        self.assert_usage_error(["mp3"])

    def test_unknown_extension_names_the_file_only(self):
        self.assert_usage_error(["jpg", self.path("notes.xyz")])
        self.assertIn("notes.xyz", self.notify.call_args.args[1])
        self.assertNotIn(str(self.dir), self.notify.call_args.args[1])

    def test_mixed_types(self):
        self.assert_usage_error(["jpg", self.path("a.png"), self.path("b.mp3")])

    def test_format_not_in_the_quick_list(self):
        self.assert_usage_error(["mp4", self.path("a.wav")])  # mp4 is a video id, not an audio quick id
        self.assert_usage_error(["bmp", self.path("a.png")])  # bmp is an image format but not in QUICK

    def test_audio_video_mix_uses_the_audio_list(self):
        conv = self.convert()
        self.assertEqual(quick.run(["mp3", self.path("a.mp4"), self.path("b.wav")]), 0)
        self.assertEqual([c.args[1] for c in conv.call_args_list], ["mp3", "mp3"])

    def test_audio_video_mix_refuses_a_video_only_id(self):
        self.assert_usage_error(["webm", self.path("a.mp4"), self.path("b.wav")])

    def test_success_converts_each_file_with_settings(self):
        conv = self.convert()
        files = [self.path("a.png"), self.path("b.png")]
        self.assertEqual(quick.run(["jpg", *files]), 0)
        opts = settings.load()["options"]
        self.assertEqual(conv.call_args_list, [mock.call(f, "jpg", opts, False, notes=mock.ANY) for f in files])
        self.assertEqual(self.notify.call_args.args[1], "Converted 2 file(s) to JPEG")
        self.assertFalse(self.last_error_flag())

    def test_trash_switch_is_passed_through(self):
        (Path(os.environ["APPDATA"]) / "Convert").mkdir(exist_ok=True)
        (Path(os.environ["APPDATA"]) / "Convert" / "settings.json").write_text(json.dumps({"trash_originals": True}))
        conv = self.convert()
        self.assertEqual(quick.run(["png", self.path("a.jpg")]), 0)
        self.assertIs(conv.call_args.args[3], True)

    def test_one_failure_does_not_stop_the_others(self):
        folder = str(self.dir)

        def fake(src, fid, opts, trash, notes=None):
            if Path(src).name == "bad.png":
                raise ValueError(f"cannot read {folder}\\bad.png")
            return []

        conv = self.convert(side_effect=fake)
        files = [self.path("bad.png"), self.path("good.png")]
        self.assertEqual(quick.run(["jpg", *files]), 1)
        self.assertEqual(conv.call_count, 2)  # the second file still converted
        text = self.notify.call_args.args[1]
        self.assertEqual(text, "1 of 2 failed: cannot read ...\\bad.png")
        self.assertNotIn(folder, text)
        self.assertTrue(self.last_error_flag())

    def test_long_job_announces_its_start(self):
        self.convert()
        quick.run(["mp3", self.path("a.mp4")])  # video: start message shown
        self.assertEqual(self.notify.call_args_list[0].args[1], "Converting 1 file(s) to MP3")
        self.notify.reset_mock()
        self.convert()
        quick.run(["jpg", self.path("a.png"), self.path("b.png")])  # two small images: no start message
        self.assertEqual(self.notify.call_count, 1)
        self.assertEqual(self.notify.call_args.args[1], "Converted 2 file(s) to JPEG")

    def test_main_dispatches_quick(self):
        with mock.patch("convert_win.quick.run", return_value=0) as run:
            self.assertEqual(main.main(["--quick", "jpg", self.path("a.png")]), 0)
        run.assert_called_once_with(["jpg", self.path("a.png")])


if __name__ == "__main__":
    unittest.main()
