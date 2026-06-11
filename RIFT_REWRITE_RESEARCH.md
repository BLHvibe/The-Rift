# THE RIFT v6 — FRONT-END REWRITE RESEARCH

**Status:** research — no code yet (2026-06-11)
**Trigger:** v5 maxed out DearPyGui's sprite-compositing ceiling. The next
visual tier (real-time blur/glass, shader post-FX, video, fluid text
effects) is impossible in DPG by architecture, not by effort.

---

## What "next level" means, concretely

Things v5 cannot do that a rewrite unlocks:

| Effect | DPG (v5) | Next level |
|---|---|---|
| Frosted glass / backdrop blur | faked w/ baked textures | real `backdrop-filter` / shader |
| Bloom, distortion, heat shimmer | glow sprites only | true post-processing |
| Animated/video backgrounds | static splash + drift | LoL-client-style video loops |
| Text effects on live strings | pre-baked textures | gradient/glow/animated type |
| Springy layout animation | manual per-frame math | declarative, GPU-driven |
| 3D / depth (cards, trophies) | none | WebGL / engine scene |

## The architecture insight (this is the big one)

The Rift is **already half-prepared** for a front-end swap:

- The **Fly server** (SQLite + REST + WS) owns all match/rank/records data.
- The **draft engine** (`draft_engine.py`, `draft_board.py`) is pure Python
  with no UI imports.
- The **LCU integration** is local REST against the League client.

So this is NOT a 25k-line rewrite. It's a **rendering-layer swap** (~12k
lines of `ui/*` immediate-mode drawing) on top of a brain that survives
intact. Two ways to keep the brain:

1. **Python sidecar** — bundle the engine + LCU client + data layer as a
   small local FastAPI process the new front end talks to (Tauri has a
   first-class sidecar pattern).
2. **Server-side engine** — move the draft engine onto the existing Fly
   server (`/api/draft/recommend`). Front end becomes a pure renderer.
   (Both can be combined: LCU must stay local; engine can go either way.)

## Candidates

### 1. Tauri 2 + web front end (Svelte or React) — RECOMMENDED
- **Visuals:** the broadcast-graphics look is *native territory* for the
  web: CSS `backdrop-filter` glass, WebGL/Three.js shaders, Lottie, video,
  GSAP/Framer-Motion animation, custom fonts with real text effects.
  Nothing in the v5 wishlist is out of reach.
- **Runtime:** uses Windows' built-in WebView2 (Chromium, auto-updating) —
  no bundled browser; installers are tens of MB, RAM stays sane.
- **Brain:** Rust host spawns the Python sidecar (proven pattern; example
  repos bundle a PyInstaller'd FastAPI server inside the Tauri app).
- **Velocity factor (honest):** AI assistance is dramatically strongest at
  web UI — the v5 pace would *increase*, not decrease.
- **Risks:** IPC hop (localhost HTTP/WS — fine at this scale); WebView2
  required (ships with Win10/11); two-process packaging complexity.

### 2. PySide6 / QML — the "keep everything Python" path
- **Visuals:** Qt Quick scene graph with real shader effects (blur, glow),
  GPU-driven declarative animation, QtMultimedia video. A genuine tier up
  from DPG.
- **Brain:** stays in-process — zero IPC, single language, single bundle.
- **Risks:** QML is its own language/ecosystem (smaller than web); data-
  dense custom tables take more work; bundles ~100 MB; the very top of the
  effect wishlist (web-grade polish ecosystem) is thinner.

### 3. Godot 4 — the game-engine play
- **Visuals:** the highest ceiling of all — full shader stack, particles,
  post-processing bloom by default, 3D trophy rooms if we ever want them.
- **Risks:** UI-heavy data apps (tables, forms, text panels) are the
  engine's weak side; the brain must move server-side or be ported
  (GDScript ≈ Python but it IS a port); least AI-assist leverage of the
  three. Best fit only if v6 should feel like a *game*, not an app.

### 4. Electron — ruled out
Same visual ceiling as Tauri, but 150-250 MB bundles and heavyweight RAM
for zero benefit at this team size.

## Recommendation

**Tauri 2 + Svelte + Python sidecar**, with the draft engine staying in
the sidecar (so it works offline at the desk) and everything else already
on Fly. Highest visual ceiling per unit of effort, smallest download for
the friends, and the stack where iteration speed is greatest.

PySide6/QML is the respectable runner-up if a single-process,
single-language app matters more than the last 20% of visual ceiling.

## Phased plan (de-risked)

| Phase | Scope | Exit test |
|---|---|---|
| 0 — Spike (small) | Tauri shell + sidecar IPC + ONE screen (Home hero w/ video bg, glass cards, real bloom) | does it beat v5 on sight? |
| 1 | App chrome + Home + Rankings | daily-driveable for browsing |
| 2 | Inhouse (all views) + Scout + Profile | stats parity |
| 3 | Feed, Tierlist, Wrapped, Settings | full parity minus draft |
| 4 — LAST | Draft tool port (engine untouched in sidecar; UI re-skinned 1:1) | a full draft night runs clean |
| — | v5 (DPG) stays the released app until Phase 4 passes — dual-ship, zero downtime for the group | |

## Open questions for the spike

- Sidecar packaging: PyInstaller the FastAPI sidecar, launch via Tauri
  sidecar API, health-check on boot.
- LCU calls from sidecar (lockfile read + local REST) — straightforward.
- Frame-perfect drag-and-drop (tierlist, draft) in webview — standard.
- Auto-update: Tauri updater vs current GitHub-release check.

## Change log
- 2026-06-11 — research drafted after v5.0.0 shipped to GitHub.
