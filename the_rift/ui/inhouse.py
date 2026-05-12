"""
Inhouse Tab — Phase 5.
Left panel: leaderboard (rank, player, GP, W-L, WR, KDA, Avg DMG, Avg Gold).
Right panel: player detail — slides in on row click, shows champion breakdown + sparkline.
Top-right notification: "GAME LOGGED" card slams in on new game detected.
"""
import math, time, random as _rnd, os
import dearpygui.dearpygui as dpg
from theme import C, RANK_COLORS
from core.animations import anim
from data.reader import live, log_inhouse_games_from_client, get_most_games_logged
from data.tips import TIPS as _TIPS

# ---------------------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------------------
_demo_rnd = _rnd.Random(7)   # isolated seed — does not affect global random

_DEMO_LEADERBOARD = [
    {"rank":1, "player":"Phantom",  "games":42, "wins":28,"losses":14,"wr":"67%","kda":4.2,"cs_min":7.1,"damage":"18,200","gold":"14,800"},
    {"rank":2, "player":"Ironclad", "games":38, "wins":24,"losses":14,"wr":"63%","kda":3.8,"cs_min":6.8,"damage":"16,900","gold":"13,600"},
    {"rank":3, "player":"Vex",      "games":35, "wins":21,"losses":14,"wr":"61%","kda":3.5,"cs_min":6.5,"damage":"15,400","gold":"12,900"},
    {"rank":4, "player":"Shroud",   "games":40, "wins":23,"losses":17,"wr":"58%","kda":3.1,"cs_min":6.2,"damage":"13,200","gold":"12,100"},
    {"rank":5, "player":"Blaze",    "games":36, "wins":20,"losses":16,"wr":"55%","kda":2.9,"cs_min":5.9,"damage":"14,600","gold":"11,800"},
    {"rank":6, "player":"Kira",     "games":30, "wins":16,"losses":14,"wr":"54%","kda":2.7,"cs_min":5.8,"damage":"12,800","gold":"11,400"},
    {"rank":7, "player":"Dusk",     "games":28, "wins":15,"losses":13,"wr":"52%","kda":2.5,"cs_min":5.6,"damage":"11,900","gold":"10,900"},
    {"rank":8, "player":"Nox",      "games":44, "wins":22,"losses":22,"wr":"50%","kda":2.3,"cs_min":5.4,"damage":"11,200","gold":"10,600"},
    {"rank":9, "player":"Cinder",   "games":32, "wins":15,"losses":17,"wr":"49%","kda":2.2,"cs_min":5.2,"damage":"10,800","gold":"10,200"},
    {"rank":10,"player":"Riven",    "games":25, "wins":12,"losses":13,"wr":"47%","kda":2.0,"cs_min":5.0,"damage":"10,100","gold": "9,800"},
    {"rank":11,"player":"Ember",    "games":22, "wins":10,"losses":12,"wr":"46%","kda":1.9,"cs_min":4.8,"damage": "9,600","gold": "9,400"},
    {"rank":12,"player":"Lyra",     "games":20, "wins": 9,"losses":11,"wr":"45%","kda":1.8,"cs_min":4.6,"damage": "9,100","gold": "9,100"},
    {"rank":13,"player":"Torque",   "games":18, "wins": 8,"losses":10,"wr":"44%","kda":1.7,"cs_min":4.4,"damage": "8,700","gold": "8,800"},
    {"rank":14,"player":"Flux",     "games":16, "wins": 7,"losses": 9,"wr":"42%","kda":1.5,"cs_min":4.2,"damage": "8,200","gold": "8,500"},
    {"rank":15,"player":"Zeal",     "games":14, "wins": 6,"losses": 8,"wr":"40%","kda":1.4,"cs_min":4.0,"damage": "7,800","gold": "8,200"},
]

_DEMO_CHAMPS = {
    p["player"]: [
        {"champ": champ, "games": _demo_rnd.randint(4,12),
         "wins": _demo_rnd.randint(2,8), "losses": _demo_rnd.randint(1,6),
         "wr": _demo_rnd.randint(40,72), "kda": round(p["kda"]+_demo_rnd.uniform(-0.5,0.7),1),
         "kills": round(p["kda"]*2.0+_demo_rnd.uniform(-0.5,0.5),1),
         "deaths": round(p["kda"]*0.8+_demo_rnd.uniform(-0.2,0.3),1),
         "assists": round(p["kda"]*3.0+_demo_rnd.uniform(-0.5,0.8),1),
         "damage": f"{_demo_rnd.randint(9000,22000):,}"}
        for champ in ["Zed","Akali","Talon"][:3]
    ]
    for p in _DEMO_LEADERBOARD
}

