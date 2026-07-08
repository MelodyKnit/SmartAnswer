import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus, { ElMessage } from 'element-plus'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'

import './style.css'
import App from './App.vue'
import router from './router'
import { useAuthStore } from './stores/auth'
import { useSiteStore } from './stores/site'
import { useThemeStore } from './stores/theme'
import { ApiException, registerUnauthorizedHandler } from './api/http'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)
app.use(ElementPlus, { locale: zhCn })

// 初始化主题（亮/暗/跟随系统），需在挂载前应用，避免首屏闪烁
useThemeStore(pinia).init()
useSiteStore(pinia).applyBrowserBrand(router.currentRoute.value.meta.title as string | undefined)
void useSiteStore(pinia).load()

// 注册全部 Element Plus 图标为全局组件
for (const [name, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(name, component)
}

// 令牌失效（401）时统一登出并跳转登录页
const authStore = useAuthStore(pinia)
registerUnauthorizedHandler(() => {
  authStore.reset()
  if (router.currentRoute.value.meta.public !== true) {
    router.replace({ name: 'login', query: { redirect: router.currentRoute.value.fullPath } })
  }
})

/** 兜底提示：捕获未被局部 try/catch 处理的接口异常，避免静默失败。
 *  401 已由上面的处理器接管，这里跳过，避免重复提示。 */
function reportError(err: unknown) {
  if (err instanceof ApiException) {
    if (err.status === 401) return
    ElMessage.error(err.message)
  }
}
app.config.errorHandler = (err) => reportError(err)
window.addEventListener('unhandledrejection', (event) => reportError(event.reason))

app.mount('#app')
