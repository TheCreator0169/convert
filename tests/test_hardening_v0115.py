"""v0.1.15 hardening: unpacked-size and image caps, tool lookup, UNC refusal, settings clamps, pipe size limit, edge cases.
Inputs are generated in a temp folder; APPDATA and LOCALAPPDATA point there too. No network is used."""
import base64
import io
import json
import os
import struct
import subprocess
import tempfile
import unittest
import uuid
import zipfile
from pathlib import Path
from unittest import mock

import docx
from PIL import Image

from convert_win import converter, doc_conv, ffmpeg_conv, image_conv, process, settings
from convert_win.converter import convert_file
from convert_win.formats import DEFAULTS

TEXT = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
TABLE = "urn:oasis:names:tc:opendocument:xmlns:table:1.0"
OFFICE = "urn:oasis:names:tc:opendocument:xmlns:office:1.0"
STYLE = "urn:oasis:names:tc:opendocument:xmlns:style:1.0"
FO = "urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0"
DRAW = "urn:oasis:names:tc:opendocument:xmlns:drawing:1.0"
XLINK = "http://www.w3.org/1999/xlink"


def make_png(path, size=(4, 4), color="blue"):
    Image.new("RGB", size, color).save(path)
    return path


def png_bytes(size=(2, 2)):
    buf = io.BytesIO()
    Image.new("RGB", size, "red").save(buf, "PNG")
    return buf.getvalue()


def make_odt(path, body, pictures=None):
    xml = (f'<?xml version="1.0"?><office:document-content xmlns:office="{OFFICE}" xmlns:text="{TEXT}" '
           f'xmlns:table="{TABLE}" xmlns:draw="{DRAW}" xmlns:xlink="{XLINK}" xmlns:fo="{FO}" xmlns:style="{STYLE}">'
           f"<office:body><office:text>{body}</office:text></office:body></office:document-content>")
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/vnd.oasis.opendocument.text")
        z.writestr("content.xml", xml)
        for name, data in (pictures or {}).items():
            z.writestr(name, data)
    return path


def picture(name):
    return f'<text:p><draw:frame><draw:image xlink:href="{name}"/></draw:frame></text:p>'


