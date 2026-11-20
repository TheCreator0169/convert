"""v0.2.2 legacy Word 97-2003 .doc input. Every test BUILDS its .doc: a minimal Compound File with a FIB and a piece table,
written to a temp folder. No binary fixture is kept in the repo. Read by doc_binary.read_text, through doc_conv.load and
through convert_file / the CLI. send2trash is replaced by a list.

Test classes: BuiltFile, PieceText, TableSelection, ControlCharacters, Refusals, HostileValues, Sniffing, Fuzz, Limits,
CancelDoc, EndToEnd, FormatLists, StripFieldsLinear, UnclosedFields, CancelStrip, RenamedFiles, EncryptedAndOtherOle,
EmptyText. Helpers (no tests): Files, Doc, cfb, make_doc, plc_of, clx_of, run_guarded, odt_bytes, FlipAfter.
"""
import gc
import io
import logging
import os
import random
import re
import struct
import tempfile
import threading
import time
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

import docx
import olefile
import pymupdf
from PySide6.QtWidgets import QApplication

from convert_win import converter, doc_binary, doc_conv, main
from convert_win import shell_integration as si
from convert_win.converter import convert_file
from convert_win.formats import DEFAULTS, EXT_TYPE, INPUTS, OUTPUTS, file_type, output_fmt, picker_filter
from convert_win.process import Cancelled

ROOT = Path(__file__).resolve().parent.parent
app = None

SECT = 512
ENDOF, FREE, FATSECT = 0xFFFFFFFE, 0xFFFFFFFF, 0xFFFFFFFD
OLE_MAGIC = bytes.fromhex("d0cf11e0a1b11ae1")
TEXT_AT = 0x800  # offset of the text inside the WordDocument stream (after the FIB)
TABLE_CLX_AT = 0x100  # offset of the Clx inside the table stream
WARNING = "formatting, tables and pictures were not carried over (text only)"


def setUpModule():
    global app
    app = QApplication.instance() or QApplication([])


# ---------------------------------------------------------------- helpers (no tests)

def dirent(name, typ, left, right, child, start, size):
    """One 128-byte directory entry (CFB v3: the size high word is 0)."""
    nb = name.encode("utf-16-le") + b"\0\0" if name else b""
    return (nb.ljust(64, b"\0") + struct.pack("<HBBIII", len(nb), typ, 1, left, right, child)
            + b"\0" * 16 + struct.pack("<I", 0) + b"\0" * 16 + struct.pack("<II", start, size & 0xFFFFFFFF)
            + struct.pack("<I", size >> 32))


