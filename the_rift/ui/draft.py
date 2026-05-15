"""
Draft Tab — Phase 3: War Room.

Layout:
  Full-screen drag-and-drop team builder > Assembly animation > Analysis

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
from data.draft_board import (DraftBoardState, recommend_action,
                              DRAFT_SEQUENCE)
from data import draft_lcu
from data import champion_icons
from ui.effects import (draw_orbital_spinner, draw_drift_field,
                         draw_breathing_ring, breathing_alpha)

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
    """Parse win rate from '68.3%' or numeric > float."""
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
    IDLE        = "idle"          # now the mode-select landing
    TEAM_BUILD  = "team_build"
    ASSEMBLING  = "assembling"
    ANALYSING   = "analysing"
    RESULTS     = "results"
    DONE        = "done"
    BOARD       = "board"         # interactive tournament-draft board


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
        self.panel_alpha      = 0     # legacy master alpha, kept for compatibility
        self.panel_alpha_blue = 0
        self.panel_alpha_pvp  = 0
        self.panel_alpha_red  = 0
        self.lane_reveals     = [0.0] * 5  # 0..1 per lane card
        self.sweep_t          = 0.0        # 0..1 radar sweep during analysing
        self.chip_alpha       = 0          # factor-chip fade in hero meter
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
        # Interactive draft board (tournament-draft mode)
        self.board            = None    # DraftBoardState | None
        self.board_rec        = None    # cached recommend_action() result
        self.board_live       = False   # live Riot import vs manual entry
        self.board_pool_page    = 0     # legacy (unused, kept for compat)
        self.board_pool_search  = ""    # type-to-filter the manual pool grid
        self.board_pool_scroll  = 0     # row offset for the scrollable pool grid
        self._board_key_was_down = {}   # edge-detection for keyboard search input
        self._board_top_call_sig  = None # (champ, tag) — detect rec change
        self._board_top_call_anim = 1.0  # 0 = just appeared, 1 = settled
        self.board_live_session = None  # latest parsed LCU snapshot | None
        self.board_live_status  = ""    # poller status line for the header
        self.board_live_stop    = False # poller stop flag
        self._board_live_sig    = None  # last-mirrored snapshot signature

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
        # Radar scan sweep during analysing — left>right traversal
        anim.tween(0.0, 1.0, 1800, "in_out",
                   on_update=lambda v: setattr(self, "sweep_t", v))
        anim.tween(0, 1, 1, "linear", delay_ms=2000, on_done=self._show_results)

    def _show_results(self):
        self.phase = DraftPhase.RESULTS
        # Hero meter: arc gauge sweeps in, % counter rolls up
        anim.tween(50.0, self.win_pct, 1400, "out_cubic",
                   on_update=lambda v: setattr(self, "win_pct_display", v))
        anim.tween(0, 255, 500, "out_cubic",
                   on_update=lambda v: setattr(self, "win_meter_alpha", int(v)))
        # Factor chips drift in after meter settles
        anim.tween(0, 255, 500, "out_cubic", delay_ms=900,
                   on_update=lambda v: setattr(self, "chip_alpha", int(v)))
        # Staggered panel reveal: blue > pvp > red
        anim.tween(0, 255, 550, "out_cubic", delay_ms=400,
                   on_update=lambda v: setattr(self, "panel_alpha_blue", int(v)))
        anim.tween(0, 255, 550, "out_cubic", delay_ms=600,
                   on_update=lambda v: setattr(self, "panel_alpha_pvp",  int(v)))
        anim.tween(0, 255, 550, "out_cubic", delay_ms=800,
                   on_update=lambda v: setattr(self, "panel_alpha_red",  int(v)))
        # Master panel alpha kept for any legacy gates
        anim.tween(0, 255, 600, "out_cubic", delay_ms=400,
                   on_update=lambda v: setattr(self, "panel_alpha", int(v)))
        # Stagger lane card reveals after pvp panel fades in
        for i in range(5):
            def _make(idx=i):
                def _set(v): self.lane_reveals[idx] = float(v)
                return _set
            anim.tween(0.0, 1.0, 420, "out_cubic",
                       delay_ms=950 + i * 95,
                       on_update=_make(i))
        anim.tween(0, 1, 1, "linear", delay_ms=1500,
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


def _gradient_frame(dl, x1, y1, x2, y2, c_top, c_bot, alpha=255, layers=4):
    """Draw a vertical-gradient frame around an existing panel.
    Stacks `layers` rectangle outlines, each one pixel further out, with
    color interpolated from c_top (outer) to c_bot (inner) — creates a
    subtle team-color halo around the panel.
    """
    def lerp(a, b, t): return int(a + (b - a) * t)
    for i in range(layers):
        t = i / max(layers - 1, 1)
        r = lerp(c_top[0], c_bot[0], t)
        g = lerp(c_top[1], c_bot[1], t)
        b = lerp(c_top[2], c_bot[2], t)
        a = int(alpha * (1.0 - t * 0.55))  # outer brightest, fades inward
        dpg.draw_rectangle((x1 - i, y1 - i), (x2 + i, y2 + i),
                            fill=(0, 0, 0, 0),
                            color=(r, g, b, a),
                            thickness=1, rounding=6 + i, parent=dl)

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
        self.target    = "batch"       # "batch" | "board"
        self.board_live = False        # board mode: live Riot import
        self.board_side = "BLUE"       # board mode: which side is "us"

_tb = _TBState()


def _tb_open(vw, vh, target="batch", board_live=False):
    pool = _get_player_pool()
    _tb.blue      = [None] * 5
    _tb.red       = [None] * 5
    _tb.pool      = list(pool)
    _tb.drag      = None
    _tb.drag_from = None
    _tb.target    = target
    _tb.board_live = board_live
    _tb.board_side = "BLUE"


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
    _txt(dl, vw//2 - 180, 11, "CONFIGURE TEAMS", (*C["gold"][:3], 230), 29, "cinzel_28")

    # Board mode: "you are" side toggle (left of the action button)
    if _tb.target == "board":
        tg_w, tg_h = 150, 34
        tg_x = vw - 220 - 110 - tg_w - 14
        tg_y = (hdr_h - tg_h) // 2
        is_blue = _tb.board_side == "BLUE"
        dpg.draw_rectangle((tg_x, tg_y), (tg_x+tg_w, tg_y+tg_h),
                            fill=(*C["card"][:3], 170),
                            color=(*C["rule_dark"][:3], 160),
                            rounding=4, parent=dl)
        half = tg_w // 2
        dpg.draw_rectangle(
            (tg_x + (0 if is_blue else half), tg_y),
            (tg_x + (half if is_blue else tg_w), tg_y+tg_h),
            fill=(*(C["platinum"][:3] if is_blue else (210, 90, 90)), 150),
            color=(0, 0, 0, 0), rounding=4, parent=dl)
        _txt(dl, tg_x + 14, tg_y + 8, "BLUE",
             (*C["gold_lt"][:3], 235 if is_blue else 150), 17, "raj_sb_18")
        _txt(dl, tg_x + half + 18, tg_y + 8, "RED",
             (*C["gold_lt"][:3], 235 if not is_blue else 150), 17, "raj_sb_18")
        _txt(dl, tg_x, tg_y - 16, "YOU ARE",
             (*C["txt2"][:3], 150), 12, "raj_sb_12")

    # Action button (label depends on mode)
    bw, bh = 220, 38
    bx = vw - bw - 110
    by = (hdr_h - bh) // 2
    _act_label = ("START DRAFT BOARD" if _tb.target == "board"
                  else "BEGIN ANALYSIS")
    dpg.draw_rectangle((bx, by), (bx+bw, by+bh),
                        fill=(*C["gold_dk"][:3], 220), color=(*C["gold"][:3], 220),
                        rounding=4, parent=dl)
    _txt(dl, bx + 14, by + 7, _act_label, (*C["gold_lt"][:3], 230), 22, "raj_sb_22")

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
        # Rank-tier ambient backdrop: subtle pulsing tinted fill keyed to tier
        # color. Higher tiers feel "lit"; low tiers stay dim/cool.
        _t        = (math.sin(time.monotonic() * 1.4 + hash(name) % 100) + 1) / 2
        _pulse_a  = int(18 + _t * 26)
        dpg.draw_rectangle((x+1, y+1), (x+w-1, y+h-1),
                            fill=(*tc[:3], _pulse_a),
                            color=(0, 0, 0, 0), rounding=4, parent=dl)
        # Bottom edge accent strip in tier color — anchors the glow
        dpg.draw_rectangle((x+4, y+h-3), (x+w-4, y+h-1),
                            fill=(*tc[:3], 130),
                            color=(0, 0, 0, 0), rounding=1, parent=dl)
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
        # Board-mode "you are" side toggle
        if _tb.target == "board":
            tg_w, tg_h = 150, 34
            tg_x = vw - 220 - 110 - tg_w - 14
            tg_y = (hdr_h - tg_h) // 2
            if tg_x <= mx <= tg_x+tg_w and tg_y <= my <= tg_y+tg_h:
                _tb.board_side = "RED" if mx >= tg_x + tg_w // 2 else "BLUE"
                return

        bw, bh = 220, 38
        bx = vw - bw - 110
        by = (hdr_h - bh) // 2
        if bx <= mx <= bx+bw and by <= my <= by+bh:
            if _tb.target == "board":
                _board_begin()
            else:
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
# Interactive tournament-draft board (U1 layout + U2 interaction)
# ---------------------------------------------------------------------------

_BOARD_TAG_COL = {
    "POWER":  (230, 170, 60),
    "SAFE":   (90, 180, 120),
    "COUNTER": (212, 90, 80),
    "FLEX":   (155, 140, 222),
    "COMFORT": (150, 178, 208),
    "BAN-P1": (212, 110, 90),
    "BAN-P2": (212, 145, 80),
}


def _draw_glyph(dl, cx, cy, kind, size, color):
    """Tiny vector glyph for tag chips. `size` ~= total span."""
    s = max(3, size // 2)
    col = color
    if kind == "POWER":
        # Lightning bolt — angular zigzag polygon
        pts = [
            (cx,        cy - s),
            (cx - s + 1, cy - 1),
            (cx - 1,    cy - 1),
            (cx,        cy + s),
            (cx + s - 1, cy + 1),
            (cx + 1,    cy + 1),
        ]
        dpg.draw_polygon(pts, fill=col, color=(0, 0, 0, 0), parent=dl)
    elif kind == "SAFE":
        # Shield — flat top, pointed bottom
        pts = [
            (cx - s + 1, cy - s + 1),
            (cx + s - 1, cy - s + 1),
            (cx + s - 1, cy),
            (cx,        cy + s),
            (cx - s + 1, cy),
        ]
        dpg.draw_polygon(pts, fill=col, color=(0, 0, 0, 0), parent=dl)
    elif kind == "COUNTER":
        # Crossed swords
        dpg.draw_line((cx - s + 1, cy - s + 1), (cx + s - 1, cy + s - 1),
                      color=col, thickness=2.5, parent=dl)
        dpg.draw_line((cx - s + 1, cy + s - 1), (cx + s - 1, cy - s + 1),
                      color=col, thickness=2.5, parent=dl)
    elif kind == "FLEX":
        # Diamond
        pts = [(cx, cy - s), (cx + s, cy), (cx, cy + s), (cx - s, cy)]
        dpg.draw_polygon(pts, fill=col, color=(0, 0, 0, 0), parent=dl)
    elif kind == "COMFORT":
        # Checkmark
        dpg.draw_line((cx - s + 1, cy + 1),
                      (cx - 1,    cy + s - 2),
                      color=col, thickness=2.5, parent=dl)
        dpg.draw_line((cx - 1,    cy + s - 2),
                      (cx + s,    cy - s + 2),
                      color=col, thickness=2.5, parent=dl)
    elif kind in ("BAN-P1", "BAN-P2"):
        # Forbidden — circle + diagonal slash
        dpg.draw_circle((cx, cy), s - 1, fill=(0, 0, 0, 0),
                        color=col, thickness=2, parent=dl)
        dpg.draw_line((cx - s + 2, cy - s + 2), (cx + s - 2, cy + s - 2),
                      color=col, thickness=2, parent=dl)
    else:
        # Fallback dot
        dpg.draw_circle((cx, cy), max(2, s - 2), fill=col,
                        color=(0, 0, 0, 0), parent=dl)


def _draw_portrait(dl, x, y, size, champ_name, fallback_color, alpha=255,
                   rounding=6, border_w=2):
    """Champion square portrait. Falls back to a colored placeholder with
    the first letter of the champion name while the texture is loading
    or missing. Always draws something in the (x, y, size, size) region."""
    if champ_name:
        try:
            tex = champion_icons.get_texture(champ_name)
        except Exception:
            tex = None
    else:
        tex = None
    if tex:
        try:
            dpg.draw_image(tex, (x, y), (x + size, y + size), parent=dl)
        except Exception:
            tex = None
    if not tex:
        # Placeholder: filled square in fallback color, first letter centered
        dpg.draw_rectangle((x, y), (x + size, y + size),
                           fill=(*C["bg"][:3], int(alpha * 0.78)),
                           color=(*fallback_color[:3], int(alpha * 0.55)),
                           thickness=border_w, rounding=rounding, parent=dl)
        if champ_name:
            ch = champ_name[:1].upper()
            # Center the letter — rough heuristic for size at this scale
            font_sz = max(14, int(size * 0.55))
            font_key = None
            if font_sz >= 44:
                font_key = "raj_44"
            elif font_sz >= 36:
                font_key = "raj_36"
            elif font_sz >= 28:
                font_key = "raj_28"
            elif font_sz >= 24:
                font_key = "raj_24"
            else:
                font_key = "raj_20"
            _txt(dl, x + size // 2 - font_sz // 3,
                 y + size // 2 - font_sz // 2,
                 ch, (*fallback_color[:3], alpha), font_sz, font_key)
        return False
    # Texture loaded — draw thin border on top for polish
    dpg.draw_rectangle((x, y), (x + size, y + size),
                       fill=(0, 0, 0, 0),
                       color=(*fallback_color[:3], int(alpha * 0.85)),
                       thickness=border_w, rounding=rounding, parent=dl)
    return True


def _draw_tag_chip(dl, x, y, tag, alpha=255, big=False):
    """Filled pill with glyph + label. Returns the consumed width in px."""
    if not tag:
        return 0
    col = _BOARD_TAG_COL.get(tag, C["txt"][:3])
    h        = 28 if big else 22
    txt_sz   = 15 if big else 13
    font_key = "raj_sb_16" if big else "raj_sb_14"
    glyph_d  = h - 10
    label_w  = len(tag) * (8 if big else 7)
    pad_l    = 10 if big else 8
    pad_mid  = 6 if big else 5
    pad_r    = 12 if big else 10
    chip_w   = pad_l + glyph_d + pad_mid + label_w + pad_r
    # Pill
    dpg.draw_rectangle((x, y), (x + chip_w, y + h),
                       fill=(*col, int(alpha * 0.88)),
                       color=(*col, alpha),
                       rounding=h // 2, parent=dl)
    # Glyph (left)
    glyph_cx = x + pad_l + glyph_d // 2
    glyph_cy = y + h // 2
    bg_col   = (*C["bg"][:3], alpha)
    _draw_glyph(dl, glyph_cx, glyph_cy, tag, glyph_d, bg_col)
    # Label
    txt_x = glyph_cx + glyph_d // 2 + pad_mid
    txt_y = y + (h - txt_sz) // 2 - 2
    _txt(dl, txt_x, txt_y, tag, bg_col, txt_sz, font_key)
    return chip_w

# Click regions registered by _draw_board, consumed by _board_handle_input.
# Each entry: (x, y, w, h, action, payload)
_board_hits = []

# Mouse position in content-area coords, updated each frame by _draw_board.
# Lets every render helper compute hover state without re-doing the offset math.
_mouse_xy = (0, 0)


def _hover(x, y, w, h):
    mx, my = _mouse_xy
    return x <= mx <= x + w and y <= my <= y + h


# Manual-pool rect (set each draw, read by the mouse-wheel handler so it
# only scrolls when the cursor is actually over the pool region).
_pool_rect = None

# Mouse-wheel handler is registered once on the first board draw.
_wheel_registered = [False]

# Letter / digit keys for type-to-filter search input.
_SEARCH_LETTER_KEYS = (
    (dpg.mvKey_A, 'A'), (dpg.mvKey_B, 'B'), (dpg.mvKey_C, 'C'),
    (dpg.mvKey_D, 'D'), (dpg.mvKey_E, 'E'), (dpg.mvKey_F, 'F'),
    (dpg.mvKey_G, 'G'), (dpg.mvKey_H, 'H'), (dpg.mvKey_I, 'I'),
    (dpg.mvKey_J, 'J'), (dpg.mvKey_K, 'K'), (dpg.mvKey_L, 'L'),
    (dpg.mvKey_M, 'M'), (dpg.mvKey_N, 'N'), (dpg.mvKey_O, 'O'),
    (dpg.mvKey_P, 'P'), (dpg.mvKey_Q, 'Q'), (dpg.mvKey_R, 'R'),
    (dpg.mvKey_S, 'S'), (dpg.mvKey_T, 'T'), (dpg.mvKey_U, 'U'),
    (dpg.mvKey_V, 'V'), (dpg.mvKey_W, 'W'), (dpg.mvKey_X, 'X'),
    (dpg.mvKey_Y, 'Y'), (dpg.mvKey_Z, 'Z'),
)
_SEARCH_DIGIT_KEYS = (
    (dpg.mvKey_0, '0'), (dpg.mvKey_1, '1'), (dpg.mvKey_2, '2'),
    (dpg.mvKey_3, '3'), (dpg.mvKey_4, '4'), (dpg.mvKey_5, '5'),
    (dpg.mvKey_6, '6'), (dpg.mvKey_7, '7'), (dpg.mvKey_8, '8'),
    (dpg.mvKey_9, '9'),
)


def _filter_pool(pool, query):
    """Case-insensitive substring filter on champion name in (champ, role) tuples."""
    if not query:
        return pool
    q = query.upper()
    return [(c, r) for c, r in pool if q in c.upper()]


def _on_pool_wheel(sender, app_data):
    """Mouse-wheel callback: scroll the manual-pool grid when hovered."""
    if draft.phase != DraftPhase.BOARD or _pool_rect is None:
        return
    try:
        mouse = dpg.get_mouse_pos(local=False)
        vp = dpg.get_viewport_pos()
    except Exception:
        return
    mx = mouse[0] - vp[0] - 68
    my = mouse[1] - vp[1] - 52
    px1, py1, px2, py2 = _pool_rect
    if not (px1 <= mx <= px2 and py1 <= my <= py2):
        return
    # app_data: +1 wheel up, -1 wheel down — invert so up reduces scroll
    delta = -int(app_data)
    draft.board_pool_scroll = max(0, draft.board_pool_scroll + delta)


def _ensure_board_wheel():
    """Register the mouse-wheel handler once."""
    if _wheel_registered[0]:
        return
    try:
        with dpg.handler_registry():
            dpg.add_mouse_wheel_handler(callback=_on_pool_wheel)
        _wheel_registered[0] = True
    except Exception:
        pass


def _board_begin():
    """Build a DraftBoardState from the team-builder rosters and enter BOARD."""
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
    draft.board = DraftBoardState(blue_players, red_players,
                                  our_side=_tb.board_side)
    draft.board_live = _tb.board_live
    draft.board_pool_search = ""
    draft.board_pool_scroll = 0
    draft.board_live_session = None
    draft.board_live_status = ""
    draft.board_live_stop = False
    draft._board_live_sig = None
    draft.phase = DraftPhase.BOARD
    _board_recompute()
    if draft.board_live:
        import threading
        threading.Thread(target=_lcu_poll_loop, daemon=True,
                         name="lcu_poll").start()


def _board_recompute():
    b = draft.board
    if b is None:
        draft.board_rec = None
        return
    try:
        draft.board_rec = recommend_action(
            b, getattr(live, "inhouse_champs", {}) or {},
            getattr(live, "primary_roles", {}) or {}, n=6)
    except Exception as e:                       # pragma: no cover
        draft.board_rec = {
            "done": b.is_complete(), "action": b.current_action(),
            "kind": None, "our_turn": False, "suggestions": [],
            "target_comp": {}, "cohesion": [], "enemy_weakness": {},
            "notes": [f"recommend error: {e}"]}


def _board_apply(champ, role=None):
    if draft.board is None or not champ:
        return
    if draft.board.apply(champ, role):
        draft.board_pool_search = ""        # fresh action → reset search/scroll
        draft.board_pool_scroll = 0
        _board_recompute()


def _lcu_poll_loop():
    """Daemon: mirror the live League champ-select into draft.board_live_*.
    Only writes plain attributes — the render thread does the actual board
    mirror + recompute (same thread-safety pattern as the prediction thread)."""
    import threading  # noqa: F401  (kept local; thread already running)
    try:
        cli = draft_lcu.connect()
    except Exception:
        cli = None
    if cli is None:
        draft.board_live_status = "League client not found - manual entry"
        return
    try:
        idmap = draft_lcu.champion_id_map()
    except Exception:
        idmap = {}
    draft.board_live_status = "Connected - waiting for champ select…"
    while (draft.phase == DraftPhase.BOARD and draft.board_live
           and not draft.board_live_stop):
        try:
            snap = draft_lcu.parse_session(cli.champ_select(), idmap)
        except Exception:
            snap = None
        if snap:
            draft.board_live_session = snap
            draft.board_live_status = "LIVE - synced to champ select"
        else:
            draft.board_live_session = None
            draft.board_live_status = "Connected - waiting for champ select…"
        time.sleep(1.5)


def _board_live_sync():
    """Render-thread: fold the latest LCU snapshot into the board (only when
    it changed) so recommendations track the live draft."""
    snap = draft.board_live_session
    if not snap or draft.board is None:
        return
    sig = (snap.get("our_side"),
           snap.get("completed"),
           tuple(sorted(snap.get("bans", {}).get("BLUE", []))),
           tuple(sorted(snap.get("bans", {}).get("RED", []))),
           tuple(sorted(snap.get("picks", {}).get("BLUE", {}).items())),
           tuple(sorted(snap.get("picks", {}).get("RED", {}).items())))
    if sig == draft._board_live_sig:
        return
    draft._board_live_sig = sig
    draft.board.mirror(snap.get("picks", {}), snap.get("bans", {}),
                       snap.get("completed", 0), snap.get("our_side"))
    _board_recompute()


def _board_legal_pool(state, action):
    """[(champ, role|None)] the user may legally lock for `action`."""
    used = state.used_champs()
    rv = getattr(_eng, "ROLE_VALID", {}) or {}
    if action.kind == "pick":
        seen = {}
        for r in state.open_roles(action.side):
            for c in sorted(rv.get(r, ())):
                if c not in used and c not in seen:
                    seen[c] = r
        return sorted(seen.items())
    allc = set()
    for r in _ROLES:
        allc |= set(rv.get(r, ()))
    return [(c, None) for c in sorted(allc) if c not in used]


def _draw_board(dl, vw, vh):
    _board_hits.clear()
    _ensure_board_wheel()                   # one-time mouse-wheel handler
    champion_icons.flush_pending()          # register any downloaded icons
    global _mouse_xy
    try:
        mp = dpg.get_mouse_pos(local=False)
        vp = dpg.get_viewport_pos()
        _mouse_xy = (mp[0] - vp[0] - 68, mp[1] - vp[1] - 52)
    except Exception:
        _mouse_xy = (0, 0)
    b = draft.board
    if b is None:
        draft.phase = DraftPhase.IDLE
        return
    if draft.board_live:
        _board_live_sync()                 # fold latest LCU snapshot in
    rec = draft.board_rec or {}
    act = rec.get("action")
    our = b.our_side
    live_connected = (draft.board_live and draft.board_live_session
                      is not None)

    # ── Header ───────────────────────────────────────────────────────
    hdr_h = 54
    dpg.draw_rectangle((0, 0), (vw, hdr_h), fill=(*C["panel"][:3], 235),
                       color=(0, 0, 0, 0), parent=dl)
    dpg.draw_line((0, hdr_h - 1), (vw, hdr_h - 1),
                  color=C["rule_dark"], thickness=1, parent=dl)
    _txt(dl, 24, 10, "DRAFT BOARD", (*C["gold"][:3], 240), 32, "cinzel_32")
    if draft.board_live:
        st = draft.board_live_status or "Connecting…"
        st_col = (90, 195, 175) if live_connected else (210, 160, 70)
        _txt(dl, 260, 18, st[:46], (*st_col, 220), 17, "raj_sb_18")
    else:
        _txt(dl, 260, 18, "MANUAL", (*C["txt2"][:3], 200), 17, "raj_sb_18")
    side_col = C["platinum"][:3] if our == "BLUE" else (215, 95, 95)
    _txt(dl, vw - 340, 18, f"YOU: {our}", (*side_col, 235), 17, "raj_sb_18")

    # UNDO (manual only — in live the client is authoritative) + EXIT
    if not live_connected:
        ub_w, ub_h = 100, 38
        ub_x = vw - ub_w - 124
        ub_y = (hdr_h - ub_h) // 2
        can_undo = bool(b._history)
        dpg.draw_rectangle((ub_x, ub_y), (ub_x+ub_w, ub_y+ub_h),
                           fill=(*C["card"][:3], 175 if can_undo else 75),
                           color=(*C["rule_dark"][:3], 170),
                           rounding=5, parent=dl)
        _txt(dl, ub_x + 22, ub_y + 8, "UNDO",
             (*C["gold_lt"][:3], 230 if can_undo else 95), 20, "raj_sb_20")
        if can_undo:
            _board_hits.append((ub_x, ub_y, ub_w, ub_h, "undo", None))
    cb_w, cb_h = 100, 38
    cb_x = vw - cb_w - 14
    cb_y = (hdr_h - cb_h) // 2
    dpg.draw_rectangle((cb_x, cb_y), (cb_x+cb_w, cb_y+cb_h),
                       fill=(*C["card"][:3], 165),
                       color=(*C["rule_dark"][:3], 170), rounding=5, parent=dl)
    _txt(dl, cb_x + 26, cb_y + 8, "EXIT", (*C["txt2"][:3], 210), 20, "raj_sb_20")
    _board_hits.append((cb_x, cb_y, cb_w, cb_h, "exit", None))

    # ── Timeline strip (20 actions) ──────────────────────────────────
    tl_y = hdr_h + 10
    phase_h = 24
    cells_h = 64
    tl_h    = phase_h + cells_h
    cells_y = tl_y + phase_h
    cell_w  = (vw - 32) / 20.0

    # Phase header band: BANS 1 · PICKS 1 · BANS 2 · PICKS 2
    PHASE_LABEL_COLOR = (*C["gold_lt"][:3], 215)
    PHASE_DIV_COLOR   = (*C["gold_dk"][:3], 230)
    phase_spans = (("BANS 1", 0, 6), ("PICKS 1", 6, 12),
                   ("BANS 2", 12, 16), ("PICKS 2", 16, 20))
    # Soft background under the phase labels
    dpg.draw_rectangle((16, tl_y), (16 + 20 * cell_w, tl_y + phase_h),
                       fill=(*C["panel"][:3], 200),
                       color=(0, 0, 0, 0), rounding=3, parent=dl)
    for label, start, end in phase_spans:
        cx_lo = 16 + start * cell_w
        cx_hi = 16 + end   * cell_w
        lbl_w = len(label) * 8
        lx    = cx_lo + ((cx_hi - cx_lo) - lbl_w) // 2
        _txt(dl, lx, tl_y + 5, label, PHASE_LABEL_COLOR, 14, "raj_sb_14")
    # Vertical dividers between phases (after action 5, 11, 15)
    for boundary in (6, 12, 16):
        bx = int(16 + boundary * cell_w)
        dpg.draw_line((bx, tl_y), (bx, cells_y + cells_h),
                      color=PHASE_DIV_COLOR, thickness=2, parent=dl)
    # Outer baseline under the whole timeline
    dpg.draw_line((16, cells_y + cells_h),
                  (int(16 + 20 * cell_w), cells_y + cells_h),
                  color=(*C["rule_dark"][:3], 200),
                  thickness=1, parent=dl)

    for a in DRAFT_SEQUENCE:
        cx0 = 16 + a.idx * cell_w
        is_cur = (act is not None and a.idx == act.idx)
        done = a.idx < b.pointer
        side_c = C["platinum"][:3] if a.side == "BLUE" else (210, 90, 90)
        if is_cur:
            pulse = (math.sin(time.monotonic() * 4) + 1) / 2
            fill_a = int(70 + pulse * 90)
        elif done:
            fill_a = 60
        else:
            fill_a = 22
        dpg.draw_rectangle((cx0 + 1, cells_y),
                           (cx0 + cell_w - 1, cells_y + cells_h),
                           fill=(*side_c, fill_a),
                           color=(*side_c, 210 if is_cur else 80),
                           thickness=2 if is_cur else 1,
                           rounding=4, parent=dl)
        kind_c = (C["gold_lt"][:3] if a.kind == "pick" else (210, 120, 100))
        side_letter = "B" if a.side == "BLUE" else "R"
        label_str = f"{side_letter} {a.kind.upper()}"
        _txt(dl, cx0 + 6, cells_y + 6, label_str,
             (*kind_c, 230 if (is_cur or done) else 140), 16, "raj_sb_16")
        locked = b.locked_at(a.idx)         # exact (from history)
        if locked:
            _txt(dl, cx0 + 6, cells_y + 34, locked[:8],
                 (*C["txt"][:3], 230), 18, "raj_sb_18")

    # ── Team columns + center recommendation panel ───────────────────
    body_y = tl_y + tl_h + 14
    col_w = 250
    cen_x = 16 + col_w + 16
    cen_w = vw - 32 - (col_w + 16) * 2
    body_h = vh - body_y - 14

    _draw_board_team(dl, 16, body_y, col_w, body_h, b, "BLUE", act)
    _draw_board_team(dl, vw - 16 - col_w, body_y, col_w, body_h, b, "RED", act)
    _draw_board_center(dl, cen_x, body_y, cen_w, body_h, b, rec,
                       interactive=not live_connected)


def _draw_board_team(dl, x, y, w, h, b, side, act):
    accent = C["platinum"][:3] if side == "BLUE" else (215, 95, 95)
    _panel_bg(dl, x, y, x + w, y + h, accent, 255)
    on_clock = (act is not None and act.side == side)
    label = f"{side} TEAM" + ("   * ON THE CLOCK" if on_clock else "")
    _txt(dl, x + 14, y + 12, label, (*accent, 235), 24, "raj_sb_24")
    ry = y + 56
    slot_h = 56
    for i, role in enumerate(_ROLES):
        pl = b.players[side][i]
        champ = b.picks[side].get(role)
        dpg.draw_rectangle((x + 10, ry), (x + w - 10, ry + slot_h),
                           fill=(*C["card"][:3], 165),
                           color=(*C["rule_dark"][:3], 135),
                           rounding=5, parent=dl)
        # Role accent stripe (left edge)
        rc = _ROLE_COLORS.get(role, (120, 120, 120))
        dpg.draw_rectangle((x + 10, ry), (x + 14, ry + slot_h),
                           fill=(*rc, 220), color=(0, 0, 0, 0),
                           rounding=2, parent=dl)
        # Champion portrait (40×40, only when locked — otherwise blank)
        port_sz = 40
        port_x  = x + 20
        port_y  = ry + (slot_h - port_sz) // 2
        if champ:
            _draw_portrait(dl, port_x, port_y, port_sz, champ, rc,
                           alpha=240, rounding=5, border_w=2)
        else:
            # Subtle empty placeholder
            dpg.draw_rectangle((port_x, port_y),
                               (port_x + port_sz, port_y + port_sz),
                               fill=(*C["bg"][:3], 110),
                               color=(*rc, 80),
                               thickness=1, rounding=5, parent=dl)
        # Role + player text (shifted right of portrait)
        txt_x = port_x + port_sz + 8
        _txt(dl, txt_x, ry + 5, role, (*C["txt2"][:3], 190), 16, "raj_sb_16")
        _txt(dl, txt_x, ry + 26, (pl.get("name", "?")[:8]),
             (*C["txt"][:3], 225), 18, "raj_sb_18")
        # Locked-champion name (right side, smaller now since portrait conveys identity)
        cc = (*C["gold_lt"][:3], 240) if champ else (*C["txt2"][:3], 125)
        cstr = (champ or "—")[:8]
        ctw  = len(cstr) * 11
        _txt(dl, x + w - 16 - ctw, ry + 20, cstr, cc, 19, "raj_sb_20")
        ry += slot_h + 6
    # bans row
    _txt(dl, x + 14, ry + 6, "BANS", (*C["txt2"][:3], 185), 14, "raj_sb_14")
    by = ry + 30
    bw_each = (w - 28) // 5
    for j in range(5):
        bx = x + 14 + j * bw_each
        ch = b.bans[side][j] if j < len(b.bans[side]) else None
        dpg.draw_rectangle((bx, by), (bx + bw_each - 4, by + 32),
                           fill=(*C["bg"][:3], 185),
                           color=(210, 90, 90, 135), rounding=4, parent=dl)
        _txt(dl, bx + 5, by + 7, (ch or "—")[:6],
             (*(210, 130, 120), 230 if ch else 105), 14, "raj_sb_14")


def _draw_board_center(dl, x, y, w, h, b, rec, interactive=True):
    _gradient_frame(dl, x, y, x + w, y + h,
                    C["gold"][:3], C["gold_dk"][:3], alpha=150, layers=3)
    _panel_bg(dl, x, y, x + w, y + h, C["gold"], 255)

    if rec.get("done") or b.is_complete():
        _txt(dl, x + w//2 - 120, y + h//2 - 60, "DRAFT COMPLETE",
             (*C["gold"][:3], 235), 30, "cinzel_28")
        _txt(dl, x + w//2 - 150, y + h//2 - 18,
             "Full team comps locked - review the board",
             (*C["txt2"][:3], 180), 16, "raj_sb_14")
        nb_w, nb_h = 220, 46
        nbx = x + w//2 - nb_w//2
        nby = y + h//2 + 24
        dpg.draw_rectangle((nbx, nby), (nbx+nb_w, nby+nb_h),
                           fill=(*C["gold_dk"][:3], 220),
                           color=(*C["gold"][:3], 220), rounding=6, parent=dl)
        _txt(dl, nbx + 46, nby + 11, "NEW DRAFT",
             (*C["gold_lt"][:3], 235), 22, "raj_sb_22")
        _board_hits.append((nbx, nby, nb_w, nb_h, "new", None))
        return

    act = rec.get("action")
    our_turn = rec.get("our_turn")

    # ── Side-tinted top edge stripe (subtle side identity wash) ──────
    if act:
        side_tint = (90, 160, 240) if act.side == "BLUE" else (220, 110, 110)
        for i in range(10):
            ta = int(38 * (1 - i / 10))
            dpg.draw_line((x + 6, y + 2 + i),
                          (x + w - 6, y + 2 + i),
                          color=(*side_tint, ta),
                          thickness=1, parent=dl)

    # ── Action banner: side-tinted, phase + step counter ─────────────
    banner = (220, 170, 60) if our_turn else (120, 130, 150)
    dpg.draw_rectangle((x + 10, y + 10), (x + w - 10, y + 68),
                       fill=(*banner, 55), color=(*banner, 215),
                       thickness=2, rounding=5, parent=dl)
    if act:
        head = f"{'YOUR' if our_turn else 'OPPONENT'} {act.kind.upper()}"
        sub = f"{act.label}  ·  phase {act.phase}  ·  step {act.idx+1}/20"
    else:
        head, sub = "—", ""
    _txt(dl, x + 22, y + 18, head, (*C["gold_lt"][:3], 240), 26, "raj_sb_26")
    _txt(dl, x + 22, y + 48, sub, (*C["txt2"][:3], 215), 15, "raj_sb_16")

    ny = y + 80
    tc = rec.get("target_comp") or {}
    if tc.get("label"):
        _txt(dl, x + 16, ny, f"BUILD  ->  {tc.get('label','')[:42]}",
             (*C["gold"][:3], 225), 16, "raj_sb_16")
        ny += 23
    # Phase reason (the meaningful note, not the redundant header echo)
    for note in (rec.get("notes") or [])[1:2]:
        _txt(dl, x + 16, ny, note[:62], (*C["txt2"][:3], 205),
             14, "raj_sb_14")
        ny += 21
    for cw_ in (rec.get("cohesion") or [])[:2]:
        _txt(dl, x + 16, ny, f"!  {cw_[:56]}", (220, 140, 90, 230),
             15, "raj_sb_16")
        ny += 21
    for exp in (rec.get("exploit") or [])[:2]:
        _txt(dl, x + 16, ny, f"EXPLOIT  {exp[:52]}", (90, 195, 175, 230),
             15, "raj_sb_16")
        ny += 21

    # ── PRIMARY CALL — the #1 recommendation, emphasised ─────────────
    sug = rec.get("suggestions") or []
    pool_region_h = 240
    if sug:
        s0 = sug[0]
        tag = s0.get("tag", "")
        tcol = _BOARD_TAG_COL.get(tag, C["platinum"][:3])
        pc_h = 110
        ny += 8

        # Detect recommendation change → trigger slide-up ease-in
        sig = (s0.get("champion", ""), tag)
        if sig != draft._board_top_call_sig:
            draft._board_top_call_sig = sig
            draft._board_top_call_anim = 0.0
            def _set_tc(v):
                draft._board_top_call_anim = v
            anim.tween(0.0, 1.0, 300, "out_cubic", on_update=_set_tc)
        t = draft._board_top_call_anim
        anim_dy = int((1 - t) * 16)
        card_y = ny + anim_dy

        # Hover detection (brightens border, slight halo bump)
        hovered = (interactive
                   and _hover(x + 14, card_y, w - 28, pc_h))

        # Halo glow — tag-colored radiating outlines around the card (subtle)
        halo_dk = (max(0, tcol[0] - 90),
                   max(0, tcol[1] - 90),
                   max(0, tcol[2] - 90))
        halo_alpha = 130 if hovered else 90
        _gradient_frame(dl, x + 14, card_y, x + w - 14, card_y + pc_h,
                        c_top=tcol, c_bot=halo_dk,
                        alpha=halo_alpha, layers=4 if hovered else 3)
        # Backdrop
        dpg.draw_rectangle((x + 14, card_y), (x + w - 14, card_y + pc_h),
                           fill=(*tcol, 50 if hovered else 42),
                           color=(*tcol, 245 if hovered else 225),
                           thickness=3 if hovered else 2,
                           rounding=6, parent=dl)
        # Champion portrait (left, 96×96 with tag-colored border)
        portrait_sz = 96
        port_x = x + 20
        port_y = card_y + (pc_h - portrait_sz) // 2
        _draw_portrait(dl, port_x, port_y, portrait_sz,
                       s0.get("champion", ""), tcol,
                       alpha=245, rounding=8, border_w=3)
        # Text content shifted right of portrait
        text_x = port_x + portrait_sz + 18
        # "TOP CALL" caption + tag pill (same row)
        _txt(dl, text_x, card_y + 14, "TOP CALL",
             (*tcol, 230), 13, "raj_sb_14")
        _draw_tag_chip(dl, text_x + 96, card_y + 9, tag, alpha=245, big=True)
        # Champion name — the hero
        _txt(dl, text_x, card_y + 44, s0.get("champion", "?")[:16],
             (*C["gold_lt"][:3], 248), 36, "raj_36")
        # Why text
        _txt(dl, text_x, card_y + 88, str(s0.get("why", ""))[:54],
             (*C["txt2"][:3], 220), 17, "raj_sb_18")
        if interactive:
            _board_hits.append((x + 14, ny, w - 28, pc_h, "pick",
                                (s0.get("champion"), s0.get("role"))))
        ny += pc_h + 14

    # ── Alternatives ────────────────────────────────────────────────
    if len(sug) > 1:
        _txt(dl, x + 16, ny, "ALTERNATIVES", (*C["gold_lt"][:3], 215),
             16, "raj_sb_16")
        ny += 28
        row_h = 52
        for s in sug[1:6]:
            if ny + row_h > y + h - pool_region_h:
                break
            tag = s.get("tag", "")
            tcol = _BOARD_TAG_COL.get(tag, C["platinum"][:3])
            # Hover lift — brighten border + fill on mouseover
            alt_hover = (interactive
                         and _hover(x + 14, ny, w - 28, row_h - 6))
            # Backdrop card
            dpg.draw_rectangle((x + 14, ny), (x + w - 14, ny + row_h - 6),
                               fill=(*C["card"][:3], 210 if alt_hover else 175),
                               color=(*tcol, 220 if alt_hover else 170),
                               thickness=2 if alt_hover else 1,
                               rounding=5, parent=dl)
            # Mini tag pill (vertically centered with the row)
            chip_h = 22
            chip_y = ny + (row_h - 6 - chip_h) // 2
            chip_w_used = _draw_tag_chip(dl, x + 22, chip_y, tag,
                                          alpha=235, big=False)
            # Champion portrait (40×40)
            port_sz = 40
            port_x  = x + 22 + chip_w_used + 12
            port_y  = ny + (row_h - 6 - port_sz) // 2
            _draw_portrait(dl, port_x, port_y, port_sz,
                           s.get("champion", ""), tcol,
                           alpha=235, rounding=5, border_w=2)
            # Right column: champion name + why
            cx_x = port_x + port_sz + 12
            _txt(dl, cx_x, ny + 4, s.get("champion", "?")[:12],
                 (*C["gold_lt"][:3], 240), 22, "raj_sb_22")
            _txt(dl, cx_x, ny + 30, str(s.get("why", ""))[:42],
                 (*C["txt2"][:3], 195), 14, "raj_sb_14")
            if interactive:
                _board_hits.append((x + 14, ny, w - 28, row_h - 6, "pick",
                                    (s.get("champion"), s.get("role"))))
            ny += row_h + 4

    # ── Manual pool (bottom region: search box + scrollable grid) ────
    global _pool_rect
    if act is None:
        _pool_rect = None
        return
    if not interactive:                    # live: client is authoritative
        _pool_rect = None
        py = y + h - 40
        dpg.draw_line((x + 14, py), (x + w - 14, py),
                      color=(*C["rule_dark"][:3], 150), thickness=1,
                      parent=dl)
        _txt(dl, x + 16, py + 10,
             "Mirroring live champ select - picks/bans follow the client",
             (90, 195, 175, 210), 15, "raj_sb_16")
        return

    py = y + h - pool_region_h
    dpg.draw_line((x + 14, py), (x + w - 14, py),
                  color=(*C["rule_dark"][:3], 150), thickness=1, parent=dl)

    full_pool = _board_legal_pool(b, act)
    filtered = _filter_pool(full_pool, draft.board_pool_search)

    # Header: title (left) + result count (right)
    _txt(dl, x + 16, py + 8, "OR LOCK ANY CHAMPION",
         (*C["txt2"][:3], 215), 16, "raj_sb_16")
    if draft.board_pool_search:
        cnt_str = f"{len(filtered)} of {len(full_pool)}"
    else:
        cnt_str = f"{len(full_pool)} champions"
    cnt_w = len(cnt_str) * 8
    _txt(dl, x + w - 16 - cnt_w, py + 10, cnt_str,
         (*C["txt_dim"][:3], 195), 14, "raj_sb_14")

    # Search box
    sb_y = py + 36
    sb_h = 38
    sb_x = x + 16
    sb_w = w - 32
    dpg.draw_rectangle((sb_x, sb_y), (sb_x + sb_w, sb_y + sb_h),
                       fill=(*C["bg"][:3], 205),
                       color=(*C["gold_dk"][:3], 210),
                       thickness=2, rounding=6, parent=dl)
    _txt(dl, sb_x + 14, sb_y + 10, "SEARCH",
         (*C["txt2"][:3], 180), 14, "raj_sb_14")
    # Vertical divider after the SEARCH label
    dpg.draw_line((sb_x + 84, sb_y + 8), (sb_x + 84, sb_y + sb_h - 8),
                  color=(*C["rule_dark"][:3], 170),
                  thickness=1, parent=dl)
    # Query text with blinking caret
    cursor = "|" if int(time.monotonic() * 2) % 2 == 0 else " "
    if draft.board_pool_search:
        _txt(dl, sb_x + 96, sb_y + 6,
             draft.board_pool_search + cursor,
             (*C["gold_lt"][:3], 240), 22, "raj_sb_22")
    else:
        _txt(dl, sb_x + 96, sb_y + 8, cursor,
             (*C["gold_lt"][:3], 200), 22, "raj_sb_22")
        _txt(dl, sb_x + 108, sb_y + 10, "type to filter…",
             (*C["txt_dim"][:3], 150), 17, "raj_sb_18")
    # Clear "X" button (only when there's text)
    if draft.board_pool_search:
        cx_x = sb_x + sb_w - 36
        cx_y = sb_y + 7
        dpg.draw_rectangle((cx_x, cx_y), (cx_x + 24, cx_y + 24),
                           fill=(*C["card"][:3], 180),
                           color=(*C["rule_dark"][:3], 170),
                           rounding=4, parent=dl)
        _txt(dl, cx_x + 7, cx_y + 3, "X",
             (*C["gold_lt"][:3], 225), 18, "raj_sb_18")
        _board_hits.append((cx_x, cx_y, 24, 24, "clear_search", None))

    # Grid: scrollable, bigger cells
    gy0 = sb_y + sb_h + 8
    grid_bottom = y + h - 10
    gx_n = max(1, sb_w // 124)
    gw = sb_w // gx_n
    gh = 38
    visible_rows = max(1, (grid_bottom - gy0) // gh)
    total_rows = (len(filtered) + gx_n - 1) // gx_n if filtered else 0
    max_scroll = max(0, total_rows - visible_rows)
    draft.board_pool_scroll = max(0, min(draft.board_pool_scroll, max_scroll))

    # Stash region for the wheel handler
    _pool_rect = (sb_x, gy0, sb_x + sb_w, grid_bottom)

    if not filtered:
        _txt(dl, sb_x + 14, gy0 + 12,
             f"No champions match  '{draft.board_pool_search}'",
             (*C["txt_dim"][:3], 200), 16, "raj_sb_16")
        return

    start = draft.board_pool_scroll * gx_n
    end = start + visible_rows * gx_n
    for k_rel, (cmp_, role) in enumerate(filtered[start:end]):
        gx = sb_x + (k_rel % gx_n) * gw
        gy = gy0 + (k_rel // gx_n) * gh
        cell_hover = _hover(gx + 2, gy + 2, gw - 4, gh - 4)
        dpg.draw_rectangle((gx + 2, gy + 2), (gx + gw - 4, gy + gh - 4),
                           fill=(*C["bg"][:3], 220 if cell_hover else 170),
                           color=(*C["gold_lt"][:3], 220) if cell_hover
                                 else (*C["rule_dark"][:3], 140),
                           thickness=2 if cell_hover else 1,
                           rounding=4, parent=dl)
        _txt(dl, gx + 9, gy + 8, cmp_[:12],
             (*C["gold_lt"][:3], 245) if cell_hover
             else (*C["txt"][:3], 230),
             16, "raj_sb_16")
        _board_hits.append((gx + 2, gy + 2, gw - 4, gh - 4, "pick",
                            (cmp_, role)))

    # Scrollbar indicator on the right edge
    if max_scroll > 0:
        sb_track_x = sb_x + sb_w - 6
        sb_track_y0 = gy0 + 2
        sb_track_y1 = grid_bottom - 2
        track_h = sb_track_y1 - sb_track_y0
        dpg.draw_rectangle((sb_track_x, sb_track_y0),
                           (sb_track_x + 4, sb_track_y1),
                           fill=(*C["rule_dark"][:3], 110),
                           color=(0, 0, 0, 0), rounding=2, parent=dl)
        thumb_frac = max(0.08, visible_rows / max(total_rows, 1))
        thumb_h = max(22, int(track_h * thumb_frac))
        thumb_pos = int((draft.board_pool_scroll / max_scroll)
                        * (track_h - thumb_h))
        dpg.draw_rectangle((sb_track_x,
                            sb_track_y0 + thumb_pos),
                           (sb_track_x + 4,
                            sb_track_y0 + thumb_pos + thumb_h),
                           fill=(*C["gold_lt"][:3], 210),
                           color=(0, 0, 0, 0), rounding=2, parent=dl)


def _board_handle_input(vw, vh):
    # ── Keyboard: type-to-filter the manual pool ─────────────────────
    kw = draft._board_key_was_down
    for key, ch in _SEARCH_LETTER_KEYS:
        down = dpg.is_key_down(key)
        if down and not kw.get(key, False):
            draft.board_pool_search += ch
            draft.board_pool_scroll = 0
        kw[key] = down
    for key, ch in _SEARCH_DIGIT_KEYS:
        down = dpg.is_key_down(key)
        if down and not kw.get(key, False):
            draft.board_pool_search += ch
            draft.board_pool_scroll = 0
        kw[key] = down
    # Backspace pops last char
    bs = dpg.mvKey_Back
    bs_down = dpg.is_key_down(bs)
    if bs_down and not kw.get(bs, False) and draft.board_pool_search:
        draft.board_pool_search = draft.board_pool_search[:-1]
        draft.board_pool_scroll = 0
    kw[bs] = bs_down
    # Arrow keys scroll the grid (one row at a time)
    for key, step in ((dpg.mvKey_Down, 1), (dpg.mvKey_Up, -1),
                      (dpg.mvKey_Next, 5), (dpg.mvKey_Prior, -5)):
        d = dpg.is_key_down(key)
        if d and not kw.get(key, False):
            draft.board_pool_scroll = max(0, draft.board_pool_scroll + step)
        kw[key] = d

    # ── Mouse clicks against registered hit rects ────────────────────
    mouse = dpg.get_mouse_pos(local=False)
    vp = dpg.get_viewport_pos()
    mx = mouse[0] - vp[0] - 68
    my = mouse[1] - vp[1] - 52
    if not dpg.is_mouse_button_clicked(0):
        return
    for (hx, hy, hw, hh, kind, payload) in list(_board_hits):
        if hx <= mx <= hx + hw and hy <= my <= hy + hh:
            if kind == "exit":
                draft.board_live_stop = True
                draft.phase = DraftPhase.IDLE
            elif kind == "undo":
                if draft.board and draft.board.undo():
                    draft.board_pool_scroll = 0
                    draft.board_pool_search = ""
                    _board_recompute()
            elif kind == "new":
                draft.board_live_stop = True
                draft.board = None
                draft.board_rec = None
                draft.board_pool_scroll = 0
                draft.board_pool_search = ""
                draft.phase = DraftPhase.IDLE
            elif kind == "clear_search":
                draft.board_pool_search = ""
                draft.board_pool_scroll = 0
            elif kind == "pick" and payload:
                _board_apply(payload[0], payload[1])
            return


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

    if phase == DraftPhase.BOARD:
        _draw_board(dl, vw, vh)
        _board_handle_input(vw, vh)
        return

    team_h  = int(vh * 0.42)
    panel_y = team_h + 16
    pad     = 18
    col_w   = (vw - pad * 4) // 3

    _draw_team_area(dl, vw, team_h)

    if phase in (DraftPhase.RESULTS, DraftPhase.DONE):
        ph = vh - panel_y - pad
        ab = draft.panel_alpha_blue
        ap = draft.panel_alpha_pvp
        ar = draft.panel_alpha_red
        if ab > 0:
            _draw_blue_panel(dl, pad,              panel_y, col_w, ph, ab)
        if ap > 0:
            _draw_pvp_panel (dl, pad*2 + col_w,    panel_y, col_w, ph, ap)
        if ar > 0:
            _draw_red_panel (dl, pad*3 + col_w*2,  panel_y, col_w, ph, ar)


def _mode_cards(vw, vh):
    """Geometry for the three mode-select cards. Returns list of
    (key, x, y, w, h, title, subtitle)."""
    cw, chh = 300, 188
    gap = 28
    total = cw * 3 + gap * 2
    x0 = vw // 2 - total // 2
    y0 = vh // 2 - chh // 2 + 24
    return [
        ("batch", x0,                 y0, cw, chh, "BATCH ANALYSIS",
         "Assign 10 players, get bans / comps / win-meter at once"),
        ("board_manual", x0+cw+gap,   y0, cw, chh, "DRAFT BOARD",
         "Tournament pick/ban order - advice each slot (manual)"),
        ("board_live", x0+(cw+gap)*2, y0, cw, chh, "DRAFT BOARD - LIVE",
         "Auto-follow an in-progress Riot champ select"),
    ]


def _draw_idle(dl, vw, vh):
    """Mode-select landing shown when the Draft tab opens."""
    cx = vw // 2
    draw_drift_field(dl, 0, 0, vw, vh, alpha=180,
                     accent=C["gold"][:3], n_dots=22, seed=11)
    t = (math.sin(time.monotonic() * 1.2) + 1) / 2
    a = int(150 + t * 90)

    _txt(dl, cx - 150, vh // 2 - 150, "DRAFT WAR ROOM",
         (*C["gold"][:3], a), 40, "cinzel_44")
    _txt(dl, cx - 132, vh // 2 - 104, "Choose how you want to draft",
         (*C["txt2"][:3], 180), 21, "raj_20")

    mp = dpg.get_mouse_pos(local=False)
    vp = dpg.get_viewport_pos()
    rx = mp[0] - vp[0] - 68
    ry = mp[1] - vp[1] - 52

    for key, x, y, w, h, title, sub in _mode_cards(vw, vh):
        hot = x <= rx <= x + w and y <= ry <= y + h
        _panel_bg(dl, x, y, x + w, y + h,
                  accent_color=C["gold"] if hot else C["platinum"],
                  alpha=255)
        if hot:
            dpg.draw_rectangle((x, y), (x + w, y + h),
                               fill=(*C["gold"][:3], 16),
                               color=(*C["gold"][:3], 200),
                               rounding=6, parent=dl)
        _txt(dl, x + 20, y + 28, title, (*C["gold_lt"][:3], 235),
             25, "raj_sb_24")
        # word-wrapped subtitle
        words, line, ly = sub.split(), "", y + 76
        for wd in words:
            if len(line) + len(wd) + 1 > 30:
                _txt(dl, x + 20, ly, line, (*C["txt2"][:3], 190),
                     16, "raj_sb_14")
                ly += 22
                line = wd
            else:
                line = (line + " " + wd).strip()
        if line:
            _txt(dl, x + 20, ly, line, (*C["txt2"][:3], 190),
                 16, "raj_sb_14")
        _txt(dl, x + 20, y + h - 34,
             "CLICK TO START", (*C["gold"][:3], 200 if hot else 110),
             15, "raj_sb_14")

    # Re-analyse a previous batch draft, if one exists
    has_prev = bool(draft.blue and len(draft.blue) > 0 and
                    any(isinstance(p, dict) for p in draft.blue))
    abw, abh = 260, 44
    abx = cx - abw // 2
    aby = vh // 2 + 150
    if has_prev:
        dpg.draw_rectangle((abx, aby), (abx + abw, aby + abh),
                            fill=(*C["card"][:3], 190),
                            color=(*C["platinum"][:3], 180),
                            rounding=6, parent=dl)
        _txt(dl, abx + 22, aby + 9, "RE-ANALYSE PREVIOUS DRAFT",
             (*C["platinum"][:3], 220), 18, "raj_sb_18")

    if dpg.is_mouse_button_clicked(0):
        for key, x, y, w, h, _t, _s in _mode_cards(vw, vh):
            if x <= rx <= x + w and y <= ry <= y + h:
                if key == "batch":
                    draft.phase = DraftPhase.TEAM_BUILD
                    _tb_open(vw, vh, target="batch")
                elif key == "board_manual":
                    draft.phase = DraftPhase.TEAM_BUILD
                    _tb_open(vw, vh, target="board", board_live=False)
                elif key == "board_live":
                    draft.phase = DraftPhase.TEAM_BUILD
                    _tb_open(vw, vh, target="board", board_live=True)
                return
        if has_prev and abx <= rx <= abx + abw and aby <= ry <= aby + abh:
            _analyse_teams(list(draft.blue), list(draft.red))

# ---------------------------------------------------------------------------
# Team area (top strip)
# ---------------------------------------------------------------------------

def _draw_team_area(dl, vw, team_h):
    center = vw // 2
    meter_half = 168  # wider zone for the arc-gauge hero meter

    dpg.draw_rectangle((0, 0),(center - meter_half, team_h),
                        fill=(*C["panel"][:3], 200), color=(0,0,0,0), parent=dl)
    dpg.draw_rectangle((center + meter_half, 0),(vw, team_h),
                        fill=(*C["panel"][:3], 200), color=(0,0,0,0), parent=dl)
    # Center plate behind the gauge — slightly darker for hierarchy
    dpg.draw_rectangle((center - meter_half, 0), (center + meter_half, team_h),
                        fill=(*C["bg"][:3], 220), color=(0, 0, 0, 0), parent=dl)

    bf = draft.team_flash_blue
    rf = draft.team_flash_red
    if bf > 0:
        dpg.draw_rectangle((0, 0),(center - meter_half, team_h),
                            fill=(10,30,58,bf), color=(0,0,0,0), parent=dl)
    if rf > 0:
        dpg.draw_rectangle((center + meter_half, 0),(vw, team_h),
                            fill=(58,10,10,rf), color=(0,0,0,0), parent=dl)

    # Team headers — accent bar + bigger title + score badge
    blue_acc = C["platinum"][:3]
    red_acc  = (220, 100, 100)
    dpg.draw_rectangle((16, 14), (20, 50), fill=(*blue_acc, 230),
                       color=(0, 0, 0, 0), rounding=2, parent=dl)
    _txt(dl, 28, 12, "BLUE TEAM", (*blue_acc, 230), 29, "raj_sb_24")
    dpg.draw_rectangle((vw - 20, 14), (vw - 16, 50), fill=(*red_acc, 230),
                       color=(0, 0, 0, 0), rounding=2, parent=dl)
    # right-align red header
    rt_label = "RED TEAM"
    rt_w = len(rt_label) * 14
    _txt(dl, vw - 28 - rt_w, 12, rt_label, (*red_acc, 230), 29, "raj_sb_24")
    if draft.phase in (DraftPhase.RESULTS, DraftPhase.DONE) and draft.panel_alpha > 0:
        al = draft.panel_alpha
        # Big score badge
        b_score = f"{draft.blue_avg:.1f}"
        _txt(dl, 28, 44, b_score, (*C["gold_lt"][:3], al), 23, "raj_sb_22")
        _txt(dl, 28 + len(b_score) * 13, 50, "avg",
             (*C["txt2"][:3], al), 13, "raj_sb_12")
        r_score = f"{draft.red_avg:.1f}"
        _txt(dl, vw - 28 - len(r_score) * 13 - 30, 44, r_score,
             (*C["gold_lt"][:3], al), 23, "raj_sb_22")
        _txt(dl, vw - 28 - 22, 50, "avg",
             (*C["txt2"][:3], al), 13, "raj_sb_12")

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
        # Breathing glow ring on locked-in hexes (skip if still flying)
        if s.get("landed") and al > 200:
            draw_breathing_ring(dl, sx, slot_y, hex_r + 6,
                                C["platinum"], int(al * 0.45),
                                period=3.6, offset=i * 0.45)
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
        if s.get("landed") and al > 200:
            draw_breathing_ring(dl, sx, slot_y, hex_r + 6,
                                (220, 100, 100), int(al * 0.45),
                                period=3.6, offset=i * 0.45 + 1.8)
        _role_dot(dl, sx + hex_r - 6, slot_y - hex_r + 6, role, alpha=al)
        if al > 60:
            nw = len(name) * 11
            _txt(dl, sx - nw//2, slot_y + hex_r + 12, name.upper(),
                 (*C["txt"][:3], al), 25, "raj_24")
            tier_abbr = tier[:3].upper()
            _txt(dl, sx - len(tier_abbr)*7, slot_y + hex_r + 40, tier_abbr,
                 (*RANK_COLORS.get(tier, RANK_COLORS["Unranked"])[:3], al), 19, "raj_18")

    if draft.phase == DraftPhase.ANALYSING:
        # Left-to-right scan line sweeping across both teams.
        sw   = draft.sweep_t
        sx   = int(vw * sw)
        # Vertical sweep line with soft halo
        for dx, alpha in ((-12, 30), (-8, 60), (-4, 110), (0, 200), (4, 110), (8, 60), (12, 30)):
            dpg.draw_line((sx + dx, 8), (sx + dx, team_h - 8),
                          color=(*C["gold"][:3], alpha),
                          thickness=2 if dx == 0 else 1, parent=dl)
        # Trailing fade band
        if sx > 20:
            dpg.draw_rectangle((max(0, sx - 80), 0), (sx, team_h),
                               fill=(*C["gold"][:3], 18),
                               color=(0, 0, 0, 0), parent=dl)
        t  = (math.sin(draft.analyse_t * 2.2) + 1) / 2
        pa = int(140 + t * 110)
        label = "ANALYSING DRAFT"
        lw = len(label) * 11
        _txt(dl, center - lw // 2, team_h - 36, label,
             (*C["gold_lt"][:3], pa), 23, "raj_sb_22")
        # Orbital spinner alongside the label
        draw_orbital_spinner(dl, center + lw // 2 + 22, team_h - 24, 9,
                              C["gold_lt"], pa, n_dots=3, speed=2.2)
        draw_orbital_spinner(dl, center - lw // 2 - 22, team_h - 24, 9,
                              C["gold_lt"], pa, n_dots=3, speed=-2.2)
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
        _txt(dl, nbx+16, nby+6, "NEW DRAFT", (*C["gold_lt"][:3], 220), 21, "raj_sb_22")
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


def _arc_points(cx, cy, r, start_deg, end_deg, n=48):
    """Points along an arc. Angle=0 = top, +90 = right, -90 = left."""
    pts = []
    if n < 2:
        n = 2
    for i in range(n):
        t = i / (n - 1)
        ang = math.radians(start_deg + (end_deg - start_deg) * t)
        pts.append((cx + r * math.sin(ang), cy - r * math.cos(ang)))
    return pts


def _factor_chips():
    """Top 3 score-breakdown deltas between blue and red top comps.
    Returns list of (label, delta_pct_normalised) — positive favours blue."""
    b = draft.comp_detail_blue[0] if draft.comp_detail_blue else None
    r = draft.comp_detail_red[0]  if draft.comp_detail_red  else None
    if not (b and r):
        return []
    sb_b = b.get("score_breakdown", {}) or {}
    sb_r = r.get("score_breakdown", {}) or {}
    AXES = [
        ("COMFORT",   "comfort"),
        ("IDENTITY",  "identity"),
        ("SYNERGY",   "synergy"),
        ("DAMAGE",    "damage"),
        ("COHERENCE", "coherence"),
    ]
    diffs = []
    for label, key in AXES:
        bv = float(sb_b.get(key, 0.0) or 0.0)
        rv = float(sb_r.get(key, 0.0) or 0.0)
        diffs.append((label, bv - rv))
    diffs.sort(key=lambda x: -abs(x[1]))
    # Always return top 3, no threshold (lets the waterfall show even subtle deltas)
    return diffs[:3]


def _draw_win_meter(dl, cx, team_h):
    """Hero win-probability arc gauge. Replaces the old horizontal bar."""
    ma = draft.win_meter_alpha
    if ma <= 0 and draft.phase not in (DraftPhase.RESULTS, DraftPhase.DONE):
        return

    pct = draft.win_pct_display
    cy  = team_h // 2 - 8
    r   = min(110, team_h // 2 - 32)

    # Background plate
    plate_r = r + 28
    dpg.draw_circle((cx, cy), plate_r,
                    fill=(*C["panel"][:3], int(ma * 0.55)),
                    color=(0, 0, 0, 0), parent=dl)
    dpg.draw_circle((cx, cy), plate_r,
                    fill=(0, 0, 0, 0),
                    color=(*C["rule_gold"][:3], int(ma * 0.5)),
                    thickness=1, parent=dl)
    # Outward-pulsing rings — slow ambient motion behind the gauge
    t = time.monotonic()
    for i in range(2):
        phase = (t * 0.45 + i * 0.5) % 1.0
        ring_r = plate_r + int(phase * 32)
        ring_a = int(ma * 0.18 * (1.0 - phase))
        if ring_a > 4:
            dpg.draw_circle((cx, cy), ring_r,
                            fill=(0, 0, 0, 0),
                            color=(*C["gold"][:3], ring_a),
                            thickness=1, parent=dl)
    # Orbiting dots around the plate — subtle motion
    for i in range(3):
        ang = t * 0.5 + i * (2 * math.pi / 3)
        ox = cx + int((plate_r + 6) * math.cos(ang))
        oy = cy + int((plate_r + 6) * math.sin(ang))
        dpg.draw_circle((ox, oy), 2,
                        fill=(*C["gold_lt"][:3], int(ma * 0.55)),
                        color=(0, 0, 0, 0), parent=dl)

    # --- Arc track (full 180°, from -100° to +100° for slight overhang) ---
    track_start, track_end = -100, 100
    track = _arc_points(cx, cy, r, track_start, track_end, n=64)
    dpg.draw_polyline(track,
                      color=(*C["rule_dark"][:3], ma),
                      thickness=10, parent=dl)
    # Thinner inner glow line for depth
    dpg.draw_polyline(_arc_points(cx, cy, r - 5, track_start, track_end, n=64),
                      color=(*C["rule_gold"][:3], int(ma * 0.35)),
                      thickness=1, parent=dl)

    # --- Fill arc from center (50%) toward current pct in win color ---
    col   = _win_color(pct)
    pct_a = (pct - 50) * 1.8   # 0 at 50%, ±90 at extremes
    pct_a = max(-90, min(90, pct_a))
    if pct_a >= 0:
        fill = _arc_points(cx, cy, r, 0, pct_a, n=max(4, int(abs(pct_a) / 2)))
    else:
        fill = _arc_points(cx, cy, r, pct_a, 0, n=max(4, int(abs(pct_a) / 2)))
    if len(fill) >= 2:
        dpg.draw_polyline(fill, color=(*col, ma), thickness=10, parent=dl)

    # --- Tick marks at 0/25/50/75/100 ---
    for tick in (-90, -45, 0, 45, 90):
        p_outer = _arc_points(cx, cy, r + 6, tick, tick, n=2)[0]
        p_inner = _arc_points(cx, cy, r - 6, tick, tick, n=2)[0]
        emph    = (tick == 0)
        tcol    = (*C["gold"][:3], int(ma * 0.9)) if emph else (*C["txt2"][:3], int(ma * 0.7))
        dpg.draw_line(p_inner, p_outer, color=tcol,
                      thickness=2 if emph else 1, parent=dl)

    # --- Needle (layered lines for smooth tapered look) ---
    needle_tip = _arc_points(cx, cy, r - 4, pct_a, pct_a, n=2)[0]
    # Soft halo behind needle
    dpg.draw_line((cx, cy), needle_tip,
                  color=(*C["gold_dk"][:3], int(ma * 0.55)),
                  thickness=6, parent=dl)
    # Main needle
    dpg.draw_line((cx, cy), needle_tip,
                  color=(*C["gold_lt"][:3], ma),
                  thickness=3, parent=dl)
    # Bright tip cap
    dpg.draw_circle(needle_tip, 3,
                    fill=(*C["gold_lt"][:3], ma),
                    color=(*C["gold"][:3], ma),
                    thickness=1, parent=dl)
    # Hub
    dpg.draw_circle((cx, cy), 9,
                    fill=(*C["card"][:3], ma),
                    color=(*C["gold"][:3], ma),
                    thickness=2, parent=dl)
    dpg.draw_circle((cx, cy), 4,
                    fill=(*C["gold_lt"][:3], ma),
                    color=(0, 0, 0, 0), parent=dl)

    # --- Big % readout, below arc center ---
    label = f"{pct:.1f}%"
    lw = len(label) * 18
    _txt(dl, cx - lw // 2, cy + 22, label, (*col, ma), 44, "raj_44")

    # Sub label
    if pct >= 55:
        sub = "BLUE FAVOURED"
        sub_col = C["platinum"]
    elif pct <= 45:
        sub = "RED FAVOURED"
        sub_col = (220, 110, 110, 255)
    else:
        sub = "EVEN MATCHUP"
        sub_col = C["gold_lt"]
    sw = len(sub) * 8
    _txt(dl, cx - sw // 2, cy + 68, sub,
         (*sub_col[:3], int(ma * 0.85)), 18, "raj_sb_18")

    # End labels at the arc tips
    blue_label_pos = _arc_points(cx, cy, r + 22, -90, -90, n=2)[0]
    red_label_pos  = _arc_points(cx, cy, r + 22,  90,  90, n=2)[0]
    _txt(dl, int(blue_label_pos[0]) - 14, int(blue_label_pos[1]) - 8,
         "BLUE", (*C["platinum"][:3], int(ma * 0.85)), 15, "raj_sb_14")
    _txt(dl, int(red_label_pos[0]) - 12, int(red_label_pos[1]) - 8,
         "RED", (220, 110, 110, int(ma * 0.85)), 15, "raj_sb_14")

    # --- Win-prob waterfall (top 3 score-breakdown contributions) ---
    ca = draft.chip_alpha
    if ca > 0:
        chips = _factor_chips()
        if chips:
            chip_y  = cy + 92
            card_w  = 92
            card_h  = 42
            gap     = 6
            total_w = len(chips) * card_w + (len(chips) - 1) * gap
            start_x = cx - total_w // 2
            for (lab, dv) in chips:
                fav_blue = dv >= 0
                accent = C["platinum"][:3] if fav_blue else (220, 110, 110)
                sign = "+" if fav_blue else ""
                # Card body
                dpg.draw_rectangle((start_x, chip_y),
                                    (start_x + card_w, chip_y + card_h),
                                    fill=(*C["card"][:3], int(ca * 0.85)),
                                    color=(*accent, int(ca * 0.55)),
                                    rounding=4, parent=dl)
                # Axis label (top)
                _txt(dl, start_x + 8, chip_y + 2, lab,
                     (*C["txt2"][:3], ca), 12, "raj_sb_12")
                # Value (centered, big-ish)
                val_str = f"{sign}{dv * 100:.1f}"
                _txt(dl, start_x + 6, chip_y + 16, val_str,
                     (*accent, ca), 16, "raj_sb_16")
                # Mini magnitude bar at bottom
                mag = max(0.05, min(1.0, abs(dv) * 5))  # scale up small values
                bar_w = int((card_w - 12) * mag)
                dpg.draw_rectangle((start_x + 6, chip_y + card_h - 6),
                                    (start_x + card_w - 6, chip_y + card_h - 3),
                                    fill=(*C["rule_dark"][:3], ca),
                                    color=(0, 0, 0, 0), parent=dl)
                dpg.draw_rectangle((start_x + 6, chip_y + card_h - 6),
                                    (start_x + 6 + bar_w, chip_y + card_h - 3),
                                    fill=(*accent, ca),
                                    color=(0, 0, 0, 0), parent=dl)
                start_x += card_w + gap


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

def _draw_score_radar(dl, cx, cy, r, sb, accent_col, alpha):
    """Pentagonal radar of score_breakdown values (0..1) with full axis names."""
    if not sb or alpha <= 0:
        return
    AXES = [
        ("IDENTITY",  "identity"),
        ("COMFORT",   "comfort"),
        ("SYNERGY",   "synergy"),
        ("DAMAGE",    "damage"),
        ("COHERENCE", "coherence"),
    ]
    n = len(AXES)
    step = 360 / n
    angles = [math.radians(-90 + i * step) for i in range(n)]
    # Background web — 3 nested polygons
    for lvl in (0.33, 0.66, 1.0):
        pts = [(cx + r * lvl * math.cos(a),
                cy + r * lvl * math.sin(a)) for a in angles]
        pts.append(pts[0])
        dpg.draw_polyline(pts,
                          color=(*C["rule_dark"][:3], int(alpha * 0.55)),
                          thickness=1, parent=dl)
    # Axis spokes
    for a in angles:
        dpg.draw_line((cx, cy),
                      (cx + r * math.cos(a), cy + r * math.sin(a)),
                      color=(*C["rule_dark"][:3], int(alpha * 0.45)),
                      thickness=1, parent=dl)
    # Value polygon — render as fan triangles from center so concave shapes
    # render correctly (DPG draw_polygon fan-triangulates from vertex 0 only).
    val_pts = []
    for (_, key), a in zip(AXES, angles):
        v = float(sb.get(key, 0.0) or 0.0)
        v = max(0.05, min(1.0, v))
        val_pts.append((cx + r * v * math.cos(a),
                        cy + r * v * math.sin(a)))
    fill_col = (*accent_col[:3], int(alpha * 0.38))
    for i in range(n):
        p1 = val_pts[i]
        p2 = val_pts[(i + 1) % n]
        dpg.draw_triangle((cx, cy), p1, p2,
                          fill=fill_col, color=(0, 0, 0, 0), parent=dl)
    # Outline drawn separately for crisp edges
    outline = val_pts + [val_pts[0]]
    dpg.draw_polyline(outline,
                      color=(*accent_col[:3], alpha),
                      thickness=2, parent=dl)
    # Vertex dots
    for vx, vy in val_pts:
        dpg.draw_circle((vx, vy), 2.5,
                        fill=(*accent_col[:3], alpha),
                        color=(0, 0, 0, 0), parent=dl)
    # Axis labels — full names, anchored outward from each vertex
    label_col = (*C["txt2"][:3], int(alpha * 0.95))
    for (lab, _), a in zip(AXES, angles):
        dx = math.cos(a)
        dy = math.sin(a)
        lx_c = cx + (r + 10) * dx
        ly_c = cy + (r + 10) * dy
        text_w = len(lab) * 5  # 9pt SemiBold approx
        # Anchor horizontally based on quadrant
        if dx > 0.3:
            ax = lx_c + 2
        elif dx < -0.3:
            ax = lx_c - text_w - 2
        else:
            ax = lx_c - text_w // 2
        # Anchor vertically
        if dy > 0.3:
            ay = ly_c + 1
        elif dy < -0.3:
            ay = ly_c - 11
        else:
            ay = ly_c - 5
        _txt(dl, int(ax), int(ay), lab, label_col, 9, "raj_sb_11")


_PRIORITY_THEME = {
    "HIGH":   {"col": (200, 86, 70), "pulse": True,  "label": "HIGH"},
    "MEDIUM": {"col": (200, 168, 106), "pulse": False, "label": "MED"},
    "LOW":    {"col": (122, 114, 99), "pulse": False, "label": "LOW"},
}


def _draw_ban_card(dl, bx, by, bw, bh, champ, detail, al):
    """Single ban card. Vertical layout: priority strip > champ > player/WR."""
    if not detail:
        # Empty placeholder
        dpg.draw_rectangle((bx, by), (bx + bw, by + bh),
                            fill=(*C["card"][:3], int(al * 0.45)),
                            color=(*C["loss"][:3], int(al * 0.20)),
                            rounding=4, parent=dl)
        _txt(dl, bx + bw // 2 - 5, by + bh // 2 - 11, "—",
             (*C["txt_dim"][:3], int(al * 0.7)), 22, "raj_20")
        return

    pri = str(detail.get("priority", "")).upper() or "LOW"
    theme = _PRIORITY_THEME.get(pri, _PRIORITY_THEME["LOW"])
    accent = theme["col"]

    # Card background
    dpg.draw_rectangle((bx, by), (bx + bw, by + bh),
                        fill=(*C["card"][:3], al),
                        color=(*accent, int(al * 0.55)),
                        rounding=5, parent=dl)

    # Priority strip across the top (subtle pulse on HIGH)
    if theme["pulse"]:
        pulse = (math.sin(time.monotonic() * 3.0) + 1) / 2
        strip_a = int(al * (0.55 + pulse * 0.30))
    else:
        strip_a = int(al * 0.70)
    dpg.draw_rectangle((bx, by), (bx + bw, by + 14),
                        fill=(*accent, strip_a),
                        color=(0, 0, 0, 0), rounding=4, parent=dl)
    lab = theme["label"]
    _txt(dl, bx + 6, by + 0, lab, (*C["bg"][:3], al), 12, "raj_sb_12")
    # Tiny X on the right of the strip
    xs, xe = bx + bw - 14, bx + bw - 6
    ys, ye = by + 3, by + 11
    dpg.draw_line((xs, ys), (xe, ye), color=(*C["bg"][:3], al), thickness=1.5, parent=dl)
    dpg.draw_line((xe, ys), (xs, ye), color=(*C["bg"][:3], al), thickness=1.5, parent=dl)

    # Champion name (centered, big)
    name_str = (champ or "—").upper()
    # crude width estimate; fits ~9 chars at size 19
    max_chars = max(1, (bw - 8) // 9)
    name_disp = name_str[:max_chars]
    nw = len(name_disp) * 9
    _txt(dl, bx + (bw - nw) // 2, by + 22, name_disp,
         (*C["gold_lt"][:3], al), 19, "raj_20")

    # Divider
    dpg.draw_line((bx + 8, by + 50), (bx + bw - 8, by + 50),
                  color=(*C["rule_dark"][:3], int(al * 0.7)),
                  thickness=1, parent=dl)

    # Player + WR sub-block (only if room and data)
    player = str(detail.get("player", "")).strip()
    wr_val = detail.get("wr", "")
    g_val  = detail.get("games", 0)
    if player:
        ptxt = player[:max(1, (bw - 12) // 8)]
        _txt(dl, bx + 6, by + 56, ptxt,
             (*C["txt"][:3], al), 15, "raj_sb_16")
        wr_str = str(wr_val).replace("%", "") if wr_val else ""
        g_str  = str(g_val) if g_val else ""
        if wr_str and g_str:
            try:
                if int(float(g_str)) > 0:
                    sub = f"{wr_str}%  ·  {g_str}g"
                    _txt(dl, bx + 6, by + 75, sub,
                         (*C["txt2"][:3], al), 13, "raj_r_12")
            except ValueError:
                pass


_VIAB_COLORS = {
    "STRONG":          (79, 168, 130),
    "VIABLE":          (216, 207, 186),
    "WEAK":            (200, 168, 106),
    "NOT RECOMMENDED": (184, 69, 53),
}

# Subclasses promoted as comp-identity chips (in display priority order)
_IDENTITY_TAGS = [
    ("engage",            "ENGAGE"),
    ("frontline",         "FRONTLINE"),
    ("aoe_damage",        "AOE"),
    ("assassin_or_burst", "BURST"),
    ("cc",                "CC"),
    ("hypercarry",        "HYPERCARRY"),
    ("long_range",        "POKE"),
    ("scaling",           "SCALING"),
    ("peel",              "PEEL"),
    ("waveclear",         "WAVECLEAR"),
    ("duelist",           "DUELIST"),
    ("anti_carry",        "ANTI-CARRY"),
]


def _identity_tags_for(picks):
    """Return up to 3 short identity tags for a comp's pick list."""
    if not picks:
        return []
    try:
        from data.draft_engine import SUBCLASSES
    except Exception:
        return []
    champs = [p.get("champion") for p in picks if p.get("champion")]
    if not champs:
        return []
    out = []
    for key, label in _IDENTITY_TAGS:
        members = SUBCLASSES.get(key, set())
        count = sum(1 for c in champs if c in members)
        if count >= 2:
            out.append((label, count))
        if len(out) >= 3:
            break
    return out


