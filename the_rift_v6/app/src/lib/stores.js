import { writable } from 'svelte/store'

export const screen = writable('home')          // active tab id
export const dissolveSignal = writable(0)       // bump to fire hex dissolve

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
