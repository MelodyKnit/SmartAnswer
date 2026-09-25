<script setup lang="ts">
/** 问题反馈管理：普通用户展示自己的反馈，管理员审核所有反馈。 */
import { computed, onMounted, ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { ApiException } from '@/api/http'
import { feedbackApi } from '@/api/endpoints'
import type { Feedback, FeedbackRelatedQuestion } from '@/api/types'
import {
  FEEDBACK_CATEGORIES,
  FEEDBACK_STATUS_META,
  feedbackCategoryLabel,
  feedbackStatusLabel,
  formatDateTime,
  questionTypeLabel,
} from '@/utils/format'
import PageHeader from '@/components/PageHeader.vue'
import FeedbackSubmitDialog from '@/components/FeedbackSubmitDialog.vue'
import { DEFAULT_PAGE_SIZE } from '@/config/constants'

const auth = useAuthStore()
const router = useRouter()
const canManageFeedback = computed(() => auth.hasPermission('feedback:manage'))
const loading = ref(false)
const list = ref<Feedback[]>([])
const filters = reactive({
  status: '',
  category: '',
  username: '',
  limit: DEFAULT_PAGE_SIZE.FEEDBACK,
})
const page = ref(1)
const total = ref(0)
const pageSize = computed(() => filters.limit)

const STATUS_OPTIONS = [
  { value: 'open', label: '待处理' },
  { value: 'processing', label: '处理中' },
  { value: 'resolved', label: '已解决' },
  { value: 'rejected', label: '已驳回' },
]

const submitVisible = ref(false)

function openSubmit() {
  submitVisible.value = true
}

const resolveVisible = ref(false)
const saving = ref(false)
const current = ref<Feedback | null>(null)
const resolveForm = reactive({
  status: 'resolved',
  admin_note: '',
  corrected_answer: '',
  reward_points: 0,
})

const pageDescription = computed(() =>
  canManageFeedback.value
    ? '处理用户反馈，纠正错题并对有效反馈发放积分奖励。'
    : '提交系统/答题反馈，并跟踪处理进度与结果。',
)

const userSummary = reactive({ total: 0, open: 0, resolved: 0 })

function statusType(status: string): string {
  return FEEDBACK_STATUS_META[status]?.type || 'info'
}

function feedbackRelations(row: Feedback): FeedbackRelatedQuestion[] {
  if (row.related_questions?.length) return row.related_questions
  if (!row.usage_log_id) return []
  return [
    {
      usage_log_id: row.usage_log_id,
      question_id: row.question_id,
      question_title: row.question_title || '',
      question_type: row.question_type || '',
      answer_snapshot: row.answer_snapshot,
      resolution_mode: row.resolution_mode,
      confidence: row.confidence,
      request_id: row.request_id,
      source_name: row.source_name,
      source_type: row.source_type,
      source_id: row.source_id,
      source_url: row.source_url,
    },
  ]
}

function feedbackQuestionTitle(row: Feedback): string {
  const relation = feedbackRelations(row)[0]
  if (relation?.question_title?.trim()) return relation.question_title
  if (feedbackRelations(row).length) return '已关联使用记录，但未读取到题干'
  return row.title || '（未关联题目）'
}

function feedbackAnswer(row: Feedback): string {
  return feedbackRelations(row)[0]?.answer_snapshot || row.corrected_answer || '—'
}

function relationLabel(row: Feedback): string {
  const relations = feedbackRelations(row)
  if (relations.length > 1) return `已关联 ${relations.length} 条记录`
  if (relations[0]?.question_id) return '已关联题库'
  if (relations.length) return '仅关联记录'
  return '普通反馈'
}

function locateQuestion(row: Feedback, relation = feedbackRelations(row)[0]) {
  if (!relation?.question_id) {
    ElMessage.info('该答题记录未关联题库，只能定位对应的使用记录')
    return
  }
  router.push({
    path: '/questions',
    query: {
      question_id: relation.question_id,
      keyword: relation.question_title || row.title,
      open: 'edit',
    },
  })
}

function locateUsage(row: Feedback, relation = feedbackRelations(row)[0]) {
  if (relation?.usage_log_id) {
    router.push({ path: '/usage-logs', query: { log_id: relation.usage_log_id } })
    return
  }
  const keyword = relation?.question_title?.trim()
  router.push({ path: '/usage-logs', query: keyword ? { keyword } : {} })
}

async function copyQuestionTitle(row: Feedback, relation = feedbackRelations(row)[0]) {
  const text = relation?.question_title?.trim()
  if (!text) {
    ElMessage.warning('当前反馈没有可复制的题干')
    return
  }
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('题干已复制')
  } catch {
    ElMessage.error('复制失败，请手动复制题干')
  }
}

