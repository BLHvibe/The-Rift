<script>
  import { onMount } from 'svelte'
  import { fly, fade } from 'svelte/transition'
  import { leagueData, iconUrl, api } from '../api.js'
  import { openScout } from '../stores.js'
  import MatchDetail from '../components/MatchDetail.svelte'

  let view = 'leader'
  let lb = [], matches = [], byMatch = new Map(), h2h = new Map(), roster = []
  let sumToDisplay = {}
  let selPair = null
  let ready = false
  let openMatch = null      // match id for the detail overlay

  // Records + predictions leaderboard — lazy-loaded on first RECORDS view.
  let records = null, predLb = null

  onMount(async () => {
    try {
      const d = await leagueData()
      lb = d.leaderboard; matches = d.matches; byMatch = d.byMatch
      h2h = d.h2h; sumToDisplay = d.sumToDisplay
      roster = lb.map(p => p.name)
    } catch (e) { console.error(e) }
    ready = true
  })

  async function loadRecords() {
    view = 'records'; selPair = null
    if (records) return
    try {
      const [r, pl] = await Promise.all([
        api('/records', { ttl: 120_000 }),
        api('/predictions/leaderboard?limit=20', { ttl: 60_000 }),
      ])
      records = r?.records ?? {}
      predLb = pl?.leaderboard ?? []
    } catch (e) { console.error(e) }
  }

  // Friendly labels + which records carry a champion/match link.
  const REC_LABELS = {
    most_kills: 'Most Kills', most_assists: 'Most Assists',
    most_damage: 'Most Damage', most_gold: 'Most Gold',
    most_cs: 'Most CS', most_vision: 'Most Vision',
    best_kda_game: 'Best KDA (game)', longest_match: 'Longest Match',
    shortest_match: 'Shortest Match', biggest_blowout: 'Biggest Blowout',
    longest_win_streak: 'Longest Win Streak',
    longest_loss_streak: 'Longest Loss Streak', most_games: 'Most Games',
  }
  const recValue = (k, r) => {
    const v = r?.value
    if (k === 'longest_match' || k === 'shortest_match')
      return `${Math.floor((v ?? 0) / 60)}m`
    if (k === 'most_damage' || k === 'most_gold')
      return (v ?? 0).toLocaleString()
    if (k === 'best_kda_game') return (v ?? 0).toFixed?.(2) ?? v
    return v
  }
  $: recordList = records
    ? Object.entries(records).filter(([, r]) => r).map(([k, r]) => ({ k, ...r }))
    : []

  const disp = s => sumToDisplay[s] ?? s
  const team = (m, side) => (byMatch.get(m.id) ?? []).filter(p => p.team === side)
  const dur = s => `${Math.floor((s ?? 0) / 60)}m`
  const cellWr = (a, b) => {
    const c = h2h.get(`${a}|${b}`)
    if (!c || !c.vsG) return null
    return { wr: c.vsW / c.vsG, ...c }
  }
  const cellColor = w => w === null ? 'transparent'
    : `rgba(${w.wr >= .5 ? '110,190,140' : '224,108,95'},${0.12 + Math.min(.5, w.vsG / 12) * (Math.abs(w.wr - .5) * 2 + .3)})`
</script>

