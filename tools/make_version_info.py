"""Writes the Windows version resource (Properties > Details) for Convert.exe: name, version, copyright.
Usage: python tools/make_version_info.py OUT.txt   (build.ps1 passes the file to PyInstaller --version-file)"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyInstaller.utils.win32.versioninfo import (FixedFileInfo, StringFileInfo, StringStruct, StringTable,
                                                 VarFileInfo, VarStruct, VSVersionInfo)

from convert_win.version import CONVERT_VERSION

COPYRIGHT = "Copyright (c) 2026 TheCreator0169. MIT License."


def build():
    v = tuple(int(n) for n in CONVERT_VERSION.split(".")) + (0,)
    strings = {"CompanyName": "TheCreator0169", "FileDescription": "Convert for Windows", "FileVersion": CONVERT_VERSION,
               "InternalName": "Convert", "LegalCopyright": COPYRIGHT, "OriginalFilename": "Convert.exe",
               "ProductName": "Convert", "ProductVersion": CONVERT_VERSION}
    return VSVersionInfo(
        ffi=FixedFileInfo(filevers=v, prodvers=v, mask=0x3F, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0),
        kids=[StringFileInfo([StringTable("040904B0", [StringStruct(k, s) for k, s in strings.items()])]),
              VarFileInfo([VarStruct("Translation", [1033, 1200])])])


if __name__ == "__main__":
    Path(sys.argv[1]).write_text(str(build()), "utf-8")
