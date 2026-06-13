<script>
  import { onMount } from 'svelte'
  import { fly, fade } from 'svelte/transition'
  import { iconUrl, splashUrl } from '../../api.js'
  import ARCH from '../../archetypes.json'
  import { loadCoreData, scoreBy, recommendAction, targetArchetype,
           pivotCheck, predictEnemyNext } from '../../draft/engine.js'
  import { draft, engineState, applyAction, undo, resetDraft, exitDraft,
           setArchetype, currentAction, usedChamps, openRoles, other,
           SEQ } from '../../draft/store.js'
  import { ROLES, timeline } from '../../draft/seq.js'

  const TAG_COL = {
    'COMFORT': 'var(--gold)', 'COUNTER': '#8c64dc', 'FLEX': '#59b3d4',
    'BLIND-SAFE': 'var(--win)', 'SYNERGY': '#d48cb4', 'POWER': 'var(--gold-hot)',
    'BAN-P1': 'var(--loss)', 'BAN-P2': '#e0935f',
  }

  let allChamps = []
  let search = ''
  let pendingChamp = null      // manual pick awaiting role choice
  let rec = null               // recommend_action result
  let enemyComp = null         // enemy side's projected comp (tactical readout)
  let pivot = null             // archetype_pivot_check result
  let ghost = null             // predict_enemy_next result
  let thinking = false
  let prevArch = null          // hysteresis for target_archetype
  let reqId = 0

  $: d = $draft
  $: st = d.state
  $: act = currentAction(st)
  $: solo = d.mode === 'solo'
  $: ourSide = st.our_side
  $: enemySide = other(ourSide)
  $: youSide = solo ? (act?.side ?? ourSide) : d.you.side
  $: isHost = solo || d.you.is_host
  $: canAct = act && (solo || d.you.side === act.side)
  $: showIntel = act && (solo || (d.you.side === act.side))
  $: spectator = !solo && d.you.side === 'SPEC'
  $: taken = usedChamps(st)
  $: cells = timeline(st)
  $: myArch = st.archetype_self
  $: filtered = search
    ? allChamps.filter(c => c.toLowerCase().includes(search.toLowerCase())).slice(0, 24)
    : []
  $: heroSplash = rec?.suggestions?.[0]?.champion ?? null

  onMount(async () => {
    try {
      await loadCoreData()
      const ver = (await (await fetch('https://ddragon.leagueoflegends.com/api/versions.json')).json())[0]
      const cj = await (await fetch(`https://ddragon.leagueoflegends.com/cdn/${ver}/data/en_US/champion.json`)).json()
      allChamps = Object.values(cj.data).map(c => c.name).sort()
    } catch (e) { console.error(e) }
  })

  // ── Engine loop — recompute on pointer / archetype movement ───────────
  $: recompute(st.pointer, myArch, d.mode)

  async function recompute() {
    const id = ++reqId
    const state = engineState(d)
    const a = currentAction(st)
    if (!a) { rec = null; return }
    thinking = true
    try {
      const actorIsUs = a.side === ourSide
      const r = await recommendAction(state, {
        forcedArch: actorIsUs ? (myArch || null) : null,
        prevArch,
        enemySide,
      })
      if (id !== reqId) return
      rec = r
      prevArch = r?.target_comp?.archetype ?? prevArch
      // Secondary intel — fire-and-forget, each guards against stale ids.
      targetArchetype(state, enemySide).then(c => {
        if (id === reqId) enemyComp = c
      }).catch(() => {})
      predictEnemyNext(state, ourSide).then(g => {
        if (id === reqId) ghost = g
      }).catch(() => { if (id === reqId) ghost = null })
      if (myArch) {
        pivotCheck(state, ourSide, myArch).then(p => {
          if (id === reqId) pivot = p?.wrecked ? p : null
        }).catch(() => {})
      } else pivot = null
    } catch (e) {
      if (id === reqId) rec = null
      console.error(e)
    }
    if (id === reqId) thinking = false
  }

  // ── Apply paths ────────────────────────────────────────────────────────
  function applySuggestion(s) {
    if (!canAct) return
    applyAction(s.champion, s.role ?? null)
    search = ''; pendingChamp = null
  }
  function applyManual(champ) {
    if (!canAct || taken.has(champ)) return
    if (act.kind === 'ban') { applyAction(champ); search = ''; return }
    const open = openRoles(st, act.side)
    if (open.length === 1) { applyAction(champ, open[0]); search = '' }
    else pendingChamp = champ
  }
  function applyWithRole(role) {
    if (!pendingChamp) return
    applyAction(pendingChamp, role)
    pendingChamp = null; search = ''
  }
  function pivotTo(arch) {
    setArchetype(arch)
    pivot = null
  }

  const sideCol = s => s === 'BLUE' ? '#59b3d4' : 'var(--loss)'
  const playerAt = (side, role) => {
    const i = ROLES.indexOf(role)
    return st.players[side]?.[i]?.name ?? ''
  }