_DEMO_SPARKLINES = {
    p["player"]: [_demo_rnd.randint(0,1) for _ in range(10)]
    for p in _DEMO_LEADERBOARD
}

_BY_NAME = {p["player"]: p for p in _DEMO_LEADERBOARD}
_LIVE_SPARKLINES = {}   # player_name → [0/1, ...] from real game log


def update_live_data(players, champs):
    """
    Called from main.py after live data loads.
    Replaces _BY_NAME and _DEMO_CHAMPS with real inhouse data so the detail
    panel shows live stats instead of demo values.
    """
    global _BY_NAME
    _BY_NAME = {p["player"]: p for p in players} if players else _BY_NAME
    _DEMO_CHAMPS.update(champs)
    for p in (players or []):
        results = p.get("recent_results")
        if results:
            _LIVE_SPARKLINES[p["player"]] = results

# ---------------------------------------------------------------------------
# "Game Logged" notification
# ---------------------------------------------------------------------------
class _GameLoggedNotif:
    def __init__(self):
        self.visible  = False
        self.y_off    = 0      # -80 = fully hidden above, 0 = fully shown
        self.alpha    = 0
        self.hold_t   = 0.0
        self._holding = False

    def show(self, summary="GAME LOGGED"):
        self.summary  = summary
        self.visible  = True
        self._holding = False
        self.hold_t   = 0.0
        self.alpha    = 0
        self.y_off    = -90
        anim.tween(-90, 0, 400, "elastic_out",
                   on_update=lambda v: setattr(self, "y_off", v))
        anim.tween(0, 255, 200, "out_cubic",
                   on_update=lambda v: setattr(self, "alpha", int(v)))
        anim.tween(0, 1, 1, "linear", delay_ms=3400, on_done=self._dismiss)

    def _dismiss(self):
        anim.tween(0, -90, 260, "out_cubic",
                   on_update=lambda v: setattr(self, "y_off", v))
        anim.tween(255, 0, 240, "out_cubic",
                   on_update=lambda v: setattr(self, "alpha", int(v)),
                   on_done=lambda: setattr(self, "visible", False))

    def draw(self, dl, vw):
        if not self.visible: return
        al = self.alpha
        if al <= 0: return
        nw, nh = 260, 72
        nx = vw - nw - 24
        ny = 8 + int(self.y_off)
        # Card
        dpg.draw_rectangle((nx, ny), (nx+nw, ny+nh),
                            fill=(*C["card"][:3], al),
                            color=(*C["gold"][:3], al),
                            rounding=6, parent=dl)
        # Gold left accent bar
        dpg.draw_rectangle((nx, ny), (nx+4, ny+nh),
                            fill=(*C["gold"][:3], al),
                            color=(0,0,0,0), rounding=3, parent=dl)
        # Title
        _txt(dl, nx+16, ny+10, "◆  GAME LOGGED", (*C["gold_lt"][:3], al), 17, "raj_sb_18")
        # Summary
        _txt(dl, nx+16, ny+38, getattr(self, "summary", ""), (*C["txt"][:3], int(al*0.8)), 13, "raj_14")


_notif = _GameLoggedNotif()

# ---------------------------------------------------------------------------
# Avatar texture registry
# ---------------------------------------------------------------------------
_AVATAR_REG     = "rift_avatar_reg"
_avatar_textures = {}   # display_name (lowercase) → dpg texture tag
_pending_avatars = []   # [(name, path)] queued from background threads → registered on main thread
_avatars_scanned = False


def _ensure_reg():
    if not dpg.does_item_exist(_AVATAR_REG):
        dpg.add_texture_registry(tag=_AVATAR_REG)


def _register_tex(name, path):
    """Register one image as a static DPG texture. Must run on main thread.
    Uses Pillow for guaranteed RGBA conversion so JPEGs and PNGs both work."""
    key = name.strip().lower()
    tag = f"av_{key}"
    if dpg.does_item_exist(tag):
        _avatar_textures[key] = tag
        return
    try:
        from PIL import Image
        import numpy as np
        img  = Image.open(path).convert("RGBA")
        w, h = img.size
        data = (np.array(img, dtype=np.float32) / 255.0).flatten().tolist()
        _ensure_reg()
        dpg.add_static_texture(w, h, data, tag=tag, parent=_AVATAR_REG)
        _avatar_textures[key] = tag
    except Exception as e:
        print(f"[avatar] Failed to load '{path}': {e}")


