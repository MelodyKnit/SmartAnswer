<script setup lang="ts">
/** 注册页：用户名/密码/确认密码 + 可选邮箱 + 可选邀请码，含实时校验。 */
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { FormInstance, FormItemRule, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { ApiException } from '@/api/http'
import { authApi } from '@/api/endpoints'
import AuthShell from './AuthShell.vue'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

const formRef = ref<FormInstance>()
const loading = ref(false)
const registrationEnabled = ref(true)
const statusLoading = ref(false)
const form = reactive({ username: '', password: '', confirm: '', email: '', invite_code: '' })

onMounted(async () => {
  const invite = route.query.invite
  if (typeof invite === 'string') form.invite_code = invite
  statusLoading.value = true
  try {
    const status = await authApi.registerStatus()
    registrationEnabled.value = status.registration_enabled
  } catch {
    registrationEnabled.value = true
  } finally {
    statusLoading.value = false
  }
})

const validateConfirm: FormItemRule['validator'] = (_rule, value, callback) => {
  if (value !== form.password) callback(new Error('两次输入的密码不一致'))
  else callback()
}

const rules: FormRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    {
      pattern: /^[A-Za-z0-9_\-一-龥]{3,32}$/,
      message: '用户名为 3-32 位，支持中文、字母、数字、下划线、连字符',
      trigger: 'blur',
    },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 8, message: '密码至少 8 位', trigger: 'blur' },
  ],
  confirm: [
    { required: true, message: '请再次输入密码', trigger: 'blur' },
    { validator: validateConfirm, trigger: 'blur' },
  ],
  email: [{ type: 'email', message: '邮箱格式不正确', trigger: 'blur' }],
}

async function submit() {
  if (!registrationEnabled.value) {
    ElMessage.warning('系统已关闭用户注册')
    return
  }
  if (!formRef.value) return
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  loading.value = true
  try {
    await auth.register(form.username, form.password, form.email || undefined, form.invite_code || undefined)
    ElMessage.success('注册成功，请登录')
    router.replace({ name: 'login' })
  } catch (err) {
    ElMessage.error(err instanceof ApiException ? err.message : '注册失败')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <AuthShell title="创建账号" subtitle="注册后即可创建 API Key 并接入答题能力">
    <el-alert
      v-if="!registrationEnabled"
      type="warning"
      :closable="false"
      class="mb-4"
      title="系统已关闭用户注册"
      description="请联系管理员创建账号或重新开启注册入口。"
    />
    <el-form ref="formRef" :model="form" :rules="rules" size="large" @submit.prevent="submit">
      <el-form-item prop="username">
        <el-input v-model="form.username" placeholder="用户名" :prefix-icon="'User'" />
      </el-form-item>
      <el-form-item prop="email">
        <el-input v-model="form.email" placeholder="邮箱（可选）" :prefix-icon="'Message'" />
      </el-form-item>
      <el-form-item prop="password">
        <el-input
          v-model="form.password"
          type="password"
          show-password
          placeholder="密码（至少 8 位）"
          :prefix-icon="'Lock'"
        />
      </el-form-item>
      <el-form-item prop="confirm">
        <el-input
          v-model="form.confirm"
          type="password"
          show-password
          placeholder="确认密码"
          :prefix-icon="'Lock'"
        />
      </el-form-item>
      <el-form-item prop="invite_code">
        <el-input v-model="form.invite_code" placeholder="邀请码（可选，填写后按当前系统策略发放奖励）" :prefix-icon="'Promotion'" @keyup.enter="submit" />
      </el-form-item>
      <el-button
        type="primary"
        class="w-full"
        size="large"
        :loading="loading || statusLoading"
        :disabled="!registrationEnabled"
        @click="submit"
      >
        注册
      </el-button>
    </el-form>
    <template #footer>
      已有账号？
      <router-link to="/login" class="font-medium text-brand-600 hover:underline">
        返回登录
      </router-link>
    </template>
  </AuthShell>
</template>
