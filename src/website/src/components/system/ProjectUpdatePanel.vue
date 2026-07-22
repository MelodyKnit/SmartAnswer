<script setup lang="ts">
/** GitHub Release 检查和已发布版本部署状态面板。 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { projectUpdateApi } from '@/api/endpoints'
import { ApiException } from '@/api/http'
import type { ProjectUpdateOperation, ProjectUpdateStatus } from '@/api/types'
import { formatDateTime } from '@/utils/format'

const props = defineProps<{ configurationVersion: number }>()

const status = ref<ProjectUpdateStatus | null>(null)
const operation = ref<ProjectUpdateOperation | null>(null)
const loading = ref(false)
const checking = ref(false)
const applying = ref(false)
let pollTimer: ReturnType<typeof setTimeout> | null = null
let stopped = false

const activeStates = new Set(['queued', 'running'])

const effectiveState = computed(() => operation.value?.state || status.value?.state || 'idle')
const isBusy = computed(() => activeStates.has(effectiveState.value))
const canApply = computed(
  () => Boolean(status.value?.enabled && status.value?.configured && status.value?.has_update && !isBusy.value),
)
const updateButtonLabel = computed(() =>
  status.value?.has_update && status.value.latest_version
    ? `更新到 v${status.value.latest_version}`
    : '暂无可用更新',
)

const stateLabel = computed(() => {
  const labels: Record<string, string> = {
    disabled: '未启用',
    unconfigured: '待配置',
    idle: '已就绪',
    queued: '等待调度',
    running: '部署中',
    succeeded: '部署完成',
    failed: '部署失败',
  }
  return labels[effectiveState.value] || '未知状态'
})

const stateType = computed(() => {
  if (effectiveState.value === 'succeeded') return 'success'
  if (effectiveState.value === 'failed') return 'danger'
  if (effectiveState.value === 'queued' || effectiveState.value === 'running') return 'warning'
  return 'info'
})

async function loadStatus(showError = false) {
  loading.value = true
  try {
    const response = await projectUpdateApi.status()
    status.value = response.update
    operation.value = response.update.operation || null
    if (operation.value && activeStates.has(operation.value.state)) schedulePoll()
  } catch (error) {
    if (showError) {
      ElMessage.error(error instanceof ApiException ? error.message : '加载项目更新状态失败')
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
    operation.value = response.update.operation || null
    ElMessage.success(response.update.has_update ? '发现可更新版本' : '当前已是最新版本')
  } catch (error) {
    ElMessage.error(error instanceof ApiException ? error.message : '检查项目更新失败')
  } finally {
    checking.value = false
  }
}

async function applyUpdate() {
  const version = status.value?.latest_version
  if (!version) return
  try {
    await ElMessageBox.confirm(
      `将通过 GitHub Actions 部署 v${version}。服务会短暂重启，健康检查失败时会自动回滚。`,
      '确认更新',
      { confirmButtonText: '开始更新', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  applying.value = true
  try {
    const response = await projectUpdateApi.apply(version)
    operation.value = response.operation
    schedulePoll(800)
  } catch (error) {
    ElMessage.error(error instanceof ApiException ? error.message : '提交更新任务失败')
  } finally {
    applying.value = false
  }
}

function schedulePoll(delay = 2500) {
  if (stopped || !operation.value || !activeStates.has(operation.value.state)) return
  if (pollTimer) clearTimeout(pollTimer)
  pollTimer = setTimeout(() => void pollOperation(), delay)
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
    if (response.operation.state === 'succeeded') ElMessage.success('项目更新已完成')
    if (response.operation.state === 'failed') ElMessage.error(response.operation.error || '项目更新失败')
  } catch {
    // 更新切换容器时请求会暂时中断，保留当前任务并延迟重新探测。
    schedulePoll(4000)
  }
}

watch(
  () => props.configurationVersion,
  () => void loadStatus(),
)

onMounted(() => void loadStatus())
onBeforeUnmount(() => {
  stopped = true
  if (pollTimer) clearTimeout(pollTimer)
})
</script>

<template>
  <div v-loading="loading" class="mt-6 border-t border-line pt-5">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div class="flex items-center gap-3">
        <span class="text-sm font-semibold text-ink">发布状态</span>
        <el-tag :type="stateType" effect="plain">{{ stateLabel }}</el-tag>
      </div>
      <div class="flex items-center gap-2">
        <el-button :loading="checking" :disabled="isBusy || !status?.enabled || !status?.configured" @click="checkUpdates">
          检查更新
        </el-button>
        <el-button type="primary" :loading="applying" :disabled="!canApply" @click="applyUpdate">
          {{ updateButtonLabel }}
        </el-button>
      </div>
    </div>

    <div class="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <div class="rounded-lg border border-line bg-card-soft px-4 py-3">
        <div class="text-xs text-ink-muted">当前版本</div>
        <div class="mt-1 font-medium text-ink">
          {{ status?.current_version ? `v${status.current_version}` : '—' }}
        </div>
      </div>
      <div class="rounded-lg border border-line bg-card-soft px-4 py-3">
        <div class="text-xs text-ink-muted">最新版本</div>
        <div class="mt-1 font-medium text-ink">
          {{ status?.latest_version ? `v${status.latest_version}` : '—' }}
        </div>
      </div>
      <div class="rounded-lg border border-line bg-card-soft px-4 py-3">
        <div class="text-xs text-ink-muted">最近检查</div>
        <div class="mt-1 text-sm text-ink">{{ status?.checked_at ? formatDateTime(status.checked_at) : '—' }}</div>
      </div>
      <div class="rounded-lg border border-line bg-card-soft px-4 py-3">
        <div class="text-xs text-ink-muted">构建提交</div>
        <div class="mt-1 font-mono text-sm text-ink">{{ status?.build_sha?.slice(0, 12) || '—' }}</div>
      </div>
    </div>

    <div v-if="operation || status?.message || status?.error" class="mt-4 rounded-lg border border-line px-4 py-3">
      <div class="text-sm text-ink">{{ operation?.message || status?.message }}</div>
      <div v-if="status?.enabled && status?.configured" class="mt-1 text-xs text-ink-muted">
        {{
          status.automatic_check_enabled
            ? `自动检查：每 ${status.check_interval_hours} 小时一次${status.next_check_at ? `，下次 ${formatDateTime(status.next_check_at)}` : ''}`
            : '自动检查已关闭'
        }}
      </div>
      <div v-if="operation?.error || status?.error" class="mt-1 text-sm text-danger">
        {{ operation?.error || status?.error }}
      </div>
      <a
        v-if="operation?.workflow_run_url"
        :href="operation.workflow_run_url"
        target="_blank"
        rel="noopener noreferrer"
        class="mt-2 inline-block text-sm text-primary hover:underline"
      >
        查看 GitHub Actions
      </a>
    </div>

    <div v-if="status?.release" class="mt-4 flex flex-wrap items-start justify-between gap-3 border-t border-line pt-4">
      <div class="min-w-0">
        <div class="text-sm font-medium text-ink">{{ status.release.name || `v${status.release.version}` }}</div>
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
