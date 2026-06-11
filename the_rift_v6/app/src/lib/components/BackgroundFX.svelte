<script>
  // Full-app living background: drifting hex lattice, volumetric fog glows,
  // rising embers with real canvas glow. Mouse-parallax on every layer.
  import { onMount } from 'svelte'
  import { motion } from '../stores.js'
  let canvas
  let mx = 0.5, my = 0.5            // smoothed mouse 0..1
  let inten = 1
  motion.subscribe(v => inten = v)

  onMount(() => {
    const ctx = canvas.getContext('2d')
    let w, h, dpr, raf
    let tmx = 0.5, tmy = 0.5

    const resize = () => {
      dpr = Math.min(2, window.devicePixelRatio || 1)
      w = canvas.clientWidth; h = canvas.clientHeight
      canvas.width = w * dpr; canvas.height = h * dpr
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    }
    resize()
    window.addEventListener('resize', resize)
    window.addEventListener('mousemove', e => {
      tmx = e.clientX / window.innerWidth
      tmy = e.clientY / window.innerHeight
    })

    // Deterministic embers — params fixed per index, position from time.
    const N = 42
    const embers = Array.from({ length: N }, (_, i) => {
      const r = mulberry(i * 7 + 1)
      return { x: r(), period: 9 + r() * 11, phase: r(), amp: 14 + r() * 40,
               size: 0.8 + r() * 1.9, bright: 0.35 + r() * 0.65 }
    })
    function mulberry(seed) {
      let a = seed
      return () => {
        a |= 0; a = (a + 0x6D2B79F5) | 0
        let t = Math.imul(a ^ (a >>> 15), 1 | a)
        t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
        return ((t ^ (t >>> 14)) >>> 0) / 4294967296
      }
    }

    const HEX = 96
    function drawHexLattice(t) {
      const px = (mx - 0.5) * 26, py = (my - 0.5) * 18
      const drift = (t * 2.4) % (HEX * 0.75)
      ctx.lineWidth = 1
      for (let gx = -2; gx * HEX * 0.75 < w + HEX; gx++) {
        for (let gy = -2; gy * (HEX * 0.866) < h + HEX; gy++) {
          const cx = gx * HEX * 0.75 - drift + px
          const cy = gy * HEX * 0.866 + ((gx % 2) ? HEX * 0.433 : 0) + py
          const pulse = 0.5 + 0.5 * Math.sin(t * 0.4 + gx * 0.7 + gy * 0.5)
          const a = 0.018 + pulse * 0.02
          ctx.strokeStyle = `rgba(200,170,110,${a})`
          ctx.beginPath()
          for (let i = 0; i < 6; i++) {
            const ang = (Math.PI / 3) * i + Math.PI / 6
            const x = cx + Math.cos(ang) * HEX * 0.5
            const y = cy + Math.sin(ang) * HEX * 0.5
            i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)
          }
          ctx.closePath(); ctx.stroke()
        }
      }
    }

    function frame(now) {
      const t = now / 1000
      mx += (tmx - mx) * 0.04; my += (tmy - my) * 0.04
      ctx.clearRect(0, 0, w, h)

      // Volumetric fog glows — three breathing radial lights.
      const fog = (x, y, r, rgb, a) => {
        const g = ctx.createRadialGradient(x, y, 0, x, y, r)
        g.addColorStop(0, `rgba(${rgb},${a})`)
        g.addColorStop(1, 'rgba(0,0,0,0)')
        ctx.fillStyle = g; ctx.fillRect(x - r, y - r, r * 2, r * 2)
      }
      const b1 = 0.5 + 0.5 * Math.sin(t * 0.21)
      const b2 = 0.5 + 0.5 * Math.sin(t * 0.16 + 2.1)
      fog(w * (0.22 + (mx - .5) * .05), h * 0.12, w * 0.42, '40,72,118', 0.16 + b1 * 0.05)
      fog(w * (0.85 + (mx - .5) * .03), h * 0.85, w * 0.36, '90,55,140', 0.07 + b2 * 0.03)
      fog(w * 0.5, h * 1.06, w * 0.5, '200,170,110', 0.05 + b1 * 0.02)

      drawHexLattice(t)

      // Embers — additive glow via shadowBlur (real bloom-ish).
      ctx.save()
      ctx.globalCompositeOperation = 'lighter'
      for (const e of embers) {
        const p = ((t / e.period) + e.phase) % 1
        const ex = e.x * w + Math.sin(t * 0.5 + e.phase * 6.28) * e.amp + (mx - .5) * 40
        const ey = h - p * (h + 80)
        const fade = Math.sin(Math.min(1, Math.max(0, p)) * Math.PI)
        const a = 0.55 * fade * e.bright * inten
        if (a < 0.02) continue
        ctx.shadowColor = `rgba(232,213,163,${a})`
        ctx.shadowBlur = 12
        ctx.fillStyle = `rgba(248,232,184,${a})`
        ctx.beginPath(); ctx.arc(ex, ey, e.size, 0, 7); ctx.fill()
      }
      ctx.restore()
      raf = requestAnimationFrame(frame)
    }
    raf = requestAnimationFrame(frame)
    return () => { cancelAnimationFrame(raf); window.removeEventListener('resize', resize) }
  })
</script>

<canvas bind:this={canvas}></canvas>

<style>
  canvas {
    position: fixed; inset: 0;
    width: 100vw; height: 100vh;
    pointer-events: none;
    z-index: 0;
  }
</style>
