# THE RIFT — Dear PyGui Rewrite: Phased Plan

**Created:** 2026-05-07  
**Backup of current launcher:** `launcher_tkinter_backup.py`

---

## Tech Stack
- **UI:** `dearpygui` (MIT, GPU immediate-mode)
- **Fonts:** Cinzel Decorative (splash/header title), Rajdhani Bold (screen headers + tab labels), Segoe UI (all data/table content), Consolas (console)
- **Crown:** 2D silhouette rendered from `heavy is the crown.stl`, exported as gold-gradient PNG texture, loaded into DPG
- **Data layer:** Unchanged — `fetch_ranks_gsheets.py`, `inhouse_tracker.py`, existing background thread model
- **Bundle:** PyInstaller single `.exe` (~25–35MB with DPG DLLs + fonts + assets)

---

## Palette

### Direction A — "The Vault" (Baseline)
```
bg          #05080d   — background void
panel       #0b1320   — panel surface
card        #0d1e30   — card depth
gold        #c8a86a   — brand gold (keep exactly)
gold_lt     #e8d5a3   — gold hover/active
gold_dk     #5c4520   — gold border/shadow
platinum    #9eb4c8   — #2/#3 accents, secondary labels
win         #4fa882   — win state teal
loss        #b84535   — loss state red
rule_gold   #463714   — section dividers (1px, named sections only)
rule_dark   #1a2535   — table/panel dividers
txt         #d8cfba   — body text
txt2        #7a7263   — secondary text
rift_purple #6b2fa0   — "THE RIFT" splash title (Cinzel Decorative)
```

### Direction C — Rank Badge Fills (badges only)
```
challenger  #c8a86a   — Challenger/GM
diamond     #3a60a8   — Diamond
platinum_b  #4a8090   — Platinum
emerald     #3aad7a   — Emerald
gold_b      #a07828   — Gold
silver_b    #8a8a9a   — Silver
bronze_b    #7a4a28   — Bronze
iron_b      #4a3828   — Iron
```

---

## Design Decisions

| Decision | Choice |
|----------|--------|
| Window chrome | Borderless (`decorated=False`), custom drag region |
| App name | THE RIFT |
| Startup | Full splash screen before main UI |
| Rank reveal | #1 first with max fanfare, then #2/#3, then #4–10, then rest |
| Tab switching | Directional slide |
| Loading states | Pulsing Rift logo + fun fact card (word doc to be provided) |
| Sound | Visual only |
| Rankings layout | Full cinematic — #1 full-width hero, #2/#3 flanking, rest scroll below |
| Player icons | Hexagon crop, manual upload linked to Riot summoner via API |
| Score display | Power ranking score is the primary visual anchor |
| Draft layout | War room (dense), avatar assembly animation during computation |
| Inhouse game logged | Animated notification card slam-in |
| Tier list | Solo use, no dramatic reveal needed |
| Target resolution | 60% 1080p / 40% 1440p, DPG global scale |
| Distribution | Single .exe, file size is not a concern |
| Scope | UI rewrite only — data/logic layer untouched |
| Background | Very subtle animated noise/grain texture |
| Tab nav | Left sidebar, collapsed (icons only), expands on hover |
| Tab icons | Swords=Rankings, Shield=Draft, Magnifier=Scout, + etc. |
| Profile icon shape | Hexagon crop |
| Ranks 11+ | Scroll down below top 10 on same screen |

---

## File Structure
```
the_rift/
  main.py                   ← entry point
  theme.py                  ← DPG theme + color registry
  assets/
    crown.png               ← rendered from STL silhouette (heavy is the crown.stl)
    crown_glow.png          ← blurred gold version for splash pulse
    noise_tile.png          ← subtle background grain texture
    icons/                  ← tab sidebar icons (24x24 PNG)
    profile_icons/          ← per-player uploaded hexagon crops ({puuid}.png)
  fonts/
    CinzelDecorative-Bold.ttf
    Rajdhani-Bold.ttf
    Rajdhani-SemiBold.ttf
  ui/
    splash.py               ← loading screen + animation sequence
    sidebar.py              ← left nav (collapsed icons, hover expand)
    rankings.py             ← cinematic reveal state machine
    draft.py                ← war room + avatar assembly
    scout.py                ← scouting table + graphs
    inhouse.py              ← leaderboard + game-logged animation
    tierlist.py             ← tier list builder
    settings.py             ← profile icon upload + Riot API link
    commands.py             ← admin tab
  core/
    state.py                ← global app state (all data lives here)
    animations.py           ← tween engine (lerp, easing, callbacks, particle system)
    profile_store.py        ← profile icon storage + Riot summoner linking
  data/                     ← existing files, untouched
    fetch_ranks_gsheets.py
    inhouse_tracker.py
    config.py
```

