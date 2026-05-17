"""
draft_sync_ui.py — UI glue between the Draft Board and `data/draft_sync.py`.

Kept separate from `ui/draft.py` so the multiplayer layer is opt-in and the
solo flow stays exactly as it was.

Public surface used by `ui/draft.py`:

    show_join_dialog()                  → opens a DPG modal Join Room window
    sync_tick(draft)                    → call every frame in BOARD; mirrors
                                          remote state into draft.board
    route_apply(draft, champ, role)     → True if remote-routed (caller should
                                          not also call draft.board.apply)
    route_undo(draft)                   → True if remote-routed
    can_act(draft)                      → False ⇒ UI should ignore pick clicks
    presence_text()                     → "ROOM abcd · 3 · YOU blue1 (host)"
                                          or "" when not connected
    disconnect_if_active()              → safe to call on exit
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

import dearpygui.dearpygui as dpg

from data import draft_sync
from data.config import load_config, save_config
from data.draft_board import DraftBoardState, ROLES as _BOARD_ROLES


# ---------------------------------------------------------------------------
# Module state (single-pane UI; one active session at a time)
# ---------------------------------------------------------------------------

_JOIN_WIN = "draft_sync_join_win"
_FIELDS = {
    "url": "draft_sync_field_url",
    "room": "draft_sync_field_room",
    "password": "draft_sync_field_password",
    "name": "draft_sync_field_name",
    "slot": "draft_sync_field_slot",
}
_STATUS_TAG = "draft_sync_field_status"

_SLOTS = [f"blue{i}" for i in range(1, 6)] + \
         [f"red{i}"  for i in range(1, 6)] + \
         ["spectator"]

# Last-applied server revision, so we only fold a snapshot in once.
_last_rev_seen: int = -1
# Signature of the players block we last mirrored — avoids stomping a fresh
# local edit every frame.
_last_players_sig: Optional[tuple] = None


# ---------------------------------------------------------------------------
# Join dialog
# ---------------------------------------------------------------------------

def show_join_dialog() -> None:
    cfg = load_config()
    sync_cfg = (cfg.get("sync") or {})
    defaults = {
        "url": sync_cfg.get("url", "") or "ws://localhost:8000",
        "room": sync_cfg.get("last_room", ""),
        "password": "",
        "name": sync_cfg.get("last_name", "") or "Player",
        "slot": sync_cfg.get("last_slot", "spectator") or "spectator",
    }

    # Rebuild fresh each invocation so defaults take.
    if dpg.does_item_exist(_JOIN_WIN):
        dpg.delete_item(_JOIN_WIN)

    with dpg.window(tag=_JOIN_WIN, label="JOIN SYNCED DRAFT",
                    modal=True, show=True, width=460, height=360,
                    pos=(420, 200), no_resize=True, no_collapse=True,
                    on_close=lambda: dpg.delete_item(_JOIN_WIN)):
        dpg.add_text("Connect to a shared draft session.", wrap=420)
        dpg.add_spacer(height=4)
        dpg.add_text("Server URL", color=(180, 180, 200))
        dpg.add_input_text(tag=_FIELDS["url"],
                          default_value=defaults["url"],
                          width=420,
                          hint="wss://your-app.fly.dev")
        dpg.add_spacer(height=4)
        with dpg.group(horizontal=True):
            with dpg.group():
                dpg.add_text("Room code", color=(180, 180, 200))
                dpg.add_input_text(tag=_FIELDS["room"],
                                  default_value=defaults["room"],
                                  width=140, hint="abcd")
            dpg.add_spacer(width=12)
            with dpg.group():
                dpg.add_text("Password", color=(180, 180, 200))
                dpg.add_input_text(tag=_FIELDS["password"],
                                  default_value=defaults["password"],
                                  width=140, password=True, hint="shared")
        dpg.add_spacer(height=4)
        dpg.add_text("Your name", color=(180, 180, 200))
        dpg.add_input_text(tag=_FIELDS["name"],
                          default_value=defaults["name"], width=240)
        dpg.add_spacer(height=4)
        dpg.add_text("Slot", color=(180, 180, 200))
        dpg.add_combo(tag=_FIELDS["slot"], items=_SLOTS,
                     default_value=defaults["slot"], width=200)
        dpg.add_spacer(height=10)
        dpg.add_text("", tag=_STATUS_TAG, color=(255, 180, 100))
        dpg.add_spacer(height=6)
        with dpg.group(horizontal=True):
            dpg.add_button(label="JOIN / HOST", width=140, height=30,
                          callback=_do_join)
            dpg.add_spacer(width=8)
            dpg.add_button(label="Cancel", width=100, height=30,
                          callback=lambda: dpg.delete_item(_JOIN_WIN))


def _set_status(msg: str) -> None:
    if dpg.does_item_exist(_STATUS_TAG):
        dpg.set_value(_STATUS_TAG, msg)


def _do_join() -> None:
    url      = dpg.get_value(_FIELDS["url"]).strip()
    room     = dpg.get_value(_FIELDS["room"]).strip().lower()
    password = dpg.get_value(_FIELDS["password"])
    name     = dpg.get_value(_FIELDS["name"]).strip() or "Player"
    slot     = dpg.get_value(_FIELDS["slot"])

    if not url:
        _set_status("Server URL is required.")
        return
    if not room:
        _set_status("Room code is required.")
        return
    if slot not in _SLOTS:
        _set_status(f"Invalid slot {slot!r}.")
        return

    _set_status("Connecting…")

    cfg = load_config()
    cfg.setdefault("sync", {})
    cfg["sync"]["url"] = url
    cfg["sync"]["last_room"] = room
    cfg["sync"]["last_name"] = name
    cfg["sync"]["last_slot"] = slot
    save_config(cfg)

    try:
        draft_sync.connect(
            url=url, room=room, password=password,
            name=name, slot=slot,
            on_error=lambda m: _set_status(f"sync: {m}"),
        )
    except Exception as e:
        _set_status(f"connect failed: {e}")
        return

    # Reset mirror state and enter BOARD phase in the existing draft state
    # machine. Caller (ui/draft.py) owns the actual board object — we go
    # through a lazy bridge here. The lobby renderer surfaces ongoing
    # connection state, so we transition out of the dialog immediately
    # rather than blocking the UI thread waiting for hello.
    global _last_rev_seen, _last_players_sig
    _last_rev_seen = -1
    _last_players_sig = None

    _on_join_ok()


def _on_join_ok() -> None:
    """Close the dialog and let ui/draft.py finish entering the BOARD phase.
    Implemented as an indirection so this module doesn't import ui/draft.py."""
    if dpg.does_item_exist(_JOIN_WIN):
        dpg.delete_item(_JOIN_WIN)
    # ui/draft.py installs the actual handler at import time (see
    # `set_join_callback` below).
    if _join_callback is not None:
        try:
            _join_callback()
        except Exception:
            pass


