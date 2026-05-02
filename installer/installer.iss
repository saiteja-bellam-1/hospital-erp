; KT HEALTH ERP — Inno Setup script
; Wraps the PyInstaller .exe in a proper Windows installer with Start Menu /
; Desktop entries and an uninstaller registered in Apps & Features.
;
; To compile this script, install Inno Setup 6+ (https://jrsoftware.org/isinfo.php)
; and run build_installer.bat from the repo root after build_exe.bat completes.

#define AppName        "KT HEALTH ERP"
#define AppPublisher   "KT Health Soft"
#define AppExeName     "KTHEALTHERP.exe"
#define AppId          "{{8BC2E1C5-7DBA-4F4D-9B1E-6A3F2A4D0001}"
#ifndef AppVersion
  #define AppVersion   "1.1.0"
#endif

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL=https://kthealthsoft.com
DefaultDirName={autopf}\KTHEALTHERP
DefaultGroupName={#AppName}
DisableDirPage=no
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}
OutputDir=..\backend\dist\installer
OutputBaseFilename=KTHEALTHERP_Setup_{#AppVersion}
SetupIconFile=..\backend\assets\icon.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64
MinVersion=10.0.17763

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: checkedonce
Name: "startmenuicon"; Description: "Create a Start Menu shortcut"; GroupDescription: "Additional shortcuts:"; Flags: checkedonce
Name: "firewall"; Description: "Allow LAN access through Windows Firewall (recommended)"; GroupDescription: "Network:"; Flags: checkedonce

[Files]
Source: "..\backend\dist\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\backend\assets\icon.ico";    DestDir: "{app}\assets"; Flags: ignoreversion
; data\ is intentionally NOT shipped — it is created on first launch by launcher.py
; so backups and DBs survive reinstall/upgrade.

[Icons]
Name: "{group}\{#AppName}";   Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\assets\icon.ico"; Tasks: startmenuicon
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{commondesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\assets\icon.ico"; Tasks: desktopicon

[Run]
; Open firewall port range used by launcher.find_free_port (8000-8020) for LAN access
Filename: "netsh"; Parameters: "advfirewall firewall add rule name=""KT HEALTH ERP"" dir=in action=allow protocol=TCP localport=8000-8020"; Flags: runhidden; Tasks: firewall
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName} now"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "netsh"; Parameters: "advfirewall firewall delete rule name=""KT HEALTH ERP"""; Flags: runhidden

[UninstallDelete]
; Leave data\ behind by default — it contains the customer DB, uploads,
; and config.json. The uninstaller asks the operator before wiping.
Type: files; Name: "{app}\assets\icon.ico"

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
  Confirmed: Integer;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{app}\data');
    if DirExists(DataDir) then
    begin
      Confirmed := MsgBox(
        'The hospital database, uploads, configuration, and backups in:' + #13#10 + DataDir + #13#10 + #13#10 +
        'have been LEFT IN PLACE so you can re-install without losing data.' + #13#10 + #13#10 +
        'Click Yes to permanently DELETE this data, or No to keep it.',
        mbConfirmation, MB_YESNO or MB_DEFBUTTON2);
      if Confirmed = IDYES then
      begin
        DelTree(DataDir, True, True, True);
      end;
    end;
  end;
end;
