"""v0.1.16 window features: clickable drop box, removing files, drag highlight, skipped-files message, shortcuts, last format.

Offscreen like test_ui_smoke. No real file dialog (QFileDialog.getOpenFileNames is mocked), no fixed sleeps.
"""
import os
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from PIL import Image
from PySide6.QtCore import QEvent, QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDropEvent, QKeySequence, QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QSpinBox

from convert_win import settings, ui
from convert_win.formats import INPUTS, picker_filter

_tmp = tempfile.TemporaryDirectory()
app = None
FAKE_FFMPEG = r"C:\fake\ffmpeg.exe"  # never run: find_tool is mocked where a test needs ffmpeg listed
NO_FFMPEG_MSG = "ffmpeg not found. Install it (winget install Gyan.FFmpeg) and restart Convert."
MIXED_MSG = "These files cannot be converted together: pick files of one kind."


def setUpModule():
    global app
    os.environ["QT_QPA_PLATFORM"] = "offscreen"  # before the QApplication exists
    os.environ["APPDATA"] = os.environ["LOCALAPPDATA"] = _tmp.name
    app = QApplication.instance() or QApplication([])


class WindowCase(unittest.TestCase):
    """A fresh settings folder and a fresh Window per test; no worker is left running at the end."""

    def setUp(self):
        fresh = tempfile.mkdtemp(dir=_tmp.name)
        env = mock.patch.dict(os.environ, {"APPDATA": fresh, "LOCALAPPDATA": fresh})
        env.start()
        self.addCleanup(env.stop)
        self.dir = Path(tempfile.mkdtemp(dir=_tmp.name))
        self.win = ui.Window()
        self.addCleanup(self._close)

    def _close(self):
        self.win.worker = None
        self.win.close()

    def make(self, n, prefix="t"):
        paths = []
        for i in range(n):
            p = self.dir / f"{prefix}{i}.png"
            Image.new("RGB", (4, 4), "red").save(p)
            paths.append(p)
        return paths

    def show(self):
        self.win.show()
        self.win.activateWindow()
        QApplication.processEvents()
        return QTest.qWaitForWindowActive(self.win, 2000)

    def tile(self, row):
        r = self.win.list.visualRect(self.win.list.model().index(row, 0))
        self.assertGreater(r.width(), 0, "tile not laid out: the click test would pass for nothing")
        return r

    def x_point(self, row):
        """Centre of the × of a tile, worked out from the tile's edges (not from the code under test)."""
        t = self.tile(row).adjusted(3, 3, -3, -3)
        return QPoint(t.right() - 15, t.top() + 16)

    def click_viewport(self, pos):
        QTest.mouseClick(self.win.list.viewport(), Qt.LeftButton, Qt.NoModifier, pos)

    def fire(self, key):
        """Emit the window shortcut for `key` (works whether or not the window has the keyboard)."""
        hits = [s for s in self.win.shortcuts if s.key().toString() == QKeySequence(key).toString()]
        self.assertTrue(hits, f"no shortcut for {key}")
        for s in hits:
            s.activated.emit()


class PickerFilter(unittest.TestCase):
    def test_picker_filter_starts_with_supported_files(self):
        self.assertTrue(picker_filter().startswith("Supported files ("))

    def test_picker_filter_lists_every_input_extension_once(self):
        f = picker_filter()
        inner = f[f.index("(") + 1:f.rindex(")")]
        tokens = inner.split()
        self.assertEqual(len(tokens), len(set(tokens)), "an extension is listed twice")
        self.assertEqual(set(tokens), {f"*.{e}" for exts in INPUTS.values() for e in exts.split()})


