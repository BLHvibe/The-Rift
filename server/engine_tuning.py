"""
engine_tuning.py — Phase 2e · tuning loop.

A small registry of named weights the engine consults, plus get / set / list
helpers + JSON persistence beside the DB. The goal is to move engine knobs
out of hand-tuned magic numbers in engine_core.py and into a *visible*,
*adjustable*, *re-fittable* surface — so we can:

  - Inspect what the engine currently weights (transparency).
  - Bump a knob and immediately see the effect (manual tuning).
  - Eventually fit knobs to real outcomes via the backtest harness (automated
    tuning, the next layer up from this scaffold).

Default values match the engine's current hand-tuned constants — bumping a
knob to its default is a no-op, so this is purely additive until anyone
actually changes a value.
"""
from __future__ import annotations

import json
import os
import threading
from typing import Any, Dict, Optional

import db as _db


_LOCK = threading.Lock()


# Defaults match the existing hand-tuned constants in engine_core. Each entry
# is (default, low, high, doc).
DEFAULTS: Dict[str, Dict[str, Any]] = {
    "shrinkage_k":             {"default": 8.0,  "low": 0.0,  "high": 50.0,
                                 "doc": "Bayesian shrinkage strength for data-vs-prior blend."},
    "counter_weight":          {"default": 1.0,  "low": 0.0,  "high": 3.0,
                                 "doc": "Multiplier on counter contribution in score_team."},
    "synergy_weight":          {"default": 1.0,  "low": 0.0,  "high": 3.0,
                                 "doc": "Multiplier on synergy contribution in score_team."},
    "archetype_weight":        {"default": 1.0,  "low": 0.0,  "high": 3.0,
                                 "doc": "Multiplier on archetype-vector match in score_team."},
    "comfort_weight":          {"default": 1.0,  "low": 0.0,  "high": 3.0,
                                 "doc": "Multiplier on per-player champion comfort."},
    "off_role_penalty_scale":  {"default": 1.0,  "low": 0.0,  "high": 3.0,
                                 "doc": "Scales the off-role penalty from engine_players."},
    "blind_safety_threshold":  {"default": 0.35, "low": 0.0,  "high": 1.0,
                                 "doc": "Champs below this blind-safety score get flagged."},
}


def _path() -> str:
    db_dir = os.path.dirname(_db._db_path())
    return os.path.join(db_dir, "rift_tuning.json")


def _load() -> Dict[str, float]:
    p = _path()
    if not os.path.exists(p):
        return {k: v["default"] for k, v in DEFAULTS.items()}
    try:
        with open(p, "r", encoding="utf-8") as f:
            saved = json.load(f)
    except Exception:
        saved = {}
    # Backfill any missing keys with their default.
    out = {k: v["default"] for k, v in DEFAULTS.items()}
    for k, v in saved.items():
        if k in DEFAULTS:
            out[k] = float(v)
    return out


def _save(values: Dict[str, float]) -> None:
    try:
        with open(_path(), "w", encoding="utf-8") as f:
            json.dump(values, f, indent=2)
    except Exception as _e:
        print(f"[tuning] save failed: {_e}")


# ---------------------------------------------------------------------------
# Cached state — read once, mutated by set/reset
# ---------------------------------------------------------------------------

_VALUES: Optional[Dict[str, float]] = None


def values() -> Dict[str, float]:
    global _VALUES
    with _LOCK:
        if _VALUES is None:
            _VALUES = _load()
        return dict(_VALUES)


def get(name: str) -> float:
    return values().get(name, DEFAULTS.get(name, {}).get("default", 0.0))


def set_value(name: str, v: float) -> Dict[str, Any]:
    global _VALUES
    if name not in DEFAULTS:
        return {"ok": False, "error": f"unknown knob: {name}"}
    meta = DEFAULTS[name]
    if not (meta["low"] <= v <= meta["high"]):
        return {"ok": False,
                "error": f"out of range [{meta['low']}, {meta['high']}]"}
    with _LOCK:
        cur = _VALUES if _VALUES is not None else _load()
        cur[name] = float(v)
        _VALUES = cur
        _save(cur)
    return {"ok": True, "name": name, "value": v}


def reset(name: Optional[str] = None) -> Dict[str, Any]:
    """Reset one knob, or all if name is None."""
    global _VALUES
    with _LOCK:
        cur = _VALUES if _VALUES is not None else _load()
        if name is None:
            cur = {k: v["default"] for k, v in DEFAULTS.items()}
        elif name in DEFAULTS:
            cur[name] = DEFAULTS[name]["default"]
        else:
            return {"ok": False, "error": f"unknown knob: {name}"}
        _VALUES = cur
        _save(cur)
    return {"ok": True, "values": dict(cur)}


def describe() -> Dict[str, Any]:
    """For /api/engine/tuning — current values + metadata."""
    cur = values()
    out: Dict[str, Any] = {}
    for k, meta in DEFAULTS.items():
        out[k] = {**meta, "value": cur.get(k, meta["default"])}
    return out
