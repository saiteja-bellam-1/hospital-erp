; KT HEALTH ERP — Inno Setup script
;
; Unified installation wizard. Beyond the usual file-copy + shortcuts an Inno
; Setup script does, this one collects everything the React Setup Wizard used
; to ask for (hospital info, admin credentials, optional license, optional
; existing data folder, backup destinations) and writes the answers to
;
;   <data-dir>\install_seed.json
;   <data-dir>\.install_seed.pwd     (plaintext, short-lived — deleted after first-launch consume)
;
; On first launch, backend\launcher.py -> app.services.bootstrap_from_seed
; consumes both files and seeds the DB exactly the way the React wizard does.
; If the operator chooses "Use existing data folder", we skip the hospital /
; admin / license pages and let the bootstrap rebind config.json instead.
;
; Build with build_installer.bat after build_exe.bat + build_dbcheck.bat.

#define AppName        "KT HEALTH ERP"
#define AppPublisher   "KT Health Soft"
#define AppExeName     "KTHEALTHERP.exe"
#define DbCheckExe     "dbcheck.exe"
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
; Self-update support: when a newer installer runs over an existing install,
; let Setup close the running KTHEALTHERP.exe (via Restart Manager) so the
; binary can be replaced. RestartApplications=no — we relaunch in [Run] instead.
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: checkedonce
Name: "startmenuicon"; Description: "Create a Start Menu shortcut"; GroupDescription: "Additional shortcuts:"; Flags: checkedonce
Name: "firewall"; Description: "Allow LAN access through Windows Firewall (recommended)"; GroupDescription: "Network:"; Flags: checkedonce

[Files]
Source: "..\backend\dist\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\backend\assets\icon.ico";    DestDir: "{app}\assets"; Flags: ignoreversion
; dbcheck.exe is used by the wizard pages at install time. We extract it to
; {tmp} on demand via ExtractTemporaryFile (dontcopy), AND drop an installed
; copy into {app} so an admin can re-run checks later from the install dir.
Source: "bin\{#DbCheckExe}"; Flags: dontcopy
Source: "bin\{#DbCheckExe}"; DestDir: "{app}"; Flags: ignoreversion
; data\ is intentionally NOT shipped — it is created by the wizard / launcher
; so backups and DBs survive reinstall/upgrade.

[Icons]
Name: "{group}\{#AppName}";   Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\assets\icon.ico"; Tasks: startmenuicon
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{commondesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\assets\icon.ico"; Tasks: desktopicon

[Run]
; Open firewall port range used by launcher.find_free_port (8000-8020) for LAN
; access. Fresh install only — the rule persists across upgrades.
Filename: "netsh"; Parameters: "advfirewall firewall add rule name=""KT HEALTH ERP"" dir=in action=allow protocol=TCP localport=8000-8020"; Flags: runhidden; Tasks: firewall; Check: GetIsFreshInstall
; Fresh install: offer "Launch now" on the Finished page (interactive only).
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName} now"; Flags: nowait postinstall skipifsilent; Check: GetIsFreshInstall
; Upgrade / self-update: always relaunch, including under /VERYSILENT.
Filename: "{app}\{#AppExeName}"; Flags: nowait postinstall; Check: GetIsUpgrade

[UninstallRun]
Filename: "netsh"; Parameters: "advfirewall firewall delete rule name=""KT HEALTH ERP"""; Flags: runhidden

[UninstallDelete]
; Leave data\ behind by default — it contains the customer DB, uploads,
; and config.json. The uninstaller asks the operator before wiping.
Type: files; Name: "{app}\assets\icon.ico"

[Code]
// ============================================================================
//   KT HEALTH ERP — wizard pages
// ============================================================================
// Order:
//   wpWelcome -> wpSelectDir -> [DataFolderPage] -> [DbCheckPage]
//   -> [LicensePage] -> [HospitalPage] -> [AdminPage] -> [BackupPage]
//   -> wpSelectTasks -> wpReady -> wpInstalling -> wpFinished
//
// Pages prefixed with [Hospital/Admin/License] are skipped when the operator
// picks "Use existing data folder" on DataFolderPage — that branch only needs
// the data folder + (optional) backup destinations.
// ============================================================================

const
  MODE_FRESH    = 0;
  MODE_EXISTING = 1;
  MODE_RESTORE  = 2;
  MIN_PWD_LEN   = 8;
  // Inno's uninstall registry key for this AppId (raw GUID + _is1 suffix).
  UNINST_KEY    = 'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{8BC2E1C5-7DBA-4F4D-9B1E-6A3F2A4D0001}_is1';

var
  // Self-update: InitializeSetup sets these when an existing install is found.
  // On upgrade the wizard skips every custom page and writes no seed file.
  IsUpgrade:         Boolean;
  ExistingAppDir:    String;
  // DataFolderPage
  DataFolderPage:    TWizardPage;
  RbFresh:           TNewRadioButton;
  RbExisting:        TNewRadioButton;
  RbRestore:         TNewRadioButton;
  EdNewDataDir:      TNewEdit;
  BtnBrowseNewData:  TNewButton;
  EdExistingDataDir: TNewEdit;
  BtnBrowseExisting: TNewButton;
  EdRestoreDataDir:  TNewEdit;
  BtnBrowseRestoreDir: TNewButton;
  EdRestoreFile:     TNewEdit;
  BtnBrowseRestoreFile: TNewButton;
  LblDataIntro:      TNewStaticText;

  // DbCheckPage (only shown for MODE_EXISTING)
  DbCheckPage:       TWizardPage;
  DbCheckMemo:       TNewMemo;
  DbCheckOk:         Boolean;

  // LicensePage
  LicensePage:       TWizardPage;
  LblMachineId:      TNewStaticText;
  EdMachineId:       TNewEdit;
  EdLicensePath:     TNewEdit;
  BtnBrowseLicense:  TNewButton;
  BtnVerifyLicense:  TNewButton;
  LblLicenseStatus:  TNewStaticText;
  LicenseValid:      Boolean;

  // HospitalPage
  HospitalPage:      TWizardPage;
  EdHospName:        TNewEdit;
  EdHospAddr:        TNewEdit;
  EdHospPhone:       TNewEdit;
  EdHospEmail:       TNewEdit;

  // AdminPage
  AdminPage:         TWizardPage;
  EdAdminUser:       TNewEdit;
  EdAdminEmail:      TNewEdit;
  EdAdminPwd:        TNewEdit;
  EdAdminPwdConfirm: TNewEdit;
  LblAdminError:     TNewStaticText;

  // BackupPage
  BackupPage:        TWizardPage;
  EdBackup1:         TNewEdit;
  EdBackup2:         TNewEdit;
  EdBackup3:         TNewEdit;
  BtnBackup1:        TNewButton;
  BtnBackup2:        TNewButton;
  BtnBackup3:        TNewButton;

