# The Rift — Draft Board: Complete Reference

> Comprehensive technical doc for the Draft Assist / Draft Board feature in The Rift.
> Covers every data source, every transformation, every algorithm, and every UI surface.
> If this doc disagrees with the code, **the code wins** — but please update this file.
>
> Last reviewed against code: 2026-05-19 · app version v2.8.x (master)

---

## 1. What the Draft Board is

The Draft Board is the interactive tournament-draft assistant inside The Rift desktop app.
A user lays out two five-player rosters (BLUE vs RED), then either:

- **Snapshot Analysis** — clicks BEGIN ANALYSIS and gets a one-shot report (bans, comp suggestions per archetype, lane matchups, win-probability meter), or
- **Tournament Board** — steps through the standard 20-action competitive pick/ban order (6 bans · 6 picks · 4 bans · 4 picks) with per-action recommendations live-updated after every lock.

The Board can be driven three ways:

1. **Manual entry** — user clicks champions in the pool grid.
2. **LCU live import** — `data/draft_lcu.py` polls the local League client during champ select and mirrors the in-game draft.
3. **Multiplayer sync** — `data/draft_sync.py` connects to the WebSocket server in `server/` so a captain on each side can co-author the draft remotely.

All three paths funnel into the same `DraftBoardState` and the same recommender — sources are interchangeable.

---

## 2. File map

| Layer | File | LOC | Purpose |
|---|---|---|---|
| Engine | `the_rift/data/draft_engine.py` | 1397 | Pure-Python champion knowledge + scoring. No I/O. The single source of truth for comps / bans / matchups. |
| Board state machine | `the_rift/data/draft_board.py` | 1191 | The 20-action tournament sequence, `DraftBoardState`, and the per-action recommender (`recommend_action`). Reuses the engine for all champion-level scoring. |
| Data layer | `the_rift/data/reader.py` | 2386 | Google Sheets I/O. Builds `live.rankings`, `live.scout`, `live.inhouse`, `live.inhouse_champs`, `live.primary_roles`, and the lazy `live.scout_sheets` cache. |
| Live import | `the_rift/data/draft_lcu.py` | 302 | League Client API polling adapter — parses champ-select JSON into the same player dicts the manual path uses. |
| Multiplayer | `the_rift/data/draft_sync.py` | 346 | WebSocket client for the multiplayer draft server in `server/`. |
| Top-level UI | `the_rift/ui/draft.py` | 4830 | Team-builder, assembly animation, analysis page, and the full interactive Board renderer. Owns `draft` (UI state) and drives `_board_recompute()`. |
| Right-rail UI | `the_rift/ui/board_rail.py` | 564 | Win-prob meter, breakdown widget, radar, damage profile widget — fed off the engine. |
| Sync UI bridge | `the_rift/ui/draft_sync_ui.py` | — | Hooks the multiplayer client into `ui/draft.py` without a circular import. |
| Scout panel | `the_rift/ui/scout.py` | — | Reads a single player's scouting sheet for the Scout tab; also seeds `live.scout_sheets` cache so the engine can use it. |

Outside the draft feature but relevant:

- `the_rift/data/fetch_ranks_gsheets.py` — legacy backend subprocess. **Not on the draft critical path anymore** (the `_kick_off_bg_draft` call in `_analyse_teams` is intentionally commented out). The local engine fully replaced it.
- `server/` — Python WebSocket server for the multiplayer sync path.

---

## 3. Data sources (Google Sheets)

All sheet I/O goes through `data/reader.py`, which authenticates via the service-account `credentials.json` and a sheet URL configured in `data/config.py`.

### 3.1 Sheets read at startup (`_read_sheets` in `reader.py`)

Populated into the `live` singleton (a `LiveData` instance):

