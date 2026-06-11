"""
Rankings Tab — Phase 2.
Podium layout mirrors old launcher: #2 left / #1 center (raised) / #3 right.
Reveal order: #1 first with max fanfare → #2 → #3 → #4–#10 → #11+
All layout is computed dynamically from the actual content area each frame.
"""
import math, time, random as _rnd
import dearpygui.dearpygui as dpg
from theme import C, RANK_COLORS, MEDAL_PARTICLE
from data.tips import TIPS as _TIPS
from data.config import load_rank_snapshot, save_rank_snapshot
from core.state import state
from core.animations import anim, ParticleSystem, Ripple
from ui import effects
from ui import luxe

# ---------------------------------------------------------------------------
# Fixed aesthetic constants (not dependent on screen size)
# ---------------------------------------------------------------------------
OUTER_PAD   = 32
COL_GAP     = 16
TOP_PAD     = 36

HERO_H      = 280   # #1 card height
SIDE_H      = 210   # #2/#3 card height
SIDE_OFFSET = 50    # #2/#3 sit this many px lower than #1

ACCENT_H    = 4
CORNER_ARM  = 18
CHAL_H      = 72
CHAL_GAP    = 8
CHAL_PAD_T  = 32
ROW_H       = 52
ROW_GAP     = 4
SECTION_GAP = 36

# Reveal delays (ms)
DELAY_BEFORE_1    = 600
DELAY_1_TO_2      = 1800
DELAY_2_TO_3      = 1400
DELAY_3_TO_CHAL   = 900
DELAY_CHAL_EACH   = 280
DELAY_CHAL_TO_REST= 400
DELAY_REST_EACH   = 55

# ---------------------------------------------------------------------------
# Dynamic layout — recomputed every frame from actual content area.
# Seeded with safe defaults for a typical viewport so the reveal-tween
# callbacks (`_card_center` → `_col_x`) never KeyError when they fire before
# the user has visited the Rankings tab (e.g. now that HOME is the default).
# `_compute_layout()` overwrites these on the first real draw.
# ---------------------------------------------------------------------------
_DEFAULT_CONTENT_W = 1212   # 1280 - 68 (sidebar)
_DEFAULT_CONTENT_H = 642    # 720 - 52 (titlebar) - 26 (ticker)
_DEFAULT_INNER_W   = _DEFAULT_CONTENT_W - OUTER_PAD * 2
_DEFAULT_COL_W     = (_DEFAULT_INNER_W - COL_GAP * 2) // 3
_L = {
    "content_w":  _DEFAULT_CONTENT_W,
    "content_h":  _DEFAULT_CONTENT_H,
    "inner_w":    _DEFAULT_INNER_W,
    "col_w":      _DEFAULT_COL_W,
    "hero_top":   TOP_PAD,
    "side_top":   TOP_PAD + SIDE_OFFSET,
    "podium_bot": TOP_PAD + SIDE_OFFSET + SIDE_H,
}
_name_hitboxes = []   # [(x1, y1, x2, y2, player_name), ...] rebuilt each frame

def _compute_layout(content_w, content_h):
    inner_w = content_w - OUTER_PAD * 2
    col_w   = (inner_w - COL_GAP * 2) // 3
    hero_top  = TOP_PAD
    side_top  = TOP_PAD + SIDE_OFFSET
    podium_bot = side_top + SIDE_H
    _L.update(dict(
        content_w  = content_w,
        content_h  = content_h,
        inner_w    = inner_w,
        col_w      = col_w,
        hero_top   = hero_top,
        side_top   = side_top,
        podium_bot = podium_bot,
    ))

def _col_x(col):
    """Left edge of column 0/1/2."""
    return OUTER_PAD + col * (_L["col_w"] + COL_GAP)


# ---------------------------------------------------------------------------
# Reveal state machine
# ---------------------------------------------------------------------------
class RankRevealPhase:
    IDLE               = "idle"
    LOADING            = "loading"
    CARDS_HIDDEN       = "cards_hidden"
    REVEAL_1           = "reveal_1"
    REVEAL_2           = "reveal_2"
    REVEAL_3           = "reveal_3"
    REVEAL_CHALLENGERS = "reveal_challengers"
    REVEAL_REST        = "reveal_rest"
    DONE               = "done"


