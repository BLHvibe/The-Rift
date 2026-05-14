"""
Activity Feed Tab.
Primary source: live.activity (_Activity sheet).
Fallback: derives events from live.inhouse + live.rankings.
Shows up to 100 events with date grouping and time-ago timestamps.
"""
import time
from datetime import datetime, timedelta, timezone
import dearpygui.dearpygui as dpg
from theme import C
from data.reader import live, load_activity

_F = {}
def set_fonts(f): global _F; _F = f

_FEED_WIN = "feed_overlay_win"

TOP_BAR_H = 52
PAD       = 20
CARD_H    = 76
CARD_GAP  = 6
SEP_H     = 28   # date separator height

MAX_EVENTS    = 100
AUTO_REFRESH_SECS = 90.0   # poll the sheet at most this often while tab is open

# ---------------------------------------------------------------------------
# Event type → border colour + icon prefix
# ---------------------------------------------------------------------------
_KIND_META = {
    "UPDATE":     (C["gold"],        "◆"),
    "SCOUT":      ((140, 100, 220, 255), "●"),
    "SCOUT_NEW":  ((140, 100, 220, 255), "★"),
    "RESCOUTED":  ((120,  80, 200, 255), "↺"),
    "DRAFT":      ((80,  160, 220, 255), "⚔"),
    "INHOUSE":    (C["win"],         "▶"),
    "inhouse":    (C["win"],         "▶"),
    "rank":       (C["gold"],        "#"),
}

def _kind_color(kind):
    meta = _KIND_META.get(kind.upper() if kind else "", None)
    if meta:
        return meta
    return (C["txt_dim"], "·")


# ---------------------------------------------------------------------------
# Time-ago formatting
# ---------------------------------------------------------------------------

def _parse_ts(ts_str):
    """Parse a sheet timestamp → datetime. Accepts ISO 8601 (with optional Z/offset)
    and the legacy 'YYYY-MM-DD HH:MM[:SS]' formats. Returns aware datetimes when
    the source is ISO, naive (treated as local) otherwise."""
    if not ts_str:
        return None
    s = ts_str.strip()
    # ISO 8601 (e.g. 2026-05-14T12:34:56Z or +00:00)
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _time_ago(ts_str):
    """Return a human-readable relative time like '2h ago', 'Just now'."""
    dt = _parse_ts(ts_str)
    if not dt:
        return ts_str
    if dt.tzinfo is not None:
        now = datetime.now(timezone.utc)
    else:
        now = datetime.now()
    delta = now - dt
    secs  = int(delta.total_seconds())
    if secs < 0:
        secs = 0
    if secs < 60:
        return "Just now"
    if secs < 3600:
        m = secs // 60
        return f"{m}m ago"
    if secs < 86400:
        h = secs // 3600
        return f"{h}h ago"
    d = secs // 86400
    if d == 1:
        return "Yesterday"
    if d < 30:
        return f"{d} days ago"
    if d < 365:
        return f"{d//30}mo ago"
    return f"{d//365}y ago"


def _date_label(ts_str):
    """Return 'Today', 'Yesterday', or 'Mon Jan 01'."""
    dt = _parse_ts(ts_str)
    if not dt:
        return ts_str
    if dt.tzinfo is not None:
        dt = dt.astimezone()  # convert to local for human-readable date grouping
    today = datetime.now().date()
    if dt.date() == today:
        return "Today"
    if dt.date() == today - timedelta(days=1):
        return "Yesterday"
    return dt.strftime("%a %b %d")


def _event_date_key(ev):
    ts = ev.get("ts", "") or ev.get("timestamp", "")
    dt = _parse_ts(ts)
    if not dt:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone()
    return dt.date()


# ---------------------------------------------------------------------------
# Event building
# ---------------------------------------------------------------------------

