"""
engine_signals.py — Phase 2a · data-grounded signals.

Builds DB-derived counters / synergies / lane-matchups / champion-strength
tables that BLEND with the hand-authored priors in engine_core via Bayesian
shrinkage:

    blend = (n / (n + k)) * data_rate + (k / (n + k)) * prior_rate

Where `n` is the observed sample size for that pair/champ, `k` is the
shrinkage strength (default 8 — equivalent to "I won't trust the data until
I have at least that many games"), `data_rate` is the empirical winrate, and
`prior_rate` is the hand table's value (or a neutral 0.50 if the table has
no entry for that pair).

Until enough matches accumulate in the DB, every shrinkage call collapses to
the prior. That is the design — the new engine behaves identically to the
old one when data is sparse, and grows more confident in the data as the
sample grows. No surprise regressions.

Caches:
- The signal tables are rebuilt from the DB on `refresh()`, then cached at
  module level. `engine_core.COUNTERS` / `SYNERGIES` are reassigned to the
  blended tables when refresh succeeds.
- Refresh is idempotent and thread-safe. Call it at server startup and after
  each batch of new matches lands.
"""
from __future__ import annotations

import threading
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Tuple

import engine_core as _eng
import db as _db


_LOCK = threading.Lock()
_LAST_REFRESH: Optional[str] = None     # ISO timestamp of the last successful build

# Shrinkage strength. With k=8, a champion needs ~8 matches before the data
# starts outweighing the prior. Tunable via engine_tuning.
SHRINKAGE_K = 8.0


# ---------------------------------------------------------------------------
# Shrinkage math
# ---------------------------------------------------------------------------

def shrink(wins: float, games: float,
           prior_rate: float = 0.50,
           k: float = SHRINKAGE_K) -> float:
    """Bayesian-shrunken rate. Returns the prior when games==0."""
    if games <= 0:
        return prior_rate
    data_rate = wins / games
    weight    = games / (games + k)
    return weight * data_rate + (1.0 - weight) * prior_rate


def shrink_score(diff: float, n: float, k: float = SHRINKAGE_K) -> float:
    """Shrink a signed score (e.g. -1..+1 counter strength). Returns 0 at n=0,
    asymptotes to diff as n grows."""
    if n <= 0:
        return 0.0
    return (n / (n + k)) * diff


# ---------------------------------------------------------------------------
# DB scans
# ---------------------------------------------------------------------------

def _scan_team_outcomes(conn) -> Tuple[
        Dict[Tuple[str, str], List[int]],            # (champ, enemy)   -> [wins, games]
        Dict[Tuple[str, str], List[int]],            # (champ, partner) -> [wins, games]
        Dict[str, List[int]],                        # champ            -> [wins, games]
]:
    """Single pass over participants joined to matches. Builds raw count
    tables — counters (one vs the other team) and synergies (with the same
    team). Returns dicts keyed by canonical-ordered champion pairs."""
    counters: Dict[Tuple[str, str], List[int]] = defaultdict(lambda: [0, 0])
    synergies: Dict[Tuple[str, str], List[int]] = defaultdict(lambda: [0, 0])
    strength: Dict[str, List[int]] = defaultdict(lambda: [0, 0])

    by_match: Dict[str, Dict[str, List[Tuple[str, int]]]] = defaultdict(
        lambda: {"blue": [], "red": []})

    rows = conn.execute(
        "SELECT match_id, team, champion, win FROM participants"
    ).fetchall()
    for r in rows:
        mid   = r["match_id"]
        team  = (r["team"] or "").lower()
        champ = r["champion"] or ""
        win   = int(r["win"] or 0)
        if not champ or team not in ("blue", "red"):
            continue
        by_match[mid][team].append((champ, win))
        s = strength[champ]
        s[0] += win
        s[1] += 1

    for mid, sides in by_match.items():
        blue = sides["blue"]
        red  = sides["red"]
        # Counters: every blue champ paired with every red champ.
        for bc, bw in blue:
            for rc, _rw in red:
                k = _eng._pair(bc, rc)
                counters[k][0] += bw          # win-count for the blue side of the pair
                counters[k][1] += 1
        # Synergies: every same-side pair.
        for side in (blue, red):
            for i in range(len(side)):
                for j in range(i + 1, len(side)):
                    a, aw = side[i]
                    b, _bw = side[j]
                    k = _eng._pair(a, b)
                    synergies[k][0] += aw     # both share the same win value (same team)
                    synergies[k][1] += 1

    return counters, synergies, strength


