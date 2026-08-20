<script setup lang="ts">
/** 兑换管理：管理员维护兑换码、手动发放权益，并查看全局兑换/权益变更记录。 */
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { billingApi, walletApi } from '@/api/endpoints'
import type { RedeemCode, WalletOrder } from '@/api/types'
import { ApiException } from '@/api/http'
import { formatDateTime, walletSourceLabel } from '@/utils/format'
import PageHeader from '@/components/PageHeader.vue'
import { DEFAULT_PAGE_SIZE } from '@/config/constants'

const loading = ref(false)
const codesLoading = ref(false)
const orders = ref<WalletOrder[]>([])
const codes = ref<RedeemCode[]>([])
const page = ref(1)
const total = ref(0)

const activeTab = ref('codes')

const filters = reactive({
  username: '',
  source: '',
  limit: DEFAULT_PAGE_SIZE.REDEEM,
})

const grantVisible = ref(false)
const pointsPolicy = reactive({ manualGrant: 1, redeemCode: 1 })
const grantForm = reactive<{ username: string; kind: 'points' | 'days'; points: number; days: number }>({
  username: '',
  kind: 'points',
  points: pointsPolicy.manualGrant,
  days: 30,
})
const codeVisible = ref(false)
const codeForm = reactive<{
  kind: 'points' | 'days'
  points: number
  days: number
  max_uses: number
  expires_at_ms: string | number
  mode: 'random' | 'manual'
  code: string
  count: number
}>({
  kind: 'points',
  points: pointsPolicy.redeemCode,
  days: 30,
  max_uses: 1,
  expires_at_ms: '',
  mode: 'random',
  code: '',
  count: 1,
})

const sourceOptions = [
  { value: 'manual_credit', label: '管理员发放' },
  { value: 'redeem_code', label: '兑换码' },
  { value: 'feedback_reward', label: '反馈奖励' },
]

const summaryCards = computed(() => {
  if (activeTab.value === 'codes') {
    const totalCodes = codes.value.length
    const activeCodes = codes.value.filter(isRedeemCodeUsable).length
    const fullyUsedCodes = codes.value.filter((c) => (c.used_uses || 0) >= (c.max_uses || 0)).length
    const totalUses = codes.value.reduce((sum, c) => sum + (c.used_uses || 0), 0)
    const limitUses = codes.value.reduce((sum, c) => sum + (c.max_uses || 0), 0)
    return [
      { label: '兑换码总数', value: totalCodes, unit: '个', color: 'text-brand-600' },
      { label: '可用兑换码', value: activeCodes, unit: '个', color: 'text-success' },
      { label: '已用完兑换码', value: fullyUsedCodes, unit: '个', color: 'text-ink-muted' },
      { label: '使用次数 / 限制次数', value: `${totalUses} / ${limitUses}`, unit: '次', color: 'text-warning' },
    ]
  } else {
    const uniqueUsers = new Set(orders.value.map((item) => item.username).filter(Boolean))
    const pointsOrders = orders.value.filter((item) => item.kind === 'points')
    const daysOrders = orders.value.filter((item) => item.kind === 'days')
    const pagePoints = pointsOrders.reduce((sum, item) => sum + Number(item.points_delta || 0), 0)
    const pageDays = daysOrders.reduce((sum, item) => sum + Number(item.days_delta || 0), 0)
    return [
      { label: '兑换/变更总数', value: total.value, unit: '条', color: 'text-brand-600' },
      { label: '本页涉及用户', value: uniqueUsers.size, unit: '人', color: 'text-success' },
      { label: '本页积分发放', value: pagePoints, unit: '分', color: 'text-warning' },
      { label: '本页天数发放', value: pageDays, unit: '天', color: 'text-accent-600' },
    ]
  }
})

function currentSeconds() {
  return Math.floor(Date.now() / 1000)
}

function isRedeemCodeExpired(code: RedeemCode) {
  return Boolean(code.expires_at && code.expires_at <= currentSeconds())
}

function isRedeemCodeExhausted(code: RedeemCode) {
  return (code.used_uses || 0) >= (code.max_uses || 0)
}

function redeemCodeStatus(code: RedeemCode): { label: string; type: 'success' | 'info' | 'warning' | 'danger' } {
  if (code.status === 'expired' || isRedeemCodeExpired(code)) return { label: '已过期', type: 'danger' }
  if (code.status === 'exhausted' || isRedeemCodeExhausted(code)) return { label: '已用完', type: 'warning' }
  if (code.status !== 'active') return { label: '失效', type: 'info' }
  return { label: '可用', type: 'success' }
}

