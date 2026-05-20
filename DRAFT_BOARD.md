# Draft Tool — v3 Spec

> Live spec for the synced tournament-draft tool inside The Rift. Reflects
> the v3 rewrite (Phases 1–6 of `DRAFT_REWRITE_HANDOFF.md`). The v2 "War
> Room" pipeline and cyberpunk theme were retired in Phase 6 — this doc
> is the canonical reference for what the tool does today.

---

## 1 · One-paragraph summary

Two League players hit BEGIN DRAFT on the Draft tab. They land in a
shared lobby hosted on Fly.io (single global room, no codes or
passwords). Each side claims BLUE or RED, drags 5 players into role
slots, and READYs up. The server runs a strict phase machine — LOBBY →
SCOUTING → BRIEFING → ARCHETYPE → BOARD → DONE — and each transition
unlocks the corresponding client UI. The board runs the canonical 20-
action tournament draft. The engine surfaces per-pick recommendations,
pivot alerts when a locked archetype gets wrecked, and a ghost-
suggestion chip predicting the enemy's next pick. The DONE screen
reveals both archetypes, charts the win-probability arc, and shows a
per-side game plan + a retrospective of which projected picks the
enemy banned out.

---

## 2 · Flow

```
   IDLE          CONNECTING      LOBBY            SCOUTING         BRIEFING        ARCHETYPE         BOARD                    DONE
                 (cold-start)                                                      (HIDDEN)
┌─────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌─────────┐       ┌──────────┐            ┌──────────┐
│ BEGIN   │ →  │ rotating │ → │ side     │ →  │ FETCHING │ →  │ snapshot │ →  │ pick 1  │ →     │ 20-step  │ →         │ both     │
│ DRAFT   │    │ gold rune│    │ swap +   │    │ SCOUT    │    │ projected│    │ of 7    │       │ tournament│  20 acts  │ archetypes│
│ (1 btn) │    │          │    │ team-    │    │ DATA     │    │ comps +  │    │ archetypes      │ draft     │           │ revealed  │
│         │    │          │    │ build    │    │ ████████░│    │ key bans │    │ secret  │       │ live recs │           │ + WR chart│
│         │    │          │    │ READY    │    │ 9 / 10   │    │ 5s timer │    │ from    │       │ + pivot   │           │ + game plan│
│         │    │          │    │          │    │          │    │          │    │ enemy   │       │ + ghost   │           │ + retro    │
└─────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘    └─────────┘       └──────────┘            └──────────┘
```

CONNECTING + SCOUTING share the same waiting-screen primitive
(splash-art backdrop + slow-rotating gold rune ring + status text +
progress bar). Solo fallback: after 30s in the LOBBY with no opponent,
a "Continue solo (briefing only)" link disconnects + jumps straight
LOBBY → BRIEFING → IDLE.

---

## 3 · Phase descriptions

### IDLE — `_draw_idle`

Single big **BEGIN DRAFT** button centred over a daily-rotating champion
splash. A connection-status hint surfaces only if the WS is in an
interesting state (connecting / error). Click → `_sync_ui.auto_connect()`
and transition to CONNECTING.

### CONNECTING — `_draw_connecting`

`lol_theme.draw_waiting_screen` (slow-rotating gold rune + status text).
Auto-advances to LOBBY when the first server snapshot lands.

### LOBBY — `_draw_sync_lobby` (local: `TEAM_BUILD` phase)

LCS broadcast lobby. Two roster boxes (BLUE / RED) with role-tag strips
on the left edge. Hosts drag players from the bottom pool into slots.
Side toggle in the header lets either party swap freely. WHO'S
CONNECTED rail shows up to 5 connection slots per side + spectators.
**READY UP** button at the bottom; both sides must ready up for the
server to advance.

Solo fallback (Phase 5): if only one side is claimed, a slim banner
above the READY button shows a 30s countdown. After timeout the user
can click "Continue solo (briefing only)" to disconnect + run a
one-shot BRIEFING preview locally.

### SCOUTING — `_draw_scouting`

Server transitions LOBBY → SCOUTING when both sides ready up. Each
client locally batched-fetches the 10 scout sheets via
`prefetch_scout_sheets(names, on_progress=...)`. The progress callback
updates `draft.scout_progress[name] = 1`. The UI renders the waiting
screen + a 2-column (BLUE/RED) per-player dot panel (gold = pending,
win = done, loss = failed). When all 10 dots are green, the client
sends `set_scout_ready(True)`.

