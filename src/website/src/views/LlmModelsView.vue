<script setup lang="ts">
/**
 * 大模型与计费配置管理
 * - 运行配置：AI 答题策略 / 联网搜索 / AI 学习缓存
 * - 模型配置：多模型主备链
 * - 调用统计与追溯
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { ApiException } from '@/api/http'
import { llmApi } from '@/api/endpoints'
import type {
  LlmCallStat,
  LlmCallTrace,
  LlmModel,
  PlaywrightSearchEngine,
  WebSearchConfig,
  WebSearchProviderTemplate,
} from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import { ElMessage, ElMessageBox } from 'element-plus'
import PageHeader from '@/components/PageHeader.vue'
import LlmCallStatsTable from '@/components/llm/LlmCallStatsTable.vue'
import LlmTraceDetailDrawer from '@/components/llm/LlmTraceDetailDrawer.vue'
import LlmTraceTable from '@/components/llm/LlmTraceTable.vue'
import LlmTraceFlow from '@/components/llm/LlmTraceFlow.vue'
import ImageGenerationModelsPanel from '@/components/llm/ImageGenerationModelsPanel.vue'
import ImageGenerationTracePanel from '@/components/llm/ImageGenerationTracePanel.vue'
import { DEFAULT_PAGE_SIZE, SYSTEM_DEFAULTS } from '@/config/constants'

// === 1. 概览状态 ===
const auth = useAuthStore()
const canManageLlm = computed(() => auth.hasPermission('llm:write'))
const activeTab = ref<
  'runtime' | 'websearch' | 'models' | 'image-models' | 'stats' | 'traces' | 'image-traces'
>('runtime')

/* ---------------- 运行配置 ---------------- */
const runtimeLoading = ref(false)
const runtimeSaving = ref(false)
const runtimeForm = reactive({
  llm_fallback: 'true',
  llm_explain: 'false',
  allow_known_rules: 'true',
  no_local_bank_mode: 'false',
  search_first: 'false',
  self_consistency_repeats: 1,
  web_search_provider: 'duckduckgo',
  search_proxy: '',
  llm_proxy: '',
  google_search_api_key: '',
  google_search_cx: '',
  baidu_search_api_key: '',
  llm_cache_enabled: 'true',
  llm_cache_min_confidence: SYSTEM_DEFAULTS.LLM_CACHE_MIN_CONFIDENCE.toString(),
  llm_cache_min_confirmations: SYSTEM_DEFAULTS.LLM_CACHE_MIN_CONFIRMATIONS.toString(),
  web_search_configs: [] as WebSearchConfig[],
})
const secretConfigured = reactive({
  google_search_api_key: false,
  baidu_search_api_key: false,
})

async function loadRuntimeConfig() {
  runtimeLoading.value = true
  try {
    const res = await llmApi.runtimeConfig()
    runtimeForm.llm_fallback = (res.config.llm_fallback as string) || 'true'
    runtimeForm.llm_explain = (res.config.llm_explain as string) || 'false'
    runtimeForm.allow_known_rules = (res.config.allow_known_rules as string) || 'true'
    runtimeForm.no_local_bank_mode = (res.config.no_local_bank_mode as string) || 'false'
    runtimeForm.search_first = (res.config.search_first as string) || 'false'
    runtimeForm.self_consistency_repeats = Number(
      (res.config.self_consistency_repeats as string) || '1',
    )
    runtimeForm.web_search_provider = (res.config.web_search_provider as string) || 'duckduckgo'
    runtimeForm.search_proxy = (res.config.search_proxy as string) || ''
    runtimeForm.llm_proxy = (res.config.llm_proxy as string) || ''
    runtimeForm.google_search_cx = (res.config.google_search_cx as string) || ''
    runtimeForm.llm_cache_enabled = (res.config.llm_cache_enabled as string) || 'true'
    runtimeForm.llm_cache_min_confidence =
      (res.config.llm_cache_min_confidence as string) || '0.95'
    runtimeForm.llm_cache_min_confirmations =
      (res.config.llm_cache_min_confirmations as string) || '2'

    const configsStr = (res.config.web_search_configs as string) || '[]'
    try {
      const parsedConfigs = JSON.parse(configsStr)
      runtimeForm.web_search_configs = Array.isArray(parsedConfigs) ? parsedConfigs : []
    } catch {
      runtimeForm.web_search_configs = []
    }

    secretConfigured.google_search_api_key = !!res.config.google_search_api_key_configured
    secretConfigured.baidu_search_api_key = !!res.config.baidu_search_api_key_configured
    runtimeForm.google_search_api_key = ''
    runtimeForm.baidu_search_api_key = ''
  } finally {
    runtimeLoading.value = false
  }
}

