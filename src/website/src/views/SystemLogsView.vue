<script setup lang="ts">
/** 系统日志查看：分为“业务调用日志”（支持分页与右侧抽屉详情）与“终端实时日志”（高仿命令行控制台）。 */
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { ApiException } from '@/api/http'
import { systemApi } from '@/api/endpoints'
import type { ConsoleLogLine, RuntimeEvent } from '@/api/types'
import { SYSTEM_DEFAULTS } from '@/config/constants'
import { ElMessage } from 'element-plus'

import PageHeader from '@/components/PageHeader.vue'

const activeTab = ref<'events' | 'console'>('events')
const loading = ref(false)
const events = ref<RuntimeEvent[]>([])
const status = ref<Record<string, unknown> | null>(null)
const errorMsg = ref('')
const autoRefresh = ref(true)
let timer: number | undefined

// 分页与事件过滤
const page = ref(1)
const pageSize = ref(20)
const eventTypeFilter = ref('')
const keywordFilter = ref('')
const selectedEvent = ref<RuntimeEvent | null>(null)
const drawerVisible = ref(false)

// 终端日志状态
const consoleLogs = ref<ConsoleLogLine[]>([])
const consoleLoading = ref(false)
const consoleLogLevel = ref('ALL')
const consoleKeyword = ref('')
const autoScroll = ref(true)
const terminalBodyRef = ref<HTMLElement | null>(null)

const getLocalDateString = (d = new Date()) => {
  const year = d.getFullYear()
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const todayStr = getLocalDateString()
const dateRange = ref<[string, string] | null>([todayStr, todayStr])

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

async function fetchConsoleLogs() {
  consoleLoading.value = true
  try {
    const res = await systemApi.consoleLogs({ limit: 1000 })
    consoleLogs.value = res.logs
    if (autoScroll.value) {
      await nextTick()
      scrollToBottom()
    }
  } catch (err) {
    // 忽略加载错误
  } finally {
    consoleLoading.value = false
  }
}

async function load() {
  loading.value = true
  errorMsg.value = ''
  try {
    const params: Record<string, string> = {}
    if (dateRange.value && dateRange.value.length === 2) {
      params.start_date = dateRange.value[0]
      params.end_date = dateRange.value[1]
    }
    const [ev, st] = await Promise.all([
      systemApi.recentEvents(params),
      systemApi.status().catch(() => null),
    ])
    events.value = [...ev.events].reverse()
    status.value = st
    if (activeTab.value === 'console') {
      await fetchConsoleLogs()
    }
  } catch (err) {
    errorMsg.value = err instanceof ApiException ? err.message : '加载失败'
  } finally {
    loading.value = false
  }
}

function scrollToBottom() {
  if (terminalBodyRef.value) {
    terminalBodyRef.value.scrollTop = terminalBodyRef.value.scrollHeight
  }
}

function openEventDrawer(ev: RuntimeEvent) {
  selectedEvent.value = ev
  drawerVisible.value = true
}

async function copyConsoleLogs() {
  const text = filteredConsoleLogs.value.map((l) => l.raw).join('\n')
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('终端日志已复制到剪贴板')
  } catch {
    ElMessage.warning('复制失败，请手动复制')
  }
}

async function clearConsole() {
  try {
    await systemApi.clearConsoleLogs()
    consoleLogs.value = []
    ElMessage.success('终端日志已清屏')
  } catch (err) {
    ElMessage.error('清屏失败')
  }
}

const filteredEvents = computed(() => {
  let list = events.value
  if (eventTypeFilter.value) {
    list = list.filter((e) => e.event === eventTypeFilter.value)
  }
  if (keywordFilter.value.trim()) {
    const kw = keywordFilter.value.trim().toLowerCase()
    list = list.filter((e) => {
      const title = String(e.title || '').toLowerCase()
      const raw = JSON.stringify(e).toLowerCase()
      return title.includes(kw) || raw.includes(kw)
    })
  }
  return list
})

const paginatedEvents = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return filteredEvents.value.slice(start, start + pageSize.value)
})

const filteredConsoleLogs = computed(() => {
  let list = consoleLogs.value
  if (consoleLogLevel.value !== 'ALL') {
    list = list.filter((l) => l.level === consoleLogLevel.value)
  }
  if (consoleKeyword.value.trim()) {
    const kw = consoleKeyword.value.trim().toLowerCase()
    list = list.filter((l) => l.raw.toLowerCase().includes(kw))
  }
  return list
})

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
  timer = undefined
  if (!autoRefresh.value) return
  load()
  timer = window.setInterval(() => {
    load()
  }, SYSTEM_DEFAULTS.LOG_REFRESH_INTERVAL_MS)
}

