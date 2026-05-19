"""
draft_board.py — Tournament-draft sequence model + per-action recommender.

Pure Python: no DPG, no I/O. Reuses `draft_engine` for ALL champion knowledge
and scoring. Import-source-agnostic — the same `DraftBoardState` is driven by
either manual UI entry or the LCU live-import adapter, so the engine/board
logic never needs to know where an action came from.

Layers of the tournament-draft board (see ../DRAFT_ASSIST_HANDOFF.md):

  E1 ✓ DRAFT_SEQUENCE + DraftBoardState + recommend_action skeleton.
  E2 ✓ blind_safety / flex_score / counter_value / contested /
       cohesion_text / side_best_comfort (pure, table-driven, cached).
  E3 ✓ pick recommender: POWER / SAFE / COUNTER / FLEX / COMFORT tagging,
       context-aware (enemy info on board, late vs early slot), ranking
       blend, archetype steering via target_archetype()/recommend_comps.
  E4 ☐ phase-split ban recommender (P1 comfort/contested/flex/role-weight;
       P2 counter-our-committed-wincon). Ban branch is still the E1
       baseline (reuses _eng.recommend_bans) until E4.
"""

from __future__ import annotations

from typing import Any, Dict, List, NamedTuple, Optional, Sequence, Set, Tuple

# --- Engine import (match the convention used across the codebase) ----------
try:
    from data import draft_engine as _eng  # type: ignore
except Exception:  # pragma: no cover - frozen-exe / direct-run fallback
    try:
        import draft_engine as _eng  # type: ignore
    except Exception:
        _eng = None  # type: ignore


# ============================================================================
# Roles (kept aligned with draft_engine.ROLES_UPPER)
# ============================================================================

ROLES: Tuple[str, ...] = ("TOP", "JGL", "MID", "BOT", "SUP")
SIDES: Tuple[str, ...] = ("BLUE", "RED")


def _other(side: str) -> str:
    return "RED" if side == "BLUE" else "BLUE"


# ============================================================================
# The tournament draft sequence (standard competitive pick/ban order)
# ============================================================================
#
#   BAN 1   B R B R B R                       (6 bans, Blue starts)
#   PICK 1  B | R R | B B | R                 (B1 first ; R1 R2 ; B2 B3 ; R3)
#   BAN 2   R B R B                            (4 bans, Red starts)
#   PICK 2  R | B B | R                        (R4 first ; B4 B5 ; R5 LAST)
#
# 20 actions total. `label` is the human name; pick labels use the canonical
# B1..B5 / R1..R5 nomenclature, bans use "Blue Ban N" / "Red Ban N".

class DraftAction(NamedTuple):
    idx: int            # 0..19, position in the sequence
    side: str           # "BLUE" | "RED"  — the team performing this action
    kind: str           # "ban" | "pick"
    phase: int          # 1 | 2
    label: str           # "Blue Ban 1", "B1", "R5", ...


def _build_sequence() -> List[DraftAction]:
    seq: List[DraftAction] = []

    # Ban phase 1: B R B R B R
    ban1_sides = ["BLUE", "RED", "BLUE", "RED", "BLUE", "RED"]
    ban1_count = {"BLUE": 0, "RED": 0}
    for s in ban1_sides:
        ban1_count[s] += 1
        seq.append(DraftAction(len(seq), s, "ban", 1,
                               f"{s.title()} Ban {ban1_count[s]}"))

    # Pick phase 1: B | R R | B B | R   →  B1 R1 R2 B2 B3 R3
    pick1 = ["BLUE", "RED", "RED", "BLUE", "BLUE", "RED"]
    pick_no = {"BLUE": 0, "RED": 0}
    for s in pick1:
        pick_no[s] += 1
        tag = "B" if s == "BLUE" else "R"
        seq.append(DraftAction(len(seq), s, "pick", 1, f"{tag}{pick_no[s]}"))

    # Ban phase 2: R B R B
    ban2_sides = ["RED", "BLUE", "RED", "BLUE"]
    ban2_count = {"BLUE": 3, "RED": 3}  # continues from ban phase 1
    for s in ban2_sides:
        ban2_count[s] += 1
        seq.append(DraftAction(len(seq), s, "ban", 2,
                               f"{s.title()} Ban {ban2_count[s]}"))

    # Pick phase 2: R | B B | R   →  R4 B4 B5 R5
    pick2 = ["RED", "BLUE", "BLUE", "RED"]
    for s in pick2:
        pick_no[s] += 1
        tag = "B" if s == "BLUE" else "R"
        seq.append(DraftAction(len(seq), s, "pick", 2, f"{tag}{pick_no[s]}"))

    return seq


DRAFT_SEQUENCE: List[DraftAction] = _build_sequence()
assert len(DRAFT_SEQUENCE) == 20
assert sum(1 for a in DRAFT_SEQUENCE if a.kind == "ban") == 10
assert sum(1 for a in DRAFT_SEQUENCE if a.kind == "pick") == 10


# ============================================================================
# Board state
# ============================================================================

class _HistEntry(NamedTuple):
    action_idx: int
    kind: str
    side: str
    champ: str
    role: Optional[str]   # role filled (picks only)


