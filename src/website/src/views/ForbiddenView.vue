<script setup lang="ts">
import { useRouter } from 'vue-router'
const router = useRouter()
</script>

<template>
  <div class="flex min-h-full flex-col items-center justify-center bg-canvas p-10">
    <el-result icon="warning" title="无访问权限" sub-title="当前账号没有访问该页面的权限，请联系管理员。">
      <template #extra>
        <el-button type="primary" @click="router.replace('/')">返回工作台</el-button>
      </template>
    </el-result>
  </div>
</template>