def _build_events():
    """
    Return up to MAX_EVENTS events with date context attached.
    Primary: live.activity (real sheet events).
    Fallback: derive from live.inhouse + live.rankings.
    """
    raw = list(live.activity or [])

    if raw:
        # Sheet events already ordered newest-first
        events = []
        for ev in raw[:MAX_EVENTS]:
            kind   = ev.get("event_type", "")
            player = ev.get("player",     "")
            detail = ev.get("details",    "")
            ts     = ev.get("timestamp",  "")
            events.append({
                "kind":    kind,
                "player":  player,
                "desc":    detail,
                "ts":      ts,
                "time_ago": _time_ago(ts),
            })
        return events

    # ── Fallback: derived events ──────────────────────────────────────────
    events = []
    for row in (live.inhouse or []):
        name  = row.get("player", "")
        wins  = row.get("wins",   0)
        losses= row.get("losses", 0)
        wr_raw = str(row.get("wr", "0")).replace("%", "")
        try:
            wr = float(wr_raw)
        except (ValueError, TypeError):
            wr = 0.0
        games = row.get("games", 0)
        if games > 0:
            events.append({
                "kind":    "INHOUSE",
                "player":  name,
                "desc":    f"played {games} inhouse game{'s' if games!=1 else ''}  —  {wins}W {losses}L  ({wr}% WR)",
                "ts":      "",
                "time_ago":"",
            })
    for row in (live.rankings or []):
        name  = row.get("name",  "")
        rank  = row.get("rank",  0)
        tier  = row.get("tier",  "")
        score = row.get("final_score") or row.get("score", "")
        try:
            score_str = f"{float(score):.0f}"
        except (ValueError, TypeError):
            score_str = str(score)
        if name and rank:
            events.append({
                "kind":    "rank",
                "player":  name,
                "desc":    f"ranked #{rank} in power rankings  —  {tier}  (score {score_str})",
                "ts":      "",
                "time_ago":"",
            })
    return events[:MAX_EVENTS]


# ---------------------------------------------------------------------------
# Feed state
# ---------------------------------------------------------------------------

class FeedState:
    def __init__(self):
        self.events            = []
        self.last_refresh      = 0.0   # monotonic, set after a sheet load completes
        self.last_sheet_attempt = 0.0  # monotonic, set when we kick off a load
        self.dirty             = False
        self.loading           = False
        self.sheet_loaded_once = False
        self.last_error        = ""

    def refresh(self):
        """Refresh from in-memory fallback only (no network)."""
        self.events       = _build_events()
        self.dirty        = True

    def refresh_from_sheet(self, force=False):
        """Kick a background load of the _Activity sheet.

        force=False is used by the auto-refresh path so we don't stampede.
        Returns True if a load was actually started."""
        if self.loading:
            return False
        if not force:
            elapsed = time.monotonic() - self.last_sheet_attempt
            if self.last_sheet_attempt and elapsed < AUTO_REFRESH_SECS:
                return False
        self.loading             = True
        self.last_sheet_attempt  = time.monotonic()
        self.dirty               = True   # repaint spinner on next frame
        def _done(evs):
            self.loading           = False
            self.last_error        = ""
            self.sheet_loaded_once = True
            self.last_refresh      = time.monotonic()
            self.events            = _build_events()
            self.dirty             = True
        def _err(msg):
            self.loading     = False
            self.last_error  = str(msg) or "Unknown error"
            self.events      = _build_events()
            self.dirty       = True
        load_activity(on_done=_done, on_error=_err)
        return True


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

    # Kick a sheet load the first time the tab is drawn, and again every
    # AUTO_REFRESH_SECS while the user is on it.
    if not _feed.sheet_loaded_once and not _feed.loading:
        _feed.refresh_from_sheet(force=True)
    elif _feed.sheet_loaded_once and not _feed.loading:
        if time.monotonic() - _feed.last_refresh >= AUTO_REFRESH_SECS:
            _feed.refresh_from_sheet(force=True)

    dpg.delete_item(dl, children_only=True)
    dpg.draw_rectangle((0, 0), (vw, vh), fill=C["bg"], color=(0, 0, 0, 0), parent=dl)

    # Top bar
    dpg.draw_rectangle((0, 0), (vw, TOP_BAR_H),
                        fill=(*C["panel"][:3], 220), color=(0, 0, 0, 0), parent=dl)
    dpg.draw_line((0, TOP_BAR_H - 1), (vw, TOP_BAR_H - 1),
                  color=C["rule_dark"], thickness=1, parent=dl)
    _txt(dl, PAD, 12, "ACTIVITY FEED", (*C["gold"][:3], 220), 23, "raj_24")

    # Loading spinner hint (animated dots)
    if _feed.loading:
        dots = "." * (int(time.monotonic() * 2) % 4)
        _txt(dl, PAD + 240, 18, f"loading{dots}", (*C["gold_lt"][:3], 200), 17, "raj_r_16")
    elif _feed.last_error:
        _txt(dl, PAD + 240, 18,
             f"⚠ sheet load failed — showing local fallback",
             (*C["loss"][:3], 200), 16, "raj_r_16")
    elif _feed.sheet_loaded_once and _feed.last_refresh:
        ago = int(time.monotonic() - _feed.last_refresh)
        if ago < 5:
            label = "synced just now"
        elif ago < 60:
            label = f"synced {ago}s ago"
        else:
            label = f"synced {ago // 60}m ago"
        _txt(dl, PAD + 240, 18, label, (*C["txt_dim"][:3], 140), 16, "raj_r_16")

    # REFRESH button
    bw, bh = 140, 34
    bx = vw - bw - PAD
    by = (TOP_BAR_H - bh) // 2
    btn_fill = (*C["gold_dk"][:3], 200) if not _feed.loading else (*C["gold_dk"][:3], 120)
    dpg.draw_rectangle((bx, by), (bx + bw, by + bh),
                        fill=btn_fill,
                        color=(*C["gold"][:3], 200), rounding=4, parent=dl)
    _txt(dl, bx + 14, by + 8, "◆  REFRESH", (*C["gold_lt"][:3], 240), 18, "raj_sb_18")

    # Click — force a sheet refresh (same hit-test pattern as the rest of the app)
    if dpg.is_mouse_button_clicked(0):
        mouse = dpg.get_mouse_pos(local=False)
        vp    = dpg.get_viewport_pos()
        rx = mouse[0] - vp[0] - 68
        ry = mouse[1] - vp[1] - TOP_BAR_H
        if bx <= rx <= bx + bw and by <= ry <= by + bh:
            _feed.refresh_from_sheet(force=True)

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

    last_date_key = None
    for ev in events:
        dk = _event_date_key(ev)
        if dk and dk != last_date_key:
            last_date_key = dk
            _draw_date_separator(ev.get("ts", ""), parent)
        _draw_event_card(ev, parent)
        dpg.add_spacer(height=CARD_GAP, parent=parent)


