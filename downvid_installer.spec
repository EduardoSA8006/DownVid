# PyInstaller spec para o instalador do DownVid
# Execute: pyinstaller downvid_installer.spec

import os
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

app_name = 'DownVid-Setup'
entry_script = 'installer_downvid.py'

# Dados (PySide6 styles/qml e afins) + certifi (CA bundle)
datas = []
datas += collect_data_files('PySide6', include_py_files=False)
datas += collect_data_files('certifi', include_py_files=False)

a = Analysis(
    [entry_script],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[],
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
    console=False,            # GUI app
    disable_windowed_traceback=False,
    target_arch=None,
    icon=None,                # Coloque um .ico e troque aqui se quiser
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