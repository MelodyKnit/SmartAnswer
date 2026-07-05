<script setup lang="ts">
/** 顶栏通知中心：聚合普通通知与系统公告。 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { notificationCenterApi } from '@/api/endpoints'
import type { NotificationCenterItem, NotificationCenterSource } from '@/api/types'
import { formatDateTime, relativeTime } from '@/utils/format'

type FilterKey = 'all' | 'unread' | NotificationCenterSource

const items = ref<NotificationCenterItem[]>([])
const unreadCount = ref(0)
const loading = ref(false)
const activeFilter = ref<FilterKey>('all')
const selected = ref<NotificationCenterItem | null>(null)
const detailVisible = ref(false)

const filterOptions: { key: FilterKey; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'unread', label: '未读' },
  { key: 'announcement', label: '公告' },
  { key: 'notification', label: '消息' },
]

const emptyText = computed(() => (activeFilter.value === 'unread' ? '暂无未读内容' : '暂无通知'))

function levelType(level: string) {
  if (level === 'danger') return 'danger'
  if (level === 'warning') return 'warning'
  if (level === 'success') return 'success'
  return 'info'
}

function sourceLabel(item: NotificationCenterItem) {
  return item.source === 'announcement' ? '公告' : '消息'
}

function sourceIcon(item: NotificationCenterItem) {
  return item.source === 'announcement' ? 'BellFilled' : 'Bell'
}

function buildParams() {
  if (activeFilter.value === 'unread') return { status: 'unread' as const, limit: 50 }
  if (activeFilter.value === 'announcement' || activeFilter.value === 'notification') {
    return { source: activeFilter.value, limit: 50 }
  }
  return { limit: 50 }
}

async function loadItems() {
  loading.value = true
  try {
    const res = await notificationCenterApi.list(buildParams())
    items.value = res.items
    unreadCount.value = res.unread_count
  } catch {
    /* 顶栏通知失败不阻塞当前页面。 */
  } finally {
    loading.value = false
  }
}

async function chooseFilter(key: FilterKey) {
  activeFilter.value = key
  await loadItems()
}

async function markRead(item: NotificationCenterItem) {
  if (item.read) return
  try {
    const res = await notificationCenterApi.read(item.source, item.item_id)
    item.read = true
    const index = items.value.findIndex(
      (candidate) =>
        candidate.source === res.item.source && candidate.item_id === res.item.item_id,
    )
    if (index >= 0) {
      if (activeFilter.value === 'unread') {
        items.value.splice(index, 1)
      } else {
        items.value[index] = res.item
      }
    }
    unreadCount.value = Math.max(0, unreadCount.value - 1)
  } catch {
    ElMessage.error('标记已读失败')
  }
}

async function openDetail(item: NotificationCenterItem) {
  selected.value = item
  detailVisible.value = true
  await markRead(item)
}

async function markAllRead() {
  if (unreadCount.value <= 0) return
  try {
    await notificationCenterApi.readAll()
    items.value =
      activeFilter.value === 'unread'
        ? []
        : items.value.map((item) => ({ ...item, read: true }))
    unreadCount.value = 0
    ElMessage.success('已全部标记为已读')
  } catch {
    ElMessage.error('操作失败')
  }
}

onMounted(loadItems)
</script>

<template>
  <el-popover placement="bottom-end" :width="420" trigger="click" @show="loadItems">
    <template #reference>
      <el-badge :value="unreadCount" :hidden="unreadCount === 0" :max="99">
        <el-button circle text>
          <el-icon :size="20"><Bell /></el-icon>
        </el-button>
      </el-badge>
    </template>

    <div class="space-y-3">
      <div class="flex items-center justify-between">
        <span class="font-medium text-ink">通知中心</span>
        <el-button link type="primary" size="small" :disabled="unreadCount === 0" @click="markAllRead">
          全部已读
        </el-button>
      </div>

      <div class="grid grid-cols-4 gap-1 rounded-lg bg-muted p-1">
        <button
          v-for="option in filterOptions"
          :key="option.key"
          class="rounded-md px-2 py-1.5 text-xs font-medium text-ink-muted transition hover:text-ink"
          :class="activeFilter === option.key ? 'bg-card text-brand-600 shadow-sm' : ''"
          type="button"
          @click="chooseFilter(option.key)"
        >
          {{ option.label }}
        </button>
      </div>

      <el-scrollbar v-loading="loading" max-height="360px">
        <div v-if="items.length === 0" class="py-10 text-center text-sm text-ink-muted">
          {{ emptyText }}
        </div>
        <button
          v-for="item in items"
          :key="`${item.source}:${item.item_id}`"
          type="button"
          class="w-full rounded-lg px-2.5 py-2.5 text-left transition hover:bg-brand-50"
          @click="openDetail(item)"
        >
          <div class="flex items-start gap-2.5">
            <span
              class="mt-0.5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-brand-600"
            >
              <el-icon :size="16"><component :is="sourceIcon(item)" /></el-icon>
            </span>
            <span class="min-w-0 flex-1">
              <span class="flex items-center gap-1.5">
                <span v-if="!item.read" class="h-1.5 w-1.5 shrink-0 rounded-full bg-brand-600"></span>
                <span class="truncate text-sm font-medium text-ink">{{ item.title }}</span>
                <el-tag size="small" effect="plain" :type="levelType(item.level)">
                  {{ sourceLabel(item) }}
                </el-tag>
                <el-tag v-if="item.pinned" size="small" type="warning" effect="plain">置顶</el-tag>
              </span>
              <span class="mt-1 block line-clamp-2 text-xs leading-5 text-ink-soft">
                {{ item.content }}
              </span>
            </span>
            <span class="shrink-0 text-xs text-ink-muted">{{ relativeTime(item.created_at) }}</span>
          </div>
        </button>
      </el-scrollbar>
    </div>

    <el-dialog v-model="detailVisible" title="通知详情" width="640px" class="app-dialog">
      <article v-if="selected" class="space-y-4">
        <div class="flex flex-wrap items-center gap-2">
          <el-tag :type="levelType(selected.level)">{{ sourceLabel(selected) }}</el-tag>
          <el-tag v-if="selected.pinned" type="warning" effect="plain">置顶</el-tag>
          <span class="text-sm text-ink-muted">{{ formatDateTime(selected.created_at) }}</span>
        </div>
        <h3 class="text-lg font-semibold text-ink">{{ selected.title }}</h3>
        <p class="whitespace-pre-line text-sm leading-6 text-ink-soft">{{ selected.content }}</p>
        <p v-if="selected.expires_at" class="text-xs text-ink-muted">
          有效期至 {{ formatDateTime(selected.expires_at) }}
        </p>
      </article>
    </el-dialog>
  </el-popover>
</template>
