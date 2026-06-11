<script>
  export let label = 'COMING'
</script>

<div class="stub">
  <div class="frame glass">
    <div class="hex">⬡</div>
    <h2 class="gold-text">{label}</h2>
    <p>This surface is being reforged for v6.</p>
  </div>
</div>

<style>
  .stub { height: 100%; display: grid; place-items: center; }
  .frame {
    padding: 60px 90px; text-align: center;
    animation: rise .6s cubic-bezier(.2,.8,.2,1);
  }
  @keyframes rise { from { opacity: 0; transform: translateY(26px); } }
  .hex { font-size: 44px; color: var(--gold); opacity: .5;
         animation: spin 14s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  h2 { font-family: var(--font-display); font-size: 30px; letter-spacing: 6px; margin: 14px 0 8px; }
  p { color: var(--txt-dim); font-size: 15px; }
</style>
