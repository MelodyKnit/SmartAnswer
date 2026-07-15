import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

// 后端 FastAPI 默认运行在 127.0.0.1:8765。
// 开发期只代理规范 API 前缀与 OCS 公共入口，新增接口无需维护名称清单；
// 生产构建为纯静态资源，运行时由 VITE_API_BASE 指定后端地址（携带 Bearer 令牌跨域）。

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  build: {
    outDir: '../study_qb_assistant/api/static/site',
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      '/api/v1': {
        target: process.env.VITE_API_TARGET || 'http://127.0.0.1:8765',
        changeOrigin: true,
      },
      '/ocs/query': {
        target: process.env.VITE_API_TARGET || 'http://127.0.0.1:8765',
        changeOrigin: true,
      },
    },
  },
})
