<script setup lang="ts">
/** 角色权限配置页：左侧选择角色，右侧按模块维护当前角色权限。 */
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { ApiException } from '@/api/http'
import { roleApi } from '@/api/endpoints'
import type { RolePermission } from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import PageHeader from '@/components/PageHeader.vue'

interface PermissionItem {
  key: string
  label: string
  description: string
}

interface PermissionGroup {
  key: string
  label: string
  description: string
  icon: string
  permissions: PermissionItem[]
}

const auth = useAuthStore()
const canEdit = computed(() => auth.isSuperAdmin)
const loading = ref(false)
const saving = ref(false)
const roles = ref<RolePermission[]>([])
const selectedRoleId = ref('')
const selected = ref<Record<string, string[]>>({})
const original = ref<Record<string, string[]>>({})
const keyword = ref('')
const openGroups = ref<string[]>([])

const roleLabels: Record<string, string> = {
  superadmin: '超级管理员',
  admin: '管理员',
  user: '普通用户',
}

const roleDescriptions: Record<string, string> = {
  superadmin: '平台最高权限',
  admin: '运营与配置管理',
  user: '基础使用权限',
}

const roleOrder: Record<string, number> = {
  superadmin: 1,
  admin: 2,
  user: 3,
}

const permissionGroups: PermissionGroup[] = [
  {
    key: 'dashboard',
    label: '控制台权限',
    description: '访问控制台看板和统计概览',
    icon: 'DataBoard',
    permissions: [
      { key: 'dashboard:all', label: '查看全部看板', description: '查看全站控制台看板数据' },
      { key: 'dashboard:self', label: '查看个人看板', description: '查看个人控制台看板数据' },
    ],
  },
  {
    key: 'users',
    label: '用户与角色',
    description: '管理用户、角色及其权限分配',
    icon: 'User',
    permissions: [
      { key: 'users:write', label: '管理用户', description: '创建、编辑、禁用用户' },
      { key: 'roles:read', label: '查看角色权限', description: '查看角色的权限配置' },
      { key: 'roles:write', label: '管理角色权限', description: '分配和保存角色权限' },
    ],
  },
  {
    key: 'questions',
    label: '题库管理',
    description: '管理题库与题目内容',
    icon: 'Collection',
    permissions: [
      { key: 'questions:read', label: '查看题库', description: '查看题库列表和题目详情' },
      { key: 'questions:write', label: '维护题库', description: '新增、编辑、删除题库题目' },
    ],
  },
  {
    key: 'wallet',
    label: '钱包与积分',
    description: '维护积分策略、兑换码和积分流水',
    icon: 'Wallet',
    permissions: [
      { key: 'billing:read', label: '查看计费规则', description: '查看系统积分扣费规则' },
      { key: 'billing:write', label: '修改计费规则', description: '修改系统积分策略配置' },
      { key: 'wallet:changes:read', label: '查看积分流水', description: '查看用户积分变动记录' },
      { key: 'wallet:changes:write', label: '管理积分与兑换码', description: '发放积分、创建和管理兑换码' },
    ],
  },
  {
    key: 'system',
    label: '系统管理',
    description: '查看运行日志与维护系统配置',
    icon: 'Setting',
    permissions: [
      { key: 'system:read', label: '查看系统日志', description: '查看系统运行日志与状态信息' },
      { key: 'system:write', label: '修改系统配置', description: '修改系统配置、积分策略和服务协议' },
    ],
  },
  {
    key: 'scripts',
    label: '导入脚本',
    description: '维护第三方平台接入脚本',
    icon: 'Document',
    permissions: [
      { key: 'import-scripts:read', label: '查看导入脚本', description: '查看脚本模板和生成记录' },
      { key: 'import-scripts:write', label: '管理导入脚本', description: '创建、编辑和发布导入脚本' },
    ],
  },
  {
    key: 'llm',
    label: '大模型配置',
    description: '维护模型链路、联网搜索与调用追溯',
    icon: 'Cpu',
    permissions: [
      { key: 'llm:read', label: '查看大模型配置', description: '查看模型、联网搜索和调用追溯' },
      { key: 'llm:write', label: '管理大模型配置', description: '维护模型配置、搜索引擎和答题策略' },
    ],
  },
  {
    key: 'personal',
    label: '个人中心',
    description: '个人 API Key 与反馈能力',
    icon: 'Key',
    permissions: [
      { key: 'tokens:self', label: '管理个人令牌', description: '创建、查看、撤销自己的 API Key' },
      { key: 'feedback:self', label: '提交个人反馈', description: '提交题目纠错和使用反馈' },
    ],
  },
]

