/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import packageJson from './package.json'
export default defineConfig({
  plugins: [vue()],
  define: { __APP_VERSION__: JSON.stringify(`v${packageJson.version}`) },
  test: { environment: 'jsdom' },
})
