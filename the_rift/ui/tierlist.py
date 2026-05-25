"""
Tier List Tab — Phase 6.
Drag-and-drop player cards into S/A/B/C/D/F tier rows.
Players loaded from config.json.
"""
import math, time, threading, os, random
import dearpygui.dearpygui as dpg
from theme import C
from core.animations import anim
from ui import effects, toast
from data.config import load_config, save_config
from data.reader import write_tier_list
from data.tips import TIPS


def _detect_lcu_summoner():
    """
    Read the LCU lockfile and return (game_name, error_str).
    Tries gameName first (Riot ID era), falls back to displayName.
    """
    candidates = []
    local_app = os.environ.get("LOCALAPPDATA", "")
    if local_app:
        candidates.append(os.path.join(local_app, "Riot Games", "League of Legends", "lockfile"))
    for drive in ("C:\\", "D:\\", "E:\\"):
        candidates.append(os.path.join(drive, "Riot Games", "League of Legends", "lockfile"))
        candidates.append(os.path.join(drive, "Program Files", "Riot Games", "League of Legends", "lockfile"))
        candidates.append(os.path.join(drive, "Program Files (x86)", "Riot Games", "League of Legends", "lockfile"))

    lockfile = next((p for p in candidates if os.path.isfile(p)), None)
    if not lockfile:
        return None, "League client not running (lockfile not found)"

    try:
        with open(lockfile, "r") as f:
            parts = f.read().strip().split(":")
        if len(parts) < 5:
            return None, "Unexpected lockfile format"
        port, password = parts[2], parts[3]
    except Exception as e:
        return None, f"Could not read lockfile: {e}"

    try:
        import requests
        from requests.auth import HTTPBasicAuth
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        url = f"https://127.0.0.1:{port}/lol-summoner/v1/current-summoner"
        r = requests.get(url, auth=HTTPBasicAuth("riot", password),
                         verify=False, timeout=5)
        if r.status_code == 200:
            j       = r.json()
            name    = j.get("gameName") or j.get("displayName") or ""
            return (name or None), ("" if name else "No name in LCU response")
        return None, f"LCU returned {r.status_code}"
    except Exception as e:
        return None, str(e)


def _resolve_summoner_to_player(game_name):
    """
    Map a Riot gameName > in-house player name.
    Priority: live sheet summoner_map > config summoner_map > direct name match.
    Returns matched player name or None.
    """
    from data.reader import live
    # 1. Live sheet map (Players tab riot_id column)
    if live.loaded and live.summoner_map:
        result = live.summoner_map.get(game_name)
        if result:
            return result
    # 2. Config summoner_map (manually set or saved by picker)
    cfg  = load_config()
    smap = cfg.get("summoner_map", {})
    if game_name in smap:
        return smap[game_name]
    # 3. Direct name match (gameName == display name)
    players = _load_players()
    if game_name in players:
        return game_name
    return None


def _save_summoner_link(game_name, player_name):
    """Persist gameName > player_name to config summoner_map."""
    cfg = load_config()
    smap = cfg.setdefault("summoner_map", {})
    smap[game_name] = player_name
    save_config(cfg)

def _load_players():
    """Return ordered list of real player names. Live sheet takes priority over config."""
    from data.reader import live
    if live.loaded and live.players:
        return list(live.players)
    cfg = load_config()
    players = cfg.get("players", [])
    return [p for p in players if p and str(p).strip()
            and not str(p).upper().startswith("PLAYER")
            and str(p).upper() not in ("TBD", "TBA")]

def _load_rater_name():
    """Return the saved 'Rating as' identity, or empty string if unset."""
    return load_config().get("tier_list_rater", "")

def _save_rater_name(name):
    """Persist the 'Rating as' identity to config."""
    cfg = load_config()
    cfg["tier_list_rater"] = name
    save_config(cfg)

TIERS = ["S", "A", "B", "C", "D", "F"]

TIER_COLORS = {
    "S": (210, 40,  40,  255),   # red
    "A": (200,155,  60,  255),   # amber
    "B": (160,136,  78,  255),   # gold
    "C": ( 92,138,  92,  255),   # muted green
    "D": ( 92,122, 156,  255),   # steel blue
    "F": ( 90,  90,  90,  255),  # grey
}

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
_TL_RATER_WIN  = "tl_rater_win"


