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

- Commits `f76673e` (smaller window, landscape drop box, restyled select), `2c6202a` (tiles, automatic height, version) and `780d553` (Advanced: labels without a dark box, selects and number fields styled like Convert to). and `5ba697a` (bottom row: no gap under the progress bar, Clear as big as Convert, version centred; hidden while the result buttons show). Rebuilt after each: earlier v0.1.11 hashes are gone, none was published. Last rebuild: window title is just "Convert" (`edca630`). Tests: 168, 1 skipped. Built with `build.ps1 v0.1.11`.
- Convert.exe sha256 `c31f8c093dc930ac0450ef7b381c0b4a173f70f253225e84e733a43dd4d3a7e8`.
- Convert-Setup-v0.1.11.exe sha256 `838a1fdeb94ca7d3b7802c9454e08f724704226002e2bb058f013c26f5b163dd`.
- Window: 440 px wide, height follows the content and cannot be dragged (no maximize button); files shown as wrapping tiles (type badge and name, 4 per row, the box grows to 3 rows then scrolls); hint centred in the box; restyled "Convert to" select with a chevron (`assets/chevron.png`, bundled), placeholder "Add files first". Fixed on the way: with a placeholder Qt no longer selects the first format by itself.
- Tests in source mode: 166, 1 skipped, all pass. Frozen smoke test inside the build passed; `chevron.png` is in the frozen bundle.
- Measured by grabbing the real window (native platform, 440 px): empty 314 px high, 1 file 406, 5 files 454, 13 files 524, with Advanced open 556.
- Not verified: how it looks on the user's screen (DPI scaling above 100% may widen the window), the frozen window itself, the install and upgrade round trip with this setup (installer script unchanged since v0.1.10), hardware encoders, SmartScreen.

## v0.1.12 (2026-11-19, not tagged, not published)

- Commit `5ae128e`, then the history. Built with `build.ps1 v0.1.12`. Fixes from the user's test of v0.1.11.
- Convert.exe sha256 `de30c47866dc4c27a54854e4ab06d55b25132b6f8cb47a4f251d774088e1aa9e`.
- Convert-Setup-v0.1.12.exe sha256 `007f49b815aebcab6ef99bba8a8b064ec5b8b53f3ec71013987b131c66bf4e0d`.
- Fixed: switching Advanced on and off made the option names vanish (only the fields are hidden now, the names stay as a preview); the progress bar stayed full blue after a finished batch (it goes back to empty on Clear and when new files are added).
- Tests in source mode: 170, 1 skipped, all pass; the two new ones fail on the previous ui.py. Frozen smoke test inside the build passed.
- Measured on the real window: Advanced off, on, off again: 387, 433, 387 px high, names visible in the first and last; after Clear the window is 291 px and the bar value 0.
- Not verified: how it looks on the user's screen, the frozen window itself, install and upgrade with this setup.

## v0.1.13 (2026-11-19, not tagged, not published)

- Commits `11686c4` and `6d13974`, then the history. Built with `build.ps1 v0.1.13`.
- Convert.exe sha256 `6085edc1a8f8f50d2d39d45b489c5395fc6d23e32c22033eb3bf1b633ddeeae0`.
- Convert-Setup-v0.1.13.exe sha256 `ffe2c1a66cf9c587e73b58b2896027895d17e5c35c9e2024774c60acb5d3423e`.
- New: a daily update notice (`update_check.py`). Once per 24 h while the app is open, one anonymous GET to the GitHub releases API on a daemon thread; a newer release shows "A new version is available" on the right above the drop box (blue, underlined on hover), a click opens the release page (checked to be a page of this repo). Nothing is downloaded or installed. Off with `update_check: false` in `settings.json`. `CLAUDE.md` and the README no longer say "no network call". Plan: `docs\update-check-plan.md`.
- Tests in source mode: 181, 1 skipped, all pass, no real network (`urlopen` replaced); three mutations of the code were each caught. The first run of the full suite failed one old test (settings keys): fixed in `6d13974` before this build.
- Frozen exe, temp profile, real network: the log says "update check: latest release is v0.1.12" and the attempt time is saved; the process was stopped by its PID.
- Measured: the notice is 17 px high and the window grows from 291 to 314 px while it shows; it takes no room while hidden; aligned right.
- Not verified: the notice in the frozen window (the real network answer is "no newer release", so it stayed hidden), a corporate proxy, how it looks on the user's screen, install and upgrade with this setup.