### BRIEFING — `_draw_briefing`

5-second strategic preview. `_compute_briefing_data` runs once per
entry: two `recommend_comps` calls + two `recommend_bans` calls (one
per side). Two side-by-side cards show projected archetype label, 5
projected picks, 3 top bans. The 5s auto-advance sends
`set_briefing_done(True)`; a manual CONTINUE button short-circuits.

### ARCHETYPE — `_draw_archetype` (hidden per side)

Each side picks one of 7 archetype cards on a screen the OTHER side
cannot see. Server stores the per-side choice and only broadcasts it
cross-side at DONE. Cards laid out in a 4×2 grid using
`lol_theme.draw_archetype_card` (AP/AD damage bar + 5 projected picks +
viability tag). Click stages `draft.archetype_pending`; CONFIRM fires
`set_archetype(arch)`. Server auto-advances when both sides confirm.

### BOARD — `_draw_board`

The 20-action tournament draft. Layout:

```
┌────────────────────────────── HEADER (gold rule) ─────────────────────────────┐
│ DRAFT BOARD                    MANUAL / SYNCED                  YOU: BLUE     │
├────────────── Timeline (20 cells, side-tinted, focal pulse on current) ──────┤
│                                                                                 │
│ ┌─ BLUE OPS ─┐   ┌─ ACTION BANNER ─┐   ┌──── ANALYTICS RAIL ─────┐            │
│ │ 5 role     │   │ TOP CALL hero    │   │ win-prob bar + spark    │            │
│ │ slots +    │   │ card w/ splash   │   │ WHY THIS CALL bars      │            │
│ │ pool-depth │   │ + tag chip +     │   │ TEAM STRENGTH radar     │            │
│ │ capsule    │   │ confidence meter │   │ DAMAGE PROFILE          │            │
│ │ + BANS row │   │ + viability      │   │ COUNTER COVERAGE donut  │            │
│ ├────────────┤   │ + per-player WR  │   │ COUNTER PREDICTOR rows  │            │
│ │ RED OPS    │   │ + alternatives   │   │ SYNERGY WEB graph       │            │
│ │ 5 role     │   │ + manual pool    │   │ CONTESTED ladder        │            │
│ │ slots ...  │   │   grid w/ search │   │                         │            │
│ │ (ENEMY:    │   │                  │   │                         │            │
│ │  GHOST     │   └──────────────────┘   └─────────────────────────┘            │
│ │  CHIP)     │                                                                 │
│ └────────────┘                                                                 │
│  PIVOT ALERT BANNER (when archetype wrecked, slides in below timeline)        │
│  ─ NARRATIVE LOG (history of recent picks/bans) ──                            │
└─────────────────────────────────────────────────────────────────────────────────┘
```

Pivot alert (Phase 4.5): `archetype_pivot_check` runs after every action
when the user has a locked archetype. On rising-edge of `wrecked=True`,
a 60px-tall banner slides in below the timeline with two pivot-option
buttons that commit a new archetype via `set_archetype`.

Enemy ghost chip (Phase 4.6): `predict_enemy_next_pick` runs once per
frame. The result overlays a translucent `draw_ghost_suggestion_chip`
on the matching empty enemy slot rect. The chip fades on the actual
lock.

### DONE — `_draw_done_summary`

End-of-draft recap. Header (Cinzel + gold rule), then four stacked
panels:

1. **Win-prob progression chart** — sparkline of
   `board_rail._cache["history"]`, midline at 50%, side-tinted polyline
   (blue if final WP ≥ 0.5, red otherwise), final WP% in the corner.
2. **Per-side game-plan cards** — for each side, the locked archetype's
   `label` + a 3–4 line wrap of its `game_plan` string from the engine
   `ARCHETYPES` dict.
3. **"What got banned" retrospective** — two columns of projected picks
   per role per side, with a win/loss dot indicating whether the OTHER
   side banned the projected pick.
4. **NEW DRAFT button** (gold-bordered) — wipes board state and returns
   to IDLE.

---

## 4 · Audio (Phase 5)

`the_rift/ui/audio.py` is a `pygame.mixer` wrapper. Six cues:

| Function          | When                                            |
|-------------------|-------------------------------------------------|
| `play_lock`       | Pick locked (any side)                          |
| `play_ban`        | Ban locked (any side)                           |
| `play_turn`       | Current action's side becomes `our_side`        |
| `play_archetype`  | User confirms their archetype                   |
| `play_pivot`      | Pivot-alert banner first appears (wrecked edge) |
| `play_draft_end`  | Final action of the draft lands                 |

