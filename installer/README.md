# Windows installer

Wraps `KTHEALTHERP.exe` in a unified Inno Setup wizard that handles
file installation **and** the first-run setup the React `SetupWizard` used
to handle. After install, the app boots straight into the login screen.

## Wizard flow

1. **Welcome**
2. **License agreement** (Inno Setup default — currently empty / skipped)
3. **Install destination** — defaults to `C:\Program Files\KTHEALTHERP`
4. **Data folder** — radio choice:
   - *Create a new data folder* (path picker, default `<app>\data`); next
     button writability-probes the chosen folder via `dbcheck.exe check-writable`.
   - *Use existing data folder* (for reinstalls). Triggers the next page.
5. **Database integrity check** *(only for "use existing")* — runs
   `dbcheck.exe check-db <folder>` and shows the result. Block "Next" on failure.
6. **License (optional)** *(skipped in adopt-existing mode)* — shows the
   machine ID with a copy field, accepts a `.lic` file picker, runs
   `dbcheck.exe validate-license <path>` on click. Block "Next" if a path
   was given but verification failed (operator can dismiss with a confirm).
7. **Hospital details** *(fresh install only)* — name (required), address,
   phone, email.
8. **Administrator account** *(fresh install only)* — username (required, no
   spaces), email, password + confirm. Min 8 characters. No prefilled
   username — operator must pick.
9. **Backup destinations** — three optional folder pickers.
10. **Tasks** — desktop shortcut, Start Menu shortcut, firewall rule.
11. **Ready** — summary
12. **Install** — copies files, then writes the seed file:
    - `{app}\data\install_seed.json` (collected answers)
    - `{app}\data\.install_seed.pwd` (password, ACL-locked to SYSTEM + Administrators)
13. **Finished** — "Launch now" checkbox.

On first launch, `backend\launcher.py` calls
`app.services.bootstrap_from_seed.consume_seed_if_present`, which reads the
two files, runs the same DB seeding path the React wizard runs, applies the
license if one was provided, persists the backup destinations into
`config.json`, and deletes both seed files. Failure leaves the seed files in
place so the operator can fix and retry; the failure traceback is recorded in
`data\.bootstrap_status.json` and `data\logs\launcher.log`.

If no seed file exists (e.g. someone ran the source install via
`install_and_setup.py` instead of the installer), the React `SetupWizard`
takes over as the fallback.

## Build steps

1. Build the `.exe`:

   ```cmd
   build_exe.bat
   ```

2. Build the wizard helper (only needed once, or whenever `dbcheck.py` changes):

   ```cmd
   installer\build_dbcheck.bat
   ```

   Output: `installer\bin\dbcheck.exe`. `build_installer.bat` calls this
   automatically if the binary is missing.

3. Install [Inno Setup 6+](https://jrsoftware.org/isinfo.php). The compiler
   `ISCC.exe` should be on `PATH` or in the default install location.

4. Run the installer builder:

   ```cmd
   build_installer.bat
   ```

   Override the version with `set INSTALLER_VERSION=1.2.0` before running.

   Output: `backend\dist\installer\KTHEALTHERP_Setup_<version>.exe`

## `dbcheck.exe`

A tiny PyInstaller-built CLI used by the wizard for things Pascal can't do
itself (Ed25519 signature verification, SQLite probes, machine fingerprint).
Subcommands:

| Command | What it does |
|---|---|
| `dbcheck machine-id` | Print the current machine ID (matches what the running app reports) |
| `dbcheck check-db <folder>` | Confirm folder contains a working KT HEALTH ERP DB |
| `dbcheck validate-license <path>` | Dry-run a `.lic` file (signature + machine match + expiry) |
| `dbcheck check-writable <folder>` | Confirm folder is creatable + writable |

All commands emit a single line of JSON to stdout (`{"ok": bool, ...}`).

## Code signing (optional)

Both `build_exe.bat` and `build_installer.bat` look for these env vars and
sign with `signtool.exe` if they're present:

```cmd
set SIGNING_CERT=C:\path\to\cert.pfx
set SIGNING_PASS=your-password
set SIGNING_TIMESTAMP=http://timestamp.digicert.com   :: optional
```

`signtool.exe` ships with the Windows SDK. If `SIGNING_CERT` is empty the
signing step is skipped silently — useful for dev / smoke builds.

Without signing, Windows SmartScreen will warn end users on first install. An
EV (Extended Validation) certificate avoids the warning entirely; OV / regular
code-signing certificates need a few hundred installs to build reputation
before SmartScreen relaxes.

## Smoke test checklist

Run on a clean Windows VM after every meaningful change to the wizard:

- [ ] **Fresh install, defaults.** Operator clicks Next through the wizard
      with default data folder, no license, blank backups, default admin.
      After "Launch now": browser shows login screen (not the React wizard);
      typing the chosen username + password logs them in.
- [ ] **Fresh install with license.** Drop a valid `.lic` for this machine on
      the License page → click Verify → green "License OK". After install,
      modules gated by license features appear in the sidebar immediately.
- [ ] **Fresh install with backup destinations.** Pick two folder paths.
      After install, Admin → Backup management shows both as mirror
      destinations and the next mirror tick writes to both.
- [ ] **Adopt existing data folder.** Reinstall over a previous install:
      pick "Use existing", point at the previous `data\` folder. DB-check
      page shows green. License/Hospital/Admin pages are skipped. After
      install, original credentials still log in.
- [ ] **Wrong-machine license.** Drop a `.lic` for a different machine →
      click Verify → red "License rejected: …". Confirmation dialog forces a
      conscious skip.
- [ ] **Bad password.** Try a 7-char password → "Password must be at least 8
      characters" inline error blocks Next.
- [ ] **Mismatched passwords.** "Passwords do not match" inline error blocks
      Next.
- [ ] **Username with whitespace.** "Username cannot contain spaces" blocks Next.
- [ ] **Bad existing folder.** Point "use existing" at a folder with no
      `kthealth_erp.db` → DB-check page shows the error and blocks Next.
- [ ] **Non-writable backup folder.** Choose a backup path under a read-only
      drive — the bootstrap drops it silently from `config.json` (visible in
      `data\logs\launcher.log` as a warning) rather than failing the install.

## What the installer does NOT do

- It does **not** ship a `data\` directory in the install payload — `launcher.py`
  creates it at first launch. Keeps the installer payload small and prevents
  upgrades from clobbering the customer DB.
- It does **not** install Python, Node, or any runtime dependencies — those
  are bundled into `KTHEALTHERP.exe` by PyInstaller.
- It does **not** support Mac. The Mac source install path
  (`install_and_setup.py` + manual run) still works for development.
