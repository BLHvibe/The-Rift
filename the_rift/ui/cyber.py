"""
Cyberpunk command-deck draw primitives (v2.7 Draft Board revamp).

All helpers are stateless and driven by time.monotonic(), matching the
convention in ui/effects.py, and draw into a DPG draw layer via parent=dl,
matching ui/draft.py. Colors are RGBA tuples.

Ambient motion (scanline scroll, grid pan, marching dashes, flicker) is
gated by a module-level flag so CALM MODE / reduce-motion can freeze it
without any callsite change:
  set_motion(False) -> scanlines suppressed, grid frozen (still drawn),
  marching dashes fall back to a static dashed border, flicker/wave hold
  at their steady value.

Label helpers take a `text_fn` callback (pass ui.draft._txt) so this
module keeps no font registry of its own and stays import-cycle free.
Breathing / drift-field atmosphere lives in ui/effects.py — reuse that;
this module deliberately does not duplicate it.
"""
import math
import time
import random
import dearpygui.dearpygui as dpg
from theme import C

# ---------------------------------------------------------------------------
# Motion gate
# ---------------------------------------------------------------------------
_MOTION = True


def set_motion(on):
    """CALM MODE / reduce-motion hook. False freezes all ambient animation."""
    global _MOTION
    _MOTION = bool(on)


def motion_on():
    return _MOTION


def _now():
    return time.monotonic()


def wave(period, lo=0.0, hi=1.0, offset=0.0):
    """Sine in [lo, hi] with the given period (s). Holds at `hi` when motion
    is off so pulsing elements stay visible but stop breathing."""
    if not _MOTION:
        return hi
    t = _now() + offset
    s = 0.5 + 0.5 * math.sin(t * (2 * math.pi / max(period, 1e-6)))
    return lo + (hi - lo) * s


def flicker_alpha(base, hz=6, ampl=0.08, drop_chance=0.04, drop_to=0.6):
    """Holographic flicker: rare brief dim, otherwise subtle sine breathing.
    Returns an int alpha. Steady at `base` when motion is off."""
    base = int(base)
    if not _MOTION:
        return base
    if random.random() < drop_chance:
        return int(base * drop_to)
    return int(base * (1.0 - ampl + ampl * (0.5 + 0.5 * math.sin(_now() * hz * math.pi))))


# ---------------------------------------------------------------------------
# Corner-cut geometry
# ---------------------------------------------------------------------------
def _cut_points(x1, y1, x2, y2, cut):
    cut = max(0, min(int(cut), int((x2 - x1) / 2), int((y2 - y1) / 2)))
    return [(x1, y1), (x2 - cut, y1), (x2, y1 + cut),
            (x2, y2), (x1 + cut, y2), (x1, y2 - cut)]


def draw_cut_rect(dl, x1, y1, x2, y2, cut=10, fill=None, color=None, thickness=1):
    """Rectangle with 45-deg notches at the top-right and bottom-left corners.
    `fill` / `color` are RGBA tuples; either may be None. The outline is
    traced as discrete lines so `thickness` is honored and AA looks clean."""
    pts = _cut_points(x1, y1, x2, y2, cut)
    if fill is not None:
        dpg.draw_polygon(pts, fill=fill, color=(0, 0, 0, 0), parent=dl)
    if color is not None:
        for i in range(len(pts)):
            a, b = pts[i], pts[(i + 1) % len(pts)]
            dpg.draw_line(a, b, color=color, thickness=thickness, parent=dl)


# ---------------------------------------------------------------------------
# Bracket frames  [ ... ]
# ---------------------------------------------------------------------------
def draw_brackets(dl, x1, y1, x2, y2, length=14, color=(255, 255, 255, 255),
                  thickness=2):
    """Two L-shapes: top-left + bottom-right corner brackets, no fill."""
    l = max(2, int(length))
    dpg.draw_line((x1, y1), (x1 + l, y1), color=color, thickness=thickness, parent=dl)
    dpg.draw_line((x1, y1), (x1, y1 + l), color=color, thickness=thickness, parent=dl)
    dpg.draw_line((x2, y2), (x2 - l, y2), color=color, thickness=thickness, parent=dl)
    dpg.draw_line((x2, y2), (x2, y2 - l), color=color, thickness=thickness, parent=dl)


def draw_bracket_label(dl, x, y, label, color, font_sz, text_fn,
                       font_key=None, bracket_color=None, gap=6,
                       char_w=0.56):
    """ [  LABEL  ]  — square brackets via text_fn so fonts bind.
    Returns the consumed width in px (approximate; uses char_w * font_sz
    per glyph for proportional fonts — pass ~0.6 for monospace)."""
    bc = bracket_color if bracket_color is not None else color
    br_w = max(6, int(font_sz * 0.42))
    text_fn(dl, x, y, "[", bc, font_sz, font_key)
    lx = x + br_w + gap
    text_fn(dl, lx, y, label, color, font_sz, font_key)
    lbl_w = int(len(label) * font_sz * char_w)
    rx = lx + lbl_w + gap
    text_fn(dl, rx, y, "]", bc, font_sz, font_key)
    return (rx + br_w) - x


