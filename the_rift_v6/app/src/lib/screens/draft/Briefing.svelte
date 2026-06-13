<script>
  import { onMount } from 'svelte'
  import { fly } from 'svelte/transition'
  import { iconUrl } from '../../api.js'
  import { recommendComps, recommendBans } from '../../draft/engine.js'
  import { draft, other, setBriefingDone, exitDraft } from '../../draft/store.js'

  let data = null, sent = false

  $: ourSide = $draft.state.our_side
  $: waitingOther = $draft.mode === 'synced' && sent

  onMount(async () => {
    const ours = $draft.state.players[ourSide] ?? []
    const theirs = $draft.state.players[other(ourSide)] ?? []
    try {
      const [usComp, themComp, usBans, themBans] = await Promise.all([
        recommendComps(ours, { n: 1 }),
        recommendComps(theirs, { n: 1 }),
        recommendBans(theirs, { n: 3 }),
        recommendBans(ours, { n: 3 }),
      ])
      data = {
        our: usComp[0] ?? null,
        their: themComp[0] ?? null,
        ourBans: usBans.names,
        theirBans: themBans.names,
      }
    } catch (e) { console.error(e); data = { our: null, their: null, ourBans: [], theirBans: [] } }
  })

  function go() { sent = true; setBriefingDone(true) }
</script>

<div class="wrap">
  <header class="top">
    <span class="kicker">◆ PRE-DRAFT BRIEFING</span><div class="rule-fade"></div>
    <button class="exitb" on:click={exitDraft}>EXIT</button>
  </header>

  {#if !data}
    <div class="loading mono dim">projecting compositions…</div>
  {:else}
    <div class="cols">
      {#each [['OUR PROJECTION', data.our, data.ourBans, ourSide === 'BLUE' ? '#59b3d4' : 'var(--loss)'], ['ENEMY PROJECTION', data.their, data.theirBans, ourSide === 'BLUE' ? 'var(--loss)' : '#59b3d4']] as [title, comp, bans, col], i}
        <section class="glass card" style="--side:{col}"
                 in:fly={{ y: 26, duration: 480, delay: i * 140 }}>
          <header><span class="kicker">◆ {title}</span><div class="rule-fade"></div></header>
          {#if comp}
            <b class="archlabel gold-text">{(comp.label ?? '').toUpperCase()}</b>
            <span class="viab mono" data-v={comp.viability}>{comp.viability}</span>
            <div class="champs">
              {#each comp.picks ?? [] as p}
                {#if p.champion && p.champion !== '?'}
                  <div class="ch"><img src={iconUrl(p.champion)} alt={p.champion} />
                    <span>{p.champion}</span></div>
                {/if}
              {/each}
            </div>
            {#if comp.win_condition}<p class="wincon">{comp.win_condition}</p>{/if}
          {:else}
            <p class="dim mono">no projection — thin data for this roster</p>
          {/if}
          <div class="bansrow">
            <span class="kicker dim">KEY BANS {i === 0 ? 'TO THROW' : 'TO FEAR'}</span>
            <div class="banlist">
              {#each bans as b}
                <div class="ban"><img src={iconUrl(b)} alt={b} /><s></s><span>{b}</span></div>
              {/each}
            </div>
          </div>
        </section>
      {/each}
    </div>

    <div class="gorow">
      {#if waitingOther}
        <span class="mono wait">✓ briefing read — waiting on the other side…</span>
      {:else}
        <button class="gob" on:click={go}>CONTINUE → CHOOSE WIN CONDITION</button>
      {/if}
    </div>
  {/if}
</div>

<style>
  .wrap { height: 100%; overflow-y: auto; padding: 26px; }
  .top { display: flex; align-items: center; gap: 14px; margin-bottom: 18px; }
  .exitb { padding: 7px 16px; border-radius: 8px; cursor: pointer;
    background: rgba(255,255,255,.04); border: 1px solid rgba(224,108,95,.4);
    color: var(--txt-dim); font-family: var(--font-ui); font-weight: 700;
    letter-spacing: 2px; font-size: 12px; }
  .exitb:hover { color: var(--loss); border-color: var(--loss); }
  .loading { padding: 60px; text-align: center; }
  .cols { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  .card { padding: 18px 20px; border-top: 3px solid var(--side); }
  .card header { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
  .archlabel { font-size: 19px; letter-spacing: 3px; display: block; }
  .viab { font-size: 10px; letter-spacing: 2px; color: var(--txt-faint); }
  .viab[data-v="STRONG"] { color: var(--win); }
  .viab[data-v="VIABLE"] { color: var(--gold-lt); }
  .viab[data-v="WEAK"] { color: var(--loss); }
  .champs { display: flex; gap: 12px; margin: 14px 0; flex-wrap: wrap; }
  .ch { display: flex; flex-direction: column; align-items: center; gap: 4px; }
  .ch img { width: 52px; height: 52px; border-radius: 10px;
            border: 1px solid rgba(200,170,110,.4); }
  .ch span { font-size: 10px; color: var(--txt-dim); }
  .wincon { font-size: 12px; color: var(--txt-dim); line-height: 1.5; }
  .bansrow { margin-top: 14px; border-top: 1px solid rgba(200,170,110,.15);
             padding-top: 12px; }
  .banlist { display: flex; gap: 12px; margin-top: 8px; }
  .ban { position: relative; display: flex; flex-direction: column;
         align-items: center; gap: 3px; }
  .ban img { width: 40px; height: 40px; border-radius: 8px;
             border: 1px solid rgba(224,108,95,.5); filter: saturate(.8); }
  .ban s { position: absolute; top: 19px; left: 3px; width: 34px; height: 2px;
           background: var(--loss); transform: rotate(-40deg);
           box-shadow: 0 0 8px var(--loss); }
  .ban span { font-size: 9px; color: var(--txt-faint); }
  .gorow { margin-top: 22px; display: flex; justify-content: center; }
  .gob { padding: 13px 30px; border-radius: 10px; cursor: pointer;
    background: linear-gradient(180deg, rgba(200,170,110,.3), rgba(120,90,40,.2));
    border: 1px solid rgba(200,170,110,.6); color: var(--gold-lt);
    font-family: var(--font-ui); font-weight: 700; letter-spacing: 2.5px;
    font-size: 14px; transition: all .25s; }
  .gob:hover { border-color: var(--gold-hot);
    box-shadow: 0 0 24px rgba(200,170,110,.4); transform: translateY(-2px); }
  .wait { color: var(--win); font-size: 12px; font-family: var(--font-mono); }
  .dim { color: var(--txt-faint); }
  .mono { font-family: var(--font-mono); }
  @media (max-width: 1100px) { .cols { grid-template-columns: 1fr; } }
</style>
