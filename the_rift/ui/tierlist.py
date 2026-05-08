"""
Tier List Tab — Phase 6.
Drag-and-drop player cards into S/A/B/C/D/F tier rows.
Players loaded from config.json.
"""
import math, time
import dearpygui.dearpygui as dpg
from theme import C
from core.animations import anim
from data.config import load_config, save_config
from data.reader import write_tier_list

def _load_players():
    cfg = load_config()
    players = cfg.get("players", [])
    return [p for p in players if p and str(p).strip()]

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
    "S": (200, 70,  60,  255),   # red
    "A": (200,155,  60,  255),   # amber
    "B": (160,136,  78,  255),   # gold
    "C": ( 92,138,  92,  255),   # muted green
    "D": ( 92,122, 156,  255),   # steel blue
    "F": ( 90,  90,  90,  255),  # grey
}

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
_TL_SUBMIT_WIN = "tl_submit_dialog"
_TL_RATER_WIN  = "tl_rater_win"


class TierListState:
    def __init__(self):
        self.placements  = {t: [] for t in TIERS}   # tier → [player_name, ...]
        self.unplaced    = _load_players()
        self.drag_name   = None        # player being dragged
        self.drag_pos    = (0, 0)      # current mouse pos during drag
        self.drag_origin_tier = None   # None = unplaced pool
        self.bounce      = {}          # name → scale factor (0.8→1.0 on drop)
        self.scroll_off  = 0           # pool scroll offset in px
        self._pool_h     = 0           # measured pool height for scroll clamping
        self.submit_status = ""        # "" | "Submitting…" | "✓ Submitted" | "✗ Error: ..."
        self.submit_flash  = 0.0       # monotonic time of last status set (fades after 4s)
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
        self.submit_status = ""
        self.submit_flash  = 0.0
        self.rater_name    = _load_rater_name()


tl = TierListState()
_F = {}
def set_fonts(f): global _F; _F = f

_wheel_delta = [0]   # accumulated between frames; consumed in _draw_pool

def _on_wheel(sender, app_data):
    _wheel_delta[0] += app_data

def register_wheel_handler():
    """Call once after DPG context is created."""
    if dpg.does_item_exist("tl_wheel_registry"):
        return
    with dpg.handler_registry(tag="tl_wheel_registry"):
        dpg.add_mouse_wheel_handler(callback=_on_wheel)

# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------
TIER_H      = 72     # height of each tier row (6 tiers now)
CARD_W      = 150
CARD_H      = 52
CARD_PAD    = 8
TIER_LBL_W  = 56
TOP_BAR_H   = 52
PAD         = 20
POOL_CARD_W = 150
POOL_CARD_H = 52
POOL_COLS   = 7


def _txt(dl, x, y, text, color, size, font_key=None):
    tag = dpg.draw_text((x, y), text, color=color, size=size, parent=dl)
    if font_key and font_key in _F:
        dpg.bind_item_font(tag, _F[font_key])
    return tag


# ---------------------------------------------------------------------------
# Main draw
# ---------------------------------------------------------------------------