| Sheet tab | Parsed by | `live.*` field | What the draft uses it for |
|---|---|---|---|
| `Player Rankings` (or similar) | `_read_rankings` | `live.rankings` | Per-player score / tier / KDA / form / **top 3 ranked champion names** (`top_champs`). The team-builder card pool and the player dicts passed into the engine. |
| `Scout Tab` | `_read_scout` | `live.scout` | Same row data as rankings + extra metadata used by the Scout panel list. |
| `In-House Stats` | `_read_inhouse` | `live.inhouse` | Per-player customs aggregates (games, WR, KDA, etc.). |
| `_GameLog` / per-match rows | `_read_inhouse_match_log` → `_read_inhouse` | `live.inhouse_champs` | **Per-player, per-champion customs history.** Each champion entry has `{champ, games, wins, wr, kda, results, recent_results, roles}` where `results` is the chronological 1=win/0=loss list **capped to the last 100 customs games** ([`reader.py:650`](the_rift/data/reader.py:650)). This is the strongest signal the engine has. |
| `_GameLog` (role aggregation) | derived | `live.primary_roles` | `{player_name: "TOP"/"JGL"/"MID"/"BOT"/"SUP"}` — each player's most-played customs role, used for the `role_match` bonus in comfort scoring. |
| `Players` sheet | `_read_players` | `live.players`, `live.summoner_map` | Display-name list and `RiotID → display name` map (used by the LCU live-import to translate summoners back to roster names). |
| `Rank History` | `load_prediction_data` → `_read_rank_history_latest` | (in-memory only) | Used by the legacy win-probability prediction path; still active alongside the engine's win-meter. |
| `_Activity` | `_read_activity` | `live.activity` | Activity feed (sidebar). Not used by the draft engine. |

### 3.2 Sheets read on-demand: per-player scouting reports

The most important late-loaded sheets for the draft board are the **per-player `Scout - {name}` worksheets**. Each contains a player's full ranked/draft history broken down by champion, role, recent matches, ban targets, and a power rating.

Parsed by `_parse_scouting_sheet` in `reader.py` into:

```python
{
  "player":           str,
  "subtitle":         str,
  "power_rating":     {position, score, rating, tier_score, rank_score},
  "overview_headers": [...], "overview_values": [...],
  "must_bans":        [{name, games, wr, kda, threat, ...}, ...],
  "ban_impact":       {text, wr, games},
  "champ_pool":       [{name, games, wins, losses, wr, kda, kills, deaths,
                        assists, cs_min, damage, gold}, ...],   # ranked + draft pool
  "roles":            [{role, games, pct, top_champs}, ...],
  "form_state":       "HOT"|"COLD"|"MIXED",
  "matches":          [{game, result, champion, role, kda_str, ...}, ...],
  "inhouse_champs":   [{name, games, wins, losses, wr, kda, damage}, ...],
  "scouted_at":       datetime|None,
}
```

These sheets are **fetched in two ways**:

1. **On-demand single fetch** (`load_scout_sheet(name, on_done, on_error)`) — fires when the user opens a player's panel in the Scout tab. Result lands in `scout.current_report` AND is mirrored into `live.scout_sheets[name]` via `cache_scout_sheet()` so the engine can read it later.

2. **Batched draft prefetch** (`prefetch_scout_sheets(names)`) — fires automatically the moment both teams are full in the Draft team-builder, and again at `_board_begin` / `start_assembly`. Pulls **every player's scout sheet in a single `values_batch_get` API call** (one round-trip, one quota unit) instead of 10 sequential reads. Worksheet titles are looked up once via `spreadsheet.worksheets()` so non-existent sheets are skipped without 404 round-trips. Results are cached in `live.scout_sheets`; the engine reads them through `live.scout_champs_for(name)` / `live.scout_champs_map(names)`.

#### 3.2.1 Why scout sheets matter

The startup `live.inhouse_champs` only covers **customs** games. A player's ranked + draft performance is *only* visible through their per-player scout sheet. Without prefetch, the engine sees:

- Customs champs (rich per-champ stats)
- 3 ranked champion **names** (from `top_champs` — no games/wr/kda)
- Generic priors as fallback

With prefetch, the engine additionally sees the full ranked + draft pool with games/wr/kda for every champion the player plays. This is what turns "Alice has 200 ranked Fiora games" from invisible into a real comfort signal and ban threat.

### 3.3 Quota / concurrency

Google Sheets API quotas (current at time of writing):

- 300 read requests per minute per project
- 60 read requests per minute per user

The batched prefetch keeps a 10-player draft to **1 read** instead of 10, which is the difference between fitting comfortably under the per-user limit and throttling out if a user opens two drafts in a minute. Multiple concurrent users in the same org now share project-quota budget instead of fighting over it.

