import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const api = `http://127.0.0.1:${process.env.API_PORT ?? '8107'}`

export default defineConfig({
  plugins: [react()],
  // Art lives at the repo root in assets/, one level above this package.
  server: { fs: { allow: ['..'] }, proxy: { '/api': api } },
  preview: { proxy: { '/api': api } },
  build: { chunkSizeWarningLimit: 1200 },
})