class Files:
    """Helper mixin (not a test class): a temp folder, a temp profile, and the Recycle Bin replaced by a list."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        env = mock.patch.dict(os.environ, {"APPDATA": self.tmp.name, "LOCALAPPDATA": self.tmp.name})
        env.start()
        self.addCleanup(env.stop)
        self.opts = {k: {**v} for k, v in DEFAULTS.items()}
        self.trashed = []
        p = mock.patch.object(converter, "send2trash", lambda s: self.trashed.append(s))
        p.start()
        self.addCleanup(p.stop)

    def names(self):
        return sorted(p.name for p in self.dir.iterdir())


class DocUnpackedCap(Files, unittest.TestCase):
    def test_docx_over_the_unpacked_limit_is_refused_without_output(self):
        src = self.dir / "a.docx"
        d = docx.Document()
        d.add_paragraph("hello docx")
        d.save(src)
        with mock.patch.object(doc_conv, "MAX_UNZIPPED", 10):
            with self.assertRaisesRegex(RuntimeError, "too large when unpacked"):
                convert_file(src, "txt", self.opts, trash_original=True)
        self.assertEqual(self.names(), ["a.docx"])
        self.assertEqual(self.trashed, [])

    def test_odt_over_the_unpacked_limit_is_refused_without_output(self):
        src = make_odt(self.dir / "a.odt", "<text:p>hi</text:p>")
        with mock.patch.object(doc_conv, "MAX_UNZIPPED", 10):
            with self.assertRaisesRegex(RuntimeError, "too large when unpacked"):
                convert_file(src, "txt", self.opts, trash_original=True)
        self.assertEqual(self.names(), ["a.odt"])
        self.assertEqual(self.trashed, [])

    def test_normal_docx_and_odt_still_convert(self):
        d = docx.Document()
        d.add_paragraph("hello docx")
        d.save(self.dir / "a.docx")
        make_odt(self.dir / "b.odt", "<text:p>hello odt</text:p>")
        (out_docx,) = convert_file(self.dir / "a.docx", "txt", self.opts)
        (out_odt,) = convert_file(self.dir / "b.odt", "txt", self.opts)
        self.assertIn("hello docx", out_docx.read_text("utf-8"))
        self.assertIn("hello odt", out_odt.read_text("utf-8"))


class OdtImageBudget(Files, unittest.TestCase):
    def test_budget_exhausted_fails_loudly_and_writes_nothing(self):
        refs = "".join(picture("Pictures/p.png") for _ in range(10))
        src = make_odt(self.dir / "many.odt", refs, {"Pictures/p.png": png_bytes()})
        with mock.patch.object(doc_conv, "MAX_ODT_IMAGE_HTML", 500):
            with self.assertRaisesRegex(RuntimeError, "too many or too large images"):
                convert_file(src, "txt", self.opts, trash_original=True)
        self.assertEqual(self.names(), ["many.odt"])
        self.assertEqual(self.trashed, [])

    def test_default_budget_converts_a_picture_used_many_times(self):
        refs = "".join(picture("Pictures/p.png") for _ in range(10))
        src = make_odt(self.dir / "many.odt", refs + "<text:p>end</text:p>", {"Pictures/p.png": png_bytes()})
        (out,) = convert_file(src, "txt", self.opts)
        self.assertIn("end", out.read_text("utf-8"))

    def test_text_box_gives_a_warning_and_keeps_the_original(self):
        body = ('<text:p>before</text:p><draw:frame><draw:text-box><text:p>boxed</text:p></draw:text-box></draw:frame>')
        src = make_odt(self.dir / "box.odt", body)
        notes = []
        (out,) = convert_file(src, "txt", self.opts, trash_original=True, notes=notes)
        self.assertTrue(out.exists())
        self.assertTrue(any("text boxes may not be carried over in full" in n for n in notes), notes)
        self.assertTrue(any("original kept" in n for n in notes), notes)
        self.assertEqual(self.trashed, [])


class ImagePixelCap(Files, unittest.TestCase):
    def test_image_over_the_pixel_limit_is_refused_without_output(self):
        src = make_png(self.dir / "big.png", (20, 10))  # 200 pixels
        with mock.patch.object(image_conv, "MAX_IMAGE_PIXELS", 100):
            with self.assertRaisesRegex(RuntimeError, "image too large"):
                convert_file(src, "jpg", self.opts, trash_original=True)
        self.assertEqual(self.names(), ["big.png"])
        self.assertEqual(self.trashed, [])

    def test_image_exactly_at_the_limit_converts(self):
        src = make_png(self.dir / "edge.png", (10, 10))  # 100 pixels
        with mock.patch.object(image_conv, "MAX_IMAGE_PIXELS", 100):
            (out,) = convert_file(src, "jpg", self.opts)
        self.assertTrue(out.exists())


class ToolLookup(Files, unittest.TestCase):
    def test_bat_is_not_a_tool_only_exe_is(self):
        tools = self.dir / "tools"
        tools.mkdir()
        (tools / "fake.bat").write_text("@echo off\r\n", "ascii")
        with mock.patch.dict(os.environ, {"PATH": str(tools)}):
            self.assertIsNone(process.find_tool("fake"))
            (tools / "fake.exe").write_bytes(b"MZ")
            self.assertEqual(Path(process.find_tool("fake")).name, "fake.exe")


class NetworkPaths(Files, unittest.TestCase):
    def test_unc_paths_are_refused_before_any_file_access(self):
        for raw in (r"\\server\share\a.png", "//server/share/a.png", "\\\\?\\UNC\\server\\share\\a.png"):
            # a regression must fail here, not reach a network lookup: is_file() raises the moment it is called
            with self.subTest(raw=raw), mock.patch.object(Path, "is_file", side_effect=AssertionError("file system touched")):
                with self.assertRaisesRegex(ValueError, r"network \(UNC\) paths are not supported"):
                    convert_file(raw, "jpg", self.opts)

    def test_local_path_still_converts(self):
        src = make_png(self.dir / "local.png")
        (out,) = convert_file(src, "jpg", self.opts)
        self.assertTrue(out.exists())


class SettingsLimits(Files, unittest.TestCase):
    def write(self, data):
        (self.dir / "Convert").mkdir(exist_ok=True)
        (self.dir / "Convert" / "settings.json").write_text(json.dumps(data), "utf-8")

    def test_out_of_range_numbers_are_clamped(self):
        self.write({"options": {"audio": {"bitrate": 9999}, "gif": {"fps": 0}, "video": {"height": 999}}})
        o = settings.load()["options"]
        self.assertEqual(o["audio"]["bitrate"], 512)
        self.assertEqual(o["gif"]["fps"], 1)
        self.assertEqual(o["video"]["height"], DEFAULTS["video"]["height"])

    def test_numbers_below_range_are_clamped_up_and_top_end_clamped_down(self):
        self.write({"options": {"audio": {"bitrate": 1}, "video": {"fps": 500}, "gif": {"width": 10}}})
        o = settings.load()["options"]
        self.assertEqual(o["audio"]["bitrate"], 32)
        self.assertEqual(o["video"]["fps"], 120)
        self.assertEqual(o["gif"]["width"], 64)

    def test_update_check_is_on_only_for_a_real_true(self):
        cases = [({}, True), ({"update_check": True}, True), ({"update_check": False}, False),
                 ({"update_check": "true"}, False), ({"update_check": 1}, False), ({"update_check": None}, False)]
        for data, expected in cases:
            with self.subTest(data=data):
                self.write(data)
                self.assertIs(settings.load()["update_check"], expected)

    def test_last_check_time_must_be_a_finite_number(self):
        for raw in ('{"last_update_check": NaN}', '{"last_update_check": Infinity}',
                    '{"last_update_check": true}', '{"last_update_check": "soon"}'):
            with self.subTest(raw=raw):
                (self.dir / "Convert").mkdir(exist_ok=True)
                (self.dir / "Convert" / "settings.json").write_text(raw, "utf-8")
                self.assertEqual(settings.load()["last_update_check"], 0)


def wait_for(cond, ms=10000):
    """Helper: pump the Qt event loop until cond() is true or the deadline passes. Returns cond()."""
    import time

    from PySide6.QtTest import QTest
    deadline = time.monotonic() + ms / 1000
    while not cond() and time.monotonic() < deadline:
        QTest.qWait(10)
    return cond()


class FakeWindow:
    """Helper: stands in for ui.Window in ui.run; records the files the pipe hands over."""
    def __init__(self):
        self.files = []

    def add_files(self, paths):
        self.files.extend(paths)

    def show(self):
        pass

    showNormal = raise_ = activateWindow = start_update_check = show


class FakeApp:
    """Helper: stands in for QApplication in ui.run; its event loop is the test's drive() function."""
    def __init__(self, real, drive):
        self.real, self.drive = real, drive

    def setStyleSheet(self, css):
        self.real.setStyleSheet(css)

    def exec(self):
        self.drive()
        return 0