def _spike_window(spike_str, archetype=""):
    """Map (archetype, spike string) to a 0..1 position on the Early→Late axis.

    More granular than just keyword matching — different mid-game comps
    have meaningfully different spike windows."""
    s    = (spike_str or "").lower()
    arch = (archetype or "").lower()

    # Archetype-first mapping (most reliable)
    arch_pos = {
        "dive":             0.28,
        "pick":             0.50,
        "teamfight":        0.55,
        "poke-siege":       0.45,
        "poke":             0.45,
        "split push":       0.62,
        "split-push":       0.62,
        "protect the carry":0.82,
        "scaling":          0.92,
    }
    for k, v in arch_pos.items():
        if k in arch:
            return v
    # Fall back to keywords in the spike text
    if "35" in s or "scaling" in s:                return 0.92
    if "late" in s and ("4 items" in s or "carry" in s): return 0.82
    if "late" in s and "mid" in s:                 return 0.72
    if "late" in s:                                return 0.85
    if "early-to-mid" in s or "early to mid" in s: return 0.30
    if "level 6" in s:                             return 0.32
    if "level 11" in s:                            return 0.60
    if "3 items" in s:                             return 0.55
    if "tp" in s or "teleport" in s:               return 0.62
    if "manamune" in s or "liandry" in s or "poke" in s: return 0.45
    if "mid" in s:                                 return 0.55
    if "early" in s:                               return 0.20
    return 0.5


