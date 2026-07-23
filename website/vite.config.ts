import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tsconfigPaths from "vite-tsconfig-paths";

// https://vite.dev/config/
export default defineConfig(({ mode }) => ({
  // GitHub Pages 部署在 /Trigen/ 子路径，本地开发保持根路径
  base: mode === 'production' ? '/Trigen/' : '/',
  server: {
    port: 5100,
    host: true,
  },
  build: {
    sourcemap: 'hidden',
  },
  plugins: [
    react({
      babel: {
        plugins: [
          'react-dev-locator',
        ],
      },
    }),
    tsconfigPaths()
  ],
}))
