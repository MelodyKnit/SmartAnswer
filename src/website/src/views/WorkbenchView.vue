<script setup lang="ts">
/** 工作台首页：聚合展示 hero、常用功能、数据概览、趋势、题型分布、排行与消息。
 *  全部数据来自 GET /dashboard/workbench（单次聚合），无任何伪造数据。 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import type { EChartsOption } from 'echarts'
import { dashboardApi } from '@/api/endpoints'
import type { Workbench } from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import { questionTypeLabel, relativeTime } from '@/utils/format'
import EChart from '@/components/EChart.vue'
import ImportScriptCopyDialog from '@/components/ImportScriptCopyDialog.vue'

const router = useRouter()
const auth = useAuthStore()
const loading = ref(true)
const data = ref<Workbench | null>(null)
const importScriptDialog = ref<InstanceType<typeof ImportScriptCopyDialog>>()
const scope = ref<'self' | 'global'>(auth.isAdmin ? 'global' : 'self')

const QUICK_ICONS: Record<string, string> = {
  create_api_key: 'Key',
  copy_import_script: 'DocumentCopy',
  generate_script: 'Document',
  interface_status: 'DataLine',
  usage_logs: 'Tickets',
  wallet: 'Wallet',
}
const ROUTE_MAP: Record<string, string> = {
  '/tokens': '/tokens',
  '/import-scripts': '/import-scripts',
  '/status': '/usage-logs',
}

async function load() {
  loading.value = true
  try {
    const res = await dashboardApi.workbench(scope.value)
    data.value = res.workbench
    scope.value = res.workbench.scope
  } finally {
    loading.value = false
  }
}

async function handleQuickAction(action: Workbench['quick_actions'][number]) {
  if (action.requires_role && !auth.hasAccess(action.requires_role)) {
    return
  }
  if (action.action === 'copy_import_script') {
    await importScriptDialog.value?.open()
    return
  }
  router.push(ROUTE_MAP[action.path] ?? action.path)
}

const overviewCards = computed(() => {
  const o = data.value?.overview
  if (!o) return []
  return [
    { label: '今日调用', value: o.today_calls.toLocaleString(), unit: '次', color: 'text-brand-600', icon: 'TrendCharts', chip: 'bg-brand-50 text-brand-600' },
    { label: '成功率', value: o.success_rate, unit: '%', color: 'text-success', icon: 'CircleCheck', chip: 'bg-emerald-50 text-emerald-600 dark:bg-emerald-500/15' },
    { label: '平均响应', value: o.avg_response_seconds, unit: 's', color: 'text-accent-600', icon: 'Timer', chip: 'bg-sky-50 text-sky-600 dark:bg-sky-500/15' },
    { label: '剩余额度', value: o.remaining_points.toLocaleString(), unit: '分', color: 'text-warning', icon: 'Coin', chip: 'bg-amber-50 text-amber-600 dark:bg-amber-500/15' },
  ]
})

const canSwitchScope = computed(() => auth.isAdmin)
const scopeLabel = computed(() => (scope.value === 'global' ? '全站' : '我的'))

const trendOption = computed<EChartsOption>(() => {
  const items = data.value?.trend.items ?? []
  return {
    grid: { left: 36, right: 16, top: 24, bottom: 28 },
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category',
      data: items.map((i) => i.date),
      axisLine: { lineStyle: { color: '#dfe3ec' } },
      axisLabel: { color: '#9aa1b2' },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: '#f0f1f5' } },
      axisLabel: { color: '#9aa1b2' },
    },
    series: [
      {
        type: 'line',
        smooth: true,
        data: items.map((i) => i.count),
        symbolSize: 7,
        lineStyle: { width: 3, color: '#4f6ef7' },
        itemStyle: { color: '#4f6ef7' },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(79,110,247,0.25)' },
              { offset: 1, color: 'rgba(79,110,247,0.02)' },
            ],
          },
        },
      },
    ],
  }
})

const distributionEntries = computed(() => {
  const dist = data.value?.question_distribution ?? {}
  return Object.entries(dist).map(([key, value]) => ({ key, value }))
})
const distributionTotal = computed(() =>
  distributionEntries.value.reduce((sum, e) => sum + e.value, 0),
)

const PIE_COLORS = ['#4f6ef7', '#22c55e', '#a855f7', '#f59e0b', '#06b6d4', '#ef4444']
const donutOption = computed<EChartsOption>(() => ({
  tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
  color: PIE_COLORS,
  series: [
    {
      type: 'pie',
      radius: ['58%', '82%'],
      avoidLabelOverlap: false,
      label: { show: false },
      labelLine: { show: false },
      data: distributionEntries.value.map((e) => ({
        name: questionTypeLabel(e.key),
        value: e.value,
      })),
    },
  ],
}))

onMounted(() => {
  load()
})

watch(
  () => auth.isAdmin,
  (isAdmin) => {
    scope.value = isAdmin ? 'global' : 'self'
  },
)

watch(scope, (_value, oldValue) => {
  if (!oldValue) return
  load()
})
</script>

<template>
  <div v-loading="loading" class="space-y-5">
    <template v-if="data">
      <!-- Hero -->
      <section
        class="relative overflow-hidden rounded-2xl bg-gradient-to-r from-brand-600 via-brand-500 to-accent-600 p-8 text-white shadow-float"
      >
        <h1 class="text-3xl font-bold">{{ data.hero.title }}</h1>
        <p class="mt-3 max-w-xl text-white/85">{{ data.hero.subtitle }}</p>
        <div class="mt-5 flex flex-wrap gap-3">
          <span
            v-for="b in data.hero.badges"
            :key="b"
            class="flex items-center gap-1.5 rounded-full bg-white/15 px-4 py-1.5 text-sm"
          >
            <el-icon><Select /></el-icon>{{ b }}
          </span>
        </div>
        <div class="pointer-events-none absolute -right-16 -top-16 h-64 w-64 rounded-full bg-white/10"></div>
        <div class="pointer-events-none absolute -bottom-20 right-24 h-48 w-48 rounded-full bg-white/10"></div>
      </section>

      <!-- 常用功能 -->
      <section class="app-card p-5">
        <h3 class="mb-4 text-base font-semibold text-ink">常用功能</h3>
        <div class="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          <button
            v-for="q in data.quick_actions.filter((item) => auth.hasAccess(item.requires_role))"
            :key="q.key"
            class="flex flex-col items-center gap-2 rounded-xl border border-line bg-canvas/60 p-4 transition hover:border-brand-300 hover:bg-brand-50"
            @click="handleQuickAction(q)"
          >
            <div
              class="flex h-11 w-11 items-center justify-center rounded-xl bg-brand-100 text-brand-600"
            >
              <el-icon :size="20"><component :is="QUICK_ICONS[q.key] || 'Operation'" /></el-icon>
            </div>
            <span class="text-sm text-ink-soft">{{ q.label }}</span>
          </button>
        </div>
      </section>

      <!-- 数据概览 -->
      <section>
        <div class="mb-3 flex items-center justify-between gap-3">
          <h3 class="text-base font-semibold text-ink">
            数据概览 <span class="text-xs font-normal text-ink-muted">({{ scopeLabel }} / 自然日统计)</span>
          </h3>
          <el-segmented
            v-if="canSwitchScope"
            v-model="scope"
            :options="[
              { label: '全站', value: 'global' },
              { label: '我的', value: 'self' },
            ]"
          />
        </div>
        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div v-for="c in overviewCards" :key="c.label" class="app-card flex items-center justify-between p-5 transition hover:shadow-float">
            <div>
              <div class="text-sm text-ink-soft">{{ c.label }}</div>
              <div class="mt-2 flex items-baseline gap-1">
                <span class="text-3xl font-bold" :class="c.color">{{ c.value }}</span>
                <span class="text-sm text-ink-muted">{{ c.unit }}</span>
              </div>
            </div>
            <div class="flex h-11 w-11 items-center justify-center rounded-xl" :class="c.chip">
              <el-icon :size="22"><component :is="c.icon" /></el-icon>
            </div>
          </div>
        </div>
      </section>

      <!-- 趋势 + 题型分布 -->
      <section class="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <div class="app-card p-5 lg:col-span-2">
          <h3 class="mb-2 text-base font-semibold text-ink">近 {{ data.trend.days }} 日调用趋势 <span class="text-xs font-normal text-ink-muted">({{ scopeLabel }})</span></h3>
          <EChart :option="trendOption" height="280px" />
        </div>
        <div class="app-card p-5">
          <h3 class="mb-2 text-base font-semibold text-ink">题型分布 <span class="text-xs font-normal text-ink-muted">(今日 / {{ scopeLabel }})</span></h3>
          <div v-if="distributionTotal === 0" class="flex h-[280px] items-center justify-center text-sm text-ink-muted">
            今日暂无调用数据
          </div>
          <div v-else>
            <div class="relative" style="height: 220px">
              <EChart :option="donutOption" height="220px" />
              <div
                class="pointer-events-none absolute inset-0 flex flex-col items-center justify-center text-center"
              >
                <div class="text-2xl font-bold text-ink">{{ distributionTotal }}</div>
                <div class="text-xs text-ink-muted">总调用</div>
              </div>
            </div>
            <div class="mt-3 space-y-1.5">
              <div
                v-for="(e, idx) in distributionEntries"
                :key="e.key"
                class="flex items-center justify-between text-sm"
              >
                <span class="flex items-center gap-2 text-ink-soft">
                  <span
                    class="h-2.5 w-2.5 rounded-full"
                    :style="{ background: PIE_COLORS[idx % PIE_COLORS.length] }"
                  ></span>
                  {{ questionTypeLabel(e.key) }}
                </span>
                <span class="text-ink">
                  {{ e.value }}
                  <span class="text-ink-muted">
                    ({{ ((e.value / distributionTotal) * 100).toFixed(1) }}%)
                  </span>
                </span>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- 排行 + 消息 -->
      <section class="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <div class="app-card p-5">
          <div class="mb-3 flex items-center justify-between">
            <h3 class="text-base font-semibold text-ink">排行统计 <span class="text-xs font-normal text-ink-muted">(今日调用次数 / {{ scopeLabel }})</span></h3>
            <el-button link type="primary" size="small" @click="router.push('/usage-logs')">更多</el-button>
          </div>
          <div v-if="data.ranking_preview.length === 0" class="py-10 text-center text-sm text-ink-muted">
            暂无排行数据
          </div>
          <div v-for="r in data.ranking_preview" :key="r.rank" class="flex items-center gap-3 py-2">
            <span
              class="flex h-6 w-6 items-center justify-center rounded-md text-xs font-bold"
              :class="r.rank <= 3 ? 'bg-brand-600 text-white' : 'bg-canvas text-ink-soft'"
            >
              {{ r.rank }}
            </span>
            <span class="flex-1 truncate text-sm text-ink">{{ r.label }}</span>
            <span class="text-sm font-semibold text-ink">{{ r.count }} 次</span>
          </div>
        </div>

        <div class="app-card p-5">
          <div class="mb-3 flex items-center justify-between">
            <h3 class="text-base font-semibold text-ink">消息列表</h3>
            <el-button link type="primary" size="small" @click="load">刷新</el-button>
          </div>
          <div
            v-if="data.notifications_preview.length === 0"
            class="py-10 text-center text-sm text-ink-muted"
          >
            暂无消息
          </div>
          <div
            v-for="n in data.notifications_preview"
            :key="n.notification_id"
            class="border-b border-line py-2.5 last:border-0"
          >
            <div class="flex items-center justify-between">
              <span class="truncate text-sm font-medium text-ink">{{ n.title }}</span>
              <span class="ml-2 shrink-0 text-xs text-ink-muted">{{ relativeTime(n.created_at) }}</span>
            </div>
            <p class="mt-1 line-clamp-1 text-xs text-ink-soft">{{ n.content }}</p>
          </div>
        </div>
      </section>

      <ImportScriptCopyDialog ref="importScriptDialog" />
    </template>
  </div>
</template>
