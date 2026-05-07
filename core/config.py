"""Config I/O and Google Sheets helpers."""

import json
import os
import time
import random

CONFIG_FILE = "launcher_config.json"

DEFAULT_CONFIG = {
    "api_key": "",
    "sheet_url": "https://docs.google.com/spreadsheets/d/1jtScmcfol2YBi0FUSwkXVWkJ4qRBuP9EVIfWSWSDpms/edit",
    "creds_path": "credentials.json",
    "region": "na1",
    "routing": "americas",
    "players": [],
    "last_run": {},
}


def sheets_retry(fn, *args, max_attempts=6, **kwargs):
    """Call fn(*args, **kwargs) with exponential backoff on quota/server errors."""
    import gspread
    for attempt in range(max_attempts):
        try:
            return fn(*args, **kwargs)
        except gspread.exceptions.APIError as e:
            status = getattr(e.response, "status_code", None)
            if status in (429, 500, 503) and attempt < max_attempts - 1:
                time.sleep((2 ** attempt) + random.uniform(0, 1))
            else:
                raise


_sheet_read_cache = {}  # {(spreadsheet_id, ws_title): (timestamp, rows)}


def cached_get_all_values(ws, ttl=45):
    """Return ws.get_all_values() from a process-local cache (TTL = 45 s)."""
    key = (ws.spreadsheet.id, ws.title)
    entry = _sheet_read_cache.get(key)
    now = time.time()
    if entry and (now - entry[0]) < ttl:
        return entry[1]
    rows = sheets_retry(ws.get_all_values)
    _sheet_read_cache[key] = (now, rows)
    return rows


def invalidate_sheet_cache(ws):
    """Drop the cached copy for ws so the next read fetches fresh data."""
    _sheet_read_cache.pop((ws.spreadsheet.id, ws.title), None)


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                cfg = DEFAULT_CONFIG.copy()
                cfg.update(json.load(f))
                return cfg
        except Exception: pass
    return DEFAULT_CONFIG.copy()


def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


def load_players_from_sheet():
    """Load player names from the Google Sheet.

    Returns (names, riot_to_display) where names is a list of display names
    and riot_to_display maps lowercase Riot game-name → display name.
    Returns ([], {}) on failure.
    """
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        cfg = load_config()
        creds = Credentials.from_service_account_file(
            cfg["creds_path"],
            scopes=["https://www.googleapis.com/auth/spreadsheets",
                     "https://www.googleapis.com/auth/drive"])
        gc = gspread.authorize(creds)
        if "docs.google.com" in cfg["sheet_url"]:
            ss = gc.open_by_url(cfg["sheet_url"])
        else:
            ss = gc.open(cfg["sheet_url"])
        ws = ss.worksheet("Players")
        vals = cached_get_all_values(ws)
        names = []
        riot_to_display = {}
        for row in vals[2:]:
            if len(row) >= 2 and row[1].strip():
                display_name = row[1].strip()
                if display_name.lower() == "player name":
                    continue
                names.append(display_name)
                if len(row) >= 3 and row[2].strip():
                    riot_id = row[2].replace("\n", "").strip()
                    if "#" in riot_id:
                        game_name = riot_id.split("#", 1)[0].strip()
                    else:
                        game_name = riot_id
                    if game_name:
                        riot_to_display[game_name.lower()] = display_name
        return names, riot_to_display
    except Exception:
        return [], {}
