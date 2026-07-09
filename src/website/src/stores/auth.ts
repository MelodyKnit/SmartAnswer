/** 全局会话状态：当前用户、登录态、角色边界。 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { authApi, userApi } from '@/api/endpoints'
import { clearToken, getToken, setToken } from '@/api/http'
import type { Billing, Role, User, WalletSummary } from '@/api/types'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const billing = ref<Billing | null>(null)
  const wallet = ref<WalletSummary | null>(null)
  const initialized = ref(false)

  const isLoggedIn = computed(() => user.value !== null)
  const role = computed<Role | null>(() => user.value?.role ?? null)
  const isAdmin = computed(() => role.value === 'admin' || role.value === 'superadmin')
  const isSuperAdmin = computed(() => role.value === 'superadmin')

  /** 是否拥有某一访问级别。 */
  function hasAccess(level: 'user' | 'admin' | 'superadmin'): boolean {
    if (!user.value) return false
    if (level === 'user') return true
    if (level === 'admin') return isAdmin.value
    return isSuperAdmin.value
  }

  async function login(username: string, password: string, remember: boolean): Promise<void> {
    const res = await authApi.login({ username, password, remember })
    setToken(res.token)
    user.value = res.user
    await refreshProfile()
    initialized.value = true
  }

  async function register(
    username: string,
    password: string,
    email?: string,
    inviteCode?: string,
    emailCode?: string,
  ): Promise<User> {
    const res = await authApi.register({
      username,
      password,
      email,
      invite_code: inviteCode || undefined,
      email_code: emailCode || undefined,
    })
    return res.user
  }

  /** 拉取当前会话；用于刷新页面后恢复登录态。 */
  async function fetchSession(): Promise<void> {
    if (!getToken()) {
      user.value = null
      initialized.value = true
      return
    }
    try {
      const res = await authApi.session()
      user.value = res.user
      await refreshProfile()
    } catch {
      user.value = null
      clearToken()
    } finally {
      initialized.value = true
    }
  }

  /** 拉取用户中心摘要（账户、计费、钱包）。 */
  async function refreshProfile(): Promise<void> {
    try {
      const res = await userApi.me()
      user.value = res.user
      billing.value = res.billing
      wallet.value = res.wallet
    } catch {
      /* 保留已有用户信息，忽略次要失败。 */
    }
  }

  async function logout(): Promise<void> {
    try {
      await authApi.logout()
    } catch {
      /* 即便后端登出失败，也要清理本地态。 */
    }
    reset()
  }

  /** 本地清理（令牌失效或主动登出）。 */
  function reset(): void {
    user.value = null
    billing.value = null
    wallet.value = null
    clearToken()
  }

  return {
    user,
    billing,
    wallet,
    initialized,
    isLoggedIn,
    role,
    isAdmin,
    isSuperAdmin,
    hasAccess,
    login,
    register,
    fetchSession,
    refreshProfile,
    logout,
    reset,
  }
})
