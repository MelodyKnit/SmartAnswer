<script setup lang="ts">
/** 复制导入脚本弹窗：处理 Key 选择、脚本复制和无状态分享链接。 */
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { tokenApi } from '@/api/endpoints'
import { ApiException } from '@/api/http'
import type { ApiToken, OcsConfig } from '@/api/types'

const router = useRouter()

const importScriptVisible = ref(false)
const tokenSelectVisible = ref(false)
const selectedTokenId = ref('')
const currentTokenId = ref('')
const importScriptContent = ref('')
const importScriptConfig = ref<OcsConfig | null>(null)
const selectableTokens = ref<ApiToken[]>([])
const isTokenSecretMissing = ref(false)
const shareUrl = ref('')
const sharing = ref(false)

async function open(tokenId?: string) {
  try {
    isTokenSecretMissing.value = false
    shareUrl.value = ''
    const res = await tokenApi.importScript(tokenId)
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
    isTokenSecretMissing.value = Boolean(res.requires_local_secret || !res.token_option?.is_recoverable)
    importScriptContent.value = res.script || ''
    importScriptConfig.value = res.ocs_config || null
    importScriptVisible.value = true
  } catch (err) {
    const apiError = err instanceof ApiException ? err : null
    if (apiError?.code === 'TOKEN_REQUIRED' || apiError?.code === 'TOKEN_NOT_FOUND') {
      ElMessage.warning(apiError.message || '请先创建密钥')
      router.push('/tokens')
      return
    }
    ElMessage.error(apiError?.message || '复制导入脚本失败')
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
  if (isTokenSecretMissing.value) {
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

  <el-dialog v-model="importScriptVisible" title="复制导入脚本" width="560px">
    <el-alert
      v-if="isTokenSecretMissing"
      type="warning"
      :closable="false"
      class="mb-4"
      title="提示：该 API Key 无法恢复完整密钥。"
      description="脚本和配置中保留了 {{TOKEN}} 占位符。请新建一个 API Key 后重新复制导入，或手动替换为你保存的实际密钥。"
    />
    <el-alert
      v-else
      type="info"
      :closable="false"
      class="mb-4"
      title="该脚本已按你当前选择的密钥生成，可直接复制使用。图片题请优先安装并启用下方导入脚本，不要只复制 OCS 配置。"
    />
    <div class="mb-2 flex items-center justify-between">
      <span class="text-sm font-medium text-ink-soft">导入脚本</span>
      <el-button link type="primary" size="small" @click="copy(importScriptContent)">复制脚本</el-button>
    </div>
    <pre class="max-h-60 overflow-auto rounded-lg bg-[#0f172a] p-3 text-xs leading-relaxed text-slate-200">{{ importScriptContent }}</pre>
    <div class="mb-2 mt-4 flex items-center justify-between">
      <span class="text-sm font-medium text-ink-soft">OCS 接入配置</span>
      <el-button
        v-if="importScriptConfig"
        link
        type="primary"
        size="small"
        @click="copy(JSON.stringify(importScriptConfig, null, 2))"
      >
        复制配置
      </el-button>
    </div>
    <pre
      v-if="importScriptConfig"
      class="max-h-60 overflow-auto rounded-lg bg-[#0f172a] p-3 text-xs leading-relaxed text-slate-200"
    >{{ JSON.stringify(importScriptConfig, null, 2) }}</pre>
    <div v-if="shareUrl" class="mt-4 rounded-lg border border-brand-500/30 bg-brand-500/5 p-3">
      <div class="mb-2 text-xs font-medium text-ink-soft">分享链接</div>
      <div class="flex items-center gap-2">
        <el-input :model-value="shareUrl" readonly />
        <el-button :icon="'CopyDocument'" @click="copyShareLink">复制</el-button>
      </div>
      <div class="mt-2 text-xs text-ink-muted">链接不会过期，吊销或删除此 API Key 后会立即失效。</div>
    </div>
    <template #footer>
      <el-button :disabled="isTokenSecretMissing" :loading="sharing" @click="generateShareLink">分享链接</el-button>
      <el-button type="primary" @click="importScriptVisible = false">我已复制</el-button>
    </template>
  </el-dialog>
</template>