def _scan_local_avatars():
    """Scan assets/profile_icons/ on first call and queue any found images."""
    global _avatars_scanned
    if _avatars_scanned:
        return
    _avatars_scanned = True
    try:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        adir = os.path.join(root, "assets", "profile_icons")
        if not os.path.isdir(adir):
            return
        for fname in os.listdir(adir):
            if fname.lower().endswith((".png", ".jpg", ".jpeg")):
                name = os.path.splitext(fname)[0]
                path = os.path.join(adir, fname)
                _pending_avatars.append((name, path))
    except Exception:
        pass


def _flush_pending():
    """Call from main draw thread to register queued textures."""
    while _pending_avatars:
        name, path = _pending_avatars.pop(0)
        _register_tex(name, path)


def queue_avatar_reload(name, path):
    """Called from settings after upload completes (may be background thread)."""
    _pending_avatars.append((name, path))


def queue_avatars_reload_all(avatar_map):
    """Called after 'Sync All Avatars' — avatar_map is {name: local_path}."""
    for name, path in avatar_map.items():
        _pending_avatars.append((name, path))


def _get_avatar_tex(name):
    """Return texture tag for name or None."""
    return _avatar_textures.get(name.strip().lower())


_log_in_progress   = False
_most_games_player = ""
_most_games_fetched = False


def _fetch_most_games_once():
    global _most_games_fetched, _most_games_player
    if _most_games_fetched:
        return
    _most_games_fetched = True
    def _done(name, count=0):
        global _most_games_player
        _most_games_player = name or ""
    get_most_games_logged(on_done=_done, on_error=lambda _: None)


def _start_log_game():
    global _log_in_progress, _most_games_fetched
    if _log_in_progress:
        return
    _log_in_progress = True
    _notif.show("Connecting to LOL client…")

    def _progress(msg):
        _notif.show(msg)

    def _done(count):
        global _log_in_progress, _most_games_fetched
        _log_in_progress = False
        if count and count > 0:
            _notif.show(f"Logged {count} new game{'s' if count != 1 else ''}")
            if live.inhouse:
                update_live_data(live.inhouse, live.inhouse_champs)
                inhouse.begin_load(live.inhouse)
            _most_games_fetched = False
            _fetch_most_games_once()
        else:
            _notif.show("No new games found")

    def _error(msg):
        global _log_in_progress
        _log_in_progress = False
        _notif.show(f"Error: {str(msg)[:40]}")

    log_inhouse_games_from_client(
        on_progress=_progress,
        on_done=_done,
        on_error=_error,
    )

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
class InhousePhase:
    IDLE    = "idle"
    LOADING = "loading"
    REVEAL  = "reveal"
    DONE    = "done"


_INHOUSE_FILTER_WIN = "inhouse_filter_win"
FILTER_H = 44   # height of search bar between top-bar and leaderboard

class InhouseState:
    def __init__(self):
        self.phase         = InhousePhase.IDLE
        self.players       = []
        self.selected      = None
        self.row_alpha     = {}
        self.row_x_off     = {}
        self.header_alpha  = 0
        self.detail_x_frac = 0.0   # 0=hidden (right), 1=shown
        self._load_t       = 0.0
        self.filter_text   = ""    # live search string
        self._tip          = _rnd.choice(_TIPS)

    def reset(self):
        self.__init__()

    def tick(self):
        self._load_t += 0.04

    def begin_load(self, players):
        self.reset()
        self.players = players
        self.phase   = InhousePhase.LOADING
        anim.tween(0, 1, 1, "linear", delay_ms=1400, on_done=self._reveal)

    def _reveal(self):
        self.phase = InhousePhase.REVEAL
        anim.tween(0, 255, 120, "out_cubic",
                   on_update=lambda v: setattr(self, "header_alpha", int(v)))
        for i, p in enumerate(self.players):
            n = p["player"]
            self.row_alpha[n] = 0
            self.row_x_off[n] = -60
            def _make(name=n):
                def _x(v): self.row_x_off[name] = int(v)
                def _a(v): self.row_alpha[name]  = int(v)
                anim.tween(-60, 0,   200, "out_cubic", on_update=_x)
                anim.tween(0,   255, 200, "out_cubic", on_update=_a)
            anim.tween(0, 1, 1, "linear", delay_ms=60 + i*35, on_done=_make)
        total_ms = 60 + len(self.players)*35 + 200
        anim.tween(0, 1, 1, "linear", delay_ms=total_ms,
                   on_done=lambda: setattr(self, "phase", InhousePhase.DONE))

    def select(self, name):
        if self.selected == name:
            self.selected = None
            anim.tween(1.0, 0.0, 250, "out_cubic",
                       on_update=lambda v: setattr(self, "detail_x_frac", v))
        else:
            self.selected = name
            anim.tween(0.0, 1.0, 320, "out_cubic",
                       on_update=lambda v: setattr(self, "detail_x_frac", v))


