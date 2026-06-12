<script>
  import { onMount } from 'svelte'
  import { fly, fade } from 'svelte/transition'
  import { api, splashUrl, iconUrl, leagueData } from '../api.js'
  import { selectedPlayer } from '../stores.js'

  let players = [], sel = null, lbByName = {}
  let champsBy = {}, rolesBy = {}, histBy = {}, league = null
  let ready = false

  onMount(async () => {
    try {
      const [s, d, ic, pr, rh] = await Promise.all([
        api('/scout'), leagueData(),
        api('/inhouse-champs'), api('/primary-roles'), api('/rank-history'),
      ])
      players = s?.scout ?? []
      league = d
      for (const p of d.leaderboard) lbByName[p.name] = p
      champsBy = ic?.inhouse_champs ?? {}
      rolesBy = pr?.primary_roles ?? {}
      histBy = rh?.rank_history ?? {}
      const want = $selectedPlayer
      sel = (want && players.find(p => p.name === want)) || players[0] || null
      selectedPlayer.set(null)
    } catch (e) { console.error(e) }
    ready = true
  })
  const formColor = f => f === 'HOT' ? 'var(--win)' : f === 'COLD' ? 'var(--loss)' : 'var(--txt-dim)'

  // Last-10 customs form from export (matches sorted newest-first).
  function lastForm(name) {
    if (!league) return []
    const out = []
    for (const m of league.matches) {
      const row = (league.byMatch.get(m.id) ?? [])
        .find(p => league.sumToDisplay[p.player] === name)
      if (row) out.push(!!row.win)
      if (out.length >= 10) break
    }
    return out
  }
  // Best duo + nemesis from the h2h map (min 3 shared games).
  function bonds(name) {
    if (!league) return {}
    let duo = null, nem = null
    for (const [k, c] of league.h2h) {
      const [a, b] = k.split('|')
      if (a !== name) continue
      if (c.withG >= 3) {
        const r = c.withW / c.withG
        if (!duo || r > duo.r) duo = { who: b, r, w: c.withW, g: c.withG }
      }
      if (c.vsG >= 3) {
        const r = c.vsW / c.vsG
        if (!nem || r < nem.r) nem = { who: b, r, w: c.vsW, g: c.vsG }
      }
    }
    return { duo, nem }
  }
  // Rank-history sparkline points (SVG polyline, 220x44 box).
  function spark(name) {
    const h = histBy[name] ?? []
    if (h.length < 2) return null
    const vals = h.map(p => p.value)
    const min = Math.min(...vals), max = Math.max(...vals)
    const span = Math.max(1, max - min)
    return vals.map((v, i) =>
      `${(i / (vals.length - 1)) * 220},${40 - ((v - min) / span) * 36 + 2}`
    ).join(' ')
  }
  $: champPool = sel ? (champsBy[sel.name] ?? []).slice(0, 6) : []
  $: form = sel ? lastForm(sel.name) : []
  $: bond = sel ? bonds(sel.name) : {}
  $: sparkPts = sel ? spark(sel.name) : null
</script>