class DraftBoardState:
    """
    Mutable state for one tournament draft. Source-agnostic: manual UI and the
    LCU adapter both mutate this through `apply` / `undo`.

    players: {"BLUE": [p0..p4], "RED": [p0..p4]} — index == ROLES index, i.e.
             players[side][i] is the player assigned ROLES[i]. Each player is a
             scouting dict (name, tier, final_score/score, wr/winrate, games,
             kda, form, top_champs, ...). `role` is (re)stamped on access so
             engine calls see the assigned role.
    picks:   {"BLUE": {role: champ}, "RED": {...}}
    bans:    {"BLUE": [champ, ...], "RED": [...]}
    pointer: index into DRAFT_SEQUENCE (== 20 when the draft is complete)
    our_side: which side the user is drafting for ("BLUE" | "RED")
    """

    def __init__(
        self,
        blue_players: Sequence[Dict[str, Any]],
        red_players: Sequence[Dict[str, Any]],
        our_side: str = "BLUE",
    ) -> None:
        self.players: Dict[str, List[Dict[str, Any]]] = {
            "BLUE": [dict(p) for p in blue_players],
            "RED":  [dict(p) for p in red_players],
        }
        for side in SIDES:
            for i, p in enumerate(self.players[side]):
                p["role"] = ROLES[i] if i < len(ROLES) else p.get("role", "")
        self.picks: Dict[str, Dict[str, str]] = {"BLUE": {}, "RED": {}}
        self.bans: Dict[str, List[str]] = {"BLUE": [], "RED": []}
        self.pointer: int = 0
        self.our_side: str = our_side if our_side in SIDES else "BLUE"
        self._history: List[_HistEntry] = []

    # --- queries -----------------------------------------------------------

    def current_action(self) -> Optional[DraftAction]:
        if 0 <= self.pointer < len(DRAFT_SEQUENCE):
            return DRAFT_SEQUENCE[self.pointer]
        return None

    def is_complete(self) -> bool:
        return self.pointer >= len(DRAFT_SEQUENCE)

    def is_our_turn(self) -> bool:
        a = self.current_action()
        return bool(a and a.side == self.our_side)

    def used_champs(self) -> Set[str]:
        used: Set[str] = set()
        for side in SIDES:
            used.update(c for c in self.bans[side] if c)
            used.update(c for c in self.picks[side].values() if c)
        return used

    def open_roles(self, side: str) -> List[str]:
        return [r for r in ROLES if r not in self.picks[side]]

    def player_for_role(self, side: str, role: str) -> Optional[Dict[str, Any]]:
        try:
            return self.players[side][ROLES.index(role)]
        except (ValueError, IndexError):
            return None

    def locked_picks(self, side: str) -> List[str]:
        """Champs locked for `side`, in role order (skips not-yet-picked)."""
        return [self.picks[side][r] for r in ROLES if r in self.picks[side]]

    def engine_players(self, side: str) -> List[Dict[str, Any]]:
        """Players for `side` with role + any locked champ stamped on, for
        passing to draft_engine functions."""
        out: List[Dict[str, Any]] = []
        for i, p in enumerate(self.players[side]):
            q = dict(p)
            role = ROLES[i] if i < len(ROLES) else p.get("role", "")
            q["role"] = role
            if role in self.picks[side]:
                q["locked_champ"] = self.picks[side][role]
            out.append(q)
        return out

    # --- mutation ----------------------------------------------------------

    def apply(self, champ: str, role: Optional[str] = None) -> bool:
        """
        Apply `champ` to the current action. For picks, `role` selects which of
        the acting side's still-open roles is filled; if omitted and exactly
        one role is open it is inferred. Returns False if the move is invalid
        (no current action, champ already used, bad/duplicate role).
        """
        a = self.current_action()
        if a is None or not champ:
            return False
        champ = champ.strip()
        if champ in self.used_champs():
            return False

        if a.kind == "ban":
            self.bans[a.side].append(champ)
            self._history.append(_HistEntry(a.idx, "ban", a.side, champ, None))
            self.pointer += 1
            return True

        # pick
        open_r = self.open_roles(a.side)
        if role is None:
            if len(open_r) == 1:
                role = open_r[0]
            else:
                return False  # caller must disambiguate which player picks
        if role not in open_r:
            return False
        self.picks[a.side][role] = champ
        self._history.append(_HistEntry(a.idx, "pick", a.side, champ, role))
        self.pointer += 1
        return True

    def reassign(self, side: str, from_role: str, to_role: str) -> bool:
        """Swap the champion in `from_role` with whatever is in `to_role`
        (or move it into the empty slot) on the same `side`. Post-hoc role
        correction — pointer/history are intentionally untouched, since the
        draft sequence already advanced when these picks were made."""
        if side not in SIDES or from_role == to_role:
            return False
        if from_role not in ROLES or to_role not in ROLES:
            return False
        picks = self.picks[side]
        if from_role not in picks:
            return False
        champ = picks[from_role]
        other = picks.get(to_role)
        picks[to_role] = champ
        if other is None:
            del picks[from_role]
        else:
            picks[from_role] = other
        return True

    def mirror(self, picks: Dict[str, Dict[str, str]],
               bans: Dict[str, List[str]], completed: int,
               our_side: Optional[str] = None) -> None:
        """Drive the board from an external authority (LCU live champ select).
        Replaces picks/bans/pointer wholesale and rebuilds an approximate
        history so the timeline still renders. Manual apply/undo are untouched
        and simply unused while a live poll is mirroring."""
        if our_side in SIDES:
            self.our_side = our_side
        self.picks = {"BLUE": dict(picks.get("BLUE", {})),
                      "RED": dict(picks.get("RED", {}))}
        self.bans = {"BLUE": [c for c in bans.get("BLUE", []) if c],
                     "RED": [c for c in bans.get("RED", []) if c]}
        self.pointer = max(0, min(int(completed), len(DRAFT_SEQUENCE)))
        # Approximate per-slot history (display-only; engine uses picks/bans).
        self._history = []
        bi = {"BLUE": 0, "RED": 0}
        pr = {s: [r for r in ROLES if r in self.picks[s]] for s in SIDES}
        pidx = {"BLUE": 0, "RED": 0}
        for a in DRAFT_SEQUENCE[:self.pointer]:
            if a.kind == "ban":
                lst = self.bans[a.side]
                if bi[a.side] < len(lst):
                    self._history.append(_HistEntry(
                        a.idx, "ban", a.side, lst[bi[a.side]], None))
                    bi[a.side] += 1
            else:
                roles = pr[a.side]
                if pidx[a.side] < len(roles):
                    rr = roles[pidx[a.side]]
                    self._history.append(_HistEntry(
                        a.idx, "pick", a.side, self.picks[a.side][rr], rr))
                    pidx[a.side] += 1

    def locked_at(self, action_idx: int) -> Optional[str]:
        """Exact champ locked at a given sequence index (from history) — used
        by the UI timeline instead of reconstructing it heuristically."""
        for h in self._history:
            if h.action_idx == action_idx:
                return h.champ
        return None

    def undo(self) -> bool:
        if not self._history:
            return False
        h = self._history.pop()
        if h.kind == "ban":
            if self.bans[h.side] and self.bans[h.side][-1] == h.champ:
                self.bans[h.side].pop()
        else:
            self.picks[h.side].pop(h.role, None)
        self.pointer = h.action_idx
        return True

    # --- debug -------------------------------------------------------------

    def summary(self) -> str:
        lines = [f"our_side={self.our_side} pointer={self.pointer}"
                 f" complete={self.is_complete()}"]
        for side in SIDES:
            picks = ", ".join(f"{r}:{self.picks[side].get(r,'-')}"
                              for r in ROLES)
            bans = ", ".join(self.bans[side]) or "-"
            lines.append(f"  {side:<4} picks[{picks}] bans[{bans}]")
        return "\n".join(lines)


