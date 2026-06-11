"""
Home / Dashboard Tab — Phase 4a (polish rewrite).

Info-dense broadcast-style dashboard. Layout:

    HERO BAR (96px)           title · date · 3 KPI chips on the right
    MAIN ROW (~62% height)
        LEFT  60%  POWER RANKINGS (top 10 in a compact table)
        RIGHT 40%  SEASON · LEAGUE PULSE · SEE WRAPPED stacked
    BOTTOM ROW (~31% height)
        LEFT  60%  RECENT MATCHES (5 matches)
        RIGHT 40%  RECORD BOOK (5 records)
    FOOTER (44px)             data status + F1-shortcuts hint

Cards are sized to their content (no comically empty boxes). All data is read
from `live.*` caches populated by background loaders; if a card is mid-load it
shows a skeleton, if it has no data it shows a designed empty state.
"""
from __future__ import annotations

import time
import math
from datetime import datetime, timezone

import dearpygui.dearpygui as dpg

from theme import C, RANK_COLORS, MEDAL_PARTICLE
from core.state import state
from core.animations import anim
from ui import effects
from ui import luxe
from ui.fmt import commas, compact, clamp_text
from data.reader import (
    live,
    load_records,
    load_match_history,
    load_tier_meta,
    load_seasons,
    load_season_standings,
    load_prediction_leaderboard,
)
from data import rift_api
from data import splash_art


# ---------------------------------------------------------------------------
# Design tokens — tightened scale so cards stay dense rather than blowing up.
# Everything snaps to an 8 px grid.
# ---------------------------------------------------------------------------
PAD_OUTER   = 24
GAP         = 16
PAD_CARD    = 18           # internal card padding
RADIUS      = 8

HERO_H      = 96
FOOTER_H    = 44

# Type scale (px). Snap to one of these — don't sprinkle one-off sizes.
# Bumped one notch across the board after the user flagged the home page as
# undersized: the body baseline was 14 (Tailwind `text-sm`) which reads small
# on a borderless 1080p+ window; 16 is a much better default.
SZ_KPI      = 30           # KPI numbers in the hero bar
SZ_TITLE    = 26           # card body hero numbers (record values, season MC)
SZ_NAME_HI  = 18           # top-3 player names + main body text
SZ_BODY     = 16           # default body text
SZ_LABEL    = 13           # uppercase labels / chip text
SZ_CAPTION  = 12           # secondary metadata


# ---------------------------------------------------------------------------
# Click hitbox registries — rebuilt every frame, consumed at end of draw_home.
# ---------------------------------------------------------------------------
_player_hits = []     # [(x1, y1, x2, y2, player_name)]
_match_hits  = []     # [(x1, y1, x2, y2, match_id)]
_wrapped_hit = None   # (x1, y1, x2, y2)


# ---------------------------------------------------------------------------
# Lazy-load gates — flip True the first time each section paints.
# ---------------------------------------------------------------------------
_loaded   = {"history": False, "records": False, "tier": False,
             "seasons": False, "pred_lb": False}
_stats_cache = {"ts": 0.0, "data": None, "inflight": False}


def _ensure(flag, predicate, kick):
    if _loaded[flag] or predicate():
        return
    _loaded[flag] = True
    kick()


def _ensure_all():
    _ensure("history",  lambda: live.match_history_loaded, load_match_history)
    _ensure("records",  lambda: live.records_loaded,       load_records)
    _ensure("tier",     lambda: live.tier_meta_loaded,     load_tier_meta)
    _ensure("seasons",  lambda: live.seasons_loaded,       load_seasons)
    _ensure("pred_lb",  lambda: live.pred_leaderboard_loaded,
            load_prediction_leaderboard)
    # Stats (cheap one-shot every 2 minutes).
    now = time.monotonic()
    if not _stats_cache["inflight"] and (
            _stats_cache["data"] is None or (now - _stats_cache["ts"]) > 120):
        _stats_cache["inflight"] = True

        def _w():
            try:
                _stats_cache["data"] = rift_api.get_stats()
                _stats_cache["ts"]   = time.monotonic()
            finally:
                _stats_cache["inflight"] = False
        import threading
        threading.Thread(target=_w, daemon=True).start()


def _invalidate():
    """Reset all gates so the next paint re-pulls — used after backfill."""
    for k in _loaded:
        _loaded[k] = False
    _stats_cache["data"] = None
    _stats_cache["ts"] = 0.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _time_ago(ts):
    if ts is None:
        return "—"
    try:
        if isinstance(ts, (int, float)):
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        else:
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        now = datetime.now(timezone.utc) if dt.tzinfo else datetime.now()
        secs = int((now - dt).total_seconds())
        if secs < 60:      return "just now"
        if secs < 3600:    return f"{secs // 60}m ago"
        if secs < 86400:   return f"{secs // 3600}h ago"
        if secs < 604800:  return f"{secs // 86400}d ago"
        try:
            return dt.astimezone().strftime("%b %d")
        except Exception:
            return dt.strftime("%b %d")
    except Exception:
        return str(ts)


def _date_short(ts):
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return dt.strftime("%b %d")
    except Exception:
        return "—"


def _tier_color(tier):
    return RANK_COLORS.get(tier, RANK_COLORS["Unranked"])


def _draw_card(dl, x, y, w, h, hov_key=None, accent=None):
    """V2 card: soft drop shadow + gradient panel + gold border + top sheen
    + 3px accent stripe with a fading wash. Returns hover_amt."""
    is_hov = False
    amt = 0.0
    if hov_key:
        try:
            cw_pos = dpg.get_item_pos("content_win") or (68, 52)
            m  = dpg.get_mouse_pos(local=False) or (0, 0)
            vp = dpg.get_viewport_pos() or (0, 0)
            mx = m[0] - vp[0] - cw_pos[0]
            my = m[1] - vp[1] - cw_pos[1]
            is_hov = (x <= mx <= x + w) and (y <= my <= y + h)
            amt = effects.hover_amt(hov_key, is_hov)
        except Exception:
            pass

    luxe.shadow(dl, x, y, x + w, y + h, alpha=95, spread=16, drop=7)
    luxe.panel(dl, x, y, x + w, y + h,
               C["card_hover"] if is_hov else C["card"],
               corner=RADIUS,
               border=C["gold_dk"], border_a=130 + int(amt * 70),
               sheen=58)
    if accent:
        dpg.draw_rectangle((x, y), (x + w, y + 3),
                           fill=(*accent[:3], 220),
                           color=(0, 0, 0, 0),
                           rounding=RADIUS, parent=dl)
        luxe.vfade(dl, x + 2, y + 3, x + w - 2, y + 18, accent, 36,
                   solid="top")
    if hov_key and amt > 0.05:
        effects.draw_hover_glow(dl, x, y, x + w, y + h,
                                 accent or C["gold"], amt,
                                 rounding=RADIUS)
    return amt


