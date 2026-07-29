<script setup lang="ts">
/** 私有图片输入工作区：上传、历史图复用与局部编辑蒙版绘制。 */
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { Brush, Picture, Upload } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type { UploadFile } from 'element-plus'
import { imageGenerationApi } from '@/api/endpoints'
import { ApiException } from '@/api/http'
import type {
  ImageGenerationInputAsset,
  ImageGenerationInputReference,
  ImageGenerationMode,
} from '@/api/types'

interface GeneratedImageChoice {
  jobId: string
  assetId: string
  width: number
  height: number
  previewUrl: string
  label: string
}

interface SelectedImage {
  sourceKind: 'uploaded' | 'generated'
  sourceId: string
  sourceJobId: string
  width: number
  height: number
  previewUrl: string
  label: string
}

const props = defineProps<{
  mode: ImageGenerationMode
  maxInputImages: number
  generatedSources: GeneratedImageChoice[]
}>()

const emit = defineEmits<{
  change: [references: ImageGenerationInputReference[]]
}>()

const loading = ref(false)
const uploading = ref(false)
const uploadedAssets = ref<ImageGenerationInputAsset[]>([])
const inputPreviewUrls = ref<Record<string, string>>({})
const source = ref<SelectedImage | null>(null)
const references = ref<SelectedImage[]>([])
const mask = ref<SelectedImage | null>(null)
const maskDialogVisible = ref(false)
const maskCanvas = ref<HTMLCanvasElement | null>(null)
const brushSize = ref(28)
const drawing = ref(false)
let lastPoint: { x: number; y: number } | null = null

const isEditMode = computed(() => props.mode !== 'text_to_image')
const isMaskedEdit = computed(() => props.mode === 'masked_edit')
const isMultiReference = computed(() => props.mode === 'multi_reference')
const maxReferences = computed(() => Math.max(0, props.maxInputImages - 1))
const sourceAssets = computed(() => uploadedAssets.value.filter((asset) => asset.kind === 'source'))
const maskAssets = computed(() => uploadedAssets.value.filter((asset) => asset.kind === 'mask'))
const sourceChoices = computed<SelectedImage[]>(() => [
  ...sourceAssets.value.map(uploadedChoice),
  ...props.generatedSources.map(generatedChoice),
])

function uploadedChoice(asset: ImageGenerationInputAsset): SelectedImage {
  return {
    sourceKind: 'uploaded',
    sourceId: asset.input_id,
    sourceJobId: '',
    width: asset.width,
    height: asset.height,
    previewUrl: inputPreviewUrls.value[asset.input_id] || '',
    label: `上传图片 ${formatDimensions(asset.width, asset.height)}`,
  }
}

function generatedChoice(asset: GeneratedImageChoice): SelectedImage {
  return {
    sourceKind: 'generated',
    sourceId: asset.assetId,
    sourceJobId: asset.jobId,
    width: asset.width,
    height: asset.height,
    previewUrl: asset.previewUrl,
    label: asset.label,
  }
}

function formatDimensions(width: number, height: number): string {
  return width > 0 && height > 0 ? `${width}x${height}` : '图片'
}

function sameChoice(left: SelectedImage | null, right: SelectedImage): boolean {
  return !!left && left.sourceKind === right.sourceKind && left.sourceId === right.sourceId
}

function choiceReference(value: SelectedImage, role: ImageGenerationInputReference['role']): ImageGenerationInputReference {
  return {
    source_kind: value.sourceKind,
    source_id: value.sourceId,
    ...(value.sourceJobId ? { source_job_id: value.sourceJobId } : {}),
    role,
  }
}

function emitReferences() {
  if (!isEditMode.value || !source.value) {
    emit('change', [])
    return
  }
  const result: ImageGenerationInputReference[] = [choiceReference(source.value, 'source')]
  if (isMultiReference.value) {
    result.push(...references.value.map((item) => choiceReference(item, 'reference')))
  }
  if (isMaskedEdit.value && mask.value) {
    result.push(choiceReference(mask.value, 'mask'))
  }
  emit('change', result)
}

async function loadUploadedAssets() {
  loading.value = true
  try {
    const result = await imageGenerationApi.inputs({ limit: 60 })
    revokeInputPreviewUrls()
    uploadedAssets.value = result.assets
    await Promise.all(result.assets.map(loadInputPreview))
  } catch (error) {
    ElMessage.error(error instanceof ApiException ? error.message : '加载私有图片失败')
  } finally {
    loading.value = false
  }
}