function isRedeemCodeUsable(code: RedeemCode) {
  return redeemCodeStatus(code).label === '可用'
}

function codeExpiryTimestamp() {
  if (!codeForm.expires_at_ms) return 0
  const timestamp = Math.floor(Number(codeForm.expires_at_ms) / 1000)
  if (!Number.isFinite(timestamp) || timestamp <= currentSeconds()) {
    ElMessage.warning('有效期必须晚于当前时间')
    return null
  }
  return timestamp
}

async function loadCodes() {
  codesLoading.value = true
  try {
    const res = await walletApi.redeemCodes()
    codes.value = res.redeem_codes
  } catch (error) {
    ElMessage.error(error instanceof ApiException ? error.message : '加载兑换码失败')
  } finally {
    codesLoading.value = false
  }
}

async function loadOrders() {
  loading.value = true
  try {
    const res = await walletApi.changes({
      username: filters.username.trim() || undefined,
      source: filters.source || undefined,
      limit: filters.limit,
      page: page.value,
    })
    orders.value = res.orders
    total.value = res.total
  } catch (error) {
    ElMessage.error(error instanceof ApiException ? error.message : '加载兑换记录失败')
  } finally {
    loading.value = false
  }
}

async function load() {
  await Promise.all([loadPointsPolicy(), loadCodes(), loadOrders()])
}

async function loadPointsPolicy() {
  try {
    const res = await billingApi.pointsPolicy()
    pointsPolicy.manualGrant = res.points_policy.manual_grant_default_points
    pointsPolicy.redeemCode = res.points_policy.redeem_code_default_points
    if (!grantVisible.value) grantForm.points = pointsPolicy.manualGrant
    if (!codeVisible.value) codeForm.points = pointsPolicy.redeemCode
  } catch {
    // 积分策略只用于表单默认值，加载失败时继续使用本地安全兜底。
  }
}

function search() {
  page.value = 1
  loadOrders()
}

function onPageChange(next: number) {
  page.value = next
  loadOrders()
}

function resetFilters() {
  filters.username = ''
  filters.source = ''
  filters.limit = DEFAULT_PAGE_SIZE.REDEEM
  page.value = 1
  loadOrders()
}

async function submitGrant() {
  if (!grantForm.username.trim()) {
    ElMessage.warning('请输入用户名')
    return
  }
  try {
    await walletApi.grant({
      username: grantForm.username.trim(),
      kind: grantForm.kind,
      points: grantForm.kind === 'points' ? grantForm.points : 0,
      days: grantForm.kind === 'days' ? grantForm.days : 0,
    })
    ElMessage.success(grantForm.kind === 'days' ? '无限使用天数已发放' : '积分已发放')
    grantVisible.value = false
    grantForm.username = ''
    grantForm.points = pointsPolicy.manualGrant
    grantForm.days = 30
    await loadOrders()
  } catch (error) {
    ElMessage.error(error instanceof ApiException ? error.message : '发放失败')
  }
}

async function submitCode() {
  const expiresAt = codeExpiryTimestamp()
  if (expiresAt === null) return

  if (codeForm.mode === 'manual' && !codeForm.code.trim()) {
    ElMessage.warning('请输入自定义兑换码')
    return
  }

  try {
    await walletApi.createRedeemCode({
      kind: codeForm.kind,
      points: codeForm.kind === 'points' ? codeForm.points : 0,
      days: codeForm.kind === 'days' ? codeForm.days : 0,
      max_uses: codeForm.max_uses,
      expires_at: expiresAt,
      code: codeForm.mode === 'manual' ? codeForm.code.trim() : undefined,
      count: codeForm.mode === 'random' ? codeForm.count : 1,
    })
    ElMessage.success('兑换码已创建')
    codeVisible.value = false
    codeForm.points = pointsPolicy.redeemCode
    codeForm.days = 30
    codeForm.max_uses = 1
    codeForm.expires_at_ms = ''
    codeForm.code = ''
    codeForm.count = 1
    codeForm.mode = 'random'
    await loadCodes()
  } catch (error) {
    ElMessage.error(error instanceof ApiException ? error.message : '创建失败')
  }
}

async function copyCode(code: string) {
  try {
    await navigator.clipboard.writeText(code)
    ElMessage.success('已复制兑换码')
  } catch {
    ElMessage.warning('复制失败')
  }
}

onMounted(load)
</script>

