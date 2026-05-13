# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for The Rift — single .exe bundle.
# Run from the_rift/ directory:
#   pyinstaller the_rift.spec --noconfirm

import os

HERE = os.path.dirname(os.path.abspath(SPEC))

a = Analysis(
    [os.path.join(HERE, 'main.py')],
    pathex=[HERE],
    binaries=[],
    datas=[
        (os.path.join(HERE, 'assets'),       'assets'),
        (os.path.join(HERE, 'fonts'),        'fonts'),
        (os.path.join(HERE, 'data'),         'data'),
        (os.path.join(HERE, '..', 'credentials.json'), '.'),
    ],
    hiddenimports=[
        # Third-party
        'dearpygui',
        'dearpygui.dearpygui',
        'PIL',
        'PIL.Image',
        'numpy',
        'gspread',
        'google.oauth2',
        'google.oauth2.service_account',
        'google.auth',
        'google.auth.transport',
        'google.auth.transport.requests',
        'requests',
        'urllib3',
        # Project modules
        'theme',
        'core',
        'core.animations',
        'core.state',
        'data',
        'data.reader',
        'data.config',
        'data.fetch_ranks_gsheets',
        'data.inhouse_tracker',
        'ui',
        'ui.rankings',
        'ui.draft',
        'ui.scout',
        'ui.inhouse',
        'ui.tierlist',
        'ui.settings',
        'ui.commands',
        'ui.feed',
        'ui.sidebar',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib'],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='TheRift',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,   # add .ico here when available
)