class RankingsState:
    def __init__(self):
        self.phase       = RankRevealPhase.IDLE
        self.data        = []
        self.flash_alpha = 0

        self.card_y_off  = {}
        self.card_alpha  = {}
        self.card_x_off  = {}

        self.particles   = []
        self.ripples     = []
        self.shimmer_t   = 0.0

        self._chal_idx   = 0
        self._rest_idx   = 0
        self._load_t     = 0.0
        self._tip        = _rnd.choice(_TIPS)
        # {player_name: delta_int} — positive = moved up since last snapshot,
        # negative = moved down, 0 = same, None = new this snapshot.
        self.deltas      = {}

    def reset(self):
        self.__init__()

    def tick(self):
        self.shimmer_t += 0.007
        self._load_t   += 0.04

    def begin_loading(self):
        self.phase = RankRevealPhase.LOADING

    def begin_reveal(self, data):
        self.data  = data
        self.phase = RankRevealPhase.CARDS_HIDDEN
        for i in range(1, len(data) + 1):
            self.card_y_off[i] = 0
            self.card_alpha[i] = 0
            self.card_x_off[i] = -80
        # Compute movement deltas vs the last persisted snapshot, then save the
        # current ranks for next launch.  Positive delta = climbed (lower rank
        # number).  Players not in the prior snapshot get delta=None ("NEW").
        prev = load_rank_snapshot()
        cur  = {}
        deltas = {}
        for idx, p in enumerate(data, start=1):
            name = p.get("name")
            if not name:
                continue
            cur[name] = idx
            if name in prev:
                deltas[name] = prev[name] - idx   # +N = improved
            else:
                deltas[name] = None
        self.deltas = deltas
        save_rank_snapshot(cur)
        anim.tween(0, 1, 1, "linear", delay_ms=DELAY_BEFORE_1,
                   on_done=self._slam_1)

    # ---------------------------------------------------------------- slams

    def _slam_1(self):
        self.phase = RankRevealPhase.REVEAL_1
        self._slam(1, dist=100, is_hero=True,
                   on_done=lambda: anim.tween(0, 1, 1, "linear",
                                              delay_ms=DELAY_1_TO_2,
                                              on_done=self._slam_2))

    def _slam_2(self):
        self.phase = RankRevealPhase.REVEAL_2
        self._slam(2, dist=70,
                   on_done=lambda: anim.tween(0, 1, 1, "linear",
                                              delay_ms=DELAY_2_TO_3,
                                              on_done=self._slam_3))

    def _slam_3(self):
        self.phase = RankRevealPhase.REVEAL_3
        self._slam(3, dist=70,
                   on_done=lambda: anim.tween(0, 1, 1, "linear",
                                              delay_ms=DELAY_3_TO_CHAL,
                                              on_done=self._start_challengers))

    def _slam(self, rank, dist, on_done, is_hero=False):
        self.card_y_off[rank] = -dist
        count  = 55 if is_hero else 28
        spread = 150 if is_hero else 110
        color  = MEDAL_PARTICLE[rank]

        def _y(v): self.card_y_off[rank] = int(v)
        def _a(v): self.card_alpha[rank]  = int(v)

        def _impact():
            cx, cy = self._card_center(rank)
            self.particles.append(
                ParticleSystem(cx, cy, color, count=count,
                               spread=spread, lifetime_ms=1000, size=8))
            r1 = Ripple(cx, cy, color,
                        max_radius=240 if is_hero else 180,
                        duration_ms=600, thickness=2)
            self.ripples.append(r1)
            if is_hero:
                r2 = Ripple(cx, cy, color, max_radius=360,
                            duration_ms=800, thickness=1)
                import time as _t
                r2._start = _t.monotonic() * 1000 + 80
                self.ripples.append(r2)
                anim.tween(70, 0, 250, "out_cubic",
                           on_update=lambda v: setattr(self, "flash_alpha", int(v)))
            if on_done:
                on_done()

        anim.tween(-dist, 0, 360, "elastic_out", on_update=_y, on_done=_impact)
        anim.tween(0,    255, 220, "out_cubic",  on_update=_a)

    # ---------------------------------------------------------- challengers

    def _start_challengers(self):
        self.phase     = RankRevealPhase.REVEAL_CHALLENGERS
        self._chal_idx = 0
        self._next_challenger()

    def _next_challenger(self):
        ranks = list(range(4, 11))
        if self._chal_idx >= len(ranks):
            anim.tween(0, 1, 1, "linear", delay_ms=DELAY_CHAL_TO_REST,
                       on_done=self._start_rest)
            return
        rank = ranks[self._chal_idx]

        def _x(v): self.card_x_off[rank] = int(v)
        def _a(v): self.card_alpha[rank]  = int(v)
        def _next():
            self._chal_idx += 1
            anim.tween(0, 1, 1, "linear", delay_ms=DELAY_CHAL_EACH,
                       on_done=self._next_challenger)

        anim.tween(-80, 0,   260, "out_cubic", on_update=_x)
        anim.tween(0,   255, 260, "out_cubic", on_update=_a, on_done=_next)

    # --------------------------------------------------------------- rest

    def _start_rest(self):
        self.phase      = RankRevealPhase.REVEAL_REST
        self._rest_idx  = 0
        self._next_rest()

    def _next_rest(self):
        rest_ranks = list(range(11, len(self.data) + 1))
        if self._rest_idx >= len(rest_ranks):
            self.phase = RankRevealPhase.DONE
            return
        rank = rest_ranks[self._rest_idx]

        def _x(v): self.card_x_off[rank] = int(v)
        def _a(v): self.card_alpha[rank]  = int(v)
        def _next():
            self._rest_idx += 1
            self._next_rest()

        anim.tween(-80, 0,   220, "out_cubic", on_update=_x)
        anim.tween(0,   255, 220, "out_cubic", on_update=_a, on_done=_next)

    # --------------------------------------------------------------- util

    def _card_center(self, rank):
        # Use _L if populated, fall back to safe defaults
        col_w     = _L.get("col_w", 390)
        hero_top  = _L.get("hero_top", TOP_PAD)
        side_top  = _L.get("side_top", TOP_PAD + SIDE_OFFSET)
        podium_bot= _L.get("podium_bot", side_top + SIDE_H)
        if rank == 1:
            return _col_x(1) + col_w // 2, hero_top + HERO_H // 2
        if rank == 2:
            return _col_x(0) + col_w // 2, side_top + SIDE_H // 2
        if rank == 3:
            return _col_x(2) + col_w // 2, side_top + SIDE_H // 2
        y = podium_bot + CHAL_PAD_T + (rank - 4) * (CHAL_H + CHAL_GAP) + CHAL_H // 2
        return _L.get("content_w", 1232) // 2, y


