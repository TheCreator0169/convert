import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image
from PySide6.QtWidgets import QApplication

from convert_win import ui

_tmp = tempfile.TemporaryDirectory()
app = None


def setUpModule():
    # Offscreen has no fonts (PDFs come out empty), so it is set here, not at import: other suites keep the real platform.
    global app
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["APPDATA"] = os.environ["LOCALAPPDATA"] = _tmp.name  # settings never touch the real profile
    app = QApplication.instance() or QApplication([])


class UiSmoke(unittest.TestCase):
    def setUp(self):
        # A fresh settings folder per test: a last_format saved by one test must not reach the next Window().
        fresh = tempfile.mkdtemp(dir=_tmp.name)
        env = mock.patch.dict(os.environ, {"APPDATA": fresh, "LOCALAPPDATA": fresh})
        env.start()
        self.addCleanup(env.stop)
        self.dir = Path(tempfile.mkdtemp(dir=_tmp.name))
        self.png = self.dir / "a.png"
        Image.new("RGB", (40, 30), "blue").save(self.png)
        self.win = ui.Window()

    def test_empty_state(self):
        self.assertEqual(self.win.fmt.count(), 0)
        self.assertFalse(self.win.go.isEnabled())

    def test_files_fill_formats_and_options(self):
        self.win.add_files([self.png])
        self.assertGreater(self.win.fmt.count(), 0)
        self.assertTrue(self.win.go.isEnabled())
        self.assertIsNotNone(self.win.fmt.currentData())  # a format is selected, not the "Add files first" placeholder
        self.assertEqual(self.win.fmt.currentIndex(), 0)
        self.assertIn("quality", self.win.opt_widgets)

    def test_window_height_follows_the_content_and_is_not_resizable(self):
        win = self.win
        win.show()
        sizes = []
        for n in (0, 1, 5, 13):
            win._clear()
            for i in range(n):
                p = self.dir / f"t{i}.png"
                p.write_bytes(self.png.read_bytes())
                win.files.append(str(p))
            win._refresh()
            QApplication.processEvents()
            self.assertEqual(win.minimumSize(), win.maximumSize())  # fixed: the user cannot drag it
            sizes.append(win.height())  # (width and exact heights depend on the fonts: offscreen has none)
        self.assertEqual(sorted(sizes), sizes)  # more files, never a smaller window
        self.assertEqual(win.list.height(), 228)  # 3 rows of tiles at most, then it scrolls
        win._clear()
        QApplication.processEvents()
        self.assertEqual(win.height(), sizes[0])  # back to the empty size, no leftover gap

    def test_bottom_row_message_takes_no_room_and_version_hides_with_result_buttons(self):
        win = self.win
        win.show()
        QApplication.processEvents()
        self.assertFalse(win.msg.isVisible())  # no gap under the progress bar while there is no message
        win.msg.setText("something")
        self.assertTrue(win.msg.isVisible())
        win.msg.setText("")
        self.assertFalse(win.msg.isVisible())
        self.assertEqual((win.clear.width(), win.clear.height()), (win.go.width(), win.go.height()))
        self.assertTrue(win.version.isVisible())
        self.assertEqual(win.version.text(), f"v{ui.CONVERT_VERSION}")
        win.open_btn.show()  # beside the version there is no room for the result buttons
        self.assertFalse(win.version.isVisible())
        win.open_btn.hide()
        self.assertTrue(win.version.isVisible())

    def test_advanced_toggle_keeps_the_option_names_visible(self):
        win = self.win
        win.show()
        win.add_files([self.png])
        QApplication.processEvents()
        fields = list(win.opt_widgets.values())
        labels = [win.form.labelForField(w) for w in fields]
        self.assertTrue(fields and all(l.isVisible() for l in labels))  # preview: names shown, fields hidden
        self.assertFalse(any(w.isVisible() for w in fields))
        for on in (True, False, True, False):  # switching on and off must not lose the names
            win.adv.setChecked(on)
            QApplication.processEvents()
            self.assertTrue(all(l.isVisible() for l in labels), f"labels lost after setChecked({on})")
            self.assertEqual([w.isVisible() for w in fields], [on] * len(fields))

    def test_progress_bar_goes_back_to_empty_on_clear_and_on_new_files(self):
        win = self.win
        win.add_files([self.png])
        win.bar.setRange(0, 1)
        win.bar.setValue(1)  # what _done leaves behind: a full bar
        win._clear()
        self.assertEqual(win.bar.value(), 0)
        win.add_files([self.png])
        win.bar.setValue(1)
        other = self.dir / "other.png"
        other.write_bytes(self.png.read_bytes())
        win.add_files([other])  # a new file starts a new batch
        self.assertEqual(win.bar.value(), 0)
        win.bar.setValue(1)
        win.add_files([])  # nothing added: the finished bar is left alone
        self.assertEqual(win.bar.value(), 1)

    def test_update_check_throttle_switch_and_notice(self):
        from unittest import mock
        from PySide6.QtCore import Qt
        from convert_win import settings, update_check as uc
        page = uc.PAGE_PREFIX + "tag/v9.9.9"
        win = self.win
        self.assertTrue(win.update_notice.isHidden())  # nothing to say: no room taken
        with mock.patch.object(uc, "fetch_latest", return_value=("v9.9.9", page)) as fetch:
            win.st["update_check"] = False  # switch off: no request at all
            self.assertFalse(win.start_update_check())
            win.st["update_check"], win.st["last_update_check"] = True, __import__("time").time() - 3600
            self.assertFalse(win.start_update_check())  # tried an hour ago
            fetch.assert_not_called()
            win.st["last_update_check"] = 0
            self.assertTrue(win.start_update_check())  # due: recorded first, then asked
            self.assertGreater(settings.load()["last_update_check"], 0)
            for _ in range(100):
                QApplication.processEvents()
                if not win.update_notice.isHidden():
                    break
                __import__("time").sleep(0.02)
            fetch.assert_called_once()
        self.assertFalse(win.update_notice.isHidden())
        self.assertEqual(win.update_notice.url, page)
        self.assertTrue(win.update_notice.alignment() & Qt.AlignRight)  # the notice sits on the right
        with mock.patch("convert_win.ui.webbrowser.open") as op:
            win.update_notice.show_for("https://evil.example/")  # refused: the old page stays
            self.assertEqual(win.update_notice.url, page)
            from PySide6.QtTest import QTest
            QTest.mouseClick(win.update_notice, Qt.LeftButton)
            op.assert_called_once_with(page)

    def test_failed_check_leaves_no_notice_and_still_counts(self):
        from unittest import mock
        from convert_win import settings, update_check as uc
        win = self.win
        win.st["update_check"], win.st["last_update_check"] = True, 0
        import threading
        asked = threading.Event()
        with mock.patch.object(uc, "fetch_latest", side_effect=lambda: asked.set()):  # returns None
            self.assertTrue(win.start_update_check())
            self.assertTrue(asked.wait(3))  # the worker ran; no fixed sleep
            QApplication.processEvents()
        self.assertTrue(win.update_notice.isHidden())
        self.assertFalse(uc.due(settings.load()["last_update_check"]))  # the attempt is on record

    def test_settings_keep_the_update_keys(self):
        from convert_win import settings
        st = settings.load()
        self.assertIs(st["update_check"], True)  # on by default
        st["update_check"], st["last_update_check"] = False, 123.5
        settings.save(st)
        back = settings.load()
        self.assertIs(back["update_check"], False)
        self.assertEqual(back["last_update_check"], 123.5)
        path = settings._dir("APPDATA") / "settings.json"
        path.write_text('{"update_check": "no", "last_update_check": "x"}')
        back = settings.load()
        self.assertIs(back["update_check"], False)  # anything but true is read as "off": the user tried to opt out
        self.assertEqual(back["last_update_check"], 0)
        for raw in ('"false"', "0", "null", "[]"):
            path.write_text('{"update_check": %s}' % raw)
            self.assertIs(settings.load()["update_check"], False, raw)
        path.write_text("{}")
        self.assertIs(settings.load()["update_check"], True)  # absent: on
        for raw in ("NaN", "Infinity", "-Infinity"):
            path.write_text('{"last_update_check": %s}' % raw)
            self.assertEqual(settings.load()["last_update_check"], 0, raw)
        st = settings.load()
        st["update_check"] = False
        settings.save(st)
        self.assertFalse(path.with_name("settings.json.tmp").exists())  # written through a temp file, then replaced
        self.assertIs(settings.load()["update_check"], False)

    def test_title_has_no_version(self):
        self.assertEqual(self.win.windowTitle(), "Convert")

    def test_empty_select_shows_the_placeholder(self):
        self.assertEqual(self.win.fmt.currentIndex(), -1)
        self.assertEqual(self.win.fmt.placeholderText(), "Add files first")

    def test_non_files_and_unsupported_ignored(self):
        exe = self.dir / "x.exe"
        exe.touch()
        self.win.add_files([exe, self.dir / "nope.png", self.dir])
        self.assertEqual(self.win.files, [])
        self.assertEqual(self.win.msg.text(),
                         f"Skipped (not a supported file type): x.exe, nope.png, {self.dir.name}")

    def test_video_file_offers_mp3_with_audio_options(self):
        mp4 = self.dir / "a.mp4"
        mp4.touch()
        self.win.add_files([mp4])
        ids = [self.win.fmt.itemData(i) for i in range(self.win.fmt.count())]
        self.assertEqual(ids[0], "mp4")
        self.win.fmt.setCurrentIndex(ids.index("mp3"))
        self.assertIn("bitrate", self.win.opt_widgets)
        self.assertIn("audio_track", self.win.opt_widgets)

    def test_mixed_kinds_offer_nothing(self):
        wav = self.dir / "a.wav"
        wav.touch()
        self.win.add_files([self.png, wav])
        self.assertEqual(self.win.fmt.count(), 0)

    def test_files_added_during_a_run_are_queued_then_added(self):  # S8
        other = self.dir / "b.png"
        Image.new("RGB", (4, 4)).save(other)
        self.win.worker = object()  # pretend a batch is running
        self.win.add_files([other])
        self.assertEqual(self.win.files, [])
        self.assertEqual(self.win.pending, [str(other)])
        self.win.worker = None

    def test_huge_saved_number_does_not_overflow_the_spin_box(self):  # reviewer finding 4
        self.win.st["options"]["image"]["quality"] = 2 ** 40
        self.win.add_files([self.png])
        self.win.fmt.setCurrentIndex(self.win.fmt.findData("webp"))
        self.win._build_options()
        self.assertEqual(self.win.opt_widgets["quality"].value(), 100)

    def test_convert_end_to_end_and_options_saved(self):
        self.win.add_files([self.png])
        self.win.fmt.setCurrentIndex(self.win.fmt.findData("webp"))
        self.win.opt_widgets["quality"].setValue(55)
        self.win._start()
        self.win.worker.wait(10000)
        app.processEvents()
        self.assertTrue((self.dir / "a.webp").exists())
        self.assertIn("Done", self.win.msg.text())
        self.assertEqual(ui.settings.load()["options"]["image"]["quality"], 55)

    def test_failure_is_reported_not_raised(self):
        bad = self.dir / "bad.png"
        bad.write_bytes(b"x")
        self.win.add_files([bad])
        self.win.fmt.setCurrentIndex(self.win.fmt.findData("jpg"))
        self.win._start()
        self.win.worker.wait(10000)
        app.processEvents()
        self.assertIn("failed", self.win.msg.text())

    def test_pipe_message_adds_files(self):
        self.assertFalse(ui._forward([str(self.png)]))  # nothing listening: first instance


if __name__ == "__main__":
    unittest.main()
