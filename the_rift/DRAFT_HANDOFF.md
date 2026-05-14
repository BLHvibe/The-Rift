# Draft Assist — Handoff

**As of v2.1.0 (2026-05-13)**

This is the only handoff document worth keeping for the_rift. Everything else
(Scout / Inhouse / Feed / Commands / Settings / Tier List / Rankings) is in
working order — the rebuild docs that used to live here described work that has
since been implemented and were misleading more than helpful.

---

## What the draft assist is

A 5v5 League draft analysis tool. Drag-and-drop players into blue / red role
slots → click BEGIN ANALYSIS → bans, comps, lane matchups, win meter.

## File map

- [data/draft_engine.py](data/draft_engine.py) — **the shared pure-Python engine** (~1230 LOC). All champion-knowledge data tables and analysis algorithms live here. No DPG, no sheet I/O.
- [ui/draft.py](ui/draft.py) — UI + state machine. The three `_compute_*` functions are thin wrappers that delegate to `draft_engine`.
- [data/fetch_ranks_gsheets.py](data/fetch_ranks_gsheets.py) — backend subprocess. **No longer invoked during draft analysis** (see below); only used by other tabs.
- [data/reader.py](data/reader.py) — data layer (`live.scout`, `live.inhouse_champs`, `live.primary_roles`, `live.rankings`, Rank-History prediction API).

## Key architectural decisions

### Local engine is the sole source of truth for comps / bans
The Sheets subprocess pipeline is intentionally disabled. The call to
`_kick_off_bg_draft` in `_analyse_teams` is commented out. The local engine now
produces a richer analysis than the backend ever did, and the backend was
overwriting it 15–120s later with worse results that confused users.

The **Rank History win-% prediction** (`load_prediction_data` /
`_apply_prediction`) IS still active — it's a separate signal that adjusts only
the win meter and per-lane bar percentages, never the comp / ban detail. To
re-enable the comp / ban subprocess, uncomment the `_kick_off_bg_draft` call.

### "Random N" placeholders are intentional
The three `_RANDOM_PLAYERS` entries (`Random 1/2/3`) in `ui/draft.py` represent
ad-hoc players who join inhouse 5v5s but are NOT on the tier list and will NOT
be added to the roster. They are first-class draft pool entries even though
they have no scouting data. Don't fold them into `_is_real_player()` rejection.

### Analysis is chained in `_analyse_teams`
Order matters and feeds forward:
1. Blue comps computed first (no enemy context).
2. Red comps computed with blue's top-comp picks passed as `enemy_picks` — red gets counter-aware drafting.
3. Blue bans use blue's top-comp picks as `own_picks` (coverage-discount on countered threats).
4. Red bans, same with red's picks.
5. Matchups use both teams' top-comp picks (champion-level lane matchup table lookup).

### Engine API surface
Three public functions in `draft_engine.py`:
- `recommend_comps(players, inhouse_champs, primary_roles, enemy_picks, n_results, beam_width)` → list of archetype dicts with `picks`, `viability`, `win_condition`, `score_breakdown`.
- `recommend_bans(opposing_players, inhouse_champs, own_picks, primary_roles, n_bans)` → `(names, detail)` tuple.
- `compute_matchups(blue, red, primary_roles, blue_picks, red_picks)` → list of `(role, blue_name, red_name, blue_win_pct, note)`.

## Algorithm knobs (non-obvious values worth knowing)

- **Beam width:** 16 per archetype. Each player step keeps top-16 partial team states.
- **Candidates per player:** 6 (top-K champions considered per player in the beam expansion).
- **Bayesian prior:** Beta(α=4, β=4) — pulls WR toward 50% on small samples. See `shrink_wr()`.
- **Score weights** in `score_team()`: identity 0.28, comfort 0.32, synergy-normalised 0.15, damage-profile 0.08, counter 0.10, coherence 0.07.
- **Viability bands** (final total score): STRONG ≥ 0.62, VIABLE ≥ 0.48, WEAK ≥ 0.32, else NOT RECOMMENDED.
- **Form modifier:** HOT × 1.10, COLD × 0.90, MIXED / missing × 1.0.
- **Ban coverage discount:** up to −40% threat if your team strongly counters that champion.
- **Bans are role-filtered:** only champions in `ROLE_VALID[player_assigned_role]` are considered, regardless of their `inhouse_champs` role history. This stops "ban Yasuo for player slotted SUP" suggestions.

