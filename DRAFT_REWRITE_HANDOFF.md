# Draft Tool Rewrite — Handoff Doc

> Live working document for the Draft Tool rewrite. A future Claude session should
> read this first, then `DRAFT_BOARD.md` for the existing architecture, then start
> work at the **Next Action** pointer near the bottom.
>
> Augment this file after every meaningful change. Keep the **Status**, **Change
> log**, and **Next Action** sections accurate at all times — they are the
> contract between sessions.

---

## 0 · Status snapshot

| Phase | State | Notes |
|---|---|---|
| Plan locked | ✅ Complete | User answered every fork; no open questions remain |
| Phase 1 — Fly.io + auto-connect | 🟢 Code + Deploy complete · ⏸ Two-client verification deferred | Server live at `https://the-rift-draft-sync.fly.dev/`. Health endpoint OK. User chose to verify everything together at the end (single PyInstaller build, Phase 6). |
| Phase 2 — Engine + scout chronology | 🟢 Code complete · ⏸ End-to-end verification deferred | All 12 sub-tasks landed. Engine self-test passes (`python -m data.draft_board` from `the_rift/`). SLOT_ROLE_BIAS verified to push B1 toward JGL/BOT; pivot detection fires correctly when engage tanks get banned. |
| Phase 3 — LCS/LEC theme + UI rewrite | 🟢 Code complete · ⏸ Manual run-through deferred to Phase 6 build | `lol_theme.py` primitive set complete; `theme.py` palette extended; **`draft.py` + `board_rail.py` cyber refs 87→0**. All existing phases (IDLE, CONNECTING, LOBBY/TEAM_BUILD, BOARD) rendered with LCS/LEC primitives. `DraftPhase` enum extended with SCOUTING/BRIEFING/ARCHETYPE + stub waiting-screen render functions. Phase 4 wires the new phases into the synced flow. |
| Phase 4 — Archetype screens + pivot + ghost | 🟢 Code complete · ⏸ End-to-end run-through deferred to Phase 6 build | SCOUTING/BRIEFING/ARCHETYPE phases wired into `_sync_phase_watcher`; each has a real rendering function + input handler. Pivot alert banner + enemy ghost-suggestion chip added to BOARD. |
| Phase 5 — Audio + DONE polish + solo fallback | 🟢 Code complete · ⏸ Sound files + end-to-end run-through deferred to Phase 6 build | `the_rift/ui/audio.py` ships; six cues wired into draft.py; config already has `audio_enabled=True`. DONE-screen rewritten with win-prob chart + per-side game-plan cards + "what got banned" retrospective. Solo fallback: 30s countdown + "Continue solo (briefing only)" link in LOBBY, jumps locally to BRIEFING then IDLE. |
| Phase 6 — LCU drop + cleanup + final build | 🟢 Code cleanup complete · ⏸ Sound sourcing + PyInstaller build deferred | `draft_lcu.py` + `cyber.py` deleted. Cyberpunk palette keys + War Room phases + their render functions gone. Settings UI swaps CALM MODE for Audio toggle. `the_rift.spec` updated for `pygame` + `ui.audio` + `ui.lol_theme`. `DRAFT_BOARD.md` rewritten. ~1200 lines of dead code removed from `draft.py` (5704 → 4479). Remaining: source 6 WAVs + run the final PyInstaller build. |

### Phase 2 sub-task ledger

| # | Task | State |
|---|---|---|
| 2.1 | Scout chronology in `analyze_player` | ✅ Done |
| 2.2 | Scout chronology in `write_scouting_sheet` (column M) | ✅ Done |
| 2.3 | Scout chronology parser in `reader.py` | ✅ Done |
| 2.4 | Engine plumbing (scout `results` → `champion_comfort`) + ranked half-life | ✅ Done |
| 2.5 | Scout tab sparkline (RECENT column with colored dots) | ✅ Done |
| 2.6 | New engine helpers (`off_role_severity`, `sample_confidence`, `pool_depth`) + decay integration | ✅ Done |
| 2.7 | COUNTERS rescale to 0.30-0.90 + ~50 2025/26 meta entries (Ambessa, Mel, Aurora, Hwei, Smolder, K'Sante, Briar, Naafiri, Bel'Veth, Sylas, Renata, Senna, Akshan) | ✅ Done |
| 2.8 | `SLOT_ROLE_BIAS` per pro convention + counter-pick gating at R3/B5/R5 + FLEX tightening to `unmatched_open` | ✅ Done |
| 2.9 | `archetype_pivot_check`, `predict_enemy_next_pick`, `pick_impact_delta` helpers | ✅ Done |
| 2.10 | Teamfight `auto_pref` × 1.05 tilt + 3-sentence `game_plan` per archetype | ✅ Done |
| 2.11 | Engine self-test verification (`python -m data.draft_board` from `the_rift/`) | ✅ Done — 20 actions walked, B1→JGL/BOT verified, pivot detection fires on engage-tank ban storm |
| 2.12 | Augment handoff doc | ✅ Done (this section) |

### Phase 1 sub-task ledger

| # | Task | State |
|---|---|---|
| 1.1 | Simplify server protocol (`server/main.py`) | ✅ Done |
| 1.2 | Tune `fly.toml` (autostop_machines = "suspend") | ✅ Done |
| 1.3 | Deploy server to Fly.io | ✅ Done — live at `https://the-rift-draft-sync.fly.dev/` |
| 1.4 | Update client config + sync wrapper | ✅ Done |
| 1.5 | Create `the_rift/ui/lol_theme.py` w/ `draw_waiting_screen` | ✅ Done |
| 1.6 | Refactor `draft.py` IDLE + add CONNECTING phase | ✅ Done |
| 1.7 | Delete `start_sync_host.bat` + `stop_sync_host.bat` | ✅ Done |
| 1.8 | Phase 1 verification (two-client end-to-end) | ⏸ Blocked on 1.3 |

**Build cadence:** No intermediate PyInstaller releases. Per-phase code lands on
master, gated by self-test scripts where possible. Single final build at the end
of Phase 6.

**No fallback to cyberpunk theme** — irreversible. Tagged as a deliberate user
decision.

---

## 1 · Decisions locked in

All answered by the user during planning. Reference these instead of re-asking.

| Decision | Choice |
|---|---|
| Server hosting | **Permanent hosted on Fly.io** (drop `.bat` + ngrok) |
| Pairing model | **Single global room** — first connect = BLUE host, second = RED, **side-swap allowed in lobby** so order can't brick anything |
| Mode UI | **Single 'BEGIN DRAFT' button** — drop BATCH ANALYSIS + DRAFT BOARD LIVE cards |
| Archetype reveal | **Hidden per side** until DONE; engine guesses enemy archetype as draft progresses |
| Pick-order rules | **Hard per-slot role priors + counter-pick gating** (B1 = JGL/ADC, R5 = TOP, R1+R2 = counters, etc.) |
| Counter aggression | **Both — surface earlier + rescale COUNTERS to 0.3-0.9 range + override at R3/B5/R5 when `cv ≥ 0.7`** |
| Pivot trigger | **Combined: viability band drop OR axis killed** (tighter thresholds during enemy phase-1 bans 0-5) |
| UI direction | **LCS/LEC broadcast overlay** — clean navy + gold, splash banners, minimal default, hover-popover detail |
| Ranked recency | **Yes — add chronology to scout sheets** via the existing Commands → Full Scout pipeline (no new Riot API calls; data is already fetched, just thrown away during aggregation) |
| Off-role handling | **Decay comfort + visible warning badge** |
| Snapshot path | **Auto-run as BRIEFING phase at end of team-build**, before archetype pick |
| Reasoning density | **Default minimal + on-hover detail** |
| LCU live import | **Drop entirely** — delete `draft_lcu.py`, drop `board_live` flag |
| Solo flow | **Snapshot only** when no opponent connects within 30s |
| Audio | **`pygame.mixer` from day one** (not `simpleaudio`); 6 subtle UI cues |
| In-draft comms | **None** — Discord covers it |
| Engine extras accepted | **All 4**: pool-depth badge, archetype damage profile preview, enemy probable next pick ghost, sample-size confidence display |
| Research-driven additions | **Featured win-prob number, per-pick impact delta, win-prob progression chart at DONE, game-plan card at DONE** |

---

## 2 · The new gold-path flow

```
   IDLE          CONNECTING      LOBBY            SCOUTING         BRIEFING        ARCHETYPE         BOARD                    DONE
                 (cold-start)                     (NEW PHASE)                       (HIDDEN)
┌─────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌─────────┐       ┌──────────┐            ┌──────────┐
│         │    │ Connecting│   │ BLUE/RED │    │ FETCHING │    │ snapshot │    │ pick 1  │       │ 20-step  │            │ both     │
│ BEGIN   │ →  │ to The   │ → │ swap     │ →  │ SCOUT    │ →  │ projected│ →  │ of 7    │ →     │ tournament│ →         │ archetypes│
│ DRAFT   │    │ Rift     │    │ team-    │    │ DATA     │    │ comps +  │    │ archetypes      │ draft     │  20 acts  │ revealed  │
│ (1 btn) │    │ Server   │    │ build    │    │          │    │ key bans │    │ secret  │       │ live recs │           │ + winner  │
│         │    │ ...      │    │ drag-drop│    │ 7 / 10   │    │ win meter│    │ from    │       │ pivot     │           │ + WR chart│
│         │    │ ◐ ◑ ◒ ◓  │    │ READY    │    │ ████████░│    │          │    │ enemy   │       │ alerts    │           │ + game plan│
└─────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘    └─────────┘       └──────────┘            └──────────┘
```

