<script>
  import { motion } from '../stores.js'
</script>

<div class="wrap">
  <header class="top"><span class="kicker">◆ SETTINGS</span><div class="rule-fade"></div></header>

  <section class="glass card">
    <h3 class="gold-text">MOTION</h3>
    <p>How alive the app feels — embers, fog, parallax, dissolves. Zero is calm and static.</p>
    <div class="slider">
      <input type="range" min="0" max="1" step="0.05" bind:value={$motion} />
      <b>{Math.round($motion * 100)}%</b>
    </div>
  </section>

  <section class="glass card">
    <h3 class="gold-text">DATA</h3>
    <p class="mono">source · the-rift-draft-sync.fly.dev (live)</p>
    <p class="mono dim">v6.0.0-alpha · draft tool runs on v5 until the port lands</p>
  </section>
</div>

<style>
  .wrap { height: 100%; overflow-y: auto; padding: 26px; max-width: 760px; }
  .top { display: flex; align-items: center; gap: 14px; margin-bottom: 16px; }
  .card { padding: 22px 24px; margin-bottom: 16px; }
  h3 { font-family: var(--font-display); letter-spacing: 3px; font-size: 18px; margin-bottom: 8px; }
  p { color: var(--txt-dim); font-size: 14px; margin-bottom: 12px; }
  .mono { font-family: var(--font-mono); font-size: 12px; }
  .dim { color: var(--txt-faint); }
  .slider { display: flex; align-items: center; gap: 18px; }
  input[type=range] { flex: 1; accent-color: var(--gold); }
  .slider b { font-family: var(--font-mono); color: var(--gold-lt); width: 48px; }
</style>