# ============================================================================
# Shared: per-player candidate helper (used by E2 contested + E3 picks)
# ============================================================================

def _candidates_for_player(
    player: Dict[str, Any],
    role: str,
    inhouse_champs: Dict[str, List[Dict]],
    primary_roles: Dict[str, str],
    exclude: Set[str],
    k: int = 8,
    scout_champs: Optional[Dict[str, List[Dict]]] = None,
) -> List[Tuple[str, float]]:
    """(champ, comfort) for a player at a role, via the engine's own candidate
    generator, with already-used champions removed."""
    if _eng is None:
        return []
    p = dict(player)
    p["role"] = role
    gen = getattr(_eng, "_player_candidates", None)
    if gen is None:
        return []
    try:
        cands = gen(p, inhouse_champs or {}, primary_roles or {}, k + len(exclude),
                    scout_champs=scout_champs or {})
    except TypeError:
        # Older engine without scout_champs kwarg — fall back gracefully.
        try:
            cands = gen(p, inhouse_champs or {}, primary_roles or {}, k + len(exclude))
        except Exception:
            return []
    except Exception:
        return []
    out = [(c, s) for (c, s) in cands if c and c not in exclude]
    return out[:k]


# ============================================================================
# E2 — Draft-intelligence helper metrics (pure; table-driven; cached)
# ============================================================================

_incoming_counter_cache: Optional[Dict[str, float]] = None
_incoming_lane_cache: Optional[Dict[str, float]] = None
# victim -> [(attacker, strength 0..1)] : who beats `victim` (counter + lane)
_counters_of_cache: Optional[Dict[str, List[Tuple[str, float]]]] = None


def _build_incoming() -> None:
    """Build, once from the engine tables:
      • per champion X, the worst *incoming* counter / lane pressure
        (max over all A of how hard A beats X)  → blind_safety
      • the reverse counter index victim → attackers  → phase-2 bans
    """
    global _incoming_counter_cache, _incoming_lane_cache, _counters_of_cache
    ic: Dict[str, float] = {}
    il: Dict[str, float] = {}
    rev: Dict[str, Dict[str, float]] = {}
    if _eng is not None:
        for (atk, x), v in getattr(_eng, "COUNTERS", {}).items():
            if v > ic.get(x, 0.0):
                ic[x] = v
            cur = rev.setdefault(x, {})
            if v > cur.get(atk, 0.0):
                cur[atk] = v
        for (atk, x), v in getattr(_eng, "LANE_MATCHUPS", {}).items():
            if v > il.get(x, 0.0):          # v>0 ⇒ A has the lane edge over X
                il[x] = v
            if v > 0:                        # lane edge → comparable ~v/16
                cur = rev.setdefault(x, {})
                s = min(0.5, v / 16.0)
                if s > cur.get(atk, 0.0):
                    cur[atk] = s
    _incoming_counter_cache = ic
    _incoming_lane_cache = il
    _counters_of_cache = {
        victim: sorted(atk.items(), key=lambda kv: -kv[1])
        for victim, atk in rev.items()
    }


def _counters_of(victim: str) -> List[Tuple[str, float]]:
    """Champions that beat `victim` (counter table + winning lane), strongest
    first. Used to pick phase-2 bans that protect our committed picks."""
    if _counters_of_cache is None:
        _build_incoming()
    return (_counters_of_cache or {}).get(victim, [])


# Ban role-importance (research: Top > Mid > ADC > Sup > JGL).
ROLE_BAN_WEIGHT: Dict[str, float] = {
    "TOP": 1.25, "MID": 1.15, "BOT": 1.05, "SUP": 0.95, "JGL": 0.90,
}


def _role_of_player(state: "DraftBoardState", side: str,
                    name: str) -> str:
    for i, p in enumerate(state.players.get(side, [])):
        if p.get("name") == name:
            return ROLES[i] if i < len(ROLES) else ""
    return ""


def champ_role_count(champ: str) -> int:
    """How many of the 5 roles this champ is a valid pick for (table-only)."""
    if _eng is None or not champ:
        return 1
    rv = getattr(_eng, "ROLE_VALID", {})
    return sum(1 for r in ROLES if champ in rv.get(r, ()))


def blind_safety(champ: str) -> float:
    """0..1. High = hard to counter → safe to reveal early / blind-pick.
    Low = easily countered → save for a late counter-pick slot. Combines the
    worst incoming counter + lane matchup, plus a small flex bonus (a champ
    that can go multiple roles is safer to show)."""
    if _eng is None or not champ:
        return 0.5
    if _incoming_counter_cache is None:
        _build_incoming()
    c = (_incoming_counter_cache or {}).get(champ, 0.0)
    l = (_incoming_lane_cache or {}).get(champ, 0.0)
    c_norm = min(c / 0.5, 1.0)              # COUNTERS strengths cap ~0.5
    l_norm = min(max(l, 0.0) / 8.0, 1.0)    # LANE_MATCHUPS span ~±8
    safety = 1.0 - (0.62 * c_norm + 0.38 * l_norm)
    if champ_role_count(champ) >= 2:
        safety += 0.06
    return round(max(0.0, min(1.0, safety)), 3)


def flex_score(champ: str, open_roles: Sequence[str]) -> int:
    """How many of the *currently open* roles this champ can fill. >=2 ⇒
    picking it conceals which role/player it is for."""
    if _eng is None or not champ:
        return 0
    rv = getattr(_eng, "ROLE_VALID", {})
    return sum(1 for r in open_roles if champ in rv.get(r, ()))


