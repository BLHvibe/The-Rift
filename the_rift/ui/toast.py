"""
toast.py — Phase 0a: unified toast / notification stack.

A single home for transient notifications, replacing the ad-hoc systems
scattered across the app (the inhouse "GAME LOGGED" card, the update-available
window, the tier-list submit flashes). Push from anywhere:

    from ui import toast
    toast.push("Logged 3 new games", kind="success")

and call toast.draw(dl, w, h) once per frame from the render loop, after the
tab content is drawn. Toasts fade in at the top-right of the content area,
stack, auto-dismiss after `duration` seconds, and dismiss on click. `kind` is
info / success / warn / error. An optional `action` callable runs on click.

Note: toasts render into the content drawlist, so on tabs that float their own
overlay window (Settings, Commands, Activity) they currently sit behind it —
acceptable for now; the tab-migration phase (0c) revisits those surfaces.
"""
import time
import dearpygui.dearpygui as dpg

from theme import C
from ui import audio

# kind -> (accent rgba, glyph)
_KIND = {
    "info":    (C["gold"],           "i"),
    "success": (C["win"],            "✓"),
    "warn":    ((220, 165, 70, 255), "!"),
    "error":   (C["loss"],           "✕"),
}

_CARD_W = 330
_MARGIN = 16
_GAP    = 10
_IN_MS  = 240.0
_OUT_MS = 260.0
_MAX    = 5
_WRAP   = 38

# Hit-test offsets — the content drawlist's origin in viewport coords. The
# sidebar is always collapsed (68) when the cursor is up at a top-right toast.
_SIDEBAR_W = 68
_TITLE_H   = 52


def _wrap(text, width):
    words, lines, cur = str(text).split(), [], ""
    for wd in words:
        if len(cur) + len(wd) + 1 <= width:
            cur = (cur + " " + wd).strip()
        else:
            if cur:
                lines.append(cur)
            cur = wd
    if cur:
        lines.append(cur)
    return lines or [""]


class _Toast:
    __slots__ = ("text", "title", "kind", "duration", "action",
                 "born", "lines", "h", "played")

    def __init__(self, text, title, kind, duration, action):
        self.text     = str(text)
        self.title    = title
        self.kind     = kind if kind in _KIND else "info"
        self.duration = max(1.0, float(duration))
        self.action   = action
        self.born     = time.monotonic()
        self.lines    = _wrap(self.text, _WRAP)[:3]
        self.h        = (22 if title else 0) + len(self.lines) * 18 + 26
        self.played   = False


_toasts = []


def push(text, kind="info", duration=4.0, title=None, action=None):
    """Queue a toast. Safe to call from any thread — only appends to a list;
    all rendering happens on the main thread in draw()."""
    _toasts.append(_Toast(text, title, kind, duration, action))
    if len(_toasts) > _MAX:
        del _toasts[0]


def clear():
    """Drop every toast immediately."""
    _toasts.clear()


def draw(dl, w, h):
    """Render the toast stack into content drawlist `dl`. `w`/`h` are the
    content-area size. Call once per frame after the tab content is drawn."""
    if not _toasts or not dpg.does_item_exist(dl):
        return
    now = time.monotonic()

    # Prune fully-expired toasts.
    current = list(_toasts)
    keep = [t for t in current
            if (now - t.born) * 1000.0 < t.duration * 1000.0 + _OUT_MS]
    if len(keep) != len(current):
        _toasts[:] = keep
        current = keep
    if not current:
        return

    clicked = dpg.is_mouse_button_clicked(0)
    if clicked:
        m  = dpg.get_mouse_pos(local=False)
        vp = dpg.get_viewport_pos()
        cx = m[0] - vp[0] - _SIDEBAR_W
        cy = m[1] - vp[1] - _TITLE_H
    else:
        cx = cy = -99999

    y   = _MARGIN
    hit = None
    for t in current:
        age = (now - t.born) * 1000.0
        if age < _IN_MS:
            p     = age / _IN_MS
            ease  = 1.0 - (1.0 - p) ** 3
            alpha = ease
            nudge = (1.0 - ease) * 14.0
        elif age < t.duration * 1000.0:
            alpha = 1.0
            nudge = 0.0
        else:
            p     = (age - t.duration * 1000.0) / _OUT_MS
            alpha = max(0.0, 1.0 - p)
            nudge = 0.0

        if not t.played:
            t.played = True
            try:
                audio.play_toast()
            except Exception:
                pass

        a = int(255 * alpha)
        if a > 4:
            x2 = w - _MARGIN
            x1 = x2 - _CARD_W
            ty = y + nudge
            _draw_card(dl, x1, ty, _CARD_W, t.h, t, a)
            if clicked and x1 <= cx <= x2 and ty <= cy <= ty + t.h:
                hit = t
        y += t.h + _GAP

    if hit is not None:
        if hit.action:
            try:
                hit.action()
            except Exception:
                pass
        hit.born = now - hit.duration   # fast-forward into the fade-out


def _draw_card(dl, x, y, w, h, t, a):
    accent, glyph = _KIND[t.kind]
    ac = accent[:3]
    # drop shadow
    dpg.draw_rectangle((x + 3, y + 5), (x + w + 3, y + h + 5),
                       fill=(0, 0, 0, int(a * 0.32)), color=(0, 0, 0, 0),
                       rounding=7, parent=dl)
    # body
    dpg.draw_rectangle((x, y), (x + w, y + h),
                       fill=(*C["card"][:3], a),
                       color=(*ac, int(a * 0.85)),
                       rounding=7, thickness=1, parent=dl)
    # accent stripe
    dpg.draw_rectangle((x, y + 6), (x + 4, y + h - 6),
                       fill=(*ac, a), color=(0, 0, 0, 0),
                       rounding=2, parent=dl)
    # glyph chip
    gx, gy = x + 28, y + 24
    dpg.draw_circle((gx, gy), 12, fill=(*ac, int(a * 0.20)),
                    color=(*ac, a), thickness=1, parent=dl)
    dpg.draw_text((gx - 4, gy - 9), glyph, color=(*ac, a),
                  size=16, parent=dl)
    # text block
    tx = x + 50
    cy = y + 13
    if t.title:
        dpg.draw_text((tx, cy), str(t.title).upper(),
                      color=(*C["gold_lt"][:3], a), size=15, parent=dl)
        cy += 22
    for ln in t.lines:
        dpg.draw_text((tx, cy), ln,
                      color=(*C["txt"][:3], int(a * 0.92)),
                      size=14, parent=dl)
        cy += 18
