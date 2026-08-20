<script setup lang="ts">
/** 用户管理：列出用户、调整状态/角色/积分，并支持管理员手动发放权益。 */
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { billingApi, roleApi, userApi, walletApi } from '@/api/endpoints'
import type { ManagedUser, RolePermission } from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import { ApiException } from '@/api/http'
import { formatDateTime } from '@/utils/format'
import PageHeader from '@/components/PageHeader.vue'

const auth = useAuthStore()
const loading = ref(false)
const users = ref<ManagedUser[]>([])
const roles = ref<RolePermission[]>([])
const manualGrantDefault = ref(1)
const canAssignRoles = computed(() => auth.isSuperAdmin)
const canGrantPoints = computed(() => auth.hasPermission('wallet:changes:write'))
const canReadBillingPolicy = computed(() => auth.hasPermission('billing:read'))

async function loadUsers() {
  loading.value = true
  try {
    const res = await userApi.list()
    users.value = res.users
  } finally {
    loading.value = false
  }
}

async function loadPointsPolicy() {
  if (!canReadBillingPolicy.value) return
  try {
    const res = await billingApi.pointsPolicy()
    manualGrantDefault.value = res.points_policy.manual_grant_default_points
  } catch {
    // 积分策略只用于表单默认值，加载失败不影响用户管理主流程。
  }
}

async function loadRoles() {
  if (!canAssignRoles.value) return
  try {
    const response = await roleApi.list()
    roles.value = response.roles
  } catch {
    // 角色选择器只为超级管理员提供；加载失败时由提交接口返回明确错误。
  }
}

const editVisible = ref(false)
const editing = reactive<{
  username: string
  role: string
  points: number
  unlimited_expires_at_ms: string | number
  status: string
  original_role: string
}>({
  username: '',
  role: 'user',
  points: 0,
  unlimited_expires_at_ms: '',
  status: 'active',
  original_role: 'user',
})

function openEdit(user: ManagedUser) {
  editing.username = user.username
  editing.role = user.role
  editing.original_role = user.role
  editing.points = user.points
  editing.unlimited_expires_at_ms = user.unlimited_expires_at ? user.unlimited_expires_at * 1000 : ''
  editing.status = user.status
  editVisible.value = true
}

function canManageUser(user: ManagedUser) {
  return auth.isSuperAdmin || user.role === 'user'
}

async function submitEdit() {
  try {
    const unlimitedExpiresAt = editing.unlimited_expires_at_ms
      ? Math.floor(Number(editing.unlimited_expires_at_ms) / 1000)
      : 0
    const body: Record<string, unknown> = {
      points: editing.points,
      unlimited_expires_at: unlimitedExpiresAt,
      status: editing.status,
    }
    if (canAssignRoles.value && editing.role !== editing.original_role) {
      body.role = editing.role
    }
    await userApi.update(editing.username, body)
    ElMessage.success('已保存')
    editVisible.value = false
    if (editing.username === auth.user?.username) {
      await auth.refreshProfile()
    }
    await loadUsers()
  } catch (error) {
    ElMessage.error(error instanceof ApiException ? error.message : '保存失败')
  }
}

const grantVisible = ref(false)
const grant = reactive<{
  username: string
  kind: 'points' | 'days'
  points: number
  days: number
}>({
  username: '',
  kind: 'points',
  points: manualGrantDefault.value,
  days: 30,
})

function openGrant(user: ManagedUser) {
  grant.username = user.username
  grant.kind = 'points'
  grant.points = manualGrantDefault.value
  grant.days = 30
  grantVisible.value = true
}

async function submitGrant() {
  try {
    await walletApi.grant({
      username: grant.username,
      kind: grant.kind,
      points: grant.kind === 'points' ? grant.points : 0,
      days: grant.kind === 'days' ? grant.days : 0,
    })
    ElMessage.success(grant.kind === 'days' ? '无限使用天数已发放' : '积分已发放')
    grantVisible.value = false
    await loadUsers()
  } catch (error) {
    ElMessage.error(error instanceof ApiException ? error.message : '发放失败')
  }
}

onMounted(async () => {
  await Promise.all([loadPointsPolicy(), loadRoles(), loadUsers()])
})
</script>

