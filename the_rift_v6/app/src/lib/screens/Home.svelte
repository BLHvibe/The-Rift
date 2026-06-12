<script>
  import { onMount } from 'svelte'
  import { tweened } from 'svelte/motion'
  import { cubicOut } from 'svelte/easing'
  import { fly, fade } from 'svelte/transition'
  import { api, splashUrl, iconUrl, leagueData } from '../api.js'

  const FALLBACK = ['Ahri', 'Jinx', 'Yasuo', 'Ezreal', 'Akali', 'Jhin', 'Sett', 'Thresh']
  let heroChamp = FALLBACK[new Date().getDate() % FALLBACK.length]
  let players = [], records = [], matches = [], byMatch = new Map()
  let sumToDisplay = {}
  let ready = false

  const kMatches = tweened(0, { duration: 1600, easing: cubicOut })
  const kPlayers = tweened(0, { duration: 1600, easing: cubicOut })

  // Mouse parallax
  let mx = 0, my = 0
  const onMove = e => {
    mx = (e.clientX / window.innerWidth - 0.5)
    my = (e.clientY / window.innerHeight - 0.5)
  }

  onMount(async () => {
    window.addEventListener('mousemove', onMove)
    try { const s = await api('/stats'); kMatches.set(s?.matches ?? 0); kPlayers.set(s?.participants ?? 0) } catch {}
    try {
      const d = await leagueData()
      matches = d.matches.slice(0, 5)
      byMatch = d.byMatch
      sumToDisplay = d.sumToDisplay
      const winners = (byMatch.get(matches[0]?.id) ?? [])
        .filter(p => p.win).map(p => p.champion).filter(Boolean)
      if (winners.length) heroChamp = winners[new Date().getDate() % winners.length]
    } catch (e) { console.error('leagueData', e) }
    try {
      // Power rankings = the real ladder (same list as the Rankings tab).
      const r = await api('/rankings')
      players = (r?.rankings ?? []).slice(0, 10)
    } catch (e) { console.error('rankings', e) }
    try {
      const r = await api('/records')
      records = Object.entries(r?.records ?? {}).slice(0, 5)
    } catch {}
    ready = true
    return () => window.removeEventListener('mousemove', onMove)
  })

  const faces = m => (byMatch.get(m.id) ?? []).slice(0, 10)
  const disp = s => sumToDisplay[s] ?? s
</script>

