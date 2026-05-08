"""
Left sidebar navigation.
Collapsed (48px) showing geometric icons only.
Expands to 160px on hover, revealing text labels that fade in.
"""
import dearpygui.dearpygui as dpg
import math
from theme import C
from core.state import state
from core.animations import anim

_OVERLAY_TAGS = {
    "settings": "settings_overlay_win",
    "commands": "commands_overlay_win",
    "feed":     "feed_overlay_win",
    "scout":    "scout_report_panel_win",
}

def _cleanup_overlay(tab_id):
    tag = _OVERLAY_TAGS.get(tab_id)
    if tag and dpg.does_item_exist(tag):
        dpg.delete_item(tag)

COLLAPSED_W = 68
EXPANDED_W  = 200
ICON_SIZE   = 30   # bounding box for each icon drawing
ITEM_H      = 68   # height per tab item
TOP_PAD     = 20

# Tab definitions: (id, label, draw_fn)
TABS = [
    ("rankings",  "RANKINGS",  "_draw_swords"),
    ("draft",     "DRAFT",     "_draw_shield"),
    ("scout",     "SCOUT",     "_draw_magnifier"),
    ("inhouse",   "INHOUSE",   "_draw_crossed_swords"),
    ("tierlist",  "TIER LIST", "_draw_layers"),
    ("settings",  "SETTINGS",  "_draw_gear"),
    ("commands",  "COMMANDS",  "_draw_terminal"),
    ("feed",      "ACTIVITY",  "_draw_feed_icon"),
]

# ---------------------------------------------------------------------------
# Geometric icon drawing functions
# Each receives (draw_list_tag, cx, cy, size, color)
# ---------------------------------------------------------------------------

def _draw_swords(dl, cx, cy, size, color):
    """Two crossed diagonal swords (Rankings)."""
    h = size * 0.5
    # Sword 1: top-left to bottom-right
    dpg.draw_line((cx - h, cy - h), (cx + h, cy + h), color=color, thickness=2, parent=dl)
    # Blade tip triangle
    dpg.draw_triangle((cx+h, cy+h), (cx+h-4, cy+h+1), (cx+h+1, cy+h-4),
                      color=color, fill=color, parent=dl)
    # Sword 2: top-right to bottom-left
    dpg.draw_line((cx + h, cy - h), (cx - h, cy + h), color=color, thickness=2, parent=dl)
    dpg.draw_triangle((cx-h, cy+h), (cx-h+4, cy+h+1), (cx-h-1, cy+h-4),
                      color=color, fill=color, parent=dl)
    # Crossguard on sword 1
    dpg.draw_line((cx - 5, cy - 2), (cx + 5, cy + 2), color=color, thickness=2, parent=dl)


def _draw_shield(dl, cx, cy, size, color):
    """Angular shield (Draft)."""
    w, h = size * 0.45, size * 0.5
    # Outer shield polygon
    pts = [
        (cx,     cy - h),        # top center
        (cx + w, cy - h * 0.5),  # top right
        (cx + w, cy + h * 0.2),  # mid right
        (cx,     cy + h),        # bottom point
        (cx - w, cy + h * 0.2),  # mid left
        (cx - w, cy - h * 0.5),  # top left
    ]
    dpg.draw_polygon(pts, color=color, thickness=2, parent=dl)
    # Inner accent line
    inner = [
        (cx,           cy - h * 0.55),
        (cx + w * 0.6, cy - h * 0.25),
        (cx + w * 0.6, cy + h * 0.1),
        (cx,           cy + h * 0.65),
        (cx - w * 0.6, cy + h * 0.1),
        (cx - w * 0.6, cy - h * 0.25),
    ]
    dpg.draw_polygon(inner, color=(*color[:3], 100), thickness=1, parent=dl)


def _draw_magnifier(dl, cx, cy, size, color):
    """Magnifying glass (Scout)."""
    r    = size * 0.33
    ox   = cx - size * 0.08
    oy   = cy - size * 0.08
    # Circle
    dpg.draw_circle((ox, oy), r, color=color, thickness=2, parent=dl)
    # Handle
    hx1  = ox + r * 0.72
    hy1  = oy + r * 0.72
    hx2  = cx + size * 0.44
    hy2  = cy + size * 0.44
    dpg.draw_line((hx1, hy1), (hx2, hy2), color=color, thickness=3, parent=dl)


