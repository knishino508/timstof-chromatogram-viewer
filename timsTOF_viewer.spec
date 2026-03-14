# -*- mode: python ; coding: utf-8 -*-
# timsTOF_viewer.spec
#
# 使い方:
#   pyinstaller timsTOF_viewer.spec
#
# 注意: opentimspy / opentims_bruker_bridge のDLLを自動収集します

import sys
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

# opentimspy / opentims_bruker_bridge のDLL・データを収集
datas = []
datas += collect_data_files('opentimspy')
datas += collect_data_files('opentims_bruker_bridge')

binaries = []
binaries += collect_dynamic_libs('opentimspy')
binaries += collect_dynamic_libs('opentims_bruker_bridge')

# pyqtgraph が使う Qt プラグインを含める
datas += collect_data_files('pyqtgraph')

block_cipher = None

a = Analysis(
    ['main_en_optimized.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        'opentimspy',
        'opentimspy.opentims',
        'opentims_bruker_bridge',
        'pyqtgraph',
        'pyqtgraph.graphicsItems',
        'pyqtgraph.widgets',
        'PyQt6',
        'PyQt6.QtWidgets',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'numpy',
        'pandas',
        'pyarrow',
        'sqlite3',
    ],
    hookspath=['.'],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'tkinter',
        'IPython',
        'jupyter',
        'scipy',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='timsTOF_Viewer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,       # コンソールウィンドウを表示しない
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='icon.ico',   # アイコンがあればコメントアウト解除
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='timsTOF_Viewer',
)
