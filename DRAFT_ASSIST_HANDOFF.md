# Draft Assist — Deep-Dive Handoff

> **Living document.** Updated after every working response.
> A fresh session (or a teammate) should be able to read only this file and continue.



## Status &nbsp; · &nbsp; Last updated 2026-05-15

```
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│   [ DONE ]   CORE STAGES            E1–E4 · U0–U5 · L1–L2        │
│   [ DONE ]   READABILITY PASS A     + POOL OVERHAUL + Visual S1  │
│                                                                  │
│   [ DONE ]   v2.7 CYBERPUNK         Phases 1·2·3 (see § 0/0.1)   │
│              PHASES 1-3              P1 aesthetic skin · P2       │
│                                     Layout A + analytics rail +  │
│                                     narrative · P3 splash art +  │
│                                     advanced widgets             │
│                                                                  │
│   [ DONE ]   MOTION TUNED           full-screen bg now STATIC    │
│                                     (user: "moving too much")    │
│   [ DONE ]   CRASH FIXED            `t` var-shadow in TOP CALL   │
│                                     identity chips → smoke-test  │
│                                                                  │
│   [ DONE ]   ENGINE DEEP-DIVE       recency-weighted comfort ·  │
│                                     per-lane counter mode ·     │
│                                     strict contested · WHY +    │
│                                     radar reworked (see § 0.2)  │
│                                                                  │
│   [ DONE ]   EXE REBUILT            dist/TheRift.exe ~39.9 MB   │
│                                     2026-05-16 16:28 · clean ·  │
│                                     P1-3 + deep-dive baked in   │
│                                                                  │
│   [ WAIT ]   USER HANDS-ON TEST     run TheRift.exe → Draft      │
│                                     Board; check Layout A rail,  │
│                                     splash, all 4 phases         │
│                                                                  │
│   [ HOLD ]   NOT YET PUSHED         verify-before-push rule      │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

**Status legend** &nbsp; ☑ done &nbsp; · &nbsp; ◐ in progress &nbsp; · &nbsp; ☐ todo &nbsp; · &nbsp; ⊘ blocked

---

## § 0 &nbsp; v2.7 Cyberpunk Command Deck — Phase 1 &nbsp; · &nbsp; 2026-05-15

Source of truth for this initiative: `the_rift/Draft board revamp.txt`
(the deep-research spec). Built on `master` @ v2.6.0. Work done in the main
directory; **not pushed** — awaiting user hands-on visual test.

### User decisions locked (spec § 9 polls)

| Question | Choice |
|---|---|
| Gold vs cyan | **Subordinate gold** to cyan/magenta (ceremonial only) |
| Monospace font | **Add JetBrains Mono** for data/labels |
| CALM MODE placement | **Settings tab** (not a header button) |
| Reduce-motion default | **OFF** — full theatrical by default |

### What shipped in Phase 1

- **Palette** — 12 cyber keys added to `theme.C` (`cy/cy_lt/cy_dk`,
  `mg/mg_lt/mg_dk`, `amb`, `term_g`, `alert_r`, `scan_gy`, `panel_dk`,
  `grid_a`). Gold kept but demoted. Side-accent shim `_side_accent()` +
  `BLUE/RED_ACCENT*` near `_ROLE_COLORS` (cyan=blue, magenta=red).
- **`the_rift/ui/cyber.py`** (new) — `draw_cut_rect`, `draw_brackets`,
  `draw_bracket_label`, `draw_dashed_rect`, `draw_marching_dash`,
  `draw_scanlines`, `draw_grid_bg`, `draw_glitch_overlay`, plus motion
  gate (`set_motion`/`motion_on`), `wave()`, `flicker_alpha()`.
  Reuses `ui/effects.py` (breathing/drift) — no duplication.
- **Fonts** — `JetBrainsMono-Medium.ttf` (+ Bold) installed in
  `the_rift/fonts/` (OFL, v2.304). `mono_11..mono_36` registered in
  `theme.setup_fonts()`.
- **CALM MODE** — `calm_mode` flag in `data/config.py` (`_DEFAULTS`,
  default `False`). Toggle lives in the **Settings tab** ("DRAFT BOARD"
  section). Applied live on toggle and on `_board_begin()` via
  `cyber.set_motion(not calm_mode)`. State-change anims are NOT gated
  (typewriter/slide/pop still play in CALM).
- **Every board surface re-skinned** (spec § 2.1–2.10): header
  `[ DRAFT BOARD ]` mono + marching UNDO/EXIT; corner-cut timeline
  cells w/ glow trail (§5.7) + marching current cell + cyan underline;
  `[ BLUE/RED OPS ]` cut team panels w/ on-clock cursor blink (A8);
  cy/mg action banner ("> YOUR PICK"); bracketed arch-picker chips;
  "TACTICAL READOUT" w/ `[ OUR ]`/`[ ENEMY ]`; terminal context sigils
  (`>`/`!`/`+`); TOP CALL heavy cut card + typewriter name (§5.4) +
  portrait flicker (§5.8) + scanning bar + mono stat band + bracket
  chips; cut alternative rows w/ cyan stripe; terminal pool search +
  cut cells + cyan scrollbar.
- **Ambient/state motion** — A1 full-screen scanlines, A6 grid drift,
  A4 timeline/banner breathing via `wave()`, A8 cursor blink, §5.7 glow
  trail, §5.8 flicker, §5.4 typewriter, S1 slide-in (pre-existing),
  S3 lock-pop (kept). All ambient motion frozen by CALM MODE.

### Deferred (not blocking; lower-impact polish)

- A2 center-panel border glow, A5 per-chip staggered pulse, A7 team
  accent breathing — extra ambient pulses; core set is in.
- S2 glitch overlay on rec-swap and a literal S5 colour cross-fade —
  `cyber.draw_glitch_overlay` exists/unused; banner already does
  instant cy↔mg side identity + pulse.
- Phase 2 / Phase 3 — now **DONE**, see § 0.1 below.

---

## § 0.1 &nbsp; v2.7 — Phase 2 + Phase 3 + motion tuning &nbsp; · &nbsp; 2026-05-15

### Motion feedback fix

User: *"the background moving is too much, keep the rest of the
animation."* → all full-screen background drift is now **static**: grid
pan speed 0, full-screen + phase-band + role-stripe scanlines speed 0.
Focal motion kept: marching dashes, timeline glow trail, typewriter,
portrait flicker, breathing pulses, cursor blink, lock pop, scanning bar.
Saved as memory `feedback_ambient_motion.md`. Particle drift field
(spec §5.3) **deliberately skipped** — it is exactly the kind of ambient
background motion the user rejected.

### Phase 2 — Layout A + analytics rail (DONE)

- **Layout A** geometry in `_draw_board`: BLUE+RED stacked in one narrow
  left column (200px, 178 ≤1300w), wide center, **300px right rail**
  (220 ≤1300w), full-width bottom narrative strip. `_draw_board_team`
  made height-adaptive (slot size/fonts scale; bans + ribbon guarded so
  they never overflow the now-short stacked panels). Refuses < 1280×720
  with a resize message (spec §7.5).
- **`the_rift/ui/board_rail.py`** (new) — defensive, engine-memoized
  (recompute only on picks-signature change). Widgets: #1 win-prob bar +
  sparkline, #3 score-breakdown bars, #11 team-strength radar (overlaid
  cyan/magenta octagons), #19 damage profile, #15 counter-coverage
  donut, #2 counter-pick predictor, #18 synergy web, #9 contested
  ladder. Each widget try/excepts to a blank frame — one bad datum can't
  crash the board.
- **#12 narrative log** — bottom terminal strip from `state._history`.
- **#27 action-queue preview** — header chips (wide viewports ≥1500w).
- **#29 identity chips** — 3 strongest SUBCLASSES tags by the hero name.

### Phase 3 — splash art + advanced (DONE)

- **`the_rift/data/splash_art.py`** (new) — mirrors `champion_icons.py`
  with disk cache (`assets/splash_cache/`) + **LRU GPU-texture eviction**
  (max 4 registered; spec §7.3). Reuses `champion_icons._ddragon_id`.
- **#21 splash backdrop** on TOP CALL with stateless **ken-burns**
  (uv pan/zoom, frozen by CALM) + readability scrim; degrades to the
  portrait until the splash is fetched.
- **#30 confidence meter** replaces the +N-vs-#2 chip (gap → 0-100 % bar).
- **#7 pool-depth capsule** per role slot (viable comfort picks left).
- **#8 LCU phase-countdown bar** on the banner — `parse_session` now
  returns `timer_left`; live mode only (no idle ring in manual, by
  design — avoids gratuitous motion).
- **#5 opponent patterns** — folded into the existing LIKELY NEXT ribbon
  (it is already per-player comfort-ranked = their favourites); no extra
  UI added to the now-tight stacked panels.

### Crash fixed

TOP CALL identity-chip loop reused local `t`, clobbering the float TOP
CALL anim progress → `str - float` at `_draw_board_center` (the screenshot
crash). Renamed to `chip_txt`. Added a **headless render smoke-test**
(stubs all `dpg.draw_*`, runs `_draw_board` across phases 0/1/6/7/13/18 ×
normal/CALM) — all pass. Harness was removed after use.

### Deferred (documented, non-blocking)

- #6 what-if ban simulator (hover-driven; interaction-heavy, risky to add
  blind — `cyber.draw_glitch_overlay` + engine speculation available when
  picked up).
- Spec §5.1 A2/A5/A7 minor ambient pulses; S2 glitch; literal S5
  cross-fade. Particle drift (intentionally cut, see above).

### Verification checklist (user)

```
1. dist/TheRift.exe → Draft → Draft Board (manual). It must NOT crash
   when a recommendation appears (the screenshot bug).