async function loadInputPreview(asset: ImageGenerationInputAsset) {
  if (inputPreviewUrls.value[asset.input_id]) return
  try {
    const blob = await imageGenerationApi.inputContent(asset.input_id)
    inputPreviewUrls.value = {
      ...inputPreviewUrls.value,
      [asset.input_id]: URL.createObjectURL(blob),
    }
  } catch {
    // 预览读取失败不会影响该资产的权限校验或任务提交。
  }
}

function revokeInputPreviewUrls() {
  Object.values(inputPreviewUrls.value).forEach((url) => URL.revokeObjectURL(url))
  inputPreviewUrls.value = {}
}

async function upload(file: UploadFile, kind: 'source' | 'mask') {
  const raw = file.raw
  if (!raw) return
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(raw.type)) {
    ElMessage.warning('仅支持 PNG、JPEG 或 WebP 图片')
    return
  }
  if (raw.size > 10 * 1024 * 1024) {
    ElMessage.warning('图片不能超过 10MB')
    return
  }
  uploading.value = true
  try {
    const result = await imageGenerationApi.uploadInput(raw, kind)
    uploadedAssets.value = [result.asset, ...uploadedAssets.value]
    await loadInputPreview(result.asset)
    const choice = uploadedChoice(result.asset)
    if (kind === 'mask') {
      mask.value = choice
    } else if (!source.value) {
      source.value = choice
    } else if (isMultiReference.value && references.value.length < maxReferences.value) {
      references.value = [...references.value, choice]
    }
    emitReferences()
    ElMessage.success(kind === 'mask' ? '蒙版已上传' : '参考图已上传')
  } catch (error) {
    ElMessage.error(error instanceof ApiException ? error.message : '上传图片失败')
  } finally {
    uploading.value = false
  }
}

function uploadSource(file: UploadFile) {
  void upload(file, 'source')
}

function uploadMask(file: UploadFile) {
  void upload(file, 'mask')
}

function selectSource(choice: SelectedImage) {
  source.value = choice
  if (mask.value && (!isMaskedEdit.value || !sameDimensions(mask.value, choice))) {
    mask.value = null
  }
  references.value = references.value.filter((item) => !sameChoice(item, choice))
  emitReferences()
}

function toggleReference(choice: SelectedImage) {
  if (sameChoice(source.value, choice)) {
    ElMessage.warning('主图不能同时作为参考图')
    return
  }
  const index = references.value.findIndex((item) => sameChoice(item, choice))
  if (index >= 0) {
    references.value = references.value.filter((_, currentIndex) => currentIndex !== index)
  } else if (references.value.length >= maxReferences.value) {
    ElMessage.warning(`当前模型最多额外选择 ${maxReferences.value} 张参考图`)
    return
  } else {
    references.value = [...references.value, choice]
  }
  emitReferences()
}

function selectMask(choice: SelectedImage) {
  if (!source.value) {
    ElMessage.warning('请先选择需要编辑的主图')
    return
  }
  if (!sameDimensions(choice, source.value)) {
    ElMessage.warning('蒙版尺寸必须与主图完全一致')
    return
  }
  mask.value = choice
  emitReferences()
}

function sameDimensions(left: SelectedImage, right: SelectedImage): boolean {
  return left.width === right.width && left.height === right.height
}

async function openMaskCanvas() {
  if (!source.value?.previewUrl) {
    ElMessage.warning('请先选择并等待主图预览加载完成')
    return
  }
  maskDialogVisible.value = true
  await nextTick()
  initializeMaskCanvas()
}

function initializeMaskCanvas() {
  if (!source.value || !maskCanvas.value) return
  const canvas = maskCanvas.value
  canvas.width = source.value.width
  canvas.height = source.value.height
  const context = canvas.getContext('2d')
  context?.clearRect(0, 0, canvas.width, canvas.height)
  canvas.style.backgroundImage = `url("${source.value.previewUrl}")`
  canvas.style.backgroundSize = '100% 100%'
  canvas.style.backgroundPosition = 'center'
  canvas.style.backgroundRepeat = 'no-repeat'
}

function pointFromEvent(event: PointerEvent): { x: number; y: number } | null {
  const canvas = maskCanvas.value
  if (!canvas) return null
  const bounds = canvas.getBoundingClientRect()
  if (!bounds.width || !bounds.height) return null
  return {
    x: ((event.clientX - bounds.left) / bounds.width) * canvas.width,
    y: ((event.clientY - bounds.top) / bounds.height) * canvas.height,
  }
}

