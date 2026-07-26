<script setup lang="ts">
/** 公告管理：管理员维护系统公告、展示时间和投放范围。 */
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { announcementApi } from '@/api/endpoints'
import { ApiException } from '@/api/http'
import type {
  Announcement,
  AnnouncementAudience,
  AnnouncementAudienceOption,
  AnnouncementLevel,
  AnnouncementStatus,
} from '@/api/types'
import PageHeader from '@/components/PageHeader.vue'
import { DEFAULT_PAGE_SIZE } from '@/config/constants'
import { formatDateTime } from '@/utils/format'

const loading = ref(false)
const saving = ref(false)
const drawerVisible = ref(false)
const editing = ref<Announcement | null>(null)
const announcements = ref<Announcement[]>([])
const total = ref(0)
const page = ref(1)
const audienceOptions = ref<AnnouncementAudienceOption[]>([{ value: 'all', label: '全部用户' }])

const filters = reactive({
  keyword: '',
  status: '',
  level: '',
  audience: '',
  limit: DEFAULT_PAGE_SIZE.QUESTIONS,
})

const form = reactive<{
  title: string
  content: string
  level: AnnouncementLevel
  audience: AnnouncementAudience
  status: AnnouncementStatus
  pinned: boolean
  starts_at_ms: string | number
  ends_at_ms: string | number
}>({
  title: '',
  content: '',
  level: 'info',
  audience: 'all',
  status: 'draft',
  pinned: false,
  starts_at_ms: '',
  ends_at_ms: '',
})

const levelOptions: { value: AnnouncementLevel; label: string; type: string }[] = [
  { value: 'info', label: '通知', type: 'info' },
  { value: 'success', label: '更新', type: 'success' },
  { value: 'warning', label: '提醒', type: 'warning' },
  { value: 'danger', label: '重要', type: 'danger' },
]

const statusOptions: { value: AnnouncementStatus; label: string; type: string }[] = [
  { value: 'draft', label: '草稿', type: 'info' },
  { value: 'published', label: '已发布', type: 'success' },
  { value: 'archived', label: '已归档', type: 'warning' },
]

const drawerTitle = computed(() => (editing.value ? '编辑公告' : '新增公告'))
const preview = computed<Announcement>(() => ({
  announcement_id: editing.value?.announcement_id || 'preview',
  title: form.title || '公告标题',
  content: form.content || '公告内容将在这里预览。',
  level: form.level,
  audience: form.audience,
  status: form.status,
  pinned: form.pinned,
  starts_at: secondsFromMilliseconds(form.starts_at_ms),
  ends_at: secondsFromMilliseconds(form.ends_at_ms),
  created_by: editing.value?.created_by || '',
  created_at: editing.value?.created_at || 0,
  updated_at: editing.value?.updated_at || 0,
  published_at: editing.value?.published_at || 0,
}))

function levelMeta(level: string) {
  return levelOptions.find((item) => item.value === level) ?? levelOptions[0]
}

function audienceLabel(value: string) {
  return audienceOptions.value.find((item) => item.value === value)?.label || value
}

function statusMeta(status: string) {
  return statusOptions.find((item) => item.value === status) ?? statusOptions[0]
}

function secondsFromMilliseconds(value: string | number) {
  if (!value) return 0
  const parsed = Math.floor(Number(value) / 1000)
  return Number.isFinite(parsed) ? parsed : 0
}

function millisecondsFromSeconds(value: number) {
  return value ? Math.floor(value * 1000) : ''
}

function timeRange(row: Announcement) {
  if (!row.starts_at && !row.ends_at) return '长期有效'
  if (row.starts_at && row.ends_at) {
    return `${formatDateTime(row.starts_at)} 至 ${formatDateTime(row.ends_at)}`
  }
  if (row.starts_at) return `${formatDateTime(row.starts_at)} 起`
  return `${formatDateTime(row.ends_at)} 前有效`
}

