"""
Inhouse Tab — Phase 5.
Left panel: leaderboard (rank, player, GP, W-L, WR, KDA, Avg DMG, Avg Gold).
Right panel: player detail — slides in on row click, shows champion breakdown + sparkline.
Top-right notification: "GAME LOGGED" card slams in on new game detected.
"""
import math, time, random as _rnd, os, queue as _queue
import dearpygui.dearpygui as dpg
from theme import C, RANK_COLORS, MEDAL_PARTICLE
from core.animations import anim
from data.reader import live, log_inhouse_games_from_client, get_most_games_logged, load_match_history, load_rivalries, load_records, load_h2h_matrix
from data.tips import TIPS as _TIPS
from ui.tierlist import _wheel_delta as _wheel_delta_shared
from ui import effects, toast, fmt, audio, luxe

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
_LIVE_SPARKLINES = {}   # player_name > [0/1, ...] from real game log


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
# Notifications — retired to the unified toast stack (ui/toast.py, Phase 0c).
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Avatar texture registry
# ---------------------------------------------------------------------------
_AVATAR_REG     = "rift_avatar_reg"
_avatar_textures = {}   # display_name (lowercase) > dpg texture tag
# Thread-safe queue: background download/sync threads enqueue (name, path);
# the main render thread drains it via _flush_pending() each frame.
_pending_avatars = _queue.SimpleQueue()
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
                _pending_avatars.put((name, path))
    except Exception as _e:
        print(f"[avatar] _scan_local_avatars failed: {type(_e).__name__}: {_e}")


def _flush_pending():
    """Call from main draw thread to register queued textures."""
    while True:
        try:
            name, path = _pending_avatars.get_nowait()
        except _queue.Empty:
            return
        _register_tex(name, path)


def queue_avatar_reload(name, path):
    """Called from settings after upload completes (may be background thread)."""
    _pending_avatars.put((name, path))


def queue_avatars_reload_all(avatar_map):
    """Called after 'Sync All Avatars' — avatar_map is {name: local_path}."""
    for name, path in avatar_map.items():
        _pending_avatars.put((name, path))


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
    global _log_in_progress
    if _log_in_progress:
        return
    _log_in_progress = True

    def _done(count):
        global _log_in_progress, _most_games_fetched
        _log_in_progress = False
        if count and count > 0:
            n = int(count)
            toast.push(f"Logged {n} new game{'s' if n != 1 else ''}.",
                       kind="success", title="Inhouse")
            if live.inhouse:
                update_live_data(live.inhouse, live.inhouse_champs)
                inhouse.begin_load(live.inhouse)
            _most_games_fetched = False
            _fetch_most_games_once()
        else:
            toast.push("No new games found.", kind="info", title="Inhouse")

    def _error(msg):
        global _log_in_progress
        _log_in_progress = False
        toast.push(str(msg)[:80], kind="error", title="Log game failed")

    log_inhouse_games_from_client(on_done=_done, on_error=_error)

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
        self.scroll_off    = 0     # rows-only scroll offset in px
        # Phase 3 — match-history toggle. "leaderboard" (current standings) or
        # "history" (per-game card feed pulled from /api/matches).
        self.view_mode     = "leaderboard"
        self.history_scroll = 0
        self.history_loading = False
        # Phase 3 — per-game detail panel (history view).
        self.selected_match_id   = None
        self.match_detail_x_frac = 0.0
        self.match_detail_scroll = 0
        # Phase 3 — rivalries view: anchor player + per-anchor scroll.
        self.rivalries_anchor    = None
        self.rivalries_scroll    = 0
        # v4.0.5 — rivalries view is now the H2H MATRIX. Selected pair (row,
        # col) drives the drill-down panel below the grid. Mode toggle picks
        # which stats render in each cell.
        self.matrix_mode         = "vs"      # "vs" | "with" | "combined"
        self.matrix_selected     = None      # (row_display, col_display)
        self.matrix_load_kicked  = False     # one-shot loader gate

    def reset(self):
        self.__init__()

    def tick(self):
        self._load_t += 0.04

    def begin_load(self, players):
        self.reset()
        self.scroll_off = 0
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

    def select_match(self, match_id):
        """Toggle the per-game detail panel for a match card."""
        if not match_id:
            return
        if self.selected_match_id == match_id:
            self.selected_match_id = None
            anim.tween(self.match_detail_x_frac, 0.0, 220, "out_cubic",
                       on_update=lambda v: setattr(self, "match_detail_x_frac", v))
        else:
            already_open = self.selected_match_id is not None
            self.selected_match_id = match_id
            self.match_detail_scroll = 0
            if not already_open:
                anim.tween(0.0, 1.0, 280, "out_cubic",
                           on_update=lambda v: setattr(self, "match_detail_x_frac", v))


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
DETAIL_W  = 560   # fixed width of sliding detail panel (player)
MATCH_DETAIL_W = 680   # per-game detail panel (history view)

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

def _ensure_filter_window(vw, vh, filter_w, show=True):
    """Create or reposition the search-bar overlay window.
    filter_w clips it to the leaderboard area so it never bleeds into the detail panel.
    Set show=False to hide the bar on views (history / records) where filtering by
    player name doesn't apply — leaving it visible looks like a dead black bar."""
    sidebar_w = dpg.get_viewport_width() - vw   # dynamic sidebar width
    win_x     = sidebar_w
    win_y     = _VP_TITLE_H + TOP_BAR_H

    if not dpg.does_item_exist(_INHOUSE_FILTER_WIN):
        if not show:
            return
        with dpg.window(tag=_INHOUSE_FILTER_WIN,
                        pos=(win_x, win_y),
                        width=filter_w, height=FILTER_H,
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
                           width=filter_w, height=FILTER_H,
                           show=show)


def draw_inhouse(dl, vw, vh, fonts=None):
    if fonts:
        set_fonts(fonts)
    _scan_local_avatars()
    _flush_pending()
    inhouse.tick()
    dpg.delete_item(dl, children_only=True)
    dpg.draw_rectangle((0, 0), (vw, 3000), fill=C["bg"], color=(0,0,0,0), parent=dl)
    # V2 ambient — broad cool top-light so the page has depth under the table.
    luxe.glow(dl, vw * 0.5, -vh * 0.25, vw * 0.75, (40, 72, 118), 55)

    # Keep native window scroll locked — rows are scrolled via scroll_off instead
    if dpg.does_item_exist("content_win"):
        dpg.set_y_scroll("content_win", 0)

    if inhouse.phase == InhousePhase.IDLE:
        _draw_idle(dl, vw, vh)
        return
    if inhouse.phase == InhousePhase.LOADING:
        _draw_loading(dl, vw, vh)
        return

    # Detail panel slide: only the view-mode's panel reserves space.
    # Player-detail panel (leaderboard mode) vs match-detail panel (history mode).
    detail_open = (inhouse.view_mode == "leaderboard"
                   and inhouse.detail_x_frac > 0.01)
    detail_px   = int(DETAIL_W * inhouse.detail_x_frac) if detail_open else 0
    match_detail_open = (inhouse.view_mode == "history"
                         and inhouse.match_detail_x_frac > 0.01)
    match_detail_px   = int(MATCH_DETAIL_W * inhouse.match_detail_x_frac) if match_detail_open else 0
    right_px    = detail_px + match_detail_px  # one of these is always 0
    table_w     = vw - PAD*2 - right_px
    # header_w tracks the left edge of any right-side panel so bars never bleed over
    header_w    = vw - right_px

    # Search filter is only meaningful on the leaderboard + rivalries views.
    # Hide it on history / records so it doesn't sit as a dead black bar.
    show_filter = inhouse.view_mode in ("leaderboard", "rivalries")
    _ensure_filter_window(vw, vh, header_w, show=show_filter)

    table_top = TOP_BAR_H + (FILTER_H + 4 if show_filter else 8)
    if inhouse.view_mode == "history":
        _draw_history(dl, PAD, table_top, table_w - PAD,
                      vh - table_top - PAD, vw, vh)
    elif inhouse.view_mode == "rivalries":
        try:
            _draw_rivalries(dl, PAD, table_top, table_w - PAD,
                            vh - table_top - PAD, vw, vh)
        except Exception as _riv_e:
            import traceback as _tb
            _tb.print_exc()
            _txt(dl, PAD, table_top + 60,
                 f"Rivalries failed to render: {type(_riv_e).__name__}: {_riv_e}",
                 (*C["loss"][:3], 230), 16, "raj_r_16")
    elif inhouse.view_mode == "records":
        _draw_records(dl, PAD, table_top, table_w - PAD,
                      vh - table_top - PAD, vw, vh)
    else:
        _draw_leaderboard(dl, PAD, table_top, table_w - PAD,
                          vh - table_top - PAD, vw, vh)
    # Draw top bar AFTER rows so it renders on top of any scrolled-up rows
    _draw_top_bar(dl, vw, header_w)
    # Cinematic vignette — under the slide-in panels so they stay crisp.
    luxe.vignette(dl, 0, 0, vw, vh, 60)
    if detail_open:
        _draw_detail_panel(dl, vw, vh)
    if match_detail_open:
        _pred_hits.clear()
        _draw_match_detail_panel(dl, vw, vh)
        _handle_prediction_clicks()


def _draw_idle(dl, vw, vh):
    # If live data is already here, skip the idle screen entirely
    if live.loaded and live.inhouse:
        update_live_data(live.inhouse, live.inhouse_champs)
        inhouse.begin_load(live.inhouse)
        return

    cx, cy = vw//2, vh//2
    t = (math.sin(time.monotonic()*1.3)+1)/2
    a = int(90 + t*110)
    _txt(dl, cx-220, cy-30, "IN-HOUSE CUSTOMS", (*C["gold"][:3], a), 36, "cinzel_36")
    hint = "Connecting to Google Sheets…" if not live.loaded else "No in-house data found"
    _txt(dl, cx-165, cy+14, hint, (*C["txt_dim"][:3], int(a*0.6)), 19, "raj_18")


