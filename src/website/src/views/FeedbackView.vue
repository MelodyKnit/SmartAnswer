<script setup lang="ts">
/** 问题反馈管理：普通用户展示自己的反馈，管理员审核所有反馈。 */
import { computed, onMounted, ref, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { ApiException } from '@/api/http'
import { feedbackApi } from '@/api/endpoints'
import type { Feedback } from '@/api/types'
import {
  FEEDBACK_CATEGORIES,
  FEEDBACK_STATUS_META,
  feedbackCategoryLabel,
  feedbackStatusLabel,
  formatDateTime,
} from '@/utils/format'
import PageHeader from '@/components/PageHeader.vue'
import { DEFAULT_PAGE_SIZE } from '@/config/constants'

const auth = useAuthStore()
const loading = ref(false)
const submitting = ref(false)
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

const submitForm = reactive({
  category: 'wrong_answer',
  title: '',
  content: '',
  image_urls_text: '',
})
const submitVisible = ref(false)

function openSubmit() {
  resetSubmitForm()
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
  auth.isAdmin
    ? '处理用户反馈，纠正错题并对有效反馈发放积分奖励。'
    : '提交系统/答题反馈，并跟踪处理进度与结果。',
)

const userSummary = reactive({ total: 0, open: 0, resolved: 0 })

function statusType(status: string): string {
  return FEEDBACK_STATUS_META[status]?.type || 'info'
}

/** 普通用户概览统计：用分页接口的 total 字段分别取总数/待处理/已解决（仅取计数，不取明细）。 */
async function loadUserSummary() {
  if (auth.isAdmin) return
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
    if (auth.isAdmin && filters.username.trim()) {
      params.username = filters.username.trim()
    }
    const res = await feedbackApi.list(params)
    list.value = res.feedbacks
    total.value = res.total
  } finally {
    loading.value = false
  }
}

function resetSubmitForm() {
  submitForm.category = 'wrong_answer'
  submitForm.title = ''
  submitForm.content = ''
  submitForm.image_urls_text = ''
}

async function submitFeedback() {
  if (!submitForm.title.trim() || !submitForm.content.trim()) {
    ElMessage.warning('请填写反馈标题与内容')
    return
  }
  submitting.value = true
  try {
    await feedbackApi.create({
      category: submitForm.category,
      title: submitForm.title.trim(),
      content: submitForm.content.trim(),
      image_urls: submitForm.image_urls_text
        .split(/\r?\n/)
        .map((item) => item.trim())
        .filter(Boolean),
    })
    ElMessage.success('反馈已提交')
    resetSubmitForm()
    submitVisible.value = false
    await refresh()
  } catch (error) {
    ElMessage.error(error instanceof ApiException ? error.message : '提交反馈失败')
  } finally {
    submitting.value = false
  }
}

function openFeedbackDetail(row: Feedback) {
  current.value = row
  if (auth.isAdmin) {
    resolveForm.status = row.status === 'open' ? 'resolved' : row.status
    resolveForm.admin_note = row.admin_note
    resolveForm.corrected_answer = row.corrected_answer
    resolveForm.reward_points = row.reward_points
  }
  resolveVisible.value = true
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
        <el-button v-if="!auth.isAdmin" type="primary" :icon="'EditPen'" @click="openSubmit">
          提交反馈
        </el-button>
        <el-button :icon="'Refresh'" plain @click="refresh">刷新列表</el-button>
      </template>
    </PageHeader>

    <template v-if="!auth.isAdmin">
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
          v-if="auth.isAdmin"
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
        <el-table-column label="标题 / 内容" min-width="260">
          <template #default="{ row }">
            <div class="font-medium text-ink">{{ row.title || '（无标题）' }}</div>
            <div class="line-clamp-2 text-xs text-ink-soft">{{ row.content }}</div>
          </template>
        </el-table-column>
        <el-table-column v-if="auth.isAdmin" label="提交人" width="120" prop="username" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="statusType(row.status) as any">
              {{ feedbackStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="纠正答案" width="130" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.corrected_answer" class="font-medium text-success">
              {{ row.corrected_answer }}
            </span>
            <span v-else class="text-ink-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="奖励积分" width="90">
          <template #default="{ row }">
            <span v-if="row.reward_points > 0" class="font-medium text-warning">
              +{{ row.reward_points }}
            </span>
            <span v-else class="text-ink-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="提交时间" width="170">
          <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="120" align="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openFeedbackDetail(row)">
              {{ auth.isAdmin ? '处理' : '详情' }}
            </el-button>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty :description="auth.isAdmin ? '暂无待处理反馈' : '你还没有提交过反馈'" />
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

    <el-dialog
      v-model="submitVisible"
      title="提交反馈"
      width="560px"
      :close-on-click-modal="false"
    >
      <el-form label-position="top">
        <div class="grid grid-cols-1 gap-x-5 md:grid-cols-2">
          <el-form-item label="反馈类型">
            <el-select v-model="submitForm.category" class="w-full">
              <el-option
                v-for="item in FEEDBACK_CATEGORIES"
                :key="item.value"
                :value="item.value"
                :label="item.label"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="反馈标题">
            <el-input
              v-model="submitForm.title"
              maxlength="60"
              placeholder="例如：某题答案有误 / 页面显示异常"
            />
          </el-form-item>
        </div>
        <el-form-item label="反馈内容">
          <el-input
            v-model="submitForm.content"
            type="textarea"
            :rows="5"
            placeholder="请尽量描述清楚问题现象、题目内容或期望结果。"
          />
        </el-form-item>
        <el-form-item label="图片链接（可选，每行一条）">
          <el-input
            v-model="submitForm.image_urls_text"
            type="textarea"
            :rows="2"
            placeholder="https://example.com/screenshot-1.png"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="submitVisible = false">取消</el-button>
        <el-button @click="resetSubmitForm">重置</el-button>
        <el-button type="primary" :loading="submitting" @click="submitFeedback">
          提交
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="resolveVisible"
      :title="auth.isAdmin ? '处理反馈' : '反馈详情'"
      width="560px"
    >
      <div v-if="current" class="space-y-4">
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

        <el-form v-if="auth.isAdmin" label-position="top">
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
        <el-button @click="resolveVisible = false">{{ auth.isAdmin ? '取消' : '关闭' }}</el-button>
        <el-button v-if="auth.isAdmin" type="primary" :loading="saving" @click="submitResolve">
          保存处理
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>
