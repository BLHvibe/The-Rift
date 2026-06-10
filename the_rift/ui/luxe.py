"""
luxe.py — V2 cinematic rendering kit.

DPG drawlists only give us flat rects, lines and images — every "flat
wireframe" complaint about the app traces back to that. This module closes
the gap the way game UIs do: a handful of pre-rendered grayscale/white
sprites (generated with PIL at startup, registered once as DPG textures)
that get tinted and 9-sliced at draw time:

    lux_glow     radial gaussian falloff   → glows, halos, bloom
    lux_vgrad    vertical alpha gradient   → scrims, sheens, edge lights
    lux_hgrad    horizontal alpha gradient → side scrims
    lux_panel    rounded rect w/ baked     → gradient card surfaces
                 luminance gradient          (9-sliced, tinted any color)
    lux_shadow   blurred rounded rect      → soft drop shadows (9-sliced)
    lux_vign     radial vignette           → cinematic edge darkening

plus lazily pre-rendered "lit" typography (gold-gradient Cinzel with a
soft glow) for ceremonial titles, cached per (text, px).

Everything is tint-parameterized: one white sprite serves every color.
Call ensure_textures() once after dpg.create_context(). All draw helpers
are stateless and safe to call every frame.
"""
from __future__ import annotations

import os
import sys

import dearpygui.dearpygui as dpg
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

_REG    = "luxe_tex_registry"
_built  = False
_titles = {}            # (text, px, style) -> (tag, w, h)

# Texture geometry constants (referenced by the 9-slice draw calls).
_PANEL_TEX   = 160      # lux_panel canvas size
_PANEL_CORNER = 44      # corner zone in texture px (radius 40 arc inside)
_SHADOW_TEX  = 256      # lux_shadow canvas size
_SHADOW_CORNER = 110    # corner zone in texture px

GOLD     = (200, 170, 110)
GOLD_LT  = (232, 213, 163)
GOLD_HOT = (255, 236, 190)


def _font_path(name="CinzelDecorative-Bold.ttf"):
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "fonts", name)


def _register(tag, img):
    if not dpg.does_item_exist(_REG):
        dpg.add_texture_registry(tag=_REG)
    w, h = img.size
    data = (np.asarray(img, dtype=np.float32) / 255.0).ravel().tolist()
    dpg.add_static_texture(w, h, data, tag=tag, parent=_REG)


def ensure_textures():
    """Build + register the sprite kit. Call once after create_context()."""
    global _built
    if _built or dpg.does_item_exist("lux_glow"):
        _built = True
        return

    # ── lux_glow — radial gaussian-ish falloff, white ──────────────────────
    N = 256
    yy, xx = np.mgrid[0:N, 0:N].astype(np.float32)
    d = np.sqrt((xx - N / 2) ** 2 + (yy - N / 2) ** 2) / (N / 2)
    a = np.clip(1.0 - d, 0.0, 1.0) ** 2.4
    img = np.zeros((N, N, 4), np.uint8)
    img[..., :3] = 255
    img[..., 3] = (a * 255).astype(np.uint8)
    _register("lux_glow", Image.fromarray(img))

    # ── lux_vgrad / lux_hgrad — alpha ramps, white ─────────────────────────
    H = 256
    ramp = np.linspace(255, 0, H).astype(np.uint8)
    v = np.zeros((H, 16, 4), np.uint8)
    v[..., :3] = 255
    v[..., 3] = ramp[:, None]
    _register("lux_vgrad", Image.fromarray(v))
    hgr = np.zeros((16, H, 4), np.uint8)
    hgr[..., :3] = 255
    hgr[..., 3] = ramp[None, :]
    _register("lux_hgrad", Image.fromarray(hgr))

    # ── lux_panel — rounded rect, baked vertical luminance gradient ───────
    P = _PANEL_TEX
    mask = Image.new("L", (P, P), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, P - 1, P - 1),
                                           radius=40, fill=255)
    lum = np.linspace(255, 198, P).astype(np.float32)   # lighter top
    panel = np.zeros((P, P, 4), np.uint8)
    panel[..., 0] = lum[:, None].astype(np.uint8)
    panel[..., 1] = lum[:, None].astype(np.uint8)
    panel[..., 2] = lum[:, None].astype(np.uint8)
    panel[..., 3] = np.asarray(mask, np.uint8)
    _register("lux_panel", Image.fromarray(panel))

    # ── lux_shadow — blurred black rounded rect ────────────────────────────
    S = _SHADOW_TEX
    sh = Image.new("L", (S, S), 0)
    ImageDraw.Draw(sh).rounded_rectangle((64, 64, S - 65, S - 65),
                                         radius=40, fill=255)
    sh = sh.filter(ImageFilter.GaussianBlur(26))
    shadow = np.zeros((S, S, 4), np.uint8)
    shadow[..., 3] = np.asarray(sh, np.uint8)
    _register("lux_shadow", Image.fromarray(shadow))

    # ── lux_vign — radial vignette, black ──────────────────────────────────
    V = 512
    yy, xx = np.mgrid[0:V, 0:V].astype(np.float32)
    d = np.sqrt((xx - V / 2) ** 2 + (yy - V / 2) ** 2) / (V / 2)
    a = np.clip((d - 0.35) / 0.65, 0.0, 1.0) ** 1.8
    vg = np.zeros((V, V, 4), np.uint8)
    vg[..., 3] = (a * 255).astype(np.uint8)
    _register("lux_vign", Image.fromarray(vg))

    _built = True


