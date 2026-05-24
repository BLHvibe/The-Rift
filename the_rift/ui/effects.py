"""
Reusable animation helpers — call once per frame from any drawlist.
All effects are stateless (use time.monotonic) so they need no per-call setup.
"""
import math
import time
import dearpygui.dearpygui as dpg

from core.animations import anim


def draw_orbital_spinner(dl, cx, cy, r, color, alpha,
                          n_dots=3, speed=1.4, dot_r=3):
    """3-dot orbital spinner. Drop-in replacement for static 'loading…' text.

    `color` is an (r,g,b) tuple. `alpha` is 0..255."""
    if alpha <= 0:
        return
    t = time.monotonic()
    base = t * speed
    # Faint orbit ring
    dpg.draw_circle((cx, cy), r,
                    fill=(0, 0, 0, 0),
                    color=(*color[:3], int(alpha * 0.25)),
                    thickness=1, parent=dl)
    for i in range(n_dots):
        ang = base + i * (2 * math.pi / n_dots)
        ox = cx + r * math.cos(ang)
        oy = cy + r * math.sin(ang)
        # Trail dimming — leading dot is brightest
        trail_a = int(alpha * (0.4 + 0.6 * ((i + 0.0) / n_dots)))
        dpg.draw_circle((ox, oy), dot_r,
                        fill=(*color[:3], trail_a),
                        color=(0, 0, 0, 0), parent=dl)


def draw_drift_field(dl, x, y, w, h, alpha, accent=(200, 168, 106),
                      n_dots=18, seed=0):
    """Slow drifting Lissajous dot field — ambient motion for idle screens.

    Deterministic per-instance via `seed`. Dots have varied frequencies so
    they never sync up. Very low alpha — meant as atmosphere, not noise."""
    alpha = alpha * anim.intensity
    if alpha <= 0 or w < 20 or h < 20:
        return
    t = time.monotonic()
    cx, cy = w / 2, h / 2
    for i in range(n_dots):
        # Per-dot frequencies + phase (deterministic from i + seed)
        fx = 0.05 + ((i * 7 + seed) % 11) * 0.013
        fy = 0.04 + ((i * 13 + seed) % 9) * 0.015
        px = ((i * 31 + seed * 7) % 360) * (math.pi / 180)
        py = ((i * 47 + seed * 11) % 360) * (math.pi / 180)
        # Position via Lissajous
        dx = math.sin(t * fx + px)
        dy = math.cos(t * fy + py)
        ox = x + cx + dx * (w * 0.42)
        oy = y + cy + dy * (h * 0.42)
        # Vary alpha per dot for depth
        a_mul = 0.4 + 0.5 * (0.5 + 0.5 * math.sin(t * 0.3 + i))
        dpg.draw_circle((int(ox), int(oy)), 1.5,
                        fill=(*accent[:3], int(alpha * a_mul * 0.55)),
                        color=(0, 0, 0, 0), parent=dl)


