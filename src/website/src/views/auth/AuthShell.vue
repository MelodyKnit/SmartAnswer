<script setup lang="ts">
/** 登录注册相关页面的统一壳组件。 */
defineProps<{
  title: string
  subtitle?: string
}>()
</script>

<template>
  <div class="flex min-h-full items-stretch bg-canvas">
    <div class="relative hidden flex-1 flex-col justify-between overflow-hidden bg-gradient-to-br from-brand-600 via-brand-500 to-accent-600 p-12 text-white lg:flex">
      <div class="flex items-center gap-3">
        <div class="flex h-10 w-10 items-center justify-center rounded-xl bg-white/15">
          <el-icon :size="22"><Cpu /></el-icon>
        </div>
        <span class="text-lg font-semibold">答题接入管理平台</span>
      </div>
      <div>
        <h1 class="text-4xl font-bold leading-tight">高效接入<br>稳定答题能力</h1>
        <p class="mt-4 max-w-sm text-white/80">统一管理 API Key 与导入脚本，实时掌握调用数据与积分消耗。</p>
        <div class="mt-8 flex gap-3">
          <span class="rounded-full bg-white/15 px-4 py-1.5 text-sm">高可用保障</span>
          <span class="rounded-full bg-white/15 px-4 py-1.5 text-sm">快速接入</span>
          <span class="rounded-full bg-white/15 px-4 py-1.5 text-sm">安全合规</span>
        </div>
      </div>
      <div class="text-sm text-white/60">© 2026 答题接入管理平台</div>
      <div class="pointer-events-none absolute -right-20 -top-20 h-72 w-72 rounded-full bg-white/10"></div>
      <div class="pointer-events-none absolute -bottom-24 right-10 h-60 w-60 rounded-full bg-white/10"></div>
    </div>

    <div class="flex flex-1 items-center justify-center p-6">
      <div class="w-full max-w-sm">
        <h2 class="text-2xl font-bold text-ink">{{ title }}</h2>
        <p v-if="subtitle" class="mt-2 mb-6 text-sm text-ink-soft">{{ subtitle }}</p>
        <div v-else class="mb-6"></div>
        <slot />
        <div v-if="$slots.footer" class="mt-6 text-center text-sm text-ink-soft">
          <slot name="footer" />
        </div>
      </div>
    </div>
  </div>
</template>
