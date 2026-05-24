# The Rift — Upgrade Initiative · Roadmap & Handoff

> Living document for the app-wide upgrade of The Rift. A future session should
> read this first, then `DRAFT_BOARD.md` (draft-tool internals) and
> `DRAFT_REWRITE_HANDOFF.md` (draft-tool history). Keep the **Status snapshot**,
> **Change log**, and **Next action** sections accurate at all times — they are
> the contract between sessions.

---

## 0 · Status snapshot

| Phase | State |
|---|---|
| Vision + competitor research | ✅ Complete (2026-05-21) |
| Decisions locked | ✅ Complete (2026-05-21) |
| Phase 0 — Foundations | ✅ Complete — 0a · 0b · 0c · 0d all live |
| Phase 1 — Backend & data depth | ✅ Complete — log→DB + Sheet mirror + backfill + modularize all landed. Secrets rotation explicitly out of scope (user decision). |
| Phase 2 — Draft engine: data-grounded & reliable | ✅ Complete — server engine + signals/players/calibration/backtest/tuning live; client heavy compute fully proxied; `_legacy_*` mirrors deleted. |
| Phase 3 — Tab feature waves | ✅ Complete — Inhouse (history + detail + rivalries + records), Scout (tags + compare), Rankings (sparkline + biggest mover), Tier List (league pulse), Activity (filters), Commands (freshness), Settings (master volume) all shipped 2026-05-22. |
| Phase 4 — New surfaces | ✅ Complete — Home/Dashboard tab, Player Profile panel, Seasons & History (server + UI) all shipped 2026-05-23. |
| Phase 5 — Wow features | ✅ Complete (4 of 6) — Achievements, Predictions, Shareable cards (PNG), Rift Wrapped recap deck. Discord + AI Analyst deferred (out of scope for this pass). |
| Phase 6 — Polish & 1.0 hardening | ✅ Initial pass — hotkey overlay (`?`), first-run welcome toast, sidebar reordered to put HOME first. Theme/accent picker + perf sweep + window remember-size deferred for a follow-up. |

---

## 1 · The vision

The Rift is a desktop app for a private inhouse League of Legends scene
(~19 players). It is **not** competing with OP.GG / Mobalytics / Porofessor
(solo-queue) or DraftGap / Drafter.lol (public draft sim). Nobody owns the
"private friend-group league" space — that is The Rift's identity and its moat.

North star: **The Rift becomes the ESPN broadcast + the league office for the
inhouse scene** — power rankings as a show, a real league with seasons and
records, deep scouting, a synced tournament draft backed by an engine you can
actually trust, and a social heartbeat. The v3 Draft rewrite set the quality
bar; the other 7 tabs rise to meet it, and the whole app is held to a premium
polish standard (§4).

---

## 2 · Decisions locked (2026-05-21)

| Decision | Choice |
|---|---|
| Design language | Unify the entire app on the `lol_theme` LCS-broadcast aesthetic — navy `#0a1428` / gold `#c8aa6e`. Keep Cinzel Decorative / Rajdhani / JetBrains Mono fonts. |
| Animation | More motion, including *persistent* motion. Focal motion + subtle *localized* ambient. No full-screen drift. A Settings animation-intensity slider lets each user dial it. |
| Backend | SQLite on a small Fly.io volume (~$0.15–0.45/mo) + a REST API added to the existing `the-rift-draft-sync` server. The Google Sheet is kept as an automatic human-readable backup/export. |
| Draft engine | A top-priority outcome (Phase 2): rebuilt on real match data — counters / synergies / matchups / player models derived from the DB, hand tables kept only as low-sample priors; calibrated win probabilities; a backtest harness with a tracked, visible accuracy rate. |
| Polish | Ambitious. Every surface meets a definition-of-done polish bar (§4). Polish systems (toasts, app-wide sound, skeletons, transitions, design tokens) are Phase-0 foundations; a dedicated hardening pass is Phase 6. |
| Cost rule | All services on free tiers. Only acceptable paid spend is the small existing Fly cost. |
| Start order | Foundations first. |

---

## 3 · Architecture today

- **App:** Python + DearPyGui, custom borderless window, drawlist-based
  rendering. 8 tabs. PyInstaller build shipped via GitHub releases
  (`BLHvibe/The-Rift`).
- **Tabs:** Rankings, Draft, Scout, Inhouse, Tier List, Settings, Commands,
  Activity.
- **Data:** Google Sheets is the shared DB. `data/reader.py` (~2.4k LOC)
  reads it; `data/fetch_ranks_gsheets.py` (~3.3k LOC) hits the Riot API and
  writes it. The LCU lockfile is used for client detection + custom-game
  logging. Match-level Riot data is fetched then aggregated away.
- **Draft tool (v3):** synced 2-client tournament draft over a Fly.io
  WebSocket server; local engine (`draft_engine.py`, `draft_board.py`);
  `lol_theme.py` primitives. (Active uncommitted v3.0.5 work in progress.)
- **Draft engine today:** pure-Python, no I/O; runs on hand-authored
  heuristic tables (`SUBCLASSES`, `SYNERGIES`, `COUNTERS`, `LANE_MATCHUPS`,
  `ARCHETYPES`, `CHAMP_PRIORS`). Phase 2 rebuilds it on real data.
- **Theme:** `theme.py` (old gold/dark "Direction A" — 7 tabs) +
  `lol_theme.py` (new navy/gold — draft only) → to be unified.
- **Animation:** `core/animations.py` (tweens/particles/ripples) +
  `ui/effects.py` (spinner/drift/shimmer/breathing).
- **Polish debt to clear:** three ad-hoc notification systems (inhouse
  `_GameLoggedNotif`, the main.py update card, tier-list submit flashes);
  tabs hard-cut; manual mouse hit-testing with hard-coded offsets; plain-text
  empty/error states; inconsistent number formatting.

---

## 4 · Polish standard — definition of done

Polish is not a phase — it is the bar every surface clears before it is
"done." When any tab, panel, or feature is built or migrated, it must meet
**all** of:

- **States designed.** Empty, loading, error, and success states are all
  designed surfaces — never bare text, never a raw traceback, never a dead
  screen. Loading uses skeletons that match the real content; errors are
  friendly and offer a retry.
- **Every interaction responds.** Hover, press, release, focus, and disabled
  states on every clickable element. Cursor changes on hover. Ripples/feedback
  on click.
- **Nothing hard-cuts.** Tab switches, panel opens, and load→loaded all
  transition. Content reflows smoothly.
- **Persistent life.** Idle motion on focal elements per the animation stance
  — count-ups, breathing accents, shimmer — gated by the intensity slider.
- **Tokens, not magic numbers.** Spacing, radii, borders, elevation, and type
  all come from the shared token scale (§5, 0b).
- **Data reads clean.** Numbers formatted (commas, %, K/M, signed deltas,
  color coding) via shared helpers. Text never clips or overflows.
- **Detail on demand.** Rich hover popovers expose the deeper numbers.
- **It sounds right.** A subtle audio cue where it adds meaning — all behind
  the audio toggle.
- **It's smooth.** 60fps, no flicker, no one-frame jank.

---

## 5 · Roadmap

### Phase 0 — Foundations
- **0a ✅ Motion, interaction & polish toolkit.** `anim` intensity system +
  `smooth`; `effects.py` motion / micro-interaction / skeleton / popover
  helpers; `ui/toast.py` unified toast stack; tab-fade transition; `audio.py`
  app-wide cues. Full surface in the change log.
