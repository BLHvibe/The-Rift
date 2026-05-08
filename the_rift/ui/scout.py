"""
Scout Tab — Phase 4 (revamp).
Left: sortable player table.  Right: inline scouting report panel.
Clicking any row loads the full report in the right panel.
"""
import math, time
import dearpygui.dearpygui as dpg
from theme import C, RANK_COLORS
from core.animations import anim
from data.reader import live, load_scout_sheet

# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------
TOP_BAR_H   = 56
PAD         = 20
TABLE_FRAC  = 0.38   # player table takes 38% of content width
ROW_H       = 52
HEADER_H    = 44
SIDEBAR_W   = 68     # viewport offset to content area
APP_TITLE_H = 52     # app titlebar height in viewport coords

COLS = [
    ("RANK",   0.08, "score"),
    ("PLAYER", 0.32, None),
    ("SCORE",  0.15, "score"),
    ("W/R",    0.13, "wr"),
    ("KDA",    0.13, "kda"),
    ("GAMES",  0.19, None),
]

_REPORT_WIN = "scout_report_panel_win"

# ---------------------------------------------------------------------------
# Report building from live data
# ---------------------------------------------------------------------------

def _build_full_report(name):
    """Build a complete report dict from live data for a named player."""
    p = next((x for x in scout.players if x["name"] == name), None)
    if not p:
        return None

    score  = p.get("score", 0)
    tier   = p.get("tier", "Unranked")
    wr     = p.get("wr", 0)
    kda    = p.get("kda", 0.0)
    games  = p.get("games", 0)
    form   = p.get("form", "MIXED")
    rating = p.get("rating", "?")

    try:    ts = float(p.get("tier_score") or 0)
    except Exception: ts = 0.0
    try:    rs = float(p.get("rank_score") or 0)
    except Exception: rs = 0.0

    rank = p.get("rank", next(
        (i + 1 for i, x in enumerate(scout.players) if x["name"] == name), 0))

    ih_champs = live.inhouse_champs.get(name, [])

    # Ban targets: inhouse champs with 3+ games, sorted by threat
    ban_targets = []
    for ch in sorted(ih_champs, key=lambda x: -x.get("games", 0)):
        cg = ch.get("games", 0)
        cwr_str = str(ch.get("wr", "0")).replace("%", "")
        try:    cwr = float(cwr_str)
        except Exception: cwr = 0.0
        ckda = ch.get("kda", 0.0)
        if cg < 3:
            continue
        if   cwr >= 65: threat = "PERMABAN"
        elif cwr >= 55: threat = "HIGH"
        elif cg  >= 5:  threat = "ELEVATED"
        else:           continue
        ban_targets.append({
            "name": ch["champ"], "games": cg,
            "wr":   f"{cwr:.0f}%", "kda": ckda, "threat": threat,
        })
        if len(ban_targets) >= 3:
            break

    # Inhouse display (top 8)
    inhouse_display = []
    for ch in ih_champs[:8]:
        inhouse_display.append({
            "name":   ch["champ"],
            "games":  ch["games"],
            "wins":   ch["wins"],
            "losses": ch["losses"],
            "wr":     ch["wr"],
            "kda":    ch["kda"],
            "damage": ch.get("damage", "—"),
        })

    return {
        "player":         name,
        "tier":           tier,
        "score":          score,
        "power_position": str(rank),
        "rating_letter":  rating,
        "tier_score":     ts,
        "rank_score":     rs,
        "scouted_days_ago": None,
        "overview": [
            ("Win Rate", f"{wr}%"),
            ("KDA",      f"{kda:.1f}"),
            ("Games",    str(games)),
            ("Form",     form),
        ],
        "form":          form,
        "ban_targets":   ban_targets,
        "top_champs":    p.get("top_champs", []),
        "inhouse_champs": inhouse_display,
    }


# ---------------------------------------------------------------------------
# Report section renderers
# (each adds DPG widgets into the current DPG container context)
# ---------------------------------------------------------------------------

def _rw_label(text, font_key="raj_sb_18", color=None):
    t = dpg.add_text(text, color=color or C["gold"][:3])
    if font_key in _F:
        dpg.bind_item_font(t, _F[font_key])


def _rw_header(r):
    dpg.add_spacer(height=10)
    with dpg.group(horizontal=True):
        dpg.add_spacer(width=14)
        with dpg.group():
            t = dpg.add_text(r["player"].upper(), color=C["gold_lt"][:3])
            if "raj_36" in _F: dpg.bind_item_font(t, _F["raj_36"])
            with dpg.group(horizontal=True):
                bc = RANK_COLORS.get(r["tier"], RANK_COLORS["Unranked"])
                t2 = dpg.add_text(r["tier"].upper(), color=bc[:3])
                if "raj_sb_18" in _F: dpg.bind_item_font(t2, _F["raj_sb_18"])
                dpg.add_spacer(width=18)
                days = r.get("scouted_days_ago", None)
                if days is not None:
                    ac = (79,168,130) if days<=2 else (200,168,106) if days<=6 else (184,69,53)
                    ta = dpg.add_text(f"Scouted {days}d ago", color=ac)
                else:
                    ta = dpg.add_text("Live data", color=(79,168,130))
                if "raj_r_14" in _F: dpg.bind_item_font(ta, _F["raj_r_14"])
    dpg.add_spacer(height=10)
    dpg.add_separator()