def _draw_crossed_swords(dl, cx, cy, size, color):
    """Trophy-style crossed swords angled wider (Inhouse)."""
    h = size * 0.46
    ang = math.radians(35)
    # Sword A
    ax1, ay1 = cx - h*math.cos(ang), cy - h*math.sin(ang)
    ax2, ay2 = cx + h*math.cos(ang), cy + h*math.sin(ang)
    dpg.draw_line((ax1, ay1), (ax2, ay2), color=color, thickness=2, parent=dl)
    # Sword B
    bx1, by1 = cx + h*math.cos(ang), cy - h*math.sin(ang)
    bx2, by2 = cx - h*math.cos(ang), cy + h*math.sin(ang)
    dpg.draw_line((bx1, by1), (bx2, by2), color=color, thickness=2, parent=dl)
    # Pommel dots
    for px, py in [(ax1,ay1),(bx1,by1)]:
        dpg.draw_circle((px, py), 3, color=color, fill=color, parent=dl)


def _draw_layers(dl, cx, cy, size, color):
    """Stacked horizontal bars (Tier List)."""
    w  = size * 0.46
    ys = [-size*0.35, -size*0.12, size*0.12, size*0.35]
    widths = [w, w*0.85, w*0.70, w*0.55]
    for y, bw in zip(ys, widths):
        dpg.draw_rectangle((cx - bw, cy + y - 3), (cx + bw, cy + y + 3),
                           color=color, rounding=2, thickness=1.5, parent=dl)


def _draw_gear(dl, cx, cy, size, color):
    """Simple gear / cog (Settings)."""
    r_inner = size * 0.22
    r_outer = size * 0.38
    teeth   = 8
    pts = []
    for i in range(teeth * 2):
        angle = math.pi * 2 * i / (teeth * 2) - math.pi / 2
        r = r_outer if i % 2 == 0 else r_inner
        pts.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    dpg.draw_polygon(pts, color=color, thickness=1.5, parent=dl)
    dpg.draw_circle((cx, cy), r_inner * 0.55, color=color, thickness=1.5, parent=dl)


def _draw_terminal(dl, cx, cy, size, color):
    """Terminal prompt > _ (Commands)."""
    # >
    dpg.draw_line((cx - size*0.3, cy - size*0.3), (cx - size*0.05, cy),
                  color=color, thickness=2, parent=dl)
    dpg.draw_line((cx - size*0.05, cy), (cx - size*0.3, cy + size*0.3),
                  color=color, thickness=2, parent=dl)
    # _
    dpg.draw_line((cx - size*0.05, cy + size*0.28), (cx + size*0.35, cy + size*0.28),
                  color=color, thickness=2, parent=dl)


def _draw_feed_icon(dl, cx, cy, size, color):
    """Three horizontal lines of decreasing width (Activity Feed)."""
    w1 = size * 0.48
    w2 = size * 0.36
    w3 = size * 0.24
    ys = [cy - size*0.22, cy, cy + size*0.22]
    for y, hw in zip(ys, [w1, w2, w3]):
        dpg.draw_line((cx - hw, y), (cx + hw, y), color=color, thickness=2, parent=dl)


_DRAW_FNS = {
    "_draw_swords":         _draw_swords,
    "_draw_shield":         _draw_shield,
    "_draw_magnifier":      _draw_magnifier,
    "_draw_crossed_swords": _draw_crossed_swords,
    "_draw_layers":         _draw_layers,
    "_draw_gear":           _draw_gear,
    "_draw_terminal":       _draw_terminal,
    "_draw_feed_icon":      _draw_feed_icon,
}

# ---------------------------------------------------------------------------
# Sidebar widget builder
# ---------------------------------------------------------------------------
_sidebar_tag   = "sidebar_child"
_expand_tween  = None
_current_width = [COLLAPSED_W]
_hovered       = [False]
_label_alpha   = [0]    # 0..255 for label fade


def build_sidebar(parent):
    """
    Call once inside the main DPG window to create the sidebar child window.
    """
    with dpg.child_window(
        tag=_sidebar_tag,
        width=COLLAPSED_W,
        parent=parent,
        border=False,
        no_scrollbar=True,
    ):
        dpg.add_drawlist(tag="sidebar_drawlist", width=EXPANDED_W, height=800)

    _redraw_sidebar()


