# Engine Fix Plan — Synthesis & Prioritised Roadmap

**Source reports**
- [`DRAFT_BASELINE_REPORT.md`](DRAFT_BASELINE_REPORT.md) — expert human vs engine across 5 worked drafts + 10 systematic gaps.
- [`ENGINE_AUDIT_REPORT.md`](ENGINE_AUDIT_REPORT.md) — engine-code pathology pass with file:line citations across 10 issues + 4 score distribution tables.

**Date:** 2026-05-25

The two reports were run independently against the same `engine_audit_run1.json` and converge on the same handful of pathologies. This document merges them into a single prioritised fix plan you can sign off on before any engine code is touched.

---

## 0 · Critical preflight — deploy current master to Fly first

The audit was run against the **deployed Fly server**, which is **on a pre-v3.0.5 revision** (Pathology #5). The audited `blind_safety = 0.98` for off-table champs (Pantheon, Maokai, Taliyah, Tristana, Ziggs) becomes `0.56` with the v3.0.5 fix that already lives in `server/engine_board.py:563-587` locally.

**Several findings may already be partly fixed in committed-but-undeployed code.** Specifically:
- Issue #5 (blind_safety bug) — already fixed in tree
- Issue #10 (SAFE tag over-firing) — partially fixed in tree
- Parts of Issue #1 (COUNTER coverage) — partial fixes may be in tree

**Recommended first action:** redeploy → re-run audit → diff. This sets a clean baseline before tuning weights against ground truth.

```
fly deploy                                            # autorised by feedback_fly_deploy_authorized
python scripts/draft_engine_audit.py --drafts 16 --out engine_audit_run2.json
# diff run1 vs run2; findings that disappear are already-fixed
```

I'll do this as step 1 unless you object. The fly-deploy memory says it's authorised, so this is a single command.

---

## 1 · The 13 findings, merged

Each finding is rated for impact (how often it fires across 16 drafts) and tuning risk (1 = small targeted change, 5 = touches scoring blend or table data).

| # | Finding | Source | Impact | Tuning risk | Location |
|---|---|---|---|---|---|
| **A** | **Role assignment ignores `/api/primary-roles`** | Baseline #2 | **10/16 drafts** | 3 | `server/engine_board.py:1285-1295` (open-role loop calls `_candidates_for_player` without role-fit prior) |
| **B** | **P1 ban triple-stacking** on one enemy player | Baseline #1 + Pathology #2 | **7/16 drafts have <4 distinct enemies banned** | 1 | `server/engine_board.py:1113-1128` |
| **C** | **P2 bans repeat-counter the same locked pick** | Baseline #5 + Pathology #3 | **14/20 P2 ban pairs** | 2 | `server/engine_board.py:1130-1170` |
| **D** | **COUNTER tag is dead** — 1 of 160 picks fired it | Pathology #1 | **0 of 47 R3/B5/R5 picks** | 4 | `server/engine_board.py:543-544, 1310-1320` + `engine_core.py:293-412` COUNTERS table |
| **E** | **B5/R5 silent failure** — no suggestion at last pick | Pathology #4 + #8 | **8/16 drafts (50%)** | 2 | `engine_core.py / draft_engine.py:1152-1161` priors fallback |
| **F** | **Tier/rank not in threat weight** — Turkey under-banned | Baseline #9 | **~all drafts where Turkey on enemy** | 1 | `server/engine_board.py:1119-1124` ban scoring |
| **G** | **Sample-size noise** — 3-game 100% WR drives ban score | Baseline #4 | **~6 drafts** (Mel, Rumble, Olaf 100% drives) | 2 | `engine_core.py` `shrink_wr` already exists; not applied everywhere |
| **H** | **`must_bans` field underused** | Baseline #8 | Ivern-Devin missed in most drafts | 1 | `server/engine_board.py:1080-1110` threat-building |
| **I** | **`form` (HOT/COLD/MIXED) ignored on bans** | Baseline #10 | All drafts to small degree | 1 | `server/engine_board.py:1119-1124` |
| **J** | **Lane-known branch worse than enemy-info when cv=0** | Pathology #6 | **11/16 R3 picks** drop to "comfort vs X" no-data scoring | 3 | `server/engine_board.py:1352-1360` |
| **K** | **Archetype oscillates every pick** | Pathology #7 | 14/16 drafts switch arch ≥3× | 2 | `server/engine_board.py:734-811` no hysteresis |
| **L** | **FLEX tag over-triggered** | Baseline #6 | Many drafts (e.g. Tahm Kench-SUP flagged as flex) | 1 | `server/engine_board.py:563-587` `+0.06` bonus |
| **M** | **No comp-construction check** (AD/AP balance, engage missing) | Baseline #7 | Picks 3-5 of every draft | 4 | new: needs a `comp_checklist` helper in pick scoring |

Plus **two structural items** that don't change recommendations but make every future fix safer:
- **Pathology #5** — redeploy Fly (preflight above).
- **Pathology #9** — single-source the engine: tables are duplicated across `server/engine_*.py` and `the_rift/data/draft_*.py`. Every weight change today has to be made twice or the proxy drifts.

---

## 2 · Recommended fix order

Sequenced so each change is independently verifiable against a re-audit and structurally cheap before expensive.

### Wave 1 — preflight + free wins (no scoring math changed)

1. **Deploy current master to Fly** (preflight §0).
2. **Re-run audit** → `engine_audit_run2.json`. Confirm which findings disappear.
3. **Add `/api/engine/version`** returning git SHA — the audit script logs it per run. Cheap (5 lines). Stops the "is this deploy fresh" question forever.
4. **Single-source the engine tables** (Pathology #9). Two options:
   - **Light**: delete the in-tree duplicate implementations in `the_rift/data/draft_engine.py` and `the_rift/data/draft_board.py`, keep only the proxy stubs that POST to `/api/engine/*`.
   - **Heavy**: export `COUNTERS`, `SUBCLASSES`, `SYNERGIES`, `LANE_MATCHUPS`, `ARCHETYPES`, `ROLE_VALID`, `CHAMP_PRIORS` to `tables.json`, load from both layers.
   - Recommend Light — the client doesn't compute, it proxies. Saves ~3000 LOC.

### Wave 2 — single-line scoring tweaks (low tuning risk, high impact)

These are all 1-3 line changes you can sanity-check against a re-audit. Order them in PR-sized batches:

5. **B – ban spread** — `server/engine_board.py:1119-1124`: add per-player decay `* 1.0 / (1 + 0.5 * already_banned_count[player])`. Forces top-6 P1 bans to spread across ≥3-4 enemies.
6. **F – tier-weighted threat** — multiply threat score by `tier_score / 50.0` (cap 0.6-2.0). Turkey at 85.5 → ×1.71; D-tier 35 → ×0.70.
7. **H – `must_bans` baseline** — pre-load per-enemy `must_ban` champions with floor score `2.0` so they beat any customs-derived ban.
8. **I – form multiplier on bans** — HOT × 1.15, COLD × 0.85, MIXED × 1.0.
9. **L – FLEX gating** — only award +0.06 flex bonus when *team has ≥2 open undecided role slots* AND *player has real history in 2+ roles* (≥3 games in second-best role from customs).
10. **C – P2 ban memory** — track per-pick protection budget; after a `counters your X` ban locks, scale `counter_us[atk]` for that `X` by 0.3 in the next P2 ban call.

### Wave 3 — table coverage (medium tuning risk)

11. **D – populate `COUNTERS` reciprocally** — 97 champs have no entry as a victim. Required additions: every meta JGL (Kha'Zix, Hecarim, Nocturne, Lillia, Sejuani, Ekko), every ADC (Caitlyn, Jhin, Miss Fortune, Tristana, Aphelios, Kai'Sa), every meta tank SUP (Leona, Nautilus, Braum, Maokai). 2-3 hard counters per champ in the 0.55-0.75 range.
12. **D thresholds** — drop `COUNTER_PICK_THRESHOLD` 0.70 → 0.55, `COUNTER` tag cutoff 0.40 → 0.35 (both in `engine_board.py:543-544, 1314`).
13. **E + Pathology #8 – expand priors fallback** — `_player_candidates` priors-fallback fills *all* `ROLE_VALID[role]` champs at 0.10 comfort instead of capping at 6 alphabetical. Plus pre-fetch `k=30` in `_candidates_for_player`. Also expand `CHAMP_PRIORS` with one meta pick per role (currently 8 champs total).
14. **G – Bayesian WR prior** — `shrink_wr` already exists; apply it in every place that reads raw WR. A 3-game 100% WR → ~62% posterior with α=β=5 prior. Drop ban scores driven by tiny samples.

### Wave 4 — structural & higher-risk

15. **A – role-fit prior in candidate generation** — when scoring a `(player, role)` pair, multiply comfort by `role_fit_factor`:
    - `role == primary_role` → 1.00
    - `role in scout_role_distribution top-2` → 0.80
    - otherwise → 0.35
    This is the most impactful single change. It needs careful testing because it changes role-to-player matching across the board.
16. **J – lane-known fallback** — at `engine_board.py:1352-1360`, when `cv < 0.05 and abs(lane_n) < 0.05`, fall back to the enemy-info blend `(0.44 × cmf + 0.34 × cv + …)`. Stops the lane-known branch from being *worse* than no-info.
17. **K – archetype hysteresis** — `target_archetype` accepts previous archetype as context; require new top to beat old by ≥0.05 combined before switching.

### Wave 5 — net-new logic (high effort, high payoff)

18. **M – comp-construction checklist** — add a `comp_score(picks)` helper that scores a 5-champ comp on:
    - Engage: ≥1 hard-engage tank or hook? (Malphite/Leona/Naut/Maokai/Thresh/Blitz/Pyke). +0.10.
    - Peel: ≥1 peel? (Lulu/Janna/Braum/Tahm/Trundle). +0.10.
    - AD/AP balance: clamp to 30-70%. Below 20% AP or above 80% AD → −0.15.
    - Waveclear: ≥1 waveclear source. +0.05.
    - Late scaling / finisher: ≥1 hyper-carry OR strong finisher (Pyke/Vex/Pantheon for finish). +0.05.
    Apply as a tiebreaker on pick scoring once 3+ picks are locked.

19. **WEAKNESS surface at R3/B5/R5** when no real counter exists — surface `enemy_weakness_vector` (already computed at line 1219-1225) as `burst_them`/`tank_bust_them` guidance tag. Gives the user actionable context at the last counter-pick instead of a `COMFORT 0.05` shrug.

20. **`notes` warnings when a role generates 0 candidates** — UI silently dropping a role is worse UX than a visible "⚠ Chris MID has no champion pool — fill manually".

---

## 3 · What the engine does well — preserve list

To be fair, the engine gets several things right and these should not regress:

- **Must-ban detection on large-sample champs** (Logan Jinx, Ben Volibear nailed every time).
- **P1 ban ordering by raw threat magnitude** (sort is correct; only spread is wrong).
- **Counter-pick search at R3/R4/B5** *when role assignment and counter table align* — Riley/Kha'Zix counter to Pantheon in draft 1 is exactly what a human plays.
- **FLEX tagging in concept** — the *idea* of recognizing 2-role champions is correct, just over-applied.
- **Score normalisation for picks** — pick scores live on 0-0.65; useful for the UI confidence meter.

---

## 4 · Open questions for you before I start

Three judgment calls before I touch engine code. None blocking — they just change priorities:

**Q1 — single-source the engine first or last?**
The two-copy drift (#9) means every weight change today has to be made twice. Light single-sourcing (delete in-tree duplicates) saves the next 20 fixes from needing two edits. But it's a one-time ~3000-line deletion. Do it before Wave 2, or trust the diff and do it after?

**Q2 — role-fit prior strength.**
Wave 4 fix A proposes 1.0 / 0.8 / 0.35 multipliers for primary / scout-top-2 / off-role. The 0.35 is what stops the "Mahesh on SUP" cascade. Too aggressive and it locks players to one role even when their customs say they flex. Want me to start at 0.5 (gentler) and re-audit? Or 0.35 (stronger) and back off if needed?

**Q3 — comp-construction (M) — scope.**
Full comp checklist is real work (~500 LOC + a comp-classification table). The cheaper version is "AD/AP balance check + missing-engage warning" only. Start cheap and add facets later, or aim for full from day one?

---

## 5 · Estimated effort (rough)

| Wave | Effort | When to re-audit |
|---|---|---|
| 1 (preflight) | 30 min | after deploy |
| 2 (single-line tweaks 5-10) | 2-3 h, batched as one PR | after batch |
| 3 (table coverage 11-14) | 4-6 h (most of that is COUNTERS table research per champ) | after each of 11, 13, 14 |
| 4 (structural 15-17) | 3-4 h | after each |
| 5 (new logic 18-20) | 6-8 h | after 18 |

Total: ~15-20 hours of focused work split across 5 PR-shaped batches, each re-audited. Each batch is independently shippable — even Wave 2 alone fixes 5 of the 13 findings.

---

## 6 · Sources

- `DRAFT_BASELINE_REPORT.md` (this repo)
- `ENGINE_AUDIT_REPORT.md` (this repo)
- `engine_audit_run1.json` — 16 drafts × 20 actions, raw engine output
- 27 LoL competitive draft theory URLs cited in `DRAFT_BASELINE_REPORT.md` §Sources
