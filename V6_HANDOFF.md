# THE RIFT V6 — SESSION HANDOFF

**Updated:** 2026-06-12 · canonical doc for continuing v6 work. Read this
first; history lives in `THE_RIFT_REIMAGINED.md` (v5) and
`RIFT_REWRITE_RESEARCH.md` (why this stack).

## What v6 is

Web-rendered rewrite of The Rift's front end. Svelte 4 + Vite in
`the_rift_v6/app`, shipped as `TheRiftV6.exe` (~24 MB): a PyInstaller'd
launcher (`the_rift_v6/desktop/launcher.py`) that embeds a FastAPI server
(serves the built bundle + proxies `/api/*` to Fly) and opens a pywebview
WebView2 window. **The Python brain (draft engine, LCU) is NOT ported yet**
— v5 (DPG, `the_rift/`) remains the league's draft-night app.

User's league reality: friend group, pickup customs, NO seasons/scheduled
games. Visual bar: "stunning, tons of animation, doing the most" — the
hextech glass + living-light language is locked and loved.

## Run / build / release

```
dev:      cd the_rift_v6/app && npm run dev        # :5173, vite proxies /api → Fly
preview:  .claude/launch.json has "rift-v6" → Claude Preview tools
bundle:   npm run build                            # → app/dist
package:  cd ../desktop; rm -r web; cp -r ../app/dist web
          pyinstaller --noconfirm --onefile --noconsole --name TheRiftV6
            --add-data "web;web" --collect-all webview --collect-all clr_loader
            --collect-all pythonnet launcher.py
smoke:    Start-Process dist\TheRiftV6.exe -ArgumentList "--headless" -PassThru -Wait
          → ExitCode 0 = server+bundle+live proxy OK
release:  GitHub API w/ PAT in memory `reference_github_token` (expires
          ~2026-08-05). Repo BLHvibe/The-Rift. Keep v6 releases
          prerelease=$true — /releases/latest must stay v5.0.0 because the
          v5 auto-updater reads it; flip only when the user says so.
```

Versions live in THREE places: `app/package.json`, `Titlebar.svelte`
(meta), `Settings.svelte` (data card). Bump all.

## Released state

- **v5.0.0** — latest (auto-update target). DPG app, full draft engine.
- v6.0.0 / v6.1.0 / v6.2.0 — pre-releases, asset `TheRiftV6.exe`.
- **v6.3.0** — BUILT LOCALLY, NOT RELEASED (awaiting a real draft-night
  verification). Full v5 parity: war room on the real engine + multiplayer
  WS sync + gated tier list + desktop sidecar (LCU/Riot) + inhouse match
  detail/predictions/records + hotkeys + update pill. See the
  `project-v6-parity-audit` memory and `the_rift_v6/PROTOCOLS.md`.
- Tags must point at the commit containing the code (see gotchas).

## App structure (`the_rift_v6/app/src`)

- `app.css` — design tokens: `.glass` (real backdrop-blur), `.gold-text`,
  `.gold-sweep` (animated specular), `.flow-line`, `.kicker`, `.rule-fade`
- `lib/stores.js` — `screen`, `navigate()` (fires hex dissolve),
  `selectedPlayer` + `openScout(name)`, `motion` (0–1, persisted, ALL FX
  respect it), `TABS`
- `lib/api.js` — `api(path)` cached fetch (same-origin `/api`);
  `leagueData()` = ONE `/api/export` call → sorted matches, `byMatch`
  map, leaderboard (sorted by exact WR ratio, ties→games — Turkey 83%
  leads, NOT most wins; user-corrected), `h2h` map `"A|B"` →
  {vsW,vsG,withW,withG}; ddragon helpers (`splashUrl`, `iconUrl` with
  live version fetch, `ddragonId` special-cases)
- `lib/archetypes.json` — the 7 v5 archetypes (label/win/spike/plan/
  target axes), exported from `the_rift/data/draft_engine.py ARCHETYPES`
- `lib/components/` — `BackgroundFX` (hex lattice + fog + embers canvas,
  mouse parallax), `HexDissolve` (nav transition), `Titlebar`, `Sidebar`,
  `Ticker`
- `lib/screens/` — Home (cinematic hero + ladder rankings + widgets:
  Form Watch / League Bonds / Meta Board), Rankings (podium w/ signature
  splash backdrops — joins /api/scout top_champs by name), Inhouse
  (leaderboard / history / rivals matrix views), Scout (deep player card:
  role, form dots, duo/nemesis, customs champ pool, rank sparkline),
  Draft (war room — see below), Feed, Tierlist (dnd, localStorage only),
  Commands (server recompute + freshness), Settings
- Names are clickable league-wide → `openScout(name)`.

### Draft war room (v6.2.0)

