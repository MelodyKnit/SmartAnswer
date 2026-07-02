<script setup lang="ts">
/** 主框架布局：左侧导航 + 顶栏 + 内容区。
 *  - 桌面：固定侧边栏；移动端：抽屉式侧边栏 + 顶栏汉堡按钮。
 *  - 顶栏含主题切换（亮/暗/跟随系统）、通知铃、用户菜单。
 *  - 菜单按角色过滤。 */
import { computed, onMounted, ref, watch } from 'vue'
import { RouterView, useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore, type ThemeMode } from '@/stores/theme'
import { notificationApi } from '@/api/endpoints'
import type { NotificationItem } from '@/api/types'
import { relativeTime } from '@/utils/format'
import AnnouncementBanner from '@/components/AnnouncementBanner.vue'
import SidebarNav from './SidebarNav.vue'

const auth = useAuthStore()
const theme = useThemeStore()
const route = useRoute()
const router = useRouter()

interface MenuEntry {
  index: string
  label: string
  icon: string
  access: 'user' | 'admin' | 'superadmin'
}

interface MenuGroup {
  title: string
  items: MenuEntry[]
}

const allGroups: MenuGroup[] = [
  {
    title: '控制台',
    items: [
      { index: '/', label: '工作台', icon: 'HomeFilled', access: 'user' },
      { index: '/search', label: '在线搜题', icon: 'Search', access: 'user' },
      { index: '/usage-logs', label: '使用记录', icon: 'Tickets', access: 'user' },
      { index: '/feedback', label: '反馈中心', icon: 'ChatDotRound', access: 'user' },
    ],
  },
  {
    title: '个人中心',
    items: [
      { index: '/profile', label: '个人资料', icon: 'User', access: 'user' },
      { index: '/tokens', label: 'API Key 管理', icon: 'Key', access: 'user' },
      { index: '/wallet', label: '我的钱包', icon: 'Wallet', access: 'user' },
    ],
  },
  {
    title: '管理',
    items: [
      { index: '/import-scripts', label: '导入脚本', icon: 'Document', access: 'admin' },
      { index: '/redeem-management', label: '兑换管理', icon: 'Coin', access: 'admin' },
      { index: '/llm-models', label: '大模型配置', icon: 'Cpu', access: 'admin' },
      { index: '/questions', label: '题库管理', icon: 'Notebook', access: 'admin' },
      { index: '/announcements', label: '公告管理', icon: 'BellFilled', access: 'admin' },
      { index: '/users', label: '用户管理', icon: 'UserFilled', access: 'admin' },
      { index: '/roles', label: '角色权限', icon: 'Lock', access: 'admin' },
      { index: '/system-logs', label: '系统日志', icon: 'Monitor', access: 'admin' },
      { index: '/system-config', label: '系统配置', icon: 'Setting', access: 'superadmin' },
    ],
  },
]

const menuGroups = computed(() =>
  allGroups
    .map((g) => ({ title: g.title, items: g.items.filter((m) => auth.hasAccess(m.access)) }))
    .filter((g) => g.items.length > 0),
)
const activeIndex = computed(() => route.path)

const roleLabel = computed(() => {
  switch (auth.role) {
    case 'superadmin':
      return '超级管理员'
    case 'admin':
      return '管理员'
    default:
      return '普通用户'
  }
})

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

/* 通知铃 */
const notifications = ref<NotificationItem[]>([])
const unreadCount = computed(() => notifications.value.filter((n) => !n.read).length)

async function loadNotifications() {
  try {
    const res = await notificationApi.list({ limit: 20 })
    notifications.value = res.notifications
  } catch {
    /* 顶栏通知失败不阻塞主流程 */
  }
}

async function markRead(item: NotificationItem) {
  if (item.read) return
  try {
    await notificationApi.read(item.notification_id)
    item.read = true
  } catch {
    /* 忽略 */
  }
}

async function markAllRead() {
  try {
    await notificationApi.readAll()
    notifications.value.forEach((n) => (n.read = true))
    ElMessage.success('已全部标记为已读')
  } catch {
    ElMessage.error('操作失败')
  }
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

onMounted(loadNotifications)
</script>

<template>
  <div class="flex h-full">
    <!-- 侧边导航：桌面常驻，移动端抽屉 -->
    <SidebarNav
      class="hidden w-60 shrink-0 lg:flex"
      :groups="menuGroups"
      :active="activeIndex"
      @select="handleSelect"
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

          <!-- 通知 -->
          <el-popover placement="bottom-end" :width="320" trigger="click">
            <template #reference>
              <el-badge :value="unreadCount" :hidden="unreadCount === 0" :max="99">
                <el-button circle text>
                  <el-icon :size="20"><Bell /></el-icon>
                </el-button>
              </el-badge>
            </template>
            <div class="flex items-center justify-between pb-2">
              <span class="font-medium text-ink">消息通知</span>
              <el-button link type="primary" size="small" @click="markAllRead">全部已读</el-button>
            </div>
            <el-scrollbar max-height="320px">
              <div v-if="notifications.length === 0" class="py-8 text-center text-sm text-ink-muted">
                暂无消息
              </div>
              <div
                v-for="n in notifications"
                :key="n.notification_id"
                class="cursor-pointer rounded-lg p-2.5 hover:bg-brand-50"
                @click="markRead(n)"
              >
                <div class="flex items-center gap-2">
                  <span v-if="!n.read" class="h-1.5 w-1.5 shrink-0 rounded-full bg-brand-600"></span>
                  <span class="truncate text-sm font-medium text-ink">{{ n.title }}</span>
                  <span class="ml-auto shrink-0 text-xs text-ink-muted">
                    {{ relativeTime(n.created_at) }}
                  </span>
                </div>
                <p class="mt-1 line-clamp-2 text-xs text-ink-soft">{{ n.content }}</p>
              </div>
            </el-scrollbar>
          </el-popover>

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