def _redraw_sidebar():
    dl = "sidebar_drawlist"
    if not dpg.does_item_exist(dl):
        return
    dpg.delete_item(dl, children_only=True)

    w   = _current_width[0]
    la  = _label_alpha[0]
    act = state.active_tab

    # Background
    dpg.draw_rectangle((0, 0), (w, 800),
                        color=(0,0,0,0),
                        fill=C["panel"],
                        parent=dl)

    # Right edge rule
    dpg.draw_line((w-1, 0), (w-1, 800),
                  color=C["rule_dark"], thickness=1, parent=dl)

    for i, (tab_id, label, draw_fn_name) in enumerate(TABS):
        item_y   = TOP_PAD + i * ITEM_H
        is_active = (tab_id == act)

        # Active indicator — 2px gold left stripe
        if is_active:
            dpg.draw_rectangle((0, item_y + 4), (3, item_y + ITEM_H - 4),
                               fill=C["gold"], color=(0,0,0,0), parent=dl)
            icon_color = C["gold"]
            bg_color   = (*C["card"][:3], 180)
        else:
            icon_color = C["txt2"]
            bg_color   = (0, 0, 0, 0)

        # Item bg on hover / active
        if is_active or _hovered_tab() == tab_id:
            dpg.draw_rectangle((3, item_y + 2), (w - 2, item_y + ITEM_H - 2),
                               fill=(*C["card"][:3], 120 if is_active else 60),
                               color=(0,0,0,0), rounding=4, parent=dl)

        # Icon centered in collapsed width
        cx = COLLAPSED_W // 2
        cy = item_y + ITEM_H // 2
        draw_fn = _DRAW_FNS.get(draw_fn_name)
        if draw_fn:
            draw_fn(dl, cx, cy, ICON_SIZE, (*icon_color[:3], 255))

        # Label — only when expanded enough
        if la > 10 and w > COLLAPSED_W + 10:
            text_x  = COLLAPSED_W + 10
            text_col = (*C["gold"][:3], la) if is_active else (*C["txt"][:3], la)
            dpg.draw_text((text_x, cy - 10), label,
                          color=text_col, size=16, parent=dl)


def _hovered_tab():
    """Return which tab item the mouse is over, or None."""
    if not dpg.is_item_hovered(_sidebar_tag):
        return None
    mouse = dpg.get_mouse_pos(local=False)
    item_pos = dpg.get_item_rect_min(_sidebar_tag)
    rel_y = mouse[1] - item_pos[1] - TOP_PAD
    idx = int(rel_y // ITEM_H)
    if 0 <= idx < len(TABS):
        return TABS[idx][0]
    return None


def sidebar_tick():
    """
    Call every frame. Handles expand/collapse animation and click detection.
    Returns True if a tab was clicked.
    """
    global _expand_tween

    hovered = dpg.is_item_hovered(_sidebar_tag)

    # Expand on hover
    if hovered and _current_width[0] < EXPANDED_W:
        if _expand_tween is None or _expand_tween.done:
            target = EXPANDED_W
            start  = _current_width[0]
            def _on_w(v):
                _current_width[0] = int(v)
                _label_alpha[0]   = max(0, int((v - COLLAPSED_W - 10) / (EXPANDED_W - COLLAPSED_W - 10) * 255))
                if dpg.does_item_exist(_sidebar_tag):
                    dpg.set_item_width(_sidebar_tag, int(v))
                _redraw_sidebar()
            _expand_tween = anim.tween(start, target, 180, "out_cubic", on_update=_on_w)

    # Collapse when not hovered
    elif not hovered and _current_width[0] > COLLAPSED_W:
        if _expand_tween is None or _expand_tween.done:
            start = _current_width[0]
            def _on_w_col(v):
                _current_width[0] = int(v)
                _label_alpha[0]   = max(0, int((v - COLLAPSED_W - 10) / (EXPANDED_W - COLLAPSED_W - 10) * 255))
                if dpg.does_item_exist(_sidebar_tag):
                    dpg.set_item_width(_sidebar_tag, int(v))
                _redraw_sidebar()
            _expand_tween = anim.tween(start, COLLAPSED_W, 140, "out_cubic", on_update=_on_w_col)

    # Click detection
    clicked = False
    if dpg.is_mouse_button_clicked(0) and hovered:
        ht = _hovered_tab()
        if ht and ht != state.active_tab:
            # Clean up overlay windows from overlay-based tabs before switching
            _cleanup_overlay(state.active_tab)
            state.prev_tab   = state.active_tab
            state.active_tab = ht
            _redraw_sidebar()
            clicked = True

    return clicked
