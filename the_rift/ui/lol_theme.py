"""
lol_theme.py — LCS/LEC broadcast-style draw primitives for the Draft Tool.

Replaces ui/cyber.py in the v3 Draft rewrite. Aesthetic:

  • Deep navy backgrounds (LoL client #0a1428 family)
  • Sparing gold accents (#c8aa6e family), used for rules + focal callouts
  • Splash-art banners as backdrop, not foreground (darkened overlays)
  • Crisp typography, no filigree, no scanlines
  • Focal motion only — slow-rotating rune marks on waiting screens, hover
    lifts, lock pulses. NO full-screen ambient motion (per the user's
    feedback_ambient_motion preference).

All helpers are stateless and time-driven (time.monotonic()), drawing into a
DPG draw layer via `parent=dl`. Colors are RGBA tuples.

Primitive set (Phase 3):

    Background / chrome
      draw_navy_panel             — basic panel w/ optional gold border
      draw_gold_rule              — thin gold line
      draw_splash_banner          — full-bleed champion splash + vignette
      draw_role_glyph             — TOP/JGL/MID/BOT/SUP mark
      draw_waiting_screen         — Phase 1: rotating rune + status + progress
      draw_progress_bar           — gold-bordered progress bar

    Player / champion
      draw_player_portrait_frame  — circular portrait w/ tier-tinted border
      draw_pick_chip              — locked champion pick chip
      draw_ban_chip               — banned champion chip w/ strikethrough

    Engine signals
      draw_sample_size_badge      — "thin"/"ok"/"strong" inline badge
      draw_pool_depth_badge       — DEEP/OK/SHALLOW/OFF-ROLE inline badge
      draw_recent_form_dots       — last-N win/loss dot row
      draw_ghost_suggestion_chip  — translucent enemy probable-next-pick
      draw_arc_meter              — win-probability arc gauge
      draw_archetype_card         — 7-archetype pick screen card
      draw_pivot_alert_banner     — slide-down warning w/ pivot options

The text helper `_text` takes an optional `font_key` so callers that want
specific glyph metrics can pass them; default uses DPG's built-in font.
"""
import math
import time

import dearpygui.dearpygui as dpg

try:
    from data import splash_art as _splash
except Exception:                                       # pragma: no cover
    _splash = None


# ---------------------------------------------------------------------------
# Palette — LoL client (#0a1428 navy / #c8aa6e gold family).
# ---------------------------------------------------------------------------

LOL = {
    "navy_deep":   (10,  20,  40,  255),     # #0a1428 — deepest background
    "navy_mid":    (12,  28,  55,  255),     # mid background panels
    "navy_panel":  (16,  36,  64,  255),     # card / panel fill
    "navy_lt":     (28,  56,  92,  255),     # hover state on panels
    "gold_rule":   (120,  90, 40,  255),     # #785a28 — thin rules
    "gold":        (200, 170, 110, 255),     # #c8aa6e — primary gold accent
    "gold_lt":     (205, 190, 145, 255),     # #cdbe91 — text highlight
    "gold_dk":      (92,  69,  32, 255),     # button-dark fill
    "txt":         (240, 230, 210, 255),     # primary text
    "txt_dim":     (160, 150, 130, 255),     # secondary text
    "txt_faint":   (100,  92,  78, 255),     # tertiary text
    "blue_side":   (118, 168, 220, 255),     # team blue accent
    "blue_side_dk":( 40,  80, 140, 255),     # team blue shadow
    "red_side":    (220, 100, 110, 255),     # team red accent
    "red_side_dk":(140,  40,  50, 255),      # team red shadow
    "win":         (110, 190, 140, 255),     # win / OK
    "loss":        (200,  90,  90, 255),     # loss / danger
    "warning":     (220, 165,  70, 255),     # caution / pivot alert
    "stripe":      ( 20,  44,  76, 255),     # zebra-stripe alt-row
}


# Tier → ring tint for player portrait frames (used by draw_player_portrait_frame).
LOL_TIER_RING = {
    "Challenger":  (240, 200, 130, 255),
    "Grandmaster": (220, 110,  90, 255),
    "Master":      (175, 110, 220, 255),
    "Diamond":     (130, 175, 220, 255),
    "Emerald":     (110, 200, 140, 255),
    "Platinum":    (130, 180, 175, 255),
    "Gold":        (200, 170, 110, 255),
    "Silver":      (170, 170, 175, 255),
    "Bronze":      (175, 110,  70, 255),
    "Iron":        (110,  95,  85, 255),
    "Unranked":    ( 80,  90, 105, 255),
}