# ---------------------------------------------------------------------------
# Core draw helpers
# ---------------------------------------------------------------------------

def nine_slice(dl, tex, x1, y1, x2, y2, corner, tex_corner, tex_size,
               color=(255, 255, 255, 255)):
    """Draw `tex` into the rect with fixed-scale corners and stretched
    edges/center, so rounded corners and blur falloffs never distort."""
    w, h = x2 - x1, y2 - y1
    if w <= 0 or h <= 0:
        return
    c = int(min(corner, w / 2 - 1, h / 2 - 1))
    if c <= 2:
        dpg.draw_image(tex, (x1, y1), (x2, y2), color=color, parent=dl)
        return
    tc = tex_corner / tex_size
    xs = (x1, x1 + c, x2 - c, x2)
    ys = (y1, y1 + c, y2 - c, y2)
    us = (0.0, tc, 1.0 - tc, 1.0)
    for i in range(3):
        if xs[i + 1] <= xs[i]:
            continue
        for j in range(3):
            if ys[j + 1] <= ys[j]:
                continue
            dpg.draw_image(tex, (xs[i], ys[j]), (xs[i + 1], ys[j + 1]),
                           uv_min=(us[i], us[j]), uv_max=(us[i + 1], us[j + 1]),
                           color=color, parent=dl)


def glow(dl, cx, cy, r, color, alpha):
    """Soft radial glow centered at (cx, cy)."""
    if alpha <= 0 or r <= 0:
        return
    dpg.draw_image("lux_glow", (cx - r, cy - r), (cx + r, cy + r),
                   color=(*color[:3], int(alpha)), parent=dl)


def vfade(dl, x1, y1, x2, y2, color, alpha, solid="top"):
    """Vertical gradient scrim — opaque at `solid` edge, fading away."""
    if alpha <= 0 or x2 <= x1 or y2 <= y1:
        return
    uv = ((0, 0), (1, 1)) if solid == "top" else ((0, 1), (1, 0))
    dpg.draw_image("lux_vgrad", (x1, y1), (x2, y2),
                   uv_min=uv[0], uv_max=uv[1],
                   color=(*color[:3], int(alpha)), parent=dl)


def hfade(dl, x1, y1, x2, y2, color, alpha, solid="left"):
    """Horizontal gradient scrim — opaque at `solid` edge, fading away."""
    if alpha <= 0 or x2 <= x1 or y2 <= y1:
        return
    uv = ((0, 0), (1, 1)) if solid == "left" else ((1, 0), (0, 1))
    dpg.draw_image("lux_hgrad", (x1, y1), (x2, y2),
                   uv_min=uv[0], uv_max=uv[1],
                   color=(*color[:3], int(alpha)), parent=dl)


def shadow(dl, x1, y1, x2, y2, alpha=110, spread=18, drop=6):
    """Soft drop shadow under a card. Draw BEFORE the panel."""
    nine_slice(dl, "lux_shadow",
               x1 - spread, y1 - spread + drop, x2 + spread, y2 + spread + drop,
               corner=spread + 30, tex_corner=_SHADOW_CORNER,
               tex_size=_SHADOW_TEX,
               color=(255, 255, 255, int(alpha)))


