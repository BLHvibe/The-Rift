<script>
  import { onMount } from 'svelte'
  import { fly } from 'svelte/transition'
  import { leagueData } from '../../api.js'
  import { loadCoreData, scoreBy, playerRow } from '../../draft/engine.js'
  import { ROLES } from '../../draft/seq.js'
  import { draft, setSide, setPlayers, setReady, exitDraft } from '../../draft/store.js'

  let roster = []
  let ready = false

  onMount(async () => {
    try {
      const [d] = await Promise.all([leagueData(), loadCoreData()])
      roster = d.leaderboard.map(p => p.name)
    } catch (e) { console.error(e) }
    ready = true
  })

  $: you = $draft.you
  $: sides = $draft.sides
  $: solo = $draft.mode === 'solo'
  $: canEdit = side => solo || you.is_host || you.side === side
  $: blue = ($draft.state.players.BLUE ?? []).map(p => p?.name).filter(Boolean)
  $: red  = ($draft.state.players.RED ?? []).map(p => p?.name).filter(Boolean)
  $: assigned = new Set([...blue, ...red])
  $: pool = roster.filter(n => !assigned.has(n))
  $: meReady = you.side in $draft.ready ? $draft.ready[you.side] : false

  // Balance meter (kept from v6.2 — elo-logistic on ladder scores).
  $: avgB = blue.length ? blue.reduce((a, n) => a + (scoreBy[n] ?? 50), 0) / blue.length : 0
  $: avgR = red.length ? red.reduce((a, n) => a + (scoreBy[n] ?? 50), 0) / red.length : 0
  $: pBlue = (blue.length && red.length)
    ? 1 / (1 + Math.pow(10, -(avgB - avgR) / 12)) : 0.5

  function assign(name, side) {
    if (!canEdit(side)) return
    const cur = side === 'BLUE' ? blue : red
    if (cur.length >= 5) return
    setPlayers(side, [...cur, name].map(playerRow))
  }
  function unassign(name, side) {
    if (!canEdit(side)) return
    const cur = side === 'BLUE' ? blue : red
    setPlayers(side, cur.filter(n => n !== name).map(playerRow))
  }
  // Pool click → fills the emptier editable side.
  function quickAssign(name) {
    const order = blue.length <= red.length ? ['BLUE', 'RED'] : ['RED', 'BLUE']
    for (const s of order) {
      const cur = s === 'BLUE' ? blue : red
      if (canEdit(s) && cur.length < 5) { assign(name, s); return }
    }
  }
  const sideLabel = s => s === 'SPEC' ? 'SPECTATOR' : `${s} CAPTAIN`
</script>