inhouse = InhouseState()
_F = {}
def set_fonts(f): global _F; _F = f

# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
ROW_H       = 52
HEADER_H    = 44
TOP_BAR_H   = 56
_VP_TITLE_H = 52   # app titlebar height (same as main.py TITLE_H)
PAD         = 20
DETAIL_W  = 560   # fixed width of sliding detail panel

COLS = [
    ("#",       0.05),
    ("PLAYER",  0.22),
    ("GP",      0.07),
    ("W-L",     0.10),
    ("WR",      0.09),
    ("KDA",     0.09),
    ("AVG DMG", 0.16),
    ("AVG GOLD",0.14),
    ("TREND",   0.08),
]


def _txt(dl, x, y, text, color, size, font_key=None):
    tag = dpg.draw_text((x, y), text, color=color, size=size, parent=dl)
    if font_key and font_key in _F:
        dpg.bind_item_font(tag, _F[font_key])
    return tag


def _col_xs(tw):
    xs, cur = [], 0
    for _, frac in COLS:
        w = int(tw * frac)
        xs.append((cur, w))
        cur += w
    return xs


# ---------------------------------------------------------------------------
# Main draw
# ---------------------------------------------------------------------------

def _ensure_filter_window(vw, vh):
    """Create or reposition the search-bar overlay window.
    x tracks the sidebar's current right edge; y is below both the app
    titlebar (_VP_TITLE_H) and the inhouse top bar (TOP_BAR_H)."""
    sidebar_w = dpg.get_viewport_width() - vw   # dynamic sidebar width
    win_x     = sidebar_w
    win_y     = _VP_TITLE_H + TOP_BAR_H

    if not dpg.does_item_exist(_INHOUSE_FILTER_WIN):
        with dpg.window(tag=_INHOUSE_FILTER_WIN,
                        pos=(win_x, win_y),
                        width=vw, height=FILTER_H,
                        no_title_bar=True, no_resize=True,
                        no_move=True, no_focus_on_appearing=True,
                        no_scrollbar=True):
            with dpg.group(horizontal=True):
                dpg.add_spacer(width=PAD - 8)
                search = dpg.add_input_text(
                    tag="ih_search",
                    hint="Search player…",
                    width=260,
                    height=30,
                    callback=lambda s, a: setattr(inhouse, "filter_text", a),
                )
                if "raj_r_14" in _F:
                    dpg.bind_item_font(search, _F["raj_r_14"])
                dpg.add_spacer(width=12)
                clear_btn = dpg.add_button(
                    label="✕",
                    width=28, height=28,
                    callback=lambda: (dpg.set_value("ih_search", ""),
                                      setattr(inhouse, "filter_text", "")),
                )
                if "raj_r_14" in _F:
                    dpg.bind_item_font(clear_btn, _F["raj_r_14"])
    else:
        dpg.configure_item(_INHOUSE_FILTER_WIN,
                           pos=(win_x, win_y),
                           width=vw, height=FILTER_H)


