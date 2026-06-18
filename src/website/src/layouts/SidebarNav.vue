<script setup lang="ts">
/** 侧边栏导航：接收已按权限过滤的菜单分组，负责展示和选择事件。 */
interface MenuEntry {
  index: string
  label: string
  icon: string
  access: 'user' | 'admin' | 'superadmin'
}

interface MenuGroup {
  title: string
  items: MenuEntry[]
}

defineProps<{
  groups: MenuGroup[]
  active: string
}>()

const emit = defineEmits<{
  select: [path: string]
}>()
</script>

<template>
  <aside class="flex flex-col border-r border-line bg-card">
    <div class="flex items-center gap-2.5 px-5 py-5">
      <div class="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-brand-500 to-accent-600 text-white shadow-float">
        <el-icon :size="20"><Cpu /></el-icon>
      </div>
      <span class="text-[17px] font-semibold text-ink">答题接入平台</span>
    </div>

    <el-scrollbar class="flex-1">
      <nav class="px-2.5 pb-4">
        <div v-for="group in groups" :key="group.title" class="mb-3">
          <div class="px-3.5 py-1.5 text-xs font-medium uppercase tracking-wide text-ink-muted">
            {{ group.title }}
          </div>
          <button
            v-for="item in group.items"
            :key="item.index"
            class="mb-0.5 flex w-full items-center gap-3 rounded-lg px-3.5 py-2.5 text-sm font-medium transition-colors"
            :class="active === item.index ? 'bg-brand-50 text-brand-600' : 'text-ink-soft hover:bg-card-soft hover:text-ink'"
            @click="emit('select', item.index)"
          >
            <el-icon :size="18"><component :is="item.icon" /></el-icon>
            <span>{{ item.label }}</span>
          </button>
        </div>
      </nav>
    </el-scrollbar>

    <div class="px-4 py-3 text-xs text-ink-muted">© 2026 答题接入管理平台</div>
  </aside>
</template>