<div class="wrap">
  <header class="top">
    <span class="kicker">◆ IN-HOUSE CUSTOMS</span>
    <div class="rule-fade"></div>
    <div class="pills">
      {#each [['leader','LEADERBOARD'],['history','HISTORY'],['rivals','RIVALS']] as [id, lbl]}
        <button class:active={view === id} on:click={() => { view = id; selPair = null }}>{lbl}</button>
      {/each}
      <button class:active={view === 'records'} on:click={loadRecords}>RECORDS</button>
    </div>
  </header>

  {#if ready && view === 'leader'}
    <section class="glass card">
      <div class="lrow head">
        <span></span><span>PLAYER</span><span>GP</span><span>W–L</span>
        <span>WIN %</span><span>KDA</span><span>AVG DMG</span><span>AVG GOLD</span><span>CS</span>
      </div>
      {#each lb as p, i (p.name)}
        <div class="lrow" in:fly={{ x: -26, duration: 400, delay: i * 45 }}>
          <span class="rk" class:medal={i < 3} data-m={i}>{i + 1}</span>
          <span class="nm click" role="button" tabindex="0"
                on:click={() => openScout(p.name)}
                on:keydown={e => e.key === 'Enter' && openScout(p.name)}>{p.name.toUpperCase()}</span>
          <span class="mono">{p.games}</span>
          <span class="mono">{p.wins}–{p.losses}</span>
          <span class="wrcell">
            <b class:up={p.wr >= 52} class:down={p.wr < 48}>{p.wr}%</b>
            <i><em style="width:{p.wr}%"></em></i>
          </span>
          <span class="mono kda">{p.kda}</span>
          <span class="mono">{p.avgDmg.toLocaleString()}</span>
          <span class="mono">{p.avgGold.toLocaleString()}</span>
          <span class="mono">{p.avgCs}</span>
        </div>
      {/each}
    </section>

  {:else if ready && view === 'history'}
    <div class="feedcol">
      {#each matches as m, i (m.id)}
        <section class="glass match click" role="button" tabindex="0"
                 on:click={() => openMatch = m.id}
                 on:keydown={e => e.key === 'Enter' && (openMatch = m.id)}
                 in:fly={{ y: 26, duration: 450, delay: Math.min(i, 8) * 70 }}>
          <div class="mhead">
            <span class="mono dim">{(m.started_at ?? '').slice(0, 10)} · {dur(m.duration)}</span>
            <span class="winner" class:blue={m.winner === 'blue'} class:red={m.winner === 'red'}>
              {(m.winner ?? '?').toUpperCase()} VICTORY</span>
          </div>
          {#each ['blue', 'red'] as side}
            <div class="trow" class:won={m.winner === side}>
              <span class="sidetag" class:blue={side === 'blue'} class:red={side === 'red'}>{side.toUpperCase()}</span>
              {#each team(m, side) as pt}
                <div class="pcell" title="{disp(pt.player)}">
                  <img src={iconUrl(pt.champion)} alt={pt.champion} loading="lazy" />
                  <div class="pmeta">
                    <b>{disp(pt.player)}</b>
                    <span class="mono">{pt.kills}/{pt.deaths}/{pt.assists}</span>
                  </div>
                </div>
              {/each}
            </div>
          {/each}
        </section>
      {/each}
    </div>

  {:else if ready && view === 'rivals'}
    <section class="glass card">
      <div class="matrix" style="--n:{roster.length}">
        <span></span>
        {#each roster as c}<span class="mlbl col">{c.slice(0, 5).toUpperCase()}</span>{/each}
        {#each roster as r}
          <span class="mlbl">{r.slice(0, 7).toUpperCase()}</span>
          {#each roster as c}
            {@const w = r === c ? null : cellWr(r, c)}
            <button class="cell" disabled={r === c}
                    style="background:{cellColor(w)}"
                    class:sel={selPair?.[0] === r && selPair?.[1] === c}
                    on:click={() => selPair = [r, c]}>
              {#if r === c}·{:else if w}{w.vsW}–{w.vsG - w.vsW}{/if}
            </button>
          {/each}
        {/each}
      </div>
      {#if selPair}
        {@const c = h2h.get(`${selPair[0]}|${selPair[1]}`) ?? {}}
        <div class="drill" in:fade={{ duration: 250 }}>
          <b class="gold-text">{selPair[0].toUpperCase()} vs {selPair[1].toUpperCase()}</b>
          <span>VS: <b>{c.vsW ?? 0}–{(c.vsG ?? 0) - (c.vsW ?? 0)}</b></span>
          <span>AS TEAMMATES: <b>{c.withW ?? 0}–{(c.withG ?? 0) - (c.withW ?? 0)}</b></span>
        </div>
      {:else}
        <div class="drill dim">Row beats column — click any cell to drill in.</div>
      {/if}
    </section>

  {:else if view === 'records'}
    {#if !records}
      <p class="dim mono load">loading the record book…</p>
    {:else}
      <div class="recgrid">
        {#each recordList as r, i (r.k)}
          <button class="rec glass" class:click={r.match_id}
                  on:click={() => r.match_id && (openMatch = r.match_id)}
                  in:fly={{ y: 20, duration: 380, delay: Math.min(i, 12) * 45 }}>
            <span class="rlabel kicker">{REC_LABELS[r.k] ?? r.k}</span>
            <b class="rval gold-text">{recValue(r.k, r)}</b>
            <span class="rwho">{(r.player ?? '').toUpperCase()}
              {#if r.champion}<i>· {r.champion}</i>{/if}</span>
            {#if r.started_at}<span class="rdate mono dim2">{r.started_at.slice(0, 10)}</span>{/if}
          </button>
        {/each}
      </div>

      {#if predLb?.length}
        <section class="glass predlb" in:fade={{ duration: 300 }}>
          <header><span class="kicker">◆ PREDICTION ACCURACY</span><div class="rule-fade"></div></header>
          {#each predLb as p, i (p.voter)}
            <div class="prow">
              <span class="mono dim2">{i + 1}</span>
              <b class="click" role="button" tabindex="0"
                 on:click={() => openScout(p.voter)}
                 on:keydown={e => e.key === 'Enter' && openScout(p.voter)}>{(p.voter ?? '').toUpperCase()}</b>
              <span class="mono">{p.correct ?? 0}/{p.total ?? 0}</span>
              <span class="acc"><em style="width:{((p.correct ?? 0) / Math.max(1, p.total ?? 1)) * 100}%"></em></span>
              <span class="mono gold-text">{Math.round(((p.correct ?? 0) / Math.max(1, p.total ?? 1)) * 100)}%</span>
            </div>
          {/each}
        </section>
      {/if}
    {/if}
  {/if}
</div>

{#if openMatch}
  <MatchDetail matchId={openMatch} {sumToDisplay} on:close={() => openMatch = null} />
{/if}

<style>
  .wrap { height: 100%; overflow-y: auto; padding: 26px; }
  .top { display: flex; align-items: center; gap: 16px; margin-bottom: 16px; }
  .pills { display: flex; gap: 6px; }
  .pills button {
    padding: 8px 18px; border-radius: 8px; cursor: pointer;
    background: rgba(255,255,255,.04); border: 1px solid rgba(200,170,110,.2);
    color: var(--txt-dim); font-family: var(--font-ui); font-weight: 700;
    font-size: 13px; letter-spacing: 2px; transition: all .25s;
  }
  .pills button.active {
    color: var(--gold-lt);
    background: linear-gradient(180deg, rgba(200,170,110,.25), rgba(120,90,40,.18));
    border-color: rgba(200,170,110,.55);
    box-shadow: 0 0 18px rgba(200,170,110,.25);
  }
  .card { padding: 18px 20px; }

  .lrow {
    display: grid;
    grid-template-columns: 34px 1.3fr 50px 70px 120px 60px 90px 90px 50px;
    align-items: center; gap: 10px;
    padding: 9px 10px; border-radius: 8px;
    transition: background .2s, transform .2s;
  }
  .lrow:not(.head):hover { background: rgba(200,170,110,.07); transform: translateX(4px); }
  .lrow.head { font-family: var(--font-mono); font-size: 10px; letter-spacing: 1.5px;
               color: var(--txt-faint); border-bottom: 1px solid rgba(200,170,110,.18);
               border-radius: 0; margin-bottom: 6px; }
  .rk { font-family: var(--font-mono); color: var(--txt-faint); }
  .rk.medal[data-m="0"] { color: #ffd700; text-shadow: 0 0 12px #ffd700aa; }
  .rk.medal[data-m="1"] { color: #e8e8e8; }
  .rk.medal[data-m="2"] { color: #cd7f32; }
  .nm { font-weight: 700; font-size: 16px; letter-spacing: 1px; }
  .nm.click { cursor: pointer; }
  .nm.click:hover { color: var(--gold-lt); text-shadow: 0 0 12px rgba(200,170,110,.4); }
  .card { overflow-x: auto; }
  @media (max-width: 1100px) { .lrow { min-width: 860px; } }
  .mono { font-family: var(--font-mono); font-size: 12px; color: var(--txt-dim); }
  .kda { color: #9eb4c8; }
  .wrcell b { display: block; font-size: 14px; }
  .wrcell i { display: block; height: 4px; border-radius: 2px;
              background: rgba(255,255,255,.06); margin-top: 3px; }
  .wrcell em { display: block; height: 100%; border-radius: 2px;
               background: linear-gradient(90deg, var(--gold-dk), var(--gold-hot));
               box-shadow: 0 0 8px rgba(200,170,110,.5); }
  .up { color: var(--win); } .down { color: var(--loss); }

  .feedcol { display: flex; flex-direction: column; gap: 14px; }
  .match { padding: 14px 18px; }
  .match.click { cursor: pointer; transition: transform .18s, box-shadow .18s; }
  .match.click:hover { transform: translateY(-2px);
    box-shadow: 0 10px 30px rgba(0,0,0,.4), 0 0 20px rgba(200,170,110,.12); }

  .load { padding: 40px; text-align: center; }
  .recgrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 14px; }
  .rec { display: flex; flex-direction: column; gap: 5px; padding: 16px 18px;
    text-align: left; border: 1px solid rgba(200,170,110,.18);
    background: rgba(255,255,255,.02); color: var(--txt); font-family: var(--font-ui); }
  .rec.click { cursor: pointer; transition: all .2s; }
  .rec.click:hover { transform: translateY(-3px); border-color: var(--gold-hot);
    box-shadow: 0 12px 30px rgba(0,0,0,.4), 0 0 22px rgba(200,170,110,.2); }
  .rlabel { font-size: 10px; }
  .rval { font-size: 28px; font-family: var(--font-display); letter-spacing: 1px; }
  .rwho { font-size: 13px; font-weight: 700; letter-spacing: 1px; }
  .rwho i { font-style: normal; color: var(--txt-faint); font-weight: 400; font-size: 11px; }
  .rdate { font-size: 10px; }
  .dim2 { color: var(--txt-faint); }

  .predlb { margin-top: 18px; padding: 16px 20px; }
  .predlb header { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
  .prow { display: grid; grid-template-columns: 28px 1.4fr 64px 1fr 56px;
    align-items: center; gap: 12px; padding: 6px 8px; border-radius: 8px; }
  .prow:hover { background: rgba(200,170,110,.06); }
  .prow b { font-size: 14px; letter-spacing: 1px; }
  .prow .click { cursor: pointer; }
  .prow .click:hover { color: var(--gold-lt); }
  .acc { display: block; height: 5px; border-radius: 3px;
    background: rgba(255,255,255,.06); overflow: hidden; }
  .acc em { display: block; height: 100%; border-radius: 3px;
    background: linear-gradient(90deg, var(--gold-dk), var(--gold-hot));
    box-shadow: 0 0 8px rgba(200,170,110,.5); }
  .mhead { display: flex; justify-content: space-between; margin-bottom: 10px; }
  .dim { color: var(--txt-faint); font-size: 11px; }
  .winner { font-family: var(--font-mono); font-size: 11px; letter-spacing: 2px; }
  .winner.blue { color: var(--blue-side); text-shadow: 0 0 10px rgba(89,179,212,.5); }
  .winner.red  { color: var(--loss); text-shadow: 0 0 10px rgba(224,108,95,.5); }
  .trow { display: flex; align-items: center; gap: 10px; padding: 7px 8px;
          border-radius: 8px; opacity: .68; }
  .trow.won { opacity: 1; background: rgba(255,255,255,.03); }
  .sidetag { font-family: var(--font-mono); font-size: 10px; width: 38px; flex-shrink: 0; }
  .sidetag.blue { color: var(--blue-side); } .sidetag.red { color: var(--loss); }
  .pcell { display: flex; align-items: center; gap: 7px; flex: 1; min-width: 0; }
  .pcell img { width: 30px; height: 30px; border-radius: 7px;
               border: 1px solid rgba(200,170,110,.3); }
  .pmeta { display: flex; flex-direction: column; min-width: 0; }
  .pmeta b { font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .pmeta span { font-size: 10px; color: var(--txt-faint); }

  .matrix {
    display: grid;
    grid-template-columns: 76px repeat(var(--n), 1fr);
    gap: 3px; overflow-x: auto;
  }
  .mlbl { font-family: var(--font-mono); font-size: 9px; color: var(--txt-faint);
          align-self: center; letter-spacing: .5px; }
  .mlbl.col { text-align: center; }
  .cell {
    aspect-ratio: 1.6; border: 1px solid rgba(255,255,255,.05); border-radius: 4px;
    color: var(--txt-dim); font-family: var(--font-mono); font-size: 10px;
    cursor: pointer; transition: all .15s;
  }
  .cell:hover:not(:disabled) { border-color: var(--gold); transform: scale(1.12); color: var(--txt); }
  .cell.sel { border-color: var(--gold-hot); box-shadow: 0 0 12px rgba(200,170,110,.5); }
  .cell:disabled { cursor: default; }
  .drill { display: flex; gap: 28px; align-items: baseline; margin-top: 14px;
           padding: 12px 14px; border-top: 1px solid rgba(200,170,110,.18);
           font-family: var(--font-mono); font-size: 12px; color: var(--txt-dim); }
  .drill b { font-size: 15px; }
</style>
