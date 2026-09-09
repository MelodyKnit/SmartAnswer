<script setup lang="ts">
/** 无状态兑换码分享页：只从 URL fragment 或当前标签页暂存中读取兑换码。 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { walletApi } from '@/api/endpoints'
import { ApiException } from '@/api/http'
import type { WalletOrder, WalletSummary } from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import { useSiteStore } from '@/stores/site'
import SiteLogo from '@/components/SiteLogo.vue'
import {
  PENDING_REDEEM_CODE_KEY,
  readRedeemCodeFromHash,
} from '@/utils/redeem-share'

type RedeemState = 'loading' | 'missing' | 'error' | 'success'

const router = useRouter()
const auth = useAuthStore()
const site = useSiteStore()
const state = ref<RedeemState>('loading')
const errorMessage = ref('')
const code = ref('')
const order = ref<WalletOrder | null>(null)
const wallet = ref<WalletSummary | null>(null)
const redeeming = ref(false)

const benefitText = computed(() => {
  if (!order.value) return ''
  if (order.value.kind === 'days') return `已增加 ${order.value.days_delta || 0} 天无限使用权益`
  return `已增加 ${order.value.points_delta || 0} 积分`
})

function clearShareFragment() {
  window.history.replaceState(
    window.history.state,
    document.title,
    `${window.location.pathname}${window.location.search}`,
  )
}

function readPendingCode(): string {
  const fragmentCode = readRedeemCodeFromHash(window.location.hash)
  if (fragmentCode) {
    clearShareFragment()
    return fragmentCode
  }

  try {
    return sessionStorage.getItem(PENDING_REDEEM_CODE_KEY)?.trim() || ''
  } catch {
    return ''
  }
}

function clearPendingCode() {
  try {
    sessionStorage.removeItem(PENDING_REDEEM_CODE_KEY)
  } catch {
    // 隐私模式禁用 sessionStorage 时不影响已完成的兑换结果。
  }
}

function savePendingCode(value: string): boolean {
  try {
    sessionStorage.setItem(PENDING_REDEEM_CODE_KEY, value)
    return true
  } catch {
    return false
  }
}

async function requireLogin() {
  if (!savePendingCode(code.value)) {
    state.value = 'error'
    errorMessage.value = '当前浏览器无法暂存兑换码，请开启会话存储后重试'
    return
  }
  await router.replace({ name: 'login', query: { redirect: '/share/redeem' } })
}

async function redeem() {
  if (!code.value || redeeming.value) return
  redeeming.value = true
  state.value = 'loading'
  errorMessage.value = ''
  try {
    const response = await walletApi.redeem(code.value)
    order.value = response.order
    wallet.value = response.wallet
    clearPendingCode()
    state.value = 'success'
    await auth.refreshProfile()
  } catch (error) {
    clearPendingCode()
    state.value = 'error'
    errorMessage.value = error instanceof ApiException ? error.message : '兑换失败，请稍后重试'
  } finally {
    redeeming.value = false
  }
}

async function load() {
  code.value = readPendingCode()
  if (!code.value) {
    state.value = 'missing'
    return
  }

  if (!auth.isLoggedIn) {
    await requireLogin()
    return
  }

  clearPendingCode()
  await redeem()
}

async function retry() {
  if (!code.value) return
  await redeem()
}

function goWallet() {
  router.replace({ name: 'wallet' })
}

function goHome() {
  router.replace({ name: 'workbench' })
}

onMounted(load)
</script>

<template>
  <div class="min-h-screen bg-canvas-deep px-4 py-8 sm:px-6 sm:py-12">
    <main class="mx-auto flex min-h-[calc(100vh-4rem)] w-full max-w-lg items-center justify-center">
      <section class="app-card w-full overflow-hidden">
        <div class="border-b border-line px-6 py-5 sm:px-8">
          <div class="flex items-center gap-3">
            <SiteLogo size="md" />
            <div class="min-w-0">
              <div class="truncate text-sm font-medium text-ink-soft">{{ site.title }}</div>
              <h1 class="mt-0.5 text-xl font-semibold text-ink">兑换码兑换</h1>
            </div>
          </div>
        </div>

        <div class="px-6 py-8 text-center sm:px-8">
          <div v-if="state === 'loading'" class="py-8">
            <div class="mx-auto mb-4 h-10 w-10 animate-spin rounded-full border-4 border-brand-100 border-t-brand-600" />
            <p class="text-sm text-ink-soft">正在验证并兑换，请稍候...</p>
          </div>

          <div v-else-if="state === 'missing'" class="py-4">
            <el-icon :size="42" class="text-warning"><WarningFilled /></el-icon>
            <h2 class="mt-4 text-lg font-semibold text-ink">兑换链接无效</h2>
            <p class="mt-2 text-sm leading-6 text-ink-soft">链接中没有找到兑换码，请让分享者重新发送完整链接。</p>
            <el-button class="mt-6" @click="goHome">返回首页</el-button>
          </div>

          <div v-else-if="state === 'error'" class="py-4">
            <el-icon :size="42" class="text-danger"><CircleCloseFilled /></el-icon>
            <h2 class="mt-4 text-lg font-semibold text-ink">兑换未完成</h2>
            <p class="mt-2 break-words text-sm leading-6 text-ink-soft">{{ errorMessage }}</p>
            <div class="mt-6 flex flex-col justify-center gap-3 sm:flex-row">
              <el-button type="primary" :loading="redeeming" @click="retry">重新尝试</el-button>
              <el-button @click="goWallet">打开我的钱包</el-button>
            </div>
          </div>

          <div v-else class="py-4">
            <el-icon :size="48" class="text-success"><CircleCheckFilled /></el-icon>
            <h2 class="mt-4 text-xl font-semibold text-ink">兑换成功</h2>
            <p class="mt-2 text-sm text-ink-soft">{{ benefitText }}</p>
            <div class="mt-6 grid grid-cols-1 gap-3 text-left sm:grid-cols-2">
              <div class="rounded-lg bg-card-soft p-4">
                <div class="text-xs text-ink-muted">当前积分</div>
                <div class="mt-1 text-xl font-semibold text-brand-600">{{ wallet?.points ?? '—' }}</div>
              </div>
              <div class="rounded-lg bg-card-soft p-4">
                <div class="text-xs text-ink-muted">处理状态</div>
                <div class="mt-1 text-xl font-semibold text-success">已完成</div>
              </div>
            </div>
            <el-button type="primary" class="mt-6 w-full" @click="goWallet">查看我的钱包</el-button>
          </div>
        </div>

        <div class="border-t border-line px-6 py-4 text-center text-xs leading-5 text-ink-muted sm:px-8">
          兑换结果与钱包页面中的手动兑换一致；兑换码的有效期和使用次数仍按系统规则执行。
        </div>
      </section>
    </main>
  </div>
</template>
