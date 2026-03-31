# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

import glob as _glob
_dev_pngs = [(f, 'dev-assets') for f in _glob.glob('dev-assets/*.png')]
datas = [('Zilk_16x16.png', '.'), ('nigrl-tileset-2.png', '.')] + _dev_pngs
binaries = []
hiddenimports = []
tmp_ret = collect_all('tcod')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['nigrl.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
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
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