# ---------------------------------------------------------------------------
# Dashed / marching borders
# ---------------------------------------------------------------------------
def _perimeter_edges(x1, y1, x2, y2):
    return (((x1, y1), (x2, y1)),
            ((x2, y1), (x2, y2)),
            ((x2, y2), (x1, y2)),
            ((x1, y2), (x1, y1)))


def draw_dashed_rect(dl, x1, y1, x2, y2, color, dash=6, gap=4,
                     thickness=1, phase=0.0):
    """Static dashed rectangle border. `phase` shifts the dash start so a
    caller can animate it (see draw_marching_dash)."""
    step = dash + gap
    if step <= 0:
        return
    off = (-phase) % step
    for (ax, ay), (bx, by) in _perimeter_edges(x1, y1, x2, y2):
        seg = math.hypot(bx - ax, by - ay)
        if seg <= 0:
            continue
        ux, uy = (bx - ax) / seg, (by - ay) / seg
        pos = off - step
        while pos < seg:
            s = max(0.0, pos)
            e = min(seg, pos + dash)
            if e > s:
                dpg.draw_line((ax + ux * s, ay + uy * s),
                              (ax + ux * e, ay + uy * e),
                              color=color, thickness=thickness, parent=dl)
            pos += step


def draw_marching_dash(dl, x1, y1, x2, y2, color, dash=8, gap=6,
                       speed=14, thickness=1):
    """Dashes that march clockwise. Falls back to a static dashed border
    when motion is off."""
    phase = (_now() * speed) if _MOTION else 0.0
    draw_dashed_rect(dl, x1, y1, x2, y2, color, dash=dash, gap=gap,
                     thickness=thickness, phase=phase)


# ---------------------------------------------------------------------------
# Full-screen scanline + grid background
# ---------------------------------------------------------------------------
def draw_scanlines(dl, x, y, w, h, color=None, alpha=14, spacing=4, speed=30):
    """Horizontal scanline overlay scrolling downward. Suppressed entirely
    when motion is off (CALM MODE removes scanlines)."""
    if not _MOTION or alpha <= 0 or w <= 0 or h <= 0:
        return
    col = (*(color or C["scan_gy"])[:3], alpha)
    drift = int((_now() * speed) % spacing)
    ly = y - spacing + drift
    while ly <= y + h:
        if y <= ly <= y + h:
            dpg.draw_line((x, ly), (x + w, ly), color=col, thickness=1, parent=dl)
        ly += spacing


def draw_grid_bg(dl, x, y, w, h, spacing=40, alpha=28, color=None,
                 speed_x=8, speed_y=4):
    """Sparse cool grid lines, slow drift. Stays drawn but frozen (no drift)
    when motion is off."""
    if alpha <= 0 or w <= 0 or h <= 0:
        return
    col = (*(color or C["grid_a"])[:3], alpha)
    t = _now()
    dx = int((t * speed_x) % spacing) if _MOTION else 0
    dy = int((t * speed_y) % spacing) if _MOTION else 0
    gx = x - spacing + dx
    while gx <= x + w:
        if x <= gx <= x + w:
            dpg.draw_line((gx, y), (gx, y + h), color=col, thickness=1, parent=dl)
        gx += spacing
    gy = y - spacing + dy
    while gy <= y + h:
        if y <= gy <= y + h:
            dpg.draw_line((x, gy), (x + w, gy), color=col, thickness=1, parent=dl)
        gy += spacing


# ---------------------------------------------------------------------------
# Transient glitch overlay (S2 — recommendation change)
# ---------------------------------------------------------------------------
def draw_glitch_overlay(dl, x1, y1, x2, y2, intensity=1.0, color=None):
    """Brief horizontal-displacement bars over a region. The caller decides
    when to fire it (e.g. during the ~100ms rec-swap window) and ramps
    `intensity` 1->0; honored even with motion off since it is informative."""
    if intensity <= 0:
        return
    col3 = (color or C["cy_lt"])[:3]
    h = y2 - y1
    if h <= 6:
        return
    n = max(1, int(4 * intensity))
    for _ in range(n):
        sy = y1 + random.random() * (h - 6)
        bh = 2 + random.random() * 5
        off = (random.random() - 0.5) * 24 * intensity
        a = int((70 + 90 * random.random()) * intensity)
        dpg.draw_rectangle((x1 + off, sy), (x2 + off, sy + bh),
                           fill=(*col3, a), color=(0, 0, 0, 0), parent=dl)
