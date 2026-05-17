# How to host a synced draft

## One-time setup (already done)

- Server code: `server/main.py`
- ngrok installed + authenticated with your account
- Static URL claimed: `https://wife-reason-unseeing.ngrok-free.dev`
- The Rift app has this URL baked into its defaults

## Every time you want to host

1. **Double-click `start_sync_host.bat`** in this folder.
   Two black windows open — one is the server, one is the tunnel.
   Leave both open while you draft.
2. **Pick a room code + password** (anything — `abc` / `123` is fine for friends).
3. **Tell your friends the code + password** (e.g. in Discord).
4. Everyone opens The Rift → Draft tab → **JOIN / HOST SYNCED DRAFT** →
   enter the same code + password + their name + their slot.
   - Slots: `blue1..blue5` for blue team, `red1..red5` for red team,
     `spectator` for anyone just watching.
   - The first person to join becomes "host" (can undo / reset).

## When you're done

Double-click `stop_sync_host.bat`, or just close both black windows.

## Things to know

- **Your PC has to be on** while friends are connected. If you close your
  laptop or it sleeps, the session ends and they'll see "reconnecting…"
- **Free ngrok limits**: ~40 connections per minute, which is way more than
  10 friends drafting. You won't hit it.
- **Restarting the host clears the room state.** All clients reconnect
  automatically and the draft starts fresh.
- **If the URL ever changes** (e.g. you regenerate it on the ngrok
  dashboard), update `data/config.json` → `sync.url` in The Rift, and the
  `TUNNEL_URL` line in `start_sync_host.bat`.

## Troubleshooting

- **Friends see "connect failed"**: check that both black windows are open
  on your PC. Restart with `start_sync_host.bat`.
- **"slot already taken"**: someone else claimed that color/number first.
  Pick a different one.
- **"wrong password"**: typo. Server room was created by the first joiner
  with the password they typed.
- **ngrok window says "ERR_NGROK_..."**: usually means another ngrok agent
  is already running, or your authtoken is wrong. Run
  `stop_sync_host.bat` then `start_sync_host.bat` again.
