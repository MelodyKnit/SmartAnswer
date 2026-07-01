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

const titleLength = computed(() => form.title.trim().length)
const optionCount = computed(() => optionList.value.length)
const localHitCost = computed(() => auth.billing?.local_hit ?? 0)

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
                输入题目信息
              </h3>
            </div>
            <el-tag type="info" effect="plain">每次 {{ localHitCost }} 积分</el-tag>
          </div>
          <p class="mt-2 text-xs leading-5 text-ink-soft">
            题干越完整、选项越规范，越容易优先命中本地题库；未命中时才进入 AI 与联网增强链路。
          </p>
        </div>

        <div class="space-y-5 p-5">
          <div class="grid gap-3 sm:grid-cols-3">
            <div class="rounded-xl border border-line bg-canvas/40 p-3">
              <div class="text-xs text-ink-muted">题干字符</div>
              <div class="mt-1 text-lg font-semibold text-ink">{{ titleLength }}</div>
            </div>
            <div class="rounded-xl border border-line bg-canvas/40 p-3">
              <div class="text-xs text-ink-muted">选项数量</div>
              <div class="mt-1 text-lg font-semibold text-ink">{{ optionCount }}</div>
            </div>
            <div class="rounded-xl border border-line bg-canvas/40 p-3">
              <div class="text-xs text-ink-muted">失败扣费</div>
              <div class="mt-1 text-lg font-semibold text-success">0</div>
            </div>
          </div>

          <el-form label-position="top" @submit.prevent>
            <el-form-item label="题型">
              <el-select v-model="form.type" class="w-full">
                <el-option v-for="t in TYPES" :key="t.value" :value="t.value" :label="t.label" />
              </el-select>
            </el-form-item>

            <el-form-item label="题目题干" required>
              <el-input
                v-model="form.title"
                type="textarea"
                :rows="5"
                maxlength="2000"
                show-word-limit
                placeholder="粘贴或输入完整题目题干，例如：国家资本主义的高级形式是【1】____。"
              />
            </el-form-item>

            <el-form-item label="选项（可选，每行一个）">
              <el-input
                v-model="form.optionsText"
                type="textarea"
                :rows="5"
                maxlength="3000"
                show-word-limit
                placeholder="例如：&#10;A. 初级形式&#10;B. 公私合营&#10;C. 统购统销&#10;D. 合作社"
              />
            </el-form-item>

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
              优先看推荐答案，再结合置信度、命中方式、解析和来源判断是否需要复核。低置信度结果不会被界面强行包装成高可信答案。
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
