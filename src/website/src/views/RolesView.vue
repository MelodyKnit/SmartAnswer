<script setup lang="ts">
/** 角色权限配置页：消费后端角色和权限目录，支持系统角色与自定义角色共存。 */
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ApiException } from '@/api/http'
import { roleApi } from '@/api/endpoints'
import type { PermissionDefinition, RolePermission } from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import PageHeader from '@/components/PageHeader.vue'

interface PermissionGroup {
  key: string
  label: string
  icon: string
  permissions: PermissionDefinition[]
}

const auth = useAuthStore()
const loading = ref(false)
const saving = ref(false)
const roles = ref<RolePermission[]>([])
const permissionCatalog = ref<PermissionDefinition[]>([])
const selectedRoleId = ref('')
const selected = ref<Record<string, string[]>>({})
const original = ref<Record<string, string[]>>({})
const keyword = ref('')
const openGroups = ref<string[]>([])
const createVisible = ref(false)
const editVisible = ref(false)
const createForm = reactive({ role_id: '', name: '', description: '' })
const editForm = reactive({ name: '', description: '' })

const canEditAnyRole = computed(() => auth.hasPermission('roles:write'))
const canManageRoleLifecycle = computed(() => auth.isSuperAdmin)

const sortedRoles = computed(() =>
  [...roles.value].sort((left, right) => {
    if (left.is_system !== right.is_system) return left.is_system ? -1 : 1
    return left.name.localeCompare(right.name, 'zh-CN')
  }),
)

const activeRole = computed(() =>
  roles.value.find((role) => role.role_id === selectedRoleId.value) ?? null,
)
const activePermissionSet = computed(() => new Set(selected.value[selectedRoleId.value] ?? []))
const originalPermissionSet = computed(() => new Set(original.value[selectedRoleId.value] ?? []))
const canEditActiveRole = computed(() => {
  if (!activeRole.value || !canEditAnyRole.value) return false
  return !activeRole.value.is_system || auth.isSuperAdmin
})
const canEditActiveMetadata = computed(
  () => Boolean(activeRole.value && !activeRole.value.is_system && canEditActiveRole.value),
)
const canDeleteActiveRole = computed(
  () => Boolean(activeRole.value && !activeRole.value.is_system && canManageRoleLifecycle.value),
)

const changedCount = computed(() => {
  const current = activePermissionSet.value
  const baseline = originalPermissionSet.value
  return [...current].filter((item) => !baseline.has(item)).length
    + [...baseline].filter((item) => !current.has(item)).length
})
const isDirty = computed(() => changedCount.value > 0)

const permissionGroups = computed<PermissionGroup[]>(() => {
  const groups = new Map<string, PermissionGroup>()
  for (const permission of permissionCatalog.value) {
    const group = groups.get(permission.group)
    if (group) {
      group.permissions.push(permission)
      continue
    }
    groups.set(permission.group, {
      key: permission.group,
      label: permission.group_label,
      icon: permission.icon || 'Lock',
      permissions: [permission],
    })
  }
  return [...groups.values()]
})

const filteredGroups = computed(() => {
  const normalizedKeyword = keyword.value.trim().toLowerCase()
  if (!normalizedKeyword) return permissionGroups.value
  return permissionGroups.value
    .map((group) => ({
      ...group,
      permissions: group.permissions.filter((permission) =>
        [group.label, permission.label, permission.description, permission.key]
          .join(' ')
          .toLowerCase()
          .includes(normalizedKeyword),
      ),
    }))
    .filter((group) => group.permissions.length > 0)
})

watch(filteredGroups, (groups) => {
  openGroups.value = groups.map((group) => group.key)
}, { immediate: true })

async function load(preferredRoleId = selectedRoleId.value) {
  loading.value = true
  try {
    const response = await roleApi.list()
    roles.value = response.roles
    permissionCatalog.value = response.permission_catalog
    selected.value = Object.fromEntries(
      response.roles.map((role) => [role.role_id, [...role.permissions]]),
    )
    original.value = Object.fromEntries(
      response.roles.map((role) => [role.role_id, [...role.permissions]]),
    )
    selectedRoleId.value = response.roles.some((role) => role.role_id === preferredRoleId)
      ? preferredRoleId
      : sortedRoles.value[0]?.role_id ?? ''
  } catch (error) {
    ElMessage.error(error instanceof ApiException ? error.message : '加载角色失败')
  } finally {
    loading.value = false
  }
}

