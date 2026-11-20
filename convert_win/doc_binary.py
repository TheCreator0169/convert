"""Legacy Word 97-2003 .doc input: the main body text, read from the binary file with olefile. No Word, no LibreOffice.
Text only: styles, pictures, headers, footnotes and text boxes are not read; tables come out as tab-separated lines.
Password-protected files are refused, never decrypted."""
import os
import re
import struct

from .process import Cancelled

OLE_MAGIC = bytes.fromhex("d0cf11e0a1b11ae1")
MAX_FILE = 64_000_000  # bytes of one .doc: the whole file is read into memory
MAX_PIECES = 100_000  # pieces in the piece table
MAX_CHARS = 20_000_000  # characters of main text
DAMAGED = "damaged .doc file"


def sniff(path):
    """'ole' for a binary Word file, 'rtf' or 'docx' when the content says so (a renamed file), else 'other'."""
    with open(path, "rb") as f:
        head = f.read(8)
    if head.startswith(OLE_MAGIC):
        return "ole"
    if head.startswith(b"{\\rtf"):
        return "rtf"
    if head.startswith(b"PK\x03\x04"):
        return "docx"
    return "other"


def _slice(b, off, n):
    if off < 0 or n < 0 or off + n > len(b):
        raise ValueError(DAMAGED)
    return b[off:off + n]


def _u16(b, off):
    return struct.unpack("<H", _slice(b, off, 2))[0]


def _u32(b, off):
    return struct.unpack("<I", _slice(b, off, 4))[0]


def _plcpcd(clx):
    """The PlcPcd inside the Clx: skip the Prc entries (0x01, each moves forward), stop at the Pcdt (0x02)."""
    pos = 0
    while True:
        kind = _slice(clx, pos, 1)[0]
        if kind == 0x01:
            pos += 3 + _u16(clx, pos + 1)  # unsigned length: always moves forward
        elif kind == 0x02:
            return _slice(clx, pos + 5, _u32(clx, pos + 1))
        else:
            raise ValueError(DAMAGED)


def _pieces(plc, word, ccp_text, cancel):
    """Raw text of each piece up to ccp_text, as (bytes, is_8_bit). CPs must not go backwards."""
    if len(plc) < 16 or (len(plc) - 4) % 12:
        raise ValueError(DAMAGED)
    n = (len(plc) - 4) // 12
    if n > MAX_PIECES:
        raise ValueError("too many pieces in this .doc file")
    cps = struct.unpack_from(f"<{n + 1}I", plc, 0)
    if cps[0] != 0 or any(b < a for a, b in zip(cps, cps[1:])) or cps[-1] < ccp_text:
        raise ValueError(DAMAGED)
    for i in range(n):
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        start = cps[i]
        if start >= ccp_text:
            break
        count = min(cps[i + 1], ccp_text) - start
        fc = _u32(plc, 4 * (n + 1) + 8 * i + 2)  # PCD: 2 bytes of flags, then FcCompressed
        is_8_bit = bool(fc & 0x40000000)  # fCompressed: cp1252 bytes at fc / 2
        off = (fc & 0x3FFFFFFF) // 2 if is_8_bit else fc & 0x3FFFFFFF
        yield _slice(word, off, count if is_8_bit else 2 * count), is_8_bit


_FIELD_MARK = re.compile("[\x13\x14\x15\r]")
CANCEL_EVERY = 65_536  # characters between two cancel checks in _strip_fields


def _strip_fields(text, cancel=None):
    """Drop field instructions (0x13 .. 0x14) and keep the result (0x14 .. 0x15); nested fields are allowed.
    An unmatched 0x15 is ignored. A field still open at a paragraph mark (0x0D) that has no 0x14 is closed there:
    its instruction stops hiding text, so a field that never ends cannot hide the rest of the document.
    Linear: only the markers are visited, the text between them is copied as slices."""
    parts = []
    stack = []  # one flag per open field, True while in its instruction part
    hidden = 0  # number of open fields whose instruction part is current: text is dropped while this is above 0
    pos = 0  # start of the text not yet copied
    n = len(text)
    for window in range(0, n, CANCEL_EVERY):  # the text is walked in windows: a cancel is seen within one window
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        for m in _FIELD_MARK.finditer(text, window, min(window + CANCEL_EVERY, n)):
            at = m.start()
            ch = m.group()
            if ch == "\r":
                if hidden:  # close the unfinished instructions: the text before this mark is dropped, the mark is shown
                    stack.clear()  # result parts hide nothing, so dropping them changes no output
                    hidden = 0
                    pos = at
                continue  # a paragraph mark is text: it stays in the next copied slice
            if not hidden:
                parts.append(text[pos:at])
            pos = at + 1
            if ch == "\x13":
                stack.append(True)
                hidden += 1
            elif ch == "\x14":
                if stack and stack[-1]:
                    stack[-1] = False
                    hidden -= 1
            elif stack and stack.pop():  # 0x15 closes the innermost field; an unmatched one is ignored
                hidden -= 1
    if not hidden:
        parts.append(text[pos:])
    return "".join(parts)


