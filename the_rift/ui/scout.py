"""
Scout Tab — Phase 4.
Left: sortable player table.  Right: score history graph.
Click a player NAME → opens full scouting report overlay window (scrollable DPG widgets).

Report sections (mirrors old launcher):
  Header · Power Rating · Overview Stats · Recent Form + Match History
  Ban Targets · Champion Pool · Role Breakdown · In-House Customs
"""
import math, time
import dearpygui.dearpygui as dpg
from theme import C, RANK_COLORS
from core.animations import anim

# ---------------------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------------------
_DEMO_PLAYERS = [
    {"name":"Phantom",  "tier":"Challenger",  "score":2840,"wr":67,"kda":4.2,"games":84,"top_champs":["Zed","Akali","Talon"]},
    {"name":"Ironclad", "tier":"Grandmaster", "score":2710,"wr":63,"kda":3.8,"games":91,"top_champs":["Vi","Hecarim","Graves"]},
    {"name":"Vex",      "tier":"Master",      "score":2590,"wr":61,"kda":3.5,"games":76,"top_champs":["Lux","Orianna","Syndra"]},
    {"name":"Shroud",   "tier":"Diamond",     "score":2440,"wr":58,"kda":3.1,"games":102,"top_champs":["Garen","Darius","Malphite"]},
    {"name":"Blaze",    "tier":"Diamond",     "score":2310,"wr":55,"kda":2.9,"games":88,"top_champs":["Lee Sin","Elise","Nidalee"]},
    {"name":"Kira",     "tier":"Emerald",     "score":2180,"wr":54,"kda":2.7,"games":73,"top_champs":["Jinx","Caitlyn","Jhin"]},
    {"name":"Dusk",     "tier":"Emerald",     "score":2050,"wr":52,"kda":2.5,"games":67,"top_champs":["Thresh","Lulu","Nautilus"]},
    {"name":"Nox",      "tier":"Platinum",    "score":1920,"wr":50,"kda":2.3,"games":95,"top_champs":["Zed","Yasuo","Yone"]},
    {"name":"Cinder",   "tier":"Platinum",    "score":1800,"wr":49,"kda":2.2,"games":81,"top_champs":["Jhin","Ezreal","Varus"]},
    {"name":"Riven",    "tier":"Gold",        "score":1670,"wr":47,"kda":2.0,"games":60,"top_champs":["Riven","Fiora","Camille"]},
    {"name":"Ember",    "tier":"Gold",        "score":1540,"wr":46,"kda":1.9,"games":55,"top_champs":["Annie","Veigar","Lux"]},
    {"name":"Lyra",     "tier":"Silver",      "score":1410,"wr":45,"kda":1.8,"games":48,"top_champs":["Sona","Soraka","Janna"]},
    {"name":"Torque",   "tier":"Silver",      "score":1290,"wr":44,"kda":1.7,"games":42,"top_champs":["Amumu","Malphite","Leona"]},
    {"name":"Flux",     "tier":"Bronze",      "score":1160,"wr":42,"kda":1.5,"games":38,"top_champs":["Garen","Ashe","Annie"]},
    {"name":"Zeal",     "tier":"Bronze",      "score":1040,"wr":40,"kda":1.4,"games":34,"top_champs":["Nasus","Tristana","Miss Fortune"]},
]
_BY_NAME = {p["name"]: p for p in _DEMO_PLAYERS}

import random as _rnd
_rnd.seed(42)
_SCORE_HISTORY = {
    p["name"]: [max(200, p["score"] + _rnd.randint(-280, 280)) for _ in range(10)]
    for p in _DEMO_PLAYERS
}