def counter_value(
    champ: str,
    enemy_picks: Sequence[str],
    enemy_role_champ: Optional[str] = None,
) -> Tuple[float, str]:
    """0..1 + reason. How well `champ` counters what the enemy has revealed:
    the direct same-lane matchup (if the opposing laner is known) weighted
    heavily, plus team-wide counter coverage vs all revealed enemies."""
    if _eng is None or not champ or not enemy_picks:
        return 0.0, ""
    counters = getattr(_eng, "COUNTERS", {})
    lanes = getattr(_eng, "LANE_MATCHUPS", {})
    best_t, best_v, team = "", 0.0, 0.0
    for e in enemy_picks:
        if not e:
            continue
        v = counters.get((champ, e), 0.0)
        team += v
        if v > best_v:
            best_v, best_t = v, e
    team_norm = min(team / 0.6, 1.0)
    if enemy_role_champ:
        d_c = counters.get((champ, enemy_role_champ), 0.0)
        d_l = max(0.0, lanes.get((champ, enemy_role_champ), 0.0)) / 8.0
        direct = min(1.0, d_c / 0.5 * 0.7 + d_l * 0.6)
        if d_c > best_v:
            best_v, best_t = d_c, enemy_role_champ
        score = max(direct, 0.35 * team_norm + 0.65 * direct)
    else:
        score = team_norm
    reason = f"counters {best_t}" if (best_t and best_v >= 0.2) else ""
    return round(min(1.0, score), 3), reason


def cohesion_text(picks: Sequence[str]) -> List[str]:
    """Plain-language draft gaps for a (partial) pick set. Only fires at >=3
    champs so early picks aren't nagged."""
    out: List[str] = []
    champs = [c for c in picks if c]
    if _eng is None or len(champs) < 3 or not hasattr(_eng, "_team_vector"):
        return out
    tv = _eng._team_vector(champs)
    sub = getattr(_eng, "SUBCLASSES", {})
    if tv.get("frontline", 0) < 1:
        out.append("No frontline - squishy, easily dove")
    if tv.get("engage", 0) < 1:
        out.append("No engage - struggles to force fights")
    hyper = sum(1 for c in champs if c in sub.get("hypercarry", ()))
    if hyper >= 1 and tv.get("peel", 0) < 1:
        out.append("Carry with no peel - gets bursted")
    if hyper >= 2:
        out.append("Two hypercarries - greedy, weak early")
    ap = ad = 0.0
    for c in champs:
        a, d = _eng.champ_damage_split(c)
        ap += a
        ad += d
    r = ap / ((ap + ad) or 1.0)
    if len(champs) >= 4 and (r >= 0.85 or r <= 0.15):
        out.append(f"Damage all {'AP' if r >= 0.85 else 'AD'} - "
                   f"enemy itemizes one stat")
    return out


def side_best_comfort(
    players: Sequence[Dict[str, Any]],
    roles: Sequence[str],
    inhouse_champs: Dict[str, List[Dict]],
    primary_roles: Dict[str, str],
    scout_champs: Optional[Dict[str, List[Dict]]] = None,
) -> Dict[str, float]:
    """champ -> best comfort across the given players (each at their role).
    Feeds `contested`."""
    out: Dict[str, float] = {}
    for p, role in zip(players, roles):
        for ch, sc in _candidates_for_player(
            p, role, inhouse_champs, primary_roles, set(), k=12,
            scout_champs=scout_champs,
        ):
            if sc > out.get(ch, 0.0):
                out[ch] = sc
    return out


def contested(champ: str, blue_map: Dict[str, float],
              red_map: Dict[str, float]) -> float:
    """0..1. High = a player on *each* side is comfortable on it, so it gets
    first-picked or banned. min() of the two sides' best comfort."""
    return round(min(blue_map.get(champ, 0.0), red_map.get(champ, 0.0)), 3)


# Enemy-weakness axis → plain actionable advice (U4).
_WEAKNESS_ADVICE = {
    "burst_them":     "Enemy backline is squishy - assassins/burst delete them",
    "kite_them":      "Enemy lacks mobility - kite / hypercarry comps thrive",
    "tank_bust_them": "Enemy stacks frontline - bring %HP / true damage",
    "poke_them":      "Enemy has no hard engage - poke & siege them",
    "lockdown_carry": "Enemy has a hypercarry - draft lockdown CC for it",
    "pop_engage":     "Enemy has hard engage - get disengage / peel",
}


def weakness_advice(vec: Dict[str, float], thresh: float = 0.5,
                    limit: int = 3) -> List[str]:
    """Turn an enemy_weakness_vector into ranked plain-language exploits."""
    if not vec:
        return []
    out: List[str] = []
    for k, v in sorted(vec.items(), key=lambda kv: -kv[1]):
        if v >= thresh and k in _WEAKNESS_ADVICE:
            out.append(_WEAKNESS_ADVICE[k])
        if len(out) >= limit:
            break
    return out


# ============================================================================
# E3 — target-archetype steering context
# ============================================================================

def target_archetype(
    state: "DraftBoardState",
    side: str,
    inhouse_champs: Dict[str, List[Dict]],
    primary_roles: Dict[str, str],
    forced_arch: Optional[str] = None,
    scout_champs: Optional[Dict[str, List[Dict]]] = None,
) -> Dict[str, Any]:
    """Best archetype this side's *players* support (via recommend_comps),
    plus the per-axis deficit vs locked picks so picks can be steered toward a
    coherent win condition. If `forced_arch` is given, that archetype is used
    directly (the user's draft-board pick), skipping the auto-detection — the
    deficit is still computed against locked picks so steering adapts as the
    draft progresses (incl. across bans which reduce the candidate pool used
    downstream)."""
    if _eng is None:
        return {}
    arches = getattr(_eng, "ARCHETYPES", {}) or {}

    # User-forced archetype: skip recommend_comps, build the deficit directly.
    if forced_arch and forced_arch in arches:
        arch_data = arches[forced_arch] or {}
        target = arch_data.get("target", {}) or {}
        cur = _eng._team_vector(state.locked_picks(side)) \
            if hasattr(_eng, "_team_vector") else {}
        deficit = {ax: max(0.0, target.get(ax, 0.0) - cur.get(ax, 0.0))
                   for ax in target}
        return {
            "archetype":     forced_arch,
            "label":         arch_data.get("label", forced_arch),
            "win_condition": arch_data.get("win_condition", ""),
            "spike":         arch_data.get("spike", ""),
            "viability":     "USER PICK",
            "deficit":       deficit,
            "forced":        True,
        }

    # Auto: engine picks the best archetype for these players.
    if not hasattr(_eng, "recommend_comps"):
        return {}
    try:
        try:
            comps = _eng.recommend_comps(
                state.engine_players(side),
                inhouse_champs=inhouse_champs,
                primary_roles=primary_roles,
                enemy_picks=state.locked_picks(_other(side)),
                n_results=1,
                scout_champs=scout_champs or {},
            )
        except TypeError:
            comps = _eng.recommend_comps(
                state.engine_players(side),
                inhouse_champs=inhouse_champs,
                primary_roles=primary_roles,
                enemy_picks=state.locked_picks(_other(side)),
                n_results=1,
            )
    except Exception:
        return {}
    if not comps:
        return {}
    top = comps[0]
    arch = top.get("archetype", "")
    target = (arches.get(arch, {}) or {}).get("target", {}) or {}
    cur = _eng._team_vector(state.locked_picks(side)) \
        if hasattr(_eng, "_team_vector") else {}
    deficit = {ax: max(0.0, target.get(ax, 0.0) - cur.get(ax, 0.0))
               for ax in target}
    return {
        "archetype":     arch,
        "label":         top.get("label", arch),
        "win_condition": top.get("win_condition", ""),
        "spike":         top.get("spike", ""),
        "viability":     top.get("viability", ""),
        "deficit":       deficit,
        "forced":        False,
    }


