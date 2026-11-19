; Built by build.ps1: iscc /DAppVersion=0.1.0 installer\convert.iss  (needs Inno Setup 6)
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{7D3B1C52-9A4E-4F0B-8E21-5C6A0D94B7F3}
AppName=Convert
AppVersion={#AppVersion}
AppPublisher=TheCreator0169
AppCopyright=Copyright (c) 2026 TheCreator0169. MIT License.
VersionInfoVersion={#AppVersion}
VersionInfoCopyright=Copyright (c) 2026 TheCreator0169. MIT License.
VersionInfoProductName=Convert
VersionInfoDescription=Convert for Windows setup
DefaultDirName={localappdata}\Programs\Convert
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=Convert-Setup-v{#AppVersion}
SetupIconFile=..\assets\convert.ico
UninstallDisplayIcon={app}\Convert.exe
Compression=lzma2
SolidCompression=yes
CloseApplications=yes
LicenseFile=..\LICENSE

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[CustomMessages]
english.DeleteSettings=Also delete your Convert settings?
french.DeleteSettings=Supprimer aussi les parametres de Convert ?

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; An upgrade starts from a clean program folder, so files dropped from the app do not linger. Settings and logs live elsewhere.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\Convert\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{userprograms}\Convert"; Filename: "{app}\Convert.exe"
Name: "{userdesktop}\Convert"; Filename: "{app}\Convert.exe"; Tasks: desktopicon

[Run]
; Adds "Convert" to the Explorer right-click menu (HKCU only)
Filename: "{app}\Convert.exe"; Parameters: "--install-menu"; Flags: runhidden
Filename: "{app}\Convert.exe"; Description: "Open Convert"; Flags: postinstall nowait skipifsilent

[UninstallRun]
Filename: "{app}\Convert.exe"; Parameters: "--uninstall-menu"; Flags: runhidden; RunOnceId: "RemoveMenu"

[UninstallDelete]
; Logs are not user data: remove them. Settings (%APPDATA%\Convert) are handled by the question below.
Type: filesandordirs; Name: "{localappdata}\Convert"

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usPostUninstall) and DirExists(ExpandConstant('{userappdata}\Convert')) then
    if MsgBox(CustomMessage('DeleteSettings'),mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      DelTree(ExpandConstant('{userappdata}\Convert'), True, True, True);
end;
