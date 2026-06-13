// Thin data layer — same-origin /api (vite proxy in dev, sidecar in prod).
const cache = new Map()

export async function api(path, { ttl = 60_000 } = {}) {
  const hit = cache.get(path)
  if (hit && Date.now() - hit.t < ttl) return hit.v
  const r = await fetch(`/api${path}`)
  if (!r.ok) throw new Error(`${path} → ${r.status}`)
  const v = await r.json()
  cache.set(path, { t: Date.now(), v })
  return v
}

export async function post(path, body = {}) {
  const r = await fetch(`/api${path}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) throw new Error(`${path} → ${r.status}`)
  return r.json()
}

// ── ddragon helpers ─────────────────────────────────────────────────────
const SPECIAL = {
  "wukong": "MonkeyKing", "kai'sa": "Kaisa", "kha'zix": "Khazix",
  "vel'koz": "Velkoz", "cho'gath": "Chogath", "rek'sai": "RekSai",
  "kog'maw": "KogMaw", "lee sin": "LeeSin", "miss fortune": "MissFortune",
  "twisted fate": "TwistedFate", "master yi": "MasterYi",
  "tahm kench": "TahmKench", "aurelion sol": "AurelionSol",
  "xin zhao": "XinZhao", "jarvan iv": "JarvanIV", "dr. mundo": "DrMundo",
  "renata glasc": "Renata", "nunu & willump": "Nunu", "nunu": "Nunu",
  "bel'veth": "Belveth", "k'sante": "KSante", "leblanc": "Leblanc",
}
export function ddragonId(name) {
  if (!name) return null
  const k = name.trim().toLowerCase()
  if (SPECIAL[k]) return SPECIAL[k]
  return name.replace(/[^a-zA-Z]/g, '')
}
export const splashUrl = (champ, skin = 0) =>
  `https://ddragon.leagueoflegends.com/cdn/img/champion/splash/${ddragonId(champ)}_${skin}.jpg`

let _ver = '16.12.1'
fetch('https://ddragon.leagueoflegends.com/api/versions.json')
  .then(r => r.json()).then(v => { if (v?.[0]) _ver = v[0] }).catch(() => {})
export const iconUrl = (champ) =>
  `https://ddragon.leagueoflegends.com/cdn/${_ver}/img/champion/${ddragonId(champ)}.png`

// ── One-call league snapshot built from /api/export ────────────────────
export async function leagueData() {
  const [exp, roster] = await Promise.all([
    api('/export', { ttl: 120_000 }),
    api('/players', { ttl: 600_000 }),
  ])
  const sumToDisplay = roster?.summoner_map ?? {}
  const parts = exp?.participants ?? []
  const matches = [...(exp?.matches ?? [])]
    .sort((a, b) => (b.started_at ?? '').localeCompare(a.started_at ?? ''))
  const byMatch = new Map()
  for (const p of parts) {
    if (!byMatch.has(p.match_id)) byMatch.set(p.match_id, [])
    byMatch.get(p.match_id).push(p)
  }
  // Leaderboard — aggregate per display-name roster member.
  const agg = new Map()
  for (const p of parts) {
    const name = sumToDisplay[p.player]
    if (!name) continue
    const a = agg.get(name) ?? { name, wins: 0, losses: 0, k: 0, d: 0, a: 0,
                                 gold: 0, dmg: 0, cs: 0 }
    p.win ? a.wins++ : a.losses++
    a.k += p.kills ?? 0; a.d += p.deaths ?? 0; a.a += p.assists ?? 0
    a.gold += p.gold ?? 0; a.dmg += p.damage ?? 0; a.cs += p.cs ?? 0
    agg.set(name, a)
  }
  const leaderboard = [...agg.values()]
    .map(a => {
      const g = a.wins + a.losses
      return { ...a, games: g,
               wr: Math.round(100 * a.wins / Math.max(1, g)),
               kda: ((a.k + a.a) / Math.max(1, a.d)).toFixed(2),
               avgDmg: Math.round(a.dmg / Math.max(1, g)),
               avgGold: Math.round(a.gold / Math.max(1, g)),
               avgCs: Math.round(a.cs / Math.max(1, g)) }
    })
    .sort((x, y) =>
      (y.wins / Math.max(1, y.games)) - (x.wins / Math.max(1, x.games))
      || y.games - x.games)

  // H2H — vs (cross-team) and with (same-team) records per roster pair.
  const h2h = new Map()  // "A|B" -> {vsW, vsG, withW, withG}
  const cell = k => { if (!h2h.has(k)) h2h.set(k, { vsW: 0, vsG: 0, withW: 0, withG: 0 }); return h2h.get(k) }
  for (const ps of byMatch.values()) {
    const named = ps.map(p => ({ ...p, dn: sumToDisplay[p.player] })).filter(p => p.dn)
    for (const a of named) for (const b of named) {
      if (a.dn === b.dn) continue
      if (a.team !== b.team) { const c = cell(`${a.dn}|${b.dn}`); c.vsG++; if (a.win) c.vsW++ }
      else { const c = cell(`${a.dn}|${b.dn}`); c.withG++; if (a.win) c.withW++ }
    }
  }
  return { matches, byMatch, leaderboard, sumToDisplay, h2h }
}
