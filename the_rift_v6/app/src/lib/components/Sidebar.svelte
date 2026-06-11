<script>
  import { screen, navigate, TABS } from '../stores.js'
</script>

<nav class="glass">
  {#each TABS as t}
    <button class:active={$screen === t.id} on:click={() => navigate(t.id)}>
      <span class="dot"></span>
      <span class="lbl">{t.label}</span>
    </button>
  {/each}
</nav>

<style>
  nav {
    width: 188px;
    display: flex; flex-direction: column; gap: 4px;
    padding: 18px 10px;
    border-radius: 0;
    border-top: none; border-bottom: none; border-left: none;
    z-index: 10;
  }
  button {
    position: relative;
    display: flex; align-items: center; gap: 12px;
    padding: 13px 14px;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 9px;
    color: var(--txt-dim);
    font-family: var(--font-ui);
    font-size: 15px; font-weight: 600;
    letter-spacing: 2.5px;
    cursor: pointer;
    transition: all .25s cubic-bezier(.2,.8,.2,1);
  }
  button:hover {
    color: var(--txt);
    background: rgba(200,170,110,.06);
    transform: translateX(3px);
  }
  .dot {
    width: 7px; height: 7px;
    background: var(--txt-faint);
    transform: rotate(45deg);
    transition: all .3s;
  }
  button.active {
    color: var(--gold-lt);
    background: linear-gradient(90deg, rgba(200,170,110,.16), rgba(200,170,110,.03));
    border-color: rgba(200,170,110,.35);
    box-shadow: 0 0 24px rgba(200,170,110,.16), inset 0 0 18px rgba(200,170,110,.05);
  }
  button.active .dot {
    background: var(--gold-hot);
    box-shadow: 0 0 10px var(--gold);
  }
</style>
