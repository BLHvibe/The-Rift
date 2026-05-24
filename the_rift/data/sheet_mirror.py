"""
sheet_mirror.py — backup the REST data API's DB to Google Sheets (Phase 1).

Pulls `/api/export` from the Rift server and writes a faithful snapshot of the
SQLite store to three dedicated tabs in the same spreadsheet the rest of the
app already uses. This is the "Sheet kept as backup" half of the Phase 0d /
Phase 1 backend plan — if the Fly volume ever loses data, the sheet is the
human-readable restore source.

Mirror tabs (all owned by this module — anything in them is overwritten on
refresh; never edit by hand):
  _RiftDB_Matches      : full row per match
  _RiftDB_Participants : full row per player-in-match
  _RiftDB_Drafts       : full row per match-with-draft

Everything is best-effort and runs on a background thread. Failures (server
asleep, sheet quota, creds missing) are caught and surfaced via on_error so
the caller's main flow can never be blocked.
"""
from __future__ import annotations

import json
import threading
from typing import Any, Callable, Dict, List, Optional

from data.config import load_config
from data import rift_api


_MATCH_HEADERS = [
    "id", "source", "queue", "patch", "duration",
    "started_at", "winner", "ingested_at",
]
_PARTICIPANT_HEADERS = [
    "match_id", "slot", "player", "riot_id", "team", "role", "champion",
    "win", "kills", "deaths", "assists", "cs", "gold", "damage", "vision",
]
_DRAFT_HEADERS = [
    "match_id", "blue_bans", "red_bans", "blue_picks", "red_picks",
]


def _row(d: Dict[str, Any], headers: List[str]) -> List[Any]:
    """Project a dict onto a header order, stringifying lists/dicts."""
    out: List[Any] = []
    for k in headers:
        v = d.get(k)
        if isinstance(v, (list, dict)):
            v = json.dumps(v, separators=(",", ":"))
        elif v is None:
            v = ""
        out.append(v)
    return out


def _write_tab(sh: Any, title: str, headers: List[str],
               rows: List[List[Any]]) -> None:
    """Overwrite the named sheet with (headers + rows). Creates it if absent."""
    try:
        ws = sh.worksheet(title)
        ws.clear()
    except Exception:
        ws = sh.add_worksheet(title=title, rows=max(len(rows) + 10, 50),
                              cols=max(len(headers), 10))
    body = [headers] + rows
    if body:
        ws.update(values=body, range_name="A1")


_ROLE_MAP_BACKFILL = {
    "TOP": "TOP", "JGL": "JGL", "MID": "MID", "BOT": "BOT", "SUP": "SUP",
    # tolerate the verbose forms in case any rows were written that way:
    "JUNGLE": "JGL", "MIDDLE": "MID", "BOTTOM": "BOT",
    "UTILITY": "SUP", "SUPPORT": "SUP",
}


def _truthy(s: Any) -> bool:
    return str(s).strip().lower() in ("true", "1", "yes", "y", "t")


def _int_or_zero(v: Any) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return 0


def _started_at_iso(ts: str) -> str:
    """Convert sheet 'YYYY-MM-DD HH:MM' to ISO 'YYYY-MM-DDTHH:MM:00' so the DB
    can sort matches by time."""
    s = (ts or "").strip().replace(" ", "T")
    return f"{s}:00" if (len(s) == 16 and s[10] == "T") else s


def _matches_from_log_rows(rows: List[List[str]]) -> List[Dict[str, Any]]:
    """Reconstruct match-API dicts from raw `_InhouseGameLog` rows.

    Rows are flat per-participant; ten rows per game keyed by `gameId`. Anything
    the sheet doesn't store (gameVersion / riot tagLine) defaults to a safe blank.
    Returns only games with 10 participants — partial games are skipped.
    """
    by_game: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        if len(r) < 16 or not r[0]:
            continue
        gid       = str(r[0]).strip()
        timestamp = r[1] if len(r) > 1 else ""
        player    = r[2] if len(r) > 2 else "Unknown"
        champion  = r[3] if len(r) > 3 else ""
        team_id   = _int_or_zero(r[4])
        win       = _truthy(r[5])
        kills     = _int_or_zero(r[6])
        deaths    = _int_or_zero(r[7])
        assists   = _int_or_zero(r[8])
        cs        = _int_or_zero(r[9])
        damage    = _int_or_zero(r[10])
        gold      = _int_or_zero(r[11])
        vision    = _int_or_zero(r[12])
        role_raw  = str(r[13] if len(r) > 13 else "").strip().upper()
        role      = _ROLE_MAP_BACKFILL.get(role_raw, "")
        duration_min = 0.0
        try:
            duration_min = float(r[14])
        except (TypeError, ValueError):
            pass

        game = by_game.setdefault(gid, {
            "id":         gid,
            "source":     "inhouse",
            "queue":      "CUSTOM",
            "patch":      "",
            "duration":   int(round(duration_min * 60)),
            "started_at": _started_at_iso(timestamp),
            "winner":     "",
            "participants": [],
            "_team_slot": {100: 0, 200: 0},
        })
        team = "blue" if team_id == 100 else ("red" if team_id == 200 else "spec")
        game["_team_slot"][team_id] = game["_team_slot"].get(team_id, 0) + 1
        if win and not game["winner"]:
            game["winner"] = team
        game["participants"].append({
            "player":   player,
            "riot_id":  player,
            "team":     team,
            "slot":     game["_team_slot"][team_id],   # 1..5 within team
            "role":     role,                          # may be empty
            "champion": champion,
            "win":      1 if win else 0,
            "kills":    kills, "deaths": deaths, "assists": assists,
            "cs":       cs, "gold": gold, "damage": damage, "vision": vision,
        })

    # Drop the helper slot map and skip partial games.
    out: List[Dict[str, Any]] = []
    for g in by_game.values():
        g.pop("_team_slot", None)
        if len(g["participants"]) == 10:
            out.append(g)
    return out


