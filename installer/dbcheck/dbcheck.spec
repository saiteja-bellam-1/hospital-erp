# PyInstaller spec for dbcheck.exe — tiny CLI used by the Inno Setup wizard.
# Built into installer/bin/dbcheck.exe by build_dbcheck.bat.
#
# We add the backend source tree to sys.path so dbcheck.py can reuse
# app.utils.machine_id and app.services.license_service without us having to
# duplicate the Ed25519 verification or the WMI-based machine fingerprint.
import os
import sys

spec_dir = os.path.abspath(os.path.dirname(SPEC) if "SPEC" in dir() else ".")
repo_root = os.path.abspath(os.path.join(spec_dir, "..", ".."))
backend_dir = os.path.join(repo_root, "backend")

if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)


a = Analysis(
    [os.path.join(spec_dir, "dbcheck.py")],
    pathex=[backend_dir],
    binaries=[],
    datas=[],
    hiddenimports=[
        "app.utils.machine_id",
        "app.services.license_inspect",
        "app.services.user_csv_import",
        "app.licensing.crypto",
        "cryptography",
        "cryptography.hazmat.primitives",
        "cryptography.hazmat.primitives.asymmetric.ed25519",
        "cryptography.hazmat.primitives.serialization",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "pytest",
        "numpy",
        "PIL",
        "reportlab",
        "fastapi",
        "uvicorn",
        "sqlalchemy",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="dbcheck",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
