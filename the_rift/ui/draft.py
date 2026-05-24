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
from data.reader import live, prefetch_scout_sheets
from data.config import load_config
from data import draft_engine as _eng
from data.draft_board import (DraftBoardState, recommend_action,
                              DRAFT_SEQUENCE, target_archetype,
                              ROLES as _BOARD_ROLES,
                              _candidates_for_player)
from data import champion_icons
from data import splash_art
from ui import draft_sync_ui as _sync_ui
from ui.tierlist import _wheel_delta as _wheel_delta_shared
from ui import board_rail
from ui import lol_theme  # Phase 3: LCS/LEC broadcast primitives
from ui import audio as _audio  # Phase 5: pygame.mixer cue wrapper

_ROLES = ["TOP", "JGL", "MID", "BOT", "SUP"]

_ROLE_COLORS = {
    "TOP": (180, 100,  60),
    "JGL": ( 80, 160,  80),
    "MID": (100, 120, 200),
    "BOT": (180, 160,  60),
    "SUP": (100, 180, 180),
}

# v3 LCS/LEC broadcast side accents. Light blue = blue side, salmon-red =
# red side. Globally referenced from board/draw_team/draw_center renderers
# so a future side recolour is still a one-liner.
BLUE_ACCENT    = lol_theme.LOL["blue_side_dk"][:3]
BLUE_ACCENT_LT = lol_theme.LOL["blue_side"][:3]
RED_ACCENT     = lol_theme.LOL["red_side_dk"][:3]
RED_ACCENT_LT  = lol_theme.LOL["red_side"][:3]


def _side_accent(side, lt=False):
    """Board side -> LCS-broadcast accent RGB. lt=True for the brighter tone."""
    if side == "BLUE":
        return BLUE_ACCENT_LT if lt else BLUE_ACCENT
    return RED_ACCENT_LT if lt else RED_ACCENT

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


def _scout_champs_for_players(players):
    """Build {name: scout_champ_pool} for the engine from cached scout sheets."""
    names = [p.get("name") for p in players if p and p.get("name")]
    return live.scout_champs_map(names) if names else {}


def _compute_bans(opposing_players, own_picks=None):
    """
    Bans vs opposing team. Delegates to draft_engine for Bayesian-shrunk threat,
    form modifier, role-context boost, and counter-coverage discount when our
    team already counters a champion. Also pulls each opposing player's
    scout-sheet FULL CHAMPION POOL (ranked + draft) so threats that aren't in
    customs still register.
    """
    return _eng.recommend_bans(
        opposing_players,
        inhouse_champs=live.inhouse_champs,
        own_picks=own_picks or [],
        primary_roles=live.primary_roles,
        n_bans=5,
        scout_champs=_scout_champs_for_players(opposing_players),
    )


def _compute_comps_detail(players, enemy_picks=None):
    """
    Per-player champion picks per archetype using beam search global optimisation.
    Adds team identity vector, synergy/anti-synergy pairs, AP/AD damage profile,
    counter-pick scoring vs locked enemy champions. Scout-sheet champ pool
    augments customs for ranked/draft signal.
    """
    return _eng.recommend_comps(
        players,
        inhouse_champs=live.inhouse_champs,
        primary_roles=live.primary_roles,
        enemy_picks=enemy_picks or (),
        n_results=5,
        scout_champs=_scout_champs_for_players(players),
    )

# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------
class DraftPhase:
    # v3 flow (LCS broadcast aesthetic, post Phase-6 cleanup):
    #   IDLE → CONNECTING → LOBBY/TEAM_BUILD → SCOUTING → BRIEFING
    #        → ARCHETYPE → BOARD → DONE
    IDLE        = "idle"          # single BEGIN DRAFT button (Phase 1)
    CONNECTING  = "connecting"    # awaiting Fly.io WS handshake (Phase 1)
    TEAM_BUILD  = "team_build"    # lobby: side picker + roster drag-drop
    LOBBY       = "team_build"    # alias — same screen, plan-canonical name
    SCOUTING    = "scouting"      # SCOUTING: waiting on scout-data fetch
    BRIEFING    = "briefing"      # BRIEFING: projected-comps snapshot
    ARCHETYPE   = "archetype"     # ARCHETYPE: per-side hidden picker
    BOARD       = "board"         # interactive tournament-draft board
    DONE        = "done"          # served by _draw_board's done-summary branch


class DraftState:
    def __init__(self):
        self.phase            = DraftPhase.IDLE
        self.blue             = []
        self.red              = []
        # Interactive draft board (tournament-draft mode)
        self.board            = None    # DraftBoardState | None
        self.board_rec        = None    # cached recommend_action() result
        self.board_pool_search  = ""    # type-to-filter the manual pool grid
        self.board_pool_scroll  = 0     # row offset for the scrollable pool grid
        self._board_key_was_down = {}   # edge-detection for keyboard search input
        self.board_target_arch  = None  # user-locked archetype (None = engine auto)
        self._board_top_call_sig  = None # (champ, tag) — detect rec change
        self._board_top_call_anim = 1.0  # 0 = just appeared, 1 = settled
        self._board_actor_sig     = None # (side, kind, action_idx) — actor change
        self._board_actor_anim    = 1.0  # 0 = just changed, 1 = settled
        self._board_lock_pop_idx  = -1   # timeline cell idx that just locked
        self._board_lock_pop_anim = 1.0  # 0 = just popped, 1 = settled
        self._board_last_pointer  = 0    # detect a new lock
        # v3.0.5: re-run recommend_action when async scout/inhouse data lands.
        # Tracks (#scout sheets loaded, len(inhouse_champs)) so the first-ban
        # call can refresh once the prefetch finishes — without this the
        # recompute happened ONCE on board entry, before scout data was
        # ready, and the TOP CALL panel stayed empty until the first lock.
        self._board_data_sig      = None
        # Phase 4 — SCOUTING / BRIEFING / ARCHETYPE state
        self.scout_progress     = {}    # name -> 1 (done) / 0 (in-flight)
        self.scout_total        = 0     # total players to fetch (for progress bar)
        self.scout_kicked       = False # already started the prefetch
        self.scout_ready_sent   = False # already sent set_scout_ready(True)
        self.scout_started_at   = 0.0   # monotonic ts when SCOUTING phase entered (for timeout)
        self.briefing_started_at = 0.0  # monotonic ts when BRIEFING phase entered
        self.briefing_done_sent  = False # already sent set_briefing_done(True)
        self.briefing_data       = None # cached {our_comp, enemy_comp, key_bans}
        self.archetype_hover     = None # archetype card the mouse is over
        self.archetype_pending   = None # archetype locally chosen, awaiting CONFIRM
        # v4.0.2: cache the (cards, subs) tuple between frames so the
        # ARCHETYPE screen doesn't re-call _eng.recommend_comps every frame —
        # that single change drops the screen from network-bound stutter to
        # smooth 60fps. Invalidated by archetype_cache_sig.
        self.archetype_cards     = None
        self.archetype_subs      = None
        self.archetype_cache_sig = None
        # Phase 4 — pivot alert state (board phase)
        self._pivot_last_sig     = None # signature of last pivot-check input
        self._pivot_alert        = None # cached pivot_check result for banner
        self._pivot_btn_rects    = []   # last-frame click hit rects for pivot buttons
        # Phase 5 — audio cue trackers
        self._audio_last_actor_idx = -1 # action.idx of last "our turn" chime
        # Phase 5 — solo fallback (synced lobby, no opponent within 30s)
        self.lobby_entered_at      = 0.0 # monotonic ts on first LOBBY frame
        self.solo_mode             = False # True after user takes solo path

    def reset(self):
        self.__init__()

    def tick(self):
        # No-op tick — the v3 flow drives all animations through `anim`
        # tweens and per-phase render functions; nothing needs a global
        # clock anymore. Kept as a stable API for the parent draw loop.
        pass


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


def _panel_bg(dl, x1, y1, x2, y2, accent_color=None, alpha=255,
              cut=False, cut_sz=14):
    """Panel background. Both modes now render LCS broadcast navy panel +
    gold rule border. `cut` is retained as a parameter for caller-compat
    but no longer changes the visual (the corner-cut command-deck style is
    gone in Phase 3 — kept the rounded LoL panel everywhere)."""
    dpg.draw_rectangle((x1, y1), (x2, y2),
                       fill=lol_theme._alpha(lol_theme.LOL["navy_panel"], alpha),
                       color=lol_theme._alpha(lol_theme.LOL["gold_rule"], alpha),
                       rounding=6, thickness=1, parent=dl)
    if accent_color:
        dpg.draw_rectangle((x1 + 2, y1 + 2), (x2 - 2, y1 + 6),
                           fill=(*accent_color[:3], alpha),
                           color=(0, 0, 0, 0), rounding=2, parent=dl)


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
        self.board_side = "BLUE"       # board mode: which side is "us"

_tb = _TBState()


