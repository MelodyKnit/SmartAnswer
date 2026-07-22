<script setup lang="ts">
/** 在线搜题结果面板：集中处理空、加载、失败和成功四种展示状态。 */
import { computed, ref } from 'vue'
import {
  CircleCheckFilled,
  DocumentChecked,
  InfoFilled,
  Link as LinkIcon,
  Loading,
  RefreshRight,
  Search,
  WarningFilled,
} from '@element-plus/icons-vue'
import type { QueryResultPayload } from '@/api/types'
import { resolutionLabel } from '@/utils/format'

const props = defineProps<{
  result: QueryResultPayload | null
  loading: boolean
  errorMessage: string
}>()

defineEmits<{
  retry: []
  clear: []
}>()

const activeDebug = ref<string[]>([])

const answer = computed(() => {
  if (!props.result) return ''
  return props.result.result.candidate_answer || props.result.result.answer_text || '—'
})

const confidencePercent = computed(() =>
  props.result ? Math.round(props.result.result.confidence * 100) : 0,
)

const confidenceStatus = computed(() => {
  if (confidencePercent.value >= 90) return 'success'
  if (confidencePercent.value >= 60) return 'warning'
  return 'exception'
})

const debugEntries = computed(() => Object.entries(props.result?.debug ?? {}))
</script>

