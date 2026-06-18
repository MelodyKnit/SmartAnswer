<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()

function goHome() {
  router.replace('/')
}

function goBack() {
  router.back()
}
</script>

<template>
  <div class="flex min-h-full flex-col items-center justify-center bg-canvas p-6 sm:p-10">
    <div class="w-full max-w-md rounded-2xl bg-card border border-line p-8 text-center shadow-card transition-all duration-300 hover:shadow-float">
      <!-- 404 炫彩数字 -->
      <div class="relative inline-block">
        <h1 class="bg-gradient-to-r from-brand-500 via-accent-500 to-brand-600 bg-clip-text text-8xl font-black tracking-widest text-transparent select-none animate-pulse">
          404
        </h1>
        <div class="absolute -inset-1 rounded-lg bg-gradient-to-r from-brand-400 to-accent-600 opacity-20 blur-xl filter"></div>
      </div>
      
      <!-- 提示文案 -->
      <h2 class="mt-6 text-2xl font-bold text-ink">页面似乎迷失了</h2>
      <p class="mt-3 text-sm text-ink-soft leading-relaxed">
        您访问的链接可能已经失效、被删除，或者输入了错误的地址。请检查拼写或尝试通过下方按钮返回。
      </p>

      <!-- 动态科技风装饰线 -->
      <div class="my-8 flex items-center justify-center gap-1.5">
        <div class="h-1 w-12 rounded bg-gradient-to-r from-transparent to-line-strong"></div>
        <div class="h-2 w-2 rounded-full bg-brand-500"></div>
        <div class="h-1 w-12 rounded bg-gradient-to-l from-transparent to-line-strong"></div>
      </div>

      <!-- 操作按钮 -->
      <div class="flex flex-col gap-3 sm:flex-row sm:justify-center">
        <el-button type="primary" :icon="'HomeFilled'" size="large" class="w-full sm:w-auto" @click="goHome">
          返回工作台
        </el-button>
        <el-button size="large" :icon="'Back'" class="!ml-0 w-full sm:w-auto" @click="goBack">
          返回上一页
        </el-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.animate-pulse {
  animation: pulse 4s cubic-bezier(0.4, 0, 0.6, 1) infinite;
}

@keyframes pulse {
  0%, 100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: .85;
    transform: scale(0.98);
  }
}
</style>
