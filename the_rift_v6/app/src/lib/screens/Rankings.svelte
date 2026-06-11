<script>
  import { onMount } from 'svelte'
  import { fly, fade, scale } from 'svelte/transition'
  import { backOut } from 'svelte/easing'
  import { api, splashUrl } from '../api.js'

  const TIER_COLORS = {
    Challenger: '#f0c882', Grandmaster: '#dc6e5a', Master: '#af6edc',
    Diamond: '#82afdc', Emerald: '#6ec88c', Platinum: '#82b4af',
    Gold: '#c8aa6e', Silver: '#aaaaaf', Bronze: '#af6e46',
    Iron: '#6e5f55', Unranked: '#505a69',
  }
  let rows = [], champs = {}
  let ready = false

  onMount(async () => {
    try {
      const [r, s] = await Promise.all([api('/rankings'), api('/scout')])
      rows = r?.rankings ?? []
      for (const p of (s?.scout ?? [])) champs[p.name] = p.top_champs?.[0]
    } catch (e) { console.error(e) }
    ready = true
  })

  const tc = t => TIER_COLORS[t] ?? TIER_COLORS.Unranked
  $: podium = rows.slice(0, 3)
  $: rest = rows.slice(3)
  const order = [1, 0, 2]   // visual: #2 left, #1 center, #3 right
</script>

<div class="wrap">
  {#if ready && podium.length === 3}
    <div class="podium">
      {#each order as oi, slot}
        {@const p = podium[oi]}
        <div class="card glass" class:champ={oi === 0}
             in:scale={{ duration: 700, delay: oi === 0 ? 200 : 500 + slot * 160, easing: backOut, start: .8 }}>
          {#if champs[p.name]}
            <div class="bg" style="background-image:url({splashUrl(champs[p.name])})"></div>
          {/if}
          <div class="veil"></div>
          <div class="inner">
            <span class="no" class:gold={oi===0} class:silver={oi===1} class:bronze={oi===2}>{p.rank}</span>
            <h2 class={oi === 0 ? 'gold-sweep' : 'gold-text'}>{p.name.toUpperCase()}</h2>
            <div class="tier" style="color:{tc(p.tier)}; text-shadow:0 0 14px {tc(p.tier)}66">
              {p.tier.toUpperCase()} {p.division ?? ''} · {p.lp ?? 0} LP
            </div>
            <div class="score"><b>{Math.round(+p.score)}</b><span>SCORE</span></div>
            <div class="line">
              <span>{p.wins}W–{p.losses}L</span>
              <span class:up={p.wr >= 52} class:down={p.wr < 48}>{p.wr}%</span>
              <span class="rating">{p.rating}</span>
            </div>
          </div>
          {#if oi === 0}<div class="flow-line crownline"></div>{/if}
        </div>
      {/each}
    </div>

    <section class="glass table">
      <header><span class="kicker">◆ FULL STANDINGS</span><div class="rule-fade"></div></header>
      {#each rest as p, i (p.name)}
        <div class="row" in:fly={{ x: -30, duration: 420, delay: 900 + i * 55 }}>
          <span class="rk">#{p.rank}</span>
          <span class="dot" style="background:{tc(p.tier)}; box-shadow:0 0 10px {tc(p.tier)}"></span>
          <span class="nm">{p.name.toUpperCase()}</span>
          <span class="tr" style="color:{tc(p.tier)}">{p.tier} {p.division ?? ''}</span>
          <div class="bar"><div class="fill" style="width:{Math.min(100, +p.score)}%"></div></div>
          <span class="sc gold-text">{Math.round(+p.score)}</span>
          <span class="wl">{p.wins}–{p.losses}</span>
          <span class="wr" class:up={p.wr >= 52} class:down={p.wr < 48}>{p.wr}%</span>
        </div>
      {/each}
    </section>
  {:else if ready}
    <div class="empty glass">No ranking data yet.</div>
  {/if}
</div>

<style>
  .wrap { height: 100%; overflow-y: auto; padding: 26px; }
  .podium {
    display: grid; grid-template-columns: 1fr 1.25fr 1fr;
    gap: 18px; align-items: end;
    margin-bottom: 22px;
  }
  .card { position: relative; overflow: hidden; height: 240px; }
  .card.champ { height: 290px; box-shadow: 0 24px 60px rgba(0,0,0,.5), 0 0 50px rgba(200,170,110,.18); }
  .bg {
    position: absolute; inset: -20px;
    background-size: cover; background-position: center 20%;
    animation: slowpan 30s ease-in-out infinite alternate;
  }
  @keyframes slowpan { from { transform: scale(1.06) } to { transform: scale(1.14) } }
  .veil { position: absolute; inset: 0;
          background: linear-gradient(180deg, rgba(6,13,26,.45), rgba(6,13,26,.93) 82%); }
  .inner { position: absolute; inset: 18px; display: flex; flex-direction: column; justify-content: flex-end; }
  .no { position: absolute; top: -6px; right: 4px; font-family: var(--font-display);
        font-size: 64px; opacity: .9; }
  .no.gold   { color: #ffd700; text-shadow: 0 0 28px #ffd700aa; }
  .no.silver { color: #e6e6e6; text-shadow: 0 0 22px #e6e6e688; }
  .no.bronze { color: #cd7f32; text-shadow: 0 0 22px #cd7f3288; }
  h2 { font-family: var(--font-display); font-size: 26px; letter-spacing: 2px; }
  .tier { font-family: var(--font-mono); font-size: 11px; letter-spacing: 2px; margin: 6px 0 10px; }
  .score b { font-size: 38px; font-weight: 700; color: var(--gold-lt);
             text-shadow: 0 0 22px rgba(200,170,110,.55); }
  .score span { font-family: var(--font-mono); font-size: 10px; letter-spacing: 2px;
                color: var(--txt-faint); margin-left: 8px; }
  .line { display: flex; gap: 16px; margin-top: 6px;
          font-family: var(--font-mono); font-size: 12px; color: var(--txt-dim); }
  .rating { color: var(--gold); font-weight: 700; }
  .crownline { position: absolute; left: 0; right: 0; bottom: 0; }

  .table { padding: 18px 20px; }
  header { display: flex; align-items: center; gap: 14px; margin-bottom: 12px; }
  .row {
    display: grid;
    grid-template-columns: 44px 14px 1fr 130px 1fr 56px 70px 52px;
    align-items: center; gap: 12px;
    padding: 9px 10px; border-radius: 8px;
    transition: background .2s, transform .2s;
  }
  .row:hover { background: rgba(200,170,110,.07); transform: translateX(4px); }
  .rk { font-family: var(--font-mono); color: var(--txt-faint); font-size: 13px; }
  .dot { width: 9px; height: 9px; border-radius: 50%; }
  .nm { font-weight: 700; font-size: 16px; letter-spacing: 1px; }
  .tr { font-family: var(--font-mono); font-size: 11px; letter-spacing: 1px; }
  .bar { height: 5px; border-radius: 3px; background: rgba(255,255,255,.06); overflow: hidden; }
  .fill { height: 100%; background: linear-gradient(90deg, var(--gold-dk), var(--gold), var(--gold-hot));
          box-shadow: 0 0 10px rgba(200,170,110,.6); }
  .sc { font-size: 18px; font-weight: 700; text-align: right; }
  .wl { font-family: var(--font-mono); font-size: 12px; color: var(--txt-dim); text-align: right; }
  .wr { font-weight: 700; text-align: right; }
  .up { color: var(--win); } .down { color: var(--loss); }
  .empty { padding: 40px; text-align: center; color: var(--txt-dim); }
</style>