2. Layout A: narrow stacked BLUE/RED on the left, wide TOP CALL center,
   analytics rail on the right (win-prob bar + sparkline, WHY bars,
   radar, damage, coverage donut, predictor, synergy web, contested),
   narrative strip along the bottom. Check nothing overlaps/clips at
   your resolution; team panels are tight when stacked — report if a
   role slot / bans row is cut off.
3. Background must be STATIC now (no swimming). Confirm marching dashes,
   typewriter, glow trail, flicker still move.
4. TOP CALL splash art fades in behind the portrait after a moment
   (needs internet first run; falls back to portrait if offline).
5. Click all four phases (BAN1/PICK1/BAN2/PICK2); verify pool + suggestion
   clicks still land (Layout A moved geometry).
6. Settings → DRAFT BOARD → CALM MODE freezes ambient motion only.
7. Batch analysis tab UNCHANGED.
8. Report anything off; nothing pushed until you confirm.
```

---

## § 0.2 &nbsp; v2.7 — Engine deep-dive + radar/why fixes &nbsp; · &nbsp; 2026-05-15

User feedback: radar confusing/no axis labels; "WHY THIS CALL" blank;
pick engine still blind-safe after the lane opponent is picked, under-
weights counters, and flags "contested" when only one side actually
plays the champ. Deep-dive done across the data → engine → board → UI
stack.

### Root causes (verified in code)

- **WHY blank** — `recommend_action` suggestions carried no
  `score_breakdown`; the widget read a key that never existed.
- **False contested** — engine `contested()` fed off `_player_candidates`,
  which injects ranked `top_champs` + `CHAMP_PRIORS`, so a champ counted
  as "both teams want it" off soloQ mastery / priors, not customs play.
- **Blind-safe after laner known** — `enemy_info` was the *team-wide*
  pick count, not the same-lane opponent; SAFE was still allowed and
  comfort (0.50) dwarfed counter (0.30).
- **No recency** — per-champ inhouse dicts were all-time aggregates; the
  reader emitted **no** per-champ recency data at all.

### Changes

- **`data/reader.py`** — `_read_inhouse` now emits per-champ `results`
  (chronological 1/0, capped to the **last 100 customs games**),
  `recent_results` (last 20) and `roles` (per-champ role-frequency the
  engine already expected but never received). Additive — other consumers
  unaffected.
- **`data/draft_engine.py`** — new `recency_weighted_wr()` (exponential,
  half-life 18 games). `champion_comfort()` blends recency-shrunk WR
  (0.65) with all-time posterior (0.35) when `results` exist. Ranked
  `top_champs` demoted ×0.75, priors ×0.50 — real customs play always
  out-ranks them. New `customs_champs()` = strict {champ: comfort} for
  champs actually played ≥3 customs games (no mastery/priors).
- **`data/draft_board.py`** — pick recommender reworked: when the
  **same-lane enemy is locked**, that role enters *counter-pick mode* —
  never tagged blind-safe, scoring `0.34 comfort + 0.40 counter +
  0.16 lane − 0.24·(losing-lane)`; counter weighting raised everywhere;
  `contested` now strict (min of both sides' real `customs_champs`).
  Each suggestion now carries a **`factors`** dict (comfort / counter /
  lane / blind_safe / flex / contested / steer / final).
- **`ui/draft.py`** — `_is_contested` aligned to the same ≥3-customs-
  games-on-both-sides rule (glyph + ladder now agree with suggestions).
- **`ui/board_rail.py`** — WHY panel reads the real per-suggestion
  `factors` (labeled bars; LANE drawn as a centre-zero advantage bar,
  green = we win lane, magenta = we lose it; shows the champ name; ban
  phases say so instead of blanking). Radar reworked: spokes, two value
  rings, **8 axis labels** (FRONT/ENGAGE/PEEL/AOE/BURST/RANGE/SCALE/
  MOBIL), a BLUE/RED legend, per-axis normalisation so one big axis no
  longer flattens the rest.

Headless smoke-test (now with an inhouse-history fixture: per-champ
`results`, shared champ across sides) — all phases × normal/CALM pass;
`recency_weighted_wr` and `customs_champs` sanity-checked. Harness removed.

### Verify (user)

```
1. WHY THIS CALL rail panel now shows labeled bars for the top
   suggestion (comfort/counter/lane/contested/safe/flex/fit) + champ name.
