"""
engine_players.py — Phase 2b · deep player models.

Per-player champion pools, per-champ performance, role comfort, off-role
penalty, and form — all computed from match-granular DB rows. This is what
makes the engine's recommendations *yours* instead of a generic LoL meta read.

When a player has no logged games yet, every helper returns sensible defaults
(neutral WR, empty champion pool) so the engine falls back to its hand priors.
That's the same shrinkage philosophy as engine_signals: behavior collapses to
the current engine when data is sparse, sharpens as the sample grows.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

import db as _db
import engine_signals as _sig


# ---------------------------------------------------------------------------
# Champion pool — per-player per-champ stats
# ---------------------------------------------------------------------------

def champion_pool(player: str, limit_recent: int = 0) -> List[Dict[str, Any]]:
    """Return the player's logged champion pool, newest first.

    Each entry: { champion, games, wins, wr, kills, deaths, assists, kda,
                  cs_avg, gold_avg, damage_avg, last_played }

    `limit_recent` > 0 caps to that many most-recent matches (useful for form).
    """
    conn = _db._conn()
    if limit_recent > 0:
        rows = conn.execute(
            "SELECT p.*, m.started_at FROM participants p "
            "JOIN matches m ON m.id = p.match_id "
            "WHERE p.player = ? "
            "ORDER BY m.started_at DESC LIMIT ?",
            (player, int(limit_recent))).fetchall()
    else:
        rows = conn.execute(
            "SELECT p.*, m.started_at FROM participants p "
            "JOIN matches m ON m.id = p.match_id "
            "WHERE p.player = ? "
            "ORDER BY m.started_at DESC",
            (player,)).fetchall()

    agg: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        c = r["champion"] or ""
        if not c:
            continue
        a = agg.setdefault(c, {
            "champion": c, "games": 0, "wins": 0,
            "kills": 0, "deaths": 0, "assists": 0,
            "cs": 0, "gold": 0, "damage": 0,
            "last_played": r["started_at"] or "",
        })
        a["games"]  += 1
        a["wins"]   += int(r["win"] or 0)
        a["kills"]  += int(r["kills"] or 0)
        a["deaths"] += int(r["deaths"] or 0)
        a["assists"]+= int(r["assists"] or 0)
        a["cs"]     += int(r["cs"] or 0)
        a["gold"]   += int(r["gold"] or 0)
        a["damage"] += int(r["damage"] or 0)
        if (r["started_at"] or "") > a["last_played"]:
            a["last_played"] = r["started_at"] or ""

    out: List[Dict[str, Any]] = []
    for c, a in agg.items():
        n = max(1, a["games"])
        kda = (a["kills"] + a["assists"]) / max(1, a["deaths"])
        out.append({
            "champion":    c,
            "games":       a["games"],
            "wins":        a["wins"],
            "wr":          a["wins"] / n,
            "wr_shrunk":   _sig.shrink(a["wins"], a["games"]),
            "kills":       a["kills"] / n,
            "deaths":      a["deaths"] / n,
            "assists":     a["assists"] / n,
            "kda":         kda,
            "cs_avg":      a["cs"] / n,
            "gold_avg":    a["gold"] / n,
            "damage_avg":  a["damage"] / n,
            "last_played": a["last_played"],
        })
    out.sort(key=lambda x: (x["games"], x["wr"]), reverse=True)
    return out


# ---------------------------------------------------------------------------
# Role comfort — share of games on the modal role; off-role penalty
# ---------------------------------------------------------------------------

def role_comfort(player: str) -> Dict[str, Any]:
    """Return { primary_role, role_share, role_breakdown:{role:games},
    off_role_penalty }. Role names follow the inhouse convention (TOP/JGL/MID/
    BOT/SUP, plus slot fallback like slot1..slot5 when the source data lacked a
    lane). off_role_penalty is a 0..1 value the engine subtracts from candidate
    fit when a player is asked to play outside their primary role."""
    conn = _db._conn()
    rows = conn.execute(
        "SELECT role, win FROM participants WHERE player = ?",
        (player,)).fetchall()
    by_role: Dict[str, List[int]] = defaultdict(lambda: [0, 0])
    for r in rows:
        role = (r["role"] or "").upper()
        if not role or role.startswith("SLOT"):
            continue
        by_role[role][0] += int(r["win"] or 0)
        by_role[role][1] += 1
    if not by_role:
        return {"primary_role": "", "role_share": 0.0,
                "role_breakdown": {}, "off_role_penalty": 0.0}
    total = sum(n for (_w, n) in by_role.values())
    breakdown = {role: n for role, (_w, n) in by_role.items()}
    primary, primary_games = max(by_role.items(), key=lambda kv: kv[1][1])
    role_share = primary_games[1] / total if total else 0.0
    # Off-role penalty grows as primary share grows (a OTP suffers more on a
    # secondary role than a flex player). Capped at 0.35.
    off_role_penalty = min(0.35, max(0.0, role_share - 0.40) * 0.6)
    return {"primary_role": primary,
            "role_share": role_share,
            "role_breakdown": breakdown,
            "off_role_penalty": off_role_penalty}


# ---------------------------------------------------------------------------
# Form — recency-weighted WR over the last N games
# ---------------------------------------------------------------------------

def form(player: str, window: int = 10) -> Dict[str, Any]:
    """Last-N games winrate + a simple trend label."""
    conn = _db._conn()
    rows = conn.execute(
        "SELECT p.win FROM participants p "
        "JOIN matches m ON m.id = p.match_id "
        "WHERE p.player = ? ORDER BY m.started_at DESC LIMIT ?",
        (player, int(window))).fetchall()
    if not rows:
        return {"window": 0, "wins": 0, "games": 0, "wr": 0.50,
                "label": "no data"}
    wins = sum(int(r["win"] or 0) for r in rows)
    n    = len(rows)
    wr   = wins / n
    if   wr >= 0.65: label = "hot"
    elif wr >= 0.55: label = "rising"
    elif wr <= 0.35: label = "cold"
    elif wr <= 0.45: label = "slumping"
    else:            label = "steady"
    return {"window": n, "wins": wins, "games": n,
            "wr": wr, "wr_shrunk": _sig.shrink(wins, n), "label": label}


# ---------------------------------------------------------------------------
# Player model bundle — the dict the engine reads
# ---------------------------------------------------------------------------

def model(player: str) -> Dict[str, Any]:
    """Compact bundle of every per-player signal the engine needs."""
    return {
        "player":  player,
        "pool":    champion_pool(player),
        "role":    role_comfort(player),
        "form":    form(player),
    }
