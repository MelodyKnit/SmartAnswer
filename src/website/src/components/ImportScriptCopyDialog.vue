<script setup lang="ts">
/** 复制导入脚本弹窗：统一处理 Token 选择、浏览器本地明文替换和 OCS 配置展示。 */
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { tokenApi } from '@/api/endpoints'
import { ApiException, getApiTokenSecret } from '@/api/http'
import type { ApiToken, OcsConfig } from '@/api/types'

const router = useRouter()

const importScriptVisible = ref(false)
const tokenSelectVisible = ref(false)
const selectedTokenId = ref('')
const importScriptContent = ref('')
const importScriptConfig = ref<OcsConfig | null>(null)
const selectableTokens = ref<ApiToken[]>([])
const isTokenSecretMissing = ref(false)

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

async function open(tokenId?: string) {
  try {
    isTokenSecretMissing.value = false
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
    importScriptContent.value = replaceTokenPlaceholder(res.script || '', finalTokenId)
    importScriptConfig.value = res.ocs_config ? fillConfigToken(res.ocs_config, finalTokenId) : null
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
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.warning('复制失败，请手动复制')
  }
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
      title="提示：系统检测到 API Key 存在，但当前浏览器未缓存其原始明文。出于安全考虑，系统不会在服务器端保存明文密钥。"
      description="您仍可正常复制，但复制后需手动将代码中的 YOUR_API_KEY_HERE 替换为您保存的实际 API Key，或在「API Key 管理」页面重新创建一个新密钥。"
    />
    <el-alert
      v-else
      type="info"
      :closable="false"
      class="mb-4"
      title="该脚本已按你当前选择的密钥生成，可直接复制使用。"
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
    <template #footer>
      <el-button type="primary" @click="importScriptVisible = false">我已复制</el-button>
    </template>
  </el-dialog>
</template>
