import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Frontend dev server on :5173, API proxied to the Express server on :8787.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8787'
    }
  }
})