function selectRole(roleId: string) {
  selectedRoleId.value = roleId
}

function rolePermissions(roleId: string) {
  return selected.value[roleId] ?? []
}

function togglePermission(permission: string, enabled: boolean) {
  if (!canEditActiveRole.value || !selectedRoleId.value) return
  const next = new Set(selected.value[selectedRoleId.value] ?? [])
  enabled ? next.add(permission) : next.delete(permission)
  selected.value[selectedRoleId.value] = [...next].sort()
}

function groupSelectedCount(group: PermissionGroup) {
  return group.permissions.filter((permission) => activePermissionSet.value.has(permission.key)).length
}

function setGroupPermissions(group: PermissionGroup, enabled: boolean) {
  if (!canEditActiveRole.value || !selectedRoleId.value) return
  const next = new Set(selected.value[selectedRoleId.value] ?? [])
  for (const permission of group.permissions) {
    enabled ? next.add(permission.key) : next.delete(permission.key)
  }
  selected.value[selectedRoleId.value] = [...next].sort()
}

function resetActiveRole() {
  if (!selectedRoleId.value) return
  selected.value[selectedRoleId.value] = [...(original.value[selectedRoleId.value] ?? [])]
}

async function saveActiveRole() {
  if (!activeRole.value || !canEditActiveRole.value) return
  saving.value = true
  try {
    await roleApi.update(activeRole.value.role_id, {
      permissions: selected.value[activeRole.value.role_id] ?? [],
    })
    ElMessage.success('权限已更新')
    await load(activeRole.value.role_id)
    await auth.refreshProfile()
  } catch (error) {
    ElMessage.error(error instanceof ApiException ? error.message : '保存失败')
  } finally {
    saving.value = false
  }
}

function openCreateDialog() {
  createForm.role_id = ''
  createForm.name = ''
  createForm.description = ''
  createVisible.value = true
}

async function createRole() {
  saving.value = true
  try {
    const response = await roleApi.create({
      role_id: createForm.role_id,
      name: createForm.name,
      description: createForm.description,
      permissions: [],
    })
    createVisible.value = false
    ElMessage.success('角色已创建')
    await load(response.role.role_id)
  } catch (error) {
    ElMessage.error(error instanceof ApiException ? error.message : '创建角色失败')
  } finally {
    saving.value = false
  }
}

function openEditDialog() {
  if (!activeRole.value) return
  editForm.name = activeRole.value.name
  editForm.description = activeRole.value.description
  editVisible.value = true
}

async function saveRoleMetadata() {
  if (!activeRole.value) return
  saving.value = true
  try {
    await roleApi.update(activeRole.value.role_id, {
      name: editForm.name,
      description: editForm.description,
    })
    editVisible.value = false
    ElMessage.success('角色信息已更新')
    await load(activeRole.value.role_id)
  } catch (error) {
    ElMessage.error(error instanceof ApiException ? error.message : '保存失败')
  } finally {
    saving.value = false
  }
}

