"""
Draft Tab — Phase 3: War Room.

Layout:
  Team builder (combo dropdowns) → Assembly animation → Analysis

Top strip:  [BLUE TEAM — 5 hexes horizontal] [WIN METER] [RED TEAM — 5 hexes horizontal]
Bottom:     [Blue bans + comps] [Player vs Player] [Red bans + comps]
"""
import math, time
import dearpygui.dearpygui as dpg
from theme import C, RANK_COLORS
from core.animations import anim, Ripple
from data.reader import live, load_prediction_data, write_draft_picks, run_draft_subprocess, read_draft_results
from data.config import load_config

# ---------------------------------------------------------------------------
# Team builder window config
# ---------------------------------------------------------------------------
_TB_WIN    = "draft_team_builder"
_TB_BUILT  = [False]


def _get_player_pool():
    """Return player list from live rankings, falling back to config players."""
    if live.loaded and live.rankings:
        return list(live.rankings)
    cfg_players = load_config().get("players", [])
    if cfg_players:
        return [{"name": p if isinstance(p, str) else p.get("name", str(p)),
                 "tier": "Unranked", "final_score": 50.0, "score": 50.0}
                for p in cfg_players]
    return []


def _player_score(p):
    """Return a float strength score for a player dict."""
    try:
        return float(p.get("final_score", p.get("score", 50.0)))
    except (TypeError, ValueError):
        return 50.0

_ROLES = ["TOP", "JGL", "MID", "BOT", "SUP"]

# ---------------------------------------------------------------------------
# Matchup computation
# ---------------------------------------------------------------------------

_ENGAGE_CHAMPS  = {"Leona","Malphite","Amumu","Sejuani","Galio","Orianna",
                   "Vi","Jarvan IV","Jarvan","Wukong","Zac","Kennen"}
_POKE_CHAMPS    = {"Jayce","Ezreal","Zoe","Karma","Lux","Nidalee","Xerath",
                   "Ziggs","Hwei","Corki","Caitlyn"}
_SPLIT_CHAMPS   = {"Fiora","Camille","Tryndamere","Riven","Jax","Nasus","Garen"}
_PROTECT_CHAMPS = {"Lulu","Janna","Soraka","Ivern","Sona","Tahm Kench","Shields"}


def _compute_matchups(blue, red):
    """
    Compute per-lane 1v1 matchup advantage for each role.
    Returns list of (role, blue_name, red_name, blue_win_pct, note).

    Factors:
      1. Score delta — power rankings score difference
      2. Role familiarity — whether player is in their inhouse primary role
    """
    rows = []
    for i, (bp, rp) in enumerate(zip(blue, red)):
        role = _ROLES[i]
        bs   = _player_score(bp)
        rs   = _player_score(rp)
        diff = bs - rs

        # Score advantage: ~0.5% per score point, capped ±25%
        blue_adv = 50.0 + diff * 0.5
        blue_adv = max(25.0, min(75.0, blue_adv))

        # Role familiarity bonus: ±4% if playing/not-playing main role
        b_main = live.primary_roles.get(bp["name"])
        r_main = live.primary_roles.get(rp["name"])
        if b_main == role:   blue_adv += 4.0
        if r_main == role:   blue_adv -= 4.0
        blue_adv = max(20.0, min(80.0, blue_adv))

        note = _matchup_note(diff, role, bp["name"], rp["name"], b_main, r_main)
        rows.append((role, bp["name"], rp["name"], round(blue_adv, 1), note))
    return rows


def _matchup_note(diff, role, bn, rn, b_main, r_main):
    parts = []
    if   abs(diff) >= 20: parts.append(f"{'Blue' if diff>0 else 'Red'} +{abs(diff):.0f} score")
    elif abs(diff) >= 8:  parts.append("Close skill match")
    else:                 parts.append("Even matchup")

    if   b_main == role:             parts.append(f"{bn} on main")
    elif b_main and b_main != role:  parts.append(f"{bn} off-role ({b_main})")
    if   r_main == role:             parts.append(f"{rn} on main")
    elif r_main and r_main != role:  parts.append(f"{rn} off-role ({r_main})")

    return "  ·  ".join(parts[:3])


def _compute_bans(opposing_players):
    """
    Recommend bans against the opposing team.
    Prioritises inhouse champions with most games, then top_champs from Player Stats.
    Returns list of up to 5 champion name strings.
    """
    seen   = {}
    # Inhouse data first (most reliable — actual games played)
    for p in opposing_players:
        for ch in live.inhouse_champs.get(p["name"], [])[:3]:
            cname = ch["champ"]
            if cname not in seen or ch["games"] > seen[cname]["games"]:
                seen[cname] = {"champ": cname, "games": ch["games"],
                               "player": p["name"]}
    # Top champs from Player Stats (mastery data)
    for p in opposing_players:
        for champ in p.get("top_champs", [])[:2]:
            if champ and champ not in seen:
                seen[champ] = {"champ": champ, "games": 0, "player": p["name"]}

    bans = sorted(seen.values(), key=lambda x: -x["games"])[:5]
    return [b["champ"] for b in bans]


_COMP_TAGS = [
    (_ENGAGE_CHAMPS,  "Engage  (Hard CC + Dive)"),
    (_POKE_CHAMPS,    "Poke  (Range + Siege)"),
    (_SPLIT_CHAMPS,   "Split Push  (1-3-1)"),
    (_PROTECT_CHAMPS, "Protect ADC  (Shield/Heal)"),
]
_COMP_FALLBACKS = [
    "Teamfight  (AoE burst)",
    "Skirmish  (Pick + Catch)",
    "Scaling  (Late-game win)",
]

