<script setup lang="ts">
/** 认证页滑块验证码：挑战和一次性凭证均由服务端签发。 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { authApi } from '@/api/endpoints'
import { ApiException } from '@/api/http'

interface SliderChallenge {
  challenge_id: string
  bg_image: string
  puzzle_image: string
  y: number
  width: number
  height: number
  puzzle_width: number
  puzzle_height: number
}

const props = withDefaults(defineProps<{ disabled?: boolean }>(), {
  disabled: false,
})

const emit = defineEmits<{
  verified: [token: string]
}>()

const railRef = ref<HTMLDivElement>()
const challenge = ref<SliderChallenge | null>(null)
const loading = ref(false)
const verifying = ref(false)
const errorMessage = ref('')
const sliderOffset = ref(0)
const railWidth = ref(0)
const dragging = ref(false)
const dragStartX = ref(0)
const dragStartOffset = ref(0)

const handleWidth = 40
const maxSliderOffset = computed(() => Math.max(0, railWidth.value - handleWidth))
const progress = computed(() => {
  if (!maxSliderOffset.value) return 0
  return Math.min(1, Math.max(0, sliderOffset.value / maxSliderOffset.value))
})
const sliderStyle = computed(() => ({ transform: `translateX(${sliderOffset.value}px)` }))
const puzzleStyle = computed(() => {
  if (!challenge.value) return {}
  const movableWidth = 1 - challenge.value.puzzle_width / challenge.value.width
  return {
    top: `${(challenge.value.y / challenge.value.height) * 100}%`,
    left: `${progress.value * movableWidth * 100}%`,
    width: `${(challenge.value.puzzle_width / challenge.value.width) * 100}%`,
  }
})

function syncRailWidth() {
  railWidth.value = railRef.value?.getBoundingClientRect().width || 0
  sliderOffset.value = Math.min(sliderOffset.value, maxSliderOffset.value)
}

async function loadChallenge(preserveError = false) {
  loading.value = true
  if (!preserveError) errorMessage.value = ''
  sliderOffset.value = 0
  emit('verified', '')
  try {
    challenge.value = await authApi.sliderCaptchaChallenge()
    await nextTick()
    syncRailWidth()
  } catch (error) {
    challenge.value = null
    errorMessage.value = error instanceof ApiException ? error.message : '验证码加载失败，请重试'
  } finally {
    loading.value = false
  }
}

function removePointerListeners() {
  window.removeEventListener('pointermove', onPointerMove)
  window.removeEventListener('pointerup', onPointerUp)
  window.removeEventListener('pointercancel', onPointerUp)
}

function onPointerDown(event: PointerEvent) {
  if (props.disabled || loading.value || verifying.value || !challenge.value) return
  event.preventDefault()
  dragging.value = true
  dragStartX.value = event.clientX
  dragStartOffset.value = sliderOffset.value
  window.addEventListener('pointermove', onPointerMove)
  window.addEventListener('pointerup', onPointerUp)
  window.addEventListener('pointercancel', onPointerUp)
}

function onPointerMove(event: PointerEvent) {
  if (!dragging.value) return
  const next = dragStartOffset.value + event.clientX - dragStartX.value
  sliderOffset.value = Math.min(maxSliderOffset.value, Math.max(0, next))
}

async function onPointerUp() {
  if (!dragging.value) return
  dragging.value = false
  removePointerListeners()
  if (!challenge.value || props.disabled) return

  verifying.value = true
  errorMessage.value = ''
  const x = progress.value * (challenge.value.width - challenge.value.puzzle_width)
  try {
    const response = await authApi.verifySliderCaptcha({
      challenge_id: challenge.value.challenge_id,
      x,
    })
    emit('verified', response.captcha_token)
  } catch (error) {
    errorMessage.value = error instanceof ApiException ? error.message : '验证失败，已刷新验证码'
    await loadChallenge(true)
  } finally {
    verifying.value = false
  }
}

function reset() {
  void loadChallenge()
}

onMounted(() => {
  void loadChallenge()
  window.addEventListener('resize', syncRailWidth)
})

onBeforeUnmount(() => {
  removePointerListeners()
  window.removeEventListener('resize', syncRailWidth)
})

defineExpose({ reset })
</script>

<template>
  <div class="w-full select-none" aria-live="polite">
    <div v-if="challenge" class="overflow-hidden rounded-lg border border-line bg-card-soft p-2">
      <div class="relative aspect-[15/8] overflow-hidden rounded-md bg-canvas">
        <img :src="challenge.bg_image" alt="滑块验证码背景" class="absolute inset-0 h-full w-full object-cover" draggable="false" />
        <img
          :src="challenge.puzzle_image"
          alt=""
          class="pointer-events-none absolute h-auto shadow-md"
          :style="puzzleStyle"
          draggable="false"
        />
        <div v-if="loading || verifying" class="absolute inset-0 flex items-center justify-center bg-canvas/50">
          <div class="h-7 w-7 animate-spin rounded-full border-2 border-brand-100 border-t-brand-600" />
        </div>
      </div>

      <div ref="railRef" class="relative mt-3 h-10 rounded-md border border-line bg-canvas" @pointerdown.prevent>
        <div class="pointer-events-none absolute inset-y-0 left-0 flex items-center px-3 text-xs text-ink-muted">
          {{ verifying ? '正在验证...' : '拖动滑块完成验证' }}
        </div>
        <button
          type="button"
          class="absolute inset-y-0 left-0 z-10 flex w-10 items-center justify-center rounded-md border border-brand-200 bg-card text-brand-600 shadow-sm transition-colors hover:bg-brand-50 disabled:cursor-not-allowed disabled:opacity-60"
          :style="sliderStyle"
          :disabled="disabled || loading || verifying"
          aria-label="拖动滑块完成验证"
          @pointerdown="onPointerDown"
        >
          <el-icon><DArrowRight /></el-icon>
        </button>
      </div>
    </div>
    <div v-else class="flex min-h-28 items-center justify-center rounded-lg border border-line bg-card-soft">
      <el-button :loading="loading" :disabled="disabled" @click="reset">重新加载验证码</el-button>
    </div>

    <div class="mt-2 flex items-center justify-between gap-3 text-xs">
      <span :class="errorMessage ? 'text-danger' : 'text-ink-muted'">{{ errorMessage || '完成后将自动填入验证凭证' }}</span>
      <el-button link size="small" :disabled="disabled || loading || verifying" @click="reset">刷新</el-button>
    </div>
  </div>
</template>
