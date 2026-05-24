# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for The Rift — single .exe bundle.
# Run from the_rift/ directory:
#   pyinstaller the_rift.spec --noconfirm

import importlib
import os

HERE = os.path.dirname(os.path.abspath(SPEC))


def _maybe(name):
    """Include the module name iff it's importable in the build env.
    Lets us mark `pygame` as an optional bundle — when it isn't installed
    (e.g. on Python versions without a prebuilt wheel), PyInstaller skips
    it and `ui/audio.py` degrades to silent no-ops at runtime."""
    try:
        importlib.import_module(name)
        return [name]
    except Exception:
        return []


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
        'data.draft_engine',
        'data.draft_board',
        'data.champion_icons',
        'data.splash_art',
        'data.patch_ticker',
        'data.draft_sync',
        # Multiplayer draft sync — WebSocket client (data/draft_sync.py)
        'websockets',
        'websockets.client',
        'websockets.legacy',
        'websockets.legacy.client',
        'ui',
        'ui.rankings',
        'ui.draft',
        'ui.draft_sync_ui',
        'ui.scout',
        'ui.inhouse',
        'ui.tierlist',
        'ui.settings',
        'ui.commands',
        'ui.feed',
        'ui.sidebar',
        'ui.effects',
        'ui.lol_theme',
        'ui.audio',
        'ui.board_rail',
        # Phase 0a / 0b — polish toolkit + design tokens.
        'ui.toast',
        'ui.tokens',
        'ui.fmt',
        # Phase 4 + 5 + 6 — new surfaces / overlays.
        'ui.home',
        'ui.profile',
        'ui.wrapped',
        'ui.hotkeys',
        # Phase 5c — share-card renderer (PIL-based).
        'data.share_cards',
        # Phase 0d / Phase 2 / Phase 1 — REST + engine clients + sheet mirror.
        'data.rift_api',
        'data.engine_api',
        'data.sheet_mirror',
        # Phase 1 — modularized fetch-ranks package.
        'data.fetch_ranks',
        'data.fetch_ranks.constants',
        'data.fetch_ranks.sheets',
        'data.fetch_ranks.scoring',
        'data.fetch_ranks.riot',
        'data.fetch_ranks.tier_analytics',
        'data.fetch_ranks.rankings',
        'data.fetch_ranks.scouting',
        'data.fetch_ranks.inhouse',
        'data.fetch_ranks.activity',
        'data.fetch_ranks.draft',
        'data.fetch_ranks.cli',
        # Draft Tool v3 — pygame.mixer cue wrapper (ui/audio.py).
        # Optional: when pygame isn't installed (no prebuilt wheel for the
        # current Python), the audio module silently no-ops at runtime.
        # WAVs sit in assets/sounds/ which is bundled via `datas` above.
        *_maybe('pygame'),
        *_maybe('pygame.mixer'),
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
