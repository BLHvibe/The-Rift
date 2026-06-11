"""
Scout Tab — Phase 4 (revamp).
Left: sortable player table.  Right: inline scouting report panel.
Clicking any row loads the full report in the right panel.
"""
import math, time, random as _rnd
import dearpygui.dearpygui as dpg
from theme import C, RANK_COLORS, MEDAL_PARTICLE
from core.animations import anim
from data.reader import live, load_scout_sheet, cache_scout_sheet
from data.tips import TIPS as _TIPS
from ui.tierlist import _wheel_delta as _wheel_delta_shared
from ui import effects
from ui import luxe

# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------
TOP_BAR_H   = 56
PAD         = 20
TABLE_FRAC  = 0.38   # player table takes 38% of content width
ROW_H       = 60     # increased from 52 for readability
HEADER_H    = 48
SIDEBAR_W   = 68
APP_TITLE_H = 52

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

    ih_champs   = live.inhouse_champs.get(name, [])
    top_champs  = p.get("top_champs", [])

    # ── Ban targets: inhouse champs + ranked/draft danger picks ──────────
    ban_targets = []
    seen_bans   = set()

    # 1. Inhouse champions (most reliable threat data)
    for ch in sorted(ih_champs, key=lambda x: -x.get("games", 0)):
        cg      = ch.get("games", 0)
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
        cname = ch["champ"]
        seen_bans.add(cname)
        ban_targets.append({
            "name": cname, "games": cg,
            "wr": f"{cwr:.0f}%", "kda": ckda,
            "threat": threat, "source": "inhouse",
        })
        if len(ban_targets) >= 5:
            break

    # 2. Ranked/draft danger picks — top_champs not yet in ban list
    for i, champ in enumerate(top_champs[:5]):
        if not champ or champ in seen_bans:
            continue
        if len(ban_targets) >= 5:
            break
        # Threat level based on champion mastery position (1st = highest threat)
        threat = "HIGH" if i == 0 else "ELEVATED"
        seen_bans.add(champ)
        ban_targets.append({
            "name": champ, "games": "—",
            "wr": "ranked", "kda": "—",
            "threat": threat, "source": "ranked",
        })

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
        "form":           form,
        "ban_targets":    ban_targets,
        "top_champs":     top_champs,
        "inhouse_champs": inhouse_display,
        # Phase 3 — raw stats preserved for the auto-tag computer so it
        # never has to re-parse a display string.
        "wr_raw":         wr,
        "kda_raw":        kda,
        "games_raw":      games,
        "primary_role":   p.get("primary_role"),
    }


# ---------------------------------------------------------------------------
# Phase 3 — auto player tags
# ---------------------------------------------------------------------------

def _safe_float(v, default=0.0):
    try: return float(str(v).replace("%", "").replace(",", ""))
    except (TypeError, ValueError): return default


def _safe_int(v, default=0):
    try: return int(float(str(v).replace(",", "")))
    except (TypeError, ValueError): return default


def _compute_player_tags(r):
    """Phase 3 — derive at-a-glance behavior tags from a scout report dict.
    Pure function: takes the report `r`, returns a list of
    {label, color, kind} dicts ordered most-interesting first.

    Tags are deterministic and use absolute thresholds — no cross-player
    normalization needed, so they work for a player even before the rest
    of the scout corpus has loaded.
    """
    tags = []
    if not r:
        return tags

    # ── Form ────────────────────────────────────────────────────────────
    form = str(r.get("form_state") or r.get("form") or "MIXED").upper()
    if form == "HOT":
        tags.append({"label": "HOT FORM",
                     "color": (79, 168, 130), "kind": "form"})
    elif form == "COLD":
        tags.append({"label": "COLD STREAK",
                     "color": (200, 80, 80), "kind": "form"})
    elif form == "MIXED":
        tags.append({"label": "MIXED FORM",
                     "color": (170, 170, 170), "kind": "form"})

    games = _safe_int(r.get("games_raw"))
    if games == 0:
        games = sum(_safe_int(c.get("games"))
                    for c in (r.get("inhouse_champs") or []))

    # ── Experience ──────────────────────────────────────────────────────
    if games >= 150:
        tags.append({"label": "VETERAN",
                     "color": (90, 170, 220), "kind": "experience"})
    elif games >= 40:
        tags.append({"label": "ACTIVE",
                     "color": (200, 180, 120), "kind": "experience"})
    elif games > 0:
        tags.append({"label": "NEWCOMER",
                     "color": (180, 140, 220), "kind": "experience"})

    # ── Mastery (OTP vs Versatile) ──────────────────────────────────────
    pool = r.get("champ_pool_full") or r.get("inhouse_champs") or []
    per_champ = []
    for entry in pool:
        ch_name = entry.get("champ") or entry.get("name") or "?"
        per_champ.append((ch_name, _safe_int(entry.get("games"))))
    per_champ.sort(key=lambda x: -x[1])
    total_pool = sum(g for _, g in per_champ)
    if total_pool >= 10 and per_champ:
        top_name, top_games = per_champ[0]
        if top_games >= 8 and top_games / total_pool >= 0.40:
            tags.append({"label": f"OTP — {top_name.upper()}",
                         "color": (220, 180, 80), "kind": "mastery"})
        elif sum(1 for _, g in per_champ if g >= 5) >= 5:
            tags.append({"label": "VERSATILE",
                         "color": (110, 200, 200), "kind": "mastery"})

    # ── KDA monster ─────────────────────────────────────────────────────
    kda = _safe_float(r.get("kda_raw"))
    if kda >= 5.0:
        tags.append({"label": "KDA GOD",
                     "color": (130, 220, 130), "kind": "stat"})
    elif kda >= 4.0:
        tags.append({"label": "KDA MONSTER",
                     "color": (130, 210, 130), "kind": "stat"})

    # ── Win-rate persona (requires meaningful sample) ───────────────────
    wr = _safe_float(r.get("wr_raw"))
    if games >= 20:
        if wr >= 60:
            tags.append({"label": "WIN MACHINE",
                         "color": (79, 168, 130), "kind": "stat"})
        elif wr <= 42:
            tags.append({"label": "SLUMPING",
                         "color": (200, 120, 80), "kind": "warning"})

    # ── Role main ───────────────────────────────────────────────────────
    role = str(r.get("primary_role") or "").upper()
    role_label = {"TOP": "TOP",  "JGL": "JUNGLE", "JUNGLE": "JUNGLE",
                  "MID": "MID",  "BOT": "ADC", "BOTTOM": "ADC",
                  "SUP": "SUPPORT", "SUPPORT": "SUPPORT"}.get(role)
    if role_label:
        tags.append({"label": f"{role_label} MAIN",
                     "color": (210, 165, 230), "kind": "role"})

    return tags


# ---------------------------------------------------------------------------
# Report section renderers
# ---------------------------------------------------------------------------