function resetForm(row?: Announcement) {
  editing.value = row ?? null
  form.title = row?.title ?? ''
  form.content = row?.content ?? ''
  form.level = row?.level ?? 'info'
  form.audience = row?.audience ?? 'all'
  form.status = row?.status ?? 'draft'
  form.pinned = row?.pinned ?? false
  form.starts_at_ms = row ? millisecondsFromSeconds(row.starts_at) : ''
  form.ends_at_ms = row ? millisecondsFromSeconds(row.ends_at) : ''
}

function openCreate() {
  resetForm()
  drawerVisible.value = true
}

function openEdit(row: Announcement) {
  resetForm(row)
  drawerVisible.value = true
}

async function load() {
  loading.value = true
  try {
    const res = await announcementApi.list({
      keyword: filters.keyword.trim() || undefined,
      status: filters.status || undefined,
      level: filters.level || undefined,
      audience: filters.audience || undefined,
      page: page.value,
      limit: filters.limit,
    })
    announcements.value = res.announcements
    audienceOptions.value = res.audience_options
    total.value = res.total
  } catch (error) {
    ElMessage.error(error instanceof ApiException ? error.message : '加载公告失败')
  } finally {
    loading.value = false
  }
}

function search() {
  page.value = 1
  load()
}

function resetFilters() {
  filters.keyword = ''
  filters.status = ''
  filters.level = ''
  filters.audience = ''
  filters.limit = DEFAULT_PAGE_SIZE.QUESTIONS
  page.value = 1
  load()
}

async function submit() {
  saving.value = true
  const body = {
    title: form.title.trim(),
    content: form.content.trim(),
    level: form.level,
    audience: form.audience,
    status: form.status,
    pinned: form.pinned,
    starts_at: secondsFromMilliseconds(form.starts_at_ms),
    ends_at: secondsFromMilliseconds(form.ends_at_ms),
  }
  try {
    if (editing.value) {
      await announcementApi.update(editing.value.announcement_id, body)
      ElMessage.success('公告已更新')
    } else {
      await announcementApi.create(body)
      ElMessage.success('公告已创建')
    }
    drawerVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error(error instanceof ApiException ? error.message : '保存公告失败')
  } finally {
    saving.value = false
  }
}

