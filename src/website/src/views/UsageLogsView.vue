<script setup lang="ts">
/** API 使用记录。 */
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { mediaApi, tokenApi, usageApi } from '@/api/endpoints'
import type { ApiToken, UsageLog } from '@/api/types'
import {
  formatDateTime,
  questionTypeLabel,
  resolutionLabel,
} from '@/utils/format'
import { Picture } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import FeedbackSubmitDialog from '@/components/FeedbackSubmitDialog.vue'
import { DEFAULT_PAGE_SIZE } from '@/config/constants'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const route = useRoute()
const canViewAllUsage = computed(() => auth.hasPermission('dashboard:all'))
const loading = ref(false)
const logs = ref<UsageLog[]>([])
const tokens = ref<ApiToken[]>([])
const page = ref(1)
const total = ref(0)

const getLocalDateString = (d = new Date()) => {
  const year = d.getFullYear()
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const todayStr = getLocalDateString()
const filters = reactive({
  username: '',
  keyword: '',
  token_id: '',
  dateRange: [todayStr, todayStr] as [string, string] | null,
  limit: DEFAULT_PAGE_SIZE.USAGE_LOGS,
})

async function load() {
  loading.value = true
  try {
    const params: Record<string, unknown> = {
      keyword: filters.keyword,
      limit: filters.limit,
      page: page.value,
    }
    const routeLogId = String(route.query.log_id || '').trim()
    if (routeLogId) params.log_id = routeLogId
    if (canViewAllUsage.value && filters.username.trim()) params.username = filters.username.trim()
    if (filters.token_id) params.token_id = filters.token_id
    if (filters.dateRange && filters.dateRange.length === 2) {
      params.start_date = filters.dateRange[0]
      params.end_date = filters.dateRange[1]
    }
    const [res, toks] = await Promise.all([
      usageApi.logs(params),
      tokenApi.list().catch(() => ({ tokens: [] as ApiToken[] })),
    ])
    logs.value = res.logs
    total.value = res.total
    tokens.value = toks.tokens
  } finally {
    loading.value = false
  }
}

/** 筛选条件变化后回到第一页再查询。 */
function search() {
  page.value = 1
  load()
}

function onPageChange(next: number) {
  page.value = next
  load()
}

/* 明细抽屉 */
const detailVisible = ref(false)
const detail = ref<UsageLog | null>(null)
const imagePreviewUrls = ref<Record<string, string>>({})
let detailImageRequestId = 0

function openDetail(row: UsageLog) {
  detail.value = row
  detailVisible.value = true
  void loadDetailImagePreviews()
}

/** 解析使用记录里保存的「当时选项」（后端以 JSON 字符串数组持久化）。 */
const detailOptions = computed<string[]>(() => {
  const contextOptions = detail.value?.context?.options
  if (Array.isArray(contextOptions)) return contextOptions.map((item) => String(item))
  const raw = detail.value?.options
  if (!raw) return []
  if (Array.isArray(raw)) return raw.map((item) => String(item))
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed.map((item) => String(item)) : []
  } catch {
    return []
  }
})

const detailImageUrls = computed<string[]>(() => {
  const urls = detail.value?.context?.image_urls
  return Array.isArray(urls) ? urls.map((item) => String(item)).filter(Boolean) : []
})

const detailInputFlags = computed<string[]>(() => {
  const flags = detail.value?.context?.input_flags
  return Array.isArray(flags) ? flags.map((item) => String(item)).filter(Boolean) : []
})

function extractImageUrls(value: string): string[] {
  const s = String(value || '')
  const matches = s.match(
    /https?:\/\/[^\s"'<>]+?\.(png|jpe?g|webp|gif|bmp)(\?[^\s"'<>]*)?(?=https?:\/\/|[\s"'<>]|[),.;:!?]|$)/gi,
  )
  return matches
    ? Array.from(new Set(matches.map((item) => item.replace(/[),.;:]+$/g, ''))))
    : []
}

function revokeImagePreviewUrls() {
  Object.values(imagePreviewUrls.value).forEach((url) => URL.revokeObjectURL(url))
  imagePreviewUrls.value = {}
}

function detailImageSourceUrls(): string[] {
  return Array.from(
    new Set([
      ...detailImageUrls.value,
      ...detailOptions.value.flatMap((option) => extractImageUrls(option)),
    ]),
  )
}

function previewImageUrl(url: string): string {
  if (url.startsWith('/') || url.startsWith('data:image/')) return url
  return imagePreviewUrls.value[url] || ''
}

