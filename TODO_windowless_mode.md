# TODO — Windowless Windows app + opt-in debug/terminal mode

Goal: `KTHEALTHERP.exe` runs windowless in the background by default; a
`--debug` flag (and a Start Menu "Debug Mode" shortcut) shows a live log
console for troubleshooting.

## Tasks

- [x] 1. `backend/hospital_erp.spec` — set `console=False` (line 133).
- [x] 2. `backend/launcher.py` — add helpers + wire into `main()`:
  - `_is_debug_requested()` (`--debug`/`-d`/`KTHEALTH_DEBUG=1`)
  - `_enable_debug_console()` (AttachConsole parent / AllocConsole)
  - `_redirect_output_to_logfile()` (windowless → `data/logs/server.log`)
  - `_acquire_single_instance()` (named mutex → focus existing instance)
  - write chosen port to `data/.runtime_port`
- [x] 3. `backend/app/routes/system.py` — `POST /api/system/shutdown`
  (admin-only) + `source=server` option on the `/logs` endpoint.
- [x] 4. `frontend/src/pages/modules/SoftwareUpdate.js` — admin "Shut Down
  Server" button with confirm dialog.
- [x] 5. `installer/installer.iss` — Start Menu "(Debug Mode)" shortcut
  passing `--debug`.
- [x] 6. Verified backend imports cleanly (launcher.py + system.py).

## Verification (Windows build)

1. `build_exe.bat` → `backend/dist/KTHEALTHERP.exe`.
2. Double-click → no console, browser opens, `data/logs/server.log` fills.
3. Double-click again → browser opens to running app, only one process.
4. Debug Mode shortcut / `KTHEALTHERP.exe --debug` → console with logs.
5. Admin "Shut Down Server" → process exits.
6. Dev sanity: `python launcher.py` unchanged.
