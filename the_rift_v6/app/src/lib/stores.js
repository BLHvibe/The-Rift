import { writable } from 'svelte/store'

export const screen = writable('home')          // active tab id
export const dissolveSignal = writable(0)       // bump to fire hex dissolve

// Global motion intensity (0..1) — every FX layer respects it.
const saved = typeof localStorage !== 'undefined'
  ? +(localStorage.getItem('rift_motion') ?? 1) : 1
export const motion = writable(isNaN(saved) ? 1 : saved)
motion.subscribe(v => {
  try { localStorage.setItem('rift_motion', String(v)) } catch {}
})

export function navigate(to) {
  dissolveSignal.update(n => n + 1)
  // Let the dissolve veil cover the swap ~140ms in.
  setTimeout(() => screen.set(to), 140)
}

export const TABS = [
  { id: 'home',     label: 'HOME' },
  { id: 'rankings', label: 'RANKINGS' },
  { id: 'draft',    label: 'DRAFT' },
  { id: 'scout',    label: 'SCOUT' },
  { id: 'inhouse',  label: 'INHOUSE' },
  { id: 'tierlist', label: 'TIER LIST' },
  { id: 'feed',     label: 'FEED' },
  { id: 'settings', label: 'SETTINGS' },
]
