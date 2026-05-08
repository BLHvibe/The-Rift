"""
Activity Feed Tab.
Reads live.inhouse (leaderboard) and live.rankings for recent events
and displays a scrollable card list of the 50 most recent events.
"""
import time
import dearpygui.dearpygui as dpg
from theme import C
from data.reader import live

_F = {}
def set_fonts(f): global _F; _F = f

_FEED_WIN = "feed_overlay_win"

TOP_BAR_H = 52
PAD       = 20
CARD_H    = 72
CARD_GAP  = 6


# ---------------------------------------------------------------------------
# Event generation — derive activity events from live data
# ---------------------------------------------------------------------------

def _build_events():
    """
    Build a list of event dicts from live.inhouse and live.rankings.
    Each event: {kind, player, desc, border_color}
    """
    events = []

    # Inhouse leaderboard events — top performers
    for row in (live.inhouse or []):
        name   = row.get("player", "")
        wins   = row.get("wins", 0)
        losses = row.get("losses", 0)
        wr_raw = str(row.get("wr", "0")).replace("%", "")
        try:
            wr = float(wr_raw)
        except (ValueError, TypeError):
            wr = 0.0
        games  = row.get("games", 0)
        rank   = row.get("rank", 0)

        if games > 0:
            events.append({
                "kind":         "inhouse",
                "player":       name,
                "desc":         f"played {games} inhouse game{'s' if games != 1 else ''}  —  {wins}W {losses}L  ({wr}% WR)",
                "border_color": C["win"] if wr >= 52 else C["loss"] if wr < 48 else C["gold"],
            })

    # Rankings events — list current power rankings
    for row in (live.rankings or []):
        name  = row.get("name", "")
        rank  = row.get("rank", 0)
        tier  = row.get("tier", "")
        score = row.get("final_score") or row.get("score", "")
        try:
            score_f = float(score)
            score_str = f"{score_f:.0f}"
        except (ValueError, TypeError):
            score_str = str(score)
        if name and rank:
            events.append({
                "kind":         "rank",
                "player":       name,
                "desc":         f"ranked #{rank} in power rankings  —  {tier}  (score {score_str})",
                "border_color": C["gold"],
            })

    return events[:50]


# ---------------------------------------------------------------------------
# Feed state
# ---------------------------------------------------------------------------

class FeedState:
    def __init__(self):
        self.events       = []
        self.last_refresh = 0.0
        self.dirty        = False   # True after refresh until cards are rebuilt

    def refresh(self):
        self.events       = _build_events()
        self.last_refresh = time.monotonic()
        self.dirty        = True


_feed = FeedState()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _txt(dl, x, y, text, color, size, font_key=None):
    tag = dpg.draw_text((x, y), text, color=color, size=size, parent=dl)
    if font_key and font_key in _F:
        dpg.bind_item_font(tag, _F[font_key])
    return tag


# ---------------------------------------------------------------------------
# Main draw
# ---------------------------------------------------------------------------

def draw_feed(dl, vw, vh, fonts=None):
    if fonts:
        set_fonts(fonts)

    dpg.delete_item(dl, children_only=True)
    dpg.draw_rectangle((0, 0), (vw, vh), fill=C["bg"], color=(0, 0, 0, 0), parent=dl)

    # Top bar
    dpg.draw_rectangle((0, 0), (vw, TOP_BAR_H),
                        fill=(*C["panel"][:3], 220), color=(0, 0, 0, 0), parent=dl)
    dpg.draw_line((0, TOP_BAR_H - 1), (vw, TOP_BAR_H - 1),
                  color=C["rule_dark"], thickness=1, parent=dl)
    _txt(dl, PAD, 12, "ACTIVITY FEED", (*C["gold"][:3], 220), 22, "raj_24")

    # REFRESH button
    bw, bh = 140, 34
    bx = vw - bw - PAD
    by = (TOP_BAR_H - bh) // 2
    dpg.draw_rectangle((bx, by), (bx + bw, by + bh),
                        fill=(*C["gold_dk"][:3], 200),
                        color=(*C["gold"][:3], 200), rounding=4, parent=dl)
    _txt(dl, bx + 14, by + 8, "◆  REFRESH", (*C["gold_lt"][:3], 240), 15, "raj_sb_16")

    # Click — refresh button
    if dpg.is_mouse_button_clicked(0):
        mouse = dpg.get_mouse_pos(local=False)
        vp    = dpg.get_viewport_pos()
        rx = mouse[0] - vp[0] - 68
        ry = mouse[1] - vp[1] - TOP_BAR_H
        if bx <= rx <= bx + bw and by <= ry <= by + bh:
            _feed.refresh()

    # Build or use cached events
    if not _feed.events:
        _feed.refresh()

    # Scrollable card list in an overlay window
    if not dpg.does_item_exist(_FEED_WIN):
        _build_feed_window(vw, vh)
    else:
        dpg.configure_item(_FEED_WIN,
                           pos=(68, TOP_BAR_H),
                           width=vw - 68, height=vh - TOP_BAR_H)
        if _feed.dirty:
            _repopulate_feed()
            _feed.dirty = False


def _build_feed_window(vw, vh):
    with dpg.window(tag=_FEED_WIN,
                    pos=(68, TOP_BAR_H),
                    width=vw - 68, height=vh - TOP_BAR_H,
                    no_title_bar=True, no_resize=True,
                    no_move=True, no_focus_on_appearing=True):
        dpg.add_spacer(height=PAD)
        with dpg.group(tag="feed_card_group"):
            _populate_cards()
    _feed.dirty = False


def _repopulate_feed():
    if not dpg.does_item_exist("feed_card_group"):
        return
    dpg.delete_item("feed_card_group", children_only=True)
    _populate_cards()


def _populate_cards():
    events = _feed.events
    parent = "feed_card_group"

    if not events:
        _empty_state(parent)
        return

    for ev in events:
        _draw_event_card(ev, parent)
        dpg.add_spacer(height=CARD_GAP, parent=parent)


def _empty_state(parent):
    dpg.add_spacer(height=60, parent=parent)
    t = dpg.add_text(
        "No activity yet — run Fetch Ranks to populate",
        color=C["txt_dim"][:3], parent=parent,
    )
    if "raj_r_14" in _F:
        dpg.bind_item_font(t, _F["raj_r_14"])


def _draw_event_card(ev, parent):
    border_col = ev.get("border_color", C["gold"])
    player     = ev.get("player", "")
    desc       = ev.get("desc", "")

    with dpg.drawlist(width=-1, height=CARD_H, parent=parent):
        dpg.draw_rectangle(
            (0, 0), (2000, CARD_H),
            fill=(*C["card"][:3], 220),
            color=(*border_col[:3], 180),
            rounding=4,
        )
        dpg.draw_rectangle(
            (0, 0), (3, CARD_H),
            fill=(*border_col[:3], 230),
            color=(0, 0, 0, 0),
            rounding=2,
        )
        name_tag = dpg.draw_text(
            (PAD, 14), player.upper(),
            color=(*C["gold_lt"][:3], 230), size=16,
        )
        if "raj_20" in _F:
            dpg.bind_item_font(name_tag, _F["raj_20"])
        desc_tag = dpg.draw_text(
            (PAD, 40), desc,
            color=(*C["txt"][:3], 190), size=13,
        )
        if "raj_r_14" in _F:
            dpg.bind_item_font(desc_tag, _F["raj_r_14"])