def _rw_label(text, font_key="raj_sb_22", color=None):
    col = color or C["gold_lt"][:3]
    t = dpg.add_text(text, color=col)
    if font_key in _F:
        dpg.bind_item_font(t, _F[font_key])
    elif "raj_sb_18" in _F:
        dpg.bind_item_font(t, _F["raj_sb_18"])


def _rw_compare(r):
    """Phase 3 (polished) — side-by-side compare. Renders a broadcast-style
    head-to-head card: the two players framed left and right, a centered VS
    chip, six head-to-head stat rows with winner-side gold highlighting and a
    final tally chip so the user can see at-a-glance who's ahead overall."""
    me = r.get("player")
    pool = [p["name"] for p in scout.players if p["name"] != me]
    if not pool:
        return
    items = ["— none —"] + sorted(pool)
    default = scout.compare_with if scout.compare_with in pool else "— none —"

    def _on_pick(_s, value):
        scout.compare_with = None if value == "— none —" else value
        scout.report_dirty = True

    dpg.add_spacer(height=4)
    _rw_label("COMPARE")
    dpg.add_spacer(height=2)
    with dpg.group(horizontal=True):
        dpg.add_spacer(width=14)
        t = dpg.add_text("vs", color=C["txt_dim"][:3])
        if "raj_r_16" in _F: dpg.bind_item_font(t, _F["raj_r_16"])
        dpg.add_spacer(width=6)
        combo = dpg.add_combo(items=items, default_value=default,
                              width=220, callback=_on_pick)
        if "raj_r_16" in _F: dpg.bind_item_font(combo, _F["raj_r_16"])

    other = scout.compare_with
    if not other:
        dpg.add_spacer(height=4)
        dpg.add_separator()
        return

    op = next((p for p in scout.players if p["name"] == other), None)
    if not op:
        dpg.add_spacer(height=4)
        dpg.add_separator()
        return

    def _fmt_wr(v):  return f"{_safe_float(v):.0f}%"
    def _fmt_kda(v): return f"{_safe_float(v):.2f}"
    def _fmt_int(v): return f"{_safe_int(v):,}"

    # Pull champ pools for overlap.
    my_champs = [c.get("champ") for c in (_DEMO_CHAMPS_RW.get(me, []) or [])]
    their_champs = [c.get("champ") for c in (_DEMO_CHAMPS_RW.get(other, []) or [])]
    if not my_champs:
        my_champs = [c.get("champion") for c in (r.get("champ_pool") or [])]
    if not their_champs:
        their_champs = [c.get("champion") for c in (op.get("champ_pool") or [])]
    overlap = sorted(set(filter(None, my_champs)) &
                     set(filter(None, their_champs)))

    rows = [
        ("WIN RATE", _safe_float(r.get("wr_raw")),
                     _safe_float(op.get("wr", 0)),     True, _fmt_wr),
        ("KDA",      _safe_float(r.get("kda_raw")),
                     _safe_float(op.get("kda", 0.0)),  True, _fmt_kda),
        ("GAMES",    _safe_int(r.get("games_raw")),
                     _safe_int(op.get("games", 0)),    True, _fmt_int),
        ("SCORE",    _safe_float(r.get("score", 0)),
                     _safe_float(op.get("score", 0)),  True, _fmt_int),
    ]

    # Tally: count how many rows each side wins.
    me_wins = 0
    them_wins = 0
    for _, mine, theirs, higher_is_better, _f in rows:
        if abs(mine - theirs) < 1e-6:
            continue
        if (mine > theirs) == higher_is_better:
            me_wins += 1
        else:
            them_wins += 1

    dpg.add_spacer(height=8)
    # ── Header row: large player names + vs chip + tally chip ──
    with dpg.group(horizontal=True):
        dpg.add_spacer(width=14)
        # Me name + tally
        me_col = (200, 255, 200) if me_wins > them_wins else C["gold_lt"][:3]
        t = dpg.add_text(str(me).upper(), color=me_col)
        if "raj_sb_18" in _F: dpg.bind_item_font(t, _F["raj_sb_18"])
        dpg.add_spacer(width=6)
        tally_t = dpg.add_text(f"({me_wins})",
                                color=(*C["txt_dim"][:3], 220))
        if "raj_r_16" in _F: dpg.bind_item_font(tally_t, _F["raj_r_16"])
        dpg.add_spacer(width=20)
        # VS chip
        vs_t = dpg.add_text("VS", color=(*C["gold"][:3], 220))
        if "raj_sb_18" in _F: dpg.bind_item_font(vs_t, _F["raj_sb_18"])
        dpg.add_spacer(width=20)
        them_col = (200, 255, 200) if them_wins > me_wins else C["gold_lt"][:3]
        tally2_t = dpg.add_text(f"({them_wins})",
                                  color=(*C["txt_dim"][:3], 220))
        if "raj_r_16" in _F: dpg.bind_item_font(tally2_t, _F["raj_r_16"])
        dpg.add_spacer(width=6)
        t = dpg.add_text(str(other).upper(), color=them_col)
        if "raj_sb_18" in _F: dpg.bind_item_font(t, _F["raj_sb_18"])

    if me_wins != them_wins:
        verdict = (f"{me.upper()} edges out the comparison"
                   if me_wins > them_wins else
                   f"{other.upper()} comes out ahead")
        with dpg.group(horizontal=True):
            dpg.add_spacer(width=14)
            v = dpg.add_text(verdict, color=(*C["gold"][:3], 200))
            if "raj_r_16" in _F: dpg.bind_item_font(v, _F["raj_r_16"])
    dpg.add_spacer(height=6)

    # ── Metric rows: gold cell on the winner side ──
    for lbl, mine, theirs, higher_is_better, formatter in rows:
        if abs(mine - theirs) < 1e-6:
            me_color = C["txt"][:3]
            them_color = C["txt"][:3]
        elif (mine > theirs) == higher_is_better:
            me_color = (130, 210, 130)
            them_color = (200, 130, 130)
        else:
            me_color = (200, 130, 130)
            them_color = (130, 210, 130)
        with dpg.group(horizontal=True):
            dpg.add_spacer(width=14)
            t = dpg.add_text(formatter(mine), color=me_color)
            if "raj_sb_18" in _F: dpg.bind_item_font(t, _F["raj_sb_18"])
            dpg.add_spacer(width=max(8, 80 - len(formatter(mine)) * 6))
            t = dpg.add_text(lbl, color=(*C["txt_dim"][:3], 220))
            if "raj_sb_14" in _F: dpg.bind_item_font(t, _F["raj_sb_14"])
            dpg.add_spacer(width=max(8, 80 - len(lbl) * 5))
            t = dpg.add_text(formatter(theirs), color=them_color)
            if "raj_sb_18" in _F: dpg.bind_item_font(t, _F["raj_sb_18"])

    # ── Champion pool overlap ──
    if overlap:
        dpg.add_spacer(height=8)
        with dpg.group(horizontal=True):
            dpg.add_spacer(width=14)
            t = dpg.add_text("SHARED POOL", color=(*C["gold"][:3], 200))
            if "raj_sb_14" in _F: dpg.bind_item_font(t, _F["raj_sb_14"])
            dpg.add_spacer(width=10)
            t = dpg.add_text("  ·  ".join(overlap[:6]),
                              color=C["txt"][:3])
            if "raj_r_16" in _F: dpg.bind_item_font(t, _F["raj_r_16"])
    else:
        dpg.add_spacer(height=4)
        with dpg.group(horizontal=True):
            dpg.add_spacer(width=14)
            t = dpg.add_text("no shared champion pool",
                              color=(*C["txt_dim"][:3], 180))
            if "raj_r_14" in _F: dpg.bind_item_font(t, _F["raj_r_14"])

    dpg.add_spacer(height=10)
    dpg.add_separator()