/** 普通用户概览统计：用分页接口的 total 字段分别取总数/待处理/已解决（仅取计数，不取明细）。 */
async function loadUserSummary() {
  if (canManageFeedback.value) return
  try {
    const [all, open, resolved] = await Promise.all([
      feedbackApi.list({ limit: 1, page: 1 }),
      feedbackApi.list({ status: 'open', limit: 1, page: 1 }),
      feedbackApi.list({ status: 'resolved', limit: 1, page: 1 }),
    ])
    userSummary.total = all.total
    userSummary.open = open.total
    userSummary.resolved = resolved.total
  } catch {
    /* 概览失败不影响列表展示 */
  }
}

async function load() {
  loading.value = true
  try {
    const params: Record<string, unknown> = {
      status: filters.status,
      category: filters.category,
      limit: pageSize.value,
      page: page.value,
    }
    if (canManageFeedback.value && filters.username.trim()) {
      params.username = filters.username.trim()
    }
    const res = await feedbackApi.list(params)
    list.value = res.feedbacks
    total.value = res.total
  } finally {
    loading.value = false
  }
}

function openFeedbackDetail(row: Feedback) {
  current.value = row
  if (canManageFeedback.value) {
    resolveForm.status = row.status === 'open' ? 'resolved' : row.status
    resolveForm.admin_note = row.admin_note
    resolveForm.corrected_answer = row.corrected_answer
    resolveForm.reward_points = row.reward_points
  }
  resolveVisible.value = true
}

async function onFeedbackSubmitted() {
  await refresh()
}

async function submitResolve() {
  if (!current.value) return
  saving.value = true
  try {
    const res = await feedbackApi.resolve(current.value.feedback_id, {
      status: resolveForm.status,
      admin_note: resolveForm.admin_note,
      corrected_answer: resolveForm.corrected_answer,
      reward_points: resolveForm.reward_points,
    })
    ElMessage.success(
      res.granted_points > 0
        ? `反馈已处理，并奖励用户 ${res.granted_points} 积分`
        : '反馈已处理',
    )
    resolveVisible.value = false
    await refresh()
  } catch (error) {
    ElMessage.error(error instanceof ApiException ? error.message : '处理反馈失败')
  } finally {
    saving.value = false
  }
}

function onPageChange(next: number) {
  page.value = next
  load()
}

/** 显式查询/回车触发：重置页码并刷新（watch 也会自动触发）。 */
function search() {
  page.value = 1
  refresh()
}

async function refresh() {
  await load()
  await loadUserSummary()
}

onMounted(() => {
  load()
  loadUserSummary()
})
</script>