def _steer_bonus(champ: str, deficit: Dict[str, float]) -> float:
    """0..~1: how much `champ` fills the archetype axes still missing."""
    if _eng is None or not deficit or not hasattr(_eng, "_champ_vector"):
        return 0.0
    cv = _eng._champ_vector(champ)
    raw = sum(deficit.get(ax, 0.0) * cv.get(ax, 0.0) for ax in deficit)
    denom = sum(deficit.values()) or 1.0
    return min(1.0, raw / denom)


# ============================================================================
# E4 — phase-split ban recommender
# ============================================================================

def recommend_bans_split(
    state: "DraftBoardState",
    action: DraftAction,
    inhouse_champs: Dict[str, List[Dict]],
    primary_roles: Dict[str, str],
    n: int = 5,
    scout_champs: Optional[Dict[str, List[Dict]]] = None,
) -> List[Dict[str, Any]]:
    """
    Phase-aware ban suggestions.

    Phase 1 (no/early picks): strip the enemy's highest-value comfort picks,
      weighted by role importance (Top>Mid>ADC>Sup>JGL) and a flex multiplier
      (a champ the enemy can flex is worth more to remove).

    Phase 2 (after pick phase 1): protect our *committed* comp — prioritise
      champions that counter what we have already locked, blended with the
      enemy's remaining comfort threat.
    """
    enemy_side = _other(action.side)
    used = state.used_champs()

    # Engine baseline: Bayesian-shrunk, role-filtered, coverage-discounted
    # comfort threat for every champ on the enemy roster.
    threat: Dict[str, Dict[str, Any]] = {}
    if _eng is not None and hasattr(_eng, "recommend_bans"):
        try:
            try:
                _, detail = _eng.recommend_bans(
                    state.engine_players(enemy_side),
                    inhouse_champs=inhouse_champs,
                    own_picks=state.locked_picks(action.side),
                    primary_roles=primary_roles,
                    n_bans=40,
                    scout_champs=scout_champs or {},
                )
            except TypeError:
                _, detail = _eng.recommend_bans(
                    state.engine_players(enemy_side),
                    inhouse_champs=inhouse_champs,
                    own_picks=state.locked_picks(action.side),
                    primary_roles=primary_roles,
                    n_bans=40,
                )
            for d in detail:
                ch = d.get("champion")
                if ch and ch not in used:
                    threat[ch] = d
        except Exception:
            pass

    out: List[Dict[str, Any]] = []

    if action.phase == 1:
        for ch, d in threat.items():
            t = float(d.get("threat", 0.0) or 0.0)
            pl = d.get("player", "")
            role = _role_of_player(state, enemy_side, pl)
            rw = ROLE_BAN_WEIGHT.get(role, 1.0)
            flex = champ_role_count(ch) >= 2
            score = t * rw * (1.15 if flex else 1.0)
            why = d.get("phase_reason", "") or f"{pl or 'enemy'} comfort"
            if flex:
                why += " - flex"
            out.append({"champion": ch, "score": round(score, 3),
                        "tag": "BAN-P1", "why": why,
                        "player": pl, "role": role})
        out.sort(key=lambda s: -s["score"])
        return out[:n]

    # Phase 2 — protect our committed picks. Map each of our locked champs to
    # the role (and thus role-importance) it occupies, so banning a counter to
    # our Top is weighted above a counter to our Jungle.
    side_picks = state.picks[action.side]              # {role: champ}
    champ_role = {c: r for r, c in side_picks.items()}
    counter_us: Dict[str, float] = {}
    best_reason_strength: Dict[str, float] = {}
    reason: Dict[str, str] = {}
    role_w: Dict[str, float] = {}
    rv = getattr(_eng, "ROLE_VALID", {}) if _eng else {}
    for p in state.locked_picks(action.side):
        prw = ROLE_BAN_WEIGHT.get(champ_role.get(p, ""), 1.0)
        for atk, strg in _counters_of(p):
            if atk in used:
                continue
            counter_us[atk] = counter_us.get(atk, 0.0) + strg
            role_w[atk] = max(role_w.get(atk, 1.0), prw)
            if strg >= 0.2 and strg > best_reason_strength.get(atk, 0.0):
                best_reason_strength[atk] = strg
                reason[atk] = f"counters your {p}"

    for ch in set(counter_us) | set(threat):
        if ch in used:
            continue
        cu = min(counter_us.get(ch, 0.0) / 0.7, 1.0)
        th = min(float(threat.get(ch, {}).get("threat", 0.0) or 0.0), 1.0)
        # Worth a ban only if it's a real pickable champ or it counters us.
        if cu <= 0.0 and not any(ch in rv.get(r, ()) for r in ROLES):
            continue
        score = (0.62 * cu + 0.38 * th) * role_w.get(ch, 1.0)
        why = (reason.get(ch)
               or (threat.get(ch, {}) or {}).get("phase_reason", "")
               or "enemy threat to your comp")
        out.append({"champion": ch, "score": round(score, 3),
                    "tag": "BAN-P2", "why": why})
    out.sort(key=lambda s: -s["score"])
    return out[:n]