CONNECTING and SCOUTING share the same waiting-screen primitive (splash-art
background + slow gold rune circle + status text + progress bar).

Solo path: LOBBY shows 30s timer; "Continue solo (briefing only)" link jumps
straight from LOBBY → BRIEFING → DONE without entering draft sequence.

---

## 3 · Architectural pillars

1. **Server.** Permanent Fly.io endpoint, `wss://the-rift-draft.fly.dev` (or
   chosen Fly app name). URL baked into `the_rift/data/config.py`. No `.bat`,
   no ngrok, no codes, no passwords. Single global room.
2. **Pairing.** First connect = BLUE host, second = RED, third+ = SPECTATOR.
   Side picker in LOBBY lets either party swap freely until both ready.
3. **Theme.** LCS/LEC broadcast aesthetic. All `ui/cyber.py` references
   (135 hits in `draft.py`, plus all of `board_rail.py`) get replaced with new
   `ui/lol_theme.py` primitives. `cyber.py` deleted in Phase 6.
4. **Flow.** 8 phases:
   `IDLE → CONNECTING → LOBBY → SCOUTING → BRIEFING → ARCHETYPE → BOARD → DONE`.
5. **Engine.** Hard slot-role priors, counter-pick gating at R3/B5/R5,
   off-role-severity decay, rescaled COUNTERS table (0.3-0.9, +~50 entries for
   2025/2026 meta), archetype-pivot detection (sensitive during phase-1 bans),
   ranked recency via scout-script chronology emission.
6. **Audio.** `pygame.mixer` from day one. 6 short WAV/OGG files in
   `the_rift/assets/sounds/`.
7. **Build cadence.** No intermediate PyInstaller builds. Single final build in
   Phase 6.

---

## 4 · Phase-by-phase work breakdown

### Phase 1 — Fly.io server + auto-connect + waiting screen ([target: 2 days])

| File | Change |
|---|---|
| [server/main.py](server/main.py) | Drop password requirement on `get_or_create_room`. Replace per-room model with single hard-coded `"global"` room. Drop `set_slot` (sides only: BLUE/RED/SPEC). Add `set_side` (swap allowed pre-`started`). Add `set_archetype` with `hidden: True` (server stores per-side, broadcasts ONLY at `done`). Add `set_ready` and gate `start_draft` on both readys. Add `archetype_pivot` derived broadcast. Add `scout_status` broadcast for SCOUTING screen progress. |
| [server/fly.toml](server/fly.toml) | Verify region + `autostop_machines = "suspend"` (NOT `"stop"`) so cold start is ~1-2s, not 5s. |
| [server/Dockerfile](server/Dockerfile) | Verify Python deps for production. |
| `start_sync_host.bat`, `stop_sync_host.bat` | **Delete.** |
| [the_rift/data/config.py](the_rift/data/config.py) | Replace ngrok URL with `wss://the-rift-draft.fly.dev` (final URL TBD on deploy). Drop legacy `last_room`, `last_name`, `last_slot` from `sync` config. |
| [the_rift/data/draft_sync.py](the_rift/data/draft_sync.py) | Drop `room` and `password` from `connect()`. Add `set_side(side)`, `set_archetype(arch, hidden=True)`, `set_ready(bool)`. Expose connection-state callbacks for CONNECTING waiting screen. |
| [the_rift/ui/lol_theme.py](the_rift/ui/lol_theme.py) | **NEW (started here, fully expanded in Phase 3).** First widget: `draw_waiting_screen(dl, vw, vh, status_text, progress_0_1)` — used by CONNECTING and SCOUTING. |
| [the_rift/ui/draft.py](the_rift/ui/draft.py) | IDLE phase becomes single big "BEGIN DRAFT" button (centered, splash-art bg). CONNECTING phase added between IDLE and LOBBY — fires `auto_connect()` on click, shows `draw_waiting_screen` until server hello received. |

**Verification gate:** Two clients can connect to Fly.io URL, see each other,
swap sides, see same roster state. No code/password anywhere.

---

### Phase 2 — Engine rewrite + scout chronology + Scout tab safety ([target: 14 days])

#### Scout-script chronology pipeline (data is already fetched, just preserve it)

| File | Change | LOC |
|---|---|---|
| [the_rift/data/fetch_ranks_gsheets.py](the_rift/data/fetch_ranks_gsheets.py:642) `analyze_player` | In `champ_stats[name]` aggregation loop, add `results: []` per champ. Append `1 if m["win"] else 0` each iteration (matches already in chronological order from `fetch_scouting_matches`). Emit `results` on each `champ_list` entry. | ~10 |
| [the_rift/data/fetch_ranks_gsheets.py](the_rift/data/fetch_ranks_gsheets.py:897) `write_scouting_sheet` FULL CHAMPION POOL block | (a) `pad([...])` width grows to 13 cols A:M. (b) Header row appends `"Results"`. (c) Each champ row appends `",".join(str(r) for r in c["results"])`. (d) Existing A:L formatting/merges unchanged — column M plain text. | ~15 |
| [the_rift/data/reader.py](the_rift/data/reader.py:1515) `_parse_scouting_sheet` FULL CHAMPION POOL parser | Read `_cell(r, 12)` as string. Non-empty → split on `,`, cast to `int`, store as `results: [1,0,1,...]`. Absent → `results: []` (fallback so older sheets still work). | ~8 |
| [the_rift/data/draft_engine.py](the_rift/data/draft_engine.py:851) `_player_candidates` scout-pool path | Pass `results=ch.get("results")` to `champion_comfort`. | ~3 |
| [the_rift/data/draft_engine.py](the_rift/data/draft_engine.py:1120) `recommend_bans` scout-pool path | Same — pass `results` for ranked threat scoring. | ~3 |
| [the_rift/ui/scout.py](the_rift/ui/scout.py:468) `_rw_full_champ_pool` | **NO BREAK** — reads named keys, ignores new `results` key. **BONUS:** add a "RECENT" column rendering last 10 `results` as colored dots (gold = win, dim = loss). Empty if no chronology (old sheets). | 0 (or ~30) |

**Backward compat:** Empty `results` is the no-op state. Players whose scout
sheet hasn't been regenerated since the change still work — they just don't get
the recency boost on ranked champs.

#### Engine improvements

| File | Change |
|---|---|
| [the_rift/data/draft_engine.py](the_rift/data/draft_engine.py) | **`off_role_severity(player, role, inhouse, scout) → 0..1`** — uses customs `roles` breakdown + scout role data. Comfort decayed by `(1 - 0.4·severity)`. **COUNTERS rescale + expansion:** sweep entries to 0.3-0.9 range; add ~50 entries for Ambessa, Mel, Aurora, Hwei, Smolder, K'Sante, Briar, Naafiri, etc. **`recency_weighted_wr` extended:** accept ranked `results` with `half_life=24` games (vs 18 for customs). **Slight teamfight tilt:** `Teamfight` archetype's auto-recommend score × 1.05. **`sample_confidence(games) → "thin"/"ok"/"strong"`** returned in factors dict. **`pool_depth(player, role, inhouse, scout) → "DEEP"/"OK"/"SHALLOW"/"OFF-ROLE"`** helper for the team-builder badge. |
| [the_rift/data/draft_board.py](the_rift/data/draft_board.py) | **`SLOT_ROLE_BIAS: Dict[int, Dict[str, float]]`** — per-action-index role weights matching pro convention. Multiply pick-suggestion scores by `SLOT_ROLE_BIAS[a.idx].get(role, 1.0)`. **Counter-pick gating at R3/B5/R5:** when `cv ≥ 0.7`, score blend becomes `0.65·cv + 0.20·cmf + 0.15·lane`. **FLEX tag tightening:** require `≥2 of open_roles have no locked enemy in same role`. **`archetype_pivot_check(state, side, current_arch, scout) → {wrecked, reason, pivot_options, severity}`**. Phase-1 sensitivity: actions 0-5 use tighter thresholds. **`predict_enemy_next_pick(state, scout) → (champ, role, confidence)`**. **`pick_impact_delta(before, after) → float`** (WR swing per pick). |

#### SLOT_ROLE_BIAS reference table (pro convention)