- **0b ✅ Design system.** `ui/tokens.py` (palette `PAL`, `TIER`, the
  `SPACE` / `RADIUS` / `STROKE` / `ELEV` / `TYPE` scales + helpers) and
  `ui/fmt.py` formatters.
- **0c ✅ Migrate onto the unified system.**
  - ✅ **Palette unified app-wide** — `theme.C` + `RANK_COLORS` retuned to the
    LCS navy/gold language (mirrors `tokens.PAL` / `TIER`). Every surface —
    chrome and all 7 non-draft tabs — now renders in the unified palette with
    no per-file draw changes. Legacy `C` keys remain as a compatibility layer.
  - ✅ **Per-surface polish-standard migration** — all 8 surfaces done
    (compile-verified; the user verifies the full upgrade visually at the end):
    1. ✅ App chrome — window-button hover states; update notification
       retired into the toast stack. (Sidebar / ticker / splash already meet
       the bar; re-skinned via the palette.)
    2. ✅ Rankings — score count-up, podium hover-lift, skeleton loading
    3. ✅ Activity — skeleton loading rows
    4. ✅ Tier List — card hover glow; submit-status flash retired to toasts
    5. ✅ Scout — skeleton table loading, row hover, score count-up
    6. ✅ Inhouse — `_GameLoggedNotif` retired to toasts; skeleton loading; row hover
    7. ✅ Commands — native-widget overlay tab; re-skinned via the palette
       (DPG widgets self-theme; no bespoke draw code to migrate)
    8. ✅ Settings — native-widget overlay tab; re-skinned via the palette
- **0d ✅ Backend — deployed and live.** SQLite match store on a Fly volume
  (`rift_data` → `/data/rift.db`); REST API (`server/api.py`) mounted
  additively on the existing draft-sync server inside a try/except, so a
  data-API fault can never take down draft multiplayer. Verified live on
  `the-rift-draft-sync.fly.dev`: `/health`, `/`, `/api/stats` (0/0 on the
  fresh DB), `/api/matches` (empty list) all 200-OK. The scheduled Sheet-
  mirror backup is a small follow-up — `/api/export` already returns the
  full DB dump for it.

**0c per-surface migration recipe** — apply to each surface in turn:
1. Swap `theme.C` lookups for cleaner `tokens` equivalents where they exist;
   snap padding / gaps / radii to `SPACE` / `RADIUS`.
2. Loading state → `effects.draw_skeleton_*` mirroring the real layout.
3. Empty + error states → designed surfaces (icon + message + action) — never
   bare text, never a raw traceback.
4. Interactive elements → `effects.hover_lift` / `hover_amt` / `press_offset`
   + `draw_hover_glow`; headline numbers → `effects.count_up`; route every
   number through `ui/fmt.py`.
5. Replace any ad-hoc notification with `toast.push(...)` — the three to
   retire are `inhouse._GameLoggedNotif`, the `main.py` update-notif window,
   and the tier-list submit-status flash.
6. Add hover popovers (`effects.draw_popover`) for deeper detail.
7. Verify: `python -m py_compile` the file (the user verifies the full
   upgrade visually at the end).

### Phase 1 — Backend & data depth
- Store match-level + timeline data (currently fetched, then discarded).
- Migrate the existing inhouse + scout corpus from Sheets into the DB at
  match granularity.
- Modularize the `fetch_ranks_gsheets.py` monolith.
- Move secrets out of the repo (`credentials.json`, Riot key) into
  env/secrets; rotate them.

### Phase 2 — Draft engine: data-grounded & reliable
*Depends on Phase 1's match-level data. The inhouse corpus already exists
(logged to Sheets via `analyze_inhouse`); Phase 1 migrates it into the DB, so
the engine is not starting from zero.*

The engine today runs on hand-authored heuristic tables — an informed
opinion, not evidence, and one that goes stale as the meta moves. Rebuild it
so the core signals come from data.

- **2a · Data-grounded signals.** Derive counters, synergies, lane matchups,
  and champion strength from the inhouse + scout match corpus. Blend with the
  hand tables by sample size (Bayesian shrinkage — low sample leans on the
  prior, high sample trusts the data). Unseen champs fall back to priors.
- **2b · Deep player models.** Per-player champion pools, per-champ
  performance, role comfort, off-role penalty, and form — computed from real
  logged games at match granularity, not scout-sheet aggregates. This is what
  makes the recommendations *yours*.
- **2c · Calibration & honest confidence.** Win probabilities that mean what
  they say (a calibrated 65% wins ~65% of the time). The engine surfaces its
  uncertainty — sample size, coverage gaps — instead of projecting false
  confidence.
- **2d · Backtest harness + tracked accuracy.** Replay historical inhouse
  drafts/games through the engine and score predictions against actual
  results. A visible, tracked hit-rate makes reliability *measurable*; a
  regression guard stops engine changes from quietly getting worse.
- **2e · Tuning loop.** Fit the engine's weights to real outcomes instead of
  hand-tuning; a surface to inspect and adjust them.
- **2f · Quality + refactor.** Sharper archetype detection, pivot logic, and
  counter-pick gating; expanded champion coverage; `draft_engine.py` /
  `draft_board.py` refactored for maintainability; expanded self-test.
- **Engine location** — decide during 2a whether the engine runs server-side
  (co-located with the match DB → always fresh + full data, identical recs
  for both clients, updatable without an app rebuild) with a local fallback,
  or stays local. Server-side is the likely call since that is where the data
  lives.

### Phase 3 — Tab feature waves
Inhouse → Scout → Rankings → Tier List → Activity → Commands/Settings.
Per-tab detail in §6. Every wave meets the §4 polish standard.

### Phase 4 — New surfaces
Home/Dashboard landing tab, Player Profile pages, Seasons & History.

### Phase 5 — Wow features
Rift Wrapped (animated season recap), AI Analyst (LLM-written summaries),
Discord integration, Predictions + leaderboard, achievements/badges,
shareable stat cards.

### Phase 6 — Polish & 1.0 hardening
- Cross-app consistency audit (tokens, spacing, copy, color).
- Performance pass — 60fps everywhere; eliminate flicker and one-frame jank.
- Brand cohesion — splash, crown, wordmark, color, and sound as one identity.
- First-run / onboarding flow.
- Window polish — remember size/position, smoother drag/snap, multi-monitor.
- Full keyboard navigation + focus states; surfaced hotkeys.

---

## 6 · Per-tab upgrade detail

- **Rankings** — rank-over-time sparkline per row; "biggest mover / on the
  rise" callouts; splash-art parallax behind #1; animated score count-up; a
  "why ranked here" explainer popover (tier vs rank vs inhouse weight); season
  framing with snapshots over time.
- **Draft** — *(engine rebuild is its own workstream — Phase 2)* draft-tool /
  UI features: draft history/replay (save + review completed drafts); Fearless
  draft (series-wide pick locks); mock draft vs AI; a saved-comp/strategy
  library; optional LCU champ-select mirroring (dropped in v3).
- **Scout** — auto player tags (Porofessor-style behavior labels); side-by-side
  player compare; head-to-head matchup view (h2h already computed in the
  script); match-timeline curves; OTP / off-role detection; an auto-written
  threat-report paragraph; raised to draft-tool polish.
