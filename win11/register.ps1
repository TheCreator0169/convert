# Registers the Convert sparse package for the current user (no admin by default).
# Ships next to Convert.msix and Convert.cer in the installer. Only touches the two TrustedPeople
# stores and the package TheCreator0169.Convert.
# -AppDir: folder that holds Convert.exe and ConvertMenu.dll (the external location).
# -Machine: trust the certificate for all users (LocalMachine); needs an elevated prompt.
param(
    [Parameter(Mandatory = $true)][string]$AppDir,
    [switch]$Machine
)

$ErrorActionPreference = 'Stop'
$PkgName = 'TheCreator0169.Convert'
$Subject = 'CN=TheCreator0169'

function Stop-Register([string]$Reason, [string]$Detail) {
    [Console]::Error.WriteLine("register failed: $Reason")
    if ($Detail) { [Console]::Error.WriteLine($Detail) }
    exit 1
}

function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    return ([Security.Principal.WindowsPrincipal]$id).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

try {
    $AppDir = (Resolve-Path -LiteralPath $AppDir -ErrorAction Stop).ProviderPath
} catch {
    Stop-Register "app folder not found: $AppDir" $null
}
foreach ($file in 'Convert.exe', 'ConvertMenu.dll') {
    if (-not (Test-Path -LiteralPath (Join-Path $AppDir $file) -PathType Leaf)) {
        Stop-Register "$file is missing from $AppDir" $null
    }
}

$cerPath = Join-Path $PSScriptRoot 'Convert.cer'
$msixPath = Join-Path $PSScriptRoot 'Convert.msix'
foreach ($file in $cerPath, $msixPath) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { Stop-Register "missing $file" $null }
}

# The thumbprint comes from the certificate itself, not from a text file.
try {
    $cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2 $cerPath
} catch {
    Stop-Register "cannot read $cerPath" $_.Exception.Message
}
if ($cert.Subject -ne $Subject) { Stop-Register "certificate subject is not $Subject" $cert.Subject }
$thumb = $cert.Thumbprint

if ($Machine -and -not (Test-Admin)) {
    Stop-Register '-Machine needs an elevated (administrator) prompt' $null
}
$store = if ($Machine) { 'Cert:\LocalMachine\TrustedPeople' } else { 'Cert:\CurrentUser\TrustedPeople' }

$alreadyTrusted = (Test-Path -LiteralPath (Join-Path 'Cert:\CurrentUser\TrustedPeople' $thumb)) -or
                  (Test-Path -LiteralPath (Join-Path 'Cert:\LocalMachine\TrustedPeople' $thumb))
$imported = $false
if (-not $alreadyTrusted) {
    try {
        $imported = $true
        Import-Certificate -FilePath $cerPath -CertStoreLocation $store | Out-Null
    } catch {
        Stop-Register "cannot import the certificate into $store" $_.Exception.Message
    }
}

# Replace an older Convert package. Its certificate is cleaned up only after the new one installs.
try {
    Get-AppxPackage -Name $PkgName -ErrorAction Stop |
        Where-Object { $_.Name -eq $PkgName } |
        Remove-AppxPackage -ErrorAction Stop
} catch {
    Stop-Register "cannot remove the previous $PkgName package" $_.Exception.Message
}

try {
    Add-AppxPackage -Path $msixPath -ExternalLocation $AppDir -ErrorAction Stop
} catch {
    # Do not leave a trusted certificate behind for a package that did not install.
    if ($imported) { Remove-Item -LiteralPath (Join-Path $store $thumb) -Force -ErrorAction SilentlyContinue }
    Stop-Register "Add-AppxPackage failed" $_.Exception.Message
}

# Remove superseded certificates: only CN=TheCreator0169 certs with another thumbprint.
try {
    Get-ChildItem -LiteralPath $store |
        Where-Object { $_.Subject -eq $Subject -and $_.Thumbprint -ne $thumb } |
        Remove-Item -Force -ErrorAction Stop
} catch { }  # an old certificate left behind is harmless; the new package is installed

Write-Output "registered $PkgName (certificate $thumb, store $store)"
exit 0
