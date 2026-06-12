<script>
  import { onMount } from 'svelte'
  import { fly } from 'svelte/transition'
  import { api } from '../api.js'

  let stats = null, log = []
  const note = (s, ok = true) => { log = [{ s, ok, t: new Date().toLocaleTimeString() }, ...log].slice(0, 8) }

  onMount(refreshStats)
  async function refreshStats() {
    try { stats = await api('/stats', { ttl: 0 }) } catch { stats = null }
  }

  let busy = false
  async function recompute() {
    busy = true
    try {
      const r = await fetch('/api/rankings/recompute', { method: 'POST' })
      note(r.ok ? 'Rankings recomputed on the server.' : `Recompute failed (${r.status})`, r.ok)
    } catch (e) { note(`Recompute failed: ${e.message}`, false) }
    busy = false
    refreshStats()
  }
  function clearCache() {
    location.reload()
  }
  const ago = ts => {
    if (!ts) return '—'
    const s = Math.floor((Date.now() - new Date(ts)) / 1000)
    if (s < 3600) return `${Math.floor(s / 60)}m ago`
    if (s < 86400) return `${Math.floor(s / 3600)}h ago`
    return `${Math.floor(s / 86400)}d ago`
  }
</script>

<div class="wrap">
  <header class="top"><span class="kicker">◆ COMMANDS</span><div class="rule-fade"></div></header>

  <section class="glass card" in:fly={{ y: 24, duration: 450 }}>
    <h3 class="gold-text">DATA FRESHNESS</h3>
    {#if stats}
      <div class="stats mono">
        <span><b>{stats.matches}</b> matches</span>
        <span><b>{stats.participants}</b> participants</span>
        <span>last game ingested <b>{ago(stats.last_ingest)}</b></span>
      </div>
    {:else}<p class="dim">server unreachable</p>{/if}
  </section>

  <section class="glass card" in:fly={{ y: 24, duration: 450, delay: 100 }}>
    <h3 class="gold-text">SERVER ACTIONS</h3>
    <div class="actions">
      <button class="act" disabled={busy} on:click={recompute}>
        <b>RECOMPUTE RANKINGS</b>
        <span>Rebuild ladder scores from the latest rank samples</span>
      </button>
      <button class="act" on:click={clearCache}>
        <b>RELOAD DATA</b>
        <span>Drop the local cache and re-pull everything</span>
      </button>
    </div>
    {#each log as l}
      <div class="logline mono" class:bad={!l.ok}>{l.t} — {l.s}</div>
    {/each}
  </section>

  <section class="glass card" in:fly={{ y: 24, duration: 450, delay: 200 }}>
    <h3 class="gold-text">LOCAL ACTIONS</h3>
    <p class="dim">FETCH RANKS and LOG GAME talk to the Riot API and your League
       client — they run from <b>The Rift v5</b> (or the v6 desktop sidecar,
       coming with the packaged build).</p>
  </section>
</div>

<style>
  .wrap { height: 100%; overflow-y: auto; padding: 26px; max-width: 820px; }
  .top { display: flex; align-items: center; gap: 14px; margin-bottom: 16px; }
  .card { padding: 22px 24px; margin-bottom: 16px; }
  h3 { font-family: var(--font-display); letter-spacing: 3px; font-size: 17px; margin-bottom: 12px; }
  .stats { display: flex; gap: 28px; flex-wrap: wrap; font-size: 12px; color: var(--txt-dim); }
  .stats b { color: var(--gold-lt); font-size: 16px; }
  .mono { font-family: var(--font-mono); }
  .dim { color: var(--txt-dim); font-size: 14px; line-height: 1.5; }
  .dim b { color: var(--gold-lt); }
  .actions { display: flex; gap: 14px; flex-wrap: wrap; margin-bottom: 12px; }
  .act {
    flex: 1; min-width: 230px; text-align: left; cursor: pointer;
    padding: 14px 18px; border-radius: 10px;
    background: linear-gradient(180deg, rgba(200,170,110,.16), rgba(120,90,40,.10));
    border: 1px solid rgba(200,170,110,.4);
    color: var(--txt); font-family: var(--font-ui);
    transition: all .2s;
  }
  .act:hover:not(:disabled) { border-color: var(--gold-hot);
    box-shadow: 0 0 22px rgba(200,170,110,.25); transform: translateY(-2px); }
  .act:disabled { opacity: .5; cursor: wait; }
  .act b { display: block; letter-spacing: 2px; font-size: 14px; color: var(--gold-lt); }
  .act span { font-size: 12px; color: var(--txt-dim); }
  .logline { font-size: 11px; color: var(--win); padding: 3px 0; }
  .logline.bad { color: var(--loss); }
</style>
