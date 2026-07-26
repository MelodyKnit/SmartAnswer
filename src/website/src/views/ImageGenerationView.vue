<script setup lang="ts">
/** AI 生图：提交私有文本生图任务、轮询状态并通过受保护接口预览结果。 */
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { Picture, Refresh, MagicStick, QuestionFilled } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { imageGenerationApi } from '@/api/endpoints'
import { ApiException } from '@/api/http'
import type {
  ImageGenerationCapabilities,
  ImageGenerationJob,
  ImageGenerationJobStatus,
  ImageGenerationOutputOptions,
} from '@/api/types'
import PageHeader from '@/components/PageHeader.vue'
import { useAuthStore } from '@/stores/auth'
import { formatDateTime } from '@/utils/format'

const auth = useAuthStore()
const loading = ref(false)
const submitting = ref(false)
const capabilities = ref<ImageGenerationCapabilities | null>(null)
const jobs = ref<ImageGenerationJob[]>([])
const activeJobId = ref('')
const previewUrls = ref<Record<string, string>>({})
let pollTimer: number | undefined

const form = reactive({
  prompt: '',
  size: '',
  aspectRatio: '',
  imageSize: '',
  useCustomSize: false,
  customWidth: 1024,
  customHeight: 1024,
})

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
const activeJob = computed(() => jobs.value.find((job) => job.job_id === activeJobId.value) || null)
const hasActiveJob = computed(() => jobs.value.some((job) => job.status === 'queued' || job.status === 'running'))
const canSubmit = computed(
  () =>
    isAvailable.value &&
    form.prompt.trim().length > 0 &&
    !submitting.value &&
    !hasActiveJob.value &&
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
  if (output.kind === 'openai-images' && form.useCustomSize) {
    return { size: `${form.customWidth}x${form.customHeight}` }
  }
  if (output.kind === 'openai-images' || output.kind === 'compatible-images') {
    return { size: form.size || output.preset_sizes[0] }
  }
  return undefined
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

async function refreshCapabilities() {
  const result = await imageGenerationApi.capabilities()
  capabilities.value = result.capabilities
  syncOutputDefaults(result.capabilities)
}

async function refreshActiveJob() {
  if (!activeJobId.value) return
  try {
    const result = await imageGenerationApi.detail(activeJobId.value)
    const index = jobs.value.findIndex((item) => item.job_id === result.job.job_id)
    if (index >= 0) {
      jobs.value.splice(index, 1, result.job)
    } else {
      jobs.value.unshift(result.job)
    }
    if (result.job.status === 'succeeded') {
      await loadPreview(result.job)
    }
    if (!['queued', 'running'].includes(result.job.status)) {
      activeJobId.value = ''
      stopPolling()
      await Promise.all([auth.refreshProfile(), refreshCapabilities()])
    }
  } catch (error) {
    if (error instanceof ApiException && error.code !== 'JOB_NOT_FOUND') {
      ElMessage.warning(error.message)
    }
    activeJobId.value = ''
  }
}

function startPolling() {
  if (pollTimer !== undefined) return
  pollTimer = window.setInterval(() => {
    void refreshActiveJob()
  }, 1_200)
}

function stopPolling() {
  if (pollTimer === undefined) return
  window.clearInterval(pollTimer)
  pollTimer = undefined
}

async function submit() {
  if (!form.prompt.trim()) {
    ElMessage.warning('请输入图片描述')
    return
  }
  if (!isAvailable.value) {
    ElMessage.warning('当前没有可用的生图模型')
    return
  }
  if (hasActiveJob.value) {
    ElMessage.warning('当前仍有生成中的任务，请等待完成后再提交')
    return
  }
  submitting.value = true
  try {
    const result = await imageGenerationApi.create({
      prompt: form.prompt.trim(),
      ...(buildOutput() ? { output: buildOutput() } : {}),
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
    ElMessage.success(result.idempotent_replay ? '已恢复原生图任务' : '生图任务已提交')
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
        ? '取消排队任务会自动退还预扣积分。'
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

onMounted(async () => {
  await load()
  if (hasActiveJob.value) startPolling()
})

onUnmounted(() => {
  stopPolling()
  revokePreviewUrls()
})
</script>

<template>
  <div v-loading="loading" class="space-y-4">
    <PageHeader title="AI 生图" description="使用私有生图模型生成一张图片；任务失败会自动退还预扣积分。">
      <template #actions>
        <el-button :icon="Refresh" @click="load">刷新</el-button>
      </template>
    </PageHeader>

    <div class="grid items-start gap-4 xl:grid-cols-[minmax(360px,0.9fr)_minmax(480px,1.1fr)]">
      <section class="app-card overflow-hidden">
        <div class="border-b border-line bg-canvas/30 px-5 py-4">
          <div class="flex items-start justify-between gap-4">
            <div>
              <p class="text-xs font-semibold uppercase tracking-[0.18em] text-brand-500">Image Generation</p>
              <h3 class="mt-1 flex items-center gap-2 text-lg font-semibold text-ink">
                <el-icon class="text-brand-500"><Picture /></el-icon>
                <span>文本生成图片</span>
                <el-tooltip
                  content="仅支持单张文本生图。提交后会锁定一次任务，模型拒绝、超时或图片校验失败会自动退款。"
                  placement="top"
                  :show-after="100"
                >
                  <el-icon class="text-ink-muted/60 hover:text-brand-500 cursor-help transition-colors text-sm">
                    <QuestionFilled />
                  </el-icon>
                </el-tooltip>
              </h3>
            </div>
            <el-tag :type="isAvailable ? 'success' : 'info'" effect="plain">
              {{ isAvailable ? '模型可用' : '暂不可用' }}
            </el-tag>
          </div>
        </div>

        <div class="space-y-5 p-5">
          <div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div class="rounded-lg border border-line bg-card-soft px-3 py-3">
              <div class="text-xs text-ink-muted">可用余额</div>
              <div class="mt-1 text-lg font-semibold text-ink">{{ capabilities?.balance ?? '—' }}</div>
            </div>
            <div class="rounded-lg border border-line bg-card-soft px-3 py-3">
              <div class="text-xs text-ink-muted">单张扣费</div>
              <div class="mt-1 text-lg font-semibold text-ink">{{ pointsPerImage }}</div>
            </div>
            <div class="rounded-lg border border-line bg-card-soft px-3 py-3">
              <div class="text-xs text-ink-muted">每日上限</div>
              <div class="mt-1 text-lg font-semibold text-ink">{{ capabilities?.daily_limit || '不限' }}</div>
            </div>
            <div class="rounded-lg border border-line bg-card-soft px-3 py-3">
              <div class="text-xs text-ink-muted">保留期限</div>
              <div class="mt-1 text-lg font-semibold text-ink">{{ capabilities?.retention_days || '永久' }}{{ capabilities?.retention_days ? ' 天' : '' }}</div>
            </div>
          </div>

          <el-form label-position="top" @submit.prevent>
            <el-form-item label="图片描述" required>
              <el-input
                v-model="form.prompt"
                type="textarea"
                :rows="8"
                maxlength="4000"
                show-word-limit
                placeholder="描述画面主体、场景、风格、光线和构图，例如：雨后城市街道，水彩插画风格，暖色灯光。"
              />
            </el-form-item>
            <el-form-item label="输出尺寸">
              <div v-if="capabilities?.output.kind === 'gemini'" class="grid w-full gap-3 sm:grid-cols-2">
                <div>
                  <p class="mb-1.5 text-xs text-ink-soft">画幅比例</p>
                  <el-select v-model="form.aspectRatio" class="w-full">
                    <el-option
                      v-for="ratio in capabilities.output.aspect_ratios"
                      :key="ratio"
                      :label="ratio"
                      :value="ratio"
                    />
                  </el-select>
                </div>
                <div>
                  <p class="mb-1.5 text-xs text-ink-soft">像素档位</p>
                  <el-select v-model="form.imageSize" class="w-full">
                    <el-option
                      v-for="imageSize in capabilities.output.image_sizes"
                      :key="imageSize"
                      :label="imageSize"
                      :value="imageSize"
                    />
                  </el-select>
                </div>
              </div>
              <div v-else-if="capabilities?.output.kind === 'openai-images'" class="w-full space-y-3">
                <el-radio-group v-model="form.size" :disabled="form.useCustomSize" class="flex flex-wrap gap-2">
                  <el-radio-button
                    v-for="size in capabilities.output.preset_sizes"
                    :key="size"
                    :value="size"
                  >
                    {{ size }}
                  </el-radio-button>
                </el-radio-group>
                <div v-if="capabilities.output.allow_custom_size" class="rounded-lg border border-line bg-card-soft px-3 py-3">
                  <div class="flex flex-wrap items-center justify-between gap-3">
                    <span class="text-sm text-ink">自定义宽高</span>
                    <el-switch v-model="form.useCustomSize" />
                  </div>
                  <div v-if="form.useCustomSize" class="mt-3 grid grid-cols-[1fr_auto_1fr] items-center gap-2">
                    <el-input-number v-model="form.customWidth" :min="capabilities.output.custom_size_constraints.min_width" :max="capabilities.output.custom_size_constraints.max_width" :step="capabilities.output.custom_size_constraints.step" controls-position="right" />
                    <span class="text-ink-muted">x</span>
                    <el-input-number v-model="form.customHeight" :min="capabilities.output.custom_size_constraints.min_height" :max="capabilities.output.custom_size_constraints.max_height" :step="capabilities.output.custom_size_constraints.step" controls-position="right" />
                  </div>
                </div>
              </div>
              <el-radio-group v-else-if="capabilities?.output.kind === 'compatible-images'" v-model="form.size" class="flex flex-wrap gap-2">
                <el-radio-button
                  v-for="size in capabilities.output.preset_sizes"
                  :key="size"
                  :value="size"
                >
                  {{ size }}
                </el-radio-button>
              </el-radio-group>
              <div v-else class="rounded-lg border border-line bg-card-soft px-3 py-2.5 text-sm text-ink-soft">
                尺寸由当前模型决定，生成完成后会显示实际输出宽高。
              </div>
              <p v-if="isAvailable" class="mt-2 text-xs text-ink-muted">本次请求：{{ outputSelectionLabel() }}</p>
            </el-form-item>
            <el-button type="primary" class="min-h-10 w-full" :loading="submitting" :disabled="!canSubmit" @click="submit">
              <el-icon class="mr-1"><MagicStick /></el-icon>
              {{ hasActiveJob ? '等待当前任务完成' : `生成图片${pointsPerImage ? `（${pointsPerImage} 积分）` : ''}` }}
            </el-button>
          </el-form>

          <div v-if="!isAvailable" class="rounded-lg border border-warning/30 bg-warning/5 p-3 text-xs leading-5 text-ink-soft">
            管理员尚未配置可用的生图模型。模型配置完成后，此页面会显示可选画幅或尺寸。
          </div>
        </div>
      </section>

      <section class="app-card overflow-hidden">
        <div class="flex items-center justify-between border-b border-line px-5 py-4">
          <div>
            <h3 class="text-lg font-semibold text-ink">我的生成记录</h3>
            <p class="mt-1 text-xs text-ink-soft">生成结果仅本人和管理员可查看。</p>
          </div>
          <el-tag v-if="activeJob" type="warning" effect="plain">{{ statusLabels[activeJob.status] }}</el-tag>
        </div>

        <div v-if="!jobs.length" class="flex min-h-80 items-center justify-center px-5">
          <el-empty description="暂无生图记录" />
        </div>
        <div v-else class="grid gap-4 p-5 sm:grid-cols-2">
          <article v-for="job in jobs" :key="job.job_id" class="overflow-hidden rounded-lg border border-line bg-card-soft">
            <div class="flex items-start justify-between gap-3 border-b border-line px-4 py-3">
              <div class="min-w-0">
                <p class="line-clamp-2 text-sm font-medium leading-5 text-ink">{{ job.prompt }}</p>
                <p class="mt-1 text-xs text-ink-muted">{{ jobOutputLabel(job) }} · {{ formatDateTime(job.created_at) }}</p>
              </div>
              <el-tag size="small" :type="statusTypes[job.status]" effect="plain">
                {{ statusLabels[job.status] }}
              </el-tag>
            </div>
            <div v-if="job.status === 'succeeded' && job.assets.length" class="aspect-square bg-canvas">
              <img
                v-if="previewUrls[job.assets[0].asset_id]"
                :src="previewUrls[job.assets[0].asset_id]"
                class="h-full w-full object-cover"
                alt="AI 生成图片"
              />
              <div v-else class="flex h-full items-center justify-center text-sm text-ink-muted">加载预览中</div>
            </div>
            <div v-else class="min-h-28 px-4 py-3 text-xs leading-5 text-ink-soft">
              <template v-if="job.status === 'queued' || job.status === 'running'">
                正在处理此任务，完成后会自动显示私有预览。
              </template>
              <template v-else>{{ job.error_message || '该任务未产生可访问图片。' }}</template>
            </div>
            <div class="flex items-center justify-between gap-3 border-t border-line px-4 py-3">
              <span class="text-xs text-ink-muted">{{ job.points_cost }} 积分</span>
              <el-button
                v-if="job.status !== 'running' && job.status !== 'deleted'"
                link
                type="danger"
                @click="removeJob(job)"
              >
                {{ job.status === 'queued' ? '取消' : '删除' }}
              </el-button>
            </div>
          </article>
        </div>
      </section>
    </div>
  </div>
</template>
