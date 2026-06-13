<script>
  import { screen, navigate, TABS } from './lib/stores.js'
  import BackgroundFX from './lib/components/BackgroundFX.svelte'
  import HexDissolve from './lib/components/HexDissolve.svelte'
  import Titlebar from './lib/components/Titlebar.svelte'
  import Sidebar from './lib/components/Sidebar.svelte'
  import Ticker from './lib/components/Ticker.svelte'
  import Hotkeys from './lib/components/Hotkeys.svelte'
  import Home from './lib/screens/Home.svelte'
  import Rankings from './lib/screens/Rankings.svelte'
  import Inhouse from './lib/screens/Inhouse.svelte'
  import Scout from './lib/screens/Scout.svelte'
  import Feed from './lib/screens/Feed.svelte'
  import Tierlist from './lib/screens/Tierlist.svelte'
  import Draft from './lib/screens/Draft.svelte'
  import Commands from './lib/screens/Commands.svelte'
  import Settings from './lib/screens/Settings.svelte'

  const SCREENS = {
    home: Home, rankings: Rankings, inhouse: Inhouse, scout: Scout,
    feed: Feed, tierlist: Tierlist, draft: Draft, commands: Commands,
    settings: Settings,
  }

  let showHotkeys = false

  // Global keyboard: 1-9 tabs, ? hotkeys card, Esc closes it. Ignored while
  // typing in an input/textarea so search boxes keep working.
  function onKey(e) {
    const el = document.activeElement
    const typing = el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA'
      || el.isContentEditable)
    if (typing) return
    if (e.key === '?' || (e.key === '/' && e.shiftKey) || e.key === 'F1') {
      e.preventDefault(); showHotkeys = !showHotkeys; return
    }
    if (e.key === 'Escape') { if (showHotkeys) showHotkeys = false; return }
    if (e.key >= '1' && e.key <= '9') {
      const tab = TABS[+e.key - 1]
      if (tab && tab.id !== $screen) navigate(tab.id)
    }
  }
</script>

<svelte:window on:keydown={onKey} />

<BackgroundFX />
<HexDissolve />

{#if showHotkeys}<Hotkeys on:close={() => showHotkeys = false} />{/if}

<div class="shell">
  <Titlebar />
  <div class="mid">
    <Sidebar />
    <main>
      <svelte:component this={SCREENS[$screen] ?? Home} />
    </main>
  </div>
  <Ticker />
</div>

<style>
  .shell {
    position: relative; z-index: 1;
    height: 100%;
    display: flex; flex-direction: column;
  }
  .mid { flex: 1; display: flex; min-height: 0; }
  main { flex: 1; min-width: 0; position: relative; }
</style>