def _compute_comps(players):
    """Suggest team compositions based on the assembled players' champion pools."""
    all_champs = {ch for p in players for ch in p.get("top_champs", [])}
    comps = []
    for champ_set, label in _COMP_TAGS:
        if all_champs & champ_set:
            comps.append(label)
    for fb in _COMP_FALLBACKS:
        if len(comps) >= 5:
            break
        comps.append(fb)
    return comps[:5]

# Fly-in config
FLY_DURATION_MS  = 460
FLY_STAGGER_MS   = 55
TEAM_FLASH_MS    = 280

# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------
class DraftPhase:
    IDLE        = "idle"
    TEAM_BUILD  = "team_build"
    ASSEMBLING  = "assembling"
    ANALYSING   = "analysing"
    RESULTS     = "results"
    DONE        = "done"


class DraftState:
    def __init__(self):
        self.phase            = DraftPhase.IDLE
        self.blue             = []   # list of player dicts with role assigned
        self.red              = []
        self.blue_slots       = {}   # idx → {x_frac, alpha, landed}
        self.red_slots        = {}
        self.team_flash_blue  = 0
        self.team_flash_red   = 0
        self.win_pct          = 50.0
        self.win_pct_display  = 50.0
        self.win_meter_alpha  = 0
        self.panel_alpha      = 0
        self.analyse_t        = 0.0
        self._landed          = 0
        self._total           = 0
        self.blue_avg         = 0.0
        self.red_avg          = 0.0
        # Local computed analysis data
        self.pvp_rows         = []   # [(role, blue_name, red_name, blue_pct, note)]
        self.blue_bans        = []   # [champ_name, ...]
        self.red_bans         = []
        self.blue_comps       = []   # [comp_str, ...]
        self.red_comps        = []
        # Sheet / subprocess results (richer data, arrives later)
        self.ban_detail_blue  = []   # [{champion, wr, games, priority, target}, ...]
        self.ban_detail_red   = []
        self.comp_detail_blue = []   # [{archetype, description, viability, synergy, picks}, ...]
        self.comp_detail_red  = []
        self.prediction_src   = "local"   # "local" | "sheets"
        self.bg_running       = False     # background sheet/subprocess in progress
        self.bg_status        = ""        # human-readable status for the ANALYSING screen
        self.prediction_ready = False     # flag: better prediction arrived, re-tween needed

    def reset(self):
        self.__init__()

    def tick(self):
        self.analyse_t += 0.05

    def start_assembly(self, blue, red, win_pct=50.0):
        self.blue    = blue
        self.red     = red
        self.win_pct = win_pct
        self.phase   = DraftPhase.ASSEMBLING
        self._total  = len(blue) + len(red)
        self._landed = 0
        for i in range(len(blue)):
            self.blue_slots[i] = {"x_frac": 0.0, "alpha": 0, "landed": False}
        for i in range(len(red)):
            self.red_slots[i]  = {"x_frac": 0.0, "alpha": 0, "landed": False}

        for i in range(len(blue)):
            delay = i * FLY_STAGGER_MS
            def _lb(idx=i): self._fly_blue(idx)
            anim.tween(0, 1, 1, "linear", delay_ms=delay, on_done=_lb)
        for i in range(len(red)):
            delay = i * FLY_STAGGER_MS
            def _lr(idx=i): self._fly_red(idx)
            anim.tween(0, 1, 1, "linear", delay_ms=delay, on_done=_lr)

    def _fly_blue(self, idx):
        s = self.blue_slots[idx]
        anim.tween(0.0, 1.0, FLY_DURATION_MS, "out_cubic",
                   on_update=lambda v: s.update({"x_frac": v}))
        anim.tween(0, 255, FLY_DURATION_MS // 2, "out_cubic",
                   on_update=lambda v: s.update({"alpha": int(v)}),
                   on_done=lambda: self._land(s))

    def _fly_red(self, idx):
        s = self.red_slots[idx]
        anim.tween(0.0, 1.0, FLY_DURATION_MS, "out_cubic",
                   on_update=lambda v: s.update({"x_frac": v}))
        anim.tween(0, 255, FLY_DURATION_MS // 2, "out_cubic",
                   on_update=lambda v: s.update({"alpha": int(v)}),
                   on_done=lambda: self._land(s))

    def _land(self, s):
        s["landed"] = True
        self._landed += 1
        if self._landed >= self._total:
            anim.tween(200, 0, TEAM_FLASH_MS, "out_cubic",
                       on_update=lambda v: setattr(self, "team_flash_blue", int(v)))
            anim.tween(200, 0, TEAM_FLASH_MS, "out_cubic",
                       on_update=lambda v: setattr(self, "team_flash_red",  int(v)))
            anim.tween(0, 1, 1, "linear", delay_ms=TEAM_FLASH_MS + 400,
                       on_done=self._start_analysing)

    def _start_analysing(self):
        self.phase = DraftPhase.ANALYSING
        anim.tween(0, 1, 1, "linear", delay_ms=2400, on_done=self._show_results)

    def _show_results(self):
        self.phase = DraftPhase.RESULTS
        anim.tween(50.0, self.win_pct, 1200, "in_out",
                   on_update=lambda v: setattr(self, "win_pct_display", v))
        anim.tween(0, 255, 400, "out_cubic",
                   on_update=lambda v: setattr(self, "win_meter_alpha", int(v)))
        anim.tween(0, 255, 600, "out_cubic", delay_ms=800,
                   on_update=lambda v: setattr(self, "panel_alpha", int(v)),
                   on_done=lambda: setattr(self, "phase", DraftPhase.DONE))


