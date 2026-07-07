<script setup lang="ts">
import type { LlmCallTrace } from '@/api/types'
import { formatDateTime } from '@/utils/format'
import { phaseLabel, traceOutputLabel, traceResultLabel, traceResultType } from './traceDisplay'

defineProps<{
  loading: boolean
  traces: LlmCallTrace[]
}>()

const emit = defineEmits<{
  detail: [trace: LlmCallTrace]
  filterRequest: [requestId: string]
}>()
</script>

<template>
  <el-table v-loading="loading" :data="traces" style="width: 100%">
    <el-table-column label="时间" width="170">
      <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
    </el-table-column>
    <el-table-column label="阶段" width="100">
      <template #default="{ row }">
        <el-tag size="small" :type="row.phase === 'failover' ? 'danger' : 'info'" effect="light">
          {{ phaseLabel[row.phase] || row.phase }}
        </el-tag>
      </template>
    </el-table-column>
    <el-table-column label="模型" width="140" show-overflow-tooltip>
      <template #default="{ row }">{{ row.model_name || row.provider || '—' }}</template>
    </el-table-column>
    <el-table-column label="题目" min-width="200" show-overflow-tooltip>
      <template #default="{ row }">{{ row.question_title || '—' }}</template>
    </el-table-column>
    <el-table-column label="阶段输出" width="140" show-overflow-tooltip>
      <template #default="{ row }">
        <span :class="row.phase === 'web_search' ? 'text-ink-muted' : 'text-success'">
          {{ traceOutputLabel(row) }}
        </span>
      </template>
    </el-table-column>
    <el-table-column label="结果" width="80" align="center">
      <template #default="{ row }">
        <el-tag size="small" :type="traceResultType(row)" effect="plain">
          {{ traceResultLabel(row) }}
        </el-tag>
      </template>
    </el-table-column>
    <el-table-column label="耗时" width="90" align="center">
      <template #default="{ row }">{{ (row.elapsed_ms / 1000).toFixed(2) }}s</template>
    </el-table-column>
    <el-table-column label="操作" width="150" align="right">
      <template #default="{ row }">
        <el-button link type="primary" @click="emit('detail', row)">详情</el-button>
        <el-button v-if="row.request_id" link type="primary" @click="emit('filterRequest', row.request_id)">
          看链路
        </el-button>
      </template>
    </el-table-column>
    <template #empty>
      <el-empty description="暂无调用追溯" />
    </template>
  </el-table>
</template>
