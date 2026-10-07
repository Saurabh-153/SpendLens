import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const port = Number(process.env.PORT ?? 3000)
const base = process.env.BASE_PATH ?? '/'

export default defineConfig({
  base,
  plugins: [react()],
  server: {
    port,
    host: '0.0.0.0',
    proxy: {
      '/spendlens/api': {
        target: 'http://localhost:5000',
        changeOrigin: true,
      },
    },
  },
  build: { outDir: 'dist/public', emptyOutDir: true },
})
