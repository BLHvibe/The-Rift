"""
profile.py — Phase 4b: global Player Profile slide-in panel.

A floating right-side panel showing a deep view of one player:
identity header, current rank, recent form sparkline, champion pool grid,
auto tags, rivalries, records held, recent matches.

Any tab opens it by setting `state.nav_to_profile = name`. The panel itself
is rendered once per frame from `main.py` after the active tab and toasts, so
it floats over every surface and works exactly the same regardless of context.
A click on the backdrop or the X button closes it. Data is lazy-loaded from
existing caches (live.match_history / live.rivalries / live.records /
live.scout / live.inhouse / live.rankings) — no extra fetches on the hot path.
"""
from __future__ import annotations

import os
import time
import math
from collections import Counter

import dearpygui.dearpygui as dpg

from theme import C, RANK_COLORS
from core.state import state
from core.animations import anim
from ui import effects
from ui import luxe
from ui.fmt import commas, compact, pct, signed, clamp_text
from data.reader import (
    live, load_rivalries, load_match_history,
    load_player_achievements,
)


PANEL_W      = 640
PAD          = 22
GAP          = 14
HEADER_H     = 116
SECTION_GAP  = 18
SCROLL_STEP  = 56

_VP_TITLE_H = 52   # mirrors main.TITLE_H


class ProfileState:
    def __init__(self):
        self.name        = None       # currently displayed player
        self.frac        = 0.0        # 0..1 panel-open progress
        self.scroll      = 0          # px scroll inside panel
        self.scroll_max  = 0          # last-computed max scroll
        self._wheel_acc  = 0.0

    def open(self, name):
        if not name:
            return
        if self.name == name:
            self.close()
            return
        opening = (self.name is None or self.frac <= 0.05)
        self.name   = name
        self.scroll = 0
        if opening:
            anim.tween(0.0, 1.0, 280, "out_cubic",
                       on_update=lambda v: setattr(self, "frac", v))
        # Lazy-load anything we might need
        if not live.match_history_loaded and not live.match_history_error:
            load_match_history()
        load_rivalries(name)
        load_player_achievements(name)

    def close(self):
        if self.name is None and self.frac <= 0.01:
            return
        anim.tween(self.frac, 0.0, 220, "out_cubic",
                   on_update=lambda v: setattr(self, "frac", v),
                   on_done=self._cleared)

    def _cleared(self):
        if self.frac < 0.02:
            self.name = None


profile = ProfileState()
_profile_hits = {}   # transient single-frame hitbox slots (e.g. share button)


# ---------------------------------------------------------------------------
# Data assembly
# ---------------------------------------------------------------------------

def _player_rankings_row(name):
    for p in (live.rankings or []):
        if p.get("name") == name:
            return p
    return None


def _player_inhouse_row(name):
    for p in (live.inhouse or []):
        if (p.get("player") or p.get("name")) == name:
            return p
    return None


def _player_scout_row(name):
    for p in (live.scout or []):
        if (p.get("name") or p.get("player")) == name:
            return p
    return None


def _player_matches(name, limit=10):
    """Most recent matches that include this player (most recent first)."""
    out = []
    for m in (live.match_history or []):
        parts = m.get("participants") or []
        for pt in parts:
            # Server schema (server/db.py) writes participant rows with key
            # "player". The other fallbacks are dead — kept as defensive aliases.
            pname = (pt.get("player") or pt.get("player_name") or
                     pt.get("name") or pt.get("display_name"))
            if pname == name:
                out.append((m, pt))
                break
        if len(out) >= limit:
            break
    return out


