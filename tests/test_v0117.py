"""v0.1.17 window features: per-file tile states, accessible names and descriptions, buddies, tab order,
the update notice from the keyboard, and the Open folder button (one folder, a menu of 2-8, more than 8).

Offscreen like test_v0116, set in setUpModule. Real Worker and real tiny PNG files (one corrupt) for the states.
send2trash, os.startfile, webbrowser.open and QFileDialog are mocked. No fixed sleeps: QTest.qWaitFor on a condition.
Classes are split: Harness is a helper (no tests); every other class is a unittest.TestCase.
"""
import os
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image
from PySide6.QtCore import QEvent, QEventLoop, Qt, QThread
from PySide6.QtGui import QColor, QKeyEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel

from convert_win import settings, theme, ui
from convert_win.process import Cancelled

_tmp = tempfile.TemporaryDirectory()
app = None
NOTICE_URL = "https://github.com/TheCreator0169/convert/releases/tag/v9.9.9"
FOREIGN_URL = "https://example.com/TheCreator0169/convert/releases/tag/v9.9.9"
WAIT = 20000  # ms: an upper bound for qWaitFor, not a sleep (returns as soon as the condition holds)


def wait_until(cond, timeout_ms=WAIT):
    """Polls `cond` while the event loop runs (queued signals from the worker thread are delivered here).
    Returns as soon as it holds; False at the timeout. Not a fixed sleep."""
    deadline = time.monotonic() + timeout_ms / 1000
    while not cond():
        if time.monotonic() > deadline:
            return False
        QApplication.processEvents(QEventLoop.AllEvents, 10)
        QThread.msleep(2)
    return True


def setUpModule():
    global app
    os.environ["QT_QPA_PLATFORM"] = "offscreen"  # before the QApplication exists; set for this process only
    os.environ["APPDATA"] = os.environ["LOCALAPPDATA"] = _tmp.name
    app = QApplication.instance() or QApplication([])


class Harness:
    """Helper, not a test class: a fresh settings folder, a fresh Window, no Recycle Bin, no real opener."""

    def setUp(self):
        super().setUp()
        fresh = tempfile.mkdtemp(dir=_tmp.name)
        env = mock.patch.dict(os.environ, {"APPDATA": fresh, "LOCALAPPDATA": fresh})
        env.start()
        self.addCleanup(env.stop)
        bin_ = mock.patch("convert_win.converter.send2trash")  # never the real Recycle Bin
        self.send2trash = bin_.start()
        self.addCleanup(bin_.stop)
        self.dir = Path(tempfile.mkdtemp(dir=_tmp.name))
        self.win = ui.Window()
        self.addCleanup(self._close)
        self.win.trash.setChecked(False)

    def _close(self):
        w = self.win.worker
        if isinstance(w, QThread):  # a real batch still running: stop it and wait, as closeEvent does
            w.cancel.set()
            w.wait(30000)
        self.win.worker = None
        self.win.close()

    def make(self, n, prefix="t"):
        paths = []
        for i in range(n):
            p = self.dir / f"{prefix}{i}.png"
            Image.new("RGB", (4, 4), "red").save(p)
            paths.append(p)
        return paths

    def make_bad(self, name, folder=None):
        """A file that has a .png name and is not an image: the real conversion fails on it."""
        folder = self.dir if folder is None else folder
        folder.mkdir(parents=True, exist_ok=True)
        p = folder / name
        p.write_bytes(b"this is not an image")
        return p

    def show(self):
        self.win.show()
        self.win.activateWindow()
        QApplication.processEvents()
        return QTest.qWaitForWindowActive(self.win, 2000)

    def run_batch(self):
        """Press Convert (the real Worker thread) and wait until the batch is over."""
        self.win._start()
        self.assertTrue(wait_until(lambda: self.win.worker is None, WAIT), "the batch did not finish")

    def item(self, row):
        return self.win.list.item(row)

    def state_of(self, row):
        return self.item(row).data(ui.STATE_ROLE)