## Where to add data

All in `draft_engine.py`:
- `SUBCLASSES` — 18 binary tags (engage / aoe_damage / frontline / assassin_or_burst / cc / duelist / waveclear / long_range / disengage / hypercarry / peel / mobile / immobile / squishy / tank_buster / anti_carry / global_pressure / scaling / early_game).
- `DAMAGE_AP` / `DAMAGE_AD` / `DAMAGE_HYBRID` / `DAMAGE_TRUE` — damage-type sets.
- `SYNERGIES` (~70 pairs) and `ANTI_SYNERGIES` (~10 pairs) — champion pair bonuses / penalties.
- `COUNTERS` (~120 pairs) — `(your_champ, enemy_champ) → strength` for counter scoring.
- `LANE_MATCHUPS` (~120 pairs) — `(your_champ, enemy_champ) → blue_adv ±8` for lane phase.
- `ARCHETYPES` — 7 archetypes (Teamfight / Pick / Split Push / Poke-Siege / Protect the Carry / Dive / Scaling), each with `target` vector + `conflict_axes` + `win_condition` string + `spike` string.
- `CHAMP_PRIORS` — handful of fallback WR priors used only when a player has zero data.
- `ROLE_VALID` — per-role champion pools (TOP / JGL / MID / BOT / SUP).

**Adding champions / synergies / counters:** edit `draft_engine.py` only. `draft.py` reads everything through the engine functions.

## Backend engine awareness

`fetch_ranks_gsheets.py` got a light touch — it isn't on the user-facing critical
path anymore, but engine awareness was added so if it's ever re-enabled it
doesn't undo the improvements:
- Optional `from data import draft_engine as _eng` at top with try/except fallback.
- `score_team_synergy` adds engine pair-synergy bonus (±20 points).
- `compute_comp_suggestions` adds `_engine_counter_bonus()` + `win_condition` + `spike` fields to its output.
- `_apply_draft_results` in `draft.py` also augments any backend response with engine-derived `win_condition` / `score_breakdown` — defence in depth.

## UI surfacing (draft results page)

Strategy panels display from each comp dict:
- archetype label (top-left, gold)
- viability tag (top-right, colour-coded by STRONG / VIABLE / WEAK / NOT RECOMMENDED)
- champion picks line (` · ` separated)
- win-condition string with `→` prefix
- AP/AD ratio (right-aligned)
- 5 synergy dots (top-right, gold / dim)

Ban cards show: champion name, player + WR% + games subline, priority label
(HIGH / MEDIUM / LOW). The engine populates `phase_reason` ("Must ban — 72% WR
over 20 games", "Threat exists but X pick counters it", etc.) but it isn't
currently rendered on the card; available for tooltips later.

Font on the draft page: every body element uses Rajdhani SemiBold (was Regular
before v2.1.0). Section headers in `gold_lt`. Body text in `txt` with no
alpha-fade multipliers.

## Open / known limitations

- **No patch awareness.** Static champion data; no patch version tracking. Edits to `SUBCLASSES`, `LANE_MATCHUPS`, etc. require code change + rebuild.
- **No champion-vs-champion stats sheet read.** Counter / lane-matchup data is hand-curated, not derived from any per-match dataset.
- **Backend still has its own legacy `compute_comp_suggestions` logic.** The engine augments it but doesn't replace the algorithm. If you re-enable the subprocess, the local engine results will still be overwritten — only the augmented fields (`win_condition`, `spike`) and the small synergy bonus apply.
- **No way for users to edit synergy / counter weights without a rebuild.** If this becomes a need, `SYNERGIES` / `COUNTERS` could be loaded from a sheet tab on startup.
- **Comp results don't surface `phase_reason` or `score_breakdown` visually** beyond AP/AD ratio. The data is in the dicts; UI just doesn't render it.