def _empty_state(parent):
    dpg.add_spacer(height=60, parent=parent)
    if _feed.loading and not _feed.sheet_loaded_once:
        msg = "Loading activity from sheet…"
    elif _feed.last_error and not _feed.sheet_loaded_once:
        msg = "Could not reach the Activity sheet. Check your connection and click REFRESH."
    elif _feed.sheet_loaded_once:
        msg = "No activity yet — events will appear here after a SCOUT, DRAFT, or INHOUSE run."
    else:
        msg = "Click REFRESH to load from the Activity sheet."
    t = dpg.add_text(msg, color=C["txt_dim"][:3], parent=parent)
    if "raj_r_14" in _F:
        dpg.bind_item_font(t, _F["raj_r_14"])
    if _feed.last_error and _feed.sheet_loaded_once is False:
        err = dpg.add_text(f"  ↳ {_feed.last_error[:140]}",
                            color=C["loss"][:3], parent=parent)
        if "raj_r_12" in _F:
            dpg.bind_item_font(err, _F["raj_r_12"])


def _draw_date_separator(ts_str, parent):
    dpg.add_spacer(height=4, parent=parent)
    lbl = _date_label(ts_str) if ts_str else ""
    if lbl:
        with dpg.drawlist(width=-1, height=SEP_H, parent=parent):
            t = dpg.draw_text((PAD, 6), lbl.upper(),
                               color=(*C["gold_dk"][:3], 200), size=15)
            if "raj_sb_14" in _F:
                dpg.bind_item_font(t, _F["raj_sb_14"])
            dpg.draw_line((PAD + 100, SEP_H // 2),
                           (2000, SEP_H // 2),
                           color=(*C["rule_dark"][:3], 120), thickness=1)
    dpg.add_spacer(height=2, parent=parent)


def _draw_event_card(ev, parent):
    kind       = ev.get("kind",    "")
    player     = ev.get("player",  "")
    desc       = ev.get("desc",    "")
    time_ago   = ev.get("time_ago","")

    border_col, icon = _kind_color(kind)

    with dpg.drawlist(width=-1, height=CARD_H, parent=parent):
        # Background
        dpg.draw_rectangle(
            (0, 0), (2000, CARD_H),
            fill=(*C["card"][:3], 220),
            color=(*border_col[:3], 160),
            rounding=4,
        )
        # Left accent bar
        dpg.draw_rectangle(
            (0, 0), (3, CARD_H),
            fill=(*border_col[:3], 230),
            color=(0, 0, 0, 0),
            rounding=2,
        )
        # Player name
        name_tag = dpg.draw_text(
            (PAD, 14), f"{icon}  {player.upper()}" if player else icon,
            color=(*C["gold_lt"][:3], 230), size=17,
        )
        if "raj_20" in _F:
            dpg.bind_item_font(name_tag, _F["raj_20"])
        # Description
        desc_tag = dpg.draw_text(
            (PAD, 40), desc,
            color=(*C["txt"][:3], 190), size=15,
        )
        if "raj_r_14" in _F:
            dpg.bind_item_font(desc_tag, _F["raj_r_14"])
        # Time-ago (right-aligned area)
        if time_ago:
            ta_tag = dpg.draw_text(
                (PAD, 58), time_ago,
                color=(*C["txt_dim"][:3], 140), size=13,
            )
            if "raj_r_12" in _F:
                dpg.bind_item_font(ta_tag, _F["raj_r_12"])
