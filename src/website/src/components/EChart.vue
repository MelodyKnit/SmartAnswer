<script setup lang="ts">
/** ECharts 轻量封装：按传入 option 渲染并跟随容器尺寸更新。 */
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import type { ECharts, EChartsOption } from 'echarts'

const props = withDefaults(
  defineProps<{
    option: EChartsOption
    height?: string
  }>(),
  { height: '260px' },
)

const el = ref<HTMLDivElement>()
let chart: ECharts | null = null
let observer: ResizeObserver | null = null

function renderChart() {
  if (!el.value) return
  chart ??= echarts.init(el.value)
  chart.setOption(props.option, true)
}

onMounted(() => {
  renderChart()
  observer = new ResizeObserver(() => chart?.resize())
  if (el.value) observer.observe(el.value)
})

watch(() => props.option, renderChart, { deep: true })

onBeforeUnmount(() => {
  observer?.disconnect()
  chart?.dispose()
  chart = null
})
</script>

<template>
  <div ref="el" class="w-full" :style="{ height }" />
</template>
