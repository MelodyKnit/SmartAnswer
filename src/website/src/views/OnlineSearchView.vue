<script setup lang="ts">
/** 站内搜题：用户输入题目，系统调用内部检索与 AI 链路返回候选答案。 */
import { computed, reactive, ref } from 'vue'
import { DocumentChecked, Search } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { ApiException } from '@/api/http'
import { queryApi } from '@/api/endpoints'
import type { QueryResultPayload } from '@/api/types'
import PageHeader from '@/components/PageHeader.vue'
import SearchResultPanel from '@/components/online-search/SearchResultPanel.vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()

const form = reactive({ rawText: '', typeOverride: 'unknown' })
const loading = ref(false)
const result = ref<QueryResultPayload | null>(null)
const errorMsg = ref('')
const activeAdvancedSections = ref<string[]>([])

const QUESTION_TYPES = [
  { value: 'unknown', label: '自动识别' },
  { value: 'single', label: '单选题' },
  { value: 'multiple', label: '多选题' },
  { value: 'judgement', label: '判断题' },
  { value: 'completion', label: '填空题' },
]

const localHitCost = computed(() => auth.billing?.local_hit ?? 0)
const inputPlaceholder = [
  '直接粘贴完整题干；选择题的选项可一并粘贴。',
  '',
  '示例：下列哪些属于国家资本主义的形式？',
  'A. 初级形式',
  'B、 公私合营',
  'C） 统购统销',
  '(D) 合作社',
].join('\n')

async function search() {
  if (!form.rawText.trim()) {
    ElMessage.warning('请输入题目内容')
    return
  }
  loading.value = true
  errorMsg.value = ''
  result.value = null
  try {
    const res = await queryApi.search({
      raw_text: form.rawText.trim(),
      ...(form.typeOverride !== 'unknown' ? { type: form.typeOverride } : {}),
    })
    result.value = res
  } catch (err) {
    errorMsg.value = err instanceof ApiException ? err.message : '搜题失败，请稍后再试'
  } finally {
    loading.value = false
  }
}

function reset() {
  form.rawText = ''
  form.typeOverride = 'unknown'
  activeAdvancedSections.value = []
  result.value = null
  errorMsg.value = ''
}
</script>

<template>
  <div class="space-y-4">
    <PageHeader
      title="在线搜题"
      :description="`输入题目即可检索答案。系统搜题每次消耗 ${localHitCost} 积分，搜索失败不扣分。`"
    />

    <div class="grid items-start gap-4 xl:grid-cols-[minmax(360px,0.86fr)_minmax(480px,1.14fr)]">
      <section class="app-card overflow-hidden">
        <div class="border-b border-line bg-canvas/30 px-5 py-4">
          <div class="flex items-start justify-between gap-4">
            <div>
              <p class="text-xs font-semibold uppercase tracking-[0.18em] text-brand-500">
                Question Input
              </p>
              <h3 class="mt-1 flex items-center gap-2 text-lg font-semibold text-ink">
                <el-icon class="text-brand-500"><Search /></el-icon>
                输入题目
              </h3>
            </div>
            <el-tag type="info" effect="plain">每次 {{ localHitCost }} 积分</el-tag>
          </div>
          <p class="mt-2 text-xs leading-5 text-ink-soft">
            直接粘贴题干即可搜索；选择题可将选项一并粘贴，系统会优先检索本地题库，未命中时才进入 AI 与联网增强链路。
          </p>
        </div>

        <div class="space-y-5 p-5">
          <el-form label-position="top" @submit.prevent>
            <el-form-item label="题目内容" required>
              <el-input
                v-model="form.rawText"
                type="textarea"
                :rows="10"
                maxlength="5000"
                show-word-limit
                :placeholder="inputPlaceholder"
              />
              <p class="mt-2 text-xs leading-5 text-ink-muted">
                选项请按行保留 A.、B、或 (C) 等标签；无法可靠识别时，系统会完整保留原文进行检索。
              </p>
            </el-form-item>

            <el-collapse v-model="activeAdvancedSections" class="online-search-advanced">
              <el-collapse-item name="type-override" title="高级设置">
                <p class="mb-3 text-xs leading-5 text-ink-soft">
                  题干未明确标注题型时，可手动指定。未设置时不会根据选项数量猜测单选或多选。
                </p>
                <el-form-item label="题型覆盖" class="!mb-0">
                  <el-select v-model="form.typeOverride" class="w-full">
                    <el-option
                      v-for="type in QUESTION_TYPES"
                      :key="type.value"
                      :value="type.value"
                      :label="type.label"
                    />
                  </el-select>
                </el-form-item>
              </el-collapse-item>
            </el-collapse>

            <div class="flex flex-col gap-3 sm:flex-row">
              <el-button type="primary" :loading="loading" class="min-h-10 flex-1" @click="search">
                <el-icon class="mr-1"><Search /></el-icon>
                开始搜题
              </el-button>
              <el-button class="min-h-10 sm:w-28" @click="reset">清空</el-button>
            </div>
          </el-form>

          <div class="rounded-2xl border border-brand-500/20 bg-brand-500/5 p-4">
            <div class="mb-2 flex items-center gap-2 text-sm font-semibold text-ink">
              <el-icon class="text-brand-500"><DocumentChecked /></el-icon>
              结果判断提示
            </div>
            <p class="text-xs leading-6 text-ink-soft">
              优先查看推荐答案，再结合置信度、命中方式、解析和来源判断是否需要复核。低置信度结果不会被界面强行包装成高可信答案。
            </p>
          </div>
        </div>
      </section>

      <SearchResultPanel
        class="xl:sticky xl:top-4"
        :result="result"
        :loading="loading"
        :error-message="errorMsg"
        @retry="search"
        @clear="reset"
      />
    </div>
  </div>
</template>

<style scoped>
.online-search-advanced :deep(.el-collapse),
.online-search-advanced :deep(.el-collapse-item__wrap),
.online-search-advanced :deep(.el-collapse-item__header) {
  border-color: var(--c-line);
  background: transparent;
}

.online-search-advanced :deep(.el-collapse-item__header) {
  color: var(--c-ink-soft);
  font-size: 0.875rem;
  font-weight: 600;
}
</style>
