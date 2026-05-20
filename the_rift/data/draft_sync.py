"""
draft_sync.py — Client-side WebSocket sync for the Draft Board (Phase 1+).

Connects to the Fly.io-hosted draft sync server (../server/main.py) over
WebSocket in a background thread, mirrors server state into a thread-safe
snapshot, and provides a thread-safe API for sending mutations.

Phase 1 rewrite changes:
  • No room codes, no passwords. Single global room.
  • Slots replaced by sides: "BLUE" / "RED" / "SPEC". Auto-assigned on connect,
    swappable in lobby.
  • New ops: set_side, set_ready, set_scout_ready, set_briefing_done,
    set_archetype. Old set_slot is gone.
  • Connection-state callbacks: on_connecting / on_connected / on_disconnected.
  • State snapshot now carries `phase`, `archetype_self`, `archetype_enemy`,
    `ready`, `scout_ready`, `briefing_done` in addition to the legacy fields.

Usage from the UI (ui/draft.py):

    from data import draft_sync

    sync = draft_sync.connect(
        url="wss://the-rift-draft.fly.dev",
        name="Alice",
        on_state=lambda snap: _request_redraw(),
        on_connecting=lambda: _show_waiting("Connecting…"),
        on_connected=lambda: _show_waiting(None),
    )

    snap = sync.state()
    if snap and snap["rev"] != _last_rev:
        ...

    sync.set_side("RED")          # swap to red if blue is taken
    sync.set_ready(True)          # in LOBBY
    sync.set_archetype("Pick")    # in ARCHETYPE / BOARD
    sync.apply("Aatrox", role="TOP")

    sync.close()
"""

from __future__ import annotations

import asyncio
import json
import queue
import threading
import time
import urllib.parse
from typing import Any, Callable, Dict, List, Optional

try:
    import websockets   # type: ignore
except ImportError:    # pragma: no cover
    websockets = None  # The module is imported lazily; connect() will raise.


_BACKOFF_INITIAL = 1.0
_BACKOFF_MAX     = 15.0


