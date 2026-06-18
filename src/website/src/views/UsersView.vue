<script setup lang="ts">
/** 用户管理：列出用户、调整状态/角色/积分，并支持管理员手动发放积分。 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { billingApi, userApi, walletApi } from '@/api/endpoints'
import type { User } from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import { ApiException } from '@/api/http'
import { formatDateTime } from '@/utils/format'
import PageHeader from '@/components/PageHeader.vue'

const auth = useAuthStore()
const loading = ref(false)
const users = ref<User[]>([])
const manualGrantDefault = ref(1)

const ROLE_LABELS: Record<string, string> = {
  superadmin: '超级管理员',
  admin: '管理员',
  user: '普通用户',
}

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
  try {
    const res = await billingApi.pointsPolicy()
    manualGrantDefault.value = res.points_policy.manual_grant_default_points
  } catch {
    // 积分策略只用于表单默认值，加载失败不影响用户管理主流程。
  }
}

const editVisible = ref(false)
const editing = reactive({
  username: '',
  role: 'user',
  points: 0,
  status: 'active',
  original_role: 'user',
})

function openEdit(user: User) {
  editing.username = user.username
  editing.role = user.role
  editing.original_role = user.role
  editing.points = user.points
  editing.status = user.status
  editVisible.value = true
}

async function submitEdit() {
  try {
    const body: Record<string, unknown> = { points: editing.points, status: editing.status }
    if (auth.isSuperAdmin && editing.role !== editing.original_role) {
      body.role = editing.role
    }
    await userApi.update(editing.username, body)
    ElMessage.success('已保存')
    editVisible.value = false
    await loadUsers()
  } catch (error) {
    ElMessage.error(error instanceof ApiException ? error.message : '保存失败')
  }
}

const grantVisible = ref(false)
const grant = reactive({ username: '', points: manualGrantDefault.value })

function openGrant(user: User) {
  grant.username = user.username
  grant.points = manualGrantDefault.value
  grantVisible.value = true
}

async function submitGrant() {
  try {
    await walletApi.grant({
      username: grant.username,
      kind: 'points',
      points: grant.points,
    })
    ElMessage.success('积分已发放')
    grantVisible.value = false
    await loadUsers()
  } catch (error) {
    ElMessage.error(error instanceof ApiException ? error.message : '发放失败')
  }
}

onMounted(async () => {
  await Promise.all([loadPointsPolicy(), loadUsers()])
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
        <el-table-column label="角色" width="120">
          <template #default="{ row }">
            <el-tag
              size="small"
              :type="row.role === 'superadmin' ? 'danger' : row.role === 'admin' ? 'warning' : 'info'"
            >
              {{ ROLE_LABELS[row.role] || row.role }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="row.status === 'active' ? 'success' : 'info'">
              {{ row.status === 'active' ? '正常' : '已禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="积分" width="100" prop="points" />
        <el-table-column label="邮箱" min-width="160">
          <template #default="{ row }">{{ row.email || '—' }}</template>
        </el-table-column>
        <el-table-column label="注册时间" width="170">
          <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="160" align="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link type="primary" @click="openGrant(row)">发放积分</el-button>
          </template>
        </el-table-column>
        <template #empty><el-empty description="暂无用户" /></template>
      </el-table>
    </div>

    <el-dialog v-model="editVisible" :title="`编辑用户 · ${editing.username}`" width="420px">
      <el-form label-position="top">
        <el-form-item label="角色">
          <el-select v-model="editing.role" :disabled="!auth.isSuperAdmin" class="w-full">
            <el-option value="user" label="普通用户" />
            <el-option value="admin" label="管理员" />
            <el-option value="superadmin" label="超级管理员" />
          </el-select>
          <div v-if="!auth.isSuperAdmin" class="mt-1 text-xs text-ink-muted">仅超级管理员可调整角色</div>
        </el-form-item>
        <el-form-item label="积分">
          <el-input-number v-model="editing.points" :min="0" class="w-full" />
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

    <el-dialog v-model="grantVisible" :title="`发放积分 · ${grant.username}`" width="420px">
      <el-form label-position="top">
        <el-form-item label="积分数量">
          <el-input-number v-model="grant.points" :min="1" class="w-full" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="grantVisible = false">取消</el-button>
        <el-button type="primary" @click="submitGrant">发放</el-button>
      </template>
    </el-dialog>
  </div>
</template>
