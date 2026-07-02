<script setup lang="ts">
/** 题库检索：允许输入题目片段查询题库，展示结果。管理员有编辑/操作题目的权限。 */
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ApiException } from '@/api/http'
import { questionApi } from '@/api/endpoints'
import type { QuestionRecord } from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import { formatDateTime } from '@/utils/format'
import PageHeader from '@/components/PageHeader.vue'
import { DEFAULT_PAGE_SIZE } from '@/config/constants'

const route = useRoute()

// 数据状态
const loading = ref(false)
const saving = ref(false)
const deleting = ref(false)
const questions = ref<QuestionRecord[]>([])
const total = ref(0)
const allTypes = ref<string[]>([])
const allSources = ref<string[]>([])

// 搜索过滤表单
const filter = reactive({
  page: 1,
  question_id: '',
  keyword: '',
  source: '',
  subject: '',
  topic: '',
  type: '',
  status: '',
  question_type: '',
  updatedDateRange: [] as string[],
  limit: DEFAULT_PAGE_SIZE.QUESTIONS,
})

// 编辑弹窗状态
const editDialogVisible = ref(false)
const editForm = reactive({
  question_id: '',
  title_raw: '',
  question_type: 'single',
  options_raw: [] as string[],
  answer_raw: '',
  explanation: '',
  subject: '',
  tags: [] as string[],
  source_name: '',
})

// 标签输入辅助
const newTag = ref('')
const pendingAutoOpenQuestionId = ref('')

// 题目类型中文映射
const typeMap: Record<string, { label: string; type: string }> = {
  single: { label: '单选题', type: 'success' },
  multiple: { label: '多选题', type: 'warning' },
  completion: { label: '填空题', type: 'primary' },
  judgement: { label: '判断题', type: 'info' },
  unknown: { label: '其它题型', type: '' },
}

const statusMap: Record<string, { label: string; type: string }> = {
  active: { label: '基础题库', type: 'info' },
  trusted: { label: '可信 AI', type: 'success' },
  low_confidence: { label: '低信任度', type: 'warning' },
  pending: { label: '待确认', type: 'info' },
  conflict: { label: '冲突', type: 'danger' },
  non_reusable: { label: '开放题留痕', type: 'info' },
}

function getQuestionTypeTag(type: string) {
  return typeMap[type] || { label: type || '其它', type: '' }
}

function getQuestionStatusTag(status?: string) {
  return statusMap[status || 'active'] || { label: status || 'active', type: 'info' }
}

// 获取选项的字母标签 A, B, C, D...
function getOptionLabel(index: number): string {
  return String.fromCharCode(65 + index) // 65 is 'A'
}

// 选项字母到索引的转换（用于单选/多选值绑定）
const optionLabels = computed(() => {
  return editForm.options_raw.map((_, i) => getOptionLabel(i))
})

// 多选题的答案数组双向绑定
const multipleAnswers = computed({
  get: () => {
    if (!editForm.answer_raw) return []
    return editForm.answer_raw.split('#')
  },
  set: (val: string[]) => {
    // 保持字母顺序排序，例如 A#B 而不是 B#A
    const sorted = [...val].sort()
    editForm.answer_raw = sorted.join('#')
  }
})

// 监听题目类型变化，重置或调整答案格式
watch(() => editForm.question_type, (newType) => {
  if (newType === 'judgement') {
    // 判断题的选项通常是“对”和“错”
    if (editForm.options_raw.length !== 2) {
      editForm.options_raw = ['对', '错']
    }
  }
})

// 添加新选项
function addOption() {
  editForm.options_raw.push('')
}

// 删除指定选项
function removeOption(index: number) {
  editForm.options_raw.splice(index, 1)
  // 校验答案是否还合法，如果不合法则清除
  const label = getOptionLabel(index)
  if (editForm.question_type === 'multiple') {
    multipleAnswers.value = multipleAnswers.value.filter(a => a !== label)
  } else if (editForm.answer_raw === label) {
    editForm.answer_raw = ''
  }
}

// 添加新标签
function addTag() {
  const tag = newTag.value.trim()
  if (tag && !editForm.tags.includes(tag)) {
    editForm.tags.push(tag)
  }
  newTag.value = ''
}

// 删除标签
function removeTag(tag: string) {
  editForm.tags = editForm.tags.filter(t => t !== tag)
}