# Module singleton
rankings = RankingsState()

# Font reference set by main at startup
_F = {}
def set_fonts(f): global _F; _F = f

# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------

def _accent_corners(dl, x1, y1, x2, y2, color, arm=CORNER_ARM, thickness=1.5):
    for pts in [
        [(x1, y1+arm), (x1, y1), (x1+arm, y1)],
        [(x2-arm, y1), (x2, y1), (x2, y1+arm)],
        [(x1, y2-arm), (x1, y2), (x1+arm, y2)],
        [(x2-arm, y2), (x2, y2), (x2, y2-arm)],
    ]:
        dpg.draw_polyline(pts, color=color, thickness=thickness, parent=dl)


def _hex(dl, cx, cy, r, fill, border, label="?", alpha=255):
    pts = [(cx + r*math.cos(math.pi/6 + i*math.pi/3),
            cy + r*math.sin(math.pi/6 + i*math.pi/3)) for i in range(6)]
    dpg.draw_polygon(pts, fill=(*fill[:3], alpha),
                     color=(*border[:3], alpha), thickness=1.5, parent=dl)
    dpg.draw_text((cx - len(label)*3 - 1, cy - 6), label,
                  color=(*C["txt"][:3], alpha), size=17, parent=dl)


def _avatar_or_hex(dl, cx, cy, r, raw_name, fill, border, label="?", alpha=255):
    """Draw the player's uploaded pfp (hex-cropped) if available, otherwise _hex.
    The image is already hex-cropped with transparent pixels, so no extra clipping needed."""
    try:
        from ui.inhouse import _get_avatar_tex
        tex = _get_avatar_tex(raw_name)
    except Exception:
        tex = None
    if tex:
        # draw_image doesn't support a color/alpha tint — but _avatar_or_hex is
        # only called when al > 0 (cards with al<=0 are skipped before we get here),
        # so the image will always be at a visible stage of the fade-in.
        try:
            dpg.draw_image(tex, (cx - r, cy - r), (cx + r, cy + r), parent=dl)
        except Exception:
            _hex(dl, cx, cy, r, fill, border, label, alpha)
    else:
        _hex(dl, cx, cy, r, fill, border, label, alpha)


_RATING_COLORS = {
    "S": (210, 40,  40,  255),
    "A": (200, 155, 60,  255),
    "B": (160, 136, 78,  255),
    "C": ( 92, 138, 92,  255),
    "D": ( 92, 122, 156, 255),
    "F": ( 90,  90, 90,  255),
}

