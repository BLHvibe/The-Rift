"""draft_engine_audit.py — drive N simulated drafts against the live engine
and dump per-action recommendations to a structured JSON log so the engine's
behaviour can be reviewed offline.

Usage:
    python scripts/draft_engine_audit.py --drafts 8 --out engine_audit.json

What it does:
    1. Pulls the real roster + inhouse-champs + scout sheets + primary-roles
       from the Fly REST API.
    2. Generates N random side allocations (5 BLUE vs 5 RED from the 19-player
       roster).
    3. For each draft, walks all 20 actions; at every action calls
       /api/engine/recommend_action with the current board state, captures the
       top suggestion + the full top-6 alternatives + the engine's "notes" /
       "tactical readout", and locks the engine's #1 pick (so the next action
       sees realistic state).
    4. Writes the resulting log as one JSON object per draft.

The output is meant to be read by either the user or an agent that's looking
for patterns like:
    * picks where the engine recommends an off-meta or wrong-role champion
    * bans where the engine targets a low-threat player
    * cases where COMFORT outweighs COUNTER or vice versa unexpectedly
    * archetypes that don't fit the locked roster

No client-side state is touched — runs entirely against the public REST API.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from typing import Any, Dict, List, Optional, Set

# Allow `python scripts/draft_engine_audit.py` from the repo root
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "the_rift"))

import requests

BASE = "https://the-rift-draft-sync.fly.dev"
ROLES = ("TOP", "JGL", "MID", "BOT", "SUP")


def _get(path: str) -> Optional[Dict[str, Any]]:
    try:
        r = requests.get(BASE + path, timeout=15)
        if r.status_code == 200:
            return r.json()
        print(f"  [api] GET {path} -> {r.status_code}: {r.text[:120]}",
              file=sys.stderr)
    except Exception as e:
        print(f"  [api] GET {path} failed: {e}", file=sys.stderr)
    return None


def _post(path: str, body: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        r = requests.post(BASE + path, json=body, timeout=20)
        if r.status_code == 200:
            return r.json()
        print(f"  [api] POST {path} -> {r.status_code}: {r.text[:200]}",
              file=sys.stderr)
    except Exception as e:
        print(f"  [api] POST {path} failed: {e}", file=sys.stderr)
    return None


def load_world() -> Dict[str, Any]:
    """Pull every reference dict the engine needs from the live API."""
    print("[audit] loading roster + scout + inhouse-champs + primary-roles…")
    players = _get("/api/players") or {}
    scout = _get("/api/scout") or {}
    inhouse_champs = _get("/api/inhouse-champs") or {}
    primary_roles = _get("/api/primary-roles") or {}
    rankings = _get("/api/rankings") or {}
    return {
        "players": players.get("players", []),
        "summoner_map": players.get("summoner_map", {}),
        "scout": {s["name"]: s for s in (scout.get("scout") or [])},
        "inhouse_champs": inhouse_champs.get("inhouse_champs") or {},
        "primary_roles": primary_roles.get("primary_roles") or {},
        "rankings": {r["name"]: r for r in (rankings.get("rankings") or [])},
    }


def _scout_pool_for_player(world, name) -> List[Dict[str, Any]]:
    """Pull the full champion pool from /api/scout-sheets/{name} → champ_pool.

    v4.1.1: also stashes must_bans on the world dict via a side-channel so
    `run_one_draft` can thread them into /api/engine/recommend_action."""
    data = _get(f"/api/scout-sheets/{name}")
    if not data:
        return []
    payload = data.get("scout_sheet") or {}

    # Stash must_bans for this player on world (created lazily).
    world.setdefault("must_bans", {})[name] = payload.get("must_bans") or []

    out = []
    for c in (payload.get("champ_pool") or []):
        cname = c.get("name") or c.get("champ")
        if not cname:
            continue
        results = c.get("results")
        if isinstance(results, str):
            results = [int(x) for x in results.split(",") if x.strip() in ("0", "1")]
        out.append({
            "champ":   cname,
            "games":   c.get("games", 0),
            "wins":    c.get("wins", 0),
            "losses":  c.get("losses", 0),
            "wr":      c.get("wr", "50%"),
            "kda":     c.get("kda", 1.5),
            "results": results if isinstance(results, list) else None,
            "roles":   {},
        })
    return out


def build_player_dict(name: str, role: str, world: Dict[str, Any]) -> Dict[str, Any]:
    """Build the per-player dict the engine expects (matches the shape the
    client sends from `draft.board.players`)."""
    sc = world["scout"].get(name) or {}
    rk = world["rankings"].get(name) or {}
    return {
        "name":        name,
        "tier":        sc.get("tier")        or rk.get("tier") or "Unranked",
        "score":       sc.get("score")       or 50.0,
        "final_score": sc.get("final_score") or rk.get("final_score") or 50.0,
        "tier_score":  sc.get("tier_score")  or rk.get("tier_score") or "",
        "rank_score":  sc.get("rank_score")  or rk.get("rank_score") or "",
        "rating":      sc.get("rating")      or rk.get("rating") or "?",
        "rank":        sc.get("rank")        or rk.get("rank") or 0,
        "wr":          sc.get("wr")          or rk.get("wr") or 0,
        "kda":         sc.get("kda")         or 0.0,
        "games":       sc.get("games")       or 0,
        "top_champs":  sc.get("top_champs")  or [],
        "form":        sc.get("form")        or "MIXED",
        "role":        role,
    }


def generate_draft(seed: int, roster: List[str]) -> Dict[str, List[str]]:
    """Random side allocation: shuffle 19 players, take 10, split 5/5."""
    rng = random.Random(seed)
    pick = list(roster)
    rng.shuffle(pick)
    chosen = pick[:10]
    return {"BLUE": chosen[0:5], "RED": chosen[5:10]}


def assign_roles(names: List[str], primary_roles: Dict[str, str],
                 seed: int) -> List[str]:
    """v4.1.1: assign 5 players to TOP/JGL/MID/BOT/SUP, respecting each
    player's primary role from /api/primary-roles. Where two players want
    the same primary, the earlier (lower-index) player gets it and the
    other falls back to their secondary (we don't know secondaries, so we
    pick the next unfilled role at random with a deterministic seed).

    Returns the role list in the same order as `names` (so player[i] maps
    to roles[i] when zipped). Without this fix the audit's old "alphabetical
    iteration order" forces every player off-role, polluting role-fit
    metrics."""
    role_order = ["TOP", "JGL", "MID", "BOT", "SUP"]
    rng = random.Random(seed)
    assigned: Dict[str, str] = {}      # name -> role
    taken: Set[str] = set()
    # Pass 1: try to give each player their primary.
    for n in names:
        pri = primary_roles.get(n)
        if pri and pri in role_order and pri not in taken:
            assigned[n] = pri
            taken.add(pri)
    # Pass 2: fill remaining players into remaining roles.
    remaining_roles = [r for r in role_order if r not in taken]
    rng.shuffle(remaining_roles)
    for n in names:
        if n not in assigned:
            assigned[n] = remaining_roles.pop(0)
    return [assigned[n] for n in names]


def run_one_draft(draft_id: int,
                  world: Dict[str, Any],
                  blue_names: List[str],
                  red_names: List[str]) -> Dict[str, Any]:
    """Walk one full 20-action draft, log every recommendation, lock the
    engine's #1 pick at each step."""
    print(f"\n[audit] === draft #{draft_id} ===")
    print(f"   BLUE: {blue_names}")
    print(f"   RED:  {red_names}")

    # v4.1.1: respect primary roles when assigning. Old code zipped each
    # team's 5 names to ROLES in iteration order, making every pick off-role.
    # CRITICAL: the engine reads `state.players[side][i]` where i = ROLES.index(role),
    # so the list MUST be in (TOP, JGL, MID, BOT, SUP) order. After assigning
    # roles we re-sort each team to that order.
    primary_roles_map = world.get("primary_roles") or {}
    blue_roles = assign_roles(blue_names, primary_roles_map, seed=draft_id * 17)
    red_roles = assign_roles(red_names, primary_roles_map, seed=draft_id * 17 + 1)
    role_index = {"TOP": 0, "JGL": 1, "MID": 2, "BOT": 3, "SUP": 4}
    blue_pairs = sorted(zip(blue_names, blue_roles), key=lambda nr: role_index[nr[1]])
    red_pairs = sorted(zip(red_names, red_roles), key=lambda nr: role_index[nr[1]])
    blue_players = [build_player_dict(n, r, world) for n, r in blue_pairs]
    red_players = [build_player_dict(n, r, world) for n, r in red_pairs]
    print(f"   BLUE: {[f'{n}:{r}' for n, r in blue_pairs]}")
    print(f"   RED : {[f'{n}:{r}' for n, r in red_pairs]}")
    # Update the names lists so downstream scout/inhouse lookups use the
    # reordered roster.
    blue_names = [p["name"] for p in blue_players]
    red_names = [p["name"] for p in red_players]

    # scout_champs for engine (the #2 comfort signal)
    scout_champs: Dict[str, List[Dict[str, Any]]] = {}
    for n in blue_names + red_names:
        scout_champs[n] = _scout_pool_for_player(world, n)

    state: Dict[str, Any] = {
        "our_side": "BLUE",
        "pointer":  0,
        "players":  {"BLUE": blue_players, "RED": red_players},
        "picks":    {"BLUE": {}, "RED": {}},
        "bans":     {"BLUE": [], "RED": []},
        "history":  [],
    }

    # v4.1.1: track prev archetype per side so hysteresis kicks in.
    prev_arch: Dict[str, Optional[str]] = {"BLUE": None, "RED": None}

    log: List[Dict[str, Any]] = []
    for step in range(20):
        # The acting side this step (need to know to look up prev_archetype).
        # Easiest: just include both, the engine picks per acting side.
        # We only pass the prev_arch for the side currently on the clock.
        # That side is derivable from state.pointer but the engine returns
        # `action.side` too. For now pass our_side's prev (engine uses it for
        # the acting side via the request).
        body = {
            "state": state,
            "inhouse_champs": world["inhouse_champs"],
            "primary_roles":  world["primary_roles"],
            "scout_champs":   scout_champs,
            "must_bans":      world.get("must_bans") or {},
            "n": 6,
        }
        # We can't know acting side without reading the action — include both
        # prev_arch entries; the engine endpoint uses a single string so pass
        # the most recent one from EITHER side as a best-effort signal.
        # (Server keys on `action.side` internally for picks.)
        last_arch = prev_arch.get("BLUE") or prev_arch.get("RED")
        if last_arch:
            body["prev_archetype"] = last_arch
        rec = _post("/api/engine/recommend_action", body)
        if not rec:
            log.append({"step": step, "error": "engine call failed"})
            break

        action = rec.get("action")
        suggestions = rec.get("suggestions") or []
        top = suggestions[0] if suggestions else None
        if not top or not top.get("champion"):
            print(f"   step {step:2d} no suggestion — stopping")
            log.append({"step": step, "action": action,
                        "suggestions": [], "applied": None,
                        "notes": rec.get("notes")})
            break

        # action is [idx, side, kind, phase, label]
        side  = action[1] if isinstance(action, list) else None
        kind  = action[2] if isinstance(action, list) else None
        label = action[4] if isinstance(action, list) else "?"

        applied_champ = top["champion"]
        applied_role  = top.get("role")
        log.append({
            "step":          step,
            "action_label":  label,
            "side":          side,
            "kind":          kind,
            "applied":       {"champion": applied_champ, "role": applied_role,
                              "tag": top.get("tag"), "why": top.get("why"),
                              "score": top.get("score"),
                              "player": top.get("player"),
                              "factors": top.get("factors") or {}},
            "alternatives":  [{"champion": s.get("champion"),
                               "score": s.get("score"),
                               "tag": s.get("tag"),
                               "why": s.get("why"),
                               "player": s.get("player"),
                               "role": s.get("role"),
                               "factors": s.get("factors") or {}}
                              for s in suggestions[:6]],
            "target_comp":   rec.get("target_comp"),
            "notes":         rec.get("notes"),
        })

        # v4.1.1: track archetype for next-call hysteresis.
        tcomp = rec.get("target_comp") or {}
        arch_now = tcomp.get("archetype")
        if arch_now and side:
            prev_arch[side] = arch_now

        # Lock the applied pick into state for the next step
        if kind == "pick":
            if applied_role:
                state["picks"][side][applied_role] = applied_champ
            else:
                # Fall back: take first open role
                for r in ROLES:
                    if r not in state["picks"][side]:
                        state["picks"][side][r] = applied_champ
                        break
        else:  # ban
            state["bans"][side].append(applied_champ)
        state["pointer"] = step + 1
        state["history"].append({"action_idx": step, "kind": kind,
                                 "side": side, "champ": applied_champ,
                                 "role": applied_role})
        print(f"   step {step:2d}  {label:<10}  {kind:<4}  {applied_champ:<15}"
              f"  {top.get('tag','-'):<8}  {top.get('why','')[:60]}")
        time.sleep(0.05)

    return {
        "draft_id":   draft_id,
        "rosters":    {"BLUE": blue_names, "RED": red_names},
        "final_state": {
            "picks": state["picks"],
            "bans":  state["bans"],
        },
        "log":        log,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--drafts", type=int, default=8,
                    help="how many drafts to simulate (default: 8)")
    ap.add_argument("--seed", type=int, default=42,
                    help="random seed (default: 42)")
    ap.add_argument("--out", default="engine_audit.json",
                    help="output JSON file (default: engine_audit.json)")
    args = ap.parse_args()

    world = load_world()
    print(f"[audit] roster size: {len(world['players'])}")

    if len(world["players"]) < 10:
        print("[audit] need at least 10 players on the roster", file=sys.stderr)
        sys.exit(1)

    results = []
    for i in range(args.drafts):
        rosters = generate_draft(args.seed + i, world["players"])
        results.append(run_one_draft(i + 1, world,
                                     rosters["BLUE"], rosters["RED"]))

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump({"world": {"roster": world["players"]},
                   "drafts": results}, fh, indent=2)
    print(f"\n[audit] wrote {len(results)} drafts to {args.out}")


if __name__ == "__main__":
    main()
