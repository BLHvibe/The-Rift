<script>
  // Tier list — gated behind LCU identity detection (v5 flow):
  //   gate (DETECT FROM LOL CLIENT → /local/lcu/summoner) → resolve via
  //   server summoner_map → local links → direct match → WHO ARE YOU picker
  //   → welcome cover ceremony → the list, rating as YOU. SUBMIT replaces
  //   your ballot on the server; CONSENSUS shows the league aggregate.
  import { onMount } from 'svelte'
  import { fly, fade } from 'svelte/transition'
  import { api, post } from '../api.js'
  import { motion } from '../stores.js'
  import { identity, setIdentity, localLink, saveLink } from '../identity.js'
  import { TIPS } from '../tips.js'

  const TIERS = [
    ['S', '#dc4646'], ['A', '#e08c3c'], ['B', '#c8aa6e'],
    ['C', '#6ec88c'], ['D', '#5a8cb4'], ['F', '#6e6e78'],
  ]
  const TIER_KEYS = TIERS.map(t => t[0])

  // gate | picker | cover | list  — the gate re-arms every app session.
  let stage = 'gate'
  let detecting = false
  let detectError = ''
  let summoner = ''          // raw gameName when the picker is needed
  let rater = ''
  let tip = ''
  let coverPct = 0

  let roster = []
  let sumToDisplay = {}
  let board = { S: [], A: [], B: [], C: [], D: [], F: [], pool: [] }
  let drag = null
  let view = 'ballot'        // ballot | consensus
  let aggregate = null
  let submitting = false
  let status = null          // {ok, msg}

  onMount(async () => {
    try {
      const p = await api('/players')
      roster = p?.players ?? []
      sumToDisplay = p?.summoner_map ?? {}
    } catch {}
  })

  // ── Identity gate ──────────────────────────────────────────────────────
  async function detect() {
    detecting = true
    detectError = ''
    try {
      const r = await fetch('/local/lcu/summoner').then(r => r.json())
      if (!r.ok) { detectError = r.error ?? 'detection failed'; return }
      const game = r.gameName
      const match = sumToDisplay[game] ?? localLink(game)
        ?? (roster.includes(game) ? game : null)
      if (match) enter(match)
      else { summoner = game; stage = 'picker' }
    } catch {
      detectError = 'Sidecar unreachable — run the desktop app (or `python desktop/launcher.py --dev`).'
    } finally { detecting = false }
  }

  function pickWho(name) {
    saveLink(summoner, name)
    enter(name)
  }

  async function enter(name) {
    rater = name
    setIdentity(name)
    tip = TIPS[Math.floor(Math.random() * TIPS.length)]
    stage = 'cover'
    // Cover ceremony — duration scales with the motion slider.
    const dur = 1200 + $motion * 3800
    coverPct = 0
    const t0 = performance.now()
    const step = now => {
      coverPct = Math.min(1, (now - t0) / dur)
      if (coverPct < 1 && stage === 'cover') requestAnimationFrame(step)
      else if (stage === 'cover') openList()
    }
    requestAnimationFrame(step)
  }

  async function openList() {
    board = { S: [], A: [], B: [], C: [], D: [], F: [], pool: [] }
    try {
      // Prefill from the server — your previous ballot comes back.
      const v = await api(`/tier-votes?rater=${encodeURIComponent(rater)}`, { ttl: 0 })
      for (const row of (v?.votes ?? [])) {
        if (TIER_KEYS.includes(row.rating) && roster.includes(row.player))
          board[row.rating].push(row.player)
      }
    } catch {}
    const placed = new Set(Object.values(board).flat())
    board.pool = roster.filter(n => !placed.has(n))
    board = board
    stage = 'list'
  }

  // ── Board interactions ─────────────────────────────────────────────────
  function dropTo(zone) {
    if (!drag) return
    for (const k of Object.keys(board)) board[k] = board[k].filter(n => n !== drag)
    board[zone] = [...board[zone], drag]
    drag = null
    board = board
  }
  function remove(name) {
    for (const k of TIER_KEYS) board[k] = board[k].filter(n => n !== name)
    if (!board.pool.includes(name)) board.pool = [...board.pool, name]
    board = board
  }
  function reset() {
    board = { S: [], A: [], B: [], C: [], D: [], F: [], pool: [...roster] }
  }
  $: placedCount = TIER_KEYS.reduce((a, t) => a + board[t].length, 0)

  // ── Submit / consensus ─────────────────────────────────────────────────
  async function submit() {
    if (submitting) return
    if (!placedCount) { status = { ok: false, msg: 'Place at least one player first.' }; return }
    submitting = true
    status = null
    try {
      const placements = Object.fromEntries(TIER_KEYS.map(t => [t, board[t]]))
      const r = await post('/tier-votes', { rater, placements })
      status = { ok: true, msg: `Ballot submitted as ${rater} — ${r.written} ratings saved.` }
      post('/activity', {
        event_type: 'TIER_LIST', actor: rater,
        details: `submitted tier-list ratings — ${placedCount} placed`,
      }).catch(() => {})
      aggregate = null   // stale now
    } catch (e) {
      status = { ok: false, msg: `Submit failed: ${e.message}` }
    }
    submitting = false
  }

  async function showConsensus() {
    view = 'consensus'
    if (!aggregate) {
      try {
        const r = await api('/tier-aggregate', { ttl: 0 })
        aggregate = r?.tier_aggregate ?? {}
      } catch { aggregate = {} }
    }
  }
  $: consensusRows = aggregate
    ? Object.entries(aggregate)
        .map(([name, a]) => ({ name, ...a }))
        .sort((x, y) => y.avg - x.avg)
    : []
  const tierColor = t => TIERS.find(([k]) => k === t)?.[1] ?? 'var(--txt-dim)'
