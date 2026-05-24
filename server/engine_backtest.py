"""
engine_backtest.py — Phase 2d · backtest harness + tracked accuracy.

Replays every match in the DB through the engine, asks "did the engine pick
the winning team?", and accumulates a hit-rate. The hit-rate is visible —
surfaced via /api/engine/backtest — so engine quality is *measurable* and a
regression guard can stop a change from quietly making things worse.

This is a coarse first pass — accuracy = how often the engine's score_team
favors the team that actually won. Future passes can layer in:
  - Pick-by-pick prediction (did the engine's #1 candidate match the real
    pick at each turn?).
  - Calibration error (Brier score / log-loss between predicted probability
    and outcome).
  - Per-archetype slices (engine is great at split-push but bad at poke).

The harness is self-contained: hits db.py directly, runs the engine in
memory, returns a JSON summary. Idempotent — safe to run anytime.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple

import db as _db
import engine_core as _eng


# ---------------------------------------------------------------------------
# Persisted state — accuracy log lives next to the DB so a Fly restart
# doesn't lose it.
# ---------------------------------------------------------------------------

def _log_path() -> str:
    db_dir = os.path.dirname(_db._db_path())
    return os.path.join(db_dir, "rift_backtest.json")


def load_log() -> Dict[str, Any]:
    path = _log_path()
    if not os.path.exists(path):
        return {"runs": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"runs": []}


def save_log(log: Dict[str, Any]) -> None:
    try:
        with open(_log_path(), "w", encoding="utf-8") as f:
            json.dump(log, f, indent=2)
    except Exception as _e:
        print(f"[backtest] save_log failed: {_e}")


# ---------------------------------------------------------------------------
# Core: replay one match
# ---------------------------------------------------------------------------

def _team_champions(conn, match_id: str) -> Tuple[List[str], List[str], str]:
    """Returns (blue_champs, red_champs, actual_winner)."""
    rows = conn.execute(
        "SELECT team, champion, win FROM participants WHERE match_id = ?",
        (match_id,)).fetchall()
    blue, red = [], []
    winner = ""
    for r in rows:
        team = (r["team"] or "").lower()
        c    = r["champion"] or ""
        if not c:
            continue
        if team == "blue":
            blue.append(c)
            if int(r["win"] or 0) and not winner:
                winner = "blue"
        elif team == "red":
            red.append(c)
            if int(r["win"] or 0) and not winner:
                winner = "red"
    return blue, red, winner


def predict_winner(blue: List[str], red: List[str]) -> Tuple[str, float]:
    """Returns (predicted_winner, confidence_in_[0,1]).
    Confidence is |score_blue - score_red| squashed to [0,1]."""
    if not blue or not red:
        return ("", 0.0)
    s_blue = _eng.score_team(blue, enemy=red)
    s_red  = _eng.score_team(red,  enemy=blue)
    diff   = s_blue - s_red
    # The engine's scores are unbounded but typically live in [-15, +15].
    # Squash to a [0,1] confidence via a soft scale.
    import math
    conf = 1.0 / (1.0 + math.exp(-diff / 4.0))
    return ("blue" if diff >= 0 else "red", abs(conf - 0.5) * 2)


# ---------------------------------------------------------------------------
# Run a backtest pass
# ---------------------------------------------------------------------------

def run(limit: Optional[int] = None) -> Dict[str, Any]:
    """Replay matches and score the engine. Returns a summary + writes a
    run entry to the persisted log."""
    conn = _db._conn()
    q = "SELECT id FROM matches ORDER BY started_at"
    if limit:
        q += f" LIMIT {int(limit)}"
    match_ids = [r["id"] for r in conn.execute(q).fetchall()]

    correct = 0
    skipped = 0
    total   = 0
    detail: List[Dict[str, Any]] = []

    for mid in match_ids:
        blue, red, actual = _team_champions(conn, mid)
        if not actual or not blue or not red:
            skipped += 1
            continue
        pred, conf = predict_winner(blue, red)
        if not pred:
            skipped += 1
            continue
        total += 1
        if pred == actual:
            correct += 1
        detail.append({
            "match_id": mid, "actual": actual,
            "pred": pred, "confidence": round(conf, 3),
            "ok": pred == actual,
        })

    accuracy = (correct / total) if total else 0.0
    summary = {
        "at":         time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "matches":    total,
        "correct":    correct,
        "skipped":    skipped,
        "accuracy":   accuracy,
        "engine":     "phase2-foundation",   # bump when engine math changes
    }

    log = load_log()
    log.setdefault("runs", []).append(summary)
    # Keep the last 50 runs to bound storage.
    log["runs"] = log["runs"][-50:]
    save_log(log)

    return {"summary": summary, "detail": detail[:20]}  # head sample, not full


def history() -> List[Dict[str, Any]]:
    return load_log().get("runs", [])


def regression_guard(min_accuracy: Optional[float] = None) -> Dict[str, Any]:
    """Compare the latest run against the best-ever accuracy. Returns ok=False
    if accuracy dropped more than 3% below the best run. `min_accuracy`, when
    supplied, is an absolute floor — useful for CI checks."""
    runs = history()
    if not runs:
        return {"ok": True, "reason": "no runs yet"}
    latest = runs[-1]
    best   = max(runs, key=lambda r: r.get("accuracy", 0.0))
    drop = best["accuracy"] - latest["accuracy"]
    ok = (drop <= 0.03) and (min_accuracy is None
                              or latest["accuracy"] >= min_accuracy)
    return {"ok": ok, "latest": latest, "best": best,
            "drop": drop, "min_accuracy": min_accuracy}
