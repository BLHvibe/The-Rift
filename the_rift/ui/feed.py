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
from ui import effects
from ui import luxe
from data.reader import live, load_activity

_F = {}
def set_fonts(f): global _F; _F = f

_FEED_WIN = "feed_overlay_win"

TOP_BAR_H   = 56
_VP_TITLE_H = 52   # app titlebar height (same as main.py TITLE_H)
PAD         = 24
CARD_H      = 84
CARD_GAP    = 8
SEP_H       = 34   # date separator height
ICON_BOX    = 38   # left-side colored kind chip

MAX_EVENTS    = 100
AUTO_REFRESH_SECS = 90.0   # poll the sheet at most this often while tab is open

# Width of the feed window's content area, set at draw time so right-aligned
# elements (time-ago / NEW badge) know the real card width.
_card_w = [800]

# ---------------------------------------------------------------------------
# Event type > border colour + icon prefix
# ---------------------------------------------------------------------------
_KIND_META = {
    "UPDATE":     (C["gold"],            "UPD"),
    "SCOUT":      ((140, 100, 220, 255), "SCT"),
    "SCOUT_NEW":  ((170, 130, 230, 255), "NEW"),
    "RESCOUTED":  ((120,  80, 200, 255), "RSC"),
    "DRAFT":      ((80,  160, 220, 255), "DFT"),
    "TIER_LIST":  ((220, 165, 100, 255), "TL"),
    "INHOUSE":    (C["win"],             "IH"),
    "inhouse":    (C["win"],             "IH"),
    "rank":       (C["gold"],            "RNK"),
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
    """Parse a sheet timestamp > datetime. Accepts ISO 8601 (with optional Z/offset)
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


def _event_key(ev):
    """Stable identifier for an event used to detect 'new since last refresh'."""
    return (ev.get("ts", ""), ev.get("kind", ""),
            ev.get("player", ""), ev.get("desc", ""))


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

    The sheet was historically only fed by INHOUSE log events, which made the
    feed feel single-note. We now MERGE the sheet events with a set of derived
    events — recent match highlights, ranking deltas, scout refresh, top
    performances — so the feed always shows a variety of activity even when
    only one event type is written to the sheet."""
    events = []

    # ── Primary: real sheet events ────────────────────────────────────────
    raw = list(live.activity or [])
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
            "_synthetic": False,
        })

    # ── Derived: recent match highlights ──────────────────────────────────
    # Surface the latest few matches with their carry & winner side. Each match
    # appears once so the feed isn't drowned in matched copies of the same row.
    matches = list(live.match_history or [])[:5]
    for m in matches:
        winner = (m.get("winner") or "").lower()
        if not winner:
            continue
        ts = m.get("started_at") or ""
        parts = m.get("participants") or []
        # Pick the top fragger on the winning side.
        best = None
        for pt in parts:
            if (pt.get("team") or "").lower() != winner:
                continue
            k = int(pt.get("kills") or 0)
            a = int(pt.get("assists") or 0)
            d = max(1, int(pt.get("deaths") or 0))
            score = (k * 2.0 + a) / d
            if best is None or score > best[0]:
                best = (score, pt)
        carry_name = ""
        carry_champ = ""
        kda = ""
        if best:
            pt = best[1]
            carry_name = (pt.get("player") or "").strip()
            carry_champ = (pt.get("champion") or "").strip()
            kda = (f"{int(pt.get('kills') or 0)}/"
                   f"{int(pt.get('deaths') or 0)}/"
                   f"{int(pt.get('assists') or 0)}")
        desc = (f"won as {winner.upper()} side"
                if not carry_name else
                f"carried on {carry_champ}  ·  {kda}")
        events.append({
            "kind":    "INHOUSE",
            "player":  carry_name or winner.upper(),
            "desc":    desc,
            "ts":      ts,
            "time_ago": _time_ago(ts),
            "_synthetic": True,
        })

    # ── Derived: ranking shifts ───────────────────────────────────────────
    try:
        from ui.rankings import rankings as _rk
        deltas = getattr(_rk, "deltas", {}) or {}
    except Exception:
        deltas = {}
    movers = [(n, d) for n, d in deltas.items()
              if isinstance(d, int) and d != 0]
    movers.sort(key=lambda x: -abs(x[1]))
    for n, d in movers[:3]:
        direction = "climbed" if d > 0 else "dropped"
        plural = "spot" if abs(d) == 1 else "spots"
        events.append({
            "kind":    "rank",
            "player":  n,
            "desc":    f"{direction} {abs(d)} {plural} in power rankings",
            "ts":      "",
            "time_ago": "",
            "_synthetic": True,
        })

    # ── Derived: scout snapshot (top 3 by score) ──────────────────────────
    scout = list(live.scout or [])[:3]
    for s in scout:
        name = s.get("name") or s.get("player") or ""
        if not name:
            continue
        score = s.get("score") or s.get("final_score") or ""
        try:
            score_s = f"score {float(score):.0f}"
        except (ValueError, TypeError):
            score_s = ""
        wr = s.get("wr") or s.get("ranked_wr") or ""
        bits = [b for b in (score_s, f"{wr} WR" if wr else "") if b]
        events.append({
            "kind":    "SCOUT",
            "player":  name,
            "desc":    f"scouted  —  {'  ·  '.join(bits)}" if bits else "scouted",
            "ts":      "",
            "time_ago": "",
            "_synthetic": True,
        })

    # ── Derived: rankings snapshot (top 3) ────────────────────────────────
    for row in (live.rankings or [])[:3]:
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
                "desc":    f"ranked #{rank}  —  {tier}  (score {score_str})",
                "ts":      "",
                "time_ago": "",
                "_synthetic": True,
            })

    # De-duplicate by (kind, player, desc) so a tier-list submit + a recent
    # match don't collapse into the same row twice across the merge.
    seen = set()
    out = []
    for ev in events:
        key = (ev.get("kind"), ev.get("player"), ev.get("desc"))
        if key in seen:
            continue
        seen.add(key)
        out.append(ev)
    return out[:MAX_EVENTS]


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
        # Per-event "appeared at" timestamps — used to flash new events briefly
        self._seen_keys        = set()    # event keys we've already shown
        self._appear_at        = {}       # key → monotonic timestamp of first appearance
        # Phase 3 — active filter chip (None = all). One of:
        # None / "DRAFT" / "INHOUSE" / "SCOUT" / "RANK".
        self.filter_kind       = None

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
            # Mark any events we haven't seen before as fresh (skip the very first
            # load — we don't flash every event on startup).
            now = time.monotonic()
            first_load = not self._seen_keys
            had_fresh = False
            for ev in self.events:
                key = _event_key(ev)
                if key and key not in self._seen_keys:
                    self._seen_keys.add(key)
                    if not first_load:
                        self._appear_at[key] = now
                        had_fresh = True
            self.dirty             = True
            # If we surfaced fresh events, schedule a re-render in 9s to drop
            # the NEW badge (is_fresh check uses an 8s window).
            if had_fresh:
                try:
                    from core.animations import anim
                    anim.tween(0, 1, 1, "linear", delay_ms=9000,
                               on_done=lambda: setattr(self, "dirty", True))
                except Exception:
                    pass
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
    luxe.glow(dl, vw * 0.5, -vh * 0.25, vw * 0.75, (40, 72, 118), 55)

    # Top bar — V2 broadcast header.
    dpg.draw_rectangle((0, 0), (vw, TOP_BAR_H),
                        fill=C["navy_deep"], color=(0, 0, 0, 0), parent=dl)
    luxe.vfade(dl, 0, 0, vw, TOP_BAR_H, (44, 74, 116), 46, solid="top")
    luxe.vfade(dl, 0, TOP_BAR_H - 10, vw, TOP_BAR_H - 1,
               C["gold"], 26, solid="bottom")
    dpg.draw_line((0, TOP_BAR_H - 1), (vw, TOP_BAR_H - 1),
                  color=(*C["gold_dk"][:3], 200), thickness=1, parent=dl)
    luxe.glow(dl, PAD + 6, TOP_BAR_H // 2, 26, C["gold"], 55)
    _txt(dl, PAD, 12, "ACTIVITY FEED", (*C["gold_lt"][:3], 235), 23, "raj_24")

    # Loading spinner (orbital)
    if _feed.loading:
        try:
            from ui.effects import draw_orbital_spinner
            draw_orbital_spinner(dl, PAD + 248, 26, 11,
                                  C["gold_lt"], 220, n_dots=3, speed=2.0, dot_r=3)
        except Exception:
            pass
        _txt(dl, PAD + 270, 18, "syncing",
             (*C["gold_lt"][:3], 200), 17, "raj_r_16")
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
    if _feed.loading:
        dpg.draw_rectangle((bx, by), (bx + bw, by + bh),
                            fill=(*C["gold_dk"][:3], 120),
                            color=(*C["gold"][:3], 120), rounding=4, parent=dl)
    else:
        luxe.glow(dl, bx + bw / 2, by + bh / 2, bh * 1.1, C["gold"], 32)
        luxe.panel(dl, bx, by, bx + bw, by + bh, (116, 90, 44, 235),
                   corner=4, border=C["gold"], border_a=210, sheen=90)
    _txt(dl, bx + 14, by + 8, "REFRESH", (*C["gold_lt"][:3], 240), 18, "raj_sb_18")

    # Phase 3 — filter chips (left of REFRESH).
    chips = (("ALL", None), ("DRAFTS", "DRAFT"), ("INHOUSE", "INHOUSE"),
             ("SCOUT", "SCOUT"), ("RANK", "RANK"))
    chip_w = 72
    chip_h = 28
    chip_gap = 4
    total_chip_w = chip_w * len(chips) + chip_gap * (len(chips) - 1)
    chip_x0 = bx - total_chip_w - 14
    chip_y = (TOP_BAR_H - chip_h) // 2
    for i, (lbl, val) in enumerate(chips):
        cx0 = chip_x0 + i * (chip_w + chip_gap)
        is_active = (_feed.filter_kind == val)
        if is_active:
            luxe.glow(dl, cx0 + chip_w / 2, chip_y + chip_h / 2,
                      chip_h, C["gold"], 34)
            luxe.panel(dl, cx0, chip_y, cx0 + chip_w, chip_y + chip_h,
                       (116, 90, 44, 235), corner=3,
                       border=C["gold"], border_a=215, sheen=80)
            lblc = (*C["gold_lt"][:3], 250)
        else:
            dpg.draw_rectangle((cx0, chip_y), (cx0 + chip_w, chip_y + chip_h),
                               fill=(*C["card"][:3], 180),
                               color=(*C["gold"][:3], 70),
                               rounding=3, parent=dl)
            lblc = (*C["txt2"][:3], 200)
        text_off = max(2, (chip_w - len(lbl) * 8) // 2)
        _txt(dl, cx0 + text_off, chip_y + 6, lbl, lblc, 13, "raj_sb_14")

    # Click — force a sheet refresh OR filter-chip toggle
    if dpg.is_mouse_button_clicked(0):
        mouse = dpg.get_mouse_pos(local=False)
        vp    = dpg.get_viewport_pos()
        rx = mouse[0] - vp[0] - 68     # 68 = collapsed sidebar width
        ry = mouse[1] - vp[1] - 52     # 52 = TITLE_H (app title bar)
        if bx <= rx <= bx + bw and by <= ry <= by + bh:
            _feed.refresh_from_sheet(force=True)
        # Filter chips
        if chip_y <= ry <= chip_y + chip_h:
            for i, (_, val) in enumerate(chips):
                cx0 = chip_x0 + i * (chip_w + chip_gap)
                if cx0 <= rx <= cx0 + chip_w and _feed.filter_kind != val:
                    _feed.filter_kind = val
                    _feed.dirty = True
                    break

    # Position the cards window flush BELOW our local top bar.
    # `vw` is content-area width; viewport sidebar width is (viewport_w - vw).
    sidebar_w = dpg.get_viewport_width() - vw
    win_x     = sidebar_w
    win_y     = _VP_TITLE_H + TOP_BAR_H
    win_w     = vw
    win_h     = max(20, vh - TOP_BAR_H)
    _card_w[0] = max(200, win_w - PAD * 2 - 12)   # minus scrollbar gutter

    if not dpg.does_item_exist(_FEED_WIN):
        _build_feed_window(win_x, win_y, win_w, win_h)
    else:
        dpg.configure_item(_FEED_WIN,
                           pos=(win_x, win_y),
                           width=win_w, height=win_h)
        if _feed.dirty:
            _repopulate_feed()
            _feed.dirty = False


def _build_feed_window(win_x, win_y, win_w, win_h):
    with dpg.window(tag=_FEED_WIN,
                    pos=(win_x, win_y),
                    width=win_w, height=win_h,
                    no_title_bar=True, no_resize=True,
                    no_move=True, no_focus_on_appearing=True,
                    no_scrollbar=False):
        dpg.add_spacer(height=PAD - 4)
        with dpg.group(tag="feed_card_group"):
            _populate_cards()
    _feed.dirty = False


def _repopulate_feed():
    if not dpg.does_item_exist("feed_card_group"):
        return
    dpg.delete_item("feed_card_group", children_only=True)
    _populate_cards()


def _kind_matches_filter(kind, filt):
    """True if an event's kind matches the active filter chip. Treats SCOUT_NEW
    and RESCOUTED as part of the SCOUT bucket; UPDATE as part of RANK."""
    if not filt:
        return True
    k = (kind or "").upper()
    if filt == "SCOUT":   return k in ("SCOUT", "SCOUT_NEW", "RESCOUTED")
    if filt == "RANK":    return k in ("RANK", "UPDATE")
    if filt == "INHOUSE": return k == "INHOUSE"
    if filt == "DRAFT":   return k == "DRAFT"
    return False


def _populate_cards():
    events = _feed.events
    parent = "feed_card_group"

    # Phase 3 — apply filter chip
    if _feed.filter_kind:
        events = [e for e in events
                  if _kind_matches_filter(e.get("kind"), _feed.filter_kind)]

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
    # Loading → skeleton rows that morph into real cards once data lands.
    if _feed.loading and not _feed.sheet_loaded_once:
        dpg.add_spacer(height=PAD, parent=parent)
        w = _card_w[0] + PAD * 2
        for _ in range(6):
            with dpg.drawlist(width=w, height=CARD_H, parent=parent) as _skdl:
                effects.draw_skeleton_row(_skdl, PAD, 4, w - PAD * 2, CARD_H - 8)
            dpg.add_spacer(height=CARD_GAP, parent=parent)
        return
    dpg.add_spacer(height=60, parent=parent)
    if _feed.last_error and not _feed.sheet_loaded_once:
        msg = "Could not reach the Activity sheet. Check your connection and click REFRESH."
    elif _feed.sheet_loaded_once:
        msg = "No activity yet — events will appear here after a SCOUT, DRAFT, or INHOUSE run."
    else:
        msg = "Click REFRESH to load from the Activity sheet."
    t = dpg.add_text(msg, color=C["txt_dim"][:3], parent=parent)
    if "raj_r_14" in _F:
        dpg.bind_item_font(t, _F["raj_r_14"])
    if _feed.last_error and _feed.sheet_loaded_once is False:
        err = dpg.add_text(f"  > {_feed.last_error[:140]}",
                            color=C["loss"][:3], parent=parent)
        if "raj_r_12" in _F:
            dpg.bind_item_font(err, _F["raj_r_12"])


def _draw_date_separator(ts_str, parent):
    dpg.add_spacer(height=6, parent=parent)
    lbl = _date_label(ts_str) if ts_str else ""
    if lbl:
        w = _card_w[0] + PAD * 2
        with dpg.drawlist(width=w, height=SEP_H, parent=parent):
            label_text = lbl.upper()
            label_w = len(label_text) * 8 + 12
            # Date pill background
            dpg.draw_rectangle(
                (PAD, 6), (PAD + label_w, SEP_H - 2),
                fill=(*C["card"][:3], 200),
                color=(*C["gold_dk"][:3], 160),
                rounding=11,
            )
            t = dpg.draw_text((PAD + 8, 8), label_text,
                               color=(*C["gold_lt"][:3], 220), size=14)
            if "raj_sb_14" in _F:
                dpg.bind_item_font(t, _F["raj_sb_14"])
            # Horizontal rule trailing off to the right
            dpg.draw_line((PAD + label_w + 10, SEP_H // 2),
                           (w - PAD, SEP_H // 2),
                           color=(*C["rule_dark"][:3], 120), thickness=1)
    dpg.add_spacer(height=4, parent=parent)


def _draw_event_card(ev, parent):
    kind       = ev.get("kind",    "")
    player     = ev.get("player",  "")
    desc       = ev.get("desc",    "")
    time_ago   = ev.get("time_ago","")

    border_col, icon_text = _kind_color(kind)
    # Was this event flagged as new in the most recent refresh?
    appear_at = _feed._appear_at.get(_event_key(ev))
    is_fresh  = appear_at is not None and (time.monotonic() - appear_at) < 8.0

    w = _card_w[0] + PAD * 2
    with dpg.drawlist(width=w, height=CARD_H, parent=parent) as _cdl:
        # ── Background — V2 gradient panel + kind-color edge wash ─
        bg_outline = (*C["gold"][:3], 220) if is_fresh else (*border_col[:3], 130)
        luxe.panel(_cdl, PAD, 4, w - PAD, CARD_H - 4,
                   (*C["card"][:3], 235), corner=6,
                   border=bg_outline[:3], border_a=bg_outline[3],
                   sheen=40)
        # ── Left accent strip ────────────────────────────────────
        accent_w = 5 if is_fresh else 3
        accent_c = (*C["gold"][:3], 240) if is_fresh else (*border_col[:3], 220)
        dpg.draw_rectangle(
            (PAD, 8), (PAD + accent_w, CARD_H - 8),
            fill=accent_c, color=(0, 0, 0, 0), rounding=2,
        )
        luxe.hfade(_cdl, PAD + accent_w, 8, PAD + int(w * 0.14), CARD_H - 8,
                   accent_c[:3], 24, solid="left")

        # ── Left-side kind chip (colored box with abbreviation) ──
        chip_x = PAD + 14
        chip_y = (CARD_H - ICON_BOX) // 2
        dpg.draw_rectangle(
            (chip_x, chip_y), (chip_x + ICON_BOX, chip_y + ICON_BOX),
            fill=(*border_col[:3], 60),
            color=(*border_col[:3], 200),
            rounding=4,
        )
        ic_label = icon_text or "·"
        ic_w     = len(ic_label) * 7
        ic_tag = dpg.draw_text(
            (chip_x + (ICON_BOX - ic_w) // 2, chip_y + 11), ic_label,
            color=(*border_col[:3], 240), size=13,
        )
        if "raj_sb_14" in _F:
            dpg.bind_item_font(ic_tag, _F["raj_sb_14"])

        # ── Player name + description ────────────────────────────
        text_x = chip_x + ICON_BOX + 14
        # right edge reserved for time-ago + optional NEW badge
        right_pad   = 100
        text_right  = w - PAD - right_pad

        name = (player or "").upper() if player else kind.upper()
        name_tag = dpg.draw_text(
            (text_x, 14), name,
            color=(*C["gold_lt"][:3], 240), size=17,
        )
        if "raj_sb_18" in _F:
            dpg.bind_item_font(name_tag, _F["raj_sb_18"])

        # Description (truncate if it would collide with the time-ago column)
        if desc:
            max_chars = max(20, (text_right - text_x) // 7)
            desc_disp = desc if len(desc) <= max_chars else desc[:max_chars - 1] + "…"
            desc_tag = dpg.draw_text(
                (text_x, 42), desc_disp,
                color=(*C["txt"][:3], 235), size=15,
            )
            if "raj_r_14" in _F:
                dpg.bind_item_font(desc_tag, _F["raj_r_14"])

        # ── Right-side: time-ago + NEW badge ─────────────────────
        if time_ago:
            ta_w = len(time_ago) * 7
            ta_tag = dpg.draw_text(
                (w - PAD - 14 - ta_w, 16), time_ago,
                color=(*C["txt2"][:3], 235), size=14,
            )
            if "raj_sb_14" in _F:
                dpg.bind_item_font(ta_tag, _F["raj_sb_14"])

        if is_fresh:
            badge_label = "NEW"
            bw_label = len(badge_label) * 7 + 12
            bx2 = w - PAD - 14 - bw_label
            by2 = 42
            dpg.draw_rectangle(
                (bx2, by2), (bx2 + bw_label, by2 + 18),
                fill=(*C["gold"][:3], 230),
                color=(0, 0, 0, 0), rounding=9,
            )
            n_tag = dpg.draw_text(
                (bx2 + 6, by2 + 1), badge_label,
                color=(*C["bg"][:3], 245), size=12,
            )
            if "raj_sb_12" in _F:
                dpg.bind_item_font(n_tag, _F["raj_sb_12"])
