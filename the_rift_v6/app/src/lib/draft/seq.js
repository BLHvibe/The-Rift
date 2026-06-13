// Tournament draft sequence — mirror of the server's DRAFT_SEQUENCE.
export const ROLES = ['TOP', 'JGL', 'MID', 'BOT', 'SUP']
export const SIDES = ['BLUE', 'RED']

function build() {
  const seq = []
  let bansB = 0, bansR = 0, picksB = 0, picksR = 0
  const push = (kind, side, phase) => {
    let label
    if (kind === 'ban') {
      label = side === 'BLUE' ? `Blue Ban ${++bansB}` : `Red Ban ${++bansR}`
    } else {
      label = side === 'BLUE' ? `B${++picksB}` : `R${++picksR}`
    }
    seq.push({ idx: seq.length, side, kind, phase, label })
  }
  for (const s of ['BLUE', 'RED', 'BLUE', 'RED', 'BLUE', 'RED']) push('ban', s, 1)
  for (const s of ['BLUE', 'RED', 'RED', 'BLUE', 'BLUE', 'RED']) push('pick', s, 1)
  for (const s of ['RED', 'BLUE', 'RED', 'BLUE']) push('ban', s, 2)
  for (const s of ['RED', 'BLUE', 'BLUE', 'RED']) push('pick', s, 2)
  return seq
}

export const SEQ = build()

export const other = s => (s === 'BLUE' ? 'RED' : 'BLUE')

export const currentAction = state =>
  state.pointer >= 0 && state.pointer < SEQ.length ? SEQ[state.pointer] : null

export function usedChamps(state) {
  const u = new Set()
  for (const s of SIDES) {
    for (const c of state.bans[s]) if (c) u.add(c)
    for (const c of Object.values(state.picks[s])) if (c) u.add(c)
  }
  return u
}

export const openRoles = (state, side) =>
  ROLES.filter(r => !(r in state.picks[side]))

// Which timeline cell shows which champ — walk the sequence against state.
// Returns [{...action, champ|null}] for all 20 cells.
export function timeline(state) {
  const counts = { BLUE: { ban: 0, pick: 0 }, RED: { ban: 0, pick: 0 } }
  const pickOrder = { BLUE: [], RED: [] }
  // Picks dict is role-keyed; recover lock order from history when present,
  // else fall back to role order (good enough for rendering).
  const hist = state.history ?? []
  const byIdx = new Map(hist.map(h => [h.action_idx, h.champ]))
  return SEQ.map(a => {
    if (byIdx.has(a.idx)) return { ...a, champ: byIdx.get(a.idx) }
    if (a.idx >= state.pointer) return { ...a, champ: null }
    // No history (synced snapshots) — reconstruct from bans list / picks set.
    if (a.kind === 'ban') {
      const i = counts[a.side].ban++
      return { ...a, champ: state.bans[a.side][i] ?? null }
    }
    if (!pickOrder[a.side].length) {
      pickOrder[a.side] = ROLES.filter(r => r in state.picks[a.side])
        .map(r => state.picks[a.side][r])
    }
    const i = counts[a.side].pick++
    return { ...a, champ: pickOrder[a.side][i] ?? null }
  })
}
