"""
The Rift — Draft Sync Server.

Single-file FastAPI WebSocket server that holds tournament-draft state for a
room of up to 10 players + spectators and fans out every mutation in realtime.

Authorization model
-------------------
A room is created on first connect with a 4-char code + password (chosen by the
host). Anyone with the code+password can connect. On connect, a client claims a
slot — one of:

    blue1..blue5  red1..red5  spectator

Slot determines write rights:
  • slot blueN  -> may write picks/bans only when current draft action.side == BLUE
  • slot redN   -> same, for RED
  • spectator   -> read-only

Player-pool edits (set_players) can be done by anyone on that side.
Reset / undo / our_side are host-only (the host is whichever client created
the room).

State is held in memory only. If the process restarts, rooms are gone — that's
fine for a friends-only tool; restart and rejoin. Add Redis later if needed.

Wire protocol
-------------
All messages are JSON.

Client -> server:
  {"type": "apply",        "champ": "Aatrox", "role": "TOP"}
  {"type": "undo"}
  {"type": "reset"}
  {"type": "set_players",  "side": "BLUE", "players": [...]}
  {"type": "set_our_side", "side": "BLUE"}
  {"type": "set_slot",     "slot": "blue2"}     # leave/reclaim a slot
  {"type": "chat",         "text": "gl hf"}
  {"type": "ping"}

Server -> client:
  {"type": "hello",  "you": {...}, "state": {...}}        # on connect
  {"type": "state",  "state": {...}, "slots": {...}, "rev": N}
  {"type": "chat",   "from": "Alice", "slot": "blue1", "text": "gl hf"}
  {"type": "error",  "msg": "..."}
  {"type": "pong"}

The "state" object on the wire is exactly what The Rift client mirrors into
its local DraftBoardState (see draft_sync.py).
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse


# ---------------------------------------------------------------------------
# Draft sequence (mirror of the_rift/data/draft_board.DRAFT_SEQUENCE).
# Server must enforce side authorization, so it needs to know whose turn it is.
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

VALID_SLOTS = {f"blue{i}" for i in range(1, 6)} | {f"red{i}" for i in range(1, 6)} | {"spectator"}


def slot_side(slot: str) -> Optional[str]:
    if slot.startswith("blue"):
        return "BLUE"
    if slot.startswith("red"):
        return "RED"
    return None


# ---------------------------------------------------------------------------
# Room state
# ---------------------------------------------------------------------------

@dataclass
class DraftState:
    """Authoritative draft state for one room. Wire-compatible JSON shape."""
    picks: Dict[str, Dict[str, str]] = field(
        default_factory=lambda: {"BLUE": {}, "RED": {}})
    bans: Dict[str, List[str]] = field(
        default_factory=lambda: {"BLUE": [], "RED": []})
    pointer: int = 0
    our_side: str = "BLUE"
    # Player pool per side. Each player is an opaque dict mirrored from the
    # client (scout dict: name/tier/score/top_champs/...). Server doesn't
    # interpret it; it just fans out.
    players: Dict[str, List[Dict[str, Any]]] = field(
        default_factory=lambda: {"BLUE": [], "RED": []})
    # Lobby gate. The room sits in lobby (started=False) until the host sends
    # `start_draft`. Apply actions are rejected while !started so an early
    # joiner can't pre-ban accidentally. Set to True at start; reset on reset.
    started: bool = False

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
        if not self.started:
            return False, "draft not started — host must press START DRAFT"
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
            return True, ""

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
        return True, ""

    def undo(self) -> bool:
        if self.pointer <= 0:
            return False
        self.pointer -= 1
        kind, side = DRAFT_SEQUENCE[self.pointer]
        if kind == "ban":
            if self.bans[side]:
                self.bans[side].pop()
        else:
            # Undo the most recently filled role on `side`. We don't keep a
            # history server-side, so reconstruct from sequence: count picks
            # for `side` up to `pointer` -> that's how many roles are filled.
            # The most recent one is the last role added; we approximate by
            # removing the last-inserted dict key (Py3.7+ dict order).
            if self.picks[side]:
                last = next(reversed(self.picks[side]))
                self.picks[side].pop(last)
        return True

    def reset(self) -> None:
        self.picks = {"BLUE": {}, "RED": {}}
        self.bans = {"BLUE": [], "RED": []}
        self.pointer = 0
        self.started = False

    def start(self) -> Tuple[bool, str]:
        if self.started:
            return False, "draft already started"
        self.started = True
        return True, ""

    def set_slot_player(self, side: str, idx: int,
                        player: Dict[str, Any]) -> Tuple[bool, str]:
        """Update one slot (idx 0..4) on `side` with the given player dict.
        Used by the lobby's per-slot name editor."""
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

    def to_json(self) -> Dict[str, Any]:
        return {
            "picks": self.picks,
            "bans": self.bans,
            "pointer": self.pointer,
            "our_side": self.our_side,
            "players": self.players,
            "started": self.started,
            "sequence_len": len(DRAFT_SEQUENCE),
        }


