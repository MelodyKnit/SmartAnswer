<script setup lang="ts">
/** 找回密码页：申请重置令牌并设置新密码。 */
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'
import { authApi } from '@/api/endpoints'
import { ApiException } from '@/api/http'
import AuthShell from './AuthShell.vue'

const router = useRouter()
const step = ref(1)
const loading = ref(false)
const reqRef = ref<FormInstance>()
const confirmRef = ref<FormInstance>()
const form = reactive({ username: '', token: '', new_password: '', confirm: '' })

const samePassword = (_: unknown, value: string, callback: (error?: Error) => void) => {
  value === form.new_password ? callback() : callback(new Error('两次输入的密码不一致'))
}

const reqRules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
}
const confirmRules: FormRules = {
  token: [{ required: true, message: '请输入重置令牌', trigger: 'blur' }],
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 8, message: '密码至少 8 位', trigger: 'blur' },
  ],
  confirm: [{ required: true, validator: samePassword, trigger: 'blur' }],
}

async function requestReset() {
  if (!reqRef.value) return
  const valid = await reqRef.value.validate().catch(() => false)
  if (!valid) return
  loading.value = true
  try {
    const res = await authApi.resetRequest(form.username)
    ElMessage.success(res.message)
    step.value = 2
  } catch (err) {
    ElMessage.error(err instanceof ApiException ? err.message : '请求失败')
  } finally {
    loading.value = false
  }
}

async function confirmReset() {
  if (!confirmRef.value) return
  const valid = await confirmRef.value.validate().catch(() => false)
  if (!valid) return
  loading.value = true
  try {
    const res = await authApi.resetConfirm({ username: form.username, token: form.token, new_password: form.new_password })
    ElMessage.success(res.message)
    router.replace({ name: 'login' })
  } catch (err) {
    ElMessage.error(err instanceof ApiException ? err.message : '重置失败')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <AuthShell title="找回密码" subtitle="本地部署场景：重置令牌将打印在服务器控制台，请向本机管理员获取">
    <el-steps :active="step - 1" finish-status="success" simple class="mb-6">
      <el-step title="申请令牌" />
      <el-step title="设置新密码" />
    </el-steps>

    <el-form v-if="step === 1" ref="reqRef" :model="form" :rules="reqRules" size="large" @submit.prevent="requestReset">
      <el-form-item prop="username">
        <el-input v-model="form.username" placeholder="账号用户名" :prefix-icon="'User'" />
      </el-form-item>
      <el-button type="primary" class="w-full" size="large" :loading="loading" @click="requestReset">申请重置令牌</el-button>
    </el-form>

    <el-form v-else ref="confirmRef" :model="form" :rules="confirmRules" size="large" @submit.prevent="confirmReset">
      <el-alert type="info" :closable="false" class="mb-4" title="令牌 30 分钟内有效，请在服务器控制台查看后填入下方。" />
      <el-form-item prop="token"><el-input v-model="form.token" placeholder="重置令牌" :prefix-icon="'Ticket'" /></el-form-item>
      <el-form-item prop="new_password"><el-input v-model="form.new_password" type="password" show-password placeholder="新密码（至少 8 位）" :prefix-icon="'Lock'" /></el-form-item>
      <el-form-item prop="confirm"><el-input v-model="form.confirm" type="password" show-password placeholder="确认新密码" :prefix-icon="'Lock'" /></el-form-item>
      <div class="flex gap-3">
        <el-button class="flex-1" size="large" @click="step = 1">上一步</el-button>
        <el-button type="primary" class="flex-1" size="large" :loading="loading" @click="confirmReset">重置密码</el-button>
      </div>
    </el-form>

    <template #footer>
      想起密码了？
      <router-link to="/login" class="font-medium text-brand-600 hover:underline">返回登录</router-link>
    </template>
  </AuthShell>
</template>
