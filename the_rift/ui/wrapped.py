"""
wrapped.py — Phase 5d: Rift Wrapped, animated end-of-season recap.

A presentation-style overlay that auto-cycles through 7 polished pages of
season highlights pulled from `live.records`, `live.match_history`,
`live.pred_leaderboard`, and the active season's standings.

Open via `wrapped.open()`. Each page auto-advances; click anywhere advances
faster; Escape closes. Runs entirely from cached data — no network calls on
the hot path.
"""
from __future__ import annotations

import time
import math
from datetime import datetime, timezone

import dearpygui.dearpygui as dpg

from theme import C, RANK_COLORS
from core.animations import anim
from ui import effects
from ui import luxe
from ui.fmt import commas, compact, clamp_text
from data.reader import (
    live,
    load_records,
    load_match_history,
    load_seasons,
    load_season_standings,
    load_prediction_leaderboard,
)


PAGE_DURATION_MS = 6500
TRANSITION_MS    = 420


class WrappedState:
    def __init__(self):
        self.open_frac   = 0.0       # 0..1 — overlay open progress
        self.is_open     = False
        self.page_idx    = 0
        self.page_t0     = 0.0       # monotonic when current page started
        self.trans_t0    = 0.0       # last transition trigger
        self.pages       = []        # populated when opened

    def open(self):
        if self.is_open:
            return
        self.is_open = True
        # Ensure data
        if not live.match_history_loaded:
            load_match_history()
        if not live.records_loaded:
            load_records()
        if not live.seasons_loaded:
            load_seasons()
        if not live.pred_leaderboard_loaded:
            load_prediction_leaderboard()
        # Build pages
        self.pages = _build_pages()
        self.page_idx = 0
        self.page_t0  = time.monotonic()
        self.trans_t0 = time.monotonic()
        anim.tween(0.0, 1.0, 360, "out_cubic",
                   on_update=lambda v: setattr(self, "open_frac", v))

    def close(self):
        if not self.is_open:
            return
        self.is_open = False
        anim.tween(self.open_frac, 0.0, 260, "out_cubic",
                   on_update=lambda v: setattr(self, "open_frac", v))

    def advance(self):
        if not self.pages:
            return
        self.page_idx += 1
        if self.page_idx >= len(self.pages):
            self.close()
            return
        self.page_t0 = time.monotonic()
        self.trans_t0 = time.monotonic()


wrapped = WrappedState()


# ---------------------------------------------------------------------------
# Page builders
# ---------------------------------------------------------------------------

def _active_season():
    seasons = live.seasons or []
    for s in reversed(seasons):
        if s.get("is_active"):
            return s
    return seasons[-1] if seasons else None