<div class="home">
  <!-- ── CINEMATIC HERO ─────────────────────────────────────────────── -->
  <section class="hero">
    <div class="splash"
         style="background-image:url({splashUrl(heroChamp)});
                transform: scale(1.12) translate({mx * -22}px, {my * -14}px)"></div>
    <div class="rays" style="transform: translate({mx * 12}px, 0)"></div>
    <div class="scrim"></div>
    <div class="hero-content">
      <div class="kick" in:fade={{ duration: 800, delay: 200 }}>
        {new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' }).toUpperCase()}
      </div>
      <h1 class="gold-sweep" style="transform: translate({mx * -10}px, {my * -5}px)">THE RIFT</h1>
      <div class="sub">EVERY GAME · EVERY RECORD · EVERY RIVALRY</div>
      <div class="chips">
        <div class="chip glass" in:fly={{ y: 24, duration: 600, delay: 300 }}>
          <b>{Math.round($kMatches).toLocaleString()}</b><span>MATCHES</span>
        </div>
        <div class="chip glass" in:fly={{ y: 24, duration: 600, delay: 420 }}>
          <b>{Math.round($kPlayers).toLocaleString()}</b><span>PARTICIPANTS</span>
        </div>
        <div class="chip glass" in:fly={{ y: 24, duration: 600, delay: 540 }}>
          <b class="live">●</b><span>LIVE DATA</span>
        </div>
      </div>
    </div>
    <div class="flow-line hero-edge"></div>
  </section>

  {#if ready}
  <div class="grid">
    <!-- ── POWER RANKINGS ─────────────────────────────────────────── -->
    <section class="glass card" in:fly={{ y: 30, duration: 600, delay: 100 }}>
      <header><span class="kicker">◆ POWER RANKINGS</span><div class="rule-fade"></div></header>
      {#each players as p, i (p.name)}
        <div class="row" in:fly={{ x: -24, duration: 450, delay: 150 + i * 60 }}>
          <span class="rank" class:medal={i < 3} data-m={i}>{p.rank ?? i + 1}</span>
          <span class="name">{p.name.toUpperCase()}</span>
          <div class="bar"><div class="fill" style="width:{Math.min(100, +p.score)}%"></div></div>
          <span class="stat gold-text">{Math.round(+p.score)}</span>
          <span class="gp">{p.tier ?? ''}</span>
        </div>
      {:else}
        <div class="empty">awaiting league data…</div>
      {/each}
    </section>

    <div class="col">
      <!-- ── RECORD BOOK ──────────────────────────────────────────── -->
      <section class="glass card" in:fly={{ y: 30, duration: 600, delay: 220 }}>
        <header><span class="kicker">◆ RECORD BOOK</span><div class="rule-fade"></div></header>
        {#each records as [key, rec], i}
          <div class="rec" in:fade={{ duration: 500, delay: 300 + i * 80 }}>
            <span class="rkey">{key.replace(/_/g, ' ').toUpperCase()}</span>
            <b class="gold-text">{(rec?.value ?? 0).toLocaleString()}</b>
            <span class="rwho">{disp(rec?.player)} · {rec?.champion ?? ''}</span>
          </div>
        {:else}
          <div class="empty">no records yet</div>
        {/each}
      </section>

      <!-- ── RECENT MATCHES ───────────────────────────────────────── -->
      <section class="glass card" in:fly={{ y: 30, duration: 600, delay: 340 }}>
        <header><span class="kicker">◆ RECENT GAMES</span><div class="rule-fade"></div></header>
        {#each matches as m, i}
          <div class="match" in:fade={{ duration: 500, delay: 380 + i * 80 }}>
            <span class="side" class:blue={m.winner === 'blue'} class:red={m.winner === 'red'}>
              {(m.winner ?? '?').toUpperCase()} WIN
            </span>
            <div class="faces">
              {#each faces(m) as pt}
                <img src={iconUrl(pt.champion)} alt={pt.champion}
                     class:won={pt.win} loading="lazy"
                     title="{disp(pt.player)} · {pt.champion} · {pt.kills}/{pt.deaths}/{pt.assists}" />
              {/each}
            </div>
            <span class="when">{(m.started_at ?? '').slice(5, 10)}</span>
          </div>
        {:else}
          <div class="empty">no games logged yet</div>
        {/each}
      </section>
    </div>
  </div>
  {/if}
</div>

<style>
  .home { height: 100%; overflow-y: auto; padding: 0 26px 26px; }

  .hero {
    position: relative;
    height: 340px;
    margin: 0 -26px;
    overflow: hidden;
  }
  .splash {
    position: absolute; inset: -40px;
    background-size: cover; background-position: center 22%;
    animation: kenburns 36s ease-in-out infinite alternate;
    transition: transform .35s cubic-bezier(.2,.8,.2,1);
    will-change: transform;
  }
  @keyframes kenburns {
    from { background-position: 46% 18%; }
    to   { background-position: 54% 30%; }
  }
  .rays {
    position: absolute; inset: 0;
    background: conic-gradient(from 230deg at 70% -10%,
      transparent 0deg, rgba(232,213,163,.10) 8deg, transparent 16deg,
      rgba(232,213,163,.06) 24deg, transparent 34deg,
      rgba(232,213,163,.08) 44deg, transparent 56deg);
    mix-blend-mode: screen;
    animation: raydrift 14s ease-in-out infinite alternate;
  }
  @keyframes raydrift { from { opacity: .7 } to { opacity: 1 } }
  .scrim {
    position: absolute; inset: 0;
    background:
      linear-gradient(180deg, rgba(6,13,26,.55) 0%, transparent 30%, rgba(6,13,26,.92) 88%),
      linear-gradient(90deg, rgba(6,13,26,.88) 0%, rgba(6,13,26,.3) 42%, transparent 65%);
  }
  .hero-content { position: absolute; left: 34px; bottom: 30px; z-index: 2; }
  .kick {
    font-family: var(--font-mono); font-size: 12px;
    letter-spacing: 4px; color: var(--gold);
    text-shadow: 0 0 12px rgba(200,170,110,.6);
    margin-bottom: 8px;
  }
  h1 {
    font-family: var(--font-display);
    font-size: 58px; letter-spacing: 8px; line-height: 1;
    transition: transform .35s cubic-bezier(.2,.8,.2,1);
  }
  .sub {
    margin-top: 10px;
    font-family: var(--font-mono); font-size: 11px;
    letter-spacing: 3px; color: var(--txt-dim);
  }
  .chips { display: flex; gap: 14px; margin-top: 22px; }
  .chip {
    padding: 12px 22px;
    display: flex; flex-direction: column; align-items: center; gap: 2px;
  }
  .chip b { font-size: 26px; font-weight: 700; color: var(--gold-lt);
            text-shadow: 0 0 16px rgba(200,170,110,.5); }
  .chip span { font-family: var(--font-mono); font-size: 10px;
               letter-spacing: 2px; color: var(--txt-dim); }
  .chip .live { color: var(--win); animation: pulse 2.2s ease-in-out infinite; }
  @keyframes pulse { 50% { opacity: .35; text-shadow: 0 0 18px var(--win); } }
  .hero-edge { position: absolute; left: 0; right: 0; bottom: 0; }

  .grid {
    display: grid; grid-template-columns: 1.4fr 1fr;
    gap: 18px; margin-top: 22px;
  }
  .col { display: flex; flex-direction: column; gap: 18px; }
  .card { padding: 18px 20px; }
  header { display: flex; align-items: center; gap: 14px; margin-bottom: 14px; }

  .row {
    display: grid;
    grid-template-columns: 34px 1fr 130px 52px 64px;
    align-items: center; gap: 12px;
    padding: 9px 10px;
    border-radius: 8px;
    transition: background .2s, transform .2s;
  }
  .row:hover { background: rgba(200,170,110,.07); transform: translateX(4px); }
  .rank { font-family: var(--font-mono); color: var(--txt-faint); font-size: 14px; }
  .rank.medal[data-m="0"] { color: #ffd700; text-shadow: 0 0 12px #ffd700aa; }
  .rank.medal[data-m="1"] { color: #e8e8e8; text-shadow: 0 0 12px #e8e8e8aa; }
  .rank.medal[data-m="2"] { color: #cd7f32; text-shadow: 0 0 12px #cd7f32aa; }
  .name { font-weight: 700; font-size: 17px; letter-spacing: 1px; }
  .bar { height: 5px; border-radius: 3px; background: rgba(255,255,255,.06); overflow: hidden; }
  .fill {
    height: 100%; border-radius: 3px;
    background: linear-gradient(90deg, var(--gold-dk), var(--gold), var(--gold-hot));
    box-shadow: 0 0 10px rgba(200,170,110,.6);
    transition: width 1.2s cubic-bezier(.2,.8,.2,1);
  }
  .stat { font-weight: 700; text-align: right; }
  .stat.up { color: var(--win); } .stat.down { color: var(--loss); }
  .gp { font-family: var(--font-mono); font-size: 12px; color: var(--txt-dim); text-align: right; }

  .rec { display: flex; align-items: baseline; gap: 12px; padding: 8px 6px; }
  .rkey { font-family: var(--font-mono); font-size: 10px; letter-spacing: 1.5px;
          color: var(--txt-faint); flex: 1; }
  .rec b { font-size: 20px; font-weight: 700; }
  .rwho { font-size: 13px; color: var(--txt-dim); }

  .match { display: flex; align-items: center; gap: 12px; padding: 8px 6px; }
  .side { font-family: var(--font-mono); font-size: 10px; letter-spacing: 1px;
          width: 74px; color: var(--txt-faint); }
  .side.blue { color: var(--blue-side); } .side.red { color: var(--loss); }
  .faces { display: flex; gap: 3px; flex: 1; }
  .faces img {
    width: 26px; height: 26px; border-radius: 6px;
    border: 1px solid rgba(200,170,110,.25);
    opacity: .55;
    transition: transform .18s;
  }
  .faces img.won { opacity: 1; border-color: rgba(110,190,140,.6);
                   box-shadow: 0 0 8px rgba(110,190,140,.25); }
  .faces img:hover { transform: scale(1.6); z-index: 2; }
  .when { font-family: var(--font-mono); font-size: 11px; color: var(--txt-faint); }

  .empty { color: var(--txt-faint); font-size: 14px; padding: 12px 6px; }
</style>