# Per-player extended demo scout data
def _make_report(p):
    n    = p["name"]
    sc   = p["score"]
    wr   = p["wr"]
    kda  = p["kda"]
    tier = p["tier"]
    form = "HOT" if wr >= 55 else "COLD" if wr < 47 else "MIXED"
    tier_score = max(0, sc - 400)
    rank_score = min(sc, 400)
    rating_letter = "S" if sc>=2700 else "A" if sc>=2300 else "B" if sc>=1900 else "C" if sc>=1500 else "D"
    champs = p["top_champs"]
    return {
        "player": n, "tier": tier, "score": sc,
        "power_position": str(_DEMO_PLAYERS.index(p)+1),
        "rating_letter": rating_letter,
        "tier_score": tier_score, "rank_score": rank_score,
        "overview": [
            ("KDA",       f"{kda:.1f}"), ("Win Rate",  f"{wr}%"),
            ("Avg Kills", f"{kda*2.1:.1f}"), ("Avg Deaths", f"{kda*0.9:.1f}"),
            ("Avg Assists",f"{kda*3.2:.1f}"),("CS/min",  f"{6.2+_rnd.uniform(-1,1):.1f}"),
            ("Avg Dmg",   f"{12000+_rnd.randint(-3000,5000):,}"),
            ("Vision/G",  f"{_rnd.uniform(0.8,2.2):.1f}"),
        ],
        "form": form,
        "matches": [
            {"game": i+1, "result": "WIN" if _rnd.random()<wr/100 else "LOSS",
             "champion": champs[i%len(champs)], "role": ["TOP","JGL","MID","BOT","SUP"][i%5],
             "kda_str": f"{_rnd.randint(2,12)}/{_rnd.randint(1,8)}/{_rnd.randint(1,14)}",
             "kda": round(kda + _rnd.uniform(-1,1), 1),
             "cs_min": round(6.0+_rnd.uniform(-1.5,2.0),1),
             "damage": _rnd.randint(8000,28000),
             "duration": f"{_rnd.randint(22,45)}m"}
            for i in range(10)
        ],
        "ban_targets": [
            {"name": champs[0], "games": p["games"]//3, "wr": min(99,wr+12), "kda": round(kda+0.8,1), "cs_min":6.8, "threat":"PERMABAN"},
            {"name": champs[1], "games": p["games"]//4, "wr": min(99,wr+6),  "kda": round(kda+0.3,1), "cs_min":6.2, "threat":"HIGH"},
        ] if wr >= 50 else [],
        "champ_pool": [
            {"name": ch, "games": max(5,p["games"]//(i+2)),
             "wins":  max(2,int(p["games"]//(i+2)*wr/100)),
             "losses":max(1,int(p["games"]//(i+2)*(100-wr)/100)),
             "wr": wr+_rnd.randint(-8,8), "kda":round(kda+_rnd.uniform(-0.5,0.8),1),
             "cs_min":round(5.8+_rnd.uniform(-1,1.5),1),
             "damage": _rnd.randint(9000,25000)}
            for i, ch in enumerate(champs)
        ],
        "roles": [
            {"role":"MID",  "games":p["games"]//2, "pct":50, "top_champs":champs},
            {"role":"TOP",  "games":p["games"]//4, "pct":25, "top_champs":[champs[0]]},
            {"role":"JGL",  "games":p["games"]//4, "pct":25, "top_champs":[champs[-1]]},
        ],
        "inhouse_champs": [
            {"name": ch, "games":_rnd.randint(3,12),
             "wins":_rnd.randint(1,8), "losses":_rnd.randint(1,6),
             "wr":_rnd.randint(40,75), "kda":round(kda+_rnd.uniform(-0.5,0.5),1),
             "damage":_rnd.randint(9000,22000)}
            for ch in champs
        ],
        "scouted_days_ago": _rnd.randint(0,10),
    }

_DEMO_REPORTS = {p["name"]: _make_report(p) for p in _DEMO_PLAYERS}

# ---------------------------------------------------------------------------
# Scout report window
# ---------------------------------------------------------------------------
_REPORT_WIN = "scout_report_win"

def _build_live_report(name):
    """Build a minimal report dict from live scout data when demo data is absent."""
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
    try:
        ts = float(p.get("tier_score") or 0)
        rs = float(p.get("rank_score") or score)
    except (ValueError, TypeError):
        ts, rs = 0.0, float(score) if score else 0.0
    rank = next((i+1 for i, x in enumerate(scout.players) if x["name"] == name), 0)
    return {
        "player":           name,
        "tier":             tier,
        "score":            score,
        "power_position":   str(rank),
        "rating_letter":    rating,
        "tier_score":       ts,
        "rank_score":       rs,
        "scouted_days_ago": 0,
        "overview": [
            ("Win Rate",   f"{wr}%"),
            ("KDA",        f"{kda:.1f}"),
            ("Games",      str(games)),
            ("Form",       form),
        ],
        "form":         form,
        "matches":      [],
        "ban_targets":  [],
        "top_champs":   p.get("top_champs", []),
        "roles":        [],
        "inhouse_games": [],
    }


def _open_report(name, vw, vh):
    if dpg.does_item_exist(_REPORT_WIN):
        dpg.delete_item(_REPORT_WIN)
    r = _DEMO_REPORTS.get(name) or _build_live_report(name)
    if not r:
        return

    rw = min(860, vw - 160)
    rh = vh - 80
    rx = 68 + (vw - rw) // 2
    ry = 52 + 40

    with dpg.window(tag=_REPORT_WIN, pos=(rx, ry),
                    width=rw, height=rh, label="Scout Report",
                    no_title_bar=False, no_resize=True, no_move=False):

        _rw_header(r, rw)
        dpg.add_separator()
        _rw_power_rating(r)
        dpg.add_separator()
        _rw_overview(r)
        dpg.add_separator()
        _rw_form(r)
        dpg.add_separator()
        _rw_ban_targets(r)
        dpg.add_separator()
        _rw_champ_pool(r)
        dpg.add_separator()
        _rw_roles(r)
        dpg.add_separator()
        _rw_inhouse(r)
        dpg.add_spacer(height=24)


def _rw_label(text, font_key="raj_sb_18", color=None):
    t = dpg.add_text(text, color=color or C["gold"][:3])
    if font_key in _F:
        dpg.bind_item_font(t, _F[font_key])


def _rw_header(r, rw):
    dpg.add_spacer(height=8)
    with dpg.group(horizontal=True):
        dpg.add_spacer(width=12)
        with dpg.group():
            t = dpg.add_text(r["player"].upper())
            if "raj_36" in _F: dpg.bind_item_font(t, _F["raj_36"])
            with dpg.group(horizontal=True):
                t2 = dpg.add_text(r["tier"].upper())
                bc = RANK_COLORS.get(r["tier"], RANK_COLORS["Unranked"])
                dpg.configure_item(t2, color=bc[:3])
                if "raj_sb_18" in _F: dpg.bind_item_font(t2, _F["raj_sb_18"])
                dpg.add_spacer(width=16)
                days = r.get("scouted_days_ago", None)
                if days is not None:
                    age_col = (79,168,130) if days<=2 else (200,168,106) if days<=6 else (184,69,53)
                    ta = dpg.add_text(f"  Scouted {days}d ago", color=age_col)
                else:
                    ta = dpg.add_text("  Live data", color=(79,168,130))
                if "raj_r_14" in _F: dpg.bind_item_font(ta, _F["raj_r_14"])
    dpg.add_spacer(height=8)


def _rw_power_rating(r):
    dpg.add_spacer(height=6)
    _rw_label("POWER RATING")
    dpg.add_spacer(height=6)
    rating_colors = {
        "S":(200,70,60),"A":(200,155,60),"B":(160,136,78),
        "C":(92,138,92),"D":(92,122,156),"F":(110,110,110),
    }
    rc = rating_colors.get(r["rating_letter"], (120,120,120))
    with dpg.group(horizontal=True):
        dpg.add_spacer(width=12)
        with dpg.group():
            t = dpg.add_text(f"  #{r['power_position']}  ", color=C["gold"][:3])
            if "raj_28" in _F: dpg.bind_item_font(t, _F["raj_28"])
        dpg.add_spacer(width=16)
        with dpg.group():
            t = dpg.add_text(f"  {r['rating_letter']}  ", color=rc)
            if "raj_44" in _F: dpg.bind_item_font(t, _F["raj_44"])
        dpg.add_spacer(width=16)
        with dpg.group():
            dpg.add_spacer(height=4)
            t = dpg.add_text(f"Score: {r['score']}", color=C["gold_lt"][:3])
            if "raj_24" in _F: dpg.bind_item_font(t, _F["raj_24"])
            t2 = dpg.add_text(f"Tier score: {r['tier_score']}  (60%)   Rank score: {r['rank_score']}  (40%)",
                               color=C["txt2"][:3])
            if "raj_r_14" in _F: dpg.bind_item_font(t2, _F["raj_r_14"])
    dpg.add_spacer(height=6)


def _rw_overview(r):
    dpg.add_spacer(height=6)
    _rw_label("OVERVIEW STATS")
    dpg.add_spacer(height=8)
    stats = r["overview"]
    cols  = 4
    for row_start in range(0, len(stats), cols):
        with dpg.group(horizontal=True):
            dpg.add_spacer(width=32)
            for lbl, val in stats[row_start:row_start+cols]:
                with dpg.child_window(width=175, height=82, border=True,
                                      no_scrollbar=True, no_scroll_with_mouse=True):
                    dpg.add_spacer(height=6)
                    with dpg.group(horizontal=False):
                        lt = dpg.add_text(lbl, color=C["txt_dim"][:3])
                        if "raj_sb_14" in _F: dpg.bind_item_font(lt, _F["raj_sb_14"])
                        dpg.add_spacer(height=2)
                        vt = dpg.add_text(val, color=C["txt"][:3])
                        if "raj_20" in _F: dpg.bind_item_font(vt, _F["raj_20"])
                dpg.add_spacer(width=8)
        dpg.add_spacer(height=8)


def _rw_form(r):
    dpg.add_spacer(height=6)
    form = r["form"]
    form_cols = {"HOT":(79,168,130),"COLD":(184,69,53),"MIXED":(200,168,106)}
    fc = form_cols.get(form, C["txt"][:3])
    _rw_label(f"RECENT FORM: {form}", color=fc)
    dpg.add_spacer(height=6)

    # Header row
    hdrs = ["#","RESULT","CHAMPION","ROLE","K/D/A","KDA","CS/M","DMG","TIME"]
    with dpg.group(horizontal=True):
        dpg.add_spacer(width=12)
        for h in hdrs:
            t = dpg.add_text(f"{h:<10}", color=C["txt_dim"][:3])
            if "raj_sb_14" in _F: dpg.bind_item_font(t, _F["raj_sb_14"])
    dpg.add_separator()

    if not r.get("matches"):
        dpg.add_text("  Match history not available for this player.",
                     color=C["txt_dim"][:3])
        dpg.add_spacer(height=6)
        return

    for m in r["matches"]:
        win    = m["result"] == "WIN"
        rc     = (79,168,130) if win else (184,69,53)
        fields = [str(m["game"]), m["result"], m["champion"], m["role"],
                  m["kda_str"], str(m["kda"]), str(m["cs_min"]),
                  f"{m['damage']:,}", m["duration"]]
        with dpg.group(horizontal=True):
            dpg.add_spacer(width=12)
            for i, f2 in enumerate(fields):
                col = rc if i == 1 else C["txt"][:3]
                t = dpg.add_text(f"{f2:<10}", color=col)
                if "raj_r_14" in _F: dpg.bind_item_font(t, _F["raj_r_14"])
    dpg.add_spacer(height=6)


def _rw_ban_targets(r):
    dpg.add_spacer(height=6)
    _rw_label("BAN TARGETS")
    dpg.add_spacer(height=6)
    bans = r.get("ban_targets",[])
    if not bans:
        t = dpg.add_text("  No high-threat champions identified (criteria: 5+ games, 65%+ WR)",
                         color=C["win"][:3])
        if "raj_r_14" in _F: dpg.bind_item_font(t, _F["raj_r_14"])
        dpg.add_spacer(height=6)
        return

    hdrs = ["CHAMPION","GAMES","W/R","KDA","CS/M","THREAT"]
    with dpg.group(horizontal=True):
        dpg.add_spacer(width=12)
        for h in hdrs:
            t = dpg.add_text(f"{h:<14}", color=C["txt_dim"][:3])
            if "raj_sb_14" in _F: dpg.bind_item_font(t, _F["raj_sb_14"])
    dpg.add_separator()

    threat_col = {"PERMABAN":(200,70,60),"HIGH":(200,155,60),"ELEVATED":(160,136,78)}
    for b in bans:
        tc = threat_col.get(b["threat"],(120,120,120))
        vals = [b["name"], str(b["games"]), f"{b['wr']}%",
                str(b["kda"]), str(b["cs_min"]), b["threat"]]
        with dpg.group(horizontal=True):
            dpg.add_spacer(width=12)
            for i, v in enumerate(vals):
                col = tc if i == 5 else C["loss"][:3] if i==0 else C["txt"][:3]
                t = dpg.add_text(f"{v:<14}", color=col)
                if "raj_r_14" in _F: dpg.bind_item_font(t, _F["raj_r_14"])
    dpg.add_spacer(height=6)


def _rw_champ_pool(r):
    dpg.add_spacer(height=6)
    pool = r.get("champ_pool",[])
    _rw_label(f"CHAMPION POOL · {len(pool)}")
    dpg.add_spacer(height=6)
    hdrs = ["CHAMPION","GAMES","W-L","W/R","KDA","CS/M","DMG"]
    with dpg.group(horizontal=True):
        dpg.add_spacer(width=12)
        for h in hdrs:
            t = dpg.add_text(f"{h:<13}", color=C["txt_dim"][:3])
            if "raj_sb_14" in _F: dpg.bind_item_font(t, _F["raj_sb_14"])
    dpg.add_separator()
    for ch in pool:
        wr  = ch["wr"]
        nc  = C["win"][:3] if wr>=60 else C["loss"][:3] if wr<45 else C["gold"][:3]
        wl  = f"{ch['wins']}-{ch['losses']}"
        vals = [ch["name"], str(ch["games"]), wl,
                f"{wr}%", str(ch["kda"]), str(ch["cs_min"]), f"{ch['damage']:,}"]
        with dpg.group(horizontal=True):
            dpg.add_spacer(width=12)
            for i, v in enumerate(vals):
                col = nc if i==0 else C["txt"][:3]
                t = dpg.add_text(f"{v:<13}", color=col)
                if "raj_r_14" in _F: dpg.bind_item_font(t, _F["raj_r_14"])
    dpg.add_spacer(height=6)


def _rw_roles(r):
    dpg.add_spacer(height=6)
    _rw_label("ROLE BREAKDOWN")
    dpg.add_spacer(height=6)
    hdrs = ["ROLE","GAMES","SHARE","TOP CHAMPIONS"]
    with dpg.group(horizontal=True):
        dpg.add_spacer(width=12)
        for h in hdrs:
            t = dpg.add_text(f"{h:<18}", color=C["txt_dim"][:3])
            if "raj_sb_14" in _F: dpg.bind_item_font(t, _F["raj_sb_14"])
    dpg.add_separator()
    for i, role in enumerate(r.get("roles",[])):
        col = C["gold"][:3] if i == 0 else C["txt"][:3]
        vals = [role["role"], str(role["games"]), f"{role['pct']}%",
                ", ".join(role.get("top_champs",[])[:3])]
        with dpg.group(horizontal=True):
            dpg.add_spacer(width=12)
            for v in vals:
                t = dpg.add_text(f"{v:<18}", color=col)
                if "raj_r_14" in _F: dpg.bind_item_font(t, _F["raj_r_14"])
    dpg.add_spacer(height=6)


def _rw_inhouse(r):
    dpg.add_spacer(height=6)
    _rw_label("IN-HOUSE CUSTOM GAMES", color=(*C["rift_purple"][:3],))
    dpg.add_spacer(height=6)
    hdrs = ["CHAMPION","GAMES","W-L","W/R","KDA","DMG"]
    with dpg.group(horizontal=True):
        dpg.add_spacer(width=12)
        for h in hdrs:
            t = dpg.add_text(f"{h:<14}", color=C["txt_dim"][:3])
            if "raj_sb_14" in _F: dpg.bind_item_font(t, _F["raj_sb_14"])
    dpg.add_separator()
    for ch in r.get("inhouse_champs",[]):
        wl  = f"{ch['wins']}-{ch['losses']}"
        wrc = C["win"][:3] if ch["wr"]>=50 else C["loss"][:3]
        vals = [ch["name"], str(ch["games"]), wl,
                f"{ch['wr']}%", str(ch["kda"]), f"{ch['damage']:,}"]
        with dpg.group(horizontal=True):
            dpg.add_spacer(width=12)
            for i, v in enumerate(vals):
                col = C["rift_purple"][:3] if i==0 else wrc if i==3 else C["txt"][:3]
                t = dpg.add_text(f"{v:<14}", color=col)
                if "raj_r_14" in _F: dpg.bind_item_font(t, _F["raj_r_14"])
    dpg.add_spacer(height=6)

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
class ScoutPhase:
    IDLE    = "idle"
    LOADING = "loading"
    REVEAL  = "reveal"
    DONE    = "done"


class ScoutState:
    def __init__(self):
        self.phase      = ScoutPhase.IDLE
        self.players    = []
        self.sort_col   = "score"
        self.sort_asc   = False
        self.selected   = None
        self.row_alpha  = {}
        self.row_x_off  = {}
        self.header_alpha = 0
        self.graph_frac = 0.0
        self._load_t    = 0.0

    def reset(self):
        self.__init__()

    def tick(self):
        self._load_t += 0.04

    def begin_load(self, players):
        self.reset()
        self.players = players
        self.phase   = ScoutPhase.LOADING
        anim.tween(0, 1, 1, "linear", delay_ms=1600, on_done=self._reveal)

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
        total_ms = 80 + len(self.players)*35 + 200
        anim.tween(0.0, 1.0, 600, "out_cubic", delay_ms=total_ms,
                   on_update=lambda v: setattr(self, "graph_frac", v),
                   on_done=lambda: setattr(self, "phase", ScoutPhase.DONE))

    def _sorted(self):
        key = self.sort_col
        filtered = [p for p in self.players]
        return sorted(filtered, key=lambda p: p.get(key, 0), reverse=not self.sort_asc)

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


scout = ScoutState()
_F    = {}
def set_fonts(f): global _F; _F = f

# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
ROW_H      = 54
HEADER_H   = 44
TOP_BAR_H  = 56
PAD        = 20
TABLE_FRAC = 0.55

COLS = [
    ("RANK",   0.07, "score"),
    ("PLAYER", 0.28, None),
    ("SCORE",  0.14, "score"),
    ("W/R",    0.11, "wr"),
    ("KDA",    0.10, "kda"),
    ("GAMES",  0.10, "games"),
    ("CHAMPS", 0.20, None),
]

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

    table_w = int(vw * TABLE_FRAC) - PAD
    graph_x = int(vw * TABLE_FRAC) + PAD
    graph_w = vw - graph_x - PAD

    _draw_top_bar(dl, vw)
    _draw_table(dl, PAD, TOP_BAR_H + PAD, table_w, vh - TOP_BAR_H - PAD*2, vw, vh)
    _draw_graph(dl, graph_x, TOP_BAR_H + PAD, graph_w, vh - TOP_BAR_H - PAD*2)


def _draw_idle(dl, vw, vh):
    cx, cy = vw//2, vh//2
    t = (math.sin(time.monotonic()*1.3)+1)/2
    a = int(90 + t*110)
    _txt(dl, cx-200, cy-30, "PLAYER SCOUTING", (*C["gold"][:3],a), 36, "raj_36")
    _txt(dl, cx-170, cy+14, "Fetch latest data to begin", (*C["txt_dim"][:3],int(a*.6)), 18, "raj_18")
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
            scout.begin_load(_DEMO_PLAYERS)


def _draw_loading(dl, vw, vh):
    cx, cy = vw//2, vh//2
    t = (math.sin(scout._load_t*2.0)+1)/2
    a = int(80 + t*130)
    _txt(dl, cx-170, cy-14, "FETCHING SCOUT DATA...", (*C["gold_dk"][:3],a), 20, "raj_20")
    dots = "." * (int(scout._load_t*2) % 4)
    _txt(dl, cx+130, cy-14, dots, (*C["gold"][:3],a), 20, "raj_20")


def _draw_top_bar(dl, vw):
    dpg.draw_rectangle((0,0),(vw,TOP_BAR_H), fill=(*C["panel"][:3],220), color=(0,0,0,0), parent=dl)
    dpg.draw_line((0,TOP_BAR_H-1),(vw,TOP_BAR_H-1), color=C["rule_dark"], thickness=1, parent=dl)
    _txt(dl, PAD, 12, "PLAYER SCOUTING", (*C["gold"][:3],220), 22, "raj_24")
    _txt(dl, PAD+240, 18, "Click a player name to open full scouting report",
         (*C["txt_dim"][:3],160), 13, "raj_r_14")

    labels = [("SCORE","score"),("W/R","wr"),("KDA","kda"),("GAMES","games")]
    bx = vw - 480
    for lbl, col in labels:
        active = scout.sort_col == col
        bc = C["gold"] if active else C["rule_dark"]
        fc = (*C["gold_dk"][:3],200) if active else (0,0,0,0)
        dpg.draw_rectangle((bx,10),(bx+90,TOP_BAR_H-10), fill=fc, color=(*bc[:3],200), rounding=4, parent=dl)
        arr = ("▲" if scout.sort_asc else "▼") if active else ""
        tcol = C["gold_lt"] if active else C["txt"]
        _txt(dl, bx+8, 18, lbl+arr, (*tcol[:3],220), 16, "raj_18")
        bx += 100
    if dpg.is_mouse_button_clicked(0):
        mouse = dpg.get_mouse_pos(local=False)
        vp    = dpg.get_viewport_pos()
        rx = mouse[0]-vp[0]-68; ry = mouse[1]-vp[1]-52
        if 10 <= ry <= TOP_BAR_H-10:
            bx2 = vw - 480
            for _, c2 in labels:
                if bx2 <= rx <= bx2+90:
                    scout.toggle_sort(c2); break
                bx2 += 100


def _draw_table(dl, tx, ty, tw, th, vw, vh):
    players = scout._sorted()
    col_xs  = _col_xs(tw)
    ha      = scout.header_alpha

    # Header
    dpg.draw_rectangle((tx,ty),(tx+tw,ty+HEADER_H),
                        fill=(*C["card"][:3],ha), color=(*C["rule_dark"][:3],ha), rounding=4, parent=dl)
    for ci, ((lbl,_,sk),(cx,cw)) in enumerate(zip(COLS,col_xs)):
        active = sk and scout.sort_col==sk
        col = C["gold"] if active else C["txt_dim"]
        _txt(dl, tx+cx+8, ty+HEADER_H//2-10, lbl, (*col[:3],ha), 14, "raj_sb_16")
    dpg.draw_line((tx,ty+HEADER_H),(tx+tw,ty+HEADER_H),
                  color=(*C["rule_dark"][:3],ha), thickness=1, parent=dl)

    row_y = ty + HEADER_H + 4
    # Store name hit boxes for click detection
    name_hitboxes = []

    for i, p in enumerate(players):
        n  = p["name"]
        al = scout.row_alpha.get(n, 0)
        xo = scout.row_x_off.get(n, -60)
        if al <= 0:
            continue
        ry  = row_y + i*(ROW_H+3)
        is_sel = scout.selected == n
        bg = (*C["card_hover"][:3],al) if is_sel else \
             (*C["card"][:3],al) if i%2==0 else (*C["panel"][:3],al)
        dpg.draw_rectangle((tx+xo,ry),(tx+tw+xo,ry+ROW_H),
                            fill=bg, color=(0,0,0,0), rounding=3, parent=dl)
        if is_sel:
            dpg.draw_rectangle((tx+xo,ry),(tx+xo+4,ry+ROW_H),
                                fill=(*C["gold"][:3],al), color=(0,0,0,0), rounding=2, parent=dl)

        tier = p.get("tier","Unranked")
        bc   = RANK_COLORS.get(tier,RANK_COLORS["Unranked"])
        try:
            score_disp = str(int(float(p["score"])))
        except (ValueError, TypeError):
            score_disp = str(p.get("score", "?"))
        vals = [str(i+1), p["name"], score_disp,
                f"{p['wr']}%", f"{p['kda']:.1f}", str(p["games"]),
                "  ".join(p["top_champs"][:2])]

        for ci,(val,(cx,cw)) in enumerate(zip(vals,col_xs)):
            vx = tx+xo+cx+8
            vy = ry+ROW_H//2-10
            if ci==0:
                _txt(dl, vx, vy, val, (*C["txt_dim"][:3],al), 16, "raj_18")
            elif ci==1:
                dpg.draw_circle((vx+6,ry+ROW_H//2),8, fill=(*bc[:3],al), color=(0,0,0,0), parent=dl)
                name_tag = _txt(dl, vx+20, vy, val.upper(), (*C["gold_lt"][:3],al), 18, "raj_20")
                # Store hitbox: (x1, y1, x2, y2, name)
                name_hitboxes.append((vx+20, vy, vx+20+len(val)*11, vy+22, n))
            elif ci==2:
                _txt(dl, vx, vy, val, (*C["gold"][:3],al), 18, "raj_20")
            elif ci==3:
                wr_v  = p.get("wr",50)
                wrc   = C["win"] if wr_v>=52 else C["loss"] if wr_v<48 else C["txt"]
                _txt(dl, vx, vy, val, (*wrc[:3],al), 16, "raj_18")
            elif ci==4:
                _txt(dl, vx, vy, val, (*C["platinum"][:3],al), 16, "raj_18")
            else:
                _txt(dl, vx, vy, val, (*C["txt2"][:3],al), 14, "raj_16")

    # Click detection — name opens report, row click selects for graph
    if dpg.is_mouse_button_clicked(0):
        mouse = dpg.get_mouse_pos(local=False)
        vp    = dpg.get_viewport_pos()
        rx2   = mouse[0]-vp[0]-68
        ry2   = mouse[1]-vp[1]-52

        # Check name hitboxes first
        opened = False
        for (x1,y1,x2,y2,name) in name_hitboxes:
            if x1 <= rx2 <= x2 and y1 <= ry2 <= y2:
                _open_report(name, vw, vh)
                opened = True
                break

        # Otherwise row click → select for graph
        if not opened:
            for i, p in enumerate(players):
                n  = p["name"]
                al = scout.row_alpha.get(n, 0)
                xo = scout.row_x_off.get(n, -60)
                ry3 = row_y + i*(ROW_H+3)
                if al>0 and tx<=rx2<=tx+tw and ry3<=ry2<=ry3+ROW_H:
                    scout.selected = n if scout.selected!=n else None
                    scout.graph_frac = 0.0
                    anim.tween(0.0,1.0,500,"out_cubic",
                               on_update=lambda v: setattr(scout,"graph_frac",v))
                    break


def _draw_graph(dl, gx, gy, gw, gh):
    ha = scout.header_alpha
    if ha <= 0: return
    dpg.draw_rectangle((gx,gy),(gx+gw,gy+gh), fill=(*C["panel"][:3],ha),
                        color=(*C["rule_dark"][:3],ha), rounding=6, parent=dl)
    dpg.draw_rectangle((gx+2,gy+2),(gx+gw-2,gy+6), fill=(*C["gold_dk"][:3],ha),
                        color=(0,0,0,0), rounding=2, parent=dl)

    name = scout.selected or (scout.players[0]["name"] if scout.players else None) \
           or (_DEMO_PLAYERS[0]["name"] if _DEMO_PLAYERS else None)
    if not name: return
    history = _SCORE_HISTORY.get(name, [])
    player  = _BY_NAME.get(name) or next((p for p in scout.players if p["name"] == name), None)
    if not player: return
    if not history:
        # Generate placeholder history from current score
        sc = player.get("score", 0)
        try:
            sc = float(sc)
        except (ValueError, TypeError):
            sc = 0
        history = [sc] * 5

    _txt(dl, gx+16, gy+14, name.upper(), (*C["gold"][:3],ha), 22, "raj_24")
    tier = player["tier"]
    bc   = RANK_COLORS.get(tier,RANK_COLORS["Unranked"])
    _txt(dl, gx+16, gy+42, tier.upper(), (*bc[:3],ha), 14, "raj_sb_16")

    sx = gx+16
    sc_display = str(player.get("score", player.get("final_score", "?")))
    for lbl, val in [("SCORE", sc_display), ("W/R", f"{player.get('wr',0)}%"),
                     ("KDA", f"{player.get('kda',0.0):.1f}"), ("GAMES", str(player.get("games",0)))]:
        _txt(dl, sx, gy+68, lbl, (*C["txt_dim"][:3],ha), 11, "raj_sb_11")
        _txt(dl, sx, gy+84, val, (*C["txt"][:3],ha), 20, "raj_20")
        sx += gw//4

    dpg.draw_line((gx+16,gy+112),(gx+gw-16,gy+112), color=(*C["rule_dark"][:3],ha), thickness=1, parent=dl)

    plot_x = gx+24; plot_y = gy+124
    plot_w = gw-48; plot_h = gh-220
    if plot_h < 60: return

    mn,mx = min(history),max(history); rng = max(mx-mn,1)
    def _pt(i,v):
        px2 = plot_x + int(i/(len(history)-1)*plot_w) if len(history)>1 else plot_x+plot_w//2
        py2 = plot_y + plot_h - int((v-mn)/rng*plot_h)
        return px2, py2

    frac    = scout.graph_frac
    n_draw  = max(2, int(frac*len(history)))
    visible = history[:n_draw]

    for gi in range(4):
        gy2 = plot_y + int(gi/3*plot_h)
        dpg.draw_line((plot_x,gy2),(plot_x+plot_w,gy2),
                      color=(*C["rule_dark"][:3],ha//2), thickness=1, parent=dl)
        _txt(dl, plot_x-36, gy2-8, str(int(mx-gi/3*rng)),
             (*C["txt_dim"][:3],ha//2), 10, "raj_sb_11")

    if len(visible)>=2:
        fp = [_pt(i,v) for i,v in enumerate(visible)]
        fp += [(fp[-1][0],plot_y+plot_h),(plot_x,plot_y+plot_h)]
        dpg.draw_polygon(fp, fill=(*C["gold_dk"][:3],int(ha*0.25)), color=(0,0,0,0), parent=dl)
    for i in range(1,len(visible)):
        dpg.draw_line(_pt(i-1,visible[i-1]), _pt(i,visible[i]),
                      color=(*C["gold"][:3],ha), thickness=2.5, parent=dl)
    for i,v in enumerate(visible):
        px2,py2 = _pt(i,v)
        dpg.draw_circle((px2,py2),5, fill=(*C["gold_lt"][:3],ha),
                        color=(*C["bg"][:3],ha), parent=dl)
    for i in range(len(history)):
        px2,_ = _pt(i,0)
        _txt(dl, px2-6, plot_y+plot_h+8, f"S{i+1}",
             (*C["txt_dim"][:3],ha//2), 10, "raj_sb_11")

    # Open report hint
    _txt(dl, gx+16, gy+gh-52, "Click player name in table for full report",
         (*C["txt_dim"][:3],ha//2), 12, "raj_r_14")

    champ_y = gy+gh-36
    _txt(dl, gx+16, champ_y-4, "TOP CHAMPIONS", (*C["txt_dim"][:3],ha), 12, "raj_sb_14")
    for i,ch in enumerate(player.get("top_champs",[])[:3]):
        cx2 = gx+16+i*(gw-48)//3
        dpg.draw_rectangle((cx2,champ_y+14),(cx2+(gw-48)//3,champ_y+36),
                            fill=(*C["card"][:3],ha), color=(*C["rule_dark"][:3],ha), rounding=4, parent=dl)
        _txt(dl, cx2+8, champ_y+20, ch, (*C["txt"][:3],ha), 14, "raj_16")
