"""
engine_api.py — client lib for the Phase 2 server-side draft engine.

Mirrors the local engine entry points used by ui/draft.py and ui/board_rail.py,
but talks to /api/engine/* on the Rift server. Every call is blocking — run
on a background thread, the way the rest of the data layer does — and best-
effort: any failure (server asleep, network blip, schema mismatch) returns
None so the caller can fall back to its local computation.

This is the bridge that lets the engine cutover happen incrementally: we can
flip one call site at a time to the server, validate the result matches the
local engine within tolerance, and only retire the local code once every
caller is server-backed.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    import requests
except Exception:                                          # pragma: no cover
    requests = None

from data import rift_api

_TIMEOUT = 12


def _base() -> Optional[str]:
    return rift_api._base_url()


def _headers() -> Dict[str, str]:
    h: Dict[str, str] = {}
    tok = rift_api._token()
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    return h


def _post(path: str, body: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not rift_api.is_configured():
        return None
    try:
        r = requests.post(_base() + path, json=body,
                          headers=_headers(), timeout=_TIMEOUT)
        if r.status_code == 200:
            return r.json()
        return None
    except Exception:
        return None


def _get(path: str) -> Optional[Dict[str, Any]]:
    if not rift_api.is_configured():
        return None
    try:
        r = requests.get(_base() + path, timeout=_TIMEOUT)
        if r.status_code == 200:
            return r.json()
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Info + refresh
# ---------------------------------------------------------------------------

def info() -> Optional[Dict[str, Any]]:
    return _get("/api/engine/info")


def refresh_signals() -> Optional[Dict[str, Any]]:
    return _post("/api/engine/refresh_signals", {})


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------

def score_team(champs: List[str],
               comforts: Optional[List[float]] = None,
               arch_name: str = "",
               enemy_picks: Optional[List[str]] = None,
               ) -> Optional[Dict[str, float]]:
    return _post("/api/engine/score_team", {
        "champs":   champs,
        "comforts": comforts or [1.0] * len(champs),
        "arch_name": arch_name,
        "enemy_picks": enemy_picks or [],
    })


def synergy_score(champs: List[str]) -> Optional[float]:
    r = _post("/api/engine/synergy", {"champs": champs})
    return None if r is None else r.get("score")


def counter_score(champ: str, enemies: List[str]) -> Optional[float]:
    r = _post("/api/engine/counter", {"champ": champ, "enemies": enemies})
    return None if r is None else r.get("score")


def enemy_weakness_vector(enemy_champs: List[str]) -> Optional[Dict[str, float]]:
    r = _post("/api/engine/weakness", {"enemy_champs": enemy_champs})
    return None if r is None else r.get("vector")


# ---------------------------------------------------------------------------
# Recommenders
# ---------------------------------------------------------------------------

def recommend_comps(players: List[Dict[str, Any]],
                    inhouse_champs: Optional[Dict[str, List[Dict[str, Any]]]] = None,
                    primary_roles: Optional[Dict[str, str]] = None,
                    enemy_picks: Optional[List[str]] = None,
                    n_results: int = 5,
                    scout_champs: Optional[Dict[str, List[Dict[str, Any]]]] = None,
                    ) -> Optional[List[Dict[str, Any]]]:
    r = _post("/api/engine/recommend_comps", {
        "players": players,
        "inhouse_champs": inhouse_champs,
        "primary_roles": primary_roles,
        "n_results": n_results,
        "enemy_picks": enemy_picks or [],
        "scout_champs": scout_champs,
    })
    return None if r is None else r.get("comps")


def recommend_bans(opposing_players: List[Dict[str, Any]],
                   inhouse_champs: Optional[Dict[str, List[Dict[str, Any]]]] = None,
                   own_picks: Optional[List[str]] = None,
                   primary_roles: Optional[Dict[str, str]] = None,
                   n_bans: int = 5,
                   scout_champs: Optional[Dict[str, List[Dict[str, Any]]]] = None,
                   ) -> Optional[Dict[str, Any]]:
    """Returns {names:[...], info:[...]} or None."""
    return _post("/api/engine/recommend_bans", {
        "opposing_players": opposing_players,
        "inhouse_champs": inhouse_champs,
        "own_picks": own_picks or [],
        "primary_roles": primary_roles,
        "n_bans": n_bans,
        "scout_champs": scout_champs,
    })


def _rehydrate_action(raw: Any) -> Any:
    """Server-side DraftAction is a NamedTuple, which JSON-serializes to a
    bare list `[idx, side, kind, phase, label]`. The UI expects an object with
    attribute access (`act.side`, `act.kind`, …). Rebuild the client-side
    NamedTuple so every call-site keeps working unchanged."""
    if raw is None:
        return None
    if isinstance(raw, dict):
        try:
            from data.draft_board import DraftAction
            return DraftAction(
                idx=int(raw.get("idx", 0)),
                side=str(raw.get("side") or ""),
                kind=str(raw.get("kind") or ""),
                phase=int(raw.get("phase", 1)),
                label=str(raw.get("label") or ""),
            )
        except Exception:
            return raw
    if isinstance(raw, (list, tuple)) and len(raw) >= 5:
        try:
            from data.draft_board import DraftAction
            return DraftAction(int(raw[0]), str(raw[1]), str(raw[2]),
                               int(raw[3]), str(raw[4]))
        except Exception:
            return raw
    return raw


def recommend_action(state: Dict[str, Any],
                     inhouse_champs: Optional[Dict[str, Any]] = None,
                     primary_roles: Optional[Dict[str, str]] = None,
                     n: int = 5,
                     forced_arch: Optional[str] = None,
                     scout_champs: Optional[Dict[str, Any]] = None,
                     ) -> Optional[Dict[str, Any]]:
    out = _post("/api/engine/recommend_action", {
        "state": state, "inhouse_champs": inhouse_champs,
        "primary_roles": primary_roles, "n": n,
        "forced_arch": forced_arch, "scout_champs": scout_champs,
    })
    if isinstance(out, dict) and "action" in out:
        out["action"] = _rehydrate_action(out["action"])
    return out


def target_archetype(state: Dict[str, Any], side: str,
                     inhouse_champs: Optional[Dict[str, Any]] = None,
                     primary_roles: Optional[Dict[str, str]] = None,
                     forced_arch: Optional[str] = None,
                     scout_champs: Optional[Dict[str, Any]] = None,
                     ) -> Optional[Dict[str, Any]]:
    return _post("/api/engine/target_archetype", {
        "state": state, "side": side,
        "inhouse_champs": inhouse_champs or {},
        "primary_roles": primary_roles or {},
        "forced_arch": forced_arch, "scout_champs": scout_champs,
    })


def pick_impact_delta(state_before: Dict[str, Any],
                      state_after: Dict[str, Any],
                      side: str,
                      inhouse_champs: Optional[Dict[str, Any]] = None,
                      primary_roles: Optional[Dict[str, str]] = None,
                      scout_champs: Optional[Dict[str, Any]] = None,
                      ) -> Optional[Dict[str, Any]]:
    return _post("/api/engine/pick_impact_delta", {
        "state_before": state_before, "state_after": state_after,
        "side": side,
        "inhouse_champs": inhouse_champs or {},
        "primary_roles": primary_roles or {},
        "scout_champs": scout_champs,
    })


def archetype_pivot_check(state: Dict[str, Any], side: str,
                          current_arch: str,
                          inhouse_champs: Optional[Dict[str, Any]] = None,
                          primary_roles: Optional[Dict[str, str]] = None,
                          scout_champs: Optional[Dict[str, Any]] = None,
                          ) -> Optional[Dict[str, Any]]:
    return _post("/api/engine/archetype_pivot_check", {
        "state": state, "side": side, "current_arch": current_arch,
        "inhouse_champs": inhouse_champs or {},
        "primary_roles": primary_roles or {},
        "scout_champs": scout_champs,
    })


def predict_enemy_next(state: Dict[str, Any], our_side: str,
                       inhouse_champs: Optional[Dict[str, Any]] = None,
                       primary_roles: Optional[Dict[str, str]] = None,
                       scout_champs: Optional[Dict[str, Any]] = None,
                       ) -> Optional[Dict[str, Any]]:
    return _post("/api/engine/predict_enemy_next", {
        "state": state, "our_side": our_side,
        "inhouse_champs": inhouse_champs or {},
        "primary_roles": primary_roles or {},
        "scout_champs": scout_champs,
    })


def recommend_bans_split(state: Dict[str, Any],
                         inhouse_champs: Optional[Dict[str, Any]] = None,
                         primary_roles: Optional[Dict[str, str]] = None,
                         n: int = 5,
                         scout_champs: Optional[Dict[str, Any]] = None,
                         ) -> Optional[Dict[str, Any]]:
    return _post("/api/engine/recommend_bans_split", {
        "state": state,
        "inhouse_champs": inhouse_champs or {},
        "primary_roles": primary_roles or {},
        "n": n, "scout_champs": scout_champs,
    })


def matchups(blue: List[Dict[str, Any]], red: List[Dict[str, Any]],
             primary_roles: Optional[Dict[str, str]] = None,
             blue_picks: Optional[Dict[str, str]] = None,
             red_picks: Optional[Dict[str, str]] = None,
             ) -> Optional[Dict[str, Any]]:
    return _post("/api/engine/matchups", {
        "blue": blue, "red": red,
        "primary_roles": primary_roles,
        "blue_picks": blue_picks, "red_picks": red_picks,
    })


# ---------------------------------------------------------------------------
# Calibration / backtest / tuning / player models
# ---------------------------------------------------------------------------

def calibrate(wins: int, games: int,
              prior_rate: float = 0.50) -> Optional[Dict[str, Any]]:
    return _post("/api/engine/calibrate",
                 {"wins": wins, "games": games, "prior_rate": prior_rate})


def player_model(name: str) -> Optional[Dict[str, Any]]:
    return _get(f"/api/engine/players/{name}")


def backtest_run(limit: Optional[int] = None) -> Optional[Dict[str, Any]]:
    return _post("/api/engine/backtest",
                 {"limit": limit} if limit else {})


def backtest_history() -> Optional[List[Dict[str, Any]]]:
    r = _get("/api/engine/backtest/history")
    return None if r is None else r.get("runs", [])


def tuning_get() -> Optional[Dict[str, Any]]:
    return _get("/api/engine/tuning")


def tuning_set(name: str, value: float) -> Optional[Dict[str, Any]]:
    return _post("/api/engine/tuning", {"name": name, "value": value})


def tuning_reset(name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    return _post("/api/engine/tuning", {"reset": name if name else True})
