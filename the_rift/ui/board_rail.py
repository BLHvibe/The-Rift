"""
Draft Board — right analytics rail.

v3.0.5 rewrite: pro-broadcast scoreboard style. Drops the radar / coverage
donut / synergy web / contested ladder clutter from v2.7 in favour of a
tighter, more actionable set of panels:

  1. WIN PROBABILITY        — LCS scoreboard arc + sparkline
  2. BAN INTEL / PICK BREAK — context-aware: ban-phase shows enemy threat
                              (player + WR + games), pick-phase shows the
                              7-factor "why this call" bars
  3. ACTIONABLE CALLOUTS    — three rows: TOP THREAT, STRONGEST SYNERGY,
                              WEAK SPOT
  4. DAMAGE PROFILE         — AP / AD / TRUE stacked bar

Every widget is defensive: a bad/empty datum draws an empty frame, never
raises, so the board can't be taken down by one analytics call. All engine
work is memoized by a picks-signature so re-running recommend_comps for the
win-probability gauge happens only when the board actually changes, not per
frame.

Text is drawn through a `txt` callback (pass ui.draft._txt) so this module
needs no font registry and stays import-cycle free. Shapes use ui.lol_theme.
"""
import math
import time
import dearpygui.dearpygui as dpg
from ui import lol_theme

try:
    from data import draft_engine as _eng
except Exception:                                    # pragma: no cover
    _eng = None


# ---------------------------------------------------------------------------
# Engine memo — recompute only when the locked picks/bans change
# ---------------------------------------------------------------------------
_cache = {
    "sig": None,
    "blue_combined": 0.0,
    "red_combined": 0.0,
    "winprob": 0.5,
    "history": [],          # last N win-prob samples (blue side)
}
_HIST_MAX = 24


def _state_sig(b):
    try:
        return (tuple(sorted(b.picks["BLUE"].items())),
                tuple(sorted(b.picks["RED"].items())),
                tuple(b.bans["BLUE"]), tuple(b.bans["RED"]))
    except Exception:
        return None


def _refresh_engine(b, inhouse, primary, scout=None):
    """Re-run recommend_comps for both sides when the board changed. Cheap
    because it is gated by the picks signature, not the frame clock."""
    sig = _state_sig(b)
    if sig == _cache["sig"]:
        return
    _cache["sig"] = sig
    bc = rc = 0.0
    scout = scout or {}
    if _eng is not None:
        for side, enemy, target_key in (("BLUE", "RED", "blue"),
                                        ("RED",  "BLUE", "red")):
            try:
                try:
                    res = _eng.recommend_comps(b.players[side], inhouse, primary,
                                               enemy_picks=b.locked_picks(enemy),
                                               n_results=1,
                                               scout_champs=scout)
                except TypeError:
                    res = _eng.recommend_comps(b.players[side], inhouse, primary,
                                               enemy_picks=b.locked_picks(enemy),
                                               n_results=1)
                val = float(res[0]["combined"]) if res else 0.0
            except Exception:
                val = 0.0
            if target_key == "blue":
                bc = val
            else:
                rc = val
    _cache["blue_combined"] = bc
    _cache["red_combined"] = rc
    tot = bc + rc
    wp = (bc / tot) if tot > 1e-6 else 0.5
    _cache["winprob"] = wp
    h = _cache["history"]
    h.append(wp)
    if len(h) > _HIST_MAX:
        del h[0:len(h) - _HIST_MAX]


# ---------------------------------------------------------------------------
# Small drawing helpers
# ---------------------------------------------------------------------------
def _panel(dl, x, y, w, h, title, txt, accent=None, badge=None):
    """Rounded rail panel with a gold title and optional right-aligned badge.
    Returns the inner content top-y."""
    accent = accent or lol_theme.LOL["gold_lt"][:3]
    lol_theme.draw_navy_panel(
        dl, x, y, x + w, y + h,
        fill=lol_theme._alpha(lol_theme.LOL["navy_deep"], 225),
        border_color=lol_theme.LOL["gold_rule"],
        border_thickness=1, rounding=6)
    txt(dl, x + 10, y + 7, title, (*accent, 235), 12, "raj_sb_12")
    if badge:
        b_lbl, b_col = badge
        bw = len(b_lbl) * 7 + 10
        bx = x + w - bw - 8
        dpg.draw_rectangle((bx, y + 5), (bx + bw, y + 21),
                           fill=(*b_col[:3], 60),
                           color=(*b_col[:3], 200),
                           thickness=1, rounding=3, parent=dl)
        txt(dl, bx + 5, y + 7, b_lbl, (*b_col[:3], 235), 11, "raj_sb_11")
    return y + 28


