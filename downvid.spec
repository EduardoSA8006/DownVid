# PyInstaller spec para DownVid no Windows
# Execute: pyinstaller downvid.spec

import sys
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Principais fontes
entry_script = 'main.py'
app_name = 'DownVid'

# Hidden imports úteis para yt_dlp e PySide6
hiddenimports = [
    'yt_dlp',
    'yt_dlp.compat',
    'yt_dlp.extractor',
    'yt_dlp.postprocessor',
]

# Coleta de dados (Qt e yt_dlp, certificados, etc.)
datas = []
datas += collect_data_files('PySide6', include_py_files=False)
datas += collect_data_files('yt_dlp', include_py_files=False)
datas += collect_data_files('certifi', include_py_files=False)

a = Analysis(
    [entry_script],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
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
    name=app_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    console=False,         # GUI app (sem console)
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=app_name
)