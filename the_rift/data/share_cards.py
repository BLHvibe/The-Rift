"""
share_cards.py — Phase 5c: render shareable PNG cards.

Pillow-based image generation for two flavors of stat card:
  - `make_player_card(name)` — player profile snapshot
  - `make_match_card(match_id)` — match-result summary

Both render into `the_rift/assets/share_cache/` and return the absolute file
path so the caller can copy it to clipboard, open it in a viewer, or attach
it to a Discord post manually. All data is read from `live.*` caches — no
extra fetches on the render hot path.

This module is deliberately UI-free: returns a path; the caller does the
toast / clipboard. Keep it portable so a future Discord-bot pass can call it
directly.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from typing import Optional, Tuple, List

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:                                             # pragma: no cover
    Image = None
    ImageDraw = None
    ImageFont = None

from data.reader import live


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def _here():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _out_dir():
    d = os.path.join(_here(), "assets", "share_cache")
    os.makedirs(d, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Palette (matches ui/tokens.PAL — LCS broadcast)
# ---------------------------------------------------------------------------

BG       = (8,   14,  26)
PANEL    = (16,  36,  64)
PANEL_HI = (28,  56,  92)
GOLD     = (200, 170, 110)
GOLD_LT  = (232, 213, 163)
GOLD_DK  = (92,  69,  32)
TXT      = (240, 230, 210)
TXT_DIM  = (160, 150, 130)
WIN      = (110, 190, 140)
LOSS     = (200,  90,  90)
BLUE     = (140, 175, 230)
RED      = (230, 145, 145)

CARD_W = 1080
CARD_H = 600


def _font(size: int, bold: bool = False):
    """Best-effort load of a system font. Falls back to PIL's default if none
    are available."""
    if ImageFont is None:
        return None
    candidates = []
    if bold:
        candidates += ["seguibl.ttf", "ariblk.ttf", "arialbd.ttf",
                       "DejaVuSans-Bold.ttf"]
    candidates += ["segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"]
    for fn in candidates:
        try:
            return ImageFont.truetype(fn, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _gradient_bg(draw, w, h):
    """Vertical navy gradient — deepest at top, navy_mid at the bottom."""
    top = (8, 14, 26)
    bot = (16, 36, 64)
    for y in range(h):
        t = y / max(1, h - 1)
        r = int(top[0] + (bot[0] - top[0]) * t)
        g = int(top[1] + (bot[1] - top[1]) * t)
        b = int(top[2] + (bot[2] - top[2]) * t)
        draw.line([(0, y), (w, y)], fill=(r, g, b))


def _gold_rule(draw, x1, y, x2, color=GOLD, thickness=2):
    draw.line([(x1, y), (x2, y)], fill=color, width=thickness)


def _stat_box(draw, x, y, w, h, label, value, accent=GOLD):
    draw.rectangle([(x, y), (x + w, y + h)],
                   fill=PANEL, outline=accent, width=1)
    draw.text((x + 14, y + 10), label.upper(),
              fill=TXT_DIM, font=_font(15, bold=True))
    draw.text((x + 14, y + 32), str(value),
              fill=GOLD_LT, font=_font(34, bold=True))


# ---------------------------------------------------------------------------
# Player card
# ---------------------------------------------------------------------------

def make_player_card(name: str) -> Optional[str]:
    if Image is None or not name:
        return None
    img = Image.new("RGBA", (CARD_W, CARD_H), BG)
    draw = ImageDraw.Draw(img)
    _gradient_bg(draw, CARD_W, CARD_H)

    # Top-bar accent
    draw.rectangle([(0, 0), (CARD_W, 6)], fill=GOLD)

    # Header — name
    name_font = _font(64, bold=True)
    draw.text((40, 36), str(name).upper(), fill=GOLD_LT, font=name_font)

    # Subline — rank/tier
    rank_pos = None
    tier = "Unranked"
    score = None
    for p in (live.rankings or []):
        if p.get("name") == name:
            rank_pos = p.get("rank") or p.get("position")
            tier = p.get("tier") or "Unranked"
            score = p.get("score")
            break
    parts = []
    if rank_pos: parts.append(f"#{rank_pos}")
    if tier:     parts.append(tier.upper())
    if score is not None: parts.append(f"{score} pts")
    if parts:
        draw.text((44, 124), "  ·  ".join(parts),
                  fill=TXT, font=_font(22, bold=True))

    _gold_rule(draw, 40, 168, CARD_W - 40)

    # 4-up stat grid from inhouse row
    ih_row = next((p for p in (live.inhouse or [])
                   if (p.get("player") or p.get("name")) == name), {}) or {}
    sc_row = next((p for p in (live.scout or [])
                   if (p.get("name") or p.get("player")) == name), {}) or {}

    games = ih_row.get("games") or sc_row.get("games_raw") or 0
    wins  = ih_row.get("wins")  or 0
    losses = ih_row.get("losses") or max(0, (games or 0) - (wins or 0))
    try:
        wr = (wins / games * 100.0) if games else 0
    except Exception:
        wr = 0
    kda = ih_row.get("kda") or sc_row.get("kda") or 0
    try:
        kda_str = f"{float(kda):.2f}"
    except Exception:
        kda_str = str(kda)

    box_w = (CARD_W - 40 * 5) // 4
    by = 192
    bh = 88
    _stat_box(draw, 40 + 0 * (box_w + 20), by, box_w, bh,
              "GAMES", str(int(games or 0)))
    _stat_box(draw, 40 + 1 * (box_w + 20), by, box_w, bh,
              "RECORD", f"{wins}-{losses}")
    _stat_box(draw, 40 + 2 * (box_w + 20), by, box_w, bh,
              "WIN RATE", f"{int(wr)}%",
              accent=(WIN if wr >= 55 else (LOSS if wr <= 45 else GOLD)))
    _stat_box(draw, 40 + 3 * (box_w + 20), by, box_w, bh,
              "KDA", kda_str)

    # Top champs row
    champs = (live.inhouse_champs.get(name) or [])[:5]
    cy = 318
    draw.text((40, cy), "TOP CHAMPIONS",
              fill=GOLD, font=_font(18, bold=True))
    cy += 32
    if not champs:
        draw.text((40, cy), "No champion data yet.",
                  fill=TXT_DIM, font=_font(15))
    else:
        col_w = (CARD_W - 80) // 5
        for i, ch in enumerate(champs):
            cx = 40 + i * col_w
            draw.rectangle([(cx, cy), (cx + col_w - 12, cy + 100)],
                           fill=PANEL, outline=GOLD_DK, width=1)
            cn = str(ch.get("champ") or ch.get("name") or "—")
            draw.text((cx + 14, cy + 12), cn[:14],
                      fill=GOLD_LT, font=_font(18, bold=True))
            gg = ch.get("games") or 0
            wrc = ch.get("wr")
            try:
                wrf = float(str(wrc).replace("%", "")) if wrc is not None else None
            except Exception:
                wrf = None
            draw.text((cx + 14, cy + 38),
                      f"{int(gg)} GP",
                      fill=TXT_DIM, font=_font(13))
            wcol = (WIN if (wrf or 0) >= 55 else
                    (LOSS if (wrf or 0) > 0 and (wrf or 0) <= 45 else TXT))
            draw.text((cx + 14, cy + 56),
                      f"{int(wrf)}%" if wrf is not None else "—",
                      fill=wcol, font=_font(20, bold=True))

    # Footer — branding
    draw.text((40, CARD_H - 44), "THE RIFT",
              fill=GOLD, font=_font(16, bold=True))
    ts = datetime.now().strftime("%b %d %Y").upper()
    tb = draw.textbbox((0, 0), ts, font=_font(14))
    tw = tb[2] - tb[0]
    draw.text((CARD_W - 40 - tw, CARD_H - 44), ts,
              fill=TXT_DIM, font=_font(14))

    fname = f"player_{_safe(name)}_{int(datetime.now().timestamp())}.png"
    path = os.path.join(_out_dir(), fname)
    img.save(path)
    return path


# ---------------------------------------------------------------------------
# Match card
# ---------------------------------------------------------------------------

def make_match_card(match_id: str) -> Optional[str]:
    if Image is None or not match_id:
        return None
    m = next((mm for mm in (live.match_history or [])
              if mm.get("id") == match_id), None)
    if not m:
        return None

    img = Image.new("RGBA", (CARD_W, CARD_H), BG)
    draw = ImageDraw.Draw(img)
    _gradient_bg(draw, CARD_W, CARD_H)

    winner = (m.get("winner") or "").lower()
    accent = BLUE if winner == "blue" else (RED if winner == "red" else GOLD)
    draw.rectangle([(0, 0), (CARD_W, 8)], fill=accent)

    # Title
    title = "INHOUSE GAME"
    draw.text((40, 28), title, fill=GOLD, font=_font(20, bold=True))

    # Winner banner
    wlabel = ("BLUE TEAM WINS" if winner == "blue"
              else ("RED TEAM WINS" if winner == "red" else "RESULT UNKNOWN"))
    draw.text((40, 60), wlabel, fill=accent, font=_font(48, bold=True))

    # Subline
    ts = m.get("started_at") or ""
    dur = int(m.get("duration") or 0)
    dur_s = f"{dur//60}:{dur%60:02d}" if dur else "—"
    sub = f"{ts[:16].replace('T', ' ')}  ·  {dur_s}  ·  {(m.get('source') or '').upper()}"
    draw.text((40, 124), sub, fill=TXT_DIM, font=_font(16))

    _gold_rule(draw, 40, 162, CARD_W - 40)

    # Two-team scoreboard
    parts = m.get("participants") or []
    blue = [p for p in parts if (p.get("team") or "").lower() == "blue"]
    red  = [p for p in parts if (p.get("team") or "").lower() == "red"]

    def _team_block(x, y, w, h, side_label, side_col, rows):
        draw.rectangle([(x, y), (x + w, y + h)],
                       fill=PANEL, outline=side_col, width=1)
        draw.rectangle([(x, y), (x + 6, y + h)], fill=side_col)
        draw.text((x + 18, y + 12), side_label, fill=side_col,
                  font=_font(20, bold=True))
        for i, p in enumerate(rows[:5]):
            ry = y + 50 + i * 38
            role = (p.get("role") or "").upper()[:3]
            champ = str(p.get("champion") or "?")[:12]
            plyr  = str(p.get("player")   or "—")[:14]
            k = int(p.get("kills",   0))
            d = int(p.get("deaths",  0))
            a = int(p.get("assists", 0))
            draw.text((x + 18,  ry),     role,
                      fill=TXT_DIM, font=_font(14, bold=True))
            draw.text((x + 56,  ry),     champ,
                      fill=GOLD_LT, font=_font(16, bold=True))
            draw.text((x + 196, ry),     plyr,
                      fill=TXT, font=_font(15))
            draw.text((x + w - 110, ry), f"{k}/{d}/{a}",
                      fill=TXT, font=_font(16, bold=True))

    block_w = (CARD_W - 60) // 2
    block_h = 280
    by = 184
    _team_block(20, by, block_w, block_h, "BLUE", BLUE, blue)
    _team_block(40 + block_w, by, block_w, block_h, "RED", RED, red)

    # Footer
    draw.text((40, CARD_H - 44), "THE RIFT",
              fill=GOLD, font=_font(16, bold=True))
    mid_short = str(match_id)[-12:]
    draw.text((CARD_W - 220, CARD_H - 44),
              f"ID  {mid_short}",
              fill=TXT_DIM, font=_font(14))

    fname = f"match_{_safe(match_id)}.png"
    path = os.path.join(_out_dir(), fname)
    img.save(path)
    return path


def _safe(s):
    return "".join(c for c in str(s) if c.isalnum() or c in "._-")[:40]


# ---------------------------------------------------------------------------
# Clipboard helper — best-effort copy of the file path to clipboard.
# ---------------------------------------------------------------------------

def copy_path_to_clipboard(path: str) -> bool:
    try:
        if sys.platform.startswith("win"):
            import subprocess
            subprocess.run(["clip"], input=str(path), text=True,
                           encoding="utf-8", check=True)
            return True
        if sys.platform == "darwin":
            import subprocess
            subprocess.run(["pbcopy"], input=str(path), text=True,
                           encoding="utf-8", check=True)
            return True
        # Linux — try xclip / xsel
        import subprocess
        for cmd in (["xclip", "-selection", "clipboard"],
                    ["xsel", "-b", "-i"]):
            try:
                subprocess.run(cmd, input=str(path), text=True,
                               encoding="utf-8", check=True)
                return True
            except FileNotFoundError:
                continue
    except Exception:
        pass
    return False