# Lazy alias: in scout.py the per-player champion pool is held externally
# (this module reaches for it on demand); we keep this hook so the compare
# section can ask for it without a hard cross-module dependency.
_DEMO_CHAMPS_RW = {}


def _rw_player_tags(r):
    """Phase 3 — at-a-glance behavior tags (Porofessor-style) computed from
    the player's stats + champ pool + form. Renders a single horizontal row
    of color-coded labels separated by a thin gold dot."""
    tags = _compute_player_tags(r)
    if not tags:
        return
    dpg.add_spacer(height=4)
    _rw_label("PLAYER TAGS")
    dpg.add_spacer(height=2)
    with dpg.group(horizontal=True):
        dpg.add_spacer(width=14)
        for i, tag in enumerate(tags):
            if i > 0:
                dot = dpg.add_text("·", color=(120, 100, 60))
                if "raj_r_16" in _F:
                    dpg.bind_item_font(dot, _F["raj_r_16"])
                dpg.add_spacer(width=4)
            t = dpg.add_text(tag["label"], color=tag["color"])
            if "raj_sb_16" in _F:
                dpg.bind_item_font(t, _F["raj_sb_16"])
            if i < len(tags) - 1:
                dpg.add_spacer(width=4)
    dpg.add_spacer(height=6)
    dpg.add_separator()


def _rw_header(r):
    """Broadcast-style scout-report header: large avatar + name, tier ribbon,
    and a row of headline KPI chips (Score, WR, KDA, Games) so the most-asked
    questions about a player are answered before scrolling."""
    from ui.inhouse import _get_avatar_tex, _flush_pending
    _flush_pending()

    dpg.add_spacer(height=10)
    with dpg.group(horizontal=True):
        dpg.add_spacer(width=14)

        tex = _get_avatar_tex(r["player"])
        if tex:
            dpg.add_image(tex, width=80, height=80)
            dpg.add_spacer(width=16)

        with dpg.group():
            t = dpg.add_text(r["player"].upper(), color=C["gold_lt"][:3])
            if "raj_36" in _F: dpg.bind_item_font(t, _F["raj_36"])
            with dpg.group(horizontal=True):
                bc = RANK_COLORS.get(r["tier"], RANK_COLORS["Unranked"])
                t2 = dpg.add_text(r["tier"].upper(), color=bc[:3])
                if "raj_sb_22" in _F: dpg.bind_item_font(t2, _F["raj_sb_22"])
                elif "raj_sb_18" in _F: dpg.bind_item_font(t2, _F["raj_sb_18"])
                dpg.add_spacer(width=14)
                rl = r.get("primary_role")
                if rl:
                    rt = dpg.add_text(f"·  {rl.upper()} MAIN",
                                       color=(*C["txt2"][:3], 220))
                    if "raj_sb_18" in _F: dpg.bind_item_font(rt, _F["raj_sb_18"])
                    dpg.add_spacer(width=14)
                days = r.get("scouted_days_ago", None)
                if days is not None:
                    ac = (79,168,130) if days<=2 else (200,168,106) if days<=6 else (184,69,53)
                    ta = dpg.add_text(f"Scouted {days}d ago", color=ac)
                else:
                    ta = dpg.add_text("Live data", color=(79,168,130))
                if "raj_r_16" in _F: dpg.bind_item_font(ta, _F["raj_r_16"])

    # ── Headline KPI chips ───────────────────────────────────────────────
    dpg.add_spacer(height=12)
    wr_f = _safe_float(r.get("wr_raw"))
    kda_f = _safe_float(r.get("kda_raw"))
    games_n = _safe_int(r.get("games_raw"))
    score_n = _safe_int(r.get("score"))
    chips = [
        ("SCORE",   f"{score_n:,}",     C["gold_lt"][:3]),
        ("WIN %",   f"{wr_f:.0f}%",
                    (130, 210, 130) if wr_f >= 52 else
                    (220, 130, 130) if wr_f < 48 else C["txt"][:3]),
        ("KDA",     f"{kda_f:.2f}",
                    (130, 210, 130) if kda_f >= 3.5 else
                    (220, 130, 130) if kda_f < 1.8 else C["txt"][:3]),
        ("GAMES",   f"{games_n:,}",    C["txt"][:3]),
    ]
    with dpg.group(horizontal=True):
        dpg.add_spacer(width=14)
        for label, val, col in chips:
            with dpg.child_window(width=128, height=88, border=True,
                                   no_scrollbar=True,
                                   no_scroll_with_mouse=True):
                dpg.add_spacer(height=4)
                lt = dpg.add_text(f"  {label}", color=(*C["txt_dim"][:3], 220))
                if "raj_sb_14" in _F: dpg.bind_item_font(lt, _F["raj_sb_14"])
                vt = dpg.add_text(f"  {val}", color=col)
                if "raj_36" in _F: dpg.bind_item_font(vt, _F["raj_36"])
            dpg.add_spacer(width=8)
    dpg.add_spacer(height=10)
    dpg.add_separator()


