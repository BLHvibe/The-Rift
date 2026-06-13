<script>
  // War room orchestrator — renders the active draft phase.
  // Phase machine lives in lib/draft/store.js (server-authoritative when
  // synced, local in solo). See the_rift_v6/PROTOCOLS.md for the contracts.
  import { draft } from '../draft/store.js'
  import Idle from './draft/Idle.svelte'
  import Lobby from './draft/Lobby.svelte'
  import Scouting from './draft/Scouting.svelte'
  import Briefing from './draft/Briefing.svelte'
  import Archetype from './draft/Archetype.svelte'
  import Board from './draft/Board.svelte'
  import Done from './draft/Done.svelte'

  $: mode = $draft.mode
  $: phase = $draft.state.phase
</script>

{#if mode === 'idle' || mode === 'connecting'}
  <Idle />
{:else if phase === 'LOBBY'}
  <Lobby />
{:else if phase === 'SCOUTING'}
  <Scouting />
{:else if phase === 'BRIEFING'}
  <Briefing />
{:else if phase === 'ARCHETYPE'}
  <Archetype />
{:else if phase === 'DONE'}
  <Done />
{:else}
  <Board />
{/if}
