import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const port = Number(process.env.PORT ?? 3000)
const base = process.env.BASE_PATH ?? '/'

export default defineConfig({
  base,
  plugins: [react()],
  server: {
    port,
    // Only this computer by default; VITE_HOST=0.0.0.0 pnpm dev opens the dev server to the network.
    host: process.env.VITE_HOST ?? 'localhost',
    proxy: {
      '/spendlens/api': {
        target: 'http://localhost:5000',
        changeOrigin: true,
        // X-Forwarded-For / -Host: the backend sees who really sent a request (its "this computer only" password
        // reset refuses one relayed from another machine) and which origin the browser was on (cross-site check).
        xfwd: true,
      },
    },
  },
  build: { outDir: 'dist/public', emptyOutDir: true },
})
