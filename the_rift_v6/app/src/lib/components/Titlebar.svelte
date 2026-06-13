<script>
  import { onMount } from 'svelte'
  import { fade } from 'svelte/transition'

  export const VERSION = 'V6.3.0'
  let update = null   // {tag, url} when a newer v6 release exists

  onMount(async () => {
    // Sidecar-only — silently no-ops in the browser (no /local proxy target).
    try {
      const r = await fetch(`/local/update-check?current=${VERSION}`).then(r => r.json())
      if (r?.ok && r.update) update = r.latest
    } catch {}
  })
</script>

<div class="bar glass">
  <span class="mark gold-sweep">THE RIFT</span>
  {#if update}
    <a class="update" href={update.url} target="_blank" rel="noopener"
       transition:fade title="A newer build is available on GitHub">
      ⬡ UPDATE {update.tag}</a>
  {/if}
  <span class="meta">CUSTOMS HQ · {VERSION}</span>
  <div class="flow-line edge"></div>
</div>

<style>
  .bar {
    position: relative;
    height: 54px;
    display: flex; align-items: center; gap: 18px;
    padding: 0 22px;
    border-radius: 0;
    border-left: none; border-right: none; border-top: none;
    z-index: 10;
  }
  .mark {
    font-family: var(--font-display);
    font-size: 21px;
    letter-spacing: 5px;
  }
  .update {
    margin-left: auto;
    font-family: var(--font-mono); font-size: 10px; letter-spacing: 1.5px;
    color: var(--gold-lt); text-decoration: none;
    padding: 4px 12px; border-radius: 99px;
    border: 1px solid rgba(200,170,110,.5);
    background: rgba(200,170,110,.1);
    animation: upglow 2.4s ease-in-out infinite;
  }
  @keyframes upglow {
    0%, 100% { box-shadow: 0 0 8px rgba(200,170,110,.2); }
    50% { box-shadow: 0 0 18px rgba(200,170,110,.45); }
  }
  .update:hover { border-color: var(--gold-hot); }
  .meta {
    margin-left: auto;
    font-family: var(--font-mono);
    font-size: 11px;
    letter-spacing: 2px;
    color: var(--txt-faint);
  }
  .update + .meta { margin-left: 0; }
  .edge { position: absolute; left: 0; right: 0; bottom: -1px; }
</style>