@dataclass
class Client:
    ws: WebSocket
    name: str
    slot: str  # one of VALID_SLOTS
    is_host: bool = False


@dataclass
class Room:
    code: str
    password: str
    state: DraftState = field(default_factory=DraftState)
    clients: Dict[int, Client] = field(default_factory=dict)  # id(ws) -> Client
    host_id: Optional[int] = None
    rev: int = 0       # monotonic state revision; clients can dedupe
    last_active: float = field(default_factory=time.time)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def slots_map(self) -> Dict[str, str]:
        """slot -> player name (for "who's in the room" UI)."""
        out: Dict[str, str] = {}
        for c in self.clients.values():
            if c.slot != "spectator":
                out[c.slot] = c.name
        return out

    def spectators(self) -> List[str]:
        return [c.name for c in self.clients.values() if c.slot == "spectator"]

    def is_slot_taken(self, slot: str, by: Optional[int] = None) -> bool:
        if slot == "spectator":
            return False
        for cid, c in self.clients.items():
            if cid == by:
                continue
            if c.slot == slot:
                return True
        return False


# ---------------------------------------------------------------------------
# Global room registry
# ---------------------------------------------------------------------------

ROOMS: Dict[str, Room] = {}
ROOMS_LOCK = asyncio.Lock()
IDLE_TTL_SECONDS = 6 * 3600   # rooms with no activity for 6h are reaped


async def get_or_create_room(code: str, password: str, host_name: str) -> Tuple[Room, bool, str]:
    """Returns (room, created, error). On wrong password: (None, False, msg)."""
    code = code.strip().lower()
    if not code or len(code) > 16:
        return None, False, "invalid room code"
    async with ROOMS_LOCK:
        room = ROOMS.get(code)
        if room is None:
            room = Room(code=code, password=password)
            ROOMS[code] = room
            return room, True, ""
        if room.password != password:
            return None, False, "wrong password"
        return room, False, ""


async def reap_idle_rooms() -> None:
    while True:
        await asyncio.sleep(600)
        now = time.time()
        async with ROOMS_LOCK:
            dead = [c for c, r in ROOMS.items()
                    if not r.clients and (now - r.last_active) > IDLE_TTL_SECONDS]
            for c in dead:
                ROOMS.pop(c, None)


# ---------------------------------------------------------------------------
# FastAPI app + endpoints
# ---------------------------------------------------------------------------

app = FastAPI(title="The Rift — Draft Sync")


@app.on_event("startup")
async def _startup() -> None:
    asyncio.create_task(reap_idle_rooms())


@app.get("/")
async def root() -> JSONResponse:
    return JSONResponse({
        "service": "the-rift-draft-sync",
        "rooms": len(ROOMS),
        "version": "1.0.0",
    })


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"ok": True})


@app.get("/room/{code}")
async def room_info(code: str) -> JSONResponse:
    """Cheap probe — does the room exist? (Doesn't reveal state.)"""
    code = code.strip().lower()
    r = ROOMS.get(code)
    if r is None:
        return JSONResponse({"exists": False})
    return JSONResponse({
        "exists": True,
        "clients": len(r.clients),
        "slots_taken": list(r.slots_map().keys()),
    })


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

