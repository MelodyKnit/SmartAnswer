<script setup lang="ts">
/**
 * 导入脚本（管理端）：以卡片网格展示仓库内 jsonl 模板目录。
 * 与普通用户工作台「复制导入脚本」共用同一模板源；标记「默认」的模板即普通用户点复制时拿到的那条。
 * 详情弹窗提供接入步骤指引、管理员/用户两种视角预览、脚本与接入配置分区复制。
 */
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { importScriptApi, tokenApi } from '@/api/endpoints'
import type { ApiToken, ImportScript, OcsConfig } from '@/api/types'
import { ApiException, getApiTokenSecret } from '@/api/http'
import PageHeader from '@/components/PageHeader.vue'

const loading = ref(false)
const scripts = ref<ImportScript[]>([])
const tokens = ref<ApiToken[]>([])

const viewVisible = ref(false)
const current = ref<ImportScript | null>(null)
const selectedTokenId = ref('')
const renderedScript = ref('')
const renderedConfig = ref<OcsConfig | null>(null)
const isTokenSecretMissing = ref(false)

/** 字面量占位符文案，避免在模板插值中直接写双花括号被编译器解析。 */
const TOKEN_PLACEHOLDER = '{{TOKEN}}'

/* 新增模板弹窗 */
const createVisible = ref(false)
const creating = ref(false)
const createForm = reactive({
  name: '',
  target: 'ocs',
  description: '',
  script_template: '',
  config_json: '',
  tags_text: '',
  requires_token: true,
  is_default: false,
})

function resetCreateForm() {
  createForm.name = ''
  createForm.target = 'ocs'
  createForm.description = ''
  createForm.script_template = ''
  createForm.config_json = ''
  createForm.tags_text = ''
  createForm.requires_token = true
  createForm.is_default = false
}

function openCreate() {
  resetCreateForm()
  createVisible.value = true
}

async function submitCreate() {
  if (!createForm.name.trim()) {
    ElMessage.warning('请填写模板名称')
    return
  }
  if (!createForm.script_template.trim()) {
    ElMessage.warning('请填写脚本模板内容')
    return
  }
  // 解析接入配置 JSON（可选）
  let configItems: Record<string, unknown>[] = []
  const rawConfig = createForm.config_json.trim()
  if (rawConfig) {
    try {
      const parsed = JSON.parse(rawConfig)
      if (!Array.isArray(parsed)) {
        ElMessage.error('接入配置需为 JSON 数组')
        return
      }
      configItems = parsed
    } catch {
      ElMessage.error('接入配置不是合法的 JSON')
      return
    }
  }
  const tags = createForm.tags_text
    .split(/[,，\s]+/)
    .map((item) => item.trim())
    .filter(Boolean)
  creating.value = true
  try {
    await importScriptApi.create({
      name: createForm.name.trim(),
      target: createForm.target.trim() || 'ocs',
      description: createForm.description.trim(),
      script_template: createForm.script_template,
      config_items: configItems,
      tags,
      requires_token: createForm.requires_token,
      is_default: createForm.is_default,
    })
    ElMessage.success('导入脚本模板已新增')
    createVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error(error instanceof ApiException ? error.message : '新增模板失败')
  } finally {
    creating.value = false
  }
}