---

## 4. From sheet to engine: data flow

```
                    Google Sheets
                         │
                         ▼
       ┌─────────── reader.py ───────────┐
       │                                  │
       │  _read_sheets (startup)          │
       │  → live.rankings                 │
       │  → live.scout                    │
       │  → live.inhouse                  │
       │  → live.inhouse_champs   ◄────── per-customs-game, last 100
       │  → live.primary_roles            │
       │                                  │
       │  prefetch_scout_sheets (draft)   │
       │  → live.scout_sheets[name]       │
       │    └ champ_pool (ranked+draft) ──┐
       │                                  ▼
       └──── live.scout_champs_map(names) → scout_champs dict
                          │
                          ▼
      ui/draft.py  _scout_champs_for_players()
      builds the per-call scout_champs map and passes it into:
                          │
       ┌─────────────────┼─────────────────┬─────────────────┐
       ▼                 ▼                 ▼                 ▼
   recommend_comps   recommend_bans   recommend_action   board_rail
   (snapshot)        (snapshot)       (interactive       (win meter)
                                       board)
                          │
                          ▼
                draft_engine.py
                _player_candidates → champion_comfort
                                       ├ shrunk WR (Bayesian Beta(α=4,β=4))
                                       ├ recency-weighted WR (half-life 18 games)
                                       ├ KDA / form / inhouse / role-match
                                       └ scout-pool augmentation (× 0.85)
                beam_search_comp → score_team → recommend_comps
                                                recommend_bans
                                                compute_matchups
```

---

## 5. Player dict shape

The "player dict" is the contract between the data layer and the engine. Every player passed to the engine has roughly:

```python
{
  "name":         str,                          # display name (matches sheet keys)
  "role":         "TOP"|"JGL"|"MID"|"BOT"|"SUP",
  "tier":         str,                          # "Diamond II", etc. (cosmetic only)
  "winrate":      float,                        # ranked WR % (0..100)
  "wr":           float|str,                    # alias
  "games":        float,                        # ranked sample size
  "kda":          float,                        # ranked KDA
  "form":         "HOT"|"COLD"|"MIXED",         # last-10-customs form indicator
  "final_score":  float,                        # composite player score (0..100)
  "score":        float,                        # alias
  "top_champs":   [str, str, str],              # top 3 ranked champion names
  "is_random":    bool,                         # placeholder slot (uses role pool with flat 0.35 comfort)
}
```

The engine treats unknown keys as missing and falls back to safe defaults (priors, neutral KDA = 1.5, neutral WR = 50%).

`inhouse_champs[player_name]` is a parallel structure:

```python
[
  {
    "champ":          str,
    "games":          int,
    "wins":           int,
    "losses":         int,
    "wr":             "67.5%",                  # string with % suffix; engine parses
    "kda":            float,
    "results":        [1,0,1,1,0,...],          # chronological, capped to last 100
    "recent_results": [1,0,1,...],              # last 20, for UI form indicator
    "roles":          {"TOP": 12, "JGL": 3},    # role breakdown
  },
  ...
]
```

And `scout_champs[player_name]` (from `live.scout_champs_for`):

```python
[
  {
    "champ":   str,
    "games":   int,
    "wins":    int, "losses": int,
    "wr":      "55.2%",
    "kda":     float,
    "kills":/"deaths":/"assists":/"damage":  # informational
    "results": None,                          # scout sheet has no per-game chronology
    "roles":   {},                            # pool is across-role
  },
  ...
]
```

---

## 6. Engine — algorithms in `draft_engine.py`

### 6.1 Champion comfort score

`champion_comfort(games, wr_pct, kda, role_match, form, inhouse, results)` → 0..1.

Combines:

1. **Bayesian-shrunk winrate** — `shrink_wr_from_pct(wr, games)` with Beta(α=4, β=4). Pulls toward 50% on small N so "1g/100%" can't beat "50g/70%".
2. **Recency-weighted winrate** (when `results` is provided) — `recency_weighted_wr(results, half_life=18)`. The most recent customs game weighs 1.0; weight halves every 18 games back. The two WRs are blended as `0.65 × recent + 0.35 × all-time`.
3. **Sample-size signal** — `log(1+games) / log(1+30)` clamped to 1.0.
4. **KDA modifier** — `max(0.6, min(1.4, kda / 2.5))`.
5. **Role match bonus** — × 1.20 when the player's primary role matches their assigned slot.
6. **Form modifier** — HOT × 1.10, COLD × 0.90, MIXED × 1.00.
7. **Inhouse weighting** — × 1.25 if the source is customs (heavier than ranked).

### 6.2 Candidate generation per player (`_player_candidates`)

For each player + role, build a `{champion: comfort}` dict using four progressively weaker sources:

1. **`inhouse_champs[name]`** (customs) — full per-champ stats + `results` for recency-weighting. Champs must be in `ROLE_VALID[role]`.
2. **`scout_champs[name]`** (scout sheet ranked + draft pool) — per-champ stats, no recency, weighted × 0.85 (`_SCOUT_CHAMPS_WEIGHT`). Only added if it beats whatever is already in the map (customs wins ties on the same champ).
3. **`top_champs`** (3 ranked champion names from the rankings sheet) — no per-champ stats, assumes `games ≈ ranked_games / 4`, weighted × 0.75.
4. **`CHAMP_PRIORS`** — global meta priors, only as a fallback when the player has **zero data**. Weighted × 0.50 plus a baseline neutral 0.20 for unknown role-pool champs to keep the candidate set non-empty.

`is_random=True` slots return the entire role pool with a flat 0.35 comfort.

### 6.3 Beam search team build (`beam_search_comp`)

For each of the 7 archetypes, find the best 5-champion assignment with constraints:

- **Beam width:** 16 (per archetype). Each player step keeps top-16 partial team states.
- **Candidates per player:** 6 (top-K per beam expansion).
- **State:** `(champs_so_far, comforts_so_far, used_set)`.
- **Partial score:** 50% mean comfort + 50% archetype-vector fit.
- **Final score** comes from `score_team`:

  | Weight | Component |
  |---|---|
  | 0.28 | Identity vector (sum of champion subclass tags weighted to the archetype target) |
  | 0.32 | Comfort (mean over the 5 picks) |
  | 0.15 | Synergy (`SYNERGIES` pair bonuses, normalised) |
  | 0.08 | Damage profile (penalises all-AP or all-AD) |
  | 0.10 | Counter (`COUNTERS` table vs `enemy_picks`) |
  | 0.07 | Coherence (subclass diversity / archetype conflict-axis penalty) |

- **Viability bands** (final total):

  | Band | Threshold | UI label |
  |---|---|---|
  | STRONG | ≥ 0.62 | green |
  | VIABLE | ≥ 0.48 | gold |
  | WEAK | ≥ 0.32 | amber |
  | NOT RECOMMENDED | < 0.32 | red |

### 6.4 Ban threat scoring (`recommend_bans`)

Per enemy player, for each champion in customs AND scout pool:

```
threat = shrunk_wr  ×  log(1+games)/log(11)·1.2 (capped 1.4)
                    ×  min(kda/2.5, 1.6)
                    ×  rank_weight (0.5..2.0 from final_score/50)
                    ×  role_factor (1.15 if primary role matches assigned)
                    ×  form_multiplier
                    ×  source_weight  (1.00 customs · 0.85 scout)
```

Then:

- **Coverage discount** — up to `-40%` if your team's locked picks strongly counter the champ.
- **Role-pool filter** — only champions valid for the enemy player's *assigned* role are considered (stops "ban Yasuo for player slotted SUP" suggestions).
- **Priority labels** — top 2 = HIGH, next 2 = MEDIUM, rest = LOW.

If neither customs nor scout-pool data exists for a player, fall back to their `top_champs` with a flat low threat = `0.20 × rank_weight`.

### 6.5 Lane matchups (`compute_matchups`)

Per role, look up `LANE_MATCHUPS[(blue_champ, red_champ)]` → ±8 blue-side win-pct delta. Combined with player KDA/form/customs WR-on-this-champ to produce a per-lane win bar.

### 6.6 Inline data tables

All in `draft_engine.py`:

- `SUBCLASSES` — 18 binary tags (engage / aoe_damage / frontline / assassin_or_burst / cc / duelist / waveclear / long_range / disengage / hypercarry / peel / mobile / immobile / squishy / tank_buster / anti_carry / global_pressure / scaling / early_game)
- `DAMAGE_AP` / `DAMAGE_AD` / `DAMAGE_HYBRID` / `DAMAGE_TRUE` — damage-type sets
- `SYNERGIES` (~70 pairs) and `ANTI_SYNERGIES` (~10 pairs) — champion pair bonuses/penalties
- `COUNTERS` (~120 pairs) — `(your_champ, enemy_champ) → strength` for counter scoring
- `LANE_MATCHUPS` (~120 pairs) — `(your_champ, enemy_champ) → blue_advantage ±8` for lane phase
- `ARCHETYPES` — 7 archetypes (Teamfight / Pick / Split Push / Poke-Siege / Protect the Carry / Dive / Scaling), each with `target` vector + `conflict_axes` + `win_condition` string + `spike` string
- `CHAMP_PRIORS` — fallback WR priors used only when a player has zero data
- `ROLE_VALID` — per-role champion pools (TOP / JGL / MID / BOT / SUP)

To add champions, synergies, counters, or matchups: **edit `draft_engine.py` only.** No other file needs touching — `draft.py` and `draft_board.py` read everything through the engine functions.

---

## 7. Board state machine — `draft_board.py`

### 7.1 The 20-action tournament sequence (`DRAFT_SEQUENCE`)

```
BAN 1   B  R  B  R  B  R              (6 bans, Blue starts)
PICK 1  B1 | R1 R2 | B2 B3 | R3       (6 picks, snake)
BAN 2         R  B  R  B              (4 bans, Red starts)
PICK 2  R4 | B4 B5 | R5                (4 picks, snake)
```

20 actions total, indexed 0..19. Each `DraftAction` carries `(idx, side, kind, phase, label)`.

### 7.2 `DraftBoardState`

The single mutable structure for one draft. Source-agnostic — manual UI, LCU adapter, and multiplayer sync all drive it through `apply(champ, role?)` / `undo()`.

Fields:

- `players: {"BLUE": [p0..p4], "RED": [p0..p4]}` — index == role index (TOP=0 … SUP=4).
- `picks: {"BLUE": {role: champ}, "RED": {role: champ}}`
- `bans: {"BLUE": [champ, ...], "RED": [...]}`
- `pointer: int` — current position in `DRAFT_SEQUENCE` (20 when complete).
- `our_side: "BLUE"|"RED"` — which side this app instance is drafting for. Pure cosmetic for recommendations; not enforced.
- `_history` — list of `_HistEntry` for undo.

### 7.3 Per-action recommender (`recommend_action`)

Inputs: `(state, inhouse_champs, primary_roles, n=5, forced_arch=None, scout_champs=None)`.

Returns:

```python
{
  "done":           bool,
  "action":         DraftAction|None,
  "our_turn":       bool,
  "kind":           "ban"|"pick"|None,
  "suggestions":    [{champion, score, tag, why, role?, player?}, ...],
  "target_comp":    {archetype, label, win_condition, spike, viability, deficit, forced},
  "enemy_weakness": {axis: 0..1},
  "cohesion":       [str, ...],   # plain-English warnings about own locked picks
  "notes":          [str, ...],
}
```

**Pick branch** uses six signals per candidate champion (`_candidates_for_player`):

| Signal | Source | What it measures |
|---|---|---|
| Comfort (`cmf`) | `_player_candidates` (customs + scout-pool + top_champs + priors) | Is this player good on this champ? |
| Blind safety (`bs`) | `blind_safety()` — `1 - worst incoming counter / lane` | Is this champ generally hard to counter? |
| Counter value (`cv`) | `counter_value(ch, enemy_locked, opp_champ)` — uses `COUNTERS` + `LANE_MATCHUPS` | Does it punish the enemy's locked picks (and the specific same-lane enemy)? |
| Flex (`fr`) | `flex_score(ch, open_roles)` | How many of our remaining open roles can it cover? |
| Contested (`con`) | `contested_strict(ch)` via `customs_champs` on both sides | Both sides have a player with ≥ 3 customs games on this champ |
| Steering (`steer`) | `_steer_bonus(ch, deficit)` vs `target_archetype.deficit` | Does it fill the archetype axes we still lack? |