---

## Phase 0 — Foundation `~15h`
*Everything else depends on this being solid.*

**Deliverables:**
- DPG borderless window (`decorated=False`) with custom drag region (click-drag on title area moves window, X button drawn by us)
- Global theme applied — all Direction A colors wired into `dpg.create_theme()`
- Font registry loaded at startup — Cinzel Decorative, Rajdhani Bold/SemiBold, Segoe UI, Consolas
- Crown asset pipeline: Python script reads `heavy is the crown.stl` → extracts front silhouette polygon → renders gold-gradient PNG via PIL → saves to `assets/crown.png` and blurred `assets/crown_glow.png`
- Noise texture: PIL-generated subtle grain tile loaded and tiled across background
- **Tween engine** (`core/animations.py`):
  - `Tween(from_val, to_val, duration_ms, easing, on_update, on_done)`
  - Easing curves: linear, ease-out-cubic, ease-in-out, elastic-out (for slams)
  - `ParticleSystem(origin, color, count, spread)` — N dots, random velocities, fade+shrink over 800ms
  - `Ripple(origin, color, max_radius, duration_ms)` — expanding DPG circle, fades out
  - All driven by `animation_tick()` called every frame from DPG render loop
- Left sidebar skeleton: collapsed (48px, icon only), expands to 160px on hover with text labels fading in
- PyInstaller `.spec` file wired up — single `.exe` confirmed buildable at end of phase

---

## Phase 1 — Splash Screen `~8h`
*First impression. Sets the tone for everything.*

**Animation sequence:**
1. Window opens — pure `#05080d`, nothing visible
2. **400ms:** Crown PNG fades in (opacity 0→1), centered, ~160px wide
3. **300ms after crown:** "THE RIFT" in Cinzel Decorative 52pt, `#6b2fa0`, letter-spaced — block fade-in
4. **200ms after title:** 1px gold rule draws from center outward, 120px total
5. **Pulsing begins:** Crown enters slow sine-wave glow pulse (crown.png ↔ crown_glow.png blend, ~2s cycle)
6. **Fun fact card slides in** from bottom — `panel` bg, `rule_gold` border, text in Segoe UI 10pt italic `txt2`. Slides from y+40 to rest over 350ms ease-out. Swaps every ~8s with slide-out/slide-in.
7. **Background thread** is already running Google Sheets + config load during all of the above
8. **On data ready:** thin gold progress bar at bottom fills to 100%, main UI cross-fades in over 400ms

**Reused in all loading states across the app:** Crown + "THE RIFT" at smaller scale (~60px crown, 24pt title) with the same pulse and fun fact card.

---

## Phase 2 — Rankings Tab: Cinematic Reveal `~20h`
*The centrepiece of the app.*

### Profile Icon System
- Settings screen: player clicks upload → picks image file → app calls Riot API with their summoner name (from Google Sheet player list) to confirm account and get `puuid` → image hex-cropped via PIL → saved as `assets/profile_icons/{puuid}.png`
- If no icon uploaded: styled placeholder hexagon with player's initials

### Reveal State Machine
One-shot per data load, not re-triggerable.

```
IDLE → LOADING → CARDS_HIDDEN → REVEAL_REST_FIRST →
REVEAL_CHALLENGERS → REVEAL_3 → REVEAL_2 → REVEAL_1 → DONE
```

**LOADING:** Pulsing rift logo + fun fact card fills the rankings area.

**CARDS_HIDDEN:** Data ready. Logo fades out. 10 dark mystery cards appear — `card` bg, hexagon placeholder, "?" in gold. Animated shimmer sweeps across all simultaneously.

**REVEAL_REST_FIRST (ranks 11+):** Stagger-slide in from left, 40ms apart, no fanfare. Builds below while top 10 remain mystery cards.

