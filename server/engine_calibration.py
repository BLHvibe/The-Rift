"""
engine_calibration.py — Phase 2c · honest confidence.

When the engine says "65% win probability," that should mean ~65% of the time
it's right. We get there by:

1. Beta-binomial confidence interval — every estimated rate carries a CI
   that widens with small samples. The UI shows the CI alongside the point
   estimate so a "65% ±20" reads honestly as "we don't know yet."
2. Sample-size labels — translate raw n into a human-readable confidence
   tag (none / sparse / fair / good / strong) the engine surfaces.
3. Coverage gaps — flag champions/pairs with no historical data so the
   engine explicitly says "no inhouse data — this is a generic guess."

This is scaffolding for now. Once the backtest harness (2d) accumulates a
real prediction-vs-outcome log, we plug in Platt scaling (logistic regression
on the engine's raw scores → calibrated probabilities) so the calibration is
empirical instead of theoretical.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Optional, Tuple


# ---------------------------------------------------------------------------
# Beta-binomial CI — Wilson score interval
# ---------------------------------------------------------------------------

def wilson_ci(wins: int, games: int, z: float = 1.96) -> Tuple[float, float]:
    """95% CI on a winrate by default. Returns (low, high) clamped to [0,1]."""
    if games <= 0:
        return (0.0, 1.0)
    p   = wins / games
    n   = games
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half   = (z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)) / den
    return (max(0.0, centre - half), min(1.0, centre + half))


def confidence_label(games: int) -> str:
    """Human-readable sample-size bucket. Aligns with the UI's confidence chip."""
    if games <= 0:   return "none"
    if games < 5:    return "sparse"
    if games < 15:   return "fair"
    if games < 40:   return "good"
    return "strong"


def calibrated_estimate(wins: int, games: int,
                        prior_rate: float = 0.50) -> Dict[str, Any]:
    """One-shot helper used by the API. Returns:
        { wr, ci_low, ci_high, confidence, n }
    """
    if games <= 0:
        return {"wr": prior_rate, "ci_low": 0.0, "ci_high": 1.0,
                "confidence": "none", "n": 0}
    wr = wins / games
    lo, hi = wilson_ci(wins, games)
    return {"wr": wr, "ci_low": lo, "ci_high": hi,
            "confidence": confidence_label(games), "n": games}


# ---------------------------------------------------------------------------
# Future hook: Platt scaling
# ---------------------------------------------------------------------------

def platt_calibrate(raw_score: float,
                    fit: Optional[Dict[str, float]] = None) -> float:
    """Sigmoid calibration: returns a probability in [0,1] for a raw engine score.
    Until we have a real `fit` from the backtest harness, this is the identity
    sigmoid (raw 0 → 0.5, raw +1 → ~0.73, raw -1 → ~0.27). Once 2d's logs
    accumulate, the fit dict comes from a logistic regression over them."""
    a = (fit or {}).get("a", 1.0)
    b = (fit or {}).get("b", 0.0)
    x = a * raw_score + b
    return 1.0 / (1.0 + math.exp(-x))
