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

# ---------------------------------------------------------------------------
# Team builder window config
# ---------------------------------------------------------------------------
_TB_WIN    = "draft_team_builder"
_TB_BUILT  = [False]

# ---------------------------------------------------------------------------
# Demo data — replaced by real Sheets player list when wired
# ---------------------------------------------------------------------------
_ALL_PLAYERS = [
    {"name": "Phantom",  "tier": "Challenger",  "score": 2840},
    {"name": "Ironclad", "tier": "Grandmaster", "score": 2710},
    {"name": "Vex",      "tier": "Master",      "score": 2590},
    {"name": "Shroud",   "tier": "Diamond",     "score": 2440},
    {"name": "Blaze",    "tier": "Diamond",     "score": 2310},
    {"name": "Kira",     "tier": "Emerald",     "score": 2180},
    {"name": "Dusk",     "tier": "Emerald",     "score": 2050},
    {"name": "Nox",      "tier": "Platinum",    "score": 1920},
    {"name": "Cinder",   "tier": "Platinum",    "score": 1800},
    {"name": "Riven",    "tier": "Gold",        "score": 1670},
    {"name": "Ember",    "tier": "Gold",        "score": 1540},
    {"name": "Lyra",     "tier": "Silver",      "score": 1410},
    {"name": "Torque",   "tier": "Silver",      "score": 1290},
    {"name": "Flux",     "tier": "Bronze",      "score": 1160},
    {"name": "Zeal",     "tier": "Bronze",      "score": 1040},
]
_PLAYER_NAMES = ["— Select —"] + [p["name"] for p in _ALL_PLAYERS]
_PLAYER_BY_NAME = {p["name"]: p for p in _ALL_PLAYERS}

_ROLES = ["TOP", "JGL", "MID", "BOT", "SUP"]

_DEMO_WIN_PCT = 61.4

_DEMO_BLUE_BANS = ["Zed", "Akali", "Fizz", "Rengar", "Katarina"]
_DEMO_RED_BANS  = ["Yasuo", "Irelia", "Jinx", "Thresh", "Hecarim"]

_DEMO_BLUE_COMPS = [
    "Engage (Engage/Dive)",
    "Poke (Range/Siege)",
    "Pick (CC/Burst)",
    "Split Push (1-3-1)",
    "Teamfight (AoE)",
]
_DEMO_RED_COMPS = [
    "Poke (Sustained dmg)",
    "Protect ADC (Shield)",
    "Engage (Hard CC)",
    "Wombo Combo (AoE)",
    "Split + Skirmish",
]

_DEMO_PVP = [
    # (role, blue_name, red_name, blue_win_pct, note)
    ("TOP", "Phantom",  "Shroud",  68, "Strong laner, early gap"),
    ("JGL", "Ironclad", "Blaze",   44, "Red favoured early"),
    ("MID", "Vex",      "Nox",     57, "Blue scaling advantage"),
    ("BOT", "Kira",     "Cinder",  61, "Blue hypercarry late"),
    ("SUP", "Dusk",     "Riven",   53, "Even, playmaking edge"),
]

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

    # Player names for dropdowns (skip "— Select —" sentinel)
    names = [p["name"] for p in _ALL_PLAYERS]

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
    blue_players, red_players = [], []
    for i, role in enumerate(_ROLES):
        bn = dpg.get_value(f"tb_blue_{i}")
        rn = dpg.get_value(f"tb_red_{i}")
        bp = dict(_PLAYER_BY_NAME.get(bn, {"name": bn, "tier": "Unranked", "score": 0}))
        rp = dict(_PLAYER_BY_NAME.get(rn, {"name": rn, "tier": "Unranked", "score": 0}))
        bp["role"] = role
        rp["role"] = role
        blue_players.append(bp)
        red_players.append(rp)

    if dpg.does_item_exist(_TB_WIN):
        dpg.delete_item(_TB_WIN)
    draft.start_assembly(blue_players, red_players, _DEMO_WIN_PCT)


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

    # Team labels
    _txt(dl, 24, 14, "BLUE TEAM", (*C["platinum"][:3], 220), 20, "raj_sb_22")
    _txt(dl, vw - 170, 14, "RED TEAM", (220, 90, 90, 220), 20, "raj_sb_22")

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

    # Analysing pulse
    if draft.phase == DraftPhase.ANALYSING:
        t = (math.sin(draft.analyse_t * 2.2) + 1) / 2
        pa = int(100 + t * 130)
        _txt(dl, center - 90, team_h - 36, "ANALYSING...",
             (*C["gold_dk"][:3], pa), 20, "raj_20")

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