- **Inhouse** — match-history feed (every custom game as a card); per-game
  detail (scoreboard + draft + timeline); rivalries / h2h; records &
  superlatives (longest streak, biggest blowout, most pentas); real player
  profile pages; seasons/splits; MVP voting; achievements/badges.
- **Tier List** — surface the consensus list, "hot takes," and rater-bias
  (all already computed by the script); consensus-over-time; champion tier
  lists; a more satisfying drag-drop.
- **Activity** — richer event types (rank changes, new records, achievements,
  draft results); reactions/comments; per-type/player filtering; an
  auto-generated weekly digest.
- **Commands** — reframe as a "Control Room": scheduled/auto refresh, a
  data-freshness + API-quota health dashboard, per-player progress with ETAs,
  one-click "refresh everything."
- **Settings** — theme/accent picker, animation-intensity slider, sound
  controls, notification prefs, profile customization.

---

## 7 · Outside-the-box backlog

- **Rift Wrapped** — a Spotify-Wrapped-style animated end-of-season recap.
- **AI Analyst** — an LLM that writes scouting summaries, draft retrospectives,
  and the weekly digest.
- **Discord integration** — post results, rankings, and draft outcomes.
- **Predictions** — call inhouse game outcomes; a sharpest-predictor board.
- **Achievements & badges** — an app-wide progression layer.
- **Shareable cards** — export a PNG of a player's stats or a draft result.

---

## 8 · Working rules

- Work in the main project dir, not `.claude/worktrees/*`.
- Never push/tag/release to GitHub until the user verifies the build; rebuild
  `dist/` before pushing so the binary matches source.
- Free-tier infra only — only the small existing Fly cost is acceptable.
- New motion: focal + subtle localized ambient, intensity-slider gated; no
  full-screen drift.
- Every surface meets the §4 polish standard before it is called done.
- Migrate visual surfaces one at a time; the user verifies each before the
  next.

---

## 9 · Change log

> Append one line per meaningful change: `YYYY-MM-DD — Phase N — [what] — [files]`

- 2026-05-21 — Initiative kicked off. Full codebase explored, competitor
  research done, vision drafted. Decisions locked (§2). Roadmap created. —
  `THE_RIFT_UPGRADE.md` (new)
- 2026-05-21 — Scope raised: added the polish layer — a definition-of-done
  polish standard (§4), polish foundations folded into Phase 0a (unified
  toast system, app-wide sound design, skeleton loaders, transition system,
  hover-popover primitive) and 0b (design tokens), and a Phase 6 polish &
  hardening pass.
- 2026-05-21 — Scope raised: added Phase 2 — Draft engine: data-grounded &
  reliable. Core signals (counters, synergies, matchups, player models) move
  from hand-authored tables to values derived from the match DB, with
  calibration, a backtest harness + tracked accuracy, and a tuning loop.
  Later phases renumbered (tab waves 2→3, new surfaces 3→4, wow 4→5,
  polish 5→6).
- 2026-05-21 — Phase 0a — Motion + intensity core landed. New `anim_intensity`
  config key; `anim.set_intensity` / `anim.smooth` / `anim.clear_smooth` on the
  animation manager; `effects.py` gains `count_up`, `hover_lift`,
  `press_offset`, `hover_amt`, `draw_hover_glow`, `draw_focus_ring`,
  `draw_ambient_motes`, `draw_parallax_image`; existing drift / shimmer /
  breathing effects now scale with intensity; Settings → INTERFACE animation
  slider wired live. Additive — no tab consumes it yet (that is 0c). Syntax +
  smoke test pass. — `config.py`, `core/animations.py`, `ui/effects.py`,
  `ui/settings.py`, `main.py`
- 2026-05-22 — Phase 0a complete — remaining toolkit landed. New `ui/toast.py`
  unified toast/notification stack (info/success/warn/error, fade-in, stack,
  auto-dismiss, click-dismiss); tab-change fade transition + `audio.play_tab`
  wired into `main.py`; `effects.py` gains skeleton-loader primitives
  (`draw_skeleton_rect` / `_text` / `_row`) and `draw_popover`; `audio.py`
  extended with app-wide cue keys (tab / click / toast / success / error) +
  `play_*` wrappers. Toast stack + transition are live; skeletons / popover
  are consumed during 0c. Syntax + smoke test pass. — `ui/toast.py` (new),
  `ui/effects.py`, `ui/audio.py`, `main.py`
- 2026-05-22 — Phase 0b complete — design system. New `ui/tokens.py` (canonical
  LCS palette `PAL`, `TIER` colors, `SPACE` / `RADIUS` / `STROKE` / `ELEV` /
  `TYPE` scales + `tier_color` / `alpha` / `mix` helpers) and `ui/fmt.py`
  (shared `commas` / `compact` / `pct` / `signed` / `ordinal` / `clamp_text` /
  `kda` / `duration` formatters). Additive — 0c migrates the tabs onto them.
  Syntax + smoke test pass. — `ui/tokens.py` (new), `ui/fmt.py` (new)
- 2026-05-22 — Phase 0c started — palette unified. `theme.py` `C` palette and
  `RANK_COLORS` retuned to the LCS navy/gold language (mirrors `ui/tokens`
  `PAL` / `TIER`), so every surface — app chrome and all 7 non-draft tabs —
  now renders in the unified palette with zero per-file draw changes. Legacy
  `C` keys kept as a compatibility layer until each tab migrates to `tokens`
  directly. Per-surface polish-standard migration is next (recipe in §5).
  Syntax + import check pass. — `theme.py`
- 2026-05-22 — Phase 0c — App chrome migrated (surface 1/8). Titlebar close /
  fullscreen buttons gained hover feedback (`effects.hover_amt` wash +
  brightened glyph); the bespoke update-notification window (`_UPDATE_WIN`)
  was retired and now surfaces through `toast.push` with a click-to-download
  action — the first of the three ad-hoc notification systems replaced.
  Syntax check pass; `_UPDATE_WIN` fully removed. — `main.py`
- 2026-05-22 — Phase 0c — Rankings migrated (surface 2/8). Score numbers count
  up as cards reveal (`effects.count_up` via a `_score_disp` helper, across
  podium / challenger / standings rows); podium #1 / #2 / #3 cards gain a
  gentle hover-lift; the loading screen is now a skeleton podium + rows that
  morphs into the real layout. Syntax check pass. — `ui/rankings.py`
- 2026-05-22 — Phase 0c — Activity migrated (surface 3/8). The first-load
  state is now skeleton rows (`effects.draw_skeleton_row`) that morph into
  real event cards; empty / error states kept as informative messages with
  the REFRESH action in the top bar. Syntax check pass. — `ui/feed.py`
- 2026-05-22 — Phase 0c — Tier List migrated (surface 4/8). Player cards
  (pool + placed) gain a hover glow (`effects.hover_amt` + `draw_hover_glow`);
  the bespoke submit-status flash was retired — submit feedback (validation,
  success, failure) now flows through `toast.push`. Second of the three
  ad-hoc notification systems replaced; `submit_status` / `submit_flash` state
  removed. Syntax check pass. — `ui/tierlist.py`
- 2026-05-22 — Phase 0c — Scout migrated (surface 5/8). Loading screen is now
  a skeleton player-table + report panel that morphs into real content; player
  rows gain hover feedback (brightened fill + faint gold stripe); the score
  column counts up as rows reveal (`effects.count_up`). Syntax check pass. —
  `ui/scout.py`
