/** 站点品牌配置：标题、Logo 与浏览器标题/favicon 同步。 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { siteConfigApi } from '@/api/endpoints'
import type { SiteConfig, SystemConfig } from '@/api/types'

const DEFAULT_SITE_TITLE = 'AI题库'
const DEFAULT_FAVICON = '/favicon.svg'

function normalizeTitle(value?: string): string {
  return (value || '').trim() || DEFAULT_SITE_TITLE
}

function normalizeLogoUrl(value?: string): string {
  return (value || '').trim()
}

export const useSiteStore = defineStore('site', () => {
  const siteTitle = ref(DEFAULT_SITE_TITLE)
  const siteLogoUrl = ref('')
  const siteLogoUrls = ref({
    original: '',
    lg: '',
    md: '',
    sm: '',
  })
  const currentRouteTitle = ref<string | undefined>()
  const initialized = ref(false)

  const title = computed(() => siteTitle.value)
  const logoUrl = computed(() => siteLogoUrl.value)
  const logoUrls = computed(() => siteLogoUrls.value)

  function applyConfig(config: Partial<SiteConfig | SystemConfig>): void {
    siteTitle.value = normalizeTitle(config.site_title)
    siteLogoUrl.value = normalizeLogoUrl(config.site_logo_url)
    const rawUrls = config.site_logo_urls
    if (rawUrls && typeof rawUrls === 'object') {
      siteLogoUrls.value = {
        original: normalizeLogoUrl(rawUrls.original),
        lg: normalizeLogoUrl(rawUrls.lg),
        md: normalizeLogoUrl(rawUrls.md),
        sm: normalizeLogoUrl(rawUrls.sm),
      }
    } else {
      const defaultUrl = normalizeLogoUrl(config.site_logo_url)
      siteLogoUrls.value = {
        original: defaultUrl,
        lg: defaultUrl,
        md: defaultUrl,
        sm: defaultUrl,
      }
    }
    applyBrowserBrand()
  }

  function applyBrowserBrand(routeTitle?: string): void {
    if (arguments.length > 0) {
      currentRouteTitle.value = routeTitle
    }
    const pageTitle = normalizeTitle(currentRouteTitle.value)
    document.title = pageTitle === siteTitle.value ? siteTitle.value : `${pageTitle} - ${siteTitle.value}`

    let favicon = document.querySelector<HTMLLinkElement>('link[rel~="icon"]')
    if (!favicon) {
      favicon = document.createElement('link')
      favicon.rel = 'icon'
      document.head.appendChild(favicon)
    }
    favicon.href = siteLogoUrls.value.sm || siteLogoUrl.value || DEFAULT_FAVICON
  }

  async function load(): Promise<void> {
    try {
      const config = await siteConfigApi.get()
      applyConfig(config)
    } catch {
      applyBrowserBrand()
    } finally {
      initialized.value = true
    }
  }

  return {
    title,
    logoUrl,
    logoUrls,
    initialized,
    applyConfig,
    applyBrowserBrand,
    load,
  }
})
