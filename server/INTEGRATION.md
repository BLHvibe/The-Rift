# Wiring sync into the Draft Board UI

The server and client module are independent of the existing UI. To make
multiplayer actually visible, four hooks need to land in `ui/draft.py`. Below
is the minimum integration — paste these into a follow-up pass; keep them
guarded by `if sync.active():` so single-player flow is unchanged.

## 1. Imports

Top of `ui/draft.py`:

```python
from data import draft_sync
```

## 2. A small "Join Room" dialog

Add a button somewhere in the draft tab header (or sidebar). When clicked,
open a tiny dialog that collects:

- Server URL (default: the Fly app URL, stored in `config.json` under
  `sync.url`)
- Room code (4-8 chars)
- Password
- Display name
- Slot (dropdown: `blue1..5`, `red1..5`, `spectator`)

On submit, call:

```python
draft_sync.connect(
    url      = cfg_sync_url,
    room     = room_code,
    password = password,
    name     = display_name,
    slot     = chosen_slot,
    on_state = _on_remote_state,
    on_chat  = _on_remote_chat,
    on_error = lambda m: _set_status_bar(f"sync: {m}"),
)
```

## 3. Mirror remote state every frame

In the draft tab's per-frame update (the same function that polls LCU /
redraws), add:

```python
_LAST_REV = 0
_REMOTE_ACTIVE = False

def _tick_sync(board):           # board: DraftBoardState
    global _LAST_REV, _REMOTE_ACTIVE
    client = draft_sync.active()
    if client is None:
        _REMOTE_ACTIVE = False
        return
    snap = client.state()
    if snap is None:
        return
    _REMOTE_ACTIVE = True
    if snap["rev"] == _LAST_REV:
        return
    _LAST_REV = snap["rev"]
    s = snap["state"]
    # Mirror picks/bans/pointer/our_side from the server into the local board.
    board.mirror(s["picks"], s["bans"], s["pointer"], our_side=s["our_side"])
    # Players too, if the host has pushed a pool:
    for side in ("BLUE", "RED"):
        pl = s.get("players", {}).get(side) or []
        if pl:
            for i, p in enumerate(pl[:5]):
                if i < len(board.players[side]):
                    board.players[side][i] = dict(p, role=("TOP","JGL","MID","BOT","SUP")[i])
```

Call `_tick_sync(board)` at the top of the draft tab's frame callback.

## 4. Route local actions through the server

Anywhere the existing UI currently does `board.apply(champ, role)`, gate it:

```python
client = draft_sync.active()
if client is not None:
    # Remote mode: send to server, let the broadcast mirror it back.
    client.apply(champ, role=role)
else:
    # Solo mode: mutate locally.
    board.apply(champ, role)
```

Same wrapper for `undo`, `reset`, and player-pool edits.

## 5. Slot-aware UI affordances

To match "only blue side can make blue picks":

```python
def _can_act(board) -> bool:
    """Is this user authorized to take the current action?"""
    client = draft_sync.active()
    if client is None:
        return True   # solo mode = always yours
    you = client.you()
    slot = you.get("slot", "spectator")
    if slot == "spectator":
        return False
    side_of_slot = "BLUE" if slot.startswith("blue") else "RED"
    act = board.current_action()
    if act is None:
        return False
    return act.side == side_of_slot
```

Use `_can_act(board)` to gray out / disable the champion-select buttons when
it isn't your turn. The server enforces the same rule, but UX is much better
when the UI reflects it before the click.

## 6. Optional: "who's here" rail

`client.state()["slots"]` is `{"blue1": "Alice", "red3": "Bob", ...}`.
`client.state()["spectators"]` is `["Charlie", ...]`. Render those as a small
list under the team headers so everyone sees who's connected.

## 7. Persisting the server URL

Add a single field to the existing settings (`data/config.py` /
`ui/settings.py`):

```python
config["sync"] = {"url": "wss://the-rift-draft-sync.fly.dev"}
```

so users don't retype it.

---

That's the whole integration. The server is the source of truth; the local
`DraftBoardState` becomes a read-through cache while a sync session is
active. When you disconnect (`draft_sync.disconnect()`), the cached state
remains and the board reverts to solo behavior with no further changes.
