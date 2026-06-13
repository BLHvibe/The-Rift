// Draft store — one interface, two modes.
//   synced: the Fly WS room is authoritative (LOBBY→SCOUTING→BRIEFING→
//           ARCHETYPE→BOARD→DONE, see PROTOCOLS.md)
//   solo:   the same phase machine run locally, one person drives both sides
import { writable, get } from 'svelte/store'
import { SEQ, currentAction, usedChamps, openRoles, other } from './seq.js'

const WS_URL = import.meta.env?.VITE_WS_URL
  ?? 'wss://the-rift-draft-sync.fly.dev/ws'

const emptyState = () => ({
  picks: { BLUE: {}, RED: {} },
  bans: { BLUE: [], RED: [] },
  pointer: 0,
  our_side: 'BLUE',
  players: { BLUE: [], RED: [] },
  phase: 'LOBBY',
  archetype_self: null,
  archetype_enemy: null,
  history: [],
})

const initial = () => ({
  mode: 'idle',            // idle | connecting | synced | solo
  connError: null,
  you: { name: '', side: 'SPEC', is_host: false },
  sides: {},               // {BLUE: name, RED: name}
  spectators: [],
  host: null,
  ready: { BLUE: false, RED: false },
  scoutReady: { BLUE: false, RED: false },
  briefingDone: { BLUE: false, RED: false },
  chat: [],
  rev: 0,
  state: emptyState(),
})

export const draft = writable(initial())

let ws = null
let pingTimer = null

const up = fn => draft.update(d => (fn(d), d))

// ── Synced mode ─────────────────────────────────────────────────────────
export function connect(name, side = '') {
  disconnect()
  up(d => { d.mode = 'connecting'; d.connError = null; d.you.name = name })
  const q = new URLSearchParams({ name })
  if (side) q.set('side', side)
  try {
    ws = new WebSocket(`${WS_URL}?${q}`)
  } catch (e) {
    up(d => { d.mode = 'idle'; d.connError = String(e) })
    return
  }
  ws.onopen = () => {
    pingTimer = setInterval(() => send({ type: 'ping' }), 25_000)
  }
  ws.onmessage = ev => {
    let msg
    try { msg = JSON.parse(ev.data) } catch { return }
    if (msg.type === 'hello' || msg.type === 'state') {
      up(d => {
        d.mode = 'synced'
        d.you = msg.you ?? d.you
        d.sides = msg.sides ?? {}
        d.spectators = msg.spectators ?? []
        d.host = msg.host ?? null
        d.ready = msg.ready ?? d.ready
        d.scoutReady = msg.scout_ready ?? d.scoutReady
        d.briefingDone = msg.briefing_done ?? d.briefingDone
        d.rev = msg.rev ?? d.rev
        const s = msg.state ?? {}
        d.state = { ...emptyState(), ...s, history: d.state.history }
      })
    } else if (msg.type === 'chat') {
      up(d => { d.chat = [...d.chat.slice(-60), msg] })
    } else if (msg.type === 'error') {
      up(d => { d.connError = msg.msg })
      setTimeout(() => up(d => {
        if (d.connError === msg.msg) d.connError = null
      }), 4000)
    }
  }
  ws.onclose = () => {
    clearInterval(pingTimer)
    up(d => {
      if (d.mode === 'connecting')
        d.connError = 'Could not reach the draft server.'
      if (d.mode !== 'solo') d.mode = 'idle'
    })
    ws = null
  }
  ws.onerror = () => {}
}

export function disconnect() {
  clearInterval(pingTimer)
  if (ws) { try { ws.close() } catch {} ws = null }
}

export function exitDraft() {
  disconnect()
  draft.set(initial())
}

function send(msg) {
  if (ws?.readyState === 1) ws.send(JSON.stringify(msg))
}

// ── Solo mode ───────────────────────────────────────────────────────────
export function beginSolo(name, side = 'BLUE') {
  disconnect()
  const d = initial()
  d.mode = 'solo'
  d.you = { name: name || 'you', side, is_host: true }
  d.sides = { [side]: name || 'you' }
  d.state.our_side = side
  draft.set(d)
}

// ── Actions — dispatch to WS (synced) or mutate locally (solo) ──────────
const isSolo = () => get(draft).mode === 'solo'