async function saveRuntimeConfig() {
  runtimeSaving.value = true
  try {
    const body: Record<string, string> = {
      llm_fallback: runtimeForm.llm_fallback,
      llm_explain: runtimeForm.llm_explain,
      allow_known_rules: runtimeForm.allow_known_rules,
      no_local_bank_mode: runtimeForm.no_local_bank_mode,
      search_first: runtimeForm.search_first,
      self_consistency_repeats: String(runtimeForm.self_consistency_repeats),
      web_search_provider: runtimeForm.web_search_provider,
      search_proxy: runtimeForm.search_proxy,
      llm_proxy: runtimeForm.llm_proxy,
      google_search_cx: runtimeForm.google_search_cx,
      llm_cache_enabled: runtimeForm.llm_cache_enabled,
      llm_cache_min_confidence: runtimeForm.llm_cache_min_confidence,
      llm_cache_min_confirmations: runtimeForm.llm_cache_min_confirmations,
      web_search_configs: JSON.stringify(runtimeForm.web_search_configs),
    }
    if (runtimeForm.google_search_api_key.trim()) {
      body.google_search_api_key = runtimeForm.google_search_api_key.trim()
    }
    if (runtimeForm.baidu_search_api_key.trim()) {
      body.baidu_search_api_key = runtimeForm.baidu_search_api_key.trim()
    }
    await llmApi.updateRuntimeConfig(body)
    ElMessage.success('运行配置已保存')
    await loadRuntimeConfig()
  } catch (err) {
    ElMessage.error(err instanceof ApiException ? err.message : '保存失败')
  } finally {
    runtimeSaving.value = false
  }
}

/* ---------------- 联网搜索配置 ---------------- */
const searchConfigVisible = ref(false)
const searchEditingIndex = ref<number | null>(null)

type SearchConfigForm = {
  id: string
  name: string
  provider: WebSearchProviderTemplate
  search_engine: PlaywrightSearchEngine
  api_key: string
  cx: string
  proxy_url: string
  status: WebSearchConfig['status']
  api_key_configured: boolean
}

const searchForm = reactive<SearchConfigForm>({
  id: '',
  name: '',
  provider: 'duckduckgo',
  search_engine: 'bing',
  api_key: '',
  cx: '',
  proxy_url: '',
  status: 'active',
  api_key_configured: false,
})

const providerLabels: Record<WebSearchProviderTemplate, string> = {
  duckduckgo: 'DuckDuckGo / 必应免密',
  google: 'Google Custom Search',
  baidu: '百度千帆 AI 搜索',
  playwright: 'Playwright 浏览器增强',
}

const playwrightSearchEngineOptions: {
  value: PlaywrightSearchEngine
  label: string
  description: string
}[] = [
  { value: 'bing', label: '必应', description: '默认选项，国内通常可直接访问。' },
  { value: 'baidu', label: '百度', description: '国内访问稳定，适合中文题目检索。' },
  { value: 'google', label: 'Google', description: '结果质量较好，通常需要独立代理。' },
  { value: 'duckduckgo', label: 'DuckDuckGo', description: '免 Key 搜索，通常需要独立代理。' },
]

const playwrightSearchEngineLabels: Record<PlaywrightSearchEngine, string> = {
  bing: '必应',
  baidu: '百度',
  google: 'Google',
  duckduckgo: 'DuckDuckGo',
}

const builtinDefaultSearchConfig: WebSearchConfig = {
  id: 'builtin_duckduckgo',
  name: '内置 DuckDuckGo 免密搜索',
  provider: 'duckduckgo',
  search_engine: '',
  proxy_url: '',
  status: 'active',
  api_key_configured: false,
  builtin: true,
}

const visibleSearchConfigs = computed(() =>
  runtimeForm.web_search_configs.length > 0
    ? runtimeForm.web_search_configs
    : [builtinDefaultSearchConfig],
)

function normalizePlaywrightSearchEngine(value: string | undefined): PlaywrightSearchEngine {
  if (value === 'baidu' || value === 'google' || value === 'duckduckgo') {
    return value
  }
  return 'bing'
}

function playwrightProviderName(engine: PlaywrightSearchEngine) {
  return `${providerLabels.playwright} - ${playwrightSearchEngineLabels[engine]}`
}

function isAutoSearchName(name: string) {
  const current = name.trim()
  if (!current || Object.values(providerLabels).includes(current)) {
    return true
  }
  return playwrightSearchEngineOptions.some((item) => current === playwrightProviderName(item.value))
}

function handleProviderChange(val: WebSearchProviderTemplate) {
  const shouldSyncName = isAutoSearchName(searchForm.name)
  if (val === 'playwright') {
    searchForm.search_engine = normalizePlaywrightSearchEngine(searchForm.search_engine)
    if (shouldSyncName) {
      searchForm.name = playwrightProviderName(searchForm.search_engine)
    }
  } else {
    searchForm.search_engine = 'bing'
    if (shouldSyncName) {
      searchForm.name = providerLabels[val]
    }
  }
}

function handlePlaywrightSearchEngineChange(value: PlaywrightSearchEngine) {
  const shouldSyncName = isAutoSearchName(searchForm.name)
  searchForm.search_engine = normalizePlaywrightSearchEngine(value)
  if (shouldSyncName) {
    searchForm.name = playwrightProviderName(searchForm.search_engine)
  }
}

