# Known issues

One entry per gotcha: symptom, cause, fix or status.

## Open

- **ffmpeg and Inno Setup installed with winget** (2026-11-18, user's OK). A shell opened before that needs `$env:Path` refreshed (or a new window) to see ffmpeg; an app started from Explorer sees it after the next sign-in or Explorer restart.
- **Inno Setup cannot write the setup exe into `dist\`** ("file in use"); `build.ps1` builds in `%TEMP%` then copies. Cause not found (Desktop sync or virus scan suspected).
- **Windows 11 short context menu.** A registry verb appears under "Show more options" only. Top-level needs a sparse MSIX with `IExplorerCommand`. Not planned yet.
- **Legacy `.doc` input** needs LibreOffice; not supported in v0.1.0.
- **Animated GIF and multi-image HEIC** keep only the first frame (same limit as the macOS original).
- **Markdown** covers common syntax only: no footnotes, embedded HTML or images.


## Gotchas (keep in mind)

- **The agent's own shell redirects HKCU writes into a private registry view** (2026-11-18). An install run from the Bash/PowerShell tools wrote the Explorer verbs where the user's Explorer never looked: the shell API in my process listed "Convert", `reg query` in the user's terminal said the key did not exist, and the user saw no menu entry for hours. Files are real, registry is not. **Run anything that must change the real registry (installer, `--install-menu`, `--uninstall-menu`, round-trip checks) through `run_in_terminal` and verify with a `Test-Path` typed there.** The "round trip" in `BUILD_HISTORY.md` proved the files and the installer logic, not the real registry.

- **Explorer caches context-menu verbs per file type** (2026-11-18): after the first install the entry was missing on a `.gif` in an already-open Explorer, although the shell API (`Shell.Application` `Verbs()`) in a fresh process listed it. `shell_integration` now sends `SHChangeNotify(SHCNE_ASSOCCHANGED)` after install and uninstall. Whether that was the cause is not confirmed until the user sees the entry.

- **Qt offscreen has no fonts**: a PDF written under `QT_QPA_PLATFORM=offscreen` has no text. `test_ui_smoke` sets it in `setUpModule`, not at import. Document code must create `QApplication`, not `QGuiApplication`, or the window tests crash (exit 0xC0000409) when run in the same process.

- Python 3.14 is the default here; native packages (PyMuPDF, pillow-heif) may lack wheels. Use `py -3.13`.
- PyInstaller does not collect every plugin by itself (Qt platform plugin, `pillow_heif`, PyMuPDF): check each family in the frozen build.
- Explorer starts one process per selected file: the single-instance pipe collects them.
- A console child of a windowed exe opens a terminal window: every subprocess uses `CREATE_NO_WINDOW`.

- Cancel (v0.1.5) stops an image job between frames, a document job between pages, a PDF job between pages and ffmpeg at once. It cannot interrupt the decoding or saving of one single frame or page: a huge single image finishes that step first (the window says "Cancelling..."; nothing is left behind and nothing is trashed).
- Audio/video (v0.1.6): one audio track is kept, chosen by the "Audio track" option (1 to 4, default 1); a track the file does not have is an error, nothing is written. Subtitles are dropped unless "Keep subtitles" is on (MP4/MOV text subtitles, WebM WebVTT, MKV as they are). Picture subtitles (PGS, DVD) cannot go in MP4/MOV/WebM: dropped with a warning, MKV keeps them. Any dropped track or subtitle is a warning and the original is kept. No track names are shown in the window: the number is the position in the file.
- An animation kept as several frames (GIF/WebP/TIFF/PDF target) is refused above 500 frames or 400 million pixels in all (frames x width x height, about 1.6 GB as RGBA) with "animation too large"; nothing is trashed. Converting it to a single-frame format still works (first frame, with a warning).
- Single-instance pipe name is predictable (`Convert-GUI-<user>`): a second local account that creates it first can receive the file paths of this user's launches. Needs another local account; nothing converts without a click. Audit 2026-11-18, LOW, not planned.
- H9 is half done: versions are pinned in `requirements.txt`; hashes (`--require-hashes`) and a fresh-venv build need `pip-tools` (a download, the user's OK).
- DOCX reader (v0.1.4): text boxes, legacy objects (`w:pict`, `w:object`) and EMF/WMF/SVG pictures are not carried over (warning, original kept). Headers and footers are deliberately not read (they repeat on every page). Footnotes and endnotes are listed at the end as [n]. Nested lists keep up to 6 levels.
- DOCX writer (v0.1.4): lists (3 levels), tables (merged and nested), links, pictures, headings, bold and italic are written; fonts, colours, alignment, column widths and page setup are not.
- ODT reader (v0.1.4, own parser, odfpy removed): headings, bold/italic from named styles, links, lists, tables, footnotes, PNG/JPEG/GIF/BMP pictures. Not read: text frames, drawings, comments, tracked changes, styles set directly on paragraphs other than bold/italic. Tested with files built by hand and by Qt's writer, not with LibreOffice files.
- RTF reader (v0.1.4, own parser, striprtf removed): paragraphs, bold/italic, links, tables, unicode and code page characters. Headings, lists, pictures and styles are not interpreted (warning, original kept). Tested with hand-written RTF, not Word files.
- PDF from a document (v0.1.4) is drawn page by page with the margins from the options (15 mm) and no page number; the side margins are narrower than in v0.1.3, so a line holds more text.
- Hardware encoders (v0.1.7): a hardware encoder can refuse a video at encode time (NVENC refuses frames below about 128 px wide: "Nothing was written into output file"). Convert now retries once with the software encoder and warns "the hardware encoder failed on this video". Found by the frozen smoke test on a 96x64 clip; the test-encode at start-up uses 256x256 and cannot see this.
- CI (v0.1.7): `.github/workflows/tests.yml` runs the suite on `windows-latest` with ffmpeg from Chocolatey. Written and not yet run on GitHub: `test_single_instance` says it needs a real desktop session and may fail on the runner until seen. Pushing a workflow file needs a login with the `workflow` scope.
- The frozen smoke test (`tools/smoke_frozen.py`, run by `build.ps1` before the installer) converts one file of every family through `Convert.exe --cli` in a temp profile; it does not open the window or touch the registry.
- **Dangling link followed by `unique_path` (found 2026-11-19 by the first CI run, fixed after v0.1.7 was published, so v0.1.7 still has it).** On Windows `open(path, "xb")` follows a dangling symbolic link and creates the file it points to; a link named like the output (`a.jpg` next to `a.png`) made Convert write through it. Needs someone able to plant a link in the same folder. Fixed with `os.path.lexists` before the exclusive create; the test (`test_dangling_link_is_not_followed`) is skipped on this PC (no link privilege) and runs only on CI. Ships in the next version.
- CI first run (v0.1.7 push): 162 of 164 passed; the 2 failures were that link bug and a test that depended on the child's console encoding (fixed in the test).