def _draw_loading(dl, vw, vh):
    """Skeleton of the leaderboard — rows morph into real standings on load."""
    rx = PAD
    ry = TOP_BAR_H + FILTER_H + 4 + HEADER_H + 4
    rw = vw - PAD * 2
    for i in range(12):
        effects.draw_skeleton_row(dl, rx, ry + i * (ROW_H + 2), rw, ROW_H)
    tip = inhouse._tip
    _txt(dl, max(40, vw // 2 - len(tip) * 5), vh - 44, tip,
         (*C["txt_dim"][:3], 150), 18, "raj_r_18")


def _draw_top_bar(dl, vw, header_w):
    """header_w = width of the area this bar owns (stops at detail-panel left edge)."""
    _fetch_most_games_once()
    # V2 broadcast header — gradient surface + gold bottom edge light.
    dpg.draw_rectangle((0,0),(header_w,TOP_BAR_H), fill=C["navy_deep"],
                        color=(0,0,0,0), parent=dl)
    luxe.vfade(dl, 0, 0, header_w, TOP_BAR_H, (44, 74, 116), 46, solid="top")
    luxe.vfade(dl, 0, TOP_BAR_H - 10, header_w, TOP_BAR_H - 1,
               C["gold"], 26, solid="bottom")
    dpg.draw_line((0,TOP_BAR_H-1),(header_w,TOP_BAR_H-1),
                  color=(*C["gold_dk"][:3], 200), thickness=1, parent=dl)
    luxe.glow(dl, PAD + 6, TOP_BAR_H // 2, 26, C["gold"], 55)
    _txt(dl, PAD, 12, "IN-HOUSE CUSTOMS", (*C["gold_lt"][:3],235), 23, "raj_24")
    _txt(dl, PAD+256, 18, "Click a player row to view champion breakdown",
         (*C["txt_dim"][:3],160), 17, "raj_r_16")

    # "LOG GAME" button — anchored to header_w right edge
    bw, bh = 160, 36
    bx = header_w - bw - PAD
    by = (TOP_BAR_H - bh)//2
    is_logging = _log_in_progress
    btn_lbl  = "LOGGING…"            if is_logging else "LOG GAME"
    lbl_col  = (*C["txt_dim"][:3], 160) if is_logging else (*C["gold_lt"][:3], 245)
    if is_logging:
        dpg.draw_rectangle((bx,by),(bx+bw,by+bh),
                            fill=(*C["card"][:3], 200),
                            color=(*C["gold"][:3], 80), rounding=4, parent=dl)
    else:
        luxe.glow(dl, bx + bw / 2, by + bh / 2, bh * 1.15, C["gold"], 34)
        luxe.panel(dl, bx, by, bx + bw, by + bh, (116, 90, 44, 235),
                   corner=4, border=C["gold"], border_a=210, sheen=95)
    _txt(dl, bx+14, by+8, btn_lbl, lbl_col, 16, "raj_sb_16")

    # Phase 3 — view-mode segmented control: LEADER | HISTORY | RIVALS | RECORDS
    pill_w = 80
    seg_gap = 4
    segments = (("LEADER",  "leaderboard"),
                ("HISTORY", "history"),
                ("RIVALS",  "rivalries"),
                ("RECORDS", "records"))
    seg_w = pill_w * len(segments) + seg_gap * (len(segments) - 1)
    seg_x = bx - seg_w - 12
    seg_y = by
    for i, (lbl, mode) in enumerate(segments):
        p_x = seg_x + i * (pill_w + seg_gap)
        is_active = (inhouse.view_mode == mode)
        if is_active:
            luxe.glow(dl, p_x + pill_w / 2, seg_y + bh / 2, bh,
                      C["gold"], 38)
            luxe.panel(dl, p_x, seg_y, p_x + pill_w, seg_y + bh,
                       (116, 90, 44, 235), corner=4,
                       border=C["gold"], border_a=220, sheen=90)
            lblc = (*C["gold_lt"][:3], 250)
        else:
            dpg.draw_rectangle((p_x, seg_y), (p_x + pill_w, seg_y + bh),
                               fill=(*C["card"][:3], 200),
                               color=(*C["gold"][:3], 70),
                               rounding=4, parent=dl)
            lblc = (*C["txt2"][:3], 200)
        # Center the label inside the pill.
        text_off = max(0, (pill_w - len(lbl) * 9) // 2)
        _txt(dl, p_x + text_off, seg_y + 8, lbl, lblc, 15, "raj_sb_16")

    # Most Games Logged label (left of segmented control)
    if _most_games_player:
        mg_lbl = f"Most Games Logged:  {_most_games_player}"
        _txt(dl, seg_x - 280, by + 10, mg_lbl,
             (*C["txt2"][:3], 200), 17, "raj_r_16")

    if dpg.is_mouse_button_clicked(0):
        mouse = dpg.get_mouse_pos(local=False)
        vp    = dpg.get_viewport_pos()
        rx = mouse[0]-vp[0]-68; ry = mouse[1]-vp[1]-52
        if not is_logging and bx<=rx<=bx+bw and by<=ry<=by+bh:
            _start_log_game()
        # Segmented-control clicks
        if seg_y <= ry <= seg_y + bh:
            for i, (_, mode) in enumerate(segments):
                p_x = seg_x + i * (pill_w + seg_gap)
                if p_x <= rx <= p_x + pill_w and inhouse.view_mode != mode:
                    _set_view_mode(mode)
                    break


def _set_view_mode(target):
    """Switch the Inhouse tab to one of: leaderboard, history, rivalries.
    Closes any cross-mode slide-in panel so the layout reflows cleanly,
    and kicks off a one-shot load for the destination mode if needed."""
    if target == inhouse.view_mode:
        return
    # Close cross-mode slide-in panels before changing the layout.
    if inhouse.selected:
        inhouse.select(inhouse.selected)
    if inhouse.selected_match_id:
        inhouse.select_match(inhouse.selected_match_id)
    inhouse.view_mode = target
    if target == "history":
        inhouse.history_scroll = 0
        if not live.match_history_loaded and not inhouse.history_loading:
            inhouse.history_loading = True
            def _done(_n): inhouse.history_loading = False
            def _err(_msg): inhouse.history_loading = False
            load_match_history(on_done=_done, on_error=_err)
    elif target == "rivalries":
        # v4.0.5 — fire the matrix loader on first entry. The grid is keyed
        # on display names (loader resolves to riot summoner names under the
        # hood), so the empty-state bug from the per-anchor view is gone.
        if (not live.h2h_matrix_loaded
                and not inhouse.matrix_load_kicked):
            inhouse.matrix_load_kicked = True
            load_h2h_matrix()
        inhouse.rivalries_scroll = 0
    elif target == "records":
        # Kick off load on first entry; cheap to recompute server-side.
        if not live.records_loaded and not live._records_inflight:
            load_records()


def _set_rivalries_anchor(name):
    """Set the rivalries-view anchor and kick off a load if the cache is cold."""
    if not name:
        return
    inhouse.rivalries_anchor = name
    inhouse.rivalries_scroll = 0
    if not live.rivalries_loaded.get(name):
        load_rivalries(name)


def _draw_history(dl, tx, ty, tw, th, vw, vh):
    """Phase 3 — match-history card feed. Each logged custom-game card shows
    the date, duration, winner side, and all 10 champion picks in role order."""
    matches = list(live.match_history or [])

    # Loading skeleton
    if (inhouse.history_loading or
            (not live.match_history_loaded and not live.match_history_error)):
        skel_y = ty + 20
        for i in range(4):
            effects.draw_skeleton_row(dl, tx, skel_y + i*100, tw, 84)
        _txt(dl, tx, ty + 0, "MATCH HISTORY", (*C["gold"][:3], 220), 21, "raj_sb_18")
        _txt(dl, tx + 200, ty + 4, "loading…",
             (*C["txt_dim"][:3], 200), 17, "raj_r_16")
        return

    # Error / empty
    if live.match_history_error and not matches:
        _txt(dl, tx, ty + 0, "MATCH HISTORY", (*C["gold"][:3], 220), 21, "raj_sb_18")
        _txt(dl, tx, ty + 60, f"Could not load history: {live.match_history_error[:80]}",
             (*C["loss"][:3], 220), 17, "raj_r_16")
        return
    if not matches:
        _txt(dl, tx, ty + 0, "MATCH HISTORY", (*C["gold"][:3], 220), 21, "raj_sb_18")
        _txt(dl, tx, ty + 60,
             "No matches yet. Log an inhouse game to seed the feed.",
             (*C["txt_dim"][:3], 200), 17, "raj_r_16")
        return

    # Header
    _txt(dl, tx, ty + 0, f"MATCH HISTORY  ·  {len(matches)} games",
         (*C["gold"][:3], 220), 21, "raj_sb_18")
    _txt(dl, tx + 280, ty + 4,
         "Click any card for the full scoreboard, draft & predictions.",
         (*C["txt_dim"][:3], 180), 14, "raj_r_14")

    # Wheel-scroll
    card_h = 164
    card_gap = 12
    visible_h = th - 40
    total_h = len(matches) * (card_h + card_gap)
    max_scroll = max(0, total_h - visible_h)
    if _wheel_delta_shared[0] != 0:
        inhouse.history_scroll = max(0, min(
            inhouse.history_scroll - _wheel_delta_shared[0] * 30, max_scroll))
        _wheel_delta_shared[0] = 0
    inhouse.history_scroll = max(0, min(inhouse.history_scroll, max_scroll))

    scroll = int(inhouse.history_scroll)
    cards_top = ty + 40
    cards_bot = ty + th - 8

    # Cursor in content coords — same offset convention as other inhouse handlers.
    _m  = dpg.get_mouse_pos(local=False)
    _vp = dpg.get_viewport_pos()
    mrx = _m[0] - _vp[0] - 68
    mry = _m[1] - _vp[1] - 52
    clicked = dpg.is_mouse_button_clicked(0)

    for i, m in enumerate(matches):
        cy = cards_top + i * (card_h + card_gap) - scroll
        if cy + card_h < cards_top or cy > cards_bot:
            continue
        mid = m.get("id") or ""
        is_hov = (tx <= mrx <= tx + tw and cy <= mry <= cy + card_h)
        is_sel = (mid and mid == inhouse.selected_match_id)
        _draw_match_card(dl, tx, cy, tw, card_h, m, is_hov=is_hov, is_sel=is_sel)
        if clicked and is_hov:
            audio.play_click()
            inhouse.select_match(mid)
            clicked = False  # consume the click so a second card can't also fire


def _draw_match_card(dl, x, y, w, h, m, is_hov=False, is_sel=False):
    """One match card: scoreboard summary across both teams.
    Lays out a header row (date/duration/winner) plus two team rows of 5
    champion+player+KDA cells so the user can read the whole game at a glance."""
    # Card chrome — selected/hover states layered on top of the base fill.
    glow = effects.hover_amt(f"match_card_{m.get('id','')}", is_hov or is_sel)
    base_fill = (*C["card"][:3], 240)
    border_a  = 60 + int(160 * glow) + (60 if is_sel else 0)
    border_a  = min(255, border_a)
    dpg.draw_rectangle((x, y), (x + w, y + h),
                       fill=base_fill,
                       color=(*C["gold"][:3], border_a),
                       rounding=8, parent=dl)
    if is_sel:
        effects.draw_hover_glow(dl, x, y, x + w, y + h,
                                C["gold"], amt=0.7, rounding=8, spread=2)
    winner = (m.get("winner") or "").lower()
    accent = _BLUE_COL if winner == "blue" else (
              _RED_COL if winner == "red" else (160, 160, 170))
    # Side accent stripe on winner edge.
    dpg.draw_rectangle((x, y), (x + 4, y + h),
                       fill=(*accent, 220), color=(0, 0, 0, 0), parent=dl)

    # ----- Header strip -----
    ts_raw = (m.get("started_at") or "").replace("T", " ").replace("Z", "")
    dur_sec = int(m.get("duration") or 0)
    dur_lbl = fmt.duration(dur_sec) if hasattr(fmt, "duration") else (
              f"{dur_sec // 60}m {dur_sec % 60:02d}s")
    date_str = _fmt_date(ts_raw[:10])
    time_str = ts_raw[11:16] if len(ts_raw) >= 16 else ""
    header_line = f"{date_str}  ·  {time_str}  ·  {dur_lbl}"
    _txt(dl, x + 18, y + 10, header_line,
         (*C["txt"][:3], 230), 15, "raj_sb_16")
    sub_parts = []
    src = m.get("source") or ""
    if src:
        sub_parts.append(src.upper())
    if m.get("queue"):
        sub_parts.append(str(m["queue"]))
    if sub_parts:
        _txt(dl, x + 18, y + 30, "  ·  ".join(sub_parts),
             (*C["txt_dim"][:3], 180), 13, "raj_r_14")

    # Winner banner — right side.
    banner_w = 130
    bx = x + w - banner_w - 14
    by = y + 10
    banner_label = (f"{winner.upper()} WINS" if winner else "PENDING")
    dpg.draw_rectangle((bx, by), (bx + banner_w, by + 28),
                       fill=(*accent, 220), color=(*accent, 240),
                       rounding=5, parent=dl)
    label_off = max(0, (banner_w - len(banner_label) * 9) // 2)
    _txt(dl, bx + label_off, by + 5, banner_label,
         (255, 255, 255, 245), 16, "raj_sb_16")

    # Headline KDA — best performer per team.
    parts = m.get("participants") or []
    blue = sorted([p for p in parts if (p.get("team") or "").lower() == "blue"],
                  key=lambda p: _role_order(p.get("role", "")))
    red  = sorted([p for p in parts if (p.get("team") or "").lower() == "red"],
                  key=lambda p: _role_order(p.get("role", "")))

    # ----- Team rows -----
    # Two rows of 5 cells each; each cell shows ROLE / CHAMP / PLAYER / KDA.
    row_y_blue = y + 52
    row_y_red  = y + 104
    row_h = 48
    inner_x = x + 14
    inner_w = w - 28
    cell_gap = 6
    cells_per_row = 5
    cell_w = max(80, (inner_w - cell_gap * (cells_per_row - 1)) // cells_per_row)
    _draw_match_team_row(dl, inner_x, row_y_blue, cell_w, row_h, cell_gap,
                         blue, _BLUE_COL, "BLUE", winner == "blue")
    _draw_match_team_row(dl, inner_x, row_y_red, cell_w, row_h, cell_gap,
                         red, _RED_COL, "RED", winner == "red")


def _draw_match_team_row(dl, x, y, cell_w, cell_h, gap, players, side_color,
                          team_label, is_winner):
    """One team's row of 5 player cells inside a match card.
    Text bumped up + bold across the board per user feedback — the cells have
    room and the layout now reads from across the screen."""
    dpg.draw_rectangle((x - 8, y), (x - 2, y + cell_h),
                       fill=(*side_color, 220 if is_winner else 130),
                       color=(0, 0, 0, 0), rounding=2, parent=dl)
    for i in range(5):
        cx = x + i * (cell_w + gap)
        p = players[i] if i < len(players) else None
        fill_a = 230 if p else 90
        bdr_a  = 130 if is_winner else 80
        dpg.draw_rectangle((cx, y), (cx + cell_w, y + cell_h),
                           fill=(*C["panel"][:3], fill_a),
                           color=(*side_color, bdr_a),
                           rounding=4, parent=dl)
        if not p:
            _txt(dl, cx + 10, y + cell_h // 2 - 8, "—",
                 (*C["txt_dim"][:3], 160), 16, "raj_sb_18")
            continue
        role = (p.get("role") or "").upper()[:3]
        champ = (p.get("champion") or "?").strip()
        name  = (p.get("player") or "?").strip()
        kills = int(p.get("kills") or 0)
        deaths = int(p.get("deaths") or 0)
        assists = int(p.get("assists") or 0)
        win = bool(p.get("win"))
        # Role pill (top-left).
        if role:
            role_w = 36
            dpg.draw_rectangle((cx + 4, y + 4), (cx + 4 + role_w, y + 22),
                               fill=(*side_color, 220),
                               color=(0, 0, 0, 0), rounding=2, parent=dl)
            _txt(dl, cx + 9, y + 6, role,
                 (255, 255, 255, 250), 14, "raj_sb_16")
        # Champion (row 1, right of role pill).
        max_c = max(6, (cell_w - 46) // 8)
        champ_disp = champ if len(champ) <= max_c else champ[:max_c-1] + "…"
        _txt(dl, cx + 46, y + 6, champ_disp,
             (*C["gold_lt"][:3], 245), 16, "raj_sb_18")
        # Player name (row 2).
        max_n = max(6, cell_w // 9)
        name_disp = name if len(name) <= max_n else name[:max_n-1] + "…"
        _txt(dl, cx + 6, y + 28, name_disp.upper(),
             (*C["txt"][:3], 235), 14, "raj_sb_16")
        # KDA bottom-right.
        kda_str = f"{kills}/{deaths}/{assists}"
        kda_x = cx + cell_w - len(kda_str) * 9 - 8
        kda_color = (*C["gold_lt"][:3], 240) if win else (*C["txt_dim"][:3], 220)
        _txt(dl, kda_x, y + 28, kda_str, kda_color, 15, "raj_sb_18")


_ROLE_ORDER = {"TOP": 0, "JGL": 1, "MID": 2, "BOT": 3, "SUP": 4}


def _role_order(role):
    r = (role or "").upper()
    return _ROLE_ORDER.get(r, 5 + sum(ord(c) for c in r))


def _draw_champ_strip(dl, x, y, w, players, side_color):
    """Five chip-sized champion tiles, with role + abbreviated champ name."""
    n = max(1, len(players))
    cell_w = w // n
    for i, p in enumerate(players[:5]):
        cx = x + i * cell_w
        # Cell bg
        dpg.draw_rectangle((cx, y), (cx + cell_w - 4, y + 26),
                           fill=(*C["panel"][:3], 240),
                           color=(*side_color, 100),
                           rounding=3, parent=dl)
        role = (p.get("role") or "").upper()
        champ = (p.get("champion") or "?").strip()
        # Trim champ name to fit
        max_c = max(6, cell_w // 9)
        display_champ = champ if len(champ) <= max_c else champ[:max_c-1] + "…"
        _txt(dl, cx + 6, y + 4, role[:3], (*side_color, 220), 12, "raj_sb_14")
        _txt(dl, cx + 38, y + 4, display_champ,
             (*C["txt"][:3], 230), 13, "raj_r_14")


# v4.0.5 — rivalries is now a full H2H matrix: rows × cols of every roster
# player against every other, color-coded by win rate, with a VS / WITH /
# COMBINED mode toggle and a click-to-drill panel below the grid.

_MATRIX_MODES = (("VS", "vs"), ("WITH", "with"), ("COMBINED", "combined"))

# Click hit rects emitted by _draw_rivalries each frame:
#   (kind, x, y, w, h, payload)
# kind = "matrix_mode" (payload = mode str) | "matrix_cell" (payload = (row, col))
_matrix_hits: list = []


def _inhouse_mouse_xy():
    """v4.0.5 — content-drawlist mouse position. Replaces the old
    `(mouse - vp - 68, mouse - vp - 52)` idiom that broke when the sidebar
    animated open. Reads the actual content_dl rect_min."""
    try:
        mouse = dpg.get_mouse_pos(local=False)
        vp = dpg.get_viewport_pos()
        st = dpg.get_item_state("content_dl") or {}
        rm = st.get("rect_min")
        if rm and len(rm) >= 2:
            return (mouse[0] - float(rm[0]),
                    mouse[1] - float(rm[1]))
        # Fallback: legacy collapsed-sidebar offsets.
        return (mouse[0] - vp[0] - 68, mouse[1] - vp[1] - 52)
    except Exception:
        return (0.0, 0.0)


def _matrix_cell_stats(stats, mode):
    """Pick (wins, games) for a given mode out of a single cell's stat dict.
    Returns (0, 0) when the slot is empty / missing."""
    if not stats:
        return 0, 0
    gv = int(stats.get("games_vs") or 0)
    wv = int(stats.get("wins_vs") or 0)
    gw = int(stats.get("games_with") or 0)
    ww = int(stats.get("wins_with") or 0)
    if mode == "vs":
        return wv, gv
    if mode == "with":
        return ww, gw
    return wv + ww, gv + gw   # combined


def _matrix_cell_color(wins, games):
    """Map (wins, games) → (fill_rgb, txt_rgb, alpha). 50% lands on neutral
    navy; brighter on the wing → fewer rows. Brightness scales with sample
    size so 1-game outliers don't shout."""
    if games <= 0:
        return ((26, 38, 60), (110, 122, 140), 70)
    wr = wins / games
    # Sample-size confidence — fully saturated by 10 games.
    conf = min(1.0, games / 10.0)
    # Distance from 50%, scaled by conf, gives saturation.
    sat = abs(wr - 0.5) * 2.0 * conf      # 0..1
    if wr >= 0.5:
        # Green wing — blend navy → win color.
        base = (95, 201, 122)   # C["win"] approx
    else:
        base = (226, 106, 106)  # C["loss"] approx
    navy = (28, 40, 64)
    fill = tuple(int(navy[i] + (base[i] - navy[i]) * sat) for i in range(3))
    # Text color: navy on bright cells, txt on faded.
    if sat >= 0.45:
        txt = (10, 20, 40)
    else:
        txt = (217, 222, 234)
    return (fill, txt, 230)


def _draw_rivalries(dl, tx, ty, tw, th, vw, vh):
    """v4.0.5 — H2H MATRIX. Replaces the per-anchor rivalries table with a
    grid of every roster player against every other. Color = win rate. Click
    a cell to drill into that pair below the grid. VS / WITH / COMBINED mode
    toggle in the header.

    Names are display-name on both axes — the loader resolves to riot
    summoner names server-side, so the old empty-state bug is gone."""
    _matrix_hits.clear()

    # ── Header strip ───────────────────────────────────────────────────
    _txt(dl, tx, ty + 0, "HEAD-TO-HEAD MATRIX",
         (*C["gold"][:3], 220), 21, "raj_sb_18")
    _txt(dl, tx, ty + 26,
         "Row beats column. Color = win rate · brightness = sample size · click a cell to drill in.",
         (*C["txt_dim"][:3], 180), 14, "raj_r_14")

    # Mode toggle (VS / WITH / COMBINED) — right-aligned on the header line.
    pill_h = 26
    pill_w = 92
    pill_gap = 4
    seg_x = tx + tw - (pill_w * len(_MATRIX_MODES) + pill_gap * (len(_MATRIX_MODES) - 1))
    seg_y = ty - 2
    for i, (lbl, mode) in enumerate(_MATRIX_MODES):
        px = seg_x + i * (pill_w + pill_gap)
        is_active = (inhouse.matrix_mode == mode)
        fill = (*C["gold_dk"][:3], 200) if is_active else (*C["card"][:3], 200)
        bdr  = (*C["gold"][:3], 220)    if is_active else (*C["gold"][:3], 80)
        lblc = (*C["gold_lt"][:3], 240) if is_active else (*C["txt2"][:3], 200)
        dpg.draw_rectangle((px, seg_y), (px + pill_w, seg_y + pill_h),
                           fill=fill, color=bdr, rounding=4, parent=dl)
        text_off = max(0, (pill_w - len(lbl) * 8) // 2)
        _txt(dl, px + text_off, seg_y + 5, lbl, lblc, 14, "raj_sb_14")
        _matrix_hits.append(("matrix_mode", px, seg_y, pill_w, pill_h, mode))

    # ── Roster ─────────────────────────────────────────────────────────
    # The loader is keyed on live.players (display names). Filter via the
    # top-bar search field too so the matrix obeys it.
    roster = list(live.players or [])
    ft = inhouse.filter_text.strip().lower()
    if ft:
        roster = [n for n in roster if ft in n.lower()]

    grid_top = ty + 60

    # Loading / empty / error states.
    matrix = live.h2h_matrix or {}
    if not live.h2h_matrix_loaded:
        for i in range(8):
            effects.draw_skeleton_row(dl, tx, grid_top + i * 40, tw, 32)
        return
    if live.h2h_matrix_error and not matrix:
        _txt(dl, tx, grid_top, f"Could not load matrix: {str(live.h2h_matrix_error)[:80]}",
             (*C["loss"][:3], 230), 16, "raj_r_16")
        return
    if not roster:
        _txt(dl, tx, grid_top, "No roster — load inhouse data first.",
             (*C["txt_dim"][:3], 220), 16, "raj_sb_16")
        return

    # ── Geometry ──────────────────────────────────────────────────────
    n = len(roster)
    # Drill-down panel below grid takes ~150px; reserve that.
    drill_h = 150
    avail_w = tw - 20
    avail_h = (ty + th) - grid_top - drill_h - 20
    row_lbl_w = max(86, min(110, avail_w // (n + 3)))
    col_hdr_h = 36
    # Cell size — keep cells roughly square, bounded so tiny rosters don't
    # explode and huge ones don't shrink past readability.
    cell_w = max(38, min(64, (avail_w - row_lbl_w) // max(n, 1)))
    cell_h = max(32, min(48, (avail_h - col_hdr_h) // max(n, 1)))
    grid_x0 = tx + 8 + row_lbl_w
    grid_y0 = grid_top + col_hdr_h
    grid_x1 = grid_x0 + cell_w * n
    grid_y1 = grid_y0 + cell_h * n

    # ── Column headers (top, abbreviated) ─────────────────────────────
    for j, col_name in enumerate(roster):
        cx = grid_x0 + j * cell_w
        # Highlight the selected column.
        sel = inhouse.matrix_selected
        is_sel_col = (sel is not None and sel[1] == col_name)
        col_hdr_bg = (*C["card"][:3], 200 if is_sel_col else 130)
        col_hdr_bdr = (*C["gold"][:3], 200 if is_sel_col else 60)
        dpg.draw_rectangle((cx + 1, grid_top + 4),
                           (cx + cell_w - 1, grid_y0 - 2),
                           fill=col_hdr_bg, color=col_hdr_bdr,
                           rounding=3, parent=dl)
        # Abbreviated name centered in the column header.
        abbr = col_name[:5].upper()
        text_off = max(2, (cell_w - len(abbr) * 7) // 2)
        _txt(dl, cx + text_off, grid_top + 14, abbr,
             (*C["gold_lt"][:3], 235 if is_sel_col else 210), 13, "raj_sb_14")

    # ── Row labels + cells ────────────────────────────────────────────
    mode = inhouse.matrix_mode
    mx, my = _inhouse_mouse_xy()
    selected = inhouse.matrix_selected
    for i, row_name in enumerate(roster):
        ry = grid_y0 + i * cell_h
        # Row label (right-aligned to the grid edge).
        is_sel_row = (selected is not None and selected[0] == row_name)
        row_bg = (*C["card"][:3], 200 if is_sel_row else 130)
        row_bdr = (*C["gold"][:3], 200 if is_sel_row else 60)
        dpg.draw_rectangle((tx + 4, ry + 1),
                           (grid_x0 - 2, ry + cell_h - 1),
                           fill=row_bg, color=row_bdr,
                           rounding=3, parent=dl)
        # Truncate to fit the column.
        max_chars = max(4, row_lbl_w // 8)
        rlbl = row_name[:max_chars].upper()
        _txt(dl, tx + 12, ry + (cell_h - 14) // 2, rlbl,
             (*C["gold_lt"][:3], 235 if is_sel_row else 215),
             13, "raj_sb_14")

        row_stats = matrix.get(row_name) or {}
        for j, col_name in enumerate(roster):
            cx = grid_x0 + j * cell_w
            if row_name == col_name:
                # Self-cell: dim diagonal slash.
                dpg.draw_rectangle((cx + 1, ry + 1),
                                   (cx + cell_w - 1, ry + cell_h - 1),
                                   fill=(*C["bg"][:3], 200),
                                   color=(0, 0, 0, 0), parent=dl)
                _txt(dl, cx + cell_w // 2 - 4, ry + (cell_h - 12) // 2,
                     "—", (*C["txt_dim"][:3], 150), 12, "raj_r_14")
                continue
            stats = row_stats.get(col_name)
            wins, games = _matrix_cell_stats(stats, mode)
            fill_rgb, txt_rgb, alpha = _matrix_cell_color(wins, games)
            # Hover highlight.
            is_hov = (cx <= mx <= cx + cell_w
                      and ry <= my <= ry + cell_h)
            border_a = 235 if is_hov else (180 if (
                selected is not None and selected == (row_name, col_name))
                else 70)
            dpg.draw_rectangle((cx + 1, ry + 1),
                               (cx + cell_w - 1, ry + cell_h - 1),
                               fill=(*fill_rgb, alpha),
                               color=(*C["gold"][:3], border_a),
                               thickness=2 if (is_hov or border_a > 200) else 1,
                               rounding=3, parent=dl)
            if games > 0:
                losses = games - wins
                rec = f"{wins}-{losses}"
                rec_off = max(2, (cell_w - len(rec) * 7) // 2)
                _txt(dl, cx + rec_off, ry + (cell_h - 13) // 2,
                     rec, (*txt_rgb, 240), 13, "raj_sb_14")
            else:
                _txt(dl, cx + cell_w // 2 - 4, ry + (cell_h - 12) // 2,
                     "·", (*C["txt_dim"][:3], 130), 14, "raj_r_14")
            _matrix_hits.append(("matrix_cell", cx, ry, cell_w, cell_h,
                                 (row_name, col_name)))

    # ── Legend (left) + summary chip (right) ─────────────────────────
    leg_y = grid_y1 + 8
    swatch_w = 16
    swatches = [
        ((226, 106, 106), "≤25%"),
        ((178, 90, 100),  "40%"),
        ((40, 56, 80),    "≈50%"),
        ((150, 178, 110), "60%"),
        ((95, 201, 122),  "≥75%"),
    ]
    lx = tx + 8
    _txt(dl, lx, leg_y + 2, "WIN-RATE",
         (*C["txt_dim"][:3], 200), 11, "raj_sb_12")
    lx += 70
    for col, lbl in swatches:
        dpg.draw_rectangle((lx, leg_y),
                           (lx + swatch_w, leg_y + 14),
                           fill=(*col, 220), color=(0, 0, 0, 0),
                           rounding=2, parent=dl)
        _txt(dl, lx + swatch_w + 4, leg_y + 1, lbl,
             (*C["txt"][:3], 220), 11, "raj_r_12")
        lx += swatch_w + 4 + len(lbl) * 7 + 12

    # ── Drill-down panel ─────────────────────────────────────────────
    drill_y0 = leg_y + 24
    drill_y1 = ty + th - 8
    _draw_matrix_drilldown(dl, tx, drill_y0, tw, drill_y1, selected, matrix)

    # ── Click handling (consume hits emitted above) ──────────────────
    if dpg.is_mouse_button_clicked(0):
        for kind, hx, hy, hw, hh, payload in list(_matrix_hits):
            if not (hx <= mx <= hx + hw and hy <= my <= hy + hh):
                continue
            if kind == "matrix_mode":
                if inhouse.matrix_mode != payload:
                    inhouse.matrix_mode = payload
                    audio.play_click()
                break
            if kind == "matrix_cell":
                row_name, col_name = payload
                if row_name == col_name:
                    break
                # Toggle off if same cell clicked again.
                if inhouse.matrix_selected == payload:
                    inhouse.matrix_selected = None
                else:
                    inhouse.matrix_selected = payload
                audio.play_click()
                break


def _draw_matrix_drilldown(dl, tx, ty, tw, ty_bot, selected, matrix):
    """The detail card that sits below the grid. Shows the stats for the
    clicked cell (row vs col) — VS record, WITH record, last played, streaks.
    Falls back to a hint when no cell is selected."""
    panel_h = max(0, ty_bot - ty)
    if panel_h < 40:
        return
    # Frame
    dpg.draw_rectangle((tx, ty), (tx + tw, ty + panel_h),
                       fill=(*C["card"][:3], 200),
                       color=(*C["gold"][:3], 80),
                       rounding=4, parent=dl)
    if not selected:
        _txt(dl, tx + 16, ty + 14, "CLICK A CELL TO DRILL IN",
             (*C["gold_lt"][:3], 220), 13, "raj_sb_12")
        _txt(dl, tx + 16, ty + 36,
             "Each cell shows the row player's wins–losses against (or with) the column player.",
             (*C["txt_dim"][:3], 200), 14, "raj_r_14")
        _txt(dl, tx + 16, ty + 58,
             "Toggle VS / WITH / COMBINED above to repaint the grid.",
             (*C["txt_dim"][:3], 200), 14, "raj_r_14")
        return
    row_name, col_name = selected
    stats = (matrix.get(row_name) or {}).get(col_name) or {}
    gv = int(stats.get("games_vs") or 0)
    wv = int(stats.get("wins_vs") or 0)
    gw = int(stats.get("games_with") or 0)
    ww = int(stats.get("wins_with") or 0)
    last = (stats.get("last_played") or "").replace("T", " ").replace("Z", "")
    last = _fmt_date(last) if last else "—"
    lv = gv - wv; lw = gw - ww
    total = gv + gw

    # Title
    _txt(dl, tx + 16, ty + 12,
         f"{row_name.upper()}  ›  vs {col_name.upper()}",
         (*C["gold_lt"][:3], 245), 19, "raj_sb_18")
    _txt(dl, tx + 16, ty + 38,
         f"{total} total customs together — last met {last}",
         (*C["txt_dim"][:3], 200), 13, "raj_r_14")

    # Mini-stat blocks across the bottom.
    block_y = ty + 64
    block_h = panel_h - (block_y - ty) - 12
    if block_h < 30:
        return
    blocks = [
        ("VS RECORD",  f"{wv}-{lv}" if gv else "—",
         f"{fmt.pct(wv, of=gv)}" if gv else "no data",
         "win" if (gv and wv * 2 > gv) else ("loss" if gv else "txt_dim")),
        ("WITH RECORD", f"{ww}-{lw}" if gw else "—",
         f"{fmt.pct(ww, of=gw)}" if gw else "no data",
         "win" if (gw and ww * 2 > gw) else ("loss" if gw else "txt_dim")),
        ("VS GAMES",    str(gv) if gv else "0", "head-to-head", "gold_lt"),
        ("WITH GAMES",  str(gw) if gw else "0", "as teammates",  "gold_lt"),
        ("LAST MET",    last or "—",                     "shared match",   "gold_lt"),
    ]
    bw = (tw - 32 - (len(blocks) - 1) * 10) // len(blocks)
    bx = tx + 16
    for label, big, sub, color_key in blocks:
        col_main = C.get(color_key, C["gold_lt"])
        # Block frame
        dpg.draw_rectangle((bx, block_y), (bx + bw, block_y + block_h),
                           fill=(*C["bg"][:3], 220),
                           color=(*C["gold"][:3], 60),
                           rounding=3, parent=dl)
        _txt(dl, bx + 10, block_y + 6, label,
             (*C["gold"][:3], 220), 11, "raj_sb_12")
        _txt(dl, bx + 10, block_y + 22, str(big),
             (*col_main[:3], 240), 22, "raj_sb_22")
        _txt(dl, bx + 10, block_y + block_h - 22, str(sub)[:18],
             (*C["txt_dim"][:3], 200), 12, "raj_r_12")
        bx += bw + 10


def _fmt_date(ts):
    """ISO timestamp → 'May 1, 2026' style. Empty / unparseable falls through.
    Hand-formats day/year to stay cross-platform (Windows lacks the %-d spec)."""
    if not ts: return ""
    s = str(ts).replace("T", " ").replace("Z", "")[:10]
    try:
        import datetime as _dt
        d = _dt.datetime.strptime(s, "%Y-%m-%d")
        return f"{d.strftime('%b')} {d.day}, {d.year}"
    except Exception:
        return s


def _record_view(key, r):
    """Render-args for one record card: (big_value, line1, line2, match_id).
    Returns None when `r` is empty."""
    if not r:
        return None
    mid = r.get("match_id")
    date = _fmt_date(r.get("started_at"))
    player = r.get("player", "?")
    champ  = r.get("champion", "")
    winner = (r.get("winner") or "").upper()
    val_raw = r.get("value", 0)

    if key in ("most_kills", "most_assists", "most_cs", "most_vision"):
        return (str(int(val_raw)),
                f"{player}  ·  {champ}" if champ else player,
                date, mid)
    if key in ("most_damage", "most_gold"):
        return (fmt.compact(val_raw),
                f"{player}  ·  {champ}" if champ else player,
                date, mid)
    if key == "best_kda_game":
        sub = f"{player}  ·  {champ}  ({int(r.get('kills',0))}/" \
              f"{int(r.get('deaths',0))}/{int(r.get('assists',0))})"
        return (f"{float(val_raw):.2f}", sub, date, mid)
    if key == "biggest_blowout":
        return (f"+{int(val_raw)}", f"{winner} TEAM by kill diff",
                date, mid)
    if key in ("longest_match", "shortest_match"):
        return (fmt.duration(int(val_raw)),
                f"{winner} TEAM won" if winner else "",
                date, mid)
    if key in ("longest_win_streak", "longest_loss_streak", "most_games"):
        return (str(int(val_raw)), player, "", None)
    # Fallback (unknown key)
    return (str(val_raw), player, date, mid)


# (key, title) — display order for the records grid.
_RECORD_DEFS = (
    ("most_kills",         "MOST KILLS"),
    ("best_kda_game",      "HIGHEST KDA"),
    ("most_damage",        "MOST DAMAGE"),
    ("most_assists",       "MOST ASSISTS"),
    ("most_cs",            "MOST CS"),
    ("most_gold",          "MOST GOLD"),
    ("most_vision",        "MOST VISION"),
    ("longest_win_streak", "LONGEST WIN STREAK"),
    ("longest_loss_streak","LONGEST LOSS STREAK"),
    ("most_games",         "MOST GAMES PLAYED"),
    ("biggest_blowout",    "BIGGEST BLOWOUT"),
    ("longest_match",      "LONGEST MATCH"),
    ("shortest_match",     "SHORTEST MATCH"),
)


def _draw_records(dl, tx, ty, tw, th, vw, vh):
    """Phase 3 — RECORDS view: card grid of league superlatives. Each card
    shows the title / big value / holder / date. Cards with an associated
    match_id are clickable: click → jump to HISTORY view with that match's
    detail panel open."""
    _txt(dl, tx, ty + 0, "LEAGUE RECORDS",
         (*C["gold"][:3], 220), 21, "raj_sb_18")
    _txt(dl, tx + 200, ty + 4,
         "All-time superlatives across every logged custom game.",
         (*C["txt_dim"][:3], 180), 14, "raj_r_14")

    rec   = live.records or {}
    err   = live.records_error
    loaded = live.records_loaded

    grid_top = ty + 40
    grid_bot = ty + th - 8

    # Grid geometry — responsive 1..4 cols capped to keep cards glanceable.
    gap = 16
    cols = max(1, min(4, (tw + gap) // (240 + gap)))
    card_w = max(220, (tw - (cols - 1) * gap) // cols)
    card_h = 124

    # Loading skeleton
    if not loaded and not rec:
        for i in range(min(12, cols * 3)):
            cx = tx + (i % cols) * (card_w + gap)
            cy = grid_top + (i // cols) * (card_h + gap)
            effects.draw_skeleton_rect(dl, cx, cy, card_w, card_h,
                                       rounding=8)
        return

    if err and not rec:
        _txt(dl, tx, grid_top, f"Could not load records: {err[:80]}",
             (*C["loss"][:3], 220), 16, "raj_r_16")
        return

    if not rec:
        _txt(dl, tx, grid_top,
             "No records yet — log an inhouse game to start the hall of fame.",
             (*C["txt_dim"][:3], 200), 16, "raj_r_16")
        return

    # Cursor for hover / click
    _m  = dpg.get_mouse_pos(local=False)
    _vp = dpg.get_viewport_pos()
    mrx = _m[0] - _vp[0] - 68
    mry = _m[1] - _vp[1] - 52
    clicked = dpg.is_mouse_button_clicked(0)

    for i, (key, title) in enumerate(_RECORD_DEFS):
        col = i % cols
        row = i // cols
        cx = tx + col * (card_w + gap)
        cy = grid_top + row * (card_h + gap)
        if cy + card_h > grid_bot:
            break  # ran out of vertical room

        view = _record_view(key, rec.get(key))
        is_empty = (view is None)
        is_hov = (not is_empty
                  and cx <= mrx <= cx + card_w
                  and cy <= mry <= cy + card_h)
        clickable_mid = (view[3] if view else None)

        glow = effects.hover_amt(f"rec_{key}", is_hov and clickable_mid is not None)
        lift = effects.hover_lift(f"rec_{key}", is_hov and clickable_mid is not None,
                                  lift=3.0)
        cy_eff = cy + int(lift)

        # Card chrome
        base_a = 240 if not is_empty else 160
        bdr_a  = 60 + int(140 * glow)
        dpg.draw_rectangle((cx, cy_eff), (cx + card_w, cy_eff + card_h),
                           fill=(*C["card"][:3], base_a),
                           color=(*C["gold"][:3], bdr_a),
                           rounding=8, parent=dl)
        if glow > 0.02:
            effects.draw_hover_glow(dl, cx, cy_eff, cx + card_w, cy_eff + card_h,
                                    C["gold"], amt=glow, rounding=8, spread=2)

        # Title bar
        _txt(dl, cx + 14, cy_eff + 10, title,
             (*C["gold"][:3], 220), 13, "raj_sb_14")

        if is_empty:
            _txt(dl, cx + 14, cy_eff + 50, "no data yet",
                 (*C["txt_dim"][:3], 180), 16, "raj_r_16")
            continue

        big_val, line1, line2, _ = view
        # Big value — count-up when the value is a clean integer string.
        try:
            target = float(big_val.replace("+", "").replace(",", "").replace("K","000").replace("M","000000").rstrip(":"))
            disp = effects.count_up(f"rec_v_{key}", target, rate=0.18)
            # Keep formatting consistent with the source string for non-numeric forms
            shown = big_val if not big_val.replace(".", "").replace("+","").replace(",","").isdigit() else (
                f"{disp:.2f}" if "." in big_val else f"{int(disp):,}")
            if big_val.startswith("+"): shown = "+" + shown.lstrip("+")
        except Exception:
            shown = big_val
        _txt(dl, cx + 14, cy_eff + 34, shown,
             (*C["gold_lt"][:3], 240), 32, "cinzel_36")

        # Holder line
        if line1:
            _txt(dl, cx + 14, cy_eff + 78,
                 fmt.clamp_text(line1, max(8, card_w // 9)),
                 (*C["txt"][:3], 220), 15, "raj_r_16")
        if line2:
            _txt(dl, cx + 14, cy_eff + 100,
                 fmt.clamp_text(line2, max(8, card_w // 9)),
                 (*C["txt_dim"][:3], 180), 13, "raj_r_14")

        # Subtle "→ open match" hint for cards with a match link
        if clickable_mid:
            _txt(dl, cx + card_w - 32, cy_eff + 100, "→",
                 (*C["gold"][:3], 200 if is_hov else 120),
                 16, "raj_sb_16")

        if clicked and is_hov and clickable_mid:
            audio.play_click()
            # Jump to history view, ensure cache is loaded, then open detail panel.
            _set_view_mode("history")
            inhouse.select_match(clickable_mid)
            clicked = False
            return


def _draw_leaderboard(dl, tx, ty, tw, th, vw, vh):
    ft = inhouse.filter_text.strip().lower()
    players  = [p for p in inhouse.players
                if not ft or ft in p["player"].lower()] if ft else inhouse.players
    col_xs   = _col_xs(tw)
    ha       = inhouse.header_alpha

    # Calculate scroll bounds and consume wheel delta
    visible_h    = th - HEADER_H - 4
    total_rows_h = len(players) * (ROW_H + 2)
    max_scroll   = max(0, total_rows_h - visible_h)
    if _wheel_delta_shared[0] != 0:
        inhouse.scroll_off = max(0, min(
            inhouse.scroll_off - _wheel_delta_shared[0] * 30, max_scroll))
        _wheel_delta_shared[0] = 0
    inhouse.scroll_off = max(0, min(inhouse.scroll_off, max_scroll))
    scroll = int(inhouse.scroll_off)

    row_clip_top = ty + HEADER_H + 4
    row_clip_bot = ty + th

    # V2 card framing — the whole table sits on a shadowed gradient panel,
    # matching the Home card language. Drawn before rows/header.
    luxe.shadow(dl, tx - 10, ty - 10, tx + tw + 10, ty + th,
                alpha=85, spread=16, drop=7)
    luxe.panel(dl, tx - 10, ty - 10, tx + tw + 10, ty + th,
               (12, 26, 48, 242), corner=10,
               border=C["gold_dk"], border_a=120, sheen=42)

    row_y = ty + HEADER_H + 4

    # Cursor in content coords, for per-row hover feedback.
    _m   = dpg.get_mouse_pos(local=False)
    _vp  = dpg.get_viewport_pos()
    _mrx = _m[0] - _vp[0] - 68
    _mry = _m[1] - _vp[1] - 52

    # Draw rows FIRST so the column header renders on top of any scrolled-up rows
    for i, p in enumerate(players):
        n  = p["player"]
        al = inhouse.row_alpha.get(n, 0)
        xo = inhouse.row_x_off.get(n, -60)
        if al <= 0:
            continue
        ry   = row_y + i*(ROW_H+2) - scroll
        # Clip rows outside the visible region below the column header
        if ry + ROW_H < row_clip_top or ry > row_clip_bot:
            continue
        rank = p["rank"]
        is_top3 = rank <= 3
        medal   = MEDAL_PARTICLE.get(rank)
        is_sel  = inhouse.selected == n
        is_hov  = (not is_sel and tx+xo <= _mrx <= tx+tw+xo
                   and ry <= _mry <= ry+ROW_H)

        # Row background
        if is_sel:
            bg = (*C["card_hover"][:3], al)
        elif is_hov:
            bg = (*C["card_hover"][:3], int(al * 0.6))
        elif is_top3:
            bg = (22, 34, 58, al)   # slightly lifted navy for the podium
        elif i % 2 == 0:
            bg = (*C["card"][:3], al)
        else:
            bg = (*C["panel"][:3], al)

        dpg.draw_rectangle((tx+xo,ry),(tx+tw+xo,ry+ROW_H),
                            fill=bg, color=(0,0,0,0), rounding=3, parent=dl)
        if is_hov:
            dpg.draw_rectangle((tx+xo,ry),(tx+tw+xo,ry+ROW_H),
                                fill=(0,0,0,0),
                                color=(*C["gold"][:3], int(al * 0.45)),
                                rounding=3, thickness=1, parent=dl)

        # Rank 1: breathing gold border on top of the row
        if rank == 1 and al > 180:
            try:
                from ui.effects import breathing_alpha
                glow_a = breathing_alpha(int(al * 0.65),
                                          period=3.0, amp=0.35)
                dpg.draw_rectangle((tx + xo - 1, ry - 1),
                                    (tx + tw + xo + 1, ry + ROW_H + 1),
                                    fill=(0, 0, 0, 0),
                                    color=(*C["gold"][:3], glow_a),
                                    rounding=4, thickness=2, parent=dl)
            except Exception:
                pass

        # Left accent stripe: gold for selected, medal color for the podium
        if is_sel:
            dpg.draw_rectangle((tx+xo,ry),(tx+xo+4,ry+ROW_H),
                                fill=(*C["gold"][:3],al), color=(0,0,0,0),
                                rounding=2, parent=dl)
        elif medal:
            luxe.glow(dl, tx+xo+2, ry + ROW_H // 2, ROW_H * 0.66,
                      medal, int(al * 0.22))
            dpg.draw_rectangle((tx+xo,ry+3),(tx+xo+4,ry+ROW_H-3),
                                fill=(*medal, al), color=(0,0,0,0),
                                rounding=2, parent=dl)

        try:
            wr_num = float(str(p["wr"]).replace("%",""))
        except (ValueError, TypeError):
            wr_num = 50.0
        wr_col = C["win"] if wr_num >= 52 else C["loss"] if wr_num < 48 else C["txt"]
        name_col = C["gold_lt"] if is_top3 else C["txt"]

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
                rank_col = medal if medal else C["txt_dim"]
                sz = 18 if is_top3 else 15
                if medal:
                    luxe.glow(dl, vx + 6, ry + ROW_H // 2, 16,
                              medal, int(al * 0.25))
                _txt(dl, vx, vy+(0 if is_top3 else 2), str(rank), (*rank_col[:3],al), sz, "raj_20" if is_top3 else "raj_16")
            elif ci == 1:
                # Avatar — draw hex-cropped image if loaded, otherwise fallback dot
                tex = _get_avatar_tex(n)
                av_sz = min(ROW_H - 8, 42)
                if tex:
                    av_y1 = ry + (ROW_H - av_sz) // 2
                    if medal:
                        luxe.glow(dl, vx + av_sz / 2, av_y1 + av_sz / 2,
                                  av_sz * 0.72, medal, int(al * 0.20))
                    dpg.draw_image(tex, (vx, av_y1), (vx + av_sz, av_y1 + av_sz), parent=dl)
                    _txt(dl, vx + av_sz + 6, vy, val, (*name_col[:3], al), 18, "raj_20")
                else:
                    _txt(dl, vx, vy, val, (*name_col[:3],al), 18, "raj_20")
            elif ci == 2:
                _txt(dl, vx, vy+2, val, (*C["txt"][:3],al), 16, "raj_16")
            elif ci == 3:
                _txt(dl, vx, vy+2, val, (*C["txt2"][:3],al), 16, "raj_16")
            elif ci == 4:
                _txt(dl, vx, vy - 4, val, (*wr_col[:3],al), 17, "raj_18")
                # Win-rate bar under the number — instant visual scan
                bw_ = min(cw - 24, 64)
                if bw_ > 20:
                    bcy = ry + ROW_H - 13
                    frac = max(0.0, min(1.0, wr_num / 100.0))
                    dpg.draw_rectangle((vx, bcy), (vx + bw_, bcy + 3),
                                       fill=(*C["rule_dark"][:3], int(al*0.5)),
                                       color=(0,0,0,0), rounding=1, parent=dl)
                    if frac > 0.01:
                        luxe.hfade(dl, vx, bcy, vx + int(bw_ * frac),
                                   bcy + 3, wr_col, int(al * 0.85),
                                   solid="right")
            elif ci == 5:
                _txt(dl, vx, vy+2, val, (*C["platinum"][:3],al), 16, "raj_16")
            elif ci in (6,7):
                _txt(dl, vx, vy+2, val, (*C["txt2"][:3],al), 18, "raj_18")
            elif ci == 8:
                _draw_sparkline(dl, vx, ry+8, cw-16, ROW_H-16, n, al)

    # Column header drawn AFTER rows so it masks any rows that scrolled into
    # its area — V2: gradient panel + gold kicker labels + fading gold rule.
    luxe.panel(dl, tx, ty, tx + tw, ty + HEADER_H,
               (24, 48, 82, min(255, ha)), corner=6,
               border=C["gold_dk"], border_a=min(150, ha), sheen=46)
    for ci, ((lbl,_),(cx,cw)) in enumerate(zip(COLS, col_xs)):
        active = (lbl in ("#","PLAYER","WR","KDA"))
        col = C["gold"] if active else C["txt_dim"]
        _txt(dl, tx+cx+8, ty+HEADER_H//2-9, lbl, (*col[:3], ha), 16, "raj_sb_16")
    luxe.hfade(dl, tx + 6, ty + HEADER_H - 2, tx + tw - 6, ty + HEADER_H,
               C["gold"], min(120, ha), solid="left")

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
            ry3 = row_y + i*(ROW_H+2) - scroll
            if ry3 + ROW_H < row_clip_top or ry3 > row_clip_bot:
                continue
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
    _txt(dl, name_x, py+16, name.upper(), (*C["gold_lt"][:3], al), 27, "raj_36")

    # Sub-stats row
    sub = f"#{p['rank']}  ·  {p['games']} games  ·  {p['wins']}-{p['losses']}  ·  {p['wr']} WR  ·  KDA {p['kda']}"
    _txt(dl, px+20, py+74, sub, (*C["txt"][:3], int(al*0.85)), 17, "raj_r_16")

    dpg.draw_line((px+16, py+98),(vw-16, py+98),
                  color=(*C["rule_dark"][:3], int(180*frac)), thickness=1, parent=dl)

    # Champion breakdown label
    _txt(dl, px+20, py+110, "CHAMPION BREAKDOWN", (*C["gold"][:3], al), 17, "raj_sb_18")

    # Table header
    champ_hdrs = [("CHAMPION",140),("GP",40),("W-L",56),("WR",52),("KDA",50),("K",36),("D",36),("A",36),("DMG",76)]
    hx = px + 16
    hy = py + 136
    dpg.draw_rectangle((px+4, hy-4),(vw-4, hy+22),
                        fill=(*C["card"][:3], int(160*frac)),
                        color=(0,0,0,0), rounding=3, parent=dl)
    for lbl, cw in champ_hdrs:
        _txt(dl, hx, hy, lbl, (*C["txt_dim"][:3], al), 18, "raj_sb_16")
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
            _txt(dl, cx2, ry4+10, v2, (*col2[:3], al), 16, "raj_16")
            cx2 += cw

    # Sparkline history
    spark_y = row_y2 + len(champs)*40 + 20
    _txt(dl, px+20, spark_y, "RECENT RESULTS  (last 10 games)", (*C["txt_dim"][:3], al), 16, "raj_sb_16")
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
        _txt(dl, dot_x-5, dot_y-8, lbl2, (*C["bg"][:3], al), 15, "raj_sb_14")

    # Close hint
    _txt(dl, px+20, vh-72, "Click the same row again to close",
         (*C["txt_dim"][:3], int(al*0.5)), 15, "raj_r_14")


# ---------------------------------------------------------------------------
# Phase 3 — per-game detail panel (history view)
# ---------------------------------------------------------------------------

_BLUE_COL = (140, 175, 230)
_RED_COL  = (230, 145, 145)


def _picks_to_list(picks):
    """Normalize a `blue_picks` / `red_picks` field (either dict-by-role or
    list) into a 5-entry list in role order: TOP, JGL, MID, BOT, SUP."""
    if isinstance(picks, dict):
        out = []
        for r in ("TOP", "JGL", "MID", "BOT", "SUP"):
            alt = {"JGL": "JUNGLE", "BOT": "BOTTOM", "SUP": "SUPPORT"}.get(r, r)
            out.append(picks.get(r) or picks.get(alt))
        return out
    if isinstance(picks, list):
        return list(picks)[:5] + [None] * max(0, 5 - len(picks))
    return [None] * 5


# Per-frame hit-test slots for the predictions vote buttons.
_pred_hits = []   # [(x1, y1, x2, y2, match_id, side, voter), ...]


def _do_share_match(mid):
    import threading, os
    def _bg():
        try:
            from data import share_cards
            path = share_cards.make_match_card(mid)
            if not path:
                toast.push("Could not generate match card", kind="warn")
                return
            copied = share_cards.copy_path_to_clipboard(path)
            msg = f"Saved match card · {os.path.basename(path)}"
            if copied:
                msg += "  (path copied to clipboard)"
            toast.push(msg, kind="success", duration=7.0)
        except Exception as e:
            toast.push(f"Share card error: {e}", kind="error")
    threading.Thread(target=_bg, daemon=True, name="share_match").start()


def _draw_match_predictions(dl, px, sy, panel_w, frac, mid, winner):
    """Phase 5b — predictions section inside the match-detail panel.
       Returns the new sy after rendering."""
    from data.config import load_config
    from data.reader import live as _live, load_match_predictions
    al = int(255 * frac)

    _txt(dl, px + 20, sy, "PREDICTIONS",
         (*C["gold"][:3], al), 16, "raj_sb_18")
    sy += 24

    cfg = load_config()
    voter = (cfg.get("display_name") or "").strip()

    # Lazy-load
    if mid not in _live.predictions and mid not in _live._predictions_inflight:
        load_match_predictions(mid)
    preds = _live.predictions.get(mid)

    # Tally
    blue_votes = sum(1 for p in (preds or []) if p.get("predicted") == "blue")
    red_votes  = sum(1 for p in (preds or []) if p.get("predicted") == "red")
    my_vote    = next((p.get("predicted") for p in (preds or [])
                       if p.get("voter") == voter), None)

    # Bar
    total = max(1, blue_votes + red_votes)
    bar_x = px + 20
    bar_w = panel_w - 40
    bar_y = sy
    bar_h = 22
    blue_frac = blue_votes / total
    dpg.draw_rectangle((bar_x, bar_y),
                       (bar_x + int(bar_w * blue_frac), bar_y + bar_h),
                       fill=(*_BLUE_COL, int(200*frac)),
                       color=(0,0,0,0), rounding=4, parent=dl)
    dpg.draw_rectangle((bar_x + int(bar_w * blue_frac), bar_y),
                       (bar_x + bar_w, bar_y + bar_h),
                       fill=(*_RED_COL, int(200*frac)),
                       color=(0,0,0,0), rounding=4, parent=dl)
    _txt(dl, bar_x + 8, bar_y + 3,
         f"{blue_votes} BLUE",
         (12, 24, 48, al), 13, "raj_sb_14")
    rt = f"{red_votes} RED"
    rw = len(rt) * 7
    _txt(dl, bar_x + bar_w - rw - 8, bar_y + 3, rt,
         (48, 12, 24, al), 13, "raj_sb_14")
    sy += bar_h + 10

    # Vote controls — only when there's no winner yet AND we know who you are
    if not winner and voter:
        btn_w = (panel_w - 60) // 2
        bx_b = px + 20
        bx_r = px + 20 + btn_w + 20
        btn_h = 28

        # Hover state — translate the absolute mouse into content_dl coords by
        # looking up the actual sidebar/titlebar positions instead of hard-
        # coding 68/52 (the sidebar can collapse/expand to widths up to 200).
        _m  = dpg.get_mouse_pos(local=False)
        _vp = dpg.get_viewport_pos()
        try:
            _cw_pos = dpg.get_item_pos("content_win")
        except Exception:
            _cw_pos = (68, 52)
        mrx = _m[0] - _vp[0] - _cw_pos[0]
        mry = _m[1] - _vp[1] - _cw_pos[1]

        # BLUE button
        h_blue = (bx_b <= mrx <= bx_b + btn_w and sy <= mry <= sy + btn_h)
        is_mine_blue = (my_vote == "blue")
        amt_b = effects.hover_amt(f"pred_b_{mid}", h_blue)
        fill_a = int((220 if is_mine_blue else 100 + 80 * amt_b) * frac)
        dpg.draw_rectangle((bx_b, sy), (bx_b + btn_w, sy + btn_h),
                           fill=(*_BLUE_COL, fill_a),
                           color=(*_BLUE_COL, int(220*frac)),
                           rounding=6, parent=dl)
        label_b = ("✓ VOTED BLUE" if is_mine_blue else "VOTE BLUE")
        lw = len(label_b) * 7
        _txt(dl, bx_b + (btn_w - lw)//2, sy + 6, label_b,
             ((12, 18, 32, al) if is_mine_blue else (*C["txt"][:3], al)),
             14, "raj_sb_16")
        _pred_hits.append((bx_b, sy, bx_b + btn_w, sy + btn_h, mid, "blue", voter))

        # RED button
        h_red = (bx_r <= mrx <= bx_r + btn_w and sy <= mry <= sy + btn_h)
        is_mine_red = (my_vote == "red")
        amt_r = effects.hover_amt(f"pred_r_{mid}", h_red)
        fill_a = int((220 if is_mine_red else 100 + 80 * amt_r) * frac)
        dpg.draw_rectangle((bx_r, sy), (bx_r + btn_w, sy + btn_h),
                           fill=(*_RED_COL, fill_a),
                           color=(*_RED_COL, int(220*frac)),
                           rounding=6, parent=dl)
        label_r = ("✓ VOTED RED" if is_mine_red else "VOTE RED")
        lw = len(label_r) * 7
        _txt(dl, bx_r + (btn_w - lw)//2, sy + 6, label_r,
             ((32, 12, 18, al) if is_mine_red else (*C["txt"][:3], al)),
             14, "raj_sb_16")
        _pred_hits.append((bx_r, sy, bx_r + btn_w, sy + btn_h, mid, "red", voter))
        sy += btn_h + 8
    elif winner:
        # Outcome accuracy
        correct = blue_votes if winner == "blue" else red_votes
        total_v = blue_votes + red_votes
        if total_v:
            acc = correct / total_v * 100
            _txt(dl, px + 20, sy,
                 f"{correct} of {total_v} predictors called it correctly ({acc:.0f}%).",
                 (*C["txt2"][:3], int(al*0.9)), 13, "raj_r_14")
        else:
            _txt(dl, px + 20, sy,
                 "No predictions were made for this match.",
                 (*C["txt_dim"][:3], int(al*0.7)), 13, "raj_r_14")
        sy += 18
    else:
        # No winner, no voter set
        _txt(dl, px + 20, sy,
             "Set your display name in Settings to cast a prediction.",
             (*C["txt_dim"][:3], int(al*0.8)), 12, "raj_r_14")
        sy += 18
    return sy


def _handle_prediction_clicks():
    """Consume any click that hit a vote button. Called after the panel draws."""
    if not _pred_hits:
        return
    if not dpg.is_mouse_button_clicked(0):
        return
    _m  = dpg.get_mouse_pos(local=False)
    _vp = dpg.get_viewport_pos()
    try:
        _cw_pos = dpg.get_item_pos("content_win")
    except Exception:
        _cw_pos = (68, 52)
    mrx = _m[0] - _vp[0] - _cw_pos[0]
    mry = _m[1] - _vp[1] - _cw_pos[1]
    for x1, y1, x2, y2, mid, side, voter in _pred_hits:
        if x1 <= mrx <= x2 and y1 <= mry <= y2:
            try:
                audio.play_click()
            except Exception:
                pass
            import threading
            def _post(mid=mid, side=side, voter=voter):
                try:
                    from data import rift_api
                    from data.reader import load_match_predictions, live as _live
                    res = rift_api.post_prediction(mid, voter, side)
                    if res and res.get("ok") is not False:
                        # Force a fresh fetch — overwrite cache
                        _live.predictions.pop(mid, None)
                        load_match_predictions(mid)
                        toast.push(f"Prediction recorded: {side.upper()}", kind="success")
                    else:
                        toast.push("Could not save prediction", kind="warn")
                except Exception as e:
                    toast.push(f"Prediction error: {e}", kind="error")
            threading.Thread(target=_post, daemon=True).start()
            return


def _draw_match_detail_panel(dl, vw, vh):
    frac = inhouse.match_detail_x_frac
    mid  = inhouse.selected_match_id
    if not mid or frac < 0.01:
        return

    # Pull from the already-cached history list — no extra fetch needed.
    m = next((mm for mm in (live.match_history or []) if mm.get("id") == mid), None)
    if not m:
        # Match disappeared (DB pruned?). Quietly close.
        inhouse.selected_match_id = None
        inhouse.match_detail_x_frac = 0.0
        return

    panel_w = int(MATCH_DETAIL_W * frac)
    px = vw - panel_w
    py = TOP_BAR_H
    al = int(255 * frac)

    # Panel chrome
    dpg.draw_rectangle((px, py), (vw, vh),
                       fill=(*C["panel"][:3], int(240*frac)),
                       color=(0,0,0,0), parent=dl)
    dpg.draw_line((px, py), (px, vh),
                  color=(*C["rule_dark"][:3], int(220*frac)),
                  thickness=1, parent=dl)

    winner = (m.get("winner") or "").lower()
    accent = _BLUE_COL if winner == "blue" else (_RED_COL if winner == "red"
                                                  else (200, 180, 120))
    dpg.draw_rectangle((px, py), (vw, py+4),
                       fill=(*accent, int(220*frac)),
                       color=(0,0,0,0), parent=dl)

    # Close (X) button — top-right of panel
    bx_close = vw - 36
    by_close = py + 12
    bw_close = bh_close = 24
    _m  = dpg.get_mouse_pos(local=False)
    _vp = dpg.get_viewport_pos()
    try:
        _cw_pos = dpg.get_item_pos("content_win")
    except Exception:
        _cw_pos = (68, 52)
    mrx = _m[0] - _vp[0] - _cw_pos[0]
    mry = _m[1] - _vp[1] - _cw_pos[1]
    is_close_hov = (bx_close <= mrx <= bx_close + bw_close
                    and by_close <= mry <= by_close + bh_close)
    close_glow = effects.hover_amt(f"match_close_{mid}", is_close_hov)
    btn_bg_a = int((40 + 120 * close_glow) * frac)
    dpg.draw_rectangle((bx_close, by_close),
                       (bx_close + bw_close, by_close + bh_close),
                       fill=(*C["card_hover"][:3], btn_bg_a),
                       color=(*C["gold"][:3], int((80 + 120 * close_glow) * frac)),
                       rounding=4, parent=dl)
    _txt(dl, bx_close + 7, by_close + 3, "X",
         (*C["gold_lt"][:3], al), 16, "raj_sb_16")

    # Header — section label + timestamp + winner-side big label
    _txt(dl, px + 20, py + 14, "MATCH DETAIL",
         (*C["gold"][:3], al), 19, "raj_sb_18")
    ts_raw = (m.get("started_at") or "").replace("T", " ").replace("Z", "")
    _txt(dl, px + 20, py + 42, ts_raw[:16] or "—",
         (*C["txt"][:3], al), 16, "raj_r_16")

    win_label = (f"{winner.upper()} TEAM WINS" if winner
                 else "RESULT UNKNOWN")
    _txt(dl, vw - 260, py + 44, win_label,
         (*accent, al), 17, "raj_sb_18")

    dur_sec = int(m.get("duration") or 0)
    sub_parts = [fmt.duration(dur_sec)]
    if m.get("queue"): sub_parts.append(str(m["queue"]))
    if m.get("patch"): sub_parts.append(f"patch {m['patch']}")
    if m.get("source"): sub_parts.append(f"source: {m['source']}")
    _txt(dl, px + 20, py + 66, "  ·  ".join(sub_parts),
         (*C["txt_dim"][:3], int(al * 0.85)), 14, "raj_r_14")

    dy = py + 96
    dpg.draw_line((px + 16, dy), (vw - 16, dy),
                  color=(*C["rule_dark"][:3], int(180*frac)),
                  thickness=1, parent=dl)

    # ----- SCOREBOARD -----
    sy = dy + 12
    _txt(dl, px + 20, sy, "SCOREBOARD",
         (*C["gold"][:3], al), 16, "raj_sb_18")
    sy += 26

    parts = m.get("participants") or []
    blue = sorted([p for p in parts if (p.get("team") or "").lower() == "blue"],
                  key=lambda p: _role_order(p.get("role", "")))
    red  = sorted([p for p in parts if (p.get("team") or "").lower() == "red"],
                  key=lambda p: _role_order(p.get("role", "")))

    sb_cols = [
        ("ROLE",   40),
        ("CHAMP",  120),
        ("PLAYER", 108),
        ("K/D/A",  82),
        ("CS",     42),
        ("GOLD",   58),
        ("DMG",    66),
        ("VIS",    40),
    ]

    # Header row
    hx = px + 22
    dpg.draw_rectangle((px + 16, sy - 3), (vw - 16, sy + 20),
                       fill=(*C["card"][:3], int(170*frac)),
                       color=(0,0,0,0), rounding=3, parent=dl)
    for lbl, cw in sb_cols:
        _txt(dl, hx, sy, lbl, (*C["txt_dim"][:3], int(al*0.95)),
             13, "raj_sb_14")
        hx += cw
    sy += 26

    def _sb_row(yy, p, side_col, alt):
        bg_a = int((130 if alt else 90) * frac)
        dpg.draw_rectangle((px + 16, yy - 2), (vw - 16, yy + 22),
                           fill=(*C["card"][:3], bg_a),
                           color=(0,0,0,0), rounding=2, parent=dl)
        dpg.draw_rectangle((px + 16, yy - 2), (px + 19, yy + 22),
                           fill=(*side_col, int(220*frac)),
                           color=(0,0,0,0), parent=dl)
        role  = (p.get("role") or "").upper()[:3]
        champ = p.get("champion") or "?"
        plyr  = p.get("player") or "—"
        k = int(p.get("kills", 0)); d = int(p.get("deaths", 0)); a_ = int(p.get("assists", 0))
        vals = [
            (role,                            side_col),
            (fmt.clamp_text(str(champ), 15),  C["gold_lt"]),
            (fmt.clamp_text(str(plyr), 13),   C["txt"]),
            (f"{k}/{d}/{a_}",                 C["txt"]),
            (str(int(p.get("cs", 0))),        C["txt"]),
            (fmt.compact(p.get("gold", 0)),   C["txt"]),
            (fmt.compact(p.get("damage", 0)), C["txt"]),
            (str(int(p.get("vision", 0))),    C["txt"]),
        ]
        xx = px + 22
        for (text, col), (_, cw) in zip(vals, sb_cols):
            _txt(dl, xx, yy + 1, text, (*col[:3], al), 14, "raj_r_14")
            xx += cw

    # Blue side
    if blue:
        for i, p in enumerate(blue[:5]):
            _sb_row(sy + i*24, p, _BLUE_COL, i % 2 == 0)
        sy += min(5, len(blue)) * 24 + 6
    else:
        _txt(dl, px + 22, sy, "(no blue-side participants logged)",
             (*C["txt2"][:3], al), 14, "raj_r_14")
        sy += 22

    # Thin team divider
    dpg.draw_line((px + 16, sy - 3), (vw - 16, sy - 3),
                  color=(*C["rule_dark"][:3], int(120*frac)),
                  thickness=1, parent=dl)

    # Red side
    if red:
        for i, p in enumerate(red[:5]):
            _sb_row(sy + i*24, p, _RED_COL, i % 2 == 0)
        sy += min(5, len(red)) * 24 + 12
    else:
        _txt(dl, px + 22, sy, "(no red-side participants logged)",
             (*C["txt2"][:3], al), 14, "raj_r_14")
        sy += 22

    # ----- DRAFT -----
    draft = m.get("draft") or {}
    _txt(dl, px + 20, sy, "DRAFT",
         (*C["gold"][:3], al), 16, "raj_sb_18")
    sy += 24

    half_w  = (panel_w - 32) // 2
    col_x_b = px + 16
    col_x_r = px + 16 + half_w + 4
    _txt(dl, col_x_b + 4, sy, "BLUE",
         (*_BLUE_COL, al), 13, "raj_sb_14")
    _txt(dl, col_x_r + 4, sy, "RED",
         (*_RED_COL, al), 13, "raj_sb_14")
    sy += 18

    def _draft_row(yy, lbl, items, anchor_x, accent_col):
        _txt(dl, anchor_x + 4, yy + 4, lbl,
             (*C["txt2"][:3], al), 13, "raj_sb_14")
        cx = anchor_x + 52
        chip_w = 62
        chip_h = 22
        for it in (items or [None]*5)[:5]:
            name = (str(it).strip() if it else "—")
            dpg.draw_rectangle((cx, yy), (cx + chip_w - 4, yy + chip_h),
                               fill=(*C["card"][:3], int(200*frac)),
                               color=(*accent_col, int(160*frac)),
                               rounding=3, parent=dl)
            _txt(dl, cx + 5, yy + 4,
                 fmt.clamp_text(name, 7),
                 (*C["txt"][:3], al), 13, "raj_r_14")
            cx += chip_w

    blue_bans = draft.get("blue_bans") or []
    red_bans  = draft.get("red_bans")  or []
    blue_pl   = _picks_to_list(draft.get("blue_picks"))
    red_pl    = _picks_to_list(draft.get("red_picks"))

    _draft_row(sy, "BANS", blue_bans, col_x_b, _BLUE_COL)
    _draft_row(sy, "BANS", red_bans,  col_x_r, _RED_COL)
    sy += 26
    _draft_row(sy, "PICKS", blue_pl, col_x_b, _BLUE_COL)
    _draft_row(sy, "PICKS", red_pl,  col_x_r, _RED_COL)
    sy += 30

    if not (blue_bans or red_bans or any(blue_pl) or any(red_pl)):
        _txt(dl, px + 20, sy, "(No draft was logged for this match.)",
             (*C["txt2"][:3], al), 14, "raj_r_14")
        sy += 20

    # ----- PREDICTIONS (Phase 5b) -----
    sy += 6
    dpg.draw_line((px + 16, sy), (vw - 16, sy),
                  color=(*C["rule_dark"][:3], int(160*frac)),
                  thickness=1, parent=dl)
    sy += 12
    sy = _draw_match_predictions(dl, px, sy, panel_w, frac, mid, winner)

    # ----- TEAM TOTALS (replaces the old TIMELINE placeholder) -----
    sy += 6
    dpg.draw_line((px + 16, sy), (vw - 16, sy),
                  color=(*C["rule_dark"][:3], int(160*frac)),
                  thickness=1, parent=dl)
    sy += 12
    _txt(dl, px + 20, sy, "TEAM TOTALS",
         (*C["gold"][:3], al), 16, "raj_sb_18")
    sy += 26

    # Aggregate per team from the participants array.
    bk = bd = bg = bv = 0
    rk = rd = rg = rv = 0
    for pt in parts:
        side = (pt.get("team") or "").lower()
        if side == "blue":
            bk += int(pt.get("kills") or 0)
            bd += int(pt.get("damage") or 0)
            bg += int(pt.get("gold") or 0)
            bv += int(pt.get("vision") or 0)
        elif side == "red":
            rk += int(pt.get("kills") or 0)
            rd += int(pt.get("damage") or 0)
            rg += int(pt.get("gold") or 0)
            rv += int(pt.get("vision") or 0)

    bar_x = px + 20
    bar_w = vw - bar_x - 24
    bar_h = 18
    label_w = 90
    val_w = 80
    inner_x = bar_x + label_w
    inner_w = bar_w - label_w - val_w * 2 - 16

    def _row(label, b_val, r_val, fmt_fn):
        nonlocal sy
        _txt(dl, bar_x, sy + 1, label.upper(),
             (*C["txt_dim"][:3], int(al * 0.95)), 13, "raj_sb_14")
        # Right-align the blue value just before the bar; red value just after.
        b_str = fmt_fn(b_val)
        r_str = fmt_fn(r_val)
        _txt(dl, inner_x - len(b_str) * 8 - 6, sy + 1, b_str,
             (*_BLUE_COL, al), 14, "raj_sb_16")
        _txt(dl, inner_x + inner_w + 8, sy + 1, r_str,
             (*_RED_COL, al), 14, "raj_sb_16")
        # Divided bar: blue's slice on the left, red's on the right, prop to share.
        total = b_val + r_val
        if total > 0:
            blue_w = int(inner_w * (b_val / total))
        else:
            blue_w = inner_w // 2
        red_w = inner_w - blue_w
        # Bar bg
        dpg.draw_rectangle((inner_x, sy), (inner_x + inner_w, sy + bar_h),
                           fill=(*C["panel"][:3], int(160 * frac)),
                           color=(0, 0, 0, 0), rounding=4, parent=dl)
        if blue_w > 0:
            dpg.draw_rectangle((inner_x, sy),
                               (inner_x + blue_w, sy + bar_h),
                               fill=(*_BLUE_COL, int(220 * frac)),
                               color=(0, 0, 0, 0),
                               rounding=4, parent=dl)
        if red_w > 0:
            dpg.draw_rectangle((inner_x + blue_w, sy),
                               (inner_x + inner_w, sy + bar_h),
                               fill=(*_RED_COL, int(220 * frac)),
                               color=(0, 0, 0, 0),
                               rounding=4, parent=dl)
        sy += bar_h + 10

    _row("Kills",   bk, rk, lambda v: str(int(v)))
    _row("Damage",  bd, rd, lambda v: fmt.compact(v))
    _row("Gold",    bg, rg, lambda v: fmt.compact(v))
    _row("Vision",  bv, rv, lambda v: str(int(v)))

    # SHARE button — bottom-right of panel
    sb_w = 90; sb_h = 28
    sbx = vw - sb_w - 20
    sby = vh - sb_h - 18
    sb_hov = (sbx <= mrx <= sbx + sb_w and sby <= mry <= sby + sb_h)
    sb_amt = effects.hover_amt(f"match_share_{mid}", sb_hov)
    dpg.draw_rectangle((sbx, sby), (sbx + sb_w, sby + sb_h),
                       fill=(*C["card_hover"][:3], int((180 + 60 * sb_amt) * frac)),
                       color=(*C["gold"][:3], int((180 + 60 * sb_amt) * frac)),
                       rounding=6, parent=dl)
    _txt(dl, sbx + 18, sby + 6, "SHARE PNG",
         (*C["gold_lt"][:3], al), 13, "raj_sb_14")

    # Close-hint footer
    _txt(dl, px + 20, vh - 28,
         "Press the X — or click the same card again — to close.",
         (*C["txt_dim"][:3], int(al*0.55)), 12, "raj_r_14")

    # X-button click
    if dpg.is_mouse_button_clicked(0) and is_close_hov:
        audio.play_click()
        inhouse.select_match(mid)
    # SHARE click — generate PNG in a worker, toast the path
    if dpg.is_mouse_button_clicked(0) and sb_hov:
        audio.play_click()
        _do_share_match(mid)