def _draw_spike_strip(dl, x, y, w, h, spike_str, accent, alpha, archetype=""):
    """Slim Early/Mid/Late timeline with a marker at the comp's peak."""
    pos = _spike_window(spike_str, archetype)
    # Track
    dpg.draw_rectangle((x, y + h // 2 - 2), (x + w, y + h // 2 + 2),
                        fill=(*C["rule_dark"][:3], alpha),
                        color=(0, 0, 0, 0), rounding=1, parent=dl)
    # Phase tick marks (Early / Mid / Late) at 0, 0.5, 1.0
    for tx in (0.0, 0.5, 1.0):
        px = x + int(w * tx)
        dpg.draw_line((px, y + h // 2 - 4), (px, y + h // 2 + 4),
                      color=(*C["txt2"][:3], int(alpha * 0.7)),
                      thickness=1, parent=dl)
    # Phase labels
    _txt(dl, x - 2,            y + h, "EARLY",
         (*C["txt2"][:3], int(alpha * 0.8)), 10, "raj_sb_11")
    _txt(dl, x + w // 2 - 9,   y + h, "MID",
         (*C["txt2"][:3], int(alpha * 0.8)), 10, "raj_sb_11")
    _txt(dl, x + w - 22,       y + h, "LATE",
         (*C["txt2"][:3], int(alpha * 0.8)), 10, "raj_sb_11")
    # Marker — small diamond at the spike position
    mx = x + int(w * pos)
    my = y + h // 2
    dpg.draw_polygon([(mx, my - 5), (mx + 5, my),
                      (mx, my + 5), (mx - 5, my)],
                     fill=(*accent, alpha),
                     color=(*C["gold_lt"][:3], alpha),
                     thickness=1, parent=dl)


def _draw_picks_with_fit(dl, x, y, max_w, picks, alpha):
    """Render champion names in fit-priority (lock-in) order; rank numeral + fit bar each."""
    if not picks:
        return
    n = min(5, len(picks))
    sorted_picks = sorted(
        picks[:n],
        key=lambda p: -float(p.get("fit_score", 0.0) or 0.0),
    )
    items = [(p.get("champion", "") or "?", float(p.get("fit_score", 0.5) or 0.5))
             for p in sorted_picks]
    gap = 12
    # Truncate champion names dynamically if total width exceeds available
    base_widths = [max(40, len(c) * 8) for c, _ in items]
    total = sum(base_widths) + gap * (n - 1)
    if total > max_w:
        # Scale down proportionally — shrink to fit
        scale = max_w / total
        base_widths = [max(36, int(w * scale)) for w in base_widths]
    cx_pos = x
    for rank, ((champ, fit), w) in enumerate(zip(items, base_widths), start=1):
        # Small rank badge (the lock-in order index)
        _txt(dl, cx_pos, y + 3, str(rank),
             (*C["gold_dk"][:3], alpha), 12, "raj_sb_12")
        # Truncate name to fit remaining width (after rank badge ~8 px)
        name_x = cx_pos + 10
        name_w = max(20, w - 10)
        max_chars = max(3, name_w // 7)
        nm = champ.upper()
        if len(nm) > max_chars:
            nm = nm[:max_chars - 1] + "…"
        _txt(dl, name_x, y, nm, (*C["txt"][:3], alpha), 16, "raj_sb_16")
        # Fit bar (4 px tall)
        bar_y = y + 22
        dpg.draw_rectangle((cx_pos, bar_y), (cx_pos + w - 2, bar_y + 4),
                            fill=(*C["rule_dark"][:3], int(alpha * 0.8)),
                            color=(0, 0, 0, 0), rounding=2, parent=dl)
        fclamp = max(0.0, min(1.0, fit))
        # Color by fit quality
        if   fclamp >= 0.7: fc = (79, 168, 130)
        elif fclamp >= 0.4: fc = C["gold"][:3]
        else:                fc = (190, 130, 80)
        dpg.draw_rectangle((cx_pos, bar_y),
                            (cx_pos + int((w - 2) * fclamp), bar_y + 4),
                            fill=(*fc, alpha),
                            color=(0, 0, 0, 0), rounding=2, parent=dl)
        cx_pos += w + gap


def _compact_lane_note(note):
    """Drop trivial parts. 'X on main' and 'Even/Close matchup' are implied
    by the phase chip; only surface things worth reading."""
    if not note:
        return ""
    parts = [p.strip() for p in note.split("·") if p.strip()]
    out = []
    for p in parts:
        pl = p.lower().strip()
        if pl.startswith("even matchup"):  continue
        if pl.startswith("close skill match"): continue
        if pl.endswith("on main"):          continue
        out.append(p)
    return "  ·  ".join(out)


def _draw_comp_card(dl, px, cy, pw, ch, idx, comp_name, detail, header_col, al):
    """Comp card: header / identity / picks-with-fit-bars / win-cond / spike timeline / radar."""
    dpg.draw_rectangle((px, cy), (px + pw, cy + ch),
                        fill=(*C["card"][:3], al),
                        color=(*C["rule_dark"][:3], al),
                        rounding=5, parent=dl)
    # Team accent stripe
    dpg.draw_rectangle((px, cy), (px + 4, cy + ch),
                        fill=(*header_col[:3], al),
                        color=(0, 0, 0, 0), rounding=2, parent=dl)
    # Index numeral
    _txt(dl, px + 10, cy + ch // 2 - 13, str(idx),
         (*C["txt2"][:3], int(al * 0.9)), 24, "raj_sb_22")

    # Radar at far right
    radar_size = min(ch - 14, 108)
    rcx = px + pw - radar_size // 2 - 10
    rcy = cy + ch // 2 + 2
    rr  = radar_size // 2 - 10

    text_x = px + 30
    text_w = (rcx - rr - 14) - text_x   # text column width

    if not detail:
        _txt(dl, text_x, cy + ch // 2 - 11, comp_name,
             (*C["gold_lt"][:3], al), 22, "raj_20")
        return

    arch  = detail.get("archetype", comp_name)
    viab  = detail.get("viability", "VIABLE")
    syn   = int(detail.get("synergy", 0))
    picks = detail.get("picks", []) or []
    wcond = detail.get("win_condition", "")
    spike = detail.get("spike", "")
    sb    = detail.get("score_breakdown", {}) or {}
    vc    = _VIAB_COLORS.get(viab, C["txt"][:3])

    # ── HEADER ROW ───────────────────────────────────────────────
    _txt(dl, text_x, cy + 4, arch,
         (*C["gold_lt"][:3], al), 22, "raj_20")

    # Right of name: viability pill
    arch_w = len(arch) * 11
    pill_x = text_x + arch_w + 14
    viab_short = "NOT REC." if viab == "NOT RECOMMENDED" else viab
    pill_w = len(viab_short) * 7 + 12
    dpg.draw_rectangle((pill_x, cy + 10), (pill_x + pill_w, cy + 26),
                        fill=(*vc, int(al * 0.20)),
                        color=(*vc, int(al * 0.6)),
                        rounding=8, parent=dl)
    _txt(dl, pill_x + 6, cy + 9, viab_short,
         (*vc, al), 12, "raj_sb_12")

    # Synergy dots
    dot_x = pill_x + pill_w + 8
    for d in range(5):
        fc = (*C["gold"][:3], al) if d < syn else (*C["rule_dark"][:3], al)
        dpg.draw_circle((dot_x + d * 11, cy + 18), 4,
                        fill=fc, color=(0, 0, 0, 0), parent=dl)

    # ── IDENTITY CHIPS (row 2) ──────────────────────────────────
    tags = _identity_tags_for(picks)
    if tags and ch >= 100:
        chip_y = cy + 32
        cx_pos = text_x
        for label, _ in tags[:3]:
            cw = len(label) * 7 + 12
            if cx_pos + cw > text_x + text_w:
                break
            dpg.draw_rectangle((cx_pos, chip_y), (cx_pos + cw, chip_y + 18),
                                fill=(*header_col[:3], int(al * 0.16)),
                                color=(*header_col[:3], int(al * 0.55)),
                                rounding=9, parent=dl)
            _txt(dl, cx_pos + 6, chip_y + 1, label,
                 (*C["txt"][:3], al), 12, "raj_sb_12")
            cx_pos += cw + 5

    # ── PICKS w/ FIT BARS (row 3) ───────────────────────────────
    if picks and ch >= 90:
        _draw_picks_with_fit(dl, text_x, cy + 56, text_w, picks, al)

    # ── WIN CONDITION (row 4) ───────────────────────────────────
    if wcond and ch >= 115:
        max_chars = max(8, text_w // 8)
        wc_disp = wcond if len(wcond) <= max_chars else wcond[:max_chars - 1] + "…"
        _txt(dl, text_x, cy + 88, "> " + wc_disp,
             (*C["txt"][:3], al), 14, "raj_sb_14")

    # ── SPIKE TIMELINE (row 5) ──────────────────────────────────
    if (spike or arch) and ch >= 130:
        strip_w = max(110, text_w - 92)
        strip_y = cy + ch - 22
        _draw_spike_strip(dl, text_x, strip_y, strip_w, 6,
                          spike, header_col, al, archetype=arch)
        # AP/AD right-aligned next to the timeline
        if sb:
            ap_pct = int(round(float(sb.get("ap_ratio", 0.5) or 0.5) * 100))
            ad_pct = 100 - ap_pct
            ap_txt = f"AP {ap_pct} · AD {ad_pct}"
            _txt(dl, text_x + strip_w + 14, strip_y - 2, ap_txt,
                 (*C["txt2"][:3], al), 13, "raj_sb_14")

    # Radar
    _draw_score_radar(dl, rcx, rcy, rr, sb, header_col, al)


def _draw_threat_focus(dl, x, y, max_w, own_bans, opposing_comp_detail, al):
    """One-line 'WATCH: <champ> (X% WR · Yg)' for the highest-fit enemy pick
    that this team isn't already banning. Drawn right-aligned at (x,y)."""
    if not opposing_comp_detail:
        return
    own_set = set((b or "").strip().upper() for b in (own_bans or []) if b)
    # Gather candidate threats from the opposing team's top comp's picks
    top = opposing_comp_detail[0] if opposing_comp_detail else None
    if not top:
        return
    candidates = []
    for p in top.get("picks", []):
        name = (p.get("champion") or "").strip()
        if not name:
            continue
        if name.upper() in own_set:
            continue
        fit = float(p.get("fit_score", 0.0) or 0.0)
        candidates.append((name, fit, p))
    if not candidates:
        return
    candidates.sort(key=lambda t: -t[1])
    threat_name, threat_fit, _ = candidates[0]

    # Pulsing warning chip
    pulse = (math.sin(time.monotonic() * 2.2) + 1) / 2
    accent = (200, 86, 70)
    label = f"!  WATCH: {threat_name.upper()}"
    chip_w = len(label) * 7 + 16
    cx = x + max_w - chip_w
    dpg.draw_rectangle((cx, y), (cx + chip_w, y + 20),
                        fill=(*accent, int(al * (0.20 + pulse * 0.18))),
                        color=(*accent, int(al * 0.7)),
                        rounding=10, parent=dl)
    _txt(dl, cx + 8, y + 1, label,
         (*C["gold_lt"][:3], al), 13, "raj_sb_14")


def _draw_strategy_panel(dl, px, py, pw, ph, al, header, header_col,
                         bans, comps, ban_detail=None, comp_detail=None,
                         opposing_comp_detail=None):
    _panel_bg(dl, px, py, px+pw, py+ph, header_col, al)
    _txt(dl, px+18, py+14, header, (*header_col[:3], al), 22, "cinzel_22")
    dpg.draw_line((px+18, py+48),(px+pw-18, py+48),
                  color=(*C["rule_dark"][:3], al), thickness=1, parent=dl)

    _txt(dl, px+18, py+58, "PRIORITY BANS",
         (*C["gold_lt"][:3], al), 20, "raj_sb_18")
    # Threat focus chip — right side of the section header
    _draw_threat_focus(dl, px + 18, py + 60, pw - 36,
                       bans, opposing_comp_detail, al)

    # ─── BANS ─────────────────────────────────────────────────────────
    ban_h  = 86
    ban_y  = py + 86
    n_bans = 5
    gap    = 6
    slot_w = (pw - 36 - (n_bans - 1) * gap) // n_bans

    for i in range(n_bans):
        bx = px + 18 + i * (slot_w + gap)
        champ  = bans[i]       if i < len(bans)        else None
        detail = (ban_detail[i] if ban_detail and i < len(ban_detail) else None)
        _draw_ban_card(dl, bx, ban_y, slot_w, ban_h, champ, detail, al)

    # ─── COMPS ────────────────────────────────────────────────────────
    div_y = ban_y + ban_h + 14
    dpg.draw_line((px+18, div_y),(px+pw-18, div_y),
                  color=(*C["rule_dark"][:3], al), thickness=1, parent=dl)
    _txt(dl, px+18, div_y+10, "TEAM COMPOSITIONS",
         (*C["gold_lt"][:3], al), 20, "raj_sb_18")

    comp_y    = div_y + 36
    remaining = max(1, ph - (comp_y - py) - 10)
    # Fit as many comps as can fit at the rich-card minimum height (130).
    min_h     = 130
    gap       = 8
    n_fits    = max(1, (remaining + gap) // (min_h + gap))
    n_comps   = min(n_fits, len(comps) if comps else 1, 3)
    comp_h    = max(min_h, (remaining - (n_comps - 1) * gap) // n_comps)

    for i, comp_name in enumerate(comps[:n_comps]):
        cy2 = comp_y + i * (comp_h + 8)
        if cy2 + comp_h > py + ph:
            break
        detail = comp_detail[i] if comp_detail and i < len(comp_detail) else None
        _draw_comp_card(dl, px + 18, cy2, pw - 36, comp_h,
                        i + 1, comp_name, detail, header_col, al)


def _draw_blue_panel(dl, px, py, pw, ph, al):
    _draw_strategy_panel(dl, px, py, pw, ph, al,
                         "BLUE TEAM STRATEGY", C["platinum"],
                         draft.blue_bans, draft.blue_comps,
                         ban_detail=draft.ban_detail_blue or None,
                         comp_detail=draft.comp_detail_blue or None,
                         opposing_comp_detail=draft.comp_detail_red or None)
    # Team-color gradient halo (bright blue → deep navy)
    _gradient_frame(dl, px, py, px + pw, py + ph,
                    c_top=(90, 160, 240), c_bot=(20, 36, 84), alpha=al)


def _draw_lane_card(dl, px, py, pw, ph, role, blue_name, red_name,
                     blue_win, note, reveal, al):
    """One lane-matchup card. reveal in 0..1 controls slide-in + alpha multiplier."""
    if reveal <= 0:
        return
    # Slide-in offset (from left, fades in)
    slide = int((1 - reveal) * 28)
    card_a = int(al * reveal)
    ox = px + slide

    # Card background
    dpg.draw_rectangle((ox, py), (ox + pw - slide, py + ph),
                        fill=(*C["card"][:3], card_a),
                        color=(*C["rule_dark"][:3], int(card_a * 0.85)),
                        rounding=5, parent=dl)

    # Role accent strip
    rc = _ROLE_COLORS.get(role, (120, 120, 120))
    dpg.draw_rectangle((ox, py), (ox + 4, py + ph),
                        fill=(*rc, card_a), color=(0, 0, 0, 0),
                        rounding=2, parent=dl)
    # Role chip top-left
    _txt(dl, ox + 12, py + 6, role,
         (*rc, card_a), 16, "raj_sb_16")

    # Phase chip top-right based on blue_win
    if blue_win >= 60:
        phase, pcol = "BLUE EARLY", C["platinum"]
    elif blue_win >= 52:
        phase, pcol = "BLUE EDGE", C["platinum"]
    elif blue_win > 48:
        phase, pcol = "EVEN", C["gold_lt"]
    elif blue_win > 40:
        phase, pcol = "RED EDGE", (220, 110, 110, 255)
    else:
        phase, pcol = "RED EARLY", (220, 110, 110, 255)
    pw_chip = len(phase) * 7 + 12
    chip_x  = ox + pw - slide - pw_chip - 8
    dpg.draw_rectangle((chip_x, py + 6), (chip_x + pw_chip, py + 22),
                        fill=(*pcol[:3], int(card_a * 0.18)),
                        color=(*pcol[:3], int(card_a * 0.55)),
                        rounding=7, parent=dl)
    _txt(dl, chip_x + 6, py + 5, phase,
         (*pcol[:3], card_a), 12, "raj_sb_12")

    # Team colors
    BLUE_TEAM = (58, 96, 168)
    RED_TEAM  = (220, 90, 90)

    # Blue name left (mid-row)
    mid_y = py + ph // 2
    name_y = mid_y - 10
    _txt(dl, ox + 14, name_y, blue_name.upper(),
         (*BLUE_TEAM, card_a), 19, "raj_20")
    # Red name right
    red_disp = red_name.upper()
    red_w = len(red_disp) * 11
    _txt(dl, ox + pw - slide - red_w - 12, name_y, red_disp,
         (*RED_TEAM, card_a), 19, "raj_20")

    # Split win-share bar — blue portion = blue_win%, red portion = (100 - blue_win)%
    # Dominant side fills more of the bar in its team color.
    bw_w   = min(360, max(220, (pw - slide) - 40))
    bx     = ox + (pw - slide - bw_w) // 2
    bh_bar = 14
    by     = mid_y + 14

    blue_frac = max(0.0, min(1.0, blue_win / 100.0))
    # Animate with reveal: ease from 50/50 toward true split
    blue_frac_anim = 0.5 + (blue_frac - 0.5) * reveal
    split_x = bx + int(bw_w * blue_frac_anim)

    # Blue portion
    if split_x > bx:
        dpg.draw_rectangle((bx, by), (split_x, by + bh_bar),
                            fill=(*BLUE_TEAM, card_a),
                            color=(0, 0, 0, 0), rounding=4, parent=dl)
    # Red portion
    if split_x < bx + bw_w:
        dpg.draw_rectangle((split_x, by), (bx + bw_w, by + bh_bar),
                            fill=(*RED_TEAM, card_a),
                            color=(0, 0, 0, 0), rounding=4, parent=dl)
    # Outline
    dpg.draw_rectangle((bx, by), (bx + bw_w, by + bh_bar),
                        fill=(0, 0, 0, 0),
                        color=(*C["rule_dark"][:3], int(card_a * 0.7)),
                        rounding=4, parent=dl)

    # Big % readout — show the DOMINANT side's win %, colored in winner's team color
    if blue_win >= 50:
        dom_pct = blue_win
        bar_col = BLUE_TEAM
    else:
        dom_pct = 100 - blue_win
        bar_col = RED_TEAM
    pct_str = f"{dom_pct:.0f}%"
    pw_pct  = len(pct_str) * 11
    _txt(dl, ox + (pw - slide - pw_pct) // 2, name_y - 4, pct_str,
         (*bar_col, card_a), 22, "raj_20")

    # Note line — drop trivial "on main" / "even matchup" parts (phase chip covers it)
    compact = _compact_lane_note(note)
    if compact and ph >= 56:
        max_chars = max(8, (pw - slide - 28) // 7)
        if len(compact) > max_chars:
            compact = compact[:max_chars - 1] + "…"
        _txt(dl, ox + 14, py + ph - 22, compact,
             (*C["txt"][:3], card_a), 14, "raj_sb_14")


def _draw_pvp_panel(dl, px, py, pw, ph, al):
    _panel_bg(dl, px, py, px+pw, py+ph, C["gold"], al)

    _txt(dl, px+18, py+14, "LANE ADVANTAGE",
         (*C["gold"][:3], al), 22, "cinzel_22")
    dpg.draw_line((px+18, py+48),(px+pw-18, py+48),
                  color=(*C["rule_dark"][:3], al), thickness=1, parent=dl)

    src_label = "Rank History + inhouse WR" if draft.prediction_src == "sheets" \
                else "Score ratio (local)"
    _txt(dl, px+18, py+54, f"Lane matchup  ·  Win % via {src_label}",
         (*C["txt"][:3], al), 18, "raj_sb_18")

    rows    = draft.pvp_rows
    start_y = py + 84
    avail_h = ph - (start_y - py) - 12

    if not rows:
        _txt(dl, px+18, start_y+16, "Configure teams to see matchups",
             (*C["txt_dim"][:3], al), 17, "raj_sb_16")
        return

    gap   = 8
    n     = len(rows)
    row_h = max(78, (avail_h - (n - 1) * gap) // n)

    for i, (role, blue_name, red_name, blue_win, note) in enumerate(rows[:5]):
        ry = start_y + i * (row_h + gap)
        if ry + row_h > py + ph:
            break
        reveal = draft.lane_reveals[i] if i < len(draft.lane_reveals) else 1.0
        _draw_lane_card(dl, px + 12, ry, pw - 24, row_h,
                        role, blue_name, red_name, blue_win, note,
                        reveal, al)


def _draw_red_panel(dl, px, py, pw, ph, al):
    _draw_strategy_panel(dl, px, py, pw, ph, al,
                         "RED TEAM STRATEGY", (220, 90, 90, 255),
                         draft.red_bans, draft.red_comps,
                         ban_detail=draft.ban_detail_red or None,
                         comp_detail=draft.comp_detail_red or None,
                         opposing_comp_detail=draft.comp_detail_blue or None)
    # Team-color gradient halo (bright red → deep maroon)
    _gradient_frame(dl, px, py, px + pw, py + ph,
                    c_top=(240, 120, 120), c_bot=(96, 24, 24), alpha=al)
