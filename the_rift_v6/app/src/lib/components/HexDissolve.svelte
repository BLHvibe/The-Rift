<script>
  // Hextech dissolve — the v5 transition reborn with real glow. A honeycomb
  // veil sweeps across on every navigation, gold-flashing as it shatters.
  import { dissolveSignal, motion } from '../stores.js'
  import { onMount } from 'svelte'
  let inten = 1
  motion.subscribe(v => inten = v)
  let canvas
  let ctx, w, h, dpr, start = -1

  const DUR = 520

  onMount(() => {
    ctx = canvas.getContext('2d')
    const resize = () => {
      dpr = Math.min(2, window.devicePixelRatio || 1)
      w = canvas.clientWidth; h = canvas.clientHeight
      canvas.width = w * dpr; canvas.height = h * dpr
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    }
    resize()
    window.addEventListener('resize', resize)
    const unsub = dissolveSignal.subscribe(n => { if (n > 0) trigger() })
    return () => { unsub(); window.removeEventListener('resize', resize) }
  })

  function trigger() {
    if (inten <= 0.01) return        // motion off → instant cut
    start = performance.now()
    canvas.style.opacity = '1'
    requestAnimationFrame(frame)
  }

  function hexPath(cx, cy, r) {
    ctx.beginPath()
    for (let i = 0; i < 6; i++) {
      const ang = (Math.PI / 3) * i
      const x = cx + Math.cos(ang) * r, y = cy + Math.sin(ang) * r
      i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)
    }
    ctx.closePath()
  }

  function frame(now) {
    const p = (now - start) / DUR
    if (p >= 1) { ctx.clearRect(0, 0, w, h); canvas.style.opacity = '0'; return }
    ctx.clearRect(0, 0, w, h)
    // Cover phase (0→.5): veil grows L→R. Reveal (.5→1): shatters L→R.
    const cover = p < 0.5
    const q = cover ? p / 0.5 : (p - 0.5) / 0.5
    const e = 1 - Math.pow(1 - q, 2.4)
    const band = 0.30
    const front = e * (1 + band)
    const HEX = Math.max(44, w / 34)
    const stepX = HEX * 0.75, stepY = HEX * 0.866

    // Solid veil region
    ctx.fillStyle = 'rgba(8,16,32,0.97)'
    if (cover) { if (front < 1) {} ctx.fillRect(0, 0, Math.min(1, front) * w, h) }
    else if (front < 1) ctx.fillRect(Math.min(1, front) * w, 0, w, h)

    for (let k = 0; k * stepX < w + HEX; k++) {
      const cx = k * stepX
      const cn = cx / w
      let lp = (front - cn) / band
      if (lp <= 0 || lp >= 1) continue
      const s = cover ? lp : (1 - lp)        // grow in, shrink out
      const r = (HEX / 2) * Math.max(0.02, s)
      const flash = Math.sin(Math.PI * Math.min(1, lp * 2)) // leading edge
      for (let row = 0; row * stepY < h + HEX; row++) {
        const cy = row * stepY + ((k % 2) ? stepY / 2 : 0)
        ctx.shadowColor = `rgba(200,170,110,${0.55 * flash})`
        ctx.shadowBlur = 18 * flash
        ctx.fillStyle = `rgba(8,16,32,${0.97 * s})`
        hexPath(cx, cy, r); ctx.fill()
        if (flash > 0.25) {
          ctx.strokeStyle = `rgba(232,213,163,${0.8 * flash * s})`
          ctx.lineWidth = 1.4
          ctx.stroke()
        }
      }
    }
    ctx.shadowBlur = 0
    requestAnimationFrame(frame)
  }
</script>

<canvas bind:this={canvas}></canvas>

<style>
  canvas {
    position: fixed; inset: 0;
    width: 100vw; height: 100vh;
    pointer-events: none;
    z-index: 90;
    opacity: 0;
  }
</style>