async function removeScript(row: ImportScript) {
  try {
    await ElMessageBox.confirm(
      `确认删除自定义模板「${row.name}」？此操作不可恢复。`,
      '删除导入脚本模板',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    await importScriptApi.remove(row.script_id)
    ElMessage.success('模板已删除')
    await load()
  } catch (error) {
    ElMessage.error(error instanceof ApiException ? error.message : '删除模板失败')
  }
}

async function load() {
  loading.value = true
  try {
    const [scriptRes, tokenRes] = await Promise.all([
      importScriptApi.list(),
      tokenApi.list().catch(() => ({ tokens: [] as ApiToken[] })),
    ])
    scripts.value = scriptRes.scripts
    tokens.value = tokenRes.tokens
  } finally {
    loading.value = false
  }
}

/** 默认模板排前，其余保持原序。 */
const orderedScripts = computed(() =>
  [...scripts.value].sort((a, b) => Number(b.is_default ?? false) - Number(a.is_default ?? false)),
)

function targetLabel(target: string): string {
  const map: Record<string, string> = { ocs: 'OCS 网课助手' }
  return map[target] || target
}

/** 按目标平台给出接入步骤指引。 */
function accessSteps(target: string): string[] {
  if (target === 'ocs') {
    return [
      '在浏览器安装 OCS 网课助手与配套的油猴（Tampermonkey）扩展。',
      '复制下方「接入配置」全文。',
      '打开 OCS 设置 → 通用 → 题库配置，粘贴该 JSON 配置。',
      '保存并启用该题库，回到答题页即可自动调用本地题库。',
    ]
  }
  return [
    '复制下方脚本或接入配置。',
    '按目标平台的导入说明粘贴并保存。',
    '启用后即可接入本地题库查询。',
  ]
}

function replaceTokenPlaceholder(value: string, tokenId: string): string {
  const secret = getApiTokenSecret(tokenId)
  if (!secret) {
    isTokenSecretMissing.value = true
    return value.replaceAll('{{TOKEN}}', 'YOUR_API_KEY_HERE')
  }
  return value.replaceAll('{{TOKEN}}', secret)
}

function fillConfigToken(config: OcsConfig, tokenId: string): OcsConfig {
  const payload = JSON.parse(JSON.stringify(config)) as OcsConfig
  for (const item of payload) {
    if (item.headers?.Authorization) {
      item.headers.Authorization = replaceTokenPlaceholder(item.headers.Authorization, tokenId)
    }
  }
  return payload
}

function syncCurrentPreview() {
  const script = current.value
  if (!script) return
  isTokenSecretMissing.value = false
  const tokenId = selectedTokenId.value
  if (!tokenId) {
    renderedScript.value = script.content || ''
    renderedConfig.value = script.ocs_config || null
    return
  }
  renderedScript.value = replaceTokenPlaceholder(script.content || '', tokenId)
  renderedConfig.value = script.ocs_config ? fillConfigToken(script.ocs_config, tokenId) : null
}

async function openView(row: ImportScript) {
  try {
    const res = await importScriptApi.get(row.script_id)
    current.value = res.script
    if (!selectedTokenId.value && tokens.value.length > 0) {
      selectedTokenId.value = tokens.value[0].token_id
    }
    syncCurrentPreview()
    viewVisible.value = true
  } catch (error) {
    ElMessage.error(error instanceof ApiException ? error.message : '加载模板失败')
  }
}

async function copy(text: string) {
  if (!text) {
    ElMessage.warning('暂无可复制内容')
    return
  }
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.warning('复制失败，请手动复制')
  }
}

watch(selectedTokenId, () => {
  syncCurrentPreview()
})

onMounted(load)
</script>