All non-blocking. Skipped silently when:

- `pygame` isn't importable
- the mixer didn't initialise (no audio device)
- the WAV file isn't present on disk
- the user unchecked "Enable audio cues" in Settings

Mute toggle in `ui/settings.py` persists `audio_enabled` in `config.json`.
`main.py` applies the saved value to `audio.set_enabled` at startup.

---

## 5 · Theme

LCS/LEC broadcast aesthetic. All draw primitives live in
`the_rift/ui/lol_theme.py`. Palette:

| Key             | Use                                       |
|-----------------|-------------------------------------------|
| `navy_deep`     | Deepest background                        |
| `navy_mid`      | Header strips, mid-tier backgrounds       |
| `navy_panel`    | Card / panel fill                         |
| `gold`          | Primary accent (borders, CTAs)            |
| `gold_lt`       | Text highlight                            |
| `gold_rule`     | Thin rules + neutral borders              |
| `gold_dk`       | Button-dark fill                          |
| `blue_side`     | BLUE-side accents                         |
| `red_side`      | RED-side accents                          |
| `win`           | Positive states                           |
| `loss`          | Hard error / banned                       |
| `warning`       | Cautious states / pivot                   |

Primitives include `draw_waiting_screen`, `draw_navy_panel`,
`draw_gold_rule`, `draw_splash_banner`, `draw_role_glyph`,
`draw_progress_bar`, `draw_player_portrait_frame`, `draw_pick_chip`,
`draw_ban_chip`, `draw_arc_meter`, `draw_archetype_card`,
`draw_pivot_alert_banner`, `draw_ghost_suggestion_chip`,
`draw_sample_size_badge`, `draw_pool_depth_badge`,
`draw_recent_form_dots`. **No full-screen ambient motion** — focal
motion only (per `feedback_ambient_motion`).

---

## 6 · Server (Fly.io)

Single file: [`server/main.py`](server/main.py). FastAPI + WebSocket.
Hosted at `wss://the-rift-draft-sync.fly.dev` (config in
[`server/fly.toml`](server/fly.toml), `auto_stop_machines = "suspend"`
for ~1–2s cold start).

**Single global room.** First connect claims BLUE, second claims RED,
the rest become SPEC. No room codes, no passwords. Sides swap freely
until both ready up.

**Phase machine on the server is the source of truth.** Per-side gate
flags (`ready`, `scout_ready`, `briefing_done`) and per-side
`archetype` storage. The server advances phases when both sides clear
their respective gates. `archetype` is hidden cross-side until DONE
(server-mediated info asymmetry).

Wire protocol — client → server:

```
{type:"set_side",         side:"BLUE"|"RED"|"SPEC"}
{type:"set_ready",        ready:bool}                # LOBBY only
{type:"set_scout_ready",  ready:bool}                # SCOUTING only
{type:"set_briefing_done",done:bool}                 # BRIEFING only
{type:"set_archetype",    archetype:string|null}    # ARCHETYPE / BOARD
{type:"set_slot_player",  side, idx, player:{...}}   # host only
{type:"apply",            champ, role}               # BOARD only
{type:"undo"} / {type:"reset"} / {type:"reassign", side, from_role, to_role}
{type:"chat", text} / {type:"ping"}
```

Server → client: `hello` on connect, `state` on every change (rev-bumped,
personalised), `chat`, `error`, `pong`.

---

## 7 · Engine

[`the_rift/data/draft_engine.py`](the_rift/data/draft_engine.py) holds
all scoring tables + the 7-archetype dict. Recommend functions:

- `recommend_action(state, ...)` — top-N picks/bans for the current
  action, with `factors` dict per suggestion (comfort, counter, lane,
  contested, blind_safe, flex, steer).
- `recommend_comps(roster, ...)` — projected comps for a side, sorted
  by viability.
- `recommend_bans(opposing_players, ...)` — top-N enemy threats to ban.
- `target_archetype(roster, ...)` — single best archetype + projected
  picks for a side, returns `game_plan` + `win_condition` + `spike`.

Engine helpers (Phase 2):

- `champion_comfort(player, champ, ...)` — recency-weighted comfort
  score factoring inhouse customs + ranked/draft chronology from scout
  sheets (`results` per champ, half-life 18 customs / 24 ranked).
- `off_role_severity(player, role, ...)` — 0..1, decays comfort when a
  player is forced off-primary.
