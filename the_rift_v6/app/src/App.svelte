<script>
  import { screen } from './lib/stores.js'
  import BackgroundFX from './lib/components/BackgroundFX.svelte'
  import HexDissolve from './lib/components/HexDissolve.svelte'
  import Titlebar from './lib/components/Titlebar.svelte'
  import Sidebar from './lib/components/Sidebar.svelte'
  import Ticker from './lib/components/Ticker.svelte'
  import Home from './lib/screens/Home.svelte'
  import Rankings from './lib/screens/Rankings.svelte'
  import Inhouse from './lib/screens/Inhouse.svelte'
  import Scout from './lib/screens/Scout.svelte'
  import Feed from './lib/screens/Feed.svelte'
  import Tierlist from './lib/screens/Tierlist.svelte'
  import Draft from './lib/screens/Draft.svelte'
  import Settings from './lib/screens/Settings.svelte'

  const SCREENS = {
    home: Home, rankings: Rankings, inhouse: Inhouse, scout: Scout,
    feed: Feed, tierlist: Tierlist, draft: Draft, settings: Settings,
  }
</script>

<BackgroundFX />
<HexDissolve />

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
