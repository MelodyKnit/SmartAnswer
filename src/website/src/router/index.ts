/** 路由表与导航守卫（含登录态与后端权限边界控制）。 */
import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useSiteStore } from '@/stores/site'

/** 路由 meta 扩展：所需后端权限。 */
declare module 'vue-router' {
  interface RouteMeta {
    public?: boolean
    requiredPermissions?: string[]
    requireAnyPermission?: boolean
    title?: string
  }
}

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/auth/LoginView.vue'),
    meta: { public: true, title: '登录' },
  },
  {
    path: '/register',
    name: 'register',
    component: () => import('@/views/auth/RegisterView.vue'),
    meta: { public: true, title: '注册' },
  },
  {
    path: '/forgot',
    name: 'forgot',
    component: () => import('@/views/auth/ForgotView.vue'),
    meta: { public: true, title: '找回密码' },
  },
  {
    path: '/',
    component: () => import('@/layouts/AppLayout.vue'),
    children: [
      {
        path: '',
        name: 'workbench',
        component: () => import('@/views/WorkbenchView.vue'),
        meta: {
          requiredPermissions: ['dashboard:self', 'dashboard:all'],
          requireAnyPermission: true,
          title: '工作台',
        },
      },
      {
        path: 'search',
        name: 'search',
        component: () => import('@/views/OnlineSearchView.vue'),
        meta: { title: '在线搜题' },
      },
      {
        path: 'image-generation',
        name: 'image-generation',
        component: () => import('@/views/ImageGenerationView.vue'),
        meta: { requiredPermissions: ['image-generation:use'], title: 'AI 生图' },
      },
      {
        path: 'profile',
        name: 'profile',
        component: () => import('@/views/ProfileView.vue'),
        meta: { title: '个人中心' },
      },
      {
        path: 'tokens',
        name: 'tokens',
        component: () => import('@/views/TokensView.vue'),
        meta: { requiredPermissions: ['tokens:self'], title: 'API Key 管理' },
      },
      {
        path: 'import-scripts',
        name: 'import-scripts',
        component: () => import('@/views/ImportScriptsView.vue'),
        meta: { requiredPermissions: ['import-scripts:read'], title: '复制导入' },
      },
      {
        path: 'usage-logs',
        name: 'usage-logs',
        component: () => import('@/views/UsageLogsView.vue'),
        meta: { title: '使用记录' },
      },
      {
        path: 'feedback',
        name: 'feedback',
        component: () => import('@/views/FeedbackView.vue'),
        meta: {
          requiredPermissions: ['feedback:self', 'feedback:manage'],
          requireAnyPermission: true,
          title: '反馈中心',
        },
      },
      {
        path: 'redeem-management',
        name: 'redeem-management',
        component: () => import('@/views/RedeemManagementView.vue'),
        meta: { requiredPermissions: ['wallet:changes:write'], title: '兑换管理' },
      },
      {
        path: 'llm-models',
        name: 'llm-models',
        component: () => import('@/views/LlmModelsView.vue'),
        meta: { requiredPermissions: ['llm:read'], title: '大模型配置' },
      },
      {
        path: 'users',
        name: 'users',
        component: () => import('@/views/UsersView.vue'),
        meta: { requiredPermissions: ['users:write'], title: '用户管理' },
      },
      {
        path: 'roles',
        name: 'roles',
        component: () => import('@/views/RolesView.vue'),
        meta: { requiredPermissions: ['roles:read'], title: '角色权限' },
      },
      {
        path: 'questions',
        name: 'questions',
        component: () => import('@/views/QuestionsView.vue'),
        meta: { requiredPermissions: ['questions:read'], title: '题库管理' },
      },
      {
        path: 'announcements',
        name: 'announcements',
        component: () => import('@/views/AnnouncementsView.vue'),
        meta: { requiredPermissions: ['announcements:read'], title: '公告管理' },
      },
      {
        path: 'system-config',
        name: 'system-config',
        component: () => import('@/views/SystemConfigView.vue'),
        meta: { requiredPermissions: ['system:write'], title: '系统配置' },
      },
      {
        path: 'system-logs',
        name: 'system-logs',
        component: () => import('@/views/SystemLogsView.vue'),
        meta: { requiredPermissions: ['system:read'], title: '系统日志' },
      },
      {
        path: 'wallet',
        name: 'wallet',
        component: () => import('@/views/WalletView.vue'),
        meta: { title: '我的钱包' },
      },
    ],
  },
  {
    path: '/403',
    name: 'forbidden',
    component: () => import('@/views/ForbiddenView.vue'),
    meta: { title: '无权限' },
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('@/views/NotFoundView.vue'),
    meta: { title: '404 页面未找到', public: true },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (!auth.initialized) {
    await auth.fetchSession()
  }

  if (to.meta.public) {
    // 已登录用户访问登录/注册页时直接回工作台
    if (auth.isLoggedIn && (to.name === 'login' || to.name === 'register')) {
      return { name: 'workbench' }
    }
    return true
  }

  if (!auth.isLoggedIn) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }

  const required = to.meta.requiredPermissions ?? []
  const allowed = to.meta.requireAnyPermission
    ? auth.hasAnyPermission(required)
    : auth.hasAllPermissions(required)
  if (!allowed) {
    return { name: 'forbidden' }
  }

  return true
})

router.afterEach((to) => {
  useSiteStore().applyBrowserBrand(to.meta.title)
})

export default router
