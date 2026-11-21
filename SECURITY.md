# Security

## Reporting a problem

Open an [issue](https://github.com/TheCreator0169/convert/issues) on this repository. If the details are sensitive, say so in the issue without the details and the author will arrange a private channel. Only the latest release is supported.

## What Convert does

- Converts files on your PC. Files never leave it. No telemetry.
- One network call: a daily anonymous request to the GitHub releases API (switch `update_check` in `settings.json`). It downloads and installs nothing.
- The original file is never overwritten.
- The installer needs no admin rights (only the optional Windows 11 menu step asks for one, see below) and is **not code-signed**, so Windows SmartScreen may warn. Check the SHA-256 shown on the release page against the file you downloaded.

## What the installer writes

| What | Where | Removed by |
|---|---|---|
| Program | `%LOCALAPPDATA%\Programs\Convert` | Uninstall |
| Classic right-click entries | `HKCU\Software\Classes\SystemFileAssociations\.<ext>\shell\Convert` | Uninstall |
| Settings, logs | `%APPDATA%\Convert`, `%LOCALAPPDATA%\Convert` | Uninstall (settings only if you say yes) |

## The Windows 11 menu option (Windows 11 only, ticked by default)

To put **Convert** in the short Windows 11 menu, Windows needs a signed package that gives the app an identity. The installer:

1. Shows **one administrator (UAC) prompt** and adds the certificate `CN=TheCreator0169` to **`Cert:\LocalMachine\TrustedPeople`**. Windows refuses a package whose certificate is only trusted for one account (error 0x800B0109), so this is machine-wide. It is the Trusted People store, **not** the Root store: it lets Windows install packages signed by this certificate, and does not make it a trusted authority for websites or other software. This is the only step that needs admin rights; the rest of Convert never does. Decline the prompt and nothing is added.
2. Registers the package `TheCreator0169.Convert` for your account only (`Add-AppxPackage -ExternalLocation <install folder>`). It holds a manifest and a small COM DLL, `ConvertMenu.dll` (class `{6D1C2F3A-8B47-4E59-9A0C-3F5B7E21D4C8}`), that only starts `Convert.exe` with the files you selected. The DLL opens no network connection and writes nothing.

**The signing key does not exist after the build.** Each release makes a new throw-away key, signs the package, and deletes the key, so nobody (including the author) can sign another package with that certificate. A different release uses a different certificate; the installer removes the old one.

**Limits you should know.**
- The certificate, package and DLL sit in your install folder, which only your account can write. Someone who can already write there runs as you and could do more directly. Convert does not defend against that.
- The upgrade step stops, by process ID, a Windows COM host process (`dllhost.exe`) only when it has `ConvertMenu.dll` loaded, so the DLL can be replaced.
- Because the certificate is machine-wide, it stays trusted for every account on the PC until it is removed. Uninstalling Convert asks for one more administrator prompt to remove it.
- If you untick the option, or decline the prompt, nothing above is added and the classic entry under **Show more options** keeps working.

### Remove it by hand

Uninstalling Convert does all of this. To do only the menu part, in a normal PowerShell:

```powershell
Get-AppxPackage TheCreator0169.Convert | Remove-AppxPackage
```

Then, in an administrator PowerShell, remove the certificate:

```powershell
Get-ChildItem Cert:\LocalMachine\TrustedPeople | Where-Object { $_.Subject -ceq 'CN=TheCreator0169' } | Remove-Item
```

## Build and supply chain

- Python dependencies are pinned with hashes (`requirements.txt`). CI runs the tests on every push.
- Releases are built on the author's PC; the setup SHA-256 is in `BUILD_HISTORY.md` and on the release page.
- Not tested: real GPU encoders (QSV, AMF), the Explorer menu on other machines.
