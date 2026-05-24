"""
The Rift — main entry point.
Phase 0: foundation shell with splash screen overlay.
"""
import sys, os, time, math, threading, random as _random

_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)

import dearpygui.dearpygui as dpg
from PIL import Image
import numpy as np

from theme import C, setup_theme, setup_fonts
from data.tips import TIPS as _TIPS
from core.animations import anim
from core.state import state
from ui.rankings import rankings as rankings_state, draw_rankings, RankRevealPhase
from ui.draft import draw_draft
from ui.scout import draw_scout, scout as scout_state
from ui.inhouse import draw_inhouse, inhouse as inhouse_state
from ui.tierlist import draw_tierlist, register_wheel_handler
from ui.settings import draw_settings, close_settings_window
from ui.commands import draw_commands
from ui.feed import draw_feed
from ui.home import draw_home
from ui import profile as profile_panel
from ui import wrapped as wrapped_overlay
from ui import hotkeys as hotkey_overlay
from ui import audio, effects, toast
from data.reader import live, load_live_data, check_for_update
from data import patch_ticker

__version__ = "4.0.6"   # bump this on each release

WIN_W, WIN_H = 1280, 800
TITLE_H      = 52    # titlebar height
TICKER_H     = 26    # bottom patch-ticker rail height
SIDEBAR_W    = 68    # collapsed sidebar width
SIDEBAR_EXP  = 200   # expanded sidebar width

# ---------------------------------------------------------------------------
# Texture loading — single registry, loaded before windows
# ---------------------------------------------------------------------------
_TEX_REG  = None
_FONTS    = {}

def _load_all_textures():
    global _TEX_REG
    asset_dir = os.path.join(_here, "assets")
    _TEX_REG  = dpg.add_texture_registry()

    noise_path = os.path.join(asset_dir, "noise_tile.png")
    if os.path.exists(noise_path):
        img  = Image.open(noise_path).convert("RGBA")
        w, h = img.size
        flat = (np.array(img, dtype=np.float32) / 255.0).flatten().tolist()
        dpg.add_static_texture(width=w, height=h, default_value=flat,
                               tag="tex_noise", parent=_TEX_REG)

    splash_path = os.path.join(asset_dir, "splash_main.png")
    if os.path.exists(splash_path):
        img  = Image.open(splash_path).convert("RGBA")
        w, h = img.size
        flat = (np.array(img, dtype=np.float32) / 255.0).flatten().tolist()
        dpg.add_static_texture(width=w, height=h, default_value=flat,
                               tag="tex_splash_main", parent=_TEX_REG)


# ---------------------------------------------------------------------------
# Programmatic crown drawing
# ---------------------------------------------------------------------------
def _draw_crown(dl, cx, cy, size, alpha):
    """
    Draw a sharp 5-spike angular crown.
    cx, cy  = center-x and base-top y position in screen coords.
    size    = half-width in pixels (crown total width = 2*size).
    alpha   = 0..255 opacity.
    """
    if alpha <= 0:
        return

    def p(nx, ny):
        return (cx + nx * size, cy + ny * size)

    a   = alpha
    a_s = min(a, 110)   # shadow alpha

    # --- Color palette ---
    col_shadow = (10,  8,   2,  a_s)
    col_base   = (72,  50,  16, a)       # dark base band
    col_body   = (155, 118, 52, a)       # main crown body
    col_mid    = (195, 158, 72, a)       # mid-tone facets
    col_bright = (240, 205, 110, a)      # lit spike faces
    col_tip    = (255, 238, 150, a)      # spike tip highlight
    col_edge   = (65,  45,  14, a)       # outline / dark edge
    col_gem    = (255, 245, 155, a)      # gem fill
    col_gem_in = (255, 255, 200, min(a, 200))  # gem inner

    # --- Outline polygon (5 spikes) ---
    outline = [
        p(-1.00,  0.30),   # base bottom-left
        p(-1.00,  0.00),   # base top-left
        p(-0.84, -0.48),   # far-left spike tip
        p(-0.60, -0.06),   # valley 1
        p(-0.40, -0.74),   # left spike tip
        p(-0.19, -0.13),   # valley 2
        p( 0.00, -1.00),   # CENTER spike tip  ← tallest
        p( 0.19, -0.13),   # valley 3
        p( 0.40, -0.74),   # right spike tip
        p( 0.60, -0.06),   # valley 4
        p( 0.84, -0.48),   # far-right spike tip
        p( 1.00,  0.00),   # base top-right
        p( 1.00,  0.30),   # base bottom-right
    ]

    # 1. Drop shadow
    shadow = [(x+4, y+5) for x,y in outline]
    dpg.draw_polygon(shadow, fill=col_shadow, color=(0,0,0,0), parent=dl)

    # 2. Main body fill
    dpg.draw_polygon(outline, fill=col_body, color=(0,0,0,0), parent=dl)

    # 3. Base band (darker)
    base = [p(-1.0, 0.0), p(1.0, 0.0), p(1.0, 0.30), p(-1.0, 0.30)]
    dpg.draw_polygon(base, fill=col_base, color=(0,0,0,0), parent=dl)

    # 4. Lit left-facing facets on each spike (the face catching "light from above-left")
    spike_data = [
        ((-1.00, 0.00), (-0.84, -0.48), (-0.60, -0.06)),   # far-left spike, right face
        ((-0.60, -0.06), (-0.40, -0.74), (-0.19, -0.13)),  # left spike, right face
        ((-0.19, -0.13), ( 0.00, -1.00), ( 0.19, -0.13)),  # center spike, split
        (( 0.19, -0.13), ( 0.40, -0.74), ( 0.60, -0.06)),  # right spike, left face
        (( 0.60, -0.06), ( 0.84, -0.48), ( 1.00,  0.00)),  # far-right spike, left face
    ]
    for tri in spike_data:
        pts = [p(*v) for v in tri]
        dpg.draw_triangle(pts[0], pts[1], pts[2],
                          fill=col_mid, color=(0,0,0,0), parent=dl)

    # 5. Bright tip highlights (small triangle at each spike point)
    spikes = [(-0.84,-0.48), (-0.40,-0.74), (0.00,-1.00), (0.40,-0.74), (0.84,-0.48)]
    tip_hw = 0.07
    tip_drop = 0.18
    for sx, sy in spikes:
        tip = [p(sx-tip_hw, sy+tip_drop), p(sx, sy), p(sx+tip_hw, sy+tip_drop)]
        dpg.draw_triangle(tip[0], tip[1], tip[2],
                          fill=col_bright, color=(0,0,0,0), parent=dl)
        # Very tip sparkle
        vtip = [p(sx-tip_hw*0.4, sy+tip_drop*0.5), p(sx, sy), p(sx+tip_hw*0.4, sy+tip_drop*0.5)]
        dpg.draw_triangle(vtip[0], vtip[1], vtip[2],
                          fill=col_tip, color=(0,0,0,0), parent=dl)

    # 6. Outline (drawn last so it's on top)
    dpg.draw_polygon(outline, fill=(0,0,0,0), color=col_edge, thickness=1.5, parent=dl)

    # 7. Base band top edge accent line
    dpg.draw_line(p(-1.0, 0.0), p(1.0, 0.0), color=col_edge, thickness=2, parent=dl)

    # 8. Decorative horizontal line mid-band
    dpg.draw_line(p(-0.88, 0.15), p(0.88, 0.15),
                  color=(*col_edge[:3], min(a, 100)), thickness=1, parent=dl)

    # 9. Gems at valley points
    for gx, gy in [(-0.60,-0.06), (-0.19,-0.13), (0.19,-0.13), (0.60,-0.06)]:
        gp = p(gx, gy)
        dpg.draw_circle(gp, 5.5, color=col_edge, fill=col_gem,    parent=dl)
        dpg.draw_circle(gp, 2.8, color=(0,0,0,0), fill=col_gem_in, parent=dl)

    # 10. Corner end-caps on base band
    for ex in [-0.88, 0.88]:
        ep = p(ex, 0.075)
        dpg.draw_rectangle((ep[0]-4, ep[1]-4), (ep[0]+4, ep[1]+4),
                            color=col_edge, fill=col_base, parent=dl)

