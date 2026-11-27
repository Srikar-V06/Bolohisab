import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

export default defineConfig(({ mode }) => ({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      // API_URL lets Windows machines that reserve port 8000 point at another backend port.
      '/api': loadEnv(mode, '.', '').API_URL || 'http://127.0.0.1:8000',
    },
  },
}))
