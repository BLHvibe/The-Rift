# v6 ↔ server contracts (verified live 2026-06-12)

Notes from reading `server/main.py`, `server/api.py`, `server/engine_board.py`
and probing the live Fly deployment. These are the shapes the v6 front end
codes against.

## WebSocket draft sync — `wss://the-rift-draft-sync.fly.dev/ws?name=X&side=BLUE`

Single global room. First connect grabs BLUE, second RED, rest SPEC. Server is
the phase authority: `LOBBY → SCOUTING → BRIEFING → ARCHETYPE → BOARD → DONE`.
Gates: both sides `set_ready` → SCOUTING; both `set_scout_ready` → BRIEFING;
both `set_briefing_done` → ARCHETYPE; both archetypes non-null → BOARD;
pointer==20 → DONE. Last client out resets the room.

Client → server messages:

```json
{"type":"set_side","side":"BLUE|RED|SPEC"}        // LOBBY only; claiming an occupied side swaps
{"type":"set_ready","ready":true}                  // LOBBY, sides only
{"type":"set_scout_ready","ready":true}            // SCOUTING
{"type":"set_briefing_done","done":true}           // BRIEFING
{"type":"set_archetype","archetype":"Teamfight"}   // ARCHETYPE or BOARD; null clears
{"type":"set_players","side":"BLUE","players":[{"name":"Ben","score":62}]}  // own side or host; max 5
{"type":"set_slot_player","side":"BLUE","idx":0,"player":{"name":"Ben"}}    // host only
{"type":"apply","champ":"Aatrox","role":"TOP"}     // BOARD; server enforces turn side; role needed when >1 open
{"type":"undo"}                                     // host only
{"type":"reassign","side":"BLUE","from_role":"TOP","to_role":"JGL"}         // host only
{"type":"reset"}                                    // host only
{"type":"chat","text":"gl hf"}
{"type":"ping"}
```

Server → client: `hello` (once) and `state` (every change), both shaped:

```json
{"type":"state",
 "you":{"name":"Ben","side":"BLUE","is_host":true},
 "state":{
   "picks":{"BLUE":{"TOP":"Aatrox"},"RED":{}},
   "bans":{"BLUE":["Zed"],"RED":[]},
   "pointer":3, "our_side":"BLUE",          // our_side is VIEWER-relative
   "players":{"BLUE":[{"name":"Ben"}],"RED":[]},
   "phase":"BOARD", "started":true, "sequence_len":20,
   "archetype_self":"Teamfight",            // own pick; enemy's only at DONE
   "archetype_enemy":null},
 "sides":{"BLUE":"Ben","RED":"Luke"}, "spectators":["Chips"], "host":"Ben",
 "ready":{"BLUE":true,"RED":false}, "scout_ready":{...}, "briefing_done":{...},
 "rev":17}
```

Plus `{"type":"chat","from","side","text","ts"}`, `{"type":"error","msg"}`,
`{"type":"pong"}`. Draft sequence (20): bans B R B R B R · picks B R R B B R ·
bans R B R B · picks R B B R — same as v6's existing `SEQ`.

## Engine endpoints — POST `/api/engine/*` (all live on Fly)

Common body parts:

- `state` — DraftBoardState dict:
  `{our_side, pointer, players:{BLUE:[{name,score?,tier?}],RED:[...]},
    picks:{BLUE:{TOP:"champ"}}, bans:{BLUE:[...]},
    history:[{action_idx,kind,side,champ,role}]}`
- `inhouse_champs` — from GET `/api/inhouse-champs` →
  `{player:[{champ,games,wins,losses,wr:"66.7%",kda,results:[1,0],roles:{JGL:6}}]}`
- `primary_roles` — from GET `/api/primary-roles` → `{player:"TOP"}` (short
  codes fine; server normalizes)
- `scout_champs` — `{player:[{champ,games,wins,losses,wr,kda,results}]}`,
  built from GET `/api/scout-sheets/{name}` → `.scout_sheet.champ_pool`
  (**rename `name`→`champ`** per entry; wr is numeric there, engine parses both)

Endpoints:

- `recommend_action` `{state, inhouse_champs, primary_roles, scout_champs, n,
  forced_arch?, must_bans?, prev_archetype?, scout_role_champs?}` →
  `{done, action, our_turn, kind, suggestions:[{champion,score,tag,why,role?,player?}],
    enemy_weakness:{axis:0..1}, target_comp:{label,...}, cohesion:[str],
    exploit:[str], notes:[str]}`.
  **`action` serializes as an ARRAY** `[idx, side, kind, phase, label]`
  (NamedTuple) — destructure it. `must_bans` comes from each enemy scout
  sheet's `.must_bans`. Pass `prev_archetype` from the previous rec's
  target_comp.label for hysteresis.
- `target_archetype` `{state, side, forced_arch?, prev_archetype?}` → comp dict
- `archetype_pivot_check` `{state, side, current_arch, ...}` → pivot rec
- `predict_enemy_next` `{state, our_side, ...}` → prediction | null
- `recommend_bans_split` `{state, n, ...}` → list (uses state.pointer's action)
- `recommend_comps` `{players:[rows], inhouse_champs, primary_roles,
  enemy_picks, n_results, scout_champs}` → `{comps:[...]}` (briefing +
  archetype viability ranking)
- `recommend_bans` `{opposing_players:[rows], own_picks, n_bans, ...}` →
  `{names:[...], info}`
- `matchups` `{blue, red, primary_roles, blue_picks, red_picks}` → lane matchups

## Tier votes

- POST `/api/tier-votes` `{"rater":"Ben","placements":{"S":["Luke"],...}}` —
  replaces that rater's whole ballot AND recomputes the rankings blend.
- GET `/api/tier-votes?rater=X` → `{votes:[{rater,player,rating}]}` (prefill).
- GET `/api/tier-aggregate` → `{tier_aggregate:{player:{avg,avg_tier,votes,min,max,std,voters}}}`.
- POST `/api/activity` `{"event_type":"TIER_LIST","actor":name,"details":...}`.
- Server runs in open mode (no RIFT_API_TOKEN) — no auth header needed today.

## Gotchas

- **launcher.py proxy drops POST bodies** (`_client.request(method, url)` with
  no `content=`). Must forward body + content-type for any engine POST to work
  in the packaged exe. Vite's dev proxy is fine.
- WS connects DIRECT to Fly (browser WS is not blocked cross-origin), not
  through the `/api` proxy.
- `/api/scout-sheets/{name}` 404s for unknown players — treat as empty pool.
- LCU lockfile: `%LOCALAPPDATA%/Riot Games/League of Legends/lockfile` +
  `C:/Riot Games/...` etc; `name:pid:port:password:https`; GET
  `https://127.0.0.1:{port}/lol-summoner/v1/current-summoner` basic-auth
  `riot:{password}`, verify off → `.gameName` (fallback `.displayName`).