# ---------------------------------------------------------------------------
# Drag support for borderless window
# ---------------------------------------------------------------------------
_drag_start     = None
_win_pos_start  = None
_is_fullscreen  = [True]   # tracks viewport fullscreen state

def _handle_drag():
    global _drag_start, _win_pos_start
    # No dragging while fullscreen — window can't be repositioned
    if _is_fullscreen[0]:
        _drag_start = None
        return

    mouse  = dpg.get_mouse_pos(local=False)
    vp_pos = dpg.get_viewport_pos()
    rel    = (mouse[0] - vp_pos[0], mouse[1] - vp_pos[1])
    vw     = dpg.get_viewport_width()

    if dpg.is_mouse_button_down(0):
        # Exclude close + fullscreen button areas so clicks don't start a drag
        in_buttons = rel[0] >= vw - TITLE_H * 2 and 8 <= rel[1] <= TITLE_H - 8
        if rel[1] < TITLE_H and _drag_start is None and not in_buttons:
            _drag_start    = mouse
            _win_pos_start = list(vp_pos)
    else:
        _drag_start = None

    if _drag_start and _win_pos_start:
        dx = mouse[0] - _drag_start[0]
        dy = mouse[1] - _drag_start[1]
        dpg.set_viewport_pos([_win_pos_start[0]+dx, _win_pos_start[1]+dy])

