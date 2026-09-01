<script setup lang="ts">
/** 无状态 API Key 分享页：Key 只从浏览器 fragment 读取，不发送给服务端。 */
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { shareApi } from '@/api/endpoints'
import { ApiException } from '@/api/http'
import type { OcsConfig } from '@/api/types'

const loading = ref(true)
const error = ref('')
const script = ref('')
const ocsConfig = ref<OcsConfig | null>(null)

function readFragmentKey(): string {
  const hash = window.location.hash.startsWith('#')
    ? window.location.hash.slice(1)
    : window.location.hash
  return new URLSearchParams(hash).get('key')?.trim() || ''
}

function replaceToken(value: unknown, token: string): unknown {
  if (typeof value === 'string') return value.replaceAll('{{TOKEN}}', token)
  if (Array.isArray(value)) return value.map((item) => replaceToken(item, token))
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [key, replaceToken(item, token)]),
    )
  }
  return value
}

async function load() {
  loading.value = true
  error.value = ''
  const token = readFragmentKey()
  if (!token) {
    error.value = '分享链接缺少 API Key'
    loading.value = false
    return
  }

  try {
    // 只请求不含 Key 的模板，fragment 不会被浏览器发送到 HTTP 服务端。
    const template = await shareApi.apikeyTemplate()
    script.value = template.script.replaceAll('{{TOKEN}}', token)
    ocsConfig.value = replaceToken(template.ocs_config, token) as OcsConfig
  } catch (err) {
    error.value = err instanceof ApiException ? err.message : '加载分享模板失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

async function copyScript() {
  try {
    await navigator.clipboard.writeText(script.value)
    ElMessage.success('已复制脚本')
  } catch {
    ElMessage.error('复制失败')
  }
}

async function copyConfig() {
  if (!ocsConfig.value) return
  try {
    await navigator.clipboard.writeText(JSON.stringify(ocsConfig.value, null, 2))
    ElMessage.success('已复制配置')
  } catch {
    ElMessage.error('复制失败')
  }
}

onMounted(load)
</script>

<template>
  <div class="min-h-screen bg-canvas-deep">
    <div class="mx-auto max-w-5xl px-6 py-12">
      <div v-if="loading" class="flex items-center justify-center py-24">
        <div class="text-center">
          <div class="mb-3 inline-block h-8 w-8 animate-spin rounded-full border-4 border-accent/20 border-t-accent" />
          <div class="text-sm text-ink-muted">加载中...</div>
        </div>
      </div>

      <div v-else-if="error" class="py-24 text-center">
        <div class="mb-4 text-6xl">!</div>
        <div class="mb-2 text-lg font-medium text-ink">{{ error }}</div>
        <div class="text-sm text-ink-muted">请让链接提供者重新生成配置，或检查 API Key 是否已被吊销或删除。</div>
      </div>

      <div v-else class="space-y-6">
        <div class="rounded-2xl bg-canvas-raised p-6">
          <div class="mb-1 text-2xl font-semibold text-ink">API Key 分享配置</div>
          <div class="text-sm text-ink-muted">复制下方内容后，在对应客户端中完成配置。</div>
        </div>

        <div class="rounded-2xl bg-canvas-raised p-6">
          <div class="mb-3 flex items-center justify-between gap-3">
            <div class="text-lg font-medium text-ink">用户脚本</div>
            <button
              class="rounded-full bg-accent px-5 py-2 text-sm font-medium text-canvas-deep transition-transform hover:scale-105 active:scale-95"
              @click="copyScript"
            >
              复制脚本
            </button>
          </div>
          <div class="mb-3 text-xs text-ink-muted">脚本已在当前浏览器中填入分享的 API Key，请勿继续转发。</div>
          <pre class="max-h-[400px] overflow-auto rounded-lg bg-canvas-deep p-4 text-xs text-ink-soft">{{ script }}</pre>
        </div>

        <div class="rounded-2xl bg-canvas-raised p-6">
          <div class="mb-3 flex items-center justify-between gap-3">
            <div class="text-lg font-medium text-ink">OCS 接入配置</div>
            <button
              class="rounded-full bg-accent px-5 py-2 text-sm font-medium text-canvas-deep transition-transform hover:scale-105 active:scale-95"
              @click="copyConfig"
            >
              复制配置
            </button>
          </div>
          <div class="mb-3 text-xs text-ink-muted">在 OCS 设置中粘贴此配置即可使用题库服务。</div>
          <pre class="overflow-auto rounded-lg bg-canvas-deep p-4 text-xs text-ink-soft">{{ JSON.stringify(ocsConfig, null, 2) }}</pre>
        </div>

        <div class="rounded-2xl border border-amber-500/30 bg-amber-500/5 p-4">
          <div class="mb-1 text-sm font-medium text-ink">注意</div>
          <div class="text-xs text-ink-muted">
            此配置包含 API Key。链接本身不会过期，但对应 API Key 被吊销或删除后，配置会立即失效。
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