A context-aware **tag** is then assigned:

| Tag | When | Why-string |
|---|---|---|
| POWER | enemy_info == 0 ∧ contested ≥ 0.40 | "Contested — both teams play it" |
| SAFE | enemy_info == 0 ∧ blind_safety ≥ 0.62 | "Blind-safe — hard to counter" |
| FLEX | enemy_info == 0 ∧ flex ≥ 2 | "Flex N roles — hides your draft" |
| COUNTER | lane known ∧ (cv ≥ 0.40 ∨ lane_n ≥ 0.25) | "Counters {enemy}" |
| COMFORT | otherwise | "{player} {role} comfort" |

**Ban branch** uses `recommend_bans_split`:

- Phase 1: take engine `recommend_bans` baseline → weight by `ROLE_BAN_WEIGHT` (Top > Mid > ADC > Sup > JGL) → boost flex champs × 1.15.
- Phase 2: also pull `_counters_of(our_locked_pick)` for every champ we've locked → blend `0.62 × counters_us + 0.38 × residual_threat` → weight by the role of the pick we're protecting.

---

## 8. UI surfaces (`ui/draft.py`)

### 8.1 Phases (`DraftPhase`)

| Phase | Trigger | What it shows |
|---|---|---|
| `IDLE` | App start | Mode-select landing — "Snapshot Analysis" vs "Tournament Draft" cards. |
| `TEAM_BUILD` | User clicks a mode | Drag-and-drop team builder. Player cards from `live.scout` snap into 5 role slots per side. **Both rosters full → batched scout-sheet prefetch fires.** |
| `ASSEMBLING` | BEGIN ANALYSIS (snapshot path) | Fly-in animation while `_analyse_teams` runs `_compute_bans` and `_compute_comps_detail`. |
| `ANALYSING` | After assemble | Radar-sweep animation. Loads Rank History prediction for win-meter calibration. |
| `RESULTS` | After analyse | Static report: bans, comps, lane matchups, win meter. |
| `BOARD` | BEGIN DRAFT (tournament path), or sync session join | Live interactive tournament-draft board (the main draft assist). |
| `DONE` | All 20 actions locked | Final summary. |

### 8.2 Snapshot analysis panels

The `RESULTS` page is laid out as three columns:

```
┌───────────────┬───────────────────────┬───────────────┐
│  BLUE BANS    │      Win meter        │   RED BANS    │
│  BLUE COMPS   │  Lane matchups (PVP)  │   RED COMPS   │
└───────────────┴───────────────────────┴───────────────┘
```

Per archetype comp card shows: archetype label (gold), viability tag, picks (`·`-separated), win-condition prefixed with →, AP/AD ratio, 5 synergy dots.

Per ban card shows: champion name, player + WR% + games subline, priority label (HIGH/MEDIUM/LOW). The engine populates `phase_reason` ("Must ban — 72% WR over 20 games") on the dict but it's currently surfaced only via tooltip-eligible data; no card-front rendering yet.

### 8.3 The interactive Board (`_draw_board`)

Layout A:

```
┌────────────────────────────────────────────────────────────────┐
│  Header strip: timeline (20 chips, current action highlighted) │
├──────────────────┬─────────────────────────┬───────────────────┤
│   BLUE COLUMN    │      CENTER POOL        │   RED COLUMN      │
│  - 5 role slots  │   - search-as-you-type  │  - 5 role slots   │
│  - picks/bans    │   - scrollable grid     │  - picks/bans     │
│  - next-pick     │   - top-call card       │  - next-pick      │
│    ribbon        │                         │    ribbon         │
└──────────────────┴─────────────────────────┴───────────────────┘
│                  Right analytics rail (board_rail.py)          │
│   win-prob meter · breakdown · radar · damage profile · etc.   │
└────────────────────────────────────────────────────────────────┘
```

Live updates flow: pick locked → `_board_apply` → `state.apply` → `_board_recompute` → `recommend_action` re-runs → `draft.board_rec` updated → next render reads it.