<template>
  <div class="space-y-5">
    <PageHeader title="兑换管理" description="维护兑换码、手动发放权益，并查看全局兑换记录与权益流水。">
      <template #actions>
        <el-button @click="load">刷新</el-button>
        <el-button v-if="activeTab === 'orders'" type="primary" @click="grantVisible = true">发放权益</el-button>
        <el-button v-if="activeTab === 'codes'" type="primary" @click="codeVisible = true">创建兑换码</el-button>
      </template>
    </PageHeader>

    <section class="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <div v-for="card in summaryCards" :key="card.label" class="app-card p-5">
        <div class="text-sm text-ink-soft">{{ card.label }}</div>
        <div class="mt-3 flex items-baseline gap-1">
          <span class="text-3xl font-bold" :class="card.color">{{ card.value }}</span>
          <span class="text-sm text-ink-muted">{{ card.unit }}</span>
        </div>
      </div>
    </section>

    <el-tabs v-model="activeTab" class="mt-2">
      <el-tab-pane label="兑换码管理" name="codes">
        <div class="space-y-4 pt-3">
          <section class="app-card p-1">
            <div class="flex items-center justify-between px-4 pt-4 pb-2">
              <div>
                <div class="text-base font-semibold text-ink">兑换码列表</div>
                <div class="mt-1 text-sm text-ink-soft">支持积分类型与天数类型兑换码的生成与维护。</div>
              </div>
              <el-button type="primary" :icon="'Plus'" @click="codeVisible = true">创建兑换码</el-button>
            </div>
            <el-table v-loading="codesLoading" :data="codes" style="width: 100%">
              <el-table-column label="兑换码" min-width="220">
                <template #default="{ row }">
                  <code class="rounded bg-canvas px-2 py-1 text-xs font-mono font-bold select-all">{{ row.code }}</code>
                  <el-button link type="primary" size="small" class="ml-2" @click="copyCode(row.code)">复制</el-button>
                </template>
              </el-table-column>
              <el-table-column label="类型与面值" width="160" align="center">
                <template #default="{ row }">
                  <el-tag v-if="row.kind === 'days'" size="small" type="warning" effect="light">
                    {{ row.days || 0 }} 天卡
                  </el-tag>
                  <span v-else class="font-semibold text-brand-600">+{{ row.points }} 积分</span>
                </template>
              </el-table-column>
              <el-table-column label="使用情况" width="120" align="center">
                <template #default="{ row }">
                  <span class="font-medium text-ink">{{ row.used_uses }}</span>
                  <span class="text-ink-muted"> / {{ row.max_uses }}</span>
                </template>
              </el-table-column>
              <el-table-column label="状态" width="110" align="center">
                <template #default="{ row }">
                  <el-tag size="small" :type="redeemCodeStatus(row).type" effect="light">
                    {{ redeemCodeStatus(row).label }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="有效期" min-width="170" align="center">
                <template #default="{ row }">
                  <el-tag v-if="!row.expires_at" size="small" type="info" effect="plain">永久有效</el-tag>
                  <el-tag v-else-if="isRedeemCodeExpired(row)" size="small" type="danger" effect="light">已过期</el-tag>
                  <span v-else class="text-ink">{{ formatDateTime(row.expires_at) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="创建人" width="140" prop="created_by" align="center" />
              <el-table-column label="创建时间" min-width="170" align="right">
                <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
              </el-table-column>
              <template #empty><el-empty description="暂无兑换码" /></template>
            </el-table>
          </section>
        </div>
      </el-tab-pane>

      <el-tab-pane label="兑换记录" name="orders">
        <div class="space-y-4 pt-3">
          <section class="app-card p-4">
            <div class="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-5">
              <el-input
                v-model="filters.username"
                placeholder="按用户名筛选"
                clearable
                :prefix-icon="'User'"
                @keyup.enter="search"
              />
              <el-select v-model="filters.source" placeholder="全部来源" clearable @change="search">
                <el-option
                  v-for="option in sourceOptions"
                  :key="option.value"
                  :value="option.value"
                  :label="option.label"
                />
              </el-select>
              <el-select v-model="filters.limit" placeholder="每页数量" @change="search">
                <el-option :value="10" label="每页 10 条" />
                <el-option :value="20" label="每页 20 条" />
                <el-option :value="50" label="每页 50 条" />
                <el-option :value="100" label="每页 100 条" />
              </el-select>
              <el-button @click="resetFilters">重置筛选</el-button>
              <el-button type="primary" :icon="'Search'" @click="search">查询</el-button>
            </div>
          </section>

          <section class="app-card p-1">
            <div class="px-4 pt-4 pb-2 text-base font-semibold text-ink">兑换与权益变更记录</div>
            <el-table v-loading="loading" :data="orders" style="width: 100%">
              <el-table-column label="用户" min-width="120" prop="username" />
              <el-table-column label="类型" width="110" align="center">
                <template #default="{ row }">
                  <el-tag size="small" :type="row.kind === 'days' ? 'warning' : 'success'" effect="light">
                    {{ row.kind === 'days' ? '天数' : '积分' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="变更面值" width="140" align="center">
                <template #default="{ row }">
                  <span v-if="row.kind === 'days'" class="font-semibold text-warning">
                    +{{ row.days_delta || 0 }} 天
                  </span>
                  <span v-else class="font-semibold text-success">+{{ row.points_delta }} 分</span>
                </template>
              </el-table-column>
              <el-table-column label="来源" min-width="140" align="center">
                <template #default="{ row }">{{ walletSourceLabel(row.source) }}</template>
              </el-table-column>
              <el-table-column label="操作人" width="140" prop="created_by" align="center" />
              <el-table-column label="状态" width="110" align="center">
                <template #default="{ row }">
                  <el-tag size="small" :type="row.status === 'completed' ? 'success' : 'info'" effect="light">
                    {{ row.status === 'completed' ? '已完成' : row.status }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="时间" min-width="170" align="right">
                <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
              </el-table-column>
              <template #empty><el-empty description="暂无兑换记录" /></template>
            </el-table>
          </section>

          <div v-if="total > 0" class="flex justify-end pt-2">
            <el-pagination
              layout="total, prev, pager, next, jumper"
              :total="total"
              :current-page="page"
              :page-size="filters.limit"
              background
              @current-change="onPageChange"
            />
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="grantVisible" title="发放权益" width="420px">
      <el-form label-position="top">
        <el-form-item label="用户名">
          <el-input v-model="grantForm.username" placeholder="输入要发放权益的用户名" />
        </el-form-item>
        <el-form-item label="发放类型">
          <el-radio-group v-model="grantForm.kind" class="w-full">
            <el-radio-button value="points">发放积分</el-radio-button>
            <el-radio-button value="days">发放天数</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="grantForm.kind === 'points'" label="积分数量">
          <el-input-number v-model="grantForm.points" :min="1" class="w-full" />
        </el-form-item>
        <el-form-item v-else label="增加天数">
          <el-input-number v-model="grantForm.days" :min="1" class="w-full" />
          <div class="mt-1 text-xs text-ink-muted">在用户现有到期时间或当前时间上顺延天数。</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="grantVisible = false">取消</el-button>
        <el-button type="primary" @click="submitGrant">发放</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="codeVisible" title="创建兑换码" width="420px">
      <el-form label-position="top">
        <el-form-item label="兑换码类型">
          <el-radio-group v-model="codeForm.kind" class="w-full">
            <el-radio-button value="points">积分兑换码</el-radio-button>
            <el-radio-button value="days">天数兑换码</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="生成方式">
          <el-radio-group v-model="codeForm.mode" class="w-full">
            <el-radio-button value="random">随机创建</el-radio-button>
            <el-radio-button value="manual">手动填写</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="codeForm.mode === 'manual'" label="兑换码名称">
          <el-input v-model="codeForm.code" placeholder="输入自定义兑换码，如 WELCOME_2026" maxlength="64" show-word-limit />
          <div class="mt-1 text-xs text-ink-muted">只支持字母、数字、下划线及连字符。</div>
        </el-form-item>
        <el-form-item v-if="codeForm.mode === 'random'" label="创建数量">
          <el-input-number v-model="codeForm.count" :min="1" :max="1000" class="w-full" />
          <div class="mt-1 text-xs text-ink-muted">设置本次批量随机生成的兑换码个数。</div>
        </el-form-item>
        <el-form-item v-if="codeForm.kind === 'points'" label="积分数量">
          <el-input-number v-model="codeForm.points" :min="1" class="w-full" />
        </el-form-item>
        <el-form-item v-else label="有效天数 (天)">
          <el-input-number v-model="codeForm.days" :min="1" class="w-full" />
          <div class="mt-1 text-xs text-ink-muted">用户兑换后增加对应的有效天数。</div>
        </el-form-item>
        <el-form-item label="可用次数">
          <el-input-number v-model="codeForm.max_uses" :min="1" class="w-full" />
        </el-form-item>
        <el-form-item label="有效期">
          <el-date-picker
            v-model="codeForm.expires_at_ms"
            type="datetime"
            value-format="x"
            placeholder="不设置则永久有效"
            clearable
            class="w-full"
          />
          <div class="mt-1 text-xs text-ink-muted">留空表示永久有效，设置后到期将无法兑换。</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="codeVisible = false">取消</el-button>
        <el-button type="primary" @click="submitCode">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>