def pipe_session(drive, server_cls=None):
    """Helper: runs ui.run with a real local server under a unique pipe name. drive(send, window) is the client side:
    send(payload) connects, writes and disconnects. server_cls replaces QLocalServer (to watch the sockets it hands out).
    Returns (ui.run's exit code, the FakeWindow)."""
    from PySide6.QtNetwork import QLocalServer, QLocalSocket
    from PySide6.QtWidgets import QApplication

    from convert_win import ui

    with mock.patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}):  # no window is shown
        real = QApplication.instance() or QApplication([])
    name = f"Convert-test-{uuid.uuid4().hex}"
    window = FakeWindow()

    def send(payload):
        # the server runs in this same thread, so every wait pumps events (wait_for) to let it read
        s = QLocalSocket()
        s.connectToServer(name)
        if not s.waitForConnected(5000):
            raise AssertionError("the pipe did not accept the connection")
        s.write(payload)
        wait_for(lambda: s.bytesToWrite() == 0 or s.state() == QLocalSocket.UnconnectedState)
        s.disconnectFromServer()
        wait_for(lambda: s.state() == QLocalSocket.UnconnectedState)

    with mock.patch.object(ui, "PIPE", name), mock.patch.object(ui, "claim_first", lambda name=None: True), \
            mock.patch.object(ui, "QApplication", lambda argv: FakeApp(real, lambda: drive(send, window))), \
            mock.patch.object(ui, "Window", lambda: window), \
            mock.patch.object(ui, "QLocalServer", server_cls or QLocalServer):
        code = ui.run([])
    return code, window


