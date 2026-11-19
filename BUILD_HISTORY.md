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

## v0.1.4 (2026-11-18, published)

Contents: DOCX writer keeps lists, tables (merged, nested), links and pictures; DOCX reader lists footnotes and keeps nested list levels; ODT and RTF read with structure by own parsers (odfpy and striprtf removed from `requirements.txt`); PDF drawn page by page without Qt's page number, with the requested 15 mm margins (side margins narrower than before).
- `build.ps1 v0.1.4` at commit `6dd4e9b` (feature commit `b02f79c`, fix `da0eb63`); rebuilt once, the first build (`f7a646e`) is under `archives\`: PyInstaller one-folder + Inno Setup.
  - `Convert.exe` sha256 `fd9ef27113af5fa7994819a1e6d76c256194d9049af9c518a5e180b02e642320`
  - `Convert-Setup-v0.1.4.exe` sha256 `5cf02e8ef7276dc5981ad97095ccb6050c5db56f5159e1f8e89cf7990c9c9599`
  - Properties > Details read back on both files: version 0.1.4, copyright "Copyright (c) 2026 TheCreator0169. MIT License."
- Source tests: 123, 1 skipped, all pass on three runs after the fix (one earlier run showed 2 failures that did not come back and were not identified), with ffmpeg on the PATH.
- Frozen `--cli` in a temp profile: French DOCX to PDF (text, 1 image, 1 link, black text present) and to DOCX (Heading 1, bullet, 1 table, 1 picture, 1 hyperlink); hand-made ODT to PDF and RTF to PDF (text found, black text present). No Convert process left.
- Found by the user's test file (`Lorem ipsum.docx`, no numbering part): every DOCX without `word/numbering.xml` failed with an empty error since v0.1.3 (python-docx raises NotImplementedError). Fixed, regression test added, errors without a message now show the exception name. The published v0.1.3 setup has this bug. Frozen retest on a copy of that file: PDF, ODT, RTF, HTML, TXT all written, no page number, left margin 46 pt.
- Found while testing: Qt's `drawContents` drew white text in Windows dark mode (fixed with an explicit palette, pixel test added); an ODT zip handle left open (fixed with a `with` block).
- Not verified: install, right-click and uninstall with this installer, DOCX/ODT/RTF files made by Word or LibreOffice, the PDF and DOCX output by eye (one rendered PDF page was looked at), hardware encoders, SmartScreen (not signed).

## v0.1.5 (2026-11-18, published)

Contents: cancel stops image jobs between frames and document jobs between pages; animations above 500 frames or 400 million pixels are refused for multi-frame targets; failed files are listed one per line (selectable, wrapped); "Open log folder" button; "Cancelling..." message.
- `build.ps1 v0.1.5` at commit `6a036b1` (feature commit `368ea83`): PyInstaller one-folder + Inno Setup.
  - `Convert.exe` sha256 `7b0728396ef5a3e49c54a5150878703ca803f57f4dcaf7fe97e90f56b0b0a7b2`
  - `Convert-Setup-v0.1.5.exe` sha256 `6089f79631985ccc2aac06896b54af72fe1b1d5a3794283cb32a34146002e372`
  - Properties > Details read back on both files: version 0.1.5, copyright "Copyright (c) 2026 TheCreator0169. MIT License."
- Source tests: 132, 1 skipped, all pass on two runs, with ffmpeg on the PATH.
- Source window check (offscreen): a 200-frame 60 MB GIF to WebP, Cancel pressed after 0.4 s, finished in 0.44 s with "Cancelled.", no output, source kept.
- Frozen `--cli` in a temp profile: a 600-frame GIF to PDF is refused (exit 1, log says "animation too large"), a 6-frame GIF to WebP is written. No Convert process left.
- Not verified: Cancel and the error list in the frozen window (no GUI automation here: the user's test), install, right-click and uninstall with this installer, hardware encoders, SmartScreen (not signed).


## v0.1.6 (2026-11-19, not tagged, not published)

- Commits `c8189db` (feature), `242364b` (a video file also offers the audio formats: found by the user in the window, the first build only had it in `--cli`), then the history. Rebuilt with `build.ps1 v0.1.6`; the first build was never published.
- Convert.exe sha256 `cc91d0732597a31ebdc7cd0b144ce399e00753407f0d923a16865cea9ed5d78a`.
- Convert-Setup-v0.1.6.exe sha256 `d5d6e1a1dd648047c97ef23415992d660dde013432677190c18f57783f2b0201`.
- New: "Audio track" (1-4) and "Keep subtitles" options, error for a missing track, picture-subtitle warning, `tests/test_encoders.py` (every audio id and video format converted for real).
- Tests in source mode: 147, 1 skipped, all pass, ffmpeg on the PATH, not under `QT_QPA_PLATFORM=offscreen` (PDF text is empty there).
- Frozen `--cli` in a temp profile on a 2-audio-track MKV: mp3, mp4, mp4-hevc (output checked: hevc + aac) and wma all exit 0; runtime log has no errors; no Convert process left.
- Not verified: the new options in the frozen window, subtitles in the frozen build, hardware encoders, install, right-click and uninstall with this installer, SmartScreen (not signed).

## v0.1.7 (2026-11-19, not tagged, not published)

- Commit `85397d5` (feature), then the history commit. Built with `build.ps1 v0.1.7`, which now runs `tools/smoke_frozen.py` before the installer is made.
- Convert.exe sha256 `64655a85796d2771e57cce3753779b43e2af060183bc0d57e79a499b274395ae`.
- Convert-Setup-v0.1.7.exe sha256 `a187c7cb0459f0ee5b81fb701613ef13f3691506e5314b42503887cf2d9e0fbb`.
- New: `tests/test_coverage_gaps.py`, the frozen smoke test in the build, `.github/workflows/tests.yml` and README badge, software fallback when a hardware encoder refuses a video (NVENC and a 96x64 clip: found by the smoke test).
- Tests in source mode: 164, 1 skipped, all pass, ffmpeg on the PATH.
- Frozen smoke test (inside the build, temp profile): image to WebP, txt to PDF, md to DOCX, DOCX to PDF, PDF to PNG and TXT, MP4 to MP3, MKV and GIF all exit 0 with a non-empty output; runtime log frozen and free of errors.
- Not verified: the CI on GitHub (never run; `test_single_instance` may fail on the runner), H9 hashes (needs pip-tools), the window, install, right-click and uninstall with this installer, SmartScreen (not signed).

## v0.1.8 (2026-11-19, tagged and published)

- Commits `b202d67` (fix), `f709cf9` (version 0.1.8), then the history. Built with `build.ps1 v0.1.8`.
- Convert.exe sha256 `c0ecc3a439ef59ba8e05c433da9cf9605c57d75862af06e6941fa2bfe55454df`.
- Convert-Setup-v0.1.8.exe sha256 `f1a2b8d4763e5789fd1d1d47a4722db46fc14f302f2459b6025f62d7110617e3`.
- Fix: `unique_path` no longer follows a dangling symbolic link on Windows (found by the first CI run on v0.1.7); a process test no longer depends on the console encoding.
- Tests in source mode: 164, 1 skipped (the link test needs a link privilege), all pass, ffmpeg on the PATH. CI on `windows-latest` was green at `b202d67` (164 tests, the link test ran there).
- Frozen smoke test (inside the build, and rerun by hand): image to WebP, txt to PDF, md to DOCX, DOCX to PDF, PDF to PNG and TXT, MP4 to MP3, MKV and GIF all exit 0; runtime log frozen and free of errors; no Convert process left.
- Not verified: the link fix in the frozen exe (no link privilege here), the window, install, right-click and uninstall with this installer, hardware encoders, SmartScreen (not signed).

## v0.1.9 (2026-11-19, not tagged, not published)

- Commit `97bfe35` (installer and version), then the history. Built with `build.ps1 v0.1.9`.
- Convert.exe sha256 `6106b2014674af3183268165f9805a331d052bfed14be8219188c41caaa35b59`.
- Convert-Setup-v0.1.9.exe sha256 `760b1ef29269bfdf7fd09ccb7be5b9d53d91454dfb7ec570829a17f740651756`.
- Installer: license page (MIT), optional desktop shortcut (unchecked), English and French, `InstallDelete` of `{app}\_internal` on upgrade. No code change in the app.
- Real install round trip in the user's terminal (real HKCU), silent: v0.1.7 installed, then v0.1.8 over it, then v0.1.9 over that (a planted stale file in `_internal` was removed, right-click verb kept, no desktop shortcut), uninstall (entry, verb and app folder gone; the French "delete settings?" question appeared, user answered No), reinstall v0.1.9.
- Frozen smoke test inside the build passed. Source tests: 164 passed on v0.1.8 (app code unchanged since).
- Not verified: the installer pages in the window (license, language, shortcut box: user's eyes), the settings kept after uninstall, hardware encoders, SmartScreen (not signed). `/SUPPRESSMSGBOXES` does not hide the settings question.

## v0.1.10 (2026-11-19, not tagged, not published)

- Commit `(see git log)`: last page of the installer says whether ffmpeg is on PATH and gives `winget install Gyan.FFmpeg` when it is not (D3: ffmpeg stays external, nothing is downloaded). No change in the app.
- Convert.exe sha256 `186834bb3e9b3ddb5f779588d6b496a86bbd5c7463b63f13ce2bc2c198483565`.
- Convert-Setup-v0.1.10.exe sha256 `cddb181f4625de06a136a1481dbdc5b7b10b50b758101a765530716efccba183`.
- Verified: the installer compiles, frozen smoke test inside the build passed.
- Not verified: how the finish page looks (text may be cut off), the ffmpeg detection in a real wizard run, install and upgrade round trip with this setup.

## v0.1.11 (2026-11-19, not tagged, not published)

- Commits `f76673e` (smaller window, landscape drop box, restyled select), `2c6202a` (tiles, automatic height, version) and `780d553` (Advanced: labels without a dark box, selects and number fields styled like Convert to). Rebuilt after the last one: the first v0.1.11 hashes are gone, that build was never published. Built with `build.ps1 v0.1.11`.
- Convert.exe sha256 `2658036008e2f0bb2ddcebb82f27efc5a075315aa02707d64e6ba042fd972bc8`.
- Convert-Setup-v0.1.11.exe sha256 `278284e8bed9f1c7daa056add19f2661134a70765f2c5b6713e77182551ca79e`.
- Window: 440 px wide, height follows the content and cannot be dragged (no maximize button); files shown as wrapping tiles (type badge and name, 4 per row, the box grows to 3 rows then scrolls); hint centred in the box; restyled "Convert to" select with a chevron (`assets/chevron.png`, bundled), placeholder "Add files first". Fixed on the way: with a placeholder Qt no longer selects the first format by itself.
- Tests in source mode: 166, 1 skipped, all pass. Frozen smoke test inside the build passed; `chevron.png` is in the frozen bundle.
- Measured by grabbing the real window (native platform, 440 px): empty 314 px high, 1 file 406, 5 files 454, 13 files 524, with Advanced open 556.
- Not verified: how it looks on the user's screen (DPI scaling above 100% may widen the window), the frozen window itself, the install and upgrade round trip with this setup (installer script unchanged since v0.1.10), hardware encoders, SmartScreen.