// 加载题目列表
async function loadList() {
  loading.value = true
  try {
    const res = await questionApi.list({
      page: filter.page,
      limit: filter.limit,
      question_id: filter.question_id.trim() || undefined,
      keyword: filter.keyword.trim() || undefined,
      type: filter.type || undefined,
      source: filter.source || undefined,
      status: filter.status || undefined,
      updated_start_date: filter.updatedDateRange[0] || undefined,
      updated_end_date: filter.updatedDateRange[1] || undefined,
    })
    questions.value = res.questions
    total.value = res.total
    allTypes.value = res.all_types
    allSources.value = res.all_sources
    openRouteTargetIfNeeded()
  } catch (err) {
    ElMessage.error(err instanceof ApiException ? err.message : '获取题目列表失败')
  } finally {
    loading.value = false
  }
}

// 重置过滤条件
function resetFilter() {
  filter.question_id = ''
  filter.keyword = ''
  filter.type = ''
  filter.source = ''
  filter.status = ''
  filter.updatedDateRange = []
  filter.page = 1
  loadList()
}

// 搜索
function handleSearch() {
  filter.question_id = ''
  filter.page = 1
  loadList()
}

// 分页变化
function handlePageChange(page: number) {
  filter.page = page
  loadList()
}

function handleLimitChange(limit: number) {
  filter.limit = limit
  filter.page = 1
  loadList()
}

// 打开编辑窗口
function openEdit(question: QuestionRecord) {
  editForm.question_id = question.question_id
  editForm.title_raw = question.title_raw || ''
  editForm.question_type = question.question_type || 'single'
  editForm.options_raw = [...(question.options_raw || [])]
  editForm.answer_raw = question.answer_raw || ''
  editForm.explanation = question.explanation || ''
  editForm.subject = question.subject || ''
  editForm.tags = [...(question.tags || [])]
  editForm.source_name = question.source_name || ''
  
  editDialogVisible.value = true
}

// 保存题目修改
async function saveQuestion() {
  if (!editForm.title_raw.trim()) {
    ElMessage.warning('题干内容不能为空')
    return
  }
  
  saving.value = true
  try {
    await questionApi.update(editForm.question_id, {
      title_raw: editForm.title_raw.trim(),
      question_type: editForm.question_type,
      options_raw: editForm.options_raw.map(o => o.trim()),
      answer_raw: editForm.answer_raw.trim() || undefined,
      explanation: editForm.explanation.trim() || '',
      subject: editForm.subject.trim() || 'default',
      tags: editForm.tags,
    })
    ElMessage.success('题目修改成功')
    editDialogVisible.value = false
    loadList()
  } catch (err) {
    ElMessage.error(err instanceof ApiException ? err.message : '修改题目失败')
  } finally {
    saving.value = false
  }
}

async function deleteQuestion(question: QuestionRecord) {
  const title = question.title_raw || question.question_id
  try {
    await ElMessageBox.confirm(
      `确认删除“${title.slice(0, 40)}”吗？删除后题目将不再参与自动命中，历史使用记录不受影响。`,
      '删除题目',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning',
        confirmButtonClass: 'el-button--danger',
      },
    )
  } catch (err) {
    if (err === 'cancel' || err === 'close') return
    throw err
  }

  deleting.value = true
  try {
    await questionApi.remove(question.question_id)
    ElMessage.success('题目已删除')
    if (questions.value.length <= 1 && filter.page > 1) {
      filter.page -= 1
    }
    await loadList()
  } catch (err) {
    ElMessage.error(err instanceof ApiException ? err.message : '删除题目失败')
  } finally {
    deleting.value = false
  }
}

function reset() {
  filter.question_id = ''
  filter.keyword = ''
  filter.source = ''
  filter.subject = ''
  filter.topic = ''
  filter.question_type = ''
  filter.type = ''
  filter.status = ''
  filter.updatedDateRange = []
  filter.limit = DEFAULT_PAGE_SIZE.QUESTIONS
  filter.page = 1
  loadList()
}

function syncRouteQuery() {
  const routeQuestionId = String(route.query.question_id || '').trim()
  const routeKeyword = String(route.query.keyword || '').trim()
  filter.question_id = routeQuestionId
  filter.keyword = routeQuestionId ? '' : routeKeyword
  pendingAutoOpenQuestionId.value =
    route.query.open === 'edit' && routeQuestionId ? routeQuestionId : ''
}

