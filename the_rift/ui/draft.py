"""
Draft Tab — Phase 3: War Room.

Layout:
  Full-screen drag-and-drop team builder → Assembly animation → Analysis

Top strip:  [BLUE TEAM — 5 hexes horizontal] [WIN METER] [RED TEAM — 5 hexes horizontal]
Bottom:     [Blue bans + comps] [Player vs Player] [Red bans + comps]
"""
import math, time
import dearpygui.dearpygui as dpg
from theme import C, RANK_COLORS
from core.animations import anim
from data.reader import live, load_prediction_data, write_draft_picks, run_draft_subprocess, read_draft_results, write_activity_event
from data.config import load_config
from data import draft_engine as _eng

_ROLES = ["TOP", "JGL", "MID", "BOT", "SUP"]

_ROLE_COLORS = {
    "TOP": (180, 100,  60),
    "JGL": ( 80, 160,  80),
    "MID": (100, 120, 200),
    "BOT": (180, 160,  60),
    "SUP": (100, 180, 180),
}

# ---------------------------------------------------------------------------
# Player pool
# ---------------------------------------------------------------------------

def _is_real_player(name):
    """Return False for placeholder names that should never appear in the draft pool."""
    if not name or not str(name).strip():
        return False
    n = str(name).strip().upper()
    if n.startswith("PLAYER"):   # "PLAYER NAME", "PLAYER 1", "PLAYER_NAME" etc.
        return False
    if n in ("TBD", "TBA", "NAME", "UNKNOWN", ""):
        return False
    return True


def _get_player_pool():
    """
    Return player list for draft dropdowns.
    Prefer live.scout — it has both final_score (win probability) AND top_champs
    (ban/comp computation).  Fall back to rankings, then live.players, then config.
    All sources are filtered to remove placeholder names and deduplicated by name.
    """
    def _dedup(players, name_fn=lambda p: p.get("name", "")):
        seen, out = set(), []
        for p in players:
            n = name_fn(p)
            if _is_real_player(n) and n.lower() not in seen:
                seen.add(n.lower())
                out.append(p)
        return out

    if live.loaded and live.scout:
        return _dedup(live.scout) + _RANDOM_PLAYERS
    if live.loaded and live.rankings:
        return _dedup(live.rankings) + _RANDOM_PLAYERS
    if live.loaded and live.players:
        return _dedup(
            [{"name": p, "tier": "Unranked", "final_score": 50.0, "score": 50.0}
             for p in live.players]) + _RANDOM_PLAYERS
    cfg_players = load_config().get("players", [])
    return _dedup(
        [{"name": p if isinstance(p, str) else p.get("name", str(p)),
          "tier": "Unranked", "final_score": 50.0, "score": 50.0}
         for p in cfg_players]) + _RANDOM_PLAYERS


def _player_score(p):
    """Return a float strength score for a player dict."""
    try:
        return float(p.get("final_score", p.get("score", 50.0)))
    except (TypeError, ValueError):
        return 50.0

# ---------------------------------------------------------------------------
# Matchup computation
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Champion classification (mirrors fetch_ranks_gsheets.py)
# ---------------------------------------------------------------------------

_ROLE_NORM = {
    "TOP": "Top", "JGL": "Jungle", "MID": "Mid", "BOT": "Bot", "SUP": "Support"
}

_SUBCLASSES = {
    "engage":      {"Malphite","Amumu","Leona","Nautilus","Rakan","Rell","Alistar",
                    "Jarvan IV","Sejuani","Maokai","Ornn","Zac","Sion","Gragas",
                    "Wukong","Diana","Galio","Skarner","Yone","Kennen","Hecarim",
                    "Vi","Camille","Kled","Nocturne","Rek'Sai","Pantheon",
                    "Ambessa","Aurora"},
    "aoe_damage":  {"Orianna","Miss Fortune","Kennen","Rumble","Diana","Yone",
                    "Yasuo","Gangplank","Samira","Karthus","Brand","Zyra",
                    "Viktor","Cassiopeia","Nilah","Fiddlesticks","Aurora","Katarina",
                    "Vladimir","Lissandra","Wukong","Galio","Lillia","Briar",
                    "Vex","Hwei","Ziggs","Seraphine","Twitch","Jinx"},
    "frontline":   {"Malphite","Maokai","Ornn","Sion","Cho'Gath","Dr. Mundo",
                    "Tahm Kench","Shen","Braum","Taric","Alistar","Leona",
                    "Nautilus","Rell","Sejuani","Amumu","Rammus","Zac",
                    "Poppy","Skarner","K'Sante","Gragas","Volibear","Darius",
                    "Garen","Sett","Mordekaiser","Illaoi","Urgot","Aatrox","Ambessa"},
    "assassin_or_burst": {"Zed","Talon","Qiyana","Akali","LeBlanc","Fizz",
                          "Katarina","Ekko","Kha'Zix","Rengar","Evelynn",
                          "Shaco","Naafiri","Pyke","Syndra","Ahri","Veigar",
                          "Annie","Lux","Neeko","Zoe","Vex","Aurora",
                          "Nocturne","Diana","Briar","Lee Sin","Ambessa","Mel"},
    "cc":          {"Thresh","Morgana","Lux","Ahri","Ashe","Jhin","Veigar","Neeko",
                    "Twisted Fate","Blitzcrank","Pyke","Elise","Lee Sin","Hwei",
                    "Sejuani","Amumu","Leona","Nautilus","Maokai","Zyra","Bard",
                    "Renata Glasc","Rakan","Rell","Skarner"},
    "duelist":     {"Fiora","Tryndamere","Jax","Camille","Gwen","Irelia","Riven",
                    "Yasuo","Yone","Mordekaiser","Nasus","Yorick","Trundle",
                    "Volibear","Udyr","Kayle","Sett","Gnar","Ambessa","Warwick",
                    "Shen","Illaoi","Olaf","Renekton","Kled"},
    "waveclear":   {"Anivia","Ryze","Malzahar","Viktor","Ziggs","Sivir",
                    "Jinx","Orianna","Xerath","Taliyah","Aurelion Sol","Hwei",
                    "Twisted Fate","Corki","Heimerdinger","Seraphine","Veigar",
                    "Cassiopeia","Vladimir","Azir","Mel","Smolder"},
    "long_range":  {"Xerath","Vel'Koz","Lux","Ziggs","Jayce","Ezreal","Varus",
                    "Kog'Maw","Nidalee","Zoe","Hwei","Caitlyn","Senna",
                    "Seraphine","Karma","Viktor","Corki","Jhin","Ashe"},
    "disengage":   {"Janna","Gragas","Poppy","Alistar","Thresh","Braum",
                    "Karma","Lulu","Zilean","Anivia","Taliyah","Azir",
                    "Nami","Milio","Soraka"},
    "hypercarry":  {"Kog'Maw","Jinx","Twitch","Aphelios","Vayne","Kayle",
                    "Kindred","Smolder","Veigar","Cassiopeia","Karthus",
                    "Azir","Viktor","Tristana","Xayah","Zeri","Kai'Sa",
                    "Draven","Nilah","Master Yi"},
    "peel":        {"Lulu","Janna","Karma","Nami","Soraka","Yuumi","Milio",
                    "Renata Glasc","Taric","Zilean","Ivern","Braum","Shen",
                    "Orianna","Seraphine","Sona","Bard"},
}

