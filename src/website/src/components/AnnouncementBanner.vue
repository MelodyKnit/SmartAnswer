<script setup lang="ts">
/** 登录后全局公告横幅：只展示未读且高优先级的有效公告。 */
import { computed, onMounted, ref } from 'vue'
import { notificationCenterApi } from '@/api/endpoints'
import type { AnnouncementLevel, NotificationCenterItem } from '@/api/types'
import { formatDateTime } from '@/utils/format'

const announcements = ref<NotificationCenterItem[]>([])
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

function announcementMeta(level: string) {
  return levelMeta[(level in levelMeta ? level : 'info') as AnnouncementLevel]
}

const visibleAnnouncements = computed(() => {
  return announcements.value.filter(
    (item) =>
      item.source === 'announcement' &&
      !item.read &&
      (item.pinned || item.level === 'danger' || item.level === 'warning'),
  )
})

const current = computed(() => visibleAnnouncements.value[0] ?? null)

async function dismiss(item: NotificationCenterItem) {
  try {
    await notificationCenterApi.read('announcement', item.item_id)
    item.read = true
    announcements.value = [...announcements.value]
  } catch {
    /* 关闭失败时保留公告，避免误以为重要公告已确认。 */
  }
}

function timeRange(item: NotificationCenterItem) {
  if (!item.expires_at) return '长期有效'
  return `${formatDateTime(item.expires_at)} 前有效`
}

async function loadAnnouncements() {
  try {
    const res = await notificationCenterApi.list({ source: 'announcement', limit: 10 })
    announcements.value = res.items
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
      :class="announcementMeta(current.level).panel"
    >
      <span
        class="mt-0.5 inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium"
        :class="announcementMeta(current.level).badge"
      >
        <el-icon :size="13">
          <component :is="announcementMeta(current.level).icon" />
        </el-icon>
        {{ announcementMeta(current.level).label }}
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
          :key="item.item_id"
          class="rounded-xl border border-line bg-muted/40 p-4"
        >
          <div class="flex flex-wrap items-center gap-2">
            <el-tag :type="item.level === 'danger' ? 'danger' : item.level">
              {{ announcementMeta(item.level).label }}
            </el-tag>
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