</script>

<div class="wrap">
  {#if heroSplash && showIntel}
    <div class="bghero" style="background-image:url({splashUrl(heroSplash)})" transition:fade></div>
  {/if}

  <header class="top">
    <span class="kicker">◆ WAR ROOM — DRAFT BOARD</span><div class="rule-fade"></div>
    {#if myArch}
      <span class="archchip mono">⬡ {ARCH[myArch]?.label?.toUpperCase() ?? myArch}</span>
    {/if}
    {#if isHost}
      <button class="hbtn" disabled={st.pointer === 0} on:click={undo}>UNDO</button>
      <button class="hbtn" on:click={resetDraft}>RESET</button>
    {/if}
    <button class="hbtn exit" on:click={exitDraft}>EXIT</button>
  </header>

  <!-- ── Timeline ──────────────────────────────────────────────────── -->
  <div class="seq">
    {#each cells as c (c.idx)}
      <div class="step" class:blue={c.side === 'BLUE'} class:red={c.side === 'RED'}
           class:ban={c.kind === 'ban'} class:cur={c.idx === st.pointer}
           title="{c.label}{c.champ ? ` — ${c.champ}` : ''}">
        {#if c.champ}
          <img src={iconUrl(c.champ)} alt={c.champ} />
          {#if c.kind === 'ban'}<s></s>{/if}
        {:else}
          <span>{c.kind === 'ban' ? 'BAN' : c.label}</span>
        {/if}
      </div>
    {/each}
  </div>

  {#if pivot}
    <div class="pivotbar" transition:fly={{ y: -16, duration: 350 }}>
      <b>⚠ PIVOT ALERT</b>
      <span>{pivot.reason}</span>
      {#each (pivot.pivot_options ?? []).slice(0, 2) as opt}
        <button class="pivopt" on:click={() => pivotTo(opt)}>
          → {ARCH[opt]?.label ?? opt}</button>
      {/each}
      <button class="pivopt stay" on:click={() => pivot = null}>STAY</button>
    </div>
  {/if}

  <div class="boardgrid">
    <!-- ── Team panels ─────────────────────────────────────────────── -->
    {#each ['BLUE', 'RED'] as side, panelIdx (side)}
      <section class="team glass" class:second={panelIdx === 1}
               style="--side:{sideCol(side)}">
        <header>
          <h3>{side} SIDE</h3>
          <span class="cap mono">{d.sides[side] ?? ''}</span>
        </header>
        {#each ROLES as role}
          {@const champ = st.picks[side]?.[role]}
          <div class="rslot" class:locked={champ}>
            <span class="role">{role}</span>
            {#if champ}
              <img src={iconUrl(champ)} alt={champ} />
              <div class="rmeta"><b>{champ}</b>
                <span>{playerAt(side, role)}</span></div>
            {:else}
              <div class="rmeta open">
                <b class="dim2">—</b>
                <span>{playerAt(side, role)}
                  {#if playerAt(side, role)}· {Math.round(scoreBy[playerAt(side, role)] ?? 50)}{/if}</span>
              </div>
            {/if}
          </div>
        {/each}
        <div class="bansline">
          {#each st.bans[side] ?? [] as b}
            <span class="bicon" title={b}><img src={iconUrl(b)} alt={b} /><s></s></span>
          {/each}
        </div>
        {#if side === enemySide && ghost?.champion && showIntel}
          <div class="ghost" transition:fade>
            <span class="kicker dim">LIKELY NEXT</span>
            <img src={iconUrl(ghost.champion)} alt={ghost.champion} />
            <div class="gmeta"><b>{ghost.champion}</b>
              <span>{ghost.player ?? ''} {ghost.role ? `· ${ghost.role}` : ''}
                · {Math.round((ghost.confidence ?? 0) * 100)}%</span></div>
          </div>
        {/if}
      </section>
    {/each}

    <!-- ── Center intel ────────────────────────────────────────────── -->
    <section class="center glass">
      {#if act}
        <div class="banner" class:ours={canAct}
             style="--bcol:{canAct ? 'var(--gold)' : sideCol(act.side)}">
          <b>{canAct ? 'YOUR' : solo ? '' : (spectator ? `${act.side}` : 'OPPONENT')} {act.kind.toUpperCase()}</b>
          <span class="mono">{act.label} · phase {act.phase} · step {act.idx + 1}/20</span>
        </div>

        {#if showIntel}
          <!-- tactical readout -->
          {#if rec?.target_comp?.label || enemyComp?.label}
            <div class="tact">
              <span class="kicker dim">TACTICAL READOUT</span>
              <div class="tline">
                {#if rec?.target_comp?.label}
                  <span class="treadout"><i class="tg" style="background:{sideCol(act.side)}"></i>
                    <b>[ OUR ]</b> {rec.target_comp.label}
                    {#if rec.target_comp.spike}· {rec.target_comp.spike}{/if}</span>
                {/if}
                {#if enemyComp?.label}
                  <span class="treadout"><i class="tg" style="background:{sideCol(enemySide)}"></i>
                    <b class="en">[ ENEMY ]</b> {enemyComp.label}</span>
                {/if}
              </div>
            </div>
          {/if}

          <!-- context lines -->
          <div class="ctx">
            {#each (rec?.notes ?? []).slice(0, 2) as n}<p class="note">› {n}</p>{/each}
            {#each (rec?.cohesion ?? []).slice(0, 2) as c}<p class="coh">! {c}</p>{/each}
            {#each (rec?.exploit ?? []).slice(0, 2) as x}<p class="exp">+ {x}</p>{/each}
          </div>

          <!-- TOP CALL -->
          {#if rec?.suggestions?.length}
            {@const s0 = rec.suggestions[0]}
            {#key s0.champion}
            <button class="topcall" style="--tag:{TAG_COL[s0.tag] ?? 'var(--gold)'}"
                    in:fly={{ y: 18, duration: 320 }}
                    disabled={!canAct} on:click={() => applySuggestion(s0)}>
              <div class="tcsplash" style="background-image:url({splashUrl(s0.champion)})"></div>
              <div class="tcscrim"></div>
              <div class="tcbody">
                <span class="kicker">TOP CALL {thinking ? '· …' : ''}</span>
                <h2>{s0.champion.toUpperCase()}</h2>
                <div class="tcrow">
                  <span class="tag mono">{s0.tag ?? ''}</span>
                  {#if s0.role}<span class="mono dim">{s0.role}
                    {#if s0.player}· {s0.player}{/if}</span>{/if}
                  <span class="score mono">{Math.round((s0.score ?? 0) * 100)}</span>
                </div>
                {#if s0.why}<p class="why">{s0.why}</p>{/if}
              </div>
            </button>
            {/key}

            <!-- alternatives -->
            <div class="alts">
              {#each rec.suggestions.slice(1, 5) as s}
                <button class="alt" style="--tag:{TAG_COL[s.tag] ?? 'var(--gold)'}"
                        disabled={!canAct} on:click={() => applySuggestion(s)}
                        title={s.why ?? ''}>
                  <img src={iconUrl(s.champion)} alt={s.champion} />
                  <b>{s.champion}</b>
                  <span class="mono">{s.tag ?? ''}</span>
                </button>
              {/each}
            </div>
          {:else if thinking}
            <div class="warming mono dim">engine thinking…</div>
          {:else}
            <div class="warming">
              <b>NO STRONG CALL</b>
              <span class="dim">pick from the pool below — comfort first, counters late</span>
            </div>
          {/if}
        {:else}
          <div class="opclock">
            <b>{spectator ? 'CAPTAINS ON THE CLOCK' : 'OPPONENT ON THE CLOCK'}</b>
            <span class="dim">intel hidden — see LIKELY NEXT on the enemy panel
              once it's your move</span>
            <div class="pulse"></div>
          </div>
        {/if}

        <!-- manual pool -->
        {#if canAct}
          <div class="manual">
            <input class="seek" placeholder="search champion…" bind:value={search} />
            {#if pendingChamp}
              <div class="rolepick" transition:fade={{ duration: 150 }}>
                <span class="mono">assign {pendingChamp} to:</span>
                {#each openRoles(st, act.side) as r}
                  <button class="rp" on:click={() => applyWithRole(r)}>{r}</button>
                {/each}
                <button class="rp x" on:click={() => pendingChamp = null}>✕</button>
              </div>
            {/if}
            {#if filtered.length}
              <div class="grid8" transition:fade={{ duration: 150 }}>
                {#each filtered as c}
                  <button class="gcell" disabled={taken.has(c)} on:click={() => applyManual(c)}>
                    <img src={iconUrl(c)} alt={c} /><span>{c}</span>
                  </button>
                {/each}
              </div>
            {/if}
          </div>
        {/if}
      {/if}
    </section>
  </div>
</div>

<style>
  .wrap { position: relative; height: 100%; overflow-y: auto; padding: 22px 26px; }
  .bghero { position: fixed; inset: 0; background-size: cover;
            background-position: center 20%; opacity: .1; pointer-events: none;
            z-index: -1; mask-image: linear-gradient(180deg, black, transparent 80%); }
  .top { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
  .archchip { font-size: 10px; letter-spacing: 2px; color: var(--gold-lt);
    padding: 4px 12px; border: 1px solid rgba(200,170,110,.4); border-radius: 99px; }
  .hbtn { padding: 6px 14px; border-radius: 8px; cursor: pointer;
    background: rgba(255,255,255,.04); border: 1px solid rgba(200,170,110,.3);
    color: var(--txt-dim); font-family: var(--font-ui); font-weight: 700;
    letter-spacing: 2px; font-size: 11px; }
  .hbtn:hover:not(:disabled) { color: var(--gold-lt); border-color: var(--gold); }
  .hbtn:disabled { opacity: .4; cursor: default; }
  .hbtn.exit { border-color: rgba(224,108,95,.4); }
  .hbtn.exit:hover { color: var(--loss); border-color: var(--loss); }

  .seq { display: grid; grid-template-columns: repeat(20, 1fr); gap: 5px;
         margin-bottom: 12px; }
  .step { aspect-ratio: 1; position: relative; border-radius: 8px;
          display: grid; place-items: center; overflow: hidden;
          background: rgba(6,13,26,.6); border: 1px solid rgba(255,255,255,.1);
          color: var(--txt-faint); font-family: var(--font-mono); font-size: 8px; }
  .step.blue { border-color: rgba(89,179,212,.45); }
  .step.red  { border-color: rgba(224,108,95,.45); }
  .step.ban  { border-style: dashed; }
  .step.cur  { border-color: var(--gold-hot); border-width: 2px;
               animation: curpulse 1.6s ease-in-out infinite; }
  @keyframes curpulse {
    0%, 100% { box-shadow: 0 0 10px rgba(200,170,110,.35); }
    50% { box-shadow: 0 0 26px rgba(200,170,110,.7); } }
  .step img { width: 100%; height: 100%; object-fit: cover; }
  .step.ban img { filter: grayscale(.8) brightness(.7); }
  .step s { position: absolute; width: 80%; height: 2px; background: var(--loss);
            transform: rotate(-40deg); box-shadow: 0 0 8px var(--loss); }

  .pivotbar { display: flex; align-items: center; gap: 14px; flex-wrap: wrap;
    padding: 10px 16px; margin-bottom: 12px; border-radius: 10px;
    background: linear-gradient(90deg, rgba(224,108,95,.22), rgba(224,108,95,.08));
    border: 1px solid rgba(224,108,95,.55);
    animation: pivpulse 2.2s ease-in-out infinite; }
  @keyframes pivpulse {
    0%, 100% { box-shadow: 0 0 12px rgba(224,108,95,.25); }
    50% { box-shadow: 0 0 26px rgba(224,108,95,.5); } }
  .pivotbar b { color: var(--loss); letter-spacing: 2px; font-size: 13px; }
  .pivotbar span { color: var(--txt-dim); font-size: 12px; }
  .pivopt { padding: 5px 14px; border-radius: 8px; cursor: pointer;
    background: rgba(255,255,255,.05); border: 1px solid rgba(224,108,95,.5);
    color: var(--txt); font-family: var(--font-ui); font-weight: 700;
    font-size: 11px; letter-spacing: 1px; }
  .pivopt:hover { border-color: var(--loss); box-shadow: 0 0 12px rgba(224,108,95,.4); }
  .pivopt.stay { border-color: rgba(200,170,110,.4); color: var(--txt-dim); }

  .boardgrid { display: grid; grid-template-columns: 250px 1fr 250px; gap: 14px;
               grid-template-areas: 'blue center red'; }
  .team { padding: 14px; border-top: 3px solid var(--side); }
  .team:not(.second) { grid-area: blue; }
  .team.second { grid-area: red; }
  .center { grid-area: center; padding: 14px 18px; min-height: 540px;
            display: flex; flex-direction: column; gap: 12px; }
  .team header { display: flex; justify-content: space-between;
                 align-items: baseline; margin-bottom: 10px; }
  .team h3 { font-family: var(--font-mono); font-size: 11px; letter-spacing: 3px;
             color: var(--side); text-shadow: 0 0 12px var(--side); }
  .cap { font-size: 9px; color: var(--txt-faint); letter-spacing: 1px; }
  .rslot { display: flex; align-items: center; gap: 10px; padding: 6px 8px;
           border-radius: 8px; margin-bottom: 5px;
           background: rgba(255,255,255,.02);
           border: 1px dashed rgba(255,255,255,.07); }
  .rslot.locked { border-style: solid; border-color: rgba(200,170,110,.3);
                  background: rgba(200,170,110,.05); }
  .rslot .role { font-family: var(--font-mono); font-size: 9px; width: 28px;
                 color: var(--txt-faint); }
  .rslot img { width: 38px; height: 38px; border-radius: 8px;
               border: 1px solid rgba(200,170,110,.4); }
  .rmeta { display: flex; flex-direction: column; min-width: 0; }
  .rmeta b { font-size: 13px; white-space: nowrap; overflow: hidden;
             text-overflow: ellipsis; }
  .rmeta span { font-size: 9px; color: var(--txt-faint);
                font-family: var(--font-mono); }
  .dim2 { color: var(--txt-faint); }
  .bansline { display: flex; gap: 6px; margin-top: 10px; min-height: 32px;
              border-top: 1px solid rgba(255,255,255,.06); padding-top: 10px; }
  .bicon { position: relative; }
  .bicon img { width: 28px; height: 28px; border-radius: 6px;
               filter: grayscale(.7) brightness(.75);
               border: 1px solid rgba(224,108,95,.4); }
  .bicon s { position: absolute; top: 13px; left: 1px; width: 26px; height: 2px;
             background: var(--loss); transform: rotate(-40deg); }
  .ghost { display: flex; align-items: center; gap: 10px; margin-top: 12px;
           padding: 8px 10px; border-radius: 9px;
           border: 1px dashed rgba(140,100,220,.5);
           background: rgba(140,100,220,.08); }
  .ghost img { width: 34px; height: 34px; border-radius: 8px; opacity: .85;
               border: 1px solid rgba(140,100,220,.5); }
  .gmeta { display: flex; flex-direction: column; }
  .gmeta b { font-size: 12px; }
  .gmeta span { font-size: 9px; color: var(--txt-faint);
                font-family: var(--font-mono); }

  .banner { display: flex; justify-content: space-between; align-items: baseline;
            padding: 12px 16px; border-radius: 9px;
            border: 2px solid var(--bcol);
            background: color-mix(in srgb, var(--bcol) 14%, transparent); }
  .banner.ours { animation: ourspulse 1.8s ease-in-out infinite; }
  @keyframes ourspulse {
    0%, 100% { box-shadow: 0 0 10px rgba(200,170,110,.3); }
    50% { box-shadow: 0 0 24px rgba(200,170,110,.6); } }
  .banner b { font-size: 17px; letter-spacing: 2.5px; color: var(--bcol);
              filter: brightness(1.3); }
  .banner span { font-size: 10px; color: var(--txt-dim); }

  .tact { padding: 8px 12px; border-radius: 8px;
          background: rgba(6,13,26,.55); border: 1px solid rgba(200,170,110,.2); }
  .tline { display: flex; gap: 22px; flex-wrap: wrap; margin-top: 5px; }
  .treadout { display: flex; align-items: center; gap: 8px; font-size: 12px;
              color: var(--txt); }
  .treadout b { color: var(--gold-lt); font-size: 10px; letter-spacing: 1px; }
  .treadout b.en { color: var(--loss); }
  .tg { width: 4px; height: 16px; border-radius: 2px; }

  .ctx { display: flex; flex-direction: column; gap: 3px; }
  .ctx p { font-size: 12px; margin: 0; }
  .note { color: var(--txt-dim); }
  .coh { color: #e0b35f; }
  .exp { color: var(--win); }

  .topcall { position: relative; display: block; width: 100%; text-align: left;
    border-radius: 12px; overflow: hidden; cursor: pointer; min-height: 130px;
    border: 1px solid var(--tag); background: none; padding: 0;
    transition: all .25s; color: var(--txt); font-family: var(--font-ui); }
  .topcall:hover:not(:disabled) { transform: translateY(-3px);
    box-shadow: 0 14px 40px rgba(0,0,0,.5),
                0 0 30px color-mix(in srgb, var(--tag) 45%, transparent); }
  .topcall:disabled { cursor: default; }
  .tcsplash { position: absolute; inset: 0; background-size: cover;
              background-position: center 22%;
              animation: kenburns 14s ease-in-out infinite alternate; }
  @keyframes kenburns { from { transform: scale(1.02); }
                        to { transform: scale(1.1) translateY(-6px); } }
  .tcscrim { position: absolute; inset: 0;
    background: linear-gradient(90deg, rgba(4,9,20,.92) 26%, rgba(4,9,20,.35)); }
  .tcbody { position: relative; padding: 14px 18px; display: flex;
            flex-direction: column; gap: 5px; }
  .tcbody h2 { font-family: var(--font-display); font-size: 30px;
               letter-spacing: 4px; color: var(--gold-lt);
               text-shadow: 0 0 22px rgba(200,170,110,.5); }
  .tcrow { display: flex; gap: 14px; align-items: baseline; }
  .tag { font-size: 10px; letter-spacing: 2px; color: var(--tag);
         border: 1px solid var(--tag); padding: 2px 9px; border-radius: 99px; }
  .score { margin-left: auto; font-size: 13px; color: var(--gold-lt); }
  .why { font-size: 12px; color: var(--txt-dim); max-width: 70%; }

  .alts { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
  .alt { display: flex; flex-direction: column; align-items: center; gap: 4px;
    padding: 10px 6px; border-radius: 10px; cursor: pointer;
    background: rgba(6,13,26,.55); border: 1px solid rgba(255,255,255,.1);
    color: var(--txt); font-family: var(--font-ui); transition: all .2s; }
  .alt:hover:not(:disabled) { border-color: var(--tag); transform: translateY(-2px);
    box-shadow: 0 0 16px color-mix(in srgb, var(--tag) 40%, transparent); }
  .alt:disabled { cursor: default; opacity: .8; }
  .alt img { width: 40px; height: 40px; border-radius: 9px;
             border: 1px solid rgba(200,170,110,.3); }
  .alt b { font-size: 11px; }
  .alt span { font-size: 8px; color: var(--tag); letter-spacing: 1px; }

  .warming { padding: 26px; text-align: center; display: flex;
             flex-direction: column; gap: 6px; border-radius: 10px;
             border: 1px dashed rgba(200,170,110,.35); }
  .warming b { letter-spacing: 2px; color: var(--gold-lt); }

  .opclock { padding: 36px 20px; text-align: center; display: flex;
             flex-direction: column; align-items: center; gap: 10px; }
  .opclock b { font-size: 19px; letter-spacing: 3px; color: var(--txt-dim); }
  .pulse { width: 60px; height: 4px; border-radius: 2px;
           background: var(--loss); opacity: .6;
           animation: opwait 1.6s ease-in-out infinite; }
  @keyframes opwait { 50% { opacity: .15; transform: scaleX(.55); } }

  .manual { margin-top: auto; display: flex; flex-direction: column; gap: 10px; }
  .seek { background: rgba(6,13,26,.7); border: 1px solid rgba(200,170,110,.35);
          border-radius: 8px; padding: 9px 14px; color: var(--txt);
          font-family: var(--font-ui); font-size: 14px; width: 100%;
          outline: none; }
  .seek:focus { border-color: var(--gold); box-shadow: 0 0 14px rgba(200,170,110,.25); }
  .rolepick { display: flex; gap: 8px; align-items: center; }
  .rolepick span { font-size: 11px; color: var(--txt-dim); }
  .rp { padding: 6px 14px; border-radius: 8px; cursor: pointer;
    background: rgba(200,170,110,.12); border: 1px solid rgba(200,170,110,.5);
    color: var(--gold-lt); font-family: var(--font-mono); font-size: 11px;
    letter-spacing: 1px; }
  .rp:hover { border-color: var(--gold-hot); box-shadow: 0 0 12px rgba(200,170,110,.35); }
  .rp.x { border-color: rgba(224,108,95,.5); color: var(--loss); }
  .grid8 { display: grid; grid-template-columns: repeat(auto-fill, minmax(68px, 1fr));
           gap: 8px; }
  .gcell { display: flex; flex-direction: column; align-items: center; gap: 3px;
           background: none; border: none; cursor: pointer; color: var(--txt-dim);
           font-family: var(--font-ui); font-size: 10px; }
  .gcell img { width: 42px; height: 42px; border-radius: 9px;
               border: 1px solid rgba(200,170,110,.3); transition: transform .15s; }
  .gcell:hover:not(:disabled) img { transform: scale(1.15);
               box-shadow: 0 0 14px rgba(200,170,110,.4); }
  .gcell:disabled { opacity: .25; cursor: default; }

  .dim { color: var(--txt-faint); }
  .mono { font-family: var(--font-mono); }
  .kicker.dim { color: var(--txt-faint); }

  @media (max-width: 1100px) {
    .boardgrid { grid-template-columns: 1fr 1fr;
      grid-template-areas: 'blue red' 'center center'; }
    .seq { grid-template-columns: repeat(10, 1fr); }
  }
</style>