def _rw_power_rating(r):
    dpg.add_spacer(height=8)
    _rw_label("POWER RATING")
    dpg.add_spacer(height=6)
    rating_colors = {
        "S":(200,70,60),"A":(200,155,60),"B":(160,136,78),
        "C":(92,138,92),"D":(92,122,156),"F":(110,110,110),
    }
    rc = rating_colors.get(r["rating_letter"], (120,120,120))
    with dpg.group(horizontal=True):
        dpg.add_spacer(width=14)
        t = dpg.add_text(f"#{r['power_position']}", color=C["gold"][:3])
        if "raj_28" in _F: dpg.bind_item_font(t, _F["raj_28"])
        dpg.add_spacer(width=20)
        t2 = dpg.add_text(r["rating_letter"], color=rc)
        if "raj_44" in _F: dpg.bind_item_font(t2, _F["raj_44"])
        dpg.add_spacer(width=20)
        with dpg.group():
            dpg.add_spacer(height=6)
            t3 = dpg.add_text(f"Score: {r['score']}", color=C["gold_lt"][:3])
            if "raj_24" in _F: dpg.bind_item_font(t3, _F["raj_24"])
            try:
                ts_str = f"{float(r['tier_score']):.0f}"
                rs_str = f"{float(r['rank_score']):.0f}"
            except Exception:
                ts_str = str(r["tier_score"])
                rs_str = str(r["rank_score"])
            t4 = dpg.add_text(f"Tier: {ts_str}   Rank: {rs_str}", color=C["txt2"][:3])
            if "raj_r_14" in _F: dpg.bind_item_font(t4, _F["raj_r_14"])
    dpg.add_spacer(height=8)
    dpg.add_separator()


def _rw_overview(r):
    dpg.add_spacer(height=8)
    _rw_label("OVERVIEW")
    dpg.add_spacer(height=8)
    with dpg.group(horizontal=True):
        dpg.add_spacer(width=14)
        for lbl, val in r["overview"]:
            with dpg.child_window(width=130, height=70, border=True,
                                  no_scrollbar=True, no_scroll_with_mouse=True):
                dpg.add_spacer(height=5)
                lt = dpg.add_text(lbl, color=C["txt_dim"][:3])
                if "raj_sb_14" in _F: dpg.bind_item_font(lt, _F["raj_sb_14"])
                dpg.add_spacer(height=2)
                vt = dpg.add_text(val, color=C["txt"][:3])
                if "raj_20" in _F: dpg.bind_item_font(vt, _F["raj_20"])
            dpg.add_spacer(width=6)
    dpg.add_spacer(height=8)
    dpg.add_separator()


def _rw_top_champs(r):
    champs = r.get("top_champs", [])
    if not champs:
        return
    dpg.add_spacer(height=8)
    _rw_label("CHAMPION POOL")
    dpg.add_spacer(height=6)
    with dpg.group(horizontal=True):
        dpg.add_spacer(width=14)
        for ch in champs[:5]:
            with dpg.child_window(width=100, height=38, border=True,
                                  no_scrollbar=True, no_scroll_with_mouse=True):
                t = dpg.add_text(ch, color=C["txt"][:3])
                if "raj_16" in _F: dpg.bind_item_font(t, _F["raj_16"])
            dpg.add_spacer(width=4)
    dpg.add_spacer(height=8)
    dpg.add_separator()


def _rw_ban_targets(r):
    dpg.add_spacer(height=8)
    _rw_label("BAN TARGETS")
    dpg.add_spacer(height=6)
    bans = r.get("ban_targets", [])
    if not bans:
        t = dpg.add_text("  No high-threat picks identified (need 3+ inhouse games at 55%+ WR)",
                         color=C["txt_dim"][:3])
        if "raj_r_14" in _F: dpg.bind_item_font(t, _F["raj_r_14"])
        dpg.add_spacer(height=8)
        dpg.add_separator()
        return

    threat_col = {"PERMABAN": C["loss"][:3], "HIGH": C["gold"][:3], "ELEVATED": C["txt2"][:3]}
    hdrs = ["CHAMPION", "GAMES", "W/R", "KDA", "THREAT"]
    with dpg.group(horizontal=True):
        dpg.add_spacer(width=14)
        for h in hdrs:
            t = dpg.add_text(f"{h:<13}", color=C["txt_dim"][:3])
            if "raj_sb_14" in _F: dpg.bind_item_font(t, _F["raj_sb_14"])
    dpg.add_separator()
    for b in bans:
        tc = threat_col.get(b["threat"], C["txt2"][:3])
        vals = [b["name"], str(b["games"]), b["wr"], str(b["kda"]), b["threat"]]
        with dpg.group(horizontal=True):
            dpg.add_spacer(width=14)
            for i, v in enumerate(vals):
                col = C["loss"][:3] if i == 0 else tc if i == 4 else C["txt"][:3]
                t = dpg.add_text(f"{v:<13}", color=col)
                if "raj_r_14" in _F: dpg.bind_item_font(t, _F["raj_r_14"])
    dpg.add_spacer(height=8)
    dpg.add_separator()


