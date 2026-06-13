// Draft engine client — calls the REAL engine on the Fly server
// (/api/engine/*, see ../../../PROTOCOLS.md) and plumbs the data it needs:
// inhouse champs, primary roles, ladder scores, scout sheets.
import { api, post } from '../api.js'

// ── Core league data (cached module-level) ──────────────────────────────
export let inhouseChamps = {}
export let primaryRoles = {}
export let scoreBy = {}
let coreLoaded = false

export async function loadCoreData() {
  if (coreLoaded) return
  const [ic, pr, rk] = await Promise.all([
    api('/inhouse-champs', { ttl: 300_000 }),
    api('/primary-roles', { ttl: 300_000 }),
    api('/rankings', { ttl: 300_000 }),
  ])
  inhouseChamps = ic?.inhouse_champs ?? {}
  primaryRoles = pr?.primary_roles ?? {}
  for (const p of (rk?.rankings ?? [])) scoreBy[p.name] = +p.score
  coreLoaded = true
}

// Player row in the shape the engine's board state expects.
export const playerRow = name => ({
  name,
  score: scoreBy[name] ?? 50,
  final_score: scoreBy[name] ?? 50,
})

// ── Scout sheets (per player, fetched once per session) ─────────────────
const sheets = new Map()   // name -> scout_sheet | null

export async function loadScoutSheets(names, onProgress) {
  const todo = [...new Set(names.filter(Boolean))].filter(n => !sheets.has(n))
  let done = names.length - todo.length
  await Promise.all(todo.map(async n => {
    try {
      const r = await api(`/scout-sheets/${encodeURIComponent(n)}`, { ttl: 600_000 })
      sheets.set(n, r?.scout_sheet ?? null)
    } catch { sheets.set(n, null) }
    onProgress?.(++done, names.length)
  }))
}

// {player: [{champ, games, wins, losses, wr, kda, results}]} — the engine's
// scout_champs shape (sheet pool entries use `name`; engine wants `champ`).
export function scoutChampsFor(names) {
  const out = {}
  for (const n of names) {
    const pool = sheets.get(n)?.champ_pool
    if (!pool) continue
    out[n] = pool.map(c => ({ ...c, champ: c.name ?? c.champ }))
  }
  return out
}

export function mustBansFor(names) {
  const out = {}
  for (const n of names) {
    const mb = sheets.get(n)?.must_bans
    if (Array.isArray(mb) && mb.length) out[n] = mb
  }
  return out
}

export const sheetFor = name => sheets.get(name) ?? null

// ── Engine calls ────────────────────────────────────────────────────────
const allNames = state =>
  [...(state.players.BLUE ?? []), ...(state.players.RED ?? [])]
    .map(p => p?.name).filter(Boolean)

const baseBody = state => ({
  state,
  inhouse_champs: inhouseChamps,
  primary_roles: primaryRoles,
  scout_champs: scoutChampsFor(allNames(state)),
})

// recommend_action's `action` arrives as an array (Python NamedTuple).
const rehydrate = a => (Array.isArray(a)
  ? { idx: a[0], side: a[1], kind: a[2], phase: a[3], label: a[4] }
  : a)

export async function recommendAction(state, { forcedArch = null, prevArch = null, enemySide = null } = {}) {
  const enemies = enemySide
    ? (state.players[enemySide] ?? []).map(p => p?.name).filter(Boolean) : []
  const out = await post('/engine/recommend_action', {
    ...baseBody(state),
    n: 5,
    forced_arch: forcedArch,
    prev_archetype: prevArch,
    must_bans: mustBansFor(enemies),
  })
  if (out && 'action' in out) out.action = rehydrate(out.action)
  return out
}

export const targetArchetype = (state, side, { forcedArch = null, prevArch = null } = {}) =>
  post('/engine/target_archetype', {
    ...baseBody(state), side, forced_arch: forcedArch, prev_archetype: prevArch,
  })

export const pivotCheck = (state, side, currentArch) =>
  post('/engine/archetype_pivot_check', {
    ...baseBody(state), side, current_arch: currentArch ?? '',
  })

export const predictEnemyNext = (state, ourSide) =>
  post('/engine/predict_enemy_next', { ...baseBody(state), our_side: ourSide })

// Stateless endpoints need a `role` on every player row (slot order =
// TOP/JGL/MID/BOT/SUP) — without it the engine's ROLE_VALID lookup empties
// every candidate pool and comps come back empty. The state-based endpoints
// attach roles server-side.
const ROLE_SLOTS = ['TOP', 'JGL', 'MID', 'BOT', 'SUP']
const withRoles = players =>
  players.map((p, i) => p?.role ? p : { ...p, role: ROLE_SLOTS[i] ?? '' })

// Briefing + archetype ranking — players is a row list for ONE side.
export async function recommendComps(players, { enemyPicks = [], n = 7 } = {}) {
  const rows = withRoles(players)
  const names = rows.map(p => p?.name).filter(Boolean)
  const out = await post('/engine/recommend_comps', {
    players: rows,
    inhouse_champs: inhouseChamps,
    primary_roles: primaryRoles,
    enemy_picks: enemyPicks,
    n_results: n,
    scout_champs: scoutChampsFor(names),
  })
  return out?.comps ?? []
}

export async function recommendBans(opposingPlayers, { ownPicks = [], n = 3 } = {}) {
  const rows = withRoles(opposingPlayers)
  const names = rows.map(p => p?.name).filter(Boolean)
  const out = await post('/engine/recommend_bans', {
    opposing_players: rows,
    inhouse_champs: inhouseChamps,
    primary_roles: primaryRoles,
    own_picks: ownPicks,
    n_bans: n,
    scout_champs: scoutChampsFor(names),
  })
  return { names: out?.names ?? [], info: out?.info ?? {} }
}