function startDrawing(event: PointerEvent) {
  const point = pointFromEvent(event)
  if (!point || !maskCanvas.value) return
  drawing.value = true
  lastPoint = point
  maskCanvas.value.setPointerCapture(event.pointerId)
  drawSegment(point, point)
}

function continueDrawing(event: PointerEvent) {
  if (!drawing.value) return
  const point = pointFromEvent(event)
  if (!point || !lastPoint) return
  drawSegment(lastPoint, point)
  lastPoint = point
}

function finishDrawing() {
  drawing.value = false
  lastPoint = null
}

function drawSegment(from: { x: number; y: number }, to: { x: number; y: number }) {
  const canvas = maskCanvas.value
  const context = canvas?.getContext('2d')
  if (!canvas || !context) return
  const visibleWidth = canvas.getBoundingClientRect().width || canvas.width
  context.strokeStyle = '#ffffff'
  context.lineCap = 'round'
  context.lineJoin = 'round'
  context.lineWidth = Math.max(1, (brushSize.value * canvas.width) / visibleWidth)
  context.beginPath()
  context.moveTo(from.x, from.y)
  context.lineTo(to.x, to.y)
  context.stroke()
}

function clearMaskCanvas() {
  const canvas = maskCanvas.value
  const context = canvas?.getContext('2d')
  if (canvas && context) context.clearRect(0, 0, canvas.width, canvas.height)
}

async function saveDrawnMask() {
  const canvas = maskCanvas.value
  if (!canvas || !source.value) return
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/png'))
  if (!blob) {
    ElMessage.error('无法生成蒙版文件')
    return
  }
  uploading.value = true
  try {
    const result = await imageGenerationApi.uploadInput(
      new File([blob], 'edit-mask.png', { type: 'image/png' }),
      'mask',
    )
    uploadedAssets.value = [result.asset, ...uploadedAssets.value]
    await loadInputPreview(result.asset)
    mask.value = uploadedChoice(result.asset)
    maskDialogVisible.value = false
    emitReferences()
    ElMessage.success('蒙版已保存')
  } catch (error) {
    ElMessage.error(error instanceof ApiException ? error.message : '保存蒙版失败')
  } finally {
    uploading.value = false
  }
}

watch(
  () => props.mode,
  (mode) => {
    if (mode === 'text_to_image') {
      source.value = null
      references.value = []
      mask.value = null
    }
    if (mode !== 'multi_reference') references.value = []
    if (mode !== 'masked_edit') mask.value = null
    emitReferences()
  },
)

watch(maxReferences, () => {
  references.value = references.value.slice(0, maxReferences.value)
  emitReferences()
})

onMounted(() => {
  void loadUploadedAssets()
})

onUnmounted(() => {
  revokeInputPreviewUrls()
})
</script>

