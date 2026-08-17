<script setup lang="ts">
/** AI 生图与修图页面：只提交私有资产引用，轮询受保护的个人任务结果。 */
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { MagicStick, Picture, QuestionFilled, Refresh } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import ImageInputWorkspace from '@/components/image-generation/ImageInputWorkspace.vue'
import ImagePreviewPanel from '@/components/image-generation/ImagePreviewPanel.vue'
import ImageHistoryPanel from '@/components/image-generation/ImageHistoryPanel.vue'
import PageHeader from '@/components/PageHeader.vue'
import { imageGenerationApi } from '@/api/endpoints'
import { ApiException } from '@/api/http'
import type {
  ImageGenerationCapabilities,
  ImageGenerationInputReference,
  ImageGenerationJob,
  ImageGenerationJobStatus,
  ImageGenerationMode,
  ImageGenerationOutputOptions,
} from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import { formatDateTime } from '@/utils/format'

const auth = useAuthStore()
const loading = ref(false)
const submitting = ref(false)
const capabilities = ref<ImageGenerationCapabilities | null>(null)
const jobs = ref<ImageGenerationJob[]>([])
const activeJobId = ref('')
const inputReferences = ref<ImageGenerationInputReference[]>([])
const previewUrls = ref<Record<string, string>>({})
let jobPollTimer: number | undefined
let sizeInferenceTimer: number | undefined
let sizeInferenceRequestId = 0

const form = reactive<{
  mode: ImageGenerationMode
  prompt: string
  size: string
  aspectRatio: string
  imageSize: string
  useCustomSize: boolean
  customWidth: number
  customHeight: number
  autoMode: boolean
  inferredExplanation: string
}>({
  mode: 'text_to_image',
  prompt: '',
  size: '',
  aspectRatio: '',
  imageSize: '',
  useCustomSize: false,
  customWidth: 1024,
  customHeight: 1024,
  autoMode: true,
  inferredExplanation: '',
})

const modeLabels: Record<ImageGenerationMode, string> = {
  text_to_image: '文生图',
  image_edit: '整图编辑',
  masked_edit: '局部编辑',
  multi_reference: '多图参考',
}

const statusLabels: Record<ImageGenerationJobStatus, string> = {
  queued: '排队中',
  running: '生成中',
  succeeded: '已完成',
  failed: '生成失败',
  rejected: '内容被拒绝',
  cancelled: '已取消',
  deleted: '已删除',
}

const statusTypes: Record<ImageGenerationJobStatus, 'info' | 'warning' | 'success' | 'danger'> = {
  queued: 'info',
  running: 'warning',
  succeeded: 'success',
  failed: 'danger',
  rejected: 'danger',
  cancelled: 'info',
  deleted: 'info',
}

const isAvailable = computed(() => capabilities.value?.available === true)
const pointsPerImage = computed(() => capabilities.value?.points_per_image ?? 0)
const availableModes = computed<ImageGenerationMode[]>(
  () => capabilities.value?.input.available_modes ?? ['text_to_image'],
)
const modeAvailable = computed(() => availableModes.value.includes(form.mode))
const activeJob = computed(() => jobs.value.find((job) => job.job_id === activeJobId.value) || null)
const activeJobPreviewUrl = computed(() => {
  const job = activeJob.value
  if (!job || job.status !== 'succeeded' || !job.assets.length) return ''
  return previewUrls.value[job.assets[0].asset_id] || ''
})
const hasActiveJob = computed(() => jobs.value.some((job) => job.status === 'queued' || job.status === 'running'))
const generatedSources = computed(() =>
  jobs.value.flatMap((job) =>
    job.status === 'succeeded'
      ? job.assets.map((asset) => ({
          jobId: job.job_id,
          assetId: asset.asset_id,
          width: asset.width,
          height: asset.height,
          previewUrl: previewUrls.value[asset.asset_id] || '',
          label: `历史生成 · ${formatDateTime(job.created_at)}`,
        }))
      : [],
  ),
)