def _build_pages():
    season = _active_season() or {"name": "All Time"}
    season_name = (season.get("name") or "ALL TIME").upper()

    # Stats
    matches_n = season.get("match_count") if season else None
    if matches_n is None:
        matches_n = len(live.match_history or [])
    standings = []
    sid = season.get("id") if season else None
    if sid:
        if sid not in live.season_standings and sid not in live._standings_inflight:
            load_season_standings(sid)
        standings = ((live.season_standings.get(sid) or {}).get("standings")) or []

    # Top performer (most wins)
    mvp = standings[0] if standings else None

    # Pentakill / best single-game KDA
    bestkda = (live.records or {}).get("best_kda_game") or {}

    # Longest streak
    streak_winner = (live.records or {}).get("longest_win_streak") or {}

    # Most damage
    most_dmg = (live.records or {}).get("most_damage") or {}

    # Sharpest predictor
    eligible = [p for p in (live.pred_leaderboard or []) if p.get("total", 0) >= 3]
    sharp = max(eligible, key=lambda p: p.get("accuracy", 0)) if eligible else None

    pages = []
    pages.append({
        "kind": "intro",
        "title": season_name,
        "subtitle": "THE RIFT  ·  WRAPPED",
    })
    pages.append({
        "kind": "big_number",
        "label": "GAMES PLAYED",
        "value": commas(int(matches_n or 0)),
        "footer": "A whole season of inhouses, drafts, and drama.",
    })
    if mvp:
        pages.append({
            "kind": "spotlight",
            "label": "SEASON MVP",
            "title": mvp.get("player", "—"),
            "lines": [
                ("WINS",     str(mvp.get("wins", 0))),
                ("RECORD",   f"{mvp.get('wins', 0)}-{mvp.get('losses', 0)}"),
                ("WIN RATE", f"{mvp.get('wr', 0):.0f}%"),
                ("KDA",      f"{mvp.get('kda', 0):.2f}"),
            ],
            "accent": (240, 200, 130, 255),
        })
    if streak_winner.get("player"):
        pages.append({
            "kind": "spotlight",
            "label": "ON A HEATER",
            "title": streak_winner.get("player", "—"),
            "lines": [
                ("LONGEST WIN STREAK", str(streak_winner.get("value", 0))),
                ("That's how legends are made.", ""),
            ],
            "accent": (255, 140, 110, 255),
        })
    if bestkda.get("player"):
        kda_val = bestkda.get("value") or 0
        try:
            kda_txt = f"{float(kda_val):.2f}"
        except Exception:
            kda_txt = str(kda_val)
        pages.append({
            "kind": "spotlight",
            "label": "PERFORMANCE OF THE SEASON",
            "title": bestkda.get("player", "—"),
            "lines": [
                ("CHAMPION", str(bestkda.get("champion") or "—")),
                ("KDA",      kda_txt),
                ("KILLS / DEATHS / ASSISTS",
                 f"{bestkda.get('kills',0)}/{bestkda.get('deaths',0)}/{bestkda.get('assists',0)}"),
            ],
            "accent": (200, 170, 110, 255),
        })
    if most_dmg.get("player"):
        pages.append({
            "kind": "spotlight",
            "label": "DAMAGE DEALER",
            "title": most_dmg.get("player", "—"),
            "lines": [
                ("MOST DAMAGE", compact(int(most_dmg.get("value") or 0))),
                ("CHAMPION", str(most_dmg.get("champion") or "—")),
            ],
            "accent": (200, 100, 110, 255),
        })
    if sharp:
        pages.append({
            "kind": "spotlight",
            "label": "SHARPEST MIND",
            "title": sharp.get("voter", "—"),
            "lines": [
                ("PREDICTION ACCURACY", f"{sharp.get('accuracy',0):.0f}%"),
                ("CORRECT CALLS", f"{sharp.get('correct',0)}/{sharp.get('total',0)}"),
            ],
            "accent": (118, 168, 220, 255),
        })
    pages.append({
        "kind": "outro",
        "title": "GG WP",
        "subtitle": "SEE YOU IN THE NEXT SEASON",
    })
    return pages


# ---------------------------------------------------------------------------
# Draw helpers
# ---------------------------------------------------------------------------

def _page_progress():
    """0..1 progress through the current page's duration."""
    elapsed = (time.monotonic() - wrapped.page_t0) * 1000.0
    return min(1.0, elapsed / PAGE_DURATION_MS)


def _transition_alpha():
    """1.0 when fully on-screen, dips on first/last 200ms for crossfade."""
    elapsed = (time.monotonic() - wrapped.trans_t0) * 1000.0
    if elapsed < TRANSITION_MS:
        return min(1.0, elapsed / TRANSITION_MS)
    return 1.0


