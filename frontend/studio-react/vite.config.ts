import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VASSIL_')
  const target = process.env.VASSIL_API_TARGET || env.VASSIL_API_TARGET || 'http://127.0.0.1:8000'
  return {
    base: '/studio/',
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    server: {
      proxy: {
        '/api': { target, ws: true },
        '/health': target,
        '/livez': target,
        '/readyz': target,
        '/diagnostics': target,
        '/model-status': target,
        '/warmup': target,
      },
    },
  }
})