<div class="wrap">
  <header class="top">
    <span class="kicker">◆ WAR ROOM — LOBBY</span><div class="rule-fade"></div>
    <button class="exitb" on:click={exitDraft}>EXIT</button>
  </header>

  {#if !solo}
    <div class="youbar glass" in:fly={{ y: -12, duration: 350 }}>
      <span class="ylbl">YOU</span>
      <b class="yname">{you.name.toUpperCase()}</b>
      <span class="yside" class:blue={you.side === 'BLUE'} class:red={you.side === 'RED'}>
        {sideLabel(you.side)}</span>
      {#if you.is_host}<span class="hostchip">HOST</span>{/if}
      <div class="spacer"></div>
      {#each ['BLUE', 'RED', 'SPEC'] as s}
        <button class="swap" class:cur={you.side === s}
                on:click={() => setSide(s)}>{s}</button>
      {/each}
    </div>

    <div class="conn glass">
      <span class="kicker dim">CONNECTED</span>
      <span class="cl blue">BLUE · {sides.BLUE ?? '— open —'}
        {#if $draft.ready.BLUE}<i>✓ ready</i>{/if}</span>
      <span class="cl red">RED · {sides.RED ?? '— open —'}
        {#if $draft.ready.RED}<i>✓ ready</i>{/if}</span>
      {#if $draft.spectators.length}
        <span class="cl spec">WATCHING · {$draft.spectators.join(', ')}</span>
      {/if}
    </div>
  {/if}

  <div class="builder">
    {#each [['BLUE', blue, '#59b3d4'], ['RED', red, 'var(--loss)']] as [side, team, col]}
      <div class="teamcol glass" style="--side:{col}">
        <h3>{side} SIDE {#if !canEdit(side)}<i class="lock">view only</i>{/if}</h3>
        {#each ROLES as role, i}
          <div class="slot" class:filled={team[i]}>
            <span class="role">{role}</span>
            {#if team[i]}
              <button class="pname" disabled={!canEdit(side)}
                      title={canEdit(side) ? 'click to remove' : ''}
                      on:click={() => unassign(team[i], side)}>
                {team[i].toUpperCase()}
                <i>{Math.round(scoreBy[team[i]] ?? 50)}</i>
              </button>
            {:else}
              <span class="empty">— open —</span>
            {/if}
          </div>
        {/each}
      </div>
    {/each}
  </div>

  <div class="meter glass">
    <span class="kicker">BALANCE</span>
    <div class="probs">
      <b style="color:#59b3d4">{Math.round(pBlue * 100)}</b><span>vs</span>
      <b style="color:var(--loss)">{Math.round((1 - pBlue) * 100)}</b>
    </div>
    <div class="pbar"><em style="width:{pBlue * 100}%"></em></div>
  </div>

  <div class="pool glass">
    <span class="kicker dim">ROSTER — click to assign · slots fill TOP→SUP</span>
    <div class="zone">
      {#each pool as n (n)}
        <button class="chip" on:click={() => quickAssign(n)}>{n.toUpperCase()}</button>
      {/each}
      {#if ready && !pool.length}<span class="dim mono">everyone is placed</span>{/if}
    </div>
  </div>

  <div class="readyrow">
    {#if you.side === 'SPEC' && !solo}
      <span class="dim mono">spectating — the captains ready up</span>
    {:else}
      <button class="readyb" class:armed={meReady}
              disabled={blue.length < 5 || red.length < 5}
              on:click={() => setReady(!meReady)}>
        {meReady ? '✓ READY — waiting on the other side' : 'READY'}
      </button>
      {#if blue.length < 5 || red.length < 5}
        <span class="dim mono">both teams need five before ready</span>
      {/if}
    {/if}
  </div>

  {#if $draft.connError}<div class="err mono">{$draft.connError}</div>{/if}
</div>

<style>
  .wrap { height: 100%; overflow-y: auto; padding: 26px; }
  .top { display: flex; align-items: center; gap: 14px; margin-bottom: 14px; }
  .exitb { padding: 7px 16px; border-radius: 8px; cursor: pointer;
    background: rgba(255,255,255,.04); border: 1px solid rgba(224,108,95,.4);
    color: var(--txt-dim); font-family: var(--font-ui); font-weight: 700;
    letter-spacing: 2px; font-size: 12px; }
  .exitb:hover { color: var(--loss); border-color: var(--loss); }

  .youbar { display: flex; align-items: center; gap: 12px;
            padding: 10px 16px; margin-bottom: 10px; }
  .ylbl { font-family: var(--font-mono); font-size: 10px; color: var(--txt-faint);
          letter-spacing: 2px; }
  .yname { letter-spacing: 2px; }
  .yside { font-family: var(--font-mono); font-size: 11px; letter-spacing: 2px;
           color: var(--txt-dim); }
  .yside.blue { color: #59b3d4; } .yside.red { color: var(--loss); }
  .hostchip { font-family: var(--font-mono); font-size: 9px; padding: 2px 8px;
    border: 1px solid rgba(200,170,110,.5); border-radius: 99px;
    color: var(--gold-lt); letter-spacing: 2px; }
  .spacer { flex: 1; }
  .swap { padding: 5px 12px; border-radius: 7px; cursor: pointer;
    background: rgba(255,255,255,.03); border: 1px solid rgba(200,170,110,.2);
    color: var(--txt-faint); font-family: var(--font-mono); font-size: 10px;
    letter-spacing: 1.5px; }
  .swap.cur { color: var(--gold-lt); border-color: var(--gold);
              box-shadow: 0 0 12px rgba(200,170,110,.25); }

  .conn { display: flex; gap: 22px; align-items: baseline;
          padding: 9px 16px; margin-bottom: 14px; flex-wrap: wrap; }
  .cl { font-family: var(--font-mono); font-size: 11px; color: var(--txt-dim); }
  .cl.blue { color: #59b3d4; } .cl.red { color: var(--loss); }
  .cl.spec { color: var(--txt-faint); }
  .cl i { font-style: normal; color: var(--win); margin-left: 6px; }

  .builder { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
  .teamcol { padding: 14px; border-top: 3px solid var(--side); }
  .teamcol h3 { font-family: var(--font-mono); font-size: 11px; letter-spacing: 3px;
                color: var(--side); margin-bottom: 10px;
                text-shadow: 0 0 12px var(--side);
                display: flex; justify-content: space-between; }
  .lock { font-style: normal; font-size: 9px; color: var(--txt-faint);
          letter-spacing: 1px; }
  .slot { display: flex; align-items: center; gap: 12px; padding: 7px 10px;
          border-radius: 8px; margin-bottom: 5px;
          background: rgba(255,255,255,.025);
          border: 1px dashed rgba(255,255,255,.08); }
  .slot.filled { border-style: solid; border-color: rgba(200,170,110,.25); }
  .role { font-family: var(--font-mono); font-size: 10px; width: 34px;
          color: var(--txt-faint); letter-spacing: 1px; }
  .pname { background: none; border: none; cursor: pointer; color: var(--txt);
           font-family: var(--font-ui); font-weight: 700; font-size: 14px;
           letter-spacing: 1px; display: flex; gap: 10px; align-items: baseline;
           padding: 0; }
  .pname:hover:not(:disabled) { color: var(--loss); }
  .pname:disabled { cursor: default; }
  .pname i { font-style: normal; font-family: var(--font-mono); font-size: 10px;
             color: var(--txt-faint); }
  .empty { color: var(--txt-faint); font-size: 12px; font-family: var(--font-mono); }

  .meter { margin-top: 14px; padding: 12px 16px; display: flex;
           align-items: center; gap: 18px; }
  .probs { display: flex; align-items: baseline; gap: 8px; }
  .probs b { font-size: 24px; font-weight: 700; text-shadow: 0 0 16px currentColor; }
  .probs span { color: var(--txt-faint); font-size: 11px; }
  .pbar { flex: 1; height: 7px; border-radius: 4px;
          background: rgba(224,108,95,.5); overflow: hidden; }
  .pbar em { display: block; height: 100%;
             background: linear-gradient(90deg, #2c7da0, #59b3d4);
             box-shadow: 0 0 12px rgba(89,179,212,.7);
             transition: width .7s cubic-bezier(.2,.8,.2,1); }

  .pool { margin-top: 14px; padding: 12px 16px; }
  .zone { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; min-height: 38px; }
  .chip { padding: 7px 14px; border-radius: 9px; cursor: pointer;
          background: linear-gradient(180deg, rgba(22,48,79,.9), rgba(13,28,50,.9));
          border: 1px solid rgba(200,170,110,.35); color: var(--txt);
          font-family: var(--font-ui); font-weight: 700; font-size: 13px;
          letter-spacing: 1px; transition: all .18s; }
  .chip:hover { border-color: var(--gold-hot); transform: translateY(-2px);
                box-shadow: 0 0 14px rgba(200,170,110,.3); }

  .readyrow { margin-top: 18px; display: flex; align-items: center; gap: 16px; }
  .readyb { padding: 13px 30px; border-radius: 10px; cursor: pointer;
    background: linear-gradient(180deg, rgba(200,170,110,.3), rgba(120,90,40,.2));
    border: 1px solid rgba(200,170,110,.6); color: var(--gold-lt);
    font-family: var(--font-ui); font-weight: 700; letter-spacing: 2.5px;
    font-size: 14px; transition: all .25s; }
  .readyb:hover:not(:disabled) { border-color: var(--gold-hot);
    box-shadow: 0 0 24px rgba(200,170,110,.4); }
  .readyb:disabled { opacity: .45; cursor: default; }
  .readyb.armed { color: var(--win); border-color: rgba(110,190,140,.6); }
  .dim { color: var(--txt-faint); font-size: 11px; }
  .mono { font-family: var(--font-mono); }
  .err { margin-top: 10px; color: var(--loss); font-size: 12px; }

  @media (max-width: 1100px) { .builder { grid-template-columns: 1fr; } }
</style>
