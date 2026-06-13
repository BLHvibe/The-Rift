<script>
  import { fly, fade } from 'svelte/transition'
  import { createEventDispatcher } from 'svelte'
  const dispatch = createEventDispatcher()

  const SHORTCUTS = [
    ['1 – 9', 'Jump to a tab (Home · Rankings · Draft · Scout · Inhouse · Tier List · Feed · Commands · Settings)'],
    ['Esc', 'Close the open overlay (this card · match detail)'],
    ['? / F1', 'Toggle this shortcuts card'],
    ['Click name', 'Open a player’s scout report from any leaderboard'],
    ['Click match', 'Open the full scoreboard in Inhouse → History'],
  ]
</script>

<div class="veil" transition:fade={{ duration: 180 }}
     on:click|self={() => dispatch('close')} role="dialog">
  <div class="card glass" in:fly={{ y: 24, duration: 320 }}>
    <h2 class="gold-sweep">KEYBOARD SHORTCUTS</h2>
    <div class="rows">
      {#each SHORTCUTS as [key, desc]}
        <div class="row">
          <kbd>{key}</kbd>
          <span>{desc}</span>
        </div>
      {/each}
    </div>
    <span class="hint mono">press ? or Esc to close</span>
  </div>
</div>

<style>
  .veil { position: fixed; inset: 0; z-index: 80; background: rgba(4,8,18,.78);
    backdrop-filter: blur(8px); display: grid; place-items: center; }
  .card { padding: 30px 36px; width: min(560px, 90%); }
  h2 { font-family: var(--font-display); font-size: 24px; letter-spacing: 6px;
    text-align: center; margin-bottom: 22px; }
  .rows { display: flex; flex-direction: column; gap: 12px; }
  .row { display: grid; grid-template-columns: 110px 1fr; gap: 18px;
    align-items: center; }
  kbd { font-family: var(--font-mono); font-size: 12px; text-align: center;
    padding: 6px 10px; border-radius: 7px; color: var(--gold-lt);
    background: rgba(200,170,110,.1); border: 1px solid rgba(200,170,110,.4);
    box-shadow: 0 2px 0 rgba(200,170,110,.2); }
  .row span { font-size: 13px; color: var(--txt-dim); line-height: 1.4; }
  .hint { display: block; text-align: center; margin-top: 22px;
    font-size: 10px; color: var(--txt-faint); letter-spacing: 1px; }
</style>
