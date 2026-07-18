<script setup lang="ts">
/** 个人中心：展示账号信息、修改昵称、修改密码、查看邀请码。
 *  通过 tabs 标签页将原本堆积的内容分流，提升界面美感和操作体验。 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import type { FormInstance, FormItemRule, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'
import { userApi } from '@/api/endpoints'
import { useAuthStore } from '@/stores/auth'
import { ApiException } from '@/api/http'
import { formatDateTime } from '@/utils/format'
import PageHeader from '@/components/PageHeader.vue'

const auth = useAuthStore()
const router = useRouter()

const activeTab = ref('profile')
const inviteCodeRefreshing = ref(false)

const roleLabel = computed(() => {
  switch (auth.role) {
    case 'superadmin':
      return '超级管理员'
    case 'admin':
      return '管理员'
    default:
      return '普通用户'
  }
})

const inviteLink = computed(() => {
  const code = auth.user?.invite_code || ''
  if (!code) return ''
  return `${window.location.origin}/register?invite=${code}`
})
const inviteBonusPoints = computed(() => auth.billing?.invite_bonus_points ?? 0)
const inviteBonusTitle = computed(() =>
  inviteBonusPoints.value > 0
    ? `邀请新成员加入：各得 ${inviteBonusPoints.value} 积分！`
    : '邀请新成员加入'
)
const inviteBonusDescription = computed(() =>
  inviteBonusPoints.value > 0
    ? `成功邀请 1 人，您和受邀用户各获得 ${inviteBonusPoints.value} 积分。`
    : '分享您的专属邀请链接或邀请码给好友。当好友通过该邀请码成功注册账号后，系统会记录您的邀请关系。'
)

/* 修改昵称 */
const nameEditing = ref(false)
const nameSaving = ref(false)
const newName = ref('')

function startEditName() {
  newName.value = auth.user?.display_name || auth.user?.username || ''
  nameEditing.value = true
}

async function saveName() {
  if (!newName.value.trim()) {
    ElMessage.warning('昵称不能为空')
    return
  }
  nameSaving.value = true
  try {
    await userApi.updateProfile(newName.value.trim())
    await auth.refreshProfile()
    ElMessage.success('昵称已更新')
    nameEditing.value = false
  } catch (err) {
    ElMessage.error(err instanceof ApiException ? err.message : '更新失败')
  } finally {
    nameSaving.value = false
  }
}

/* 修改密码 */
const pwdRef = ref<FormInstance>()
const pwdSaving = ref(false)
const pwd = reactive({ old_password: '', new_password: '', confirm: '' })

const validateConfirm: FormItemRule['validator'] = (_rule, value, callback) => {
  if (value !== pwd.new_password) callback(new Error('两次输入的密码不一致'))
  else callback()
}

const pwdRules: FormRules = {
  old_password: [{ required: true, message: '请输入原密码', trigger: 'blur' }],
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 8, message: '密码至少 8 位', trigger: 'blur' },
  ],
  confirm: [{ required: true, validator: validateConfirm, trigger: 'blur' }],
}

async function changePassword() {
  if (!pwdRef.value) return
  const valid = await pwdRef.value.validate().catch(() => false)
  if (!valid) return
  pwdSaving.value = true
  try {
    await userApi.changePassword({
      old_password: pwd.old_password,
      new_password: pwd.new_password,
    })
    ElMessage.success('密码已修改，请重新登录')
    await auth.logout()
    router.replace({ name: 'login' })
  } catch (err) {
    ElMessage.error(err instanceof ApiException ? err.message : '修改失败')
  } finally {
    pwdSaving.value = false
  }
}

async function copy(text: string) {
  if (!text) {
    ElMessage.warning('暂无可复制内容')
    return
  }
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.warning('复制失败，请手动复制')
  }
}

async function refreshInviteCode() {
  inviteCodeRefreshing.value = true
  try {
    const res = await userApi.ensureInviteCode()
    auth.user = res.user
    await auth.refreshProfile()
    ElMessage.success('邀请码已生成')
  } catch (err) {
    ElMessage.error(err instanceof ApiException ? err.message : '生成邀请码失败')
  } finally {
    inviteCodeRefreshing.value = false
  }
}

onMounted(() => {
  void auth.refreshProfile()
})
</script>

