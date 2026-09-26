<script setup lang="ts">
/** 复制 OCS 接入配置弹窗：处理 API Key 选择与无状态分享链接。 */
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { tokenApi } from '@/api/endpoints'
import { ApiException } from '@/api/http'
import type { ApiToken, OcsConfig } from '@/api/types'

const router = useRouter()

const configVisible = ref(false)
const tokenSelectVisible = ref(false)
const selectedTokenId = ref('')
const currentTokenId = ref('')
const config = ref<OcsConfig | null>(null)
const selectableTokens = ref<ApiToken[]>([])
const requiresTokenReplacement = ref(false)
const shareUrl = ref('')
const sharing = ref(false)

async function open(tokenId?: string) {
  try {
    requiresTokenReplacement.value = false
    shareUrl.value = ''
    const res = await tokenApi.ocsConfig(tokenId)
    if (res.mode === 'select_token') {
      selectableTokens.value = res.token_options || []
      selectedTokenId.value = selectableTokens.value[0]?.token_id || ''
      tokenSelectVisible.value = true
      return
    }

    const finalTokenId = res.token_id || tokenId || ''
    if (!finalTokenId) {
      throw new ApiException('请先创建密钥', 'TOKEN_REQUIRED', 404)
    }
    currentTokenId.value = finalTokenId
    requiresTokenReplacement.value = Boolean(
      res.requires_token_replacement || !res.token_option?.is_recoverable,
    )
    config.value = res.ocs_config || null
    configVisible.value = true
  } catch (err) {
    const apiError = err instanceof ApiException ? err : null
    if (apiError?.code === 'TOKEN_REQUIRED' || apiError?.code === 'TOKEN_NOT_FOUND') {
      ElMessage.warning(apiError.message || '请先创建密钥')
      router.push('/tokens')
      return
    }
    ElMessage.error(apiError?.message || '生成 OCS 配置失败')
  }
}

async function confirmTokenSelection() {
  tokenSelectVisible.value = false
  if (!selectedTokenId.value) {
    ElMessage.warning('请选择密钥')
    return
  }
  await open(selectedTokenId.value)
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

async function generateShareLink() {
  if (!currentTokenId.value) {
    ElMessage.warning('请先选择一个 API Key')
    return
  }
  if (requiresTokenReplacement.value) {
    ElMessage.warning('该 API Key 无法恢复完整密钥，请新建一个 API Key')
    return
  }
  sharing.value = true
  try {
    const res = await tokenApi.shareLink(currentTokenId.value)
    shareUrl.value = res.share_url
    await copy(res.share_url)
  } catch (err) {
    ElMessage.error(err instanceof ApiException ? err.message : '生成分享链接失败')
  } finally {
    sharing.value = false
  }
}

async function copyShareLink() {
  await copy(shareUrl.value)
}

defineExpose({ open })
</script>

<template>
  <el-dialog v-model="tokenSelectVisible" title="选择密钥" width="420px">
    <el-form label-position="top">
      <el-form-item label="请选择要复制的密钥">
        <el-select v-model="selectedTokenId" class="w-full" placeholder="请选择密钥">
          <el-option
            v-for="token in selectableTokens"
            :key="token.token_id"
            :label="token.description || token.key_mask"
            :value="token.token_id"
          />
        </el-select>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="tokenSelectVisible = false">取消</el-button>
      <el-button type="primary" @click="confirmTokenSelection">确认</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="configVisible" title="复制 OCS 配置" width="560px">
    <el-alert
      v-if="requiresTokenReplacement"
      type="warning"
      :closable="false"
      class="mb-4"
      title="该 API Key 无法恢复完整密钥。"
      description="配置中的 {{TOKEN}} 是占位符。请新建 API Key 后重新复制，或手动替换为已保存的密钥。"
    />
    <el-alert
      v-else
      type="info"
      :closable="false"
      class="mb-4"
      title="配置已按当前选择的 API Key 生成，可直接粘贴到 OCS 的题库配置中。"
    />
    <div class="mb-2 flex items-center justify-between">
      <span class="text-sm font-medium text-ink-soft">OCS 接入配置</span>
      <el-button
        v-if="config"
        link
        type="primary"
        size="small"
        @click="copy(JSON.stringify(config, null, 2))"
      >
        复制配置
      </el-button>
    </div>
    <pre
      v-if="config"
      class="max-h-[60vh] overflow-auto rounded-lg bg-[#0f172a] p-3 text-xs leading-relaxed text-slate-200"
    >{{ JSON.stringify(config, null, 2) }}</pre>
    <div v-if="shareUrl" class="mt-4 rounded-lg border border-brand-500/30 bg-brand-500/5 p-3">
      <div class="mb-2 text-xs font-medium text-ink-soft">分享链接</div>
      <div class="flex items-center gap-2">
        <el-input :model-value="shareUrl" readonly />
        <el-button :icon="'CopyDocument'" @click="copyShareLink">复制</el-button>
      </div>
      <div class="mt-2 text-xs text-ink-muted">链接不会过期，禁用或删除此 API Key 后会立即失效。</div>
    </div>
    <template #footer>
      <el-button :disabled="requiresTokenReplacement" :loading="sharing" @click="generateShareLink">
        分享链接
      </el-button>
      <el-button type="primary" @click="configVisible = false">我已复制</el-button>
    </template>
  </el-dialog>
</template>
