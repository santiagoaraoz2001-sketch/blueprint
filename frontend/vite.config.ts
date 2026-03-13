import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import packageJson from './package.json'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')

  return {
    plugins: [react()],
    define: {
      __APP_VERSION__: JSON.stringify(packageJson.version),
    },
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    server: {
      port: parseInt(process.env.PORT || env.VITE_PORT || '5173', 10),
      proxy: {
        '/api': {
          target: env.VITE_API_TARGET || 'http://127.0.0.1:8000',
          changeOrigin: true,
          ws: true,
          secure: false,
          configure: (proxy) => {
            proxy.on('error', (err) => {
              console.error('[vite proxy error]', err.message)
            })
          },
        },
      },
    },
  }
})
