<script setup lang="ts">
/** API 使用记录。 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { feedbackApi, tokenApi, usageApi } from '@/api/endpoints'
import type { ApiToken, UsageLog } from '@/api/types'
import { ApiException } from '@/api/http'
import {
  FEEDBACK_CATEGORIES,
  formatDateTime,
  questionTypeLabel,
  resolutionLabel,
} from '@/utils/format'
import PageHeader from '@/components/PageHeader.vue'
import { DEFAULT_PAGE_SIZE } from '@/config/constants'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const route = useRoute()
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
    if (auth.isAdmin && filters.username.trim()) params.username = filters.username.trim()
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
function openDetail(row: UsageLog) {
  detail.value = row
  detailVisible.value = true
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

/* 反馈 */
const fbVisible = ref(false)
const fbSubmitting = ref(false)
const fbContext = ref<UsageLog | null>(null)
const fbForm = reactive({
  usage_log_id: '' as string | null,
  category: 'wrong_answer',
  title: '',
  content: '',
})

function openFeedback(log: UsageLog) {
  fbContext.value = log
  fbForm.usage_log_id = log.log_id
  fbForm.category = 'wrong_answer'
  fbForm.title = '题目反馈'
  fbForm.content = ''
  fbVisible.value = true
}

async function submitFeedback() {
  if (!fbForm.content.trim()) {
    ElMessage.warning('请填写反馈内容')
    return
  }
  fbSubmitting.value = true
  try {
    await feedbackApi.create({
      usage_log_id: fbForm.usage_log_id,
      category: fbForm.category,
      title: fbForm.title,
      content: fbForm.content,
    })
    ElMessage.success('反馈已提交')
    fbVisible.value = false
  } catch (err) {
    ElMessage.error(err instanceof ApiException ? err.message : '提交失败')
  } finally {
    fbSubmitting.value = false
  }
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
  const keyword = String(route.query.keyword || '').trim()
  if (keyword) {
    filters.keyword = keyword
  }
  load()
})
</script>

<template>
  <div>
    <PageHeader title="使用记录" description="查看答题调用流水、命中方式与积分消耗。" />

    <div class="app-card mb-4 flex flex-wrap items-center gap-3 p-4">
      <el-input
        v-if="auth.isAdmin"
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

    <div class="app-card p-1">
      <el-table v-loading="loading" :data="logs" style="width: 100%">
        <el-table-column label="题目" min-width="240" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="text-ink">{{ row.title || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="auth.isAdmin" label="用户" width="120" prop="username" align="center" />
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
            <el-button link type="primary" @click="openFeedback(row)">反馈</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="暂无使用记录" />
        </template>
      </el-table>
    </div>

    <div v-if="total > 0" class="mt-4 flex justify-end">
      <el-pagination
        layout="total, prev, pager, next, jumper"
        :total="total"
        :current-page="page"
        :page-size="filters.limit"
        background
        @current-change="onPageChange"
      />
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
          <ul class="space-y-1 rounded-lg bg-card-soft p-3">
            <li
              v-for="(opt, index) in detailOptions"
              :key="index"
              class="text-ink"
            >
              {{ opt }}
            </li>
          </ul>
        </div>
        <div v-if="detailImageUrls.length">
          <div class="mb-1 text-ink-muted">图片上下文</div>
          <ul class="space-y-1 rounded-lg bg-card-soft p-3">
            <li
              v-for="url in detailImageUrls"
              :key="url"
              class="break-all text-ink"
            >
              {{ url }}
            </li>
          </ul>
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
          <div v-if="auth.isAdmin" class="flex justify-between border-b border-line pb-2">
            <dt class="text-ink-muted">使用者</dt>
            <dd class="text-ink">{{ detail.username }}</dd>
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
        <el-button type="primary" class="w-full" @click="openFeedback(detail)">就此题提交反馈</el-button>
      </div>
    </el-drawer>

    <el-dialog v-model="fbVisible" title="提交反馈" width="480px">
      <el-form label-position="top">
        <div v-if="fbContext" class="mb-4 rounded-lg border border-line bg-card-soft p-3">
          <div class="mb-2 flex items-center justify-between gap-3">
            <span class="text-sm font-semibold text-ink">关联题目</span>
            <el-tag size="small" effect="plain">
              {{ fbContext.question_id ? '已关联题库' : '未关联题库' }}
            </el-tag>
          </div>
          <p class="line-clamp-3 text-sm text-ink">{{ fbContext.title }}</p>
          <div class="mt-3 grid grid-cols-1 gap-2 text-xs text-ink-soft sm:grid-cols-2">
            <span>题型：{{ questionTypeLabel(fbContext.question_type) }}</span>
            <span>命中：{{ resolutionLabel(fbContext.resolution_mode) }}</span>
            <span>答案：{{ fbContext.answer || '—' }}</span>
            <span>题库 ID：{{ fbContext.question_id || '—' }}</span>
          </div>
        </div>
        <el-form-item label="反馈类型">
          <el-select v-model="fbForm.category" class="w-full">
            <el-option
              v-for="c in FEEDBACK_CATEGORIES"
              :key="c.value"
              :value="c.value"
              :label="c.label"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="反馈内容">
          <el-input
            v-model="fbForm.content"
            type="textarea"
            :rows="4"
            placeholder="请描述问题，例如：该题答案不正确，正确答案应为……"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="fbVisible = false">取消</el-button>
        <el-button type="primary" :loading="fbSubmitting" @click="submitFeedback">提交</el-button>
      </template>
    </el-dialog>
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
