<script setup lang="ts">
import { computed } from 'vue'
import type { LlmCallTrace } from '@/api/types'
import {
  phaseLabel,
  traceCandidateLabel,
  traceOutputLabel,
  traceResultLabel,
  traceResultType,
} from './traceDisplay'

const props = defineProps<{
  modelValue: boolean
  trace: LlmCallTrace | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
})
</script>

<template>
  <el-drawer v-model="visible" title="调用追溯详情" size="560px">
    <div v-if="trace" class="space-y-4 text-sm">
      <dl class="space-y-2">
        <div class="flex justify-between border-b border-line pb-2">
          <dt class="text-ink-muted">阶段</dt>
          <dd class="text-ink">{{ phaseLabel[trace.phase] || trace.phase }}</dd>
        </div>
        <div class="flex justify-between border-b border-line pb-2">
          <dt class="text-ink-muted">模型 / 提供方</dt>
          <dd class="text-ink">{{ trace.model_name || trace.provider || '—' }}</dd>
        </div>
        <div class="flex justify-between border-b border-line pb-2">
          <dt class="text-ink-muted">接口地址</dt>
          <dd class="text-ink">{{ trace.base_url || '—' }}</dd>
        </div>
        <div class="flex justify-between border-b border-line pb-2">
          <dt class="text-ink-muted">关联 ID</dt>
          <dd class="font-mono text-xs text-ink">{{ trace.request_id || '—' }}</dd>
        </div>
        <div class="flex justify-between border-b border-line pb-2">
          <dt class="text-ink-muted">阶段输出 / 置信度</dt>
          <dd class="text-success">
            {{ traceOutputLabel(trace) }}（{{ (trace.confidence * 100).toFixed(0) }}%）
          </dd>
        </div>
        <div v-if="trace.phase !== 'web_search'" class="flex justify-between border-b border-line pb-2">
          <dt class="text-ink-muted">候选答案</dt>
          <dd class="text-success">{{ traceCandidateLabel(trace) }}</dd>
        </div>
        <div class="flex justify-between border-b border-line pb-2">
          <dt class="text-ink-muted">结果 / 耗时</dt>
          <dd>
            <el-tag size="small" :type="traceResultType(trace)" effect="plain">
              {{ traceResultLabel(trace) }}
            </el-tag>
            <span class="ml-2 text-ink">{{ (trace.elapsed_ms / 1000).toFixed(2) }}s</span>
          </dd>
        </div>
      </dl>

      <div v-if="trace.error">
        <div class="mb-1 text-ink-muted">错误信息</div>
        <p class="whitespace-pre-wrap rounded-lg bg-danger/10 p-3 text-danger">{{ trace.error }}</p>
      </div>

      <div>
        <div class="mb-1 text-ink-muted">输入提示词</div>
        <pre class="max-h-48 overflow-auto rounded-lg bg-[#0f172a] p-3 text-xs leading-relaxed text-slate-200">{{ trace.prompt || '—' }}</pre>
      </div>

      <div v-if="trace.evidence && trace.evidence.length">
        <div class="mb-1 text-ink-muted">联网检索证据（{{ trace.evidence.length }} 条）</div>
        <ul class="space-y-2">
          <li v-for="(ev, index) in trace.evidence" :key="index" class="rounded-lg bg-card-soft p-3">
            <div class="font-medium text-ink">[{{ index + 1 }}] {{ ev.title || '—' }}</div>
            <a v-if="ev.url" :href="ev.url" target="_blank" class="break-all text-xs text-primary">{{ ev.url }}</a>
            <p class="mt-1 text-xs text-ink-muted">{{ ev.snippet || '' }}</p>
          </li>
        </ul>
      </div>

      <div>
        <div class="mb-1 text-ink-muted">
          {{ trace.phase === 'web_search' ? '检索输出' : '模型输出' }}
        </div>
        <pre class="max-h-56 overflow-auto rounded-lg bg-[#0f172a] p-3 text-xs leading-relaxed text-slate-200">{{ trace.response_text || '—' }}</pre>
      </div>
    </div>
  </el-drawer>
</template>