<template>
  <div>
    <PageHeader title="个人中心" description="查看基本资料，管理安全设置并分享推广邀请以获得积分奖励。" />

    <!-- 侧边导航与内容页相结合的高级 Tab 布局 -->
    <div class="flex flex-col gap-6 lg:flex-row">
      <!-- 左侧卡片：包含个人卡片以及侧边 Tabs -->
      <div class="w-full shrink-0 lg:w-80">
        <div class="app-card p-6 text-center">
          <div class="relative mx-auto mb-4 h-20 w-20">
            <el-avatar :size="80" class="!bg-brand-500 !text-2xl shadow-md">
              {{ (auth.user?.display_name || auth.user?.username || 'U')[0].toUpperCase() }}
            </el-avatar>
            <div class="absolute -bottom-1 -right-1 flex h-6 w-6 items-center justify-center rounded-full bg-brand-600 text-white shadow">
              <el-icon :size="12"><User /></el-icon>
            </div>
          </div>
          <h2 class="text-lg font-bold text-ink">{{ auth.user?.display_name || auth.user?.username }}</h2>
          <div class="mt-1 flex items-center justify-center gap-1.5">
            <el-tag size="small" type="primary" effect="plain">{{ roleLabel }}</el-tag>
            <el-tag size="small" type="success" effect="plain">积分: {{ auth.user?.points ?? 0 }}</el-tag>
          </div>

          <div class="mt-8 border-t border-line pt-4">
            <div 
              class="flex cursor-pointer items-center justify-between rounded-lg px-3 py-2 text-sm font-medium transition-all"
              :class="activeTab === 'profile' ? 'bg-brand-50 text-brand-600 dark:bg-brand-100' : 'text-ink-soft hover:bg-canvas'"
              @click="activeTab = 'profile'"
            >
              <span class="flex items-center gap-2">
                <el-icon><User /></el-icon> 基础资料
              </span>
              <el-icon :size="12"><ArrowRight /></el-icon>
            </div>
            <div 
              class="mt-1 flex cursor-pointer items-center justify-between rounded-lg px-3 py-2 text-sm font-medium transition-all"
              :class="activeTab === 'security' ? 'bg-brand-50 text-brand-600 dark:bg-brand-100' : 'text-ink-soft hover:bg-canvas'"
              @click="activeTab = 'security'"
            >
              <span class="flex items-center gap-2">
                <el-icon><Lock /></el-icon> 安全设置
              </span>
              <el-icon :size="12"><ArrowRight /></el-icon>
            </div>
            <div 
              class="mt-1 flex cursor-pointer items-center justify-between rounded-lg px-3 py-2 text-sm font-medium transition-all"
              :class="activeTab === 'invite' ? 'bg-brand-50 text-brand-600 dark:bg-brand-100' : 'text-ink-soft hover:bg-canvas'"
              @click="activeTab = 'invite'"
            >
              <span class="flex items-center gap-2">
                <el-icon><Share /></el-icon> 推广邀请
              </span>
              <el-icon :size="12"><ArrowRight /></el-icon>
            </div>
          </div>
        </div>
      </div>

      <!-- 右侧主要内容展示区域 -->
      <div class="min-w-0 flex-1">
        <transition name="fade" mode="out-in">
          <!-- 基础资料 -->
          <div :key="activeTab">
            <div v-if="activeTab === 'profile'" class="app-card p-6">
              <h3 class="mb-6 text-lg font-bold text-ink border-b border-line pb-3 flex items-center gap-2">
                <el-icon class="text-brand-500"><User /></el-icon> 基础资料
              </h3>
              
              <el-form label-position="left" label-width="120px" class="max-w-xl">
                <el-form-item label="登录账号">
                  <div class="flex items-center gap-2">
                    <span class="font-medium text-ink">{{ auth.user?.username }}</span>
                    <el-tag size="small" type="info" class="select-none">不可修改</el-tag>
                  </div>
                </el-form-item>
                
                <el-form-item label="昵称">
                  <div v-if="!nameEditing" class="flex items-center gap-3">
                    <span class="font-medium text-ink">{{ auth.user?.display_name || '—' }}</span>
                    <el-button link type="primary" size="small" :icon="'Edit'" @click="startEditName">修改</el-button>
                  </div>
                  <div v-else class="flex items-center gap-2">
                    <el-input v-model="newName" size="small" maxlength="32" style="width: 200px" />
                    <el-button type="primary" size="small" :loading="nameSaving" @click="saveName">
                      保存
                    </el-button>
                    <el-button size="small" @click="nameEditing = false">取消</el-button>
                  </div>
                </el-form-item>

                <el-form-item label="绑定邮箱">
                  <span class="font-medium text-ink">{{ auth.user?.email || '未绑定邮箱' }}</span>
                </el-form-item>

                <el-form-item label="当前可用积分">
                  <span class="font-bold text-brand-600 text-lg">{{ auth.user?.points ?? 0 }}</span>
                </el-form-item>

                <el-form-item label="注册时间">
                  <span class="font-medium text-ink-soft">{{ formatDateTime(auth.user?.created_at) }}</span>
                </el-form-item>
              </el-form>
            </div>

            <!-- 安全设置 -->
            <div v-else-if="activeTab === 'security'" class="app-card p-6">
              <h3 class="mb-6 text-lg font-bold text-ink border-b border-line pb-3 flex items-center gap-2">
                <el-icon class="text-brand-500"><Lock /></el-icon> 修改账户密码
              </h3>
              
              <el-form ref="pwdRef" :model="pwd" :rules="pwdRules" label-position="top" class="max-w-md">
                <el-form-item label="原密码" prop="old_password">
                  <el-input v-model="pwd.old_password" type="password" show-password placeholder="请输入当前旧密码" />
                </el-form-item>
                <el-form-item label="新密码" prop="new_password">
                  <el-input v-model="pwd.new_password" type="password" show-password placeholder="请输入新密码（至少 8 位）" />
                </el-form-item>
                <el-form-item label="确认新密码" prop="confirm">
                  <el-input v-model="pwd.confirm" type="password" show-password placeholder="请再次输入新密码" />
                </el-form-item>
                <el-form-item class="mt-6">
                  <el-button type="primary" size="large" :loading="pwdSaving" @click="changePassword" class="w-full sm:w-auto">
                    确认修改并重新登录
                  </el-button>
                </el-form-item>
              </el-form>
            </div>

            <!-- 推广邀请 -->
            <div v-else-if="activeTab === 'invite'" class="app-card p-6">
              <h3 class="mb-6 text-lg font-bold text-ink border-b border-line pb-3 flex items-center gap-2">
                <el-icon class="text-brand-500"><Share /></el-icon> 推广与邀请福利
              </h3>

              <!-- 福利卡片 -->
              <div class="mb-6 rounded-xl bg-brand-50 p-4 dark:bg-brand-100/10">
                <h4 class="font-semibold text-brand-700 dark:text-brand-400">{{ inviteBonusTitle }}</h4>
                <p class="mt-1 text-xs text-ink-soft leading-relaxed">
                  {{ inviteBonusDescription }}
                </p>
              </div>

              <div class="space-y-6 max-w-xl">
                <!-- 邀请码 -->
                <div>
                  <div class="mb-2 text-sm font-semibold text-ink">我的专属邀请码</div>
                  <div class="flex items-center gap-3">
                    <code class="rounded-lg bg-canvas px-4 py-2.5 text-lg font-bold tracking-widest text-brand-600 border border-line">
                      {{ auth.user?.invite_code || '—' }}
                    </code>
                    <el-button
                      v-if="!auth.user?.invite_code"
                      :icon="'Refresh'"
                      type="primary"
                      plain
                      :loading="inviteCodeRefreshing"
                      @click="refreshInviteCode"
                    >
                      生成邀请码
                    </el-button>
                    <el-button v-else :icon="'CopyDocument'" type="primary" plain @click="copy(auth.user?.invite_code || '')">
                      复制邀请码
                    </el-button>
                  </div>
                </div>

                <!-- 邀请链接 -->
                <div>
                  <div class="mb-2 text-sm font-semibold text-ink">专属邀请链接</div>
                  <div class="flex items-center gap-2">
                    <el-input :model-value="inviteLink" readonly placeholder="生成专属邀请链接中..." />
                    <el-button :icon="'Link'" type="primary" @click="copy(inviteLink)">
                      一键复制链接
                    </el-button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </transition>
      </div>
    </div>
  </div>
</template>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.fade-enter-from {
  opacity: 0;
  transform: translateY(8px);
}

.fade-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
</style>

