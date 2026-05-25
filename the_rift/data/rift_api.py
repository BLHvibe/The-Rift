"""
rift_api.py — client for The Rift REST data API (Phase 0d).

Talks to the match store on the Fly server (server/db.py + server/api.py).
The base URL is derived from the existing draft-sync `sync.url` config
(wss -> https), so no extra configuration is needed; an optional `api_token`
config field is sent as a bearer token when the server requires one.

Every call is best-effort: on any failure (server asleep, offline, error) it
returns None / [] so the app keeps working. Calls are blocking — run them in a
background thread, as the rest of the data layer does.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import quote

try:
    import requests
except Exception:                                          # pragma: no cover
    requests = None

from data.config import load_config

_TIMEOUT = 10


def _players_qs(players: Optional[Iterable[str]]) -> str:
    """Encode an optional roster whitelist as `&players=a,b,c`. Returns '' when
    no list is supplied so URL paths stay clean for unfiltered callers."""
    if not players:
        return ""
    parts: List[str] = []
    seen = set()
    for p in players:
        if p is None:
            continue
        s = str(p).strip()
        if s and s not in seen:
            seen.add(s)
            parts.append(s)
    if not parts:
        return ""
    return "&players=" + quote(",".join(parts), safe=",")


def _base_url() -> Optional[str]:
    """REST base URL, derived from the draft-sync websocket URL."""
    cfg = load_config()
    url = ((cfg.get("sync") or {}).get("url") or "").strip()
    if not url:
        return None
    url = url.replace("wss://", "https://").replace("ws://", "http://")
    # Strip any trailing /ws path and slashes — REST lives at the host root.
    return url.split("/ws")[0].rstrip("/")


def _token() -> str:
    return str(load_config().get("api_token", "") or "")


def is_configured() -> bool:
    """True when requests is available and a server URL is known."""
    return requests is not None and _base_url() is not None


def _get(path: str) -> Optional[Any]:
    if not is_configured():
        return None
    try:
        r = requests.get(_base_url() + path, timeout=_TIMEOUT)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def get_stats() -> Optional[Dict[str, Any]]:
    return _get("/api/stats")


def get_matches(source: Optional[str] = None,
                limit: int = 200) -> List[Dict[str, Any]]:
    q = f"?limit={int(limit)}" + (f"&source={source}" if source else "")
    data = _get("/api/matches" + q)
    return (data or {}).get("matches", []) if data else []


def get_match(match_id: str) -> Optional[Dict[str, Any]]:
    return _get(f"/api/matches/{match_id}")


def get_player_matches(name: str, limit: int = 200) -> List[Dict[str, Any]]:
    data = _get(f"/api/players/{name}/matches?limit={int(limit)}")
    return (data or {}).get("matches", []) if data else []


def get_rivalries(name: str, limit: int = 50,
                  players: Optional[Iterable[str]] = None
                  ) -> List[Dict[str, Any]]:
    """Per-opponent h2h records for `name`: list of
    {opponent, games_vs, wins_vs, games_with, wins_with, last_played}.

    `players`, when provided, restricts opponents to that roster whitelist on
    the server side."""
    data = _get(f"/api/players/{name}/rivalries?limit={int(limit)}"
                f"{_players_qs(players)}")
    return (data or {}).get("rivalries", []) if data else []


def get_h2h_matrix(players: Iterable[str]) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Full head-to-head matrix for a roster, in one trip. `players` must be
    riot summoner names (whatever participants.player holds). Returns
    `{player_a: {player_b: {games_vs, wins_vs, games_with, wins_with,
    last_played}, ...}, ...}`. Empty pairs are omitted from the inner dict."""
    qs = _players_qs(players)
    if not qs:
        return {}
    path = "/api/h2h-matrix?" + qs[1:]   # strip leading "&"
    data = _get(path)
    return (data or {}).get("matrix", {}) if data else {}


