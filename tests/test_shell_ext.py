"""Tests for shell_ext: the generated tables (pure Python) and the built ConvertMenu.dll (ctypes, raw COM vtable calls).

The DLL tests skip when build\\shell_ext\\ConvertMenu.dll is missing; build it with tools\\build_shell_ext.ps1.
Nothing here builds anything or touches the registry. Temp files only (tempfile); no network.
"""
import contextlib
import ctypes
import importlib.util
import re
import shutil
import sys
import tempfile
import unittest
import uuid
from ctypes import byref, wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from convert_win.formats import EXT_TYPE, QUICK  # noqa: E402

HEADER = ROOT / "shell_ext" / "exts.h"
QUICK_HEADER = ROOT / "shell_ext" / "quick.h"
DLL = ROOT / "build" / "shell_ext" / "ConvertMenu.dll"

CLSID_TEXT = "{6D1C2F3A-8B47-4E59-9A0C-3F5B7E21D4C8}"
IID_ICLASSFACTORY = "{00000001-0000-0000-C000-000000000046}"
IID_IEXPLORERCOMMAND = "{A08CE4D0-FA25-44AB-B57C-C7B1C323E0B9}"
IID_IENUMEXPLORERCOMMAND = "{BDDACB60-7657-47AE-8445-D23E1ACF82AE}"
S_OK = 0
S_FALSE = 1
CLASS_E_CLASSNOTAVAILABLE = 0x80040111
COINIT_APARTMENTTHREADED = 0x2

# Values from the Windows SDK shobjidl_core.h (ECS_HIDDEN is 0x2, not 1).
ECS_ENABLED = 0
ECS_HIDDEN = 0x2
ECF_HASSUBCOMMANDS = 0x1
ECF_ISSEPARATOR = 0x8

OPEN_TITLE = "Open Convert..."
SEPARATOR = None  # the entry list marks the separator with None


def _load_generator():
    spec = importlib.util.spec_from_file_location("gen_ext_header", ROOT / "tools" / "gen_ext_header.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]


def to_guid(text):
    return GUID.from_buffer_copy(uuid.UUID(text).bytes_le)


class GeneratedTables(unittest.TestCase):
    def test_exts_header_lists_exactly_the_ext_type_keys(self):
        self.assertTrue(HEADER.exists(), "run tools\\build_shell_ext.ps1 (or tools\\gen_ext_header.py)")
        text = HEADER.read_text(encoding="utf-8")
        listed = re.findall(r'L"(\.[^"]*)"', text)
        expected = {f".{e.lower()}" for e in EXT_TYPE}
        self.assertEqual(len(listed), len(set(listed)), "duplicate entries in exts.h")
        self.assertEqual(set(listed), expected, "exts.h is stale: rerun tools\\gen_ext_header.py")
        self.assertIn(f"kExtCount = {len(expected)};", text)

    def test_quick_header_is_what_the_generator_writes(self):
        self.assertTrue(QUICK_HEADER.exists(), "run tools\\build_shell_ext.ps1 (or tools\\gen_ext_header.py)")
        gen = _load_generator()
        self.assertEqual(QUICK_HEADER.read_text(encoding="utf-8"), gen.build_quick(),
                         "quick.h is stale: rerun tools\\gen_ext_header.py")

    def test_exts_header_is_what_the_generator_writes(self):
        gen = _load_generator()
        self.assertEqual(HEADER.read_text(encoding="utf-8"), gen.build_exts(),
                         "exts.h is stale: rerun tools\\gen_ext_header.py")

    def test_every_quick_id_appears_in_quick_header(self):
        text = QUICK_HEADER.read_text(encoding="utf-8")
        for kind, ids in QUICK.items():
            for fmt_id in ids:
                self.assertIn(f'{{L"{fmt_id}", ', text, f"{kind} quick id {fmt_id} missing from quick.h")


@contextlib.contextmanager
def item_array(paths):
    """IShellItemArray (raw pointer) of real files, built from absolute PIDLs. Released on exit."""
    shell32 = ctypes.WinDLL("shell32")
    ole32 = ctypes.WinDLL("ole32")
    shell32.SHParseDisplayName.restype = ctypes.c_long
    shell32.SHParseDisplayName.argtypes = [ctypes.c_wchar_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
                                           ctypes.c_ulong, ctypes.c_void_p]
    shell32.SHCreateShellItemArrayFromIDLists.restype = ctypes.c_long
    shell32.SHCreateShellItemArrayFromIDLists.argtypes = [ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p),
                                                          ctypes.POINTER(ctypes.c_void_p)]
    ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    pidls = []
    psia = ctypes.c_void_p()
    try:
        for path in paths:
            pidl = ctypes.c_void_p()
            hr = shell32.SHParseDisplayName(str(path), None, byref(pidl), 0, None)
            if hr & 0xFFFFFFFF != S_OK:
                raise AssertionError(f"SHParseDisplayName {path}: {hr & 0xFFFFFFFF:#x}")
            pidls.append(pidl)
        array = (ctypes.c_void_p * len(pidls))(*[p.value for p in pidls])
        hr = shell32.SHCreateShellItemArrayFromIDLists(len(pidls), array, byref(psia))
        if hr & 0xFFFFFFFF != S_OK:
            raise AssertionError(f"SHCreateShellItemArrayFromIDLists: {hr & 0xFFFFFFFF:#x}")
        yield psia.value
    finally:
        release(psia.value)
        for pidl in pidls:
            if pidl.value:
                ole32.CoTaskMemFree(pidl)