# Side accents indexed by string.
SIDE_ACCENT = {
    "BLUE": LOL["blue_side"],
    "RED":  LOL["red_side"],
}
SIDE_ACCENT_DK = {
    "BLUE": LOL["blue_side_dk"],
    "RED":  LOL["red_side_dk"],
}


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _now() -> float:
    return time.monotonic()


def _alpha(rgba, a):
    """Return a copy of rgba with the alpha overridden to `a`."""
    return (rgba[0], rgba[1], rgba[2], int(a))


def _text(dl, x, y, txt, color, size=18):
    dpg.draw_text((x, y), txt, color=color, size=size, parent=dl)


def _text_centered(dl, cx, y, txt, color, size=18, approx_glyph_w=0.55):
    w = len(txt) * size * approx_glyph_w
    _text(dl, cx - w / 2, y, txt, color, size)


# ---------------------------------------------------------------------------
# Basic panels + rules
# ---------------------------------------------------------------------------

def draw_navy_panel(dl, x1, y1, x2, y2, *,
                    fill=None, border=True,
                    border_color=None, border_thickness=1,
                    rounding=4, hover=False, alpha=255):
    """Standard panel: navy_panel fill with a thin gold_rule border.
    `hover=True` brightens the fill to navy_lt and the border to gold."""
    if fill is None:
        fill = LOL["navy_lt"] if hover else LOL["navy_panel"]
    fill_rgba = _alpha(fill, alpha) if alpha != 255 else fill
    bcol = (border_color
            if border_color is not None
            else (LOL["gold"] if hover else LOL["gold_rule"]))
    bcol = _alpha(bcol, alpha if alpha < 255 else bcol[3])
    dpg.draw_rectangle((x1, y1), (x2, y2),
                       fill=fill_rgba,
                       color=bcol if border else (0, 0, 0, 0),
                       thickness=border_thickness,
                       rounding=rounding, parent=dl)


def draw_gold_rule(dl, x1, y1, x2, y2, *, thickness=1, alpha=200):
    dpg.draw_line((x1, y1), (x2, y2),
                  color=_alpha(LOL["gold_rule"], alpha),
                  thickness=thickness, parent=dl)


# ---------------------------------------------------------------------------
# Splash banner (champion splash w/ darkening + side accent stripe)
# ---------------------------------------------------------------------------