def draw_shimmer(dl, x, y, w, h, accent, alpha,
                  period=4.0, sweep_w=80):
    """Translucent vertical band that sweeps left→right across a region every
    `period` seconds. One pass per cycle (off-screen between passes).

    Used for podium-row gold/silver/bronze sheen."""
    alpha = alpha * anim.intensity
    if alpha <= 0 or w <= 0:
        return
    t = time.monotonic()
    phase = (t % period) / period      # 0..1
    # Active for first 35% of the cycle, otherwise off-screen
    active_frac = 0.35
    if phase > active_frac:
        return
    travel_t = phase / active_frac     # 0..1 during active window
    # Position: starts just left of x, ends just right of x+w
    band_x = x - sweep_w + int((w + sweep_w * 2) * travel_t)
    # Soft falloff at sweep edges
    for ofs in range(-sweep_w // 2, sweep_w // 2, 4):
        # Bell curve alpha across the band width
        rel = ofs / (sweep_w / 2)
        a = int(alpha * 0.55 * max(0.0, 1.0 - rel * rel))
        if a <= 2:
            continue
        seg_x = band_x + ofs + sweep_w // 2
        if seg_x < x - 4 or seg_x > x + w + 4:
            continue
        dpg.draw_rectangle((seg_x, y), (seg_x + 4, y + h),
                           fill=(*accent[:3], a),
                           color=(0, 0, 0, 0), parent=dl)


def breathing_alpha(base_alpha, period=3.5, amp=0.18, offset=0.0):
    """Return an alpha value that pulses sinusoidally between base*(1-amp) and base.
    Useful for breathing borders / glow rings. Pulse depth scales with the
    global animation intensity — at intensity 0 the value holds steady."""
    amp = amp * anim.intensity
    t = time.monotonic() + offset
    factor = 1.0 - amp * (0.5 - 0.5 * math.cos(t * (2 * math.pi / period)))
    return max(0, min(255, int(base_alpha * factor)))


def draw_breathing_ring(dl, cx, cy, r, color, alpha,
                         period=3.5, offset=0.0, thickness=2):
    """Pulsing circle outline — same effect as the gauge's ambient ring,
    drop-in for any element that should glow."""
    a = breathing_alpha(alpha, period=period, amp=0.4, offset=offset)
    if a <= 0:
        return
    dpg.draw_circle((cx, cy), r,
                    fill=(0, 0, 0, 0),
                    color=(*color[:3], a),
                    thickness=thickness, parent=dl)


# ---------------------------------------------------------------------------
# Phase 0a — persistent / interactive motion toolkit.
# Ambient helpers scale by anim.intensity (and vanish at 0); functional
# helpers (count-ups, hover lifts) collapse to instant when intensity is 0.
# Every helper is stateless per frame — per-element state lives in anim.smooth,
# keyed by a caller-supplied id.
# ---------------------------------------------------------------------------

def count_up(key, target, rate=0.16, start=0.0):
    """Living number — eases from `start` (first sight) toward `target`, and
    re-eases whenever `target` changes. Returns a float; the caller formats
    it. Snaps instantly when motion is disabled."""
    target = float(target)
    if anim.intensity <= 0.01:
        return target
    return anim.smooth(f"cu:{key}", target, rate=rate, snap=0.01, start=start)


def hover_lift(key, hovered, lift=6.0):
    """Eased vertical offset (0 -> -lift px) for an element under the cursor —
    add it to the element's y so it rises on hover. Instant at intensity 0."""
    target = -abs(lift) if hovered else 0.0
    if anim.intensity <= 0.01:
        return target
    return anim.smooth(f"hl:{key}", target, rate=0.28, snap=0.05, start=0.0)


def press_offset(key, pressed, depth=2.0):
    """Eased downward offset (0 -> +depth px) while an element is held, for
    tactile press feedback. Instant at intensity 0."""
    target = abs(depth) if pressed else 0.0
    if anim.intensity <= 0.01:
        return target
    return anim.smooth(f"po:{key}", target, rate=0.40, snap=0.05, start=0.0)


def hover_amt(key, hovered):
    """Eased 0..1 hover strength for fading glows / borders / tints. Instant
    at intensity 0."""
    target = 1.0 if hovered else 0.0
    if anim.intensity <= 0.01:
        return target
    return anim.smooth(f"ha:{key}", target, rate=0.30, snap=0.02, start=0.0)


def draw_hover_glow(dl, x1, y1, x2, y2, color, amt, rounding=6, spread=3):
    """Soft outer glow that fades in with hover strength `amt` (0..1, e.g.
    from hover_amt). A few concentric rounded rects, brightest nearest the
    element."""
    if amt <= 0.01:
        return
    a = max(0.0, min(1.0, amt))
    for i in range(1, spread + 1):
        ring_a = int(a * 55 * (spread - i + 1) / spread)
        if ring_a <= 1:
            continue
        dpg.draw_rectangle((x1 - i, y1 - i), (x2 + i, y2 + i),
                           fill=(0, 0, 0, 0), color=(*color[:3], ring_a),
                           rounding=rounding + i, thickness=1, parent=dl)


def draw_focus_ring(dl, x1, y1, x2, y2, color, rounding=6):
    """Keyboard-focus ring — always visible (focus is functional); the outer
    glow breathes when motion is enabled and holds steady when it isn't."""
    dpg.draw_rectangle((x1 - 2, y1 - 2), (x2 + 2, y2 + 2),
                       fill=(0, 0, 0, 0), color=(*color[:3], 235),
                       rounding=rounding + 2, thickness=2, parent=dl)
    glow = breathing_alpha(90, period=1.8, amp=0.7)
    if glow > 4:
        dpg.draw_rectangle((x1 - 4, y1 - 4), (x2 + 4, y2 + 4),
                           fill=(0, 0, 0, 0), color=(*color[:3], glow),
                           rounding=rounding + 4, thickness=2, parent=dl)


def draw_ambient_motes(dl, x, y, w, h, accent, alpha=255, n=10, seed=0):
    """Localized ambient — a few faint motes drifting slowly upward inside the
    rect. Subtle by design; scales with anim.intensity and is off at 0.
    Localized to the given rect — never a full-screen effect."""
    a = alpha * anim.intensity
    if a <= 1 or w < 20 or h < 20:
        return
    t = time.monotonic()
    for i in range(n):
        col_x = ((i * 53 + seed * 13) % 100) / 100.0
        speed = 0.012 + ((i * 7 + seed) % 7) * 0.004
        sway  = ((i * 31 + seed * 5) % 100) / 100.0
        prog  = (t * speed + i / max(n, 1)) % 1.0
        mx = x + col_x * w + math.sin(t * 0.35 + i) * (w * 0.04 * sway)
        my = y + h - prog * h
        edge = min(prog, 1.0 - prog) * 4.0
        mote_a = int(a * 0.5 * max(0.0, min(1.0, edge)))
        if mote_a <= 1:
            continue
        dpg.draw_circle((int(mx), int(my)), 1.6,
                        fill=(*accent[:3], mote_a),
                        color=(0, 0, 0, 0), parent=dl)


def draw_parallax_image(dl, tex, x, y, w, h, drift=7):
    """Draw an image as a living backdrop — sized slightly larger than its
    frame and drifting on a slow ken-burns path so an edge never shows. The
    drift scales with anim.intensity (holds still at 0). `tex` must be a valid
    texture tag; the caller checks existence and clips with panels on top."""
    t = time.monotonic()
    dx = math.sin(t * 0.07) * drift * anim.intensity
    dy = math.cos(t * 0.05) * drift * anim.intensity
    dpg.draw_image(tex,
                   (x - drift + dx, y - drift + dy),
                   (x + w + drift + dx, y + h + drift + dy),
                   parent=dl)


# ---------------------------------------------------------------------------
# Skeleton loaders — placeholder shapes shown while real content loads so a
# view morphs in rather than popping. The shimmer sweep is intensity-aware
# (shapes stay, sweep stops, when motion is off).
# ---------------------------------------------------------------------------

def draw_skeleton_rect(dl, x, y, w, h, rounding=4,
                       base=(28, 38, 56), sheen=(120, 134, 158)):
    """A dim placeholder block with a shimmer sweep."""
    if w <= 0 or h <= 0:
        return
    dpg.draw_rectangle((x, y), (x + w, y + h),
                       fill=(*base[:3], 210), color=(0, 0, 0, 0),
                       rounding=rounding, parent=dl)
    draw_shimmer(dl, x, y, w, h, sheen, alpha=64,
                 period=2.2, sweep_w=min(130, max(40, w)))


def draw_skeleton_text(dl, x, y, w, lines=1, line_h=12, gap=9,
                       base=(28, 38, 56), sheen=(120, 134, 158)):
    """A run of skeleton text lines; the last line is short."""
    for i in range(max(1, lines)):
        lw = w if i < lines - 1 else int(w * 0.6)
        draw_skeleton_rect(dl, x, y + i * (line_h + gap), lw, line_h,
                           rounding=3, base=base, sheen=sheen)


def draw_skeleton_row(dl, x, y, w, h, base=(28, 38, 56),
                      sheen=(120, 134, 158)):
    """A list-row skeleton — a leading avatar disc plus two text bars."""
    pad    = 10
    disc_r = max(8, min(h, 44) // 2 - 2)
    cx     = x + pad + disc_r
    cy     = y + h // 2
    dpg.draw_circle((cx, cy), disc_r, fill=(*base[:3], 210),
                    color=(0, 0, 0, 0), parent=dl)
    tx = cx + disc_r + 12
    tw = max(40, (x + w) - tx - pad)
    draw_skeleton_rect(dl, tx, cy - 13, int(tw * 0.55), 11,
                       rounding=3, base=base, sheen=sheen)
    draw_skeleton_rect(dl, tx, cy + 2, int(tw * 0.80), 9,
                       rounding=3, base=base, sheen=sheen)


# ---------------------------------------------------------------------------
# Hover popover — a small floating detail panel. Call it on hover (drawn last,
# on top) to expose deeper numbers without cluttering the default view.
# ---------------------------------------------------------------------------

def draw_popover(dl, x, y, lines, vw, vh, title=None, width=240,
                 panel=(16, 28, 46), border=(120, 90, 40),
                 title_col=(205, 190, 145), text_col=(216, 207, 186)):
    """Draw a floating popover near (x, y), clamped to stay inside (vw, vh).
    `lines` is a list of strings, or (label, value) tuples rendered as a left
    label + right-aligned value."""
    pad    = 12
    line_h = 19
    head_h = 26 if title else 0
    h  = pad * 2 + head_h + max(1, len(lines)) * line_h
    px = min(max(8, int(x)), max(8, vw - width - 8))
    py = min(max(8, int(y)), max(8, vh - h - 8))
    dpg.draw_rectangle((px + 4, py + 5), (px + width + 4, py + h + 5),
                       fill=(0, 0, 0, 115), color=(0, 0, 0, 0),
                       rounding=6, parent=dl)
    dpg.draw_rectangle((px, py), (px + width, py + h),
                       fill=(*panel[:3], 250), color=(*border[:3], 235),
                       rounding=6, thickness=1, parent=dl)
    cy = py + pad
    if title:
        dpg.draw_text((px + pad, cy), str(title).upper(),
                      color=(*title_col[:3], 255), size=14, parent=dl)
        dpg.draw_line((px + pad, cy + 20), (px + width - pad, cy + 20),
                      color=(*border[:3], 200), thickness=1, parent=dl)
        cy += head_h
    for ln in lines:
        if isinstance(ln, (tuple, list)) and len(ln) == 2:
            lbl, val = ln
            dpg.draw_text((px + pad, cy), str(lbl),
                          color=(*text_col[:3], 170), size=14, parent=dl)
            vs    = str(val)
            vw_px = len(vs) * 7
            dpg.draw_text((px + width - pad - vw_px, cy), vs,
                          color=(*text_col[:3], 255), size=14, parent=dl)
        else:
            dpg.draw_text((px + pad, cy), str(ln),
                          color=(*text_col[:3], 220), size=14, parent=dl)
        cy += line_h
