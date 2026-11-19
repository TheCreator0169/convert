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
DisableWelcomePage=yes
DisableDirPage=yes
DisableReadyPage=yes
WizardSizePercent=100

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[CustomMessages]
english.DeleteSettings=Also delete your Convert settings?
french.DeleteSettings=Supprimer aussi les parametres de Convert ?
english.FfmpegFound=ffmpeg was found: audio and video conversion is available.
french.FfmpegFound=ffmpeg a ete trouve : la conversion audio et video est disponible.
english.FfmpegMissing=ffmpeg was not found. Images and documents work now; audio and video need ffmpeg. To install it, open a terminal and run: winget install Gyan.FFmpeg  (then restart Convert).
french.FfmpegMissing=ffmpeg est introuvable. Les images et les documents fonctionnent; l'audio et la video demandent ffmpeg. Pour l'installer, ouvrez un terminal et lancez : winget install Gyan.FFmpeg  (puis relancez Convert).
english.OpenConvert=Open Convert
french.OpenConvert=Ouvrir Convert
english.AppRunning=Convert is already running. Close it, then click OK to continue, or Cancel to quit.
french.AppRunning=Convert est deja ouvert. Fermez-le, puis cliquez sur OK pour continuer, ou sur Annuler pour quitter.

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
Filename: "{app}\Convert.exe"; Description: "{cm:OpenConvert}"; Flags: postinstall nowait skipifsilent

[UninstallRun]
Filename: "{app}\Convert.exe"; Parameters: "--uninstall-menu"; Flags: runhidden; RunOnceId: "RemoveMenu"

[UninstallDelete]
; Logs are not user data: remove them. Settings (%APPDATA%\Convert) are handled by the question below.
Type: filesandordirs; Name: "{localappdata}\Convert"

[Code]
{ The app holds the mutex "Local\Convert-GUI-<login>" (convert_win\ui.py claim_first). Setup and the app share the session namespace,
  so the unprefixed name and the Local\ name are the same object; both are checked. }
function AppMutexNames(): String;
var
  User: String;
begin
  { Python's getpass.getuser() takes the first non-empty of LOGNAME, USER, LNAME, USERNAME; do the same, then the account name. }
  User := GetEnv('LOGNAME');
  if User = '' then User := GetEnv('USER');
  if User = '' then User := GetEnv('LNAME');
  if User = '' then User := GetEnv('USERNAME');
  if User = '' then User := GetUserNameString;
  Result := 'Convert-GUI-' + User + ',Local\Convert-GUI-' + User;
end;

{ True when Convert is running and the user clicked Cancel. Silent runs never block: CloseApplications handles the app. }
function AppBlocks(Silent: Boolean): Boolean;
var
  Msg: String;
begin
  Result := False;
  if Silent then Exit;
  Msg := CustomMessage('AppRunning');
  while CheckForMutexes(AppMutexNames()) do
  begin
    if MsgBox(Msg, mbError, MB_OKCANCEL) = IDCANCEL then
    begin
      Result := True;
      Exit;
    end;
  end;
end;

function InitializeSetup(): Boolean;
begin
  Result := not AppBlocks(WizardSilent);
end;

function InitializeUninstall(): Boolean;
begin
  Result := not AppBlocks(UninstallSilent);
end;

{ Last page: say whether ffmpeg is there. It is not bundled; nothing is downloaded or installed here. }
procedure CurPageChanged(CurPageID: Integer);
var
  Note: String;
begin
  if CurPageID = wpFinished then
  begin
    if FileSearch('ffmpeg.exe', GetEnv('PATH')) <> '' then
      Note := CustomMessage('FfmpegFound')
    else
      Note := CustomMessage('FfmpegMissing');
    WizardForm.FinishedLabel.Caption := WizardForm.FinishedLabel.Caption + #13#10#13#10 + Note;
  end;
end;

{ Safety net: --uninstall-menu normally removes the Explorer verbs; if it failed, remove them here (HKCU only, only our own key). }
procedure RemoveMenuVerbs;
var
  Exts: String;
  P: Integer;
begin
  Exts := 'mp3,m4a,aac,wav,aiff,aif,flac,opus,ogg,oga,wma,ac3,wv,mp2,mp4,mov,webm,mkv,avi,m4v,wmv,flv,mpg,mpeg,3gp,jpg,jpeg,png,heic,heif,avif,webp,tif,tiff,gif,bmp,txt,md,markdown,html,htm,rtf,docx,odt,pdf,';
  while Exts <> '' do
  begin
    P := Pos(',', Exts);
    RegDeleteKeyIncludingSubkeys(HKCU, 'Software\Classes\SystemFileAssociations\.' + Copy(Exts, 1, P - 1) + '\shell\Convert');
    Delete(Exts, 1, P);
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then RemoveMenuVerbs;
  if (CurUninstallStep = usPostUninstall) and DirExists(ExpandConstant('{userappdata}\Convert')) then
    if SuppressibleMsgBox(CustomMessage('DeleteSettings'), mbConfirmation, MB_YESNO or MB_DEFBUTTON2, IDNO) = IDYES then  { silent: keep the settings }
      DelTree(ExpandConstant('{userappdata}\Convert'), True, True, True);
end;