class TileStates(Harness, unittest.TestCase):
    """Per-file states from the real Worker: waiting, working, done, failed. Keyed by full path."""

    def test_fresh_files_are_waiting_with_the_plain_path_as_tooltip(self):
        a, b = self.make(2)
        self.win.add_files([a, b])
        self.assertEqual([self.state_of(0), self.state_of(1)], ["waiting", "waiting"])
        self.assertEqual(self.item(0).toolTip(), str(a))
        self.assertEqual(self.item(0).data(Qt.AccessibleTextRole), "t0.png, PNG, waiting")

    def test_real_conversion_ends_done_and_the_tile_says_so(self):
        a = self.make(1)[0]
        self.win.add_files([a])
        self.win.fmt.setCurrentIndex(self.win.fmt.findData("webp"))
        self.run_batch()
        self.assertTrue((self.dir / "t0.webp").is_file(), "precondition: the real conversion wrote the file")
        self.assertEqual(self.state_of(0), "done")
        self.assertEqual(self.item(0).toolTip(), str(a))  # done has no extra line in the tooltip
        self.assertEqual(self.item(0).data(Qt.AccessibleTextRole), "t0.png, PNG, done")
        self.assertEqual(self.win.states, {str(a): "done"})

    def test_corrupt_file_ends_failed_with_path_and_message_in_the_tooltip(self):
        bad = self.make_bad("bad.png")
        self.win.add_files([bad])
        self.run_batch()
        self.assertEqual(self.state_of(0), "failed")
        msg = self.win.fail_msgs[str(bad)]
        self.assertTrue(msg, "the failure message must not be empty")
        self.assertEqual(self.item(0).toolTip(), f"{bad}\n{msg}")
        self.assertEqual(self.item(0).data(Qt.AccessibleTextRole), "bad.png, PNG, failed")

    def test_failure_message_is_the_one_listed_in_the_status_line(self):
        bad = self.make_bad("bad.png")
        self.win.add_files([bad])
        self.run_batch()
        msg = self.win.fail_msgs[str(bad)]
        self.assertIn(f"- bad.png: {msg}", self.win.msg.text())
        self.assertIn("0 file(s) written, 1 failed", self.win.msg.text())

    def test_working_state_is_shown_while_the_file_is_being_converted(self):
        a, b = self.make(2)
        self.win.add_files([a, b])
        gate = threading.Event()
        self.addCleanup(gate.set)  # never leave the worker blocked if an assertion fails
        real = ui.convert_file

        def gated(f, *args, **kw):
            if f == str(a):
                gate.wait(WAIT / 1000)  # held here until the test has seen the state
            return real(f, *args, **kw)

        with mock.patch.object(ui, "convert_file", side_effect=gated):
            self.win._start()
            self.assertTrue(wait_until(lambda: self.win.states.get(str(a)) == "working", WAIT))
            self.assertEqual(self.state_of(0), "working")
            self.assertEqual(self.item(0).toolTip(), str(a))
            self.assertEqual(self.win.states[str(b)], "waiting")  # not reached yet
            gate.set()
            self.assertTrue(wait_until(lambda: self.win.worker is None, WAIT))
        self.assertEqual(self.state_of(0), "done")
        self.assertEqual(self.state_of(1), "done")

    def test_same_name_failures_in_two_folders_are_told_apart_by_tooltip(self):
        bad1 = self.make_bad("bad.png", self.dir / "one")
        bad2 = self.make_bad("bad.png", self.dir / "two")
        self.win.add_files([bad1, bad2])
        self.run_batch()
        self.assertEqual([self.state_of(0), self.state_of(1)], ["failed", "failed"])
        tip1, tip2 = self.item(0).toolTip(), self.item(1).toolTip()
        self.assertNotEqual(tip1, tip2)
        self.assertTrue(tip1.startswith(f"{bad1}\n"), tip1)
        self.assertTrue(tip2.startswith(f"{bad2}\n"), tip2)
        self.assertEqual(set(self.win.states), {str(bad1), str(bad2)})  # two entries, not one per name

    def test_states_survive_a_rebuild_of_the_list(self):
        a, bad = self.make(1)[0], self.make_bad("bad.png")
        self.win.add_files([a, bad])
        self.run_batch()
        before = (self.state_of(0), self.state_of(1), self.item(1).toolTip())
        self.win._refresh()  # the list is cleared and rebuilt from the states
        self.assertEqual((self.state_of(0), self.state_of(1), self.item(1).toolTip()), before)
        self.assertEqual(self.state_of(1), "failed")
        self.assertIn(str(bad), self.win.fail_msgs)

    def test_convert_again_resets_every_tile_to_waiting(self):
        bad = self.make_bad("bad.png")
        self.win.add_files([bad])
        self.run_batch()
        self.assertEqual(self.state_of(0), "failed")
        with mock.patch.object(ui, "Worker"):
            self.win._start()
            self.assertEqual(self.state_of(0), "waiting")  # checked before any event is processed
            self.assertEqual(self.item(0).toolTip(), str(bad))
            self.assertEqual(self.win.fail_msgs, {})
        self.win.worker = None

    def test_clear_resets_states_and_a_re_added_file_waits(self):
        bad = self.make_bad("bad.png")
        self.win.add_files([bad])
        self.run_batch()
        self.win._clear()
        self.assertEqual(self.win.states, {})
        self.assertEqual(self.win.fail_msgs, {})
        self.win.add_files([bad])
        self.assertEqual(self.state_of(0), "waiting")  # the old failure is not shown again

    def test_removing_a_file_drops_only_its_state_and_the_others_keep_theirs(self):
        bad = self.make_bad("bad.png")
        a = self.make(1)[0]
        self.win.add_files([a, bad])
        self.run_batch()
        self.win._remove(0)  # the good file goes; the failed one moves to row 0 and keeps its state
        self.assertEqual(self.win.files, [str(bad)])
        self.assertEqual(self.state_of(0), "failed")
        self.assertEqual(self.win.states, {str(bad): "failed"})
        self.assertNotIn(str(a), self.win.states)
        self.win._remove(0)
        self.assertNotIn(str(bad), self.win.fail_msgs)

    def test_cancel_leaves_the_interrupted_and_unreached_files_waiting(self):
        a, b, c = self.make(3)

        def fake_convert(f, fid, opts, trash, cancel, notes):
            name = Path(f).name
            if name == "t0.png":
                return [Path(f).with_suffix(".webp")]
            if name == "t1.png":  # the user presses Cancel while this file is being converted
                cancel.set()
                raise Cancelled()
            raise AssertionError("t2 must not be reached after Cancel")

        self.win.add_files([a, b, c])
        with mock.patch.object(ui, "convert_file", side_effect=fake_convert):
            self.run_batch()
        self.assertEqual([self.state_of(0), self.state_of(1), self.state_of(2)], ["done", "waiting", "waiting"])
        self.assertEqual(self.win.msg.text(), "Cancelled.")
        self.assertNotIn("working", self.win.states.values())

    def test_trash_option_removes_the_converted_tiles_and_keeps_the_failed_one(self):
        self.win.trash.setChecked(True)
        ok, bad = self.make(1, "ok")[0], self.make_bad("bad.png")
        self.send2trash.side_effect = lambda p: Path(p).unlink()  # stands in for the Recycle Bin
        self.win.add_files([ok, bad])
        self.run_batch()
        self.send2trash.assert_called_once_with(os.path.abspath(ok))
        self.assertFalse(ok.exists())
        self.assertEqual(self.win.files, [str(bad)])
        self.assertEqual(self.win.states, {str(bad): "failed"})
        self.assertEqual(self.item(0).data(Qt.AccessibleTextRole), "bad.png, PNG, failed")

    def test_progress_and_converted_and_failed_carry_the_batch_index(self):
        a, bad, b = self.make(1, "ok")[0], self.make_bad("bad.png"), self.make(2, "z")[1]
        w = ui.Worker([str(a), str(bad), str(b)], "webp", settings.load()["options"], False)
        progress, converted, failed, done = [], [], [], []
        w.progress.connect(lambda i, n: progress.append((i, n)))
        w.converted.connect(lambda i: converted.append(i))
        w.failed.connect(lambda i, m: failed.append((i, m)))
        w.done.connect(lambda outs, errs, notes: done.append((len(outs), errs)))
        w.run()  # synchronous on this thread: the signals are delivered at once
        self.assertEqual(progress, [(0, "ok0.png"), (1, "bad.png"), (2, "z1.png")])
        self.assertEqual(converted, [0, 2])
        self.assertEqual([i for i, _ in failed], [1])
        self.assertTrue(failed[0][1])
        self.assertEqual(done[0][0], 2)
        self.assertEqual([n for n, _ in done[0][1]], ["bad.png"])

    def test_worker_stopped_before_it_starts_converts_nothing(self):
        a = self.make(1)[0]
        w = ui.Worker([str(a)], "webp", settings.load()["options"], False)
        progress, converted, done = [], [], []
        w.progress.connect(lambda i, n: progress.append(i))
        w.converted.connect(lambda i: converted.append(i))
        w.done.connect(lambda outs, errs, notes: done.append((outs, errs)))
        w.cancel.set()
        w.run()
        self.assertEqual((progress, converted), ([], []))
        self.assertTrue(w.cancelled)
        self.assertEqual(done, [([], [])])


