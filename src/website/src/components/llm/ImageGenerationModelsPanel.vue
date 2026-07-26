<script setup lang="ts">
/** 生图模型配置面板：用受控协议配置声明模型实际可用的输出能力。 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { imageGenerationApi } from '@/api/endpoints'
import { ApiException } from '@/api/http'
import type { ImageGenerationModel } from '@/api/types'
import { formatDateTime } from '@/utils/format'

defineProps<{ canManage: boolean }>()

const geminiAspectRatioOptions = [
  '1:1', '1:4', '4:1', '1:8', '8:1', '2:3', '3:2', '3:4', '4:3', '4:5', '5:4', '9:16', '16:9', '21:9',
]
const geminiImageSizeOptions = ['512', '1K', '2K', '4K']
const defaultPresetSizes = ['1024x1024', '1024x1536', '1536x1024']

const loading = ref(false)
const saving = ref(false)
const visible = ref(false)
const editingId = ref('')
const testingId = ref('')
const models = ref<ImageGenerationModel[]>([])
const form = reactive({
  name: '',
  provider: 'openai-images',
  base_url: '',
  model: '',
  api_key: '',
  timeout_seconds: 60,
  status: 'active',
  gemini_auth_mode: 'x-goog-api-key',
  gemini_aspect_ratios: ['1:1'] as string[],
  gemini_image_sizes: ['1K'] as string[],
  preset_sizes_text: defaultPresetSizes.join(', '),
  allow_custom_size: false,
  min_width: 512,
  max_width: 3840,
  min_height: 512,
  max_height: 3840,
  step: 16,
  min_pixels: 655360,
  max_pixels: 8294400,
})

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function stringList(value: unknown, fallback: string[]): string[] {
  if (!Array.isArray(value)) return [...fallback]
  const normalized = [...new Set(value.map((item) => String(item).trim()).filter(Boolean))]
  return normalized.length ? normalized : [...fallback]
}

function numberValue(value: unknown, fallback: number): number {
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback
}

function sizesFromText(value: string): string[] {
  return [...new Set(value.split(',').map((item) => item.trim().toLowerCase()).filter(Boolean))]
}

function protocolLabel(provider: string): string {
  const labels: Record<string, string> = {
    'gemini-native': 'Gemini 原生协议',
    'openai-images': 'OpenAI Images 协议',
    'openai-compatible-images': '通用兼容 Images 协议',
    'openai-chat-image': '旧版聊天生图兼容协议',
  }
  return labels[provider] || provider
}

function displayOutput(model: ImageGenerationModel): string {
  const config = isRecord(model.protocol_config) ? model.protocol_config : {}
  if (model.provider === 'gemini-native') {
    return `${stringList(config.aspect_ratios, ['1:1']).join(' / ')} · ${stringList(config.image_sizes, ['1K']).join(' / ')}`
  }
  if (model.provider === 'openai-chat-image') return '由模型决定'
  return stringList(config.preset_sizes, model.capabilities.filter((item) => item.includes('x'))).join(' / ')
}

function resetProtocolForm() {
  form.gemini_auth_mode = 'x-goog-api-key'
  form.gemini_aspect_ratios = ['1:1']
  form.gemini_image_sizes = ['1K']
  form.preset_sizes_text = defaultPresetSizes.join(', ')
  form.allow_custom_size = false
  form.min_width = 512
  form.max_width = 3840
  form.min_height = 512
  form.max_height = 3840
  form.step = 16
  form.min_pixels = 655360
  form.max_pixels = 8294400
}

function resetForm() {
  editingId.value = ''
  form.name = ''
  form.provider = 'openai-images'
  form.base_url = ''
  form.model = ''
  form.api_key = ''
  form.timeout_seconds = 60
  form.status = 'active'
  resetProtocolForm()
}

function resetProtocolForProvider() {
  resetProtocolForm()
}

function protocolConfig(): Record<string, unknown> {
  if (form.provider === 'gemini-native') {
    return {
      auth_mode: form.gemini_auth_mode,
      aspect_ratios: [...form.gemini_aspect_ratios],
      image_sizes: [...form.gemini_image_sizes],
    }
  }
  if (form.provider === 'openai-images') {
    return {
      preset_sizes: sizesFromText(form.preset_sizes_text),
      allow_custom_size: form.allow_custom_size,
      custom_size_constraints: {
        min_width: form.min_width,
        max_width: form.max_width,
        min_height: form.min_height,
        max_height: form.max_height,
        step: form.step,
        min_pixels: form.min_pixels,
        max_pixels: form.max_pixels,
      },
    }
  }
  if (form.provider === 'openai-compatible-images') {
    return { preset_sizes: sizesFromText(form.preset_sizes_text), allow_custom_size: false }
  }
  return { mode: 'model-controlled' }
}

async function load() {
  loading.value = true
  try {
    models.value = (await imageGenerationApi.models()).models
  } catch (error) {
    ElMessage.error(error instanceof ApiException ? error.message : '加载生图模型失败')
  } finally {
    loading.value = false
  }
}

function openCreate() {
  resetForm()
  visible.value = true
}

function openEdit(model: ImageGenerationModel) {
  const config = isRecord(model.protocol_config) ? model.protocol_config : {}
  const constraints = isRecord(config.custom_size_constraints) ? config.custom_size_constraints : {}
  editingId.value = model.model_id
  form.name = model.name
  form.provider = model.provider
  form.base_url = model.base_url
  form.model = model.model
  form.api_key = ''
  form.timeout_seconds = model.timeout_seconds
  form.status = model.status
  form.gemini_auth_mode = config.auth_mode === 'bearer' ? 'bearer' : 'x-goog-api-key'
  form.gemini_aspect_ratios = stringList(config.aspect_ratios, ['1:1'])
  form.gemini_image_sizes = stringList(config.image_sizes, ['1K'])
  form.preset_sizes_text = stringList(
    config.preset_sizes,
    model.capabilities.filter((item) => item.includes('x')),
  ).join(', ')
  form.allow_custom_size = config.allow_custom_size === true
  form.min_width = numberValue(constraints.min_width, 512)
  form.max_width = numberValue(constraints.max_width, 3840)
  form.min_height = numberValue(constraints.min_height, 512)
  form.max_height = numberValue(constraints.max_height, 3840)
  form.step = numberValue(constraints.step, 16)
  form.min_pixels = numberValue(constraints.min_pixels, 655360)
  form.max_pixels = numberValue(constraints.max_pixels, 8294400)
  visible.value = true
}

async function save() {
  if (!form.name.trim() || !form.base_url.trim() || !form.model.trim()) {
    ElMessage.warning('请填写模型名称、接口地址和模型标识')
    return
  }
  if (!editingId.value && !form.api_key.trim()) {
    ElMessage.warning('新增生图模型时必须填写 API Key')
    return
  }
  if (form.provider === 'gemini-native' && (!form.gemini_aspect_ratios.length || !form.gemini_image_sizes.length)) {
    ElMessage.warning('请至少保留一个 Gemini 画幅比例和像素档位')
    return
  }
  if (
    ['openai-images', 'openai-compatible-images'].includes(form.provider)
    && !sizesFromText(form.preset_sizes_text).length
  ) {
    ElMessage.warning('请至少配置一个预设图片尺寸')
    return
  }
  saving.value = true
  try {
    const payload: Record<string, unknown> = {
      name: form.name.trim(),
      provider: form.provider,
      base_url: form.base_url.trim(),
      model: form.model.trim(),
      timeout_seconds: form.timeout_seconds,
      status: form.status,
      protocol_config: protocolConfig(),
    }
    if (form.api_key.trim()) payload.api_key = form.api_key.trim()
    if (editingId.value) {
      await imageGenerationApi.updateModel(editingId.value, payload)
      ElMessage.success('生图模型已更新')
    } else {
      await imageGenerationApi.createModel({ ...payload, api_key: form.api_key.trim() })
      ElMessage.success('生图模型已新增')
    }
    visible.value = false
    await load()
  } catch (error) {
    ElMessage.error(error instanceof ApiException ? error.message : '保存生图模型失败')
  } finally {
    saving.value = false
  }
}

async function test(model: ImageGenerationModel) {
  testingId.value = model.model_id
  try {
    const result = await imageGenerationApi.testModel(model.model_id)
    if (result.ok) {
      ElMessage.success(`模型连通性正常，耗时 ${Math.round(result.elapsed_ms)} ms`)
    } else {
      ElMessage.error(result.error || '模型测试失败')
    }
  } catch (error) {
    ElMessage.error(error instanceof ApiException ? error.message : '测试请求失败')
  } finally {
    testingId.value = ''
  }
}

async function remove(model: ImageGenerationModel) {
  try {
    await ElMessageBox.confirm(
      `删除后将无法再创建使用「${model.name}」的新任务，历史任务不受影响。`,
      '删除生图模型',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    await imageGenerationApi.deleteModel(model.model_id)
    ElMessage.success('生图模型已删除')
    await load()
  } catch (error) {
    ElMessage.error(error instanceof ApiException ? error.message : '删除生图模型失败')
  }
}

onMounted(load)
</script>

<template>
  <section class="space-y-4">
    <div class="app-card p-5">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 class="text-base font-semibold text-ink">生图模型</h3>
          <p class="mt-1 text-xs text-ink-soft">模型协议、尺寸能力与聊天模型独立配置；同一时间仅一个生图模型启用。</p>
        </div>
        <div class="flex gap-2">
          <el-button @click="load">刷新</el-button>
          <el-button v-if="canManage" type="primary" :icon="'Plus'" @click="openCreate">新增模型</el-button>
        </div>
      </div>
    </div>

    <div class="app-card p-1">
      <el-table v-loading="loading" :data="models" style="width: 100%">
        <el-table-column label="名称" min-width="120" prop="name" show-overflow-tooltip />
        <el-table-column label="协议" min-width="150" show-overflow-tooltip>
          <template #default="{ row }"><span class="text-xs text-ink-soft">{{ protocolLabel(row.provider) }}</span></template>
        </el-table-column>
        <el-table-column label="模型标识" min-width="140" prop="model" show-overflow-tooltip />
        <el-table-column label="输出能力" min-width="180" show-overflow-tooltip>
          <template #default="{ row }"><span class="text-xs text-ink-soft">{{ displayOutput(row) }}</span></template>
        </el-table-column>
        <el-table-column label="状态" width="84" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.status === 'active' ? 'success' : 'info'" effect="plain">
              {{ row.status === 'active' ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="更新时间" width="150" align="right">
          <template #default="{ row }">{{ formatDateTime(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column v-if="canManage" label="操作" width="150" align="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link type="warning" :loading="testingId === row.model_id" @click="test(row)">测试</el-button>
            <el-button link type="danger" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
        <template #empty><el-empty description="暂无生图模型配置" /></template>
      </el-table>
    </div>

    <el-dialog v-model="visible" :title="editingId ? '编辑生图模型' : '新增生图模型'" width="680px" top="6vh">
      <el-form label-position="top" :disabled="saving">
        <el-form-item label="模型名称" required><el-input v-model="form.name" maxlength="60" /></el-form-item>
        <el-form-item label="调用协议" required>
          <el-select v-model="form.provider" class="w-full" @change="resetProtocolForProvider">
            <el-option value="gemini-native" label="Gemini 原生协议" />
            <el-option value="openai-images" label="OpenAI Images 协议" />
            <el-option value="openai-compatible-images" label="通用兼容 Images 协议" />
            <el-option value="openai-chat-image" label="旧版聊天生图兼容协议" />
          </el-select>
        </el-form-item>
        <el-alert v-if="form.provider === 'gemini-native'" type="info" :closable="false" show-icon title="使用 generateContent 与 imageConfig，支持画幅比例和像素档位。" />
        <el-alert v-else-if="form.provider === 'openai-images'" type="info" :closable="false" show-icon title="使用 /images/generations；可按模型能力声明预设尺寸或受控自定义尺寸。" />
        <el-alert v-else-if="form.provider === 'openai-compatible-images'" type="info" :closable="false" show-icon title="使用兼容 /images/generations，仅向用户开放管理员声明的预设尺寸。" />
        <el-alert v-else type="warning" :closable="false" show-icon title="旧配置兼容入口，尺寸由上游聊天模型决定，不建议用于新增模型。" />
        <el-form-item class="mt-4" label="接口地址 (base_url)" required><el-input v-model="form.base_url" placeholder="https://api.example.com/v1" /></el-form-item>
        <el-form-item label="模型标识" required><el-input v-model="form.model" placeholder="例如 gemini-3.1-flash-image" /></el-form-item>
        <el-form-item :label="editingId ? 'API Key（留空保持不变）' : 'API Key'" required>
          <el-input v-model="form.api_key" type="password" show-password autocomplete="new-password" />
        </el-form-item>
        <div class="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
          <el-form-item label="请求超时（秒)"><el-input-number v-model="form.timeout_seconds" :min="5" :max="300" class="w-full" /></el-form-item>
          <el-form-item label="状态"><el-select v-model="form.status" class="w-full"><el-option value="active" label="启用" /><el-option value="inactive" label="停用" /></el-select></el-form-item>
        </div>

        <section v-if="form.provider === 'gemini-native'" class="rounded-lg border border-line bg-card-soft p-4">
          <h4 class="text-sm font-medium text-ink">Gemini 输出能力</h4>
          <div class="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2">
            <el-form-item label="鉴权方式" class="mb-0"><el-select v-model="form.gemini_auth_mode"><el-option value="x-goog-api-key" label="x-goog-api-key" /><el-option value="bearer" label="Bearer" /></el-select></el-form-item>
            <el-form-item label="可用像素档位" class="mb-0"><el-select v-model="form.gemini_image_sizes" multiple collapse-tags collapse-tags-tooltip><el-option v-for="value in geminiImageSizeOptions" :key="value" :label="value" :value="value" /></el-select></el-form-item>
          </div>
          <el-form-item label="可用画幅比例" class="mb-0 mt-4"><el-select v-model="form.gemini_aspect_ratios" multiple collapse-tags collapse-tags-tooltip><el-option v-for="value in geminiAspectRatioOptions" :key="value" :label="value" :value="value" /></el-select></el-form-item>
        </section>

        <section v-else-if="form.provider === 'openai-images' || form.provider === 'openai-compatible-images'" class="rounded-lg border border-line bg-card-soft p-4">
          <h4 class="text-sm font-medium text-ink">输出尺寸能力</h4>
          <el-form-item label="预设尺寸" class="mb-0 mt-3"><el-input v-model="form.preset_sizes_text" placeholder="1024x1024, 1536x1024" /><p class="mt-1 text-xs text-ink-muted">以逗号分隔，必须是宽x高格式。</p></el-form-item>
          <template v-if="form.provider === 'openai-images'">
            <div class="mt-4 flex items-center justify-between rounded-md border border-line px-3 py-2.5"><span class="text-sm text-ink">允许受控自定义尺寸</span><el-switch v-model="form.allow_custom_size" /></div>
            <div v-if="form.allow_custom_size" class="mt-4 grid grid-cols-2 gap-x-4">
              <el-form-item label="最小宽度"><el-input-number v-model="form.min_width" :min="1" class="w-full" /></el-form-item>
              <el-form-item label="最大宽度"><el-input-number v-model="form.max_width" :min="1" class="w-full" /></el-form-item>
              <el-form-item label="最小高度"><el-input-number v-model="form.min_height" :min="1" class="w-full" /></el-form-item>
              <el-form-item label="最大高度"><el-input-number v-model="form.max_height" :min="1" class="w-full" /></el-form-item>
              <el-form-item label="宽高步长"><el-input-number v-model="form.step" :min="1" class="w-full" /></el-form-item>
              <el-form-item label="最小像素"><el-input-number v-model="form.min_pixels" :min="1" class="w-full" /></el-form-item>
              <el-form-item label="最大像素"><el-input-number v-model="form.max_pixels" :min="1" class="w-full" /></el-form-item>
            </div>
          </template>
        </section>
      </el-form>
      <template #footer>
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </section>
</template>
