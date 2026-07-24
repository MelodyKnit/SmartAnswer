<script setup lang="ts">
/** 生图调用追溯与任务统计，严格不展示提示词、图片字节或密钥。 */
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { imageGenerationApi } from '@/api/endpoints'
import { ApiException } from '@/api/http'
import type { ImageGenerationStats, ImageGenerationTrace } from '@/api/types'
import { formatDateTime } from '@/utils/format'

const loading = ref(false)
const stats = ref<ImageGenerationStats | null>(null)
const traces = ref<ImageGenerationTrace[]>([])

async function load() {
  loading.value = true
  try {
    const [statsResult, traceResult] = await Promise.all([
      imageGenerationApi.stats(),
      imageGenerationApi.traces({ limit: 100 }),
    ])
    stats.value = statsResult.stats
    traces.value = traceResult.traces
  } catch (error) {
    ElMessage.error(error instanceof ApiException ? error.message : '加载生图调用追溯失败')
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <section v-loading="loading" class="space-y-4">
    <div class="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-5">
      <div class="app-card p-4"><p class="text-xs text-ink-muted">全部任务</p><p class="mt-1 text-xl font-semibold text-ink">{{ stats?.total_jobs ?? 0 }}</p></div>
      <div class="app-card p-4"><p class="text-xs text-ink-muted">处理中</p><p class="mt-1 text-xl font-semibold text-warning">{{ (stats?.queued_jobs ?? 0) + (stats?.running_jobs ?? 0) }}</p></div>
      <div class="app-card p-4"><p class="text-xs text-ink-muted">成功</p><p class="mt-1 text-xl font-semibold text-success">{{ stats?.succeeded_jobs ?? 0 }}</p></div>
      <div class="app-card p-4"><p class="text-xs text-ink-muted">失败 / 拒绝</p><p class="mt-1 text-xl font-semibold text-danger">{{ (stats?.failed_jobs ?? 0) + (stats?.rejected_jobs ?? 0) }}</p></div>
      <div class="app-card p-4"><p class="text-xs text-ink-muted">平均耗时</p><p class="mt-1 text-xl font-semibold text-ink">{{ ((stats?.avg_elapsed_ms ?? 0) / 1000).toFixed(2) }}s</p></div>
    </div>

    <div class="app-card p-1">
      <div class="flex items-center justify-between px-4 pt-4"><h3 class="text-base font-semibold text-ink">生图调用追溯</h3><el-button size="small" @click="load">刷新</el-button></div>
      <el-table :data="traces" style="width: 100%">
        <el-table-column label="时间" width="170"><template #default="{ row }">{{ formatDateTime(row.created_at) }}</template></el-table-column>
        <el-table-column label="模型" min-width="150" prop="model_name" />
        <el-table-column label="阶段" width="110" prop="phase" />
        <el-table-column label="结果" width="90" align="center"><template #default="{ row }"><el-tag size="small" :type="row.ok ? 'success' : 'danger'" effect="plain">{{ row.ok ? '成功' : '失败' }}</el-tag></template></el-table-column>
        <el-table-column label="耗时" width="110" align="right"><template #default="{ row }">{{ (row.elapsed_ms / 1000).toFixed(2) }}s</template></el-table-column>
        <el-table-column label="错误" min-width="220" show-overflow-tooltip><template #default="{ row }">{{ row.error || '—' }}</template></el-table-column>
        <template #empty><el-empty description="暂无生图调用记录" /></template>
      </el-table>
    </div>
  </section>
</template>
