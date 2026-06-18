<script setup lang="ts">
/** 系统配置：积分策略与服务协议配置。仅超级管理员可访问与修改。
 *  敏感项后端只返回 *_configured 标志，不回明文；留空表示不修改。 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { billingApi, systemConfigApi } from '@/api/endpoints'
import { ApiException } from '@/api/http'
import PageHeader from '@/components/PageHeader.vue'

const loading = ref(false)
const saving = ref(false)

/* 表单：明文字段直接编辑；密钥字段为“新值”，留空表示保持不变。 */
const form = reactive({
  smart_proto_enabled: 'true',
  custom_proto_header: 'http',
  default_user_points: 100,
  invite_bonus_points: 0,
  manual_grant_default_points: 100,
  redeem_code_default_points: 50,
})

const billingForm = reactive({
  local_hit: 1,
  web_search: 2,
  llm_fallback: 3,
})

async function load() {
  loading.value = true
  try {
    const res = await systemConfigApi.get()
    const billing = await billingApi.get()
    // 大模型推理、联网搜索和 AI 学习缓存统一在“大模型配置”页维护。
    form.smart_proto_enabled = (res.config.smart_proto_enabled as string) || 'true'
    form.custom_proto_header = (res.config.custom_proto_header as string) || 'http'
    form.default_user_points = Number(res.config.default_user_points || 100)
    form.invite_bonus_points = Number(res.config.invite_bonus_points || 0)
    form.manual_grant_default_points = Number(res.config.manual_grant_default_points || 100)
    form.redeem_code_default_points = Number(res.config.redeem_code_default_points || 50)
    billingForm.local_hit = Number(billing.billing.local_hit || 0)
    billingForm.web_search = Number(billing.billing.web_search || 0)
    billingForm.llm_fallback = Number(billing.billing.llm_fallback || 0)
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  try {
    const body: Record<string, string> = {
      smart_proto_enabled: form.smart_proto_enabled,
      custom_proto_header: form.custom_proto_header,
      default_user_points: String(form.default_user_points),
      invite_bonus_points: String(form.invite_bonus_points),
      manual_grant_default_points: String(form.manual_grant_default_points),
      redeem_code_default_points: String(form.redeem_code_default_points),
    }

    await systemConfigApi.update(body)
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
    <PageHeader title="系统配置" description="配置积分策略与服务协议。大模型推理、联网搜索和 AI 学习缓存请到“大模型配置”中维护。">
      <template #actions>
        <el-button type="primary" :loading="saving" @click="save">保存配置</el-button>
      </template>
    </PageHeader>

    <div class="space-y-4">
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
        </el-form>
        <p class="text-xs text-ink-muted">
          查题扣费实时影响 OCS/API 调用；默认积分用于后台表单预填和后续注册奖励策略。
        </p>
      </div>

      <!-- 服务协议配置 -->
      <div class="app-card p-6">
        <h3 class="mb-4 text-base font-semibold text-ink">服务协议配置</h3>
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
          开启智能检测后，系统会自动根据客户端发送的 HTTP/HTTPS 头或穿透网关识别协议。关闭智能检测时，可手动指定以该协议头作为基础接入 URL。
        </p>
      </div>
    </div>
  </div>
</template>