class TierListState:
    def __init__(self):
        self.placements  = {t: [] for t in TIERS}   # tier > [player_name, ...]
        self.unplaced    = _load_players()
        self.drag_name   = None        # player being dragged
        self.drag_pos    = (0, 0)      # current mouse pos during drag
        self.drag_origin_tier = None   # None = unplaced pool
        self.bounce      = {}          # name > scale factor (0.8>1.0 on drop)
        self.scroll_off  = 0           # pool scroll offset in px
        self._pool_h     = 0           # measured pool height for scroll clamping
        self.submitting    = False     # True while a submit is in flight
        self.rater_name    = _load_rater_name()   # persisted "Rating as:" identity

    def place(self, name, tier):
        # Remove from wherever it is
        self.unplaced = [c for c in self.unplaced if c != name]
        for t in TIERS:
            self.placements[t] = [c for c in self.placements[t] if c != name]
        self.placements[tier].append(name)
        # Bounce animation
        self.bounce[name] = 0.75
        anim.tween(0.75, 1.0, 220, "elastic_out",
                   on_update=lambda v, n=name: self.bounce.update({n: v}),
                   on_done=lambda n=name: self.bounce.pop(n, None))

    def remove(self, name):
        for t in TIERS:
            self.placements[t] = [c for c in self.placements[t] if c != name]
        if name not in self.unplaced:
            self.unplaced.append(name)

    def reset(self):
        self.placements  = {t: [] for t in TIERS}
        self.unplaced    = _load_players()
        self.drag_name   = None
        self.drag_pos    = (0, 0)
        self.drag_origin_tier = None
        self.bounce      = {}
        self.scroll_off  = 0
        self._pool_h     = 0
        self.submitting    = False
        self.rater_name    = _load_rater_name()


tl = TierListState()
_F = {}
def set_fonts(f): global _F; _F = f

_wheel_delta = [0]   # accumulated between frames; consumed in _draw_pool

# ---------------------------------------------------------------------------
# Detection gate + welcome cover page
# ---------------------------------------------------------------------------
_TIPS = TIPS  # from data/tips.py

# Phase flags (per-session, reset when the module is reloaded)
_tl_unlocked = False   # True once cover page has finished > tier list is accessible

_cv = {
    "active":      False,
    "name":        "",
    "tip":         "",
    "name_offset": -700.0,
    "bar_pct":     0.0,
    "alpha":       0,
}

# Detection screen state (status line + optional name picker)
_det = {
    "status":   "",
    "color":    (70, 65, 55, 255),
    "busy":     False,
    "picker":   False,   # True when we need the user to pick their player name
    "summoner": "",      # raw gameName returned by LCU (shown in picker prompt)
}


def _show_cover_page(player_name):
    global _tl_unlocked
    _tl_unlocked = False   # lock again until cover finishes
    _cv.update({
        "active":      True,
        "name":        player_name,
        "tip":         random.choice(_TIPS),
        "name_offset": -700.0,
        "bar_pct":     0.0,
        "alpha":       0,
    })
    anim.tween(0, 255, 200, "out_cubic",
               on_update=lambda v: _cv.update({"alpha": int(v)}))
    anim.tween(-700.0, 0.0, 800, "elastic_out",
               on_update=lambda v: _cv.update({"name_offset": v}))
    anim.tween(0.0, 1.0, 4700, "linear",
               on_update=lambda v: _cv.update({"bar_pct": v}))
    anim.tween(0, 1, 1, "linear", delay_ms=5000, on_done=_hide_cover_page)


def _hide_cover_page():
    anim.tween(255, 0, 400, "out_cubic",
               on_update=lambda v: _cv.update({"alpha": int(v)}),
               on_done=_on_cover_hidden)


def _on_cover_hidden():
    global _tl_unlocked
    _cv["active"] = False
    _tl_unlocked  = True