def draw_inhouse(dl, vw, vh, fonts=None):
    if fonts:
        set_fonts(fonts)
    _scan_local_avatars()
    _flush_pending()
    inhouse.tick()
    dpg.delete_item(dl, children_only=True)
    dpg.draw_rectangle((0, 0), (vw, vh), fill=C["bg"], color=(0,0,0,0), parent=dl)

    if inhouse.phase == InhousePhase.IDLE:
        _draw_idle(dl, vw, vh)
        _notif.draw(dl, vw)
        return
    if inhouse.phase == InhousePhase.LOADING:
        _draw_loading(dl, vw, vh)
        return

    # Detail panel slide: occupies right DETAIL_W when open
    detail_open = inhouse.detail_x_frac > 0.01
    table_w = vw - PAD*2 - (int(DETAIL_W * inhouse.detail_x_frac) if detail_open else 0)

    _draw_top_bar(dl, vw)
    _ensure_filter_window(vw, vh)

    table_top = TOP_BAR_H + FILTER_H + 4
    _draw_leaderboard(dl, PAD, table_top, table_w - PAD,
                      vh - table_top - PAD, vw, vh)
    if detail_open:
        _draw_detail_panel(dl, vw, vh)
    _notif.draw(dl, vw)


def _draw_idle(dl, vw, vh):
    cx, cy = vw//2, vh//2
    t = (math.sin(time.monotonic()*1.3)+1)/2
    a = int(90 + t*110)
    _txt(dl, cx-180, cy-30, "IN-HOUSE CUSTOMS", (*C["gold"][:3], a), 36, "raj_36")
    hint = "Live data ready — click to load" if (live.loaded and live.inhouse) \
           else "Fetch leaderboard to begin"
    _txt(dl, cx-165, cy+14, hint, (*C["txt_dim"][:3], int(a*0.6)), 18, "raj_18")
    bw, bh = 320, 60
    bx, by = cx-bw//2, cy+56
    dpg.draw_rectangle((bx,by),(bx+bw,by+bh), fill=(*C["gold_dk"][:3],210),
                        color=(*C["gold"][:3],210), rounding=6, parent=dl)
    _txt(dl, bx+bw//2-130, by+16, "LOAD LEADERBOARD", (*C["gold_lt"][:3], 230), 22, "raj_24")

    if dpg.is_mouse_button_clicked(0):
        mouse = dpg.get_mouse_pos(local=False)
        vp    = dpg.get_viewport_pos()
        rx = mouse[0]-vp[0]-68; ry = mouse[1]-vp[1]-52
        if bx<=rx<=bx+bw and by<=ry<=by+bh:
            if live.loaded and live.inhouse:
                update_live_data(live.inhouse, live.inhouse_champs)
                inhouse.begin_load(live.inhouse)
            else:
                inhouse.begin_load(_DEMO_LEADERBOARD)


def _draw_loading(dl, vw, vh):
    cx, cy = vw//2, vh//2
    t  = (math.sin(inhouse._load_t*2.0)+1)/2
    a  = int(80 + t*130)
    dots = "." * (int(inhouse._load_t*2) % 4)
    label = f"FETCHING LEADERBOARD{dots}"
    _txt(dl, cx - len(label)*7, cy-30, label, (*C["gold_dk"][:3], a), 26, "raj_28")
    tip = inhouse._tip
    tip_x = max(40, cx - len(tip) * 5)
    _txt(dl, tip_x, cy+16, tip, (*C["txt_dim"][:3], int(a*0.8)), 18, "raj_r_18")
    # Animated loading bar
    bar_w = min(400, vw - 120)
    bar_x = cx - bar_w // 2
    bar_y = cy + 62
    prog  = (inhouse._load_t % 1.8) / 1.8
    fill  = int(bar_w * prog)
    dpg.draw_rectangle((bar_x, bar_y), (bar_x+bar_w, bar_y+4),
                        fill=(*C["card"][:3], int(a*0.5)), color=(0,0,0,0), parent=dl)
    if fill > 0:
        dpg.draw_rectangle((bar_x, bar_y), (bar_x+fill, bar_y+4),
                            fill=(*C["gold_dk"][:3], a), color=(0,0,0,0), parent=dl)


def _draw_top_bar(dl, vw):
    _fetch_most_games_once()
    dpg.draw_rectangle((0,0),(vw,TOP_BAR_H), fill=(*C["panel"][:3],220),
                        color=(0,0,0,0), parent=dl)
    dpg.draw_line((0,TOP_BAR_H-1),(vw,TOP_BAR_H-1),
                  color=C["rule_dark"], thickness=1, parent=dl)
    _txt(dl, PAD, 12, "IN-HOUSE CUSTOMS", (*C["gold"][:3],220), 22, "raj_24")
    _txt(dl, PAD+256, 18, "Click a player row to view champion breakdown",
         (*C["txt_dim"][:3],160), 16, "raj_r_16")

    # "LOG GAME" button
    bw, bh = 160, 36
    bx = vw - bw - PAD
    by = (TOP_BAR_H - bh)//2
    is_logging = _log_in_progress
    btn_fill = (*C["card"][:3], 200) if is_logging else (*C["gold_dk"][:3], 200)
    btn_bdr  = (*C["gold"][:3], 80)  if is_logging else (*C["gold"][:3], 200)
    btn_lbl  = "LOGGING…"            if is_logging else "◆  LOG GAME"
    lbl_col  = (*C["txt_dim"][:3], 160) if is_logging else (*C["gold_lt"][:3], 240)
    dpg.draw_rectangle((bx,by),(bx+bw,by+bh),
                        fill=btn_fill, color=btn_bdr, rounding=4, parent=dl)
    _txt(dl, bx+14, by+8, btn_lbl, lbl_col, 15, "raj_sb_16")

    # Most Games Logged label (left of LOG GAME button)
    if _most_games_player:
        mg_lbl = f"Most Games Logged:  {_most_games_player}"
        _txt(dl, bx - 280, by + 10, mg_lbl, (*C["txt2"][:3], 200), 16, "raj_r_16")

    if dpg.is_mouse_button_clicked(0):
        mouse = dpg.get_mouse_pos(local=False)
        vp    = dpg.get_viewport_pos()
        rx = mouse[0]-vp[0]-68; ry = mouse[1]-vp[1]-52
        if not is_logging and bx<=rx<=bx+bw and by<=ry<=by+bh:
            _start_log_game()


def _draw_leaderboard(dl, tx, ty, tw, th, vw, vh):
    ft = inhouse.filter_text.strip().lower()
    players  = [p for p in inhouse.players
                if not ft or ft in p["player"].lower()] if ft else inhouse.players
    col_xs   = _col_xs(tw)
    ha       = inhouse.header_alpha

    # Section header
    dpg.draw_rectangle((tx,ty),(tx+tw,ty+HEADER_H),
                        fill=(*C["card"][:3], ha), color=(*C["rule_dark"][:3], ha),
                        rounding=4, parent=dl)
    for ci, ((lbl,_),(cx,cw)) in enumerate(zip(COLS, col_xs)):
        active = (lbl in ("#","PLAYER","WR","KDA"))
        col = C["gold"] if active else C["txt_dim"]
        _txt(dl, tx+cx+8, ty+HEADER_H//2-9, lbl, (*col[:3], ha), 13, "raj_sb_14")
    dpg.draw_line((tx, ty+HEADER_H),(tx+tw, ty+HEADER_H),
                  color=(*C["rule_dark"][:3], ha), thickness=1, parent=dl)

    row_y = ty + HEADER_H + 4

    for i, p in enumerate(players):
        n  = p["player"]
        al = inhouse.row_alpha.get(n, 0)
        xo = inhouse.row_x_off.get(n, -60)
        if al <= 0:
            continue
        ry   = row_y + i*(ROW_H+2)
        rank = p["rank"]
        is_top3 = rank <= 3
        is_sel  = inhouse.selected == n

        # Row background
        if is_sel:
            bg = (*C["card_hover"][:3], al)
        elif is_top3:
            bg = (26, 20, 40, al)   # subtle purple tint for top 3
        elif i % 2 == 0:
            bg = (*C["card"][:3], al)
        else:
            bg = (*C["panel"][:3], al)

        dpg.draw_rectangle((tx+xo,ry),(tx+tw+xo,ry+ROW_H),
                            fill=bg, color=(0,0,0,0), rounding=3, parent=dl)

        # Left accent stripe: gold for selected, rift_purple for top3, nothing otherwise
        if is_sel:
            dpg.draw_rectangle((tx+xo,ry),(tx+xo+4,ry+ROW_H),
                                fill=(*C["gold"][:3],al), color=(0,0,0,0),
                                rounding=2, parent=dl)
        elif is_top3:
            dpg.draw_rectangle((tx+xo,ry),(tx+xo+4,ry+ROW_H),
                                fill=(*C["rift_purple"][:3],al), color=(0,0,0,0),
                                rounding=2, parent=dl)

        try:
            wr_num = float(str(p["wr"]).replace("%",""))
        except (ValueError, TypeError):
            wr_num = 50.0
        wr_col = C["win"] if wr_num >= 52 else C["loss"] if wr_num < 48 else C["txt"]
        name_col = C["rift_purple"] if is_top3 else C["gold_lt"]

        vals = [
            str(rank),
            p["player"].upper(),
            str(p["games"]),
            f"{p['wins']}-{p['losses']}",
            str(p["wr"]),
            str(p["kda"]),
            p["damage"],
            p["gold"],
            "",  # sparkline placeholder
        ]

        for ci, (val, (cx, cw)) in enumerate(zip(vals, col_xs)):
            vx = tx + xo + cx + 8
            vy = ry + ROW_H//2 - 10

            if ci == 0:
                rank_col = C["gold"] if is_top3 else C["txt_dim"]
                sz = 18 if is_top3 else 15
                _txt(dl, vx, vy+(0 if is_top3 else 2), str(rank), (*rank_col[:3],al), sz, "raj_20" if is_top3 else "raj_16")
            elif ci == 1:
                # Avatar — draw hex-cropped image if loaded, otherwise fallback dot
                tex = _get_avatar_tex(n)
                av_sz = min(ROW_H - 8, 42)
                if tex:
                    av_y1 = ry + (ROW_H - av_sz) // 2
                    dpg.draw_image(tex, (vx, av_y1), (vx + av_sz, av_y1 + av_sz), parent=dl)
                    _txt(dl, vx + av_sz + 6, vy, val, (*name_col[:3], al), 17, "raj_20")
                else:
                    _txt(dl, vx, vy, val, (*name_col[:3],al), 17, "raj_20")
            elif ci == 2:
                _txt(dl, vx, vy+2, val, (*C["txt"][:3],al), 15, "raj_16")
            elif ci == 3:
                _txt(dl, vx, vy+2, val, (*C["txt2"][:3],al), 15, "raj_16")
            elif ci == 4:
                _txt(dl, vx, vy, val, (*wr_col[:3],al), 16, "raj_18")
            elif ci == 5:
                _txt(dl, vx, vy+2, val, (*C["platinum"][:3],al), 15, "raj_16")
            elif ci in (6,7):
                _txt(dl, vx, vy+2, val, (*C["txt2"][:3],al), 17, "raj_18")
            elif ci == 8:
                _draw_sparkline(dl, vx, ry+8, cw-16, ROW_H-16, n, al)

    # Click detection
    if dpg.is_mouse_button_clicked(0):
        mouse = dpg.get_mouse_pos(local=False)
        vp    = dpg.get_viewport_pos()
        rx2   = mouse[0]-vp[0]-68
        ry2   = mouse[1]-vp[1]-52
        for i, p in enumerate(players):
            n  = p["player"]
            al = inhouse.row_alpha.get(n, 0)
            xo = inhouse.row_x_off.get(n, -60)
            ry3 = row_y + i*(ROW_H+2)
            if al>0 and tx<=rx2<=tx+tw and ry3<=ry2<=ry3+ROW_H:
                inhouse.select(n)
                break


def _draw_sparkline(dl, sx, sy, sw, sh, name, al):
    """Mini win/loss trend — green dot = win, red dot = loss."""
    history = _LIVE_SPARKLINES.get(name) or _DEMO_SPARKLINES.get(name, [])
    if not history:
        return
    n = len(history)
    dot_r = 4
    spacing = min(sw // max(n,1), 14)
    total_w = spacing * (n-1)
    ox = sx + (sw - total_w) // 2
    for i, result in enumerate(history):
        px2 = ox + i * spacing
        py2 = sy + sh//2
        col = C["win"] if result else C["loss"]
        dpg.draw_circle((px2, py2), dot_r, fill=(*col[:3], al),
                        color=(0,0,0,0), parent=dl)


def _draw_detail_panel(dl, vw, vh):
    frac = inhouse.detail_x_frac
    name = inhouse.selected
    if not name or frac < 0.01:
        return

    panel_w = int(DETAIL_W * frac)
    px = vw - panel_w
    py = TOP_BAR_H

    # Clip via scissor-like overlay — draw panel bg
    dpg.draw_rectangle((px, py), (vw, vh),
                        fill=(*C["panel"][:3], int(240*frac)),
                        color=(0,0,0,0), parent=dl)
    dpg.draw_line((px, py), (px, vh),
                  color=(*C["rule_dark"][:3], int(220*frac)),
                  thickness=1, parent=dl)
    dpg.draw_rectangle((px, py), (vw, py+4),
                        fill=(*C["gold_dk"][:3], int(200*frac)),
                        color=(0,0,0,0), parent=dl)

    al  = int(255 * frac)
    p   = _BY_NAME.get(name)
    if not p:
        return

    # Header — avatar + name
    av_sz = 56
    tex   = _get_avatar_tex(name)
    if tex:
        dpg.draw_image(tex, (px+16, py+10), (px+16+av_sz, py+10+av_sz), parent=dl)
        name_x = px + 16 + av_sz + 14
    else:
        name_x = px + 20
    _txt(dl, name_x, py+16, name.upper(), (*C["gold_lt"][:3], al), 26, "raj_28")

    # Sub-stats row
    sub = f"#{p['rank']}  ·  {p['games']} games  ·  {p['wins']}-{p['losses']}  ·  {p['wr']} WR  ·  KDA {p['kda']}"
    _txt(dl, px+20, py+74, sub, (*C["txt"][:3], int(al*0.85)), 16, "raj_r_16")

    dpg.draw_line((px+16, py+98),(vw-16, py+98),
                  color=(*C["rule_dark"][:3], int(180*frac)), thickness=1, parent=dl)

    # Champion breakdown label
    _txt(dl, px+20, py+110, "CHAMPION BREAKDOWN", (*C["gold"][:3], al), 16, "raj_sb_18")

    # Table header
    champ_hdrs = [("CHAMPION",140),("GP",40),("W-L",56),("WR",52),("KDA",50),("K",36),("D",36),("A",36),("DMG",76)]
    hx = px + 16
    hy = py + 136
    dpg.draw_rectangle((px+4, hy-4),(vw-4, hy+22),
                        fill=(*C["card"][:3], int(160*frac)),
                        color=(0,0,0,0), rounding=3, parent=dl)
    for lbl, cw in champ_hdrs:
        _txt(dl, hx, hy, lbl, (*C["txt_dim"][:3], al), 15, "raj_sb_14")
        hx += cw

    champs = _DEMO_CHAMPS.get(name, [])
    row_y2 = hy + 30
    for i, ch in enumerate(champs):
        ry4 = row_y2 + i * 40
        row_bg = C["card"] if i % 2 == 0 else C["panel"]
        dpg.draw_rectangle((px+4, ry4),(vw-4, ry4+36),
                            fill=(*row_bg[:3], int(140*frac)),
                            color=(0,0,0,0), rounding=2, parent=dl)
        try:
            wr_n = float(str(ch["wr"]).replace("%",""))
        except (ValueError, TypeError):
            wr_n = 50.0
        champ_col  = C["win"] if wr_n>=60 else C["loss"] if wr_n<45 else C["gold_lt"]
        wr_col2    = C["win"] if wr_n>=52 else C["loss"] if wr_n<48 else C["txt"]
        vals2 = [ch["champ"], str(ch["games"]),
                 f"{ch['wins']}-{ch['losses']}", f"{ch['wr']}%",
                 str(ch["kda"]), str(ch["kills"]), str(ch["deaths"]),
                 str(ch["assists"]), ch["damage"]]
        cx2 = px + 16
        for vi, (v2, cw) in enumerate(zip(vals2, [cw2 for _,cw2 in champ_hdrs])):
            col2 = champ_col if vi==0 else wr_col2 if vi==3 else C["txt"]
            _txt(dl, cx2, ry4+10, v2, (*col2[:3], al), 13, "raj_14")
            cx2 += cw

    # Sparkline history
    spark_y = row_y2 + len(champs)*40 + 20
    _txt(dl, px+20, spark_y, "RECENT RESULTS  (last 10 games)", (*C["txt_dim"][:3], al), 13, "raj_sb_14")
    history = _LIVE_SPARKLINES.get(name) or _DEMO_SPARKLINES.get(name, [])
    dot_y = spark_y + 28
    dot_spacing = 28
    ox2 = px + 20
    for i, result in enumerate(history):
        dot_x = ox2 + i * dot_spacing
        col3  = C["win"] if result else C["loss"]
        dpg.draw_circle((dot_x, dot_y), 10,
                        fill=(*col3[:3], al), color=(0,0,0,0), parent=dl)
        lbl2 = "W" if result else "L"
        _txt(dl, dot_x-5, dot_y-8, lbl2, (*C["bg"][:3], al), 11, "raj_sb_12")

    # Close hint
    _txt(dl, px+20, vh-72, "Click the same row again to close",
         (*C["txt_dim"][:3], int(al*0.5)), 12, "raj_r_12")