class DraftSyncClient:
    """Background-thread WebSocket client. All public methods are thread-safe."""

    def __init__(self, url: str, name: str,
                 on_state: Optional[Callable[[Dict[str, Any]], None]] = None,
                 on_chat: Optional[Callable[[Dict[str, Any]], None]] = None,
                 on_error: Optional[Callable[[str], None]] = None,
                 on_connecting: Optional[Callable[[], None]] = None,
                 on_connected: Optional[Callable[[], None]] = None,
                 on_disconnected: Optional[Callable[[], None]] = None) -> None:
        if websockets is None:
            raise RuntimeError(
                "the `websockets` package is required for draft_sync — "
                "install with: pip install websockets"
            )

        self._url = url.rstrip("/")
        self._name = name
        self._on_state = on_state
        self._on_chat = on_chat
        self._on_error = on_error
        self._on_connecting = on_connecting
        self._on_connected = on_connected
        self._on_disconnected = on_disconnected

        self._snap: Optional[Dict[str, Any]] = None
        self._snap_lock = threading.Lock()
        self._outgoing: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self._stop = threading.Event()
        self._connected = threading.Event()
        self._you: Dict[str, Any] = {}
        self._last_error: Optional[str] = None

        self._thread = threading.Thread(
            target=self._run, name="draft-sync-ws", daemon=True)
        self._thread.start()

    # --- public, thread-safe API --------------------------------------------

    def state(self) -> Optional[Dict[str, Any]]:
        """Latest server snapshot, or None if we haven't received one yet.
        Shape: {"state": {...}, "sides": {...}, "spectators": [...],
                "host": str|None, "ready": {...}, "scout_ready": {...},
                "briefing_done": {...}, "rev": int}
        Where state is shaped by server.main.DraftState.to_json_for_side."""
        with self._snap_lock:
            return None if self._snap is None else dict(self._snap)

    def you(self) -> Dict[str, Any]:
        """{"name": ..., "side": "BLUE"|"RED"|"SPEC", "is_host": bool}.
        Set on hello."""
        return dict(self._you)

    def is_connected(self) -> bool:
        return self._connected.is_set()

    def last_error(self) -> Optional[str]:
        return self._last_error

    # ----- mutation ops -----

    def set_side(self, side: str) -> None:
        self._send({"type": "set_side", "side": side.upper()})

    def set_ready(self, ready: bool = True) -> None:
        self._send({"type": "set_ready", "ready": bool(ready)})

    def set_scout_ready(self, ready: bool = True) -> None:
        self._send({"type": "set_scout_ready", "ready": bool(ready)})

    def set_briefing_done(self, done: bool = True) -> None:
        self._send({"type": "set_briefing_done", "done": bool(done)})

    def set_archetype(self, archetype: Optional[str]) -> None:
        self._send({"type": "set_archetype",
                    "archetype": archetype if archetype else None})

    def apply(self, champ: str, role: Optional[str] = None) -> None:
        self._send({"type": "apply", "champ": champ, "role": role})

    def undo(self) -> None:
        self._send({"type": "undo"})

    def reassign(self, side: str, from_role: str, to_role: str) -> None:
        self._send({"type": "reassign", "side": side.upper(),
                    "from_role": from_role.upper(),
                    "to_role": to_role.upper()})

    def reset(self) -> None:
        self._send({"type": "reset"})

    def set_players(self, side: str, players: List[Dict[str, Any]]) -> None:
        self._send({"type": "set_players",
                    "side": side.upper(),
                    "players": players})

    def set_slot_player(self, side: str, idx: int,
                        player: Dict[str, Any]) -> None:
        self._send({"type": "set_slot_player",
                    "side": side.upper(),
                    "idx": int(idx),
                    "player": player})

    def chat(self, text: str) -> None:
        self._send({"type": "chat", "text": text})

    def ping(self) -> None:
        self._send({"type": "ping"})

    def close(self) -> None:
        self._stop.set()
        self._outgoing.put({"__stop__": True})

    # --- internals ----------------------------------------------------------

    def _send(self, msg: Dict[str, Any]) -> None:
        self._outgoing.put(msg)

    def _build_ws_url(self) -> str:
        # Accept http(s)://, ws(s)://, or bare host:port — coerce to ws(s)://.
        u = self._url
        if u.startswith("http://"):
            u = "ws://" + u[len("http://"):]
        elif u.startswith("https://"):
            u = "wss://" + u[len("https://"):]
        elif not (u.startswith("ws://") or u.startswith("wss://")):
            u = "ws://" + u
        qs = urllib.parse.urlencode({"name": self._name})
        # Single global room — server accepts any path under /ws.
        return f"{u}/ws?{qs}"

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._main())
        finally:
            loop.close()

    async def _main(self) -> None:
        backoff = _BACKOFF_INITIAL
        while not self._stop.is_set():
            url = self._build_ws_url()
            if self._on_connecting:
                try:
                    self._on_connecting()
                except Exception:
                    pass
            try:
                async with websockets.connect(url, max_size=2**20,
                                              ping_interval=20,
                                              ping_timeout=20) as ws:
                    self._connected.set()
                    backoff = _BACKOFF_INITIAL
                    if self._on_connected:
                        try:
                            self._on_connected()
                        except Exception:
                            pass
                    await asyncio.gather(
                        self._reader(ws),
                        self._writer(ws),
                    )
            except Exception as e:
                self._connected.clear()
                self._last_error = str(e)
                if self._on_error:
                    try:
                        self._on_error(str(e))
                    except Exception:
                        pass
            finally:
                if self._connected.is_set():
                    self._connected.clear()
                    if self._on_disconnected:
                        try:
                            self._on_disconnected()
                        except Exception:
                            pass

            if self._stop.is_set():
                break
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, _BACKOFF_MAX)

    async def _reader(self, ws: Any) -> None:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            t = msg.get("type")

            if t == "hello":
                self._you = msg.get("you") or {}
                self._apply_snapshot(msg)
                continue

            if t == "state":
                self._apply_snapshot(msg)
                continue

            if t == "chat":
                if self._on_chat:
                    try:
                        self._on_chat(msg)
                    except Exception:
                        pass
                continue

            if t == "error":
                self._last_error = msg.get("msg", "")
                if self._on_error:
                    try:
                        self._on_error(self._last_error)
                    except Exception:
                        pass
                continue

            if t == "pong":
                continue

    def _apply_snapshot(self, msg: Dict[str, Any]) -> None:
        with self._snap_lock:
            self._snap = {
                "state":          msg.get("state") or {},
                "sides":          msg.get("sides") or {},
                "spectators":     msg.get("spectators") or [],
                "host":           msg.get("host"),
                "ready":          msg.get("ready") or {},
                "scout_ready":    msg.get("scout_ready") or {},
                "briefing_done": msg.get("briefing_done") or {},
                "rev":            int(msg.get("rev", 0)),
                "ts":             time.time(),
            }
            snap_copy = dict(self._snap)
        if self._on_state:
            try:
                self._on_state(snap_copy)
            except Exception:
                pass

    async def _writer(self, ws: Any) -> None:
        loop = asyncio.get_event_loop()
        while not self._stop.is_set():
            msg = await loop.run_in_executor(None, self._outgoing.get)
            if msg.get("__stop__"):
                try:
                    await ws.close()
                except Exception:
                    pass
                return
            try:
                await ws.send(json.dumps(msg, default=str))
            except Exception:
                self._outgoing.put(msg)
                return


# Module-level convenience: one active client at a time.
_active: Optional[DraftSyncClient] = None
_active_lock = threading.Lock()


def connect(url: str, name: str,
            on_state: Optional[Callable[[Dict[str, Any]], None]] = None,
            on_chat: Optional[Callable[[Dict[str, Any]], None]] = None,
            on_error: Optional[Callable[[str], None]] = None,
            on_connecting: Optional[Callable[[], None]] = None,
            on_connected: Optional[Callable[[], None]] = None,
            on_disconnected: Optional[Callable[[], None]] = None
            ) -> DraftSyncClient:
    """Connect (or reconnect) the singleton client. Closes any prior session."""
    global _active
    with _active_lock:
        if _active is not None:
            try:
                _active.close()
            except Exception:
                pass
        _active = DraftSyncClient(
            url=url, name=name,
            on_state=on_state, on_chat=on_chat, on_error=on_error,
            on_connecting=on_connecting, on_connected=on_connected,
            on_disconnected=on_disconnected,
        )
        return _active


def active() -> Optional[DraftSyncClient]:
    """Currently-connected client, if any."""
    return _active


def disconnect() -> None:
    global _active
    with _active_lock:
        if _active is not None:
            try:
                _active.close()
            except Exception:
                pass
            _active = None
