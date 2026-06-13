// League identity — who is using this client. Set by the tier-list LCU
// detection or a manual pick; shared by draft sync (lobby name) and
// tier-vote submission.
import { writable } from 'svelte/store'

const KEY = 'rift_identity'
const MAP_KEY = 'rift_summoner_links'   // gameName -> player display name

const saved = typeof localStorage !== 'undefined'
  ? (localStorage.getItem(KEY) ?? '') : ''

export const identity = writable(saved)
identity.subscribe(v => {
  try { localStorage.setItem(KEY, v ?? '') } catch {}
})

export function setIdentity(name) { identity.set(name ?? '') }

// Local summoner→player links (mirrors v5's config summoner_map): remembered
// after the user answers WHO ARE YOU once for an unknown Riot gameName.
export function localLink(gameName) {
  try {
    const m = JSON.parse(localStorage.getItem(MAP_KEY) ?? '{}')
    return m[gameName] ?? null
  } catch { return null }
}

export function saveLink(gameName, playerName) {
  try {
    const m = JSON.parse(localStorage.getItem(MAP_KEY) ?? '{}')
    m[gameName] = playerName
    localStorage.setItem(MAP_KEY, JSON.stringify(m))
  } catch {}
}