def _tb_open(vw, vh, target="batch"):
    pool = _get_player_pool()
    _tb.blue      = [None] * 5
    _tb.red       = [None] * 5
    _tb.pool      = list(pool)
    _tb.drag      = None
    _tb.drag_from = None
    _tb.target    = target
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
    # In synced mode, the server is the source of truth for which side we
    # occupy. Mirror it into _tb.board_side so the local toggle visual matches.
    if _sync_ui.is_active():
        srv_side = _sync_ui.my_side()
        if srv_side in ("BLUE", "RED"):
            _tb.board_side = srv_side
    dpg.draw_rectangle((0, 0), (vw, vh),
                       fill=lol_theme.LOL["navy_deep"],
                       color=(0,0,0,0), parent=dl)

    hdr_h   = 60
    pool_h  = 170
    teams_h = vh - hdr_h - pool_h - 12

    # ── Header ───────────────────────────────────────────────────
    dpg.draw_rectangle((0, 0), (vw, hdr_h),
                        fill=lol_theme.LOL["navy_mid"],
                        color=(0,0,0,0), parent=dl)
    lol_theme.draw_gold_rule(dl, 0, hdr_h - 1, vw, hdr_h - 1,
                             thickness=1, alpha=220)
    _txt(dl, vw//2 - 180, 11, "CONFIGURE TEAMS",
         (*lol_theme.LOL["gold_lt"][:3], 230), 29, "cinzel_28")

    # Board mode: "you are" side toggle (left of the action button)
    if _tb.target == "board":
        tg_w, tg_h = 150, 34
        tg_x = vw - 220 - 110 - tg_w - 14
        tg_y = (hdr_h - tg_h) // 2
        is_blue = _tb.board_side == "BLUE"
        lol_theme.draw_navy_panel(
            dl, tg_x, tg_y, tg_x+tg_w, tg_y+tg_h,
            fill=lol_theme._alpha(lol_theme.LOL["navy_panel"], 170),
            border_color=lol_theme.LOL["gold_rule"],
            border_thickness=1, rounding=4)
        half = tg_w // 2
        side_col = (lol_theme.LOL["blue_side"] if is_blue
                    else lol_theme.LOL["red_side"])
        dpg.draw_rectangle(
            (tg_x + (0 if is_blue else half), tg_y),
            (tg_x + (half if is_blue else tg_w), tg_y+tg_h),
            fill=(*side_col[:3], 150),
            color=(0, 0, 0, 0), rounding=4, parent=dl)
        _txt(dl, tg_x + 14, tg_y + 8, "BLUE",
             (*lol_theme.LOL["gold_lt"][:3], 235 if is_blue else 150), 17, "raj_sb_18")
        _txt(dl, tg_x + half + 18, tg_y + 8, "RED",
             (*lol_theme.LOL["gold_lt"][:3], 235 if not is_blue else 150), 17, "raj_sb_18")
        _txt(dl, tg_x, tg_y - 16, "YOU ARE",
             (*lol_theme.LOL["txt_dim"][:3], 170), 12, "raj_sb_12")

    # Action button (label depends on mode)
    bw, bh = 220, 38
    bx = vw - bw - 110
    by = (hdr_h - bh) // 2
    _act_label = ("START DRAFT BOARD" if _tb.target == "board"
                  else "BEGIN ANALYSIS")
    lol_theme.draw_navy_panel(
        dl, bx, by, bx+bw, by+bh,
        fill=lol_theme._alpha(lol_theme.LOL["gold_dk"], 220),
        border_color=lol_theme.LOL["gold"],
        border_thickness=2, rounding=4)
    _txt(dl, bx + 14, by + 7, _act_label,
         (*lol_theme.LOL["gold_lt"][:3], 235), 22, "raj_sb_22")

    # CANCEL button
    cw, ch = 90, 38
    cx2 = vw - cw - 10
    cy2 = (hdr_h - ch) // 2
    lol_theme.draw_navy_panel(
        dl, cx2, cy2, cx2+cw, cy2+ch,
        fill=lol_theme._alpha(lol_theme.LOL["navy_panel"], 160),
        border_color=lol_theme.LOL["gold_rule"],
        border_thickness=1, rounding=4)
    _txt(dl, cx2 + 14, cy2 + 7, "CANCEL",
         (*lol_theme.LOL["txt_dim"][:3], 220), 20, "raj_sb_18")

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
                        fill=lol_theme._alpha(lol_theme.LOL["navy_mid"], 140),
                        color=(*lol_theme.LOL["blue_side"][:3], 80),
                        rounding=6, parent=dl)
    dpg.draw_rectangle((red_x, slots_top), (red_x+col_w, slots_top+teams_h),
                        fill=lol_theme._alpha(lol_theme.LOL["navy_mid"], 140),
                        color=(*lol_theme.LOL["red_side"][:3], 80),
                        rounding=6, parent=dl)

    _txt(dl, blue_x+14, slots_top+8, "BLUE TEAM",
         (*lol_theme.LOL["blue_side"][:3], 230), 22, "raj_sb_22")
    _txt(dl, red_x+14,  slots_top+8, "RED TEAM",
         (*lol_theme.LOL["red_side"][:3], 230), 21, "raj_sb_22")

    _draw_role_slots(dl, blue_x, slots_top+36, col_w, _tb.blue, slot_h)
    _draw_role_slots(dl, red_x,  slots_top+36, col_w, _tb.red,  slot_h)

    # ── Player pool ───────────────────────────────────────────────
    pool_y = vh - pool_h
    lol_theme.draw_gold_rule(dl, pad, pool_y, vw-pad, pool_y,
                             thickness=1, alpha=180)
    _txt(dl, pad, pool_y+4, "PLAYER POOL",
         (*lol_theme.LOL["txt_dim"][:3], 180), 22, "raj_sb_22")

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
        _txt(dl, pad, ry+8, "All players assigned.",
             (*lol_theme.LOL["txt_dim"][:3], 160), 18, "raj_sb_16")

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

        bg_col  = lol_theme._alpha(lol_theme.LOL["navy_panel"],
                                   200 if p else 90)
        bdr_col = (*rc, 200 if (p or hovering) else 80)

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
            _txt(dl, x+60, sy+max(4, slot_h//2-name_sz//2-2), name.upper(),
                 (*lol_theme.LOL["gold_lt"][:3], 235), name_sz, "raj_24")
            _txt(dl, x+60, sy+slot_h-20, tier[:3].upper(),
                 (*tc[:3], 200), 19, "raj_sb_18")
            sc = _tb_score_str(p)
            if sc:
                _txt(dl, x+width-86, sy+max(4, slot_h//2-13), sc,
                     (*lol_theme.LOL["txt_dim"][:3], 220), 22, "raj_20")
        else:
            _txt(dl, x+60, sy+slot_h//2-9, "drag here",
                 (*lol_theme.LOL["txt_dim"][:3], 110), 19, "raj_sb_18")


def _draw_tb_card(dl, x, y, w, h, player, dragging=False):
    """Draw a compact player card."""
    name      = player.get("name", "?")
    is_random = player.get("is_random", False)
    tier      = player.get("tier", "Unranked")
    tc        = RANK_COLORS.get(tier, RANK_COLORS["Unranked"])
    al        = 240 if dragging else 210

    if is_random:
        dpg.draw_rectangle((x, y), (x+w, y+h),
                            fill=lol_theme._alpha(lol_theme.LOL["navy_panel"],
                                                  130 if not dragging else 190),
                            color=(100, 120, 170, 140 if not dragging else 200),
                            rounding=4, parent=dl)
        # Dashed top edge to signal "unknown player"
        dpg.draw_line((x+4, y+1), (x+w-4, y+1),
                      color=(100, 120, 170, 80), thickness=1, parent=dl)
        _txt(dl, x+10, y+5,    name.upper(), (130, 155, 210, al), 21, "raj_20")
        _txt(dl, x+10, y+h-19, "RAND",       ( 90, 110, 160, int(al*0.7)), 18, "raj_sb_18")
        _txt(dl, x+w-46, y+5,  "~50",
             (*lol_theme.LOL["txt_dim"][:3], int(al*0.85)), 18, "raj_20")
    else:
        dpg.draw_rectangle((x, y), (x+w, y+h),
                            fill=lol_theme._alpha(lol_theme.LOL["navy_panel"],
                                                  240 if dragging else 180),
                            color=(*tc[:3], 220 if dragging else 150),
                            rounding=4, parent=dl)
        # Rank-tier ambient backdrop: subtle pulsing tinted fill keyed to tier
        # color. Higher tiers feel "lit"; low tiers stay dim/cool. Per-card
        # focal motion only — full-screen ambient motion is dropped in v3.
        _t        = (math.sin(time.monotonic() * 1.4 + hash(name) % 100) + 1) / 2
        _pulse_a  = int(18 + _t * 26)
        dpg.draw_rectangle((x+1, y+1), (x+w-1, y+h-1),
                            fill=(*tc[:3], _pulse_a),
                            color=(0, 0, 0, 0), rounding=4, parent=dl)
        # Bottom edge accent strip in tier color — anchors the glow
        dpg.draw_rectangle((x+4, y+h-3), (x+w-4, y+h-1),
                            fill=(*tc[:3], 130),
                            color=(0, 0, 0, 0), rounding=1, parent=dl)
        _txt(dl, x+10, y+5,    name.upper(),
             (*lol_theme.LOL["gold_lt"][:3], al), 23, "raj_24")
        _txt(dl, x+10, y+h-19, tier[:3].upper(),  (*tc[:3], int(al*0.85)), 20, "raj_sb_18")
        sc = _tb_score_str(player)
        if sc:
            _txt(dl, x+w-52, y+5, sc,
                 (*lol_theme.LOL["gold_lt"][:3], al), 20, "raj_20")


def _tb_slot_hit(sx, sy, sw, sh, pos):
    """True if pos=(mx,my) is inside the slot rect (accounting for the 8px inset)."""
    mx, my = pos
    return (sx+8 <= mx <= sx+sw-8) and (sy <= my <= sy+sh)


def _tb_handle_input(vw, vh):
    """Process mouse input for the team builder. Call every frame."""
    mx, my = _content_mouse()

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
        # Board-mode "you are" side toggle. In synced mode, also broadcast
        # the side claim to the server so the swap is authoritative for
        # both clients.
        if _tb.target == "board":
            tg_w, tg_h = 150, 34
            tg_x = vw - 220 - 110 - tg_w - 14
            tg_y = (hdr_h - tg_h) // 2
            if tg_x <= mx <= tg_x+tg_w and tg_y <= my <= tg_y+tg_h:
                new_side = "RED" if mx >= tg_x + tg_w // 2 else "BLUE"
                _tb.board_side = new_side
                if _sync_ui.is_active():
                    _sync_ui.send_set_side(new_side)
                return

        bw, bh = 220, 38
        bx = vw - bw - 110
        by = (hdr_h - bh) // 2
        if bx <= mx <= bx+bw and by <= my <= by+bh:
            # In synced mode, the action button means "I'M READY" — the
            # server advances the phase once both sides ready up. In solo
            # mode it kicks off the local board directly.
            # (Phase 6: the legacy "batch analysis" target was removed.
            # `_tb.target` is always "board" now.)
            if _sync_ui.is_active():
                _sync_ui.send_set_ready(True)
            else:
                _board_begin()
            return

        cw3, ch3 = 90, 38
        cx2 = vw - cw3 - 10
        cy2 = (hdr_h - ch3) // 2
        if cx2 <= mx <= cx2+cw3 and cy2 <= my <= cy2+ch3:
            # v3.0.2: also drop the WS so we don't keep re-running the join
            # callback on every server broadcast and yank ourselves back
            # into TEAM_BUILD.
            _sync_ui.disconnect_if_active()
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
        # As soon as both teams are full, kick off a single batched fetch of
        # every active player's scout sheet so ranked/draft champion pools
        # are cached before the user starts the draft. Deduped via
        # live._scout_inflight + live.scout_sheets cache.
        if all(_tb.blue) and all(_tb.red):
            try:
                names = [p["name"] for p in (_tb.blue + _tb.red)
                         if p and p.get("name")]
                if names:
                    prefetch_scout_sheets(names)
            except Exception:
                pass


def _tb_release_displaced(player):
    """Remove a displaced player from any slot so they return to the pool."""
    for i in range(5):
        if _tb.blue[i] and _tb.blue[i]["name"] == player["name"]:
            _tb.blue[i] = None
            return
        if _tb.red[i] and _tb.red[i]["name"] == player["name"]:
            _tb.red[i] = None
            return


# ---------------------------------------------------------------------------
# Interactive tournament-draft board (U1 layout + U2 interaction)
# (Phase 6: the legacy `_analyse_teams` and `_tb_begin_analysis` War-Room
# entry points were deleted along with the ASSEMBLING/ANALYSING/RESULTS
# phases. BEGIN ANALYSIS is gone — the synced flow and the solo-briefing
# fallback together replace what they did.)
# ---------------------------------------------------------------------------

_BOARD_TAG_COL = {
    "POWER":  lol_theme.LOL["warning"][:3],
    "SAFE":   (90, 180, 120),
    "COUNTER": (212, 90, 80),
    "FLEX":   (155, 140, 222),
    "COMFORT": (150, 178, 208),
    "BAN-P1": (212, 110, 90),
    "BAN-P2": (212, 145, 80),
}

# Viability-tier colors for the TOP CALL viability chip in _draw_board_center.
# Restored in v3.0.3 — the original dict was deleted during Phase 6 cyber.py
# cleanup but a single reference at draft.py:3466 was missed, which crashed
# the board the moment a target_comp surfaced.
_VIAB_COLORS = {
    "STRONG":          lol_theme.LOL["win"][:3],
    "VIABLE":          lol_theme.LOL["gold"][:3],
    "WEAK":            lol_theme.LOL["warning"][:3],
    "NOT RECOMMENDED": lol_theme.LOL["loss"][:3],
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
    """Corner-cut tactical chip: glyph + mono label. Same signature + returned
    width contract as before (callsites position relative to the return)."""
    if not tag:
        return 0
    col = _BOARD_TAG_COL.get(tag, C["txt"][:3])
    h        = 28 if big else 22
    txt_sz   = 15 if big else 13
    font_key = "mono_16" if big else "mono_14"
    glyph_d  = h - 10
    label_w  = len(tag) * (9 if big else 8)   # mono glyphs run wider
    pad_l    = 10 if big else 8
    pad_mid  = 6 if big else 5
    pad_r    = 14 if big else 12
    chip_w   = pad_l + glyph_d + pad_mid + label_w + pad_r
    round_r  = 7 if big else 5
    # Tag-colored chip body (LCS broadcast aesthetic — soft rounded rect).
    dpg.draw_rectangle((x, y), (x + chip_w, y + h),
                       fill=(*col, int(alpha * 0.88)),
                       color=(*col, alpha),
                       thickness=1, rounding=round_r, parent=dl)
    # Glyph (left)
    glyph_cx = x + pad_l + glyph_d // 2
    glyph_cy = y + h // 2
    bg_col   = (*lol_theme.LOL["navy_deep"][:3], alpha)
    _draw_glyph(dl, glyph_cx, glyph_cy, tag, glyph_d, bg_col)
    # Label
    txt_x = glyph_cx + glyph_d // 2 + pad_mid
    txt_y = y + (h - txt_sz) // 2 - 2
    _txt(dl, txt_x, txt_y, tag, bg_col, txt_sz, font_key)
    return chip_w

# Click regions registered by _draw_board, consumed by _board_handle_input.
# Each entry: (x, y, w, h, action, payload)
_board_hits = []

# Per-role slot rects registered by _draw_board_team, consumed by drag handler.
# Each entry: (x, y, w, h, side, role, champ_or_None). Cleared each frame.
_pick_slot_rects = []


class _PickDrag:
    """Drag state for moving a locked champion between role slots on the same
    side after the pick has already been made. Separate from _tb (which drags
    players, not champs)."""
    side = None        # "BLUE" | "RED" while dragging, else None
    from_role = None   # role the champ was picked into
    champ = None       # champion name, for the ghost portrait
    pos = (0, 0)       # current mouse in content-area coords
    was_down = False   # mouse-button-down on previous frame (edge detect)

_pdrag = _PickDrag()


# Mouse position in content-area coords, updated each frame by _draw_board.
# Lets every render helper compute hover state without re-doing the offset math.
_mouse_xy = (0, 0)


def _content_origin():
    """v3.0.5: dynamic content-drawlist screen-space top-left. Replaces the
    old hardcoded (sidebar_w=68, titlebar_h=52) offsets that broke whenever
    the sidebar animated open (200px expanded) or the viewport state changed
    (fullscreen toggle / minimize+restore could leave the sidebar stuck wide,
    making every click miss).

    We read the content drawlist's `rect_min` (absolute screen position) and
    subtract the viewport position to get viewport-relative coords.
    Falls back to the old constants if the item isn't ready or DPG complains."""
    try:
        st = dpg.get_item_state("content_dl") or {}
        rm = st.get("rect_min")
        if rm and len(rm) >= 2:
            vp = dpg.get_viewport_pos()
            return (float(rm[0]) - float(vp[0]),
                    float(rm[1]) - float(vp[1]))
    except Exception:
        pass
    return (68.0, 52.0)


def _content_mouse():
    """Mouse position relative to the content drawlist top-left.
    Use this instead of the (mouse - vp - 68, mouse - vp - 52) idiom that
    only worked when the sidebar was collapsed."""
    try:
        mouse = dpg.get_mouse_pos(local=False)
        vp = dpg.get_viewport_pos()
        ox, oy = _content_origin()
        return (mouse[0] - vp[0] - ox, mouse[1] - vp[1] - oy)
    except Exception:
        return (0.0, 0.0)


def _hover(x, y, w, h):
    mx, my = _mouse_xy
    return x <= mx <= x + w and y <= my <= y + h


# Manual-pool rect (set each draw, used to gate wheel-scroll consumption).
_pool_rect = None

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


def _player_champ_stats(player_name, champ_name):
    """Look up a player's per-champion record. Returns dict or None."""
    if not player_name or not champ_name:
        return None
    champs = (getattr(live, "inhouse_champs", {}) or {}).get(player_name, [])
    for ch in champs:
        if ch.get("champ") == champ_name:
            try:
                wr_pct = int(float(str(ch.get("wr", 0)).replace("%", "") or 0))
            except (ValueError, TypeError):
                wr_pct = 0
            return {
                "wr":     wr_pct,
                "games":  int(ch.get("games", 0) or 0),
                "wins":   int(ch.get("wins", 0) or 0),
                "losses": int(ch.get("losses", 0) or 0),
                "kda":    float(ch.get("kda", 0.0) or 0.0),
            }
    return None


def _player_form(player_name):
    """Return 'HOT' / 'COLD' / 'MIXED' for a player, or empty string."""
    if not player_name:
        return ""
    for p in (getattr(live, "scout", []) or []):
        if p.get("name") == player_name:
            return (p.get("form") or "").upper()
    return ""


_FORM_COLORS = {
    "HOT":   (235, 130, 70),
    "COLD":  (90, 160, 230),
    "MIXED": (170, 170, 170),
}

# Cyan for synergy callouts — distinct from SAFE chip green and form-HOT orange.
_SYNERGY_COL_OK   = (90, 200, 215)
_SYNERGY_COL_BAD  = (220, 110, 110)


def _truncate_band(s, max_chars):
    """Truncate `s` cleanly: prefer the last separator before max_chars, so
    we never cut a fact mid-word (e.g. '...4.2 K' becomes '...11g')."""
    if not s or len(s) <= max_chars:
        return s
    cut = s[:max_chars]
    sep = cut.rfind(" · ")
    if sep <= max_chars // 2:
        sep = cut.rfind("  ·  ")
    if sep > max_chars // 2:
        return s[:sep].rstrip()
    return cut.rstrip() + "…"


def _enemy_threat(champ_name, enemy_players):
    """Find the enemy player with the strongest profile on `champ_name`.
    Returns {player, wr, games, kda} or None."""
    best = None
    for pl in enemy_players or []:
        pname = pl.get("name", "")
        s = _player_champ_stats(pname, champ_name)
        if not s or s["games"] <= 0:
            continue
        weight = s["wr"] * s["games"]   # rough threat = WR × volume
        if best is None or weight > best["_w"]:
            best = {**s, "player": pname, "_w": weight}
    return best


def _lane_matchup(your_champ, enemy_champ):
    """Signed lane advantage for `your_champ` vs `enemy_champ` (~ -8..+8).
    Looks up engine LANE_MATCHUPS table; flips sign if mirrored entry."""
    if not your_champ or not enemy_champ:
        return 0
    LM = getattr(_eng, "LANE_MATCHUPS", {}) or {}
    if (your_champ, enemy_champ) in LM:
        try:
            return int(LM[(your_champ, enemy_champ)])
        except (TypeError, ValueError):
            return 0
    if (enemy_champ, your_champ) in LM:
        try:
            return -int(LM[(enemy_champ, your_champ)])
        except (TypeError, ValueError):
            return 0
    return 0


def _synergy_callouts(champ, our_locked):
    """Return list of (other_champ, kind, strength) where kind is 'syn'|'anti'.
    Only flags meaningful pairs (|strength| >= 0.20)."""
    out = []
    if not champ or not our_locked:
        return out
    SYN  = getattr(_eng, "SYNERGIES", {}) or {}
    ANTI = getattr(_eng, "ANTI_SYNERGIES", {}) or {}
    for c2 in our_locked:
        if not c2 or c2 == champ:
            continue
        s = SYN.get((champ, c2), SYN.get((c2, champ), 0))
        if s and s >= 0.20:
            out.append((c2, "syn", float(s)))
            continue
        a = ANTI.get((champ, c2), ANTI.get((c2, champ), 0))
        if a and a >= 0.20:
            out.append((c2, "anti", float(a)))
    return out


def _is_contested(champ_name, blue_players, red_players):
    """True only if a player on EACH side has actually played `champ_name`
    in customs ≥ 3 games (matches the engine's strict `customs_champs` rule
    so the TOP CALL glyph / contested ladder agree with the suggestions)."""
    if not champ_name:
        return False
    icmp = getattr(live, "inhouse_champs", {}) or {}

    def _side_plays(players):
        for pl in players or []:
            for ch in (icmp.get(pl.get("name", ""), []) or []):
                if ch.get("champ") == champ_name:
                    try:
                        if float(ch.get("games", 0)) >= 3:
                            return True
                    except (TypeError, ValueError):
                        pass
        return False

    return _side_plays(blue_players) and _side_plays(red_players)


# Archetype picker: 7 engine archetypes + AUTO. Each chip has a distinct color
# so the active one reads instantly. AUTO = engine picks automatically.
_ARCH_PICKER = (
    (None,                "AUTO",     (230, 190,  80)),
    ("Teamfight",         "TF",       (210, 110,  90)),
    ("Pick",              "Pick",     (170, 120, 220)),
    ("Split Push",        "Split",    (110, 180, 120)),
    ("Poke / Siege",      "Poke",     (220, 180,  80)),
    ("Protect the Carry", "Protect",  ( 90, 180, 210)),
    ("Dive",              "Dive",     (235, 130,  70)),
    ("Scaling",           "Scale",    (110, 140, 220)),
)


def _draw_arch_picker(dl, x, y, w, current):
    """Horizontal chip row — lets the user lock a target archetype.
    Returns the consumed height in px."""
    label = "TARGET COMP"
    _txt(dl, x + 16, y + 8, label,
         (*lol_theme.LOL["gold_lt"][:3], 220), 13, "raj_sb_12")
    lw = int(len(label) * 13 * 0.6)
    cx = x + 16 + lw + 12
    chip_h = 26
    for arch_key, lbl, col in _ARCH_PICKER:
        is_active = (arch_key == current)
        disp = f"* {lbl} *" if is_active else f" {lbl} "
        cw = len(disp) * 8 + 8
        hov = _hover(cx, y + 4, cw, chip_h)
        if is_active:
            # Active: filled chip
            fill_a = 230
            dpg.draw_rectangle((cx, y + 4), (cx + cw, y + 4 + chip_h),
                               fill=(*col, fill_a),
                               color=(*col, 255),
                               thickness=2, rounding=5, parent=dl)
            txt_col = (*lol_theme.LOL["navy_deep"][:3], 255)
        else:
            # Inactive: outline-only, brighten on hover
            fill_a   = 80 if hov else 28
            border_a = 235 if hov else 150
            dpg.draw_rectangle((cx, y + 4), (cx + cw, y + 4 + chip_h),
                               fill=(*col, fill_a),
                               color=(*col, border_a),
                               thickness=2 if hov else 1,
                               rounding=5, parent=dl)
            txt_col = (*col, 245 if hov else 210)
        _txt(dl, cx + 8, y + 8, disp, txt_col, 13, "raj_sb_12")
        _board_hits.append((cx, y + 4, cw, chip_h, "set_arch", arch_key))
        cx += cw + 6
    return chip_h + 12


# v4.0.3: cache for _enemy_target_comp. The underlying call proxies to the
# Fly server's /api/engine/target_archetype, so doing it per-frame from the
# main render thread blocked the UI and made the draft board feel laggy
# (and made the OS show "not responding" when closing). Recompute only when
# the relevant inputs actually change.
_enemy_tc_cache = {"sig": None, "value": {}}

# v4.0.3: per-slot pool-depth cache. _draw_board_team's depth capsule called
# _candidates_for_player + _scout_champs_for_players for every empty slot on
# both teams every frame; memoize by (side, role, player, board sig).
_depth_cache = {}


def _enemy_target_comp(b, act):
    """Run target_archetype for the team that ISN'T currently acting, so the
    STRATEGIC sub-panel can show their wincon alongside ours. Cached on a
    signature of (enemy_side, picks, bans, pointer, roster) so we don't make
    a network call every frame."""
    if b is None or act is None:
        return {}
    enemy_side = "RED" if act.side == "BLUE" else "BLUE"
    try:
        enemy_players = list(b.players.get(enemy_side, []))
        roster_sig = tuple((p or {}).get("name", "") for p in enemy_players)
        sig = (enemy_side, b.pointer, roster_sig,
               tuple(sorted(b.picks.get("BLUE", {}).items())),
               tuple(sorted(b.picks.get("RED", {}).items())),
               tuple(b.bans.get("BLUE", [])),
               tuple(b.bans.get("RED", [])))
        if sig == _enemy_tc_cache["sig"]:
            return _enemy_tc_cache["value"]
        val = target_archetype(
            b, enemy_side,
            getattr(live, "inhouse_champs", {}) or {},
            getattr(live, "primary_roles", {}) or {},
            scout_champs=_scout_champs_for_players(enemy_players)) or {}
        _enemy_tc_cache["sig"] = sig
        _enemy_tc_cache["value"] = val
        return val
    except Exception:
        return {}


# v4.0.3: cache for _enemy_pick_preview — engine candidate-search runs every
# frame for every open enemy role; cache by board signature so it only
# recomputes when something changed.
_enemy_preview_cache = {"sig": None, "value": []}


def _enemy_pick_preview(b, side, n=3):
    """For each open enemy role, return (role, player_name, [top champion candidates]).
    Used by the bottom-of-team-column 'next-pick' ribbon."""
    if b is None:
        return []
    try:
        roster_sig = tuple((p or {}).get("name", "")
                           for p in (b.players.get(side, []) or []))
        sig = (side, b.pointer, n, roster_sig,
               tuple(sorted(b.picks.get("BLUE", {}).items())),
               tuple(sorted(b.picks.get("RED", {}).items())),
               tuple(b.bans.get("BLUE", [])),
               tuple(b.bans.get("RED", [])))
    except Exception:
        sig = None
    if sig is not None and sig == _enemy_preview_cache["sig"]:
        return _enemy_preview_cache["value"]
    used = b.used_champs() if hasattr(b, "used_champs") else set()
    icmp = getattr(live, "inhouse_champs", {}) or {}
    proles = getattr(live, "primary_roles", {}) or {}
    scout_map = _scout_champs_for_players(list(b.players.get(side, [])))
    out = []
    if not hasattr(b, "open_roles"):
        return out
    for role in b.open_roles(side):
        pl = b.player_for_role(side, role) if hasattr(b, "player_for_role") else None
        if not pl:
            continue
        try:
            cands = _candidates_for_player(pl, role, icmp, proles, used, k=n,
                                           scout_champs=scout_map)
        except Exception:
            cands = []
        names = [c[0] for c in cands][:n]
        out.append((role, pl.get("name", "?"), names))
    if sig is not None:
        _enemy_preview_cache["sig"] = sig
        _enemy_preview_cache["value"] = out
    return out


def _team_counter_covers(champ_to_ban, our_locked):
    """True if any of our locked picks 'covers' (counters) `champ_to_ban`,
    making the ban lower-priority. Uses engine COUNTERS table."""
    if not champ_to_ban or not our_locked:
        return False
    CT = getattr(_eng, "COUNTERS", {}) or {}
    for our_ch in our_locked:
        if (our_ch, champ_to_ban) in CT and CT[(our_ch, champ_to_ban)] >= 0.55:
            return True
    return False


def _filter_pool(pool, query):
    """Case-insensitive substring filter on champion name in (champ, role) tuples."""
    if not query:
        return pool
    q = query.upper()
    return [(c, r) for c, r in pool if q in c.upper()]


def _lobby_begin_synced():
    """Phase 1 join callback. After draft_sync.connect() succeeds and the
    first server snapshot arrives, drop into TEAM_BUILD (the lobby) — NOT
    directly into BOARD. The server's phase-machine drives the transition
    to BOARD later, once both sides press READY.

    Called by ui.draft_sync_ui after a successful join.
    """
    placeholder = lambda side, i: {
        "name": f"{side[0]}{i+1}",
        "tier": "Unranked",
        "final_score": 50.0,
        "score": 50.0,
        "role": _ROLES[i],
    }
    blue_players = [placeholder("BLUE", i) for i in range(5)]
    red_players  = [placeholder("RED",  i) for i in range(5)]
    # Server snapshot will overwrite our_side via sync_tick; initial value
    # is legal-but-cosmetic. The new server protocol uses `side` (BLUE/RED/
    # SPEC) on each client; our_side here is the legacy field surfaced for
    # the rest of the codebase.
    draft.board = DraftBoardState(blue_players, red_players,
                                  our_side=_sync_ui.my_side() or "BLUE")
    draft.board_pool_search = ""
    draft.board_pool_scroll = 0
    draft.board_target_arch = None

    # Initialise the team-builder so the lobby renders correctly. _tb_open
    # doesn't actually use vw/vh — its arguments are vestigial — so passing
    # zeros is safe. The team-builder draws against the current viewport
    # each frame.
    _tb_open(0, 0, target="board")
    draft.phase = DraftPhase.TEAM_BUILD


def _board_begin_synced():
    """Legacy callback retained for compatibility. The new join-flow uses
    _lobby_begin_synced (above). This stays for any callsite that still
    expects an immediate BOARD transition, and as the fallback when the
    server reports it's already in BOARD/DONE (i.e. you joined late to an
    in-progress draft)."""
    placeholder = lambda side, i: {
        "name": f"{side[0]}{i+1}",
        "tier": "Unranked",
        "final_score": 50.0,
        "score": 50.0,
        "role": _ROLES[i],
    }
    blue_players = [placeholder("BLUE", i) for i in range(5)]
    red_players  = [placeholder("RED",  i) for i in range(5)]
    draft.board = DraftBoardState(blue_players, red_players,
                                  our_side=_sync_ui.my_side() or "BLUE")
    draft.board_pool_search = ""
    draft.board_pool_scroll = 0
    draft.board_target_arch = None
    draft.phase = DraftPhase.BOARD
    _board_recompute()


def _on_lobby_join():
    """Adaptive join callback: routes to LOBBY (TEAM_BUILD) by default, but
    if the server is already past LOBBY (mid-draft session in progress),
    jumps straight to BOARD. This lets latecomers spectate in-progress
    drafts without dropping back to IDLE."""
    phase = _sync_ui.server_phase()
    if phase in ("BOARD", "DONE"):
        _board_begin_synced()
    else:
        _lobby_begin_synced()


# Hand the bridge to the sync UI module so it can call us back without a
# circular import.
_sync_ui.set_join_callback(_on_lobby_join)


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
    draft.board_pool_search = ""
    draft.board_pool_scroll = 0
    draft.board_target_arch = None
    draft.phase = DraftPhase.BOARD
    # Kick off background scout-sheet fetch. Sheets land into live.scout_sheets
    # and are picked up by the next _board_recompute (next pick/ban or arch
    # change). We don't trigger recompute from the worker thread to avoid
    # racing with the UI render loop.
    try:
        names = [p.get("name") for p in (blue_players + red_players)
                 if p and p.get("name")]
        if names:
            prefetch_scout_sheets(names)
    except Exception:
        pass
    _board_recompute()


def _board_recompute():
    b = draft.board
    if b is None:
        draft.board_rec = None
        return
    try:
        # Build a scout_champs map spanning both teams so the engine sees
        # every active player's ranked/draft champion pool.
        all_players = list(b.players.get("BLUE", [])) + list(b.players.get("RED", []))
        scout_map = _scout_champs_for_players(all_players)
        draft.board_rec = recommend_action(
            b, getattr(live, "inhouse_champs", {}) or {},
            getattr(live, "primary_roles", {}) or {}, n=6,
            forced_arch=draft.board_target_arch,
            scout_champs=scout_map)
    except Exception as e:                       # pragma: no cover
        draft.board_rec = {
            "done": b.is_complete(), "action": b.current_action(),
            "kind": None, "our_turn": False, "suggestions": [],
            "target_comp": {}, "cohesion": [], "enemy_weakness": {},
            "notes": [f"recommend error: {e}"]}


def _board_apply(champ, role=None):
    if draft.board is None or not champ:
        return
    # In a synced session the server is the source of truth — route the action,
    # then let _draw_board's sync_tick fold the broadcast back into draft.board.
    if _sync_ui.route_apply(draft, champ, role):
        draft.board_pool_search = ""
        draft.board_pool_scroll = 0
        return
    if draft.board.apply(champ, role):
        draft.board_pool_search = ""        # fresh action → reset search/scroll
        draft.board_pool_scroll = 0
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


# ---------------------------------------------------------------------------
# Sync lobby — drag-and-drop team builder + START gate
# ---------------------------------------------------------------------------

# Hit rects emitted by _draw_sync_lobby and consumed by _lobby_handle_input.
# (x, y, w, h, "lobby_slot", (side, idx)) for slot drop targets.
# (x, y, w, h, "lobby_pool", player_dict) for source cards.
_lobby_hits: list = []
# True after the lobby has populated _tb.pool from the current data layer for
# this lobby session; reset on disconnect / EXIT.
_lobby_pool_ready: bool = False


def _lobby_reset_pool():
    """Force the next lobby frame to refresh _tb.pool from data sources."""
    global _lobby_pool_ready
    _lobby_pool_ready = False


def _draw_sync_lobby(dl, vw, vh):
    """Pre-draft lobby shown when a sync session is open but
    `start_draft` hasn't fired yet. Surfaces connection state, who's
    connected per slot, hosts the team-builder drag-and-drop, and a
    START DRAFT button (host only)."""
    from data import draft_sync as _ds
    client = _ds.active()
    snap = client.state() if client else None
    status = _sync_ui.connection_status()
    is_host = bool((client.you() or {}).get("is_host")) if client else False

    # Lazily fill _tb.pool with live scouting data once per lobby session.
    global _lobby_pool_ready
    if not _lobby_pool_ready:
        _tb.pool      = list(_get_player_pool())
        _tb.drag      = None
        _tb.drag_from = None
        _lobby_pool_ready = True

    _lobby_hits.clear()

    # Background — solid navy (no full-screen ambient motion per user pref)
    dpg.draw_rectangle((0, 0), (vw, vh),
                       fill=lol_theme.LOL["navy_deep"],
                       color=(0, 0, 0, 0), parent=dl)

    # Header
    hdr_h = 54
    dpg.draw_rectangle((0, 0), (vw, hdr_h),
                       fill=lol_theme.LOL["navy_mid"],
                       color=(0, 0, 0, 0), parent=dl)
    lol_theme.draw_gold_rule(dl, 0, hdr_h - 1, vw, hdr_h - 1,
                             thickness=1, alpha=220)
    _txt(dl, 24, 14, "DRAFT LOBBY",
         (*lol_theme.LOL["gold_lt"][:3], 245), 26, "cinzel_24")
    if status:
        col = (lol_theme.LOL["win"] if status == "synced"
               else lol_theme.LOL["warning"])
        _txt(dl, 220, 18, status[:32], (*col[:3], 230), 16, "raj_sb_16")

    # v4.0.3: clear "OPPONENT CONNECTED?" badge in the header. Without this,
    # users on the team-builder screen had no quick way to tell whether the
    # other side had joined — they'd see only their own slot on the WHO'S
    # CONNECTED rail and not realize it was waiting on the opponent.
    sides_map = (snap or {}).get("sides") or {}
    my_side_for_badge = (client.you() or {}).get("side", "") if client else ""
    opp_side = ("RED" if my_side_for_badge == "BLUE"
                else "BLUE" if my_side_for_badge == "RED" else "")
    opp_name = sides_map.get(opp_side) if opp_side else None
    if opp_name:
        badge_text = f"OPPONENT: {str(opp_name)[:12]}"
        badge_col = lol_theme.LOL["win"]
        dot_col = lol_theme.LOL["win"]
    elif my_side_for_badge in ("BLUE", "RED"):
        badge_text = "WAITING FOR OPPONENT"
        badge_col = lol_theme.LOL["warning"]
        dot_col = lol_theme.LOL["warning"]
    else:
        badge_text = ""
        badge_col = lol_theme.LOL["gold_rule"]
        dot_col = lol_theme.LOL["gold_rule"]
    if badge_text:
        bw = max(170, len(badge_text) * 9 + 38)
        bh = 30
        bx = 460
        by = (hdr_h - bh) // 2
        lol_theme.draw_navy_panel(
            dl, bx, by, bx + bw, by + bh,
            fill=lol_theme._alpha(lol_theme.LOL["navy_panel"], 200),
            border_color=badge_col,
            border_thickness=1, rounding=4)
        # Status dot — pulses gently when waiting so it draws the eye.
        if opp_name:
            dot_a = 235
        else:
            pulse = (math.sin(time.monotonic() * 2.4 * 2 * math.pi) + 1) / 2
            dot_a = int(140 + pulse * 110)
        dpg.draw_circle((bx + 14, by + bh // 2), 5,
                        fill=(*dot_col[:3], dot_a),
                        color=(0, 0, 0, 0), parent=dl)
        _txt(dl, bx + 26, by + 6, badge_text,
             (*badge_col[:3], 240), 15, "raj_sb_16")

    # EXIT button (top-right) — registers a hit
    cb_w, cb_h = 100, 38
    cb_x = vw - cb_w - 16
    cb_y = (hdr_h - cb_h) // 2
    lol_theme.draw_navy_panel(
        dl, cb_x, cb_y, cb_x + cb_w, cb_y + cb_h,
        fill=lol_theme._alpha(lol_theme.LOL["navy_panel"], 220),
        border_color=lol_theme.LOL["red_side"],
        border_thickness=1, rounding=4)
    _txt(dl, cb_x + 30, cb_y + 9, "EXIT",
         (*lol_theme.LOL["red_side"][:3], 235), 18, "raj_sb_18")
    _board_hits.append((cb_x, cb_y, cb_w, cb_h, "exit", None))

    # ── YOU [side] indicator + swap button (top-right, left of EXIT) ──
    # Server-authoritative: `set_side("RED")` triggers a true swap in v3.0.2+
    # so clicking the arrow flips both players' sides at once.
    my_side_str = (client.you() or {}).get("side", "") if client else ""
    if my_side_str in ("BLUE", "RED"):
        side_col = lol_theme.LOL[
            "blue_side" if my_side_str == "BLUE" else "red_side"]
        you_w, you_h = 130, 38
        you_x = cb_x - you_w - 12
        you_y = cb_y
        lol_theme.draw_navy_panel(
            dl, you_x, you_y, you_x + you_w, you_y + you_h,
            fill=lol_theme._alpha(lol_theme.LOL["navy_panel"], 220),
            border_color=side_col,
            border_thickness=2, rounding=4)
        _txt(dl, you_x + 12, you_y + 9, f"YOU: {my_side_str}",
             (*side_col[:3], 240), 18, "raj_sb_18")
        # Swap arrow button — to the left of the YOU pill. Only meaningful
        # when both sides are claimed; otherwise renders dim + ignores clicks.
        sides_claimed = sum(1 for k in ("BLUE", "RED")
                            if k in ((snap or {}).get("sides") or {}))
        sw_w, sw_h = 44, 38
        sw_x = you_x - sw_w - 8
        sw_y = you_y
        can_swap = sides_claimed >= 1   # always lets you flip; server-side
                                        # handles the swap-vs-take logic
        sw_border = (lol_theme.LOL["gold"] if can_swap
                     else lol_theme.LOL["gold_dk"])
        sw_text_col = (lol_theme.LOL["gold_lt"] if can_swap
                       else lol_theme.LOL["txt_dim"])
        lol_theme.draw_navy_panel(
            dl, sw_x, sw_y, sw_x + sw_w, sw_y + sw_h,
            fill=lol_theme._alpha(lol_theme.LOL["navy_panel"], 220),
            border_color=sw_border,
            border_thickness=2 if can_swap else 1, rounding=4)
        # v3.0.5: draw a swap arrow shape rather than the ⇄ glyph — the
        # Rajdhani font in use here doesn't have U+21C4 in its glyph set,
        # so the unicode literal was rendering as "?".
        arrow_a = 240 if can_swap else 130
        arrow_col = (*sw_text_col[:3], arrow_a)
        ax_c = sw_x + sw_w // 2
        ay_c = sw_y + sw_h // 2
        # Top arrow (rightwards)
        dpg.draw_line((ax_c - 10, ay_c - 5), (ax_c + 8, ay_c - 5),
                      color=arrow_col, thickness=2, parent=dl)
        dpg.draw_polygon([(ax_c + 10, ay_c - 5),
                          (ax_c + 4, ay_c - 9),
                          (ax_c + 4, ay_c - 1)],
                         fill=arrow_col, color=(0, 0, 0, 0), parent=dl)
        # Bottom arrow (leftwards)
        dpg.draw_line((ax_c - 8, ay_c + 5), (ax_c + 10, ay_c + 5),
                      color=arrow_col, thickness=2, parent=dl)
        dpg.draw_polygon([(ax_c - 10, ay_c + 5),
                          (ax_c - 4, ay_c + 1),
                          (ax_c - 4, ay_c + 9)],
                         fill=arrow_col, color=(0, 0, 0, 0), parent=dl)
        if can_swap:
            opp_side = "RED" if my_side_str == "BLUE" else "BLUE"
            _board_hits.append((sw_x, sw_y, sw_w, sw_h, "swap_side", opp_side))

    slots_map = (snap or {}).get("slots") or {}
    specs = (snap or {}).get("spectators") or []
    host_name = (snap or {}).get("host")
    you = client.you() if client else {}
    my_slot = you.get("slot", "")
    players_state = ((snap or {}).get("state") or {}).get("players") or {}

    # ── WHO'S CONNECTED rail (compact, read-only, no drag) ───────────
    # One line per side listing all 5 connection slots and their occupant.
    # Decoupled from draft rosters below — joining/leaving the room does NOT
    # change team composition; it just tells everyone who's in the call.
    rail_y = hdr_h + 12
    rail_h = 56
    lol_theme.draw_navy_panel(
        dl, 20, rail_y, vw - 20, rail_y + rail_h,
        fill=lol_theme._alpha(lol_theme.LOL["navy_mid"], 200),
        border_color=lol_theme.LOL["gold_rule"],
        border_thickness=1, rounding=4)
    _txt(dl, 30, rail_y + 4, "WHO'S CONNECTED",
         (*lol_theme.LOL["txt_dim"][:3], 200), 13, "raj_sb_12")
    for ci, (side, accent) in enumerate(
        (("BLUE", lol_theme.SIDE_ACCENT["BLUE"]),
         ("RED",  lol_theme.SIDE_ACCENT["RED"]))):
        y = rail_y + 22 + ci * 16
        _txt(dl, 32, y, f"{side[0]}:", (*accent[:3], 230), 14, "raj_sb_14")
        x = 56
        for i in range(5):
            sk = f"{side.lower()}{i+1}"
            occ = slots_map.get(sk)
            label = f"{i+1} {occ}" if occ else f"{i+1} ·"
            col = ((*lol_theme.LOL["txt"][:3], 230) if occ
                   else (*lol_theme.LOL["txt_dim"][:3], 130))
            if occ and host_name and occ == host_name:
                label += "(h)"
            if sk == my_slot:
                col = (*lol_theme.LOL["gold_lt"][:3], 240)
            _txt(dl, x, y, label[:24], col, 14, "raj_sb_14")
            x += max(110, (vw - 80) // 5)
    if specs:
        _txt(dl, vw - 280, rail_y + 4,
             f"SPECTATORS: {len(specs)}  ({' '.join(specs)[:30]})",
             (*lol_theme.LOL["txt_dim"][:3], 200), 13, "raj_sb_12")

    # ── DRAFT TEAMS — separate roster boxes, host drag-and-drop ──────
    teams_y      = rail_y + rail_h + 14
    col_w        = (vw - 60) // 2
    row_h        = 46
    slot_box_h   = row_h - 6
    teams_header = 26
    rosters_bottom = teams_y + teams_header + 5 * row_h

    for ci, (side, accent) in enumerate(
        (("BLUE", lol_theme.SIDE_ACCENT["BLUE"]),
         ("RED",  lol_theme.SIDE_ACCENT["RED"]))):
        cx = 30 + ci * col_w
        title = f"{side} ROSTER"
        _txt(dl, cx, teams_y, title, (*accent[:3], 240), 20, "raj_sb_20")
        lol_theme.draw_gold_rule(dl, cx, teams_y + 22,
                                 cx + col_w - 30, teams_y + 22,
                                 thickness=1, alpha=200)
        for i, role in enumerate(_ROLES):
            y = teams_y + teams_header + i * row_h
            box_x1 = cx
            box_x2 = cx + col_w - 30
            try:
                pl = (players_state.get(side) or [])[i]
            except IndexError:
                pl = None
            has_real = bool(pl and pl.get("name") and pl.get("tier"))

            hover = (_tb.drag is not None and is_host
                     and box_x1 <= _tb.drag_pos[0] <= box_x2
                     and y <= _tb.drag_pos[1] <= y + slot_box_h)
            box_fill = lol_theme._alpha(
                lol_theme.LOL["navy_panel"],
                220 if has_real else (180 if hover else 130))
            box_border = (*accent[:3], 230 if (has_real or hover) else 80)
            dpg.draw_rectangle((box_x1, y), (box_x2, y + slot_box_h),
                               fill=box_fill, color=box_border,
                               thickness=1, rounding=4, parent=dl)
            if hover:
                dpg.draw_rectangle((box_x1, y), (box_x2, y + slot_box_h),
                                   fill=(*accent[:3], 28),
                                   color=(*accent[:3], 200),
                                   thickness=1, rounding=4, parent=dl)

            # Role tag strip on the left
            rc = _ROLE_COLORS.get(role, (120, 120, 120))
            dpg.draw_rectangle((box_x1, y), (box_x1 + 50, y + slot_box_h),
                               fill=(*rc, 60), color=(0, 0, 0, 0),
                               rounding=4, parent=dl)
            _txt(dl, box_x1 + 8, y + slot_box_h // 2 - 9, role,
                 (*rc, 240), 16, "raj_sb_16")

            if has_real:
                tier_c = RANK_COLORS.get(pl.get("tier", "Unranked"),
                                         RANK_COLORS["Unranked"])
                _txt(dl, box_x1 + 60, y + 4, pl["name"].upper(),
                     (*lol_theme.LOL["gold_lt"][:3], 235), 19, "raj_24")
                _txt(dl, box_x1 + 60, y + slot_box_h - 18,
                     pl.get("tier", "Unranked")[:4].upper(),
                     (*tier_c[:3], 220), 14, "raj_sb_14")
                sc = _tb_score_str(pl)
                if sc:
                    _txt(dl, box_x2 - 56, y + 6, sc,
                         (*lol_theme.LOL["txt_dim"][:3], 220), 18, "raj_sb_18")
            elif is_host:
                _txt(dl, box_x1 + 60, y + slot_box_h // 2 - 9,
                     "drag a player here",
                     (*lol_theme.LOL["txt_dim"][:3], 160), 14, "raj_sb_14")
            else:
                _txt(dl, box_x1 + 60, y + slot_box_h // 2 - 9,
                     "—", (*lol_theme.LOL["txt_dim"][:3], 150), 14, "raj_sb_14")

            _lobby_hits.append((box_x1, y, box_x2 - box_x1, slot_box_h,
                                "lobby_slot", (side, i)))

    # ── Player pool (host-only drag-and-drop) ────────────────────────
    pool_top    = rosters_bottom + 18
    sb_w, sb_h  = 320, 56
    sb_y        = vh - sb_h - 60
    pool_bottom = sb_y - 28

    # Section header
    hdr_label = ("HOST: drag a player onto a slot to assign"
                 if is_host
                 else "PLAYER POOL")
    _txt(dl, 30, pool_top, hdr_label,
         (*lol_theme.LOL["gold_lt"][:3], 220), 16, "raj_sb_16")
    lol_theme.draw_gold_rule(dl, 30, pool_top + 22, vw - 30, pool_top + 22,
                             thickness=1, alpha=180)

    pool_grid_top = pool_top + 30
    pool_grid_h   = max(0, pool_bottom - pool_grid_top)

    if pool_grid_h >= _TB_CARD_H + 4:
        # Filter pool: hide players already assigned to either side.
        assigned_names = set()
        for side in ("BLUE", "RED"):
            for p in (players_state.get(side) or []):
                if isinstance(p, dict) and p.get("name"):
                    assigned_names.add(p["name"])
        pool_vis = [p for p in _tb.pool
                    if p.get("name") not in assigned_names
                    and (not _tb.drag or p.get("name") != _tb.drag.get("name"))]

        cw2  = _TB_CARD_W
        ch2  = _TB_CARD_H
        cgap = 8
        cols = max(1, (vw - 60 + cgap) // (cw2 + cgap))

        max_rows = pool_grid_h // (ch2 + cgap)
        max_cards = max_rows * cols

        for i, p in enumerate(pool_vis[:max_cards]):
            px = 30 + (i % cols) * (cw2 + cgap)
            py = pool_grid_top + (i // cols) * (ch2 + cgap)
            _draw_tb_card(dl, px, py, cw2, ch2, p)
            if is_host:
                _lobby_hits.append((px, py, cw2, ch2, "lobby_pool", p))

        if not pool_vis and is_host:
            _txt(dl, 30, pool_grid_top + 8,
                 "All players assigned — press READY UP.",
                 (*lol_theme.LOL["txt_dim"][:3], 160), 16, "raj_sb_14")
        if len(pool_vis) > max_cards:
            _txt(dl, vw - 240, pool_top,
                 f"(+{len(pool_vis) - max_cards} hidden — resize window)",
                 (*lol_theme.LOL["txt_dim"][:3], 170), 13, "raj_sb_12")

    # ── Dragged card (top layer) ────────────────────────────────────
    if _tb.drag and is_host:
        mx, my = _tb.drag_pos
        _draw_tb_card(dl, mx - _TB_CARD_W // 2, my - _TB_CARD_H // 2,
                      _TB_CARD_W, _TB_CARD_H, _tb.drag, dragging=True)

    # READY UP button — centered, big, gold when enabled
    can, reason = _sync_ui.can_start_draft()
    sb_w, sb_h = 320, 56
    sb_x = vw // 2 - sb_w // 2
    sb_y = vh - sb_h - 60

    btn_fill = (lol_theme.LOL["navy_lt"] if can
                else lol_theme._alpha(lol_theme.LOL["navy_panel"], 120))
    btn_border = lol_theme.LOL["gold"] if can else lol_theme.LOL["gold_dk"]
    txt_col = lol_theme.LOL["gold_lt"] if can else lol_theme.LOL["txt_dim"]
    lol_theme.draw_navy_panel(
        dl, sb_x, sb_y, sb_x + sb_w, sb_y + sb_h,
        fill=btn_fill, border_color=btn_border,
        border_thickness=2 if can else 1, rounding=6)
    label = "READY UP"
    label_x = sb_x + (sb_w - len(label) * 16) // 2
    _txt(dl, label_x, sb_y + 16, label,
         (*txt_col[:3], 235 if can else 130), 26, "cinzel_24")
    if can:
        _board_hits.append((sb_x, sb_y, sb_w, sb_h, "start_draft", None))

    # Hint line below the button explaining what's needed
    hint_y = sb_y + sb_h + 14
    if you.get("is_host"):
        hint = ("host — press READY when ready"
                if can else f"waiting: {reason}")
    else:
        hint = "waiting for host to press READY UP"
    _txt(dl, vw // 2 - len(hint) * 4, hint_y, hint,
         (*lol_theme.LOL["txt_dim"][:3], 200), 16, "raj_sb_14")

    # ── Solo fallback (Phase 5): if only one client has claimed a side,
    # show a 30s countdown banner + a "Continue solo (briefing only)"
    # link that bypasses the synced draft entirely.
    _draw_solo_fallback(dl, vw, vh, snap)


_SOLO_LOBBY_TIMEOUT_S = 30.0


def _draw_solo_fallback(dl, vw, vh, snap):
    """Slim banner above the READY button that lets a lone user skip
    straight to a local BRIEFING preview when no opponent joins. Renders
    nothing if both sides are claimed, or before the 30s threshold."""
    sides = (snap or {}).get("sides") or {}
    claimed = sum(1 for k in ("BLUE", "RED") if k in sides)
    if claimed >= 2:
        # Two sides claimed — the regular READY-UP flow takes over. Reset
        # the lobby-entered timestamp so a future single-occupant lobby
        # restarts the countdown cleanly.
        draft.lobby_entered_at = 0.0
        return
    # First frame in a solo lobby — start the clock.
    if not draft.lobby_entered_at:
        draft.lobby_entered_at = time.monotonic()
    elapsed = time.monotonic() - draft.lobby_entered_at
    remaining = max(0.0, _SOLO_LOBBY_TIMEOUT_S - elapsed)

    bx, bh = vw - 80, 56
    bx0 = 40
    by0 = vh - 200
    if by0 < 0:
        return
    lol_theme.draw_navy_panel(
        dl, bx0, by0, bx0 + bx, by0 + bh,
        fill=lol_theme._alpha(lol_theme.LOL["navy_mid"], 220),
        border_color=lol_theme.LOL["gold_rule"],
        border_thickness=1, rounding=4)
    if remaining > 0:
        msg = f"Waiting for opponent…  {int(remaining)}s"
        _txt(dl, bx0 + 18, by0 + 10, msg,
             (*lol_theme.LOL["txt"][:3], 230), 16, "raj_sb_16")
    else:
        msg = "No opponent — solo briefing available"
        _txt(dl, bx0 + 18, by0 + 10, msg,
             (*lol_theme.LOL["warning"][:3], 235), 16, "raj_sb_16")
    sub = "Continue solo (briefing only)"
    sub_x = bx0 + bx - len(sub) * 9 - 18
    _txt(dl, sub_x, by0 + 30, sub,
         (*lol_theme.LOL["gold_lt"][:3], 230), 14, "raj_sb_14")
    # Register a click rect for the "Continue solo" link covering the
    # right half of the banner — the user clicks anywhere on the link.
    link_x = sub_x - 6
    link_y = by0 + 26
    link_w = bx0 + bx - link_x - 6
    link_h = bh - 32
    _board_hits.append((link_x, link_y, link_w, link_h, "go_solo", None))


# ---------------------------------------------------------------------------
# Phase 3 scaffolding for the new SCOUTING / BRIEFING / ARCHETYPE screens.
# These render via lol_theme.draw_waiting_screen as a placeholder. Phase 4
# replaces each body with the real content (scout-progress dots, projected-
# comp snapshot card, 7-archetype hidden picker w/ damage previews).
# ---------------------------------------------------------------------------

def _scout_player_names() -> list:
    """Pull the 10 player names (5 per side) out of the server snapshot.
    Returns an empty list if we're not synced or the rosters aren't set."""
    if not _sync_ui.is_active():
        return []
    try:
        from data import draft_sync as _ds
        snap = (_ds.active() or None)
        snap = snap.state() if snap else None
        if not snap:
            return []
        players = (snap.get("state") or {}).get("players") or {}
        out = []
        for side in ("BLUE", "RED"):
            for p in (players.get(side) or [])[:5]:
                nm = (p or {}).get("name", "")
                if nm:
                    out.append(nm)
        return out
    except Exception:
        return []


def _maybe_start_scout_prefetch() -> None:
    """First-time entry into SCOUTING — kick the bulk scout-sheet fetch and
    register a per-player progress callback. Idempotent."""
    if draft.scout_kicked:
        return
    names = _scout_player_names()
    if not names:
        return                        # rosters not yet mirrored
    draft.scout_kicked = True
    draft.scout_total = len(names)
    draft.scout_started_at = time.monotonic()
    # Pre-mark anything already cached (we may have prefetched in TEAM_BUILD).
    try:
        for n in names:
            if n in (getattr(live, "scout_sheets", {}) or {}):
                draft.scout_progress[n] = 1
    except Exception:
        pass

    def _on_progress(name, ok):
        # Callback fires from the fetch worker thread. Dict update is atomic
        # enough; the read-side just polls each frame.
        draft.scout_progress[name] = 1 if ok else 0

    def _on_done(_results):
        # v3.0.4: prefetch_scout_sheets skips names that are already in-flight
        # from a previous call — for those, on_progress NEVER fires for this
        # session. on_done is our backstop: when the bg thread finishes, any
        # name still missing from scout_progress is treated as confirmed-
        # failed (so the phase can advance). Names that DID land in
        # live.scout_sheets are caught at read time by _maybe_send_scout_ready.
        for n in names:
            if n in (getattr(live, "scout_sheets", {}) or {}):
                draft.scout_progress.setdefault(n, 1)
            else:
                draft.scout_progress.setdefault(n, 0)

    try:
        prefetch_scout_sheets(names, on_progress=_on_progress, on_done=_on_done)
    except Exception:
        # Worst case: pretend we're done so the lobby doesn't get stuck.
        for n in names:
            draft.scout_progress[n] = 1


# Safety net: if SCOUTING runs longer than this, advance regardless. Keeps a
# hopelessly-broken fetch from blocking the lobby forever.
_SCOUTING_TIMEOUT_S = 45.0
# When the lobby snapshot has zero player names (sync hiccup, roster not yet
# populated for our side), give it this long before we send ready anyway so
# the draft isn't bricked at "FETCHING SCOUT DATA · 0/1".
_SCOUTING_EMPTY_TIMEOUT_S = 15.0
# Track when SCOUTING was first entered even before prefetch kicks. That's the
# clock the empty-snapshot timeout runs against (scout_started_at is only set
# by _maybe_start_scout_prefetch, which never runs when names is empty).
_scouting_seen_at = [0.0]


def _maybe_send_scout_ready() -> None:
    """When all sheets have settled (success / confirmed-failed / inflight-
    landed-in-scout_sheets), tell the server we're ready to advance.
    Sends at most once per SCOUTING entry.

    v3.0.4: also polls live.scout_sheets directly so names whose fetch was
    skipped due to being in-flight from an earlier call still register as
    settled when their scout sheet lands. 45-second hard timeout as a final
    safety net.

    v4.0.1: when scout_total is still 0 because the synced lobby snapshot has
    no player names yet (the prior early-return), wait up to
    _SCOUTING_EMPTY_TIMEOUT_S and then send ready anyway so the draft can
    advance to BRIEFING — otherwise the lobby is bricked at "0/1 done"."""
    if draft.scout_ready_sent:
        return
    # Track first time we see SCOUTING so the empty-snapshot timeout has a
    # stable starting point.
    if _scouting_seen_at[0] == 0.0:
        _scouting_seen_at[0] = time.monotonic()

    # Empty-snapshot branch — prefetch never kicked because no names.
    if draft.scout_total <= 0:
        elapsed = time.monotonic() - _scouting_seen_at[0]
        if elapsed >= _SCOUTING_EMPTY_TIMEOUT_S:
            draft.scout_ready_sent = True
            _scouting_seen_at[0] = 0.0   # reset for the next SCOUTING entry
            try:
                _sync_ui.send_set_scout_ready(True)
            except Exception:
                pass
        return
    names = _scout_player_names()
    sheets = getattr(live, "scout_sheets", {}) or {}
    # Any name in scout_sheets is success-settled (1). Anything already
    # marked by the on_progress / on_done callbacks is settled too.
    for n in names:
        if n in sheets:
            draft.scout_progress.setdefault(n, 1)
    settled = sum(1 for n in names if n in draft.scout_progress)
    timed_out = (draft.scout_started_at
                 and (time.monotonic() - draft.scout_started_at
                      >= _SCOUTING_TIMEOUT_S))
    if settled >= draft.scout_total or timed_out:
        draft.scout_ready_sent = True
        try:
            _sync_ui.send_set_scout_ready(True)
        except Exception:
            pass


def _draw_scouting(dl, vw, vh):
    """Per-player progress UI for the bulk scout-sheet fetch.
    Each player gets a row with a status dot (gold = fetching, win = done,
    loss = failed). When all dots are green we auto-advance."""
    # Solid navy backdrop + waiting-screen rune
    dpg.draw_rectangle((0, 0), (vw, vh),
                       fill=lol_theme.LOL["navy_deep"],
                       color=(0, 0, 0, 0), parent=dl)

    names = _scout_player_names()
    total = max(1, draft.scout_total or len(names))
    done = sum(1 for v in draft.scout_progress.values() if v >= 1)
    frac = done / total if total else 0.0

    # Reuse the waiting-screen rune as a focal element
    lol_theme.draw_waiting_screen(
        dl, vw, vh,
        status_text="FETCHING SCOUT DATA",
        subtitle=f"pulling ranked + draft pools  ·  {done}/{total} done",
        progress_0_1=frac)

    # ── EXIT button — top-right corner. Always available on the SCOUTING
    # screen so the user can bail back to lobby without killing the app if
    # the draft hangs (sync hiccup, server cold-start, etc.).
    try:
        ex_w, ex_h = 96, 32
        ex_x = vw - ex_w - 18
        ex_y = 18
        mrx, mry = _content_mouse()
        ex_hov = ex_x <= mrx <= ex_x + ex_w and ex_y <= mry <= ex_y + ex_h
        dpg.draw_rectangle((ex_x, ex_y), (ex_x + ex_w, ex_y + ex_h),
                           fill=lol_theme._alpha(
                               lol_theme.LOL.get("loss", (180, 60, 60)),
                               220 if ex_hov else 150),
                           color=lol_theme.LOL["gold_rule"],
                           rounding=4, parent=dl)
        _txt(dl, ex_x + 30, ex_y + 7, "EXIT",
             (255, 255, 255, 240), 16, "raj_sb_16")
        if ex_hov and dpg.is_mouse_button_clicked(0):
            # Disconnect from sync and reset local draft state — mirrors the
            # TEAM_BUILD EXIT handler.
            try:
                _sync_ui.disconnect_if_active()
            except Exception:
                pass
            try:
                _lobby_reset_pool()
            except Exception:
                pass
            try:
                draft.reset()
            except Exception:
                pass
            _scouting_seen_at[0] = 0.0
            return
    except Exception:
        pass

    # Per-player dots panel, anchored below the waiting screen
    if not names:
        # No names means the synced lobby snapshot is empty or our side has
        # no rosters set yet. Tell the user instead of silently spinning, and
        # let _maybe_send_scout_ready time out after _SCOUTING_EMPTY_TIMEOUT_S.
        msg = "Lobby roster not loaded yet — auto-advancing in a few seconds…"
        mx = max(40, (vw - len(msg) * 7) // 2)
        my = vh - 132
        _txt(dl, mx, my, msg,
             (*lol_theme.LOL["txt"][:3], 200), 16, "raj_sb_16")
        # Manual skip — a SKIP button so the user can punt the wait if they
        # know the lobby is intentionally incomplete (testing, etc.).
        bw, bh = 140, 36
        bx = (vw - bw) // 2
        by = my + 36
        try:
            mrx, mry = _content_mouse()
            is_hov = bx <= mrx <= bx + bw and by <= mry <= by + bh
        except Exception:
            is_hov = False
        dpg.draw_rectangle((bx, by), (bx + bw, by + bh),
                           fill=lol_theme._alpha(lol_theme.LOL["gold_rule"],
                                                  220 if is_hov else 160),
                           color=lol_theme.LOL["gold_rule"],
                           rounding=4, parent=dl)
        _txt(dl, bx + 36, by + 10, "SKIP WAIT",
             (255, 255, 255, 240), 15, "raj_sb_16")
        if is_hov and dpg.is_mouse_button_clicked(0):
            draft.scout_ready_sent = True
            _scouting_seen_at[0] = 0.0
            try:
                _sync_ui.send_set_scout_ready(True)
            except Exception:
                pass
        return
    panel_w = min(640, vw - 80)
    panel_x = (vw - panel_w) // 2
    panel_y = vh - 200
    if panel_y < vh // 2 + 80:
        panel_y = vh // 2 + 80
    panel_h = 132
    lol_theme.draw_navy_panel(
        dl, panel_x, panel_y, panel_x + panel_w, panel_y + panel_h,
        fill=lol_theme._alpha(lol_theme.LOL["navy_mid"], 230),
        border_color=lol_theme.LOL["gold_rule"],
        border_thickness=1, rounding=6)
    _txt(dl, panel_x + 16, panel_y + 10, "PLAYER POOLS",
         (*lol_theme.LOL["gold_lt"][:3], 220), 14, "raj_sb_14")

    # Two columns of 5 (BLUE / RED)
    col_w = (panel_w - 32) // 2
    for ci, side in enumerate(("BLUE", "RED")):
        col_x = panel_x + 16 + ci * col_w
        side_col = lol_theme.LOL[
            "blue_side" if side == "BLUE" else "red_side"]
        _txt(dl, col_x, panel_y + 30, side,
             (*side_col[:3], 230), 12, "raj_sb_12")
        # Reach into the snapshot for the per-side names
        try:
            from data import draft_sync as _ds
            snap = (_ds.active() or None)
            snap = snap.state() if snap else None
            side_players = (((snap or {}).get("state") or {})
                            .get("players") or {}).get(side) or []
        except Exception:
            side_players = []
        for i, p in enumerate(side_players[:5]):
            nm = (p or {}).get("name", "")
            ry = panel_y + 50 + i * 16
            dot_status = draft.scout_progress.get(nm, None)
            if dot_status is None:
                dot_col = lol_theme.LOL["gold_rule"]
                dot_label = nm or "—"
            elif dot_status == 1:
                dot_col = lol_theme.LOL["win"]
                dot_label = nm
            else:
                dot_col = lol_theme.LOL["loss"]
                dot_label = nm + " (failed)"
            dpg.draw_circle((col_x + 6, ry + 6), 4,
                            fill=dot_col, color=(0, 0, 0, 0), parent=dl)
            _txt(dl, col_x + 18, ry,
                 dot_label[:24],
                 (*lol_theme.LOL["txt"][:3], 220), 12, "raj_sb_12")


_BRIEFING_TIMEOUT_S = 5.0       # auto-advance after this long
_BRIEFING_MIN_S     = 0.5       # never bail before this (avoids flash)


def _compute_briefing_data() -> dict:
    """Build the projected-comp + key-bans snapshot for the BRIEFING card.
    Engine work runs once per BRIEFING entry — cached on draft.briefing_data
    so we don't recompute every frame."""
    if draft.board is None:
        return {"our_label": "", "our_picks": [], "their_label": "",
                "their_picks": [], "our_bans": [], "their_bans": []}
    try:
        inhouse = getattr(live, "inhouse_champs", {}) or {}
        primary = getattr(live, "primary_roles", {}) or {}
        scout = _scout_champs_for_players(
            list(draft.board.players.get("BLUE", []))
            + list(draft.board.players.get("RED", [])))
    except Exception:
        inhouse, primary, scout = {}, {}, {}
    out = {}
    our_side = draft.board.our_side
    enemy_side = "RED" if our_side == "BLUE" else "BLUE"
    try:
        rec_us = _eng.recommend_comps(
            draft.board.players[our_side], inhouse, primary,
            enemy_picks=[], n_results=1, scout_champs=scout)
    except Exception:
        rec_us = []
    try:
        rec_them = _eng.recommend_comps(
            draft.board.players[enemy_side], inhouse, primary,
            enemy_picks=[], n_results=1, scout_champs=scout)
    except Exception:
        rec_them = []
    if rec_us:
        out["our_label"] = rec_us[0].get("label", "")
        out["our_picks"] = [p.get("champion", "")
                            for p in (rec_us[0].get("picks") or [])][:5]
    else:
        out["our_label"], out["our_picks"] = "", []
    if rec_them:
        out["their_label"] = rec_them[0].get("label", "")
        out["their_picks"] = [p.get("champion", "")
                              for p in (rec_them[0].get("picks") or [])][:5]
    else:
        out["their_label"], out["their_picks"] = "", []
    # Each side's top-3 bans against the OTHER side's roster.
    try:
        names_us, _ = _eng.recommend_bans(
            opposing_players=draft.board.players[enemy_side],
            inhouse_champs=inhouse,
            own_picks=[],
            primary_roles=primary,
            n_bans=3,
            scout_champs=scout)
        out["our_bans"] = list(names_us or [])[:3]
    except Exception:
        out["our_bans"] = []
    try:
        names_them, _ = _eng.recommend_bans(
            opposing_players=draft.board.players[our_side],
            inhouse_champs=inhouse,
            own_picks=[],
            primary_roles=primary,
            n_bans=3,
            scout_champs=scout)
        out["their_bans"] = list(names_them or [])[:3]
    except Exception:
        out["their_bans"] = []
    return out


def _maybe_send_briefing_done() -> None:
    """Auto-advance after 5s. The user can also press CONTINUE manually.
    In solo mode the briefing is a one-shot preview, so the timeout
    returns to IDLE instead of asking the server to advance."""
    if draft.briefing_done_sent:
        return
    elapsed = time.monotonic() - draft.briefing_started_at
    if elapsed >= _BRIEFING_TIMEOUT_S:
        draft.briefing_done_sent = True
        if draft.solo_mode:
            draft.solo_mode = False
            draft.phase = DraftPhase.IDLE
            return
        try:
            _sync_ui.send_set_briefing_done(True)
        except Exception:
            pass


def _draw_briefing(dl, vw, vh):
    """Projected-comps snapshot card + key bans + auto-advance timer."""
    dpg.draw_rectangle((0, 0), (vw, vh),
                       fill=lol_theme.LOL["navy_deep"],
                       color=(0, 0, 0, 0), parent=dl)

    data = draft.briefing_data or _compute_briefing_data()
    if data is not None:
        draft.briefing_data = data

    # Header
    _txt(dl, vw // 2 - 160, 60, "STRATEGIC BRIEFING",
         (*lol_theme.LOL["gold_lt"][:3], 245), 36, "cinzel_36")
    sub = "projected comps  ·  key bans  ·  auto-advance in {:d}s".format(
        max(0, int(_BRIEFING_TIMEOUT_S - (time.monotonic() - draft.briefing_started_at))))
    _txt(dl, vw // 2 - 220, 108, sub,
         (*lol_theme.LOL["txt_dim"][:3], 220), 16, "raj_sb_16")

    # Two side panels: OUR projection (left) + THEIR projection (right)
    panel_y = 160
    panel_h = min(360, vh - panel_y - 140)
    panel_w = min(440, (vw - 80) // 2)
    blue_panel_x = vw // 2 - panel_w - 12
    red_panel_x = vw // 2 + 12

    our_side = (draft.board.our_side if draft.board else "BLUE")
    panels = (
        ("OURS",   blue_panel_x, lol_theme.LOL[
            "blue_side" if our_side == "BLUE" else "red_side"],
         data.get("our_label", ""),
         data.get("our_picks", []),
         data.get("our_bans", [])),
        ("THEIRS", red_panel_x, lol_theme.LOL[
            "red_side" if our_side == "BLUE" else "blue_side"],
         data.get("their_label", ""),
         data.get("their_picks", []),
         data.get("their_bans", [])),
    )
    for title, px, accent, label, picks, bans in panels:
        lol_theme.draw_navy_panel(
            dl, px, panel_y, px + panel_w, panel_y + panel_h,
            fill=lol_theme._alpha(lol_theme.LOL["navy_mid"], 220),
            border_color=accent,
            border_thickness=2, rounding=8)
        _txt(dl, px + 18, panel_y + 12, title,
             (*accent[:3], 245), 18, "raj_sb_18")
        _txt(dl, px + 18, panel_y + 42, label or "(no comp yet)",
             (*lol_theme.LOL["gold_lt"][:3], 235), 22, "raj_sb_22")
        # Projected picks
        _txt(dl, px + 18, panel_y + 80, "Projected picks",
             (*lol_theme.LOL["txt_dim"][:3], 200), 13, "raj_sb_12")
        for i, ch in enumerate(picks[:5]):
            row_y = panel_y + 100 + i * 26
            dpg.draw_rectangle((px + 18, row_y),
                               (px + panel_w - 18, row_y + 22),
                               fill=lol_theme._alpha(
                                   lol_theme.LOL["navy_panel"], 200),
                               color=lol_theme._alpha(accent, 160),
                               thickness=1, rounding=3, parent=dl)
            _txt(dl, px + 26, row_y + 3, ch[:18],
                 (*lol_theme.LOL["txt"][:3], 230), 15, "raj_sb_16")
        # Key bans
        bans_y = panel_y + panel_h - 64
        _txt(dl, px + 18, bans_y, "Key bans",
             (*lol_theme.LOL["txt_dim"][:3], 200), 13, "raj_sb_12")
        bx = px + 18
        for ch in bans[:3]:
            chip_w = max(56, 8 * len(ch) + 16)
            dpg.draw_rectangle((bx, bans_y + 20),
                               (bx + chip_w, bans_y + 44),
                               fill=lol_theme._alpha(
                                   lol_theme.LOL["navy_deep"], 220),
                               color=lol_theme._alpha(
                                   lol_theme.LOL["red_side"], 200),
                               thickness=1, rounding=4, parent=dl)
            _txt(dl, bx + 8, bans_y + 24, ch[:14],
                 (*lol_theme.LOL["red_side"][:3], 235), 13, "raj_sb_12")
            bx += chip_w + 8

    # CONTINUE button (manual skip) + click hit
    btn_w, btn_h = 220, 46
    btn_x = vw // 2 - btn_w // 2
    btn_y = vh - 92
    lol_theme.draw_navy_panel(
        dl, btn_x, btn_y, btn_x + btn_w, btn_y + btn_h,
        fill=lol_theme._alpha(lol_theme.LOL["gold_dk"], 220),
        border_color=lol_theme.LOL["gold"],
        border_thickness=2, rounding=6)
    _txt(dl, btn_x + 64, btn_y + 11, "CONTINUE",
         (*lol_theme.LOL["gold_lt"][:3], 240), 22, "cinzel_24")
    _board_hits.append((btn_x, btn_y, btn_w, btn_h, "briefing_continue", None))


def _archetype_subs(card_data, players, inhouse, primary, scout):
    """v3.0.5: return a list of 5 sub-pick champion names, parallel to the
    archetype's primary 5 picks. Each sub is the player's #2 candidate for
    their assigned role that isn't already the primary pick on this card
    (or on any other role of this card, to keep the comp legal).

    Used by the circular archetype-card layout to render one backup icon
    under each primary champ — "if X is banned, the comp falls back to Y"."""
    if not card_data:
        return []
    primary_picks = [(p.get("champion") or "")
                     for p in (card_data.get("picks") or [])][:5]
    used = {c for c in primary_picks if c}
    subs = []
    for i, p in enumerate(players[:5]):
        primary_champ = primary_picks[i] if i < len(primary_picks) else ""
        role = _ROLES[i] if i < len(_ROLES) else (p.get("role", "") if p else "")
        sub = ""
        # Use the board-layer wrapper that already guards _eng presence and
        # missing-kwarg cases.
        try:
            local_used = set(used)
            if primary_champ:
                local_used.add(primary_champ)
            cands = _candidates_for_player(
                p, role, inhouse, primary, local_used,
                k=6, scout_champs=scout)
        except Exception:
            cands = []
        for cname, _comfort in cands:
            if cname:
                sub = cname
                break
        subs.append(sub)
        if sub:
            used.add(sub)
    return subs


def _draw_archetype_card_circular(dl, cx, cy, card_data, subs, *,
                                  card_w=240, card_h=210,
                                  hot=False, selected=False,
                                  accent_side="BLUE"):
    """v3.0.5: compact archetype card for the circular layout. Lays out the
    primary 5 picks as champion icons (32×32) in a row, with 1 sub icon
    (22×22) directly beneath each, plus label + viability chip + spike."""
    x1 = cx - card_w // 2
    y1 = cy - card_h // 2
    x2 = x1 + card_w
    y2 = y1 + card_h

    # Hover/selected lift
    fill = lol_theme.LOL["navy_lt"] if (selected or hot) else lol_theme.LOL["navy_panel"]
    border_col = (lol_theme.LOL["gold"] if selected else
                  (lol_theme.LOL["gold_lt"] if hot else lol_theme.LOL["gold_rule"]))
    border_thickness = 3 if selected else (2 if hot else 1)
    lol_theme.draw_navy_panel(dl, x1, y1, x2, y2, fill=fill,
                              border_color=border_col,
                              border_thickness=border_thickness, rounding=8)

    # Side-accent stripe along the top
    accent = lol_theme.SIDE_ACCENT.get(accent_side, lol_theme.LOL["gold"])
    dpg.draw_rectangle((x1 + 2, y1 + 2), (x2 - 2, y1 + 6),
                       fill=lol_theme._alpha(accent, 220),
                       color=(0, 0, 0, 0), parent=dl)

    # Archetype label (truncated to fit)
    label = str(card_data.get("label", card_data.get("archetype", "?")))
    _txt(dl, x1 + 12, y1 + 12, label[:22],
         (*lol_theme.LOL["gold_lt"][:3], 240), 16, "raj_sb_16")

    # Viability chip + combined %
    viab = str(card_data.get("viability", ""))
    viab_color_key = lol_theme._VIABILITY_COLORS.get(viab, "gold")
    viab_col = lol_theme.LOL.get(viab_color_key, lol_theme.LOL["gold"])
    combined = card_data.get("combined", 0)
    chip_txt = f"[ {viab} {combined} ]"
    chip_w = len(chip_txt) * 6 + 8
    chip_x = x2 - chip_w - 12
    dpg.draw_rectangle((chip_x, y1 + 14), (chip_x + chip_w, y1 + 34),
                       fill=(*viab_col[:3], 60),
                       color=(*viab_col[:3], 220),
                       thickness=1, rounding=3, parent=dl)
    _txt(dl, chip_x + 5, y1 + 16, chip_txt,
         (*viab_col[:3], 235), 11, "raj_sb_11")

    # 5 champion icons in a row
    primary_picks = (card_data.get("picks") or [])[:5]
    icon_sz = 32
    sub_sz = 22
    row_y = y1 + 50
    sub_y = row_y + icon_sz + 6
    total_w = 5 * icon_sz + 4 * 10
    icon_start_x = x1 + (card_w - total_w) // 2
    for i in range(5):
        ix = icon_start_x + i * (icon_sz + 10)
        # Role label above each icon
        role = _ROLES[i] if i < len(_ROLES) else ""
        if role:
            rc = _ROLE_COLORS.get(role, (180, 180, 180))
            _txt(dl, ix + (icon_sz - len(role) * 6) // 2, row_y - 14,
                 role, (*rc, 220), 11, "raj_sb_11")
        # Primary icon
        primary_champ = (primary_picks[i].get("champion") or "?") if i < len(primary_picks) else "?"
        _draw_portrait(dl, ix, row_y, icon_sz, primary_champ, accent,
                       alpha=240, rounding=4, border_w=2)
        # Sub icon (1 backup, smaller and dimmer)
        sub_champ = subs[i] if i < len(subs) else ""
        sub_x = ix + (icon_sz - sub_sz) // 2
        if sub_champ:
            _draw_portrait(dl, sub_x, sub_y, sub_sz, sub_champ,
                           lol_theme.LOL["gold_rule"], alpha=200,
                           rounding=4, border_w=1)
        else:
            # Empty slot placeholder
            dpg.draw_rectangle((sub_x, sub_y), (sub_x + sub_sz, sub_y + sub_sz),
                               fill=lol_theme._alpha(lol_theme.LOL["navy_deep"], 120),
                               color=lol_theme._alpha(lol_theme.LOL["gold_rule"], 120),
                               thickness=1, rounding=3, parent=dl)
            _txt(dl, sub_x + sub_sz // 2 - 3, sub_y + 4, "?",
                 (*lol_theme.LOL["txt_dim"][:3], 130), 12, "raj_sb_12")

    # Spike / win-condition tagline at the bottom
    spike = str(card_data.get("spike", "")).strip()
    wc = str(card_data.get("win_condition", "")).strip()
    tag = spike or wc
    if tag:
        tag_y = y2 - 24
        _txt(dl, x1 + 12, tag_y, ("→ " + tag)[:34],
             (*lol_theme.LOL["txt_dim"][:3], 215), 11, "raj_sb_11")


def _draw_archetype(dl, vw, vh):
    """v3.0.5: 7-archetype hidden picker — circular formation around an
    animated rune wheel center. Each card shows 5 primary champion icons
    + 1 sub icon per role. Click a card → pending selection; CONFIRM
    locks via set_archetype()."""
    side = _sync_ui.my_side() or "BLUE"
    accent_key = "blue_side" if side == "BLUE" else "red_side"

    # v4.0.3: register any champion icons / splash art that finished downloading
    # since the last frame. Without this, every portrait on this screen stays
    # stuck on the letter-placeholder forever (the textures only get registered
    # on the BOARD screen, which the user hasn't reached yet).
    champion_icons.flush_pending()
    splash_art.flush_pending()

    # ── Backdrop: solid navy + subtle vignette (LoL-client feel) ─────
    dpg.draw_rectangle((0, 0), (vw, vh),
                       fill=lol_theme.LOL["navy_deep"],
                       color=(0, 0, 0, 0), parent=dl)
    # Splash of a featured champion behind the center, dimmed heavily.
    # Try board_rec's top suggestion first (existing behavior); fall back to
    # the hovered or top-archetype's hero champion so the screen always has
    # a thematic splash backdrop instead of flat navy.
    feature_champ = None
    try:
        rec = draft.board_rec or {}
        sg = (rec.get("suggestions") or [{}])[0] or {}
        feature_champ = sg.get("champion") or None
    except Exception:
        feature_champ = None
    if not feature_champ:
        try:
            target_cards = draft.archetype_cards or []
            hovered = draft.archetype_hover or draft.archetype_pending
            chosen = None
            if hovered:
                for c in target_cards:
                    if c.get("archetype") == hovered:
                        chosen = c
                        break
            if chosen is None and target_cards:
                chosen = target_cards[0]
            if chosen:
                picks = (chosen.get("picks") or [])
                if picks:
                    feature_champ = (picks[0] or {}).get("champion")
        except Exception:
            pass
    if feature_champ:
        try:
            sp_tex = splash_art.get_texture(feature_champ)
            if sp_tex:
                # Center the splash, scale to cover, then black-out heavily.
                dpg.draw_image(sp_tex, (0, 60), (vw, vh - 60),
                               uv_min=(0.10, 0.18), uv_max=(0.90, 0.78),
                               parent=dl)
                dpg.draw_rectangle((0, 0), (vw, vh),
                                   fill=lol_theme._alpha(
                                       lol_theme.LOL["navy_deep"], 215),
                                   color=(0, 0, 0, 0), parent=dl)
        except Exception:
            pass
    # Vignette — radial-ish darken at the corners
    vig_layers = 6
    for vi in range(vig_layers):
        va = int(50 * (1 - vi / vig_layers))
        if va <= 0:
            continue
        inset = vi * 14
        dpg.draw_rectangle((inset, inset), (vw - inset, vh - inset),
                           fill=(0, 0, 0, 0),
                           color=(0, 0, 0, va),
                           thickness=2, parent=dl)

    # ── Header ──────────────────────────────────────────────────────
    _txt(dl, vw // 2 - 220, 32, "PICK YOUR ARCHETYPE",
         (*lol_theme.LOL["gold_lt"][:3], 245), 36, "cinzel_36")
    sub = "hidden from your opponent · CONFIRM to lock"
    _txt(dl, vw // 2 - len(sub) * 4, 78, sub,
         (*lol_theme.LOL["txt_dim"][:3], 220), 16, "raj_sb_16")

    # ── Compute viability-sorted cards for OUR roster ───────────────
    # v4.0.2: recompute only when the relevant inputs change (a different
    # roster, switched sides, etc.). Without this the screen makes one
    # blocking server call per frame and stutters badly.
    cards: List[Dict[str, Any]] = []
    sub_picks_per_card: List[List[Any]] = []
    try:
        if draft.board is not None:
            inhouse = getattr(live, "inhouse_champs", {}) or {}
            primary = getattr(live, "primary_roles", {}) or {}
            players = list(draft.board.players.get(side, []))
            roster_sig = tuple((p or {}).get("name", "") for p in players)
            sig = (side, roster_sig, len(inhouse), len(primary))
            if (draft.archetype_cards is not None
                    and draft.archetype_cache_sig == sig):
                cards = draft.archetype_cards
                sub_picks_per_card = draft.archetype_subs or []
            else:
                scout = _scout_champs_for_players(players)
                cards = _eng.recommend_comps(
                    draft.board.players[side], inhouse, primary,
                    enemy_picks=[], n_results=7, scout_champs=scout) or []
                sub_picks_per_card = [
                    _archetype_subs(c, players, inhouse, primary, scout)
                    for c in cards]
                draft.archetype_cards = cards
                draft.archetype_subs = sub_picks_per_card
                draft.archetype_cache_sig = sig
    except Exception:
        cards = draft.archetype_cards or []
        sub_picks_per_card = draft.archetype_subs or []

    # ── Circular layout geometry ────────────────────────────────────
    # Center the ring vertically below the header, leaving room for the
    # CONFIRM button at the bottom.
    ring_cx = vw // 2
    ring_cy = (130 + (vh - 110)) // 2
    # v4.0.2: cards a touch larger and the ring pushed further from center
    # per user feedback — the previous layout felt cramped at the middle.
    card_w = 296 if vw >= 1500 else 272
    card_h = 224 if vw >= 1500 else 210
    n_cards = max(1, len(cards[:7]))
    angular_step = 2 * math.pi / max(n_cards, 1)
    # Wider angular separation requirement = larger ring radius.
    min_sep_w = card_w + 60
    sep_factor = 2.0 * math.sin(angular_step / 2.0)
    needed_r = min_sep_w / sep_factor if sep_factor > 0.05 else 380.0
    # Bound by viewport — the card extents at angle 0 (right) would push
    # past the right edge if needed_r + card_w/2 > vw/2 - 32.
    max_r_w = (vw // 2) - card_w // 2 - 32
    max_r_h = (ring_cy - 120) - card_h // 2 - 8
    max_r = min(max_r_w, max_r_h + (card_h // 4))
    ring_r = max(220.0, min(needed_r, max_r))

    # ── Hover detection BEFORE drawing so card lift / center pulse sync ─
    # (we compute hover for the input handler; the click pick lives there)
    draft.archetype_hover = None
    mx, my = _content_mouse()
    for i, card_data in enumerate(cards[:7]):
        ang = -math.pi / 2 + i * angular_step
        cx_i = ring_cx + ring_r * math.cos(ang)
        cy_i = ring_cy + ring_r * math.sin(ang)
        hx = cx_i - card_w / 2
        hy = cy_i - card_h / 2
        if hx <= mx <= hx + card_w and hy <= my <= hy + card_h:
            draft.archetype_hover = card_data.get("archetype", "")
            break

    # ── Connector lines between center and each card ────────────────
    for i, card_data in enumerate(cards[:7]):
        arch_key = card_data.get("archetype", "")
        ang = -math.pi / 2 + i * angular_step
        cx_i = ring_cx + ring_r * math.cos(ang)
        cy_i = ring_cy + ring_r * math.sin(ang)
        # Pulse the line for the hovered card.
        is_hover = (draft.archetype_hover == arch_key)
        pulse = (math.sin(time.monotonic() * 2.0 * 2 * math.pi) + 1) / 2 if is_hover else 0.0
        line_a = int(60 + 140 * pulse) if is_hover else 50
        # Don't draw the line all the way into the card — stop short.
        # Compute the unit vector from center→card.
        dx = cx_i - ring_cx
        dy = cy_i - ring_cy
        d = math.hypot(dx, dy) or 1.0
        ux, uy = dx / d, dy / d
        l_start = (ring_cx + ux * 80, ring_cy + uy * 80)
        l_end = (cx_i - ux * (card_h / 2 - 4),
                 cy_i - uy * (card_h / 2 - 4))
        dpg.draw_line(l_start, l_end,
                      color=(*lol_theme.LOL["gold_rule"][:3], line_a),
                      thickness=1 + (1 if is_hover else 0),
                      parent=dl)

    # ── Center rune wheel ───────────────────────────────────────────
    _draw_archetype_center_wheel(dl, ring_cx, ring_cy,
                                 cards, draft.archetype_hover or
                                          draft.archetype_pending)

    # ── Draw cards around the ring ──────────────────────────────────
    _archetype_hits = []
    for i, card_data in enumerate(cards[:7]):
        ang = -math.pi / 2 + i * angular_step
        cx_i = int(ring_cx + ring_r * math.cos(ang))
        cy_i = int(ring_cy + ring_r * math.sin(ang))
        arch_key = card_data.get("archetype", "")
        is_pending = (draft.archetype_pending == arch_key)
        is_hover = (draft.archetype_hover == arch_key)
        subs = sub_picks_per_card[i] if i < len(sub_picks_per_card) else []
        _draw_archetype_card_circular(
            dl, cx_i, cy_i, card_data, subs,
            card_w=card_w, card_h=card_h,
            hot=is_hover, selected=is_pending, accent_side=side)
        _archetype_hits.append((cx_i - card_w // 2, cy_i - card_h // 2,
                                card_w, card_h, arch_key))

    # Stash for input handler
    _board_hits.clear()
    for hx, hy, hw, hh, ak in _archetype_hits:
        _board_hits.append((hx, hy, hw, hh, "archetype_pick", ak))

    # ── CONFIRM button (only when something is selected) ────────────
    btn_w, btn_h = 240, 50
    btn_x = vw // 2 - btn_w // 2
    btn_y = vh - 72
    can_confirm = bool(draft.archetype_pending)
    btn_fill = (lol_theme.LOL["gold_dk"] if can_confirm
                else lol_theme._alpha(lol_theme.LOL["navy_panel"], 120))
    btn_border = (lol_theme.LOL["gold"] if can_confirm
                  else lol_theme.LOL["gold_dk"])
    txt_col = (lol_theme.LOL["gold_lt"] if can_confirm
               else lol_theme.LOL["txt_dim"])
    lol_theme.draw_navy_panel(
        dl, btn_x, btn_y, btn_x + btn_w, btn_y + btn_h,
        fill=btn_fill, border_color=btn_border,
        border_thickness=2 if can_confirm else 1, rounding=6)
    label = ("CONFIRM " + draft.archetype_pending) if can_confirm else "CONFIRM"
    _txt(dl, btn_x + (btn_w - len(label) * 12) // 2, btn_y + 13, label,
         (*txt_col[:3], 240 if can_confirm else 140), 22, "cinzel_24")
    if can_confirm:
        _board_hits.append((btn_x, btn_y, btn_w, btn_h,
                             "archetype_confirm", draft.archetype_pending))


def _draw_archetype_center_wheel(dl, cx, cy, cards, focused_arch):
    """v3.0.5: rotating gold rune ring at the center of the circular archetype
    picker, plus a focal readout of the hovered/pending archetype in the
    middle (label + viability + spike). Focal-motion only (rune rotates,
    inner text pulses gently)."""
    # Rotating rune dashes
    t = time.monotonic()
    n_dashes = 24
    inner_r = 56
    outer_r = 72
    base_angle = (t / 8.0) * 2 * math.pi    # slow rotation, ~8s/rev
    for i in range(n_dashes):
        a = base_angle + (2 * math.pi * i / n_dashes)
        cosA, sinA = math.cos(a), math.sin(a)
        x1 = cx + inner_r * cosA
        y1 = cy + inner_r * sinA
        x2 = cx + outer_r * cosA
        y2 = cy + outer_r * sinA
        fade = i / max(n_dashes - 1, 1)
        alpha = int(70 + 170 * (1.0 - fade))
        gold = lol_theme.LOL["gold"]
        col = (gold[0], gold[1], gold[2], alpha)
        dpg.draw_line((x1, y1), (x2, y2),
                      color=col, thickness=2, parent=dl)
    # Inner ring (counter-rotating dim arc)
    base_angle2 = -(t / 12.0) * 2 * math.pi
    inner2_r = 44
    outer2_r = 50
    for i in range(36):
        a = base_angle2 + (2 * math.pi * i / 36)
        cosA, sinA = math.cos(a), math.sin(a)
        x1 = cx + inner2_r * cosA
        y1 = cy + inner2_r * sinA
        x2 = cx + outer2_r * cosA
        y2 = cy + outer2_r * sinA
        dpg.draw_line((x1, y1), (x2, y2),
                      color=(*lol_theme.LOL["gold_dk"][:3], 160),
                      thickness=1, parent=dl)
    # Outer ring
    ring_pts = []
    n_ring = 64
    for i in range(n_ring):
        a = 2 * math.pi * i / n_ring
        ring_pts.append((cx + (outer_r + 6) * math.cos(a),
                         cy + (outer_r + 6) * math.sin(a)))
    for i in range(len(ring_pts)):
        a, b = ring_pts[i], ring_pts[(i + 1) % len(ring_pts)]
        dpg.draw_line(a, b, color=lol_theme._alpha(lol_theme.LOL["gold_rule"], 180),
                      thickness=1, parent=dl)
    # Inner ring
    inner_ring_pts = []
    for i in range(n_ring):
        a = 2 * math.pi * i / n_ring
        inner_ring_pts.append((cx + (inner_r - 4) * math.cos(a),
                               cy + (inner_r - 4) * math.sin(a)))
    for i in range(len(inner_ring_pts)):
        a, b = inner_ring_pts[i], inner_ring_pts[(i + 1) % len(inner_ring_pts)]
        dpg.draw_line(a, b, color=lol_theme._alpha(lol_theme.LOL["gold_rule"], 200),
                      thickness=1, parent=dl)

    # Find focused card data (by archetype key)
    focused_data = None
    if focused_arch:
        for c in cards:
            if c.get("archetype") == focused_arch:
                focused_data = c
                break

    # Inner panel — text readout for the focused archetype.
    pulse = (math.sin(time.monotonic() * 1.6 * 2 * math.pi) + 1) / 2
    if focused_data:
        label = str(focused_data.get("label", focused_data.get("archetype", "")))
        viab = str(focused_data.get("viability", ""))
        combined = focused_data.get("combined", 0)
        spike = str(focused_data.get("spike", "") or
                    focused_data.get("win_condition", ""))[:32]
        # Title
        title = label.split("(")[0].strip()  # drop the "(AoE + Engage)" suffix
        title_w = len(title) * 7
        _txt(dl, cx - title_w // 2, cy - 18, title[:18],
             (*lol_theme.LOL["gold_lt"][:3], int(220 + pulse * 35)),
             16, "raj_sb_16")
        # Viability + score, second line
        line2 = f"{viab}  {combined}"
        l2_w = len(line2) * 5
        viab_color_key = lol_theme._VIABILITY_COLORS.get(viab, "gold")
        viab_col = lol_theme.LOL.get(viab_color_key, lol_theme.LOL["gold"])
        _txt(dl, cx - l2_w // 2, cy + 4, line2,
             (*viab_col[:3], 230), 12, "raj_sb_12")
        # Spike, third line (dim)
        if spike:
            sp_w = len(spike) * 4
            _txt(dl, cx - sp_w // 2, cy + 22, spike,
                 (*lol_theme.LOL["txt_dim"][:3], 210),
                 10, "raj_sb_11")
    else:
        # Idle state — generic hint, pulsing
        msg = "HOVER A CARD"
        mw = len(msg) * 7
        _txt(dl, cx - mw // 2, cy - 8, msg,
             (*lol_theme.LOL["gold_lt"][:3], int(150 + pulse * 100)),
             14, "raj_sb_14")


def _draw_enemy_ghost_chip(dl, b):
    """Overlay the predict_enemy_next_pick result on the matching enemy
    slot rect. Renders nothing if there's no next enemy pick or the
    matching slot already has a locked champion."""
    if b is None or not hasattr(b, "our_side"):
        return
    enemy_side = "RED" if b.our_side == "BLUE" else "BLUE"
    try:
        from data.draft_board import predict_enemy_next_pick as _pen
        inhouse = getattr(live, "inhouse_champs", {}) or {}
        primary = getattr(live, "primary_roles", {}) or {}
        scout = _scout_champs_for_players(
            list(b.players.get("BLUE", [])) + list(b.players.get("RED", [])))
        pred = _pen(b, inhouse, primary, scout)
    except Exception:
        pred = None
    if not pred:
        return
    pred_role = (pred.get("role") or "").upper()
    pred_champ = pred.get("champion") or ""
    if not pred_role or not pred_champ:
        return
    # Find the enemy slot rect for that role; only render if it's empty.
    for (rx, ry_, rw, rh, side, role, champ) in _pick_slot_rects:
        if side == enemy_side and role == pred_role and not champ:
            chip_w = min(rw - 12, 200)
            chip_x = rx + (rw - chip_w) // 2
            chip_y = ry_ + (rh - 56) // 2
            lol_theme.draw_ghost_suggestion_chip(
                dl, chip_x, chip_y, chip_x + chip_w, chip_y + 56,
                pred_champ, pred_role,
                float(pred.get("confidence", 0.35)),
                side=enemy_side)
            return


def _bans_retrospective(b):
    """Build the "what got banned" panel data. For each side, returns
    {"BLUE": {ROLE: [(champ, banned_by_enemy, was_top_proj)], ...},
     "RED":  ...}.

    We re-run recommend_comps per side (no enemy locks, n_results=1) to
    get the projected top-pick per role, then compare each projection
    against the OTHER side's actual ban list to flag what the enemy
    removed.
    """
    if b is None:
        return {}
    out = {}
    try:
        inhouse = getattr(live, "inhouse_champs", {}) or {}
        primary = getattr(live, "primary_roles", {}) or {}
        scout = _scout_champs_for_players(
            list(b.players.get("BLUE", []))
            + list(b.players.get("RED", [])))
    except Exception:
        inhouse, primary, scout = {}, {}, {}
    enemy_bans = {
        "BLUE": set(b.bans.get("RED", []) or []),
        "RED":  set(b.bans.get("BLUE", []) or []),
    }
    for side in ("BLUE", "RED"):
        try:
            comps = _eng.recommend_comps(
                b.players[side], inhouse, primary,
                enemy_picks=[], n_results=1, scout_champs=scout) or []
        except Exception:
            comps = []
        per_role = {}
        if comps:
            for p in (comps[0].get("picks") or []):
                champ = p.get("champion") or ""
                role = (p.get("role") or "").upper()
                if not champ or not role or role in per_role:
                    continue
                per_role[role] = (champ, champ in enemy_bans[side])
        out[side] = per_role
    return out


def _draw_done_summary(dl, x, y, w, h, b, interactive):
    """Phase 5 DONE-screen polish. Lays out four stacked panels inside
    the center column:

      1. DRAFT COMPLETE banner
      2. Win-prob progression sparkline (board_rail._cache["history"])
      3. Per-side game-plan cards (ARCHETYPES[arch]["game_plan"])
      4. "What got banned" retrospective (projected picks vs enemy bans)
      5. NEW DRAFT button
    """
    # Header
    _txt(dl, x + 24, y + 18, "DRAFT COMPLETE",
         (*lol_theme.LOL["gold_lt"][:3], 245), 28, "cinzel_28")
    _txt(dl, x + 24, y + 56,
         "Both archetypes revealed — review the recap below",
         (*lol_theme.LOL["txt_dim"][:3], 220), 14, "raj_sb_14")
    lol_theme.draw_gold_rule(dl, x + 14, y + 86, x + w - 14, y + 86,
                             thickness=1, alpha=200)

    # Win-prob progression sparkline (uses the cached history from board_rail)
    chart_y = y + 100
    chart_h = 64
    chart_x1 = x + 14
    chart_x2 = x + w - 14
    chart_w = chart_x2 - chart_x1
    lol_theme.draw_navy_panel(
        dl, chart_x1, chart_y, chart_x2, chart_y + chart_h,
        fill=lol_theme._alpha(lol_theme.LOL["navy_panel"], 200),
        border_color=lol_theme.LOL["gold_rule"],
        border_thickness=1, rounding=4)
    _txt(dl, chart_x1 + 10, chart_y + 6, "WIN-PROBABILITY · BLUE",
         (*lol_theme.LOL["gold_lt"][:3], 220), 12, "raj_sb_12")
    try:
        hist = list(board_rail._cache.get("history") or [])
    except Exception:
        hist = []
    if len(hist) >= 2:
        # 50% baseline
        mid_y = chart_y + 24 + (chart_h - 28) // 2
        dpg.draw_line((chart_x1 + 10, mid_y), (chart_x2 - 10, mid_y),
                      color=(*lol_theme.LOL["gold_rule"][:3], 110),
                      thickness=1, parent=dl)
        n = len(hist)
        step = (chart_w - 20) / max(1, n - 1)
        plot_top = chart_y + 24
        plot_h = chart_h - 30
        pts = [(chart_x1 + 10 + i * step,
                plot_top + plot_h - max(0.0, min(1.0, hist[i])) * plot_h)
               for i in range(n)]
        # Side-tinted polyline (blue if final WP>=0.5, red otherwise)
        line_col = (lol_theme.LOL["blue_side"]
                    if hist[-1] >= 0.5 else lol_theme.LOL["red_side"])
        for i in range(n - 1):
            dpg.draw_line(pts[i], pts[i + 1],
                          color=(*line_col[:3], 230),
                          thickness=2, parent=dl)
        final_pct = int(round(hist[-1] * 100))
        _txt(dl, chart_x2 - 70, chart_y + 6,
             f"FINAL {final_pct}%",
             (*line_col[:3], 240), 12, "raj_sb_12")
    else:
        _txt(dl, chart_x1 + 14, chart_y + 28,
             "no history captured this game",
             (*lol_theme.LOL["txt_dim"][:3], 180), 13, "raj_sb_12")

    # Per-side game-plan cards
    gp_y = chart_y + chart_h + 12
    gp_h = 140
    half_w = (w - 36) // 2
    blue_x1 = x + 14
    red_x1 = x + 14 + half_w + 8
    archetypes = getattr(_eng, "ARCHETYPES", {}) or {}
    for side_label, side, px1, side_col in (
        ("BLUE COMP", "BLUE", blue_x1, lol_theme.LOL["blue_side"]),
        ("RED COMP",  "RED",  red_x1,  lol_theme.LOL["red_side"]),
    ):
        # Try to read the locked archetype from the synced snapshot — the
        # server reveals BOTH sides at DONE, so even the spectators see them.
        arch_label = ""
        gp = ""
        try:
            if _sync_ui.is_active():
                from data import draft_sync as _ds
                snap = (_ds.active() or None)
                snap = snap.state() if snap else None
                if snap:
                    sst = snap.get("state") or {}
                    if side == (b.our_side if b is not None else "BLUE"):
                        arch_label = sst.get("archetype_self") or ""
                    else:
                        arch_label = sst.get("archetype_enemy") or ""
        except Exception:
            arch_label = ""
        if not arch_label and side == (b.our_side if b is not None else "BLUE"):
            arch_label = draft.board_target_arch or ""
        ad = archetypes.get(arch_label, {}) if arch_label else {}
        title = ad.get("label", arch_label or "(no archetype)")
        gp = (ad.get("game_plan") or "").strip()
        lol_theme.draw_navy_panel(
            dl, px1, gp_y, px1 + half_w, gp_y + gp_h,
            fill=lol_theme._alpha(lol_theme.LOL["navy_panel"], 220),
            border_color=side_col,
            border_thickness=2, rounding=6)
        _txt(dl, px1 + 10, gp_y + 8, side_label,
             (*side_col[:3], 240), 14, "raj_sb_14")
        _txt(dl, px1 + 10, gp_y + 30, title[:32],
             (*lol_theme.LOL["gold_lt"][:3], 235), 18, "raj_sb_18")
        # Wrap the game plan across ~3 lines.
        line_max = max(30, (half_w - 28) // 7)
        words = gp.split()
        lines, cur = [], ""
        for word in words:
            cand = (cur + " " + word).strip()
            if len(cand) <= line_max:
                cur = cand
            else:
                if cur:
                    lines.append(cur)
                cur = word
            if len(lines) >= 4:
                break
        if cur and len(lines) < 4:
            lines.append(cur)
        for i, ln in enumerate(lines[:4]):
            _txt(dl, px1 + 10, gp_y + 58 + i * 18, ln,
                 (*lol_theme.LOL["txt"][:3], 225), 13, "raj_sb_12")

    # "What got banned" retrospective panel
    bans_y = gp_y + gp_h + 12
    bans_h = max(70, y + h - 80 - bans_y)
    if bans_h >= 50:
        bans_x1 = x + 14
        bans_x2 = x + w - 14
        lol_theme.draw_navy_panel(
            dl, bans_x1, bans_y, bans_x2, bans_y + bans_h,
            fill=lol_theme._alpha(lol_theme.LOL["navy_panel"], 200),
            border_color=lol_theme.LOL["gold_rule"],
            border_thickness=1, rounding=4)
        _txt(dl, bans_x1 + 10, bans_y + 6, "WHAT GOT BANNED",
             (*lol_theme.LOL["gold_lt"][:3], 220), 12, "raj_sb_12")
        retro = _bans_retrospective(b)
        # Two columns: BLUE projected picks vs RED bans, and vice versa.
        col_w = (bans_x2 - bans_x1 - 24) // 2
        col_y = bans_y + 28
        for ci, side in enumerate(("BLUE", "RED")):
            cx_ = bans_x1 + 12 + ci * (col_w + 8)
            side_col = lol_theme.LOL[
                "blue_side" if side == "BLUE" else "red_side"]
            _txt(dl, cx_, col_y, f"{side} projected picks",
                 (*side_col[:3], 220), 12, "raj_sb_12")
            per_role = retro.get(side, {})
            ry = col_y + 18
            for role in _ROLES:
                entry = per_role.get(role)
                if not entry:
                    continue
                champ, banned = entry
                # Status dot
                dot_col = (lol_theme.LOL["loss"]
                           if banned else lol_theme.LOL["win"])
                dpg.draw_circle((cx_ + 5, ry + 8), 4,
                                fill=dot_col, color=(0, 0, 0, 0),
                                parent=dl)
                role_x = cx_ + 16
                _txt(dl, role_x, ry, role,
                     (*_ROLE_COLORS.get(role, (180, 180, 180)), 230),
                     12, "raj_sb_12")
                _txt(dl, role_x + 40, ry, champ[:14],
                     (*lol_theme.LOL["txt"][:3], 225),
                     13, "raj_sb_13" if "raj_sb_13" in _F else "raj_sb_12")
                if banned:
                    _txt(dl, role_x + 130, ry, "BANNED",
                         (*lol_theme.LOL["loss"][:3], 230),
                         11, "raj_sb_11")
                ry += 16
                if ry + 16 > bans_y + bans_h - 6:
                    break

    # NEW DRAFT button (centered at bottom)
    nb_w, nb_h = 220, 46
    nbx = x + w // 2 - nb_w // 2
    nby = y + h - nb_h - 14
    nb_hov = interactive and _hover(nbx, nby, nb_w, nb_h)
    lol_theme.draw_navy_panel(
        dl, nbx, nby, nbx + nb_w, nby + nb_h,
        fill=lol_theme._alpha(lol_theme.LOL["gold_dk"],
                              230 if nb_hov else 200),
        border_color=lol_theme.LOL["gold"],
        border_thickness=2, rounding=6)
    _txt(dl, nbx + 52, nby + 12, "NEW DRAFT",
         (*lol_theme.LOL["gold_lt"][:3], 245), 22, "cinzel_24")
    _board_hits.append((nbx, nby, nb_w, nb_h, "new", None))


def _compute_pivot_alert(b):
    """Run draft_board.archetype_pivot_check when the locked archetype or
    board signature changes. Cached on `draft._pivot_alert` between frames
    so we don't redo the engine work on every redraw."""
    # Identify the locked archetype — prefer the server's hidden-per-side
    # value, falling back to the local team-builder's choice.
    arch = draft.board_target_arch
    if _sync_ui.is_active():
        try:
            from data import draft_sync as _ds
            snap = (_ds.active() or None)
            snap = snap.state() if snap else None
            if snap:
                a_self = ((snap.get("state") or {}).get("archetype_self"))
                if a_self:
                    arch = a_self
        except Exception:
            pass
    if not arch:
        draft._pivot_alert = None
        return
    if b is None or not hasattr(b, "our_side"):
        draft._pivot_alert = None
        return
    # Signature: archetype + every locked pick/ban + pointer. Pivot check
    # depends only on board state + arch.
    sig = (arch, b.pointer,
           tuple(sorted(b.picks.get("BLUE", {}).items())),
           tuple(sorted(b.picks.get("RED", {}).items())),
           tuple(b.bans.get("BLUE", [])),
           tuple(b.bans.get("RED", [])))
    if sig == draft._pivot_last_sig:
        return
    draft._pivot_last_sig = sig
    was_wrecked = bool(draft._pivot_alert and draft._pivot_alert.get("wrecked"))
    try:
        from data.draft_board import archetype_pivot_check as _piv
        inhouse = getattr(live, "inhouse_champs", {}) or {}
        primary = getattr(live, "primary_roles", {}) or {}
        scout = _scout_champs_for_players(
            list(b.players.get("BLUE", [])) + list(b.players.get("RED", [])))
        info = _piv(b, b.our_side, arch, inhouse, primary, scout)
        if isinstance(info, dict):
            info["archetype"] = arch
            info["archetype_label"] = arch
        draft._pivot_alert = info
    except Exception:
        draft._pivot_alert = None
    # Fire the pivot-alert audio sting once on the rising edge (a brand-new
    # wreck), not every redraw while the banner is showing.
    now_wrecked = bool(draft._pivot_alert and draft._pivot_alert.get("wrecked"))
    if now_wrecked and not was_wrecked:
        try:
            _audio.play_pivot()
        except Exception:
            pass


def _draw_board(dl, vw, vh):
    # Sync mirror first: if a session is active, fold the latest server
    # snapshot into draft.board before we render. Recompute the recommender
    # whenever a new revision lands so the suggestions follow remote actions.
    _prev_pointer = draft.board.pointer if draft.board is not None else -1
    _sync_ui.sync_tick(draft)
    needs_recompute = (draft.board is not None
                       and draft.board.pointer != _prev_pointer)

    # v3.0.5: also recompute when async scout / inhouse data lands. Without
    # this, _board_recompute() fired only at board-entry — before
    # prefetch_scout_sheets() had a chance to populate live.scout_sheets —
    # so the very first ban's TOP CALL panel rendered empty (no suggestions)
    # until the user manually advanced. We snapshot a coarse data signature
    # (#scout sheets, #inhouse-champ entries, live.loaded flag) per frame
    # and retrigger when it grows. Cheap: just length lookups, no copying.
    if draft.board is not None:
        try:
            data_sig = (len(getattr(live, "scout_sheets", {}) or {}),
                        len(getattr(live, "inhouse_champs", {}) or {}),
                        bool(getattr(live, "loaded", False)))
        except Exception:
            data_sig = None
        if data_sig != draft._board_data_sig:
            draft._board_data_sig = data_sig
            # Only retrigger when we have an empty/missing suggestion list —
            # don't trample the engine result with a re-run after the user
            # has already seen a useful recommendation (cheap optimisation).
            cur_rec = draft.board_rec or {}
            cur_sug = cur_rec.get("suggestions") or []
            if not cur_sug:
                needs_recompute = True

    if needs_recompute:
        _board_recompute()

    # If we're in a synced session whose host hasn't pressed START yet,
    # render the lobby instead of the pick/ban board. The board state still
    # mirrors in the background so the moment START fires we have everything
    # we need to render the real board on the next frame.
    if _sync_ui.in_lobby():
        _board_hits.clear()
        _draw_sync_lobby(dl, vw, vh)
        return

    _board_hits.clear()
    _pick_slot_rects.clear()
    champion_icons.flush_pending()          # register any downloaded icons
    splash_art.flush_pending()              # register any downloaded splashes
    # Lock the parent content window's vertical scroll — the board is a fixed
    # full-viewport layout, and any wheel-scroll should hit only the manual
    # pool grid, never the outer window.
    if dpg.does_item_exist("content_win"):
        dpg.set_y_scroll("content_win", 0)
    global _mouse_xy
    _mouse_xy = _content_mouse()
    b = draft.board
    if b is None:
        draft.phase = DraftPhase.IDLE
        return
    # Solid navy backdrop — no grid drift (per ambient-motion feedback).
    dpg.draw_rectangle((0, 0), (vw, vh),
                       fill=lol_theme.LOL["navy_deep"],
                       color=(0, 0, 0, 0), parent=dl)

    # §7.5 — Layout A needs room for the right rail; refuse below 1280x720.
    if vw < 1280 or vh < 720:
        _txt(dl, vw // 2 - 230, vh // 2 - 16,
             "RESIZE VIEWPORT TO AT LEAST 1280 x 720",
             (*lol_theme.LOL["warning"][:3], 235), 18, "raj_sb_18")
        return
    rec = draft.board_rec or {}
    act = rec.get("action")
    our = b.our_side
    # Phase 6: LCU live-import path was deleted. Board is always manual /
    # sync-mirrored from this point on; this constant keeps the body's
    # `interactive` plumbing readable.
    live_connected = False

    # Phase 5 audio — fire turn chime once when the current action's side
    # becomes ours. action.idx changes monotonically so we just remember the
    # idx of the last fired cue to avoid re-firing on every frame.
    if act is not None and act.side == our and act.idx != draft._audio_last_actor_idx:
        draft._audio_last_actor_idx = act.idx
        try:
            _audio.play_turn()
        except Exception:
            pass

    # ── Header ───────────────────────────────────────────────────────
    hdr_h = 54
    dpg.draw_rectangle((0, 0), (vw, hdr_h),
                       fill=lol_theme.LOL["navy_mid"],
                       color=(0, 0, 0, 0), parent=dl)
    lol_theme.draw_gold_rule(dl, 0, hdr_h - 1, vw, hdr_h - 1,
                             thickness=1, alpha=220)
    _txt(dl, 24, 14, "DRAFT BOARD",
         (*lol_theme.LOL["gold_lt"][:3], 245), 26, "cinzel_24")
    if _sync_ui.is_active():
        ptxt = _sync_ui.presence_text() or "SYNCED"
        _txt(dl, 320, 18, ptxt[:80],
             (*lol_theme.LOL["win"][:3], 230), 16, "raj_sb_16")
    else:
        _txt(dl, 320, 18, "MANUAL",
             (*lol_theme.LOL["txt_dim"][:3], 200), 16, "raj_sb_16")
    side_col = _side_accent(our, lt=True)
    _txt(dl, vw - 340, 18, f"YOU: {our}", (*side_col, 240), 16, "raj_sb_16")

    # UNDO (manual only — in live the client is authoritative) + EXIT
    if not live_connected:
        ub_w, ub_h = 100, 38
        ub_x = vw - ub_w - 124
        ub_y = (hdr_h - ub_h) // 2
        can_undo = bool(b._history)
        lol_theme.draw_navy_panel(
            dl, ub_x, ub_y, ub_x + ub_w, ub_y + ub_h,
            fill=lol_theme._alpha(lol_theme.LOL["navy_panel"],
                                  185 if can_undo else 70),
            border_color=(lol_theme.LOL["gold"] if can_undo
                          else lol_theme.LOL["gold_dk"]),
            border_thickness=1, rounding=4)
        _txt(dl, ub_x + 22, ub_y + 9, "UNDO",
             (*lol_theme.LOL["gold_lt"][:3], 235 if can_undo else 95),
             18, "raj_sb_18")
        if can_undo:
            _board_hits.append((ub_x, ub_y, ub_w, ub_h, "undo", None))
    cb_w, cb_h = 100, 38
    cb_x = vw - cb_w - 14
    cb_y = (hdr_h - cb_h) // 2
    lol_theme.draw_navy_panel(
        dl, cb_x, cb_y, cb_x + cb_w, cb_y + cb_h,
        fill=lol_theme._alpha(lol_theme.LOL["navy_panel"], 170),
        border_color=lol_theme.LOL["red_side"],
        border_thickness=1, rounding=4)
    _txt(dl, cb_x + 28, cb_y + 9, "EXIT",
         (*lol_theme.LOL["red_side"][:3], 235), 18, "raj_sb_18")
    _board_hits.append((cb_x, cb_y, cb_w, cb_h, "exit", None))

    # ── Timeline strip (20 actions) ──────────────────────────────────
    tl_y = hdr_h + 10
    phase_h = 24
    cells_h = 64
    tl_h    = phase_h + cells_h
    cells_y = tl_y + phase_h
    cell_w  = (vw - 32) / 20.0

    # Phase header band: BANS 1 · PICKS 1 · BANS 2 · PICKS 2
    PHASE_LABEL_COLOR = (*lol_theme.LOL["gold_lt"][:3], 220)
    PHASE_DIV_COLOR   = (*lol_theme.LOL["gold_rule"][:3], 220)
    phase_spans = (("BANS 1", 0, 6), ("PICKS 1", 6, 12),
                   ("BANS 2", 12, 16), ("PICKS 2", 16, 20))
    for label, start, end in phase_spans:
        cx_lo = 16 + start * cell_w
        cx_hi = 16 + end   * cell_w
        lbl_w = len(label) * 9
        lx    = cx_lo + ((cx_hi - cx_lo) - lbl_w) // 2
        _txt(dl, lx, tl_y + 4, label, PHASE_LABEL_COLOR, 14, "raj_sb_14")
    # Gold vertical dividers between phases (after action 6, 12, 16)
    for boundary in (6, 12, 16):
        bx = int(16 + boundary * cell_w)
        dpg.draw_line((bx, tl_y), (bx, cells_y + cells_h),
                      color=PHASE_DIV_COLOR, thickness=2, parent=dl)
    # Outer baseline under the whole timeline
    lol_theme.draw_gold_rule(dl, 16, cells_y + cells_h,
                             int(16 + 20 * cell_w), cells_y + cells_h,
                             thickness=1, alpha=210)

    # Detect a fresh lock and start the cell-pop animation.
    if b.pointer != draft._board_last_pointer:
        if b.pointer > draft._board_last_pointer:
            draft._board_lock_pop_idx  = b.pointer - 1
            draft._board_lock_pop_anim = 0.0
            def _set_pop(v):
                draft._board_lock_pop_anim = v
            # out_cubic instead of out_back — rapid back-to-back locks no
            # longer feel chaotic with overshoot.
            anim.tween(0.0, 1.0, 260, "out_cubic", on_update=_set_pop)
            # Phase 5 audio cue — pick or ban thunk fires once per lock.
            try:
                last_kind = DRAFT_SEQUENCE[b.pointer - 1].kind
                if last_kind == "pick":
                    _audio.play_lock()
                else:
                    _audio.play_ban()
                # Final action of the draft → outro flourish.
                if b.pointer >= len(DRAFT_SEQUENCE):
                    _audio.play_draft_end()
            except Exception:
                pass
        draft._board_last_pointer = b.pointer

    for a in DRAFT_SEQUENCE:
        cx0 = 16 + a.idx * cell_w
        is_cur = (act is not None and a.idx == act.idx)
        done = a.idx < b.pointer
        side_c  = _side_accent(a.side)
        side_lt = _side_accent(a.side, lt=True)
        if is_cur:
            # Focal pulse on the on-the-clock cell (allowed per ambient_motion).
            pulse = (math.sin(time.monotonic() * 1.6 * 2 * math.pi) + 1) / 2
            fill_a = int(70 + pulse * 90)
        elif done:
            fill_a = 60
        else:
            fill_a = 22
        # Pop highlight: just-locked cell briefly glows brighter
        is_pop = (a.idx == draft._board_lock_pop_idx
                  and draft._board_lock_pop_anim < 1.0)
        if is_pop:
            pop_t = draft._board_lock_pop_anim
            # bright glow that decays to normal as anim completes
            fill_a = max(fill_a, int(180 * (1 - pop_t) + 60))
            border_alpha = max(80, int(255 * (1 - pop_t) + 80))
            border_thick = 3 if pop_t < 0.5 else 2
        else:
            border_alpha = 210 if is_cur else 80
            border_thick = 2 if is_cur else 1
        # Focal glow halo behind the on-the-clock cell (per-cell, not background)
        if is_cur:
            gp = (math.sin(time.monotonic() * 1.6 * 2 * math.pi + 0.35) + 1) / 2
            for gi in range(6):
                ga = int(110 * (1 - gi / 6) * gp)
                if ga <= 0:
                    continue
                dpg.draw_rectangle((cx0 + 1 - gi, cells_y - gi),
                                   (cx0 + cell_w - 1 + gi,
                                    cells_y + cells_h + gi),
                                   fill=(0, 0, 0, 0),
                                   color=(*side_lt, ga),
                                   thickness=1, rounding=4, parent=dl)
        dpg.draw_rectangle((cx0 + 1, cells_y),
                           (cx0 + cell_w - 1, cells_y + cells_h),
                           fill=(*side_c, fill_a),
                           color=(*side_c, border_alpha),
                           thickness=border_thick,
                           rounding=4, parent=dl)
        if is_cur:
            # Thicker border accent for the on-the-clock cell (no marching dash)
            dpg.draw_rectangle((cx0 + 1, cells_y),
                               (cx0 + cell_w - 1, cells_y + cells_h),
                               fill=(0, 0, 0, 0),
                               color=(*side_lt, 235),
                               thickness=2, rounding=4, parent=dl)
        kind_c = (side_lt if a.kind == "pick"
                  else lol_theme.LOL["red_side"][:3])
        side_letter = "B" if a.side == "BLUE" else "R"
        label_str = f"{side_letter} {a.kind.upper()}"
        _txt(dl, cx0 + 6, cells_y + 6, label_str,
             (*kind_c, 230 if (is_cur or done) else 140), 14, "raj_sb_14")
        locked = b.locked_at(a.idx)         # exact (from history)
        if locked:
            # Pop scale on the locked text — bigger size early in the anim
            if is_pop:
                pt = draft._board_lock_pop_anim
                # ease size from 24 down to baseline 18
                lock_sz = max(18, int(24 - 6 * pt))
            else:
                lock_sz = 18
            _txt(dl, cx0 + 6, cells_y + 34, locked[:8],
                 (*lol_theme.LOL["txt"][:3], 230), lock_sz, "raj_sb_18")
            # Side-tinted underline beneath the locked champion name
            ul_w = min(int(cell_w) - 12, len(locked[:8]) * (lock_sz // 2 + 2))
            dpg.draw_line((cx0 + 6, cells_y + 34 + lock_sz + 2),
                          (cx0 + 6 + ul_w, cells_y + 34 + lock_sz + 2),
                          color=(*side_lt, 170), thickness=1, parent=dl)

    # §3 #27 — action-queue preview in the header (wide viewports only)
    if vw >= 1500:
        try:
            board_rail.draw_action_queue(dl, 470, 18, vw - 820, b, _txt,
                                         DRAFT_SEQUENCE)
        except Exception:
            pass

    # ── Pivot-alert banner (Phase 4): runs the engine pivot check when the
    # user has a locked archetype, and slides a warning in below the timeline
    # if their comp got wrecked by recent enemy bans.
    _compute_pivot_alert(b)
    pivot_banner_h = 0
    if draft._pivot_alert and draft._pivot_alert.get("wrecked"):
        pivot_banner_h = 60
        bx0 = 16
        by0 = tl_y + tl_h + 6
        info = draft._pivot_alert
        arch_name = info.get("archetype_label") or info.get("archetype") or "Archetype"
        rects = lol_theme.draw_pivot_alert_banner(
            dl, bx0, by0, vw - 16, by0 + pivot_banner_h,
            archetype_name=arch_name,
            reason=info.get("reason", ""),
            pivot_options=info.get("pivot_options") or [],
            severity=float(info.get("severity", 0.8)))
        draft._pivot_btn_rects = rects
        # Register hits so the click handler can fire pivot transitions.
        for rx1, ry1, rx2, ry2, opt in rects:
            _board_hits.append((rx1, ry1, rx2 - rx1, ry2 - ry1,
                                 "pivot_to", opt))

    # ── Layout A: stacked team column · center · right analytics rail ─
    body_y = tl_y + tl_h + 14 + pivot_banner_h
    narr_h = 26
    narr_y = vh - narr_h - 8
    if vw <= 1300:
        col_w, rail_w = 178, 220
    else:
        col_w, rail_w = 200, 300
    gap    = 14
    left_x = 16
    rail_x = vw - 16 - rail_w
    cen_x  = left_x + col_w + gap
    cen_w  = rail_x - gap - cen_x
    body_h = (narr_y - 10) - body_y
    team_h = (body_h - 10) // 2

    _draw_board_team(dl, left_x, body_y, col_w, team_h, b, "BLUE", act)
    _draw_board_team(dl, left_x, body_y + team_h + 10, col_w, team_h,
                     b, "RED", act)
    _draw_board_center(dl, cen_x, body_y, cen_w, body_h, b, rec,
                       interactive=not live_connected)
    try:
        _rail_all = list(b.players.get("BLUE", [])) + list(b.players.get("RED", []))
        board_rail.draw_rail(dl, rail_x, body_y, rail_w, body_h, b, rec,
                             _txt, getattr(live, "inhouse_champs", {}) or {},
                             getattr(live, "primary_roles", {}) or {},
                             scout=_scout_champs_for_players(_rail_all))
    except Exception:
        pass

    # ── Enemy "probable next pick" ghost chip (Phase 4) ──────────────
    # Overlay a translucent chip on the enemy slot the engine thinks
    # will get filled next. Fades out automatically when that slot locks
    # (since _pick_slot_rects[..].champ becomes non-None).
    _draw_enemy_ghost_chip(dl, b)
    try:
        board_rail.draw_narrative(dl, left_x, narr_y, vw - 32, narr_h,
                                  b, _txt)
    except Exception:
        pass

    # (Full-screen scanline overlay deleted in Phase 3 — per ambient_motion
    # feedback, no full-screen ambient texture. Focal motion only.)

    # Pick-drag ghost: a portrait following the cursor while the user drags
    # a locked champion between role slots. Rendered last so it sits on top.
    if _pdrag.side is not None and _pdrag.champ:
        gsz = 40
        gx = _pdrag.pos[0] - gsz // 2
        gy = _pdrag.pos[1] - gsz // 2
        rc = _side_accent(_pdrag.side, lt=True)
        _draw_portrait(dl, gx, gy, gsz, _pdrag.champ, rc,
                       alpha=235, rounding=6, border_w=2)


def _draw_board_team(dl, x, y, w, h, b, side, act):
    accent    = _side_accent(side)
    accent_lt = _side_accent(side, lt=True)
    _panel_bg(dl, x, y, x + w, y + h, accent, 255, cut=True, cut_sz=14)
    on_clock = (act is not None and act.side == side)
    callsign = "BLUE OPS" if side == "BLUE" else "RED OPS"
    _txt(dl, x + 12, y + 12, callsign,
         (*accent_lt, 240), 22, "raj_sb_22")
    if on_clock:
        # Blinking "on the clock" cue beside the callsign (focal motion).
        blink = int(time.monotonic() * 2) % 2 == 0
        _txt(dl, x + 12, y + 36,
             ("> ON THE CLOCK" + (" _" if blink else "")),
             (*lol_theme.LOL["win"][:3], 225), 12, "raj_sb_12")
    ry = y + 54
    # Adaptive slot height — two team panels are stacked in one narrow
    # column under Layout A, so size slots to the available height.
    avail  = h - 54 - 70                 # header above · bans block below
    slot_h = max(30, min(56, avail // 5 - 6))
    port_sz = max(24, min(40, slot_h - 12))
    name_sz = 18 if slot_h >= 46 else (16 if slot_h >= 38 else 14)
    lock_sz = 20 if slot_h >= 46 else (18 if slot_h >= 38 else 16)
    name_key = ("raj_sb_18" if name_sz >= 18 else
                "raj_sb_16" if name_sz >= 16 else "raj_sb_14")
    lock_key = ("raj_sb_20" if lock_sz >= 20 else
                "raj_sb_18" if lock_sz >= 18 else "raj_sb_16")
    for i, role in enumerate(_ROLES):
        pl = b.players[side][i]
        champ = b.picks[side].get(role)
        # Register the slot rect for the pick-drag handler.
        _pick_slot_rects.append(
            (x + 10, ry, w - 20, slot_h, side, role, champ))
        # Drop-target highlight: when a pick is being dragged on this side,
        # other slots glow to advertise they're droppable.
        is_drop_target = (
            _pdrag.side == side and _pdrag.from_role is not None
            and role != _pdrag.from_role
            and x + 10 <= _pdrag.pos[0] <= x + w - 10
            and ry <= _pdrag.pos[1] <= ry + slot_h)
        slot_fill = lol_theme._alpha(lol_theme.LOL["navy_panel"],
                                     220 if is_drop_target else 165)
        slot_outline = ((*_side_accent(side, lt=True), 230)
                        if is_drop_target
                        else lol_theme._alpha(lol_theme.LOL["gold_rule"], 200))
        dpg.draw_rectangle((x + 10, ry), (x + w - 10, ry + slot_h),
                           fill=slot_fill, color=slot_outline,
                           thickness=2 if is_drop_target else 1,
                           rounding=4, parent=dl)
        # Role accent stripe (left edge)
        rc = _ROLE_COLORS.get(role, (120, 120, 120))
        dpg.draw_rectangle((x + 10, ry), (x + 16, ry + slot_h),
                           fill=(*rc, 220), color=(0, 0, 0, 0),
                           rounding=0, parent=dl)
        # Champion portrait (only when locked — otherwise blank).
        # While this slot's pick is being dragged, fade the source.
        port_x  = x + 20
        port_y  = ry + (slot_h - port_sz) // 2
        is_drag_source = (_pdrag.side == side and _pdrag.from_role == role)
        if champ:
            _draw_portrait(dl, port_x, port_y, port_sz, champ, rc,
                           alpha=90 if is_drag_source else 240,
                           rounding=5, border_w=2)
        else:
            dpg.draw_rectangle((port_x, port_y),
                               (port_x + port_sz, port_y + port_sz),
                               fill=lol_theme._alpha(lol_theme.LOL["navy_deep"], 140),
                               color=(*rc, 80),
                               thickness=1, rounding=5, parent=dl)
        # Role + player text (shifted right of portrait)
        txt_x = port_x + port_sz + 8
        _txt(dl, txt_x, ry + 4, role, (*accent, 200), 12, "raj_sb_12")
        _txt(dl, txt_x, ry + slot_h - name_sz - 5,
             (pl.get("name", "?")[:8]),
             (*lol_theme.LOL["txt"][:3], 225), name_sz, name_key)
        # Locked-champion name (right side; side-tinted, gold demoted)
        cc = ((*accent_lt, 245) if champ
              else (*lol_theme.LOL["txt_dim"][:3], 150))
        cstr = (champ or "—")[:8]
        ctw  = len(cstr) * (lock_sz // 2 + 1)
        _txt(dl, x + w - 14 - ctw, ry + (slot_h - lock_sz) // 2,
             cstr, cc, lock_sz, lock_key)
        # §3 #7 — pool-depth capsule: viable comfort picks left (pre-pick)
        if not champ:
            # v4.0.3: cache the per-slot candidate-search result on a board
            # signature. Without this we re-run _candidates_for_player for
            # every empty slot on both teams every frame, which (combined
            # with the rest of the board work) made the screen feel laggy.
            try:
                pname = (pl or {}).get("name", "")
                key = (side, role, pname, b.pointer,
                       tuple(sorted(b.picks.get("BLUE", {}).items())),
                       tuple(sorted(b.picks.get("RED", {}).items())),
                       tuple(b.bans.get("BLUE", [])),
                       tuple(b.bans.get("RED", [])))
                depth = _depth_cache.get(key)
                if depth is None:
                    depth = len(_candidates_for_player(
                        pl, role, getattr(live, "inhouse_champs", {}) or {},
                        getattr(live, "primary_roles", {}) or {},
                        b.used_champs(), k=10,
                        scout_champs=_scout_champs_for_players([pl])))
                    _depth_cache[key] = depth
                    # Bound cache size — a draft tops out at ~200 distinct
                    # signatures; this stays well under that.
                    if len(_depth_cache) > 512:
                        _depth_cache.clear()
                        _depth_cache[key] = depth
            except Exception:
                depth = 0
            cap_x = x + w - 13
            cap_h = slot_h - 14
            cap_y = ry + 7
            dpg.draw_rectangle((cap_x, cap_y), (cap_x + 4, cap_y + cap_h),
                               fill=lol_theme._alpha(lol_theme.LOL["navy_deep"], 160),
                               color=(0, 0, 0, 0), parent=dl)
            f = max(0.0, min(1.0, depth / 8.0))
            fh = int(cap_h * f)
            dcol = (lol_theme.LOL["win"][:3] if depth >= 5 else
                    lol_theme.LOL["warning"][:3] if depth >= 2
                    else lol_theme.LOL["loss"][:3])
            if fh > 0:
                dpg.draw_rectangle((cap_x, cap_y + cap_h - fh),
                                   (cap_x + 4, cap_y + cap_h),
                                   fill=(*dcol, 220), color=(0, 0, 0, 0),
                                   parent=dl)
        ry += slot_h + 6
    # bans row — only if it still fits inside this (possibly short) panel
    if ry + 44 <= y + h:
        _txt(dl, x + 14, ry + 4, "BANS",
             (*lol_theme.LOL["red_side"][:3], 220), 14, "raj_sb_14")
        by = ry + 26
        bh = min(30, (y + h) - by - 4)
        bw_each = (w - 28) // 5
        for j in range(5):
            bx = x + 14 + j * bw_each
            ch = b.bans[side][j] if j < len(b.bans[side]) else None
            dpg.draw_rectangle((bx, by), (bx + bw_each - 4, by + bh),
                               fill=lol_theme._alpha(lol_theme.LOL["navy_deep"], 200),
                               color=(*lol_theme.LOL["red_side_dk"][:3], 175),
                               thickness=1, rounding=3, parent=dl)
            _txt(dl, bx + 5, by + max(2, (bh - 13) // 2), (ch or "—")[:6],
                 (165, 165, 165, 230 if ch else 95), 13, "raj_sb_12")
        ry = by + bh

    # ── Enemy "LIKELY NEXT" preview ribbon ──────────────────────────
    # Only on the OPPOSING side (the user's intel about the enemy team).
    # Slides in / fades on each actor change for a polished feel.
    if hasattr(b, "our_side") and side != b.our_side:
        ribbon_top = ry + 16
        if ribbon_top + 40 < y + h - 4:
            preview = _enemy_pick_preview(b, side, n=3)
            if preview:
                # Trigger slide-in fade when the on-the-clock actor changes
                actor_sig = (act.side, act.kind, act.idx) if act else None
                if actor_sig != draft._board_actor_sig:
                    draft._board_actor_sig = actor_sig
                    draft._board_actor_anim = 0.0
                    def _set_act(v):
                        draft._board_actor_anim = v
                    anim.tween(0.0, 1.0, 280, "out_cubic",
                               on_update=_set_act)
                ta = draft._board_actor_anim
                slide_dx = int((1 - ta) * 14)
                fade = int(ta * 255)

                rib_x = x + 12 + slide_dx
                rib_w = w - 24 - slide_dx
                # Container — navy panel with side-accent border
                dpg.draw_rectangle((rib_x, ribbon_top),
                                   (rib_x + rib_w, ribbon_top + 22),
                                   fill=lol_theme._alpha(
                                       lol_theme.LOL["navy_deep"],
                                       int(fade * 0.82)),
                                   color=(*accent, int(fade * 0.55)),
                                   thickness=1, rounding=3, parent=dl)
                _txt(dl, rib_x + 6, ribbon_top + 3, "LIKELY NEXT",
                     (*accent_lt, int(fade * 0.90)), 12, "raj_sb_12")
                row_y = ribbon_top + 28
                for role, pname, names in preview[:3]:
                    if row_y + 22 > y + h - 4:
                        break
                    rc = _ROLE_COLORS.get(role, (140, 140, 140))
                    # Role badge
                    dpg.draw_rectangle((rib_x + 4, row_y),
                                       (rib_x + 38, row_y + 18),
                                       fill=(*rc, int(fade * 0.20)),
                                       color=(*rc, int(fade * 0.85)),
                                       thickness=1, rounding=3, parent=dl)
                    _txt(dl, rib_x + 8, row_y + 1, role[:4],
                         (*rc, fade), 12, "raj_sb_12")
                    # Likely champ list — top 2 with shorter separator so
                    # full champion names survive at narrow column widths.
                    line = " & ".join(names[:2]) if names else "—"
                    max_chars = max(9, (rib_w - 52) // 8)
                    if len(line) > max_chars:
                        line = line[:max_chars - 1] + "…"
                    _txt(dl, rib_x + 44, row_y + 2, line,
                         (*lol_theme.LOL["txt"][:3], int(fade * 0.92)),
                         13, "raj_sb_12")
                    row_y += 22


def _draw_board_center(dl, x, y, w, h, b, rec, interactive=True):
    _gradient_frame(dl, x, y, x + w, y + h,
                    lol_theme.LOL["gold_lt"][:3],
                    lol_theme.LOL["gold_rule"][:3],
                    alpha=160, layers=4)
    _panel_bg(dl, x, y, x + w, y + h, lol_theme.LOL["gold"], 255,
              cut=True, cut_sz=18)

    if rec.get("done") or b.is_complete():
        _draw_done_summary(dl, x, y, w, h, b, interactive)
        return

    act = rec.get("action")
    our_turn = rec.get("our_turn")

    # ── Side-tinted top edge stripe (subtle side identity wash) ──────
    if act:
        side_tint = _side_accent(act.side, lt=True)
        for i in range(10):
            ta = int(40 * (1 - i / 10))
            dpg.draw_line((x + 6, y + 2 + i),
                          (x + w - 6, y + 2 + i),
                          color=(*side_tint, ta),
                          thickness=1, parent=dl)

    # ── Action banner: gold = our turn, red = opponent turn ──────
    banner = (lol_theme.LOL["gold"][:3] if our_turn
              else lol_theme.LOL["red_side"][:3])
    # Focal shimmer when it's our turn — pulses border alpha gently
    if our_turn:
        bpulse = (math.sin(time.monotonic() * 3.3 * 2 * math.pi) + 1) / 2
        banner_border_a = int(190 + bpulse * 60)
        banner_fill_a   = int(50 + bpulse * 16)
    else:
        banner_border_a = 215
        banner_fill_a   = 55
    dpg.draw_rectangle((x + 10, y + 10), (x + w - 10, y + 68),
                       fill=(*banner, banner_fill_a),
                       color=(*banner, banner_border_a),
                       thickness=2, rounding=6, parent=dl)
    # Top-edge inner highlight (rich-card feel)
    for hi in range(5):
        ha = int(60 * (1 - hi / 5))
        dpg.draw_line((x + 16, y + 12 + hi), (x + w - 16, y + 12 + hi),
                      color=(*banner, ha), thickness=1, parent=dl)
    if act:
        head = f"{'YOUR' if our_turn else 'OPPONENT'} {act.kind.upper()}"
        sub = f"{act.label}  ·  phase {act.phase}  ·  step {act.idx+1}/20"
    else:
        head, sub = "—", ""
    _txt(dl, x + 22, y + 18, head,
         (*(lol_theme.LOL["gold_lt"][:3] if our_turn
            else lol_theme.LOL["red_side"][:3]), 245),
         22, "raj_sb_22")
    _txt(dl, x + 22, y + 48, sub,
         (*lol_theme.LOL["txt_dim"][:3], 220), 14, "raj_sb_14")

    # (Phase 6: LCU phase-countdown bar was removed with the rest of
    # the LCU live-import path — no timer source remains.)

    ny = y + 80

    # ── Archetype picker row (only when interactive, not in live mirror) ─
    if interactive and act:
        picker_h = _draw_arch_picker(dl, x, ny, w, draft.board_target_arch)
        ny += picker_h

    # ── STRATEGIC sub-panel: both teams' wincon contrast ──────────────
    tc       = rec.get("target_comp") or {}
    tc_enemy = _enemy_target_comp(b, act)
    if tc.get("label") or tc_enemy.get("label"):
        sp_h     = 50
        OUR_COL   = (_side_accent(act.side) if act
                     else lol_theme.LOL["gold"][:3])
        OUR_LT    = (_side_accent(act.side, lt=True) if act
                     else lol_theme.LOL["gold_lt"][:3])
        ENEMY_COL = (_side_accent("RED" if act.side == "BLUE" else "BLUE")
                     if act else lol_theme.LOL["red_side"][:3])
        dpg.draw_rectangle((x + 14, ny), (x + w - 14, ny + sp_h),
                           fill=lol_theme._alpha(lol_theme.LOL["navy_deep"], 210),
                           color=lol_theme._alpha(lol_theme.LOL["gold_rule"], 200),
                           thickness=1, rounding=4, parent=dl)
        _txt(dl, x + 20, ny + 4, "TACTICAL READOUT",
             (*lol_theme.LOL["gold_lt"][:3], 235), 13, "raj_sb_12")
        # Middle divider between the two readouts
        mid_x = x + w // 2 + 4
        dpg.draw_line((mid_x - 6, ny + 22), (mid_x - 6, ny + sp_h - 4),
                      color=(*lol_theme.LOL["gold_rule"][:3], 170),
                      thickness=1, parent=dl)
        # Our readout — [ OUR ] callsign + side-tinted stripe
        if tc.get("label"):
            dpg.draw_rectangle((x + 18, ny + 24), (x + 22, ny + 44),
                               fill=(*OUR_COL, 220), color=(0, 0, 0, 0),
                               parent=dl)
            our_label = tc.get("label", "")[:24]
            our_spike = (tc.get("spike", "") or tc.get("win_condition", ""))[:26]
            our_line  = our_label + (f"  ·  {our_spike}" if our_spike else "")
            _txt(dl, x + 28, ny + 25, "[ OUR ]",
                 (*OUR_LT, 235), 12, "raj_sb_12")
            _txt(dl, x + 86, ny + 25, our_line[:40],
                 (*lol_theme.LOL["txt"][:3], 240), 13, "raj_sb_12")
        # Enemy readout — [ ENEMY ] callsign + right-edge stripe
        if tc_enemy.get("label"):
            dpg.draw_rectangle((mid_x, ny + 24), (mid_x + 4, ny + 44),
                               fill=(*ENEMY_COL, 220), color=(0, 0, 0, 0),
                               parent=dl)
            ene_label = tc_enemy.get("label", "")[:24]
            ene_spike = (tc_enemy.get("spike", "") or tc_enemy.get("win_condition", ""))[:26]
            ene_line  = ene_label + (f"  ·  {ene_spike}" if ene_spike else "")
            _txt(dl, mid_x + 10, ny + 25, "[ ENEMY ]",
                 (*lol_theme.LOL["red_side"][:3], 235), 12, "raj_sb_12")
            _txt(dl, mid_x + 84, ny + 25, ene_line[:36],
                 (*lol_theme.LOL["txt"][:3], 240), 13, "raj_sb_12")
        ny += sp_h + 8

    # Context lines — coded prefixes, color coding preserved
    for note in (rec.get("notes") or [])[1:2]:
        _txt(dl, x + 16, ny, f"›  {note[:58]}",
             (*lol_theme.LOL["txt_dim"][:3], 220), 14, "raj_sb_14")
        ny += 21
    for cw_ in (rec.get("cohesion") or [])[:2]:
        _txt(dl, x + 16, ny, f"!  {cw_[:56]}",
             (*lol_theme.LOL["warning"][:3], 235), 14, "raj_sb_14")
        ny += 21
    for exp in (rec.get("exploit") or [])[:2]:
        _txt(dl, x + 16, ny, f"+  {exp[:54]}",
             (*lol_theme.LOL["win"][:3], 235), 14, "raj_sb_14")
        ny += 21

    # ── PRIMARY CALL — the #1 recommendation, emphasised ─────────────
    sug = rec.get("suggestions") or []
    pool_region_h = 220
    if not sug and act:
        # v3.0.5: graceful fallback so the very first ban (or any state
        # where the engine produces nothing) doesn't render an empty hero
        # area. _draw_board's data-signature retry re-runs once scout data
        # lands; while we wait, we show a placeholder card that tells the
        # user what to do and keeps the manual pool grid below interactive.
        pc_h = 96
        ny += 8
        card_y = ny
        placeholder_col = lol_theme.LOL["gold"][:3]
        dpg.draw_rectangle((x + 14, card_y), (x + w - 14, card_y + pc_h),
                           fill=lol_theme._alpha(lol_theme.LOL["navy_panel"], 200),
                           color=(*placeholder_col, 200),
                           thickness=2, rounding=8, parent=dl)
        # Caption + body
        head = ("WARMING UP" if (not getattr(live, "loaded", False)
                                  or not getattr(live, "scout_sheets", None))
                else "NO STRONG CALL")
        _txt(dl, x + 24, card_y + 16, head,
             (*placeholder_col, 240), 14, "raj_sb_14")
        body = ("loading scouting data — pick from the pool below"
                if head == "WARMING UP" else
                "engine has no high-confidence pick — choose from the manual pool")
        _txt(dl, x + 24, card_y + 42, body[:64],
             (*lol_theme.LOL["txt_dim"][:3], 230), 13, "raj_sb_12")
        if act.kind == "ban":
            _txt(dl, x + 24, card_y + 64,
                 "tip: strip the enemy's deepest comfort pick",
                 (*lol_theme.LOL["gold_lt"][:3], 200), 12, "raj_sb_12")
        else:
            _txt(dl, x + 24, card_y + 64,
                 "tip: prioritise comfort picks before lane is revealed",
                 (*lol_theme.LOL["gold_lt"][:3], 200), 12, "raj_sb_12")
        ny += pc_h + 14
        sug = []  # ensure the rest of the block stays no-op
    if sug:
        s0 = sug[0]
        tag = s0.get("tag", "")
        tcol = _BOARD_TAG_COL.get(tag, lol_theme.LOL["gold"][:3])
        pc_h = 150
        ny += 8

        # Detect recommendation change → trigger slide-up ease-in
        sig = (s0.get("champion", ""), tag)
        if sig != draft._board_top_call_sig:
            draft._board_top_call_sig = sig
            draft._board_top_call_anim = 0.0
            def _set_tc(v):
                draft._board_top_call_anim = v
            anim.tween(0.0, 1.0, 320, "out_cubic", on_update=_set_tc)
        t = draft._board_top_call_anim
        anim_dy = int((1 - t) * 18)
        card_y = ny + anim_dy

        # Hover detection (brightens border, slight halo bump)
        hovered = (interactive
                   and _hover(x + 14, card_y, w - 28, pc_h))

        # Focal pulsing accent line ABOVE the card — anchors TOP CALL.
        div_alpha = int(110 + (math.sin(time.monotonic() * 4.5 * 2 * math.pi)
                               + 1) / 2 * 70)
        dpg.draw_line((x + 24, ny - 6), (x + w - 24, ny - 6),
                      color=(*tcol, div_alpha), thickness=1, parent=dl)

        # Halo glow — intensified bloom (6 layers, brighter inner color)
        halo_dk = (max(0, tcol[0] - 90),
                   max(0, tcol[1] - 90),
                   max(0, tcol[2] - 90))
        halo_alpha = 150 if hovered else 110
        _gradient_frame(dl, x + 14, card_y, x + w - 14, card_y + pc_h,
                        c_top=tcol, c_bot=halo_dk,
                        alpha=halo_alpha, layers=6)
        # §3 #21 — splash-art backdrop with §5.5 ken-burns (degrades to
        # portrait-only until the splash is fetched/registered).
        try:
            _sp = splash_art.get_texture(s0.get("champion", ""))
        except Exception:
            _sp = None
        if _sp:
            _seed = hash(s0.get("champion", "")) % 100
            # Ken-burns drift on the hero splash (focal motion, always on).
            _t = (time.monotonic() / 12.0) % 1.0
            _ph = 0.5 + 0.5 * math.sin(_t * 2 * math.pi + _seed)
            _jx = (_seed % 7 - 3) / 120.0 * _ph
            _jy = ((_seed // 7) % 5 - 2) / 120.0 * _ph
            _u0 = min(0.30, max(0.0, 0.05 + 0.03 * _ph + _jx))
            _v0 = min(0.40, max(0.0, 0.14 + 0.04 * _ph + _jy))
            _u1 = max(0.70, min(1.0, 0.95 + 0.03 * _ph + _jx))
            _v1 = max(0.55, min(1.0, 0.62 + 0.04 * _ph + _jy))
            try:
                dpg.draw_image(_sp, (x + 15, card_y + 1),
                               (x + w - 15, card_y + pc_h - 1),
                               uv_min=(_u0, _v0), uv_max=(_u1, _v1),
                               parent=dl)
                # Readability scrim over the splash
                dpg.draw_rectangle((x + 15, card_y + 1),
                                   (x + w - 15, card_y + pc_h - 1),
                                   fill=lol_theme._alpha(
                                       lol_theme.LOL["navy_deep"], 158),
                                   color=(0, 0, 0, 0), parent=dl)
            except Exception:
                pass
        # Backdrop — hero card body (rounded LCS-broadcast look)
        dpg.draw_rectangle((x + 14, card_y), (x + w - 14, card_y + pc_h),
                           fill=(*tcol, 50 if hovered else 42),
                           color=(*tcol, 245 if hovered else 225),
                           thickness=3 if hovered else 2,
                           rounding=8, parent=dl)
        # Inner top-edge gradient highlight — "lit from above" feel.
        for hi in range(8):
            ha = int(80 * (1 - hi / 8))
            dpg.draw_line((x + 22, card_y + 3 + hi),
                          (x + w - 22, card_y + 3 + hi),
                          color=(*tcol, ha), thickness=1, parent=dl)

        # Champion portrait (left, 96×96)
        portrait_sz = 96
        port_x = x + 20
        port_y = card_y + (pc_h - portrait_sz) // 2
        _draw_portrait(dl, port_x, port_y, portrait_sz,
                       s0.get("champion", ""), tcol,
                       alpha=245, rounding=8, border_w=3)
        # Inner glow rim around the portrait.
        dpg.draw_rectangle((port_x + 2, port_y + 2),
                           (port_x + portrait_sz - 2,
                            port_y + portrait_sz - 2),
                           fill=(0, 0, 0, 0),
                           color=(*tcol, 130),
                           thickness=1, rounding=6, parent=dl)

        # ─ Right-column text content ─────────────────────────────────
        text_x  = port_x + portrait_sz + 18
        right_x = x + w - 22                       # right edge for chips

        # ROW 1 (header): TOP CALL caption + tag chip on left;
        #                 confidence meter + viability chip on right
        _txt(dl, text_x, card_y + 12, "TOP CALL",
             (*tcol, 240), 13, "raj_sb_12")
        cap_w = int(len("TOP CALL") * 13 * 0.6)
        # Gold underline under the caption
        dpg.draw_line((text_x, card_y + 28),
                      (text_x + cap_w, card_y + 28),
                      color=(*tcol, 180), thickness=1, parent=dl)
        chip_w_used = _draw_tag_chip(dl, text_x + 110, card_y + 9,
                                      tag, alpha=245, big=True)

        # Score gap to next-best (only show if meaningful)
        gap_chip_w = 0
        if len(sug) >= 2:
            try:
                gap = float(s0.get("score", 0)) - float(sug[1].get("score", 0))
            except (TypeError, ValueError):
                gap = 0.0
            if gap >= 0.05:
                # §3 #30 — confidence meter: score gap → 0-100% conviction bar
                if gap >= 0.15:
                    g_alpha = int(190 + (math.sin(time.monotonic() * 2.6
                                                   * 2 * math.pi) + 1) / 2 * 60)
                else:
                    g_alpha = 215
                conf = max(0.0, min(1.0, gap / 0.30))
                gap_chip_w = 150
                gx = text_x + 110 + chip_w_used + 14
                lbl = f"CONF {int(round(conf*100))}%"
                _txt(dl, gx, card_y + 13, lbl,
                     (*lol_theme.LOL["gold_lt"][:3], 240), 12, "raj_sb_12")
                bar_x = gx + 78
                bar_w = gap_chip_w - 78
                dpg.draw_rectangle((bar_x, card_y + 14),
                                   (bar_x + bar_w, card_y + 28),
                                   fill=lol_theme._alpha(
                                       lol_theme.LOL["navy_deep"], 150),
                                   color=lol_theme._alpha(
                                       lol_theme.LOL["gold_rule"], 200),
                                   thickness=1, rounding=3, parent=dl)
                dpg.draw_rectangle((bar_x, card_y + 14),
                                   (bar_x + max(3, int(bar_w * conf)),
                                    card_y + 28),
                                   fill=(*lol_theme.LOL["gold"][:3], g_alpha),
                                   color=(0, 0, 0, 0),
                                   rounding=3, parent=dl)

        # Viability chip — right-aligned (uses target_comp data when available)
        viab = (tc.get("viability") or "").upper()
        if viab:
            vcol = _VIAB_COLORS.get(viab, lol_theme.LOL["txt"][:3])
            v_short = "NOT REC." if viab == "NOT RECOMMENDED" else viab
            v_lbl   = f"[ {v_short} ]"
            v_chip_w = len(v_lbl) * 8 + 14
            vx = right_x - v_chip_w
            dpg.draw_rectangle((vx, card_y + 11),
                               (vx + v_chip_w, card_y + 31),
                               fill=(*vcol, 80), color=(*vcol, 240),
                               thickness=2, rounding=4, parent=dl)
            _txt(dl, vx + 8, card_y + 12, v_lbl,
                 (*vcol, 250), 13, "raj_sb_12")

        # Contested mini-glyph (between header and champion name) when applicable
        contested_here = _is_contested(s0.get("champion", ""),
                                        b.players.get("BLUE", []),
                                        b.players.get("RED", []))
        if contested_here:
            cx_dot = text_x
            cy_dot = card_y + 38
            # diamond glyph + label, tinted with the tag color so it reads
            # as part of the recommendation (not a separate gold cue).
            ds = 5
            dpg.draw_polygon([(cx_dot + ds, cy_dot),
                              (cx_dot + 2*ds, cy_dot + ds),
                              (cx_dot + ds, cy_dot + 2*ds),
                              (cx_dot,        cy_dot + ds)],
                             fill=(*tcol, 235),
                             color=(0, 0, 0, 0), parent=dl)
            _txt(dl, cx_dot + 16, cy_dot - 4, "CONTESTED",
                 (*tcol, 230), 12, "mono_12")
            champ_name_y = card_y + 58
        else:
            champ_name_y = card_y + 44

        # ROW 2: champion name (the hero) — typewriter reveal on change
        name = s0.get("champion", "?")[:16]
        reveal_t = draft._board_top_call_anim          # 0..1
        chars = int(len(name) * min(1.0, reveal_t * 1.6))
        visible = name[:chars]
        cursor = "|" if (int(time.monotonic() * 3) % 2 == 0
                         and chars < len(name)) else ""
        _txt(dl, text_x, champ_name_y, visible + cursor,
             (*lol_theme.LOL["gold_lt"][:3], 248), 36, "raj_36")

        # §3 #29 — champion identity vector: 3 strongest subclass tags as
        # bracketed chips, to the right of the hero name.
        try:
            sc = getattr(_eng, "SUBCLASSES", {}) or {}
            _ID_PRI = (("frontline", "FRONT"), ("engage", "ENGAGE"),
                       ("assassin_or_burst", "BURST"), ("aoe_damage", "AOE"),
                       ("peel", "PEEL"), ("long_range", "RANGE"),
                       ("hypercarry", "CARRY"), ("scaling", "SCALE"),
                       ("cc", "CC"), ("mobile", "MOBILE"),
                       ("waveclear", "WAVE"), ("duelist", "DUEL"),
                       ("global_pressure", "GLOBAL"),
                       ("tank_buster", "TANKBST"), ("anti_carry", "ANTICRY"))
            cn = s0.get("champion", "")
            id_tags = [lbl for key, lbl in _ID_PRI
                       if cn in sc.get(key, ())][:3]
            ix = text_x + len(visible) * 21 + 18
            for lbl in id_tags:
                chip_txt = f"[ {lbl} ]"
                cw = len(chip_txt) * 8 + 4
                dpg.draw_rectangle((ix, champ_name_y + 8),
                                   (ix + cw, champ_name_y + 30),
                                   fill=lol_theme._alpha(
                                       lol_theme.LOL["gold_dk"], 110),
                                   color=lol_theme._alpha(
                                       lol_theme.LOL["gold"], 190),
                                   thickness=1, rounding=3, parent=dl)
                _txt(dl, ix + 6, champ_name_y + 10, chip_txt,
                     (*lol_theme.LOL["gold_lt"][:3], 230), 12, "raj_sb_12")
                ix += cw + 6
        except Exception:
            pass

        # ROW 3: why text
        why_y = champ_name_y + 44
        _txt(dl, text_x, why_y, str(s0.get("why", ""))[:60],
             (*lol_theme.LOL["txt_dim"][:3], 230), 17, "raj_sb_18")

        # Divider before stats band (fades with the data-band animation)
        band_alpha = int(min(1.0, max(0.0, (t - 0.35) / 0.65)) * 255)
        if band_alpha > 0:
            div_y = why_y + 26
            dpg.draw_line((text_x, div_y), (right_x, div_y),
                          color=(*lol_theme.LOL["gold_rule"][:3],
                                 int(band_alpha * 0.7)),
                          thickness=1, parent=dl)

            # ROW 4: per-player stats data band
            stats_y    = div_y + 6
            player     = s0.get("player", "")
            champ_n    = s0.get("champion", "")
            role_n     = s0.get("role", "")
            opp_champ  = None
            if act and act.kind == "pick" and role_n:
                opp_side = "RED" if act.side == "BLUE" else "BLUE"
                opp_champ = b.picks.get(opp_side, {}).get(role_n)

            if act and act.kind == "ban":
                # BANS: surface the enemy threat (player + games + WR)
                enemy_side = "RED" if act.side == "BLUE" else "BLUE"
                threat = _enemy_threat(champ_n, b.players.get(enemy_side, []))
                covered = _team_counter_covers(
                    champ_n, b.locked_picks(act.side) if hasattr(b, "locked_picks") else [])
                if threat:
                    band = _truncate_band(
                        f"{threat['player']}: {threat['wr']}% over "
                        f"{threat['games']}g  ·  {threat['kda']:.1f} KDA",
                        56)
                    _txt(dl, text_x, stats_y, band,
                         (*lol_theme.LOL["txt"][:3], band_alpha),
                         14, "raj_sb_14")
                else:
                    _txt(dl, text_x, stats_y,
                         "No inhouse data on this enemy threat",
                         (*lol_theme.LOL["txt_dim"][:3], band_alpha),
                         14, "raj_sb_14")
                if covered:
                    cov_lbl = "[ COVERED · save the ban ]"
                    cov_w = len(cov_lbl) * 8 + 14
                    cov_x = right_x - cov_w
                    dpg.draw_rectangle((cov_x, stats_y - 3),
                                       (cov_x + cov_w, stats_y + 19),
                                       fill=(*lol_theme.LOL["win"][:3],
                                             int(band_alpha * 0.22)),
                                       color=(*lol_theme.LOL["win"][:3],
                                              band_alpha),
                                       thickness=1, rounding=3, parent=dl)
                    _txt(dl, cov_x + 8, stats_y - 1, cov_lbl,
                         (*lol_theme.LOL["win"][:3], band_alpha),
                         12, "raj_sb_12")
            else:
                # PICKS: per-player WR / games / KDA / form
                stats = _player_champ_stats(player, champ_n) if player else None
                form  = _player_form(player) if player else ""
                bits  = []
                if stats:
                    bits.append(f"{player}:  {stats['wr']}% over {stats['games']}g")
                    if stats["games"] > 0:
                        bits.append(f"{stats['kda']:.1f} KDA")
                elif player:
                    bits.append(f"{player}:  no inhouse history on {champ_n}")
                if form and form in _FORM_COLORS:
                    pass   # rendered as a chip below
                band_text = _truncate_band("  ·  ".join(bits), 56)
                _txt(dl, text_x, stats_y, band_text,
                     (*lol_theme.LOL["txt"][:3], band_alpha),
                     14, "raj_sb_14")
                # Form chip on the right end of stats line — [ HOT ] bracketed
                if form in _FORM_COLORS:
                    fcol = _FORM_COLORS[form]
                    f_lbl = f"[ {form} ]"
                    f_w = len(f_lbl) * 8 + 12
                    fx = right_x - f_w
                    dpg.draw_rectangle((fx, stats_y - 3),
                                       (fx + f_w, stats_y + 19),
                                       fill=(*fcol, int(band_alpha * 0.22)),
                                       color=(*fcol, band_alpha),
                                       thickness=1, rounding=3, parent=dl)
                    _txt(dl, fx + 8, stats_y - 1, f_lbl,
                         (*fcol, band_alpha), 12, "raj_sb_12")

            # ROW 5 (optional): lane matchup OR synergy callout
            extra_y = stats_y + 22
            extra_drawn = False
            if act and act.kind == "pick" and opp_champ and champ_n:
                lm = _lane_matchup(champ_n, opp_champ)
                if lm:
                    sign = "+" if lm > 0 else ""
                    lm_col = ((90, 200, 140) if lm > 0
                              else (215, 110, 100) if lm < 0
                              else (180, 180, 180))
                    _txt(dl, text_x, extra_y,
                         f"Lane vs {opp_champ[:12]}: {sign}{lm}",
                         (*lm_col, band_alpha), 14, "raj_sb_14")
                    extra_drawn = True
            if not extra_drawn and act and act.kind == "pick":
                ours = b.locked_picks(act.side) if hasattr(b, "locked_picks") else []
                cos = _synergy_callouts(champ_n, ours)
                if cos:
                    other, kind, _str = cos[0]
                    msg_col = (_SYNERGY_COL_OK if kind == "syn"
                               else _SYNERGY_COL_BAD)
                    pre = "Strong with" if kind == "syn" else "Conflict with"
                    _txt(dl, text_x, extra_y,
                         f"{pre} {other[:14]}",
                         (*msg_col, band_alpha), 14, "raj_sb_14")

        if interactive:
            _board_hits.append((x + 14, ny, w - 28, pc_h, "pick",
                                (s0.get("champion"), s0.get("role"))))
        ny += pc_h + 14

    # ── Alternatives ────────────────────────────────────────────────
    if len(sug) > 1:
        _txt(dl, x + 16, ny, "ALTERNATIVES",
             (*lol_theme.LOL["gold_lt"][:3], 230), 16, "raj_sb_16")
        ny += 28
        row_h = 52
        # Cap to 4 alternative rows to give STRATEGIC + enriched TOP CALL room.
        for s in sug[1:5]:
            if ny + row_h > y + h - pool_region_h:
                break
            tag = s.get("tag", "")
            tcol = _BOARD_TAG_COL.get(tag, lol_theme.LOL["gold"][:3])
            # Hover lift — brighten border + fill on mouseover
            alt_hover = (interactive
                         and _hover(x + 14, ny, w - 28, row_h - 6))
            # Backdrop card — slim rounded row
            dpg.draw_rectangle((x + 14, ny),
                               (x + w - 14, ny + row_h - 6),
                               fill=lol_theme._alpha(
                                   lol_theme.LOL["navy_panel"],
                                   210 if alt_hover else 165),
                               color=(*tcol, 220 if alt_hover else 160),
                               thickness=2 if alt_hover else 1,
                               rounding=4, parent=dl)
            # Left-edge tag vertical stripe
            dpg.draw_rectangle((x + 14, ny + 3),
                               (x + 18, ny + row_h - 9),
                               fill=(*tcol, 220 if alt_hover else 170),
                               color=(0, 0, 0, 0), parent=dl)
            # Subtle top-edge tint stripe — consistency with TOP CALL
            for hi in range(4):
                ha = int(40 * (1 - hi / 4))
                dpg.draw_line((x + 20, ny + 2 + hi),
                              (x + w - 18, ny + 2 + hi),
                              color=(*tcol, ha), thickness=1, parent=dl)
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
                 (*lol_theme.LOL["gold_lt"][:3], 240), 22, "raj_sb_22")
            _txt(dl, cx_x, ny + 30, str(s.get("why", ""))[:36],
                 (*lol_theme.LOL["txt_dim"][:3], 205), 14, "raj_sb_14")
            # Right-edge mini stats column (WR · g and comfort delta)
            stats_x = x + w - 22
            stats = (_player_champ_stats(s.get("player", ""),
                                         s.get("champion", ""))
                     if act and act.kind == "pick" else None)
            if stats and stats["games"] > 0:
                line1 = f"{stats['wr']}% · {stats['games']}g"
                lw = len(line1) * 8
                _txt(dl, stats_x - lw, ny + 6, line1,
                     (*lol_theme.LOL["txt"][:3], 230), 14, "raj_sb_14")
                # Comfort delta vs TOP CALL
                try:
                    delta = (float(s.get("comfort", 0))
                             - float(s0.get("comfort", 0)))
                except (TypeError, ValueError):
                    delta = 0.0
                if abs(delta) >= 0.05:
                    sign = "+" if delta > 0 else ""
                    dpct = int(round(delta * 100))
                    dlbl = f"{sign}{dpct}c"
                    dcol = (lol_theme.LOL["win"][:3] if delta > 0
                            else lol_theme.LOL["loss"][:3])
                    dw = len(dlbl) * 8
                    _txt(dl, stats_x - dw, ny + 28, dlbl,
                         (*dcol, 220), 14, "raj_sb_14")
            elif act and act.kind == "ban":
                # Mirror the ban backing for alt bans
                opp_side = "RED" if act.side == "BLUE" else "BLUE"
                threat = _enemy_threat(s.get("champion", ""),
                                       b.players.get(opp_side, []))
                if threat:
                    line1 = f"{threat['wr']}% · {threat['games']}g"
                    lw = len(line1) * 8
                    _txt(dl, stats_x - lw, ny + 6, line1,
                         (*lol_theme.LOL["txt"][:3], 230), 14, "raj_sb_14")
                    pname_short = threat['player'][:8]
                    pw = len(pname_short) * 7
                    _txt(dl, stats_x - pw, ny + 28, pname_short,
                         (*lol_theme.LOL["txt_dim"][:3], 210), 12, "raj_sb_12")
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
        lol_theme.draw_gold_rule(dl, x + 14, py, x + w - 14, py,
                                 thickness=1, alpha=160)
        _txt(dl, x + 16, py + 10,
             "› mirroring live champ select — picks/bans follow the client",
             (*lol_theme.LOL["win"][:3], 215), 14, "raj_sb_14")
        return

    py = y + h - pool_region_h
    lol_theme.draw_gold_rule(dl, x + 14, py, x + w - 14, py,
                             thickness=1, alpha=160)

    full_pool = _board_legal_pool(b, act)
    filtered = _filter_pool(full_pool, draft.board_pool_search)

    # Header: title (left) + result count (right)
    _txt(dl, x + 16, py + 8, "LOCK ANY CHAMPION",
         (*lol_theme.LOL["gold_lt"][:3], 230), 14, "raj_sb_14")
    if draft.board_pool_search:
        cnt_str = f"{len(filtered)} of {len(full_pool)}"
    else:
        cnt_str = f"{len(full_pool)} champions"
    cnt_w = len(cnt_str) * 8
    _txt(dl, x + w - 16 - cnt_w, py + 10, cnt_str,
         (*lol_theme.LOL["txt_dim"][:3], 200), 12, "raj_sb_12")

    # Search box
    sb_y = py + 36
    sb_h = 38
    sb_x = x + 16
    sb_w = w - 32
    dpg.draw_rectangle((sb_x, sb_y), (sb_x + sb_w, sb_y + sb_h),
                       fill=lol_theme._alpha(lol_theme.LOL["navy_deep"], 210),
                       color=lol_theme._alpha(lol_theme.LOL["gold_rule"], 220),
                       thickness=2, rounding=4, parent=dl)
    _txt(dl, sb_x + 14, sb_y + 8, "›",
         (*lol_theme.LOL["gold_lt"][:3], 220), 22, "raj_sb_22")
    # Vertical divider after the prompt
    dpg.draw_line((sb_x + 40, sb_y + 8), (sb_x + 40, sb_y + sb_h - 8),
                  color=(*lol_theme.LOL["gold_rule"][:3], 180),
                  thickness=1, parent=dl)
    # Query text with blinking caret
    cursor = "_" if int(time.monotonic() * 2) % 2 == 0 else " "
    if draft.board_pool_search:
        _txt(dl, sb_x + 52, sb_y + 7,
             draft.board_pool_search + cursor,
             (*lol_theme.LOL["gold_lt"][:3], 245), 22, "raj_sb_22")
    else:
        _txt(dl, sb_x + 52, sb_y + 7, cursor,
             (*lol_theme.LOL["gold_lt"][:3], 200), 22, "raj_sb_22")
        _txt(dl, sb_x + 68, sb_y + 11, "type to filter…",
             (*lol_theme.LOL["txt_dim"][:3], 165), 16, "raj_sb_16")
    # Clear "X" button (only when there's text)
    if draft.board_pool_search:
        cx_x = sb_x + sb_w - 36
        cx_y = sb_y + 7
        dpg.draw_rectangle((cx_x, cx_y), (cx_x + 24, cx_y + 24),
                           fill=lol_theme._alpha(lol_theme.LOL["navy_panel"], 185),
                           color=lol_theme.LOL["red_side"],
                           thickness=1, rounding=3, parent=dl)
        _txt(dl, cx_x + 7, cx_y + 4, "X",
             (*lol_theme.LOL["red_side"][:3], 230), 16, "raj_sb_16")
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

    # Stash region for the wheel-scroll consumer below.
    _pool_rect = (sb_x, gy0, sb_x + sb_w, grid_bottom)

    # Consume mouse-wheel delta (registered globally by ui.tierlist) when the
    # cursor is over the pool grid. wheel up = +delta = scroll toward top.
    if _wheel_delta_shared[0] != 0:
        mx, my = _mouse_xy
        if (sb_x <= mx <= sb_x + sb_w and gy0 <= my <= grid_bottom):
            draft.board_pool_scroll = max(0, min(
                draft.board_pool_scroll - int(_wheel_delta_shared[0]),
                max_scroll))
        # Always clear so deltas don't accumulate while we're on this tab.
        _wheel_delta_shared[0] = 0

    if not filtered:
        _txt(dl, sb_x + 14, gy0 + 12,
             f"No champions match  '{draft.board_pool_search}'",
             (*lol_theme.LOL["txt_dim"][:3], 200), 14, "raj_sb_14")
        return

    start = draft.board_pool_scroll * gx_n
    end = start + visible_rows * gx_n
    for k_rel, (cmp_, role) in enumerate(filtered[start:end]):
        gx = sb_x + (k_rel % gx_n) * gw
        gy = gy0 + (k_rel // gx_n) * gh
        cell_hover = _hover(gx + 2, gy + 2, gw - 4, gh - 4)
        cell_fill_a = 225 if cell_hover else 165
        dpg.draw_rectangle((gx + 2, gy + 2),
                           (gx + gw - 4, gy + gh - 4),
                           fill=lol_theme._alpha(
                               lol_theme.LOL["navy_deep"], cell_fill_a),
                           color=(lol_theme.LOL["gold"]
                                  if cell_hover
                                  else lol_theme._alpha(
                                      lol_theme.LOL["gold_rule"], 180)),
                           thickness=2 if cell_hover else 1,
                           rounding=3, parent=dl)
        _txt(dl, gx + 9, gy + 8, cmp_[:12],
             (*lol_theme.LOL["gold_lt"][:3], 248) if cell_hover
             else (*lol_theme.LOL["txt"][:3], 230),
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
                           fill=lol_theme._alpha(lol_theme.LOL["gold_rule"], 120),
                           color=(0, 0, 0, 0), rounding=2, parent=dl)
        thumb_frac = max(0.08, visible_rows / max(total_rows, 1))
        thumb_h = max(22, int(track_h * thumb_frac))
        thumb_pos = int((draft.board_pool_scroll / max_scroll)
                        * (track_h - thumb_h))
        dpg.draw_rectangle((sb_track_x,
                            sb_track_y0 + thumb_pos),
                           (sb_track_x + 4,
                            sb_track_y0 + thumb_pos + thumb_h),
                           fill=lol_theme._alpha(lol_theme.LOL["gold"], 215),
                           color=(0, 0, 0, 0), rounding=2, parent=dl)


def _enter_solo_briefing() -> None:
    """Phase 5 solo path: drop the synced session and jump locally into
    a one-shot BRIEFING preview. CONTINUE on that screen returns to IDLE
    (no synced draft, no archetype phase, no board sequence)."""
    # Mark solo so the briefing CONTINUE handler returns to IDLE instead
    # of trying to set_briefing_done on a closed websocket.
    draft.solo_mode = True
    # Build the board state from the team-builder roster so the briefing
    # has something to compute projected comps against. Reuses the same
    # local-only pipeline as the legacy solo BEGIN ANALYSIS path.
    try:
        _board_begin()
    except Exception:
        pass
    # Disconnect AFTER building the local board so we keep the lobby's
    # mirrored player list around long enough to compute the snapshot.
    _sync_ui.disconnect_if_active()
    draft.briefing_started_at = time.monotonic()
    draft.briefing_done_sent = False
    draft.briefing_data = _compute_briefing_data()
    draft.phase = DraftPhase.BRIEFING


def _briefing_handle_input(vw, vh):
    """Mouse input for the BRIEFING screen. Only thing clickable is the
    CONTINUE button which short-circuits the 5s auto-advance."""
    if not dpg.is_mouse_button_clicked(0):
        return
    mx, my = _content_mouse()
    for (hx, hy, hw, hh, kind, payload) in list(_board_hits):
        if not (hx <= mx <= hx + hw and hy <= my <= hy + hh):
            continue
        if kind == "briefing_continue" and not draft.briefing_done_sent:
            draft.briefing_done_sent = True
            if draft.solo_mode:
                draft.solo_mode = False
                draft.phase = DraftPhase.IDLE
                return
            try:
                _sync_ui.send_set_briefing_done(True)
            except Exception:
                pass
            return


def _archetype_handle_input(vw, vh):
    """Mouse input for the ARCHETYPE screen. Two click types:
       - archetype_pick: stage a pending selection (highlights the card)
       - archetype_confirm: send set_archetype to the server (locks it)"""
    mx, my = _content_mouse()
    # Hover update (visual lift) every frame
    draft.archetype_hover = None
    for (hx, hy, hw, hh, kind, payload) in list(_board_hits):
        if kind == "archetype_pick" and hx <= mx <= hx + hw and hy <= my <= hy + hh:
            draft.archetype_hover = payload
            break
    if not dpg.is_mouse_button_clicked(0):
        return
    for (hx, hy, hw, hh, kind, payload) in list(_board_hits):
        if not (hx <= mx <= hx + hw and hy <= my <= hy + hh):
            continue
        if kind == "archetype_pick":
            draft.archetype_pending = payload
            return
        if kind == "archetype_confirm":
            try:
                _sync_ui.send_set_archetype(payload)
            except Exception:
                pass
            try:
                _audio.play_archetype()
            except Exception:
                pass
            return


def _lobby_handle_input(vw, vh):
    """Mouse input for the synced draft lobby. Handles:
       - click on START DRAFT / EXIT (registered in _board_hits)
       - host-only drag-and-drop from pool to slot
       - host-only drag-out of slot to clear it"""
    mx, my = _content_mouse()
    _tb.drag_pos = (mx, my)

    client = None
    try:
        from data import draft_sync as _ds
        client = _ds.active()
    except Exception:
        pass
    is_host = bool((client.you() or {}).get("is_host")) if client else False

    # ── Click on START DRAFT / EXIT (button hits live in _board_hits) ──
    if dpg.is_mouse_button_clicked(0) and _tb.drag is None:
        for (hx, hy, hw, hh, kind, payload) in list(_board_hits):
            if hx <= mx <= hx + hw and hy <= my <= hy + hh:
                if kind == "start_draft":
                    _sync_ui.send_start_draft()
                    return
                if kind == "exit":
                    # v3.0.4: full reset on EXIT so re-entering BEGIN
                    # DRAFT lands in a clean state.
                    _sync_ui.disconnect_if_active()
                    _lobby_reset_pool()
                    draft.reset()
                    return
                if kind == "go_solo":
                    # Phase 5 solo fallback: disconnect from the synced
                    # lobby and jump straight to the local BRIEFING
                    # snapshot card. The user gets a strategic preview
                    # without waiting for an opponent.
                    _enter_solo_briefing()
                    return
                if kind == "swap_side":
                    # v3.0.2: click ⇄ to flip sides with the other player.
                    # Server-side `set_side` handles the swap atomically:
                    # if the target side is occupied, the two users trade
                    # places (no SPEC limbo). Both ready flags clear so
                    # they re-confirm.
                    try:
                        _sync_ui.send_set_side(payload)
                    except Exception:
                        pass
                    return

    if not is_host:
        return   # spectators / players don't get to drag the host's pool

    # ── Drag start: pool card or filled slot ──────────────────────────
    if dpg.is_mouse_button_down(0) and _tb.drag is None:
        for (hx, hy, hw, hh, kind, payload) in _lobby_hits:
            if not (hx <= mx <= hx + hw and hy <= my <= hy + hh):
                continue
            if kind == "lobby_pool":
                _tb.drag = dict(payload)        # copy so we don't mutate pool entry
                _tb.drag_from = ("lobby_pool",)
                return
            if kind == "lobby_slot":
                # Pick up the assigned player from this slot (if any).
                side, idx = payload
                snap = client.state() if client else None
                pl = None
                try:
                    pl = ((snap or {}).get("state") or {}) \
                        .get("players", {}).get(side, [])[idx]
                except (IndexError, TypeError, AttributeError):
                    pl = None
                # Only pick up if there's substantive assigned data (not just
                # the auto-populated display name from the join handshake).
                if isinstance(pl, dict) and pl.get("tier") \
                        and pl.get("tier") != "Unranked":
                    _tb.drag = dict(pl)
                    _tb.drag_from = ("lobby_slot", side, idx)
                    # Tentatively clear the slot on the server so the UI
                    # responds immediately; if the user drops it nowhere we
                    # restore in the drop branch below.
                    _sync_ui.send_set_slot_player(side, idx, {"name": "",
                                                              "tier": "Unranked",
                                                              "final_score": 50.0})
                return

    # ── Drag end: drop on a slot, or back where it came from ──────────
    if not dpg.is_mouse_button_down(0) and _tb.drag is not None:
        dropped = False
        for (hx, hy, hw, hh, kind, payload) in _lobby_hits:
            if kind != "lobby_slot":
                continue
            if hx <= mx <= hx + hw and hy <= my <= hy + hh:
                side, idx = payload
                _sync_ui.send_set_slot_player(side, idx, dict(_tb.drag))
                dropped = True
                break
        if not dropped and _tb.drag_from \
                and _tb.drag_from[0] == "lobby_slot":
            # Dropped outside — return to original slot (we'd cleared it on
            # pickup; restore now).
            _, side, idx = _tb.drag_from
            _sync_ui.send_set_slot_player(side, idx, dict(_tb.drag))
        _tb.drag = None
        _tb.drag_from = None


def _board_handle_input(vw, vh):
    # Lobby short-circuit: when synced and host hasn't pressed START yet,
    # the board input rules don't apply (no pick/ban, just drag-and-drop +
    # the START / EXIT buttons).
    if _sync_ui.in_lobby():
        _lobby_handle_input(vw, vh)
        return

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
    mx, my = _content_mouse()

    # ── Pick-drag: move a locked champion between role slots ─────────
    # Synced sessions: only the host may reassign (server enforces this);
    # non-hosts and spectators get no-op drag. Live LCU poll: disabled
    # (the live feed is authoritative, manual reassign would desync).
    _pdrag.pos = (mx, my)
    mb_down = dpg.is_mouse_button_down(0)
    is_synced = _sync_ui.is_active()
    drag_disabled = is_synced and not _sync_ui.is_host()
    if drag_disabled:
        _pdrag.side = None
        _pdrag.from_role = None
        _pdrag.champ = None
    elif _pdrag.side is None:
        # Not dragging — start on mouse-down over a filled slot.
        if mb_down and not _pdrag.was_down:
            for (rx, ry_, rw, rh, side, role, champ) in _pick_slot_rects:
                if champ and rx <= mx <= rx + rw and ry_ <= my <= ry_ + rh:
                    _pdrag.side = side
                    _pdrag.from_role = role
                    _pdrag.champ = champ
                    break
    else:
        # Currently dragging — drop on release.
        if not mb_down:
            target_role = None
            for (rx, ry_, rw, rh, side, role, _c) in _pick_slot_rects:
                if (side == _pdrag.side and role != _pdrag.from_role
                        and rx <= mx <= rx + rw and ry_ <= my <= ry_ + rh):
                    target_role = role
                    break
            if target_role and draft.board is not None:
                # Synced: route through server, which will broadcast back via
                # sync_tick. Local: mutate directly and recompute.
                if _sync_ui.route_reassign(draft, _pdrag.side,
                                           _pdrag.from_role, target_role):
                    pass
                elif draft.board.reassign(_pdrag.side, _pdrag.from_role,
                                          target_role):
                    _board_recompute()
            _pdrag.side = None
            _pdrag.from_role = None
            _pdrag.champ = None
    _pdrag.was_down = mb_down

    # If a drag just started this frame, swallow the click so it doesn't
    # also trigger any underlying hit rect (e.g. the manual pool grid).
    if _pdrag.side is not None:
        return

    if not dpg.is_mouse_button_clicked(0):
        return
    for (hx, hy, hw, hh, kind, payload) in list(_board_hits):
        if hx <= mx <= hx + hw and hy <= my <= hy + hh:
            if kind == "start_draft":
                _sync_ui.send_start_draft()
            elif kind == "exit":
                # v3.0.4: full state wipe on EXIT so a subsequent BEGIN
                # DRAFT starts clean (no stale board, no carried-over
                # archetype pending, no half-fetched scout sheets, etc.).
                # Without this, the next session would inherit the old
                # board.picks / board.bans and the engine would still
                # think those champions are locked.
                _sync_ui.disconnect_if_active()
                _lobby_reset_pool()
                draft.reset()
            elif kind == "undo":
                # Synced: host-only on the server side; route and let mirror
                # update the board on broadcast.
                if _sync_ui.route_undo(draft):
                    draft.board_pool_scroll = 0
                    draft.board_pool_search = ""
                elif draft.board and draft.board.undo():
                    draft.board_pool_scroll = 0
                    draft.board_pool_search = ""
                    _board_recompute()
            elif kind == "new":
                # v3.0.4: same full reset as EXIT — DONE-screen NEW DRAFT
                # should be indistinguishable from a fresh launch.
                _sync_ui.disconnect_if_active()
                _lobby_reset_pool()
                draft.reset()
            elif kind == "clear_search":
                draft.board_pool_search = ""
                draft.board_pool_scroll = 0
            elif kind == "set_arch":
                # Toggle: clicking the active chip reverts to AUTO (None).
                new_arch = payload   # None for AUTO, else archetype name
                if draft.board_target_arch == new_arch:
                    draft.board_target_arch = None
                else:
                    draft.board_target_arch = new_arch
                _board_recompute()
            elif kind == "pivot_to" and payload:
                # User clicked one of the pivot-alert banner buttons. Commit
                # the new archetype as the local target + sync it to the
                # server (so the engine pivots its recommendations).
                draft.board_target_arch = payload
                try:
                    _sync_ui.send_set_archetype(payload)
                except Exception:
                    pass
                # Force a recompute + invalidate the cached pivot result so
                # the banner re-evaluates against the new archetype.
                draft._pivot_last_sig = None
                _board_recompute()
            elif kind == "pick" and payload:
                # In sync mode the server enforces side-authorization, but
                # short-circuit here so spectators / off-turn players don't
                # see flashing rejections.
                if not _sync_ui.can_act(draft):
                    return
                _board_apply(payload[0], payload[1])
            return


# ---------------------------------------------------------------------------
# Main draw entry
# (Phase 6: the legacy `_apply_prediction` / `_kick_off_bg_draft` /
# `_apply_draft_results` background-write pipeline was deleted along with the
# War Room phases — none of it survived the cutover to the synced lobby +
# BRIEFING flow.)
# ---------------------------------------------------------------------------

def _sync_phase_watcher() -> None:
    """Phase 4: keep local DraftPhase in sync with the server's phase
    machine. Called once per frame from draw_draft.

    Server phase   →   Local action
    ─────────────────  ─────────────────────────────────────────────────────
    LOBBY              TEAM_BUILD render (already handled by join callback)
    SCOUTING           local phase ← SCOUTING; kick scout-prefetch once
    BRIEFING           local phase ← BRIEFING; cache briefing_data once
    ARCHETYPE          local phase ← ARCHETYPE
    BOARD / DONE       _board_begin_synced (drops the lobby UI)
    (disconnected)     no change — solo flow remains valid
    """
    if not _sync_ui.is_active():
        return
    sp = _sync_ui.server_phase()
    if sp is None:
        return

    # SCOUTING — server says "fetch scout data". Transition local phase
    # and kick the background fetch the first time we see this.
    if sp == "SCOUTING":
        if draft.phase != DraftPhase.SCOUTING:
            draft.phase = DraftPhase.SCOUTING
        _maybe_start_scout_prefetch()
        _maybe_send_scout_ready()
        return

    # v4.0.3: BRIEFING is now skipped. The team-comp overview was redundant
    # with the archetype picker that immediately follows it. We auto-ack the
    # briefing the moment the server enters that phase, so the user goes
    # straight from SCOUTING to ARCHETYPE.
    if sp == "BRIEFING":
        if not draft.briefing_done_sent:
            draft.briefing_done_sent = True
            try:
                _sync_ui.send_set_briefing_done(True)
            except Exception:
                pass
        return

    # ARCHETYPE — show the 7-card hidden picker for OUR side.
    if sp == "ARCHETYPE":
        if draft.phase != DraftPhase.ARCHETYPE:
            draft.phase = DraftPhase.ARCHETYPE
            # Reset any local pending selection from a prior round
            draft.archetype_pending = None
            draft.archetype_hover = None
        return

    if sp in ("BOARD", "DONE") and draft.phase in (
        DraftPhase.TEAM_BUILD, DraftPhase.SCOUTING,
        DraftPhase.BRIEFING, DraftPhase.ARCHETYPE,
    ):
        # Server says draft has started — drop the lobby UI and enter the
        # board view. Engine recompute happens inside _board_begin_synced.
        _board_begin_synced()


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

    # Phase 1: if synced, watch the server's phase machine and transition
    # the local phase in lock-step. The server advances LOBBY→BOARD once
    # both sides ready; the local UI must follow.
    _sync_phase_watcher()

    phase = draft.phase

    if phase == DraftPhase.IDLE:
        _draw_idle(dl, vw, vh)
        return

    if phase == DraftPhase.CONNECTING:
        _draw_connecting(dl, vw, vh)
        return

    if phase == DraftPhase.TEAM_BUILD:
        # v3.0.2 fix: in a synced LOBBY the team-builder UI needs to be
        # the server-authoritative one (_draw_sync_lobby + _lobby_handle_input),
        # not the solo _tb-state one. The solo builder only broadcasts side
        # toggles, so drag-drop changes never reached the other client and
        # the rosters appeared to "reset" on READY because they were never
        # mirrored into draft.board.players in the first place.
        if _sync_ui.in_lobby():
            _draw_sync_lobby(dl, vw, vh)
            _lobby_handle_input(vw, vh)
            return
        _draw_team_builder_full(dl, vw, vh)
        _tb_handle_input(vw, vh)
        return

    # Phase 4 — synced lobby flow: SCOUTING / BRIEFING / ARCHETYPE.
    # Server drives transitions; _sync_phase_watcher kicks the local
    # rendering. Click handlers added below for BRIEFING/ARCHETYPE.
    if phase == DraftPhase.SCOUTING:
        _board_hits.clear()
        _draw_scouting(dl, vw, vh)
        return
    if phase == DraftPhase.BRIEFING:
        _board_hits.clear()
        _draw_briefing(dl, vw, vh)
        _briefing_handle_input(vw, vh)
        return
    if phase == DraftPhase.ARCHETYPE:
        _draw_archetype(dl, vw, vh)
        _archetype_handle_input(vw, vh)
        return

    if phase == DraftPhase.BOARD:
        _draw_board(dl, vw, vh)
        _board_handle_input(vw, vh)
        return

    # Phase 6: the legacy ASSEMBLING / ANALYSING / RESULTS "War Room"
    # fallback was removed. Anything not matched above means the local
    # phase desynced — recover by bouncing back to IDLE.
    draft.phase = DraftPhase.IDLE


# Cycling hero splash for the IDLE landing — pick a striking champion based
# on the day-of-year so the splash refreshes daily without flickering between
# sessions. Adds personality without distraction.
_IDLE_HERO_ROTATION = [
    "Aatrox", "Yone", "Akali", "Sett", "Jhin", "Vayne", "Ahri", "Camille",
    "Lee Sin", "Riven", "Irelia", "Ekko", "Ezreal", "Sylas",
]


def _idle_hero_splash() -> str:
    return _IDLE_HERO_ROTATION[
        int(time.time() // 86400) % len(_IDLE_HERO_ROTATION)]


def _draw_idle(dl, vw, vh):
    """LCS/LEC broadcast-style landing (Phase 3 rewrite).

    Full-bleed champion splash backdrop with darkening gradient; the single
    BEGIN DRAFT button + RE-ANALYSE-PREVIOUS link sit centered on a navy
    panel that floats over the splash. One click on BEGIN DRAFT auto-connects
    to the Fly.io sync server and transitions to CONNECTING, then LOBBY.
    """
    cx = vw // 2

    # --- Full-bleed splash backdrop ---
    lol_theme.draw_splash_banner(
        dl, 0, 0, vw, vh,
        champion=_idle_hero_splash(),
        darken=200,
        accent_side=None,
    )

    # --- Title + subtitle ---
    t = (math.sin(time.monotonic() * 1.2) + 1) / 2
    title_a = int(180 + t * 70)
    _txt(dl, cx - 188, vh // 2 - 180, "DRAFT WAR ROOM",
         (*lol_theme.LOL["gold_lt"][:3], title_a), 44, "cinzel_44")
    _txt(dl, cx - 220, vh // 2 - 128,
         "Connect, build teams, draft together.",
         (*lol_theme.LOL["txt_dim"][:3], 200), 21, "raj_20")

    rx, ry = _content_mouse()

    # --- BEGIN DRAFT — single large primary button ---
    bw, bh = 380, 84
    bx = cx - bw // 2
    by = vh // 2 - bh // 2
    hot_begin = bx <= rx <= bx + bw and by <= ry <= by + bh

    # Halo on hover (focal motion).
    if hot_begin:
        glow = int(160 + 60 * t)
        dpg.draw_rectangle((bx - 6, by - 6), (bx + bw + 6, by + bh + 6),
                           fill=(*lol_theme.LOL["gold"][:3], 18),
                           color=(*lol_theme.LOL["gold"][:3], glow),
                           rounding=10, parent=dl)

    lol_theme.draw_navy_panel(
        dl, bx, by, bx + bw, by + bh,
        fill=lol_theme._alpha(lol_theme.LOL["navy_panel"],
                              240 if hot_begin else 215),
        border_color=lol_theme.LOL["gold"]
            if hot_begin else lol_theme.LOL["gold_rule"],
        border_thickness=2,
        rounding=8,
    )
    _txt(dl, bx + 30, by + 22, "BEGIN DRAFT",
         (*lol_theme.LOL["gold_lt"][:3], 240), 38, "cinzel_36")
    _txt(dl, bx + 32, by + bh - 22,
         "auto-syncs with whoever else is here",
         (*lol_theme.LOL["txt_dim"][:3], 220 if hot_begin else 160),
         13, "raj_sb_12")

    # (Phase 6 removed the legacy "RE-ANALYSE PREVIOUS DRAFT" link — the
    # batch-analysis path was retired together with the War Room phases.)

    # --- Connection status hint (only if there's an interesting state) ---
    status = _sync_ui.connection_status()
    if status and status != "synced":
        _txt(dl, cx - 200, by + bh + 60,
             status, (*lol_theme.LOL["txt_dim"][:3], 200), 14, "raj_r_14")

    # --- Input handling ---
    if dpg.is_mouse_button_clicked(0):
        if hot_begin:
            draft.phase = DraftPhase.CONNECTING
            try:
                _sync_ui.auto_connect()
            except Exception:
                draft.phase = DraftPhase.IDLE
            return


def _draw_connecting(dl, vw, vh):
    """Phase 1 waiting screen — shown between IDLE and TEAM_BUILD while we
    wait for the Fly.io server's hello. Cold-start can take ~1-2s on a
    suspended VM; this screen also covers reconnect attempts."""
    status = _sync_ui.connection_status()
    if status == "synced":
        # First snapshot arrived; transition handled by the join callback.
        # Render a stable frame so we don't flash IDLE between the snapshot
        # arriving and the callback firing.
        headline = "Connected — entering lobby…"
        subtitle = None
        progress = 1.0
    elif status.startswith("could not connect"):
        headline = "Could not connect to the server"
        subtitle = status.replace("could not connect: ", "")
        progress = None
    elif status == "":
        # Not synced and no client active — something raced. Bounce back.
        draft.phase = DraftPhase.IDLE
        return
    else:
        headline = "Connecting to The Rift Server…"
        subtitle = status if status not in (
            "connecting to the server…", "synced") else None
        progress = None

    lol_theme.draw_waiting_screen(
        dl, vw, vh,
        status_text=headline,
        subtitle=subtitle,
        progress_0_1=progress,
    )

    # Cancel link — bottom of screen, click to drop the connection.
    cx = vw // 2
    cw, ch = 140, 32
    cxx = cx - cw // 2
    cyy = vh - 60
    rx, ry = _content_mouse()
    hot = cxx <= rx <= cxx + cw and cyy <= ry <= cyy + ch
    dpg.draw_rectangle((cxx, cyy), (cxx + cw, cyy + ch),
                       fill=(0, 0, 0, 0),
                       color=(*C["txt2"][:3], 180 if hot else 120),
                       rounding=4, parent=dl)
    _txt(dl, cxx + 32, cyy + 8, "CANCEL",
         (*C["txt2"][:3], 220 if hot else 160), 16, "raj_sb_14")
    if hot and dpg.is_mouse_button_clicked(0):
        _sync_ui.disconnect_if_active()
        draft.phase = DraftPhase.IDLE

# ---------------------------------------------------------------------------
# Phase 6: every helper from _draw_team_area to _draw_red_panel was deleted
# (the legacy War Room render path). The synced LOBBY → SCOUTING → BRIEFING →
# ARCHETYPE → BOARD → DONE flow + the solo-briefing fallback cover everything
# they did. ~1100 lines of dead code removed.
# ---------------------------------------------------------------------------
