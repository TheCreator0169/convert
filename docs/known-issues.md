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

- **The agent's own shell redirects HKCU writes into a private registry view** (2026-11-18). An install run from the Bash/PowerShell tools wrote the Explorer verbs where the user's Explorer never looked: the shell API in my process listed "Convert", `reg query` in the user's terminal said the key did not exist, and the user saw no menu entry for hours. Files are real, registry is not. **Run anything that must change the real registry (installer, `--install-menu`, `--uninstall-menu`, round-trip checks) through `run_in_terminal` and verify with a `Test-Path` typed there.** The "round trip" in `BUILD_HISTORY.md` proved the files and the installer logic, not the real registry.

- **Explorer caches context-menu verbs per file type** (2026-11-18): after the first install the entry was missing on a `.gif` in an already-open Explorer, although the shell API (`Shell.Application` `Verbs()`) in a fresh process listed it. `shell_integration` now sends `SHChangeNotify(SHCNE_ASSOCCHANGED)` after install and uninstall. Whether that was the cause is not confirmed until the user sees the entry.

- **Qt offscreen has no fonts**: a PDF written under `QT_QPA_PLATFORM=offscreen` has no text. `test_ui_smoke` sets it in `setUpModule`, not at import. Document code must create `QApplication`, not `QGuiApplication`, or the window tests crash (exit 0xC0000409) when run in the same process.

- Python 3.14 is the default here; native packages (PyMuPDF, pillow-heif) may lack wheels. Use `py -3.13`.
- PyInstaller does not collect every plugin by itself (Qt platform plugin, `pillow_heif`, PyMuPDF): check each family in the frozen build.
- Explorer starts one process per selected file: the single-instance pipe collects them.
- A console child of a windowed exe opens a terminal window: every subprocess uses `CREATE_NO_WINDOW`.

- Cancel cannot interrupt a single image or document conversion already running (checked between files, between PDF pages, and inside ffmpeg). Closing the window waits up to 30 s for it. Found by review 2026-11-18, planned v0.2.0.
- Audio/video: only the first audio track is kept (`0:a:0`) and subtitles are dropped; since v0.1.3 this is reported as a warning and the original is kept.
- A long animated GIF to PDF/WebP/TIFF loads every frame in memory; a very long one can fail with a memory error (nothing is trashed then).
- Single-instance pipe name is predictable (`Convert-GUI-<user>`): a second local account that creates it first can receive the file paths of this user's launches. Needs another local account; nothing converts without a click. Audit 2026-11-18, LOW, not planned.
- H9 is half done: versions are pinned in `requirements.txt`; hashes (`--require-hashes`) and a fresh-venv build need `pip-tools` (a download, the user's OK).
- DOCX reader (v0.1.3): text boxes, footnotes/endnotes, legacy objects (`w:pict`, `w:object`) and EMF/WMF/SVG pictures are not carried over (warning, original kept). Nested lists are flattened to one level; headers/footers are not read. ODT and RTF are still text only.
