"""Checks for the Windows 11 sparse package: manifest template, PowerShell scripts, and (when the shell
extension DLL is built) a real run of tools\\make_msix.ps1 into a temp folder. Never registers anything,
never runs Add-AppxPackage, never needs admin. The build step's signing certificate is removed again."""
import os
import re
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from convert_win.formats import EXT_TYPE

REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / "win11" / "AppxManifest.xml"
MAKE_MSIX = REPO / "tools" / "make_msix.ps1"
REGISTER = REPO / "win11" / "register.ps1"
UNREGISTER = REPO / "win11" / "unregister.ps1"
CPP = REPO / "shell_ext" / "ConvertMenu.cpp"
# CONVERT_SHELL_DLL lets a run point at another DLL (for example a placeholder in a temp folder).
DLL = Path(os.environ.get("CONVERT_SHELL_DLL") or REPO / "build" / "shell_ext" / "ConvertMenu.dll")
SUBJECT = "CN=TheCreator0169"
CLSID = "6D1C2F3A-8B47-4E59-9A0C-3F5B7E21D4C8"
NS_DESKTOP5 = "{http://schemas.microsoft.com/appx/manifest/desktop/windows10/5}"
NS_APPX = "{http://schemas.microsoft.com/appx/manifest/foundation/windows10}"
POWERSHELL = "powershell.exe"


def run_ps_file(script, *args):
    return subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script), *args],
        capture_output=True, text=True, timeout=900)


def run_ps_command(command):
    return subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True, text=True, timeout=120)


class ManifestTemplate(unittest.TestCase):
    def setUp(self):
        self.text = MANIFEST.read_text(encoding="utf-8")

    def test_parses_as_xml(self):
        ET.fromstring(self.text.encode("utf-8"))

    def test_has_placeholders(self):
        self.assertIn("@VERSION@", self.text)
        self.assertIn("@ITEMTYPES@", self.text)

    def test_identity_publisher_matches_scripts(self):
        root = ET.fromstring(self.text.encode("utf-8"))
        identity = root.find(NS_APPX + "Identity")
        self.assertEqual(identity.get("Publisher"), SUBJECT)
        self.assertEqual(identity.get("Name"), "TheCreator0169.Convert")
        for script in (MAKE_MSIX, REGISTER, UNREGISTER):
            self.assertIn(f"'{SUBJECT}'", script.read_text(encoding="utf-8"), script.name)

    def test_clsid_matches_shell_extension_source(self):
        if not CPP.exists():
            self.skipTest("shell_ext\\ConvertMenu.cpp does not exist yet")
        self.assertIn(CLSID.lower(), CPP.read_text(encoding="utf-8", errors="replace").lower())
        self.assertIn(f'Id="{CLSID}"', self.text)  # com:Class
        self.assertIn(CLSID, MAKE_MSIX.read_text(encoding="utf-8"))  # verb Clsid, filled by make_msix.ps1

    def test_com_and_context_menu_entries(self):
        self.assertIn('Category="windows.comServer"', self.text)
        self.assertIn('Category="windows.fileExplorerContextMenus"', self.text)
        self.assertIn('Path="ConvertMenu.dll"', self.text)
        self.assertIn('ThreadingModel="STA"', self.text)


class PowerShellScripts(unittest.TestCase):
    def test_scripts_parse(self):
        for script in (MAKE_MSIX, REGISTER, UNREGISTER):
            with self.subTest(script=script.name):
                env = dict(os.environ, PS_SCRIPT_PATH=str(script))
                proc = subprocess.run(
                    [POWERSHELL, "-NoProfile", "-NonInteractive", "-Command",
                     "$t = $null; $e = $null; "
                     "[void][System.Management.Automation.Language.Parser]::ParseFile($env:PS_SCRIPT_PATH, [ref]$t, [ref]$e); "
                     "if ($e) { $e | ForEach-Object { Write-Output $_.Message }; exit 1 }; exit 0"],
                    capture_output=True, text=True, timeout=120, env=env)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


@unittest.skipUnless(DLL.exists(), f"{DLL} is not built")
class InstallerExtensionList(unittest.TestCase):
    """convert.iss repeats the extension list (RemoveMenuVerbs); a new format must be added there too."""

    def test_iss_list_matches_ext_type(self):
        iss = (Path(__file__).resolve().parent.parent / "installer" / "convert.iss").read_text("utf-8")
        m = re.search(r"Exts := '([a-z0-9,]+)'", iss)
        self.assertIsNotNone(m, "RemoveMenuVerbs list not found in convert.iss")
        self.assertEqual(set(m.group(1).strip(",").split(",")), set(EXT_TYPE))


class BuildMsix(unittest.TestCase):
    def test_build_creates_signed_package_and_removes_key(self):
        with tempfile.TemporaryDirectory() as out:
            proc = run_ps_file(MAKE_MSIX, "-Version", "0.2.4", "-Dll", str(DLL), "-Out", out)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            msix = Path(out, "Convert.msix")
            cer = Path(out, "Convert.cer")
            self.assertTrue(msix.exists())
            self.assertTrue(cer.exists())
            thumb = Path(out, "thumbprint.txt").read_text(encoding="ascii").strip()
            self.assertRegex(thumb, r"^[0-9A-F]{40}$")

            # The private key is gone: no certificate with that thumbprint is left in CurrentUser\My.
            check = run_ps_command(
                f"Test-Path -LiteralPath 'Cert:\\CurrentUser\\My\\{thumb}'")
            self.assertEqual(check.stdout.strip(), "False", check.stdout + check.stderr)

            # The .cer holds the same certificate.
            cer_check = run_ps_command(
                f"(New-Object System.Security.Cryptography.X509Certificates.X509Certificate2 '{cer}').Thumbprint")
            self.assertEqual(cer_check.stdout.strip(), thumb)

            with zipfile.ZipFile(msix) as z:
                names = z.namelist()
                self.assertIn("AppxManifest.xml", names)
                self.assertIn("AppxSignature.p7x", names)
                self.assertIn("Assets/storelogo.png", names)
                manifest = ET.fromstring(z.read("AppxManifest.xml"))
            types = {el.get("Type") for el in manifest.iter(NS_DESKTOP5 + "ItemType")}
            self.assertEqual(types, {"." + e for e in EXT_TYPE})
            self.assertEqual(manifest.find(NS_APPX + "Identity").get("Version"), "0.2.4.0")


if __name__ == "__main__":
    unittest.main()
