<script setup lang="ts">
/** 站内搜题：用户输入题目，系统调用内部/网页检索引擎返回可能的答案。 */
import { computed, reactive, ref } from 'vue'
import { ApiException } from '@/api/http'
import { queryApi } from '@/api/endpoints'
import type { QueryResultPayload } from '@/api/types'
import { Search } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import PageHeader from '@/components/PageHeader.vue'
import { resolutionLabel } from '@/utils/format'

const auth = useAuthStore()

const form = reactive({ title: '', optionsText: '', type: 'single' })
const loading = ref(false)
const result = ref<QueryResultPayload | null>(null)
const errorMsg = ref('')

const TYPES = [
  { value: 'single', label: '单选题' },
  { value: 'multiple', label: '多选题' },
  { value: 'judgement', label: '判断题' },
  { value: 'completion', label: '填空题' },
  { value: 'unknown', label: '未知/自动' },
]

const optionList = computed(() =>
  form.optionsText
    .split('\n')
    .map((s) => s.trim())
    .filter(Boolean),
)

async function search() {
  if (!form.title.trim()) {
    ElMessage.warning('请输入题目题干')
    return
  }
  loading.value = true
  errorMsg.value = ''
  result.value = null
  try {
    const res = await queryApi.search({
      title: form.title.trim(),
      options: optionList.value,
      type: form.type,
    })
    result.value = res
  } catch (err) {
    errorMsg.value = err instanceof ApiException ? err.message : '搜题失败，请稍后再试'
  } finally {
    loading.value = false
  }
}

function reset() {
  form.title = ''
  form.optionsText = ''
  form.type = 'single'
  result.value = null
  errorMsg.value = ''
}

const confidencePercent = computed(() =>
  result.value ? Math.round(result.value.result.confidence * 100) : 0,
)

const localHitCost = computed(() => auth.billing?.local_hit ?? 0)
</script>

<template>
  <div class="space-y-4">
    <PageHeader title="在线搜题" :description="`输入题目即可检索答案。系统搜题每次消耗 ${localHitCost} 积分，搜索失败不扣分。`" />

    <!-- 搜题入口卡片 -->
    <div class="app-card overflow-hidden">
      <!-- Header -->
      <div class="border-b border-line bg-canvas/30 px-6 py-4">
        <h3 class="text-base font-semibold text-ink flex items-center gap-2">
          <el-icon class="text-brand-500"><Search /></el-icon>
          输入题目信息
        </h3>
        <p class="mt-1 text-xs text-ink-soft">每次搜题将消耗 {{ localHitCost }} 积分，搜索失败不会扣除积分。</p>
      </div>

      <div class="p-6">
        <!-- 输入 -->
        <el-form label-position="top">
          <el-form-item label="题型">
            <el-select v-model="form.type" class="w-full">
              <el-option v-for="t in TYPES" :key="t.value" :value="t.value" :label="t.label" />
            </el-select>
          </el-form-item>
          <el-form-item label="题目题干" required>
            <el-input
              v-model="form.title"
              type="textarea"
              :rows="3"
              placeholder="粘贴或输入题目题干"
            />
          </el-form-item>
          <el-form-item label="选项（可选，每行一个）">
            <el-input
              v-model="form.optionsText"
              type="textarea"
              :rows="4"
              placeholder="例如：&#10;A. 选项一&#10;B. 选项二"
            />
          </el-form-item>
          <div class="flex gap-3">
            <el-button type="primary" :loading="loading" class="flex-1" @click="search">
              开始搜题
            </el-button>
            <el-button @click="reset">清空</el-button>
          </div>
        </el-form>

        <!-- 结果 -->
        <div class="flex flex-col p-5">
          <h3 class="mb-3 text-base font-semibold text-ink">搜题结果</h3>

          <div v-if="loading" class="flex flex-1 items-center justify-center text-ink-muted">
            <el-icon class="mr-2 animate-spin"><Loading /></el-icon> 检索中…
          </div>

          <el-result
            v-else-if="errorMsg"
            icon="warning"
            title="未获取到答案"
            :sub-title="errorMsg"
          />

          <div v-else-if="result" class="flex-1 space-y-4">
            <div class="rounded-xl bg-success/10 p-4">
              <div class="text-sm text-ink-soft">推荐答案</div>
              <div class="mt-1 text-2xl font-bold text-success">
                {{ result.result.candidate_answer || result.result.answer_text || '—' }}
              </div>
              <div v-if="result.result.answer_text" class="mt-1 text-sm text-ink">
                {{ result.result.answer_text }}
              </div>
            </div>

            <div class="flex flex-wrap gap-4 text-sm">
              <div>
                <span class="text-ink-muted">命中方式：</span>
                <el-tag size="small" type="success" effect="light">
                  {{ resolutionLabel(result.result.resolution_mode) }}
                </el-tag>
              </div>
              <div class="flex items-center gap-2">
                <span class="text-ink-muted">置信度：</span>
                <el-progress
                  :percentage="confidencePercent"
                  :stroke-width="8"
                  style="width: 120px"
                />
              </div>
              <div v-if="result.result.review_required">
                <el-tag size="small" type="warning" effect="light">建议人工复核</el-tag>
              </div>
            </div>

            <div v-if="result.result.explanation">
              <div class="mb-1 text-sm text-ink-muted">解析</div>
              <p class="whitespace-pre-wrap rounded-lg bg-card-soft p-3 text-sm text-ink-soft">
                {{ result.result.explanation }}
              </p>
            </div>

            <div v-if="result.sources.length">
              <div class="mb-1 text-sm text-ink-muted">来源</div>
              <div class="flex flex-wrap gap-2">
                <el-tag
                  v-for="(s, i) in result.sources"
                  :key="i"
                  size="small"
                  effect="plain"
                >
                  {{ s.source_name }}（{{ (s.score * 100).toFixed(0) }}%）
                </el-tag>
              </div>
            </div>
          </div>

          <div v-else class="flex flex-1 items-center justify-center text-sm text-ink-muted">
            在左侧输入题目后开始搜题
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.animate-spin {
  animation: spin 1s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
