"""
draft_lcu.py — League Client (LCU) live champ-select adapter  (L1).

Reads the local League client's lockfile, polls
`/lol-champ-select/v1/session`, and normalises it into a side / role / pick /
ban snapshot the draft board mirrors in live mode.

Design:
  • `parse_session()` is a **pure** function (unit-tested in __main__ with a
    captured-shape session) — no networking, fully deterministic.
  • The networking layer degrades gracefully: no lockfile, client closed, not
    in champ select, or any error → returns None, so live mode always falls
    back to manual entry.
  • Champion id→name uses the existing `patch_ticker` ddragon helper.

Nothing here touches DPG. The poll loop only writes plain attributes that the
render thread reads (same pattern as the Rank-History prediction thread).
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

try:
    import requests
    try:                      # LCU uses a self-signed cert
        requests.packages.urllib3.disable_warnings()  # type: ignore
    except Exception:
        pass
except Exception:             # pragma: no cover
    requests = None  # type: ignore


# LCU assignedPosition → our role codes (matches draft_board.ROLES)
POSITION_ROLE = {
    "top": "TOP", "jungle": "JGL", "middle": "MID",
    "bottom": "BOT", "utility": "SUP",
}
_ROLE_ORDER = ("TOP", "JGL", "MID", "BOT", "SUP")


# ---------------------------------------------------------------------------
# Lockfile discovery + auth
# ---------------------------------------------------------------------------

def _candidate_lockfiles() -> List[str]:
    paths = [
        r"C:\Riot Games\League of Legends\lockfile",
        r"C:\Program Files\Riot Games\League of Legends\lockfile",
        r"C:\Program Files (x86)\Riot Games\League of Legends\lockfile",
    ]
    # Optional explicit override from config (key: "league_path" → install dir)
    try:
        from data.config import load_config
        lp = (load_config() or {}).get("league_path") or ""
        if lp:
            paths.insert(0, os.path.join(lp, "lockfile"))
    except Exception:
        pass
    return paths


def find_lockfile() -> Optional[str]:
    for p in _candidate_lockfiles():
        try:
            if p and os.path.isfile(p):
                return p
        except Exception:
            continue
    return None


def read_lockfile(path: str) -> Optional[Dict[str, str]]:
    """Parse `name:pid:port:password:protocol`."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            parts = f.read().strip().split(":")
        if len(parts) >= 5:
            return {"port": parts[2], "password": parts[3],
                    "protocol": parts[4]}
    except Exception:
        pass
    return None


class LCU:
    """Minimal authenticated LCU HTTP client (localhost only)."""

    def __init__(self, port: str, password: str, protocol: str = "https"):
        self.base = f"{protocol}://127.0.0.1:{port}"
        self.auth = ("riot", password)

    def _get(self, path: str) -> Optional[Any]:
        if requests is None:
            return None
        try:
            r = requests.get(self.base + path, auth=self.auth,
                              verify=False, timeout=2.0)
            if r.status_code == 200:
                return r.json()
        except Exception:
            return None
        return None

    def champ_select(self) -> Optional[Dict[str, Any]]:
        return self._get("/lol-champ-select/v1/session")


def connect() -> Optional[LCU]:
    """Find + read the lockfile and return a client, or None."""
    lf = find_lockfile()
    if not lf:
        return None
    info = read_lockfile(lf)
    if not info:
        return None
    return LCU(info["port"], info["password"],
               info.get("protocol", "https"))


# ---------------------------------------------------------------------------
# Champion id → name (via patch_ticker / ddragon), cached
# ---------------------------------------------------------------------------

_id_to_name: Optional[Dict[str, str]] = None


def champion_id_map() -> Dict[str, str]:
    global _id_to_name
    if _id_to_name:
        return _id_to_name
    try:
        from data import patch_ticker
        patch = patch_ticker.get_patch_version() \
            or patch_ticker._fetch_latest_patch()
        _id_to_name = patch_ticker._fetch_champion_id_to_name(patch) or {}
    except Exception:
        _id_to_name = {}
    return _id_to_name


def _name(cid: Any, id_map: Dict[str, str]) -> str:
    try:
        return id_map.get(str(int(cid)), "") if cid else ""
    except (TypeError, ValueError):
        return ""


# ---------------------------------------------------------------------------
# Pure session parser
# ---------------------------------------------------------------------------

def _side_of_cell(cell_id: int) -> str:
    return "BLUE" if 0 <= cell_id <= 4 else "RED"


