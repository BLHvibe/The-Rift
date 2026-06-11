<script>
  import { screen, TABS } from './lib/stores.js'
  import BackgroundFX from './lib/components/BackgroundFX.svelte'
  import HexDissolve from './lib/components/HexDissolve.svelte'
  import Titlebar from './lib/components/Titlebar.svelte'
  import Sidebar from './lib/components/Sidebar.svelte'
  import Ticker from './lib/components/Ticker.svelte'
  import Home from './lib/screens/Home.svelte'
  import Stub from './lib/screens/Stub.svelte'
</script>

<BackgroundFX />
<HexDissolve />

<div class="shell">
  <Titlebar />
  <div class="mid">
    <Sidebar />
    <main>
      {#if $screen === 'home'}
        <Home />
      {:else}
        <Stub label={TABS.find(t => t.id === $screen)?.label ?? ''} />
      {/if}
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