**REVEAL_CHALLENGERS (#4–10, bottom-to-top):** Starting #10 → #4. Each card flips (180° Y-axis tween, 180ms). 120ms gap between flips. Profile hexagon slides in from card's left side simultaneously.

**REVEAL_3:** 500ms pause. #3 **slams** from 80px above with elastic-out easing. Impact: bronze particle burst (20–30 particles, `#cd7f32`, spread upward/outward, 700ms fade) + bronze ripple ring (200px max radius, 500ms). Player name fades in 200ms after.

**REVEAL_2:** 700ms pause. Same slam with silver particles + silver ripple. Card slightly larger than challengers.

**REVEAL_1 — The Big Moment:**
- Card slams from 120px above with harder elastic overshoot
- **Gold particle burst:** 50+ particles, multi-directional, some arcing upward
- **Double ripple:** two expanding gold rings from impact, 50ms apart
- **Screen flash:** background pulses `#0d1b2a` for 80ms then returns (shockwave)
- Card is ~20% taller than all others
- Player name in Rajdhani Bold 28pt fades in with scale-up (90%→100%, 300ms)
- Gold accent corners (L-shapes) draw onto card 400ms after slam
- Medal border breathing glow begins 600ms after slam

**DONE:** All cards visible, sidebar becomes interactive.

---

## Phase 3 — Draft Tab: War Room `~18h`

### Avatar Assembly Animation
1. Blue team (left) and red team (right) areas defined. Gold rule divider center. Win meter between them.
2. 10 player hexagons fly in — blue from left edge, red from right edge — curved paths to slot positions. 60ms stagger between players. 500ms each, ease-out.
3. On all landed: blue side pulses `#0a1e3a`, red side pulses `#1e0a0a` (team lock flash).
4. During computation: "ANALYSING..." pulses beneath each team. Win meter shows pulsing loader.
5. On data ready: war room layout (champion suggestions, matchup stats, bans) fades in over assembled teams, 400ms.

### Win Meter
- Starts at 50%, animates to result with ease-in-out over 1.2s
- > 50%: fills gold toward blue side. < 50%: fills toward red.
- Large Rajdhani Bold number counts up/down simultaneously
- Result number holds with a brief scale-pulse on arrival

### War Room Layout
Three panels below the team strip, fading in after win meter settles:
- **Left — Blue Team Strategy:** 5 ban recommendation slots + 5 team composition suggestions
- **Center — Player vs Player:** 5 role-matched rows (Blue TOP vs Red TOP, etc.), each with a win probability bar and notes. _Logic to write:_ pull each player's recent match history from Sheets/Riot API, find games where these two players were in the same role on opposite teams (or estimate from champion pool + rank delta), compute head-to-head win rate. Fallback to rank-score differential if no direct matchup history exists.
- **Right — Red Team Strategy:** Same layout as left but for red team — 5 ban slots + 5 comp suggestions

---

## Phase 4 — Scout Tab `~10h`

- Tab opens: pulsing rift logo while Riot API fetches
- On ready: table headers snap in instantly
- Rows stagger-slide in from left, 35ms apart, ease-out (full table builds in <400ms)
- DPG native `add_plot` graphs animate data series drawing left-to-right over 600ms
- Search/filter: filtered rows re-stagger-animate on update
- **Player names are clickable** — opens full scouting report overlay window (DPG floating window, natively scrollable)

### Player Score Computing Logic

The **Power Rating Score** shown in the scout table and at the top of each player report is a composite metric combining solo-queue rank performance with inhouse game history. Formula:

```
power_score = tier_score * 0.60 + inhouse_score * 0.40
```

**Tier Score (60% weight) — from Google Sheets rank data:**
```
base = RANK_SCORES[tier][division]   # e.g. Platinum I = ~1700, pulled from fetch_ranks_gsheets.py
lp_bonus = current_lp / 100.0       # fractional division progress (0–1.0)
tier_score = base + lp_bonus * DIV_OFFSET[tier]  # DIV_OFFSET ≈ 100–200 per tier
```
- Uses the same `RANK_SCORES` / `DIV_OFFSETS` constants already defined in `fetch_ranks_gsheets.py`
- Challenger/Grandmaster: use LP directly scaled to a ceiling above Diamond I

**Inhouse Score (40% weight) — from inhouse_tracker.py game log:**
```
win_rate   = wins / max(1, wins + losses)          # 0.0 – 1.0
kda_avg    = (kills + assists) / max(1, deaths)    # average KDA over last N games
dmg_share  = avg_damage_dealt / avg_team_damage    # damage share vs team avg (0.0–1.0)
vision_avg = avg_vision_score                      # raw average

inhouse_score = (
    win_rate    * 500   +   # 0–500 pts
    min(kda_avg, 5) / 5 * 250 +  # 0–250 pts (capped KDA)
    dmg_share   * 150   +   # 0–150 pts
    min(vision_avg, 50) / 50 * 100  # 0–100 pts
)  # total range: 0–1000
```
- Falls back to `tier_score * 0.40` if a player has < 3 inhouse games recorded (insufficient sample)

**Normalization:** After computing raw scores for all active players, scores are percentile-ranked within the group (0–100 scale) for display in the table. The raw score is shown in the full report tooltip. This prevents a single high-rank outlier from compressing everyone else.

**Columns in scout table derived from this:**
- `SCORE` — normalized percentile (0–100)
- `TIER` — formatted rank string (e.g. "Plat I 74LP")
- `W/L` — inhouse wins/losses
- `KDA` — inhouse KDA average
- `DMG` — avg damage dealt per inhouse game
- `VISION` — avg vision score per inhouse game

**Data sources:**
- Rank data: `data/fetch_ranks_gsheets.py` → Google Sheet "Player Rankings" tab
- Inhouse stats: `data/inhouse_tracker.py` → Google Sheet "Inhouse Log" tab
- Match history (for form section): Riot API `/lol/match/v5/matches` — last 10 ranked games per player

---

## Phase 5 — Inhouse Tab `~10h`

- Leaderboard: same stagger-slide as Scout
- **"Game Logged" notification:** 180×80px card slams in from top-right corner, elastic-out overshoot. Shows game result summary. Holds 3s. Slides back out upward. Gold micro-burst on entry.
- Player detail panel slides in from right on row click
- Win/loss trend sparkline animates its line drawing over 400ms

---

## Phase 6 — Tier List, Settings, Commands `~8h`

**Settings — Profile Icon Upload:**
- Summoner name input → "Verify with Riot" → shows confirmed account + rank → file picker appears → hexagon preview → "Save"
- Error states inline (summoner not found, image too small)

**Tier List:**
- Drag-and-drop champion cards into tier rows
- Card snaps into slot with scale-bounce on drop
- Tier row accent colors: S=gold, A=platinum, etc.

**Commands/Admin:**
- Purely functional, clean styling, no drama

---

## Phase 7 — Production Polish & Build `~8h`

- **Resolution scaling:** `dpg.set_global_font_scale()` + dynamic layout math. 1080p native, 1440p proportional. Test both.
- **Frame budget:** Animation tick must run <2ms per frame for solid 60fps. Profile particle-heavy frames.
- **Asset preloading:** All textures and fonts loaded at startup, never mid-animation.
- **PyInstaller spec:** Bundle DPG DLLs, `assets/`, `fonts/`, `data/` (excluding secrets). Single `.exe`, ~25–35MB.
- **Graceful degradation:** Riot API unreachable → show retry, don't crash.
- **Version bump → build → user verifies → GitHub release**

---

## Timeline Estimate

| Phase | Description | Hours |
|-------|-------------|-------|
| 0 | Foundation | ~15h |
| 1 | Splash screen | ~8h |
| 2 | Rankings cinematic reveal | ~20h |
| 3 | Draft war room | ~18h |
| 4 | Scout tab | ~10h |
| 5 | Inhouse tab | ~10h |
| 6 | Tier list + Settings + Commands | ~8h |
| 7 | Production polish + build | ~8h |
| **Total** | | **~97h** |

---

## Resolved Decisions

1. **"THE RIFT" splash title:** Character-by-character typewriter reveal (~4 chars/frame, ~300ms total)
2. **Sidebar icons:** Programmatic — geometric flat icons drawn with DPG drawing API, no asset files needed

---

## Notes

- Fun facts word doc to be provided by user when Phase 1 begins
- Purple color `#6b2fa0` is a starting point — to be refined during Phase 1
- Crown STL source: `C:\Users\blhei\Downloads\heavy is the crown.stl` (180 triangles, binary format)
- All existing data logic stays in `data/` untouched — UI rewrite only
- Do not push to GitHub until user verifies each build
