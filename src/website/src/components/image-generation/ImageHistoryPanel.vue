<script setup lang="ts">
/** 底部历史记录面板 - 支持拖拽高度调整 */
import { ref, computed } from 'vue'
import { Delete } from '@element-plus/icons-vue'
import { formatDateTime } from '@/utils/format'
import type { ImageGenerationJob, ImageGenerationJobStatus } from '@/api/types'

interface Props {
  jobs: ImageGenerationJob[]
  previewUrls: Record<string, string>
  statusLabels: Record<ImageGenerationJobStatus, string>
  statusTypes: Record<ImageGenerationJobStatus, 'info' | 'warning' | 'success' | 'danger'>
  modeLabels: Record<string, string>
}

interface Emits {
  (e: 'remove', job: ImageGenerationJob): void
  (e: 'select', job: ImageGenerationJob): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const panelHeight = ref(300) // 默认高度 300px
const isDragging = ref(false)
const dragStartY = ref(0)
const dragStartHeight = ref(0)

const panelStyle = computed(() => ({
  height: `${panelHeight.value}px`,
  minHeight: '200px',
  maxHeight: '600px',
}))

function startResize(event: MouseEvent) {
  isDragging.value = true
  dragStartY.value = event.clientY
  dragStartHeight.value = panelHeight.value
  document.addEventListener('mousemove', onResize)
  document.addEventListener('mouseup', stopResize)
  event.preventDefault()
}

function onResize(event: MouseEvent) {
  if (!isDragging.value) return
  const deltaY = dragStartY.value - event.clientY // 向上拖拽为正
  const newHeight = Math.max(200, Math.min(600, dragStartHeight.value + deltaY))
  panelHeight.value = newHeight
}

function stopResize() {
  isDragging.value = false
  document.removeEventListener('mousemove', onResize)
  document.removeEventListener('mouseup', stopResize)
}

function handleSelect(job: ImageGenerationJob) {
  emit('select', job)
}

function handleRemove(job: ImageGenerationJob, event: Event) {
  event.stopPropagation()
  emit('remove', job)
}

function jobOutputLabel(job: ImageGenerationJob): string {
  const requested = job.output.aspect_ratio && job.output.image_size
    ? `${job.output.aspect_ratio} · ${job.output.image_size}`
    : job.output.size || job.size || '由模型决定'
  const asset = job.assets[0]
  return asset?.width && asset?.height ? `${requested} · 实际 ${asset.width}x${asset.height}` : requested
}
</script>

<template>
  <div class="app-card flex flex-col overflow-hidden" :style="panelStyle">
    <!-- 拖拽手柄 -->
    <div
      class="group flex h-2 cursor-ns-resize items-center justify-center border-b border-line bg-gradient-to-b from-canvas to-card-soft transition-colors hover:border-brand-300 hover:bg-brand-50/30"
      @mousedown="startResize"
    >
      <div class="h-1 w-12 rounded-full bg-ink-muted/20 transition-colors group-hover:bg-brand-400"></div>
    </div>

    <!-- 标题栏 -->
    <div class="flex items-center justify-between border-b border-line px-5 py-3">
      <div>
        <h3 class="text-base font-semibold text-ink">历史记录</h3>
        <p class="mt-0.5 text-xs text-ink-soft">点击图片可查看详情，支持拖拽到编辑区复用</p>
      </div>
      <el-tag size="small" type="info" effect="plain">{{ jobs.length }} 条记录</el-tag>
    </div>

    <!-- 历史记录网格 -->
    <div class="flex-1 overflow-y-auto p-4">
      <div v-if="!jobs.length" class="flex h-full items-center justify-center">
        <el-empty description="暂无生成记录" :image-size="80" />
      </div>
      <div v-else class="grid gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 2xl:grid-cols-8">
        <article
          v-for="job in jobs"
          :key="job.job_id"
          class="group relative cursor-pointer overflow-hidden rounded-lg border border-line bg-card-soft transition-all hover:border-brand-300 hover:shadow-md"
          @click="handleSelect(job)"
        >
          <!-- 图片预览 -->
          <div class="aspect-square bg-canvas">
            <img
              v-if="job.status === 'succeeded' && previewUrls[job.assets[0]?.asset_id]"
              :src="previewUrls[job.assets[0]?.asset_id]"
              class="h-full w-full object-cover transition-transform group-hover:scale-105"
              alt="AI 生成图片"
            />
            <div v-else class="flex h-full items-center justify-center text-xs text-ink-muted">
              {{ statusLabels[job.status] }}
            </div>
          </div>

          <!-- 状态标签 -->
          <el-tag
            size="small"
            :type="statusTypes[job.status]"
            effect="plain"
            class="absolute right-2 top-2"
          >
            {{ statusLabels[job.status] }}
          </el-tag>

          <!-- 底部信息 -->
          <div class="border-t border-line bg-white px-2 py-2">
            <p class="line-clamp-1 text-xs font-medium text-ink">{{ job.prompt }}</p>
            <div class="mt-1 flex items-center justify-between gap-2">
              <span class="text-xs text-ink-muted">{{ modeLabels[job.mode] }}</span>
              <el-button
                v-if="job.status !== 'running' && job.status !== 'deleted'"
                link
                type="danger"
                size="small"
                :icon="Delete"
                @click="(e: Event) => handleRemove(job, e)"
              />
            </div>
          </div>
        </article>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 自定义滚动条样式 */
.overflow-y-auto::-webkit-scrollbar {
  width: 6px;
}

.overflow-y-auto::-webkit-scrollbar-track {
  background: var(--el-fill-color-lighter);
  border-radius: 3px;
}

.overflow-y-auto::-webkit-scrollbar-thumb {
  background: var(--el-color-info-light-5);
  border-radius: 3px;
}

.overflow-y-auto::-webkit-scrollbar-thumb:hover {
  background: var(--el-color-primary);
}
</style>