</script>

<div class="wrap">
  <!-- ── GATE ─────────────────────────────────────────────────────────── -->
  {#if stage === 'gate'}
    <div class="gate" in:fade={{ duration: 300 }}>
      <h1 class="gold-sweep">TIER LIST</h1>
      <p class="dim">Identify yourself to begin rating</p>
      <button class="detectb" disabled={detecting} on:click={detect}>
        {detecting ? 'DETECTING…' : '⬡ DETECT FROM LOL CLIENT'}
      </button>
      {#if detectError}<p class="err mono" transition:fade>✗ {detectError}</p>{/if}
      <span class="hint mono">your ratings are tied to your league identity —
        the LoL client must be running</span>
    </div>

  <!-- ── WHO ARE YOU picker ──────────────────────────────────────────── -->
  {:else if stage === 'picker'}
    <div class="gate" in:fade={{ duration: 300 }}>
      <h1 class="gold-text">WHO ARE YOU?</h1>
      <p class="dim">Signed in as <b class="gold-text">'{summoner}'</b> — select your player name:</p>
      <div class="whogrid">
        {#each roster as n (n)}
          <button class="who" on:click={() => pickWho(n)}>{n.toUpperCase()}</button>
        {/each}
      </div>
      <button class="ghostb" on:click={() => stage = 'gate'}>← BACK</button>
    </div>

  <!-- ── WELCOME COVER ───────────────────────────────────────────────── -->
  {:else if stage === 'cover'}
    <div class="cover" out:fade={{ duration: 400 }}>
      <span class="cw" in:fly={{ y: -40, duration: 500 }}>Welcome,</span>
      <h1 class="cname gold-sweep" in:fly={{ y: -60, duration: 700 }}>{rater.toUpperCase()}</h1>
      <p class="ctip" in:fade={{ delay: 400, duration: 600 }}>{tip}</p>
      <div class="cbar"><em style="width:{coverPct * 100}%"></em></div>
      <span class="cload mono">LOADING TIER LIST…</span>
    </div>

  <!-- ── THE LIST ────────────────────────────────────────────────────── -->
  {:else}
    <header class="top">
      <span class="kicker">◆ TIER LIST</span><div class="rule-fade"></div>
      <div class="pills">
        <button class:active={view === 'ballot'} on:click={() => view = 'ballot'}>MY BALLOT</button>
        <button class:active={view === 'consensus'} on:click={showConsensus}>CONSENSUS</button>
      </div>
      {#if view === 'ballot'}
        <button class="ghostb" on:click={reset}>RESET</button>
        <button class="submitb" disabled={submitting} on:click={submit}>
          {submitting ? 'SUBMITTING…' : 'SUBMIT LIST'}</button>
      {/if}
    </header>

    <div class="raterbar glass">
      <span class="mono dim2">RATING AS</span>
      <b class="rname">✓ {rater.toUpperCase()}</b>
      <button class="redetect mono" on:click={() => { stage = 'gate'; detectError = '' }}>
        re-detect</button>
      <span class="spacer"></span>
      <span class="mono dim2">{placedCount}/{roster.length} placed</span>
    </div>
    {#if status}
      <div class="status mono" class:bad={!status.ok} transition:fade>{status.msg}</div>
    {/if}

    {#if view === 'ballot'}
      {#each TIERS as [t, color], i}
        <div class="tier glass" style="--tc:{color}"
             in:fly={{ y: 22, duration: 420, delay: i * 60 }}
             on:dragover|preventDefault on:drop={() => dropTo(t)} role="list">
          <span class="lbl" style="background:{color}">{t}</span>
          <div class="zone">
            {#each board[t] as n (n)}
              <span class="chip" draggable="true" role="button" tabindex="0"
                    title="right-click to remove"
                    on:dragstart={() => drag = n}
                    on:contextmenu|preventDefault={() => remove(n)}>{n.toUpperCase()}</span>
            {/each}
          </div>
        </div>
      {/each}

      <div class="pool glass" on:dragover|preventDefault on:drop={() => dropTo('pool')} role="list">
        <span class="kicker dim2">PLAYER POOL — drag names into tiers · right-click a placed name to remove</span>
        <div class="zone">
          {#each board.pool as n (n)}
            <span class="chip" draggable="true" role="button" tabindex="0"
                  on:dragstart={() => drag = n}>{n.toUpperCase()}</span>
          {/each}
        </div>
      </div>

    {:else}
      <!-- consensus -->
      {#if !aggregate}
        <p class="dim mono">loading league consensus…</p>
      {:else}
        <section class="glass agg" in:fade={{ duration: 300 }}>
          <div class="arow head mono">
            <span></span><span>PLAYER</span><span>CONSENSUS</span><span>AVG</span>
            <span>RANGE</span><span>VOTES</span><span>CONTROVERSY</span>
          </div>
          {#each consensusRows as r, i (r.name)}
            <div class="arow" in:fly={{ x: -20, duration: 300, delay: Math.min(i, 12) * 40 }}>
              <span class="mono dim2">{i + 1}</span>
              <b>{r.name.toUpperCase()}</b>
              <span class="tbadge" style="--tc:{tierColor(r.avg_tier)}">{r.avg_tier}</span>
              <span class="mono">{r.avg?.toFixed(2)}</span>
              <span class="mono dim2">{r.min}–{r.max}</span>
              <span class="mono">{r.votes}</span>
              <span class="contro"><em style="width:{Math.min(100, (r.std ?? 0) * 60)}%"></em></span>
            </div>
          {/each}
        </section>
      {/if}
    {/if}
  {/if}
</div>

<style>
  .wrap { height: 100%; overflow-y: auto; padding: 26px; }

  .gate { height: 100%; display: flex; flex-direction: column; align-items: center;
          justify-content: center; gap: 16px; text-align: center; }
  .gate h1 { font-family: var(--font-display); font-size: 44px; letter-spacing: 9px; }
  .gate p { color: var(--txt-dim); font-size: 14px; }
  .detectb { padding: 14px 30px; border-radius: 10px; cursor: pointer;
    background: linear-gradient(180deg, rgba(200,170,110,.3), rgba(120,90,40,.2));
    border: 1px solid rgba(200,170,110,.6); color: var(--gold-lt);
    font-family: var(--font-ui); font-weight: 700; letter-spacing: 2.5px;
    font-size: 14px; transition: all .25s; }
  .detectb:hover:not(:disabled) { border-color: var(--gold-hot);
    box-shadow: 0 0 26px rgba(200,170,110,.4); transform: translateY(-2px); }
  .detectb:disabled { opacity: .55; cursor: wait; }
  .err { color: var(--loss); font-size: 12px; max-width: 460px; }
  .hint { font-size: 10px; color: var(--txt-faint); }
  .whogrid { display: grid; grid-template-columns: repeat(4, minmax(130px, 1fr));
             gap: 10px; max-width: 640px; }
  .who { padding: 11px 14px; border-radius: 9px; cursor: pointer;
    background: linear-gradient(180deg, rgba(22,48,79,.9), rgba(13,28,50,.9));
    border: 1px solid rgba(200,170,110,.35); color: var(--gold-lt);
    font-family: var(--font-ui); font-weight: 700; font-size: 13px;
    letter-spacing: 1.5px; transition: all .18s; }
  .who:hover { border-color: var(--gold-hot); transform: translateY(-2px);
               box-shadow: 0 0 16px rgba(200,170,110,.3); }

  .cover { height: 100%; display: flex; flex-direction: column; align-items: center;
           justify-content: center; gap: 10px; }
  .cw { font-size: 22px; color: var(--txt-dim); }
  .cname { font-family: var(--font-display); font-size: 56px; letter-spacing: 10px; }
  .ctip { color: var(--txt-dim); font-size: 14px; margin-top: 14px;
          max-width: 560px; text-align: center; font-style: italic; }
  .cbar { width: min(420px, 70%); height: 6px; border-radius: 3px; margin-top: 30px;
          background: rgba(255,255,255,.07); overflow: hidden; }
  .cbar em { display: block; height: 100%;
             background: linear-gradient(90deg, var(--gold-dk), var(--gold-hot));
             box-shadow: 0 0 12px rgba(200,170,110,.6); }
  .cload { font-size: 9px; color: var(--txt-faint); letter-spacing: 3px; }

  .top { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
  .pills { display: flex; gap: 6px; }
  .pills button { padding: 7px 16px; border-radius: 8px; cursor: pointer;
    background: rgba(255,255,255,.04); border: 1px solid rgba(200,170,110,.2);
    color: var(--txt-dim); font-family: var(--font-ui); font-weight: 700;
    font-size: 12px; letter-spacing: 2px; transition: all .25s; }
  .pills button.active { color: var(--gold-lt);
    background: linear-gradient(180deg, rgba(200,170,110,.25), rgba(120,90,40,.18));
    border-color: rgba(200,170,110,.55);
    box-shadow: 0 0 18px rgba(200,170,110,.25); }
  .ghostb { padding: 7px 16px; border-radius: 8px; cursor: pointer;
    background: rgba(255,255,255,.04); border: 1px solid rgba(200,170,110,.3);
    color: var(--txt-dim); font-family: var(--font-ui); font-weight: 700;
    letter-spacing: 2px; font-size: 12px; }
  .ghostb:hover { color: var(--gold-lt); border-color: var(--gold); }
  .submitb { padding: 7px 18px; border-radius: 8px; cursor: pointer;
    background: linear-gradient(180deg, rgba(200,170,110,.32), rgba(120,90,40,.22));
    border: 1px solid rgba(200,170,110,.65); color: var(--gold-lt);
    font-family: var(--font-ui); font-weight: 700; letter-spacing: 2px;
    font-size: 12px; transition: all .2s; }
  .submitb:hover:not(:disabled) { border-color: var(--gold-hot);
    box-shadow: 0 0 18px rgba(200,170,110,.4); }
  .submitb:disabled { opacity: .55; cursor: wait; }

  .raterbar { display: flex; align-items: center; gap: 14px;
              padding: 9px 16px; margin-bottom: 10px; }
  .rname { color: var(--win); letter-spacing: 1.5px; font-size: 14px; }
  .redetect { background: none; border: none; cursor: pointer; font-size: 10px;
              color: var(--txt-faint); text-decoration: underline; }
  .redetect:hover { color: var(--gold-lt); }
  .spacer { flex: 1; }
  .status { padding: 8px 14px; margin-bottom: 10px; border-radius: 8px;
            font-size: 12px; color: var(--win);
            border: 1px solid rgba(110,190,140,.4);
            background: rgba(110,190,140,.08); }
  .status.bad { color: var(--loss); border-color: rgba(224,108,95,.4);
                background: rgba(224,108,95,.08); }

  .tier { display: flex; align-items: stretch; min-height: 66px;
          margin-bottom: 8px; overflow: hidden; }
  .lbl { width: 60px; display: grid; place-items: center;
    font-family: var(--font-display); font-size: 26px; color: #0a1428;
    text-shadow: 0 1px 0 rgba(255,255,255,.3);
    box-shadow: 0 0 26px color-mix(in srgb, var(--tc) 45%, transparent); }
  .zone { flex: 1; display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
          padding: 10px 14px; min-height: 46px; }
  .chip { padding: 8px 16px; border-radius: 9px; cursor: grab;
    background: linear-gradient(180deg, rgba(22,48,79,.9), rgba(13,28,50,.9));
    border: 1px solid rgba(200,170,110,.35);
    font-weight: 700; font-size: 13px; letter-spacing: 1.5px;
    transition: all .18s; }
  .chip:hover { border-color: var(--gold-hot); transform: translateY(-3px) scale(1.04);
                box-shadow: 0 8px 20px rgba(0,0,0,.5), 0 0 16px rgba(200,170,110,.3); }
  .chip:active { cursor: grabbing; }
  .pool { margin-top: 16px; padding: 14px 16px; }

  .agg { padding: 16px 18px; }
  .arow { display: grid;
    grid-template-columns: 30px 1.4fr 90px 70px 80px 60px 1fr;
    align-items: center; gap: 12px; padding: 8px 10px; border-radius: 8px; }
  .arow:not(.head):hover { background: rgba(200,170,110,.06); }
  .arow.head { font-size: 9px; letter-spacing: 1.5px; color: var(--txt-faint);
               border-bottom: 1px solid rgba(200,170,110,.18); }
  .arow b { font-size: 14px; letter-spacing: 1px; }
  .tbadge { width: 34px; height: 26px; display: grid; place-items: center;
    border-radius: 6px; font-family: var(--font-display); font-size: 15px;
    color: #0a1428; background: var(--tc);
    box-shadow: 0 0 14px color-mix(in srgb, var(--tc) 50%, transparent); }
  .contro { display: block; height: 5px; border-radius: 3px;
            background: rgba(255,255,255,.06); overflow: hidden; }
  .contro em { display: block; height: 100%; border-radius: 3px;
    background: linear-gradient(90deg, #5a8cb4, var(--loss));
    box-shadow: 0 0 8px rgba(224,108,95,.5); }

  .dim { color: var(--txt-dim); } .dim2 { color: var(--txt-faint); }
  .mono { font-family: var(--font-mono); }
  @media (max-width: 900px) { .whogrid { grid-template-columns: repeat(2, 1fr); } }
</style>
