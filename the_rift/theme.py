"""
Direction A palette + Direction C rank badge fills.
Call setup_theme() once after dpg.create_context().
"""
import dearpygui.dearpygui as dpg

# ---------------------------------------------------------------------------
# Palette — Direction A
# ---------------------------------------------------------------------------
C = {
    "bg":          (5,   8,  13, 255),
    "panel":       (11,  19, 32, 255),
    "card":        (13,  30, 48, 255),
    "card_hover":  (18,  40, 62, 255),
    "gold":        (200, 168, 106, 255),
    "gold_lt":     (232, 213, 163, 255),
    "gold_dk":     (92,  69,  32, 255),
    "platinum":    (158, 180, 200, 255),
    "win":         (79,  168, 130, 255),
    "loss":        (184,  69,  53, 255),
    "rule_gold":   (70,  55,  20, 255),
    "rule_dark":   (44,  56,  78, 255),   # bumped from (26,35,53) for better separator contrast against bg
    "txt":         (216, 207, 186, 255),
    "txt2":        (122, 114,  99, 255),
    "txt_dim":     (70,  65,  55, 255),
    "rift_purple": (107,  47, 160, 255),
    # Splash flash
    "flash":       (13,  27,  42, 255),

    # -----------------------------------------------------------------------
    # Cyberpunk command-deck accents (v2.7 Draft Board revamp).
    # Gold above is demoted to "ceremonial" use (mastheads / non-board tabs).
    # Cyan = blue side, magenta = red side, on the Draft Board.
    # -----------------------------------------------------------------------
    "cy_lt":       (120, 230, 255, 255),   # electric cyan — hi-light edges, blue-side accent
    "cy":          (60,  195, 235, 255),   # cyan body — chip fills, dividers, gridlines
    "cy_dk":       (20,   90, 130, 255),   # cyan shadow / dim borders
    "mg_lt":       (255, 110, 220, 255),   # hot magenta — DANGER / opponent callouts
    "mg":          (220,  70, 175, 255),   # magenta body — red-side accent
    "mg_dk":       (110,  30,  90, 255),   # magenta shadow / dim borders
    "amb":         (255, 175,  60, 255),   # hot amber — warning / decision required
    "term_g":      (80,  255, 160, 255),   # terminal green — OK / SAFE / NOMINAL
    "alert_r":     (255,  65,  80, 255),   # alert red — hard error / contested ban
    "scan_gy":     (180, 200, 220, 255),   # scanline tint (drawn at very low alpha)
    "panel_dk":    (8,    12,  22, 255),   # deeper panel background
    "grid_a":      (40,   80, 110, 255),   # grid-cell line color (cool dim)
}

# Direction C — rank badge backgrounds
RANK_COLORS = {
    "Challenger": (200, 168, 106, 255),
    "Grandmaster":(200, 168, 106, 255),
    "Master":     (200, 168, 106, 255),
    "Diamond":    (58,  96, 168, 255),
    "Emerald":    (58, 173, 122, 255),
    "Platinum":   (74, 128, 144, 255),
    "Gold":       (160, 120,  40, 255),
    "Silver":     (138, 138, 154, 255),
    "Bronze":     (122,  74,  40, 255),
    "Iron":       (74,  56,  40, 255),
    "Unranked":   (40,  50,  65, 255),
}

# Medal particle colors (RGB for particle system)
MEDAL_PARTICLE = {
    1: (255, 215,   0),   # gold
    2: (232, 232, 232),   # silver
    3: (205, 127,  50),   # bronze
}

def _rgba(key, alpha_override=None):
    r, g, b, a = C[key]
    if alpha_override is not None:
        a = alpha_override
    return (r, g, b, a)

def _hex_to_dpg(hex_str, alpha=255):
    h = hex_str.lstrip("#")
    r, g, b = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
    return (r, g, b, alpha)