2. Radar: 8 labeled axes, BLUE/RED legend, both shapes readable.
3. After an enemy laner is locked, that role's suggestion is a COUNTER
   (or best-into-the-matchup COMFORT) — never "blind-safe"; counters
   rank above merely-comfortable neutral picks.
4. "Contested" only shows when BOTH teams have a player with ≥3 customs
   games on that champ (no more one-sided false contested).
5. Recency: a champ a player has been winning on lately should rank
   above one they used to win on but lost recently (needs real customs
   data loaded — verify against someone whose form changed).
6. Still nothing pushed.
```

> **Tuning knobs** if you want it stronger/weaker after testing:
> `recency_weighted_wr` half-life (engine), the `0.65/0.35` recency blend
> in `champion_comfort`, and the counter-mode score weights in
> `draft_board.py` pick branch.

---

## § 1 &nbsp; Mission

### Make Draft Assist the best drafting tool *for your friends specifically*

The format that matters: **tournament draft** (competitive pick / ban order),
very likely **Fearless** in 2026.

> **"Most useful" =** &nbsp; at every decision point in a real draft, the tool
> tells you the **best action and why**, grounded in *these players'* real
> comfort data — not a generic meta tool.

### Two surfaces to maximise

| Surface | Job |
|---|---|
| **Compositions** | what to pick, in what order, countering what |
| **Suggested bans** | what to remove, split correctly across the two ban phases |

### Scope lock &nbsp; · &nbsp; 2026-05-14

| Decision | Choice |
|---|---|
| Format | single tournament-draft games (champions reusable) |
| Build | interactive **draft board** — click through the 20-action sequence |
| Opponents | mostly inhouse → no enemy scouting work |
| Entry point | straight to tournament-draft mode |
| Fearless? | **dropped** (Phase 3) |
| Enemy scouting? | **dropped** (Phase 4-C) |

### Three modes (chosen from a new landing screen on the Draft tab)

1. **Batch analysis** &nbsp; — existing drag-drop "BEGIN ANALYSIS". &nbsp; *Keep as-is.*
2. **Draft board — manual entry** &nbsp; — type / click each action in a room.
3. **Draft board — live Riot import** &nbsp; — auto-follow an in-progress champ select.

> **Tech note on live import.** &nbsp; Public Riot API has *no* champ-select
> endpoint. Live import = **LCU local API** (`https://127.0.0.1:2999`, riot
> client `/lol-champ-select/v1/session` via lockfile-auth port) polled on the
> machine running the League client. A thin `draft_lcu.py` adapter maps LCU
> session → `DraftBoardState`. Engine / board logic is import-source-agnostic,
> so E1–E4 are unaffected.



