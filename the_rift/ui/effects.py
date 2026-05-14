"""
Reusable animation helpers — call once per frame from any drawlist.
All effects are stateless (use time.monotonic) so they need no per-call setup.
"""
import math
import time
import dearpygui.dearpygui as dpg


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
    Useful for breathing borders / glow rings."""
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