<template>
  <div>
    <PageHeader title="用户管理" description="管理平台用户、积分、状态与角色。">
      <template #actions>
        <el-button @click="loadUsers">刷新</el-button>
      </template>
    </PageHeader>

    <div class="app-card p-1">
      <el-table v-loading="loading" :data="users" style="width: 100%">
        <el-table-column label="用户名" min-width="140" prop="username" />
        <el-table-column label="角色" width="120" align="center">
          <template #default="{ row }">
            <el-tag
              size="small"
              :type="row.role_is_system ? 'info' : 'success'"
            >
              {{ row.role_name || row.role }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.status === 'active' ? 'success' : 'info'">
              {{ row.status === 'active' ? '正常' : '已禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="积分" width="100" prop="points" align="center" />
        <el-table-column label="天数到期时间" min-width="160" align="center">
          <template #default="{ row }">
            <el-tag
              v-if="(row.unlimited_expires_at || 0) > Math.floor(Date.now() / 1000)"
              size="small"
              type="warning"
              effect="light"
            >
              {{ formatDateTime(row.unlimited_expires_at) }}
            </el-tag>
            <span v-else class="text-xs text-ink-muted">未开通</span>
          </template>
        </el-table-column>
        <el-table-column label="使用次数" width="110" align="center">
          <template #default="{ row }">{{ row.usage_count ?? 0 }}</template>
        </el-table-column>
        <el-table-column label="邮箱" min-width="160" align="center">
          <template #default="{ row }">{{ row.email || '—' }}</template>
        </el-table-column>
        <el-table-column label="邀请人" min-width="140" show-overflow-tooltip align="center">
          <template #default="{ row }">{{ row.invited_by || '—' }}</template>
        </el-table-column>
        <el-table-column label="注册时间" width="170" align="center">
          <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="160" align="right">
          <template #default="{ row }">
            <template v-if="canManageUser(row)">
              <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
              <el-button v-if="canGrantPoints" link type="primary" @click="openGrant(row)">发放权益</el-button>
            </template>
            <span v-else class="text-xs text-ink-muted">无权限</span>
          </template>
        </el-table-column>
        <template #empty><el-empty description="暂无用户" /></template>
      </el-table>
    </div>

    <el-dialog v-model="editVisible" :title="`编辑用户 · ${editing.username}`" width="420px">
      <el-form label-position="top">
        <el-form-item label="角色">
          <el-select v-model="editing.role" :disabled="!canAssignRoles" class="w-full">
            <el-option v-for="role in roles" :key="role.role_id" :value="role.role_id" :label="role.name" />
          </el-select>
          <div v-if="!canAssignRoles" class="mt-1 text-xs text-ink-muted">仅超级管理员可调整角色</div>
        </el-form-item>
        <el-form-item label="积分">
          <el-input-number v-model="editing.points" :min="0" class="w-full" />
        </el-form-item>
        <el-form-item label="到期时间">
          <el-date-picker
            v-model="editing.unlimited_expires_at_ms"
            type="datetime"
            value-format="x"
            placeholder="留空或设为过去时间即未开通"
            clearable
            class="w-full"
          />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="editing.status" class="w-full">
            <el-option value="active" label="正常" />
            <el-option value="disabled" label="禁用" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" @click="submitEdit">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="grantVisible" :title="`发放权益 · ${grant.username}`" width="420px">
      <el-form label-position="top">
        <el-form-item label="发放类型">
          <el-radio-group v-model="grant.kind" class="w-full">
            <el-radio-button value="points">积分充值</el-radio-button>
            <el-radio-button value="days">无限使用天数</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="grant.kind === 'points'" label="积分数量">
          <el-input-number v-model="grant.points" :min="1" class="w-full" />
        </el-form-item>
        <el-form-item v-else label="有效天数">
          <el-input-number v-model="grant.days" :min="1" class="w-full" />
          <div class="mt-1 text-xs text-ink-muted">增加的天数将自动在用户当前会员到期时间或当前时间上顺延。</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="grantVisible = false">取消</el-button>
        <el-button type="primary" @click="submitGrant">发放</el-button>
      </template>
    </el-dialog>
  </div>
</template>
