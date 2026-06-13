<script>
  // Match-detail overlay — full scoreboard, draft (if present), and the
  // predictions panel (vote blue/red, accuracy after the fact).
  import { onMount, createEventDispatcher } from 'svelte'
  import { fly, fade } from 'svelte/transition'
  import { api, post, iconUrl } from '../api.js'
  import { identity } from '../identity.js'

  export let matchId
  export let sumToDisplay = {}

  const dispatch = createEventDispatcher()
  const close = () => dispatch('close')
  const onKey = e => { if (e.key === 'Escape') close() }

  let match = null
  let preds = []
  let loading = true
  let voting = false

  $: disp = s => sumToDisplay[s] ?? s
  $: me = $identity

  onMount(load)
  async function load() {
    loading = true
    try {
      match = await api(`/matches/${matchId}`, { ttl: 30_000 })
      preds = (await api(`/matches/${matchId}/predictions`, { ttl: 0 }))?.predictions ?? []
    } catch (e) { console.error(e) }
    loading = false
  }

  const team = side => (match?.participants ?? []).filter(p => p.team === side)
  const dur = s => `${Math.floor((s ?? 0) / 60)}:${String((s ?? 0) % 60).padStart(2, '0')}`
  const sum = (side, key) => team(side).reduce((a, p) => a + (p[key] ?? 0), 0)

  $: blueVotes = preds.filter(p => p.predicted === 'blue').length
  $: redVotes = preds.filter(p => p.predicted === 'red').length
  $: myVote = preds.find(p => p.voter === me)?.predicted ?? null
  $: totalVotes = preds.length
  $: correct = match?.winner ? preds.filter(p => p.predicted === match.winner).length : 0

  async function vote(side) {
    if (!me) return
    voting = true
    try {
      await post(`/matches/${matchId}/predictions`, { voter: me, predicted: side })
      preds = (await api(`/matches/${matchId}/predictions`, { ttl: 0 }))?.predictions ?? []
    } catch (e) { console.error(e) }
    voting = false
  }
</script>

<svelte:window on:keydown={onKey} />

