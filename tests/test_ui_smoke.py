import os
import tempfile
import unittest
from pathlib import Path

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

    def test_empty_select_shows_the_placeholder(self):
        self.assertEqual(self.win.fmt.currentIndex(), -1)
        self.assertEqual(self.win.fmt.placeholderText(), "Add files first")

    def test_non_files_and_unsupported_ignored(self):
        exe = self.dir / "x.exe"
        exe.touch()
        self.win.add_files([exe, self.dir / "nope.png", self.dir])
        self.assertEqual(self.win.files, [])

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