// ----------------------------------------------------------------------------
//   helpers
// ----------------------------------------------------------------------------

function GetMode: Integer;
begin
  if RbExisting.Checked then
    Result := MODE_EXISTING
  else if RbRestore.Checked then
    Result := MODE_RESTORE
  else
    Result := MODE_FRESH;
end;

function DbCheckExePath: String;
begin
  // While the wizard is running, ExtractTemporaryFile makes the file available
  // at {tmp}\dbcheck.exe. We extract on first use.
  Result := ExpandConstant('{tmp}\') + '{#DbCheckExe}';
end;

procedure EnsureDbCheckExtracted;
begin
  if not FileExists(DbCheckExePath) then
    ExtractTemporaryFile('{#DbCheckExe}');
end;

function StripTrailingSlash(const S: String): String;
var
  L: Integer;
begin
  Result := Trim(S);
  L := Length(Result);
  while (L > 0) and ((Result[L] = '\') or (Result[L] = '/')) do
  begin
    // Don't eat the lone backslash of a drive root ("C:\") — without it
    // the path is meaningless. Same for UNC roots ("\\server\share").
    if (L = 3) and (Result[2] = ':') then
      Break;
    SetLength(Result, L - 1);
    L := L - 1;
  end;
end;

function QuoteArg(const S: String): String;
begin
  // Wrap in double quotes. We're calling Exec() directly (no cmd shell),
  // so this single layer of quoting is all that's needed and there's no
  // backslash-escapes-quote hazard provided callers strip trailing
  // separators first via StripTrailingSlash.
  Result := '"' + S + '"';
end;

function RunDbCheck(const Args: String; out Output: String): Boolean;
var
  TmpFile, Params: String;
  ResultCode: Integer;
  Lines: TStringList;
begin
  Result := False;
  Output := '';
  EnsureDbCheckExtracted;
  TmpFile := ExpandConstant('{tmp}\dbcheck_out.txt');

  // Wipe any prior output so we don't read stale JSON from a previous run.
  if FileExists(TmpFile) then
    DeleteFile(TmpFile);

  // Call dbcheck.exe directly (no `cmd /C` wrapper). dbcheck writes its
  // JSON to TmpFile via --out, which dodges Windows command-line quoting
  // bugs entirely (a path ending in `\` would otherwise escape the
  // closing quote and corrupt the redirection).
  Params := '--out ' + QuoteArg(TmpFile) + ' ' + Args;
  if not Exec(DbCheckExePath, Params, '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
    Exit;

  Lines := TStringList.Create;
  try
    if FileExists(TmpFile) then
    begin
      Lines.LoadFromFile(TmpFile);
      Output := Lines.Text;
    end;
  finally
    Lines.Free;
  end;

  // Treat a successful Exec + populated output as a successful invocation.
  // The caller still inspects "ok": true/false in the JSON to decide
  // whether the underlying check passed.
  Result := (Output <> '') or (ResultCode = 0);
end;

function JsonHasOkTrue(const S: String): Boolean;
begin
  // Tiny JSON probe — dbcheck.exe always emits {"ok": true|false, ...} as the
  // first thing on stdout. We avoid pulling in a real JSON lib in Pascal.
  Result := (Pos('"ok": true', S) > 0) or (Pos('"ok":true', S) > 0);
end;

function ExtractJsonError(const S: String): String;
var
  P, Q: Integer;
  Tag: String;
begin
  Result := '';
  Tag := '"error":';
  P := Pos(Tag, S);
  if P = 0 then Exit;
  P := P + Length(Tag);
  while (P <= Length(S)) and (S[P] = ' ') do Inc(P);
  if (P > Length(S)) or (S[P] <> '"') then Exit;
  Inc(P);
  Q := P;
  while (Q <= Length(S)) and (S[Q] <> '"') do Inc(Q);
  if Q > P then Result := Copy(S, P, Q - P);
end;

function DescribeFailure(const S: String): String;
var
  Err: String;
begin
  // Caller-friendly failure summary. Prefer the JSON `error` field; fall
  // back to a tail of the raw output so a malformed-output bug never
  // shows up as a blank message box.
  Err := ExtractJsonError(S);
  if Err <> '' then
  begin
    Result := Err;
    Exit;
  end;
  if Trim(S) = '' then
  begin
    Result := '(dbcheck.exe produced no output. Log: ' +
              ExpandConstant('{tmp}\dbcheck_out.txt') + ')';
    Exit;
  end;
  // Truncate to keep the MsgBox readable.
  if Length(S) > 400 then
    Result := Copy(S, 1, 400) + '...'
  else
    Result := S;
end;

function PickFolder(Default: String): String;
var
  Selected: String;
begin
  Selected := Default;
  if BrowseForFolder('Select a folder', Selected, True) then
    Result := Selected
  else
    Result := Default;
end;

function ParentDir(const Path: String): String;
var
  i: Integer;
begin
  Result := '';
  for i := Length(Path) downto 1 do
    if (Path[i] = '\') or (Path[i] = '/') then
    begin
      Result := Copy(Path, 1, i - 1);
      Exit;
    end;
end;

function PickFile(const Filter, Default, InitialDir: String): String;
var
  Selected, StartDir: String;
begin
  Selected := Default;
  // Choose a sensible starting folder so the dialog doesn't open in
  // Inno Setup's temp dir (where no .db / .lic files exist) — which is
  // what causes the "Browse only shows folders, no files" symptom.
  // Preference order:
  //   1. The directory of the previously-picked file (if any),
  //   2. The InitialDir hint passed by the caller,
  //   3. The user's Documents folder as a last resort.
  if (Default <> '') and DirExists(ParentDir(Default)) then
    StartDir := ParentDir(Default)
  else if (InitialDir <> '') and DirExists(InitialDir) then
    StartDir := InitialDir
  else
    StartDir := ExpandConstant('{userdocs}');

  if GetOpenFileName('Select a file', Selected, StartDir, Filter, '') then
    Result := Selected
  else
    Result := Default;
end;

function StrIsEmpty(const S: String): Boolean;
begin
  Result := Trim(S) = '';
end;

function HasWhitespace(const S: String): Boolean;
var
  i: Integer;
begin
  Result := False;
  for i := 1 to Length(S) do
    if (S[i] = ' ') or (S[i] = #9) then
    begin
      Result := True;
      Exit;
    end;
end;

// ----------------------------------------------------------------------------
//   page constructors
// ----------------------------------------------------------------------------

procedure OnBrowseNewData(Sender: TObject);
begin
  EdNewDataDir.Text := PickFolder(EdNewDataDir.Text);
end;

procedure OnBrowseExisting(Sender: TObject);
begin
  EdExistingDataDir.Text := PickFolder(EdExistingDataDir.Text);
end;

procedure OnBrowseRestoreDir(Sender: TObject);
begin
  EdRestoreDataDir.Text := PickFolder(EdRestoreDataDir.Text);
end;

procedure OnBrowseRestoreFile(Sender: TObject);
begin
  // Filter: accept the common KT HEALTH ERP backup extensions, plus generic
  // SQLite variants. Semicolons let one filter entry list multiple patterns.
  // Falls back to "All files" so the operator can still pick an oddly-named
  // backup if needed.
  EdRestoreFile.Text := PickFile(
    'KT HEALTH ERP backups (*.db;*.db.bak;*.sqlite;*.sqlite3)|*.db;*.db.bak;*.sqlite;*.sqlite3|All files (*.*)|*.*',
    EdRestoreFile.Text,
    EdRestoreDataDir.Text);
end;

procedure OnRadioChange(Sender: TObject);
begin
  EdNewDataDir.Enabled         := RbFresh.Checked;
  BtnBrowseNewData.Enabled     := RbFresh.Checked;
  EdExistingDataDir.Enabled    := RbExisting.Checked;
  BtnBrowseExisting.Enabled    := RbExisting.Checked;
  EdRestoreDataDir.Enabled     := RbRestore.Checked;
  BtnBrowseRestoreDir.Enabled  := RbRestore.Checked;
  EdRestoreFile.Enabled        := RbRestore.Checked;
  BtnBrowseRestoreFile.Enabled := RbRestore.Checked;
end;

procedure CreateDataFolderPage;
begin
  DataFolderPage := CreateCustomPage(wpSelectDir,
    'Data folder',
    'Choose where the database, uploads, and configuration live.');

  LblDataIntro := TNewStaticText.Create(DataFolderPage.Surface);
  LblDataIntro.Parent := DataFolderPage.Surface;
  LblDataIntro.Top := 0;
  LblDataIntro.Width := DataFolderPage.SurfaceWidth;
  LblDataIntro.AutoSize := False;
  LblDataIntro.Height := 30;
  LblDataIntro.WordWrap := True;
  LblDataIntro.Caption :=
    'Pick "Create a new data folder" for a fresh install, "Use existing data folder" to ' +
    'reinstall on top of an existing database, or "Restore from a backup database file" ' +
    'to bring up a hospital from a single .db backup file.';

  RbFresh := TNewRadioButton.Create(DataFolderPage.Surface);
  RbFresh.Parent := DataFolderPage.Surface;
  RbFresh.Top := 40;
  RbFresh.Width := DataFolderPage.SurfaceWidth;
  RbFresh.Caption := 'Create a new data folder (fresh install)';
  RbFresh.Checked := True;
  RbFresh.OnClick := @OnRadioChange;

  EdNewDataDir := TNewEdit.Create(DataFolderPage.Surface);
  EdNewDataDir.Parent := DataFolderPage.Surface;
  EdNewDataDir.Top := 65;
  EdNewDataDir.Left := 24;
  EdNewDataDir.Width := DataFolderPage.SurfaceWidth - 110;
  // Default to ProgramData, NOT Program Files. Storing a SQLite DB under
  // Program Files is fragile (UAC virtualisation, AV interference, blown
  // away on uninstall) and previously caused "Cannot write to this folder"
  // when the wizard wasn't elevated.
  EdNewDataDir.Text := ExpandConstant('{commonappdata}\KTHEALTHERP\data');

  BtnBrowseNewData := TNewButton.Create(DataFolderPage.Surface);
  BtnBrowseNewData.Parent := DataFolderPage.Surface;
  BtnBrowseNewData.Top := 63;
  BtnBrowseNewData.Left := DataFolderPage.SurfaceWidth - 80;
  BtnBrowseNewData.Width := 80;
  BtnBrowseNewData.Height := 23;
  BtnBrowseNewData.Caption := 'Browse...';
  BtnBrowseNewData.OnClick := @OnBrowseNewData;

  RbExisting := TNewRadioButton.Create(DataFolderPage.Surface);
  RbExisting.Parent := DataFolderPage.Surface;
  RbExisting.Top := 110;
  RbExisting.Width := DataFolderPage.SurfaceWidth;
  RbExisting.Caption := 'Use existing data folder (keep my existing database)';
  RbExisting.OnClick := @OnRadioChange;

  EdExistingDataDir := TNewEdit.Create(DataFolderPage.Surface);
  EdExistingDataDir.Parent := DataFolderPage.Surface;
  EdExistingDataDir.Top := 135;
  EdExistingDataDir.Left := 24;
  EdExistingDataDir.Width := DataFolderPage.SurfaceWidth - 110;
  // Pre-fill with the same default the fresh-install path uses, so that
  // re-running the installer over a previous install just needs Next.
  EdExistingDataDir.Text := ExpandConstant('{commonappdata}\KTHEALTHERP\data');
  EdExistingDataDir.Enabled := False;

  BtnBrowseExisting := TNewButton.Create(DataFolderPage.Surface);
  BtnBrowseExisting.Parent := DataFolderPage.Surface;
  BtnBrowseExisting.Top := 133;
  BtnBrowseExisting.Left := DataFolderPage.SurfaceWidth - 80;
  BtnBrowseExisting.Width := 80;
  BtnBrowseExisting.Height := 23;
  BtnBrowseExisting.Caption := 'Browse...';
  BtnBrowseExisting.Enabled := False;
  BtnBrowseExisting.OnClick := @OnBrowseExisting;

  // ----- Option 3: Restore from a single .db backup file -----
  RbRestore := TNewRadioButton.Create(DataFolderPage.Surface);
  RbRestore.Parent := DataFolderPage.Surface;
  RbRestore.Top := 175;
  RbRestore.Width := DataFolderPage.SurfaceWidth;
  RbRestore.Caption := 'Restore from a backup database file (.db)';
  RbRestore.OnClick := @OnRadioChange;

  EdRestoreDataDir := TNewEdit.Create(DataFolderPage.Surface);
  EdRestoreDataDir.Parent := DataFolderPage.Surface;
  EdRestoreDataDir.Top := 200;
  EdRestoreDataDir.Left := 24;
  EdRestoreDataDir.Width := DataFolderPage.SurfaceWidth - 110;
  EdRestoreDataDir.Text := ExpandConstant('{commonappdata}\KTHEALTHERP\data');
  EdRestoreDataDir.Enabled := False;

  BtnBrowseRestoreDir := TNewButton.Create(DataFolderPage.Surface);
  BtnBrowseRestoreDir.Parent := DataFolderPage.Surface;
  BtnBrowseRestoreDir.Top := 198;
  BtnBrowseRestoreDir.Left := DataFolderPage.SurfaceWidth - 80;
  BtnBrowseRestoreDir.Width := 80;
  BtnBrowseRestoreDir.Height := 23;
  BtnBrowseRestoreDir.Caption := 'Browse...';
  BtnBrowseRestoreDir.Enabled := False;
  BtnBrowseRestoreDir.OnClick := @OnBrowseRestoreDir;

  EdRestoreFile := TNewEdit.Create(DataFolderPage.Surface);
  EdRestoreFile.Parent := DataFolderPage.Surface;
  EdRestoreFile.Top := 228;
  EdRestoreFile.Left := 24;
  EdRestoreFile.Width := DataFolderPage.SurfaceWidth - 110;
  EdRestoreFile.Enabled := False;

  BtnBrowseRestoreFile := TNewButton.Create(DataFolderPage.Surface);
  BtnBrowseRestoreFile.Parent := DataFolderPage.Surface;
  BtnBrowseRestoreFile.Top := 226;
  BtnBrowseRestoreFile.Left := DataFolderPage.SurfaceWidth - 80;
  BtnBrowseRestoreFile.Width := 80;
  BtnBrowseRestoreFile.Height := 23;
  BtnBrowseRestoreFile.Caption := 'Browse .db';
  BtnBrowseRestoreFile.Enabled := False;
  BtnBrowseRestoreFile.OnClick := @OnBrowseRestoreFile;
end;

procedure CreateDbCheckPage;
begin
  DbCheckPage := CreateCustomPage(DataFolderPage.ID,
    'Database integrity check',
    'Verifying the existing data folder before we connect to it.');

  DbCheckMemo := TNewMemo.Create(DbCheckPage.Surface);
  DbCheckMemo.Parent := DbCheckPage.Surface;
  DbCheckMemo.Top := 0;
  DbCheckMemo.Width := DbCheckPage.SurfaceWidth;
  DbCheckMemo.Height := DbCheckPage.SurfaceHeight;
  DbCheckMemo.ReadOnly := True;
  DbCheckMemo.ScrollBars := ssVertical;
  DbCheckMemo.Text := '';
end;

procedure OnBrowseLicense(Sender: TObject);
begin
  EdLicensePath.Text := PickFile(
    'License files (*.lic)|*.lic|All files (*.*)|*.*',
    EdLicensePath.Text,
    ExpandConstant('{userdocs}'));
end;

procedure OnVerifyLicense(Sender: TObject);
var
  Output, Err: String;
begin
  LicenseValid := False;
  if StrIsEmpty(EdLicensePath.Text) then
  begin
    LblLicenseStatus.Caption := 'No license selected. You can skip this step and upload one from the app later.';
    Exit;
  end;
  if not FileExists(EdLicensePath.Text) then
  begin
    LblLicenseStatus.Caption := 'File not found: ' + EdLicensePath.Text;
    Exit;
  end;

  LblLicenseStatus.Caption := 'Verifying...';
  RunDbCheck('validate-license ' + QuoteArg(StripTrailingSlash(EdLicensePath.Text)), Output);
  if JsonHasOkTrue(Output) then
  begin
    LicenseValid := True;
    LblLicenseStatus.Caption := 'License OK — signature valid and bound to this machine.';
  end
  else
  begin
    Err := ExtractJsonError(Output);
    if Err = '' then Err := 'Unknown error. See ' + ExpandConstant('{tmp}\dbcheck_out.txt');
    LblLicenseStatus.Caption := 'License rejected: ' + Err;
  end;
end;

procedure CreateLicensePage;
var
  Output: String;
  MachineId: String;
  P, Q: Integer;
begin
  LicensePage := CreateCustomPage(DbCheckPage.ID,
    'License (optional)',
    'You can apply a .lic file now, or skip and upload it from the app later.');

  LblMachineId := TNewStaticText.Create(LicensePage.Surface);
  LblMachineId.Parent := LicensePage.Surface;
  LblMachineId.Top := 0;
  LblMachineId.Caption := 'This machine''s ID (give this to your vendor when buying a license):';

  EdMachineId := TNewEdit.Create(LicensePage.Surface);
  EdMachineId.Parent := LicensePage.Surface;
  EdMachineId.Top := 18;
  EdMachineId.Width := LicensePage.SurfaceWidth;
  EdMachineId.ReadOnly := True;
  EdMachineId.Text := '(detecting...)';

  // Detect machine ID — runs at page-create time so the value is visible up front.
  if RunDbCheck('machine-id', Output) and JsonHasOkTrue(Output) then
  begin
    P := Pos('"machine_id":', Output);
    if P > 0 then
    begin
      P := P + Length('"machine_id":');
      while (P <= Length(Output)) and (Output[P] = ' ') do Inc(P);
      if Output[P] = '"' then
      begin
        Inc(P);
        Q := P;
        while (Q <= Length(Output)) and (Output[Q] <> '"') do Inc(Q);
        MachineId := Copy(Output, P, Q - P);
        EdMachineId.Text := MachineId;
      end;
    end;
  end
  else
    EdMachineId.Text := '(unavailable)';

  EdLicensePath := TNewEdit.Create(LicensePage.Surface);
  EdLicensePath.Parent := LicensePage.Surface;
  EdLicensePath.Top := 60;
  EdLicensePath.Width := LicensePage.SurfaceWidth - 200;

  BtnBrowseLicense := TNewButton.Create(LicensePage.Surface);
  BtnBrowseLicense.Parent := LicensePage.Surface;
  BtnBrowseLicense.Top := 58;
  BtnBrowseLicense.Left := LicensePage.SurfaceWidth - 190;
  BtnBrowseLicense.Width := 90;
  BtnBrowseLicense.Height := 23;
  BtnBrowseLicense.Caption := 'Browse .lic';
  BtnBrowseLicense.OnClick := @OnBrowseLicense;

  BtnVerifyLicense := TNewButton.Create(LicensePage.Surface);
  BtnVerifyLicense.Parent := LicensePage.Surface;
  BtnVerifyLicense.Top := 58;
  BtnVerifyLicense.Left := LicensePage.SurfaceWidth - 95;
  BtnVerifyLicense.Width := 95;
  BtnVerifyLicense.Height := 23;
  BtnVerifyLicense.Caption := 'Verify';
  BtnVerifyLicense.OnClick := @OnVerifyLicense;

  LblLicenseStatus := TNewStaticText.Create(LicensePage.Surface);
  LblLicenseStatus.Parent := LicensePage.Surface;
  LblLicenseStatus.Top := 95;
  LblLicenseStatus.Width := LicensePage.SurfaceWidth;
  LblLicenseStatus.AutoSize := False;
  LblLicenseStatus.Height := 40;
  LblLicenseStatus.WordWrap := True;
  LblLicenseStatus.Caption := 'Leave empty to skip; otherwise click Verify before continuing.';
end;

procedure CreateHospitalPage;
var
  Lbl: TNewStaticText;
begin
  HospitalPage := CreateCustomPage(LicensePage.ID,
    'Hospital details',
    'These appear on prescriptions, bills, and reports.');

  Lbl := TNewStaticText.Create(HospitalPage.Surface);
  Lbl.Parent := HospitalPage.Surface;
  Lbl.Top := 0;  Lbl.Caption := 'Hospital name *';
  EdHospName := TNewEdit.Create(HospitalPage.Surface);
  EdHospName.Parent := HospitalPage.Surface;
  EdHospName.Top := 18; EdHospName.Width := HospitalPage.SurfaceWidth;

  Lbl := TNewStaticText.Create(HospitalPage.Surface);
  Lbl.Parent := HospitalPage.Surface;
  Lbl.Top := 50; Lbl.Caption := 'Address';
  EdHospAddr := TNewEdit.Create(HospitalPage.Surface);
  EdHospAddr.Parent := HospitalPage.Surface;
  EdHospAddr.Top := 68; EdHospAddr.Width := HospitalPage.SurfaceWidth;

  Lbl := TNewStaticText.Create(HospitalPage.Surface);
  Lbl.Parent := HospitalPage.Surface;
  Lbl.Top := 100; Lbl.Caption := 'Phone';
  EdHospPhone := TNewEdit.Create(HospitalPage.Surface);
  EdHospPhone.Parent := HospitalPage.Surface;
  EdHospPhone.Top := 118; EdHospPhone.Width := HospitalPage.SurfaceWidth;

  Lbl := TNewStaticText.Create(HospitalPage.Surface);
  Lbl.Parent := HospitalPage.Surface;
  Lbl.Top := 150; Lbl.Caption := 'Email';
  EdHospEmail := TNewEdit.Create(HospitalPage.Surface);
  EdHospEmail.Parent := HospitalPage.Surface;
  EdHospEmail.Top := 168; EdHospEmail.Width := HospitalPage.SurfaceWidth;
end;

procedure CreateAdminPage;
var
  Lbl: TNewStaticText;
begin
  AdminPage := CreateCustomPage(HospitalPage.ID,
    'Administrator account',
    'This is the first user that can sign in. You can add more from the app afterwards.');

  Lbl := TNewStaticText.Create(AdminPage.Surface);
  Lbl.Parent := AdminPage.Surface;
  Lbl.Top := 0; Lbl.Caption := 'Username * (no spaces)';
  EdAdminUser := TNewEdit.Create(AdminPage.Surface);
  EdAdminUser.Parent := AdminPage.Surface;
  EdAdminUser.Top := 18; EdAdminUser.Width := AdminPage.SurfaceWidth;

  Lbl := TNewStaticText.Create(AdminPage.Surface);
  Lbl.Parent := AdminPage.Surface;
  Lbl.Top := 48; Lbl.Caption := 'Email';
  EdAdminEmail := TNewEdit.Create(AdminPage.Surface);
  EdAdminEmail.Parent := AdminPage.Surface;
  EdAdminEmail.Top := 66; EdAdminEmail.Width := AdminPage.SurfaceWidth;

  Lbl := TNewStaticText.Create(AdminPage.Surface);
  Lbl.Parent := AdminPage.Surface;
  Lbl.Top := 96; Lbl.Caption := 'Password * (min ' + IntToStr(MIN_PWD_LEN) + ' characters)';
  EdAdminPwd := TNewEdit.Create(AdminPage.Surface);
  EdAdminPwd.Parent := AdminPage.Surface;
  EdAdminPwd.Top := 114; EdAdminPwd.Width := AdminPage.SurfaceWidth;
  EdAdminPwd.PasswordChar := '*';

  Lbl := TNewStaticText.Create(AdminPage.Surface);
  Lbl.Parent := AdminPage.Surface;
  Lbl.Top := 144; Lbl.Caption := 'Confirm password *';
  EdAdminPwdConfirm := TNewEdit.Create(AdminPage.Surface);
  EdAdminPwdConfirm.Parent := AdminPage.Surface;
  EdAdminPwdConfirm.Top := 162; EdAdminPwdConfirm.Width := AdminPage.SurfaceWidth;
  EdAdminPwdConfirm.PasswordChar := '*';

  LblAdminError := TNewStaticText.Create(AdminPage.Surface);
  LblAdminError.Parent := AdminPage.Surface;
  LblAdminError.Top := 195; LblAdminError.Width := AdminPage.SurfaceWidth;
  LblAdminError.AutoSize := False; LblAdminError.Height := 30; LblAdminError.WordWrap := True;
  LblAdminError.Caption := '';
end;

procedure OnBrowseBackup1(Sender: TObject); begin EdBackup1.Text := PickFolder(EdBackup1.Text); end;
procedure OnBrowseBackup2(Sender: TObject); begin EdBackup2.Text := PickFolder(EdBackup2.Text); end;
procedure OnBrowseBackup3(Sender: TObject); begin EdBackup3.Text := PickFolder(EdBackup3.Text); end;

procedure CreateBackupPage;
var
  Lbl: TNewStaticText;
begin
  BackupPage := CreateCustomPage(AdminPage.ID,
    'Backup destinations (optional)',
    'Folders the app will mirror the database into every minute. Leave blank to configure later.');

  Lbl := TNewStaticText.Create(BackupPage.Surface);
  Lbl.Parent := BackupPage.Surface;
  Lbl.Top := 0; Lbl.Caption := 'Backup folder 1';
  EdBackup1 := TNewEdit.Create(BackupPage.Surface);
  EdBackup1.Parent := BackupPage.Surface;
  EdBackup1.Top := 18; EdBackup1.Width := BackupPage.SurfaceWidth - 90;
  BtnBackup1 := TNewButton.Create(BackupPage.Surface);
  BtnBackup1.Parent := BackupPage.Surface;
  BtnBackup1.Top := 16; BtnBackup1.Left := BackupPage.SurfaceWidth - 80;
  BtnBackup1.Width := 80; BtnBackup1.Height := 23;
  BtnBackup1.Caption := 'Browse...'; BtnBackup1.OnClick := @OnBrowseBackup1;

  Lbl := TNewStaticText.Create(BackupPage.Surface);
  Lbl.Parent := BackupPage.Surface;
  Lbl.Top := 50; Lbl.Caption := 'Backup folder 2';
  EdBackup2 := TNewEdit.Create(BackupPage.Surface);
  EdBackup2.Parent := BackupPage.Surface;
  EdBackup2.Top := 68; EdBackup2.Width := BackupPage.SurfaceWidth - 90;
  BtnBackup2 := TNewButton.Create(BackupPage.Surface);
  BtnBackup2.Parent := BackupPage.Surface;
  BtnBackup2.Top := 66; BtnBackup2.Left := BackupPage.SurfaceWidth - 80;
  BtnBackup2.Width := 80; BtnBackup2.Height := 23;
  BtnBackup2.Caption := 'Browse...'; BtnBackup2.OnClick := @OnBrowseBackup2;

  Lbl := TNewStaticText.Create(BackupPage.Surface);
  Lbl.Parent := BackupPage.Surface;
  Lbl.Top := 100; Lbl.Caption := 'Backup folder 3';
  EdBackup3 := TNewEdit.Create(BackupPage.Surface);
  EdBackup3.Parent := BackupPage.Surface;
  EdBackup3.Top := 118; EdBackup3.Width := BackupPage.SurfaceWidth - 90;
  BtnBackup3 := TNewButton.Create(BackupPage.Surface);
  BtnBackup3.Parent := BackupPage.Surface;
  BtnBackup3.Top := 116; BtnBackup3.Left := BackupPage.SurfaceWidth - 80;
  BtnBackup3.Width := 80; BtnBackup3.Height := 23;
  BtnBackup3.Caption := 'Browse...'; BtnBackup3.OnClick := @OnBrowseBackup3;
end;

procedure InitializeWizard;
begin
  CreateDataFolderPage;
  CreateDbCheckPage;
  CreateLicensePage;
  CreateHospitalPage;
  CreateAdminPage;
  CreateBackupPage;
  DbCheckOk := False;
  LicenseValid := False;
end;

// ----------------------------------------------------------------------------
//   self-update — detect an existing install and upgrade in place
// ----------------------------------------------------------------------------

function InitializeSetup: Boolean;
var
  Loc: String;
begin
  Result := True;
  IsUpgrade := False;
  ExistingAppDir := '';
  // Inno records the install directory under the AppId uninstall key. A 64-bit
  // install writes it to the 64-bit registry view; probe both to be safe.
  if RegQueryStringValue(HKLM64, UNINST_KEY, 'InstallLocation', Loc) and (Loc <> '') then
  begin
    IsUpgrade := True;
    ExistingAppDir := RemoveBackslash(Loc);
  end
  else if RegQueryStringValue(HKLM32, UNINST_KEY, 'InstallLocation', Loc) and (Loc <> '') then
  begin
    IsUpgrade := True;
    ExistingAppDir := RemoveBackslash(Loc);
  end;
end;

function GetIsUpgrade: Boolean;
begin
  Result := IsUpgrade;
end;

function GetIsFreshInstall: Boolean;
begin
  Result := not IsUpgrade;
end;

function FileIsLocked(const FileName: String): Boolean;
var
  TmpName: String;
begin
  // No direct lock API in Inno Pascal — probe by renaming the file aside and
  // straight back. A file held open by a running process cannot be renamed.
  TmpName := FileName + '.lockprobe';
  if RenameFile(FileName, TmpName) then
  begin
    RenameFile(TmpName, FileName);
    Result := False;
  end
  else
    Result := True;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ExePath: String;
  Waited: Integer;
begin
  Result := '';
  if not IsUpgrade then
    Exit;
  // The self-update flow exits the running backend just before launching this
  // installer. Wait for the .exe lock to clear so the file copy doesn't race
  // the dying process; CloseApplications=yes is the backstop if it doesn't.
  ExePath := AddBackslash(ExistingAppDir) + 'KTHEALTHERP.exe';
  if not FileExists(ExePath) then
    Exit;
  Waited := 0;
  while (Waited < 30000) and FileIsLocked(ExePath) do
  begin
    Sleep(500);
    Waited := Waited + 500;
  end;
end;

// ----------------------------------------------------------------------------
//   navigation gates
// ----------------------------------------------------------------------------

procedure RunDbIntegrityCheck;
var
  Output, Err, Folder: String;
begin
  DbCheckOk := False;
  DbCheckMemo.Lines.Clear;
  Folder := StripTrailingSlash(EdExistingDataDir.Text);
  EdExistingDataDir.Text := Folder;
  DbCheckMemo.Lines.Add('Checking ' + Folder + ' ...');

  if RunDbCheck('check-db ' + QuoteArg(Folder), Output) and JsonHasOkTrue(Output) then
  begin
    DbCheckOk := True;
    DbCheckMemo.Lines.Add('');
    DbCheckMemo.Lines.Add('OK — folder contains a valid KT HEALTH ERP database.');
    DbCheckMemo.Lines.Add('');
    DbCheckMemo.Lines.Add(Output);
  end
  else
  begin
    Err := ExtractJsonError(Output);
    if Err = '' then
    begin
      if Output = '' then
        Err := '(dbcheck.exe produced no output — see ' + ExpandConstant('{tmp}\dbcheck_out.txt') + ')'
      else
        Err := '(see raw output below)';
    end;
    DbCheckMemo.Lines.Add('');
    DbCheckMemo.Lines.Add('Database check FAILED: ' + Err);
    DbCheckMemo.Lines.Add('');
    if Output <> '' then
      DbCheckMemo.Lines.Add(Output)
    else
      DbCheckMemo.Lines.Add('(no output captured)');
  end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  PathOk: Boolean;
  Output: String;
begin
  Result := True;

  if CurPageID = DataFolderPage.ID then
  begin
    if GetMode = MODE_FRESH then
    begin
      if StrIsEmpty(EdNewDataDir.Text) then
      begin
        MsgBox('Please choose a data folder.', mbError, MB_OK);
        Result := False; Exit;
      end;
      // Normalise once, then write back so the rest of the wizard sees
      // the cleaned-up value.
      EdNewDataDir.Text := StripTrailingSlash(EdNewDataDir.Text);
      // probe writability
      PathOk := RunDbCheck('check-writable ' + QuoteArg(EdNewDataDir.Text), Output) and JsonHasOkTrue(Output);
      if not PathOk then
      begin
        MsgBox('Cannot write to that folder:' + Chr(13) + Chr(10) + DescribeFailure(Output), mbError, MB_OK);
        Result := False;
      end;
    end
    else if GetMode = MODE_RESTORE then
    begin
      if StrIsEmpty(EdRestoreDataDir.Text) then
      begin
        MsgBox('Please choose a target data folder.', mbError, MB_OK);
        Result := False; Exit;
      end;
      if StrIsEmpty(EdRestoreFile.Text) then
      begin
        MsgBox('Please select the .db backup file to restore.', mbError, MB_OK);
        Result := False; Exit;
      end;
      EdRestoreDataDir.Text := StripTrailingSlash(EdRestoreDataDir.Text);
      EdRestoreFile.Text    := StripTrailingSlash(EdRestoreFile.Text);
      // target folder must be writable
      PathOk := RunDbCheck('check-writable ' + QuoteArg(EdRestoreDataDir.Text), Output) and JsonHasOkTrue(Output);
      if not PathOk then
      begin
        MsgBox('Cannot write to target folder:' + Chr(13) + Chr(10) + DescribeFailure(Output), mbError, MB_OK);
        Result := False; Exit;
      end;
      // target folder must not already contain a kthealth_erp.db
      if FileExists(AddBackslash(EdRestoreDataDir.Text) + 'kthealth_erp.db') then
      begin
        MsgBox('Target folder already contains a kthealth_erp.db. Pick an empty folder ' +
               'or choose "Use existing data folder" instead.', mbError, MB_OK);
        Result := False; Exit;
      end;
      // backup file must be a valid KT HEALTH ERP database
      PathOk := RunDbCheck('validate-backup-db ' + QuoteArg(EdRestoreFile.Text), Output) and JsonHasOkTrue(Output);
      if not PathOk then
      begin
        MsgBox('Backup file rejected:' + Chr(13) + Chr(10) + DescribeFailure(Output), mbError, MB_OK);
        Result := False;
      end;
    end
    else
    begin
      if StrIsEmpty(EdExistingDataDir.Text) then
      begin
        MsgBox('Please pick the existing data folder.', mbError, MB_OK);
        Result := False; Exit;
      end;
      EdExistingDataDir.Text := StripTrailingSlash(EdExistingDataDir.Text);
    end;
    Exit;
  end;

  if CurPageID = DbCheckPage.ID then
  begin
    if not DbCheckOk then
    begin
      MsgBox('Database check failed. Fix the issue or pick a different folder before continuing.', mbError, MB_OK);
      Result := False;
    end;
    Exit;
  end;

  if CurPageID = LicensePage.ID then
  begin
    // License is optional. If a path was entered, require a successful Verify.
    if (not StrIsEmpty(EdLicensePath.Text)) and (not LicenseValid) then
    begin
      if MsgBox('You picked a license file but did not click Verify (or the verify failed). ' +
                'Click Yes to skip it for now (you can upload from the app later) or No to go back and verify.',
                mbConfirmation, MB_YESNO) = IDNO then
      begin
        Result := False;
        Exit;
      end;
      // If they say yes, drop the license path so it isn't carried forward
      EdLicensePath.Text := '';
    end;
    Exit;
  end;

  if CurPageID = HospitalPage.ID then
  begin
    if StrIsEmpty(EdHospName.Text) then
    begin
      MsgBox('Hospital name is required.', mbError, MB_OK);
      Result := False;
    end;
    Exit;
  end;

  if CurPageID = AdminPage.ID then
  begin
    LblAdminError.Caption := '';
    if StrIsEmpty(EdAdminUser.Text) then
    begin
      LblAdminError.Caption := 'Username is required.';
      Result := False; Exit;
    end;
    if HasWhitespace(EdAdminUser.Text) then
    begin
      LblAdminError.Caption := 'Username cannot contain spaces.';
      Result := False; Exit;
    end;
    if Length(EdAdminPwd.Text) < MIN_PWD_LEN then
    begin
      LblAdminError.Caption := 'Password must be at least ' + IntToStr(MIN_PWD_LEN) + ' characters.';
      Result := False; Exit;
    end;
    if EdAdminPwd.Text <> EdAdminPwdConfirm.Text then
    begin
      LblAdminError.Caption := 'Passwords do not match.';
      Result := False; Exit;
    end;
    Exit;
  end;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  // ShouldSkipPage handles MODE_FRESH/EXISTING fork, but Inno Setup needs
  // the explicit ShouldSkipPage callback below — this proc is only used for
  // page-specific side effects.
  if CurPageID = DbCheckPage.ID then
    RunDbIntegrityCheck;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
var
  Mode: Integer;
begin
  Result := False;
  // Upgrade / self-update: skip every custom page. The existing data folder +
  // config.json already bind everything; no seed is written (CurStepChanged).
  if IsUpgrade then
  begin
    if (PageID = DataFolderPage.ID) or (PageID = DbCheckPage.ID) or
       (PageID = LicensePage.ID) or (PageID = HospitalPage.ID) or
       (PageID = AdminPage.ID) or (PageID = BackupPage.ID) then
      Result := True;
    Exit;
  end;
  Mode := GetMode;
  if (Mode = MODE_EXISTING) or (Mode = MODE_RESTORE) then
  begin
    // Skip license/hospital/admin — they live in the existing/backup DB.
    // Skip the dedicated DbCheckPage too: MODE_EXISTING uses it for an
    // existing folder, MODE_RESTORE validates the .db file inline on
    // the DataFolderPage Next click.
    if (PageID = LicensePage.ID) or
       (PageID = HospitalPage.ID) or
       (PageID = AdminPage.ID) then
      Result := True;
    if (Mode = MODE_RESTORE) and (PageID = DbCheckPage.ID) then
      Result := True;
  end
  else
  begin
    if PageID = DbCheckPage.ID then
      Result := True;
  end;
end;

// ----------------------------------------------------------------------------
//   write the seed file at the end of the install
// ----------------------------------------------------------------------------

function JsonEscape(const S: String): String;
var
  i: Integer;
  C: Char;
begin
  Result := '';
  for i := 1 to Length(S) do
  begin
    C := S[i];
    // Avoid `#N` at line start — Inno Setup's preprocessor treats `#` as a
    // directive marker when it's the first non-whitespace token on a line,
    // so a Pascal character literal like `#8:` triggers a fake directive
    // error. Chr(N) is unambiguous.
    if C = '\' then Result := Result + '\\'
    else if C = '"' then Result := Result + '\"'
    else if C = Chr(8) then Result := Result + '\b'
    else if C = Chr(9) then Result := Result + '\t'
    else if C = Chr(10) then Result := Result + '\n'
    else if C = Chr(13) then Result := Result + '\r'
    else if Ord(C) < 32 then
      Result := Result + '\u00' + Format('%.2x', [Ord(C)])
    else
      Result := Result + C;
  end;
end;

procedure WriteSeedFile;
var
  DataDir, SeedPath, PwdPath, Json: String;
  Mode: Integer;
  Lines: TStringList;
  ResultCode: Integer;
begin
  Mode := GetMode;
  if Mode = MODE_FRESH then
    DataDir := EdNewDataDir.Text
  else if Mode = MODE_RESTORE then
    DataDir := EdRestoreDataDir.Text
  else
    DataDir := EdExistingDataDir.Text;

  // launcher.py looks for the seed under <exe-dir>\data — when the exe is in
  // {app}, that's {app}\data. The data folder the operator chose is captured
  // INSIDE the seed JSON (the launcher then rebinds config.json to it).
  ForceDirectories(ExpandConstant('{app}\data'));
  SeedPath := ExpandConstant('{app}\data\install_seed.json');
  PwdPath  := ExpandConstant('{app}\data\.install_seed.pwd');

  if Mode = MODE_FRESH then
  begin
    Json :=
      '{' + #13#10 +
      '  "mode": "fresh",' + #13#10 +
      '  "data_dir": "' + JsonEscape(DataDir) + '",' + #13#10 +
      '  "hospital_name": "' + JsonEscape(EdHospName.Text) + '",' + #13#10 +
      '  "hospital_address": "' + JsonEscape(EdHospAddr.Text) + '",' + #13#10 +
      '  "hospital_phone": "' + JsonEscape(EdHospPhone.Text) + '",' + #13#10 +
      '  "hospital_email": "' + JsonEscape(EdHospEmail.Text) + '",' + #13#10 +
      '  "admin_username": "' + JsonEscape(EdAdminUser.Text) + '",' + #13#10 +
      '  "admin_email": "' + JsonEscape(EdAdminEmail.Text) + '",' + #13#10 +
      '  "license_path": "' + JsonEscape(EdLicensePath.Text) + '",' + #13#10 +
      '  "backup_locations": [' + #13#10 +
      '    "' + JsonEscape(EdBackup1.Text) + '",' + #13#10 +
      '    "' + JsonEscape(EdBackup2.Text) + '",' + #13#10 +
      '    "' + JsonEscape(EdBackup3.Text) + '"' + #13#10 +
      '  ]' + #13#10 +
      '}';
  end
  else if Mode = MODE_RESTORE then
  begin
    Json :=
      '{' + #13#10 +
      '  "mode": "restore_backup",' + #13#10 +
      '  "data_dir": "' + JsonEscape(DataDir) + '",' + #13#10 +
      '  "backup_file_path": "' + JsonEscape(EdRestoreFile.Text) + '",' + #13#10 +
      '  "backup_locations": [' + #13#10 +
      '    "' + JsonEscape(EdBackup1.Text) + '",' + #13#10 +
      '    "' + JsonEscape(EdBackup2.Text) + '",' + #13#10 +
      '    "' + JsonEscape(EdBackup3.Text) + '"' + #13#10 +
      '  ]' + #13#10 +
      '}';
  end
  else
  begin
    Json :=
      '{' + #13#10 +
      '  "mode": "adopt_existing",' + #13#10 +
      '  "data_dir": "' + JsonEscape(DataDir) + '",' + #13#10 +
      '  "backup_locations": [' + #13#10 +
      '    "' + JsonEscape(EdBackup1.Text) + '",' + #13#10 +
      '    "' + JsonEscape(EdBackup2.Text) + '",' + #13#10 +
      '    "' + JsonEscape(EdBackup3.Text) + '"' + #13#10 +
      '  ]' + #13#10 +
      '}';
  end;

  Lines := TStringList.Create;
  try
    Lines.Text := Json;
    Lines.SaveToFile(SeedPath);
  finally
    Lines.Free;
  end;

  if Mode = MODE_FRESH then
  begin
    Lines := TStringList.Create;
    try
      Lines.Add(EdAdminPwd.Text);
      Lines.SaveToFile(PwdPath);
    finally
      Lines.Free;
    end;
    // Intentionally NOT locking the ACL with `icacls /inheritance:r`.
    // The pwd file lives in {app}\data, which on Program Files installs is
    // already restricted to admins for write and to local users for read by
    // the default NTFS ACL. Stripping inheritance and granting only SYSTEM +
    // Administrators (as the previous version of this installer did) breaks
    // the [Run] step below: that step relaunches KTHEALTHERP.exe with the
    // INVOKING user token (UAC is dropped for postinstall flags), so a
    // strict-admin-only ACL gives the launcher PermissionError when it
    // tries to read the file and seeding silently fails — no admin user is
    // ever created. The file is short-lived: bootstrap deletes it on first
    // successful launch.
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  // On upgrade, never write a seed — the existing data folder + config.json
  // already bind the DB; launcher.consume_seed_if_present() then no-ops and
  // startup migrations bring the schema forward.
  if (CurStep = ssPostInstall) and (not IsUpgrade) then
    WriteSeedFile;
end;

// ----------------------------------------------------------------------------
//   uninstall — keep the data-preservation prompt from the previous version
// ----------------------------------------------------------------------------

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
