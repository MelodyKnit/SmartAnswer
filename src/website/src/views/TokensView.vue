<script setup lang="ts">
/** API Key 管理：列表、创建、启用/禁用与删除。用户级，仅管理自己的令牌。 */
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { tokenApi } from '@/api/endpoints'
import type { ApiToken, OcsConfig } from '@/api/types'
import { ApiException } from '@/api/http'
import { formatDateTime } from '@/utils/format'
import PageHeader from '@/components/PageHeader.vue'
import OcsConfigCopyDialog from '@/components/OcsConfigCopyDialog.vue'

const loading = ref(false)
const tokens = ref<ApiToken[]>([])

const createVisible = ref(false)
const creating = ref(false)
const newDescription = ref('')
const newQuotaLimit = ref(-1)
const newRejectLowConfidence = ref(false)
const newMinAnswerConfidence = ref(0)

const editVisible = ref(false)
const updating = ref(false)
const statusChanging = ref(false)
const editForm = ref({
  token_id: '',
  key_mask: '',
  description: '',
  status: 'active',
  quota_limit: -1,
  reject_low_confidence: false,
  min_answer_confidence: 0,
})

const revealVisible = ref(false)
const revealToken = ref('')
const revealConfig = ref<OcsConfig | null>(null)
const ocsConfigDialog = ref<InstanceType<typeof OcsConfigCopyDialog>>()

async function load() {
  loading.value = true
  try {
    const res = await tokenApi.list()
    tokens.value = res.tokens
  } finally {
    loading.value = false
  }
}

function openCreate() {
  newDescription.value = ''
  newQuotaLimit.value = -1
  newRejectLowConfidence.value = false
  newMinAnswerConfidence.value = 0
  createVisible.value = true
}

async function submitCreate() {
  creating.value = true
  try {
    const res = await tokenApi.create(
      newDescription.value.trim(),
      newQuotaLimit.value,
      newRejectLowConfidence.value,
      newMinAnswerConfidence.value,
    )
    createVisible.value = false
    revealToken.value = res.token
    revealConfig.value = res.ocs_config
    revealVisible.value = true
    await load()
  } catch (err) {
    ElMessage.error(err instanceof ApiException ? err.message : '创建失败')
  } finally {
    creating.value = false
  }
}

async function setEditingTokenEnabled() {
  if (editForm.value.status === 'revoked') {
    ElMessage.warning('已吊销的 API Key 不能重新启用，请创建新的 API Key')
    return
  }
  const label = editForm.value.description || editForm.value.key_mask
  const enabled = editForm.value.status === 'disabled'
  const action = enabled ? '启用' : '禁用'
  const description = enabled
    ? '启用后客户端可以恢复访问。'
    : '禁用后使用该令牌的客户端将立即无法访问服务。'
  const confirmed = await ElMessageBox.confirm(
    '确定' + action + ' API Key「' + label + '」吗？' + description,
    action + '确认',
    { type: enabled ? 'info' : 'warning', confirmButtonText: action, cancelButtonText: '取消' },
  )
    .then(() => true)
    .catch(() => false)
  if (!confirmed) return
  statusChanging.value = true
  try {
    const res = await tokenApi.setStatus(editForm.value.token_id, enabled)
    editForm.value.status = res.token.status
    ElMessage.success('已' + action)
    await load()
  } catch (err) {
    ElMessage.error(err instanceof ApiException ? err.message : '操作失败')
  } finally {
    statusChanging.value = false
  }
}

async function remove(token: ApiToken) {
  const confirmed = await ElMessageBox.confirm(
    `确定彻底删除令牌「${token.description || token.key_mask}」吗？删除后此令牌的所有记录将被彻底移除。`,
    '删除确认',
    { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
  )
    .then(() => true)
    .catch(() => false)
  if (!confirmed) return
  try {
    await tokenApi.delete(token.token_id)
    ElMessage.success('已删除')
    await load()
  } catch (err) {
    ElMessage.error(err instanceof ApiException ? err.message : '删除失败')
  }
}

async function copyToken(token: ApiToken) {
  if (token.status !== 'active') {
    ElMessage.warning(token.status === 'revoked' ? '已吊销的 API Key 无法复制' : '已禁用的 API Key 无法复制')
    return
  }
  if (!token.is_recoverable) {
    ElMessage.warning('该 API Key 无法恢复完整密钥，请新建一个 API Key')
    return
  }
  try {
    const res = await tokenApi.copyValue(token.token_id)
    await copy(res.token)
  } catch (err) {
    ElMessage.error(err instanceof ApiException ? err.message : '获取完整密钥失败')
  }
}

function openEdit(token: ApiToken) {
  editForm.value = {
    token_id: token.token_id,
    key_mask: token.key_mask,
    description: token.description || '',
    status: token.status,
    quota_limit: token.quota_limit ?? -1,
    reject_low_confidence: Boolean(token.reject_low_confidence),
    min_answer_confidence: token.min_answer_confidence ?? 0,
  }
  editVisible.value = true
}

async function submitUpdate() {
  if (!editForm.value.description.trim()) {
    ElMessage.warning('描述不能为空')
    return
  }
  updating.value = true
  try {
    await tokenApi.update(
      editForm.value.token_id,
      editForm.value.description.trim(),
      editForm.value.quota_limit,
      editForm.value.reject_low_confidence,
      editForm.value.min_answer_confidence,
    )
    editVisible.value = false
    ElMessage.success('修改成功')
    await load()
  } catch (err) {
    ElMessage.error(err instanceof ApiException ? err.message : '修改失败')
  } finally {
    updating.value = false
  }
}

async function copy(text: string) {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.warning('复制失败，请手动复制')
  }
}

