# -*- coding: utf-8 -*-
"""LoL Power Rankings — bundled distribution.

This is the merged single-file build of the launcher + analytics scripts
+ in-house tracker. Generated automatically by build.py — don't edit by hand.

Entry points (selected via --mode argument; default = launch GUI):
  (no args)            Launch the GUI launcher
  --mode=fetch_ranks   Run the rank/scout/draft analytics CLI
  --mode=inhouse       Run the in-house tracker CLI

When packaged as a one-file .exe via PyInstaller, the GUI invokes this
same .exe with --mode=... to run the analytics subprocesses.
"""

from collections import defaultdict
from datetime import datetime
from datetime import datetime, timedelta
from datetime import datetime, timezone
from google.oauth2.service_account import Credentials
from tkinter import ttk, scrolledtext
import argparse
import argparse, time, random, sys, os, re, subprocess, urllib3
import gspread
import io
import json
import math
import os
import queue
import random
import re
import requests
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser


# ─── Embedded credentials and API key ────────────────────────────────
# These are baked into the distribution build. DO NOT share this file
# publicly — it grants service-account access to the Google Sheet and
# contains a Riot API key.

import base64 as _b64

_EMBEDDED_CREDS_B64 = "ewogICJ0eXBlIjogInNlcnZpY2VfYWNjb3VudCIsCiAgInByb2plY3RfaWQiOiAidGllci1saXN0LTQ5NDMwNSIsCiAgInByaXZhdGVfa2V5X2lkIjogIjczOTdiNDY1NmYwZDU0ODljN2I3MDUxODBlMjAzZjk2MjZmYzU0MGEiLAogICJwcml2YXRlX2tleSI6ICItLS0tLUJFR0lOIFBSSVZBVEUgS0VZLS0tLS1cbk1JSUV2Z0lCQURBTkJna3Foa2lHOXcwQkFRRUZBQVNDQktnd2dnU2tBZ0VBQW9JQkFRRGphS3FtNUtxbzlQQi9cbnFWZThYaERsSHUxWnhta1dZcHMzUXpZQXBwREZrdVc4dWV0S1pjL1AvVFBBSURBT2RrOVJOVmhDMjVzb0FYQlFcblp6cW5MdXBmdFF2YzM2MWgvblpRRDdrYmo1NFNOdTZVMGxNQytkZjhyenRLMUNEUkdEejRKMzRLaXJISG4wQlpcbi96R1RCRk42NjFoWGtzdTk4bEE3eHhIVmVzcnRrYWtqd1cxNThGTHg4SGdOdHBseTJuU0RnaTBPQllHb3M1b0Zcbis4NGFOUjhxV3M3ZXAwZmozQWZmN0EySEM3dmFSUk9PRWNmSFZ5ZlQwc3F6Sy9qTFB4cDdWVGwyVVRJeHQ4Ty9cbmhHTWhzUHdnaFV1aVlDR0NnQWxjd1oxOHdodk5nM2sxWFltTHNFTk1NQWtQZEpOMHFrM1oxdXgySnlKVHNsUytcblFHamhGQVloQWdNQkFBRUNnZ0VBQnBMUWpLLzRvSmNwK2pWa2hadW8wZDFiRk9OWHgzcEtESHdsekE3WjN2Z3dcbktneUJibWtJZ09BMmEzNlNzbUdvU1NEcFlFOWdTZ3BXbXpXM1crZE8yNUxodzZkTWtxbFd5cTdWcXpsZUkwa21cbnR0Mjk0V0lPK2dKOURJZEZacE0vTkpqUnBpVGNYdU5ES29iUkFaNnRwTDgzcDhVUGNpVEJFeVZJa1BCSDBaRDhcbmM2TE1RUytSUTU5eHpDT1J0ZzNlQUlReFFxc3NDTVp1ajQ5cllqNDJJWUtRV25GdWVtdDZ3Njc0UmwvY2pEUnhcblIzaktYc3pQeXh4MEJVWWxQOENyWEI4VnAxZzkra1JQS1h3TDFVVThEcXZWRGxycWpoQjd6OUczUk9rMS8vWU1cbkozVk5udVFIZXV0ZVFtaFhTL0xHQ2taM3RzMGsxaGpBRWxIMWNiUWIwUUtCZ1FEOG8xUU9Ob2hYSmRaRHlHemNcbkdLVG5tR3c5V3JscHBuQmZFcU90bFJqbmhBZS9CRW9RWFRSNE50aENiRHdrWjdqdWE4YXVrOXYraUl6NlFxMjBcbjcwMk5hZFl0QktQMk5BV29SckRXOVk4R3N0dTFFSTlXMDdGcG1FcVI4M2NWWEZSVlVBT1V4dEFQQXQ4US84S1FcblN6UVlvYlgrNC9nMUUyMG9kR2t5SFU5Q2FRS0JnUURtYjJPZm5KNWUyT2FQWExmUXRIVHhkbUhzUzdjR1hxZGRcbk93a1V6RE5KT0pIQ2tSSmY1UkxtYzJMZitGMzZHOWxkY0tsZ0xlSFp1TW00anIyanlNUDhCT0ZKbjg0a0ZSU0hcbk9XQVd4dXRnYVM4bUM1WVdrdzN0dGNiWFNqWHg3MUJqM3FzRHV6L3hDcXNjNm1WbHlDckZXd1BBZE15ekZxTWlcbnpBbkRhczgrK1FLQmdDSUw0TWdKa1ZZdFF6TGZUOHhaaGQrd0t1WVowK0xwQ3p2RXgwb2RUYjNsalNXdzdrcEdcblJVdnVHRGJiWHorSXV1Tm1vdC9rRFVIQUpUK1V2TlFsYTg0aTlUb2I1ZnpJQmZzbmk2MXNhbG44d0o4bUhDc1hcblhGRmV0SzMyb1pXL1c1NGpxbGZpY3llU3UzME8rcWwzZVEzWXZTNGNpdGFjUjVtc0ZvRXFjZ1FCQW9HQkFMdDJcbit4RXFsUnlNVUdWcEJKRmhmWkhDd1Q4L0NaTEJCbDh1VytEemp2V09jK1pacHgwa2V3L0g1elJXRmY0WEVlcVdcbmNQU3gzdjhFK2ZhUENYQnBNQ2Vpd0xUb3NRZGhydVdqbzZ4ai83RGJZV1FPSVBnVWdreFVpWU16K0ZidVhmUWhcbmZmYjNLcm1wK0RMNTdhdTBBRGUySjRNMmdpRmYxUy9GMWx1SVZUbmhBb0dCQU91d3VDZkpMdjcvWkFwbm0yUzRcbnJVUnFoZ0czQkl0c3hkeG9HMnhaalovQlNLZGxENUtYWHQ1SGpxNkJPalBGKzBsa0NpWHRCcURha0NRSEtIWVJcbldETTF1QW5NNVh0WjFjQ0kxMXZ1MngvKzJscWJzU1FmeGsydnNvRnc4Mk1EM1JmT0F4UWszZjJzNmVvbm53ZzZcbnBERHhnbTNRUElDNjEweHN1K1Y1d2t5OVxuLS0tLS1FTkQgUFJJVkFURSBLRVktLS0tLVxuIiwKICAiY2xpZW50X2VtYWlsIjogInRoZXJpZnRAdGllci1saXN0LTQ5NDMwNS5pYW0uZ3NlcnZpY2VhY2NvdW50LmNvbSIsCiAgImNsaWVudF9pZCI6ICIxMDA5MjkwMzMzMjIxMzI0NDQwMzAiLAogICJhdXRoX3VyaSI6ICJodHRwczovL2FjY291bnRzLmdvb2dsZS5jb20vby9vYXV0aDIvYXV0aCIsCiAgInRva2VuX3VyaSI6ICJodHRwczovL29hdXRoMi5nb29nbGVhcGlzLmNvbS90b2tlbiIsCiAgImF1dGhfcHJvdmlkZXJfeDUwOV9jZXJ0X3VybCI6ICJodHRwczovL3d3dy5nb29nbGVhcGlzLmNvbS9vYXV0aDIvdjEvY2VydHMiLAogICJjbGllbnRfeDUwOV9jZXJ0X3VybCI6ICJodHRwczovL3d3dy5nb29nbGVhcGlzLmNvbS9yb2JvdC92MS9tZXRhZGF0YS94NTA5L3RoZXJpZnQlNDB0aWVyLWxpc3QtNDk0MzA1LmlhbS5nc2VydmljZWFjY291bnQuY29tIiwKICAidW5pdmVyc2VfZG9tYWluIjogImdvb2dsZWFwaXMuY29tIgp9Cg=="
_EMBEDDED_API_KEY = "RGAPI-0b3a766e-0bb4-4248-a479-578cff5d165b"


def _resolve_resource_dir():
    """Return a directory next to the .exe (frozen) or the script (source).

    PyInstaller sets sys.frozen=True and stores extracted bundle resources
    under sys._MEIPASS; user-writable files should sit next to the .exe.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _user_data_dir():
    r"""Per-user app data directory. Created if missing.

    Windows: %LOCALAPPDATA%\LoLPowerRankings\
    Other:   ~/.lolpowerrankings/
    """
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        d = os.path.join(base, "LoLPowerRankings")
    else:
        d = os.path.join(os.path.expanduser("~"), ".lolpowerrankings")
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        # Fall back to the .exe's directory if we can't write to user-data
        d = _resolve_resource_dir()
    return d


def _materialize_creds():
    """Ensure the embedded credentials JSON is on disk in a stable location.

    Returns the filesystem path. Writes the file if it's missing or the
    contents differ from the embedded version (so updates ship the latest
    creds). Re-callable at any time without churn.
    """
    target = os.path.join(_user_data_dir(), "credentials.json")
    creds_text = _b64.b64decode(_EMBEDDED_CREDS_B64).decode("utf-8")

    # Skip the write if the existing file is already correct
    try:
        if os.path.exists(target):
            with open(target, "r", encoding="utf-8") as f:
                if f.read() == creds_text:
                    return target
    except Exception:
        pass  # fall through to rewrite

    try:
        with open(target, "w", encoding="utf-8") as f:
            f.write(creds_text)
    except Exception:
        # Last-ditch fallback: write to a temp file in the .exe's directory
        # (covers weird permission setups where %LOCALAPPDATA% isn't writable).
        target = os.path.join(_resolve_resource_dir(), "credentials.json")
        with open(target, "w", encoding="utf-8") as f:
            f.write(creds_text)

    return target


# ─── Launcher (GUI) ─────────────────────────────────────────────────

"""Config I/O and Google Sheets helpers."""


CONFIG_FILE = os.path.join(_resolve_resource_dir(), "launcher_config.json")

DEFAULT_CONFIG = {
    "api_key": _EMBEDDED_API_KEY,
    "sheet_url": "https://docs.google.com/spreadsheets/d/1jtScmcfol2YBi0FUSwkXVWkJ4qRBuP9EVIfWSWSDpms/edit",
    "creds_path": _materialize_creds(),
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
                # Always override with current embedded values — stale temp
                # paths from previous runs would crash gspread otherwise.
                cfg["creds_path"] = _materialize_creds()
                if not cfg.get("api_key"):
                    cfg["api_key"] = _EMBEDDED_API_KEY
                return cfg
        except Exception: pass
    # Fresh-install path: also re-materialize in case the file got cleaned
    # between module-load and now.
    cfg = DEFAULT_CONFIG.copy()
    cfg["creds_path"] = _materialize_creds()
    return cfg


def save_config(cfg):
    # Don't persist creds_path; it's re-materialized on every load.
    cfg_to_save = {k: v for k, v in cfg.items() if k != "creds_path"}
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg_to_save, f, indent=2)


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


"""Visual constants — color palette, roles, animation timings."""

C = {
    # Surfaces (deeper, slightly bluer)
    "bg":       "#06090f",
    "panel":    "#0c1422",
    "panel_2":  "#101a2b",   # alternating row bg
    "card":     "#0a2230",
    "strip":    "#091324",   # table column-header strip
    "tile":     "#0d1a2a",   # overview stat tiles
    "input":    "#13192a",
    "hover":    "#16314f",
    "active":   "#0e3a5a",

    # Brand — refined gold (warmer highlights, deeper shadows)
    "gold":     "#c8a86a",
    "gold_lt":  "#f3e6c4",
    "gold_dk":  "#6e5424",
    "gold_br":  "#d4b06e",

    # `rule` is the warm brown-gold separator color used in place
    # of the cool grey border.
    "rule":     "#3a2d12",

    # Status / accents
    "blue":     "#5fa8c9",
    "blue_lt":  "#5fb89a",
    "blue_dk":  "#0e3a5a",
    "red":      "#c84b31",
    "red_dk":   "#5a1c12",
    "teal":     "#5fb89a",

    # Text
    "txt":      "#e6dec7",
    "txt2":     "#9a9078",
    "txt_dim":  "#564f3e",
    "txt_dk":   "#06090f",

    # Borders
    "border":   "#3a2d12",
    "brd_gold": "#463714",
    "brd_act":  "#c8a86a",

    "green":    "#0ACF83",
    "purple":   "#9B59B6",

    # Team sides
    "team_blue": "#0a223a",
    "team_red":  "#2a0a0a",
}

ROLES = ["Top", "Jungle", "Mid", "Bot", "Support"]

# Rankings animation timings (ms)
ANIM_ROW_REVEAL_MS = 45
ANIM_PODIUM_CENTER_MS = 60
ANIM_PODIUM_SIDES_OFFSET_MS = 360
ANIM_PODIUM_STAGGER_MS = 220


"""
LoL Power Rankings — Command Center
=====================================
Visual control panel with real-time output, integrated draft tool,
and League of Legends client-style UI.

REQUIREMENTS:
  pip install requests gspread google-auth
  (tkinter comes built-in with Python)

USAGE:
  python launcher.py
"""



# ── Version & Update Info ─────────────────────────────────────
# These get overwritten by build_merger.py when the .exe is packaged.
__version__ = "1.1.1"
GITHUB_REPO = "BLHvibe/The-Rift"



class JobRunner:
    def __init__(self, app):
        self._app = app
        self._jobs = {}  # name -> (thread, cancel_event)

    def submit(self, name, fn, on_done=None, on_error=None):
        cancel = threading.Event()
        def _run():
            try:
                fn(cancel)
            except Exception as e:
                if on_error:
                    self._app.after(0, on_error, e)
                else:
                    self._app._output_q.put((f"[{name}] ERROR: {e}\n",
                                             "red"))
            finally:
                if on_done:
                    self._app.after(0, on_done)
                self._jobs.pop(name, None)
        t = threading.Thread(target=_run, name=name, daemon=True)
        self._jobs[name] = (t, cancel)
        t.start()
        return cancel

    def shutdown(self, timeout=3):
        for _name, (_t, cancel) in list(self._jobs.items()):
            cancel.set()
        for _name, (t, _cancel) in list(self._jobs.items()):
            t.join(timeout=timeout)
        self._jobs.clear()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.config = load_config()
        self.proc = None
        self.title("LoL Power Rankings")
        self.geometry("1150x860")
        self.minsize(1000, 700)
        self.configure(bg=C["bg"])

        # API key var — created early so commands work without opening admin window
        self.api_var = tk.StringVar(value=self.config["api_key"])

        # Settings vars — mirror the live config so the settings panel stays in sync
        self.settings_sheet_var   = tk.StringVar(value=self.config.get("sheet_url", ""))
        self.settings_region_var  = tk.StringVar(value=self.config.get("region", "na1"))
        self.settings_routing_var = tk.StringVar(value=self.config.get("routing", "americas"))
        self.settings_creds_var   = tk.StringVar(value=self.config.get("creds_path", "credentials.json"))

        # Re-scout player picker — used by the Re-scout button in COMMANDS tab
        self.rescount_player_var = tk.StringVar()

        # Draft state
        self.team1_vars = [(tk.StringVar(), tk.StringVar(value=r)) for r in ROLES]
        self.team2_vars = [(tk.StringVar(), tk.StringVar(value=r)) for r in ROLES]
        self.player_list = self.config.get("players", [])
        # Map Riot game-name (lowercased, without #TAG) → display name from
        # the Players sheet. Populated by _load_players_bg.
        self.riot_to_display = {}

        # Console log buffer — collects messages before admin window is opened
        self._log_buffer = []
        self._log_buffer_max = 200

        # Thread-safe queue: background thread puts (line, tag) here;
        # _poll_output drains it on the main thread every 50 ms.
        self._output_q = queue.Queue()

        # Track which mode is currently running so we can update timestamps
        self._current_mode = None

        self.jobs = JobRunner(self)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.build_ui()

        self.jobs.submit("load_players", lambda c: self._load_players_bg())
        self.jobs.submit("load_draft", lambda c: self._load_initial_draft_bg())
        self.jobs.submit("load_rankings", lambda c: self._load_initial_rankings_bg())
        self.jobs.submit("load_inhouse", lambda c: self._load_initial_inhouse_bg())
        self.jobs.submit("check_updates", lambda c: self._check_for_updates_bg())

    def _load_players_bg(self):
        result = load_players_from_sheet()
        # Backwards-compat: older versions returned just a list of names
        if isinstance(result, tuple):
            names, riot_to_display = result
        else:
            names, riot_to_display = result, {}

        if names:
            self.player_list = names
            self.config["players"] = names
            save_config(self.config)
            self.riot_to_display = riot_to_display
            self.after(0, self._refresh_dropdowns)
            # If the in-house tab already rendered without filtering, re-render
            # now that the roster is known.
            self.after(0, self._maybe_rerender_inhouse_for_roster)
            self.after(0, self.log, "Loaded player roster from Google Sheet.\n", "green")

    def _maybe_rerender_inhouse_for_roster(self):
        """Called when the Players sheet finishes loading. If the in-house tab
        is already showing data, re-render so the new roster filters apply."""
        if getattr(self, "inhouse_data", None) and self.inhouse_data.get("leaderboard"):
            try:
                self._display_inhouse_results(self.inhouse_data)
            except Exception:
                pass

    def _load_initial_draft_bg(self):
        """On startup, check the Google Sheet for an existing draft and display it if found."""
        try:
            import gspread
            from google.oauth2.service_account import Credentials
            cfg = self.config
            creds = Credentials.from_service_account_file(
                cfg["creds_path"],
                scopes=["https://www.googleapis.com/auth/spreadsheets",
                         "https://www.googleapis.com/auth/drive"])
            gc = gspread.authorize(creds)
            if "docs.google.com" in cfg["sheet_url"]:
                ss = gc.open_by_url(cfg["sheet_url"])
            else:
                ss = gc.open(cfg["sheet_url"])

            try:
                ws = ss.worksheet("Draft Tool")
            except Exception:
                return  # No Draft Tool sheet — nothing to load, stay on placeholder

            draft_data = self._parse_draft_sheet(ws)

            has_rosters = bool(draft_data["team1_roster"] or draft_data["team2_roster"])
            has_analysis = bool(
                draft_data["bans_blue"] or draft_data["bans_red"]
                or draft_data["blue_comps"] or draft_data["red_comps"])

            if has_rosters:
                self.after(0, self._prefill_draft_selections, draft_data)

            if has_analysis:
                self.after(0, self._display_draft_results, draft_data)
                self.after(0, self.log,
                           "Loaded existing draft analysis from sheet.\n", "green")
            elif has_rosters:
                self.after(0, self.log,
                           "Loaded saved team selections from sheet.\n", "blue")
        except Exception:
            # Silent fail — startup load failures shouldn't disrupt the user
            pass

    def _prefill_draft_selections(self, draft_data):
        """Populate team dropdowns from rosters in the loaded draft data."""
        for roster, vars_list in [
            (draft_data["team1_roster"], self.team1_vars),
            (draft_data["team2_roster"], self.team2_vars),
        ]:
            role_to_player = {p["role"]: p["player"] for p in roster}
            for i, role in enumerate(ROLES):
                if role in role_to_player:
                    vars_list[i][0].set(role_to_player[role])
                    vars_list[i][1].set(role)

    def _load_initial_rankings_bg(self):
        """On startup, fetch and display the Final Rankings sheet."""
        try:
            import gspread
            from google.oauth2.service_account import Credentials
            cfg = self.config
            creds = Credentials.from_service_account_file(
                cfg["creds_path"],
                scopes=["https://www.googleapis.com/auth/spreadsheets",
                         "https://www.googleapis.com/auth/drive"])
            gc = gspread.authorize(creds)
            if "docs.google.com" in cfg["sheet_url"]:
                ss = gc.open_by_url(cfg["sheet_url"])
            else:
                ss = gc.open(cfg["sheet_url"])

            try:
                ws = ss.worksheet("Final Rankings")
            except Exception:
                self.after(0, self._show_rankings_empty,
                           "No 'Final Rankings' sheet found.\n"
                           "Run 'Update Ranks & Analytics' from the admin panel first.")
                return

            data = self._parse_rankings_sheet(ws)
            if not data["players"]:
                self.after(0, self._show_rankings_empty,
                           "Final Rankings sheet is empty.")
                return

            self.after(0, self._display_rankings, data)
            self.after(0, self.log,
                       f"Loaded power rankings ({len(data['players'])} players).\n",
                       "green")
        except Exception as e:
            self.after(0, self._show_rankings_empty,
                       f"Couldn't load rankings: {e}")

    def _parse_rankings_sheet(self, ws):
        """Parse Final Rankings sheet into a structured list."""
        values = cached_get_all_values(ws)
        out = {"title": "", "subtitle": "", "players": []}
        if not values:
            return out

        if values[0]:
            out["title"] = values[0][0] if values[0][0] else "FINAL POWER RANKINGS"
        if len(values) > 1 and values[1]:
            out["subtitle"] = values[1][0]

        # Headers at row 3 (index 2): Rank | Name | Avg Tier | Tier Score | LoL Rank | Rank Score | Final | Rating
        # Player rows start at index 3, stop at blank or non-numeric rank
        for row in values[3:]:
            if not row or len(row) < 8:
                continue
            r = [str(c).strip() for c in row[:8]]
            rank_str, name, avg_tier, tier_score, rank_score_raw, rank_score, final, rating = r

            # Stop at the end of the rankings table (blank rank, blank name,
            # or hitting the "Chris List" section)
            if not rank_str or not rank_str.replace(".", "").isdigit():
                break

            # Filter out empty placeholder rows: name == "Player Name"
            # and rating present but no real data
            if name == "Player Name" or not name:
                continue

            try:
                pos = int(float(rank_str))
            except (ValueError, TypeError):
                continue

            try:
                final_score = float(final) if final else 0.0
            except (ValueError, TypeError):
                final_score = 0.0

            # Skip rows with no real score (placeholder rows often have 10.0)
            if final_score <= 10.0 and rating == "F":
                # Heuristic: 10.0 is the placeholder default. Skip if the row
                # has no tier score or rank score either
                try:
                    has_signal = (float(tier_score) > 10.0 or
                                  (rank_score and float(rank_score) > 0))
                except (ValueError, TypeError):
                    has_signal = False
                if not has_signal:
                    continue

            out["players"].append({
                "rank": pos,
                "name": name,
                "avg_tier": avg_tier,
                "tier_score": tier_score,
                "rank_score_raw": rank_score_raw,
                "rank_score": rank_score,
                "final_score": final,
                "rating": rating or "?",
            })

        return out

    # ── Rankings tab build & display ───────────────────────────

    # Refined LoL-inspired rating colors (also used for badge gradients)
    _RATING_COLORS = {
        "S": "#C8463C",   # crimson
        "A": "#C89B3C",   # warm gold
        "B": "#A0884E",   # muted brass
        "C": "#5C8A5C",   # sage
        "D": "#5C7A9C",   # steel blue
        "F": "#6E6E6E",   # gray
    }
    _RATING_GLOW = {
        "S": "#FF6B5C",
        "A": "#FFC85C",
        "B": "#D0A878",
        "C": "#80B080",
        "D": "#80A0C0",
        "F": "#909090",
    }

    def build_rankings_tab(self):
        """Set up the scrollable Power Rankings tab."""
        canvas = tk.Canvas(self.tab_rankings, bg=C["bg"], highlightthickness=0)
        scrollbar = tk.Scrollbar(self.tab_rankings, orient="vertical",
                                 command=canvas.yview)
        self.rankings_frame = tk.Frame(canvas, bg=C["bg"])

        self.rankings_frame.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        wid = canvas.create_window((0, 0), window=self.rankings_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.bind("<Configure>",
            lambda e, w=wid: canvas.itemconfigure(w, width=e.width))

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        self._bind_canvas_scroll(canvas, self.tab_rankings)

        # Initial loading state
        self._show_rankings_loading()

    def _show_rankings_loading(self):
        for w in self.rankings_frame.winfo_children():
            w.destroy()
        outer = tk.Frame(self.rankings_frame, bg=C["bg"])
        outer.pack(fill="x", padx=8, pady=80)
        tk.Frame(outer, bg=C["gold"], height=1).pack(fill="x")
        tk.Frame(outer, bg=C["gold_dk"], height=1).pack(fill="x", pady=(2, 0))
        body = tk.Frame(outer, bg=C["panel"])
        body.pack(fill="x")
        tk.Label(body, text="POWER RANKINGS", bg=C["panel"], fg=C["gold_dk"],
                 font=("Segoe UI", 9, "bold")).pack(pady=(22, 4))
        tk.Label(body, text="LOADING", bg=C["panel"], fg=C["gold_lt"],
                 font=("Segoe UI", 22, "bold")).pack()
        tk.Label(body, text="Fetching the latest tier list...",
                 bg=C["panel"], fg=C["txt2"],
                 font=("Segoe UI", 9, "italic")).pack(pady=(6, 22))
        tk.Frame(outer, bg=C["gold_dk"], height=1).pack(fill="x")
        tk.Frame(outer, bg=C["gold"], height=1).pack(fill="x", pady=(2, 0))

    def _show_rankings_empty(self, msg):
        for w in self.rankings_frame.winfo_children():
            w.destroy()
        outer = tk.Frame(self.rankings_frame, bg=C["bg"])
        outer.pack(fill="x", padx=8, pady=80)
        card = tk.Frame(outer, bg=C["panel"], highlightthickness=1,
                        highlightbackground=C["gold_dk"])
        card.pack(fill="x")
        tk.Label(card, text="POWER RANKINGS", bg=C["panel"], fg=C["gold_dk"],
                 font=("Segoe UI", 9, "bold")).pack(pady=(22, 4))
        tk.Label(card, text="NO DATA AVAILABLE", bg=C["panel"], fg=C["gold_lt"],
                 font=("Segoe UI", 18, "bold")).pack()
        tk.Label(card, text=msg, bg=C["panel"], fg=C["txt2"],
                 font=("Segoe UI", 10), wraplength=600,
                 justify="center").pack(pady=(8, 22), padx=20)

    def _display_rankings(self, data):
        """Build the dramatic rankings view."""
        for w in self.rankings_frame.winfo_children():
            w.destroy()

        rf = self.rankings_frame
        players = data["players"]
        if not players:
            self._show_rankings_empty("No ranked players found.")
            return

        # ── Hero header ──
        self._build_rankings_hero(rf, data)

        # ── Podium for top 3 ──
        if len(players) >= 1:
            self._build_rankings_podium(rf, players[:3])

        # ── Section divider ──
        if len(players) > 3:
            self._build_rankings_divider(rf, "CHALLENGERS")
            # Build the rest of the table — staggered reveal for drama
            list_frame = tk.Frame(rf, bg=C["bg"])
            list_frame.pack(fill="x", padx=20, pady=(0, 24))
            self._reveal_rankings_rows(list_frame, players[3:], idx=0)
        else:
            tk.Frame(rf, bg=C["bg"], height=24).pack()

    def _build_rankings_hero(self, parent, data):
        """Cinematic hero: eyebrow subtitle above, large title, count line below."""
        outer = tk.Frame(parent, bg=C["bg"])
        outer.pack(fill="x", padx=22, pady=(20, 0))

        # Single 2px gold rule on top
        tk.Frame(outer, bg=C["gold"], height=2).pack(fill="x")

        body = tk.Frame(outer, bg=C["panel"],
                        highlightthickness=1, highlightbackground=C["rule"])
        body.pack(fill="x")

        # Eyebrow subtitle (above the main title)
        eyebrow = data["subtitle"].upper() if data["subtitle"] \
            else "COMMUNITY CONSENSUS"
        tk.Label(body, text=eyebrow, bg=C["panel"], fg=C["gold"],
                 font=("Segoe UI", 9, "bold")).pack(pady=(36, 0))

        # Big title — wider scale
        tk.Label(body, text=data["title"] or "FINAL POWER RANKINGS",
                 bg=C["panel"], fg=C["gold_lt"],
                 font=("Segoe UI", 32, "bold")).pack(pady=(10, 4))

        # Count line at the bottom
        tk.Label(body,
                 text=f"{len(data['players'])} CONTENDERS RANKED".upper(),
                 bg=C["panel"], fg=C["txt2"],
                 font=("Segoe UI", 9, "bold")).pack(pady=(0, 30))

        # Single gold-dk rule on bottom
        tk.Frame(outer, bg=C["gold_dk"], height=1).pack(fill="x")

    def _build_rankings_podium(self, parent, top3):
        """Top 3 podium — #1 center & raised, #2 left, #3 right."""
        wrap = tk.Frame(parent, bg=C["bg"])
        wrap.pack(fill="x", padx=20, pady=(8, 24))

        # 3-column grid; columns 0,1,2 hold ranks 2/1/3
        for col in range(3):
            wrap.columnconfigure(col, weight=1, uniform="podium")

        order = []
        if len(top3) >= 2:
            order.append((top3[1], 0, "small"))  # #2 → left
        if len(top3) >= 1:
            order.append((top3[0], 1, "large"))  # #1 → center, big
        if len(top3) >= 3:
            order.append((top3[2], 2, "small"))  # #3 → right

        # Schedule reveal-with-delay for each podium slot, center first
        # (visual effect: champion appears first, then their flanks)
        center = next((o for o in order if o[2] == "large"), None)
        sides = [o for o in order if o[2] != "large"]

        if center:
            self.after(60, lambda: self._build_podium_card(wrap, *center))
        for i, slot in enumerate(sides):
            self.after(360 + i * 220,
                       lambda s=slot: self._build_podium_card(wrap, *s))

    def _build_podium_card(self, parent, player, col, size):
        """Cinematic podium card. `size` = 'large' for #1, 'small' for 2/3.

        Replaces the glowing-ring pattern with a single 3px top accent stripe
        in the rating color and a thin rule-color frame on the other 3 sides.
        """
        rating = player["rating"]
        rating_color = self._RATING_COLORS.get(rating, C["gold"])
        is_first = (player["rank"] == 1)

        cell = tk.Frame(parent, bg=C["bg"])
        # Add top padding so 2nd/3rd appear lower than 1st
        top_pad = 0 if is_first else 36
        cell.grid(row=0, column=col, padx=10, pady=(top_pad, 0), sticky="ew")

        # Outer wrapper holds the top accent stripe + the body
        outer = tk.Frame(cell, bg=C["bg"])
        outer.pack(fill="x")

        # 3px top accent stripe in the rating color
        tk.Frame(outer, bg=rating_color, height=3).pack(fill="x")

        # Card body — rule-color frame on the other three sides
        card = tk.Frame(outer, bg=C["panel"],
                        highlightthickness=1,
                        highlightbackground=C["rule"])
        card.pack(fill="x")

        # ── Position label at top ──
        if is_first:
            label_text, label_color = "CHAMPION", rating_color
            pos_size = 88
            name_size = 26
            badge_size = 78
            badge_letter = 48
            score_size = 30
            top_pad_inner = 20
            bottom_pad = 28
        else:
            label_text = "RUNNER-UP" if player["rank"] == 2 else "THIRD"
            label_color = rating_color
            pos_size = 60
            name_size = 19
            badge_size = 56
            badge_letter = 32
            score_size = 22
            top_pad_inner = 14
            bottom_pad = 20

        tk.Label(card, text=label_text, bg=C["panel"], fg=label_color,
                 font=("Segoe UI", 9, "bold")).pack(pady=(top_pad_inner, 6))

        # "NO." + number side-by-side
        pos_row = tk.Frame(card, bg=C["panel"])
        pos_row.pack()
        tk.Label(pos_row, text="NO.", bg=C["panel"], fg=C["txt_dim"],
                 font=("Segoe UI", 18 if is_first else 14, "bold")).pack(
            side="left", padx=(0, 14), pady=(0, 0))
        tk.Label(pos_row, text=str(player["rank"]), bg=C["panel"],
                 fg=C["gold_lt"],
                 font=("Segoe UI", pos_size, "bold")).pack(side="left")

        # Player name — clickable for profile popup
        _pname = str(player["name"])
        name_lbl = tk.Label(card, text=_pname.upper(),
                             bg=C["panel"], fg=C["gold_lt"],
                             font=("Segoe UI", name_size, "bold"),
                             cursor="hand2")
        name_lbl.pack(pady=(6, 14))
        name_lbl.bind("<Button-1>",
                      lambda e, n=_pname: self._navigate_to_scout(n))

        # Rating badge — single border, no double frame
        badge = tk.Frame(card, bg=C["bg"], width=badge_size, height=badge_size,
                         highlightthickness=2,
                         highlightbackground=rating_color)
        badge.pack()
        badge.pack_propagate(False)
        tk.Label(badge, text=rating, bg=C["bg"], fg=rating_color,
                 font=("Segoe UI", badge_letter, "bold")).pack(expand=True)

        # Final score
        tk.Label(card, text="FINAL SCORE", bg=C["panel"], fg=C["gold_dk"],
                 font=("Segoe UI", 8, "bold")).pack(pady=(14, 0))
        tk.Label(card, text=str(player["final_score"]),
                 bg=C["panel"], fg=C["gold"],
                 font=("Segoe UI", score_size, "bold")).pack()

        # Score breakdown
        tk.Label(card,
                 text=f"TIER {player['tier_score']}  ·  RANK {player['rank_score']}",
                 bg=C["panel"], fg=C["txt2"],
                 font=("Segoe UI", 8, "bold")).pack(pady=(4, bottom_pad))

    def _build_rankings_divider(self, parent, title):
        """Cinematic divider: thin rule lines + caps title (no diamonds)."""
        wrap = tk.Frame(parent, bg=C["bg"])
        wrap.pack(fill="x", padx=28, pady=(20, 12))

        row = tk.Frame(wrap, bg=C["bg"])
        row.pack(fill="x")

        tk.Frame(row, bg=C["rule"], height=1).pack(
            side="left", fill="x", expand=True, pady=(8, 0))
        tk.Label(row, text=f"  {title}  ", bg=C["bg"], fg=C["gold"],
                 font=("Segoe UI", 11, "bold")).pack(side="left")
        tk.Frame(row, bg=C["rule"], height=1).pack(
            side="left", fill="x", expand=True, pady=(8, 0))

    def _reveal_rankings_rows(self, parent, remaining_players, idx):
        """Reveal table rows one at a time for a staggered animation effect."""
        if idx >= len(remaining_players):
            return
        player = remaining_players[idx]
        self._build_ranking_row(parent, player, idx)
        # Schedule the next row reveal — fast enough to feel snappy
        self.after(45, lambda: self._reveal_rankings_rows(
            parent, remaining_players, idx + 1))

    def _build_ranking_row(self, parent, player, idx):
        """Cinematic single row in the ranks-4-and-below table."""
        rating = player["rating"]
        rating_color = self._RATING_COLORS.get(rating, C["gold"])

        # Alternating row bg — uses panel_2 token for the off-rows
        row_bg = C["panel"] if idx % 2 == 0 else C["panel_2"]

        # Each row gets a thin rule-color bottom border via a 1px frame
        row_outer = tk.Frame(parent, bg=C["bg"])
        row_outer.pack(fill="x")

        row = tk.Frame(row_outer, bg=row_bg)
        row.pack(fill="x")

        # Left rating-colored stripe
        stripe = tk.Frame(row, bg=rating_color, width=4)
        stripe.pack(side="left", fill="y")
        stripe.pack_propagate(False)

        # NO.{rank} composite
        pos_box = tk.Frame(row, bg=row_bg, width=80)
        pos_box.pack(side="left", fill="y")
        pos_box.pack_propagate(False)
        tk.Label(pos_box, text=f"NO.{player['rank']}", bg=row_bg,
                 fg=C["txt2"],
                 font=("Segoe UI", 11, "bold")).pack(expand=True)

        # Rating badge
        badge_box = tk.Frame(row, bg=row_bg, width=64)
        badge_box.pack(side="left", fill="y")
        badge_box.pack_propagate(False)
        badge = tk.Frame(badge_box, bg=row_bg, width=38, height=38,
                         highlightthickness=2,
                         highlightbackground=rating_color)
        badge.pack(expand=True)
        badge.pack_propagate(False)
        tk.Label(badge, text=rating, bg=row_bg, fg=rating_color,
                 font=("Segoe UI", 17, "bold")).pack(expand=True)

        # Player name (large, takes flex space) — clickable for profile popup
        name_box = tk.Frame(row, bg=row_bg)
        name_box.pack(side="left", fill="both", expand=True, padx=(8, 0))
        _pname = str(player["name"])
        name_lbl = tk.Label(name_box, text=_pname.upper(),
                             bg=row_bg, fg=C["gold_lt"],
                             font=("Segoe UI", 14, "bold"),
                             anchor="w", cursor="hand2")
        name_lbl.pack(fill="x", pady=(14, 0))
        name_lbl.bind("<Button-1>",
                      lambda e, n=_pname: self._navigate_to_scout(n))
        tk.Label(name_box,
                 text=f"AVG TIER {player['avg_tier']}  ·  RANK {player['rank_score']}",
                 bg=row_bg, fg=C["txt2"],
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(3, 14))

        # Final score on the right
        score_box = tk.Frame(row, bg=row_bg, width=150)
        score_box.pack(side="right", fill="y")
        score_box.pack_propagate(False)
        tk.Label(score_box, text="SCORE", bg=row_bg, fg=C["gold_dk"],
                 font=("Segoe UI", 8, "bold")).pack(pady=(12, 0))
        tk.Label(score_box, text=str(player["final_score"]),
                 bg=row_bg, fg=C["gold"],
                 font=("Segoe UI", 22, "bold")).pack(pady=(0, 8))

        # Bottom rule-color separator
        tk.Frame(row_outer, bg=C["rule"], height=1).pack(fill="x")

    def _refresh_dropdowns(self):
        for menu in self.player_menus:
            menu["menu"].delete(0, "end")
            for name in self.player_list:
                # Need to capture the variable for each menu
                var = menu._var
                menu["menu"].add_command(label=name,
                    command=lambda v=var, n=name: v.set(n))

    # ── UI Construction ──────────────────────────────────────

    def build_ui(self):
        # Top bar — cinematic restyle (64px, vertical separator, teal status dot)
        top = tk.Frame(self, bg=C["panel"], height=64)
        top.pack(fill="x")
        top.pack_propagate(False)
        tk.Frame(top, bg=C["gold"], height=2).pack(fill="x", side="top")
        tf = tk.Frame(top, bg=C["panel"])
        tf.pack(fill="x", padx=22, pady=10)
        tk.Label(tf, text="POWER RANKINGS", bg=C["panel"], fg=C["gold"],
                font=("Segoe UI", 17, "bold")).pack(side="left")
        # Vertical separator
        sep = tk.Frame(tf, bg=C["gold_dk"], width=1, height=18)
        sep.pack(side="left", padx=14, pady=4)
        sep.pack_propagate(False)
        tk.Label(tf, text="COMMAND CENTER", bg=C["panel"], fg=C["txt2"],
                font=("Segoe UI", 11, "bold")).pack(side="left")

        # Version pill (right side). When an update is detected this becomes
        # a clickable "UPDATE AVAILABLE" badge.
        self.version_frame = tk.Frame(tf, bg=C["panel"])
        self.version_frame.pack(side="right", padx=(8, 0))
        self.version_label = tk.Label(self.version_frame,
                                       text=f"v{__version__}",
                                       bg=C["panel"], fg=C["txt_dim"],
                                       font=("Segoe UI", 8, "bold"))
        self.version_label.pack(side="right")

        # Status with teal indicator dot — "● READY"
        self.status = tk.StringVar(value="● READY")
        tk.Label(tf, textvariable=self.status, bg=C["panel"], fg=C["teal"],
                font=("Segoe UI", 10, "bold")).pack(side="right", padx=(0, 18))
        tk.Frame(self, bg=C["gold_dk"], height=1).pack(fill="x")

        # Notebook (tabs) — cinematic styling
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TNotebook", background=C["bg"], borderwidth=0)
        style.configure("TNotebook.Tab", background=C["bg"], foreground=C["txt2"],
                        font=("Segoe UI", 10, "bold"), padding=[22, 10],
                        borderwidth=0)
        style.map("TNotebook.Tab",
                  background=[("selected", C["card"])],
                  foreground=[("selected", C["gold"])])

        # Secondary bar — gear icon + JOIN CTA, right-stacked
        topbar = tk.Frame(self, bg=C["bg"])
        topbar.pack(fill="x")

        rstack = tk.Frame(topbar, bg=C["bg"])
        rstack.pack(side="right", padx=14, pady=4)

        admin_btn = tk.Button(rstack, text="⚙",
                              command=lambda: self.notebook.select(self.tab_cmd),
                              bg=C["bg"], fg=C["gold_dk"],
                              activebackground=C["panel"],
                              activeforeground=C["gold"],
                              font=("Segoe UI", 14), relief="flat", bd=0,
                              cursor="hand2", padx=8, pady=2)
        admin_btn.pack(anchor="e")

        # Subtle rule hairline between gear and JOIN
        tk.Frame(rstack, bg=C["rule"], height=1, width=180).pack(
            anchor="e", pady=(2, 4))

        join_btn = tk.Button(rstack, text="JOIN THE TIER LIST →",
                             command=self._open_join_dialog,
                             bg=C["blue_dk"], fg=C["gold_lt"],
                             activebackground=C["blue"],
                             activeforeground=C["gold_lt"],
                             font=("Segoe UI", 9, "bold"),
                             relief="flat", bd=0,
                             cursor="hand2", padx=18, pady=8,
                             highlightthickness=1,
                             highlightbackground=C["gold"])
        join_btn.pack(anchor="e")

        # Hover effect
        def _join_enter(_e): join_btn.configure(bg=C["blue"])
        def _join_leave(_e): join_btn.configure(bg=C["blue_dk"])
        join_btn.bind("<Enter>", _join_enter)
        join_btn.bind("<Leave>", _join_leave)

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True)
        self.notebook = nb

        # Tab 1: Power Rankings (DEFAULT VIEW)
        self.tab_rankings = tk.Frame(nb, bg=C["bg"])
        nb.add(self.tab_rankings, text="  POWER RANKINGS  ")
        self.build_rankings_tab()

        # Tab 2: Draft
        self.tab_draft = tk.Frame(nb, bg=C["bg"])
        nb.add(self.tab_draft, text="  DRAFT TOOL  ")
        self.build_draft_tab()

        # Tab 3: Scouting
        self.tab_scout = tk.Frame(nb, bg=C["bg"])
        nb.add(self.tab_scout, text="  SCOUTING  ")
        self.build_scouting_tab()

        # Tab 4: Build Your Tier List
        self.tab_rating = tk.Frame(nb, bg=C["bg"])
        nb.add(self.tab_rating, text="  BUILD YOUR TIER LIST  ")
        self.build_rating_tab()

        # Tab 5: In-House Games
        self.tab_inhouse = tk.Frame(nb, bg=C["bg"])
        nb.add(self.tab_inhouse, text="  IN-HOUSE GAMES  ")
        self.build_inhouse_tab()

        # Tab 6: Activity Feed
        self.tab_feed = tk.Frame(nb, bg=C["bg"])
        nb.add(self.tab_feed, text="  ACTIVITY  ")
        self.build_feed_tab()

        # Tab 7: Admin Commands (always in the notebook, console always live)
        self.tab_cmd = tk.Frame(nb, bg=C["bg"])
        nb.add(self.tab_cmd, text="  COMMANDS  ")
        self.console = None  # set by build_commands_tab below
        self.build_commands_tab(self.tab_cmd)

    # ── Activity Feed tab ────────────────────────────────────────────────

    _FEED_ICONS = {
        "UPDATE":    ("↑", "#3A7BD5"),
        "SCOUT":     ("◈", "#C9A227"),
        "SCOUT_NEW": ("✦", "#2ECC71"),
        "RESCOUTED": ("↺", "#E0A020"),
        "DRAFT":     ("⚔", "#5BC0EB"),
        "INHOUSE":   ("⚡", "#9B59B6"),
    }

    def build_feed_tab(self):
        outer = tk.Frame(self.tab_feed, bg=C["bg"])
        outer.pack(fill="both", expand=True)

        # Header bar
        hdr = tk.Frame(outer, bg=C["panel"], height=52)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="ACTIVITY FEED", bg=C["panel"], fg=C["gold"],
                 font=("Segoe UI", 13, "bold")).pack(side="left", padx=20, pady=14)
        self._btn(hdr, "↻  Refresh", self._feed_refresh, s="dim").pack(
            side="right", padx=16, pady=10)

        tk.Frame(outer, bg=C["rule"], height=1).pack(fill="x")

        # Scrollable events area
        self.feed_canvas = tk.Canvas(outer, bg=C["bg"], highlightthickness=0)
        feed_scroll = ttk.Scrollbar(outer, orient="vertical",
                                    command=self.feed_canvas.yview)
        self.feed_canvas.configure(yscrollcommand=feed_scroll.set)
        feed_scroll.pack(side="right", fill="y")
        self.feed_canvas.pack(side="left", fill="both", expand=True)

        self.feed_frame = tk.Frame(self.feed_canvas, bg=C["bg"])
        self.feed_canvas_window = self.feed_canvas.create_window(
            (0, 0), window=self.feed_frame, anchor="nw")

        self.feed_frame.bind("<Configure>",
            lambda e: self.feed_canvas.configure(
                scrollregion=self.feed_canvas.bbox("all")))
        self.feed_canvas.bind("<Configure>",
            lambda e: self.feed_canvas.itemconfig(
                self.feed_canvas_window, width=e.width))

        # Mousewheel scroll
        def _feed_scroll(e):
            self.feed_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        self.feed_canvas.bind("<MouseWheel>", _feed_scroll)
        self.feed_frame.bind("<MouseWheel>", _feed_scroll)

        # Placeholder while loading
        self._feed_placeholder = tk.Label(
            self.feed_frame,
            text="Loading activity log…",
            bg=C["bg"], fg=C["txt_dim"], font=("Segoe UI", 11, "italic"))
        self._feed_placeholder.pack(pady=40)

        # Load feed in background on startup
        self.jobs.submit("feed_load", lambda c: self._feed_load_bg())

    def _feed_load_bg(self):
        try:
            import gspread
            from google.oauth2.service_account import Credentials
            cfg = self.config
            creds = Credentials.from_service_account_file(
                cfg["creds_path"],
                scopes=["https://www.googleapis.com/auth/spreadsheets",
                        "https://www.googleapis.com/auth/drive.readonly"])
            gc = gspread.authorize(creds)
            sheet = cfg["sheet_url"]
            ss = gc.open_by_url(sheet) if "docs.google.com" in sheet else gc.open(sheet)
            try:
                ws = ss.worksheet("_Activity")
                rows = ws.get_all_values()
            except Exception:
                rows = []
            data_rows = [r for r in rows
                         if len(r) >= 4 and r[0] != "_ACTIVITY LOG" and r[0]]
            recent = data_rows[-100:]
            recent.reverse()
            events = [{"ts": r[0], "type": r[1], "player": r[2], "details": r[3]}
                      for r in recent]
            self.after(0, self._feed_render, events)
        except Exception as e:
            self.after(0, self._feed_render, None, str(e))

    def _feed_refresh(self):
        for w in self.feed_frame.winfo_children():
            w.destroy()
        self._feed_placeholder = tk.Label(
            self.feed_frame,
            text="Refreshing…",
            bg=C["bg"], fg=C["txt_dim"], font=("Segoe UI", 11, "italic"))
        self._feed_placeholder.pack(pady=40)
        self.jobs.submit("feed_refresh", lambda c: self._feed_load_bg())

    def _feed_render(self, events, error=None):
        for w in self.feed_frame.winfo_children():
            w.destroy()

        if error:
            tk.Label(self.feed_frame,
                     text=f"Could not load activity log:\n{error}",
                     bg=C["bg"], fg=C["red"],
                     font=("Segoe UI", 10), wraplength=600).pack(pady=40)
            return

        if not events:
            tk.Label(self.feed_frame,
                     text="No activity yet — run an update to start logging events.",
                     bg=C["bg"], fg=C["txt_dim"],
                     font=("Segoe UI", 11, "italic")).pack(pady=40)
            return

        from datetime import datetime as _dt, date as _date, timedelta as _td

        now = _dt.now()
        today = _date.today()
        yesterday = today - _td(days=1)

        def _date_label(ts_str):
            try:
                event_date = _dt.strptime(ts_str, "%Y-%m-%d %H:%M").date()
            except ValueError:
                return ts_str[:10]
            if event_date == today:
                return "Today"
            elif event_date == yesterday:
                return "Yesterday"
            else:
                return event_date.strftime("%b ") + str(event_date.day)

        current_date_group = None

        for i, ev in enumerate(events):
            group = _date_label(ev["ts"])
            if group != current_date_group:
                current_date_group = group
                sep = tk.Frame(self.feed_frame, bg=C["bg"])
                sep.pack(fill="x", pady=(8, 2))
                tk.Label(sep, text=group, bg=C["bg"], fg=C["txt_dim"],
                         font=("Segoe UI", 8, "bold")).pack(side="left", padx=10)
                tk.Frame(sep, bg=C["rule"], height=1).pack(
                    side="left", fill="x", expand=True, pady=4)

            icon_char, icon_color = self._FEED_ICONS.get(
                ev["type"], ("●", C["txt_dim"]))

            row_bg = C["panel"] if i % 2 == 0 else C["bg"]
            row = tk.Frame(self.feed_frame, bg=row_bg)
            row.pack(fill="x", padx=0, pady=0)

            # Icon column
            icon_col = tk.Frame(row, bg=row_bg, width=44)
            icon_col.pack(side="left", fill="y")
            icon_col.pack_propagate(False)
            tk.Label(icon_col, text=icon_char, bg=row_bg, fg=icon_color,
                     font=("Segoe UI", 16)).pack(padx=10, pady=10)

            # Text column
            txt_col = tk.Frame(row, bg=row_bg)
            txt_col.pack(side="left", fill="both", expand=True, pady=8)

            # Time-ago string
            try:
                ts = _dt.strptime(ev["ts"], "%Y-%m-%d %H:%M")
                delta = now - ts
                minutes = int(delta.total_seconds() // 60)
                if minutes < 2:
                    ago = "just now"
                elif minutes < 60:
                    ago = f"{minutes}m ago"
                elif minutes < 1440:
                    ago = f"{minutes // 60}h ago"
                else:
                    ago = f"{delta.days}d ago"
            except Exception:
                ago = ev["ts"]

            # Details line
            detail_text = ev["details"]
            if ev.get("player"):
                detail_text = ev["player"]

            tk.Label(txt_col, text=detail_text, bg=row_bg, fg=C["txt"],
                     font=("Segoe UI", 11, "bold"), anchor="w").pack(
                fill="x", padx=4)
            tk.Label(txt_col, text=ago, bg=row_bg, fg=C["txt_dim"],
                     font=("Segoe UI", 9), anchor="w").pack(
                fill="x", padx=4)

            # Thin separator
            tk.Frame(self.feed_frame, bg=C["rule"], height=1).pack(fill="x")

    def build_commands_tab(self, parent):
        """Build the admin Commands view inside `parent`. Used by the admin window."""
        wrap = tk.Frame(parent, bg=C["bg"])
        wrap.pack(fill="both", expand=True)

        # Left: buttons
        left = tk.Frame(wrap, bg=C["bg"], width=300)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        inner = tk.Frame(left, bg=C["bg"])
        inner.pack(fill="both", expand=True, padx=10, pady=8)

        # Settings
        self._section(inner, "SETTINGS")
        sf = tk.Frame(inner, bg=C["panel"], highlightthickness=1,
                     highlightbackground=C["border"])
        sf.pack(fill="x", pady=(0, 8))

        def _lbl(text):
            tk.Label(sf, text=text, bg=C["panel"], fg=C["txt2"],
                     font=("Segoe UI", 8)).pack(anchor="w", padx=8, pady=(6, 0))

        def _entry(var, show=None):
            e = tk.Entry(sf, textvariable=var, bg=C["input"], fg=C["txt"],
                         insertbackground=C["gold"], font=("Consolas", 9),
                         relief="flat", highlightthickness=1,
                         highlightbackground=C["border"],
                         highlightcolor=C["gold_dk"], show=show)
            e.pack(fill="x", padx=8, pady=(2, 0))
            return e

        def _dropdown(var, choices):
            om = tk.OptionMenu(sf, var, *choices)
            om.configure(bg=C["input"], fg=C["txt"], font=("Segoe UI", 9),
                         activebackground=C["strip"], activeforeground=C["gold_lt"],
                         relief="flat", bd=0, highlightthickness=1,
                         highlightbackground=C["border"], anchor="w", width=18)
            om["menu"].configure(bg=C["panel_2"], fg=C["txt"],
                                 activebackground=C["strip"],
                                 activeforeground=C["gold_lt"],
                                 font=("Segoe UI", 9))
            om.pack(fill="x", padx=8, pady=(2, 0))

        _lbl("Riot API Key")
        _entry(self.api_var, show="•")

        _lbl("Google Sheet URL or Name")
        _entry(self.settings_sheet_var)

        _lbl("Region")
        _dropdown(self.settings_region_var,
                  ["na1", "euw1", "eun1", "kr", "jp1",
                   "br1", "la1", "la2", "oc1", "tr1", "ru"])

        _lbl("Routing")
        _dropdown(self.settings_routing_var,
                  ["americas", "europe", "asia", "sea"])

        _lbl("Credentials File")
        creds_row = tk.Frame(sf, bg=C["panel"])
        creds_row.pack(fill="x", padx=8, pady=(2, 0))
        tk.Entry(creds_row, textvariable=self.settings_creds_var,
                 bg=C["input"], fg=C["txt"], insertbackground=C["gold"],
                 font=("Consolas", 9), relief="flat", highlightthickness=1,
                 highlightbackground=C["border"],
                 highlightcolor=C["gold_dk"]).pack(side="left", fill="x", expand=True)

        def _browse_creds():
            from tkinter import filedialog
            path = filedialog.askopenfilename(
                title="Select credentials.json",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
            if path:
                self.settings_creds_var.set(path)
        tk.Button(creds_row, text="Browse…", command=_browse_creds,
                  bg=C["strip"], fg=C["txt"], font=("Segoe UI", 8),
                  relief="flat", cursor="hand2", padx=6).pack(side="left", padx=(4, 0))

        btn_row = tk.Frame(sf, bg=C["panel"])
        btn_row.pack(fill="x", padx=8, pady=(10, 8))
        self._btn(btn_row, "Test Connection",
                  self._test_connection, w=16, s="dim").pack(side="left")
        self._btn(btn_row, "Save", self.save_cfg,
                  w=8, s="accent").pack(side="right")

        # Last-run timestamp labels — keyed by mode string
        self._last_run_labels = {}
        _last_run_cfg = self.config.get("last_run", {})

        def _make_ts_label(parent, mode_key):
            ts = _last_run_cfg.get(mode_key, "")
            lbl = tk.Label(parent, text=f"Last updated: {ts}" if ts else "",
                           bg=C["bg"], fg=C["txt_dim"], font=("Segoe UI", 8))
            lbl.pack(fill="x", padx=4)
            self._last_run_labels[mode_key] = lbl

        # Buttons
        self._section(inner, "RANK & ANALYTICS")
        self._btn(inner, "Update Ranks & Analytics",
                 lambda: self.run("update")).pack(fill="x", pady=2)
        _make_ts_label(inner, "update")
        self._btn(inner, "Update (Skip Matches)",
                 lambda: self.run("update_fast"), s="dim").pack(fill="x", pady=2)
        _make_ts_label(inner, "update_fast")

        self._section(inner, "SCOUTING REPORTS")
        self._btn(inner, "Full Scout + Ranks",
                 lambda: self.run("scout"), s="accent").pack(fill="x", pady=2)
        _make_ts_label(inner, "scout")
        self._btn(inner, "Scout Only",
                 lambda: self.run("scout_only")).pack(fill="x", pady=2)
        _make_ts_label(inner, "scout_only")
        self._btn(inner, "Scout New Players",
                 lambda: self.run("scout_new")).pack(fill="x", pady=2)
        _make_ts_label(inner, "scout_new")

        # Re-scout single player row
        rs_row = tk.Frame(inner, bg=C["bg"])
        rs_row.pack(fill="x", pady=(4, 2))
        rescount_menu = tk.OptionMenu(rs_row, self.rescount_player_var,
                                      *self.player_list if self.player_list else ["Loading..."])
        rescount_menu._var = self.rescount_player_var
        rescount_menu.configure(bg=C["input"], fg=C["txt"],
                                activebackground=C["hover"],
                                activeforeground=C["gold"],
                                font=("Segoe UI", 10), highlightthickness=0,
                                relief="flat", width=18, indicatoron=True)
        rescount_menu["menu"].configure(bg=C["input"], fg=C["txt"],
                                        activebackground=C["hover"],
                                        activeforeground=C["gold"],
                                        font=("Segoe UI", 10))
        rescount_menu.pack(side="left", padx=(0, 6))
        self.player_menus.append(rescount_menu)

        self._btn(rs_row, "Re-scout",
                  lambda: self._run_rescount_player(), s="dim").pack(side="left")
        _make_ts_label(inner, "scout_player")

        self._section(inner, "DRAFT TOOL")
        self._btn(inner, "Setup Draft Sheet",
                 lambda: self.run("setup_draft")).pack(fill="x", pady=2)
        _make_ts_label(inner, "setup_draft")

        self._section(inner, "IN-HOUSE")
        self._btn(inner, "Log Custom Games",
                 lambda: self.run("inhouse"), s="accent").pack(fill="x", pady=2)
        _make_ts_label(inner, "inhouse")

        tk.Frame(inner, bg=C["bg"], height=8).pack()
        self._btn(inner, "Stop Process", self.stop, s="danger").pack(fill="x", pady=2)

        # Separator
        tk.Frame(wrap, bg=C["gold_dk"], width=1).pack(side="left", fill="y")

        # Right: console
        right = tk.Frame(wrap, bg=C["bg"])
        right.pack(side="left", fill="both", expand=True)

        ch = tk.Frame(right, bg=C["panel"], height=32)
        ch.pack(fill="x")
        ch.pack_propagate(False)
        tk.Label(ch, text="OUTPUT", bg=C["panel"], fg=C["gold_dk"],
                font=("Segoe UI", 8, "bold")).pack(side="left", padx=10, pady=6)
        tk.Button(ch, text="Clear", command=self.clear_log, bg=C["panel"],
                 fg=C["txt_dim"], font=("Segoe UI", 7), relief="flat",
                 cursor="hand2").pack(side="right", padx=10)
        tk.Frame(right, bg=C["border"], height=1).pack(fill="x")

        self.console = scrolledtext.ScrolledText(
            right, bg=C["bg"], fg=C["txt"], insertbackground=C["gold"],
            font=("Consolas", 10), relief="flat", padx=14, pady=10,
            wrap="word", state="disabled")
        self.console.pack(fill="both", expand=True)
        for tag, color in [("gold", C["gold"]), ("blue", C["blue_lt"]),
                           ("green", C["green"]), ("red", C["red"]),
                           ("dim", C["txt_dim"]),
                           ("hdr", C["gold"])]:
            self.console.tag_configure(tag, foreground=color,
                font=("Consolas", 11, "bold") if tag == "hdr" else None)

        # Progress bar — shown below the console output area
        self.progress_bar = ttk.Progressbar(right, mode="indeterminate")
        self.progress_bar.pack(fill="x", side="bottom")

        # Mousewheel scroll
        def _on_scroll(e):
            self.console.yview_scroll(int(-1 * (e.delta / 120)), "units")
        self.console.bind("<MouseWheel>", _on_scroll)
        self.console.bind("<Button-4>",
                          lambda e: self.console.yview_scroll(-3, "units"))
        self.console.bind("<Button-5>",
                          lambda e: self.console.yview_scroll(3, "units"))

        # Flush any buffered log lines into the new console
        for text, tag in self._log_buffer:
            self.console.configure(state="normal")
            if tag:
                self.console.insert("end", text, tag)
            else:
                self.console.insert("end", text)
            self.console.configure(state="disabled")
        self._log_buffer = []
        self.console.see("end")

        # Banner (only show once, the first time admin window opens)
        if not getattr(self, "_admin_banner_shown", False):
            self.log("LoL Power Rankings — Command Center\n", "hdr")
            self.log("─" * 45 + "\n", "dim")
            self.log("Ready. Enter API key and select a command.\n\n", "blue")
            self._admin_banner_shown = True

    # ── Join The Tier List ────────────────────────────────────

    JOIN_MAX_PLAYERS = 25
    JOIN_PLACEHOLDER_NAME = "Player Name"
    JOIN_PLACEHOLDER_RIOT = "Riot ID"

    def _open_join_dialog(self):
        """Modal dialog for new players to join the tier list."""
        # Reuse if already open
        if getattr(self, "join_window", None) is not None:
            try:
                if self.join_window.winfo_exists():
                    self.join_window.lift()
                    self.join_window.focus_force()
                    return
            except Exception:
                pass

        win = tk.Toplevel(self)
        win.title("Join The Tier List")
        win.configure(bg=C["bg"])
        win.geometry("460x440")
        win.resizable(False, False)
        win.transient(self)
        win.grab_set()
        self.join_window = win

        def _on_close():
            self.join_window = None
            win.destroy()
        win.protocol("WM_DELETE_WINDOW", _on_close)

        # ── Header (gold double rule treatment) ──
        tk.Frame(win, bg=C["gold"], height=1).pack(fill="x")
        tk.Frame(win, bg=C["gold_dk"], height=1).pack(fill="x", pady=(2, 0))

        hdr = tk.Frame(win, bg=C["panel"])
        hdr.pack(fill="x")
        tk.Label(hdr, text="◆  JOIN THE TIER LIST  ◆", bg=C["panel"],
                 fg=C["gold_lt"],
                 font=("Segoe UI", 14, "bold")).pack(pady=14)

        tk.Frame(win, bg=C["gold_dk"], height=1).pack(fill="x")
        tk.Frame(win, bg=C["gold"], height=1).pack(fill="x", pady=(2, 0))

        # ── Body ──
        body = tk.Frame(win, bg=C["bg"])
        body.pack(fill="both", expand=True, padx=24, pady=18)

        # Name field
        tk.Label(body, text="NAME", bg=C["bg"], fg=C["gold_dk"],
                 font=("Segoe UI", 9, "bold")).pack(anchor="w")
        self.join_name_var = tk.StringVar()
        name_entry = tk.Entry(body, textvariable=self.join_name_var,
                              bg=C["input"], fg=C["txt"],
                              insertbackground=C["gold"],
                              font=("Segoe UI", 11), relief="flat",
                              highlightthickness=1,
                              highlightbackground=C["border"],
                              highlightcolor=C["gold_dk"])
        name_entry.pack(fill="x", pady=(4, 14), ipady=4)

        # Riot ID field
        tk.Label(body, text="RIOT ID", bg=C["bg"], fg=C["gold_dk"],
                 font=("Segoe UI", 9, "bold")).pack(anchor="w")
        self.join_riot_var = tk.StringVar()
        riot_entry = tk.Entry(body, textvariable=self.join_riot_var,
                              bg=C["input"], fg=C["txt"],
                              insertbackground=C["gold"],
                              font=("Segoe UI", 11), relief="flat",
                              highlightthickness=1,
                              highlightbackground=C["border"],
                              highlightcolor=C["gold_dk"])
        riot_entry.pack(fill="x", pady=(4, 4), ipady=4)
        tk.Label(body, text="Format: GameName#TAG  (e.g. SomeChips#BBQ)",
                 bg=C["bg"], fg=C["txt_dim"],
                 font=("Segoe UI", 8, "italic")).pack(anchor="w", pady=(0, 14))

        # Status / error message slot
        self.join_status_var = tk.StringVar(value="")
        self.join_status = tk.Label(body, textvariable=self.join_status_var,
                                    bg=C["bg"], fg=C["red"],
                                    font=("Segoe UI", 9),
                                    wraplength=400, justify="left")
        self.join_status.pack(anchor="w", pady=(0, 8))

        # Buttons
        btns = tk.Frame(body, bg=C["bg"])
        btns.pack(fill="x", pady=(8, 0))
        self._btn(btns, "CANCEL", _on_close, w=10, s="dim").pack(side="right",
                                                                  padx=(8, 0))
        self.join_submit_btn = self._btn(btns, "JOIN",
                                          self._submit_join_dialog,
                                          w=10, s="accent")
        self.join_submit_btn.pack(side="right")

        # Submit on Enter from either field
        name_entry.bind("<Return>", lambda _e: self._submit_join_dialog())
        riot_entry.bind("<Return>", lambda _e: self._submit_join_dialog())

        name_entry.focus_set()

    def _join_set_status(self, text, color=None):
        """Update the status line in the join dialog."""
        if color is None:
            color = C["red"]
        if not getattr(self, "join_status", None):
            return
        try:
            self.join_status.configure(fg=color)
            self.join_status_var.set(text)
        except Exception:
            pass

    def _submit_join_dialog(self):
        """Validate the form and kick off the background writer."""
        name = self.join_name_var.get().strip().replace("\n", " ")
        riot = self.join_riot_var.get().strip().replace("\n", "")

        # Local validation — fail fast before hitting the network
        if not name:
            self._join_set_status("Please enter a name.")
            return
        if not riot:
            self._join_set_status("Please enter a Riot ID.")
            return
        if len(name) > 50:
            self._join_set_status("Name is too long (max 50 characters).")
            return
        if len(riot) > 60:
            self._join_set_status("Riot ID is too long (max 60 characters).")
            return
        if name.lower() == self.JOIN_PLACEHOLDER_NAME.lower():
            self._join_set_status("Please enter a real name.")
            return
        if riot.lower() == self.JOIN_PLACEHOLDER_RIOT.lower():
            self._join_set_status("Please enter a real Riot ID.")
            return
        # Riot ID must be of the form GameName#TAG
        if "#" not in riot or riot.startswith("#") or riot.endswith("#"):
            self._join_set_status(
                "Riot ID must be in the format GameName#TAG.")
            return

        # Lock the dialog while we work
        try:
            self.join_submit_btn.configure(state="disabled")
        except Exception:
            pass
        self._join_set_status("Adding you to the roster...", C["blue_lt"])

        self.jobs.submit("join_tier_list",
                         lambda c, n=name, r=riot: self._join_tier_list_bg(n, r))

    def _join_tier_list_bg(self, name, riot_id):
        """Write a new player into the Players sheet, with full validation."""
        try:
            import gspread
            from google.oauth2.service_account import Credentials
            cfg = self.config
            creds = Credentials.from_service_account_file(
                cfg["creds_path"],
                scopes=["https://www.googleapis.com/auth/spreadsheets",
                         "https://www.googleapis.com/auth/drive"])
            gc = gspread.authorize(creds)
            if "docs.google.com" in cfg["sheet_url"]:
                ss = gc.open_by_url(cfg["sheet_url"])
            else:
                ss = gc.open(cfg["sheet_url"])

            try:
                ws = ss.worksheet("Players")
            except Exception:
                self.after(0, self._join_finish_error,
                           "Couldn't find the 'Players' sheet.")
                return

            values = cached_get_all_values(ws)

            # Build sets of existing names and riot IDs for duplicate checking
            # (rows 1+ skip the title and header rows; data starts at index 2)
            existing_names = set()
            existing_riots = set()
            real_entry_count = 0
            first_empty_row = None  # 1-indexed sheet row number

            for i, row in enumerate(values[2:], start=3):  # i = sheet row number
                cells = row + [""] * (3 - len(row))
                _slot, ex_name, ex_riot = cells[0], cells[1].strip(), cells[2].strip()

                is_placeholder = (
                    not ex_name
                    or ex_name == self.JOIN_PLACEHOLDER_NAME
                    or (not ex_riot and ex_name == self.JOIN_PLACEHOLDER_NAME)
                )

                if is_placeholder:
                    if first_empty_row is None:
                        first_empty_row = i
                    continue

                # Real entry — count it, collect for dup check
                real_entry_count += 1
                # Normalize Riot IDs: strip embedded newlines (some
                # historical entries have them, e.g. "name\n#tag")
                clean_riot = ex_riot.replace("\n", "").strip()
                existing_names.add(ex_name.lower())
                existing_riots.add(clean_riot.lower())

            # Cap check — if we already have 25 real entries, refuse
            if real_entry_count >= self.JOIN_MAX_PLAYERS:
                self.after(0, self._join_finish_error,
                           f"Roster is full ({self.JOIN_MAX_PLAYERS} players "
                           f"maximum). Talk to the admin.")
                return

            # Duplicate checks (case-insensitive)
            if name.lower() in existing_names:
                self.after(0, self._join_finish_error,
                           f"The name \"{name}\" is already on the roster.")
                return
            if riot_id.lower() in existing_riots:
                self.after(0, self._join_finish_error,
                           f"The Riot ID \"{riot_id}\" is already on the roster.")
                return

            # No empty slot found in existing rows — append a new row at
            # position real_entry_count+3 (sheet row number)
            if first_empty_row is None:
                target_row = real_entry_count + 3  # row 3 is slot 1
                slot_num = real_entry_count + 1
                # Write the slot number too since this is a new row
                sheets_retry(ws.update, values=[[slot_num, name, riot_id]],
                             range_name=f"A{target_row}:C{target_row}")
            else:
                # Reuse existing placeholder row — preserve column A
                sheets_retry(ws.update, values=[[name, riot_id]],
                             range_name=f"B{first_empty_row}:C{first_empty_row}")
            invalidate_sheet_cache(ws)

            self.after(0, self._join_finish_success, name)

        except Exception as e:
            self.after(0, self._join_finish_error, f"Error: {e}")

    def _join_finish_error(self, msg):
        """Re-enable the submit button and show the error."""
        self._join_set_status(msg, C["red"])
        try:
            self.join_submit_btn.configure(state="normal")
        except Exception:
            pass

    def _join_finish_success(self, name):
        """Show success state, refresh local roster, auto-close dialog."""
        # Update local roster so dropdowns get the new name immediately
        if name not in self.player_list:
            self.player_list.append(name)
            self.config["players"] = list(self.player_list)
            try:
                save_config(self.config)
            except Exception:
                pass
            self._refresh_dropdowns()

        self._join_set_status(f"Welcome, {name}!  You're on the roster.",
                              C["green"])
        self.log(f"Added {name} to the tier list.\n", "green")

        # Briefly show the success message, then close
        if getattr(self, "join_window", None) is not None:
            try:
                self.after(1500, self._close_join_dialog)
            except Exception:
                pass

    def _close_join_dialog(self):
        if getattr(self, "join_window", None) is not None:
            try:
                if self.join_window.winfo_exists():
                    self.join_window.destroy()
            except Exception:
                pass
            self.join_window = None

    def build_draft_tab(self):
        # Scrollable canvas for draft content
        canvas = tk.Canvas(self.tab_draft, bg=C["bg"], highlightthickness=0)
        scrollbar = tk.Scrollbar(self.tab_draft, orient="vertical", command=canvas.yview)
        self.draft_frame = tk.Frame(canvas, bg=C["bg"])

        self.draft_frame.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        window_id = canvas.create_window((0, 0), window=self.draft_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        # Make inner frame width match canvas width so content fills horizontally
        canvas.bind("<Configure>",
            lambda e, wid=window_id: canvas.itemconfigure(wid, width=e.width))

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        self._bind_canvas_scroll(canvas, self.tab_draft)

        df = self.draft_frame

        # Title
        self._tab_title(df, "DRAFT", "IN-HOUSE 5v5")

        # Teams side by side
        teams_wrap = tk.Frame(df, bg=C["bg"])
        teams_wrap.pack(fill="x", padx=16, pady=12)

        self.player_menus = []

        for col, label, color, team_vars in [
            (0, "TEAM 1 (BLUE SIDE)", C["team_blue"], self.team1_vars),
            (1, "TEAM 2 (RED SIDE)", C["team_red"], self.team2_vars),
        ]:
            frame = tk.Frame(teams_wrap, bg=C["bg"])
            frame.pack(side="left", fill="both", expand=True, padx=(0 if col == 0 else 8, 8 if col == 0 else 0))

            # Team header
            th = tk.Frame(frame, bg=color)
            th.pack(fill="x")
            tk.Label(th, text=label, bg=color, fg=C["gold"],
                    font=("Segoe UI", 12, "bold")).pack(pady=6)

            # Player slots
            for i, (pvar, rvar) in enumerate(team_vars):
                slot = tk.Frame(frame, bg=C["panel"] if i % 2 == 0 else C["input"],
                              highlightthickness=1, highlightbackground=C["border"])
                slot.pack(fill="x", pady=1)

                # Role label
                tk.Label(slot, text=ROLES[i], bg=slot["bg"], fg=C["gold"],
                        font=("Segoe UI", 10, "bold"), width=8).pack(side="left", padx=8, pady=6)

                # Player dropdown
                pvar.set("")
                menu = tk.OptionMenu(slot, pvar, *self.player_list if self.player_list else ["Loading..."])
                menu._var = pvar
                menu.configure(bg=C["input"], fg=C["txt"], activebackground=C["hover"],
                             activeforeground=C["gold"], font=("Segoe UI", 10),
                             highlightthickness=0, relief="flat", width=16,
                             indicatoron=True)
                menu["menu"].configure(bg=C["input"], fg=C["txt"],
                                      activebackground=C["hover"],
                                      activeforeground=C["gold"],
                                      font=("Segoe UI", 10))
                menu.pack(side="left", padx=4, pady=4)
                self.player_menus.append(menu)

        # Run Draft button
        btn_frame = tk.Frame(df, bg=C["bg"])
        btn_frame.pack(fill="x", padx=16, pady=8)
        self._btn(btn_frame, "RUN DRAFT ANALYSIS", self.run_draft_ui,
                 w=30, s="accent").pack(pady=4)
        self._btn(btn_frame, "Refresh Players", self._reload_players,
                 w=20, s="dim").pack(pady=2)

        tk.Frame(df, bg=C["gold_dk"], height=1).pack(fill="x", padx=16, pady=8)

        # Results area
        self.draft_results = tk.Frame(df, bg=C["bg"])
        self.draft_results.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        # Placeholder
        tk.Label(self.draft_results, text="Select players and roles, then click RUN DRAFT ANALYSIS",
                bg=C["bg"], fg=C["txt_dim"], font=("Segoe UI", 11)).pack(pady=30)

    def _reload_players(self):
        self.log("Refreshing player list...\n", "blue")
        self.jobs.submit("load_players", lambda c: self._load_players_bg())

    def run_draft_ui(self):
        """Run draft computation and display results in the UI."""
        team1 = [(pv.get(), rv.get()) for pv, rv in self.team1_vars if pv.get()]
        team2 = [(pv.get(), rv.get()) for pv, rv in self.team2_vars if pv.get()]

        if len(team1) < 3 or len(team2) < 3:
            self._show_draft_error("Select at least 3 players per team.")
            return

        self._clear_draft_results()
        tk.Label(self.draft_results, text="Computing draft analysis...",
                bg=C["bg"], fg=C["blue_lt"], font=("Segoe UI", 12)).pack(pady=20)

        self.jobs.submit("run_draft",
                         lambda c, t1=team1, t2=team2: self._run_draft_bg(t1, t2))

    def _run_draft_bg(self, team1, team2):
        """Write team selections to sheet, run --draft, then parse and display results."""
        ss = None
        try:
            import gspread
            from google.oauth2.service_account import Credentials

            cfg = self.config
            creds = Credentials.from_service_account_file(
                cfg["creds_path"],
                scopes=["https://www.googleapis.com/auth/spreadsheets",
                         "https://www.googleapis.com/auth/drive"])
            gc = gspread.authorize(creds)
            if "docs.google.com" in cfg["sheet_url"]:
                ss = gc.open_by_url(cfg["sheet_url"])
            else:
                ss = gc.open(cfg["sheet_url"])

            # Write team selections to Draft Tool sheet
            try:
                ws = ss.worksheet("Draft Tool")
            except Exception:
                self.after(0, self._show_draft_error,
                          "Draft Tool sheet not found. Run 'Setup Draft Sheet' first.")
                return

            # Write to rows 6-10 (team rosters)
            for i in range(5):
                row = i + 6
                p1 = team1[i][0] if i < len(team1) else ""
                r1 = team1[i][1] if i < len(team1) else ""
                p2 = team2[i][0] if i < len(team2) else ""
                r2 = team2[i][1] if i < len(team2) else ""
                sheets_retry(ws.update, values=[[i+1, p1, r1]], range_name=f"A{row}:C{row}")
                sheets_retry(ws.update, values=[[i+1, p2, r2]], range_name=f"H{row}:J{row}")
            invalidate_sheet_cache(ws)

            self.after(0, self.log, "Team selections written to sheet.\n", "green")

        except Exception as e:
            self.after(0, self._show_draft_error, f"Error writing teams: {e}")
            return

        # Now run --draft command
        key = self.api_var.get().strip()
        if not key:
            self.after(0, self._show_draft_error, "Enter your Riot API key first.")
            return

        cmd = self._build_cmd("draft")
        self.after(0, self.log, "\nRunning draft analysis...\n", "blue")
        self.after(0, self._show_draft_loading, "Crunching the numbers...")

        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, bufsize=1, cwd=self._script_dir(),
                                   env={**os.environ, "PYTHONUNBUFFERED": "1"})

            output_lines = []
            for line in iter(proc.stdout.readline, ""):
                output_lines.append(line)
                self.after(0, self.log, line)

            try:
                proc.wait(timeout=60)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

            if proc.returncode != 0:
                self.after(0, self._show_draft_error,
                          f"Draft failed (exit code {proc.returncode}). Check console output.")
                return

            self.after(0, self.log, "\nDraft analysis complete. Loading results...\n", "green")

            # Re-fetch sheet (the script deletes and recreates it)
            try:
                ws = ss.worksheet("Draft Tool")
                draft_data = self._parse_draft_sheet(ws)
            except Exception as e:
                self.after(0, self._show_draft_error,
                          f"Couldn't read draft results from sheet: {e}")
                return

            # Compute match prediction inline (we already have ss)
            team1_names = [p for p, _r in team1]
            team2_names = [p for p, _r in team2]
            prediction = self._compute_prediction_data(ss, team1_names, team2_names)

            self.after(0, self._display_draft_results, draft_data, prediction)

        except Exception as e:
            self.after(0, self._show_draft_error, f"Error: {e}")

    def _compute_prediction_data(self, ss, team1_names, team2_names):
        """Compute win probability data from rank history + in-house stats."""
        rank_vals = {}
        try:
            rh_ws = ss.worksheet("Rank History")
            rh_rows = rh_ws.get_all_values()
            if len(rh_rows) >= 3:
                header = rh_rows[1]
                last_row = rh_rows[-1]
                for ci, col_name in enumerate(header[1:], start=1):
                    if ci < len(last_row) and last_row[ci]:
                        try:
                            rank_vals[col_name.strip()] = float(last_row[ci])
                        except ValueError:
                            pass
        except Exception:
            pass

        inhouse_stats = {}
        try:
            ih_ws = ss.worksheet("In-House Stats")
            ih_rows = ih_ws.get_all_values()
            for row in ih_rows:
                if len(row) >= 6 and row[1].strip() and row[2].strip().isdigit():
                    name = row[1].strip()
                    games = int(row[2])
                    wins = int(row[3]) if row[3].strip().isdigit() else 0
                    if games > 0:
                        inhouse_stats[name] = {"games": games, "wr": wins / games}
        except Exception:
            pass

        def player_strength(name):
            rv = rank_vals.get(name, 13.0)
            rank_norm = rv / 31.0
            ih = inhouse_stats.get(name)
            if ih and ih["games"] >= 1:
                confidence = min(ih["games"] / 10.0, 1.0)
                wr_norm = ih["wr"] * confidence + 0.5 * (1 - confidence)
            else:
                wr_norm = 0.5
            return 0.65 * rank_norm + 0.35 * wr_norm

        all_names = set(team1_names) | set(team2_names)
        strengths = {n: player_strength(n) for n in all_names}
        t1_strength = sum(strengths[n] for n in team1_names) / max(len(team1_names), 1)
        t2_strength = sum(strengths[n] for n in team2_names) / max(len(team2_names), 1)
        total = t1_strength + t2_strength
        t1_prob = round(t1_strength / total * 100, 1) if total else 50.0
        t2_prob = round(100 - t1_prob, 1)
        return {
            "team1": team1_names, "team2": team2_names,
            "t1_prob": t1_prob, "t2_prob": t2_prob,
            "strengths": strengths, "rank_vals": rank_vals,
            "inhouse_stats": inhouse_stats,
        }

    # ── Sheet Parser ──────────────────────────────────────────

    def _parse_draft_sheet(self, ws):
        """Read the 'Draft Tool' sheet and return structured draft results."""
        values = cached_get_all_values(ws)

        team1_roster, team2_roster = [], []
        bans_blue, bans_red = [], []
        blue_comps, red_comps = [], []

        # ── Rosters: rows after the header row "TEAM 1 (BLUE SIDE)" ──
        for i, row in enumerate(values):
            if not row:
                continue
            if "TEAM 1" in row[0] and "BLUE" in row[0]:
                # Header row at i, column-header row at i+1, rosters at i+2..i+6
                for j in range(i + 2, min(i + 7, len(values))):
                    r = values[j] + [""] * (14 - len(values[j]))
                    if r[1].strip():
                        team1_roster.append({
                            "role": r[0].strip(), "player": r[1].strip(),
                            "rank": r[2].strip(), "top_champ": r[3].strip(),
                        })
                    if r[8].strip():
                        team2_roster.append({
                            "role": r[7].strip(), "player": r[8].strip(),
                            "rank": r[9].strip(), "top_champ": r[10].strip(),
                        })
                break

        # ── Bans: rows after "RECOMMENDED BANS" header ──
        for i, row in enumerate(values):
            if not row:
                continue
            if "RECOMMENDED BANS" in row[0]:
                # Header row at i, column-header row at i+1, ban data at i+2..i+6
                for j in range(i + 2, min(i + 7, len(values))):
                    r = values[j] + [""] * (14 - len(values[j]))
                    if r[1] and r[1] != "-":
                        bans_blue.append({
                            "phase": r[0], "champion": r[1], "target": r[2],
                            "wr": r[3], "games": r[4], "priority": r[5],
                        })
                    if r[8] and r[8] != "-":
                        bans_red.append({
                            "phase": r[7], "champion": r[8], "target": r[9],
                            "wr": r[10], "games": r[11], "priority": r[12],
                        })
                break

        # ── Comp suggestions ──
        # Walk through rows tracking which team's comps we're in and current comp
        current_team = None  # "blue" or "red"
        current_comp = None

        for row in values:
            if not row:
                continue
            r = row + [""] * (14 - len(row))
            first = r[0].strip()
            eighth = r[7].strip()

            if "TEAM 1 COMP SUGGESTIONS" in first:
                current_team = "blue"
                current_comp = None
                continue
            if "TEAM 2 COMP SUGGESTIONS" in first:
                current_team = "red"
                current_comp = None
                continue

            if current_team is None:
                continue

            # Archetype header: "ARCHETYPE — desc" in col A, "VIABILITY | ..." in col H
            is_arch_header = (
                "—" in first
                and ("Synergy" in eighth or any(v in eighth for v in
                     ["STRONG", "VIABLE", "WEAK", "NOT RECOMMENDED"]))
            )
            if is_arch_header:
                parts = first.split("—", 1)
                archetype = parts[0].strip()
                description = parts[1].strip() if len(parts) > 1 else ""

                viability = "VIABLE"
                for v in ["NOT RECOMMENDED", "STRONG", "VIABLE", "WEAK"]:
                    if eighth.startswith(v):
                        viability = v
                        break

                syn_match = re.search(r"Synergy:\s*(\d+)", eighth)
                meta_match = re.search(r"(\d+)/5\s*on-meta", eighth)

                current_comp = {
                    "archetype": archetype,
                    "description": description,
                    "viability": viability,
                    "synergy": int(syn_match.group(1)) if syn_match else 0,
                    "on_meta": meta_match.group(1) if meta_match else "0",
                    "picks": [],
                }
                (blue_comps if current_team == "blue" else red_comps).append(current_comp)
                continue

            # Pick rows: skip the column header row ("Player","Role","Champion",...)
            if first == "Player" and r[1].strip() == "Role":
                continue

            # A real pick row has Role in column B
            if current_comp is not None and r[1].strip() in ROLES:
                current_comp["picks"].append({
                    "player": r[0], "role": r[1], "champion": r[2],
                    "games": r[3], "wr": r[4], "kda": r[5], "fit": r[6],
                })

        return {
            "team1_roster": team1_roster,
            "team2_roster": team2_roster,
            "bans_blue": bans_blue,
            "bans_red": bans_red,
            "blue_comps": blue_comps,
            "red_comps": red_comps,
        }

    def _display_draft_results(self, draft_data, prediction=None):
        """Build a visual draft results view with Blue/Red team tabs."""
        self._clear_draft_results()
        dr = self.draft_results

        # ── Status Bar ──
        status_bar = tk.Frame(dr, bg=C["panel"], highlightthickness=1,
                              highlightbackground=C["gold_dk"])
        status_bar.pack(fill="x", pady=(0, 8))

        sl = tk.Frame(status_bar, bg=C["panel"])
        sl.pack(side="left", fill="x", expand=True, padx=12, pady=8)
        tk.Label(sl, text="DRAFT ANALYSIS COMPLETE",
                 bg=C["panel"], fg=C["green"],
                 font=("Segoe UI", 11, "bold")).pack(side="left")
        tk.Label(sl, text="  ·  Switch tabs below to see each team's plan",
                 bg=C["panel"], fg=C["txt2"],
                 font=("Segoe UI", 9)).pack(side="left")

        sr = tk.Frame(status_bar, bg=C["panel"])
        sr.pack(side="right", padx=8, pady=4)
        self._btn(sr, "Open Google Sheet", self._open_sheet_url,
                  w=20, s="dim").pack(side="right")

        # ── Match Prediction (compact, just below player selection) ──
        if prediction:
            self._render_prediction_bar(dr, prediction)

        # ── Inner Team Notebook ──
        style = ttk.Style()
        style.configure("Team.TNotebook", background=C["bg"], borderwidth=0,
                        tabmargins=[2, 4, 2, 0])
        style.configure("Team.TNotebook.Tab",
                        background=C["panel"], foreground=C["txt2"],
                        font=("Segoe UI", 11, "bold"), padding=[28, 10])
        style.map("Team.TNotebook.Tab",
                  background=[("selected", C["card"])],
                  foreground=[("selected", C["gold_lt"])])

        nb = ttk.Notebook(dr, style="Team.TNotebook")
        nb.pack(fill="both", expand=True, pady=4)

        blue_tab = tk.Frame(nb, bg=C["bg"])
        red_tab = tk.Frame(nb, bg=C["bg"])
        nb.add(blue_tab, text="  BLUE TEAM PLAN  ")
        nb.add(red_tab, text="  RED TEAM PLAN  ")

        self._build_team_plan(blue_tab, "BLUE",
                              draft_data["team1_roster"],
                              draft_data["bans_blue"],
                              draft_data["blue_comps"],
                              C["team_blue"], C["blue_lt"])
        self._build_team_plan(red_tab, "RED",
                              draft_data["team2_roster"],
                              draft_data["bans_red"],
                              draft_data["red_comps"],
                              C["team_red"], C["red"])

    def _render_prediction_bar(self, parent, r):
        """Compact prediction strip shown at top of draft results."""
        t1p, t2p = r["t1_prob"], r["t2_prob"]
        diff = abs(t1p - t2p)
        favor = "BLUE" if t1p > t2p else ("RED" if t2p > t1p else "EVEN")
        if diff < 2:
            verdict = "Essentially even — coin flip"
        elif diff < 8:
            verdict = f"{favor} slightly favored (+{diff:.1f}%)"
        elif diff < 16:
            verdict = f"{favor} favored (+{diff:.1f}%)"
        else:
            verdict = f"{favor} heavily favored (+{diff:.1f}%)"

        bar_frame = tk.Frame(parent, bg=C["panel"], highlightthickness=1,
                             highlightbackground=C["gold_dk"])
        bar_frame.pack(fill="x", pady=(0, 8))

        # Header row
        hdr = tk.Frame(bar_frame, bg=C["panel"])
        hdr.pack(fill="x", padx=12, pady=(8, 4))
        tk.Label(hdr, text="⚡  MATCH PREDICTION", bg=C["panel"], fg=C["gold"],
                 font=("Segoe UI", 10, "bold")).pack(side="left")
        tk.Label(hdr, text=verdict, bg=C["panel"], fg=C["txt2"],
                 font=("Segoe UI", 9, "italic")).pack(side="right")

        # Probability numbers + bar
        prob_row = tk.Frame(bar_frame, bg=C["panel"])
        prob_row.pack(fill="x", padx=12, pady=(0, 4))
        tk.Label(prob_row, text=f"{t1p}%", bg=C["panel"], fg="#5B9BD5",
                 font=("Segoe UI", 18, "bold")).pack(side="left")
        tk.Label(prob_row, text="BLUE", bg=C["panel"], fg="#5B9BD5",
                 font=("Segoe UI", 8, "bold")).pack(side="left", padx=(2, 8))

        bar_outer = tk.Frame(bar_frame, bg=C["bg"], height=10)
        bar_outer.pack(fill="x", padx=12, pady=(0, 4))
        bar_outer.pack_propagate(False)

        def _draw(e, t1p=t1p):
            w = bar_outer.winfo_width()
            t1w = max(4, int(w * t1p / 100))
            for ch in bar_outer.winfo_children():
                ch.destroy()
            tk.Frame(bar_outer, bg="#2A4A7A", width=t1w, height=10).pack(side="left")
            tk.Frame(bar_outer, bg="#7A2A2A", width=max(4, w - t1w), height=10).pack(side="left")

        bar_outer.bind("<Configure>", _draw)

        prob_row2 = tk.Frame(bar_frame, bg=C["panel"])
        prob_row2.pack(fill="x", padx=12, pady=(0, 8))
        tk.Label(prob_row2, text=f"{t2p}%", bg=C["panel"], fg="#C86060",
                 font=("Segoe UI", 18, "bold")).pack(side="right")
        tk.Label(prob_row2, text="RED", bg=C["panel"], fg="#C86060",
                 font=("Segoe UI", 8, "bold")).pack(side="right", padx=(8, 2))

    def _build_team_plan(self, parent, side_label, roster, bans, comps,
                         team_color, accent_color):
        """Build a single team's draft plan view inside a notebook tab."""

        # ── Team Banner ──
        banner_outer = tk.Frame(parent, bg=accent_color)
        banner_outer.pack(fill="x", pady=(6, 4), padx=2)
        banner = tk.Frame(banner_outer, bg=team_color)
        banner.pack(fill="x", padx=2, pady=2)
        tk.Label(banner, text=f"{side_label} SIDE", bg=team_color,
                 fg=C["gold"], font=("Segoe UI", 16, "bold")).pack(pady=10)

        # ── Roster ──
        self._section_bar(parent, "TEAM ROSTER", accent_color)

        roster_card = tk.Frame(parent, bg=C["panel"], highlightthickness=1,
                               highlightbackground=C["border"])
        roster_card.pack(fill="x", padx=4, pady=(0, 8))

        rh = tk.Frame(roster_card, bg=C["card"])
        rh.pack(fill="x")
        for txt, w in [("ROLE", 8), ("PLAYER", 18), ("RANK", 8),
                       ("TOP CUSTOM CHAMP", 28)]:
            tk.Label(rh, text=txt, bg=C["card"], fg=C["gold_dk"],
                     font=("Segoe UI", 9, "bold"), width=w,
                     anchor="w").pack(side="left", padx=6, pady=4)

        if not roster:
            tk.Label(roster_card, text="No roster data",
                     bg=C["panel"], fg=C["txt_dim"],
                     font=("Segoe UI", 10, "italic")).pack(pady=8)
        else:
            for i, p in enumerate(roster):
                bg = C["panel"] if i % 2 == 0 else C["input"]
                row = tk.Frame(roster_card, bg=bg)
                row.pack(fill="x")
                tk.Label(row, text=p["role"], bg=bg, fg=C["gold"],
                         font=("Segoe UI", 10, "bold"), width=8,
                         anchor="w").pack(side="left", padx=6, pady=5)
                _pname = p["player"]
                name_lbl = tk.Label(row, text=_pname, bg=bg, fg=C["txt"],
                         font=("Segoe UI", 11, "bold"), width=18,
                         anchor="w", cursor="hand2")
                name_lbl.pack(side="left", padx=6, pady=5)
                name_lbl.bind("<Button-1>", lambda e, n=_pname: self._navigate_to_scout(n))
                tk.Label(row, text=p["rank"] or "-", bg=bg, fg=C["blue_lt"],
                         font=("Segoe UI", 10, "bold"), width=8,
                         anchor="w").pack(side="left", padx=6, pady=5)
                tk.Label(row, text=p["top_champ"] or "-", bg=bg, fg=C["txt2"],
                         font=("Segoe UI", 9), anchor="w").pack(
                    side="left", padx=6, pady=5, fill="x", expand=True)

        # ── Bans ──
        self._section_bar(parent, "RECOMMENDED BANS", accent_color)
        tk.Label(parent,
                 text="Champions to ban against the enemy team's biggest threats",
                 bg=C["bg"], fg=C["txt_dim"],
                 font=("Segoe UI", 8, "italic")).pack(anchor="w", padx=10)

        bans_card = tk.Frame(parent, bg=C["panel"], highlightthickness=1,
                             highlightbackground=C["border"])
        bans_card.pack(fill="x", padx=4, pady=(2, 8))

        bh = tk.Frame(bans_card, bg=C["card"])
        bh.pack(fill="x")
        for txt, w in [("PHASE", 11), ("CHAMPION", 16),
                       ("ENEMY TARGET", 18), ("WR", 7),
                       ("GAMES", 7), ("PRIORITY", 10)]:
            tk.Label(bh, text=txt, bg=C["card"], fg=C["gold_dk"],
                     font=("Segoe UI", 9, "bold"), width=w,
                     anchor="w").pack(side="left", padx=6, pady=4)

        if not bans:
            tk.Label(bans_card,
                     text="No ban recommendations available "
                          "(need 5+ games per champion)",
                     bg=C["panel"], fg=C["txt_dim"],
                     font=("Segoe UI", 10, "italic")).pack(pady=8)
        else:
            for i, b in enumerate(bans):
                bg = C["panel"] if i % 2 == 0 else C["input"]
                phase_color = C["red"] if "1st" in b["phase"] else C["gold_dk"]
                row = tk.Frame(bans_card, bg=bg)
                row.pack(fill="x")
                tk.Label(row, text=b["phase"], bg=bg, fg=phase_color,
                         font=("Segoe UI", 9, "bold"), width=11,
                         anchor="w").pack(side="left", padx=6, pady=5)
                tk.Label(row, text=b["champion"], bg=bg, fg=C["red"],
                         font=("Segoe UI", 11, "bold"), width=16,
                         anchor="w").pack(side="left", padx=6, pady=5)
                _tname = b["target"]
                tgt_lbl = tk.Label(row, text=_tname, bg=bg, fg=C["txt"],
                         font=("Segoe UI", 10), width=18,
                         anchor="w", cursor="hand2")
                tgt_lbl.pack(side="left", padx=6, pady=5)
                tgt_lbl.bind("<Button-1>", lambda e, n=_tname: self._navigate_to_scout(n))
                tk.Label(row, text=b["wr"], bg=bg, fg=C["green"],
                         font=("Segoe UI", 10, "bold"), width=7,
                         anchor="w").pack(side="left", padx=6, pady=5)
                tk.Label(row, text=str(b["games"]), bg=bg, fg=C["txt2"],
                         font=("Segoe UI", 10), width=7,
                         anchor="w").pack(side="left", padx=6, pady=5)
                tk.Label(row, text=str(b["priority"]), bg=bg, fg=C["gold"],
                         font=("Segoe UI", 10, "bold"), width=10,
                         anchor="w").pack(side="left", padx=6, pady=5)

        # ── Comp Suggestions ──
        self._section_bar(parent, "TEAM COMP SUGGESTIONS", accent_color)
        tk.Label(parent,
                 text="Best compositions for this roster, sorted by overall strength",
                 bg=C["bg"], fg=C["txt_dim"],
                 font=("Segoe UI", 8, "italic")).pack(anchor="w", padx=10)
        tk.Frame(parent, bg=C["bg"], height=4).pack()

        if not comps:
            tk.Label(parent, text="No comp suggestions available",
                     bg=C["bg"], fg=C["txt_dim"],
                     font=("Segoe UI", 10, "italic")).pack(pady=12)
        else:
            for comp in comps:
                self._build_comp_card(parent, comp)

        tk.Frame(parent, bg=C["bg"], height=14).pack()  # bottom padding

    def _build_comp_card(self, parent, comp):
        """Build a single comp suggestion card with viability-coded header."""
        via_colors = {
            "STRONG":          ("#1B6B3A", C["gold_lt"]),
            "VIABLE":          ("#2C5F8F", C["gold_lt"]),
            "WEAK":            ("#8E6E2E", C["gold_lt"]),
            "NOT RECOMMENDED": ("#7C3030", C["gold_lt"]),
        }
        via_bg, via_fg = via_colors.get(comp["viability"], (C["card"], C["txt"]))

        card = tk.Frame(parent, bg=C["panel"], highlightthickness=1,
                        highlightbackground=C["border"])
        card.pack(fill="x", padx=4, pady=4)

        # Header bar
        header = tk.Frame(card, bg=via_bg)
        header.pack(fill="x")

        left = tk.Frame(header, bg=via_bg)
        left.pack(side="left", fill="x", expand=True, padx=12, pady=8)
        tk.Label(left, text=comp["archetype"], bg=via_bg, fg=via_fg,
                 font=("Segoe UI", 13, "bold"), anchor="w").pack(anchor="w")
        if comp["description"]:
            tk.Label(left, text=comp["description"], bg=via_bg, fg=C["txt"],
                     font=("Segoe UI", 8, "italic"), anchor="w",
                     wraplength=420, justify="left").pack(anchor="w")

        right = tk.Frame(header, bg=via_bg)
        right.pack(side="right", padx=12, pady=8)
        tk.Label(right, text=comp["viability"], bg=via_bg, fg=via_fg,
                 font=("Segoe UI", 11, "bold")).pack(anchor="e")
        tk.Label(right,
                 text=f"Synergy {comp['synergy']}/100  ·  "
                      f"{comp['on_meta']}/5 on-meta",
                 bg=via_bg, fg=C["txt"],
                 font=("Segoe UI", 8)).pack(anchor="e")

        # Pick column headers
        ph = tk.Frame(card, bg=C["card"])
        ph.pack(fill="x")
        for txt, w in [("PLAYER", 16), ("ROLE", 8), ("CHAMPION", 18),
                       ("GAMES", 7), ("WR", 7), ("KDA", 7), ("FIT", 12)]:
            tk.Label(ph, text=txt, bg=C["card"], fg=C["gold_dk"],
                     font=("Segoe UI", 8, "bold"), width=w,
                     anchor="w").pack(side="left", padx=4, pady=3)

        fit_colors = {
            "MAIN":     C["green"],
            "Comfort":  C["gold"],
            "Off-meta": C["red"],
            "No data":  C["txt_dim"],
        }

        if not comp["picks"]:
            tk.Label(card, text="No picks available",
                     bg=C["panel"], fg=C["txt_dim"],
                     font=("Segoe UI", 9, "italic")).pack(pady=4)
        else:
            for i, p in enumerate(comp["picks"]):
                bg = C["panel"] if i % 2 == 0 else C["input"]
                row = tk.Frame(card, bg=bg)
                row.pack(fill="x")
                _pname = p["player"]
                cp_lbl = tk.Label(row, text=_pname, bg=bg, fg=C["txt"],
                         font=("Segoe UI", 10), width=16,
                         anchor="w", cursor="hand2")
                cp_lbl.pack(side="left", padx=4, pady=3)
                cp_lbl.bind("<Button-1>", lambda e, n=_pname: self._navigate_to_scout(n))
                tk.Label(row, text=p["role"], bg=bg, fg=C["gold"],
                         font=("Segoe UI", 10, "bold"), width=8,
                         anchor="w").pack(side="left", padx=4, pady=3)
                tk.Label(row, text=p["champion"], bg=bg, fg=C["blue_lt"],
                         font=("Segoe UI", 10, "bold"), width=18,
                         anchor="w").pack(side="left", padx=4, pady=3)
                tk.Label(row, text=str(p["games"]), bg=bg, fg=C["txt2"],
                         font=("Segoe UI", 10), width=7,
                         anchor="w").pack(side="left", padx=4, pady=3)
                tk.Label(row, text=str(p["wr"]), bg=bg, fg=C["green"],
                         font=("Segoe UI", 10), width=7,
                         anchor="w").pack(side="left", padx=4, pady=3)
                tk.Label(row, text=str(p["kda"]), bg=bg, fg=C["txt2"],
                         font=("Segoe UI", 10), width=7,
                         anchor="w").pack(side="left", padx=4, pady=3)
                fit_color = fit_colors.get(p["fit"], C["txt"])
                tk.Label(row, text=p["fit"], bg=bg, fg=fit_color,
                         font=("Segoe UI", 10, "bold"), width=12,
                         anchor="w").pack(side="left", padx=4, pady=3)

    def _section_bar(self, parent, text, accent_color):
        """Cinematic section header: short accent bar + uppercase label."""
        f = tk.Frame(parent, bg=C["bg"])
        f.pack(fill="x", pady=(14, 6), padx=4)

        bar = tk.Frame(f, bg=accent_color, width=22, height=2)
        bar.pack(side="left", padx=(0, 10), pady=(6, 0))
        bar.pack_propagate(False)

        tk.Label(f, text=text, bg=C["bg"], fg=accent_color,
                 font=("Segoe UI", 11, "bold")).pack(side="left", anchor="w")

    def _show_draft_loading(self, msg):
        """Show a loading box in the results area while draft is running."""
        self._clear_draft_results()
        box = tk.Frame(self.draft_results, bg=C["panel"],
                       highlightthickness=1,
                       highlightbackground=C["gold_dk"])
        box.pack(fill="x", padx=8, pady=20)
        tk.Label(box, text="WORKING", bg=C["panel"], fg=C["gold"],
                 font=("Segoe UI", 18, "bold")).pack(pady=(14, 4))
        tk.Label(box, text=msg, bg=C["panel"], fg=C["blue_lt"],
                 font=("Segoe UI", 12, "bold")).pack(pady=(0, 4))
        tk.Label(box,
                 text="Reading scouting data, computing bans and comps...",
                 bg=C["panel"], fg=C["txt2"],
                 font=("Segoe UI", 9)).pack(pady=(0, 14))

    def _open_sheet_url(self):
        """Open the configured Google Sheet URL in the default browser."""
        url = self.config.get("sheet_url", "")
        if url:
            try:
                webbrowser.open(url)
                self.log("Opening Google Sheet in browser.\n", "blue")
            except Exception as e:
                self.log(f"Couldn't open URL: {e}\n", "red")

    def _clear_draft_results(self):
        for w in self.draft_results.winfo_children():
            w.destroy()

    def _show_draft_error(self, msg):
        self._clear_draft_results()
        tk.Label(self.draft_results, text=msg, bg=C["bg"], fg=C["red"],
                font=("Segoe UI", 11)).pack(pady=20)

    # ── Scouting Tab ──────────────────────────────────────────

    def build_scouting_tab(self):
        # Scrollable canvas for scouting content
        canvas = tk.Canvas(self.tab_scout, bg=C["bg"], highlightthickness=0)
        scrollbar = tk.Scrollbar(self.tab_scout, orient="vertical",
                                 command=canvas.yview)
        self.scout_frame = tk.Frame(canvas, bg=C["bg"])

        self.scout_frame.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        window_id = canvas.create_window((0, 0), window=self.scout_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        # Stretch inner frame to canvas width
        canvas.bind("<Configure>",
            lambda e, wid=window_id: canvas.itemconfigure(wid, width=e.width))

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        self._bind_canvas_scroll(canvas, self.tab_scout)

        sf = self.scout_frame

        # Title
        self._tab_title(sf, "PLAYER", "SCOUTING REPORT")

        # Selector area
        selector = tk.Frame(sf, bg=C["bg"])
        selector.pack(fill="x", padx=16, pady=12)

        tk.Label(selector, text="PLAYER", bg=C["bg"], fg=C["gold_dk"],
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 4))

        sel_row = tk.Frame(selector, bg=C["bg"])
        sel_row.pack(fill="x")

        self.scout_player_var = tk.StringVar()
        scout_menu = tk.OptionMenu(sel_row, self.scout_player_var,
                                   *self.player_list if self.player_list
                                   else ["Loading..."])
        scout_menu._var = self.scout_player_var
        scout_menu.configure(bg=C["input"], fg=C["txt"],
                             activebackground=C["hover"],
                             activeforeground=C["gold"],
                             font=("Segoe UI", 11), highlightthickness=0,
                             relief="flat", width=24, indicatoron=True)
        scout_menu["menu"].configure(bg=C["input"], fg=C["txt"],
                                     activebackground=C["hover"],
                                     activeforeground=C["gold"],
                                     font=("Segoe UI", 10))
        scout_menu.pack(side="left", padx=(0, 10))
        # Register so _refresh_dropdowns rebuilds it when players load
        self.player_menus.append(scout_menu)

        self._btn(sel_row, "LOAD REPORT", self.load_scout_ui,
                  w=18, s="accent").pack(side="left")

        tk.Frame(sf, bg=C["gold_dk"], height=1).pack(fill="x", padx=16, pady=4)

        # Results area
        self.scout_results = tk.Frame(sf, bg=C["bg"])
        self.scout_results.pack(fill="both", expand=True, padx=16, pady=(4, 16))

        tk.Label(self.scout_results,
                 text="Select a player and click LOAD REPORT to view their scouting data",
                 bg=C["bg"], fg=C["txt_dim"],
                 font=("Segoe UI", 11)).pack(pady=30)

    def load_scout_ui(self):
        """Triggered by Load Report button — kicks off bg fetch."""
        name = self.scout_player_var.get().strip()
        if not name or name == "Loading...":
            self._show_scout_error("Pick a player from the dropdown first.")
            return

        self._show_scout_loading(name)
        self.jobs.submit("load_scout",
                         lambda c, n=name: self._load_scout_bg(n))

    def _load_scout_bg(self, player_name):
        """Background fetch of a player's scouting sheet."""
        try:
            import gspread
            from google.oauth2.service_account import Credentials
            cfg = self.config
            creds = Credentials.from_service_account_file(
                cfg["creds_path"],
                scopes=["https://www.googleapis.com/auth/spreadsheets",
                         "https://www.googleapis.com/auth/drive"])
            gc = gspread.authorize(creds)
            if "docs.google.com" in cfg["sheet_url"]:
                ss = gc.open_by_url(cfg["sheet_url"])
            else:
                ss = gc.open(cfg["sheet_url"])

            # Sheet name uses same truncation rule as the writer
            sheet_name = f"Scout - {player_name}"[:30]
            try:
                ws = ss.worksheet(sheet_name)
            except Exception:
                self.after(0, self._show_scout_error,
                           f"No scouting report found for {player_name}.\n"
                           f"Run 'Full Scout' from the Commands tab first.")
                return

            data = self._parse_scouting_sheet(ws)

            # Also fetch rank history for the graph
            history = []
            try:
                rh_ws = ss.worksheet("Rank History")
                rh_vals = rh_ws.get_all_values()
                if len(rh_vals) >= 3:
                    header = rh_vals[1]
                    col_idx = None
                    for ci, col_name in enumerate(header):
                        if col_name.strip().lower() == player_name.strip().lower():
                            col_idx = ci
                            break
                    if col_idx is not None:
                        for row in rh_vals[2:]:
                            if col_idx < len(row) and row[col_idx]:
                                try:
                                    history.append((row[0], float(row[col_idx])))
                                except ValueError:
                                    pass
            except Exception:
                pass

            self.after(0, self._display_scouting_results, data, None, history)
            self.after(0, self.log,
                       f"Loaded scouting report for {player_name}.\n", "green")
        except Exception as e:
            self.after(0, self._show_scout_error,
                       f"Couldn't load scouting report: {e}")

    # ── Scouting Sheet Parser ─────────────────────────────────

    def _parse_scouting_sheet(self, ws):
        """Parse the 'Scout - PlayerName' sheet into a structured dict."""
        values = cached_get_all_values(ws)

        result = {
            "player": "", "subtitle": "", "power_rating": None,
            "overview_headers": [], "overview_values": [],
            "must_bans": [], "must_bans_msg": None,
            "ban_impact": None,
            "champ_pool": [],
            "roles": [],
            "form_label": "", "form_state": "",
            "matches": [],
            "inhouse_header": "", "inhouse_champs": [],
            "scouted_at": None,
        }

        if not values:
            return result

        # Row 0: player name (col A) + scout timestamp (col L, index 11)
        if values[0] and values[0][0]:
            m = re.match(r"SCOUTING REPORT:\s*(.+)", values[0][0])
            if m:
                result["player"] = m.group(1).strip()
            if len(values[0]) > 11:
                ts_raw = str(values[0][11]).strip()
                if ts_raw.startswith("Scouted:"):
                    try:
                        from datetime import datetime as _dt
                        result["scouted_at"] = _dt.strptime(
                            ts_raw.replace("Scouted:", "").strip(),
                            "%Y-%m-%d %H:%M")
                    except ValueError:
                        pass

        # Row 1: subtitle
        if len(values) > 1 and values[1]:
            result["subtitle"] = values[1][0]

        # Walk through remaining rows
        i = 2
        while i < len(values):
            row = values[i]
            cell = str(row[0]).strip() if row and row[0] != "" and row[0] is not None else ""

            if not cell:
                i += 1
                continue

            # Power ranking
            if cell.startswith("POWER RANKING:"):
                result["power_rating"] = self._parse_power_rating(cell)
                i += 1
                continue

            # Overview stats: header row begins with "KDA"
            if cell == "KDA" and len(row) > 1 and row[1].strip() == "Avg Kills":
                result["overview_headers"] = [c.strip() for c in row[:12]]
                if i + 1 < len(values):
                    result["overview_values"] = [
                        (c if c is not None else "")
                        for c in values[i + 1][:12]]
                i += 2
                continue

            # Must-ban section
            if cell == "BAN THESE CHAMPIONS":
                i += 1
                if i >= len(values):
                    continue
                next_row = values[i]
                next_cell = next_row[0].strip() if next_row and next_row[0] else ""
                if next_cell == "Champion":
                    # Headers row, then data rows until blank/next section
                    i += 1
                    while i < len(values):
                        r = values[i]
                        c0 = str(r[0]).strip() if r and r[0] != "" and r[0] is not None else ""
                        if not c0 or self._is_section_header(c0):
                            break
                        result["must_bans"].append({
                            "name": c0,
                            "games": r[1] if len(r) > 1 else "",
                            "wins": r[2] if len(r) > 2 else "",
                            "losses": r[3] if len(r) > 3 else "",
                            "wr": r[4] if len(r) > 4 else "",
                            "kda": r[5] if len(r) > 5 else "",
                            "kills": r[6] if len(r) > 6 else "",
                            "deaths": r[7] if len(r) > 7 else "",
                            "assists": r[8] if len(r) > 8 else "",
                            "cs_min": r[9] if len(r) > 9 else "",
                            "damage": r[10] if len(r) > 10 else "",
                            "threat": r[11] if len(r) > 11 else "",
                        })
                        i += 1
                else:
                    # "No standout..." message
                    result["must_bans_msg"] = next_cell
                    i += 1
                continue

            # Ban impact line
            if cell.startswith("BAN IMPACT:"):
                result["ban_impact"] = self._parse_ban_impact(row)
                i += 1
                continue

            # Champion pool
            if cell == "FULL CHAMPION POOL":
                i += 1
                # Skip header row
                if (i < len(values) and values[i] and
                        values[i][0].strip() == "Champion"):
                    i += 1
                while i < len(values):
                    r = values[i]
                    c0 = str(r[0]).strip() if r and r[0] != "" and r[0] is not None else ""
                    if not c0 or self._is_section_header(c0):
                        break
                    result["champ_pool"].append({
                        "name": c0,
                        "games": r[1] if len(r) > 1 else "",
                        "wins": r[2] if len(r) > 2 else "",
                        "losses": r[3] if len(r) > 3 else "",
                        "wr": r[4] if len(r) > 4 else "",
                        "kda": r[5] if len(r) > 5 else "",
                        "kills": r[6] if len(r) > 6 else "",
                        "deaths": r[7] if len(r) > 7 else "",
                        "assists": r[8] if len(r) > 8 else "",
                        "cs_min": r[9] if len(r) > 9 else "",
                        "damage": r[10] if len(r) > 10 else "",
                        "gold": r[11] if len(r) > 11 else "",
                    })
                    i += 1
                continue

            # Role breakdown
            if cell == "ROLE BREAKDOWN":
                i += 1
                if (i < len(values) and values[i] and
                        values[i][0].strip() == "Role"):
                    i += 1
                while i < len(values):
                    r = values[i]
                    c0 = str(r[0]).strip() if r and r[0] != "" and r[0] is not None else ""
                    if not c0 or self._is_section_header(c0):
                        break
                    result["roles"].append({
                        "role": c0,
                        "games": r[1] if len(r) > 1 else "",
                        "pct": r[2] if len(r) > 2 else "",
                        "top_champs": r[3] if len(r) > 3 else "",
                    })
                    i += 1
                continue

            # Recent form
            if cell.startswith("RECENT FORM:"):
                result["form_label"] = cell
                # Extract state (HOT/COLD/MIXED)
                m = re.match(r"RECENT FORM:\s*(\S+)", cell)
                if m:
                    result["form_state"] = m.group(1)
                i += 1
                # Skip header row
                if (i < len(values) and values[i] and
                        values[i][0].strip() == "Game"):
                    i += 1
                while i < len(values):
                    r = values[i]
                    c0 = str(r[0]).strip() if r and r[0] != "" and r[0] is not None else ""
                    if not c0 or self._is_section_header(c0):
                        break
                    result["matches"].append({
                        "game": c0,
                        "result": r[1] if len(r) > 1 else "",
                        "champion": r[2] if len(r) > 2 else "",
                        "role": r[3] if len(r) > 3 else "",
                        "kda_str": r[4] if len(r) > 4 else "",
                        "kda": r[5] if len(r) > 5 else "",
                        "cs_min": r[6] if len(r) > 6 else "",
                        "damage": r[7] if len(r) > 7 else "",
                        "vision": r[8] if len(r) > 8 else "",
                        "gold": r[9] if len(r) > 9 else "",
                        "duration": r[10] if len(r) > 10 else "",
                    })
                    i += 1
                continue

            # In-house customs
            if cell.startswith("IN-HOUSE CUSTOM GAMES"):
                result["inhouse_header"] = cell
                i += 1
                if (i < len(values) and values[i] and
                        values[i][0].strip() == "Champion"):
                    i += 1
                while i < len(values):
                    r = values[i]
                    c0 = str(r[0]).strip() if r and r[0] != "" and r[0] is not None else ""
                    if not c0 or self._is_section_header(c0):
                        break
                    result["inhouse_champs"].append({
                        "name": c0,
                        "games": r[1] if len(r) > 1 else "",
                        "wins": r[2] if len(r) > 2 else "",
                        "losses": r[3] if len(r) > 3 else "",
                        "wr": r[4] if len(r) > 4 else "",
                        "kda": r[5] if len(r) > 5 else "",
                        "kills": r[6] if len(r) > 6 else "",
                        "deaths": r[7] if len(r) > 7 else "",
                        "assists": r[8] if len(r) > 8 else "",
                        "damage": r[9] if len(r) > 9 else "",
                    })
                    i += 1
                continue

            i += 1

        return result

    def _is_section_header(self, cell):
        """True if cell text marks the start of a known section."""
        markers = ("BAN THESE CHAMPIONS", "BAN IMPACT:", "FULL CHAMPION POOL",
                   "ROLE BREAKDOWN", "RECENT FORM:", "IN-HOUSE CUSTOM GAMES",
                   "POWER RANKING:")
        return any(cell.startswith(m) for m in markers)

    def _parse_power_rating(self, text):
        """Parse the power ranking bar string."""
        out = {"position": "", "score": "", "rating": "",
               "tier_score": "", "rank_score": ""}
        m = re.search(r"#(\S+)", text)
        if m:
            out["position"] = m.group(1)
        m = re.search(r"Final Score:\s*([^|]+)", text)
        if m:
            out["score"] = m.group(1).strip()
        m = re.search(r"Rating:\s*([^|]+)", text)
        if m:
            out["rating"] = m.group(1).strip()
        m = re.search(r"Tier Score \(60%\):\s*([^|]+)", text)
        if m:
            out["tier_score"] = m.group(1).strip()
        m = re.search(r"Rank Score \(40%\):\s*([^|]+)", text)
        if m:
            out["rank_score"] = m.group(1).strip()
        return out

    def _parse_ban_impact(self, row):
        """Parse the 'BAN IMPACT' line from a row."""
        text = " ".join(c for c in row if c)
        out = {"text": "", "wr": "", "games": ""}
        m = re.match(r"(BAN IMPACT:[^|]*?)(?:Remaining|$)", text)
        if m:
            out["text"] = m.group(1).strip()
        m = re.search(r"Remaining WR:\s*(\d+(?:\.\d+)?%)", text)
        if m:
            out["wr"] = m.group(1)
        m = re.search(r"\((\d+)\s*games?\)", text)
        if m:
            out["games"] = m.group(1)
        return out

    # ── Scouting Display ──────────────────────────────────────

    def _display_scouting_results(self, data, parent=None, history=None):
        """Render scouting data as cards into `parent`.

        Defaults to self.scout_results (the Scouting tab); the rating tab
        passes its own container to reuse the same display.
        """
        if parent is None:
            self._clear_scout_results()
            parent = self.scout_results
        sr = parent

        if not data["player"]:
            tk.Label(sr,
                     text="Couldn't read scouting report (sheet may be empty).",
                     bg=C["bg"], fg=C["red"],
                     font=("Segoe UI", 11)).pack(pady=20)
            return

        # ── Player Header ──
        self._build_scout_header(sr, data)

        # ── Scout Age Badge ──
        if data.get("scouted_at"):
            self._build_scout_age_badge(sr, data["scouted_at"])

        # ── Rank History Graph ──
        if history:
            tk.Label(sr, text="RANK HISTORY", bg=C["bg"], fg=C["gold"],
                     font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(4, 2))
            self._profile_render_graph(sr, history)
            tk.Frame(sr, bg=C["rule"], height=1).pack(fill="x", pady=(4, 8))

        # ── Power Rating ──
        if data["power_rating"]:
            self._build_scout_rating(sr, data["power_rating"])

        # ── Overview Stats ──
        if data["overview_headers"] and data["overview_values"]:
            self._build_scout_overview(sr, data)

        # ── Recent Form (moved up - quick at-a-glance) ──
        if data["matches"]:
            self._build_scout_form(sr, data)

        # ── Ban Targets ──
        self._build_scout_bans(sr, data)

        # ── Ban Impact ──
        if data["ban_impact"] and data["ban_impact"].get("text"):
            self._build_scout_ban_impact(sr, data["ban_impact"])

        # ── Champion Pool ──
        if data["champ_pool"]:
            self._build_scout_champ_pool(sr, data["champ_pool"])

        # ── Role Breakdown ──
        if data["roles"]:
            self._build_scout_roles(sr, data["roles"])

        # ── In-House Customs ──
        if data["inhouse_champs"]:
            self._build_scout_inhouse(sr, data)

        tk.Frame(sr, bg=C["bg"], height=14).pack()

    def _build_scout_header(self, parent, data):
        """Player name plaque with gold double-rule above and below."""
        outer = tk.Frame(parent, bg=C["bg"])
        outer.pack(fill="x", pady=(0, 14))

        # Double gold rule (top)
        tk.Frame(outer, bg=C["gold"], height=1).pack(fill="x")
        tk.Frame(outer, bg=C["gold_dk"], height=1).pack(fill="x", pady=(2, 0))

        body = tk.Frame(outer, bg=C["panel"])
        body.pack(fill="x")
        tk.Label(body, text=data["player"].upper(), bg=C["panel"],
                 fg=C["gold_lt"],
                 font=("Segoe UI", 26, "bold")).pack(pady=(18, 4))
        if data["subtitle"]:
            tk.Label(body, text=data["subtitle"], bg=C["panel"],
                     fg=C["txt2"],
                     font=("Segoe UI", 11)).pack(pady=(0, 18))

        # Double gold rule (bottom)
        tk.Frame(outer, bg=C["gold_dk"], height=1).pack(fill="x")
        tk.Frame(outer, bg=C["gold"], height=1).pack(fill="x", pady=(2, 0))

    def _navigate_to_scout(self, name):
        """Switch to the Scouting tab and load this player's report."""
        self.notebook.select(self.tab_scout)
        self.scout_player_var.set(name)
        self.load_scout_ui()

    # Y-axis gridline positions (at tier boundaries, i.e. the IV division of each tier)
    _CHART_RANK_LABELS = {
        0: "Unranked", 5: "Bronze", 9: "Silver", 13: "Gold",
        17: "Plat", 21: "Emerald", 25: "Diamond",
        29: "Master", 30: "GM", 31: "Chall",
    }
    # Tier zone fill colors — boundaries match RANK_CHART_VALUES exactly
    # Iron=1-4, Bronze=5-8, Silver=9-12, Gold=13-16, Plat=17-20,
    # Emerald=21-24, Diamond=25-28, Master+=29-31
    _CHART_ZONES = [
        (0,  5,  "#1A1A1A"),  # Unranked / Iron
        (5,  9,  "#1E1208"),  # Bronze
        (9,  13, "#1A1A1A"),  # Silver
        (13, 17, "#1E1A08"),  # Gold
        (17, 21, "#091E1E"),  # Platinum
        (21, 25, "#0A1A0F"),  # Emerald
        (25, 29, "#0A0E1E"),  # Diamond
        (29, 32, "#1A091E"),  # Master+
    ]
    # Exact rank name per integer chart value (0-31) for tooltip display
    _VALUE_TO_RANK_NAME = {
        0: "Unranked",
        1: "Iron IV", 2: "Iron III", 3: "Iron II", 4: "Iron I",
        5: "Bronze IV", 6: "Bronze III", 7: "Bronze II", 8: "Bronze I",
        9: "Silver IV", 10: "Silver III", 11: "Silver II", 12: "Silver I",
        13: "Gold IV", 14: "Gold III", 15: "Gold II", 16: "Gold I",
        17: "Plat IV", 18: "Plat III", 19: "Plat II", 20: "Plat I",
        21: "Emer IV", 22: "Emer III", 23: "Emer II", 24: "Emer I",
        25: "Dia IV", 26: "Dia III", 27: "Dia II", 28: "Dia I",
        29: "Master", 30: "GM", 31: "Chall",
    }

    def _profile_render_graph(self, parent, history):
        """Draw a line chart of rank history on a tk.Canvas."""
        W, H = 460, 200
        LM, RM, TM, BM = 58, 12, 14, 36  # left/right/top/bottom margins
        cw = W - LM - RM
        ch = H - TM - BM

        canvas = tk.Canvas(parent, width=W, height=H,
                           bg=C["bg"], highlightthickness=0)
        canvas.pack(pady=(0, 8))

        values = [v for _, v in history]
        dates  = [d for d, _ in history]
        if not values:
            canvas.create_text(W // 2, H // 2,
                               text="No history data yet",
                               fill=C["txt_dim"], font=("Segoe UI", 10))
            return

        y_min = max(0, min(values) - 1)
        y_max = min(31, max(values) + 1)
        if y_max == y_min:
            y_min = max(0, y_min - 1)
            y_max = min(31, y_max + 1)

        def cx(i):
            n = len(values)
            return LM + (i / max(n - 1, 1)) * cw

        def cy(v):
            return TM + (1 - (v - y_min) / (y_max - y_min)) * ch

        # Tier zone fills
        for z_lo, z_hi, z_col in self._CHART_ZONES:
            if z_hi <= y_min or z_lo >= y_max:
                continue
            lo = max(z_lo, y_min)
            hi = min(z_hi, y_max)
            canvas.create_rectangle(
                LM, cy(hi), LM + cw, cy(lo),
                fill=z_col, outline="")

        # Horizontal grid lines at major rank boundaries
        for tick_v, tick_lbl in self._CHART_RANK_LABELS.items():
            if y_min <= tick_v <= y_max:
                yp = cy(tick_v)
                canvas.create_line(LM, yp, LM + cw, yp,
                                   fill="#2A2A2A", width=1, dash=(3, 4))
                canvas.create_text(LM - 4, yp, text=tick_lbl,
                                   anchor="e", fill=C["txt_dim"],
                                   font=("Segoe UI", 7))

        # Chart border box
        canvas.create_rectangle(LM, TM, LM + cw, TM + ch,
                                 outline="#333333", width=1)

        # Line
        if len(values) >= 2:
            coords = []
            for i, v in enumerate(values):
                coords.extend([cx(i), cy(v)])
            canvas.create_line(*coords, fill=C["gold"], width=2,
                                smooth=True, joinstyle="round")

        # Dots + tooltip-on-hover
        dot_radius = 4
        for i, (v, d) in enumerate(zip(values, dates)):
            xp, yp = cx(i), cy(v)
            dot = canvas.create_oval(
                xp - dot_radius, yp - dot_radius,
                xp + dot_radius, yp + dot_radius,
                fill=C["gold_lt"], outline=C["gold"], width=1)

            # Exact rank name for tooltip
            rank_lbl = self._VALUE_TO_RANK_NAME.get(round(v), "Unknown")

            # Hover tooltip
            tip_text = f"{d}\n{rank_lbl}"
            tip = None

            def _enter(e, xp=xp, yp=yp, txt=tip_text, dot=dot):
                nonlocal tip
                canvas.itemconfig(dot, fill=C["gold"])
                tip = canvas.create_text(
                    min(max(xp, LM + 30), LM + cw - 30),
                    max(yp - 16, TM + 8),
                    text=txt, fill=C["txt"], font=("Segoe UI", 8, "bold"),
                    anchor="s", justify="center",
                    tags="tip")
                canvas.create_rectangle(
                    canvas.bbox("tip"),
                    fill=C["panel"], outline=C["gold_dk"], tags="tip_bg")
                canvas.tag_raise("tip")

            def _leave(e, dot=dot):
                nonlocal tip
                canvas.delete("tip")
                canvas.delete("tip_bg")
                canvas.itemconfig(dot, fill=C["gold_lt"])

            canvas.tag_bind(dot, "<Enter>", _enter)
            canvas.tag_bind(dot, "<Leave>", _leave)

        # X-axis date labels: show first, last, and up to 3 in between
        if len(dates) >= 2:
            label_indices = {0, len(dates) - 1}
            step = max(1, len(dates) // 4)
            for i in range(step, len(dates) - 1, step):
                label_indices.add(i)
            for i in sorted(label_indices):
                # Show only MM-DD for brevity
                d = dates[i]
                short = d[5:10] if len(d) >= 10 else d
                canvas.create_text(cx(i), TM + ch + 6,
                                   text=short, anchor="n",
                                   fill=C["txt_dim"], font=("Segoe UI", 7))

    def _build_scout_age_badge(self, parent, scouted_at):
        """Slim pill showing how old the scouting data is, color-coded by age."""
        from datetime import datetime as _dt
        days = (_dt.now() - scouted_at).days

        if days < 3:
            label = "Scouted today" if days == 0 else f"Scouted {days}d ago"
            color = C["green"]
            bg    = "#0F2218"
        elif days < 7:
            label = f"Scouted {days}d ago  —  consider refreshing"
            color = C["gold"]
            bg    = "#1E1A0A"
        else:
            label = f"Scouted {days}d ago  —  data may be outdated"
            color = C["red"]
            bg    = "#1E0A0A"

        pill = tk.Frame(parent, bg=bg, highlightthickness=1,
                        highlightbackground=color)
        pill.pack(fill="x", pady=(0, 8))
        tk.Label(pill, text=f"◷  {label}",
                 bg=bg, fg=color,
                 font=("Segoe UI", 9, "italic"),
                 anchor="w").pack(padx=14, pady=5, anchor="w")

    def _build_scout_rating(self, parent, pr):
        """Power rating card — muted accent stripe + dark body."""
        # Refined LoL-inspired rating colors (less neon, more brass/crimson)
        rating_colors = {
            "S": "#C8463C",   # crimson
            "A": "#C89B3C",   # warm gold
            "B": "#A0884E",   # muted brass
            "C": "#5C8A5C",   # sage
            "D": "#5C7A9C",   # steel blue
            "F": "#6E6E6E",   # gray
        }
        rating = pr.get("rating", "")
        accent = rating_colors.get(rating, C["gold_dk"])

        card = tk.Frame(parent, bg=C["panel"], highlightthickness=1,
                        highlightbackground=C["gold_dk"])
        card.pack(fill="x", pady=(0, 10))

        # Left accent stripe + content row
        stripe = tk.Frame(card, bg=accent, width=4)
        stripe.pack(side="left", fill="y")
        stripe.pack_propagate(False)

        body = tk.Frame(card, bg=C["panel"])
        body.pack(side="left", fill="x", expand=True, padx=18, pady=14)

        # Left side: position + rating letter
        left = tk.Frame(body, bg=C["panel"])
        left.pack(side="left")

        if pr.get("position"):
            pos_box = tk.Frame(left, bg=C["panel"])
            pos_box.pack(side="left", padx=(0, 24))
            tk.Label(pos_box, text="POWER RANK", bg=C["panel"],
                     fg=C["gold_dk"],
                     font=("Segoe UI", 8, "bold")).pack(anchor="w")
            tk.Label(pos_box, text=f"#{pr['position']}", bg=C["panel"],
                     fg=C["gold_lt"],
                     font=("Segoe UI", 26, "bold")).pack(anchor="w")

        if rating:
            r_box = tk.Frame(left, bg=C["panel"])
            r_box.pack(side="left")
            tk.Label(r_box, text="RATING", bg=C["panel"], fg=C["gold_dk"],
                     font=("Segoe UI", 8, "bold")).pack(anchor="w")
            tk.Label(r_box, text=rating, bg=C["panel"], fg=accent,
                     font=("Segoe UI", 32, "bold")).pack(anchor="w")

        # Right side: scores
        right = tk.Frame(body, bg=C["panel"])
        right.pack(side="right")
        if pr.get("score"):
            tk.Label(right, text="FINAL SCORE", bg=C["panel"],
                     fg=C["gold_dk"],
                     font=("Segoe UI", 8, "bold")).pack(anchor="e")
            tk.Label(right, text=str(pr["score"]), bg=C["panel"],
                     fg=C["gold"],
                     font=("Segoe UI", 18, "bold")).pack(anchor="e")
        sub_parts = []
        if pr.get("tier_score"):
            sub_parts.append(f"Tier {pr['tier_score']}")
        if pr.get("rank_score"):
            sub_parts.append(f"Rank {pr['rank_score']}")
        if sub_parts:
            tk.Label(right, text="  ·  ".join(sub_parts), bg=C["panel"],
                     fg=C["txt2"],
                     font=("Segoe UI", 9)).pack(anchor="e", pady=(2, 0))

    def _build_scout_overview(self, parent, data):
        """Stats grid — warmer tiles with gold accent underline."""
        self._scout_section_label(parent, "OVERVIEW")

        card = tk.Frame(parent, bg=C["panel"], highlightthickness=1,
                        highlightbackground=C["gold_dk"])
        card.pack(fill="x", pady=(0, 12))

        headers = data["overview_headers"]
        vals = data["overview_values"]
        n = min(len(headers), len(vals), 12)

        grid = tk.Frame(card, bg=C["panel"])
        grid.pack(fill="x", padx=14, pady=14)
        for col in range(4):
            grid.columnconfigure(col, weight=1, uniform="overview")

        TILE_BG = C["tile"]  # warmer dark slate for tiles

        for idx in range(n):
            r, c = divmod(idx, 4)
            tile = tk.Frame(grid, bg=TILE_BG, highlightthickness=1,
                            highlightbackground=C["border"])
            tile.grid(row=r, column=c, padx=4, pady=4, sticky="ew")

            tk.Label(tile, text=str(headers[idx]).upper(), bg=TILE_BG,
                     fg=C["gold_dk"],
                     font=("Segoe UI", 8, "bold")).pack(pady=(10, 2))
            val_text = str(vals[idx]) if vals[idx] not in (None, "") else "—"
            tk.Label(tile, text=val_text, bg=TILE_BG, fg=C["gold_lt"],
                     font=("Segoe UI", 14, "bold")).pack(pady=(0, 2))
            # Subtle gold accent under the value
            tk.Frame(tile, bg=C["gold_dk"], height=1).pack(
                fill="x", padx=24, pady=(4, 10))

    def _build_scout_form(self, parent, data):
        """Recent form — cinematic: dramatic banner with 2px bottom accent + accent-stripe match rows."""
        form = data.get("form_state", "").upper()
        # Banner uses cinematic dim tints — slightly deeper greens/reds
        banner_map = {
            "HOT":   ("#143a2c", C["teal"]),
            "COLD":  ("#3a1414", C["red"]),
            "MIXED": ("#3a2e14", C["gold_br"]),
        }
        banner_bg, accent = banner_map.get(form, (C["card"], C["gold_dk"]))

        self._scout_section_label(parent, "RECENT FORM", accent=accent)

        card = tk.Frame(parent, bg=C["panel"], highlightthickness=1,
                        highlightbackground=C["rule"])
        card.pack(fill="x", pady=(0, 12))

        # Banner with 2px bottom accent border
        banner = tk.Frame(card, bg=banner_bg)
        banner.pack(fill="x")
        tk.Label(banner, text=data["form_label"] or "RECENT FORM",
                 bg=banner_bg, fg=C["gold_lt"],
                 font=("Segoe UI", 12, "bold")).pack(pady=10)
        tk.Frame(card, bg=accent, height=2).pack(fill="x")

        # Column headers
        h = tk.Frame(card, bg=C["strip"])
        h.pack(fill="x")
        tk.Frame(h, width=3, bg=C["strip"]).pack(side="left")
        for txt, w in [("#", 4), ("RESULT", 7), ("CHAMPION", 14), ("ROLE", 6),
                       ("K/D/A", 10), ("KDA", 6), ("CS/M", 6),
                       ("DMG", 9), ("VIS", 5), ("GOLD", 9), ("TIME", 6)]:
            tk.Label(h, text=txt, bg=C["strip"], fg=C["gold_dk"],
                     font=("Segoe UI", 8, "bold"), width=w,
                     anchor="w").pack(side="left", padx=3, pady=5)

        # Match rows — muted tints + accent stripes
        WIN_BG, LOSS_BG = "#0E2620", "#261212"
        WIN_ACCENT, LOSS_ACCENT = C["teal"], C["red"]

        for i, m in enumerate(data["matches"][:10]):
            is_win = (str(m["result"]).upper() == "WIN")
            row_bg = WIN_BG if is_win else LOSS_BG
            row_accent = WIN_ACCENT if is_win else LOSS_ACCENT

            row = tk.Frame(card, bg=row_bg)
            row.pack(fill="x")

            # Accent stripe at left
            stripe = tk.Frame(row, bg=row_accent, width=3)
            stripe.pack(side="left", fill="y")
            stripe.pack_propagate(False)

            cells = [
                (str(m["game"]), C["txt_dim"], 4, ("Segoe UI", 9)),
                (str(m["result"]), row_accent, 7, ("Segoe UI", 9, "bold")),
                (str(m["champion"]), C["gold_lt"], 14,
                 ("Segoe UI", 10, "bold")),
                (str(m["role"]), C["gold"], 6, ("Segoe UI", 9, "bold")),
                (str(m["kda_str"]), C["txt"], 10, ("Segoe UI", 10)),
                (str(m["kda"]), C["txt"], 6, ("Segoe UI", 9)),
                (str(m["cs_min"]), C["txt2"], 6, ("Segoe UI", 9)),
                (str(m["damage"]), C["txt2"], 9, ("Segoe UI", 9)),
                (str(m["vision"]), C["txt2"], 5, ("Segoe UI", 9)),
                (str(m["gold"]), C["txt2"], 9, ("Segoe UI", 9)),
                (str(m["duration"]), C["txt2"], 6, ("Segoe UI", 9)),
            ]
            for text, fg, w, font in cells:
                tk.Label(row, text=text, bg=row_bg, fg=fg, font=font,
                         width=w, anchor="w").pack(side="left", padx=3, pady=5)

        if len(data["matches"]) > 10:
            tk.Label(card,
                     text=f"+ {len(data['matches']) - 10} more matches in the Google Sheet",
                     bg=C["panel"], fg=C["txt_dim"],
                     font=("Segoe UI", 8, "italic")).pack(pady=6)

    def _build_scout_bans(self, parent, data):
        """Must-ban section — refined threat badges."""
        self._scout_section_label(parent, "BAN TARGETS", accent="#C84B31")

        if not data["must_bans"]:
            msg = data.get("must_bans_msg") or \
                "No standout ban targets (no champion with 5+ games AND 65%+ WR)"
            card = tk.Frame(parent, bg="#0F2218", highlightthickness=1,
                            highlightbackground="#1F4A35")
            card.pack(fill="x", pady=(0, 12))
            tk.Label(card, text=msg, bg="#0F2218", fg="#5fb89a",
                     font=("Segoe UI", 10, "italic")).pack(pady=12)
            return

        card = tk.Frame(parent, bg=C["panel"], highlightthickness=1,
                        highlightbackground=C["gold_dk"])
        card.pack(fill="x", pady=(0, 12))

        h = tk.Frame(card, bg=C["strip"])
        h.pack(fill="x")
        tk.Frame(h, width=3, bg=C["strip"]).pack(side="left")
        for txt, w in [("CHAMPION", 14), ("GAMES", 6), ("WR", 6),
                       ("KDA", 6), ("CS/M", 6), ("DMG", 8),
                       ("THREAT", 11)]:
            tk.Label(h, text=txt, bg=C["strip"], fg=C["gold_dk"],
                     font=("Segoe UI", 8, "bold"), width=w,
                     anchor="w").pack(side="left", padx=4, pady=5)

        threat_color = {
            "PERMABAN": "#C8463C",
            "HIGH":     "#C89B3C",
            "ELEVATED": "#A0884E",
        }

        for i, b in enumerate(data["must_bans"]):
            row_bg = C["panel"] if i % 2 == 0 else C["panel_2"]
            row = tk.Frame(card, bg=row_bg)
            row.pack(fill="x")

            # Left accent stripe (subtle red)
            stripe = tk.Frame(row, bg="#7C2A20", width=3)
            stripe.pack(side="left", fill="y")
            stripe.pack_propagate(False)

            tk.Label(row, text=b["name"], bg=row_bg, fg="#E07060",
                     font=("Segoe UI", 11, "bold"), width=14,
                     anchor="w").pack(side="left", padx=4, pady=6)
            tk.Label(row, text=str(b["games"]), bg=row_bg, fg=C["txt"],
                     font=("Segoe UI", 10), width=6,
                     anchor="w").pack(side="left", padx=4, pady=6)
            tk.Label(row, text=str(b["wr"]), bg=row_bg, fg="#5fb89a",
                     font=("Segoe UI", 10, "bold"), width=6,
                     anchor="w").pack(side="left", padx=4, pady=6)
            tk.Label(row, text=str(b["kda"]), bg=row_bg, fg=C["txt"],
                     font=("Segoe UI", 10), width=6,
                     anchor="w").pack(side="left", padx=4, pady=6)
            tk.Label(row, text=str(b["cs_min"]), bg=row_bg, fg=C["txt2"],
                     font=("Segoe UI", 10), width=6,
                     anchor="w").pack(side="left", padx=4, pady=6)
            tk.Label(row, text=str(b["damage"]), bg=row_bg, fg=C["txt2"],
                     font=("Segoe UI", 10), width=8,
                     anchor="w").pack(side="left", padx=4, pady=6)

            # Threat badge — small inset pill
            threat = str(b["threat"]).strip()
            tc = threat_color.get(threat, C["txt"])
            badge_box = tk.Frame(row, bg=row_bg, width=98)
            badge_box.pack(side="left", padx=4, pady=6)
            badge_box.pack_propagate(False)
            tk.Label(badge_box, text=threat, bg=row_bg, fg=tc,
                     font=("Segoe UI", 9, "bold"),
                     anchor="w").pack(side="left")

    def _build_scout_ban_impact(self, parent, bi):
        """Ban impact — clean single card with refined contrast."""
        self._scout_section_label(parent, "BAN IMPACT", accent=C["gold"])

        try:
            wr_num = float(str(bi.get("wr", "0")).replace("%", ""))
        except (ValueError, TypeError):
            wr_num = 50.0

        # Muted backgrounds: dim green if below 50, dim red if above
        bg = "#0F2620" if wr_num < 50 else "#261212"
        accent = "#5fb89a" if wr_num < 50 else "#C84B31"

        card = tk.Frame(parent, bg=bg, highlightthickness=1,
                        highlightbackground=C["gold_dk"])
        card.pack(fill="x", pady=(0, 12))

        # Side accent stripe
        stripe = tk.Frame(card, bg=accent, width=4)
        stripe.pack(side="left", fill="y")
        stripe.pack_propagate(False)

        body = tk.Frame(card, bg=bg)
        body.pack(side="left", fill="x", expand=True, padx=14, pady=12)

        tk.Label(body, text=bi.get("text", ""), bg=bg, fg=C["gold_lt"],
                 font=("Segoe UI", 11, "bold"), wraplength=900,
                 justify="left").pack(anchor="w")

        stats_row = tk.Frame(body, bg=bg)
        stats_row.pack(anchor="w", pady=(8, 0))
        if bi.get("wr"):
            tk.Label(stats_row, text=f"REMAINING WR  {bi['wr']}",
                     bg=bg, fg=accent,
                     font=("Segoe UI", 11, "bold")).pack(
                side="left", padx=(0, 18))
        if bi.get("games"):
            tk.Label(stats_row, text=f"SAMPLE  {bi['games']} games",
                     bg=bg, fg=C["txt2"],
                     font=("Segoe UI", 9, "bold")).pack(side="left")

    def _build_scout_champ_pool(self, parent, champs):
        """Champion pool — muted WR coloring."""
        self._scout_section_label(parent, f"CHAMPION POOL  ·  {len(champs)}")

        card = tk.Frame(parent, bg=C["panel"], highlightthickness=1,
                        highlightbackground=C["gold_dk"])
        card.pack(fill="x", pady=(0, 12))

        h = tk.Frame(card, bg=C["strip"])
        h.pack(fill="x")
        for txt, w in [("CHAMPION", 14), ("GAMES", 6), ("W-L", 8),
                       ("WR", 6), ("KDA", 6), ("CS/M", 6),
                       ("DMG", 9), ("GOLD", 9)]:
            tk.Label(h, text=txt, bg=C["strip"], fg=C["gold_dk"],
                     font=("Segoe UI", 8, "bold"), width=w,
                     anchor="w").pack(side="left", padx=4, pady=5)

        for i, c in enumerate(champs):
            row_bg = C["panel"] if i % 2 == 0 else C["panel_2"]

            try:
                wr_num = float(str(c["wr"]).replace("%", ""))
            except (ValueError, TypeError):
                wr_num = 50.0

            # Muted WR-based name color
            if wr_num >= 60:
                name_color = "#5fb89a"  # muted teal
            elif wr_num < 45:
                name_color = "#C84B31"  # warm red
            else:
                name_color = C["gold_lt"]

            wr_color = ("#5fb89a" if wr_num >= 50 else "#C84B31")

            row = tk.Frame(card, bg=row_bg)
            row.pack(fill="x")

            tk.Label(row, text=str(c["name"]), bg=row_bg, fg=name_color,
                     font=("Segoe UI", 11, "bold"), width=14,
                     anchor="w").pack(side="left", padx=4, pady=5)
            tk.Label(row, text=str(c["games"]), bg=row_bg, fg=C["txt"],
                     font=("Segoe UI", 10), width=6,
                     anchor="w").pack(side="left", padx=4, pady=5)
            tk.Label(row, text=f"{c['wins']}-{c['losses']}", bg=row_bg,
                     fg=C["txt2"], font=("Segoe UI", 10), width=8,
                     anchor="w").pack(side="left", padx=4, pady=5)
            tk.Label(row, text=str(c["wr"]), bg=row_bg, fg=wr_color,
                     font=("Segoe UI", 10, "bold"), width=6,
                     anchor="w").pack(side="left", padx=4, pady=5)
            tk.Label(row, text=str(c["kda"]), bg=row_bg, fg=C["txt"],
                     font=("Segoe UI", 10), width=6,
                     anchor="w").pack(side="left", padx=4, pady=5)
            tk.Label(row, text=str(c["cs_min"]), bg=row_bg, fg=C["txt2"],
                     font=("Segoe UI", 10), width=6,
                     anchor="w").pack(side="left", padx=4, pady=5)
            tk.Label(row, text=str(c["damage"]), bg=row_bg, fg=C["txt2"],
                     font=("Segoe UI", 10), width=9,
                     anchor="w").pack(side="left", padx=4, pady=5)
            tk.Label(row, text=str(c["gold"]), bg=row_bg, fg=C["txt2"],
                     font=("Segoe UI", 10), width=9,
                     anchor="w").pack(side="left", padx=4, pady=5)

    def _build_scout_roles(self, parent, roles):
        """Role breakdown — primary role gets gold accent."""
        self._scout_section_label(parent, "ROLE BREAKDOWN")

        card = tk.Frame(parent, bg=C["panel"], highlightthickness=1,
                        highlightbackground=C["gold_dk"])
        card.pack(fill="x", pady=(0, 12))

        h = tk.Frame(card, bg=C["strip"])
        h.pack(fill="x")
        for txt, w in [("ROLE", 10), ("GAMES", 7), ("SHARE", 8),
                       ("TOP CHAMPIONS", 50)]:
            tk.Label(h, text=txt, bg=C["strip"], fg=C["gold_dk"],
                     font=("Segoe UI", 8, "bold"), width=w,
                     anchor="w").pack(side="left", padx=4, pady=5)

        for i, r in enumerate(roles):
            row_bg = C["panel"] if i % 2 == 0 else C["panel_2"]
            is_primary = (i == 0)

            row = tk.Frame(card, bg=row_bg)
            row.pack(fill="x")

            # Gold accent stripe for primary role
            if is_primary:
                stripe = tk.Frame(row, bg=C["gold"], width=3)
                stripe.pack(side="left", fill="y")
                stripe.pack_propagate(False)

            role_color = C["gold_lt"] if is_primary else C["txt"]
            tk.Label(row, text=str(r["role"]), bg=row_bg, fg=role_color,
                     font=("Segoe UI", 11, "bold"),
                     width=10 if is_primary else 11,
                     anchor="w").pack(side="left", padx=4, pady=6)
            tk.Label(row, text=str(r["games"]), bg=row_bg, fg=C["txt"],
                     font=("Segoe UI", 10), width=7,
                     anchor="w").pack(side="left", padx=4, pady=6)
            tk.Label(row, text=str(r["pct"]), bg=row_bg,
                     fg=C["gold"] if is_primary else C["txt2"],
                     font=("Segoe UI", 10, "bold"), width=8,
                     anchor="w").pack(side="left", padx=4, pady=6)
            tk.Label(row, text=str(r["top_champs"]), bg=row_bg, fg=C["txt2"],
                     font=("Segoe UI", 9), anchor="w").pack(
                side="left", padx=4, pady=6, fill="x", expand=True)

    def _build_scout_inhouse(self, parent, data):
        """In-house customs — refined mauve accent."""
        ACCENT = "#8a6fc9"  # softer mauve-purple
        ACCENT_DIM = "#2a1f47"

        self._scout_section_label(parent, "IN-HOUSE CUSTOMS", accent=ACCENT)

        card = tk.Frame(parent, bg=C["panel"], highlightthickness=1,
                        highlightbackground=ACCENT_DIM)
        card.pack(fill="x", pady=(0, 12))

        # Side accent + header
        if data.get("inhouse_header"):
            head_row = tk.Frame(card, bg=C["panel"])
            head_row.pack(fill="x")
            stripe = tk.Frame(head_row, bg=ACCENT, width=4)
            stripe.pack(side="left", fill="y")
            stripe.pack_propagate(False)
            tk.Label(head_row, text=str(data["inhouse_header"]),
                     bg=C["panel"], fg=ACCENT,
                     font=("Segoe UI", 11, "bold")).pack(
                side="left", padx=12, pady=10, anchor="w")

        h = tk.Frame(card, bg=C["strip"])
        h.pack(fill="x")
        for txt, w in [("CHAMPION", 14), ("GAMES", 6), ("W-L", 8),
                       ("WR", 6), ("KDA", 6), ("DMG", 10)]:
            tk.Label(h, text=txt, bg=C["strip"], fg=C["gold_dk"],
                     font=("Segoe UI", 8, "bold"), width=w,
                     anchor="w").pack(side="left", padx=4, pady=5)

        for i, c in enumerate(data["inhouse_champs"]):
            row_bg = C["panel"] if i % 2 == 0 else "#16122A"

            try:
                wr_num = float(str(c["wr"]).replace("%", ""))
            except (ValueError, TypeError):
                wr_num = 50.0
            wr_color = "#5fb89a" if wr_num >= 50 else "#C84B31"

            row = tk.Frame(card, bg=row_bg)
            row.pack(fill="x")

            tk.Label(row, text=str(c["name"]), bg=row_bg, fg=ACCENT,
                     font=("Segoe UI", 11, "bold"), width=14,
                     anchor="w").pack(side="left", padx=4, pady=5)
            tk.Label(row, text=str(c["games"]), bg=row_bg, fg=C["txt"],
                     font=("Segoe UI", 10), width=6,
                     anchor="w").pack(side="left", padx=4, pady=5)
            tk.Label(row, text=f"{c['wins']}-{c['losses']}", bg=row_bg,
                     fg=C["txt2"], font=("Segoe UI", 10), width=8,
                     anchor="w").pack(side="left", padx=4, pady=5)
            tk.Label(row, text=str(c["wr"]), bg=row_bg, fg=wr_color,
                     font=("Segoe UI", 10, "bold"), width=6,
                     anchor="w").pack(side="left", padx=4, pady=5)
            tk.Label(row, text=str(c["kda"]), bg=row_bg, fg=C["txt"],
                     font=("Segoe UI", 10), width=6,
                     anchor="w").pack(side="left", padx=4, pady=5)
            tk.Label(row, text=str(c["damage"]), bg=row_bg, fg=C["txt2"],
                     font=("Segoe UI", 10), width=10,
                     anchor="w").pack(side="left", padx=4, pady=5)

    def _scout_section_label(self, parent, text, accent=None):
        """Cinematic section header: short colored bar + caps label."""
        if accent is None:
            accent = C["gold"]

        f = tk.Frame(parent, bg=C["bg"])
        f.pack(fill="x", pady=(18, 6))

        title_row = tk.Frame(f, bg=C["bg"])
        title_row.pack(fill="x")

        # Short horizontal accent bar (replaces the diamond ornament)
        bar = tk.Frame(title_row, bg=accent, width=18, height=2)
        bar.pack(side="left", padx=(2, 10), pady=(6, 0))
        bar.pack_propagate(False)
        tk.Label(title_row, text=text, bg=C["bg"], fg=accent,
                 font=("Segoe UI", 10, "bold")).pack(side="left", anchor="w")

    def _tab_title(self, parent, eyebrow, title):
        """Cinematic tab-title plaque: small eyebrow caps above large main title.

        Replaces the single-line "TAB NAME" header used at the top of
        Draft, Scouting, Rating, and In-House tabs.
        """
        tk.Frame(parent, bg=C["gold"], height=2).pack(fill="x")
        hdr = tk.Frame(parent, bg=C["panel"])
        hdr.pack(fill="x")
        tk.Label(hdr, text=eyebrow.upper(), bg=C["panel"], fg=C["gold"],
                 font=("Segoe UI", 9, "bold")).pack(pady=(14, 0))
        tk.Label(hdr, text=title.upper(), bg=C["panel"], fg=C["gold_lt"],
                 font=("Segoe UI", 22, "bold")).pack(pady=(4, 14))
        tk.Frame(parent, bg=C["gold_dk"], height=1).pack(fill="x")

    def _clear_scout_results(self):
        for w in self.scout_results.winfo_children():
            w.destroy()

    def _show_scout_loading(self, name):
        """Loading state — refined frame with double gold rule."""
        self._clear_scout_results()
        outer = tk.Frame(self.scout_results, bg=C["bg"])
        outer.pack(fill="x", padx=8, pady=24)

        tk.Frame(outer, bg=C["gold"], height=1).pack(fill="x")
        tk.Frame(outer, bg=C["gold_dk"], height=1).pack(fill="x", pady=(2, 0))

        body = tk.Frame(outer, bg=C["panel"])
        body.pack(fill="x")
        tk.Label(body, text="LOADING REPORT", bg=C["panel"], fg=C["gold_dk"],
                 font=("Segoe UI", 9, "bold")).pack(pady=(18, 4))
        tk.Label(body, text=name.upper(), bg=C["panel"], fg=C["gold_lt"],
                 font=("Segoe UI", 18, "bold")).pack()
        tk.Label(body, text="Reading scouting data from Google Sheet...",
                 bg=C["panel"], fg=C["txt2"],
                 font=("Segoe UI", 9, "italic")).pack(pady=(6, 18))

        tk.Frame(outer, bg=C["gold_dk"], height=1).pack(fill="x")
        tk.Frame(outer, bg=C["gold"], height=1).pack(fill="x", pady=(2, 0))

    def _show_scout_error(self, msg):
        self._clear_scout_results()
        card = tk.Frame(self.scout_results, bg="#261212",
                        highlightthickness=1,
                        highlightbackground="#7C2A20")
        card.pack(fill="x", padx=8, pady=24)
        # Side stripe
        stripe = tk.Frame(card, bg="#C84B31", width=4)
        stripe.pack(side="left", fill="y")
        stripe.pack_propagate(False)
        tk.Label(card, text=msg, bg="#261212", fg="#E07060",
                 font=("Segoe UI", 11), justify="left",
                 wraplength=700).pack(padx=16, pady=18)

    # ── Auto-Update ───────────────────────────────────────────

    def _is_frozen(self):
        """True when running as a PyInstaller .exe (not from source)."""
        return getattr(sys, "frozen", False)

    def _check_for_updates_bg(self):
        """Background-poll GitHub for a newer release. Skips when running
        from source — there's no .exe to replace and we don't want to bug
        you during development."""
        if not self._is_frozen():
            return
        if not GITHUB_REPO or "/" not in GITHUB_REPO:
            return  # No repo configured; skip silently

        try:
            import urllib.request
            import json as _json
            url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
            req = urllib.request.Request(
                url,
                headers={"Accept": "application/vnd.github+json",
                         "User-Agent": "LoLPowerRankings-Updater"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = _json.loads(resp.read().decode("utf-8"))
        except Exception:
            return  # Network down / GitHub flaky / private repo / etc.

        latest_tag = (data.get("tag_name") or "").lstrip("v").strip()
        if not latest_tag:
            return

        if not self._is_newer_version(latest_tag, __version__):
            return

        # Pick the .exe asset off the release
        download_url = None
        download_size = 0
        for asset in data.get("assets", []) or []:
            name = (asset.get("name") or "").lower()
            if name.endswith(".exe"):
                download_url = asset.get("browser_download_url")
                download_size = asset.get("size", 0)
                break
        if not download_url:
            return  # Release has no .exe asset attached

        notes = (data.get("body") or "").strip()
        # Marshal back to the UI thread to surface the update pill
        self.after(0, self._show_update_available,
                   latest_tag, download_url, download_size, notes)

    def _is_newer_version(self, latest, current):
        """Compare two dotted-numeric version strings.

        Returns True iff `latest` > `current`. Tolerant of versions with
        differing numbers of components (e.g. "1.2" vs "1.2.0").
        """
        def parse(v):
            parts = []
            for p in v.split("."):
                # Strip non-numeric suffixes ("1.0.0-beta" → "1.0.0")
                num = ""
                for ch in p:
                    if ch.isdigit():
                        num += ch
                    else:
                        break
                parts.append(int(num) if num else 0)
            return parts

        try:
            l = parse(latest)
            c = parse(current)
            # Pad shorter list with zeros for comparison
            n = max(len(l), len(c))
            l += [0] * (n - len(l))
            c += [0] * (n - len(c))
            return l > c
        except Exception:
            return False

    def _show_update_available(self, version, download_url, size, notes):
        """Replace the version label with a clickable 'UPDATE AVAILABLE' pill."""
        if not getattr(self, "version_frame", None):
            return
        try:
            self.version_label.destroy()
        except Exception:
            pass

        pill = tk.Label(self.version_frame,
                        text=f"↓ UPDATE TO v{version}",
                        bg=C["gold_dk"], fg=C["gold_lt"],
                        font=("Segoe UI", 9, "bold"),
                        padx=12, pady=6,
                        cursor="hand2")
        pill.pack(side="right", pady=2)

        def _enter(_e):
            try: pill.configure(bg=C["gold_br"])
            except Exception: pass
        def _leave(_e):
            try: pill.configure(bg=C["gold_dk"])
            except Exception: pass
        pill.bind("<Enter>", _enter)
        pill.bind("<Leave>", _leave)
        pill.bind("<Button-1>",
                  lambda _e: self._open_update_dialog(version, download_url, size, notes))

        self.log(f"Update available: v{version}\n", "blue")

    def _open_update_dialog(self, version, download_url, size, notes):
        """Modal asking the user to confirm the update."""
        win = tk.Toplevel(self)
        win.title(f"Update to v{version}")
        win.configure(bg=C["bg"])
        win.geometry("520x420")
        win.resizable(False, False)
        win.transient(self)
        win.grab_set()

        # Header
        tk.Frame(win, bg=C["gold"], height=1).pack(fill="x")
        tk.Frame(win, bg=C["gold_dk"], height=1).pack(fill="x", pady=(2, 0))
        hdr = tk.Frame(win, bg=C["panel"])
        hdr.pack(fill="x")
        tk.Label(hdr, text="◆  UPDATE AVAILABLE  ◆", bg=C["panel"],
                 fg=C["gold_lt"],
                 font=("Segoe UI", 13, "bold")).pack(pady=12)
        tk.Frame(win, bg=C["gold_dk"], height=1).pack(fill="x")
        tk.Frame(win, bg=C["gold"], height=1).pack(fill="x", pady=(2, 0))

        body = tk.Frame(win, bg=C["bg"])
        body.pack(fill="both", expand=True, padx=20, pady=14)

        tk.Label(body,
                 text=f"v{__version__}  →  v{version}",
                 bg=C["bg"], fg=C["gold"],
                 font=("Segoe UI", 14, "bold")).pack(anchor="w")
        if size:
            tk.Label(body,
                     text=f"Download size: {size / (1024*1024):.1f} MB",
                     bg=C["bg"], fg=C["txt_dim"],
                     font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 8))

        # Release notes
        notes_text = notes or "(No release notes provided.)"
        tk.Label(body, text="WHAT'S NEW", bg=C["bg"], fg=C["gold_dk"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(4, 4))

        notes_box = tk.Text(body, bg=C["panel"], fg=C["txt"],
                            font=("Segoe UI", 9),
                            relief="flat", height=10, wrap="word",
                            highlightthickness=1,
                            highlightbackground=C["border"],
                            padx=8, pady=6)
        notes_box.pack(fill="both", expand=True)
        notes_box.insert("1.0", notes_text)
        notes_box.configure(state="disabled")

        # Status line for download progress
        self.update_status_var = tk.StringVar(value="")
        status = tk.Label(body, textvariable=self.update_status_var,
                          bg=C["bg"], fg=C["blue_lt"],
                          font=("Segoe UI", 9))
        status.pack(anchor="w", pady=(8, 0))

        # Buttons
        btns = tk.Frame(body, bg=C["bg"])
        btns.pack(fill="x", pady=(10, 0))

        later_btn = self._btn(btns, "LATER", win.destroy, w=10, s="dim")
        later_btn.pack(side="right", padx=(8, 0))
        update_btn = self._btn(btns, "UPDATE NOW",
                                lambda: self._start_update_download(
                                    win, download_url, version,
                                    later_btn, update_btn),
                                w=14, s="accent")
        update_btn.pack(side="right")

    def _start_update_download(self, dialog, download_url, version,
                                later_btn, update_btn):
        """Lock buttons and start the download in a background thread."""
        try:
            update_btn.configure(state="disabled", text="DOWNLOADING...")
            later_btn.configure(state="disabled")
        except Exception:
            pass
        self.update_status_var.set("Connecting to GitHub...")
        self.jobs.submit("download_update",
                         lambda c, d=dialog, u=download_url, v=version:
                         self._download_and_install_bg(d, u, v))

    def _download_and_install_bg(self, dialog, download_url, version):
        """Download the new .exe and trigger the swap-and-restart."""
        try:
            import urllib.request
            import tempfile

            tmpdir = tempfile.gettempdir()
            new_exe_path = os.path.join(tmpdir, f"LoLPowerRankings_v{version}.exe")

            req = urllib.request.Request(
                download_url,
                headers={"User-Agent": "LoLPowerRankings-Updater"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                downloaded = 0
                chunk = 64 * 1024
                with open(new_exe_path, "wb") as f:
                    while True:
                        buf = resp.read(chunk)
                        if not buf:
                            break
                        f.write(buf)
                        downloaded += len(buf)
                        if total > 0:
                            pct = (downloaded / total) * 100
                            mb_done = downloaded / (1024 * 1024)
                            mb_total = total / (1024 * 1024)
                            self.after(0, self.update_status_var.set,
                                       f"Downloading... {pct:.0f}%  "
                                       f"({mb_done:.1f} / {mb_total:.1f} MB)")
                        else:
                            mb_done = downloaded / (1024 * 1024)
                            self.after(0, self.update_status_var.set,
                                       f"Downloading... {mb_done:.1f} MB")

            self.after(0, self.update_status_var.set,
                       "Download complete. Installing...")
            self.after(400, lambda: self._install_update(new_exe_path))

        except Exception as e:
            self.after(0, self.update_status_var.set,
                       f"Update failed: {e}")
            self.log(f"Update failed: {e}\n", "red")

    def _install_update(self, new_exe_path):
        """Swap the running .exe with the downloaded one and relaunch.

        Uses a PowerShell helper script instead of a batch file.
        PowerShell's System.IO.File::Open reliably detects the file lock,
        unlike cmd's >> redirection which does not set errorlevel on failure.
        """
        try:
            import tempfile
            current_exe = sys.executable
            log_path = os.path.join(tempfile.gettempdir(), "lolpr_update.log")
            ps_path = os.path.join(tempfile.gettempdir(), "lolpr_update.ps1")

            src = new_exe_path.replace("\\", "\\\\")
            dst = current_exe.replace("\\", "\\\\")
            log = log_path.replace("\\", "\\\\")

            ps_lines = [
                '$ErrorActionPreference = "SilentlyContinue"',
                f'$src = "{src}"',
                f'$dst = "{dst}"',
                f'$log = "{log}"',
                'Add-Content $log "=== LoL PR update started $(Get-Date) ==="',
                '',
                '# Poll until the exe file lock is released (up to 40 s).',
                '# System.IO.File::Open with Write access is the reliable',
                '# way to test this — cmd.exe >> does not set errorlevel.',
                '$unlocked = $false',
                'for ($i = 0; $i -lt 40; $i++) {',
                '    try {',
                '        $s = [System.IO.File]::Open($dst, "Open", "Write", "None")',
                '        $s.Close()',
                '        $unlocked = $true',
                '        break',
                '    } catch {',
                '        Start-Sleep -Seconds 1',
                '    }',
                '}',
                '',
                'if (-not $unlocked) {',
                '    Add-Content $log "ERROR: timed out waiting for lock release"',
                '    Write-Host "Update failed: app did not release the file lock."',
                '    Write-Host "New version is at: $src"',
                '    Read-Host "Press Enter to close"',
                '    exit 1',
                '}',
                '',
                'Add-Content $log "File unlocked after $i s. Moving..."',
                '',
                '# Replace the exe, retry up to 5 times.',
                '$moved = $false',
                'for ($j = 0; $j -lt 5; $j++) {',
                '    try {',
                '        Move-Item -Force $src $dst',
                '        $moved = $true',
                '        break',
                '    } catch {',
                '        Add-Content $log "Move attempt $j failed: $_"',
                '        Start-Sleep -Seconds 2',
                '    }',
                '}',
                '',
                'if ($moved) {',
                '    Add-Content $log "Move succeeded."',
                '    Write-Host "Update complete! Launch LoL Power Rankings to use the new version."',
                '    Start-Sleep -Seconds 3',
                '    Add-Content $log "Done."',
                '} else {',
                '    Add-Content $log "ERROR: all move attempts failed"',
                '    Write-Host "Update failed: could not replace the exe."',
                '    Write-Host "New version is at: $src"',
                '    Read-Host "Press Enter to close"',
                '}',
            ]

            with open(ps_path, "w", encoding="utf-8") as f:
                f.write("\n".join(ps_lines))

            import subprocess
            CREATE_NEW_PROCESS_GROUP = 0x00000200
            CREATE_NEW_CONSOLE = 0x00000010
            flags = CREATE_NEW_CONSOLE | CREATE_NEW_PROCESS_GROUP
            subprocess.Popen(
                ["powershell.exe", "-ExecutionPolicy", "Bypass",
                 "-File", ps_path],
                creationflags=flags)

            self.update_status_var.set("Update downloaded. Closing — relaunch the app to use the new version.")
            self.after(800, self._quit_for_update)

        except Exception as e:
            self.update_status_var.set(f"Install failed: {e}")
            self.log(f"Install failed: {e}\n", "red")

    def _quit_for_update(self):
        """Gracefully exit so the PyInstaller bootloader can release its
        file lock. Avoid os._exit() — it kills Python before the bootloader
        can clean up, which extends the lock window.
        """
        try:
            if self.proc and self.proc.poll() is None:
                self.proc.terminate()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass
        # sys.exit lets the bootloader cleanup run, releasing the .exe lock
        # within a second or two. The batch script's wait loop handles the
        # rest of the timing.
        sys.exit(0)

    # ── Build Your Tier List Tab ──────────────────────────────

    _RATING_VALUES = {"S": 6, "A": 5, "B": 4, "C": 3, "D": 2, "F": 1}
    _RATING_COLORS_BTL = {
        "S": "#C8463C",   # crimson
        "A": "#C89B3C",   # warm gold
        "B": "#A0884E",   # muted brass
        "C": "#5C8A5C",   # sage
        "D": "#5C7A9C",   # steel blue
        "F": "#6E6E6E",   # gray
    }

    def build_rating_tab(self):
        """Set up the 'Build Your Tier List' scrollable tab."""
        canvas = tk.Canvas(self.tab_rating, bg=C["bg"], highlightthickness=0)
        scrollbar = tk.Scrollbar(self.tab_rating, orient="vertical",
                                 command=canvas.yview)
        self.rating_frame = tk.Frame(canvas, bg=C["bg"])

        self.rating_frame.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        wid = canvas.create_window((0, 0), window=self.rating_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.bind("<Configure>",
            lambda e, w=wid: canvas.itemconfigure(w, width=e.width))

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        self._bind_canvas_scroll(canvas, self.tab_rating)
        self.rating_canvas = canvas

        # State
        self.rating_self = None        # display name of the rater
        self.rating_targets = []       # list of display names to rate
        self.rating_index = 0          # current target index
        self.rating_existing = {}      # ratee_display_name -> existing rating ('S'..'F')
        self.rating_col_index = None   # 1-based column index in Tier Lists sheet
        self.rating_var = tk.StringVar()
        self.rating_status_var = tk.StringVar(value="")
        self.rating_progress_var = tk.StringVar(value="")
        self.rating_show_scout = tk.BooleanVar(value=True)

        self._show_rating_intro()

    # ── Rating: intro / start screen ──

    def _show_rating_intro(self):
        """Initial screen: a START button that triggers LCU detection."""
        for w in self.rating_frame.winfo_children():
            w.destroy()
        f = self.rating_frame

        # Title
        self._tab_title(f, "RATE", "BUILD YOUR TIER LIST")

        intro = tk.Frame(f, bg=C["bg"])
        intro.pack(fill="x", padx=20, pady=40)

        # Hero card
        card = tk.Frame(intro, bg=C["panel"], highlightthickness=1,
                        highlightbackground=C["gold_dk"])
        card.pack(fill="x")

        tk.Label(card, text="◆  RATE YOUR PEERS  ◆",
                 bg=C["panel"], fg=C["gold_lt"],
                 font=("Segoe UI", 16, "bold")).pack(pady=(20, 6))
        tk.Label(card,
                 text="Walk through every player on the tier list and rate them S to F.",
                 bg=C["panel"], fg=C["txt"],
                 font=("Segoe UI", 10)).pack(pady=(0, 4))
        tk.Label(card,
                 text="Each rater fills their own column in the shared sheet.",
                 bg=C["panel"], fg=C["txt2"],
                 font=("Segoe UI", 9, "italic")).pack(pady=(0, 18))

        btn = tk.Button(card, text="START RATING",
                        command=self._start_rating_flow,
                        bg=C["blue_dk"], fg=C["gold_lt"],
                        activebackground=C["blue"],
                        activeforeground=C["gold_lt"],
                        font=("Segoe UI", 12, "bold"),
                        relief="flat", bd=0, cursor="hand2",
                        padx=28, pady=10,
                        highlightthickness=2,
                        highlightbackground=C["gold_dk"])
        btn.pack(pady=(0, 18))

        def _be(_e):
            try: btn.configure(bg=C["blue"])
            except Exception: pass
        def _bl(_e):
            try: btn.configure(bg=C["blue_dk"])
            except Exception: pass
        btn.bind("<Enter>", _be)
        btn.bind("<Leave>", _bl)

        # Scout toggle
        opt_row = tk.Frame(card, bg=C["panel"])
        opt_row.pack(pady=(0, 8))
        tk.Checkbutton(
            opt_row, text="Display Scouting Report",
            variable=self.rating_show_scout,
            bg=C["panel"], fg=C["txt"], selectcolor=C["bg"],
            activebackground=C["panel"], activeforeground=C["gold_lt"],
            font=("Segoe UI", 10),
        ).pack()

        tk.Label(card,
                 text="Make sure your League client is running before starting.",
                 bg=C["panel"], fg=C["txt_dim"],
                 font=("Segoe UI", 9, "italic")).pack(pady=(0, 18))

    def _start_rating_flow(self):
        """Kick off the LCU lookup + sheet preload."""
        self._show_rating_loading("Connecting to League client...")
        self.jobs.submit("rating_init", lambda c: self._rating_init_bg())

    def _show_rating_loading(self, msg):
        for w in self.rating_frame.winfo_children():
            w.destroy()
        f = self.rating_frame

        self._tab_title(f, "RATE", "BUILD YOUR TIER LIST")

        outer = tk.Frame(f, bg=C["bg"])
        outer.pack(fill="x", padx=20, pady=60)
        card = tk.Frame(outer, bg=C["panel"], highlightthickness=1,
                        highlightbackground=C["gold_dk"])
        card.pack(fill="x")
        tk.Label(card, text="WORKING", bg=C["panel"], fg=C["gold_dk"],
                 font=("Segoe UI", 9, "bold")).pack(pady=(22, 4))
        tk.Label(card, text=msg, bg=C["panel"], fg=C["blue_lt"],
                 font=("Segoe UI", 13, "bold"), wraplength=600,
                 justify="center").pack(pady=(0, 22), padx=20)

    def _show_rating_error(self, msg, retry=True):
        for w in self.rating_frame.winfo_children():
            w.destroy()
        f = self.rating_frame
        self._tab_title(f, "RATE", "BUILD YOUR TIER LIST")

        outer = tk.Frame(f, bg=C["bg"])
        outer.pack(fill="x", padx=20, pady=40)
        card = tk.Frame(outer, bg="#261212", highlightthickness=1,
                        highlightbackground="#7C2A20")
        card.pack(fill="x")
        stripe = tk.Frame(card, bg="#C84B31", width=4)
        stripe.pack(side="left", fill="y")
        stripe.pack_propagate(False)
        body = tk.Frame(card, bg="#261212")
        body.pack(side="left", fill="x", expand=True, padx=14, pady=14)
        tk.Label(body, text=msg, bg="#261212", fg="#E07060",
                 font=("Segoe UI", 11), wraplength=700,
                 justify="left").pack(anchor="w")
        if retry:
            btn = self._btn(body, "TRY AGAIN", self._show_rating_intro,
                            w=14, s="dim")
            btn.pack(anchor="w", pady=(12, 0))

    def _rating_init_bg(self):
        """Background work: detect summoner, find their entry, load sheet."""
        # Step 1: connect to LCU
        self.after(0, self._show_rating_loading,
                   "Connecting to League client...")
        try:
            game_name = self._lcu_get_summoner_game_name()
        except Exception as e:
            self.after(0, self._show_rating_error,
                       f"Couldn't reach the League client. "
                       f"Make sure it's running, then try again.\n\n{e}")
            return

        if not game_name:
            self.after(0, self._show_rating_error,
                       "Couldn't reach the League client. "
                       "Make sure it's running, then try again.")
            return

        # Step 2: cross-reference with Players sheet via Riot game-name
        if not self.riot_to_display:
            # Roster hasn't loaded yet; wait briefly for the players bg thread
            self.after(0, self._show_rating_loading,
                       "Loading roster from Google Sheet...")
            for _ in range(15):  # up to ~7.5s
                if self.riot_to_display:
                    break
                time.sleep(0.5)

        rater_display = self.riot_to_display.get(game_name.lower())
        if not rater_display:
            self.after(0, self._show_rating_error,
                       f"Your in-game name '{game_name}' isn't on the tier "
                       f"list yet. Add yourself via 'Join The Tier List' "
                       f"first, then come back here.")
            return

        # Step 3: Load Tier Lists sheet, find rater's column, load existing ratings
        self.after(0, self._show_rating_loading,
                   f"Loading tier list... welcome, {rater_display}")
        try:
            ws, col_index, existing = self._load_tier_list_state(rater_display)
        except Exception as e:
            self.after(0, self._show_rating_error,
                       f"Couldn't load Tier Lists sheet from Google.\n\n{e}")
            return

        if col_index is None:
            self.after(0, self._show_rating_error,
                       "The Tier Lists sheet is full — all 25 rater "
                       "columns are taken. Talk to the admin to make room.")
            return

        # Step 4: Build target list (everyone on the roster, in sheet order)
        targets = list(self.player_list)

        self.rating_self = rater_display
        self.rating_col_index = col_index
        self.rating_targets = targets
        self.rating_existing = existing
        self.rating_index = 0

        # Skip past players who've already been rated, so the user lands
        # on the first un-rated one instead of having to click through
        # all their previous picks.
        for i, name in enumerate(targets):
            if name not in existing:
                self.rating_index = i
                break
        else:
            # All players already rated — start at the beginning so they
            # can review/change their picks
            self.rating_index = 0

        self.after(0, self._render_rating_view)

    def _lcu_get_summoner_game_name(self):
        """Return the Riot game-name of the currently-logged-in summoner.

        Reuses the same lockfile approach as inhouse_tracker but inlined here
        so the launcher can call it directly without subprocess overhead.
        """
        # Only meaningful on Windows / macOS — friends ship the .exe to Windows.
        # We still try cross-platform paths in case someone runs from source.
        paths = []
        if sys.platform == "win32":
            for d in ["C", "D", "E"]:
                paths.extend([
                    f"{d}:\\Riot Games\\League of Legends\\lockfile",
                    f"{d}:\\Program Files\\Riot Games\\League of Legends\\lockfile",
                    f"{d}:\\Program Files (x86)\\Riot Games\\League of Legends\\lockfile",
                ])
        elif sys.platform == "darwin":
            paths.append(
                "/Applications/League of Legends.app/Contents/LoL/lockfile")

        lockfile_path = None
        for p in paths:
            if os.path.exists(p):
                lockfile_path = p
                break

        # Fallback — try wmic to find the running client
        if not lockfile_path and sys.platform == "win32":
            try:
                out = subprocess.check_output(
                    'wmic process where "name=\'LeagueClientUx.exe\'" '
                    'get commandline',
                    shell=True, text=True, stderr=subprocess.DEVNULL)
                m = re.search(r'"([^"]*LeagueClientUx\.exe)"', out)
                if m:
                    lf = os.path.join(os.path.dirname(m.group(1)), "lockfile")
                    if os.path.exists(lf):
                        lockfile_path = lf
            except Exception:
                pass

        if not lockfile_path:
            return None

        with open(lockfile_path) as f:
            parts = f.read().strip().split(":")
        if len(parts) < 5:
            return None

        base = f"{parts[4]}://127.0.0.1:{parts[2]}"
        auth = ("riot", parts[3])

        try:
            import requests
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            r = requests.get(f"{base}/lol-summoner/v1/current-summoner",
                             auth=auth, verify=False, timeout=5)
            if r.status_code == 200:
                s = r.json()
                return s.get("gameName") or s.get("displayName") or None
        except Exception:
            pass
        return None

    # Rater columns live between B (Player Name) and the computed columns
    # (Avg Score / Normalized / tier-legend). The roster caps at 25 players,
    # which means rater columns occupy C through AA (column indices 3..27).
    _RATER_COL_FIRST = 3   # Column C (1-based)
    _RATER_COL_LAST = 27   # Column AA (1-based) — 25 slots total

    def _load_tier_list_state(self, rater_display):
        """Open the Tier Lists sheet and return (ws, col_index, existing_ratings).

        If the rater doesn't yet have a column on the sheet, claim the first
        empty rater slot for them (writes their display name into the
        header row). This way new players from 'Join The Tier List' get a
        rating column the first time they open this tab.

        - col_index is 1-based (gspread convention) for the rater's column
        - existing_ratings is {ratee_display_name: 'S'|'A'|...}
        - Returns (ws, None, {}) when:
            - The sheet is unreadable
            - The 25-rater cap is reached and we couldn't claim a slot
        """
        import gspread
        from google.oauth2.service_account import Credentials
        cfg = self.config
        creds = Credentials.from_service_account_file(
            cfg["creds_path"],
            scopes=["https://www.googleapis.com/auth/spreadsheets",
                     "https://www.googleapis.com/auth/drive"])
        gc = gspread.authorize(creds)
        if "docs.google.com" in cfg["sheet_url"]:
            ss = gc.open_by_url(cfg["sheet_url"])
        else:
            ss = gc.open(cfg["sheet_url"])

        ws = ss.worksheet("Tier Lists")
        values = cached_get_all_values(ws)
        if len(values) < 4:
            return ws, None, {}

        header_row = values[2]
        rater_lower = rater_display.lower()

        # Pass 1 — does the rater already have a column?
        col_index = self._find_rater_column(header_row, rater_lower)

        # Pass 2 — if not, try to claim the first empty rater slot
        if col_index is None:
            col_index = self._claim_rater_column(ws, header_row,
                                                  rater_display)
            if col_index is None:
                return ws, None, {}
            # Re-fetch the sheet so we read back any header we just wrote
            # (ensures existing-ratings parsing operates on the latest view)
            values = cached_get_all_values(ws)

        # Walk player rows (starting at row 4 = index 3); read existing ratings
        existing = {}
        for row in values[3:]:
            if len(row) < 2:
                continue
            name = str(row[1]).strip()
            if not name or name.lower() == "player name":
                continue
            cell = (row[col_index - 1]
                    if col_index - 1 < len(row) else "").strip()
            if cell in self._RATING_VALUES:
                existing[name] = cell

        return ws, col_index, existing

    def _find_rater_column(self, header_row, rater_lower):
        """Return the 1-based column index for `rater_lower` in the header
        row, or None if not present. Only considers the rater range
        (columns C through AA)."""
        for i, cell in enumerate(header_row):
            col_1based = i + 1
            if (col_1based < self._RATER_COL_FIRST or
                    col_1based > self._RATER_COL_LAST):
                continue
            if str(cell).strip().lower() == rater_lower:
                return col_1based
        return None

    def _claim_rater_column(self, ws, header_row, rater_display):
        """Find the first empty rater slot and write `rater_display` into it.

        Returns the 1-based column index that was claimed, or None if all
        25 slots are taken. An "empty" slot is one where the header is
        blank or equals 'Player Name' (the placeholder text shipped with
        the sheet template).
        """
        target_col = None
        for i in range(self._RATER_COL_FIRST - 1, self._RATER_COL_LAST):
            cell = (str(header_row[i]).strip()
                    if i < len(header_row) else "")
            if not cell or cell.lower() == "player name":
                target_col = i + 1  # 1-based
                break

        if target_col is None:
            self.log(
                "Tier Lists sheet is full (25 raters max). "
                "Talk to the admin to make room.\n", "red")
            return None

        # Write the rater's display name into the header cell. We only
        # touch this single cell — the rest of the column (placeholder F
        # values down to row N) is left alone. Subsequent _submit_rating_bg
        # calls will overwrite individual cells with the rater's picks.
        col_letter = self._col_index_to_letter(target_col)
        cell_a1 = f"{col_letter}3"
        try:
            sheets_retry(ws.update, values=[[rater_display]], range_name=cell_a1)
            invalidate_sheet_cache(ws)
            self.log(
                f"Claimed Tier Lists column {col_letter} for {rater_display}.\n",
                "green")
        except Exception as e:
            self.log(f"Failed to claim Tier Lists column: {e}\n", "red")
            return None

        return target_col

    # ── Rating: per-player rating view ──

    def _render_rating_view(self):
        """Show the current player's scouting report + rating dropdown."""
        for w in self.rating_frame.winfo_children():
            w.destroy()
        f = self.rating_frame

        # Sticky top bar — cinematic: stacked eyebrow + name, gold progress bar below
        tk.Frame(f, bg=C["gold"], height=2).pack(fill="x")
        hdr = tk.Frame(f, bg=C["panel"])
        hdr.pack(fill="x")

        # Two-column layout: rating-as (left) | progress (right)
        rating_as = tk.Frame(hdr, bg=C["panel"])
        rating_as.pack(fill="x", padx=22, pady=14)

        # LEFT — RATING AS / NAME stacked
        left = tk.Frame(rating_as, bg=C["panel"])
        left.pack(side="left")
        tk.Label(left, text="RATING AS",
                 bg=C["panel"], fg=C["gold_dk"],
                 font=("Segoe UI", 9, "bold")).pack(anchor="w")
        tk.Label(left, text=str(self.rating_self).upper(),
                 bg=C["panel"], fg=C["gold_lt"],
                 font=("Segoe UI", 16, "bold")).pack(anchor="w", pady=(2, 0))

        # CENTER — Skip to player
        center = tk.Frame(rating_as, bg=C["panel"])
        center.pack(side="left", padx=30)
        tk.Label(center, text="SKIP TO",
                 bg=C["panel"], fg=C["gold_dk"],
                 font=("Segoe UI", 9, "bold")).pack(anchor="w")
        skip_var = tk.StringVar(value=self.rating_targets[self.rating_index]
                                if self.rating_targets else "")
        skip_menu = tk.OptionMenu(center, skip_var, *self.rating_targets)
        skip_menu.configure(
            bg=C["panel_2"], fg=C["txt"], font=("Segoe UI", 9),
            activebackground=C["strip"], activeforeground=C["gold_lt"],
            relief="flat", bd=0, highlightthickness=1,
            highlightbackground=C["gold_dk"], width=16)
        skip_menu["menu"].configure(bg=C["panel_2"], fg=C["txt"],
                                    activebackground=C["strip"],
                                    activeforeground=C["gold_lt"],
                                    font=("Segoe UI", 9))
        skip_menu.pack(anchor="w", pady=(4, 0))

        def _do_skip(*_):
            name = skip_var.get()
            if name in self.rating_targets:
                self.rating_index = self.rating_targets.index(name)
                self.rating_status_var.set("")
                self._render_rating_view()
        skip_var.trace_add("write", _do_skip)

        # RIGHT — PROGRESS / "PLAYER X / Y" stacked
        total = len(self.rating_targets)
        cur = self.rating_index + 1
        right = tk.Frame(rating_as, bg=C["panel"])
        right.pack(side="right")
        tk.Label(right, text="PROGRESS",
                 bg=C["panel"], fg=C["gold_dk"],
                 font=("Segoe UI", 9, "bold")).pack(anchor="e")
        tk.Label(right, text=f"PLAYER {cur} / {total}",
                 bg=C["panel"], fg=C["gold"],
                 font=("Segoe UI", 14, "bold")).pack(anchor="e", pady=(2, 0))

        tk.Frame(f, bg=C["gold_dk"], height=1).pack(fill="x")

        # Progress bar — gold fill on rule track, 4px tall
        progress_track = tk.Frame(f, bg=C["rule"], height=4)
        progress_track.pack(fill="x", padx=22, pady=(0, 0))
        progress_track.pack_propagate(False)
        # Filled portion (uses .place to size proportionally)
        progress_fill = tk.Frame(progress_track, bg=C["gold"])
        try:
            pct = max(0.02, min(1.0, cur / max(total, 1)))
        except (ZeroDivisionError, TypeError):
            pct = 0.02
        progress_fill.place(relx=0, rely=0, relwidth=pct, relheight=1)

        # Body container
        body = tk.Frame(f, bg=C["bg"])
        body.pack(fill="x", padx=16, pady=(8, 0))

        if not self.rating_targets:
            tk.Label(body, text="No players to rate.",
                     bg=C["bg"], fg=C["txt_dim"],
                     font=("Segoe UI", 11)).pack(pady=40)
            return

        target_name = self.rating_targets[self.rating_index]

        # Skip self and show notice
        if target_name == self.rating_self:
            self._render_rating_self_notice(body, target_name)
            return

        # Scouting report container (only when checkbox is on)
        if self.rating_show_scout.get():
            scout_box = tk.Frame(body, bg=C["bg"])
            scout_box.pack(fill="x", pady=(0, 12))
            tk.Label(scout_box,
                     text=f"Loading scouting report for {target_name}...",
                     bg=C["bg"], fg=C["txt_dim"],
                     font=("Segoe UI", 10, "italic")).pack(pady=20)
            self.jobs.submit("rating_load_scout",
                             lambda c, n=target_name, b=scout_box:
                             self._rating_load_scout_bg(n, b))

        # Rating dropdown card (always visible, even while scouting loads)
        self._render_rating_controls(body, target_name)

    def _render_rating_self_notice(self, body, name):
        """Special view for the rater's own row — they shouldn't rate themselves."""
        card = tk.Frame(body, bg=C["panel"], highlightthickness=1,
                        highlightbackground=C["gold_dk"])
        card.pack(fill="x", pady=12)
        stripe = tk.Frame(card, bg=C["gold"], width=4)
        stripe.pack(side="left", fill="y")
        stripe.pack_propagate(False)

        inner = tk.Frame(card, bg=C["panel"])
        inner.pack(side="left", fill="x", expand=True, padx=18, pady=18)
        tk.Label(inner, text=f"◆  THIS IS YOU  ◆",
                 bg=C["panel"], fg=C["gold_lt"],
                 font=("Segoe UI", 14, "bold")).pack(anchor="w")
        tk.Label(inner,
                 text="You can rate yourself if you want, or skip ahead "
                      "to the next player.",
                 bg=C["panel"], fg=C["txt"],
                 font=("Segoe UI", 10)).pack(anchor="w", pady=(4, 0))

        # Reuse the rating controls card
        self._render_rating_controls(body, name)

    def _render_rating_controls(self, body, target_name):
        """The rate/save card with S/A/B/C/D/F dropdown + nav buttons."""
        existing = self.rating_existing.get(target_name, "")
        self.rating_var.set(existing)

        ctl_card = tk.Frame(body, bg=C["panel"], highlightthickness=1,
                            highlightbackground=C["gold_dk"])
        ctl_card.pack(fill="x", pady=(8, 12))

        title_bar = tk.Frame(ctl_card, bg=C["strip"])
        title_bar.pack(fill="x")

        # LEFT — RATE / NAME stacked
        tb_left = tk.Frame(title_bar, bg=C["strip"])
        tb_left.pack(side="left", padx=18, pady=12)
        tk.Label(tb_left, text="RATE", bg=C["strip"], fg=C["gold"],
                 font=("Segoe UI", 10, "bold")).pack(anchor="w")
        tk.Label(tb_left, text=str(target_name).upper(),
                 bg=C["strip"], fg=C["gold_lt"],
                 font=("Segoe UI", 18, "bold")).pack(anchor="w", pady=(2, 0))

        # RIGHT — current rating stacked
        if existing:
            tb_right = tk.Frame(title_bar, bg=C["strip"])
            tb_right.pack(side="right", padx=18, pady=12)
            tk.Label(tb_right, text="YOUR CURRENT RATING",
                     bg=C["strip"], fg=C["gold_dk"],
                     font=("Segoe UI", 9, "bold")).pack(anchor="e")
            cur_color = self._RATING_COLORS_BTL.get(existing, C["gold"])
            tk.Label(tb_right, text=existing, bg=C["strip"], fg=cur_color,
                     font=("Segoe UI", 18, "bold")).pack(anchor="e", pady=(2, 0))

        # Bottom rule under titlebar
        tk.Frame(ctl_card, bg=C["rule"], height=1).pack(fill="x")

        inner = tk.Frame(ctl_card, bg=C["panel"])
        inner.pack(fill="x", padx=16, pady=14)

        # Big colored S/A/B/C/D/F buttons in a row — cinematic 84x84 scale
        btn_row = tk.Frame(inner, bg=C["panel"])
        btn_row.pack(pady=(8, 4))

        for tier in ["S", "A", "B", "C", "D", "F"]:
            color = self._RATING_COLORS_BTL[tier]
            is_selected = (existing == tier)
            bg = color if is_selected else C["panel"]
            fg = C["txt_dk"] if is_selected else color
            border = color
            btn = tk.Button(btn_row, text=tier,
                            bg=bg, fg=fg,
                            activebackground=color,
                            activeforeground=C["txt_dk"],
                            font=("Segoe UI", 28, "bold"),
                            relief="flat", bd=0, cursor="hand2",
                            width=3, padx=6, pady=18,
                            highlightthickness=2,
                            highlightbackground=border,
                            command=lambda t=tier:
                                self._submit_rating(target_name, t))
            btn.pack(side="left", padx=6)

        # Status line for save feedback
        status = tk.Label(inner, textvariable=self.rating_status_var,
                          bg=C["panel"], fg=C["teal"],
                          font=("Segoe UI", 9, "italic"))
        status.pack(pady=(14, 0))

        # Nav buttons
        nav = tk.Frame(inner, bg=C["panel"])
        nav.pack(fill="x", pady=(14, 0))

        prev_btn = self._btn(nav, "← PREVIOUS",
                              self._rating_prev,
                              w=14, s="dim")
        prev_btn.pack(side="left")
        if self.rating_index <= 0:
            try: prev_btn.configure(state="disabled")
            except Exception: pass

        skip_btn = self._btn(nav, "SKIP →",
                              self._rating_next,
                              w=14, s="dim")
        skip_btn.pack(side="right")

    def _rating_load_scout_bg(self, target_name, scout_box):
        """Fetch and render the scouting report for `target_name`."""
        try:
            import gspread
            from google.oauth2.service_account import Credentials
            cfg = self.config
            creds = Credentials.from_service_account_file(
                cfg["creds_path"],
                scopes=["https://www.googleapis.com/auth/spreadsheets",
                         "https://www.googleapis.com/auth/drive"])
            gc = gspread.authorize(creds)
            if "docs.google.com" in cfg["sheet_url"]:
                ss = gc.open_by_url(cfg["sheet_url"])
            else:
                ss = gc.open(cfg["sheet_url"])

            sheet_name = f"Scout - {target_name}"[:30]
            try:
                ws = ss.worksheet(sheet_name)
            except Exception:
                self.after(0, self._render_rating_no_scout,
                           scout_box, target_name)
                return

            data = self._parse_scouting_sheet(ws)
            self.after(0, self._render_rating_with_scout,
                       scout_box, data)
        except Exception as e:
            self.after(0, self._render_rating_scout_error,
                       scout_box, str(e))

    def _render_rating_with_scout(self, scout_box, data):
        """Drop the parsed scouting report into `scout_box`."""
        if not scout_box.winfo_exists():
            return  # User navigated away
        for w in scout_box.winfo_children():
            w.destroy()
        # Reuse the scouting tab's renderer
        self._display_scouting_results(data, parent=scout_box)

    def _render_rating_no_scout(self, scout_box, target_name):
        if not scout_box.winfo_exists():
            return
        for w in scout_box.winfo_children():
            w.destroy()
        card = tk.Frame(scout_box, bg=C["panel"], highlightthickness=1,
                        highlightbackground=C["gold_dk"])
        card.pack(fill="x", pady=8)
        tk.Label(card,
                 text=f"No scouting report yet for {target_name}.",
                 bg=C["panel"], fg=C["gold"],
                 font=("Segoe UI", 13, "bold")).pack(pady=(20, 4))
        tk.Label(card,
                 text="You can still rate them based on what you know — "
                      "or skip them and come back later.",
                 bg=C["panel"], fg=C["txt2"],
                 font=("Segoe UI", 9, "italic"),
                 wraplength=600).pack(pady=(0, 20))

    def _render_rating_scout_error(self, scout_box, err):
        if not scout_box.winfo_exists():
            return
        for w in scout_box.winfo_children():
            w.destroy()
        tk.Label(scout_box,
                 text=f"Couldn't load scouting report: {err}",
                 bg=C["bg"], fg=C["red"],
                 font=("Segoe UI", 10),
                 wraplength=700).pack(pady=14)

    def _submit_rating(self, target_name, tier):
        """Write the selected rating to the sheet and advance."""
        self.rating_status_var.set(f"Saving {tier}...")
        self.jobs.submit("submit_rating",
                         lambda c, n=target_name, t=tier:
                         self._submit_rating_bg(n, t))

    def _submit_rating_bg(self, target_name, tier):
        try:
            import gspread
            from google.oauth2.service_account import Credentials
            cfg = self.config
            creds = Credentials.from_service_account_file(
                cfg["creds_path"],
                scopes=["https://www.googleapis.com/auth/spreadsheets",
                         "https://www.googleapis.com/auth/drive"])
            gc = gspread.authorize(creds)
            if "docs.google.com" in cfg["sheet_url"]:
                ss = gc.open_by_url(cfg["sheet_url"])
            else:
                ss = gc.open(cfg["sheet_url"])

            ws = ss.worksheet("Tier Lists")
            # Find the row for `target_name`. Re-fetch to be safe — someone
            # else might have just added a new player via Join The Tier List.
            values = cached_get_all_values(ws)
            target_row = None
            target_lower = target_name.lower()
            for idx, row in enumerate(values[3:], start=4):  # 1-based sheet row
                if (len(row) >= 2 and
                        str(row[1]).strip().lower() == target_lower):
                    target_row = idx
                    break

            if target_row is None:
                self.after(0, self.rating_status_var.set,
                           f"Couldn't find '{target_name}' in the sheet.")
                return

            # Translate (row, col_index) into A1 notation
            col_letter = self._col_index_to_letter(self.rating_col_index)
            cell_a1 = f"{col_letter}{target_row}"
            sheets_retry(ws.update, values=[[tier]], range_name=cell_a1)
            invalidate_sheet_cache(ws)

            # Update local state
            self.rating_existing[target_name] = tier
            self.after(0, self._rating_after_save, target_name, tier)
        except Exception as e:
            self.after(0, self.rating_status_var.set, f"Save failed: {e}")

    def _rating_after_save(self, target_name, tier):
        """Show a brief confirmation then advance to the next player."""
        self.rating_status_var.set(f"✓ Saved {target_name} → {tier}")
        self.log(f"Rated {target_name} as {tier}\n", "green")
        # Auto-advance after a short pause so the confirmation is visible
        self.after(700, self._rating_next)

    def _col_index_to_letter(self, n):
        """Convert 1-based column index → spreadsheet letter (1=A, 27=AA)."""
        result = ""
        while n > 0:
            n, rem = divmod(n - 1, 26)
            result = chr(ord("A") + rem) + result
        return result

    def _rating_prev(self):
        if self.rating_index > 0:
            self.rating_index -= 1
            self.rating_status_var.set("")
            self._render_rating_view()

    def _rating_next(self):
        if self.rating_index < len(self.rating_targets) - 1:
            self.rating_index += 1
            self.rating_status_var.set("")
            self._render_rating_view()
        else:
            # End of list
            self.rating_status_var.set("")
            self._render_rating_complete()

    def _render_rating_complete(self):
        """Final screen: your ratings summary + nav."""
        for w in self.rating_frame.winfo_children():
            w.destroy()
        f = self.rating_frame

        self._tab_title(f, "RATE", "BUILD YOUR TIER LIST")

        # Summary header card
        outer = tk.Frame(f, bg=C["bg"])
        outer.pack(fill="x", padx=20, pady=(30, 10))
        card = tk.Frame(outer, bg=C["panel"], highlightthickness=2,
                        highlightbackground=C["gold"])
        card.pack(fill="x")
        tk.Label(card, text="◆  ALL DONE  ◆",
                 bg=C["panel"], fg=C["gold_lt"],
                 font=("Segoe UI", 18, "bold")).pack(pady=(20, 6))

        rated_count = sum(1 for n in self.rating_targets
                           if n in self.rating_existing)
        tk.Label(card,
                 text=f"You've rated {rated_count} of "
                      f"{len(self.rating_targets)} players.",
                 bg=C["panel"], fg=C["txt"],
                 font=("Segoe UI", 11)).pack(pady=(0, 4))
        tk.Label(card,
                 text="Your ratings are live in the Google Sheet.",
                 bg=C["panel"], fg=C["txt2"],
                 font=("Segoe UI", 9, "italic")).pack(pady=(0, 12))

        btn_row = tk.Frame(card, bg=C["panel"])
        btn_row.pack(pady=(0, 18))
        self._btn(btn_row, "← BACK TO LIST",
                  self._rating_restart_at_top, w=16,
                  s="accent").pack(side="left", padx=4)
        self._btn(btn_row, "START OVER", self._show_rating_intro,
                  w=14, s="dim").pack(side="left", padx=4)

        # "VIEW YOUR RATINGS" section
        section_hdr = tk.Frame(f, bg=C["bg"])
        section_hdr.pack(fill="x", padx=20, pady=(6, 0))
        tk.Frame(section_hdr, bg=C["gold_dk"], height=1).pack(fill="x")
        tk.Label(section_hdr, text="YOUR RATINGS",
                 bg=C["bg"], fg=C["gold_dk"],
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(6, 4))

        ratings_outer = tk.Frame(f, bg=C["bg"])
        ratings_outer.pack(fill="x", padx=20, pady=(0, 20))

        ratings_card = tk.Frame(ratings_outer, bg=C["panel"],
                                highlightthickness=1,
                                highlightbackground=C["gold_dk"])
        ratings_card.pack(fill="x")

        for i, name in enumerate(self.rating_targets):
            tier = self.rating_existing.get(name, "")
            row_bg = C["panel"] if i % 2 == 0 else C["panel_2"]
            row = tk.Frame(ratings_card, bg=row_bg)
            row.pack(fill="x")

            # Tier color badge on the left
            tier_color = self._RATING_COLORS_BTL.get(tier, C["txt_dim"])
            badge = tk.Frame(row, bg=tier_color, width=4)
            badge.pack(side="left", fill="y")
            badge.pack_propagate(False)

            # Player name
            tk.Label(row, text=name,
                     bg=row_bg, fg=C["txt"],
                     font=("Segoe UI", 10),
                     anchor="w", width=22).pack(side="left", padx=(12, 4), pady=6)

            # Tier label (right-aligned)
            tier_label = tier if tier else "—"
            tk.Label(row, text=tier_label,
                     bg=row_bg, fg=tier_color,
                     font=("Segoe UI", 11, "bold"),
                     anchor="e", width=4).pack(side="right", padx=14, pady=6)

            # Click any row to jump back to that player
            def _go(n=name):
                self.rating_index = self.rating_targets.index(n)
                self.rating_status_var.set("")
                self._render_rating_view()
            for w in (row, badge):
                w.bind("<Button-1>", lambda e, n=name: _go(n))
                w.configure(cursor="hand2")

    def _rating_restart_at_top(self):
        """Jump back to the first player so the user can review/edit."""
        self.rating_index = 0
        self.rating_status_var.set("")
        self._render_rating_view()

    # ── In-House Games Tab ────────────────────────────────────

    _INHOUSE_ACCENT = "#8a6fc9"   # mauve (matches scouting in-house section)
    _INHOUSE_DIM    = "#2a1f47"

    def build_inhouse_tab(self):
        """Set up the In-House Games tab: scrollable canvas + initial UI."""
        canvas = tk.Canvas(self.tab_inhouse, bg=C["bg"], highlightthickness=0)
        scrollbar = tk.Scrollbar(self.tab_inhouse, orient="vertical",
                                 command=canvas.yview)
        self.inhouse_frame = tk.Frame(canvas, bg=C["bg"])

        self.inhouse_frame.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        wid = canvas.create_window((0, 0), window=self.inhouse_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.bind("<Configure>",
            lambda e, w=wid: canvas.itemconfigure(w, width=e.width))

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        self._bind_canvas_scroll(canvas, self.tab_inhouse)

        # Cached refs we'll repopulate as data and selection change
        self.inhouse_data = None
        self.inhouse_logger_proc = None
        self.inhouse_logger_running = False
        self.inhouse_player_var = tk.StringVar()
        self.inhouse_log_btn = None
        self.inhouse_progress_frame = None
        self.inhouse_status_frame = None
        self.inhouse_player_detail = None

        self._build_inhouse_chrome()
        self._show_inhouse_loading()

    def _build_inhouse_chrome(self):
        """Build the persistent UI: title, log button, status slot, body slot."""
        f = self.inhouse_frame
        for w in f.winfo_children():
            w.destroy()

        # Title
        self._tab_title(f, "CUSTOM GAMES", "IN-HOUSE LEADERBOARD")

        # Log Your Custom Games button — large, centered, prominent
        log_wrap = tk.Frame(f, bg=C["bg"])
        log_wrap.pack(fill="x", pady=(18, 8))

        self.inhouse_log_btn = tk.Button(
            log_wrap, text="LOG YOUR CUSTOM GAMES",
            command=self._run_inhouse_logger,
            bg=self._INHOUSE_ACCENT, fg=C["gold_lt"],
            activebackground="#a087d8",
            activeforeground=C["gold_lt"],
            font=("Segoe UI", 12, "bold"),
            relief="flat", bd=0, cursor="hand2",
            padx=36, pady=14,
            highlightthickness=2,
            highlightbackground=C["gold"])
        self.inhouse_log_btn.pack()

        # Subtitle / hint
        tk.Label(log_wrap,
                 text="Make sure your League client is running before logging.",
                 bg=C["bg"], fg=C["txt_dim"],
                 font=("Segoe UI", 9, "italic")).pack(pady=(8, 0))

        # Hover effect
        def _b_enter(_e):
            try: self.inhouse_log_btn.configure(bg="#a087d8")
            except Exception: pass
        def _b_leave(_e):
            try: self.inhouse_log_btn.configure(bg=self._INHOUSE_ACCENT)
            except Exception: pass
        self.inhouse_log_btn.bind("<Enter>", _b_enter)
        self.inhouse_log_btn.bind("<Leave>", _b_leave)

        # Slot for transient run-status (progress while logger is running)
        self.inhouse_status_frame = tk.Frame(f, bg=C["bg"])
        self.inhouse_status_frame.pack(fill="x", padx=20, pady=(4, 0))

        # Slot for the actual stats body (loaded/empty/data)
        self.inhouse_body = tk.Frame(f, bg=C["bg"])
        self.inhouse_body.pack(fill="both", expand=True, padx=20, pady=(8, 24))

    def _clear_inhouse_body(self):
        for w in self.inhouse_body.winfo_children():
            w.destroy()

    def _show_inhouse_loading(self):
        self._clear_inhouse_body()
        outer = tk.Frame(self.inhouse_body, bg=C["bg"])
        outer.pack(fill="x", pady=40)
        card = tk.Frame(outer, bg=C["panel"], highlightthickness=1,
                        highlightbackground=self._INHOUSE_DIM)
        card.pack(fill="x")
        tk.Label(card, text="LOADING IN-HOUSE STATS",
                 bg=C["panel"], fg=C["gold_dk"],
                 font=("Segoe UI", 9, "bold")).pack(pady=(20, 4))
        tk.Label(card, text="Reading from Google Sheet...",
                 bg=C["panel"], fg=self._INHOUSE_ACCENT,
                 font=("Segoe UI", 13, "bold")).pack(pady=(0, 20))

    def _show_inhouse_empty(self, msg):
        self._clear_inhouse_body()
        outer = tk.Frame(self.inhouse_body, bg=C["bg"])
        outer.pack(fill="x", pady=40)
        card = tk.Frame(outer, bg=C["panel"], highlightthickness=1,
                        highlightbackground=self._INHOUSE_DIM)
        card.pack(fill="x")
        tk.Label(card, text="NO IN-HOUSE DATA",
                 bg=C["panel"], fg=C["gold_dk"],
                 font=("Segoe UI", 9, "bold")).pack(pady=(20, 4))
        tk.Label(card, text="Click LOG YOUR CUSTOM GAMES above",
                 bg=C["panel"], fg=self._INHOUSE_ACCENT,
                 font=("Segoe UI", 13, "bold")).pack()
        tk.Label(card, text=msg, bg=C["panel"], fg=C["txt2"],
                 font=("Segoe UI", 10), wraplength=600,
                 justify="center").pack(pady=(8, 20), padx=20)

    # ── Sheet Parser ──────────────────────────────────────────

    def _load_initial_inhouse_bg(self):
        """Background fetch of In-House Stats sheet on startup."""
        try:
            import gspread
            from google.oauth2.service_account import Credentials
            cfg = self.config
            creds = Credentials.from_service_account_file(
                cfg["creds_path"],
                scopes=["https://www.googleapis.com/auth/spreadsheets",
                         "https://www.googleapis.com/auth/drive"])
            gc = gspread.authorize(creds)
            if "docs.google.com" in cfg["sheet_url"]:
                ss = gc.open_by_url(cfg["sheet_url"])
            else:
                ss = gc.open(cfg["sheet_url"])

            try:
                ws = ss.worksheet("In-House Stats")
            except Exception:
                self.after(0, self._show_inhouse_empty,
                           "No 'In-House Stats' sheet found yet. "
                           "Be the first to log custom games.")
                return

            data = self._parse_inhouse_sheet(ws)

            # Pipe diagnostic breadcrumbs to the admin console (they'll
            # buffer until you open the gear panel). These help when the
            # tab seems to find nothing despite the sheet having data.
            for line in data.get("_diag", []):
                self.after(0, self.log, f"[in-house] {line}\n", "dim")

            if not data["leaderboard"]:
                self.after(0, self._show_inhouse_empty,
                           "Couldn't read any rows from the In-House Stats "
                           "sheet. Open the admin panel (⚙) for diagnostic "
                           "details, or try clicking 'Log Your Custom Games' "
                           "to refresh the data.")
                return

            self.after(0, self._display_inhouse_results, data)
            self.after(0, self.log,
                       f"Loaded in-house stats ({data['total_games']} games).\n",
                       "green")
        except Exception as e:
            self.after(0, self._show_inhouse_empty,
                       f"Couldn't load in-house stats: {e}")

    def _parse_inhouse_sheet(self, ws):
        """Parse In-House Stats sheet into a structured dict.

        Robust against:
          - Trailing whitespace in cells
          - Variable row lengths (gspread truncates trailing empties)
          - Non-string values (gspread normalizes, but defensive anyway)
          - Merged cells (only the top-left holds the value)
        """
        values = cached_get_all_values(ws)
        out = {
            "title": "", "subtitle": "",
            "total_games": 0, "last_updated": "",
            "leaderboard": [], "per_player": {},
            "_diag": [],  # diagnostic breadcrumbs for the admin console
        }

        def cell0(row):
            """Safely extract the first cell of a row as a stripped string."""
            if not row:
                return ""
            v = row[0]
            if v is None or v == "":
                return ""
            return str(v).strip()

        if not values:
            out["_diag"].append("Sheet is completely empty.")
            return out

        out["_diag"].append(f"Sheet has {len(values)} rows.")

        if values[0]:
            out["title"] = cell0(values[0])
        if len(values) > 1 and values[1]:
            out["subtitle"] = cell0(values[1])
            m = re.match(r"(\d+)\s+in-house\s+games", out["subtitle"])
            if m:
                try:
                    out["total_games"] = int(m.group(1))
                except (ValueError, TypeError):
                    pass
            m = re.search(r"Last updated:\s*(.+)$", out["subtitle"])
            if m:
                out["last_updated"] = m.group(1).strip()

        # Walk through, identifying sections
        i = 0
        n = len(values)

        # Find the leaderboard section. Be tolerant of header variations:
        # match if the cell starts with "IN-HOUSE LEADERBOARD" (case-insensitive).
        leaderboard_start = None
        for idx in range(n):
            c = cell0(values[idx])
            if c.upper().startswith("IN-HOUSE LEADERBOARD"):
                leaderboard_start = idx
                break

        if leaderboard_start is None:
            out["_diag"].append(
                "Could not find 'IN-HOUSE LEADERBOARD' header. "
                f"First-cell preview: {[cell0(r) for r in values[:8]]!r}")
            return out

        out["_diag"].append(f"Leaderboard header at row {leaderboard_start + 1}.")
        i = leaderboard_start + 1

        # Skip the "#" column header row if present
        if i < n and cell0(values[i]) == "#":
            i += 1

        # Read leaderboard rows until we hit a blank row or a section header
        while i < n:
            r = values[i]
            c0 = cell0(r)
            if not c0:
                break
            if self._is_inhouse_section_header(c0):
                break
            r = list(r) + [""] * (14 - len(r))
            out["leaderboard"].append({
                "rank":      r[0],
                "player":    r[1],
                "games":     r[2],
                "wins":      r[3],
                "losses":    r[4],
                "wr":        r[5],
                "kda":       r[6],
                "kills":     r[7],
                "deaths":    r[8],
                "assists":   r[9],
                "cs_min":    r[10],
                "damage":    r[11],
                "vision":    r[12],
                "gold":      r[13],
            })
            i += 1

        out["_diag"].append(
            f"Parsed {len(out['leaderboard'])} leaderboard rows.")

        # Per-player champion sections
        cur_player = None
        while i < n:
            cell = cell0(values[i])

            if not cell:
                i += 1
                continue
            if cell.upper().startswith("IN-HOUSE CHAMPION STATS"):
                i += 1
                continue
            # Stop at a different section (e.g. ROLE PERFORMANCE)
            if (cell.upper().startswith("IN-HOUSE ROLE")
                    or cell.upper().startswith("HEAD-TO-HEAD")
                    or cell.upper().startswith("IN-HOUSE H2H")):
                break

            # Player block header: "PlayerName  —  N games  |  WR% WR"
            # Be tolerant of dash variants (em-dash, en-dash, hyphen-minus)
            # and confirm by looking for "N games" pattern.
            has_dash = any(d in cell for d in ("—", "–", "-"))
            if has_dash and "games" in cell.lower():
                # Match the player name as everything up to the first dash
                # variant followed by a number-games pattern.
                m = re.match(r"^(.*?)\s*[—–-]\s*(\d+)\s+games", cell)
                if m:
                    cur_player = m.group(1).strip()
                    out["per_player"][cur_player] = []
                else:
                    cur_player = None
                i += 1
                continue

            # Champion column-header row — skip
            if cell == "Champion":
                i += 1
                continue

            # Champion data row
            if cur_player is not None:
                cells = list(values[i]) + [""] * (10 - len(values[i]))
                out["per_player"][cur_player].append({
                    "champ":   cells[0],
                    "games":   cells[1],
                    "wins":    cells[2],
                    "losses":  cells[3],
                    "wr":      cells[4],
                    "kda":     cells[5],
                    "kills":   cells[6],
                    "deaths":  cells[7],
                    "assists": cells[8],
                    "damage":  cells[9],
                })
            i += 1

        out["_diag"].append(
            f"Parsed champion data for {len(out['per_player'])} players.")
        if out["per_player"]:
            sample_keys = list(out["per_player"].keys())[:5]
            out["_diag"].append(
                f"Per-player keys (sample): {sample_keys!r}")

        return out

    def _is_inhouse_section_header(self, cell):
        """True if the cell text is a known section header in the in-house sheet."""
        markers = ("IN-HOUSE LEADERBOARD",
                   "IN-HOUSE CHAMPION STATS",
                   "IN-HOUSE H2H", "HEAD-TO-HEAD")
        return any(cell.startswith(m) for m in markers)

    # ── Display ───────────────────────────────────────────────

    def _display_inhouse_results(self, data):
        """Render parsed in-house data into the body."""
        self.inhouse_data = data
        self._clear_inhouse_body()
        body = self.inhouse_body

        if not data["leaderboard"]:
            self._show_inhouse_empty("No tracked games yet.")
            return

        # Filter leaderboard to only players on the Players sheet, and
        # rewrite their display name from the Riot game-name (e.g.
        # "AllAmerican Bear") to the tier-list display name (e.g. "Ben").
        # The mapping comes from Players sheet column C (Riot ID) → column B.
        # If the roster hasn't loaded yet, fall back to showing all entries
        # so we don't render an empty leaderboard.
        if self.riot_to_display:
            filtered = []
            display_for_player = {}  # in-house name → display name (for per-player lookups)
            for p in data["leaderboard"]:
                in_house_name = str(p["player"]).strip()
                key = in_house_name.lower()
                if key in self.riot_to_display:
                    p2 = dict(p)
                    display = self.riot_to_display[key]
                    p2["player"] = display
                    filtered.append(p2)
                    display_for_player[in_house_name] = display
        elif self.player_list:
            # Roster loaded but no Riot ID mapping (shouldn't happen with the
            # new loader, but be tolerant). Fall back to direct name match.
            roster_lower = {n.lower() for n in self.player_list}
            filtered = [p for p in data["leaderboard"]
                        if str(p["player"]).strip().lower() in roster_lower]
            display_for_player = {}
        else:
            filtered = list(data["leaderboard"])
            display_for_player = {}

        if not filtered:
            # We had raw data but filtered everyone out — most likely the
            # in-house sheet uses different name spellings than the Players
            # sheet. Show what we found so it's easy to fix.
            sample = [str(p["player"]).strip()
                      for p in data["leaderboard"][:6]
                      if p["player"]]
            sample_text = ", ".join(sample) if sample else "(none)"
            self._show_inhouse_empty(
                f"Found {len(data['leaderboard'])} in-house entries, "
                f"but none of them match Riot IDs on the Players sheet.\n\n"
                f"Sample names from in-house data: {sample_text}\n\n"
                f"Roster has {len(self.player_list)} players. "
                f"The Riot ID column on the Players sheet must include the "
                f"in-house Riot game-name (e.g. 'AllAmerican Bear#NA1').")
            return

        # Cache the filtered leaderboard on the data dict so the dropdown
        # handler can find display-named rows
        data["leaderboard_display"] = filtered

        # Re-rank sequentially (1, 2, 3...) so the displayed positions match
        # the filtered view rather than the original sheet order.
        for i, p in enumerate(filtered, 1):
            p["rank"] = i

        # Build a per_player view keyed on display names (for the drilldown).
        # The original data["per_player"] is keyed on Riot game-names.
        per_player_display = {}
        for in_house_name, display in display_for_player.items():
            if in_house_name in data["per_player"]:
                per_player_display[display] = data["per_player"][in_house_name]
        # Keep the original raw map for any debug, but swap the keyed-by-display
        # version into the data dict so the dropdown handlers find what they want.
        data["per_player_display"] = per_player_display

        # Only show the games-tracked banner if we actually have logged data.
        # (Avoids the confusing "0 games tracked" placeholder.)
        if data.get("total_games", 0) > 0:
            self._build_inhouse_banner(body, data, len(filtered))

        self._build_inhouse_leaderboard(body, filtered)
        self._build_inhouse_player_select(body, data, filtered)

        # Player detail slot (populated when a name is picked)
        self.inhouse_player_detail = tk.Frame(body, bg=C["bg"])
        self.inhouse_player_detail.pack(fill="x", pady=(4, 0))
        self._build_inhouse_player_placeholder()

    def _build_inhouse_banner(self, parent, data, ranked_count):
        """Compact one-line stats banner (only shown when data exists)."""
        card = tk.Frame(parent, bg=C["panel"], highlightthickness=1,
                        highlightbackground=self._INHOUSE_DIM)
        card.pack(fill="x", pady=(0, 10))

        # Side accent stripe (slim)
        stripe = tk.Frame(card, bg=self._INHOUSE_ACCENT, width=3)
        stripe.pack(side="left", fill="y")
        stripe.pack_propagate(False)

        # Single inline row: count · last updated · ranked
        body = tk.Frame(card, bg=C["panel"])
        body.pack(side="left", fill="x", expand=True, padx=12, pady=6)

        tk.Label(body, text=str(data["total_games"]),
                 bg=C["panel"], fg=self._INHOUSE_ACCENT,
                 font=("Segoe UI", 13, "bold")).pack(side="left")
        tk.Label(body, text="GAMES TRACKED",
                 bg=C["panel"], fg=C["gold_dk"],
                 font=("Segoe UI", 8, "bold")).pack(side="left", padx=(6, 12))

        if data.get("last_updated"):
            tk.Label(body, text="·", bg=C["panel"], fg=C["txt_dim"],
                     font=("Segoe UI", 9)).pack(side="left", padx=4)
            tk.Label(body, text=f"Updated  {data['last_updated']}",
                     bg=C["panel"], fg=C["txt2"],
                     font=("Segoe UI", 9)).pack(side="left")

        # Ranked count on the right
        tk.Label(body, text=f"{ranked_count} ranked",
                 bg=C["panel"], fg=C["txt2"],
                 font=("Segoe UI", 9)).pack(side="right")

    def _build_inhouse_leaderboard(self, parent, players):
        """Leaderboard table (rank, player, games, W-L, WR, KDA + key averages)."""
        # Section header
        f = tk.Frame(parent, bg=C["bg"])
        f.pack(fill="x", pady=(8, 4))
        title_row = tk.Frame(f, bg=C["bg"])
        title_row.pack(fill="x")
        tk.Label(title_row, text="◆", bg=C["bg"], fg=self._INHOUSE_ACCENT,
                 font=("Segoe UI", 9)).pack(side="left", padx=(0, 8))
        tk.Label(title_row, text="LEADERBOARD", bg=C["bg"], fg=C["gold_lt"],
                 font=("Segoe UI", 11, "bold")).pack(side="left", anchor="w")
        tk.Frame(f, bg=C["gold_dk"], height=1).pack(fill="x", pady=(6, 0))

        card = tk.Frame(parent, bg=C["panel"], highlightthickness=1,
                        highlightbackground=self._INHOUSE_DIM)
        card.pack(fill="x", pady=(0, 14))

        h = tk.Frame(card, bg=C["strip"])
        h.pack(fill="x")
        for txt, w in [("#", 4), ("PLAYER", 14), ("GP", 6), ("W-L", 8),
                       ("WR", 7), ("KDA", 6), ("AVG CS", 7),
                       ("AVG DMG", 9), ("AVG GOLD", 10)]:
            tk.Label(h, text=txt, bg=C["strip"], fg=C["gold_dk"],
                     font=("Segoe UI", 8, "bold"), width=w,
                     anchor="w").pack(side="left", padx=4, pady=5)

        # Top 3 highlight + alternating rows
        for i, p in enumerate(players):
            is_top = i < 3
            if is_top:
                row_bg = "#1A1428"  # subtle purple-tinted row for top 3
            else:
                row_bg = C["panel"] if i % 2 == 0 else C["panel_2"]

            row = tk.Frame(card, bg=row_bg)
            row.pack(fill="x")

            # Top-3 left accent stripe
            if is_top:
                stripe = tk.Frame(row, bg=self._INHOUSE_ACCENT, width=3)
                stripe.pack(side="left", fill="y")
                stripe.pack_propagate(False)

            try:
                wr_num = float(str(p["wr"]).replace("%", ""))
            except (ValueError, TypeError):
                wr_num = 50.0
            wr_color = ("#5fb89a" if wr_num >= 50 else "#C84B31")
            name_color = (self._INHOUSE_ACCENT if is_top else C["gold_lt"])

            tk.Label(row, text=str(p["rank"]), bg=row_bg,
                     fg=C["gold"] if is_top else C["txt2"],
                     font=("Segoe UI", 11, "bold" if is_top else "normal"),
                     width=4 if is_top else 4,
                     anchor="w").pack(side="left",
                                       padx=(4 if not is_top else 1, 4),
                                       pady=5)
            tk.Label(row, text=str(p["player"]), bg=row_bg, fg=name_color,
                     font=("Segoe UI", 11, "bold"), width=14,
                     anchor="w").pack(side="left", padx=4, pady=5)
            tk.Label(row, text=str(p["games"]), bg=row_bg, fg=C["txt"],
                     font=("Segoe UI", 10), width=6,
                     anchor="w").pack(side="left", padx=4, pady=5)
            tk.Label(row, text=f"{p['wins']}-{p['losses']}",
                     bg=row_bg, fg=C["txt2"],
                     font=("Segoe UI", 10), width=8,
                     anchor="w").pack(side="left", padx=4, pady=5)
            tk.Label(row, text=str(p["wr"]), bg=row_bg, fg=wr_color,
                     font=("Segoe UI", 10, "bold"), width=7,
                     anchor="w").pack(side="left", padx=4, pady=5)
            tk.Label(row, text=str(p["kda"]), bg=row_bg, fg=C["txt"],
                     font=("Segoe UI", 10), width=6,
                     anchor="w").pack(side="left", padx=4, pady=5)
            tk.Label(row, text=str(p["cs_min"]), bg=row_bg, fg=C["txt2"],
                     font=("Segoe UI", 10), width=7,
                     anchor="w").pack(side="left", padx=4, pady=5)
            tk.Label(row, text=str(p["damage"]), bg=row_bg, fg=C["txt2"],
                     font=("Segoe UI", 10), width=9,
                     anchor="w").pack(side="left", padx=4, pady=5)
            tk.Label(row, text=str(p["gold"]), bg=row_bg, fg=C["txt2"],
                     font=("Segoe UI", 10), width=10,
                     anchor="w").pack(side="left", padx=4, pady=5)

    def _build_inhouse_player_select(self, parent, data, filtered):
        """Centered player dropdown for drilldown.

        `filtered` is the leaderboard already restricted to roster members,
        so the dropdown shows only registered tier-list players who also
        have champion data.
        """
        # Decorative divider
        div = tk.Frame(parent, bg=C["bg"])
        div.pack(fill="x", pady=(14, 6))
        row = tk.Frame(div, bg=C["bg"])
        row.pack(fill="x")
        tk.Frame(row, bg=C["gold_dk"], height=1).pack(
            side="left", fill="x", expand=True, pady=(8, 0))
        tk.Label(row, text="  ◆  PLAYER STATS  ◆  ", bg=C["bg"],
                 fg=C["gold"],
                 font=("Segoe UI", 11, "bold")).pack(side="left")
        tk.Frame(row, bg=C["gold_dk"], height=1).pack(
            side="left", fill="x", expand=True, pady=(8, 0))

        # Centered dropdown
        wrap = tk.Frame(parent, bg=C["bg"])
        wrap.pack(pady=(8, 6))

        tk.Label(wrap, text="VIEW DATA FOR", bg=C["bg"], fg=C["gold_dk"],
                 font=("Segoe UI", 8, "bold")).pack()

        # Build sorted list of roster players who actually have champion data.
        # Each name in `filtered` is already a display name (e.g. "Ben"),
        # and per_player_display is keyed on display names too.
        per_player_display = data.get("per_player_display", data["per_player"])
        players_with_data = sorted(
            p["player"] for p in filtered
            if p["player"] and str(p["player"]).strip()
            and p["player"] in per_player_display
            and len(per_player_display[p["player"]]) > 0
        )
        if not players_with_data:
            players_with_data = ["No data"]

        # Reset the var so the menu shows the placeholder
        self.inhouse_player_var.set("")

        menu = tk.OptionMenu(wrap, self.inhouse_player_var,
                             *players_with_data,
                             command=self._select_inhouse_player)
        menu._var = self.inhouse_player_var
        menu.configure(bg=C["input"], fg=C["txt"],
                       activebackground=C["hover"],
                       activeforeground=C["gold"],
                       font=("Segoe UI", 11), highlightthickness=1,
                       highlightbackground=C["gold_dk"],
                       relief="flat", width=22, indicatoron=True)
        menu["menu"].configure(bg=C["input"], fg=C["txt"],
                               activebackground=C["hover"],
                               activeforeground=C["gold"],
                               font=("Segoe UI", 10))
        menu.pack(pady=(4, 0))

    def _select_inhouse_player(self, name):
        """Handler when a player is picked from the dropdown."""
        if not self.inhouse_data or not name:
            return
        # Both maps are keyed on display name (e.g. "Ben"), set up by
        # _display_inhouse_results when filtering.
        per_player = self.inhouse_data.get("per_player_display") \
                     or self.inhouse_data["per_player"]
        leaderboard = self.inhouse_data.get("leaderboard_display") \
                      or self.inhouse_data["leaderboard"]
        champs = per_player.get(name, [])
        leader_row = next((p for p in leaderboard
                            if p["player"] == name), None)
        self._build_inhouse_player_detail(name, leader_row, champs)

    def _build_inhouse_player_placeholder(self):
        for w in self.inhouse_player_detail.winfo_children():
            w.destroy()
        msg = tk.Frame(self.inhouse_player_detail, bg=C["bg"])
        msg.pack(fill="x", pady=(12, 8))
        tk.Label(msg, text="Pick a player above to see their champion stats.",
                 bg=C["bg"], fg=C["txt_dim"],
                 font=("Segoe UI", 10, "italic")).pack()

    def _build_inhouse_player_detail(self, name, leader_row, champs):
        for w in self.inhouse_player_detail.winfo_children():
            w.destroy()

        if not champs:
            tk.Label(self.inhouse_player_detail,
                     text=f"No champion-level data for {name}.",
                     bg=C["bg"], fg=C["txt_dim"],
                     font=("Segoe UI", 10, "italic")).pack(pady=12)
            return

        # Player header card
        card = tk.Frame(self.inhouse_player_detail, bg=C["panel"],
                        highlightthickness=1,
                        highlightbackground=self._INHOUSE_DIM)
        card.pack(fill="x", pady=(8, 0))

        head = tk.Frame(card, bg=C["panel"])
        head.pack(fill="x")
        stripe = tk.Frame(head, bg=self._INHOUSE_ACCENT, width=4)
        stripe.pack(side="left", fill="y")
        stripe.pack_propagate(False)

        info = tk.Frame(head, bg=C["panel"])
        info.pack(side="left", fill="x", expand=True, padx=14, pady=12)

        tk.Label(info, text=str(name).upper(),
                 bg=C["panel"], fg=self._INHOUSE_ACCENT,
                 font=("Segoe UI", 18, "bold")).pack(anchor="w")

        if leader_row:
            sub = (f"#{leader_row['rank']}  ·  "
                   f"{leader_row['games']} games  ·  "
                   f"{leader_row['wins']}-{leader_row['losses']}  ·  "
                   f"{leader_row['wr']} WR  ·  KDA {leader_row['kda']}")
            tk.Label(info, text=sub, bg=C["panel"], fg=C["gold_lt"],
                     font=("Segoe UI", 10)).pack(anchor="w", pady=(4, 0))

        # Champion stats table headers
        h = tk.Frame(card, bg=C["strip"])
        h.pack(fill="x")
        for txt, w in [("CHAMPION", 14), ("GAMES", 6), ("W-L", 8),
                       ("WR", 7), ("KDA", 6),
                       ("K", 5), ("D", 5), ("A", 5), ("DMG", 10)]:
            tk.Label(h, text=txt, bg=C["strip"], fg=C["gold_dk"],
                     font=("Segoe UI", 8, "bold"), width=w,
                     anchor="w").pack(side="left", padx=4, pady=5)

        # Champion rows
        for i, c in enumerate(champs):
            row_bg = C["panel"] if i % 2 == 0 else C["panel_2"]
            try:
                wr_num = float(str(c["wr"]).replace("%", ""))
            except (ValueError, TypeError):
                wr_num = 50.0
            wr_color = "#5fb89a" if wr_num >= 50 else "#C84B31"

            try:
                wr_for_name = float(str(c["wr"]).replace("%", ""))
            except (ValueError, TypeError):
                wr_for_name = 50.0
            if wr_for_name >= 60:
                name_color = "#5fb89a"
            elif wr_for_name < 45:
                name_color = "#C84B31"
            else:
                name_color = self._INHOUSE_ACCENT

            row = tk.Frame(card, bg=row_bg)
            row.pack(fill="x")
            tk.Label(row, text=str(c["champ"]), bg=row_bg, fg=name_color,
                     font=("Segoe UI", 11, "bold"), width=14,
                     anchor="w").pack(side="left", padx=4, pady=5)
            tk.Label(row, text=str(c["games"]), bg=row_bg, fg=C["txt"],
                     font=("Segoe UI", 10), width=6,
                     anchor="w").pack(side="left", padx=4, pady=5)
            tk.Label(row, text=f"{c['wins']}-{c['losses']}",
                     bg=row_bg, fg=C["txt2"],
                     font=("Segoe UI", 10), width=8,
                     anchor="w").pack(side="left", padx=4, pady=5)
            tk.Label(row, text=str(c["wr"]), bg=row_bg, fg=wr_color,
                     font=("Segoe UI", 10, "bold"), width=7,
                     anchor="w").pack(side="left", padx=4, pady=5)
            tk.Label(row, text=str(c["kda"]), bg=row_bg, fg=C["txt"],
                     font=("Segoe UI", 10), width=6,
                     anchor="w").pack(side="left", padx=4, pady=5)
            tk.Label(row, text=str(c["kills"]), bg=row_bg, fg=C["txt2"],
                     font=("Segoe UI", 10), width=5,
                     anchor="w").pack(side="left", padx=4, pady=5)
            tk.Label(row, text=str(c["deaths"]), bg=row_bg, fg=C["txt2"],
                     font=("Segoe UI", 10), width=5,
                     anchor="w").pack(side="left", padx=4, pady=5)
            tk.Label(row, text=str(c["assists"]), bg=row_bg, fg=C["txt2"],
                     font=("Segoe UI", 10), width=5,
                     anchor="w").pack(side="left", padx=4, pady=5)
            tk.Label(row, text=str(c["damage"]), bg=row_bg, fg=C["txt2"],
                     font=("Segoe UI", 10), width=10,
                     anchor="w").pack(side="left", padx=4, pady=5)

    # ── Logger Run ────────────────────────────────────────────

    def _run_inhouse_logger(self):
        """Kick off inhouse_tracker.py from the in-house tab."""
        # Only allow one logger at a time — and don't conflict with admin runs
        if self.inhouse_logger_running:
            return
        if self.proc and self.proc.poll() is None:
            self._inhouse_show_status(
                "A process is already running. Wait for it to finish.",
                color=C["red"])
            return

        # Lock the button
        try:
            self.inhouse_log_btn.configure(state="disabled",
                                            text="LOGGING IN PROGRESS...")
        except Exception:
            pass

        self._inhouse_show_status(
            "Connecting to your League client...",
            color=self._INHOUSE_ACCENT, show_spinner=True)
        self.inhouse_logger_running = True
        self.jobs.submit("inhouse_logger", lambda c: self._inhouse_logger_bg())

    def _inhouse_logger_bg(self):
        """Run the inhouse_tracker.py subprocess and stream output."""
        cmd = self._build_cmd("inhouse")
        last_lines = []
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, cwd=self._script_dir(),
                env={**os.environ, "PYTHONUNBUFFERED": "1"})
            self.inhouse_logger_proc = proc

            for line in iter(proc.stdout.readline, ""):
                s = line.strip()
                if s:
                    last_lines.append(s)
                    if len(last_lines) > 6:
                        last_lines = last_lines[-6:]
                    # Show the most recent line as inline status
                    self.after(0, self._inhouse_show_status,
                               s[:120], self._INHOUSE_ACCENT, True)
                    # Also pipe to the admin console (will buffer if closed)
                    self.after(0, self.log, line)

            try:
                proc.wait(timeout=60)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            rc = proc.returncode

            if rc == 0:
                self.after(0, self._inhouse_show_status,
                           "Done! Refreshing stats...",
                           "#5fb89a", False)
                # Re-fetch the sheet to pick up the new games
                self.after(200, lambda: self.jobs.submit(
                    "reload_inhouse", lambda c: self._load_initial_inhouse_bg()))
                self.after(2500, self._inhouse_clear_status)
            else:
                tail = " | ".join(last_lines[-3:]) if last_lines else ""
                self.after(0, self._inhouse_show_status,
                           f"Logger exited with code {rc}.  {tail}",
                           "#C84B31", False)
        except Exception as e:
            self.after(0, self._inhouse_show_status,
                       f"Couldn't start logger: {e}",
                       "#C84B31", False)
        finally:
            self.inhouse_logger_running = False
            self.inhouse_logger_proc = None
            self.after(0, self._inhouse_unlock_button)

    def _inhouse_unlock_button(self):
        try:
            self.inhouse_log_btn.configure(state="normal",
                                            text="LOG YOUR CUSTOM GAMES")
        except Exception:
            pass

    def _inhouse_show_status(self, msg, color=None, show_spinner=False):
        """Render a transient status row above the body."""
        if not getattr(self, "inhouse_status_frame", None):
            return
        for w in self.inhouse_status_frame.winfo_children():
            w.destroy()
        if color is None:
            color = self._INHOUSE_ACCENT

        card = tk.Frame(self.inhouse_status_frame, bg=C["panel"],
                        highlightthickness=1,
                        highlightbackground=color)
        card.pack(fill="x", pady=(0, 4))
        stripe = tk.Frame(card, bg=color, width=3)
        stripe.pack(side="left", fill="y")
        stripe.pack_propagate(False)

        body = tk.Frame(card, bg=C["panel"])
        body.pack(side="left", fill="x", expand=True, padx=10, pady=8)
        if show_spinner:
            tk.Label(body, text="●", bg=C["panel"], fg=color,
                     font=("Segoe UI", 12, "bold")).pack(side="left",
                                                          padx=(0, 8))
        tk.Label(body, text=msg, bg=C["panel"], fg=C["gold_lt"],
                 font=("Segoe UI", 10), wraplength=900,
                 justify="left", anchor="w").pack(side="left", fill="x",
                                                    expand=True)

    def _inhouse_clear_status(self):
        if not getattr(self, "inhouse_status_frame", None):
            return
        for w in self.inhouse_status_frame.winfo_children():
            w.destroy()

    # ── Helpers ──────────────────────────────────────────────

    def _bind_canvas_scroll(self, canvas, container):
        """Make the mouse wheel scroll `canvas` only when cursor is inside `container`."""
        def _on_wheel(event):
            if event.num == 4:  # Linux scroll up
                canvas.yview_scroll(-1, "units")
            elif event.num == 5:  # Linux scroll down
                canvas.yview_scroll(1, "units")
            else:  # Windows / Mac
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def _enter(_e):
            canvas.bind_all("<MouseWheel>", _on_wheel)
            canvas.bind_all("<Button-4>", _on_wheel)
            canvas.bind_all("<Button-5>", _on_wheel)

        def _leave(_e):
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")

        container.bind("<Enter>", _enter)
        container.bind("<Leave>", _leave)

    def _section(self, parent, text):
        """Cinematic section label: short gold accent bar + caps label."""
        f = tk.Frame(parent, bg=C["bg"])
        f.pack(fill="x", pady=(12, 4))
        row = tk.Frame(f, bg=C["bg"])
        row.pack(fill="x")
        # Short accent bar (replaces the gold-dk hairline + diamond pattern)
        bar = tk.Frame(row, bg=C["gold"], width=18, height=2)
        bar.pack(side="left", padx=(0, 10), pady=(4, 0))
        bar.pack_propagate(False)
        tk.Label(row, text=text, bg=C["bg"], fg=C["gold"],
                font=("Segoe UI", 9, "bold")).pack(side="left", anchor="w")

    def _btn(self, parent, text, cmd, w=22, s="primary"):
        colors = {
            "primary":  (C["card"], C["gold"], C["gold_dk"], C["hover"]),
            "accent":   (C["blue_dk"], C["gold_lt"], C["blue"], C["blue"]),
            "danger":   (C["red_dk"], C["gold_lt"], C["red"], C["red"]),
            "dim":      (C["input"], C["txt2"], C["border"], C["hover"]),
        }
        bg, fg, brd, hv = colors.get(s, colors["primary"])
        b = tk.Button(parent, text=text, command=cmd, bg=bg, fg=fg,
                     activebackground=hv, activeforeground=C["gold_lt"],
                     font=("Segoe UI", 10, "bold"), relief="flat",
                     padx=14, pady=7, width=w, cursor="hand2",
                     highlightthickness=1, highlightbackground=brd,
                     highlightcolor=C["brd_act"])

        def enter(e): b.configure(bg=hv)
        def leave(e): b.configure(bg=bg)
        b.bind("<Enter>", enter)
        b.bind("<Leave>", leave)
        return b

    def log(self, text, tag=None):
        # Buffer messages while admin window is closed; flush when it opens
        if self.console is None:
            self._log_buffer.append((text, tag))
            # Bound the buffer to avoid runaway memory in long-running sessions
            if len(self._log_buffer) > self._log_buffer_max:
                self._log_buffer = self._log_buffer[-self._log_buffer_max:]
            return
        self.console.configure(state="normal")
        if tag:
            self.console.insert("end", text, tag)
        else:
            self.console.insert("end", text)
        self.console.see("end")
        self.console.configure(state="disabled")

    def clear_log(self):
        self._log_buffer = []
        if self.console is None:
            return
        self.console.configure(state="normal")
        self.console.delete("1.0", "end")
        self.console.configure(state="disabled")

    def save_cfg(self):
        self.config["api_key"]    = self.api_var.get().strip()
        self.config["sheet_url"]  = self.settings_sheet_var.get().strip()
        self.config["region"]     = self.settings_region_var.get().strip()
        self.config["routing"]    = self.settings_routing_var.get().strip()
        self.config["creds_path"] = self.settings_creds_var.get().strip()
        save_config(self.config)
        self.log("Settings saved.\n", "green")

    def _test_connection(self):
        self.notebook.select(self.tab_cmd)
        self.log("\nTesting connection...\n", "blue")
        self.jobs.submit("test_connection", lambda c: self._test_connection_bg())

    def _test_connection_bg(self):
        key    = self.api_var.get().strip()
        sheet  = self.settings_sheet_var.get().strip()
        creds  = self.settings_creds_var.get().strip()
        region = self.settings_region_var.get().strip()

        # 1 — Google Sheets
        self.after(0, self.log, "  Checking Google Sheets... ", None)
        try:
            import gspread
            from google.oauth2.service_account import Credentials as _Creds
            gc = gspread.authorize(
                _Creds.from_service_account_file(
                    creds,
                    scopes=["https://www.googleapis.com/auth/spreadsheets",
                            "https://www.googleapis.com/auth/drive"]))
            ss = gc.open_by_url(sheet) if "docs.google.com" in sheet else gc.open(sheet)
            self.after(0, self.log, f"OK  ({ss.title})\n", "green")
        except FileNotFoundError:
            self.after(0, self.log, f"FAIL — credentials file not found: {creds}\n", "red")
        except Exception as e:
            self.after(0, self.log, f"FAIL — {e}\n", "red")

        # 2 — Riot API
        self.after(0, self.log, "  Checking Riot API key... ", None)
        if not key:
            self.after(0, self.log, "FAIL — no API key entered\n", "red")
            return
        try:
            import urllib.request as _ur
            url = f"https://{region}.api.riotgames.com/lol/status/v4/platform-data"
            req = _ur.Request(url, headers={"X-Riot-Token": key})
            with _ur.urlopen(req, timeout=6) as r:
                r.read()
            self.after(0, self.log, "OK\n", "green")
        except Exception as e:
            self.after(0, self.log, f"FAIL — {e}\n", "red")

        self.after(0, self.log, "  Done.\n", "blue")

    def _script_dir(self):
        return _resolve_resource_dir()

    def _py(self):
        # When frozen (PyInstaller .exe), invoke this same .exe.
        # In source mode, fall back to python interpreter.
        if getattr(sys, "frozen", False):
            return sys.executable
        return "python" if sys.platform == "win32" else "python3"

    def _build_cmd(self, mode):
        py = self._py()
        key = self.api_var.get().strip()
        sheet = self.config["sheet_url"]
        creds = self.config["creds_path"]
        # When frozen (.exe), we invoke ourselves with --mode=.... When running
        # from source, we re-invoke this same script via python with --mode=....
        if getattr(sys, "frozen", False):
            self_target = [sys.executable]
        else:
            self_target = [py, os.path.abspath(__file__)]

        if mode == "inhouse":
            return self_target + ["--mode=inhouse",
                                  "--sheet", sheet, "--creds", creds]

        base = self_target + ["--mode=fetch_ranks",
                              "--key", key, "--sheet", sheet, "--creds", creds,
                              "--region", self.config["region"],
                              "--routing", self.config["routing"]]

        flags = {
            "update": [], "update_fast": ["--skip-matches"],
            "scout": ["--scout"], "scout_only": ["--scout-only"],
            "scout_new": ["--scout-new"],
            "setup_draft": ["--setup-draft"], "draft": ["--draft"],
        }
        if mode == "scout_player":
            name = self.rescount_player_var.get().strip()
            return base + ["--scout-player", name]
        return base + flags.get(mode, [])

    # ── Analytics execution helpers ───────────────────────────────────

    def _classify_line(self, line):
        s = line.strip()
        if "error" in s.lower() or "traceback" in s.lower():
            return "red"
        if "===" in s or "───" in s or "___" in s:
            return "gold"
        if any(w in s for w in ["Done", "written", "saved", "updated", "created"]):
            return "green"
        if s.startswith("[") or "Fetching" in s or "Loading" in s or "Connecting" in s:
            return "blue"
        return None

    def _build_cli_args(self, mode):
        key  = self.api_var.get().strip()
        sheet = self.config["sheet_url"]
        creds = self.config["creds_path"]
        if mode == "inhouse":
            return ["--sheet", sheet, "--creds", creds]
        base = ["--key", key, "--sheet", sheet, "--creds", creds,
                "--region", self.config["region"],
                "--routing", self.config["routing"]]
        flags = {
            "update": [], "update_fast": ["--skip-matches"],
            "scout": ["--scout"], "scout_only": ["--scout-only"],
            "scout_new": ["--scout-new"],
            "setup_draft": ["--setup-draft"], "draft": ["--draft"],
        }
        if mode == "scout_player":
            name = self.rescount_player_var.get().strip()
            return base + ["--scout-player", name]
        return base + flags.get(mode, [])

    def _on_close(self):
        self.jobs.shutdown(timeout=3)
        self.destroy()

    def _is_running(self):
        if isinstance(self.proc, threading.Thread):
            return self.proc.is_alive()
        return self.proc is not None and self.proc.poll() is None

    def _run_rescount_player(self):
        name = self.rescount_player_var.get().strip()
        if not name or name == "Loading...":
            self.log("\nSelect a player to re-scout first.\n", "red")
            return
        self.run("scout_player")

    def run(self, mode):
        if self._is_running():
            self.log("\nA process is already running.\n", "red")
            return

        key = self.api_var.get().strip()
        if mode != "inhouse" and not key:
            self.log("\nEnter your Riot API key first.\n", "red")
            return

        names = {
            "update": "Update Ranks", "update_fast": "Update (Fast)",
            "scout": "Full Scout", "scout_only": "Scout Only",
            "scout_new": "Scout New Players",
            "scout_player": f"Re-scout {self.rescount_player_var.get() or 'Player'}",
            "setup_draft": "Setup Draft", "draft": "Run Draft",
            "inhouse": "In-House Tracker",
        }
        # Switch to the COMMANDS tab so the user sees output immediately
        self.notebook.select(self.tab_cmd)

        self.log(f"\n{'═' * 45}\n", "gold")
        self.log(f"  {names.get(mode, mode)}\n", "hdr")
        self.log(f"{'═' * 45}\n\n", "gold")
        self.status.set(f"● {names.get(mode, mode).upper()}")

        self._current_mode = mode
        self.progress_bar.start(10)

        # In the merged frozen exe, _run_fetch_ranks/_run_inhouse are defined at
        # module level and can be called in-process — no pipes, no sys.stdout = None.
        # When running from source (python launcher.py), fall back to subprocess.
        if globals().get("_run_fetch_ranks") is not None:
            t = threading.Thread(target=self._run_bg_inprocess, args=(mode,), daemon=True)
        else:
            t = threading.Thread(target=self._run_bg, args=(mode,), daemon=True)
        self.proc = t
        t.start()
        self.after(50, self._poll_output)

    def _run_bg_inprocess(self, mode):
        """Run analytics in-process with stdout redirected to the output queue."""
        import sys as _sys
        import traceback as _tb

        class _QStream:
            def __init__(self, q, classify):
                self._q, self._classify, self._buf = q, classify, ""
            def write(self, text):
                self._buf += text
                while "\n" in self._buf:
                    line, self._buf = self._buf.split("\n", 1)
                    self._q.put((line + "\n", self._classify(line)))
            def flush(self): pass
            def fileno(self): return 1

        stream = _QStream(self._output_q, self._classify_line)
        old_out, old_err = _sys.stdout, _sys.stderr
        _sys.stdout = _sys.stderr = stream
        rc = 0
        try:
            cli_args = self._build_cli_args(mode)
            fn = globals().get("_run_inhouse" if mode == "inhouse" else "_run_fetch_ranks")
            fn(cli_args)
        except SystemExit as e:
            rc = e.code if isinstance(e.code, int) else 0
        except Exception as e:
            self._output_q.put((f"\nError: {e}\n{_tb.format_exc()}\n", "red"))
            rc = 1
        finally:
            _sys.stdout, _sys.stderr = old_out, old_err
            self.proc = None

        if rc == 0:
            self._output_q.put(("\nCompleted.\n", "green"))
            self.after(0, self.status.set, "● READY")
            self.after(2000, self._feed_refresh)
        else:
            self._output_q.put((f"\nFailed (code {rc})\n", "red"))
            self.after(0, self.status.set, f"● ERROR ({rc})")
        # Sentinel: signals _poll_output that the run is done
        self._output_q.put((None, rc))

    def _run_bg(self, mode):
        """Subprocess fallback (used when running from source, not frozen)."""
        cmd = self._build_cmd(mode)
        rc = 1
        try:
            self.proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, cwd=self._script_dir(),
                env={**os.environ, "PYTHONUNBUFFERED": "1"})
            for line in iter(self.proc.stdout.readline, ""):
                self._output_q.put((line, self._classify_line(line)))
            try:
                self.proc.wait(timeout=60)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
            rc = self.proc.returncode
            if rc == 0:
                self._output_q.put(("\nCompleted.\n", "green"))
                self.after(0, self.status.set, "● READY")
                self.after(2000, self._feed_refresh)
            else:
                self._output_q.put((f"\nFailed (code {rc})\n", "red"))
                self.after(0, self.status.set, f"● ERROR ({rc})")
        except FileNotFoundError:
            self._output_q.put(("\nScript not found.\n", "red"))
            self.after(0, self.status.set, "● ERROR")
        except Exception as e:
            self._output_q.put((f"\nError: {e}\n", "red"))
            self.after(0, self.status.set, "● ERROR")
        finally:
            self.proc = None
            # Sentinel: signals _poll_output that the run is done
            self._output_q.put((None, rc))

    def _poll_output(self):
        """Drain the output queue into the console. Runs on main thread every 50 ms."""
        try:
            for _ in range(50):
                line, tag = self._output_q.get_nowait()
                if line is None:
                    rc = tag  # sentinel: tag holds exit code
                    self.progress_bar.stop()
                    if rc != 0:
                        self.log(f"\n[ERROR] Process exited with code {rc}\n", "red")
                    else:
                        mode = self._current_mode
                        if mode:
                            ts = datetime.now().strftime("%Y-%m-%d %H:%M")
                            self.config["last_run"][mode] = ts
                            save_config(self.config)
                            lbl = self._last_run_labels.get(mode)
                            if lbl:
                                lbl.config(text=f"Last updated: {ts}")
                    self._current_mode = None
                    break
                self.log(line, tag)
        except queue.Empty:
            pass
        if self._is_running() or not self._output_q.empty():
            self.after(50, self._poll_output)

    def stop(self):
        if self._is_running():
            if isinstance(self.proc, threading.Thread):
                self.log("\nCannot stop mid-run — wait for completion.\n", "dim")
            else:
                self.proc.terminate()
                self.log("\nStopped.\n", "red")
                self.status.set("● READY")
        else:
            self.log("No process running.\n", "dim")


# ─── CLI subcommand dispatchers ─────────────────────────────────────


def _run_fetch_ranks(argv):
    """Run the rank/scout/draft analytics CLI in a subprocess context."""
    import sys as _sys
    _sys.argv = ["fetch_ranks_gsheets"] + list(argv)
    """
    League of Legends Power Rankings - Full Analytics Suite
    ========================================================
    Fetches rank data, champion mastery, match history, and generates
    analytics sheets including consensus, hot takes, bias reports,
    and rank history tracking with chart data.

    SETUP:
      pip install gspread google-auth requests

    USAGE:
      python3 fetch_ranks_gsheets.py --key "RGAPI-xxxx" --sheet "URL_OR_NAME"

    OPTIONS:
      --creds    Path to Google credentials JSON (default: credentials.json)
      --region   Platform routing (default: na1)
      --routing  Regional routing (default: americas)
      --skip-matches  Skip match history fetch (faster, fewer API calls)
    """



    DEFAULT_CREDS_FILE = "credentials.json"
    DEFAULT_REGION = "na1"
    DEFAULT_ROUTING = "americas"

    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    RANK_SCORES = {
        "Challenger": 10, "Grandmaster": 9.5, "Master": 9,
        "Diamond": 8, "Emerald": 6.25, "Platinum": 5.5,
        "Gold": 4.75, "Silver": 4, "Bronze": 3.25, "Iron": 2.5,
        # Unranked players are treated as Gold I (4.75) for scoring purposes
        # so they aren't unfairly penalized for not having placement games yet.
        "Unranked": 4.75,
    }
    DIV_OFFSETS = {"I": 0, "II": -0.25, "III": -0.5, "IV": -0.75}

    RANK_CHART_VALUES = {
        "Iron IV": 1, "Iron III": 2, "Iron II": 3, "Iron I": 4,
        "Bronze IV": 5, "Bronze III": 6, "Bronze II": 7, "Bronze I": 8,
        "Silver IV": 9, "Silver III": 10, "Silver II": 11, "Silver I": 12,
        "Gold IV": 13, "Gold III": 14, "Gold II": 15, "Gold I": 16,
        "Platinum IV": 17, "Platinum III": 18, "Platinum II": 19, "Platinum I": 20,
        "Emerald IV": 21, "Emerald III": 22, "Emerald II": 23, "Emerald I": 24,
        "Diamond IV": 25, "Diamond III": 26, "Diamond II": 27, "Diamond I": 28,
        "Master": 29, "Grandmaster": 30, "Challenger": 31, "Unranked": 0,
    }

    TIER_TO_NUM = {"S": 6, "A": 5, "B": 4, "C": 3, "D": 2, "F": 1}
    NUM_TO_TIER = {6: "S", 5: "A", 4: "B", 3: "C", 2: "D", 1: "F"}


    # ── Retry helper ──────────────────────────────────────────────

    def sheets_retry(fn, *args, max_attempts=6, **kwargs):
        """Call fn(*args, **kwargs) with exponential backoff on quota/server errors."""
        for attempt in range(max_attempts):
            try:
                return fn(*args, **kwargs)
            except gspread.exceptions.APIError as e:
                status = getattr(e.response, "status_code", None)
                if status in (429, 500, 503) and attempt < max_attempts - 1:
                    time.sleep((2 ** attempt) + random.uniform(0, 1))
                else:
                    raise


    # ── Google Sheets helpers ─────────────────────────────────────

    def connect_to_sheet(creds_file, sheet_identifier):
        credentials = Credentials.from_service_account_file(creds_file, scopes=SCOPES)
        gc = gspread.authorize(credentials)
        if "docs.google.com" in sheet_identifier:
            return gc.open_by_url(sheet_identifier)
        elif re.match(r'^[a-zA-Z0-9_-]{30,}$', sheet_identifier):
            return gc.open_by_key(sheet_identifier)
        else:
            return gc.open(sheet_identifier)


    def get_or_create_sheet(spreadsheet, name, rows=100, cols=30):
        try:
            return spreadsheet.worksheet(name)
        except gspread.exceptions.WorksheetNotFound:
            return sheets_retry(spreadsheet.add_worksheet, name, rows=rows, cols=cols)


    def fmt_title(ws, end_col):
        sheets_retry(ws.format, f"A1:{end_col}1", {
            "backgroundColor": {"red": 0.11, "green": 0.11, "blue": 0.18},
            "textFormat": {"bold": True, "fontSize": 14,
                           "foregroundColor": {"red": 0.91, "green": 0.72, "blue": 0.29}},
            "horizontalAlignment": "CENTER",
        })


    def fmt_header(ws, row, end_col):
        sheets_retry(ws.format, f"A{row}:{end_col}{row}", {
            "backgroundColor": {"red": 0.09, "green": 0.14, "blue": 0.28},
            "textFormat": {"bold": True,
                           "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
            "horizontalAlignment": "CENTER",
        })


    # ── Riot API helpers ──────────────────────────────────────────

    def riot_get(url, api_key, retries=3):
        for attempt in range(retries):
            resp = requests.get(url, headers={"X-Riot-Token": api_key})
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 5))
                print(f"    ... rate limited, waiting {wait}s")
                time.sleep(wait)
                continue
            if resp.status_code == 404:
                return None
            if attempt < retries - 1:
                time.sleep(2)
                continue
            print(f"    x API error {resp.status_code}: {resp.text[:120]}")
            return None
        return None


    def compute_score(tier, division):
        base = RANK_SCORES.get(tier, 1)
        offset = DIV_OFFSETS.get(division, 0) if tier not in [
            "Challenger", "Grandmaster", "Master", "Unranked"] else 0
        return round(base + offset, 2)


    def rank_to_chart_value(tier, division):
        if tier in ["Master", "Grandmaster", "Challenger", "Unranked"]:
            return RANK_CHART_VALUES.get(tier, 0)
        key = f"{tier} {division}" if division != "N/A" else tier
        return RANK_CHART_VALUES.get(key, 0)


    # ── Data Dragon ───────────────────────────────────────────────

    def load_champion_map():
        try:
            versions = requests.get(
                "https://ddragon.leagueoflegends.com/api/versions.json", timeout=10).json()
            latest = versions[0]
            url = f"https://ddragon.leagueoflegends.com/cdn/{latest}/data/en_US/champion.json"
            data = requests.get(url, timeout=10).json()
            champ_map = {}
            champ_tags = {}  # name -> [tags]
            for cname, cdata in data["data"].items():
                cid = int(cdata["key"])
                name = cdata["name"]
                champ_map[cid] = name
                champ_tags[name] = cdata.get("tags", [])
            print(f"  Loaded {len(champ_map)} champion names (patch {latest})")
            return champ_map, champ_tags
        except Exception as e:
            print(f"  Warning: could not load champion names: {e}")
            return {}, {}


    # ── Fetch functions ───────────────────────────────────────────

    def fetch_account(game_name, tag_line, routing, api_key):
        data = riot_get(
            f"https://{routing}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/"
            f"{game_name}/{tag_line}", api_key)
        return data.get("puuid") if data else None


    def fetch_ranked(puuid, region, api_key):
        entries = riot_get(
            f"https://{region}.api.riotgames.com/lol/league/v4/entries/by-puuid/{puuid}",
            api_key)
        if not entries:
            return "Unranked", "N/A", 0, 0, 0
        if isinstance(entries, dict):
            entries = [entries]
        for entry in entries:
            if entry.get("queueType") == "RANKED_SOLO_5x5":
                tier = entry["tier"].capitalize()
                rank = entry.get("rank", "I")
                lp = entry.get("leaguePoints", 0)
                wins = entry.get("wins", 0)
                losses = entry.get("losses", 0)
                division = rank if tier not in [
                    "Challenger", "Grandmaster", "Master"] else "N/A"
                return tier, division, lp, wins, losses
        return "Unranked", "N/A", 0, 0, 0


    def fetch_top_champions(puuid, region, api_key, champ_map, count=3):
        data = riot_get(
            f"https://{region}.api.riotgames.com/lol/champion-mastery/v4/"
            f"champion-masteries/by-puuid/{puuid}/top?count={count}", api_key)
        if not data:
            return []
        champs = []
        for entry in data[:count]:
            cid = entry.get("championId", 0)
            champs.append({
                "name": champ_map.get(cid, f"Champ#{cid}"),
                "points": entry.get("championPoints", 0),
                "level": entry.get("championLevel", 0),
            })
        return champs


    def fetch_recent_matches(puuid, routing, region, api_key, count=10):
        # Fetch extra to account for filtered-out ARAMs
        fetch_count = min(count * 3, 100)
        match_ids = riot_get(
            f"https://{routing}.api.riotgames.com/lol/match/v5/matches/"
            f"by-puuid/{puuid}/ids?count={fetch_count}", api_key)
        if not match_ids:
            return []
        # Valid queues: 400=Normal Draft, 420=Ranked Solo, 430=Blind, 490=Quickplay
        VALID_QUEUES = {400, 420, 430, 490}
        matches = []
        for mid in match_ids:
            if len(matches) >= count:
                break
            time.sleep(0.5)
            mdata = riot_get(
                f"https://{routing}.api.riotgames.com/lol/match/v5/matches/{mid}",
                api_key)
            if not mdata:
                continue
            info = mdata.get("info", {})
            queue_id = info.get("queueId", 0)
            if queue_id not in VALID_QUEUES:
                continue
            for p in info.get("participants", []):
                if p.get("puuid") == puuid:
                    matches.append({
                        "win": p.get("win", False),
                        "kills": p.get("kills", 0),
                        "deaths": p.get("deaths", 0),
                        "assists": p.get("assists", 0),
                        "champion": p.get("championName", "?"),
                        "cs": p.get("totalMinionsKilled", 0) + p.get("neutralMinionsKilled", 0),
                        "damage": p.get("totalDamageDealtToChampions", 0),
                    })
                    break
        return matches


    # ── Analytics ─────────────────────────────────────────────────

    def compute_tier_analytics(tier_data, player_names, rater_names):
        num_raters = len(rater_names)
        num_players = len(player_names)

        # CONSENSUS & CONTROVERSY
        consensus = []
        for i in range(num_players):
            tiers = tier_data.get(i, [])
            nums = [TIER_TO_NUM.get(t, 0) for t in tiers if t in TIER_TO_NUM]
            if not nums:
                consensus.append({"name": player_names[i], "avg": 0, "std": 0,
                                  "min": "-", "max": "-", "range": 0,
                                  "avg_tier": "?"})
                continue
            avg = sum(nums) / len(nums)
            std = math.sqrt(sum((x - avg)**2 for x in nums) / len(nums))
            consensus.append({
                "name": player_names[i],
                "avg": round(avg, 2),
                "avg_tier": NUM_TO_TIER.get(round(avg), "?"),
                "std": round(std, 2),
                "min": NUM_TO_TIER.get(min(nums), "?"),
                "max": NUM_TO_TIER.get(max(nums), "?"),
                "range": max(nums) - min(nums),
            })

        # HOT TAKE DETECTOR
        hot_takes = []
        for i in range(num_players):
            tiers = tier_data.get(i, [])
            nums = [TIER_TO_NUM.get(t, 0) for t in tiers if t in TIER_TO_NUM]
            if not nums:
                continue
            avg = sum(nums) / len(nums)
            for j, t in enumerate(tiers):
                if j >= num_raters:
                    break
                val = TIER_TO_NUM.get(t, 0)
                diff = val - avg
                if abs(diff) >= 1.5:
                    hot_takes.append({
                        "rater": rater_names[j] if j < len(rater_names) else f"Rater {j+1}",
                        "player": player_names[i],
                        "rated": t,
                        "avg": NUM_TO_TIER.get(round(avg), "?"),
                        "diff": round(abs(diff), 1),
                        "direction": "higher" if diff > 0 else "lower",
                    })
        hot_takes.sort(key=lambda x: x["diff"], reverse=True)

        # RATER BIAS
        rater_bias = []
        for j in range(num_raters):
            rater_tiers = []
            for i in range(num_players):
                tiers = tier_data.get(i, [])
                if j < len(tiers) and tiers[j] in TIER_TO_NUM:
                    rater_tiers.append(TIER_TO_NUM[tiers[j]])
            if not rater_tiers:
                continue
            avg = sum(rater_tiers) / len(rater_tiers)
            std = math.sqrt(sum((x - avg)**2 for x in rater_tiers) / len(rater_tiers))
            rater_bias.append({
                "rater": rater_names[j] if j < len(rater_names) else f"Rater {j+1}",
                "avg": round(avg, 2),
                "avg_tier": NUM_TO_TIER.get(round(avg), "?"),
                "s_count": sum(1 for t in rater_tiers if t == 6),
                "f_count": sum(1 for t in rater_tiers if t == 1),
                "std": round(std, 2),
            })

        if rater_bias:
            overall = sum(r["avg"] for r in rater_bias) / len(rater_bias)
            for r in rater_bias:
                d = r["avg"] - overall
                r["diff_from_avg"] = round(d, 2)
                r["label"] = "Generous" if d > 0.3 else ("Harsh" if d < -0.3 else "Balanced")

        return consensus, hot_takes, rater_bias


    # ── Sheet writers ─────────────────────────────────────────────

    def write_rank_data(spreadsheet, results, timestamp):
        ws = get_or_create_sheet(spreadsheet, "Rank Data", rows=30, cols=12)
        title = ["LEAGUE OF LEGENDS RANK DATA"] + [""]*11
        header = ["#", "Player Name", "Rank", "Division", "LP", "Wins", "Losses",
                  "Rank Score", "Normalized (0-100)", "Win Rate %", "Games Played",
                  "Last Updated"]
        rows = [title, header]
        for r in results:
            games = r["wins"] + r["losses"]
            wr = round(r["wins"] / games * 100, 1) if games > 0 else 0
            rows.append([r["row"], r["name"], r["tier"], r["division"],
                         r["lp"], r["wins"], r["losses"], r["score"],
                         r["normalized"], wr, games, timestamp])
        ws.clear()
        sheets_retry(ws.update, range_name="A1", values=rows)
        fmt_title(ws, "L")
        fmt_header(ws, 2, "L")
        if len(rows) > 2:
            sheets_retry(ws.format, f"A3:L{len(rows)}", {"horizontalAlignment": "CENTER"})
        print("  Rank Data updated")


    def write_player_stats(spreadsheet, results, champ_map):
        ws = get_or_create_sheet(spreadsheet, "Player Stats", rows=30, cols=16)
        title = ["PLAYER STATS - CHAMPIONS & RECENT PERFORMANCE"] + [""]*15
        header = ["#", "Player", "Win Rate %",
                  "Top Champ 1", "Mastery 1", "Top Champ 2", "Mastery 2",
                  "Top Champ 3", "Mastery 3",
                  "Recent W-L", "Recent WR%", "Avg KDA", "Avg Kills",
                  "Avg Deaths", "Avg Assists", "Hot/Cold"]
        rows = [title, header]
        for r in results:
            games = r["wins"] + r["losses"]
            wr = round(r["wins"] / games * 100, 1) if games > 0 else 0
            ch = r.get("top_champs", [])
            c1 = ch[0]["name"] if len(ch) > 0 else "-"
            m1 = f'{ch[0]["points"]:,}' if len(ch) > 0 else "-"
            c2 = ch[1]["name"] if len(ch) > 1 else "-"
            m2 = f'{ch[1]["points"]:,}' if len(ch) > 1 else "-"
            c3 = ch[2]["name"] if len(ch) > 2 else "-"
            m3 = f'{ch[2]["points"]:,}' if len(ch) > 2 else "-"
            matches = r.get("recent_matches", [])
            if matches:
                rw = sum(1 for m in matches if m["win"])
                rl = len(matches) - rw
                rwr = round(rw / len(matches) * 100, 1)
                ak = round(sum(m["kills"] for m in matches) / len(matches), 1)
                ad = round(sum(m["deaths"] for m in matches) / len(matches), 1)
                aa = round(sum(m["assists"] for m in matches) / len(matches), 1)
                kda = round((ak + aa) / max(ad, 1), 2)
                rwl = f"{rw}W-{rl}L"
                if rwr > wr + 10:
                    hc = "HOT"
                elif rwr < wr - 10:
                    hc = "COLD"
                else:
                    hc = "Steady"
            else:
                rwl = rwr = kda = ak = ad = aa = "-"
                hc = "-"
            rows.append([r["row"], r["name"], wr, c1, m1, c2, m2, c3, m3,
                         rwl, rwr, kda, ak, ad, aa, hc])
        ws.clear()
        sheets_retry(ws.update, range_name="A1", values=rows)
        fmt_title(ws, "P")
        fmt_header(ws, 2, "P")
        if len(rows) > 2:
            sheets_retry(ws.format, f"A3:P{len(rows)}", {"horizontalAlignment": "CENTER"})
        print("  Player Stats updated")


    def write_consensus(spreadsheet, consensus_data):
        ws = get_or_create_sheet(spreadsheet, "Consensus & Controversy", rows=30, cols=9)
        title = ["CONSENSUS & CONTROVERSY"] + [""]*8
        header = ["#", "Player", "Avg Tier Score", "Avg Tier", "Std Deviation",
                  "Lowest Rating", "Highest Rating", "Tier Spread", "Verdict"]
        rows = [title, header]
        sorted_data = sorted(consensus_data, key=lambda x: x["std"], reverse=True)
        for i, c in enumerate(sorted_data, 1):
            if c["std"] >= 1.5:
                verdict = "VERY Controversial"
            elif c["std"] >= 1.0:
                verdict = "Controversial"
            elif c["std"] >= 0.5:
                verdict = "Mixed"
            else:
                verdict = "Consensus"
            rows.append([i, c["name"], c["avg"], c.get("avg_tier", "?"),
                         c["std"], c["min"], c["max"], c["range"], verdict])
        ws.clear()
        sheets_retry(ws.update, range_name="A1", values=rows)
        fmt_title(ws, "I")
        fmt_header(ws, 2, "I")
        if len(rows) > 2:
            sheets_retry(ws.format, f"A3:I{len(rows)}", {"horizontalAlignment": "CENTER"})
        print("  Consensus & Controversy updated")


    def write_hot_takes(spreadsheet, hot_takes):
        ws = get_or_create_sheet(spreadsheet, "Hot Take Detector", rows=100, cols=7)
        title = ["HOT TAKE DETECTOR"] + [""]*6
        subtitle = ["Ratings 1.5+ tiers away from group average"] + [""]*6
        header = ["#", "Rater", "Player", "Their Rating", "Group Average",
                  "Tiers Off", "Direction"]
        rows = [title, subtitle, header]
        for i, ht in enumerate(hot_takes, 1):
            rows.append([i, ht["rater"], ht["player"], ht["rated"], ht["avg"],
                         ht["diff"], ht["direction"].upper()])
        if not hot_takes:
            rows.append(["", "No hot takes found - everyone agrees!", "", "", "", "", ""])
        ws.clear()
        sheets_retry(ws.update, range_name="A1", values=rows)
        fmt_title(ws, "G")
        sheets_retry(ws.format, "A2:G2", {
            "backgroundColor": {"red": 0.15, "green": 0.15, "blue": 0.25},
            "textFormat": {"italic": True,
                           "foregroundColor": {"red": 0.7, "green": 0.7, "blue": 0.7}},
            "horizontalAlignment": "CENTER",
        })
        fmt_header(ws, 3, "G")
        if len(rows) > 3:
            sheets_retry(ws.format, f"A4:G{len(rows)}", {"horizontalAlignment": "CENTER"})
        print(f"  Hot Take Detector updated ({len(hot_takes)} hot takes)")


    def write_rater_bias(spreadsheet, rater_bias):
        ws = get_or_create_sheet(spreadsheet, "Rater Bias Report", rows=30, cols=9)
        title = ["RATER BIAS REPORT"] + [""]*8
        header = ["#", "Rater", "Avg Tier Score", "Avg Tier", "# S Ratings",
                  "# F Ratings", "Spread (Std Dev)", "vs Group Avg", "Label"]
        rows = [title, header]
        sorted_bias = sorted(rater_bias, key=lambda x: x["avg"], reverse=True)
        for i, rb in enumerate(sorted_bias, 1):
            ds = f"+{rb['diff_from_avg']}" if rb["diff_from_avg"] > 0 else str(rb["diff_from_avg"])
            rows.append([i, rb["rater"], rb["avg"], rb["avg_tier"],
                         rb["s_count"], rb["f_count"], rb["std"], ds, rb["label"]])
        ws.clear()
        sheets_retry(ws.update, range_name="A1", values=rows)
        fmt_title(ws, "I")
        fmt_header(ws, 2, "I")
        if len(rows) > 2:
            sheets_retry(ws.format, f"A3:I{len(rows)}", {"horizontalAlignment": "CENTER"})
        print("  Rater Bias Report updated")


    def write_rank_history(spreadsheet, results, timestamp):
        """
        Chart-friendly layout:
        Row 1: Title
        Row 2: "Date/Time", Player1, Player2, ...  (header)
        Row 3+: one row of numeric rank values per run
        """
        ws = get_or_create_sheet(spreadsheet, "Rank History", rows=200, cols=50)
        existing = ws.get_all_values()
        result_map = {r["name"]: r for r in results}
        player_names = [r["name"] for r in results]
        num_players = len(results)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        ref_col = num_players + 3

        if not existing or len(existing) < 2:
            title = ["RANK HISTORY"] + [""] * num_players
            header = ["Date/Time"] + player_names
            data_row = [now_str]
            for r in results:
                data_row.append(rank_to_chart_value(r["tier"], r["division"]))

            all_rows = [title, header, data_row]
            ws.clear()
            sheets_retry(ws.update, range_name="A1", values=all_rows)
            fmt_title(ws, chr(64 + min(num_players + 1, 26)))

            ref_labels = [
                "Y-Axis Reference", "Rank = Value", "",
                "Challenger = 31", "Grandmaster = 30", "Master = 29",
                "Diamond I = 28", "Diamond IV = 25",
                "Emerald I = 24", "Emerald IV = 21",
                "Platinum I = 20", "Platinum IV = 17",
                "Gold I = 16", "Gold IV = 13",
                "Silver I = 12", "Silver IV = 9",
                "Bronze I = 8", "Bronze IV = 5",
                "Iron I = 4", "Iron IV = 1", "Unranked = 0",
            ]
            for i, label in enumerate(ref_labels):
                sheets_retry(ws.update_cell, i + 1, ref_col, label)

            print("  Rank History created (first snapshot)")
        else:
            next_row = len(existing) + 1
            header_names = existing[1][1:] if len(existing) > 1 else player_names

            data_row = [now_str]
            for name in header_names:
                r = result_map.get(name)
                if r:
                    data_row.append(rank_to_chart_value(r["tier"], r["division"]))
                else:
                    data_row.append("")

            sheets_retry(ws.update, range_name=f"A{next_row}", values=[data_row])

            data_points = next_row - 2
            print(f"  Rank History updated ({data_points} data points)")




    # ── Scouting system ───────────────────────────────────────────

    def fetch_scouting_matches(puuid, routing, region, api_key, count=100):
        """Fetch last N ranked/normal matches (skips ARAM, Arena, etc).

        Paginates the match-ID endpoint (max 100 IDs per call) so we can reach
        100+ valid games even if a player has many filtered-out ARAM/Arena games.
        """
        VALID_QUEUES = {400, 420, 430, 490}  # Normal Draft, Ranked Solo, Blind, Quickplay
        matches = []
        skipped = 0
        checked = 0
        start = 0
        BATCH = 100  # Riot API max IDs per call

        while len(matches) < count:
            match_ids = riot_get(
                f"https://{routing}.api.riotgames.com/lol/match/v5/matches/"
                f"by-puuid/{puuid}/ids?start={start}&count={BATCH}", api_key)
            if not match_ids:
                break

            for mid in match_ids:
                if len(matches) >= count:
                    break
                time.sleep(0.5)
                mdata = riot_get(
                    f"https://{routing}.api.riotgames.com/lol/match/v5/matches/{mid}",
                    api_key)
                if not mdata:
                    checked += 1
                    continue
                info = mdata.get("info", {})
                queue_id = info.get("queueId", 0)
                checked += 1
                if queue_id not in VALID_QUEUES:
                    skipped += 1
                    continue
                for p in info.get("participants", []):
                    if p.get("puuid") == puuid:
                        dur = info.get("gameDuration", 1) / 60
                        if dur < 0.1:
                            dur = 1
                        cs = p.get("totalMinionsKilled", 0) + p.get("neutralMinionsKilled", 0)
                        matches.append({
                            "win": p.get("win", False),
                            "champion": p.get("championName", "?"),
                            "kills": p.get("kills", 0),
                            "deaths": p.get("deaths", 0),
                            "assists": p.get("assists", 0),
                            "cs": cs,
                            "cs_min": round(cs / dur, 1),
                            "damage": p.get("totalDamageDealtToChampions", 0),
                            "vision": p.get("visionScore", 0),
                            "gold": p.get("goldEarned", 0),
                            "role": p.get("teamPosition", "UNKNOWN"),
                            "duration_min": round(dur, 1),
                            "first_blood": p.get("firstBloodKill", False),
                        })
                        break
                if checked % 10 == 0:
                    print(f"      {len(matches)} valid / {checked} checked (skipped {skipped} ARAM/other)")

            # Stop if the API returned fewer IDs than requested (no more history)
            if len(match_ids) < BATCH:
                break
            start += BATCH

        if skipped:
            print(f"      Filtered out {skipped} non-standard games (ARAM, Arena, etc)")
        return matches


    def analyze_player(matches):
        """Full statistical analysis of a player's match history."""
        if not matches:
            return None
        total = len(matches)
        wins = sum(1 for m in matches if m["win"])

        champ_stats = defaultdict(lambda: {
            "games": 0, "wins": 0, "kills": 0, "deaths": 0,
            "assists": 0, "cs_min": 0, "damage": 0, "gold": 0})
        for m in matches:
            c = champ_stats[m["champion"]]
            c["games"] += 1
            c["wins"] += 1 if m["win"] else 0
            c["kills"] += m["kills"]
            c["deaths"] += m["deaths"]
            c["assists"] += m["assists"]
            c["cs_min"] += m["cs_min"]
            c["damage"] += m["damage"]
            c["gold"] += m["gold"]

        champ_list = []
        for name, s in champ_stats.items():
            g = s["games"]
            champ_list.append({
                "name": name, "games": g, "wins": s["wins"], "losses": g - s["wins"],
                "wr": round(s["wins"] / g * 100, 1),
                "avg_kills": round(s["kills"] / g, 1),
                "avg_deaths": round(s["deaths"] / g, 1),
                "avg_assists": round(s["assists"] / g, 1),
                "kda": round((s["kills"] + s["assists"]) / max(s["deaths"], 1), 2),
                "avg_cs_min": round(s["cs_min"] / g, 1),
                "avg_damage": round(s["damage"] / g),
                "avg_gold": round(s["gold"] / g),
            })
        champ_list.sort(key=lambda x: x["games"], reverse=True)

        unique_champs = len(champ_list)
        pool_label = ("ONE-TRICK" if unique_champs <= 4 else
                      "SMALL POOL" if unique_champs <= 9 else
                      "MODERATE POOL" if unique_champs <= 16 else "DEEP POOL")

        must_bans = sorted(
            [c for c in champ_list if c["games"] >= 5 and c["wr"] >= 65],
            key=lambda x: x["wr"], reverse=True)

        top3_names = set(c["name"] for c in champ_list[:3])
        remaining = [m for m in matches if m["champion"] not in top3_names]
        ban3_wr = round(sum(1 for m in remaining if m["win"]) / len(remaining) * 100, 1) if remaining else 0
        ban3_games = len(remaining)

        role_map = {"TOP": "Top", "JUNGLE": "Jungle", "MIDDLE": "Mid",
                    "BOTTOM": "Bot", "UTILITY": "Support", "UNKNOWN": "Other"}
        role_counts = defaultdict(int)
        for m in matches:
            role_counts[role_map.get(m["role"], "Other")] += 1
        role_list = sorted(
            [{"role": r, "games": c, "pct": round(c / total * 100, 1)}
             for r, c in role_counts.items() if c > 0],
            key=lambda x: x["games"], reverse=True)

        role_champs = defaultdict(lambda: defaultdict(lambda: {"games": 0, "wins": 0}))
        for m in matches:
            role = role_map.get(m["role"], "Other")
            rc = role_champs[role][m["champion"]]
            rc["games"] += 1
            rc["wins"] += 1 if m["win"] else 0

        avg_kills = round(sum(m["kills"] for m in matches) / total, 1)
        avg_deaths = round(sum(m["deaths"] for m in matches) / total, 1)
        avg_assists = round(sum(m["assists"] for m in matches) / total, 1)
        avg_cs_min = round(sum(m["cs_min"] for m in matches) / total, 1)
        avg_damage = round(sum(m["damage"] for m in matches) / total)
        avg_vision = round(sum(m["vision"] for m in matches) / total, 1)
        avg_gold = round(sum(m["gold"] for m in matches) / total)
        overall_kda = round((avg_kills + avg_assists) / max(avg_deaths, 1), 2)
        overall_wr = round(wins / total * 100, 1)
        fb_rate = round(sum(1 for m in matches if m["first_blood"]) / total * 100, 1)

        recent = matches[:10]
        recent_wins = sum(1 for m in recent if m["win"])
        recent_wr = round(recent_wins / len(recent) * 100, 1) if recent else 0
        form = ("HOT" if recent_wr > overall_wr + 10 else
                "COLD" if recent_wr < overall_wr - 10 else "STEADY")

        return {
            "total": total, "wins": wins, "losses": total - wins,
            "wr": overall_wr, "overall_kda": overall_kda,
            "avg_kills": avg_kills, "avg_deaths": avg_deaths,
            "avg_assists": avg_assists, "avg_cs_min": avg_cs_min,
            "avg_damage": avg_damage, "avg_vision": avg_vision,
            "avg_gold": avg_gold, "fb_rate": fb_rate,
            "unique_champs": unique_champs, "pool_label": pool_label,
            "champ_list": champ_list, "must_bans": must_bans,
            "top3_names": list(top3_names), "ban3_wr": ban3_wr,
            "ban3_games": ban3_games,
            "role_list": role_list, "role_champs": dict(role_champs),
            "recent_wins": recent_wins, "recent_total": len(recent),
            "recent_wr": recent_wr, "form": form,
            "recent_matches": recent,
        }


    def write_scouting_sheet(spreadsheet, player_name, rank_str, lp, analysis, ranking_info=None, inhouse_data=None):
        """Create a detailed, styled scouting sheet for one player."""
        a = analysis
        sheet_name = f"Scout - {player_name}"[:30]
        try:
            old = spreadsheet.worksheet(sheet_name)
            sheets_retry(spreadsheet.del_worksheet, old)
        except gspread.exceptions.WorksheetNotFound:
            pass

        ws = sheets_retry(spreadsheet.add_worksheet, sheet_name, rows=120, cols=12)

        DARK = {"red": 0.11, "green": 0.11, "blue": 0.18}
        HEADER = {"red": 0.09, "green": 0.14, "blue": 0.28}
        SECTION = {"red": 0.13, "green": 0.17, "blue": 0.30}
        GOLD_TEXT = {"red": 0.91, "green": 0.72, "blue": 0.29}
        WHITE = {"red": 1, "green": 1, "blue": 1}
        L_BLUE = {"red": 0.88, "green": 0.92, "blue": 0.98}
        L_GREEN = {"red": 0.85, "green": 0.95, "blue": 0.85}
        L_RED = {"red": 0.98, "green": 0.88, "blue": 0.88}
        L_GOLD = {"red": 1.0, "green": 0.97, "blue": 0.88}

        rows = []
        fmts = []
        merges = []  # collect merge ranges to apply at end

        def rn():
            return len(rows)

        pad = lambda d: d + [""] * (12 - len(d))

        # ── HEADER ──
        # Timestamp is in col L (index 11). Merge only A:K so that L stays
        # unmerged and readable by the launcher via get_all_values().
        hdr_row = [f"SCOUTING REPORT: {player_name.upper()}"] + [""] * 10
        hdr_row.append(f"Scouted: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        rows.append(hdr_row)
        merges.append(f"A{rn()}:K{rn()}")
        fmts.append((f"A{rn()}:K{rn()}", {
            "backgroundColor": DARK,
            "textFormat": {"bold": True, "fontSize": 18, "foregroundColor": GOLD_TEXT},
            "horizontalAlignment": "CENTER"}))
        fmts.append((f"L{rn()}", {
            "backgroundColor": DARK,
            "textFormat": {"fontSize": 9, "italic": True, "foregroundColor": GOLD_TEXT},
            "horizontalAlignment": "RIGHT", "verticalAlignment": "MIDDLE"}))

        # Build subtitle with ranking info if available
        subtitle_parts = [rank_str, f"{lp} LP", f"{a['wins']}W-{a['losses']}L",
                          f"{a['wr']}% WR", f"{a['total']} games analyzed"]
        rows.append(pad(["  |  ".join(subtitle_parts)]))
        merges.append(f"A{rn()}:L{rn()}")
        fmts.append((f"A{rn()}:L{rn()}", {
            "backgroundColor": DARK,
            "textFormat": {"fontSize": 12, "foregroundColor": WHITE},
            "horizontalAlignment": "CENTER"}))

        # ── POWER RANKING BAR ──
        if ranking_info:
            ri = ranking_info
            rank_bar = (f"POWER RANKING: #{ri['position']}  |  "
                        f"Final Score: {ri['score']}  |  "
                        f"Rating: {ri['rating']}  |  "
                        f"Tier Score (60%): {ri.get('tier_component', '?')}  |  "
                        f"Rank Score (40%): {ri.get('rank_component', '?')}")
            rows.append(pad([rank_bar]))
            merges.append(f"A{rn()}:L{rn()}")
            # Color based on rating
            rating_colors = {
                "S": {"red": 1.0, "green": 0.27, "blue": 0.27},
                "A": {"red": 1.0, "green": 0.55, "blue": 0.0},
                "B": {"red": 1.0, "green": 0.84, "blue": 0.0},
                "C": {"red": 0.2, "green": 0.8, "blue": 0.2},
                "D": {"red": 0.25, "green": 0.41, "blue": 0.88},
                "F": {"red": 0.5, "green": 0.5, "blue": 0.5},
            }
            bar_color = rating_colors.get(ri.get("rating", ""), SECTION)
            fmts.append((f"A{rn()}:L{rn()}", {
                "backgroundColor": bar_color,
                "textFormat": {"bold": True, "fontSize": 13, "foregroundColor": WHITE},
                "horizontalAlignment": "CENTER"}))

        # ── OVERVIEW STATS ──
        rows.append(pad([""]))
        rows.append(pad(["KDA", "Avg Kills", "Avg Deaths", "Avg Assists",
                         "CS/min", "Avg Damage", "Avg Vision", "Avg Gold",
                         "FB %", "Form", "Pool Depth", "Unique Champs"]))
        fmts.append((f"A{rn()}:L{rn()}", {
            "backgroundColor": HEADER,
            "textFormat": {"bold": True, "fontSize": 10, "foregroundColor": WHITE},
            "horizontalAlignment": "CENTER"}))

        form_lbl = f"{a['form']} ({a['recent_wins']}/{a['recent_total']})"
        rows.append(pad([a["overall_kda"], a["avg_kills"], a["avg_deaths"],
                         a["avg_assists"], a["avg_cs_min"], f"{a['avg_damage']:,}",
                         a["avg_vision"], f"{a['avg_gold']:,}", f"{a['fb_rate']}%",
                         form_lbl, a["pool_label"], a["unique_champs"]]))
        fmts.append((f"A{rn()}:L{rn()}", {
            "backgroundColor": L_BLUE,
            "textFormat": {"bold": True, "fontSize": 11},
            "horizontalAlignment": "CENTER"}))

        # ── MUST-BAN ──
        rows.append(pad([""]))
        rows.append(pad(["BAN THESE CHAMPIONS"]))
        merges.append(f"A{rn()}:L{rn()}")
        fmts.append((f"A{rn()}:L{rn()}", {
            "backgroundColor": {"red": 0.6, "green": 0.1, "blue": 0.1},
            "textFormat": {"bold": True, "fontSize": 14, "foregroundColor": WHITE},
            "horizontalAlignment": "CENTER"}))

        if a["must_bans"]:
            rows.append(pad(["Champion", "Games", "Wins", "Losses", "Win Rate",
                             "KDA", "Avg Kills", "Avg Deaths", "Avg Assists",
                             "CS/min", "Avg Damage", "Threat"]))
            fmts.append((f"A{rn()}:L{rn()}", {
                "backgroundColor": HEADER,
                "textFormat": {"bold": True, "fontSize": 10, "foregroundColor": WHITE},
                "horizontalAlignment": "CENTER"}))
            for c in a["must_bans"]:
                threat = ("PERMABAN" if c["wr"] >= 75 and c["games"] >= 5 else
                          "HIGH" if c["wr"] >= 70 else "ELEVATED")
                rows.append(pad([c["name"], c["games"], c["wins"], c["losses"],
                                 f"{c['wr']}%", c["kda"], c["avg_kills"], c["avg_deaths"],
                                 c["avg_assists"], c["avg_cs_min"], f"{c['avg_damage']:,}",
                                 threat]))
                fmts.append((f"A{rn()}:L{rn()}", {
                    "backgroundColor": L_RED,
                    "textFormat": {"bold": True, "fontSize": 11},
                    "horizontalAlignment": "CENTER"}))
        else:
            rows.append(pad(["No standout ban targets (no champ with 5+ games AND 65%+ WR)"]))
            merges.append(f"A{rn()}:L{rn()}")
            fmts.append((f"A{rn()}:L{rn()}", {
                "backgroundColor": L_GREEN,
                "textFormat": {"italic": True, "fontSize": 11},
                "horizontalAlignment": "CENTER"}))

        # ── BAN IMPACT ──
        rows.append(pad([""]))
        top3_str = ", ".join(a["top3_names"])
        rows.append(pad([f"BAN IMPACT: If you ban {top3_str} ...", "", "", "", "",
                         f"Remaining WR: {a['ban3_wr']}%", "", "", "",
                         f"({a['ban3_games']} games)"]))
        merges.append(f"A{rn()}:E{rn()}")
        merges.append(f"F{rn()}:L{rn()}")
        bg = L_GREEN if a["ban3_wr"] < 50 else L_RED
        fmts.append((f"A{rn()}:L{rn()}", {
            "backgroundColor": bg,
            "textFormat": {"bold": True, "fontSize": 11},
            "horizontalAlignment": "CENTER"}))

        # ── FULL CHAMPION POOL ──
        rows.append(pad([""]))
        rows.append(pad(["FULL CHAMPION POOL"]))
        merges.append(f"A{rn()}:L{rn()}")
        fmts.append((f"A{rn()}:L{rn()}", {
            "backgroundColor": SECTION,
            "textFormat": {"bold": True, "fontSize": 14, "foregroundColor": GOLD_TEXT},
            "horizontalAlignment": "CENTER"}))

        rows.append(pad(["Champion", "Games", "Wins", "Losses", "Win Rate",
                         "KDA", "Avg Kills", "Avg Deaths", "Avg Assists",
                         "CS/min", "Avg Damage", "Avg Gold"]))
        fmts.append((f"A{rn()}:L{rn()}", {
            "backgroundColor": HEADER,
            "textFormat": {"bold": True, "fontSize": 10, "foregroundColor": WHITE},
            "horizontalAlignment": "CENTER"}))

        for i, c in enumerate(a["champ_list"]):
            bg_c = L_BLUE if i % 2 == 0 else {"red": 1, "green": 1, "blue": 1}
            rows.append(pad([c["name"], c["games"], c["wins"], c["losses"],
                             f"{c['wr']}%", c["kda"], c["avg_kills"], c["avg_deaths"],
                             c["avg_assists"], c["avg_cs_min"], f"{c['avg_damage']:,}",
                             f"{c['avg_gold']:,}"]))
            fmts.append((f"A{rn()}", {"backgroundColor": bg_c,
                                       "textFormat": {"bold": True, "fontSize": 11}}))
            fmts.append((f"B{rn()}:L{rn()}", {"backgroundColor": bg_c,
                                                "textFormat": {"fontSize": 11},
                                                "horizontalAlignment": "CENTER"}))

        # ── ROLE BREAKDOWN ──
        rows.append(pad([""]))
        rows.append(pad(["ROLE BREAKDOWN"]))
        merges.append(f"A{rn()}:L{rn()}")
        fmts.append((f"A{rn()}:L{rn()}", {
            "backgroundColor": SECTION,
            "textFormat": {"bold": True, "fontSize": 14, "foregroundColor": GOLD_TEXT},
            "horizontalAlignment": "CENTER"}))

        rows.append(pad(["Role", "Games", "% of Total", "Top Champions in Role"]))
        fmts.append((f"A{rn()}:L{rn()}", {
            "backgroundColor": HEADER,
            "textFormat": {"bold": True, "fontSize": 10, "foregroundColor": WHITE},
            "horizontalAlignment": "CENTER"}))

        for ri, r in enumerate(a["role_list"]):
            rc = a["role_champs"].get(r["role"], {})
            sorted_rc = sorted(rc.items(), key=lambda x: x[1]["games"], reverse=True)[:3]
            champ_str = ", ".join(f"{n} ({s['wins']}/{s['games']})" for n, s in sorted_rc)
            rows.append(pad([r["role"], r["games"], f"{r['pct']}%", champ_str]))
            merges.append(f"D{rn()}:L{rn()}")
            bg_r = L_GOLD if ri == 0 else {"red": 1, "green": 1, "blue": 1}
            fmts.append((f"A{rn()}:L{rn()}", {
                "backgroundColor": bg_r,
                "textFormat": {"fontSize": 11},
                "horizontalAlignment": "CENTER"}))

        # ── RECENT FORM ──
        rows.append(pad([""]))
        fc = ({"red": 0.1, "green": 0.5, "blue": 0.1} if a["form"] == "HOT"
              else {"red": 0.6, "green": 0.1, "blue": 0.1} if a["form"] == "COLD"
              else SECTION)
        rows.append(pad([f"RECENT FORM: {a['form']}  ({a['recent_wr']}% last {a['recent_total']} games)"]))
        merges.append(f"A{rn()}:L{rn()}")
        fmts.append((f"A{rn()}:L{rn()}", {
            "backgroundColor": fc,
            "textFormat": {"bold": True, "fontSize": 14, "foregroundColor": WHITE},
            "horizontalAlignment": "CENTER"}))

        rows.append(pad(["Game", "Result", "Champion", "Role", "K/D/A",
                         "KDA", "CS/min", "Damage", "Vision", "Gold", "Duration"]))
        fmts.append((f"A{rn()}:K{rn()}", {
            "backgroundColor": HEADER,
            "textFormat": {"bold": True, "fontSize": 10, "foregroundColor": WHITE},
            "horizontalAlignment": "CENTER"}))

        for i, m in enumerate(a["recent_matches"]):
            result = "WIN" if m["win"] else "LOSS"
            kda_s = f"{m['kills']}/{m['deaths']}/{m['assists']}"
            kda_r = round((m["kills"] + m["assists"]) / max(m["deaths"], 1), 2)
            role = {"TOP": "Top", "JUNGLE": "Jng", "MIDDLE": "Mid",
                    "BOTTOM": "Bot", "UTILITY": "Sup"}.get(m["role"], "?")
            bg_m = L_GREEN if m["win"] else L_RED
            rows.append(pad([i + 1, result, m["champion"], role, kda_s,
                             kda_r, m["cs_min"], f"{m['damage']:,}",
                             m["vision"], f"{m['gold']:,}", f"{m['duration_min']}m"]))
            fmts.append((f"A{rn()}:K{rn()}", {
                "backgroundColor": bg_m,
                "textFormat": {"fontSize": 11, "bold": m["win"]},
                "horizontalAlignment": "CENTER"}))

        # ── IN-HOUSE CUSTOMS ──
        if inhouse_data:
            ih = inhouse_data
            rows.append(pad([""]))
            rows.append(pad([f"IN-HOUSE CUSTOM GAMES  ({ih['total_games']} games  |  {ih['total_wr']}% WR)"]))
            merges.append(f"A{rn()}:L{rn()}")
            fmts.append((f"A{rn()}:L{rn()}", {
                "backgroundColor": {"red": 0.4, "green": 0.2, "blue": 0.6},
                "textFormat": {"bold": True, "fontSize": 14, "foregroundColor": WHITE},
                "horizontalAlignment": "CENTER"}))

            rows.append(pad(["Champion", "Games", "Wins", "Losses", "Win Rate",
                             "KDA", "Avg Kills", "Avg Deaths", "Avg Assists",
                             "Avg Damage"]))
            fmts.append((f"A{rn()}:J{rn()}", {
                "backgroundColor": HEADER,
                "textFormat": {"bold": True, "fontSize": 10, "foregroundColor": WHITE},
                "horizontalAlignment": "CENTER"}))

            for i, c in enumerate(ih["champs"]):
                bg_c = {"red": 0.92, "green": 0.88, "blue": 0.98} if i % 2 == 0 else {"red": 1, "green": 1, "blue": 1}
                rows.append(pad([c["name"], c["games"], c["wins"], c["games"] - c["wins"],
                                 f"{c['wr']}%", c["kda"], c["avg_kills"], c["avg_deaths"],
                                 c["avg_assists"], f"{c['avg_damage']:,}"]))
                fmts.append((f"A{rn()}", {"backgroundColor": bg_c,
                                           "textFormat": {"bold": True, "fontSize": 11}}))
                fmts.append((f"B{rn()}:J{rn()}", {"backgroundColor": bg_c,
                                                    "textFormat": {"fontSize": 11},
                                                    "horizontalAlignment": "CENTER"}))

        # ── WRITE + FORMAT ──
        sheets_retry(ws.update, range_name="A1", values=rows)

        # Apply all tracked merges
        for m in merges:
            sheets_retry(ws.merge_cells, m)

        # Column widths
        col_px = [160, 80, 80, 80, 90, 80, 90, 100, 100, 90, 100, 120]
        reqs = []
        for ci, px in enumerate(col_px):
            reqs.append({"updateDimensionProperties": {
                "range": {"sheetId": ws.id, "dimension": "COLUMNS",
                          "startIndex": ci, "endIndex": ci + 1},
                "properties": {"pixelSize": px}, "fields": "pixelSize"}})
        reqs.append({"updateDimensionProperties": {
            "range": {"sheetId": ws.id, "dimension": "ROWS",
                      "startIndex": 0, "endIndex": 1},
            "properties": {"pixelSize": 50}, "fields": "pixelSize"}})
        sheets_retry(spreadsheet.batch_update, {"requests": reqs})

        # Apply formats in batches
        for i in range(0, len(fmts), 15):
            batch = [{"range": r, "format": f} for r, f in fmts[i:i+15]]
            sheets_retry(ws.batch_format, batch)

        # Tab color by form
        tc = ({"red": 0.2, "green": 0.8, "blue": 0.2} if a["form"] == "HOT"
              else {"red": 0.8, "green": 0.2, "blue": 0.2} if a["form"] == "COLD"
              else {"red": 0.3, "green": 0.5, "blue": 0.9})
        sheets_retry(spreadsheet.batch_update, {"requests": [{
            "updateSheetProperties": {
                "properties": {"sheetId": ws.id, "tabColor": tc},
                "fields": "tabColor"}}]})

        print(f"  Scout - {player_name} done")


    # ── Rankings lookup ────────────────────────────────────────────

    def get_final_rankings(spreadsheet):
        """Read Final Rankings sheet to get each player's position and score."""
        try:
            ws = spreadsheet.worksheet("Final Rankings")
            values = ws.get_all_values()
            rankings = {}
            for row in values[3:]:  # skip title, subtitle, header
                if len(row) >= 8 and row[0] and row[1]:
                    try:
                        rankings[row[1].strip()] = {
                            "position": int(row[0]),
                            "score": float(row[6]) if row[6] else 0,
                            "rating": row[7] if len(row) > 7 else "?",
                            "tier_component": row[3] if len(row) > 3 else "?",
                            "rank_component": row[5] if len(row) > 5 else "?",
                        }
                    except (ValueError, IndexError):
                        continue
            return rankings
        except Exception as e:
            print(f"  Could not read Final Rankings: {e}")
            return {}


    def load_inhouse_db(spreadsheet):
        """Load inhouse stats by reading directly from _InhouseGameLog.
        This ensures all games from all contributors are included."""
        try:
            ws = spreadsheet.worksheet("_InhouseGameLog")
            values = ws.get_all_values()
            if len(values) < 2: return {}

            # Parse all game records
            # Header: gameId, timestamp, player, champion, teamId, win, kills, deaths, assists, cs, damage, gold, vision, role, duration, logged_by
            records = []
            for row in values[1:]:
                if len(row) < 14 or not row[0]: continue
                try:
                    records.append({
                        "gameId": row[0],
                        "player": row[2],
                        "champion": row[3],
                        "teamId": int(row[4]) if row[4] else 0,
                        "win": str(row[5]).upper() in ("TRUE", "1"),
                        "kills": int(float(row[6])) if row[6] else 0,
                        "deaths": int(float(row[7])) if row[7] else 0,
                        "assists": int(float(row[8])) if row[8] else 0,
                        "damage": int(float(row[10])) if len(row) > 10 and row[10] else 0,
                        "role": row[13] if len(row) > 13 else "Fill",
                    })
                except (ValueError, IndexError): continue

            if not records:
                return {}

            # Compute stats per player
            inhouse = {}
            player_games = defaultdict(lambda: {"games": set(), "wins": 0})
            champ_stats = defaultdict(lambda: defaultdict(lambda: {
                "games": 0, "wins": 0, "kills": 0, "deaths": 0, "assists": 0,
                "damage": 0, "roles": defaultdict(int)}))

            # Group by game to count unique games per player
            games_by_id = defaultdict(list)
            for r in records:
                games_by_id[r["gameId"]].append(r)

            for gid, game_records in games_by_id.items():
                # Only count 5v5 games (10 players)
                if len(game_records) != 10:
                    continue
                for r in game_records:
                    name = r["player"]
                    player_games[name]["games"].add(gid)
                    if r["win"]:
                        player_games[name]["wins"] += 1

                    cs = champ_stats[name][r["champion"]]
                    cs["games"] += 1
                    cs["wins"] += 1 if r["win"] else 0
                    cs["kills"] += r["kills"]
                    cs["deaths"] += r["deaths"]
                    cs["assists"] += r["assists"]
                    cs["damage"] += r["damage"]
                    cs["roles"][r["role"]] += 1

            # Build output format
            for name, pg in player_games.items():
                total_g = len(pg["games"])
                total_wr = round(pg["wins"] / total_g * 100, 1) if total_g > 0 else 0

                champs = []
                for champ_name, cs in champ_stats[name].items():
                    cg = cs["games"]
                    if cg == 0: continue
                    champs.append({
                        "name": champ_name,
                        "games": cg,
                        "wins": cs["wins"],
                        "wr": round(cs["wins"] / cg * 100, 1),
                        "kda": round((cs["kills"] + cs["assists"]) / max(cs["deaths"], 1), 2),
                        "avg_kills": round(cs["kills"] / cg, 1),
                        "avg_deaths": round(cs["deaths"] / cg, 1),
                        "avg_assists": round(cs["assists"] / cg, 1),
                        "avg_damage": round(cs["damage"] / cg),
                        "roles": dict(cs["roles"]),
                    })

                champs.sort(key=lambda x: x["games"], reverse=True)
                inhouse[name] = {"total_games": total_g, "total_wr": total_wr, "champs": champs}

            print(f"  Loaded {len(inhouse)} players from game log ({sum(len(pg['games']) for pg in player_games.values())} player-game records)")
            return inhouse

        except gspread.exceptions.WorksheetNotFound:
            # Fall back to _InhouseDB if game log doesn't exist
            try:
                ws = spreadsheet.worksheet("_InhouseDB")
                values = ws.get_all_values()
                if len(values) < 3: return {}
                inhouse = {}
                for row in values[2:]:
                    if len(row) < 10 or not row[0]: continue
                    name = row[0]
                    if name not in inhouse:
                        inhouse[name] = {"total_games": 0, "total_wr": 0, "champs": []}
                    try:
                        inhouse[name]["total_games"] = int(float(row[10])) if len(row) > 10 and row[10] else 0
                        inhouse[name]["total_wr"] = float(row[11]) if len(row) > 11 and row[11] else 0
                        roles = {}
                        if len(row) > 12 and row[12]:
                            for part in row[12].split(";"):
                                if ":" in part:
                                    r, c = part.split(":")
                                    roles[r] = int(c)
                        inhouse[name]["champs"].append({
                            "name": row[1], "games": int(float(row[2])) if row[2] else 0,
                            "wins": int(float(row[3])) if row[3] else 0,
                            "wr": float(row[4]) if row[4] else 0,
                            "kda": float(row[5]) if row[5] else 0,
                            "avg_kills": float(row[6]) if row[6] else 0,
                            "avg_deaths": float(row[7]) if row[7] else 0,
                            "avg_assists": float(row[8]) if row[8] else 0,
                            "avg_damage": int(float(row[9])) if row[9] else 0,
                            "roles": roles,
                        })
                    except (ValueError, IndexError): continue
                for name in inhouse:
                    inhouse[name]["champs"].sort(key=lambda x: x["games"], reverse=True)
                return inhouse
            except Exception as e:
                print(f"Warning: failed to load inhouse DB fallback: {e}")
                return {}
        except Exception as e:
            print(f"Warning: failed to load inhouse data: {e}")
            return {}


    # ── Champion archetype database ───────────────────────────────

    COMP_ARCHETYPES = {
        "Teamfight": {
            "description": "Group and win 5v5s with AoE and engage",
            "needs": {"engage": 1, "aoe_damage": 2, "frontline": 1},
            "ideal_tags": {"Tank", "Mage"},
        },
        "Pick": {
            "description": "Catch enemies with CC and burst them 1-by-1",
            "needs": {"assassin_or_burst": 2, "cc": 2},
            "ideal_tags": {"Assassin", "Mage"},
        },
        "Split Push": {
            "description": "1-3-1 or 1-4 with strong duelists in side lanes",
            "needs": {"duelist": 1, "waveclear": 1},
            "ideal_tags": {"Fighter"},
        },
        "Poke / Siege": {
            "description": "Chunk enemies before fights with long-range abilities",
            "needs": {"long_range": 2, "disengage": 1},
            "ideal_tags": {"Mage", "Marksman"},
        },
        "Protect the Carry": {
            "description": "Peel and buff your strongest damage dealer",
            "needs": {"hypercarry": 1, "peel": 2},
            "ideal_tags": {"Support", "Marksman"},
        },
        "Dive": {
            "description": "Hard engage onto backline, collapse and delete carries",
            "needs": {"engage": 2, "assassin_or_burst": 1, "frontline": 1},
            "ideal_tags": {"Tank", "Assassin", "Fighter"},
        },
        "Scaling": {
            "description": "Play safe early, outscale with late-game champions",
            "needs": {"hypercarry": 1, "waveclear": 1, "disengage": 1},
            "ideal_tags": {"Mage", "Marksman"},
        },
    }

    ARCHETYPE_CONFLICTS = {
        "Dive": ["hypercarry", "disengage"],        # hypercarry/peel in dive = bad
        "Teamfight": ["disengage", "duelist"],       # selfish fighters in TF = bad
        "Poke / Siege": ["engage", "assassin_or_burst"],  # dive in poke = contradictory
        "Protect the Carry": ["assassin_or_burst"],  # assassins in protect = bad
        "Split Push": ["engage", "aoe_damage"],      # AoE teamfight in split = bad
    }

    CHAMP_SUBCLASSES = {
        "engage": {"Malphite","Amumu","Leona","Nautilus","Rakan","Rell","Alistar",
                   "Jarvan IV","Sejuani","Maokai","Ornn","Zac","Sion","Gragas",
                   "Wukong","Diana","Galio","Skarner","Yone","Kennen","Hecarim",
                   "Vi","Camille","Kled","Nocturne","Rek'Sai","Pantheon",
                   "Ambessa","Aurora"},
        "aoe_damage": {"Orianna","Miss Fortune","Kennen","Rumble","Diana","Yone",
                       "Yasuo","Gangplank","Samira","Karthus","Brand","Zyra",
                       "Viktor","Cassiopeia","Nilah","Fiddlesticks","Aurora","Katarina",
                       "Vladimir","Lissandra","Wukong","Galio","Lillia","Briar",
                       "Vex","Hwei","Ziggs","Seraphine","Twitch","Jinx"},
        "frontline": {"Malphite","Maokai","Ornn","Sion","Cho'Gath","Dr. Mundo",
                      "Tahm Kench","Shen","Braum","Taric","Alistar","Leona",
                      "Nautilus","Rell","Sejuani","Amumu","Rammus","Zac",
                      "Poppy","Skarner","K'Sante","Gragas","Volibear","Darius",
                      "Garen","Sett","Mordekaiser","Illaoi","Urgot","Aatrox","Ambessa"},
        "assassin_or_burst": {"Zed","Talon","Qiyana","Akali","LeBlanc","Fizz",
                              "Katarina","Ekko","Kha'Zix","Rengar","Evelynn",
                              "Shaco","Naafiri","Pyke","Syndra","Ahri","Veigar",
                              "Annie","Lux","Neeko","Zoe","Vex","Aurora",
                              "Nocturne","Diana","Briar","Lee Sin",
                              "Ambessa","Mel"},
        "cc": {"Thresh","Morgana","Lux","Ahri","Ashe","Jhin","Veigar","Neeko",
               "Twisted Fate","Blitzcrank","Pyke","Elise","Lee Sin","Hwei",
               "Sejuani","Amumu","Leona","Nautilus","Maokai","Zyra","Bard",
               "Renata Glasc","Rakan","Rell","Skarner"},
        "duelist": {"Fiora","Tryndamere","Jax","Camille","Gwen","Irelia","Riven",
                    "Yasuo","Yone","Mordekaiser","Nasus","Yorick","Trundle",
                    "Volibear","Udyr","Kayle","Sett","Gnar","Ambessa","Warwick",
                    "Shen","Illaoi","Olaf","Renekton","Kled"},
        "waveclear": {"Anivia","Ryze","Malzahar","Viktor","Ziggs","Sivir",
                      "Jinx","Orianna","Xerath","Taliyah","Aurelion Sol","Hwei",
                      "Twisted Fate","Corki","Heimerdinger","Seraphine","Veigar",
                      "Cassiopeia","Vladimir","Azir","Mel","Smolder"},
        "long_range": {"Xerath","Vel'Koz","Lux","Ziggs","Jayce","Ezreal","Varus",
                       "Kog'Maw","Nidalee","Zoe","Hwei","Caitlyn","Senna",
                       "Seraphine","Karma","Viktor","Corki","Jhin","Ashe"},
        "disengage": {"Janna","Gragas","Poppy","Alistar","Thresh","Braum",
                      "Karma","Lulu","Zilean","Anivia","Taliyah","Azir",
                      "Nami","Milio","Soraka"},
        "hypercarry": {"Kog'Maw","Jinx","Twitch","Aphelios","Vayne","Kayle",
                       "Kindred","Smolder","Veigar","Cassiopeia","Karthus",
                       "Azir","Viktor","Tristana","Xayah","Zeri","Kai'Sa",
                       "Draven","Nilah","Master Yi"},
        "peel": {"Lulu","Janna","Karma","Nami","Soraka","Yuumi","Milio",
                 "Renata Glasc","Taric","Zilean","Ivern","Braum","Shen",
                 "Orianna","Seraphine","Sona","Bard"},
    }


    ROLE_VALID = {
        "Top": {"Aatrox","Ambessa","Aurora","Camille","Cho'Gath","Darius","Dr. Mundo",
                "Fiora","Gangplank","Garen","Gnar","Gwen","Illaoi","Irelia","Jax",
                "Jayce","K'Sante","Kayle","Kennen","Kled","Malphite","Maokai",
                "Mordekaiser","Nasus","Olaf","Ornn","Pantheon","Poppy","Quinn",
                "Renekton","Rengar","Riven","Rumble","Sett","Shen","Singed",
                "Sion","Tahm Kench","Teemo","Trundle","Tryndamere","Urgot",
                "Vladimir","Volibear","Wukong","Yasuo","Yone","Yorick","Gragas",
                "Heimerdinger","Akali","Sylas","Warwick","Zac"},
        "Jungle": {"Amumu","Ambessa","Bel'Veth","Briar","Diana","Ekko","Elise","Evelynn",
                   "Fiddlesticks","Gragas","Graves","Hecarim","Ivern","Jarvan IV",
                   "Karthus","Kayn","Kha'Zix","Kindred","Lee Sin","Lillia",
                   "Master Yi","Nidalee","Nocturne","Nunu","Pantheon","Poppy",
                   "Rammus","Rek'Sai","Rengar","Sejuani","Shaco","Shyvana",
                   "Skarner","Taliyah","Udyr","Vi","Viego","Volibear","Warwick",
                   "Wukong","Xin Zhao","Zac","Maokai","Trundle","Sylas"},
        "Mid": {"Ahri","Akali","Akshan","Anivia","Annie","Aurelion Sol","Azir",
                "Cassiopeia","Corki","Diana","Ekko","Fizz","Galio","Hwei",
                "Irelia","Kassadin","Katarina","LeBlanc","Lissandra","Lux",
                "Malzahar","Mel","Naafiri","Neeko","Orianna","Pantheon","Qiyana",
                "Ryze","Sylas","Syndra","Taliyah","Talon","Tristana","Twisted Fate",
                "Veigar","Vex","Viktor","Vladimir","Xerath","Yasuo","Yone",
                "Zed","Zoe","Ziggs","Aurora","Jayce","Rumble","Heimerdinger","Zyra"},
        "Bot": {"Aphelios","Ashe","Caitlyn","Corki","Draven","Ezreal","Jhin",
                "Jinx","Kai'Sa","Kalista","Kog'Maw","Lucian","Miss Fortune",
                "Nilah","Samira","Sivir","Smolder","Tristana","Twitch","Varus",
                "Vayne","Xayah","Zeri","Ziggs","Senna"},
        "Support": {"Alistar","Bard","Blitzcrank","Braum","Janna","Karma","Leona",
                    "Lulu","Lux","Mel","Milio","Morgana","Nami","Nautilus","Pyke",
                    "Rakan","Rell","Renata Glasc","Senna","Seraphine","Sona",
                    "Soraka","Taric","Thresh","Yuumi","Zilean","Zyra","Xerath",
                    "Vel'Koz","Maokai","Poppy","Tahm Kench","Galio"},
    }


    def score_champ_for_archetype(champ_name, archetype, champ_tags_data):
        """Score how well a champion fits an archetype (0-1).

        Positive score from subclass needs + tag overlap; penalty when champion
        subclass conflicts with the archetype's style.
        """
        arch = COMP_ARCHETYPES[archetype]
        total_needs = sum(arch["needs"].values())
        matches = sum(1 for need in arch["needs"]
                      if champ_name in CHAMP_SUBCLASSES.get(need, set()))

        # Tag match bonus
        tags = set(champ_tags_data.get(champ_name, []))
        ideal = arch.get("ideal_tags", set())
        tag_overlap = len(tags & ideal)

        score = (matches / max(total_needs, 1)) * 0.7 + (tag_overlap / max(len(ideal), 1)) * 0.3

        # Conflict penalty: subclasses that contradict this archetype subtract 0.2
        conflicts = ARCHETYPE_CONFLICTS.get(archetype, [])
        for conflict_class in conflicts:
            if champ_name in CHAMP_SUBCLASSES.get(conflict_class, set()):
                score -= 0.2
                break  # only penalize once even if multiple conflicts

        return max(score, 0.0)


    def score_team_synergy(picks, champ_tags_data):
        """Score overall team synergy (0-100)."""
        champ_names = [p["champion"].replace(" (off-meta)", "") for p in picks if p["champion"] != "?"]
        if len(champ_names) < 3:
            return 0

        score = 0

        # 1. Damage type balance (AD/AP mix) — 25 points
        ad_count = 0
        ap_count = 0
        for c in champ_names:
            tags = champ_tags_data.get(c, [])
            if "Marksman" in tags or "Fighter" in tags or "Assassin" in tags:
                ad_count += 1
            if "Mage" in tags:
                ap_count += 1
        if ad_count >= 2 and ap_count >= 1:
            score += 25
        elif ad_count >= 1 and ap_count >= 1:
            score += 15
        else:
            score += 5

        # 2. Frontline presence — 25 points
        frontline = sum(1 for c in champ_names if c in CHAMP_SUBCLASSES.get("frontline", set()))
        if frontline >= 2:
            score += 25
        elif frontline == 1:
            score += 15
        else:
            score += 0

        # 3. CC count — 25 points
        cc = sum(1 for c in champ_names if c in CHAMP_SUBCLASSES.get("cc", set())
                 or c in CHAMP_SUBCLASSES.get("engage", set()))
        if cc >= 3:
            score += 25
        elif cc >= 2:
            score += 18
        elif cc >= 1:
            score += 10

        # 4. Win condition clarity — 25 points
        has_carry = any(c in CHAMP_SUBCLASSES.get("hypercarry", set())
                        or c in CHAMP_SUBCLASSES.get("assassin_or_burst", set())
                        or c in CHAMP_SUBCLASSES.get("duelist", set())
                        for c in champ_names)
        has_peel = any(c in CHAMP_SUBCLASSES.get("peel", set())
                       or c in CHAMP_SUBCLASSES.get("engage", set())
                       for c in champ_names)
        if has_carry and has_peel:
            score += 25
        elif has_carry:
            score += 15
        else:
            score += 5

        return score


    def compute_ban_recommendations(team_players, all_scouting, rankings):
        """Compute ban recommendations. Requires 5+ games to be ban-worthy.

        Improvements over v1:
        - Off-role champions penalized 0.4x (player won't play them this game)
        - Role specialists boosted 1.3x (existing behaviour kept)
        - must-ban champions guaranteed to appear in phases 1-3
        """
        ban_candidates = []
        for player_name, role in team_players:
            scout = all_scouting.get(player_name)
            rank_info = rankings.get(player_name, {})
            player_rank = rank_info.get("position", 15)
            rank_weight = max(0.5, 2.0 - (player_rank - 1) * 0.06)
            if not scout: continue

            role_valid = ROLE_VALID.get(role, set())
            role_champs = scout.get("role_champs_flat", {})
            player_role_champs = role_champs.get(role, set()) if role else set()

            for champ in scout.get("champ_list", []):
                games = champ["games"]; wr = champ["wr"]
                if games < 5: continue
                kda_factor = min(champ["kda"] / 3, 1.5)
                base_threat = (wr / 100) * math.sqrt(games) * kda_factor

                # Role-aware modifiers: if we know what the player plays in this role,
                # skip any champion they don't actually play there
                if player_role_champs:
                    if champ["name"] not in player_role_champs:
                        continue
                    role_boost = 1.3  # filtered to role champs — all are specialists
                else:
                    is_role_specialist = role and champ["name"] in role_champs.get(role, set())
                    is_in_role_valid   = not role_valid or champ["name"] in role_valid
                    role_boost = 1.3 if is_role_specialist else (0.4 if (role and not is_in_role_valid) else 1.0)

                is_must_ban = any(mb["name"] == champ["name"] for mb in scout.get("must_bans", []))
                must_ban_boost = 1.5 if is_must_ban else 1.0

                priority = base_threat * rank_weight * role_boost * must_ban_boost
                ban_candidates.append({
                    "champion": champ["name"], "player": player_name,
                    "role": role, "games": games, "wr": wr,
                    "kda": champ["kda"], "priority": round(priority, 2),
                    "player_rank": player_rank,
                    "is_must_ban": is_must_ban})

        # Sort: must-bans first within their priority tier, then by priority
        ban_candidates.sort(key=lambda x: (x["is_must_ban"], x["priority"]), reverse=True)
        seen = set(); final = []
        for b in ban_candidates:
            if b["champion"] not in seen:
                seen.add(b["champion"]); final.append(b)
            if len(final) >= 10: break

        # Assign phase labels for display
        for i, ban in enumerate(final):
            if i < 3:
                ban["phase"] = 1
                ban["phase_reason"] = ("Must ban" if ban["is_must_ban"]
                                       else "High threat flexible pick")
            else:
                ban["phase"] = 2
                ban["phase_reason"] = "Phase 2 — target likely counter-picks"

        return final


    def compute_comp_suggestions(team_players, all_scouting, rankings,
                                 champ_tags_data=None, inhouse_db=None,
                                 enemy_team_players=None, enemy_scouting=None):
        """Smart comp engine. Balances player comfort (33%), archetype fit (33%), win condition (33%).

        Improvements over v1:
        - Uses module-level ROLE_VALID (shared with ban engine)
        - Role specialist comfort boost (1.25x) for champions played in assigned role
        - Scaled in-house boost based on games + WR
        - In-house-only champions included as synthetic candidates
        - Enemy context: counter_potential score added per archetype
        - inhouse_db: dict from load_inhouse_db(), keyed by player name
        - enemy_team_players: list of (name, role) for the opposing team
        - enemy_scouting: all_scouting dict (used to evaluate enemy champ pools)
        """
        if champ_tags_data is None:
            champ_tags_data = {}
        if inhouse_db is None:
            inhouse_db = {}
        if enemy_scouting is None:
            enemy_scouting = all_scouting

        # Pre-compute enemy tendencies for counter scoring
        enemy_squishy_count = 0
        enemy_diver_count = 0
        enemy_frontline_count = 0
        if enemy_team_players:
            for e_name, _e_role in enemy_team_players:
                e_scout = enemy_scouting.get(e_name)
                if not e_scout:
                    continue
                top_champs = [c["name"] for c in e_scout.get("champ_list", [])[:3]]
                squishy_subs = CHAMP_SUBCLASSES.get("assassin_or_burst", set()) | \
                               CHAMP_SUBCLASSES.get("hypercarry", set()) | \
                               CHAMP_SUBCLASSES.get("long_range", set())
                diver_subs = CHAMP_SUBCLASSES.get("engage", set()) | \
                             CHAMP_SUBCLASSES.get("assassin_or_burst", set())
                frontline_subs = CHAMP_SUBCLASSES.get("frontline", set())
                if any(c in squishy_subs for c in top_champs):
                    enemy_squishy_count += 1
                if any(c in diver_subs for c in top_champs):
                    enemy_diver_count += 1
                if any(c in frontline_subs for c in top_champs):
                    enemy_frontline_count += 1

        suggestions = {}

        for archetype, arch_data in COMP_ARCHETYPES.items():
            used_champs = set()

            # Sort players: best ranked first so they get priority
            ranked_players = []
            for player_name, role in team_players:
                rank_info = rankings.get(player_name, {})
                ranked_players.append((player_name, role, rank_info.get("position", 99)))
            ranked_players.sort(key=lambda x: x[2])

            arch_picks = []

            for player_name, role, player_rank in ranked_players:
                scout = all_scouting.get(player_name)
                if not scout:
                    arch_picks.append({
                        "player": player_name, "role": role,
                        "champion": "?", "games": 0, "wr": 0, "kda": 0,
                        "fit": "No data", "comp_score": 0})
                    continue

                valid_for_role = ROLE_VALID.get(role, set())

                # Score each candidate champion
                candidates = []
                for champ in scout.get("champ_list", []):
                    cname = champ["name"]
                    if cname in used_champs:
                        continue
                    if valid_for_role and cname not in valid_for_role:
                        continue

                    # --- COMFORT SCORE (33%) ---
                    # Role specialist boost: player plays this champ in their assigned role
                    role_spec = scout.get("role_champs_flat", {})
                    role_spec_boost = 1.25 if (role and cname in role_spec.get(role, set())) else 1.0

                    # Scaled inhouse boost: more games + higher WR = stronger boost
                    ih = inhouse_db.get(player_name)
                    inhouse_boost = 1.0
                    if ih:
                        ih_champ = next((c for c in ih.get("champs", []) if c.get("name") == cname), None)
                        if ih_champ:
                            ih_games = ih_champ.get("games", 0)
                            ih_wr = ih_champ.get("wr", 0)
                            if ih_games >= 5 and ih_wr >= 60:
                                inhouse_boost = 2.5
                            elif ih_games >= 3:
                                inhouse_boost = 1.8
                            else:
                                inhouse_boost = 1.5

                    comfort = min((champ["wr"] / 100) * math.log(champ["games"] + 1) *
                                 min(champ["kda"] / 2.5, 1.5), 3.0) / 3.0
                    comfort = min(comfort * role_spec_boost * inhouse_boost, 1.0)

                    # --- ARCHETYPE FIT SCORE (33%) ---
                    arch_fit = score_champ_for_archetype(cname, archetype, champ_tags_data)

                    # --- WIN CONDITION SCORE (33%) ---
                    # Best players should be on carries
                    is_carry = (cname in CHAMP_SUBCLASSES.get("hypercarry", set()) or
                               cname in CHAMP_SUBCLASSES.get("assassin_or_burst", set()) or
                               cname in CHAMP_SUBCLASSES.get("duelist", set()))
                    is_top_player = player_rank <= 5
                    if is_carry and is_top_player:
                        win_cond = 1.0
                    elif is_carry:
                        win_cond = 0.7
                    elif not is_carry and not is_top_player:
                        win_cond = 0.6  # utility on weaker player is fine
                    else:
                        win_cond = 0.4

                    total = (comfort * 0.33 + arch_fit * 0.33 + win_cond * 0.33)
                    candidates.append((champ, total, arch_fit))

                # Include in-house-only champions not in ranked data
                ih = inhouse_db.get(player_name)
                if ih and ih.get("champs"):
                    ih_names_in_candidates = {c[0]["name"] for c in candidates if c}
                    for ih_champ in ih["champs"]:
                        cname = ih_champ.get("name", "")
                        if cname in used_champs or cname in ih_names_in_candidates:
                            continue
                        if valid_for_role and cname not in valid_for_role:
                            continue
                        # Create a synthetic champ entry from in-house data
                        synth = {"name": cname, "games": ih_champ.get("games", 0),
                                 "wr": ih_champ.get("wr", 50), "kda": ih_champ.get("kda", 2.0)}
                        # Apply strong inhouse boost since this is custom-only
                        inhouse_boost_synth = 2.0 if ih_champ.get("games", 0) >= 3 else 1.5
                        comfort = min((synth["wr"] / 100) * math.log(synth["games"] + 1) *
                                     min(synth["kda"] / 2.5, 1.5), 3.0) / 3.0 * inhouse_boost_synth
                        comfort = min(comfort, 1.0)
                        arch_fit = score_champ_for_archetype(cname, archetype, champ_tags_data)
                        # Use conservative win condition since no ranked data
                        win_cond = 0.5
                        total = (comfort * 0.33 + arch_fit * 0.33 + win_cond * 0.33)
                        candidates.append((synth, total, arch_fit))

                candidates.sort(key=lambda x: x[1], reverse=True)

                if candidates:
                    best_champ, best_score, best_fit = candidates[0]
                    used_champs.add(best_champ["name"])
                    fit = ("MAIN" if best_champ["games"] >= 5 else
                           "Comfort" if best_champ["games"] >= 3 else
                           "Playable" if best_fit > 0.3 else "Off-meta")
                    arch_picks.append({
                        "player": player_name, "role": role,
                        "champion": best_champ["name"] if best_fit > 0.1 else f"{best_champ['name']} (off-meta)",
                        "games": best_champ["games"],
                        "wr": best_champ["wr"],
                        "kda": best_champ["kda"],
                        "fit": fit,
                        "comp_score": round(best_score, 2),
                    })
                else:
                    arch_picks.append({
                        "player": player_name, "role": role,
                        "champion": "?", "games": 0, "wr": 0, "kda": 0,
                        "fit": "No data", "comp_score": 0})

            # Sort by role for display
            role_order = {"Top": 0, "Jungle": 1, "Mid": 2, "Bot": 3, "Support": 4}
            arch_picks.sort(key=lambda x: role_order.get(x["role"], 5))

            # Score team synergy
            synergy = score_team_synergy(arch_picks, champ_tags_data)
            on_meta = sum(1 for p in arch_picks
                          if "off-meta" not in str(p.get("champion", ""))
                          and p["fit"] != "No data")
            avg_comfort = sum(p.get("comp_score", 0) for p in arch_picks) / max(len(arch_picks), 1)

            # Combined viability score
            combined = synergy * 0.5 + avg_comfort * 50 * 0.3 + on_meta * 10 * 0.2

            # Counter potential: bonus score when this comp counters the enemy
            counter_bonus = 0.0
            if enemy_team_players:
                pick_names = [p["champion"].replace(" (off-meta)", "") for p in arch_picks
                              if p["champion"] != "?"]
                engage_subs = CHAMP_SUBCLASSES.get("engage", set())
                frontline_subs = CHAMP_SUBCLASSES.get("frontline", set())
                long_range_subs = CHAMP_SUBCLASSES.get("long_range", set())
                poke_subs = CHAMP_SUBCLASSES.get("long_range", set()) | \
                            CHAMP_SUBCLASSES.get("waveclear", set())
                if enemy_squishy_count >= 3:
                    counter_bonus += sum(0.15 for c in pick_names if c in engage_subs)
                if enemy_diver_count >= 3:
                    counter_bonus += sum(0.15 for c in pick_names if c in frontline_subs)
                if enemy_frontline_count >= 3:
                    counter_bonus += sum(0.15 for c in pick_names
                                         if c in long_range_subs or c in poke_subs)
            counter_potential = min(int(counter_bonus * 100), 100)

            suggestions[archetype] = {
                "description": arch_data["description"],
                "picks": arch_picks,
                "synergy": synergy,
                "on_meta_count": on_meta,
                "combined_score": round(combined, 1),
                "counter_potential": counter_potential,
                "viability": ("STRONG" if combined >= 35 else
                              "VIABLE" if combined >= 25 else
                              "WEAK" if combined >= 15 else "NOT RECOMMENDED"),
            }

        # ── Filter out comps with 3+ off-meta picks (they don't represent the archetype) ──
        to_remove = []
        for archetype, comp in suggestions.items():
            off_meta_count = sum(1 for p in comp["picks"]
                                if "off-meta" in str(p.get("champion", ""))
                                or p["fit"] == "Off-meta"
                                or p["fit"] == "No data")
            if off_meta_count >= 3:
                to_remove.append(archetype)
        for a in to_remove:
            del suggestions[a]

        # ── Select top 5 comps, then enforce diversity on them ──
        top5 = dict(sorted(suggestions.items(),
            key=lambda x: x[1].get("combined_score", 0), reverse=True)[:5])

        # Enforce diversity: each player must have 3+ unique champs in the 5 shown comps
        for _pass in range(3):  # multiple passes to handle cascading swaps
            player_champ_usage = defaultdict(lambda: defaultdict(list))
            for archetype, comp in top5.items():
                for pick in comp["picks"]:
                    pname = pick["player"]
                    cname = pick["champion"].replace(" (off-meta)", "")
                    player_champ_usage[pname][cname].append(archetype)

            any_swapped = False
            for player_name, champ_usage in player_champ_usage.items():
                if len(champ_usage) >= 3:
                    continue

                scout = all_scouting.get(player_name)
                if not scout: continue
                role = ""
                for tp in team_players:
                    if tp[0] == player_name: role = tp[1]; break
                valid_for_role = ROLE_VALID.get(role, set())

                used_champs = set(champ_usage.keys())
                alternatives = [c for c in scout.get("champ_list", [])
                               if c["name"] not in used_champs and
                               (not valid_for_role or c["name"] in valid_for_role)]

                # Sort shown comps weakest first for swapping
                sorted_archetypes = sorted(top5.keys(),
                    key=lambda a: top5[a].get("combined_score", 0))

                swaps_needed = 3 - len(champ_usage)
                alt_idx = 0
                for arch in sorted_archetypes:
                    if swaps_needed <= 0 or alt_idx >= len(alternatives):
                        break
                    for pick in top5[arch]["picks"]:
                        if pick["player"] == player_name:
                            cname = pick["champion"].replace(" (off-meta)", "")
                            if len(champ_usage.get(cname, [])) > 1:
                                alt = alternatives[alt_idx]
                                arch_fit = score_champ_for_archetype(alt["name"], arch, champ_tags_data)
                                pick["champion"] = alt["name"] if arch_fit > 0.1 else f"{alt['name']} (off-meta)"
                                pick["games"] = alt["games"]
                                pick["wr"] = alt["wr"]
                                pick["kda"] = alt["kda"]
                                pick["fit"] = ("MAIN" if alt["games"] >= 5 else
                                               "Comfort" if alt["games"] >= 3 else
                                               "Off-meta" if arch_fit <= 0.1 else "Playable")
                                alt_idx += 1
                                swaps_needed -= 1
                                any_swapped = True
                            break

            if not any_swapped:
                break

        return top5


    def write_draft_tool(spreadsheet, player_names):
        """Create the Draft Tool sheet with player/role dropdowns."""
        sheet_name = "Draft Tool"
        try:
            old = spreadsheet.worksheet(sheet_name)
            sheets_retry(spreadsheet.del_worksheet, old)
        except gspread.exceptions.WorksheetNotFound:
            pass

        ws = sheets_retry(spreadsheet.add_worksheet, sheet_name, rows=120, cols=14)

        DARK = {"red": 0.11, "green": 0.11, "blue": 0.18}
        HEADER = {"red": 0.09, "green": 0.14, "blue": 0.28}
        GOLD_TEXT = {"red": 0.91, "green": 0.72, "blue": 0.29}
        WHITE = {"red": 1, "green": 1, "blue": 1}
        BLUE_TEAM = {"red": 0.15, "green": 0.25, "blue": 0.55}
        RED_TEAM = {"red": 0.55, "green": 0.15, "blue": 0.15}
        L_BLUE = {"red": 0.85, "green": 0.9, "blue": 1.0}
        L_RED = {"red": 1.0, "green": 0.88, "blue": 0.88}

        rows = []
        fmts = []

        pad = lambda d, n=14: d + [""] * (n - len(d))

        # Title
        rows.append(pad(["IN-HOUSE 5v5 DRAFT TOOL"]))
        fmts.append(("A1:N1", {
            "backgroundColor": DARK,
            "textFormat": {"bold": True, "fontSize": 18, "foregroundColor": GOLD_TEXT},
            "horizontalAlignment": "CENTER"}))

        rows.append(pad(["Select players and roles, then run: python fetch_ranks_gsheets.py --draft"]))
        fmts.append(("A2:N2", {
            "backgroundColor": DARK,
            "textFormat": {"italic": True, "fontSize": 11, "foregroundColor": WHITE},
            "horizontalAlignment": "CENTER"}))

        rows.append(pad([""]))

        # ── TEAM 1 (Blue Side) ──
        rows.append(pad(["TEAM 1 (BLUE SIDE)", "", "", "", "", "", "",
                         "TEAM 2 (RED SIDE)"]))
        fmts.append(("A4:G4", {
            "backgroundColor": BLUE_TEAM,
            "textFormat": {"bold": True, "fontSize": 14, "foregroundColor": WHITE},
            "horizontalAlignment": "CENTER"}))
        fmts.append(("H4:N4", {
            "backgroundColor": RED_TEAM,
            "textFormat": {"bold": True, "fontSize": 14, "foregroundColor": WHITE},
            "horizontalAlignment": "CENTER"}))

        rows.append(pad(["Slot", "Player", "Role", "", "", "", "",
                         "Slot", "Player", "Role"]))
        fmts.append(("A5:C5", {
            "backgroundColor": HEADER,
            "textFormat": {"bold": True, "foregroundColor": WHITE},
            "horizontalAlignment": "CENTER"}))
        fmts.append(("H5:J5", {
            "backgroundColor": HEADER,
            "textFormat": {"bold": True, "foregroundColor": WHITE},
            "horizontalAlignment": "CENTER"}))

        roles = ["Top", "Jungle", "Mid", "Bot", "Support"]
        for i, role in enumerate(roles):
            r = pad([i + 1, "", role, "", "", "", "", i + 1, "", role])
            rows.append(r)
            fmts.append((f"A{6+i}:C{6+i}", {
                "backgroundColor": L_BLUE,
                "textFormat": {"fontSize": 12},
                "horizontalAlignment": "CENTER"}))
            fmts.append((f"H{6+i}:J{6+i}", {
                "backgroundColor": L_RED,
                "textFormat": {"fontSize": 12},
                "horizontalAlignment": "CENTER"}))

        # Spacer
        rows.append(pad([""]))
        rows.append(pad([""]))

        # ── BAN RECOMMENDATIONS (filled by --draft) ──
        ban_start = len(rows) + 1
        rows.append(pad(["RECOMMENDED BANS VS TEAM 2", "", "", "", "", "", "",
                         "RECOMMENDED BANS VS TEAM 1"]))
        fmts.append((f"A{ban_start}:G{ban_start}", {
            "backgroundColor": BLUE_TEAM,
            "textFormat": {"bold": True, "fontSize": 13, "foregroundColor": WHITE},
            "horizontalAlignment": "CENTER"}))
        fmts.append((f"H{ban_start}:N{ban_start}", {
            "backgroundColor": RED_TEAM,
            "textFormat": {"bold": True, "fontSize": 13, "foregroundColor": WHITE},
            "horizontalAlignment": "CENTER"}))

        rows.append(pad(["Phase", "Ban", "Target Player", "WR%", "Games", "Priority", "",
                         "Phase", "Ban", "Target Player", "WR%", "Games", "Priority"]))
        fmts.append((f"A{ban_start+1}:F{ban_start+1}", {
            "backgroundColor": HEADER,
            "textFormat": {"bold": True, "fontSize": 10, "foregroundColor": WHITE},
            "horizontalAlignment": "CENTER"}))
        fmts.append((f"H{ban_start+1}:N{ban_start+1}", {
            "backgroundColor": HEADER,
            "textFormat": {"bold": True, "fontSize": 10, "foregroundColor": WHITE},
            "horizontalAlignment": "CENTER"}))

        ban_labels = ["1st Ban", "2nd Ban", "3rd Ban", "4th Ban", "5th Ban"]
        for i, label in enumerate(ban_labels):
            phase = "FIRST PHASE" if i < 3 else "SECOND PHASE"
            rows.append(pad([phase, "(run --draft)", "", "", "", "", "",
                             phase, "(run --draft)", "", "", "", ""]))
            bg = {"red": 0.95, "green": 0.92, "blue": 1.0} if i < 3 else {"red": 0.92, "green": 0.95, "blue": 1.0}
            fmts.append((f"A{ban_start+2+i}:F{ban_start+2+i}", {
                "backgroundColor": bg,
                "textFormat": {"fontSize": 11},
                "horizontalAlignment": "CENTER"}))
            fmts.append((f"H{ban_start+2+i}:N{ban_start+2+i}", {
                "backgroundColor": bg,
                "textFormat": {"fontSize": 11},
                "horizontalAlignment": "CENTER"}))

        # Spacer
        rows.append(pad([""]))
        rows.append(pad([""]))

        # ── COMP SUGGESTIONS HEADER ──
        comp_start = len(rows) + 1
        rows.append(pad(["TEAM 1 COMP SUGGESTIONS"]))
        fmts.append((f"A{comp_start}:N{comp_start}", {
            "backgroundColor": BLUE_TEAM,
            "textFormat": {"bold": True, "fontSize": 14, "foregroundColor": WHITE},
            "horizontalAlignment": "CENTER"}))

        rows.append(pad(["(Run --draft to generate comp suggestions based on selected players)"]))
        fmts.append((f"A{comp_start+1}:N{comp_start+1}", {
            "backgroundColor": {"red": 0.2, "green": 0.3, "blue": 0.5},
            "textFormat": {"italic": True, "fontSize": 11, "foregroundColor": WHITE},
            "horizontalAlignment": "CENTER"}))

        # Spacer for comp data (will be filled by --draft)
        for _ in range(35):
            rows.append(pad([""]))

        comp2_start = len(rows) + 1
        rows.append(pad(["TEAM 2 COMP SUGGESTIONS"]))
        fmts.append((f"A{comp2_start}:N{comp2_start}", {
            "backgroundColor": RED_TEAM,
            "textFormat": {"bold": True, "fontSize": 14, "foregroundColor": WHITE},
            "horizontalAlignment": "CENTER"}))

        rows.append(pad(["(Run --draft to generate comp suggestions based on selected players)"]))

        # Write all data
        sheets_retry(ws.update, range_name="A1", values=rows)
        sheets_retry(ws.merge_cells, "A1:N1")
        sheets_retry(ws.merge_cells, "A2:N2")

        # Add data validation dropdowns for player selection
        role_list = "Top,Jungle,Mid,Bot,Support"

        # Use Sheets API for data validation
        reqs = []
        for row_idx in range(5, 10):  # 0-indexed rows 5-9 = sheet rows 6-10
            # Team 1 player (column B = index 1)
            reqs.append({
                "setDataValidation": {
                    "range": {"sheetId": ws.id, "startRowIndex": row_idx, "endRowIndex": row_idx + 1,
                              "startColumnIndex": 1, "endColumnIndex": 2},
                    "rule": {"condition": {"type": "ONE_OF_LIST",
                                           "values": [{"userEnteredValue": n} for n in player_names]},
                             "showCustomUi": True, "strict": False}
                }
            })
            # Team 1 role (column C = index 2)
            reqs.append({
                "setDataValidation": {
                    "range": {"sheetId": ws.id, "startRowIndex": row_idx, "endRowIndex": row_idx + 1,
                              "startColumnIndex": 2, "endColumnIndex": 3},
                    "rule": {"condition": {"type": "ONE_OF_LIST",
                                           "values": [{"userEnteredValue": r} for r in roles]},
                             "showCustomUi": True, "strict": False}
                }
            })
            # Team 2 player (column I = index 8)
            reqs.append({
                "setDataValidation": {
                    "range": {"sheetId": ws.id, "startRowIndex": row_idx, "endRowIndex": row_idx + 1,
                              "startColumnIndex": 8, "endColumnIndex": 9},
                    "rule": {"condition": {"type": "ONE_OF_LIST",
                                           "values": [{"userEnteredValue": n} for n in player_names]},
                             "showCustomUi": True, "strict": False}
                }
            })
            # Team 2 role (column J = index 9)
            reqs.append({
                "setDataValidation": {
                    "range": {"sheetId": ws.id, "startRowIndex": row_idx, "endRowIndex": row_idx + 1,
                              "startColumnIndex": 9, "endColumnIndex": 10},
                    "rule": {"condition": {"type": "ONE_OF_LIST",
                                           "values": [{"userEnteredValue": r} for r in roles]},
                             "showCustomUi": True, "strict": False}
                }
            })

        # Column widths
        col_px = [80, 130, 150, 110, 70, 70, 110, 80, 130, 150, 110, 70, 70, 110]
        for ci, px in enumerate(col_px):
            reqs.append({"updateDimensionProperties": {
                "range": {"sheetId": ws.id, "dimension": "COLUMNS",
                          "startIndex": ci, "endIndex": ci + 1},
                "properties": {"pixelSize": px}, "fields": "pixelSize"}})

        # Row 1 height
        reqs.append({"updateDimensionProperties": {
            "range": {"sheetId": ws.id, "dimension": "ROWS",
                      "startIndex": 0, "endIndex": 1},
            "properties": {"pixelSize": 50}, "fields": "pixelSize"}})

        sheets_retry(spreadsheet.batch_update, {"requests": reqs})

        # Apply formats
        for i in range(0, len(fmts), 15):
            batch = [{"range": r, "format": f} for r, f in fmts[i:i+15]]
            sheets_retry(ws.batch_format, batch)

        print("  Draft Tool created with dropdowns")


    def run_draft(spreadsheet, all_scouting, rankings, champ_tags_data=None):
        """Read team selections from Draft Tool and compute bans + comps."""
        try:
            ws = spreadsheet.worksheet("Draft Tool")
        except gspread.exceptions.WorksheetNotFound:
            print("  Draft Tool sheet not found. Run --setup-draft first.")
            return [], []

        values = ws.get_all_values()

        team1 = []
        team2 = []
        for i in range(5, 10):
            if i < len(values):
                row = values[i]
                p1 = row[1].strip() if len(row) > 1 else ""
                r1 = row[2].strip() if len(row) > 2 else ""
                if p1:
                    team1.append((p1, r1))
                p2 = row[8].strip() if len(row) > 8 else ""
                r2 = row[9].strip() if len(row) > 9 else ""
                if p2:
                    team2.append((p2, r2))

        if not team1 and not team2:
            print("  No players selected. Fill in the Draft Tool dropdowns first.")
            return [], []

        print(f"  Team 1: {', '.join(f'{p} ({r})' for p, r in team1)}")
        print(f"  Team 2: {', '.join(f'{p} ({r})' for p, r in team2)}")

        for name, scout in all_scouting.items():
            role_champs_flat = {}
            for role, champs in scout.get("role_champs", {}).items():
                role_champs_flat[role] = set(champs.keys())
            scout["role_champs_flat"] = role_champs_flat

        # Load in-house data first so comp suggestions can use it
        print("  Loading in-house custom game data...")
        inhouse_db = load_inhouse_db(spreadsheet)
        if inhouse_db:
            print(f"  Found inhouse data for {len(inhouse_db)} players")

        print("\n  Computing ban recommendations...")
        bans_vs_t2 = compute_ban_recommendations(team2, all_scouting, rankings)
        bans_vs_t1 = compute_ban_recommendations(team1, all_scouting, rankings)

        print("  Computing comp suggestions...")
        comps_t1 = compute_comp_suggestions(team1, all_scouting, rankings,
                                            champ_tags_data, inhouse_db=inhouse_db,
                                            enemy_team_players=team2,
                                            enemy_scouting=all_scouting)
        comps_t2 = compute_comp_suggestions(team2, all_scouting, rankings,
                                            champ_tags_data, inhouse_db=inhouse_db,
                                            enemy_team_players=team1,
                                            enemy_scouting=all_scouting)

        # Build name-to-riot-name mapping from Players sheet
        riot_name_map = {}
        try:
            ws_p = spreadsheet.worksheet("Players")
            pv = ws_p.get_all_values()
            for row in pv[2:]:
                if len(row) >= 3 and "#" in str(row[2]):
                    riot_name_map[row[1].strip()] = row[2].rsplit("#", 1)[0]
        except Exception as e:
            print(f"Warning: riot name map build failed: {e}")

        def get_inhouse(player_name):
            ih = inhouse_db.get(player_name)
            if ih: return ih
            riot_name = riot_name_map.get(player_name, "")
            if riot_name:
                ih = inhouse_db.get(riot_name)
                if ih: return ih
            return None

        def get_top_custom_champ(player_name, role=""):
            ih = get_inhouse(player_name)
            if ih and ih["champs"]:
                # Try role-specific first
                if role:
                    for c in ih["champs"]:
                        if c.get("roles", {}).get(role, 0) > 0:
                            return f"{c['name']} ({c['games']}g / {c['wr']}% WR)"
                # Fallback to overall top
                c = ih["champs"][0]
                return f"{c['name']} ({c['games']}g / {c['wr']}% WR)"
            return "No custom data"

        # ── Delete and recreate sheet to avoid write limit issues ──
        sheet_id = ws.id
        sheets_retry(spreadsheet.del_worksheet, ws)
        ws = sheets_retry(spreadsheet.add_worksheet, "Draft Tool", rows=200, cols=14)
        time.sleep(1)  # needed for the sheet to be available after recreation

        DARK = {"red": 0.11, "green": 0.11, "blue": 0.18}
        HEADER = {"red": 0.09, "green": 0.14, "blue": 0.28}
        BLUE_TEAM = {"red": 0.15, "green": 0.25, "blue": 0.55}
        RED_TEAM = {"red": 0.55, "green": 0.15, "blue": 0.15}
        WHITE = {"red": 1, "green": 1, "blue": 1}
        GOLD_TEXT = {"red": 0.91, "green": 0.72, "blue": 0.29}
        L_RED = {"red": 1.0, "green": 0.88, "blue": 0.88}
        L_BLUE = {"red": 0.88, "green": 0.92, "blue": 1.0}
        L_GREEN = {"red": 0.85, "green": 0.95, "blue": 0.85}
        L_GOLD = {"red": 1.0, "green": 0.97, "blue": 0.88}
        SECTION = {"red": 0.13, "green": 0.17, "blue": 0.30}

        rows = []
        fmts = []
        merges = []
        pad = lambda d, n=14: d + [""] * (n - len(d))

        def rn():
            return len(rows)

        # ── TITLE ──
        rows.append(pad(["IN-HOUSE 5v5 DRAFT TOOL"]))
        merges.append(f"A{rn()}:N{rn()}")
        fmts.append((f"A{rn()}:N{rn()}", {
            "backgroundColor": DARK,
            "textFormat": {"bold": True, "fontSize": 18, "foregroundColor": GOLD_TEXT},
            "horizontalAlignment": "CENTER"}))

        rows.append(pad([""]))

        # ── TEAM ROSTERS ──
        rows.append(pad(["TEAM 1 (BLUE SIDE)", "", "", "", "", "", "",
                         "TEAM 2 (RED SIDE)"]))
        merges.append(f"A{rn()}:F{rn()}")
        merges.append(f"H{rn()}:N{rn()}")
        fmts.append((f"A{rn()}:F{rn()}", {
            "backgroundColor": BLUE_TEAM,
            "textFormat": {"bold": True, "fontSize": 14, "foregroundColor": WHITE},
            "horizontalAlignment": "CENTER"}))
        fmts.append((f"H{rn()}:N{rn()}", {
            "backgroundColor": RED_TEAM,
            "textFormat": {"bold": True, "fontSize": 14, "foregroundColor": WHITE},
            "horizontalAlignment": "CENTER"}))

        rows.append(pad(["Role", "Player", "Rank", "Top Custom Champ", "", "", "",
                         "Role", "Player", "Rank", "Top Custom Champ"]))
        fmts.append((f"A{rn()}:D{rn()}", {
            "backgroundColor": HEADER,
            "textFormat": {"bold": True, "foregroundColor": WHITE},
            "horizontalAlignment": "CENTER"}))
        fmts.append((f"H{rn()}:K{rn()}", {
            "backgroundColor": HEADER,
            "textFormat": {"bold": True, "foregroundColor": WHITE},
            "horizontalAlignment": "CENTER"}))

        for i in range(5):
            t1_role = team1[i][1] if i < len(team1) else ""
            t1_name = team1[i][0] if i < len(team1) else ""
            t1_rank = f"#{rankings.get(t1_name, {}).get('position', '?')}" if t1_name else ""
            t1_champ = get_top_custom_champ(t1_name, t1_role) if t1_name else ""
            t2_role = team2[i][1] if i < len(team2) else ""
            t2_name = team2[i][0] if i < len(team2) else ""
            t2_rank = f"#{rankings.get(t2_name, {}).get('position', '?')}" if t2_name else ""
            t2_champ = get_top_custom_champ(t2_name, t2_role) if t2_name else ""

            rows.append(pad([t1_role, t1_name, t1_rank, t1_champ, "", "", "",
                             t2_role, t2_name, t2_rank, t2_champ]))
            bg = L_BLUE if i % 2 == 0 else {"red": 0.92, "green": 0.95, "blue": 1.0}
            fmts.append((f"A{rn()}:D{rn()}", {
                "backgroundColor": bg,
                "textFormat": {"bold": True, "fontSize": 12},
                "horizontalAlignment": "CENTER"}))
            bg2 = L_RED if i % 2 == 0 else {"red": 1.0, "green": 0.93, "blue": 0.93}
            fmts.append((f"H{rn()}:K{rn()}", {
                "backgroundColor": bg2,
                "textFormat": {"bold": True, "fontSize": 12},
                "horizontalAlignment": "CENTER"}))

        rows.append(pad([""]))
        rows.append(pad([""]))

        # ── BAN RECOMMENDATIONS ──
        rows.append(pad(["RECOMMENDED BANS vs TEAM 2 (Blue bans)", "", "", "", "", "",
                         "", "RECOMMENDED BANS vs TEAM 1 (Red bans)"]))
        merges.append(f"A{rn()}:F{rn()}")
        merges.append(f"H{rn()}:N{rn()}")
        fmts.append((f"A{rn()}:F{rn()}", {
            "backgroundColor": BLUE_TEAM,
            "textFormat": {"bold": True, "fontSize": 13, "foregroundColor": WHITE},
            "horizontalAlignment": "CENTER"}))
        fmts.append((f"H{rn()}:N{rn()}", {
            "backgroundColor": RED_TEAM,
            "textFormat": {"bold": True, "fontSize": 13, "foregroundColor": WHITE},
            "horizontalAlignment": "CENTER"}))

        rows.append(pad(["Phase", "BAN", "Target", "WR%", "Games", "Priority",
                         "", "Phase", "BAN", "Target", "WR%", "Games", "Priority"]))
        fmts.append((f"A{rn()}:F{rn()}", {
            "backgroundColor": HEADER,
            "textFormat": {"bold": True, "fontSize": 10, "foregroundColor": WHITE},
            "horizontalAlignment": "CENTER"}))
        fmts.append((f"H{rn()}:N{rn()}", {
            "backgroundColor": HEADER,
            "textFormat": {"bold": True, "fontSize": 10, "foregroundColor": WHITE},
            "horizontalAlignment": "CENTER"}))

        for i in range(5):
            phase = "1st Phase" if i < 3 else "2nd Phase"
            b1 = bans_vs_t2[i] if i < len(bans_vs_t2) else None
            b2 = bans_vs_t1[i] if i < len(bans_vs_t1) else None

            def _ban_label(b):
                if not b: return "-"
                return f"⚠ {b['champion']}" if b.get("is_must_ban") else b["champion"]

            row_data = [
                phase,
                _ban_label(b1),
                b1["player"] if b1 else "-",
                f"{b1['wr']}%" if b1 else "-",
                b1["games"] if b1 else "-",
                round(b1["priority"], 1) if b1 else "-",
                "",
                phase,
                _ban_label(b2),
                b2["player"] if b2 else "-",
                f"{b2['wr']}%" if b2 else "-",
                b2["games"] if b2 else "-",
                round(b2["priority"], 1) if b2 else "-",
                "",
            ]
            rows.append(row_data)
            bg = L_RED if i < 3 else L_BLUE
            fmts.append((f"A{rn()}:F{rn()}", {
                "backgroundColor": bg,
                "textFormat": {"bold": True, "fontSize": 11},
                "horizontalAlignment": "CENTER"}))
            fmts.append((f"H{rn()}:N{rn()}", {
                "backgroundColor": bg,
                "textFormat": {"bold": True, "fontSize": 11},
                "horizontalAlignment": "CENTER"}))

        rows.append(pad([""]))
        rows.append(pad([""]))

        # ── COMP SUGGESTIONS ──
        for team_label, comps, team_color in [
            ("TEAM 1", comps_t1, BLUE_TEAM),
            ("TEAM 2", comps_t2, RED_TEAM),
        ]:
            rows.append(pad([f"{team_label} COMP SUGGESTIONS"]))
            merges.append(f"A{rn()}:N{rn()}")
            fmts.append((f"A{rn()}:N{rn()}", {
                "backgroundColor": team_color,
                "textFormat": {"bold": True, "fontSize": 15, "foregroundColor": WHITE},
                "horizontalAlignment": "CENTER"}))

            sorted_comps = sorted(comps.items(),
                                  key=lambda x: x[1].get("combined_score", 0), reverse=True)

            for archetype, comp in sorted_comps:
                viability = comp["viability"]
                v_colors = {
                    "STRONG": {"red": 0.1, "green": 0.5, "blue": 0.1},
                    "VIABLE": {"red": 0.3, "green": 0.5, "blue": 0.2},
                    "WEAK": {"red": 0.6, "green": 0.4, "blue": 0.1},
                    "NOT RECOMMENDED": {"red": 0.5, "green": 0.2, "blue": 0.2},
                }

                ctr = comp.get("counter_potential", 0)
                ctr_str = f" | Counter: {ctr}/100" if ctr > 0 else ""
                rows.append(pad([f"{archetype.upper()} — {comp['description']}",
                                 "", "", "", "", "", "",
                                 f"{viability} | Synergy: {comp.get('synergy', 0)}/100 | {comp['on_meta_count']}/5 on-meta{ctr_str}"]))
                merges.append(f"A{rn()}:G{rn()}")
                merges.append(f"H{rn()}:N{rn()}")
                fmts.append((f"A{rn()}:N{rn()}", {
                    "backgroundColor": v_colors.get(viability, SECTION),
                    "textFormat": {"bold": True, "fontSize": 12, "foregroundColor": WHITE},
                    "horizontalAlignment": "CENTER"}))

                rows.append(pad(["Player", "Role", "Champion", "Games", "Win Rate",
                                 "KDA", "Fit Level"]))
                fmts.append((f"A{rn()}:G{rn()}", {
                    "backgroundColor": HEADER,
                    "textFormat": {"bold": True, "fontSize": 10, "foregroundColor": WHITE},
                    "horizontalAlignment": "CENTER"}))

                for pick in comp["picks"]:
                    bg = (L_GREEN if pick["fit"] == "MAIN" else
                          L_GOLD if pick["fit"] == "Comfort" else
                          L_RED if pick["fit"] == "Off-meta" else
                          {"red": 1, "green": 1, "blue": 1})
                    rows.append(pad([pick["player"], pick["role"], pick["champion"],
                                     pick.get("games", 0),
                                     f"{pick.get('wr', 0)}%",
                                     pick.get("kda", 0),
                                     pick["fit"]]))
                    fmts.append((f"A{rn()}:G{rn()}", {
                        "backgroundColor": bg,
                        "textFormat": {"fontSize": 11},
                        "horizontalAlignment": "CENTER"}))

                rows.append(pad([""]))  # spacer

            rows.append(pad([""]))

        # ── SINGLE BATCH WRITE ──
        sheets_retry(ws.update, values=rows, range_name="A1")

        # Apply merges
        for m in merges:
            sheets_retry(ws.merge_cells, m)

        # Column widths
        col_px = [80, 130, 150, 110, 70, 70, 110, 80, 130, 150, 110, 70, 70, 110]
        reqs = []
        for ci, px in enumerate(col_px):
            reqs.append({"updateDimensionProperties": {
                "range": {"sheetId": ws.id, "dimension": "COLUMNS",
                          "startIndex": ci, "endIndex": ci + 1},
                "properties": {"pixelSize": px}, "fields": "pixelSize"}})
        reqs.append({"updateDimensionProperties": {
            "range": {"sheetId": ws.id, "dimension": "ROWS",
                      "startIndex": 0, "endIndex": 1},
            "properties": {"pixelSize": 50}, "fields": "pixelSize"}})
        sheets_retry(spreadsheet.batch_update, {"requests": reqs})

        # Apply formats in batches
        for i in range(0, len(fmts), 15):
            batch = [{"range": r, "format": f} for r, f in fmts[i:i+15]]
            sheets_retry(ws.batch_format, batch)

        print("\n  Draft Tool updated with bans and comp suggestions!")
        return team1, team2


    def append_activity_event(spreadsheet, event_type, player_name, details):
        """Append one event row to the _Activity log sheet."""
        sheet_name = "_Activity"
        try:
            ws = get_or_create_sheet(spreadsheet, sheet_name, rows=200, cols=4)
            # Write header row if the sheet is brand new
            if not ws.get_all_values():
                sheets_retry(ws.append_row, ["_ACTIVITY LOG", "", "", ""],
                             value_input_option="RAW")
            sheets_retry(ws.append_row,
                         [datetime.now().strftime("%Y-%m-%d %H:%M"), event_type,
                          player_name or "", details],
                         value_input_option="RAW")
        except Exception as e:
            print(f"  (Activity log write skipped: {e})")


    def load_activity_log(spreadsheet, limit=50):
        """Return the most recent `limit` activity events as a list of dicts."""
        try:
            ws = spreadsheet.worksheet("_Activity")
        except Exception as e:
            print(f"Warning: could not load activity log: {e}")
            return []
        rows = ws.get_all_values()
        # Skip header row; rows are oldest-first
        data_rows = [r for r in rows if len(r) >= 4 and r[0] != "_ACTIVITY LOG" and r[0]]
        recent = data_rows[-limit:]
        recent.reverse()  # newest first
        return [
            {"ts": r[0], "type": r[1], "player": r[2], "details": r[3]}
            for r in recent
        ]


    def write_scouting_database(spreadsheet, all_scouting, rankings):
        """Save scouting data to a hidden sheet so --draft can use it later."""
        sheet_name = "_ScoutDB"
        try:
            old = spreadsheet.worksheet(sheet_name)
            sheets_retry(spreadsheet.del_worksheet, old)
        except gspread.exceptions.WorksheetNotFound:
            pass

        ws = sheets_retry(spreadsheet.add_worksheet, sheet_name, rows=500, cols=15)

        rows = [["SCOUTING DATABASE - DO NOT EDIT", "", "", "", "", "",
                 datetime.now().strftime("%Y-%m-%d %H:%M")]]
        rows.append(["player", "champ", "games", "wins", "wr", "kda",
                     "avg_kills", "avg_deaths", "avg_assists", "avg_cs_min",
                     "avg_damage", "avg_gold", "role_data", "rank_pos", "rank_score"])

        for player_name, analysis in all_scouting.items():
            rank_info = rankings.get(player_name, {})
            rank_pos = rank_info.get("position", 99)
            rank_score = rank_info.get("score", 0)

            for champ in analysis.get("champ_list", []):
                # Build role data string
                role_str = ""
                for role, champs in analysis.get("role_champs", {}).items():
                    if champ["name"] in champs:
                        role_str += f"{role}:{champs[champ['name']]['games']};"

                rows.append([
                    player_name, champ["name"], champ["games"], champ["wins"],
                    champ["wr"], champ["kda"], champ["avg_kills"], champ["avg_deaths"],
                    champ["avg_assists"], champ["avg_cs_min"], champ["avg_damage"],
                    champ["avg_gold"], role_str, rank_pos, rank_score,
                ])

        sheets_retry(ws.update, range_name="A1", values=rows)
        print(f"  Scouting database saved ({len(all_scouting)} players)")


    def load_scouting_database(spreadsheet):
        """Load scouting data from the hidden database sheet."""
        try:
            ws = spreadsheet.worksheet("_ScoutDB")
        except gspread.exceptions.WorksheetNotFound:
            return {}, {}

        values = ws.get_all_values()
        if len(values) < 3:
            return {}, {}

        all_scouting = {}
        rankings = {}

        for row in values[2:]:  # skip header rows
            if len(row) < 12 or not row[0]:
                continue
            player = row[0]
            if player not in all_scouting:
                all_scouting[player] = {
                    "champ_list": [], "must_bans": [], "role_champs": {},
                }

            try:
                games = int(row[2]) if row[2] else 0
                wins = int(row[3]) if row[3] else 0
                wr = float(row[4]) if row[4] else 0
                kda = float(row[5]) if row[5] else 0
                rank_pos = int(row[13]) if len(row) > 13 and row[13] else 99
                rank_score = float(row[14]) if len(row) > 14 and row[14] else 0
            except (ValueError, IndexError):
                continue

            champ = {
                "name": row[1], "games": games, "wins": wins,
                "losses": games - wins, "wr": wr, "kda": kda,
                "avg_kills": float(row[6]) if row[6] else 0,
                "avg_deaths": float(row[7]) if row[7] else 0,
                "avg_assists": float(row[8]) if row[8] else 0,
                "avg_cs_min": float(row[9]) if row[9] else 0,
                "avg_damage": int(float(row[10])) if row[10] else 0,
                "avg_gold": int(float(row[11])) if row[11] else 0,
            }

            all_scouting[player]["champ_list"].append(champ)
            if games >= 5 and wr >= 65:
                all_scouting[player]["must_bans"].append(champ)

            # Parse role data
            if len(row) > 12 and row[12]:
                for part in row[12].split(";"):
                    if ":" in part:
                        role, count = part.split(":")
                        if role not in all_scouting[player]["role_champs"]:
                            all_scouting[player]["role_champs"][role] = {}
                        all_scouting[player]["role_champs"][role][row[1]] = {
                            "games": int(count), "wins": 0}

            rankings[player] = {"position": rank_pos, "score": rank_score,
                                "rating": "?"}

        return all_scouting, rankings



    # ── In-House Stats Tracker ────────────────────────────────────

    def fetch_custom_matches(puuid, routing, api_key, count=25):
        """Fetch ALL match IDs from the last 60 days using time-based pagination."""
        # Go back 60 days
        end_time = int(time.time())
        start_time = end_time - (60 * 24 * 60 * 60)

        all_ids = []
        start_idx = 0

        while True:
            ids = riot_get(
                f"https://{routing}.api.riotgames.com/lol/match/v5/matches/"
                f"by-puuid/{puuid}/ids?startTime={start_time}&endTime={end_time}"
                f"&start={start_idx}&count=100", api_key)
            if not ids:
                break
            all_ids.extend(ids)
            if len(ids) < 100:
                break  # no more pages
            start_idx += 100
            time.sleep(0.5)

        return all_ids


    def fetch_and_filter_inhouse(all_puuids, player_puuid_map, routing, region, api_key, count=25):
        """
        Fetch custom games across all players, deduplicate, and filter for
        true in-house games (5v5 with multiple group members).
        Returns list of match dicts with full participant data.
        """
        all_match_ids = set()
        player_match_ids = {}

        # Collect match IDs from all players
        print("\n  Collecting custom game IDs from all players...")
        for name, puuid in player_puuid_map.items():
            ids = fetch_custom_matches(puuid, routing, api_key, count)
            player_match_ids[name] = ids
            all_match_ids.update(ids)
            print(f"    {name}: {len(ids)} custom games found")
            time.sleep(0.8)

        print(f"\n  {len(all_match_ids)} unique matches found across all players (last 60 days)")

        # Pre-filter: in-house 5v5 must appear in many players' histories
        # A game with 5+ group members will show up in 5+ match lists
        match_count = defaultdict(int)
        for name, ids in player_match_ids.items():
            for mid in ids:
                match_count[mid] += 1

        # Games in 5+ players' histories are almost certainly in-houses
        candidates = [mid for mid, cnt in match_count.items() if cnt >= 5]
        # Also check games in 3-4 players' histories (could be customs with some non-group members)
        maybe_candidates = [mid for mid, cnt in match_count.items() if cnt >= 3 and cnt < 5]

        all_candidates = candidates + maybe_candidates
        print(f"  {len(candidates)} matches in 5+ players' histories (very likely in-house)")
        print(f"  {len(maybe_candidates)} matches in 3-4 players' histories (possible in-house)")
        print(f"  Checking {len(all_candidates)} candidate matches...")

        # Fetch each candidate match
        inhouse_matches = []
        checked = 0
        queue_ids_seen = defaultdict(int)
        group_puuids = set(all_puuids)
        for mid in all_candidates:
            time.sleep(0.5)
            mdata = riot_get(
                f"https://{routing}.api.riotgames.com/lol/match/v5/matches/{mid}",
                api_key)
            checked += 1
            if not mdata:
                continue

            info = mdata.get("info", {})
            participants = info.get("participants", [])
            queue_id = info.get("queueId", -1)
            game_mode = info.get("gameMode", "")
            game_type = info.get("gameType", "")
            queue_ids_seen[f"{queue_id} ({game_mode}/{game_type})"] += 1

            # Must be 10 participants (5v5)
            if len(participants) != 10:
                continue

            # Count group members in this game
            game_puuids = set(p.get("puuid", "") for p in participants)
            overlap = group_puuids & game_puuids
            group_count = len(overlap)

            # Detection:
            # - Queue 0/3130/CUSTOM_GAME with 3+ group = custom in-house
            # - Any non-ranked-solo queue with 5+ group members = likely in-house
            is_custom_queue = (queue_id == 0 or queue_id == 3130 or game_type == "CUSTOM_GAME")

            if is_custom_queue and group_count >= 3:
                pass  # accept
            elif group_count >= 6 and queue_id != 420:
                pass  # accept
            else:
                continue

            # This is an in-house game — extract all data
            match_data = {
                "match_id": mid,
                "duration_min": round(info.get("gameDuration", 0) / 60, 1),
                "timestamp": info.get("gameCreation", 0),
                "players": [],
            }

            for p in participants:
                puuid = p.get("puuid", "")
                # Reverse lookup name
                pname = None
                for name, pid in player_puuid_map.items():
                    if pid == puuid:
                        pname = name
                        break

                cs = p.get("totalMinionsKilled", 0) + p.get("neutralMinionsKilled", 0)
                dur = max(info.get("gameDuration", 1) / 60, 0.1)

                match_data["players"].append({
                    "puuid": puuid,
                    "name": pname or p.get("riotIdGameName", "Unknown"),
                    "is_group": puuid in group_puuids,
                    "champion": p.get("championName", "?"),
                    "team_id": p.get("teamId", 0),
                    "win": p.get("win", False),
                    "kills": p.get("kills", 0),
                    "deaths": p.get("deaths", 0),
                    "assists": p.get("assists", 0),
                    "cs": cs,
                    "cs_min": round(cs / dur, 1),
                    "damage": p.get("totalDamageDealtToChampions", 0),
                    "gold": p.get("goldEarned", 0),
                    "vision": p.get("visionScore", 0),
                    "role": p.get("teamPosition", "UNKNOWN"),
                })

            inhouse_matches.append(match_data)

            if checked % 20 == 0:
                print(f"    Checked {checked}/{len(all_candidates)}, found {len(inhouse_matches)} in-house games")

        print(f"\n  Found {len(inhouse_matches)} in-house 5v5 games total")
        print(f"  Queue types seen across all matches:")
        for qt, cnt in sorted(queue_ids_seen.items(), key=lambda x: x[1], reverse=True):
            print(f"    {qt}: {cnt} games")
        return inhouse_matches


    def analyze_inhouse(inhouse_matches, player_puuid_map):
        """Crunch all in-house stats."""
        puuid_to_name = {v: k for k, v in player_puuid_map.items()}
        group_names = set(player_puuid_map.keys())

        # Per-player overall stats
        player_stats = defaultdict(lambda: {
            "games": 0, "wins": 0, "kills": 0, "deaths": 0, "assists": 0,
            "cs_min": 0, "damage": 0, "gold": 0, "vision": 0,
            "champs": defaultdict(lambda: {"games": 0, "wins": 0, "kills": 0,
                                            "deaths": 0, "assists": 0, "damage": 0}),
            "roles": defaultdict(lambda: {"games": 0, "wins": 0}),
        })

        # Head-to-head: h2h[playerA][playerB] = {"same_team": 0, "same_wins": 0,
        #                                         "vs": 0, "vs_wins": 0}
        h2h = defaultdict(lambda: defaultdict(lambda: {
            "same_team": 0, "same_wins": 0, "vs": 0, "vs_wins": 0}))

        role_map = {"TOP": "Top", "JUNGLE": "Jungle", "MIDDLE": "Mid",
                    "BOTTOM": "Bot", "UTILITY": "Support", "UNKNOWN": "Fill"}

        for match in inhouse_matches:
            # Group players by team
            team_100 = []
            team_200 = []
            for p in match["players"]:
                if not p["is_group"]:
                    continue
                name = p["name"]
                if p["team_id"] == 100:
                    team_100.append(p)
                else:
                    team_200.append(p)

                # Update player stats
                ps = player_stats[name]
                ps["games"] += 1
                ps["wins"] += 1 if p["win"] else 0
                ps["kills"] += p["kills"]
                ps["deaths"] += p["deaths"]
                ps["assists"] += p["assists"]
                ps["cs_min"] += p["cs_min"]
                ps["damage"] += p["damage"]
                ps["gold"] += p["gold"]
                ps["vision"] += p["vision"]

                # Champion stats
                cs = ps["champs"][p["champion"]]
                cs["games"] += 1
                cs["wins"] += 1 if p["win"] else 0
                cs["kills"] += p["kills"]
                cs["deaths"] += p["deaths"]
                cs["assists"] += p["assists"]
                cs["damage"] += p["damage"]

                # Role stats
                role = role_map.get(p["role"], "Fill")
                rs = ps["roles"][role]
                rs["games"] += 1
                rs["wins"] += 1 if p["win"] else 0

            # Head-to-head: same team pairs
            for team in [team_100, team_200]:
                for i in range(len(team)):
                    for j in range(i + 1, len(team)):
                        a, b = team[i]["name"], team[j]["name"]
                        h2h[a][b]["same_team"] += 1
                        h2h[b][a]["same_team"] += 1
                        if team[i]["win"]:
                            h2h[a][b]["same_wins"] += 1
                            h2h[b][a]["same_wins"] += 1

            # Head-to-head: opposing team pairs
            for p1 in team_100:
                for p2 in team_200:
                    a, b = p1["name"], p2["name"]
                    h2h[a][b]["vs"] += 1
                    h2h[b][a]["vs"] += 1
                    if p1["win"]:
                        h2h[a][b]["vs_wins"] += 1
                    else:
                        h2h[b][a]["vs_wins"] += 1

        return dict(player_stats), dict(h2h)


    def write_inhouse_overview(spreadsheet, player_stats, total_games):
        """Write the main in-house stats overview sheet."""
        sheet_name = "In-House Stats"
        try:
            old = spreadsheet.worksheet(sheet_name)
            sheets_retry(spreadsheet.del_worksheet, old)
        except gspread.exceptions.WorksheetNotFound:
            pass

        ws = sheets_retry(spreadsheet.add_worksheet, sheet_name, rows=80, cols=14)

        DARK = {"red": 0.11, "green": 0.11, "blue": 0.18}
        HEADER = {"red": 0.09, "green": 0.14, "blue": 0.28}
        SECTION = {"red": 0.13, "green": 0.17, "blue": 0.30}
        GOLD_TEXT = {"red": 0.91, "green": 0.72, "blue": 0.29}
        WHITE = {"red": 1, "green": 1, "blue": 1}
        L_BLUE = {"red": 0.88, "green": 0.92, "blue": 0.98}
        L_GREEN = {"red": 0.85, "green": 0.95, "blue": 0.85}
        L_RED = {"red": 0.98, "green": 0.88, "blue": 0.88}

        rows = []
        fmts = []
        merges = []
        pad = lambda d, n=14: d + [""] * (n - len(d))
        rn = lambda: len(rows)

        # Title
        rows.append(pad(["IN-HOUSE 5v5 STATS"]))
        merges.append(f"A{rn()}:N{rn()}")
        fmts.append((f"A{rn()}:N{rn()}", {
            "backgroundColor": DARK,
            "textFormat": {"bold": True, "fontSize": 18, "foregroundColor": GOLD_TEXT},
            "horizontalAlignment": "CENTER"}))

        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        rows.append(pad([f"{total_games} in-house games tracked  |  Last updated: {ts}"]))
        merges.append(f"A{rn()}:N{rn()}")
        fmts.append((f"A{rn()}:N{rn()}", {
            "backgroundColor": DARK,
            "textFormat": {"fontSize": 11, "foregroundColor": WHITE},
            "horizontalAlignment": "CENTER"}))

        rows.append(pad([""]))

        # ── LEADERBOARD ──
        rows.append(pad(["IN-HOUSE LEADERBOARD"]))
        merges.append(f"A{rn()}:N{rn()}")
        fmts.append((f"A{rn()}:N{rn()}", {
            "backgroundColor": SECTION,
            "textFormat": {"bold": True, "fontSize": 14, "foregroundColor": GOLD_TEXT},
            "horizontalAlignment": "CENTER"}))

        rows.append(pad(["#", "Player", "Games", "Wins", "Losses", "Win Rate",
                         "KDA", "Avg Kills", "Avg Deaths", "Avg Assists",
                         "Avg CS/min", "Avg Damage", "Avg Vision", "Avg Gold"]))
        fmts.append((f"A{rn()}:N{rn()}", {
            "backgroundColor": HEADER,
            "textFormat": {"bold": True, "fontSize": 10, "foregroundColor": WHITE},
            "horizontalAlignment": "CENTER"}))

        # Sort by win rate (min 3 games), then by games played
        sorted_players = sorted(
            player_stats.items(),
            key=lambda x: (
                x[1]["wins"] / max(x[1]["games"], 1) if x[1]["games"] >= 3 else 0,
                x[1]["games"]
            ),
            reverse=True
        )

        for i, (name, ps) in enumerate(sorted_players, 1):
            g = ps["games"]
            if g == 0:
                continue
            wr = round(ps["wins"] / g * 100, 1)
            kda = round((ps["kills"] + ps["assists"]) / max(ps["deaths"], 1), 2)
            bg = L_GREEN if i <= 3 else (L_BLUE if i % 2 == 0 else {"red": 1, "green": 1, "blue": 1})

            rows.append(pad([i, name, g, ps["wins"], g - ps["wins"],
                             f"{wr}%",
                             kda,
                             round(ps["kills"] / g, 1),
                             round(ps["deaths"] / g, 1),
                             round(ps["assists"] / g, 1),
                             round(ps["cs_min"] / g, 1),
                             f"{round(ps['damage'] / g):,}",
                             round(ps["vision"] / g, 1),
                             f"{round(ps['gold'] / g):,}"]))
            fmts.append((f"A{rn()}:N{rn()}", {
                "backgroundColor": bg,
                "textFormat": {"fontSize": 11, "bold": i <= 3},
                "horizontalAlignment": "CENTER"}))

        rows.append(pad([""]))
        rows.append(pad([""]))

        # ── PER-PLAYER CHAMPION STATS ──
        rows.append(pad(["IN-HOUSE CHAMPION STATS (per player)"]))
        merges.append(f"A{rn()}:N{rn()}")
        fmts.append((f"A{rn()}:N{rn()}", {
            "backgroundColor": SECTION,
            "textFormat": {"bold": True, "fontSize": 14, "foregroundColor": GOLD_TEXT},
            "horizontalAlignment": "CENTER"}))

        for name, ps in sorted_players:
            if ps["games"] == 0:
                continue

            wr = round(ps["wins"] / ps["games"] * 100, 1)
            rows.append(pad([f"{name}  —  {ps['games']} games  |  {wr}% WR"]))
            merges.append(f"A{rn()}:N{rn()}")
            fmts.append((f"A{rn()}:N{rn()}", {
                "backgroundColor": {"red": 0.2, "green": 0.3, "blue": 0.5},
                "textFormat": {"bold": True, "fontSize": 12, "foregroundColor": WHITE},
                "horizontalAlignment": "CENTER"}))

            rows.append(pad(["Champion", "Games", "Wins", "Losses", "Win Rate",
                             "KDA", "Avg Kills", "Avg Deaths", "Avg Assists",
                             "Avg Damage"]))
            fmts.append((f"A{rn()}:J{rn()}", {
                "backgroundColor": HEADER,
                "textFormat": {"bold": True, "fontSize": 10, "foregroundColor": WHITE},
                "horizontalAlignment": "CENTER"}))

            sorted_champs = sorted(ps["champs"].items(),
                                    key=lambda x: x[1]["games"], reverse=True)
            for j, (champ, cs) in enumerate(sorted_champs):
                cg = cs["games"]
                cwr = round(cs["wins"] / cg * 100, 1)
                ckda = round((cs["kills"] + cs["assists"]) / max(cs["deaths"], 1), 2)
                bg = L_BLUE if j % 2 == 0 else {"red": 1, "green": 1, "blue": 1}

                rows.append(pad([champ, cg, cs["wins"], cg - cs["wins"],
                                 f"{cwr}%", ckda,
                                 round(cs["kills"] / cg, 1),
                                 round(cs["deaths"] / cg, 1),
                                 round(cs["assists"] / cg, 1),
                                 f"{round(cs['damage'] / cg):,}"]))
                fmts.append((f"A{rn()}:J{rn()}", {
                    "backgroundColor": bg,
                    "textFormat": {"fontSize": 11},
                    "horizontalAlignment": "CENTER"}))

            rows.append(pad([""]))

        rows.append(pad([""]))

        # ── ROLE STATS ──
        rows.append(pad(["IN-HOUSE ROLE PERFORMANCE"]))
        merges.append(f"A{rn()}:N{rn()}")
        fmts.append((f"A{rn()}:N{rn()}", {
            "backgroundColor": SECTION,
            "textFormat": {"bold": True, "fontSize": 14, "foregroundColor": GOLD_TEXT},
            "horizontalAlignment": "CENTER"}))

        rows.append(pad(["Player", "Top", "", "Jungle", "", "Mid", "",
                         "Bot", "", "Support", ""]))
        fmts.append((f"A{rn()}:K{rn()}", {
            "backgroundColor": HEADER,
            "textFormat": {"bold": True, "fontSize": 10, "foregroundColor": WHITE},
            "horizontalAlignment": "CENTER"}))

        rows.append(pad(["", "Games", "WR%", "Games", "WR%", "Games", "WR%",
                         "Games", "WR%", "Games", "WR%"]))
        fmts.append((f"A{rn()}:K{rn()}", {
            "backgroundColor": HEADER,
            "textFormat": {"bold": True, "fontSize": 9, "foregroundColor": WHITE},
            "horizontalAlignment": "CENTER"}))

        for name, ps in sorted_players:
            if ps["games"] == 0:
                continue
            row_data = [name]
            for role in ["Top", "Jungle", "Mid", "Bot", "Support"]:
                rs = ps["roles"].get(role, {"games": 0, "wins": 0})
                rg = rs["games"]
                rwr = f"{round(rs['wins'] / rg * 100)}%" if rg > 0 else "-"
                row_data.extend([rg if rg > 0 else "-", rwr])
            rows.append(pad(row_data))
            fmts.append((f"A{rn()}:K{rn()}", {
                "backgroundColor": L_BLUE,
                "textFormat": {"fontSize": 11},
                "horizontalAlignment": "CENTER"}))

        # Write everything in one batch
        sheets_retry(ws.update, values=rows, range_name="A1")

        for m in merges:
            sheets_retry(ws.merge_cells, m)

        col_px = [50, 120, 65, 60, 65, 75, 60, 75, 80, 80, 80, 100, 80, 100]
        reqs = []
        for ci, px in enumerate(col_px):
            reqs.append({"updateDimensionProperties": {
                "range": {"sheetId": ws.id, "dimension": "COLUMNS",
                          "startIndex": ci, "endIndex": ci + 1},
                "properties": {"pixelSize": px}, "fields": "pixelSize"}})
        reqs.append({"updateDimensionProperties": {
            "range": {"sheetId": ws.id, "dimension": "ROWS",
                      "startIndex": 0, "endIndex": 1},
            "properties": {"pixelSize": 50}, "fields": "pixelSize"}})
        sheets_retry(spreadsheet.batch_update, {"requests": reqs})

        for i in range(0, len(fmts), 15):
            batch = [{"range": r, "format": f} for r, f in fmts[i:i+15]]
            sheets_retry(ws.batch_format, batch)

        print("  In-House Stats overview written")


    def write_inhouse_h2h(spreadsheet, h2h, player_stats):
        """Write head-to-head matrix sheet."""
        sheet_name = "In-House Head-to-Head"
        try:
            old = spreadsheet.worksheet(sheet_name)
            sheets_retry(spreadsheet.del_worksheet, old)
        except gspread.exceptions.WorksheetNotFound:
            pass

        # Only include players with games
        active = [n for n, ps in player_stats.items() if ps["games"] > 0]
        active.sort()
        n = len(active)

        ws = sheets_retry(spreadsheet.add_worksheet, sheet_name, rows=n * 2 + 10, cols=n + 3)

        DARK = {"red": 0.11, "green": 0.11, "blue": 0.18}
        HEADER = {"red": 0.09, "green": 0.14, "blue": 0.28}
        SECTION = {"red": 0.13, "green": 0.17, "blue": 0.30}
        GOLD_TEXT = {"red": 0.91, "green": 0.72, "blue": 0.29}
        WHITE = {"red": 1, "green": 1, "blue": 1}
        L_GREEN = {"red": 0.85, "green": 0.95, "blue": 0.85}
        L_RED = {"red": 0.98, "green": 0.88, "blue": 0.88}
        L_BLUE = {"red": 0.88, "green": 0.92, "blue": 0.98}

        rows = []
        fmts = []
        merges = []
        pad_n = n + 2
        pad = lambda d: d + [""] * (pad_n - len(d))
        rn = lambda: len(rows)

        # Title
        rows.append(pad(["IN-HOUSE HEAD-TO-HEAD"]))
        fmts.append((f"A{rn()}:{chr(64+pad_n)}{rn()}", {
            "backgroundColor": DARK,
            "textFormat": {"bold": True, "fontSize": 16, "foregroundColor": GOLD_TEXT},
            "horizontalAlignment": "CENTER"}))

        rows.append(pad([""]))

        # ── TEAMMATE WIN RATE MATRIX ──
        rows.append(pad(["TEAMMATE WIN RATE (when on same team)"]))
        fmts.append((f"A{rn()}:{chr(64+pad_n)}{rn()}", {
            "backgroundColor": SECTION,
            "textFormat": {"bold": True, "fontSize": 13, "foregroundColor": GOLD_TEXT},
            "horizontalAlignment": "CENTER"}))

        # Header row with player names
        header = [""] + active
        rows.append(pad(header))
        fmts.append((f"A{rn()}:{chr(64+n+1)}{rn()}", {
            "backgroundColor": HEADER,
            "textFormat": {"bold": True, "fontSize": 9, "foregroundColor": WHITE},
            "horizontalAlignment": "CENTER"}))

        for a in active:
            row_data = [a]
            for b in active:
                if a == b:
                    row_data.append("-")
                else:
                    d = h2h.get(a, {}).get(b, {"same_team": 0, "same_wins": 0})
                    if d["same_team"] > 0:
                        wr = round(d["same_wins"] / d["same_team"] * 100)
                        row_data.append(f"{wr}% ({d['same_team']})")
                    else:
                        row_data.append("-")
            rows.append(pad(row_data))
            fmts.append((f"A{rn()}:{chr(64+n+1)}{rn()}", {
                "backgroundColor": L_BLUE,
                "textFormat": {"fontSize": 10},
                "horizontalAlignment": "CENTER"}))
            fmts.append((f"A{rn()}", {
                "backgroundColor": HEADER,
                "textFormat": {"bold": True, "fontSize": 9, "foregroundColor": WHITE}}))

        rows.append(pad([""]))
        rows.append(pad([""]))

        # ── VS WIN RATE MATRIX ──
        rows.append(pad(["HEAD-TO-HEAD (when on opposing teams — row player's WR vs column player)"]))
        fmts.append((f"A{rn()}:{chr(64+pad_n)}{rn()}", {
            "backgroundColor": SECTION,
            "textFormat": {"bold": True, "fontSize": 13, "foregroundColor": GOLD_TEXT},
            "horizontalAlignment": "CENTER"}))

        rows.append(pad(header))
        fmts.append((f"A{rn()}:{chr(64+n+1)}{rn()}", {
            "backgroundColor": HEADER,
            "textFormat": {"bold": True, "fontSize": 9, "foregroundColor": WHITE},
            "horizontalAlignment": "CENTER"}))

        for a in active:
            row_data = [a]
            for b in active:
                if a == b:
                    row_data.append("-")
                else:
                    d = h2h.get(a, {}).get(b, {"vs": 0, "vs_wins": 0})
                    if d["vs"] > 0:
                        wr = round(d["vs_wins"] / d["vs"] * 100)
                        row_data.append(f"{wr}% ({d['vs']})")
                    else:
                        row_data.append("-")
            rows.append(pad(row_data))
            fmts.append((f"A{rn()}:{chr(64+n+1)}{rn()}", {
                "backgroundColor": L_BLUE,
                "textFormat": {"fontSize": 10},
                "horizontalAlignment": "CENTER"}))
            fmts.append((f"A{rn()}", {
                "backgroundColor": HEADER,
                "textFormat": {"bold": True, "fontSize": 9, "foregroundColor": WHITE}}))

        # Write
        sheets_retry(ws.update, values=rows, range_name="A1")

        # Column widths
        reqs = [{"updateDimensionProperties": {
            "range": {"sheetId": ws.id, "dimension": "COLUMNS",
                      "startIndex": 0, "endIndex": 1},
            "properties": {"pixelSize": 100}, "fields": "pixelSize"}}]
        for ci in range(1, n + 1):
            reqs.append({"updateDimensionProperties": {
                "range": {"sheetId": ws.id, "dimension": "COLUMNS",
                          "startIndex": ci, "endIndex": ci + 1},
                "properties": {"pixelSize": 85}, "fields": "pixelSize"}})
        reqs.append({"updateDimensionProperties": {
            "range": {"sheetId": ws.id, "dimension": "ROWS",
                      "startIndex": 0, "endIndex": 1},
            "properties": {"pixelSize": 45}, "fields": "pixelSize"}})
        sheets_retry(spreadsheet.batch_update, {"requests": reqs})

        for i in range(0, len(fmts), 15):
            batch = [{"range": r, "format": f} for r, f in fmts[i:i+15]]
            sheets_retry(ws.batch_format, batch)

        print("  In-House Head-to-Head matrix written")


    # ── Main ──────────────────────────────────────────────────────

    def main():
        parser = argparse.ArgumentParser(description="LoL Power Rankings - Full Analytics")
        parser.add_argument("--key", required=True, help="Riot API key")
        parser.add_argument("--sheet", required=True, help="Google Sheet name, URL, or key")
        parser.add_argument("--creds", default=DEFAULT_CREDS_FILE)
        parser.add_argument("--region", default=DEFAULT_REGION)
        parser.add_argument("--routing", default=DEFAULT_ROUTING)
        parser.add_argument("--skip-matches", action="store_true",
                            help="Skip match history (faster, fewer API calls)")
        parser.add_argument("--scout", action="store_true",
                            help="Generate per-player scouting reports (100 games each)")
        parser.add_argument("--scout-only", action="store_true",
                            help="Only run scouting reports, skip rank/analytics updates")
        parser.add_argument("--draft", action="store_true",
                            help="Read Draft Tool selections and compute bans + comp suggestions")
        parser.add_argument("--setup-draft", action="store_true",
                            help="Just create/recreate the Draft Tool sheet with dropdowns")
        parser.add_argument("--inhouse", action="store_true",
                            help="Track in-house custom game stats")
        parser.add_argument("--scout-new", action="store_true",
                            help="Scout only players not already in _ScoutDB, then merge into existing data")
        parser.add_argument("--scout-player", default="",
                            help="Re-scout a single named player and merge into existing _ScoutDB")
        args = parser.parse_args()

        print(f"\n{'='*60}")
        print(f"  LoL Power Rankings - Full Analytics Suite")
        print(f"  Region: {args.region}  |  Routing: {args.routing}")
        print(f"{'='*60}\n")

        # Connect
        print("Connecting to Google Sheets...")
        try:
            spreadsheet = connect_to_sheet(args.creds, args.sheet)
            print(f"  Connected to: {spreadsheet.title}\n")
        except FileNotFoundError:
            print(f"  x Credentials file '{args.creds}' not found.")
            sys.exit(1)
        except gspread.exceptions.SpreadsheetNotFound:
            print(f"  x Sheet not found. Share it with your service account email.")
            sys.exit(1)

        # Champion map
        print("Loading champion data...")
        champ_map, champ_tags = load_champion_map()

        # Read players
        try:
            ws_players = spreadsheet.worksheet("Players")
        except gspread.exceptions.WorksheetNotFound:
            print("  x 'Players' sheet not found.")
            sys.exit(1)

        all_values = ws_players.get_all_values()
        players = []
        for row_idx, row in enumerate(all_values):
            if len(row) >= 3 and "#" in str(row[2]) and row_idx >= 2:
                players.append({"row": row_idx - 1, "name": row[1], "riot_id": row[2]})

        if not players:
            print("  No valid Riot IDs found.")
            sys.exit(1)

        print(f"\nFound {len(players)} players.\n")

        # Read tier list data for analytics
        if not args.scout_only and not args.draft and not args.setup_draft and not args.inhouse and not args.scout_player:
            print("Reading tier list data...")
            try:
                ws_tiers = spreadsheet.worksheet("Tier Lists")
                tier_values = ws_tiers.get_all_values()
                rater_names = []
                if len(tier_values) > 2:
                    for c in range(2, len(tier_values[2])):
                        val = tier_values[2][c]
                        if val in ("Avg Score", "Normalized", ""):
                            break
                        rater_names.append(val)
                tier_data = {}
                player_names_tiers = []
                for i, row in enumerate(tier_values[3:]):
                    tiers = []
                    for c in range(2, 2 + len(rater_names)):
                        if c < len(row) and row[c] in TIER_TO_NUM:
                            tiers.append(row[c])
                    tier_data[i] = tiers
                    if len(row) > 1 and row[1]:
                        player_names_tiers.append(row[1])
                print(f"  Read {len(rater_names)} raters x {len(player_names_tiers)} players")
            except Exception as e:
                print(f"  Warning: could not read tier lists: {e}")
                tier_data, rater_names, player_names_tiers = {}, [], []

            # Fetch from Riot API
            print(f"\n{'='*60}")
            print("FETCHING RIOT API DATA")
            print(f"{'='*60}\n")

            results = []
            for idx, player in enumerate(players, 1):
                game_name, tag_line = player["riot_id"].rsplit("#", 1)
                print(f"[{idx}/{len(players)}] {player['name']} ({player['riot_id']})")

                puuid = fetch_account(game_name.strip(), tag_line.strip(), args.routing, args.key)
                if not puuid:
                    results.append({
                        "row": idx, "name": player["name"],
                        "tier": "Unranked", "division": "N/A",
                        "lp": 0, "wins": 0, "losses": 0,
                        "score": 0, "normalized": 0,
                        "top_champs": [], "recent_matches": [],
                    })
                    continue
                time.sleep(0.8)

                tier, division, lp, wins, losses = fetch_ranked(puuid, args.region, args.key)
                score = compute_score(tier, division)
                normalized = round(score / 10 * 100, 1)
                rs = f"{tier} {division}" if division != "N/A" else tier
                print(f"    Rank: {rs} ({lp} LP) - {wins}W / {losses}L")
                time.sleep(0.8)

                top_champs = fetch_top_champions(puuid, args.region, args.key, champ_map)
                if top_champs:
                    print(f"    Champs: {', '.join(c['name'] for c in top_champs)}")
                time.sleep(0.8)

                recent_matches = []
                if not args.skip_matches:
                    recent_matches = fetch_recent_matches(
                        puuid, args.routing, args.region, args.key)
                    if recent_matches:
                        rw = sum(1 for m in recent_matches if m["win"])
                        print(f"    Recent: {rw}W-{len(recent_matches)-rw}L")
                else:
                    print(f"    Skipping match history")

                results.append({
                    "row": idx, "name": player["name"],
                    "tier": tier, "division": division,
                    "lp": lp, "wins": wins, "losses": losses,
                    "score": score, "normalized": normalized,
                    "top_champs": top_champs, "recent_matches": recent_matches,
                })

            # Compute analytics
            print(f"\n{'='*60}")
            print("COMPUTING ANALYTICS")
            print(f"{'='*60}\n")

            consensus, hot_takes, rater_bias = [], [], []
            if tier_data and player_names_tiers:
                consensus, hot_takes, rater_bias = compute_tier_analytics(
                    tier_data, player_names_tiers, rater_names)
                print(f"  {len(consensus)} players analyzed")
                print(f"  {len(hot_takes)} hot takes found")
                print(f"  {len(rater_bias)} raters analyzed")
            else:
                print("  No tier data for analytics")

            # Write to Google Sheets
            print(f"\n{'='*60}")
            print("WRITING TO GOOGLE SHEETS")
            print(f"{'='*60}\n")

            ts = datetime.now().strftime("%Y-%m-%d %H:%M")

            write_rank_data(spreadsheet, results, ts)
            write_player_stats(spreadsheet, results, champ_map)
            if consensus:
                write_consensus(spreadsheet, consensus)
            write_hot_takes(spreadsheet, hot_takes)
            if rater_bias:
                write_rater_bias(spreadsheet, rater_bias)
            write_rank_history(spreadsheet, results, ts)
            append_activity_event(spreadsheet, "UPDATE", "",
                                  f"{len(results)} players updated")
        else:
            results = []

        # Scouting reports
        if args.scout or args.scout_only:
            # Read final rankings for scouting headers
            print("\nReading Final Rankings...")
            final_rankings = get_final_rankings(spreadsheet)
            if final_rankings:
                print(f"  Found rankings for {len(final_rankings)} players")
            else:
                print("  No final rankings found (run without --scout-only first)")

            # Load inhouse data if available
            print("\nLoading In-House custom game data...")
            inhouse_db = load_inhouse_db(spreadsheet)
            if inhouse_db:
                print(f"  Found inhouse data for {len(inhouse_db)} players")
            else:
                print("  No inhouse data found (run inhouse_tracker.py first)")

            print(f"\n{'='*60}")
            print("GENERATING SCOUTING REPORTS (100 games per player)")
            print(f"{'='*60}")
            print(f"This will make ~{len(players) * 50} API calls. Estimated time: {len(players) * 2}-{len(players) * 4} minutes.\n")

            all_scouting = {}

            for idx, player in enumerate(players, 1):
                game_name, tag_line = player["riot_id"].rsplit("#", 1)
                print(f"\n[{idx}/{len(players)}] Scouting {player['name']}...")

                puuid = fetch_account(game_name.strip(), tag_line.strip(), args.routing, args.key)
                if not puuid:
                    print(f"    Could not find account, skipping")
                    continue
                time.sleep(0.8)

                scout_matches = fetch_scouting_matches(puuid, args.routing, args.region, args.key, count=100)
                if not scout_matches:
                    print(f"    No matches found, skipping")
                    continue

                analysis = analyze_player(scout_matches)
                if not analysis:
                    print(f"    Analysis failed, skipping")
                    continue

                # Store for draft tool
                all_scouting[player["name"]] = analysis

                # Find this player's rank info
                pr = next((r for r in results if r["name"] == player["name"]), None)
                if pr:
                    rs = f"{pr['tier']} {pr['division']}" if pr['division'] != "N/A" else pr['tier']
                    plp = pr["lp"]
                else:
                    # Scout-only mode: fetch rank directly
                    tier, division, plp, _, _ = fetch_ranked(puuid, args.region, args.key)
                    rs = f"{tier} {division}" if division != "N/A" else tier
                    time.sleep(0.8)

                # Get ranking info for this player
                ranking_info = final_rankings.get(player["name"])

                # Get inhouse data - try player name and riot game name
                player_inhouse = inhouse_db.get(player["name"])
                if not player_inhouse:
                    riot_name = player["riot_id"].rsplit("#", 1)[0] if "#" in player["riot_id"] else ""
                    player_inhouse = inhouse_db.get(riot_name)

                write_scouting_sheet(spreadsheet, player["name"], rs, plp, analysis, ranking_info, player_inhouse)

            # Create Draft Tool sheet with dropdowns
            print(f"\nCreating Draft Tool...")
            player_name_list = [p["name"] for p in players]
            write_draft_tool(spreadsheet, player_name_list)

            # Save scouting data for draft use
            # Store as a hidden data sheet for --draft to use later
            write_scouting_database(spreadsheet, all_scouting, final_rankings)

            append_activity_event(spreadsheet, "SCOUT", "",
                                  f"Full scout: {len(all_scouting)} players updated")
            print(f"\nAll scouting reports generated!")

        # Scout new players only (merge into existing _ScoutDB)
        if args.scout_new:
            print(f"\n{'='*60}")
            print("SCOUTING NEW PLAYERS")
            print(f"{'='*60}\n")

            # Load existing scouting database
            print("Loading existing scouting database...")
            existing_scouting, existing_rankings = load_scouting_database(spreadsheet)
            already_scouted = set(existing_scouting.keys())
            print(f"  {len(already_scouted)} players already scouted: {', '.join(sorted(already_scouted)) or 'none'}")

            # Determine which players are missing
            new_players = [p for p in players[::-1] if p["name"] not in already_scouted]
            if not new_players:
                print("\nAll players are already scouted. Nothing to do.")
                print("Tip: run the full Scout command to refresh existing players.")
                return

            print(f"\n  {len(new_players)} new player(s) to scout (bottom to top): {', '.join(p['name'] for p in new_players)}\n")

            # Load ranking info for the new players
            final_rankings = get_final_rankings(spreadsheet)

            # Load inhouse data
            print("Loading In-House custom game data...")
            inhouse_db = load_inhouse_db(spreadsheet)
            if inhouse_db:
                print(f"  Found inhouse data for {len(inhouse_db)} players")
            else:
                print("  No inhouse data found")

            print(f"\nScouting {len(new_players)} new player(s) (100 games each)...\n")

            new_scouting = {}
            for idx, player in enumerate(new_players, 1):
                game_name, tag_line = player["riot_id"].rsplit("#", 1)
                print(f"\n[{idx}/{len(new_players)}] Scouting {player['name']}...")

                puuid = fetch_account(game_name.strip(), tag_line.strip(), args.routing, args.key)
                if not puuid:
                    print(f"    Could not find account, skipping")
                    continue
                time.sleep(0.8)

                scout_matches = fetch_scouting_matches(puuid, args.routing, args.region, args.key, count=100)
                if not scout_matches:
                    print(f"    No matches found, skipping")
                    continue

                analysis = analyze_player(scout_matches)
                if not analysis:
                    print(f"    Analysis failed, skipping")
                    continue

                new_scouting[player["name"]] = analysis

                # Fetch rank for scouting sheet header
                tier, division, plp, _, _ = fetch_ranked(puuid, args.region, args.key)
                rs = f"{tier} {division}" if division != "N/A" else tier
                time.sleep(0.8)

                ranking_info = final_rankings.get(player["name"])
                player_inhouse = inhouse_db.get(player["name"])
                if not player_inhouse:
                    riot_name = player["riot_id"].rsplit("#", 1)[0] if "#" in player["riot_id"] else ""
                    player_inhouse = inhouse_db.get(riot_name)

                write_scouting_sheet(spreadsheet, player["name"], rs, plp, analysis, ranking_info, player_inhouse)

            if not new_scouting:
                print("\nNo new players could be scouted.")
                return

            # Merge new data into existing and save
            merged_scouting = {**existing_scouting, **new_scouting}
            merged_rankings = {**existing_rankings, **final_rankings}
            write_scouting_database(spreadsheet, merged_scouting, merged_rankings)
            new_names = ", ".join(new_scouting.keys())
            append_activity_event(spreadsheet, "SCOUT_NEW", new_names,
                                  f"Added {len(new_scouting)} new player(s): {new_names}")
            print(f"\nScouting complete! Added {len(new_scouting)} new player(s). Database now covers {len(merged_scouting)} players.")
            return

        # Re-scout a single named player and merge into existing _ScoutDB
        if args.scout_player:
            target_name = args.scout_player.strip()
            print(f"\n{'='*60}")
            print(f"RE-SCOUTING PLAYER: {target_name.upper()}")
            print(f"{'='*60}\n")

            # Find the player in the Players sheet
            player = next((p for p in players if p["name"].lower() == target_name.lower()), None)
            if not player:
                print(f"  ERROR: '{target_name}' not found in Players sheet.")
                print(f"  Available: {', '.join(p['name'] for p in players)}")
                return

            print(f"  Found: {player['name']} ({player['riot_id']})")

            game_name, tag_line = player["riot_id"].rsplit("#", 1)
            puuid = fetch_account(game_name.strip(), tag_line.strip(), args.routing, args.key)
            if not puuid:
                print(f"  ERROR: Could not find Riot account for {player['riot_id']}.")
                return
            time.sleep(0.8)

            print(f"  Fetching last 100 games...")
            scout_matches = fetch_scouting_matches(puuid, args.routing, args.region, args.key, count=100)
            if not scout_matches:
                print(f"  ERROR: No matches found for {player['name']}.")
                return

            analysis = analyze_player(scout_matches)
            if not analysis:
                print(f"  ERROR: Analysis failed for {player['name']}.")
                return

            # Fetch current rank
            tier, division, plp, _, _ = fetch_ranked(puuid, args.region, args.key)
            rs = f"{tier} {division}" if division != "N/A" else tier
            time.sleep(0.8)

            # Load supporting data
            final_rankings = get_final_rankings(spreadsheet)
            ranking_info = final_rankings.get(player["name"])

            print("  Loading In-House custom game data...")
            inhouse_db = load_inhouse_db(spreadsheet)
            player_inhouse = inhouse_db.get(player["name"])
            if not player_inhouse:
                riot_name = player["riot_id"].rsplit("#", 1)[0] if "#" in player["riot_id"] else ""
                player_inhouse = inhouse_db.get(riot_name)

            # Write/overwrite the scout sheet for this player
            print(f"  Writing scouting sheet...")
            write_scouting_sheet(spreadsheet, player["name"], rs, plp, analysis, ranking_info, player_inhouse)

            # Load existing _ScoutDB, replace this player's entry, save merged result
            print(f"  Updating _ScoutDB...")
            existing_scouting, existing_rankings = load_scouting_database(spreadsheet)
            existing_scouting[player["name"]] = analysis
            existing_rankings.update(final_rankings)
            write_scouting_database(spreadsheet, existing_scouting, existing_rankings)
            rank_str = f" ({rs} {plp} LP)" if rs and rs not in ("Unranked", "") else ""
            append_activity_event(spreadsheet, "SCOUT", player["name"],
                                  f"Re-scouted {player['name']}{rank_str}")
            print(f"\nDone! {player['name']} has been re-scouted and _ScoutDB updated.")
            return

        # Setup draft tool only
        if args.setup_draft:
            print("\nCreating Draft Tool sheet...")
            player_name_list = [p["name"] for p in players]
            write_draft_tool(spreadsheet, player_name_list)
            print(f"\nDone! Go to the Draft Tool tab and select players from the dropdowns.\n")
            return

        # Draft mode
        if args.draft:
            print(f"\n{'='*60}")
            print("RUNNING DRAFT TOOL")
            print(f"{'='*60}\n")

            # Load scouting database
            all_scouting, db_rankings = load_scouting_database(spreadsheet)
            if not all_scouting:
                print("  No scouting data found. Run --scout first.")
            else:
                # Also get latest final rankings
                final_rankings = get_final_rankings(spreadsheet)
                if final_rankings:
                    db_rankings.update(final_rankings)
                team1, team2 = run_draft(spreadsheet, all_scouting, db_rankings, champ_tags)
                t1_str = ", ".join(p for p, r in team1) if team1 else "?"
                t2_str = ", ".join(p for p, r in team2) if team2 else "?"
                append_activity_event(spreadsheet, "DRAFT", "",
                                      f"Draft: Team 1 [{t1_str}] vs Team 2 [{t2_str}]")

        # In-house stats tracker
        if args.inhouse:
            print(f"\n{'='*60}")
            print("IN-HOUSE STATS TRACKER")
            print(f"{'='*60}\n")

            # First get all PUUIDs
            print("  Looking up player accounts...")
            player_puuid_map = {}
            for player in players:
                game_name, tag_line = player["riot_id"].rsplit("#", 1)
                puuid = fetch_account(game_name.strip(), tag_line.strip(), args.routing, args.key)
                if puuid:
                    player_puuid_map[player["name"]] = puuid
                    print(f"    {player['name']}: found")
                else:
                    print(f"    {player['name']}: not found, skipping")
                time.sleep(0.8)

            all_puuids = list(player_puuid_map.values())

            # Fetch and filter in-house matches
            inhouse_matches = fetch_and_filter_inhouse(
                all_puuids, player_puuid_map, args.routing, args.region, args.key, count=25)

            if not inhouse_matches:
                print("\n  No in-house games found. Make sure you've played custom 5v5s recently.")
            else:
                # Analyze
                print("\n  Analyzing in-house stats...")
                player_stats, h2h = analyze_inhouse(inhouse_matches, player_puuid_map)

                # Write sheets
                print(f"\n{'='*60}")
                print("WRITING TO GOOGLE SHEETS")
                print(f"{'='*60}\n")

                write_inhouse_overview(spreadsheet, player_stats, len(inhouse_matches))
                write_inhouse_h2h(spreadsheet, h2h, player_stats)

                # Print summary
                print(f"\n{'='*60}")
                print("IN-HOUSE SUMMARY")
                print(f"{'='*60}")
                print(f"\n{len(inhouse_matches)} in-house games found\n")
                print(f"{'Player':<14} {'Games':<7} {'W-L':<8} {'WR%':<7} {'KDA'}")
                print(f"{'_'*45}")
                sorted_ps = sorted(player_stats.items(),
                                    key=lambda x: x[1]["wins"] / max(x[1]["games"], 1),
                                    reverse=True)
                for name, ps in sorted_ps:
                    g = ps["games"]
                    if g == 0:
                        continue
                    wr = round(ps["wins"] / g * 100, 1)
                    kda = round((ps["kills"] + ps["assists"]) / max(ps["deaths"], 1), 2)
                    print(f"{name:<14} {g:<7} {ps['wins']}W-{g-ps['wins']}L  {wr}%   {kda}")

                append_activity_event(spreadsheet, "INHOUSE", "",
                                      f"{len(inhouse_matches)} in-house game(s) logged")
                print(f"\nDone! Check 'In-House Stats' and 'In-House Head-to-Head' tabs.\n")
                return

        # Summary
        if not args.scout_only and not args.draft and not args.setup_draft and not args.inhouse:
            print(f"\n{'='*60}")
            print("SUMMARY")
            print(f"{'='*60}")
            print(f"\n{'#':<4} {'Player':<14} {'Rank':<16} {'WR%':<7} {'Top Champ':<14} {'Recent'}")
            print(f"{'_'*70}")
            for r in results:
                rs = f"{r['tier']} {r['division']}" if r['division'] != "N/A" else r['tier']
                g = r["wins"] + r["losses"]
                wr = f"{round(r['wins']/g*100,1)}%" if g > 0 else "-"
                top = r["top_champs"][0]["name"] if r.get("top_champs") else "-"
                mt = r.get("recent_matches", [])
                rec = f"{sum(1 for m in mt if m['win'])}W-{sum(1 for m in mt if not m['win'])}L" if mt else "-"
                print(f"{r['row']:<4} {r['name']:<14} {rs:<16} {wr:<7} {top:<14} {rec}")

            if hot_takes:
                print(f"\nTOP HOT TAKES:")
                for ht in hot_takes[:5]:
                    print(f"  {ht['rater']} rated {ht['player']} as {ht['rated']} "
                          f"(avg: {ht['avg']}) - {ht['diff']} tiers {ht['direction']}")

            if rater_bias:
                mg = max(rater_bias, key=lambda x: x["avg"])
                mh = min(rater_bias, key=lambda x: x["avg"])
                print(f"\nMOST GENEROUS: {mg['rater']} (avg {mg['avg_tier']}, {mg['avg']})")
                print(f"MOST HARSH:    {mh['rater']} (avg {mh['avg_tier']}, {mh['avg']})")

        print(f"\nDone! Check your Google Sheet.\n")

    main()


def _run_inhouse(argv):
    """Run the in-house tracker CLI in a subprocess context."""
    import sys as _sys
    _sys.argv = ["inhouse_tracker"] + list(argv)
    """
    In-House Custom Game Tracker (via League Client API)
    =====================================================
    Anyone in the group can run this to log their custom games.
    Games are tracked by ID so duplicates are impossible.

    SETUP:
      pip install requests gspread google-auth
      Place credentials.json in the same folder

    USAGE:
      python inhouse_tracker.py --sheet "YOUR_SHEET_URL"

    OPTIONS:
      --count    Matches to search (default: 500)
      --days     Time window in days (default: 180)
      --debug    Show raw data for debugging
      --lol-path Custom League install path
    """



    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
              "https://www.googleapis.com/auth/drive"]


    # ── Sheets Retry Helper ───────────────────────────────────────

    def sheets_retry(fn, *args, max_attempts=6, **kwargs):
        """Call fn(*args, **kwargs) with exponential backoff on quota/server errors."""
        for attempt in range(max_attempts):
            try:
                return fn(*args, **kwargs)
            except gspread.exceptions.APIError as e:
                status = getattr(e.response, "status_code", None)
                if status in (429, 500, 503) and attempt < max_attempts - 1:
                    time.sleep((2 ** attempt) + random.uniform(0, 1))
                else:
                    raise


    # ── LCU Connection ───────────────────────────────────────────

    def find_lockfile():
        paths = []
        if sys.platform == "win32":
            for d in ["C","D","E"]:
                paths.extend([f"{d}:\\Riot Games\\League of Legends\\lockfile",
                             f"{d}:\\Program Files\\Riot Games\\League of Legends\\lockfile",
                             f"{d}:\\Program Files (x86)\\Riot Games\\League of Legends\\lockfile"])
        elif sys.platform == "darwin":
            paths.append("/Applications/League of Legends.app/Contents/LoL/lockfile")
        for p in paths:
            if os.path.exists(p): return p
        if sys.platform == "win32":
            try:
                out = subprocess.check_output(
                    'wmic process where "name=\'LeagueClientUx.exe\'" get commandline',
                    shell=True, text=True, stderr=subprocess.DEVNULL)
                m = re.search(r'"([^"]*LeagueClientUx\.exe)"', out)
                if m:
                    lf = os.path.join(os.path.dirname(m.group(1)), "lockfile")
                    if os.path.exists(lf): return lf
            except Exception as e:
                print(f"Warning: lockfile lookup failed: {e}")
        return None


    def connect_lcu(lockfile_path=None):
        path = lockfile_path or find_lockfile()
        if not path:
            print("  Could not find League client. Make sure it's OPEN.")
            return None, None
        with open(path) as f:
            parts = f.read().strip().split(":")
        if len(parts) < 5:
            print("  Invalid lockfile"); return None, None
        base = f"{parts[4]}://127.0.0.1:{parts[2]}"
        auth = ("riot", parts[3])
        try:
            r = requests.get(f"{base}/lol-summoner/v1/current-summoner",
                            auth=auth, verify=False, timeout=5)
            if r.status_code == 200:
                s = r.json()
                name = s.get("gameName", s.get("displayName", "?"))
                print(f"  Connected as: {name}")
                return base, auth
            print(f"  LCU error: {r.status_code}"); return None, None
        except Exception as e:
            print(f"  LCU connection attempt failed: {e}")
            print("  Can't connect to League client"); return None, None


    # ── LCU Match History ────────────────────────────────────────

    def fetch_all_matches(base_url, auth, max_count=500):
        seen_ids = set()
        all_games = []
        url = f"{base_url}/lol-match-history/v1/products/lol/current-summoner/matches?begIndex=0&endIndex={max_count}"
        try:
            r = requests.get(url, auth=auth, verify=False, timeout=30)
            if r.status_code == 200:
                for g in r.json().get("games", {}).get("games", []):
                    gid = g.get("gameId")
                    if gid and gid not in seen_ids:
                        seen_ids.add(gid)
                        all_games.append(g)
                print(f"  Fetched {len(all_games)} unique matches")
        except Exception as e:
            print(f"  Fetch failed: {e}")
        if len(all_games) < 20:
            print("  Trying page-by-page...")
            for start in range(0, max_count, 20):
                url = f"{base_url}/lol-match-history/v1/products/lol/current-summoner/matches?begIndex={start}&endIndex={start+20}"
                try:
                    r = requests.get(url, auth=auth, verify=False, timeout=15)
                    if r.status_code != 200: break
                    games = r.json().get("games", {}).get("games", [])
                    if not games: break
                    new = 0
                    for g in games:
                        gid = g.get("gameId")
                        if gid and gid not in seen_ids:
                            seen_ids.add(gid); all_games.append(g); new += 1
                    if new == 0: break
                except Exception as e:
                    print(f"Warning: match page fetch failed: {e}")
                    break
        return all_games


    def fetch_detail(base_url, auth, game_id):
        try:
            r = requests.get(f"{base_url}/lol-match-history/v1/games/{game_id}",
                            auth=auth, verify=False, timeout=15)
            if r.status_code == 200: return r.json()
        except Exception as e:
            print(f"Warning: game detail fetch failed: {e}")
        return None


    def load_champion_map():
        try:
            v = requests.get("https://ddragon.leagueoflegends.com/api/versions.json", timeout=10).json()
            data = requests.get(f"https://ddragon.leagueoflegends.com/cdn/{v[0]}/data/en_US/champion.json", timeout=10).json()
            return {int(d["key"]): d["name"] for d in data["data"].values()}
        except Exception as e:
            print(f"Warning: failed to load champion map from DDragon: {e}")
            return {}


    def connect_sheet(creds, sheet):
        cred = Credentials.from_service_account_file(creds, scopes=SCOPES)
        gc = gspread.authorize(cred)
        if "docs.google.com" in sheet: return gc.open_by_url(sheet)
        return gc.open(sheet)


    # ── Game Log Database ────────────────────────────────────────

    def load_existing_game_ids(spreadsheet):
        """Load all already-logged game IDs from the _InhouseGameLog sheet."""
        try:
            ws = spreadsheet.worksheet("_InhouseGameLog")
            values = ws.get_all_values()
            existing = set()
            for row in values[1:]:  # skip header
                if row and row[0]:
                    try: existing.add(int(row[0]))
                    except Exception: existing.add(row[0])
            return existing
        except gspread.exceptions.WorksheetNotFound:
            return set()


    def append_game_log(spreadsheet, new_records, logged_by="Unknown"):
        """Append new game records to the _InhouseGameLog sheet. Creates if needed."""
        try:
            ws = spreadsheet.worksheet("_InhouseGameLog")
        except gspread.exceptions.WorksheetNotFound:
            ws = sheets_retry(spreadsheet.add_worksheet, "_InhouseGameLog", rows=5000, cols=16)
            header = ["gameId", "timestamp", "player", "champion", "teamId",
                      "win", "kills", "deaths", "assists", "cs", "damage",
                      "gold", "vision", "role", "duration", "logged_by"]
            sheets_retry(ws.update, values=[header], range_name="A1")
            sheets_retry(ws.format, "A1:P1", {
                "backgroundColor": {"red": 0.09, "green": 0.14, "blue": 0.28},
                "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                "horizontalAlignment": "CENTER"})

        if not new_records:
            return

        # Find next empty row
        existing = ws.get_all_values()
        next_row = len(existing) + 1

        # Batch write new records
        rows = []
        for r in new_records:
            rows.append([
                r["gameId"], r["timestamp"], r["player"], r["champion"],
                r["teamId"], r["win"], r["kills"], r["deaths"], r["assists"],
                r["cs"], r["damage"], r["gold"], r["vision"], r["role"],
                r["duration"], r["logged_by"],
            ])

        # Write in chunks of 500 to avoid API limits
        for i in range(0, len(rows), 500):
            chunk = rows[i:i+500]
            sheets_retry(ws.update, values=chunk, range_name=f"A{next_row + i}")

        print(f"  Appended {len(rows)} new records to game log")
        _log_activity(spreadsheet, "INHOUSE", logged_by,
                      f"Logged {len(rows)} new games ({next_row - 1 + len(rows)} total)")


    def load_full_game_log(spreadsheet):
        """Load all game records from the log."""
        try:
            ws = spreadsheet.worksheet("_InhouseGameLog")
            values = ws.get_all_values()
            records = []
            for row in values[1:]:
                if len(row) < 15 or not row[0]: continue
                try:
                    records.append({
                        "gameId": row[0], "timestamp": row[1],
                        "player": row[2], "champion": row[3],
                        "teamId": int(row[4]) if row[4] else 0,
                        "win": row[5] == "True" or row[5] == "TRUE",
                        "kills": int(row[6]) if row[6] else 0,
                        "deaths": int(row[7]) if row[7] else 0,
                        "assists": int(row[8]) if row[8] else 0,
                        "cs": int(row[9]) if row[9] else 0,
                        "damage": int(row[10]) if row[10] else 0,
                        "gold": int(row[11]) if row[11] else 0,
                        "vision": int(row[12]) if row[12] else 0,
                        "role": row[13], "duration": row[14],
                    })
                except (ValueError, IndexError): continue
            return records
        except Exception as e:
            print(f"Warning: failed to load game log: {e}")
            return []


    def compute_stats_from_log(records):
        """Compute all stats from the game log records."""
        player_stats = defaultdict(lambda: {
            "games": 0, "wins": 0, "kills": 0, "deaths": 0, "assists": 0,
            "cs": 0, "damage": 0, "gold": 0,
            "champs": defaultdict(lambda: {"games": 0, "wins": 0, "kills": 0,
                                            "deaths": 0, "assists": 0, "damage": 0}),
            "roles": defaultdict(lambda: {"games": 0, "wins": 0}),
            "champ_roles": defaultdict(lambda: defaultdict(int)),
            "win_streak": 0, "best_streak": 0, "mvp_count": 0,
            "recent_wr": None,
        })
        # Keyed by player name; holds (timestamp, win) tuples for post-processing
        game_results: dict[str, list] = defaultdict(list)

        h2h = defaultdict(lambda: defaultdict(lambda: {
            "same_team": 0, "same_wins": 0, "vs": 0, "vs_wins": 0}))

        # Group records by gameId
        games = defaultdict(list)
        for r in records:
            games[r["gameId"]].append(r)

        total_games = 0
        for gid, players in games.items():
            if len(players) != 10: continue
            total_games += 1

            mvp_name = None
            mvp_score = None
            for p in players:
                name = p["player"]
                ps = player_stats[name]
                ps["games"] += 1
                ps["wins"] += 1 if p["win"] else 0
                ps["kills"] += p["kills"]
                ps["deaths"] += p["deaths"]
                ps["assists"] += p["assists"]
                ps["cs"] += p["cs"]
                ps["damage"] += p["damage"]
                ps["gold"] += p["gold"]

                game_results[name].append((p["timestamp"], p["win"]))

                ce = ps["champs"][p["champion"]]
                ce["games"] += 1
                ce["wins"] += 1 if p["win"] else 0
                ce["kills"] += p["kills"]
                ce["deaths"] += p["deaths"]
                ce["assists"] += p["assists"]
                ce["damage"] += p["damage"]

                role = p["role"]
                rs = ps["roles"][role]
                rs["games"] += 1
                rs["wins"] += 1 if p["win"] else 0

                ps["champ_roles"][p["champion"]][role] += 1

                # MVP: player with highest kills*3 + assists - deaths + damage/1000
                score = p["kills"] * 3 + p["assists"] - p["deaths"] + p["damage"] / 1000
                if mvp_score is None or score > mvp_score:
                    mvp_score = score
                    mvp_name = name

            if mvp_name:
                player_stats[mvp_name]["mvp_count"] += 1

            # Head-to-head
            t100 = [p for p in players if p["teamId"] == 100]
            t200 = [p for p in players if p["teamId"] == 200]

            for team in [t100, t200]:
                for i in range(len(team)):
                    for j in range(i + 1, len(team)):
                        a, b = team[i]["player"], team[j]["player"]
                        h2h[a][b]["same_team"] += 1
                        h2h[b][a]["same_team"] += 1
                        if team[i]["win"]:
                            h2h[a][b]["same_wins"] += 1
                            h2h[b][a]["same_wins"] += 1

            for p1 in t100:
                for p2 in t200:
                    a, b = p1["player"], p2["player"]
                    h2h[a][b]["vs"] += 1
                    h2h[b][a]["vs"] += 1
                    if p1["win"]:
                        h2h[a][b]["vs_wins"] += 1
                    else:
                        h2h[b][a]["vs_wins"] += 1

        # Post-process streaks and recent WR for each player
        for name, ps in player_stats.items():
            outcomes = [win for _, win in sorted(game_results[name], key=lambda x: x[0])]

            streak = 0
            for win in reversed(outcomes):
                if win:
                    streak += 1
                else:
                    break
            ps["win_streak"] = streak

            best = cur = 0
            for win in outcomes:
                cur = cur + 1 if win else 0
                best = max(best, cur)
            ps["best_streak"] = best

            recent = outcomes[-10:]
            ps["recent_wr"] = round(sum(recent) / len(recent) * 100, 1) if len(recent) >= 3 else None

        return dict(player_stats), dict(h2h), total_games


    # ── Activity Log ─────────────────────────────────────────────

    def _log_activity(spreadsheet, event_type, player_name, details):
        """Write one row to the _Activity sheet for cross-user feed visibility."""
        try:
            sheet_name = "_Activity"
            try:
                ws = spreadsheet.worksheet(sheet_name)
            except gspread.exceptions.WorksheetNotFound:
                ws = sheets_retry(spreadsheet.add_worksheet, sheet_name, rows=500, cols=4)
                sheets_retry(ws.append_row, ["_ACTIVITY LOG", "", "", ""], value_input_option="RAW")
            sheets_retry(ws.append_row,
                [datetime.now().strftime("%Y-%m-%d %H:%M"), event_type, player_name or "", details],
                value_input_option="RAW")
        except Exception as e:
            print(f"  (Activity log write skipped: {e})")


    # ── Main ─────────────────────────────────────────────────────

    def main():
        parser = argparse.ArgumentParser(description="In-House Custom Game Tracker")
        parser.add_argument("--sheet", required=True)
        parser.add_argument("--creds", default="credentials.json")
        parser.add_argument("--count", type=int, default=500)
        parser.add_argument("--days", type=int, default=180)
        parser.add_argument("--lol-path", default=None)
        parser.add_argument("--debug", action="store_true")
        args = parser.parse_args()

        print(f"\n{'='*60}")
        print(f"  In-House Custom Game Tracker")
        print(f"  Anyone can run this — games are tracked by ID")
        print(f"  Duplicates are automatically prevented")
        print(f"{'='*60}\n")

        champ_map = {}
        print("Loading champions...")
        champ_map = load_champion_map()
        if champ_map:
            print(f"  Loaded {len(champ_map)} champion names")

        print("\nConnecting to League client...")
        lf = args.lol_path
        if lf and not lf.endswith("lockfile"): lf = os.path.join(lf, "lockfile")
        base_url, auth = connect_lcu(lf)
        if not base_url: sys.exit(1)

        # Get current player name for logging
        try:
            r = requests.get(f"{base_url}/lol-summoner/v1/current-summoner",
                            auth=auth, verify=False, timeout=5)
            logged_by = r.json().get("gameName", "Unknown") if r.status_code == 200 else "Unknown"
        except Exception as e:
            print(f"Warning: could not fetch summoner name: {e}")
            logged_by = "Unknown"

        # Connect to Google Sheets early to check existing games
        print("\nConnecting to Google Sheets...")
        try:
            spreadsheet = connect_sheet(args.creds, args.sheet)
            print(f"  Connected to: {spreadsheet.title}")
        except Exception as e:
            print(f"Error: Could not connect to Google Sheets. Check your credentials file and sheet name.")
            print(f"  Detail: {e}")
            sys.exit(1)

        # Load existing game IDs to skip duplicates
        print("\nChecking for existing game data...")
        existing_ids = load_existing_game_ids(spreadsheet)
        print(f"  {len(existing_ids)} games already logged")

        # Fetch match history from client
        print(f"\nFetching match history from client...")
        all_games = fetch_all_matches(base_url, auth, args.count)
        print(f"  {len(all_games)} unique matches found")

        # Filter for customs
        cutoff = int((datetime.now() - timedelta(days=args.days)).timestamp() * 1000)
        customs = []
        queue_counts = defaultdict(int)
        for g in all_games:
            qid = g.get("queueId", -1)
            gt = g.get("gameType", "")
            queue_counts[f"{qid} ({g.get('gameMode','')}/{gt})"] += 1
            if g.get("gameCreation", 0) < cutoff: continue
            if qid == 0 or qid == 3130 or gt == "CUSTOM_GAME":
                gid = g.get("gameId")
                # Skip if already logged
                if gid in existing_ids:
                    continue
                customs.append(g)

        print(f"\n  Queue breakdown:")
        for qt, cnt in sorted(queue_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"    {qt}: {cnt}")
        print(f"\n  {len(customs)} NEW custom games to process (skipped {len(existing_ids)} already logged)")

        if customs:
            # Fetch full details for new games
            print(f"\nFetching details for {len(customs)} new custom games...")
            role_map = {"TOP": "Top", "JUNGLE": "Jungle", "MIDDLE": "Mid",
                       "BOTTOM": "Bot", "UTILITY": "Support", "NONE": "Fill",
                       "UNKNOWN": "Fill", "": "Fill"}

            new_records = []
            seen = set()
            valid_count = 0
            for i, g in enumerate(customs):
                gid = g.get("gameId")
                if not gid or gid in seen: continue
                seen.add(gid)

                d = fetch_detail(base_url, auth, gid)
                if not d: continue

                participants = d.get("participants", [])
                identities = d.get("participantIdentities", [])

                if len(participants) != 10:
                    print(f"  [{i+1}] Game {gid}: {len(participants)} players — skipped (not 5v5)")
                    continue

                valid_count += 1
                duration = max(d.get("gameDuration", 1), 1)
                timestamp = datetime.fromtimestamp(
                    d.get("gameCreation", 0) / 1000).strftime("%Y-%m-%d %H:%M")

                print(f"  [{valid_count}] Game {gid}: 5v5 custom on {timestamp}")

                for idx, p in enumerate(participants):
                    pname = "Unknown"
                    if idx < len(identities):
                        pl = identities[idx].get("player", {})
                        pname = pl.get("gameName") or pl.get("summonerName") or f"Player_{idx}"

                    stats = p.get("stats", {})
                    cid = p.get("championId", 0)
                    cname = champ_map.get(cid, f"Champ#{cid}")
                    lane = p.get("timeline", {}).get("lane", "UNKNOWN")
                    role = role_map.get(lane.upper() if isinstance(lane, str) else "", "Fill")
                    cs = stats.get("totalMinionsKilled", 0) + stats.get("neutralMinionsKilled", 0)

                    new_records.append({
                        "gameId": gid,
                        "timestamp": timestamp,
                        "player": pname,
                        "champion": cname,
                        "teamId": p.get("teamId", 0),
                        "win": stats.get("win", False),
                        "kills": stats.get("kills", 0),
                        "deaths": stats.get("deaths", 0),
                        "assists": stats.get("assists", 0),
                        "cs": cs,
                        "damage": stats.get("totalDamageDealtToChampions", 0),
                        "gold": stats.get("goldEarned", 0),
                        "vision": stats.get("visionScore", 0),
                        "role": role,
                        "duration": round(duration / 60, 1) if duration > 300 else duration,
                        "logged_by": logged_by,
                    })

            # Append new records to game log
            if new_records:
                print(f"\n  {valid_count} new 5v5 games, {len(new_records)} player records")
                print(f"\nSaving to game log...")
                append_game_log(spreadsheet, new_records, logged_by)
            else:
                print(f"\n  No new valid 5v5 games found")
        else:
            print("\n  No new games to process")

        # Rebuild stats from FULL game log (existing + new)
        print(f"\nRebuilding stats from complete game log...")
        all_records = load_full_game_log(spreadsheet)
        print(f"  {len(all_records)} total records in log")

        if not all_records:
            print("  No game data to analyze")
            sys.exit(0)

        player_stats, h2h, total_games = compute_stats_from_log(all_records)
        print(f"  {total_games} total 5v5 games, {len(player_stats)} unique players")

        # Write stats sheets
        print(f"\n{'='*60}")
        print("WRITING TO GOOGLE SHEETS")
        print(f"{'='*60}\n")

        write_overview(spreadsheet, player_stats, total_games, champ_map)
        write_h2h(spreadsheet, h2h, player_stats)
        write_inhouse_db(spreadsheet, player_stats)

        # Summary
        print(f"\n{'='*60}")
        print(f"IN-HOUSE SUMMARY — {total_games} total games")
        if customs:
            print(f"  ({len([r for r in (new_records if 'new_records' in dir() else [])]) // 10} new games added this run)")
        print(f"{'='*60}\n")
        print(f"{'Player':<20} {'Games':<6} {'W-L':<9} {'WR%':<7} {'KDA'}")
        print("_" * 52)
        for name, ps in sorted(player_stats.items(),
            key=lambda x: (x[1]["wins"]/max(x[1]["games"],1), x[1]["games"]), reverse=True):
            g = ps["games"]
            if g == 0: continue
            wr = round(ps["wins"]/g*100, 1)
            kda = round((ps["kills"]+ps["assists"])/max(ps["deaths"],1), 2)
            print(f"{name:<20} {g:<6} {ps['wins']}W-{g-ps['wins']}L   {wr:<7} {kda}")
        print(f"\nDone! Check 'In-House Stats' and 'In-House Head-to-Head' tabs.")
        print(f"Logged by: {logged_by}\n")


    # ── Inhouse Database (for scouting/draft integration) ────────

    def write_inhouse_db(spreadsheet, player_stats):
        try:
            spreadsheet.del_worksheet(spreadsheet.worksheet("_InhouseDB"))
        except gspread.exceptions.WorksheetNotFound:
            pass  # sheet doesn't exist yet, that's fine
        ws = sheets_retry(spreadsheet.add_worksheet, "_InhouseDB", rows=500, cols=13)
        rows = [["INHOUSE DATABASE - DO NOT EDIT", "", "", "", "", "",
                 datetime.now().strftime("%Y-%m-%d %H:%M")],
                ["player", "champion", "games", "wins", "wr", "kda",
                 "avg_kills", "avg_deaths", "avg_assists", "avg_damage",
                 "total_games", "total_wr", "roles"]]
        for name, ps in player_stats.items():
            g = ps["games"]
            if g == 0: continue
            total_wr = round(ps["wins"] / g * 100, 1)
            for champ, cs in ps["champs"].items():
                cg = cs["games"]
                cwr = round(cs["wins"] / cg * 100, 1)
                ckda = round((cs["kills"] + cs["assists"]) / max(cs["deaths"], 1), 2)
                champ_role_data = ps.get("champ_roles", {}).get(champ, {})
                role_str = ";".join(f"{r}:{c}" for r, c in champ_role_data.items() if c > 0)
                rows.append([name, champ, cg, cs["wins"], cwr, ckda,
                             round(cs["kills"]/cg, 1), round(cs["deaths"]/cg, 1),
                             round(cs["assists"]/cg, 1), round(cs["damage"]/cg),
                             g, total_wr, role_str])
        sheets_retry(ws.update, values=rows, range_name="A1")
        print("  Inhouse DB saved (for scouting/draft)")


    # ── Sheet Writers ────────────────────────────────────────────

    DARK = {"red":0.11,"green":0.11,"blue":0.18}
    HEADER = {"red":0.09,"green":0.14,"blue":0.28}
    SECTION = {"red":0.13,"green":0.17,"blue":0.30}
    GOLD = {"red":0.91,"green":0.72,"blue":0.29}
    WHITE = {"red":1,"green":1,"blue":1}
    LB = {"red":0.88,"green":0.92,"blue":0.98}
    LG = {"red":0.85,"green":0.95,"blue":0.85}

    def write_overview(spreadsheet, player_stats, total, champ_map):
        try:
            spreadsheet.del_worksheet(spreadsheet.worksheet("In-House Stats"))
        except gspread.exceptions.WorksheetNotFound:
            pass  # sheet doesn't exist yet, that's fine
        ws = sheets_retry(spreadsheet.add_worksheet, "In-House Stats", rows=300, cols=17)
        rows=[]; fmts=[]; merges=[]
        # 17 columns: # Player Games Wins Losses WinRate Last10 KDA AvgK AvgD AvgA AvgCS AvgDmg AvgGold CurStreak BestStreak MVPs
        NCOLS = 17
        pad=lambda d,n=NCOLS: d+[""]*(n-len(d))
        rn=lambda: len(rows)

        last_col = chr(64 + NCOLS)  # 'Q'

        rows.append(pad(["IN-HOUSE 5v5 STATS"])); merges.append(f"A{rn()}:{last_col}{rn()}")
        fmts.append((f"A{rn()}:{last_col}{rn()}", {"backgroundColor":DARK,"textFormat":{"bold":True,"fontSize":18,"foregroundColor":GOLD},"horizontalAlignment":"CENTER"}))
        ts=datetime.now().strftime("%Y-%m-%d %H:%M")
        rows.append(pad([f"{total} custom 5v5 games (all contributors combined)  |  Updated: {ts}"])); merges.append(f"A{rn()}:{last_col}{rn()}")
        fmts.append((f"A{rn()}:{last_col}{rn()}", {"backgroundColor":DARK,"textFormat":{"fontSize":11,"foregroundColor":WHITE},"horizontalAlignment":"CENTER"}))
        rows.append(pad([""]))

        rows.append(pad(["IN-HOUSE LEADERBOARD"])); merges.append(f"A{rn()}:{last_col}{rn()}")
        fmts.append((f"A{rn()}:{last_col}{rn()}", {"backgroundColor":SECTION,"textFormat":{"bold":True,"fontSize":14,"foregroundColor":GOLD},"horizontalAlignment":"CENTER"}))
        rows.append(pad(["#","Player","Games","Wins","Losses","Win Rate","Last 10","KDA","Avg K","Avg D","Avg A","Avg CS","Avg Dmg","Avg Gold","Cur Streak","Best Streak","MVPs"]))
        fmts.append((f"A{rn()}:{last_col}{rn()}", {"backgroundColor":HEADER,"textFormat":{"bold":True,"fontSize":10,"foregroundColor":WHITE},"horizontalAlignment":"CENTER"}))

        sp=sorted(player_stats.items(), key=lambda x:(x[1]["wins"]/max(x[1]["games"],1),x[1]["games"]), reverse=True)
        for i,(name,ps) in enumerate(sp,1):
            g=ps["games"]
            if g==0: continue
            wr=round(ps["wins"]/g*100,1)
            kda=round((ps["kills"]+ps["assists"])/max(ps["deaths"],1),2)
            recent_wr = ps.get("recent_wr")
            last10 = f"{int(recent_wr)}%" if recent_wr is not None else "—"
            bg=LG if i<=3 else(LB if i%2==0 else {"red":1,"green":1,"blue":1})
            rows.append(pad([i,name,g,ps["wins"],g-ps["wins"],f"{wr}%",last10,kda,
                round(ps["kills"]/g,1),round(ps["deaths"]/g,1),round(ps["assists"]/g,1),
                round(ps["cs"]/g),f"{round(ps['damage']/g):,}",f"{round(ps['gold']/g):,}",
                ps.get("win_streak",0),ps.get("best_streak",0),ps.get("mvp_count",0)]))
            fmts.append((f"A{rn()}:{last_col}{rn()}", {"backgroundColor":bg,"textFormat":{"fontSize":11,"bold":i<=3},"horizontalAlignment":"CENTER"}))

        rows.append(pad([""])); rows.append(pad([""]))
        rows.append(pad(["IN-HOUSE CHAMPION STATS"])); merges.append(f"A{rn()}:{last_col}{rn()}")
        fmts.append((f"A{rn()}:{last_col}{rn()}", {"backgroundColor":SECTION,"textFormat":{"bold":True,"fontSize":14,"foregroundColor":GOLD},"horizontalAlignment":"CENTER"}))

        for name,ps in sp:
            if ps["games"]==0: continue
            wr=round(ps["wins"]/ps["games"]*100,1)
            rows.append(pad([f"{name}  -  {ps['games']} games  |  {wr}% WR"])); merges.append(f"A{rn()}:{last_col}{rn()}")
            fmts.append((f"A{rn()}:{last_col}{rn()}", {"backgroundColor":{"red":0.2,"green":0.3,"blue":0.5},"textFormat":{"bold":True,"fontSize":12,"foregroundColor":WHITE},"horizontalAlignment":"CENTER"}))
            rows.append(pad(["Champion","Games","Wins","Losses","WR%","KDA","Avg K","Avg D","Avg A","Avg Dmg"]))
            fmts.append((f"A{rn()}:J{rn()}", {"backgroundColor":HEADER,"textFormat":{"bold":True,"fontSize":10,"foregroundColor":WHITE},"horizontalAlignment":"CENTER"}))
            for j,(ch,cs) in enumerate(sorted(ps["champs"].items(), key=lambda x:x[1]["games"], reverse=True)):
                cg=cs["games"]; cwr=round(cs["wins"]/cg*100,1); ckda=round((cs["kills"]+cs["assists"])/max(cs["deaths"],1),2)
                bg=LB if j%2==0 else {"red":1,"green":1,"blue":1}
                rows.append(pad([ch,cg,cs["wins"],cg-cs["wins"],f"{cwr}%",ckda,
                    round(cs["kills"]/cg,1),round(cs["deaths"]/cg,1),round(cs["assists"]/cg,1),f"{round(cs['damage']/cg):,}"]))
                fmts.append((f"A{rn()}:J{rn()}", {"backgroundColor":bg,"textFormat":{"fontSize":11},"horizontalAlignment":"CENTER"}))
            rows.append(pad([""]))

        rows.append(pad([""])); rows.append(pad([""]))
        rows.append(pad(["IN-HOUSE ROLE PERFORMANCE"])); merges.append(f"A{rn()}:{last_col}{rn()}")
        fmts.append((f"A{rn()}:{last_col}{rn()}", {"backgroundColor":SECTION,"textFormat":{"bold":True,"fontSize":14,"foregroundColor":GOLD},"horizontalAlignment":"CENTER"}))
        rows.append(pad(["Player","Top","","Jungle","","Mid","","Bot","","Support",""]))
        fmts.append((f"A{rn()}:K{rn()}", {"backgroundColor":HEADER,"textFormat":{"bold":True,"fontSize":10,"foregroundColor":WHITE},"horizontalAlignment":"CENTER"}))
        rows.append(pad(["","G","WR%","G","WR%","G","WR%","G","WR%","G","WR%"]))
        fmts.append((f"A{rn()}:K{rn()}", {"backgroundColor":HEADER,"textFormat":{"bold":True,"fontSize":9,"foregroundColor":WHITE},"horizontalAlignment":"CENTER"}))
        for name,ps in sp:
            if ps["games"]==0: continue
            rd=[name]
            for role in ["Top","Jungle","Mid","Bot","Support"]:
                rs=ps["roles"].get(role,{"games":0,"wins":0}); rg=rs["games"]
                rd.extend([rg if rg>0 else "-", f"{round(rs['wins']/rg*100)}%" if rg>0 else "-"])
            rows.append(pad(rd))
            fmts.append((f"A{rn()}:K{rn()}", {"backgroundColor":LB,"textFormat":{"fontSize":11},"horizontalAlignment":"CENTER"}))

        sheets_retry(ws.update, values=rows, range_name="A1")
        for m in merges:
            sheets_retry(ws.merge_cells, m)
        col_px=[50,120,60,55,60,70,65,55,60,60,60,70,95,90,80,85,55]
        reqs=[{"updateDimensionProperties":{"range":{"sheetId":ws.id,"dimension":"COLUMNS","startIndex":ci,"endIndex":ci+1},"properties":{"pixelSize":px},"fields":"pixelSize"}} for ci,px in enumerate(col_px)]
        reqs.append({"updateDimensionProperties":{"range":{"sheetId":ws.id,"dimension":"ROWS","startIndex":0,"endIndex":1},"properties":{"pixelSize":50},"fields":"pixelSize"}})
        sheets_retry(spreadsheet.batch_update, {"requests":reqs})
        for i in range(0,len(fmts),15):
            sheets_retry(ws.batch_format, [{"range":r,"format":f} for r,f in fmts[i:i+15]])
        print("  In-House Stats written")


    def write_h2h(spreadsheet, h2h, player_stats):
        try:
            spreadsheet.del_worksheet(spreadsheet.worksheet("In-House Head-to-Head"))
        except gspread.exceptions.WorksheetNotFound:
            pass  # sheet doesn't exist yet, that's fine
        active=sorted([n for n,ps in player_stats.items() if ps["games"]>0])
        n=len(active)
        ws=sheets_retry(spreadsheet.add_worksheet, "In-House Head-to-Head", rows=n*2+15, cols=n+3)
        rows=[]; fmts=[]
        pad_n=n+2; ec=chr(64+min(pad_n,26))
        pad=lambda d: d+[""]*(pad_n-len(d))
        rn=lambda: len(rows)

        rows.append(pad(["IN-HOUSE HEAD-TO-HEAD"]))
        fmts.append((f"A{rn()}:{ec}{rn()}", {"backgroundColor":DARK,"textFormat":{"bold":True,"fontSize":16,"foregroundColor":GOLD},"horizontalAlignment":"CENTER"}))
        rows.append(pad([""]))

        for title, ks, kw in [("TEAMMATE WIN RATE","same_team","same_wins"),("HEAD-TO-HEAD (opposing)","vs","vs_wins")]:
            rows.append(pad([title]))
            fmts.append((f"A{rn()}:{ec}{rn()}", {"backgroundColor":SECTION,"textFormat":{"bold":True,"fontSize":13,"foregroundColor":GOLD},"horizontalAlignment":"CENTER"}))
            rows.append(pad([""]+active))
            fmts.append((f"A{rn()}:{chr(64+n+1)}{rn()}", {"backgroundColor":HEADER,"textFormat":{"bold":True,"fontSize":9,"foregroundColor":WHITE},"horizontalAlignment":"CENTER"}))
            for a in active:
                rd=[a]
                for b in active:
                    if a==b: rd.append("-")
                    else:
                        d=h2h.get(a,{}).get(b,{ks:0,kw:0}); t=d.get(ks,0); w=d.get(kw,0)
                        rd.append(f"{round(w/t*100)}% ({t})" if t>0 else "-")
                rows.append(pad(rd))
                fmts.append((f"A{rn()}:{chr(64+n+1)}{rn()}", {"backgroundColor":LB,"textFormat":{"fontSize":10},"horizontalAlignment":"CENTER"}))
                fmts.append((f"A{rn()}", {"backgroundColor":HEADER,"textFormat":{"bold":True,"fontSize":9,"foregroundColor":WHITE}}))
            rows.append(pad([""])); rows.append(pad([""]))

        sheets_retry(ws.update, values=rows, range_name="A1")
        reqs=[{"updateDimensionProperties":{"range":{"sheetId":ws.id,"dimension":"COLUMNS","startIndex":0,"endIndex":1},"properties":{"pixelSize":100},"fields":"pixelSize"}}]
        for ci in range(1,n+1):
            reqs.append({"updateDimensionProperties":{"range":{"sheetId":ws.id,"dimension":"COLUMNS","startIndex":ci,"endIndex":ci+1},"properties":{"pixelSize":85},"fields":"pixelSize"}})
        sheets_retry(spreadsheet.batch_update, {"requests":reqs})
        for i in range(0,len(fmts),15):
            sheets_retry(ws.batch_format, [{"range":r,"format":f} for r,f in fmts[i:i+15]])
        print("  Head-to-Head written")

    main()


def _rewire_stdio():
    """Rewire sys.stdout/stderr to the real pipe fd when running headless.

    PyInstaller --windowed sets sys.stdout = None (no console attached).
    When the GUI spawns a child instance with --mode=fetch_ranks/inhouse,
    the parent opens a pipe on fd 1/2, but Python's print() still targets
    sys.stdout — which is None. Rewiring it to the OS fd makes all print()
    output flow through the pipe to the parent's console widget.
    """
    import io
    for fd, name in ((1, "stdout"), (2, "stderr")):
        stream = getattr(sys, name, None)
        if stream is None or not hasattr(stream, "write"):
            try:
                setattr(sys, name,
                        io.TextIOWrapper(io.FileIO(fd, closefd=False),
                                         encoding="utf-8", line_buffering=True))
            except Exception:
                pass


def _main_dispatch():
    """Decide whether to launch the GUI or run a CLI subcommand."""
    argv = sys.argv[1:]
    mode = None
    cli_args = []
    for a in argv:
        if a.startswith("--mode="):
            mode = a.split("=", 1)[1]
        else:
            cli_args.append(a)

    if mode in ("fetch_ranks", "inhouse"):
        _rewire_stdio()

    if mode == "fetch_ranks":
        _run_fetch_ranks(cli_args)
    elif mode == "inhouse":
        _run_inhouse(cli_args)
    else:
        app = App()
        app.mainloop()


if __name__ == "__main__":
    _main_dispatch()
