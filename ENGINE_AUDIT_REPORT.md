# Draft Engine Audit — Run 1

**Source**: `engine_audit_run1.json` (16 simulated drafts × 20 actions, posted to
`https://the-rift-draft-sync.fly.dev/api/engine/recommend_action`).

**Engine code reviewed**:
- `C:\Users\blhei\Desktop\all code\the_rift\data\draft_engine.py` (1448 LOC)
- `C:\Users\blhei\Desktop\all code\the_rift\data\draft_board.py` (1043 LOC)
- `C:\Users\blhei\Desktop\all code\server\engine_board.py` (1635 LOC — actual
  server impl; the `the_rift/` copy is now a thin client proxy)
- `C:\Users\blhei\Desktop\all code\server\engine_core.py` (1703 LOC — scoring tables)

**Cross-cutting context**: client and server have **two copies** of every engine
function (`blind_safety`, `counter_value`, `recommend_bans`, `recommend_bans_split`,
…). The recommend_action HTTP endpoint runs the *server* copy. Drift between the
two copies is now itself a pathology — see Issue #9.

---

## 1 · Executive Summary — top pathologies, ranked by severity

| # | Pathology | Severity | Lines of impact |
|---|---|---|---|
| 1 | **`COUNTER` tag is essentially dead — fires once in 160 picks** (0.6% rate, never at R3/B5/R5). The engine's "counter-pick" branch never wins the score blend. | CRITICAL | `server/engine_board.py:1311-1372` |
| 2 | **P1 bans fixate on 1–2 players** (3/16 drafts target only 2 of 5 enemies with all 6 P1 bans). No diminishing return / spread-the-pain bonus. | CRITICAL | `server/engine_board.py:1113-1128` |
| 3 | **P2 bans repeatedly counter the *same* locked pick** (14/20 sides with ≥2 P2 bans target one ally). Same `_counters_of(p)` table runs every ban with no de-prioritisation after the first. | HIGH | `server/engine_board.py:1130-1170` |
| 4 | **8 drafts (50%) terminate B5/R5 with "no suggestion — stopping"**. After bans + 4 picks the engine cannot generate a candidate for the last open role. The `_player_candidates` path drops to zero when customs+scout+top_champs are all exhausted of legal champs. | HIGH | `server/engine_core.py` `_player_candidates` (lines mirroring `draft_engine.py:1059-1175`) |
| 5 | **Deployed engine still applies the pre-v3.0.5 `blind_safety = 1.0` for off-table champs**. Audit log shows `(98)` blind-safety for Pantheon/Maokai/Taliyah/Tristana/Ziggs — locally those compute to 0.56 with the v3.0.5 fix. The Fly deploy is stale. | HIGH | `server/engine_board.py:570-587` vs deployed runtime |

