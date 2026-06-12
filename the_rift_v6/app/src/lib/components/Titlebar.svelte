<div class="bar glass">
  <span class="mark gold-sweep">THE RIFT</span>
  <span class="meta">CUSTOMS HQ · V6.0.0</span>
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
  .meta {
    margin-left: auto;
    font-family: var(--font-mono);
    font-size: 11px;
    letter-spacing: 2px;
    color: var(--txt-faint);
  }
  .edge { position: absolute; left: 0; right: 0; bottom: -1px; }
</style>
