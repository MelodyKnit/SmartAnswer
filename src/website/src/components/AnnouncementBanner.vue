<script setup lang="ts">
/** 登录后系统公告居中模态弹窗：支持今日关闭与本次会话关闭。 */
import { computed, onMounted, ref } from 'vue'
import { notificationCenterApi } from '@/api/endpoints'
import type { AnnouncementLevel, NotificationCenterItem } from '@/api/types'
import { formatDateTime } from '@/utils/format'

const announcements = ref<NotificationCenterItem[]>([])

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

const MUTE_TODAY_STORAGE_KEY = 'stqb_announcements_muted_today'
const sessionDismissedIds = ref<Set<string>>(new Set())
const mutedTodayIds = ref<Set<string>>(new Set(loadMutedTodayIds()))

function loadMutedTodayIds(): string[] {
  try {
    const raw = localStorage.getItem(MUTE_TODAY_STORAGE_KEY)
    if (!raw) return []
    const parsed: Record<string, number> = JSON.parse(raw)
    const now = Date.now()
    const validIds: string[] = []
    const updatedRecord: Record<string, number> = {}
    for (const [id, expireAt] of Object.entries(parsed)) {
      if (typeof expireAt === 'number' && now < expireAt) {
        validIds.push(id)
        updatedRecord[id] = expireAt
      }
    }
    localStorage.setItem(MUTE_TODAY_STORAGE_KEY, JSON.stringify(updatedRecord))
    return validIds
  } catch {
    return []
  }
}

function muteTodayAll() {
  const endOfDay = new Date()
  endOfDay.setHours(23, 59, 59, 999)
  const expireAt = endOfDay.getTime()

  try {
    const raw = localStorage.getItem(MUTE_TODAY_STORAGE_KEY)
    const parsed: Record<string, number> = raw ? JSON.parse(raw) : {}
    for (const item of visibleAnnouncements.value) {
      parsed[item.item_id] = expireAt
    }
    localStorage.setItem(MUTE_TODAY_STORAGE_KEY, JSON.stringify(parsed))
  } catch {
    /* 忽略存储异常 */
  }

  const next = new Set(mutedTodayIds.value)
  for (const item of visibleAnnouncements.value) {
    next.add(item.item_id)
  }
  mutedTodayIds.value = next
}

function dismissSessionAll() {
  const next = new Set(sessionDismissedIds.value)
  for (const item of visibleAnnouncements.value) {
    next.add(item.item_id)
  }
  sessionDismissedIds.value = next
}

const visibleAnnouncements = computed(() => {
  return announcements.value.filter(
    (item) =>
      item.source === 'announcement' &&
      !item.read &&
      !sessionDismissedIds.value.has(item.item_id) &&
      !mutedTodayIds.value.has(item.item_id) &&
      (item.pinned || item.level === 'danger' || item.level === 'warning'),
  )
})

const isModalVisible = computed({
  get: () => visibleAnnouncements.value.length > 0,
  set: (val: boolean) => {
    if (!val) {
      dismissSessionAll()
    }
  },
})

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
  <el-dialog
    v-model="isModalVisible"
    width="680px"
    :show-close="true"
    :close-on-click-modal="false"
    class="announcement-modal-dialog"
    align-center
    @close="dismissSessionAll"
  >
    <template #header>
      <div class="flex items-center gap-2 pr-6 text-base font-semibold text-ink">
        <el-icon><Notification /></el-icon>
        系统公告
      </div>
    </template>

    <div class="max-h-[60vh] space-y-4 overflow-y-auto px-1 py-2">
      <article
        v-for="item in visibleAnnouncements"
        :key="item.item_id"
        class="rounded-2xl border border-line bg-card-soft p-5 shadow-xs transition-all hover:border-brand-200"
      >
        <div class="flex flex-wrap items-center gap-2">
          <span
            class="inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium"
            :class="announcementMeta(item.level).badge"
          >
            <el-icon :size="12">
              <component :is="announcementMeta(item.level).icon" />
            </el-icon>
            {{ announcementMeta(item.level).label }}
          </span>
          <h3 class="text-base font-bold text-ink">{{ item.title }}</h3>
          <span v-if="item.pinned" class="rounded-md bg-warning/15 px-2 py-0.5 text-xs font-semibold text-warning">
            置顶
          </span>
        </div>
        <p class="mt-3 whitespace-pre-line text-sm leading-relaxed text-ink-soft">
          {{ item.content }}
        </p>
        <div class="mt-4 flex items-center justify-between text-xs text-ink-muted border-t border-line/60 pt-3">
          <span>有效期：{{ timeRange(item) }}</span>
          <span>发布于 {{ formatDateTime(item.created_at) }}</span>
        </div>
      </article>
    </div>

    <template #footer>
      <div class="flex items-center justify-end gap-3 pt-2">
        <el-button
          size="default"
          class="!rounded-xl border-line text-ink-muted hover:bg-canvas hover:text-ink"
          @click="muteTodayAll"
        >
          今日关闭
        </el-button>
        <el-button
          type="primary"
          size="default"
          class="!rounded-xl bg-brand-500 font-medium hover:bg-brand-600"
          @click="dismissSessionAll"
        >
          关闭公告
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
:deep(.announcement-modal-dialog) {
  border-radius: 1.25rem;
  overflow: hidden;
  background-color: var(--color-card, #ffffff);
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1);
}
:deep(.announcement-modal-dialog .el-dialog__header) {
  padding: 1.25rem 1.5rem 0.75rem;
  margin-right: 0;
  border-bottom: 1px solid var(--color-line, #f1f5f9);
}
:deep(.announcement-modal-dialog .el-dialog__body) {
  padding: 1rem 1.5rem;
}
:deep(.announcement-modal-dialog .el-dialog__footer) {
  padding: 0.75rem 1.5rem 1.25rem;
  border-top: 1px solid var(--color-line, #f1f5f9);
}
</style>
