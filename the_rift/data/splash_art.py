"""
Champion splash-art fetcher with disk cache + LRU GPU-texture eviction.

Mirrors data/champion_icons.py, but splashes are huge (1215x717 ≈ 3.5 MB
RGBA each) so we cannot keep all ~170 registered. Strategy (spec § 7.3):

  • cache the JPEG to disk eagerly (assets/splash_cache/), ~25 MB for all
  • register at most LRU_MAX textures in DPG; evict the least-recently
    *used* one when a new register would exceed the cap
  • a miss returns None and the caller falls back to the portrait until
    the splash is ready — never blocks the render thread

Name → ddragon id resolution is reused from champion_icons so we don't
fetch champion.json twice.
"""
import os
import sys
import queue as _queue
import threading
from io import BytesIO

import dearpygui.dearpygui as dpg

try:
    import requests
except Exception:                                    # pragma: no cover
    requests = None

from data import champion_icons as _ci

_SPLASH_REG = "splash_tex_registry"
LRU_MAX = 4

_tex = {}                       # ddragon_id(lower) → texture tag
_lru = []                       # ddragon_id(lower), most-recent last
_pending = _queue.SimpleQueue() # (ddragon_id, jpg_bytes) → main thread
_in_flight = set()
_fetch_lock = threading.Lock()
_disk_enqueued = set()


def _cache_dir():
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "assets", "splash_cache")


def _ensure_reg():
    if not dpg.does_item_exist(_SPLASH_REG):
        dpg.add_texture_registry(tag=_SPLASH_REG)


def _ensure_cache_dir():
    try:
        os.makedirs(_cache_dir(), exist_ok=True)
    except Exception:
        pass


def _touch(key):
    """Mark `key` as most-recently-used."""
    try:
        _lru.remove(key)
    except ValueError:
        pass
    _lru.append(key)


def _evict_if_needed():
    """Drop least-recently-used registered textures past the cap."""
    while len(_lru) > LRU_MAX:
        old = _lru.pop(0)
        tag = _tex.pop(old, None)
        if tag and dpg.does_item_exist(tag):
            try:
                dpg.delete_item(tag)
            except Exception:
                pass


def _register_jpg_bytes(ddragon_id, jpg_bytes):
    """Main thread only: JPEG → DPG static texture, with LRU eviction."""
    key = ddragon_id.lower()
    tag = f"splash_{key}"
    if dpg.does_item_exist(tag):
        _tex[key] = tag
        _touch(key)
        _evict_if_needed()
        return
    try:
        from PIL import Image
        import numpy as np
        img = Image.open(BytesIO(jpg_bytes)).convert("RGBA")
        w, h = img.size
        data = (np.array(img, dtype=np.float32) / 255.0).flatten().tolist()
        _ensure_reg()
        dpg.add_static_texture(w, h, data, tag=tag, parent=_SPLASH_REG)
        _tex[key] = tag
        _touch(key)
        _evict_if_needed()
    except Exception as e:                            # pragma: no cover
        print(f"[splash_art] register failed for {ddragon_id}: {e}")


def _fetch_thread(ddragon_id):
    url = ("https://ddragon.leagueoflegends.com/cdn/img/champion/splash/"
           f"{ddragon_id}_0.jpg")
    try:
        if requests is None:
            return
        r = requests.get(url, timeout=12)
        if r.status_code == 200 and r.content:
            jpg = r.content
            _ensure_cache_dir()
            try:
                with open(os.path.join(_cache_dir(), f"{ddragon_id}_0.jpg"),
                          "wb") as f:
                    f.write(jpg)
            except Exception:
                pass
            _pending.put((ddragon_id, jpg))
    except Exception:
        pass
    finally:
        with _fetch_lock:
            _in_flight.discard(ddragon_id)


def flush_pending():
    """Drain pending registrations. Call from the main render thread."""
    drained = 0
    while drained < 2:                       # splashes are heavy; cap low
        try:
            ddragon_id, jpg = _pending.get_nowait()
        except _queue.Empty:
            return
        _register_jpg_bytes(ddragon_id, jpg)
        drained += 1


def get_texture(name):
    """Return a DPG texture tag for `name`'s splash, or None if not ready
    (caller should fall back to the portrait until then)."""
    if not name:
        return None
    ddragon_id = _ci._ddragon_id(name)
    if not ddragon_id:
        return None
    key = ddragon_id.lower()
    tag = _tex.get(key)
    if tag and dpg.does_item_exist(tag):
        _touch(key)
        return tag

    cache_path = os.path.join(_cache_dir(), f"{ddragon_id}_0.jpg")
    if os.path.isfile(cache_path):
        if ddragon_id not in _disk_enqueued:
            try:
                with open(cache_path, "rb") as f:
                    _pending.put((ddragon_id, f.read()))
                _disk_enqueued.add(ddragon_id)
            except Exception:
                pass
        return None

    with _fetch_lock:
        if ddragon_id in _in_flight:
            return None
        _in_flight.add(ddragon_id)
    threading.Thread(target=_fetch_thread, args=(ddragon_id,),
                     daemon=True, name=f"splash_fetch_{ddragon_id}").start()
    return None
