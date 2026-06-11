<script>
  import { onMount } from 'svelte'
  import { fly } from 'svelte/transition'
  import { api } from '../api.js'

  const TIERS = [
    ['S', '#dc4646'], ['A', '#e08c3c'], ['B', '#c8aa6e'],
    ['C', '#6ec88c'], ['D', '#5a8cb4'], ['F', '#6e6e78'],
  ]
  let board = { S: [], A: [], B: [], C: [], D: [], F: [], pool: [] }
  let drag = null

  onMount(async () => {
    let roster = []
    try { roster = (await api('/players'))?.players ?? [] } catch {}
    const saved = JSON.parse(localStorage.getItem('rift_tierlist_v6') ?? 'null')
    if (saved) {
      board = saved
      const placed = new Set(Object.values(board).flat())
      for (const n of roster) if (!placed.has(n)) board.pool.push(n)
    } else {
      board.pool = roster
    }
    board = board
  })

  const save = () => localStorage.setItem('rift_tierlist_v6', JSON.stringify(board))
  function dropTo(zone) {
    if (!drag) return
    for (const k of Object.keys(board)) board[k] = board[k].filter(n => n !== drag)
    board[zone] = [...board[zone], drag]
    drag = null
    board = board
    save()
  }
  function reset() {
    const all = Object.values(board).flat()
    board = { S: [], A: [], B: [], C: [], D: [], F: [], pool: all }
    save()
  }
</script>

<div class="wrap">
  <header class="top">
    <span class="kicker">◆ TIER LIST</span><div class="rule-fade"></div>
    <button class="reset" on:click={reset}>RESET</button>
  </header>

  {#each TIERS as [t, color], i}
    <div class="tier glass" style="--tc:{color}"
         in:fly={{ y: 22, duration: 420, delay: i * 70 }}
         on:dragover|preventDefault on:drop={() => dropTo(t)} role="list">
      <span class="lbl" style="background:{color}">{t}</span>
      <div class="zone">
        {#each board[t] as n (n)}
          <span class="chip" draggable="true"
                on:dragstart={() => drag = n}>{n.toUpperCase()}</span>
        {/each}
      </div>
    </div>
  {/each}

  <div class="pool glass" on:dragover|preventDefault on:drop={() => dropTo('pool')} role="list">
    <span class="kicker">PLAYER POOL — drag names into tiers</span>
    <div class="zone">
      {#each board.pool as n (n)}
        <span class="chip" draggable="true" on:dragstart={() => drag = n}>{n.toUpperCase()}</span>
      {/each}
    </div>
  </div>
</div>

<style>
  .wrap { height: 100%; overflow-y: auto; padding: 26px; }
  .top { display: flex; align-items: center; gap: 14px; margin-bottom: 14px; }
  .reset {
    padding: 7px 16px; border-radius: 8px; cursor: pointer;
    background: rgba(255,255,255,.04); border: 1px solid rgba(200,170,110,.3);
    color: var(--txt-dim); font-family: var(--font-ui); font-weight: 700;
    letter-spacing: 2px; font-size: 12px;
  }
  .reset:hover { color: var(--gold-lt); border-color: var(--gold); }
  .tier {
    display: flex; align-items: stretch; min-height: 66px;
    margin-bottom: 8px; overflow: hidden;
    border-left: none;
  }
  .lbl {
    width: 60px; display: grid; place-items: center;
    font-family: var(--font-display); font-size: 26px; color: #0a1428;
    text-shadow: 0 1px 0 rgba(255,255,255,.3);
    box-shadow: 0 0 26px color-mix(in srgb, var(--tc) 45%, transparent);
  }
  .zone { flex: 1; display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
          padding: 10px 14px; min-height: 46px; }
  .chip {
    padding: 8px 16px; border-radius: 9px; cursor: grab;
    background: linear-gradient(180deg, rgba(22,48,79,.9), rgba(13,28,50,.9));
    border: 1px solid rgba(200,170,110,.35);
    font-weight: 700; font-size: 13px; letter-spacing: 1.5px;
    transition: all .18s;
  }
  .chip:hover { border-color: var(--gold-hot); transform: translateY(-3px) scale(1.04);
                box-shadow: 0 8px 20px rgba(0,0,0,.5), 0 0 16px rgba(200,170,110,.3); }
  .chip:active { cursor: grabbing; }
  .pool { margin-top: 16px; padding: 14px 16px; }
</style>
