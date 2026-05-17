"""End-to-end protocol test against a running draft-sync server.

Starts three WebSocket clients (blue1 host, red1, spectator) against
ws://localhost:8000, walks through the full 20-action draft, and asserts:

  • Slot authorization (red can't pick on blue's turn)
  • Broadcast: every client sees every state change
  • Host-only commands (undo) rejected for non-host
  • Player-pool sync
  • Chat fan-out
  • Final draft completes (pointer == 20)

Run while `python main.py` is up on :8000.

Usage:
  python test_e2e.py
Exits 0 on pass, 1 on fail.
"""

from __future__ import annotations

import asyncio
import json
import sys
import urllib.parse
from typing import Any, Dict, List, Optional

import websockets


SERVER = "ws://localhost:8000"
ROOM = "test-room"
PASSWORD = "hunter2"

# Tournament order from main.py / draft_board.py.
# 20 actions in pairs of (kind, side):
DRAFT_SEQUENCE = [
    ("ban", "BLUE"), ("ban", "RED"), ("ban", "BLUE"),
    ("ban", "RED"),  ("ban", "BLUE"), ("ban", "RED"),
    ("pick", "BLUE"),
    ("pick", "RED"),  ("pick", "RED"),
    ("pick", "BLUE"), ("pick", "BLUE"),
    ("pick", "RED"),
    ("ban", "RED"),  ("ban", "BLUE"),
    ("ban", "RED"),  ("ban", "BLUE"),
    ("pick", "RED"),
    ("pick", "BLUE"), ("pick", "BLUE"),
    ("pick", "RED"),
]
ROLES = ("TOP", "JGL", "MID", "BOT", "SUP")


CHAMPS = {
    "BLUE": {
        "ban": ["Yasuo", "Zed", "LeeSin", "Akali", "Riven"],
        "pick": {"TOP": "Aatrox", "JGL": "Vi", "MID": "Ahri",
                 "BOT": "Jinx", "SUP": "Thresh"},
    },
    "RED": {
        "ban": ["Lulu", "Lux", "Soraka", "Braum", "Karma"],
        "pick": {"TOP": "Darius", "JGL": "Graves", "MID": "Syndra",
                 "BOT": "Caitlyn", "SUP": "Leona"},
    },
}


class Client:
    """Tiny WS client that maintains the latest state snapshot + an error log."""

    def __init__(self, name: str, slot: str) -> None:
        self.name = name
        self.slot = slot
        self.ws: Optional[Any] = None
        self.snap: Optional[Dict[str, Any]] = None
        self.you: Dict[str, Any] = {}
        self.errors: List[str] = []
        self.chats: List[Dict[str, Any]] = []
        self._reader_task: Optional[asyncio.Task] = None
        self.rev: int = -1

    async def connect(self) -> None:
        qs = urllib.parse.urlencode({
            "password": PASSWORD, "name": self.name, "slot": self.slot,
        })
        url = f"{SERVER}/ws/{ROOM}?{qs}"
        self.ws = await websockets.connect(url)
        self._reader_task = asyncio.create_task(self._reader())

    async def _reader(self) -> None:
        try:
            async for raw in self.ws:
                msg = json.loads(raw)
                t = msg.get("type")
                if t == "hello":
                    self.you = msg.get("you") or {}
                    self._take_snap(msg)
                elif t == "state":
                    self._take_snap(msg)
                elif t == "error":
                    self.errors.append(msg.get("msg", ""))
                elif t == "chat":
                    self.chats.append(msg)
        except websockets.ConnectionClosed:
            pass

    def _take_snap(self, msg: Dict[str, Any]) -> None:
        self.snap = {
            "state": msg.get("state") or {},
            "slots": msg.get("slots") or {},
            "spectators": msg.get("spectators") or [],
            "host": msg.get("host"),
            "rev": int(msg.get("rev", 0)),
        }
        self.rev = self.snap["rev"]

    async def send(self, msg: Dict[str, Any]) -> None:
        await self.ws.send(json.dumps(msg))

    async def wait_for_rev(self, at_least: int, timeout: float = 2.0) -> None:
        deadline = asyncio.get_event_loop().time() + timeout
        while self.rev < at_least:
            if asyncio.get_event_loop().time() > deadline:
                raise AssertionError(
                    f"{self.name}: timeout waiting for rev>={at_least} "
                    f"(have {self.rev})")
            await asyncio.sleep(0.02)

    async def close(self) -> None:
        if self.ws is not None:
            await self.ws.close()
        if self._reader_task is not None:
            try:
                await asyncio.wait_for(self._reader_task, 1.0)
            except Exception:
                pass


