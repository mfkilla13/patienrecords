# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

matplotlib_datas = collect_data_files('matplotlib')
matplotlib_hiddenimports = collect_submodules('matplotlib')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('data', 'data'), ('templates', 'templates'), ('widgets', 'widgets'), ('windows', 'windows')] + matplotlib_datas,
    hiddenimports=matplotlib_hiddenimports + [
        'matplotlib',
        'matplotlib.pyplot',
        'matplotlib.figure',
        'matplotlib.dates',
        'matplotlib.backends.backend_qtagg',
        'matplotlib.backends.backend_qt5agg',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=2,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [('O', None, 'OPTION'), ('O', None, 'OPTION')],
    exclude_binaries=True,
    name='MedQT',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='MedQT',
)