async function deleteActiveRole() {
  if (!activeRole.value || !canDeleteActiveRole.value) return
  const role = activeRole.value
  try {
    await ElMessageBox.confirm(
      `删除后无法恢复“${role.name}”，请先确认没有用户仍使用该角色。`,
      '删除自定义角色',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' },
    )
    await roleApi.remove(role.role_id)
    ElMessage.success('角色已删除')
    await load()
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error(error instanceof ApiException ? error.message : '删除角色失败')
  }
}

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="roles-page flex min-h-0 flex-col xl:h-full xl:overflow-hidden">
    <PageHeader title="角色权限" description="集中管理角色可访问的功能范围。">
      <template #actions>
        <div class="flex w-full items-center gap-2 sm:w-auto">
          <el-input v-model="keyword" class="w-full sm:w-64" clearable placeholder="搜索权限" :prefix-icon="'Search'" />
          <el-button v-if="canManageRoleLifecycle" type="primary" @click="openCreateDialog">
            <el-icon><Plus /></el-icon> 新增角色
          </el-button>
        </div>
      </template>
    </PageHeader>

    <el-alert
      v-if="!canEditAnyRole"
      type="info"
      :closable="false"
      class="mb-4"
      title="当前账号仅可查看角色权限。"
    />

    <div class="grid min-h-0 grid-cols-1 gap-5 xl:flex-1 xl:grid-cols-[360px_minmax(0,1fr)] xl:overflow-hidden">
      <aside class="app-card flex min-h-0 flex-col overflow-hidden">
        <div class="flex items-center justify-between border-b border-line px-5 py-4">
          <h3 class="text-base font-semibold text-ink">角色列表</h3>
          <el-tag size="small" effect="plain">{{ sortedRoles.length }} 个角色</el-tag>
        </div>

        <div class="min-h-0 space-y-3 overflow-y-auto p-4 xl:flex-1">
          <button
            v-for="role in sortedRoles"
            :key="role.role_id"
            type="button"
            class="w-full cursor-pointer rounded-xl border p-4 text-left transition hover:border-brand-300 hover:bg-brand-50/70 dark:hover:bg-brand-50"
            :class="role.role_id === selectedRoleId ? 'border-brand-400 bg-brand-50 shadow-[0_10px_28px_rgba(79,110,247,0.16)]' : 'border-line bg-card-soft'"
            @click="selectRole(role.role_id)"
          >
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <div class="flex items-center gap-2">
                  <span class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-brand-100 text-brand-600">
                    <el-icon><UserFilled /></el-icon>
                  </span>
                  <span class="truncate font-semibold text-ink">{{ role.name }}</span>
                </div>
                <p v-if="role.description" class="mt-2 line-clamp-2 text-xs text-ink-muted">{{ role.description }}</p>
              </div>
              <span class="shrink-0 rounded-full bg-canvas px-2.5 py-1 text-xs text-ink-soft">{{ rolePermissions(role.role_id).length }} 项</span>
            </div>
            <div class="mt-3 flex items-center gap-2 text-xs">
              <span class="rounded-full bg-canvas px-2 py-0.5 text-ink-muted">{{ role.is_system ? '系统内置' : '自定义' }}</span>
              <span v-if="role.role_id === selectedRoleId" class="ml-auto text-brand-600">当前选中</span>
            </div>
          </button>
        </div>
      </aside>

      <section class="app-card flex min-h-[620px] flex-col overflow-hidden xl:h-full xl:min-h-0">
        <div class="shrink-0 border-b border-line bg-card px-5 py-4">
          <div v-if="activeRole" class="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <div class="flex flex-wrap items-center gap-2">
                <h3 class="text-lg font-semibold text-ink">{{ activeRole.name }}</h3>
                <el-tag effect="plain">{{ activeRole.is_system ? '系统内置' : '自定义角色' }}</el-tag>
                <el-tag type="primary" effect="light">{{ activePermissionSet.size }} 项权限</el-tag>
              </div>
              <p v-if="activeRole.description" class="mt-1 text-sm text-ink-soft">{{ activeRole.description }}</p>
            </div>
            <div class="flex items-center gap-2">
              <el-button v-if="canEditActiveMetadata" @click="openEditDialog">编辑信息</el-button>
              <el-button v-if="canDeleteActiveRole" type="danger" plain @click="deleteActiveRole">删除角色</el-button>
              <span class="text-sm text-ink-muted">已开启 {{ activePermissionSet.size }} / {{ permissionCatalog.length }} 项</span>
            </div>
          </div>
        </div>

        <div class="min-h-0 flex-1 overflow-y-auto p-4 lg:p-5">
          <el-empty v-if="!activeRole" description="暂无角色数据" />
          <el-empty v-else-if="filteredGroups.length === 0" description="没有匹配的权限项" />
          <el-collapse v-else v-model="openGroups" class="roles-permission-collapse">
            <el-collapse-item v-for="group in filteredGroups" :key="group.key" :name="group.key">
              <template #title>
                <div class="flex min-w-0 flex-1 items-center justify-between gap-4 pr-2">
                  <div class="flex min-w-0 items-center gap-3">
                    <span class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-brand-600">
                      <el-icon><component :is="group.icon" /></el-icon>
                    </span>
                    <div class="flex min-w-0 items-center gap-2">
                      <span class="truncate font-semibold text-ink">{{ group.label }}</span>
                      <span class="shrink-0 text-xs text-ink-muted">{{ groupSelectedCount(group) }} / {{ group.permissions.length }}</span>
                    </div>
                  </div>
                  <div class="hidden shrink-0 items-center gap-3 text-xs sm:flex" @click.stop>
                    <button type="button" class="permission-action" :disabled="!canEditActiveRole" @click="setGroupPermissions(group, true)">全选</button>
                    <span class="h-3 w-px bg-line-strong" />
                    <button type="button" class="permission-action text-ink-soft hover:text-danger" :disabled="!canEditActiveRole" @click="setGroupPermissions(group, false)">清空</button>
                  </div>
                </div>
              </template>

              <div class="divide-y divide-line">
                <label v-for="permission in group.permissions" :key="permission.key" class="grid cursor-pointer grid-cols-[auto_minmax(0,1fr)] items-center gap-3 px-1 py-3 transition hover:bg-card-soft sm:grid-cols-[auto_minmax(0,1fr)_max-content]">
                  <el-checkbox :model-value="activePermissionSet.has(permission.key)" :disabled="!canEditActiveRole" @change="togglePermission(permission.key, !!$event)" />
                  <span class="min-w-0">
                    <span class="block text-sm font-medium text-ink">{{ permission.label }}</span>
                    <span class="mt-0.5 block text-xs text-ink-muted">{{ permission.description }}</span>
                  </span>
                  <code class="permission-code col-start-2 w-fit justify-self-start rounded-md px-1.5 py-0.5 font-mono text-[10px] sm:col-start-auto sm:justify-self-end">{{ permission.key }}</code>
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
              <el-button v-if="canEditActiveRole" type="primary" :loading="saving" :disabled="!isDirty" @click="saveActiveRole">保存修改</el-button>
            </div>
          </div>
        </div>
      </section>
    </div>

    <el-dialog v-model="createVisible" title="新增自定义角色" width="440px" destroy-on-close>
      <el-form label-position="top">
        <el-form-item label="角色标识">
          <el-input v-model="createForm.role_id" placeholder="例如 content_editor" />
        </el-form-item>
        <el-form-item label="角色名称">
          <el-input v-model="createForm.name" placeholder="例如 内容运营" />
        </el-form-item>
        <el-form-item label="角色说明">
          <el-input v-model="createForm.description" maxlength="120" show-word-limit type="textarea" :rows="3" placeholder="可选，用于说明该角色的职责" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="createRole">创建并配置权限</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="editVisible" title="编辑角色信息" width="440px" destroy-on-close>
      <el-form label-position="top">
        <el-form-item label="角色名称"><el-input v-model="editForm.name" /></el-form-item>
        <el-form-item label="角色说明"><el-input v-model="editForm.description" maxlength="120" show-word-limit type="textarea" :rows="3" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveRoleMetadata">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.roles-page { min-height: 0; }
