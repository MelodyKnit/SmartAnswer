<script setup lang="ts">
/** 反馈提交对话框：反馈中心和使用记录入口共用此组件。 */
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { ApiException } from '@/api/http'
import { feedbackApi } from '@/api/endpoints'
import type {
  FeedbackAnswerRecord,
  FeedbackAnswerRecordGroup,
  UsageLog,
} from '@/api/types'
import { FEEDBACK_CATEGORIES, formatDateTime } from '@/utils/format'

const props = withDefaults(
  defineProps<{
    modelValue: boolean
    initialRecord?: UsageLog | null
  }>(),
  { initialRecord: null },
)

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  submitted: []
}>()

const form = reactive({
  category: 'wrong_answer',
  title: '',
  content: '',
  imageUrlsText: '',
})
const submitting = ref(false)
const records = ref<FeedbackAnswerRecord[]>([])
const groups = ref<FeedbackAnswerRecordGroup[]>([])
const expandedRecords = ref<Record<string, FeedbackAnswerRecord[]>>({})
const selectedRecords = ref<Record<string, FeedbackAnswerRecord>>({})
const selectedIds = ref<string[]>([])
const keyword = ref('')
const days = ref(1)
const deduplicate = ref(false)
const loadingRecords = ref(false)
const recordsPage = ref(1)
const recordsTotal = ref(0)
const recordsLimit = 20

const isAnswerFeedback = computed(() => form.category === 'wrong_answer')
const selectedCount = computed(() => selectedIds.value.length)
const activeGroupKeys = ref<string[]>([])

const optionRecords = computed(() => {
  const source = deduplicate.value ? groups.value.map((item) => item.latest) : records.value
  const byId = new Map(source.map((item) => [item.log_id, item]))
  Object.values(selectedRecords.value).forEach((item) => byId.set(item.log_id, item))
  return [...byId.values()]
})

const groupedLatestIds = computed(
  () => new Set(groups.value.map((group) => group.latest.log_id)),
)

const selectedOnlyRecords = computed(() =>
  optionRecords.value.filter(
    (record) => deduplicate.value && !groupedLatestIds.value.has(record.log_id),
  ),
)

function recordLabel(record: FeedbackAnswerRecord): string {
  const title = record.title.trim() || '未保存题干'
  return `${title} · ${formatDateTime(record.created_at)} · ${record.answer || '无答案'}`
}

function resetForm() {
  form.category = 'wrong_answer'
  form.title = props.initialRecord ? '题目反馈' : ''
  form.content = ''
  form.imageUrlsText = ''
  keyword.value = ''
  days.value = 1
  deduplicate.value = false
  records.value = []
  groups.value = []
  expandedRecords.value = {}
  activeGroupKeys.value = []
  selectedRecords.value = {}
  selectedIds.value = []
  if (props.initialRecord) {
    selectedIds.value = [props.initialRecord.log_id]
    selectedRecords.value[props.initialRecord.log_id] = fromUsageLog(props.initialRecord)
  }
}

function fromUsageLog(record: UsageLog): FeedbackAnswerRecord {
  return {
    log_id: record.log_id,
    question_id: record.question_id,
    title: record.title,
    question_type: record.question_type,
    answer: record.answer,
    resolution_mode: record.resolution_mode,
    confidence: record.confidence,
    created_at: record.created_at,
    points_cost: record.points_cost,
    provider: record.provider,
    source_name: record.source_name || '',
  }
}

async function loadRecords() {
  if (!isAnswerFeedback.value) return
  loadingRecords.value = true
  try {
    const response = await feedbackApi.answerRecords({
      keyword: keyword.value.trim(),
      days: days.value,
      deduplicate: deduplicate.value,
      page: recordsPage.value,
      limit: recordsLimit,
    })
    records.value = response.records
    groups.value = response.groups
    recordsTotal.value = response.total
    response.records.forEach((item) => {
      selectedRecords.value[item.log_id] = item
    })
    response.groups.forEach((item) => {
      selectedRecords.value[item.latest.log_id] = item.latest
    })
  } catch (error) {
    ElMessage.error(error instanceof ApiException ? error.message : '加载答题记录失败')
  } finally {
    loadingRecords.value = false
  }
}

