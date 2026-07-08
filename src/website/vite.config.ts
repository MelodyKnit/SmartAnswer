import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

// 后端 FastAPI 默认运行在 127.0.0.1:8765。
// 开发期通过代理把平台接口前缀直接转发到后端，保持同源、免跨域；
// 生产构建为纯静态资源，运行时由 VITE_API_BASE 指定后端地址（携带 Bearer 令牌跨域）。
const API_PREFIX_RE =
  '^/(auth|users|dashboard|notifications|notification-center|tokens|usage-logs|import-scripts|roles|site-config|system-config|project-update|billing|points-policy|wallet|feedback|status|query|ocs|configs|healthz|debug|questions|llm-models|llm-runtime-config|llm-stats|llm-traces)'

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  build: {
    outDir: '../study_qb_assistant/api/static',
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      [API_PREFIX_RE]: {
        target: process.env.VITE_API_TARGET || 'http://127.0.0.1:8765',
        changeOrigin: true,
        bypass: (req) => {
          if (req.headers.accept?.includes('text/html')) {
            return '/index.html'
          }
        },
      },
    },
  },
})
