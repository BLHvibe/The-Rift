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

import tkinter as tk
from tkinter import ttk, scrolledtext
import subprocess
import threading
import queue
import os
import sys
import json
import io
import re
import time
import webbrowser
import random
from datetime import datetime

from core.config import (
    CONFIG_FILE, DEFAULT_CONFIG,
    sheets_retry, cached_get_all_values, invalidate_sheet_cache,
    load_config, save_config, load_players_from_sheet,
)
from core.theme import C, ROLES, ANIM_ROW_REVEAL_MS, ANIM_PODIUM_CENTER_MS, ANIM_PODIUM_SIDES_OFFSET_MS, ANIM_PODIUM_STAGGER_MS

# ── Version & Update Info ─────────────────────────────────────
# These get overwritten by build_merger.py when the .exe is packaged.
__version__ = "0.0.0"
GITHUB_REPO = ""  # e.g. "blhei/lol-power-rankings" — set in build_merger.py



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
                 font=("Segoe UI", 9, "italic")).pack(pady=(6, 8))

        shimmer_cv = tk.Canvas(body, bg=C["gold_dk"], highlightthickness=0, height=6)
        shimmer_cv.pack(fill="x", padx=40, pady=(0, 22))

        _sx = [-160]
        def _tick():
            if not shimmer_cv.winfo_exists():
                return
            shimmer_cv.delete("all")
            w = shimmer_cv.winfo_width()
            if w < 10:
                shimmer_cv.after(50, _tick)
                return
            shimmer_cv.create_rectangle(0, 0, w, 6, fill=C["gold_dk"], outline="")
            # Bright core
            shimmer_cv.create_rectangle(_sx[0] + 20, 1, _sx[0] + 140, 5,
                                        fill=C["gold_lt"], outline="")
            # Soft edges
            shimmer_cv.create_rectangle(_sx[0], 0, _sx[0] + 20, 6,
                                        fill=C["gold"], outline="")
            shimmer_cv.create_rectangle(_sx[0] + 140, 0, _sx[0] + 160, 6,
                                        fill=C["gold"], outline="")
            _sx[0] += 8
            if _sx[0] > w + 160:
                _sx[0] = -160
            shimmer_cv.after(25, _tick)
        shimmer_cv.after(200, _tick)

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

        # Podium medal border thickness: gold=4, silver/bronze=2
        rank = player["rank"]
        border_thick = 4 if rank == 1 else 2

        # Card body — bordered frame, animated per rank
        card = tk.Frame(outer, bg=C["panel"],
                        highlightthickness=border_thick,
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

        # Breathing border glow — gold for #1, silver for #2, bronze for #3
        import math
        _MEDAL_COLORS = {
            1: ((0x3a, 0x2d, 0x12), (0xff, 0xd7, 0x00)),  # dark rule → bright gold
            2: ((0x2a, 0x2a, 0x2a), (0xe8, 0xe8, 0xe8)),  # dark → silver
            3: ((0x2a, 0x18, 0x08), (0xcd, 0x7f, 0x32)),  # dark → bronze
        }
        if rank in _MEDAL_COLORS:
            lo, hi = _MEDAL_COLORS[rank]
            _tick = [0]
            def _breathe(_card=card, _lo=lo, _hi=hi):
                if not _card.winfo_exists():
                    return
                b = (math.sin(_tick[0] * 0.07) + 1) / 2
                r = int(_lo[0] + (_hi[0] - _lo[0]) * b)
                g = int(_lo[1] + (_hi[1] - _lo[1]) * b)
                bl = int(_lo[2] + (_hi[2] - _lo[2]) * b)
                _card.configure(highlightbackground=f"#{r:02x}{g:02x}{bl:02x}")
                _tick[0] += 1
                _card.after(50, _breathe)
            card.after(400, _breathe)

        # Fade podium label text in from card bg
        self._fade_lbl(name_lbl, C["panel"], C["gold_lt"], steps=12, ms=25)

    def _fade_lbl(self, lbl, from_c, to_c, steps=8, ms=20):
        """Interpolate a single Label's fg from from_c to to_c."""
        def _rgb(h):
            h = h.lstrip("#")
            return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        fr, to = _rgb(from_c), _rgb(to_c)
        lbl.configure(fg=from_c)
        def _step(i, _l=lbl):
            if not _l.winfo_exists():
                return
            t = i / steps
            r = int(fr[0] + (to[0] - fr[0]) * t)
            g = int(fr[1] + (to[1] - fr[1]) * t)
            b = int(fr[2] + (to[2] - fr[2]) * t)
            _l.configure(fg=f"#{r:02x}{g:02x}{b:02x}")
            if i < steps:
                _l.after(ms, lambda: _step(i + 1))
        _step(0)

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
        stripe = tk.Frame(row, bg=rating_color, width=6)
        stripe.pack(side="left", fill="y")
        stripe.pack_propagate(False)

        # Flash stripe bright gold on row appear, then settle to rating color
        def _stripe_flash(step, _s=stripe):
            if not _s.winfo_exists():
                return
            if step == 0:
                _s.configure(bg=C["gold_lt"], width=8)
                _s.after(80, lambda: _stripe_flash(1))
            elif step == 1:
                _s.configure(bg=C["gold"], width=7)
                _s.after(100, lambda: _stripe_flash(2))
            else:
                _s.configure(bg=rating_color, width=6)
        _stripe_flash(0)

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
        score_val_lbl = tk.Label(score_box, text=str(player["final_score"]),
                                 bg=row_bg, fg=C["gold"],
                                 font=("Segoe UI", 22, "bold"))
        score_val_lbl.pack(pady=(0, 8))

        # Bottom rule-color separator
        tk.Frame(row_outer, bg=C["rule"], height=1).pack(fill="x")

        # Fade the two most visible labels in from row background
        self._fade_lbl(name_lbl, row_bg, C["gold_lt"], steps=8, ms=20)
        self._fade_lbl(score_val_lbl, row_bg, C["gold"], steps=8, ms=20)

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
        return os.path.dirname(os.path.abspath(__file__))

    def _py(self):
        return "python" if sys.platform == "win32" else "python3"

    def _build_cmd(self, mode):
        py = self._py()
        sd = self._script_dir()
        key = self.api_var.get().strip()
        sheet = self.config["sheet_url"]
        creds = self.config["creds_path"]

        if mode == "inhouse":
            return [py, os.path.join(sd, "inhouse_tracker.py"),
                    "--sheet", sheet, "--creds", creds]

        base = [py, os.path.join(sd, "fetch_ranks_gsheets.py"),
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


if __name__ == "__main__":
    app = App()
    app.mainloop()

