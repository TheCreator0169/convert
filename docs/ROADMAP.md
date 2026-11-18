# Convert for Windows: roadmap

Written 2026-11-18. Goal in one sentence: right-click one or more files in Explorer, choose **Convert**, pick a
format, and the file is converted next to the original, fully local, installed by one `Convert-Setup-vX.Y.Z.exe`.

Reference: the macOS app `newtonstudios/convert` (read only, not copied). Same features, Windows engines. No website,
no server, no analytics, no network code.

## Scope

| macOS original | Windows version |
|---|---|
| SwiftUI | Python 3.13 + PySide6 |
| Finder Quick Action | Explorer verb in `HKCU\Software\Classes\SystemFileAssociations\<ext>\shell\Convert` (no admin) |
| ffmpeg + VideoToolbox | ffmpeg with NVENC, QSV or AMF when present, else software |
| ImageIO + cwebp | Pillow, `pillow-heif`, `pillow-avif-plugin` |
| textutil + AppKit | `python-docx`, `striprtf`, `odfpy`, built-in Markdown to HTML, PDF through Qt |
| PDFKit / Core Graphics | PyMuPDF |
| Trash | `send2trash` (Recycle Bin) |
| `build.sh` | `build.ps1`: PyInstaller (one-folder) then Inno Setup |

Formats (same table as the original): audio (MP3, M4A, WAV, AIFF, FLAC, ALAC, Opus, OGG, WMA, AC3, WavPack, MP2),
video (MP4 H.264/HEVC/AV1, MOV ProRes, WebM VP9, MKV, GIF, or audio only), images (JPEG, PNG, HEIC, AVIF, WebP, TIFF,
GIF, BMP, PDF), documents (PDF, DOCX, ODT, RTF, TXT, HTML), PDF to PNG/JPEG/TXT.
Advanced options per format, remembered in `%APPDATA%\Convert\settings.json`.

Not in scope: the website, Excel/PowerPoint, legacy `.doc` (needs LibreOffice; listed in known-issues), code signing,
auto-update, any network call.

## Known platform limit (decide with the user before v0.3.0)

Windows 11 puts registry verbs in the classic menu ("Show more options" or Shift+F10), not in the short top menu.
Top-level placement needs a signed sparse MSIX package with a COM `IExplorerCommand`; that is a separate mission.
v0.3.0 ships the registry verb and says so in the README.

## Gates (every version)

1. Tracked tree clean, all test suites green before and after (see `convert-testing`). A bug fixed = a test that fails without the fix.
2. `reviewer` on the diff before the commit.
3. Visible change: user's OK on the element list before editing (`CLAUDE.md`).
4. Frozen build checked, not only source (`convert-build`).
5. `BUILD_HISTORY.md` entry, `docs/` updated, local commit. Tag only when the user says so.
6. Explorer menu and the window are validated by the user's eye.

## v0.1.0 Core and CLI (no window)

- `formats.py` (detect type, output formats, options), `process.py` (subprocess with CREATE_NO_WINDOW, cancel), `ffmpeg_conv.py`,
  `image_conv.py`, `doc_conv.py`, `pdf_conv.py`, `converter.py`, `main.py --cli`. (No `markdown_html.py`: Qt's `QTextDocument.setMarkdown` does it.)
- Output beside the original, numbered if the name exists, never overwritten.
- Done when: `main.py --cli mp3 song.opus` writes a playable file; every format family has a real conversion test.

## v0.2.0 Window

- PySide6 window: drag and drop, formats filtered by the selection, one progress bar, Advanced options, "move originals to
  Recycle Bin" switch, fixed English labels. Single instance: a second launch forwards its files to the first through a
  `QLocalServer` named pipe, so a multi-file right-click opens one window.
- Done when: all tabs and states construct from source and frozen, no Traceback in `%LOCALAPPDATA%\Convert\logs`.

## v0.3.0 Explorer menu and installer

- `shell_integration.py --install-menu / --uninstall-menu` writes and removes the HKCU verbs for the supported extensions only.
- `installer\convert.iss` (Inno Setup 6): per-user install to `%LOCALAPPDATA%\Programs\Convert`, Start menu entry, menu verbs,
  uninstall removes both, asks whether to keep `%APPDATA%\Convert`. Needs Inno Setup (`winget install JRSoftware.InnoSetup`, the user's OK).
- ffmpeg is not bundled (licence): the installer looks for it and the app tells the user how to get it. Decision for the user:
  bundle a GPL ffmpeg build or keep it external.
- Done when: install, right-click, convert, uninstall leaves no registry key and no file (checked in Windows Sandbox or a spare account).