watch(activeTab, (tab) => {
  if (tab === 'console') {
    void fetchConsoleLogs()
  }
})

watch([eventTypeFilter, keywordFilter], () => {
  page.value = 1
})

onMounted(() => {
  setupTimer()
})
onUnmounted(() => {
  if (timer) window.clearInterval(timer)
})
</script>

<template>
  <div>
    <PageHeader title="系统日志" description="查看业务调用流水与终端实时运行输出，含详细报错信息，便于排查问题。">
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

    <div class="mt-2">
      <el-tabs v-model="activeTab" class="app-tabs">
        <!-- Tab 1: 业务调用日志 -->
        <el-tab-pane label="业务调用日志" name="events">
          <div class="app-card p-5 mt-2">
            <!-- 过滤条 -->
            <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
              <div class="flex flex-wrap items-center gap-2">
                <el-select v-model="eventTypeFilter" placeholder="全部事件类型" clearable style="width: 140px">
                  <el-option v-for="(v, k) in EVENT_META" :key="k" :value="k" :label="v.label" />
                </el-select>
                <el-input
                  v-model="keywordFilter"
                  placeholder="搜索题干或参数..."
                  clearable
                  style="width: 220px"
                />
              </div>
              <!-- 时间段选择器 -->
              <el-date-picker
                v-model="dateRange"
                type="daterange"
                range-separator="至"
                start-placeholder="开始日期"
                end-placeholder="结束日期"
                value-format="YYYY-MM-DD"
                :clearable="false"
                class="system-log-date-range"
                @change="load"
              />
            </div>

            <div v-if="filteredEvents.length === 0" class="py-12 text-center text-sm text-ink-muted">
              该时间区间内暂无符合条件的业务调用事件
            </div>

            <!-- 事件列表（非折叠，点击抽屉查看，极度丝滑） -->
            <div v-else class="space-y-2.5">
              <div
                v-for="(ev, idx) in paginatedEvents"
                :key="`${ev.ts}-${ev.event}-${idx}`"
                class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-xl border border-line bg-card-soft p-3.5 transition hover:border-brand-500/40 hover:bg-card hover:shadow-subtle cursor-pointer"
                @click="openEventDrawer(ev)"
              >
                <div class="flex items-start sm:items-center gap-3 min-w-0 flex-1">
                  <div
                    class="mt-0.5 sm:mt-0 h-2.5 w-2.5 shrink-0 rounded-full"
                    :class="{
                      'bg-success': eventType(ev.event) === 'success',
                      'bg-danger': eventType(ev.event) === 'danger',
                      'bg-brand-500': eventType(ev.event) === 'primary',
                      'bg-ink-muted': eventType(ev.event) === 'info',
                    }"
                  />
                  <el-tag size="small" :type="(eventType(ev.event) as any)">{{ eventLabel(ev.event) }}</el-tag>
                  <span class="truncate text-sm font-medium text-ink" :title="String(ev.title || ev.event)">
                    {{ ev.title || (isErrorEvent(ev) ? (ev.error || ev.error_message || '发生错误') : '系统操作') }}
                  </span>
                </div>
                <div class="flex items-center gap-4 shrink-0 text-xs text-ink-muted">
                  <span class="font-mono">{{ ev.ts }}</span>
                  <el-button link type="primary" size="small">查看详情 &gt;</el-button>
                </div>
              </div>

              <!-- 分页器 -->
              <div class="mt-5 flex justify-end">
                <el-pagination
                  v-model:current-page="page"
                  v-model:page-size="pageSize"
                  :page-sizes="[20, 50, 100]"
                  layout="total, sizes, prev, pager, next"
                  :total="filteredEvents.length"
                  background
                />
              </div>
            </div>
          </div>
        </el-tab-pane>

        <!-- Tab 2: 终端实时日志 (NoneBot / Linux 终端高亮风格) -->
        <el-tab-pane label="终端实时日志" name="console">
          <div class="app-card p-4 mt-2">
            <!-- 终端顶部控制栏 -->
            <div class="mb-3 flex flex-wrap items-center justify-between gap-3 border-b border-line pb-3">
              <div class="flex flex-wrap items-center gap-2">
                <el-radio-group v-model="consoleLogLevel" size="small">
                  <el-radio-button value="ALL">全部</el-radio-button>
                  <el-radio-button value="INFO">INFO</el-radio-button>
                  <el-radio-button value="SUCCESS">SUCCESS</el-radio-button>
                  <el-radio-button value="WARNING">WARNING</el-radio-button>
                  <el-radio-button value="ERROR">ERROR</el-radio-button>
                </el-radio-group>
                <el-input
                  v-model="consoleKeyword"
                  placeholder="过滤控制台输出..."
                  size="small"
                  clearable
                  style="width: 200px"
                />
              </div>
              <div class="flex items-center gap-2">
                <el-checkbox v-model="autoScroll" label="自动滚动" />
                <el-button size="small" @click="copyConsoleLogs">复制日志</el-button>
                <el-button size="small" type="danger" plain @click="clearConsole">清屏</el-button>
              </div>
            </div>

            <!-- 仿命令行 Terminal 黑色面板 -->
            <div
              ref="terminalBodyRef"
              class="terminal-container rounded-xl bg-[#121316] p-4 font-mono text-xs text-gray-200 overflow-y-auto leading-relaxed select-text"
              style="height: 560px;"
            >
              <div v-if="filteredConsoleLogs.length === 0" class="text-gray-500 py-10 text-center">
                ~ 暂无控制台日志输出 ~
              </div>
              <div
                v-for="(line, idx) in filteredConsoleLogs"
                :key="`${line.created}-${idx}`"
                class="terminal-line py-0.5 hover:bg-white/5 px-1 rounded transition-colors"
              >
                <span class="text-emerald-400 select-none">{{ line.time }}</span>
                <span class="mx-1 select-none font-bold" :class="{
                  'text-blue-400': line.level === 'INFO',
                  'text-emerald-400': line.level === 'SUCCESS',
                  'text-yellow-400': line.level === 'WARNING',
                  'text-red-400': line.level === 'ERROR',
                  'text-cyan-400': line.level === 'DEBUG',
                }">[{{ line.level }}]</span>
                <span class="text-cyan-400 underline select-none mr-2">{{ line.name }}</span>
                <span class="text-gray-100 break-all">{{ line.message }}</span>
              </div>
            </div>
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>

    <!-- 业务日志详情抽屉 Drawer -->
    <el-drawer
      v-model="drawerVisible"
      title="事件调用明细"
      size="480px"
      destroy-on-close
    >
      <div v-if="selectedEvent" class="space-y-4">
        <div class="flex items-center gap-2">
          <el-tag :type="(eventType(selectedEvent.event) as any)">
            {{ eventLabel(selectedEvent.event) }}
          </el-tag>
          <span class="font-mono text-xs text-ink-muted">{{ selectedEvent.ts }}</span>
        </div>

        <div v-if="selectedEvent.title" class="rounded-xl border border-line bg-card-soft p-3">
          <div class="text-xs text-ink-muted">关联题目 / 操作</div>
          <div class="mt-1 text-sm font-semibold text-ink">{{ selectedEvent.title }}</div>
        </div>

        <!-- 结构化字段表格 -->
        <div class="rounded-xl border border-line bg-card-soft p-3">
          <div class="mb-2 text-xs font-semibold text-ink">参数详情</div>
          <div class="space-y-1.5">
            <div
              v-for="d in detailEntries(selectedEvent)"
              :key="d.key"
              class="flex flex-col gap-0.5 text-xs border-b border-line/50 pb-1.5 last:border-b-0 last:pb-0"
            >
              <span class="font-mono font-medium text-ink-muted">{{ d.key }}:</span>
              <span class="break-all font-mono text-ink" :class="d.key.includes('error') ? 'text-danger' : ''">
                {{ d.value }}
              </span>
            </div>
          </div>
        </div>

        <!-- JSON 完整原始数据 -->
        <div class="rounded-xl border border-line bg-card-soft p-3">
          <div class="mb-2 text-xs font-semibold text-ink">原始 JSON Payload</div>
          <pre class="max-h-60 overflow-y-auto rounded bg-canvas p-2 font-mono text-xs text-ink-soft select-all">{{ JSON.stringify(selectedEvent, null, 2) }}</pre>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.system-log-date-range {
  width: 240px !important;
  flex: 0 0 240px;
}

@media (max-width: 768px) {
  .system-log-date-range {
    width: 100% !important;
    flex-basis: 100%;
  }
}

.terminal-container::-webkit-scrollbar {
  width: 6px;
}
.terminal-container::-webkit-scrollbar-thumb {
  background-color: rgba(255, 255, 255, 0.2);
  border-radius: 3px;
}
</style>