# ============================================================================
# Per-action recommender (E1 state + E3 tagged picks + E4 phase-split bans)
# ============================================================================

def recommend_action(
    state: DraftBoardState,
    inhouse_champs: Optional[Dict[str, List[Dict]]] = None,
    primary_roles: Optional[Dict[str, str]] = None,
    n: int = 5,
    forced_arch: Optional[str] = None,
    scout_champs: Optional[Dict[str, List[Dict]]] = None,
) -> Dict[str, Any]:
    """
    Recommend the current action.

    Returns a dict the UI renders directly:
      {
        "done": bool,                       # draft complete
        "action": DraftAction | None,
        "our_turn": bool,
        "kind": "ban" | "pick",
        "suggestions": [
            {"champion","score","tag","why",
             "role"?,"player"?}             # role/player only for picks
        ],
        "enemy_weakness": {axis: 0..1},     # context, from engine
        "notes": [str, ...],
      }
    """
    inhouse_champs = inhouse_champs or {}
    primary_roles = primary_roles or {}
    scout_champs = scout_champs or {}

    a = state.current_action()
    if a is None:
        return {"done": True, "action": None, "our_turn": False,
                "kind": None, "suggestions": [], "enemy_weakness": {},
                "notes": ["Draft complete."]}

    used = state.used_champs()
    notes: List[str] = []

    # Enemy-weakness context: what the *opponent of the acting side* has
    # revealed so far. (E4 will turn this into explicit ban/pick advice.)
    enemy_side = _other(a.side)
    enemy_locked = state.locked_picks(enemy_side)
    enemy_weak: Dict[str, float] = {}
    if _eng is not None and hasattr(_eng, "enemy_weakness_vector"):
        try:
            enemy_weak = _eng.enemy_weakness_vector(enemy_locked)
        except Exception:
            enemy_weak = {}

    suggestions: List[Dict[str, Any]] = []
    target_comp: Dict[str, Any] = {}
    cohesion: List[str] = cohesion_text(state.locked_picks(state.our_side))

    if a.kind == "ban":
        try:
            suggestions = recommend_bans_split(
                state, a, inhouse_champs, primary_roles, n=n,
                scout_champs=scout_champs)
        except Exception as e:  # pragma: no cover
            notes.append(f"ban engine fallback: {e}")
            suggestions = []
        if a.phase == 1:
            notes.append("Ban phase 1 - strip enemy comfort / flex threats")
        else:
            notes.append("Ban phase 2 - deny counters to your locked comp")
        if not suggestions:
            notes.append("No ban data - engine unavailable / empty rosters.")

    else:  # pick — E3: comfort + blind-safety + counter + flex + steering
        open_r = state.open_roles(a.side)
        tcomp = target_archetype(state, a.side, inhouse_champs, primary_roles,
                                  forced_arch=forced_arch,
                                  scout_champs=scout_champs)
        deficit = tcomp.get("deficit", {}) if tcomp else {}
        # Strict contested: a champ is only "contested" when a player on EACH
        # side has actually played it in customs (≥3 games) — not ranked
        # mastery or priors. min() of the two sides' real customs comfort.
        def _cust_pool(side):
            m: Dict[str, float] = {}
            if _eng is None or not hasattr(_eng, "customs_champs"):
                return m
            for p in state.players.get(side, []):
                for c, v in _eng.customs_champs(p, inhouse_champs).items():
                    if v > m.get(c, 0.0):
                        m[c] = v
            return m
        blue_cust = _cust_pool("BLUE")
        red_cust = _cust_pool("RED")

        def contested_strict(ch):
            return round(min(blue_cust.get(ch, 0.0),
                             red_cust.get(ch, 0.0)), 3)

        lanes = getattr(_eng, "LANE_MATCHUPS", {}) if _eng else {}
        enemy_by_role = state.picks[enemy_side]
        enemy_info = len(enemy_locked)
        late = a.label in ("R3", "B5", "R5")

        pool: List[Dict[str, Any]] = []
        for role in open_r:
            player = state.player_for_role(a.side, role)
            if not player:
                continue
            pname = player.get("name", "player")
            opp_champ = enemy_by_role.get(role)   # same-lane enemy, if known
            for ch, sc in _candidates_for_player(
                player, role, inhouse_champs, primary_roles, used, k=n + 2,
                scout_champs=scout_champs,
            ):
                bs = blind_safety(ch)
                fr = flex_score(ch, open_r)
                cv, cv_why = counter_value(ch, enemy_locked, opp_champ)
                con = contested_strict(ch)
                steer = _steer_bonus(ch, deficit)
                cmf = float(sc)
                # Direct same-lane matchup (±8 → -1..+1; >0 = we win lane).
                lane_known = bool(opp_champ)
                lane_n = 0.0
                if lane_known:
                    lr = lanes.get((ch, opp_champ), 0.0)
                    lane_n = max(-1.0, min(1.0, lr / 8.0))

                # --- context-aware tag ---
                if lane_known:
                    # Our lane opponent is locked → counter-pick this slot.
                    # Never call a pick "blind-safe" when the lane is known.
                    if cv >= 0.40 or lane_n >= 0.25:
                        tag = "COUNTER"
                        why = (cv_why or f"counters {opp_champ}").capitalize()
                    elif lane_n <= -0.30:
                        tag, why = "COMFORT", f"{pname}'s best into {opp_champ} (hard lane)"
                    else:
                        tag, why = "COMFORT", f"{pname} {role} vs {opp_champ}"
                elif enemy_info == 0:
                    if con >= 0.40:
                        tag, why = "POWER", "Contested - both teams play it"
                    elif bs >= 0.62:
                        tag, why = "SAFE", f"Blind-safe - hard to counter ({int(bs*100)})"
                    elif fr >= 2:
                        tag, why = "FLEX", f"Flex {fr} roles - hides your draft"
                    else:
                        tag, why = "COMFORT", f"{pname} {role} comfort"
                else:
                    if cv >= 0.45:
                        tag, why = "COUNTER", (cv_why or "counters their pick").capitalize()
                    elif con >= 0.45:
                        tag, why = "POWER", "Contested - lock before they grab it"
                    elif fr >= 2 and not late:
                        tag, why = "FLEX", f"Flex {fr} roles - hides your {role}"
                    elif bs >= 0.60 and not late:
                        tag, why = "SAFE", "Blind-safe - hard to counter"
                    else:
                        tag, why = "COMFORT", f"{pname} {role} comfort"

                # --- ranking blend ---
                if lane_known:
                    # Counter-pick slot: comfort still matters but the matchup
                    # dominates, and picking into a losing lane is punished.
                    score = (0.34 * cmf + 0.40 * cv
                             + 0.16 * max(0.0, lane_n) + 0.06 * steer
                             + (0.04 if fr >= 2 else 0.0))
                    score -= 0.24 * max(0.0, -lane_n)
                elif enemy_info == 0:
                    score = (0.50 * cmf + 0.22 * bs + 0.18 * con
                             + 0.08 * steer + (0.04 if fr >= 2 else 0.0))
                else:
                    score = (0.44 * cmf + 0.34 * cv + 0.10 * con
                             + 0.06 * bs + 0.06 * steer)

                factors = {
                    "comfort":    round(max(0.0, min(1.0, cmf)), 3),
                    "counter":    round(cv, 3),
                    "lane":       round((lane_n + 1.0) / 2.0, 3),
                    "blind_safe": round(bs, 3),
                    "flex":       round(min(1.0, fr / 3.0), 3),
                    "contested":  round(con, 3),
                    "steer":      round(max(0.0, min(1.0, steer)), 3),
                    "final":      round(max(0.0, min(1.0, score)), 3),
                }

                pool.append({
                    "champion": ch,
                    "score": round(score, 3),
                    "comfort": round(cmf, 3),
                    "tag": tag,
                    "why": f"{why}  ({pname} {role})",
                    "role": role,
                    "player": pname,
                    "factors": factors,
                })

        best: Dict[str, Dict[str, Any]] = {}
        for s in pool:
            cur = best.get(s["champion"])
            if cur is None or s["score"] > cur["score"]:
                best[s["champion"]] = s
        suggestions = sorted(best.values(), key=lambda s: -s["score"])[:n]
        if tcomp:
            target_comp = tcomp
            wc = tcomp.get("win_condition", "")
            notes.append(f"Build toward {tcomp.get('label','')}"
                         + (f" - {wc}" if wc else ""))
        if not suggestions:
            notes.append("No pick data - engine unavailable / no open roles.")

    if a.side == state.our_side:
        notes.insert(0, f"YOUR {a.kind.upper()} - {a.label}")
    else:
        notes.insert(0, f"Opponent {a.kind} - {a.label} (plan ahead)")

    return {
        "done": False,
        "action": a,
        "our_turn": a.side == state.our_side,
        "kind": a.kind,
        "suggestions": suggestions,
        "target_comp": target_comp,        # E3: archetype we're building toward
        "cohesion": cohesion,              # E2: plain-language gaps in OUR comp
        "enemy_weakness": enemy_weak,      # raw axis vector
        "exploit": weakness_advice(enemy_weak),   # U4: readable exploits
        "notes": notes,
    }


