; GenMeta Installer — v20.1
; Inno Setup 6 — https://jrsoftware.org/isinfo.php
;
; TWO INSTALL MODES:
;   Recommended — installs to C:\Program\GenMeta, creates Desktop + Start Menu shortcuts
;   Custom       — user selects install dir, shortcut preferences, and output folder location

#define MyAppName      "GenMeta"
#define MyAppVersion   "20.1"
#define MyAppPublisher "Palan Dev"
#define MyAppExeName   "GenMeta.exe"
#define MySourceDir    SourcePath + "dist\GenMeta"

[Setup]
AppId={{B7E3F1A2-CC94-4D8E-9F1B-2A3D4E5F6071}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL=https://github.com/meetpalan-dev/genmeta
AppSupportURL=https://github.com/meetpalan-dev/genmeta/issues
AppUpdatesURL=https://github.com/meetpalan-dev/genmeta/releases

; Default install path — Recommended mode uses this; Custom mode lets user change it
DefaultDirName=C:\Program\GenMeta
DefaultGroupName={#MyAppName}

; Allow user to choose install type
SetupType=custom
; Two setup types
SetupTypes=\
  Name: "recommended"; Description: "Recommended — Install to C:\Program\GenMeta";\
  Name: "custom"; Description: "Custom — Choose install location and preferences";

AllowNoIcons=no
OutputDir=installer_output
OutputBaseFilename=GenMeta_Setup_v{#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
WizardSizePercent=120
MinVersion=10.0
; Per-user install — no admin rights needed
PrivilegesRequired=lowest
; Show "Select install type" page
ShowInstallTypeDialog=yes
; Show directory page only in Custom mode
DisableDirPage=auto
; Show components page only in Custom mode
DisableProgramGroupPage=auto

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Types]
Name: "recommended"; Description: "Recommended Installation"
Name: "custom";      Description: "Custom Installation"; Flags: iscustom

[Components]
Name: "main";    Description: "GenMeta Application (required)"; Types: recommended custom; Flags: fixed
Name: "desktop"; Description: "Create Desktop shortcut";        Types: recommended custom
Name: "startmenu"; Description: "Create Start Menu shortcut";   Types: recommended custom

[Tasks]
Name: "desktopicon";   Description: "Create a Desktop shortcut";   Components: desktop
Name: "startmenuicon"; Description: "Create a Start Menu shortcut"; Components: startmenu

[Files]
Source: "{#MySourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Components: main

[Icons]
Name: "{group}\{#MyAppName}";       Filename: "{app}\{#MyAppExeName}"; Tasks: startmenuicon
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}";     Tasks: startmenuicon
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; \
  Description: "{cm:LaunchProgram,{#StringChange(MyAppName,'&','&&')}}"; \
  Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: files; Name: "{app}\config.json"
Type: files; Name: "{app}\run_history.json"
Type: files; Name: "{app}\undo_log.json"

[Code]
var
  OutputFolderPage: TInputDirWizardPage;
  InstallTypePage:  TWizardPage;

// Detect WebView2 runtime
function IsWebView2Installed(): Boolean;
var
  Version: String;
begin
  Result := RegQueryStringValue(
    HKEY_LOCAL_MACHINE,
    'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
    'pv', Version) and (Version <> '');
  if not Result then
    Result := RegQueryStringValue(
      HKEY_CURRENT_USER,
      'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
      'pv', Version) and (Version <> '');
end;

procedure InitializeWizard();
begin
  // Extra page for Custom mode: let user choose the Universal output folder
  OutputFolderPage := CreateInputDirPage(
    wpSelectComponents,
    'Universal Output Folder',
    'Where should GenMeta store processed images and CSVs?',
    'GenMeta will create  valid,  duplicate,  and  CSV  subfolders here.' + #13#10 +
    'You can change this later in Settings.',
    False, '');
  OutputFolderPage.Add('Output folder:');
  OutputFolderPage.Values[0] := ExpandConstant('{app}');
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
  // Skip the custom output folder page in Recommended mode
  if PageID = OutputFolderPage.ID then
    Result := (WizardSetupType(False) = 'recommended');
end;

function GetOutputFolder(Param: String): String;
begin
  if WizardSetupType(False) = 'recommended' then
    Result := ExpandConstant('{app}')   // same as install dir for Recommended
  else
    Result := OutputFolderPage.Values[0];
end;

procedure WriteConfig(OutputFolder: String);
// Write a default config.json so the app starts with the right output path
var
  ConfigPath: String;
  ConfigLines: TArrayOfString;
begin
  ConfigPath := ExpandConstant('{app}\config.json');
  // Only write if config doesn't already exist (preserve user settings on upgrade)
  if not FileExists(ConfigPath) then begin
    SetArrayLength(ConfigLines, 7);
    ConfigLines[0] := '{';
    ConfigLines[1] := '  "global_storage_path": "' + StringReplace(OutputFolder, '\', '\\', [rfReplaceAll]) + '",';
    ConfigLines[2] := '  "use_local_output": false,';
    ConfigLines[3] := '  "univ_dup_enabled": false,';
    ConfigLines[4] := '  "univ_csv_enabled": false,';
    ConfigLines[5] := '  "dedup_all_files": true,';
    ConfigLines[6] := '  "export_shutter": true';
    ConfigLines[7] := '}';
    SaveStringsToFile(ConfigPath, ConfigLines, False);
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  OutputFolder: String;
begin
  if CurStep = ssPostInstall then begin
    OutputFolder := GetOutputFolder('');
    // Create the output folder if it doesn't exist
    if not DirExists(OutputFolder) then
      CreateDir(OutputFolder);
    // Write default config.json
    WriteConfig(OutputFolder);
    // WebView2 warning
    if not IsWebView2Installed() then
      MsgBox(
        'GenMeta needs the Microsoft WebView2 Runtime to run.' + #13#10#13#10 +
        'Please download it from:' + #13#10 +
        'https://developer.microsoft.com/microsoft-edge/webview2/' + #13#10#13#10 +
        'GenMeta will not open until WebView2 is installed.',
        mbInformation, MB_OK);
  end;
end;
