<script setup lang="ts">
/** API Key 管理：列表 / 创建（一次性展示明文 + OCS 配置）/ 吊销与删除。用户级，仅管理自己的令牌。 */
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { tokenApi } from '@/api/endpoints'
import type { ApiToken, OcsConfig } from '@/api/types'
import { ApiException, getApiTokenSecret, removeApiTokenSecret, setApiTokenSecret } from '@/api/http'
import { formatDateTime } from '@/utils/format'
import PageHeader from '@/components/PageHeader.vue'

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
const editForm = ref({
  token_id: '',
  description: '',
  quota_limit: -1,
  reject_low_confidence: false,
  min_answer_confidence: 0,
})

const revealVisible = ref(false)
const revealToken = ref('')
const revealConfig = ref<OcsConfig | null>(null)

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
    setApiTokenSecret(res.token_info.token_id, res.token)
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

async function revoke(token: ApiToken) {
  const confirmed = await ElMessageBox.confirm(
    `确定吊销令牌「${token.description || token.key_mask}」吗？吊销后使用该令牌的客户端将立即失效。`,
    '吊销确认',
    { type: 'warning', confirmButtonText: '吊销', cancelButtonText: '取消' },
  )
    .then(() => true)
    .catch(() => false)
  if (!confirmed) return
  try {
    await tokenApi.revoke(token.token_id)
    removeApiTokenSecret(token.token_id)
    ElMessage.success('已吊销')
    await load()
  } catch (err) {
    ElMessage.error(err instanceof ApiException ? err.message : '操作失败')
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
    removeApiTokenSecret(token.token_id)
    ElMessage.success('已删除')
    await load()
  } catch (err) {
    ElMessage.error(err instanceof ApiException ? err.message : '删除失败')
  }
}

async function copyToken(token: ApiToken) {
  const secret = getApiTokenSecret(token.token_id)
  if (secret) {
    await copy(secret)
  } else {
    try {
      await navigator.clipboard.writeText(token.key_mask)
      ElMessage.success('完整密钥未缓存，已复制掩码')
    } catch {
      ElMessage.warning('复制失败，请手动复制')
    }
  }
}

function openEdit(token: ApiToken) {
  editForm.value = {
    token_id: token.token_id,
    description: token.description || '',
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

const ocsConfigText = (config: OcsConfig | null) =>
  config ? JSON.stringify(config, null, 2) : ''

onMounted(load)
</script>

<template>
  <div>
    <PageHeader title="API Key 管理" description="创建并管理用于 OCS 等客户端接入答题服务的 API 令牌。">
      <template #actions>
        <el-button type="primary" :icon="'Plus'" @click="openCreate">创建 API Key</el-button>
      </template>
    </PageHeader>

    <div class="app-card p-1">
      <el-table v-loading="loading" :data="tokens" style="width: 100%">
        <el-table-column label="描述" min-width="160">
          <template #default="{ row }">
            <span class="font-medium text-ink">{{ row.description || '未命名令牌' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="密钥" min-width="210">
          <template #default="{ row }">
            <div class="inline-flex items-center gap-1.5">
              <code
                class="cursor-pointer rounded bg-canvas px-2 py-1 text-xs text-ink-soft hover:bg-canvas-hover"
                title="点击复制"
                @click="copyToken(row)"
              >
                {{ row.key_mask }}
              </code>
              <el-button
                circle
                text
                size="small"
                icon="CopyDocument"
                title="点击复制"
                @click="copyToken(row)"
              />
            </div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === 'active' ? 'success' : 'info'" size="small">
              {{ row.status === 'active' ? '正常' : '已吊销' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="调用次数" width="90" prop="usage_count" />
        <el-table-column label="已用 / 限额" width="160">
          <template #default="{ row }">
            <span class="text-ink-soft">{{ row.quota_used }}</span>
            <span class="text-ink-muted"> / </span>
            <span :class="row.quota_limit === -1 ? 'text-ink-muted' : 'text-ink'">
              {{ row.quota_limit === -1 ? '无限制' : `${row.quota_limit} 积分` }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="低信任度" width="130">
          <template #default="{ row }">
            <el-tag :type="row.reject_low_confidence ? 'warning' : 'info'" size="small">
              {{ row.reject_low_confidence ? `拒答 ${row.min_answer_confidence || '系统'}` : '允许' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="最近使用" width="170">
          <template #default="{ row }">{{ formatDateTime(row.last_used_at) }}</template>
        </el-table-column>
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="150" align="right">
          <template #default="{ row }">
            <div class="flex justify-end gap-2">
              <template v-if="row.status === 'active'">
                <el-button
                  link
                  type="primary"
                  @click="openEdit(row)"
                >
                  编辑
                </el-button>
                <el-button
                  link
                  type="danger"
                  @click="revoke(row)"
                >
                  吊销
                </el-button>
              </template>
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
        <el-form-item label="令牌描述">
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
      <el-form label-position="top">
        <el-form-item label="令牌描述">
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
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="updating" @click="submitUpdate">保存</el-button>
      </template>
    </el-dialog>

    <!-- 明文展示弹窗（仅此一次） -->
    <el-dialog v-model="revealVisible" title="请妥善保存你的 API Key" width="560px">
      <el-alert
        type="warning"
        :closable="false"
        class="mb-4"
        title="出于安全考虑，完整密钥仅在此展示一次，关闭后无法再次查看。"
      />
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
        <el-button type="primary" @click="revealVisible = false">我已保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>
