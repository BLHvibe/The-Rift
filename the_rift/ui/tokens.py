"""
tokens.py — Phase 0b: The Rift design system.

The single source of truth for the unified visual language — the LCS-broadcast
palette plus the spacing / radius / stroke / elevation / type scales every
surface snaps to. Phase 0c migrates the 8 tabs onto these tokens; once that is
done the legacy `theme.C` gold/dark palette is retired.

Usage:
    from ui.tokens import PAL, SPACE, RADIUS, TYPE, tier_color
    fill = PAL["panel"]
    pad  = SPACE["lg"]
"""

# ---------------------------------------------------------------------------
# Palette — LCS/LEC broadcast: deep navy (#0a1428) + sparing gold (#c8aa6e).
# Matches ui/lol_theme.py's LOL dict (the draft tool already ships this look);
# Phase 0c moves the rest of the app onto it, after which it is canonical.
# ---------------------------------------------------------------------------
PAL = {
    "bg":          (8,   14,  26, 255),   # app background — deepest
    "navy_deep":   (10,  20,  40, 255),   # #0a1428
    "navy_mid":    (12,  28,  55, 255),
    "panel":       (16,  36,  64, 255),   # card / panel fill
    "panel_hi":    (28,  56,  92, 255),   # hover / raised panel
    "rule":        (120, 90,  40, 255),   # #785a28 — thin gold rules
    "rule_dim":    (40,  54,  78, 255),   # neutral separators

    "gold":        (200, 170, 110, 255),  # #c8aa6e — primary accent
    "gold_lt":     (232, 213, 163, 255),  # bright text highlight
    "gold_dk":     (92,  69,  32, 255),   # button-dark fill

    "txt":         (240, 230, 210, 255),
    "txt_dim":     (160, 150, 130, 255),
    "txt_faint":   (100, 92,  78, 255),

    "win":         (110, 190, 140, 255),
    "loss":        (200, 90,  90, 255),
    "warn":        (220, 165, 70, 255),

    "blue":        (118, 168, 220, 255),  # team-blue accent
    "blue_dk":     (40,  80,  140, 255),
    "red":         (220, 100, 110, 255),  # team-red accent
    "red_dk":      (140, 40,  50, 255),

    "shadow":      (0,   0,   0,  120),
}

# Tier -> accent color (rank badges, portrait rings).
TIER = {
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
    "Unranked":    (80,   90,  105, 255),
}

# Spacing scale (px) — every gap / padding snaps to one of these.
SPACE = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24, "xxl": 32, "huge": 48}

# Corner radii (px).
RADIUS = {"sm": 3, "md": 6, "lg": 10, "xl": 14, "pill": 999}

# Border / stroke weights (px).
STROKE = {"hair": 1, "thin": 1.5, "thick": 2, "heavy": 3}

# Elevation — (shadow_alpha, offset_px) for layered surfaces.
ELEV = {
    "flat":   (0,   0),
    "raised": (90,  3),
    "float":  (120, 5),
    "modal":  (160, 8),
}

# Type scale — semantic name -> point size. Pair with the font keys the app
# already loads (Cinzel for display/headers, Rajdhani for body, Mono for data).
TYPE = {
    "display": 44,   # splash / hero
    "h1":      32,   # tab titles
    "h2":      24,   # section headers
    "title":   20,   # card titles
    "body":    16,   # default text
    "label":   14,   # field labels / chips
    "caption": 12,   # secondary detail
    "micro":   11,   # dense data
}


def tier_color(tier):
    """Accent color for a rank tier; falls back to Unranked."""
    return TIER.get(tier, TIER["Unranked"])


def alpha(rgba, a):
    """Return `rgba` with its alpha replaced by `a` (0-255)."""
    return (rgba[0], rgba[1], rgba[2], int(max(0, min(255, a))))


def mix(c1, c2, t):
    """Linear blend of two colors; t=0 -> c1, t=1 -> c2 (alpha blended too)."""
    t = max(0.0, min(1.0, t))
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(4))
