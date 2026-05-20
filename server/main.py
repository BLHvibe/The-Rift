"""
The Rift — Draft Sync Server (Phase 1 rewrite).

Single-file FastAPI WebSocket server that holds tournament-draft state for ONE
global shared room. No room codes, no passwords. Anyone who connects lands in
the same lobby — first connect grabs BLUE, second grabs RED, everyone else is
SPECTATOR. Sides can swap freely in the lobby until both sides press READY.

Phase model (server is source of truth)
---------------------------------------

    LOBBY      Building rosters + picking sides + readying up
       │       (both BLUE and RED ready → phase advances)
       ▼
    SCOUTING   Each client batched-fetches the 10 scout sheets locally
       │       (both sides report scout_ready → phase advances)
       ▼
    BRIEFING   Snapshot card shown to both sides
       │       (both sides press CONTINUE → phase advances)
       ▼
    ARCHETYPE  Each side picks an archetype on a screen the OTHER side
       │       cannot see (server stores per side, never broadcasts cross-side)
       │       (both sides confirm archetype → phase advances)
       ▼
    BOARD      20-action tournament draft (B-R-B-R-B-R / B1 R1 R2 B2 B3 R3 /
       │       R-B-R-B / R4 B4 B5 R5). Engine recommendations run client-side;
       │       the server only enforces side-turn authorization.
       ▼
    DONE       Pointer == 20. Server reveals both archetypes to both sides.

Authorization model
-------------------

    side BLUE   may apply pick/ban only when current action.side == BLUE
    side RED    may apply pick/ban only when current action.side == RED
    SPECTATOR   read-only
    host        the oldest-still-connected client; can reset / undo /
                set_scout_ready on behalf of either side / archetype-broadcast-
                cross-side at DONE time

Wire protocol
-------------

All messages are JSON.

Client → server:
  {"type": "set_side",        "side": "BLUE" | "RED" | "SPEC"}
  {"type": "set_ready",       "ready": true|false}            # in LOBBY
  {"type": "set_scout_ready", "ready": true|false}            # in SCOUTING
  {"type": "set_briefing_done","done":  true|false}           # in BRIEFING
  {"type": "set_archetype",   "archetype": "Teamfight" | ... | null}  # ARCHETYPE / BOARD
  {"type": "set_players",     "side": "BLUE", "players": [...]}
  {"type": "set_slot_player", "side": "BLUE", "idx": 0, "player": {...}}
  {"type": "apply",           "champ": "Aatrox", "role": "TOP"}
  {"type": "undo"}                                # host only
  {"type": "reassign", "side": "BLUE", "from_role": "TOP", "to_role": "JGL"}
  {"type": "reset"}                                # host only
  {"type": "chat", "text": "gl hf"}
  {"type": "ping"}

Server → client (server tailors state for hidden-archetype info-asymmetry):
  {"type": "hello",  "you": {...}, "state": {...}, "phase": "...", ...}
  {"type": "state",  "state": {...}, "phase": "...", "sides": {...}, "rev": N}
  {"type": "chat",   "from": "Alice", "side": "BLUE", "text": "...", "ts": ...}
  {"type": "error",  "msg": "..."}
  {"type": "pong"}

The "state" object includes:
  picks / bans / pointer / our_side / players / started / phase / sequence_len
  archetype_self   (the receiving client's side's archetype, or null)
  archetype_enemy  (the other side's archetype — null unless phase == DONE)

This file holds zero coupling to the client codebase; the 20-action sequence is
inlined.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse


# ---------------------------------------------------------------------------
# Draft sequence (mirror of the_rift/data/draft_board.DRAFT_SEQUENCE).
# Server enforces side authorization, so it needs to know whose turn it is.
# Kept inline so the server has zero dependency on the client codebase.
# ---------------------------------------------------------------------------

# (kind, side) for each of the 20 tournament-draft actions, in order.
DRAFT_SEQUENCE: List[Tuple[str, str]] = [
    # Ban phase 1: B R B R B R
    ("ban", "BLUE"), ("ban", "RED"), ("ban", "BLUE"),
    ("ban", "RED"),  ("ban", "BLUE"), ("ban", "RED"),
    # Pick phase 1: B | R R | B B | R
    ("pick", "BLUE"),
    ("pick", "RED"),  ("pick", "RED"),
    ("pick", "BLUE"), ("pick", "BLUE"),
    ("pick", "RED"),
    # Ban phase 2: R B R B
    ("ban", "RED"),  ("ban", "BLUE"),
    ("ban", "RED"),  ("ban", "BLUE"),
    # Pick phase 2: R | B B | R
    ("pick", "RED"),
    ("pick", "BLUE"), ("pick", "BLUE"),
    ("pick", "RED"),
]

ROLES = ("TOP", "JGL", "MID", "BOT", "SUP")
SIDES = ("BLUE", "RED")
VALID_SIDES = {"BLUE", "RED", "SPEC"}

# Phases the room can be in. Server is source of truth; clients render based
# on this field.
PHASE_LOBBY     = "LOBBY"
PHASE_SCOUTING  = "SCOUTING"
PHASE_BRIEFING  = "BRIEFING"
PHASE_ARCHETYPE = "ARCHETYPE"
PHASE_BOARD     = "BOARD"
PHASE_DONE      = "DONE"


# ---------------------------------------------------------------------------
# Room state
# ---------------------------------------------------------------------------

@dataclass
class DraftState:
    """Authoritative draft state for the global room. Wire-compatible JSON
    shape (with personalisation applied at broadcast time for hidden
    archetypes)."""
    picks: Dict[str, Dict[str, str]] = field(
        default_factory=lambda: {"BLUE": {}, "RED": {}})
    bans: Dict[str, List[str]] = field(
        default_factory=lambda: {"BLUE": [], "RED": []})
    pointer: int = 0
    our_side: str = "BLUE"  # legacy / cosmetic — not used for auth in Phase 1+
    players: Dict[str, List[Dict[str, Any]]] = field(
        default_factory=lambda: {"BLUE": [], "RED": []})
    # Phase machine — server-controlled. Replaces the v2.8 `started` boolean.
    phase: str = PHASE_LOBBY
    # Per-side archetype selection. Hidden from the other side until DONE.
    archetype: Dict[str, Optional[str]] = field(
        default_factory=lambda: {"BLUE": None, "RED": None})

    def used_champs(self) -> Set[str]:
        used: Set[str] = set()
        for s in SIDES:
            used.update(c for c in self.bans[s] if c)
            used.update(c for c in self.picks[s].values() if c)
        return used

    def open_roles(self, side: str) -> List[str]:
        return [r for r in ROLES if r not in self.picks[side]]

    def current_action(self) -> Optional[Tuple[str, str]]:
        if 0 <= self.pointer < len(DRAFT_SEQUENCE):
            return DRAFT_SEQUENCE[self.pointer]
        return None

    def apply(self, champ: str, role: Optional[str]) -> Tuple[bool, str]:
        if self.phase != PHASE_BOARD:
            return False, f"draft not in BOARD phase (current: {self.phase})"
        act = self.current_action()
        if act is None:
            return False, "draft is complete"
        champ = (champ or "").strip()
        if not champ:
            return False, "missing champ"
        if champ in self.used_champs():
            return False, f"{champ} already used"

        kind, side = act
        if kind == "ban":
            self.bans[side].append(champ)
            self.pointer += 1
        else:
            open_r = self.open_roles(side)
            if role is None:
                if len(open_r) == 1:
                    role = open_r[0]
                else:
                    return False, "role required (multiple slots open)"
            if role not in open_r:
                return False, f"role {role} not open"
            self.picks[side][role] = champ
            self.pointer += 1

        # Auto-advance to DONE on final action.
        if self.pointer >= len(DRAFT_SEQUENCE):
            self.phase = PHASE_DONE
        return True, ""

    def undo(self) -> bool:
        if self.pointer <= 0:
            return False
        # If we're in DONE, rewinding pops us back to BOARD.
        if self.phase == PHASE_DONE:
            self.phase = PHASE_BOARD
        self.pointer -= 1
        kind, side = DRAFT_SEQUENCE[self.pointer]
        if kind == "ban":
            if self.bans[side]:
                self.bans[side].pop()
        else:
            if self.picks[side]:
                last = next(reversed(self.picks[side]))
                self.picks[side].pop(last)
        return True

    def reassign(self, side: str, from_role: str, to_role: str
                 ) -> Tuple[bool, str]:
        if side not in SIDES:
            return False, "bad side"
        if from_role == to_role:
            return False, "same role"
        if from_role not in ROLES or to_role not in ROLES:
            return False, "bad role"
        picks = self.picks[side]
        if from_role not in picks:
            return False, f"no pick in {from_role}"
        champ = picks[from_role]
        other = picks.get(to_role)
        picks[to_role] = champ
        if other is None:
            del picks[from_role]
        else:
            picks[from_role] = other
        return True, ""

    def reset(self) -> None:
        self.picks = {"BLUE": {}, "RED": {}}
        self.bans = {"BLUE": [], "RED": []}
        self.pointer = 0
        self.phase = PHASE_LOBBY
        self.archetype = {"BLUE": None, "RED": None}

    def set_slot_player(self, side: str, idx: int,
                        player: Dict[str, Any]) -> Tuple[bool, str]:
        if side not in SIDES:
            return False, "bad side"
        if not (0 <= idx < 5):
            return False, "slot idx must be 0..4"
        pl = self.players.setdefault(side, [])
        while len(pl) < 5:
            pl.append({"name": "", "tier": "Unranked",
                       "final_score": 50.0, "score": 50.0})
        if isinstance(player, str):
            player = {"name": player}
        merged = dict(pl[idx])
        merged.update(player or {})
        pl[idx] = merged
        return True, ""

    def to_json_for_side(self, viewer_side: str) -> Dict[str, Any]:
        """Serialize state with archetype info-asymmetry applied. The viewer
        sees their OWN side's archetype, and only sees the enemy's when the
        draft is DONE."""
        enemy_side = "RED" if viewer_side == "BLUE" else "BLUE"
        if viewer_side == "SPEC":
            # Spectators see neither until DONE.
            archetype_self = None
            archetype_enemy = None
            if self.phase == PHASE_DONE:
                archetype_self = self.archetype.get("BLUE")
                archetype_enemy = self.archetype.get("RED")
        else:
            archetype_self = self.archetype.get(viewer_side)
            archetype_enemy = (self.archetype.get(enemy_side)
                                if self.phase == PHASE_DONE else None)
        # v3.0.3: our_side is now VIEWER-RELATIVE — each client sees its own
        # claimed side as `our_side`, not the global default. Spectators
        # default to BLUE (they don't have a real side, but the BOARD UI
        # needs *some* anchor; spectator view follows BLUE perspective).
        if viewer_side in SIDES:
            viewer_our_side = viewer_side
        else:
            viewer_our_side = self.our_side
        return {
            "picks": self.picks,
            "bans": self.bans,
            "pointer": self.pointer,
            "our_side": viewer_our_side,
            "players": self.players,
            "phase": self.phase,
            "started": self.phase in (PHASE_BOARD, PHASE_DONE),
            "sequence_len": len(DRAFT_SEQUENCE),
            "archetype_self": archetype_self,
            "archetype_enemy": archetype_enemy,
        }


@dataclass
class Client:
    ws: WebSocket
    name: str
    side: str                  # "BLUE" | "RED" | "SPEC"
    is_host: bool = False
    # Phase gating signals. Per side rather than per client so swapping sides
    # mid-lobby doesn't accidentally fast-forward into SCOUTING with stale
    # readys. Tracked on the Room, not the Client — but Client carries the
    # name for chat / presence display.


@dataclass
class Room:
    """Singleton — there is only ever ONE Room in this server (the global
    room). Kept as a class for code symmetry with the v2.8 codebase."""
    state: DraftState = field(default_factory=DraftState)
    clients: Dict[int, Client] = field(default_factory=dict)  # id(ws) -> Client
    host_id: Optional[int] = None
    rev: int = 0
    last_active: float = field(default_factory=time.time)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    # Per-side phase-gate signals. Required for advancing phases.
    ready:         Dict[str, bool] = field(
        default_factory=lambda: {"BLUE": False, "RED": False})
    scout_ready:   Dict[str, bool] = field(
        default_factory=lambda: {"BLUE": False, "RED": False})
    briefing_done: Dict[str, bool] = field(
        default_factory=lambda: {"BLUE": False, "RED": False})

    def side_claimed_by(self, side: str) -> Optional[int]:
        """Return the cid of the client occupying `side`, or None if unclaimed."""
        if side == "SPEC":
            return None
        for cid, c in self.clients.items():
            if c.side == side:
                return cid
        return None

    def sides_map(self) -> Dict[str, str]:
        """{"BLUE": "Alice", "RED": "Bob"} — for the lobby header."""
        out: Dict[str, str] = {}
        for c in self.clients.values():
            if c.side != "SPEC":
                out[c.side] = c.name
        return out

    def spectators(self) -> List[str]:
        return [c.name for c in self.clients.values() if c.side == "SPEC"]

    def reset_gates(self) -> None:
        """Wipe all phase-gate signals (used on reset / side-swap)."""
        self.ready = {"BLUE": False, "RED": False}
        self.scout_ready = {"BLUE": False, "RED": False}
        self.briefing_done = {"BLUE": False, "RED": False}

    def maybe_advance_phase(self) -> bool:
        """Returns True if phase advanced. Called after any gate update."""
        st = self.state
        if st.phase == PHASE_LOBBY:
            if (self.ready["BLUE"] and self.ready["RED"]
                    and self.side_claimed_by("BLUE") is not None
                    and self.side_claimed_by("RED") is not None):
                st.phase = PHASE_SCOUTING
                return True
        elif st.phase == PHASE_SCOUTING:
            if self.scout_ready["BLUE"] and self.scout_ready["RED"]:
                st.phase = PHASE_BRIEFING
                return True
        elif st.phase == PHASE_BRIEFING:
            if self.briefing_done["BLUE"] and self.briefing_done["RED"]:
                st.phase = PHASE_ARCHETYPE
                return True
        elif st.phase == PHASE_ARCHETYPE:
            if st.archetype["BLUE"] and st.archetype["RED"]:
                st.phase = PHASE_BOARD
                return True
        return False


# ---------------------------------------------------------------------------
# Singleton global room
# ---------------------------------------------------------------------------

ROOM: Room = Room()
ROOM_LOCK = asyncio.Lock()


# ---------------------------------------------------------------------------
# FastAPI app + endpoints
# ---------------------------------------------------------------------------

app = FastAPI(title="The Rift — Draft Sync")


@app.get("/")
async def root() -> JSONResponse:
    return JSONResponse({
        "service": "the-rift-draft-sync",
        "version": "2.0.0",
        "clients": len(ROOM.clients),
        "phase": ROOM.state.phase,
    })


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"ok": True})


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

async def _send(ws: WebSocket, msg: Dict[str, Any]) -> None:
    try:
        await ws.send_text(json.dumps(msg, default=str))
    except Exception:
        pass


async def _send_state_personalised(room: Room, cid: int) -> None:
    """Send the room's state to one client, with archetype info-asymmetry
    applied based on the client's side."""
    c = room.clients.get(cid)
    if c is None:
        return
    payload = {
        "type": "state",
        # v3.0.3: include `you` on every state broadcast so the client can
        # refresh its `_you` snapshot after a set_side without needing a
        # fresh `hello`. Fixes the "YOU: BLUE on a RED client" mismatch.
        "you": {"name": c.name, "side": c.side, "is_host": c.is_host},
        "state": room.state.to_json_for_side(c.side),
        "sides": room.sides_map(),
        "spectators": room.spectators(),
        "host": (room.clients[room.host_id].name
                 if room.host_id and room.host_id in room.clients else None),
        "ready": dict(room.ready),
        "scout_ready": dict(room.scout_ready),
        "briefing_done": dict(room.briefing_done),
        "rev": room.rev,
    }
    await _send(c.ws, payload)


