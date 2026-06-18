import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

export type ThemeMode = 'light' | 'dark' | 'system'

const STORAGE_KEY = 'stqb_theme_mode'
const media = window.matchMedia?.('(prefers-color-scheme: dark)')

export const useThemeStore = defineStore('theme', () => {
  const mode = ref<ThemeMode>('system')
  const systemDark = ref(Boolean(media?.matches))
  const effectiveMode = computed(() => (mode.value === 'system' ? (systemDark.value ? 'dark' : 'light') : mode.value))

  function apply() {
    document.documentElement.classList.toggle('dark', effectiveMode.value === 'dark')
  }

  function setMode(value: ThemeMode) {
    mode.value = value
    localStorage.setItem(STORAGE_KEY, value)
    apply()
  }

  function init() {
    const saved = localStorage.getItem(STORAGE_KEY) as ThemeMode | null
    if (saved === 'light' || saved === 'dark' || saved === 'system') mode.value = saved
    media?.addEventListener('change', (event) => {
      systemDark.value = event.matches
      apply()
    })
    apply()
  }

  return { mode, effectiveMode, setMode, init }
})
