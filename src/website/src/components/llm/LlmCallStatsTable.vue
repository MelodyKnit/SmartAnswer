<script setup lang="ts">
import type { LlmCallStat } from '@/api/types'

defineProps<{
  loading: boolean
  stats: LlmCallStat[]
}>()
</script>

<template>
  <el-table v-loading="loading" :data="stats" style="width: 100%">
    <el-table-column label="模型" min-width="180">
      <template #default="{ row }">
        <span class="text-ink">{{ row.model_name || row.model_id || '（未关联模型）' }}</span>
      </template>
    </el-table-column>
    <el-table-column label="总调用次数" width="120" prop="total_calls" align="center" />
    <el-table-column label="成功" width="100" align="center">
      <template #default="{ row }">
        <span class="text-success">{{ row.ok_calls }}</span>
      </template>
    </el-table-column>
    <el-table-column label="失败" width="100" align="center">
      <template #default="{ row }">
        <span :class="row.error_calls > 0 ? 'text-danger' : 'text-ink-muted'">
          {{ row.error_calls }}
        </span>
      </template>
    </el-table-column>
    <el-table-column label="平均耗时" width="120" align="center">
      <template #default="{ row }">{{ (row.avg_elapsed_ms / 1000).toFixed(2) }}s</template>
    </el-table-column>
    <template #empty>
      <el-empty description="暂无调用统计" />
    </template>
  </el-table>
</template>