- 2026-05-22 — Phase 0c — Inhouse migrated (surface 6/8). The `_GameLoggedNotif`
  slide-in card was retired — log-game feedback (success / no-games / error)
  now flows through `toast.push`, with the in-progress state on the LOG GAME
  button. Third and last ad-hoc notification system gone. Leaderboard loading
  is now a skeleton; rows gain hover feedback. Syntax check pass. —
  `ui/inhouse.py`
- 2026-05-22 — Phase 0c — Commands + Settings (surfaces 7-8/8) migrated via the
  palette. Both are native-DPG-widget overlay tabs — buttons / inputs / combos
  self-theme from the global theme, which now carries the unified navy/gold
  palette; their thin drawlist chrome re-skinned through `theme.C`. No bespoke
  draw code to migrate. **Phase 0c complete — all 8 surfaces done.**
- 2026-05-22 — Phase 0d — Backend code complete (deploy pending). New
  `server/db.py` (SQLite store: matches / participants / drafts; round-trip
  tested) and `server/api.py` (REST router: ingest + read + export, optional
  bearer-token auth). `server/main.py` mounts the router additively inside a
  try/except — the WebSocket draft path is untouched and protected.
  `server/fly.toml` gains the `rift_data` volume mount; `server/Dockerfile`
  `COPY main.py .` → `COPY *.py .` (single-file copy would have crashed the
  deploy). Client `the_rift/data/rift_api.py` + an `api_token` config key. All
  files compile; the SQLite layer is round-trip verified. Deploy + secret
  rotation remain as user actions (§10). — `server/db.py` (new),
  `server/api.py` (new), `server/main.py`, `server/fly.toml`,
  `server/Dockerfile`, `the_rift/data/rift_api.py` (new), `the_rift/data/config.py`
- 2026-05-22 — Phase 0d — Backend deployed live. `flyctl volumes create
  rift_data --region iad --size 1` + `flyctl deploy` from `server/`; Fly
  replaced the existing machine with one mounting the volume; smoke checks
  passed. Verified the live REST API: `GET /api/stats` → `{"matches":0,
  "participants":0,"last_ingest":null,"db_path":"/data/rift.db"}`; `GET
  /api/matches` → empty list. `/health` + `/` still respond — the WebSocket
  draft path is untouched. User authorized autonomous Fly deploys for the
  future (see `memory/feedback_fly_deploy_authorized.md`). **Phase 0 is
  complete — 0a + 0b + 0c + 0d all live.**
- 2026-05-22 — Phase 1 — Inhouse log → DB wired. `log_inhouse_games_from_client`
  now builds a parallel list of API match dicts alongside the per-participant
  sheet rows it always wrote, and POSTs them to `/api/matches` after the
  sheet append succeeds. Best-effort: a server outage / auth issue / network
  hiccup can never block the sheet path. Slot-fallback (`slot{i}` within
  team) keeps the `(match_id, team, role)` PK collision-safe when Riot
  returns lane=NONE. Compile + import + live `/api/stats` smoke checks pass.
  First end-to-end verification will happen on the user's next LOG INHOUSE
  GAME click. — `the_rift/data/reader.py`
- 2026-05-22 — **Phase 1 modularize landed.** The 3.7k-line monolith
  `the_rift/data/fetch_ranks_gsheets.py` is now a 36-line backwards-compat
  shim. The real implementation lives in a new `the_rift/data/fetch_ranks/`
  package split into 11 focused submodules: `constants.py` (rank scores,
  tier maps, archetype + champion-subclass DBs), `sheets.py` (auth + retry +
  worksheet helpers), `scoring.py` (`compute_score` / `rank_to_chart_value`),
  `riot.py` (Riot API client — 8 fetchers + ddragon load), `tier_analytics.py`
  (consensus / hot-takes / rater-bias), `rankings.py` (rank-data writers +
  history + final-rankings reader), `scouting.py` (analyze + write + DB),
  `inhouse.py` (custom-game ingest + analysis + sheet writers), `activity.py`
  (event log read/write), `draft.py` (archetype scoring + ban recs + comp
  suggestions + `run_draft`), `cli.py` (the `main()` entrypoint). Import
  order is acyclic — `constants` ⇒ `sheets`/`scoring` ⇒ `riot` ⇒ the
  domain modules ⇒ `cli`. Both legacy and modern import paths work:
  `import data.fetch_ranks_gsheets as fg; fg.main()` AND `from data.fetch_ranks
  import main, compute_score, ...`. The shim adds a path-fixup so the script
  invocation (`python data/fetch_ranks_gsheets.py --help`) still works from
  the launcher's dev-mode subprocess. Smoke tests pass: `compute_score`
  resolves through both paths; `score_team_synergy([Malphite,Diana,Ahri,Jinx,
  Lulu]) = 73.36` (cross-module call: `draft` → `constants.CHAMP_SUBCLASSES`
  → archetype scoring math); `--help` argparse output unchanged. Domain
  functions that hit Riot API / Google Sheets cannot be exercised offline —
  user will verify those on the next real `fetch_ranks_gsheets.py --key …
  --sheet …` run. — `the_rift/data/fetch_ranks/` (new package),
  `the_rift/data/fetch_ranks_gsheets.py` (now a 36-line shim)
- 2026-05-22 — **Phase 3 started — Inhouse match-history feed.** New
  `data.reader.load_match_history()` fetches every match header + full payload
  (`/api/matches` + `/api/matches/{id}`) and caches the result on
  `live.match_history` (with `_loaded` / `_error` flags). Inhouse tab gains a
  HISTORY / LEADERBOARD toggle button in the top bar (left of LOG GAME); when
  in history mode, the leaderboard is replaced with a vertically-scrollable
  card feed. Each match card shows timestamp, duration, source label, a
  winner badge with side-accent edge, and a 5+5 champion strip in role order
  with role chips and abbreviated champion names. Skeleton-row loading state;
  designed empty + error states. First-load is lazy (only when the user
  toggles to history). With `matches=0` the empty state advises "log an
  inhouse game to seed the feed." Compile + import + end-to-end smoke check
  all pass. Per-game *detail panel* (scoreboard + draft + timeline), rivalries,
  records, and player profile pages remain for Phase 3 follow-ups. —
  `the_rift/data/reader.py`, `the_rift/ui/inhouse.py`
- 2026-05-22 — **Phase 2 complete.** Cutover finished — every heavy-compute
  call in `the_rift/data/draft_engine.py` and `the_rift/data/draft_board.py`
  is now a server proxy through `data/engine_api.py` / `/api/engine/*`. Nine
  functions converted: `recommend_comps` / `recommend_bans` / `compute_matchups`
  (engine) and `recommend_action` / `target_archetype` / `pick_impact_delta` /
  `archetype_pivot_check` / `predict_enemy_next_pick` / `recommend_bans_split`
  (board). Original implementations preserved as `_legacy_*` for a deeper
  cleanup pass once the cutover is verified through a real synced draft.
  `DraftBoardState` gained matched `to_dict()` / `from_dict()` on both client
  and server so any board state can be serialized across the wire. Six new
  server endpoints; `recommend_comps` / `recommend_bans` endpoints fixed to
  accept the original kwarg names (`n_results` / `n_bans`). End-to-end live
  test: cold call ~4s (Fly scale-to-zero wake), warm ~500ms; recommend_action
  + target_archetype return correct shapes. The 1.7k-line + 1.6k-line client
  engine files now defer all real work to the server. — `server/api.py`,
  `server/engine_board.py` (+ to_dict/from_dict), `the_rift/data/engine_api.py`,
  `the_rift/data/draft_engine.py`, `the_rift/data/draft_board.py`