<div class="veil" transition:fade={{ duration: 200 }} on:click|self={close} role="dialog">
  <div class="sheet glass" in:fly={{ y: 30, duration: 350 }}>
    <button class="x" on:click={close}>✕</button>

    {#if loading}
      <div class="loading mono dim">loading match…</div>
    {:else if match}
      <header class="mhead">
        <span class="mono dim">{(match.started_at ?? '').slice(0, 10)} · {dur(match.duration)} · {match.queue ?? 'CUSTOM'}</span>
        <span class="winner" class:blue={match.winner === 'blue'} class:red={match.winner === 'red'}>
          {(match.winner ?? '?').toUpperCase()} VICTORY</span>
      </header>

      {#each ['blue', 'red'] as side}
        <div class="teamblock" class:won={match.winner === side}>
          <div class="teamhead">
            <span class="sidetag" class:blue={side === 'blue'} class:red={side === 'red'}>
              {side.toUpperCase()} TEAM</span>
            <span class="kills mono">{sum(side, 'kills')} / {sum(side, 'deaths')} / {sum(side, 'assists')}</span>
            <span class="gold mono">{(sum(side, 'gold') / 1000).toFixed(1)}k gold</span>
          </div>
          <div class="scol head mono">
            <span></span><span>PLAYER</span><span>K/D/A</span><span>CS</span><span>DMG</span><span>GOLD</span>
          </div>
          {#each team(side) as p}
            <div class="scol">
              <img src={iconUrl(p.champion)} alt={p.champion} title={p.champion} />
              <span class="pn">{disp(p.player)}<i>{p.role ?? ''}</i></span>
              <span class="mono">{p.kills}/{p.deaths}/{p.assists}</span>
              <span class="mono dim">{p.cs ?? 0}</span>
              <span class="mono dim">{((p.damage ?? 0) / 1000).toFixed(1)}k</span>
              <span class="mono dim">{((p.gold ?? 0) / 1000).toFixed(1)}k</span>
            </div>
          {/each}
        </div>
      {/each}

      {#if match.draft && (match.draft.bans || match.draft.picks)}
        <div class="draft">
          <span class="kicker dim">DRAFT</span>
          <div class="mono dim2">draft data recorded</div>
        </div>
      {/if}

      <!-- Predictions -->
      <div class="preds">
        <header><span class="kicker">◆ PREDICTIONS</span><div class="rule-fade"></div></header>
        {#if totalVotes}
          <div class="ptally">
            <div class="pbar">
              <em class="blue" style="width:{(blueVotes / totalVotes) * 100}%"></em>
              <em class="red" style="width:{(redVotes / totalVotes) * 100}%"></em>
            </div>
            <span class="mono dim">{blueVotes} blue · {redVotes} red ·
              {#if match.winner}{correct}/{totalVotes} called it right{/if}</span>
          </div>
          <div class="voters">
            {#each preds as p}
              <span class="voter mono" class:hit={match.winner && p.predicted === match.winner}
                    class:miss={match.winner && p.predicted !== match.winner}>
                {disp(p.voter)} → {p.predicted}</span>
            {/each}
          </div>
        {:else}
          <p class="dim mono">No predictions on this match yet.</p>
        {/if}

        {#if me}
          <div class="voterow">
            <span class="mono dim">{myVote ? `you called ${myVote.toUpperCase()}` : 'your call:'}</span>
            <button class="vb blue" class:on={myVote === 'blue'} disabled={voting}
                    on:click={() => vote('blue')}>BLUE</button>
            <button class="vb red" class:on={myVote === 'red'} disabled={voting}
                    on:click={() => vote('red')}>RED</button>
          </div>
        {:else}
          <p class="dim mono">Set your identity (Tier List → detect) to cast a prediction.</p>
        {/if}
      </div>
    {:else}
      <div class="loading dim">match not found.</div>
    {/if}
  </div>
</div>

<style>
  .veil { position: fixed; inset: 0; z-index: 70; background: rgba(4,8,18,.8);
    backdrop-filter: blur(8px); display: flex; align-items: flex-start;
    justify-content: center; padding: 40px 20px; overflow-y: auto; }
  .sheet { position: relative; width: min(720px, 100%); padding: 24px 26px; }
  .x { position: absolute; top: 14px; right: 16px; background: none; border: none;
    color: var(--txt-dim); font-size: 18px; cursor: pointer; }
  .x:hover { color: var(--loss); }
  .loading { padding: 50px; text-align: center; }
  .mhead { display: flex; justify-content: space-between; align-items: baseline;
    margin-bottom: 16px; }
  .winner { font-family: var(--font-mono); font-size: 12px; letter-spacing: 2px; }
  .winner.blue { color: var(--blue-side); text-shadow: 0 0 10px rgba(89,179,212,.5); }
  .winner.red { color: var(--loss); text-shadow: 0 0 10px rgba(224,108,95,.5); }
  .teamblock { margin-bottom: 14px; padding: 10px 12px; border-radius: 10px;
    opacity: .72; border: 1px solid rgba(255,255,255,.05); }
  .teamblock.won { opacity: 1; background: rgba(255,255,255,.03);
    border-color: rgba(200,170,110,.2); }
  .teamhead { display: flex; gap: 16px; align-items: baseline; margin-bottom: 8px; }
  .sidetag { font-family: var(--font-mono); font-size: 11px; letter-spacing: 2px; }
  .sidetag.blue { color: var(--blue-side); } .sidetag.red { color: var(--loss); }
  .teamhead .kills { font-size: 12px; } .teamhead .gold { margin-left: auto;
    font-size: 11px; color: var(--txt-faint); }
  .scol { display: grid; grid-template-columns: 34px 1.4fr 70px 50px 60px 60px;
    align-items: center; gap: 10px; padding: 4px 6px; }
  .scol.head { font-size: 9px; letter-spacing: 1px; color: var(--txt-faint);
    padding-bottom: 2px; }
  .scol img { width: 30px; height: 30px; border-radius: 7px;
    border: 1px solid rgba(200,170,110,.3); }
  .pn { font-size: 13px; display: flex; flex-direction: column; min-width: 0; }
  .pn i { font-style: normal; font-size: 8px; color: var(--txt-faint);
    font-family: var(--font-mono); }
  .mono { font-family: var(--font-mono); font-size: 12px; }
  .dim { color: var(--txt-dim); } .dim2 { color: var(--txt-faint); }
  .draft { margin: 10px 0; padding: 8px 12px; border-radius: 8px;
    background: rgba(6,13,26,.5); }
  .preds { margin-top: 16px; }
  .preds header { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; }
  .ptally { margin-bottom: 8px; }
  .ptally .pbar { display: flex; height: 8px; border-radius: 4px; overflow: hidden;
    background: rgba(255,255,255,.06); margin-bottom: 5px; }
  .pbar em.blue { background: linear-gradient(90deg, #2c7da0, #59b3d4); }
  .pbar em.red { background: linear-gradient(90deg, var(--loss), #f0a090); }
  .voters { display: flex; flex-wrap: wrap; gap: 6px; }
  .voter { font-size: 10px; padding: 3px 9px; border-radius: 99px;
    border: 1px solid rgba(255,255,255,.1); color: var(--txt-dim); }
  .voter.hit { color: var(--win); border-color: rgba(110,190,140,.4); }
  .voter.miss { color: var(--loss); border-color: rgba(224,108,95,.3); opacity: .7; }
  .voterow { display: flex; align-items: center; gap: 10px; margin-top: 12px; }
  .vb { padding: 7px 18px; border-radius: 8px; cursor: pointer;
    background: rgba(255,255,255,.04); border: 1px solid rgba(255,255,255,.15);
    color: var(--txt-dim); font-family: var(--font-ui); font-weight: 700;
    letter-spacing: 2px; font-size: 12px; transition: all .2s; }
  .vb.blue:hover, .vb.blue.on { color: var(--blue-side);
    border-color: var(--blue-side); box-shadow: 0 0 14px rgba(89,179,212,.3); }
  .vb.red:hover, .vb.red.on { color: var(--loss);
    border-color: var(--loss); box-shadow: 0 0 14px rgba(224,108,95,.3); }
  .vb:disabled { opacity: .5; cursor: wait; }
</style>