async def _send(ws: WebSocket, msg: Dict[str, Any]) -> None:
    try:
        await ws.send_text(json.dumps(msg, default=str))
    except Exception:
        pass


async def _broadcast(room: Room, msg: Dict[str, Any], skip_id: Optional[int] = None) -> None:
    payload = json.dumps(msg, default=str)
    dead: List[int] = []
    for cid, c in list(room.clients.items()):
        if cid == skip_id:
            continue
        try:
            await c.ws.send_text(payload)
        except Exception:
            dead.append(cid)
    for cid in dead:
        room.clients.pop(cid, None)


async def _broadcast_state(room: Room) -> None:
    room.rev += 1
    await _broadcast(room, {
        "type": "state",
        "state": room.state.to_json(),
        "slots": room.slots_map(),
        "spectators": room.spectators(),
        "host": (room.clients[room.host_id].name
                 if room.host_id and room.host_id in room.clients else None),
        "rev": room.rev,
    })


@app.websocket("/ws/{code}")
async def ws_endpoint(ws: WebSocket, code: str) -> None:
    # Query params: ?password=...&name=...&slot=blue1
    password = ws.query_params.get("password", "")
    name = (ws.query_params.get("name", "") or "anon").strip()[:32]
    slot = (ws.query_params.get("slot", "spectator") or "spectator").strip().lower()

    if slot not in VALID_SLOTS:
        await ws.accept()
        await _send(ws, {"type": "error", "msg": f"invalid slot {slot!r}"})
        await ws.close()
        return

    room, created, err = await get_or_create_room(code, password, name)
    if room is None:
        await ws.accept()
        await _send(ws, {"type": "error", "msg": err or "could not join"})
        await ws.close()
        return

    await ws.accept()
    cid = id(ws)

    async with room.lock:
        if room.is_slot_taken(slot):
            await _send(ws, {
                "type": "error",
                "msg": f"slot {slot} already taken — pick another",
            })
            await ws.close()
            return

        client = Client(ws=ws, name=name, slot=slot, is_host=created)
        room.clients[cid] = client
        if created or room.host_id is None or room.host_id not in room.clients:
            room.host_id = cid
            client.is_host = True
        room.last_active = time.time()

        # Draft rosters are explicit (host drag-and-drop in the lobby), not
        # tied to WebSocket connection slots. We intentionally do NOT auto-
        # populate state.players on connect — the connection slots and the
        # team rosters are decoupled, per v2.8.3 UI separation.

    await _send(ws, {
        "type": "hello",
        "you": {"name": name, "slot": slot, "is_host": client.is_host},
        "state": room.state.to_json(),
        "slots": room.slots_map(),
        "spectators": room.spectators(),
        "rev": room.rev,
    })
    await _broadcast_state(room)

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except Exception:
                await _send(ws, {"type": "error", "msg": "bad json"})
                continue

            mtype = msg.get("type")
            room.last_active = time.time()

            if mtype == "ping":
                await _send(ws, {"type": "pong"})
                continue

            if mtype == "chat":
                text = str(msg.get("text", ""))[:500]
                if not text:
                    continue
                await _broadcast(room, {
                    "type": "chat", "from": client.name, "slot": client.slot,
                    "text": text, "ts": time.time(),
                })
                continue

            if mtype == "set_slot":
                new_slot = (msg.get("slot") or "").strip().lower()
                if new_slot not in VALID_SLOTS:
                    await _send(ws, {"type": "error", "msg": "invalid slot"})
                    continue
                async with room.lock:
                    if room.is_slot_taken(new_slot, by=cid):
                        await _send(ws, {"type": "error",
                                         "msg": f"slot {new_slot} taken"})
                        continue
                    client.slot = new_slot
                await _broadcast_state(room)
                continue

            if mtype == "apply":
                champ = str(msg.get("champ", ""))
                role = msg.get("role")
                # Authorization: which side does the current action belong to?
                act = room.state.current_action()
                if act is None:
                    await _send(ws, {"type": "error", "msg": "draft complete"})
                    continue
                _, action_side = act
                client_side = slot_side(client.slot)
                if client_side != action_side:
                    await _send(ws, {
                        "type": "error",
                        "msg": f"not your turn — current action is {action_side}",
                    })
                    continue
                async with room.lock:
                    ok, err = room.state.apply(champ, role)
                if not ok:
                    await _send(ws, {"type": "error", "msg": err})
                    continue
                await _broadcast_state(room)
                continue

            if mtype == "undo":
                if not client.is_host:
                    await _send(ws, {"type": "error", "msg": "host only"})
                    continue
                async with room.lock:
                    room.state.undo()
                await _broadcast_state(room)
                continue

            if mtype == "reset":
                if not client.is_host:
                    await _send(ws, {"type": "error", "msg": "host only"})
                    continue
                async with room.lock:
                    room.state.reset()
                await _broadcast_state(room)
                continue

            if mtype == "set_our_side":
                if not client.is_host:
                    await _send(ws, {"type": "error", "msg": "host only"})
                    continue
                side = str(msg.get("side", "")).upper()
                if side not in SIDES:
                    await _send(ws, {"type": "error", "msg": "side must be BLUE or RED"})
                    continue
                async with room.lock:
                    room.state.our_side = side
                await _broadcast_state(room)
                continue

            if mtype == "start_draft":
                if not client.is_host:
                    await _send(ws, {"type": "error", "msg": "host only"})
                    continue
                # Require at least 1 connected non-spectator per side.
                slots_filled = {"BLUE": 0, "RED": 0}
                for c in room.clients.values():
                    s = slot_side(c.slot)
                    if s:
                        slots_filled[s] += 1
                if slots_filled["BLUE"] < 1 or slots_filled["RED"] < 1:
                    await _send(ws, {"type": "error",
                                     "msg": "need at least 1 player per side"})
                    continue
                async with room.lock:
                    ok, err = room.state.start()
                if not ok:
                    await _send(ws, {"type": "error", "msg": err})
                    continue
                await _broadcast_state(room)
                continue

            if mtype == "set_slot_player":
                # Host-only: edit any draft-roster slot. Rosters are decoupled
                # from WS connection slots (v2.8.3) — only the host drives
                # team composition from the lobby's drag-and-drop pool.
                if not client.is_host:
                    await _send(ws, {"type": "error", "msg": "host only"})
                    continue
                side = str(msg.get("side", "")).upper()
                try:
                    idx = int(msg.get("idx", -1))
                except (TypeError, ValueError):
                    idx = -1
                player = msg.get("player") or {}
                async with room.lock:
                    ok, err = room.state.set_slot_player(side, idx, player)
                if not ok:
                    await _send(ws, {"type": "error", "msg": err})
                    continue
                await _broadcast_state(room)
                continue

            if mtype == "set_players":
                # Anyone on that side (or host) can update the player pool.
                side = str(msg.get("side", "")).upper()
                if side not in SIDES:
                    await _send(ws, {"type": "error", "msg": "side must be BLUE or RED"})
                    continue
                client_side = slot_side(client.slot)
                if not client.is_host and client_side != side:
                    await _send(ws, {"type": "error",
                                     "msg": f"only {side} side or host can edit {side} players"})
                    continue
                players = msg.get("players") or []
                if not isinstance(players, list):
                    await _send(ws, {"type": "error", "msg": "players must be a list"})
                    continue
                # Trim to 5 and keep them as plain dicts.
                clean: List[Dict[str, Any]] = []
                for p in players[:5]:
                    if isinstance(p, dict):
                        clean.append(p)
                    elif isinstance(p, str):
                        clean.append({"name": p})
                async with room.lock:
                    room.state.players[side] = clean
                await _broadcast_state(room)
                continue

            await _send(ws, {"type": "error", "msg": f"unknown type {mtype!r}"})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        await _send(ws, {"type": "error", "msg": f"server: {e}"})
    finally:
        room.clients.pop(cid, None)
        if room.host_id == cid:
            # Promote oldest remaining client to host.
            if room.clients:
                room.host_id = next(iter(room.clients))
                room.clients[room.host_id].is_host = True
            else:
                room.host_id = None
        try:
            await _broadcast_state(room)
        except Exception:
            pass


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