def cfb(streams):
    """A CFB v3 file with one FAT sector and one directory sector (Root plus at most three streams). Each stream is padded
    to at least 4096 bytes, so olefile reads it from the regular FAT and no mini FAT is needed."""
    assert len(streams) <= 3
    fat = [FREE] * 128
    fat[0], fat[1] = FATSECT, ENDOF
    body, entries, sec = b"", [], 2
    for name, data in streams:
        size = max(4096, -(-len(data) // SECT) * SECT)
        data = data.ljust(size, b"\0")
        n = size // SECT
        for k in range(n):
            fat[sec + k] = sec + k + 1 if k < n - 1 else ENDOF
        entries.append((name, data, sec, size))
        body += data
        sec += n
    assert sec <= 128, "one FAT sector only"
    d = [dirent("Root Entry", 5, FREE, FREE, 1 if entries else FREE, ENDOF, 0)]
    for i, (name, _data, start, size) in enumerate(entries):
        right = i + 2 if i + 1 < len(entries) else FREE  # directory index i+1 is this stream; its sibling is the next one
        d.append(dirent(name, 2, FREE, right, FREE, start, size))
    d += [dirent("", 0, FREE, FREE, FREE, 0, 0)] * (4 - len(d))
    hdr = bytearray(SECT)
    hdr[0:8] = OLE_MAGIC
    struct.pack_into("<HHHHH", hdr, 0x18, 0x3E, 3, 0xFFFE, 9, 6)  # minor, major, byte order, sector shift, mini shift
    struct.pack_into("<9I", hdr, 0x28, 0, 1, 1, 0, 0x1000, ENDOF, 0, ENDOF, 0)
    struct.pack_into("<109I", hdr, 0x4C, 0, *([FREE] * 108))  # DIFAT: FAT sector 0, the rest unused
    return bytes(hdr) + struct.pack("<128I", *fat) + b"".join(d) + body


def plc_of(cps, fcs):
    """PlcPcd: n+1 character positions, then n piece descriptors (2 flag bytes, fc, 2 bytes prm)."""
    return struct.pack(f"<{len(cps)}I", *cps) + b"".join(struct.pack("<HIH", 0, fc, 0) for fc in fcs)


def clx_of(plc, prc=None):
    """Clx: an optional Prc entry (0x01, size, data), then the Pcdt (0x02, size, PlcPcd)."""
    out = b""
    if prc is not None:
        out += b"\x01" + struct.pack("<H", len(prc)) + prc
    return out + b"\x02" + struct.pack("<I", len(plc)) + plc


class Doc:
    """The text area of a WordDocument stream, shared by both piece tables. A piece is (kind, text) or (kind, text, fc):
    kind 'c' is cp1252 bytes (fCompressed, fc = 2 * byte offset with bit 30 set), kind 'u' is UTF-16LE (fc = byte offset).
    A third item sets the fc by hand (hostile values)."""
    def __init__(self):
        self.text = bytearray()

    def plc(self, pieces):
        cps, fcs = [0], []
        for p in pieces:
            kind, text = p[0], p[1]
            raw = text.encode("cp1252") if kind == "c" else text.encode("utf-16-le")
            if len(self.text) % 2:
                self.text += b"\0"
            off = TEXT_AT + len(self.text)
            self.text += raw
            if len(p) == 3:
                fc = p[2]
            else:
                fc = (0x40000000 | 2 * off) if kind == "c" else off
            cps.append(cps[-1] + (len(raw) if kind == "c" else len(text)))
            fcs.append(fc)
        return plc_of(cps, fcs), cps[-1]


def make_doc(pieces, *, pieces1=None, which=0, ccp=None, encrypted=False, prc=None, clx0=None, edits=()):
    """A .doc. pieces is table 0; pieces1 (optional) is table 1. which is the fWhichTblStm choice (0 or 1). ccp defaults to
    the character count of the selected table. clx0 replaces table 0's Clx. edits: (offset, struct fmt, value) on the FIB."""
    doc = Doc()
    plc0, n0 = doc.plc(pieces)
    clxs = {"0Table": clx_of(plc0, prc) if clx0 is None else clx0}
    chars = n0
    if pieces1 is not None:
        plc1, n1 = doc.plc(pieces1)
        clxs["1Table"] = clx_of(plc1, prc)
        if which == 1:
            chars = n1
    selected = "1Table" if which == 1 else "0Table"
    word = bytearray(TEXT_AT) + doc.text
    flags = (0x0200 if which == 1 else 0) | (0x0100 if encrypted else 0)
    struct.pack_into("<H", word, 0x00, 0xA5EC)  # wIdent
    struct.pack_into("<H", word, 0x02, 0xC1)  # nFib: Word 97
    struct.pack_into("<H", word, 0x0A, flags)
    struct.pack_into("<H", word, 0x20, 14)  # csw
    struct.pack_into("<H", word, 0x3E, 22)  # cslw
    struct.pack_into("<I", word, 0x40, len(word))  # cbMac
    struct.pack_into("<I", word, 0x4C, chars if ccp is None else ccp)  # ccpText
    struct.pack_into("<H", word, 0x98, 93)  # cbRgFcLcb
    struct.pack_into("<II", word, 0x1A2, TABLE_CLX_AT, len(clxs.get(selected, b"")))  # fcClx, lcbClx (0 if absent)
    for off, fmt, value in edits:
        struct.pack_into(fmt, word, off, value)
    tables = [(name, b"\0" * TABLE_CLX_AT + clx) for name, clx in clxs.items()]
    return cfb([("WordDocument", bytes(word))] + tables)


def write(folder, name, data):
    p = Path(folder) / name
    p.write_bytes(data)
    return p


def run_guarded(path, limit=2.0):
    """read_text in a daemon thread. Returns (outcome dict, still running after limit, seconds)."""
    box = {}

    def go():
        try:
            box["ok"] = doc_binary.read_text(path)
        except BaseException as e:  # every outcome is recorded: the caller decides which are allowed
            box["err"] = e

    t = threading.Thread(target=go, daemon=True)
    t0 = time.perf_counter()
    t.start()
    t.join(limit)
    return box, t.is_alive(), time.perf_counter() - t0


class Files:
    """Helper mixin (not a test class): a temp folder, a temp profile, and the Recycle Bin replaced by a list."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(gc.collect)  # olefile handles are closed before the folder is removed
        self.dir = Path(self.tmp.name)
        env = mock.patch.dict(os.environ, {"APPDATA": self.tmp.name, "LOCALAPPDATA": self.tmp.name})
        env.start()
        self.addCleanup(env.stop)
        self.opts = {k: dict(v) for k, v in DEFAULTS.items()}
        self.trashed = []
        p = mock.patch.object(converter, "send2trash", lambda s: self.trashed.append(s))
        p.start()
        self.addCleanup(p.stop)

    def names(self):
        """File names in the temp folder (the CLI's log folder, Convert\\, is not a file here)."""
        return sorted(p.name for p in self.dir.iterdir() if p.is_file())

    def read(self, data, name="a.doc"):
        return doc_binary.read_text(write(self.dir, name, data))


# ---------------------------------------------------------------- tests

class BuiltFile(Files, unittest.TestCase):
    def test_streams_come_back_byte_for_byte(self):
        payload = b"hello stream" * 3
        raw = cfb([("WordDocument", payload), ("0Table", b"\x07" * 600)])
        ole = olefile.OleFileIO(io.BytesIO(raw))
        self.assertEqual(ole.openstream("WordDocument").read(), payload.ljust(4096, b"\0"))
        self.assertEqual(ole.openstream("0Table").read(), (b"\x07" * 600).ljust(4096, b"\0"))
        self.assertEqual(sorted(ole.listdir()), [["0Table"], ["WordDocument"]])

    def test_built_doc_opens_with_strict_olefile_checks(self):
        p = write(self.dir, "strict.doc", make_doc([("c", "ok\r")], pieces1=[("c", "ok!\r")]))
        ole = olefile.OleFileIO(str(p), raise_defects=olefile.DEFECT_INCORRECT)
        try:
            self.assertEqual(ole.parsing_issues, [])
            self.assertEqual(sorted(ole.listdir()), [["0Table"], ["1Table"], ["WordDocument"]])
            self.assertEqual(struct.unpack("<H", ole.openstream("WordDocument").read(2))[0], 0xA5EC)
        finally:
            ole.close()


class PieceText(Files, unittest.TestCase):
    def test_compressed_piece_reads_cp1252(self):
        self.assertEqual(self.read(make_doc([("c", "Plain text, café.\r")])), "Plain text, café.\n")

    def test_utf16_piece_keeps_characters_outside_cp1252(self):
        self.assertEqual(self.read(make_doc([("u", "ő 日本語\r")])), "ő 日本語\n")

    def test_two_pieces_mixed_compressed_and_utf16(self):
        pieces = [("c", "Hello "), ("u", "ő 日本語"), ("c", " café\r")]
        self.assertEqual(self.read(make_doc(pieces)), "Hello ő 日本語 café\n")

    def test_prc_entry_before_the_piece_table_is_skipped(self):
        self.assertEqual(self.read(make_doc([("c", "after prc")], prc=b"\x00" * 10)), "after prc")

    def test_text_past_ccp_is_not_read(self):
        self.assertEqual(self.read(make_doc([("c", "abcdef")], ccp=3)), "abc")

    def test_piece_starting_past_ccp_is_not_read(self):
        self.assertEqual(self.read(make_doc([("c", "abc"), ("c", "XYZ")], ccp=3)), "abc")

    def test_ccp_longer_than_the_pieces_is_damaged(self):
        with self.assertRaisesRegex(ValueError, "damaged"):
            self.read(make_doc([("c", "abc")], ccp=7))


class TableSelection(Files, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.build = lambda which: make_doc([("c", "ALPHA-table")], pieces1=[("c", "BRAVO-table")], which=which)

    def test_flag_clear_reads_0table(self):
        self.assertEqual(self.read(self.build(0)), "ALPHA-table")

    def test_flag_set_reads_1table(self):
        self.assertEqual(self.read(self.build(1)), "BRAVO-table")

    def test_flag_set_without_1table_is_damaged(self):
        with self.assertRaisesRegex(ValueError, "damaged"):
            self.read(make_doc([("c", "ALPHA-table")], which=1))


class ControlCharacters(Files, unittest.TestCase):
    def text(self, raw):
        return self.read(make_doc([("c", raw)]))

    def test_carriage_return_is_newline(self):
        self.assertEqual(self.text("one\rtwo\r"), "one\ntwo\n")

    def test_vertical_tab_and_form_feed_are_newlines(self):
        self.assertEqual(self.text("x\x0by\x0cz"), "x\ny\nz")

    def test_tab_and_line_feed_are_kept(self):
        self.assertEqual(self.text("a\tb\nc"), "a\tb\nc")

    def test_0x01_0x02_0x08_0x1f_are_dropped(self):
        self.assertEqual(self.text("p\x01q\x08r\x02s\x1ft"), "pqrst")

    def test_0x1e_is_a_hyphen(self):
        self.assertEqual(self.text("a\x1eb"), "a-b")

    def test_cell_marks_make_a_tab_and_row_end_a_newline(self):
        self.assertEqual(self.text("a\r\x07b\r\x07\x07"), "a\tb\n")

    def test_two_rows_of_two_cells(self):
        self.assertEqual(self.text("a\r\x07b\r\x07\x07c\r\x07d\r\x07\x07"), "a\tb\nc\td\n")

    def test_empty_middle_cell_is_taken_for_a_row_end(self):
        # documented limit: the file does not tell an empty cell from a row end without the table properties
        self.assertEqual(self.text("a\r\x07\r\x07b\r\x07\x07"), "a\nb\n")

    def test_field_keeps_only_the_result(self):
        self.assertEqual(self.text('A\x13 HYPERLINK "http://x" \x14shown\x15 B'), "Ashown B")

    def test_nested_field_inside_an_instruction_is_dropped_with_it(self):
        self.assertEqual(self.text("pre\x13A\x13B\x14inner\x15\x14outer\x15post"), "preouterpost")

    def test_nested_field_inside_a_result_keeps_each_result(self):
        self.assertEqual(self.text("\x13A\x14r1\x13B\x14r2\x15r3\x15"), "r1r2r3")

    def test_lone_field_marks_are_dropped(self):
        self.assertEqual(self.text("a\x14b\x15c"), "abc")

    def test_unclosed_field_with_a_result_keeps_its_result(self):
        self.assertEqual(self.text('keep\x13 HYPERLINK "x" \x14 result never closed'), "keep result never closed")

    def test_unclosed_instruction_keeps_the_text_before_it(self):
        # Only the text before the open 0x13 is pinned. With no 0x14 separator the current code drops everything after it
        # (possible data loss, reported to the caller); the test deliberately does not assert the tail either way.
        self.assertTrue(self.text("keep\x13 instruction never ended then more text").startswith("keep"))

    def test_unclosed_cell_mark_at_the_end_gives_a_tab(self):
        self.assertEqual(self.text("a\x07"), "a\t")


class Refusals(Files, unittest.TestCase):
    def test_wrong_wident_is_not_a_word_document(self):
        with self.assertRaisesRegex(ValueError, "not a Word document"):
            self.read(make_doc([("c", "x")], edits=[(0x00, "<H", 0x1234)]))

    def test_not_an_ole_file_is_not_a_word_document(self):
        with self.assertRaisesRegex(ValueError, "not a Word document"):
            self.read(b"this is plain text, not a compound file " * 80)

    def test_random_junk_is_not_a_word_document(self):
        with self.assertRaisesRegex(ValueError, "not a Word document"):
            self.read(random.Random(7).randbytes(5000))

    def test_empty_file_is_not_a_word_document(self):
        with self.assertRaisesRegex(ValueError, "not a Word document"):
            self.read(b"")

    def test_no_worddocument_stream_is_not_a_word_document(self):
        with self.assertRaisesRegex(ValueError, "not a Word document"):
            self.read(cfb([("0Table", b"x" * 100)]))

    def test_encrypted_flag_is_refused_with_a_password_message(self):
        with self.assertRaisesRegex(ValueError, "password"):
            self.read(make_doc([("c", "secret")], encrypted=True))

    def test_encrypted_flag_with_1table_is_refused_too(self):
        with self.assertRaisesRegex(ValueError, "password"):
            self.read(make_doc([("c", "secret")], pieces1=[("c", "secret")], which=1, encrypted=True))

    def test_word_95_is_refused(self):
        with self.assertRaisesRegex(ValueError, "Word 95"):
            self.read(make_doc([("c", "x")], edits=[(0x02, "<H", 0xBF)]))


class HostileValues(Files, unittest.TestCase):
    """Each value is written on purpose: the reader must raise ValueError, never IndexError, struct.error or a hang."""

    def expect_damaged(self, data):
        with self.assertRaisesRegex(ValueError, "damaged"):
            self.read(data)

    def test_compressed_piece_fc_past_the_stream(self):
        self.expect_damaged(make_doc([("c", "hi", 0x40000000 | 2 * 900000)]))

    def test_utf16_piece_fc_past_the_stream(self):
        self.expect_damaged(make_doc([("u", "hi", 0x00F00000)]))

    def test_lcb_clx_bigger_than_the_table(self):
        self.expect_damaged(make_doc([("c", "x")], edits=[(0x1A6, "<I", 99999)]))

    def test_fc_clx_past_the_table(self):
        self.expect_damaged(make_doc([("c", "x")], edits=[(0x1A2, "<I", 0xFFFFFF)]))

    def test_unknown_clx_kind_byte(self):
        self.expect_damaged(make_doc([("c", "x")], clx0=b"\x03" + b"\0" * 20))

    def test_prc_size_overruns_the_clx(self):
        self.expect_damaged(make_doc([("c", "x")], clx0=b"\x01\xff\xff" + b"ab"))

    def test_character_positions_that_go_backwards(self):
        base = 0x40000000 | 2 * TEXT_AT
        self.expect_damaged(make_doc([("c", "x")], clx0=clx_of(plc_of([0, 10, 5], [base, base]))))

    def test_cbrgfclcb_below_34(self):
        self.expect_damaged(make_doc([("c", "x")], edits=[(0x98, "<H", 33)]))

    def test_huge_csw(self):
        self.expect_damaged(make_doc([("c", "x")], edits=[(0x20, "<H", 0xFFFF)]))

    def test_huge_cslw(self):
        self.expect_damaged(make_doc([("c", "x")], edits=[(0x3E, "<H", 0xFFFF)]))


class Sniffing(Files, unittest.TestCase):
    def test_sniff_kinds(self):
        cases = [("ole", make_doc([("c", "x")]), "ole"), ("rtf", b"{\\rtf1 hi}", "rtf"),
                 ("docx", b"PK\x03\x04junk", "docx"), ("other", b"plain text", "other"), ("empty", b"", "other")]
        for name, data, expected in cases:
            with self.subTest(name=name):
                self.assertEqual(doc_binary.sniff(write(self.dir, f"{name}.doc", data)), expected)

    def test_renamed_rtf_is_read_as_rtf(self):
        doc = doc_conv.load(write(self.dir, "renamed.doc", b"{\\rtf1\\ansi Hello rtf}"))
        self.assertIn("Hello rtf", doc.toPlainText())

    def test_renamed_docx_is_read_as_docx(self):
        src = self.dir / "real.docx"
        d = docx.Document()
        d.add_paragraph("Hello docx")
        d.save(src)
        doc = doc_conv.load(src.rename(self.dir / "renamed.doc"))
        self.assertIn("Hello docx", doc.toPlainText())

    def test_text_named_doc_is_refused_by_load(self):
        with self.assertRaisesRegex(ValueError, "not a Word document"):
            doc_conv.load(write(self.dir, "fake.doc", b"just some words"))

    def test_text_named_doc_gives_no_output_and_no_trash(self):
        src = write(self.dir, "fake.doc", b"just some words")
        with self.assertRaises(ValueError):
            convert_file(src, "txt", self.opts, trash_original=True)
        self.assertEqual(self.names(), ["fake.doc"])
        self.assertEqual(self.trashed, [])

    def test_renamed_rtf_warning_is_the_rtf_one(self):
        src = write(self.dir, "renamed.doc", b"{\\rtf1\\ansi Hello rtf}")
        notes = []
        (out,) = convert_file(src, "txt", self.opts, trash_original=True, notes=notes)
        self.assertIn("Hello rtf", out.read_text("utf-8"))
        self.assertEqual(notes, ["renamed.doc: RTF headings, lists and pictures were not carried over",
                                 "renamed.doc: original kept"])
        self.assertEqual(self.trashed, [])

    def test_renamed_docx_with_nothing_lost_is_trashed(self):
        src = self.dir / "plain.docx"
        d = docx.Document()
        d.add_paragraph("Hello docx")
        d.save(src)
        src = src.rename(self.dir / "plain.doc")
        notes = []
        convert_file(src, "txt", self.opts, trash_original=True, notes=notes)
        self.assertEqual(notes, [])
        self.assertEqual(self.trashed, [str(src)])  # converter passes the path as a string


class Fuzz(Files, unittest.TestCase):
    """Truncations and seeded byte flips: every result is a text or a ValueError, within 2 s, never a hang."""

    def base(self):
        return make_doc([("c", "Fuzz base text, café.\r"), ("u", "ő 日本語\r")], prc=b"\x00\x01\x02")

    def check(self, data, label, counts):
        path = write(self.dir, "fuzz.doc", data)
        box, alive, dt = run_guarded(path)
        self.assertFalse(alive, f"hang: {label}")
        self.assertLess(dt, 2.0, f"slow ({dt:.2f}s): {label}")
        if "err" in box:
            self.assertIsInstance(box["err"], ValueError, f"{label}: {type(box['err']).__name__}: {box['err']}")
            counts["error"] += 1
        else:
            self.assertIsInstance(box["ok"], str, label)
            counts["text"] += 1

    def test_every_truncation_is_text_or_value_error(self):
        data = self.base()
        counts = {"text": 0, "error": 0}
        lengths = list(range(0, min(1500, len(data)))) + list(range(1500, len(data), 97))
        for n in lengths:
            self.check(data[:n], f"truncated to {n} bytes", counts)
        self.assertGreater(counts["error"], 0)  # the check is not vacuous

    def test_seeded_byte_flips_are_text_or_value_error(self):
        data = self.base()
        ole = olefile.OleFileIO(io.BytesIO(data))
        word_at = (next(e for e in ole.direntries if e and e.name == "WordDocument").isectStart + 1) * SECT
        table_at = (next(e for e in ole.direntries if e and e.name == "0Table").isectStart + 1) * SECT
        ole.close()
        self.assertEqual(data[word_at:word_at + 2], b"\xec\xa5")  # wIdent 0xA5EC: the FIB is where the flips aim
        clx_len = struct.unpack_from("<I", data, word_at + 0x1A6)[0]
        self.assertEqual(data[table_at + TABLE_CLX_AT + 0:table_at + TABLE_CLX_AT + 1], b"\x01")  # Prc entry of the Clx
        hot = [(word_at, word_at + 0x200), (table_at + TABLE_CLX_AT, table_at + TABLE_CLX_AT + clx_len)]  # FIB, Clx
        rng = random.Random(20260220)
        counts = {"text": 0, "error": 0}
        for i in range(300):
            buf = bytearray(data)
            for _ in range(rng.randint(1, 3)):
                if rng.random() < 0.5:
                    lo, hi = rng.choice(hot)
                    pos = rng.randrange(lo, hi)
                else:
                    pos = rng.randrange(len(buf))
                buf[pos] = rng.randrange(256)
            self.check(bytes(buf), f"flip iteration {i}", counts)
        self.assertGreater(counts["error"], 0)


class Limits(Files, unittest.TestCase):
    def test_file_at_the_limit_is_read_and_one_byte_over_is_refused(self):
        data = make_doc([("c", "limit test\r")])
        p = write(self.dir, "limit.doc", data)
        with mock.patch.object(doc_binary, "MAX_FILE", len(data)):
            self.assertEqual(doc_binary.read_text(p), "limit test\n")
        with mock.patch.object(doc_binary, "MAX_FILE", len(data) - 1):
            with self.assertRaisesRegex(ValueError, "file too large"):
                doc_binary.read_text(p)

    def test_piece_cap_boundary(self):
        p = write(self.dir, "pieces.doc", make_doc([("c", "one"), ("c", "two")]))
        with mock.patch.object(doc_binary, "MAX_PIECES", 2):
            self.assertEqual(doc_binary.read_text(p), "onetwo")
        with mock.patch.object(doc_binary, "MAX_PIECES", 1):
            with self.assertRaisesRegex(ValueError, "too many pieces"):
                doc_binary.read_text(p)

    def test_character_cap_boundary(self):
        p = write(self.dir, "chars.doc", make_doc([("c", "elevenchars")]))
        with mock.patch.object(doc_binary, "MAX_CHARS", 11):
            self.assertEqual(doc_binary.read_text(p), "elevenchars")
        with mock.patch.object(doc_binary, "MAX_CHARS", 10):
            with self.assertRaisesRegex(ValueError, "document too long"):
                doc_binary.read_text(p)

    def test_shipped_limits(self):
        self.assertEqual(doc_binary.MAX_FILE, 64_000_000)
        self.assertEqual(doc_binary.MAX_PIECES, 100_000)
        self.assertEqual(doc_binary.MAX_CHARS, 20_000_000)


class FlipAfter:
    """A cancel object that is set from the n-th check on (is_set is called once per piece)."""
    def __init__(self, n):
        self.n, self.calls = n, 0

    def is_set(self):
        self.calls += 1
        return self.calls > self.n


class CancelDoc(Files, unittest.TestCase):
    def test_set_event_raises_cancelled(self):
        p = write(self.dir, "c.doc", make_doc([("c", "text")]))
        ev = threading.Event()
        ev.set()
        with self.assertRaises(Cancelled):
            doc_binary.read_text(p, cancel=ev)

    def test_cancel_between_pieces_raises(self):
        p = write(self.dir, "c.doc", make_doc([("c", "first "), ("c", "second")]))
        with self.assertRaises(Cancelled):
            doc_binary.read_text(p, cancel=FlipAfter(1))

    def test_clear_event_reads_the_text(self):
        p = write(self.dir, "c.doc", make_doc([("c", "text\r")]))
        self.assertEqual(doc_binary.read_text(p, cancel=threading.Event()), "text\n")

    def test_convert_file_with_cancel_set_leaves_nothing(self):
        src = write(self.dir, "c.doc", make_doc([("c", "text")]))
        ev = threading.Event()
        ev.set()
        with self.assertRaises(Cancelled):
            convert_file(src, "txt", self.opts, trash_original=True, cancel=ev)
        self.assertEqual(self.names(), ["c.doc"])
        self.assertEqual(self.trashed, [])


class EndToEnd(Files, unittest.TestCase):
    def sample(self, name="report.doc"):
        pieces = [("c", "Hello doc, café\r"), ("u", "ő 日本語\r")]
        return write(self.dir, name, make_doc(pieces, pieces1=None))

    def test_txt_output_has_the_text_and_the_warning_and_keeps_the_original(self):
        src = self.sample()
        notes = []
        (out,) = convert_file(src, "txt", self.opts, trash_original=True, notes=notes)
        self.assertEqual(out.name, "report.txt")
        self.assertEqual(out.read_text("utf-8").rstrip("\n"), "Hello doc, café\nő 日本語")
        self.assertIn(f"report.doc: {WARNING}", notes)
        self.assertIn("report.doc: original kept", notes)
        self.assertEqual(self.trashed, [])
        self.assertTrue(src.exists())

    def test_pdf_output_has_the_text_and_the_warning_and_keeps_the_original(self):
        src = self.sample()
        notes = []
        (out,) = convert_file(src, "pdf", self.opts, trash_original=True, notes=notes)
        with pymupdf.open(out) as d:
            text = d[0].get_text()
        self.assertIn("Hello doc, café", text)
        self.assertIn(f"report.doc: {WARNING}", notes)
        self.assertEqual(self.trashed, [])
        self.assertTrue(src.exists())

    def test_cli_txt_prints_the_output_and_the_warning(self):
        src = self.sample()
        out_buf, err_buf = io.StringIO(), io.StringIO()
        self.addCleanup(self.close_log)
        with redirect_stdout(out_buf), redirect_stderr(err_buf):
            code = main.main(["--cli", "txt", str(src)])
        self.assertEqual(code, 0, err_buf.getvalue())
        self.assertIn(str(self.dir / "report.txt"), out_buf.getvalue())
        self.assertIn(f"warning: report.doc: {WARNING}", err_buf.getvalue())
        self.assertTrue((self.dir / "report.txt").exists())
        self.assertTrue(src.exists())

    def test_cli_refuses_a_text_file_named_doc(self):
        src = write(self.dir, "fake.doc", b"just words")
        out_buf, err_buf = io.StringIO(), io.StringIO()
        self.addCleanup(self.close_log)
        with redirect_stdout(out_buf), redirect_stderr(err_buf):
            code = main.main(["--cli", "txt", str(src)])
        self.assertEqual(code, 1)
        self.assertIn("not a Word document", err_buf.getvalue())
        self.assertEqual(self.names(), ["fake.doc"])

    def test_pdf_cli_writes_one_pdf(self):
        src = self.sample()
        out_buf, err_buf = io.StringIO(), io.StringIO()
        self.addCleanup(self.close_log)
        with redirect_stdout(out_buf), redirect_stderr(err_buf):
            code = main.main(["--cli", "pdf", str(src)])
        self.assertEqual(code, 0, err_buf.getvalue())
        self.assertTrue((self.dir / "report.pdf").exists())
        with pymupdf.open(self.dir / "report.pdf") as d:
            self.assertIn("Hello doc", d[0].get_text())

    def close_log(self):
        log = logging.getLogger("convert")
        for h in list(log.handlers):
            h.close()
            log.removeHandler(h)


def odt_bytes(paragraph):
    """A minimal ODT: mimetype first (stored), then a content.xml with one paragraph."""
    xml = ('<?xml version="1.0"?><office:document-content '
           'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
           'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">'
           f"<office:body><office:text><text:p>{paragraph}</text:p></office:text></office:body>"
           "</office:document-content>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("mimetype", "application/vnd.oasis.opendocument.text")
        z.writestr("content.xml", xml)
    return buf.getvalue()


class StripFieldsLinear(unittest.TestCase):
    def test_many_closed_fields_then_long_text_is_linear(self):
        # every 0x13 0x14 pair leaves one False entry on the stack: a per-character scan of the stack would be quadratic here
        text = "\x13\x14" * 20000 + "a" * 1000000
        box = {}

        def go():
            box["out"] = doc_binary._strip_fields(text)

        t = threading.Thread(target=go, daemon=True)  # the bound is enforced while the call runs: a slow version cannot hang the suite
        t0 = time.perf_counter()
        t.start()
        t.join(3.0)
        dt = time.perf_counter() - t0
        self.assertFalse(t.is_alive(), f"_strip_fields still running after {dt:.1f} s")
        self.assertIn("out", box)
        self.assertTrue(box["out"] == "a" * 1000000, f"got {len(box['out'])} characters")

    def test_many_markers_with_a_deep_stack_stay_linear(self):
        # 400000 markers and a stack of 200000 entries: a scan of the stack at every marker is about 4e10 steps
        text = "\x13\x14" * 200000 + "a" * 1000
        box = {}
        t = threading.Thread(target=lambda: box.__setitem__("out", doc_binary._strip_fields(text)), daemon=True)
        t.start()
        t.join(3.0)
        self.assertFalse(t.is_alive(), "_strip_fields still running after 3 s")
        self.assertTrue(box.get("out") == "a" * 1000, f"got {len(box.get('out', ''))} characters")


class UnclosedFields(unittest.TestCase):
    def strip(self, text):
        return doc_binary._strip_fields(text)

    def test_unclosed_instruction_before_a_paragraph_mark_is_closed_there(self):
        out = self.strip("keep\x13 instr never ended\rmore text")
        self.assertIn("keep", out)
        self.assertIn("more text", out)
        self.assertNotIn("\x13", out)
        self.assertNotIn("instr", out)

    def test_unclosed_instruction_at_the_end_keeps_only_the_text_before_it(self):
        self.assertEqual(self.strip("keep\x13 instr never ended"), "keep")

    def test_field_result_spanning_a_paragraph_keeps_both_sides(self):
        self.assertEqual(self.strip("A\x13 HYPERLINK x \x14first\rsecond\x15 B"), "Afirst\rsecond B")

    def test_nested_fields_keep_the_outer_result(self):
        self.assertEqual(self.strip("x\x13a\x13b\x15c\x14r\x15y"), "xry")

    def test_stray_result_and_end_marks_are_removed(self):
        self.assertEqual(self.strip("\x15\x15a\x14\x14b"), "ab")


class CancelStrip(unittest.TestCase):
    def test_cancel_inside_strip_fields_raises_cancelled(self):
        with self.assertRaises(Cancelled):
            doc_binary._strip_fields("a" * 200000, FlipAfter(1))

    def test_set_event_inside_strip_fields_raises_cancelled(self):
        ev = threading.Event()
        ev.set()
        with self.assertRaises(Cancelled):
            doc_binary._strip_fields("keep\x13x\x14y\x15" + "a" * 200000, ev)

    def test_clear_event_returns_the_text(self):
        text = "keep\x13hidden\x14shown\x15" + "a" * 200000
        self.assertTrue(doc_binary._strip_fields(text, threading.Event()) == "keepshown" + "a" * 200000)


class RenamedFiles(Files, unittest.TestCase):
    def fmt_txt(self, src):
        return output_fmt(src, "txt")[1]

    def test_real_docx_renamed_doc_reads_through_load(self):
        src = self.dir / "real.docx"
        d = docx.Document()
        d.add_paragraph("Hello renamed docx")
        d.save(src)
        doc = doc_conv.load(src.rename(self.dir / "renamed.doc"))
        self.assertIn("Hello renamed docx", doc.toPlainText())

    def test_real_docx_renamed_doc_converts_to_txt(self):
        src = self.dir / "real.docx"
        d = docx.Document()
        d.add_paragraph("Hello converted docx")
        d.save(src)
        src = src.rename(self.dir / "renamed.doc")
        dst = self.dir / "out.txt"
        self.assertIsNone(doc_conv.convert(src, dst, self.fmt_txt(src), self.opts["doc"]))
        self.assertIn("Hello converted docx", dst.read_text("utf-8"))

    def test_odt_renamed_doc_reads_through_load(self):
        src = write(self.dir, "renamed.doc", odt_bytes("Hello renamed odt"))
        self.assertIn("Hello renamed odt", doc_conv.load(src).toPlainText())

    def test_odt_renamed_doc_has_no_convert_warning(self):
        src = write(self.dir, "renamed.doc", odt_bytes("Hello odt warning"))
        dst = self.dir / "out.txt"
        self.assertIsNone(doc_conv.convert(src, dst, self.fmt_txt(src), self.opts["doc"]))
        self.assertIn("Hello odt warning", dst.read_text("utf-8"))

    def test_plain_zip_named_doc_is_not_a_word_document(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("hello.txt", "just a zip")
        with self.assertRaisesRegex(ValueError, "not a Word document"):
            doc_conv.load(write(self.dir, "zip.doc", buf.getvalue()))

    def test_corrupt_zip_named_doc_is_not_a_word_document(self):
        with self.assertRaisesRegex(ValueError, "not a Word document"):
            doc_conv.load(write(self.dir, "corrupt.doc", b"PK\x03\x04" + b"garbage" * 60))

    def test_html_named_doc_is_not_a_word_document(self):
        html_src = write(self.dir, "page.doc", b"<html><body><p>not a doc</p></body></html>")
        with self.assertRaisesRegex(ValueError, "not a Word document"):
            doc_conv.load(html_src)
        with self.assertRaisesRegex(ValueError, "not a Word document"):
            doc_conv.convert(html_src, self.dir / "out.txt", self.fmt_txt(html_src), self.opts["doc"])


class EncryptedAndOtherOle(Files, unittest.TestCase):
    def test_encrypted_package_without_worddocument_is_refused_with_a_password_message(self):
        raw = cfb([("EncryptionInfo", b"x" * 100), ("EncryptedPackage", b"y" * 200)])
        with self.assertRaisesRegex(ValueError, "password-protected files are not supported"):
            self.read(raw)

    def test_encryption_info_alone_is_not_a_word_document(self):
        with self.assertRaisesRegex(ValueError, "not a Word document"):
            self.read(cfb([("EncryptionInfo", b"x" * 100)]))

    def test_workbook_stream_without_worddocument_is_not_a_word_document(self):
        with self.assertRaisesRegex(ValueError, "not a Word document"):
            self.read(cfb([("Workbook", b"x" * 100)]))


class EmptyText(Files, unittest.TestCase):
    def test_zero_ccp_text_is_refused(self):
        with self.assertRaisesRegex(ValueError, "the document has no text"):
            self.read(make_doc([("c", "")]))

    def test_only_control_characters_is_refused(self):
        with self.assertRaisesRegex(ValueError, "the document has no text"):
            self.read(make_doc([("c", "\x01\x02\x08\x1f")]))

    def test_only_an_empty_field_is_refused(self):
        with self.assertRaisesRegex(ValueError, "the document has no text"):
            self.read(make_doc([("c", "\x13 HYPERLINK x\x15")]))

    def test_cli_txt_reports_the_message_and_writes_nothing(self):
        src = write(self.dir, "empty.doc", make_doc([("c", "\x01\x02")]))
        out_buf, err_buf = io.StringIO(), io.StringIO()
        self.addCleanup(self.close_log)
        with redirect_stdout(out_buf), redirect_stderr(err_buf):
            code = main.main(["--cli", "txt", str(src)])
        self.assertNotEqual(code, 0)
        self.assertIn("the document has no text", err_buf.getvalue())
        self.assertEqual(self.names(), ["empty.doc"])

    def close_log(self):
        log = logging.getLogger("convert")
        for h in list(log.handlers):
            h.close()
            log.removeHandler(h)


class FormatLists(unittest.TestCase):
    def test_doc_is_an_input_type(self):
        self.assertIn("doc", INPUTS["doc"].split())
        self.assertEqual(file_type(Path("letter.doc")), "doc")
        self.assertEqual(file_type(Path("LETTER.DOC")), "doc")
        self.assertEqual(EXT_TYPE["doc"], "doc")
        self.assertEqual(file_type(Path("letter.docx")), "doc")

    def test_doc_outputs_are_the_text_formats(self):
        self.assertEqual(set(OUTPUTS["doc"]), {"pdf", "docx", "odt", "rtf", "txt", "html"})

    def test_picker_filter_lists_doc_as_a_whole_token(self):
        m = re.search(r"\((.*)\)$", picker_filter())
        self.assertIsNotNone(m)
        tokens = m.group(1).split()
        self.assertIn("*.doc", tokens)
        self.assertEqual(set(tokens), {f"*.{e}" for e in EXT_TYPE})

    def test_shell_integration_writes_a_verb_for_doc(self):
        self.assertIn("doc", si.EXT_TYPE)
        self.assertTrue(si._verb(r"Software\Classes", "doc").endswith(r"\SystemFileAssociations\.doc\shell\Convert"))

    def test_installer_remove_list_has_doc_and_every_input(self):
        text = (ROOT / "installer" / "convert.iss").read_text("utf-8", errors="replace")
        m = re.search(r"Exts := '([^']*)'", text)
        self.assertIsNotNone(m)
        listed = [e for e in m.group(1).split(",") if e]
        self.assertIn("doc", listed)
        self.assertEqual(set(EXT_TYPE) - set(listed), set())

    def test_requirements_in_pins_olefile(self):
        self.assertRegex((ROOT / "requirements.in").read_text("utf-8"), r"(?m)^olefile==0\.47\r?$")

    def test_requirements_txt_pins_olefile_with_a_hash(self):
        self.assertRegex((ROOT / "requirements.txt").read_text("utf-8"),
                         r"(?m)^olefile==0\.47 \\\r?\n\s+--hash=sha256:[0-9a-f]{64}")


if __name__ == "__main__":
    unittest.main()