# ---------------------------------------------------------------------------
# Title bar
# ---------------------------------------------------------------------------
def _draw_titlebar(dl, w):
    h = TITLE_H
    dpg.delete_item(dl, children_only=True)
    dpg.draw_rectangle((0,0),(w,h), fill=C["panel"], color=(0,0,0,0), parent=dl)
    dpg.draw_line((0,h-1),(w,h-1), color=C["rule_dark"], thickness=1, parent=dl)
    t = dpg.draw_text((18, h//2-14), "THE RIFT", color=C["rift_purple"], size=29, parent=dl)
    if "cinzel_28" in _FONTS:
        dpg.bind_item_font(t, _FONTS["cinzel_28"])

    m  = 8
    cy = h // 2
    # Mouse in titlebar-local coords, for window-button hover feedback.
    mouse  = dpg.get_mouse_pos(local=False)
    vp     = dpg.get_viewport_pos()
    rx, ry = mouse[0] - vp[0], mouse[1] - vp[1]

    # Close button — gentle red wash on hover.
    cl_x1, cl_x2 = w - h + m, w - m
    cl_hov = (cl_x1 <= rx <= cl_x2 and m <= ry <= h - m)
    cl_amt = effects.hover_amt("tb_close", cl_hov)
    if cl_amt > 0.01:
        dpg.draw_rectangle((cl_x1, m), (cl_x2, h - m),
                           fill=(200, 70, 70, int(cl_amt * 150)),
                           color=(0, 0, 0, 0), rounding=4, parent=dl)
    dpg.draw_rectangle((cl_x1, m), (cl_x2, h - m),
                       fill=(0,0,0,0), color=C["rule_dark"], rounding=4, parent=dl)
    ccx    = w - h // 2
    cl_col = C["gold_lt"] if cl_hov else C["txt2"]
    dpg.draw_line((ccx-9, cy-9),(ccx+9, cy+9), color=cl_col, thickness=2, parent=dl)
    dpg.draw_line((ccx+9, cy-9),(ccx-9, cy+9), color=cl_col, thickness=2, parent=dl)

    # Fullscreen button — gold wash on hover.
    fx1, fx2 = w - h*2 + m, w - h*2 + m + (h - m*2)
    fs_hov = (fx1 <= rx <= fx2 and m <= ry <= h - m)
    fs_amt = effects.hover_amt("tb_fs", fs_hov)
    if fs_amt > 0.01:
        dpg.draw_rectangle((fx1, m), (fx2, h - m),
                           fill=(*C["gold"][:3], int(fs_amt * 60)),
                           color=(0, 0, 0, 0), rounding=4, parent=dl)
    dpg.draw_rectangle((fx1, m), (fx2, h - m),
                       fill=(0,0,0,0), color=C["rule_dark"], rounding=4, parent=dl)
    fcx    = fx1 + (h - m*2) // 2
    fs_col = C["gold_lt"] if fs_hov else C["txt2"]
    dpg.draw_rectangle((fcx-9, cy-9),(fcx+9, cy+9),
                        fill=(0,0,0,0), color=fs_col, thickness=1.5, parent=dl)

# ---------------------------------------------------------------------------
# Splash state machine
# ---------------------------------------------------------------------------
class SplashPhase:
    IDLE, CROWN_IN, TITLE_TYPE, RULE_DRAW, PULSE, LOADING, FADE_OUT, DONE = range(8)

class Splash:
    TITLE    = "THE RIFT"
    SUBTITLE = "Inhouse Analytics"

    def __init__(self):
        self.phase        = SplashPhase.IDLE
        self.crown_alpha  = 0.0
        self.title_chars  = 0
        self.rule_frac    = 0.0
        self.fact_y_off   = 60.0
        self.fact_alpha   = 0.0
        self.pulse_t      = 0.0
        self.fade_alpha   = 255.0
        self.fun_fact     = _random.choice(_TIPS)
        self.loading_done = False

    def start(self):
        self.phase = SplashPhase.CROWN_IN
        anim.tween(0, 255, 500, "out_cubic",
                   on_update=lambda v: setattr(self, "crown_alpha", v),
                   on_done=self._after_crown)

    def _after_crown(self):
        self.phase = SplashPhase.TITLE_TYPE
        n     = len(self.TITLE)
        dur   = n * 55            # ~55ms per character
        anim.tween(0, n, dur, "linear",
                   on_update=lambda v: setattr(self, "title_chars", int(v)),
                   on_done=self._after_title)

    def _after_title(self):
        self.phase = SplashPhase.RULE_DRAW
        anim.tween(0, 1, 300, "out_cubic",
                   on_update=lambda v: setattr(self, "rule_frac", v),
                   on_done=self._after_rule)

    def _after_rule(self):
        self.phase = SplashPhase.PULSE
        anim.tween(60, 0, 380, "out_cubic", delay_ms=150,
                   on_update=lambda v: setattr(self, "fact_y_off", v))
        anim.tween(0, 255, 380, "out_cubic", delay_ms=150,
                   on_update=lambda v: setattr(self, "fact_alpha", v),
                   on_done=self._after_fact)

    def _after_fact(self):
        self.phase = SplashPhase.LOADING

    def tick(self):
        self.pulse_t += 0.035

    def finish(self):
        if self.phase in (SplashPhase.LOADING, SplashPhase.PULSE):
            self.phase = SplashPhase.FADE_OUT
            anim.tween(255, 0, 500, "in_out",
                       on_update=lambda v: setattr(self, "fade_alpha", v),
                       on_done=lambda: setattr(state, "splash_done", True))


def _draw_splash(dl, sp: Splash, vw, vh):
    dpg.delete_item(dl, children_only=True)

    fa  = int(sp.fade_alpha)
    cx  = vw // 2

    # Image-anchored layout: caricature is the hero, title + subtitle cascade below.
    _IMG_W, _IMG_H = 960, 640
    img_x = cx - _IMG_W // 2
    img_y = max(15, (vh - _IMG_H - 140) // 2)
    cy    = img_y + _IMG_H + 15   # title sits just below the image; other rows offset

    # Full background
    dpg.draw_rectangle((0,0),(vw,vh),
                        fill=(*C["bg"][:3], fa),
                        color=(0,0,0,0), parent=dl)

    # --- Splash caricature (replaces vector crown) ---
    pulse  = (math.sin(sp.pulse_t) + 1) / 2
    ca     = int(sp.crown_alpha * fa / 255)

    if ca > 10 and dpg.does_item_exist("tex_splash_main"):
        # Soft gold glow halo behind the image
        glow_a = int(pulse * 70 * fa / 255)
        halo_cx, halo_cy = cx, img_y + _IMG_H // 2
        for r, ga in [(200, glow_a//3), (150, glow_a//2), (105, glow_a)]:
            dpg.draw_circle((halo_cx, halo_cy), r, color=(0,0,0,0),
                            fill=(*C["gold_dk"][:3], ga), parent=dl)
        dpg.draw_image("tex_splash_main",
                       (img_x, img_y), (img_x + _IMG_W, img_y + _IMG_H),
                       color=(255, 255, 255, ca), parent=dl)
        # Gold border
        dpg.draw_rectangle((img_x - 2, img_y - 2),
                           (img_x + _IMG_W + 2, img_y + _IMG_H + 2),
                           color=(*C["gold"][:3], ca),
                           fill=(0, 0, 0, 0), thickness=2, parent=dl)
    elif ca > 10:
        # Fallback to vector crown if texture failed to load
        glow_a = int(pulse * 55 * fa / 255)
        crown_cx = cx
        crown_cy = cy - 42
        crown_sz = 108
        for r, ga in [(90, glow_a//3), (65, glow_a//2), (45, glow_a)]:
            dpg.draw_circle((crown_cx, crown_cy - crown_sz*0.35),
                            r, color=(0,0,0,0),
                            fill=(*C["gold_dk"][:3], ga), parent=dl)
        _draw_crown(dl, crown_cx, crown_cy, crown_sz, ca)

    # --- Title typewriter ---
    # Anchor tx from the full title width so text stays centered as chars reveal
    shown = sp.TITLE[:sp.title_chars]
    if shown:
        ta    = int(sp.crown_alpha * fa / 255)
        tx    = cx - _TITLE_W // 2 + 40
        # Shadow
        dpg.draw_text((tx+2, cy+10), shown,
                      color=(*C["bg"][:3], ta//2), size=52, parent=dl)
        # Main purple Cinzel
        t_tag = dpg.draw_text((tx, cy+8), shown,
                              color=(*C["rift_purple"][:3], ta), size=52, parent=dl)
        if "cinzel_52" in _FONTS:
            dpg.bind_item_font(t_tag, _FONTS["cinzel_52"])

    # --- Gold rule ---
    if sp.rule_frac > 0:
        half = int(70 * sp.rule_frac)
        ry   = cy + 70
        ra   = int(fa * 0.8)
        dpg.draw_line((cx-half, ry), (cx+half, ry),
                      color=(*C["gold"][:3], ra), thickness=1, parent=dl)

    # --- Subtitle ---
    if sp.rule_frac > 0.5:
        sa    = int((sp.rule_frac - 0.5) * 2 * 160 * fa / 255)
        sub   = sp.SUBTITLE
        sw    = len(sub) * 8
        s_tag = dpg.draw_text((cx - sw//2, cy + 78), sub,
                              color=(*C["txt2"][:3], sa), size=15, parent=dl)
        if "raj_sb_14" in _FONTS:
            dpg.bind_item_font(s_tag, _FONTS["raj_sb_14"])

    # --- Fun fact card ---
    if sp.fact_alpha > 0:
        crd_w, crd_h = 440, 72
        crd_x = cx - crd_w // 2
        # Sits just below subtitle, but clamps to stay above the loading bar
        crd_y = int(min(cy + 100 + sp.fact_y_off, vh - crd_h - 30))
        fa2   = int(sp.fact_alpha * fa / 255)

        dpg.draw_rectangle((crd_x, crd_y), (crd_x+crd_w, crd_y+crd_h),
                           fill=(*C["panel"][:3], fa2),
                           color=(*C["rule_gold"][:3], fa2),
                           rounding=4, parent=dl)
        lbl = dpg.draw_text((crd_x+14, crd_y+10), "DID YOU KNOW",
                            color=(*C["gold_dk"][:3], fa2), size=15, parent=dl)
        if "raj_sb_14" in _FONTS: dpg.bind_item_font(lbl, _FONTS["raj_sb_14"])
        lines = _wrap(sp.fun_fact, 48)
        for i, line in enumerate(lines[:3]):
            ft = dpg.draw_text((crd_x+14, crd_y+30+i*20), line,
                               color=(*C["txt2"][:3], fa2), size=17, parent=dl)
            if "raj_r_16" in _FONTS: dpg.bind_item_font(ft, _FONTS["raj_r_16"])

    # --- Loading bar ---
    if sp.phase in (SplashPhase.LOADING, SplashPhase.FADE_OUT):
        t    = (time.monotonic() % 1.8) / 1.8
        fill = int(200 * t)
        bar_y = vh - 20
        dpg.draw_rectangle((cx-100, bar_y),(cx+100, bar_y+4),
                           fill=(0,0,0,0), color=(*C["rule_dark"][:3], fa),
                           rounding=2, parent=dl)
        if fill > 0:
            dpg.draw_rectangle((cx-100, bar_y),(cx-100+fill, bar_y+4),
                               fill=(*C["gold_dk"][:3], fa),
                               color=(0,0,0,0), rounding=2, parent=dl)


def _wrap(text, w):
    words, lines, cur = text.split(), [], ""
    for word in words:
        if len(cur)+len(word)+1 <= w:
            cur = (cur+" "+word).strip()
        else:
            if cur: lines.append(cur)
            cur = word
    if cur: lines.append(cur)
    return lines

# ---------------------------------------------------------------------------
# Sidebar — hover to expand
# ---------------------------------------------------------------------------
_sb_w          = [SIDEBAR_W]   # current animated width
_sb_tween      = [None]
_sb_last_w     = [SIDEBAR_W]   # detect width changes for content resize
_sb_ind_y      = [None]        # current y of sliding active-tab indicator
_sb_ind_target = [None]        # target y based on active tab

def _sidebar_tick(vw, vh):
    """Animate expand/collapse; returns True if a tab was clicked."""
    from ui.sidebar import TABS, ICON_SIZE, ITEM_H, TOP_PAD, _DRAW_FNS, COLLAPSED_W, _OVERLAY_TAGS

    # Hover detection — mouse over the sidebar column
    mouse = dpg.get_mouse_pos(local=False)
    vp    = dpg.get_viewport_pos()
    rx    = mouse[0] - vp[0]
    ry    = mouse[1] - vp[1]
    in_sb = (0 <= rx < _sb_w[0]) and (TITLE_H <= ry < vh)

    if in_sb and _sb_w[0] < SIDEBAR_EXP:
        if _sb_tween[0] is None or _sb_tween[0].done:
            start = _sb_w[0]
            def _on_exp(v):
                _sb_w[0] = int(v)
            _sb_tween[0] = anim.tween(start, SIDEBAR_EXP, 180, "out_cubic", on_update=_on_exp)
    elif not in_sb and _sb_w[0] > COLLAPSED_W:
        if _sb_tween[0] is None or _sb_tween[0].done:
            start = _sb_w[0]
            def _on_col(v):
                _sb_w[0] = int(v)
            _sb_tween[0] = anim.tween(start, COLLAPSED_W, 140, "out_cubic", on_update=_on_col)

    # Resize sidebar_win + content_win if width changed
    sw = _sb_w[0]
    if sw != _sb_last_w[0]:
        content_h = vh - TITLE_H
        dpg.configure_item("sidebar_win", width=sw)
        dpg.configure_item("sidebar_dl",  width=sw)
        dpg.configure_item("content_win", width=vw - sw)
        dpg.configure_item("content_dl",  width=vw - sw)
        _sb_last_w[0] = sw

    # Redraw sidebar
    dl = "sidebar_dl"
    dpg.delete_item(dl, children_only=True)

    label_alpha = max(0, int((sw - COLLAPSED_W - 8) / (SIDEBAR_EXP - COLLAPSED_W - 8) * 255))
    h = vh - TITLE_H

    dpg.draw_rectangle((0,0),(sw,h), fill=C["panel"], color=(0,0,0,0), parent=dl)
    dpg.draw_line((sw-1,0),(sw-1,h), color=C["rule_dark"], thickness=1, parent=dl)

    # Hovered tab index. `ry` is already viewport-local (mouse[1] - vp[1]),
    # so do NOT subtract vp[1] again — that bug made bottom tabs unreachable
    # whenever the window wasn't fullscreen.
    hov_idx = -1
    if in_sb:
        idx = int((ry - TITLE_H - TOP_PAD) // ITEM_H)
        if 0 <= idx < len(TABS):
            hov_idx = idx

    # Smooth the active-tab indicator toward its target (ease-out lerp)
    active_idx = next((i for i, t in enumerate(TABS) if t[0] == state.active_tab), 0)
    target_y = TOP_PAD + active_idx * ITEM_H
    if _sb_ind_y[0] is None:
        _sb_ind_y[0] = float(target_y)
    _sb_ind_target[0] = float(target_y)
    delta = _sb_ind_target[0] - _sb_ind_y[0]
    if abs(delta) > 0.4:
        _sb_ind_y[0] += delta * 0.22

    try:
        from ui.effects import breathing_alpha
        pulse_alpha = breathing_alpha(255, period=2.6, amp=0.30)
        icon_alpha  = breathing_alpha(255, period=2.6, amp=0.22)
    except Exception:
        pulse_alpha = 255
        icon_alpha  = 255

    for i, (tab_id, label, draw_fn_name) in enumerate(TABS):
        iy        = TOP_PAD + i * ITEM_H
        is_active = (tab_id == state.active_tab)
        is_hov    = (i == hov_idx)
        icon_col  = C["gold"] if is_active else (C["txt"] if is_hov else C["txt2"])

        if is_active or is_hov:
            bg_a = 160 if is_active else 70
            dpg.draw_rectangle((3, iy+2),(sw-2, iy+ITEM_H-2),
                               fill=(*C["card"][:3], bg_a), color=(0,0,0,0),
                               rounding=4, parent=dl)

        fn = _DRAW_FNS.get(draw_fn_name)
        if fn:
            if is_active:
                fn(dl, COLLAPSED_W//2, iy+ITEM_H//2, ICON_SIZE,
                   (*icon_col[:3], icon_alpha))
            else:
                fn(dl, COLLAPSED_W//2, iy+ITEM_H//2, ICON_SIZE,
                   (*icon_col[:3], 255))

        # Labels — fade in as sidebar expands
        if label_alpha > 0:
            text_x   = COLLAPSED_W + 10
            text_col = (*C["gold"][:3], label_alpha) if is_active else \
                       (*C["txt"][:3],  label_alpha)
            dpg.draw_text((text_x, iy + ITEM_H//2 - 9), label,
                          color=text_col, size=17, parent=dl)

    # Sliding gold indicator — drawn last (sits on top of icon row backgrounds)
    ind_y = int(_sb_ind_y[0])
    dpg.draw_rectangle((0, ind_y + 4), (3, ind_y + ITEM_H - 4),
                        fill=(*C["gold"][:3], pulse_alpha),
                        color=(0, 0, 0, 0), parent=dl)
    # Soft glow extension to the right of the stripe
    dpg.draw_rectangle((3, ind_y + 4), (8, ind_y + ITEM_H - 4),
                        fill=(*C["gold"][:3], int(pulse_alpha * 0.30)),
                        color=(0, 0, 0, 0), parent=dl)

    # Click handling
    clicked = False
    if dpg.is_mouse_button_clicked(0) and in_sb:
        idx = int((ry - TITLE_H - TOP_PAD) // ITEM_H)
        if 0 <= idx < len(TABS):
            new_tab = TABS[idx][0]
            if new_tab != state.active_tab:
                # clean up overlay windows
                old_tag = _OVERLAY_TAGS.get(state.active_tab)
                if old_tag and dpg.does_item_exist(old_tag):
                    dpg.delete_item(old_tag)
                state.active_tab = new_tab
                if dpg.does_item_exist("content_win"):
                    dpg.set_y_scroll("content_win", 0)
                clicked = True

    return clicked

# ---------------------------------------------------------------------------
# Bottom patch-ticker rail
# ---------------------------------------------------------------------------
_TICKER_PX_PER_SEC = 60   # marquee scroll speed

def _draw_ticker(dl, vw):
    """Bottom marquee — scrolling patch / free-rotation / flavor strings."""
    if not dpg.does_item_exist(dl):
        return
    dpg.delete_item(dl, children_only=True)

    # Background bar
    dpg.draw_rectangle((0, 0), (vw, TICKER_H),
                       fill=(*C["panel"][:3], 255),
                       color=(0, 0, 0, 0), parent=dl)
    dpg.draw_line((0, 0), (vw, 0), color=C["rule_dark"],
                  thickness=1, parent=dl)
    # Left "PATCH" pill
    patch = patch_ticker.get_patch_version()
    pill_label = f"PATCH {patch}" if patch else "THE RIFT"
    pill_w = 8 + len(pill_label) * 8
    dpg.draw_rectangle((0, 0), (pill_w + 12, TICKER_H),
                       fill=(*C["gold_dk"][:3], 240),
                       color=(0, 0, 0, 0), parent=dl)
    t = dpg.draw_text((8, 6), pill_label,
                      color=(*C["gold_lt"][:3], 255), size=14, parent=dl)
    if "raj_sb_14" in _FONTS:
        dpg.bind_item_font(t, _FONTS["raj_sb_14"])

    # Marquee content
    items = patch_ticker.get_ticker_items()
    if not items:
        return
    sep   = "    ◆    "
    text  = sep.join(items) + sep
    # repeat enough times that the scrolling window always has content
    full  = (text + text + text)
    char_w = 8
    full_px = len(full) * char_w
    track_start = pill_w + 24

    elapsed = time.monotonic() * _TICKER_PX_PER_SEC
    offset  = int(elapsed) % max(1, len(text) * char_w)
    x_draw  = track_start - offset

    # Clip mask via a clip rectangle would be ideal — DPG draw_text doesn't
    # auto-clip, so we just draw the long string starting at x_draw. Anything
    # to the left of pill draws over the pill briefly when it wraps; cover by
    # redrawing the pill on top below.
    txt_id = dpg.draw_text((x_draw, 6), full,
                           color=(*C["txt"][:3], 220),
                           size=14, parent=dl)
    if "raj_sb_14" in _FONTS:
        dpg.bind_item_font(txt_id, _FONTS["raj_sb_14"])

    # Re-paint pill on top so the marquee appears to slide out from behind it
    dpg.draw_rectangle((0, 0), (pill_w + 12, TICKER_H),
                       fill=(*C["gold_dk"][:3], 255),
                       color=(0, 0, 0, 0), parent=dl)
    t2 = dpg.draw_text((8, 6), pill_label,
                       color=(*C["gold_lt"][:3], 255), size=14, parent=dl)
    if "raj_sb_14" in _FONTS:
        dpg.bind_item_font(t2, _FONTS["raj_sb_14"])
    dpg.draw_line((pill_w + 12, 0), (pill_w + 12, TICKER_H),
                  color=(*C["gold"][:3], 200), thickness=1, parent=dl)


# ---------------------------------------------------------------------------
# Content routing
# ---------------------------------------------------------------------------
def _draw_content(dl, w, h):
    if state.active_tab == "home":
        draw_home(dl, w, h, _FONTS)
    elif state.active_tab == "rankings":
        draw_rankings(dl, w, h, _FONTS)
    elif state.active_tab == "draft":
        draw_draft(dl, w, h, _FONTS)
    elif state.active_tab == "scout":
        draw_scout(dl, w, h, _FONTS)
    elif state.active_tab == "inhouse":
        draw_inhouse(dl, w, h, _FONTS)
    elif state.active_tab == "tierlist":
        draw_tierlist(dl, w, h, _FONTS)
    elif state.active_tab == "settings":
        draw_settings(dl, w, h, _FONTS)
    elif state.active_tab == "commands":
        draw_commands(dl, w, h, _FONTS)
    elif state.active_tab == "feed":
        draw_feed(dl, w, h, _FONTS)
    else:
        dpg.delete_item(dl, children_only=True)
        dpg.draw_rectangle((0,0),(w,h), fill=C["bg"], color=(0,0,0,0), parent=dl)

# ---------------------------------------------------------------------------
# Tab-change transition — a soft fade-in veil over the content area so tabs
# never hard-cut. Scales with anim.intensity (instant when motion is off).
# ---------------------------------------------------------------------------
_tab_xfade    = {"last": None, "t0": 0.0}
_TAB_XFADE_MS = 190

def _draw_tab_transition(dl, w, h):
    cur = state.active_tab
    if _tab_xfade["last"] != cur:
        if _tab_xfade["last"] is not None:
            try:
                audio.play_tab()
            except Exception:
                pass
        _tab_xfade["last"] = cur
        _tab_xfade["t0"]   = time.monotonic()
    if anim.intensity <= 0.01:
        return
    elapsed = (time.monotonic() - _tab_xfade["t0"]) * 1000.0
    if elapsed >= _TAB_XFADE_MS:
        return
    a = int(205 * (1.0 - elapsed / _TAB_XFADE_MS))
    if a <= 2:
        return
    dpg.draw_rectangle((0, 0), (w, h),
                       fill=(*C["bg"][:3], a), color=(0, 0, 0, 0),
                       parent=dl)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
_TITLE_W = 270   # measured after fonts load

def main():
    global _FONTS, _TITLE_W

    dpg.create_context()
    _load_all_textures()
    setup_theme()
    _FONTS = setup_fonts()
    # Phase 5 — bring the pygame.mixer cue wrapper up and gate it on the
    # saved audio_enabled flag. Init is best-effort; no audio device or
    # missing files don't break startup.
    try:
        from data.config import load_config as _load_cfg
        _cfg0 = _load_cfg()
        audio.set_enabled(bool(_cfg0.get("audio_enabled", True)))
        audio.set_volume(float(_cfg0.get("audio_volume", 1.0)))
        anim.set_intensity(float(_cfg0.get("anim_intensity", 1.0)))
    except Exception:
        pass
    # Bind Rajdhani as the application-default font so ALL widgets — including
    # add_text/add_button/add_input_text calls that never had an explicit
    # bind_item_font — render in our theme typeface instead of DPG's pixelated
    # ProggyClean bitmap default. This is what was showing in the scout report
    # panel and other places.
    for _default_key in ("raj_r_18", "raj_r_16", "raj_16"):
        if _default_key in _FONTS:
            dpg.bind_font(_FONTS[_default_key])
            break
    register_wheel_handler()

    # Measure actual rendered width of splash title so centering is exact
    if "cinzel_52" in _FONTS:
        try:
            sz = dpg.get_text_size("THE RIFT", font=_FONTS["cinzel_52"])
            if sz and sz[0] > 0:
                _TITLE_W = int(sz[0])
        except Exception:
            pass

    dpg.create_viewport(
        title     = "The Rift",
        width     = WIN_W,
        height    = WIN_H,
        decorated = False,
        resizable = False,   # prevents Windows resize border artifact
    )
    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.toggle_viewport_fullscreen()   # start fullscreen by default

    # Per-window theme: kill ItemSpacing inside root so the titlebar/sidebar/
    # content drawlists butt up against each other with no panel-bg gap
    # showing through (the "black bar" bug).
    with dpg.theme() as _root_zero_spacing:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing,    0.0, 0.0)
            dpg.add_theme_style(dpg.mvStyleVar_WindowPadding,  0.0, 0.0)
            dpg.add_theme_style(dpg.mvStyleVar_ChildBorderSize, 0.0)
            dpg.add_theme_style(dpg.mvStyleVar_ChildRounding,  0.0)

    # --- Root window ---
    with dpg.window(tag="root", no_title_bar=True, no_resize=True,
                    no_move=True, no_scrollbar=True):
        with dpg.drawlist(tag="titlebar_dl", width=WIN_W, height=TITLE_H):
            pass
        _mid_h = WIN_H - TITLE_H - TICKER_H
        with dpg.group(horizontal=True):
            with dpg.child_window(tag="sidebar_win", width=SIDEBAR_W, height=_mid_h,
                                  border=False, no_scrollbar=True, no_scroll_with_mouse=True):
                with dpg.drawlist(tag="sidebar_dl", width=SIDEBAR_W, height=_mid_h):
                    pass
            # `no_scroll_with_mouse=True` — every tab manages its own scroll
            # via _wheel_delta_shared (registered by ui.tierlist). The native
            # content_win scroll was causing a 1-frame visual glitch on the
            # Draft Board (wheel shifts the window, then set_y_scroll(0) snaps
            # it back). Disabling native scroll removes the glitch entirely.
            with dpg.child_window(tag="content_win", width=WIN_W-SIDEBAR_W, height=_mid_h,
                                  border=False, no_scrollbar=True, no_scroll_with_mouse=True):
                with dpg.drawlist(tag="content_dl", width=WIN_W-SIDEBAR_W, height=3000):
                    pass
        # Patch-ticker rail at the very bottom of the window
        with dpg.drawlist(tag="ticker_dl", width=WIN_W, height=TICKER_H):
            pass

    # --- Splash overlay window (on top of root) ---
    with dpg.window(tag="splash_win", no_title_bar=True, no_resize=True,
                    no_move=True, no_scrollbar=True, no_scroll_with_mouse=True,
                    pos=(0, 0), width=WIN_W, height=WIN_H,
                    no_bring_to_front_on_focus=False):
        with dpg.drawlist(tag="splash_dl", width=WIN_W, height=WIN_H):
            pass

    dpg.bind_item_theme("root", _root_zero_spacing)
    dpg.set_primary_window("root", True)
    dpg.focus_item("splash_win")

    # Start splash
    splash = Splash()
    splash.start()

    # Fallback demo rankings if Sheets data not available
    _DEMO_RANKS_FALLBACK = [
        {"name": "Phantom",  "score": 95, "tier": "Challenger"},
        {"name": "Ironclad", "score": 88, "tier": "Grandmaster"},
        {"name": "Vex",      "score": 82, "tier": "Master"},
        {"name": "Shroud",   "score": 74, "tier": "Diamond"},
        {"name": "Blaze",    "score": 66, "tier": "Diamond"},
        {"name": "Kira",     "score": 58, "tier": "Emerald"},
        {"name": "Dusk",     "score": 52, "tier": "Emerald"},
        {"name": "Nox",      "score": 46, "tier": "Platinum"},
        {"name": "Cinder",   "score": 40, "tier": "Platinum"},
        {"name": "Riven",    "score": 36, "tier": "Gold"},
    ]

    # First-run welcome — surface the new Home tab and ? hotkey overlay once.
    try:
        from data.config import load_config as _lc, save_config as _sc
        _cfg = _lc()
        if not _cfg.get("welcomed_v40"):
            def _show_welcome():
                toast.push(
                    "Welcome to v4 — new HOME tab, player profiles, seasons & Wrapped. "
                    "Press ? anytime for keyboard shortcuts.",
                    kind="info", title="What's new", duration=11.0)
                _cfg["welcomed_v40"] = True
                _sc(_cfg)
            anim.tween(0, 1, 1, "linear", delay_ms=1600, on_done=_show_welcome)
    except Exception:
        pass

    # One-time sheet → DB backfill. The Fly DB is empty on first launch even
    # when the user has years of `_InhouseGameLog` in their sheet. Push them
    # all through `/api/matches` so the new Home / Profile / Inhouse history
    # surfaces have something to show. Idempotent server-side (INSERT OR REPLACE
    # on match id), gated by a config flag so it never re-runs.
    try:
        from data.config import load_config as _lc2, save_config as _sc2
        _cfg2 = _lc2()
        if not _cfg2.get("backfilled_from_sheet"):
            from data import sheet_mirror as _sm
            def _on_backfill_done(counts):
                _cfg2["backfilled_from_sheet"] = True
                _sc2(_cfg2)
                ing = int(counts.get("ingested", 0))
                if ing > 0:
                    toast.push(f"Imported {ing} historical games from the sheet.",
                               kind="success", title="Backfill complete",
                               duration=8.0)
                # Invalidate caches that loaded BEFORE backfill ran so the
                # new matches show up without a relaunch.
                try:
                    from data.reader import live as _live, load_match_history, load_records
                    _live.match_history = []
                    _live.match_history_loaded = False
                    _live.match_history_error = None
                    _live.records = {}
                    _live.records_loaded = False
                    load_match_history()
                    load_records()
                    # Reset home's per-tab lazy-load gates so it re-pulls too.
                    try:
                        from ui.home import _invalidate as _home_invalidate
                        _home_invalidate()
                    except Exception:
                        pass
                except Exception:
                    pass
            def _on_backfill_progress(msg):
                pass  # silent — toast on done only
            def _on_backfill_error(msg):
                # Don't set the flag — let the next launch try again.
                print(f"[backfill] {msg}")
            # Give the splash + first-paint plenty of time before pounding
            # the API.
            def _kick():
                _sm.backfill_from_sheets(on_progress=_on_backfill_progress,
                                          on_done=_on_backfill_done,
                                          on_error=_on_backfill_error)
            anim.tween(0, 1, 1, "linear", delay_ms=4000, on_done=_kick)
    except Exception as _e:
        print(f"[backfill] init failed: {_e}")

    # Live data load — reads Rank Data + Player Stats + InhouseGameLog from Sheets
    def _on_live_data_ready():
        splash.loading_done = True
        # Auto-sync avatars on every launch so all clients stay up-to-date
        from data.reader import download_all_avatars
        from ui.inhouse import queue_avatars_reload_all
        download_all_avatars(on_done=queue_avatars_reload_all, on_error=lambda _: None)

    def _on_live_data_error(msg):
        print(f"[live data] {msg}")
        splash.loading_done = True   # unblock splash even on error; tabs fall back to demo

    load_live_data(on_done=_on_live_data_ready, on_error=_on_live_data_error)

    # ── Auto-update check (background, non-blocking) ───────────────────────
    # IMPORTANT: DPG is NOT thread-safe. The background callback only writes to
    # this list; the main render loop reads it and creates DPG items on the main thread.
    _pending_update = [None]   # [None] or [(latest_tag, download_url)]

    def _on_update_result(latest_tag, download_url):
        if latest_tag:
            _pending_update[0] = (latest_tag, download_url)

    check_for_update(__version__, on_done=_on_update_result)

    # Kick off live patch/rotation ticker refresh in the background.
    patch_ticker.start_background_refresh()

    _rankings_triggered   = [False]
    _scout_populated      = [False]
    _inhouse_populated    = [False]
    _last_vp_size       = [0, 0]   # tracks resize
    _f11_was_down       = [False]  # edge-detect for F11
    _key_was_down       = {}       # edge-detect for tab-switch hotkeys

    # Sidebar TABS list, hoisted so hotkeys can index into it.
    from ui.sidebar import TABS as _TABS, _OVERLAY_TAGS as _OVL
    _TAB_HOTKEYS = [
        (dpg.mvKey_1, 0), (dpg.mvKey_2, 1), (dpg.mvKey_3, 2), (dpg.mvKey_4, 3),
        (dpg.mvKey_5, 4), (dpg.mvKey_6, 5), (dpg.mvKey_7, 6), (dpg.mvKey_8, 7),
        (dpg.mvKey_9, 8),
    ]

    while dpg.is_dearpygui_running():
        anim.tick()
        splash.tick()

        vw = dpg.get_viewport_width()
        vh = dpg.get_viewport_height()

        # F11 fullscreen toggle (edge-detect so one press = one toggle)
        f11_down = dpg.is_key_down(dpg.mvKey_F11)
        if f11_down and not _f11_was_down[0]:
            dpg.toggle_viewport_fullscreen()
            _is_fullscreen[0] = not _is_fullscreen[0]
        _f11_was_down[0] = f11_down

        # Per-frame input gates reset (Phase 6): overlays cooperate so a
        # single click doesn't fire on both the overlay and the tab beneath,
        # and Esc only closes the topmost open thing.
        state.click_consumed = False
        state.esc_consumed   = False
        esc_down = dpg.is_key_down(dpg.mvKey_Escape)
        state.esc_pressed = bool(esc_down and not _key_was_down.get(dpg.mvKey_Escape, False))

        # ── Keyboard hotkeys: 1-9 switch tabs, Esc closes active overlay ─────
        # Suppress while splash is up so the user can't tab away mid-intro.
        if state.splash_done:
            for key, tab_idx in _TAB_HOTKEYS:
                down = dpg.is_key_down(key)
                if down and not _key_was_down.get(key, False) and tab_idx < len(_TABS):
                    new_tab = _TABS[tab_idx][0]
                    if new_tab != state.active_tab:
                        old_tag = _OVL.get(state.active_tab)
                        if old_tag and dpg.does_item_exist(old_tag):
                            dpg.delete_item(old_tag)
                        state.active_tab = new_tab
                        if dpg.does_item_exist("content_win"):
                            dpg.set_y_scroll("content_win", 0)
                _key_was_down[key] = down

            # Esc: close overlays in priority order (topmost first) then fall
            # back to the legacy tab-overlay cleanup. Overlays inspect
            # `state.esc_pressed` (edge-detected single-frame True) and call
            # `state.esc_consumed = True` if they handle it.
            if state.esc_pressed:
                # Try overlays from topmost down to keep behavior intuitive:
                # hotkeys > wrapped > profile > tab overlay
                if hotkey_overlay.is_open():
                    hotkey_overlay.close()
                    state.esc_consumed = True
                elif wrapped_overlay.is_open():
                    wrapped_overlay.close()
                    state.esc_consumed = True
                elif profile_panel.is_open():
                    profile_panel.close()
                    state.esc_consumed = True
                else:
                    cur_tag = _OVL.get(state.active_tab)
                    if cur_tag and dpg.does_item_exist(cur_tag):
                        dpg.delete_item(cur_tag)
                        state.esc_consumed = True
            _key_was_down[dpg.mvKey_Escape] = esc_down

        # Resize: update all containers when viewport dimensions change
        if vw != _last_vp_size[0] or vh != _last_vp_size[1]:
            _last_vp_size[0], _last_vp_size[1] = vw, vh
            sw        = _sb_w[0]
            content_w = vw - sw
            content_h = vh - TITLE_H - TICKER_H
            dpg.configure_item("titlebar_dl",  width=vw,        height=TITLE_H)
            dpg.configure_item("sidebar_win",  width=sw,        height=content_h)
            dpg.configure_item("sidebar_dl",   width=sw,        height=content_h)
            dpg.configure_item("content_win",  width=content_w, height=content_h)
            dpg.configure_item("content_dl",   width=content_w)
            dpg.configure_item("ticker_dl",    width=vw,        height=TICKER_H)
            dpg.configure_item("splash_win",   width=vw,        height=vh)
            dpg.configure_item("splash_dl",    width=vw,        height=vh)
            _draw_titlebar("titlebar_dl", vw)
            _sb_last_w[0] = -1  # force content resize on next tick

        _handle_drag()

        # Close button (top-right corner, tracks current vw)
        if dpg.is_mouse_button_clicked(0):
            mouse = dpg.get_mouse_pos(local=False)
            vp    = dpg.get_viewport_pos()
            rx    = mouse[0] - vp[0]
            ry    = mouse[1] - vp[1]
            # Close — rightmost button
            if vw-TITLE_H+8 <= rx <= vw-8 and 8 <= ry <= TITLE_H-8:
                dpg.stop_dearpygui()
            # Fullscreen toggle button (second from right)
            elif vw-TITLE_H*2+8 <= rx <= vw-TITLE_H+8 and 8 <= ry <= TITLE_H-8:
                dpg.toggle_viewport_fullscreen()
                _is_fullscreen[0] = not _is_fullscreen[0]

        # Title bar redrawn every frame so button hit-states stay current
        _draw_titlebar("titlebar_dl", vw)

        # Sidebar & content
        _sidebar_tick(vw, vh)
        _content_w = vw - _sb_w[0]
        _content_h = vh - TITLE_H - TICKER_H
        _draw_content("content_dl", _content_w, _content_h)
        _draw_tab_transition("content_dl", _content_w, _content_h)
        profile_panel.draw("content_dl", _content_w, _content_h)
        wrapped_overlay.draw("content_dl", _content_w, _content_h)
        hotkey_overlay.draw("content_dl", _content_w, _content_h)
        toast.draw("content_dl", _content_w, _content_h)
        _draw_ticker("ticker_dl", vw)

        # Kick off rankings reveal the first time the user actually lands on
        # the Rankings tab. Phase 4 changed the default tab to HOME, so we no
        # longer fire the reveal at splash-done — the slam-impact tween reads
        # rankings layout state that is only populated by `draw_rankings`, and
        # tweens that fire while the user is on another tab would KeyError.
        if (state.splash_done
                and state.active_tab == "rankings"
                and not _rankings_triggered[0]):
            _rankings_triggered[0] = True
            rankings_state.begin_loading()
            def _start_reveal():
                time.sleep(0.5)
                data = live.rankings if live.loaded and live.rankings else _DEMO_RANKS_FALLBACK
                rankings_state.begin_reveal(data)
            threading.Thread(target=_start_reveal, daemon=True).start()

        # Rankings → Scout navigation (click player name on rankings page)
        if state.nav_to_scout:
            target = state.nav_to_scout
            state.nav_to_scout = None
            # Ensure scout has data loaded
            if scout_state.phase == scout_state.__class__.__mro__[0] or \
               not scout_state.players:
                if live.loaded and live.scout:
                    scout_state.begin_load(live.scout)
            state.active_tab = "scout"
            if dpg.does_item_exist("content_win"):
                dpg.set_y_scroll("content_win", 0)
            # Auto-select the player after a brief delay for the tab animation
            def _nav_select(name=target):
                scout_state.select(name)
            anim.tween(0, 1, 1, "linear", delay_ms=200, on_done=_nav_select)

        # Populate scout + inhouse tabs with live data when available
        if live.loaded and not _scout_populated[0] and live.scout:
            _scout_populated[0] = True
            scout_state.begin_load(live.scout)

        if live.loaded and not _inhouse_populated[0] and live.inhouse:
            _inhouse_populated[0] = True
            from ui.inhouse import update_live_data as _ih_update
            _ih_update(live.inhouse, live.inhouse_champs)
            inhouse_state.begin_load(live.inhouse)

        # ── Show update notification (main-thread safe) ───────────────────
        if _pending_update[0]:
            _upd_tag, _upd_url = _pending_update[0]
            _pending_update[0] = None   # consume once
            _rel_url = (_upd_url or
                        f"https://github.com/BLHvibe/The-Rift/releases/tag/{_upd_tag}")
            def _open_release(url=_rel_url):
                import webbrowser
                try:
                    webbrowser.open(url)
                except Exception:
                    pass
            toast.push(f"The Rift {_upd_tag} is ready — click to download.",
                       kind="info", title="Update available",
                       duration=14.0, action=_open_release)

        # Splash overlay
        if not state.splash_done:
            _draw_splash("splash_dl", splash, vw, vh)
            if splash.loading_done and splash.phase == SplashPhase.LOADING:
                splash.finish()
            # Click-to-skip — only once we've finished loading so we don't
            # dismiss before live data has populated the tabs.
            if (dpg.is_mouse_button_clicked(0)
                    and splash.loading_done
                    and splash.phase != SplashPhase.FADE_OUT):
                splash.finish()
            dpg.focus_item("splash_win")
        else:
            if dpg.does_item_exist("splash_win"):
                dpg.configure_item("splash_win", show=False)

        dpg.render_dearpygui_frame()

    # Clean shutdown — release pygame.mixer first so its callback thread
    # isn't running when the interpreter starts tearing down. Wrap
    # destroy_context in try/except because PyInstaller-frozen builds on
    # Windows occasionally fault during the final teardown even on a clean
    # close; the user has already chosen to exit, so suppress noise.
    try:
        audio.shutdown()
    except Exception:
        pass
    try:
        dpg.destroy_context()
    except Exception:
        pass


if __name__ == "__main__":
    main()
