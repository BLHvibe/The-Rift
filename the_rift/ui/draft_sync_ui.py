"""
draft_sync_ui.py — UI glue between the Draft Board and `data/draft_sync.py`.

Phase 1+ (post draft-tool rewrite): no room codes, no passwords. Single global
room on Fly.io. `auto_connect()` replaces `show_join_dialog()`. Sides
(BLUE/RED/SPEC) replace slots.

Public surface used by `ui/draft.py`:

    auto_connect(name=None)             → open the singleton sync session
    sync_tick(draft)                    → call every frame; mirrors remote
                                          state into draft.board
    route_apply(draft, champ, role)     → True if remote-routed
    route_undo(draft)                   → True if remote-routed
    route_reassign(draft, side, ...)    → True if remote-routed
    can_act(draft)                      → False ⇒ ignore pick clicks
    presence_text()                     → header status string
    sides_summary()                     → ["BLUE  Alice", "RED  Bob", ...]
    is_active()                         → connected to a sync session
    is_host()                           → we are the room host
    is_started()                        → draft has started (BOARD or DONE)
    in_lobby()                          → in LOBBY phase
    in_scouting() / in_briefing() / in_archetype()  → phase predicates
    my_side()                           → "BLUE" | "RED" | "SPEC" | None
    server_phase()                      → server's current phase string
    connection_status()                 → one-line UI status
    send_set_ready(b)                   → ready-up in lobby
    send_set_scout_ready(b)             → scout-prefetch complete
    send_set_briefing_done(b)           → briefing card dismissed
    send_set_archetype(arch)            → archetype committed (per side)
    send_set_side(side)                 → claim or swap side
    send_set_slot_player(side, idx, p)  → roster slot edit
    disconnect_if_active()              → safe to call on exit
    set_join_callback(fn)               → fired once state arrives
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from data import draft_sync
from data.config import load_config, save_config
from data.draft_board import ROLES as _BOARD_ROLES


# ---------------------------------------------------------------------------
# Module state — single active session at a time
# ---------------------------------------------------------------------------

_last_rev_seen: int = -1
_last_players_sig: Optional[tuple] = None
_join_callback = None
# v3.0.2 bugfix: `_on_state_snapshot` was firing the join callback on every
# server broadcast, not just the first one — so any server-side state update
# (the other client typing, a side flip, a roster edit) would re-run
# `_lobby_begin_synced` and throw the local user back into TEAM_BUILD even
# after they'd hit CANCEL. This flag gates the callback to fire exactly once
# per `auto_connect()` session.
_join_callback_fired: bool = False


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

def auto_connect(name: Optional[str] = None) -> None:
    """Open the singleton sync session. URL is baked into config.py; the
    only per-user input is the display name.

    Calling this when already connected closes the prior session and starts
    fresh.
    """
    cfg = load_config()
    sync_cfg = cfg.get("sync") or {}
    url = sync_cfg.get("url") or "wss://the-rift-draft.fly.dev"

    if not name:
        name = (cfg.get("display_name") or "").strip() or "Player"

    # Persist the chosen display name so a re-connect doesn't ask again.
    if name != (cfg.get("display_name") or ""):
        cfg["display_name"] = name
        save_config(cfg)

    global _last_rev_seen, _last_players_sig, _join_callback_fired
    _last_rev_seen = -1
    _last_players_sig = None
    _join_callback_fired = False        # arm the one-shot for this session

    draft_sync.connect(
        url=url,
        name=name,
        on_state=_on_state_snapshot,
        on_error=_on_error,
    )


def _on_state_snapshot(_snap: Dict[str, Any]) -> None:
    """First snapshot from the server fires the registered join callback.
    Subsequent snapshots are picked up by `sync_tick` each frame — they do
    NOT re-fire the callback, otherwise CANCEL → IDLE would get yanked
    back to TEAM_BUILD on the next server broadcast."""
    global _join_callback_fired
    if _join_callback_fired:
        return
    if _join_callback is None:
        return
    _join_callback_fired = True
    try:
        _join_callback()
    except Exception:
        pass


def _on_error(msg: str) -> None:
    # Errors are surfaced by `connection_status()` reading
    # `draft_sync.active().last_error()`. The UI polls this each frame.
    pass


def set_join_callback(fn) -> None:
    """ui/draft.py registers a callback to fire when the first server
    snapshot arrives (i.e. we've successfully joined the lobby)."""
    global _join_callback
    _join_callback = fn


# ---------------------------------------------------------------------------
# Per-frame mirror
# ---------------------------------------------------------------------------

def sync_tick(draft) -> None:
    """If a sync session is active, fold the latest server snapshot into
    draft.board. Cheap & idempotent — only rev-bumped snapshots do work."""
    client = draft_sync.active()
    if client is None or draft.board is None:
        return
    snap = client.state()
    if snap is None:
        return

    global _last_rev_seen, _last_players_sig

    s = snap.get("state") or {}

    # Mirror players first so engine recompute sees them.
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
# Routing
# ---------------------------------------------------------------------------

def is_active() -> bool:
    return draft_sync.active() is not None


def is_host() -> bool:
    client = draft_sync.active()
    if client is None:
        return False
    try:
        return bool(client.you().get("is_host"))
    except Exception:
        return False


def route_apply(draft, champ: str, role: Optional[str] = None) -> bool:
    """Returns True if the call was forwarded to the sync server. Caller
    MUST NOT also call draft.board.apply when True is returned."""
    client = draft_sync.active()
    if client is None:
        return False
    if not can_act(draft):
        return True
    client.apply(champ, role)
    return True


def route_undo(draft) -> bool:
    client = draft_sync.active()
    if client is None:
        return False
    client.undo()
    return True


def route_reassign(draft, side: str, from_role: str, to_role: str) -> bool:
    client = draft_sync.active()
    if client is None:
        return False
    client.reassign(side, from_role, to_role)
    return True


# ---------------------------------------------------------------------------
# Side / phase queries
# ---------------------------------------------------------------------------

def my_side() -> Optional[str]:
    """The side this client is currently occupying. None if not connected."""
    client = draft_sync.active()
    if client is None:
        return None
    return (client.you() or {}).get("side")


def my_side_idx() -> Optional[Tuple[str, None]]:
    """Legacy compat shim — old code returned ('BLUE', idx_in_slots_0_4).
    Slots are gone; return ('BLUE', None) etc. Roster slots are now driven by
    the host's drag-drop, not by which slot the connection holds."""
    side = my_side()
    return (side, None) if side in ("BLUE", "RED") else None


def server_phase() -> Optional[str]:
    """Server's current phase string, or None if not synced/no state yet."""
    client = draft_sync.active()
    if client is None:
        return None
    snap = client.state()
    if snap is None:
        return None
    return ((snap.get("state") or {}).get("phase"))


def is_started() -> bool:
    """True once the draft has actually started (BOARD or DONE). In solo
    mode (no sync), always True (the existing solo flow keeps working)."""
    client = draft_sync.active()
    if client is None:
        return True
    return server_phase() in ("BOARD", "DONE")


def in_lobby() -> bool:
    """Synced AND in LOBBY phase. UI gates on this to show the lobby."""
    client = draft_sync.active()
    if client is None:
        return False
    return server_phase() == "LOBBY"


def in_scouting() -> bool:
    return is_active() and server_phase() == "SCOUTING"


def in_briefing() -> bool:
    return is_active() and server_phase() == "BRIEFING"


def in_archetype() -> bool:
    return is_active() and server_phase() == "ARCHETYPE"


def is_done() -> bool:
    return is_active() and server_phase() == "DONE"


def can_act(draft) -> bool:
    """In sync mode: is it our side's turn to take the current action?
    In solo mode: always True."""
    client = draft_sync.active()
    if client is None:
        return True
    if draft.board is None or draft.board.is_complete():
        return False
    side = my_side()
    if side not in ("BLUE", "RED"):
        return False
    act = draft.board.current_action()
    if act is None:
        return False
    return act.side == side


def can_start_draft() -> Tuple[bool, str]:
    """Legacy shim — `START DRAFT` is replaced by per-side READY-UP. This now
    reports whether THIS side can ready up (i.e. has claimed a side). Phase 3
    UI will replace the START DRAFT button with two READY buttons."""
    client = draft_sync.active()
    if client is None:
        return False, ""
    snap = client.state()
    if snap is None:
        return False, "connecting…"
    if server_phase() != "LOBBY":
        return False, "already advanced"
    if my_side() not in ("BLUE", "RED"):
        return False, "claim a side first"
    return True, ""


# ---------------------------------------------------------------------------
# Send helpers
# ---------------------------------------------------------------------------

def send_set_side(side: str) -> None:
    client = draft_sync.active()
    if client is not None:
        client.set_side(side)


def send_set_ready(ready: bool = True) -> None:
    client = draft_sync.active()
    if client is not None:
        client.set_ready(ready)


def send_set_scout_ready(ready: bool = True) -> None:
    client = draft_sync.active()
    if client is not None:
        client.set_scout_ready(ready)


def send_set_briefing_done(done: bool = True) -> None:
    client = draft_sync.active()
    if client is not None:
        client.set_briefing_done(done)


def send_set_archetype(archetype: Optional[str]) -> None:
    client = draft_sync.active()
    if client is not None:
        client.set_archetype(archetype)


def send_set_slot_player(side: str, idx: int,
                         player: Dict[str, Any]) -> None:
    client = draft_sync.active()
    if client is not None:
        client.set_slot_player(side, idx, player)


def send_start_draft() -> None:
    """Legacy alias — now translates to set_ready(True). Phase 3 UI will
    expose explicit READY buttons and drop this shim."""
    send_set_ready(True)


# ---------------------------------------------------------------------------
# Presence + status strings
# ---------------------------------------------------------------------------

def presence_text() -> str:
    """Short status string for the board header."""
    client = draft_sync.active()
    if client is None:
        return ""
    snap = client.state()
    you = client.you() or {}
    if snap is None:
        return "sync: connecting…"
    sides = snap.get("sides") or {}
    spectators = snap.get("spectators") or []
    n = len(sides) + len(spectators)
    badge = "host" if you.get("is_host") else "guest"
    side = you.get("side", "?")
    return f"DRAFT · {n} connected · YOU {side} ({badge})"


def sides_summary() -> List[str]:
    """List of "BLUE  Alice", "RED  Bob", "SPEC  Charlie" — for header."""
    client = draft_sync.active()
    out: List[str] = []
    if client is None:
        return out
    snap = client.state()
    if snap is None:
        return out
    sides = snap.get("sides") or {}
    for k in ("BLUE", "RED"):
        if k in sides:
            out.append(f"{k}  {sides[k]}")
    for n in (snap.get("spectators") or []):
        out.append(f"SPEC  {n}")
    return out


# Legacy name kept for compat with any callsite that still references
# `slots_summary`. Phase 3 will rename callsites and remove this alias.
def slots_summary() -> List[str]:
    return sides_summary()


def disconnect_if_active() -> None:
    try:
        draft_sync.disconnect()
    except Exception:
        pass
    global _last_rev_seen, _last_players_sig, _join_callback_fired
    _last_rev_seen = -1
    _last_players_sig = None
    _join_callback_fired = False        # re-arm for the next auto_connect()


def connection_status() -> str:
    """One-line status for the UI:
       ""                                — not synced
       "connecting to the server…"       — WS not up yet, no prior error
       "could not connect: <error>"      — WS down with a known cause
       "connected, waiting for state…"   — WS up, no hello yet
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
    return "connecting to the server…"


# ---------------------------------------------------------------------------
# Legacy shim — `show_join_dialog` is gone. Anything still calling it should
# call `auto_connect()` instead. Keeping a no-op alias prevents crashes if a
# stale reference survives during the Phase 3 UI rewrite.
# ---------------------------------------------------------------------------

def show_join_dialog() -> None:  # pragma: no cover - transitional shim
    auto_connect()