function playwrightSearchEngineLabel(row: WebSearchConfig) {
  if (row.provider !== 'playwright') {
    return '—'
  }
  const engine = normalizePlaywrightSearchEngine(row.search_engine || 'bing')
  return playwrightSearchEngineLabels[engine]
}

function providerTemplateLabel(row: { provider?: string }) {
  const provider = row.provider || 'duckduckgo'
  if (provider === 'duckduckgo' || provider === 'google' || provider === 'baidu' || provider === 'playwright') {
    return providerLabels[provider]
  }
  return provider
}

function openCreateSearch() {
  searchEditingIndex.value = null
  searchForm.id = 'search_' + Math.random().toString(36).substring(2, 10)
  searchForm.name = providerLabels['duckduckgo']
  searchForm.provider = 'duckduckgo'
  searchForm.search_engine = 'bing'
  searchForm.api_key = ''
  searchForm.cx = ''
  searchForm.proxy_url = ''
  searchForm.status = 'active'
  searchForm.api_key_configured = false
  searchConfigVisible.value = true
}

function openEditSearch(index: number) {
  searchEditingIndex.value = index
  const item = runtimeForm.web_search_configs[index]
  searchForm.id = item.id
  searchForm.name = item.name
  searchForm.provider = item.provider
  searchForm.search_engine = normalizePlaywrightSearchEngine(item.search_engine || 'bing')
  searchForm.api_key = ''
  searchForm.cx = item.cx || ''
  searchForm.proxy_url = item.proxy_url || ''
  searchForm.status = item.status || 'active'
  searchForm.api_key_configured = !!item.api_key_configured
  searchConfigVisible.value = true
}

function submitSearchConfig() {
  if (!searchForm.name.trim()) {
    ElMessage.warning('请填写配置名称')
    return
  }
  const item: WebSearchConfig = {
    id: searchForm.id,
    name: searchForm.name.trim(),
    provider: searchForm.provider,
    search_engine:
      searchForm.provider === 'playwright'
        ? normalizePlaywrightSearchEngine(searchForm.search_engine)
        : '',
    api_key: searchForm.api_key.trim(),
    cx: searchForm.cx.trim(),
    proxy_url: searchForm.proxy_url.trim(),
    status: searchForm.status,
    api_key_configured: searchForm.api_key_configured || !!searchForm.api_key.trim(),
  }

  if (searchEditingIndex.value === null) {
    runtimeForm.web_search_configs.push(item)
  } else {
    if (!item.api_key && searchForm.api_key_configured) {
      item.api_key_configured = true
    }
    runtimeForm.web_search_configs[searchEditingIndex.value] = item
  }
  searchConfigVisible.value = false
}

function removeSearchConfig(index: number) {
  runtimeForm.web_search_configs.splice(index, 1)
}

function moveSearchConfig(index: number, direction: 'up' | 'down') {
  const targetIndex = direction === 'up' ? index - 1 : index + 1
  if (targetIndex < 0 || targetIndex >= runtimeForm.web_search_configs.length) return
  const temp = runtimeForm.web_search_configs[index]
  runtimeForm.web_search_configs[index] = runtimeForm.web_search_configs[targetIndex]
  runtimeForm.web_search_configs[targetIndex] = temp
}

/* ---------------- 模型配置 ---------------- */
const modelsLoading = ref(false)
const models = ref<LlmModel[]>([])
const testingModelId = ref<string | null>(null)

async function loadModels() {
  modelsLoading.value = true
  try {
    models.value = (await llmApi.models()).models
  } finally {
    modelsLoading.value = false
  }
}

