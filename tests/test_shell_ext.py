"""Tests for shell_ext: the generated extension list (pure Python) and the built ConvertMenu.dll (ctypes).

The DLL tests skip when build\\shell_ext\\ConvertMenu.dll is missing; build it with tools\\build_shell_ext.ps1.
Nothing here builds anything or touches the registry.
"""
import ctypes
import re
import sys
import unittest
import uuid
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from convert_win.formats import EXT_TYPE  # noqa: E402

HEADER = ROOT / "shell_ext" / "exts.h"
DLL = ROOT / "build" / "shell_ext" / "ConvertMenu.dll"

CLSID_TEXT = "{6D1C2F3A-8B47-4E59-9A0C-3F5B7E21D4C8}"
IID_ICLASSFACTORY = "{00000001-0000-0000-C000-000000000046}"
S_OK = 0
S_FALSE = 1
CLASS_E_CLASSNOTAVAILABLE = 0x80040111


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]


def to_guid(text):
    return GUID.from_buffer_copy(uuid.UUID(text).bytes_le)


class ExtsHeader(unittest.TestCase):
    def test_header_lists_exactly_the_ext_type_keys(self):
        self.assertTrue(HEADER.exists(), "run tools\\build_shell_ext.ps1 (or tools\\gen_ext_header.py)")
        text = HEADER.read_text(encoding="utf-8")
        listed = re.findall(r'L"(\.[^"]*)"', text)
        expected = {f".{e.lower()}" for e in EXT_TYPE}
        self.assertEqual(len(listed), len(set(listed)), "duplicate entries in exts.h")
        self.assertEqual(set(listed), expected, "exts.h is stale: rerun tools\\gen_ext_header.py")
        self.assertIn(f"kExtCount = {len(expected)};", text)


@unittest.skipUnless(DLL.exists(), "build\\shell_ext\\ConvertMenu.dll not built")
class ConvertMenuDll(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lib = ctypes.WinDLL(str(DLL))
        cls.lib.DllCanUnloadNow.restype = ctypes.c_long
        cls.lib.DllCanUnloadNow.argtypes = []
        cls.lib.DllGetClassObject.restype = ctypes.c_long
        cls.lib.DllGetClassObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]

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