const permissionCatalog = computed(() => permissionGroups.flatMap((group) => group.permissions))
const totalPermissionCount = computed(() => permissionCatalog.value.length)

const sortedRoles = computed(() => {
  return [...roles.value].sort((left, right) => {
    return (roleOrder[left.role_id] ?? 99) - (roleOrder[right.role_id] ?? 99)
  })
})

const activeRole = computed(() => {
  return sortedRoles.value.find((role) => role.role_id === selectedRoleId.value) ?? null
})

const activePermissionSet = computed(() => new Set(selected.value[selectedRoleId.value] || []))
const originalPermissionSet = computed(() => new Set(original.value[selectedRoleId.value] || []))

const changedCount = computed(() => {
  const current = activePermissionSet.value
  const baseline = originalPermissionSet.value
  const added = [...current].filter((item) => !baseline.has(item)).length
  const removed = [...baseline].filter((item) => !current.has(item)).length
  return added + removed
})

const isDirty = computed(() => changedCount.value > 0)

const filteredGroups = computed(() => {
  const text = keyword.value.trim().toLowerCase()
  if (!text) return permissionGroups
  return permissionGroups
    .map((group) => ({
      ...group,
      permissions: group.permissions.filter((permission) => {
        return [group.label, group.description, permission.label, permission.description, permission.key]
          .join(' ')
          .toLowerCase()
          .includes(text)
      }),
    }))
    .filter((group) => group.permissions.length > 0)
})

watch(filteredGroups, (groups) => {
  openGroups.value = groups.map((group) => group.key)
}, { immediate: true })

async function load() {
  loading.value = true
  try {
    const res = await roleApi.list()
    roles.value = res.roles
    selected.value = Object.fromEntries(res.roles.map((role) => [role.role_id, [...role.permissions]]))
    original.value = Object.fromEntries(res.roles.map((role) => [role.role_id, [...role.permissions]]))
    if (!selectedRoleId.value || !res.roles.some((role) => role.role_id === selectedRoleId.value)) {
      selectedRoleId.value = sortedRoleId(res.roles[0]?.role_id || '')
    }
  } finally {
    loading.value = false
  }
}

function sortedRoleId(fallback: string) {
  const first = [...roles.value].sort((left, right) => {
    return (roleOrder[left.role_id] ?? 99) - (roleOrder[right.role_id] ?? 99)
  })[0]
  return first?.role_id || fallback
}

function roleLabel(roleId: string) {
  return roleLabels[roleId] || roleId
}

function roleDescription(roleId: string) {
  return roleDescriptions[roleId] || '自定义角色权限配置'
}

function rolePermissions(roleId: string) {
  return selected.value[roleId] || []
}

function selectRole(roleId: string) {
  selectedRoleId.value = roleId
}

function togglePermission(permission: string, enabled: boolean) {
  if (!canEdit.value || !selectedRoleId.value) return
  const values = new Set(selected.value[selectedRoleId.value] || [])
  enabled ? values.add(permission) : values.delete(permission)
  selected.value[selectedRoleId.value] = [...values]
}

function groupSelectedCount(group: PermissionGroup) {
  const current = activePermissionSet.value
  return group.permissions.filter((permission) => current.has(permission.key)).length
}

function setGroupPermissions(group: PermissionGroup, enabled: boolean) {
  if (!canEdit.value || !selectedRoleId.value) return
  const values = new Set(selected.value[selectedRoleId.value] || [])
  for (const permission of group.permissions) {
    enabled ? values.add(permission.key) : values.delete(permission.key)
  }
  selected.value[selectedRoleId.value] = [...values]
}

function resetActiveRole() {
  if (!selectedRoleId.value) return
  selected.value[selectedRoleId.value] = [...(original.value[selectedRoleId.value] || [])]
}

