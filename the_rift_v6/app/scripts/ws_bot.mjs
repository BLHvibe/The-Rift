// Headless second captain for testing the synced draft flow.
// Node 22+ (global WebSocket). Claims RED, fills its roster, readies through
// every gate, and answers RED turns with scripted picks/bans.
const URL = 'wss://the-rift-draft-sync.fly.dev/ws?name=LukeBot&side=RED'

const RED_TEAM = ['Miles', 'Devin', 'Kian', 'Logan', 'Chris']
  .map(n => ({ name: n, score: 50 }))
const BANS = ['Volibear', 'Yasuo', 'Zed', 'Akali', 'Riven']
const PICKS = [
  ['Olaf', 'JGL'], ['Ahri', 'MID'], ['Jinx', 'BOT'],
  ['Leona', 'SUP'], ['Malphite', 'TOP'],
]
let banIdx = 0, pickIdx = 0
let lastPointer = -1
let phaseSeen = ''

const ws = new WebSocket(URL)
const send = m => ws.send(JSON.stringify(m))
const log = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a)

const SEQ = []
for (const s of ['BLUE','RED','BLUE','RED','BLUE','RED']) SEQ.push(['ban', s])
for (const s of ['BLUE','RED','RED','BLUE','BLUE','RED']) SEQ.push(['pick', s])
for (const s of ['RED','BLUE','RED','BLUE']) SEQ.push(['ban', s])
for (const s of ['RED','BLUE','BLUE','RED']) SEQ.push(['pick', s])

ws.onopen = () => log('connected')
ws.onerror = e => log('error', e.message ?? e)
ws.onclose = () => { log('closed'); process.exit(0) }

ws.onmessage = ev => {
  const msg = JSON.parse(ev.data)
  if (msg.type === 'error') { log('SERVER ERR:', msg.msg); return }
  if (msg.type !== 'hello' && msg.type !== 'state') return
  const st = msg.state
  if (st.phase !== phaseSeen) { phaseSeen = st.phase; log('phase →', st.phase) }

  if (st.phase === 'LOBBY') {
    if ((st.players.RED ?? []).length < 5) {
      send({ type: 'set_players', side: 'RED', players: RED_TEAM })
      log('set RED roster')
    } else if (!msg.ready?.RED) {
      send({ type: 'set_ready', ready: true }); log('ready')
    }
  } else if (st.phase === 'SCOUTING') {
    if (!msg.scout_ready?.RED) { send({ type: 'set_scout_ready', ready: true }); log('scout ready') }
  } else if (st.phase === 'BRIEFING') {
    if (!msg.briefing_done?.RED) { send({ type: 'set_briefing_done', done: true }); log('briefing done') }
  } else if (st.phase === 'ARCHETYPE') {
    if (!st.archetype_self) { send({ type: 'set_archetype', archetype: 'Teamfight' }); log('archetype set') }
  } else if (st.phase === 'BOARD') {
    if (st.pointer === lastPointer) return
    const act = SEQ[st.pointer]
    if (!act) return
    const [kind, side] = act
    if (side !== 'RED') return
    lastPointer = st.pointer
    const used = new Set([
      ...st.bans.BLUE, ...st.bans.RED,
      ...Object.values(st.picks.BLUE), ...Object.values(st.picks.RED),
    ])
    setTimeout(() => {
      if (kind === 'ban') {
        while (banIdx < BANS.length && used.has(BANS[banIdx])) banIdx++
        const c = BANS[banIdx++] ?? 'Garen'
        send({ type: 'apply', champ: c }); log(`ban ${c} @${st.pointer}`)
      } else {
        while (pickIdx < PICKS.length && used.has(PICKS[pickIdx][0])) pickIdx++
        const [c, r] = PICKS[pickIdx++] ?? ['Sion', null]
        send({ type: 'apply', champ: c, role: r }); log(`pick ${c}/${r} @${st.pointer}`)
      }
    }, 700)
  } else if (st.phase === 'DONE') {
    log('DONE — enemy archetype revealed:', st.archetype_enemy)
    setTimeout(() => ws.close(), 3000)
  }
}

setTimeout(() => { log('timeout, closing'); ws.close() }, 600_000)