<div class="wrap">
  <section class="glass list">
    <header><span class="kicker">◆ PLAYER SCOUTING</span><div class="rule-fade"></div></header>
    {#each players as p, i (p.name)}
      <button class="row" class:sel={sel?.name === p.name}
              in:fly={{ x: -26, duration: 380, delay: i * 40 }}
              on:click={() => sel = p}>
        <span class="rk">{p.rank}</span>
        <span class="nm">{p.name.toUpperCase()}</span>
        <span class="sc gold-text">{Math.round(p.score)}</span>
        <span class="wr" class:up={p.wr >= 52} class:down={p.wr < 48}>{p.wr}%</span>
        <span class="mono">{p.kda}</span>
        <span class="form" style="color:{formColor(p.form)}">{p.form ?? ''}</span>
      </button>
    {/each}
  </section>

  {#if sel}
    {#key sel.name}
    <section class="report" in:fade={{ duration: 300 }}>
      <div class="card glass">
        {#if sel.top_champs?.[0]}
          <div class="bg" style="background-image:url({splashUrl(sel.top_champs[0])})"></div>
        {/if}
        <div class="veil"></div>
        <div class="inner">
          <div class="kick">SCOUTING REPORT · {sel.tier?.toUpperCase()}
            {#if rolesBy[sel.name]} · {rolesBy[sel.name]} MAIN{/if}</div>
          <h1 class="gold-sweep">{sel.name.toUpperCase()}</h1>
          <div class="chips">
            <div class="chip"><b>{Math.round(sel.score)}</b><span>SCORE</span></div>
            <div class="chip"><b class:up={sel.wr >= 52} class:down={sel.wr < 48}>{sel.wr}%</b><span>WIN RATE</span></div>
            <div class="chip"><b>{sel.kda}</b><span>KDA</span></div>
            <div class="chip"><b>{sel.games}</b><span>GAMES</span></div>
            <div class="chip"><b style="color:{formColor(sel.form)}">{sel.form ?? '—'}</b><span>FORM</span></div>
          </div>
        </div>
        <div class="flow-line edge"></div>
      </div>

      <div class="glass pool">
        <header><span class="kicker">◆ SIGNATURE PICKS</span><div class="rule-fade"></div></header>
        <div class="champs">
          {#each (sel.top_champs ?? []) as c, i}
            <div class="champ" in:fly={{ y: 18, duration: 400, delay: 120 + i * 110 }}>
              <img src={iconUrl(c)} alt={c} />
              <span>{c}</span>
              {#if i === 0}<em class="kicker">BAN-WORTHY</em>{/if}
            </div>
          {/each}
        </div>
      </div>

      {#if lbByName[sel.name]}
        {@const ih = lbByName[sel.name]}
        <div class="glass pool">
          <header><span class="kicker">◆ IN-HOUSE RECORD</span><div class="rule-fade"></div></header>
          <div class="statline mono">
            <span><b>{ih.wins}–{ih.losses}</b> customs</span>
            <span><b class:up={ih.wr >= 52} class:down={ih.wr < 48}>{ih.wr}%</b> win rate</span>
            <span><b>{ih.kda}</b> KDA</span>
            <span><b>{ih.avgDmg.toLocaleString()}</b> avg dmg</span>
          </div>
          {#if form.length}
            <div class="formrow">
              <span class="kicker dim2">LAST {form.length}</span>
              {#each form as w}<i class="fdot" class:w></i>{/each}
            </div>
          {/if}
          {#if bond.duo || bond.nem}
            <div class="bonds mono">
              {#if bond.duo}<span>BEST DUO · <b>{bond.duo.who.toUpperCase()}</b> {bond.duo.w}–{bond.duo.g - bond.duo.w} together</span>{/if}
              {#if bond.nem}<span>NEMESIS · <b>{bond.nem.who.toUpperCase()}</b> {bond.nem.w}–{bond.nem.g - bond.nem.w} against</span>{/if}
            </div>
          {/if}
        </div>
      {/if}

      {#if champPool.length}
        <div class="glass pool">
          <header><span class="kicker">◆ CUSTOMS CHAMP POOL</span><div class="rule-fade"></div></header>
          {#each champPool as c, i (c.champ)}
            <div class="crow" in:fly={{ x: -18, duration: 350, delay: 80 + i * 60 }}>
              <img src={iconUrl(c.champ)} alt={c.champ} />
              <b>{c.champ}</b>
              <span class="mono">{c.games} GP</span>
              <span class="mono">{c.wins}–{c.losses}</span>
              <div class="cbar"><em style="width:{parseFloat(c.wr)}%"></em></div>
              <span class="cwr" class:up={parseFloat(c.wr) >= 52} class:down={parseFloat(c.wr) < 48}>{c.wr}</span>
              <span class="mono">{c.kda} KDA</span>
            </div>
          {/each}
        </div>
      {/if}

      {#if sparkPts}
        <div class="glass pool">
          <header><span class="kicker">◆ RANK JOURNEY</span><div class="rule-fade"></div></header>
          <svg viewBox="0 0 220 44" class="sparksvg" preserveAspectRatio="none">
            <polyline points={sparkPts} fill="none" stroke="var(--gold)"
                      stroke-width="2" stroke-linejoin="round"
                      style="filter: drop-shadow(0 0 4px rgba(200,170,110,.7))" />
          </svg>
          <div class="mono dim2" style="font-size:10px">
            {(histBy[sel.name] ?? []).at(-1)?.tier ?? ''} {(histBy[sel.name] ?? []).at(-1)?.division ?? ''} — last {histBy[sel.name]?.length ?? 0} samples
          </div>
        </div>
      {/if}
    </section>
    {/key}
  {/if}
</div>

<style>
  .wrap { height: 100%; overflow-y: auto; padding: 26px;
          display: grid; grid-template-columns: 1fr 1.15fr; gap: 18px;
          align-items: start; }
  .list { padding: 16px 14px; }
  header { display: flex; align-items: center; gap: 14px; margin-bottom: 10px; }
  .row {
    width: 100%;
    display: grid; grid-template-columns: 30px 1fr 54px 52px 46px 50px;
    align-items: center; gap: 10px;
    padding: 10px 10px; border-radius: 9px;
    background: transparent; border: 1px solid transparent;
    color: var(--txt); font-family: var(--font-ui); cursor: pointer;
    text-align: left; transition: all .2s;
  }
  .row:hover { background: rgba(200,170,110,.07); transform: translateX(4px); }
  .row.sel { background: linear-gradient(90deg, rgba(200,170,110,.14), transparent);
             border-color: rgba(200,170,110,.4);
             box-shadow: 0 0 18px rgba(200,170,110,.12); }
  .rk { font-family: var(--font-mono); font-size: 12px; color: var(--txt-faint); }
  .nm { font-weight: 700; font-size: 15px; letter-spacing: 1px; }
  .sc { font-weight: 700; font-size: 16px; text-align: right; }
  .wr { font-weight: 700; text-align: right; font-size: 13px; }
  .mono { font-family: var(--font-mono); font-size: 12px; color: #9eb4c8; text-align: right; }
  .form { font-family: var(--font-mono); font-size: 10px; letter-spacing: 1px; text-align: right; }
  .up { color: var(--win); } .down { color: var(--loss); }

  .report { display: flex; flex-direction: column; gap: 16px; }
  .card { position: relative; overflow: hidden; height: 250px; }
  .bg { position: absolute; inset: -24px; background-size: cover;
        background-position: center 18%;
        animation: pan 28s ease-in-out infinite alternate; }
  @keyframes pan { from { transform: scale(1.05) } to { transform: scale(1.13) translateX(-14px) } }
  .veil { position: absolute; inset: 0;
          background: linear-gradient(180deg, rgba(6,13,26,.3), rgba(6,13,26,.94) 85%); }
  .inner { position: absolute; inset: 20px; display: flex; flex-direction: column; justify-content: flex-end; }
  .kick { font-family: var(--font-mono); font-size: 10px; letter-spacing: 3px;
          color: var(--gold); margin-bottom: 4px; }
  h1 { font-family: var(--font-display); font-size: 34px; letter-spacing: 4px; }
  .chips { display: flex; gap: 10px; margin-top: 14px; flex-wrap: wrap; }
  .chip {
    padding: 8px 16px; border-radius: 9px;
    background: rgba(13,28,50,.6); backdrop-filter: blur(10px);
    border: 1px solid rgba(200,170,110,.3);
    display: flex; flex-direction: column; align-items: center;
  }
  .chip b { font-size: 19px; color: var(--gold-lt); }
  .chip span { font-family: var(--font-mono); font-size: 9px; letter-spacing: 1.5px;
               color: var(--txt-faint); }
  .edge { position: absolute; left: 0; right: 0; bottom: 0; }

  .pool { padding: 16px 18px; }
  .champs { display: flex; gap: 16px; }
  .champ { display: flex; flex-direction: column; align-items: center; gap: 6px; }
  .champ img { width: 64px; height: 64px; border-radius: 12px;
               border: 1px solid rgba(200,170,110,.4);
               box-shadow: 0 8px 22px rgba(0,0,0,.4);
               transition: transform .2s; }
  .champ:hover img { transform: scale(1.1) rotate(2deg);
                     box-shadow: 0 0 24px rgba(200,170,110,.35); }
  .champ span { font-size: 13px; font-weight: 600; }
  .champ em { font-style: normal; font-size: 8px; color: var(--loss); }
  .statline { display: flex; gap: 26px; font-size: 12px; color: var(--txt-dim); flex-wrap: wrap; }
  .statline b { color: var(--txt); font-size: 15px; }
  .formrow { display: flex; align-items: center; gap: 5px; margin-top: 12px; }
  .dim2 { color: var(--txt-faint); }
  .fdot { width: 12px; height: 12px; border-radius: 50%;
          background: rgba(224,108,95,.8); box-shadow: 0 0 8px rgba(224,108,95,.4); }
  .fdot.w { background: var(--win); box-shadow: 0 0 8px rgba(110,190,140,.5); }
  .bonds { display: flex; gap: 24px; margin-top: 12px; font-size: 11px;
           color: var(--txt-dim); flex-wrap: wrap; }
  .bonds b { color: var(--gold-lt); }
  .crow { display: grid; grid-template-columns: 34px 1fr 50px 50px 90px 52px 70px;
          align-items: center; gap: 10px; padding: 6px 4px; border-radius: 8px;
          transition: background .2s; }
  .crow:hover { background: rgba(200,170,110,.06); }
  .crow img { width: 30px; height: 30px; border-radius: 7px;
              border: 1px solid rgba(200,170,110,.3); }
  .crow b { font-size: 14px; }
  .cbar { height: 4px; border-radius: 2px; background: rgba(255,255,255,.06); }
  .cbar em { display: block; height: 100%; border-radius: 2px;
             background: linear-gradient(90deg, var(--gold-dk), var(--gold-hot));
             box-shadow: 0 0 8px rgba(200,170,110,.5); }
  .cwr { font-weight: 700; font-size: 12px; text-align: right; }
  .sparksvg { width: 100%; height: 52px; margin-bottom: 6px; }
  @media (max-width: 1100px) { .wrap { grid-template-columns: 1fr; } }
</style>