<template>
  <div>
    <PageHeader
      title="导入脚本"
      description="查看仓库内提交的导入脚本模板，和用户侧「复制导入脚本」共用同一模板源。"
    >
      <template #actions>
        <el-button :icon="'Refresh'" @click="load">刷新模板</el-button>
        <el-button type="primary" :icon="'Plus'" @click="openCreate">新增导入脚本</el-button>
      </template>
    </PageHeader>

    <el-alert type="info" :closable="false" class="mb-4">
      <template #title>
        模板目录由仓库中的 jsonl 文件统一维护，新增脚本只需补充模板记录。标记
        <el-tag size="small" type="success" effect="dark" class="mx-1">默认</el-tag>
        的模板，就是普通用户在工作台点「复制导入脚本」时拿到的那条。
      </template>
    </el-alert>

    <div v-loading="loading">
      <div
        v-if="orderedScripts.length"
        class="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3"
      >
        <div
          v-for="script in orderedScripts"
          :key="script.script_id"
          class="app-card flex flex-col p-5 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg relative overflow-hidden"
          :class="script.is_default ? 'border-t-4 border-brand-500' : 'border-t-4 border-line'"
        >
          <!-- 默认标识 -->
          <div v-if="script.is_default" class="absolute top-0 right-0">
            <span class="bg-brand-500 text-white text-[10px] font-semibold px-2.5 py-0.5 rounded-bl">默认模板</span>
          </div>

          <div class="mb-3 pr-16">
            <h3 class="text-base font-semibold text-ink flex items-center gap-1.5">
              <el-icon class="text-brand-500"><Document /></el-icon>
              {{ script.name }}
            </h3>
          </div>

          <p class="mb-4 line-clamp-2 min-h-10 text-xs text-ink-soft">
            {{ script.description || '暂无描述信息' }}
          </p>

          <!-- 元数据网格 -->
          <div class="mb-4 grid grid-cols-2 gap-2 rounded-lg bg-card-soft p-2.5 text-xs">
            <div class="flex items-center gap-1.5 text-ink-soft">
              <span class="text-ink-muted">适用平台:</span>
              <span class="font-medium">{{ targetLabel(script.target) }}</span>
            </div>
            <div class="flex items-center gap-1.5 text-ink-soft">
              <span class="text-ink-muted">鉴权要求:</span>
              <span
                class="font-medium"
                :class="script.requires_token ? 'text-amber-600 dark:text-amber-400' : 'text-emerald-600 dark:text-emerald-400'"
              >
                {{ script.requires_token ? '需要 Key' : '免 Key' }}
              </span>
            </div>
          </div>

          <!-- 标签展示 -->
          <div v-if="script.tags && script.tags.length" class="mb-4 flex flex-wrap gap-1">
            <span
              v-for="tag in script.tags"
              :key="tag"
              class="rounded bg-canvas px-2 py-0.5 text-[10px] text-ink-muted border border-line"
            >
              {{ tag }}
            </span>
          </div>

          <!-- 底部栏 -->
          <div class="mt-auto flex items-center justify-between border-t border-line pt-3">
            <span class="text-xs text-ink-muted">
              {{ script.builtin ? '内置模板' : '自定义模板' }}
            </span>
            <div class="flex items-center gap-1">
              <el-button type="primary" link size="small" :icon="'View'" @click="openView(script)">
                配置与预览
              </el-button>
              <el-button
                v-if="!script.builtin"
                type="danger"
                link
                size="small"
                :icon="'Delete'"
                @click="removeScript(script)"
              >
                删除
              </el-button>
            </div>
          </div>
        </div>
      </div>

      <el-empty v-else-if="!loading" description="暂无导入脚本模板" />
    </div>

    <el-dialog v-model="viewVisible" :title="current?.name || '配置与预览'" width="760px" top="6vh">
      <div v-if="current" class="space-y-5">
        <!-- 关联说明 -->
        <el-alert
          v-if="current.is_default"
          type="success"
          :closable="false"
          title="提示：当前是默认模板，用户在工作台点一键复制时将直接获得填充本人密钥后的内容。"
        />

        <!-- 接入步骤指引 -->
        <div>
          <div class="mb-3 text-sm font-semibold text-ink flex items-center gap-1">
            <el-icon class="text-brand-500"><SetUp /></el-icon>
            <span>接入步骤指引</span>
          </div>
          <el-steps
            direction="vertical"
            :active="accessSteps(current.target).length"
            space="46px"
          >
            <el-step
              v-for="(step, i) in accessSteps(current.target)"
              :key="i"
              :title="step"
            />
          </el-steps>
        </div>

        <!-- 密钥填充注入 (仅在需要密钥时展示) -->
        <div v-if="current.requires_token && tokens.length" class="flex items-center gap-3 rounded-lg bg-card-soft p-3.5 border border-line text-xs">
          <span class="text-xs text-ink-soft font-semibold whitespace-nowrap">填充 API Key</span>
          <el-select
            v-model="selectedTokenId"
            clearable
            placeholder="选择 API Key 进行预览填充（可选）"
            size="small"
            class="w-64"
          >
            <el-option
              v-for="token in tokens"
              :key="token.token_id"
              :value="token.token_id"
              :label="token.description || token.key_mask"
            />
          </el-select>
          <span class="text-ink-muted">不选则原样展示占位符 {{ TOKEN_PLACEHOLDER }}</span>
        </div>

        <el-alert
          v-if="isTokenSecretMissing"
          type="warning"
          :closable="false"
          title="当前浏览器未缓存所选 API Key 的明文，预览中已用 YOUR_API_KEY_HERE 占位。用户实际复制时会自动填入其本人密钥。"
        />

        <!-- 脚本 -->
        <div>
          <div class="mb-2 flex items-center justify-between">
            <span class="text-sm font-medium text-ink-soft">导入脚本</span>
            <el-button link type="primary" size="small" :icon="'CopyDocument'" @click="copy(renderedScript)">
              复制脚本
            </el-button>
          </div>
          <pre
            class="max-h-56 overflow-auto rounded-lg bg-[#0f172a] p-4 text-xs leading-relaxed text-slate-200 font-mono"
          >{{ renderedScript }}</pre>
        </div>

        <!-- 接入配置 -->
        <div v-if="renderedConfig">
          <div class="mb-2 flex items-center justify-between">
            <span class="text-sm font-medium text-ink-soft">接入配置</span>
            <el-button
              link
              type="primary"
              size="small"
              :icon="'CopyDocument'"
              @click="copy(JSON.stringify(renderedConfig, null, 2))"
            >
              复制配置
            </el-button>
          </div>
          <pre
            class="max-h-56 overflow-auto rounded-lg bg-[#0f172a] p-4 text-xs leading-relaxed text-slate-200 font-mono"
          >{{ JSON.stringify(renderedConfig, null, 2) }}</pre>
        </div>
      </div>

      <template #footer>
        <el-button type="primary" @click="viewVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 新增模板弹窗 -->
    <el-dialog v-model="createVisible" title="新增导入脚本模板" width="680px" top="6vh">
      <el-form label-position="top" :disabled="creating">
        <el-form-item label="模板名称" required>
          <el-input v-model="createForm.name" maxlength="60" placeholder="例如：OCS 网课助手题库" />
        </el-form-item>
        <div class="flex gap-4">
          <el-form-item label="目标平台" class="flex-1">
            <el-select v-model="createForm.target" class="w-full">
              <el-option value="ocs" label="OCS 网课助手" />
            </el-select>
          </el-form-item>
          <el-form-item label="标签（逗号或空格分隔）" class="flex-1">
            <el-input v-model="createForm.tags_text" placeholder="例如：网课, 自动答题" />
          </el-form-item>
        </div>
        <el-form-item label="模板描述">
          <el-input v-model="createForm.description" type="textarea" :rows="2" placeholder="简要说明此模板的用途" />
        </el-form-item>
        <el-form-item label="脚本模板内容" required>
          <el-input
            v-model="createForm.script_template"
            type="textarea"
            :rows="6"
            :placeholder="`脚本正文，使用 ${TOKEN_PLACEHOLDER} 占位用户的 API Key`"
          />
        </el-form-item>
        <el-form-item label="接入配置（JSON 数组，可选）">
          <el-input
            v-model="createForm.config_json"
            type="textarea"
            :rows="5"
            placeholder='[{"name":"本地题库","url":"...","headers":{"Authorization":"Bearer {{TOKEN}}"}}]'
          />
        </el-form-item>
        <div class="flex items-center gap-6">
          <el-checkbox v-model="createForm.requires_token">需要 API Key</el-checkbox>
          <el-checkbox v-model="createForm.is_default">设为默认模板（用户复制时取此条）</el-checkbox>
        </div>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="submitCreate">保存模板</el-button>
      </template>
    </el-dialog>
  </div>
</template>
