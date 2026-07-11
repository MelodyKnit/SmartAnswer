<script setup lang="ts">
import { computed } from 'vue'
import type { LlmCallTrace } from '@/api/types'
import { phaseLabel, traceOutputLabel, traceResultLabel, traceResultType } from './traceDisplay'

const props = defineProps<{
  loading: boolean
  traces: LlmCallTrace[]
  requestIdFilter: string
}>()

const emit = defineEmits<{
  detail: [trace: LlmCallTrace]
  clearFilter: []
}>()

// 按照流程发生的创建时间对 Trace 排序，确保流程线是由早到晚
const sortedTraces = computed(() => {
  return [...props.traces].sort((a, b) => (a.created_at || 0) - (b.created_at || 0))
})

// 为特定 Request 链路补充虚拟首尾节点 (输入节点与最终决定输出节点)
const flowSequence = computed(() => {
  if (!props.requestIdFilter || !sortedTraces.value.length) return []
  
  const nodes = []
  
  // 1. 本地输入节点 (Question Ingress)
  const first = sortedTraces.value[0]
  nodes.push({
    id: 'input',
    title: '输入上下文',
    phaseName: '问题载入',
    desc: first.question_title || '未知题目',
    status: 'success',
    type: 'input',
    raw: { prompt: `【题目】\n${first.question_title}` }
  })
  
  // 2. 变换中途真实的 Trace 节点
  for (const t of sortedTraces.value) {
    let type = 'info'
    if (!t.ok) {
      type = 'danger'
    } else if (t.phase === 'web_search') {
      type = (t.evidence?.length || 0) > 0 ? 'success' : 'warning'
    } else {
      type = 'primary'
    }
    
    nodes.push({
      id: t.trace_id,
      title: phaseLabel[t.phase] || t.phase,
      phaseName: t.model_name || t.provider || 'AI组件',
      desc: traceOutputLabel(t),
      status: type,
      type: 'trace',
      raw: t
    })
  }
  
  return nodes
})
</script>

<template>
  <div v-loading="loading" class="p-6">
    <!-- 未提供特定 request_id 过滤时的体验提示 -->
    <div v-if="!requestIdFilter" class="flex flex-col items-center justify-center py-12 text-center">
      <el-empty description="请先在顶部条件中输入或过滤「关联 ID」以呈现完整的 Agent 流程链路" />
    </div>
    
    <!-- 渲染有向依赖链路图 -->
    <div v-else class="relative">
      <div class="mb-6 flex items-center justify-between">
        <h4 class="text-sm font-semibold text-ink">
          关联 ID: <code class="rounded bg-canvas px-2 py-1 font-mono text-xs select-all">{{ requestIdFilter }}</code>
        </h4>
        <el-button size="small" :icon="'Close'" @click="emit('clearFilter')">返回全览</el-button>
      </div>

      <!-- 时间连线链路 -->
      <div class="flex flex-col gap-6 lg:flex-row lg:items-stretch lg:overflow-x-auto lg:pb-4">
        <div 
          v-for="(node, index) in flowSequence" 
          :key="node.id"
          class="flex flex-col items-center lg:flex-row lg:shrink-0"
        >
          <!-- 节点卡片 -->
          <div 
            class="w-full max-w-sm rounded-xl border border-line bg-card p-4 shadow-sm transition hover:border-primary-400 hover:shadow-md lg:w-72"
          >
            <div class="flex items-center justify-between border-b border-line pb-2 mb-3">
              <span class="text-xs font-semibold uppercase tracking-wider text-ink-muted">
                {{ node.phaseName }}
              </span>
              <el-tag size="small" :type="node.status as any" effect="light">
                {{ node.title }}
              </el-tag>
            </div>
            
            <div class="space-y-3">
              <p class="line-clamp-3 text-sm text-ink-soft font-medium leading-relaxed">
                {{ node.desc }}
              </p>
              
              <div class="flex justify-end pt-2">
                <el-button 
                  v-if="node.type === 'trace'"
                  size="small" 
                  link 
                  type="primary" 
                  @click="emit('detail', node.raw as any)"
                >
                  查看节点详情
                </el-button>
                <span v-else class="text-xs text-ink-muted select-none">Ingress 节点</span>
              </div>
            </div>
          </div>

          <!-- 单向引导箭头 (最后一个之外显示) -->
          <div 
            v-if="index < flowSequence.length - 1" 
            class="flex h-12 w-12 items-center justify-center text-ink-muted rotate-90 lg:h-auto lg:w-16 lg:rotate-0"
          >
            <!-- 右向箭头 SVG -->
            <svg class="h-6 w-6 stroke-current" fill="none" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 5l7 7m0 0l-7 7m7-7H3" />
            </svg>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
