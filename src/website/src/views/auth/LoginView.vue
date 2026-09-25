<script setup lang="ts">
/** 登录页：支持用户名或邮箱 + 密码，链接注册与找回密码。 */
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { ApiException } from '@/api/http'
import { authApi } from '@/api/endpoints'
import { useSiteStore } from '@/stores/site'
import AuthShell from './AuthShell.vue'
import SliderCaptcha from '@/components/auth/SliderCaptcha.vue'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const site = useSiteStore()

const formRef = ref<FormInstance>()
const loading = ref(false)
const registrationEnabled = ref(true)
const captchaRequired = ref(false)
const captchaRef = ref<InstanceType<typeof SliderCaptcha>>()
const form = reactive({ username: '', password: '', remember: true, captcha_token: '' })
const loginSubtitle = computed(() => `登录${site.title}，继续管理你的接入能力`)

onMounted(async () => {
  try {
    const status = await authApi.registerStatus()
    registrationEnabled.value = status.registration_enabled
  } catch {
    registrationEnabled.value = true
  }
})

function resetCaptcha() {
  form.captcha_token = ''
  void nextTick(() => captchaRef.value?.reset())
}

const rules: FormRules = {
  username: [{ required: true, message: '请输入用户名或邮箱', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function submit() {
  if (!formRef.value) return
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  if (captchaRequired.value && !form.captcha_token) {
    ElMessage.warning('请先完成滑块验证')
    return
  }
  loading.value = true
  try {
    await auth.login(form.username, form.password, form.remember, form.captcha_token)
    ElMessage.success('登录成功')
    const redirect = (route.query.redirect as string) || '/'
    router.replace(redirect)
  } catch (err) {
    if (
      err instanceof ApiException &&
      (err.metadata.require_captcha === true || ['CAPTCHA_REQUIRED', 'CAPTCHA_INVALID'].includes(err.code))
    ) {
      captchaRequired.value = true
      resetCaptcha()
    } else if (captchaRequired.value) {
      // 验证凭证为一次性使用，密码校验失败后需要重新完成一次验证。
      resetCaptcha()
    }
    ElMessage.error(err instanceof ApiException ? err.message : '登录失败')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <AuthShell title="欢迎回来" :subtitle="loginSubtitle">
    <el-form ref="formRef" :model="form" :rules="rules" size="large" @submit.prevent="submit">
      <el-form-item prop="username">
        <el-input v-model="form.username" placeholder="用户名或邮箱" :prefix-icon="'User'" />
      </el-form-item>
      <el-form-item prop="password">
        <el-input
          v-model="form.password"
          type="password"
          show-password
          placeholder="密码"
          :prefix-icon="'Lock'"
          @keyup.enter="submit"
        />
      </el-form-item>
      <div class="mb-4 flex items-center justify-between">
        <el-checkbox v-model="form.remember">记住我</el-checkbox>
        <router-link to="/forgot" class="text-sm text-brand-600 hover:underline">
          忘记密码？
        </router-link>
      </div>
      <el-form-item v-if="captchaRequired">
        <SliderCaptcha ref="captchaRef" :disabled="loading" @verified="form.captcha_token = $event" />
      </el-form-item>
      <el-button type="primary" class="w-full" size="large" :loading="loading" @click="submit">
        登录
      </el-button>
    </el-form>
    <template #footer>
      <div class="flex items-center justify-between text-sm">
        <span v-if="registrationEnabled">
          还没有账号？
          <router-link to="/register" class="font-medium text-brand-600 hover:underline">
            立即注册
          </router-link>
        </span>
        <span v-else></span>
        <router-link to="/help" class="text-xs text-ink-muted hover:text-brand-600 hover:underline inline-flex items-center gap-1">
          <el-icon :size="12"><QuestionFilled /></el-icon>
          帮助文档
        </router-link>
      </div>
    </template>
  </AuthShell>
</template>