async def _broadcast_state(room: Room) -> None:
    """Bump the revision and send each client a personalised state."""
    room.rev += 1
    dead: List[int] = []
    for cid in list(room.clients.keys()):
        try:
            await _send_state_personalised(room, cid)
        except Exception:
            dead.append(cid)
    for cid in dead:
        room.clients.pop(cid, None)


async def _broadcast_chat(room: Room, msg: Dict[str, Any]) -> None:
    payload = json.dumps(msg, default=str)
    dead: List[int] = []
    for cid, c in list(room.clients.items()):
        try:
            await c.ws.send_text(payload)
        except Exception:
            dead.append(cid)
    for cid in dead:
        room.clients.pop(cid, None)


def _auto_assign_side(room: Room) -> str:
    """Pick the best initial side for a new connection."""
    if room.side_claimed_by("BLUE") is None:
        return "BLUE"
    if room.side_claimed_by("RED") is None:
        return "RED"
    return "SPEC"


@app.websocket("/ws")
@app.websocket("/ws/{_anything}")
async def ws_endpoint(ws: WebSocket, _anything: str = "global") -> None:
    """Single global room. Path param `_anything` is ignored (kept for
    forwards/backwards-compat with old clients that send a room code)."""
    name = (ws.query_params.get("name", "") or "anon").strip()[:32]
    # Optional `side` query param hint, otherwise auto-assign.
    requested_side = (ws.query_params.get("side") or "").strip().upper()

    await ws.accept()
    cid = id(ws)

    async with ROOM.lock:
        side = requested_side if requested_side in VALID_SIDES else ""
        if not side or (side != "SPEC" and ROOM.side_claimed_by(side) is not None):
            side = _auto_assign_side(ROOM)

        client = Client(ws=ws, name=name, side=side)
        ROOM.clients[cid] = client
        if ROOM.host_id is None or ROOM.host_id not in ROOM.clients:
            ROOM.host_id = cid
            client.is_host = True
        ROOM.last_active = time.time()

    # Personalised hello — same shape as state but tagged "hello" so the
    # client can run its one-time on-connect handlers.
    await _send(ws, {
        "type": "hello",
        "you": {"name": name, "side": side, "is_host": client.is_host},
        "state": ROOM.state.to_json_for_side(side),
        "sides": ROOM.sides_map(),
        "spectators": ROOM.spectators(),
        "ready": dict(ROOM.ready),
        "scout_ready": dict(ROOM.scout_ready),
        "briefing_done": dict(ROOM.briefing_done),
        "rev": ROOM.rev,
    })
    await _broadcast_state(ROOM)

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except Exception:
                await _send(ws, {"type": "error", "msg": "bad json"})
                continue

            mtype = msg.get("type")
            ROOM.last_active = time.time()

            # ----- presence / utility -----
            if mtype == "ping":
                await _send(ws, {"type": "pong"})
                continue

            if mtype == "chat":
                text = str(msg.get("text", ""))[:500]
                if not text:
                    continue
                await _broadcast_chat(ROOM, {
                    "type": "chat", "from": client.name, "side": client.side,
                    "text": text, "ts": time.time(),
                })
                continue

            # ----- side selection (LOBBY phase only) -----
            if mtype == "set_side":
                new_side = str(msg.get("side", "")).upper()
                if new_side not in VALID_SIDES:
                    await _send(ws, {"type": "error",
                                     "msg": "side must be BLUE, RED, or SPEC"})
                    continue
                if ROOM.state.phase != PHASE_LOBBY:
                    await _send(ws, {"type": "error",
                                     "msg": "can only change side in LOBBY"})
                    continue
                async with ROOM.lock:
                    if new_side != "SPEC":
                        other = ROOM.side_claimed_by(new_side)
                        if other is not None and other != cid:
                            # True swap: the other player takes MY current
                            # side instead of getting punted to SPEC. Both
                            # ready flags clear so they re-confirm.
                            other_client = ROOM.clients[other]
                            old_side = client.side
                            other_client.side = old_side
                            if old_side in SIDES:
                                ROOM.ready[old_side] = False
                            ROOM.ready[new_side] = False
                    # If leaving a side, also clear that side's ready flag.
                    if client.side != "SPEC" and client.side != new_side:
                        ROOM.ready[client.side] = False
                    client.side = new_side
                await _broadcast_state(ROOM)
                continue

            # ----- phase gate flags -----
            if mtype == "set_ready":
                if ROOM.state.phase != PHASE_LOBBY:
                    await _send(ws, {"type": "error",
                                     "msg": "can only ready up in LOBBY"})
                    continue
                if client.side not in SIDES:
                    await _send(ws, {"type": "error",
                                     "msg": "spectators can't ready up"})
                    continue
                async with ROOM.lock:
                    ROOM.ready[client.side] = bool(msg.get("ready", True))
                    ROOM.maybe_advance_phase()
                await _broadcast_state(ROOM)
                continue

            if mtype == "set_scout_ready":
                if ROOM.state.phase != PHASE_SCOUTING:
                    await _send(ws, {"type": "error",
                                     "msg": "scout_ready only valid in SCOUTING"})
                    continue
                if client.side not in SIDES:
                    continue
                async with ROOM.lock:
                    ROOM.scout_ready[client.side] = bool(msg.get("ready", True))
                    ROOM.maybe_advance_phase()
                await _broadcast_state(ROOM)
                continue

            if mtype == "set_briefing_done":
                if ROOM.state.phase != PHASE_BRIEFING:
                    await _send(ws, {"type": "error",
                                     "msg": "briefing_done only valid in BRIEFING"})
                    continue
                if client.side not in SIDES:
                    continue
                async with ROOM.lock:
                    ROOM.briefing_done[client.side] = bool(msg.get("done", True))
                    ROOM.maybe_advance_phase()
                await _broadcast_state(ROOM)
                continue

            # ----- archetype selection (hidden per side) -----
            if mtype == "set_archetype":
                if ROOM.state.phase not in (PHASE_ARCHETYPE, PHASE_BOARD):
                    await _send(ws, {"type": "error",
                                     "msg": "archetype only valid in ARCHETYPE/BOARD"})
                    continue
                if client.side not in SIDES:
                    await _send(ws, {"type": "error",
                                     "msg": "spectators can't set archetype"})
                    continue
                arch = msg.get("archetype")
                arch = str(arch).strip() if arch else None
                async with ROOM.lock:
                    ROOM.state.archetype[client.side] = arch or None
                    if ROOM.state.phase == PHASE_ARCHETYPE:
                        ROOM.maybe_advance_phase()
                await _broadcast_state(ROOM)
                continue

            # ----- team-roster edits -----
            if mtype == "set_slot_player":
                if not client.is_host:
                    await _send(ws, {"type": "error", "msg": "host only"})
                    continue
                side = str(msg.get("side", "")).upper()
                try:
                    idx = int(msg.get("idx", -1))
                except (TypeError, ValueError):
                    idx = -1
                player = msg.get("player") or {}
                async with ROOM.lock:
                    ok, err = ROOM.state.set_slot_player(side, idx, player)
                if not ok:
                    await _send(ws, {"type": "error", "msg": err})
                    continue
                await _broadcast_state(ROOM)
                continue

            if mtype == "set_players":
                side = str(msg.get("side", "")).upper()
                if side not in SIDES:
                    await _send(ws, {"type": "error",
                                     "msg": "side must be BLUE or RED"})
                    continue
                if not client.is_host and client.side != side:
                    await _send(ws, {"type": "error",
                                     "msg": f"only {side} side or host can edit"})
                    continue
                players = msg.get("players") or []
                if not isinstance(players, list):
                    await _send(ws, {"type": "error",
                                     "msg": "players must be a list"})
                    continue
                clean: List[Dict[str, Any]] = []
                for p in players[:5]:
                    if isinstance(p, dict):
                        clean.append(p)
                    elif isinstance(p, str):
                        clean.append({"name": p})
                async with ROOM.lock:
                    ROOM.state.players[side] = clean
                await _broadcast_state(ROOM)
                continue

            # ----- draft actions (BOARD phase only) -----
            if mtype == "apply":
                champ = str(msg.get("champ", ""))
                role = msg.get("role")
                act = ROOM.state.current_action()
                if act is None:
                    await _send(ws, {"type": "error", "msg": "draft complete"})
                    continue
                _, action_side = act
                if client.side != action_side:
                    await _send(ws, {
                        "type": "error",
                        "msg": f"not your turn — current action is {action_side}",
                    })
                    continue
                async with ROOM.lock:
                    ok, err = ROOM.state.apply(champ, role)
                if not ok:
                    await _send(ws, {"type": "error", "msg": err})
                    continue
                await _broadcast_state(ROOM)
                continue

            if mtype == "undo":
                if not client.is_host:
                    await _send(ws, {"type": "error", "msg": "host only"})
                    continue
                async with ROOM.lock:
                    ROOM.state.undo()
                await _broadcast_state(ROOM)
                continue

            if mtype == "reassign":
                if not client.is_host:
                    await _send(ws, {"type": "error", "msg": "host only"})
                    continue
                side = str(msg.get("side", "")).upper()
                from_role = str(msg.get("from_role", "")).upper()
                to_role = str(msg.get("to_role", "")).upper()
                async with ROOM.lock:
                    ok, err = ROOM.state.reassign(side, from_role, to_role)
                if not ok:
                    await _send(ws, {"type": "error", "msg": err})
                    continue
                await _broadcast_state(ROOM)
                continue

            if mtype == "reset":
                if not client.is_host:
                    await _send(ws, {"type": "error", "msg": "host only"})
                    continue
                async with ROOM.lock:
                    ROOM.state.reset()
                    ROOM.reset_gates()
                await _broadcast_state(ROOM)
                continue

            await _send(ws, {"type": "error", "msg": f"unknown type {mtype!r}"})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        await _send(ws, {"type": "error", "msg": f"server: {e}"})
    finally:
        # Clear the leaving client's side-ready flag so a re-join doesn't
        # ghost-trigger phase advance.
        if cid in ROOM.clients:
            leaving = ROOM.clients[cid]
            if leaving.side in SIDES:
                ROOM.ready[leaving.side] = False
                ROOM.scout_ready[leaving.side] = False
                ROOM.briefing_done[leaving.side] = False
        ROOM.clients.pop(cid, None)
        if ROOM.host_id == cid:
            if ROOM.clients:
                ROOM.host_id = next(iter(ROOM.clients))
                ROOM.clients[ROOM.host_id].is_host = True
            else:
                ROOM.host_id = None
                # Last client out — reset the room to LOBBY so a fresh draft
                # starts when someone reconnects.
                ROOM.state.reset()
                ROOM.reset_gates()
        try:
            await _broadcast_state(ROOM)
        except Exception:
            pass


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