```
B1   (idx 6) :  JGL 1.30, BOT 1.25, MID 1.10, SUP 0.95, TOP 0.85   # flex/safe blind pick
R1   (idx 7) :  counter B1's lane × 1.30, others 1.00
R2   (idx 8) :  counter B1's lane × 1.20, secure own carry × 1.15
B2   (idx 9) :  MID 1.20, ADC 1.15, JGL 1.10, TOP 0.95, SUP 0.95
B3   (idx 10):  SUP 1.20, TOP 1.10, others 1.00                    # hide TOP if possible
R3   (idx 11):  TOP 1.25 (counter B's TOP if shown), MID/SUP 1.10  # last pick of round 1
R4   (idx 16):  SUP 1.30, BOT 1.10, others 0.95                    # start of round 2 — usually SUP
B4   (idx 17):  SUP 1.25, TOP 1.10, others 0.95
B5   (idx 18):  TOP 1.30, SUP 1.20, others 0.85
R5   (idx 19):  TOP 1.45 (last pick top counter is canonical)
```

Ban-phase slots (idx 0-5, 12-15): no role bias — ban scoring uses
`ROLE_BAN_WEIGHT` separately.

**Verification gate:** `python -m the_rift.data.draft_board` self-test —
B1 should prefer JGL/ADC; R5 should prefer TOP; off-role TOP-slotted-JGL
should score 0.4-0.6× normal; phase-1 pivot test with engage tank banned
should flag Teamfight archetype as wrecked.

---

### Phase 3 — LCS/LEC theme + full UI rewrite ([target: 21 days, largest phase])

