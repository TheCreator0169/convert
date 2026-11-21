# Undoes register.ps1, in two steps.
# Without a switch (normal user): remove the package TheCreator0169.Convert for this account and release ConvertMenu.dll.
# -CertOnly (elevated, administrator): remove our certificate (CN=TheCreator0169, self-signed) from Cert:\LocalMachine\TrustedPeople.
# Exit 0 even when there is nothing to remove.
param(
    [switch]$CertOnly
)

$ErrorActionPreference = 'Stop'
$PkgName = 'TheCreator0169.Convert'
$Subject = 'CN=TheCreator0169'
$store = 'Cert:\LocalMachine\TrustedPeople'

if ($CertOnly) {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $isAdmin = ([Security.Principal.WindowsPrincipal]$id).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $isAdmin) { [Console]::Error.WriteLine('unregister failed: -CertOnly needs an elevated (administrator) prompt'); exit 1 }
    try {
        Get-ChildItem -LiteralPath $store |
            Where-Object { $_.Subject -ceq $Subject -and $_.Issuer -ceq $Subject } |  # ours: exact name, self-signed
            Remove-Item -Force -ErrorAction Stop
    } catch {
        [Console]::Error.WriteLine("unregister: cannot remove the certificate from ${store}: $($_.Exception.Message)")
        exit 1
    }
    Write-Output "removed the certificate from $store"
    exit 0
}

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

if ($failed) { exit 1 }
Write-Output "unregistered $PkgName"
exit 0