class PipeLimit(unittest.TestCase):
    def test_oversized_pipe_message_is_dropped_and_the_next_one_still_works(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        good = str(make_png(Path(tmp.name) / "good.png"))

        def drive(send, window):
            send(json.dumps(["C:\\bad\\" + "x" * ((1 << 20) + 10) + ".png"]).encode())  # just over the 1 MiB limit, a literal on purpose
            send(json.dumps([good]).encode())
            wait_for(lambda: window.files)

        code, window = pipe_session(drive)
        self.assertEqual(code, 0)
        self.assertEqual(window.files, [good])

    def test_incoming_socket_buffers_at_most_one_byte_past_the_limit(self):
        from PySide6.QtNetwork import QLocalServer

        from convert_win import ui

        sockets = []
        sizes = []

        class Recording(QLocalServer):
            def nextPendingConnection(self):
                c = super().nextPendingConnection()
                sockets.append(c)  # keep the socket the server hands out, to read its buffer size while it is alive
                return c

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        good = str(make_png(Path(tmp.name) / "good.png"))

        def drive(send, window):
            send(json.dumps([good]).encode())
            wait_for(lambda: window.files)
            sizes.extend(s.readBufferSize() for s in sockets)  # read inside the run, not after ui.run has returned

        code, window = pipe_session(drive, server_cls=Recording)
        self.assertEqual(code, 0)
        self.assertEqual(window.files, [good])
        self.assertEqual(len(sockets), 1)
        self.assertEqual(sizes, [ui.MAX_MESSAGE + 1])


class EdgeCases(Files, unittest.TestCase):
    def test_missing_ffmpeg_is_a_clear_error_and_writes_nothing(self):
        src = self.dir / "song.mp3"
        src.write_bytes(b"not really audio")
        with mock.patch.object(ffmpeg_conv, "find_tool", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "ffmpeg not found"):
                convert_file(src, "wav", self.opts, trash_original=True)
        self.assertEqual(self.names(), ["song.mp3"])
        self.assertEqual(self.trashed, [])

    def test_read_only_output_folder_fails_clearly_and_keeps_the_original(self):
        ro = self.dir / "readonly"
        ro.mkdir()
        src = make_png(ro / "a.png")
        # Windows ignores the read-only attribute on folders, so deny write and add-file for Everyone (folder only)
        probe = ro / "probe.txt"
        self.addCleanup(lambda: subprocess.run(["icacls", str(ro), "/remove:d", "*S-1-1-0"], capture_output=True))
        subprocess.run(["icacls", str(ro), "/deny", "*S-1-1-0:(WD,AD)"], check=True, capture_output=True)
        try:
            probe.write_text("x")
        except OSError:
            pass
        else:
            self.skipTest("this folder is still writable after icacls deny: no clean way to test it here")
        with self.assertRaises(OSError):
            convert_file(src, "jpg", self.opts, trash_original=True)
        self.assertTrue(src.exists())
        self.assertEqual(self.trashed, [])
        self.assertEqual(sorted(p.name for p in ro.iterdir()), ["a.png"])

    def test_zero_byte_image_fails_clearly_and_keeps_the_original(self):
        src = self.dir / "empty.png"
        src.write_bytes(b"")
        with self.assertRaisesRegex(OSError, "cannot identify image file"):
            convert_file(src, "jpg", self.opts, trash_original=True)
        self.assertEqual(self.names(), ["empty.png"])
        self.assertEqual(self.trashed, [])

    def test_zero_byte_text_converts_without_a_crash(self):
        src = self.dir / "empty.txt"
        src.write_bytes(b"")
        (out,) = convert_file(src, "html", self.opts)
        self.assertGreater(out.stat().st_size, 0)

    def test_non_ascii_and_200_character_names_convert(self):
        for stem in ("\u00e9\u65e5\u672c\u8a9e", "a" * 200):
            with self.subTest(stem=stem[:12]):
                src = make_png(self.dir / f"{stem}.png")
                (out,) = convert_file(src, "jpg", self.opts)
                self.assertEqual(out.name, f"{stem}.jpg")
                self.assertTrue(out.exists())


class DocxPictureOnce(Files, unittest.TestCase):
    def make_docx(self, uses):
        pic = make_png(self.dir / "p.png", (2, 2))
        d = docx.Document()
        for _ in range(uses):  # one picture part, referenced by a run per use
            d.add_paragraph().add_run().add_picture(str(pic))
        path = self.dir / "pics.docx"
        d.save(path)
        with zipfile.ZipFile(path) as z:
            (media,) = [n for n in z.namelist() if n.startswith("word/media/")]
            blob = z.read(media)
        return path, blob

    def test_picture_used_many_times_is_encoded_once_and_shown_each_time(self):
        src, blob = self.make_docx(10)
        real = base64.b64encode
        encoded = []

        def spy(data, *a, **k):
            encoded.append(bytes(data))
            return real(data, *a, **k)

        with mock.patch.object(base64, "b64encode", spy):
            (out,) = convert_file(src, "html", self.opts)
        self.assertEqual(sum(1 for d in encoded if d == blob), 1)
        self.assertEqual(out.read_text("utf-8").count("<img"), 10)

    def test_docx_picture_budget_exhausted_fails_loudly_and_writes_nothing(self):
        src, _ = self.make_docx(10)
        with mock.patch.object(doc_conv, "MAX_ODT_IMAGE_HTML", 500):
            with self.assertRaisesRegex(RuntimeError, "too many or too large images"):
                convert_file(src, "txt", self.opts, trash_original=True)
        self.assertEqual(self.names(), ["p.png", "pics.docx"])
        self.assertEqual(self.trashed, [])


class ZipReadLimits(Files, unittest.TestCase):
    def test_stdlib_zip_read_chunk_is_capped_at_16_mb(self):
        self.assertEqual(zipfile.ZipExtFile.MAX_N, 1 << 24)

    def test_member_holding_more_than_its_declared_size_is_refused(self):
        # content.xml is stored (5 MB real bytes) but its headers declare 1000 bytes: the read must not return the bloat
        big = b"<x>" + b"a" * 5_000_000 + b"</x>"
        path = self.dir / "lie.odt"
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("mimetype", "application/vnd.oasis.opendocument.text")
            z.writestr("content.xml", big, compress_type=zipfile.ZIP_STORED)
        data = bytearray(path.read_bytes())
        local = data.index(b"content.xml") - 30  # the local file header starts 30 bytes before its name
        self.assertEqual(bytes(data[local:local + 4]), b"PK\x03\x04")
        central = data.rindex(b"PK\x01\x02")  # the last central directory entry is content.xml
        self.assertEqual(bytes(data[central + 46:central + 57]), b"content.xml")
        struct.pack_into("<I", data, local + 22, 1000)  # uncompressed size, local header
        struct.pack_into("<I", data, central + 24, 1000)  # uncompressed size, central directory
        path.write_bytes(bytes(data))
        with self.assertRaises((zipfile.BadZipFile, RuntimeError)):
            convert_file(path, "txt", self.opts, trash_original=True)
        self.assertEqual(self.names(), ["lie.odt"])
        self.assertEqual(self.trashed, [])


class ImageFrames(Files, unittest.TestCase):
    def make_tiff(self, second=(30, 30)):
        path = self.dir / "two.tif"
        Image.new("RGB", (10, 10), "red").save(path, save_all=True,
                                               append_images=[Image.new("RGB", second, "blue")])
        return path

    def test_second_frame_over_the_pixel_limit_is_refused_without_output(self):
        src = self.make_tiff()  # first frame 10x10 (100 pixels), second 30x30 (900)
        with mock.patch.object(image_conv, "MAX_IMAGE_PIXELS", 100):
            with self.assertRaisesRegex(RuntimeError, "image too large"):
                convert_file(src, "gif", self.opts, trash_original=True)
        self.assertEqual(self.names(), ["two.tif"])
        self.assertEqual(self.trashed, [])

    def test_every_frame_within_the_limit_converts(self):
        src = self.make_tiff(second=(10, 10))
        with mock.patch.object(image_conv, "MAX_IMAGE_PIXELS", 100):
            (out,) = convert_file(src, "gif", self.opts)
        self.assertTrue(out.exists())


class OdtPictureNotes(Files, unittest.TestCase):
    def convert(self, body, pictures=None):
        src = make_odt(self.dir / "p.odt", body, pictures)
        notes = []
        convert_file(src, "txt", self.opts, trash_original=True, notes=notes)
        return src, notes

    def test_svg_picture_gives_the_warning_and_keeps_the_original(self):
        src, notes = self.convert(picture("Pictures/v.svg") + "<text:p>end</text:p>",
                                  {"Pictures/v.svg": b'<svg xmlns="http://www.w3.org/2000/svg"/>'})
        self.assertTrue(any("pictures were not carried over" in n for n in notes), notes)
        self.assertTrue(any("original kept" in n for n in notes), notes)
        self.assertTrue(src.exists())
        self.assertEqual(self.trashed, [])

    def test_remote_link_gives_the_warning_and_keeps_the_original(self):
        src, notes = self.convert(picture("https://example.com/a.png") + "<text:p>end</text:p>")
        self.assertTrue(any("pictures were not carried over" in n for n in notes), notes)
        self.assertTrue(any("original kept" in n for n in notes), notes)
        self.assertEqual(self.trashed, [])

    def test_embedded_png_gives_no_picture_warning(self):
        src, notes = self.convert(picture("Pictures/p.png") + "<text:p>end</text:p>",
                                  {"Pictures/p.png": png_bytes()})
        self.assertFalse(any("pictures were not carried over" in n for n in notes), notes)
        self.assertEqual([Path(p).name for p in self.trashed], ["p.odt"])


class NetworkPathRules(unittest.TestCase):
    def test_unc_and_device_namespace_paths_are_network_paths(self):
        for raw in (r"\\server\share\a.png", "//server/share/a.png", "\\\\?\\UNC\\server\\share\\a.png",
                    r"\\?\GLOBALROOT\Device\Mup\x", "//?/globalroot/x", "\\\\?\\globalroot\\device\\mup\\x"):
            with self.subTest(raw=raw):
                self.assertTrue(converter._is_network_path(raw))

    def test_local_drive_paths_are_not_network_paths(self):
        for raw in (r"C:\a", "C:/a/b.png", "\\\\?\\C:\\a", "\\\\?\\C:\\a\\b.png"):
            with self.subTest(raw=raw):
                self.assertFalse(converter._is_network_path(raw))


class MainArgvNetwork(Files, unittest.TestCase):
    def test_unc_argument_is_dropped_before_any_file_check(self):
        from convert_win import main as cw_main
        from convert_win import ui

        local = make_png(self.dir / "ok.png")
        unc = r"\\server\share\a.png"
        real_is_file = Path.is_file

        def guarded(path, *a, **k):  # a UNC path must never reach is_file(), which would touch the share
            if str(path).startswith(("\\\\", "//")):
                raise AssertionError(f"file system touched for {path}")
            return real_is_file(path, *a, **k)

        with mock.patch.object(Path, "is_file", autospec=True, side_effect=guarded), \
                mock.patch.object(settings, "setup_logging"), \
                mock.patch.object(ui, "run", return_value=0) as run:  # no log file kept open in the temp profile
            code = cw_main.main([unc, str(local)])
        self.assertEqual(code, 0)
        run.assert_called_once_with([str(local)])


class ToolPathNetwork(Files, unittest.TestCase):
    def test_network_path_entries_on_path_are_never_probed(self):
        tools = self.dir / "tools"
        tools.mkdir()
        (tools / "fake.exe").write_bytes(b"MZ")
        real_is_file = Path.is_file

        def guarded(path, *a, **k):  # a probe under \\ or // would reach a network share
            if str(path).startswith(("\\\\", "//")):
                raise AssertionError(f"network PATH entry probed: {path}")
            return real_is_file(path, *a, **k)

        with mock.patch.object(Path, "is_file", autospec=True, side_effect=guarded):
            with mock.patch.dict(os.environ, {"PATH": os.pathsep.join(["\\\\server\\share", "//server/share", str(tools)])}):
                self.assertEqual(Path(process.find_tool("fake")).name, "fake.exe")
            with mock.patch.dict(os.environ, {"PATH": os.pathsep.join(["\\\\server\\share", "//server/share"])}):
                self.assertIsNone(process.find_tool("fake"))


if __name__ == "__main__":
    unittest.main()