def _rw_power_rating(r):
    dpg.add_spacer(height=8)
    _rw_label("POWER RATING")
    dpg.add_spacer(height=6)
    rating_colors = {
        "S":(210,40,40),"A":(200,155,60),"B":(160,136,78),
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
            if "raj_r_16" in _F: dpg.bind_item_font(t4, _F["raj_r_16"])
    dpg.add_spacer(height=8)
    dpg.add_separator()


def _rw_overview(r):
    dpg.add_spacer(height=8)
    _rw_label("OVERVIEW")
    dpg.add_spacer(height=8)
    with dpg.group(horizontal=True):
        dpg.add_spacer(width=PAD)
        for lbl, val in r["overview"]:
            with dpg.group():
                lt = dpg.add_text(lbl, color=C["txt2"][:3])
                if "raj_sb_18" in _F: dpg.bind_item_font(lt, _F["raj_sb_18"])
                dpg.add_spacer(height=4)
                # Color-code win rate
                if lbl == "Win Rate":
                    try:
                        wr_n = float(str(val).replace("%",""))
                        vcol = C["win"][:3] if wr_n>=52 else C["loss"][:3] if wr_n<48 else C["txt"][:3]
                    except Exception:
                        vcol = C["txt"][:3]
                elif lbl == "Form":
                    form_colors = {"HOT":(220,110,60),"COLD":(80,140,220),"MIXED":C["txt"][:3]}
                    vcol = form_colors.get(str(val).upper(), C["txt"][:3])
                else:
                    vcol = C["gold_lt"][:3]
                vt = dpg.add_text(val, color=vcol)
                if "raj_28" in _F: dpg.bind_item_font(vt, _F["raj_28"])
            dpg.add_spacer(width=36)
    dpg.add_spacer(height=8)
    dpg.add_separator()


def _rw_ban_targets(r):
    dpg.add_spacer(height=8)
    _rw_label("BAN TARGETS")
    dpg.add_spacer(height=6)
    bans = r.get("ban_targets", [])
    if not bans:
        t = dpg.add_text("  No high-threat picks identified.",
                         color=C["txt_dim"][:3])
        if "raj_r_16" in _F: dpg.bind_item_font(t, _F["raj_r_16"])
        dpg.add_spacer(height=8)
        dpg.add_separator()
        return

    threat_col = {
        "PERMABAN": C["loss"][:3],
        "HIGH":     C["gold"][:3],
        "ELEVATED": C["txt2"][:3],
    }
    source_col = {
        "inhouse": (175, 110, 220),   # readable violet on the navy table
        "ranked":  C["platinum"][:3],
    }
    # Fixed pixel column widths — consistent regardless of content length
    hdrs   = ["CHAMPION",  "G",   "W/R",  "KDA",  "SOURCE",  "THREAT"]
    widths = [140,          50,    70,     60,     84,        100]
    with dpg.table(header_row=True, borders_innerH=False, borders_outerH=False,
                   borders_innerV=False, borders_outerV=False, row_background=False):
        for w in widths:
            dpg.add_table_column(width_fixed=True, init_width_or_weight=w)
        with dpg.table_row():
            for h in hdrs:
                t = dpg.add_text(h, color=C["txt2"][:3])
                if "raj_sb_16" in _F: dpg.bind_item_font(t, _F["raj_sb_16"])
        for b in bans:
            tc  = threat_col.get(b["threat"], C["txt2"][:3])
            src = b.get("source", "inhouse")
            sc  = source_col.get(src, C["txt2"][:3])
            vals = [b["name"], str(b["games"]), str(b["wr"]), str(b["kda"]),
                    src.upper(), b["threat"]]
            with dpg.table_row():
                for i, v in enumerate(vals):
                    if   i == 0: col = C["loss"][:3]
                    elif i == 4: col = sc
                    elif i == 5: col = tc
                    else:        col = C["txt"][:3]
                    t = dpg.add_text(str(v)[:16], color=col)
                    if "raj_r_16" in _F: dpg.bind_item_font(t, _F["raj_r_16"])
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

    GW, GH = 520, 160
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
        dpg.draw_rectangle((0, 0), (GW, GH),
                            fill=(*C["card"][:3], 180), color=(0,0,0,0), parent=dl)
        _TIER_BANDS = [
            (1,  3,  (200, 160,  80, 30)),
            (4,  6,  (100, 160, 100, 25)),
            (7, 10,  ( 80, 120, 160, 20)),
            (11, 20, ( 80,  80,  80, 15)),
        ]
        for band_lo, band_hi, band_col in _TIER_BANDS:
            y1 = _py(min(hi, band_hi + 0.5))
            y2 = _py(max(lo, band_lo - 0.5))
            if y1 < y2:
                dpg.draw_rectangle((PAD_L, y1), (PAD_L + pw, y2),
                                   fill=band_col, color=(0,0,0,0), parent=dl)
        for rank_line in range(int(lo), int(hi) + 1):
            if lo <= rank_line <= hi:
                gy = _py(rank_line)
                dpg.draw_line((PAD_L, gy), (PAD_L + pw, gy),
                              color=(*C["rule_dark"][:3], 60), thickness=1, parent=dl)
                dpg.draw_text((2, gy - 8), f"#{int(rank_line)}",
                              color=(*C["txt2"][:3], 220), size=14, parent=dl)
        pts = [(_px(i), _py(v)) for i, v in enumerate(vals)]
        if len(pts) >= 2:
            dpg.draw_polyline(pts, color=(*C["gold"][:3], 200), thickness=2, parent=dl)
        for i, (x, y) in enumerate(pts):
            dpg.draw_circle((x, y), 4, fill=(*C["gold_lt"][:3], 220),
                            color=(*C["gold"][:3], 180), parent=dl)
        step = max(1, len(dates) // 6)
        for i in range(0, len(dates), step):
            lbl = str(dates[i])[-5:]
            dpg.draw_text((_px(i) - 14, GH - PAD_B + 4), lbl,
                          color=(*C["txt_dim"][:3], 140), size=12, parent=dl)
        dpg.draw_line((PAD_L, PAD_T), (PAD_L, PAD_T + ph),
                      color=(*C["rule_dark"][:3], 140), thickness=1, parent=dl)
        dpg.draw_line((PAD_L, PAD_T + ph), (PAD_L + pw, PAD_T + ph),
                      color=(*C["rule_dark"][:3], 140), thickness=1, parent=dl)
    dpg.add_spacer(height=6)
    dpg.add_separator()


def _rw_recent_form(r):
    """Last 10 matches table — DPG table for perfectly even row spacing."""
    matches = r.get("matches", [])
    if not matches:
        return
    dpg.add_spacer(height=8)
    form_state = r.get("form_state", "MIXED")
    form_col = {
        "HOT":   (220, 110,  60),
        "COLD":  ( 80, 140, 220),
        "MIXED": C["txt2"][:3],
    }.get(form_state, C["txt2"][:3])
    _rw_label(f"RECENT FORM — {form_state}", color=form_col)
    dpg.add_spacer(height=4)

    hdrs   = ["#",  "RES", "CHAMPION",  "ROLE", "KDA",  "DAMAGE", "GOLD", "TIME"]
    widths = [30,    46,    130,          52,     70,     84,       80,     60]

    with dpg.child_window(height=min(280, len(matches[:10])*26 + 44),
                          border=True, no_scroll_with_mouse=False):
        with dpg.table(header_row=True, borders_innerH=True, borders_outerH=False,
                       borders_innerV=False, borders_outerV=False, row_background=True):
            for w in widths:
                dpg.add_table_column(width_fixed=True, init_width_or_weight=w)
            with dpg.table_row():
                for h in hdrs:
                    t = dpg.add_text(h, color=C["txt2"][:3])
                    if "raj_sb_16" in _F: dpg.bind_item_font(t, _F["raj_sb_16"])
            for idx, m in enumerate(matches[:10]):
                res    = str(m.get("result", "")).upper()
                wl_col = C["win"][:3] if res == "W" else \
                         C["loss"][:3] if res == "L" else C["txt_dim"][:3]
                vals = [
                    str(idx + 1),
                    res,
                    str(m.get("champion", ""))[:14],
                    str(m.get("role", ""))[:4],
                    str(m.get("kda_str", m.get("kda", ""))),
                    str(m.get("damage", "")),
                    str(m.get("gold", "")),
                    str(m.get("duration", "")),
                ]
                with dpg.table_row():
                    for i2, v in enumerate(vals):
                        col = C["txt_dim"][:3] if i2 == 0 \
                            else wl_col          if i2 == 1 \
                            else C["gold_lt"][:3] if i2 == 2 \
                            else C["txt"][:3]
                        t = dpg.add_text(str(v), color=col)
                        if "raj_r_16" in _F: dpg.bind_item_font(t, _F["raj_r_16"])
    dpg.add_spacer(height=8)
    dpg.add_separator()


def _rw_role_breakdown(r):
    """Role breakdown with horizontal bars — fixed-width alignment."""
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
        # Truncate role to 3 chars to ensure consistent alignment
        role     = str(row.get("role", "")).upper()[:3]
        pct_str  = str(row.get("pct", "0")).replace("%", "")
        try:    pct = float(pct_str) / 100.0
        except: pct = 0.0
        games    = str(row.get("games", ""))
        champs   = str(row.get("top_champs", ""))
        rc       = role_col.get(role, (120,120,120))

        with dpg.group(horizontal=True):
            dpg.add_spacer(width=14)
            # Fixed-width role label (3 chars in same font → consistent bar start)
            t = dpg.add_text(f"{role:<3}", color=rc)
            if "raj_sb_16" in _F: dpg.bind_item_font(t, _F["raj_sb_16"])
            dpg.add_spacer(width=8)
            # Right-align the percentage in the overlay so columns line up
            try:
                pct_display = f"{float(pct_str):5.1f}%"
            except Exception:
                pct_display = f"{pct_str:>5}%"
            dpg.add_progress_bar(default_value=pct, width=BAR_W, height=16,
                                 overlay=f"{pct_display}  {games}g")
            dpg.add_spacer(width=8)
            if champs:
                tc = dpg.add_text(champs[:30], color=C["txt_dim"][:3])
                if "raj_r_16" in _F: dpg.bind_item_font(tc, _F["raj_r_16"])
        dpg.add_spacer(height=4)
    dpg.add_spacer(height=4)
    dpg.add_separator()


def _rw_full_champ_pool(r):
    """Full champion pool — proper fixed-width table columns.

    Phase 2: a RECENT column renders the last 10 ranked/draft games per champ
    as colored dots (gold = win, dim red = loss). Driven by the chronology
    list added to scout sheets in this rewrite. Sheets that pre-date the
    chronology emit (`results` empty) render an em-dash in the RECENT column.
    """
    pool = r.get("champ_pool_full", [])
    if not pool:
        _rw_top_champs(r)
        return
    dpg.add_spacer(height=8)
    _rw_label("CHAMPION POOL")
    dpg.add_spacer(height=4)

    # Fixed-width columns: CHAMPION | G | W-L | W/R | KDA | DMG | RECENT
    hdrs   = ["CHAMPION",  "G",   "W-L",  "W/R",  "KDA",  "DMG",  "RECENT"]
    widths = [140,          44,    68,     60,     60,     80,     108]
    row_h  = len(pool) * 22 + 36
    with dpg.child_window(height=min(280, row_h),
                          border=True, no_scroll_with_mouse=False):
        with dpg.table(header_row=True, borders_innerH=False, borders_outerH=False,
                       borders_innerV=False, borders_outerV=False, row_background=True,
                       scrollY=True):
            for w in widths:
                dpg.add_table_column(width_fixed=True, init_width_or_weight=w)
            with dpg.table_row():
                for h in hdrs:
                    t = dpg.add_text(h, color=C["txt2"][:3])
                    if "raj_sb_16" in _F: dpg.bind_item_font(t, _F["raj_sb_16"])
            for ch in pool:
                wr_str = str(ch.get("wr","")).replace("%","")
                try:    wr_f = float(wr_str)
                except: wr_f = 50.0
                wrc = C["win"][:3] if wr_f >= 52 else C["loss"][:3] if wr_f < 48 else C["txt"][:3]
                wl  = f"{ch.get('wins','')}–{ch.get('losses','')}"
                vals = [ch.get("name",""), str(ch.get("games","")), wl,
                        f"{wr_str}%", str(ch.get("kda","")), str(ch.get("damage",""))]
                results = ch.get("results") or []
                with dpg.table_row():
                    for i2, v in enumerate(vals):
                        col = C["gold_lt"][:3] if i2 == 0 \
                            else wrc             if i2 == 3 \
                            else C["txt"][:3]
                        t = dpg.add_text(str(v)[:16], color=col)
                        if "raj_r_16" in _F: dpg.bind_item_font(t, _F["raj_r_16"])
                    # RECENT column: last 10 results as dots, oldest→newest
                    # (left→right). Em-dash placeholder when chronology is
                    # absent (legacy scout sheets).
                    if results:
                        with dpg.group(horizontal=True):
                            for win in results[-10:]:
                                dot_col = C["win"][:3] if win else C["loss"][:3]
                                dt = dpg.add_text("●", color=dot_col)
                                if "raj_r_16" in _F:
                                    dpg.bind_item_font(dt, _F["raj_r_16"])
                    else:
                        dt = dpg.add_text("—", color=C["txt_dim"][:3])
                        if "raj_r_16" in _F:
                            dpg.bind_item_font(dt, _F["raj_r_16"])
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
            with dpg.child_window(width=110, height=40, border=True,
                                  no_scrollbar=True, no_scroll_with_mouse=True):
                t = dpg.add_text(ch, color=C["txt"][:3])
                if "raj_16" in _F: dpg.bind_item_font(t, _F["raj_16"])
            dpg.add_spacer(width=4)
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
        with dpg.child_window(width=-1, height=50, border=True,
                              no_scrollbar=True, no_scroll_with_mouse=True):
            dpg.add_spacer(height=4)
            t1 = dpg.add_text(text, color=C["loss"][:3])
            if "raj_r_16" in _F: dpg.bind_item_font(t1, _F["raj_r_16"])
            if wr:
                t2 = dpg.add_text(f"Remaining WR if banned: {wr}", color=C["txt2"][:3])
                if "raj_r_16" in _F: dpg.bind_item_font(t2, _F["raj_r_16"])
    dpg.add_spacer(height=8)
    dpg.add_separator()


def _rw_inhouse(r):
    champs = r.get("inhouse_champs", [])
    dpg.add_spacer(height=8)
    _rw_label("INHOUSE CUSTOM GAMES", color=C["rift_purple"][:3])
    dpg.add_spacer(height=6)
    if not champs:
        t = dpg.add_text("  No inhouse champion data recorded yet.", color=C["txt_dim"][:3])
        if "raj_r_16" in _F: dpg.bind_item_font(t, _F["raj_r_16"])
        dpg.add_spacer(height=8)
        return
    hdrs   = ["CHAMPION",  "G",   "W-L",  "W/R",  "KDA",  "AVG DMG"]
    widths = [140,           46,    70,     68,     68,     100]
    with dpg.table(header_row=True, borders_innerH=True, borders_outerH=False,
                   borders_innerV=False, borders_outerV=False, row_background=True):
        for w in widths:
            dpg.add_table_column(width_fixed=True, init_width_or_weight=w)
        with dpg.table_row():
            for h in hdrs:
                t = dpg.add_text(h, color=C["txt2"][:3])
                if "raj_sb_16" in _F: dpg.bind_item_font(t, _F["raj_sb_16"])
        for ch in champs:
            wl  = f"{ch['wins']}-{ch['losses']}"
            wr_str = str(ch["wr"])
            try:    wr_f = float(wr_str.replace("%",""))
            except Exception: wr_f = 50.0
            wrc = C["win"][:3] if wr_f >= 50 else C["loss"][:3]
            vals = [ch["name"], str(ch["games"]), wl, wr_str,
                    str(ch["kda"]), str(ch.get("damage","—"))]
            with dpg.table_row():
                for i, v in enumerate(vals):
                    col = C["rift_purple"][:3] if i==0 else wrc if i==3 else C["txt"][:3]
                    t = dpg.add_text(str(v), color=col)
                    if "raj_r_16" in _F: dpg.bind_item_font(t, _F["raj_r_16"])
    dpg.add_spacer(height=16)


# ---------------------------------------------------------------------------
# Report window management
# ---------------------------------------------------------------------------

def _report_panel_pos(vw):
    table_end = int(vw * TABLE_FRAC) + PAD
    rw = vw - table_end
    rx = SIDEBAR_W + table_end
    return rx, APP_TITLE_H, rw, None


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
            if "raj_r_16" in _F: dpg.bind_item_font(t, _F["raj_r_16"])
            return

        if scout.report_loading and r is None:
            dpg.add_spacer(height=60)
            t = dpg.add_text("Fetching scouting report…", color=C["gold_dk"][:3])
            if "raj_r_16" in _F: dpg.bind_item_font(t, _F["raj_r_16"])
            return

        if r is None:
            return

        _rw_header(r)
        _rw_player_tags(r)
        _rw_compare(r)

        if scout.report_loading:
            with dpg.group(horizontal=True):
                dpg.add_spacer(width=14)
                t = dpg.add_text("  Loading detailed report from sheet...",
                                 color=C["gold_dk"][:3])
                if "raj_r_16" in _F: dpg.bind_item_font(t, _F["raj_r_16"])
            dpg.add_spacer(height=4)
        elif r.get("sheet_error"):
            err_msg    = str(r["sheet_error"])
            is_missing = "No scouting sheet" in err_msg
            banner_col = C["gold_dk"][:3] if is_missing else C["loss"][:3]
            with dpg.group(horizontal=True):
                dpg.add_spacer(width=14)
                with dpg.child_window(width=-1, height=52, border=True,
                                      no_scrollbar=True, no_scroll_with_mouse=True):
                    if is_missing:
                        t = dpg.add_text("  No scout sheet for this player.", color=banner_col)
                        if "raj_r_16" in _F: dpg.bind_item_font(t, _F["raj_r_16"])
                        t2 = dpg.add_text(
                            "  Run 'RUN SCOUT' from the Commands tab to generate it.",
                            color=C["txt_dim"][:3])
                        if "raj_r_14" in _F: dpg.bind_item_font(t2, _F["raj_r_14"])
                    else:
                        t = dpg.add_text(f"  Sheet error: {err_msg[:90]}", color=banner_col)
                        if "raj_r_16" in _F: dpg.bind_item_font(t, _F["raj_r_16"])
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
    LOADING_REPORT = "loading_report"


class ScoutState:
    def __init__(self):
        self.phase          = ScoutPhase.IDLE
        self.players        = []
        self.sort_col       = "score"
        self.sort_asc       = False
        self.selected       = None
        self.current_report = None
        self.report_dirty   = False
        self.report_loading = False
        self.report_error   = None
        self.row_alpha      = {}
        self.row_x_off      = {}
        self.header_alpha   = 0
        self._load_t        = 0.0
        self._tip           = _rnd.choice(_TIPS)
        self.scroll_off     = 0
        # Phase 3 — side-by-side compare target (player name or None)
        self.compare_with   = None

    def reset(self):
        self.__init__()

    def tick(self):
        self._load_t += 0.04

    def begin_load(self, players):
        self.reset()
        self.scroll_off = 0
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
        self.selected       = name
        self.report_error   = None
        self.current_report = _build_full_report(name)
        self.report_dirty   = True
        self.report_loading = True
        load_scout_sheet(
            name,
            on_done  = lambda data, hist: _on_sheet_loaded(name, data, hist),
            on_error = lambda msg:        _on_sheet_error(name, msg),
        )

    def toggle_sort(self, col):
        self.scroll_off = 0
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
    # Always cache the parsed sheet for the draft engine, even if the user
    # has navigated to a different player by the time it lands.
    cache_scout_sheet(name, sheet_data)
    if scout.selected != name:
        return
    base = _build_full_report(name) or {}

    scouted_at = sheet_data.get("scouted_at")
    if scouted_at:
        from datetime import datetime as _dt
        parsed = None
        if isinstance(scouted_at, _dt):
            parsed = scouted_at
        else:
            s = str(scouted_at).strip().replace("Z", "+00:00")
            try:
                parsed = _dt.fromisoformat(s)
            except ValueError:
                for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
                    try:
                        parsed = _dt.strptime(s, fmt)
                        break
                    except ValueError:
                        continue
        if parsed is not None:
            now = _dt.now(parsed.tzinfo) if parsed.tzinfo else _dt.now()
            base["scouted_days_ago"] = max(0, (now - parsed).days)

    if sheet_data.get("champ_pool"):
        base["champ_pool_full"] = sheet_data["champ_pool"]

    if sheet_data.get("roles"):
        base["roles"] = sheet_data["roles"]

    if sheet_data.get("matches"):
        base["matches"] = sheet_data["matches"]
        base["form_state"] = sheet_data.get("form_state", base.get("form_state", "MIXED"))

    # Merge sheet ban targets (inhouse) with ranked danger picks
    if sheet_data.get("must_bans"):
        sheet_bans = []
        seen_sheet = set()
        for b in sheet_data["must_bans"]:
            threat = str(b.get("threat", "")).upper()
            if threat in ("HIGH", "PERMABAN", "ELEVATED"):
                cname = b["name"]
                seen_sheet.add(cname)
                sheet_bans.append({
                    "name":   cname,
                    "games":  b.get("games", ""),
                    "wr":     b.get("wr", ""),
                    "kda":    b.get("kda", ""),
                    "threat": threat,
                    "source": "inhouse",
                })
        # Keep ranked danger picks from local report that aren't already covered
        for bt in base.get("ban_targets", []):
            if bt.get("source") == "ranked" and bt["name"] not in seen_sheet:
                sheet_bans.append(bt)
        if sheet_bans:
            base["ban_targets"] = sheet_bans[:6]

    if sheet_data.get("ban_impact"):
        base["ban_impact"] = sheet_data["ban_impact"]

    base["rank_history"] = history

    scout.current_report  = base
    scout.report_loading  = False
    scout.report_dirty    = True


def _on_sheet_error(name, msg):
    if scout.selected != name:
        return
    scout.report_loading = False
    scout.report_error   = msg
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
    # Flush any newly uploaded avatars so the report panel can display them
    try:
        from ui.inhouse import _scan_local_avatars, _flush_pending
        _scan_local_avatars()
        _flush_pending()
    except Exception:
        pass
    scout.tick()
    dpg.delete_item(dl, children_only=True)
    dpg.draw_rectangle((0,0),(vw,3000), fill=C["bg"], color=(0,0,0,0), parent=dl)
    # V2 ambient — broad cool top-light + page vignette for depth.
    luxe.glow(dl, vw * 0.5, -vh * 0.25, vw * 0.75, (40, 72, 118), 55)
    # Prevent native content_win scroll from misaligning click zones
    if dpg.does_item_exist("content_win"):
        dpg.set_y_scroll("content_win", 0)

    if scout.phase == ScoutPhase.IDLE:
        _draw_idle(dl, vw, vh); return
    if scout.phase == ScoutPhase.LOADING:
        _draw_loading(dl, vw, vh); return

    table_w = int(vw * TABLE_FRAC)

    _draw_table(dl, PAD, TOP_BAR_H + PAD, table_w - PAD*2, vh - TOP_BAR_H - PAD*2, vw, vh)
    # Draw top bar AFTER the table so it renders on top of any scrolled-up rows;
    # pass table_w so the bar background and buttons stay inside the table column.
    _draw_top_bar(dl, vw, table_w)

    if not dpg.does_item_exist(_REPORT_WIN):
        _rebuild_report_window(vw, vh)
    else:
        rx, ry, rw, _ = _report_panel_pos(vw)
        dpg.configure_item(_REPORT_WIN, pos=(rx, ry), width=rw, height=vh)
        if scout.report_dirty:
            _rebuild_report_window(vw, vh)
            scout.report_dirty = False

    dx = table_w + 1
    dpg.draw_line((dx, TOP_BAR_H),(dx, vh),
                  color=(*C["gold_dk"][:3], 110), thickness=1, parent=dl)
    luxe.vignette(dl, 0, 0, vw, vh, 60)


def _draw_idle(dl, vw, vh):
    cx, cy = vw//2, vh//2
    try:
        from ui.effects import draw_drift_field
        draw_drift_field(dl, 0, 0, vw, vh, alpha=180,
                         accent=C["gold"][:3], n_dots=20, seed=23)
    except Exception:
        pass
    t  = (math.sin(time.monotonic()*1.3)+1)/2
    a  = int(90 + t*110)
    _txt(dl, cx-220, cy-30, "PLAYER SCOUTING", (*C["gold"][:3],a), 36, "cinzel_36")
    _txt(dl, cx-160, cy+14, "Fetch latest data to begin", (*C["txt_dim"][:3],int(a*.6)), 19, "raj_18")
    bw, bh = 300, 60
    bx, by = cx-bw//2, cy+56
    dpg.draw_rectangle((bx,by),(bx+bw,by+bh), fill=(*C["gold_dk"][:3],210),
                        color=(*C["gold"][:3],210), rounding=6, parent=dl)
    _txt(dl, bx+bw//2-110, by+16, "LOAD SCOUT DATA", (*C["gold_lt"][:3],230), 23, "raj_24")
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
    """Skeleton of the scout layout — the player table + report panel morph
    into real content once the data lands."""
    table_w = int(vw * TABLE_FRAC)
    rx = PAD
    ry = TOP_BAR_H + PAD
    rw = max(80, table_w - PAD * 2)
    for i in range(10):
        effects.draw_skeleton_row(dl, rx, ry + i * (ROW_H + 3), rw, ROW_H)
    px = table_w + PAD
    pw = max(80, vw - px - PAD)
    effects.draw_skeleton_rect(dl, px, TOP_BAR_H + PAD, pw,
                               max(80, vh - TOP_BAR_H - PAD * 2), rounding=6)
    tip = scout._tip
    _txt(dl, max(40, vw // 2 - len(tip) * 5), vh - 44, tip,
         (*C["txt_dim"][:3], 150), 18, "raj_r_18")


def _draw_top_bar(dl, vw, header_w):
    """header_w = width of the table column — bars and buttons stay inside it."""
    # V2 broadcast header — gradient surface + gold bottom edge light.
    dpg.draw_rectangle((0,0),(header_w,TOP_BAR_H), fill=C["navy_deep"],
                       color=(0,0,0,0), parent=dl)
    luxe.vfade(dl, 0, 0, header_w, TOP_BAR_H, (44, 74, 116), 46, solid="top")
    luxe.vfade(dl, 0, TOP_BAR_H - 10, header_w, TOP_BAR_H - 1,
               C["gold"], 26, solid="bottom")
    dpg.draw_line((0,TOP_BAR_H-1),(header_w,TOP_BAR_H-1),
                  color=(*C["gold_dk"][:3], 200), thickness=1, parent=dl)
    luxe.glow(dl, PAD + 6, TOP_BAR_H // 2, 26, C["gold"], 55)
    _txt(dl, PAD, 12, "PLAYER SCOUTING", (*C["gold_lt"][:3],240), 24, "cinzel_24")

    labels = [("SCORE","score"),("W/R","wr"),("KDA","kda")]
    bx = header_w - 320   # anchor sort buttons to the right edge of the table column
    for lbl, col_key in labels:
        active = scout.sort_col == col_key
        if active:
            luxe.glow(dl, bx + 45, TOP_BAR_H // 2, 30, C["gold"], 34)
            luxe.panel(dl, bx, 10, bx + 90, TOP_BAR_H - 10,
                       (116, 90, 44, 235), corner=4,
                       border=C["gold"], border_a=215, sheen=85)
            tcol = C["gold_lt"]
        else:
            dpg.draw_rectangle((bx,10),(bx+90,TOP_BAR_H-10),
                                fill=(*C["card"][:3], 180),
                                color=(*C["gold"][:3], 70),
                                rounding=4, parent=dl)
            tcol = C["txt"]
        arr  = ("▲" if scout.sort_asc else "▼") if active else ""
        _txt(dl, bx+8, 18, lbl+arr, (*tcol[:3],220), 17, "raj_18")
        bx += 100

    if dpg.is_mouse_button_clicked(0):
        mouse = dpg.get_mouse_pos(local=False)
        vp    = dpg.get_viewport_pos()
        rx = mouse[0]-vp[0]-68; ry = mouse[1]-vp[1]-52
        if 10 <= ry <= TOP_BAR_H-10:
            bx2 = header_w - 320
            for _, c2 in labels:
                if bx2 <= rx <= bx2+90:
                    scout.toggle_sort(c2); break
                bx2 += 100


def _draw_table(dl, tx, ty, tw, th, vw, vh):
    players  = scout._sorted()
    col_xs   = _col_xs(tw)
    ha       = scout.header_alpha

    # Calculate scroll bounds and consume wheel delta
    visible_h    = th - HEADER_H - 4
    total_rows_h = len(players) * (ROW_H + 3)
    max_scroll   = max(0, total_rows_h - visible_h)
    if _wheel_delta_shared[0] != 0:
        scout.scroll_off = max(0, min(
            scout.scroll_off - _wheel_delta_shared[0] * 30, max_scroll))
        _wheel_delta_shared[0] = 0
    scout.scroll_off = max(0, min(scout.scroll_off, max_scroll))
    scroll = int(scout.scroll_off)

    row_clip_top = ty + HEADER_H + 4
    row_clip_bot = ty + th

    # V2 card framing — the table sits on a shadowed gradient panel.
    luxe.shadow(dl, tx - 8, ty - 8, tx + tw + 8, ty + th,
                alpha=85, spread=14, drop=6)
    luxe.panel(dl, tx - 8, ty - 8, tx + tw + 8, ty + th,
               (12, 26, 48, 242), corner=10,
               border=C["gold_dk"], border_a=120, sheen=42)

    row_y = ty + HEADER_H + 4

    # Cursor in content coords, for per-row hover feedback.
    _m   = dpg.get_mouse_pos(local=False)
    _vp  = dpg.get_viewport_pos()
    _mrx = _m[0] - _vp[0] - SIDEBAR_W
    _mry = _m[1] - _vp[1] - APP_TITLE_H

    # Draw rows FIRST so the column header renders on top of any scrolled-up rows
    for i, p in enumerate(players):
        n  = p["name"]
        al = scout.row_alpha.get(n, 0)
        xo = scout.row_x_off.get(n, -60)
        if al <= 0:
            continue
        ry  = row_y + i*(ROW_H+3) - scroll
        if ry + ROW_H < row_clip_top or ry > row_clip_bot:
            continue
        is_sel = scout.selected == n
        is_hov = (not is_sel and tx+xo <= _mrx <= tx+tw+xo
                  and ry <= _mry <= ry+ROW_H)
        if is_sel:
            bg = (*C["card_hover"][:3], al)
        elif is_hov:
            bg = (*C["card_hover"][:3], int(al * 0.65))
        elif i % 2 == 0:
            bg = (*C["card"][:3], al)
        else:
            bg = (*C["panel"][:3], al)
        dpg.draw_rectangle((tx+xo,ry),(tx+tw+xo,ry+ROW_H),
                            fill=bg, color=(0,0,0,0), rounding=3, parent=dl)
        if is_sel:
            dpg.draw_rectangle((tx+xo,ry),(tx+xo+4,ry+ROW_H),
                                fill=(*C["gold"][:3],al), color=(0,0,0,0), rounding=2, parent=dl)
        elif is_hov:
            dpg.draw_rectangle((tx+xo,ry),(tx+xo+3,ry+ROW_H),
                                fill=(*C["gold"][:3],int(al*0.5)), color=(0,0,0,0), rounding=2, parent=dl)

        tier = p.get("tier","Unranked")
        bc   = RANK_COLORS.get(tier, RANK_COLORS["Unranked"])
        try:
            score_disp = str(int(round(effects.count_up(f"scscore:{n}", float(p["score"])))))
        except (TypeError, ValueError):
            score_disp = str(p.get("score", "?"))

        vals = [
            str(i+1),
            p["name"],
            score_disp,
            f"{p.get('wr',0)}%",
            f"{p.get('kda',0.0):.1f}",
            str(p.get("games",0)),
        ]

        medal = MEDAL_PARTICLE.get(i + 1)
        if medal:
            luxe.glow(dl, tx + xo + 2, ry + ROW_H // 2, ROW_H * 0.6,
                      medal, int(al * 0.22))
            dpg.draw_rectangle((tx+xo, ry+3), (tx+xo+4, ry+ROW_H-3),
                               fill=(*medal, al), color=(0, 0, 0, 0),
                               rounding=2, parent=dl)
        for ci, (val, (cx, cw)) in enumerate(zip(vals, col_xs)):
            vx = tx + xo + cx + 8
            vy = ry + ROW_H//2 - 10
            if ci == 0:
                rank_c = medal if medal else C["txt2"]
                _txt(dl, vx, vy, val, (*rank_c[:3],al), 20, "raj_20")
            elif ci == 1:
                luxe.glow(dl, vx+5, ry+ROW_H//2, 12, bc, int(al * 0.30))
                dpg.draw_circle((vx+5,ry+ROW_H//2),8, fill=(*bc[:3],al), color=(0,0,0,0), parent=dl)
                _txt(dl, vx+20, vy, val.upper(), (*C["gold_lt"][:3],al), 22, "raj_24")
            elif ci == 2:
                _txt(dl, vx, vy, val, (*C["gold"][:3],al), 22, "raj_24")
            elif ci == 3:
                wr_v  = p.get("wr",50)
                wrc   = C["win"] if wr_v>=52 else C["loss"] if wr_v<48 else C["txt"]
                _txt(dl, vx, vy, val, (*wrc[:3],al), 20, "raj_20")
            elif ci == 4:
                _txt(dl, vx, vy, val, (*C["platinum"][:3],al), 20, "raj_20")
            else:
                _txt(dl, vx, vy, val, (*C["txt2"][:3],al), 19, "raj_20")

    # Column header drawn AFTER rows so it masks any rows that scrolled into
    # its area — V2: gradient panel + fading gold rule.
    luxe.panel(dl, tx, ty, tx + tw, ty + HEADER_H,
               (24, 48, 82, min(255, ha)), corner=6,
               border=C["gold_dk"], border_a=min(150, ha), sheen=46)
    for (lbl,_,sk),(cx,cw) in zip(COLS, col_xs):
        active = sk and scout.sort_col == sk
        col    = C["gold_lt"] if active else C["txt2"]
        _txt(dl, tx+cx+8, ty+HEADER_H//2-10, lbl, (*col[:3],ha), 19, "raj_sb_18")
    luxe.hfade(dl, tx + 6, ty + HEADER_H - 2, tx + tw - 6, ty + HEADER_H,
               C["gold"], min(120, ha), solid="left")

    # Click detection — uses scroll-adjusted positions
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
            row_top = row_y + i*(ROW_H+3) - scroll
            if row_top + ROW_H < row_clip_top or row_top > row_clip_bot:
                continue
            if tx <= rx2 <= tx+tw and row_top <= ry2 <= row_top+ROW_H:
                scout.select(n)
                break