---

## § 2 &nbsp; Strategy

### The core realisation

> **The engine currently solves the wrong problem.**
>
> It computes a *god's-eye, simultaneous-pick optimal comp* for two
> fully-known teams. Real tournament draft is a *sequential, alternating,
> partial-information* game.
>
> Players need **per-slot advice as the board fills in**, not a post-hoc
> "ideal team."

### Priority order

1. **Exploit the moat first.** &nbsp; The Rift uniquely has *per-player,
   per-champion* comfort (inhouse WR / KDA / role split), ranked mastery,
   form, rank-history. Public ML tools (LoLDraftAI ≈ 57% from draft alone) do
   **not** know *your friends*. Squeeze every drop from this with current
   data before adding any.

2. **Make it phase-aware.** &nbsp; Encode the real tournament draft sequence
   and give per-slot recommendations (first-pick-safe vs counter-pick vs
   power-pick).

3. **Make it Fearless-aware.** &nbsp; *(Deferred — not in current scope.)*
   Track champions spent across a series; manage each player's *series pool*.

4. **Then** enrich with new data — per-match history already on the sheet
   but aggregated away; patch tag; external meta tier; enemy scouting.

### Guardrails

| ✓ | Keep the pure-Python engine the single source of truth (subprocess stays disabled) |
| ✓ | All champion knowledge stays in `draft_engine.py` unless we move it to an editable sheet tab |
| ✓ | **Don't push to GitHub** until the user verifies |
| ✓ | Work in the **main directory** `C:\Users\blhei\Desktop\all code` — not worktrees |



---

## § 3 &nbsp; Context &nbsp; · &nbsp; *verified against v2.3.1, branch `master`*

### 3.1 &nbsp; Tournament draft format

