<script setup lang="ts" generic="Row extends object">
import DataTablePagination from './DataTablePagination.vue'

const props = withDefaults(defineProps<{
  data: Row[]
  loading?: boolean
  rowKey?: string | ((row: Row) => string | number)
  fillHeight?: boolean
  showPagination?: boolean
  total?: number
  currentPage?: number
  pageSize?: number
  emptyText?: string
}>(), {
  loading: false,
  fillHeight: false,
  showPagination: false,
  total: 0,
  currentPage: 1,
  pageSize: 20,
  emptyText: '暂无数据',
})

const emit = defineEmits<{
  'page-change': [page: number]
  'selection-change': [rows: Row[]]
}>()

</script>

<template>
  <section
    class="unified-data-table app-card min-w-0 overflow-hidden p-1"
    :class="{ 'flex min-h-0 flex-1 flex-col': fillHeight }"
  >
    <div class="unified-data-table__body" :class="{ 'min-h-0 flex-1': fillHeight }">
      <el-table
        v-loading="loading"
        :data="data"
        :row-key="rowKey"
        :height="fillHeight ? '100%' : undefined"
        style="width: 100%"
        class="unified-data-table__table"
        @selection-change="emit('selection-change', $event)"
      >
        <slot />
        <template #empty><el-empty :description="emptyText" /></template>
      </el-table>
    </div>

    <DataTablePagination
      v-if="showPagination && total > 0"
      :total="total"
      :current-page="currentPage"
      :page-size="pageSize"
      @page-change="emit('page-change', $event)"
    />
  </section>
</template>

<style scoped>
.unified-data-table__table {
  --el-table-bg-color: var(--c-card);
  --el-table-tr-bg-color: var(--c-card);
  --el-table-header-bg-color: var(--c-card-soft);
  --el-table-row-hover-bg-color: var(--c-card-soft);
  --el-table-border-color: var(--c-line);
  --el-table-text-color: var(--c-ink);
  --el-table-header-text-color: var(--c-ink-soft);
}

.unified-data-table__table :deep(.el-table__inner-wrapper::before) {
  background-color: var(--c-line);
}
</style>
