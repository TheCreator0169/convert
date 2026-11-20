"""v0.2.3 path refusals (converter._refusal), the message per refusal kind, the lossy .doc warning in the log and notes,
and the scheme-change handler for a window that is not built yet.

Nothing here touches the network or a share: GetDriveTypeW is replaced by a mock in every test that gives a drive letter,
and Path.is_file is replaced where a refused path must never reach the disk. The .doc tests build their own file (helpers
imported from tests.test_v022; that module's TestCase classes are not imported, so they do not run twice).
Test classes: RefusalKinds, ConvertFileRefusals, LossyWarning, SchemeChanged, AuditFixes.
"""
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from PySide6.QtWidgets import QApplication

from convert_win import converter, doc_conv, ui
from convert_win.converter import convert_file
from convert_win.formats import DEFAULTS
from tests.test_v022 import WARNING, Files, make_doc, write

app = None
DEFAULTS_OPTS = {k: dict(v) for k, v in DEFAULTS.items()}
REAL_DRIVE_TYPE = converter._drive_type  # kept before any test patches it

PROBES = {
    "network": [
        r"\\server\share\a.png",
        r"\\?\UNC\server\share\a.png",
        r"\\?\unc\server\share\a.png",
        "//?/UNC/server/share/a.png",
        "//server/share/a.png",
    ],
    "device": [
        r"\\?\GLOBALROOT\Device\HarddiskVolumeShadowCopy1\a.png",
        r"\\?\Global\C:\a.png",
        r"\\??\C:\a.png",
        r"\\.\C:\a.png",
        r"\\.\PhysicalDrive0",
        "//./C:/a.png",
    ],
    "unsupported": [
        r"\\?\PhysicalDrive0",
        r"\\?\PIPE\x\a.png",
        r"\\?\Volume{1234}\x.png",
    ],
}

ALLOWED = [
    r"C:\a.png",
    r"\\?\C:\x",
    r"\\?\Volume{12345678-1234-1234-1234-123456789012}\x",
    r"\\wsl$\Ubuntu\a.png",
    r"\\wsl.localhost\Ubuntu\a.png",
]

MALFORMED_GUID = [
    r"\\?\Volume{12345678-1234-1234-1234-12345678901}\x",     # 35 characters
    r"\\?\Volume{1234567G-1234-1234-1234-123456789012}\x",    # not hex
    r"\\?\Volume12345678-1234-1234-1234-123456789012\x",      # no braces
]

MESSAGES = {
    "network": "network (UNC) paths are not supported: a.png",
    "device": "device paths are not supported: a.png",
    "unsupported": "this kind of path is not supported: a.png",
    "remote": "mapped network drive paths are not supported: a.png",
}


def setUpModule():
    global app
    app = QApplication.instance() or QApplication([])


class RefusalKinds(unittest.TestCase):
    """_refusal: which kind each path gets. _drive_type is mocked to 3 (local) unless a test says otherwise."""

    def setUp(self):
        self.drive = mock.patch.object(converter, "_drive_type", return_value=3).start()
        self.addCleanup(mock.patch.stopall)

    def test_network_paths_are_refused_as_network(self):
        for p in PROBES["network"]:
            with self.subTest(p=p):
                self.assertEqual(converter._refusal(p), "network")
                self.assertTrue(converter._is_network_path(p))

    def test_device_paths_are_refused_as_device(self):
        for p in PROBES["device"]:
            with self.subTest(p=p):
                self.assertEqual(converter._refusal(p), "device")

    def test_other_extended_paths_are_refused_as_unsupported(self):
        for p in PROBES["unsupported"]:
            with self.subTest(p=p):
                self.assertEqual(converter._refusal(p), "unsupported")

    def test_malformed_volume_guid_is_refused(self):
        for p in MALFORMED_GUID:
            with self.subTest(p=p):
                self.assertEqual(converter._refusal(p), "unsupported")

    def test_allowed_paths(self):
        for p in ALLOWED:
            with self.subTest(p=p):
                self.assertIsNone(converter._refusal(p))
                self.assertFalse(converter._is_network_path(p))

    def test_mapped_network_drive_is_refused_when_drive_type_is_4(self):
        self.drive.return_value = 4
        for p in (r"Z:\a.png", r"\\?\Z:\a.png", "z:/a.png"):
            with self.subTest(p=p):
                self.assertEqual(converter._refusal(p), "remote")
                self.assertTrue(converter._is_network_path(p))

    def test_drive_type_3_and_unknown_are_allowed(self):
        for value in (3, "unknown"):
            self.drive.return_value = value
            for p in (r"Z:\a.png", r"\\?\Z:\a.png"):
                with self.subTest(value=value, p=p):
                    self.assertIsNone(converter._refusal(p))

    def test_drive_type_is_asked_only_for_drive_letters(self):
        self.drive.return_value = 4
        for p in PROBES["network"] + PROBES["device"] + PROBES["unsupported"] + [r"\\wsl$\Ubuntu\a.png"]:
            converter._refusal(p)
        self.assertEqual(self.drive.call_count, 0, "a UNC, device or WSL path must not ask the drive type")
        converter._refusal(r"\\?\Z:\a.png")
        self.drive.assert_called_once_with("Z")

    def test_drive_type_failure_reads_as_unknown(self):
        with mock.patch("ctypes.WinDLL", side_effect=OSError("no kernel32")):
            self.assertEqual(REAL_DRIVE_TYPE("Z"), "unknown")


