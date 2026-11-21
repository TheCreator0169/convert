# Registers the Convert sparse package, in two steps. Ships next to Convert.msix and Convert.cer in the installer.
# Only touches Cert:\LocalMachine\TrustedPeople (certificate CN=TheCreator0169) and the package TheCreator0169.Convert.
# -AppDir: folder that holds Convert.exe and ConvertMenu.dll (the external location).
# -TrustOnly: step 1, elevated (administrator): trust the certificate, then stop.
# Without it: step 2, normal user: register the package for this account; the certificate must already be trusted.
param(
    [Parameter(Mandatory = $true)][string]$AppDir,
    [switch]$TrustOnly
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

$store = 'Cert:\LocalMachine\TrustedPeople'  # Windows refuses a package whose certificate is only in the per-user store (0x800B0109)

if ($TrustOnly) {
    # Step 1 of 2, run elevated by the installer: trust the certificate, drop older copies of ours, nothing else.
    if (-not (Test-Admin)) { Stop-Register '-TrustOnly needs an elevated (administrator) prompt' $null }
    try {
        Import-Certificate -FilePath $cerPath -CertStoreLocation $store | Out-Null
        Get-ChildItem -LiteralPath $store |
            Where-Object { $_.Subject -ceq $Subject -and $_.Issuer -ceq $Subject -and $_.Thumbprint -ne $thumb } |
            Remove-Item -Force -ErrorAction SilentlyContinue
    } catch {
        Stop-Register "cannot import the certificate into $store" $_.Exception.Message
    }
    Write-Output "trusted certificate $thumb ($store)"
    exit 0
}

# Step 2 of 2, normal user: the package registers for this account only.
if (-not (Test-Path -LiteralPath (Join-Path $store $thumb))) {
    Stop-Register 'the certificate is not trusted yet (the administrator step was declined or failed)' $null
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
    Stop-Register "Add-AppxPackage failed" $_.Exception.Message
}

Write-Output "registered $PkgName (certificate $thumb)"
exit 0
