# Builds the sparse MSIX for the Windows 11 context menu.
#   build\win11\Convert.msix   signed with a throw-away certificate (its private key is deleted at the end)
#   build\win11\Convert.cer    the public certificate; register.ps1 trusts it per user
#   build\win11\thumbprint.txt thumbprint of the signing certificate
#   build\win11\register.ps1, unregister.ps1
# Relative -Dll and -Out paths are taken from the repository root, so the script works from any folder.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Version,
    [string]$Dll = 'build\shell_ext\ConvertMenu.dll',
    [string]$Out = 'build\win11'
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Subject = 'CN=TheCreator0169'
$Clsid = '6D1C2F3A-8B47-4E59-9A0C-3F5B7E21D4C8'
$Sdk = 'C:\Program Files (x86)\Windows Kits\10\bin\10.0.19041.0\x64'

function Get-FullPath([string]$p) {
    if ([IO.Path]::IsPathRooted($p)) { return [IO.Path]::GetFullPath($p) }
    return [IO.Path]::GetFullPath((Join-Path $Root $p))
}

function Require-File([string]$p) {
    if (-not (Test-Path -LiteralPath $p -PathType Leaf)) { throw "required file not found: $p" }
}

$work = $null
$cert = $null
$keyHandle = $null
$failed = $false
try {
    if ($Version -notmatch '^\d+\.\d+\.\d+$') { throw "Version must look like 0.2.4, got '$Version'" }
    $Dll = Get-FullPath $Dll
    $Out = Get-FullPath $Out
    $template = Join-Path $Root 'win11\AppxManifest.xml'
    $logo = Join-Path $Root 'assets\logo.png'
    $py = Join-Path $Root '.venv-win\Scripts\python.exe'
    $makeappx = Join-Path $Sdk 'MakeAppx.exe'
    $signtool = Join-Path $Sdk 'SignTool.exe'
    foreach ($f in $template, $logo, $py, $makeappx, $signtool, $Dll,
                   (Join-Path $Root 'win11\register.ps1'), (Join-Path $Root 'win11\unregister.ps1')) {
        Require-File $f
    }

    # Supported extensions come from the one format table.
    Push-Location $Root
    try {
        $exts = @(& $py -c 'from convert_win.formats import EXT_TYPE; print(chr(10).join(sorted(EXT_TYPE)))')
        if ($LASTEXITCODE -ne 0) { throw "cannot read EXT_TYPE from convert_win.formats (exit $LASTEXITCODE)" }
    } finally {
        Pop-Location
    }
    $exts = @($exts | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    if ($exts.Count -eq 0) { throw 'no extensions found in convert_win.formats.EXT_TYPE' }
    foreach ($e in $exts) { if ($e -notmatch '^[a-z0-9]+$') { throw "unexpected extension '$e'" } }

    $items = ($exts | ForEach-Object {
        '            <desktop5:ItemType Type=".{0}"><desktop5:Verb Id="ConvertMenu" Clsid="{1}" /></desktop5:ItemType>' -f $_, $Clsid
    }) -join "`r`n"

    $tag = [guid]::NewGuid().ToString('N')
    $work = Join-Path ([IO.Path]::GetTempPath()) "convert-msix-$tag"
    $stage = Join-Path $work 'stage'
    New-Item -ItemType Directory -Path $stage, (Join-Path $stage 'Assets') | Out-Null
    $utf8 = New-Object System.Text.UTF8Encoding($false)

    # (a) staged manifest and Assets (the DLL stays in the external app folder)
    $xml = [IO.File]::ReadAllText($template).Replace('@VERSION@', $Version).Replace('@ITEMTYPES@', $items)
    $null = [xml]$xml   # fails loudly if the filled template is not well-formed
    [IO.File]::WriteAllText((Join-Path $stage 'AppxManifest.xml'), $xml, $utf8)

    $assetScript = Join-Path $work 'make_assets.py'
    [IO.File]::WriteAllText($assetScript, @'
import os
import sys
from PIL import Image, ImageOps
src, dst = sys.argv[1], sys.argv[2]
sizes = {"storelogo.png": 50, "Square44x44Logo.png": 44, "Square150x150Logo.png": 150}
img = Image.open(src).convert("RGBA")
for name, size in sizes.items():
    ImageOps.fit(img, (size, size), Image.Resampling.LANCZOS).save(os.path.join(dst, name), "PNG")
'@, $utf8)
    & $py -I $assetScript $logo (Join-Path $stage 'Assets')
    if ($LASTEXITCODE -ne 0) { throw "asset generation failed (exit $LASTEXITCODE)" }

    # Clear outputs of an earlier run, keep anything else in the folder.
    New-Item -ItemType Directory -Path $Out -Force | Out-Null
    foreach ($name in 'Convert.msix', 'Convert.cer', 'thumbprint.txt', 'register.ps1', 'unregister.ps1') {
        Remove-Item -LiteralPath (Join-Path $Out $name) -Force -ErrorAction SilentlyContinue
    }

    # (b) throw-away signing certificate, private key not exportable
    $cert = New-SelfSignedCertificate -Type Custom -Subject $Subject -KeyUsage DigitalSignature `
        -KeyAlgorithm RSA -KeyLength 3072 -HashAlgorithm SHA256 -NotAfter (Get-Date).AddYears(3) `
        -CertStoreLocation Cert:\CurrentUser\My -KeyExportPolicy NonExportable `
        -TextExtension @('2.5.29.37={text}1.3.6.1.5.5.7.3.3', '2.5.29.19={text}')
    $thumb = $cert.Thumbprint
    $certPath = Join-Path 'Cert:\CurrentUser\My' $thumb

    # Remember how the private key is stored, so it can be deleted explicitly in the finally block.
    $keyHandle = [System.Security.Cryptography.X509Certificates.RSACertificateExtensions]::GetRSAPrivateKey($cert)
    $keyName = $null; $keyProv = $null; $keyCsp = $null
    if ($keyHandle -is [System.Security.Cryptography.RSACng]) {
        $keyName = $keyHandle.Key.UniqueName
        $keyProv = $keyHandle.Key.Provider
    } elseif ($keyHandle -is [System.Security.Cryptography.RSACryptoServiceProvider]) {
        $keyCsp = $keyHandle.CspKeyContainerInfo
    } else {
        throw "unknown private key type $($keyHandle.GetType().FullName)"
    }

    # (c) public part only
    $cerPath = Join-Path $Out 'Convert.cer'
    Export-Certificate -Cert $cert -FilePath $cerPath -Type CERT | Out-Null

    # (d) pack and sign
    $msix = Join-Path $Out 'Convert.msix'
    & $makeappx pack /o /d $stage /nv /p $msix
    if ($LASTEXITCODE -ne 0) { throw "MakeAppx pack failed (exit $LASTEXITCODE)" }
    & $signtool sign /fd SHA256 /sha1 $thumb $msix
    if ($LASTEXITCODE -ne 0) { throw "SignTool sign failed (exit $LASTEXITCODE)" }

    # (e) check the signature. It is not trusted on this PC, so NotTrusted or UnknownError is expected.
    $sig = Get-AuthenticodeSignature -LiteralPath $msix
    if ($null -eq $sig.SignerCertificate) { throw "signature not readable: $($sig.Status) $($sig.StatusMessage)" }
    if ($sig.SignerCertificate.Thumbprint -ne $thumb) { throw 'signer thumbprint differs from the signing certificate' }
    $exported = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2 $cerPath
    if ($exported.Thumbprint -ne $thumb) { throw 'Convert.cer thumbprint differs from the signing certificate' }
    if (@('Valid', 'NotTrusted', 'UnknownError') -notcontains [string]$sig.Status) {
        throw "unexpected signature status $($sig.Status): $($sig.StatusMessage)"
    }
    Write-Output "signature status: $($sig.Status) (expected until the certificate is trusted)"
    [IO.File]::WriteAllText((Join-Path $Out 'thumbprint.txt'), $thumb + "`r`n", $utf8)

    # (f) scripts that ship with the package
    Copy-Item -LiteralPath (Join-Path $Root 'win11\register.ps1') -Destination $Out
    Copy-Item -LiteralPath (Join-Path $Root 'win11\unregister.ps1') -Destination $Out
    Write-Output "built $msix (certificate $thumb)"
} catch {
    [Console]::Error.WriteLine("make_msix failed: $($_.Exception.Message)")
    $failed = $true
} finally {
    # (g) the signing key must not survive the build
    if ($null -ne $cert) {
        $thumb = $cert.Thumbprint
        $certPath = Join-Path 'Cert:\CurrentUser\My' $thumb
        $keyLeft = $null
        if (Test-Path -LiteralPath $certPath) { Remove-Item -LiteralPath $certPath -Force -ErrorAction Continue }
        if ($keyHandle -is [System.Security.Cryptography.RSACng]) {
            # Delete the key itself even if the certificate removal failed, then check it is really gone.
            try {
                if ([System.Security.Cryptography.CngKey]::Exists($keyName, $keyProv)) {
                    $k = [System.Security.Cryptography.CngKey]::Open($keyName, $keyProv)
                    try { $k.Delete() } finally { $k.Dispose() }
                }
            } catch { }
            $keyLeft = [System.Security.Cryptography.CngKey]::Exists($keyName, $keyProv)
        } elseif ($null -ne $keyCsp) {
            try {
                $p = New-Object System.Security.Cryptography.CspParameters($keyCsp.ProviderType, $keyCsp.ProviderName, $keyCsp.KeyContainerName)
                $r = New-Object System.Security.Cryptography.RSACryptoServiceProvider($p)
                $r.PersistKeyInCsp = $false
                $r.Clear()
            } catch [System.Security.Cryptography.CryptographicException] {
                # the container is already gone (the certificate removal deleted it)
            }
        }
        if ($null -ne $keyHandle) { $keyHandle.Dispose() }
        if (Test-Path -LiteralPath $certPath) { [Console]::Error.WriteLine("make_msix: could not delete the signing certificate $thumb"); $failed = $true }
        if ($keyLeft) { [Console]::Error.WriteLine("make_msix: the signing key $keyName is still on disk"); $failed = $true }
        Write-Output "signing certificate $thumb removed from Cert:\CurrentUser\My; key deleted: $(-not $keyLeft)"
    }
    if ($null -ne $work -and (Test-Path -LiteralPath $work)) { Remove-Item -LiteralPath $work -Recurse -Force }
}
if ($failed) { exit 1 }
exit 0