function remoteSearch(value: string) {
  keyword.value = value
  recordsPage.value = 1
  void loadRecords()
}

function refreshRecords() {
  recordsPage.value = 1
  expandedRecords.value = {}
  activeGroupKeys.value = []
  void loadRecords()
}

function onRecordsPageChange(page: number) {
  recordsPage.value = page
  void loadRecords()
}

async function loadGroupRecords(group: FeedbackAnswerRecordGroup) {
  if (!group.question_id || expandedRecords.value[group.group_key]) return
  try {
    const response = await feedbackApi.answerRecords({
      question_id: group.question_id,
      days: days.value,
      keyword: keyword.value.trim(),
      page: 1,
      limit: 100,
    })
    expandedRecords.value = { ...expandedRecords.value, [group.group_key]: response.records }
    response.records.forEach((item) => {
      selectedRecords.value[item.log_id] = item
    })
  } catch (error) {
    ElMessage.error(error instanceof ApiException ? error.message : '加载同题记录失败')
  }
}

function onGroupChange(value: string | string[]) {
  const keys = Array.isArray(value) ? value : [value]
  activeGroupKeys.value = keys
  groups.value
    .filter((group) => keys.includes(group.group_key))
    .forEach((group) => void loadGroupRecords(group))
}

function onCategoryChange() {
  if (!isAnswerFeedback.value) {
    selectedIds.value = []
  } else if (!records.value.length && !groups.value.length) {
    void loadRecords()
  }
}

function onSelectionChange(ids: string[]) {
  selectedIds.value = ids
}

function close() {
  if (!submitting.value) emit('update:modelValue', false)
}

function resetVisibleForm() {
  resetForm()
  if (props.modelValue) void loadRecords()
}

async function submit() {
  if (!form.title.trim() || !form.content.trim()) {
    ElMessage.warning('请填写反馈标题与内容')
    return
  }
  if (isAnswerFeedback.value && selectedIds.value.length === 0) {
    ElMessage.warning('答题问题至少选择一条答题记录')
    return
  }
  submitting.value = true
  try {
    await feedbackApi.create({
      category: form.category,
      title: form.title.trim(),
      content: form.content.trim(),
      image_urls: form.imageUrlsText
        .split(/\r?\n/)
        .map((item) => item.trim())
        .filter(Boolean),
      usage_log_ids: isAnswerFeedback.value ? selectedIds.value : [],
    })
    ElMessage.success('反馈已提交')
    emit('submitted')
    close()
  } catch (error) {
    ElMessage.error(error instanceof ApiException ? error.message : '提交反馈失败')
  } finally {
    submitting.value = false
  }
}

watch(
  () => props.modelValue,
  (visible) => {
    if (visible) {
      resetForm()
      void loadRecords()
    }
  },
)