```
┌────────────────────────────────────────────────────────────────┐
│                                                                 │
│   STANDARD COMPETITIVE ORDER — 20 ACTIONS                       │
│                                                                 │
│   BAN  1     ▸     B  R  B  R  B  R          (B starts, alt.)  │
│                                                                 │
│   PICK 1     ▸     B  │  R R  │  B B  │  R   (snake from B1)   │
│                                                                 │
│   BAN  2     ▸     R  B  R  B                (R starts)        │
│                                                                 │
│   PICK 2     ▸     R  │  B B  │  R           (R5 = final pick) │
│                                                                 │
└────────────────────────────────────────────────────────────────┘
```

#### Strategic consequences the tool must reflect

| Side / slot | Implication |
|---|---|
| **Blue** first pick | grab the contested power pick — but you reveal first |
| **Red** R3 (last of P1) | counter-pick power |
| **Red** R5 (final pick) | counter-pick power |
| Early picks | should be **blind-safe / flexible** |
| Late picks | save the **counters** for here |
| Ban phase 1 | enemy comfort / OP / flex threats — little info yet |
| Ban phase 2 | targeted: kill what wrecks *your now-drafted* comp |
| Role-weighting (bans) | **Top &gt; Mid &gt; ADC &gt; Sup &gt; JGL** |

> **2026 rules note.** &nbsp; "First Selection" decouples side from pick
> order; **Fearless Draft is the default competitive format** — no champion
> reused within a series, so champion-pool depth across games is decisive.
> *Not in scope for the current build.*

### 3.2 &nbsp; Current architecture

#### Files

| File | LOC | Role |
|---|---:|---|
| `the_rift/data/draft_engine.py` | 1232 | pure-Python engine + all tables |
| `the_rift/ui/draft.py` | 2251 | UI + state machine |
| `the_rift/data/draft_board.py` | new | sequence + state + per-slot recommender |
| `the_rift/data/draft_lcu.py` | new | live LCU adapter |

#### Engine internals — `draft_engine.py`

- **Tables.** &nbsp; `SUBCLASSES` (19 tags), `DAMAGE_*`, `SYNERGIES` /
  `ANTI_SYNERGIES`, `COUNTERS` (~150 pairs), `LANE_MATCHUPS` (~120),
  `ARCHETYPES` (7), `ROLE_VALID`, `CHAMP_PRIORS`.
- **Algorithms.** &nbsp; Bayesian shrink (Beta 4,4), team identity vector,
  beam search (width 16, 6 cands / player), `score_team` (identity .28 /
  comfort .32 / synergy .15 / damage .08 / counter .10 / coherence .07),
  `recommend_comps`, `recommend_bans`, `compute_matchups`,
  `enemy_weakness_vector` *(exists, **underused**)*.

#### UI internals — `draft.py`

- Drag-drop builder → `_analyse_teams` (4-stage chained pipeline) → strategy panels.
- **No pick / ban-order model of its own** — that's what `draft_board.py` adds.
- Subprocess (`_kick_off_bg_draft`) **disabled by design.**
- Rank-history win-% prediction still active (win meter + lane bars only).
- Renderers: &nbsp; `_draw_strategy_panel`, `_draw_ban_card`, `_draw_comp_card`,
  `_draw_threat_focus`, `_draw_lane_card`, `_draw_score_radar`, `_draw_win_meter`.
- UI already carries `win_condition`, `spike`, `score_breakdown`, `phase_reason`
  in its dicts.

### 3.3 &nbsp; Data inventory

#### The moat &nbsp; — &nbsp; *per-player, available now*

- **Inhouse per-champion.** &nbsp; `champ, games, wins, losses, wr, kda, kills,
  deaths, assists, damage` per player (from `_InhouseGameLog`, aggregated).
- **`primary_roles`** per player
- **Ranked** &nbsp; tier / score / `final_score`
- **`top_champs`** &nbsp; Riot mastery, top 3 + points
- **`form`** &nbsp; HOT / COLD / MIXED
- **Rank-history series**

#### Available but UNUSED &nbsp; — &nbsp; *high leverage*

| Source | What it unlocks |
|---|---|
| Per-match rows in `_InhouseGameLog` | recency weighting, per-matchup, h2h, pool-trend |
| `patch_ticker.get_patch_version()` | patch awareness |
| `fetch_recent_matches` (Riot) | scout non-inhouse / enemy players' real pools |
| `enemy_weakness_vector()` (coded!) | already exists — just needs surfacing |

#### Would need new feeds

- Champion meta tier / pick-ban-WR by patch &nbsp; *(external, or editable sheet tab)*.
- Editable curated tables (synergy / counter / matchup) via a sheet tab so the
  user can tune between patches **without a rebuild.**

### 3.4 &nbsp; Research benchmarks

