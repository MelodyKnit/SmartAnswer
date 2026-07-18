<script setup lang="ts">
/** 注册页：用户名、密码、邮箱策略与邀请码。 */
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
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
const emailRegistrationMode = ref<'optional' | 'required' | 'verified'>('optional')
const emailVerificationEnabled = ref(false)
const statusLoading = ref(false)
const sendingEmailCode = ref(false)
const emailCountdown = ref(0)
let countdownTimer: number | undefined
const form = reactive({
  username: '',
  password: '',
  confirm: '',
  email: '',
  email_code: '',
  invite_code: '',
})

const emailRequired = computed(() => emailRegistrationMode.value !== 'optional')
const emailPlaceholder = '邮箱'
const emailCodeButtonText = computed(() => {
  if (emailCountdown.value > 0) return `${emailCountdown.value}s`
  return '发送验证码'
})

onMounted(async () => {
  const invite = route.query.invite
  if (typeof invite === 'string') form.invite_code = invite
  statusLoading.value = true
  try {
    const status = await authApi.registerStatus()
    registrationEnabled.value = status.registration_enabled
    emailRegistrationMode.value = status.email_registration_mode
    emailVerificationEnabled.value = status.email_verification_enabled
  } catch {
    registrationEnabled.value = true
    emailRegistrationMode.value = 'optional'
    emailVerificationEnabled.value = false
  } finally {
    statusLoading.value = false
  }
})

onBeforeUnmount(() => {
  if (countdownTimer !== undefined) window.clearInterval(countdownTimer)
})

const validateConfirm: FormItemRule['validator'] = (_rule, value, callback) => {
  if (value !== form.password) callback(new Error('两次输入的密码不一致'))
  else callback()
}

const validateEmail: FormItemRule['validator'] = (_rule, value, callback) => {
  if (emailRequired.value && !String(value || '').trim()) {
    callback(new Error('请输入邮箱'))
    return
  }
  callback()
}

const validateEmailCode: FormItemRule['validator'] = (_rule, value, callback) => {
  if (emailVerificationEnabled.value && !String(value || '').trim()) {
    callback(new Error('请输入邮箱验证码'))
    return
  }
  callback()
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
  email: [
    { validator: validateEmail, trigger: 'blur' },
    { type: 'email', message: '邮箱格式不正确', trigger: 'blur' },
  ],
  email_code: [{ validator: validateEmailCode, trigger: 'blur' }],
}

function startEmailCountdown(seconds = 60) {
  const normalizedSeconds = Math.max(0, Math.floor(seconds))
  emailCountdown.value = normalizedSeconds
  if (countdownTimer !== undefined) window.clearInterval(countdownTimer)
  if (normalizedSeconds <= 0) {
    countdownTimer = undefined
    return
  }
  countdownTimer = window.setInterval(() => {
    emailCountdown.value -= 1
    if (emailCountdown.value <= 0 && countdownTimer !== undefined) {
      window.clearInterval(countdownTimer)
      countdownTimer = undefined
    }
  }, 1000)
}

async function sendEmailCode() {
  if (!registrationEnabled.value) {
    ElMessage.warning('系统已关闭用户注册')
    return
  }
  if (!formRef.value || sendingEmailCode.value || emailCountdown.value > 0) return
  const validEmail = await formRef.value.validateField('email').catch(() => false)
  if (validEmail === false) return

  // 前端防御：限制同一个邮箱在前端本地被频繁连续发送（即使刷新页面仍然以冷却定时器为准）
  const storageKey = `email_cooldown_${form.email.trim().toLowerCase()}`
  const now = Date.now()
  const val = sessionStorage.getItem(storageKey)
  if (val) {
    const expireTime = Number(val)
    if (now < expireTime) {
      const waitSec = Math.ceil((expireTime - now) / 1000)
      ElMessage.warning(`该邮箱发送频率过快，请等待 ${waitSec} 秒后重试`)
      return
    }
  }

  sendingEmailCode.value = true
  try {
    const res = await authApi.sendEmailVerificationCode({ email: form.email })
    ElMessage.success('验证码已发送，请查看邮箱')
    const cooldownSeconds = Math.max(0, Math.floor(res.cooldown_seconds ?? 60))
    if (cooldownSeconds > 0) {
      sessionStorage.setItem(storageKey, String(Date.now() + cooldownSeconds * 1000))
    } else {
      sessionStorage.removeItem(storageKey)
    }
    startEmailCountdown(cooldownSeconds)
  } catch (err) {
    ElMessage.error(err instanceof ApiException ? err.message : '验证码发送失败')
  } finally {
    sendingEmailCode.value = false
  }
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
    await auth.register(
      form.username,
      form.password,
      form.email || undefined,
      form.invite_code || undefined,
      form.email_code || undefined,
    )
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
        <el-input v-model="form.email" :placeholder="emailPlaceholder" :prefix-icon="'Message'" />
      </el-form-item>
      <el-form-item v-if="emailVerificationEnabled" prop="email_code">
        <div class="flex w-full gap-2">
          <el-input
            v-model="form.email_code"
            class="flex-1"
            maxlength="6"
            placeholder="邮箱验证码"
            :prefix-icon="'Ticket'"
          />
          <el-button
            class="shrink-0"
            :loading="sendingEmailCode"
            :disabled="emailCountdown > 0"
            @click="sendEmailCode"
          >
            {{ emailCodeButtonText }}
          </el-button>
        </div>
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
