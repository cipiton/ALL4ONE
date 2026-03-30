# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

hiddenimports = []
hiddenimports += collect_submodules("app")
hiddenimports += collect_submodules("engine")
hiddenimports += collect_submodules("ui")
hiddenimports += collect_submodules("tkinterdnd2")

datas = [
    ('skills', 'skills'),
    ('config.ini', '.'),
    ('.env.example', '.'),
    ('README.md', '.'),
]
datas += collect_data_files("tkinterdnd2")

a = Analysis(
    ['gui.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Fake Agent',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Fake Agent',
)
