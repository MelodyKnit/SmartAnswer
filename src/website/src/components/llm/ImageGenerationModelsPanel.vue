<script setup lang="ts">
/** 生图模型配置面板：独立于聊天模型，不回显供应商密钥。 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { imageGenerationApi } from '@/api/endpoints'
import { ApiException } from '@/api/http'
import type { ImageGenerationModel } from '@/api/types'
import { formatDateTime } from '@/utils/format'

defineProps<{ canManage: boolean }>()

const loading = ref(false)
const saving = ref(false)
const visible = ref(false)
const editingId = ref('')
const testingId = ref('')
const models = ref<ImageGenerationModel[]>([])
const form = reactive({
  name: '',
  provider: 'openai-images' as string,
  base_url: '',
  model: '',
  api_key: '',
  timeout_seconds: 60,
  status: 'active',
  capabilities_text: 'text-to-image, 1024x1024, 1024x1536, 1536x1024',
})

function capabilitiesFromText(value: string): string[] {
  return [...new Set(value.split(',').map((item) => item.trim()).filter(Boolean))]
}

function displaySizes(model: ImageGenerationModel): string {
  return model.capabilities.filter((item) => item !== 'text-to-image').join(' / ')
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
  form.capabilities_text = 'text-to-image, 1024x1024, 1024x1536, 1536x1024'
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
  editingId.value = model.model_id
  form.name = model.name
  form.provider = model.provider
  form.base_url = model.base_url
  form.model = model.model
  form.api_key = ''
  form.timeout_seconds = model.timeout_seconds
  form.status = model.status
  form.capabilities_text = model.capabilities.join(', ')
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
  const capabilities = capabilitiesFromText(form.capabilities_text)
  if (!capabilities.includes('text-to-image') || capabilities.length < 2) {
    ElMessage.warning('能力集必须包含 text-to-image 和至少一个图片尺寸')
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
      capabilities,
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
          <p class="mt-1 text-xs text-ink-soft">支持 OpenAI Images 与兼容聊天生图协议，和聊天模型配置相互独立；同一时间仅一个模型启用。</p>
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
        <el-table-column label="模型标识" min-width="140" prop="model" show-overflow-tooltip />
        <el-table-column label="接口地址" min-width="210" prop="base_url" show-overflow-tooltip />
        <el-table-column label="能力" min-width="130" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="text-xs text-ink-soft">{{ displaySizes(row) }}</span>
          </template>
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

    <el-dialog v-model="visible" :title="editingId ? '编辑生图模型' : '新增生图模型'" width="620px" top="6vh">
      <el-form label-position="top" :disabled="saving">
        <el-form-item label="模型名称" required><el-input v-model="form.name" maxlength="60" /></el-form-item>
        <el-form-item label="调用协议" required>
          <el-select v-model="form.provider" class="w-full">
            <el-option value="openai-images" label="OpenAI Images 协议" />
            <el-option value="openai-chat-image" label="OpenAI 兼容聊天生图" />
          </el-select>
          <p class="mt-1 text-xs text-ink-muted">
            聊天生图适用于通过 <code>/chat/completions</code> 返回图片的兼容模型；图片尺寸由上游模型实际能力决定。
          </p>
        </el-form-item>
        <el-form-item label="接口地址 (base_url)" required><el-input v-model="form.base_url" placeholder="https://api.example.com/v1" /></el-form-item>
        <el-form-item label="模型标识" required><el-input v-model="form.model" placeholder="例如 gpt-image-1" /></el-form-item>
        <el-form-item :label="editingId ? 'API Key（留空保持不变）' : 'API Key'" required>
          <el-input v-model="form.api_key" type="password" show-password autocomplete="new-password" />
        </el-form-item>
        <div class="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
          <el-form-item label="请求超时（秒)"><el-input-number v-model="form.timeout_seconds" :min="5" :max="300" class="w-full" /></el-form-item>
          <el-form-item label="状态">
            <el-select v-model="form.status" class="w-full"><el-option value="active" label="启用" /><el-option value="inactive" label="停用" /></el-select>
          </el-form-item>
        </div>
        <el-form-item label="能力集" required>
          <el-input v-model="form.capabilities_text" placeholder="text-to-image, 1024x1024" />
          <p class="mt-1 text-xs text-ink-muted">逗号分隔；首版仅支持文本生图与模型明确支持的尺寸。</p>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </section>
</template>
