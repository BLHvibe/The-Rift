<script>
  import { onMount } from 'svelte'
  import { fly } from 'svelte/transition'
  import { api, post } from '../api.js'

  let stats = null, log = []
  const note = (s, ok = true) => { log = [{ s, ok, t: new Date().toLocaleTimeString() }, ...log].slice(0, 10) }

  // Sidecar presence — gates the LOCAL ACTIONS card.
  let sidecar = null   // null = checking, true/false = result

  onMount(async () => {
    refreshStats()
    try {
      const r = await fetch('/local/lcu/summoner')
      // any JSON response (even {ok:false, league not running}) means the
      // sidecar is alive; only a network/proxy failure means it's absent.
      sidecar = r.ok
    } catch { sidecar = false }
  })

  async function refreshStats() {
    try { stats = await api('/stats', { ttl: 0 }) } catch { stats = null }
  }

  // ── Server actions ──────────────────────────────────────────────────────
  let busyServer = false
  async function recompute() {
    busyServer = true
    try {
      const r = await fetch('/api/rankings/recompute', { method: 'POST' })
      note(r.ok ? 'Rankings recomputed on the server.' : `Recompute failed (${r.status})`, r.ok)
    } catch (e) { note(`Recompute failed: ${e.message}`, false) }
    busyServer = false
    refreshStats()
  }
  const clearCache = () => location.reload()

  // ── Local (sidecar) actions — start a job, poll until done ──────────────
  let running = null    // label of the in-flight job, or null
  let progress = 0
  let liveLine = ''

  // /local endpoints are sidecar-only — NOT under the /api proxy, so they
  // use a raw fetch rather than the /api-prefixed helpers.
  const local = (path, method = 'GET') =>
    fetch(`/local${path}`, { method }).then(r => r.json())

  async function runJob(path, label) {
    if (running) { note('A command is already running.', false); return }
    running = label
    progress = 0
    liveLine = 'starting…'
    note(`▶ ${label} started.`)
    try {
      const start = await local(path, 'POST')
      if (!start.ok) { note(`${label}: ${start.error}`, false); running = null; return }
      const jobId = start.job
      // poll
      for (;;) {
        await new Promise(r => setTimeout(r, 1500))
        const j = await local(`/jobs/${jobId}`)
        progress = j.progress ?? 0
        liveLine = (j.log ?? []).slice(-1)[0] ?? ''
        if (j.done) {
          if (j.ok) {
            const sum = j.summary ?? {}
            const detail = sum.new_games !== undefined
              ? `${sum.new_games} new game${sum.new_games === 1 ? '' : 's'}`
              : sum.refreshed !== undefined ? `${sum.refreshed} players`
              : 'complete'
            note(`✓ ${label} — ${detail}.`)
            refreshStats()
          } else {
            note(`✗ ${label}: ${(j.summary ?? {}).error ?? 'failed'}`, false)
          }
          break
        }
      }
    } catch (e) { note(`${label} error: ${e.message}`, false) }
    running = null
    liveLine = ''
  }

  // JOIN TIER LIST — register a new player on the server roster.
  let joinName = ''
  async function joinTierList() {
    const n = joinName.trim()
    if (!n) return
    try {
      const cur = (await api('/players', { ttl: 0 }))?.players ?? []
      if (cur.includes(n)) { note(`${n} is already on the roster.`); joinName = ''; return }
      // upsert just the new row — the server INSERT-OR-REPLACEs by display_name.
      await post('/players', { players: [{ display_name: n }] })
      note(`✓ Registered ${n} into the tier list roster.`)
      joinName = ''
    } catch (e) { note(`Join failed: ${e.message}`, false) }
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

  <section class="glass card" in:fly={{ y: 24, duration: 450, delay: 80 }}>
    <h3 class="gold-text">SERVER ACTIONS</h3>
    <div class="actions">
      <button class="act" disabled={busyServer} on:click={recompute}>
        <b>RECOMPUTE RANKINGS</b>
        <span>Rebuild ladder scores from the latest rank samples</span>
      </button>
      <button class="act" on:click={clearCache}>
        <b>RELOAD DATA</b>
        <span>Drop the local cache and re-pull everything</span>
      </button>
    </div>
  </section>

  <section class="glass card" in:fly={{ y: 24, duration: 450, delay: 160 }}>
    <h3 class="gold-text">LOCAL ACTIONS</h3>
    {#if sidecar === null}
      <p class="dim">checking for the desktop sidecar…</p>
    {:else if sidecar}
      <p class="dim">These talk to the Riot API and your League client through
        the desktop app.</p>
      <div class="actions">
        <button class="act" disabled={!!running} on:click={() => runJob('/fetch-ranks', 'FETCH RANKS')}>
          <b>FETCH RANKS</b>
          <span>Pull every player's current rank from the Riot API</span>
        </button>
        <button class="act" disabled={!!running} on:click={() => runJob('/run-scout', 'RUN SCOUT')}>
          <b>RUN SCOUT</b>
          <span>Full scout pass — champ pools, rank, form for the roster</span>
        </button>
        <button class="act" disabled={!!running} on:click={() => runJob('/log-game', 'LOG INHOUSE GAME')}>
          <b>LOG INHOUSE GAME</b>
          <span>Scrape the last custom games from your client → the DB</span>
        </button>
      </div>

      <div class="join">
        <input placeholder="new player name…" bind:value={joinName}
               on:keydown={e => e.key === 'Enter' && joinTierList()} />
        <button class="joinb" on:click={joinTierList}>JOIN TIER LIST</button>
      </div>

      {#if running}
        <div class="runbar" transition:fly={{ y: 8, duration: 200 }}>
          <span class="mono">{running} · {liveLine}</span>
          <div class="pbar"><em style="width:{progress * 100}%"></em></div>
        </div>
      {/if}
    {:else}
      <p class="dim">FETCH RANKS, RUN SCOUT and LOG GAME need the desktop app's
        local sidecar (LCU + Riot access). In the browser they're unavailable —
        run <b>The Rift v6</b> desktop build, or for dev start
        <code>python desktop/launcher.py --dev</code>.</p>
    {/if}

    {#each log as l}
      <div class="logline mono" class:bad={!l.ok}>{l.t} — {l.s}</div>
    {/each}
  </section>
</div>

<style>
  .wrap { height: 100%; overflow-y: auto; padding: 26px; max-width: 860px; }
  .top { display: flex; align-items: center; gap: 14px; margin-bottom: 16px; }
  .card { padding: 22px 24px; margin-bottom: 16px; }
  h3 { font-family: var(--font-display); letter-spacing: 3px; font-size: 17px; margin-bottom: 12px; }
  .stats { display: flex; gap: 28px; flex-wrap: wrap; font-size: 12px; color: var(--txt-dim); }
  .stats b { color: var(--gold-lt); font-size: 16px; }
  .mono { font-family: var(--font-mono); }
  .dim { color: var(--txt-dim); font-size: 14px; line-height: 1.5; }
  .dim b { color: var(--gold-lt); }
  .dim code { font-family: var(--font-mono); font-size: 12px; color: var(--gold-lt);
              background: rgba(200,170,110,.1); padding: 1px 6px; border-radius: 4px; }
  .actions { display: flex; gap: 14px; flex-wrap: wrap; margin-bottom: 12px; }
  .act {
    flex: 1; min-width: 220px; text-align: left; cursor: pointer;
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
  .join { display: flex; gap: 10px; margin: 6px 0 12px; }
  .join input { flex: 1; max-width: 280px; background: rgba(6,13,26,.7);
    border: 1px solid rgba(200,170,110,.35); border-radius: 8px;
    padding: 9px 14px; color: var(--txt); font-family: var(--font-ui);
    font-size: 13px; outline: none; }
  .join input:focus { border-color: var(--gold); }
  .joinb { padding: 9px 18px; border-radius: 8px; cursor: pointer;
    background: rgba(255,255,255,.04); border: 1px solid rgba(200,170,110,.4);
    color: var(--gold-lt); font-family: var(--font-ui); font-weight: 700;
    letter-spacing: 2px; font-size: 12px; }
  .joinb:hover { border-color: var(--gold-hot); box-shadow: 0 0 14px rgba(200,170,110,.3); }
  .runbar { margin-bottom: 12px; }
  .runbar span { font-size: 11px; color: var(--gold-lt); display: block; margin-bottom: 6px; }
  .pbar { height: 5px; border-radius: 3px; background: rgba(255,255,255,.07); overflow: hidden; }
  .pbar em { display: block; height: 100%;
    background: linear-gradient(90deg, var(--gold-dk), var(--gold-hot));
    box-shadow: 0 0 10px rgba(200,170,110,.5); transition: width .4s ease; }
  .logline { font-size: 11px; color: var(--win); padding: 3px 0; }
  .logline.bad { color: var(--loss); }
</style>
