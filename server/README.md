# The Rift — Draft Sync Server

Self-hosted FastAPI + WebSocket server that lets a group of friends share one
live tournament-draft session: blue-side users make blue picks/bans, red-side
users make red picks/bans, and every action appears on every client in
~real-time. No Google / Firebase / Supabase dependency.

## How it works

- One process holds rooms in memory. A "room" is identified by a 4-char code
  + a password chosen by whoever creates it.
- Up to 10 players + spectators connect to `/ws/<code>` over WebSocket.
- Each connection claims a slot: `blue1..blue5`, `red1..red5`, or `spectator`.
- Server enforces side authorization: slot `blueN` can only mutate state when
  the current draft action belongs to BLUE side; same for red. Spectators are
  read-only.
- Every mutation is fanned out to all connected clients as a full state
  snapshot. Clients mirror it into their local `DraftBoardState`.

## Local test

```bash
cd server
pip install -r requirements.txt
python main.py
```

Then in another shell:

```bash
# probe
curl http://localhost:8000/

# connect a websocket client (using websocat — install from https://github.com/vi/websocat)
websocat "ws://localhost:8000/ws/test?password=hunter2&name=alice&slot=blue1"
# in the websocat shell, paste:
{"type":"apply","champ":"Aatrox"}
```

A second websocat session as `slot=red1` can paste `{"type":"apply","champ":"Darius"}`
once BLUE's first ban lands — and both clients see the state update.

## Deploy to Fly.io (free tier)

1. Install flyctl (https://fly.io/docs/hands-on/install-flyctl/).
2. `fly auth login`
3. From this directory:
   ```bash
   fly launch --no-deploy --copy-config --name <choose-a-name>
   fly deploy
   ```
   The included `fly.toml` is pre-configured for shared-cpu-1x / 256MB / auto-stop.
4. After deploy, your WebSocket URL is `wss://<your-app>.fly.dev/ws/<code>`.

## Deploy to Railway (alternative)

Railway auto-detects the `Dockerfile`. Push this `server/` dir as a repo,
connect it in Railway, and it just works. Set `PORT` env var to whatever
Railway tells you (it injects one automatically).

## Deploy to a VPS

Anywhere you can run Docker:

```bash
docker build -t rift-sync .
docker run -d --restart unless-stopped -p 8080:8080 --name rift-sync rift-sync
```

Put it behind nginx / Caddy with TLS termination (WebSocket needs `wss://` in
production, not `ws://`). Caddy is one line: `your-domain { reverse_proxy localhost:8080 }`.

## Operational notes

- **State is in memory.** Process restart = rooms lost. Fine for a friends
  tool; restart, everyone reconnects. To persist, swap `ROOMS` for a Redis
  hash and serialise `DraftState` on each mutation.
- **Idle rooms reaped after 6h** of no activity (`IDLE_TTL_SECONDS`).
- **Fly auto-stop**: with `auto_stop_machines=true`, the VM hibernates when
  there are no connections, cold-starts on the next connect (~1-2s). If you
  hate the cold start, set `min_machines_running = 1`.
- **No rate limiting / abuse protection.** This is a friends-only tool. If you
  open it to the world, add a per-IP token bucket on connect.

## Wire protocol

See the module docstring at the top of `main.py`. Short version:

Client -> server:
```json
{"type":"apply","champ":"Aatrox","role":"TOP"}
{"type":"undo"}                                  // host only
{"type":"reset"}                                 // host only
{"type":"set_players","side":"BLUE","players":[...]}
{"type":"set_our_side","side":"BLUE"}            // host only
{"type":"set_slot","slot":"red3"}
{"type":"chat","text":"gl hf"}
{"type":"ping"}
```

Server -> client:
```json
{"type":"hello","you":{...},"state":{...},"slots":{...},"rev":N}
{"type":"state","state":{...},"slots":{...},"spectators":[...],"host":"alice","rev":N}
{"type":"chat","from":"alice","slot":"blue1","text":"gl hf"}
{"type":"error","msg":"..."}
{"type":"pong"}
```

The `state` object mirrors `DraftBoardState`:
```json
{
  "picks": {"BLUE": {"TOP":"Aatrox"}, "RED": {}},
  "bans":  {"BLUE": [], "RED": []},
  "pointer": 7,
  "our_side": "BLUE",
  "players": {"BLUE":[{...},...], "RED":[{...},...]},
  "sequence_len": 20
}
```