## v0.1.14 (2026-11-19, not tagged, not published)

- Commit `77805d3`, then the history. Built with `build.ps1 v0.1.14`.
- Convert.exe sha256 `dac322330fb393077d41450076c8091e08045ad4dc65afb80485deda4b6b7a98`.
- Convert-Setup-v0.1.14.exe sha256 `2a735dcffd22ae5f68eb239b01bfdbc41628566ca75e6b84e8060f77a696b257`.
- Dependencies pinned with hashes (H9): `requirements.in` (direct pins) and `requirements.txt` generated with `pip-compile --generate-hashes --strip-extras --allow-unsafe` (pip-tools 7.7.0 in a scratch venv outside the repo; 676 hash lines). Verified: `pip install --require-hashes -r requirements.txt` in a fresh Python 3.13 venv (31 packages, exit 0) and the whole suite run with that venv: 182 tests OK. CI not yet seen with it.
- Update check hardened after a read-only audit by the security-auditor agent (its claims re-checked by hand: RecursionError, huge integers, HTTPException and unicode digits all escaped the old code): any exception means "no answer"; tags only ASCII digits, 6 at most; the page address must match `https://github.com/TheCreator0169/convert/releases/[A-Za-z0-9._/-]*` completely; the signal is connected as a queued connection; `update_check` is on only when true or absent (`"false"`, 0, null all mean off); a NaN or infinite last-check time is ignored; `settings.json` is written through a temp file and replaced. Not taken: refusing a redirect to http (the page check already limits the damage).
- Tests in source mode: 182, 1 skipped, all pass; the failure test no longer sleeps a fixed time.
- Real GPU test on this PC (NVIDIA GeForce RTX 3050): ffmpeg lists and passes the start-up test for h264_nvenc and hevc_nvenc (also av1_nvenc, av1_amf, av1_qsv, which Convert does not use). MP4 (H.264) and MP4 HEVC with hardware encoding on: 1280x720 and 320x240 convert and play as h264 and hevc; with it off libx264 and libx265 are chosen; a 96x64 clip makes NVENC refuse and Convert falls back to software with the warning. QSV and AMF were not tested (no such hardware here).
- Installed on the user's PC in the user's terminal, silently (v0.1.13 to v0.1.14): uninstall entry 0.1.14, right-click verb still there, exe version 0.1.14, settings kept. The installer pages were skipped by the silent mode.
- Not verified: the notice in a real window, a corporate proxy, the pages of this installer, QSV and AMF.

## v0.1.15 (2026-11-19)

