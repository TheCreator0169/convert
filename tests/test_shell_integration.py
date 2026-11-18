import unittest
import winreg

from convert_win import shell_integration as si
from convert_win.formats import EXT_TYPE

TEST_BASE = r"Software\ConvertTest\Classes"  # never the real Software\Classes


def read(path):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as k:
        return winreg.QueryValueEx(k, "")[0]


def exists(path):
    try:
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CURRENT_USER, path))
        return True
    except OSError:
        return False


class ShellIntegration(unittest.TestCase):
    def tearDown(self):
        si.uninstall(TEST_BASE)
        for p in (TEST_BASE + r"\SystemFileAssociations", TEST_BASE, r"Software\ConvertTest"):
            si._delete(p)

    def test_install_writes_verb_and_command_for_every_extension(self):
        si.install(TEST_BASE, cmd='"x.exe" "%1"', icon="x.exe")
        for ext in EXT_TYPE:
            self.assertEqual(read(si._verb(TEST_BASE, ext)), "Convert")
            self.assertEqual(read(si._verb(TEST_BASE, ext) + r"\command"), '"x.exe" "%1"')

    def test_uninstall_leaves_nothing(self):
        si.install(TEST_BASE, cmd="c", icon="i")
        si.uninstall(TEST_BASE)
        self.assertFalse(exists(TEST_BASE + r"\SystemFileAssociations\.mp3"))

    def test_uninstall_keeps_foreign_verbs(self):
        si.install(TEST_BASE, cmd="c", icon="i")
        other = TEST_BASE + r"\SystemFileAssociations\.mp3\shell\Other"
        winreg.CloseKey(winreg.CreateKey(winreg.HKEY_CURRENT_USER, other))
        si.uninstall(TEST_BASE)
        self.assertTrue(exists(other))
        self.assertFalse(exists(si._verb(TEST_BASE, "mp3")))
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, other)

    def test_uninstall_twice_is_harmless(self):
        si.uninstall(TEST_BASE)
        si.uninstall(TEST_BASE)

    def test_default_command_quotes_the_file(self):
        cmd, _ = si.command()
        self.assertTrue(cmd.endswith('"%1"'))


if __name__ == "__main__":
    unittest.main()