_ARCHETYPES = {
    "Teamfight":         {"needs": {"engage": 1, "aoe_damage": 2, "frontline": 1},
                          "label": "Teamfight  (AoE + Engage)"},
    "Pick":              {"needs": {"assassin_or_burst": 2, "cc": 2},
                          "label": "Pick  (Catch + Burst)"},
    "Split Push":        {"needs": {"duelist": 1, "waveclear": 1},
                          "label": "Split Push  (1-3-1)"},
    "Poke / Siege":      {"needs": {"long_range": 2, "disengage": 1},
                          "label": "Poke / Siege  (Range + Zone)"},
    "Protect the Carry": {"needs": {"hypercarry": 1, "peel": 2},
                          "label": "Protect the Carry  (Shield/Peel)"},
    "Dive":              {"needs": {"engage": 2, "assassin_or_burst": 1, "frontline": 1},
                          "label": "Dive  (Hard Engage + Collapse)"},
    "Scaling":           {"needs": {"hypercarry": 1, "waveclear": 1, "disengage": 1},
                          "label": "Scaling  (Late-game win)"},
}

_ARCH_CONFLICTS = {
    "Dive":              {"hypercarry", "disengage"},
    "Teamfight":         {"disengage", "duelist"},
    "Poke / Siege":      {"engage", "assassin_or_burst"},
    "Protect the Carry": {"assassin_or_burst"},
    "Split Push":        {"engage", "aoe_damage"},
}

_ROLE_VALID = {
    "TOP": {"Aatrox","Ambessa","Aurora","Camille","Cho'Gath","Darius","Dr. Mundo",
            "Fiora","Gangplank","Garen","Gnar","Gwen","Illaoi","Irelia","Jax",
            "Jayce","K'Sante","Kayle","Kennen","Kled","Malphite","Maokai",
            "Mordekaiser","Nasus","Olaf","Ornn","Pantheon","Poppy","Quinn",
            "Renekton","Riven","Rumble","Sett","Shen","Sion","Tahm Kench",
            "Teemo","Trundle","Tryndamere","Urgot","Vladimir","Volibear",
            "Wukong","Yasuo","Yone","Yorick","Gragas","Akali","Warwick","Zac"},
    "JGL": {"Amumu","Ambessa","Bel'Veth","Briar","Diana","Ekko","Elise","Evelynn",
            "Fiddlesticks","Gragas","Graves","Hecarim","Ivern","Jarvan IV",
            "Karthus","Kayn","Kha'Zix","Kindred","Lee Sin","Lillia",
            "Master Yi","Nidalee","Nocturne","Nunu","Pantheon","Poppy",
            "Rammus","Rek'Sai","Rengar","Sejuani","Shaco","Shyvana",
            "Skarner","Taliyah","Udyr","Vi","Viego","Volibear","Warwick",
            "Wukong","Xin Zhao","Zac","Maokai","Trundle","Sylas"},
    "MID": {"Ahri","Akali","Akshan","Anivia","Annie","Aurelion Sol","Azir",
            "Cassiopeia","Corki","Diana","Ekko","Fizz","Galio","Hwei",
            "Irelia","Kassadin","Katarina","LeBlanc","Lissandra","Lux",
            "Malzahar","Mel","Naafiri","Neeko","Orianna","Pantheon","Qiyana",
            "Ryze","Sylas","Syndra","Taliyah","Talon","Tristana","Twisted Fate",
            "Veigar","Vex","Viktor","Vladimir","Xerath","Yasuo","Yone",
            "Zed","Zoe","Ziggs","Aurora","Jayce","Rumble","Heimerdinger","Zyra"},
    "BOT": {"Aphelios","Ashe","Caitlyn","Corki","Draven","Ezreal","Jhin",
            "Jinx","Kai'Sa","Kalista","Kog'Maw","Lucian","Miss Fortune",
            "Nilah","Samira","Sivir","Smolder","Tristana","Twitch","Varus",
            "Vayne","Xayah","Zeri","Ziggs","Senna"},
    "SUP": {"Alistar","Bard","Blitzcrank","Braum","Janna","Karma","Leona",
            "Lulu","Lux","Mel","Milio","Morgana","Nami","Nautilus","Pyke",
            "Rakan","Rell","Renata Glasc","Senna","Seraphine","Sona",
            "Soraka","Taric","Thresh","Yuumi","Zilean","Zyra","Xerath",
            "Vel'Koz","Maokai","Poppy","Tahm Kench","Galio"},
}

# INTENTIONAL: these "Random N" entries are placeholders in the draft pool to
# represent ad-hoc players who join our inhouse 5v5s but are NOT on the tier list
# and will NOT be added to the roster. Do not remove them and do not fold them
# into `_is_real_player()` rejection — they are a first-class part of the draft
# experience even though they have no scouting data.
_RANDOM_PLAYERS = [
    {"name": "Random 1", "tier": "Unranked", "final_score": 50.0, "score": 50.0,
     "top_champs": [], "is_random": True},
    {"name": "Random 2", "tier": "Unranked", "final_score": 50.0, "score": 50.0,
     "top_champs": [], "is_random": True},
    {"name": "Random 3", "tier": "Unranked", "final_score": 50.0, "score": 50.0,
     "top_champs": [], "is_random": True},
]


def _parse_wr(val):
    """Parse win rate from '68.3%' or numeric → float."""
    try:
        return float(str(val).replace("%", ""))
    except (ValueError, TypeError):
        return 50.0


def _champ_arch_score(champ, archetype):
    """0-1 fit score for a champion in an archetype."""
    arch  = _ARCHETYPES[archetype]
    total = sum(arch["needs"].values())
    hits  = sum(1 for need in arch["needs"] if champ in _SUBCLASSES.get(need, set()))
    score = hits / max(total, 1)
    for conflict in _ARCH_CONFLICTS.get(archetype, set()):
        if champ in _SUBCLASSES.get(conflict, set()):
            score -= 0.25
            break
    return max(score, 0.0)


def _compute_matchups(blue, red, blue_picks=None, red_picks=None):
    """Per-lane matchup. Delegates to draft_engine for champion + form awareness."""
    return _eng.compute_matchups(
        blue, red,
        primary_roles=live.primary_roles,
        blue_picks=blue_picks or [],
        red_picks=red_picks or [],
    )


def _compute_bans(opposing_players, own_picks=None):
    """
    Bans vs opposing team. Delegates to draft_engine for Bayesian-shrunk threat,
    form modifier, role-context boost, and counter-coverage discount when our
    team already counters a champion.
    """
    return _eng.recommend_bans(
        opposing_players,
        inhouse_champs=live.inhouse_champs,
        own_picks=own_picks or [],
        primary_roles=live.primary_roles,
        n_bans=5,
    )


def _compute_comps_detail(players, enemy_picks=None):
    """
    Per-player champion picks per archetype using beam search global optimisation.
    Adds team identity vector, synergy/anti-synergy pairs, AP/AD damage profile,
    counter-pick scoring vs locked enemy champions.
    """
    return _eng.recommend_comps(
        players,
        inhouse_champs=live.inhouse_champs,
        primary_roles=live.primary_roles,
        enemy_picks=enemy_picks or (),
        n_results=5,
    )

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
        self.blue             = []
        self.red              = []
        self.blue_slots       = {}
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
        self.pvp_rows         = []
        self.blue_bans        = []
        self.red_bans         = []
        self.blue_comps       = []
        self.red_comps        = []
        self.ban_detail_blue  = []
        self.ban_detail_red   = []
        self.comp_detail_blue = []
        self.comp_detail_red  = []
        self.prediction_src   = "local"
        self.bg_running       = False
        self.bg_status        = ""
        self.prediction_ready = False

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
# Drawing helpers
# ---------------------------------------------------------------------------

