# Build history

## v0.1.0 (2026-11-18, not tagged, not committed)

- Final `build.ps1 v0.1.0` (after the Explorer-notify fix, commit `28479d6`): PyInstaller one-folder + Inno Setup 6.7.3.
  - `Convert.exe` sha256 `1d7d231b36f669005ca20a5add729021ae07ebd38952849c767828437b762061`
  - `Convert-Setup-v0.1.0.exe` sha256 `555c0a8ad31e5c821b56cb09575a2c9ecb51458a164b324defb119cf0a54c69c`
  - The round-trip checks below were done on the previous build (same installer script, no menu-notify call).
  - Earlier builds of the same version are under `archives\`.
- Source tests: 60 (54 with ffmpeg off the PATH, 6 media tests skipped then), all pass, 9 suites.
- Frozen, `--cli`: image, document and PDF families, wav to mp3/flac, mp4 to mp4/webm/gif/mp3, all written, no Traceback.
- **Real-registry round trip, run in the user's own terminal (checked there):** before 45 verbs, install dir, Start menu link, uninstall key, logs. After silent uninstall: 0 verbs, no install dir, no link, no uninstall key, no logs. After reinstall: all back (45 verbs). The user saw "Convert" in the real right-click menu and converted a .jpg to .webp (640 KB to 118 KB, same look). The PC is left with the app installed.
- **Correction (same day): the registry parts of the round trip below were done in the agent's private HKCU view, not the user's real one** (see `known-issues.md`). Files, the installer logic and the single-instance fix are real. The real install was redone from the user's terminal; the entry was then seen in the real registry (`Test-Path` True there).
- **Installer round trip on this PC (user's OK), per-user, silent:** install writes `%LOCALAPPDATA%\Programs\Convert`, a Start menu link, an uninstall entry and 45 HKCU verbs (command `"...\Convert.exe" "%1"`); upgrade over an existing install works; uninstall leaves 0 verbs, no install folder, no link, no uninstall entry, no logs. The silent uninstall keeps settings by default (`%APPDATA%\Convert`, never created in this run). The PC was left in its original state (app uninstalled).
- **Bug found by that test and fixed:** three Explorer-style simultaneous launches opened two or three windows (every process saw no server yet). Fixed with an atomic named mutex plus waiting for the first instance's pipe; after the fix three launches gave one process and one window. Guarded by `tests.test_single_instance`.
- Build script note: Inno Setup could not write into `dist\` ("file in use"); `build.ps1` compiles in `%TEMP%` and copies.
- Not verified: how Explorer shows the entry (Windows 11 "Show more options" expected), the window by eye, that all three forwarded files appear in the one window (process count only), hardware encoders on a real GPU, the "keep settings?" question answered by a person.

## v0.1.1 (2026-11-18, published)

Contents: data-safety fixes S1-S11 and hardening H1-H8, H10 (`docs\ROADMAP.md`), new logo, window icon, copyright in Properties > Details. H9 half done (versions pinned, no hashes).
- `build.ps1 v0.1.1` at commit `669ce20` (version commit `c9308df`): PyInstaller one-folder + Inno Setup.
  - `Convert.exe` sha256 `d1852970092c948eba3af330a8304b7f727b38fb48afd20942ca228f35e21464`
  - `Convert-Setup-v0.1.1.exe` sha256 `a602e73036a28a7ffaa977a3d090cc6d4d0854d5a3aec6bdb37fce69e49c3ba8`
  - Properties > Details read back on both files: company TheCreator0169, version 0.1.1, product Convert, copyright "Copyright (c) 2026 TheCreator0169. MIT License."
  - An earlier build of the same version (before the copyright fields) is under `archives\`.
- Source tests: 92, 1 skipped (symlinks need a privilege), all pass, with ffmpeg on the PATH.
- Frozen `--cli` in a temp profile: wav to mp3, mp4 to mp4/webm/gif, 3-page TIFF to PDF (3 pages), EXIF-rotated JPG to PNG (20x40 upright), Markdown to PDF (text found), scanned PDF to TXT refused with exit 1 and "no text found". Log has file names only, no folders. No Convert process left.
- Not verified: install, right-click and uninstall with this installer (needs the user's terminal), the window by eye (window icon, messages), hardware encoders, SmartScreen behaviour (not signed).

## v0.1.2 (2026-11-18, published)

Same code as v0.1.1 (commit `109ccd2`, which already held the security hardening); only the version number changes, so the release names match the roadmap. Built from branch `release-0.1.2`, version commit `77c4237`, without the v0.1.3 work.
- `build.ps1 v0.1.2`: PyInstaller one-folder + Inno Setup.
  - `Convert.exe` sha256 `4785471bc7be9ba826bda3e2ee684e129d5b9384f3caf1d0ccb0f5141cc8c434`
  - `Convert-Setup-v0.1.2.exe` sha256 `317f069fd243156f88197564d42235044e2fdf3f7553ba69fa4564b4bba54d6f`
  - Properties > Details read back on both files: version 0.1.2, company TheCreator0169, copyright "Copyright (c) 2026 TheCreator0169. MIT License."
- Source tests: 92, 1 skipped, all pass. Frozen `--cli` wav to mp3 works, log written, no Convert process left.
- Not verified: install, right-click and uninstall with this installer, the window by eye, hardware encoders, SmartScreen (not signed).

## v0.1.3 (2026-11-18, published)

Contents: DOCX reader keeps links, content controls, pictures, lists, nested and merged tables, localized heading styles; ffmpeg conversions warn on extra audio tracks and subtitles (original kept).
- `build.ps1 v0.1.3` at commit `493fcc8` (feature commit `e71ab4d`): PyInstaller one-folder + Inno Setup.
  - `Convert.exe` sha256 `f0b73515dc502f03c2b48279ed6cc232b8fdbd867e6a6c2acf4381954ce1818d`
  - `Convert-Setup-v0.1.3.exe` sha256 `86c23fb95c2f170513c41afa4ab648da03aa011877ccb9df32138c89341ff724`
  - Properties > Details read back on both files: version 0.1.3, copyright "Copyright (c) 2026 TheCreator0169. MIT License."
- Source tests: 104, 1 skipped, all pass, with ffmpeg on the PATH.
- Frozen `--cli` in a temp profile: French DOCX (title style "Titre 1", link, bullet, picture, table) to PDF: all four texts found, 1 image, 1 link. Log written, no Convert process left.
- Not verified: frozen audio/video warnings (the windowed exe prints no warning; covered in source tests only), install, right-click and uninstall with this installer, the PDF by eye, DOCX files made by Word or LibreOffice, hardware encoders, SmartScreen (not signed).

## v0.1.4 (2026-11-18, not tagged, not published)

Contents: DOCX writer keeps lists, tables (merged, nested), links and pictures; DOCX reader lists footnotes and keeps nested list levels; ODT and RTF read with structure by own parsers (odfpy and striprtf removed from `requirements.txt`); PDF drawn page by page without Qt's page number, with the requested 15 mm margins (side margins narrower than before).
- `build.ps1 v0.1.4` at commit `f7a646e` (feature commit `b02f79c`): PyInstaller one-folder + Inno Setup.
  - `Convert.exe` sha256 `d6830b6190d6bb2fe570b77ead98352a025f0090d0d4f63542c1ae6d831d3bd6`
  - `Convert-Setup-v0.1.4.exe` sha256 `cf7c6a7e00978c7e02bfa910a7c636a8971105f85dade0e63dbd493e7fd65700`
  - Properties > Details read back on both files: version 0.1.4, copyright "Copyright (c) 2026 TheCreator0169. MIT License."
- Source tests: 121, 1 skipped, all pass, with ffmpeg on the PATH.
- Frozen `--cli` in a temp profile: French DOCX to PDF (text, 1 image, 1 link, black text present) and to DOCX (Heading 1, bullet, 1 table, 1 picture, 1 hyperlink); hand-made ODT to PDF and RTF to PDF (text found, black text present). No Convert process left.
- Found while testing: Qt's `drawContents` drew white text in Windows dark mode (fixed with an explicit palette, pixel test added); an ODT zip handle left open (fixed with a `with` block).
- Not verified: install, right-click and uninstall with this installer, DOCX/ODT/RTF files made by Word or LibreOffice, the PDF and DOCX output by eye (one rendered PDF page was looked at), hardware encoders, SmartScreen (not signed).