async function handleTestModel(row: LlmModel) {
  testingModelId.value = row.model_id
  ElMessage.info(`正在诊断模型「${row.name}」连通性，请稍候...`)
  try {
    const res = await llmApi.testModel(row.model_id)
    if (res.ok) {
      ElMessageBox.alert(
        `<div class="space-y-2">
          <div class="text-success font-bold flex items-center gap-1">✓ 连通性测试通过</div>
          <div class="text-xs text-ink-soft">本次调用通过结构化自检模型推理通道。</div>
          <hr class="border-line/45 my-2" />
          <div class="grid grid-cols-3 gap-y-1.5 text-xs">
            <span class="text-ink-muted">测试耗时:</span>
            <span class="col-span-2 font-medium">${res.elapsed_ms.toFixed(0)} ms</span>
            <span class="text-ink-muted">推荐参考:</span>
            <span class="col-span-2 font-bold text-success">${res.candidate_answer || '—'}</span>
            <span class="text-ink-muted">匹配答案:</span>
            <span class="col-span-2 text-ink">${res.answer_text || '—'}</span>
            <span class="text-ink-muted">置信得分:</span>
            <span class="col-span-2 font-medium">${(res.confidence ?? 0).toFixed(2)}</span>
          </div>
          <hr class="border-line/45 my-2" />
          <div class="text-xs text-ink-muted">推理证据与说明:</div>
          <div class="bg-canvas p-2.5 rounded text-[11px] max-h-32 overflow-y-auto whitespace-pre-wrap leading-relaxed mt-1 text-ink-soft border border-line">
            ${res.explanation || '模型未返回解析描述。'}
          </div>
         </div>`,
        `模型「${row.name}」测试报告`,
        { 
          confirmButtonText: '关闭详情',
          dangerouslyUseHTMLString: true,
          customClass: 'max-w-md'
        }
      )
    } else {
      ElMessageBox.alert(
        `<div class="space-y-2">
          <div class="text-rose-600 font-bold flex items-center gap-1">✗ 连通性测试失败</div>
          <hr class="border-line/45 my-2" />
          <div class="grid grid-cols-3 gap-1 text-xs">
            <span class="text-ink-muted">测试耗时:</span>
            <span class="col-span-2 font-medium">${res.elapsed_ms.toFixed(0)} ms</span>
          </div>
          <hr class="border-line/45 my-2" />
          <div class="text-xs text-rose-700 font-medium">错误信息追踪:</div>
          <div class="bg-rose-50/50 dark:bg-rose-950/20 text-rose-700 border border-rose-100 p-2.5 rounded text-[11px] max-h-40 overflow-y-auto whitespace-pre-wrap leading-relaxed font-mono mt-1">
            ${res.error || '未获知具体底层错误原因，请检查端口监听。'}
          </div>
         </div>`,
        `模型「${row.name}」诊断报告`,
        { 
          confirmButtonText: '我知道了',
          dangerouslyUseHTMLString: true,
          customClass: 'max-w-md'
        }
      )
    }
  } catch (err) {
    ElMessage.error(err instanceof ApiException ? err.message : '与后端服务测试联调通信异常')
  } finally {
    testingModelId.value = null
  }
}

const roleLabel: Record<string, string> = {
  primary: '主用',
  backup: '备用',
  disabled: '停用',
}
const roleTagType: Record<string, string> = {
  primary: 'success',
  backup: 'warning',
  disabled: 'info',
}

const editVisible = ref(false)
const editing = ref(false)
const editingId = ref<string | null>(null)
const form = reactive({
  name: '',
  base_url: '',
  model: '',
  api_key: '',
  role: 'backup',
  priority: 100,
  stream: true,
  max_completion_tokens: 700,
  timeout_seconds: 30,
  status: 'active',
})

function resetForm() {
  form.name = ''
  form.base_url = ''
  form.model = ''
  form.api_key = ''
  form.role = 'backup'
  form.priority = 100
  form.stream = true
  form.max_completion_tokens = 700
  form.timeout_seconds = 30
  form.status = 'active'
}

function openCreate() {
  editingId.value = null
  resetForm()
  editVisible.value = true
}

function openEdit(row: LlmModel) {
  editingId.value = row.model_id
  form.name = row.name
  form.base_url = row.base_url
  form.model = row.model
  form.api_key = ''
  form.role = row.role
  form.priority = row.priority
  form.stream = row.stream
  form.max_completion_tokens = row.max_completion_tokens
  form.timeout_seconds = row.timeout_seconds
  form.status = row.status
  editVisible.value = true
}

async function submitModel() {
  if (!form.name.trim()) {
    ElMessage.warning('请填写模型名称')
    return
  }
  if (!form.base_url.trim() || !form.model.trim()) {
    ElMessage.warning('请填写接口地址与模型标识')
    return
  }
  editing.value = true
  try {
    if (editingId.value) {
      const body: Record<string, unknown> = {
        name: form.name,
        base_url: form.base_url,
        model: form.model,
        role: form.role,
        priority: form.priority,
        stream: form.stream,
        max_completion_tokens: form.max_completion_tokens,
        timeout_seconds: form.timeout_seconds,
        status: form.status,
      }
      if (form.api_key.trim()) body.api_key = form.api_key.trim()
      await llmApi.updateModel(editingId.value, body)
      ElMessage.success('模型配置已更新')
    } else {
      await llmApi.createModel({
        name: form.name,
        base_url: form.base_url,
        model: form.model,
        api_key: form.api_key.trim(),
        role: form.role,
        priority: form.priority,
        stream: form.stream,
        max_completion_tokens: form.max_completion_tokens,
        timeout_seconds: form.timeout_seconds,
        status: form.status,
      })
      ElMessage.success('模型已新增')
    }
    editVisible.value = false
    await loadModels()
  } catch (err) {
    ElMessage.error(err instanceof ApiException ? err.message : '保存失败')
  } finally {
    editing.value = false
  }
}

