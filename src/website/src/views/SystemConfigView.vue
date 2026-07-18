<script setup lang="ts">
/** 系统配置：积分策略、账户与服务配置。仅超级管理员可访问与修改。
 *  敏感项后端只返回 *_configured 标志，不回明文；留空表示不修改。 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { billingApi, systemConfigApi } from '@/api/endpoints'
import { ApiException } from '@/api/http'
import PageHeader from '@/components/PageHeader.vue'
import SiteLogo from '@/components/SiteLogo.vue'
import { useSiteStore } from '@/stores/site'
import { getToken } from '@/api/http'

const loading = ref(false)
const saving = ref(false)
const route = useRoute()
const site = useSiteStore()

const uploadHeaders = computed(() => {
  const token = getToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
})

function handleLogoUploadSuccess(res: any) {
  if (res.ok && res.urls?.lg) {
    // 保存返回的大尺寸对应 logo URL 到表单
    form.site_logo_url = res.urls.lg
    ElMessage.success('Logo 上传并裁切成功！')
  } else {
    ElMessage.error(res.error?.message || '上传 Logo 失败')
  }
}

function handleLogoUploadError(err: any) {
  try {
    const parsed = JSON.parse(err.message)
    ElMessage.error(parsed.error?.message || '上传异常')
  } catch {
    ElMessage.error('上传 Logo 接口连接失败')
  }
}

/* 表单：明文字段直接编辑；密钥字段为“新值”，留空表示保持不变。 */
const form = reactive({
  site_title: '',
  site_logo_url: '',
  smart_proto_enabled: 'true',
  custom_proto_header: 'http',
  default_user_points: 100,
  invite_bonus_points: 0,
  manual_grant_default_points: 100,
  redeem_code_default_points: 50,
  answer_retry_times: 3,
  registration_enabled: 'true',
  registration_email_mode: 'optional',
  smtp_host: '',
  smtp_port: 465,
  smtp_security: 'ssl',
  smtp_username: '',
  smtp_password: '',
  smtp_password_configured: false,
  smtp_from_email: '',
  smtp_from_name: 'AI题库',
  email_code_ttl_minutes: 10,
  email_code_cooldown_seconds: 60,
  email_code_daily_limit: 5,
  email_code_ip_hourly_limit: 20,
  email_code_max_attempts: 5,
})

const billingForm = reactive({
  local_hit: 1,
  web_search: 2,
  llm_fallback: 3,
})

const previewLogoUrl = computed(() => {
  const value = form.site_logo_url.trim()
  if (!value) return ''
  if (value.startsWith('/') && !value.startsWith('//') && !/\s/.test(value)) return value
  if (/^https?:\/\/\S+$/i.test(value)) return value
  return ''
})

/** 返回 SMTP 配置中首个未满足的启用条件。 */
function smtpConfigurationIssue(): string | null {
  if (!form.smtp_host.trim()) return '请填写 SMTP 服务器'
  if (!Number.isInteger(form.smtp_port) || form.smtp_port < 1 || form.smtp_port > 65535) {
    return '请填写有效的 SMTP 端口'
  }
  if (!['ssl', 'starttls', 'none'].includes(form.smtp_security)) {
    return '请选择 SMTP 加密方式'
  }
  if (!form.smtp_username.trim()) return '请填写 SMTP 用户名'
  if (!form.smtp_password.trim() && !form.smtp_password_configured) {
    return '请填写 SMTP 密码'
  }
  if (!/^\S+@\S+\.\S+$/.test(form.smtp_from_email.trim())) {
    return '请填写有效的发件邮箱'
  }
  return null
}

/** 选择注册邮箱策略；验证码模式要求先完成 SMTP 配置。 */
function selectRegistrationEmailMode(value: 'optional' | 'required' | 'verified') {
  if (value !== 'verified') {
    form.registration_email_mode = value
    return
  }
  const issue = smtpConfigurationIssue()
  if (!issue) {
    form.registration_email_mode = value
    return
  }
  ElMessage.warning(`请先完成 SMTP 配置后再开启邮箱验证：${issue}`)
}

