# -*- mode: python ; coding: utf-8 -*-
import os

block_cipher = None
frontend_build = os.path.join('..', 'frontend', 'build')

a = Analysis(
    ['launcher.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        (frontend_build, 'frontend_build'),
    ] if os.path.isdir(frontend_build) else [],
    hiddenimports=[
        'uvicorn.logging', 'uvicorn.loops', 'uvicorn.loops.auto',
        'uvicorn.protocols', 'uvicorn.protocols.http', 'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets', 'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan', 'uvicorn.lifespan.on', 'uvicorn.lifespan.off',
        'cryptography', 'cryptography.hazmat.primitives.asymmetric.ed25519',
        'app',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
    name='KTLicenseManager',
    debug=False,
    strip=False,
    upx=True,
    console=True,
    icon=None,
)
