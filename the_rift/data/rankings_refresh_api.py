"""rankings_refresh_api.py — API-only Riot rank refresh.

Phase E (sheet decommission) replacement for the gspread-based
`data/fetch_ranks/cli.py`. Reads the roster from `/api/players`, pulls
each player's rank info from the Riot API, computes scores, and pushes
the result through `api_writer` to the Fly REST endpoints. No Google
Sheets writes; no credentials.json; no gspread import path.

Entry points:

    refresh_rankings(api_key, region='na1', routing='americas',
                     do_scout=False, on_progress=None, on_done=None,
                     on_error=None)

Run from a background thread — the Riot API calls add up to ~30s per
player when --scout is enabled. `on_progress(msg, pct)` is called with
status updates suitable for the Commands tab log. `on_done(summary)`
fires when everything is pushed; `on_error(msg)` on any fatal failure.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, List, Optional, Sequence

from data import rift_api
from data.fetch_ranks.riot import (fetch_account, fetch_ranked,
                                   fetch_top_champions, fetch_recent_matches,
                                   fetch_scouting_matches, load_champion_map)
from data.fetch_ranks.scoring import compute_score
from data.fetch_ranks.scouting import analyze_player
from data.fetch_ranks import api_writer


_ProgressFn = Optional[Callable[[str, float], None]]


def _roster_from_api() -> List[Dict[str, Any]]:
    """Roster shape the fetcher's `results` builder expects:
    [{"name": display, "riot_id": "Game#NA1"}, ...]"""
    out: List[Dict[str, Any]] = []
    data = rift_api.get_players_roster() or {}
    players = data.get("players") or []
    # `get_players` doesn't return riot_id today; rebuild from the
    # summoner_map. The summoner_map's KEY is the riot game_name, the
    # value is the display name. We need the inverse + the tagline,
    # which the roster doesn't expose. Fall back: ask Riot to look up
    # by display_name lookup elsewhere. For now, accept that riot_id
    # may be empty — fetch_account fails fast with a clear message.
    summoner_map = data.get("summoner_map") or {}
    display_to_game = {v: k for k, v in summoner_map.items()}
    for name in players:
        game = display_to_game.get(name, "")
        # Tagline unknown via the current /api/players endpoint — the
        # client will eventually surface it; for now we accept that
        # the roster needs to be re-bootstrapped with full riot_ids.
        out.append({"name": name, "riot_id": game})
    return out


def refresh_rankings(api_key: str,
                     region: str = "na1",
                     routing: str = "americas",
                     do_scout: bool = False,
                     on_progress: _ProgressFn = None,
                     on_done: Optional[Callable[[Dict[str, Any]], None]] = None,
                     on_error: Optional[Callable[[str], None]] = None) -> None:
    """Kick off the API-only rank refresh in a background thread."""
    def _bg():
        try:
            _run(api_key, region, routing, do_scout, on_progress, on_done)
        except Exception as e:                                 # pragma: no cover
            print(f"[refresh] error: {e}")
            if on_error:
                on_error(str(e))

    threading.Thread(target=_bg, daemon=True,
                     name="rankings_refresh_api").start()


def _emit(progress: _ProgressFn, msg: str, pct: float) -> None:
    if progress:
        try:
            progress(msg, pct)
        except Exception:
            pass
    print(f"  {msg}")


def _run(api_key: str, region: str, routing: str, do_scout: bool,
         on_progress: _ProgressFn,
         on_done: Optional[Callable[[Dict[str, Any]], None]]) -> None:
    _emit(on_progress, "Loading roster from server…", 0.02)
    roster_api = _roster_from_api()
    # The /api/players endpoint loses the tagline today, so the fetcher
    # uses the local config's full Riot IDs when available. Sources:
    #   1. live.scout (loaded earlier) — name + tier + final_score, no riot_id
    #   2. config['players'] — display names only, no riot_id
    #   3. config['roster_riot_ids'] (new optional field) — {display: full_riot_id}
    # For now we rely on the riot game name from summoner_map + a tagline
    # default of 'NA1'. A future API change exposes the tagline alongside.
    from data.config import load_config
    cfg = load_config()
    overrides = cfg.get("roster_riot_ids") or {}
    roster: List[Dict[str, Any]] = []
    for p in roster_api:
        name = p["name"]
        if name in overrides:
            riot_id = overrides[name]
        elif p["riot_id"]:
            riot_id = f"{p['riot_id']}#NA1"
        else:
            continue
        roster.append({"name": name, "riot_id": riot_id})
    if not roster:
        _emit(on_progress, "No roster on server — push roster first.", 1.0)
        if on_done:
            on_done({"ok": False, "reason": "empty_roster"})
        return

    _emit(on_progress, f"Roster: {len(roster)} players", 0.05)

    _emit(on_progress, "Loading champion map (Data Dragon)…", 0.08)
    try:
        champ_map = load_champion_map()
        # load_champion_map returns either dict or tuple — normalize to dict
        if isinstance(champ_map, tuple):
            champ_map = champ_map[0]
    except Exception as e:
        _emit(on_progress, f"Champion map load failed: {e}", 0.10)
        champ_map = {}

    # ── Per-player Riot fetch ──────────────────────────────────────────
    results: List[Dict[str, Any]] = []
    n = len(roster)
    for idx, player in enumerate(roster, 1):
        pct = 0.10 + (idx / max(n, 1)) * (0.60 if do_scout else 0.85)
        name = player["name"]
        try:
            game_name, tag_line = player["riot_id"].rsplit("#", 1)
        except ValueError:
            _emit(on_progress, f"[{idx}/{n}] {name}: bad riot_id", pct)
            continue
        _emit(on_progress, f"[{idx}/{n}] {name} ({player['riot_id']})", pct)

        try:
            puuid = fetch_account(game_name.strip(), tag_line.strip(),
                                  routing, api_key)
        except Exception as e:
            puuid = None
            _emit(on_progress, f"  account lookup failed: {e}", pct)
        if not puuid:
            results.append({
                "row": idx, "name": name,
                "tier": "Unranked", "division": "N/A",
                "lp": 0, "wins": 0, "losses": 0,
                "score": 0, "normalized": 0,
                "top_champs": [], "recent_matches": [],
            })
            continue
        time.sleep(0.6)

        tier, division, lp, wins, losses = fetch_ranked(puuid, region, api_key)
        score_v = compute_score(tier, division)
        normalized = round(score_v / 10 * 100, 1)
        time.sleep(0.6)

        try:
            top_champs = fetch_top_champions(puuid, region, api_key, champ_map)
        except Exception:
            top_champs = []
        time.sleep(0.4)

        try:
            recent_matches = fetch_recent_matches(puuid, routing, region, api_key)
        except Exception:
            recent_matches = []

        results.append({
            "row": idx, "name": name,
            "tier": tier, "division": division,
            "lp": lp, "wins": wins, "losses": losses,
            "score": score_v, "normalized": normalized,
            "top_champs": top_champs,
            "recent_matches": recent_matches,
            "puuid": puuid,
        })

    # ── Push to REST API  ──────────────────────────────────────────────
    _emit(on_progress, "Pushing rankings / scout / rank-history…", 0.85)
    api_writer.push_rankings(results)
    api_writer.push_scout(results)
    api_writer.push_rank_history(results)
    # Server-side recompute applies the tier_score + rank_score blend.
    try:
        import requests as _r
        base = rift_api._base_url()
        if base:
            _r.post(f"{base}/api/rankings/recompute", timeout=30)
    except Exception as e:
        print(f"[refresh] recompute call failed: {e}")

    # Optional per-player scout-sheet push
    if do_scout:
        _emit(on_progress, "Scouting each player (100 games)…", 0.90)
        for idx, r in enumerate(results, 1):
            if not r.get("puuid"):
                continue
            pct = 0.90 + (idx / max(len(results), 1)) * 0.08
            _emit(on_progress,
                  f"  scout [{idx}/{len(results)}] {r['name']}", pct)
            try:
                matches = fetch_scouting_matches(
                    r["puuid"], routing, region, api_key, count=100)
                if not matches:
                    continue
                analysis = analyze_player(matches)
                if not analysis:
                    continue
                rs = f"{r['tier']} {r['division']}" if r['division'] != "N/A" else r['tier']
                api_writer.push_scout_sheet(
                    r["name"], rs, r["lp"], analysis,
                    ranking_info={"position": idx,
                                  "score": r.get("normalized"),
                                  "rating": "",
                                  "tier_component": "",
                                  "rank_component": str(r.get("normalized"))})
            except Exception as e:                             # pragma: no cover
                _emit(on_progress, f"  {r['name']}: scout failed - {e}", pct)
                continue

    # Activity event
    try:
        rift_api.post_activity_event(
            event_type=("SCOUT" if do_scout else "UPDATE"),
            actor=(cfg.get("display_name") or "system"),
            details=f"{len(results)} players refreshed")
    except Exception:
        pass

    _emit(on_progress, "Done.", 1.0)
    if on_done:
        on_done({"ok": True, "refreshed": len(results)})