draft = DraftState()

_F = {}
def set_fonts(f): global _F; _F = f

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _txt(dl, x, y, text, color, size, font_key=None):
    tag = dpg.draw_text((x, y), text, color=color, size=size, parent=dl)
    if font_key and font_key in _F:
        dpg.bind_item_font(tag, _F[font_key])
    return tag


def _hex_avatar(dl, cx, cy, r, tier, name, alpha=255):
    bc  = RANK_COLORS.get(tier, RANK_COLORS["Unranked"])
    pts = [(cx + r * math.cos(math.pi/6 + i * math.pi/3),
            cy + r * math.sin(math.pi/6 + i * math.pi/3)) for i in range(6)]
    dpg.draw_polygon(pts, fill=(*C["card"][:3], alpha),
                     color=(*bc[:3], alpha), thickness=2.5, parent=dl)
    initials = (name[:2] if name else "??").upper()
    dpg.draw_text((cx - len(initials)*8, cy - 13), initials,
                  color=(*C["txt"][:3], alpha), size=22, parent=dl)


def _role_dot(dl, cx, cy, role, alpha=255):
    role_colors = {
        "TOP": (180,100,60), "JGL": (80,160,80),
        "MID": (100,120,200), "BOT": (180,160,60), "SUP": (100,180,180),
    }
    col = role_colors.get(role, (120,120,120))
    dpg.draw_circle((cx, cy), 12, fill=(*col, alpha),
                    color=(0,0,0,0), parent=dl)
    dpg.draw_text((cx - 5, cy - 8), role[:1],
                  color=(*C["txt"][:3], alpha), size=12, parent=dl)


def _panel_bg(dl, x1, y1, x2, y2, accent_color=None, alpha=255):
    dpg.draw_rectangle((x1, y1),(x2, y2),
                        fill=(*C["panel"][:3], alpha),
                        color=(*C["rule_dark"][:3], alpha),
                        rounding=6, parent=dl)
    if accent_color:
        dpg.draw_rectangle((x1+2, y1+2),(x2-2, y1+6),
                            fill=(*accent_color[:3], alpha),
                            color=(0,0,0,0), rounding=2, parent=dl)

# ---------------------------------------------------------------------------
# Team builder — DPG widget window
# ---------------------------------------------------------------------------