def _badge(dl, cx, cy, abbr, tier, alpha=255, r=28):
    bc  = _RATING_COLORS.get(abbr) or RANK_COLORS.get(tier, RANK_COLORS["Unranked"])
    dpg.draw_circle((cx, cy), r, fill=(*bc[:3], alpha),
                    color=(*C["bg"][:3], int(alpha*0.6)), thickness=2, parent=dl)
    fs  = max(12, int(r * 0.72))
    off = len(abbr) * int(fs * 0.32)
    dpg.draw_text((cx - off, cy - fs//2), abbr,
                  color=(*C["bg"][:3], alpha), size=fs, parent=dl)


def _shimmer(dl, x1, y1, x2, y2, t, alpha=45):
    w   = x2 - x1
    pos = int((t % 1.0) * (w + 80)) - 40
    sx1, sx2 = max(x1, x1+pos-22), min(x2, x1+pos+22)
    if sx2 > sx1:
        dpg.draw_rectangle((sx1,y1),(sx2,y2),
                           fill=(*C["gold_lt"][:3], alpha),
                           color=(0,0,0,0), parent=dl)


def _mystery(dl, x1, y1, x2, y2, t, alpha=255):
    dpg.draw_rectangle((x1,y1),(x2,y2),
                        fill=(*C["card"][:3], alpha),
                        color=(*C["rule_dark"][:3], alpha),
                        rounding=4, parent=dl)
    _shimmer(dl, x1, y1, x2, y2, t)
    cx, cy = (x1+x2)//2, (y1+y2)//2
    dpg.draw_text((cx-5, cy-8), "?",
                  color=(*C["gold_dk"][:3], alpha), size=17, parent=dl)


def _txt(dl, x, y, text, color, size, font_key=None):
    tag = dpg.draw_text((x, y), text, color=color, size=size, parent=dl)
    if font_key and font_key in _F:
        dpg.bind_item_font(tag, _F[font_key])
    return tag


def _score_disp(key, raw):
    """Score as a display string — count-up animated when the value is
    numeric, so the number climbs into place as a card reveals."""
    try:
        target = float(raw)
    except (TypeError, ValueError):
        return str(raw)
    return str(int(round(effects.count_up(f"rkscore:{key}", target))))


def _draw_delta(dl, x, y, delta, alpha):
    """Draw a movement indicator: ▲N (green), ▼N (red), – (dim), NEW (gold)."""
    if alpha <= 0:
        return
    if delta is None:
        _txt(dl, x, y, "NEW", (*C["gold"][:3], alpha), 13, "raj_sb_14")
    elif delta > 0:
        _txt(dl, x, y, f"▲{delta}", (*C["win"][:3], alpha), 13, "raj_sb_14")
    elif delta < 0:
        _txt(dl, x, y, f"▼{-delta}", (*C["loss"][:3], alpha), 13, "raj_sb_14")
    else:
        _txt(dl, x, y, "–", (*C["txt_dim"][:3], alpha), 13, "raj_sb_14")


def _player_streak(raw_name):
    """Return signed current streak for a player.
    Positive = consecutive wins, negative = consecutive losses, 0 = none.
    Looks up live.inhouse leaderboard (chronological recent_results: 1=W, 0=L).
    """
    try:
        from data.reader import live
        for p in (live.inhouse or []):
            if p.get("player") == raw_name:
                results = p.get("recent_results") or []
                if not results:
                    return 0
                last = results[-1]
                run = 0
                for r in reversed(results):
                    if r == last:
                        run += 1
                    else:
                        break
                return run if last else -run
    except Exception:
        pass
    return 0


def _draw_streak_medallion(dl, x, y, streak, alpha=255, min_streak=3):
    """Draw a flame (win streak) or ice (loss streak) medallion next to a name.
    Only shown when |streak| >= min_streak so it stays meaningful.
    Returns the pixel width consumed (0 if nothing drawn).
    """
    if abs(streak) < min_streak:
        return 0
    if streak > 0:
        glyph = "\U0001F525"   # 🔥
        col   = (255, 140, 60)
    else:
        glyph = "❄"       # ❄
        col   = (130, 200, 240)
    label = f"{glyph}{abs(streak)}"
    # Pill background
    pw = 32
    dpg.draw_rectangle((x, y), (x + pw, y + 18),
                       fill=(*col, max(0, min(255, int(alpha * 0.18)))),
                       color=(*col, max(0, min(255, int(alpha * 0.55)))),
                       rounding=9, thickness=1, parent=dl)
    dpg.draw_text((x + 4, y + 1), label,
                  color=(*col, alpha), size=14, parent=dl)
    return pw + 6


def _player_results(raw_name, n=8):
    """Return last `n` W/L results for a player (1=W, 0=L) from live.inhouse,
    most recent on the right. Empty list when none available."""
    try:
        from data.reader import live
        for p in (live.inhouse or []):
            if p.get("player") == raw_name:
                return list(p.get("recent_results") or [])[-n:]
    except Exception:
        pass
    return []


def _draw_mini_sparkline(dl, x, y, results, alpha=255, dot_r=3, gap=4):
    """Phase 3 — tiny W/L sparkline; most recent on the right."""
    if not results:
        return
    win_col = (130, 210, 130)
    loss_col = (220, 110, 110)
    for i, r in enumerate(results):
        col = win_col if r else loss_col
        cx = x + i * (dot_r * 2 + gap)
        dpg.draw_circle((cx, y), dot_r, fill=(*col, alpha),
                        color=(0, 0, 0, 0), parent=dl)


def _biggest_climber():
    """Return (player_name, +delta) for the biggest positive mover since the
    last rank snapshot, or None when no positive movement exists."""
    best, best_d = None, 0
    for name, d in (rankings.deltas or {}).items():
        if d is None or d <= 0:
            continue
        if d > best_d:
            best, best_d = name, d
    return (best, best_d) if best else None


def _biggest_faller():
    """Return (player_name, -delta) for the biggest negative mover, or None."""
    worst, worst_d = None, 0
    for name, d in (rankings.deltas or {}).items():
        if d is None or d >= 0:
            continue
        if d < worst_d:
            worst, worst_d = name, d
    return (worst, worst_d) if worst else None


def _name_link(dl, x, y, name_upper, raw_name, color, size, font_key=None):
    """Draw a player name as an underlined clickable link and register its hitbox."""
    tag = _txt(dl, x, y, name_upper, color, size, font_key)
    # Approximate text width: ~0.58 * size per char (Rajdhani proportional)
    tw = int(len(name_upper) * size * 0.58)
    # Underline — gold dot-dash hint that this is clickable
    dpg.draw_line((x, y + size + 2), (x + tw, y + size + 2),
                  color=(*C["gold_dk"][:3], color[3] if len(color) > 3 else 180),
                  thickness=1, parent=dl)
    _name_hitboxes.append((x, y, x + tw, y + size + 4, raw_name))
    return tag

# ---------------------------------------------------------------------------
# Main draw entry
# ---------------------------------------------------------------------------

def draw_rankings(dl, vw, vh, fonts=None):
    global _name_hitboxes
    if fonts:
        set_fonts(fonts)

    # Flush any newly uploaded avatars so cards can display them
    try:
        from ui.inhouse import _scan_local_avatars, _flush_pending
        _scan_local_avatars()
        _flush_pending()
    except Exception:
        pass

    _compute_layout(vw, vh)
    _name_hitboxes = []   # reset hitboxes each frame

    dpg.delete_item(dl, children_only=True)
    rankings.tick()

    dpg.draw_rectangle((0,0),(vw,3000), fill=C["bg"], color=(0,0,0,0), parent=dl)
    # V2 ambient — cool top-light + a faint gold stage-light over the podium.
    luxe.glow(dl, vw * 0.5, -vh * 0.25, vw * 0.75, (40, 72, 118), 55)
    luxe.glow(dl, vw * 0.5, _L.get("hero_top", TOP_PAD) + 60, vw * 0.34,
              C["gold"], 16)
    # Arena embers rising behind the podium.
    luxe.draw_embers(dl, 0, 0, vw, int(vh * 0.55), n=18, seed=5, alpha=110)

    phase = rankings.phase

    if phase in (RankRevealPhase.IDLE, RankRevealPhase.LOADING):
        _draw_loading(dl, vw, vh)
        return

    _draw_podium_cards(dl)
    _draw_challenger_rows(dl)
    _draw_rest_rows(dl)

    # Click-to-scout: detect clicks on player names
    if dpg.is_mouse_button_clicked(0) and _name_hitboxes:
        mouse = dpg.get_mouse_pos(local=False)
        vp    = dpg.get_viewport_pos()
        rx    = mouse[0] - vp[0] - 68   # subtract sidebar width
        ry    = mouse[1] - vp[1] - 52   # subtract app titlebar
        for (x1, y1, x2, y2, pname) in _name_hitboxes:
            if x1 <= rx <= x2 and y1 <= ry <= y2:
                state.nav_to_scout = pname
                break

    # Ripple effects
    now_ms = time.monotonic() * 1000
    for rip in rankings.ripples:
        rip.tick(now_ms)
        if not rip.done:
            dpg.draw_circle((rip.x, rip.y), rip.radius,
                            color=(*rip.color, rip.alpha),
                            thickness=rip.thickness, parent=dl)
    rankings.ripples = [r for r in rankings.ripples if not r.done]

    # Particle effects
    for ps in rankings.particles:
        ps.tick(now_ms, 16)
        for p in ps.particles:
            if p.alive:
                dpg.draw_circle((p.x, p.y), p.current_size,
                                fill=(*p.color, p.alpha),
                                color=(0,0,0,0), parent=dl)
    rankings.particles = [ps for ps in rankings.particles if not ps.finished]

    # Cinematic vignette — under the reveal flash so slams still read hot.
    luxe.vignette(dl, 0, 0, vw, vh, 65)

    if rankings.flash_alpha > 0:
        dpg.draw_rectangle((0,0),(vw,vh),
                           fill=(*C["flash"][:3], rankings.flash_alpha),
                           color=(0,0,0,0), parent=dl)

# ---------------------------------------------------------------------------
# Sub-draw functions (all read from _L)
# ---------------------------------------------------------------------------

def _draw_loading(dl, vw, vh):
    """Skeleton placeholder of the rankings layout — the podium + rows morph
    into real content once data lands, instead of popping in."""
    col_w      = _L.get("col_w", 380)
    hero_top   = _L.get("hero_top", TOP_PAD)
    side_top   = _L.get("side_top", TOP_PAD + SIDE_OFFSET)
    podium_bot = _L.get("podium_bot", side_top + SIDE_H)
    row_w      = _L.get("inner_w", vw - OUTER_PAD * 2)
    for rank, col in ((2, 0), (1, 1), (3, 2)):
        x1 = _col_x(col)
        y1 = hero_top if rank == 1 else side_top
        h  = HERO_H   if rank == 1 else SIDE_H
        effects.draw_skeleton_rect(dl, x1, y1, col_w, h, rounding=4)
    for i in range(7):
        ry = podium_bot + CHAL_PAD_T + i * (CHAL_H + CHAL_GAP)
        effects.draw_skeleton_row(dl, OUTER_PAD, ry, row_w, CHAL_H)
    tip = rankings._tip
    _txt(dl, max(40, vw // 2 - len(tip) * 5), vh - 48, tip,
         (*C["txt_dim"][:3], 150), 18, "raj_r_18")


def _draw_podium_cards(dl):
    data      = rankings.data
    if not data:
        return
    t         = rankings.shimmer_t
    col_w     = _L["col_w"]
    hero_top  = _L["hero_top"]
    side_top  = _L["side_top"]

    for rank, col_idx in [(2, 0), (3, 2), (1, 1)]:
        p   = data[rank-1] if rank <= len(data) else None
        al  = rankings.card_alpha.get(rank, 0)
        yo  = rankings.card_y_off.get(rank, 0)
        x1  = _col_x(col_idx)
        x2  = x1 + col_w
        base_y = hero_top if rank == 1 else side_top
        h      = HERO_H   if rank == 1 else SIDE_H
        # Gentle hover-lift once the card has fully revealed.
        lift = 0.0
        if al >= 200:
            _mp  = dpg.get_mouse_pos(local=False)
            _vp  = dpg.get_viewport_pos()
            _mrx = _mp[0] - _vp[0] - 68
            _mry = _mp[1] - _vp[1] - 52
            _hov = (x1 <= _mrx <= x2 and
                    base_y + yo <= _mry <= base_y + yo + h)
            lift = effects.hover_lift(f"podium:{rank}", _hov, lift=5.0)
        y1 = base_y + yo + lift
        y2 = y1 + h

        if al <= 0:
            _mystery(dl, x1, y1, x2, y2, t)
            continue

        tier         = p.get("tier", "Unranked") if p else "Unranked"
        accent_color = RANK_COLORS.get(tier, RANK_COLORS["Unranked"])
        medal_colors = {1: C["gold"], 2: C["platinum"], 3: (205, 127, 50, 255)}
        border_col   = medal_colors.get(rank, C["rule_dark"])

        # V2 podium card — medal aura + drop shadow + gradient panel.
        a_f = al / 255.0
        luxe.glow(dl, (x1 + x2) / 2, y2 - 10, col_w * 0.62,
                  border_col, int((34 if rank == 1 else 22) * a_f))
        luxe.shadow(dl, x1, y1, x2, y2,
                    alpha=int(100 * a_f), spread=16, drop=8)
        luxe.panel(dl, x1, y1, x2, y2, (*C["panel"][:3], al),
                   corner=8, border=border_col,
                   border_a=int(200 * a_f), sheen=int(60 * a_f))
        dpg.draw_rectangle((x1+2, y1+2),(x2-2, y1+2+ACCENT_H),
                           fill=(*accent_color[:3], al),
                           color=(0,0,0,0), rounding=2, parent=dl)
        luxe.vfade(dl, x1 + 3, y1 + 2 + ACCENT_H, x2 - 3, y1 + 22 + ACCENT_H,
                   accent_color, int(34 * a_f), solid="top")
        # Medal sheen — gold/silver/bronze single-pass sweep on revealed podium cards
        if al >= 220:
            try:
                from ui.effects import draw_shimmer
                draw_shimmer(dl, x1 + 2, y1 + 2 + ACCENT_H,
                             (x2 - 2) - (x1 + 2), (y2) - (y1 + 2 + ACCENT_H),
                             border_col, alpha=int(al * 0.55),
                             period=4.5 + rank * 0.7, sweep_w=110)
            except Exception:
                pass

        if rank == 1:
            _accent_corners(dl, x1, y1, x2, y2, (*C["gold"][:3], al))

        if not p:
            continue

        name = p.get("name", "Unknown").upper()

        ts     = str(p.get("tier_score", "?"))
        rs     = str(p.get("rank_score", "?"))
        fs     = _score_disp(p.get("name", ""), p.get("final_score", p.get("score", "?")))
        avg    = str(p.get("avg_tier", ""))
        rating = str(p.get("rating", tier[:1].upper()))

        raw_name = p.get("name", "Unknown")
        # Movement delta in the top-right corner of every podium card
        _draw_delta(dl, x2 - 56, y1 + 12, rankings.deltas.get(raw_name), al)
        if rank == 1:
            label_col = (*accent_color[:3], al)
            _txt(dl, x1+20, y1+18, "CHAMPION", label_col, 15, "raj_sb_18")
            _txt(dl, x1+20, y1+44, "NO.", (*C["txt2"][:3], al), 19, "raj_sb_18")
            luxe.glow(dl, x1+106, y1+76, 54, C["gold"], int(52 * al / 255))
            _txt(dl, x1+78, y1+28, "1", (*C["gold_lt"][:3], al), 90, "raj_72")
            _name_link(dl, x1+20, y1+152, name, raw_name, (*C["gold"][:3], al), 31, "raj_36")
            _txt(dl, x2-150, y1+72, fs,
                 (*C["gold_lt"][:3], al), 44, "raj_44")
            _badge(dl, x2-44, y1+44, rating, tier, al, r=38)
            dpg.draw_line((x1+20, y1+192),(x1+col_w-30, y1+192),
                          color=(*C["gold_dk"][:3], al), thickness=1, parent=dl)
            _txt(dl, x1+20, y1+202, f"TIER {ts}  ·  RANK {rs}",
                 (*C["txt2"][:3], al), 16, "raj_r_14")
            _avatar_or_hex(dl, x2-70, y1+h-52, 44, raw_name,
                           C["card_hover"], (*C["gold"][:3], al),
                           label=name[:2], alpha=al)
        else:
            label = "RUNNER-UP" if rank == 2 else "THIRD"
            _txt(dl, x1+16, y1+14, label, (*accent_color[:3], al), 16, "raj_sb_16")
            _txt(dl, x1+16, y1+32, "NO.", (*C["txt2"][:3], al), 17, "raj_sb_16")
            luxe.glow(dl, x1+88, y1+54, 40, border_col, int(34 * al / 255))
            _txt(dl, x1+66, y1+18, str(rank), (*C["gold_lt"][:3], al), 68, "raj_56")
            _name_link(dl, x1+16, y1+118, name, raw_name, (*C["txt"][:3], al), 25, "raj_36")
            _txt(dl, x2-120, y1+56, fs,
                 (*C["gold_lt"][:3], al), 31, "raj_36")
            _txt(dl, x1+16, y1+168, f"TIER {ts}  ·  RANK {rs}",
                 (*C["txt2"][:3], al), 16, "raj_r_14")
            _badge(dl, x2-38, y1+34, rating, tier, al, r=30)
            _avatar_or_hex(dl, x2-58, y1+h-42, 36, raw_name,
                           C["card_hover"], (*border_col[:3], al),
                           label=name[:2], alpha=al)


def _draw_challenger_rows(dl):
    data      = rankings.data
    row_w     = _L["inner_w"]
    rx        = OUTER_PAD
    t         = rankings.shimmer_t
    podium_bot= _L["podium_bot"]

    for i, rank in enumerate(range(4, 11)):
        p   = data[rank-1] if rank <= len(data) else None
        al  = rankings.card_alpha.get(rank, 0)
        xo  = rankings.card_x_off.get(rank, -80)
        ry  = podium_bot + CHAL_PAD_T + i * (CHAL_H + CHAL_GAP)

        if al <= 0:
            _mystery(dl, rx, ry, rx+row_w, ry+CHAL_H, t+i*0.1)
            continue

        luxe.panel(dl, rx+xo, ry, rx+row_w+xo, ry+CHAL_H,
                   (*C["card"][:3], al), corner=6,
                   border=C["gold_dk"], border_a=int(115 * al / 255),
                   sheen=int(30 * al / 255))
        if not p: continue

        dpg.draw_rectangle((rx+xo, ry+6),(rx+xo+4, ry+CHAL_H-6),
                           fill=(*C["gold_dk"][:3], al),
                           color=(0,0,0,0), parent=dl)

        name   = p.get("name","Unknown").upper()
        tier   = p.get("tier","Unranked")
        avg    = str(p.get("avg_tier", ""))
        fs     = _score_disp(p.get("name", ""), p.get("final_score", p.get("score", "?")))
        ts     = str(p.get("tier_score", "?"))
        rs     = str(p.get("rank_score", "?"))
        rating = str(p.get("rating", tier[:1].upper()))

        raw = p.get("name", "")
        _txt(dl, rx+xo+16, ry+CHAL_H//2-18, f"#{rank}",
             (*C["txt2"][:3], al), 19, "raj_20")
        # Rank movement delta directly under the rank number
        _draw_delta(dl, rx+xo+16, ry+CHAL_H//2+4, rankings.deltas.get(raw), al)
        _avatar_or_hex(dl, rx+xo+90, ry+CHAL_H//2, 26, raw,
                       C["panel"], C["rule_dark"], label=name[:2], alpha=al)
        _name_link(dl, rx+xo+122, ry+CHAL_H//2-18, name,
                   raw, (*C["txt"][:3], al), 21, "raj_20")
        _txt(dl, rx+xo+122, ry+CHAL_H//2+6, f"AVG TIER {avg}  ·  RANK {rs}",
             (*C["txt2"][:3], al), 15, "raj_r_14")
        # Phase 3 — mini sparkline (last 8 W/L) sits between name and score.
        spark_x = rx + xo + row_w - 280
        _draw_mini_sparkline(dl, spark_x, ry + CHAL_H//2 + 2,
                             _player_results(raw, n=8), alpha=al,
                             dot_r=4, gap=5)
        _txt(dl, rx+xo+row_w-110, ry+CHAL_H//2-14, fs,
             (*C["gold"][:3], al), 23, "raj_24")
        _badge(dl, rx+xo+row_w-152, ry+CHAL_H//2, rating, tier, al, r=24)


def _draw_rest_rows(dl):
    data      = rankings.data
    row_w     = _L["inner_w"]
    rx        = OUTER_PAD
    podium_bot= _L["podium_bot"]

    chal_h    = 7 * (CHAL_H + CHAL_GAP)
    section_y = podium_bot + CHAL_PAD_T + chal_h + SECTION_GAP

    luxe.glow(dl, rx + 8, section_y - 13, 22, C["gold"], 70)
    _txt(dl, rx, section_y - 22, "FULL STANDINGS",
         (*C["gold"][:3], 240), 19, "raj_sb_20")

    # Phase 3 — "on the rise / falling" callouts (right of section title).
    climber = _biggest_climber()
    faller  = _biggest_faller()
    callout_x = rx + 200
    if climber:
        nm, d = climber
        lbl = f"ON THE RISE  ·  {nm.upper()}  +{d}"
        _txt(dl, callout_x, section_y - 22, lbl,
             (130, 210, 130, 220), 16, "raj_sb_16")
        callout_x += int(len(lbl) * 9) + 24
    if faller:
        nm, d = faller
        lbl = f"FALLING  ·  {nm.upper()}  {d}"
        _txt(dl, callout_x, section_y - 22, lbl,
             (220, 130, 130, 200), 16, "raj_sb_16")

    luxe.hfade(dl, rx, section_y - 5, rx + row_w, section_y - 3,
               C["gold"], 110, solid="left")

    for i, rank in enumerate(range(11, len(data)+1)):
        p   = data[rank-1]
        al  = rankings.card_alpha.get(rank, 0)
        xo  = rankings.card_x_off.get(rank, -80)
        if al <= 0: continue

        ry  = section_y + i * (ROW_H + ROW_GAP)
        bg  = C["panel"] if i % 2 == 0 else C["card"]
        dpg.draw_rectangle((rx+xo, ry),(rx+row_w+xo, ry+ROW_H),
                           fill=(*bg[:3], al),
                           color=(0,0,0,0), rounding=2, parent=dl)
        if not p: continue

        name   = p.get("name","").upper()
        tier   = p.get("tier","Unranked")
        # Rank-tier ambient tint — slow per-row pulse keyed off tier color.
        _tc      = RANK_COLORS.get(tier, RANK_COLORS["Unranked"])
        _t       = (math.sin(time.monotonic() * 1.2 + i * 0.4) + 1) / 2
        _pulse_a = int((10 + _t * 22) * (al / 255.0))
        dpg.draw_rectangle((rx+xo, ry),(rx+row_w+xo, ry+ROW_H),
                           fill=(*_tc[:3], _pulse_a),
                           color=(0,0,0,0), rounding=2, parent=dl)
        # Left edge tier-color accent strip
        dpg.draw_rectangle((rx+xo, ry),(rx+xo+3, ry+ROW_H),
                           fill=(*_tc[:3], int(al * 0.75)),
                           color=(0,0,0,0), rounding=1, parent=dl)
        fs     = _score_disp(p.get("name", ""), p.get("final_score", p.get("score", "?")))
        rating = str(p.get("rating", tier[:1].upper()))

        raw2 = p.get("name", "")
        _txt(dl, rx+xo+14, ry+ROW_H//2-11, f"#{rank}",
             (*C["txt2"][:3], al), 17, "raj_18")
        _avatar_or_hex(dl, rx+xo+72, ry+ROW_H//2, 18, raw2,
                       C["panel"], C["rule_dark"], label=name[:2], alpha=al)
        _name_link(dl, rx+xo+96, ry+ROW_H//2-11, name,
                   raw2, (*C["txt"][:3], al), 17, "raj_18")
        # Movement delta to the right of the name
        name_w = int(len(name) * 17 * 0.58)
        _draw_delta(dl, rx+xo+96+name_w+10, ry+ROW_H//2-8,
                    rankings.deltas.get(raw2), al)
        # Phase 3 — mini sparkline (last 8 W/L) sits left of the score column.
        spark_x = rx + xo + row_w - 240
        _draw_mini_sparkline(dl, spark_x, ry + ROW_H//2 - 3,
                             _player_results(raw2, n=8), alpha=al,
                             dot_r=3, gap=4)
        _txt(dl, rx+xo+row_w-90, ry+ROW_H//2-11, fs,
             (*C["gold"][:3], al), 17, "raj_18")
        _badge(dl, rx+xo+row_w-118, ry+ROW_H//2, rating, tier, al, r=20)