| File | Change |
|---|---|
| [the_rift/ui/lol_theme.py](the_rift/ui/lol_theme.py) | **Full primitive set.** `draw_navy_panel`, `draw_gold_rule`, `draw_splash_banner` (full-bleed splash w/ darkening vignette), `draw_role_glyph` (TOP/JGL/MID/BOT/SUP marks), `draw_pick_chip`, `draw_ban_chip`, `draw_player_portrait_frame` (tier-tinted gold border), `draw_arc_meter` (win-prob gauge), `draw_archetype_card`, `draw_waiting_screen`, `draw_progress_bar`, `draw_pivot_alert_banner`, `draw_ghost_suggestion_chip`, `draw_sample_size_badge`, `draw_pool_depth_badge`, `draw_recent_form_dots` (for Scout tab sparkline). |
| [the_rift/ui/cyber.py](the_rift/ui/cyber.py) | **Delete in Phase 6**, but stop using it from any new code in Phase 3. |
| [the_rift/theme.py](the_rift/theme.py) | Remove cyberpunk palette keys (`cy_*`, `mg_*`, `term_g`, `alert_r`, `scan_gy`, `panel_dk`, `grid_a`). Add `navy_deep` (#0a1428), `navy_mid` (#091428), `gold_rule` (#785a28), `gold_lt2` (#cdbe91) — LoL official palette. |
| [the_rift/ui/draft.py](the_rift/ui/draft.py) | **Major rewrite.** New `DraftPhase` enum: `IDLE / CONNECTING / LOBBY / SCOUTING / BRIEFING / ARCHETYPE / BOARD / DONE`. Each phase has a dedicated `_draw_<phase>` function. All 135 `cyber.*` calls replaced. LOBBY = team builder + side toggle + READY-UP per side. SCOUTING = waiting screen with per-player progress bar. BRIEFING = auto-shows snapshot card for 5s then advance. ARCHETYPE = per-side hidden screen, 7 cards w/ damage preview. BOARD = broadcast aesthetic, splash banners, gold rules, minimal-default w/ hover popover, pool-depth + sample-size badges, pivot alert banner, ghost suggestion chip, per-pick impact delta overlay. DONE = both archetypes revealed, win-prob progression chart, game plan card per side, "what got banned" retrospective. |
| [the_rift/ui/board_rail.py](the_rift/ui/board_rail.py) | Rewrite using `lol_theme` primitives. Featured win-prob number (big, top-center). Minimal cards w/ tag + 1-line `why`. Hover → full factor breakdown popover. Cohesion alerts (`No frontline`, `No engage`) as orange-tinted callouts at top. |
| [the_rift/ui/draft_sync_ui.py](the_rift/ui/draft_sync_ui.py) | Delete `show_join_dialog`. Replace with `auto_connect()` called from BEGIN DRAFT. Adapt `presence_text`, `can_act` to new server protocol. |

---

### Phase 4 — Archetype screens + pivot + ghost suggestions ([target: 4-5 days])

| File | Change |
|---|---|
| [the_rift/ui/draft.py](the_rift/ui/draft.py) `_draw_archetype` | 7-card grid sorted by viability for THIS side's roster. Card: archetype, viability band, AP/AD damage profile bars, 5 projected picks, win condition, spike. CONFIRM locks. Footer ribbon shows engine's guess at enemy archetype (visible only on your screen). |
| [the_rift/data/draft_board.py](the_rift/data/draft_board.py) | After every action, run `archetype_pivot_check` (server-side derivation). Broadcast `pivot_alert` to affected side. |
| [the_rift/ui/draft.py](the_rift/ui/draft.py) | Pivot alert banner slides in: "⚠ Enemy banned {champ} — your {Teamfight} comp drops to WEAK. Pivot to {Pick} or {Dive}?". Two big buttons commit new archetype via `set_archetype`. **Archetype-swap allowed any time during BOARD**, not just ARCHETYPE phase. |
| [the_rift/ui/draft.py](the_rift/ui/draft.py) | Ghost suggestion chip during enemy turns — translucent chip showing `predict_enemy_next_pick` top result. Fades on actual lock. |

---

### Phase 5 — Audio + DONE polish + solo fallback ([target: 3-4 days])

| File | Change |
|---|---|
| [the_rift/ui/audio.py](the_rift/ui/audio.py) | **NEW.** `pygame.mixer` wrapper. Init at app startup. `play_lock()`, `play_ban()`, `play_turn()`, `play_archetype()`, `play_pivot()`, `play_draft_end()`. Non-blocking. Mute toggle in settings. |
| `the_rift/assets/sounds/` | **NEW.** 6 short WAV/OGG (~300 KB total): `lock.wav`, `ban.wav`, `turn_chime.wav`, `archetype_stinger.wav`, `pivot_alert.wav`, `draft_complete.wav`. Royalty-free source (Freesound CC0). |
| [the_rift/data/config.py](the_rift/data/config.py) | Add `audio_enabled = True`. Drop `calm_mode` (cyberpunk artifact). |
| [the_rift/ui/draft.py](the_rift/ui/draft.py) `_draw_done` | Final summary panel: win-prob progression chart (uses existing `_cache["history"]` from board_rail), game-plan card per side (rendered from archetype `win_condition` + `spike` + new ~3-sentence concrete-actions string added to ARCHETYPES dict), "what got banned" panel showing which of each side's top-3 projected picks per role were removed by the enemy. |
| [the_rift/ui/draft.py](the_rift/ui/draft.py) | Solo fallback: LOBBY shows "Waiting for opponent…" + 30s countdown + "Continue solo (briefing only)" link. Skips to BRIEFING → DONE without entering draft sequence. |

---

### Phase 6 — LCU drop + cleanup + final build ([target: 1-2 days])

| File | Change |
|---|---|
| [the_rift/data/draft_lcu.py](the_rift/data/draft_lcu.py) | **Delete.** |
| [the_rift/ui/draft.py](the_rift/ui/draft.py) | Remove all references to `board_live`, `_lcu_poll_loop`, `board_live_session`, `board_live_status`, `board_live_stop`, `_board_live_sig`. |
| [the_rift/ui/cyber.py](the_rift/ui/cyber.py) | **Delete.** |
| [DRAFT_BOARD.md](DRAFT_BOARD.md) | Rewrite spec to match new flow, new phases, new theme module. |
| `build_merger.py`, `LoLPowerRankings.spec` | Ensure `sounds/`, `lol_theme.py`, and `pygame` bundled correctly. |
| **PyInstaller build** | **Single end-of-project build per user request.** |

---

## 5 · Engine extras + research-driven additions

| Feature | Phase | Lives in |
|---|---|---|
| **Champion-pool depth badge** on team-builder slots | 2 + 3 | `draft_engine.pool_depth` + `lol_theme.draw_pool_depth_badge` |
| **Per-archetype damage profile preview** | 4 | `draw_archetype_card` includes AP/AD bar chart |
| **Live enemy probable next pick ghost** | 2 + 4 | `draft_board.predict_enemy_next_pick` + `lol_theme.draw_ghost_suggestion_chip` |
| **Sample-size confidence display** | 2 + 3 | `draft_engine.sample_confidence` + `lol_theme.draw_sample_size_badge` |
| **Featured win-prob number** (big, top-center) | 3 | `board_rail.py` header |
| **Per-pick impact delta** | 2 + 3 | `draft_board.pick_impact_delta` + floating overlay on each lock |
| **Win-prob progression chart** at DONE | 5 | Uses existing `_cache["history"]` |
| **Game plan card** at DONE | 5 | New `game_plan` field on ARCHETYPES dict |
| **Cohesion alerts** prominent | 3 | Orange-tinted callouts top of right rail |
| **Recent-form sparkline** on Scout tab | 2 | Optional bonus from new chronology data |

---

## 6 · Risks (current + resolved)

| # | Risk | Status |
|---|---|---|
| 1 | Scout-script Riot API quota | ✅ **Resolved** — user clarified: data is fetched once via Commands → Full Scout; we just preserve chronology that's already in memory. Zero new API calls. |
| 2 | Fly.io scale-to-zero cold start (~3-5s) | Mitigated by `autostop_machines = "suspend"` (~1-2s) + CONNECTING waiting screen |
| 3 | `pygame.mixer` + PyInstaller bundling | Needs verification at final build; well-established pattern |
| 4 | No intermediate builds → late discovery of regressions | Mitigated by per-phase self-test scripts (`python -m the_rift.data.draft_board`) |
| 5 | Cyberpunk delete is permanent | Acknowledged by user; no rollback path |

---

## 7 · Key files (orientation map)

| Layer | Path | LOC | Role |
|---|---|---|---|
| Server | [server/main.py](server/main.py) | ~400 | FastAPI WebSocket sync server |
| Server | [server/fly.toml](server/fly.toml) | ~30 | Fly.io deployment config |
| Engine | [the_rift/data/draft_engine.py](the_rift/data/draft_engine.py) | 1397 | Pure-Python champion + scoring tables |
| Board state | [the_rift/data/draft_board.py](the_rift/data/draft_board.py) | 1191 | 20-action sequence + `recommend_action` |
| Sync client | [the_rift/data/draft_sync.py](the_rift/data/draft_sync.py) | 346 | WebSocket client |
| Sheets I/O | [the_rift/data/reader.py](the_rift/data/reader.py) | 2386 | Google Sheets parsing |
| Scout script | [the_rift/data/fetch_ranks_gsheets.py](the_rift/data/fetch_ranks_gsheets.py) | ~2500 | Commands → Full Scout backend |
| LCU adapter | [the_rift/data/draft_lcu.py](the_rift/data/draft_lcu.py) | 302 | **DELETE in Phase 6** |
| Config | [the_rift/data/config.py](the_rift/data/config.py) | ~143 | Settings |
| Draft UI | [the_rift/ui/draft.py](the_rift/ui/draft.py) | 4830 | **Major rewrite Phase 3** |
| Right rail | [the_rift/ui/board_rail.py](the_rift/ui/board_rail.py) | 564 | **Rewrite Phase 3** |
| Sync bridge | [the_rift/ui/draft_sync_ui.py](the_rift/ui/draft_sync_ui.py) | ~475 | Adapt Phase 3 |
| Cyberpunk | [the_rift/ui/cyber.py](the_rift/ui/cyber.py) | ~ | **DELETE Phase 6** |
| Scout tab | [the_rift/ui/scout.py](the_rift/ui/scout.py) | ~ | Bonus sparkline in Phase 2 |
| Commands tab | [the_rift/ui/commands.py](the_rift/ui/commands.py) | ~600 | Unchanged (button still runs `--scout`) |
| Theme | [the_rift/theme.py](the_rift/theme.py) | ~200 | Palette swap Phase 3 |
| New theme | [the_rift/ui/lol_theme.py](the_rift/ui/lol_theme.py) | 0 | **NEW Phase 1 (start) + Phase 3 (expand)** |
| New audio | [the_rift/ui/audio.py](the_rift/ui/audio.py) | 0 | **NEW Phase 5** |
| Spec doc | [DRAFT_BOARD.md](DRAFT_BOARD.md) | ~560 | Update Phase 6 |

---

## 8 · User preferences / rules specific to this work

These come from `memory/MEMORY.md` and direct user statements during planning.
A future Claude session must honor them.

- **Work in the main directory**, not `.claude/worktrees/*` (per
  `feedback_worktree_preference.md`).
- **Don't push to GitHub or tag releases** until the user has verified the
  build works (per `feedback_no_push_before_verify.md`). For this rewrite
  specifically the user has **explicitly overridden the per-phase rebuild
  rule** — no intermediate builds, single PyInstaller build at end of
  Phase 6 only.
- **Background motion** should be minimal (per `feedback_ambient_motion.md`).
  No full-screen scanlines or grid drift in the new theme. Focal motion only
  (splash banner crossfades, archetype-card hover lift, pick-lock pulse).
- **No reverting to cyberpunk** regardless of how the new theme lands.
  Explicit user decision.

---

## 9 · Change log

> Append a one-line entry per meaningful change. Format:
> `YYYY-MM-DD — Phase N — [what changed] — [files touched]`

- 2026-05-19 — Plan locked, handoff doc created — `DRAFT_REWRITE_HANDOFF.md` (this file)
- 2026-05-19 — Phase 1.1 — Rewrote server protocol: single global room, no codes/passwords, sides (BLUE/RED/SPEC) replace slots, added set_side/set_ready/set_scout_ready/set_briefing_done/set_archetype, phase machine (LOBBY→SCOUTING→BRIEFING→ARCHETYPE→BOARD→DONE), personalised state per side for archetype info-asymmetry — `server/main.py`
- 2026-05-19 — Phase 1.2 — Tuned fly.toml: `auto_stop_machines = "suspend"` for ~1-2s cold start (was ~5s); updated header docs — `server/fly.toml`
- 2026-05-19 — Phase 1.4 — Rewrote `draft_sync.py` for new protocol: `connect(url, name)` (no room/password), new ops (set_side/set_ready/set_scout_ready/set_briefing_done/set_archetype), connection-state callbacks (on_connecting/on_connected/on_disconnected) — `the_rift/data/draft_sync.py`
- 2026-05-19 — Phase 1.4 — Updated `config.py`: replaced ngrok URL with `wss://the-rift-draft.fly.dev`; dropped legacy `last_room`/`last_name`/`last_slot`; added top-level `display_name` and `audio_enabled`; dropped `calm_mode` cyberpunk artifact — `the_rift/data/config.py`
- 2026-05-19 — Phase 1.4 — Rewrote `draft_sync_ui.py` for new protocol: `auto_connect(name)` replaces `show_join_dialog()`, side-based gating instead of slot-based, phase predicates (`in_lobby` / `in_scouting` / `in_briefing` / `in_archetype` / `is_done`), `send_set_ready` and friends, sides_summary replaces slots_summary, legacy shims kept for transitional callsites — `the_rift/ui/draft_sync_ui.py`
- 2026-05-19 — Phase 1.5 — Created `lol_theme.py` w/ `draw_waiting_screen` primitive: full-bleed navy backdrop + slow-rotating gold rune ring + status text + subtitle + optional progress bar. LOL palette dict defined. Phase 3 will expand this module with full primitive set — `the_rift/ui/lol_theme.py` (NEW)
- 2026-05-19 — Phase 1.6 — Replaced 3-mode-card IDLE with single BEGIN DRAFT button; added CONNECTING phase using `lol_theme.draw_waiting_screen`; new `_on_lobby_join` callback transitions to TEAM_BUILD (LOBBY) instead of straight to BOARD; added `_sync_phase_watcher()` per-frame to follow server phase machine (TEAM_BUILD → BOARD when server advances); team-builder side toggle now broadcasts `set_side` in synced mode; START button calls `set_ready` instead of `start_draft` in synced mode; team-builder mirrors `my_side()` into local `_tb.board_side` for visual consistency — `the_rift/ui/draft.py`
- 2026-05-19 — Phase 1.7 — Deleted `start_sync_host.bat` and `stop_sync_host.bat` — manual hosting workflow retired
- 2026-05-19 — Phase 1 syntax check: `python -m py_compile` on all 6 modified files = ALL OK
- 2026-05-19 — Phase 1.3 — flyctl installed via winget (v0.4.53). Fly auth completed (`blheidel4@gmail.com`). App `the-rift-draft-sync` registered on personal org. **Deploy BLOCKED on Fly.io depot-builder outage (503).** Fly status page shows ongoing dashboard incident — wait for recovery and retry. Fixed config.py URL typo: `the-rift-draft.fly.dev` → `the-rift-draft-sync.fly.dev` to match registered app.
- 2026-05-20 — Phase 1.3 — Fly recovered after ~1hr outage. **Deploy succeeded.** Server live at `https://the-rift-draft-sync.fly.dev/`. Image 49 MB, single machine in iad, suspend-on-idle. Verified: `/health` → `{"ok":true}`, `/` → `{"service":"the-rift-draft-sync","version":"2.0.0","clients":0,"phase":"LOBBY"}`. Scaled down from default 2-machine HA to 1 machine to avoid split-brain on in-memory Room singleton (`fly scale count 1`).
- 2026-05-20 — Phase 2.1-2.5 — **Scout chronology pipeline.** `analyze_player` preserves per-game results during aggregation (newest-first, reversed at emit to oldest→newest). `write_scouting_sheet` emits "Results" column M with comma-joined chronology. `_parse_scouting_sheet` parses M into `results: [1,0,...]`. Engine path passes `results` through `champion_comfort` (scout-pool uses `recency_half_life=24` vs customs `18`, and `recency_weight=0.55` vs customs `0.65`). Scout tab `_rw_full_champ_pool` gains a RECENT column rendering last 10 dots (gold=win, dim red=loss). Older sheets without column M fall back gracefully via `results=None`/`[]` so engine + tab keep working. — `fetch_ranks_gsheets.py`, `reader.py`, `draft_engine.py`, `ui/scout.py`
- 2026-05-20 — Phase 2.6 — **Off-role + pool-depth + sample-size helpers.** New `off_role_severity(player, role, inhouse, primary, scout) → 0..1` with tiers (0.0 on-primary, 0.20 has-mixed-customs, 0.45 limited, 0.65 thin, 0.90 severe). Comfort decayed by `(1 - 0.40*sev)` inside `_player_candidates`. New `pool_depth → "DEEP"/"OK"/"SHALLOW"/"OFF-ROLE"` for the team-builder badge. New `sample_confidence(games) → "thin"/"ok"/"strong"` for the UI badge. — `draft_engine.py`
- 2026-05-20 — Phase 2.7 — **COUNTERS rescale + 2026 meta.** Stretched all entries from 0.10-0.50 to 0.30-0.90 via `new = 0.30 + (old - 0.10) * 1.5`. Added ~45 entries for current meta (Ambessa, Mel, Aurora, Hwei, Smolder, K'Sante, Briar, Naafiri, Bel'Veth, Sylas, Renata Glasc, Senna, Akshan). Normalisers in `counter_value` and `blind_safety` bumped in lockstep (`/ 0.9`, `/ 1.4` etc.) so `cv` and `bs` still land 0..1. `recommend_bans_split` "counters your X" reason threshold lifted from 0.20 → 0.45 to match the new "solid counter" tier. — `draft_engine.py`, `draft_board.py`
- 2026-05-20 — Phase 2.8 — **Pro-convention pick-order bias + counter-pick gating + FLEX tightening.** New `SLOT_ROLE_BIAS: Dict[int, Dict[str, float]]` per pro-draft convention (B1 favors JGL/BOT 1.30/1.25; R5 favors TOP 1.45; B5 favors TOP/SUP; etc.). Bias multiplies the per-candidate score after the existing blend. New `COUNTER_PICK_SLOTS = {11, 18, 19}` (R3/B5/R5); at those slots when same-lane enemy is locked AND `cv ≥ 0.70`, the score blend becomes `0.65·cv + 0.20·cmf + 0.15·lane` so hard counters dominate comfort. FLEX tag tightened to require ≥2 of *unmatched* open roles (no enemy locked in same role yet) — fixes "flex mid/top when both enemy mid+top locked". New `factors` dict surfaces `flex_unmatched`, `slot_bias`, `confidence`, `off_role` for the UI. — `draft_board.py`
- 2026-05-20 — Phase 2.9 — **Pivot + predict + impact-delta helpers.** New `archetype_pivot_check(state, side, current_arch, inhouse, primary, scout) → {wrecked, reason, severity, pivot_options, viability_now}` — fires on viability-band drop OR key-axis killed; phase-1 sensitivity tightens threshold during enemy bans 0-5. New `predict_enemy_next_pick(state, inhouse, primary, scout) → {champion, role, player, confidence, action_idx}` for the ghost-suggestion chip. New `pick_impact_delta(before, after, side, ...) → float` returning the win-meter swing per pick. — `draft_board.py`
- 2026-05-20 — Phase 2.10 — **Teamfight tilt + game_plan strings.** Each archetype gained `auto_pref` multiplier (Teamfight ×1.05, all others ×1.00) applied to `recommend_comps` totals — reflects front-to-back being the dominant pro-play archetype. Each archetype gained a 3-sentence `game_plan` string for the DONE-screen briefing in Phase 5. — `draft_engine.py`
- 2026-05-20 — Phase 2.11 — **Self-test verified.** `python -m data.draft_board` (run from `the_rift/` so the package-local `from data import draft_engine` resolves) walks all 20 actions cleanly. Custom verification: B1 (idx 6) top-5 suggestions = JGL/BOT/SUP only, no TOP; pivot check on Teamfight after banning 6 engage tanks correctly reports `wrecked=True severity=0.85 viability_now=WEAK pivot_options=[Pick, Dive]`; `predict_enemy_next_pick` returns a champion + confidence for the upcoming enemy slot. All Phase 2 syntax checks clean.
- 2026-05-19 — Phase 3.1 — **lol_theme.py primitive expansion.** Full primitive set added beyond the Phase 1 waiting screen: `draw_navy_panel`, `draw_gold_rule`, `draw_splash_banner` (champion splash bg + vignette + side accent strip + title/subtitle), `draw_role_glyph` (TOP/JGL/MID/BOT/SUP marks), `draw_progress_bar`, `draw_player_portrait_frame` (tier-tinted gold ring), `draw_pick_chip`, `draw_ban_chip` (with strikethrough), `draw_sample_size_badge` (thin/ok/strong), `draw_pool_depth_badge` (DEEP/OK/SHALLOW/OFF-ROLE), `draw_recent_form_dots` (last-N w/l dots), `draw_ghost_suggestion_chip` (enemy probable-next-pick), `draw_arc_meter` (180° win-prob gauge), `draw_archetype_card` (AP/AD bar + projected picks + win-cond + spike), `draw_pivot_alert_banner` (severity-tinted warning w/ two pivot buttons; returns btn rects for click hit-testing). Helpers: `_alpha`, `_text`, `_text_centered`, `_now`. Palette dict `LOL` (navy_deep/mid/panel/lt, gold/lt/dk/rule, txt/dim/faint, blue_side/dk, red_side/dk, win/loss/warning, stripe). `LOL_TIER_RING` + `SIDE_ACCENT` lookups. — `the_rift/ui/lol_theme.py`
- 2026-05-19 — Phase 3.2 — **theme.py palette extension.** Added LoL-client palette keys additively (`navy_deep`, `navy_mid`, `gold_rule`, `gold_lt2`) without touching the existing Direction A keys. Cyberpunk keys (`cy_*`/`mg_*`/`term_g`/`amb`/`alert_r`/`scan_gy`/`panel_dk`/`grid_a`) flagged **DEPRECATED in Phase 3**; Phase 6 prunes them when `cyber.py` is deleted. — `the_rift/theme.py`
- 2026-05-19 — Phase 3.3 — **IDLE + CONNECTING phases converted to LoL primitives.** IDLE renders `draw_splash_banner` (full-bleed) under a centered `draw_navy_panel` with the single BEGIN DRAFT button (gold-bordered when hot). Mode-pick row beneath uses `draw_navy_panel` with hover lift. CONNECTING uses `draw_waiting_screen` (slow-rotating gold rune + status + subtitle) for the Fly.io handshake. — `the_rift/ui/draft.py`
- 2026-05-19 — Phase 3.4 — **LOBBY screen fully de-cybered.** `_draw_sync_lobby` swapped to lol_theme: solid navy_deep background (no grid drift, per ambient-motion feedback), navy_mid header strip with gold_rule divider, gold_lt2 "DRAFT LOBBY" header in Cinzel, red-bordered EXIT button, blue/red SIDE_ACCENT colors on the WHO'S CONNECTED rail + roster boxes, gold-rule horizontal dividers, gold-bordered "READY UP" CTA (rename from "START DRAFT" per Phase 1 verification note). `_draw_tb_card` (player pool card) swapped to LOL palette (navy_panel fill, gold_lt name, txt_dim score — kept the tier-color rank-pulse focal motion). `_draw_tag_chip` swapped to plain rounded rect (no corner-cut). `_draw_arch_picker` swapped to plain rounded rect chips. — `the_rift/ui/draft.py`
- 2026-05-19 — Phase 3.5 — **Solo team-builder + side accent globals swapped to LoL.** `_draw_team_builder_full` palette swept to LOL (navy_deep bg, navy_mid header, gold_lt CONFIGURE TEAMS title in Cinzel, gold-bordered action button, gold_rule-bordered toggles/cancel, blue_side/red_side column tints). `_draw_role_slots` same. Globals `BLUE_ACCENT`/`BLUE_ACCENT_LT`/`RED_ACCENT`/`RED_ACCENT_LT` repointed at `LOL["blue_side_dk"/"blue_side"/"red_side_dk"/"red_side"]` so the board's side coloring shifts from cyan/magenta to LCS broadcast blue/red without touching individual board callsites. — `the_rift/ui/draft.py` (cyber refs 71→59)
- 2026-05-19 — Phase 3.6 — **Draft board chrome swept to LoL.** `_draw_board` background swapped from `draw_grid_bg` (no drift) to a solid `navy_deep` fill. Resize-viewport prompt is now plain warning text. Header rebuilt: `navy_mid` strip + `gold_rule` divider + Cinzel "DRAFT BOARD" title, blue/red/win/warning status pills. UNDO + EXIT buttons rebuilt with `draw_navy_panel` (gold border for UNDO; red border for EXIT). Timeline strip rebuilt: phase labels in gold, gold dividers between phases, gold underline baseline, action cells switched from `cyber.draw_cut_rect` + `draw_marching_dash` to plain rounded `dpg.draw_rectangle` with a focal pulse on the on-the-clock cell. Full-screen scanline overlay deleted entirely. `_panel_bg` helper simplified to a single rounded navy panel + gold-rule border (the `cut=True` corner-cut style is gone in v3). — `the_rift/ui/draft.py` (cyber refs 59→46)
- 2026-05-19 — Phase 3.7 — **Draft board team panels swept to LoL.** `_draw_board_team` rebuilt: callsign now plain raj_sb text in side accent; on-the-clock cursor uses LOL["win"] instead of `term_g`; per-player slots use `lol_theme._alpha(navy_panel)` fill with side-accent or `gold_rule` border (no more corner-cut, no more scanline strip on the role tag); empty-portrait placeholder backed by `navy_deep`; pool-depth capsule uses `win`/`warning`/`loss` instead of `term_g`/`amb`/`alert_r`; BANS row label is plain `red_side` text; ban-slot rects are rounded with `red_side_dk` borders. Enemy "LIKELY NEXT" ribbon swapped to navy panel + side-accent rectangle borders + plain "LIKELY NEXT" label (no bracket label, no marching dash). — `the_rift/ui/draft.py` (cyber refs 46→35)
- 2026-05-19 — Phase 3.8 — **Draft board center panel swept to LoL.** `_draw_board_center` fully converted: gradient frame uses `gold_lt`/`gold_rule` instead of cyan; `_panel_bg` accent passed as `LOL["gold"]`; DRAFT COMPLETE end-state uses Cinzel + gold-bordered NEW DRAFT button. Action banner: gold = our turn, red_side = opponent turn (replaces cyan/magenta), focal shimmer kept on our-turn border. Strategic readout panel rebuilt: navy_deep fill + gold_rule border + plain "TACTICAL READOUT" caption + side-accent stripes + red_side `[ ENEMY ]` callout. Context-line sigils kept (›/!/+) tinted with txt_dim / warning / win. PRIMARY CALL hero card: tag-color rounded rect (no corner-cut), splash ken-burns scrim now `navy_deep`, plain "TOP CALL" caption with gold underline (no bracket-label, no marching dash), confidence meter renders as rounded bar with gold-rule border, viability chip is plain rounded rect. Champion name typewriter reveal kept (focal motion, always on). Identity-vector chips use `gold_dk`/`gold` instead of `cy_dk`/`cy`. ALTERNATIVES rows rebuilt with `navy_panel` fill + tag-color border + tag-color vertical stripe. Manual pool search box rebuilt with `navy_deep` fill + `gold_rule` border + gold prompt arrow `›`. Champion grid cells are rounded with gold-hover borders. Scrollbar uses gold tones. Last `cyber.motion_on()` (ken-burns gate) replaced with always-on focal motion. Three `cyber.set_motion` calls in `_lobby_begin_synced`/`_board_begin_synced`/`_board_begin` removed (no global motion flag in v3 aesthetic). **`from ui import cyber` import dropped from draft.py.** — `the_rift/ui/draft.py` (cyber refs 35→0; only 3 comment mentions remain)
- 2026-05-19 — Phase 3.9 — **board_rail.py fully de-cybered.** `_panel` helper now renders a rounded `draw_navy_panel` with a plain gold title (no corner-cut, no bracket label). `_bar` is a rounded `dpg.draw_rectangle`. `_w_winprob` bar split is `blue_side` ↔ `red_side` (replaces cyan/magenta); sparkline draws in `gold_lt`; midline in `gold_rule`. `_WHY_ROWS` re-keyed to LOL palette keys (`gold_lt` / `win` / `warning` / `blue_side`). `_w_breakdown` LANE deviation bar uses `win` (positive) / `red_side` (negative). `_w_radar` rings + axes in `gold_rule`; legend pills in `blue_side`/`red_side`; team polygons in same. `_w_coverage` donut uses `win`/`gold_rule`. `_w_damage` segments use AP magenta-ish / `warning` AD / light-gray TR with `navy_deep` text fallback. `_w_contested` status colors: BANNED `red_side`, PICKED `warning`, FREE `win`. `_w_synergy` synergies in `win`, anti-synergies in `red_side`, nodes use `gold_dk`/`gold`. `_w_predictor` enemy threats in `red_side`, suggested answers in `win`. `draw_rail` exception fallback uses `red_side_dk` border. `draw_narrative` bottom strip is a navy panel with gold_rule border. `draw_action_queue` header pills use `blue_side`/`red_side` per actor side. **Both `from theme import C` and `from ui import cyber` imports dropped.** — `the_rift/ui/board_rail.py` (cyber refs 16→0; all `C[...]` refs gone)
- 2026-05-19 — Phase 3.10 — **New phase enum + scaffolded render functions.** `DraftPhase` extended with `LOBBY` (alias for `TEAM_BUILD`, plan-canonical name), `SCOUTING`, `BRIEFING`, `ARCHETYPE`. Legacy `ASSEMBLING`/`ANALYSING`/`RESULTS` kept so the solo BEGIN ANALYSIS path still works while v4 cuts the new flow in behind. New stub render functions `_draw_scouting`/`_draw_briefing`/`_draw_archetype` dispatch to `lol_theme.draw_waiting_screen` with phase-appropriate titles + subtitles (Phase 4 will replace each body with the real per-player progress UI, projected-comps snapshot card, and 7-card hidden picker). Main render dispatcher in `_draw_tab_content` routes each new phase to its stub. **No auto-transitions wired yet** — the new phases are reachable only by setting `draft.phase` manually for development, so the existing IDLE→CONNECTING→TEAM_BUILD→BOARD flow is unaffected. — `the_rift/ui/draft.py`
- 2026-05-19 — Phase 4.1 — **Verified `draft_sync.py` + `draft_sync_ui.py` already expose every Phase 4 op.** `set_ready` / `set_scout_ready` / `set_briefing_done` / `set_archetype` mutation methods are all on the client; the snapshot dict already carries `ready`/`scout_ready`/`briefing_done` per side, and the state JSON carries `phase`/`archetype_self`/`archetype_enemy`. Phase predicates `in_lobby` / `in_scouting` / `in_briefing` / `in_archetype` / `is_done` exist. Send helpers `send_set_ready` / `send_set_scout_ready` / `send_set_briefing_done` / `send_set_archetype` exist. **Zero changes needed.**
- 2026-05-19 — Phase 4.2 — **SCOUTING phase wired end-to-end.** `_sync_phase_watcher` now drives SCOUTING locally. On entry it calls `_maybe_start_scout_prefetch()` which (a) pulls 10 player names from the server snapshot, (b) pre-marks anything already cached, (c) kicks `prefetch_scout_sheets(names, on_progress=...)` whose callback updates `draft.scout_progress[name] = 1/0` from the worker thread, and (d) calls `_maybe_send_scout_ready()` which sends `set_scout_ready(True)` once all 10 dots are green. `_draw_scouting` replaced with a real UI: solid navy backdrop + waiting-screen rune + status text + overall progress bar + a 2-column (BLUE/RED) per-player dot panel showing gold/win/loss status per name. — `the_rift/ui/draft.py`
- 2026-05-19 — Phase 4.3 — **BRIEFING phase wired end-to-end.** `_sync_phase_watcher` enters BRIEFING and snapshots `draft.briefing_started_at`. `_compute_briefing_data()` runs once-per-entry (cached): `recommend_comps(our_roster)` + `recommend_comps(enemy_roster)` for projected labels + 5 picks each, plus `recommend_bans(enemy_roster)` and `recommend_bans(our_roster)` for the top-3 bans each side likely plays. `_draw_briefing` renders a two-panel snapshot card (OURS / THEIRS), each showing the projected archetype label + 5 projected picks + 3 key bans, with a side-accented border, in Cinzel header. `_maybe_send_briefing_done()` fires `set_briefing_done(True)` after `_BRIEFING_TIMEOUT_S` (5s); a manual CONTINUE button short-circuits via `_briefing_handle_input`. Sub-second elapsed counter in the header updates each frame. — `the_rift/ui/draft.py`
- 2026-05-19 — Phase 4.4 — **ARCHETYPE phase wired end-to-end (hidden per side).** `_draw_archetype` runs `recommend_comps(our_roster, n_results=7)` and lays out the result in a 4×2 grid using `lol_theme.draw_archetype_card` (which already renders AP/AD damage profile bar + 5 projected picks + viability tag from the Phase 3 primitive set). Clicking a card stages `draft.archetype_pending`; the bottom CONFIRM button (gold-bordered when something is pending) calls `send_set_archetype(arch)` which the server stores per-side and never broadcasts cross-side until DONE. Server auto-advances LOBBY→BOARD once both sides confirm. `_archetype_handle_input` handles both pick + confirm clicks. Hover state on the cards is tracked in `draft.archetype_hover` for a visual lift. — `the_rift/ui/draft.py`
- 2026-05-19 — Phase 4.5 — **Pivot alert banner in `_draw_board`.** Added `_compute_pivot_alert(b)` which runs `archetype_pivot_check(b, our_side, arch, inhouse, primary, scout)` whenever the (archetype, pointer, picks, bans) signature changes. Locked archetype is read from the server's hidden-per-side `archetype_self` first, falling back to the local `board_target_arch`. When `wrecked=True`, a 60px-tall warning banner slides in just below the timeline (drops `body_y` so the team panels reflow). `lol_theme.draw_pivot_alert_banner` renders the banner with the archetype name + reason text + two pivot-option buttons; the click hit rects come back from the primitive and get registered as `pivot_to` board hits. The board input handler commits the new archetype via `send_set_archetype()` AND sets `board_target_arch` locally + invalidates the cached pivot signature + recomputes recommendations. — `the_rift/ui/draft.py`
- 2026-05-19 — Phase 4.6 — **Enemy ghost-suggestion chip on BOARD.** Added `_draw_enemy_ghost_chip(dl, b)` which calls `predict_enemy_next_pick(b, inhouse, primary, scout)` (Phase 2 engine helper), looks up the matching enemy `_pick_slot_rects` entry, and overlays `lol_theme.draw_ghost_suggestion_chip` (translucent, opacity gated by confidence) on the empty role slot the enemy is most likely to fill next. Renders nothing when the predicted slot is already locked, so the chip naturally fades on the actual pick. Rendered after both team panels so the slot rects are populated. — `the_rift/ui/draft.py`
- 2026-05-19 — Phase 5.1 — **`the_rift/ui/audio.py` created.** Minimal `pygame.mixer` wrapper. Six cues: `play_lock`, `play_ban`, `play_turn`, `play_archetype`, `play_pivot`, `play_draft_end`. Per-cue `Sound.set_volume` mixing. Init is best-effort (no pygame / no audio device / no sound files all degrade to no-ops). Files resolved from `the_rift/assets/sounds/` in dev, `sys._MEIPASS/assets/sounds/` in frozen builds. `set_enabled(bool)` / `is_enabled()` / `is_ready()` / `loaded_keys()` helpers expose state to Settings. **No sound files shipped yet** — they get added during Phase 6 (royalty-free Freesound CC0 sourcing). Mixer comes up empty in dev, so cues are silent no-ops until the WAVs land. — `the_rift/ui/audio.py` (NEW)
- 2026-05-19 — Phase 5.2 — **Audio cues wired into draft.py.** `_board_apply` pointer-bump in `_draw_board` fires `play_lock` (pick) or `play_ban` (ban) on every locked action, AND `play_draft_end` when `b.pointer >= 20` (final action). `_archetype_handle_input` fires `play_archetype` on CONFIRM. `_compute_pivot_alert` fires `play_pivot` on the rising edge of `wrecked=True`. A new `draft._audio_last_actor_idx` tracker in `_draw_board` fires `play_turn` once per action when the current `act.side == our_side` (so the user gets a chime each time it becomes their turn). `main.py` startup applies `audio.set_enabled(cfg["audio_enabled"])` so the mute toggle persists across launches. — `the_rift/ui/draft.py`, `the_rift/main.py`
- 2026-05-19 — Phase 5.3 — **DONE-screen polish.** `_draw_board_center`'s DRAFT-COMPLETE branch now delegates to `_draw_done_summary(dl, x, y, w, h, b, interactive)` which lays out: (a) Cinzel header + gold rule, (b) win-prob progression chart pulled from `board_rail._cache["history"]` with a midline + side-tinted polyline + final WP% in the corner, (c) two side-by-side game-plan cards using each side's locked archetype (read from server's `archetype_self`/`archetype_enemy` for sync mode, falling back to `board_target_arch`) — title from `ARCHETYPES[arch]["label"]` and a 3-4 line wrap of `ARCHETYPES[arch]["game_plan"]`, (d) "WHAT GOT BANNED" retrospective panel: re-runs `recommend_comps(side_roster)` to get projected picks per role, compares against the OTHER side's ban list, shows BANNED/win dots + role/champ rows for both sides side-by-side, (e) gold-bordered "NEW DRAFT" button at the bottom. `_bans_retrospective(b)` helper does the projection diff. — `the_rift/ui/draft.py`
- 2026-05-19 — Phase 5.4 — **Solo fallback in LOBBY.** New `_draw_solo_fallback(dl, vw, vh, snap)` renders a slim banner above the READY button whenever only one side is claimed in the synced lobby. Counts down 30s ("Waiting for opponent… 27s"); after the timeout the banner copy switches to "No opponent — solo briefing available" and a "Continue solo (briefing only)" link becomes the active CTA. Click handler in `_lobby_handle_input` dispatches `go_solo` → `_enter_solo_briefing()` which (1) sets `draft.solo_mode=True`, (2) builds the local board via `_board_begin()`, (3) disconnects from the synced session, (4) populates `draft.briefing_data`, (5) jumps `draft.phase = BRIEFING`. The briefing's 5s auto-advance + CONTINUE button both detect `draft.solo_mode` and return to IDLE instead of trying to `set_briefing_done` on a closed websocket. — `the_rift/ui/draft.py`
- 2026-05-20 — Phase 6.1 — **LCU drop.** All `board_live*` / `_lcu_poll_loop` / `_board_live_sync` references stripped from `draft.py`: DraftState attrs, `_TBState.board_live`, `_tb_open(board_live=...)` kwarg, three setter blocks in `_lobby_begin_synced` / `_board_begin_synced` / `_board_begin`, the entire `_lcu_poll_loop` daemon, the entire `_board_live_sync` mirror, the LCU branch in `_draw_board` header, the LCU phase-countdown bar in `_draw_board_center`, `drag_disabled` LCU check, and the `board_live_stop` setters in the exit + new-draft handlers. `live_connected` is now a constant `False` retained only so the `interactive=not live_connected` plumbing reads. **`the_rift/data/draft_lcu.py` (302 lines) deleted.** **`from data import draft_lcu` import dropped from `draft.py`.** — `the_rift/ui/draft.py`, **`the_rift/data/draft_lcu.py` DELETED**
- 2026-05-20 — Phase 6.2 — **cyber.py deleted.** Residual import in `ui/settings.py` cleaned up: CALM MODE section replaced with an AUDIO section ("Enable audio cues" checkbox) that calls `_apply_audio_enabled` → `audio.set_enabled(enabled)`. `SettingsState` swapped `calm_mode` field for `audio_enabled`. **`the_rift/ui/cyber.py` DELETED.** — `the_rift/ui/settings.py`, **`the_rift/ui/cyber.py` DELETED**
- 2026-05-20 — Phase 6.3 — **Cyberpunk palette keys pruned.** `theme.py` `C` dict no longer carries `cy_*` / `mg_*` / `term_g` / `amb` / `alert_r` / `scan_gy` / `panel_dk` / `grid_a`. Only `navy_deep` / `navy_mid` / `gold_rule` / `gold_lt2` survive from the LCS palette (alongside the original Direction A keys). The last reference (`_BOARD_TAG_COL["POWER"]` → `C["amb"]`) was repointed at `lol_theme.LOL["warning"]`. — `the_rift/theme.py`, `the_rift/ui/draft.py`
- 2026-05-20 — Phase 6.4 — **Legacy War Room phases removed.** `DraftPhase` enum trimmed: `ASSEMBLING` / `ANALYSING` / `RESULTS` gone. The IDLE → BEGIN ANALYSIS → ASSEMBLING → ANALYSING → RESULTS pipeline is fully deleted: `start_assembly` + `_fly_blue` + `_fly_red` + `_land` + `_start_analysing` + `_show_results` methods on DraftState removed. Legacy DraftState fields gone (`win_pct` family, `panel_alpha_*`, `lane_reveals`, `sweep_t`, `chip_alpha`, `analyse_t`, `_landed`, `_total`, `blue_avg`, `red_avg`, `pvp_rows`, `blue_bans` / `red_bans` / `blue_comps` / `red_comps` / `ban_detail_*` / `comp_detail_*`, `prediction_*`, `bg_*`, `team_flash_*`, `blue_slots` / `red_slots`). `_analyse_teams`, `_tb_begin_analysis`, `_apply_prediction`, `_kick_off_bg_draft`, `_apply_draft_results` functions deleted. Entire War Room render block (`_draw_team_area`, `_draw_win_meter`, `_factor_chips`, `_arc_points`, `_win_color`, `_draw_score_radar`, `_draw_ban_card`, `_identity_tags_for`, `_spike_window`, `_draw_spike_strip`, `_draw_picks_with_fit`, `_compact_lane_note`, `_draw_comp_card`, `_draw_threat_focus`, `_draw_strategy_panel`, `_draw_lane_card`, `_draw_blue_panel`, `_draw_pvp_panel`, `_draw_red_panel`) deleted from the tail of `draft.py`. Legacy IDLE "RE-ANALYSE PREVIOUS DRAFT" link gone. Solo BEGIN ANALYSIS target on the team-builder gone (target is always `"board"` now). Unused imports pruned (`load_prediction_data`, `write_draft_picks`, `run_draft_subprocess`, `read_draft_results`, `write_activity_event`, `draw_orbital_spinner`, `draw_drift_field`, `draw_breathing_ring`, `breathing_alpha`, `FLY_*`/`TEAM_FLASH_MS` constants). Dispatcher fall-through to legacy now bounces back to IDLE. **`draft.py` shrank from 5704 lines → 4479 lines.** — `the_rift/ui/draft.py`
- 2026-05-20 — Phase 6.5 — **PyInstaller spec updated.** `the_rift/the_rift.spec` hidden-imports: dropped `data.draft_lcu` and `ui.cyber`, added `pygame` + `pygame.mixer` + `ui.lol_theme` + `ui.audio`. `assets/` already bundled, so newly-created `assets/sounds/` (with README.md placeholder) ships automatically. There is no `build_merger.py` in the repo despite the planning doc mentioning one — the .spec is the only build config and it's now Phase 5-ready. — `the_rift/the_rift.spec`, `the_rift/assets/sounds/README.md`
- 2026-05-20 — Phase 6.6 — **DRAFT_BOARD.md rewritten.** 558-line v2.7 spec replaced with a fresh v3 reference: one-paragraph summary, 8-phase flow diagram, per-phase render-function descriptions, audio cue table, LCS palette table, server protocol summary, engine highlights, scout-chronology notes, key-files map, user preferences. — `DRAFT_BOARD.md`

---

## 10 · Next Action

**Phase 1 code is complete and syntax-clean. Deploy + verification are
blocked on user actions.**

### Immediate next step — USER ACTION REQUIRED: deploy server to Fly.io

From the project root, in a terminal with `fly` CLI installed:

```bash
cd server
# First time only:
fly auth login                      # if not already logged in
fly launch --no-deploy --copy-config # registers the app; accept defaults
# Then (and on every future deploy):
fly deploy
```

After the deploy completes, Fly prints the app URL. Confirm:
1. The URL matches what's baked into `the_rift/data/config.py`'s
   `sync.url` field (currently `wss://the-rift-draft.fly.dev`). If different,
   update either the Fly app name (`fly apps rename <new>`) or the
   `config.py` URL. Both must agree.
2. The health endpoint responds: `curl https://<app>.fly.dev/health`
   should return `{"ok": true}`.

### Phase 1 verification (after deploy is live)

Run the app on two machines (or two user accounts on the same machine):

1. Both press **BEGIN DRAFT** on the Draft tab.
2. Both see the CONNECTING waiting screen briefly (rotating gold rune).
3. Both land in TEAM_BUILD (the existing team-builder UI).
4. Header shows `DRAFT · 2 connected · YOU BLUE (host)` and `... YOU RED (guest)`.
5. Either user can click the BLUE/RED toggle in the header to swap sides.
   The swap should reflect on the OTHER client too (server-authoritative).
6. Drag-drop a few players into roster slots on either side. Both clients see
   the roster updates.
7. Each side clicks the action button (legacy label: "START DRAFT BOARD") —
   in synced mode this sends `set_ready(True)` to the server. After both
   sides ready up, the server advances phase to BOARD.
8. The `_sync_phase_watcher()` per-frame check detects the phase advance and
   transitions the local view to BOARD.

Expected pain points / Phase-3 todos to NOT fix in Phase 1:
- The team-builder still uses cyberpunk styling. **Don't fix here** — Phase 3 rewrites the whole UI.
- The action button still says "START DRAFT BOARD"; in synced mode it's really "I'M READY". **Phase 3** renames + restyles.
- There's no visible "the other side is ready" indicator on the lobby header. **Phase 3** adds the per-side ready light.
- SCOUTING / BRIEFING / ARCHETYPE phases on the server are stubbed — the
  current client doesn't render them, just falls through to BOARD once the
  server says BOARD. **Phase 4** wires real per-phase UIs.

### After Phase 1 verifies clean

Update the **Status snapshot** to mark Phase 1 ✅ Complete, then begin Phase 2:

> **Phase 2 entry point:** Scout-script chronology pipeline in
> `the_rift/data/fetch_ranks_gsheets.py` (preserve per-game `results` during
> aggregation in `analyze_player`; emit new "Results" column in
> `write_scouting_sheet`'s FULL CHAMPION POOL block) + matching parser
> update in `the_rift/data/reader.py:1515`. Detailed file delta in
> Section 4 / Phase 2.

Append progress to the Change log as each step completes.

---

## 11 · Phase 2 status: complete (code only — end-to-end verification at Phase 6 build)

Phase 2 is fully landed. Engine self-test passes. The user opted to skip
intermediate two-client verification and Phase 1 lobby verification — both
get exercised together in Phase 6 when we do the single PyInstaller build
and full manual run-through.

### Phase 2 verification commands (for the future Claude session)

```bash
# Engine self-test (must be run from the_rift/ so `from data import ...` resolves)
cd "C:/Users/blhei/Desktop/all code/the_rift"
python -m data.draft_board   # expect "OK - walked 20 actions, ..." at the end

# Spot-check SLOT_ROLE_BIAS is doing its job
cd "C:/Users/blhei/Desktop/all code/the_rift"
python -c "
import sys; sys.path.insert(0, '.')
from data.draft_board import DraftBoardState, recommend_action, ROLES
from data import draft_engine as _eng
rv = _eng.ROLE_VALID
def p(name, role):
    return {'name': name, 'tier':'Gold','final_score':55.0,'score':55.0,
            'wr':53.0,'winrate':53.0,'games':40,'kda':2.6,'form':'MIXED',
            'top_champs': sorted(rv.get(role, ()))[:3], 'role': role}
blue = [p(f'B{i+1}', r) for i, r in enumerate(ROLES)]
red  = [p(f'R{i+1}', r) for i, r in enumerate(ROLES)]
st = DraftBoardState(blue, red, our_side='BLUE')
for _ in range(6):
    rec = recommend_action(st, {}, {}, n=5, scout_champs={})
    if rec['suggestions']:
        st.apply(rec['suggestions'][0]['champion'], role=rec['suggestions'][0].get('role'))
rec = recommend_action(st, {}, {}, n=5, scout_champs={})
roles = [s['role'] for s in rec['suggestions']]
print('B1 top-5 roles:', roles)
assert 'TOP' not in roles, 'BUG: TOP should be biased out of B1 suggestions'
print('PASS — B1 bias toward JGL/BOT/SUP confirmed')
"
```

### Next Action: source sounds + final build (user actions only)

Phase 6 code cleanup is complete. `draft_lcu.py` and `cyber.py` are
gone. Cyberpunk palette keys and War Room render functions are gone.
The PyInstaller spec is Phase-5-ready. `DRAFT_BOARD.md` is rewritten.
`draft.py` is now 4479 lines (down from 4992 at the start of the
rewrite — the cyber.py rip cost ~135 line edits while the War Room
removal saved ~1200 lines).

Two manual steps remain before the rewrite ships:

> **Step A — source the 6 sound cues.** Drop these WAV/OGG files into
> `the_rift/assets/sounds/`:
>
>     lock.wav            ~120 ms thunk            pick lock
>     ban.wav             ~120 ms muted thud       ban lock
>     turn_chime.wav      ~250 ms rising chime     your turn
>     archetype_stinger.wav ~600 ms stinger        archetype confirm
>     pivot_alert.wav     ~400 ms warning sting    pivot wrecked
>     draft_complete.wav  ~1500 ms outro flourish  final action
>
> See `the_rift/assets/sounds/README.md` for naming + format guidance.
> Freesound (CC0) is the user-blessed source. The audio module
> auto-loads whatever's on disk at startup; missing files are silent
> no-ops, so you can ship without all six.
>
> **Step B — run the single PyInstaller build.**
>
>     cd the_rift
>     pyinstaller the_rift.spec --noconfirm
>
> Then full manual QA:
>
>     • Two clients connect to the Fly.io URL, see each other in LOBBY
>     • Side toggle swaps cleanly
>     • Drag-drop rosters; READY UP on both sides
>     • SCOUTING dots fill in as scout sheets load
>     • BRIEFING card auto-advances after 5s
>     • ARCHETYPE picker hides your choice from the opponent until DONE
>     • BOARD pivot alert fires when archetype gets wrecked
>     • Enemy ghost chip appears on the predicted next slot
>     • DONE shows both archetypes + WP chart + game plans + bans retro
>     • Six audio cues fire at the right moments
>     • Settings → audio toggle persists across launches
>     • Solo fallback: drop to lobby with one client, click "Continue
>       solo" after 30s, get a BRIEFING preview → IDLE
>
> If anything regresses, file a follow-up against this handoff doc.
> Otherwise the rewrite is done.
