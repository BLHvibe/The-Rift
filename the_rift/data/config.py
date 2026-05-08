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
    "sheet_url": "",
    "creds_path":"credentials.json",
    "region":    "na1",
    "routing":   "americas",
    "players":   [],
    "last_run":  {},
}

def load_config():
    path = _config_path()
    if not os.path.exists(path):
        return dict(_DEFAULTS)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        cfg = dict(_DEFAULTS)
        cfg.update(data)
        return cfg
    except Exception:
        return dict(_DEFAULTS)

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