watch(
  () => props.initialRecord,
  (record) => {
    if (!props.modelValue || !record) return
    selectedIds.value = Array.from(new Set([...selectedIds.value, record.log_id]))
    selectedRecords.value[record.log_id] = fromUsageLog(record)
  },
)
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="提交反馈"
    width="620px"
    :close-on-click-modal="false"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <el-form label-position="top">
      <div class="grid grid-cols-1 gap-x-5 md:grid-cols-2">
        <el-form-item label="反馈类型">
          <el-select v-model="form.category" class="w-full" @change="onCategoryChange">
            <el-option
              v-for="item in FEEDBACK_CATEGORIES"
              :key="item.value"
              :value="item.value"
              :label="item.label"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="反馈标题">
          <el-input v-model="form.title" maxlength="60" placeholder="例如：答案错误或页面显示异常" />
        </el-form-item>
      </div>

      <el-form-item v-if="isAnswerFeedback" label="问题答题记录">
        <div class="w-full space-y-2">
          <div class="flex flex-wrap gap-2">
            <el-select
              v-model="selectedIds"
              class="min-w-0 flex-1"
              multiple
              filterable
              remote
              reserve-keyword
              :remote-method="remoteSearch"
              :loading="loadingRecords"
              collapse-tags
              collapse-tags-tooltip
              placeholder="搜索并选择自己的答题记录"
              @change="onSelectionChange"
            >
              <template v-if="deduplicate">
                <el-option
                  v-for="group in groups"
                  :key="group.latest.log_id"
                  :value="group.latest.log_id"
                  :label="`${group.title || '未保存题干'} · 共${group.attempt_count}次`"
                />
                <el-option
                  v-for="record in selectedOnlyRecords"
                  :key="`selected-${record.log_id}`"
                  :value="record.log_id"
                  :label="recordLabel(record)"
                />
              </template>
              <template v-else>
                <el-option
                  v-for="record in optionRecords"
                  :key="record.log_id"
                  :value="record.log_id"
                  :label="recordLabel(record)"
                />
              </template>
            </el-select>
            <el-button :loading="loadingRecords" @click="refreshRecords">刷新</el-button>
          </div>
          <div class="flex flex-wrap items-center gap-2 text-xs text-ink-muted">
            <el-select v-model="days" size="small" class="!w-32" @change="refreshRecords">
              <el-option :value="1" label="当天" />
              <el-option :value="7" label="最近 7 天" />
              <el-option :value="30" label="最近 30 天" />
              <el-option :value="90" label="最近 90 天" />
              <el-option :value="0" label="全部历史" />
            </el-select>
            <el-button size="small" :type="deduplicate ? 'primary' : 'default'" @click="deduplicate = !deduplicate; refreshRecords()">
              {{ deduplicate ? '已去重' : '去重' }}
            </el-button>
            <span>已选 {{ selectedCount }} 条，共 {{ recordsTotal }} 组记录</span>
          </div>

          <el-collapse
            v-if="deduplicate && groups.some((item) => item.question_id)"
            v-model="activeGroupKeys"
            class="rounded border border-line px-2"
            @change="onGroupChange"
          >
            <el-collapse-item
              v-for="group in groups.filter((item) => item.question_id)"
              :key="group.group_key"
              :name="group.group_key"
            >
              <template #title>
                <span class="truncate pr-2 text-sm">{{ group.title }}</span>
                <el-tag size="small" effect="plain">{{ group.attempt_count }} 次</el-tag>
              </template>
              <el-checkbox-group v-if="expandedRecords[group.group_key]" v-model="selectedIds" class="space-y-2">
                <el-checkbox
                  v-for="record in expandedRecords[group.group_key]"
                  :key="record.log_id"
                  :label="record.log_id"
                  class="!mr-0 block"
                >
                  <span class="text-xs">{{ recordLabel(record) }}</span>
                </el-checkbox>
              </el-checkbox-group>
              <span v-else class="text-xs text-ink-muted">展开后加载该题的具体答题记录</span>
            </el-collapse-item>
          </el-collapse>

          <el-pagination
            v-if="recordsTotal > recordsLimit"
            small
            layout="prev, pager, next"
            :total="recordsTotal"
            :page-size="recordsLimit"
            :current-page="recordsPage"
            @current-change="onRecordsPageChange"
          />
        </div>
      </el-form-item>

      <el-form-item label="反馈内容">
        <el-input
          v-model="form.content"
          type="textarea"
          :rows="5"
          placeholder="请尽量描述清楚问题现象、题目内容或期望结果。"
        />
      </el-form-item>
      <el-form-item label="图片链接（可选，每行一条）">
        <el-input
          v-model="form.imageUrlsText"
          type="textarea"
          :rows="2"
          placeholder="https://example.com/screenshot-1.png"
        />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="close">取消</el-button>
      <el-button @click="resetVisibleForm">重置</el-button>
      <el-button type="primary" :loading="submitting" @click="submit">提交</el-button>
    </template>
  </el-dialog>
</template>