export function setSide(side) {
  if (isSolo()) {
    up(d => {
      d.you.side = side
      d.sides = { [side]: d.you.name }
      d.state.our_side = side
    })
  } else send({ type: 'set_side', side })
}

export function setPlayers(side, players) {
  if (isSolo()) up(d => { d.state.players[side] = players.slice(0, 5) })
  else send({ type: 'set_players', side, players: players.slice(0, 5) })
}

export function setReady(ready = true) {
  if (isSolo()) {
    up(d => { d.ready = { BLUE: true, RED: true }; d.state.phase = 'SCOUTING' })
  } else send({ type: 'set_ready', ready })
}

export function setScoutReady(ready = true) {
  if (isSolo()) {
    up(d => { d.scoutReady = { BLUE: true, RED: true }; d.state.phase = 'BRIEFING' })
  } else send({ type: 'set_scout_ready', ready })
}

export function setBriefingDone(done = true) {
  if (isSolo()) {
    up(d => { d.briefingDone = { BLUE: true, RED: true }; d.state.phase = 'ARCHETYPE' })
  } else send({ type: 'set_briefing_done', done })
}

export function setArchetype(archetype) {
  if (isSolo()) {
    up(d => {
      d.state.archetype_self = archetype
      if (d.state.phase === 'ARCHETYPE') d.state.phase = 'BOARD'
    })
  } else send({ type: 'set_archetype', archetype })
}

export function applyAction(champ, role = null) {
  if (!isSolo()) { send({ type: 'apply', champ, role }); return }
  up(d => {
    const s = d.state
    if (s.phase !== 'BOARD') return
    const act = currentAction(s)
    if (!act || !champ || usedChamps(s).has(champ)) return
    if (act.kind === 'ban') {
      s.bans[act.side] = [...s.bans[act.side], champ]
    } else {
      const open = openRoles(s, act.side)
      const r = role && open.includes(role) ? role
        : (open.length === 1 ? open[0] : null)
      if (!r) return
      s.picks[act.side] = { ...s.picks[act.side], [r]: champ }
      role = r
    }
    s.history = [...s.history,
      { action_idx: act.idx, kind: act.kind, side: act.side, champ, role }]
    s.pointer += 1
    if (s.pointer >= SEQ.length) s.phase = 'DONE'
  })
}

export function undo() {
  if (!isSolo()) { send({ type: 'undo' }); return }
  up(d => {
    const s = d.state
    if (s.pointer <= 0) return
    if (s.phase === 'DONE') s.phase = 'BOARD'
    s.pointer -= 1
    const act = SEQ[s.pointer]
    if (act.kind === 'ban') {
      s.bans[act.side] = s.bans[act.side].slice(0, -1)
    } else {
      const h = [...s.history].reverse()
        .find(h => h.action_idx === act.idx)
      const picks = { ...s.picks[act.side] }
      if (h?.role) delete picks[h.role]
      else {
        const last = Object.keys(picks).pop()
        if (last) delete picks[last]
      }
      s.picks[act.side] = picks
    }
    s.history = s.history.filter(h => h.action_idx !== act.idx)
  })
}

export function reassign(side, fromRole, toRole) {
  if (!isSolo()) { send({ type: 'reassign', side, from_role: fromRole, to_role: toRole }); return }
  up(d => {
    const picks = { ...d.state.picks[side] }
    if (!(fromRole in picks) || fromRole === toRole) return
    const champ = picks[fromRole]
    const swap = picks[toRole]
    picks[toRole] = champ
    if (swap === undefined) delete picks[fromRole]
    else picks[fromRole] = swap
    d.state.picks[side] = picks
  })
}

export function resetDraft() {
  if (!isSolo()) { send({ type: 'reset' }); return }
  up(d => {
    const players = d.state.players
    const ourSide = d.state.our_side
    d.state = { ...emptyState(), players, our_side: ourSide }
    d.ready = { BLUE: false, RED: false }
    d.scoutReady = { BLUE: false, RED: false }
    d.briefingDone = { BLUE: false, RED: false }
  })
}

export const sendChat = text => send({ type: 'chat', text })

// State dict for the engine API (history included for completeness).
export const engineState = d => ({
  our_side: d.state.our_side,
  pointer: d.state.pointer,
  players: d.state.players,
  picks: d.state.picks,
  bans: d.state.bans,
  history: d.state.history ?? [],
})

export { currentAction, usedChamps, openRoles, other, SEQ }
