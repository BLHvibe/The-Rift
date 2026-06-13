<script>
  import { onMount } from 'svelte'
  import { fade } from 'svelte/transition'
  import { loadCoreData, loadScoutSheets } from '../../draft/engine.js'
  import { draft, setScoutReady, exitDraft } from '../../draft/store.js'

  let done = 0, total = 1, sent = false

  $: names = [
    ...($draft.state.players.BLUE ?? []),
    ...($draft.state.players.RED ?? []),
  ].map(p => p?.name).filter(Boolean)
  $: waitingOther = $draft.mode === 'synced' && sent

  onMount(async () => {
    total = Math.max(1, names.length)
    try {
      await loadCoreData()
      await loadScoutSheets(names, (d, t) => { done = d; total = t })
    } catch (e) { console.error(e) }
    done = total
    sent = true
    setScoutReady(true)
  })
</script>

<div class="scouting">
  <div class="rune" in:fade={{ duration: 400 }}>
    <svg viewBox="0 0 120 120" width="120" height="120">
      <polygon points="60,8 105,34 105,86 60,112 15,86 15,34"
               fill="none" stroke="var(--gold)" stroke-width="1.5"
               opacity="0.8" class="hex" />
      <polygon points="60,26 90,43 90,77 60,94 30,77 30,43"
               fill="none" stroke="var(--gold-lt)" stroke-width="1"
               opacity="0.5" class="hex r" />
    </svg>
  </div>
  <h2 class="gold-text">FETCHING SCOUT DATA</h2>
  <p class="mono dim">pulling ranked + draft pools · {done}/{total} done</p>
  <div class="bar"><em style="width:{(done / total) * 100}%"></em></div>
  {#if waitingOther}
    <p class="mono wait" transition:fade>✓ scout data ready — waiting on the other side…</p>
  {/if}
  <button class="exitb" on:click={exitDraft}>EXIT</button>
</div>

<style>
  .scouting { height: 100%; display: flex; flex-direction: column;
              align-items: center; justify-content: center; gap: 16px;
              position: relative; }
  .hex { transform-origin: 60px 60px; animation: spin 9s linear infinite; }
  .hex.r { animation-direction: reverse; animation-duration: 6s; }
  @keyframes spin { to { transform: rotate(360deg); } }
  h2 { font-family: var(--font-display); font-size: 26px; letter-spacing: 6px; }
  .dim { color: var(--txt-dim); font-size: 12px; }
  .mono { font-family: var(--font-mono); }
  .bar { width: min(420px, 70%); height: 6px; border-radius: 3px;
         background: rgba(255,255,255,.07); overflow: hidden; }
  .bar em { display: block; height: 100%;
            background: linear-gradient(90deg, var(--gold-dk), var(--gold-hot));
            box-shadow: 0 0 12px rgba(200,170,110,.6);
            transition: width .4s ease; }
  .wait { color: var(--win); font-size: 12px; }
  .exitb { position: absolute; top: 22px; right: 26px;
    padding: 7px 16px; border-radius: 8px; cursor: pointer;
    background: rgba(255,255,255,.04); border: 1px solid rgba(224,108,95,.4);
    color: var(--txt-dim); font-family: var(--font-ui); font-weight: 700;
    letter-spacing: 2px; font-size: 12px; }
  .exitb:hover { color: var(--loss); border-color: var(--loss); }
</style>
