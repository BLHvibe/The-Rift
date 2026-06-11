# The Rift v6 — web-rendered rewrite

The v6 front end: Svelte + Vite, real glass, shaders-class visuals, with the
Python brain unchanged. v5 (DearPyGui) remains the released app until v6
reaches parity (draft tool last).

## Run (dev)
```
cd app && npm install && npm run dev      # http://localhost:5173
```
Dev mode proxies `/api/*` straight to the Fly server (vite.config.js) — no
sidecar needed. The sidecar (`sidecar/main.py`, FastAPI on :8765) exists for
production/Tauri and will grow `/engine/*` (draft engine) and `/lcu/*`.

## Structure
- `app/src/app.css` — design tokens: hextech glass, gold gradient/sweep
  text, flowing lines, kickers
- `lib/components/BackgroundFX.svelte` — full-app living canvas: hex
  lattice, fog glows, rising embers, mouse parallax
- `lib/components/HexDissolve.svelte` — honeycomb dissolve on navigation
- `lib/components/{Titlebar,Sidebar,Ticker}.svelte` — glass chrome
- `lib/screens/Home.svelte` — cinematic hero (Ken Burns + parallax + rays),
  KPI count-ups, power rankings, record book, recent games — all live data
- `lib/api.js` — `/api` fetch + ddragon helpers + `leagueData()` (one
  `/api/export` call → leaderboard/matches/faces computed client-side)

## Packaging plan
Tauri 2 shell (needs rustup + MSVC build tools — not yet installed on the
dev machine): wraps `app/dist` + spawns the PyInstaller'd sidecar.
See `RIFT_REWRITE_RESEARCH.md` at repo root.
