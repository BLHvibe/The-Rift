"""
hotkeys.py — Phase 6: floating keyboard-shortcut reference.

Toggle with `?` (or Shift+/). A polished centered card lists every shortcut.
Esc closes. Render with `draw()` from the main loop; pass viewport-content
width/height. Click outside the card also closes.
"""
from __future__ import annotations

import time
import math
import dearpygui.dearpygui as dpg

from theme import C
from core.animations import anim
from ui import effects


# (chord, description) — keep aligned with the actual handlers in main.py.
SHORTCUTS = [
    ("1 – 9",      "Switch tabs (Home / Rankings / Draft / Scout / Inhouse / Tier List / Settings / Commands / Activity)"),
    ("Esc",        "Close the current overlay (profile, match detail, hotkeys, Wrapped)"),
    ("F1 / ?",     "Toggle this hotkeys overlay"),
    ("F11",        "Toggle fullscreen"),
    ("Mouse wheel","Scroll the current tab content"),
    ("Click name", "Open the player profile overlay (Home podium · Rankings names · etc.)"),
    ("Click match","Open match detail in Inhouse → History"),
]


class HotkeyOverlay:
    def __init__(self):
        self.is_open  = False
        self.frac     = 0.0
        self._toggle_lock = False

    def open(self):
        if self.is_open:
            return
        self.is_open = True
        anim.tween(0.0, 1.0, 220, "out_cubic",
                   on_update=lambda v: setattr(self, "frac", v))

    def close(self):
        if not self.is_open:
            return
        self.is_open = False
        anim.tween(self.frac, 0.0, 180, "out_cubic",
                   on_update=lambda v: setattr(self, "frac", v))

    def toggle(self):
        if self.is_open:
            self.close()
        else:
            self.open()


hotkeys = HotkeyOverlay()


def is_open():
    return hotkeys.is_open or hotkeys.frac > 0.02


def draw(dl, w, h):
    """Per-frame: handle the `?` / F1 toggle and Esc, then render if open.

    `?` requires Shift+/ which DPG sometimes mis-routes depending on keyboard
    layout — F1 is the always-on alternative. Either fires the toggle."""
    wants = False
    try:
        if dpg.is_key_down(dpg.mvKey_F1):
            wants = True
    except Exception:
        pass
    try:
        slash_down = dpg.is_key_down(dpg.mvKey_Slash)
        shift_down = (dpg.is_key_down(dpg.mvKey_LShift)
                      or dpg.is_key_down(dpg.mvKey_RShift)
                      or dpg.is_key_down(dpg.mvKey_Shift))
        if slash_down and shift_down:
            wants = True
    except Exception:
        pass
    if wants and not hotkeys._toggle_lock:
        hotkeys.toggle()
        hotkeys._toggle_lock = True
    elif not wants:
        hotkeys._toggle_lock = False

    if hotkeys.frac <= 0.01:
        return

    frac = hotkeys.frac
    # Dim backdrop
    dpg.draw_rectangle((0, 0), (w, h),
                       fill=(0, 0, 0, int(160 * frac)),
                       color=(0, 0, 0, 0), parent=dl)

    # Card
    card_w = min(620, max(360, w - 80))
    line_h = 26
    head_h = 64
    body_h = head_h + len(SHORTCUTS) * line_h + 48
    card_h = body_h
    cx1 = (w - card_w) // 2
    cy1 = (h - card_h) // 2
    cx2 = cx1 + card_w
    cy2 = cy1 + card_h
    # Drop shadow
    dpg.draw_rectangle((cx1 + 4, cy1 + 6), (cx2 + 4, cy2 + 6),
                       fill=(0, 0, 0, int(140 * frac)),
                       color=(0, 0, 0, 0), rounding=10, parent=dl)
    dpg.draw_rectangle((cx1, cy1), (cx2, cy2),
                       fill=(*C["panel"][:3], int(245 * frac)),
                       color=(*C["gold"][:3], int(230 * frac)),
                       rounding=10, thickness=1, parent=dl)
    # Header
    dpg.draw_rectangle((cx1, cy1), (cx2, cy1 + head_h),
                       fill=(*C["card_hover"][:3], int(220 * frac)),
                       color=(0, 0, 0, 0), rounding=10, parent=dl)
    dpg.draw_line((cx1 + 16, cy1 + head_h - 1), (cx2 - 16, cy1 + head_h - 1),
                  color=(*C["gold"][:3], int(220 * frac)), thickness=1, parent=dl)
    dpg.draw_text((cx1 + 22, cy1 + 16), "KEYBOARD SHORTCUTS",
                  color=(*C["gold_lt"][:3], int(255 * frac)),
                  size=20, parent=dl)
    dpg.draw_text((cx1 + 22, cy1 + 40), "Press ? again or Esc to close",
                  color=(*C["txt2"][:3], int(240 * frac)),
                  size=14, parent=dl)

    # Rows
    rx = cx1 + 22
    ry = cy1 + head_h + 12
    chord_col_w = 130
    for chord, desc in SHORTCUTS:
        # Key chord chip
        cw_ = max(70, len(chord) * 8 + 18)
        dpg.draw_rectangle((rx, ry), (rx + cw_, ry + 22),
                           fill=(*C["card"][:3], int(220 * frac)),
                           color=(*C["gold_dk"][:3], int(200 * frac)),
                           rounding=4, parent=dl)
        dpg.draw_text((rx + 9, ry + 4), chord,
                      color=(*C["gold_lt"][:3], int(245 * frac)),
                      size=13, parent=dl)
        # Description
        dpg.draw_text((rx + chord_col_w, ry + 4), desc,
                      color=(*C["txt"][:3], int(235 * frac)),
                      size=14, parent=dl)
        ry += line_h

    # Esc handled in main.py via edge-detected state.esc_pressed.
    # Click outside the card closes (cooperatively via state.click_consumed).
    from core.state import state as _st
    if hotkeys.is_open and dpg.is_mouse_button_clicked(0) and not _st.click_consumed:
        try:
            cw_pos = dpg.get_item_pos("content_win")
        except Exception:
            cw_pos = (0, 0)
        mouse = dpg.get_mouse_pos(local=False)
        vp = dpg.get_viewport_pos()
        mx = mouse[0] - vp[0] - cw_pos[0]
        my = mouse[1] - vp[1] - cw_pos[1]
        # Consume any click while the overlay is open so tabs underneath
        # don't fire on the same press.
        _st.click_consumed = True
        if not (cx1 <= mx <= cx2 and cy1 <= my <= cy2):
            hotkeys.close()
