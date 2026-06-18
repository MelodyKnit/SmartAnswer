<script setup lang="ts">
/** 角色权限矩阵页面。 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { ApiException } from '@/api/http'
import { roleApi } from '@/api/endpoints'
import { useAuthStore } from '@/stores/auth'
import PageHeader from '@/components/PageHeader.vue'

const auth = useAuthStore()
const canEdit = computed(() => auth.isSuperAdmin)
const loading = ref(false)
const roles = ref<Array<{ role_id: string; permissions: string[] }>>([])

const roleLabels: Record<string, string> = {
  superadmin: '超级管理员',
  admin: '管理员',
  user: '普通用户',
}

const permissions = [
  { key: 'dashboard:all', label: '查看全部看板', group: '看板' },
  { key: 'dashboard:self', label: '查看个人看板', group: '看板' },
  { key: 'users:write', label: '管理用户', group: '用户' },
  { key: 'roles:read', label: '查看角色权限', group: '权限' },
  { key: 'roles:write', label: '管理角色权限', group: '权限' },
  { key: 'system:read', label: '查看系统日志', group: '系统' },
  { key: 'system:write', label: '修改系统配置', group: '系统' },
  { key: 'billing:read', label: '查看计费规则', group: '计费' },
  { key: 'billing:write', label: '修改计费规则', group: '计费' },
  { key: 'wallet:changes:read', label: '查看积分流水', group: '积分' },
  { key: 'wallet:changes:write', label: '管理积分与兑换码', group: '积分' },
  { key: 'import-scripts:read', label: '查看导入脚本', group: '接入' },
  { key: 'import-scripts:write', label: '管理导入脚本', group: '接入' },
  { key: 'questions:read', label: '查看题库', group: '题库' },
  { key: 'questions:write', label: '维护题库', group: '题库' },
  { key: 'llm:read', label: '查看大模型配置', group: '大模型' },
  { key: 'llm:write', label: '管理大模型配置', group: '大模型' },
  { key: 'tokens:self', label: '管理个人令牌', group: '令牌' },
  { key: 'feedback:self', label: '提交个人反馈', group: '反馈' },
]

const selected = ref<Record<string, string[]>>({})

async function load() {
  loading.value = true
  try {
    const res = await roleApi.list()
    roles.value = res.roles
    selected.value = Object.fromEntries(res.roles.map((role) => [role.role_id, [...role.permissions]]))
  } finally {
    loading.value = false
  }
}

function toggle(roleId: string, permission: string, enabled: boolean) {
  const values = new Set(selected.value[roleId] || [])
  enabled ? values.add(permission) : values.delete(permission)
  selected.value[roleId] = [...values]
}

async function save(roleId: string) {
  try {
    await roleApi.setPermissions(roleId, selected.value[roleId] || [])
    ElMessage.success('权限已更新')
    await load()
  } catch (err) {
    ElMessage.error(err instanceof ApiException ? err.message : '保存失败')
  }
}

onMounted(load)
</script>

<template>
  <div v-loading="loading">
    <PageHeader title="角色权限" description="配置不同角色的权限矩阵。" />
    <el-alert v-if="!canEdit" type="info" :closable="false" class="mb-4" title="当前为只读视图，仅超级管理员可修改角色权限。" />

    <div class="grid grid-cols-1 gap-4 lg:grid-cols-3">
      <div v-for="role in roles" :key="role.role_id" class="app-card flex flex-col p-5">
        <div class="mb-3 flex items-center justify-between">
          <h3 class="text-base font-semibold text-ink">{{ roleLabels[role.role_id] || role.role_id }}</h3>
          <el-tag size="small" effect="plain">{{ (selected[role.role_id] || []).length }} 项权限</el-tag>
        </div>

        <div class="flex-1 space-y-2.5">
          <label v-for="permission in permissions" :key="permission.key" class="flex items-center gap-2">
            <el-checkbox
              :model-value="(selected[role.role_id] || []).includes(permission.key)"
              :disabled="!canEdit"
              @change="toggle(role.role_id, permission.key, !!$event)"
            />
            <span class="text-sm text-ink-soft">{{ permission.label }}</span>
            <code class="ml-auto rounded bg-canvas px-1.5 py-0.5 text-[11px] text-ink-muted">{{ permission.key }}</code>
          </label>
        </div>

        <el-button v-if="canEdit" type="primary" class="mt-4 w-full" @click="save(role.role_id)">保存</el-button>
      </div>
    </div>
  </div>
</template>
