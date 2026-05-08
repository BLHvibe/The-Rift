"""
Rankings Tab — Phase 2.
Podium layout mirrors old launcher: #2 left / #1 center (raised) / #3 right.
Reveal order: #1 first with max fanfare → #2 → #3 → #4–#10 → #11+
All layout is computed dynamically from the actual content area each frame.
"""
import math, time
import dearpygui.dearpygui as dpg
from theme import C, RANK_COLORS, MEDAL_PARTICLE
from core.state import state
from core.animations import anim, ParticleSystem, Ripple

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
# Dynamic layout — recomputed every frame from actual content area
# ---------------------------------------------------------------------------
_L = {}   # populated by _compute_layout() at the top of draw_rankings()

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

    def reset(self):
        self.__init__()

    def tick(self):
        self.shimmer_t += 0.007

    def begin_loading(self):
        self.phase = RankRevealPhase.LOADING

    def begin_reveal(self, data):
        self.data  = data
        self.phase = RankRevealPhase.CARDS_HIDDEN
        for i in range(1, len(data) + 1):
            self.card_y_off[i] = 0
            self.card_alpha[i] = 0
            self.card_x_off[i] = -80
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
                               spread=spread, lifetime_ms=1000, size=5))
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
                  color=(*C["txt"][:3], alpha), size=11, parent=dl)


def _badge(dl, cx, cy, abbr, tier, alpha=255):
    bc = RANK_COLORS.get(tier, RANK_COLORS["Unranked"])
    r  = 18
    pts = [(cx, cy-r), (cx+r, cy), (cx, cy+r), (cx-r, cy)]
    dpg.draw_polygon(pts, fill=(*bc[:3], alpha),
                     color=(*C["bg"][:3], alpha), thickness=1, parent=dl)
    dpg.draw_text((cx - len(abbr)*4, cy - 7), abbr,
                  color=(*C["txt"][:3], alpha), size=12, parent=dl)


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
                  color=(*C["gold_dk"][:3], alpha), size=16, parent=dl)


def _txt(dl, x, y, text, color, size, font_key=None):
    tag = dpg.draw_text((x, y), text, color=color, size=size, parent=dl)
    if font_key and font_key in _F:
        dpg.bind_item_font(tag, _F[font_key])
    return tag

# ---------------------------------------------------------------------------
# Main draw entry
# ---------------------------------------------------------------------------

def draw_rankings(dl, vw, vh, fonts=None):
    if fonts:
        set_fonts(fonts)

    _compute_layout(vw, vh)

    dpg.delete_item(dl, children_only=True)
    rankings.tick()

    dpg.draw_rectangle((0,0),(vw,vh), fill=C["bg"], color=(0,0,0,0), parent=dl)

    phase = rankings.phase

    if phase in (RankRevealPhase.IDLE, RankRevealPhase.LOADING):
        _draw_loading(dl, vw, vh)
        return

    _draw_podium_cards(dl)
    _draw_challenger_rows(dl)
    _draw_rest_rows(dl)

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

    if rankings.flash_alpha > 0:
        dpg.draw_rectangle((0,0),(vw,vh),
                           fill=(*C["flash"][:3], rankings.flash_alpha),
                           color=(0,0,0,0), parent=dl)

# ---------------------------------------------------------------------------
# Sub-draw functions (all read from _L)
# ---------------------------------------------------------------------------

