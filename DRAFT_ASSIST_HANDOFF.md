# Draft Assist — Deep-Dive Handoff

> **Living document.** Updated after every working response.
> A fresh session (or a teammate) should be able to read only this file and continue.



## Status &nbsp; · &nbsp; Last updated 2026-05-15

```
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│   [ DONE ]   CORE STAGES            E1–E4 · U0–U5 · L1–L2        │
│                                                                  │
│   [ DONE ]   READABILITY PASS A     Draft Board mode resized     │
│                                     (timeline · team cols ·      │
│                                      TOP CALL hero · alternatives│
│                                      · action banner · header)   │
│                                                                  │
│   [ DONE ]   POOL OVERHAUL          search box + scrollable grid │
│                                     (type-to-filter · mousewheel │
│                                      · arrow keys · clear-X)     │
│                                                                  │
│   [ DONE ]   EXE REBUILT            the_rift/dist/TheRift.exe    │
│                                     ~41.5 MB · 2026-05-15 00:57  │
│                                     clean · Pass A + pool +      │
│                                     Visual Stage 1 baked in      │
│                                                                  │
│   [ WAIT ]   USER HANDS-ON TEST     run TheRift.exe, eyeball     │
│                                     Draft Board mode             │
│                                                                  │
│   [ HOLD ]   NOT YET PUSHED         verify-before-push rule      │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

**Status legend** &nbsp; ☑ done &nbsp; · &nbsp; ◐ in progress &nbsp; · &nbsp; ☐ todo &nbsp; · &nbsp; ⊘ blocked

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