> Pure champion-draft win prediction caps at **≈ 56–62%** accuracy.
> *(LoLDraftAI 56.7% &nbsp; · &nbsp; academic 62% champions-only.)*
>
> → Heuristic engine is fine. &nbsp; The *win* is **player-specific data +
> draft-phase guidance**, not chasing ML accuracy.
>
> Academic result: &nbsp; **player–champion experience** is a strong predictor.
> That is exactly The Rift's unique signal. &nbsp; Lean into it.



---

## § 4 &nbsp; Build Plan &nbsp; · &nbsp; Interactive Tournament-Draft Board

### Architecture map

```
                ┌─────────────────────────────┐
                │   ui/draft.py               │   state · rendering · input
                │   (existing, extended)      │
                └──────────────┬──────────────┘
                               │
                ┌──────────────┴───────────────┐
                │                              │
   ┌────────────▼────────────┐    ┌────────────▼────────────┐
   │  data/draft_board.py    │    │  data/draft_lcu.py      │
   │  (NEW)                  │    │  (NEW — live mode)      │
   │                         │    │                         │
   │  • DRAFT_SEQUENCE       │    │  • lockfile auth        │
   │  • DraftBoardState      │    │  • parse_session        │
   │  • recommend_action     │    │                         │
   └────────────┬────────────┘    └─────────────────────────┘
                │
   ┌────────────▼────────────┐
   │  data/draft_engine.py   │    scoring core — unchanged
   │  (existing)             │
   └─────────────────────────┘
```

### Engine side &nbsp; — &nbsp; `data/draft_board.py`

- **`DRAFT_SEQUENCE`** — the 20 actions as data tuples.
- **`DraftBoardState`** — blue / red `picks[5]` (by role), blue / red `bans[5]`,
  pointer 0–19, `our_side`, players-by-side (with inhouse / primary_roles).
- **`recommend_action(state, inhouse, primary_roles)`** — for the current action:
  - **ban** → ranked bans + reason.
    - **P1** &nbsp; enemy comfort × OP / contested × flex × role-importance (Top &gt; Mid &gt; ADC &gt; Sup &gt; JGL).
    - **P2** &nbsp; counters to *our committed* wincon (reuse `recommend_comps`
      on our locked picks to know the wincon, then `team_counter_coverage` inverse).
  - **pick** → ranked champs for the player on the clock, each tagged
    **POWER · SAFE · COUNTER · FLEX · COMFORT** + one-line why; steered toward
    a coherent archetype via `recommend_comps` on picks-so-far.

#### Helper metrics (reuse existing tables)

| Metric | Definition |
|---|---|
| `blind_safety(champ)` | 1 − norm(max incoming `COUNTERS` / `LANE_MATCHUPS`); bonus if in ≥ 2 `ROLE_VALID` |
| `flex_score(champ, our_players)` | # roles ∩ players who can play it |
| `counter_value(champ, enemy_revealed, role)` | from `COUNTERS` + `LANE_MATCHUPS` |
| `contested(champ)` | high comfort for a player on **both** sides → grab / ban early |
| `cohesion_text(picks)` | `_team_vector` gaps → words ("no frontline" …) |

### UI side &nbsp; — &nbsp; `ui/draft.py`

- New **`DraftPhase.BOARD`** + state &nbsp; · &nbsp; menu entry "Tournament Draft".
- **Board screen** &nbsp; 10 pick slots (5 / side by role) + 10 ban slots + action
  timeline with "on the clock" highlight; manual champion picker per action;
  lock / undo.
- **Recommendation panel** &nbsp; updates after each locked action: top-3 for
  current action (tag + why), live our-side cohesion readout, live
  enemy-weakness advice from `enemy_weakness_vector`, `phase_reason`-style strings.
- **Visual parity** &nbsp; reuse `_panel_bg`, `_draw_*`, fonts, anim.

---

### Ordered steps

#### Engine &nbsp; — &nbsp; `data/draft_board.py`

| ID | Step | Status | Notes |
|---|---|:---:|---|
| E0 | Research + handoff + scope lock | ☑ | done |
| E1 | `DRAFT_SEQUENCE` + `DraftBoardState` + skeleton `recommend_action` | ☑ | full 20-action walk &nbsp; · &nbsp; 5+5 picks/bans &nbsp; · &nbsp; no dupes &nbsp; · &nbsp; undo OK &nbsp; · &nbsp; real engine champs returned |
| E2 | Helper metrics | ☑ | Yasuo → 0.17 &nbsp; · &nbsp; Malphite → 0.57 &nbsp; · &nbsp; Malz vs Yasuo → 1.0 &nbsp; · &nbsp; cohesion phrases correct |
| E3 | Pick recommender | ☑ | POWER / SAFE / COUNTER / FLEX / COMFORT tagging &nbsp; · &nbsp; archetype steering &nbsp; · &nbsp; B1 → SAFE picks steered to "Split Push (1-3-1)" |
| E4 | `recommend_bans_split()` | ☑ | P1 enemy-comfort × role-weight × flex(1.15) &nbsp; · &nbsp; P2 counter-our-wincon blended .62/.38 &nbsp; · &nbsp; "counters your Vayne" verified |