def setup_theme():
    """Apply the global DPG theme. Call once after create_context."""
    with dpg.theme() as global_theme:
        with dpg.theme_component(dpg.mvAll):
            # Window / child backgrounds
            dpg.add_theme_color(dpg.mvThemeCol_WindowBg,        C["bg"])
            dpg.add_theme_color(dpg.mvThemeCol_ChildBg,         C["panel"])
            dpg.add_theme_color(dpg.mvThemeCol_PopupBg,         C["card"])
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg,         C["card"])
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered,  C["card_hover"])
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive,   C["card_hover"])

            # Text
            dpg.add_theme_color(dpg.mvThemeCol_Text,            C["txt"])
            dpg.add_theme_color(dpg.mvThemeCol_TextDisabled,    C["txt_dim"])

            # Borders
            dpg.add_theme_color(dpg.mvThemeCol_Border,          C["rule_dark"])
            dpg.add_theme_color(dpg.mvThemeCol_BorderShadow,    (0,0,0,0))

            # Buttons (gold)
            dpg.add_theme_color(dpg.mvThemeCol_Button,          C["gold_dk"])
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered,   C["gold"])
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,    C["gold_lt"])

            # Header / selectable
            dpg.add_theme_color(dpg.mvThemeCol_Header,          C["card"])
            dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered,   C["card_hover"])
            dpg.add_theme_color(dpg.mvThemeCol_HeaderActive,    C["card_hover"])

            # Scrollbar
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarBg,     C["panel"])
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrab,   C["gold_dk"])
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrabHovered, C["gold"])
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrabActive,  C["gold_lt"])

            # Title bar (hidden for borderless but set anyway)
            dpg.add_theme_color(dpg.mvThemeCol_TitleBg,         C["bg"])
            dpg.add_theme_color(dpg.mvThemeCol_TitleBgActive,   C["panel"])

            # Separator
            dpg.add_theme_color(dpg.mvThemeCol_Separator,       C["rule_dark"])

            # Plot
            dpg.add_theme_color(dpg.mvThemeCol_PlotLines,       C["gold"])
            dpg.add_theme_color(dpg.mvThemeCol_PlotHistogram,   C["gold"])

            # Rounding & spacing
            dpg.add_theme_style(dpg.mvStyleVar_WindowRounding,     0.0)
            dpg.add_theme_style(dpg.mvStyleVar_ChildRounding,      6.0)
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding,      4.0)
            dpg.add_theme_style(dpg.mvStyleVar_GrabRounding,       4.0)
            dpg.add_theme_style(dpg.mvStyleVar_ScrollbarRounding,  4.0)
            dpg.add_theme_style(dpg.mvStyleVar_WindowBorderSize,   0.0)
            dpg.add_theme_style(dpg.mvStyleVar_ChildBorderSize,    1.0)
            dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing,        10.0, 8.0)
            dpg.add_theme_style(dpg.mvStyleVar_WindowPadding,      0.0, 0.0)
            dpg.add_theme_style(dpg.mvStyleVar_FramePadding,       8.0, 5.0)

    dpg.bind_theme(global_theme)
    return global_theme


def setup_fonts():
    """
    Load and register all fonts.
    Returns a dict of tag -> dpg font tag.
    """
    import os
    font_dir = os.path.join(os.path.dirname(__file__), "fonts")

    fonts = {}
    with dpg.font_registry():
        # Cinzel Decorative — splash + ceremonial headers (tab titles, panel titles)
        for size, key in [(52, "cinzel_52"), (44, "cinzel_44"), (36, "cinzel_36"),
                          (32, "cinzel_32"), (28, "cinzel_28"), (24, "cinzel_24"),
                          (22, "cinzel_22"), (20, "cinzel_20"), (18, "cinzel_18"),
                          (16, "cinzel_16"), (14, "cinzel_14")]:
            path = os.path.join(font_dir, "CinzelDecorative-Bold.ttf")
            if os.path.exists(path):
                fonts[key] = dpg.add_font(path, size)

        # JetBrains Mono Medium — data, codes, action labels, stat bands
        # (the cyberpunk command-deck type cue; Rajdhani stays the body font)
        for size, key in [(36, "mono_36"), (28, "mono_28"), (22, "mono_22"),
                          (18, "mono_18"), (16, "mono_16"), (14, "mono_14"),
                          (12, "mono_12"), (11, "mono_11")]:
            path = os.path.join(font_dir, "JetBrainsMono-Medium.ttf")
            if os.path.exists(path):
                fonts[key] = dpg.add_font(path, size)

        # Rajdhani Bold — screen headers, player names, numbers
        for size, key in [(72, "raj_72"), (56, "raj_56"), (44, "raj_44"),
                          (36, "raj_36"), (28, "raj_28"), (24, "raj_24"),
                          (20, "raj_20"), (18, "raj_18"), (16, "raj_16"),
                          (14, "raj_14"), (12, "raj_12")]:
            path = os.path.join(font_dir, "Rajdhani-Bold.ttf")
            if os.path.exists(path):
                fonts[key] = dpg.add_font(path, size)

        # Rajdhani SemiBold — tab labels, subheaders
        for size, key in [(26, "raj_sb_26"), (24, "raj_sb_24"), (22, "raj_sb_22"),
                          (20, "raj_sb_20"), (18, "raj_sb_18"), (16, "raj_sb_16"),
                          (14, "raj_sb_14"), (12, "raj_sb_12"), (11, "raj_sb_11")]:
            path = os.path.join(font_dir, "Rajdhani-SemiBold.ttf")
            if os.path.exists(path):
                fonts[key] = dpg.add_font(path, size)

        # Rajdhani Regular — supporting UI text
        for size, key in [(26, "raj_r_26"), (24, "raj_r_24"), (22, "raj_r_22"),
                          (20, "raj_r_20"), (18, "raj_r_18"), (16, "raj_r_16"),
                          (14, "raj_r_14"), (12, "raj_r_12"), (11, "raj_r_11")]:
            path = os.path.join(font_dir, "Rajdhani-Regular.ttf")
            if os.path.exists(path):
                fonts[key] = dpg.add_font(path, size)

    return fonts