async function archive(row: Announcement) {
  try {
    await ElMessageBox.confirm(
      `确认归档公告「${row.title}」？归档后不会再展示给用户。`,
      '归档公告',
      { type: 'warning', confirmButtonText: '归档', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    await announcementApi.archive(row.announcement_id)
    ElMessage.success('公告已归档')
    if (announcements.value.length === 1 && page.value > 1) page.value -= 1
    await load()
  } catch (error) {
    ElMessage.error(error instanceof ApiException ? error.message : '归档公告失败')
  }
}

onMounted(load)
</script>

<template>
  <div>
    <PageHeader title="公告管理" description="发布系统公告，控制展示时间和可见范围。">
      <template #actions>
        <el-button type="primary" @click="openCreate">
          <el-icon><Plus /></el-icon>
          新增公告
        </el-button>
      </template>
    </PageHeader>

    <section class="app-card mb-4">
      <div class="grid gap-3 lg:grid-cols-[1fr_150px_150px_170px_auto]">
        <el-input
          v-model="filters.keyword"
          clearable
          placeholder="搜索公告标题或内容"
          @keyup.enter="search"
        >
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <el-select v-model="filters.status" clearable placeholder="全部状态">
          <el-option v-for="item in statusOptions" :key="item.value" :label="item.label" :value="item.value" />
        </el-select>
        <el-select v-model="filters.level" clearable placeholder="全部等级">
          <el-option v-for="item in levelOptions" :key="item.value" :label="item.label" :value="item.value" />
        </el-select>
        <el-select v-model="filters.audience" clearable placeholder="全部范围">
          <el-option v-for="item in audienceOptions" :key="item.value" :label="item.label" :value="item.value" />
        </el-select>
        <div class="flex gap-2">
          <el-button type="primary" @click="search">搜索</el-button>
          <el-button @click="resetFilters">重置</el-button>
        </div>
      </div>
    </section>

    <section class="app-card overflow-hidden !p-0">
      <el-table v-loading="loading" :data="announcements" class="w-full">
        <el-table-column label="标题" min-width="280">
          <template #default="{ row }">
            <div class="min-w-0">
              <div class="flex items-center gap-2">
                <span class="truncate font-medium text-ink">{{ row.title }}</span>
                <el-tag v-if="row.pinned" size="small" type="warning" effect="plain">置顶</el-tag>
              </div>
              <p class="mt-1 line-clamp-1 text-xs text-ink-muted">{{ row.content }}</p>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="等级" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="levelMeta(row.level).type">{{ levelMeta(row.level).label }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="投放范围" width="120" align="center">
          <template #default="{ row }">{{ audienceLabel(row.audience) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="statusMeta(row.status).type" effect="plain">{{ statusMeta(row.status).label }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="展示时间" min-width="230" align="center">
          <template #default="{ row }">{{ timeRange(row) }}</template>
        </el-table-column>
        <el-table-column label="更新时间" width="150" align="center">
          <template #default="{ row }">{{ formatDateTime(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" fixed="right" width="150" align="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button
              link
              type="danger"
              :disabled="row.status === 'archived'"
              @click="archive(row)"
            >
              归档
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="flex items-center justify-between border-t border-line px-4 py-3">
        <span class="text-sm text-ink-muted">共 {{ total }} 条</span>
        <el-pagination
          v-model:current-page="page"
          :page-size="filters.limit"
          layout="prev, pager, next"
          :total="total"
          @current-change="load"
        />
      </div>
    </section>

    <el-drawer v-model="drawerVisible" :title="drawerTitle" size="640px" class="app-drawer">
      <div class="space-y-5">
        <section class="rounded-2xl border border-line bg-muted/40 p-4">
          <div class="mb-2 flex items-center gap-2">
            <el-tag :type="levelMeta(preview.level).type">{{ levelMeta(preview.level).label }}</el-tag>
            <el-tag v-if="preview.pinned" type="warning" effect="plain">置顶</el-tag>
            <el-tag effect="plain">{{ audienceLabel(preview.audience) }}</el-tag>
          </div>
          <h3 class="text-base font-semibold text-ink">{{ preview.title }}</h3>
          <p class="mt-2 whitespace-pre-line text-sm leading-6 text-ink-soft">{{ preview.content }}</p>
          <p class="mt-3 text-xs text-ink-muted">{{ timeRange(preview) }}</p>
        </section>

        <el-form label-position="top">
          <el-form-item label="公告标题" required>
            <el-input v-model="form.title" maxlength="120" show-word-limit placeholder="请输入公告标题" />
          </el-form-item>
          <el-form-item label="公告内容" required>
            <el-input
              v-model="form.content"
              type="textarea"
              :rows="7"
              maxlength="3000"
              show-word-limit
              placeholder="请输入公告内容"
            />
          </el-form-item>
          <div class="grid gap-3 sm:grid-cols-2">
            <el-form-item label="公告等级">
              <el-select v-model="form.level" class="w-full">
                <el-option v-for="item in levelOptions" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
            </el-form-item>
            <el-form-item label="投放范围">
              <el-select v-model="form.audience" class="w-full">
                <el-option v-for="item in audienceOptions" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
            </el-form-item>
          </div>
          <div class="grid gap-3 sm:grid-cols-2">
            <el-form-item label="状态">
              <el-select v-model="form.status" class="w-full">
                <el-option v-for="item in statusOptions" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
            </el-form-item>
            <el-form-item label="置顶展示">
              <el-switch v-model="form.pinned" />
            </el-form-item>
          </div>
          <div class="grid gap-3 sm:grid-cols-2">
            <el-form-item label="开始时间">
              <el-date-picker
                v-model="form.starts_at_ms"
                class="!w-full"
                type="datetime"
                value-format="x"
                clearable
                placeholder="不限制"
              />
            </el-form-item>
            <el-form-item label="结束时间">
              <el-date-picker
                v-model="form.ends_at_ms"
                class="!w-full"
                type="datetime"
                value-format="x"
                clearable
                placeholder="长期有效"
              />
            </el-form-item>
          </div>
        </el-form>
      </div>
      <template #footer>
        <div class="flex justify-end gap-2">
          <el-button @click="drawerVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="submit">保存</el-button>
        </div>
      </template>
    </el-drawer>
  </div>
</template>
