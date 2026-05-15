"""
Champion square-icon fetcher + cache.

- Lazy fetch from Data Dragon CDN; cache to local disk (assets/champion_cache/).
- `get_texture(name)` returns a DPG texture tag if registered, else None
  (and kicks off a background download on first miss).
- Network calls happen in a daemon thread; the main render thread drains
  registered textures via `flush_pending()` each frame.
"""

import os
import re
import threading
import queue as _queue
from io import BytesIO

import requests
import dearpygui.dearpygui as dpg

from data import patch_ticker


# ── Texture registry ────────────────────────────────────────────────
_CHAMP_REG = "rift_champion_icon_reg"
_champ_textures = {}              # ddragon_id (lowercase) → dpg texture tag
_pending_icons  = _queue.SimpleQueue()  # (ddragon_id, png_bytes) → main thread
_fetch_in_flight = set()          # ids currently being downloaded
_disk_enqueued   = set()          # ids enqueued from local cache (await register)
_fetch_lock = threading.Lock()

_id_map_cache = None              # {display_name_upper: ddragon_id, id_upper: id}
_id_map_lock = threading.Lock()

CACHE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets", "champion_cache")


# ── Name → ddragon ID resolution ────────────────────────────────────

def _ensure_id_map():
    """Fetch champion.json once and build display-name → ddragon-id map."""
    global _id_map_cache
    with _id_map_lock:
        if _id_map_cache is not None:
            return _id_map_cache
        try:
            patch = patch_ticker.get_patch_version()
            if not patch:
                r = requests.get(
                    "https://ddragon.leagueoflegends.com/api/versions.json",
                    timeout=8)
                versions = r.json()
                patch = versions[0] if versions else None
            if not patch:
                _id_map_cache = {}
                return _id_map_cache
            r = requests.get(
                f"https://ddragon.leagueoflegends.com/cdn/{patch}/data/en_US/champion.json",
                timeout=10)
            data = r.json().get("data", {})
            m = {}
            for info in data.values():
                m[info["name"].strip().upper()] = info["id"]
                m[info["id"].upper()] = info["id"]
            _id_map_cache = m
            return _id_map_cache
        except Exception:
            _id_map_cache = {}
            return _id_map_cache


def _ddragon_id(name):
    """Map a display name (e.g. 'Cho'Gath', 'Wukong') to a ddragon URL id."""
    if not name:
        return None
    key = name.strip().upper()
    m = _ensure_id_map()
    if key in m:
        return m[key]
    # Heuristic fallback if the map fetch failed: strip punctuation,
    # title-case each whitespace-separated word.
    words = []
    for w in name.strip().split():
        w2 = re.sub(r"[^A-Za-z0-9]", "", w)
        if w2:
            words.append(w2[0].upper() + w2[1:].lower())
    return "".join(words) if words else None


# ── Registry / cache plumbing ───────────────────────────────────────

def _ensure_reg():
    if not dpg.does_item_exist(_CHAMP_REG):
        dpg.add_texture_registry(tag=_CHAMP_REG)


def _ensure_cache_dir():
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
    except Exception:
        pass


def _register_png_bytes(ddragon_id, png_bytes):
    """Main thread only: PIL → DPG static texture."""
    key = ddragon_id.lower()
    tag = f"champ_{key}"
    if dpg.does_item_exist(tag):
        _champ_textures[key] = tag
        return
    try:
        from PIL import Image
        import numpy as np
        img  = Image.open(BytesIO(png_bytes)).convert("RGBA")
        w, h = img.size
        data = (np.array(img, dtype=np.float32) / 255.0).flatten().tolist()
        _ensure_reg()
        dpg.add_static_texture(w, h, data, tag=tag, parent=_CHAMP_REG)
        _champ_textures[key] = tag
    except Exception as e:
        print(f"[champion_icons] register failed for {ddragon_id}: {e}")


def _fetch_thread(ddragon_id, patch):
    """Daemon thread: download PNG, save to disk, enqueue for register."""
    url = (f"https://ddragon.leagueoflegends.com/cdn/{patch}"
           f"/img/champion/{ddragon_id}.png")
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200 and r.content:
            png = r.content
            _ensure_cache_dir()
            try:
                with open(os.path.join(CACHE_DIR, f"{ddragon_id}.png"),
                          "wb") as f:
                    f.write(png)
            except Exception:
                pass
            _pending_icons.put((ddragon_id, png))
    except Exception:
        pass
    finally:
        with _fetch_lock:
            _fetch_in_flight.discard(ddragon_id)


def flush_pending():
    """Drain the pending-register queue. Call from main render thread."""
    drained = 0
    while drained < 16:                       # cap per frame
        try:
            ddragon_id, png = _pending_icons.get_nowait()
        except _queue.Empty:
            return
        _register_png_bytes(ddragon_id, png)
        drained += 1


def get_texture(name):
    """Return DPG texture tag for a champion display name, or None.

    First miss: enqueues from local cache (if present) or starts a
    background download. Subsequent calls find the registered texture."""
    if not name:
        return None
    ddragon_id = _ddragon_id(name)
    if not ddragon_id:
        return None
    key = ddragon_id.lower()
    tag = _champ_textures.get(key)
    if tag and dpg.does_item_exist(tag):
        return tag

    # Try local disk cache (cheap, no network)
    cache_path = os.path.join(CACHE_DIR, f"{ddragon_id}.png")
    if os.path.isfile(cache_path):
        if ddragon_id not in _disk_enqueued:
            try:
                with open(cache_path, "rb") as f:
                    _pending_icons.put((ddragon_id, f.read()))
                _disk_enqueued.add(ddragon_id)
            except Exception:
                pass
        return None

    # Kick off network fetch (once per id)
    with _fetch_lock:
        if ddragon_id in _fetch_in_flight:
            return None
        _fetch_in_flight.add(ddragon_id)
    patch = patch_ticker.get_patch_version()
    if not patch:
        with _fetch_lock:
            _fetch_in_flight.discard(ddragon_id)
        return None
    threading.Thread(
        target=_fetch_thread, args=(ddragon_id, patch),
        daemon=True, name=f"champ_fetch_{ddragon_id}",
    ).start()
    return None