# ---------------------------------------------------------------------------
# Public: blended tables
# ---------------------------------------------------------------------------

def build_blended_counters(conn) -> Dict[Tuple[str, str], float]:
    """Return shrinkage-blended COUNTERS table. Keys are `_pair(a,b)` ordered.
    Value is the engine's "advantage score" for the canonical first champ
    over the second (positive = first wins more)."""
    raw_counters, _, _ = _scan_team_outcomes(conn)
    blended = dict(_eng.COUNTERS)             # start from hand table
    for key, (wins, n) in raw_counters.items():
        if n <= 0:
            continue
        # The hand table's value range is roughly -1..+2. We treat 0 as neutral
        # and shrink the data delta toward that neutral when n is small.
        # Data signal: a "lift" of wr - 0.5, clamped/scaled to similar range.
        wr = wins / n
        data_lift = (wr - 0.5) * 2.0          # -1..+1 nominally
        prior     = blended.get(key, 0.0)
        # Shrink the delta from prior toward zero based on n.
        delta = data_lift - prior
        blended[key] = prior + shrink_score(delta, n)
    return blended


def build_blended_synergies(conn) -> Dict[Tuple[str, str], float]:
    _, raw_synergies, _ = _scan_team_outcomes(conn)
    blended = dict(_eng.SYNERGIES)
    for key, (wins, n) in raw_synergies.items():
        if n <= 0:
            continue
        wr = wins / n
        data_lift = (wr - 0.5) * 2.0
        prior     = blended.get(key, 0.0)
        delta = data_lift - prior
        blended[key] = prior + shrink_score(delta, n)
    return blended


def build_champion_strength(conn) -> Dict[str, float]:
    """Shrunken champ-level WR delta vs neutral 0.5. Positive = above-average
    performer in our inhouse corpus; negative = below. Defaults to 0.0 when no
    sample."""
    _, _, raw = _scan_team_outcomes(conn)
    out: Dict[str, float] = {}
    for champ, (wins, n) in raw.items():
        out[champ] = shrink(wins, n, prior_rate=0.50) - 0.50
    return out


# ---------------------------------------------------------------------------
# Refresh — recompute, then publish to engine_core
# ---------------------------------------------------------------------------

def refresh() -> Dict[str, Any]:
    """Rebuild the blended signal tables from the DB and reassign them onto
    engine_core. Safe to call repeatedly. Returns a small status dict."""
    global _LAST_REFRESH
    with _LOCK:
        try:
            conn = _db._conn()
            counters  = build_blended_counters(conn)
            synergies = build_blended_synergies(conn)
            strength  = build_champion_strength(conn)
            # Publish.
            _eng.COUNTERS  = counters
            _eng.SYNERGIES = synergies
            # Champion strength is a new attribute the engine reads when present.
            setattr(_eng, "CHAMP_STRENGTH", strength)
            import time
            _LAST_REFRESH = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            return {
                "ok": True,
                "counter_keys":  len(counters),
                "synergy_keys":  len(synergies),
                "strength_keys": len(strength),
                "at": _LAST_REFRESH,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}


def status() -> Dict[str, Any]:
    """Inspection helper for /api/engine/info."""
    return {
        "shrinkage_k": SHRINKAGE_K,
        "last_refresh": _LAST_REFRESH,
        "counter_keys":  len(getattr(_eng, "COUNTERS", {}) or {}),
        "synergy_keys":  len(getattr(_eng, "SYNERGIES", {}) or {}),
        "strength_keys": len(getattr(_eng, "CHAMP_STRENGTH", {}) or {}),
    }