function openOcsConfig(token?: ApiToken) {
  ocsConfigDialog.value?.open(token?.token_id)
}

const ocsConfigText = (config: OcsConfig | null) =>
  config ? JSON.stringify(config, null, 2) : ''

onMounted(load)
</script>

<template>
  <div>
    <PageHeader title="API Key 管理" description="创建并管理用于 OCS 等客户端接入答题服务的 API 令牌。">
      <template #actions>
        <router-link to="/help?article=api-key-guide">
          <el-button :icon="'QuestionFilled'" plain>使用指南</el-button>
        </router-link>
        <el-button :icon="'DocumentCopy'" @click="openOcsConfig()">复制 OCS 配置</el-button>
        <el-button type="primary" :icon="'Plus'" @click="openCreate">创建 API Key</el-button>
      </template>
    </PageHeader>

    <div class="mb-4">
      <el-alert
        type="info"
        :closable="true"
        show-icon
      >
        <template #title>
          <span>初次使用 API Key？</span>
          <router-link
            to="/help?article=api-key-guide"
            class="ml-1 font-semibold text-brand-600 hover:underline dark:text-brand-400"
          >
            点击查看《API Key 是什么、如何创建以及如何接入 OCS》
          </router-link>
        </template>
      </el-alert>
    </div>

    <div class="app-card p-1">
      <el-table v-loading="loading" :data="tokens" style="width: 100%">
        <el-table-column label="名称" min-width="160">
          <template #default="{ row }">
            <span class="font-medium text-ink">{{ row.description || '未命名令牌' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="密钥" min-width="210" align="center">
          <template #default="{ row }">
            <div class="inline-flex items-center gap-1.5">
              <code
                class="rounded bg-canvas px-2 py-1 text-xs"
                :title="row.status === 'active' && row.is_recoverable ? '点击复制完整 API Key' : '该 API Key 当前不可复制'"
                :class="row.status === 'active' && row.is_recoverable ? 'cursor-pointer text-ink-soft hover:bg-canvas-hover' : 'cursor-not-allowed text-ink-muted'"
                @click="copyToken(row)"
              >
                {{ row.key_mask }}
              </code>
              <el-button
                circle
                text
                size="small"
                icon="CopyDocument"
                :title="row.status === 'active' && row.is_recoverable ? '点击复制完整 API Key' : '该 API Key 当前不可复制'"
                :disabled="row.status !== 'active' || !row.is_recoverable"
                @click="copyToken(row)"
              />
            </div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="row.status === 'active' ? 'success' : row.status === 'revoked' ? 'danger' : 'info'" size="small">
              {{ row.status === 'active' ? '正常' : row.status === 'revoked' ? '已吊销' : '已禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="调用次数" width="90" prop="usage_count" align="center" />
        <el-table-column label="已用 / 限额" width="160" align="center">
          <template #default="{ row }">
            <span class="text-ink-soft">{{ row.quota_used }}</span>
            <span class="text-ink-muted"> / </span>
            <span :class="row.quota_limit === -1 ? 'text-ink-muted' : 'text-ink'">
              {{ row.quota_limit === -1 ? '无限制' : `${row.quota_limit} 积分` }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="低信任度" width="130" align="center">
          <template #default="{ row }">
            <el-tag :type="row.reject_low_confidence ? 'warning' : 'info'" size="small">
              {{ row.reject_low_confidence ? `拒答 ${row.min_answer_confidence || '系统'}` : '允许' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="最近使用" width="170" align="center">
          <template #default="{ row }">{{ formatDateTime(row.last_used_at) }}</template>
        </el-table-column>
        <el-table-column label="创建时间" width="170" align="center">
          <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="150" align="right">
          <template #default="{ row }">
            <div class="flex justify-end gap-2">
              <template v-if="row.status === 'active'">
                <el-button
                  link
                  type="primary"
                  @click="openOcsConfig(row)"
                >
                  复制 OCS 配置
                </el-button>
              </template>
              <el-button
                v-if="row.status !== 'revoked'"
                link
                type="primary"
                @click="openEdit(row)"
              >
                编辑
              </el-button>
              <el-button
                link
                type="danger"
                @click="remove(row)"
              >
                删除
              </el-button>
            </div>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="暂无 API Key，点击右上角创建" />
        </template>
      </el-table>
    </div>

    <!-- 创建弹窗 -->
    <el-dialog v-model="createVisible" title="创建 API Key" width="440px">
      <el-form label-position="top">
        <el-form-item label="API Key 名称">
          <el-input v-model="newDescription" placeholder="例如：宿舍台式机浏览器扩展" maxlength="64" />
        </el-form-item>
        <el-form-item label="额度设置 (-1 表示无限制)">
          <el-input-number v-model="newQuotaLimit" :min="-1" style="width: 100%" />
        </el-form-item>
        <el-form-item label="低信任度不作答">
          <el-switch v-model="newRejectLowConfidence" />
        </el-form-item>
        <el-form-item label="最低作答置信度 (0 表示使用系统配置)">
          <el-input-number
            v-model="newMinAnswerConfidence"
            :min="0"
            :max="1"
            :step="0.01"
            :precision="2"
            style="width: 100%"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="submitCreate">创建</el-button>
      </template>
    </el-dialog>

    <!-- 编辑弹窗 -->
    <el-dialog v-model="editVisible" title="编辑 API Key" width="440px">
      <el-form label-position="top" :disabled="updating || statusChanging">
        <el-form-item label="API Key 名称">
          <el-input v-model="editForm.description" placeholder="请输入描述" maxlength="64" />
        </el-form-item>
        <el-form-item label="额度设置 (-1 表示无限制)">
          <el-input-number v-model="editForm.quota_limit" :min="-1" style="width: 100%" />
        </el-form-item>
        <el-form-item label="低信任度不作答">
          <el-switch v-model="editForm.reject_low_confidence" />
        </el-form-item>
        <el-form-item label="最低作答置信度 (0 表示使用系统配置)">
          <el-input-number
            v-model="editForm.min_answer_confidence"
            :min="0"
            :max="1"
            :step="0.01"
            :precision="2"
            style="width: 100%"
          />
        </el-form-item>
      </el-form>
      <div
        v-if="editForm.status === 'revoked'"
        class="mt-2 rounded-lg border border-danger/30 bg-danger/5 p-3"
      >
        <div class="text-sm font-medium text-ink">API Key 已永久吊销</div>
        <div class="mt-1 text-xs text-ink-muted">已吊销的密钥不能重新启用。需要继续使用时，请创建新的 API Key。</div>
      </div>
      <div
        v-else
        class="mt-2 flex items-center justify-between gap-4 rounded-lg border p-3"
        :class="editForm.status === 'active' ? 'border-danger/30 bg-danger/5' : 'border-line bg-card-soft'"
      >
        <div class="min-w-0">
          <div class="text-sm font-medium text-ink">API Key 访问状态</div>
          <div class="mt-1 text-xs text-ink-muted">
            {{ editForm.status === 'active' ? '禁用后，使用该密钥的客户端将立即无法访问服务。' : '启用后，该密钥可以继续用于 OCS 和 API 调用。' }}
          </div>
        </div>
        <el-button
          :type="editForm.status === 'active' ? 'danger' : 'success'"
          plain
          :loading="statusChanging"
          @click="setEditingTokenEnabled"
        >
          {{ editForm.status === 'active' ? '禁用' : '启用' }}
        </el-button>
      </div>
      <template #footer>
        <el-button :disabled="statusChanging" @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="updating" :disabled="statusChanging" @click="submitUpdate">
          保存
        </el-button>
      </template>
    </el-dialog>

    <!-- 明文展示弹窗 -->
    <el-dialog v-model="revealVisible" title="请妥善保存你的 API Key" width="560px">
      <div class="mb-2 text-sm font-medium text-ink-soft">API Key</div>
      <div class="mb-4 flex items-center gap-2">
        <code class="flex-1 break-all rounded-lg bg-canvas px-3 py-2 text-sm text-ink">{{ revealToken }}</code>
        <el-button :icon="'CopyDocument'" @click="copy(revealToken)">复制</el-button>
      </div>
      <div class="mb-2 flex items-center justify-between">
        <span class="text-sm font-medium text-ink-soft">OCS 接入配置</span>
        <el-button link type="primary" size="small" @click="copy(ocsConfigText(revealConfig))">
          复制配置
        </el-button>
      </div>
      <pre
        class="max-h-60 overflow-auto rounded-lg bg-[#0f172a] p-3 text-xs leading-relaxed text-slate-200"
      >{{ ocsConfigText(revealConfig) }}</pre>
      <template #footer>
        <el-button type="primary" @click="revealVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <OcsConfigCopyDialog ref="ocsConfigDialog" />
  </div>
</template>