# every control character except tab and line feed; 0x0B, 0x0C, 0x0D become a line break and 0x1E a hyphen
_CONTROL = {c: None for c in range(0x20) if c not in (0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x1E)}
_CONTROL.update({0x0B: "\n", 0x0C: "\n", 0x0D: "\n", 0x1E: "-"})


def _clean(text, cancel=None):
    if "\x13" in text:
        text = _strip_fields(text, cancel)
    # table marks: Word writes each cell end as paragraph mark + 0x07. The paragraph mark is dropped; a 0x07 right after
    # another 0x07 is an empty cell group, which is taken for the row end (an empty cell in the middle of a row breaks
    # the row: the file does not tell an empty cell from a row end without the table properties).
    text = text.replace("\r\x07", "\x07")
    text = re.sub("\x07", lambda m: "\n" if m.start() and m.string[m.start() - 1] == "\x07" else "\t", text)
    text = text.replace("\t\n", "\n")
    return text.translate(_CONTROL)


def _read_ole(ole, cancel):
    if not ole.exists("WordDocument"):
        if ole.exists("EncryptionInfo") and ole.exists("EncryptedPackage"):  # Office 2007+ encrypted package, saved as .doc
            raise ValueError("password-protected files are not supported")
        raise ValueError("not a Word document")  # xls, ppt or another OLE file with a .doc name
    with ole.openstream("WordDocument") as s:
        word = s.read()
    if _u16(word, 0x00) != 0xA5EC:  # wIdent
        raise ValueError("not a Word document")
    flags = _u16(word, 0x0A)
    if flags & 0x0100:  # fEncrypted
        raise ValueError("password-protected .doc files are not supported")
    if _u16(word, 0x02) < 0xC1:  # nFib: Word 97 and later
        raise ValueError("Word 95 or older .doc files are not supported")
    table_name = "1Table" if flags & 0x0200 else "0Table"  # fWhichTblStm
    if not ole.exists(table_name):
        raise ValueError(DAMAGED)
    with ole.openstream(table_name) as s:
        table = s.read()
    csw = _u16(word, 0x20)  # FibBase is 32 bytes; csw, then fibRgW97
    cslw = _u16(word, 0x22 + 2 * csw)  # then cslw, then FibRgLw97
    lw = 0x24 + 2 * csw
    ccp_text = _u32(word, lw + 12)  # ccpText: the 4th DWORD of FibRgLw97 (0x4C in Word 97)
    rgfc = lw + 4 * cslw + 2  # after the FibRgLw97 words and cbRgFcLcb: FibRgFcLcb97
    if _u16(word, rgfc - 2) < 34:
        raise ValueError(DAMAGED)
    fc_clx = _u32(word, rgfc + 33 * 8)  # pair 33 is fcClx / lcbClx (0x1A2 and 0x1A6 in Word 97)
    lcb_clx = _u32(word, rgfc + 33 * 8 + 4)
    if ccp_text > MAX_CHARS:
        raise ValueError(f"document too long: more than {MAX_CHARS // 1_000_000} million characters")
    plc = _plcpcd(_slice(table, fc_clx, lcb_clx))
    parts = []
    for raw, is_8_bit in _pieces(plc, word, ccp_text, cancel):
        parts.append(raw.decode("cp1252", "replace") if is_8_bit else raw.decode("utf-16-le", "replace"))
    return _clean("".join(parts), cancel)


def read_text(path, cancel=None):
    """The body text of a binary .doc. Raises ValueError with a short message when the file cannot be read."""
    import olefile  # imported here: sniff() and the module load without it

    if os.path.getsize(path) > MAX_FILE:
        raise ValueError(f"file too large: over {MAX_FILE // 1_000_000} MB")
    try:
        ole = olefile.OleFileIO(str(path))
    except Exception as e:  # not an OLE2 file, or damaged beyond reading
        raise ValueError("not a Word document") from e
    try:
        text = _read_ole(ole, cancel)
        if not text:  # ccpText 0, or every character sat inside field instructions
            raise ValueError("the document has no text")
        return text
    except (Cancelled, ValueError):
        raise
    except Exception as e:  # olefile and struct errors on damaged files: never escape as they are
        raise ValueError(DAMAGED) from e
    finally:
        ole.close()
