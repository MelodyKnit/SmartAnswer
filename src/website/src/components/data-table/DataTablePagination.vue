<script setup lang="ts">
defineProps<{
  total: number
  currentPage: number
  pageSize: number
}>()

const emit = defineEmits<{
  'page-change': [page: number]
}>()
</script>

<template>
  <div class="data-table-pagination flex shrink-0 justify-end border-t border-line px-4 py-3">
    <el-pagination
      layout="total, prev, pager, next, jumper"
      :total="total"
      :current-page="currentPage"
      :page-size="pageSize"
      background
      @current-change="emit('page-change', $event)"
    />
  </div>
</template>

<style scoped>
.data-table-pagination :deep(.el-pagination) {
  flex-wrap: wrap;
  justify-content: flex-end;
}

@media (max-width: 640px) {
  .data-table-pagination :deep(.el-pagination__jump) {
    display: none;
  }
}
</style>