def _open_team_builder(vw, vh):
    if dpg.does_item_exist(_TB_WIN):
        return

    # Player names for dropdowns — use live rankings or config fallback
    pool  = _get_player_pool()
    names = [p["name"] for p in pool] if pool else [f"Player {i}" for i in range(1, 11)]

    win_w = min(1000, vw - 160)
    win_h = 520
    # Position in full viewport coords (content area offset: sidebar 68, titlebar 52)
    wx = 68 + (vw - win_w) // 2
    wy = 52 + (vh - win_h) // 2

    with dpg.window(tag=_TB_WIN, label="Configure Teams",
                    pos=(wx, wy), width=win_w, height=win_h,
                    no_title_bar=True, no_resize=True, no_move=False,
                    no_scrollbar=True):

        dpg.add_spacer(height=16)

        # Title
        with dpg.group(horizontal=True):
            dpg.add_spacer(width=win_w // 2 - 120)
            t = dpg.add_text("CONFIGURE TEAMS")
            if "raj_28" in _F:
                dpg.bind_item_font(t, _F["raj_28"])

        dpg.add_spacer(height=12)
        dpg.add_separator()
        dpg.add_spacer(height=16)

        combo_w = (win_w - 80) // 2 - 20

        with dpg.group(horizontal=True):
            dpg.add_spacer(width=20)

            # Blue team column
            with dpg.group():
                bt = dpg.add_text("BLUE TEAM")
                if "raj_sb_22" in _F: dpg.bind_item_font(bt, _F["raj_sb_22"])
                dpg.add_spacer(height=10)
                for i, role in enumerate(_ROLES):
                    with dpg.group(horizontal=True):
                        rt = dpg.add_text(f"{role:<3} ")
                        if "raj_sb_16" in _F: dpg.bind_item_font(rt, _F["raj_sb_16"])
                        dpg.add_combo(names, tag=f"tb_blue_{i}",
                                      width=combo_w - 60, default_value=names[i % len(names)])
                    dpg.add_spacer(height=6)

            dpg.add_spacer(width=40)

            # Red team column
            with dpg.group():
                rt2 = dpg.add_text("RED TEAM")
                if "raj_sb_22" in _F: dpg.bind_item_font(rt2, _F["raj_sb_22"])
                dpg.add_spacer(height=10)
                for i, role in enumerate(_ROLES):
                    with dpg.group(horizontal=True):
                        rl = dpg.add_text(f"{role:<3} ")
                        if "raj_sb_16" in _F: dpg.bind_item_font(rl, _F["raj_sb_16"])
                        # Default to players 5-9 so both teams have different defaults
                        default_idx = (i + 5) % len(names)
                        dpg.add_combo(names, tag=f"tb_red_{i}",
                                      width=combo_w - 60, default_value=names[default_idx])
                    dpg.add_spacer(height=6)

        dpg.add_spacer(height=20)
        dpg.add_separator()
        dpg.add_spacer(height=16)

        with dpg.group(horizontal=True):
            dpg.add_spacer(width=win_w // 2 - 140)
            btn = dpg.add_button(label="  BEGIN ANALYSIS  ",
                                 callback=_on_begin_analysis,
                                 width=280, height=52)
            if "raj_24" in _F: dpg.bind_item_font(btn, _F["raj_24"])


def _on_begin_analysis():
    pool         = _get_player_pool()
    pool_by_name = {p["name"]: p for p in pool}

    blue_players, red_players = [], []
    for i, role in enumerate(_ROLES):
        bn = dpg.get_value(f"tb_blue_{i}")
        rn = dpg.get_value(f"tb_red_{i}")
        bp = dict(pool_by_name.get(bn, {"name": bn, "tier": "Unranked",
                                         "final_score": 50.0, "score": 50.0}))
        rp = dict(pool_by_name.get(rn, {"name": rn, "tier": "Unranked",
                                         "final_score": 50.0, "score": 50.0}))
        bp["role"] = role
        rp["role"] = role
        blue_players.append(bp)
        red_players.append(rp)

    blue_avg = sum(_player_score(p) for p in blue_players) / max(len(blue_players), 1)
    red_avg  = sum(_player_score(p) for p in red_players)  / max(len(red_players),  1)

    total   = blue_avg + red_avg
    win_pct = (blue_avg / total * 100) if total > 0 else 50.0
    win_pct = max(25.0, min(75.0, win_pct))

    draft.blue_avg        = blue_avg
    draft.red_avg         = red_avg
    draft.pvp_rows        = _compute_matchups(blue_players, red_players)
    draft.blue_bans       = _compute_bans(red_players)    # blue bans = target red team's picks
    draft.red_bans        = _compute_bans(blue_players)
    draft.blue_comps      = _compute_comps(blue_players)
    draft.red_comps       = _compute_comps(red_players)
    # Reset richer results from any previous run
    draft.ban_detail_blue  = []
    draft.ban_detail_red   = []
    draft.comp_detail_blue = []
    draft.comp_detail_red  = []
    draft.prediction_src   = "local"
    draft.prediction_ready = False

    if dpg.does_item_exist(_TB_WIN):
        dpg.delete_item(_TB_WIN)
    draft.start_assembly(blue_players, red_players, win_pct)

    # ── Phase 1: Better win probability from Rank History + inhouse stats ──
    blue_names = [p["name"] for p in blue_players]
    red_names  = [p["name"] for p in red_players]
    load_prediction_data(blue_names, red_names, on_done=_apply_prediction)

    # ── Phase 2: Write picks to sheet + run subprocess + read rich results ──
    draft.bg_running = True
    draft.bg_status  = "Writing picks to sheet…"
    _kick_off_bg_draft(blue_players, red_players)


def _apply_prediction(pred):
    """
    Called from background thread when Rank History prediction is ready.
    Updates win_pct; if results are already showing, flags a re-tween.
    Thread-safe: only mutates Python attributes, no DPG calls.
    """
    if "error" not in pred or pred.get("rank_vals"):
        draft.win_pct       = pred["blue_prob"]
        draft.prediction_src = "sheets"
        draft.prediction_ready = True   # main loop handles the re-tween


def _kick_off_bg_draft(blue_players, red_players):
    """
    Background chain: write picks → run subprocess → read results.
    All errors are soft — local results remain visible if any step fails.
    """
    def _on_write_done():
        draft.bg_status = "Running draft analysis…"
        run_draft_subprocess(
            on_done  = _on_subprocess_done,
            on_error = _on_bg_error,
        )

    def _on_write_error(msg):
        # Write failed — still attempt subprocess with existing sheet picks
        draft.bg_status = f"Sheet write failed ({msg}) — running analysis anyway…"
        run_draft_subprocess(
            on_done  = _on_subprocess_done,
            on_error = _on_bg_error,
        )

    def _on_subprocess_done(sh):
        draft.bg_status = "Reading results from sheet…"
        read_draft_results(sh,
                           on_done  = _apply_draft_results,
                           on_error = _on_bg_error)

    def _on_bg_error(msg):
        draft.bg_running = False
        draft.bg_status  = f"Rich analysis unavailable: {msg}"

    write_draft_picks(blue_players, red_players,
                      on_done  = _on_write_done,
                      on_error = _on_write_error)


def _apply_draft_results(results):
    """
    Called from background thread when the Draft Tool sheet has been parsed.
    Updates ban/comp data with richer sheet-sourced information.
    Thread-safe: only mutates Python attributes.
    """
    draft.bg_running = False
    draft.bg_status  = "Full analysis complete ✓"

    bans_b  = results.get("bans_blue",  [])
    bans_r  = results.get("bans_red",   [])
    comps_b = results.get("blue_comps", [])
    comps_r = results.get("red_comps",  [])

    if bans_b:
        draft.blue_bans       = [b["champion"] for b in bans_b]
        draft.ban_detail_blue = bans_b
    if bans_r:
        draft.red_bans        = [b["champion"] for b in bans_r]
        draft.ban_detail_red  = bans_r
    if comps_b:
        draft.comp_detail_blue = comps_b
        draft.blue_comps       = [c["archetype"] for c in comps_b]
    if comps_r:
        draft.comp_detail_red  = comps_r
        draft.red_comps        = [c["archetype"] for c in comps_r]


def _close_team_builder():
    if dpg.does_item_exist(_TB_WIN):
        dpg.delete_item(_TB_WIN)

# ---------------------------------------------------------------------------
# Main draw entry
# ---------------------------------------------------------------------------

def draw_draft(dl, vw, vh, fonts=None):
    if fonts:
        set_fonts(fonts)

    draft.tick()
    dpg.delete_item(dl, children_only=True)
    dpg.draw_rectangle((0,0),(vw,vh), fill=C["bg"], color=(0,0,0,0), parent=dl)

    phase = draft.phase

    if phase == DraftPhase.IDLE:
        _draw_idle(dl, vw, vh)
        return

    if phase == DraftPhase.TEAM_BUILD:
        _draw_waiting(dl, vw, vh)
        return

    team_h  = int(vh * 0.42)
    panel_y = team_h + 16
    pad     = 18
    col_w   = (vw - pad * 4) // 3

    _draw_team_area(dl, vw, team_h)

    if phase in (DraftPhase.RESULTS, DraftPhase.DONE) and draft.panel_alpha > 0:
        al = draft.panel_alpha
        _draw_blue_panel (dl, pad,              panel_y, col_w, vh - panel_y - pad, al)
        _draw_pvp_panel  (dl, pad*2 + col_w,    panel_y, col_w, vh - panel_y - pad, al)
        _draw_red_panel  (dl, pad*3 + col_w*2,  panel_y, col_w, vh - panel_y - pad, al)


def _draw_idle(dl, vw, vh):
    cx, cy = vw // 2, vh // 2
    t = (math.sin(time.monotonic() * 1.2) + 1) / 2
    a = int(100 + t * 120)

    _txt(dl, cx - 200, cy - 60, "DRAFT WAR ROOM",
         (*C["gold"][:3], a), 36, "raj_36")
    _txt(dl, cx - 170, cy - 10, "Build your teams and run the analysis",
         (*C["txt2"][:3], int(a * 0.7)), 18, "raj_18")

    bw, bh = 320, 64
    bx, by = cx - bw//2, cy + 40
    dpg.draw_rectangle((bx, by),(bx+bw, by+bh),
                        fill=(*C["gold_dk"][:3], 220),
                        color=(*C["gold"][:3], 220),
                        rounding=6, parent=dl)
    _txt(dl, bx + bw//2 - 110, by + 16, "CONFIGURE TEAMS",
         (*C["gold_lt"][:3], 230), 24, "raj_24")

    if dpg.is_mouse_button_clicked(0):
        mouse = dpg.get_mouse_pos(local=False)
        vp    = dpg.get_viewport_pos()
        rx    = mouse[0] - vp[0] - 68
        ry    = mouse[1] - vp[1] - 52
        if bx <= rx <= bx+bw and by <= ry <= by+bh:
            draft.phase = DraftPhase.TEAM_BUILD
            _open_team_builder(vw, vh)


def _draw_waiting(dl, vw, vh):
    cx, cy = vw // 2, vh // 2
    t = (math.sin(time.monotonic() * 1.4) + 1) / 2
    a = int(80 + t * 100)
    _txt(dl, cx - 200, cy - 20, "SELECT YOUR TEAMS ABOVE",
         (*C["txt_dim"][:3], a), 22, "raj_22")


# ---------------------------------------------------------------------------
# Team area (top strip)
# ---------------------------------------------------------------------------

def _draw_team_area(dl, vw, team_h):
    center = vw // 2
    meter_half = 110

    # Zone backgrounds
    dpg.draw_rectangle((0, 0),(center - meter_half, team_h),
                        fill=(*C["panel"][:3], 200), color=(0,0,0,0), parent=dl)
    dpg.draw_rectangle((center + meter_half, 0),(vw, team_h),
                        fill=(*C["panel"][:3], 200), color=(0,0,0,0), parent=dl)

    bf = draft.team_flash_blue
    rf = draft.team_flash_red
    if bf > 0:
        dpg.draw_rectangle((0, 0),(center - meter_half, team_h),
                            fill=(10,30,58,bf), color=(0,0,0,0), parent=dl)
    if rf > 0:
        dpg.draw_rectangle((center + meter_half, 0),(vw, team_h),
                            fill=(58,10,10,rf), color=(0,0,0,0), parent=dl)

    # Team labels + average scores (shown once results are in)
    _txt(dl, 24, 14, "BLUE TEAM", (*C["platinum"][:3], 220), 20, "raj_sb_22")
    _txt(dl, vw - 170, 14, "RED TEAM", (220, 90, 90, 220), 20, "raj_sb_22")
    if draft.phase in (DraftPhase.RESULTS, DraftPhase.DONE) and draft.panel_alpha > 0:
        al = draft.panel_alpha
        _txt(dl, 24, 38, f"avg score: {draft.blue_avg:.1f}",
             (*C["txt_dim"][:3], al), 14, "raj_r_14")
        _txt(dl, vw - 170, 38, f"avg score: {draft.red_avg:.1f}",
             (220, 90, 90, al), 14, "raj_r_14")

    # Center divider
    dpg.draw_line((center, 0),(center, team_h),
                  color=(*C["rule_gold"][:3], 180), thickness=1, parent=dl)

    # --- Horizontal hex slots ---
    blue = draft.blue
    red  = draft.red
    n    = 5

    # Blue team: spread across left half (minus meter gap)
    blue_area_w = center - meter_half - 40
    blue_slot_x = [40 + int(blue_area_w * (i + 0.5) / n) for i in range(n)]
    hex_r  = min(62, (blue_area_w // n) // 2 - 6)
    slot_y = team_h // 2

    for i in range(n):
        p   = blue[i] if i < len(blue) else None
        s   = draft.blue_slots.get(i, {"x_frac": 0.0, "alpha": 0})
        xfrac = s.get("x_frac", 0.0)
        al    = s.get("alpha", 0)
        if al <= 0 and not s.get("landed"):
            continue

        dest_x = blue_slot_x[i]
        sx     = int(-hex_r + (dest_x + hex_r) * xfrac)
        tier   = p.get("tier","Unranked") if p else "Unranked"
        name   = p.get("name","?")        if p else "?"
        role   = p.get("role", _ROLES[i]) if p else _ROLES[i]

        _hex_avatar(dl, sx, slot_y, hex_r, tier, name, alpha=al)
        _role_dot(dl, sx + hex_r - 6, slot_y - hex_r + 6, role, alpha=al)
        if al > 60:
            nw = len(name) * 9
            _txt(dl, sx - nw//2, slot_y + hex_r + 12, name.upper(),
                 (*C["txt"][:3], al), 20, "raj_20")
            tier_abbr = tier[:3].upper()
            _txt(dl, sx - len(tier_abbr)*6, slot_y + hex_r + 36, tier_abbr,
                 (*RANK_COLORS.get(tier, RANK_COLORS["Unranked"])[:3], al), 16, "raj_18")

    # Red team: spread across right half
    red_start    = center + meter_half + 20
    red_area_w   = vw - red_start - 20
    red_slot_x   = [red_start + int(red_area_w * (i + 0.5) / n) for i in range(n)]

    for i in range(n):
        p   = red[i] if i < len(red) else None
        s   = draft.red_slots.get(i, {"x_frac": 0.0, "alpha": 0})
        xfrac = s.get("x_frac", 0.0)
        al    = s.get("alpha", 0)
        if al <= 0 and not s.get("landed"):
            continue

        dest_x = red_slot_x[i]
        # Fly from right edge
        sx     = int(vw + hex_r - (vw + hex_r - dest_x) * xfrac)
        tier   = p.get("tier","Unranked") if p else "Unranked"
        name   = p.get("name","?")        if p else "?"
        role   = p.get("role", _ROLES[i]) if p else _ROLES[i]

        _hex_avatar(dl, sx, slot_y, hex_r, tier, name, alpha=al)
        _role_dot(dl, sx + hex_r - 6, slot_y - hex_r + 6, role, alpha=al)
        if al > 60:
            nw = len(name) * 9
            _txt(dl, sx - nw//2, slot_y + hex_r + 12, name.upper(),
                 (*C["txt"][:3], al), 20, "raj_20")
            tier_abbr = tier[:3].upper()
            _txt(dl, sx - len(tier_abbr)*6, slot_y + hex_r + 36, tier_abbr,
                 (*RANK_COLORS.get(tier, RANK_COLORS["Unranked"])[:3], al), 16, "raj_18")

    # Analysing pulse + background status
    if draft.phase == DraftPhase.ANALYSING:
        t  = (math.sin(draft.analyse_t * 2.2) + 1) / 2
        pa = int(100 + t * 130)
        _txt(dl, center - 90, team_h - 36, "ANALYSING...",
             (*C["gold_dk"][:3], pa), 20, "raj_20")
    elif draft.bg_running and draft.phase in (DraftPhase.RESULTS, DraftPhase.DONE):
        # Subtle running indicator after results appear
        t  = (math.sin(time.monotonic() * 2.0) + 1) / 2
        pa = int(60 + t * 60)
        _txt(dl, center - 120, team_h - 22, draft.bg_status,
             (*C["txt_dim"][:3], pa), 11, "raj_r_14")
    elif draft.bg_status and not draft.bg_running and draft.phase in (DraftPhase.RESULTS, DraftPhase.DONE):
        _txt(dl, center - 120, team_h - 22, draft.bg_status,
             (*C["txt_dim"][:3], 140), 11, "raj_r_14")

    # Re-tween win meter if a better prediction just arrived
    if draft.prediction_ready:
        draft.prediction_ready = False
        if draft.phase in (DraftPhase.RESULTS, DraftPhase.DONE):
            anim.tween(draft.win_pct_display, draft.win_pct, 900, "in_out",
                       on_update=lambda v: setattr(draft, "win_pct_display", v))

    # Win meter
    _draw_win_meter(dl, center, team_h)


def _draw_win_meter(dl, cx, team_h):
    ma = draft.win_meter_alpha
    if ma <= 0 and draft.phase not in (DraftPhase.RESULTS, DraftPhase.DONE):
        return

    mw   = 200
    mh   = 22
    my   = team_h // 2
    mx   = cx - mw // 2
    pct  = draft.win_pct_display / 100.0

    dpg.draw_rectangle((mx, my - mh//2),(mx+mw, my+mh//2),
                        fill=(*C["card"][:3], ma),
                        color=(*C["rule_dark"][:3], ma),
                        rounding=4, parent=dl)

    fill_w = int(mw * abs(pct - 0.5) * 2)
    col    = _win_color(draft.win_pct_display)
    if pct >= 0.5:
        dpg.draw_rectangle((mx + mw//2, my - mh//2 + 2),
                            (mx + mw//2 + fill_w//2, my + mh//2 - 2),
                            fill=(*col, ma), color=(0,0,0,0), rounding=3, parent=dl)
    else:
        dpg.draw_rectangle((mx + mw//2 - fill_w//2, my - mh//2 + 2),
                            (mx + mw//2, my + mh//2 - 2),
                            fill=(*col, ma), color=(0,0,0,0), rounding=3, parent=dl)

    label = f"{draft.win_pct_display:.1f}%"
    _txt(dl, cx - 26, my - 36, label, (*col, ma), 26, "raj_28")
    _txt(dl, cx - 22, my + mh//2 + 8, "BLUE WIN", (*C["txt_dim"][:3], ma), 12, "raj_sb_14")


def _win_color(pct):
    if pct >= 50:
        t = min((pct - 50) / 50, 1.0)
        return (int(130 + 70*t), int(140 + 28*t), int(50 + 56*t))
    else:
        t = min((50 - pct) / 50, 1.0)
        return (int(184), int(int(69*(1-t))), int(int(53*(1-t))))

# ---------------------------------------------------------------------------
# Analysis panels
# ---------------------------------------------------------------------------

def _draw_strategy_panel(dl, px, py, pw, ph, al, header, header_col,
                         bans, comps, ban_detail=None, comp_detail=None):
    """
    Shared renderer for blue/red strategy panels.
    ban_detail: optional list of rich ban dicts {champion, wr, games, priority}
    comp_detail: optional list of rich comp dicts {archetype, viability, synergy, picks}
    """
    _panel_bg(dl, px, py, px+pw, py+ph, header_col, al)
    _txt(dl, px+18, py+16, header, (*header_col[:3], al), 18, "raj_sb_18")
    dpg.draw_line((px+18, py+44),(px+pw-18, py+44),
                  color=(*C["rule_dark"][:3], al), thickness=1, parent=dl)

    _txt(dl, px+18, py+54, "PRIORITY BANS",
         (*C["txt2"][:3], al), 14, "raj_sb_16")

    has_rich_bans = bool(ban_detail)
    ban_h  = 58 if has_rich_bans else 44
    ban_y  = py + 76
    n_bans = max(1, len(bans)) if bans else 5
    slot_w = (pw - 36 - (n_bans - 1) * 6) // n_bans

    _PRIORITY_COLORS = {
        "HIGH":   C["loss"][:3],
        "MEDIUM": C["gold"][:3],
        "LOW":    C["txt2"][:3],
    }

    for i, champ in enumerate(bans[:5]):
        bx     = px + 18 + i * (slot_w + 6)
        detail = ban_detail[i] if has_rich_bans and i < len(ban_detail) else None
        dpg.draw_rectangle((bx, ban_y),(bx+slot_w, ban_y+ban_h),
                            fill=(*C["card"][:3], al),
                            color=(*C["loss"][:3], int(al*0.5)),
                            rounding=4, parent=dl)
        # X icon
        xs, xe = bx+8, bx+18
        ys, ye = ban_y+8, ban_y+18
        dpg.draw_line((xs,ys),(xe,ye), color=(*C["loss"][:3],al), thickness=1.5, parent=dl)
        dpg.draw_line((xe,ys),(xs,ye), color=(*C["loss"][:3],al), thickness=1.5, parent=dl)
        # Champion name
        name_y = (ban_y + 8) if has_rich_bans else (ban_y + ban_h//2 - 9)
        _txt(dl, bx+24, name_y, champ, (*C["txt"][:3], al), 13, "raj_16")
        # Rich detail: WR%, games, priority
        if detail:
            wr_str = str(detail.get("wr", "")).replace("%", "")
            g_str  = str(detail.get("games", ""))
            pri    = str(detail.get("priority", "")).upper()
            sub    = f"{wr_str}% WR · {g_str}g" if wr_str and g_str else ""
            if sub:
                _txt(dl, bx+8, ban_y+28, sub,
                     (*C["txt_dim"][:3], int(al*0.8)), 10, "raj_r_14")
            pc = _PRIORITY_COLORS.get(pri, C["txt_dim"][:3])
            if pri:
                _txt(dl, bx+8, ban_y+42, pri, (*pc, int(al*0.9)), 10, "raj_r_14")

    if not bans:
        _txt(dl, px+24, ban_y+14, "Run analysis to compute",
             (*C["txt_dim"][:3], al), 13, "raj_r_14")

    div_y = ban_y + ban_h + 14
    dpg.draw_line((px+18, div_y),(px+pw-18, div_y),
                  color=(*C["rule_dark"][:3], al), thickness=1, parent=dl)

    _txt(dl, px+18, div_y+10, "TEAM COMPOSITIONS",
         (*C["txt2"][:3], al), 14, "raj_sb_16")

    comp_y   = div_y + 34
    has_rich = bool(comp_detail)
    comp_h   = max(36, (ph - (comp_y - py) - 18) // 5)

    _VIAB_COLORS = {
        "STRONG":          (79, 168, 130),
        "VIABLE":          C["txt"][:3],
        "WEAK":            C["gold"][:3],
        "NOT RECOMMENDED": C["loss"][:3],
    }

    for i, comp in enumerate(comps[:5]):
        cy2    = comp_y + i * (comp_h + 5)
        detail = comp_detail[i] if has_rich and i < len(comp_detail) else None
        dpg.draw_rectangle((px+18, cy2),(px+pw-18, cy2+comp_h),
                            fill=(*C["card"][:3], al),
                            color=(*C["rule_dark"][:3], al),
                            rounding=4, parent=dl)
        dpg.draw_rectangle((px+18, cy2),(px+22, cy2+comp_h),
                            fill=(*header_col[:3], al),
                            color=(0,0,0,0), rounding=2, parent=dl)
        dpg.draw_text((px+28, cy2+comp_h//2-11), str(i+1),
                      color=(*C["txt_dim"][:3], al), size=14, parent=dl)
        if detail:
            arch = detail.get("archetype", comp)
            viab = detail.get("viability", "VIABLE")
            syn  = int(detail.get("synergy", 0))
            vc   = _VIAB_COLORS.get(viab, C["txt2"][:3])
            _txt(dl, px+46, cy2 + 4, arch, (*C["txt"][:3], al), 13, "raj_16")
            # Viability label right-aligned
            viab_short = viab[:4] if viab == "NOT RECOMMENDED" else viab
            vx = px + pw - 18 - len(viab_short) * 6 - 4
            _txt(dl, vx, cy2 + 4, viab_short, (*vc, al), 10, "raj_r_14")
            # Synergy dots
            if comp_h >= 36:
                dot_y = cy2 + comp_h - 13
                for d in range(5):
                    fc = (*C["gold"][:3], al) if d < syn else (*C["rule_dark"][:3], al)
                    dpg.draw_circle((px+46 + d*12, dot_y), 4,
                                    fill=fc, color=(0,0,0,0), parent=dl)
        else:
            _txt(dl, px+46, cy2+comp_h//2-11, comp, (*C["txt"][:3], al), 14, "raj_16")


def _draw_blue_panel(dl, px, py, pw, ph, al):
    _draw_strategy_panel(dl, px, py, pw, ph, al,
                         "BLUE TEAM STRATEGY", C["platinum"],
                         draft.blue_bans, draft.blue_comps,
                         ban_detail=draft.ban_detail_blue or None,
                         comp_detail=draft.comp_detail_blue or None)


def _draw_pvp_panel(dl, px, py, pw, ph, al):
    _panel_bg(dl, px, py, px+pw, py+ph, C["gold"], al)

    _txt(dl, px+18, py+16, "LANE ADVANTAGE",
         (*C["gold"][:3], al), 18, "raj_sb_18")
    dpg.draw_line((px+18, py+44),(px+pw-18, py+44),
                  color=(*C["rule_dark"][:3], al), thickness=1, parent=dl)

    note_col = (*C["txt_dim"][:3], int(al * 0.6))
    src_label = "Rank History + inhouse WR" if draft.prediction_src == "sheets" \
                else "Score ratio (local)"
    _txt(dl, px+18, py+52, f"Lane matchup  ·  Win % via {src_label}",
         note_col, 11, "raj_r_14")

    rows    = draft.pvp_rows
    row_h   = max(44, (ph - 80) // max(len(rows), 1)) if rows else 60
    start_y = py + 72

    role_cols = {
        "TOP":(180,100,60),"JGL":(80,160,80),
        "MID":(100,120,200),"BOT":(180,160,60),"SUP":(100,180,180),
    }

    if not rows:
        _txt(dl, px+18, start_y+16, "Configure teams to see matchups",
             (*C["txt_dim"][:3], al), 14, "raj_r_14")
        return

    for i, (role, blue_name, red_name, blue_win, note) in enumerate(rows):
        ry = start_y + i * (row_h + 6)

        dpg.draw_rectangle((px+12, ry),(px+pw-12, ry+row_h),
                            fill=(*C["card"][:3], al), color=(0,0,0,0), rounding=4, parent=dl)

        rc = role_cols.get(role, (120,120,120))
        dpg.draw_rectangle((px+12, ry),(px+16, ry+row_h),
                            fill=(*rc, al), color=(0,0,0,0), rounding=2, parent=dl)
        _txt(dl, px+22, ry+4, role, (*rc, al), 11, "raj_sb_11")

        # Blue name (left)
        _txt(dl, px+22, ry+row_h//2-8, blue_name.upper(),
             (*C["platinum"][:3], al), 15, "raj_18")

        # Win bar (centered)
        bar_x, bar_w, bh2 = px + pw//2 - 55, 110, 7
        bar_y = ry + row_h//2 - bh2//2

        dpg.draw_rectangle((bar_x, bar_y),(bar_x+bar_w, bar_y+bh2),
                            fill=(*C["bg"][:3], al), color=(0,0,0,0), rounding=3, parent=dl)
        fill_px = int(bar_w * blue_win / 100)
        bar_col = (79,168,130) if blue_win >= 50 else (184,69,53)
        dpg.draw_rectangle((bar_x, bar_y),(bar_x+fill_px, bar_y+bh2),
                            fill=(*bar_col, al), color=(0,0,0,0), rounding=3, parent=dl)

        pct_str = f"{blue_win:.0f}%"
        _txt(dl, px + pw//2 - 18, ry + row_h//2 - 19, pct_str, (*bar_col, al), 14, "raj_16")

        # Red name (right-aligned)
        rname_x = px + pw - 18 - len(red_name) * 9
        _txt(dl, rname_x, ry + row_h//2 - 8, red_name.upper(), (220, 90, 90, al), 15, "raj_18")

        # Note
        if row_h > 40 and note:
            _txt(dl, px+22, ry+row_h-15, note,
                 (*C["txt_dim"][:3], int(al*0.65)), 10, "raj_r_14")


def _draw_red_panel(dl, px, py, pw, ph, al):
    _draw_strategy_panel(dl, px, py, pw, ph, al,
                         "RED TEAM STRATEGY", (220, 90, 90, 255),
                         draft.red_bans, draft.red_comps,
                         ban_detail=draft.ban_detail_red or None,
                         comp_detail=draft.comp_detail_red or None)
