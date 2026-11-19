"""v0.2.1 light theme: the resolved scheme, the saved setting, the light palette's contrast, the stylesheet, the
right-click Theme menu, and the arrow images. Qt is used for the window, the stylesheet and the menu; no test shows a window.

Settings live in a temp folder (APPDATA and LOCALAPPDATA are patched per test). theme.PALETTE is global: every test that
changes it restores the dark palette in addCleanup. Classes are unittest.TestCase subclasses; ChoosingMenu is a helper (no tests).
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from PIL import Image
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QMenu

from convert_win import settings, theme, ui

ROOT = Path(__file__).resolve().parent.parent
app = None


def setUpModule():
    global app
    app = QApplication.instance() or QApplication([])


def restore_dark(test):
    """Puts the dark palette and the dark stylesheet back, and clears any Qt colour scheme a test set."""
    def restore():
        ui.apply_theme(QApplication.instance(), "dark")
        QGuiApplication.styleHints().unsetColorScheme()
    test.addCleanup(restore)


def fresh_appdata(test):
    """A new APPDATA and LOCALAPPDATA folder for this test; returns the folder."""
    tmp = tempfile.TemporaryDirectory()
    test.addCleanup(tmp.cleanup)
    env = mock.patch.dict(os.environ, {"APPDATA": tmp.name, "LOCALAPPDATA": tmp.name})
    env.start()
    test.addCleanup(env.stop)
    return Path(tmp.name)


def lum(hex_colour):
    """WCAG relative luminance of a #rrggbb colour."""
    channels = [int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def ratio(a, b):
    """WCAG contrast ratio of two colours (1 to 21)."""
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


class ChoosingMenu(QMenu):
    """Helper: stands in for QMenu. exec() records the menu and triggers the action named `choose`, instead of showing it."""
    choose = None
    shown = None

    def exec(self, *args, **kwargs):
        ChoosingMenu.shown = self
        for act in self.actions():
            if ChoosingMenu.choose and act.text() == ChoosingMenu.choose:
                act.trigger()
        return None


class ThemeResolve(unittest.TestCase):
    def test_system_follows_the_windows_scheme(self):
        self.assertEqual(theme.resolve("system", "dark"), "dark")
        self.assertEqual(theme.resolve("system", "light"), "light")

    def test_unknown_scheme_is_light(self):
        self.assertEqual(theme.resolve("system", "unknown"), "light")
        self.assertEqual(theme.resolve("system", ""), "light")
        self.assertEqual(theme.resolve("system", None), "light")

    def test_fixed_setting_ignores_the_scheme(self):
        self.assertEqual(theme.resolve("dark", "light"), "dark")
        self.assertEqual(theme.resolve("dark", "unknown"), "dark")
        self.assertEqual(theme.resolve("light", "dark"), "light")
        self.assertEqual(theme.resolve("light", "unknown"), "light")


class SettingsTheme(unittest.TestCase):
    def setUp(self):
        self.appdata = fresh_appdata(self)
        (self.appdata / "Convert").mkdir()
        self.file = self.appdata / "Convert" / "settings.json"

    def write(self, data):
        self.file.write_text(json.dumps(data), "utf-8")

    def test_only_the_exact_values_are_kept(self):
        for value in ("system", "dark", "light"):
            with self.subTest(value=value):
                self.write({"theme": value})
                self.assertEqual(settings.load()["theme"], value)

    def test_other_strings_load_as_system(self):
        for value in ("Dark", "LIGHT", " dark", "light ", "auto", "", "darkish"):
            with self.subTest(value=value):
                self.write({"theme": value})
                self.assertEqual(settings.load()["theme"], "system")

    def test_wrong_type_or_missing_loads_as_system(self):
        for value in (None, True, False, 0, 1, ["dark"], {"theme": "dark"}, 1.0):
            with self.subTest(value=value):
                self.write({"theme": value})
                self.assertEqual(settings.load()["theme"], "system")
        self.write({"trash_originals": True})  # no theme key at all
        self.assertEqual(settings.load()["theme"], "system")

    def test_no_settings_file_loads_as_system(self):
        self.assertFalse(self.file.exists())
        self.assertEqual(settings.load()["theme"], "system")

    def test_save_then_load_round_trip(self):
        for value in ("dark", "light", "system"):
            with self.subTest(value=value):
                st = settings.load()
                st["theme"] = value
                settings.save(st)
                self.assertEqual(json.loads(self.file.read_text("utf-8"))["theme"], value)
                self.assertEqual(settings.load()["theme"], value)


class LightContrast(unittest.TestCase):
    """WCAG ratios of the light palette only. The dark palette is left as it is (known failures, decided by the user)."""
    L = theme.LIGHT

    def test_text_on_background_and_panel(self):
        for bg in ("bg", "panel"):
            with self.subTest(bg=bg):
                self.assertGreaterEqual(ratio(self.L["text"], self.L[bg]), 4.5)

    def test_muted_on_background_panel_and_tile(self):
        for bg in ("bg", "panel", "tile"):
            with self.subTest(bg=bg):
                self.assertGreaterEqual(ratio(self.L["muted"], self.L[bg]), 4.5)

    def test_accent_text_on_accent(self):
        self.assertGreaterEqual(ratio(self.L["accent_text"], self.L["accent"]), 4.5)

    def test_accent_on_background_and_tile(self):
        for bg in ("bg", "tile"):
            with self.subTest(bg=bg):
                self.assertGreaterEqual(ratio(self.L["accent"], self.L[bg]), 4.5)

    def test_error_and_ok_on_background_and_tile(self):
        for token in ("error", "ok"):
            for bg in ("bg", "tile"):
                with self.subTest(token=token, bg=bg):
                    self.assertGreaterEqual(ratio(self.L[token], self.L[bg]), 4.5)

    def test_border_on_background(self):
        self.assertGreaterEqual(ratio(self.L["border"], self.L["bg"]), 3)


class DarkPalette(unittest.TestCase):
    def test_dark_values_are_the_old_ones(self):
        self.assertEqual(theme.DARK["bg"], "#1b1d22")
        self.assertEqual(theme.DARK["panel"], "#252830")
        self.assertEqual(theme.DARK["border"], "#343844")
        self.assertEqual(theme.DARK["text"], "#e8eaf0")
        self.assertEqual(theme.DARK["muted"], "#9aa1b2")
        self.assertEqual(theme.DARK["tile"], "#2f3340")
        self.assertEqual(theme.DARK["accent"], "#4c8dff")
        self.assertEqual(theme.DARK["error"], "#ff6b6b")
        self.assertEqual(theme.DARK["ok"], "#4cd08a")


class Stylesheet(unittest.TestCase):
    def test_each_palette_has_its_background_and_a_tooltip_rule(self):
        for name, palette in (("dark", theme.DARK), ("light", theme.LIGHT)):
            with self.subTest(palette=name):
                sheet = theme.stylesheet(palette)
                self.assertIn(f"background: {palette['bg']}", sheet)
                self.assertIn("QToolTip", sheet)
                self.assertIn(f"background: {palette['panel']}; color: {palette['text']}; border: 1px solid {palette['border']}", sheet)

    def test_applied_light_sheet_uses_the_dark_arrow_files(self):
        restore_dark(self)
        ui.apply_theme(app, "light")
        sheet = app.styleSheet()
        self.assertIn("background: #f3f4f7", sheet)
        self.assertIn("QToolTip", sheet)
        self.assertRegex(sheet, r"url\([^)]*/chevron-dark\.png\)")
        self.assertRegex(sheet, r"url\([^)]*/chevron-up-dark\.png\)")
        self.assertNotRegex(sheet, r"url\([^)]*/chevron\.png\)")

    def test_applied_dark_sheet_uses_the_light_arrow_files(self):
        restore_dark(self)
        ui.apply_theme(app, "dark")
        sheet = app.styleSheet()
        self.assertIn("background: #1b1d22", sheet)
        self.assertRegex(sheet, r"url\([^)]*/chevron\.png\)")
        self.assertRegex(sheet, r"url\([^)]*/chevron-up\.png\)")
        self.assertNotRegex(sheet, r"url\([^)]*/chevron-dark\.png\)")


class ApplyThemeInPlace(unittest.TestCase):
    def test_palette_dict_changes_in_place(self):
        restore_dark(self)
        same = theme.PALETTE
        ui.apply_theme(app, "light")
        self.assertIs(theme.PALETTE, same)
        self.assertEqual(theme.PALETTE["bg"], "#f3f4f7")
        ui.apply_theme(app, "dark")
        self.assertIs(theme.PALETTE, same)
        self.assertEqual(theme.PALETTE["bg"], "#1b1d22")


class SchemeChange(unittest.TestCase):
    def setUp(self):
        self.win = SimpleNamespace(st={"theme": "system"}, update=mock.Mock(), list=mock.Mock(), update_notice=mock.Mock())

    def test_handler_reapplies_only_for_system(self):
        for setting in ("system", "dark", "light"):
            with self.subTest(setting=setting):
                self.win.st["theme"] = setting
                with mock.patch.object(ui, "_refresh_palette") as refresh:
                    ui._on_scheme_changed(app, self.win)
                if setting == "system":
                    refresh.assert_called_once_with(app, "system")
                    self.win.update.assert_called_once()
                else:
                    refresh.assert_not_called()
                    self.win.update.assert_not_called()
                self.win.update.reset_mock()

    def test_handler_never_sets_or_unsets_the_colour_scheme(self):
        restore_dark(self)
        hints = mock.MagicMock()
        for setting in ("system", "dark", "light"):
            with self.subTest(setting=setting):
                self.win.st["theme"] = setting
                with mock.patch.object(ui, "QGuiApplication") as qga:
                    qga.styleHints.return_value = hints
                    ui._on_scheme_changed(app, self.win)
                hints.setColorScheme.assert_not_called()
                hints.unsetColorScheme.assert_not_called()

    def test_system_handler_follows_the_new_scheme_and_fixed_one_keeps_its_palette(self):
        restore_dark(self)
        self.win.st["theme"] = "system"
        hints = mock.MagicMock()
        hints.colorScheme.return_value = Qt.ColorScheme.Light
        with mock.patch.object(ui, "QGuiApplication") as qga:
            qga.styleHints.return_value = hints
            ui._on_scheme_changed(app, self.win)
        self.assertEqual(theme.PALETTE["bg"], "#f3f4f7")
        ui.apply_theme(app, "dark")  # a fixed choice ignores a scheme change: the dark palette stays
        self.win.st["theme"] = "dark"
        with mock.patch.object(ui, "QGuiApplication") as qga:
            qga.styleHints.return_value = hints
            ui._on_scheme_changed(app, self.win)
        self.assertEqual(theme.PALETTE["bg"], "#1b1d22")


class ThemeMenu(unittest.TestCase):
    def setUp(self):
        self.appdata = fresh_appdata(self)
        restore_dark(self)
        ChoosingMenu.choose = None
        ChoosingMenu.shown = None
        patch = mock.patch.object(ui, "QMenu", ChoosingMenu)
        patch.start()
        self.addCleanup(patch.stop)

    def window(self, setting):
        (self.appdata / "Convert").mkdir(exist_ok=True)
        (self.appdata / "Convert" / "settings.json").write_text(json.dumps({"theme": setting}), "utf-8")
        win = ui.Window()
        self.addCleanup(win.close)
        return win

    def test_menu_has_a_label_and_three_exclusive_checkable_choices(self):
        win = self.window("system")
        win._theme_menu(QPoint(0, 0))
        menu = ChoosingMenu.shown
        self.assertIsNotNone(menu)
        label = menu.actions()[0]
        self.assertEqual(label.text(), "Theme")
        self.assertFalse(label.isEnabled())
        self.assertFalse(label.isCheckable())
        choices = [a for a in menu.actions() if a.isCheckable()]
        self.assertEqual([a.text() for a in choices], ["System", "Dark", "Light"])
        groups = {id(a.actionGroup()) for a in choices}
        self.assertEqual(len(groups), 1)
        self.assertIsNotNone(choices[0].actionGroup())
        self.assertTrue(choices[0].actionGroup().isExclusive())

    def test_checked_choice_matches_the_setting(self):
        for setting, label in (("system", "System"), ("dark", "Dark"), ("light", "Light")):
            with self.subTest(setting=setting):
                win = self.window(setting)
                win._theme_menu(QPoint(0, 0))
                checked = [a.text() for a in ChoosingMenu.shown.actions() if a.isCheckable() and a.isChecked()]
                self.assertEqual(checked, [label])

    def test_choosing_light_saves_it_and_changes_the_palette(self):
        win = self.window("system")
        ChoosingMenu.choose = "Light"
        win._theme_menu(QPoint(0, 0))
        self.assertEqual(win.st["theme"], "light")
        saved = json.loads((self.appdata / "Convert" / "settings.json").read_text("utf-8"))
        self.assertEqual(saved["theme"], "light")
        self.assertEqual(theme.PALETTE["bg"], "#f3f4f7")
        self.assertEqual(settings.load()["theme"], "light")


class ArrowAssets(unittest.TestCase):
    def test_dark_arrow_images_exist_and_are_20_by_20_with_alpha(self):
        for name in ("chevron-dark.png", "chevron-up-dark.png"):
            with self.subTest(name=name):
                path = ROOT / "assets" / name
                self.assertTrue(path.is_file())
                self.assertGreater(path.stat().st_size, 0)
                with Image.open(path) as im:
                    self.assertEqual(im.size, (20, 20))
                    alpha = im.convert("RGBA").getchannel("A")
                    self.assertGreater(alpha.getextrema()[1], 0)  # some pixels are not transparent

    def test_build_bundles_the_dark_arrow_images(self):
        text = (ROOT / "build.ps1").read_text("utf-8-sig")
        self.assertIn(r'--add-data "assets\chevron-dark.png;assets"', text)
        self.assertIn(r'--add-data "assets\chevron-up-dark.png;assets"', text)
        line = next(ln for ln in text.splitlines() if "--add-data" in ln and "chevron-dark.png" in ln)
        self.assertIn(r'--add-data "assets\chevron-up-dark.png;assets"', line)  # both on the same --add-data line