_join_callback = None


def set_join_callback(fn) -> None:
    """ui/draft.py calls this on import so we can transition to BOARD without
    a circular import."""
    global _join_callback
    _join_callback = fn


# ---------------------------------------------------------------------------
# Per-frame mirror
# ---------------------------------------------------------------------------

def sync_tick(draft) -> None:
    """If a sync session is active, fold the server snapshot into
    draft.board. Cheap & idempotent — only rev-bumped snapshots do work."""
    client = draft_sync.active()
    if client is None or draft.board is None:
        return
    snap = client.state()
    if snap is None:
        return

    global _last_rev_seen, _last_players_sig

    s = snap.get("state") or {}

    # Mirror players FIRST (so engine recompute sees them).
    players = s.get("players") or {}
    sig = (
        tuple((p.get("name"), p.get("tier"), p.get("final_score"),
               p.get("score")) for p in (players.get("BLUE") or [])),
        tuple((p.get("name"), p.get("tier"), p.get("final_score"),
               p.get("score")) for p in (players.get("RED") or [])),
    )
    if sig != _last_players_sig:
        _last_players_sig = sig
        for side in ("BLUE", "RED"):
            pl = players.get(side) or []
            if not pl:
                continue
            for i in range(min(5, len(pl))):
                if i < len(draft.board.players[side]):
                    new_p = dict(pl[i])
                    new_p["role"] = _BOARD_ROLES[i]
                    draft.board.players[side][i] = new_p

    rev = int(snap.get("rev", 0))
    if rev <= _last_rev_seen:
        return
    _last_rev_seen = rev

    picks = s.get("picks") or {"BLUE": {}, "RED": {}}
    bans  = s.get("bans")  or {"BLUE": [], "RED": []}
    pointer = int(s.get("pointer", 0))
    our_side = s.get("our_side") or draft.board.our_side

    draft.board.mirror(picks, bans, pointer, our_side=our_side)


# ---------------------------------------------------------------------------
# Routing: send actions to the server instead of mutating locally
# ---------------------------------------------------------------------------

def is_active() -> bool:
    return draft_sync.active() is not None


def route_apply(draft, champ: str, role: Optional[str] = None) -> bool:
    """Returns True if the call was forwarded to the sync server. In that case
    the caller MUST NOT also call draft.board.apply — the broadcast comes back
    via sync_tick and updates the local board uniformly across all clients."""
    client = draft_sync.active()
    if client is None:
        return False
    if not can_act(draft):
        return True  # swallow click — UI shouldn't let this happen, server would 403 anyway
    client.apply(champ, role)
    return True


def route_undo(draft) -> bool:
    client = draft_sync.active()
    if client is None:
        return False
    client.undo()
    return True


# ---------------------------------------------------------------------------
# Slot gating + presence
# ---------------------------------------------------------------------------

