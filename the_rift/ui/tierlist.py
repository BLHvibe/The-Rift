"""
Tier List Tab — Phase 6.
Drag-and-drop champion cards into S/A/B/C/D tier rows.
Card snaps into slot with scale-bounce on drop.
"""
import math, time
import dearpygui.dearpygui as dpg
from theme import C
from core.animations import anim

# ---------------------------------------------------------------------------
# Champion pool (demo)
# ---------------------------------------------------------------------------
_ALL_CHAMPS = [
    "Aatrox","Ahri","Akali","Alistar","Ambessa","Amumu","Annie","Ashe",
    "Blitzcrank","Camille","Caitlyn","Darius","Diana","Elise","Ezreal",
    "Fiora","Garen","Gragas","Graves","Hecarim","Irelia","Janna","Jax",
    "Jinx","Kai'Sa","Katarina","Kayn","Kennen","Khazix","Kindred",
    "Lee Sin","Leona","Lulu","Lux","Malphite","Mel","Miss Fortune",
    "Morgana","Nasus","Nautilus","Nidalee","Orianna","Pantheon","Pyke",
    "Riven","Sejuani","Smolder","Sona","Soraka","Syndra","Talon","Thresh",
    "Tristana","Twisted Fate","Veigar","Vi","Viego","Xin Zhao","Yasuo","Yone",
    "Zed","Ziggs","Zilean","Zyra",
]

TIERS = ["S","A","B","C","D"]

TIER_COLORS = {
    "S": (200, 70,  60,  255),   # red-gold
    "A": (200,155,  60,  255),   # amber
    "B": (160,136,  78,  255),   # gold
    "C": ( 92,138,  92,  255),   # muted green
    "D": ( 92,122, 156,  255),   # steel blue
}

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
class TierListState:
    def __init__(self):
        self.placements  = {t: [] for t in TIERS}   # tier → [champ_name, ...]
        self.unplaced    = list(_ALL_CHAMPS)
        self.drag_name   = None        # champion being dragged
        self.drag_pos    = (0, 0)      # current mouse pos during drag
        self.drag_origin_tier = None   # None = unplaced pool
        self.bounce      = {}          # name → scale factor (0.8→1.0 on drop)
        self.scroll_off  = 0           # pool scroll offset in px
        self._pool_h     = 0           # measured pool height for scroll clamping

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
        self.__init__()


tl = TierListState()
_F = {}
def set_fonts(f): global _F; _F = f

# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------
TIER_H      = 72     # height of each tier row
CARD_W      = 110
CARD_H      = 40
CARD_PAD    = 6
TIER_LBL_W  = 56
TOP_BAR_H   = 52
PAD         = 20
POOL_CARD_W = 96
POOL_CARD_H = 34
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

    content_y = TOP_BAR_H + PAD
    tier_area_h = len(TIERS) * (TIER_H + 4)
    pool_y = content_y + tier_area_h + 16

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
    _txt(dl, PAD+270, 18, "Drag champions from the pool into tiers  ·  Right-click a card to remove",
         (*C["txt_dim"][:3],150), 13, "raj_r_14")

    # Reset button
    bw, bh = 120, 34
    bx = vw - bw - PAD
    by = (TOP_BAR_H - bh)//2
    dpg.draw_rectangle((bx,by),(bx+bw,by+bh),
                        fill=(*C["card"][:3],200), color=(*C["rule_dark"][:3],200),
                        rounding=4, parent=dl)
    _txt(dl, bx+14, by+8, "↺  RESET", (*C["txt"][:3],200), 14, "raj_sb_16")

    if dpg.is_mouse_button_clicked(0):
        mouse = dpg.get_mouse_pos(local=False)
        vp    = dpg.get_viewport_pos()
        rx = mouse[0]-vp[0]-68; ry = mouse[1]-vp[1]-52
        if bx<=rx<=bx+bw and by<=ry<=by+bh:
            tl.reset()


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
    _txt(dl, tx, dy+4, "CHAMPION POOL", (*C["gold_dk"][:3],220), 14, "raj_sb_16")
    placed_count = sum(len(v) for v in tl.placements.values())
    total = len(_ALL_CHAMPS)
    _txt(dl, tx+190, dy+8, f"{placed_count}/{total} placed",
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

    # Scroll via mouse wheel when hovering pool
    if dpg.is_item_hovered("content_dl"):
        mouse = dpg.get_mouse_pos(local=False)
        vp    = dpg.get_viewport_pos()
        ry2   = mouse[1]-vp[1]-52
        if ry2 >= py:
            scroll = dpg.get_mouse_drag_delta(2)  # middle click drag fallback
            wheel = dpg.get_mouse_wheel()  # actually works in DPG render loop
            if wheel:
                tl.scroll_off = max(0, min(tl.scroll_off - wheel*30, max_scroll))

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
    fs = max(11, int(13*scale))
    _txt(dl, ox+6, oy+h//2-fs//2, name[:14], (*C["txt"][:3],230), fs, "raj_14")


def _draw_pool_card(dl, cx, cy, name, ghost=False):
    if ghost:
        dpg.draw_rectangle((cx,cy),(cx+POOL_CARD_W,cy+POOL_CARD_H),
                            fill=(0,0,0,0), color=(*C["rule_dark"][:3],100),
                            rounding=4, parent=dl)
        return
    dpg.draw_rectangle((cx,cy),(cx+POOL_CARD_W,cy+POOL_CARD_H),
                        fill=(*C["card"][:3],210), color=(*C["rule_dark"][:3],160),
                        rounding=4, parent=dl)
    _txt(dl, cx+6, cy+POOL_CARD_H//2-8, name[:12], (*C["txt"][:3],220), 12, "raj_14")


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
