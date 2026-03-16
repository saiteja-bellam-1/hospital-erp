# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for KT HEALTH ERP.
Build with: pyinstaller hospital_erp.spec --clean
"""

import os

block_cipher = None

# Path to frontend build output
frontend_build = os.path.join('..', 'frontend', 'build')

a = Analysis(
    ['launcher.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        # Bundle the React frontend build
        (frontend_build, 'frontend_build'),
    ],
    hiddenimports=[
        # Uvicorn internals
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'uvicorn.lifespan.off',

        # SQLAlchemy
        'sqlalchemy.dialects.sqlite',

        # Passlib / bcrypt
        'passlib.handlers.bcrypt',
        'bcrypt',

        # Cryptography (for python-jose)
        'cryptography',
        'cryptography.hazmat.primitives.kdf.pbkdf2',
        'cryptography.hazmat.backends',

        # App modules
        'main',
        'config.database',
        'config.settings',
        'app.models.user',
        'app.models.permissions',
        'app.models.system',
        'app.models.hospital',
        'app.models.prescriptions_simple',
        'app.models.doctor_availability',
        'app.models.license',
        'app.routes.auth',
        'app.routes.patients',
        'app.routes.admin',
        'app.routes.system',
        'app.routes.module_admin',
        'app.routes.hospital_admin',
        'app.routes.appointments',
        'app.routes.prescriptions',
        'app.routes.medicines',
        'app.routes.consultations',
        'app.routes.prescriptions_simple',
        'app.routes.doctor_availability',
        'app.routes.lab',
        'app.routes.ehr',
        'app.routes.license',
        'app.utils.paths',
        'app.utils.config',
        'app.routes.setup',
        'app.routes.backup',
        'setup_system_data',
        'app.services.super_admin_service',
        'app.utils.auth',
        'app.utils.dependencies',
        'app.utils.pdf_service',
        'app.middleware.license_middleware',

        # Other dependencies
        'reportlab',
        'reportlab.lib.pagesizes',
        'reportlab.platypus',
        'multipart',
        'jose',
        'pydantic_settings',
        'pandas',
        'openpyxl',
        'dateutil',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='KTHEALTHERP',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Set to False for production (no console window)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Add icon path here: icon='assets/icon.ico'
)