async function saveActiveRole() {
  if (!selectedRoleId.value || !canEdit.value) return
  saving.value = true
  try {
    await roleApi.setPermissions(selectedRoleId.value, selected.value[selectedRoleId.value] || [])
    ElMessage.success('权限已更新')
    await load()
  } catch (err) {
    ElMessage.error(err instanceof ApiException ? err.message : '保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="flex min-h-0 flex-col xl:h-[calc(100vh-7rem)] xl:overflow-hidden">
    <PageHeader title="角色权限" description="集中管理角色可访问的功能范围。">
      <template #actions>
        <el-input
          v-model="keyword"
          class="w-full sm:w-72"
          clearable
          placeholder="搜索权限"
          :prefix-icon="'Search'"
        />
      </template>
    </PageHeader>

    <el-alert
      v-if="!canEdit"
      type="info"
      :closable="false"
      class="mb-4"
      title="当前为只读视图，仅超级管理员可修改角色权限。"
    />

    <div class="grid min-h-0 grid-cols-1 gap-5 xl:flex-1 xl:grid-cols-[360px_minmax(0,1fr)]">
      <aside class="app-card h-full min-h-0 overflow-hidden">
        <div class="border-b border-line px-5 py-4">
          <div class="flex items-center justify-between">
            <h3 class="text-base font-semibold text-ink">角色列表</h3>
            <el-tag size="small" effect="plain">{{ sortedRoles.length }} 个角色</el-tag>
          </div>
        </div>

        <div class="space-y-3 p-4">
          <button
            v-for="role in sortedRoles"
            :key="role.role_id"
            type="button"
            class="w-full cursor-pointer rounded-2xl border p-4 text-left transition hover:border-brand-300 hover:bg-brand-50/70 dark:hover:bg-brand-50"
            :class="role.role_id === selectedRoleId
              ? 'border-brand-400 bg-brand-50 shadow-[0_10px_28px_rgba(79,110,247,0.16)]'
              : 'border-line bg-card-soft'"
            @click="selectRole(role.role_id)"
          >
            <div class="flex items-start justify-between gap-3">
              <div>
                <div class="flex items-center gap-2">
                  <span class="flex h-8 w-8 items-center justify-center rounded-xl bg-brand-100 text-brand-600">
                    <el-icon><UserFilled /></el-icon>
                  </span>
                  <span class="font-semibold text-ink">{{ roleLabel(role.role_id) }}</span>
                </div>
                <p class="mt-2 line-clamp-2 text-xs text-ink-muted">{{ roleDescription(role.role_id) }}</p>
              </div>
              <span class="shrink-0 rounded-full bg-canvas px-2.5 py-1 text-xs text-ink-soft">
                {{ rolePermissions(role.role_id).length }} 项权限
              </span>
            </div>

            <div class="mt-3 flex items-center gap-2 text-xs">
              <span class="rounded-full bg-canvas px-2 py-0.5 text-ink-muted">内置</span>
              <span
                class="rounded-full px-2 py-0.5"
                :class="canEdit ? 'bg-emerald-500/10 text-success' : 'bg-canvas text-ink-muted'"
              >
                {{ canEdit ? '可配置' : '只读' }}
              </span>
              <span v-if="role.role_id === selectedRoleId" class="ml-auto text-brand-600">当前选中</span>
            </div>
          </button>
        </div>
      </aside>

      <section class="app-card flex min-h-[620px] flex-col overflow-hidden xl:h-full xl:min-h-0">
        <div class="shrink-0 border-b border-line bg-card px-5 py-4">
          <div v-if="activeRole" class="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <div class="flex flex-wrap items-center gap-3">
                <h3 class="text-lg font-semibold text-ink">{{ roleLabel(activeRole.role_id) }}</h3>
                <el-tag type="primary" effect="light">{{ activePermissionSet.size }} 项权限</el-tag>
                <el-tag v-if="canEdit" type="success" effect="light">可编辑</el-tag>
                <el-tag v-else effect="plain">只读</el-tag>
              </div>
              <p class="mt-1 text-sm text-ink-soft">{{ roleDescription(activeRole.role_id) }}</p>
            </div>
            <div class="text-sm text-ink-muted">
              已开启 {{ activePermissionSet.size }} / {{ totalPermissionCount }} 项
            </div>
          </div>
        </div>

        <div class="min-h-0 flex-1 overflow-y-auto p-4 lg:p-5">
          <el-empty v-if="!activeRole" description="暂无角色数据" />
          <el-empty v-else-if="filteredGroups.length === 0" description="没有匹配的权限项" />

          <el-collapse v-else v-model="openGroups" class="roles-permission-collapse">
            <el-collapse-item v-for="group in filteredGroups" :key="group.key" :name="group.key">
              <template #title>
                <div class="grid min-w-0 flex-1 grid-cols-[minmax(0,1fr)_auto] items-center gap-3 pr-2">
                  <div class="flex min-w-0 items-center gap-3">
                    <span class="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-600">
                      <el-icon><component :is="group.icon" /></el-icon>
                    </span>
                    <div class="flex min-w-0 items-center gap-2">
                      <span class="truncate font-semibold text-ink">{{ group.label }}</span>
                      <span class="shrink-0 text-xs text-ink-muted">
                        {{ groupSelectedCount(group) }} / {{ group.permissions.length }}
                      </span>
                    </div>
                  </div>
                  <div class="hidden items-center justify-end gap-3 text-xs sm:flex" @click.stop>
                    <button
                      type="button"
                      class="cursor-pointer text-brand-600 transition hover:text-brand-700 disabled:cursor-not-allowed disabled:text-ink-muted"
                      :disabled="!canEdit"
                      @click="setGroupPermissions(group, true)"
                    >
                      全选
                    </button>
                    <span class="h-3 w-px bg-line-strong" />
                    <button
                      type="button"
                      class="cursor-pointer text-ink-soft transition hover:text-danger disabled:cursor-not-allowed disabled:text-ink-muted"
                      :disabled="!canEdit"
                      @click="setGroupPermissions(group, false)"
                    >
                      清空
                    </button>
                  </div>
                </div>
              </template>

              <div class="divide-y divide-line">
                <label
                  v-for="permission in group.permissions"
                  :key="permission.key"
                  class="grid cursor-pointer grid-cols-[auto_minmax(0,1fr)] items-center gap-3 px-1 py-3 transition hover:bg-card-soft sm:grid-cols-[auto_minmax(0,1fr)_max-content]"
                >
                  <el-checkbox
                    :model-value="activePermissionSet.has(permission.key)"
                    :disabled="!canEdit"
                    @change="togglePermission(permission.key, !!$event)"
                  />
                  <span class="min-w-0">
                    <span class="block text-sm font-medium text-ink">{{ permission.label }}</span>
                    <span class="mt-0.5 block text-xs text-ink-muted">{{ permission.description }}</span>
                  </span>
                  <code
                    class="col-start-2 w-fit justify-self-start rounded-md bg-card-soft px-2 py-0.5 font-mono text-[10px] text-ink-muted opacity-80 sm:col-start-auto sm:justify-self-end"
                  >
                    {{ permission.key }}
                  </code>
                </label>
              </div>
            </el-collapse-item>
          </el-collapse>
        </div>

        <div class="shrink-0 border-t border-line bg-card/95 px-5 py-4 backdrop-blur">
          <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div class="text-sm">
              <span v-if="isDirty" class="font-medium text-brand-600">已修改 {{ changedCount }} 项权限</span>
              <span v-else class="text-ink-muted">当前角色权限未修改</span>
            </div>
            <div class="flex items-center gap-2">
              <el-button :disabled="!isDirty || saving" @click="resetActiveRole">取消</el-button>
              <el-button
                v-if="canEdit"
                type="primary"
                :loading="saving"
                :disabled="!isDirty"
                @click="saveActiveRole"
              >
                保存修改
              </el-button>
            </div>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.roles-permission-collapse {
  --el-collapse-border-color: transparent;
  border: 0;
}

.roles-permission-collapse :deep(.el-collapse-item) {
  margin-bottom: 10px;
  overflow: hidden;
  border: 1px solid var(--c-line);
  border-radius: 14px;
  background: var(--c-card);
}

.roles-permission-collapse :deep(.el-collapse-item__header) {
  height: auto;
  min-height: 56px;
  padding: 12px 16px;
  border-bottom-color: var(--c-line);
  background: var(--c-card-soft);
  line-height: 1.2;
}

.roles-permission-collapse :deep(.el-collapse-item__wrap) {
  border-bottom: 0;
  background: var(--c-card);
}

.roles-permission-collapse :deep(.el-collapse-item__content) {
  padding: 0 16px 6px;
}
</style>
