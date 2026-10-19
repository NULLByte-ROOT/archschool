import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    // Same-origin WebSocket in dev, mirroring the nginx proxy in production.
    proxy: {
      '/api/ws': {
        target: 'http://127.0.0.1:8000',
        ws: true,
        changeOrigin: true,
      },
    },
  },
})