def _draw_intro(dl, w, h, page, alpha):
    cx = w // 2
    cy = h // 2
    # Big title
    title = page.get("title", "")
    sz = 88
    tw = len(title) * (sz * 4 // 10)
    dpg.draw_text((cx - tw // 2, cy - 80), title,
                  color=(*C["gold_lt"][:3], int(255 * alpha)),
                  size=sz, parent=dl)
    sub = page.get("subtitle", "")
    sw = len(sub) * 8
    dpg.draw_text((cx - sw // 2, cy + 40), sub,
                  color=(*C["gold"][:3], int(220 * alpha)),
                  size=18, parent=dl)
    # Rule
    dpg.draw_line((cx - 80, cy + 24), (cx + 80, cy + 24),
                  color=(*C["gold"][:3], int(220 * alpha)),
                  thickness=2, parent=dl)


def _draw_outro(dl, w, h, page, alpha):
    _draw_intro(dl, w, h, page, alpha)


def _draw_big_number(dl, w, h, page, alpha):
    cx = w // 2
    cy = h // 2
    label = page.get("label", "")
    value = page.get("value", "")
    footer = page.get("footer", "")
    # Label
    lw = len(label) * 8
    dpg.draw_text((cx - lw // 2, cy - 140), label,
                  color=(*C["gold"][:3], int(220 * alpha)),
                  size=18, parent=dl)
    # Big number (count-up)
    try:
        live_val = effects.count_up("wrapped_num", float(str(value).replace(",", "")), rate=0.16)
        vtxt = commas(int(round(live_val)))
    except Exception:
        vtxt = str(value)
    sz = 156
    vw = len(vtxt) * (sz * 4 // 10)
    dpg.draw_text((cx - vw // 2, cy - 80), vtxt,
                  color=(*C["gold_lt"][:3], int(255 * alpha)),
                  size=sz, parent=dl)
    # Footer
    if footer:
        fw = len(footer) * 7
        dpg.draw_text((cx - fw // 2, cy + 100), footer,
                      color=(*C["txt2"][:3], int(220 * alpha)),
                      size=15, parent=dl)


def _draw_spotlight(dl, w, h, page, alpha):
    cx = w // 2
    cy = h // 2
    accent = page.get("accent") or C["gold"]
    label = page.get("label", "")
    title = page.get("title", "")
    lines = page.get("lines") or []

    # Chip
    chip_w = max(180, len(label) * 9 + 36)
    dpg.draw_rectangle((cx - chip_w // 2, cy - 180),
                       (cx + chip_w // 2, cy - 150),
                       fill=(*accent[:3], int(60 * alpha)),
                       color=(*accent[:3], int(220 * alpha)),
                       rounding=15, parent=dl)
    lw = len(label) * 8
    dpg.draw_text((cx - lw // 2, cy - 173), label,
                  color=(*accent[:3], int(240 * alpha)),
                  size=14, parent=dl)

    # Title
    sz = 78
    tw = len(title) * (sz * 4 // 10)
    dpg.draw_text((cx - tw // 2, cy - 130), str(title).upper(),
                  color=(*C["gold_lt"][:3], int(255 * alpha)),
                  size=sz, parent=dl)
    # Rule
    dpg.draw_line((cx - 120, cy - 30), (cx + 120, cy - 30),
                  color=(*accent[:3], int(220 * alpha)),
                  thickness=2, parent=dl)

    # Lines (2 cols if pairs)
    line_y = cy + 0
    for lbl, val in lines[:4]:
        if val:
            dpg.draw_text((cx - 280, line_y), str(lbl),
                          color=(*C["txt2"][:3], int(220 * alpha)),
                          size=16, parent=dl)
            vt = str(val)
            vw = len(vt) * 14
            dpg.draw_text((cx + 280 - vw, line_y), vt,
                          color=(*C["gold_lt"][:3], int(255 * alpha)),
                          size=20, parent=dl)
        else:
            tw = len(lbl) * 8
            dpg.draw_text((cx - tw // 2, line_y), str(lbl),
                          color=(*C["txt2"][:3], int(220 * alpha)),
                          size=16, parent=dl)
        line_y += 38


# ---------------------------------------------------------------------------
# Public draw
# ---------------------------------------------------------------------------

def draw(dl, w, h):
    """Render the Wrapped overlay on top of the content area when open. Also
    drives auto-advance + click-to-advance."""
    if wrapped.open_frac <= 0.01 and not wrapped.is_open:
        return

    frac = wrapped.open_frac
    bg_a = int(245 * frac)
    # Backdrop — V2: cinematic stage instead of a flat sheet. Deep navy with
    # a warm gold floor-light, cool top-light, and a vignette.
    dpg.draw_rectangle((0, 0), (w, h),
                       fill=(*C["bg"][:3], bg_a),
                       color=(0, 0, 0, 0), parent=dl)
    luxe.glow(dl, w * 0.5, h * 1.12, w * 0.55, C["gold"], int(34 * frac))
    luxe.glow(dl, w * 0.5, -h * 0.25, w * 0.7, (40, 72, 118), int(60 * frac))

    # Localized ambient field
    effects.draw_ambient_motes(dl, 0, 0, w, h, accent=C["gold"],
                                alpha=int(120 * frac), n=22, seed=23)
    luxe.vignette(dl, 0, 0, w, h, int(110 * frac))

    if wrapped.pages:
        page = wrapped.pages[min(wrapped.page_idx, len(wrapped.pages) - 1)]
        alpha = frac * _transition_alpha()
        kind = page.get("kind")
        if kind == "intro":
            _draw_intro(dl, w, h, page, alpha)
        elif kind == "outro":
            _draw_outro(dl, w, h, page, alpha)
        elif kind == "big_number":
            _draw_big_number(dl, w, h, page, alpha)
        elif kind == "spotlight":
            _draw_spotlight(dl, w, h, page, alpha)

        # Page progress dots + bar (bottom)
        n = len(wrapped.pages)
        if n > 1:
            track_w = min(420, max(160, w // 3))
            track_x = w // 2 - track_w // 2
            track_y = h - 80
            for i in range(n):
                seg_w = (track_w - (n - 1) * 6) // n
                sx = track_x + i * (seg_w + 6)
                # Bar background
                dpg.draw_rectangle((sx, track_y), (sx + seg_w, track_y + 4),
                                   fill=(*C["rule_dark"][:3], int(180 * frac)),
                                   color=(0, 0, 0, 0), rounding=2, parent=dl)
                # Filled portion for current page
                if i < wrapped.page_idx:
                    dpg.draw_rectangle((sx, track_y), (sx + seg_w, track_y + 4),
                                       fill=(*C["gold"][:3], int(220 * frac)),
                                       color=(0, 0, 0, 0), rounding=2, parent=dl)
                elif i == wrapped.page_idx:
                    p_frac = _page_progress()
                    dpg.draw_rectangle((sx, track_y),
                                       (sx + int(seg_w * p_frac), track_y + 4),
                                       fill=(*C["gold"][:3], int(255 * frac)),
                                       color=(0, 0, 0, 0), rounding=2, parent=dl)

        # Hint text + close X
        if wrapped.is_open:
            hint = "CLICK ANYWHERE FOR NEXT  ·  ESC TO CLOSE"
            hint_w = len(hint) * 7
            dpg.draw_text(((w - hint_w) // 2, h - 60),
                          hint,
                          color=(*C["txt2"][:3], int(240 * frac)),
                          size=14, parent=dl)

    # Auto-advance
    if wrapped.is_open and _page_progress() >= 1.0:
        wrapped.advance()

    # Input — cooperate with main.py's per-frame gates
    from core.state import state as _st
    if wrapped.is_open:
        if dpg.is_mouse_button_clicked(0) and not _st.click_consumed:
            _st.click_consumed = True
            wrapped.advance()
        # Esc handled in main.py via edge-detected state.esc_pressed


def open_wrapped():
    wrapped.open()


def is_open():
    return wrapped.is_open or wrapped.open_frac > 0.02
