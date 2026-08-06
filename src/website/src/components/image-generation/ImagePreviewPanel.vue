<script setup lang="ts">
/** 右侧预览面板 - 显示生成进度和结果 */
import { computed } from 'vue'
import { Picture, Loading, WarningFilled } from '@element-plus/icons-vue'
import type { ImageGenerationJob, ImageGenerationJobStatus } from '@/api/types'

interface Props {
  job: ImageGenerationJob | null
  previewUrl: string
  statusLabels: Record<ImageGenerationJobStatus, string>
}

const props = defineProps<Props>()

const isGenerating = computed(() =>
  props.job?.status === 'queued' || props.job?.status === 'running'
)

const hasError = computed(() =>
  props.job?.status === 'failed' || props.job?.status === 'rejected'
)

const hasResult = computed(() =>
  props.job?.status === 'succeeded' && props.previewUrl
)
</script>

<template>
  <div class="app-card flex h-full flex-col overflow-hidden">
    <!-- 顶部标题栏 -->
    <div class="border-b border-line bg-gradient-to-br from-brand-50/40 to-canvas/30 px-5 py-4">
      <div class="flex items-center justify-between gap-4">
        <div>
          <p class="text-xs font-semibold uppercase tracking-[0.18em] text-brand-600">Preview</p>
          <h3 class="mt-1 flex items-center gap-2 text-lg font-semibold text-ink">
            <el-icon class="text-brand-500"><Picture /></el-icon>
            <span>实时预览</span>
          </h3>
        </div>
        <el-tag v-if="job" :type="isGenerating ? 'warning' : hasError ? 'danger' : 'success'" effect="plain">
          {{ statusLabels[job.status] }}
        </el-tag>
      </div>
    </div>

    <!-- 预览内容区 -->
    <div class="flex flex-1 flex-col items-center justify-center overflow-hidden bg-canvas p-5">
      <!-- 生成中状态 -->
      <div v-if="isGenerating" class="flex flex-col items-center gap-4 text-center">
        <el-icon class="animate-spin text-6xl text-brand-500"><Loading /></el-icon>
        <div>
          <p class="text-lg font-medium text-ink">{{ statusLabels[job!.status] }}</p>
          <p class="mt-2 text-sm text-ink-muted">{{ job!.prompt }}</p>
        </div>
        <el-progress
          :percentage="job!.status === 'running' ? 60 : 30"
          :indeterminate="true"
          class="w-64"
        />
      </div>

      <!-- 生成成功 -->
      <div v-else-if="hasResult" class="flex h-full w-full flex-col items-center gap-4">
        <div class="flex-1 overflow-auto rounded-lg border border-line bg-white shadow-sm">
          <img
            :src="previewUrl"
            :alt="job!.prompt"
            class="h-full w-full object-contain"
          />
        </div>
        <div class="w-full rounded-lg border border-line bg-card-soft px-4 py-3">
          <p class="line-clamp-2 text-sm font-medium text-ink">{{ job!.prompt }}</p>
          <div class="mt-2 flex items-center gap-3 text-xs text-ink-muted">
            <span>{{ job!.assets[0]?.width }}x{{ job!.assets[0]?.height }}</span>
            <span>•</span>
            <span>{{ job!.points_cost }} 积分</span>
          </div>
        </div>
      </div>

      <!-- 生成失败 -->
      <div v-else-if="hasError" class="flex flex-col items-center gap-4 text-center">
        <el-icon class="text-6xl text-danger"><WarningFilled /></el-icon>
        <div>
          <p class="text-lg font-medium text-ink">{{ statusLabels[job!.status] }}</p>
          <p class="mt-2 text-sm text-ink-muted">{{ job!.error_message || '生成过程中发生错误' }}</p>
        </div>
      </div>

      <!-- 空状态 -->
      <div v-else class="flex flex-col items-center gap-4 text-center">
        <el-icon class="text-6xl text-ink-muted/30"><Picture /></el-icon>
        <div>
          <p class="text-lg font-medium text-ink-muted">暂无预览</p>
          <p class="mt-2 text-sm text-ink-muted">提交生成任务后会在此处显示实时预览</p>
        </div>
      </div>
    </div>
  </div>
</template>