In synced mode (`draft.board_live = True`):

- The user's local `apply` is intercepted by `_sync_ui.route_apply` and sent to the server instead.
- Every frame, `sync_tick` mirrors the server's authoritative snapshot back into `draft.board`.
- `_lcu_poll_loop` (when board_live for LCU import) reads `data/draft_lcu.py` and folds the live champ-select into the board state.

### 8.4 Where each engine call site lives

| Call site | File / function | Engine entry point |
|---|---|---|
| Snapshot bans | `_compute_bans` | `_eng.recommend_bans` |
| Snapshot comps | `_compute_comps_detail` | `_eng.recommend_comps` |
| Snapshot matchups | `_compute_matchups` | `_eng.compute_matchups` |
| Board per-action | `_board_recompute` | `recommend_action` (`draft_board.py`) |
| Enemy target arch | `_enemy_target_comp` | `target_archetype` |
| Enemy next-pick ribbon | `_enemy_pick_preview` | `_candidates_for_player` |
| Per-slot pool-depth capsule | inline in `_draw_role_slots` | `_candidates_for_player` |
| Win-prob meter | `board_rail._refresh_engine` | `_eng.recommend_comps` (n=1 per side) |

Every one of those call sites now forwards `scout_champs` so the ranked+draft signal feeds into the same scoring everywhere.

---

## 9. Multiplayer sync (`data/draft_sync.py`, `server/`)

- Captain on each side connects to `wss://<server>/draft/<session>`.
- Server is authoritative — it holds the canonical `DraftBoardState` and broadcasts JSON snapshots after every action.
- Local UI is a renderer: `route_apply` short-circuits the local `state.apply` and sends `{"op": "apply", "champ": "...", "role": "..."}` instead. The local state catches up on the next snapshot.
- LCU live-import is **disabled** in synced sessions (only the side captain mutates).
- See `server/README.md`, `server/INTEGRATION.md`, `server/HOSTING.md` for the server side.

---

## 10. Prefetch & quota strategy

### 10.1 What gets fetched when

| Trigger | Function | API calls | When |
|---|---|---|---|
| App launch | `load_live_data` → `_read_sheets` | ~10 sheet reads | Background thread on startup. Populates `live.rankings`, `live.inhouse_champs`, etc. |
| User opens Scout tab → clicks a player | `load_scout_sheet(name)` | 2 (sheet read + Rank History) | On-demand per click. Result cached in `live.scout_sheets`. |
| Team-builder fills both rosters | `prefetch_scout_sheets(names)` | **1 batched read** (+ 1 worksheet-titles metadata) | Auto-fires the moment all 10 slots are filled. Pulls every player's scout sheet in one round-trip. Already-cached or in-flight players are skipped. |
| BEGIN ANALYSIS (snapshot) | `prefetch_scout_sheets` in `start_assembly` | 0 or 1 (skipped if already cached) | Belt-and-suspenders fallback. |
| BEGIN DRAFT (board) | `prefetch_scout_sheets` in `_board_begin` | 0 or 1 (skipped if already cached) | Belt-and-suspenders fallback. |

### 10.2 Sheets API quota math (current Google limits)

| Limit | Per-user / minute | Per-project / minute |
|---|---|---|
| Read requests | 60 | 300 |
| Write requests | 60 | 300 |

A 10-player draft now costs **1 read** (batched prefetch) plus ~10 reads for app startup. Five concurrent users running back-to-back drafts comfortably fit under 300/min — previously the per-user reads (10 × 5 = 50) plus startup (10 × 5 = 50) plus other tabs could push close to limits.

### 10.3 Cache lifetime

`live.scout_sheets` is **never auto-invalidated** — once a sheet is fetched for a session, the engine sees that snapshot until app restart. If a player's scouting report is regenerated mid-session via the Commands tab "Full Scout", the user must restart the app (or manually re-fetch via the Scout tab) for the engine to pick it up. This is a known limitation; the upside is predictable behavior during a draft.

---

## 11. Known limitations

