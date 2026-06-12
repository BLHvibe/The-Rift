<script>
  import { onMount } from 'svelte'
  import { fly, fade } from 'svelte/transition'
  import { api, iconUrl, splashUrl, leagueData } from '../api.js'

  // ── Tournament draft sequence (20 actions, v5 order) ───────────────────
  const SEQ = [
    ...['B','R','B','R','B','R'].map(s => ({ side: s, kind: 'ban' })),
    ...['B','R','R','B','B','R'].map(s => ({ side: s, kind: 'pick' })),
    ...['R','B','R','B'].map(s => ({ side: s, kind: 'ban' })),
    ...['R','B','B','R'].map(s => ({ side: s, kind: 'pick' })),
  ]

  let roster = [], scoreBy = {}, champsBy = {}, rolesBy = {}, scoutBy = {}
  let allChamps = []
  let teams = { B: [], R: [], pool: [] }
  let drag = null
  let board = Array(20).fill(null)     // champion name per action
  let cursor = 0
  let search = ''
  let ready = false

  onMount(async () => {
    try {
      const [r, ic, pr, s, d] = await Promise.all([
        api('/rankings'), api('/inhouse-champs'), api('/primary-roles'),
        api('/scout'), leagueData(),
      ])
      for (const p of (r?.rankings ?? [])) scoreBy[p.name] = +p.score
      champsBy = ic?.inhouse_champs ?? {}
      rolesBy = pr?.primary_roles ?? {}
      for (const p of (s?.scout ?? [])) scoutBy[p.name] = p
      teams.pool = d.leaderboard.map(p => p.name)
      const ver = (await (await fetch('https://ddragon.leagueoflegends.com/api/versions.json')).json())[0]
      const cj = await (await fetch(`https://ddragon.leagueoflegends.com/cdn/${ver}/data/en_US/champion.json`)).json()
      allChamps = Object.values(cj.data).map(c => c.name).sort()
    } catch (e) { console.error(e) }
    ready = true
  })

  function dropTo(zone) {
    if (!drag) return
    for (const k of Object.keys(teams)) teams[k] = teams[k].filter(n => n !== drag)
    if (zone !== 'pool' && teams[zone].length >= 5) zone = 'pool'
    teams[zone] = [...teams[zone], drag]
    drag = null; teams = teams
  }

  // ── Balance meter — elo-style logistic on avg ladder score ────────────
  $: avgB = teams.B.length ? teams.B.reduce((a, n) => a + (scoreBy[n] ?? 50), 0) / teams.B.length : 0
  $: avgR = teams.R.length ? teams.R.reduce((a, n) => a + (scoreBy[n] ?? 50), 0) / teams.R.length : 0
  $: pBlue = (teams.B.length && teams.R.length)
    ? 1 / (1 + Math.pow(10, -(avgB - avgR) / 12)) : 0.5

  // ── Intel — bans = enemy's proven customs champs; picks = your pools ──
  const taken = () => new Set(board.filter(Boolean))
  function banTargets(side) {
    const enemy = side === 'B' ? teams.R : teams.B
    const t = taken()
    const out = []
    for (const name of enemy) {
      for (const c of (champsBy[name] ?? [])) {
        const wr = parseFloat(c.wr) || 0
        const weight = wr * Math.min(1, c.games / 4)
        if (!t.has(c.champ)) out.push({ champ: c.champ, who: name, wr: c.wr, g: c.games, weight })
      }
      const sig = scoutBy[name]?.top_champs?.[0]
      if (sig && !t.has(sig)) out.push({ champ: sig, who: name, wr: 'signature', g: '', weight: 55 })
    }
    const seen = new Set()
    return out.sort((a, b) => b.weight - a.weight)
      .filter(c => !seen.has(c.champ) && seen.add(c.champ)).slice(0, 6)
  }
  function pickIdeas(side) {
    const mine = side === 'B' ? teams.B : teams.R
    const t = taken()
    const out = []
    for (const name of mine) {
      const best = (champsBy[name] ?? []).filter(c => !t.has(c.champ))
        .sort((a, b) => (parseFloat(b.wr) * Math.min(1, b.games / 3)) -
                        (parseFloat(a.wr) * Math.min(1, a.games / 3)))[0]
      if (best) out.push({ who: name, champ: best.champ, wr: best.wr, g: best.games })
    }
    return out
  }
  $: bansB = ready && teams.R.length ? banTargets('B') : []
  $: bansR = ready && teams.B.length ? banTargets('R') : []
  $: picksB = ready && teams.B.length ? pickIdeas('B') : []
  $: picksR = ready && teams.R.length ? pickIdeas('R') : []
  $: _board = board   // reactivity anchor for intel recompute
  $: heroPick = board.slice(6).find(Boolean) ?? null

  // ── Board interactions ─────────────────────────────────────────────────
  function assign(champ) {
    if (cursor >= 20 || taken().has(champ)) return
    board[cursor] = champ
    board = board
    const next = board.findIndex(c => !c)
    cursor = next === -1 ? 20 : next
    search = ''
  }
  function clearStep(i) { board[i] = null; board = board; cursor = i }
  $: filtered = search
    ? allChamps.filter(c => c.toLowerCase().includes(search.toLowerCase())).slice(0, 24)
    : []
