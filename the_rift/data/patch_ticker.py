"""
Live patch ticker — fetches current LoL patch version, free champion
rotation, and assembles a list of ticker strings for the bottom marquee.

Runs in a background thread on app startup; results are cached in module
state. The UI reads `get_ticker_items()` every frame — never blocks.
"""
import threading
import time as _time

import requests


# Module-level cache. UI reads these; background thread writes.
_items = [
    "WELCOME TO THE RIFT",
    "LIVE PATCH DATA LOADING…",
]
_patch_version = None
_last_refresh  = 0.0
_REFRESH_SEC   = 60 * 30   # refresh every 30 minutes
_lock          = threading.Lock()


def get_ticker_items():
    """UI accessor — returns the current ticker string list (never blocks)."""
    with _lock:
        return list(_items)


def get_patch_version():
    with _lock:
        return _patch_version


def _fetch_latest_patch():
    """Return latest patch version string (e.g. '15.10.1') or None."""
    try:
        r = requests.get("https://ddragon.leagueoflegends.com/api/versions.json",
                         timeout=8)
        versions = r.json()
        return versions[0] if versions else None
    except Exception:
        return None


def _fetch_free_rotation(api_key, region="na1"):
    """Return list of champion key strings (ddragon 'key' field, numeric)
    on the current free rotation, or None on failure."""
    if not api_key:
        return None
    try:
        r = requests.get(
            f"https://{region}.api.riotgames.com/lol/platform/v3/champion-rotations",
            headers={"X-Riot-Token": api_key}, timeout=8)
        if r.status_code != 200:
            return None
        data = r.json()
        return [str(c) for c in data.get("freeChampionIds", [])]
    except Exception:
        return None


def _fetch_champion_id_to_name(patch):
    """Return dict mapping numeric champion key → name for the given patch."""
    try:
        r = requests.get(
            f"https://ddragon.leagueoflegends.com/cdn/{patch}/data/en_US/champion.json",
            timeout=10)
        data = r.json().get("data", {})
        return {info["key"]: info["name"] for info in data.values()}
    except Exception:
        return {}


def _build_items():
    """Refresh the ticker contents. Safe to call from any thread."""
    global _items, _patch_version, _last_refresh

    items = []

    patch = _fetch_latest_patch()
    if patch:
        items.append(f"PATCH {patch} LIVE")

    # Free rotation — needs Riot API key
    try:
        from data.config import load_config
        cfg = load_config()
        api_key = cfg.get("api_key") or ""
    except Exception:
        api_key = ""

    rotation_ids = _fetch_free_rotation(api_key)
    if rotation_ids and patch:
        key_to_name = _fetch_champion_id_to_name(patch)
        names = [key_to_name.get(k) for k in rotation_ids if key_to_name.get(k)]
        if names:
            items.append("FREE ROTATION  ·  " + "  ·  ".join(names[:14]))

    # Always include a few flavor lines from tips.py so the ticker never
    # feels empty even when the network is down.
    try:
        from data.tips import TIPS
        # Take a deterministic-ish slice (avoid random for testability)
        flavor = [t.upper() for t in TIPS[:6] if len(t) < 80]
        items.extend(flavor)
    except Exception:
        pass

    if not items:
        items = ["THE RIFT  ·  STAY SHARP"]

    with _lock:
        _items = items
        _patch_version = patch
        _last_refresh = _time.monotonic()


def start_background_refresh():
    """Kick off a daemon thread that refreshes the ticker periodically."""
    def _loop():
        while True:
            _build_items()
            _time.sleep(_REFRESH_SEC)

    t = threading.Thread(target=_loop, daemon=True, name="patch_ticker")
    t.start()