function openRouteTargetIfNeeded() {
  if (!pendingAutoOpenQuestionId.value) return
  const target = questions.value.find(
    (question) => question.question_id === pendingAutoOpenQuestionId.value,
  )
  if (target) {
    pendingAutoOpenQuestionId.value = ''
    openEdit(target)
    return
  }
  const fallbackKeyword = String(route.query.keyword || '').trim()
  if (fallbackKeyword && filter.question_id) {
    ElMessage.warning('未找到关联题库记录，已按题干关键字检索')
    pendingAutoOpenQuestionId.value = ''
    filter.question_id = ''
    filter.keyword = fallbackKeyword
    filter.page = 1
    loadList()
    return
  }
  ElMessage.warning('未找到关联题库记录，可尝试按题干关键字搜索')
  pendingAutoOpenQuestionId.value = ''
}

watch(
  () => route.query,
  () => {
    syncRouteQuery()
    filter.page = 1
    loadList()
  },
)

onMounted(() => {
  syncRouteQuery()
  loadList()
})
</script>

<template>
  <div>
    <PageHeader title="题库管理" description="查看系统中所有题库的详细题目内容、选项与答案，并支持实时编辑修改。">
      <template #actions>
        <el-button type="primary" :loading="loading" @click="loadList">
          <el-icon class="mr-1"><Refresh /></el-icon>
          刷新题库
        </el-button>
      </template>
    </PageHeader>

    <div class="space-y-4">
      <!-- 搜索过滤条 -->
      <div class="question-filter-card app-card p-4">
        <el-form
          :model="filter"
          class="question-filter-form grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-[minmax(260px,1fr)_150px_190px_160px_300px_auto] xl:items-end"
        >
          <el-form-item label="关键字" class="mb-0">
            <el-input
              v-model="filter.keyword"
              placeholder="搜索题干/选项/解析..."
              clearable
              class="w-full"
              @keyup.enter="handleSearch"
            />
          </el-form-item>
          <el-form-item label="题型" class="mb-0">
            <el-select v-model="filter.type" placeholder="全部题型" clearable class="w-full">
              <el-option value="single" label="单选题" />
              <el-option value="multiple" label="多选题" />
              <el-option value="completion" label="填空题" />
              <el-option value="judgement" label="判断题" />
              <el-option value="unknown" label="其它题型" />
            </el-select>
          </el-form-item>
          <el-form-item label="数据源" class="mb-0">
            <el-select v-model="filter.source" placeholder="全部来源" clearable class="w-full">
              <el-option v-for="src in allSources" :key="src" :value="src" :label="src" />
            </el-select>
          </el-form-item>
          <el-form-item label="状态" class="mb-0">
            <el-select v-model="filter.status" placeholder="全部状态" clearable class="w-full">
              <el-option value="active" label="基础题库" />
              <el-option value="trusted" label="可信 AI" />
              <el-option value="low_confidence" label="低信任度" />
              <el-option value="pending" label="待确认" />
              <el-option value="conflict" label="冲突" />
              <el-option value="non_reusable" label="开放题留痕" />
            </el-select>
          </el-form-item>
          <el-form-item label="修改时间" class="mb-0">
            <el-date-picker
              v-model="filter.updatedDateRange"
              type="daterange"
              range-separator="至"
              start-placeholder="开始日期"
              end-placeholder="结束日期"
              value-format="YYYY-MM-DD"
              clearable
              class="question-updated-range"
              @change="handleSearch"
            />
          </el-form-item>
          <el-form-item class="mb-0">
            <div class="flex w-full gap-2 xl:justify-end">
              <el-button type="primary" class="flex-1 xl:flex-none" @click="handleSearch">
                <el-icon class="mr-1"><Search /></el-icon>
                搜索
              </el-button>
              <el-button class="flex-1 xl:flex-none" @click="resetFilter">重置</el-button>
            </div>
          </el-form-item>
        </el-form>
      </div>

      <!-- 题目列表表格 -->
      <div class="app-card overflow-hidden" v-loading="loading">
        <el-table :data="questions" style="width: 100%" row-key="question_id" stripe>
          <!-- 题型 -->
          <el-table-column label="题型" width="100">
            <template #default="{ row }">
              <el-tag :type="getQuestionTypeTag(row.question_type).type" effect="light" size="small">
                {{ getQuestionTypeTag(row.question_type).label }}
              </el-tag>
            </template>
          </el-table-column>

          <!-- 题干与选项 -->
          <el-table-column label="题目内容">
            <template #default="{ row }">
              <div class="space-y-2">
                <!-- 题干 -->
                <div class="font-medium text-ink break-words text-sm">{{ row.title_raw }}</div>
                
                <!-- 选项列表 -->
                <div v-if="row.options_raw && row.options_raw.length > 0" class="grid grid-cols-1 md:grid-cols-2 gap-2 pl-4">
                  <div 
                    v-for="(option, index) in row.options_raw" 
                    :key="index"
                    class="text-xs text-ink-muted flex items-start gap-1"
                  >
                    <span class="font-semibold text-primary">{{ getOptionLabel(index) }}.</span>
                    <span class="break-words">{{ option }}</span>
                  </div>
                </div>
              </div>
            </template>
          </el-table-column>

          <!-- 答案 -->
          <el-table-column label="参考答案" width="120">
            <template #default="{ row }">
              <el-tag type="danger" effect="dark" size="small" class="font-bold">
                {{ row.answer_raw }}
              </el-tag>
            </template>
          </el-table-column>

          <el-table-column label="状态" width="120">
            <template #default="{ row }">
              <el-tag size="small" :type="getQuestionStatusTag(row.status).type">
                {{ getQuestionStatusTag(row.status).label }}
              </el-tag>
            </template>
          </el-table-column>

          <el-table-column label="修改时间" width="170">
            <template #default="{ row }">
              <span class="text-sm text-ink-soft">{{ formatDateTime(row.updated_at) }}</span>
            </template>
          </el-table-column>

          <!-- 科目/解析 -->
          <el-table-column label="科目 & 来源" width="180">
            <template #default="{ row }">
              <div class="text-xs space-y-1">
                <div><span class="text-ink-soft">科目:</span> <span class="text-ink font-medium">{{ row.subject || '未分类' }}</span></div>
                <div><span class="text-ink-soft">来源:</span> <el-tag size="small" type="info" class="scale-90 origin-left">{{ row.source_name }}</el-tag></div>
              </div>
            </template>
          </el-table-column>

          <!-- 操作 -->
          <el-table-column label="操作" width="140" align="center">
            <template #default="{ row }">
              <div class="flex justify-center gap-2">
                <el-button type="primary" size="small" circle @click="openEdit(row)">
                  <el-icon><Edit /></el-icon>
                </el-button>
                <el-button type="danger" size="small" circle :loading="deleting" @click="deleteQuestion(row)">
                  <el-icon><Delete /></el-icon>
                </el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>

        <!-- 分页 -->
        <div class="flex justify-end p-4 bg-surface-muted border-t border-layout">
          <el-pagination
            v-model:current-page="filter.page"
            v-model:page-size="filter.limit"
            :page-sizes="[10, 20, 50, 100]"
            layout="total, sizes, prev, pager, next, jumper"
            :total="total"
            @size-change="handleLimitChange"
            @current-change="handlePageChange"
          />
        </div>
      </div>
    </div>

    <!-- 编辑题目的对话框 -->
    <el-dialog
      v-model="editDialogVisible"
      title="修改题目与答案"
      width="60%"
      destroy-on-close
      class="custom-dialog"
    >
      <el-form label-position="top" :model="editForm" class="space-y-4">
        <!-- 题干 -->
        <el-form-item label="题干" required>
          <el-input
            v-model="editForm.title_raw"
            type="textarea"
            :rows="3"
            placeholder="请输入题干内容"
          />
        </el-form-item>

        <!-- 基础配置列 -->
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
          <el-form-item label="题型" required>
            <el-select v-model="editForm.question_type" class="w-full">
              <el-option value="single" label="单选题" />
              <el-option value="multiple" label="多选题" />
              <el-option value="completion" label="填空题" />
              <el-option value="judgement" label="判断题" />
              <el-option value="unknown" label="其它题型" />
            </el-select>
          </el-form-item>
          <el-form-item label="所属学科">
            <el-input v-model="editForm.subject" placeholder="例如：解剖学" />
          </el-form-item>
          <el-form-item label="数据源 (只读)">
            <el-input v-model="editForm.source_name" disabled />
          </el-form-item>
        </div>

        <!-- 选项配置 -->
        <div v-if="editForm.question_type !== 'completion'" class="app-card p-4 bg-surface-muted/50 border border-layout">
          <div class="flex justify-between items-center mb-3">
            <span class="text-sm font-semibold text-ink">选项列表</span>
            <el-button type="primary" size="small" @click="addOption" v-if="editForm.question_type !== 'judgement'">
              <el-icon class="mr-1"><Plus /></el-icon>
              添加选项
            </el-button>
          </div>
          <div class="space-y-3">
            <div 
              v-for="(_, index) in editForm.options_raw" 
              :key="index"
              class="flex items-center gap-2"
            >
              <el-tag type="primary" class="font-bold flex-shrink-0 w-8 text-center">{{ getOptionLabel(index) }}</el-tag>
              <el-input v-model="editForm.options_raw[index]" placeholder="请输入选项内容" />
              <el-button 
                type="danger" 
                size="small" 
                circle 
                v-if="editForm.question_type !== 'judgement' && editForm.options_raw.length > 2"
                @click="removeOption(index)"
              >
                <el-icon><Delete /></el-icon>
              </el-button>
            </div>
          </div>
        </div>

        <!-- 答案配置 -->
        <el-form-item label="设置正确答案" required>
          <!-- 1. 单选题 / 判断题 答案配置 (Radio 列表) -->
          <div v-if="editForm.question_type === 'single' || editForm.question_type === 'judgement'" class="w-full">
            <el-radio-group v-model="editForm.answer_raw" class="flex flex-wrap gap-4">
              <el-radio 
                v-for="label in optionLabels" 
                :key="label" 
                :label="label"
                class="custom-radio-answer"
              >
                选项 {{ label }}
              </el-radio>
            </el-radio-group>
          </div>

          <!-- 2. 多选题 答案配置 (Checkbox 列表) -->
          <div v-else-if="editForm.question_type === 'multiple'" class="w-full">
            <el-checkbox-group v-model="multipleAnswers" class="flex flex-wrap gap-4">
              <el-checkbox 
                v-for="label in optionLabels" 
                :key="label" 
                :label="label"
              >
                选项 {{ label }}
              </el-checkbox>
            </el-checkbox-group>
          </div>

          <!-- 3. 其它题型/填空题 答案配置 (直接输入框) -->
          <div v-else class="w-full">
            <el-input 
              v-model="editForm.answer_raw" 
              placeholder="请输入正确答案（填空题可用逗号或井号分隔多个填空）"
            />
          </div>
        </el-form-item>

        <!-- 答案解析 -->
        <el-form-item label="答案解析">
          <el-input
            v-model="editForm.explanation"
            type="textarea"
            :rows="3"
            placeholder="请输入答案的解析说明"
          />
        </el-form-item>

        <!-- 标签管理 -->
        <el-form-item label="分类标签">
          <div class="flex flex-wrap gap-2 mb-2 items-center">
            <el-tag
              v-for="tag in editForm.tags"
              :key="tag"
              closable
              type="info"
              @close="removeTag(tag)"
            >
              {{ tag }}
            </el-tag>
            <el-input
              v-model="newTag"
              placeholder="添加标签"
              size="small"
              class="w-24"
              @keyup.enter="addTag"
              @blur="addTag"
            />
          </div>
        </el-form-item>
      </el-form>

      <template #footer>
        <div class="flex justify-end gap-2">
          <el-button @click="editDialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="saveQuestion">
            保存修改
          </el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.custom-radio-answer {
  margin-right: 0 !important;
}

.question-filter-card {
  display: flex;
  min-height: 96px;
  align-items: center;
}

.question-filter-form {
  width: 100%;
}

.question-filter-form :deep(.el-form-item) {
  margin-bottom: 0;
  align-items: center;
}

.question-filter-form :deep(.el-form-item__label) {
  height: 38px;
  margin-bottom: 0;
  line-height: 38px;
}

.question-filter-form :deep(.el-form-item__content) {
  width: 100%;
}

.question-updated-range {
  width: 100% !important;
}
</style>