def _bar(dl, x, y, w, h, frac, col, bg=None):
    frac = max(0.0, min(1.0, frac))
    if bg is None:
        bg = lol_theme._alpha(lol_theme.LOL["navy_deep"], 150)
    dpg.draw_rectangle((x, y), (x + w, y + h),
                       fill=bg, color=(0, 0, 0, 0),
                       rounding=2, parent=dl)
    if frac > 0:
        dpg.draw_rectangle((x, y), (x + max(2, int(w * frac)), y + h),
                           fill=(*col[:3], 230), color=(0, 0, 0, 0),
                           rounding=2, parent=dl)


# ---------------------------------------------------------------------------
# Panel 1 — WIN PROBABILITY (LCS scoreboard look + sparkline)
# ---------------------------------------------------------------------------
def _w_winprob(dl, x, y, w, h, b, txt):
    cy0 = _panel(dl, x, y, w, h, "WIN PROBABILITY", txt)
    wp = _cache["winprob"]
    blue_pct = wp * 100.0
    red_pct = (1.0 - wp) * 100.0

    # Big paired percentages, centered. LCS scoreboard treatment: the leading
    # side's number is brightened, the trailing side is dimmed.
    leading_blue = blue_pct >= red_pct
    bcol = lol_theme.LOL["blue_side"][:3]
    rcol = lol_theme.LOL["red_side"][:3]
    big_y = cy0 + 4
    b_str = f"{blue_pct:5.1f}%"
    r_str = f"{red_pct:5.1f}%"
    txt(dl, x + 14, big_y, b_str,
        (*bcol, 245 if leading_blue else 170), 24, "raj_sb_22")
    rx = x + w - 14 - len(r_str) * 11
    txt(dl, rx, big_y, r_str,
        (*rcol, 245 if not leading_blue else 170), 24, "raj_sb_22")

    # VS divider, centered. Smaller "lead" indicator below the leader's %.
    cx_div = x + w // 2
    dpg.draw_line((cx_div, big_y + 4), (cx_div, big_y + 24),
                  color=(*lol_theme.LOL["gold_rule"][:3], 200),
                  thickness=1, parent=dl)
    lead_abs = abs(blue_pct - red_pct)
    lead_txt = f"+{lead_abs:.1f}"
    if leading_blue:
        txt(dl, x + 14, big_y + 28, lead_txt, (*bcol, 230), 12, "raj_sb_12")
    else:
        lwx = x + w - 14 - len(lead_txt) * 8
        txt(dl, lwx, big_y + 28, lead_txt, (*rcol, 230), 12, "raj_sb_12")

    # Split bar (blue|red).
    bar_y = big_y + 46
    bar_h = 12
    bx, bw = x + 12, w - 24
    split = int(bw * wp)
    dpg.draw_rectangle((bx, bar_y), (bx + split, bar_y + bar_h),
                       fill=(*bcol, 230), color=(0, 0, 0, 0),
                       rounding=3, parent=dl)
    dpg.draw_rectangle((bx + split, bar_y), (bx + bw, bar_y + bar_h),
                       fill=(*rcol, 230), color=(0, 0, 0, 0),
                       rounding=3, parent=dl)
    dpg.draw_rectangle((bx, bar_y), (bx + bw, bar_y + bar_h),
                       fill=(0, 0, 0, 0),
                       color=lol_theme._alpha(lol_theme.LOL["gold_rule"], 200),
                       thickness=1, rounding=3, parent=dl)
    # 50% reference tick
    dpg.draw_line((bx + bw // 2, bar_y - 2),
                  (bx + bw // 2, bar_y + bar_h + 2),
                  color=(*lol_theme.LOL["gold_lt"][:3], 200),
                  thickness=1, parent=dl)

    # Sparkline below.
    hist = _cache["history"][-16:]
    sp_y = bar_y + bar_h + 6
    sp_h = max(10, (y + h) - sp_y - 6)
    if len(hist) >= 2 and sp_h > 6:
        n = len(hist)
        step = bw / (n - 1)
        pts = [(bx + i * step, sp_y + sp_h - hist[i] * sp_h)
               for i in range(n)]
        for i in range(n - 1):
            dpg.draw_line(pts[i], pts[i + 1],
                          color=(*lol_theme.LOL["gold_lt"][:3], 200),
                          thickness=2, parent=dl)
        dpg.draw_line((bx, sp_y + sp_h * 0.5),
                      (bx + bw, sp_y + sp_h * 0.5),
                      color=(*lol_theme.LOL["gold_rule"][:3], 130),
                      thickness=1, parent=dl)


# ---------------------------------------------------------------------------
# Panel 2 — BAN INTEL (ban phase) or PICK BREAKDOWN (pick phase)
# ---------------------------------------------------------------------------
_WHY_ROWS = (
    ("comfort",    "COMFORT",  "gold_lt"),
    ("counter",    "COUNTER",  "win"),
    ("lane",       "LANE",     "win"),
    ("contested",  "CONTEST",  "warning"),
    ("blind_safe", "SAFE",     "blue_side"),
    ("flex",       "FLEX",     "blue_side"),
    ("steer",      "FIT",      "blue_side"),
)


def _w_breakdown(dl, x, y, w, h, rec, b, txt):
    """v3.0.5: context-aware. For PICK actions render the 7-factor bars
    (existing behaviour). For BAN actions render BAN INTEL — the threatening
    enemy player + their WR / games / KDA on the suggested champion, so the
    first ban no longer renders as an empty placeholder panel.

    v4.1.1: hide the engine breakdown on the opponent's turn — the figures
    here are for whoever is on the clock, so showing them while the enemy is
    picking leaks the engine's read of THEIR pick. Win-prob / callouts /
    damage profile stay visible because they're framed from our perspective."""
    is_ban = (rec.get("kind") == "ban")
    title = "BAN INTEL" if is_ban else "WHY THIS CALL"
    our_turn = bool(rec.get("our_turn"))
    if not our_turn:
        cy0 = _panel(dl, x, y, w, h, title, txt)
        txt(dl, x + 12, cy0 + 4, "opponent on the clock",
            (*lol_theme.LOL["txt_dim"][:3], 215), 13, "raj_sb_12")
        txt(dl, x + 12, cy0 + 24,
            "› intel deferred until our pick",
            (*lol_theme.LOL["txt_dim"][:3], 170), 12, "raj_sb_12")
        return

    sug0 = {}
    try:
        sug0 = (rec.get("suggestions") or [{}])[0] or {}
    except Exception:
        sug0 = {}

    if is_ban:
        cy0 = _panel(dl, x, y, w, h, title, txt)
        champ = sug0.get("champion", "")
        why = sug0.get("why", "")
        pl = sug0.get("player", "")
        role = sug0.get("role", "")
        if not champ:
            txt(dl, x + 12, cy0 + 6, "ban phase — strip enemy comfort",
                (*lol_theme.LOL["txt_dim"][:3], 220), 13, "raj_sb_12")
            return
        # Lead line: champion name + role chip.
        txt(dl, x + 12, cy0, champ[:18],
            (*lol_theme.LOL["loss"][:3], 240), 18, "raj_sb_18")
        if role:
            rx = x + 12 + min(len(champ[:18]) * 11, w - 80)
            chip_w = len(role) * 8 + 10
            dpg.draw_rectangle((rx, cy0 + 2), (rx + chip_w, cy0 + 20),
                               fill=lol_theme._alpha(lol_theme.LOL["navy_panel"], 200),
                               color=lol_theme._alpha(lol_theme.LOL["gold_rule"], 200),
                               thickness=1, rounding=3, parent=dl)
            txt(dl, rx + 5, cy0 + 4, role,
                (*lol_theme.LOL["gold_lt"][:3], 220), 11, "raj_sb_11")
        # Player line
        if pl:
            txt(dl, x + 12, cy0 + 22, f"THREAT: {pl[:18]}",
                (*lol_theme.LOL["txt_dim"][:3], 220), 12, "raj_sb_12")
        # Pull the enemy player's customs/scout stats for this champ.
        if b is not None:
            enemy_side = "RED" if b.our_side == "BLUE" else "BLUE"
            enemy_players = b.players.get(enemy_side, [])
            wr, games, kda, form = None, None, None, ""
            for p in enemy_players:
                if (p.get("name") or "") == pl:
                    form = (p.get("form") or "")[:12]
                    break
            # Try threat data attached to the suggestion (when present).
            try:
                games = int(sug0.get("games") or 0)
                wr = float(sug0.get("wr") or 0.0)
                kda = float(sug0.get("kda") or 0.0)
            except (TypeError, ValueError):
                games = wr = kda = None
            if games and games > 0:
                stat_y = cy0 + 42
                line = f"{int(wr)}% WR · {games}g · {kda:.1f} KDA"
                txt(dl, x + 12, stat_y, line[:30],
                    (*lol_theme.LOL["txt"][:3], 230), 13, "raj_sb_12")
                if form:
                    txt(dl, x + 12, stat_y + 18,
                        f"form: {form}",
                        (*lol_theme.LOL["txt_dim"][:3], 200),
                        11, "raj_sb_11")
            else:
                txt(dl, x + 12, cy0 + 42,
                    "no customs data — comfort pick",
                    (*lol_theme.LOL["txt_dim"][:3], 200),
                    12, "raj_sb_12")
        # Reason text — wraps the engine `why` field.
        if why:
            wy = cy0 + 80
            txt(dl, x + 12, wy, ("› " + str(why))[:42],
                (*lol_theme.LOL["gold_lt"][:3], 220), 11, "raj_sb_11")
        return

    # ── Pick branch: factor bars ────────────────────────────────────
    cy0 = _panel(dl, x, y, w, h, title, txt)
    f = sug0.get("factors") or {}
    champ = sug0.get("champion", "")
    if not f:
        txt(dl, x + 12, cy0 + 8, "no suggestion yet",
            (*lol_theme.LOL["txt_dim"][:3], 210), 12, "raj_sb_12")
        return
    if champ:
        txt(dl, x + 12, cy0, champ[:16],
            (*lol_theme.LOL["gold_lt"][:3], 235), 13, "raj_sb_12")
        cy0 += 18
    avail = (y + h) - cy0 - 6
    rh = max(13, min(19, avail // len(_WHY_ROWS)))
    ry = cy0 + 2
    lab_w = 64
    for key, lbl, col_key in _WHY_ROWS:
        col = lol_theme.LOL[col_key]
        try:
            v = max(0.0, min(1.0, float(f.get(key, 0.0))))
        except (TypeError, ValueError):
            v = 0.0
        if key == "lane":
            cmid = x + 12 + lab_w + (w - 24 - lab_w - 34) // 2
            txt(dl, x + 12, ry, lbl, (*col[:3], 215), 11, "raj_sb_11")
            half = (w - 24 - lab_w - 34) // 2
            adv = v - 0.5
            bx = x + 12 + lab_w
            dpg.draw_rectangle((bx, ry + 1), (bx + half * 2, ry + rh - 5),
                               fill=lol_theme._alpha(
                                   lol_theme.LOL["navy_deep"], 150),
                               color=(0, 0, 0, 0),
                               rounding=2, parent=dl)
            if adv >= 0:
                dpg.draw_rectangle((cmid, ry + 1),
                                   (cmid + int(half * adv * 2), ry + rh - 5),
                                   fill=(*lol_theme.LOL["win"][:3], 230),
                                   color=(0, 0, 0, 0),
                                   rounding=2, parent=dl)
            else:
                dpg.draw_rectangle((cmid + int(half * adv * 2), ry + 1),
                                   (cmid, ry + rh - 5),
                                   fill=(*lol_theme.LOL["red_side"][:3], 230),
                                   color=(0, 0, 0, 0),
                                   rounding=2, parent=dl)
            dpg.draw_line((cmid, ry), (cmid, ry + rh - 4),
                          color=(*lol_theme.LOL["txt_dim"][:3], 200),
                          thickness=1, parent=dl)
        else:
            txt(dl, x + 12, ry, lbl, (*col[:3], 215), 11, "raj_sb_11")
            _bar(dl, x + 12 + lab_w, ry + 1, w - 24 - lab_w - 34, rh - 6,
                 v, col)
        vs = f"{v:.2f}"
        txt(dl, x + w - 12 - len(vs) * 7, ry, vs,
            (*lol_theme.LOL["txt"][:3], 220), 11, "raj_sb_11")
        ry += rh


# ---------------------------------------------------------------------------
# Panel 3 — ACTIONABLE CALLOUTS (top threat / strongest synergy / weak spot)
# ---------------------------------------------------------------------------
def _build_callouts(b):
    """Return [(label, value, color_key), ...] for the three callout rows."""
    out = []
    our = b.our_side
    enemy_side = "RED" if our == "BLUE" else "BLUE"
    locked_us = [c for c in b.locked_picks(our) if c]
    locked_them = [c for c in b.locked_picks(enemy_side) if c]
    used = b.used_champs()

    # ROW 1 — TOP THREAT: enemy pick we have no counter for, plus best counter.
    threat_str = None
    threat_col = "warning"
    if _eng is not None and hasattr(_eng, "COUNTERS"):
        ctr = _eng.COUNTERS
        uncovered = []
        for e in locked_them:
            covered = any(ctr.get((o, e), 0.0) >= 0.30 for o in locked_us)
            if not covered:
                uncovered.append(e)
        if uncovered:
            target = uncovered[0]
            # Find the best legal counter to this threat.
            best, bestv = None, 0.0
            for (atk, vic), v in ctr.items():
                if vic == target and v > bestv and atk not in used:
                    best, bestv = atk, v
            if best:
                threat_str = f"{target[:10]} → {best[:10]}"
                threat_col = "loss"
            else:
                threat_str = f"{target[:14]}  (no counter)"
        elif locked_them:
            threat_str = "all threats covered"
            threat_col = "win"
    if not threat_str:
        if not locked_them:
            threat_str = "no enemy threats yet"
        else:
            threat_str = "—"
    out.append(("TOP THREAT", threat_str, threat_col))

    # ROW 2 — STRONGEST SYNERGY: best synergy pair on our locked picks.
    syn_str = None
    syn_col = "win"
    if _eng is not None and len(locked_us) >= 2:
        syn = getattr(_eng, "SYNERGIES", {}) or {}
        best_pair, best_val = None, 0.0
        for i in range(len(locked_us)):
            for j in range(i + 1, len(locked_us)):
                a, c = locked_us[i], locked_us[j]
                v = syn.get((a, c), syn.get((c, a), 0.0))
                if v > best_val:
                    best_pair, best_val = (a, c), v
        if best_pair and best_val > 0:
            syn_str = f"{best_pair[0][:8]} + {best_pair[1][:8]}"
        else:
            syn_str = "no notable pairs"
            syn_col = "txt_dim"
    if syn_str is None:
        syn_str = "need 2+ picks"
        syn_col = "txt_dim"
    out.append(("BEST SYNERGY", syn_str, syn_col))

    # ROW 3 — WEAK SPOT: role with worst projected matchup or open & high-risk.
    weak_str = None
    weak_col = "warning"
    if _eng is not None:
        lanes = getattr(_eng, "LANE_MATCHUPS", {}) or {}
        worst_role, worst_v = None, 0.0
        roles = ("TOP", "JGL", "MID", "BOT", "SUP")
        for r in roles:
            us_c = b.picks.get(our, {}).get(r)
            them_c = b.picks.get(enemy_side, {}).get(r)
            if us_c and them_c:
                v = lanes.get((us_c, them_c), 0.0)
                if v < worst_v:
                    worst_v, worst_role = v, r
        if worst_role and worst_v < -2:
            weak_str = f"{worst_role} losing {int(worst_v)}"
            weak_col = "loss"
        elif worst_role and worst_v < 0:
            weak_str = f"{worst_role} slight loss"
            weak_col = "warning"
        else:
            # Fall back to flagging open roles still missing comfort.
            open_us = [r for r in roles if r not in b.picks.get(our, {})]
            if open_us:
                weak_str = f"open: {' '.join(open_us[:3])}"
                weak_col = "txt_dim"
            else:
                weak_str = "lanes look even"
                weak_col = "win"
    if not weak_str:
        weak_str = "—"
    out.append(("WEAK SPOT", weak_str, weak_col))

    return out


def _w_callouts(dl, x, y, w, h, b, txt):
    cy0 = _panel(dl, x, y, w, h, "CALLOUTS", txt)
    try:
        rows = _build_callouts(b)
    except Exception:
        rows = []
    if not rows:
        txt(dl, x + 12, cy0 + 8, "no callouts",
            (*lol_theme.LOL["txt_dim"][:3], 200), 12, "raj_sb_12")
        return
    avail = (y + h) - cy0 - 6
    rh = max(28, min(40, avail // max(len(rows), 1)))
    ry = cy0 + 4
    for label, value, col_key in rows:
        if ry + rh > y + h:
            break
        col = lol_theme.LOL.get(col_key, lol_theme.LOL["txt_dim"])[:3]
        # Side stripe — colored tab at the left edge of the row.
        dpg.draw_rectangle((x + 10, ry + 2), (x + 13, ry + rh - 6),
                           fill=(*col, 230), color=(0, 0, 0, 0),
                           parent=dl)
        txt(dl, x + 20, ry + 2, label,
            (*lol_theme.LOL["txt_dim"][:3], 220), 11, "raj_sb_11")
        txt(dl, x + 20, ry + 18, str(value)[:26],
            (*col, 240), 14, "raj_sb_14")
        ry += rh


# ---------------------------------------------------------------------------
# Panel 4 — DAMAGE PROFILE (AP / AD / TRUE) — minimal, retained from v2.7
# ---------------------------------------------------------------------------
def _w_damage(dl, x, y, w, h, b, txt):
    cy0 = _panel(dl, x, y, w, h, "DAMAGE PROFILE", txt)
    if _eng is None:
        return
    ap = ad = tr = 0.0
    for c in b.locked_picks(b.our_side):
        if c in getattr(_eng, "DAMAGE_HYBRID", set()):
            ap += 0.5
            ad += 0.5
        elif c in getattr(_eng, "DAMAGE_AP", set()):
            ap += 1
        elif c in getattr(_eng, "DAMAGE_TRUE", set()):
            tr += 1
        else:
            ad += 1
    tot = ap + ad + tr
    bx, bw = x + 12, w - 24
    by = cy0 + 4
    bh = 18
    if tot <= 0:
        dpg.draw_rectangle((bx, by), (bx + bw, by + bh),
                           fill=lol_theme._alpha(lol_theme.LOL["navy_deep"], 150),
                           color=(0, 0, 0, 0), rounding=3, parent=dl)
        txt(dl, bx + 6, by + 2, "no picks yet",
            (*lol_theme.LOL["txt_dim"][:3], 200), 11, "raj_sb_11")
        return
    segs = ((ap, (180, 130, 220, 255), "AP"),
            (ad, lol_theme.LOL["warning"], "AD"),
            (tr, (200, 200, 210, 255), "TR"))
    cxp = bx
    for val, col, lbl in segs:
        sw = int(bw * (val / tot))
        if sw <= 0:
            continue
        dpg.draw_rectangle((cxp, by), (cxp + sw, by + bh),
                           fill=(*col[:3], 230), color=(0, 0, 0, 0),
                           rounding=2, parent=dl)
        if sw > 26:
            txt(dl, cxp + 5, by + 2, lbl,
                (*lol_theme.LOL["navy_deep"][:3], 235), 11, "raj_sb_11")
        cxp += sw
    txt(dl, bx, by + bh + 4,
        f"AP {int(ap)}  AD {int(ad)}  TRUE {int(tr)}",
        (*lol_theme.LOL["txt"][:3], 215), 11, "raj_sb_11")


# ---------------------------------------------------------------------------
# Public — right rail
# ---------------------------------------------------------------------------
def draw_rail(dl, x, y, w, h, b, rec, txt, inhouse, primary, scout=None):
    """Stack the analytics widgets down the right rail.

    v3.0.5: dropped radar / coverage donut / synergy web / contested ladder /
    counter predictor (visual clutter that needed too many picks to populate).
    Replaced with a tight scoreboard layout: win-prob, ban/pick breakdown,
    actionable callouts, damage profile."""
    try:
        _refresh_engine(b, inhouse or {}, primary or {}, scout or {})
    except Exception:
        pass
    gap = 8
    cur = y
    plan = [
        (_w_winprob,    140, (b,)),
        (_w_breakdown,  170, (rec, b)),
        (_w_callouts,   130, (b,)),
        (_w_damage,     70,  (b,)),
    ]
    for fn, ph, args in plan:
        if cur + 60 > y + h:
            break
        ph = min(ph, (y + h) - cur)
        try:
            fn(dl, x, cur, w, ph, *args, txt)
        except Exception:
            lol_theme.draw_navy_panel(
                dl, x, cur, x + w, cur + ph,
                fill=lol_theme._alpha(lol_theme.LOL["navy_deep"], 220),
                border_color=lol_theme.LOL["red_side_dk"],
                border_thickness=1, rounding=6)
        cur += ph + gap


# ---------------------------------------------------------------------------
# § 3 #12 — draft narrative log (bottom terminal strip)
# ---------------------------------------------------------------------------
def draw_narrative(dl, x, y, w, h, b, txt):
    lol_theme.draw_navy_panel(
        dl, x, y, x + w, y + h,
        fill=lol_theme._alpha(lol_theme.LOL["navy_deep"], 225),
        border_color=lol_theme.LOL["gold_rule"],
        border_thickness=1, rounding=4)
    parts = []
    try:
        # v3.0.5: take the most-recent entries via the chronological
        # _history list (true action order, restored by the mirror() fix).
        # Step count is bounded by the strip's pixel budget at ~28 chars/entry.
        budget = max(4, (w - 32) // 22)
        for hentry in list(b._history)[-budget:]:
            side = "B" if hentry.side == "BLUE" else "R"
            verb = "BAN" if hentry.kind == "ban" else "PICK"
            parts.append(f"{side}{verb[:1]} {hentry.champ}")
    except Exception:
        parts = []
    line = "  ·  ".join(parts) if parts else "draft start — awaiting first action"
    txt(dl, x + 12, y + (h - 16) // 2, ("› " + line)[:max(8, (w - 24) // 8)],
        (*lol_theme.LOL["gold_lt"][:3], 225), 13, "raj_sb_12")


# ---------------------------------------------------------------------------
# § 3 #27 — action-queue preview (header strip)
# ---------------------------------------------------------------------------
def draw_action_queue(dl, x, y, w, b, txt, seq):
    """Next few actions: B-PICK · R-PICK …  side-colored, drawn in the header."""
    try:
        ptr = b.pointer
        nxt = [a for a in seq if a.idx >= ptr][:4]
    except Exception:
        nxt = []
    cxp = x
    txt(dl, cxp, y, "QUEUE",
        (*lol_theme.LOL["gold_rule"][:3], 220), 12, "raj_sb_12")
    cxp += 56
    for a in nxt:
        col = (lol_theme.LOL["blue_side"][:3] if a.side == "BLUE"
               else lol_theme.LOL["red_side"][:3])
        lbl = f"{'B' if a.side=='BLUE' else 'R'}-{a.kind[:4].upper()}"
        cw = len(lbl) * 8 + 14
        dpg.draw_rectangle((cxp, y - 3), (cxp + cw, y + 17),
                           fill=(*col, 36), color=(*col, 170),
                           thickness=1, rounding=3, parent=dl)
        txt(dl, cxp + 7, y, lbl, (*col, 235), 12, "raj_sb_12")
        cxp += cw + 6