def backfill_from_sheets(chunk: int = 50,
                         on_progress: Optional[Callable[[str], None]] = None,
                         on_done: Optional[Callable[[Dict[str, int]], None]] = None,
                         on_error: Optional[Callable[[str], None]] = None) -> None:
    """Read every row of `_InhouseGameLog` and POST the games into `/api/matches`.

    Idempotent — the server upserts on match id, so re-running is safe and is the
    way to "catch up" after a Fly volume reset. Runs on a background thread."""

    def _bg() -> None:
        try:
            if not rift_api.is_configured():
                if on_error: on_error("Rift API not configured (no server URL)")
                return

            from data.reader import _gspread_connect
            cfg = load_config()
            if on_progress: on_progress("Connecting to sheet…")
            sh = _gspread_connect(cfg)
            try:
                ws = sh.worksheet("_InhouseGameLog")
            except Exception:
                if on_error: on_error("'_InhouseGameLog' sheet not found")
                return

            if on_progress: on_progress("Reading rows…")
            rows = ws.get_all_values()[1:]      # skip header
            matches = _matches_from_log_rows(rows)
            if not matches:
                if on_done: on_done({"games_found": 0, "ingested": 0, "failed": 0})
                return

            ingested = 0
            failed = 0
            for i in range(0, len(matches), max(1, int(chunk))):
                batch = matches[i:i + chunk]
                if on_progress:
                    on_progress(f"Posting games {i + 1}-{i + len(batch)} of {len(matches)}…")
                resp = rift_api.post_matches(batch)
                if isinstance(resp, dict) and resp.get("ok"):
                    ingested += int(resp.get("ingested", len(batch)))
                else:
                    failed += len(batch)
                    print(f"[rift-backfill] batch failed: {resp}")

            if on_done:
                on_done({"games_found": len(matches),
                         "ingested": ingested, "failed": failed})
        except Exception as e:
            if on_error: on_error(str(e))

    threading.Thread(target=_bg, daemon=True, name="rift_sheet_backfill").start()


def full_refresh(on_progress: Optional[Callable[[str], None]] = None,
                 on_done: Optional[Callable[[Dict[str, int]], None]] = None,
                 on_error: Optional[Callable[[str], None]] = None) -> None:
    """Pull `/api/export` and rewrite the three mirror tabs. Runs in the
    background; calls one of on_done / on_error when finished."""

    def _bg() -> None:
        try:
            if not rift_api.is_configured():
                if on_error: on_error("Rift API not configured (no server URL)")
                return

            if on_progress: on_progress("Pulling DB export from server…")
            dump = rift_api.get_export()
            if dump is None:
                if on_error: on_error("Server unreachable or returned no data")
                return

            matches      = dump.get("matches") or []
            participants = dump.get("participants") or []
            drafts       = dump.get("drafts") or []

            # Connect to the same spreadsheet the rest of the app uses.
            # We import lazily so this module loads cheaply when gspread isn't
            # installed (the data API still works without sheet backup).
            from data.reader import _gspread_connect
            cfg = load_config()
            if on_progress: on_progress("Connecting to backup sheet…")
            sh = _gspread_connect(cfg)

            if on_progress: on_progress(f"Writing {len(matches)} matches…")
            _write_tab(sh, "_RiftDB_Matches", _MATCH_HEADERS,
                       [_row(m, _MATCH_HEADERS) for m in matches])

            if on_progress: on_progress(f"Writing {len(participants)} participants…")
            _write_tab(sh, "_RiftDB_Participants", _PARTICIPANT_HEADERS,
                       [_row(p, _PARTICIPANT_HEADERS) for p in participants])

            if on_progress: on_progress(f"Writing {len(drafts)} drafts…")
            _write_tab(sh, "_RiftDB_Drafts", _DRAFT_HEADERS,
                       [_row(d, _DRAFT_HEADERS) for d in drafts])

            counts = {"matches":      len(matches),
                      "participants": len(participants),
                      "drafts":       len(drafts)}
            if on_done: on_done(counts)
        except Exception as e:
            if on_error: on_error(str(e))

    threading.Thread(target=_bg, daemon=True, name="rift_sheet_mirror").start()