def panel(dl, x1, y1, x2, y2, tint, corner=10,
          border=None, border_a=150, sheen=70):
    """Gradient card surface: 9-sliced rounded panel + optional gold top
    sheen + 1px border. `tint` is the surface color at the top edge."""
    nine_slice(dl, "lux_panel", x1, y1, x2, y2,
               corner=corner, tex_corner=_PANEL_CORNER, tex_size=_PANEL_TEX,
               color=(*tint[:3], tint[3] if len(tint) > 3 else 255))
    if sheen:
        vfade(dl, x1 + corner, y1 + 1, x2 - corner, y1 + 12,
              GOLD_HOT, sheen * 0.55, solid="top")
    if border:
        dpg.draw_rectangle((x1, y1), (x2, y2),
                           fill=(0, 0, 0, 0),
                           color=(*border[:3], int(border_a)),
                           rounding=corner, thickness=1, parent=dl)


def vignette(dl, x, y, w, h, alpha=140):
    """Cinematic edge darkening over a region."""
    if alpha <= 0:
        return
    dpg.draw_image("lux_vign", (x, y), (x + w, y + h),
                   color=(255, 255, 255, int(alpha)), parent=dl)


def hairline(dl, x1, y, x2, alpha=200, glow_h=10, glow_a=70, color=GOLD):
    """Gold rule with a soft under-glow — the broadcast edge light."""
    vfade(dl, x1, y + 1, x2, y + 1 + glow_h, color, glow_a, solid="top")
    dpg.draw_line((x1, y), (x2, y), color=(*color[:3], int(alpha)),
                  thickness=1, parent=dl)


# ---------------------------------------------------------------------------
# Lit typography — pre-rendered gradient + glow text for ceremonial titles
# ---------------------------------------------------------------------------

_STYLE_FONTS = {
    "gold":      "CinzelDecorative-Bold.ttf",
    "gold_raj":  "Rajdhani-Bold.ttf",
}


def lit_title(text, px, style="gold"):
    """Render `text` once with a vertical gold gradient and soft glow.
    Returns (texture_tag, w, h); draw at native size for crisp edges."""
    key = (text, int(px), style)
    if key in _titles:
        return _titles[key]
    try:
        font = ImageFont.truetype(_font_path(_STYLE_FONTS.get(style,
                                  _STYLE_FONTS["gold"])), int(px))
        probe = ImageDraw.Draw(Image.new("L", (4, 4)))
        bbox = probe.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        pad = max(14, int(px) // 3)
        W, H = tw + pad * 2, th + pad * 2

        mask = Image.new("L", (W, H), 0)
        ImageDraw.Draw(mask).text((pad - bbox[0], pad - bbox[1]),
                                  text, 255, font=font)
        m = np.asarray(mask, np.float32) / 255.0

        top = np.array([248, 232, 184], np.float32)
        mid = np.array([214, 180, 118], np.float32)
        bot = np.array([148, 110, 56],  np.float32)
        rows = np.linspace(0.0, 1.0, H, dtype=np.float32).reshape(H, 1, 1)
        grad = np.where(rows < 0.55,
                        top + (mid - top) * (rows / 0.55),
                        mid + (bot - mid) * ((rows - 0.55) / 0.45))
        rgb = np.broadcast_to(grad, (H, W, 3))

        out = np.zeros((H, W, 4), np.uint8)
        out[..., :3] = rgb.astype(np.uint8)
        out[..., 3]  = (m * 255).astype(np.uint8)
        txt_img = Image.fromarray(out)

        glow_mask = mask.filter(ImageFilter.GaussianBlur(max(2, px / 7)))
        glow_img = Image.new("RGBA", (W, H), (232, 198, 132, 0))
        glow_img.putalpha(glow_mask.point(lambda v: int(v * 0.55)))

        base = Image.alpha_composite(
            Image.new("RGBA", (W, H), (0, 0, 0, 0)), glow_img)
        base = Image.alpha_composite(base, txt_img)

        tag = f"lux_title_{abs(hash(key))}"
        _register(tag, base)
        _titles[key] = (tag, W, H)
    except Exception as e:                               # pragma: no cover
        print(f"[luxe] lit_title failed for {text!r}: {e}")
        _titles[key] = (None, 0, 0)
    return _titles[key]


def draw_lit_title(dl, x, y, text, px, style="gold", alpha=255):
    """Draw a lit title at native size, top-left anchored. Returns (w, h)."""
    tag, w, h = lit_title(text, px, style)
    if tag is None:
        dpg.draw_text((x, y), text, color=(*GOLD_LT, alpha), size=px,
                      parent=dl)
        return (len(text) * px // 2, px)
    dpg.draw_image(tag, (x, y), (x + w, y + h),
                   color=(255, 255, 255, int(alpha)), parent=dl)
    return (w, h)