def _draw_cover(dl, vw, vh):
    al = _cv["alpha"]
    if al <= 0:
        return

    dpg.draw_rectangle((0, 0), (vw, vh),
                        fill=(*C["bg"][:3], al),
                        color=(0, 0, 0, 0), parent=dl)
    dpg.draw_rectangle((0, 0), (vw, 5),
                        fill=(*C["gold_dk"][:3], al),
                        color=(0, 0, 0, 0), parent=dl)
    # Ambient drift field
    try:
        from ui.effects import draw_drift_field
        draw_drift_field(dl, 0, 0, vw, vh, alpha=int(al * 0.8),
                         accent=C["gold"][:3], n_dots=24, seed=37)
    except Exception:
        pass

    cx     = vw // 2
    cy     = vh // 2
    offset = int(_cv["name_offset"])

    _txt(dl, cx - 72, cy - 90 + offset, "Welcome,",
         (*C["txt2"][:3], al), 29, "raj_36")

    name   = _cv["name"].upper()
    name_x = max(20, cx - len(name) * 16)
    _txt(dl, name_x, cy - 36 + offset, name,
         (*C["gold_lt"][:3], al), 52, "raj_56")

    tip   = _cv["tip"]
    tip_x = max(40, cx - len(tip) * 5)
    _txt(dl, tip_x, cy + 62 + offset, tip,
         (*C["txt_dim"][:3], int(al * 0.8)), 19, "raj_r_18")

    bar_w  = min(420, vw - 120)
    bar_x  = cx - bar_w // 2
    bar_y  = vh - 70
    dpg.draw_rectangle((bar_x, bar_y), (bar_x + bar_w, bar_y + 6),
                        fill=(*C["card"][:3], int(al * 0.6)),
                        color=(0, 0, 0, 0), rounding=3, parent=dl)
    fill_w = int(bar_w * _cv["bar_pct"])
    if fill_w > 0:
        dpg.draw_rectangle((bar_x, bar_y), (bar_x + fill_w, bar_y + 6),
                            fill=(*C["gold"][:3], al),
                            color=(0, 0, 0, 0), rounding=3, parent=dl)
    _txt(dl, bar_x, bar_y + 12, "LOADING TIER LIST…",
         (*C["txt_dim"][:3], int(al * 0.5)), 17, "raj_r_16")


