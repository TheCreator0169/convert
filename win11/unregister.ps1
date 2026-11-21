# Removes the Convert sparse package for the current user and the CN=TheCreator0169 certificates
# from TrustedPeople. Exit 0 even when there is nothing to remove.
# -Machine: also works on LocalMachine\TrustedPeople (needs an elevated prompt).
param(
    [switch]$Machine
)

$ErrorActionPreference = 'Stop'
$PkgName = 'TheCreator0169.Convert'
$Subject = 'CN=TheCreator0169'

function Stop-Unregister([string]$Reason, [string]$Detail) {
    [Console]::Error.WriteLine("unregister failed: $Reason")
    if ($Detail) { [Console]::Error.WriteLine($Detail) }
    exit 1
}

if ($Machine) {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $isAdmin = ([Security.Principal.WindowsPrincipal]$id).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $isAdmin) { Stop-Unregister '-Machine needs an elevated (administrator) prompt' $null }
}
$store = if ($Machine) { 'Cert:\LocalMachine\TrustedPeople' } else { 'Cert:\CurrentUser\TrustedPeople' }

$failed = $false
try {
    Get-AppxPackage -Name $PkgName -ErrorAction Stop |
        Where-Object { $_.Name -eq $PkgName } |
        Remove-AppxPackage -ErrorAction Stop
} catch {
    $failed = $true
    [Console]::Error.WriteLine("unregister: cannot remove ${PkgName}: $($_.Exception.Message)")
}

# Explorer's COM host (dllhost.exe) can keep ConvertMenu.dll loaded after the package is gone, which blocks the installer
# from replacing or deleting it. Stop only a host process (by PID) that really has this DLL loaded; never by name.
$dll = Join-Path (Split-Path -Parent $PSScriptRoot) 'ConvertMenu.dll'
foreach ($p in @(Get-Process -Name dllhost -ErrorAction SilentlyContinue)) {
    try {
        if (@($p.Modules | Where-Object { $_.FileName -eq $dll }).Count -gt 0) { Stop-Process -Id $p.Id -Force -ErrorAction Stop }
    } catch { }  # not ours, protected, or already gone
}

# The certificate is removed even if the package removal failed: the package no longer needs it once installed.
try {
    Get-ChildItem -LiteralPath $store |
        Where-Object { $_.Subject -ceq $Subject -and $_.Issuer -ceq $Subject } |  # ours: exact name, self-signed
        Remove-Item -Force -ErrorAction Stop
} catch {
    $failed = $true
    [Console]::Error.WriteLine("unregister: cannot remove the certificate from ${store}: $($_.Exception.Message)")
}

if ($failed) { exit 1 }
Write-Output "unregistered $PkgName (store $store)"
exit 0