def get_records(players: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    """League records / superlatives. Each named entry is None (no data
    yet) or a dict with the holder + numeric value + match context.

    `players`, when provided, restricts player-keyed records to that roster
    whitelist (and match-keyed records to matches with at least one eligible
    participant) on the server side."""
    qs = _players_qs(players)
    path = "/api/records" + (("?" + qs[1:]) if qs else "")
    data = _get(path)
    return (data or {}).get("records", {}) if data else {}


def get_export() -> Optional[Dict[str, Any]]:
    """Full DB dump — feeds the Sheet-mirror backup job. Returns None on failure."""
    return _get("/api/export")


def post_matches(matches: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Ingest one or more match dicts. Best-effort; returns the server's
    JSON response, or None / an error dict on failure."""
    if not is_configured() or not matches:
        return None
    headers: Dict[str, str] = {}
    tok = _token()
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    try:
        r = requests.post(f"{_base_url()}/api/matches",
                          json={"matches": matches},
                          headers=headers, timeout=_TIMEOUT)
        if r.status_code == 200:
            return r.json()
        return {"ok": False, "status": r.status_code, "detail": r.text[:200]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Phase 4c — Seasons
# ---------------------------------------------------------------------------

def get_seasons() -> List[Dict[str, Any]]:
    data = _get("/api/seasons")
    return (data or {}).get("seasons", []) if data else []


def get_season_standings(season_id: int,
                         players: Optional[Iterable[str]] = None
                         ) -> Dict[str, Any]:
    qs = _players_qs(players)
    path = f"/api/seasons/{int(season_id)}/standings" + (
        ("?" + qs[1:]) if qs else "")
    return _get(path) or {}


def post_season(name: str, start_at: str,
                end_at: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if not is_configured():
        return None
    headers: Dict[str, str] = {}
    tok = _token()
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    body: Dict[str, Any] = {"name": name, "start_at": start_at}
    if end_at:
        body["end_at"] = end_at
    try:
        r = requests.post(f"{_base_url()}/api/seasons",
                          json=body, headers=headers, timeout=_TIMEOUT)
        if r.status_code == 200:
            return r.json()
        return {"ok": False, "status": r.status_code, "detail": r.text[:200]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Phase 5a — Achievements
# ---------------------------------------------------------------------------

def get_achievement_catalog() -> List[Dict[str, Any]]:
    data = _get("/api/achievements")
    return (data or {}).get("achievements", []) if data else []


def get_player_achievements(name: str) -> List[Dict[str, Any]]:
    if not name:
        return []
    data = _get(f"/api/players/{name}/achievements")
    return (data or {}).get("achievements", []) if data else []


# ---------------------------------------------------------------------------
# Phase 5b — Predictions
# ---------------------------------------------------------------------------

def get_match_predictions(match_id: str) -> List[Dict[str, Any]]:
    if not match_id:
        return []
    data = _get(f"/api/matches/{match_id}/predictions")
    return (data or {}).get("predictions", []) if data else []


def get_prediction_leaderboard(limit: int = 50,
                               players: Optional[Iterable[str]] = None
                               ) -> List[Dict[str, Any]]:
    data = _get(f"/api/predictions/leaderboard?limit={int(limit)}"
                f"{_players_qs(players)}")
    return (data or {}).get("leaderboard", []) if data else []


def post_prediction(match_id: str, voter: str,
                    predicted: str,
                    confidence: Optional[float] = None) -> Optional[Dict[str, Any]]:
    if not is_configured() or not match_id or not voter or not predicted:
        return None
    headers: Dict[str, str] = {}
    tok = _token()
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    body: Dict[str, Any] = {"voter": voter, "predicted": predicted}
    if confidence is not None:
        body["confidence"] = float(confidence)
    try:
        r = requests.post(f"{_base_url()}/api/matches/{match_id}/predictions",
                          json=body, headers=headers, timeout=_TIMEOUT)
        if r.status_code == 200:
            return r.json()
        return {"ok": False, "status": r.status_code, "detail": r.text[:200]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Phase A/B (sheet decommission) — roster + derived aggregates + rankings/scout
# ---------------------------------------------------------------------------
#
# These getters replace `reader.py::_read_sheets` once `load_live_data` is
# flipped over to the REST path. Same return shapes the sheet readers used so
# the rest of the data layer keeps working unchanged.

def get_players_roster() -> Dict[str, Any]:
    """{`players`: [display_name, ...], `summoner_map`: {game_name: display}}.
    Empty dict on failure so callers can fall back to the sheet path."""
    data = _get("/api/players")
    return data or {}


def get_rankings_api(players: Optional[Iterable[str]] = None
                     ) -> List[Dict[str, Any]]:
    """Per-player rankings list (replaces the Final Rankings sheet)."""
    qs = _players_qs(players)
    path = "/api/rankings" + (("?" + qs[1:]) if qs else "")
    data = _get(path)
    return (data or {}).get("rankings", []) if data else []


def get_scout_api(players: Optional[Iterable[str]] = None
                  ) -> List[Dict[str, Any]]:
    """Per-player scout list (replaces the Player Stats sheet read)."""
    qs = _players_qs(players)
    path = "/api/scout" + (("?" + qs[1:]) if qs else "")
    data = _get(path)
    return (data or {}).get("scout", []) if data else []


def get_inhouse_aggregates_api(players: Optional[Iterable[str]] = None
                               ) -> List[Dict[str, Any]]:
    """Per-player customs leaderboard (replaces _InhouseGameLog aggregation)."""
    qs = _players_qs(players)
    path = "/api/inhouse-aggregates" + (("?" + qs[1:]) if qs else "")
    data = _get(path)
    return (data or {}).get("inhouse", []) if data else []


def get_inhouse_champs_api(players: Optional[Iterable[str]] = None
                           ) -> Dict[str, List[Dict[str, Any]]]:
    """Per-player customs champion dict (the engine's #1 comfort signal)."""
    qs = _players_qs(players)
    path = "/api/inhouse-champs" + (("?" + qs[1:]) if qs else "")
    data = _get(path)
    return (data or {}).get("inhouse_champs", {}) if data else {}


def get_primary_roles_api(players: Optional[Iterable[str]] = None
                          ) -> Dict[str, str]:
    """Per-player most-played role from customs."""
    qs = _players_qs(players)
    path = "/api/primary-roles" + (("?" + qs[1:]) if qs else "")
    data = _get(path)
    return (data or {}).get("primary_roles", {}) if data else {}


def get_rank_history_api(players: Optional[Iterable[str]] = None,
                         limit: int = 30
                         ) -> Dict[str, List[Dict[str, Any]]]:
    """Per-player rank-value time series for the sparkline."""
    qs = _players_qs(players)
    path = (f"/api/rank-history?limit={int(limit)}"
            + (qs if qs else ""))
    data = _get(path)
    return (data or {}).get("rank_history", {}) if data else {}


def get_activity_api(limit: int = 200,
                     event_type: Optional[str] = None,
                     actor: Optional[str] = None) -> List[Dict[str, Any]]:
    """Newest-first activity events for the feed (replaces _Activity sheet)."""
    parts = [f"limit={int(limit)}"]
    if event_type:
        parts.append(f"event_type={event_type}")
    if actor:
        parts.append(f"actor={actor}")
    path = "/api/activity?" + "&".join(parts)
    data = _get(path)
    return (data or {}).get("events", []) if data else []


def post_activity_event(event_type: str,
                        actor: Optional[str] = None,
                        details: Optional[str] = None,
                        related: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Append one event to the activity feed."""
    if not is_configured() or not event_type:
        return None
    headers: Dict[str, str] = {}
    tok = _token()
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    body = {"event_type": event_type,
            "actor": actor, "details": details, "related": related}
    try:
        r = requests.post(f"{_base_url()}/api/activity",
                          json=body, headers=headers, timeout=_TIMEOUT)
        if r.status_code == 200:
            return r.json()
        return {"ok": False, "status": r.status_code, "detail": r.text[:200]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_scout_sheet_api(display_name: str) -> Optional[Dict[str, Any]]:
    """One player's full scout-sheet payload (None if missing)."""
    if not display_name:
        return None
    data = _get(f"/api/scout-sheets/{display_name}")
    return (data or {}).get("scout_sheet") if data else None


def get_scout_sheets_batch_api(players: Iterable[str]
                               ) -> Dict[str, Optional[Dict[str, Any]]]:
    """Bulk-fetch many scout-sheet payloads. Missing players come back
    keyed to None so callers can detect 'no scout sheet yet'."""
    qs = _players_qs(players)
    if not qs:
        return {}
    # endpoint expects `?players=…`, _players_qs returns `&players=…`
    data = _get("/api/scout-sheets?" + qs[1:])
    return (data or {}).get("scout_sheets", {}) if data else {}


def post_scout_sheet(display_name: str,
                     payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Replace one player's scout-sheet payload."""
    if not is_configured() or not display_name:
        return None
    headers: Dict[str, str] = {}
    tok = _token()
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    try:
        r = requests.post(f"{_base_url()}/api/scout-sheets",
                          json={"display_name": display_name,
                                "payload": payload or {}},
                          headers=headers, timeout=_TIMEOUT)
        if r.status_code == 200:
            return r.json()
        return {"ok": False, "status": r.status_code, "detail": r.text[:200]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def post_scout_sheets_bulk(rows: List[Dict[str, Any]]
                           ) -> Optional[Dict[str, Any]]:
    """Bulk-write scout-sheet payloads. Each row: {display_name, payload}."""
    if not is_configured() or not rows:
        return None
    headers: Dict[str, str] = {}
    tok = _token()
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    try:
        r = requests.post(f"{_base_url()}/api/scout-sheets",
                          json={"sheets": rows},
                          headers=headers, timeout=_TIMEOUT)
        if r.status_code == 200:
            return r.json()
        return {"ok": False, "status": r.status_code, "detail": r.text[:200]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def post_tier_votes_bulk(votes: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Bulk-import tier votes (one-time backfill from the old Tier Lists
    sheet). Each row: {rater, player, rating}."""
    if not is_configured() or not votes:
        return None
    headers: Dict[str, str] = {}
    tok = _token()
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    try:
        r = requests.post(f"{_base_url()}/api/tier-votes/bulk",
                          json={"votes": votes},
                          headers=headers, timeout=_TIMEOUT)
        if r.status_code == 200:
            return r.json()
        return {"ok": False, "status": r.status_code, "detail": r.text[:200]}
    except Exception as e:
        return {"ok": False, "error": str(e)}
