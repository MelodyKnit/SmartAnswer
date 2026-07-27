<script setup lang="ts">
/** 公开 GitHub Release 状态面板；部署始终由 GitHub Actions 负责。 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { projectUpdateApi } from '@/api/endpoints'
import { ApiException } from '@/api/http'
import type { ProjectUpdateStatus } from '@/api/types'
import { formatDateTime } from '@/utils/format'

const status = ref<ProjectUpdateStatus | null>(null)
const loading = ref(false)
const checking = ref(false)

const stateLabel = computed(() => {
  const labels: Record<string, string> = {
    unavailable: '来源未声明',
    idle: '可检查',
    failed: '检查失败',
  }
  return labels[status.value?.state || 'idle'] || '未知状态'
})

const stateType = computed(() => {
  if (status.value?.state === 'failed') return 'danger'
  if (status.value?.state === 'unavailable') return 'warning'
  return 'info'
})

async function loadStatus(showError = false) {
  loading.value = true
  try {
    status.value = (await projectUpdateApi.status()).update
  } catch (error) {
    if (showError) {
      ElMessage.error(error instanceof ApiException ? error.message : '加载发布状态失败')
    }
  } finally {
    loading.value = false
  }
}

async function checkUpdates() {
  checking.value = true
  try {
    const response = await projectUpdateApi.check()
    status.value = response.update
    ElMessage.success(response.update.has_update ? '发现新 Release' : '当前已是最新 Release')
  } catch (error) {
    ElMessage.error(error instanceof ApiException ? error.message : '检查 Release 失败')
  } finally {
    checking.value = false
  }
}

onMounted(() => void loadStatus())
</script>

<template>
  <div v-loading="loading" class="mt-4 border-t border-line pt-5">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div class="flex items-center gap-3">
        <span class="text-sm font-semibold text-ink">发布状态</span>
        <el-tag :type="stateType" effect="plain">{{ stateLabel }}</el-tag>
      </div>
      <el-button :loading="checking" :disabled="!status?.available" @click="checkUpdates">
        检查 Release
      </el-button>
    </div>

    <div class="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <div class="rounded-lg border border-line bg-card-soft px-4 py-3">
        <div class="text-xs text-ink-muted">当前版本</div>
        <div class="mt-1 font-medium text-ink">
          {{ status?.current_version ? `v${status.current_version}` : '—' }}
        </div>
      </div>
      <div class="rounded-lg border border-line bg-card-soft px-4 py-3">
        <div class="text-xs text-ink-muted">最新 Release</div>
        <div class="mt-1 font-medium text-ink">
          {{ status?.latest_version ? `v${status.latest_version}` : '—' }}
        </div>
      </div>
      <div class="rounded-lg border border-line bg-card-soft px-4 py-3">
        <div class="text-xs text-ink-muted">最近检查</div>
        <div class="mt-1 text-sm text-ink">
          {{ status?.checked_at ? formatDateTime(status.checked_at) : '—' }}
        </div>
      </div>
      <div class="rounded-lg border border-line bg-card-soft px-4 py-3">
        <div class="text-xs text-ink-muted">来源仓库</div>
        <div class="mt-1 truncate text-sm text-ink">{{ status?.repository || '—' }}</div>
      </div>
    </div>

    <div v-if="status?.message || status?.error" class="mt-4 rounded-lg border border-line px-4 py-3">
      <div class="text-sm text-ink">{{ status?.message }}</div>
      <div v-if="status?.error" class="mt-1 text-sm text-danger">{{ status.error }}</div>
      <div class="mt-2 text-xs text-ink-muted">
        正式部署由 GitHub Actions 的 production 环境审批后执行，应用不会保存 GitHub 凭据或触发部署。
      </div>
    </div>

    <div v-if="status?.release" class="mt-4 flex flex-wrap items-start justify-between gap-3 border-t border-line pt-4">
      <div class="min-w-0">
        <div class="text-sm font-medium text-ink">
          {{ status.release.name || `v${status.release.version}` }}
        </div>
        <div class="mt-1 text-xs text-ink-muted">{{ status.release.published_at || '未提供发布时间' }}</div>
      </div>
      <a
        v-if="status.release.html_url"
        :href="status.release.html_url"
        target="_blank"
        rel="noopener noreferrer"
        class="text-sm text-primary hover:underline"
      >
        查看 Release
      </a>
    </div>
  </div>
</template>