.roles-permission-collapse { --el-collapse-border-color: transparent; border: 0; }
.roles-permission-collapse :deep(.el-collapse-item) { margin-bottom: 10px; overflow: hidden; border: 1px solid var(--c-line); border-radius: 12px; background: var(--c-card); }
.roles-permission-collapse :deep(.el-collapse-item__header) { height: auto; min-height: 60px; padding: 10px 14px 10px 16px; border-bottom-color: var(--c-line); background: var(--c-card-soft); line-height: 1.2; }
.roles-permission-collapse :deep(.el-collapse-item__arrow) { margin-left: 6px; color: var(--c-ink-muted); }
.roles-permission-collapse :deep(.el-collapse-item__wrap) { border-bottom: 0; background: var(--c-card); }
.roles-permission-collapse :deep(.el-collapse-item__content) { padding: 0 14px 6px; }
.permission-code { color: color-mix(in srgb, var(--c-ink-muted) 72%, transparent); background: color-mix(in srgb, var(--c-card-soft) 78%, transparent); border: 1px solid color-mix(in srgb, var(--c-line) 80%, transparent); }
.permission-action { cursor: pointer; color: var(--c-brand-600); transition: color 150ms ease; }
.permission-action:hover { color: var(--c-brand-700); }
.permission-action:disabled { cursor: not-allowed; color: var(--c-ink-muted); }
</style>
