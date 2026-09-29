<script setup lang="ts">
import type { LlmCallStat } from '@/api/types'
import DataTable from '@/components/data-table/DataTable.vue'

defineProps<{
  loading: boolean
  stats: LlmCallStat[]
}>()
</script>

<template>
  <DataTable :data="stats" :loading="loading" empty-text="暂无调用统计">
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
  </DataTable>
</template>
