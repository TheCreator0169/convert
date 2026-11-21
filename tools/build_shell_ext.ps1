# Builds shell_ext\ConvertMenu.dll (native x64 IExplorerCommand) with VS 2019 BuildTools cl/rc/link.
# Usage: powershell -File tools\build_shell_ext.ps1 [-Out build\shell_ext]
param([string]$Out = 'build\shell_ext')

$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
$root = (Get-Location).Path

if (-not [IO.Path]::IsPathRooted($Out)) { $Out = Join-Path $root $Out }
$Out = [IO.Path]::GetFullPath($Out)
$obj = Join-Path $Out 'obj'
New-Item -ItemType Directory -Force -Path $obj | Out-Null

# 1. Regenerate the extension list from convert_win.formats.EXT_TYPE.
$py = Join-Path $root '.venv-win\Scripts\python.exe'
if (-not (Test-Path $py)) { throw "Missing venv python: $py" }
& $py (Join-Path $root 'tools\gen_ext_header.py')
if ($LASTEXITCODE -ne 0) { throw "gen_ext_header.py failed (exit $LASTEXITCODE)" }

# 2. Version values for the .rc, read from convert_win\version.py.
$verText = Get-Content -Raw -Encoding UTF8 (Join-Path $root 'convert_win\version.py')
if ($verText -notmatch 'CONVERT_VERSION\s*=\s*"(\d+)\.(\d+)\.(\d+)"') { throw 'Cannot read CONVERT_VERSION from convert_win\version.py' }
$maj = $Matches[1]; $min = $Matches[2]; $pat = $Matches[3]
$verH = @(
    "#define CONVERT_VERSION_NUM $maj,$min,$pat,0",
    "#define CONVERT_VERSION_STR `"$maj.$min.$pat.0`""
) -join "`r`n"
[IO.File]::WriteAllText((Join-Path $Out 'ver.h'), $verH + "`r`n", [Text.Encoding]::ASCII)

# 3. Import the VS 2019 x64 build environment (cl, rc, link, dumpbin, SDK paths).
$vcvars = 'C:\Program Files (x86)\Microsoft Visual Studio\2019\BuildTools\VC\Auxiliary\Build\vcvars64.bat'
if (-not (Test-Path $vcvars)) { throw "vcvars64.bat not found: $vcvars" }
$envDump = cmd /c "`"$vcvars`" >nul 2>&1 && set"
if ($LASTEXITCODE -ne 0) { throw "vcvars64.bat failed (exit $LASTEXITCODE)" }
foreach ($line in $envDump) {
    $k, $v = $line -split '=', 2
    if ($k -and -not $k.StartsWith('=') -and $null -ne $v) { Set-Item -Path "env:$k" -Value $v }
}
foreach ($tool in 'cl.exe', 'rc.exe', 'link.exe', 'dumpbin.exe') {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { throw "$tool not found after vcvars64" }
}

$src = Join-Path $root 'shell_ext\ConvertMenu.cpp'
$rc = Join-Path $root 'shell_ext\ConvertMenu.rc'
$def = Join-Path $root 'shell_ext\ConvertMenu.def'
$res = Join-Path $obj 'ConvertMenu.res'
$dll = Join-Path $Out 'ConvertMenu.dll'
$lib = Join-Path $obj 'ConvertMenu.lib'

# 4. Compile (static CRT: no vcruntime dependency).
& cl.exe /nologo /c /MT /O2 /GS /guard:cf /W4 /WX /EHsc /DUNICODE /D_UNICODE `
    /DWIN32_LEAN_AND_MEAN /DNOMINMAX /D_WIN32_WINNT=0x0A00 "/Fo$obj\" $src
if ($LASTEXITCODE -ne 0) { throw "cl.exe failed (exit $LASTEXITCODE)" }

# 5. Resource.
& rc.exe /nologo "/I$Out" "/fo$res" $rc
if ($LASTEXITCODE -ne 0) { throw "rc.exe failed (exit $LASTEXITCODE)" }

# 6. Link.
& link.exe /nologo /DLL /MACHINE:X64 /DYNAMICBASE /NXCOMPAT /HIGHENTROPYVA /GUARD:CF `
    "/DEF:$def" "/IMPLIB:$lib" "/OUT:$dll" (Join-Path $obj 'ConvertMenu.obj') $res `
    shell32.lib ole32.lib shlwapi.lib uuid.lib
if ($LASTEXITCODE -ne 0) { throw "link.exe failed (exit $LASTEXITCODE)" }

if (-not (Test-Path $dll)) { throw "Build reported success but $dll is missing" }

Write-Output "Built: $dll"
Get-FileHash -Algorithm SHA256 $dll | ForEach-Object { Write-Output "SHA256: $($_.Hash)  $($_.Path)" }
Write-Output '--- dumpbin /exports ---'
& dumpbin.exe /nologo /exports $dll
if ($LASTEXITCODE -ne 0) { throw "dumpbin failed (exit $LASTEXITCODE)" }