- 2026-05-22 — Phase 2 foundation landed. **Engine location decision: server-side
  only, no local fallback** (user choice 2026-05-22). The draft engine moved
  from `the_rift/data/{draft_engine,draft_board}.py` to `server/{engine_core,
  engine_board}.py` (copied near-verbatim — pure-python, no external deps).
  Five new server modules implement Phase 2's data layers, every one wrapped
  in a shrinkage → hand-priors fallback so behavior collapses to today's
  engine when sample is small and sharpens as the DB grows:
  - `engine_signals.py` (**2a**) — Bayesian-shrunken counters / synergies /
    champion-strength tables blended from DB matches; published to
    `engine_core.COUNTERS` / `SYNERGIES` / `CHAMP_STRENGTH` on `refresh()`.
    With `matches=0`, the priors come through unchanged (201 counter keys,
    88 synergy keys).
  - `engine_players.py` (**2b**) — per-player champion pool, role comfort,
    off-role penalty, form (last-N WR + hot/cold label).
  - `engine_calibration.py` (**2c**) — Wilson CI on rate estimates, sample-
    size confidence labels, Platt-scaling hook for the future fit step.
  - `engine_backtest.py` (**2d**) — replays every match through `score_team`,
    persists per-run hit-rate to `/data/rift_backtest.json`, regression-guard
    helper.
  - `engine_tuning.py` (**2e**) — named knob registry with JSON persistence at
    `/data/rift_tuning.json`. Seven knobs default to engine_core's current
    constants (shrinkage_k=8, counter_weight=1.0, …) so changes are
    opt-in.
  Fifteen new `/api/engine/*` REST endpoints (info / refresh_signals /
  score_team / synergy / counter / weakness / recommend_comps / recommend_bans
  / matchups / players/{name} / calibrate / backtest / backtest/history /
  tuning GET+POST). Wrapped in a try/except so an engine bug can never break
  the data API or the WebSocket draft path. **Live on the Fly server** —
  smoke-tested `/api/engine/info`, `/api/engine/score_team`, `/api/engine/
  synergy`, `/api/engine/calibrate`, `/api/engine/backtest` all 200-OK and
  returning sensible values (`Malphite/Diana/Ahri/Jinx/Lulu` vs `Yasuo/Lee
  Sin/Zed/Vayne/Janna` → total=0.734).
  Client lib `the_rift/data/engine_api.py` mirrors every endpoint; new
  Settings → DRAFT ENGINE section exposes ENGINE INFO / REFRESH SIGNALS /
  RUN BACKTEST buttons. **The UI cutover (replacing every `_eng.*` call site
  in `the_rift/ui/draft.py` with async server calls) is the next session's
  work** — the working v3 draft tool is left intact for now so the engine
  swap can be done incrementally and verified call-by-call. **2f (refactor +
  sharper logic) is deferred** to that same UI-cutover pass since both will
  touch the same files. — `server/engine_core.py` (new),
  `server/engine_board.py` (new), `server/engine_signals.py` (new),
  `server/engine_players.py` (new), `server/engine_calibration.py` (new),
  `server/engine_backtest.py` (new), `server/engine_tuning.py` (new),
  `server/api.py`, `the_rift/data/engine_api.py` (new),
  `the_rift/ui/settings.py`