async function load() {
  loading.value = true
  try {
    const res = await systemConfigApi.get()
    const billing = await billingApi.get()
    // 大模型推理、联网搜索和 AI 学习缓存统一在“大模型配置”页维护。
    form.site_title = (res.config.site_title as string) || ''
    form.site_logo_url = (res.config.site_logo_url as string) || ''
    form.smart_proto_enabled = (res.config.smart_proto_enabled as string) || 'true'
    form.custom_proto_header = (res.config.custom_proto_header as string) || 'http'
    form.default_user_points = Number(res.config.default_user_points || 100)
    form.invite_bonus_points = Number(res.config.invite_bonus_points || 0)
    form.manual_grant_default_points = Number(res.config.manual_grant_default_points || 100)
    form.redeem_code_default_points = Number(res.config.redeem_code_default_points || 50)
    form.answer_retry_times = Number(res.config.answer_retry_times || 3)
    form.registration_enabled = (res.config.registration_enabled as string) || 'true'
    form.registration_email_mode = res.config.registration_email_mode || 'optional'
    form.smtp_host = (res.config.smtp_host as string) || ''
    form.smtp_port = Number(res.config.smtp_port || 465)
    form.smtp_security = (res.config.smtp_security as string) || 'ssl'
    form.smtp_username = (res.config.smtp_username as string) || ''
    form.smtp_password = ''
    form.smtp_password_configured = Boolean(res.config.smtp_password_configured)
    form.smtp_from_email = (res.config.smtp_from_email as string) || ''
    form.smtp_from_name = (res.config.smtp_from_name as string) || 'AI题库'
    form.email_code_ttl_minutes = Number(res.config.email_code_ttl_minutes || 10)
    form.email_code_cooldown_seconds = Number(res.config.email_code_cooldown_seconds || 60)
    form.email_code_daily_limit = Number(res.config.email_code_daily_limit || 5)
    form.email_code_ip_hourly_limit = Number(res.config.email_code_ip_hourly_limit || 20)
    form.email_code_max_attempts = Number(res.config.email_code_max_attempts || 5)
    billingForm.local_hit = Number(billing.billing.local_hit || 0)
    billingForm.web_search = Number(billing.billing.web_search || 0)
    billingForm.llm_fallback = Number(billing.billing.llm_fallback || 0)
  } finally {
    loading.value = false
  }
}

