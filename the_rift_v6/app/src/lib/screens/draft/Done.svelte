<script>
  import { onMount } from 'svelte'
  import { fly } from 'svelte/transition'
  import { iconUrl, post } from '../../api.js'
  import ARCH from '../../archetypes.json'
  import { primaryRoles } from '../../draft/engine.js'
  import { draft, resetDraft, exitDraft } from '../../draft/store.js'
  import { ROLES } from '../../draft/seq.js'

  let matchups = null

  $: st = $draft.state
  $: solo = $draft.mode === 'solo'
  $: isHost = solo || $draft.you.is_host
  $: ourSide = st.our_side

  onMount(async () => {
    try {
      // → [[role, blueName, redName, blueWinPct, note], ...]
      const out = await post('/engine/matchups', {
        blue: st.players.BLUE ?? [],
        red: st.players.RED ?? [],
        primary_roles: primaryRoles,
        blue_picks: ROLES.map(r => st.picks.BLUE?.[r] ?? ''),
        red_picks: ROLES.map(r => st.picks.RED?.[r] ?? ''),
      })
      if (Array.isArray(out)) {
        matchups = out.map(m => ({
          role: m[0], blue: m[1], red: m[2], pct: +m[3], note: m[4],
        }))
      }
    } catch (e) { console.error(e) }
  })

  const playerAt = (side, role) => {
    const i = ROLES.indexOf(role)
    return st.players[side]?.[i]?.name ?? ''
  }
  const archLabel = a => a ? (ARCH[a]?.label ?? a) : 'no archetype'
  const sideCol = s => s === 'BLUE' ? '#59b3d4' : 'var(--loss)'
  $: archs = {
    [ourSide]: st.archetype_self,
    [ourSide === 'BLUE' ? 'RED' : 'BLUE']: st.archetype_enemy,
  }
</script>