- **No patch awareness.** All champion data (subclasses, counters, matchups, archetypes) is static and edited inline. Patch X.Y boosts are not modeled.
- **No champion-vs-champion stats sheet read.** `COUNTERS` and `LANE_MATCHUPS` are hand-curated, not derived from match data.
- **Scout-sheet champ_pool has no role breakdown.** A player who flexed Akali to top and mid in ranked appears as a single pooled `Akali` entry; the engine assumes role_match based on the player's primary, not on role-specific historic performance for that champ.
- **Scout sheets only refresh on app restart.** No invalidation hook from the Commands "Full Scout" run.
- **Backend `fetch_ranks_gsheets.py` is dormant on the draft path.** The `_kick_off_bg_draft` call is intentionally commented out; if you re-enable it, the local engine results will get overwritten 15–120s later (the original bug this was disabling fixes).
- **Multiplayer sync does not yet trigger scout prefetch.** The synced path receives the roster via `sync_tick` after `_board_begin_synced`; adding a thread-safe scout-prefetch trigger from the sync handler is straightforward but not yet wired up.
- **`phase_reason` and full `score_breakdown` are computed but not always rendered** — tooltips and detail-on-hover are an open UX TODO.

---

## 12. Where to make common changes

| Goal | File · function |
|---|---|
| Add or rebalance a champion's class tags | `draft_engine.py` · `SUBCLASSES` |
| Add a synergy / anti-synergy pair | `draft_engine.py` · `SYNERGIES` / `ANTI_SYNERGIES` |
| Add a counter | `draft_engine.py` · `COUNTERS` |
| Add a lane matchup | `draft_engine.py` · `LANE_MATCHUPS` |
| Add or change an archetype | `draft_engine.py` · `ARCHETYPES` |
| Add a global champion prior (used only when a player has zero data) | `draft_engine.py` · `CHAMP_PRIORS` |
| Add a champion to a role pool | `draft_engine.py` · `ROLE_VALID` |
| Reweight comp scoring (comfort vs synergy vs counter, etc.) | `draft_engine.py` · `score_team` weights block |
| Change recency half-life | `draft_engine.py` · `recency_weighted_wr(half_life=...)` |
| Change scout-pool vs customs weight | `draft_engine.py` · `_SCOUT_CHAMPS_WEIGHT` |
| Change beam width / candidate count | `draft_engine.py` · `beam_search_comp` defaults |
| Adjust ban role weighting | `draft_board.py` · `ROLE_BAN_WEIGHT` |
| Change which sheet provides which field | `reader.py` · `_read_rankings` / `_read_inhouse` / `_parse_scouting_sheet` |
| Add a new column to per-player scout sheet | `reader.py` · `_parse_scouting_sheet` AND propagate through `LiveData.scout_champs_for` if the engine should see it |
| Change pre-fetch trigger | `ui/draft.py` · drop-completion block at end of team-builder drop handler |

---

## 13. Quick reference: engine knobs

| Knob | Default | Tunes |
|---|---|---|
| `_BAYES_ALPHA`, `_BAYES_BETA` | 4.0 / 4.0 | Beta prior strength on per-champ WR shrinkage |
| `recency_weighted_wr.half_life` | 18 games | How fast old customs decay |
| Recent vs all-time WR blend | 0.65 / 0.35 | Weighting inside `champion_comfort` |
| Comfort: role_match bonus | × 1.20 | Reward for playing primary role |
| Comfort: inhouse multiplier | × 1.25 | Customs > ranked |
| `_SCOUT_CHAMPS_WEIGHT` | 0.85 | Scout-sheet ranked/draft champ vs customs |
| Form: HOT / COLD | × 1.10 / × 0.90 | Recent-form modifier |
| `score_team` weights | identity 0.28 · comfort 0.32 · synergy 0.15 · damage 0.08 · counter 0.10 · coherence 0.07 | Comp scoring blend |
| Viability bands | STRONG ≥ 0.62 · VIABLE ≥ 0.48 · WEAK ≥ 0.32 | UI tag thresholds |
| Beam width | 16 | Per-archetype search width |
| Candidates per player | 6 | Per-beam expansion fan-out |
| Ban coverage discount | up to −40% | When own picks counter the threat |
| Ban role weight (`ROLE_BAN_WEIGHT`) | TOP > MID > BOT > SUP > JGL | Phase-aware ban prioritisation |