async function removeModel(row: LlmModel) {
  try {
    await ElMessageBox.confirm(`确认删除模型「${row.name}」？`, '删除大模型配置', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    await llmApi.deleteModel(row.model_id)
    ElMessage.success('模型已删除')
    await loadModels()
  } catch (err) {
    ElMessage.error(err instanceof ApiException ? err.message : '删除失败')
  }
}

/* ---------------- 调用统计 ---------------- */
const statsLoading = ref(false)
const stats = ref<LlmCallStat[]>([])

async function loadStats() {
  statsLoading.value = true
  try {
    stats.value = (await llmApi.stats()).stats
  } finally {
    statsLoading.value = false
  }
}

/* ---------------- 调用追溯 ---------------- */
const tracesLoading = ref(false)
const traces = ref<LlmCallTrace[]>([])
const traceViewMode = ref<'table' | 'flow'>('table')
const traceFilters = reactive({
  request_id: '',
  model_id: '',
  phase: '',
  limit: DEFAULT_PAGE_SIZE.CALL_TRACES,
})
const tracePage = ref(1)
const traceTotal = ref(0)
function resetTraceFilters() {
  traceFilters.request_id = ''
  traceFilters.model_id = ''
  traceFilters.phase = ''
  traceFilters.limit = DEFAULT_PAGE_SIZE.CALL_TRACES
  tracePage.value = 1
  loadTraces()
}

async function loadTraces() {
  tracesLoading.value = true
  try {
    const res = await llmApi.traces({
      request_id: traceFilters.request_id.trim() || undefined,
      model_id: traceFilters.model_id || undefined,
      phase: traceFilters.phase || undefined,
      limit: traceFilters.limit,
      page: tracePage.value,
    })
    traces.value = res.traces
    traceTotal.value = res.total
  } finally {
    tracesLoading.value = false
  }
}

function searchTraces() {
  tracePage.value = 1
  loadTraces()
}

function onTracePageChange(next: number) {
  tracePage.value = next
  loadTraces()
}

function filterByRequest(requestId: string) {
  traceFilters.request_id = requestId
  traceViewMode.value = 'flow'
  searchTraces()
}

const traceDetailVisible = ref(false)
const traceDetail = ref<LlmCallTrace | null>(null)
function openTraceDetail(row: LlmCallTrace) {
  traceDetail.value = row
  traceDetailVisible.value = true
}

const modelOptions = computed(() =>
  models.value.map((m) => ({ value: m.model_id, label: m.name })),
)

function handleTab(tab: string) {
  if (tab === 'stats' && !stats.value.length) loadStats()
  if (tab === 'traces' && !traces.value.length) loadTraces()
}

onMounted(async () => {
  await Promise.all([loadRuntimeConfig(), loadModels()])
})
</script>

<template>
  <div>
    <PageHeader title="大模型配置" description="统一维护 AI 答题运行配置、模型链和调用追溯。">
      <template #actions>
        <el-button
          v-if="canManageLlm && (activeTab === 'runtime' || activeTab === 'websearch')"
          type="primary"
          :loading="runtimeSaving"
          @click="saveRuntimeConfig"
        >
          保存运行配置
        </el-button>
        <el-button
          v-if="canManageLlm && activeTab === 'models'"
          type="primary"
          :icon="'Plus'"
          @click="openCreate"
        >
          新增模型
        </el-button>
      </template>
    </PageHeader>

    <el-tabs v-model="activeTab" @tab-change="handleTab">
      <el-tab-pane label="答题配置" name="runtime">
        <div class="space-y-4" v-loading="runtimeLoading">
          <div class="app-card p-6">
            <h3 class="mb-4 text-base font-semibold text-ink">答题策略</h3>
            <el-form label-position="top" class="grid grid-cols-1 gap-x-6 md:grid-cols-2 xl:grid-cols-4">
              <el-form-item label="启用 LLM 兜底">
                <el-switch
                  v-model="runtimeForm.llm_fallback"
                  active-value="true"
                  inactive-value="false"
                  :disabled="!canManageLlm"
                />
              </el-form-item>
              <el-form-item label="为本地命中生成 AI 解析">
                <el-switch
                  v-model="runtimeForm.llm_explain"
                  active-value="true"
                  inactive-value="false"
                  :disabled="!canManageLlm"
                />
              </el-form-item>
              <el-form-item label="启用本地规则">
                <el-switch
                  v-model="runtimeForm.allow_known_rules"
                  active-value="true"
                  inactive-value="false"
                  :disabled="!canManageLlm"
                />
              </el-form-item>
              <el-form-item label="无本地题库模式">
                <el-switch
                  v-model="runtimeForm.no_local_bank_mode"
                  active-value="true"
                  inactive-value="false"
                  :disabled="!canManageLlm"
                />
              </el-form-item>
              <el-form-item label="优先联网搜索">
                <el-switch
                  v-model="runtimeForm.search_first"
                  active-value="true"
                  inactive-value="false"
                  :disabled="!canManageLlm"
                />
              </el-form-item>
              <el-form-item label="自一致性重复次数">
                <el-input-number
                  v-model="runtimeForm.self_consistency_repeats"
                  :min="1"
                  :max="10"
                  class="w-full"
                  :disabled="!canManageLlm"
                />
              </el-form-item>
              <el-form-item label="全局模型代理">
                <el-input
                  v-model="runtimeForm.llm_proxy"
                  placeholder="http://127.0.0.1:7890"
                  :disabled="!canManageLlm"
                />
              </el-form-item>
            </el-form>
          </div>

          <div class="app-card p-6">
            <h3 class="mb-4 text-base font-semibold text-ink">AI 学习缓存</h3>
            <el-form label-position="top" class="grid grid-cols-1 gap-x-6 md:grid-cols-3">
              <el-form-item label="启用 AI 缓存">
                <el-switch
                  v-model="runtimeForm.llm_cache_enabled"
                  active-value="true"
                  inactive-value="false"
                  :disabled="!canManageLlm"
                />
              </el-form-item>
              <el-form-item label="最低置信度">
                <el-input v-model="runtimeForm.llm_cache_min_confidence" placeholder="0.95" :disabled="!canManageLlm" />
              </el-form-item>
              <el-form-item label="最少确认次数">
                <el-input v-model="runtimeForm.llm_cache_min_confirmations" placeholder="2" :disabled="!canManageLlm" />
              </el-form-item>
            </el-form>
          </div>
        </div>
      </el-tab-pane>

      <!-- 联网搜索配置 Tab -->
      <el-tab-pane label="联网搜索" name="websearch">
        <div class="space-y-4" v-loading="runtimeLoading">
          <div class="app-card p-6">
            <div class="flex items-center justify-between mb-4">
              <div>
                <h3 class="text-base font-semibold text-ink">搜索引擎列表</h3>
                <p class="text-xs text-ink-muted mt-1">
                  可以配置多个搜索引擎进行协同搜索，答题时会并行请求所有启用的引擎。
                </p>
              </div>
              <el-button
                v-if="canManageLlm"
                type="primary"
                size="small"
                icon="Plus"
                @click="openCreateSearch"
              >
                添加搜索引擎
              </el-button>
            </div>

            <el-table :data="visibleSearchConfigs" style="width: 100%">
              <el-table-column label="显示名称" min-width="120">
                <template #default="{ row }">
                  <span class="font-medium text-ink">{{ row.name }}</span>
                  <el-tag v-if="row.builtin" size="small" type="success" effect="plain" class="ml-2">
                    内置默认
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="供应商模板" width="180" align="center">
                <template #default="{ row }">
                  <el-tag size="small" type="info">
                    {{ providerTemplateLabel(row) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="页面搜索" width="110" align="center">
                <template #default="{ row }">
                  <span class="text-ink-muted text-xs">
                    {{ playwrightSearchEngineLabel(row) }}
                  </span>
                </template>
              </el-table-column>
              <el-table-column label="独立代理" width="160" show-overflow-tooltip align="center">
                <template #default="{ row }">
                  <span class="text-ink-muted text-xs">{{ row.proxy_url || '—' }}</span>
                </template>
              </el-table-column>
              <el-table-column label="密钥状态" width="100" align="center">
                <template #default="{ row }">
                  <el-tag size="small" :type="row.api_key_configured ? 'success' : 'info'" effect="plain">
                    {{ row.api_key_configured ? '已配置' : '无' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="状态" width="90" align="center">
                <template #default="{ row }">
                  <el-tag size="small" :type="row.status === 'active' ? 'success' : 'info'" effect="plain">
                    {{ row.status === 'active' ? '启用' : '停用' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column v-if="canManageLlm" label="排序/操作" width="220" align="right">
                <template #default="{ row, $index }">
                  <span v-if="row.builtin" class="text-xs text-ink-muted">
                    默认启用，无需配置
                  </span>
                  <template v-else>
                  <el-button
                    link
                    type="primary"
                    :disabled="$index === 0"
                    @click="moveSearchConfig($index, 'up')"
                  >
                    上移
                  </el-button>
                  <el-button
                    link
                    type="primary"
                    :disabled="$index === runtimeForm.web_search_configs.length - 1"
                    @click="moveSearchConfig($index, 'down')"
                  >
                    下移
                  </el-button>
                  <el-button link type="primary" @click="openEditSearch($index)">编辑</el-button>
                  <el-button link type="danger" @click="removeSearchConfig($index)">删除</el-button>
                  </template>
                </template>
              </el-table-column>
            </el-table>
          </div>

          <!-- 全局搜索设置 -->
          <div class="app-card p-6">
            <h3 class="mb-4 text-base font-semibold text-ink">全局搜索代理</h3>
            <el-form label-position="top" class="grid grid-cols-1 gap-x-6 md:grid-cols-2">
              <el-form-item label="全局搜索代理 (search_proxy)">
                <el-input
                  v-model="runtimeForm.search_proxy"
                  placeholder="http://127.0.0.1:7890 (若引擎未配置独立代理，则会以此代理发起网络请求)"
                  :disabled="!canManageLlm"
                />
              </el-form-item>
            </el-form>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="模型配置" name="models">
        <div class="app-card p-1">
          <el-table v-loading="modelsLoading" :data="models" style="width: 100%">
            <el-table-column label="名称" min-width="160" show-overflow-tooltip>
              <template #default="{ row }">
                <span class="font-medium text-ink">{{ row.name }}</span>
              </template>
            </el-table-column>
            <el-table-column label="模型标识" width="160" prop="model" show-overflow-tooltip align="center" />
            <el-table-column label="接口地址" min-width="200" prop="base_url" show-overflow-tooltip align="center" />
            <el-table-column label="角色" width="90" align="center">
              <template #default="{ row }">
                <el-tag size="small" :type="roleTagType[row.role]" effect="light">
                  {{ roleLabel[row.role] || row.role }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="优先级" width="80" prop="priority" align="center" />
            <el-table-column label="密钥" width="90" align="center">
              <template #default="{ row }">
                <el-tag size="small" :type="row.api_key_configured ? 'success' : 'info'" effect="plain">
                  {{ row.api_key_configured ? '已配置' : '无' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="80" align="center">
              <template #default="{ row }">
                <el-tag size="small" :type="row.status === 'active' ? 'success' : 'info'" effect="plain">
                  {{ row.status === 'active' ? '启用' : '停用' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column v-if="canManageLlm" label="操作" width="180" align="right">
              <template #default="{ row }">
                <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
                <el-button link type="warning" :loading="testingModelId === row.model_id" @click="handleTestModel(row)">测试</el-button>
                <el-button link type="danger" @click="removeModel(row)">删除</el-button>
              </template>
            </el-table-column>
            <template #empty>
              <el-empty description="暂无模型配置" />
            </template>
          </el-table>
        </div>
      </el-tab-pane>

      <el-tab-pane label="生图模型" name="image-models">
        <ImageGenerationModelsPanel :can-manage="canManageLlm" />
      </el-tab-pane>

      <el-tab-pane label="调用统计" name="stats">
        <div class="mb-3 flex justify-end">
          <el-button :icon="'Refresh'" @click="loadStats">刷新统计</el-button>
        </div>
        <div class="app-card p-1">
          <LlmCallStatsTable :loading="statsLoading" :stats="stats" />
        </div>
      </el-tab-pane>

      <el-tab-pane label="调用追溯" name="traces">
        <div class="app-card mb-4 flex flex-wrap items-center gap-3 p-4">
          <el-input
            v-model="traceFilters.request_id"
            placeholder="按关联 ID 筛选"
            clearable
            class="!w-72"
            @keyup.enter="searchTraces"
          />
          <el-select v-model="traceFilters.model_id" placeholder="全部模型" clearable class="!w-40">
            <el-option v-for="opt in modelOptions" :key="opt.value" :value="opt.value" :label="opt.label" />
          </el-select>
          <el-select v-model="traceFilters.phase" placeholder="全部阶段" clearable class="!w-36">
            <el-option value="answer" label="模型作答" />
            <el-option value="answer_with_evidence" label="证据作答" />
            <el-option value="verify_answer" label="答案自检" />
            <el-option value="verify_answer_with_evidence" label="证据复核" />
            <el-option value="model_request" label="模型请求" />
            <el-option value="model_decode" label="响应解码" />
            <el-option value="model_parse" label="答案解析" />
            <el-option value="web_search" label="联网检索" />
            <el-option value="failover" label="主备降级" />
          </el-select>
          <el-button type="primary" :icon="'Search'" @click="searchTraces">查询</el-button>
          <el-button v-if="traceFilters.request_id" @click="() => { traceFilters.request_id = ''; searchTraces() }">
            清除关联
          </el-button>
          
          <div class="ml-auto">
            <el-radio-group v-model="traceViewMode" size="small">
              <el-radio-button value="table">表格视图</el-radio-button>
              <el-radio-button value="flow">链路拓扑</el-radio-button>
            </el-radio-group>
          </div>
        </div>

        <div class="app-card p-1">
          <LlmTraceTable
            v-if="traceViewMode === 'table'"
            :loading="tracesLoading"
            :traces="traces"
            @detail="openTraceDetail"
            @filter-request="filterByRequest"
          />
          <LlmTraceFlow
            v-else
            :loading="tracesLoading"
            :traces="traces"
            :request-id-filter="traceFilters.request_id"
            @detail="openTraceDetail"
            @clear-filter="() => { traceFilters.request_id = ''; traceViewMode = 'table'; searchTraces() }"
          />
        </div>

        <div v-if="traceTotal > 0" class="mt-4 flex justify-end">
          <el-pagination
            layout="total, prev, pager, next, jumper"
            :total="traceTotal"
            :current-page="tracePage"
            :page-size="traceFilters.limit"
            background
            @current-change="onTracePageChange"
          />
        </div>
      </el-tab-pane>

      <el-tab-pane label="生图调用" name="image-traces">
        <ImageGenerationTracePanel />
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="editVisible" :title="editingId ? '编辑模型' : '新增模型'" width="620px" top="6vh">
      <el-form label-position="top" :disabled="editing">
        <el-form-item label="模型名称" required>
          <el-input v-model="form.name" maxlength="60" placeholder="便于识别的名称" />
        </el-form-item>
        <el-form-item label="接口地址 (base_url)" required>
          <el-input v-model="form.base_url" placeholder="https://api.openai.com/v1" />
        </el-form-item>
        <el-form-item label="模型标识 (model)" required>
          <el-input v-model="form.model" placeholder="gpt-4o / deepseek-chat 等" />
        </el-form-item>
        <el-form-item label="API Key">
          <el-input
            v-model="form.api_key"
            type="password"
            show-password
            :placeholder="editingId ? '留空表示保持原密钥不变' : '接口无需鉴权可留空'"
          />
        </el-form-item>
        <div class="flex gap-4">
          <el-form-item label="角色" class="flex-1">
            <el-select v-model="form.role" class="w-full">
              <el-option value="primary" label="主用" />
              <el-option value="backup" label="备用" />
              <el-option value="disabled" label="停用" />
            </el-select>
          </el-form-item>
          <el-form-item label="优先级（越小越靠前）" class="flex-1">
            <el-input-number v-model="form.priority" :min="0" :max="9999" class="w-full" />
          </el-form-item>
        </div>
        <div class="flex gap-4">
          <el-form-item label="最大生成 token" class="flex-1">
            <el-input-number v-model="form.max_completion_tokens" :min="1" :max="32000" class="w-full" />
          </el-form-item>
          <el-form-item label="超时（秒）" class="flex-1">
            <el-input-number v-model="form.timeout_seconds" :min="1" :max="600" class="w-full" />
          </el-form-item>
        </div>
        <div class="flex items-center gap-6">
          <el-form-item label="流式响应" class="mb-0">
            <el-switch v-model="form.stream" />
          </el-form-item>
          <el-form-item label="启用" class="mb-0">
            <el-switch v-model="form.status" active-value="active" inactive-value="inactive" />
          </el-form-item>
        </div>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="editing" @click="submitModel">保存</el-button>
      </template>
    </el-dialog>

    <!-- 搜索引擎配置弹窗 -->
    <el-dialog
      v-model="searchConfigVisible"
      :title="searchEditingIndex !== null ? '编辑搜索引擎' : '添加搜索引擎'"
      width="560px"
      top="10vh"
    >
      <el-form label-position="top">
        <el-form-item label="供应商模板" required>
          <el-select v-model="searchForm.provider" class="w-full" @change="handleProviderChange">
            <el-option value="duckduckgo" label="DuckDuckGo / 必应免密" />
            <el-option value="google" label="Google Custom Search (需要 Key & CX)" />
            <el-option value="baidu" label="百度千帆 AI 搜索 (需要 API Key)" />
            <el-option value="playwright" label="Playwright 浏览器增强" />
          </el-select>
        </el-form-item>

        <el-form-item
          v-if="searchForm.provider === 'playwright'"
          label="页面搜索引擎"
          required
        >
          <el-select
            v-model="searchForm.search_engine"
            class="w-full"
            @change="handlePlaywrightSearchEngineChange"
          >
            <el-option
              v-for="engine in playwrightSearchEngineOptions"
              :key="engine.value"
              :value="engine.value"
              :label="engine.label"
            >
              <div class="flex flex-col py-1">
                <span class="text-sm text-ink">{{ engine.label }}</span>
                <span class="text-xs text-ink-muted">{{ engine.description }}</span>
              </div>
            </el-option>
          </el-select>
          <p class="mt-1 text-xs text-ink-muted">
            这里决定 Playwright 打开哪个搜索结果页；若选择 Google / DuckDuckGo，建议配置独立代理。
          </p>
        </el-form-item>

        <el-form-item label="显示名称" required>
          <el-input v-model="searchForm.name" maxlength="60" placeholder="方便识别的名称，如：谷歌可编程搜索" />
        </el-form-item>

        <!-- Google Custom Search 独有配置 -->
        <el-form-item v-if="searchForm.provider === 'google'" label="Google CX (搜索引擎 ID)" required>
          <el-input v-model="searchForm.cx" placeholder="请输入谷歌自定义搜索引擎 ID (cx)" />
        </el-form-item>

        <!-- 需要 API Key 的引擎配置 -->
        <el-form-item v-if="searchForm.provider === 'google' || searchForm.provider === 'baidu'">
          <template #label>
            API Key
            <el-tag v-if="searchForm.api_key_configured" size="small" type="success" class="ml-1">
              已配置
            </el-tag>
          </template>
          <el-input
            v-model="searchForm.api_key"
            type="password"
            show-password
            :placeholder="searchForm.api_key_configured ? '留空表示保持原密钥不变' : '请输入 API Key / 密钥'"
          />
        </el-form-item>

        <el-form-item label="独立代理地址">
          <el-input v-model="searchForm.proxy_url" placeholder="http://127.0.0.1:7890 (留空则默认使用全局代理配置)" />
        </el-form-item>

        <el-form-item label="是否启用">
          <el-switch v-model="searchForm.status" active-value="active" inactive-value="inactive" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="searchConfigVisible = false">取消</el-button>
        <el-button type="primary" @click="submitSearchConfig">保存</el-button>
      </template>
    </el-dialog>

    <LlmTraceDetailDrawer v-model="traceDetailVisible" :trace="traceDetail" />
  </div>
</template>
