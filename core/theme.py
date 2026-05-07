"""Visual constants — color palette, roles, animation timings."""

C = {
    # Surfaces (deeper, slightly bluer)
    "bg":       "#06090f",
    "panel":    "#0c1422",
    "panel_2":  "#101a2b",   # alternating row bg
    "card":     "#0a2230",
    "strip":    "#091324",   # table column-header strip
    "tile":     "#0d1a2a",   # overview stat tiles
    "input":    "#13192a",
    "hover":    "#16314f",
    "active":   "#0e3a5a",

    # Brand — refined gold (warmer highlights, deeper shadows)
    "gold":     "#c8a86a",
    "gold_lt":  "#f3e6c4",
    "gold_dk":  "#6e5424",
    "gold_br":  "#d4b06e",

    # `rule` is the warm brown-gold separator color used in place
    # of the cool grey border.
    "rule":     "#3a2d12",

    # Status / accents
    "blue":     "#5fa8c9",
    "blue_lt":  "#5fb89a",
    "blue_dk":  "#0e3a5a",
    "red":      "#c84b31",
    "red_dk":   "#5a1c12",
    "teal":     "#5fb89a",

    # Text
    "txt":      "#e6dec7",
    "txt2":     "#9a9078",
    "txt_dim":  "#564f3e",
    "txt_dk":   "#06090f",

    # Borders
    "border":   "#3a2d12",
    "brd_gold": "#463714",
    "brd_act":  "#c8a86a",

    "green":    "#0ACF83",
    "purple":   "#9B59B6",

    # Team sides
    "team_blue": "#0a223a",
    "team_red":  "#2a0a0a",
}

ROLES = ["Top", "Jungle", "Mid", "Bot", "Support"]

# Rankings animation timings (ms)
ANIM_ROW_REVEAL_MS = 45
ANIM_PODIUM_CENTER_MS = 60
ANIM_PODIUM_SIDES_OFFSET_MS = 360
ANIM_PODIUM_STAGGER_MS = 220
