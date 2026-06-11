<div class="wrap">
  <div class="frame glass">
    <div class="hexes">⬡ ⬡ ⬡</div>
    <h2 class="gold-sweep">WAR ROOM</h2>
    <p>The draft tool — engine, board, and live sync — still runs on
       <b>The Rift v5</b> while it's ported with surgical care.</p>
    <p class="mono">It ports last, and only after a full draft night passes on v6.</p>
  </div>
</div>

<style>
  .wrap { height: 100%; display: grid; place-items: center; }
  .frame { padding: 56px 80px; text-align: center; max-width: 560px;
           animation: rise .6s cubic-bezier(.2,.8,.2,1); }
  @keyframes rise { from { opacity: 0; transform: translateY(26px); } }
  .hexes { font-size: 30px; color: var(--gold); opacity: .5; letter-spacing: 14px;
           animation: breathe 4s ease-in-out infinite; }
  @keyframes breathe { 50% { opacity: .9; text-shadow: 0 0 18px var(--gold); } }
  h2 { font-family: var(--font-display); font-size: 32px; letter-spacing: 7px; margin: 14px 0 14px; }
  p { color: var(--txt-dim); font-size: 15px; line-height: 1.6; }
  p b { color: var(--gold-lt); }
  .mono { font-family: var(--font-mono); font-size: 11px; margin-top: 10px; color: var(--txt-faint); }
</style>