- Commit `e2923d8`, then the history. Built with `build.ps1 v0.1.15`.
- Convert.exe sha256 `8395fcfcb6d435dfff29f95f0d5565236999c36012b9c845bb778dec67885388`.
- Convert-Setup-v0.1.15.exe sha256 `51154be5368cd74291954244e4971d8dce77ab069eee43d8fc8b3e17943a5a68`.
- Safety hardening, no visible change in the window: size caps for DOCX/ODT (unzipped, pictures encoded once, total budget) and for images (pixels, every frame); ffmpeg found only as `.exe`; network (UNC, `\?\GLOBALROOT`) paths refused; pipe read bounded; `settings.json` numbers clamped; an ODT with drawings, text boxes or pictures not carried over keeps the original and warns; the installer removes the Explorer verbs at uninstall even if `--uninstall-menu` fails (Pascal `RemoveMenuVerbs`, compiled, not run).
- Made by Haiku 5.5 agents (builders, tester, reviewer, security-auditor, windows-builder); the reviewer and auditor findings were re-checked and fixed before the commit. Decision D8 (refuse UNC) applied on the assistant's advice.
- Tests in source mode: 217, 1 skipped, all pass (35 new in `test_hardening_v0115.py`; the new tests fail without their fix, except two guards). Frozen smoke test: 10 of 10 checks.
- Not verified: install, upgrade and uninstall with this setup (RemoveMenuVerbs not run), the Explorer menu, real network shares, the sizes of `dist\` files read by the orchestrator (hashes taken from build.ps1 and `SHA256SUMS`).

## v0.1.16 (2026-11-19)

- Commits `3d59c24` and `841bcee`, then the history. Built with `build.ps1 v0.1.16` (the first build of this version, with an Add files button, was never published; the user asked to drop the button and make the drop box the control).
- Convert.exe sha256 `55eac947126cacb028fad4c85dfd0234520e471b73449f0bfab046632c84483c`.
- Convert-Setup-v0.1.16.exe sha256 `f56d37d8db97f8fd2da3c9d94f6c04db360ef57e17217dfccd590de49aaa6ac4`.
- New in the window: a click on empty space in the drop box opens the file picker (pointing-hand cursor, tooltip "Click to add files (Ctrl+O)", Ctrl+O too); a x on each tile and the Delete key remove one file (blocked while a batch runs); the drop box gets a 2 px dashed accent border during a drag; skipped files are named in a muted message ("Skipped (not a supported file type): ..."); Enter converts, Esc cancels a running batch; the last format is remembered per file type (`last_format` in `settings.json`, validated on load).
- Made by Haiku 5.5 agents (builder, tester, reviewer, windows-builder); reviewer findings re-checked and fixed (Delete removes only the selected tile, double click on the x, stale hover).
- Tests in source mode, real platform (not offscreen, which has no fonts and empties the PDFs): 276, 1 skipped, all pass (59 in `test_v0116.py`; 19 mutations caught). Frozen smoke test: 10 of 10 checks and one real `--cli mp3` conversion.
- Not verified: a real mouse and a real drag from Explorer, the cursor shape on screen, the Windows folder the picker opens in, install/upgrade/uninstall with this setup, the PyInstaller warnings file (access to `build\` denied to the agent), the Explorer menu.

## v0.1.17 (2026-11-19)

- Commit `0353d48`, then the history. Built with `build.ps1 v0.1.17`.
- Convert.exe sha256 `65be3a96317d14562607e523c3c1ca33b8e69e3b5bccd2b5da1edb6741c6b682`.
- Convert-Setup-v0.1.17.exe sha256 `29594286cd358d37bc088eac7d3c027a6d54e41d23d9bcdf9bc1c8869178c903`.
- New in the window: each tile shows Waiting / Working / Done / Failed (9 px word in the free strip; failed: 1 px red edge and the message in the tooltip); errors are tied to the file index, not its name; accessible names and descriptions, label buddies (no mnemonics), tab order; the update notice is reachable with Tab and opens the release page with Enter, Return or Space (1 px accent outline on keyboard focus only); Open folder opens a menu of full paths when the files went to 2-8 folders (first 8 and a count beyond), one folder opens directly, a folder that is gone or remote is not opened.
- Fixed after the review: Clear is blocked during a run; Enter on a focused button other than Convert no longer starts Convert; a click on the notice no longer draws the focus outline; a stale tile index is ignored.
- Made by Haiku 5.5 agents (ui-designer, two builders, tester, reviewer, windows-builder).
- Tests in source mode, real platform: 343, 1 skipped, all pass (67 new in `test_v0117.py`; 27 of 28 mutations caught, the survivor is equivalent). Frozen smoke test: 10 of 10 checks and one real `--cli mp3` conversion.
- Not verified: how the state words, the focus outline and the folder menu look on screen, a real screen reader (names are set and tested in code only), install/upgrade/uninstall with this setup, the PyInstaller warnings file (access to `build\` denied to the agent), the Explorer menu.

## v0.1.18 (2026-11-19)

- Commits `3313320` (installer) and `ea1409e` (tile fix), then the history. Built with `build.ps1 v0.1.18` (two builds of this version; the first, before the tile fix, was installed on the user's PC for the install test and never published).
- Convert.exe sha256 `748981e2cf59fe3ed10230e79a9abe12de165303f923f30238c5bb33f880ec96` (the installed copy on the user's PC has this hash, read from the file).
- Convert-Setup-v0.1.18.exe sha256 `9e4e456c63a287fb2fa331e386f604a31186722e8661fbc27aed35427138e286`.
- Installer: no Welcome, Directory or Ready page (License, Tasks, Installing, Finished remain); classic window size (`WizardSizePercent=100`); "Ouvrir Convert" in French; Setup and Uninstall check for a running Convert (mutex name built like the app builds it: first non-empty of LOGNAME, USER, LNAME, USERNAME, else the account name) and offer retry or cancel; silent runs never wait; the uninstall question about the settings is suppressible and defaults to keeping them. Found by the security-auditor and fixed before the build: that question hung a silent uninstall; the mutex name could differ from the app's.
- Window: the state word (Waiting / Working / Done / Failed) was drawn 3 px below the tile; it now sits inside the 58 px tile body (badge 8-24, name 26-42, state 42-54), with a pixel test.
- Tests in source mode: 344, 1 skipped, all pass. Frozen smoke test: all checks; direct `--cli mp3` conversion exit code 0.
- Install test on the user's PC (real HKCU, user's terminal, `.claude\test-installer-v0.1.18.ps1`): (1) install with pages over 0.1.14, exit 0, menu, shortcuts and settings kept; (2) setup with pages while Convert runs, exit 0, the user reported it perfect; (3) silent upgrade with Convert running, exit 0, no hang, Convert closed; (4) uninstall with pages, answer No to the settings question: exit 0, entry, exe, menu key and shortcuts removed, settings kept; silent reinstall exit 0, everything back. Settings differ from the backup only by the new `last_format` key.
- Not verified by the assistant: the text and size of each page, the French pages and the language of the running-Convert message (the user looked, said it was perfect; details not reported), `/VERYSILENT` uninstall, the Explorer menu after install, Windows 11 "Show more options".

## v0.2.0 (2026-11-20)

- Commit `ae717bb`, then the history. Built with `build.ps1 v0.2.0`.
- Convert.exe sha256 `a97bd3ae6b6a1c01a9fac50429c3a7046a9ec1958b9498b4c0afdc0627441312`.
- Convert-Setup-v0.2.0.exe sha256 `b4b6826d4dd304cadcfd512beffd2fc1e5e5fcb9172ee30e05d35bab8b951c36`.
- New: a HEIC with several images converted to a single-image format gives one file per image (`name_1.jpg`, `name_2.jpg`, ...). Each image uses its own EXIF; ICC kept; images over 178 million pixels are skipped with a warning (the original is then kept); limits 500 images and 400 million pixels in total; cancel removes the files already written; AVIF is not split.
- Fixed after the review: the EXIF of the first image could leak onto later images that have none (reproduced, test added; it fails on the old code).
- Made by Haiku 5.5 agents (builder, tester, reviewer, windows-builder).
- Tests in source mode: 363, 1 skipped, all pass (20 new in `test_v020.py`). Frozen smoke test: all checks passed.
- Install test on the user's PC (real HKCU, `.claude\test-installer-v0.2.0.ps1`): silent upgrade 0.1.18 to 0.2.0 exit 0, exe 0.2.0, uninstall entry 0.2.0, menu key present; the installed exe converted a synthetic 3-image HEIC into 3 jpg, exit 0.
- Not verified: a real iPhone HEIC; `still_count` seeks every frame (cost on large files); aggregate caps also apply to stills (a 3-image file of 150 million pixels each is refused); ICC and `_save_kw` have no dedicated test; an empty reserved file can remain if the process is killed; the Explorer menu; Windows 11 "Show more options".

## v0.2.1 (2026-11-20)

- Commit `8ce145e`, then the history. Built with `build.ps1 v0.2.1`.
- Convert.exe sha256 `ce7dde4262770f1ab323e7b089425ed50a7760eb57262a7f6055ba8f8143b32d`.
- Convert-Setup-v0.2.1.exe sha256 `cecceb63c850846a8dbb6ab6f043677b9dbbd225eeed9d1de93139ec894c1af8`.
- New: light theme and a Theme choice (System, Dark, Light; default System, follows Windows live). Right-click the version number, or Tab to it and press the Menu key / Shift+F10. Saved as `theme` in `settings.json` (exact strings only, else "system"). Light palette: bg #f3f4f7, panel #ffffff, border #7b8393, text #1c1f26, muted #555c6b, tile #e3e7ee, accent #1b5ccc, error #b42318, ok #17703f; every text pair at least 4.5:1. Dark rendering unchanged (pixel-identical tiles) except tooltips, which now follow the theme. New dark chevron images for the combo arrows in light mode (build.ps1 and Convert.spec list them; Convert.spec is git-ignored).
- Known dark-theme contrast shortfalls left as they are (user's choice): primary button text 3.2:1, "Working" 3.9:1, x hover 4.2:1, tile and progress edges.
- Review: keyboard access to the Theme menu was missing; fixed (focusable version label, accessible name, focus background).
- Made by Haiku 5.5 agents (ui-designer, builder, tester, reviewer, windows-builder).
- Tests in source mode: 390, 1 skipped, all pass (27 new in `test_v021.py`; 6 of 7 mutations caught, the survivor `setColorScheme(Light)` added in apply_theme is not caught). Frozen smoke test: all checks; `--cli jpg` exit 0; dark chevrons present in the exe.
- Install test on the user's PC: silent upgrade 0.2.0 to 0.2.1 exit 0, exe and uninstall entry 0.2.1; the user looked at the themes and approved the light theme.
- Not verified: real light Windows with System mode, live Windows mode change, the Windows title bar, Windows 11 style details, the Explorer menu. Existing users on a light Windows get the light theme after the update (default System).

## v0.2.2 (2026-11-20)

- Commit `505e29c`, then the history. Built with `build.ps1 v0.2.2`.
- Convert.exe sha256 `810c2ad9c507667ad59e19e6a8d6504878a404e9263e45318db9e096d100891e`.
- Convert-Setup-v0.2.2.exe sha256 `16e8105e9fcaf1092c417651837a05a1a7d97eed9cf6f9b74690fc5c1e7d6a76`.
- New: legacy Word 97-2003 `.doc` input, text only (own reader `convert_win\doc_binary.py` on `olefile` 0.47, BSD; no LibreOffice). A lossy warning is shown and the original is kept. Password-protected files are refused (Word 97 flag and Office 2007+ encrypted package). RTF, DOCX or ODT files named `.doc` are read as what they are; HTML, WordML or text named `.doc` are refused ("not a Word document"). Empty documents are refused ("the document has no text"). Explorer menu and installer uninstall list include `doc`.
- Limits: 64 MB file, 100000 pieces, 20 million characters, cancel honoured between pieces and inside field stripping; headers, footnotes and text boxes are not read; an empty cell in the middle of a table row is lost; a field instruction never closed hides text up to the next paragraph mark.
- Fixed after the review: `_strip_fields` was quadratic and could hang for minutes on a hostile file (20000 unmatched field marks plus 1 million characters: over 100 s before, 0.03 s now; marker-dense text still about 0.8 microseconds per marker, 12-15 s at 16-20 million characters); unclosed fields cut the text silently; an ODT renamed `.doc` showed a raw KeyError; an empty document gave "converter wrote no output".
- Dismissed from the review: decoding compressed pieces as cp1252 (the format specifies Windows-1252 for compressed text; Word stores non-Western text as UTF-16). Unverified with a non-Western file.
- Made by Haiku 5.5 agents (builder x2, tester x2, reviewer, windows-builder). Real Word 365 `.doc` fixtures were made with Word COM in the scratch folder and are not in the repo; tests build their own minimal compound files.
- Tests in source mode: 488, 1 skipped, all pass (98 in `test_v022.py`; 16 of 17 mutants caught in the first round, 7 of 7 in the second). Fuzz: 900 mutated real files and 1585 truncations plus 300 seeded flips: only ValueError, no hang. Frozen smoke test: all checks; frozen `--cli txt` and `--cli pdf` on real `.doc` files exit 0, protected exit 1.
- Install test on the user's PC (real HKCU, `.claude\test-installer-v0.2.2.ps1`): silent upgrade 0.2.1 to 0.2.2 exit 0, exe and uninstall entry 0.2.2, `.doc` verb key present; installed exe converted plain.doc and table.doc, refused protected.doc (exit 1), originals kept. The user tried the window with plain.doc and approved.
- Not verified: the lossy warning in the frozen console output (windowed exe), the Explorer menu entry for `.doc` on screen, Word 97/2000/2002 files, non-Western files, merged-cell tables, the olefile wheel hash against PyPI (taken from a pip download over HTTPS).

## v0.2.3 (2026-11-20)

- Commit `3e34378`, then the history. Built with `build.ps1 v0.2.3`. A cleanup release; the Windows 11 top-level menu was deferred (signing route and C++ toolchain undecided).
- Convert.exe sha256 `1cf43e468587455faf3079b5b8d00c6cf56d97be5a69792c1337521540f8e0ae`.
- Convert-Setup-v0.2.3.exe sha256 `c2eb56bc3828a6f1fc004881730460e60aa40622a8bf1c8f103ed3dec16bce94`.
- Changed: paths refused before any disk access: UNC and `\?\UNC`, device paths (`\.\`, `\??\`, `\?\GLOBALROOT`, `\?\Global`), every other `\?\` form except `\?\X:\` and `\?\Volume{GUID}\`, and mapped network drives (GetDriveTypeW = 4); `\wsl$` and `\wsl.localhost` stay allowed. A message per kind. The lossy warning (for example the `.doc` "text only" note) is now written to the log (folder scrubbed). The theme change handler ignores a window that is not built yet.
- Fixed after the audit: the WSL exemption used Unicode upper-casing (U+017F became "S", so `\w<U+017F>l$` passed as WSL and could reach the network); a relative name was checked before being resolved, so a working folder on a share passed. The check now works on the absolute path with ASCII-only upper-casing.
- CI: the v0.2.2 run on GitHub failed because Chocolatey timed out (504) while installing ffmpeg: 23 tests were skipped and 4 failed instead of skipping. Those 4 tests no longer need ffmpeg; the workflow retries the install up to 4 times, adds the Chocolatey folder to the PATH of later steps and fails with a clear message if ffmpeg is missing. `test_single_instance` no longer sleeps a fixed 6 s, waits for events, and no longer makes a real update-check request. The same flake had hit the first v0.2.0 run.
- Docs: README, ROADMAP, ROADMAP-next, known-issues, decisions and progress brought up to date; convert-testing skill updated (git-ignored).
- Made by Haiku 5.5 agents (scout, builder, docs agent, tester, security-auditor, windows-builder).
- Tests in source mode: 509, 1 skipped, all pass (21 in `test_v023.py`; they fail on the previous code). The 23 ffmpeg tests skip cleanly when ffmpeg is hidden from PATH. Frozen smoke test: all checks; frozen `--cli` png to jpg and `.doc` to txt exit 0; UNC refused in 0.7 s and a device path in 0.8 s.
- Install test on the user's PC (real HKCU, `.claude\test-installer-v0.2.3.ps1`): silent upgrade 0.2.2 to 0.2.3 exit 0; plain.doc to txt exit 0 with the warning in the log; protected.doc exit 1; UNC path refused in 1.0 s, exit 1; the user confirmed Convert starts and approved.
- Not verified: the new CI workflow (only a push can run it), a real mapped network drive, `subst` drives pointing at a share (reported as local by GetDriveTypeW), symlinks or junctions to a share, the disconnected-drive timing of GetDriveTypeW, the Explorer menu.

## v0.2.4 (2026-11-21)

- Commit `1573d3b`, then the history. Built with `build.ps1 v0.2.4`. The Windows 11 menu release.
- Convert.exe sha256 `454d8bca08e5658e3f134799f9d9acc79c6e412d9bf3d8651e4e9c13bb351874`.
- Convert-Setup-v0.2.4.exe sha256 `35d03592f87e11ab2a0f6a7506016856fdd92021f9aa3359bb3440eb9a6b8536`.
- Added: an optional Windows 11 menu entry (setup task `win11menu`, Windows 11 only, ticked by default). A sparse MSIX package `TheCreator0169.Convert` (`win11\AppxManifest.xml`, one `desktop10` entry for every file) and a native C++ `IExplorerCommand` DLL (`shell_ext\ConvertMenu.cpp`, built with VS 2019 Build Tools by `tools\build_shell_ext.ps1`): it hides itself unless a selected file has a supported extension and starts Convert.exe once with all the selected files. `tools\make_msix.ps1` signs the package with a throw-away self-signed certificate `CN=TheCreator0169`; the private key is deleted at the end of every build and the script fails if it is not.
- Installer: still `PrivilegesRequired=lowest`. Step 1 asks one UAC prompt (answer within about 2 minutes) to add the certificate to `LocalMachine\TrustedPeople`; step 2 registers the package for the user only. Uninstall removes the package, and asks one more UAC prompt to remove the certificate only when setup added it (`HKCU\Software\Convert\Win11Trust`). A declined prompt leaves the classic entry working. `SECURITY.md` is new and the README has a Security section.
- Found while testing on the user's PC: a certificate trusted for one user only (`CurrentUser\TrustedPeople`) is refused with 0x800B0109, although Microsoft Learn says it works, so the certificate goes to the machine store. ShellExecute with `runas` cannot see the Sysnative folder (code 3). `shellexec` entries must wait (`waituntilterminated`). `skipifdoesntexist` silently skipped `{sysnative}` entries. A UAC prompt left unanswered for about 2 minutes ends with code 1223. On Windows 11 build 26300 the entry first lands under "Applications extensions"; the user switches Convert on in Customize menu, App extensions to get it in the main menu (README says so). A sparse package looks for its logos in the app folder, so they are shipped there.
- Reviewed by a reviewer and a security-auditor agent: fixed the key deletion order and check, a dangling package on a failed uninstall, a DLL locked by `dllhost.exe` on upgrade (stopped by PID, only if it holds the DLL), a selection over 500 files, and an extension list guard test. Not followed: removing `AllowExternalContent` (Microsoft requires it for this package type).
- Made by Haiku 5.5 and Sonnet agents (builders, research, reviewer, security-auditor, docs).
- Tests in source mode: 522, 1 skipped, all pass (13 for the DLL and the package).
- Tested on the user's PC (real HKCU and certificate store): installer run with the UAC accepted registers the package (status Ok) and the certificate; the user saw Convert in "Applications extensions" and in the main menu after switching it on, with its logo, one window for several files, and no entry for a `.zip`; uninstall then reinstall (`.claude\test-uninstall-v0.2.4.ps1`): after uninstall no package, no certificate, no classic entry, no `HKCU\Software\Convert`, and the app folder still existed (contents not looked at); reinstall registered the package again.
- Not verified: other Windows 11 builds and Windows 10 (the option is skipped there), an upgrade from v0.2.3 through the setup window (not silent), the installer on a PC where the UAC prompt is declined, the second "Convert" in Show more options (classic entry plus the package), what stays in the app folder after uninstall, the Explorer menu for each of the 46 extensions.
