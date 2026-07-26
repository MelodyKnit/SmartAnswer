<script setup lang="ts">
/** 主框架布局：左侧导航 + 顶栏 + 内容区。
 *  - 桌面：固定侧边栏；移动端：抽屉式侧边栏 + 顶栏汉堡按钮。
 *  - 顶栏含主题切换（亮/暗/跟随系统）、通知铃、用户菜单。
 *  - 菜单按后端权限目录过滤。 */
import { computed, ref, watch } from 'vue'
import { RouterView, useRoute, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore, type ThemeMode } from '@/stores/theme'
import AnnouncementBanner from '@/components/AnnouncementBanner.vue'
import NotificationCenterPopover from '@/components/NotificationCenterPopover.vue'
import SidebarNav from './SidebarNav.vue'

const auth = useAuthStore()
const theme = useThemeStore()
const route = useRoute()
const router = useRouter()

/* 侧边栏折叠状态，优先从 localStorage 读取以保持用户偏好 */
const isCollapsed = ref(localStorage.getItem('sidebar_collapsed') === 'true')
function toggleCollapse() {
  isCollapsed.value = !isCollapsed.value
  localStorage.setItem('sidebar_collapsed', String(isCollapsed.value))
}

interface MenuEntry {
  index: string
  label: string
  icon: string
  requiredPermissions?: string[]
  requireAnyPermission?: boolean
}

interface MenuGroup {
  title: string
  items: MenuEntry[]
}

const allGroups: MenuGroup[] = [
  {
    title: '控制台',
    items: [
      { index: '/', label: '工作台', icon: 'HomeFilled', requiredPermissions: ['dashboard:self', 'dashboard:all'], requireAnyPermission: true },
      { index: '/search', label: '在线搜题', icon: 'Search' },
      { index: '/image-generation', label: 'AI 生图', icon: 'Picture', requiredPermissions: ['image-generation:use'] },
      { index: '/usage-logs', label: '使用记录', icon: 'Tickets' },
      { index: '/feedback', label: '反馈中心', icon: 'ChatDotRound', requiredPermissions: ['feedback:self', 'feedback:manage'], requireAnyPermission: true },
    ],
  },
  {
    title: '个人中心',
    items: [
      { index: '/profile', label: '个人资料', icon: 'User' },
      { index: '/tokens', label: 'API Key 管理', icon: 'Key', requiredPermissions: ['tokens:self'] },
      { index: '/wallet', label: '我的钱包', icon: 'Wallet' },
    ],
  },
  {
    title: '管理',
    items: [
      { index: '/import-scripts', label: '复制导入', icon: 'Document', requiredPermissions: ['import-scripts:read'] },
      { index: '/redeem-management', label: '兑换管理', icon: 'Coin', requiredPermissions: ['wallet:changes:write'] },
      { index: '/llm-models', label: '大模型配置', icon: 'Cpu', requiredPermissions: ['llm:read'] },
      { index: '/questions', label: '题库管理', icon: 'Notebook', requiredPermissions: ['questions:read'] },
      { index: '/announcements', label: '公告管理', icon: 'BellFilled', requiredPermissions: ['announcements:read'] },
      { index: '/users', label: '用户管理', icon: 'UserFilled', requiredPermissions: ['users:write'] },
      { index: '/roles', label: '角色权限', icon: 'Lock', requiredPermissions: ['roles:read'] },
      { index: '/system-logs', label: '系统日志', icon: 'Monitor', requiredPermissions: ['system:read'] },
      { index: '/system-config', label: '系统配置', icon: 'Setting', requiredPermissions: ['system:write'] },
    ],
  },
]

const menuGroups = computed(() =>
  allGroups
    .map((group) => ({
      title: group.title,
      items: group.items.filter((item) => {
        const required = item.requiredPermissions ?? []
        return item.requireAnyPermission
          ? auth.hasAnyPermission(required)
          : auth.hasAllPermissions(required)
      }),
    }))
    .filter((g) => g.items.length > 0),
)
const activeIndex = computed(() => route.path)

const roleLabel = computed(() => auth.user?.role_name || auth.user?.role || '—')

/* 移动端抽屉 */
const drawerOpen = ref(false)
watch(
  () => route.path,
  () => {
    drawerOpen.value = false
  },
)

