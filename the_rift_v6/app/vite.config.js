import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'

// Dev: vite proxies /api → Fly server-side (no CORS pain, no sidecar needed).
// Prod (Tauri): the Python sidecar serves /api on localhost:8765.
export default defineConfig({
  plugins: [svelte()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'https://the-rift-draft-sync.fly.dev',
        changeOrigin: true,
      },
    },
  },
})
