<script setup lang="ts">
/** 登录后全局公告横幅：只展示当前用户角色可见且有效的公告。 */
import { computed, onMounted, ref } from 'vue'
import { announcementApi } from '@/api/endpoints'
import type { Announcement, AnnouncementLevel } from '@/api/types'
import { formatDateTime } from '@/utils/format'

const STORAGE_KEY = 'study-qb-dismissed-announcements'

const announcements = ref<Announcement[]>([])
const dialogVisible = ref(false)

const levelMeta: Record<
  AnnouncementLevel,
  { label: string; badge: string; panel: string; icon: string }
> = {
  info: {
    label: '通知',
    badge: 'bg-brand-500 text-white',
    panel: 'border-brand-200 bg-brand-50 text-ink',
    icon: 'InfoFilled',
  },
  success: {
    label: '更新',
    badge: 'bg-success text-white',
    panel: 'border-success/30 bg-success/10 text-ink',
    icon: 'CircleCheckFilled',
  },
  warning: {
    label: '提醒',
    badge: 'bg-warning text-white',
    panel: 'border-warning/30 bg-warning/10 text-ink',
    icon: 'WarningFilled',
  },
  danger: {
    label: '重要',
    badge: 'bg-danger text-white',
    panel: 'border-danger/30 bg-danger/10 text-ink',
    icon: 'CircleCloseFilled',
  },
}

function readDismissedKeys() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    const parsed = raw ? JSON.parse(raw) : []
    return new Set(Array.isArray(parsed) ? parsed.map(String) : [])
  } catch {
    return new Set<string>()
  }
}

function writeDismissedKeys(keys: Set<string>) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify([...keys].slice(-100)))
  } catch {
    /* localStorage 不可用时忽略关闭记忆，不影响公告展示。 */
  }
}

function dismissKey(item: Announcement) {
  return `${item.announcement_id}:${item.updated_at}`
}

const visibleAnnouncements = computed(() => {
  const dismissed = readDismissedKeys()
  return announcements.value.filter((item) => !dismissed.has(dismissKey(item)))
})

const current = computed(() => visibleAnnouncements.value[0] ?? null)

function dismiss(item: Announcement) {
  const dismissed = readDismissedKeys()
  dismissed.add(dismissKey(item))
  writeDismissedKeys(dismissed)
  announcements.value = [...announcements.value]
}

function timeRange(item: Announcement) {
  if (!item.starts_at && !item.ends_at) return '长期有效'
  if (item.starts_at && item.ends_at) {
    return `${formatDateTime(item.starts_at)} 至 ${formatDateTime(item.ends_at)}`
  }
  if (item.starts_at) return `${formatDateTime(item.starts_at)} 起`
  return `${formatDateTime(item.ends_at)} 前有效`
}

async function loadAnnouncements() {
  try {
    const res = await announcementApi.active(10)
    announcements.value = res.announcements
  } catch {
    /* 公告加载失败不阻塞业务页面。 */
  }
}

onMounted(loadAnnouncements)
</script>

<template>
  <div v-if="current" class="border-b border-line bg-card px-4 py-2 sm:px-6">
    <div
      class="flex items-start gap-3 rounded-xl border px-3 py-2 text-sm shadow-sm"
      :class="levelMeta[current.level].panel"
    >
      <span
        class="mt-0.5 inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium"
        :class="levelMeta[current.level].badge"
      >
        <el-icon :size="13">
          <component :is="levelMeta[current.level].icon" />
        </el-icon>
        {{ levelMeta[current.level].label }}
      </span>
      <div class="min-w-0 flex-1">
        <div class="flex flex-wrap items-center gap-2">
          <span class="font-semibold">{{ current.title }}</span>
          <span v-if="current.pinned" class="rounded bg-white/70 px-1.5 py-0.5 text-xs">置顶</span>
        </div>
        <p class="mt-0.5 line-clamp-2 whitespace-pre-line text-xs opacity-90">
          {{ current.content }}
        </p>
      </div>
      <div class="flex shrink-0 items-center gap-1">
        <el-button v-if="visibleAnnouncements.length > 1" link type="primary" @click="dialogVisible = true">
          查看全部
        </el-button>
        <el-button circle text size="small" @click="dismiss(current)">
          <el-icon><Close /></el-icon>
        </el-button>
      </div>
    </div>

    <el-dialog v-model="dialogVisible" title="系统公告" width="720px" class="app-dialog">
      <div class="space-y-3">
        <article
          v-for="item in visibleAnnouncements"
          :key="item.announcement_id"
          class="rounded-xl border border-line bg-muted/40 p-4"
        >
          <div class="flex flex-wrap items-center gap-2">
            <el-tag :type="item.level === 'danger' ? 'danger' : item.level">{{ levelMeta[item.level].label }}</el-tag>
            <h3 class="text-base font-semibold text-ink">{{ item.title }}</h3>
            <el-tag v-if="item.pinned" type="warning" effect="plain">置顶</el-tag>
          </div>
          <p class="mt-3 whitespace-pre-line text-sm leading-6 text-ink-soft">{{ item.content }}</p>
          <p class="mt-3 text-xs text-ink-muted">{{ timeRange(item) }}</p>
        </article>
      </div>
    </el-dialog>
  </div>
</template>
