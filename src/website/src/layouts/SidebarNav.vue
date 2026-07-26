<script setup lang="ts">
/** 侧边栏导航：接收已按权限过滤的菜单分组，负责展示和选择事件。 */
import SiteLogo from '@/components/SiteLogo.vue'
import { useSiteStore } from '@/stores/site'

interface MenuEntry {
  index: string
  label: string
  icon: string
}

interface MenuGroup {
  title: string
  items: MenuEntry[]
}

const props = withDefaults(
  defineProps<{
    groups: MenuGroup[]
    active: string
    collapsed?: boolean
  }>(),
  {
    collapsed: false,
  }
)

const emit = defineEmits<{
  select: [path: string]
  toggleCollapse: []
}>()

const site = useSiteStore()
</script>

<template>
  <aside class="flex flex-col border-r border-line bg-card transition-all duration-300">
    <div
      class="flex items-center gap-2.5 py-5 overflow-hidden transition-all duration-300"
      :class="collapsed ? 'px-4 justify-center' : 'px-5'"
    >
      <SiteLogo size="md" />
      <span
        v-if="!collapsed"
        class="truncate text-[17px] font-semibold text-ink transition-opacity duration-300"
      >
        {{ site.title }}
      </span>
    </div>

    <el-scrollbar class="flex-1">
      <nav class="pb-4 transition-all duration-300" :class="collapsed ? 'px-2' : 'px-2.5'">
        <div v-for="group in groups" :key="group.title" class="mb-3">
          <div
            v-if="!collapsed"
            class="px-3.5 py-1.5 text-xs font-medium uppercase tracking-wide text-ink-muted transition-opacity duration-300"
          >
            {{ group.title }}
          </div>
          <div
            v-else
            class="mx-2 my-2 border-t border-line transition-all duration-300"
          ></div>

          <el-tooltip
            v-for="item in group.items"
            :key="item.index"
            :content="item.label"
            :disabled="!collapsed"
            placement="right"
          >
            <button
              class="mb-0.5 flex items-center rounded-lg text-sm font-medium transition-all duration-300"
              :class="[
                active === item.index ? 'bg-brand-50 text-brand-600' : 'text-ink-soft hover:bg-card-soft hover:text-ink',
                collapsed ? 'w-10 h-10 px-0 justify-center mx-auto' : 'w-full px-3.5 py-2.5 gap-3'
              ]"
              @click="emit('select', item.index)"
            >
              <el-icon :size="18" class="shrink-0"><component :is="item.icon" /></el-icon>
              <span
                v-if="!collapsed"
                class="truncate transition-opacity duration-300"
              >
                {{ item.label }}
              </span>
            </button>
          </el-tooltip>
        </div>
      </nav>
    </el-scrollbar>

    <!-- 折叠切换按钮与版权信息 -->
    <div class="mt-auto border-t border-line">
      <button
        class="flex w-full items-center gap-3 px-5 py-3 text-sm font-medium text-ink-soft hover:bg-card-soft hover:text-ink transition-all duration-300"
        :class="collapsed ? 'justify-center px-0' : 'justify-start'"
        @click="emit('toggleCollapse')"
      >
        <el-icon :size="18" class="shrink-0">
          <component :is="collapsed ? 'Expand' : 'Fold'" />
        </el-icon>
        <span v-if="!collapsed" class="truncate">收起导航</span>
      </button>
    </div>

    <div
      v-if="!collapsed"
      class="px-5 py-3 text-xs text-ink-muted border-t border-line/50 transition-opacity duration-300"
    >
      © 2026 {{ site.title }}
    </div>
  </aside>
</template>