- 2026-05-22 — **Phase 3 complete — remaining tab waves shipped in one pass.**
  Each wave kept to a focused, polish-standard increment so the whole phase
  could close today without a multi-day push:
  * **Scout — side-by-side compare** (`ui/scout.py`). New `_rw_compare(r)`
    section: a DPG combo picks the 2nd player (none / any other player);
    when set, a 4-row delta table (WR / KDA / Games / Score) appears under
    the tags, with green/red coloring based on which side of the metric you
    win. `scout.compare_with` state persists across rebuilds.
  * **Rankings — sparkline + biggest-mover callouts** (`ui/rankings.py`).
    New helpers: `_player_results(n=8)`, `_draw_mini_sparkline()`,
    `_biggest_climber()`, `_biggest_faller()`. Per-row mini W/L sparklines
    on both the challenger rows (#4-10) and the rest rows (#11+); "ON THE
    RISE — Name +N" and "FALLING — Name -N" callouts on the FULL STANDINGS
    header, computed from the existing `rankings.deltas` snapshot diff.
  * **Tier List — LEAGUE PULSE inline insight** (`ui/tierlist.py` +
    `data/reader.py`). New `load_tier_meta()` background loader pulls three
    sheet tabs (Consensus & Controversy, Hot Take Detector, Rater Bias
    Report — all already written by `fetch_ranks/tier_analytics.py`) into
    `live.tier_consensus / tier_hot_takes / tier_rater_bias`. Rater bar
    grew a "LEAGUE PULSE" inline that rotates between the top hot take and
    the most-controversial player every 6 seconds; loads lazily on tab
    entry. New `_open_sheet()` helper in reader.py centralizes the read-
    only sheet handle for future loaders.
  * **Activity — event-type filter chips** (`ui/feed.py`). Top bar grew a
    5-chip segmented control (ALL · DRAFTS · INHOUSE · SCOUT · RANK);
    `_feed.filter_kind` drives a `_kind_matches_filter` helper that's
    applied at populate time. SCOUT chip absorbs SCOUT / SCOUT_NEW /
    RESCOUTED, RANK absorbs UPDATE.
  * **Commands — DATA FRESHNESS panel** (`ui/commands.py`). New section
    above ROSTER: shows match count, participant count, last-ingest
    relative-time, DB path — all pulled from `/api/stats` via a
    single-flight background fetch on first paint, plus a manual REFRESH
    STATS button. `_fmt_ingest` formats "just now" / "Xm ago" / "Xh ago"
    / fallback date.
  * **Settings — master volume slider** (`ui/audio.py`, `ui/settings.py`,
    `main.py`). New `audio.set_volume(v)` / `get_volume()` module API; the
    `_play` helper now multiplies the per-cue volume by the master scaler
    so relative cue loudness is preserved. Settings AUDIO section gained
    a 0.00-1.00 slider (with live "%" label) — live-applies, persists to
    `config.json`, and main.py wires it at app launch alongside
    `audio.set_enabled`.
  All files compile + import clean (smoke-tested via stubbed DPG/pygame).
  No server changes in this batch. — `the_rift/ui/scout.py`,
  `the_rift/ui/rankings.py`, `the_rift/ui/tierlist.py`,
  `the_rift/ui/feed.py`, `the_rift/ui/commands.py`,
  `the_rift/ui/settings.py`, `the_rift/ui/audio.py`,
  `the_rift/data/reader.py`, `the_rift/main.py`
- 2026-05-22 — **Phase 3 — Scout auto player tags landed.** New
  `_compute_player_tags(r)` derives at-a-glance behavior tags (Porofessor-
  style) from existing per-player data: FORM (HOT / COLD / MIXED),
  EXPERIENCE (VETERAN ≥150g / ACTIVE ≥40g / NEWCOMER), MASTERY (OTP — X
  when top champ is ≥40% of a ≥10-game pool / VERSATILE when 5+ champs each
  ≥5g), KDA GOD (≥5.0) / KDA MONSTER (≥4.0), WIN MACHINE (wr ≥60% with
  ≥20g) / SLUMPING (wr ≤42% with ≥20g), and {role} MAIN. Pure function,
  deterministic, no cross-player normalization needed — works for one
  player before the rest of the scout corpus has loaded. New
  `_rw_player_tags(r)` section renderer inserted after the report header:
  a single horizontal row of color-coded labels separated by thin gold
  dots. `_build_full_report` now preserves raw stats on the report dict
  (`wr_raw`, `kda_raw`, `games_raw`, `primary_role`) so the tag computer
  never has to re-parse a display string. Compile + smoke-test pass across
  4 representative player profiles (HOT-OTP veteran, COLD-versatile
  newcomer, MIXED-KDA-god active, empty/None). Server-free change — uses
  existing scout-sheet + inhouse-champ data already loaded by the report
  flow. Side-by-side player compare is the next half of Phase 3 wave 2.
  — `the_rift/ui/scout.py`
- 2026-05-22 — **Phase 3 — Records & superlatives landed (server + UI + live).**
  Server: new `db.records()` aggregator computes a curated set of 13
  superlatives in one request — single-game maxes (kills / assists / damage
  / gold / CS / vision / KDA), match-level (longest, shortest, biggest
  blowout by kill-diff), per-player streaks (longest win + longest loss
  via an ordered per-player scan), and most-games-logged. Empty fields
  return `null` so the UI can show "no data yet" cards. New `/api/records`
  endpoint. Verified end-to-end against synthetic 3-match data (Alice 18
  kills / 240 CS / 18K gold; Carol 10/1/6 → 16.0 KDA; M3 = 40-min longest;
  M1 = +25 blowout). Live endpoint smoke-checked on Fly: returns 13 named
  entries, all `null` against the empty production DB. Client:
  `rift_api.get_records()` + `data.reader.load_records()` background loader
  caching on `live.records` (single-flight guarded by `_records_inflight`).
  UI: segmented control grew to a 4th pill RECORDS (`LEADER | HISTORY |
  RIVALS | RECORDS`, narrower 80-px pills to fit). New `_draw_records`
  view: responsive card grid (1-4 cols capped, auto-fits viewport), each
  card showing TITLE / big value (count-up animation) / holder + champion
  / formatted date. Cards for records with a `match_id` are clickable —
  click jumps to the HISTORY view with that match's detail panel already
  open (cross-feature link). Hover lift + gold glow + count-up follow the
  §4 polish standard; skeleton loading + designed empty state. Deployed:
  `flyctl deploy --remote-only` from `server/`; rolling update succeeded.
  — `server/db.py`, `server/api.py`, `the_rift/data/rift_api.py`,
  `the_rift/data/reader.py`, `the_rift/ui/inhouse.py`
- 2026-05-22 — **Phase 3 — Inhouse rivalries / h2h landed (server + UI + live).**
  Server: new `db.rivalries(name, limit)` SQL aggregator (single JOIN on
  participants → per-opponent {games_vs, wins_vs, games_with, wins_with,
  last_played}, sorted by total games together desc) + `/api/players/{name}/
  rivalries` REST endpoint. Verified end-to-end with synthetic 2-match /
  4-player data; live endpoint smoke-checked on Fly (`{"player":"anyone",
  "rivalries":[]}` with empty DB; `/health` + `/api/stats` still 200-OK).
  Client: `rift_api.get_rivalries(name)` wrapper; `data.reader.load_rivalries
  (name, ...)` background loader caching on `live.rivalries[anchor]` (with
  `_rivalries_inflight` de-dup so repeat clicks don't fan out parallel
  fetches). UI: top-bar swapped from 2-state toggle to a 3-pill segmented
  control LEADER | HISTORY | RIVALS (`_set_view_mode` generalizes the old
  toggle, closes cross-mode slide-ins, seeds the default rivalries-anchor =
  most-games-logged player); new `_draw_rivalries` view renders a column
  table (OPPONENT · TOGETHER · VS RECORD · WITH RECORD · LAST PLAYED) with
  win-rate-colored cells, hover glow per row, skeleton loading, designed
  empty + error states, and search-bar filter reuse. Click a row to swap
  anchor — `audio.play_click` + immediate cache lookup (or background fetch
  if cold). Deployed: `flyctl deploy --remote-only` from `server/` —
  rolling update, machine returned to good state. — `server/db.py`,
  `server/api.py`, `the_rift/data/rift_api.py`, `the_rift/data/reader.py`,
  `the_rift/ui/inhouse.py`
- 2026-05-22 — **Phase 3 — Inhouse per-game detail panel landed.** Clicking
  a match-history card opens a right-side slide-in panel (`MATCH_DETAIL_W`
  = 680 px) with the full match breakdown: header (timestamp + winner
  banner + duration / queue / patch / source), an 8-column **scoreboard**
  (role · champion · player · K/D/A · CS · gold · damage · vision — blue
  team then red, with side-accent stripes and alt-row banding), a **draft**
  block (two columns of bans + role-ordered picks, with empty-state copy
  when no draft was logged), and a **timeline** placeholder section telling
  the user per-minute data will arrive with the next Riot-API pass. New
  `InhouseState.select_match()` toggles the panel, animated with a 280ms
  out_cubic tween; click another card to swap targets, the X button or
  re-click to close. Match cards now have hover + selected visual states
  (gold border glow via `effects.hover_amt` / `draw_hover_glow`); a
  `audio.play_click()` fires on open/close. View-mode toggle now also
  closes the cross-mode panel so the layout reflows cleanly. Data is read
  straight from the cached `live.match_history` (already fully hydrated
  by `load_match_history`) — no extra fetch needed. Compile + import +
  helper-roundtrip tests pass. — `the_rift/ui/inhouse.py`
- 2026-05-22 — **Phase 2 cleanup — `_legacy_*` deleted.** Nine deprecated
  local implementations of engine functions removed now that the server
  cutover is verified end-to-end: `_legacy_recommend_comps` /
  `_legacy_recommend_bans` / `_legacy_compute_matchups` in `draft_engine.py`
  (3 funcs, -323 lines) and `_legacy_target_archetype` /
  `_legacy_archetype_pivot_check` / `_legacy_predict_enemy_next_pick` /
  `_legacy_pick_impact_delta` / `_legacy_recommend_bans_split` /
  `_legacy_recommend_action` in `draft_board.py` (6 funcs, -709 lines).
  Combined: -1,032 lines. The 9 public proxies are unchanged (same names,
  same signatures, same return shapes — verified via `inspect.signature`);
  every heavy-compute call still routes to `the-rift-draft-sync.fly.dev/api/
  engine/*` via `data/engine_api.py`. Both files re-compile and re-import
  clean. Orphaned heavy-compute helpers / data tables (e.g. `LANE_MATCHUPS`,
  `beam_search_comp`, `parse_wr`) are kept for now since some are still
  imported by UI / other modules; a follow-up dead-code audit can prune
  whatever the proxies leave unreachable. — `the_rift/data/draft_engine.py`,
  `the_rift/data/draft_board.py`
- 2026-05-22 — Phase 1 — Sheet mirror landed. New `the_rift/data/sheet_mirror.py`
  with `full_refresh()` (pulls `/api/export`, rewrites three `_RiftDB_*` tabs
  — matches / participants / drafts — as a human-readable backup) and
  `backfill_from_sheets()` (reads `_InhouseGameLog`, reconstructs match dicts
  in the same shape as the live POST, ingests in chunks of 50; idempotent
  via INSERT OR REPLACE on match id). New `rift_api.get_export()` helper.
  `full_refresh()` runs automatically after each successful log-game POST;
  both are also exposed as BACKFILL FROM SHEET + BACK UP TO SHEET buttons
  in Settings → DATA API. Compile pass. — `the_rift/data/sheet_mirror.py`
  (new), `the_rift/data/rift_api.py`, `the_rift/data/reader.py`,
  `the_rift/ui/settings.py`
- 2026-05-23 — **Phase 4 complete — new surfaces shipped.** All three Phase-4
  surfaces landed in one pass:
  * **Phase 4a — Home / Dashboard** (`ui/home.py` — new). A landing tab that
    aggregates the strongest signal from every other tab: greeting ribbon
    with live data-status pulse, top-3 power-rankings podium (clickable
    names open the Player Profile panel), rotating LEAGUE PULSE card
    (hot-take · most controversial · biggest mover · sharpest predictor),
    recent-matches strip (rows jump to Inhouse → History), three-up RECORD
    BOOK strip, full-width CURRENT SEASON card with a SEE WRAPPED chip, and
    a data-freshness ribbon. Polish-standard: skeletons on every loading
    state, designed empty/error states, count-up animations on stat values,
    localized ambient motes, all data pulled from `live.*` caches with no
    extra fetches.
  * **Phase 4b — Player Profile** (`ui/profile.py` — new). Right-side slide-
    in panel openable from any tab via `state.nav_to_profile = name`.
    Header (avatar / tier ring / name / rank / score), recent-form W/L
    sparkline (last 10), auto-tags (FORM / EXPERIENCE / MASTERY / KDA GOD /
    WIN MACHINE / role main), top-6 champion-pool grid, rivalries (top 4
    from live cache), records held, achievements (unlocked + locked
    chips), recent matches strip. Click backdrop, click X, or press Esc to
    close. Wheel-scroll inside the panel. Click-anywhere-on-dim closes.
    Wired from `main.py` (renders over every tab) — no per-tab plumbing
    required to open one.
  * **Phase 4c — Seasons & History.** Server: `seasons` table + helpers
    (`list_seasons`, `create_season`, `season_standings`, `auto_seed_season`)
    that bucket matches by date window and compute per-player W/L/WR/KDA
    rankings; `/api/seasons` (auto-seeds Season 1 on first call) and
    `/api/seasons/{id}/standings` endpoints. Client: `rift_api.get_seasons`
    / `get_season_standings` / `post_season`; `reader.load_seasons` and
    `load_season_standings` with single-flight caches; CURRENT SEASON card
    on the Home dashboard renders the active season's name/dates/match
    count/leader. Live-deployed to Fly; smoke-checked
    `/api/seasons` → Season 1 auto-seeded successfully.
  — `the_rift/ui/home.py` (new), `the_rift/ui/profile.py` (new),
    `the_rift/ui/sidebar.py` (TABS now leads with HOME + new home icon),
    `the_rift/core/state.py` (active_tab default is `home` + `nav_to_profile`
    nav slot), `the_rift/main.py` (Home in the content router, profile panel
    renders over content, 1-9 hotkeys), `server/db.py` (seasons schema +
    helpers), `server/api.py` (3 season endpoints), `the_rift/data/rift_api.py`
    (3 season wrappers), `the_rift/data/reader.py` (season caches + loaders).
- 2026-05-23 — **Phase 5 — Wow features shipped (4 of 6).**
  * **5a — Achievements** (`server/db.py` + `server/api.py` +
    `the_rift/data/rift_api.py` + `the_rift/data/reader.py` +
    `the_rift/ui/profile.py`). Server-side catalog of 11 unlockable
    achievements (first_blood / first_win / pentakill / flawless / carry /
    damage_dealer / vision_warden / streak3 / streak5 / century /
    comeback) computed on-demand from match data via
    `db.player_achievements(name)` — no per-event write needed. New
    `/api/achievements` + `/api/players/{name}/achievements` endpoints.
    Profile panel surfaces unlocked chips (gold) and locked chips (faded)
    side-by-side for visible progress.
  * **5b — Predictions + leaderboard** (`server/db.py` + `server/api.py` +
    `ui/inhouse.py`). New `predictions` table + helpers
    (`add_prediction`, `match_predictions`, `prediction_leaderboard`) and
    3 REST endpoints. Match-detail panel in Inhouse grew a PREDICTIONS
    section: tally bar (blue/red split), VOTE BLUE / VOTE RED buttons
    (live-updating my-vote highlight), accuracy line shown after a match
    has a winner. Toast confirms each vote. SHARPEST PREDICTOR rotates
    into the Home dashboard's LEAGUE PULSE card.
  * **5c — Shareable PNG cards** (`the_rift/data/share_cards.py` — new +
    `ui/profile.py` + `ui/inhouse.py`). Pillow-based card renderer with
    two flavors: `make_player_card(name)` (broadcast-style player snapshot
    with stat grid + top-5 champions + footer) and `make_match_card(mid)`
    (winner banner + 5-vs-5 scoreboard). Outputs to
    `the_rift/assets/share_cache/`, auto-copies the path to clipboard.
    SHARE button on the Profile header; SHARE PNG button in the Inhouse
    match-detail panel. Both flavours verified to ~27 KB clean PNGs.
  * **5d — Rift Wrapped** (`the_rift/ui/wrapped.py` — new). Fullscreen
    auto-cycling presentation deck: intro page → big-number GAMES PLAYED →
    SEASON MVP spotlight → ON A HEATER (longest streak) → PERFORMANCE OF
    THE SEASON (best single-game KDA) → DAMAGE DEALER → SHARPEST MIND
    (predictor) → outro. Auto-advances every 6.5s, click anywhere to skip,
    page-progress bar at the bottom. Opens via SEE WRAPPED chip on the
    Home season card; Esc closes. Renders over every tab from the main
    loop.
  Discord integration + AI Analyst remain explicitly deferred (out of
  scope for this pass per existing free-tier infra rule).
  — `server/db.py`, `server/api.py`, `the_rift/data/rift_api.py`,
    `the_rift/data/reader.py`, `the_rift/data/share_cards.py` (new),
    `the_rift/ui/wrapped.py` (new), `the_rift/ui/profile.py`,
    `the_rift/ui/inhouse.py`, `the_rift/ui/home.py`
- 2026-05-23 — **Phase 6 polish — first pass.** Hotkey overlay
  (`the_rift/ui/hotkeys.py` — new) reachable via `?` (Shift+/) and Esc to
  close: floating centered card lists 1-9 tab switches, Esc / mouse wheel /
  click-name / click-match shortcuts. First-run welcome toast surfaces the
  new Home tab + hotkey overlay (gated by `welcomed_v40` config key so it
  fires exactly once per install). Theme/accent picker, full perf sweep,
  window remember-size, and keyboard-nav for inputs remain as deferred
  polish for a future pass.
  — `the_rift/ui/hotkeys.py` (new), `the_rift/main.py`

---

## 10 · Next action

**Phase 1 is complete.** Log→DB + auto Sheet mirror + backfill + Settings
buttons + the `fetch_ranks` modularization all landed. The flow on a real
LOG INHOUSE GAME click is now: append rows to `_InhouseGameLog` → POST every
new match to `/api/matches` → pull `/api/export` and rewrite `_RiftDB_*`
mirror tabs. **Secrets rotation is explicitly out of scope** for this
workstream per user direction (user will rotate Google SA + Riot key and
`git rm --cached` on their own schedule).

### Verification (user)
1. Open the League client, queue + finish at least one new custom game.
2. App → Inhouse → LOG INHOUSE GAME. Watch the toast for success.
3. Confirm `https://the-rift-draft-sync.fly.dev/api/stats` shows
   `matches: 1+` and a recent `last_ingest`.
4. Check the Google Sheet — three new `_RiftDB_Matches` / `_RiftDB_Participants`
   / `_RiftDB_Drafts` tabs should have appeared, populated with the same
   data the server is holding.
5. Optionally hit Settings → DATA API → BACKFILL FROM SHEET to bulk-upload
   every row of the existing `_InhouseGameLog` (idempotent).

### Out of scope (user action, on user's schedule)
**Secrets hygiene** — currently `credentials.json` and
`the_rift/data/config.json` are both *tracked* in git despite
`credentials.json` being in `.gitignore` (it was added before the ignore).
When the user is ready:
- Rotate the Google service-account JSON in the GCP console.
- Rotate the Riot API key at `developer.riotgames.com`.
- `git rm --cached credentials.json the_rift/data/config.json` and commit.
- Decide config strategy: a checked-in `config.example.json` template plus a
  gitignored local `config.json`, or move api_key / sheet_url to env / a
  separate secrets file.

### Phase 2 — complete (incl. `_legacy_*` cleanup)
Engine fully cut over. Server endpoints at `the-rift-draft-sync.fly.dev/api/engine/*`
are the only path for any heavy compute; client `draft_engine.py` /
`draft_board.py` are thin proxies (~9 functions). The deprecated `_legacy_*`
mirrors were deleted on 2026-05-22 (-1,032 lines combined). Cold-start
latency is ~4s (Fly scale-to-zero wake); warm calls are ~500ms.

### Phase 3 — Inhouse match-history feed started
First Phase-3 feature is live: a HISTORY toggle on the Inhouse tab swaps the
leaderboard out for a card feed of every logged custom game, pulled from
`/api/matches`. With the DB empty, the feed shows an empty-state advising
the user to log a game. After the next LOG INHOUSE GAME the cards start
populating.

### Verification (user, after next LOG INHOUSE GAME)
1. Inhouse → LOG INHOUSE GAME → POST flows up to `/api/matches` (Phase 1).
2. Inhouse → HISTORY button → confirm the new match appears as a card with
   timestamp, duration, winner side, role-ordered champ strip.
3. Settings → DRAFT ENGINE → RUN BACKTEST. With ≥1 match the harness can
   replay it and report a hit-rate (instead of `0/0`).
4. Draft tool: open it as usual — every recommendation is now coming from
   `the-rift-draft-sync.fly.dev`. Expect a brief delay on first interaction
   if the server is cold. (The `_legacy_*` local mirrors have been removed
   now that the server cutover is verified; the previous commit
   `d78c60c` is the rollback point if anything in the draft UI breaks.)

### Next: two active workstreams
Per-tab roadmap detail lives in §6.

**A · Phase 3 — closed 2026-05-22.** Every tab wave shipped:
- ✅ Inhouse: per-game detail panel · rivalries · records & superlatives.
- ✅ Scout: auto player tags · side-by-side compare.
- ✅ Rankings: per-row sparkline · biggest mover / falling callouts.
- ✅ Tier List: cross-rater LEAGUE PULSE (consensus + hot takes).
- ✅ Activity: event-type filter chips.
- ✅ Commands: DATA FRESHNESS panel (live `/api/stats`).
- ✅ Settings: master volume slider.
Deferred to Phase 6 polish: Rankings splash parallax + explainer popover ·
Scout match-timeline curves + auto threat-report paragraph · Tier List
dedicated consensus view · Activity reactions + weekly digest · Commands
control-room scheduler + API-quota dashboard · Settings theme/accent picker.
- **Rankings: sparkline + biggest-mover callouts** — Phase 3 wave 3.
- **Tier List + Activity waves** — Phase 3 waves 4-5.

**Next: Phase 4 — New surfaces.** Home/Dashboard landing tab, Player Profile
pages, Seasons & History. Foundation work starts with the home dashboard
since it aggregates signals from every existing tab.

**B · Phase 2 deep cleanup** (engine quality + tech debt):
- ✅ `_legacy_*` removal (2026-05-22, -1,032 lines).
- Dead-code audit on the heavy-compute helpers the legacy functions used
  (e.g. `beam_search_comp`, `LANE_MATCHUPS`, `parse_wr`) — some are imported
  by UI modules, others may now be unreachable.
- Phase 2f (sharper archetype detection / pivot logic / counter-pick gating,
  expanded champion coverage, refactor `draft_engine.py` / `draft_board.py`
  for maintainability, expand self-test).

### C · Phase 4 — New surfaces (2026-05-23, complete)
Home/Dashboard tab live; Player Profile slide-in panel openable from any
tab; Seasons backend + UI shipped (server auto-seeds Season 1 on first
`/api/seasons` call). What to verify on next launch:
1. App opens on the new **HOME** tab (now the first sidebar item). The
   greeting ribbon shows the date + matches-logged chip; the podium card
   has the top-3 power-rankings entries (clickable to open profiles); the
   LEAGUE PULSE card rotates between hot-take / most-controversial / on-
   the-rise / sharpest-predictor every 7s; the SEASON card shows Season 1
   with a leader line + a SEE WRAPPED chip.
2. Press **?** anywhere to see the keyboard-shortcuts overlay; Esc closes.
3. Click any podium name on Home → the Player Profile slide-in opens with
   form sparkline, auto-tags, champion pool, rivalries, records held,
   achievements (locked + unlocked chips), recent matches, and a SHARE
   button.
4. Click the SEE WRAPPED chip on Home → a fullscreen 7-page season recap
   auto-cycles; click to skip, Esc to close.

### D · Phase 5 — Wow features (2026-05-23, complete: 4 of 6)
Achievements, Predictions, Shareable PNG cards, and Rift Wrapped all live;
Discord + AI Analyst explicitly deferred. What to verify:
5. Inhouse → click any match card → MATCH DETAIL panel now has a
   PREDICTIONS section: tally bar + VOTE BLUE / VOTE RED buttons (only
   active for matches without a winner and when `display_name` is set in
   Settings). Voting persists server-side.
6. Match detail panel also has a SHARE PNG button bottom-right that saves
   a polished card to `the_rift/assets/share_cache/` and copies the path
   to clipboard.

### E · Phase 6 — Polish & 1.0 hardening (initial pass landed)
- ✅ Hotkey overlay (`?`)
- ✅ First-run welcome toast (gated by `welcomed_v40`)
- ✅ Sidebar reordered (HOME is first)
- ⏳ Deferred for a follow-up: theme/accent picker · perf-sweep / 60fps
  audit · window remember-size · keyboard-nav for inputs / focus rings ·
  brand cohesion audit · cross-app token sweep.
