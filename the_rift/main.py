"""
The Rift — main entry point.
Phase 0: foundation shell with splash screen overlay.
"""
import sys, os, time, math, threading

_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)

import dearpygui.dearpygui as dpg
from PIL import Image
import numpy as np

from theme import C, setup_theme, setup_fonts
from core.animations import anim
from core.state import state
from ui.rankings import rankings as rankings_state, draw_rankings, RankRevealPhase
from ui.draft import draw_draft
from ui.scout import draw_scout
from ui.inhouse import draw_inhouse
from ui.tierlist import draw_tierlist
from ui.settings import draw_settings, close_settings_window
from ui.commands import draw_commands

WIN_W, WIN_H = 1280, 800
TITLE_H      = 52    # titlebar height
SIDEBAR_W    = 68    # collapsed sidebar width

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

def _handle_drag():
    global _drag_start, _win_pos_start
    mouse  = dpg.get_mouse_pos(local=False)
    vp_pos = dpg.get_viewport_pos()
    rel    = (mouse[0] - vp_pos[0], mouse[1] - vp_pos[1])

    if dpg.is_mouse_button_down(0):
        if rel[1] < TITLE_H and _drag_start is None:
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
    t = dpg.draw_text((18, h//2-14), "THE RIFT", color=C["rift_purple"], size=28, parent=dl)
    if "cinzel_28" in _FONTS:
        dpg.bind_item_font(t, _FONTS["cinzel_28"])
    # Close button
    m = 8
    dpg.draw_rectangle((w-h+m, m),(w-m, h-m),
                        fill=(0,0,0,0), color=C["rule_dark"], rounding=4, parent=dl)
    cx, cy = w - h//2, h//2
    dpg.draw_line((cx-9, cy-9),(cx+9, cy+9), color=C["txt2"], thickness=2, parent=dl)
    dpg.draw_line((cx+9, cy-9),(cx-9, cy+9), color=C["txt2"], thickness=2, parent=dl)
    # Fullscreen button
    fx = w - h*2 + m
    dpg.draw_rectangle((fx, m),(fx+h-m*2, h-m),
                        fill=(0,0,0,0), color=C["rule_dark"], rounding=4, parent=dl)
    fcx = fx + (h-m*2)//2
    dpg.draw_rectangle((fcx-9, cy-9),(fcx+9, cy+9),
                        fill=(0,0,0,0), color=C["txt2"], thickness=1.5, parent=dl)

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
        self.fun_fact     = "The term 'The Rift' refers to the divide between victory and defeat."
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
    cy  = vh // 2 - 50

    # Full background
    dpg.draw_rectangle((0,0),(vw,vh),
                        fill=(*C["bg"][:3], fa),
                        color=(0,0,0,0), parent=dl)

    # --- Crown (programmatic) ---
    pulse  = (math.sin(sp.pulse_t) + 1) / 2
    ca     = int(sp.crown_alpha * fa / 255)

    # Soft gold glow halo behind crown using layered circles
    if ca > 10:
        glow_a = int(pulse * 55 * fa / 255)
        crown_cx = cx
        crown_cy = cy - 42           # base-top sits 42px above cy
        crown_sz = 108               # half-width
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
        ry   = cy + 80
        ra   = int(fa * 0.8)
        dpg.draw_line((cx-half, ry), (cx+half, ry),
                      color=(*C["gold"][:3], ra), thickness=1, parent=dl)

    # --- Subtitle ---
    if sp.rule_frac > 0.5:
        sa    = int((sp.rule_frac - 0.5) * 2 * 160 * fa / 255)
        sub   = sp.SUBTITLE
        sw    = len(sub) * 8
        s_tag = dpg.draw_text((cx - sw//2, cy + 90), sub,
                              color=(*C["txt2"][:3], sa), size=14, parent=dl)
        if "raj_sb_14" in _FONTS:
            dpg.bind_item_font(s_tag, _FONTS["raj_sb_14"])

    # --- Fun fact card ---
    if sp.fact_alpha > 0:
        crd_w, crd_h = 440, 72
        crd_x = cx - crd_w // 2
        crd_y = int(cy + 120 + sp.fact_y_off)
        fa2   = int(sp.fact_alpha * fa / 255)

        dpg.draw_rectangle((crd_x, crd_y), (crd_x+crd_w, crd_y+crd_h),
                           fill=(*C["panel"][:3], fa2),
                           color=(*C["rule_gold"][:3], fa2),
                           rounding=4, parent=dl)
        lbl = dpg.draw_text((crd_x+14, crd_y+10), "DID YOU KNOW",
                            color=(*C["gold_dk"][:3], fa2), size=10, parent=dl)
        lines = _wrap(sp.fun_fact, 54)
        for i, line in enumerate(lines[:2]):
            ft = dpg.draw_text((crd_x+14, crd_y+25+i*18), line,
                               color=(*C["txt2"][:3], fa2), size=12, parent=dl)

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
# Sidebar (Phase 0 — static icon strip)
# ---------------------------------------------------------------------------
def _draw_sidebar(dl, h):
    from ui.sidebar import TABS, ICON_SIZE, ITEM_H, TOP_PAD, _DRAW_FNS, COLLAPSED_W
    dpg.delete_item(dl, children_only=True)

    dpg.draw_rectangle((0,0),(COLLAPSED_W,h), fill=C["panel"], color=(0,0,0,0), parent=dl)
    dpg.draw_line((COLLAPSED_W-1,0),(COLLAPSED_W-1,h),
                  color=C["rule_dark"], thickness=1, parent=dl)

    for i, (tab_id, label, draw_fn_name) in enumerate(TABS):
        iy        = TOP_PAD + i * ITEM_H
        is_active = (tab_id == state.active_tab)
        icon_col  = C["gold"] if is_active else C["txt2"]

        if is_active:
            dpg.draw_rectangle((0, iy+4),(3, iy+ITEM_H-4),
                               fill=C["gold"], color=(0,0,0,0), parent=dl)
            dpg.draw_rectangle((3, iy+2),(COLLAPSED_W-2, iy+ITEM_H-2),
                               fill=(*C["card"][:3], 160), color=(0,0,0,0),
                               rounding=4, parent=dl)
        fn = _DRAW_FNS.get(draw_fn_name)
        if fn:
            fn(dl, COLLAPSED_W//2, iy+ITEM_H//2, ICON_SIZE, (*icon_col[:3], 255))

    # Click handling
    if dpg.is_mouse_button_clicked(0):
        mouse  = dpg.get_mouse_pos(local=False)
        vp     = dpg.get_viewport_pos()
        rel_x  = mouse[0] - vp[0]
        rel_y  = mouse[1] - vp[1] - TITLE_H
        if 0 <= rel_x < COLLAPSED_W:
            idx = int((rel_y - TOP_PAD) // ITEM_H)
            if 0 <= idx < len(TABS):
                new_tab = TABS[idx][0]
                if new_tab != state.active_tab:
                    state.active_tab = new_tab

# ---------------------------------------------------------------------------
# Content routing
# ---------------------------------------------------------------------------
def _draw_content(dl, w, h):
    if state.active_tab == "rankings":
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
    else:
        dpg.delete_item(dl, children_only=True)
        dpg.draw_rectangle((0,0),(w,h), fill=C["bg"], color=(0,0,0,0), parent=dl)

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

    # --- Root window ---
    with dpg.window(tag="root", no_title_bar=True, no_resize=True,
                    no_move=True, no_scrollbar=True):
        with dpg.drawlist(tag="titlebar_dl", width=WIN_W, height=TITLE_H):
            pass
        with dpg.group(horizontal=True):
            with dpg.child_window(tag="sidebar_win", width=SIDEBAR_W, height=WIN_H-TITLE_H,
                                  border=False, no_scrollbar=True):
                with dpg.drawlist(tag="sidebar_dl", width=SIDEBAR_W, height=WIN_H-TITLE_H):
                    pass
            with dpg.child_window(tag="content_win", width=WIN_W-SIDEBAR_W, height=WIN_H-TITLE_H,
                                  border=False, no_scrollbar=True):
                with dpg.drawlist(tag="content_dl", width=WIN_W-SIDEBAR_W, height=WIN_H-TITLE_H):
                    pass

    # --- Splash overlay window (on top of root) ---
    with dpg.window(tag="splash_win", no_title_bar=True, no_resize=True,
                    no_move=True, no_scrollbar=True, no_scroll_with_mouse=True,
                    pos=(0, 0), width=WIN_W, height=WIN_H,
                    no_bring_to_front_on_focus=False):
        with dpg.drawlist(tag="splash_dl", width=WIN_W, height=WIN_H):
            pass

    dpg.set_primary_window("root", True)
    dpg.focus_item("splash_win")

    # Start splash
    splash = Splash()
    splash.start()

    # Demo rankings data — will be replaced by real Sheets fetch
    _DEMO_RANKS = [
        {"name": "Phantom",   "score": 2840, "tier": "Challenger"},
        {"name": "Ironclad",  "score": 2710, "tier": "Grandmaster"},
        {"name": "Vex",       "score": 2590, "tier": "Master"},
        {"name": "Shroud",    "score": 2440, "tier": "Diamond"},
        {"name": "Blaze",     "score": 2310, "tier": "Diamond"},
        {"name": "Kira",      "score": 2180, "tier": "Emerald"},
        {"name": "Dusk",      "score": 2050, "tier": "Emerald"},
        {"name": "Nox",       "score": 1920, "tier": "Platinum"},
        {"name": "Cinder",    "score": 1800, "tier": "Platinum"},
        {"name": "Riven",     "score": 1670, "tier": "Gold"},
        {"name": "Ember",     "score": 1540, "tier": "Gold"},
        {"name": "Lyra",      "score": 1410, "tier": "Silver"},
        {"name": "Torque",    "score": 1290, "tier": "Silver"},
        {"name": "Flux",      "score": 1160, "tier": "Bronze"},
        {"name": "Zeal",      "score": 1040, "tier": "Bronze"},
    ]

    # Fake data load (8s) — real load wired when Sheets is connected
    def _fake_load():
        time.sleep(8.0)
        splash.loading_done = True
    threading.Thread(target=_fake_load, daemon=True).start()

    _rankings_triggered = [False]
    _last_vp_size       = [0, 0]   # tracks resize
    _f11_was_down       = [False]  # edge-detect for F11

    while dpg.is_dearpygui_running():
        anim.tick()
        splash.tick()

        vw = dpg.get_viewport_width()
        vh = dpg.get_viewport_height()

        # F11 fullscreen toggle (edge-detect so one press = one toggle)
        f11_down = dpg.is_key_down(dpg.mvKey_F11)
        if f11_down and not _f11_was_down[0]:
            dpg.toggle_viewport_fullscreen()
        _f11_was_down[0] = f11_down

        # Resize: update all containers when viewport dimensions change
        if vw != _last_vp_size[0] or vh != _last_vp_size[1]:
            _last_vp_size[0], _last_vp_size[1] = vw, vh
            content_w = vw - 48
            content_h = vh - TITLE_H
            dpg.configure_item("titlebar_dl",  width=vw,        height=TITLE_H)
            dpg.configure_item("sidebar_win",  width=SIDEBAR_W, height=content_h)
            dpg.configure_item("sidebar_dl",   width=SIDEBAR_W, height=content_h)
            dpg.configure_item("content_win",  width=content_w, height=content_h)
            dpg.configure_item("content_dl",   width=content_w, height=content_h)
            dpg.configure_item("splash_win",   width=vw,       height=vh)
            dpg.configure_item("splash_dl",    width=vw,       height=vh)
            _draw_titlebar("titlebar_dl", vw)

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

        # Title bar redrawn every frame so button hit-states stay current
        _draw_titlebar("titlebar_dl", vw)

        # Sidebar & content
        _draw_sidebar("sidebar_dl", vh-TITLE_H)
        _draw_content("content_dl", vw-SIDEBAR_W, vh-TITLE_H)

        # Kick off rankings reveal once splash is done
        if state.splash_done and not _rankings_triggered[0]:
            _rankings_triggered[0] = True
            rankings_state.begin_loading()
            def _start_reveal():
                time.sleep(0.5)
                rankings_state.begin_reveal(_DEMO_RANKS)
            threading.Thread(target=_start_reveal, daemon=True).start()

        # Splash overlay
        if not state.splash_done:
            _draw_splash("splash_dl", splash, vw, vh)
            if splash.loading_done and splash.phase == SplashPhase.LOADING:
                splash.finish()
            dpg.focus_item("splash_win")
        else:
            if dpg.does_item_exist("splash_win"):
                dpg.configure_item("splash_win", show=False)

        dpg.render_dearpygui_frame()

    dpg.destroy_context()


if __name__ == "__main__":
    main()