def can_act(draft) -> bool:
    """In sync mode: is the current draft action ours to take? In solo mode:
    always True."""
    client = draft_sync.active()
    if client is None:
        return True
    if draft.board is None or draft.board.is_complete():
        return False
    you = client.you()
    slot = you.get("slot", "spectator")
    if not slot or slot == "spectator":
        return False
    side_of_slot = "BLUE" if slot.startswith("blue") else "RED"
    act = draft.board.current_action()
    if act is None:
        return False
    return act.side == side_of_slot


def presence_text() -> str:
    """Short status string for the board header."""
    client = draft_sync.active()
    if client is None:
        return ""
    snap = client.state()
    you = client.you()
    if snap is None:
        return "sync: connecting…"
    slots = snap.get("slots") or {}
    spectators = snap.get("spectators") or []
    n = len(slots) + len(spectators)
    badge = "host" if you.get("is_host") else "guest"
    return f"ROOM {client._room.upper()} · {n} connected · YOU {you.get('slot','?')} ({badge})"


def slots_summary() -> List[str]:
    """List of "blue1 Alice", "red1 Bob", "spectator Charlie" — used by the
    presence rail in the board header."""
    client = draft_sync.active()
    out: List[str] = []
    if client is None:
        return out
    snap = client.state()
    if snap is None:
        return out
    slots = snap.get("slots") or {}
    for k in (f"blue{i}" for i in range(1, 6)):
        if k in slots:
            out.append(f"{k.upper()}  {slots[k]}")
    for k in (f"red{i}"  for i in range(1, 6)):
        if k in slots:
            out.append(f"{k.upper()}  {slots[k]}")
    for n in (snap.get("spectators") or []):
        out.append(f"SPEC   {n}")
    return out


def disconnect_if_active() -> None:
    try:
        draft_sync.disconnect()
    except Exception:
        pass
    global _last_rev_seen, _last_players_sig
    _last_rev_seen = -1
    _last_players_sig = None


# ---------------------------------------------------------------------------
# Lobby helpers (v2.8.1)
# ---------------------------------------------------------------------------

def is_started() -> bool:
    """True once the host has pressed START DRAFT. False in solo mode (the
    caller should fall through to the normal board)."""
    client = draft_sync.active()
    if client is None:
        return True   # solo mode = draft is always "started"
    snap = client.state()
    if snap is None:
        return False
    return bool((snap.get("state") or {}).get("started"))


def in_lobby() -> bool:
    """True iff synced AND not yet started. UI gates on this to show the
    lobby instead of the pick/ban board."""
    client = draft_sync.active()
    if client is None:
        return False
    snap = client.state()
    if snap is None:
        return True    # connected, no hello — show lobby with "connecting…"
    return not bool((snap.get("state") or {}).get("started"))


def can_start_draft() -> Tuple[bool, str]:
    """Returns (can_start, reason). True only when:
      - we're the host
      - lobby hasn't already started
      - at least 1 blue slot and 1 red slot are occupied
    Reason is a short user-facing string for the disabled-state hint."""
    client = draft_sync.active()
    if client is None:
        return False, ""
    snap = client.state()
    if snap is None:
        return False, "connecting…"
    you = client.you()
    if not you.get("is_host"):
        return False, "host only"
    if (snap.get("state") or {}).get("started"):
        return False, "already started"
    slots = snap.get("slots") or {}
    blue_n = sum(1 for k in slots if k.startswith("blue"))
    red_n  = sum(1 for k in slots if k.startswith("red"))
    if blue_n < 1 or red_n < 1:
        return False, f"need ≥1 per side (blue {blue_n}, red {red_n})"
    return True, ""


def send_start_draft() -> None:
    client = draft_sync.active()
    if client is not None:
        client.start_draft()


def send_set_slot_player(side: str, idx: int,
                         player: Dict[str, Any]) -> None:
    client = draft_sync.active()
    if client is not None:
        client.set_slot_player(side, idx, player)


def my_slot_idx() -> Optional[Tuple[str, int]]:
    """('BLUE', 2) if our slot is blue3, etc. None for spectator/unknown."""
    client = draft_sync.active()
    if client is None:
        return None
    slot = (client.you() or {}).get("slot", "")
    if slot.startswith("blue"):
        try:
            return "BLUE", int(slot[-1]) - 1
        except (TypeError, ValueError):
            return None
    if slot.startswith("red"):
        try:
            return "RED", int(slot[-1]) - 1
        except (TypeError, ValueError):
            return None
    return None


def connection_status() -> str:
    """One-line status for the UI:
       ""                                — not synced
       "connecting to <host>…"           — WS not up yet, no prior error
       "could not connect: <error>"      — WS down with a known cause
       "connected, waiting for hello…"   — WS up but server hasn't responded
       "synced"                          — WS up + hello received
    """
    client = draft_sync.active()
    if client is None:
        return ""
    if client.state() is not None:
        return "synced"
    err = client.last_error()
    if client.is_connected():
        return err if err else "connected, waiting for room state…"
    if err:
        return f"could not connect: {err}"
    return "connecting to server…"