const hasRequiredInputs = computed(() => {
  if (form.mode === 'text_to_image') return inputReferences.value.length === 0
  const sourceCount = inputReferences.value.filter((item) => item.role === 'source').length
  const referenceCount = inputReferences.value.filter((item) => item.role === 'reference').length
  const maskCount = inputReferences.value.filter((item) => item.role === 'mask').length
  if (form.mode === 'image_edit') return sourceCount === 1 && referenceCount === 0 && maskCount === 0
  if (form.mode === 'masked_edit') return sourceCount === 1 && referenceCount === 0 && maskCount === 1
  return sourceCount === 1 && referenceCount >= 1 && maskCount === 0
})

const canSubmit = computed(
  () =>
    isAvailable.value &&
    modeAvailable.value &&
    !submitting.value &&
    !hasActiveJob.value &&
    form.prompt.trim().length > 0 &&
    hasRequiredInputs.value &&
    (capabilities.value?.balance ?? 0) >= pointsPerImage.value,
)

function createIdempotencyKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `image-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

function syncOutputDefaults(value: ImageGenerationCapabilities) {
  const output = value.output
  if (!value.input.available_modes.includes(form.mode)) {
    form.mode = 'text_to_image'
    inputReferences.value = []
  }
  if (output.kind === 'gemini') {
    if (!output.aspect_ratios.includes(form.aspectRatio)) form.aspectRatio = output.aspect_ratios[0] || ''
    if (!output.image_sizes.includes(form.imageSize)) form.imageSize = output.image_sizes[0] || ''
    return
  }
  if (output.kind === 'openai-images' || output.kind === 'compatible-images') {
    if (!output.preset_sizes.includes(form.size)) form.size = output.preset_sizes[0] || ''
    if (form.useCustomSize && !output.allow_custom_size) form.useCustomSize = false
    return
  }
  form.size = ''
  form.useCustomSize = false
}

function buildOutput(): ImageGenerationOutputOptions | undefined {
  const output = capabilities.value?.output
  if (!output || output.kind === 'unavailable' || output.kind === 'model-controlled') return undefined
  if (output.kind === 'gemini') {
    return {
      aspect_ratio: form.aspectRatio || output.aspect_ratios[0],
      image_size: form.imageSize || output.image_sizes[0],
    }
  }
  if (output.kind === 'openai-images' || output.kind === 'compatible-images') {
    if (output.kind === 'openai-images' && form.useCustomSize) {
      return { size: `${form.customWidth}x${form.customHeight}` }
    }
    return { size: form.size || output.preset_sizes[0] }
  }
  return undefined
}

async function inferSizeFromPrompt() {
  const prompt = form.prompt.trim()
  if (!prompt || !form.autoMode) return
  const requestId = ++sizeInferenceRequestId
  try {
    const result = await imageGenerationApi.inferSize(prompt)
    // 异步响应可能晚于用户的下一次输入，只接受当前提示词对应的推断结果。
    if (requestId !== sizeInferenceRequestId || prompt !== form.prompt.trim() || !form.autoMode) return
    const output = result.output
    form.inferredExplanation = result.explanation

    // 应用推断结果
    if (output.aspect_ratio && output.image_size) {
      form.aspectRatio = output.aspect_ratio
      form.imageSize = output.image_size
    } else if (output.size) {
      form.size = output.size
    }
  } catch (error) {
    // 推断失败不影响用户继续操作
    console.warn('尺寸推断失败:', error)
  }
}

function outputSelectionLabel(): string {
  const output = buildOutput()
  if (output?.aspect_ratio && output.image_size) return `${output.aspect_ratio} · ${output.image_size}`
  if (output?.size) return output.size
  return '由模型决定'
}

function jobOutputLabel(job: ImageGenerationJob): string {
  const requested = job.output.aspect_ratio && job.output.image_size
    ? `${job.output.aspect_ratio} · ${job.output.image_size}`
    : job.output.size || job.size || '由模型决定'
  const asset = job.assets[0]
  return asset?.width && asset?.height ? `${requested} · 实际 ${asset.width}x${asset.height}` : requested
}

function revokePreviewUrls() {
  Object.values(previewUrls.value).forEach((url) => URL.revokeObjectURL(url))
  previewUrls.value = {}
}

async function loadPreview(job: ImageGenerationJob) {
  for (const asset of job.assets || []) {
    if (previewUrls.value[asset.asset_id]) continue
    try {
      const blob = await imageGenerationApi.assetContent(job.job_id, asset.asset_id)
      previewUrls.value = {
        ...previewUrls.value,
        [asset.asset_id]: URL.createObjectURL(blob),
      }
    } catch (error) {
      if (error instanceof ApiException && error.code !== 'ASSET_NOT_FOUND') {
        ElMessage.warning('生成图片预览加载失败')
      }
    }
  }
}

async function refreshJobs() {
  const result = await imageGenerationApi.list({ limit: 24 })
  revokePreviewUrls()
  jobs.value = result.jobs
  await Promise.all(jobs.value.filter((job) => job.status === 'succeeded').map(loadPreview))
  const newestActive = jobs.value.find((job) => job.status === 'queued' || job.status === 'running')
  activeJobId.value = newestActive?.job_id || ''
}

async function refreshCapabilities() {
  const result = await imageGenerationApi.capabilities()
  capabilities.value = result.capabilities
  syncOutputDefaults(result.capabilities)
}

async function load() {
  loading.value = true
  try {
    await refreshCapabilities()
    await refreshJobs()
  } catch (error) {
    ElMessage.error(error instanceof ApiException ? error.message : '加载生图能力失败')
  } finally {
    loading.value = false
  }
}

async function refreshActiveJob() {
  if (!activeJobId.value) return
  try {
    const result = await imageGenerationApi.detail(activeJobId.value)
    const index = jobs.value.findIndex((item) => item.job_id === result.job.job_id)
    if (index >= 0) jobs.value.splice(index, 1, result.job)
    else jobs.value.unshift(result.job)
    if (result.job.status === 'succeeded') await loadPreview(result.job)
    if (!['queued', 'running'].includes(result.job.status)) {
      activeJobId.value = ''
      stopPolling()
      await Promise.all([auth.refreshProfile(), refreshCapabilities()])
    }
  } catch (error) {
    if (error instanceof ApiException && error.code !== 'JOB_NOT_FOUND') ElMessage.warning(error.message)
    activeJobId.value = ''
    stopPolling()
  }
}

function startPolling() {
  if (jobPollTimer !== undefined) return
  jobPollTimer = window.setInterval(() => void refreshActiveJob(), 1_200)
}

function stopPolling() {
  if (jobPollTimer === undefined) return
  window.clearInterval(jobPollTimer)
  jobPollTimer = undefined
}

function clearSizeInference() {
  sizeInferenceRequestId += 1
  if (sizeInferenceTimer !== undefined) {
    window.clearTimeout(sizeInferenceTimer)
    sizeInferenceTimer = undefined
  }
}

function scheduleSizeInference() {
  clearSizeInference()
  if (!form.autoMode || form.prompt.trim().length <= 10) return
  sizeInferenceTimer = window.setTimeout(() => {
    sizeInferenceTimer = undefined
    void inferSizeFromPrompt()
  }, 800)
}

function handleInputReferences(references: ImageGenerationInputReference[]) {
  inputReferences.value = references
}

async function submit() {
  if (!form.prompt.trim()) {
    ElMessage.warning('请输入图片描述或编辑指令')
    return
  }
  if (!modeAvailable.value) {
    ElMessage.warning('当前模型尚未通过此编辑能力测试')
    return
  }
  if (!hasRequiredInputs.value) {
    ElMessage.warning('请按当前模式补齐需要的主图、参考图或蒙版')
    return
  }
  if (!isAvailable.value || hasActiveJob.value) return
  submitting.value = true
  try {
    const output = buildOutput()
    const result = await imageGenerationApi.create({
      prompt: form.prompt.trim(),
      mode: form.mode,
      input_assets: inputReferences.value,
      ...(output ? { output } : {}),
      idempotency_key: createIdempotencyKey(),
    })
    const existingIndex = jobs.value.findIndex((item) => item.job_id === result.job.job_id)
    if (existingIndex >= 0) jobs.value.splice(existingIndex, 1, result.job)
    else jobs.value.unshift(result.job)
    activeJobId.value = result.job.job_id
    capabilities.value = capabilities.value
      ? { ...capabilities.value, balance: Math.max(0, capabilities.value.balance - result.job.points_cost) }
      : capabilities.value
    await auth.refreshProfile()
    startPolling()
    ElMessage.success(result.idempotent_replay ? '已恢复原生图任务' : '任务已提交')
  } catch (error) {
    ElMessage.error(error instanceof ApiException ? error.message : '创建生图任务失败')
  } finally {
    submitting.value = false
  }
}

async function removeJob(job: ImageGenerationJob) {
  const action = job.status === 'queued' ? '取消' : '删除'
  try {
    await ElMessageBox.confirm(
      job.status === 'queued'
        ? '取消尚未提交给供应商的任务会退还预扣积分。'
        : '删除后将立即撤销该图片的访问权限。',
      `${action}生图任务`,
      { type: 'warning', confirmButtonText: action, cancelButtonText: '返回' },
    )
  } catch {
    return
  }
  try {
    await imageGenerationApi.delete(job.job_id)
    if (activeJobId.value === job.job_id) activeJobId.value = ''
    await Promise.all([refreshJobs(), refreshCapabilities(), auth.refreshProfile()])
    if (!hasActiveJob.value) stopPolling()
    ElMessage.success(`${action}成功`)
  } catch (error) {
    ElMessage.error(error instanceof ApiException ? error.message : `${action}失败`)
  }
}

function handleSelectJob(job: ImageGenerationJob) {
  activeJobId.value = job.job_id
}

watch(
  () => form.mode,
  () => {
    inputReferences.value = []
  },
)

watch(
  () => form.prompt,
  () => {
    // 尺寸推断与任务轮询使用独立定时器，输入不应中断生成任务刷新。
    scheduleSizeInference()
  },
)

watch(
  () => form.autoMode,
  (enabled) => {
    clearSizeInference()
    if (enabled && form.prompt.trim()) {
      void inferSizeFromPrompt()
    } else {
      form.inferredExplanation = ''
    }
  },
)

onMounted(async () => {
  await load()
  if (hasActiveJob.value) startPolling()
})

onUnmounted(() => {
  stopPolling()
  clearSizeInference()
  revokePreviewUrls()
})
</script>

<template>
  <div v-loading="loading" class="space-y-4">
    <PageHeader title="AI 生图" description="使用私有模型创建图片，或基于私有图片进行编辑。">
      <template #actions>
        <el-button :icon="Refresh" @click="load">刷新</el-button>
      </template>
    </PageHeader>

    <div class="grid gap-4 xl:grid-cols-2">
      <!-- 左侧编辑面板 -->
      <section class="app-card overflow-hidden">
        <div class="border-b border-line bg-gradient-to-br from-brand-50/40 to-canvas/30 px-5 py-4">
          <div class="flex items-start justify-between gap-4">
            <div>
              <p class="text-xs font-semibold uppercase tracking-[0.18em] text-brand-600">Image Studio</p>
              <h3 class="mt-1 flex items-center gap-2 text-lg font-semibold text-ink">
                <el-icon class="text-brand-500"><Picture /></el-icon>
                <span>AI 生成与编辑</span>
                <el-tooltip
                  content="提交到供应商前的校验、读取失败会退还预扣积分；请求已发出后，即使上游超时或失败也不会自动重试或退款，避免重复产生供应商费用。"
                  placement="top"
                  :show-after="100"
                >
                  <el-icon class="cursor-help text-sm text-ink-muted/60 transition-colors hover:text-brand-500"><QuestionFilled /></el-icon>
                </el-tooltip>
              </h3>
            </div>
            <el-tag :type="isAvailable ? 'success' : 'info'" effect="plain">{{ isAvailable ? '模型可用' : '暂不可用' }}</el-tag>
          </div>
        </div>

        <div class="space-y-5 p-5">
          <div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div class="rounded-lg border border-line bg-card-soft px-3 py-3"><div class="text-xs text-ink-muted">可用余额</div><div class="mt-1 text-lg font-semibold text-ink">{{ capabilities?.balance ?? '—' }}</div></div>
            <div class="rounded-lg border border-line bg-card-soft px-3 py-3"><div class="text-xs text-ink-muted">单张扣费</div><div class="mt-1 text-lg font-semibold text-ink">{{ pointsPerImage }}</div></div>
            <div class="rounded-lg border border-line bg-card-soft px-3 py-3"><div class="text-xs text-ink-muted">每日上限</div><div class="mt-1 text-lg font-semibold text-ink">{{ capabilities?.daily_limit || '不限' }}</div></div>
            <div class="rounded-lg border border-line bg-card-soft px-3 py-3"><div class="text-xs text-ink-muted">保留期限</div><div class="mt-1 text-lg font-semibold text-ink">{{ capabilities?.retention_days || '永久' }}{{ capabilities?.retention_days ? ' 天' : '' }}</div></div>
          </div>

          <el-form label-position="top" @submit.prevent>
            <el-form-item label="生成模式">
              <el-radio-group v-model="form.mode" class="flex flex-wrap gap-2">
                <el-radio-button v-for="mode in availableModes" :key="mode" :value="mode">{{ modeLabels[mode] }}</el-radio-button>
              </el-radio-group>
              <p v-if="capabilities?.input.requires_capability_test && availableModes.length === 1" class="mt-2 text-xs text-ink-muted">当前模型尚未完成图片编辑能力测试，暂只开放文生图。</p>
            </el-form-item>

            <ImageInputWorkspace
              :mode="form.mode"
              :max-input-images="capabilities?.input.max_input_images ?? 0"
              :generated-sources="generatedSources"
              @change="handleInputReferences"
            />

            <el-form-item :label="form.mode === 'text_to_image' ? '图片描述' : '编辑指令'" required class="mt-5">
              <el-input
                v-model="form.prompt"
                type="textarea"
                :rows="6"
                maxlength="4000"
                show-word-limit
                :placeholder="form.mode === 'text_to_image' ? '描述画面主体、场景、风格、光线和构图，例如：雨后城市街道，水彩插画风格，暖色灯光。' : '明确描述希望改变的内容，例如：将背景替换为冬天雪景，保持人物姿势与主体构图不变。'"
              />
            </el-form-item>

            <el-form-item label="输出尺寸">
              <div class="mb-3 flex items-center justify-between gap-3 rounded-lg border border-brand-200 bg-brand-50/30 px-4 py-2.5">
                <div class="flex items-center gap-2">
                  <el-icon class="text-brand-500"><MagicStick /></el-icon>
                  <span class="text-sm font-medium text-brand-700">智能推荐尺寸</span>
                </div>
                <el-switch v-model="form.autoMode" :active-text="form.autoMode ? '已启用' : '已关闭'" />
              </div>
              <p v-if="form.autoMode && form.inferredExplanation" class="mb-3 rounded-md bg-canvas px-3 py-2 text-xs text-ink-soft">
                <el-icon class="mr-1 align-middle text-brand-500"><QuestionFilled /></el-icon>
                {{ form.inferredExplanation }}
              </p>
              <div v-if="capabilities?.output.kind === 'gemini'" class="grid w-full gap-3 sm:grid-cols-2">
                <div><p class="mb-1.5 text-xs text-ink-soft">画幅比例</p><el-select v-model="form.aspectRatio" :disabled="form.autoMode" class="w-full"><el-option v-for="ratio in capabilities.output.aspect_ratios" :key="ratio" :label="ratio" :value="ratio" /></el-select></div>
                <div><p class="mb-1.5 text-xs text-ink-soft">像素档位</p><el-select v-model="form.imageSize" :disabled="form.autoMode" class="w-full"><el-option v-for="imageSize in capabilities.output.image_sizes" :key="imageSize" :label="imageSize" :value="imageSize" /></el-select></div>
              </div>
              <div v-else-if="capabilities?.output.kind === 'openai-images'" class="w-full space-y-3">
                <el-radio-group v-model="form.size" :disabled="form.useCustomSize || form.autoMode" class="flex flex-wrap gap-2"><el-radio-button v-for="size in capabilities.output.preset_sizes" :key="size" :value="size">{{ size }}</el-radio-button></el-radio-group>
                <div v-if="capabilities.output.allow_custom_size" class="rounded-lg border border-line bg-card-soft px-3 py-3">
                  <div class="flex flex-wrap items-center justify-between gap-3"><span class="text-sm text-ink">自定义宽高</span><el-switch v-model="form.useCustomSize" :disabled="form.autoMode" /></div>
                  <div v-if="form.useCustomSize" class="mt-3 grid grid-cols-[1fr_auto_1fr] items-center gap-2"><el-input-number v-model="form.customWidth" :min="capabilities.output.custom_size_constraints.min_width" :max="capabilities.output.custom_size_constraints.max_width" :step="capabilities.output.custom_size_constraints.step" controls-position="right" /><span class="text-ink-muted">x</span><el-input-number v-model="form.customHeight" :min="capabilities.output.custom_size_constraints.min_height" :max="capabilities.output.custom_size_constraints.max_height" :step="capabilities.output.custom_size_constraints.step" controls-position="right" /></div>
                </div>
              </div>
              <el-radio-group v-else-if="capabilities?.output.kind === 'compatible-images'" v-model="form.size" :disabled="form.autoMode" class="flex flex-wrap gap-2"><el-radio-button v-for="size in capabilities.output.preset_sizes" :key="size" :value="size">{{ size }}</el-radio-button></el-radio-group>
              <div v-else class="rounded-lg border border-line bg-card-soft px-3 py-2.5 text-sm text-ink-soft">尺寸由当前模型决定，完成后会显示实际输出宽高。</div>
              <p v-if="isAvailable && !form.autoMode" class="mt-2 text-xs text-ink-muted">本次请求：{{ outputSelectionLabel() }}</p>
            </el-form-item>

            <el-button type="primary" class="min-h-10 w-full" :loading="submitting" :disabled="!canSubmit" @click="submit">
              <el-icon class="mr-1"><MagicStick /></el-icon>{{ hasActiveJob ? '等待当前任务完成' : `提交${modeLabels[form.mode]}${pointsPerImage ? `（${pointsPerImage} 积分）` : ''}` }}
            </el-button>
          </el-form>

          <div v-if="!isAvailable" class="rounded-lg border border-warning/30 bg-warning/5 p-3 text-xs leading-5 text-ink-soft">管理员尚未配置可用的生图模型。模型配置完成后，此页面会显示可选尺寸和已验证的编辑模式。</div>
        </div>
      </section>

      <!-- 右侧预览面板 -->
      <ImagePreviewPanel
        :job="activeJob"
        :preview-url="activeJobPreviewUrl"
        :status-labels="statusLabels"
      />
    </div>

    <!-- 底部历史记录面板 -->
    <ImageHistoryPanel
      :jobs="jobs"
      :preview-urls="previewUrls"
      :status-labels="statusLabels"
      :status-types="statusTypes"
      :mode-labels="modeLabels"
      @remove="removeJob"
      @select="handleSelectJob"
    />
  </div>
</template>
