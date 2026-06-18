<script setup lang="ts">
/** 系统日志查看：查看服务的各种操作与报警日志，并可尝试重启服务（硬重启，仅适用系统服务模式）。 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ApiException } from '@/api/http'
import { systemApi } from '@/api/endpoints'
import type { RuntimeEvent } from '@/api/types'
import { SYSTEM_DEFAULTS } from '@/config/constants'

import PageHeader from '@/components/PageHeader.vue'

const loading = ref(false)
const events = ref<RuntimeEvent[]>([])
const status = ref<Record<string, unknown> | null>(null)
const errorMsg = ref('')
const autoRefresh = ref(true)
let timer: number | undefined

const EVENT_META: Record<string, { label: string; type: string }> = {
  query: { label: '查题', type: 'primary' },
  model_request: { label: '模型请求', type: 'info' },
  model_response: { label: '模型响应', type: 'success' },
  model_error: { label: '模型错误', type: 'danger' },
  web_search: { label: '联网检索', type: 'info' },
  service_start: { label: '服务启动', type: 'success' },
  error: { label: '错误', type: 'danger' },
}

function eventLabel(name: string) {
  return EVENT_META[name]?.label || name
}
function eventType(name: string) {
  return EVENT_META[name]?.type || 'info'
}

async function load() {
  loading.value = true
  errorMsg.value = ''
  try {
    const [ev, st] = await Promise.all([
      systemApi.recentEvents(),
      systemApi.status().catch(() => null),
    ])
    events.value = [...ev.events].reverse()
    status.value = st
  } catch (err) {
    errorMsg.value = err instanceof ApiException ? err.message : '加载失败'
  } finally {
    loading.value = false
  }
}

/** 把事件除 ts/event 外的字段整理成键值明细。 */
function detailEntries(ev: RuntimeEvent): { key: string; value: string }[] {
  return Object.entries(ev)
    .filter(([k]) => k !== 'ts' && k !== 'event')
    .map(([key, value]) => ({
      key,
      value: typeof value === 'object' ? JSON.stringify(value) : String(value),
    }))
}

function isErrorEvent(ev: RuntimeEvent): boolean {
  return ev.event.includes('error') || 'error' in ev || 'error_message' in ev
}

const statusSummary = computed(() => {
  const s = status.value
  if (!s) return []
  const lookup = (s.lookup as Record<string, unknown>) || {}
  const model = (s.model as Record<string, unknown>) || {}
  const cache = (s.ai_answer_cache as Record<string, unknown>) || {}
  return [
    { label: '题库记录数', value: String(lookup.record_count ?? '—') },
    { label: 'LLM 兜底', value: model.fallback_enabled ? '已启用' : '未启用' },
    { label: '模型', value: String(model.model || '—') },
    { label: '搜索引擎', value: String(model.search_provider || '—') },
    { label: 'AI 缓存条目', value: String(cache.entry_count ?? '—') },
  ]
})

function toggleAuto() {
  autoRefresh.value = !autoRefresh.value
  setupTimer()
}

function setupTimer() {
  if (timer) window.clearInterval(timer)
  if (autoRefresh.value) {
    load()
  }
  timer = window.setInterval(() => {
    load()
  }, SYSTEM_DEFAULTS.LOG_REFRESH_INTERVAL_MS)
}

onMounted(() => {
  load()
  setupTimer()
})
onUnmounted(() => {
  if (timer) window.clearInterval(timer)
})
</script>

<template>
  <div>
    <PageHeader title="系统日志" description="查看运行状态与最近运行事件，含详细报错信息，便于排查问题。">
      <template #actions>
        <el-button :type="autoRefresh ? 'primary' : 'default'" @click="toggleAuto">
          {{ autoRefresh ? '自动刷新中' : '已暂停' }}
        </el-button>
        <el-button :icon="'Refresh'" :loading="loading" @click="load">刷新</el-button>
      </template>
    </PageHeader>

    <!-- 运行状态 -->
    <div class="mb-5 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
      <div v-for="s in statusSummary" :key="s.label" class="app-card p-4">
        <div class="text-xs text-ink-muted">{{ s.label }}</div>
        <div class="mt-1 truncate text-lg font-semibold text-ink">{{ s.value }}</div>
      </div>
    </div>

    <el-alert v-if="errorMsg" type="error" :closable="false" class="mb-4" :title="errorMsg" />

    <!-- 事件流 -->
    <div class="app-card p-5">
      <h3 class="mb-3 text-base font-semibold text-ink">运行事件（最近）</h3>
      <div v-if="events.length === 0" class="py-10 text-center text-sm text-ink-muted">
        暂无运行事件
      </div>
      <el-timeline v-else>
        <el-timeline-item
          v-for="(ev, idx) in events"
          :key="idx"
          :timestamp="ev.ts"
          :type="(eventType(ev.event) as any)"
          placement="top"
        >
          <div class="flex items-center gap-2">
            <el-tag size="small" :type="(eventType(ev.event) as any)">{{ eventLabel(ev.event) }}</el-tag>
            <span v-if="ev.title" class="truncate text-sm font-medium text-ink">{{ ev.title }}</span>
          </div>
          <el-collapse class="mt-2">
            <el-collapse-item :title="isErrorEvent(ev) ? '查看报错详情' : '查看详情'">
              <div class="space-y-1">
                <div
                  v-for="d in detailEntries(ev)"
                  :key="d.key"
                  class="flex gap-2 text-xs"
                  :class="d.key.includes('error') ? 'text-danger' : 'text-ink-soft'"
                >
                  <span class="shrink-0 font-mono text-ink-muted">{{ d.key }}:</span>
                  <span class="break-all">{{ d.value }}</span>
                </div>
              </div>
            </el-collapse-item>
          </el-collapse>
        </el-timeline-item>
      </el-timeline>
    </div>
  </div>
</template>