</script>

<div class="wrap">
  {#if heroPick}
    <div class="bghero" style="background-image:url({splashUrl(heroPick)})" transition:fade></div>
  {/if}

  <header class="top">
    <span class="kicker">◆ WAR ROOM</span><div class="rule-fade"></div>
    <button class="resetb" on:click={() => { board = Array(20).fill(null); cursor = 0 }}>RESET DRAFT</button>
  </header>

  <!-- ── Team builder + balance ─────────────────────────────────────── -->
  <div class="builder">
    <div class="teamcol glass" style="--side:#59b3d4"
         on:dragover|preventDefault on:drop={() => dropTo('B')} role="list">
      <h3>BLUE SIDE</h3>
      {#each teams.B as n (n)}
        <span class="chip" draggable="true" on:dragstart={() => drag = n}>
          {n.toUpperCase()}<i>{rolesBy[n] ?? ''} · {Math.round(scoreBy[n] ?? 0)}</i></span>
      {/each}
    </div>

    <div class="meter glass">
      <span class="kicker">BALANCE</span>
      <div class="probs">
        <b style="color:#59b3d4">{Math.round(pBlue * 100)}</b>
        <span>vs</span>
        <b style="color:var(--loss)">{Math.round((1 - pBlue) * 100)}</b>
      </div>
      <div class="pbar"><em style="width:{pBlue * 100}%"></em></div>
      <span class="mono dim">{teams.B.length}v{teams.R.length} · ladder-score model</span>
    </div>

    <div class="teamcol glass" style="--side:var(--loss)"
         on:dragover|preventDefault on:drop={() => dropTo('R')} role="list">
      <h3>RED SIDE</h3>
      {#each teams.R as n (n)}
        <span class="chip" draggable="true" on:dragstart={() => drag = n}>
          {n.toUpperCase()}<i>{rolesBy[n] ?? ''} · {Math.round(scoreBy[n] ?? 0)}</i></span>
      {/each}
    </div>
  </div>

  <div class="pool glass" on:dragover|preventDefault on:drop={() => dropTo('pool')} role="list">
    <span class="kicker dim">ROSTER — drag five to each side</span>
    <div class="zone">
      {#each teams.pool as n (n)}
        <span class="chip" draggable="true" on:dragstart={() => drag = n}>{n.toUpperCase()}</span>
      {/each}
    </div>
  </div>

  <!-- ── Intel ──────────────────────────────────────────────────────── -->
  {#if teams.B.length && teams.R.length}
  <div class="intel" in:fly={{ y: 24, duration: 450 }}>
    {#each [['BLUE BANS — deny red', bansB, picksB, '#59b3d4'], ['RED BANS — deny blue', bansR, picksR, 'var(--loss)']] as [t, bans, picks, col]}
      <section class="glass icard" style="--side:{col}">
        <header><span class="kicker">◆ {t}</span><div class="rule-fade"></div></header>
        <div class="banrow">
          {#each bans as b}
            <button class="ban" title="{b.who} · {b.wr} in {b.g} customs" on:click={() => assign(b.champ)}>
              <img src={iconUrl(b.champ)} alt={b.champ} /><s></s>
              <span>{b.champ}</span><i>{b.who}</i>
            </button>
          {/each}
        </div>
        <div class="pickline">
          {#each picks as p}
            <span class="mono" role="button" tabindex="0" on:click={() => assign(p.champ)}>
              <b>{p.who.toUpperCase()}</b> → {p.champ} ({p.wr})</span>
          {/each}
        </div>
      </section>
    {/each}
  </div>
  {/if}

  <!-- ── Pick/ban board ─────────────────────────────────────────────── -->
  <section class="glass boardcard">
    <header>
      <span class="kicker">◆ DRAFT BOARD — tournament order</span><div class="rule-fade"></div>
      <input class="seek" placeholder="search champion…" bind:value={search} />
    </header>
    {#if filtered.length}
      <div class="grid8" transition:fade={{ duration: 150 }}>
        {#each filtered as c}
          <button class="gcell" disabled={taken().has(c)} on:click={() => assign(c)}>
            <img src={iconUrl(c)} alt={c} /><span>{c}</span>
          </button>
        {/each}
      </div>
    {/if}
    <div class="seq">
      {#each SEQ as a, i}
        <button class="step" class:blue={a.side === 'B'} class:red={a.side === 'R'}
                class:ban={a.kind === 'ban'} class:cur={i === cursor} class:done={board[i]}
                on:click={() => cursor = i}
                on:contextmenu|preventDefault={() => clearStep(i)}
                title="{a.side === 'B' ? 'Blue' : 'Red'} {a.kind} {i + 1}{board[i] ? ' — right-click to clear' : ''}">
          {#if board[i]}
            <img src={iconUrl(board[i])} alt={board[i]} />
            {#if a.kind === 'ban'}<s></s>{/if}
          {:else}
            <span>{a.kind === 'ban' ? 'BAN' : 'PICK'}</span>
          {/if}
        </button>
      {/each}
    </div>
    <div class="mono dim hint">click a slot to target it · search or click intel to assign · right-click clears</div>
  </section>
</div>

<style>
  .wrap { position: relative; height: 100%; overflow-y: auto; padding: 26px; }
  .bghero { position: fixed; inset: 0; background-size: cover; background-position: center 20%;
            opacity: .14; pointer-events: none; z-index: -1;
            mask-image: linear-gradient(180deg, black, transparent 80%); }
  .top { display: flex; align-items: center; gap: 14px; margin-bottom: 14px; }
  .resetb { padding: 7px 16px; border-radius: 8px; cursor: pointer;
    background: rgba(255,255,255,.04); border: 1px solid rgba(200,170,110,.3);
    color: var(--txt-dim); font-family: var(--font-ui); font-weight: 700;
    letter-spacing: 2px; font-size: 12px; }
  .resetb:hover { color: var(--gold-lt); border-color: var(--gold); }

  .builder { display: grid; grid-template-columns: 1fr 220px 1fr; gap: 14px; }
  .teamcol { padding: 14px; min-height: 150px;
             border-top: 3px solid var(--side); }
  .teamcol h3 { font-family: var(--font-mono); font-size: 11px; letter-spacing: 3px;
                color: var(--side); margin-bottom: 10px;
                text-shadow: 0 0 12px var(--side); }
  .chip { display: inline-flex; flex-direction: column; margin: 0 6px 6px 0;
          padding: 7px 14px; border-radius: 9px; cursor: grab;
          background: linear-gradient(180deg, rgba(22,48,79,.9), rgba(13,28,50,.9));
          border: 1px solid rgba(200,170,110,.35);
          font-weight: 700; font-size: 13px; letter-spacing: 1px; transition: all .18s; }
  .chip i { font-style: normal; font-family: var(--font-mono); font-size: 9px;
            color: var(--txt-faint); }
  .chip:hover { border-color: var(--gold-hot); transform: translateY(-2px);
                box-shadow: 0 0 14px rgba(200,170,110,.3); }
  .meter { padding: 16px; display: flex; flex-direction: column; align-items: center; gap: 8px; }
  .probs { display: flex; align-items: baseline; gap: 10px; }
  .probs b { font-size: 34px; font-weight: 700; text-shadow: 0 0 18px currentColor; }
  .probs span { color: var(--txt-faint); font-size: 12px; }
  .pbar { width: 100%; height: 7px; border-radius: 4px; background: rgba(224,108,95,.5); overflow: hidden; }
  .pbar em { display: block; height: 100%; background: linear-gradient(90deg, #2c7da0, #59b3d4);
             box-shadow: 0 0 12px rgba(89,179,212,.7); transition: width .7s cubic-bezier(.2,.8,.2,1); }
  .pool { margin-top: 14px; padding: 12px 16px; }
  .zone { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; min-height: 38px; }
  .dim { color: var(--txt-faint); }
  .mono { font-family: var(--font-mono); }

  .intel { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-top: 14px; }
  .icard { padding: 14px 16px; border-top: 3px solid var(--side); }
  .icard header { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; }
  .banrow { display: flex; gap: 10px; flex-wrap: wrap; }
  .ban { position: relative; display: flex; flex-direction: column; align-items: center;
         gap: 2px; background: none; border: none; cursor: pointer;
         color: var(--txt); font-family: var(--font-ui); }
  .ban img { width: 44px; height: 44px; border-radius: 9px;
             border: 1px solid rgba(224,108,95,.6); filter: saturate(.8); transition: transform .18s; }
  .ban:hover img { transform: scale(1.12); box-shadow: 0 0 16px rgba(224,108,95,.5); }
  .ban s { position: absolute; top: 21px; left: 4px; width: 36px; height: 2px;
           background: var(--loss); transform: rotate(-40deg);
           box-shadow: 0 0 8px var(--loss); }
  .ban span { font-size: 10px; } .ban i { font-style: normal; font-size: 8px; color: var(--txt-faint); }
  .pickline { display: flex; flex-direction: column; gap: 4px; margin-top: 10px; }
  .pickline span { font-size: 11px; color: var(--txt-dim); cursor: pointer; }
  .pickline span:hover { color: var(--gold-lt); }
  .pickline b { color: var(--txt); }

  .boardcard { margin-top: 14px; padding: 16px 18px; }
  .boardcard header { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
  .seek { background: rgba(6,13,26,.7); border: 1px solid rgba(200,170,110,.35);
          border-radius: 8px; padding: 8px 14px; color: var(--txt);
          font-family: var(--font-ui); font-size: 14px; width: 230px; outline: none; }
  .seek:focus { border-color: var(--gold); box-shadow: 0 0 14px rgba(200,170,110,.25); }
  .grid8 { display: grid; grid-template-columns: repeat(auto-fill, minmax(72px, 1fr));
           gap: 8px; margin-bottom: 14px; }
  .gcell { display: flex; flex-direction: column; align-items: center; gap: 3px;
           background: none; border: none; cursor: pointer; color: var(--txt-dim);
           font-family: var(--font-ui); font-size: 10px; }
  .gcell img { width: 44px; height: 44px; border-radius: 9px;
               border: 1px solid rgba(200,170,110,.3); transition: transform .15s; }
  .gcell:hover:not(:disabled) img { transform: scale(1.15);
               box-shadow: 0 0 14px rgba(200,170,110,.4); }
  .gcell:disabled { opacity: .25; cursor: default; }
  .seq { display: grid; grid-template-columns: repeat(20, 1fr); gap: 5px; }
  .step { aspect-ratio: 1; position: relative; border-radius: 8px; cursor: pointer;
          display: grid; place-items: center; overflow: hidden;
          background: rgba(6,13,26,.6); border: 1px solid rgba(255,255,255,.1);
          color: var(--txt-faint); font-family: var(--font-mono); font-size: 8px; }
  .step.blue { border-color: rgba(89,179,212,.45); }
  .step.red  { border-color: rgba(224,108,95,.45); }
  .step.ban  { border-style: dashed; }
  .step.cur  { border-color: var(--gold-hot); border-width: 2px;
               box-shadow: 0 0 16px rgba(200,170,110,.45);
               animation: curpulse 1.6s ease-in-out infinite; }
  @keyframes curpulse { 50% { box-shadow: 0 0 26px rgba(200,170,110,.7); } }
  .step img { width: 100%; height: 100%; object-fit: cover; }
  .step.done.ban img { filter: grayscale(.8) brightness(.7); }
  .step s { position: absolute; width: 80%; height: 2px; background: var(--loss);
            transform: rotate(-40deg); box-shadow: 0 0 8px var(--loss); }
  .hint { font-size: 10px; margin-top: 10px; }

  @media (max-width: 1100px) {
    .builder { grid-template-columns: 1fr; }
    .intel { grid-template-columns: 1fr; }
    .seq { grid-template-columns: repeat(10, 1fr); }
  }
</style>