class UpdateNoticeKeys(Harness, unittest.TestCase):
    """The update notice is a label that can be reached and opened by keyboard. Only the release page of this project opens."""

    def setUp(self):
        super().setUp()
        self.show()
        self.notice = self.win.update_notice
        self.opener = mock.patch("convert_win.ui.webbrowser.open").start()
        self.addCleanup(mock.patch.stopall)

    def test_accessible_name_and_description_as_in_the_code(self):
        self.assertEqual(self.notice.accessibleName(), "A new version is available")
        self.assertEqual(self.notice.accessibleDescription(), "Press Enter to open the release page.")

    def test_hidden_with_no_focus_until_a_safe_page_is_given(self):
        self.assertTrue(self.notice.isHidden())
        self.assertEqual(self.notice.focusPolicy(), Qt.NoFocus)
        self.notice.show_for(NOTICE_URL)
        self.assertFalse(self.notice.isHidden())
        self.assertNotEqual(self.notice.focusPolicy(), Qt.NoFocus)  # reachable by Tab while it is shown

    def test_focus_policy_goes_back_to_no_focus_when_hidden(self):
        self.notice.show_for(NOTICE_URL)
        self.notice.hide()
        self.assertEqual(self.notice.focusPolicy(), Qt.NoFocus)

    def test_foreign_or_odd_addresses_are_refused_and_nothing_shows(self):
        for url in (FOREIGN_URL, "", None, 5, "https://github.com/TheCreator0169/convert/releasesX/tag/v1",
                    "http://github.com/TheCreator0169/convert/releases/tag/v1"):
            self.notice.show_for(url)
            self.assertTrue(self.notice.isHidden(), repr(url))
            self.assertEqual(self.notice.url, "", repr(url))
        self.assertEqual(self.notice.focusPolicy(), Qt.NoFocus)

    def test_enter_opens_the_release_page_through_webbrowser(self):
        self.notice.show_for(NOTICE_URL)
        QTest.keyClick(self.notice, Qt.Key_Return)
        self.opener.assert_called_once_with(NOTICE_URL)

    def test_keypad_enter_opens_the_page_too(self):
        self.notice.show_for(NOTICE_URL)
        QTest.keyClick(self.notice, Qt.Key_Enter)
        self.opener.assert_called_once_with(NOTICE_URL)

    def test_space_opens_the_page_too(self):
        self.notice.show_for(NOTICE_URL)
        QTest.keyClick(self.notice, Qt.Key_Space)
        self.opener.assert_called_once_with(NOTICE_URL)

    def test_enter_on_the_notice_does_not_start_convert(self):
        self.win.add_files(self.make(1))
        self.assertTrue(self.win.go.isEnabled(), "precondition: Convert would be enabled")
        self.notice.show_for(NOTICE_URL)
        with mock.patch.object(self.win, "_start") as start:
            QTest.keyClick(self.notice, Qt.Key_Return)
        start.assert_not_called()
        self.opener.assert_called_once_with(NOTICE_URL)

    def test_window_shortcut_override_for_enter_is_accepted_by_the_notice(self):
        self.notice.show_for(NOTICE_URL)
        ev = QKeyEvent(QEvent.ShortcutOverride, Qt.Key_Return, Qt.NoModifier)
        QApplication.sendEvent(self.notice, ev)
        self.assertTrue(ev.isAccepted())

    def test_other_keys_and_plain_text_do_nothing(self):
        self.notice.show_for(NOTICE_URL)
        QTest.keyClick(self.notice, Qt.Key_A)
        QTest.keyClick(self.notice, Qt.Key_Tab)
        self.opener.assert_not_called()

    def test_a_click_opens_the_page_as_before(self):
        self.notice.show_for(NOTICE_URL)
        QTest.mouseClick(self.notice, Qt.LeftButton, Qt.NoModifier, self.notice.rect().center())
        self.opener.assert_called_once_with(NOTICE_URL)

    def test_url_replaced_by_a_foreign_one_is_not_opened(self):
        self.notice.show_for(NOTICE_URL)
        self.notice.url = FOREIGN_URL  # _open checks the address again, not only show_for
        QTest.keyClick(self.notice, Qt.Key_Return)
        self.opener.assert_not_called()

    def test_focus_outline_is_drawn_only_while_the_notice_has_focus(self):
        self.notice.show_for(NOTICE_URL)
        accent = QColor(theme.PALETTE["accent"]).name()
        self.notice.setFocus()
        QApplication.processEvents()
        if not self.notice.hasFocus():
            self.skipTest("offscreen window did not give the label the focus here: outline not checked")
        img = self.notice.grab().toImage()
        self.assertEqual(QColor.fromRgba(img.pixel(0, img.height() // 2)).name(), accent)  # the 1 px outline, left edge
        self.notice.clearFocus()
        QApplication.processEvents()
        img = self.notice.grab().toImage()
        self.assertNotEqual(QColor.fromRgba(img.pixel(0, img.height() // 2)).name(), accent)


class TabOrderAndBuddies(Harness, unittest.TestCase):
    """The Tab key is walked with QWidget.focusNextChild, so the order is what a keyboard user gets.
    The expected order is written here from the spec; hidden and non-focusable widgets are left out of it."""

    def setUp(self):
        super().setUp()
        self.show()  # the Tab walk needs the window active and the widgets visible

    def spec(self):
        w = self.win
        return [w.update_notice, w.list, w.fmt, w.adv, *w.opt_widgets.values(), w.trash, w.clear, w.logs_btn,
                w.open_btn, w.stop, w.go]

    def reachable(self):
        return [w for w in self.spec() if w.isVisible() and w.isEnabled() and w.focusPolicy() != Qt.NoFocus]

    def tab_from(self, start, steps):
        """Focus `start`, then press Tab `steps` times; the widget that has the focus after each press."""
        start.setFocus()
        QApplication.processEvents()
        if QApplication.focusWidget() is not start:
            self.skipTest("offscreen window did not give the focus here: the Tab walk is not checked")
        seen = []
        for _ in range(steps):
            self.win.focusNextChild()
            seen.append(QApplication.focusWidget())
        return seen

    def assert_walk(self, expect):
        seen = self.tab_from(self.win.update_notice, len(expect) - 1)
        self.assertEqual([type(w).__name__ for w in seen], [type(w).__name__ for w in expect[1:]])
        self.assertEqual([id(w) for w in seen], [id(w) for w in expect[1:]])

    def test_tab_walks_notice_list_format_trash_clear_convert_when_no_files(self):
        self.win.update_notice.show_for(NOTICE_URL)
        # no file listed: Advanced is hidden and Convert is disabled, so Tab stops at neither
        self.assertEqual(self.reachable(), [self.win.update_notice, self.win.list, self.win.fmt,
                                            self.win.trash, self.win.clear])
        self.assert_walk(self.reachable())

    def test_tab_walks_the_option_fields_when_advanced_is_open(self):
        self.win.add_files(self.make(1))
        self.assertGreater(len(self.win.opt_widgets), 0, "precondition: the image group has option fields")
        self.win.update_notice.show_for(NOTICE_URL)
        self.win.adv.setChecked(True)
        QApplication.processEvents()
        expect = self.reachable()
        self.assertTrue(all(w in expect for w in self.win.opt_widgets.values()), "the option fields are not reached")
        self.assert_walk(expect)

    def test_tab_order_is_the_same_after_the_option_fields_are_rebuilt(self):
        self.win.add_files(self.make(1))
        self.win.update_notice.show_for(NOTICE_URL)
        self.win.adv.setChecked(True)
        QApplication.processEvents()
        self.win.fmt.setCurrentIndex(self.win.fmt.findData("jpg"))  # new option fields
        QApplication.processEvents()
        self.assert_walk(self.reachable())

    def test_the_notice_is_not_reached_by_tab_while_hidden(self):
        self.win.add_files(self.make(1))
        self.assertNotIn(self.win.update_notice, self.reachable())
        self.assertNotIn(self.win.update_notice, self.tab_from(self.win.list, 3))

    def test_format_label_is_a_buddy_of_the_format_box(self):
        self.assertIs(self.win.fmt_label.buddy(), self.win.fmt)

    def test_every_option_row_label_is_the_buddy_of_its_field(self):
        self.win.add_files(self.make(1))
        self.assertGreater(len(self.win.opt_widgets), 0)
        for key, w in self.win.opt_widgets.items():
            self.assertIs(self.win.form.labelForField(w).buddy(), w, key)

    def test_no_label_has_an_ampersand_so_no_mnemonic_is_made(self):
        self.win.add_files(self.make(1))
        for lbl in self.win.findChildren(QLabel):
            self.assertNotIn("&", lbl.text(), repr(lbl.text()))


class AccessibleNames(Harness, unittest.TestCase):
    """Each name and description exactly as set in Window.__init__ and UpdateNotice.__init__."""

    def test_drop_box_name_and_description(self):
        self.assertEqual(self.win.list.accessibleName(), "Files to convert")
        self.assertEqual(self.win.list.accessibleDescription(),
                         "Drop files here or click an empty area to add files. Ctrl+O also adds files. "
                         "Select a file and press Delete to remove it.")

    def test_format_box_name_and_description(self):
        self.assertEqual(self.win.fmt.accessibleName(), "Convert to")
        self.assertEqual(self.win.fmt.accessibleDescription(), "Output format")

    def test_advanced_group_name(self):
        self.assertEqual(self.win.adv.accessibleName(), "Advanced")

    def test_progress_bar_name(self):
        self.assertEqual(self.win.bar.accessibleName(), "Conversion progress")

    def test_convert_button_name_and_description(self):
        self.assertEqual(self.win.go.accessibleName(), "Convert")
        self.assertEqual(self.win.go.accessibleDescription(), "Convert the listed files to the chosen format")

    def test_cancel_button_name_and_description(self):
        self.assertEqual(self.win.stop.accessibleName(), "Cancel")
        self.assertEqual(self.win.stop.accessibleDescription(), "Stop after the current file")

    def test_open_folder_button_name_and_description(self):
        self.assertEqual(self.win.open_btn.accessibleName(), "Open folder")
        self.assertEqual(self.win.open_btn.accessibleDescription(), "Open the folder with the converted files")

    def test_open_log_folder_button_name_and_description(self):
        self.assertEqual(self.win.logs_btn.accessibleName(), "Open log folder")
        self.assertEqual(self.win.logs_btn.accessibleDescription(), "Open the folder with the log file")

    def test_clear_button_name_and_description(self):
        self.assertEqual(self.win.clear.accessibleName(), "Clear")
        self.assertEqual(self.win.clear.accessibleDescription(), "Remove all files from the list")

    def test_update_notice_name_and_description(self):
        self.assertEqual(self.win.update_notice.accessibleName(), "A new version is available")
        self.assertEqual(self.win.update_notice.accessibleDescription(), "Press Enter to open the release page.")

    def test_option_fields_are_named_by_their_label(self):
        self.win.add_files(self.make(1))
        self.assertGreater(len(self.win.opt_widgets), 0)
        for key, w in self.win.opt_widgets.items():
            self.assertEqual(w.accessibleName(), ui.LABEL[key], key)


class OpenFolder(Harness, unittest.TestCase):
    """Open folder: one folder opens directly; 2-8 folders a menu with the full paths; more than 8 the first 8 and a count."""

    def setUp(self):
        super().setUp()
        self.show()
        self.startfile = mock.patch("convert_win.ui.os.startfile").start()
        self.popup = mock.patch.object(ui.QMenu, "popup").start()
        self.addCleanup(mock.patch.stopall)

    def folders(self, n):
        """Output files in n different folders. The folders exist: the window lists only folders that are there."""
        out = []
        for i in range(n):
            (self.dir / f"out{i}").mkdir(exist_ok=True)
            out.append(str(self.dir / f"out{i}" / f"x{i}.webp"))
        return out

    def menu_texts(self):
        return [a.text() for a in self.win.folder_menu.actions()]

    def test_no_output_means_nothing_happens(self):
        self.win._open_folder()
        self.startfile.assert_not_called()
        self.popup.assert_not_called()

    def test_one_folder_opens_directly_without_a_menu(self):
        self.win.outs = self.folders(1) + [str(self.dir / "out0" / "again.webp")]
        self.win._open_folder()
        self.startfile.assert_called_once_with(str(self.dir / "out0"))
        self.popup.assert_not_called()

    def test_two_folders_show_a_menu_with_full_paths_and_open_nothing_yet(self):
        self.win.outs = self.folders(2)
        self.win._open_folder()
        self.popup.assert_called_once()
        self.startfile.assert_not_called()
        self.assertEqual(self.menu_texts(), [str(self.dir / "out0"), str(self.dir / "out1")])

    def test_choosing_an_entry_opens_that_folder(self):
        self.win.outs = self.folders(3)
        self.win._open_folder()
        self.win.folder_menu.actions()[1].trigger()
        self.startfile.assert_called_once_with(str(self.dir / "out1"))

    def test_eight_folders_are_all_listed_and_no_more_line(self):
        self.win.outs = self.folders(8)
        self.win._open_folder()
        self.popup.assert_called_once()
        self.assertEqual(len(self.win.folder_menu.actions()), 8)
        self.assertFalse(any("more" in t for t in self.menu_texts()))

    def test_nine_folders_show_eight_and_a_disabled_one_more_line(self):
        self.win.outs = self.folders(9)
        self.win._open_folder()
        acts = self.win.folder_menu.actions()
        self.assertEqual(len(acts), 9)
        self.assertEqual([a.text() for a in acts[:8]], [str(self.dir / f"out{i}") for i in range(8)])
        self.assertEqual(acts[8].text(), "... and 1 more")
        self.assertFalse(acts[8].isEnabled())

    def test_twelve_folders_say_four_more_and_the_line_cannot_be_chosen(self):
        self.win.outs = self.folders(12)
        self.win._open_folder()
        acts = self.win.folder_menu.actions()
        self.assertEqual(len(acts), 9)
        self.assertEqual(acts[8].text(), "... and 4 more")
        self.assertFalse(acts[8].isEnabled())

    def test_an_ampersand_in_a_folder_name_is_shown_not_taken_as_a_mnemonic(self):
        ampersand = str(self.dir / "R&D")
        (self.dir / "R&D").mkdir()
        (self.dir / "plain").mkdir()
        self.win.outs = [str(Path(ampersand) / "a.webp"), str(self.dir / "plain" / "b.webp")]
        self.win._open_folder()
        self.assertEqual(self.win.folder_menu.actions()[0].text(), ampersand.replace("&", "&&"))

    def test_the_same_folder_twice_counts_once(self):
        (self.dir / "same").mkdir()
        self.win.outs = [str(self.dir / "same" / "a.webp"), str(self.dir / "same" / "b.webp")]
        self.win._open_folder()
        self.startfile.assert_called_once_with(str(self.dir / "same"))
        self.popup.assert_not_called()

    def test_real_batch_writing_to_two_folders_offers_the_menu(self):
        a = self.make(1, "a")[0]
        (self.dir / "second").mkdir()
        b = self.dir / "second" / "b.png"
        Image.new("RGB", (4, 4), "blue").save(b)
        self.win.add_files([a, b])
        self.win.fmt.setCurrentIndex(self.win.fmt.findData("webp"))
        self.run_batch()
        self.assertEqual(self.win.open_btn.isHidden(), False)
        self.win._open_folder()
        self.popup.assert_called_once()
        self.assertEqual(self.menu_texts(), [str(self.dir), str(self.dir / "second")])

    def test_enter_on_the_focused_button_shows_the_menu_and_does_not_start_convert(self):
        self.win.add_files(self.make(1))
        self.assertTrue(self.win.go.isEnabled(), "precondition: Convert would be enabled")
        self.win.outs = self.folders(2)
        self.win.open_btn.show()
        with mock.patch.object(self.win, "_start") as start:
            QTest.keyClick(self.win.open_btn, Qt.Key_Return)
        self.popup.assert_called_once()
        start.assert_not_called()
        self.startfile.assert_not_called()

    def test_enter_on_the_focused_button_is_not_passed_on_as_the_window_shortcut(self):
        self.win.outs = self.folders(2)
        self.win.open_btn.show()
        ev = QKeyEvent(QEvent.ShortcutOverride, Qt.Key_Enter, Qt.NoModifier)
        QApplication.sendEvent(self.win.open_btn, ev)
        self.assertTrue(ev.isAccepted())

    def test_enter_on_the_button_with_one_folder_opens_it(self):
        self.win.outs = self.folders(1)
        self.win.open_btn.show()
        QTest.keyClick(self.win.open_btn, Qt.Key_Return)
        self.startfile.assert_called_once_with(str(self.dir / "out0"))
        self.popup.assert_not_called()

    def test_a_folder_that_is_gone_is_left_out_so_one_left_opens_directly(self):
        self.win.outs = self.folders(2)
        shutil.rmtree(self.dir / "out1")  # removed after the batch
        self.win._open_folder()
        self.startfile.assert_called_once_with(str(self.dir / "out0"))
        self.popup.assert_not_called()

    def test_when_every_output_folder_is_gone_the_status_line_says_so(self):
        self.win.outs = self.folders(2)
        shutil.rmtree(self.dir / "out0")
        shutil.rmtree(self.dir / "out1")
        self.win._open_folder()
        self.startfile.assert_not_called()
        self.popup.assert_not_called()
        self.assertEqual(self.win.msg.text(), "The output folder no longer exists.")

    def test_open_button_is_hidden_until_a_batch_writes_something(self):
        self.assertTrue(self.win.open_btn.isHidden())
        self.win.add_files(self.make(1))
        self.run_batch()
        self.assertFalse(self.win.open_btn.isHidden())


class ReviewFixes(Harness, unittest.TestCase):
    """Defects found by the reviewer of v0.1.17: Clear during a run, Enter on a focused button, a stale tile index."""

    def setUp(self):
        super().setUp()
        self.png = self.dir / "a.png"
        Image.new("RGB", (8, 8), "red").save(self.png)
        self.win.add_files([self.png])

    def test_clear_is_ignored_while_a_batch_runs(self):
        self.win.worker = object()  # pretend a batch is running
        try:
            self.win._clear()
            self.assertEqual(self.win.files, [str(self.png)])
        finally:
            self.win.worker = None

    def test_enter_on_a_focused_clear_button_does_not_start_convert(self):
        self.win.show()
        self.win.clear.setFocus()
        QApplication.processEvents()
        with mock.patch.object(self.win, "_start") as start:
            self.win._enter()
            start.assert_not_called()

    def test_enter_still_starts_convert_from_the_list(self):
        self.win.show()
        self.win.list.setFocus()
        QApplication.processEvents()
        with mock.patch.object(self.win, "_start") as start:
            self.win._enter()
            start.assert_called_once()

    def test_a_state_change_for_a_row_that_is_gone_is_ignored(self):
        self.win._set_state(5, "working")  # no such row: no IndexError
        self.win.files = []
        self.win._refresh()
        self.win._set_state(0, "done")

    def test_the_notice_takes_focus_from_tab_only_not_from_a_click(self):
        self.win.show()  # the focus policy is set when the notice is really shown
        self.win.update_notice.show_for(NOTICE_URL)
        QApplication.processEvents()
        self.assertEqual(self.win.update_notice.focusPolicy(), Qt.TabFocus)

    def test_a_missing_output_folder_is_not_opened(self):
        self.win.outs = [str(self.dir / "gone" / "a.webp")]
        with mock.patch("convert_win.ui.os.startfile") as op:
            self.win._open_folder()
            op.assert_not_called()
        self.assertIn("no longer exists", self.win.msg.text())


    def test_the_state_word_is_painted_inside_the_tile_body(self):
        """The tile body is the 88x64 item rect inset by 3 px: its bottom edge is row 61. The word must sit above it."""
        from PySide6.QtCore import QRect
        from PySide6.QtGui import QImage, QPainter
        from PySide6.QtWidgets import QStyleOptionViewItem
        item = self.win.list.item(0)
        item.setData(ui.STATE_ROLE, "waiting")
        img = QImage(88, 64, QImage.Format_RGB32)
        img.fill(QColor("#ff00ff"))  # a colour nothing else uses
        opt = QStyleOptionViewItem()
        opt.rect = QRect(0, 0, 88, 64)
        opt.font = self.win.font()
        p = QPainter(img)
        ui.TileDelegate(self.win.list).paint(p, opt, self.win.list.indexFromItem(item))
        p.end()
        body = QColor(theme.PALETTE["tile"]).rgb()
        magenta = QColor("#ff00ff").rgb()
        outside = [img.pixel(x, y) for y in range(61, 64) for x in range(88)] + [img.pixel(x, y) for y in range(0, 64) for x in (0, 1, 2)]
        self.assertTrue(all(c == magenta for c in outside), "something is painted outside the tile body")
        word_rows = {y for y in range(45, 57) for x in range(8, 80) if img.pixel(x, y) not in (body, magenta)}
        self.assertTrue(word_rows, "no state word inside the body, below the name")
        self.assertLess(max(word_rows), 58)


if __name__ == "__main__":
    unittest.main()