<template>
  <section class="app-card flex min-h-[460px] flex-col overflow-hidden">
    <div class="flex items-start justify-between gap-4 border-b border-line bg-canvas/30 px-5 py-4">
      <div>
        <p class="text-xs font-semibold uppercase tracking-[0.18em] text-brand-500">Search Result</p>
        <h3 class="mt-1 text-lg font-semibold text-ink">搜题结果</h3>
      </div>
      <el-tag v-if="loading" type="info" effect="plain">
        <el-icon class="mr-1 animate-spin"><Loading /></el-icon>
        检索中
      </el-tag>
      <el-tag v-else-if="result" type="success" effect="light">已返回</el-tag>
      <el-tag v-else-if="errorMessage" type="danger" effect="light">未获取到答案</el-tag>
      <el-tag v-else type="info" effect="plain">等待输入</el-tag>
    </div>

    <div class="flex flex-1 flex-col p-5">
      <div v-if="loading" class="space-y-5">
        <div class="rounded-2xl border border-line bg-card-soft p-5">
          <el-skeleton :rows="3" animated />
        </div>
        <div class="grid gap-3 sm:grid-cols-3">
          <div v-for="i in 3" :key="i" class="rounded-xl border border-line bg-canvas/40 p-4">
            <el-skeleton :rows="1" animated />
          </div>
        </div>
        <div class="rounded-2xl border border-line bg-canvas/40 p-5">
          <el-skeleton :rows="4" animated />
        </div>
      </div>

      <div v-else-if="errorMessage" class="flex flex-1 items-center justify-center">
        <div class="max-w-md text-center">
          <div class="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-danger/10 text-danger">
            <el-icon size="28"><WarningFilled /></el-icon>
          </div>
          <h4 class="mt-4 text-lg font-semibold text-ink">这次没有拿到可用答案</h4>
          <p class="mt-2 text-sm leading-6 text-ink-soft">{{ errorMessage }}</p>
          <div class="mt-5 flex justify-center gap-3">
            <el-button type="primary" @click="$emit('retry')">
              <el-icon class="mr-1"><RefreshRight /></el-icon>
              重新搜题
            </el-button>
            <el-button @click="$emit('clear')">清空输入</el-button>
          </div>
        </div>
      </div>

      <div v-else-if="result" class="flex flex-1 flex-col gap-5">
        <div class="relative overflow-hidden rounded-2xl border border-success/30 bg-success/10 p-5">
          <div class="pointer-events-none absolute -right-10 -top-10 h-32 w-32 rounded-full bg-success/20 blur-2xl" />
          <div class="relative flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
            <div class="min-w-0 flex-1">
              <div class="flex flex-wrap items-center gap-2">
                <el-icon class="text-success"><CircleCheckFilled /></el-icon>
                <span class="text-sm font-medium text-success">推荐答案</span>
                <el-tag v-if="result.result.review_required" size="small" type="warning" effect="light">
                  建议人工复核
                </el-tag>
              </div>
              <div class="mt-3 break-words text-3xl font-bold leading-tight text-success">
                {{ answer }}
              </div>
              <p
                v-if="result.result.answer_text && result.result.answer_text !== answer"
                class="mt-3 whitespace-pre-wrap text-sm leading-6 text-ink"
              >
                {{ result.result.answer_text }}
              </p>
            </div>
            <div class="w-full rounded-xl border border-line bg-card/80 p-4 lg:w-48">
              <div class="mb-2 flex items-center justify-between text-xs text-ink-muted">
                <span>置信度</span>
                <span class="font-semibold text-ink">{{ confidencePercent }}%</span>
              </div>
              <el-progress
                :percentage="confidencePercent"
                :status="confidenceStatus"
                :stroke-width="10"
                :show-text="false"
              />
              <div class="mt-3 text-xs text-ink-soft">
                {{ confidencePercent >= 90 ? '高可信，可优先采用' : '请结合解析和来源复核' }}
              </div>
            </div>
          </div>
        </div>

        <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          <div class="rounded-xl border border-line bg-canvas/40 p-4">
            <div class="flex items-center gap-2 text-xs text-ink-muted">
              <el-icon><DocumentChecked /></el-icon>
              命中方式
            </div>
            <div class="mt-2 text-sm font-semibold text-ink">
              {{ resolutionLabel(result.result.resolution_mode) }}
            </div>
          </div>
          <div class="rounded-xl border border-line bg-canvas/40 p-4">
            <div class="flex items-center gap-2 text-xs text-ink-muted">
              <el-icon><Search /></el-icon>
              题型
            </div>
            <div class="mt-2 text-sm font-semibold text-ink">{{ result.query.type || '未知' }}</div>
          </div>
          <div class="rounded-xl border border-line bg-canvas/40 p-4 sm:col-span-2 xl:col-span-1">
            <div class="flex items-center gap-2 text-xs text-ink-muted">
              <el-icon><InfoFilled /></el-icon>
              请求编号
            </div>
            <div class="mt-2 truncate text-sm font-semibold text-ink" :title="result.request_id || '—'">
              {{ result.request_id || '—' }}
            </div>
          </div>
        </div>

        <div v-if="result.result.explanation" class="rounded-2xl border border-line bg-card-soft p-5">
          <div class="mb-3 flex items-center gap-2 text-sm font-semibold text-ink">
            <el-icon class="text-brand-500"><DocumentChecked /></el-icon>
            答案解析
          </div>
          <p class="whitespace-pre-wrap text-sm leading-7 text-ink-soft">
            {{ result.result.explanation }}
          </p>
        </div>

        <div v-if="result.sources.length" class="rounded-2xl border border-line bg-canvas/40 p-5">
          <div class="mb-3 flex items-center gap-2 text-sm font-semibold text-ink">
            <el-icon class="text-brand-500"><LinkIcon /></el-icon>
            参考来源
          </div>
          <div class="grid gap-3 md:grid-cols-2">
            <a
              v-for="(source, index) in result.sources"
              :key="`${source.source_name}-${index}`"
              class="group rounded-xl border border-line bg-card/70 p-4 transition-colors hover:border-brand-500/70"
              :class="{ 'cursor-pointer': source.source_url }"
              :href="source.source_url || undefined"
              :target="source.source_url ? '_blank' : undefined"
              rel="noreferrer"
            >
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <div class="truncate text-sm font-semibold text-ink group-hover:text-brand-500">
                    {{ source.source_name }}
                  </div>
                  <div class="mt-1 text-xs text-ink-muted">{{ source.source_type || 'source' }}</div>
                </div>
                <el-tag size="small" effect="plain">{{ (source.score * 100).toFixed(0) }}%</el-tag>
              </div>
            </a>
          </div>
        </div>

        <el-collapse v-if="debugEntries.length" v-model="activeDebug" class="online-search-debug">
          <el-collapse-item title="诊断信息" name="debug">
            <dl class="grid gap-3 text-xs md:grid-cols-2">
              <div
                v-for="[key, value] in debugEntries"
                :key="key"
                class="rounded-lg border border-line bg-canvas/40 p-3"
              >
                <dt class="font-medium text-ink-muted">{{ key }}</dt>
                <dd class="mt-1 break-all text-ink-soft">{{ value }}</dd>
              </div>
            </dl>
          </el-collapse-item>
        </el-collapse>
      </div>

      <div v-else class="flex flex-1 items-center justify-center">
        <div class="max-w-sm text-center">
          <div class="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl border border-line bg-card-soft text-brand-500">
            <el-icon size="30"><Search /></el-icon>
          </div>
          <h4 class="mt-4 text-lg font-semibold text-ink">等待输入题目</h4>
          <p class="mt-2 text-sm leading-6 text-ink-soft">
            在左侧粘贴题干，选项可一并粘贴；答案、来源和置信度会在这里集中展示。
          </p>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.animate-spin {
  animation: spin 1s linear infinite;
}

.online-search-debug :deep(.el-collapse),
.online-search-debug :deep(.el-collapse-item__wrap) {
  border-color: var(--c-line);
  background: transparent;
}

.online-search-debug :deep(.el-collapse-item__header) {
  border-color: var(--c-line);
  background: transparent;
  color: var(--c-ink-soft);
  font-weight: 600;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