# -- Test helpers ------------------------------------------------------------

PASS = 0
FAIL = 0
FAIL_NOTES: List[str] = []


def check(cond: bool, label: str) -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {label}")
    else:
        FAIL += 1
        FAIL_NOTES.append(label)
        print(f"  FAIL  {label}")


async def wait_all(clients: List[Client], rev: int) -> None:
    await asyncio.gather(*[c.wait_for_rev(rev) for c in clients])


async def main() -> int:
    blue1 = Client("Alice", "blue1")    # host (first to join)
    red1 = Client("Bob", "red1")
    spec = Client("Charlie", "spectator")

    print("\n[setup] connect three clients...")
    await blue1.connect()
    await asyncio.sleep(0.1)
    await red1.connect()
    await asyncio.sleep(0.1)
    await spec.connect()
    await asyncio.sleep(0.2)

    # After all 3 connect, the latest rev is at least 3 (one bump per join).
    await wait_all([blue1, red1, spec], 3)

    print("[hello] verify slot assignment + host election")
    check(blue1.you.get("is_host") is True, "blue1 is host (first joiner)")
    check(red1.you.get("is_host") is False, "red1 is not host")
    check(spec.you.get("is_host") is False, "spec is not host")
    check(blue1.snap["slots"].get("blue1") == "Alice", "blue1 slot recorded")
    check(red1.snap["slots"].get("red1") == "Bob", "red1 slot recorded")
    check("Charlie" in spec.snap["spectators"], "Charlie listed as spectator")

    print("[authz] red1 tries to ban on BLUE's first turn (should fail)")
    err_before = len(red1.errors)
    await red1.send({"type": "apply", "champ": "Sona"})
    await asyncio.sleep(0.15)
    check(len(red1.errors) > err_before, "red1 received error for wrong-side write")
    check(blue1.snap["state"]["pointer"] == 0,
          "pointer unchanged after rejected write")

    print("[authz] spectator tries to ban (should fail)")
    err_before = len(spec.errors)
    await spec.send({"type": "apply", "champ": "Sona"})
    await asyncio.sleep(0.15)
    check(len(spec.errors) > err_before, "spectator received error")

    print("[broadcast] walk the full 20-action sequence using correct sides")
    bi = {"BLUE": 0, "RED": 0}
    pi = {"BLUE": 0, "RED": 0}
    expected_rev = blue1.rev
    for step, (kind, side) in enumerate(DRAFT_SEQUENCE):
        actor = blue1 if side == "BLUE" else red1
        if kind == "ban":
            champ = CHAMPS[side]["ban"][bi[side]]
            bi[side] += 1
            await actor.send({"type": "apply", "champ": champ})
        else:
            role = ROLES[pi[side]]
            champ = CHAMPS[side]["pick"][role]
            pi[side] += 1
            await actor.send({"type": "apply", "champ": champ, "role": role})
        expected_rev += 1
        await wait_all([blue1, red1, spec], expected_rev)
        # Every client must agree on the pointer.
        check(blue1.snap["state"]["pointer"] == step + 1
              and red1.snap["state"]["pointer"] == step + 1
              and spec.snap["state"]["pointer"] == step + 1,
              f"step {step+1}: all clients see pointer={step+1}")

    print("[final] draft complete on all clients")
    check(blue1.snap["state"]["pointer"] == 20, "blue1 pointer == 20")
    check(red1.snap["state"]["pointer"] == 20, "red1 pointer == 20")
    check(spec.snap["state"]["pointer"] == 20, "spec pointer == 20")
    # Picks lock to roles.
    check(blue1.snap["state"]["picks"]["BLUE"].get("TOP") == "Aatrox",
          "BLUE TOP locked to Aatrox")
    check(blue1.snap["state"]["picks"]["RED"].get("SUP") == "Leona",
          "RED SUP locked to Leona")
    # Bans length = 5 each.
    check(len(blue1.snap["state"]["bans"]["BLUE"]) == 5, "BLUE has 5 bans")
    check(len(blue1.snap["state"]["bans"]["RED"]) == 5, "RED has 5 bans")

    print("[host-only] non-host undo rejected, host undo accepted")
    err_before = len(red1.errors)
    await red1.send({"type": "undo"})
    await asyncio.sleep(0.15)
    check(len(red1.errors) > err_before, "red1 undo rejected (not host)")
    pre_rev = blue1.rev
    await blue1.send({"type": "undo"})
    await wait_all([blue1, red1, spec], pre_rev + 1)
    check(blue1.snap["state"]["pointer"] == 19, "host undo brought pointer to 19")

    print("[players] red1 sets RED player pool, all see it")
    pool = [
        {"name": "RedTop", "tier": "Diamond"},
        {"name": "RedJgl", "tier": "Platinum"},
        {"name": "RedMid", "tier": "Diamond"},
        {"name": "RedBot", "tier": "Master"},
        {"name": "RedSup", "tier": "Diamond"},
    ]
    pre_rev = blue1.rev
    await red1.send({"type": "set_players", "side": "RED", "players": pool})
    await wait_all([blue1, red1, spec], pre_rev + 1)
    check(len(blue1.snap["state"]["players"]["RED"]) == 5,
          "all clients see 5 RED players")
    check(blue1.snap["state"]["players"]["RED"][0]["name"] == "RedTop",
          "RED player pool content matches")

    print("[players] red1 tries to set BLUE pool (should fail, not host & not blue)")
    err_before = red1.errors[:]
    await red1.send({"type": "set_players", "side": "BLUE",
                     "players": [{"name": "X"}]})
    await asyncio.sleep(0.15)
    check(len(red1.errors) > len(err_before),
          "red1 blocked from editing BLUE players")

    print("[chat] fan-out")
    chats_before = (len(blue1.chats), len(red1.chats), len(spec.chats))
    await blue1.send({"type": "chat", "text": "gl hf"})
    await asyncio.sleep(0.2)
    check(len(blue1.chats) > chats_before[0]
          and len(red1.chats) > chats_before[1]
          and len(spec.chats) > chats_before[2],
          "chat broadcast to all three clients")
    check(red1.chats[-1].get("from") == "Alice"
          and red1.chats[-1].get("slot") == "blue1",
          "chat carries sender name + slot")

    print("[ping]")
    await blue1.send({"type": "ping"})
    await asyncio.sleep(0.1)
    # No assertion needed; just verify no error was raised.

    print("[slot conflict] new client tries to take blue1 (taken)")
    qs = urllib.parse.urlencode({"password": PASSWORD, "name": "Mallory",
                                 "slot": "blue1"})
    try:
        async with websockets.connect(f"{SERVER}/ws/{ROOM}?{qs}") as ws2:
            msg = json.loads(await asyncio.wait_for(ws2.recv(), 2.0))
            check(msg.get("type") == "error", "second blue1 claim got error")
    except Exception as e:
        check(False, f"slot conflict probe raised: {e}")

    print("[wrong password] rejected")
    qs = urllib.parse.urlencode({"password": "wrong", "name": "Mallory",
                                 "slot": "red2"})
    try:
        async with websockets.connect(f"{SERVER}/ws/{ROOM}?{qs}") as ws2:
            msg = json.loads(await asyncio.wait_for(ws2.recv(), 2.0))
            check(msg.get("type") == "error"
                  and "password" in msg.get("msg", "").lower(),
                  "wrong-password connection rejected")
    except Exception as e:
        check(False, f"wrong-password probe raised: {e}")

    await blue1.close()
    await red1.close()
    await spec.close()

    print(f"\n=== {PASS} passed, {FAIL} failed ===")
    if FAIL:
        for note in FAIL_NOTES:
            print(f"  - {note}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
