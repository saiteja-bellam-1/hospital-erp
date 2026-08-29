# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for KT HEALTH ERP.
Build with: pyinstaller hospital_erp.spec --clean
"""

import os
from PyInstaller.utils.hooks import collect_all

block_cipher = None

# Path to frontend build output
frontend_build = os.path.join('..', 'frontend', 'build')

# ReportLab barcode widgets (code128, eanbc, …) are loaded from
# reportlab.graphics.barcode.__init__ via a dynamic _reset() import graph
# that PyInstaller does not follow. Without collect_all, a frozen build
# crashes on startup with:
#   ModuleNotFoundError: No module named 'reportlab.graphics.barcode.code128'
# as soon as lab/pharmacy import label_pdf_service.
reportlab_datas, reportlab_binaries, reportlab_hiddenimports = collect_all('reportlab')

a = Analysis(
    ['launcher.py'],
    pathex=['.'],
    binaries=reportlab_binaries,
    datas=[
        # Bundle the React frontend build
        (frontend_build, 'frontend_build'),
        # Bundle the app icon
        ('assets/icon.ico', 'assets'),
        ('assets/icon.png', 'assets'),
    ] + reportlab_datas,
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
        'app.routes.backup',
        'app.services.db_seed',
        'app.services.system_modules',
        'app.models.physiotherapy',
        'app.routes.physiotherapy',
        'app.routes.referrals',
        'app.models.referral',
        'setup_system_data',
        'app.services.super_admin_service',
        'app.utils.auth',
        'app.utils.dependencies',
        'app.utils.pdf_service',
        'app.utils.label_pdf_service',
        'app.utils.machine_id',
        'app.middleware.license_middleware',
        'app.middleware.audit_middleware',
        'app.models.audit',
        'app.services.audit_service',
        'app.routes.audit',

        # Other dependencies
        'reportlab',
        'reportlab.lib.pagesizes',
        'reportlab.platypus',
        'reportlab.graphics',
        'reportlab.graphics.barcode',
        'reportlab.graphics.barcode.code128',
        'reportlab.graphics.barcode.code39',
        'reportlab.graphics.barcode.code93',
        'reportlab.graphics.barcode.eanbc',
        'reportlab.graphics.barcode.widgets',
        'reportlab.graphics.barcode.common',
        'reportlab.graphics.barcode.qr',
        'reportlab.graphics.barcode.usps',
        'reportlab.graphics.barcode.usps4s',
        'reportlab.graphics.barcode.fourstate',
        'reportlab.graphics.barcode.ecc200datamatrix',
        'PyPDF2',
        'multipart',
        'jose',
        'pydantic_settings',
        'pandas',
        'openpyxl',
        'dateutil',
    ] + reportlab_hiddenimports,
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
    console=False,  # Windowless: launcher.py opens a console only in --debug mode
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico',
)