<template>
  <section v-if="isEditMode" v-loading="loading" class="space-y-4 rounded-lg border border-line bg-card-soft p-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h4 class="text-sm font-semibold text-ink">图片输入</h4>
        <p class="mt-1 text-xs text-ink-soft">上传图片和历史生成结果均为私有资产，仅在当前任务中按引用使用。</p>
      </div>
      <el-upload action="" :auto-upload="false" :show-file-list="false" accept="image/png,image/jpeg,image/webp" :on-change="uploadSource">
        <el-button size="small" :loading="uploading" plain type="primary">
          <el-icon class="mr-1"><Upload /></el-icon>上传图片
        </el-button>
      </el-upload>
    </div>

    <div>
      <div class="mb-2 flex items-center justify-between gap-2">
        <span class="text-sm font-medium text-ink">主图</span>
        <span v-if="source" class="text-xs text-ink-muted">{{ source.label }}</span>
      </div>
      <div v-if="sourceChoices.length" class="grid grid-cols-3 gap-2 sm:grid-cols-5">
        <button
          v-for="choice in sourceChoices"
          :key="`${choice.sourceKind}:${choice.sourceId}`"
          type="button"
          class="group overflow-hidden rounded-md border bg-canvas text-left transition-colors"
          :class="sameChoice(source, choice) ? 'border-brand-500 ring-1 ring-brand-500' : 'border-line hover:border-brand-300'"
          @click="selectSource(choice)"
        >
          <img v-if="choice.previewUrl" :src="choice.previewUrl" class="aspect-square w-full object-cover" :alt="choice.label" />
          <span v-else class="flex aspect-square items-center justify-center text-ink-muted"><el-icon><Picture /></el-icon></span>
          <span class="block truncate px-1.5 py-1 text-[11px] text-ink-soft">{{ choice.sourceKind === 'generated' ? '历史生成' : '上传图片' }}</span>
        </button>
      </div>
      <el-empty v-else :image-size="52" description="上传一张图片或先完成一次生图" />
    </div>

    <div v-if="isMultiReference">
      <div class="mb-2 flex items-center justify-between gap-2">
        <span class="text-sm font-medium text-ink">参考图</span>
        <span class="text-xs text-ink-muted">已选 {{ references.length }}/{{ maxReferences }}</span>
      </div>
      <div class="grid grid-cols-3 gap-2 sm:grid-cols-5">
        <button
          v-for="choice in sourceChoices"
          :key="`reference:${choice.sourceKind}:${choice.sourceId}`"
          type="button"
          class="overflow-hidden rounded-md border bg-canvas text-left transition-colors"
          :class="references.some((item) => sameChoice(item, choice)) ? 'border-brand-500 ring-1 ring-brand-500' : 'border-line hover:border-brand-300'"
          @click="toggleReference(choice)"
        >
          <img v-if="choice.previewUrl" :src="choice.previewUrl" class="aspect-square w-full object-cover" :alt="choice.label" />
          <span v-else class="flex aspect-square items-center justify-center text-ink-muted"><el-icon><Picture /></el-icon></span>
        </button>
      </div>
    </div>

    <div v-if="isMaskedEdit" class="space-y-3">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <div>
          <span class="text-sm font-medium text-ink">局部编辑蒙版</span>
          <p class="mt-1 text-xs text-ink-soft">白色表示允许修改，黑色表示保持原样；蒙版必须和主图同尺寸。</p>
        </div>
        <div class="flex gap-2">
          <el-upload action="" :auto-upload="false" :show-file-list="false" accept="image/png,image/jpeg,image/webp" :on-change="uploadMask">
            <el-button size="small" :loading="uploading">上传蒙版</el-button>
          </el-upload>
          <el-button size="small" type="primary" plain :disabled="!source" @click="openMaskCanvas">
            <el-icon class="mr-1"><Brush /></el-icon>绘制蒙版
          </el-button>
        </div>
      </div>
      <div v-if="maskAssets.length" class="grid grid-cols-3 gap-2 sm:grid-cols-5">
        <button
          v-for="asset in maskAssets"
          :key="asset.input_id"
          type="button"
          class="overflow-hidden rounded-md border bg-canvas text-left transition-colors"
          :class="sameChoice(mask, uploadedChoice(asset)) ? 'border-brand-500 ring-1 ring-brand-500' : 'border-line hover:border-brand-300'"
          @click="selectMask(uploadedChoice(asset))"
        >
          <img v-if="inputPreviewUrls[asset.input_id]" :src="inputPreviewUrls[asset.input_id]" class="aspect-square w-full object-cover" alt="局部编辑蒙版" />
          <span v-else class="flex aspect-square items-center justify-center text-ink-muted"><el-icon><Brush /></el-icon></span>
          <span class="block truncate px-1.5 py-1 text-[11px] text-ink-soft">{{ formatDimensions(asset.width, asset.height) }}</span>
        </button>
      </div>
    </div>

    <el-dialog v-model="maskDialogVisible" title="绘制局部编辑蒙版" width="min(880px, 94vw)" destroy-on-close @opened="initializeMaskCanvas">
      <div class="space-y-3">
        <p class="text-sm leading-6 text-ink-soft">在主图上涂白需要修改的区域。未涂白的透明区域会被保存为黑色保留区域。</p>
        <div class="max-h-[58vh] overflow-auto rounded-lg border border-line bg-canvas p-3">
          <canvas
            ref="maskCanvas"
            class="mx-auto block max-h-[52vh] max-w-full cursor-crosshair bg-cover bg-center bg-no-repeat"
            @pointerdown.prevent="startDrawing"
            @pointermove.prevent="continueDrawing"
            @pointerup="finishDrawing"
            @pointerleave="finishDrawing"
          />
        </div>
        <div class="flex flex-wrap items-center gap-3">
          <span class="text-sm text-ink">画笔大小</span>
          <el-slider v-model="brushSize" :min="4" :max="100" class="max-w-72 flex-1" />
          <el-button @click="clearMaskCanvas">清空蒙版</el-button>
        </div>
      </div>
      <template #footer>
        <el-button @click="maskDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="uploading" @click="saveDrawnMask">保存蒙版</el-button>
      </template>
    </el-dialog>
  </section>
</template>