# ============================================================================
# Self-test (run directly:  python the_rift/data/draft_board.py)
# ============================================================================

def _selftest() -> None:
    print("DRAFT_SEQUENCE:")
    for x in DRAFT_SEQUENCE:
        print(f"  [{x.idx:2d}] {x.side:<4} {x.kind:<4} P{x.phase} {x.label}")

    rv = getattr(_eng, "ROLE_VALID", {}) if _eng else {}

    def team(prefix: str, off: int) -> List[Dict[str, Any]]:
        """5 players, each with a role-appropriate 3-champ pool (offset so the
        two sides differ but overlap → exercises contested/counter paths)."""
        out = []
        for i, role in enumerate(ROLES):
            champs = sorted(rv.get(role, ()))
            if champs:
                s = (off + i * 3) % len(champs)
                tc = [champs[(s + j) % len(champs)] for j in range(3)]
            else:
                tc = []
            out.append({"name": f"{prefix}{i+1}", "tier": "Gold",
                        "final_score": 55.0, "score": 55.0, "wr": 53.0,
                        "winrate": 53.0, "games": 40, "kda": 2.6,
                        "form": "MIXED", "top_champs": tc, "role": role})
        return out

    def _step(state: DraftBoardState, rec: Dict[str, Any]) -> bool:
        """Apply rec's top suggestion; fall back to any unused legal champ so
        the walk still progresses when dummy data yields no suggestions."""
        a = rec["action"]
        sug = rec["suggestions"]
        if sug:
            return state.apply(sug[0]["champion"], role=sug[0].get("role"))
        if a.kind == "pick":
            role = state.open_roles(a.side)[0]
            pool = sorted(set(rv.get(role, {"Ahri"})) - state.used_champs())
            return state.apply(pool[0], role=role)
        pool = sorted({"Zed", "Yasuo", "Akali", "Kassadin", "Lux", "Leona",
                       "Thresh", "Ashe", "Jinx", "Lee Sin", "Ahri", "Sett",
                       "Ornn", "Maokai", "Viego"} - state.used_champs())
        return state.apply(pool[0])

    st = DraftBoardState(team("B", 0), team("R", 11), our_side="BLUE")
    steps = 0
    while not st.is_complete():
        rec = recommend_action(st, {}, {}, n=5)
        a = rec["action"]
        assert a is not None
        ok = _step(st, rec)
        assert ok, f"apply failed at action {a.idx} ({a.label})"
        steps += 1
        assert steps <= 20

    assert st.is_complete()
    for side in SIDES:
        assert len(st.picks[side]) == 5, (side, st.picks[side])
        assert len(st.bans[side]) == 5, (side, st.bans[side])
    allc = [c for side in SIDES for c in st.bans[side]] + \
           [c for side in SIDES for c in st.picks[side].values()]
    assert len(allc) == len(set(allc)), "duplicate champion in completed draft"

    # Undo sanity: rewind 3, ensure pointer + state revert.
    p0 = st.pointer
    for _ in range(3):
        st.undo()
    assert st.pointer == p0 - 3

    print("\nFinal board:")
    print(st.summary())

    # --- E2 metric ranges ---
    for c in ("Yasuo", "Malphite", "Kassadin", "Sett", "Zed"):
        assert 0.0 <= blind_safety(c) <= 1.0, c
    assert champ_role_count("Sett") >= 1
    assert flex_score("Sett", ("TOP", "MID")) >= 0
    cv, _why = counter_value("Malzahar", ["Yasuo", "Zed"], "Yasuo")
    assert 0.0 <= cv <= 1.0
    coh = cohesion_text(["Vayne", "Jinx", "Karthus", "Lux"])
    assert isinstance(coh, list)
    print(f"\nE2 OK - blind_safety(Yasuo)={blind_safety('Yasuo')} "
          f"blind_safety(Malphite)={blind_safety('Malphite')} "
          f"counter_value(Malz-vs-Yas)={cv} cohesion_sample={coh}")

    # --- E3 tagged picks: fresh draft, advance through ban phase 1 then
    #     B1 (no enemy info) and a later pick (enemy info on board). ---
    st2 = DraftBoardState(team("B", 0), team("R", 11), our_side="BLUE")
    for _ in range(6):                       # clear ban phase 1
        _step(st2, recommend_action(st2, {}, {}, n=5))
    r_b1 = recommend_action(st2, {}, {}, n=5)
    assert r_b1["kind"] == "pick" and r_b1["action"].label == "B1", \
        f"expected B1, got {r_b1['action'].label} ptr={st2.pointer}"
    tags_b1 = {s["tag"] for s in r_b1["suggestions"]}
    print(f"\nE3 B1 (no enemy info) tags={sorted(tags_b1)} "
          f"target={r_b1['target_comp'].get('label','-')}")
    for s in r_b1["suggestions"][:3]:
        print(f"   {s['tag']:<8} {s['champion']:<12} {s['why']}")
    _step(st2, r_b1)                          # lock B1
    for _ in range(2):                        # R1, R2 → blue gets enemy info
        _step(st2, recommend_action(st2, {}, {}, n=5))
    r_b2 = recommend_action(st2, {}, {}, n=5)
    assert r_b2["kind"] == "pick"

    def _ascii(s: str) -> str:               # engine strings may carry ±/—
        return str(s).encode("ascii", "replace").decode()

    print(f"\nE3 {r_b2['action'].label} (enemy info on board) "
          f"target={_ascii(r_b2['target_comp'].get('label','-'))} "
          f"notes={[_ascii(x) for x in r_b2['notes'][:2]]}")
    for s in r_b2["suggestions"][:4]:
        print(f"   {s['tag']:<8} {s['champion']:<12} {s['why']}")
    assert all({"champion", "tag", "why", "score"}.issubset(s)
               for s in r_b2["suggestions"])

    # --- E4 phase-split bans ---
    st3 = DraftBoardState(team("B", 0), team("R", 11), our_side="BLUE")
    rb1 = recommend_action(st3, {}, {}, n=5)        # action 0: Blue Ban 1 (P1)
    assert rb1["kind"] == "ban" and rb1["action"].phase == 1
    assert all(s["tag"] == "BAN-P1" for s in rb1["suggestions"])
    print(f"\nE4 Ban P1 ({rb1['action'].label}) "
          f"notes={[_ascii(x) for x in rb1['notes'][:2]]}")
    for s in rb1["suggestions"][:4]:
        print(f"   {s['tag']:<7} {s['champion']:<12} {_ascii(s['why'])}")
    while not st3.is_complete() and st3.current_action().idx < 12:
        _step(st3, recommend_action(st3, {}, {}, n=5))
    rb2 = recommend_action(st3, {}, {}, n=5)        # action 12: Red Ban 4 (P2)
    assert rb2["kind"] == "ban" and rb2["action"].phase == 2
    assert all(s["tag"] == "BAN-P2" for s in rb2["suggestions"])
    print(f"\nE4 Ban P2 ({rb2['action'].label}) "
          f"notes={[_ascii(x) for x in rb2['notes'][:2]]}")
    for s in rb2["suggestions"][:4]:
        print(f"   {s['tag']:<7} {s['champion']:<12} {_ascii(s['why'])}")

    # --- U4 weakness_advice + U5 locked_at ---
    adv = weakness_advice({"burst_them": 0.9, "kite_them": 0.6,
                           "poke_them": 0.2})
    assert adv and adv[0].startswith("Enemy backline is squishy"), adv
    assert weakness_advice({}) == []
    st4 = DraftBoardState(team("B", 0), team("R", 11), our_side="BLUE")
    r0 = recommend_action(st4, {}, {}, n=3)
    assert "exploit" in r0
    first = (r0["suggestions"] or [{"champion": "Zed"}])[0]["champion"]
    st4.apply(first)
    assert st4.locked_at(0) == first, (st4.locked_at(0), first)
    assert st4.locked_at(5) is None
    st4.undo()
    assert st4.locked_at(0) is None
    print(f"\nU4/U5 OK - weakness_advice={adv[:2]} "
          f"locked_at exact, exploit field present")

    # --- L2 mirror (live LCU sync) ---
    st5 = DraftBoardState(team("B", 0), team("R", 11), our_side="BLUE")
    st5.mirror(
        picks={"BLUE": {"TOP": "Aatrox"}, "RED": {"TOP": "Sett"}},
        bans={"BLUE": ["Zed"], "RED": ["Pyke", "Lulu"]},
        completed=7, our_side="RED")
    assert st5.our_side == "RED"
    assert st5.pointer == 7
    assert st5.picks["BLUE"]["TOP"] == "Aatrox"
    assert st5.bans["RED"] == ["Pyke", "Lulu"]
    assert "Aatrox" in st5.used_champs() and "Zed" in st5.used_champs()
    rmir = recommend_action(st5, {}, {}, n=3)
    assert rmir["action"] is not None and not rmir["done"]
    assert st5.locked_at(0) is not None       # history rebuilt for timeline
    print(f"L2 OK - mirror sets side/pointer/picks/bans, recommend_action "
          f"advises {rmir['action'].label}, timeline history rebuilt")

    print(f"\nOK - walked {steps} actions, 5+5 picks/bans per side, no "
          f"duplicates, undo works; E2/E3/E4 + U4/U5 helpers verified.")


if __name__ == "__main__":
    _selftest()
