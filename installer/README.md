# Windows installer

Wraps `KTHEALTHERP.exe` in a real Windows installer with Start Menu / Desktop
shortcuts, an uninstaller registered in **Apps & Features**, and a Windows
Firewall rule for LAN access.

## Build steps

1. Build the `.exe` first:

   ```cmd
   build_exe.bat
   ```

2. Install [Inno Setup 6+](https://jrsoftware.org/isinfo.php). The installer
   compiler `ISCC.exe` should be on `PATH` or in the default install location.

3. Run the installer builder:

   ```cmd
   build_installer.bat
   ```

   Override the version with `set INSTALLER_VERSION=1.2.0` before running.

   Output: `backend\dist\installer\KTHEALTHERP_Setup_<version>.exe`

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

## What the installer does

- Installs to `C:\Program Files\KTHEALTHERP\` by default.
- Creates Start Menu shortcuts (with an uninstall entry).
- Optionally creates a Desktop shortcut.
- Optionally adds a Windows Firewall rule for TCP 8000-8020 (the launcher's
  port range), so other devices on the LAN can reach the server.
- Leaves `C:\Program Files\KTHEALTHERP\data\` in place on uninstall (the DB,
  uploads, and config) and asks the operator before wiping it.

## What it does NOT do

- It does **not** ship a `data\` directory — `launcher.py` creates one on
  first launch. This keeps the installer payload small and means upgrades /
  reinstalls don't clobber the customer database.
- It does **not** install Python, Node, or any runtime dependencies — those
  are bundled into `KTHEALTHERP.exe` by PyInstaller.
