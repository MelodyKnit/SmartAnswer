<script setup lang="ts">
/** 统一站点 Logo 展示。有配置图片时显示图片，加载失败或未配置时回退默认图标。 */
import { computed, ref, watch } from 'vue'
import { useSiteStore } from '@/stores/site'

const props = withDefaults(
  defineProps<{
    size?: 'sm' | 'md' | 'lg'
    variant?: 'gradient' | 'light'
    title?: string
    logoUrl?: string
  }>(),
  {
    size: 'md',
    variant: 'gradient',
  },
)

const site = useSiteStore()
const imageFailed = ref(false)
const displayTitle = computed(() => (props.title || site.title).trim() || site.title)

const displayLogoUrl = computed(() => {
  if (props.logoUrl) {
    return props.logoUrl.trim()
  }
  // 根据 size 加载对应尺寸的 Logo 地址，如果没能解析出则回退到 site.logoUrl
  const sizeKey = props.size === 'sm' ? 'sm' : props.size === 'lg' ? 'lg' : 'md'
  const url = site.logoUrls?.[sizeKey] || site.logoUrl
  return (url || '').trim()
})

watch(
  displayLogoUrl,
  () => {
    imageFailed.value = false
  },
)

const sizeClass = computed(() => {
  if (props.size === 'sm') return 'h-8 w-8'
  if (props.size === 'lg') return 'h-10 w-10'
  return 'h-9 w-9'
})

const iconSize = computed(() => {
  if (props.size === 'sm') return 18
  if (props.size === 'lg') return 22
  return 20
})

const wrapperClass = computed(() => [
  sizeClass.value,
  'flex shrink-0 items-center justify-center overflow-hidden rounded-xl',
  props.variant === 'light'
    ? 'bg-white/15 text-white'
    : 'bg-gradient-to-br from-brand-500 to-accent-600 text-white shadow-float',
])
</script>

<template>
  <div :class="wrapperClass">
    <img
      v-if="displayLogoUrl && !imageFailed"
      :src="displayLogoUrl"
      :alt="`${displayTitle} Logo`"
      class="h-full w-full object-cover"
      @error="imageFailed = true"
    />
    <el-icon v-else :size="iconSize"><Cpu /></el-icon>
  </div>
</template>