def _draw_detection_screen(dl, vw, vh):
    """Full-screen gate shown until the user detects their identity."""
    cx, cy = vw // 2, vh // 2
    t = (math.sin(time.monotonic() * 1.3) + 1) / 2
    a = int(90 + t * 110)

    # --- Name picker (shown when gameName couldn't be auto-matched) ---
    if _det["picker"]:
        _txt(dl, cx - 180, cy - 110, "WHO ARE YOU?", (*C["gold"][:3], a), 36, "raj_36")
        summoner = _det["summoner"]
        sub = f"Signed in as  '{summoner}'  — select your player name:"
        _txt(dl, max(20, cx - len(sub) * 4), cy - 58, sub,
             (*C["txt_dim"][:3], int(a * 0.75)), 17, "raj_r_16")

        players  = _load_players()
        cols     = 4
        bw, bh   = 160, 40
        gap      = 12
        total_w  = cols * bw + (cols - 1) * gap
        start_x  = cx - total_w // 2
        start_y  = cy - 24

        clicked = dpg.is_mouse_button_clicked(0)
        mouse   = dpg.get_mouse_pos(local=False)
        vp      = dpg.get_viewport_pos()
        rx = mouse[0] - vp[0] - 68
        ry = mouse[1] - vp[1] - 52

        for i, pname in enumerate(players):
            col_i = i % cols
            row_i = i // cols
            bx = start_x + col_i * (bw + gap)
            by = start_y + row_i * (bh + gap)
            dpg.draw_rectangle((bx, by), (bx + bw, by + bh),
                                fill=(*C["card"][:3], 200),
                                color=(*C["gold_dk"][:3], 180), rounding=4, parent=dl)
            lx = bx + bw // 2 - len(pname) * 6
            _txt(dl, lx, by + 11, pname, (*C["gold_lt"][:3], 220), 18, "raj_sb_18")
            if clicked and bx <= rx <= bx + bw and by <= ry <= by + bh:
                _save_summoner_link(summoner, pname)
                tl.rater_name    = pname
                _save_rater_name(pname)
                _det["picker"]   = False
                _det["summoner"] = ""
                _det["status"]   = ""
                _show_cover_page(pname)
        return

    # --- Normal detection screen ---
    _txt(dl, cx - 140, cy - 80, "TIER LIST", (*C["gold"][:3], a), 44, "cinzel_44")
    _txt(dl, cx - 168, cy - 20, "Identify yourself to begin rating",
         (*C["txt_dim"][:3], int(a * 0.7)), 17, "raj_r_16")

    bw, bh = 300, 56
    bx, by = cx - bw // 2, cy + 20
    dpg.draw_rectangle((bx, by), (bx + bw, by + bh),
                        fill=(*C["gold_dk"][:3], 210),
                        color=(*C["gold"][:3], 210), rounding=6, parent=dl)
    lbl     = "DETECTING…" if _det["busy"] else "DETECT FROM LOL CLIENT"
    lbl_col = (*C["txt_dim"][:3], 160) if _det["busy"] else (*C["gold_lt"][:3], 230)
    _txt(dl, bx + bw // 2 - len(lbl) * 5, by + 16, lbl, lbl_col, 17, "raj_sb_16")

    if _det["status"]:
        st_x = max(20, cx - len(_det["status"]) * 4)
        _txt(dl, st_x, by + bh + 14, _det["status"],
             (*_det["color"][:3], 220), 17, "raj_r_16")

    if not _det["busy"] and dpg.is_mouse_button_clicked(0):
        mouse = dpg.get_mouse_pos(local=False)
        vp    = dpg.get_viewport_pos()
        rx = mouse[0] - vp[0] - 68
        ry = mouse[1] - vp[1] - 52
        if bx <= rx <= bx + bw and by <= ry <= by + bh:
            _run_detect_from_screen()


def _on_wheel(sender, app_data):
    _wheel_delta[0] += app_data


def register_wheel_handler():
    """Call once after DPG context is created."""
    if dpg.does_item_exist("tl_wheel_registry"):
        return
    with dpg.handler_registry(tag="tl_wheel_registry"):
        dpg.add_mouse_wheel_handler(callback=_on_wheel)


def _run_detect_from_screen():
    """Detection triggered from the gate screen (no rater DPG window yet)."""
    _det["busy"]   = True
    _det["status"] = "Connecting to LoL client…"
    _det["color"]  = C["txt_dim"]

    def _bg():
        game_name, err = _detect_lcu_summoner()
        if not game_name:
            _det["busy"]   = False
            _det["status"] = f"✗  {err[:60]}"
            _det["color"]  = C["loss"]
            return
        matched = _resolve_summoner_to_player(game_name)
        _det["busy"] = False
        if matched:
            tl.rater_name = matched
            _save_rater_name(matched)
            _det["status"] = ""
            _show_cover_page(matched)
        else:
            # Unknown summoner — show picker so user links once
            _det["summoner"] = game_name
            _det["picker"]   = True
            _det["status"]   = ""

    threading.Thread(target=_bg, daemon=True).start()

# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------
TIER_H      = 72     # height of each tier row (6 tiers now)
CARD_W      = 150
CARD_H      = 52
CARD_PAD    = 8
TIER_LBL_W  = 56
TOP_BAR_H   = 52
_VP_TITLE_H = 52   # main window titlebar height in viewport coords
PAD         = 20
POOL_CARD_W = 150
POOL_CARD_H = 52
POOL_COLS   = 7


def _txt(dl, x, y, text, color, size, font_key=None):
    tag = dpg.draw_text((x, y), text, color=color, size=size, parent=dl)
    if font_key and font_key in _F:
        dpg.bind_item_font(tag, _F[font_key])
    return tag


def _card_hovered(x, y, w, h):
    """True when the cursor is over the rect (content-area-relative coords)."""
    m  = dpg.get_mouse_pos(local=False)
    vp = dpg.get_viewport_pos()
    rx = m[0] - vp[0] - 68
    ry = m[1] - vp[1] - 52
    return x <= rx <= x + w and y <= ry <= y + h


# ---------------------------------------------------------------------------
# Main draw
# ---------------------------------------------------------------------------

def draw_tierlist(dl, vw, vh, fonts=None):
    if fonts:
        set_fonts(fonts)
    dpg.delete_item(dl, children_only=True)
    dpg.draw_rectangle((0,0),(vw,vh), fill=C["bg"], color=(0,0,0,0), parent=dl)
    # Prevent native content_win scroll from fighting with scroll_off-based pool scroll
    if dpg.does_item_exist("content_win"):
        dpg.set_y_scroll("content_win", 0)

    # Phase 1: cover page animating (detection just succeeded)
    if _cv["active"]:
        _draw_cover(dl, vw, vh)
        return

    # Phase 2: not yet unlocked > show detection gate
    if not _tl_unlocked:
        _draw_detection_screen(dl, vw, vh)
        return

    # Phase 3: unlocked > full tier list
    _draw_top_bar(dl, vw)
    if dpg.does_item_exist(_TL_RATER_WIN):
        dpg.delete_item(_TL_RATER_WIN)

    rater_bar_h = 40
    content_y   = TOP_BAR_H + rater_bar_h + PAD
    _draw_rater_bar(dl, vw, TOP_BAR_H, rater_bar_h)
    tier_area_h = len(TIERS) * (TIER_H + 4)
    pool_y      = content_y + tier_area_h + 16

    _draw_tier_rows(dl, PAD, content_y, vw - PAD*2, vw, vh)
    _draw_pool_divider(dl, PAD, pool_y - 10, vw - PAD*2)
    _draw_pool(dl, PAD, pool_y, vw - PAD*2, vh - pool_y - PAD, vw, vh)

    if tl.drag_name:
        mx, my = tl.drag_pos
        _draw_card(dl, mx - CARD_W//2, my - CARD_H//2, tl.drag_name,
                   ghost=False, scale=1.0, dragging=True)

    _handle_drag(vw, vh, content_y, pool_y)


def _draw_top_bar(dl, vw):
    dpg.draw_rectangle((0,0),(vw,TOP_BAR_H), fill=(*C["panel"][:3],220),
                        color=(0,0,0,0), parent=dl)
    dpg.draw_line((0,TOP_BAR_H-1),(vw,TOP_BAR_H-1),
                  color=C["rule_dark"], thickness=1, parent=dl)
    _txt(dl, PAD, 12, "TIER LIST BUILDER", (*C["gold"][:3],220), 22, "cinzel_22")
    _txt(dl, PAD+270, 18, "Drag players from the pool into tiers  ·  Right-click a card to remove",
         (*C["txt_dim"][:3],150), 17, "raj_r_16")

    # Reset button
    bw, bh = 120, 34
    bx = vw - bw - PAD
    by = (TOP_BAR_H - bh)//2
    dpg.draw_rectangle((bx,by),(bx+bw,by+bh),
                        fill=(*C["card"][:3],200), color=(*C["rule_dark"][:3],200),
                        rounding=4, parent=dl)
    _txt(dl, bx+14, by+8, "RESET", (*C["txt"][:3],200), 17, "raj_sb_16")

    # Submit button
    sbw, sbh = 160, 34
    sbx = bx - sbw - 10
    sby = by
    dpg.draw_rectangle((sbx,sby),(sbx+sbw,sby+sbh),
                        fill=(*C["gold_dk"][:3],200), color=(*C["gold"][:3],200),
                        rounding=4, parent=dl)
    _txt(dl, sbx+14, sby+8, "SUBMIT LIST", (*C["gold_lt"][:3],230), 17, "raj_sb_16")

    if dpg.is_mouse_button_clicked(0):
        mouse = dpg.get_mouse_pos(local=False)
        vp    = dpg.get_viewport_pos()
        rx = mouse[0]-vp[0]-68; ry = mouse[1]-vp[1]-52
        if bx<=rx<=bx+bw and by<=ry<=by+bh:
            tl.reset()
        if sbx<=rx<=sbx+sbw and sby<=ry<=sby+sbh:
            _do_submit()


def _draw_rater_bar(dl, vw, rater_y, rater_h):
    """Draw the 'Rating as' identity bar directly on the drawlist — no floating window."""
    dpg.draw_rectangle((0, rater_y), (vw, rater_y + rater_h),
                        fill=(*C["panel"][:3], 200), color=(0,0,0,0), parent=dl)
    dpg.draw_line((0, rater_y), (vw, rater_y),
                  color=C["rule_dark"], thickness=1, parent=dl)
    dpg.draw_line((0, rater_y + rater_h - 1), (vw, rater_y + rater_h - 1),
                  color=C["rule_dark"], thickness=1, parent=dl)

    ty = rater_y + rater_h // 2 - 7
    tx = PAD

    _txt(dl, tx, ty, "Rating as:", (*C["txt_dim"][:3], 200), 17, "raj_sb_16")
    tx += 92

    rater = tl.rater_name
    id_text  = f"✓  {rater}" if rater else "Not identified"
    id_color = (*C["win"][:3], 220) if rater else (*C["txt_dim"][:3], 180)
    _txt(dl, tx, ty, id_text, id_color, 17, "raj_r_16")
    tx += max(180, len(id_text) * 9 + 20)

    busy = _det.get("busy", False)
    btn_lbl = "Detecting…" if busy else "Detect from LoL Client"
    bw, bh  = 190, 26
    bx      = tx
    by      = rater_y + (rater_h - bh) // 2
    btn_fill = (*C["card"][:3], 140) if busy else (*C["gold_dk"][:3], 200)
    btn_bdr  = (*C["rule_dark"][:3], 140) if busy else (*C["gold"][:3], 180)
    dpg.draw_rectangle((bx, by), (bx + bw, by + bh),
                        fill=btn_fill, color=btn_bdr, rounding=3, parent=dl)
    _txt(dl, bx + 10, by + 6, btn_lbl, (*C["gold_lt"][:3], 210 if not busy else 120), 16, "raj_r_16")

    status = _det.get("status", "")
    if status:
        st_col = C["loss"] if status.startswith("✗") else C["txt_dim"]
        _txt(dl, bx + bw + 14, by + 6, status[:70], (*st_col[:3], 200), 16, "raj_r_16")

    # D1 (sheet decommission): the LEAGUE PULSE strip — which rotated
    # cross-rater meta sourced from the Consensus / Hot Takes / Rater Bias
    # sheets — was removed alongside those sheets. The rater bar now ends
    # at the IDENTIFY button.

    if not busy and dpg.is_mouse_button_clicked(0):
        mouse = dpg.get_mouse_pos(local=False)
        vp    = dpg.get_viewport_pos()
        rx = mouse[0] - vp[0] - 68
        ry = mouse[1] - vp[1] - 52
        if bx <= rx <= bx + bw and by <= ry <= by + bh:
            _detect_identity_bg()


def _draw_tier_rows(dl, tx, ty, tw, vw, vh):
    for i, tier in enumerate(TIERS):
        row_y  = ty + i*(TIER_H+4)
        tcol   = TIER_COLORS[tier]

        # Row background
        dpg.draw_rectangle((tx, row_y),(tx+tw, row_y+TIER_H),
                            fill=(*C["card"][:3],220),
                            color=(*C["rule_dark"][:3],180),
                            rounding=4, parent=dl)

        # Tier label box
        dpg.draw_rectangle((tx, row_y),(tx+TIER_LBL_W, row_y+TIER_H),
                            fill=(*tcol[:3],220), color=(0,0,0,0),
                            rounding=4, parent=dl)
        lbl_x = tx + TIER_LBL_W//2 - 10
        lbl_y = row_y + TIER_H//2 - 14
        _txt(dl, lbl_x, lbl_y, tier, (*C["bg"][:3],240), 27, "raj_36")

        # Cards in this tier
        cx = tx + TIER_LBL_W + CARD_PAD
        for name in tl.placements[tier]:
            scale = tl.bounce.get(name, 1.0)
            if tl.drag_name == name:
                # Draw ghost placeholder
                _draw_card(dl, cx, row_y + (TIER_H-CARD_H)//2, name, ghost=True, scale=1.0)
            else:
                _draw_card(dl, cx, row_y + (TIER_H-CARD_H)//2, name, scale=scale)
            cx += CARD_W + CARD_PAD

        # Drop zone hint when dragging
        if tl.drag_name and not _tier_contains(tier, tl.drag_name):
            hint_x = cx
            dpg.draw_rectangle((hint_x, row_y+4),(hint_x+CARD_W, row_y+TIER_H-4),
                                fill=(0,0,0,0),
                                color=(*tcol[:3],80),
                                rounding=4, parent=dl)


def _tier_contains(tier, name):
    return name in tl.placements.get(tier, [])


def _draw_pool_divider(dl, tx, dy, tw):
    dpg.draw_line((tx, dy),(tx+tw, dy), color=(*C["rule_dark"][:3],180), thickness=1, parent=dl)
    _txt(dl, tx, dy+4, "PLAYER POOL", (*C["gold_dk"][:3],220), 17, "raj_sb_16")
    placed_count = sum(len(v) for v in tl.placements.values())
    total = placed_count + len(tl.unplaced)
    _txt(dl, tx+170, dy+8, f"{placed_count}/{total} placed",
         (*C["txt_dim"][:3],180), 15, "raj_r_14")


def _draw_pool(dl, px, py, pw, ph, vw, vh):
    # Clamp scroll
    cols    = max(1, (pw + CARD_PAD) // (POOL_CARD_W + CARD_PAD))
    visible = [c for c in tl.unplaced]
    rows    = math.ceil(len(visible) / cols) if visible else 0
    total_h = rows * (POOL_CARD_H + CARD_PAD)
    tl._pool_h = total_h
    max_scroll = max(0, total_h - ph + PAD)
    tl.scroll_off = max(0, min(tl.scroll_off, max_scroll))

    # Consume accumulated wheel delta when mouse is over pool area
    if _wheel_delta[0] != 0:
        mouse = dpg.get_mouse_pos(local=False)
        vp    = dpg.get_viewport_pos()
        ry2   = mouse[1]-vp[1]-52
        if ry2 >= py:
            tl.scroll_off = max(0, min(tl.scroll_off - _wheel_delta[0]*30, max_scroll))
        _wheel_delta[0] = 0

    # Draw scissor region background
    dpg.draw_rectangle((px, py),(px+pw, py+ph),
                        fill=(*C["bg"][:3],120), color=(0,0,0,0), parent=dl)

    for i, name in enumerate(visible):
        row = i // cols
        col = i % cols
        cx  = px + col * (POOL_CARD_W + CARD_PAD)
        cy  = py + row * (POOL_CARD_H + CARD_PAD) - int(tl.scroll_off)
        if cy + POOL_CARD_H < py or cy > py + ph:
            continue
        if tl.drag_name == name:
            _draw_pool_card(dl, cx, cy, name, ghost=True)
        else:
            _draw_pool_card(dl, cx, cy, name)


def _draw_card(dl, cx, cy, name, ghost=False, scale=1.0, dragging=False):
    w = int(CARD_W * scale)
    h = int(CARD_H * scale)
    ox = cx + (CARD_W - w)//2
    oy = cy + (CARD_H - h)//2
    if ghost:
        dpg.draw_rectangle((ox,oy),(ox+w,oy+h),
                            fill=(0,0,0,0), color=(*C["rule_dark"][:3],120),
                            rounding=4, parent=dl)
        return
    hov = (not dragging and tl.drag_name is None
           and _card_hovered(cx, cy, CARD_W, CARD_H))
    amt = effects.hover_amt(f"tlcard:{name}", hov)
    if amt > 0.01:
        effects.draw_hover_glow(dl, ox, oy, ox+w, oy+h, C["gold"], amt, rounding=4)
    fill_col = (*C["card_hover"][:3],230) if dragging else (*C["card"][:3],220)
    border   = (*C["gold"][:3],220) if (dragging or hov) else (*C["rule_dark"][:3],180)
    dpg.draw_rectangle((ox,oy),(ox+w,oy+h), fill=fill_col, color=border,
                        rounding=4, parent=dl)
    fs = max(16, int(20*scale))
    fk = "raj_20" if scale >= 0.9 else "raj_18"
    _txt(dl, ox+8, oy+h//2-fs//2, name, (*C["txt"][:3],230), fs, fk)


def _draw_pool_card(dl, cx, cy, name, ghost=False):
    if ghost:
        dpg.draw_rectangle((cx,cy),(cx+POOL_CARD_W,cy+POOL_CARD_H),
                            fill=(0,0,0,0), color=(*C["rule_dark"][:3],100),
                            rounding=4, parent=dl)
        return
    hov = (tl.drag_name is None
           and _card_hovered(cx, cy, POOL_CARD_W, POOL_CARD_H))
    amt = effects.hover_amt(f"tlpool:{name}", hov)
    if amt > 0.01:
        effects.draw_hover_glow(dl, cx, cy, cx+POOL_CARD_W, cy+POOL_CARD_H,
                                C["gold"], amt, rounding=4)
    border = (*C["gold"][:3],220) if hov else (*C["rule_dark"][:3],160)
    dpg.draw_rectangle((cx,cy),(cx+POOL_CARD_W,cy+POOL_CARD_H),
                        fill=(*C["card"][:3],210), color=border,
                        rounding=4, parent=dl)
    _txt(dl, cx+8, cy+POOL_CARD_H//2-10, name, (*C["txt"][:3],220), 21, "raj_20")


def _handle_drag(vw, vh, content_y, pool_y):
    mouse = dpg.get_mouse_pos(local=False)
    vp    = dpg.get_viewport_pos()
    rx = mouse[0]-vp[0]-68
    ry = mouse[1]-vp[1]-52
    tl.drag_pos = (rx, ry)

    # Pick up card — left button press
    if dpg.is_mouse_button_down(0) and tl.drag_name is None:
        # Check tier rows
        for i, tier in enumerate(TIERS):
            row_y = content_y + i*(TIER_H+4)
            if row_y <= ry <= row_y+TIER_H:
                cx = PAD + TIER_LBL_W + CARD_PAD
                for name in tl.placements[tier]:
                    if cx <= rx <= cx+CARD_W and row_y+(TIER_H-CARD_H)//2 <= ry <= row_y+(TIER_H+CARD_H)//2:
                        tl.drag_name = name
                        tl.drag_origin_tier = tier
                        return
                    cx += CARD_W + CARD_PAD
        # Check pool
        if ry >= pool_y:
            cols = max(1, (vw - PAD*2 + CARD_PAD) // (POOL_CARD_W + CARD_PAD))
            for i, name in enumerate(tl.unplaced):
                row = i // cols
                col = i % cols
                cx  = PAD + col*(POOL_CARD_W+CARD_PAD)
                cy  = pool_y + row*(POOL_CARD_H+CARD_PAD) - int(tl.scroll_off)
                if cx <= rx <= cx+POOL_CARD_W and cy <= ry <= cy+POOL_CARD_H:
                    tl.drag_name = name
                    tl.drag_origin_tier = None
                    return

    # Release card — drop into tier
    if tl.drag_name and not dpg.is_mouse_button_down(0):
        name = tl.drag_name
        tl.drag_name = None
        for i, tier in enumerate(TIERS):
            row_y = content_y + i*(TIER_H+4)
            if row_y <= ry <= row_y+TIER_H and PAD+TIER_LBL_W <= rx <= vw-PAD:
                tl.place(name, tier)
                return
        # Dropped outside — return to pool
        tl.remove(name)

    # Right-click to remove from tier
    if dpg.is_mouse_button_clicked(1):
        for i, tier in enumerate(TIERS):
            row_y = content_y + i*(TIER_H+4)
            if row_y <= ry <= row_y+TIER_H:
                cx = PAD + TIER_LBL_W + CARD_PAD
                for name in list(tl.placements[tier]):
                    if cx <= rx <= cx+CARD_W:
                        tl.remove(name)
                        return
                    cx += CARD_W + CARD_PAD


# ---------------------------------------------------------------------------
# Rater identity bar
# ---------------------------------------------------------------------------

def _detect_identity_bg():
    """Button callback — detects LCU summoner name in a background thread."""
    _det["busy"]   = True
    _det["status"] = ""

    def _bg():
        game_name, err = _detect_lcu_summoner()
        if not game_name:
            _det["busy"]   = False
            _det["status"] = f"✗ {err[:60]}"
            _det["color"]  = C["loss"]
            return
        matched = _resolve_summoner_to_player(game_name)
        _det["busy"] = False
        if matched:
            tl.rater_name = matched
            _save_rater_name(matched)
            _det["status"] = ""
            _show_cover_page(matched)
        else:
            # Unknown summoner — fall back to picker on the gate screen
            global _tl_unlocked
            _tl_unlocked       = False
            _det["summoner"]   = game_name
            _det["picker"]     = True
            _det["status"]     = ""

    threading.Thread(target=_bg, daemon=True).start()


# ---------------------------------------------------------------------------
# Submit
# ---------------------------------------------------------------------------

def _do_submit():
    """Validate and submit the tier list — feedback via the toast stack."""
    if tl.submitting:
        return
    if not tl.rater_name:
        toast.push("Detect your identity from the LoL client first.",
                   kind="warn", title="Can't submit")
        return
    placed = sum(len(v) for v in tl.placements.values())
    if placed == 0:
        toast.push("Place at least one player before submitting.",
                   kind="warn", title="Can't submit")
        return
    name = tl.rater_name
    tl.submitting = True

    def _done():
        tl.submitting = False
        toast.push(f"Tier list submitted as {name}.",
                   kind="success", title="Submitted")
        # Drop a TIER_LIST activity event so the feed reflects something other
        # than inhouse log events. Best-effort — never block the success toast.
        try:
            from data.reader import write_activity_event
            placed_count = sum(len(v) for v in (tl.placements or {}).values())
            write_activity_event(
                "TIER_LIST", name,
                f"submitted tier-list ratings — {placed_count} placed")
        except Exception:
            pass

    def _err(msg):
        tl.submitting = False
        toast.push(str(msg)[:90], kind="error", title="Submit failed")

    write_tier_list(tl.placements, name, on_done=_done, on_error=_err)