#### UI &nbsp; — &nbsp; `ui/draft.py`

| ID | Step | Status | Notes |
|---|---|:---:|---|
| U0 | Mode-select landing | ☑ | 3 mode cards &nbsp; + &nbsp; "Re-analyse previous" &nbsp; · &nbsp; Batch path unchanged |
| U1 | `DraftPhase.BOARD` + `_draw_board` | ☑ | header / 20-action timeline / two team columns / center panel |
| U2 | Picker + wiring | ☑ | clickable tagged rows + manual legal-pool grid &nbsp; · &nbsp; UNDO / EXIT / NEW &nbsp; · &nbsp; `_board_hits` registry |
| U3 | Restructured `_draw_board_center` | ☑ | TOP CALL card (big champ, tag chip, why) + compact ALTERNATIVES rows |
| U4 | `weakness_advice()` surfaced | ☑ | teal **EXPLOIT** lines &nbsp; · &nbsp; amber cohesion warnings &nbsp; · &nbsp; phase-reason note &nbsp; · &nbsp; BUILD → target-comp line |
| U5 | Timeline + pagination + polish | ☑ | exact `locked_at()` &nbsp; · &nbsp; paginated pool &nbsp; · &nbsp; gradient frame on center panel |

#### LCU Live &nbsp; — &nbsp; `data/draft_lcu.py`

| ID | Step | Status | Notes |
|---|---|:---:|---|
| L1 | Lockfile + `parse_session()` | ☑ | std paths + optional `league_path` config &nbsp; · &nbsp; Basic-auth HTTPS &nbsp; · &nbsp; pure parser &nbsp; · &nbsp; self-test green |
| L2 | `mirror()` + `_lcu_poll_loop` daemon | ☑ | render-thread `_board_live_sync` &nbsp; · &nbsp; live status header &nbsp; · &nbsp; UNDO / pool hidden when synced &nbsp; · &nbsp; falls back to manual cleanly |

#### UI Readability Polish

