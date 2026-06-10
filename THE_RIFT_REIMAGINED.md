# THE RIFT — v5: VISUAL IDENTITY V2

**Status:** active — visual identity v2 greenlit 2026-06-10
**Predecessor:** THE_RIFT_UPGRADE.md (v4 initiative, completed & removed)

---

## League reality (read this first)

There are **no seasons and no scheduled games**. The Rift serves a friend
group that plays pickup customs whenever enough people are online. Features
framed around standings races, scheduled game nights, or league-office
ceremony don't fit and were explicitly rejected (2026-06-10).

The **draft assist is done** — the user likes where it is. Don't rework it.
The only acceptable draft-tab changes are visual-language consistency passes.

## Scope

1. **Visual identity v2** (greenlit) — make the whole app look and feel
   stunning, inside the locked navy/gold LCS language and animation stance
   (persistent focal motion + subtle localized ambient, intensity slider,
   no full-screen drift).
2. **Richer features on non-draft tabs** — proposals below, framed for a
   casual pickup group; user picks from the menu.

---

## Pillar — Visual identity v2 (greenlit)

From *flat* navy/gold to *deep + cinematic*:

- **V2.1 Tab wipe transitions** — ~260ms gold-line sweep between tabs;
  broadcast "rejoin" feel, app-wide, immediately felt.
- **V2.2 Hero depth system** — on hero surfaces (Home hero, Profile header,
  Wrapped pages): darkened champion-splash backdrop with very slow drift
  (Ken Burns), vignette, noise-tile grain, foreground gold corner accents.
  Splash always 60–75% darkened, never behind body text.
- **V2.3 Gold particle moments** — event-driven only: record broken,
  rank-up detected, new leaderboard #1, game logged. Hooks into existing
  toast/effects systems.
- **V2.4 Broadcast chrome** — lower-third nameplates for player rows,
  LIVE-style pulse accents, oversized numeral moments (72px stat callouts),
  consistent panel header system across all tabs.
- **V2.5 Typography discipline** — Cinzel only for ceremonial moments;
  Rajdhani everywhere else; audit stray sizes.
- **V2.6 Fullscreen / TV scaling** — make the fixed 1280×800 layout scale
  to fullscreen for big-screen use. (Bigger lift — separate phase.)
- **V2.7 Ambient intensity slider** in Settings governing all of the above.

## Menu — richer features for a pickup group (pending picks)

All grounded in data the backend already has; none assume seasons:

- **Match detail view (Inhouse)** — click any logged game → full box score,
  team gold/damage split, MVP highlight. Data exists per game already.
- **Duo synergy (Inhouse/Profile)** — "best teammates" winrate-together
  matrix, complement of the existing opponents h2h matrix.
- **Rank journey (Rankings)** — rank/LP history graph per player over time
  (rank snapshots already exist), promotion/demotion callouts in the feed.
- **Aggregate tier list (Tierlist)** — merge everyone's tier lists into a
  community consensus board; show disagreement hotspots.
- **Rolling "Rift Recap" (Wrapped)** — on-demand recap of the last N games
  / last month instead of end-of-season only.
- **Badges & achievements showcase (Profile)** — surface the existing
  achievements endpoint as a trophy-case grid with reveal animation.
- **Share card v2** — redesigned player/match PNG cards in the v2 visual
  language; optional Discord webhook auto-post.
- **Ctrl+K command palette** — jump to any player/tab/action.

## Sequencing

| Phase | Scope |
|-------|-------|
| 1 | V2.1 wipes + V2.4 panel-header consistency (app-wide feel shift) |
| 2 | V2.2 hero depth on Home + Profile + Wrapped |
| 3 | V2.3 particle moments + V2.7 intensity slider |
| 4 | Feature picks from the menu |
| 5 | V2.6 fullscreen scaling |

## Constraints (locked)

- Free-tier infra only; existing small Fly spend OK.
- Navy/gold theme + Cinzel/Rajdhani/JetBrains Mono stay.
- Animation stance: focal + localized ambient, intensity slider, no
  full-screen drift.
- Draft assist: hands off (visual consistency only).
- No push/tag/release until the user verifies a build; rebuild dist/ first.

## Change log

- 2026-06-10 — v5 scope reset after user feedback: no seasons/scheduled
  games; visual identity v2 greenlit; richer-features menu drafted.
- 2026-06-10 — luxe rendering kit shipped (`ui/luxe.py`: PIL-baked
  gradient/glow/shadow/vignette sprites, 9-slice panels, lit gold
  typography). Chrome redesigned (titlebar/sidebar). Home rebuilt as the
  cinematic showcase (full-bleed splash hero, glass KPI chips, score-bar
  leaderboard with podium glows, entrance choreography, vignette).
  QA screenshot harness added (`RIFT_QA_SHOT`/`RIFT_QA_TABS` env vars);
  before/after captures in `.claude/qa_screens/v5_*`. All tabs sweep-tested,
  no regressions; draft tab untouched. Next: propagate the luxe language to
  Inhouse, Scout, Rankings, Feed, Profile, Wrapped.
- 2026-06-10 — Home approved by user. Inhouse leaderboard luxe pass:
  broadcast header bar (gradient + gold edge light, lit LOG GAME button,
  gold active segment pill), table carded on a shadowed gradient panel,
  podium rows with medal stripes/glows (matches Home), win-rate bars under
  WR%, gradient column header, ambient top-light + vignette. Captures in
  `.claude/qa_screens/v5_inhouse2`. Next targets: Inhouse detail panel +
  history/rivals/records views, then Scout report panel, Rankings, Feed.