def _com(ptr, index, restype, *argtypes):
    """Raw vtable call: the returned function takes the arguments after 'this'. index counts from IUnknown (0)."""
    vtbl = ctypes.cast(ctypes.c_void_p(ptr), ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
    proto = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)
    fn = proto(vtbl[index])
    return lambda *args: fn(ptr, *args)


def release(ptr):
    if ptr:
        _com(ptr, 2, ctypes.c_ulong)()


def hr_value(hr):
    return hr & 0xFFFFFFFF


def command_title(cmd):
    out = ctypes.c_void_p()
    hr = _com(cmd, 3, ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))(None, byref(out))
    if hr_value(hr) != S_OK:
        raise AssertionError(f"GetTitle: {hr_value(hr):#x}")
    try:
        return ctypes.wstring_at(out.value)
    finally:
        ctypes.WinDLL("ole32").CoTaskMemFree(out)


@unittest.skipUnless(DLL.exists(), "build\\shell_ext\\ConvertMenu.dll not built")
class ConvertMenuDll(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lib = ctypes.WinDLL(str(DLL))
        cls.lib.DllCanUnloadNow.restype = ctypes.c_long
        cls.lib.DllCanUnloadNow.argtypes = []
        cls.lib.DllGetClassObject.restype = ctypes.c_long
        cls.lib.DllGetClassObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
        ole32 = ctypes.WinDLL("ole32")
        ole32.CoInitializeEx.restype = ctypes.c_long
        ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        cls.com_hr = ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)

    @classmethod
    def tearDownClass(cls):
        if cls.com_hr >= 0:  # S_OK or S_FALSE: this thread holds one CoInitialize
            ctypes.WinDLL("ole32").CoUninitialize()

    def assert_unloadable(self):
        self.assertEqual(hr_value(self.lib.DllCanUnloadNow()), S_OK, "a COM object is still alive")

    def new_command(self):
        """IExplorerCommand from DllGetClassObject + IClassFactory::CreateInstance. Caller releases it (int pointer)."""
        clsid = to_guid(CLSID_TEXT)
        iid_factory = to_guid(IID_ICLASSFACTORY)
        iid_cmd = to_guid(IID_IEXPLORERCOMMAND)
        factory = ctypes.c_void_p()
        hr = self.lib.DllGetClassObject(byref(clsid), byref(iid_factory), byref(factory))
        self.assertEqual(hr_value(hr), S_OK)
        try:
            cmd = ctypes.c_void_p()
            # IClassFactory: QueryInterface 0, AddRef 1, Release 2, CreateInstance 3, LockServer 4
            hr = _com(factory.value, 3, ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(GUID),
                      ctypes.POINTER(ctypes.c_void_p))(None, byref(iid_cmd), byref(cmd))
            self.assertEqual(hr_value(hr), S_OK)
            return cmd.value
        finally:
            release(factory.value)

    def command_flags(self, cmd):
        flags = ctypes.c_int()
        hr = _com(cmd, 9, ctypes.c_long, ctypes.POINTER(ctypes.c_int))(byref(flags))
        self.assertEqual(hr_value(hr), S_OK)
        return flags.value

    def command_state(self, cmd, psia):
        state = ctypes.c_int(-1)
        hr = _com(cmd, 7, ctypes.c_long, ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_int))(
            psia, 0, byref(state))
        self.assertEqual(hr_value(hr), S_OK)
        return state.value

    def flyout(self, cmd):
        """Every entry of EnumSubCommands in order: the title, or SEPARATOR for the separator."""
        enum = ctypes.c_void_p()
        hr = _com(cmd, 10, ctypes.c_long, ctypes.POINTER(ctypes.c_void_p))(byref(enum))
        self.assertEqual(hr_value(hr), S_OK)
        entries = []
        try:
            while True:
                item = ctypes.c_void_p()
                fetched = ctypes.c_ulong(0)
                # IEnumExplorerCommand: QueryInterface 0, AddRef 1, Release 2, Next 3, Skip 4, Reset 5, Clone 6
                hr = _com(enum.value, 3, ctypes.c_long, ctypes.c_ulong, ctypes.POINTER(ctypes.c_void_p),
                          ctypes.POINTER(ctypes.c_ulong))(1, byref(item), byref(fetched))
                if fetched.value == 0:
                    self.assertEqual(hr_value(hr), S_FALSE)
                    break
                self.assertEqual(hr_value(hr), S_OK)
                try:
                    if self.command_flags(item.value) & ECF_ISSEPARATOR:
                        entries.append(SEPARATOR)
                    else:
                        entries.append(command_title(item.value))
                finally:
                    release(item.value)
        finally:
            release(enum.value)
        return entries

    def test_flags_have_subcommands(self):
        cmd = self.new_command()
        try:
            self.assertTrue(self.command_flags(cmd) & ECF_HASSUBCOMMANDS)
        finally:
            release(cmd)
        self.assert_unloadable()

    def test_flyout_before_any_state_is_only_open(self):
        cmd = self.new_command()
        try:
            self.assertEqual(self.flyout(cmd), [OPEN_TITLE])
        finally:
            release(cmd)
        self.assert_unloadable()

    def check_flyout(self, names, state, expected_titles):
        """names: files to create in the temp folder. Checks GetState then the flyout entries."""
        folder = Path(tempfile.mkdtemp(prefix="convert-shellext-"))
        cmd = None
        try:
            paths = []
            for name in names:
                path = folder / name
                path.write_bytes(b"")
                paths.append(path)
            cmd = self.new_command()
            with item_array(paths) as psia:
                self.assertEqual(self.command_state(cmd, psia), state)
                if state == ECS_HIDDEN:
                    return
                self.assertEqual(self.flyout(cmd), expected_titles)
        finally:
            release(cmd)
            shutil.rmtree(folder, ignore_errors=True)
        self.assert_unloadable()

    def test_png_flyout_skips_png(self):
        self.check_flyout(["picture.png"], ECS_ENABLED,
                          ["Convert to JPEG", "Convert to WebP", "Convert to PDF", SEPARATOR, OPEN_TITLE])

    def test_jpeg_flyout_skips_jpg_by_alias(self):
        self.check_flyout(["picture.jpeg"], ECS_ENABLED,
                          ["Convert to PNG", "Convert to WebP", "Convert to PDF", SEPARATOR, OPEN_TITLE])

    def test_mp3_and_mp4_use_the_audio_list(self):
        self.check_flyout(["song.mp3", "clip.mp4"], ECS_ENABLED,
                          ["Convert to MP3", "Convert to M4A (AAC)", "Convert to WAV", "Convert to FLAC",
                           SEPARATOR, OPEN_TITLE])

    def test_zip_alone_is_hidden(self):
        self.check_flyout(["archive.zip"], ECS_HIDDEN, [])

    def test_can_unload_when_no_objects_are_alive(self):
        self.assertEqual(self.lib.DllCanUnloadNow() & 0xFFFFFFFF, S_OK)

    def test_class_factory_for_our_clsid(self):
        clsid = to_guid(CLSID_TEXT)
        iid = to_guid(IID_ICLASSFACTORY)
        ppv = ctypes.c_void_p()
        hr = self.lib.DllGetClassObject(ctypes.byref(clsid), ctypes.byref(iid), ctypes.byref(ppv))
        self.assertEqual(hr & 0xFFFFFFFF, S_OK)
        self.assertTrue(ppv.value)
        # IUnknown::Release is slot 2 of the vtable; release the factory so the DLL can unload again.
        vtbl = ctypes.cast(ppv, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
        release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtbl[2])
        self.assertEqual(release(ppv.value), 0)
        self.assertEqual(self.lib.DllCanUnloadNow() & 0xFFFFFFFF, S_OK)

    def test_wrong_clsid_is_class_not_available(self):
        other = to_guid("{11111111-2222-3333-4444-555555555555}")
        iid = to_guid(IID_ICLASSFACTORY)
        ppv = ctypes.c_void_p(1)
        hr = self.lib.DllGetClassObject(ctypes.byref(other), ctypes.byref(iid), ctypes.byref(ppv))
        self.assertEqual(hr & 0xFFFFFFFF, CLASS_E_CLASSNOTAVAILABLE)
        self.assertFalse(ppv.value)


if __name__ == "__main__":
    unittest.main()