class ConvertFileRefusals(unittest.TestCase):
    """convert_file raises ValueError before the disk is touched; the allowed paths get as far as the file check."""

    def setUp(self):
        mock.patch.object(converter, "_drive_type", return_value=3).start()
        self.addCleanup(mock.patch.stopall)

    def test_message_per_kind(self):
        cases = {
            "network": r"\\server\share\a.png",
            "device": r"\\.\C:\a.png",
            "unsupported": r"\\?\PhysicalDrive0\a.png",
        }
        for kind, raw in cases.items():
            with self.subTest(kind=kind), \
                    mock.patch.object(Path, "is_file", side_effect=AssertionError("touched the disk")):
                with self.assertRaises(ValueError) as cm:
                    convert_file(raw, "png", DEFAULTS_OPTS)
                self.assertEqual(str(cm.exception), MESSAGES[kind])

    def test_mapped_drive_message(self):
        mock.patch.object(converter, "_drive_type", return_value=4).start()
        with mock.patch.object(Path, "is_file", side_effect=AssertionError("touched the disk")):
            with self.assertRaises(ValueError) as cm:
                convert_file(r"Z:\a.png", "png", DEFAULTS_OPTS)
        self.assertEqual(str(cm.exception), MESSAGES["remote"])

    def test_refused_paths_never_touch_the_disk(self):
        for kind in PROBES:
            for raw in PROBES[kind]:
                with self.subTest(raw=raw), \
                        mock.patch.object(Path, "is_file", side_effect=AssertionError("touched the disk")):
                    with self.assertRaises(ValueError):
                        convert_file(raw, "png", DEFAULTS_OPTS)

    def test_allowed_paths_pass_the_refusal_and_stop_at_the_file_check(self):
        for raw in ALLOWED:
            with self.subTest(raw=raw), mock.patch.object(Path, "is_file", return_value=False) as is_file:
                with self.assertRaises(FileNotFoundError) as cm:
                    convert_file(raw, "png", DEFAULTS_OPTS)
                self.assertEqual(str(cm.exception), f"not a file: {Path(raw).name}")
                is_file.assert_called_once()


class LossyWarning(Files, unittest.TestCase):
    """A .doc converted to text or PDF loses formatting: the warning is logged (folder scrubbed) and kept in notes."""

    def sample(self):
        return write(self.dir, "report.doc", make_doc([("c", "Hello doc\r")]))

    def test_warning_is_logged_without_the_folder(self):
        src = self.sample()
        notes = []
        with self.assertLogs("convert", level="WARNING") as cm:
            convert_file(src, "txt", self.opts, notes=notes)
        self.assertEqual(cm.output, [f"WARNING:convert:report.doc: {WARNING}"])
        self.assertNotIn(str(self.dir), "\n".join(cm.output))

    def test_warning_is_in_notes(self):
        src = self.sample()
        notes = []
        with self.assertLogs("convert", level="WARNING"):
            convert_file(src, "pdf", self.opts, notes=notes)
        self.assertIn(f"report.doc: {WARNING}", notes)

    def test_folder_is_scrubbed_from_the_logged_warning_but_not_from_notes(self):
        src = self.dir / "report.doc"
        folder = str(self.dir)
        doubled = folder.replace("\\", "\\\\")
        warn = f"plain {folder}\\part.bin and repr {doubled}\\part.bin"

        def fake(s, dst, fmt, opts, cancel):
            dst.write_text("text", "utf-8")
            return warn

        src.write_bytes(b"not really a doc: doc_conv.convert is replaced")
        notes = []
        with mock.patch.object(doc_conv, "convert", side_effect=fake), \
                self.assertLogs("convert", level="WARNING") as cm:
            convert_file(src, "txt", self.opts, notes=notes)
        logged = cm.records[-1].getMessage()
        self.assertEqual(logged, f"report.doc: plain ...\\part.bin and repr ...\\part.bin")
        self.assertNotIn(folder, logged)
        self.assertNotIn(doubled, logged)
        self.assertIn(f"report.doc: {warn}", notes)


class SchemeChanged(unittest.TestCase):
    """_on_scheme_changed: a window that is not built yet is ignored; "system" follows Windows, a fixed choice does not."""

    def setUp(self):
        self.palette = mock.patch.object(ui, "_refresh_palette").start()
        self.repaint = mock.patch.object(ui, "_repaint").start()
        self.addCleanup(mock.patch.stopall)

    def test_window_without_st_is_ignored(self):
        ui._on_scheme_changed(None, SimpleNamespace())
        self.palette.assert_not_called()
        self.repaint.assert_not_called()

    def test_window_with_system_theme_is_refreshed(self):
        ui._on_scheme_changed(None, SimpleNamespace(st={"theme": "system"}))
        self.palette.assert_called_once_with(None, "system")
        self.repaint.assert_called_once()

    def test_fixed_theme_ignores_the_change(self):
        ui._on_scheme_changed(None, SimpleNamespace(st={"theme": "dark"}))
        self.palette.assert_not_called()
        self.repaint.assert_not_called()


class AuditFixes(unittest.TestCase):
    """Found by the v0.2.3 audit: Unicode upper-casing and relative names."""

    def test_long_s_does_not_pass_as_wsl(self):
        # U+017F upper-cases to "S" with str.upper(): the WSL exemption must be ASCII only
        bs = "\\"
        self.assertEqual(converter._refusal(bs * 2 + "wſl$" + bs + "x.png"), "network")
        self.assertEqual(converter._refusal(bs * 2 + "wsl$" + bs + "Ubuntu" + bs + "x.png"), None)

    def test_relative_name_is_resolved_before_the_check(self):
        bs = "\\"
        with mock.patch("os.path.abspath", return_value=bs * 2 + "server" + bs + "share" + bs + "a.png"):
            self.assertEqual(converter._refusal("a.png"), "network")
            self.assertTrue(converter._is_network_path("a.png"))


if __name__ == "__main__":
    unittest.main()
