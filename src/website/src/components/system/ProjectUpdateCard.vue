<script setup lang="ts">
/** 私有 GitHub Release 更新状态与人工确认入口。 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { projectUpdateApi } from '@/api/endpoints'
import { ApiException } from '@/api/http'
import type {
  ProjectUpdateOperation,
  ProjectUpdateState,
  ProjectUpdateStatus,
} from '@/api/types'
import { formatDateTime } from '@/utils/format'

const status = ref<ProjectUpdateStatus | null>(null)
const operation = ref<ProjectUpdateOperation | null>(null)
const loading = ref(false)
const checking = ref(false)
const applying = ref(false)
let pollTimer: ReturnType<typeof setTimeout> | null = null
let stopped = false

const activeStates = new Set<ProjectUpdateState>([
  'queued',
  'checking',
  'downloading',
  'backing_up',
  'deploying',
  'verifying',
  'rolling_back',
])

const isBusy = computed(() => {
  const state = operation.value?.state || status.value?.state
  return state ? activeStates.has(state) : false
})

const stateLabel = computed(() => {
  const state = operation.value?.state || status.value?.state || 'idle'
  const labels: Record<ProjectUpdateState, string> = {
    idle: '已就绪',
    disabled: '未启用',
    unconfigured: '未配置',
    queued: '等待执行',
    checking: '检查版本',
    downloading: '下载镜像',
    backing_up: '备份数据',
    deploying: '切换版本',
    verifying: '健康检查',
    rolling_back: '自动回滚',
    succeeded: '更新成功',
    failed: '执行失败',
    rolled_back: '已回滚',
    rollback_failed: '回滚失败',
  }
  return labels[state]
})

const stateType = computed(() => {
  const state = operation.value?.state || status.value?.state
  if (state === 'succeeded') return 'success'
  if (state === 'failed' || state === 'rollback_failed') return 'danger'
  if (state === 'rolled_back' || state === 'unconfigured' || state === 'disabled') return 'warning'
  return 'info'
})

const canApply = computed(
  () => Boolean(status.value?.configured && status.value.has_update && !isBusy.value),
)

async function loadStatus(showError = false) {
  loading.value = true
  try {
    const response = await projectUpdateApi.status()
    status.value = response.update
    if (response.update.operation_id && activeStates.has(response.update.state)) {
      operation.value = {
        operation_id: response.update.operation_id,
        action: response.update.action,
        state: response.update.state,
        expected_version: response.update.expected_version,
        created_at: response.update.created_at,
        updated_at: response.update.updated_at,
        message: response.update.message,
        error: response.update.error,
      }
      schedulePoll()
    }
  } catch (error) {
    if (showError) {
      ElMessage.error(error instanceof ApiException ? error.message : '加载版本状态失败')
    }
  } finally {
    loading.value = false
  }
}

async function checkUpdates() {
  checking.value = true
  try {
    const response = await projectUpdateApi.check()
    operation.value = response.operation
    schedulePoll(500)
  } catch (error) {
    ElMessage.error(error instanceof ApiException ? error.message : '检查更新失败')
  } finally {
    checking.value = false
  }
}

async function applyUpdate() {
  const version = status.value?.latest_version
  if (!version) return
  try {
    await ElMessageBox.confirm(
      `即将更新到 v${version}，服务会短暂重启；健康检查失败时将自动恢复上一版本。`,
      '确认更新',
      {
        confirmButtonText: '开始更新',
        cancelButtonText: '取消',
        type: 'warning',
      },
    )
  } catch {
    return
  }

  applying.value = true
  try {
    const response = await projectUpdateApi.apply(version)
    operation.value = response.operation
    schedulePoll(500)
  } catch (error) {
    ElMessage.error(error instanceof ApiException ? error.message : '提交更新失败')
  } finally {
    applying.value = false
  }
}

function schedulePoll(delay = 2000) {
  if (stopped || !operation.value?.operation_id) return
  if (pollTimer) clearTimeout(pollTimer)
  pollTimer = setTimeout(pollOperation, delay)
}

async function pollOperation() {
  const operationId = operation.value?.operation_id
  if (!operationId || stopped) return
  try {
    const response = await projectUpdateApi.operation(operationId)
    operation.value = response.operation
    if (activeStates.has(response.operation.state)) {
      schedulePoll()
      return
    }
    await loadStatus()
    if (response.operation.state === 'succeeded') {
      ElMessage.success(response.operation.message || '版本更新完成')
    } else if (response.operation.state === 'rolled_back') {
      ElMessage.warning(response.operation.message || '新版本不可用，已自动回滚')
    } else if (response.operation.error) {
      ElMessage.error(response.operation.error)
    }
  } catch {
    // 更新期间容器会短暂重启，保留任务并继续轮询。
    schedulePoll(3000)
  }
}

onMounted(() => loadStatus())
onBeforeUnmount(() => {
  stopped = true
  if (pollTimer) clearTimeout(pollTimer)
})
</script>

<template>
  <div v-loading="loading" class="app-card p-6">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div class="flex items-center gap-3">
        <h3 class="text-base font-semibold text-ink">版本更新</h3>
        <el-tag :type="stateType" effect="plain">{{ stateLabel }}</el-tag>
      </div>
      <div class="flex items-center gap-2">
        <el-button :loading="checking" :disabled="isBusy" @click="checkUpdates">
          检查更新
        </el-button>
        <el-button
          type="primary"
          :loading="applying"
          :disabled="!canApply"
          @click="applyUpdate"
        >
          更新到 v{{ status?.latest_version || '—' }}
        </el-button>
      </div>
    </div>

    <div class="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <div class="rounded-md border border-line bg-card-soft px-4 py-3">
        <div class="text-xs text-ink-muted">当前版本</div>
        <div class="mt-1 font-medium text-ink">v{{ status?.current_version || '—' }}</div>
      </div>
      <div class="rounded-md border border-line bg-card-soft px-4 py-3">
        <div class="text-xs text-ink-muted">最新版本</div>
        <div class="mt-1 font-medium text-ink">v{{ status?.latest_version || '—' }}</div>
      </div>
      <div class="rounded-md border border-line bg-card-soft px-4 py-3">
        <div class="text-xs text-ink-muted">构建提交</div>
        <div class="mt-1 font-mono text-sm text-ink">{{ status?.build_sha?.slice(0, 12) || '—' }}</div>
      </div>
      <div class="rounded-md border border-line bg-card-soft px-4 py-3">
        <div class="text-xs text-ink-muted">最近检查</div>
        <div class="mt-1 text-sm text-ink">
          {{ status?.checked_at ? formatDateTime(status.checked_at) : '—' }}
        </div>
      </div>
    </div>

    <div
      v-if="operation || status?.message || status?.error"
      class="mt-4 rounded-md border border-line px-4 py-3"
    >
      <div class="text-sm font-medium text-ink">
        {{ operation?.message || status?.message }}
      </div>
      <div v-if="operation?.error || status?.error" class="mt-1 text-sm text-danger">
        {{ operation?.error || status?.error }}
      </div>
    </div>

    <div v-if="status?.release" class="mt-4 border-t border-line pt-4">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div class="font-medium text-ink">{{ status.release.name || `v${status.latest_version}` }}</div>
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
      <div
        v-if="status.release.body"
        class="mt-3 max-h-40 overflow-auto whitespace-pre-wrap rounded-md bg-card-soft px-4 py-3 text-sm leading-6 text-ink-soft"
      >
        {{ status.release.body }}
      </div>
    </div>
  </div>
</template>