def _txt(dl, x, y, text, color, size, font_key=None):
    tag = dpg.draw_text((x, y), text, color=color, size=size, parent=dl)
    if font_key and font_key in _F:
        dpg.bind_item_font(tag, _F[font_key])
    return tag


def _hex_avatar(dl, cx, cy, r, tier, name, alpha=255):
    bc  = RANK_COLORS.get(tier, RANK_COLORS["Unranked"])
    try:
        from ui.inhouse import _get_avatar_tex
        tex = _get_avatar_tex(name)
    except Exception:
        tex = None
    if tex:
        try:
            dpg.draw_image(tex, (cx - r, cy - r), (cx + r, cy + r), parent=dl)
            return
        except Exception:
            pass
    pts = [(cx + r * math.cos(math.pi/6 + i * math.pi/3),
            cy + r * math.sin(math.pi/6 + i * math.pi/3)) for i in range(6)]
    dpg.draw_polygon(pts, fill=(*C["card"][:3], alpha),
                     color=(*bc[:3], alpha), thickness=2.5, parent=dl)
    initials = (name[:2] if name else "??").upper()
    dpg.draw_text((cx - len(initials)*8, cy - 13), initials,
                  color=(*C["txt"][:3], alpha), size=23, parent=dl)


def _role_dot(dl, cx, cy, role, alpha=255):
    col = _ROLE_COLORS.get(role, (120,120,120))
    dpg.draw_circle((cx, cy), 12, fill=(*col, alpha),
                    color=(0,0,0,0), parent=dl)
    dpg.draw_text((cx - 5, cy - 8), role[:1],
                  color=(*C["txt"][:3], alpha), size=18, parent=dl)


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
# Full-screen drag-and-drop team builder
# ---------------------------------------------------------------------------

_TB_SLOT_H = 70    # height of each role slot
_TB_CARD_W = 148   # width of player card in pool
_TB_CARD_H = 52    # height of player card in pool


class _TBState:
    def __init__(self):
        self.blue      = [None] * 5   # player dict or None per role
        self.red       = [None] * 5
        self.pool      = []            # all player dicts
        self.drag      = None          # player dict being dragged
        self.drag_from = None          # ("pool",) | ("blue",i) | ("red",i)
        self.drag_pos  = (0, 0)

_tb = _TBState()


def _tb_open(vw, vh):
    pool = _get_player_pool()
    _tb.blue      = [None] * 5
    _tb.red       = [None] * 5
    _tb.pool      = list(pool)
    _tb.drag      = None
    _tb.drag_from = None


def _tb_placed_names():
    placed = set()
    for p in _tb.blue:
        if p: placed.add(p["name"])
    for p in _tb.red:
        if p: placed.add(p["name"])
    return placed


def _tb_score_str(p):
    try:
        return f"{float(p.get('final_score', p.get('score', 50))):.0f}"
    except (ValueError, TypeError):
        return ""