def draw_tierlist(dl, vw, vh, fonts=None):
    if fonts:
        set_fonts(fonts)
    dpg.delete_item(dl, children_only=True)
    dpg.draw_rectangle((0,0),(vw,vh), fill=C["bg"], color=(0,0,0,0), parent=dl)

    _draw_top_bar(dl, vw)
    _ensure_rater_window(vw, vh)

    rater_bar_h = 40 if not tl.rater_name else 0
    content_y   = TOP_BAR_H + rater_bar_h + PAD
    tier_area_h = len(TIERS) * (TIER_H + 4)
    pool_y      = content_y + tier_area_h + 16

    _draw_tier_rows(dl, PAD, content_y, vw - PAD*2, vw, vh)
    _draw_pool_divider(dl, PAD, pool_y - 10, vw - PAD*2)
    _draw_pool(dl, PAD, pool_y, vw - PAD*2, vh - pool_y - PAD, vw, vh)

    # Draw dragged card on top of everything
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
    _txt(dl, PAD, 12, "TIER LIST BUILDER", (*C["gold"][:3],220), 22, "raj_24")
    _txt(dl, PAD+270, 18, "Drag players from the pool into tiers  ·  Right-click a card to remove",
         (*C["txt_dim"][:3],150), 13, "raj_r_14")

    # Reset button
    bw, bh = 120, 34
    bx = vw - bw - PAD
    by = (TOP_BAR_H - bh)//2
    dpg.draw_rectangle((bx,by),(bx+bw,by+bh),
                        fill=(*C["card"][:3],200), color=(*C["rule_dark"][:3],200),
                        rounding=4, parent=dl)
    _txt(dl, bx+14, by+8, "↺  RESET", (*C["txt"][:3],200), 14, "raj_sb_16")

    # Submit button
    sbw, sbh = 160, 34
    sbx = bx - sbw - 10
    sby = by
    dpg.draw_rectangle((sbx,sby),(sbx+sbw,sby+sbh),
                        fill=(*C["gold_dk"][:3],200), color=(*C["gold"][:3],200),
                        rounding=4, parent=dl)
    _txt(dl, sbx+14, sby+8, "◆  SUBMIT LIST", (*C["gold_lt"][:3],230), 14, "raj_sb_16")

    # Submit status flash
    status = tl.submit_status
    if status and (time.monotonic() - tl.submit_flash) < 5.0:
        st_col = C["win"] if status.startswith("✓") else C["loss"] if status.startswith("✗") else C["txt_dim"]
        _txt(dl, sbx - 320, sby+8, status, (*st_col[:3],220), 13, "raj_r_14")

    if dpg.is_mouse_button_clicked(0):
        mouse = dpg.get_mouse_pos(local=False)
        vp    = dpg.get_viewport_pos()
        rx = mouse[0]-vp[0]-68; ry = mouse[1]-vp[1]-52
        if bx<=rx<=bx+bw and by<=ry<=by+bh:
            tl.reset()
        if sbx<=rx<=sbx+sbw and sby<=ry<=sby+sbh:
            _open_submit_dialog()


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
        _txt(dl, lbl_x, lbl_y, tier, (*C["bg"][:3],240), 26, "raj_28")

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
    _txt(dl, tx, dy+4, "PLAYER POOL", (*C["gold_dk"][:3],220), 14, "raj_sb_16")
    placed_count = sum(len(v) for v in tl.placements.values())
    total = placed_count + len(tl.unplaced)
    _txt(dl, tx+170, dy+8, f"{placed_count}/{total} placed",
         (*C["txt_dim"][:3],180), 12, "raj_r_12")


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
    fill_col = (*C["card_hover"][:3],230) if dragging else (*C["card"][:3],220)
    border   = (*C["gold"][:3],220)       if dragging else (*C["rule_dark"][:3],180)
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
    dpg.draw_rectangle((cx,cy),(cx+POOL_CARD_W,cy+POOL_CARD_H),
                        fill=(*C["card"][:3],210), color=(*C["rule_dark"][:3],160),
                        rounding=4, parent=dl)
    _txt(dl, cx+8, cy+POOL_CARD_H//2-10, name, (*C["txt"][:3],220), 20, "raj_20")


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

def _ensure_rater_window(vw, vh):
    """
    Show a slim 'Rating as: [dropdown]' bar below the top bar.
    Visible whenever a rater is set or needs to be set.
    """
    if not dpg.does_item_exist(_TL_RATER_WIN):
        players = _load_players()
        rater   = tl.rater_name
        with dpg.window(tag=_TL_RATER_WIN,
                        pos=(68, TOP_BAR_H),
                        width=vw - 68, height=40,
                        no_title_bar=True, no_resize=True,
                        no_move=True, no_focus_on_appearing=True,
                        no_scrollbar=True):
            with dpg.group(horizontal=True):
                dpg.add_spacer(width=PAD - 8)
                lbl = dpg.add_text("Rating as:", color=C["txt_dim"][:3])
                if "raj_sb_14" in _F: dpg.bind_item_font(lbl, _F["raj_sb_14"])
                dpg.add_spacer(width=8)

                def _on_rater_change(s, a):
                    tl.rater_name = a
                    _save_rater_name(a)

                combo = dpg.add_combo(
                    [""] + players,
                    tag="tl_rater_combo",
                    default_value=rater if rater in players else "",
                    width=220,
                    callback=_on_rater_change,
                )
                if "raj_r_14" in _F: dpg.bind_item_font(combo, _F["raj_r_14"])

                dpg.add_spacer(width=16)
                if not tl.rater_name:
                    warn = dpg.add_text("⚠  Select your name before submitting a tier list.",
                                        color=(*C["gold_dk"][:3], 200))
                    if "raj_r_12" in _F: dpg.bind_item_font(warn, _F["raj_r_12"])
    else:
        dpg.configure_item(_TL_RATER_WIN,
                           pos=(68, TOP_BAR_H),
                           width=vw - 68, height=40)
        # Keep the combo in sync if tl.rater_name was updated
        if dpg.does_item_exist("tl_rater_combo"):
            if dpg.get_value("tl_rater_combo") != tl.rater_name:
                dpg.set_value("tl_rater_combo", tl.rater_name)


# ---------------------------------------------------------------------------
# Submit dialog
# ---------------------------------------------------------------------------

def _open_submit_dialog():
    if dpg.does_item_exist(_TL_SUBMIT_WIN):
        dpg.delete_item(_TL_SUBMIT_WIN)

    # Require rater identity before allowing submission
    if not tl.rater_name:
        # Flash warning in the rater bar instead of opening dialog
        tl.submit_status = "⚠  Select your name in the 'Rating as:' bar first."
        tl.submit_flash  = time.monotonic()
        return

    placed = sum(len(v) for v in tl.placements.values())
    if placed == 0:
        tl.submit_status = "⚠  Place at least one player before submitting."
        tl.submit_flash  = time.monotonic()
        return

    vp  = dpg.get_viewport_width(), dpg.get_viewport_height()
    w, h = 380, 200
    px  = (vp[0] - w) // 2
    py  = (vp[1] - h) // 2
    with dpg.window(tag=_TL_SUBMIT_WIN, label="Submit Tier List",
                    pos=(px, py), width=w, height=h,
                    no_resize=True, modal=True):
        dpg.add_spacer(height=12)
        t = dpg.add_text("SUBMIT YOUR TIER LIST", color=C["gold"][:3])
        if "raj_sb_18" in _F: dpg.bind_item_font(t, _F["raj_sb_18"])
        dpg.add_spacer(height=6)
        dpg.add_text(f"Submitting as:  {tl.rater_name}", color=C["txt"][:3])
        dpg.add_spacer(height=4)
        dpg.add_text(f"{placed} player(s) placed across "
                     f"{len([v for v in tl.placements.values() if v])} tier(s).",
                     color=C["txt_dim"][:3])
        dpg.add_spacer(height=18)
        with dpg.group(horizontal=True):
            dpg.add_button(label="  SUBMIT  ", callback=_do_submit,
                           width=120, height=36)
            dpg.add_spacer(width=12)
            dpg.add_button(label="Cancel##tl_cancel",
                           callback=lambda: dpg.delete_item(_TL_SUBMIT_WIN),
                           width=80, height=36)
        dpg.add_spacer(height=8)
        dpg.add_text(tag="tl_submit_status", default_value="",
                     color=C["txt_dim"][:3])


def _do_submit():
    name = tl.rater_name   # already validated in _open_submit_dialog
    if not name:
        return
    if dpg.does_item_exist("tl_submit_status"):
        dpg.configure_item("tl_submit_status", default_value="⟳  Writing to sheet…")
    tl.submit_status = "Submitting…"
    tl.submit_flash  = time.monotonic()

    def _done():
        tl.submit_status = f"✓  Submitted as {name}"
        tl.submit_flash  = time.monotonic()
        if dpg.does_item_exist("tl_submit_status"):
            dpg.configure_item("tl_submit_status", default_value=f"✓  Saved as {name}.")
        if dpg.does_item_exist(_TL_SUBMIT_WIN):
            dpg.delete_item(_TL_SUBMIT_WIN)

    def _err(msg):
        tl.submit_status = f"✗  Error: {msg[:60]}"
        tl.submit_flash  = time.monotonic()
        if dpg.does_item_exist("tl_submit_status"):
            dpg.configure_item("tl_submit_status", default_value=f"✗  {msg[:60]}")

    write_tier_list(tl.placements, name, on_done=_done, on_error=_err)