- `sample_confidence(games)` → `"thin"/"ok"/"strong"`.
- `pool_depth(player, role, ...)` → `"DEEP"/"OK"/"SHALLOW"/"OFF-ROLE"`.

Board helpers (Phase 2):

- `archetype_pivot_check(state, side, current_arch, ...)` — fires when
  viability band drops or a key axis is killed; tighter threshold during
  enemy phase-1 bans.
- `predict_enemy_next_pick(state, ...)` — `{champ, role, player,
  confidence, action_idx}`.
- `pick_impact_delta(before, after, side, ...)` — WR swing per pick.

`SLOT_ROLE_BIAS` (per-action-index role multipliers) reflects pro
convention: B1 favours JGL/BOT, R5 favours TOP, etc. Counter-pick
gating at R3/B5/R5 forces `score = 0.65·cv + 0.20·cmf + 0.15·lane` when
`cv ≥ 0.70` against a same-lane locked enemy.

`COUNTERS` table is rescaled to 0.30–0.90 range (was 0.10–0.50) with
~45 new entries for the 2025/2026 meta (Ambessa, Mel, Aurora, Hwei,
Smolder, K'Sante, Briar, Naafiri, Bel'Veth, Sylas, Renata Glasc, Senna,
Akshan).

---

## 8 · Scout chronology

Scout sheets carry a `Results` column (M) with comma-joined
chronological results per champ (`1,0,1,1,0,...`).
`prefetch_scout_sheets` → `analyze_player` preserves the per-game
sequence; `_parse_scouting_sheet` parses it back into `results: [int,
int, ...]`. The engine passes this through `champion_comfort` so the
ranked-pool recency boost is real (vs. tossing chronology during
aggregation). The Scout tab's RECENT column renders the last 10 dots
inline.

---

## 9 · Key files

| Layer | Path | Role |
|---|---|---|
| Server | [`server/main.py`](server/main.py) | FastAPI WS, phase machine |
| Server | [`server/fly.toml`](server/fly.toml) | Fly.io deploy config |
| Engine | [`the_rift/data/draft_engine.py`](the_rift/data/draft_engine.py) | Champion + scoring tables, archetype dict |
| Board state | [`the_rift/data/draft_board.py`](the_rift/data/draft_board.py) | 20-action seq + recommend_action + pivot/predict/impact |
| Sync client | [`the_rift/data/draft_sync.py`](the_rift/data/draft_sync.py) | WebSocket client, thread-safe |
| Sheets I/O | [`the_rift/data/reader.py`](the_rift/data/reader.py) | Sheets parsing + scout prefetch |
| Scout script | [`the_rift/data/fetch_ranks_gsheets.py`](the_rift/data/fetch_ranks_gsheets.py) | Commands → Full Scout backend |
| Config | [`the_rift/data/config.py`](the_rift/data/config.py) | Settings (sync url, audio_enabled) |
| Draft UI | [`the_rift/ui/draft.py`](the_rift/ui/draft.py) | Main rendering + input + phase machine |
| Right rail | [`the_rift/ui/board_rail.py`](the_rift/ui/board_rail.py) | Win-prob, breakdown, radar, donut, etc. |
| Sync bridge | [`the_rift/ui/draft_sync_ui.py`](the_rift/ui/draft_sync_ui.py) | Phase predicates + send helpers |
| Theme | [`the_rift/ui/lol_theme.py`](the_rift/ui/lol_theme.py) | LCS broadcast draw primitives |
| Audio | [`the_rift/ui/audio.py`](the_rift/ui/audio.py) | pygame.mixer cue wrapper |
| Settings | [`the_rift/ui/settings.py`](the_rift/ui/settings.py) | Audio mute toggle + sheet config |
| Spec | [`the_rift/the_rift.spec`](the_rift/the_rift.spec) | PyInstaller bundle config |

---

## 10 · Rules / preferences specific to this work

- **No reverting to cyberpunk theme** — the v2.7 cyber.py module + its
  palette keys were deleted in Phase 6. Explicit user decision; no
  rollback path.
- **No full-screen ambient motion** — focal motion only (per
  `feedback_ambient_motion`).
- **No intermediate PyInstaller builds during the rewrite** — single
  final build at the end of Phase 6 per user's explicit override.
- **Work in the main directory**, not `.claude/worktrees/*`.
- **Don't push to GitHub or tag releases** until the user has verified
  the build (per `feedback_no_push_before_verify`).