| ID | Step | Status | Notes |
|---|---|:---:|---|
| **U6 · Pass A** | Draft Board readability resize | ☑ | header 26→32 cinzel &nbsp; · &nbsp; timeline 46h→64h, labels 12→16, locked-champ 12→18, cleaner "B PICK"/"R BAN" naming &nbsp; · &nbsp; team-col header 19→24, role 12→16, player 14→18, locked-champ 17→22, slot 40→56h with role accent stripe, bans 12→14 &nbsp; · &nbsp; action banner 20→26 + thicker border, sub 13→15 &nbsp; · &nbsp; **TOP CALL hero** champion 24→**36** with 8px accent stripe, card 62→110h, why-text 12→17 &nbsp; · &nbsp; alternatives row 34→52h, champion 15→22, why 11→14, accent stripe &nbsp; · &nbsp; UNDO/EXIT 18→20 |
| **U6b · Pool overhaul** | "Lock any champion" searchable + scrollable | ☑ | replaced pagination with **type-to-filter search box** + **scrollable grid** (mouse-wheel + arrow keys) &nbsp; · &nbsp; pool region 150h→240h &nbsp; · &nbsp; cell 92×24 / 12px → 124×38 / 16px &nbsp; · &nbsp; SEARCH header with blinking caret + "type to filter…" hint + live result count ("N of M") &nbsp; · &nbsp; X button to clear &nbsp; · &nbsp; backspace pops last char &nbsp; · &nbsp; scrollbar indicator on right edge &nbsp; · &nbsp; PageUp/Down for fast scroll &nbsp; · &nbsp; Up/Down for row-by-row |
| **U6c · Visual Stage 1** | Polish pass — pills, phase dividers, halos | ☑ | **pill-shaped tag chips** with vector glyphs (lightning/shield/crossed-swords/diamond/check/banned) on TOP CALL + every alternative row &nbsp; · &nbsp; **timeline phase headers** (BANS 1 / PICKS 1 / BANS 2 / PICKS 2) with gold vertical dividers between phases &nbsp; · &nbsp; **side-tinted top edge** stripe on center panel (blue/red wash by current action's side) &nbsp; · &nbsp; **TOP CALL halo** — `_gradient_frame` radiating glow in tag color around the hero card |
| U6d · Visual Stage 2 | Champion portraits *(next)* | ☐ | fetch + cache Data Dragon square icons; add to TOP CALL + locked picks + alts + pool cells |
| U6e · Visual Stage 3 | Motion polish *(next)* | ☐ | TOP CALL ease-in · timeline lock-pop · pool filter stagger-fade · hover lifts |
| U7 · Pass B | Batch results readability *(pending)* | ☐ | ban / comp / lane cards · radar labels · threat chip |
| U8 · Pass C | Polish *(pending)* | ☐ | strategy panel headers · win-meter sub-label |

#### Build & Verify

| ID | Step | Status | Notes |
|---|---|:---:|---|
| V1a | Spec hiddenimports + EXE build | ☑ | `TheRift.exe` ~41.5 MB &nbsp; · &nbsp; 2026-05-14 23:49 &nbsp; · &nbsp; *(superseded by V2a)* |
| V2a | Rebuild EXE after Pass A | ☑ | `TheRift.exe` ~41.5 MB &nbsp; · &nbsp; 2026-05-15 00:31 &nbsp; · &nbsp; clean &nbsp; · &nbsp; `ui/draft.py` changes baked in |
| V2b | **USER HANDS-ON TEST** | ◐ | ← run `dist/TheRift.exe` &nbsp; · &nbsp; check Pass A visual scale &nbsp; · &nbsp; do **not** push until confirmed |

---

### V1 user test checklist

```
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│   1.  Launch  the_rift/dist/TheRift.exe  →  Draft tab            │
│       Expect:  3 mode cards appear.                              │
│                                                                  │
│   2.  BATCH                                                      │
│       Works exactly as before  (regression check).               │
│                                                                  │
│   3.  DRAFT BOARD — MANUAL                                       │
│       Builder opens with "START DRAFT BOARD" + BLUE/RED          │
│       "YOU ARE" toggle.                                          │
│       Board shows:  timeline · both teams · TOP CALL +           │
│         alternatives + EXPLOIT / cohesion.                       │
│       Click suggestion or pool champ → locks, advice advances.   │
│       UNDO reverts.  Pool pager works.  EXIT / NEW → mode select.│
│                                                                  │
│   4.  DRAFT BOARD — LIVE                                         │
│       With League in custom champ select:                        │
│         status → "LIVE — synced"; picks/bans mirror client;      │
│         UNDO and pool grid hidden.                               │
│       With client closed:                                        │
│         "League client not found — manual entry"  and            │
│         manual flow still works.                                 │
│                                                                  │
│   5.  Report anything off — layout overlap · wrong advice ·      │
│       click misalignment — for U5-style polish.                  │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

### Folded-in quick wins

*Delivered as parts of E2 / E3 / E4 / U4 — not separate steps.*

- First-pick safety
- Flex detection
- Per-slot counter engine
- Cohesion warnings
- Enemy-weakness advice
- `phase_reason` rendering

### Deferred &nbsp; — &nbsp; not in current scope

- Fearless series tracker
- Enemy / outside-team scouting

### Optional later &nbsp; — &nbsp; low-risk, after the board ships

- Expose `_InhouseGameLog` per-match rows (recency weighting)
- Patch tag via `patch_ticker`
- Editable meta / curated sheet tab



---

## § 5 &nbsp; Decisions Log

#### 2026-05-14 &nbsp; · &nbsp; Subprocess stays disabled

Engine is sole source of truth (confirmed in v2.3.1). Work targets
`draft_engine.py` + new `draft_board.py` + `draft.py`, **main directory only.**

#### 2026-05-14 &nbsp; · &nbsp; Research conclusion

Biggest lever is *phase-aware advice on top of player-specific data*, not ML
accuracy or more champion tables.

#### 2026-05-14 &nbsp; · &nbsp; 2026 competitive default

Fearless + First Selection. &nbsp; *(Context only — not in scope.)*

#### 2026-05-14 &nbsp; · &nbsp; **USER SCOPE LOCK**

> - **Format:** &nbsp; single tournament-draft games (not Fearless).
> - **Build:** &nbsp; interactive draft board.
> - **Opponents:** &nbsp; mostly inhouse — no enemy scouting.
> - **Entry:** &nbsp; start straight on tournament-draft mode.
> - → Fearless tracker + enemy scouting **dropped.**
>   Phase-1 wins folded into the board build.

#### 2026-05-14 &nbsp; · &nbsp; **USER**

> - Want **both** manual entry **and** live Riot draft import.
> - Keep the old batch screen.
> - Add a **mode-select landing screen** on the Draft tab.
> - Approved starting **E1** now.
> - → Live import via LCU local API adapter (steps L1–L2);
>   landing screen = step U0.



---

## § 6 &nbsp; Open Items

> *No blocking questions right now.*
>
> Live-import depends on the League client running on the same PC as The Rift
> and exposing the LCU port. &nbsp; If a teammate's setup blocks that, live
> mode degrades to manual cleanly.