def _form_sparkline(name, last_n=10):
    """Last-N results for the player as a list of 1=win / 0=loss (newest last).
    Newest-first match_history is reversed at the end so the rightmost cell is
    the most recent."""
    results = []
    for m in (live.match_history or []):
        if len(results) >= last_n:
            break
        parts = m.get("participants") or []
        for pt in parts:
            pname = (pt.get("player") or pt.get("player_name") or
                     pt.get("name") or pt.get("display_name"))
            if pname != name:
                continue
            # Use the participant's own `win` column directly when present —
            # it's authoritative and doesn't rely on side/winner heuristics.
            if "win" in pt and pt["win"] is not None:
                results.append(1 if pt["win"] else 0)
            else:
                winner = (m.get("winner") or "").lower()
                side = (pt.get("team") or "").lower()
                won = (side and winner and side == winner)
                results.append(1 if won else 0)
            break
    return list(reversed(results))


def _player_tags(name):
    """A small auto-tag list using the same patterns as scout._compute_player_tags
    but resilient to data shape differences (works with rankings/inhouse-only rows)."""
    tags = []
    row_ih = _player_inhouse_row(name) or {}
    row_sc = _player_scout_row(name) or {}

    # Games + WR from inhouse table.
    games = int(row_ih.get("games") or 0)
    wins  = int(row_ih.get("wins") or 0)
    losses = int(row_ih.get("losses") or max(0, games - wins))
    wr = (wins / games * 100.0) if games else None
    kda = float(row_ih.get("kda") or row_sc.get("kda") or 0.0)

    if games >= 150:
        tags.append(("VETERAN", C["gold"]))
    elif games >= 40:
        tags.append(("ACTIVE", (118, 168, 220, 255)))
    elif games > 0:
        tags.append(("NEWCOMER", (155, 200, 155, 255)))

    if wr is not None and games >= 20:
        if wr >= 60:
            tags.append(("WIN MACHINE", C["win"]))
        elif wr <= 42:
            tags.append(("SLUMPING", C["loss"]))

    if kda >= 5.0:
        tags.append(("KDA GOD", C["gold_lt"]))
    elif kda >= 4.0:
        tags.append(("KDA MONSTER", (200, 175, 130, 255)))

    # Form from recent results
    form = _form_sparkline(name, last_n=5)
    if form:
        recent_wins = sum(form)
        if recent_wins >= 4:
            tags.append(("HOT", (255, 140, 110, 255)))
        elif recent_wins <= 1:
            tags.append(("COLD", (130, 175, 220, 255)))

    # Primary role
    role = (row_sc.get("primary_role") or
            row_ih.get("primary_role") or
            live.primary_roles.get(name))
    if role:
        tags.append((f"{role.upper()} MAIN", (175, 110, 220, 255)))

    return tags


def _records_held(name):
    """League records this player currently holds."""
    held = []
    for key, rec in (live.records or {}).items():
        if not rec:
            continue
        holder = rec.get("player") or rec.get("holder")
        if holder == name:
            held.append((key, rec))
    return held


# ---------------------------------------------------------------------------
# Draw helpers
# ---------------------------------------------------------------------------

