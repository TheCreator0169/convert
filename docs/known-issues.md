# Known issues

One entry per gotcha: symptom, cause, fix or status.

## Open

- **ffmpeg and Inno Setup installed with winget** (2026-11-18, user's OK). A shell opened before that needs `$env:Path` refreshed (or a new window) to see ffmpeg; an app started from Explorer sees it after the next sign-in or Explorer restart.
- **Inno Setup cannot write the setup exe into `dist\`** ("file in use"); `build.ps1` builds in `%TEMP%` then copies. Cause not found (Desktop sync or virus scan suspected).
- **Windows 11 short context menu.** A registry verb appears under "Show more options" only. Top-level needs a sparse MSIX with `IExplorerCommand`. Not planned yet.
- **Legacy `.doc` input** needs LibreOffice; not supported in v0.1.0.
- **Animated GIF and multi-image HEIC** keep only the first frame (same limit as the macOS original).
- **Markdown** covers common syntax only: no footnotes, embedded HTML or images.

- **Document to PDF prints a page number** at the bottom of each page (Qt's `QTextDocument.print` does it). Not removed yet.

## Gotchas (keep in mind)

- **Qt offscreen has no fonts**: a PDF written under `QT_QPA_PLATFORM=offscreen` has no text. `test_ui_smoke` sets it in `setUpModule`, not at import. Document code must create `QApplication`, not `QGuiApplication`, or the window tests crash (exit 0xC0000409) when run in the same process.

- Python 3.14 is the default here; native packages (PyMuPDF, pillow-heif) may lack wheels. Use `py -3.13`.
- PyInstaller does not collect every plugin by itself (Qt platform plugin, `pillow_heif`, PyMuPDF): check each family in the frozen build.
- Explorer starts one process per selected file: the single-instance pipe collects them.
- A console child of a windowed exe opens a terminal window: every subprocess uses `CREATE_NO_WINDOW`.
