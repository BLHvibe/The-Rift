<script>
  import { fly, fade } from 'svelte/transition'
  import { splashUrl } from '../../api.js'
  import { identity, setIdentity } from '../../identity.js'
  import { draft, connect, beginSolo } from '../../draft/store.js'

  // Daily rotating hero — same roster as v5's idle screen.
  const HEROES = ['Aatrox', 'Yone', 'Akali', 'Sett', 'Jhin', 'Vayne', 'Ahri',
    'Camille', 'Lee Sin', 'Riven', 'Irelia', 'Ekko', 'Ezreal', 'Sylas']
  const hero = HEROES[Math.floor(Date.now() / 86_400_000) % HEROES.length]

  let name = $identity
  $: connecting = $draft.mode === 'connecting'

  function begin() {
    if (!name.trim()) return
    setIdentity(name.trim())
    connect(name.trim())
  }
  function solo() {
    if (name.trim()) setIdentity(name.trim())
    beginSolo(name.trim() || 'captain')
  }
</script>

<div class="idle">
  <div class="splash" style="background-image:url({splashUrl(hero)})"></div>
  <div class="scrim"></div>

  <div class="center" in:fly={{ y: 30, duration: 600 }}>
    <span class="kicker">◆ THE WAR ROOM</span>
    <h1 class="gold-sweep">DRAFT NIGHT</h1>
    <p class="sub">Live tournament draft against the other captain —
      scouting, briefing, win conditions, and the engine on every pick.</p>

    <input class="name" placeholder="your name…" bind:value={name}
           maxlength="24" on:keydown={e => e.key === 'Enter' && begin()} />

    <div class="btns">
      <button class="primary" disabled={connecting || !name.trim()} on:click={begin}>
        {connecting ? 'CONNECTING…' : '⬡ ENTER THE WAR ROOM'}
      </button>
      <button class="ghost" on:click={solo}>SOLO BOARD</button>
    </div>

    {#if $draft.connError}
      <div class="err" transition:fade>{$draft.connError}</div>
    {/if}
    <span class="hint mono">everyone joins the same room · first two claims captain the sides ·
      the rest spectate</span>
  </div>
</div>

<style>
  .idle { position: relative; height: 100%; overflow: hidden;
          display: grid; place-items: center; }
  .splash { position: absolute; inset: 0; background-size: cover;
            background-position: center 18%; opacity: .35;
            animation: kb 26s ease-in-out infinite alternate; }
  @keyframes kb { from { transform: scale(1.04) translateY(0); }
                  to   { transform: scale(1.12) translateY(-14px); } }
  .scrim { position: absolute; inset: 0;
           background: radial-gradient(ellipse at 50% 42%,
             rgba(4,9,20,.25), rgba(4,9,20,.88) 75%); }
  .center { position: relative; display: flex; flex-direction: column;
            align-items: center; gap: 14px; text-align: center;
            max-width: 560px; padding: 30px; }
  h1 { font-family: var(--font-display); font-size: 54px; letter-spacing: 10px; }
  .sub { color: var(--txt-dim); font-size: 14px; line-height: 1.6; }
  .name { background: rgba(6,13,26,.8); border: 1px solid rgba(200,170,110,.4);
          border-radius: 10px; padding: 12px 18px; color: var(--txt);
          font-family: var(--font-ui); font-size: 16px; letter-spacing: 1px;
          text-align: center; width: 280px; outline: none; }
  .name:focus { border-color: var(--gold); box-shadow: 0 0 18px rgba(200,170,110,.25); }
  .btns { display: flex; gap: 12px; margin-top: 6px; }
  .primary { padding: 13px 26px; border-radius: 10px; cursor: pointer;
    background: linear-gradient(180deg, rgba(200,170,110,.3), rgba(120,90,40,.2));
    border: 1px solid rgba(200,170,110,.6); color: var(--gold-lt);
    font-family: var(--font-ui); font-weight: 700; letter-spacing: 2.5px;
    font-size: 14px; transition: all .25s; }
  .primary:hover:not(:disabled) { border-color: var(--gold-hot);
    box-shadow: 0 0 28px rgba(200,170,110,.4); transform: translateY(-2px); }
  .primary:disabled { opacity: .5; cursor: default; }
  .ghost { padding: 13px 22px; border-radius: 10px; cursor: pointer;
    background: rgba(255,255,255,.04); border: 1px solid rgba(200,170,110,.25);
    color: var(--txt-dim); font-family: var(--font-ui); font-weight: 700;
    letter-spacing: 2px; font-size: 12px; transition: all .2s; }
  .ghost:hover { color: var(--gold-lt); border-color: var(--gold); }
  .err { color: var(--loss); font-size: 13px; font-family: var(--font-mono); }
  .hint { font-size: 10px; color: var(--txt-faint); margin-top: 8px; }
  .mono { font-family: var(--font-mono); }
</style>
