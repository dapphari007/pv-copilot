import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Proxy /api -> FastAPI backend (main.py) running on :8000, so the React dev
// server and the API share an origin in development.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