class ClickableBox(WindowCase):
    """v0.1.16 final: no Add files button. A left click on empty space in the drop box opens the picker."""

    def setUp(self):
        super().setUp()
        self.show()

    def vp(self):
        return self.win.list.viewport()

    def picker(self, returns=([], "")):
        return mock.patch("convert_win.ui.QFileDialog.getOpenFileNames", return_value=returns)

    def with_files(self, n):
        self.win.add_files(self.make(n, "w"))
        QApplication.processEvents()
        self.assertEqual(len(self.win.files), n)

    def empty_point(self):
        """Bottom right of the box: the tiles fill from the top left, so this is empty space (checked)."""
        p = QPoint(self.vp().width() - 6, self.vp().height() - 6)
        self.assertFalse(self.win.list.indexAt(p).isValid(), "precondition: this point must be empty space")
        return p

    def move(self, pos):
        return QMouseEvent(QEvent.MouseMove, QPointF(pos), QPointF(self.vp().mapToGlobal(pos)),
                           Qt.NoButton, Qt.NoButton, Qt.NoModifier)

    def test_no_add_button_in_the_window(self):
        self.assertFalse(hasattr(self.win, "add"))
        self.assertNotIn("Add files", [b.text() for b in self.win.findChildren(QPushButton)])

    def test_click_on_empty_space_opens_picker_and_adds_the_chosen_files(self):
        chosen = self.make(2, "pick")
        with self.picker(([str(p) for p in chosen], "")) as dlg:
            self.click_viewport(self.empty_point())
        dlg.assert_called_once()
        self.assertEqual(dlg.call_args.args[3], picker_filter())
        self.assertEqual(self.win.files, [str(p) for p in chosen])

    def test_cancelled_picker_adds_nothing(self):
        with self.picker(([], "")) as dlg:
            self.click_viewport(self.empty_point())
        dlg.assert_called_once()
        self.assertEqual(self.win.files, [])

    def test_ctrl_o_is_wired_to_the_picker(self):
        chosen = self.make(1, "k")
        with self.picker(([str(chosen[0])], "")) as dlg:
            self.fire("Ctrl+O")
        dlg.assert_called_once()
        self.assertEqual(self.win.files, [str(chosen[0])])

    def test_ctrl_o_key_press_opens_the_picker(self):
        if not self.show():
            self.skipTest("offscreen window never became active: the key press cannot reach the shortcut here")
        with self.picker() as dlg:
            QTest.keyClick(self.win, Qt.Key_O, Qt.ControlModifier)
        dlg.assert_called_once()

    def test_windows_double_click_on_empty_space_opens_the_picker_once(self):
        p, vp = self.empty_point(), self.vp()
        with self.picker() as dlg:
            QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, p)
            QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, p)
            QApplication.sendEvent(vp, QMouseEvent(QEvent.MouseButtonDblClick, QPointF(p), QPointF(vp.mapToGlobal(p)),
                                                   Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
            QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, p)
        dlg.assert_called_once()

    def test_press_on_empty_space_and_release_on_a_tile_opens_nothing(self):
        self.with_files(2)
        tile = self.tile(0).center()
        with self.picker() as dlg:
            QTest.mousePress(self.vp(), Qt.LeftButton, Qt.NoModifier, self.empty_point())
            QTest.mouseRelease(self.vp(), Qt.LeftButton, Qt.NoModifier, tile)
        dlg.assert_not_called()
        self.assertEqual(len(self.win.files), 2)

    def test_press_on_a_tile_and_release_on_empty_space_opens_nothing(self):
        self.with_files(2)
        with self.picker() as dlg:
            QTest.mousePress(self.vp(), Qt.LeftButton, Qt.NoModifier, self.tile(0).center())
            QTest.mouseRelease(self.vp(), Qt.LeftButton, Qt.NoModifier, self.empty_point())
        dlg.assert_not_called()

    def test_click_on_a_tile_selects_it_and_opens_nothing(self):
        self.with_files(3)
        with self.picker() as dlg:
            self.click_viewport(self.tile(1).center())
        dlg.assert_not_called()
        self.assertEqual(self.win.list.currentRow(), 1)
        self.assertEqual(len(self.win.files), 3)

    def test_click_on_a_x_removes_the_file_and_opens_nothing(self):
        self.with_files(3)
        with self.picker() as dlg:
            self.click_viewport(self.x_point(1))
        dlg.assert_not_called()
        self.assertEqual(len(self.win.files), 2)

    def test_press_on_a_x_and_release_on_empty_space_removes_one_and_opens_nothing(self):
        self.with_files(2)
        with self.picker() as dlg:
            QTest.mousePress(self.vp(), Qt.LeftButton, Qt.NoModifier, self.x_point(0))
            QTest.mouseRelease(self.vp(), Qt.LeftButton, Qt.NoModifier, self.empty_point())
        dlg.assert_not_called()
        self.assertEqual(len(self.win.files), 1)  # the × press removed one file; the release did not open the picker

    def test_click_on_empty_space_while_a_batch_runs_queues_the_chosen_files(self):
        self.win.worker = object()  # a batch is running: the picker still opens, the files wait for the batch
        chosen = self.make(1, "q")
        with self.picker(([str(chosen[0])], "")) as dlg:
            self.click_viewport(self.empty_point())
        dlg.assert_called_once()
        self.assertEqual(self.win.files, [])
        self.assertEqual(self.win.pending, [str(chosen[0])])

    def test_cursor_is_pointing_hand_on_empty_space_and_arrow_on_a_tile(self):
        self.with_files(2)
        self.assertEqual(self.vp().cursor().shape(), Qt.PointingHandCursor)  # the empty-box cursor from the start
        self.win.list.mouseMoveEvent(self.move(self.empty_point()))
        self.assertEqual(self.vp().cursor().shape(), Qt.PointingHandCursor)
        self.win.list.mouseMoveEvent(self.move(self.tile(0).center()))
        self.assertEqual(self.vp().cursor().shape(), Qt.ArrowCursor)
        self.win.list.mouseMoveEvent(self.move(self.empty_point()))
        self.assertEqual(self.vp().cursor().shape(), Qt.PointingHandCursor)

    def test_tooltip_on_the_box_names_the_click_and_ctrl_o(self):
        self.assertEqual(self.win.list.toolTip(), "Click to add files (Ctrl+O)")

    def test_tile_tooltip_is_still_the_file_path(self):
        self.with_files(1)
        self.assertEqual(self.win.list.item(0).toolTip(), self.win.files[0])

    def test_empty_box_is_110_high_and_the_form_follows_it_with_no_widget_between(self):
        self.assertEqual(self.win.list.height(), 110)
        lay = self.win.layout()
        items = [lay.itemAt(i).widget() for i in range(lay.count())]
        nxt = items[items.index(self.win.list) + 1]
        self.assertIsInstance(nxt, QLabel)
        self.assertEqual(nxt.text(), "Convert to")


class RemoveOneFile(WindowCase):
    def setUp(self):
        super().setUp()
        self.files = self.make(4)
        self.win.add_files(self.files)
        self.show()

    def names(self):
        return [Path(f).name for f in self.win.files]

    def test_x_click_removes_only_that_file(self):
        self.click_viewport(self.x_point(1))
        self.assertEqual(self.names(), ["t0.png", "t2.png", "t3.png"])

    def test_click_on_the_tile_body_does_not_remove(self):
        self.click_viewport(self.tile(1).center())
        self.assertEqual(self.names(), ["t0.png", "t1.png", "t2.png", "t3.png"])
        self.assertEqual(self.win.list.currentRow(), 1)  # the click selects the tile instead

    def test_x_click_while_running_does_nothing(self):
        self.win.worker = object()
        self.click_viewport(self.x_point(0))
        self.assertEqual(len(self.win.files), 4)

    def test_delete_removes_the_selected_file_and_keeps_the_index(self):
        self.win.list.setFocus()
        self.win.list.setCurrentRow(1)
        QTest.keyClick(self.win.list, Qt.Key_Delete)
        self.assertEqual(self.names(), ["t0.png", "t2.png", "t3.png"])
        self.assertEqual(self.win.list.currentRow(), 1)  # the file that came after it is now selected

    def test_delete_of_the_last_file_selects_the_previous(self):
        self.win.list.setCurrentRow(3)
        QTest.keyClick(self.win.list, Qt.Key_Delete)
        self.assertEqual(self.names(), ["t0.png", "t1.png", "t2.png"])
        self.assertEqual(self.win.list.currentRow(), 2)

    def test_delete_without_a_selection_does_nothing(self):
        self.win.list.setCurrentRow(-1)
        QTest.keyClick(self.win.list, Qt.Key_Delete)
        self.assertEqual(len(self.win.files), 4)

    def test_delete_while_running_is_blocked(self):
        self.win.list.setCurrentRow(0)
        self.win.worker = object()
        QTest.keyClick(self.win.list, Qt.Key_Delete)
        self.assertEqual(len(self.win.files), 4)

    def test_removing_the_only_file_empties_the_window(self):
        self.win.files = self.win.files[:1]
        self.win._refresh()
        self.win.list.setCurrentRow(0)
        QTest.keyClick(self.win.list, Qt.Key_Delete)
        self.assertEqual(self.win.files, [])
        self.assertFalse(self.win.go.isEnabled())
        self.assertIsNone(self.win.list.currentItem())

    def test_window_height_shrinks_when_a_tile_row_goes(self):
        self.win.add_files(self.make(5, "u"))  # 9 files: 3 rows of tiles
        QApplication.processEvents()
        self.assertEqual(len(self.win.files), 9)
        self.assertEqual(self.win.list.height(), 228)
        tall = self.win.height()
        self.win.list.setCurrentRow(8)
        QTest.keyClick(self.win.list, Qt.Key_Delete)  # 8 files: 2 rows
        QApplication.processEvents()
        self.assertEqual(len(self.win.files), 8)
        self.assertEqual(self.win.list.height(), 158)
        self.assertEqual(tall - self.win.height(), 70)  # exactly the height of one row of tiles


class FormatAfterRemoval(WindowCase):
    def test_format_chosen_now_is_kept_when_still_offered(self):
        self.win.st["last_format"]["image"] = "jpg"  # a saved value must not win over the choice on screen
        a, b = self.make(2)
        self.win.add_files([a, b])  # two PNGs: PNG itself is not offered
        self.win.fmt.setCurrentIndex(self.win.fmt.findData("webp"))
        self.win._remove(0)
        self.assertEqual(self.win.fmt.currentData(), "webp")

    def test_not_offered_any_more_falls_back_to_the_saved_format(self):
        self.win.st["last_format"]["image"] = "webp"
        a = self.make(1)[0]
        b = self.dir / "b.jpg"
        Image.new("RGB", (4, 4), "red").save(b)
        self.win.add_files([a, b])
        self.win.fmt.setCurrentIndex(self.win.fmt.findData("png"))
        self.win._remove(1)  # only a PNG left: PNG is no longer offered
        self.assertEqual(self.win.fmt.currentData(), "webp")

    def test_not_offered_and_no_saved_format_falls_back_to_index_zero(self):
        a = self.make(1)[0]
        b = self.dir / "b.jpg"
        Image.new("RGB", (4, 4), "red").save(b)
        self.win.add_files([a, b])
        self.win.fmt.setCurrentIndex(self.win.fmt.findData("png"))
        self.win._remove(1)
        self.assertEqual(self.win.fmt.currentIndex(), 0)
        self.assertEqual(self.win.fmt.currentData(), self.win.fmt.itemData(0))
        self.assertEqual(self.win.fmt.currentData(), "jpg")


class DragHighlight(WindowCase):
    def mime(self, urls=None, text=None):
        m = QMimeData()  # kept in self so the event never points at a freed object
        self.m = m
        if urls is not None:
            m.setUrls([QUrl.fromLocalFile(str(u)) for u in urls])
        if text is not None:
            m.setText(text)
        return m

    def enter(self, m):
        self.win.dragEnterEvent(QDragEnterEvent(QPoint(10, 10), Qt.CopyAction, m, Qt.LeftButton, Qt.NoModifier))

    def test_highlight_set_on_enter_cleared_on_leave_and_on_drop(self):
        png = self.make(1)[0]
        self.assertFalse(self.win.list.property("drag"))
        self.enter(self.mime(urls=[png]))
        self.assertTrue(self.win.list.property("drag"))
        self.win.dragLeaveEvent(QDragLeaveEvent())
        self.assertFalse(self.win.list.property("drag"))
        self.enter(self.mime(urls=[png]))
        self.assertTrue(self.win.list.property("drag"))
        self.win.dropEvent(QDropEvent(QPointF(10, 10), Qt.CopyAction, self.mime(urls=[png]), Qt.LeftButton,
                                      Qt.NoModifier))
        self.assertFalse(self.win.list.property("drag"))
        self.assertEqual(self.win.files, [str(png)])

    def test_text_drag_is_not_highlighted(self):
        self.enter(self.mime(text="hello"))
        self.assertFalse(self.win.list.property("drag"))


class SkippedMessage(WindowCase):
    def test_names_are_listed_then_three_and_an_ellipsis(self):
        for n in ("a.exe", "b.exe", "c.exe", "d.exe"):
            (self.dir / n).touch()
        self.win.add_files([self.dir / n for n in ("a.exe", "b.exe", "c.exe", "d.exe")])
        self.assertEqual(self.win.msg.text(), "Skipped (not a supported file type): a.exe, b.exe, c.exe, ...")

    def test_folder_and_missing_file_are_named_too(self):
        self.win.add_files([self.dir, self.dir / "ghost.png"])
        self.assertEqual(self.win.msg.text(),
                         f"Skipped (not a supported file type): {self.dir.name}, ghost.png")
        self.assertFalse(self.win.msg.isHidden())  # the status line shows the message (window not shown here)

    def test_shown_in_the_muted_colour(self):
        (self.dir / "x.exe").touch()
        self.win.add_files([self.dir / "x.exe"])
        self.assertEqual(self.win.msg.objectName(), "muted")

    def test_cleared_by_the_next_add(self):
        (self.dir / "x.exe").touch()
        self.win.add_files([self.dir / "x.exe"])
        self.win.add_files(self.make(1))
        self.assertEqual(self.win.msg.text(), "")

    def test_cleared_by_remove(self):
        (self.dir / "x.exe").touch()
        self.win.add_files(self.make(1))
        self.win.add_files([self.dir / "x.exe"])
        self.win._remove(0)
        self.assertEqual(self.win.msg.text(), "")

    def test_cleared_by_clear(self):
        (self.dir / "x.exe").touch()
        self.win.add_files([self.dir / "x.exe"])
        self.win._clear()
        self.assertEqual(self.win.msg.text(), "")

    def test_cleared_when_convert_starts(self):
        (self.dir / "x.exe").touch()
        self.win.add_files(self.make(1))
        self.win.add_files([self.dir / "x.exe"])
        with mock.patch.object(ui, "Worker"):
            self.win._start()
            self.assertEqual(self.win.msg.text(), "")  # checked before any event is processed

    def test_ffmpeg_message_keeps_precedence(self):
        (self.dir / "x.exe").touch()
        mp4 = self.dir / "v.mp4"
        mp4.touch()
        with mock.patch.object(ui, "find_tool", return_value=None):
            self.win.add_files([mp4, self.dir / "x.exe"])
        self.assertEqual(self.win.msg.text(), NO_FFMPEG_MSG)

    def test_mixed_kinds_message_keeps_precedence(self):
        (self.dir / "x.exe").touch()
        wav = self.dir / "a.wav"
        wav.touch()
        with mock.patch.object(ui, "find_tool", return_value="ffmpeg"):
            self.win.add_files([self.make(1)[0], wav, self.dir / "x.exe"])
        self.assertEqual(self.win.msg.text(), MIXED_MSG)


class Shortcuts(WindowCase):
    def test_enter_starts_convert_when_convert_is_enabled(self):
        self.win.add_files(self.make(1))
        with mock.patch.object(self.win, "_start") as start:
            self.fire(Qt.Key_Return)
        start.assert_called_once()

    def test_enter_does_nothing_without_files(self):
        with mock.patch.object(self.win, "_start") as start:
            self.fire(Qt.Key_Return)
        start.assert_not_called()

    def test_enter_does_nothing_while_running(self):
        self.win.add_files(self.make(1))
        self.win.worker = object()
        with mock.patch.object(self.win, "_start") as start:
            self.win._enter()
        start.assert_not_called()

    def test_enter_in_a_spin_box_does_not_start(self):
        self.win.add_files(self.make(1))
        self.win.adv.setChecked(True)
        self.show()
        spin = next(w for w in self.win.opt_widgets.values() if isinstance(w, QSpinBox))
        spin.setFocus()
        QApplication.processEvents()
        self.assertIs(QApplication.focusWidget(), spin)  # the precondition: the focus really is in the spin box
        with mock.patch.object(self.win, "_start") as start:
            self.win._enter()
        start.assert_not_called()

    def test_esc_cancels_only_while_running(self):
        self.win.add_files(self.make(1))
        with mock.patch.object(self.win, "_cancel") as cancel:
            self.fire(Qt.Key_Escape)  # not running
            cancel.assert_not_called()
            self.win.worker = SimpleNamespace(cancel=threading.Event())
            self.win.stop.hide()  # the Cancel button is hidden: not a running batch that can be stopped
            self.fire(Qt.Key_Escape)
            cancel.assert_not_called()
            self.win.stop.show()
            self.fire(Qt.Key_Escape)
            cancel.assert_called_once()

    def test_esc_really_sets_the_cancel_flag(self):
        self.win.worker = SimpleNamespace(cancel=threading.Event())
        self.win.stop.show()
        self.fire(Qt.Key_Escape)
        self.assertTrue(self.win.worker.cancel.is_set())


class LastFormat(WindowCase):
    def setUp(self):
        super().setUp()
        # audio and video need ffmpeg to be offered: a fake path keeps the list (no ffmpeg runs, Worker is mocked)
        ff = mock.patch.object(ui, "find_tool", return_value=FAKE_FFMPEG)
        ff.start()
        self.addCleanup(ff.stop)
    def convert_with(self, paths, fid):
        """Select `paths`, pick `fid`, press Convert with the worker mocked (no real conversion)."""
        self.win._clear()
        self.win.add_files(paths)
        self.win.fmt.setCurrentIndex(self.win.fmt.findData(fid))
        with mock.patch.object(ui, "Worker"):
            self.win._start()
        self.win.worker = None

    def saved(self):
        return settings.load()["last_format"]

    def test_saved_per_file_type_on_convert(self):
        self.convert_with(self.make(1), "webp")
        self.assertEqual(self.win.st["last_format"], {"image": "webp"})
        self.assertEqual(self.saved(), {"image": "webp"})

    def test_video_saves_under_video(self):
        mp4 = self.dir / "v.mp4"
        mp4.touch()
        self.convert_with([mp4], "mp3")  # a video's sound track: an audio id, offered for video
        self.assertEqual(self.saved(), {"video": "mp3"})

    def test_audio_mixed_with_video_saves_under_audio(self):
        wav, mp4 = self.dir / "a.wav", self.dir / "v.mp4"
        wav.touch()
        mp4.touch()
        self.convert_with([wav, mp4], "flac")
        self.assertEqual(self.saved(), {"audio": "flac"})

    def test_each_type_keeps_its_own_entry(self):
        self.convert_with(self.make(1), "webp")
        mp4 = self.dir / "v.mp4"
        mp4.touch()
        self.convert_with([mp4], "webm")
        self.assertEqual(self.saved(), {"image": "webp", "video": "webm"})

    def test_saved_format_is_restored_when_offered(self):
        self.win.st["last_format"]["image"] = "webp"
        self.win.add_files(self.make(1))
        self.assertEqual(self.win.fmt.currentData(), "webp")

    def test_saved_format_survives_a_restart(self):
        self.convert_with(self.make(1), "tiff")
        again = ui.Window()
        self.addCleanup(again.close)
        again.add_files(self.make(1, "r"))
        self.assertEqual(again.fmt.currentData(), "tiff")

    def test_saved_format_not_offered_is_ignored_and_not_overwritten(self):
        self.win.st["last_format"]["image"] = "nosuch"
        self.win.add_files(self.make(1))
        self.assertEqual(self.win.fmt.currentIndex(), 0)
        self.assertEqual(self.win.st["last_format"]["image"], "nosuch")
        self.assertFalse((settings._dir("APPDATA") / "settings.json").exists())  # adding files writes nothing

    def load_with(self, last):
        path = settings._dir("APPDATA") / "settings.json"
        path.write_text(__import__("json").dumps({"last_format": last}), "utf-8")
        return settings.load()["last_format"]

    def test_load_drops_wrong_types_unknown_types_and_ids_not_offered(self):
        kept = self.load_with({"image": 5, "nosuchtype": "png", "doc": "png", "pdf": "nosuch", "gif": "png",
                               "audio": True})
        self.assertEqual(kept, {})
        self.assertEqual(self.load_with({"image": ["png"]}), {})
        self.assertEqual(self.load_with({"image": None}), {})

    def test_load_keeps_a_valid_id_and_drops_the_rest(self):
        self.assertEqual(self.load_with({"image": "webp", "doc": "docx"}), {"image": "webp", "doc": "docx"})

    def test_load_video_accepts_an_audio_id(self):
        self.assertEqual(self.load_with({"video": "mp3"}), {"video": "mp3"})

    def test_load_audio_does_not_accept_a_video_id(self):
        self.assertEqual(self.load_with({"audio": "mp4"}), {})

    def test_load_ignores_a_last_format_that_is_not_an_object(self):
        for raw in ("png", ["png"], 3, None):
            self.assertEqual(self.load_with(raw), {}, raw)


if __name__ == "__main__":
    unittest.main()