Other notable issues (covered in §2): COMFORT-only drift at counter-pick slots (#6),
archetype oscillates every pick (#7), late-pick candidate generation only produces
options from a single open role (#8), client/server engine drift (#9), `flex` bonus
priced for an empty COUNTERS-as-victim table (#10).

---

## 2 · Per-pathology details

### Issue #1 — COUNTER tag is functionally dead

**Severity: CRITICAL**

#### Evidence

- Across 16 drafts × 10 picks = **160 pick actions**, `COUNTER` is applied **1 time**
  (draft 15 step 11 R3 — Naafiri on Remy MID, counters Akali, score 0.376).
- At the canonical counter-pick slots (`COUNTER_PICK_SLOTS = {11, 18, 19}` per
  `engine_board.py:543`), **0 / 47 picks** were tagged `COUNTER` (the one COUNTER
  was at step 11 in draft 15; the other 15 drafts at step 11 + all 32 picks at
  step 18 and step 19 were `COMFORT`).
- In every R3/B5/R5 case, the engine fell back to `COMFORT` with `why = "{player}
  {role} vs {enemy_in_same_lane}"`, with scores collapsing to 0.05–0.30.

Examples (R3, step 11):

| draft | applied | top alt scores | enemy in lane | issue |
|---|---|---|---|---|
| 1 | Kha'Zix COMFORT 0.171 | Rammus 0.119, Akali 0.094 | Pantheon (BLUE JGL) | Engine knows the lane (Riley JGL vs Pantheon) but no COUNTERS entry for "anti-Pantheon-JGL" exists |
| 11 | Nocturne COMFORT 0.232 | Ekko 0.222, Sylas 0.179 | Kha'Zix (BLUE JGL) | Kha'Zix has **zero** entries as a `COUNTERS` victim |
| 16 | Garen COMFORT 0.288 | Darius 0.277, Poppy 0.214 | (TOP lane unknown) | No enemy TOP locked yet → cv branch never engages |

#### Root cause

`server/engine_core.py` `COUNTERS` table has **201 entries** but **97 of the 167
ROLE_VALID champs (58%) appear nowhere as a victim** (`b` position). The
`_counters_of(victim)` reverse index returns an empty list for over half the
champion pool, so `counter_value(your_champ, [enemy], opp_champ)` evaluates to
0 the moment the enemy laner is one of those 97.

Combined with the threshold logic in `engine_board.py:1310-1320`:

```python
if lane_known:
    if cv >= 0.40 or lane_n >= 0.25:
        tag = "COUNTER"
    elif lane_n <= -0.30:
        tag, why = "COMFORT", f"{pname}'s best into {opp_champ} (hard lane)"
    else:
        tag, why = "COMFORT", f"{pname} {role} vs {opp_champ}"
```

The `cv ≥ 0.40` gate almost never triggers because:
1. Counter table is sparse on the *victim* side (Kha'Zix, Nocturne, Hecarim,
   Maokai, etc. — all popular JGLs — never appear as victims).
2. `counter_value` normalisation is `min(team / 1.4, 1.0)` *plus* the
   `direct = min(1.0, d_c / 0.9 * 0.7 + d_l * 0.6)` formula
   (`engine_board.py:631-636`). For a 0.45 counter entry, direct = 0.35;
   `cv = max(direct, 0.35 * team_norm + 0.65 * direct)`. Even with maximal team
   coverage that's about 0.46. The 0.40 tag-cutoff is reachable, but the
   `COUNTER_PICK_THRESHOLD = 0.70` for the *score blend override* almost never
   is.

#### Suggested fix

1. **Populate `COUNTERS` as a fully reciprocal table.** Every attacker pair
   `(A, X): v` should imply a victim record for `X`. Audit the 97 uncovered
   victims and add entries — at minimum the meta junglers (Kha'Zix, Hecarim,
   Nocturne, Lillia), every ADC (Caitlyn, Jhin, Miss Fortune, Tristana, Kai'Sa),
   and tank supports (Leona, Nautilus, Braum, Maokai-SUP). Many already exist as
   attackers in the table; their inverse can be ported.
2. **Drop `COUNTER` tag gate to `cv ≥ 0.35`** (`engine_board.py:1314`). The
   current 0.40 was tuned for the 0.10-0.50 legacy table; with the rescale to
   0.30-0.90, soft counters at 0.30-0.40 already land cv ≈ 0.30, so 0.35 means
   "any rescaled counter pair fires the tag".
3. **Drop `COUNTER_PICK_THRESHOLD` from 0.70 to 0.55** (`engine_board.py:544`).
   The current threshold means the override only fires for *hard* counters
   (0.70+ raw). At R3/B5/R5, *any* solid counter (0.45+) should bias scoring;
   otherwise the override is dead.
4. **Add a "no-counter-data" fallback** at counter-pick slots: if `cv < 0.20`
   for the entire candidate pool, surface a `WEAKNESS` tag based on
   `enemy_weakness_vector` (already computed at line 1219-1225). e.g.
   "burst_them" → suggest assassin candidates, "tank_bust_them" → suggest %hp
   carries. This gives the user actionable context at R5 instead of a
   `COMFORT 0.05` shrug.

---

### Issue #2 — P1 bans fixate on 1–2 enemy players

**Severity: CRITICAL**

#### Evidence

P1 ban target diversity per draft (player banned, count out of 6 P1 bans):

| draft | distinct players targeted | top player's share |
|---|---|---|
| 1 | **2** | 3/6 (Logan, Mahesh only) |
| 6 | **2** | 3/6 (Turkey, Logan only) |
| 11 | **2** | 3/6 (Logan, Mahesh only) |
| 5 | 3 | 3/6 |
| 8 | 3 | 3/6 |
| 13 | 3 | 3/6 |
| 2,3,4,9,12,14,15 | 5 | 2/6 |

Draft 1 ban-by-ban (BLUE side bans 1, 2, 3 hit Logan's pool):
- Ban 1: Jinx (Logan BOT, 68% WR / 48g, score 1.522)
- Ban 2: Ezreal (Logan BOT, 44% WR / 4.4 KDA, score 1.281)
- Ban 3: Kai'Sa (Logan BOT, 33% WR / 4.4 KDA, score 0.987)

Riley's Kha'Zix at 100% WR (score 0.792) was rank #4 across all three bans —
banning Logan's *third*-best ADC outranks denying a 100% WR jungler on a
different player.

#### Root cause

`recommend_bans_split` Phase 1 (`server/engine_board.py:1113-1128`):

```python
if action.phase == 1:
    for ch, d in threat.items():
        t = float(d.get("threat", 0.0) or 0.0)
        pl = d.get("player", "")
        role = _role_of_player(state, enemy_side, pl)
        rw = ROLE_BAN_WEIGHT.get(role, 1.0)
        flex = champ_role_count(ch) >= 2
        score = t * rw * (1.15 if flex else 1.0)
        ...
    out.sort(key=lambda s: -s["score"])
    return out[:n]
```

The score depends *only* on the absolute champion-level threat. There is no
**player-level cap** or **per-player decay**. A whale of a Bot laner with 4
strong champs simply occupies the top 4 ban slots.

Compounding factor: `recommend_bans` itself does not deduplicate on player
either — it returns top-N champions globally sorted, even though the BAN
INTENT is to **deny each enemy a path forward**.

#### Suggested fix

1. **Per-player diminishing-return penalty** in `recommend_bans_split` P1:

   ```python
   per_player_seen = {}
   for ch, d in threat.items():
       pl = d.get("player", "")
       decay = 1.0 / (1 + 0.50 * per_player_seen.get(pl, 0))
       per_player_seen[pl] = per_player_seen.get(pl, 0) + 1
       score = t * rw * (1.15 if flex else 1.0) * decay
   ```
   With decay 0.5, a 2nd ban on the same player gets ×0.67, 3rd gets ×0.50.
   This forces the top-6 ban list to spread across at least 3–4 enemies before
   doubling back.

2. **Surface a `pool_depth` gate**. If an enemy player has `pool_depth ==
   "DEEP"`, the player needs to eat *2* bans before decay kicks in; if
   `"SHALLOW"`, one ban exhausts their pool and decay should be steep.

3. Alternative (gentler): instead of a hard decay, **softcap the threat score
   per player** to `0.85 × max(other_players_threats)` — i.e., the top threat
   on any player can never exceed the best threat across all *other* players
   by more than 15%. This breaks ties early without changing the underlying
   formula.

---

### Issue #3 — P2 bans repeatedly counter the same locked pick

**Severity: HIGH**

#### Evidence

Across 16 drafts, 20 sides had ≥2 P2 bans with a `"counters your X"` reason.
**14 of those 20 sides (70%) banned counters to the *same* locked pick both
times.**

Draft 5 BLUE locked pick Malphite. Both BLUE P2 bans counter Malphite:
- step 12 (Red Ban 4 → wait, this is RED banning): Vayne — "counters your Malphite"
- step 14 (Red Ban 5): Kog'Maw — "counters your Malphite"

Draft 10 (both sides commit this):
- BLUE bans (steps 13, 15): Teemo + Quinn — both "counters your Darius"
- RED bans (steps 12, 14): both "counters your Ambessa"

Draft 15 RED: both bans (steps 12, 14) target Naafiri-counters; BLUE: both (13, 15) target Akali-counters.

#### Root cause

`server/engine_board.py:1130-1170`:

```python
# Phase 2 — protect our committed picks. Map each of our locked champs to
# the role (and thus role-importance) it occupies...
counter_us: Dict[str, float] = {}
...
for p in state.locked_picks(action.side):
    prw = ROLE_BAN_WEIGHT.get(champ_role.get(p, ""), 1.0)
    for atk, strg in _counters_of(p):
        ...
        counter_us[atk] = counter_us.get(atk, 0.0) + strg
        ...

for ch in set(counter_us) | set(threat):
    cu = min(counter_us.get(ch, 0.0) / 1.4, 1.0)
    th = min(float(threat.get(ch, {}).get("threat", 0.0) or 0.0), 1.0)
    score = (0.62 * cu + 0.38 * th) * role_w.get(ch, 1.0)
```

The score `0.62 × cu + 0.38 × th` is **memoryless across consecutive bans**.
The next P2 ban call computes the same `counter_us` map (we still have the
same locked picks; the only diff is one extra used champ which doesn't remove
any other counter). The *same* top-scoring counters re-appear in rank order,
so the same locked pick gets all the protective bans.

#### Suggested fix

1. **Track per-pick protection budget.** After each P2 ban locks, attribute
   the ban to its target (the `p` in `counters your {p}`). On the next P2
   ban, multiply that target's `counter_us[atk]` by ~0.3 — "this pick is
   already mostly protected, defend a different pick now."

2. **Spread by role**. After a `counters your TOP_pick` ban, scale subsequent
   `TOP_pick` counter-bans by 0.5; the engine should rotate through TOP →
   MID → JGL → BOT → SUP across the 4 P2 ban slots.

3. **Tie in `pick_impact_delta`**. If banning candidate A reduces enemy
   counter-coverage of *multiple* of our locked picks (not just one), it
   should outrank a candidate that protects only one. Currently the scoring
   sums `strg` per attacker but doesn't reward *breadth* of protection.

---

### Issue #4 — 8/16 drafts terminate with "no suggestion" at B5/R5

**Severity: HIGH** — failure mode is visible to the user as the engine going
silent at the most stressful pick.

#### Evidence

Drafts where the engine emitted **no candidates** for the final pick:
- Draft 2 step 19 (R5), 4 step 18 (B5), 5 step 18 (B5), 6 step 19 (R5),
  7 step 18 (B5), 9 step 19 (R5), 12 step 18 (B5), 14 step 19 (R5).

Notes recorded: `"No pick data - engine unavailable / no open roles."`

Draft 4 at step 18 — used champs are 18 (10 bans + 8 picks). BLUE has JGL
unfilled. Chris (BLUE JGL) presumably has zero customs JGL data + zero scout
JGL data, so `_player_candidates` falls through all four sources:

1. Inhouse customs: empty for JGL
2. Scout-sheet pool: empty
3. `top_champs`: also empty or all 8 already used
4. `CHAMP_PRIORS`: only 8 priors (Garen, Darius, Master Yi, Tryndamere, Annie,
   Ashe, Brand, Morgana). If any of those JGL-valid champs (only Master Yi)
   is already used, `_player_candidates` falls into the "add safe meta picks
   for the role" branch (line 1158-1161) which only adds up to 6 champs. With
   ~50 champs in `ROLE_VALID["JGL"]` and ~6 ban-restricted, **49 JGL champs
   should be available** — the candidate generator just stops at 6.

Actually looking more carefully at `draft_engine.py:1159-1161`:
```python
for cname in sorted(valid):
    if cname not in seen and len(seen) < 6:
        seen[cname] = 0.20
```

This adds the first 6 alphabetical JGL champs that aren't already in `seen`.
If Amumu/Ambessa/Bel'Veth/Briar/Diana/Ekko got banned/picked earlier, this
loop adds Elise/Evelynn/etc. — should always have champs available… unless
the *board* layer fails first.

Re-examining `server/engine_board.py:1285-1295` — the pick loop iterates open
roles and calls `_candidates_for_player`. For a player with `is_random` no
or zero data, the engine WILL return an empty list if exclusions wipe out
the first 6 alphabetical picks. The candidate generator gets `k = n + 2 = 8`
candidates *then* `exclude` removes used champs *after* — see
`server/engine_board.py:444-454`:

```python
cands = gen(p, ... , k + len(exclude), ...)
out = [(c, s) for (c, s) in cands if c and c not in exclude]
return out[:k]
```

This pre-fetches `k + len(exclude)` candidates, but the underlying
`_player_candidates` has its own caps. With 20+ used champs late in draft,
`8 + 20 = 28` requested. The priors-fallback branch only emits ≤14 entries
(8 priors + 6 alphabetical). After exclusion the list can genuinely be empty
for a no-data player at JGL late draft.

#### Root cause

`draft_engine.py:1152-1161` priors-fallback only generates up to **14**
candidates (`CHAMP_PRIORS` + 6 alphabetical valid champs). At B5/R5, ~10
champs may be banned + 8 picked across both sides, but more importantly the
*alphabetical* slice + priors set is small. For a JGL player with no data,
the first 6 JGL by alphabet are `Amumu, Ambessa, Bel'Veth, Briar, Diana,
Ekko` — if any are used, the candidate set is missing them, plus the
exclusion strips others, and after exclusion it can hit zero.

#### Suggested fix

1. **Expand the priors fallback** in `draft_engine.py:1152-1161` to fill
   *all* valid-role champs at a low constant comfort (e.g. 0.10) rather than
   capping at 6. The 0.10 score keeps them ranked below any real data, but
   ensures a candidate exists for the final pick.

2. **Pre-fetch a higher `k`** in `_candidates_for_player`:
   `gen(p, …, max(k + len(exclude), 30), …)` — always request 30 even if 8
   are needed, so deep-draft exclusions don't starve the pool.

3. **Add a `last-pick role fill` branch** in `recommend_action` when the
   pool is empty: pull from `ROLE_VALID[role] - used_champs` and surface
   them with `tag = "FALLBACK"`. Better to show *any* legal champ with a
   warning than fall silent at the most important pick.

---

### Issue #5 — Deployed engine has pre-v3.0.5 `blind_safety = 1.0` bug

**Severity: HIGH** — distorts every B1 / no-enemy-info pick.

#### Evidence

The audit log was generated against the deployed Fly server. Multiple champs
that have **no** entry as a victim in `COUNTERS` and **no** entry as a
defender in `LANE_MATCHUPS` are reported with `blind_safety = 0.98`:

| champ | audited blind_safety | local-code blind_safety (v3.0.5) |
|---|---|---|
| Pantheon | 0.98 | 0.56 |
| Maokai | 0.98 | 0.56 |
| Taliyah | 0.98 | 0.56 |
| Tristana | 0.98 | 0.56 |
| Ziggs | 0.98 | 0.56 |

The local code at `server/engine_board.py:563-587` and
`the_rift/data/draft_board.py:563-587` both have the v3.0.5 fix:

```python
if c <= 0.0 and l <= 0.0:
    safety = 0.5
```

The deployed runtime returns 1.0 (yielding 1.0 + 0.06 - clamp → 1.0; the
display rounds to 0.98 after the multi-role bonus). The deployed Fly server
is on an older revision than the in-tree code.

#### Root cause

Deployment drift. The Fly machine is serving an older `engine_board.py` /
`engine_core.py` revision. The audit therefore reflects *legacy* behaviour,
not the engine that currently lives in the repo.

#### Suggested fix

1. **Redeploy the server** (the project allows `fly deploy` autonomously
   per `feedback_fly_deploy_authorized`).
2. **Add a `/api/engine/version` endpoint** that returns the git SHA the
   server was built from. The audit script could record this once per run
   so future audits know whether they are testing committed code or a stale
   binary.
3. **Re-run the audit after redeploy** to confirm `(98)` becomes `(56)` and
   that the `bs` weight reduction (0.22 → 0.14 per the v3.0.5 comment at
   line 1362-1364) actually de-emphasises blind-safety for the off-table
   champs.

---

### Issue #6 — Late-pick branch picks COMFORT even when enemy lane is locked

**Severity: MEDIUM**

#### Evidence

Step 11 (R3) — RED's first counter-pick slot, ENEMY (BLUE) has exactly 3
picks locked. The same-lane enemy is locked in 11/16 drafts (R3 picks JGL/
MID/SUP/TOP; in those drafts the enemy at that role is locked).

In all 11 cases the tag was `COMFORT "{player} {role} vs {enemy}"`, never
`COUNTER`. Examples:
- Draft 1: Riley JGL vs Pantheon — Kha'Zix 0.171 (Pantheon not in COUNTERS as victim)
- Draft 2: Remy JGL vs Amumu — Hecarim 0.166 (Amumu not in COUNTERS as victim)
- Draft 11: Joaquin JGL vs Kha'Zix — Nocturne 0.232 (Kha'Zix not in COUNTERS as victim)

The engine *acknowledges* the lane matchup in `why` text but the underlying
score blend (`engine_board.py:1354-1360`):
```python
elif lane_known:
    score = (0.34 * cmf + 0.40 * cv
             + 0.16 * max(0.0, lane_n) + 0.06 * steer
             + (0.04 if fr_unmatched >= 2 else 0.0))
    score -= 0.24 * max(0.0, -lane_n)
```
relies on `cv` and `lane_n`. With `cv = 0` (no counter table data) and
`lane_n = 0` (no lane matchup data), the score becomes effectively
`0.34 × cmf` — which is just *de-rated comfort*. Lane-known scoring is
*worse* than enemy-info scoring (where weight 0.44 × cmf), because the
counter weight that displaced 10% of comfort weight is filling with 0.

#### Root cause

`counter_value` (`engine_board.py:603-645`) returns `(0.0, "")` for ~58% of
champs as victims (Issue #1's coverage gap), but the score blend at
`lane_known=True` *assumes* `cv` is informative. When the victim has no
table coverage, the formula effectively penalises the candidate by
reweighting comfort downward and adding zero from counter/lane.

#### Suggested fix

1. **Fall back to enemy-info blend when `cv < 0.05` and `|lane_n| < 0.05`**:
   detect "we know the lane but have zero data on it" and use the
   enemy-info-only blend `(0.44 × cmf + 0.34 × cv + …)`. Currently the
   lane-known branch is *always* worse for no-data matchups.

2. **Combine with the counter-table fill from Issue #1**. Once the
   `COUNTERS` table is properly populated, this issue partially resolves
   — but the structural fallback is still wanted as a safety net.

---

### Issue #7 — Archetype target oscillates every pick

**Severity: MEDIUM** — produces incoherent "steer" guidance.

#### Evidence

Per-draft archetype sequence (step → archetype reported in `target_comp`):

| draft | sequence |
|---|---|
| 1 | Pick → Split Push → Pick → Split Push → (ban gap) → Split Push → Pick → Split Push |
| 5 | Teamfight → Pick → Teamfight → Pick → (ban gap) → Pick → Teamfight |
| 8 | Pick → Teamfight → Pick → Teamfight → (ban gap) → Teamfight → Pick → Teamfight |
| 11 | Split Push → Teamfight → Split Push → Pick → (ban gap) → Pick → Split Push → Pick |

Every pick switches the engine's "target comp". In a 10-step pick sequence,
14/16 drafts switch archetype ≥3 times.

#### Root cause

`target_archetype` (`server/engine_board.py:734-811`) calls `recommend_comps`
fresh each invocation, returns `comps[0]` (top by `combined`). With no
memory of the previous step's archetype, near-ties (which are common given
the comfort-dominated scoring) flip between archetypes. Each pick locks one
new champ, which can flip the top archetype because beam-search scores all
seven and picks the highest.

#### Suggested fix

1. **Hysteresis on archetype re-selection**. The engine should pass the
   previously-displayed archetype as a context arg and require the new top
   archetype to beat it by ≥`0.05` `combined` before switching. Otherwise
   stay on the previous one.

2. **Bias toward forced_arch**: in `target_archetype`, if `forced_arch` was
   the user's explicit archetype pick from the ARCHETYPE screen, always
   present it as the target (compute deficit), never reassess. This is
   actually already supported but `recommend_action` doesn't always
   thread `forced_arch` through — confirm the live UI is sending it.

3. **Bonus**: surface `archetype_pivot_check` (already implemented at
   `engine_board.py:814-924`) results in `recommend_action`. The pivot
   logic is the *correct* place to recommend archetype changes; the
   silently-changing `target_comp` field is the wrong place.

---

### Issue #8 — Late-pick candidate generation only surfaces one open role

**Severity: MEDIUM**

#### Evidence

At B4 (step 17, 2 BLUE roles open) and B5 (step 18, 1 BLUE role open), the
audit shows **all 5-6 alternatives from a single player/role** in 9 drafts:

| draft | step | open roles for side | all alts on |
|---|---|---|---|
| 4 | 17 (B4) | should be 2 | Jase2 SUP only (5 alts) |
| 5 | 17 (B4) | should be 2 (TOP, JGL, MID open) | Jase TOP only (6 alts) |
| 6 | 9 (B2) | 3 open | Bobby MID only (6 alts) |
| 9 | 16 (R4) | 3 open | Devin TOP only (3 alts) |
| 12 | 10 (B3) | 2 open | Logan JGL only (6 alts) |

(B5 step 18 having all alts on one role is correct — only 1 role open. But
B2/B3/B4/R4 with 2-3 roles open is wrong.)

Draft 5 step 17 (BLUE has TOP, JGL, MID open):
- All 6 alts are Jase TOP (Illaoi 0.19, Kayle 0.153, Dr. Mundo 0.142, …)
- Zero alts for Miles JGL or Chris MID.

#### Root cause

`server/engine_board.py:1285-1295`:

```python
pool: List[Dict[str, Any]] = []
for role in open_r:
    player = state.player_for_role(a.side, role)
    if not player:
        continue
    ...
    for ch, sc in _candidates_for_player(
        player, role, inhouse_champs, primary_roles, used, k=n + 2,
        scout_champs=scout_champs,
    ):
```

The loop iterates every open role. If `_candidates_for_player` returns
empty for Miles JGL and Chris MID (no inhouse data + no scout data +
limited fallback), only Jase TOP's candidates fill the pool, and dedup +
sort-by-score keeps all 6 from one role.

This is the **same root cause as Issue #4** — the candidate generator
silently produces zero entries for low-data players. The user sees the UI
show "all your options are TOP" with no indication that the engine simply
*can't* recommend anything for the other open roles.

#### Suggested fix

Same as Issue #4 (expand priors fallback to cover the whole role pool with
low constant comfort), plus:

1. **Emit a note when a role generates 0 candidates**: append to `notes`
   like `"⚠ Chris MID has no champion pool — fill manually"`. The UI can
   then surface this as a warning rather than silently dropping the role.

2. **Force at least one candidate per open role**: even if comfort is 0.05,
   pulling a single random meta champ for the role (a tank/safe pick) is
   better UX than zero options.

---

### Issue #9 — Two-copy engine drift

**Severity: HIGH** (impacts every future engine fix; multi-fix tax)

#### Evidence

Every engine function exists twice:
- `the_rift/data/draft_engine.py` ↔ `server/engine_core.py`
- `the_rift/data/draft_board.py` ↔ `server/engine_board.py`

The client-side copies (`the_rift/data/*.py`) are now **proxy wrappers** that
POST to `/api/engine/*` endpoints — see lines 1252-1297 of
`the_rift/data/draft_engine.py`. But the tables (`SUBCLASSES`, `COUNTERS`,
`LANE_MATCHUPS`, `ARCHETYPES`, `ROLE_VALID`, `CHAMP_PRIORS`) and helper
functions (`shrink_wr`, `champion_comfort`, `_player_candidates`,
`blind_safety`, `counter_value`, `recommend_bans_split`, …) are **all
duplicated as full implementations** in both files.

The duplication is also visible in the doc comments — both files start with
`"""draft_board.py — Tournament-draft sequence model…"""`. Identical text;
*intended* to be in sync.

#### Suggested fix

1. **Single source of truth**: make `server/engine_core.py` and
   `server/engine_board.py` the *only* place these tables live. The
   `the_rift/data/*.py` modules should only contain the proxy wrappers
   plus a *minimal* set of helpers that the UI needs to compute locally
   (e.g. `parse_wr`, `parse_float`).

2. **CI smoke test**: a tiny script that diffs the duplicated functions
   and fails loudly when they drift. Even a `grep -c "^def " server/engine_*
   the_rift/data/draft_*.py` should match on every commit.

3. **Or**: ship the tables as `tables.json` checked into the repo, loaded
   by both layers at boot — eliminates Python-level duplication entirely.

---

### Issue #10 — `flex` bonus pricing assumes a populated counters-as-victim table

**Severity: LOW**

#### Evidence

`blind_safety` adds `+0.06` for `champ_role_count(champ) >= 2`. This pushes
champs with no table coverage from `0.50 → 0.56`. Champs with table coverage
get the same +0.06 *on top of* their threat-derived safety. The net effect
is that a 2-role champ with a real bad lane matchup (e.g. Aurora vs
Pantheon, `lane_n` strongly negative) still gets the flex sweetener.

Less critically: `SAFE` tag fires at `bs >= 0.62` (line 1325). With the
local (post-v3.0.5) code, an off-table champ has `bs = 0.56`, **just under
the threshold**, so SAFE never fires for off-table champs. With deployed
code (v3.0.4) it's 1.0 → SAFE always fires. The deploy mismatch in Issue #5
swings this both ways.

#### Suggested fix

1. After redeploy (Issue #5), re-tune `bs >= 0.62` threshold. The intent
   is "real signal of safety". With v3.0.5's 0.56 default for no-data
   champs, only champs with *measured* low threat (low ic / low il) should
   reach 0.62+. Drop to `bs >= 0.60` and the in-data champs that beat 0.60
   are the genuine blind-safe candidates.

2. Move the `+0.06` flex bonus *outside* the threshold check so the SAFE
   tag depends only on real threat data, not the table-coverage default.

---

## 3 · Engine scoring distribution stats (all 16 drafts)

### Applied-pick tag distribution (148 picks total)

| Tag | Count | % of picks |
|---|---|---|
| COMFORT | 86 | 58.1% |
| SAFE | 44 | 29.7% |
| FLEX | 16 | 10.8% |
| POWER | 1 | 0.7% |
| COUNTER | 1 | 0.7% |

(Ban actions yield BAN-P1 96 / BAN-P2 64; complete 1:1 with the 160 ban
actions across 16 drafts.)

### Score percentiles (alternatives, not just #1 — n shown per tag)

| Tag | n | min | p25 | p50 | p75 | max | mean |
|---|---|---|---|---|---|---|---|
| BAN-P1 | 550 | 0.144 | – | 0.774 | – | 1.739 | 0.801 |
| BAN-P2 | 379 | 0.049 | – | 0.244 | – | 0.664 | 0.212 |
| SAFE | 216 | 0.094 | – | 0.257 | – | 0.639 | 0.292 |
| COMFORT | 489 | 0.015 | – | 0.139 | – | 0.462 | 0.144 |
| FLEX | 76 | 0.134 | – | 0.264 | – | 0.592 | 0.275 |
| POWER | 2 | 0.295 | – | 0.296 | – | 0.298 | 0.296 |
| COUNTER | 1 | 0.376 | – | 0.376 | – | 0.376 | 0.376 |

### Applied-action score percentiles

| Action kind | n | min | p25 | p50 | p75 | max | mean |
|---|---|---|---|---|---|---|---|
| pick | 148 | 0.043 | 0.145 | 0.218 | 0.297 | 0.639 | 0.240 |
| ban | 160 | 0.052 | 0.332 | 0.770 | 1.275 | 1.739 | 0.809 |

**The ban-vs-pick scale mismatch is structural**: ban scores average
**3.4×** higher than pick scores. They live on completely different scales
(picks 0..0.65, bans 0..1.74) because `recommend_bans` applies
`rank_weight * role_factor * ssz * kda_factor` multiplicatively while
picks normalise everything to 0..1. The UI ranking the two side-by-side
will always over-weight ban suggestions.

### Score gap #1 vs #2 (alternative dispersion — flat or peaked?)

| kind / tag | n | abs gap (avg) | abs gap (med) | rel gap (avg) |
|---|---|---|---|---|
| ban BAN-P1 | 96 | 0.199 | 0.151 | 17.4% |
| ban BAN-P2 | 64 | 0.049 | 0.026 | 14.9% |
| pick COMFORT | 82 | 0.029 | 0.020 | 16.7% |
| pick COUNTER | 1 | 0.156 | 0.156 | 41.5% |
| pick FLEX | 16 | 0.058 | 0.038 | 16.4% |
| pick POWER | 1 | 0.060 | 0.060 | 20.1% |
| pick SAFE | 44 | 0.036 | 0.024 | 11.2% |

**SAFE picks have the tightest cluster** (11.2% rel-gap) — the top SAFE is
barely ahead of #2. **COUNTER** has the widest gap (41.5%) but only 1
sample. **BAN-P2 has near-zero median gap (0.026)** — the engine treats the
2nd and 1st P2 ban as basically tied (explains Issue #3 fixation).

### Player-side ban concentration (16 drafts, P1 phase)

| concentration | count |
|---|---|
| 2 distinct enemy players targeted | 3 (drafts 1, 6, 11) |
| 3 distinct | 4 |
| 4 distinct | 3 |
| 5 distinct | 6 |

In 7/16 drafts (44%), P1 ban diversity is below 4 — meaning at least 2 of
the 5 enemy players are *never* contested in the ban phase.

---

## 4 · Recommended weight/code changes (prioritised)

### High-impact (changes scoring weights)

| File / line | Current | Proposed | Issue |
|---|---|---|---|
| `server/engine_board.py:544` | `COUNTER_PICK_THRESHOLD = 0.70` | `0.55` | #1 |
| `server/engine_board.py:1314` | `if cv >= 0.40 or lane_n >= 0.25:` | `if cv >= 0.35 or lane_n >= 0.25:` | #1 |
| `server/engine_board.py:1325` | `bs >= 0.62` (SAFE tag) | `bs >= 0.60` after #5 deploy fix | #10 |
| `server/engine_board.py:1352-1360` | lane-known blend uses cv even when zero | Fall back to `enemy_info` blend when `cv < 0.05 and lane_n ≈ 0` | #6 |
| `server/engine_board.py:1119-1124` | `score = t * rw * (1.15 if flex else 1.0)` | Add per-player decay `* 1/(1+0.5*ban_count_for_player)` | #2 |
| `server/engine_board.py:1164` | `score = (0.62 * cu + 0.38 * th) * role_w[ch]` | After each P2 ban, scale `counter_us[atk]` by 0.3 for the already-protected pick | #3 |

### Coverage / table fixes

- **Populate `COUNTERS` reciprocally** (`server/engine_core.py:293-412`). 97 of
  167 champs (58%) have no entry as a victim. Required entries: every meta
  jungler (Kha'Zix, Hecarim, Nocturne, Lillia, Sejuani, Ekko), every ADC
  (Caitlyn, Jhin, Miss Fortune, Tristana, Aphelios), and the meta tank
  supports (Leona, Nautilus, Maokai, Braum). For each, encode the 2-3 hard
  counters in the 0.55–0.75 range.
- **Expand `CHAMP_PRIORS`** (`server/engine_core.py:771-774` and
  `the_rift/data/draft_engine.py:771-774`). Currently 8 champs. Add one
  meta pick per role so the no-data fallback always emits at least 5 valid
  options regardless of which role is being filled.
- **Expand priors fallback** (`server/engine_core.py` / `draft_engine.py:
  1152-1161`): fill *all* `ROLE_VALID[role]` champs at a low constant
  comfort (0.10) instead of capping at 6 alphabetical.

### Structural fixes

- **Redeploy Fly** (Issue #5) and add `/api/engine/version` returning git
  SHA; thread version into audit log.
- **Single-source the engine code** (Issue #9). Either delete the tables
  from `the_rift/data/*.py` or check them in as JSON loaded by both layers.
- **Hysteresis on `target_archetype`** (Issue #7): pass the previously
  selected archetype as a context arg; require new top to beat old by
  `≥0.05 combined` before switching.

### UI / engine surface

- **Emit a `WEAKNESS` candidate tag** at R3/B5/R5 when no real counter
  exists. Use `enemy_weakness_vector` (already computed) to surface
  "burst the squishy backline → assassin pool" suggestions.
- **Append `notes` warnings** when a player generates 0 candidates (Issue
  #8) — the UI silently dropping a role is worse than a visible warning.
- **Add `tag = "FALLBACK"`** for emergency last-pick fills so the user
  knows the engine ran out of real data (Issue #4).

### Open question for the user

The audit data was generated against the **deployed** server which is on a
pre-v3.0.5 revision. Several findings (especially Issue #5, Issue #10, and
parts of Issue #1) may already be partly fixed in the committed code. The
recommended first action is to:

1. Deploy the current `master` to Fly.
2. Re-run the audit (`python scripts/draft_engine_audit.py --drafts 16
   --out engine_audit_run2.json`).
3. Diff run1 → run2 and confirm which findings persist.

Then the table-coverage / weight changes above can be applied in priority
order against ground truth.
