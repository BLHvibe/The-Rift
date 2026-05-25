"""api_writer.py — push the Riot-fetcher output to the Fly REST API.

Replacement for the Google Sheets writer path (`sheets.py`,
`rankings.py::write_rank_data`, `rankings.py::write_player_stats`,
`rankings.py::write_rank_history`). When this module is wired up, the
fetcher no longer needs gspread / credentials.json / a service-account
key — the server's SQLite store becomes the single source of truth.

Public entry points (call from `cli.py` after the fetch completes):

    push_roster(players, base_url=None, token=None)
        Bulk-upsert the player roster (display_name + riot_id).

    push_rankings(results, consensus=None, base_url=None, token=None)
        Combine the Riot-API results + optional community-vote consensus
        into the rankings table.

    push_scout(results, base_url=None, token=None)
        Push Player Stats rows (top champs, recent KDA, hot/cold) to
        scout_stats.

    push_rank_history(results, sampled_at=None, base_url=None, token=None)
        Snapshot one rank-value-per-player into the time-series table.

Each function is best-effort: on any failure (server down, network blip,
schema mismatch) it prints a warning and returns False so the caller can
fall back to the sheet path during the migration window.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence

try:
    import requests
except Exception:                                              # pragma: no cover
    requests = None  # type: ignore

from .constants import RANK_CHART_VALUES, TIER_TO_NUM, NUM_TO_TIER

# Default base URL: the Fly draft-sync server (same host serves the data API).
# Allow override via env / kwarg so dev can point at localhost.
_DEFAULT_BASE = "https://the-rift-draft-sync.fly.dev"
_TIMEOUT = 30


def _post(path: str, body: Dict[str, Any],
          base_url: Optional[str] = None,
          token: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if requests is None:
        print("  [api] requests not installed, skipping")
        return None
    url = (base_url or _DEFAULT_BASE).rstrip("/") + path
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        r = requests.post(url, json=body, headers=headers, timeout=_TIMEOUT)
        if r.status_code == 200:
            return r.json()
        print(f"  [api] {path} -> {r.status_code}: {r.text[:200]}")
        return None
    except Exception as e:                                     # pragma: no cover
        print(f"  [api] {path} failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Roster
# ---------------------------------------------------------------------------

def push_roster(players: Sequence[Dict[str, Any]],
                base_url: Optional[str] = None,
                token: Optional[str] = None) -> bool:
    """Bulk-upsert the roster (display_name + riot_id) to /api/players.
    `players` is the list cli.py builds from the Players sheet —
    each row needs at minimum `name` and `riot_id`."""
    rows: List[Dict[str, Any]] = []
    for p in (players or []):
        if not isinstance(p, dict):
            continue
        name = (p.get("name") or p.get("display_name") or "").strip()
        riot = (p.get("riot_id") or "").strip()
        if not name:
            continue
        rows.append({"display_name": name, "riot_id": riot})
    if not rows:
        return False
    out = _post("/api/players", {"players": rows},
                base_url=base_url, token=token)
    if out and out.get("ok"):
        print(f"  [api] /api/players -> wrote {out.get('written')} roster rows")
        return True
    return False


# ---------------------------------------------------------------------------
# Rankings  (Riot rank + optional community-vote blend)
# ---------------------------------------------------------------------------
#
# Scoring blend: rank_score (Riot rank, normalized 0..100) + tier_score
# (community vote, normalized 0..100), then final_score = (rank + tier) / 2
# so the value stays on a 0..100 scale and remains meaningful even when
# tier-list votes are missing. Rating is a letter grade from final_score.
#
# These formulas are intentionally simpler than the original sheet formulas
# (which used hand-tuned weights) — they're a clean starting point that's
# easy to tweak later. The Riot-only signal (`rank_score`) is exact; the
# community blend is best-effort and only kicks in when consensus data is
# provided.


def _rating_from(final_score: float) -> str:
    s = float(final_score or 0.0)
    if s >= 85: return "S"
    if s >= 70: return "A"
    if s >= 55: return "B"
    if s >= 40: return "C"
    if s >= 25: return "D"
    return "F"


def push_rankings(results: Sequence[Dict[str, Any]],
                  consensus: Optional[Sequence[Dict[str, Any]]] = None,
                  base_url: Optional[str] = None,
                  token: Optional[str] = None) -> bool:
    """Bulk-upsert per-player rankings to /api/rankings. `results` is the
    fetcher's Riot-API output (tier/division/lp/wins/losses/score). If
    `consensus` is provided (from compute_tier_analytics), the community-
    vote average is blended into final_score; otherwise final_score
    collapses to rank_score."""
    avg_by_name: Dict[str, float] = {}
    for c in (consensus or []):
        if isinstance(c, dict) and c.get("name"):
            avg_by_name[c["name"]] = float(c.get("avg") or 0.0)

    rows: List[Dict[str, Any]] = []
    # Sort results by Riot score desc so rank_position is meaningful
    ordered = sorted(results or [], key=lambda r: -float(r.get("score") or 0))
    for idx, r in enumerate(ordered):
        if not isinstance(r, dict):
            continue
        name = (r.get("name") or "").strip()
        if not name:
            continue
        # Riot side: normalized 0..100
        rank_score = round(float(r.get("normalized")
                                 or (float(r.get("score") or 0) * 10)), 2)
        # Community side: avg is on 1..6 (F..S). Scale to 0..100 (each tier
        # step = 20 pts, so S=100, A=80, B=60, C=40, D=20, F=0).
        avg_num = avg_by_name.get(name, 0.0)
        if avg_num > 0:
            tier_score = round((avg_num - 1.0) * 20.0, 2)
            final_score = round((rank_score + tier_score) / 2.0, 2)
            avg_tier_str = f"{avg_num:.2f}"
        else:
            tier_score = 0.0
            final_score = rank_score
            avg_tier_str = ""
        wins = int(r.get("wins") or 0)
        losses = int(r.get("losses") or 0)
        games = wins + losses
        wr = round(wins / games * 100, 1) if games > 0 else 0.0
        rows.append({
            "name":        name,
            "rank":        idx + 1,
            "tier":        r.get("tier") or "Unranked",
            "division":    r.get("division") or "",
            "avg_tier":    avg_tier_str,
            "tier_score":  f"{tier_score:.2f}" if tier_score else "",
            "rank_score":  f"{rank_score:.2f}",
            "final_score": f"{final_score:.2f}",
            "rating":      _rating_from(final_score),
            "lp":          int(r.get("lp") or 0),
            "wins":        wins, "losses": losses,
            "games":       games, "wr": wr,
        })
    if not rows:
        return False
    out = _post("/api/rankings", {"rankings": rows},
                base_url=base_url, token=token)
    if out and out.get("ok"):
        print(f"  [api] /api/rankings -> wrote {out.get('written')} rows")
        return True
    return False


# ---------------------------------------------------------------------------
# Scout stats  (Player Stats sheet — top champs, recent KDA, hot/cold)
# ---------------------------------------------------------------------------

def push_scout(results: Sequence[Dict[str, Any]],
               base_url: Optional[str] = None,
               token: Optional[str] = None) -> bool:
    """Bulk-upsert per-player scout stats to /api/scout."""
    rows: List[Dict[str, Any]] = []
    for r in (results or []):
        if not isinstance(r, dict):
            continue
        name = (r.get("name") or "").strip()
        if not name:
            continue
        matches = r.get("recent_matches") or []
        rw = sum(1 for m in matches if m.get("win"))
        rl = len(matches) - rw
        if matches:
            tk = sum(int(m.get("kills") or 0) for m in matches)
            td = sum(int(m.get("deaths") or 0) for m in matches)
            ta = sum(int(m.get("assists") or 0) for m in matches)
            avg_k = round(tk / len(matches), 1)
            avg_d = round(td / len(matches), 1)
            avg_a = round(ta / len(matches), 1)
            kda = round((tk + ta) / max(td, 1), 1)
        else:
            avg_k = avg_d = avg_a = kda = 0.0
        # Hot/Cold heuristic mirrors the sheet formula — 70%+ recent WR is HOT,
        # 30% or less is COLD, anything in between MIXED.
        if matches:
            recent_wr = rw / len(matches)
            form = "HOT" if recent_wr >= 0.70 else (
                   "COLD" if recent_wr <= 0.30 else "MIXED")
        else:
            form = "MIXED"
        top_champs_names = [c.get("name") for c in (r.get("top_champs") or [])
                            if isinstance(c, dict) and c.get("name")][:3]
        wr_from_stats = 0
        wins = int(r.get("wins") or 0)
        losses = int(r.get("losses") or 0)
        if (wins + losses) > 0:
            wr_from_stats = int(round(wins / (wins + losses) * 100))
        rows.append({
            "name":           name,
            "kda":            kda,
            "form":           form,
            "top_champs":     top_champs_names,
            "wr_from_stats":  wr_from_stats,
            "games_fallback": wins + losses,
            "wins_fallback":  wins,
            "avg_kills":      avg_k,
            "avg_deaths":     avg_d,
            "avg_assists":    avg_a,
        })
    if not rows:
        return False
    out = _post("/api/scout", {"scout": rows}, base_url=base_url, token=token)
    if out and out.get("ok"):
        print(f"  [api] /api/scout -> wrote {out.get('written')} rows")
        return True
    return False


# ---------------------------------------------------------------------------
# Rank history snapshot  (for the per-player sparkline)
# ---------------------------------------------------------------------------

def push_rank_history(results: Sequence[Dict[str, Any]],
                      sampled_at: Optional[str] = None,
                      base_url: Optional[str] = None,
                      token: Optional[str] = None) -> bool:
    """Snapshot the current rank values to /api/rank-history. One row per
    player; `value` is the chart-friendly int 0..31 (Unranked..Challenger I
    in `RANK_CHART_VALUES`)."""
    rows: List[Dict[str, Any]] = []
    for r in (results or []):
        if not isinstance(r, dict):
            continue
        name = (r.get("name") or "").strip()
        if not name:
            continue
        tier = r.get("tier") or "Unranked"
        division = r.get("division") or ""
        if tier in ("Master", "Grandmaster", "Challenger", "Unranked"):
            value = RANK_CHART_VALUES.get(tier, 0)
        else:
            key = f"{tier} {division}" if division and division != "N/A" else tier
            value = RANK_CHART_VALUES.get(key, 0)
        rows.append({"name": name, "value": value,
                     "tier": tier, "division": division})
    if not rows:
        return False
    ts = sampled_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = _post("/api/rank-history",
                {"sampled_at": ts, "rows": rows},
                base_url=base_url, token=token)
    if out and out.get("ok"):
        print(f"  [api] /api/rank-history -> wrote {out.get('written')} samples")
        return True
    return False


# ---------------------------------------------------------------------------
# Convenience: full push in one call
# ---------------------------------------------------------------------------

def push_all(players: Sequence[Dict[str, Any]],
             results: Sequence[Dict[str, Any]],
             consensus: Optional[Sequence[Dict[str, Any]]] = None,
             base_url: Optional[str] = None,
             token: Optional[str] = None) -> Dict[str, bool]:
    """Run every push step. Returns a dict of which sub-pushes succeeded so
    the caller can log a single-line summary."""
    return {
        "roster":       push_roster(players, base_url=base_url, token=token),
        "rankings":     push_rankings(results, consensus=consensus,
                                      base_url=base_url, token=token),
        "scout":        push_scout(results, base_url=base_url, token=token),
        "rank_history": push_rank_history(results,
                                          base_url=base_url, token=token),
    }


# ---------------------------------------------------------------------------
# Per-player scout sheet  (replaces write_scouting_sheet's gspread writes)
# ---------------------------------------------------------------------------

def _analysis_to_scout_payload(player_name: str,
                               rank_str: str,
                               lp: int,
                               analysis: Dict[str, Any],
                               ranking_info: Optional[Dict[str, Any]] = None,
                               inhouse_data: Optional[Dict[str, Any]] = None
                               ) -> Dict[str, Any]:
    """Convert the Riot fetcher's `analysis` dict (from
    scouting.analyze_player) into the parsed shape that
    `reader._parse_scouting_sheet` used to emit, so the client can consume
    the API-stored payload exactly like the sheet-parsed one."""
    a = analysis or {}
    rn = ranking_info or {}
    # Subtitle line — mirrors the sheet's "Rank | LP | W-L | WR | Total" header
    parts = [rank_str or "", f"{lp or 0} LP",
             f"{a.get('wins',0)}W-{a.get('losses',0)}L",
             f"{a.get('wr',0)}% WR",
             f"{a.get('total',0)} games analyzed"]
    subtitle = "  |  ".join(p for p in parts if p)

    # Power-rating block
    power = None
    if rn:
        power = {
            "position":     rn.get("position"),
            "score":        rn.get("score"),
            "rating":       rn.get("rating"),
            "tier_score":   rn.get("tier_component"),
            "rank_score":   rn.get("rank_component"),
        }

    # Overview header/value rows — same 12-column layout the sheet uses
    overview_headers = ["KDA","Avg Kills","Avg Deaths","Avg Assists",
                        "CS/min","Avg Damage","Avg Vision","Avg Gold",
                        "FB %","Form","Pool Depth","Unique Champs"]
    form_lbl = f"{a.get('form','MIXED')} ({a.get('recent_wins',0)}/{a.get('recent_total',0)})"
    overview_values = [
        str(a.get("overall_kda","")),
        str(a.get("avg_kills","")),
        str(a.get("avg_deaths","")),
        str(a.get("avg_assists","")),
        str(a.get("avg_cs_min","")),
        f"{a.get('avg_damage',0):,}",
        str(a.get("avg_vision","")),
        f"{a.get('avg_gold',0):,}",
        f"{a.get('fb_rate',0)}%",
        form_lbl,
        str(a.get("pool_depth","")),
        str(a.get("unique_champs","")),
    ]

    # Champ pool — engine's #2 comfort signal.
    champ_pool = []
    for c in (a.get("champ_pool") or []):
        if not isinstance(c, dict):
            continue
        results_list = c.get("results") or []
        if isinstance(results_list, str):
            # Comma-encoded form ("1,0,1,1,…") — split into ints
            results_list = [int(x) for x in results_list.split(",")
                            if x.strip() in ("0","1")]
        champ_pool.append({
            "name":    c.get("champion") or c.get("name"),
            "games":   c.get("games", 0),
            "wins":    c.get("wins",  0),
            "losses":  c.get("losses",0),
            "wr":      c.get("wr"),
            "kda":     c.get("kda"),
            "kills":   c.get("avg_kills", c.get("kills")),
            "deaths":  c.get("avg_deaths", c.get("deaths")),
            "assists": c.get("avg_assists", c.get("assists")),
            "cs_min":  c.get("avg_cs_min", c.get("cs_min")),
            "damage":  c.get("avg_damage", c.get("damage")),
            "results": results_list,
        })

    # Must-bans — same shape the sheet parser produced
    must_bans = []
    for b in (a.get("must_bans") or []):
        if not isinstance(b, dict):
            continue
        must_bans.append({
            "name":    b.get("name") or b.get("champion"),
            "games":   b.get("games", 0),
            "wins":    b.get("wins",  0),
            "losses":  b.get("losses",0),
            "wr":      b.get("wr"),
            "kda":     b.get("kda"),
            "kills":   b.get("avg_kills", b.get("kills")),
            "deaths":  b.get("avg_deaths", b.get("deaths")),
            "assists": b.get("avg_assists", b.get("assists")),
            "cs_min":  b.get("avg_cs_min", b.get("cs_min")),
            "damage":  b.get("avg_damage", b.get("damage")),
            "threat":  b.get("threat"),
        })

    payload = {
        "player":           player_name,
        "subtitle":         subtitle,
        "power_rating":     power,
        "overview_headers": overview_headers,
        "overview_values":  overview_values,
        "must_bans":        must_bans,
        "must_bans_msg":    a.get("must_bans_msg"),
        "ban_impact":       a.get("ban_impact"),
        "champ_pool":       champ_pool,
        "roles":            a.get("roles") or [],
        "form_state":       a.get("form", "MIXED"),
        "matches":          a.get("matches") or [],
        "inhouse_champs":   (inhouse_data or {}).get("champs") or [],
        "scouted_at":       datetime.now(timezone.utc)
                                    .strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    return payload


def push_scout_sheet(player_name: str, rank_str: str, lp: int,
                     analysis: Dict[str, Any],
                     ranking_info: Optional[Dict[str, Any]] = None,
                     inhouse_data: Optional[Dict[str, Any]] = None,
                     base_url: Optional[str] = None,
                     token: Optional[str] = None) -> bool:
    """Push one player's parsed scout-sheet payload to /api/scout-sheets.
    Called from the fetcher's `--scout` flow right after analyze_player()
    finishes, in parallel with the sheet write (during the transition)."""
    payload = _analysis_to_scout_payload(player_name, rank_str, lp,
                                         analysis, ranking_info, inhouse_data)
    out = _post("/api/scout-sheets",
                {"display_name": player_name, "payload": payload},
                base_url=base_url, token=token)
    if out and out.get("ok"):
        print(f"  [api] /api/scout-sheets[{player_name}] -> ok")
        return True
    return False