<div class="wrap">
  <header class="hero" in:fly={{ y: -20, duration: 600 }}>
    <h1 class="gold-sweep">DRAFT COMPLETE</h1>
    <span class="mono dim">the war room has spoken — win conditions revealed</span>
  </header>

  <div class="cols">
    {#each ['BLUE', 'RED'] as side, i (side)}
      <section class="glass card" style="--side:{sideCol(side)}"
               in:fly={{ y: 30, duration: 500, delay: i * 150 }}>
        <header>
          <h3>{side} SIDE</h3>
          <span class="cap mono">{$draft.sides[side] ?? ''}</span>
        </header>
        <div class="archrow">
          <span class="kicker dim">WIN CONDITION</span>
          <b class="gold-text">{archLabel(archs[side]).toUpperCase()}</b>
        </div>
        {#each ROLES as role}
          {@const champ = st.picks[side]?.[role]}
          <div class="rrow">
            <span class="role mono">{role}</span>
            {#if champ}<img src={iconUrl(champ)} alt={champ} />{/if}
            <b>{champ ?? '—'}</b>
            <span class="who mono">{playerAt(side, role)}</span>
          </div>
        {/each}
        <div class="bansrow">
          <span class="kicker dim">BANS</span>
          {#each st.bans[side] ?? [] as b}
            <span class="bicon" title={b}><img src={iconUrl(b)} alt={b} /><s></s></span>
          {/each}
        </div>
      </section>
    {/each}
  </div>

  {#if matchups?.length}
    <section class="glass lanes" in:fly={{ y: 26, duration: 500, delay: 350 }}>
      <header><span class="kicker">◆ LANE READOUT</span><div class="rule-fade"></div></header>
      <div class="lanegrid">
        {#each matchups as m}
          <div class="lane">
            <span class="role mono">{m.role}</span>
            <span class="pair">{m.blue} <i>vs</i> {m.red}</span>
            <span class="pct mono" class:adv={m.pct >= 55} class:dis={m.pct <= 45}>
              {Math.round(m.pct)}% blue</span>
            <b>{m.note}</b>
          </div>
        {/each}
      </div>
    </section>
  {/if}

  <div class="btns">
    {#if isHost}
      <button class="primary" on:click={resetDraft}>⬡ NEW DRAFT</button>
    {/if}
    <button class="ghost" on:click={exitDraft}>EXIT WAR ROOM</button>
  </div>
</div>

<style>
  .wrap { height: 100%; overflow-y: auto; padding: 30px 26px; }
  .hero { text-align: center; margin-bottom: 24px; }
  h1 { font-family: var(--font-display); font-size: 42px; letter-spacing: 9px; }
  .cols { display: grid; grid-template-columns: 1fr 1fr; gap: 16px;
          max-width: 1100px; margin: 0 auto; }
  .card { padding: 18px 20px; border-top: 3px solid var(--side); }
  .card header { display: flex; justify-content: space-between;
                 align-items: baseline; margin-bottom: 8px; }
  .card h3 { font-family: var(--font-mono); font-size: 12px; letter-spacing: 3px;
             color: var(--side); text-shadow: 0 0 12px var(--side); }
  .cap { font-size: 10px; color: var(--txt-faint); }
  .archrow { display: flex; flex-direction: column; gap: 2px; margin-bottom: 12px;
             padding-bottom: 10px; border-bottom: 1px solid rgba(200,170,110,.15); }
  .archrow b { font-size: 17px; letter-spacing: 2px; }
  .rrow { display: flex; align-items: center; gap: 12px; padding: 6px 4px; }
  .role { font-size: 9px; width: 30px; color: var(--txt-faint); }
  .rrow img { width: 40px; height: 40px; border-radius: 9px;
              border: 1px solid rgba(200,170,110,.4); }
  .rrow b { font-size: 14px; }
  .who { margin-left: auto; font-size: 10px; color: var(--txt-faint); }
  .bansrow { display: flex; align-items: center; gap: 8px; margin-top: 12px;
             padding-top: 10px; border-top: 1px solid rgba(255,255,255,.06); }
  .bicon { position: relative; }
  .bicon img { width: 28px; height: 28px; border-radius: 6px;
               filter: grayscale(.7) brightness(.75);
               border: 1px solid rgba(224,108,95,.4); }
  .bicon s { position: absolute; top: 13px; left: 1px; width: 26px; height: 2px;
             background: var(--loss); transform: rotate(-40deg); }
  .lanes { max-width: 1100px; margin: 16px auto 0; padding: 16px 20px; }
  .lanes header { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; }
  .lanegrid { display: flex; flex-direction: column; gap: 6px; }
  .lane { display: flex; gap: 14px; align-items: baseline; font-size: 12px; }
  .lane .pair { min-width: 180px; }
  .lane .pair i { font-style: normal; color: var(--txt-faint); font-size: 10px; }
  .lane .pct { min-width: 70px; color: var(--txt-dim); }
  .lane .pct.adv { color: var(--win); }
  .lane .pct.dis { color: var(--loss); }
  .lane b { color: var(--txt-dim); font-weight: 400; }
  .btns { display: flex; justify-content: center; gap: 14px; margin-top: 26px; }
  .primary { padding: 13px 28px; border-radius: 10px; cursor: pointer;
    background: linear-gradient(180deg, rgba(200,170,110,.3), rgba(120,90,40,.2));
    border: 1px solid rgba(200,170,110,.6); color: var(--gold-lt);
    font-family: var(--font-ui); font-weight: 700; letter-spacing: 2.5px;
    font-size: 14px; transition: all .25s; }
  .primary:hover { border-color: var(--gold-hot);
    box-shadow: 0 0 28px rgba(200,170,110,.4); transform: translateY(-2px); }
  .ghost { padding: 13px 22px; border-radius: 10px; cursor: pointer;
    background: rgba(255,255,255,.04); border: 1px solid rgba(200,170,110,.25);
    color: var(--txt-dim); font-family: var(--font-ui); font-weight: 700;
    letter-spacing: 2px; font-size: 12px; }
  .ghost:hover { color: var(--gold-lt); border-color: var(--gold); }
  .dim { color: var(--txt-faint); }
  .mono { font-family: var(--font-mono); }
  @media (max-width: 1100px) { .cols { grid-template-columns: 1fr; } }
</style>
