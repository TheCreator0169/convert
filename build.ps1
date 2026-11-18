# Usage: powershell -File build.ps1 vX.Y.Z
# Archives the previous build, runs PyInstaller (one-folder), writes SHA256SUMS, builds the installer if Inno Setup exists.
param([Parameter(Mandatory)][string]$Version)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if ($Version -notmatch '^v\d+\.\d+\.\d+$') { throw "version must look like v0.1.0" }
if (git status --porcelain --untracked-files=no) { throw "tracked tree is not clean: commit first" }
$py = '.venv-win\Scripts\python.exe'
$have = & $py -c "from convert_win.version import CONVERT_VERSION as v; print('v' + v)"
if ($have -ne $Version) { throw "convert_win\version.py says $have, not $Version" }

$busy = Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -like "$PSScriptRoot\dist\*" }
if ($busy) { throw "dist\ is in use by PID $($busy.ProcessId -join ', '): stop them by PID first" }

if (Test-Path dist\Convert) {
    $arc = "archives\pre-$Version-build-$(Get-Date -Format yyyyMMdd-HHmm)"
    New-Item -ItemType Directory $arc -Force | Out-Null
    Move-Item dist\Convert $arc
}
# An old setup exe left in dist\ can still be locked (virus scan) when Inno Setup rewrites it: archive it too.
Get-ChildItem dist -Filter 'Convert-Setup-*.exe' -ErrorAction SilentlyContinue | ForEach-Object {
    $arc = "archives\old-setup-$(Get-Date -Format yyyyMMdd-HHmmss)"
    New-Item -ItemType Directory $arc -Force | Out-Null
    Move-Item $_.FullName $arc
}
& $py tools\make_icon.py | Out-Null
if ($LASTEXITCODE) { throw "make_icon failed" }
& $py -m PyInstaller --noconfirm --clean --windowed --name Convert --icon assets\convert.ico `
    --add-data "assets\logo.png;assets" --collect-all pillow_heif --collect-all pillow_avif convert.pyw
if ($LASTEXITCODE) { throw "PyInstaller failed" }

$rel = "archives\$Version-release"
New-Item -ItemType Directory $rel -Force | Out-Null
$files = @('dist\Convert\Convert.exe')
$iscc = (Get-Command iscc -ErrorAction SilentlyContinue).Source
if (-not $iscc -and (Test-Path "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe")) { $iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" }
if (-not $iscc -and (Test-Path "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe")) { $iscc = "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" }
if ($iscc) {
    # Writing the setup straight into dist\ (Desktop, synced or scanned) failed with "file in use": build in %TEMP%, then copy.
    $out = Join-Path $env:TEMP "convert-setup-$Version"
    Remove-Item $out -Recurse -Force -ErrorAction SilentlyContinue
    & $iscc "/DAppVersion=$($Version.TrimStart('v'))" "/O$out" installer\convert.iss
    if ($LASTEXITCODE) { throw "Inno Setup failed" }
    foreach ($try in 1..5) {
        try { Copy-Item "$out\Convert-Setup-$Version.exe" dist\ -Force -ErrorAction Stop; break }
        catch { if ($try -eq 5) { throw }; Start-Sleep 5 }
    }
    $files += "dist\Convert-Setup-$Version.exe"
} else { Write-Warning "Inno Setup not found: installer skipped (winget install JRSoftware.InnoSetup)" }
$files | ForEach-Object { $h = Get-FileHash $_ -Algorithm SHA256; "$($h.Hash.ToLower())  $(Split-Path $_ -Leaf)" } |
    Set-Content "$rel\SHA256SUMS-$Version.txt"
Get-Content "$rel\SHA256SUMS-$Version.txt"