def _draw_team_builder_full(dl, vw, vh):
    """Full-screen drawlist team builder with drag-and-drop."""
    dpg.draw_rectangle((0, 0), (vw, vh), fill=C["bg"], color=(0,0,0,0), parent=dl)

    hdr_h   = 60
    pool_h  = 170
    teams_h = vh - hdr_h - pool_h - 12

    # ── Header ───────────────────────────────────────────────────
    dpg.draw_rectangle((0, 0), (vw, hdr_h),
                        fill=(*C["panel"][:3], 235), color=(0,0,0,0), parent=dl)
    dpg.draw_line((0, hdr_h-1), (vw, hdr_h-1),
                  color=C["rule_dark"], thickness=1, parent=dl)
    _txt(dl, vw//2 - 160, 11, "CONFIGURE TEAMS", (*C["gold"][:3], 230), 29, "raj_36")

    # BEGIN ANALYSIS button
    bw, bh = 220, 38
    bx = vw - bw - 110
    by = (hdr_h - bh) // 2
    dpg.draw_rectangle((bx, by), (bx+bw, by+bh),
                        fill=(*C["gold_dk"][:3], 220), color=(*C["gold"][:3], 220),
                        rounding=4, parent=dl)
    _txt(dl, bx + 14, by + 7, "BEGIN ANALYSIS", (*C["gold_lt"][:3], 230), 22, "raj_sb_22")

    # CANCEL button
    cw, ch = 90, 38
    cx2 = vw - cw - 10
    cy2 = (hdr_h - ch) // 2
    dpg.draw_rectangle((cx2, cy2), (cx2+cw, cy2+ch),
                        fill=(*C["card"][:3], 160), color=(*C["rule_dark"][:3], 160),
                        rounding=4, parent=dl)
    _txt(dl, cx2 + 14, cy2 + 7, "CANCEL", (*C["txt2"][:3], 200), 20, "raj_sb_18")

    # ── Two team columns ─────────────────────────────────────────
    pad    = 24
    gap    = 20
    col_w  = (vw - pad*2 - gap) // 2
    blue_x = pad
    red_x  = pad + col_w + gap

    slots_top = hdr_h + 10
    slot_h    = max(36, int(max(52, (teams_h - 40) // 5) * 0.7))

    # Column backgrounds
    dpg.draw_rectangle((blue_x, slots_top), (blue_x+col_w, slots_top+teams_h),
                        fill=(*C["panel"][:3], 100), color=(*C["platinum"][:3], 50),
                        rounding=6, parent=dl)
    dpg.draw_rectangle((red_x, slots_top), (red_x+col_w, slots_top+teams_h),
                        fill=(*C["panel"][:3], 100), color=(220, 90, 90, 50),
                        rounding=6, parent=dl)

    _txt(dl, blue_x+14, slots_top+8, "BLUE TEAM", (*C["platinum"][:3], 220), 22, "raj_sb_22")
    _txt(dl, red_x+14,  slots_top+8, "RED TEAM",  (220, 90, 90, 220),      21, "raj_sb_22")

    _draw_role_slots(dl, blue_x, slots_top+36, col_w, _tb.blue, slot_h)
    _draw_role_slots(dl, red_x,  slots_top+36, col_w, _tb.red,  slot_h)

    # ── Player pool ───────────────────────────────────────────────
    pool_y = vh - pool_h
    dpg.draw_line((pad, pool_y), (vw-pad, pool_y),
                  color=(*C["rule_dark"][:3], 140), thickness=1, parent=dl)
    _txt(dl, pad, pool_y+4, "PLAYER POOL", (*C["txt2"][:3], 160), 22, "raj_sb_22")

    placed   = _tb_placed_names()
    pool_vis = [p for p in _tb.pool
                if p["name"] not in placed
                and (not _tb.drag or p["name"] != _tb.drag.get("name"))]

    cw2   = _TB_CARD_W
    ch2   = _TB_CARD_H
    cgap  = 8
    cols  = max(1, (vw - pad*2 + cgap) // (cw2 + cgap))
    ry    = pool_y + 22

    for i, p in enumerate(pool_vis):
        px2 = pad + (i % cols) * (cw2 + cgap)
        py2 = ry  + (i // cols) * (ch2 + cgap)
        if py2 + ch2 > vh - 4:
            break
        _draw_tb_card(dl, px2, py2, cw2, ch2, p)

    # Empty pool hint
    if not pool_vis and not _tb.drag:
        _txt(dl, pad, ry+8, "All players assigned.", (*C["txt_dim"][:3], 120), 18, "raj_sb_16")

    # ── Dragged card (top layer) ──────────────────────────────────
    if _tb.drag:
        mx, my = _tb.drag_pos
        _draw_tb_card(dl, mx - cw2//2, my - ch2//2, cw2, ch2, _tb.drag, dragging=True)


def _draw_role_slots(dl, x, y, width, slots, slot_h):
    """Draw 5 role slots for a team column."""
    for i, role in enumerate(_ROLES):
        sy = y + i * (slot_h + 6)
        p  = slots[i]
        rc = _ROLE_COLORS.get(role, (120, 120, 120))

        # Highlight when a dragged card is hovering over this slot
        hovering = (_tb.drag is not None and
                    _tb_slot_hit(x, sy, width, slot_h, _tb.drag_pos))

        bg_col  = (*C["card"][:3], 180 if p else 70)
        bdr_col = (*rc, 200 if (p or hovering) else 70)

        dpg.draw_rectangle((x+8, sy), (x+width-8, sy+slot_h),
                           fill=bg_col, color=bdr_col, rounding=5, parent=dl)

        if hovering:
            dpg.draw_rectangle((x+8, sy), (x+width-8, sy+slot_h),
                               fill=(*rc, 25), color=(*rc, 180),
                               rounding=5, parent=dl)

        # Role colour strip
        dpg.draw_rectangle((x+8, sy), (x+52, sy+slot_h),
                           fill=(*rc, 40), color=(0,0,0,0), rounding=5, parent=dl)
        dpg.draw_text((x+14, sy+slot_h//2-10), role, color=(*rc, 255), size=20, parent=dl)

        if p:
            name  = p.get("name", "?")
            tier  = p.get("tier", "Unranked")
            tc    = RANK_COLORS.get(tier, RANK_COLORS["Unranked"])
            name_sz = min(28, max(22, slot_h - 26))
            _txt(dl, x+60, sy+max(4, slot_h//2-name_sz//2-2), name.upper(), (*C["gold_lt"][:3], 235), name_sz, "raj_24")
            _txt(dl, x+60, sy+slot_h-20, tier[:3].upper(), (*tc[:3], 200), 19, "raj_sb_18")
            sc = _tb_score_str(p)
            if sc:
                _txt(dl, x+width-86, sy+max(4, slot_h//2-13), sc, (*C["txt2"][:3], 200), 22, "raj_20")
        else:
            _txt(dl, x+60, sy+slot_h//2-9, "drag here",
                 (*C["txt_dim"][:3], 70), 19, "raj_sb_18")


def _draw_tb_card(dl, x, y, w, h, player, dragging=False):
    """Draw a compact player card."""
    name      = player.get("name", "?")
    is_random = player.get("is_random", False)
    tier      = player.get("tier", "Unranked")
    tc        = RANK_COLORS.get(tier, RANK_COLORS["Unranked"])
    al        = 240 if dragging else 210

    if is_random:
        dpg.draw_rectangle((x, y), (x+w, y+h),
                            fill=(*C["card"][:3], 130 if not dragging else 190),
                            color=(100, 120, 170, 140 if not dragging else 200),
                            rounding=4, parent=dl)
        # Dashed top edge to signal "unknown player"
        dpg.draw_line((x+4, y+1), (x+w-4, y+1),
                      color=(100, 120, 170, 80), thickness=1, parent=dl)
        _txt(dl, x+10, y+5,    name.upper(), (130, 155, 210, al), 21, "raj_20")
        _txt(dl, x+10, y+h-19, "RAND",       ( 90, 110, 160, int(al*0.7)), 18, "raj_sb_18")
        _txt(dl, x+w-46, y+5,  "~50",        (*C["txt2"][:3], int(al*0.55)), 18, "raj_20")
    else:
        dpg.draw_rectangle((x, y), (x+w, y+h),
                            fill=(*C["card"][:3], 240 if dragging else 180),
                            color=(*tc[:3], 220 if dragging else 150),
                            rounding=4, parent=dl)
        _txt(dl, x+10, y+5,    name.upper(),      (*C["gold_lt"][:3], al), 23, "raj_24")
        _txt(dl, x+10, y+h-19, tier[:3].upper(),  (*tc[:3], int(al*0.85)), 20, "raj_sb_18")
        sc = _tb_score_str(player)
        if sc:
            _txt(dl, x+w-52, y+5, sc, (*C["txt2"][:3], int(al*0.9)), 20, "raj_20")


def _tb_slot_hit(sx, sy, sw, sh, pos):
    """True if pos=(mx,my) is inside the slot rect (accounting for the 8px inset)."""
    mx, my = pos
    return (sx+8 <= mx <= sx+sw-8) and (sy <= my <= sy+sh)


def _tb_handle_input(vw, vh):
    """Process mouse input for the team builder. Call every frame."""
    mouse = dpg.get_mouse_pos(local=False)
    vp    = dpg.get_viewport_pos()
    mx    = mouse[0] - vp[0] - 68   # content-relative x (68 = collapsed sidebar)
    my    = mouse[1] - vp[1] - 52   # content-relative y (52 = titlebar)

    _tb.drag_pos = (mx, my)

    hdr_h   = 60
    pool_h  = 170
    teams_h = vh - hdr_h - pool_h - 12
    pad     = 24
    gap     = 20
    col_w   = (vw - pad*2 - gap) // 2
    blue_x  = pad
    red_x   = pad + col_w + gap
    slot_h  = max(36, int(max(52, (teams_h - 40) // 5) * 0.7))
    slots_y = hdr_h + 46
    pool_y  = vh - pool_h

    cw2  = _TB_CARD_W
    ch2  = _TB_CARD_H
    cgap = 8
    cols = max(1, (vw - pad*2 + cgap) // (cw2 + cgap))
    ry   = pool_y + 22

    # ── Button clicks ─────────────────────────────────────────────
    if dpg.is_mouse_button_clicked(0):
        bw, bh = 220, 38
        bx = vw - bw - 110
        by = (hdr_h - bh) // 2
        if bx <= mx <= bx+bw and by <= my <= by+bh:
            _tb_begin_analysis()
            return

        cw3, ch3 = 90, 38
        cx2 = vw - cw3 - 10
        cy2 = (hdr_h - ch3) // 2
        if cx2 <= mx <= cx2+cw3 and cy2 <= my <= cy2+ch3:
            draft.phase = DraftPhase.IDLE
            return

    # ── Drag start ────────────────────────────────────────────────
    if dpg.is_mouse_button_down(0) and _tb.drag is None:
        placed   = _tb_placed_names()
        pool_vis = [p for p in _tb.pool if p["name"] not in placed]

        # Pool cards
        for i, p in enumerate(pool_vis):
            px2 = pad + (i % cols) * (cw2 + cgap)
            py2 = ry  + (i // cols) * (ch2 + cgap)
            if px2 <= mx <= px2+cw2 and py2 <= my <= py2+ch2:
                _tb.drag      = p
                _tb.drag_from = ("pool",)
                break

        # Blue team slots
        if _tb.drag is None:
            for i in range(5):
                sy = slots_y + i * (slot_h + 6)
                if _tb_slot_hit(blue_x, sy, col_w, slot_h, (mx, my)) and _tb.blue[i]:
                    _tb.drag      = _tb.blue[i]
                    _tb.drag_from = ("blue", i)
                    _tb.blue[i]   = None
                    break

        # Red team slots
        if _tb.drag is None:
            for i in range(5):
                sy = slots_y + i * (slot_h + 6)
                if _tb_slot_hit(red_x, sy, col_w, slot_h, (mx, my)) and _tb.red[i]:
                    _tb.drag      = _tb.red[i]
                    _tb.drag_from = ("red", i)
                    _tb.red[i]    = None
                    break

    # ── Drag end ──────────────────────────────────────────────────
    elif not dpg.is_mouse_button_down(0) and _tb.drag is not None:
        dropped = False

        for i in range(5):
            sy = slots_y + i * (slot_h + 6)
            if _tb_slot_hit(blue_x, sy, col_w, slot_h, (mx, my)):
                if _tb.blue[i]:
                    _tb_release_displaced(_tb.blue[i])
                _tb.blue[i] = _tb.drag
                dropped = True
                break

        if not dropped:
            for i in range(5):
                sy = slots_y + i * (slot_h + 6)
                if _tb_slot_hit(red_x, sy, col_w, slot_h, (mx, my)):
                    if _tb.red[i]:
                        _tb_release_displaced(_tb.red[i])
                    _tb.red[i] = _tb.drag
                    dropped = True
                    break

        if not dropped and _tb.drag_from:
            src = _tb.drag_from[0]
            if src == "blue":
                _tb.blue[_tb.drag_from[1]] = _tb.drag
            elif src == "red":
                _tb.red[_tb.drag_from[1]] = _tb.drag
            # pool: card just stays in pool (no slot to restore)

        _tb.drag      = None
        _tb.drag_from = None


def _tb_release_displaced(player):
    """Remove a displaced player from any slot so they return to the pool."""
    for i in range(5):
        if _tb.blue[i] and _tb.blue[i]["name"] == player["name"]:
            _tb.blue[i] = None
            return
        if _tb.red[i] and _tb.red[i]["name"] == player["name"]:
            _tb.red[i] = None
            return


def _analyse_teams(blue_players, red_players):
    """Core analysis pipeline. Populates draft state and starts assembly animation."""
    blue_avg = sum(_player_score(p) for p in blue_players) / max(len(blue_players), 1)
    red_avg  = sum(_player_score(p) for p in red_players)  / max(len(red_players),  1)
    total    = blue_avg + red_avg
    win_pct  = (blue_avg / total * 100) if total > 0 else 50.0
    win_pct  = max(25.0, min(75.0, win_pct))

    # Stage 1: recommend comps for both sides independently
    blue_comp_detail = _compute_comps_detail(blue_players)
    # Stage 2: red sees blue's likely picks, can be counter-aware
    blue_top_picks = [pk["champion"] for pk in (blue_comp_detail[0]["picks"]
                                                if blue_comp_detail else [])]
    red_comp_detail = _compute_comps_detail(red_players, enemy_picks=blue_top_picks)

    red_top_picks = [pk["champion"] for pk in (red_comp_detail[0]["picks"]
                                               if red_comp_detail else [])]

    # Stage 3: bans use our likely picks for coverage-discount on countered threats
    blue_bans, blue_ban_detail = _compute_bans(red_players, own_picks=blue_top_picks)
    red_bans,  red_ban_detail  = _compute_bans(blue_players, own_picks=red_top_picks)

    draft.blue_avg         = blue_avg
    draft.red_avg          = red_avg
    # Stage 4: matchups use top-comp picks for champion-level matchup awareness
    draft.pvp_rows         = _compute_matchups(blue_players, red_players,
                                                blue_picks=blue_top_picks,
                                                red_picks=red_top_picks)
    draft.blue_bans        = blue_bans
    draft.red_bans         = red_bans
    draft.blue_comps       = [c["archetype"] for c in blue_comp_detail]
    draft.red_comps        = [c["archetype"] for c in red_comp_detail]
    draft.ban_detail_blue  = blue_ban_detail
    draft.ban_detail_red   = red_ban_detail
    draft.comp_detail_blue = blue_comp_detail
    draft.comp_detail_red  = red_comp_detail
    draft.prediction_src   = "local"
    draft.prediction_ready = False

    draft.start_assembly(blue_players, red_players, win_pct)

    blue_names = [p["name"] for p in blue_players]
    red_names  = [p["name"] for p in red_players]
    # Log a DRAFT activity event so the Activity Feed reflects local analyses
    # (the Sheets subprocess path is disabled — see project notes).
    try:
        detail = (f"BLUE {' / '.join(blue_names)}  vs  "
                  f"RED {' / '.join(red_names)}  ({win_pct:.0f}% blue)")
        write_activity_event("DRAFT", "", detail)
    except Exception:
        pass
    # Keep the Rank History win-% prediction (different signal: strength-based,
    # updates win meter + per-lane bars but does NOT touch bans/comps).
    load_prediction_data(blue_names, red_names, on_done=_apply_prediction)

    # Sheets-subprocess pass is disabled: the local engine now produces the
    # full rich comps/bans on the spot. The subprocess used to overwrite them
    # with its older logic. If you ever want the backend rerun, re-enable
    # _kick_off_bg_draft below.
    # draft.bg_running = True
    # draft.bg_status  = "Writing picks to sheet…"
    # _kick_off_bg_draft(blue_players, red_players)


def _tb_begin_analysis():
    """Called when user clicks BEGIN ANALYSIS in the drag-and-drop builder."""
    pool_by_name = {p["name"]: p for p in _tb.pool}

    blue_players, red_players = [], []
    for i, role in enumerate(_ROLES):
        bp_src = _tb.blue[i]
        rp_src = _tb.red[i]

        bn = bp_src["name"] if bp_src else f"Blue {i+1}"
        rn = rp_src["name"] if rp_src else f"Red {i+1}"

        bp = dict(pool_by_name.get(bn, {"name": bn, "tier": "Unranked",
                                         "final_score": 50.0, "score": 50.0}))
        rp = dict(pool_by_name.get(rn, {"name": rn, "tier": "Unranked",
                                         "final_score": 50.0, "score": 50.0}))
        bp["role"] = role
        rp["role"] = role
        blue_players.append(bp)
        red_players.append(rp)

    _analyse_teams(blue_players, red_players)

# ---------------------------------------------------------------------------
# Background draft pipeline
# ---------------------------------------------------------------------------

def _apply_prediction(pred):
    """
    Called from background thread when Rank History prediction is ready.
    Updates win_pct AND per-lane pvp_rows using per-player strength scores.
    Thread-safe: only mutates Python attributes, no DPG calls.
    """
    has_data = pred.get("rank_vals") or not pred.get("error")
    if not has_data:
        return

    draft.win_pct        = pred["blue_prob"]
    draft.prediction_src = "sheets"
    draft.prediction_ready = True

    # Update per-lane matchup percentages with the better strength data
    strengths = pred.get("strengths", {})
    if strengths and draft.pvp_rows:
        updated = []
        for role, bn, rn, _old_pct, _old_note in draft.pvp_rows:
            bs    = strengths.get(bn, 0.5)
            rs    = strengths.get(rn, 0.5)
            total = bs + rs
            pct   = (bs / total * 100) if total > 0 else 50.0
            pct   = max(20.0, min(80.0, round(pct, 1)))

            # Generate a readable note from strength differential
            diff = bs - rs
            if   abs(diff) > 0.15: note = f"{'Blue' if diff>0 else 'Red'} strength edge"
            elif abs(diff) > 0.06: note = "Close matchup"
            else:                  note = "Even matchup"

            b_main = live.primary_roles.get(bn)
            r_main = live.primary_roles.get(rn)
            if b_main == role:            note += f"  ·  {bn} on main"
            elif b_main and b_main != role: note += f"  ·  {bn} off-role"
            if r_main == role:            note += f"  ·  {rn} on main"
            elif r_main and r_main != role: note += f"  ·  {rn} off-role"

            updated.append((role, bn, rn, pct, note.strip("  ·  ")))
        draft.pvp_rows = updated


def _kick_off_bg_draft(blue_players, red_players):
    def _on_write_done():
        draft.bg_status = "Running draft analysis…"
        run_draft_subprocess(on_done=_on_subprocess_done, on_error=_on_bg_error)

    def _on_write_error(msg):
        draft.bg_status = f"Sheet write failed ({msg}) — running analysis anyway…"
        run_draft_subprocess(on_done=_on_subprocess_done, on_error=_on_bg_error)

    def _on_subprocess_done(sh):
        draft.bg_status = "Reading results from sheet…"
        read_draft_results(sh, on_done=_apply_draft_results, on_error=_on_bg_error)

    def _on_bg_error(msg):
        draft.bg_running = False
        draft.bg_status  = f"Rich analysis unavailable: {msg}"

    write_draft_picks(blue_players, red_players,
                      on_done=_on_write_done, on_error=_on_write_error)


def _apply_draft_results(results):
    draft.bg_running = False
    draft.bg_status  = "Full analysis complete ✓"

    bans_b  = results.get("bans_blue",  [])
    bans_r  = results.get("bans_red",   [])
    comps_b = results.get("blue_comps", [])
    comps_r = results.get("red_comps",  [])

    # Augment backend comp results with engine-derived UI fields (win_condition,
    # spike, score_breakdown). Backend predates the engine module; this adds the
    # richer surface without touching fetch_ranks_gsheets.py.
    def _augment_comp(c):
        arch = c.get("archetype")
        if arch and arch in _eng.ARCHETYPES:
            ad = _eng.ARCHETYPES[arch]
            c.setdefault("win_condition", ad.get("win_condition", ""))
            c.setdefault("spike",         ad.get("spike", ""))
        # Score breakdown from the engine if backend didn't provide one
        if "score_breakdown" not in c:
            picks = c.get("picks") or []
            champs = [p.get("champion", "") for p in picks if p.get("champion")]
            if champs and arch in _eng.ARCHETYPES:
                comforts = [float(p.get("fit_score") or p.get("comfort") or 0.4)
                            for p in picks]
                try:
                    sb = _eng.score_team(champs, comforts, arch)
                    c["score_breakdown"] = {
                        "identity":  round(sb["identity"], 2),
                        "synergy":   round(sb["synergy"],  2),
                        "damage":    round(sb["damage"],   2),
                        "counter":   round(sb["counter"],  2),
                        "comfort":   round(sb["comfort"],  2),
                        "coherence": round(sb["coherence"],2),
                        "ap_ratio":  round(sb["ap_ratio"], 2),
                    }
                except Exception:
                    pass
        return c

    if bans_b:
        draft.blue_bans       = [b["champion"] for b in bans_b]
        draft.ban_detail_blue = bans_b
    if bans_r:
        draft.red_bans        = [b["champion"] for b in bans_r]
        draft.ban_detail_red  = bans_r
    if comps_b:
        draft.comp_detail_blue = [_augment_comp(dict(c)) for c in comps_b]
        draft.blue_comps       = [c["archetype"] for c in comps_b]
    if comps_r:
        draft.comp_detail_red  = [_augment_comp(dict(c)) for c in comps_r]
        draft.red_comps        = [c["archetype"] for c in comps_r]

# ---------------------------------------------------------------------------
# Main draw entry
# ---------------------------------------------------------------------------

def draw_draft(dl, vw, vh, fonts=None):
    if fonts:
        set_fonts(fonts)

    try:
        from ui.inhouse import _scan_local_avatars, _flush_pending
        _scan_local_avatars()
        _flush_pending()
    except Exception:
        pass

    draft.tick()
    dpg.delete_item(dl, children_only=True)
    dpg.draw_rectangle((0,0),(vw,vh), fill=C["bg"], color=(0,0,0,0), parent=dl)

    phase = draft.phase

    if phase == DraftPhase.IDLE:
        _draw_idle(dl, vw, vh)
        return

    if phase == DraftPhase.TEAM_BUILD:
        _draw_team_builder_full(dl, vw, vh)
        _tb_handle_input(vw, vh)
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

    _txt(dl, cx - 240, cy - 60, "DRAFT WAR ROOM",
         (*C["gold"][:3], a), 44, "raj_44")
    _txt(dl, cx - 200, cy - 4, "Build your teams and run the analysis",
         (*C["txt2"][:3], int(a * 0.7)), 23, "raj_20")

    bw, bh = 320, 64
    bx, by = cx - bw//2, cy + 40
    dpg.draw_rectangle((bx, by),(bx+bw, by+bh),
                        fill=(*C["gold_dk"][:3], 220),
                        color=(*C["gold"][:3], 220),
                        rounding=6, parent=dl)
    _txt(dl, bx + bw//2 - 130, by + 14, "CONFIGURE TEAMS",
         (*C["gold_lt"][:3], 230), 29, "raj_36")

    # ANALYSE DRAFT — shown when a previous draft has teams assigned
    has_prev = bool(draft.blue and len(draft.blue) > 0 and
                    any(isinstance(p, dict) for p in draft.blue))
    abw, abh = 280, 52
    abx = cx - abw // 2
    aby = by + bh + 18
    if has_prev:
        dpg.draw_rectangle((abx, aby),(abx+abw, aby+abh),
                            fill=(*C["card"][:3], 200),
                            color=(*C["platinum"][:3], 200),
                            rounding=6, parent=dl)
        _txt(dl, abx + 24, aby + 10, "◆  ANALYSE DRAFT",
             (*C["platinum"][:3], int(a * 0.95)), 27, "raj_36")

    if dpg.is_mouse_button_clicked(0):
        mouse = dpg.get_mouse_pos(local=False)
        vp    = dpg.get_viewport_pos()
        rx    = mouse[0] - vp[0] - 68
        ry    = mouse[1] - vp[1] - 52
        if bx <= rx <= bx+bw and by <= ry <= by+bh:
            draft.phase = DraftPhase.TEAM_BUILD
            _tb_open(vw, vh)
        elif has_prev and abx <= rx <= abx+abw and aby <= ry <= aby+abh:
            _analyse_teams(list(draft.blue), list(draft.red))

# ---------------------------------------------------------------------------
# Team area (top strip)
# ---------------------------------------------------------------------------

def _draw_team_area(dl, vw, team_h):
    center = vw // 2
    meter_half = 110

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

    _txt(dl, 24, 12, "BLUE TEAM", (*C["platinum"][:3], 220), 27, "raj_sb_22")
    _txt(dl, vw - 190, 12, "RED TEAM", (220, 90, 90, 220), 27, "raj_sb_22")
    if draft.phase in (DraftPhase.RESULTS, DraftPhase.DONE) and draft.panel_alpha > 0:
        al = draft.panel_alpha
        _txt(dl, 24, 42, f"avg score: {draft.blue_avg:.1f}",
             (*C["txt"][:3], al), 20, "raj_sb_18")
        _txt(dl, vw - 190, 42, f"avg score: {draft.red_avg:.1f}",
             (220, 110, 110, al), 20, "raj_sb_18")

    dpg.draw_line((center, 0),(center, team_h),
                  color=(*C["rule_gold"][:3], 180), thickness=1, parent=dl)

    blue = draft.blue
    red  = draft.red
    n    = 5

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
            nw = len(name) * 11
            _txt(dl, sx - nw//2, slot_y + hex_r + 12, name.upper(),
                 (*C["txt"][:3], al), 25, "raj_24")
            tier_abbr = tier[:3].upper()
            _txt(dl, sx - len(tier_abbr)*7, slot_y + hex_r + 40, tier_abbr,
                 (*RANK_COLORS.get(tier, RANK_COLORS["Unranked"])[:3], al), 19, "raj_18")

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
        sx     = int(vw + hex_r - (vw + hex_r - dest_x) * xfrac)
        tier   = p.get("tier","Unranked") if p else "Unranked"
        name   = p.get("name","?")        if p else "?"
        role   = p.get("role", _ROLES[i]) if p else _ROLES[i]

        _hex_avatar(dl, sx, slot_y, hex_r, tier, name, alpha=al)
        _role_dot(dl, sx + hex_r - 6, slot_y - hex_r + 6, role, alpha=al)
        if al > 60:
            nw = len(name) * 11
            _txt(dl, sx - nw//2, slot_y + hex_r + 12, name.upper(),
                 (*C["txt"][:3], al), 25, "raj_24")
            tier_abbr = tier[:3].upper()
            _txt(dl, sx - len(tier_abbr)*7, slot_y + hex_r + 40, tier_abbr,
                 (*RANK_COLORS.get(tier, RANK_COLORS["Unranked"])[:3], al), 19, "raj_18")

    if draft.phase == DraftPhase.ANALYSING:
        t  = (math.sin(draft.analyse_t * 2.2) + 1) / 2
        pa = int(100 + t * 130)
        _txt(dl, center - 110, team_h - 38, "ANALYSING...",
             (*C["gold_dk"][:3], pa), 25, "raj_24")
    elif draft.bg_running and draft.phase in (DraftPhase.RESULTS, DraftPhase.DONE):
        t  = (math.sin(time.monotonic() * 2.0) + 1) / 2
        pa = int(60 + t * 60)
        _txt(dl, center - 140, team_h - 24, draft.bg_status,
             (*C["txt2"][:3], pa), 19, "raj_sb_18")
    elif draft.bg_status and not draft.bg_running and draft.phase in (DraftPhase.RESULTS, DraftPhase.DONE):
        _txt(dl, center - 140, team_h - 24, draft.bg_status,
             (*C["txt2"][:3], 160), 19, "raj_sb_18")

    # NEW DRAFT button — visible in results/done phase
    if draft.phase in (DraftPhase.RESULTS, DraftPhase.DONE):
        nbw, nbh = 160, 34
        nbx = center - nbw // 2
        nby = team_h - nbh - 8
        dpg.draw_rectangle((nbx, nby), (nbx+nbw, nby+nbh),
                            fill=(*C["card"][:3], 200), color=(*C["gold"][:3], 180),
                            rounding=4, parent=dl)
        _txt(dl, nbx+16, nby+6, "◆  NEW DRAFT", (*C["gold_lt"][:3], 220), 21, "raj_sb_22")
        if dpg.is_mouse_button_clicked(0):
            mouse = dpg.get_mouse_pos(local=False)
            vp    = dpg.get_viewport_pos()
            rx2   = mouse[0] - vp[0] - 68
            ry2   = mouse[1] - vp[1] - 52
            if nbx <= rx2 <= nbx+nbw and nby <= ry2 <= nby+nbh:
                draft.reset()
                return

    if draft.prediction_ready:
        draft.prediction_ready = False
        if draft.phase in (DraftPhase.RESULTS, DraftPhase.DONE):
            anim.tween(draft.win_pct_display, draft.win_pct, 900, "in_out",
                       on_update=lambda v: setattr(draft, "win_pct_display", v))

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
    _txt(dl, cx - 32, my - 42, label, (*col, ma), 31, "raj_26")
    _txt(dl, cx - 32, my + mh//2 + 8, "BLUE WIN", (*C["txt"][:3], ma), 23, "raj_sb_22")


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
    _panel_bg(dl, px, py, px+pw, py+ph, header_col, al)
    _txt(dl, px+18, py+14, header, (*header_col[:3], al), 23, "raj_sb_22")
    dpg.draw_line((px+18, py+48),(px+pw-18, py+48),
                  color=(*C["rule_dark"][:3], al), thickness=1, parent=dl)

    _txt(dl, px+18, py+58, "PRIORITY BANS",
         (*C["gold_lt"][:3], al), 20, "raj_sb_18")

    has_rich_bans = bool(ban_detail)
    ban_h  = 78 if has_rich_bans else 52
    ban_y  = py + 84
    n_bans = max(1, len(bans)) if bans else 5
    slot_w = (pw - 36 - (n_bans - 1) * 6) // n_bans

    _PRIORITY_COLORS = {
        "HIGH":   C["loss"][:3],
        "MEDIUM": C["gold_lt"][:3],
        "LOW":    C["txt"][:3],
    }

    for i, champ in enumerate(bans[:5]):
        bx     = px + 18 + i * (slot_w + 6)
        detail = ban_detail[i] if has_rich_bans and i < len(ban_detail) else None
        dpg.draw_rectangle((bx, ban_y),(bx+slot_w, ban_y+ban_h),
                            fill=(*C["card"][:3], al),
                            color=(*C["loss"][:3], int(al*0.5)),
                            rounding=4, parent=dl)
        xs, xe = bx+8, bx+18
        ys, ye = ban_y+8, ban_y+18
        dpg.draw_line((xs,ys),(xe,ye), color=(*C["loss"][:3],al), thickness=1.5, parent=dl)
        dpg.draw_line((xe,ys),(xs,ye), color=(*C["loss"][:3],al), thickness=1.5, parent=dl)
        name_y = (ban_y + 6) if has_rich_bans else (ban_y + ban_h//2 - 10)
        _txt(dl, bx+24, name_y, champ, (*C["txt"][:3], al), 21, "raj_20")
        if detail:
            player = str(detail.get("player", ""))
            wr_val = detail.get("wr", "")
            g_val  = detail.get("games", 0)
            pri    = str(detail.get("priority", "")).upper()

            if player:
                # Combine player + WR on one compact line
                wr_str = str(wr_val).replace("%", "") if wr_val else ""
                g_str  = str(g_val) if g_val else ""
                if wr_str and g_str and int(float(g_str)) > 0:
                    sub = f"{player[:11]}  {wr_str}%wr  {g_str}g"
                else:
                    sub = player[:16]
                _txt(dl, bx+8, ban_y+32, sub,
                     (*C["txt"][:3], al), 18, "raj_sb_18")
            pc = _PRIORITY_COLORS.get(pri, C["txt"][:3])
            if pri:
                _txt(dl, bx+8, ban_y+53, pri, (*pc, al), 18, "raj_sb_18")

    if not bans:
        for i in range(5):
            bx = px + 18 + i * (slot_w + 6)
            dpg.draw_rectangle((bx, ban_y),(bx+slot_w, ban_y+ban_h),
                                fill=(*C["card"][:3], int(al*0.5)),
                                color=(*C["loss"][:3], int(al*0.25)),
                                rounding=4, parent=dl)
            _txt(dl, bx + slot_w//2 - 6, ban_y + ban_h//2 - 11, "?",
                 (*C["txt_dim"][:3], int(al*0.6)), 22, "raj_20")

    div_y = ban_y + ban_h + 14
    dpg.draw_line((px+18, div_y),(px+pw-18, div_y),
                  color=(*C["rule_dark"][:3], al), thickness=1, parent=dl)

    _txt(dl, px+18, div_y+10, "TEAM COMPOSITIONS",
         (*C["gold_lt"][:3], al), 20, "raj_sb_18")

    comp_y   = div_y + 36
    has_rich = bool(comp_detail)
    remaining = max(1, ph - (comp_y - py) - 10)
    n_comps  = max(1, len(comps)) if comps else 1
    # Need vertical room for arch + picks + win-cond + AP/AD at readable sizes
    comp_h   = max(78, (remaining - (n_comps-1)*5) // n_comps)

    _VIAB_COLORS = {
        "STRONG":          (79, 168, 130),
        "VIABLE":          C["txt"][:3],
        "WEAK":            C["gold"][:3],
        "NOT RECOMMENDED": C["loss"][:3],
    }

    for i, comp in enumerate(comps[:5]):
        cy2    = comp_y + i * (comp_h + 5)
        if cy2 + comp_h > py + ph:
            break
        detail = comp_detail[i] if has_rich and i < len(comp_detail) else None
        dpg.draw_rectangle((px+18, cy2),(px+pw-18, cy2+comp_h),
                            fill=(*C["card"][:3], al),
                            color=(*C["rule_dark"][:3], al),
                            rounding=4, parent=dl)
        dpg.draw_rectangle((px+18, cy2),(px+22, cy2+comp_h),
                            fill=(*header_col[:3], al),
                            color=(0,0,0,0), rounding=2, parent=dl)
        dpg.draw_text((px+26, cy2+comp_h//2-10), str(i+1),
                      color=(*C["txt2"][:3], al), size=20, parent=dl)
        if detail:
            arch  = detail.get("archetype", comp)
            viab  = detail.get("viability", "VIABLE")
            syn   = int(detail.get("synergy", 0))
            picks = detail.get("picks", [])
            wcond = detail.get("win_condition", "")
            spike = detail.get("spike", "")
            sb    = detail.get("score_breakdown", {}) or {}
            vc    = _VIAB_COLORS.get(viab, C["txt"][:3])
            _txt(dl, px+40, cy2 + 5, arch, (*C["gold_lt"][:3], al), 22, "raj_20")
            viab_short = viab[:4] if viab == "NOT RECOMMENDED" else viab
            vx = px + pw - 18 - len(viab_short) * 9 - 4
            _txt(dl, vx, cy2 + 6, viab_short, (*vc, al), 19, "raj_sb_18")
            if picks and comp_h >= 50:
                champ_str = "  ·  ".join(
                    p.get("champion", "") for p in picks[:5] if p.get("champion"))
                if champ_str:
                    _txt(dl, px+40, cy2 + 28, champ_str,
                         (*C["txt"][:3], al), 19, "raj_sb_18")
            # Win condition — bumped to readable size + brighter colour
            if wcond and comp_h >= 70:
                _txt(dl, px+40, cy2 + 52, "→ " + wcond,
                     (*C["txt"][:3], al), 18, "raj_sb_18")
            # AP/AD ratio — right side, same readable tier
            if sb and comp_h >= 70:
                ap_r = sb.get("ap_ratio", 0.5)
                ap_pct = int(round(ap_r * 100))
                ad_pct = 100 - ap_pct
                bd_str = f"AP/AD {ap_pct}/{ad_pct}"
                bdx = px + pw - 18 - len(bd_str) * 10 - 4
                _txt(dl, bdx, cy2 + 52, bd_str,
                     (*C["txt"][:3], al), 18, "raj_sb_18")
            # Synergy dots — top-right under viability label
            if comp_h >= 44:
                dot_y = cy2 + 33
                dot_start_x = px + pw - 18 - 5*14
                for d in range(5):
                    fc = (*C["gold"][:3], al) if d < syn else (*C["rule_dark"][:3], al)
                    dpg.draw_circle((dot_start_x + d*14, dot_y), 5,
                                    fill=fc, color=(0,0,0,0), parent=dl)
        else:
            text_y = cy2 + comp_h//2 - 11
            _txt(dl, px+40, text_y, comp, (*C["gold_lt"][:3], al), 22, "raj_20")


def _draw_blue_panel(dl, px, py, pw, ph, al):
    _draw_strategy_panel(dl, px, py, pw, ph, al,
                         "BLUE TEAM STRATEGY", C["platinum"],
                         draft.blue_bans, draft.blue_comps,
                         ban_detail=draft.ban_detail_blue or None,
                         comp_detail=draft.comp_detail_blue or None)


def _draw_pvp_panel(dl, px, py, pw, ph, al):
    _panel_bg(dl, px, py, px+pw, py+ph, C["gold"], al)

    _txt(dl, px+18, py+14, "LANE ADVANTAGE",
         (*C["gold"][:3], al), 23, "raj_sb_22")
    dpg.draw_line((px+18, py+48),(px+pw-18, py+48),
                  color=(*C["rule_dark"][:3], al), thickness=1, parent=dl)

    src_label = "Rank History + inhouse WR" if draft.prediction_src == "sheets" \
                else "Score ratio (local)"
    _txt(dl, px+18, py+54, f"Lane matchup  ·  Win % via {src_label}",
         (*C["txt"][:3], al), 18, "raj_sb_18")

    rows    = draft.pvp_rows
    row_h   = max(68, (ph - 86) // max(len(rows), 1)) if rows else 68
    start_y = py + 78

    if not rows:
        _txt(dl, px+18, start_y+16, "Configure teams to see matchups",
             (*C["txt_dim"][:3], al), 17, "raj_sb_16")
        return

    for i, (role, blue_name, red_name, blue_win, note) in enumerate(rows):
        ry = start_y + i * (row_h + 6)

        dpg.draw_rectangle((px+12, ry),(px+pw-12, ry+row_h),
                            fill=(*C["card"][:3], al), color=(0,0,0,0), rounding=4, parent=dl)

        rc = _ROLE_COLORS.get(role, (120,120,120))
        dpg.draw_rectangle((px+12, ry),(px+16, ry+row_h),
                            fill=(*rc, al), color=(0,0,0,0), rounding=2, parent=dl)
        _txt(dl, px+22, ry+4, role, (*rc, al), 19, "raj_sb_18")

        _txt(dl, px+22, ry+row_h//2-10, blue_name.upper(),
             (*C["platinum"][:3], al), 21, "raj_20")

        bar_x, bar_w, bh2 = px + pw//2 - 60, 120, 8
        bar_y = ry + row_h//2 - bh2//2

        dpg.draw_rectangle((bar_x, bar_y),(bar_x+bar_w, bar_y+bh2),
                            fill=(*C["bg"][:3], al), color=(0,0,0,0), rounding=3, parent=dl)
        fill_px = int(bar_w * blue_win / 100)
        bar_col = (79,168,130) if blue_win >= 50 else (184,69,53)
        dpg.draw_rectangle((bar_x, bar_y),(bar_x+fill_px, bar_y+bh2),
                            fill=(*bar_col, al), color=(0,0,0,0), rounding=3, parent=dl)

        pct_str = f"{blue_win:.0f}%"
        _txt(dl, px + pw//2 - 24, ry + row_h//2 - 25, pct_str, (*bar_col, al), 23, "raj_20")

        rname_x = px + pw - 18 - len(red_name) * 12
        _txt(dl, rname_x, ry + row_h//2 - 10, red_name.upper(), (220, 90, 90, al), 21, "raj_20")

        if row_h > 40 and note:
            _txt(dl, px+22, ry+row_h-21, note,
                 (*C["txt"][:3], al), 18, "raj_sb_18")


def _draw_red_panel(dl, px, py, pw, ph, al):
    _draw_strategy_panel(dl, px, py, pw, ph, al,
                         "RED TEAM STRATEGY", (220, 90, 90, 255),
                         draft.red_bans, draft.red_comps,
                         ban_detail=draft.ban_detail_red or None,
                         comp_detail=draft.comp_detail_red or None)