async function save() {
  // 后端仍执行最终校验；这里用于处理直接编辑字段后保存的场景。
  if (form.registration_email_mode === 'verified') {
    const issue = smtpConfigurationIssue()
    if (issue) {
      ElMessage.warning(`SMTP 配置不完整：${issue}`)
      return
    }
  }

  saving.value = true
  try {
    const body: Record<string, string> = {
      site_title: form.site_title,
      site_logo_url: form.site_logo_url,
      smart_proto_enabled: form.smart_proto_enabled,
      custom_proto_header: form.custom_proto_header,
      default_user_points: String(form.default_user_points),
      invite_bonus_points: String(form.invite_bonus_points),
      manual_grant_default_points: String(form.manual_grant_default_points),
      redeem_code_default_points: String(form.redeem_code_default_points),
      answer_retry_times: String(form.answer_retry_times),
      registration_enabled: form.registration_enabled,
      registration_email_mode: form.registration_email_mode,
      smtp_host: form.smtp_host,
      smtp_port: String(form.smtp_port),
      smtp_security: form.smtp_security,
      smtp_username: form.smtp_username,
      smtp_from_email: form.smtp_from_email,
      smtp_from_name: form.smtp_from_name,
      email_code_ttl_minutes: String(form.email_code_ttl_minutes),
      email_code_cooldown_seconds: String(form.email_code_cooldown_seconds),
      email_code_daily_limit: String(form.email_code_daily_limit),
      email_code_ip_hourly_limit: String(form.email_code_ip_hourly_limit),
      email_code_max_attempts: String(form.email_code_max_attempts),
    }
    if (form.smtp_password.trim()) {
      body.smtp_password = form.smtp_password
    }

    const updated = await systemConfigApi.update(body)
    site.applyConfig(updated.config)
    site.applyBrowserBrand(route.meta.title as string | undefined)
    await billingApi.update({
      local_hit: billingForm.local_hit,
      web_search: billingForm.web_search,
      llm_fallback: billingForm.llm_fallback,
    })
    ElMessage.success('配置已保存')
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
  <div v-loading="loading">
    <PageHeader title="系统配置" description="配置站点外观、积分策略、账户开关与服务协议。大模型相关能力请到“大模型配置”中维护。">
      <template #actions>
        <el-button type="primary" :loading="saving" @click="save">保存配置</el-button>
      </template>
    </PageHeader>

    <div class="space-y-4">
      <!-- 站点外观 -->
      <div class="app-card p-6">
        <h3 class="mb-4 text-base font-semibold text-ink">站点外观</h3>
        <div class="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_280px]">
          <el-form label-position="top" class="grid grid-cols-1 gap-x-6 md:grid-cols-2">
            <el-form-item label="网站标题">
              <el-input v-model="form.site_title" maxlength="40" show-word-limit placeholder="请输入网站标题" />
            </el-form-item>
            <el-form-item label="网站 Logo">
              <div class="flex flex-col gap-2">
                <el-upload
                  action="/api/system/logo/upload"
                  :headers="uploadHeaders"
                  accept="image/png, image/jpeg, image/jpg, image/webp"
                  :show-file-list="false"
                  :on-success="handleLogoUploadSuccess"
                  :on-error="handleLogoUploadError"
                >
                  <el-button type="primary">上传图片修改 Logo</el-button>
                </el-upload>
                <div class="text-xs text-ink-muted">
                  支持 png、jpg、jpeg、webp 格式，文件大小不超过 5MB，将自动裁剪为多分辨率正方形尺寸。
                </div>
              </div>
            </el-form-item>
          </el-form>
          <div class="rounded-xl border border-line bg-card-soft p-4">
            <div class="mb-3 text-xs font-medium text-ink-muted">预览</div>
            <div class="flex items-center gap-3">
              <SiteLogo :title="form.site_title" :logo-url="previewLogoUrl" />
              <div class="min-w-0">
                <div class="truncate text-base font-semibold text-ink">{{ form.site_title || '网站标题' }}</div>
                <div class="truncate text-xs text-ink-muted">{{ form.site_logo_url ? '已配置自定义 Logo' : '使用默认图标' }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 积分策略 -->
      <div class="app-card p-6">
        <h3 class="mb-4 text-base font-semibold text-ink">积分策略</h3>
        <el-form label-position="top" class="grid grid-cols-1 gap-x-6 md:grid-cols-3">
          <el-form-item label="题库命中扣费">
            <el-input-number v-model="billingForm.local_hit" :min="0" class="w-full" />
          </el-form-item>
          <el-form-item label="联网检索扣费">
            <el-input-number v-model="billingForm.web_search" :min="0" class="w-full" />
          </el-form-item>
          <el-form-item label="大模型兜底扣费">
            <el-input-number v-model="billingForm.llm_fallback" :min="0" class="w-full" />
          </el-form-item>
          <el-form-item label="新用户初始积分">
            <el-input-number v-model="form.default_user_points" :min="0" class="w-full" />
          </el-form-item>
          <el-form-item label="邀请码奖励积分">
            <el-input-number v-model="form.invite_bonus_points" :min="0" class="w-full" />
          </el-form-item>
          <el-form-item label="手动发放默认积分">
            <el-input-number v-model="form.manual_grant_default_points" :min="1" class="w-full" />
          </el-form-item>
          <el-form-item label="兑换码默认积分">
            <el-input-number v-model="form.redeem_code_default_points" :min="1" class="w-full" />
          </el-form-item>
          <el-form-item label="答题报错重试次数">
            <el-input-number v-model="form.answer_retry_times" :min="0" :max="10" class="w-full" />
          </el-form-item>
        </el-form>
        <p class="text-xs text-ink-muted">
          查题扣费实时影响 OCS/API 调用；默认积分用于后台表单预填和后续注册奖励策略。答题报错重试仅在 AI/联网增强链路抛异常时生效，0 表示不重试。
        </p>
      </div>

      <!-- 账户配置 -->
      <div class="app-card p-6">
        <h3 class="mb-4 text-base font-semibold text-ink">账户配置</h3>
        <el-form label-position="top" class="grid grid-cols-1 gap-x-6 md:grid-cols-2">
          <el-form-item label="允许用户注册">
            <el-switch v-model="form.registration_enabled" active-value="true" inactive-value="false" />
          </el-form-item>
          <el-form-item label="注册邮箱策略">
            <el-radio-group
              :model-value="form.registration_email_mode"
              @update:model-value="selectRegistrationEmailMode"
            >
              <el-radio-button value="optional">邮箱可选</el-radio-button>
              <el-radio-button value="required">邮箱必填，不验证</el-radio-button>
              <el-radio-button value="verified">邮箱必填并验证</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="SMTP 服务器">
            <el-input v-model="form.smtp_host" placeholder="smtp.example.com" />
          </el-form-item>
          <el-form-item label="SMTP 端口">
            <el-input-number v-model="form.smtp_port" :min="1" :max="65535" class="w-full" />
          </el-form-item>
          <el-form-item label="SMTP 加密方式">
            <el-select v-model="form.smtp_security" class="w-full">
              <el-option value="ssl" label="SSL" />
              <el-option value="starttls" label="STARTTLS" />
              <el-option value="none" label="不加密" />
            </el-select>
          </el-form-item>
          <el-form-item label="SMTP 用户名">
            <el-input v-model="form.smtp_username" placeholder="通常为邮箱账号" />
          </el-form-item>
          <el-form-item :label="form.smtp_password_configured ? 'SMTP 密码（已配置）' : 'SMTP 密码'">
            <el-input
              v-model="form.smtp_password"
              type="password"
              show-password
              placeholder="留空保持不变"
            />
          </el-form-item>
          <el-form-item label="发件邮箱">
            <el-input v-model="form.smtp_from_email" placeholder="noreply@example.com" />
          </el-form-item>
          <el-form-item label="发件人名称">
            <el-input v-model="form.smtp_from_name" maxlength="40" placeholder="AI题库" />
          </el-form-item>
          <el-form-item label="验证码有效分钟">
            <el-input-number v-model="form.email_code_ttl_minutes" :min="1" :max="60" class="w-full" />
          </el-form-item>
          <el-form-item label="发送冷却秒数">
            <el-input-number
              v-model="form.email_code_cooldown_seconds"
              :min="0"
              :max="3600"
              class="w-full"
            />
          </el-form-item>
          <el-form-item label="单邮箱每日上限">
            <el-input-number v-model="form.email_code_daily_limit" :min="1" :max="100" class="w-full" />
          </el-form-item>
          <el-form-item label="单 IP 每小时上限">
            <el-input-number
              v-model="form.email_code_ip_hourly_limit"
              :min="1"
              :max="500"
              class="w-full"
            />
          </el-form-item>
          <el-form-item label="验证码最大错误次数">
            <el-input-number v-model="form.email_code_max_attempts" :min="1" :max="20" class="w-full" />
          </el-form-item>
        </el-form>
        <p class="text-xs text-ink-muted">
          开启邮箱验证后，新用户注册必须通过白名单邮箱接收验证码；SMTP 密码留空不会覆盖已有配置。
        </p>
      </div>

      <!-- 服务配置 -->
      <div class="app-card p-6">
        <h3 class="mb-4 text-base font-semibold text-ink">服务配置</h3>
        <el-form label-position="top" class="grid grid-cols-1 gap-x-6 md:grid-cols-2">
          <el-form-item label="智能检测协议头（优先获取 X-Forwarded-Proto 与 Host）">
            <el-switch v-model="form.smart_proto_enabled" active-value="true" inactive-value="false" />
          </el-form-item>
          <el-form-item label="手动协议头">
            <el-select v-model="form.custom_proto_header" class="w-full" :disabled="form.smart_proto_enabled === 'true'">
              <el-option value="http" label="http" />
              <el-option value="https" label="https" />
            </el-select>
          </el-form-item>
        </el-form>
        <p class="text-xs text-ink-muted">
          开启智能检测后，系统会自动根据客户端发送的 HTTP/HTTPS 头或穿透网关识别协议。
        </p>
      </div>
    </div>
  </div>
</template>
