"""
api.py — The Rift REST data API (Phase 0d).

A FastAPI router mounted onto the existing draft-sync server. Endpoints for
ingesting and reading match-granular data from the SQLite store (db.py).

Purely additive — the WebSocket draft path in main.py is untouched, and
main.py loads this router inside a try/except so a fault here can never take
down draft multiplayer.

Auth: write endpoints accept an optional bearer token. If the RIFT_API_TOKEN
env var is set on the server, writes require `Authorization: Bearer <token>`;
if it is unset, writes are open (fine for a private deployment).
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse


def _split_players(players: Optional[str]) -> Optional[list]:
    """Parse a ?players=a,b,c query string into a de-duplicated list. Returns
    None when the caller didn't provide one (preserves the unfiltered
    behavior of the records / standings / rivalries / pred LB endpoints)."""
    if not players:
        return None
    out, seen = [], set()
    for part in players.split(","):
        s = part.strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out or None

from db import (init as db_init, upsert_match, list_matches, get_match,
                player_matches, rivalries, h2h_matrix,
                records, stats as db_stats,
                export_all,
                # Phase 4c — Seasons
                list_seasons, create_season, season_standings, auto_seed_season,
                # Phase 5a — Achievements
                list_achievements, player_achievements,
                # Phase 5b — Predictions
                add_prediction, match_predictions, prediction_leaderboard)

# Phase 2 — server-side draft engine. Imports are wrapped in a try/except so a
# bug in the engine package can never break the existing data API or the
# WebSocket draft path mounted in main.py.
try:
    import engine_core as _eng
    import engine_board as _board
    import engine_signals
    import engine_players
    import engine_calibration
    import engine_backtest
    import engine_tuning
    _ENGINE_OK = True
except Exception as _e:                                    # pragma: no cover
    print(f"[rift-api] engine import deferred: {_e}")
    _ENGINE_OK = False

router = APIRouter(prefix="/api")

# Make sure the schema exists as soon as the router module loads.
try:
    db_init()
except Exception as _e:                                    # pragma: no cover
    print(f"[rift-api] db init deferred: {_e}")

# Phase 2 — eagerly blend the data-grounded signals at startup. Idempotent;
# safe to call when the DB is empty (the priors come through unchanged).
if _ENGINE_OK:
    try:
        engine_signals.refresh()
    except Exception as _e:                                # pragma: no cover
        print(f"[rift-api] signals refresh deferred: {_e}")


def _check_token(authorization: Optional[str]) -> None:
    """Enforce the bearer token on writes when RIFT_API_TOKEN is configured."""
    want = os.environ.get("RIFT_API_TOKEN", "").strip()
    if not want:
        return  # open mode
    got = (authorization or "").strip()
    if got.lower().startswith("bearer "):
        got = got[7:].strip()
    if got != want:
        raise HTTPException(status_code=401, detail="bad or missing API token")


@router.get("/stats")
async def api_stats() -> JSONResponse:
    return JSONResponse(db_stats())


@router.get("/matches")
async def api_matches(source: Optional[str] = None,
                      limit: int = 200) -> JSONResponse:
    return JSONResponse({"matches": list_matches(source=source, limit=limit)})


@router.get("/matches/{match_id}")
async def api_match(match_id: str) -> JSONResponse:
    m = get_match(match_id)
    if m is None:
        raise HTTPException(status_code=404, detail="match not found")
    return JSONResponse(m)


@router.get("/players/{name}/matches")
async def api_player_matches(name: str, limit: int = 200) -> JSONResponse:
    return JSONResponse({"player": name,
                         "matches": player_matches(name, limit=limit)})


@router.get("/players/{name}/rivalries")
async def api_player_rivalries(name: str, limit: int = 50,
                               players: Optional[str] = None) -> JSONResponse:
    return JSONResponse({"player": name,
                         "rivalries": rivalries(name, limit=limit,
                                                eligible=_split_players(players))})


@router.get("/h2h-matrix")
async def api_h2h_matrix(players: Optional[str] = None) -> JSONResponse:
    """Full head-to-head matrix for a roster, in one trip. `players` is a
    comma-separated list of riot summoner names (the value participants.player
    holds). Returns {matrix: {A: {B: {games_vs, wins_vs, ...}, ...}, ...}}.

    Omitting `players` returns an empty matrix — the client always knows its
    roster and we want to avoid accidentally fanning out across every player
    in the DB."""
    return JSONResponse({"matrix": h2h_matrix(_split_players(players) or [])})


@router.get("/records")
async def api_records(players: Optional[str] = None) -> JSONResponse:
    """League records / superlatives — single-game maxes, match-level records,
    per-player streaks. Each value is None when the DB is empty.

    Pass `?players=a,b,c` (the roster) to restrict player-keyed records to
    that whitelist and match-keyed records to matches containing at least one
    eligible player. Omitting the param keeps the legacy global behavior."""
    return JSONResponse({"records": records(eligible=_split_players(players))})


@router.get("/export")
async def api_export() -> JSONResponse:
    """Full DB dump — feeds the Sheet-mirror backup job."""
    return JSONResponse(export_all())


@router.post("/matches")
async def api_ingest(payload: Dict[str, Any],
                     authorization: Optional[str] = Header(default=None)
                     ) -> JSONResponse:
    """Ingest one match (`{...}` with an `id`) or many (`{"matches": [...]}`)."""
    _check_token(authorization)
    body = payload or {}
    matches = body.get("matches")
    if matches is None and body.get("id"):
        matches = [body]                       # single-match convenience form
    if not matches:
        raise HTTPException(status_code=400, detail="no matches in payload")
    ids = []
    for m in matches:
        try:
            ids.append(upsert_match(m))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    # Phase 2 — invalidate the signal cache so the next engine call sees the
    # fresh data. Best-effort; never blocks the ingest response.
    if _ENGINE_OK:
        try:
            engine_signals.refresh()
        except Exception as _e:                            # pragma: no cover
            print(f"[rift-api] post-ingest signals refresh failed: {_e}")
    return JSONResponse({"ok": True, "ingested": len(ids), "ids": ids})


# ===========================================================================
# Phase 2 — Engine endpoints
# ===========================================================================
# All endpoints below are stateless: clients pass the current draft state
# (champions / players / etc.) on every call. The server reads its DB for
# DB-derived signals (counters, synergies, player models) and falls back to
# engine_core's hand priors when sample is too small. See engine_signals.py.

def _require_engine() -> None:
    if not _ENGINE_OK:
        raise HTTPException(status_code=503, detail="engine not loaded")


@router.get("/engine/info")
async def api_engine_info() -> JSONResponse:
    """Engine + signal-table + tuning status (no compute)."""
    _require_engine()
    return JSONResponse({
        "engine":  "phase2-foundation",
        "signals": engine_signals.status(),
        "tuning":  engine_tuning.describe(),
    })


@router.post("/engine/refresh_signals")
async def api_engine_refresh_signals(
        authorization: Optional[str] = Header(default=None)) -> JSONResponse:
    """Force a rebuild of the blended counter/synergy/strength tables."""
    _require_engine()
    _check_token(authorization)
    return JSONResponse(engine_signals.refresh())


@router.post("/engine/score_team")
async def api_engine_score_team(payload: Dict[str, Any]) -> JSONResponse:
    """Body: { champs:[...], comforts:[...], arch_name, enemy_picks:[...] }"""
    _require_engine()
    p = payload or {}
    champs   = list(p.get("champs") or [])
    comforts = list(p.get("comforts") or [1.0] * len(champs))
    arch     = str(p.get("arch_name") or "")
    enemy    = list(p.get("enemy_picks") or ())
    return JSONResponse(_eng.score_team(champs, comforts, arch, enemy))


@router.post("/engine/synergy")
async def api_engine_synergy(payload: Dict[str, Any]) -> JSONResponse:
    _require_engine()
    return JSONResponse({"score": _eng.synergy_score(list((payload or {}).get("champs") or []))})


@router.post("/engine/counter")
async def api_engine_counter(payload: Dict[str, Any]) -> JSONResponse:
    _require_engine()
    p = payload or {}
    return JSONResponse({"score": _eng.counter_score(
        str(p.get("champ") or ""), list(p.get("enemies") or []))})


@router.post("/engine/weakness")
async def api_engine_weakness(payload: Dict[str, Any]) -> JSONResponse:
    _require_engine()
    return JSONResponse({"vector": _eng.enemy_weakness_vector(
        list((payload or {}).get("enemy_champs") or []))})


@router.post("/engine/recommend_comps")
async def api_engine_recommend_comps(payload: Dict[str, Any]) -> JSONResponse:
    """Thin wrapper around engine_core.recommend_comps. Body matches the
    function's kwargs, with player rows as dicts. Accepts both `n` (Phase 2
    API convention) and `n_results` (legacy engine_core signature)."""
    _require_engine()
    p = payload or {}
    n_results = int(p.get("n_results") or p.get("n") or 3)
    out = _eng.recommend_comps(
        players=list(p.get("players") or []),
        inhouse_champs=p.get("inhouse_champs"),
        primary_roles=p.get("primary_roles"),
        enemy_picks=list(p.get("enemy_picks") or ()),
        n_results=n_results,
        scout_champs=p.get("scout_champs"),
    )
    return JSONResponse({"comps": out})


@router.post("/engine/recommend_bans")
async def api_engine_recommend_bans(payload: Dict[str, Any]) -> JSONResponse:
    _require_engine()
    p = payload or {}
    n_bans = int(p.get("n_bans") or p.get("n") or 5)
    names, info = _eng.recommend_bans(
        opposing_players=list(p.get("opposing_players") or []),
        inhouse_champs=p.get("inhouse_champs"),
        own_picks=list(p.get("own_picks") or ()),
        primary_roles=p.get("primary_roles"),
        n_bans=n_bans,
        scout_champs=p.get("scout_champs"),
    )
    return JSONResponse({"names": names, "info": info})


@router.post("/engine/matchups")
async def api_engine_matchups(payload: Dict[str, Any]) -> JSONResponse:
    _require_engine()
    p = payload or {}
    out = _eng.compute_matchups(
        blue=list(p.get("blue") or []),
        red=list(p.get("red") or []),
        primary_roles=p.get("primary_roles"),
        blue_picks=p.get("blue_picks"),
        red_picks=p.get("red_picks"),
    )
    return JSONResponse(out)


# --- Stateful draft endpoints (need a serialized DraftBoardState) ----------

def _state_from(payload: Dict[str, Any]) -> Any:
    """Reconstruct a DraftBoardState from a JSON snapshot."""
    return _board.DraftBoardState.from_dict(payload.get("state") or {})


@router.post("/engine/recommend_action")
async def api_engine_recommend_action(payload: Dict[str, Any]) -> JSONResponse:
    _require_engine()
    p = payload or {}
    out = _board.recommend_action(
        _state_from(p),
        inhouse_champs=p.get("inhouse_champs"),
        primary_roles=p.get("primary_roles"),
        n=int(p.get("n") or 5),
        forced_arch=p.get("forced_arch"),
        scout_champs=p.get("scout_champs"),
    )
    return JSONResponse(out)


@router.post("/engine/target_archetype")
async def api_engine_target_archetype(payload: Dict[str, Any]) -> JSONResponse:
    _require_engine()
    p = payload or {}
    out = _board.target_archetype(
        _state_from(p),
        side=str(p.get("side") or "BLUE"),
        inhouse_champs=p.get("inhouse_champs") or {},
        primary_roles=p.get("primary_roles") or {},
        forced_arch=p.get("forced_arch"),
        scout_champs=p.get("scout_champs"),
    )
    return JSONResponse(out)


@router.post("/engine/pick_impact_delta")
async def api_engine_pick_impact_delta(payload: Dict[str, Any]) -> JSONResponse:
    _require_engine()
    p = payload or {}
    before = _board.DraftBoardState.from_dict(p.get("state_before") or {})
    after  = _board.DraftBoardState.from_dict(p.get("state_after")  or {})
    out = _board.pick_impact_delta(
        before, after,
        side=str(p.get("side") or "BLUE"),
        inhouse_champs=p.get("inhouse_champs") or {},
        primary_roles=p.get("primary_roles") or {},
        scout_champs=p.get("scout_champs"),
    )
    return JSONResponse(out)


@router.post("/engine/archetype_pivot_check")
async def api_engine_archetype_pivot_check(payload: Dict[str, Any]) -> JSONResponse:
    _require_engine()
    p = payload or {}
    out = _board.archetype_pivot_check(
        _state_from(p),
        side=str(p.get("side") or "BLUE"),
        current_arch=str(p.get("current_arch") or ""),
        inhouse_champs=p.get("inhouse_champs") or {},
        primary_roles=p.get("primary_roles") or {},
        scout_champs=p.get("scout_champs"),
    )
    return JSONResponse(out)


@router.post("/engine/predict_enemy_next")
async def api_engine_predict_enemy_next(payload: Dict[str, Any]) -> JSONResponse:
    _require_engine()
    p = payload or {}
    out = _board.predict_enemy_next_pick(
        _state_from(p),
        our_side=str(p.get("our_side") or "BLUE"),
        inhouse_champs=p.get("inhouse_champs") or {},
        primary_roles=p.get("primary_roles") or {},
        scout_champs=p.get("scout_champs"),
    )
    return JSONResponse(out)


@router.post("/engine/recommend_bans_split")
async def api_engine_recommend_bans_split(payload: Dict[str, Any]) -> JSONResponse:
    _require_engine()
    p = payload or {}
    state = _state_from(p)
    action = state.current_action()
    if not action:
        raise HTTPException(status_code=400, detail="no current action in state")
    out = _board.recommend_bans_split(
        state, action,
        inhouse_champs=p.get("inhouse_champs") or {},
        primary_roles=p.get("primary_roles") or {},
        n=int(p.get("n") or 5),
        scout_champs=p.get("scout_champs"),
    )
    return JSONResponse(out)


# --- Player models ---------------------------------------------------------

@router.get("/engine/players/{name}")
async def api_engine_player_model(name: str) -> JSONResponse:
    _require_engine()
    return JSONResponse(engine_players.model(name))


# --- Calibration helper ----------------------------------------------------

@router.post("/engine/calibrate")
async def api_engine_calibrate(payload: Dict[str, Any]) -> JSONResponse:
    """Body: { wins, games, prior_rate? } → Wilson CI + sample-size label."""
    _require_engine()
    p = payload or {}
    return JSONResponse(engine_calibration.calibrated_estimate(
        int(p.get("wins") or 0),
        int(p.get("games") or 0),
        float(p.get("prior_rate") or 0.50),
    ))


# --- Backtest --------------------------------------------------------------

@router.post("/engine/backtest")
async def api_engine_backtest(payload: Optional[Dict[str, Any]] = None,
                              authorization: Optional[str] = Header(default=None)
                              ) -> JSONResponse:
    _require_engine()
    _check_token(authorization)
    p = payload or {}
    return JSONResponse(engine_backtest.run(limit=p.get("limit")))


@router.get("/engine/backtest/history")
async def api_engine_backtest_history() -> JSONResponse:
    _require_engine()
    return JSONResponse({"runs": engine_backtest.history()})


# --- Tuning ----------------------------------------------------------------

@router.get("/engine/tuning")
async def api_engine_tuning_get() -> JSONResponse:
    _require_engine()
    return JSONResponse(engine_tuning.describe())


@router.post("/engine/tuning")
async def api_engine_tuning_set(payload: Dict[str, Any],
                                authorization: Optional[str] = Header(default=None)
                                ) -> JSONResponse:
    """Body: { name, value } or { reset: name|true }."""
    _require_engine()
    _check_token(authorization)
    p = payload or {}
    if "reset" in p:
        name = p["reset"] if isinstance(p["reset"], str) else None
        return JSONResponse(engine_tuning.reset(name))
    name = str(p.get("name") or "")
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    return JSONResponse(engine_tuning.set_value(name, float(p.get("value", 0.0))))


# ===========================================================================
# Phase 4c — Seasons & history
# ===========================================================================

@router.get("/seasons")
async def api_seasons() -> JSONResponse:
    """All seasons in chronological order (oldest first). Seeds a default
    Season 1 on first call when no seasons exist yet."""
    try:
        auto_seed_season()
    except Exception as _e:                                    # pragma: no cover
        print(f"[rift-api] season auto-seed deferred: {_e}")
    return JSONResponse({"seasons": list_seasons()})


@router.post("/seasons")
async def api_create_season(payload: Dict[str, Any],
                            authorization: Optional[str] = Header(default=None)
                            ) -> JSONResponse:
    """Body: { name, start_at, end_at? }"""
    _check_token(authorization)
    p = payload or {}
    try:
        season = create_season(
            name=str(p.get("name") or "").strip(),
            start_at=str(p.get("start_at") or "").strip(),
            end_at=(p.get("end_at") or None))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return JSONResponse({"season": season})


@router.get("/seasons/{season_id}/standings")
async def api_season_standings(season_id: int,
                               players: Optional[str] = None) -> JSONResponse:
    return JSONResponse(season_standings(
        int(season_id), eligible=_split_players(players)))


# ===========================================================================
# Phase 5a — Achievements
# ===========================================================================

@router.get("/achievements")
async def api_achievement_catalog() -> JSONResponse:
    """Full catalog of achievements (code + label + description)."""
    return JSONResponse({"achievements": list_achievements()})


@router.get("/players/{name}/achievements")
async def api_player_achievements(name: str) -> JSONResponse:
    return JSONResponse({"player": name,
                         "achievements": player_achievements(name)})


# ===========================================================================
# Phase 5b — Predictions
# ===========================================================================

@router.get("/predictions/leaderboard")
async def api_prediction_leaderboard(limit: int = 50,
                                     players: Optional[str] = None
                                     ) -> JSONResponse:
    return JSONResponse({"leaderboard": prediction_leaderboard(
        limit=limit, eligible=_split_players(players))})


@router.get("/matches/{match_id}/predictions")
async def api_match_predictions(match_id: str) -> JSONResponse:
    return JSONResponse({"match_id": match_id,
                         "predictions": match_predictions(match_id)})


@router.post("/matches/{match_id}/predictions")
async def api_add_prediction(match_id: str, payload: Dict[str, Any],
                             authorization: Optional[str] = Header(default=None)
                             ) -> JSONResponse:
    """Body: { voter, predicted (blue|red), confidence? }"""
    _check_token(authorization)
    p = payload or {}
    try:
        out = add_prediction(
            match_id=match_id,
            voter=str(p.get("voter") or "").strip(),
            predicted=str(p.get("predicted") or "").strip().lower(),
            confidence=(float(p["confidence"]) if "confidence" in p else None),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return JSONResponse(out)