def _draw_loading(dl, vw, vh):
    cx, cy = vw // 2, vh // 2
    t  = (math.sin(time.monotonic() * 1.6) + 1) / 2
    a  = int(80 + t * 100)
    _txt(dl, cx-110, cy-10, "LOADING RANKINGS...",
         (*C["gold_dk"][:3], a), 14, "raj_14")


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
        if rank == 1:
            y1, h = hero_top + yo, HERO_H
        else:
            y1, h = side_top + yo, SIDE_H
        y2 = y1 + h

        if al <= 0:
            _mystery(dl, x1, y1, x2, y2, t)
            continue

        tier         = p.get("tier", "Unranked") if p else "Unranked"
        accent_color = RANK_COLORS.get(tier, RANK_COLORS["Unranked"])
        medal_colors = {1: C["gold"], 2: C["platinum"], 3: (205, 127, 50, 255)}
        border_col   = medal_colors.get(rank, C["rule_dark"])

        dpg.draw_rectangle((x1, y1),(x2, y2),
                           fill=(*C["panel"][:3], al),
                           color=(*border_col[:3], al),
                           rounding=4, parent=dl)
        dpg.draw_rectangle((x1+2, y1+2),(x2-2, y1+2+ACCENT_H),
                           fill=(*accent_color[:3], al),
                           color=(0,0,0,0), rounding=2, parent=dl)

        if rank == 1:
            _accent_corners(dl, x1, y1, x2, y2, (*C["gold"][:3], al))

        if not p:
            continue

        name = p.get("name", "Unknown").upper()

        if rank == 1:
            label_col = (*accent_color[:3], al)
            _txt(dl, x1+20, y1+18, "CHAMPION", label_col, 14, "raj_sb_18")
            _txt(dl, x1+20, y1+44, "NO.", (*C["txt_dim"][:3], al), 18, "raj_sb_18")
            _txt(dl, x1+78, y1+28, "1", (*C["gold_lt"][:3], al), 90, "raj_72")
            _txt(dl, x1+20, y1+152, name, (*C["gold"][:3], al), 32, "raj_36")
            _txt(dl, x2-150, y1+72, str(p.get("score", 0)),
                 (*C["gold_lt"][:3], al), 44, "raj_44")
            _badge(dl, x2-34, y1+28, tier[:2].upper(), tier, al)
            dpg.draw_line((x1+20, y1+192),(x1+col_w-30, y1+192),
                          color=(*C["gold_dk"][:3], al), thickness=1, parent=dl)
            _hex(dl, x2-70, y1+h-52, 44, C["card_hover"],
                 (*C["gold"][:3], al), label=name[:2], alpha=al)
        else:
            label = "RUNNER-UP" if rank == 2 else "THIRD"
            _txt(dl, x1+16, y1+14, label, (*accent_color[:3], al), 13, "raj_sb_14")
            _txt(dl, x1+16, y1+32, "NO.", (*C["txt_dim"][:3], al), 14, "raj_sb_14")
            _txt(dl, x1+66, y1+18, str(rank), (*C["gold_lt"][:3], al), 68, "raj_56")
            _txt(dl, x1+16, y1+118, name, (*C["txt"][:3], al), 24, "raj_28")
            _txt(dl, x2-120, y1+56, str(p.get("score", 0)),
                 (*C["gold_lt"][:3], al), 32, "raj_36")
            _badge(dl, x2-30, y1+24, tier[:2].upper(), tier, al)
            _hex(dl, x2-58, y1+h-42, 36, C["card_hover"],
                 (*border_col[:3], al), label=name[:2], alpha=al)


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

        dpg.draw_rectangle((rx+xo, ry),(rx+row_w+xo, ry+CHAL_H),
                           fill=(*C["card"][:3], al),
                           color=(*C["rule_dark"][:3], al),
                           rounding=3, parent=dl)
        if not p: continue

        dpg.draw_rectangle((rx+xo, ry+6),(rx+xo+4, ry+CHAL_H-6),
                           fill=(*C["gold_dk"][:3], al),
                           color=(0,0,0,0), parent=dl)

        name = p.get("name","Unknown").upper()
        tier = p.get("tier","Unranked")

        _txt(dl, rx+xo+16, ry+CHAL_H//2-12, f"#{rank}",
             (*C["txt2"][:3], al), 18, "raj_20")
        _hex(dl, rx+xo+90, ry+CHAL_H//2, 26,
             C["panel"], C["rule_dark"], label=name[:2], alpha=al)
        _txt(dl, rx+xo+122, ry+CHAL_H//2-12, name,
             (*C["txt"][:3], al), 20, "raj_20")
        _txt(dl, rx+xo+row_w-100, ry+CHAL_H//2-12, str(p.get("score",0)),
             (*C["gold"][:3], al), 22, "raj_24")
        _badge(dl, rx+xo+row_w-136, ry+CHAL_H//2, tier[:2].upper(), tier, al)


def _draw_rest_rows(dl):
    data      = rankings.data
    row_w     = _L["inner_w"]
    rx        = OUTER_PAD
    podium_bot= _L["podium_bot"]

    chal_h    = 7 * (CHAL_H + CHAL_GAP)
    section_y = podium_bot + CHAL_PAD_T + chal_h + SECTION_GAP

    _txt(dl, rx, section_y - 22, "FULL STANDINGS",
         (*C["txt_dim"][:3], 180), 14, "raj_sb_16")
    dpg.draw_line((rx, section_y - 4),(rx + row_w, section_y - 4),
                  color=C["rule_dark"], thickness=1, parent=dl)

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

        name = p.get("name","").upper()
        tier = p.get("tier","Unranked")

        _txt(dl, rx+xo+14, ry+ROW_H//2-11, f"#{rank}",
             (*C["txt2"][:3], al), 16, "raj_18")
        _txt(dl, rx+xo+56, ry+ROW_H//2-11, name,
             (*C["txt"][:3], al), 16, "raj_18")
        _txt(dl, rx+xo+row_w-90, ry+ROW_H//2-11, str(p.get("score",0)),
             (*C["gold"][:3], al), 16, "raj_18")
        _badge(dl, rx+xo+row_w-124, ry+ROW_H//2, tier[:2].upper(), tier, al)