<template>
  <div class="space-y-5">
    <PageHeader title="反馈中心" :description="pageDescription">
      <template #actions>
        <el-button v-if="!canManageFeedback" type="primary" :icon="'EditPen'" @click="openSubmit">
          提交反馈
        </el-button>
        <el-button :icon="'Refresh'" plain @click="refresh">刷新列表</el-button>
      </template>
    </PageHeader>

    <template v-if="!canManageFeedback">
      <!-- 概览：紧凑横向统计条 -->
      <section class="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div class="app-card flex items-center gap-4 p-4">
          <span class="flex h-11 w-11 items-center justify-center rounded-xl bg-brand-50 text-brand-600 dark:bg-brand-500/15">
            <el-icon :size="20"><ChatDotRound /></el-icon>
          </span>
          <div>
            <div class="text-sm text-ink-soft">我的反馈</div>
            <div class="text-2xl font-bold text-ink">{{ userSummary.total }}</div>
          </div>
        </div>
        <div class="app-card flex items-center gap-4 p-4">
          <span class="flex h-11 w-11 items-center justify-center rounded-xl bg-amber-50 text-warning dark:bg-amber-500/15">
            <el-icon :size="20"><Clock /></el-icon>
          </span>
          <div>
            <div class="text-sm text-ink-soft">待处理</div>
            <div class="text-2xl font-bold text-warning">{{ userSummary.open }}</div>
          </div>
        </div>
        <div class="app-card flex items-center gap-4 p-4">
          <span class="flex h-11 w-11 items-center justify-center rounded-xl bg-emerald-50 text-success dark:bg-emerald-500/15">
            <el-icon :size="20"><CircleCheck /></el-icon>
          </span>
          <div>
            <div class="text-sm text-ink-soft">已解决</div>
            <div class="text-2xl font-bold text-success">{{ userSummary.resolved }}</div>
          </div>
        </div>
      </section>

      <h3 class="px-1 pt-1 text-base font-semibold text-ink">我的反馈记录</h3>
    </template>

    <section class="app-card p-4">
      <div class="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
        <el-select v-model="filters.status" placeholder="全部状态" clearable @change="search">
          <el-option
            v-for="status in STATUS_OPTIONS"
            :key="status.value"
            :value="status.value"
            :label="status.label"
          />
        </el-select>
        <el-select v-model="filters.category" placeholder="全部类型" clearable @change="search">
          <el-option
            v-for="category in FEEDBACK_CATEGORIES"
            :key="category.value"
            :value="category.value"
            :label="category.label"
          />
        </el-select>
        <el-input
          v-if="canManageFeedback"
          v-model="filters.username"
          placeholder="按用户名筛选"
          clearable
          :prefix-icon="'User'"
          @keyup.enter="search"
        />
        <el-button type="primary" :icon="'Search'" @click="search">查询</el-button>
      </div>
    </section>

    <section class="app-card p-1">
      <el-table v-loading="loading" :data="list" style="width: 100%">
        <el-table-column label="类型" width="110">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ feedbackCategoryLabel(row.category) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="题目 / 反馈" min-width="360">
          <template #default="{ row }">
            <div class="flex flex-wrap items-center gap-2">
              <span class="line-clamp-1 font-medium text-ink">
                {{ feedbackQuestionTitle(row) }}
              </span>
              <el-tag size="small" effect="plain">{{ relationLabel(row) }}</el-tag>
            </div>
            <div class="line-clamp-2 text-xs text-ink-soft">
              {{ row.content || row.title }}
            </div>
          </template>
        </el-table-column>
        <el-table-column v-if="canManageFeedback" label="提交人" width="120" prop="username" align="center" />
        <el-table-column label="操作" width="120" align="right">
          <template #default="{ row }">
            <el-tag size="small" :type="statusType(row.status) as any">
              {{ feedbackStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="当前答案" width="150" show-overflow-tooltip align="center">
          <template #default="{ row }">
            <span v-if="feedbackAnswer(row) !== '—'" class="font-medium text-success">
              {{ feedbackAnswer(row) }}
            </span>
            <span v-else class="text-ink-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="奖励积分" width="90" align="center">
          <template #default="{ row }">
            <span v-if="row.reward_points > 0" class="font-medium text-warning">
              +{{ row.reward_points }}
            </span>
            <span v-else class="text-ink-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="提交时间" width="170" align="center">
          <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="120" align="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openFeedbackDetail(row)">
              {{ canManageFeedback ? '处理' : '详情' }}
            </el-button>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty :description="canManageFeedback ? '暂无待处理反馈' : '你还没有提交过反馈'" />
        </template>
      </el-table>
    </section>

    <div v-if="total > 0" class="flex justify-end">
      <el-pagination
        layout="total, prev, pager, next, jumper"
        :total="total"
        :current-page="page"
        :page-size="pageSize"
        background
        @current-change="onPageChange"
      />
    </div>

    <FeedbackSubmitDialog
      v-model="submitVisible"
      @submitted="onFeedbackSubmitted"
    />

    <el-dialog
      v-model="resolveVisible"
      :title="canManageFeedback ? '处理反馈' : '反馈详情'"
      width="560px"
    >
      <div v-if="current" class="space-y-4">
        <div
          v-if="feedbackRelations(current).length"
          class="space-y-3 rounded-lg border border-line bg-card-soft p-3"
        >
          <div class="flex items-center justify-between gap-2">
            <span class="text-sm font-semibold text-ink">答题上下文</span>
            <el-tag size="small" effect="plain">{{ relationLabel(current) }}</el-tag>
          </div>
          <div
            v-for="(relation, index) in feedbackRelations(current)"
            :key="relation.usage_log_id"
            class="rounded border border-line/60 bg-canvas/30 p-3"
          >
            <div class="mb-2 flex flex-wrap items-center justify-between gap-2">
              <span class="text-xs font-semibold text-ink-soft">关联记录 {{ index + 1 }}</span>
              <div class="flex flex-wrap gap-2">
                <el-button
                  size="small"
                  plain
                  :disabled="!relation.question_title?.trim()"
                  @click="copyQuestionTitle(current, relation)"
                >复制题干</el-button>
                <el-button size="small" plain @click="locateUsage(current, relation)">查看记录</el-button>
                <el-button
                  size="small"
                  type="primary"
                  :disabled="!relation.question_id"
                  :title="relation.question_id ? '定位题库记录' : '该记录未关联题库'"
                  @click="locateQuestion(current, relation)"
                >
                  定位题库
                </el-button>
              </div>
            </div>
            <p class="whitespace-pre-wrap text-sm text-ink">
              {{ relation.question_title || '未保存题干' }}
            </p>
            <dl class="mt-3 grid grid-cols-1 gap-2 text-xs text-ink-soft sm:grid-cols-2">
              <div>题库 ID：{{ relation.question_id || '未关联题库' }}</div>
              <div>使用记录：{{ relation.usage_log_id }}</div>
              <div>题型：{{ relation.question_type ? questionTypeLabel(relation.question_type) : '—' }}</div>
              <div>命中方式：{{ relation.resolution_mode || '—' }}</div>
              <div>当时答案：{{ relation.answer_snapshot || '—' }}</div>
              <div>置信度：{{ relation.confidence ? `${Math.round(relation.confidence * 100)}%` : '—' }}</div>
            </dl>
          </div>
        </div>

        <div class="rounded-lg bg-card-soft p-3">
          <div class="mb-2 flex items-center gap-2">
            <el-tag size="small" effect="plain">{{ feedbackCategoryLabel(current.category) }}</el-tag>
            <span class="text-sm font-medium text-ink">{{ current.title || '（无标题）' }}</span>
          </div>
          <p class="whitespace-pre-wrap text-sm text-ink-soft">{{ current.content }}</p>
          <div v-if="current.image_urls.length" class="mt-3 flex flex-wrap gap-2">
            <el-image
              v-for="(url, index) in current.image_urls"
              :key="index"
              :src="url"
              :preview-src-list="current.image_urls"
              :initial-index="index"
              fit="cover"
              class="h-16 w-16 rounded-lg"
            />
          </div>
        </div>

        <el-form v-if="canManageFeedback" label-position="top">
          <el-form-item label="处理状态">
            <el-select v-model="resolveForm.status" class="w-full">
              <el-option
                v-for="status in STATUS_OPTIONS"
                :key="status.value"
                :value="status.value"
                :label="status.label"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="纠正答案">
            <el-input
              v-model="resolveForm.corrected_answer"
              placeholder="针对错题反馈，可填写纠正后的正确答案"
            />
          </el-form-item>
          <el-form-item label="处理说明">
            <el-input
              v-model="resolveForm.admin_note"
              type="textarea"
              :rows="3"
              placeholder="给用户的处理回复"
            />
          </el-form-item>
          <el-form-item label="积分奖励（累计值）">
            <el-input-number v-model="resolveForm.reward_points" :min="0" :step="5" class="w-full" />
            <div class="mt-1 text-xs text-ink-muted">
              系统只补发尚未发放的差额，不会重复奖励。
            </div>
          </el-form-item>
        </el-form>

        <div v-else class="space-y-2 text-sm">
          <div class="flex items-center gap-2">
            <span class="text-ink-muted">当前状态：</span>
            <el-tag size="small" :type="statusType(current.status) as any">
              {{ feedbackStatusLabel(current.status) }}
            </el-tag>
          </div>
          <div v-if="current.corrected_answer">
            <span class="text-ink-muted">纠正答案：</span>
            <span class="font-medium text-success">{{ current.corrected_answer }}</span>
          </div>
          <div v-if="current.admin_note">
            <span class="text-ink-muted">处理说明：</span>
            <span class="text-ink">{{ current.admin_note }}</span>
          </div>
          <div v-if="current.reward_points > 0">
            <span class="text-ink-muted">奖励积分：</span>
            <span class="font-medium text-warning">+{{ current.reward_points }}</span>
          </div>
          <div
            v-if="!current.admin_note && !current.corrected_answer && current.status === 'open'"
            class="text-ink-muted"
          >
            该反馈正在等待处理，请耐心等待。
          </div>
        </div>
      </div>

      <template #footer>
        <el-button @click="resolveVisible = false">{{ canManageFeedback ? '取消' : '关闭' }}</el-button>
        <el-button v-if="canManageFeedback" type="primary" :loading="saving" @click="submitResolve">
          保存处理
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>