def parse_session(session: Optional[Dict[str, Any]],
                  id_map: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """
    Normalise an LCU champ-select session into:
      {
        "in_champ_select": True,
        "our_side": "BLUE"|"RED",
        "players": {"BLUE":[{cellId,name,role,champion}], "RED":[...]},
        "picks":   {"BLUE":{role:champ}, "RED":{...}},
        "bans":    {"BLUE":[champ,...], "RED":[champ,...]},
        "completed": <int actions completed>,
      }
    Returns None when not in champ select / unparseable.
    """
    if not session or "myTeam" not in session:
        return None

    local_cell = session.get("localPlayerCellId", 0)
    try:
        our_side = _side_of_cell(int(local_cell))
    except (TypeError, ValueError):
        our_side = "BLUE"

    players: Dict[str, List[Dict[str, Any]]] = {"BLUE": [], "RED": []}
    picks: Dict[str, Dict[str, str]] = {"BLUE": {}, "RED": {}}

    members = list(session.get("myTeam") or []) + \
        list(session.get("theirTeam") or [])
    # Stable order by cellId so role-fallback is deterministic.
    members.sort(key=lambda m: m.get("cellId", 0))
    side_seen: Dict[str, int] = {"BLUE": 0, "RED": 0}
    for m in members:
        try:
            cell = int(m.get("cellId", 0))
        except (TypeError, ValueError):
            continue
        side = _side_of_cell(cell)
        pos = (m.get("assignedPosition") or "").lower()
        role = POSITION_ROLE.get(pos)
        if not role:
            idx = side_seen[side]
            role = _ROLE_ORDER[idx] if idx < 5 else ""
        side_seen[side] += 1
        champ = _name(m.get("championId"), id_map)
        nm = (m.get("gameName") or m.get("summonerName") or "").strip()
        players[side].append({"cellId": cell, "name": nm,
                              "role": role, "champion": champ})
        if champ and role and role not in picks[side]:
            picks[side][role] = champ

    bans: Dict[str, List[str]] = {"BLUE": [], "RED": []}
    raw_bans = session.get("bans") or {}
    my_b = [_name(c, id_map) for c in (raw_bans.get("myTeamBans") or [])]
    th_b = [_name(c, id_map) for c in (raw_bans.get("theirTeamBans") or [])]
    other = "RED" if our_side == "BLUE" else "BLUE"
    bans[our_side] = [c for c in my_b if c]
    bans[other] = [c for c in th_b if c]

    completed = 0
    for grp in (session.get("actions") or []):
        for a in grp:
            if a.get("completed"):
                completed += 1

    # Phase countdown (seconds left in the current pick/ban window).
    timer_left = 0.0
    try:
        ms = (session.get("timer") or {}).get("adjustedTimeLeftInPhase", 0)
        timer_left = max(0.0, float(ms) / 1000.0)
    except (TypeError, ValueError):
        timer_left = 0.0

    return {
        "in_champ_select": True,
        "our_side": our_side,
        "players": players,
        "picks": picks,
        "bans": bans,
        "completed": completed,
        "timer_left": timer_left,
    }


# ---------------------------------------------------------------------------
# Self-test (python -m data.draft_lcu) — pure parser, no client needed
# ---------------------------------------------------------------------------

def _selftest() -> None:
    idmap = {"266": "Aatrox", "64": "Lee Sin", "103": "Ahri",
             "22": "Ashe", "412": "Thresh", "875": "Sett",
             "238": "Zed", "555": "Pyke", "51": "Caitlyn", "117": "Lulu"}
    session = {
        "localPlayerCellId": 0,
        "myTeam": [
            {"cellId": 0, "championId": 266, "assignedPosition": "top",
             "gameName": "Top1"},
            {"cellId": 1, "championId": 64, "assignedPosition": "jungle"},
            {"cellId": 2, "championId": 0, "assignedPosition": "middle"},
            {"cellId": 3, "championId": 0, "assignedPosition": "bottom"},
            {"cellId": 4, "championId": 0, "assignedPosition": "utility"},
        ],
        "theirTeam": [
            {"cellId": 5, "championId": 875, "assignedPosition": "top"},
            {"cellId": 6, "championId": 0, "assignedPosition": "jungle"},
            {"cellId": 7, "championId": 103, "assignedPosition": "middle"},
            {"cellId": 8, "championId": 51, "assignedPosition": "bottom"},
            {"cellId": 9, "championId": 0, "assignedPosition": "utility"},
        ],
        "bans": {"myTeamBans": [238], "theirTeamBans": [555, 117],
                 "numBans": 10},
        "actions": [
            [{"completed": True, "type": "ban"}],
            [{"completed": True, "type": "ban"}],
            [{"completed": True, "type": "ban"}],
            [{"completed": False, "type": "pick"}],
        ],
    }
    snap = parse_session(session, idmap)
    assert snap and snap["our_side"] == "BLUE", snap
    assert snap["picks"]["BLUE"]["TOP"] == "Aatrox", snap["picks"]
    assert snap["picks"]["BLUE"]["JGL"] == "Lee Sin"
    assert snap["picks"]["RED"]["TOP"] == "Sett"
    assert snap["picks"]["RED"]["MID"] == "Ahri"
    assert snap["picks"]["RED"]["BOT"] == "Caitlyn"
    assert snap["bans"]["BLUE"] == ["Zed"], snap["bans"]
    assert snap["bans"]["RED"] == ["Pyke", "Lulu"], snap["bans"]
    assert snap["completed"] == 3, snap["completed"]
    assert parse_session(None, idmap) is None
    assert parse_session({}, idmap) is None

    # Role fallback when assignedPosition is blank
    s2 = {"localPlayerCellId": 7, "theirTeam": [], "myTeam": [
        {"cellId": 5, "championId": 22, "assignedPosition": ""},
    ], "bans": {}, "actions": []}
    snap2 = parse_session(s2, idmap)
    assert snap2["our_side"] == "RED", snap2["our_side"]
    assert snap2["players"]["RED"][0]["role"] == "TOP", snap2["players"]
    assert snap2["picks"]["RED"].get("TOP") == "Ashe"

    print("draft_lcu OK - parse_session: sides, roles, picks, bans, "
          "completed count, blank-position fallback, None guards.")


if __name__ == "__main__":
    _selftest()