def _rw_rank_history(r):
    """Rank history graph — DPG drawlist inside a child window."""
    history = r.get("rank_history", [])
    if len(history) < 2:
        return
    dpg.add_spacer(height=8)
    _rw_label("RANK HISTORY")
    dpg.add_spacer(height=4)

    GW, GH = 520, 160   # graph canvas size (will be clipped to panel width)
    PAD_L, PAD_R, PAD_T, PAD_B = 36, 12, 10, 28

    pw = GW - PAD_L - PAD_R
    ph = GH - PAD_T - PAD_B

    vals  = [v for _, v in history]
    dates = [d for d, _ in history]
    lo    = max(1.0, min(vals) - 0.5)
    hi    = max(lo + 1.0, max(vals) + 0.5)

    def _px(i):   return PAD_L + int(pw * i / max(len(vals) - 1, 1))
    def _py(v):   return PAD_T + int(ph * (1.0 - (v - lo) / (hi - lo)))

    with dpg.child_window(height=GH + 4, border=False,
                          no_scrollbar=True, no_scroll_with_mouse=True):
        dl = dpg.add_drawlist(width=GW, height=GH)

        # Background
        dpg.draw_rectangle((0, 0), (GW, GH),
                            fill=(*C["card"][:3], 180), color=(0,0,0,0), parent=dl)

        # Tier zone fills (approximate bands mapped to rank value ranges)
        # Rank value ≈ position number; lower = better
        _TIER_BANDS = [
            (1,  3,  (200, 160,  80, 30)),   # gold tinge = top 3
            (4,  6,  (100, 160, 100, 25)),   # green = top 6
            (7, 10,  ( 80, 120, 160, 20)),   # blue = top 10
            (11, 20, ( 80,  80,  80, 15)),   # grey = rest
        ]
        for band_lo, band_hi, band_col in _TIER_BANDS:
            y1 = _py(min(hi, band_hi + 0.5))
            y2 = _py(max(lo, band_lo - 0.5))
            if y1 < y2:
                dpg.draw_rectangle((PAD_L, y1), (PAD_L + pw, y2),
                                   fill=band_col, color=(0,0,0,0), parent=dl)

        # Grid lines (horizontal rank guides)
        for rank_line in range(int(lo), int(hi) + 1):
            if lo <= rank_line <= hi:
                gy = _py(rank_line)
                dpg.draw_line((PAD_L, gy), (PAD_L + pw, gy),
                              color=(*C["rule_dark"][:3], 60), thickness=1, parent=dl)
                dpg.draw_text((2, gy - 8), f"#{int(rank_line)}",
                              color=(*C["txt_dim"][:3], 120), size=10, parent=dl)

        # Polyline
        pts = [(_px(i), _py(v)) for i, v in enumerate(vals)]
        if len(pts) >= 2:
            dpg.draw_polyline(pts, color=(*C["gold"][:3], 200),
                              thickness=2, parent=dl)

        # Data points + hover hint
        for i, (x, y) in enumerate(pts):
            dpg.draw_circle((x, y), 4,
                            fill=(*C["gold_lt"][:3], 220),
                            color=(*C["gold"][:3], 180), parent=dl)

        # Date labels (every 4th point, or fewer if not many)
        step = max(1, len(dates) // 6)
        for i in range(0, len(dates), step):
            lbl = str(dates[i])[-5:]   # "MM-DD" from "YYYY-MM-DD"
            dpg.draw_text((_px(i) - 14, GH - PAD_B + 4), lbl,
                          color=(*C["txt_dim"][:3], 140), size=9, parent=dl)

        # Axes
        dpg.draw_line((PAD_L, PAD_T), (PAD_L, PAD_T + ph),
                      color=(*C["rule_dark"][:3], 140), thickness=1, parent=dl)
        dpg.draw_line((PAD_L, PAD_T + ph), (PAD_L + pw, PAD_T + ph),
                      color=(*C["rule_dark"][:3], 140), thickness=1, parent=dl)

    dpg.add_spacer(height=6)
    dpg.add_separator()


def _rw_recent_form(r):
    """Last 10 matches table."""
    matches = r.get("matches", [])
    if not matches:
        return
    dpg.add_spacer(height=8)
    form_state = r.get("form_state", "MIXED")
    form_col = {
        "HOT":   (200, 100,  60),
        "COLD":  ( 80, 130, 200),
        "MIXED": C["txt2"][:3],
    }.get(form_state, C["txt2"][:3])
    _rw_label(f"RECENT FORM — {form_state}", color=form_col)
    dpg.add_spacer(height=4)

    hdrs   = ["#", "RES", "CHAMPION",    "ROLE", "KDA",  "CS/M", "DAMAGE", "GOLD", "TIME"]
    widths = [24,   40,    118,           46,     60,     46,     76,       72,     52]

    with dpg.child_window(height=226, border=True,
                          no_scroll_with_mouse=False):
        with dpg.group(horizontal=True):
            dpg.add_spacer(width=6)
            for h, w in zip(hdrs, widths):
                t = dpg.add_text(h, color=C["txt_dim"][:3])
                if "raj_sb_14" in _F: dpg.bind_item_font(t, _F["raj_sb_14"])
                dpg.add_spacer(width=max(2, w - len(h)*7))
        dpg.add_separator()
        for idx, m in enumerate(matches[:10]):
            res = str(m.get("result", "")).upper()
            wl_col = C["win"][:3] if res == "W" else \
                     C["loss"][:3] if res == "L" else C["txt_dim"][:3]
            vals = [
                str(idx + 1),
                res,
                str(m.get("champion", ""))[:12],
                str(m.get("role", ""))[:4],
                str(m.get("kda_str", m.get("kda", ""))),
                str(m.get("cs_min", "")),
                str(m.get("damage", "")),
                str(m.get("gold", "")),
                str(m.get("duration", "")),
            ]
            with dpg.group(horizontal=True):
                dpg.add_spacer(width=6)
                for i2, (v, w) in enumerate(zip(vals, widths)):
                    col = C["txt_dim"][:3] if i2 == 0 \
                        else wl_col         if i2 == 1 \
                        else C["gold"][:3]  if i2 == 2 \
                        else C["txt"][:3]
                    t = dpg.add_text(str(v)[:12], color=col)
                    if "raj_r_14" in _F: dpg.bind_item_font(t, _F["raj_r_14"])
                    dpg.add_spacer(width=max(2, w - len(str(v))*7))
    dpg.add_spacer(height=8)
    dpg.add_separator()


def _rw_role_breakdown(r):
    """Role breakdown with horizontal bars."""
    roles = r.get("roles", [])
    if not roles:
        return
    dpg.add_spacer(height=8)
    _rw_label("ROLE BREAKDOWN")
    dpg.add_spacer(height=6)

    role_col = {
        "TOP": (180,100,60), "JGL": (80,160,80),
        "MID": (100,120,200), "BOT": (180,160,60), "SUP": (100,180,180),
    }
    BAR_W = 200
    for row in roles:
        role = str(row.get("role", "")).upper()
        pct_str = str(row.get("pct", "0")).replace("%", "")
        try:    pct = float(pct_str) / 100.0
        except: pct = 0.0
        games = str(row.get("games", ""))
        champs = str(row.get("top_champs", ""))
        rc = role_col.get(role, (120,120,120))

        with dpg.group(horizontal=True):
            dpg.add_spacer(width=14)
            t = dpg.add_text(f"{role:<3}", color=rc)
            if "raj_sb_14" in _F: dpg.bind_item_font(t, _F["raj_sb_14"])
            dpg.add_spacer(width=8)
            # Bar via progress bar widget
            dpg.add_progress_bar(default_value=pct, width=BAR_W, height=14,
                                 overlay=f"{pct_str}%  {games}g")
            dpg.add_spacer(width=8)
            if champs:
                tc = dpg.add_text(champs[:30], color=C["txt_dim"][:3])
                if "raj_r_14" in _F: dpg.bind_item_font(tc, _F["raj_r_14"])
        dpg.add_spacer(height=4)
    dpg.add_spacer(height=4)
    dpg.add_separator()


def _rw_full_champ_pool(r):
    """Full champion pool from the scout sheet (all ranked champions)."""
    pool = r.get("champ_pool_full", [])
    if not pool:
        # Fallback to top_champs pills if no full pool available
        _rw_top_champs(r)
        return
    dpg.add_spacer(height=8)
    _rw_label("CHAMPION POOL")
    dpg.add_spacer(height=4)

    hdrs   = ["CHAMPION",  "G",  "W-L",  "W/R",  "KDA",  "CS/M",  "DMG"]
    widths = [120,          34,   54,      50,      50,     46,      70]

    with dpg.child_window(height=min(240, len(pool)*22 + 36),
                          border=True, no_scroll_with_mouse=False):
        with dpg.group(horizontal=True):
            dpg.add_spacer(width=6)
            for h, w in zip(hdrs, widths):
                t = dpg.add_text(h, color=C["txt_dim"][:3])
                if "raj_sb_14" in _F: dpg.bind_item_font(t, _F["raj_sb_14"])
                dpg.add_spacer(width=max(2, w - len(h)*7))
        dpg.add_separator()
        for ch in pool:
            wr_str = str(ch.get("wr","")).replace("%","")
            try:    wr_f = float(wr_str)
            except: wr_f = 50.0
            wrc = C["win"][:3] if wr_f >= 52 else C["loss"][:3] if wr_f < 48 else C["txt"][:3]
            wl  = f"{ch.get('wins','')}–{ch.get('losses','')}"
            vals = [ch.get("name",""), str(ch.get("games","")), wl,
                    f"{wr_str}%", str(ch.get("kda","")),
                    str(ch.get("cs_min","")), str(ch.get("damage",""))]
            with dpg.group(horizontal=True):
                dpg.add_spacer(width=6)
                for i2, (v, w) in enumerate(zip(vals, widths)):
                    col = C["gold"][:3] if i2 == 0 \
                        else wrc         if i2 == 3 \
                        else C["txt"][:3]
                    t = dpg.add_text(str(v)[:14], color=col)
                    if "raj_r_14" in _F: dpg.bind_item_font(t, _F["raj_r_14"])
                    dpg.add_spacer(width=max(2, w - len(str(v))*7))
    dpg.add_spacer(height=8)
    dpg.add_separator()


def _rw_ban_impact(r):
    """Ban impact score card."""
    bi = r.get("ban_impact")
    if not bi:
        return
    text = str(bi.get("text", "")).strip()
    wr   = str(bi.get("wr", ""))
    if not text:
        return
    dpg.add_spacer(height=8)
    _rw_label("BAN IMPACT", color=C["loss"][:3])
    dpg.add_spacer(height=4)
    with dpg.group(horizontal=True):
        dpg.add_spacer(width=14)
        with dpg.child_window(width=-1, height=46, border=True,
                              no_scrollbar=True, no_scroll_with_mouse=True):
            dpg.add_spacer(height=4)
            t1 = dpg.add_text(text, color=C["loss"][:3])
            if "raj_r_14" in _F: dpg.bind_item_font(t1, _F["raj_r_14"])
            if wr:
                t2 = dpg.add_text(f"Remaining WR if banned: {wr}",
                                  color=C["txt2"][:3])
                if "raj_r_14" in _F: dpg.bind_item_font(t2, _F["raj_r_14"])
    dpg.add_spacer(height=8)
    dpg.add_separator()


def _rw_inhouse(r):
    champs = r.get("inhouse_champs", [])
    dpg.add_spacer(height=8)
    _rw_label("INHOUSE CUSTOM GAMES", color=C["rift_purple"][:3])
    dpg.add_spacer(height=6)
    if not champs:
        t = dpg.add_text("  No inhouse champion data recorded yet.", color=C["txt_dim"][:3])
        if "raj_r_14" in _F: dpg.bind_item_font(t, _F["raj_r_14"])
        dpg.add_spacer(height=8)
        return
    hdrs = ["CHAMPION", "G", "W-L", "W/R", "KDA", "AVG DMG"]
    with dpg.group(horizontal=True):
        dpg.add_spacer(width=14)
        widths = [120, 40, 60, 60, 60, 90]
        for h, w in zip(hdrs, widths):
            t = dpg.add_text(h, color=C["txt_dim"][:3])
            if "raj_sb_14" in _F: dpg.bind_item_font(t, _F["raj_sb_14"])
            dpg.add_spacer(width=w - len(h) * 7)
    dpg.add_separator()
    for ch in champs:
        wl  = f"{ch['wins']}-{ch['losses']}"
        wr_str = str(ch["wr"])
        try:    wr_f = float(wr_str.replace("%",""))
        except Exception: wr_f = 50.0
        wrc = C["win"][:3] if wr_f >= 50 else C["loss"][:3]
        vals = [ch["name"], str(ch["games"]), wl, wr_str, str(ch["kda"]), str(ch.get("damage","—"))]
        with dpg.group(horizontal=True):
            dpg.add_spacer(width=14)
            for i, (v, w) in enumerate(zip(vals, [120, 40, 60, 60, 60, 90])):
                col = C["rift_purple"][:3] if i==0 else wrc if i==3 else C["txt"][:3]
                t = dpg.add_text(v, color=col)
                if "raj_r_14" in _F: dpg.bind_item_font(t, _F["raj_r_14"])
                dpg.add_spacer(width=max(4, w - len(str(v)) * 7))
    dpg.add_spacer(height=16)


# ---------------------------------------------------------------------------
# Report window management
# ---------------------------------------------------------------------------

def _report_panel_pos(vw):
    """Return (viewport_x, viewport_y, width, height) for the report panel."""
    table_end = int(vw * TABLE_FRAC) + PAD
    rw = vw - table_end
    rx = SIDEBAR_W + table_end
    return rx, APP_TITLE_H, rw, None  # height handled by configure_item


def _rebuild_report_window(vw, vh):
    if dpg.does_item_exist(_REPORT_WIN):
        dpg.delete_item(_REPORT_WIN)

    rx, ry, rw, _ = _report_panel_pos(vw)
    r = scout.current_report

    with dpg.window(tag=_REPORT_WIN,
                    pos=(rx, ry),
                    width=rw, height=vh,
                    no_title_bar=True, no_resize=True,
                    no_move=True, no_focus_on_appearing=True):

        if r is None and not scout.report_loading:
            dpg.add_spacer(height=60)
            t = dpg.add_text("← Select a player to view their scouting report",
                             color=C["txt_dim"][:3])
            if "raj_r_14" in _F: dpg.bind_item_font(t, _F["raj_r_14"])
            return

        # Loading indicator shown in header area while sheet fetch is pending
        if scout.report_loading and r is None:
            dpg.add_spacer(height=60)
            t = dpg.add_text("Fetching scouting report…", color=C["gold_dk"][:3])
            if "raj_r_14" in _F: dpg.bind_item_font(t, _F["raj_r_14"])
            return

        if r is None:
            return

        _rw_header(r)

        # Sheet fetch status banner
        if scout.report_loading:
            with dpg.group(horizontal=True):
                dpg.add_spacer(width=14)
                t = dpg.add_text("  Loading detailed report from sheet...",
                                 color=C["gold_dk"][:3])
                if "raj_r_14" in _F: dpg.bind_item_font(t, _F["raj_r_14"])
            dpg.add_spacer(height=4)
        elif r.get("sheet_error"):
            err_msg      = str(r["sheet_error"])
            is_missing   = "No scouting sheet" in err_msg
            banner_col   = C["gold_dk"][:3] if is_missing else C["loss"][:3]
            with dpg.group(horizontal=True):
                dpg.add_spacer(width=14)
                with dpg.child_window(width=-1, height=52, border=True,
                                      no_scrollbar=True, no_scroll_with_mouse=True):
                    if is_missing:
                        t = dpg.add_text("  No scout sheet for this player.",
                                         color=banner_col)
                        if "raj_r_14" in _F: dpg.bind_item_font(t, _F["raj_r_14"])
                        t2 = dpg.add_text(
                            "  Run 'RUN SCOUT' from the Commands tab to generate it.",
                            color=C["txt_dim"][:3])
                        if "raj_r_12" in _F: dpg.bind_item_font(t2, _F["raj_r_12"])
                    else:
                        t = dpg.add_text(f"  Sheet error: {err_msg[:90]}",
                                         color=banner_col)
                        if "raj_r_14" in _F: dpg.bind_item_font(t, _F["raj_r_14"])
            dpg.add_spacer(height=6)

        _rw_power_rating(r)
        _rw_overview(r)
        _rw_rank_history(r)
        _rw_ban_impact(r)
        _rw_ban_targets(r)
        _rw_full_champ_pool(r)
        _rw_role_breakdown(r)
        _rw_recent_form(r)
        _rw_inhouse(r)
        dpg.add_spacer(height=24)


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
class ScoutPhase:
    IDLE           = "idle"
    LOADING        = "loading"
    REVEAL         = "reveal"
    DONE           = "done"
    LOADING_REPORT = "loading_report"   # fetching individual sheet


class ScoutState:
    def __init__(self):
        self.phase          = ScoutPhase.IDLE
        self.players        = []
        self.sort_col       = "score"
        self.sort_asc       = False
        self.selected       = None
        self.current_report = None
        self.report_dirty   = False
        self.report_loading = False   # True while background sheet fetch is in progress
        self.report_error   = None    # error string from last failed fetch
        self.row_alpha      = {}
        self.row_x_off      = {}
        self.header_alpha   = 0
        self._load_t        = 0.0

    def reset(self):
        self.__init__()

    def tick(self):
        self._load_t += 0.04

    def begin_load(self, players):
        self.reset()
        self.players = players
        self.phase   = ScoutPhase.LOADING
        anim.tween(0, 1, 1, "linear", delay_ms=1400, on_done=self._reveal)

    def _reveal(self):
        self.phase = ScoutPhase.REVEAL
        anim.tween(0, 255, 120, "out_cubic",
                   on_update=lambda v: setattr(self, "header_alpha", int(v)))
        for i, p in enumerate(self._sorted()):
            n = p["name"]
            self.row_alpha[n] = 0
            self.row_x_off[n] = -60
            def _make(name=n):
                def _x(v): self.row_x_off[name] = int(v)
                def _a(v): self.row_alpha[name]  = int(v)
                anim.tween(-60, 0,   200, "out_cubic", on_update=_x)
                anim.tween(0,   255, 200, "out_cubic", on_update=_a)
            anim.tween(0, 1, 1, "linear", delay_ms=80 + i*35, on_done=_make)
        anim.tween(0, 1, 1, "linear",
                   delay_ms=80 + len(self.players)*35 + 200,
                   on_done=lambda: setattr(self, "phase", ScoutPhase.DONE))

    def _sorted(self):
        key = self.sort_col
        return sorted(self.players, key=lambda p: p.get(key, 0), reverse=not self.sort_asc)

    def select(self, name):
        """
        Select a player. Immediately builds a fast local report from cached data,
        then kicks off a background sheet fetch for the full report.
        """
        self.selected       = name
        self.report_error   = None
        # Show local report immediately so the panel isn't blank
        self.current_report = _build_full_report(name)
        self.report_dirty   = True

        # Now fetch the rich per-player sheet in background
        self.report_loading = True
        load_scout_sheet(
            name,
            on_done  = lambda data, hist: _on_sheet_loaded(name, data, hist),
            on_error = lambda msg:        _on_sheet_error(name, msg),
        )

    def toggle_sort(self, col):
        if self.sort_col == col:
            self.sort_asc = not self.sort_asc
        else:
            self.sort_col = col
            self.sort_asc = False
        for i, p in enumerate(self._sorted()):
            n = p["name"]
            self.row_alpha[n] = 0
            self.row_x_off[n] = -40
            def _make(name=n):
                def _x(v): self.row_x_off[name] = int(v)
                def _a(v): self.row_alpha[name]  = int(v)
                anim.tween(-40, 0,   160, "out_cubic", on_update=_x)
                anim.tween(0,   255, 160, "out_cubic", on_update=_a)
            anim.tween(0, 1, 1, "linear", delay_ms=i*28, on_done=_make)


def _on_sheet_loaded(name, sheet_data, history):
    """
    Called from background thread when a player's scout sheet is parsed.
    Merges sheet data with live inhouse data and updates the report.
    Thread-safe: only mutates Python objects, no DPG calls.
    """
    if scout.selected != name:
        return  # user selected a different player while we were fetching

    # Start from the local report base (has live ranking data)
    base = _build_full_report(name) or {}

    # Overlay sheet-sourced fields
    scouted_at = sheet_data.get("scouted_at")
    if scouted_at:
        from datetime import datetime as _dt
        delta = (_dt.now() - scouted_at).days
        base["scouted_days_ago"] = delta

    # Full champion pool from sheet (replaces top_champs if available)
    if sheet_data.get("champ_pool"):
        base["champ_pool_full"] = sheet_data["champ_pool"]

    # Role breakdown
    if sheet_data.get("roles"):
        base["roles"] = sheet_data["roles"]

    # Recent matches
    if sheet_data.get("matches"):
        base["matches"] = sheet_data["matches"]
        base["form_state"] = sheet_data.get("form_state", base.get("form_state", "MIXED"))

    # Ban targets from sheet (richer: has threat label + stats)
    if sheet_data.get("must_bans"):
        sheet_bans = []
        for b in sheet_data["must_bans"]:
            threat = str(b.get("threat", "")).upper()
            if threat in ("HIGH", "PERMABAN", "ELEVATED"):
                sheet_bans.append({
                    "name":   b["name"],
                    "games":  b.get("games", ""),
                    "wr":     b.get("wr", ""),
                    "kda":    b.get("kda", ""),
                    "threat": threat,
                })
        if sheet_bans:
            base["ban_targets"] = sheet_bans

    # Ban impact score
    if sheet_data.get("ban_impact"):
        base["ban_impact"] = sheet_data["ban_impact"]

    # Rank history (for the graph)
    base["rank_history"] = history

    scout.current_report  = base
    scout.report_loading  = False
    scout.report_dirty    = True


def _on_sheet_error(name, msg):
    """Called from background thread on fetch failure — keep local report, show note."""
    if scout.selected != name:
        return
    scout.report_loading = False
    scout.report_error   = msg
    # Local report already showing; just mark it so the panel knows to show the error hint
    if scout.current_report:
        scout.current_report["sheet_error"] = msg
    scout.report_dirty = True


scout = ScoutState()
_F    = {}
def set_fonts(f): global _F; _F = f


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def _txt(dl, x, y, text, color, size, font_key=None):
    tag = dpg.draw_text((x, y), text, color=color, size=size, parent=dl)
    if font_key and font_key in _F:
        dpg.bind_item_font(tag, _F[font_key])
    return tag


def _col_xs(tw):
    xs, cur = [], 0
    for _, frac, _ in COLS:
        w = int(tw * frac)
        xs.append((cur, w))
        cur += w
    return xs


# ---------------------------------------------------------------------------
# Main draw
# ---------------------------------------------------------------------------

def draw_scout(dl, vw, vh, fonts=None):
    if fonts:
        set_fonts(fonts)
    scout.tick()
    dpg.delete_item(dl, children_only=True)
    dpg.draw_rectangle((0,0),(vw,vh), fill=C["bg"], color=(0,0,0,0), parent=dl)

    if scout.phase == ScoutPhase.IDLE:
        _draw_idle(dl, vw, vh); return
    if scout.phase == ScoutPhase.LOADING:
        _draw_loading(dl, vw, vh); return

    table_w = int(vw * TABLE_FRAC)

    _draw_top_bar(dl, vw)
    _draw_table(dl, PAD, TOP_BAR_H + PAD, table_w - PAD*2, vh - TOP_BAR_H - PAD*2, vw, vh)

    # Report panel — create once, rebuild when dirty or loading state changes
    if not dpg.does_item_exist(_REPORT_WIN):
        _rebuild_report_window(vw, vh)
    else:
        rx, ry, rw, _ = _report_panel_pos(vw)
        dpg.configure_item(_REPORT_WIN, pos=(rx, ry), width=rw, height=vh)
        if scout.report_dirty:
            _rebuild_report_window(vw, vh)
            scout.report_dirty = False

    # Vertical divider between table and report
    dx = table_w + 1
    dpg.draw_line((dx, TOP_BAR_H),(dx, vh),
                  color=C["rule_dark"], thickness=1, parent=dl)


def _draw_idle(dl, vw, vh):
    cx, cy = vw//2, vh//2
    t  = (math.sin(time.monotonic()*1.3)+1)/2
    a  = int(90 + t*110)
    _txt(dl, cx-180, cy-30, "PLAYER SCOUTING", (*C["gold"][:3],a), 36, "raj_36")
    _txt(dl, cx-160, cy+14, "Fetch latest data to begin", (*C["txt_dim"][:3],int(a*.6)), 18, "raj_18")
    bw, bh = 300, 60
    bx, by = cx-bw//2, cy+56
    dpg.draw_rectangle((bx,by),(bx+bw,by+bh), fill=(*C["gold_dk"][:3],210),
                        color=(*C["gold"][:3],210), rounding=6, parent=dl)
    _txt(dl, bx+bw//2-110, by+16, "LOAD SCOUT DATA", (*C["gold_lt"][:3],230), 22, "raj_24")
    if dpg.is_mouse_button_clicked(0):
        mouse = dpg.get_mouse_pos(local=False)
        vp    = dpg.get_viewport_pos()
        rx = mouse[0]-vp[0]-68; ry = mouse[1]-vp[1]-52
        if bx<=rx<=bx+bw and by<=ry<=by+bh:
            if live.loaded and live.scout:
                scout.begin_load(live.scout)
            else:
                scout.begin_load([])


def _draw_loading(dl, vw, vh):
    cx, cy = vw//2, vh//2
    t  = (math.sin(scout._load_t*2.0)+1)/2
    a  = int(80 + t*130)
    _txt(dl, cx-180, cy-14, "FETCHING SCOUT DATA...", (*C["gold_dk"][:3],a), 20, "raj_20")


def _draw_top_bar(dl, vw):
    dpg.draw_rectangle((0,0),(vw,TOP_BAR_H), fill=(*C["panel"][:3],220), color=(0,0,0,0), parent=dl)
    dpg.draw_line((0,TOP_BAR_H-1),(vw,TOP_BAR_H-1), color=C["rule_dark"], thickness=1, parent=dl)
    _txt(dl, PAD, 14, "PLAYER SCOUTING", (*C["gold"][:3],220), 22, "raj_24")

    labels = [("SCORE","score"),("W/R","wr"),("KDA","kda")]
    bx = vw - 340
    for lbl, col_key in labels:
        active = scout.sort_col == col_key
        bc = C["gold"] if active else C["rule_dark"]
        fc = (*C["gold_dk"][:3],200) if active else (0,0,0,0)
        dpg.draw_rectangle((bx,10),(bx+90,TOP_BAR_H-10),
                            fill=fc, color=(*bc[:3],200), rounding=4, parent=dl)
        arr  = ("▲" if scout.sort_asc else "▼") if active else ""
        tcol = C["gold_lt"] if active else C["txt"]
        _txt(dl, bx+8, 18, lbl+arr, (*tcol[:3],220), 16, "raj_18")
        bx += 100

    if dpg.is_mouse_button_clicked(0):
        mouse = dpg.get_mouse_pos(local=False)
        vp    = dpg.get_viewport_pos()
        rx = mouse[0]-vp[0]-68; ry = mouse[1]-vp[1]-52
        if 10 <= ry <= TOP_BAR_H-10:
            bx2 = vw - 340
            for _, c2 in labels:
                if bx2 <= rx <= bx2+90:
                    scout.toggle_sort(c2); break
                bx2 += 100


def _draw_table(dl, tx, ty, tw, th, vw, vh):
    players  = scout._sorted()
    col_xs   = _col_xs(tw)
    ha       = scout.header_alpha

    # Column headers
    dpg.draw_rectangle((tx,ty),(tx+tw,ty+HEADER_H),
                        fill=(*C["card"][:3],ha), color=(*C["rule_dark"][:3],ha), rounding=4, parent=dl)
    for (lbl,_,sk),(cx,cw) in zip(COLS, col_xs):
        active = sk and scout.sort_col == sk
        col    = C["gold"] if active else C["txt_dim"]
        _txt(dl, tx+cx+8, ty+HEADER_H//2-10, lbl, (*col[:3],ha), 14, "raj_sb_16")
    dpg.draw_line((tx,ty+HEADER_H),(tx+tw,ty+HEADER_H),
                  color=(*C["rule_dark"][:3],ha), thickness=1, parent=dl)

    row_y = ty + HEADER_H + 4

    for i, p in enumerate(players):
        n  = p["name"]
        al = scout.row_alpha.get(n, 0)
        xo = scout.row_x_off.get(n, -60)
        if al <= 0:
            continue
        ry  = row_y + i*(ROW_H+3)
        is_sel = scout.selected == n
        if is_sel:
            bg = (*C["card_hover"][:3], al)
        elif i % 2 == 0:
            bg = (*C["card"][:3], al)
        else:
            bg = (*C["panel"][:3], al)
        dpg.draw_rectangle((tx+xo,ry),(tx+tw+xo,ry+ROW_H),
                            fill=bg, color=(0,0,0,0), rounding=3, parent=dl)
        if is_sel:
            dpg.draw_rectangle((tx+xo,ry),(tx+xo+4,ry+ROW_H),
                                fill=(*C["gold"][:3],al), color=(0,0,0,0), rounding=2, parent=dl)

        tier = p.get("tier","Unranked")
        bc   = RANK_COLORS.get(tier, RANK_COLORS["Unranked"])
        try:    score_disp = str(int(float(p["score"])))
        except Exception: score_disp = str(p.get("score","?"))

        vals = [
            str(i+1),
            p["name"],
            score_disp,
            f"{p.get('wr',0)}%",
            f"{p.get('kda',0.0):.1f}",
            str(p.get("games",0)),
        ]

        for ci, (val, (cx, cw)) in enumerate(zip(vals, col_xs)):
            vx = tx + xo + cx + 8
            vy = ry + ROW_H//2 - 10
            if ci == 0:
                _txt(dl, vx, vy, val, (*C["txt_dim"][:3],al), 15, "raj_18")
            elif ci == 1:
                dpg.draw_circle((vx+5,ry+ROW_H//2),7, fill=(*bc[:3],al), color=(0,0,0,0), parent=dl)
                _txt(dl, vx+18, vy, val.upper(), (*C["gold_lt"][:3],al), 17, "raj_20")
            elif ci == 2:
                _txt(dl, vx, vy, val, (*C["gold"][:3],al), 17, "raj_20")
            elif ci == 3:
                wr_v  = p.get("wr",50)
                wrc   = C["win"] if wr_v>=52 else C["loss"] if wr_v<48 else C["txt"]
                _txt(dl, vx, vy, val, (*wrc[:3],al), 15, "raj_18")
            elif ci == 4:
                _txt(dl, vx, vy, val, (*C["platinum"][:3],al), 15, "raj_18")
            else:
                _txt(dl, vx, vy, val, (*C["txt2"][:3],al), 14, "raj_16")

    # Click anywhere on a row to open the report
    if dpg.is_mouse_button_clicked(0):
        mouse = dpg.get_mouse_pos(local=False)
        vp    = dpg.get_viewport_pos()
        rx2   = mouse[0] - vp[0] - 68
        ry2   = mouse[1] - vp[1] - 52

        for i, p in enumerate(players):
            n  = p["name"]
            al = scout.row_alpha.get(n, 0)
            if al <= 0:
                continue
            row_top = row_y + i*(ROW_H+3)
            if tx <= rx2 <= tx+tw and row_top <= ry2 <= row_top+ROW_H:
                scout.select(n)
                break
