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
    # Draft Tool Rewrite (Phase 5) — when False, mutes pygame.mixer cues
    # (pick lock, ban, your-turn, archetype stinger, pivot alert, draft end).
    "audio_enabled": True,
    # Upgrade initiative (Phase 0a) — global animation-intensity multiplier.
    # 0.0 = no ambient/persistent motion (calm, snappy); 1.0 = full. The
    # motion/effects layer reads this so each user can dial the app's feel.
    "anim_intensity": 1.0,
    # Phase 0d — optional bearer token for the REST data API (server/api.py).
    # Blank = open deployment; set it to match the server's RIFT_API_TOKEN
    # env var to require auth on writes.
    "api_token": "",
    # Display name shown on the synced draft lobby & in chat. Auto-populated
    # from the player's first connect; user-editable in Settings.
    "display_name": "",
    # Draft Tool Rewrite (Phase 1) — Synced multiplayer draft session config.
    # `url` is the Fly.io-hosted FastAPI websocket server (see ../../server/).
    # No room codes, no passwords — single global room. Pairing is automatic:
    # first BEGIN DRAFT click claims BLUE, second claims RED, others SPEC.
    # Sides swap freely in the lobby until both READY.
    "sync": {
        "url": "wss://the-rift-draft-sync.fly.dev",
    },
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

    # v3 migration — drop stale `sync` config left over from v2.x (ngrok URL,
    # room codes, slot assignments). The v3 protocol is a single global room
    # on Fly.io with auto-side-assignment, so any of those legacy fields
    # blocks the connection.
    sync_cfg = cfg.get("sync") or {}
    needs_sync_migration = False
    cur_url = (sync_cfg.get("url") or "").lower()
    if (("ngrok" in cur_url)
            or ("the-rift-draft.fly.dev" in cur_url and "-sync" not in cur_url)
            or not cur_url):
        sync_cfg["url"] = _DEFAULTS["sync"]["url"]
        needs_sync_migration = True
    for stale_key in ("last_room", "last_name", "last_slot"):
        if stale_key in sync_cfg:
            del sync_cfg[stale_key]
            needs_sync_migration = True
    if needs_sync_migration:
        cfg["sync"] = sync_cfg
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
