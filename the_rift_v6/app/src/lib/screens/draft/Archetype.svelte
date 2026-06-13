<script>
  import { onMount } from 'svelte'
  import { fly, fade } from 'svelte/transition'
  import { iconUrl } from '../../api.js'
  import ARCH from '../../archetypes.json'
  import { recommendComps } from '../../draft/engine.js'
  import { draft, setArchetype, exitDraft } from '../../draft/store.js'

  let cards = []        // engine-ranked comps for OUR roster
  let loaded = false
  let pending = null    // locally chosen, awaiting CONFIRM
  let confirmed = false

  $: ourSide = $draft.state.our_side
  $: ourPlayers = $draft.state.players[ourSide] ?? []
  $: waitingOther = $draft.mode === 'synced' && confirmed

  onMount(async () => {
    try {
      cards = await recommendComps(ourPlayers, { n: 7 })
    } catch (e) { console.error(e) }
    loaded = true
  })

  function confirm() {
    if (!pending && pending !== '') return
    confirmed = true
    setArchetype(pending || null)
  }
  const meta = key => ARCH[key] ?? {}
</script>

<div class="wrap">
  <header class="top">
    <span class="kicker">◆ CHOOSE YOUR WIN CONDITION</span><div class="rule-fade"></div>
    <span class="mono dim">ranked for YOUR five — the other side can't see this</span>
    <button class="exitb" on:click={exitDraft}>EXIT</button>
  </header>

  {#if !loaded}
    <div class="loading mono dim">running the engine over your roster…</div>
  {:else}
    <div class="grid">
      {#each cards as c, i (c.archetype)}
        <button class="acard glass" class:sel={pending === c.archetype}
                in:fly={{ y: 30, duration: 420, delay: 60 + i * 70 }}
                on:click={() => pending = c.archetype}>
          <div class="ahead">
            <b class="gold-text">{(c.label ?? c.archetype).toUpperCase()}</b>
            <span class="viab mono" data-v={c.viability}>{c.viability}</span>
          </div>
          <div class="dots">
            {#each Array(5) as _, d}
              <i class:on={d < (c.synergy ?? 0)}></i>
            {/each}
            <em class="mono">{Math.round(c.combined ?? 0)}</em>
          </div>
          <div class="picks">
            {#each (c.picks ?? []).slice(0, 5) as p, pi}
              {#if p.champion && p.champion !== '?'}
                <span class="pk" title="{ourPlayers[pi]?.name ?? ''} → {p.champion}">
                  <img src={iconUrl(p.champion)} alt={p.champion} /></span>
              {/if}
            {/each}
          </div>
          <em class="win">{c.win_condition ?? meta(c.archetype).win ?? ''}</em>
          <i class="kicker">SPIKES {(c.spike ?? meta(c.archetype).spike ?? '—').toUpperCase()}</i>
        </button>
      {/each}
      <button class="acard glass none" class:sel={pending === ''}
              on:click={() => pending = ''}>
        <span class="ahex">◇</span><b>NO ARCHETYPE</b>
        <em class="win">Draft on raw comfort — the engine still calls every pick</em>
      </button>
    </div>

    <div class="confrow">
      {#if waitingOther}
        <span class="mono wait" transition:fade>✓ win condition locked — waiting on the other side…</span>
      {:else}
        <button class="confb" disabled={pending === null} on:click={confirm}>
          {pending === null ? 'SELECT A WIN CONDITION'
            : pending === '' ? 'CONFIRM — NO ARCHETYPE'
            : `CONFIRM — ${(meta(pending).label ?? pending).toUpperCase()}`}
        </button>
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
    letter-spacing: 2px; font-size: 12px; margin-left: auto; }
  .exitb:hover { color: var(--loss); border-color: var(--loss); }
  .loading { padding: 60px; text-align: center; }
  .grid { display: grid; grid-template-columns: repeat(4, minmax(220px, 1fr));
          gap: 14px; }
  .acard { display: flex; flex-direction: column; gap: 8px; text-align: left;
    padding: 16px 18px; cursor: pointer; color: var(--txt);
    font-family: var(--font-ui); transition: all .22s; }
  .acard:hover { transform: translateY(-5px); border-color: var(--gold-hot);
    box-shadow: 0 18px 44px rgba(0,0,0,.5), 0 0 30px rgba(200,170,110,.28); }
  .acard.sel { border-color: var(--gold-hot);
    box-shadow: 0 0 34px rgba(200,170,110,.45); }
  .ahead { display: flex; justify-content: space-between; align-items: baseline; }
  .ahead b { font-size: 15px; letter-spacing: 2px; }
  .viab { font-size: 9px; letter-spacing: 1.5px; color: var(--txt-faint); }
  .viab[data-v="STRONG"] { color: var(--win); text-shadow: 0 0 10px rgba(110,190,140,.5); }
  .viab[data-v="VIABLE"] { color: var(--gold-lt); }
  .viab[data-v="WEAK"] { color: var(--loss); }
  .dots { display: flex; gap: 4px; align-items: center; }
  .dots i { width: 8px; height: 8px; border-radius: 50%;
            background: rgba(255,255,255,.08); }
  .dots i.on { background: var(--gold); box-shadow: 0 0 8px rgba(200,170,110,.6); }
  .dots em { margin-left: auto; font-style: normal; font-size: 11px;
             color: var(--txt-faint); }
  .picks { display: flex; gap: 6px; }
  .pk img { width: 38px; height: 38px; border-radius: 8px;
            border: 1px solid rgba(200,170,110,.35); }
  .win { font-style: normal; font-size: 11px; color: var(--txt-dim);
         line-height: 1.5; }
  .acard i.kicker { font-size: 9px; }
  .acard.none { justify-content: center; align-items: center;
                text-align: center; color: var(--txt-dim); }
  .ahex { font-size: 22px; color: var(--gold); opacity: .65; }
  .confrow { margin-top: 22px; display: flex; justify-content: center; }
  .confb { padding: 13px 30px; border-radius: 10px; cursor: pointer;
    background: linear-gradient(180deg, rgba(200,170,110,.3), rgba(120,90,40,.2));
    border: 1px solid rgba(200,170,110,.6); color: var(--gold-lt);
    font-family: var(--font-ui); font-weight: 700; letter-spacing: 2.5px;
    font-size: 14px; transition: all .25s; }
  .confb:hover:not(:disabled) { border-color: var(--gold-hot);
    box-shadow: 0 0 24px rgba(200,170,110,.4); transform: translateY(-2px); }
  .confb:disabled { opacity: .45; cursor: default; }
  .wait { color: var(--win); font-size: 12px; font-family: var(--font-mono); }
  .dim { color: var(--txt-faint); font-size: 11px; }
  .mono { font-family: var(--font-mono); }
  @media (max-width: 1100px) { .grid { grid-template-columns: repeat(2, 1fr); } }
</style>
