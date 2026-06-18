<script setup lang="ts">
/** 列表/管理页通用页头：标题 + 描述 + 右侧操作槽。 */
defineProps<{ title: string; description?: string }>()
</script>

<template>
  <div class="mb-5 flex items-end justify-between gap-4">
    <div>
      <h2 class="text-xl font-semibold text-ink">{{ title }}</h2>
      <p v-if="description" class="mt-1 text-sm text-ink-soft">{{ description }}</p>
    </div>
    <div class="flex items-center gap-2">
      <slot name="actions" />
    </div>
  </div>
</template>
