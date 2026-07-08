<script setup lang="ts">
/** 我的钱包：积分概览、兑换码核销、个人积分流水。所有用户可用。 */
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { walletApi } from '@/api/endpoints'
import type { WalletOrder, WalletSummary } from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import { ApiException } from '@/api/http'
import { formatDateTime, walletSourceLabel } from '@/utils/format'
import PageHeader from '@/components/PageHeader.vue'
import { DEFAULT_PAGE_SIZE } from '@/config/constants'

const auth = useAuthStore()
const router = useRouter()
const loading = ref(false)
const wallet = ref<WalletSummary | null>(null)
const orders = ref<WalletOrder[]>([])
const page = ref(1)
const pageSize = ref(DEFAULT_PAGE_SIZE.WALLET)
const total = ref(0)
const redeem = reactive({
  code: '',
  loading: false,
})

async function loadOrders() {
  const o = await walletApi.orders({ limit: pageSize.value, page: page.value })
  orders.value = o.orders
  total.value = o.total
}

async function load() {
  loading.value = true
  try {
    const [w] = await Promise.all([
      walletApi.me(),
      loadOrders().catch(() => {
        ElMessage.warning('积分流水加载失败，已先显示钱包余额')
      }),
    ])
    wallet.value = w.wallet
  } catch (err) {
    ElMessage.error(err instanceof ApiException ? err.message : '加载钱包失败')
  } finally {
    loading.value = false
  }
}

function onPageChange(next: number) {
  page.value = next
  loadOrders()
}

async function submitRedeem() {
  if (!redeem.code.trim()) {
    ElMessage.warning('请输入兑换码')
    return
  }
  redeem.loading = true
  try {
    const res = await walletApi.redeem(redeem.code.trim())
    wallet.value = res.wallet
    redeem.code = ''
    ElMessage.success('兑换成功')
    await auth.refreshProfile()
    await load()
  } catch (err) {
    ElMessage.error(err instanceof ApiException ? err.message : '兑换失败')
  } finally {
    redeem.loading = false
  }
}

onMounted(load)
</script>

<template>
  <div v-loading="loading">
    <PageHeader title="我的钱包" description="查看积分余额、兑换积分码与个人积分流水。">
      <template v-if="auth.isAdmin" #actions>
        <el-button type="primary" plain @click="router.push('/redeem-management')">
          兑换管理
        </el-button>
      </template>
    </PageHeader>

    <div class="mb-5 grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
      <div class="app-card p-5">
        <div class="text-sm text-ink-soft">当前积分</div>
        <div class="mt-2 text-3xl font-bold text-brand-600">
          {{ wallet?.points?.toLocaleString() ?? '—' }}
        </div>
      </div>
      <div class="app-card p-5">
        <div class="mb-2 text-sm text-ink-soft">兑换码核销</div>
        <div class="flex gap-2">
          <el-input v-model="redeem.code" placeholder="输入兑换码" @keyup.enter="submitRedeem" />
          <el-button type="primary" :loading="redeem.loading" @click="submitRedeem">兑换</el-button>
        </div>
      </div>
    </div>

    <div class="app-card p-1">
      <div class="px-4 pt-4 text-base font-semibold text-ink">积分流水</div>
      <el-table :data="orders" style="width: 100%">
        <el-table-column label="类型" width="120" align="center">
          <template #default="{ row }">
            <el-tag size="small" type="warning" effect="light">
              {{ row.kind === 'points' ? '积分' : row.kind }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="变更" width="140" align="center">
          <template #default="{ row }">
            <span class="font-medium text-success">+{{ row.points_delta }} 分</span>
          </template>
        </el-table-column>
        <el-table-column label="来源" width="140" align="center">
          <template #default="{ row }">{{ walletSourceLabel(row.source) }}</template>
        </el-table-column>
        <el-table-column label="操作人" width="140" prop="created_by" align="center" />
        <el-table-column label="时间" min-width="170" align="right">
          <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
        </el-table-column>
        <template #empty>
          <el-empty description="暂无积分流水" />
        </template>
      </el-table>
      <div v-if="total > 0" class="mt-4 flex justify-end">
        <el-pagination
          layout="total, prev, pager, next"
          :total="total"
          :current-page="page"
          :page-size="pageSize"
          background
          @current-change="onPageChange"
        />
      </div>
    </div>
  </div>
</template>
