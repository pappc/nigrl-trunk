# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['nigrl.py'],
    pathex=[],
    binaries=[],
    datas=[('Zilk_16x16.png', '.'), ('nigrl-tileset-2.png', '.'), ('fire_tile.pixil', '.'), ('nigrl-ascii-v3.png', '.'), ('nigrl-graphics-curses12x12.png', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='NIGRL',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
