import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // The browser talks to the backend through the dev server, so there is one origin.
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws': { target: 'ws://localhost:8000', ws: true },
    },
  },
  // The map library is large and this is a locally installed application.
  build: { chunkSizeWarningLimit: 1800 },
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
})
