import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// /api/* is proxied to FastAPI (make api) so the browser never needs CORS in dev.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://localhost:8000', rewrite: (p) => p.replace(/^\/api/, '') },
    },
  },
})