/* 主题切换 */
const themeIcon = computed(() => {
  if (theme.mode === 'system') return 'Monitor'
  return theme.mode === 'dark' ? 'Moon' : 'Sunny'
})
function chooseTheme(mode: ThemeMode) {
  theme.setMode(mode)
}

function handleSelect(index: string) {
  if (index !== route.path) router.push(index)
}

async function handleLogout() {
  const confirmed = await ElMessageBox.confirm('确定退出登录吗？', '退出确认', {
    confirmButtonText: '退出',
    cancelButtonText: '取消',
    type: 'warning',
  })
    .then(() => true)
    .catch(() => false)
  if (!confirmed) return
  await auth.logout()
  router.replace({ name: 'login' })
}
</script>

<template>
  <div class="flex h-full">
    <!-- 侧边导航：桌面常驻，移动端抽屉 -->
    <SidebarNav
      class="hidden shrink-0 lg:flex transition-[width] duration-300 ease-in-out"
      :class="isCollapsed ? 'w-18' : 'w-60'"
      :groups="menuGroups"
      :active="activeIndex"
      :collapsed="isCollapsed"
      @select="handleSelect"
      @toggle-collapse="toggleCollapse"
    />

    <!-- 移动端抽屉 -->
    <transition name="drawer-fade">
      <div
        v-if="drawerOpen"
        class="fixed inset-0 z-40 bg-black/40 lg:hidden"
        @click="drawerOpen = false"
      ></div>
    </transition>
    <transition name="drawer-slide">
      <SidebarNav
        v-if="drawerOpen"
        class="fixed inset-y-0 left-0 z-50 flex w-64 lg:hidden"
        :groups="menuGroups"
        :active="activeIndex"
        @select="handleSelect"
      />
    </transition>

    <!-- 右侧主体 -->
    <div class="flex min-w-0 flex-1 flex-col">
      <!-- 顶栏 -->
      <header
        class="flex h-16 shrink-0 items-center justify-between border-b border-line bg-card px-4 sm:px-6"
      >
        <div class="flex items-center gap-2">
          <el-button class="lg:!hidden" circle text @click="drawerOpen = true">
            <el-icon :size="20"><Expand /></el-icon>
          </el-button>
          <span class="text-base font-medium text-ink">{{ route.meta.title || '工作台' }}</span>
        </div>

        <div class="flex items-center gap-1.5 sm:gap-3">
          <!-- 主题切换 -->
          <el-dropdown trigger="click" @command="chooseTheme">
            <el-button circle text>
              <el-icon :size="18"><component :is="themeIcon" /></el-icon>
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="light" :class="{ 'text-brand-600': theme.mode === 'light' }">
                  <el-icon><Sunny /></el-icon> 亮色
                </el-dropdown-item>
                <el-dropdown-item command="dark" :class="{ 'text-brand-600': theme.mode === 'dark' }">
                  <el-icon><Moon /></el-icon> 暗色
                </el-dropdown-item>
                <el-dropdown-item command="system" :class="{ 'text-brand-600': theme.mode === 'system' }">
                  <el-icon><Monitor /></el-icon> 跟随系统
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>

          <NotificationCenterPopover />

          <!-- 用户菜单 -->
          <el-dropdown trigger="click">
            <div class="flex cursor-pointer items-center gap-2">
              <el-avatar :size="32" class="!bg-brand-500">
                {{ auth.user?.username?.[0]?.toUpperCase() || 'U' }}
              </el-avatar>
              <div class="hidden leading-tight sm:block">
                <div class="text-sm font-medium text-ink">{{ auth.user?.username }}</div>
                <div class="text-xs text-ink-muted">{{ roleLabel }}</div>
              </div>
              <el-icon class="hidden text-ink-muted sm:block"><ArrowDown /></el-icon>
            </div>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click="router.push('/wallet')">
                  <el-icon><Wallet /></el-icon> 我的钱包
                </el-dropdown-item>
                <el-dropdown-item divided @click="handleLogout">
                  <el-icon><SwitchButton /></el-icon> 退出登录
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </header>

      <AnnouncementBanner />

      <!-- 内容区 -->
      <main class="min-w-0 flex-1 overflow-y-auto p-4 sm:p-6">
        <RouterView v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </RouterView>
      </main>
    </div>
  </div>
</template>