def _section_title(dl, x, y, w, label, accent=None, count=None):
    """Section heading: short colored dash + uppercase label + thin rule + count.
    Returns the y-offset where body content should start (relative to passed y)."""
    a = accent or C["gold"]
    title_sz = SZ_LABEL + 4   # ~17 — reads as a real heading, not a chip caption
    # Accent block — lit from behind so headers carry a focal glow
    luxe.glow(dl, x + 8, y + 9, 22, a, 80)
    dpg.draw_rectangle((x, y + 6), (x + 16, y + 12),
                       fill=(*a[:3], 240), color=(0, 0, 0, 0), parent=dl)
    dpg.draw_text((x + 24, y), label.upper(),
                  color=(*a[:3], 250), size=title_sz, parent=dl)
    label_px = 24 + len(label) * (title_sz * 4 // 10) + 14
    # Optional count chip on the right
    right_px = x + w
    if count is not None:
        ct = str(count)
        cw = len(ct) * 9 + 14
        cx_ = right_px - cw
        dpg.draw_rectangle((cx_, y + 1), (right_px, y + 20),
                           fill=(*C["card_hover"][:3], 230),
                           color=(*a[:3], 200),
                           rounding=10, parent=dl)
        dpg.draw_text((cx_ + 7, y + 3), ct,
                      color=(*a[:3], 240), size=SZ_LABEL + 1, parent=dl)
        right_px = cx_ - 8
    # Gradient rule fills the middle, fading toward the right
    rule_x = x + label_px
    if rule_x < right_px - 4:
        luxe.hfade(dl, rule_x, y + 9, right_px - 4, y + 11,
                   a, 110, solid="left")
    return 26  # body starts ~26 px below the heading top (was 22)


def _draw_mini_sparkline(dl, x, y, w, h, results):
    """Compact W/L sparkline. `results` is a list of 1/0 (newest last)."""
    if not results:
        dpg.draw_text((x, y + h // 2 - 6), "—",
                      color=(*C["txt_dim"][:3], 180),
                      size=SZ_CAPTION, parent=dl)
        return
    n = len(results)
    cell_w = max(4, (w - (n - 1) * 2) // max(1, n))
    cx = x
    for r in results:
        col = C["win"] if r == 1 else C["loss"]
        dpg.draw_rectangle((cx, y), (cx + cell_w, y + h),
                           fill=(*col[:3], 220),
                           color=(0, 0, 0, 0),
                           rounding=2, parent=dl)
        cx += cell_w + 2


# ---------------------------------------------------------------------------
# HERO BAR
# ---------------------------------------------------------------------------

_hero_bg = {"key": None, "champ": None}

# Iconic, splash-safe picks so the hero is cinematic from first launch even
# before any match history exists. Rotates daily.
_HERO_FALLBACK = ["Ahri", "Jinx", "Yasuo", "Ezreal", "Akali",
                  "Jhin", "Sett", "Thresh", "Yone", "Caitlyn"]


def _hero_champion():
    """Champion whose splash backs the hero — drawn from the most recent
    logged match (winning side first), rotating through that game's champs
    day by day. Falls back to a curated icon list until history loads."""
    day = int(datetime.now().strftime("%j"))
    hist = live.match_history or []
    if not hist:
        return _HERO_FALLBACK[day % len(_HERO_FALLBACK)]
    m = hist[0]
    key = (m.get("match_id") or m.get("id") or 0,
           datetime.now().strftime("%Y%m%d"))
    if _hero_bg["key"] == key:
        return _hero_bg["champ"]
    parts  = m.get("participants") or []
    winner = (m.get("winner") or "").lower()
    champs  = [(pt.get("champion") or "").strip() for pt in parts
               if (pt.get("team") or "").lower() == winner]
    champs += [(pt.get("champion") or "").strip() for pt in parts
               if (pt.get("team") or "").lower() != winner]
    champs = [c for c in champs if c and c != "?"]
    pick = champs[day % len(champs)] if champs else \
        _HERO_FALLBACK[day % len(_HERO_FALLBACK)]
    _hero_bg["key"]   = key
    _hero_bg["champ"] = pick
    return pick


def _draw_hero(dl, x, y, w, h):
    """V2 cinematic hero — full-bleed champion splash with layered scrims,
    a lit gold wordmark, and glass KPI chips. The anchor of the front page."""
    t = time.monotonic()

    # ── Cursor state — drives parallax + the hero light glint ─────────────
    drift = max(0.0, min(1.0, anim.intensity))
    try:
        _m  = dpg.get_mouse_pos(local=False)
        _vp = dpg.get_viewport_pos()
        mxc = _m[0] - _vp[0] - 68
        myc = _m[1] - _vp[1] - 52
    except Exception:
        mxc, myc = x + w / 2, y + h / 2
    nx = max(-0.5, min(0.5, (mxc - x) / max(1.0, float(w)) - 0.5))
    ny = max(-0.5, min(0.5, (myc - y) / max(1.0, float(h)) - 0.5))
    par_x = anim.smooth("hero_par_x", nx * drift, rate=0.06)
    par_y = anim.smooth("hero_par_y", ny * drift, rate=0.06)

    # ── Backdrop: cover-cropped splash, slow drift + mouse parallax ───────
    champ = _hero_champion()
    tex = splash_art.get_texture(champ) if champ else None
    dpg.draw_rectangle((x, y), (x + w, y + h),
                       fill=C["navy_deep"], color=(0, 0, 0, 0), parent=dl)
    if tex and dpg.does_item_exist(tex):
        SPLASH_AR = 1215.0 / 717.0
        aspect = max(1.0, w / max(1.0, float(h)))
        uw = 1.0 - 0.06 * (0.5 + 0.5 * math.sin(t * 2 * math.pi / 53.0)) * drift
        vh = min(1.0, uw * SPLASH_AR / aspect)
        u0 = (1.0 - uw) * (0.5 + 0.5 * math.sin(t * 2 * math.pi / 67.0) * drift)
        v0 = 0.06 + 0.06 * drift * (0.5 + 0.5 * math.sin(t * 2 * math.pi / 59.0))
        u0 = max(0.0, min(1.0 - uw, u0 + par_x * 0.020))
        v0 = max(0.0, min(1.0 - vh, v0 + par_y * 0.014))
        dpg.draw_image(tex, (x, y), (x + w, y + h),
                       uv_min=(u0, v0), uv_max=(u0 + uw, v0 + vh),
                       parent=dl)
    else:
        # Fallback bed — gradient navy with a warm focal glow, never flat.
        luxe.vfade(dl, x, y, x + w, y + h, (26, 52, 92), 255, solid="top")
        luxe.glow(dl, x + int(w * 0.24), y + int(h * 0.62),
                  int(h * 1.25), C["gold"], 34)
        luxe.glow(dl, x + int(w * 0.86), y + int(h * 0.30),
                  int(h * 0.95), C["rift_purple"], 30)

    # ── Hero light glint — a soft lamp follows the cursor over the art ────
    if drift > 0.01 and x <= mxc <= x + w and y <= myc <= y + h:
        luxe.glow(dl, mxc, myc, h * 0.85, (205, 195, 165), int(16 * drift))

    # ── Scrims — bottom-heavy navy so type sits in clean air ──────────────
    luxe.vfade(dl, x, y + int(h * 0.40), x + w, y + h, C["bg"], 235,
               solid="bottom")
    luxe.hfade(dl, x, y, x + int(w * 0.46), y + h, C["bg"], 185,
               solid="left")
    luxe.vfade(dl, x, y, x + w, y + int(h * 0.30), C["bg"], 110,
               solid="top")

    # Embers drifting up through the hero art.
    luxe.draw_embers(dl, x, y + int(h * 0.25), w, int(h * 0.75),
                     n=16, seed=31, alpha=120)

    # ── Wordmark block (lower-left) — counter-drifts against the parallax ─
    today = datetime.now().strftime("%A · %B %d").upper()
    title_px = max(38, min(72, int(h * 0.24)))
    _, tw_, th_ = luxe.lit_title("THE RIFT", title_px)
    ty = y + h - th_ - 34
    tx_ = x + 26 - int(par_x * 30)
    ty_off = -int(par_y * 10)
    dpg.draw_text((tx_ + 4, ty - 20 + ty_off), today,
                  color=(*C["gold"][:3], 215), size=SZ_LABEL, parent=dl)
    luxe.glow(dl, tx_ + tw_ / 2, ty + th_ / 2 + ty_off, tw_ * 0.66,
              (212, 178, 118),
              int(effects.breathing_alpha(40, period=5.0, amp=0.5)))
    # Static lit title here — the per-px sweep frames are too heavy to bake
    # lazily at hero size; the breathing glow + parallax keep it alive.
    luxe.draw_lit_title(dl, tx_, ty + ty_off, "THE RIFT", title_px)

    stats = _stats_cache["data"] or {}
    matches = stats.get("matches") if isinstance(stats, dict) else None
    parts   = stats.get("participants") if isinstance(stats, dict) else None
    last    = stats.get("last_ingest") if isinstance(stats, dict) else None
    sub = "CUSTOMS HQ — EVERY GAME, EVERY RECORD, EVERY RIVALRY"
    dpg.draw_text((x + 30, ty + th_ + 2), sub,
                  color=(*C["txt2"][:3], 225), size=SZ_LABEL, parent=dl)

    # ── KPI glass chips (lower-right) ──────────────────────────────────────
    kpis = [
        ("MATCHES",      commas(matches if matches is not None else 0)),
        ("PARTICIPANTS", commas(parts if parts is not None else 0)),
        ("LAST GAME",    _time_ago(last) if last else "—"),
    ]
    chip_w, chip_h, chip_gap = 168, 66, 14
    total_w = len(kpis) * chip_w + (len(kpis) - 1) * chip_gap
    cx = x + w - 26 - total_w
    cy = y + h - chip_h - 26
    for label, val in kpis:
        luxe.shadow(dl, cx, cy, cx + chip_w, cy + chip_h,
                    alpha=80, spread=12, drop=5)
        luxe.panel(dl, cx, cy, cx + chip_w, cy + chip_h,
                   (12, 26, 48, 228), corner=8,
                   border=C["gold_dk"], border_a=170, sheen=70)
        vw = len(val) * (SZ_KPI * 4 // 10)
        luxe.glow(dl, cx + chip_w / 2, cy + 24, 34, C["gold"], 36)
        dpg.draw_text((cx + (chip_w - vw) // 2, cy + 8),
                      val, color=C["gold_lt"], size=SZ_KPI, parent=dl)
        lw = len(label) * (SZ_LABEL * 4 // 10)
        dpg.draw_text((cx + (chip_w - lw) // 2, cy + chip_h - 20),
                      label, color=(*C["txt2"][:3], 220),
                      size=SZ_LABEL, parent=dl)
        cx += chip_w + chip_gap

    # Live pulse dot above the chips
    fresh = bool(last)
    dot_col = C["win"] if fresh else C["txt_dim"]
    pulse = (math.sin(t * 2.4) * 0.5 + 0.5)
    dot_x = x + w - 26 - total_w - 18
    dot_y = cy + chip_h // 2
    luxe.glow(dl, dot_x, dot_y, 14, dot_col, int(60 + pulse * 60))
    dpg.draw_circle((dot_x, dot_y), 4,
                    fill=(*dot_col[:3], int(190 + pulse * 65)),
                    color=(0, 0, 0, 0), parent=dl)

    # ── Bottom edge light — flowing energy line under the hero ────────────
    luxe.hairline(dl, x, y + h - 1, x + w, alpha=150, glow_h=12, glow_a=45)
    luxe.flow_line(dl, x, y + h - 3, x + w, color=C["gold"], alpha=95,
                   h=3, speed=52)


# ---------------------------------------------------------------------------
# POWER RANKINGS card (top 10 with sparkline)
# ---------------------------------------------------------------------------

ROLE_SLOTS = ("TOP", "JGL", "MID", "BOT", "SUP")
_ROLE_ALIASES = {
    "TOP": "TOP",
    "JGL": "JGL", "JUNGLE": "JGL",
    "MID": "MID", "MIDDLE": "MID",
    "BOT": "BOT", "BOTTOM": "BOT", "ADC": "BOT",
    "SUP": "SUP", "SUPPORT": "SUP", "UTILITY": "SUP",
}


def _winning_team_names(m, limit=5):
    """Backwards-compat helper — returns up to `limit` raw player names from the
    winning side, in role order. Used by the Pulse 'LATEST DRAMA' card."""
    slots = _winning_team_slots(m)
    return [name for _, name in slots if name][:limit]


def _winning_team_slots(m):
    """Return 5 (role, name_or_None) tuples for the winning side, in role
    order. Slots without a logged player return name=None so the renderer
    can show a faint placeholder. Empty list when there is no winner or
    participants aren't loaded."""
    winner = (m.get("winner") or "").lower()
    if not winner:
        return []
    parts = m.get("participants") or []
    if not parts:
        return []
    by_role = {role: None for role in ROLE_SLOTS}
    unmapped = []  # fallback for slot1/slot2/... or unknown lanes
    for pt in parts:
        side = (pt.get("team") or "").lower()
        if side != winner:
            continue
        name = (pt.get("player") or pt.get("player_name")
                or pt.get("name") or pt.get("summoner"))
        if not name:
            continue
        raw_role = (pt.get("role") or pt.get("lane") or "").upper()
        canon = _ROLE_ALIASES.get(raw_role)
        if canon and by_role.get(canon) is None:
            by_role[canon] = name
        else:
            unmapped.append(name)
    # Fill any leftover slots from the unmapped pool in role order
    for role in ROLE_SLOTS:
        if by_role[role] is None and unmapped:
            by_role[role] = unmapped.pop(0)
    return [(role, by_role[role]) for role in ROLE_SLOTS]


def _participant_completeness(m):
    """Return (logged, expected) participant counts. Expected is always 10 for
    a 5v5 — anything less is incomplete due to the participants-PK collision
    bug, and we want the UI to show that gap honestly."""
    parts = m.get("participants") or []
    return len(parts), 10


def _player_recent_results(name, last_n=6):
    """Last-N W/L for `name`, newest last. Returns [] if no history yet."""
    out = []
    for m in (live.match_history or []):
        if len(out) >= last_n:
            break
        for pt in (m.get("participants") or []):
            pname = pt.get("player") or pt.get("player_name") or pt.get("name")
            if pname != name:
                continue
            if "win" in pt and pt["win"] is not None:
                out.append(1 if pt["win"] else 0)
            else:
                winner = (m.get("winner") or "").lower()
                side = (pt.get("team") or "").lower()
                out.append(1 if (side and winner and side == winner) else 0)
            break
    return list(reversed(out))


def _draw_rankings(dl, x, y, w, h):
    accent = C["gold"]
    _draw_card(dl, x, y, w, h, hov_key="rk", accent=accent)

    data = list(live.rankings or [])
    total = len(data)
    cap = "POWER RANKINGS"

    title_h = _section_title(dl, x + PAD_CARD, y + PAD_CARD,
                              w - PAD_CARD * 2, cap, accent,
                              count=total if total else None)

    if not data:
        # Designed empty state — small skeleton list
        skel_y = y + PAD_CARD + title_h + 8
        for i in range(5):
            effects.draw_skeleton_row(dl, x + PAD_CARD,
                                       skel_y + i * 44,
                                       w - PAD_CARD * 2, 36)
        return

    # Column layout (relative to inner)
    inner_x = x + PAD_CARD
    inner_y = y + PAD_CARD + title_h + 4
    inner_w = w - PAD_CARD * 2
    inner_h = h - (inner_y - y) - PAD_CARD

    # Show as many players as the card can comfortably fit. Target ~38px/row
    # minimum so names/scores stay readable; cap at the data length so empty
    # rows never appear below the leaderboard.
    target_row_h = 38
    max_rows = max(8, min(len(data), inner_h // target_row_h))
    rows = data[:max_rows]
    row_h = inner_h // len(rows)
    row_h = max(34, min(52, row_h))

    # Column x offsets
    col_rank   = 0
    col_tier   = 42
    col_name   = 58
    col_score_w = 74          # right-aligned score column width
    col_spark_w = 110         # right-aligned sparkline width
    col_spark_x = inner_w - col_spark_w
    col_score_x = col_spark_x - col_score_w - 16

    max_score = max(1.0, float(rows[0].get("score") or 1))
    for i, p in enumerate(rows):
        ry   = inner_y + i * row_h
        rank = i + 1
        name = p.get("name") or "—"
        score = float(p.get("score") or 0)
        tier  = p.get("tier") or "Unranked"
        is_top3 = rank <= 3
        medal = MEDAL_PARTICLE.get(rank)

        # Subtle alt-row banding for readability
        if i % 2 == 1:
            dpg.draw_rectangle((inner_x - 4, ry),
                               (inner_x + inner_w + 4, ry + row_h - 2),
                               fill=(*C["card_hover"][:3], 80),
                               color=(0, 0, 0, 0),
                               rounding=4, parent=dl)

        # Medal edge light for the podium ranks
        if medal:
            luxe.glow(dl, inner_x - 2, ry + row_h // 2, row_h * 0.7,
                      medal, 55)
            dpg.draw_rectangle((inner_x - 4, ry + 4),
                               (inner_x - 1, ry + row_h - 6),
                               fill=(*medal, 235), color=(0, 0, 0, 0),
                               rounding=2, parent=dl)

        # Rank number — podium ranks glow in their medal color
        rank_col = medal if medal else C["txt2"]
        rank_sz  = SZ_NAME_HI + (4 if is_top3 else 0)
        rank_txt = f"{rank}"
        rw = len(rank_txt) * 8
        if medal:
            luxe.glow(dl, inner_x + col_tier // 2,
                      ry + row_h // 2, 18, medal, 60)
        dpg.draw_text((inner_x + (col_tier - rw) // 2,
                       ry + (row_h - rank_sz) // 2),
                      rank_txt, color=(*rank_col[:3], 255),
                      size=rank_sz, parent=dl)

        # Tier bead with a soft halo
        tcol = _tier_color(tier)
        luxe.glow(dl, inner_x + col_tier + 6, ry + row_h // 2, 10,
                  tcol, 70)
        dpg.draw_circle((inner_x + col_tier + 6, ry + row_h // 2),
                        4, fill=(*tcol[:3], 240),
                        color=(0, 0, 0, 0), parent=dl)

        # Name (clickable → profile)
        nx = inner_x + col_name
        name_sz = SZ_NAME_HI + (2 if is_top3 else 0)
        name_col = C["gold_lt"] if is_top3 else C["txt"]
        name_text = clamp_text(name, 22)
        dpg.draw_text((nx, ry + (row_h - name_sz) // 2),
                      name_text, color=name_col,
                      size=name_sz, parent=dl)
        # Hitbox spans the full row so clicking anywhere on a player row opens
        # their profile. Score / sparkline are passive readouts.
        _player_hits.append((inner_x, ry, inner_x + col_score_x - 8,
                             ry + row_h - 2, name))

        # Score bar — fills the dead middle with a power readout
        bar_x1 = nx + 196
        bar_x2 = inner_x + col_score_x - 18
        if bar_x2 - bar_x1 > 50:
            bar_cy = ry + row_h // 2
            frac = max(0.04, min(1.0, score / max_score))
            dpg.draw_rectangle((bar_x1, bar_cy - 2), (bar_x2, bar_cy + 2),
                               fill=(*C["rule_dark"][:3], 90),
                               color=(0, 0, 0, 0), rounding=2, parent=dl)
            fx2 = bar_x1 + int((bar_x2 - bar_x1) * frac)
            luxe.hfade(dl, bar_x1, bar_cy - 2, fx2, bar_cy + 2,
                       C["gold"], 200 if is_top3 else 120, solid="right")
            dpg.draw_circle((fx2, bar_cy), 2.6,
                            fill=(*C["gold_lt"][:3], 230 if is_top3 else 150),
                            color=(0, 0, 0, 0), parent=dl)

        # Score (right-aligned within its column)
        s_txt = str(int(round(score)))
        sw = len(s_txt) * (SZ_NAME_HI * 4 // 10) + 4
        sz = SZ_NAME_HI + (2 if is_top3 else 0)
        sx = inner_x + col_score_x + col_score_w - sw
        dpg.draw_text((sx, ry + (row_h - sz) // 2),
                      s_txt, color=C["gold_lt"] if is_top3 else C["txt"],
                      size=sz, parent=dl)

        # Mini sparkline
        spark = _player_recent_results(name, last_n=6)
        _draw_mini_sparkline(dl, inner_x + col_spark_x, ry + 6,
                              col_spark_w, row_h - 14, spark)


# ---------------------------------------------------------------------------
# RIGHT-COLUMN cards: Season, Pulse, Wrapped CTA
# ---------------------------------------------------------------------------

def _active_season():
    seasons = live.seasons or []
    for s in reversed(seasons):
        if s.get("is_active"):
            return s
    return seasons[-1] if seasons else None


def _draw_season(dl, x, y, w, h):
    global _wrapped_hit
    accent = (110, 200, 140, 255)   # win-green
    _draw_card(dl, x, y, w, h, hov_key="sea", accent=accent)
    title_h = _section_title(dl, x + PAD_CARD, y + PAD_CARD,
                              w - PAD_CARD * 2, "SEASON", accent)

    season = _active_season()
    inner_x = x + PAD_CARD
    inner_y = y + PAD_CARD + title_h + 6
    inner_w = w - PAD_CARD * 2

    if not season:
        if not live.seasons_loaded and not live.seasons_error:
            effects.draw_skeleton_text(dl, inner_x, inner_y,
                                        inner_w, lines=2,
                                        line_h=14, gap=8)
        else:
            dpg.draw_text((inner_x, inner_y), "No active season.",
                          color=(*C["txt_dim"][:3], 220),
                          size=SZ_BODY, parent=dl)
        return

    name = (season.get("name") or "—").upper()
    dpg.draw_text((inner_x, inner_y), name,
                  color=C["gold_lt"], size=22, parent=dl)

    # Dates
    start = season.get("start_at") or ""
    try:
        start_str = datetime.fromisoformat(start.replace("Z", "+00:00")).strftime("%b %d %Y")
    except Exception:
        start_str = start[:10] or "—"
    end_str = "ongoing" if not season.get("end_at") else season.get("end_at", "")[:10]
    dpg.draw_text((inner_x, inner_y + 28),
                  f"{start_str}  →  {end_str}",
                  color=(*C["txt2"][:3], 235),
                  size=SZ_CAPTION + 1, parent=dl)

    # Match count big number on the right
    mc = int(season.get("match_count") or 0)
    live_mc = int(round(effects.count_up(
        f"home_mc:{season.get('id')}", mc, rate=0.20)))
    mc_txt = commas(live_mc)
    mcw = len(mc_txt) * (SZ_TITLE * 4 // 10) + 6
    mc_x = x + w - PAD_CARD - mcw
    dpg.draw_text((mc_x, inner_y - 2), mc_txt,
                  color=C["gold_lt"], size=SZ_TITLE, parent=dl)
    label = "MATCHES"
    lw = len(label) * (SZ_CAPTION * 4 // 10)
    dpg.draw_text((mc_x + (mcw - lw) // 2, inner_y + 22),
                  label, color=(*accent[:3], 230),
                  size=SZ_CAPTION, parent=dl)

    # Leader line (if standings available)
    sid = season.get("id")
    if sid:
        if sid not in live.season_standings and sid not in live._standings_inflight:
            load_season_standings(sid)
        sd = (live.season_standings.get(sid) or {}).get("standings") or []
        if sd:
            ldr = sd[0]
            ldr_txt = (f"LEADER  {ldr.get('player', '—')}  · "
                       f"  {ldr.get('wins', 0)}-{ldr.get('losses', 0)}"
                       f"  ·  {ldr.get('wr', 0):.0f}%")
            dpg.draw_text((inner_x, inner_y + 56),
                          ldr_txt,
                          color=(*accent[:3], 245),
                          size=SZ_BODY, parent=dl)

    # SEE WRAPPED chip at the bottom-right of the card — breathing border so
    # idle eyes are gently pulled toward it.
    chip_label = "SEE WRAPPED  >>"
    cw = len(chip_label) * 8 + 22
    chx = x + w - PAD_CARD - cw
    chy = y + h - PAD_CARD - 26
    chip_bdr_a = effects.breathing_alpha(235, period=2.6, amp=0.45)
    dpg.draw_rectangle((chx, chy), (chx + cw, chy + 26),
                       fill=(*C["gold_dk"][:3], 220),
                       color=(*C["gold"][:3], chip_bdr_a),
                       rounding=13, thickness=2, parent=dl)
    dpg.draw_text((chx + 12, chy + 5),
                  chip_label, color=C["gold_lt"],
                  size=SZ_LABEL, parent=dl)
    _wrapped_hit = (chx, chy, chx + cw, chy + 26)


# ---------------------------------------------------------------------------
# League Pulse — broadcast-style rotating cards (rewritten 2026-05-23).
#
# Each card is a dict with the same shape so the renderer can stay simple:
#   {
#     'label':   "ON FIRE",            # chip text, uppercase
#     'accent':  (r, g, b, a),         # chip + accent color
#     'headline':"xdCrunchymunches  ·  9-game win streak",
#     'detail':  "5-0 on Shen  ·  3-0 on Yone  ·  vs 3 different opponents",
#     'context': "longest active streak this season",   # caption, optional
#     'visual':  ('streak_bar', 9),    # tuple or None; renderer dispatches on tag
#   }
#
# Card builders return a dict or None (when their data isn't ready). The pool
# is rebuilt cheaply every render — the heavy O(n) compute is memoized in
# `_pulse_cache` and refreshed only when the underlying match history changes.
# ---------------------------------------------------------------------------

# Accents shared across card types
_AC_AMBER  = (220, 165,  70, 255)
_AC_GOLD   = (200, 170, 110, 255)
_AC_RED    = (220, 100, 110, 255)
_AC_BLUE   = (118, 168, 220, 255)
_AC_VIOLET = (175, 110, 220, 255)
_AC_WIN    = (110, 190, 140, 255)
_AC_TEAL   = (110, 200, 200, 255)


_pulse_cache = {"sig": None, "items": None}


def _match_history_signature():
    """Cheap fingerprint to bust the pulse cache when matches change.
    Includes the first match's participant count so cards rebuild when the
    streaming `load_match_history` upgrades headers to full payloads."""
    mh = live.match_history or []
    if not mh:
        return ("empty", 0)
    first = mh[0] or {}
    return (first.get("id"), len(mh),
            len(first.get("participants") or []),
            (live.records or {}).get("most_games", {}).get("value", 0))


def _build_on_fire():
    """Find the current longest active win streak across all players."""
    streaks   = {}     # name -> current streak
    champs_in_streak = {}  # name -> [(champ, opponents...), ...]
    if not live.match_history:
        return None
    # Iterate oldest -> newest so a loss resets the counter cleanly.
    for m in reversed(live.match_history):
        for pt in m.get("participants") or []:
            name = pt.get("player") or pt.get("player_name")
            if not name:
                continue
            # Use the participant's own win column when present (authoritative).
            if "win" in pt and pt["win"] is not None:
                won = bool(pt["win"])
            else:
                won = ((pt.get("team") or "").lower()
                       == (m.get("winner") or "").lower())
            if won:
                streaks[name] = streaks.get(name, 0) + 1
                champs_in_streak.setdefault(name, []).append(
                    pt.get("champion") or "?")
            else:
                streaks[name] = 0
                champs_in_streak[name] = []
    if not streaks:
        return None
    name, streak = max(streaks.items(), key=lambda kv: kv[1])
    if streak < 2:
        return None
    champs_list = champs_in_streak.get(name, [])
    champ_counts = {}
    for c in champs_list:
        champ_counts[c] = champ_counts.get(c, 0) + 1
    top_champs = sorted(champ_counts.items(), key=lambda kv: -kv[1])[:3]
    detail = "  ·  ".join(f"{n}-0 on {c}" for c, n in top_champs) \
             if top_champs else f"{streak} wins in a row"
    return {
        "label":    "ON FIRE",
        "accent":   _AC_AMBER,
        "headline": f"{name}  ·  {streak}-game win streak",
        "detail":   detail,
        "context":  "longest active streak in the league",
        "visual":   ("streak_bar", streak),
    }


def _build_top_performance():
    rec = (live.records or {}).get("best_kda_game")
    if not rec:
        return None
    k = rec.get("kills"); d = rec.get("deaths"); a = rec.get("assists")
    kda = float(rec.get("value") or 0)
    champ = rec.get("champion") or "?"
    player = rec.get("player") or "—"
    win = "WIN" if rec.get("win") else "LOSS"
    when = _date_short(rec.get("started_at"))
    detail_bits = []
    if k is not None and d is not None and a is not None:
        detail_bits.append(f"{k}/{d}/{a} on {champ}")
    else:
        detail_bits.append(f"on {champ}")
    return {
        "label":    "TOP PERFORMANCE",
        "accent":   _AC_GOLD,
        "headline": f"{player}  ·  {kda:.2f} KDA",
        "detail":   "  ·  ".join(detail_bits),
        "context":  f"{win}  ·  {when}",
        "visual":   ("kda_breakdown", (k or 0, d or 0, a or 0)),
    }


def _build_carry_mode():
    rec = (live.records or {}).get("most_damage")
    if not rec:
        return None
    val = int(rec.get("value") or 0)
    player = rec.get("player") or "—"
    champ = rec.get("champion") or "?"
    win = "WIN" if rec.get("win") else "LOSS"
    when = _date_short(rec.get("started_at"))
    return {
        "label":    "CARRY MODE",
        "accent":   _AC_VIOLET,
        "headline": f"{player}  ·  {compact(val)} damage",
        "detail":   f"on {champ}  ·  {win}",
        "context":  f"single-game damage record  ·  {when}",
        "visual":   None,
    }


def _build_most_kills():
    rec = (live.records or {}).get("most_kills")
    if not rec:
        return None
    val = int(rec.get("value") or 0)
    player = rec.get("player") or "—"
    champ = rec.get("champion") or "?"
    when = _date_short(rec.get("started_at"))
    return {
        "label":    "MOST KILLS",
        "accent":   _AC_RED,
        "headline": f"{player}  ·  {val} kills",
        "detail":   f"on {champ}  ·  {when}",
        "context":  "league single-game record",
        "visual":   None,
    }


def _build_biggest_blowout():
    rec = (live.records or {}).get("biggest_blowout")
    if not rec:
        return None
    diff = int(rec.get("value") or 0)
    winner = (rec.get("winner") or "").lower()
    when = _date_short(rec.get("started_at"))
    # Find the carry — pick the top-K player on the winning side of the
    # blowout match if we have its participants cached.
    mid = rec.get("match_id")
    carry_name = ""
    carry_champ = ""
    carry_kda = ""
    if mid:
        for mm in (live.match_history or []):
            if str(mm.get("id")) != str(mid):
                continue
            best = None
            for pt in (mm.get("participants") or []):
                if (pt.get("team") or "").lower() != winner:
                    continue
                k = int(pt.get("kills") or 0)
                a = int(pt.get("assists") or 0)
                d = max(1, int(pt.get("deaths") or 0))
                score = (k * 2.0 + a) / d
                if best is None or score > best[0]:
                    best = (score, pt)
            if best:
                pt = best[1]
                carry_name  = (pt.get("player") or "").strip()
                carry_champ = (pt.get("champion") or "").strip()
                carry_kda   = f"{int(pt.get('kills') or 0)}/{int(pt.get('deaths') or 0)}/{int(pt.get('assists') or 0)}"
            break
    if carry_name:
        head = f"{carry_name.upper()} carried"
        if carry_champ:
            head += f" on {carry_champ}"
        detail = f"{carry_kda}  ·  team won by +{diff} kills"
    else:
        head = f"Blowout — won by +{diff} kills"
        detail = "the largest stomp ever logged"
    return {
        "label":    "BIGGEST BLOWOUT",
        "accent":   _AC_RED,
        "headline": head,
        "detail":   detail,
        "context":  when,
        "visual":   ("kill_bar", (winner, diff)),
    }


def _build_grinder():
    rec = (live.records or {}).get("most_games")
    if not rec:
        return None
    n = int(rec.get("value") or 0)
    player = rec.get("player") or "—"
    return {
        "label":    "THE GRINDER",
        "accent":   _AC_TEAL,
        "headline": f"{player}  ·  {n} games logged",
        "detail":   "most active player in the league",
        "context":  "first into queue, last to log off",
        "visual":   None,
    }


def _build_climber():
    """Biggest rank delta since the rankings tab last opened."""
    try:
        from ui.rankings import rankings as _rk
        deltas = getattr(_rk, "deltas", {}) or {}
    except Exception:
        return None
    ups = [(n, d) for n, d in deltas.items()
           if isinstance(d, int) and d > 0]
    if not ups:
        return None
    ups.sort(key=lambda x: -x[1])
    name, delta = ups[0]
    plural = "spot" if delta == 1 else "spots"
    return {
        "label":    "CLIMBER",
        "accent":   _AC_WIN,
        "headline": f"{name}  ·  +{delta} {plural}",
        "detail":   "biggest rank jump since you last opened Rankings",
        "context":  "momentum — watch this player",
        "visual":   None,
    }


def _build_latest_drama():
    if not live.match_history:
        return None
    m = live.match_history[0]
    winner = (m.get("winner") or "").lower()
    if not winner:
        return None
    dur = m.get("duration") or 0
    mm = int(dur) // 60 if dur else 0
    # Compute kill totals per team and find the top-fragger on the winning side.
    bk, rk = 0, 0
    best = None
    for pt in m.get("participants") or []:
        side = (pt.get("team") or "").lower()
        k = int(pt.get("kills") or 0)
        if side == "blue": bk += k
        elif side == "red": rk += k
        if side == winner:
            a = int(pt.get("assists") or 0)
            d = max(1, int(pt.get("deaths") or 0))
            score = (k * 2.0 + a) / d
            if best is None or score > best[0]:
                best = (score, pt)
    diff = abs(bk - rk)
    winners = _winning_team_names(m, limit=5)
    if best:
        pt = best[1]
        carry_name  = (pt.get("player") or "").strip().upper() or "—"
        carry_champ = (pt.get("champion") or "").strip()
        carry_kda   = (f"{int(pt.get('kills') or 0)}/"
                       f"{int(pt.get('deaths') or 0)}/"
                       f"{int(pt.get('assists') or 0)}")
        head = f"{carry_name} popped off"
        if carry_champ:
            head += f"  ·  {carry_champ}"
        detail = (f"{carry_kda} carry  ·  team kills {bk}-{rk}"
                  if (bk or rk) else f"{carry_kda} carry")
        # Add the rest of the winning lineup so the card has a sense of the
        # whole team, not just the carry.
        other_winners = [n for n in winners
                         if n.upper() != carry_name][:4]
        if other_winners:
            detail += "  ·  with " + "  ".join(other_winners)
    elif winners:
        # Participants exist but the carry pick was somehow None — fall back
        # to listing the winning team.
        head = f"{winners[0].upper()} on the winning side"
        detail = (f"with {'  ·  '.join(winners[1:5])}"
                  if len(winners) > 1 else "—")
    else:
        # Header-only state (participants haven't streamed in yet). Show the
        # most useful info we have: which side won + score is unknown.
        head = f"{winner.upper()} side won"
        detail = "loading lineup…" if not live.match_history_loaded else "no participants logged"
    context = _time_ago(m.get("started_at"))
    if mm:
        context = f"{mm}-minute game  ·  {context}"
    return {
        "label":    "LATEST DRAMA" if diff and diff < 12 else "LATEST MATCH",
        "accent":   _AC_WIN if winner == "blue" else _AC_RED,
        "headline": head,
        "detail":   detail,
        "context":  context,
        "visual":   ("kill_bar", ("blue" if winner == "blue" else "red",
                                   max(bk, rk) - min(bk, rk))),
    }


# D1 (sheet decommission): _build_hot_take and _build_controversial were
# removed alongside the Consensus / Hot Takes / Rater Bias sheets they fed
# on. The home-tab pulse rotation falls back to the remaining card builders.

def _build_hot_take():
    return None


def _build_controversial():
    return None
    # Legacy implementation kept below for reference; unreachable.
    top = max(live.tier_consensus or [],
              key=lambda p: float(p.get("std", 0) or 0),
              default=None)
    if not top:
        return None
    std = float(top.get("std", 0) or 0)
    avg = float(top.get("avg", 0) or 0)
    return {
        "label":    "MOST CONTROVERSIAL",
        "accent":   _AC_GOLD,
        "headline": f"{top.get('name') or '—'}  ·  σ={std:.2f}",
        "detail":   f"average rating {avg:.1f}  ·  raters can't agree",
        "context":  "widest disagreement on the tier list",
        "visual":   None,
    }


def _build_sharpest_predictor():
    eligible = [p for p in (live.pred_leaderboard or [])
                if p.get("total", 0) >= 3]
    if not eligible:
        return None
    top = max(eligible, key=lambda p: p.get("accuracy", 0))
    return {
        "label":    "SHARPEST PREDICTOR",
        "accent":   _AC_BLUE,
        "headline": f"{top.get('voter') or '—'}  ·  "
                    f"{top.get('accuracy', 0):.0f}% correct",
        "detail":   f"{top.get('correct', 0)}/{top.get('total', 0)} calls right",
        "context":  "the smart money on inhouse predictions",
        "visual":   None,
    }


_PULSE_BUILDERS = (
    _build_on_fire,
    _build_top_performance,
    _build_carry_mode,
    _build_biggest_blowout,
    _build_most_kills,
    _build_grinder,
    _build_climber,
    _build_latest_drama,
    _build_sharpest_predictor,
)


def _pulse_items():
    """Memoized list of pulse cards. Rebuilt only when match history changes."""
    sig = _match_history_signature()
    if _pulse_cache["sig"] == sig and _pulse_cache["items"] is not None:
        return _pulse_cache["items"]
    items = []
    for fn in _PULSE_BUILDERS:
        try:
            card = fn()
        except Exception:
            card = None
        if card:
            items.append(card)
    _pulse_cache["sig"] = sig
    _pulse_cache["items"] = items
    return items


def _draw_pulse_visual(dl, x, y, w, accent, spec):
    """Render the optional tiny visual a pulse card may include.

    Returns the height it consumed."""
    if not spec:
        return 0
    tag, val = spec
    if tag == "streak_bar":
        n = int(val)
        cells = min(n, 12)
        cell_w = min(22, (w - (cells - 1) * 4) // cells) if cells else 0
        cx = x
        for _ in range(cells):
            dpg.draw_rectangle((cx, y), (cx + cell_w, y + 14),
                               fill=(*_AC_WIN[:3], 230),
                               color=(0, 0, 0, 0),
                               rounding=3, parent=dl)
            cx += cell_w + 4
        if n > cells:
            dpg.draw_text((cx + 4, y - 1), f"+{n - cells}",
                          color=(*_AC_WIN[:3], 230),
                          size=SZ_CAPTION, parent=dl)
        return 18
    if tag == "kda_breakdown":
        k, d, a = val
        items = [("K", k, _AC_RED), ("D", d, (160, 160, 165, 255)),
                 ("A", a, _AC_BLUE)]
        cx = x
        for tag2, num, col in items:
            chip_w = 64
            dpg.draw_rectangle((cx, y), (cx + chip_w, y + 22),
                               fill=(*col[:3], 35),
                               color=(*col[:3], 200),
                               rounding=4, parent=dl)
            dpg.draw_text((cx + 6, y + 3), tag2,
                          color=(*col[:3], 240),
                          size=SZ_LABEL, parent=dl)
            v_txt = str(int(num))
            vw = len(v_txt) * 8
            dpg.draw_text((cx + chip_w - vw - 6, y + 3), v_txt,
                          color=C["txt"], size=SZ_BODY, parent=dl)
            cx += chip_w + 6
        return 26
    if tag == "kill_bar":
        side, diff = val
        # Two-side bar: 50/50 default, biased toward winner by `diff` notches
        bar_w = w
        bar_h = 10
        ratio = min(0.85, 0.5 + (diff / 60.0))   # cap so the loser isn't 0
        if side == "blue":
            blue_w = int(bar_w * ratio)
        else:
            blue_w = int(bar_w * (1 - ratio))
        dpg.draw_rectangle((x, y), (x + blue_w, y + bar_h),
                           fill=(*_AC_BLUE[:3], 230),
                           color=(0, 0, 0, 0),
                           rounding=2, parent=dl)
        dpg.draw_rectangle((x + blue_w, y), (x + bar_w, y + bar_h),
                           fill=(*_AC_RED[:3], 230),
                           color=(0, 0, 0, 0),
                           rounding=2, parent=dl)
        return 14
    return 0


def _draw_pulse(dl, x, y, w, h):
    accent = _AC_VIOLET
    _draw_card(dl, x, y, w, h, hov_key="pls", accent=accent)
    title_h = _section_title(dl, x + PAD_CARD, y + PAD_CARD,
                              w - PAD_CARD * 2, "LEAGUE PULSE", accent)

    items = _pulse_items()
    inner_x = x + PAD_CARD
    inner_y = y + PAD_CARD + title_h + 6
    inner_w = w - PAD_CARD * 2

    if not items:
        if (not live.match_history_loaded and not live.match_history_error
                and not live.records_loaded):
            effects.draw_skeleton_text(dl, inner_x, inner_y,
                                        inner_w, lines=3,
                                        line_h=18, gap=10)
        else:
            dpg.draw_text((inner_x, inner_y),
                          "No pulse yet.",
                          color=(*C["txt"][:3], 235),
                          size=SZ_BODY, parent=dl)
            dpg.draw_text((inner_x, inner_y + 24),
                          "Log an inhouse game and headlines start here.",
                          color=(*C["txt2"][:3], 220),
                          size=SZ_CAPTION + 1, parent=dl)
        return

    idx = int(time.monotonic() // 8) % len(items)
    card = items[idx]
    label   = card["label"]
    col     = card["accent"]
    head    = card["headline"]
    detail  = card.get("detail") or ""
    context = card.get("context") or ""
    visual  = card.get("visual")

    # ── Label chip ────────────────────────────────────────────────────────
    chip_w = max(150, len(label) * 9 + 22)
    dpg.draw_rectangle((inner_x, inner_y),
                       (inner_x + chip_w, inner_y + 26),
                       fill=(*col[:3], 60), color=(*col[:3], 235),
                       rounding=13, parent=dl)
    dpg.draw_text((inner_x + 12, inner_y + 6),
                  label, color=(*col[:3], 250),
                  size=SZ_LABEL + 1, parent=dl)

    # ── Headline ──────────────────────────────────────────────────────────
    head_y = inner_y + 42
    max_head = max(20, inner_w // 11)
    dpg.draw_text((inner_x, head_y),
                  clamp_text(head, max_head),
                  color=C["gold_lt"], size=24, parent=dl)

    # Accent underline on the headline — pulls the eye to it
    dpg.draw_line((inner_x, head_y + 30),
                  (inner_x + 36, head_y + 30),
                  color=(*col[:3], 230), thickness=3, parent=dl)

    # ── Detail line ───────────────────────────────────────────────────────
    detail_y = head_y + 40
    if detail:
        dpg.draw_text((inner_x, detail_y),
                      clamp_text(detail, max(30, inner_w // 9)),
                      color=(*C["txt"][:3], 240),
                      size=SZ_BODY, parent=dl)

    # ── Context line ──────────────────────────────────────────────────────
    context_y = detail_y + (24 if detail else 0)
    if context:
        dpg.draw_text((inner_x, context_y),
                      clamp_text(context, max(34, inner_w // 8)),
                      color=(*C["txt2"][:3], 235),
                      size=SZ_CAPTION + 1, parent=dl)

    # ── Optional visual (bottom-left, above the rotation dots) ────────────
    if visual:
        vis_h = 28
        vis_y = y + h - PAD_CARD - 20 - vis_h
        _draw_pulse_visual(dl, inner_x, vis_y,
                            min(inner_w, 260), col, visual)

    # ── Rotation dots ────────────────────────────────────────────────────
    n = len(items)
    dot_y = y + h - PAD_CARD - 4
    dot_strip_w = 16 * n
    base_x = x + w - PAD_CARD - dot_strip_w
    for i in range(n):
        cxd = base_x + i * 16
        active = (i == idx)
        r = 4 if active else 3
        a = 240 if active else 110
        col_d = (*col[:3], a) if active else (*C["txt_dim"][:3], a)
        dpg.draw_circle((cxd, dot_y), r,
                        fill=col_d, color=(0, 0, 0, 0), parent=dl)

# ---------------------------------------------------------------------------
# BOTTOM ROW: Recent Matches + Record Book
# ---------------------------------------------------------------------------

def _draw_recent_matches(dl, x, y, w, h):
    accent = (118, 168, 220, 255)
    _draw_card(dl, x, y, w, h, hov_key="rm", accent=accent)
    matches = list(live.match_history or [])
    title_h = _section_title(dl, x + PAD_CARD, y + PAD_CARD,
                              w - PAD_CARD * 2, "RECENT MATCHES",
                              accent, count=len(matches) if matches else None)

    inner_x = x + PAD_CARD
    inner_y = y + PAD_CARD + title_h + 4
    inner_w = w - PAD_CARD * 2
    inner_h = h - (inner_y - y) - PAD_CARD - 18   # leave room for footer link

    if not live.match_history_loaded and not live.match_history_error:
        for i in range(4):
            effects.draw_skeleton_row(dl, inner_x, inner_y + i * 40,
                                       inner_w, 34)
        return
    if live.match_history_error and not matches:
        dpg.draw_text((inner_x, inner_y + 8),
                      "Can't reach the match server.",
                      color=(*C["loss"][:3], 220),
                      size=SZ_BODY, parent=dl)
        return
    if not matches:
        dpg.draw_text((inner_x, inner_y + 8),
                      "No matches logged yet.",
                      color=(*C["txt_dim"][:3], 220),
                      size=SZ_BODY, parent=dl)
        dpg.draw_text((inner_x, inner_y + 28),
                      "Inhouse -> LOG INHOUSE GAME after a custom.",
                      color=(*C["txt2"][:3], 200),
                      size=SZ_CAPTION, parent=dl)
        return

    # Sized to show 5 matches comfortably — bumped row height so the role-
    # slot lineup line has breathing room.
    n_show = min(5, len(matches))
    row_h = max(62, (inner_h - 4) // n_show)

    # Column geometry. We stack two text lines per row now:
    #   line 1: WHEN  |  WIN_LABEL ............................. duration  source
    #   line 2: winning side roster (5 player names, dot-separated, clamped)
    col_when_x = inner_x + 14
    col_src_w_max = 110

    for i, m in enumerate(matches[:n_show]):
        ry = inner_y + i * row_h
        winner = (m.get("winner") or "").lower()
        side_col = C["win"] if winner == "blue" else \
                   ((220, 110, 120, 255) if winner == "red" else C["txt_dim"])

        # Subtle alt-row band so rows read as discrete cards
        if i % 2 == 1:
            dpg.draw_rectangle((inner_x - 4, ry + 2),
                               (inner_x + inner_w + 4, ry + row_h - 4),
                               fill=(*C["card_hover"][:3], 70),
                               color=(0, 0, 0, 0),
                               rounding=4, parent=dl)

        # Side-color stripe on the left
        dpg.draw_rectangle((inner_x, ry + 4), (inner_x + 4, ry + row_h - 6),
                           fill=(*side_col[:3], 240),
                           color=(0, 0, 0, 0), rounding=2, parent=dl)

        # Hitbox spans the full row
        mid = m.get("id")
        if mid:
            _match_hits.append((inner_x, ry, inner_x + inner_w,
                                 ry + row_h - 2, str(mid)))

        # --- line 1: when · win label · ... duration · source ---
        line1_y = ry + 6
        when = _time_ago(m.get("started_at"))
        dpg.draw_text((col_when_x, line1_y),
                      when.upper(), color=(*C["txt"][:3], 230),
                      size=SZ_BODY, parent=dl)

        # Source pill (right-aligned)
        src_right = inner_x + inner_w - 4
        if (src := (m.get("source") or "").upper()):
            sw = min(col_src_w_max, len(src) * 8 + 18)
            sx = src_right - sw
            sy = line1_y - 2
            dpg.draw_rectangle((sx, sy), (sx + sw, sy + 22),
                               fill=(*C["card_hover"][:3], 230),
                               color=(*C["gold_dk"][:3], 210),
                               rounding=11, parent=dl)
            dpg.draw_text((sx + 9, sy + 4),
                          src, color=(*C["txt"][:3], 235),
                          size=SZ_LABEL, parent=dl)
            src_right = sx - 12

        # Duration (sits to the left of the source pill)
        dur = m.get("duration") or 0
        if dur:
            mm, ss = int(dur) // 60, int(dur) % 60
            dtxt = f"{mm}:{ss:02d}"
            dw = len(dtxt) * (SZ_BODY * 4 // 10) + 8
            dpg.draw_text((src_right - dw, line1_y),
                          dtxt, color=(*C["txt2"][:3], 235),
                          size=SZ_BODY, parent=dl)

        # Win-label badge (after the timestamp)
        wlabel = "BLUE WIN" if winner == "blue" else \
                 ("RED WIN" if winner == "red" else "PENDING")
        when_w = len(when) * (SZ_BODY * 4 // 10) + 18
        wlx = col_when_x + when_w
        wlw = len(wlabel) * 8 + 18
        dpg.draw_rectangle((wlx, line1_y - 2),
                           (wlx + wlw, line1_y + 20),
                           fill=(*side_col[:3], 55),
                           color=(*side_col[:3], 220),
                           rounding=11, parent=dl)
        dpg.draw_text((wlx + 9, line1_y + 1),
                      wlabel, color=(*side_col[:3], 250),
                      size=SZ_LABEL, parent=dl)

        # --- line 2: 5 role slots, one per position ---
        slots = _winning_team_slots(m)
        line2_y = ry + row_h - SZ_CAPTION - 10
        if slots:
            # Left label: "WINNERS" — or "WINNERS · 3/10" when incomplete
            logged, expected = _participant_completeness(m)
            label_text = "WINNERS"
            label_color = (*C["txt2"][:3], 240)
            if logged < expected:
                label_text = f"WINNERS  ·  {logged}/{expected}"
                label_color = (*C["loss"][:3], 235)
            label_x = col_when_x
            dpg.draw_text((label_x, line2_y),
                          label_text,
                          color=label_color,
                          size=SZ_CAPTION, parent=dl)
            label_px = len(label_text) * 7 + 14
            # 5 slot grid spans the remaining width
            slots_x0 = label_x + label_px
            slots_w  = max(0, (inner_x + inner_w - 4) - slots_x0)
            slot_w   = slots_w // len(slots)
            for si, (role, name) in enumerate(slots):
                sx = slots_x0 + si * slot_w
                # Role chip (small)
                rx2 = sx + 26
                dpg.draw_rectangle((sx, line2_y - 1),
                                   (rx2, line2_y + 14),
                                   fill=(*C["card_hover"][:3], 220),
                                   color=(*C["gold_dk"][:3], 200),
                                   rounding=3, parent=dl)
                dpg.draw_text((sx + 4, line2_y + 1),
                              role,
                              color=(*C["gold"][:3], 235),
                              size=SZ_CAPTION - 1, parent=dl)
                # Name (or faint placeholder)
                if name:
                    name_text = clamp_text(name, max(8, (slot_w - 32) // 7))
                    dpg.draw_text((rx2 + 6, line2_y),
                                  name_text,
                                  color=(*C["txt"][:3], 235),
                                  size=SZ_CAPTION + 1, parent=dl)
                else:
                    dpg.draw_text((rx2 + 6, line2_y),
                                  "—",
                                  color=(*C["txt_dim"][:3], 180),
                                  size=SZ_CAPTION + 1, parent=dl)
        else:
            # Participants are streaming in
            dpg.draw_text((col_when_x, line2_y),
                          "loading roster…",
                          color=(*C["txt_dim"][:3], 200),
                          size=SZ_CAPTION, parent=dl)

        if i < n_show - 1:
            dpg.draw_line((inner_x + 14, ry + row_h - 2),
                          (inner_x + inner_w - 4, ry + row_h - 2),
                          color=(*C["rule_dark"][:3], 100),
                          thickness=1, parent=dl)

    # Footer link
    fx = inner_x
    fy = y + h - PAD_CARD - 4
    dpg.draw_text((fx, fy), "OPEN INHOUSE  >  HISTORY  >>",
                  color=(*C["gold"][:3], 220),
                  size=SZ_CAPTION, parent=dl)


def _draw_records(dl, x, y, w, h):
    accent = C["gold"]
    _draw_card(dl, x, y, w, h, hov_key="rb", accent=accent)
    title_h = _section_title(dl, x + PAD_CARD, y + PAD_CARD,
                              w - PAD_CARD * 2, "RECORD BOOK", accent)

    inner_x = x + PAD_CARD
    inner_y = y + PAD_CARD + title_h + 6
    inner_w = w - PAD_CARD * 2
    inner_h = h - (inner_y - y) - PAD_CARD

    if not live.records_loaded and not live.records_error:
        for i in range(4):
            effects.draw_skeleton_row(dl, inner_x, inner_y + i * 38,
                                       inner_w, 32)
        return
    if live.records_error and not live.records:
        dpg.draw_text((inner_x, inner_y + 4),
                      "Can't reach the records server.",
                      color=(*C["loss"][:3], 220),
                      size=SZ_BODY, parent=dl)
        return

    candidates = [
        ("Most kills",      "most_kills",         "int"),
        ("Highest KDA",     "best_kda_game",      "kda"),
        ("Most damage",     "most_damage",        "compact"),
        ("Longest streak",  "longest_win_streak", "int"),
        ("Biggest blowout", "biggest_blowout",    "int"),
        ("Most games",      "most_games",         "int"),
    ]
    picked = []
    for label, key, fmt in candidates:
        rec = (live.records or {}).get(key)
        if rec:
            picked.append((label, rec, fmt))
        if len(picked) >= 5:
            break

    if not picked:
        dpg.draw_text((inner_x, inner_y + 4),
                      "No records yet — log a few games.",
                      color=(*C["txt_dim"][:3], 220),
                      size=SZ_BODY, parent=dl)
        return

    n = len(picked)
    row_h = max(36, (inner_h - 4) // n)

    for i, (label, rec, fmt) in enumerate(picked):
        ry = inner_y + i * row_h
        # Alt-row band
        if i % 2 == 1:
            dpg.draw_rectangle((inner_x - 4, ry),
                               (inner_x + inner_w + 4, ry + row_h - 2),
                               fill=(*C["card_hover"][:3], 80),
                               color=(0, 0, 0, 0),
                               rounding=4, parent=dl)
        # Label (small caps)
        dpg.draw_text((inner_x, ry + (row_h - SZ_CAPTION) // 2 - 9),
                      label.upper(),
                      color=(*C["txt2"][:3], 220),
                      size=SZ_CAPTION, parent=dl)
        # Holder
        holder = (rec.get("player") or rec.get("holder")
                  or (rec.get("winner") or "—").upper() + " TEAM")
        dpg.draw_text((inner_x, ry + (row_h - SZ_NAME_HI) // 2 + 8),
                      clamp_text(holder, 22),
                      color=C["txt"],
                      size=SZ_NAME_HI, parent=dl)
        # Value (right-aligned, count-up)
        value = rec.get("value", 0)
        try:
            vnum = float(value)
            lv = effects.count_up(f"home_rec:{i}", vnum, rate=0.20)
            if fmt == "kda":
                v_txt = f"{lv:.2f}"
            elif fmt == "compact":
                v_txt = compact(lv)
            else:
                v_txt = commas(int(round(lv)))
        except (TypeError, ValueError):
            v_txt = str(value)
        vw = len(v_txt) * (SZ_TITLE * 4 // 10) + 4
        vx = inner_x + inner_w - vw
        dpg.draw_text((vx, ry + (row_h - SZ_TITLE) // 2 + 2),
                      v_txt, color=C["gold_lt"],
                      size=SZ_TITLE, parent=dl)


# ---------------------------------------------------------------------------
# FOOTER
# ---------------------------------------------------------------------------

def _draw_footer(dl, x, y, w):
    h = FOOTER_H
    dpg.draw_rectangle((x, y), (x + w, y + h),
                       fill=C["card"], color=(*C["rule_dark"][:3], 180),
                       rounding=RADIUS, thickness=1, parent=dl)

    stats = _stats_cache["data"] or {}
    matches = stats.get("matches") if isinstance(stats, dict) else 0
    parts   = stats.get("participants") if isinstance(stats, dict) else 0
    last    = stats.get("last_ingest")

    # Pulse dot on the left
    fresh = bool(last)
    dot_col = C["win"] if fresh else C["txt_dim"]
    pulse = (math.sin(time.monotonic() * 2.0) * 0.5 + 0.5)
    dot_x = x + 18
    dot_y = y + h // 2
    dpg.draw_circle((dot_x, dot_y), 5,
                    fill=(*dot_col[:3], int(180 + pulse * 75)),
                    color=(0, 0, 0, 0), parent=dl)
    age = _time_ago(last) if last else "no ingest yet"
    line = (f"{commas(matches)} matches  ·  {commas(parts)} participants  "
            f"·  last update {age}")
    dpg.draw_text((dot_x + 14, dot_y - 7),
                  line, color=(*C["txt"][:3], 235),
                  size=SZ_BODY, parent=dl)

    # Right: hotkey hint
    hint = "F1 / ?  KEYBOARD SHORTCUTS    Esc  CLOSE OVERLAY"
    hw = len(hint) * 7
    hx = x + w - hw - 22
    if hx > dot_x + 360:
        dpg.draw_text((hx, dot_y - 7), hint,
                      color=(*C["txt_dim"][:3], 220),
                      size=SZ_CAPTION, parent=dl)


# ---------------------------------------------------------------------------
# PUBLIC DRAW
# ---------------------------------------------------------------------------

_enter = {"t0": 0.0, "last": 0.0}


def _entrance_dy(i, now):
    """Staggered entrance offset for card `i` — cards settle upward into
    place when the tab is (re)opened. 0 when motion is off."""
    if anim.intensity <= 0.01:
        return 0
    t = (now - _enter["t0"] - 0.055 * i) / 0.36
    t = max(0.0, min(1.0, t))
    return int(((1.0 - t) ** 3) * 30)


def draw_home(dl, w, h, fonts=None):
    global _wrapped_hit
    dpg.delete_item(dl, children_only=True)
    _player_hits.clear()
    _match_hits.clear()
    _wrapped_hit = None

    _ensure_all()
    splash_art.flush_pending()   # register any hero-backdrop splash downloads

    # Entrance choreography clock — reset when the tab is re-entered.
    now = time.monotonic()
    if now - _enter["last"] > 0.45:
        _enter["t0"] = now
    _enter["last"] = now

    # Background — flat base + a broad cool top-light so the page has depth
    # before any card draws.
    dpg.draw_rectangle((0, 0), (w, h),
                       fill=C["bg"], color=(0, 0, 0, 0), parent=dl)
    luxe.glow(dl, w * 0.5, -h * 0.25, w * 0.75, (40, 72, 118), 60)
    # Persistent ambient layers — three motes seeds + a very slow drift field
    # behind everything so the home page reads "alive" without distracting from
    # content. All layers scale with the global anim intensity slider.
    effects.draw_ambient_motes(dl, 0, 0, w, h,
                                accent=C["gold"], alpha=70, n=14, seed=11)
    effects.draw_ambient_motes(dl, 0, 0, w, h,
                                accent=C["rift_purple"], alpha=45, n=10, seed=29)
    effects.draw_ambient_motes(dl, 0, 0, w // 2, h,
                                accent=C["gold_lt"], alpha=35, n=8, seed=53)
    effects.draw_drift_field(dl, 0, 0, w, h, alpha=50,
                              accent=C["gold"], n_dots=14, seed=17)
    # Rising embers — the page breathes even at rest.
    luxe.draw_embers(dl, 0, int(h * 0.35), w, int(h * 0.65),
                     n=22, seed=13, alpha=105)

    # ── Layout ────────────────────────────────────────────────────────────
    # Cinematic hero scales with the window (~28% of height); the remaining
    # space splits ~62/38 between the main row and the bottom row.
    hero_h = max(180, min(340, int(h * 0.28)))
    avail = h - PAD_OUTER * 2 - hero_h - GAP - FOOTER_H - GAP
    main_h   = max(420, int(avail * 0.62))
    bottom_h = max(240, avail - main_h)

    x0 = PAD_OUTER
    y0 = PAD_OUTER
    width = w - PAD_OUTER * 2

    # 1) Hero (full-bleed cinematic — no entrance offset, it's the anchor)
    _draw_hero(dl, x0, y0, width, hero_h)
    cy = y0 + hero_h + GAP

    # 2) Main row (rankings + right stack) — staggered entrance
    left_w  = int((width - GAP) * 0.60)
    right_w = width - GAP - left_w
    _draw_rankings(dl, x0, cy + _entrance_dy(1, now), left_w, main_h)

    # Right column stack: SEASON (top, ~46%) + PULSE (bottom, ~54%)
    rx = x0 + left_w + GAP
    season_h = int(main_h * 0.46) - GAP // 2
    pulse_h  = main_h - season_h - GAP
    _draw_season(dl, rx, cy + _entrance_dy(2, now), right_w, season_h)
    _draw_pulse(dl, rx, cy + season_h + GAP + _entrance_dy(3, now),
                right_w, pulse_h)

    cy += main_h + GAP

    # 3) Bottom row (recent matches + records)
    _draw_recent_matches(dl, x0, cy + _entrance_dy(4, now), left_w, bottom_h)
    _draw_records(dl, rx, cy + _entrance_dy(5, now), right_w, bottom_h)
    cy += bottom_h + GAP

    # 4) Footer
    _draw_footer(dl, x0, cy, width)

    # 5) Periodic light sweep + cinematic vignette (under overlays/toasts)
    luxe.sheen_band(dl, 0, 0, w, h, period=19.0, alpha=15)
    luxe.vignette(dl, 0, 0, w, h, 70)

    # ── Click dispatch ───────────────────────────────────────────────────
    if dpg.is_mouse_button_clicked(0) and not state.click_consumed:
        try:
            cw_pos = dpg.get_item_pos("content_win") or (68, 52)
            m  = dpg.get_mouse_pos(local=False) or (0, 0)
            vp = dpg.get_viewport_pos() or (0, 0)
        except Exception:
            return
        mx = m[0] - vp[0] - cw_pos[0]
        my = m[1] - vp[1] - cw_pos[1]

        if _wrapped_hit:
            wx1, wy1, wx2, wy2 = _wrapped_hit
            if wx1 <= mx <= wx2 and wy1 <= my <= wy2:
                state.click_consumed = True
                try:
                    from ui import wrapped as _wr, audio as _a
                    _wr.open_wrapped()
                    try: _a.play_click()
                    except Exception: pass
                except Exception:
                    pass
                return
        for x1, y1, x2, y2, name in _player_hits:
            if x1 <= mx <= x2 and y1 <= my <= y2:
                state.click_consumed = True
                state.nav_to_profile = name
                from ui import audio as _a
                try: _a.play_click()
                except Exception: pass
                return
        for x1, y1, x2, y2, mid in _match_hits:
            if x1 <= mx <= x2 and y1 <= my <= y2:
                state.click_consumed = True
                state.active_tab = "inhouse"
                try:
                    from ui.inhouse import inhouse as _ih, _set_view_mode
                    _set_view_mode("history")
                    _ih.select_match(mid)
                except Exception:
                    pass
                return
