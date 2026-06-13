import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'

// Dev: vite proxies /api → Fly server-side (no CORS pain, no sidecar needed)
// and /local → a locally running sidecar (`python desktop/launcher.py --dev`,
// port 8765) for LCU/Riot commands. Without the sidecar, /local calls fail
// and the UI degrades gracefully (manual identity picker, disabled commands).
export default defineConfig({
  plugins: [svelte()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'https://the-rift-draft-sync.fly.dev',
        changeOrigin: true,
      },
      '/local': {
        target: 'http://127.0.0.1:8765',
        changeOrigin: true,
      },
    },
  },
})
