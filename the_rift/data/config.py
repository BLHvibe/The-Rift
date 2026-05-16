"""
Config loader/saver for The Rift.
Reads and writes data/config.json (same format as launcher_config.json).
"""
import json, os, sys

def _config_path():
    """Locate config.json — works both dev (file beside this module) and frozen .exe."""
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "config.json")

_DEFAULTS = {
    "api_key":   "",
    "sheet_url": "https://docs.google.com/spreadsheets/d/1jtScmcfol2YBi0FUSwkXVWkJ4qRBuP9EVIfWSWSDpms/edit",
    "creds_path":"credentials.json",
    "region":    "na1",
    "routing":   "americas",
    "players":   [],
    "last_run":  {},
    # Draft Board v2.7 — when True, CALM MODE freezes ambient cyberpunk motion
    # (scanlines, grid drift, breathing pulses, flicker, marching dashes).
    # State-change animations (typewriter, slide-in, ripple) are unaffected.
    "calm_mode": False,
}

def _load_bundled_config():
    """Read the bundled config template shipped inside the frozen exe."""
    if not getattr(sys, "frozen", False):
        return {}
    bundled = os.path.join(sys._MEIPASS, "data", "config.json")
    if not os.path.exists(bundled):
        return {}
    try:
        with open(bundled, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def load_config():
    path = _config_path()
    bundled = _load_bundled_config()

    if not os.path.exists(path):
        # First run of the frozen exe — bootstrap from the bundled config
        # template so the API key, sheet URL, etc. are pre-populated.
        if bundled:
            cfg = dict(_DEFAULTS)
            cfg.update(bundled)
            cfg["creds_path"] = "credentials.json"
            save_config(cfg)
            return cfg
        return dict(_DEFAULTS)

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        cfg = dict(_DEFAULTS)
        cfg.update(data)
    except Exception:
        cfg = dict(_DEFAULTS)

    # Backfill bundled values for any keys the user's local config is missing
    # or has blanked out. This recovers users with a stale config.json from an
    # older build that shipped without an api_key / sheet_url.
    if bundled:
        changed = False
        for key in ("api_key", "sheet_url", "region", "routing"):
            if not cfg.get(key) and bundled.get(key):
                cfg[key] = bundled[key]
                changed = True
        if not cfg.get("creds_path"):
            cfg["creds_path"] = "credentials.json"
            changed = True
        if changed:
            save_config(cfg)
    return cfg

def save_config(cfg):
    path = _config_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        print(f"[config] save failed: {e}")

def _data_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def script_path(name):
    """Return absolute path to a data script by filename."""
    return os.path.join(_data_dir(), name)


# ---------------------------------------------------------------------------
# Rank snapshot — used by Rankings tab to compute movement (▲ / ▼) since last
# launch.  Lives in its own JSON beside config.json so a corrupt snapshot can't
# wipe the rest of the user's settings.
# ---------------------------------------------------------------------------
def _rank_snapshot_path():
    return os.path.join(_data_dir(), "rank_snapshot.json")


def load_rank_snapshot():
    """Return {player_name: rank_int} from the last saved snapshot, or {}."""
    path = _rank_snapshot_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {str(k): int(v) for k, v in data.items() if isinstance(v, (int, float))}
    except Exception:
        return {}


def save_rank_snapshot(snapshot):
    """Persist {player_name: rank_int} for the next launch."""
    path = _rank_snapshot_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({str(k): int(v) for k, v in snapshot.items()}, f, indent=2)
    except Exception as e:
        print(f"[rank_snapshot] save failed: {e}")