def draw_splash_banner(dl, x1, y1, x2, y2, *,
                       champion=None,
                       darken=180,
                       accent_side=None,
                       title=None,
                       subtitle=None,
                       title_color=None,
                       fallback=True):
    """Render a championing splash-art banner inside (x1,y1)-(x2,y2). If the
    splash texture isn't loaded yet, falls back to a navy gradient (so we
    never block on disk/network). Top + bottom gradients darken the splash
    so foreground text remains legible. An optional accent strip on the left
    (`accent_side="BLUE"` / `"RED"`) colour-codes which team this belongs to.
    """
    w = max(1, x2 - x1)
    h = max(1, y2 - y1)
    tex_tag = None
    if champion and _splash is not None:
        try:
            tex_tag = _splash.get_texture(champion)
        except Exception:
            tex_tag = None

    if tex_tag is not None and dpg.does_item_exist(tex_tag):
        try:
            dpg.draw_image(tex_tag, (x1, y1), (x2, y2), parent=dl)
        except Exception:
            tex_tag = None
    if tex_tag is None and fallback:
        # Vertical gradient via stacked translucent quads
        for i in range(8):
            t0 = y1 + (h * i // 8)
            t1 = y1 + (h * (i + 1) // 8)
            shade = LOL["navy_deep"] if i < 2 else (
                LOL["navy_mid"] if i < 5 else LOL["navy_deep"])
            dpg.draw_rectangle((x1, t0), (x2, t1),
                               fill=shade, color=(0, 0, 0, 0),
                               parent=dl)

    # Darkening top-band + bottom-band for text legibility.
    dark_top = _alpha(LOL["navy_deep"], min(255, darken + 30))
    dark_bot = _alpha(LOL["navy_deep"], min(255, darken))
    dpg.draw_rectangle((x1, y1), (x2, y1 + h // 3),
                       fill=dark_top, color=(0, 0, 0, 0), parent=dl)
    dpg.draw_rectangle((x1, y1 + 2 * h // 3), (x2, y2),
                       fill=dark_bot, color=(0, 0, 0, 0), parent=dl)

    # Side accent strip (left edge).
    if accent_side and accent_side in SIDE_ACCENT:
        strip_w = max(3, w // 80)
        dpg.draw_rectangle((x1, y1), (x1 + strip_w, y2),
                           fill=SIDE_ACCENT[accent_side],
                           color=(0, 0, 0, 0), parent=dl)

    # Optional title / subtitle (rendered over the darkened bottom band).
    if title:
        tc = title_color or LOL["gold_lt"]
        _text(dl, x1 + 18, y2 - 56, title, tc, 26)
    if subtitle:
        _text(dl, x1 + 18, y2 - 28, subtitle, LOL["txt_dim"], 14)


# ---------------------------------------------------------------------------
# Role glyphs — small marker shape for TOP/JGL/MID/BOT/SUP
# ---------------------------------------------------------------------------

def draw_role_glyph(dl, x, y, size, role, *, color=None):
    """Tiny role icon at (x, y) bounded by `size`. Uses simple geometric
    primitives so we don't depend on icon assets. Color defaults to gold."""
    c = color or LOL["gold"]
    s = max(8, int(size))
    half = s / 2.0
    cx, cy = x + half, y + half
    if role == "TOP":
        # crossed swords (diagonals)
        dpg.draw_line((cx - half, cy + half), (cx + half, cy - half),
                      color=c, thickness=2, parent=dl)
        dpg.draw_line((cx - half, cy - half), (cx + half, cy + half),
                      color=c, thickness=2, parent=dl)
    elif role == "JGL":
        # leafy claw — 3 spread lines from bottom
        for ang_deg in (-50, -90, -130):
            ang = math.radians(ang_deg)
            dx = math.cos(ang) * half
            dy = math.sin(ang) * half
            dpg.draw_line((cx, cy + half * 0.4),
                          (cx + dx, cy + half * 0.4 + dy),
                          color=c, thickness=2, parent=dl)
    elif role == "MID":
        # diamond / star (4-point)
        pts = [(cx, cy - half), (cx + half, cy),
               (cx, cy + half), (cx - half, cy)]
        for i in range(4):
            dpg.draw_line(pts[i], pts[(i + 1) % 4],
                          color=c, thickness=2, parent=dl)
    elif role == "BOT":
        # bow shape — arc + arrow
        for theta_deg in range(120, 241, 18):
            theta = math.radians(theta_deg)
            tnext = math.radians(theta_deg + 18)
            a = (cx + math.cos(theta) * half * 0.9,
                 cy + math.sin(theta) * half * 0.9)
            b = (cx + math.cos(tnext) * half * 0.9,
                 cy + math.sin(tnext) * half * 0.9)
            dpg.draw_line(a, b, color=c, thickness=2, parent=dl)
        # arrow head
        dpg.draw_line((cx + half * 0.4, cy),
                      (cx + half * 0.9, cy),
                      color=c, thickness=2, parent=dl)
    elif role == "SUP":
        # plus / cross
        dpg.draw_line((cx, cy - half * 0.85), (cx, cy + half * 0.85),
                      color=c, thickness=2, parent=dl)
        dpg.draw_line((cx - half * 0.85, cy), (cx + half * 0.85, cy),
                      color=c, thickness=2, parent=dl)
    else:
        # unknown role: small ring
        dpg.draw_circle((cx, cy), half * 0.7,
                        color=c, thickness=2, parent=dl)


# ---------------------------------------------------------------------------
# Waiting screen + standalone progress bar
# ---------------------------------------------------------------------------

def draw_waiting_screen(dl, vw, vh,
                        status_text="",
                        progress_0_1=None,
                        subtitle=None,
                        rotation_period_s=6.0,
                        n_dashes=18,
                        radius=64):
    """Centered waiting screen used by CONNECTING + SCOUTING. Slow gold rune
    ring spins at the center with status text below and an optional
    progress bar."""
    dpg.draw_rectangle((0, 0), (vw, vh),
                       fill=LOL["navy_deep"], color=(0, 0, 0, 0),
                       parent=dl)

    margin = max(40, min(vw, vh) // 12)
    dpg.draw_rectangle((margin, margin), (vw - margin, vh - margin),
                       fill=_alpha(LOL["navy_mid"], 90),
                       color=(0, 0, 0, 0),
                       rounding=8, parent=dl)

    cx, cy = vw // 2, vh // 2

    t = _now()
    base_angle = (t / max(rotation_period_s, 0.5)) * 2 * math.pi
    inner_r = radius - 6
    outer_r = radius + 6
    gold = LOL["gold"]
    gold_dk = LOL["gold_dk"]

    for i in range(n_dashes):
        a = base_angle + (2 * math.pi * i / n_dashes)
        cosA, sinA = math.cos(a), math.sin(a)
        x1 = cx + inner_r * cosA
        y1 = cy + inner_r * sinA
        x2 = cx + outer_r * cosA
        y2 = cy + outer_r * sinA
        fade = i / max(n_dashes - 1, 1)
        alpha = int(70 + 170 * (1.0 - fade))
        col = (gold[0], gold[1], gold[2], alpha)
        dpg.draw_line((x1, y1), (x2, y2), color=col, thickness=2, parent=dl)

    ring_pts = []
    for i in range(48):
        a = 2 * math.pi * i / 48
        ring_pts.append((cx + (radius - 12) * math.cos(a),
                         cy + (radius - 12) * math.sin(a)))
    for i in range(len(ring_pts)):
        a, b = ring_pts[i], ring_pts[(i + 1) % len(ring_pts)]
        dpg.draw_line(a, b, color=_alpha(gold_dk, 120),
                      thickness=1, parent=dl)

    status_y = cy + radius + 30
    if status_text:
        _text_centered(dl, cx, status_y, status_text,
                       _alpha(LOL["gold_lt"], 240), size=22)
    subtitle_y = status_y + 36
    if subtitle:
        _text_centered(dl, cx, subtitle_y, subtitle,
                       _alpha(LOL["txt_dim"], 180), size=15)

    if progress_0_1 is not None:
        bar_y = subtitle_y + 36 if subtitle else status_y + 50
        bar_w, bar_h = 320, 8
        bx = cx - bar_w // 2
        draw_progress_bar(dl, bx, bar_y, bx + bar_w, bar_y + bar_h,
                          progress_0_1, label=None, show_pct=True)


def draw_progress_bar(dl, x1, y1, x2, y2, progress_0_1, *,
                      label=None, show_pct=False):
    """Standalone gold-bordered progress bar. Caller is responsible for
    label placement above; show_pct prints the % under the bar."""
    dpg.draw_rectangle((x1, y1), (x2, y2),
                       fill=_alpha(LOL["navy_panel"], 220),
                       color=_alpha(LOL["gold_dk"], 200),
                       rounding=2, parent=dl)
    p = max(0.0, min(1.0, float(progress_0_1)))
    fill_w = int((x2 - x1) * p)
    if fill_w > 0:
        dpg.draw_rectangle((x1, y1), (x1 + fill_w, y2),
                           fill=_alpha(LOL["gold"], 230),
                           color=(0, 0, 0, 0), rounding=2, parent=dl)
    if label:
        _text(dl, x1, y1 - 18, label, LOL["txt_dim"], 13)
    if show_pct:
        _text_centered(dl, (x1 + x2) // 2, y2 + 6,
                       f"{int(p * 100)}%",
                       _alpha(LOL["txt_dim"], 220), size=12)


# ---------------------------------------------------------------------------
# Player portrait frame (circular w/ tier-tinted gold ring)
# ---------------------------------------------------------------------------

def draw_player_portrait_frame(dl, cx, cy, radius, *,
                               tier="Unranked",
                               portrait_texture=None,
                               name=None):
    """Circular portrait frame at (cx, cy). Tier-tinted gold ring outside.
    If `portrait_texture` is a valid DPG texture tag, image is drawn inside;
    otherwise navy fill. `name` printed below at `cy + radius + 14` if given."""
    ring = LOL_TIER_RING.get(tier, LOL_TIER_RING["Unranked"])
    # Outer ring (filled, thick)
    dpg.draw_circle((cx, cy), radius + 4,
                    fill=_alpha(ring, 230),
                    color=(0, 0, 0, 0), parent=dl)
    # Inner navy backplate
    dpg.draw_circle((cx, cy), radius,
                    fill=LOL["navy_panel"],
                    color=_alpha(LOL["gold_rule"], 180),
                    thickness=1, parent=dl)
    # Portrait, if available — drawn as a square clipped by the circle.
    if portrait_texture and dpg.does_item_exist(portrait_texture):
        try:
            dpg.draw_image(portrait_texture,
                           (cx - radius * 0.85, cy - radius * 0.85),
                           (cx + radius * 0.85, cy + radius * 0.85),
                           parent=dl)
        except Exception:
            pass
    if name:
        _text_centered(dl, cx, cy + radius + 12, name,
                       LOL["txt"], size=14)


# ---------------------------------------------------------------------------
# Pick / ban chips
# ---------------------------------------------------------------------------

def draw_pick_chip(dl, x1, y1, x2, y2, champ_name, *,
                   role=None, side="BLUE", locked=True, ghost=False,
                   hot=False, splash=True):
    """A locked champion's pick chip — splash thumbnail (left) + name (right)
    + optional role glyph. `ghost=True` makes it translucent for the enemy
    probable-next-pick chip."""
    h = y2 - y1
    alpha = 110 if ghost else (245 if locked else 200)
    accent = SIDE_ACCENT.get(side, LOL["gold"])
    fill = _alpha(LOL["navy_panel"], alpha)
    border = _alpha(accent, 200 if (hot or locked) else 140)
    dpg.draw_rectangle((x1, y1), (x2, y2),
                       fill=fill, color=border, rounding=4,
                       thickness=2 if hot else 1, parent=dl)

    # Splash thumbnail on the left (square)
    if splash:
        thumb_w = h
        if _splash is not None and champ_name:
            try:
                tex = _splash.get_texture(champ_name)
            except Exception:
                tex = None
        else:
            tex = None
        if tex and dpg.does_item_exist(tex):
            try:
                dpg.draw_image(tex, (x1, y1), (x1 + thumb_w, y2), parent=dl)
            except Exception:
                tex = None
        # Always lay a dark overlay on the right portion of the thumbnail so
        # the text remains legible against the splash.
        dpg.draw_rectangle((x1, y1), (x1 + thumb_w, y2),
                           fill=_alpha(LOL["navy_deep"], 90),
                           color=(0, 0, 0, 0), parent=dl)
    text_x = x1 + (h + 10 if splash else 10)
    txt_color = _alpha(LOL["gold_lt"], alpha)
    if ghost:
        txt_color = _alpha(LOL["txt_dim"], 230)
    _text(dl, text_x, y1 + (h - 18) // 2, champ_name, txt_color, 18)

    if role:
        draw_role_glyph(dl, x2 - h + 6, y1 + 6, h - 12, role,
                        color=_alpha(accent, alpha))


def draw_ban_chip(dl, x1, y1, x2, y2, champ_name, *,
                  side="BLUE", strikethrough=True, hot=False):
    """A banned-champion chip. Dim navy with a diagonal strikethrough line
    in side accent color. Name reads in red_side tones."""
    accent = SIDE_ACCENT.get(side, LOL["gold"])
    dpg.draw_rectangle((x1, y1), (x2, y2),
                       fill=_alpha(LOL["navy_deep"], 230 if hot else 200),
                       color=_alpha(accent, 180 if hot else 110),
                       rounding=3, thickness=1, parent=dl)
    _text(dl, x1 + 8, y1 + (y2 - y1 - 16) // 2,
          champ_name, _alpha(LOL["txt_dim"], 230), 16)
    if strikethrough:
        dpg.draw_line((x1 + 2, y1 + 4), (x2 - 2, y2 - 4),
                      color=_alpha(LOL["loss"], 220), thickness=2,
                      parent=dl)


# ---------------------------------------------------------------------------
# Engine-signal badges
# ---------------------------------------------------------------------------

_SAMPLE_LABEL = {
    "thin":   ("thin",   "warning", "txt_dim"),
    "ok":     ("ok",     "gold",     "txt"),
    "strong": ("strong", "win",      "gold_lt"),
}


def draw_sample_size_badge(dl, x, y, confidence_label, *,
                            height=16, padding=6, font_size=11):
    """Tiny badge: 'thin' / 'ok' / 'strong' inline next to a suggestion.
    Returns the right edge X so callers can chain badges."""
    if confidence_label not in _SAMPLE_LABEL:
        return x
    label, fill_key, txt_key = _SAMPLE_LABEL[confidence_label]
    text = label.upper()
    w = padding * 2 + int(font_size * 0.6 * len(text))
    dpg.draw_rectangle((x, y), (x + w, y + height),
                       fill=_alpha(LOL[fill_key], 150),
                       color=_alpha(LOL[fill_key], 240),
                       rounding=3, parent=dl)
    _text(dl, x + padding, y + (height - font_size) // 2,
          text, LOL[txt_key], font_size)
    return x + w


_POOL_DEPTH_LABEL = {
    "DEEP":     ("DEEP",     "win",     "gold_lt"),
    "OK":       ("OK",       "gold",    "txt"),
    "SHALLOW":  ("SHALLOW",  "warning", "navy_deep"),
    "OFF-ROLE": ("OFF-ROLE", "loss",    "gold_lt"),
}


def draw_pool_depth_badge(dl, x, y, depth_label, *,
                          height=18, padding=7, font_size=12):
    """DEEP/OK/SHALLOW/OFF-ROLE badge on a team-builder slot. Returns the
    right edge X so callers can chain."""
    if depth_label not in _POOL_DEPTH_LABEL:
        return x
    label, fill_key, txt_key = _POOL_DEPTH_LABEL[depth_label]
    w = padding * 2 + int(font_size * 0.6 * len(label))
    dpg.draw_rectangle((x, y), (x + w, y + height),
                       fill=_alpha(LOL[fill_key], 170),
                       color=_alpha(LOL[fill_key], 240),
                       rounding=3, parent=dl)
    _text(dl, x + padding, y + (height - font_size) // 2,
          label, LOL[txt_key], font_size)
    return x + w


def draw_recent_form_dots(dl, x, y, results, *,
                          n=10, dot_size=6, gap=2):
    """Horizontal row of last `n` win/loss dots (gold for win, dim red for
    loss). Renders nothing when results is empty/None."""
    if not results:
        return x
    tail = list(results)[-n:]
    cx = x
    cy = y + dot_size // 2
    for r in tail:
        col = LOL["win"] if r else LOL["loss"]
        dpg.draw_circle((cx + dot_size // 2, cy), dot_size // 2,
                        fill=col, color=(0, 0, 0, 0), parent=dl)
        cx += dot_size + gap
    return cx


def draw_ghost_suggestion_chip(dl, x1, y1, x2, y2,
                                champ, role, confidence, *,
                                side="RED"):
    """Translucent chip rendered at an enemy's expected pick slot during
    their turn. Confidence affects opacity (more confident = more solid)."""
    alpha_factor = max(0.25, min(0.85, float(confidence)))
    alpha = int(255 * alpha_factor * 0.4)
    accent = SIDE_ACCENT.get(side, LOL["gold"])
    dpg.draw_rectangle((x1, y1), (x2, y2),
                       fill=_alpha(LOL["navy_panel"], alpha),
                       color=_alpha(accent, 160),
                       rounding=4, thickness=1, parent=dl)
    _text(dl, x1 + 10, y1 + 6, "ENEMY GHOST",
          _alpha(LOL["txt_faint"], 230), 11)
    _text(dl, x1 + 10, y1 + 22, champ or "?",
          _alpha(LOL["gold_lt"], int(255 * alpha_factor)), 18)
    _text(dl, x1 + 10, y1 + 46,
          f"{role}  ·  {int(confidence * 100)}% conf",
          _alpha(LOL["txt_dim"], 200), 12)


# ---------------------------------------------------------------------------
# Arc meter — win-probability gauge (180° sweep, blue on left, red on right)
# ---------------------------------------------------------------------------

def draw_arc_meter(dl, cx, cy, radius, blue_pct, *,
                   thickness=14, show_text=True):
    """Render a 180° win-probability arc. `blue_pct` is 0..100. Blue half
    fills from left, red half fills from right. Pointer in the middle
    shows BLUE 60% / RED 40% style label."""
    pct = max(0.0, min(100.0, float(blue_pct)))
    # 180° arc from 180° (left) → 360° (right), pointing upward.
    # Step-wise rendering with thin lines.
    steps = 60
    for i in range(steps):
        a0 = math.radians(180 + (i / steps) * 180)
        a1 = math.radians(180 + ((i + 1) / steps) * 180)
        # Inner + outer ring points
        p_share = (i + 0.5) / steps              # 0..1 (left→right)
        is_blue_zone = p_share <= (pct / 100.0)
        col = (LOL["blue_side"] if is_blue_zone else LOL["red_side"])
        col = _alpha(col, 225)
        # quad strip via two triangles approximated as a thin polyline
        x_o0 = cx + (radius) * math.cos(a0)
        y_o0 = cy + (radius) * math.sin(a0)
        x_o1 = cx + (radius) * math.cos(a1)
        y_o1 = cy + (radius) * math.sin(a1)
        x_i0 = cx + (radius - thickness) * math.cos(a0)
        y_i0 = cy + (radius - thickness) * math.sin(a0)
        x_i1 = cx + (radius - thickness) * math.cos(a1)
        y_i1 = cy + (radius - thickness) * math.sin(a1)
        dpg.draw_polygon([(x_o0, y_o0), (x_o1, y_o1),
                          (x_i1, y_i1), (x_i0, y_i0)],
                         fill=col, color=(0, 0, 0, 0), parent=dl)

    # Tick mark at 50% (top center)
    tip_x = cx
    tip_y = cy - radius - 4
    dpg.draw_line((tip_x, tip_y), (tip_x, cy - (radius - thickness) + 2),
                  color=_alpha(LOL["gold"], 180), thickness=2, parent=dl)

    if show_text:
        _text_centered(dl, cx, cy - 18, f"{int(round(pct))}%",
                       LOL["gold_lt"], size=34)
        _text_centered(dl, cx, cy + 6, "BLUE WIN", LOL["txt_dim"], 11)


# ---------------------------------------------------------------------------
# Archetype card — the 7-archetype pick screen tile
# ---------------------------------------------------------------------------

_VIABILITY_COLORS = {
    "STRONG":         "win",
    "VIABLE":         "gold",
    "WEAK":           "warning",
    "NOT RECOMMENDED": "loss",
}


def draw_archetype_card(dl, x1, y1, x2, y2, archetype_data, *,
                        hot=False, selected=False,
                        accent_side="BLUE"):
    """Render one archetype option card for the ARCHETYPE pick screen.

    `archetype_data` is an entry from `recommend_comps` (or `target_archetype`)
    with: archetype, label, viability, combined, picks (list of {champion,
    fit_score}), win_condition, spike, score_breakdown (with ap_ratio).
    """
    fill = LOL["navy_lt"] if (selected or hot) else LOL["navy_panel"]
    border_col = (LOL["gold"] if selected else
                  (LOL["gold_lt"] if hot else LOL["gold_rule"]))
    border_thickness = 3 if selected else (2 if hot else 1)
    draw_navy_panel(dl, x1, y1, x2, y2, fill=fill,
                    border_color=border_col,
                    border_thickness=border_thickness,
                    rounding=6)

    # Accent strip top
    strip_h = 6
    accent = SIDE_ACCENT.get(accent_side, LOL["gold"])
    dpg.draw_rectangle((x1 + 1, y1 + 1), (x2 - 1, y1 + strip_h),
                       fill=_alpha(accent, 200), color=(0, 0, 0, 0),
                       parent=dl)

    # Title (archetype name)
    label = str(archetype_data.get("label", archetype_data.get("archetype", "?")))
    _text(dl, x1 + 14, y1 + 14, label, LOL["gold_lt"], 20)

    # Viability tag
    viab = str(archetype_data.get("viability", ""))
    viab_color = LOL.get(_VIABILITY_COLORS.get(viab, "gold"), LOL["gold"])
    combined = archetype_data.get("combined", 0)
    tag_text = f"{viab}  {combined}"
    _text(dl, x1 + 14, y1 + 42, tag_text, _alpha(viab_color, 240), 14)

    # AP / AD damage profile bar
    sb = archetype_data.get("score_breakdown", {}) or {}
    ap_ratio = float(sb.get("ap_ratio", 0.5))
    bar_y = y1 + 66
    bar_h = 6
    bar_x1 = x1 + 14
    bar_x2 = x2 - 14
    bar_w = bar_x2 - bar_x1
    split = bar_x1 + int(bar_w * max(0.0, min(1.0, ap_ratio)))
    dpg.draw_rectangle((bar_x1, bar_y), (split, bar_y + bar_h),
                       fill=_alpha((180, 130, 220, 255), 200),
                       color=(0, 0, 0, 0), parent=dl)
    dpg.draw_rectangle((split, bar_y), (bar_x2, bar_y + bar_h),
                       fill=_alpha((200, 140, 100, 255), 200),
                       color=(0, 0, 0, 0), parent=dl)
    _text(dl, bar_x1, bar_y + 10,
          f"AP {int(ap_ratio * 100)}%   AD {int((1 - ap_ratio) * 100)}%",
          LOL["txt_dim"], 11)

    # Projected picks (5 champs in a row)
    picks_y = bar_y + 32
    picks = archetype_data.get("picks") or []
    chip_w = (x2 - x1 - 28) // 5
    chip_h = 24
    for i, p in enumerate(picks[:5]):
        cx_chip = x1 + 14 + i * chip_w
        champ = (p.get("champion") or "?")
        draw_navy_panel(dl, cx_chip, picks_y,
                        cx_chip + chip_w - 4, picks_y + chip_h,
                        fill=_alpha(LOL["navy_deep"], 240),
                        border_color=_alpha(accent, 140),
                        border_thickness=1,
                        rounding=3)
        _text(dl, cx_chip + 4, picks_y + 5, champ[:10],
              LOL["txt"], 12)

    # Win condition + spike (small text at bottom)
    wc = str(archetype_data.get("win_condition", ""))
    spike = str(archetype_data.get("spike", ""))
    _text(dl, x1 + 14, picks_y + chip_h + 12,
          f"→ {wc[:60]}", LOL["txt_dim"], 12)
    if spike:
        _text(dl, x1 + 14, picks_y + chip_h + 30,
              f"Spike: {spike[:50]}",
              _alpha(LOL["txt_faint"], 220), 11)


# ---------------------------------------------------------------------------
# Pivot alert banner — slide-down warning when archetype gets wrecked
# ---------------------------------------------------------------------------

def draw_pivot_alert_banner(dl, x1, y1, x2, y2,
                            archetype_name, reason, pivot_options,
                            *, severity=0.8):
    """Render a horizontal warning banner inside (x1,y1)-(x2,y2). The two
    pivot options become two buttons on the right; the caller hit-tests
    them externally (we return their rects)."""
    color_key = "warning" if severity < 0.85 else "loss"
    accent = LOL[color_key]
    draw_navy_panel(dl, x1, y1, x2, y2,
                    fill=_alpha(LOL["navy_lt"], 240),
                    border_color=accent,
                    border_thickness=2,
                    rounding=4)
    # Warning triangle on the left
    icon_x = x1 + 14
    icon_cy = (y1 + y2) // 2
    pts = [(icon_x, icon_cy - 13),
           (icon_x + 16, icon_cy + 12),
           (icon_x - 16, icon_cy + 12)]
    dpg.draw_polygon(pts, fill=_alpha(accent, 200),
                     color=(0, 0, 0, 0), parent=dl)
    _text(dl, icon_x - 3, icon_cy - 6, "!",
          LOL["navy_deep"], 16)
    # Reason text
    _text(dl, x1 + 50, y1 + 10,
          archetype_name or "Archetype", accent, 18)
    _text(dl, x1 + 50, y1 + 34, reason or "",
          LOL["txt"], 13)

    # Buttons — return their geometries so the caller can click-detect.
    btn_rects = []
    if pivot_options:
        bw = 130
        bh = 32
        by = (y1 + y2) // 2 - bh // 2
        bx = x2 - bw - 12
        for i, opt in enumerate(pivot_options[:2]):
            rx = bx - i * (bw + 8)
            draw_navy_panel(dl, rx, by, rx + bw, by + bh,
                            fill=_alpha(LOL["gold_dk"], 230),
                            border_color=LOL["gold"],
                            border_thickness=1, rounding=4)
            _text(dl, rx + 12, by + 7,
                  f"Pivot → {opt}", LOL["gold_lt"], 14)
            btn_rects.append((rx, by, rx + bw, by + bh, opt))
    return btn_rects
