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
    [{"name": display, "riot_id": "Game#Tagline", "game_name": "Game"}, ...]

    Prefers the server-supplied `riot_ids` map (full GameName#Tagline). Falls
    back to the legacy `summoner_map` (game_name only, no tagline) so older
    servers still function — the caller will then look for a local override
    or warn and skip the player rather than forge a wrong tagline."""
    out: List[Dict[str, Any]] = []
    data = rift_api.get_players_roster() or {}
    players = data.get("players") or []
    summoner_map = data.get("summoner_map") or {}
    riot_ids = data.get("riot_ids") or {}
    display_to_game = {v: k for k, v in summoner_map.items()}
    for name in players:
        game = display_to_game.get(name, "")
        out.append({
            "name": name,
            "riot_id": riot_ids.get(name, ""),
            "game_name": game,
        })
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
    # Riot-ID resolution order, most authoritative first:
    #   1. server `/api/players` → riot_ids[name]  (full GameName#Tagline)
    #   2. local config['roster_riot_ids']         (manual override)
    #   3. legacy fallback: game_name + '#NA1'     (only if user opts in)
    # The legacy fallback used to run unconditionally and silently mis-tagged
    # everyone whose real tag wasn't NA1 — that's the unranked-everyone bug.
    from data.config import load_config
    cfg = load_config()
    overrides = cfg.get("roster_riot_ids") or {}
    allow_na1_fallback = bool(cfg.get("allow_na1_tag_fallback"))
    roster: List[Dict[str, Any]] = []
    missing: List[str] = []
    for p in roster_api:
        name = p["name"]
        if name in overrides and "#" in overrides[name]:
            riot_id = overrides[name]
        elif p.get("riot_id") and "#" in p["riot_id"]:
            riot_id = p["riot_id"]
        elif allow_na1_fallback and p.get("game_name"):
            riot_id = f"{p['game_name']}#NA1"
        else:
            missing.append(name)
            continue
        roster.append({"name": name, "riot_id": riot_id})
    if missing:
        _emit(on_progress,
              f"Skipping {len(missing)} player(s) with no tagline on server: "
              f"{', '.join(missing)}", 0.04)
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
        # Batch-fetch inhouse champion comfort for every player up-front so the
        # scout payload's `inhouse_champs` array carries the customs signal the
        # draft engine reads. One API call instead of N.
        try:
            from urllib.parse import quote
            names = [r["name"] for r in results if r.get("name")]
            qs = quote(",".join(names), safe=",")
            ih_resp = rift_api._get(f"/api/inhouse-champs?players={qs}") or {}
            inhouse_by_name = ih_resp.get("inhouse_champs") or {}
        except Exception as e:                                 # pragma: no cover
            _emit(on_progress, f"  inhouse-champs fetch failed: {e}", 0.89)
            inhouse_by_name = {}

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
                player_inhouse = inhouse_by_name.get(r["name"]) or []
                api_writer.push_scout_sheet(
                    r["name"], rs, r["lp"], analysis,
                    ranking_info={"position": idx,
                                  "score": r.get("normalized"),
                                  "rating": "",
                                  "tier_component": "",
                                  "rank_component": str(r.get("normalized"))},
                    inhouse_data=({"champs": player_inhouse}
                                  if player_inhouse else None))
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