Team builder (drag + click-assign, role/score chips) → elo-logistic
balance meter (`1/(1+10^(-(avgB-avgR)/12))` on ladder scores) → intel:
ban targets (enemy customs champs weighted `wr × min(1, games/4)` +
scout signature picks), per-player pick suggestions (×1.45 boost when the
champ's ddragon tags match the chosen archetype via `ARCH_TAGS`) →
archetype overlay (7 ceremonial cards + "no archetype") → 20-action
tournament board (search/click-assign, right-click clears, ban slashes,
splash bg from first pick). Svelte gotcha: intel reactive statements must
reference `archetype`/`board` IN the `$:` expression — deps inside helper
functions are invisible.

**v6.3.0 update — parity reached.** The draft tool was fully rebuilt
(`app/src/lib/draft/*` + `app/src/lib/screens/draft/*`). The deep engine was
NOT ported — it already runs on Fly at `/api/engine/*` (server/engine_board.py
+ engine_core.py); v6 just calls it. Multiplayer WS sync reuses the existing
`wss://…/ws`. LCU + Riot fetchers live in the desktop sidecar
(`desktop/local_api.py`, mounted by launcher.py) which imports the UI-free v5
`the_rift/data` package. See the old plan below for history; it's done.

## Server API (Fly: the-rift-draft-sync.fly.dev, all via `/api`)

`/stats`, `/export` (matches+participants+drafts — THE one-call source),
`/players` (roster + summoner_map riot→display + riot_ids), `/rankings`
(+POST, +`/rankings/recompute` POST — wired to Commands), `/scout`
(score/wr/kda/games/top_champs/form), `/records` (wrapped in `.records`),
`/rank-history`, `/primary-roles`, `/inhouse-champs` (per-player champ
stats w/ results string), `/h2h-matrix`, `/activity`, `/seasons`,
`/achievements`, `/scout-sheets/{name}`, `/tier-votes` (GET/POST/bulk —
**exists but UNUSED by v6**; tierlist submit is a ready quick win),
`/matches?limit=`, `/matches/{id}`. Participant row: match_id, player
(summoner name — map via summoner_map!), team, role, champion, win,
kills/deaths/assists, cs, gold, damage, vision.

## Gotchas (each cost real debugging time)

1. **PS 5.1 text editing corrupts UTF-8** — `Get-Content|-replace|
   Set-Content -Encoding utf8` produced mojibake (`·`→`Â·`) AND a BOM on
   package.json, which silently broke `"type":"module"` → vite build
   failed → **exe packaged stale code while smoke tests passed**. Use the
   Edit/Write tools for source files, and verify bundle contents
   (`Select-String dist/assets/index-*.js -Pattern "V6.2.0"`).
2. **--noconsole exes have None stdout/stderr** — uvicorn logging kills
   the server thread. launcher.py nulls the streams at import; keep it.
3. **GUI exes don't block PowerShell** — use
   `Start-Process -PassThru -Wait` for exit codes.
4. **git commit -m with embedded double quotes** mangles args in PS 5.1 —
   v6.2.0's tag initially pointed at stale source; fixed via
   `git tag -f` + force-push of the tag. Keep commit messages quote-free
   or use files.
5. **preview_screenshot times out on the Draft screen** (capture quirk;
   page is fine) — verify via `preview_eval` DOM checks instead.
6. The preview iframe is narrow by default — layouts are responsive
   (≤1080px stacks) but judge desktop at real width.
7. Repo history contains one accidental node_modules commit (d1e2676,
   ~unavoidable bloat now); `.gitignore`s exist in app/ and desktop/.

## Roadmap (user-validated direction: deepen, don't add systems)

1. ~~Engine in war room~~ — DONE (v6.3.0). Calls `/api/engine/*` directly.
2. ~~Multiplayer draft sync~~ — DONE (v6.3.0). Reuses `wss://…/ws`.
3. ~~LCU via sidecar~~ — DONE (v6.3.0). `desktop/local_api.py`: summoner
   detect, log games, fetch ranks, run scout (+ update-check).
4. ~~Tier-vote submit~~ — DONE (v6.3.0) + consensus view.
5. **Wrapped** as a v6 set piece — still unported (v5 `ui/wrapped.py`).
   Share cards (v5 `data/share_cards.py`) also unported — both good next.
6. **Tauri shell** (optional; needs rustup + MSVC — not installed).
7. **Flip v6 to latest** when the user says it survived a draft night;
   v5 stays downloadable. Run a real session FIRST (LCU gate, live WS
   between two machines) before releasing.

Remaining v5-only nicety not yet in v6: profile-icon upload (Settings),
audio cues (user said NO audio — skip), Wrapped, share cards.

## Hard rules

Free-tier infra only. No seasons/scheduled-games framing. Don't release
as `latest` without explicit user instruction. Motion slider must govern
every effect. Verify visually (preview tools / eval) before claiming done
— every "done" this project shipped was screenshot- or DOM-verified.