def _draw_blue_panel(dl, px, py, pw, ph, al):
    _panel_bg(dl, px, py, px+pw, py+ph, C["platinum"], al)

    # Header
    _txt(dl, px+18, py+16, "BLUE TEAM STRATEGY",
         (*C["platinum"][:3], al), 18, "raj_sb_18")
    dpg.draw_line((px+18, py+44),(px+pw-18, py+44),
                  color=(*C["rule_dark"][:3], al), thickness=1, parent=dl)

    # --- Ban recommendations (5 slots) ---
    _txt(dl, px+18, py+54, "PRIORITY BANS",
         (*C["txt2"][:3], al), 14, "raj_sb_16")

    bans_per_row = 5
    ban_slot_w   = (pw - 36 - (bans_per_row-1)*6) // bans_per_row
    ban_h        = 44
    ban_y        = py + 76

    for i, champ in enumerate(_DEMO_BLUE_BANS[:bans_per_row]):
        bx = px + 18 + i * (ban_slot_w + 6)
        dpg.draw_rectangle((bx, ban_y),(bx+ban_slot_w, ban_y+ban_h),
                            fill=(*C["card"][:3], al),
                            color=(*C["loss"][:3], int(al*0.5)),
                            rounding=4, parent=dl)
        xs, xe = bx+8, bx+18
        ys, ye = ban_y+8, ban_y+18
        dpg.draw_line((xs,ys),(xe,ye), color=(*C["loss"][:3],al), thickness=1.5, parent=dl)
        dpg.draw_line((xe,ys),(xs,ye), color=(*C["loss"][:3],al), thickness=1.5, parent=dl)
        _txt(dl, bx+24, ban_y+ban_h//2-9, champ,
             (*C["txt"][:3], al), 14, "raj_16")

    # Divider
    div_y = ban_y + ban_h + 14
    dpg.draw_line((px+18, div_y),(px+pw-18, div_y),
                  color=(*C["rule_dark"][:3], al), thickness=1, parent=dl)

    # --- Team compositions ---
    _txt(dl, px+18, div_y + 10, "TEAM COMPOSITIONS",
         (*C["txt2"][:3], al), 14, "raj_sb_16")

    comp_y = div_y + 34
    comp_h = max(36, (ph - (comp_y - py) - 18) // 5)

    for i, comp in enumerate(_DEMO_BLUE_COMPS):
        cy2 = comp_y + i * (comp_h + 5)
        dpg.draw_rectangle((px+18, cy2),(px+pw-18, cy2+comp_h),
                            fill=(*C["card"][:3], al),
                            color=(*C["rule_dark"][:3], al),
                            rounding=4, parent=dl)
        dpg.draw_rectangle((px+18, cy2),(px+22, cy2+comp_h),
                            fill=(*C["platinum"][:3], al),
                            color=(0,0,0,0), rounding=2, parent=dl)
        num_t = dpg.draw_text((px+28, cy2+comp_h//2-11), str(i+1),
                               color=(*C["txt_dim"][:3], al), size=14, parent=dl)
        _txt(dl, px+46, cy2+comp_h//2-11, comp,
             (*C["txt"][:3], al), 16, "raj_18")


def _draw_pvp_panel(dl, px, py, pw, ph, al):
    _panel_bg(dl, px, py, px+pw, py+ph, C["gold"], al)

    _txt(dl, px+18, py+16, "PLAYER vs PLAYER",
         (*C["gold"][:3], al), 18, "raj_sb_18")
    dpg.draw_line((px+18, py+44),(px+pw-18, py+44),
                  color=(*C["rule_dark"][:3], al), thickness=1, parent=dl)

    note_col = (*C["txt_dim"][:3], int(al * 0.6))
    _txt(dl, px+18, py+52, "Head-to-head by role — historical matchup data",
         note_col, 12, "raj_r_14")

    row_h = max(44, (ph - 80) // 5)
    start_y = py + 72

    for i, (role, blue_name, red_name, blue_win, note) in enumerate(_DEMO_PVP):
        ry = start_y + i * (row_h + 6)

        dpg.draw_rectangle((px+12, ry),(px+pw-12, ry+row_h),
                            fill=(*C["card"][:3], al),
                            color=(0,0,0,0), rounding=4, parent=dl)

        # Role label
        role_cols = {
            "TOP":(180,100,60),"JGL":(80,160,80),
            "MID":(100,120,200),"BOT":(180,160,60),"SUP":(100,180,180)
        }
        rc = role_cols.get(role, (120,120,120))
        dpg.draw_rectangle((px+12, ry),(px+16, ry+row_h),
                            fill=(*rc, al), color=(0,0,0,0), rounding=2, parent=dl)
        _txt(dl, px+22, ry+4, role, (*rc, al), 11, "raj_sb_11")

        # Blue player name
        _txt(dl, px+22, ry+row_h//2-8, blue_name.upper(),
             (*C["platinum"][:3], al), 16, "raj_18")

        # Win bar (centered)
        bar_x   = px + pw//2 - 60
        bar_w   = 120
        bar_h_h = 6
        bar_y   = ry + row_h//2 - bar_h_h//2

        dpg.draw_rectangle((bar_x, bar_y),(bar_x+bar_w, bar_y+bar_h_h),
                            fill=(*C["bg"][:3], al), color=(0,0,0,0), rounding=3, parent=dl)
        fill_px = int(bar_w * blue_win / 100)
        bar_col = (79,168,130) if blue_win >= 50 else (184,69,53)
        dpg.draw_rectangle((bar_x, bar_y),(bar_x+fill_px, bar_y+bar_h_h),
                            fill=(*bar_col, al), color=(0,0,0,0), rounding=3, parent=dl)

        pct_str = f"{blue_win}%"
        _txt(dl, px + pw//2 - 16, ry + row_h//2 - 18, pct_str,
             (*bar_col, al), 14, "raj_16")

        # Red player name (right-aligned)
        rname_x = px + pw - 18 - len(red_name)*9
        _txt(dl, rname_x, ry + row_h//2 - 8, red_name.upper(),
             (220, 90, 90, al), 16, "raj_18")

        # Note below
        if row_h > 40:
            _txt(dl, px+22, ry+row_h-16, note,
                 (*C["txt_dim"][:3], int(al*0.65)), 11, "raj_r_14")


def _draw_red_panel(dl, px, py, pw, ph, al):
    _panel_bg(dl, px, py, px+pw, py+ph, (220, 90, 90, 255), al)

    _txt(dl, px+18, py+16, "RED TEAM STRATEGY",
         (220, 90, 90, al), 18, "raj_sb_18")
    dpg.draw_line((px+18, py+44),(px+pw-18, py+44),
                  color=(*C["rule_dark"][:3], al), thickness=1, parent=dl)

    _txt(dl, px+18, py+54, "PRIORITY BANS",
         (*C["txt2"][:3], al), 14, "raj_sb_16")

    bans_per_row = 5
    ban_slot_w   = (pw - 36 - (bans_per_row-1)*6) // bans_per_row
    ban_h        = 44
    ban_y        = py + 76

    for i, champ in enumerate(_DEMO_RED_BANS[:bans_per_row]):
        bx = px + 18 + i * (ban_slot_w + 6)
        dpg.draw_rectangle((bx, ban_y),(bx+ban_slot_w, ban_y+ban_h),
                            fill=(*C["card"][:3], al),
                            color=(184, 69, 53, int(al*0.5)),
                            rounding=4, parent=dl)
        xs, xe = bx+8, bx+18
        ys, ye = ban_y+8, ban_y+18
        dpg.draw_line((xs,ys),(xe,ye), color=(184,69,53,al), thickness=1.5, parent=dl)
        dpg.draw_line((xe,ys),(xs,ye), color=(184,69,53,al), thickness=1.5, parent=dl)
        _txt(dl, bx+24, ban_y+ban_h//2-9, champ,
             (*C["txt"][:3], al), 14, "raj_16")

    div_y = ban_y + ban_h + 14
    dpg.draw_line((px+18, div_y),(px+pw-18, div_y),
                  color=(*C["rule_dark"][:3], al), thickness=1, parent=dl)

    _txt(dl, px+18, div_y + 10, "TEAM COMPOSITIONS",
         (*C["txt2"][:3], al), 14, "raj_sb_16")

    comp_y = div_y + 34
    comp_h = max(36, (ph - (comp_y - py) - 18) // 5)

    for i, comp in enumerate(_DEMO_RED_COMPS):
        cy2 = comp_y + i * (comp_h + 5)
        dpg.draw_rectangle((px+18, cy2),(px+pw-18, cy2+comp_h),
                            fill=(*C["card"][:3], al),
                            color=(*C["rule_dark"][:3], al),
                            rounding=4, parent=dl)
        dpg.draw_rectangle((px+18, cy2),(px+22, cy2+comp_h),
                            fill=(220, 90, 90, al),
                            color=(0,0,0,0), rounding=2, parent=dl)
        _txt(dl, px+28, cy2+comp_h//2-11, str(i+1),
             (*C["txt_dim"][:3], al), 14)
        _txt(dl, px+46, cy2+comp_h//2-11, comp,
             (*C["txt"][:3], al), 16, "raj_18")