def _draw_header(dl, x, y, w, name):
    h = HEADER_H
    # V2 header — gradient surface + gold edge light along the bottom.
    dpg.draw_rectangle((x, y), (x + w, y + h),
                       fill=C["card_hover"], color=(0, 0, 0, 0),
                       rounding=0, parent=dl)
    luxe.vfade(dl, x, y, x + w, y + h, (52, 84, 128), 55, solid="top")
    luxe.vfade(dl, x, y + h - 14, x + w, y + h - 2, C["gold"], 40,
               solid="bottom")
    dpg.draw_rectangle((x, y + h - 2), (x + w, y + h),
                       fill=C["gold"], color=(0, 0, 0, 0), parent=dl)

    # Avatar circle (initials inside) — keeps the panel light even without textures
    av_r = 36
    av_cx = x + PAD + av_r
    av_cy = y + h // 2
    initials = "".join(part[0] for part in name.split()[:2]).upper() or "?"
    # Tier-tinted ring
    rk = _player_rankings_row(name) or {}
    tier = rk.get("tier") or "Unranked"
    tcol = RANK_COLORS.get(tier, RANK_COLORS["Unranked"])
    luxe.glow(dl, av_cx, av_cy, av_r * 1.7, tcol, 44)
    dpg.draw_circle((av_cx, av_cy), av_r + 4,
                    fill=(0, 0, 0, 0), color=(*tcol[:3], 230),
                    thickness=2, parent=dl)
    dpg.draw_circle((av_cx, av_cy), av_r,
                    fill=(*C["panel"][:3], 240), color=(0, 0, 0, 0),
                    parent=dl)
    iw = len(initials) * 12
    dpg.draw_text((av_cx - iw // 2, av_cy - 13), initials,
                  color=C["gold_lt"], size=22, parent=dl)

    # Name + role line
    nx = av_cx + av_r + 18
    dpg.draw_text((nx, y + 26), clamp_text(name, 26),
                  color=C["gold_lt"], size=26, parent=dl)
    # Subline: rank · score · tier
    rank_pos = rk.get("rank") or rk.get("position")
    score = rk.get("score")
    parts = []
    if rank_pos:
        parts.append(f"#{rank_pos}")
    if tier:
        parts.append(tier.upper())
    if score is not None:
        parts.append(f"{score} pts")
    sub = "  ·  ".join(parts) if parts else "UNRANKED"
    dpg.draw_text((nx, y + 60), sub,
                  color=(*C["txt2"][:3], 240), size=15, parent=dl)

    # SHARE button — left of the close X
    sh_x1 = x + w - 110
    sh_y1 = y + 12
    sh_x2 = x + w - 46
    sh_y2 = y + 36
    dpg.draw_rectangle((sh_x1, sh_y1), (sh_x2, sh_y2),
                       fill=(*C["card_hover"][:3], 220),
                       color=(*C["gold"][:3], 200),
                       rounding=4, parent=dl)
    sh_text = "SHARE"
    sw = len(sh_text) * 6
    dpg.draw_text(((sh_x1 + sh_x2) // 2 - sw // 2, sh_y1 + 6),
                  sh_text, color=C["gold_lt"], size=12, parent=dl)
    # Stash hitbox for the panel-level click dispatcher
    _profile_hits["share_rect"] = (sh_x1, sh_y1, sh_x2, sh_y2)

    # Close X (top-right)
    cx1 = x + w - 36
    cy1 = y + 12
    cx2 = x + w - 12
    cy2 = y + 36
    dpg.draw_rectangle((cx1, cy1), (cx2, cy2),
                       fill=(0, 0, 0, 0), color=(*C["rule_dark"][:3], 180),
                       rounding=4, parent=dl)
    cmid_x = (cx1 + cx2) // 2
    cmid_y = (cy1 + cy2) // 2
    dpg.draw_line((cmid_x - 6, cmid_y - 6), (cmid_x + 6, cmid_y + 6),
                  color=C["txt"], thickness=2, parent=dl)
    dpg.draw_line((cmid_x + 6, cmid_y - 6), (cmid_x - 6, cmid_y + 6),
                  color=C["txt"], thickness=2, parent=dl)

    return h


def _draw_section_title(dl, x, y, w, label, accent=None):
    a = accent or C["gold"]
    luxe.glow(dl, x + 6, y + 13, 16, a, 60)
    dpg.draw_rectangle((x, y + 11), (x + 12, y + 15),
                       fill=(*a[:3], 220), color=(0, 0, 0, 0), parent=dl)
    dpg.draw_text((x + 20, y + 4), label.upper(),
                  color=(*a[:3], 230), size=13, parent=dl)
    luxe.hfade(dl, x + 20 + max(80, len(label) * 8 + 8), y + 12,
               x + w, y + 14, a, 90, solid="left")
    return 24


def _draw_form_sparkline(dl, x, y, w, h, form):
    """Big sparkline-style W/L row, like the rankings mini ones but larger."""
    if not form:
        dpg.draw_text((x, y + (h - 14) // 2), "Not enough games yet.",
                      color=(*C["txt2"][:3], 235), size=14, parent=dl)
        return
    n = len(form)
    cell_w = (w - (n - 1) * 4) // max(1, n)
    cx = x
    for i, r in enumerate(form):
        col = C["win"] if r == 1 else C["loss"]
        dpg.draw_rectangle((cx, y), (cx + cell_w, y + h),
                           fill=(*col[:3], 220), color=(0, 0, 0, 0),
                           rounding=4, parent=dl)
        letter = "W" if r == 1 else "L"
        lw = len(letter) * 11
        dpg.draw_text((cx + (cell_w - lw) // 2, y + (h - 18) // 2),
                      letter, color=(255, 255, 255, 235),
                      size=18, parent=dl)
        cx += cell_w + 4


def _draw_tags(dl, x, y, w, tags):
    if not tags:
        dpg.draw_text((x, y + 6), "No auto-tags computed.",
                      color=(*C["txt2"][:3], 235), size=14, parent=dl)
        return 30
    cx = x
    cy = y + 4
    for label, col in tags:
        tw = len(label) * 7 + 18
        if cx + tw > x + w:
            cx = x
            cy += 28
        dpg.draw_rectangle((cx, cy), (cx + tw, cy + 22),
                           fill=(*col[:3], 40),
                           color=(*col[:3], 220),
                           rounding=11, parent=dl)
        dpg.draw_text((cx + 9, cy + 4), label,
                      color=(*col[:3], 240), size=12, parent=dl)
        cx += tw + 6
    return (cy - y) + 30


def _draw_champ_pool(dl, x, y, w, name):
    """Compact grid of the player's top champions."""
    champs = live.inhouse_champs.get(name) or live.scout_champs_for(name) or []
    if not champs:
        dpg.draw_text((x, y + 4), "No champion-pool data loaded.",
                      color=(*C["txt2"][:3], 235), size=14, parent=dl)
        return 28
    # Sort by games desc, take top 6
    champs = sorted(champs, key=lambda c: -int(c.get("games") or 0))[:6]
    cols = 3
    cell_w = (w - (cols - 1) * 10) // cols
    cell_h = 60
    rows = (len(champs) + cols - 1) // cols
    for i, c in enumerate(champs):
        r = i // cols
        col = i % cols
        cx = x + col * (cell_w + 10)
        cy = y + r * (cell_h + 8)
        dpg.draw_rectangle((cx, cy), (cx + cell_w, cy + cell_h),
                           fill=(*C["card_hover"][:3], 200),
                           color=(*C["rule_dark"][:3], 180),
                           rounding=6, parent=dl)
        # Champ name + accent stripe
        dpg.draw_rectangle((cx, cy), (cx + cell_w, cy + 3),
                           fill=(*C["gold"][:3], 200),
                           color=(0, 0, 0, 0), rounding=4, parent=dl)
        cname = str(c.get("champ") or c.get("name") or "—")
        dpg.draw_text((cx + 8, cy + 8), clamp_text(cname, max(6, cell_w // 9)),
                      color=C["txt"], size=14, parent=dl)
        # Games + WR
        games = int(c.get("games") or 0)
        wr_raw = c.get("wr")
        try:
            wr_val = float(str(wr_raw).replace("%", "")) if wr_raw is not None else None
        except (ValueError, TypeError):
            wr_val = None
        wr_col = (C["win"] if (wr_val or 0) >= 55 else
                  (C["loss"] if (wr_val or 0) > 0 and (wr_val or 0) <= 45 else
                   C["txt2"]))
        wr_txt = f"{wr_val:.0f}%" if wr_val is not None else "—"
        dpg.draw_text((cx + 8, cy + 28), f"{games} GP",
                      color=(*C["txt2"][:3], 220), size=12, parent=dl)
        dpg.draw_text((cx + 8, cy + 42), wr_txt,
                      color=(*wr_col[:3], 235), size=13, parent=dl)
        # KDA on the right
        kda = c.get("kda")
        if kda is not None:
            try:
                kda_txt = f"{float(kda):.1f}"
            except (ValueError, TypeError):
                kda_txt = str(kda)
            kw = len(kda_txt) * 9
            dpg.draw_text((cx + cell_w - kw - 8, cy + 38), kda_txt,
                          color=C["gold_lt"], size=14, parent=dl)
    return rows * (cell_h + 8)


def _draw_rivalries(dl, x, y, w, name):
    rivs = live.rivalries.get(name) or []
    if not rivs and not live.rivalries_loaded.get(name):
        # Show a single skeleton row
        effects.draw_skeleton_row(dl, x, y, w, 36)
        return 40
    if not rivs:
        dpg.draw_text((x, y + 4), "No rivalries yet — log more inhouse games.",
                      color=(*C["txt2"][:3], 235), size=14, parent=dl)
        return 28
    rivs = rivs[:4]
    row_h = 32
    for i, r in enumerate(rivs):
        ry = y + i * (row_h + 4)
        opp = r.get("opponent") or "—"
        gv  = int(r.get("games_vs") or 0)
        wv  = int(r.get("wins_vs") or 0)
        gw  = int(r.get("games_with") or 0)
        ww  = int(r.get("wins_with") or 0)
        # Opp name
        dpg.draw_text((x, ry + 7), clamp_text(opp, 18),
                      color=C["txt"], size=14, parent=dl)
        # VS record
        if gv:
            wr = wv / gv * 100.0
            vs_txt = f"vs {wv}-{gv-wv}  ({wr:.0f}%)"
            vs_col = C["win"] if wr >= 55 else \
                     (C["loss"] if wr <= 45 else C["txt2"])
        else:
            vs_txt = "vs —"
            vs_col = C["txt_dim"]
        dpg.draw_text((x + int(w * 0.40), ry + 7), vs_txt,
                      color=vs_col, size=13, parent=dl)
        # WITH record
        if gw:
            wr2 = ww / gw * 100.0
            with_txt = f"with {ww}-{gw-ww}  ({wr2:.0f}%)"
            with_col = C["win"] if wr2 >= 55 else \
                       (C["loss"] if wr2 <= 45 else C["txt2"])
        else:
            with_txt = "with —"
            with_col = C["txt_dim"]
        dpg.draw_text((x + int(w * 0.68), ry + 7), with_txt,
                      color=with_col, size=13, parent=dl)
    return len(rivs) * (row_h + 4)


def _draw_records_held(dl, x, y, w, name):
    held = _records_held(name)
    if not held:
        dpg.draw_text((x, y + 4),
                      "No league records currently held.",
                      color=(*C["txt2"][:3], 235), size=14, parent=dl)
        return 28
    cx = x
    cy = y
    line_h = 22
    for key, rec in held[:6]:
        title = key.replace("_", " ").upper()
        chip_w = max(120, len(title) * 7 + 20)
        if cx + chip_w > x + w:
            cx = x
            cy += line_h + 6
        dpg.draw_rectangle((cx, cy), (cx + chip_w, cy + line_h),
                           fill=(*C["gold_dk"][:3], 160),
                           color=(*C["gold"][:3], 200),
                           rounding=6, parent=dl)
        dpg.draw_text((cx + 8, cy + 3), title,
                      color=C["gold_lt"], size=13, parent=dl)
        cx += chip_w + 6
    return (cy - y) + line_h + 4


def _draw_achievements(dl, x, y, w, name):
    rows = live.achievements.get(name)
    if rows is None:
        # not loaded yet
        effects.draw_skeleton_text(dl, x, y + 4, w - 20, lines=2, line_h=14, gap=10)
        return 40

    unlocked_codes = {r.get("code") for r in (rows or [])}
    catalog = list(live.achievement_catalog) if hasattr(live, "achievement_catalog") \
              and live.achievement_catalog else []
    if not catalog:
        # Just render unlocked, catalog will populate on a later frame
        catalog = [{"code": r.get("code"), "label": r.get("label") or r.get("code"),
                    "description": r.get("description", "")} for r in (rows or [])]

    if not catalog:
        dpg.draw_text((x, y + 4),
                      "No achievements catalog loaded.",
                      color=(*C["txt2"][:3], 235), size=14, parent=dl)
        return 28

    cx = x
    cy = y
    line_h = 30
    chip_h = 26
    # Show unlocked first, then locked (faded)
    ordered = sorted(catalog, key=lambda a: 0 if a.get("code") in unlocked_codes else 1)
    for a in ordered[:24]:
        code = a.get("code")
        label = (a.get("label") or code or "—").upper()
        is_unlocked = code in unlocked_codes
        chip_w = max(110, len(label) * 7 + 22)
        if cx + chip_w > x + w:
            cx = x
            cy += line_h
        if is_unlocked:
            dpg.draw_rectangle((cx, cy), (cx + chip_w, cy + chip_h),
                               fill=(*C["gold_dk"][:3], 180),
                               color=(*C["gold"][:3], 220),
                               rounding=13, parent=dl)
            dpg.draw_text((cx + 8, cy + 5), "*",
                          color=C["gold_lt"], size=15, parent=dl)
            dpg.draw_text((cx + 22, cy + 6), label,
                          color=C["gold_lt"], size=12, parent=dl)
        else:
            dpg.draw_rectangle((cx, cy), (cx + chip_w, cy + chip_h),
                               fill=(*C["card_hover"][:3], 120),
                               color=(*C["rule_dark"][:3], 200),
                               rounding=13, parent=dl)
            dpg.draw_text((cx + 8, cy + 5), "·",
                          color=(*C["txt_dim"][:3], 200), size=15, parent=dl)
            dpg.draw_text((cx + 22, cy + 6), label,
                          color=(*C["txt_dim"][:3], 200), size=12, parent=dl)
        cx += chip_w + 8
    return (cy - y) + line_h


def _draw_recent_matches_strip(dl, x, y, w, name):
    matches = _player_matches(name, limit=5)
    if not matches:
        dpg.draw_text((x, y + 4),
                      "No matches found in the local cache.",
                      color=(*C["txt2"][:3], 235), size=14, parent=dl)
        return 28
    row_h = 30
    for i, (m, pt) in enumerate(matches):
        ry = y + i * (row_h + 4)
        # Use the participant's own win column if present — authoritative.
        if "win" in pt and pt["win"] is not None:
            won = bool(pt["win"])
        else:
            winner = (m.get("winner") or "").lower()
            side = (pt.get("team") or "").lower()
            won = bool(side and winner and side == winner)
        col = C["win"] if won else C["loss"]
        # Outcome chip
        dpg.draw_rectangle((x, ry), (x + 38, ry + row_h),
                           fill=(*col[:3], 60), color=(*col[:3], 200),
                           rounding=6, parent=dl)
        dpg.draw_text((x + 10, ry + (row_h - 18) // 2),
                      "WIN" if won else "LOSS",
                      color=(*col[:3], 240), size=12, parent=dl)
        # Champion played
        champ = str(pt.get("champion") or "—")
        dpg.draw_text((x + 50, ry + (row_h - 16) // 2),
                      clamp_text(champ, 14),
                      color=C["txt"], size=14, parent=dl)
        # KDA
        k = int(pt.get("kills") or 0)
        d = int(pt.get("deaths") or 0)
        a = int(pt.get("assists") or 0)
        kda_txt = f"{k}/{d}/{a}"
        kw = len(kda_txt) * 8
        dpg.draw_text((x + int(w * 0.55), ry + (row_h - 16) // 2),
                      kda_txt, color=(*C["txt2"][:3], 230),
                      size=13, parent=dl)
        # Duration
        dur = m.get("duration") or 0
        if dur:
            mm = int(dur) // 60
            ss = int(dur) % 60
            dur_txt = f"{mm}:{ss:02d}"
            dw = len(dur_txt) * 8
            dpg.draw_text((x + w - dw - 6, ry + (row_h - 16) // 2),
                          dur_txt, color=(*C["txt_dim"][:3], 200),
                          size=12, parent=dl)
    return len(matches) * (row_h + 4)


# ---------------------------------------------------------------------------
# Public entrypoints
# ---------------------------------------------------------------------------

def open_profile(name: str):
    """Public helper for any tab to open a player profile."""
    profile.open(name)


def _do_share(name: str):
    """Spawn a worker that renders the share card and toasts the user."""
    import threading
    from ui import toast
    def _bg():
        try:
            from data import share_cards
            path = share_cards.make_player_card(name)
            if not path:
                toast.push("Could not generate share card", kind="warn")
                return
            copied = share_cards.copy_path_to_clipboard(path)
            msg = f"Saved share card · {os.path.basename(path)}"
            if copied:
                msg += "  (path copied to clipboard)"
            toast.push(msg, kind="success", duration=7.0)
        except Exception as e:
            toast.push(f"Share card error: {e}", kind="error")
    threading.Thread(target=_bg, daemon=True, name="share_player").start()


def is_open():
    return profile.name is not None and profile.frac > 0.02


def close():
    """Module-level helper so callers can do `from ui import profile;
    profile.close()` without reaching into the singleton."""
    profile.close()


def handle_hotkeys():
    """Call from main.py: closes the panel on Escape and consumes the press
    so the active tab doesn't also see it. Returns True if it consumed Esc."""
    if not is_open():
        return False
    if dpg.is_key_down(dpg.mvKey_Escape):
        profile.close()
        return True
    return False


def draw(dl, content_w, content_h):
    """Render the floating panel on top of the current tab. Drives navigation
    via state.nav_to_profile so any tab can request an open by writing it."""
    # Pick up navigation requests (set by any tab).
    target = getattr(state, "nav_to_profile", None)
    if target:
        state.nav_to_profile = None
        profile.open(target)

    if profile.frac <= 0.01 or profile.name is None:
        return

    name = profile.name
    frac = profile.frac

    # Slide-in panel from the right of the content area
    panel_w = min(PANEL_W, max(360, content_w - 40))
    panel_h = content_h
    px_off  = int(panel_w * (1.0 - frac))
    x1 = content_w - panel_w + px_off
    y1 = 0
    x2 = content_w + px_off
    y2 = panel_h

    # Dim backdrop (clickable to close)
    if frac > 0.05:
        dim_a = int(120 * frac)
        dpg.draw_rectangle((0, 0), (content_w, content_h),
                           fill=(0, 0, 0, dim_a), color=(0, 0, 0, 0),
                           parent=dl)

    # Click-anywhere-on-backdrop closes the panel. Consumes the click
    # via state.click_consumed so the underlying tab doesn't also fire on
    # the same press.
    if dpg.is_mouse_button_clicked(0) and not state.click_consumed:
        try:
            cw_pos = dpg.get_item_pos("content_win")
        except Exception:
            cw_pos = (0, 0)
        mouse = dpg.get_mouse_pos(local=False)
        vp = dpg.get_viewport_pos()
        mx = mouse[0] - vp[0] - cw_pos[0]
        my = mouse[1] - vp[1] - cw_pos[1]
        # Check share button first (it's inside the panel, so check before close).
        share_rect = _profile_hits.get("share_rect")
        if share_rect:
            sx1, sy1, sx2, sy2 = share_rect
            if sx1 <= mx <= sx2 and sy1 <= my <= sy2:
                state.click_consumed = True
                _do_share(name)
                return
        # Close X — top-right of header
        cx1, cy1 = x2 - 36, 12
        cx2, cy2 = x2 - 12, 36
        in_close = (cx1 <= mx <= cx2 and cy1 <= my <= cy2)
        in_panel = (x1 <= mx <= x2) and (y1 <= my <= y2)
        if in_close or not in_panel:
            state.click_consumed = True
            profile.close()
            return
        # Click inside the panel but not on a known control — still consume
        # so it doesn't bleed through to the tab below.
        if in_panel:
            state.click_consumed = True

    # Panel chrome — V2: cast shadow to the left, gradient body, gold edge.
    luxe.hfade(dl, x1 - 28, y1, x1, y2, (0, 0, 0), int(130 * frac),
               solid="right")
    dpg.draw_rectangle((x1, y1), (x2, y2),
                       fill=C["panel"], color=(0, 0, 0, 0),
                       parent=dl)
    luxe.vfade(dl, x1, y1 + HEADER_H, x2, y2, (6, 12, 24),
               int(70 * frac), solid="bottom")
    dpg.draw_line((x1, y1), (x1, y2),
                  color=(*C["gold_dk"][:3], 220), thickness=1, parent=dl)

    # Header (sticky — does not scroll)
    _draw_header(dl, x1, y1, panel_w, name)

    # Scroll body
    body_x = x1
    body_y = y1 + HEADER_H
    body_w = panel_w
    body_h = panel_h - HEADER_H

    # Handle wheel scrolling when mouse is over the panel
    try:
        cw_pos = dpg.get_item_pos("content_win")
    except Exception:
        cw_pos = (0, 0)
    mouse = dpg.get_mouse_pos(local=False)
    vp = dpg.get_viewport_pos()
    mx = mouse[0] - vp[0] - cw_pos[0]
    my = mouse[1] - vp[1] - cw_pos[1]
    over_panel = (x1 <= mx <= x2) and (body_y <= my <= y2)
    if over_panel:
        try:
            from ui.tierlist import _wheel_delta as _wd
            d = _wd[0]
            _wd[0] = 0
            if d:
                profile.scroll = max(0, min(profile.scroll_max,
                                             profile.scroll - int(d) * SCROLL_STEP))
        except Exception:
            pass

    # Body drawing — vertical layout with sections
    cur_x = body_x + PAD
    cur_y = body_y + PAD - profile.scroll
    inner_w = body_w - PAD * 2

    # 1) FORM
    cur_y += _draw_section_title(dl, cur_x, cur_y, inner_w, "RECENT FORM (LAST 10)")
    _draw_form_sparkline(dl, cur_x, cur_y, inner_w, 40, _form_sparkline(name, 10))
    cur_y += 48 + SECTION_GAP

    # 2) AUTO TAGS
    cur_y += _draw_section_title(dl, cur_x, cur_y, inner_w, "AUTO TAGS")
    cur_y += _draw_tags(dl, cur_x, cur_y, inner_w, _player_tags(name))
    cur_y += SECTION_GAP - 8

    # 3) CHAMPION POOL
    cur_y += _draw_section_title(dl, cur_x, cur_y, inner_w, "CHAMPION POOL")
    cur_y += _draw_champ_pool(dl, cur_x, cur_y, inner_w, name)
    cur_y += SECTION_GAP

    # 4) RIVALRIES
    cur_y += _draw_section_title(dl, cur_x, cur_y, inner_w, "RIVALRIES")
    cur_y += _draw_rivalries(dl, cur_x, cur_y, inner_w, name)
    cur_y += SECTION_GAP

    # 5) RECORDS HELD
    cur_y += _draw_section_title(dl, cur_x, cur_y, inner_w, "RECORDS HELD")
    cur_y += _draw_records_held(dl, cur_x, cur_y, inner_w, name)
    cur_y += SECTION_GAP

    # 6) ACHIEVEMENTS
    cur_y += _draw_section_title(dl, cur_x, cur_y, inner_w, "ACHIEVEMENTS")
    cur_y += _draw_achievements(dl, cur_x, cur_y, inner_w, name)
    cur_y += SECTION_GAP

    # 7) RECENT MATCHES
    cur_y += _draw_section_title(dl, cur_x, cur_y, inner_w, "RECENT MATCHES")
    cur_y += _draw_recent_matches_strip(dl, cur_x, cur_y, inner_w, name)
    cur_y += PAD

    # Update scroll max — used to clamp wheel scrolls next frame
    total = (cur_y + profile.scroll) - (body_y + PAD)
    profile.scroll_max = max(0, total - body_h)
