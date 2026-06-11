<script>
  import { onMount } from 'svelte'
  import { api } from '../api.js'
  let items = ['WELCOME TO THE RIFT V6']
  onMount(async () => {
    try {
      const acts = await api('/activity')
      const evts = (acts?.events || acts || []).slice(0, 20)
      const lines = evts.map(e => (e.desc || e.summary || '').toUpperCase())
                        .filter(Boolean)
      if (lines.length) items = lines
    } catch {}
  })
</script>

<div class="ticker glass">
  <span class="pill kicker">LIVE</span>
  <div class="track">
    <div class="scroll">
      {#each [...items, ...items] as it}
        <span class="item">{it}<i>◆</i></span>
      {/each}
    </div>
  </div>
</div>

<style>
  .ticker {
    height: 30px;
    display: flex; align-items: center;
    border-radius: 0; border: none;
    border-top: 1px solid var(--glass-border);
    overflow: hidden;
    z-index: 10;
  }
  .pill {
    flex-shrink: 0;
    padding: 0 14px;
    line-height: 30px;
    background: linear-gradient(180deg, rgba(200,170,110,.3), rgba(120,90,40,.3));
    border-right: 1px solid var(--glass-border);
  }
  .track { overflow: hidden; flex: 1; }
  .scroll {
    display: inline-flex; white-space: nowrap;
    animation: marquee 60s linear infinite;
  }
  .item {
    font-family: var(--font-mono); font-size: 11px;
    letter-spacing: 1.5px; color: var(--txt-dim);
  }
  .item i { color: var(--gold); font-style: normal; margin: 0 18px; opacity: .6; }
  @keyframes marquee { to { transform: translateX(-50%); } }
</style>
