<script>
  import { onMount } from 'svelte'
  import { fly } from 'svelte/transition'
  import { api } from '../api.js'

  const KIND = {
    UPDATE:  { c: 'var(--gold)',  t: 'UPD' },
    SCOUT:   { c: '#8c64dc',      t: 'SCT' },
    INHOUSE: { c: 'var(--win)',   t: 'IHG' },
    DRAFT:   { c: 'var(--blue-side)', t: 'DFT' },
    RANK:    { c: '#82afdc',      t: 'RNK' },
  }
  let groups = []
  let ready = false

  onMount(async () => {
    try {
      const a = await api('/activity')
      const evts = (a?.events ?? []).slice(0, 80)
      const byDay = new Map()
      for (const e of evts) {
        const day = (e.timestamp ?? '').slice(0, 10)
        if (!byDay.has(day)) byDay.set(day, [])
        byDay.get(day).push(e)
      }
      groups = [...byDay.entries()]
    } catch (e) { console.error(e) }
    ready = true
  })
  const meta = k => KIND[(k ?? '').toUpperCase()] ?? { c: 'var(--txt-faint)', t: '···' }
  const fmtDay = d => new Date(d + 'T12:00:00')
    .toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' }).toUpperCase()
</script>

<div class="wrap">
  <header class="top">
    <span class="kicker">◆ ACTIVITY FEED</span><div class="rule-fade"></div>
  </header>
  {#each groups as [day, evts], gi}
    <div class="day kicker" in:fly={{ y: 16, duration: 350, delay: gi * 60 }}>{fmtDay(day)}</div>
    {#each evts as e, i}
      {@const m = meta(e.event_type)}
      <div class="card glass" style="--ac:{m.c}"
           in:fly={{ y: 20, duration: 380, delay: gi * 60 + i * 50 }}>
        <span class="tag" style="color:{m.c}; border-color:{m.c}">{m.t}</span>
        <div class="body">
          <b>{(e.player && e.player !== 'Player' ? e.player : e.event_type ?? '').toUpperCase()}</b>
          <span>{e.details ?? ''}</span>
        </div>
        <span class="when mono">{(e.timestamp ?? '').slice(11, 16)}</span>
      </div>
    {/each}
  {/each}
  {#if ready && !groups.length}
    <div class="glass empty">Quiet on the Rift — log a game to wake the feed.</div>
  {/if}
</div>

<style>
  .wrap { height: 100%; overflow-y: auto; padding: 26px; max-width: 940px; }
  .top { display: flex; align-items: center; gap: 14px; margin-bottom: 16px; }
  .day { margin: 18px 4px 8px; opacity: .8; }
  .card {
    position: relative;
    display: flex; align-items: center; gap: 16px;
    padding: 13px 16px; margin-bottom: 8px;
    border-left: 3px solid var(--ac);
    border-radius: 0 12px 12px 0;
    transition: transform .2s, box-shadow .2s;
  }
  .card:hover { transform: translateX(5px); box-shadow: 0 10px 30px rgba(0,0,0,.45), 0 0 22px color-mix(in srgb, var(--ac) 22%, transparent); }
  .tag {
    font-family: var(--font-mono); font-size: 10px; letter-spacing: 1px;
    border: 1px solid; border-radius: 6px; padding: 5px 8px;
    text-shadow: 0 0 10px currentColor;
  }
  .body { display: flex; flex-direction: column; gap: 1px; flex: 1; }
  .body b { font-size: 14px; letter-spacing: 1px; }
  .body span { font-size: 13px; color: var(--txt-dim); }
  .when { font-size: 11px; color: var(--txt-faint); }
  .mono { font-family: var(--font-mono); }
  .empty { padding: 36px; text-align: center; color: var(--txt-dim); }
</style>