async function loadDetailImagePreviews() {
  const requestId = ++detailImageRequestId
  revokeImagePreviewUrls()
  await Promise.all(
    detailImageSourceUrls()
      .filter((url) => /^https?:\/\//i.test(url))
      .map(async (url) => {
        try {
          const blob = await mediaApi.proxyImage(url)
          const previewUrl = URL.createObjectURL(blob)
          if (requestId !== detailImageRequestId || !detailVisible.value) {
            URL.revokeObjectURL(previewUrl)
            return
          }
          imagePreviewUrls.value = { ...imagePreviewUrls.value, [url]: previewUrl }
        } catch {
          // 单张外链图片不可用不影响使用记录其余内容。
        }
      }),
  )
}

watch(detailVisible, (visible) => {
  if (!visible) {
    detailImageRequestId += 1
    revokeImagePreviewUrls()
  }
})

/* 反馈 */
const fbVisible = ref(false)
const fbContext = ref<UsageLog | null>(null)

function openFeedback(log: UsageLog) {
  fbContext.value = log
  fbVisible.value = true
}

function canSubmitFeedback(log?: UsageLog | null): boolean {
  return Boolean(log && auth.user?.user_id && log.user_id === auth.user.user_id)
}

function resetFilters() {
  filters.username = ''
  filters.keyword = ''
  filters.token_id = ''
  const todayStr = getLocalDateString()
  filters.dateRange = [todayStr, todayStr]
  filters.limit = DEFAULT_PAGE_SIZE.USAGE_LOGS
  page.value = 1
  load()
}

function compactTokenId(tokenId?: string | null) {
  if (!tokenId) return ''
  return tokenId.length <= 12 ? tokenId : `${tokenId.slice(0, 8)}...${tokenId.slice(-4)}`
}

function tokenLabel(log?: UsageLog | null) {
  if (!log?.token_id) return '—'
  const token = tokens.value.find((item) => item.token_id === log.token_id)
  return log.token_label || token?.description || token?.key_mask || compactTokenId(log.token_id) || '—'
}

function tokenTooltip(log: UsageLog) {
  const parts = [
    log.token_description ? `描述：${log.token_description}` : '',
    log.token_key_mask ? `密钥：${log.token_key_mask}` : '',
    log.token_id ? `ID：${log.token_id}` : '',
  ].filter(Boolean)
  return parts.join('\n') || tokenLabel(log)
}

onMounted(() => {
  const logId = String(route.query.log_id || '').trim()
  if (logId) {
    // 精确定位历史记录时不能沿用页面默认的“今天”筛选。
    filters.dateRange = null
  }
  const keyword = String(route.query.keyword || '').trim()
  if (keyword && !logId) {
    filters.keyword = keyword
  }
  load()
})

onUnmounted(revokeImagePreviewUrls)
</script>

<template>
  <div class="flex h-full flex-col min-h-0">
    <PageHeader title="使用记录" description="查看答题调用流水、命中方式与积分消耗。" />

    <div class="app-card mb-3 shrink-0 flex flex-wrap items-center gap-3 p-4">
      <el-input
        v-if="canViewAllUsage"
        v-model="filters.username"
        placeholder="按用户名筛选"
        clearable
        class="!w-48"
        :prefix-icon="'User'"
        @keyup.enter="search"
      />
      <el-input
        v-model="filters.keyword"
        placeholder="按题目关键词筛选"
        clearable
        class="!w-60"
        :prefix-icon="'Search'"
        @keyup.enter="search"
      />
      <el-date-picker
        v-model="filters.dateRange"
        type="daterange"
        range-separator="至"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
        value-format="YYYY-MM-DD"
        :clearable="false"
        class="usage-date-range"
        @change="search"
      />
      <el-select
        v-model="filters.token_id"
        placeholder="按 API Key 筛选"
        clearable
        class="!w-56"
        @change="search"
      >
        <el-option
          v-for="token in tokens"
          :key="token.token_id"
          :value="token.token_id"
          :label="token.description || token.key_mask"
        />
      </el-select>
      <el-select v-model="filters.limit" class="!w-32" @change="search">
        <el-option :value="10" label="每页 10 条" />
        <el-option :value="20" label="每页 20 条" />
        <el-option :value="50" label="每页 50 条" />
        <el-option :value="100" label="每页 100 条" />
      </el-select>
      <el-button type="primary" :icon="'Search'" @click="search">查询</el-button>
    </div>

    <div class="app-card min-h-0 flex-1 flex flex-col p-1">
      <div class="min-h-0 flex-1">
        <el-table v-loading="loading" :data="logs" height="100%" style="width: 100%">
          <el-table-column label="题目" min-width="240" show-overflow-tooltip>
            <template #default="{ row }">
            <span class="text-ink truncate block">{{ row.title || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="canViewAllUsage" label="用户" width="140" show-overflow-tooltip align="center">
          <template #default="{ row }">
            <span class="truncate block text-ink-soft">{{ row.username || '—' }}</span>
          </template>
        </el-table-column>
          <el-table-column label="令牌" width="150" show-overflow-tooltip align="center">
            <template #default="{ row }">
              <span class="text-ink-soft" :title="tokenTooltip(row)">
                {{ tokenLabel(row) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="题型" width="90" align="center">
            <template #default="{ row }">
              <el-tag size="small" effect="plain">{{ questionTypeLabel(row.question_type) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="命中方式" width="110" align="center">
            <template #default="{ row }">
              <el-tag size="small" type="success" effect="light">
                {{ resolutionLabel(row.resolution_mode) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="答案" width="110" show-overflow-tooltip align="center">
            <template #default="{ row }">
              <span class="font-medium text-success">{{ row.answer || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="请求 IP" width="130" show-overflow-tooltip align="center">
            <template #default="{ row }">
              <span class="text-ink-soft">{{ row.client_ip || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="置信度" width="90" align="center">
            <template #default="{ row }">{{ (row.confidence * 100).toFixed(0) }}%</template>
          </el-table-column>
          <el-table-column label="积分" width="70" prop="points_cost" align="center" />
          <el-table-column label="时间" width="170" align="center">
            <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="130" align="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="openDetail(row)">明细</el-button>
              <el-button
                link
                type="primary"
                :disabled="!canSubmitFeedback(row)"
                :title="canSubmitFeedback(row) ? '提交反馈' : '只能关联自己的答题记录'"
                @click="openFeedback(row)"
              >反馈</el-button>
            </template>
          </el-table-column>
          <template #empty>
            <el-empty description="暂无使用记录" />
          </template>
        </el-table>
      </div>

      <div v-if="total > 0" class="shrink-0 flex justify-end border-t border-line px-4 py-3">
        <el-pagination
          layout="total, prev, pager, next, jumper"
          :total="total"
          :current-page="page"
          :page-size="filters.limit"
          background
          @current-change="onPageChange"
        />
      </div>
    </div>

    <!-- 明细抽屉 -->
    <el-drawer v-model="detailVisible" title="搜题明细" size="420px">
      <div v-if="detail" class="space-y-4 text-sm">
        <div>
          <div class="mb-1 text-ink-muted">题目</div>
          <p class="whitespace-pre-wrap rounded-lg bg-card-soft p-3 text-ink">{{ detail.title || '—' }}</p>
        </div>
        <div v-if="detailInputFlags.length" class="rounded-lg border border-warning/30 bg-warning/10 p-3">
          <div class="mb-2 text-sm font-semibold text-warning">输入异常</div>
          <div class="flex flex-wrap gap-2">
            <el-tag
              v-for="flag in detailInputFlags"
              :key="flag"
              size="small"
              type="warning"
              effect="light"
            >
              {{ flag }}
            </el-tag>
          </div>
          <p v-if="detail.context?.error_message" class="mt-2 text-ink-muted">
            {{ detail.context.error_message }}
          </p>
        </div>
        <div v-if="detailOptions.length">
          <div class="mb-1 text-ink-muted">选项（搜题当时）</div>
          <ul class="space-y-2 rounded-lg bg-card-soft p-3">
            <li
              v-for="(opt, index) in detailOptions"
              :key="index"
              class="break-all text-ink space-y-1.5 border-b border-line/40 pb-2 last:border-b-0 last:pb-0"
            >
              <div class="leading-relaxed">{{ opt }}</div>
              <div v-if="extractImageUrls(opt).length" class="flex flex-wrap gap-2 pt-1">
                <template v-for="(imgUrl, imgIdx) in extractImageUrls(opt)" :key="imgIdx">
                  <el-image
                    v-if="previewImageUrl(imgUrl)"
                    :src="previewImageUrl(imgUrl)"
                    :preview-src-list="[previewImageUrl(imgUrl)]"
                    fit="contain"
                    preview-teleported
                    class="h-20 max-w-full rounded border border-line bg-card p-1 shadow-sm"
                  >
                    <template #error>
                      <div class="flex h-20 w-20 items-center justify-center rounded bg-canvas text-xs text-ink-muted">
                        <el-icon><Picture /></el-icon>
                      </div>
                    </template>
                  </el-image>
                  <div
                    v-else
                    class="flex h-20 w-20 items-center justify-center rounded border border-line bg-canvas text-xs text-ink-muted"
                    title="图片加载中或不可用"
                  >
                    <el-icon><Picture /></el-icon>
                  </div>
                </template>
              </div>
            </li>
          </ul>
        </div>
        <div v-if="detailImageUrls.length">
          <div class="mb-1 text-ink-muted">图片上下文</div>
          <div class="flex flex-col gap-3 rounded-lg bg-card-soft p-3">
            <div v-for="(url, idx) in detailImageUrls" :key="idx" class="space-y-1 max-w-full">
              <el-image
                v-if="previewImageUrl(url)"
                :src="previewImageUrl(url)"
                :preview-src-list="[previewImageUrl(url)]"
                fit="contain"
                preview-teleported
                class="h-24 max-w-full rounded border border-line bg-card p-1 shadow-sm"
              >
                <template #error>
                  <div class="flex h-24 w-24 items-center justify-center rounded bg-canvas text-xs text-ink-muted">
                    <el-icon><Picture /></el-icon>
                  </div>
                </template>
              </el-image>
              <div
                v-else
                class="flex h-24 w-24 items-center justify-center rounded border border-line bg-canvas text-xs text-ink-muted"
                title="图片加载中或不可用"
              >
                <el-icon><Picture /></el-icon>
              </div>
              <div class="break-all font-mono text-xs text-ink-muted select-all leading-tight">{{ url }}</div>
            </div>
          </div>
        </div>
        <div class="rounded-lg bg-success/10 p-3">
          <div class="text-ink-muted">答案</div>
          <div class="mt-1 text-lg font-bold text-success">{{ detail.answer || '—' }}</div>
        </div>
        <dl class="space-y-2">
          <div class="flex justify-between border-b border-line pb-2">
            <dt class="text-ink-muted">题型</dt>
            <dd class="text-ink">{{ questionTypeLabel(detail.question_type) }}</dd>
          </div>
          <div class="flex justify-between border-b border-line pb-2">
            <dt class="text-ink-muted">检索/命中方式</dt>
            <dd><el-tag size="small" type="success" effect="light">{{ resolutionLabel(detail.resolution_mode) }}</el-tag></dd>
          </div>
          <div class="flex justify-between border-b border-line pb-2">
            <dt class="text-ink-muted">准确率（置信度）</dt>
            <dd class="text-ink">{{ (detail.confidence * 100).toFixed(0) }}%</dd>
          </div>
          <div v-if="canViewAllUsage" class="flex justify-between border-b border-line pb-2">
            <dt class="text-ink-muted">使用者</dt>
            <dd class="text-ink">{{ detail.username }}</dd>
          </div>
          <div class="flex justify-between border-b border-line pb-2">
            <dt class="text-ink-muted">请求 IP</dt>
            <dd class="text-ink">{{ detail.client_ip || '—' }}</dd>
          </div>
          <div class="flex justify-between border-b border-line pb-2">
            <dt class="text-ink-muted">使用的 API Key</dt>
            <dd class="text-ink">{{ tokenLabel(detail) }}</dd>
          </div>
          <div class="flex justify-between border-b border-line pb-2">
            <dt class="text-ink-muted">消耗积分</dt>
            <dd class="font-medium text-warning">{{ detail.points_cost }}</dd>
          </div>
          <div class="flex justify-between border-b border-line pb-2">
            <dt class="text-ink-muted">提供方</dt>
            <dd class="text-ink">{{ detail.provider || '—' }}</dd>
          </div>
          <div class="flex justify-between">
            <dt class="text-ink-muted">时间</dt>
            <dd class="text-ink">{{ formatDateTime(detail.created_at) }}</dd>
          </div>
        </dl>
        <el-button
          type="primary"
          class="w-full"
          :disabled="!canSubmitFeedback(detail)"
          @click="openFeedback(detail)"
        >
          {{ canSubmitFeedback(detail) ? '就此题提交反馈' : '仅可反馈自己的答题记录' }}
        </el-button>
      </div>
    </el-drawer>

    <FeedbackSubmitDialog v-model="fbVisible" :initial-record="fbContext" />
  </div>
</template>

<style scoped>
.usage-date-range {
  width: 240px !important;
  flex: 0 0 240px;
}

@media (max-width: 768px) {
  .usage-date-range {
    width: 100% !important;
    flex-basis: 100%;
  }
}
</style>
