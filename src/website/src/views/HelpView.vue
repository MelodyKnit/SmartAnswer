<script setup lang="ts">
/**
 * 帮助中心页面：采用纯 Markdown + 后端动态 API 驱动呈现。
 * - 免登录公开访问。
 * - 文档源自项目根目录 docs/help/*.md，修改文件后刷新网页即时生效，无需前端打包构建。
 * - 搜索支持实时下拉匹配：高亮匹配片段、点击直接打开该文章并滚动到匹配内容。
 * - 渲染后的内部链接（如 /tokens, /wallet）由 router 统一拦截；未登录点击自动跳转登录并携带 redirect。
 * - 支持侧边栏切换文章、文章大纲（TOC）快速定位。
 */
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { marked } from 'marked'
import { helpApi, type HelpDocItem } from '@/api/endpoints'
import { useAuthStore } from '@/stores/auth'
import { useSiteStore } from '@/stores/site'
import { useThemeStore, type ThemeMode } from '@/stores/theme'
import SiteLogo from '@/components/SiteLogo.vue'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const site = useSiteStore()
const theme = useThemeStore()

/* 主题切换图标与逻辑 */
const themeIcon = computed(() => {
  if (theme.mode === 'system') return 'Monitor'
  return theme.mode === 'dark' ? 'Moon' : 'Sunny'
})
function chooseTheme(mode: ThemeMode) {
  theme.setMode(mode)
}

const loading = ref(false)
const docs = ref<HelpDocItem[]>([])
const currentDocId = ref<string>('')
const searchQuery = ref('')
const isSearchFocused = ref(false)
const mobileDrawerVisible = ref(false)
const articleContentRef = ref<HTMLElement | null>(null)

// 动态分类组织（按文档自身 metadata.category 动态归类，无任何前端写死规则）
interface DocCategory {
  name: string
  icon: string
  items: HelpDocItem[]
}

const docCategories = computed<DocCategory[]>(() => {
  const map = new Map<string, HelpDocItem[]>()
  docs.value.forEach((item) => {
    const cat = item.category || '常见指南'
    if (!map.has(cat)) {
      map.set(cat, [])
    }
    map.get(cat)!.push(item)
  })

  const categories: DocCategory[] = []
  for (const [name, items] of map.entries()) {
    const firstIcon = items[0]?.icon || 'Document'
    categories.push({
      name,
      icon: firstIcon,
      items,
    })
  }
  return categories
})

// 当前查看的文档对象
const currentDoc = computed<HelpDocItem | null>(() => {
  if (docs.value.length === 0) return null
  return docs.value.find((d) => d.id === currentDocId.value) || docs.value[0]
})

// Markdown 渲染结果
const renderedHtml = computed(() => {
  if (!currentDoc.value?.content) return ''
  return marked.parse(currentDoc.value.content, {
    gfm: true,
    breaks: true,
  }) as string
})

// 搜索结果结构
interface SearchResult {
  doc: HelpDocItem
  matchTitle: boolean
  snippet: string
}

function escapeRegExp(string: string) {
  return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

// 在 HTML 文本中高亮匹配关键字（用于下拉展示）
function highlightSearchText(text: string, keyword: string): string {
  if (!text || !keyword) return text
  const escaped = escapeRegExp(keyword)
  const regex = new RegExp(`(${escaped})`, 'gi')
  return text.replace(regex, '<mark class="bg-amber-300/40 text-amber-600 dark:text-amber-300 font-semibold px-0.5 rounded">$1</mark>')
}

const searchResults = computed<SearchResult[]>(() => {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) return []

  const results: SearchResult[] = []

  docs.value.forEach((doc) => {
    const titleLower = doc.title.toLowerCase()
    const descLower = (doc.description || '').toLowerCase()
    const contentLower = doc.content.toLowerCase()

    const matchTitle = titleLower.includes(q)
    const matchDesc = descLower.includes(q)
    const contentIndex = contentLower.indexOf(q)

    if (matchTitle || matchDesc || contentIndex !== -1) {
      let snippet = ''
      if (contentIndex !== -1) {
        // 截取匹配词前后 40 个字符
        const start = Math.max(0, contentIndex - 20)
        const end = Math.min(doc.content.length, contentIndex + q.length + 40)
        const rawSnippet = doc.content.slice(start, end).replace(/[#*`~>\-_[\]]/g, ' ').replace(/\s+/g, ' ')
        snippet = `${start > 0 ? '...' : ''}${rawSnippet}${end < doc.content.length ? '...' : ''}`
      } else if (doc.description) {
        snippet = doc.description
      }

      results.push({
        doc,
        matchTitle,
        snippet,
      })
    }
  })

  return results
})

// 在正文中给关键字打上黄色边缘高亮并在 2 秒后淡出
function highlightAndScrollInArticle(keyword: string) {
  if (!keyword || !articleContentRef.value) return

  const container = articleContentRef.value
  const escaped = escapeRegExp(keyword)
  const regex = new RegExp(escaped, 'i')

  // 使用 TreeWalker 找到包含关键词的文本节点
  const walker = document.createTreeWalker(
    container,
    NodeFilter.SHOW_TEXT,
    null,
  )

  const nodesToHighlight: Text[] = []
  let currentNode: Node | null = walker.nextNode()
  while (currentNode) {
    if (currentNode.textContent && regex.test(currentNode.textContent)) {
      // 避免重复高亮或在脚本/样式节点中高亮
      const parent = currentNode.parentElement
      if (parent && !parent.classList.contains('search-highlight-pulse') && parent.tagName !== 'SCRIPT' && parent.tagName !== 'STYLE') {
        nodesToHighlight.push(currentNode as Text)
      }
    }
    currentNode = walker.nextNode()
  }

  let firstHighlightEl: HTMLElement | null = null

  nodesToHighlight.forEach((textNode) => {
    const text = textNode.textContent || ''
    const match = regex.exec(text)
    if (!match) return

    const span = document.createElement('span')
    span.className = 'search-highlight-pulse'
    span.textContent = match[0]

    const afterText = text.slice(match.index + match[0].length)
    const beforeText = text.slice(0, match.index)

    const parent = textNode.parentNode
    if (!parent) return

    if (beforeText) {
      parent.insertBefore(document.createTextNode(beforeText), textNode)
    }
    parent.insertBefore(span, textNode)
    if (afterText) {
      parent.insertBefore(document.createTextNode(afterText), textNode)
    }
    parent.removeChild(textNode)

    if (!firstHighlightEl) {
      firstHighlightEl = span
    }
  })

  if (firstHighlightEl) {
    (firstHighlightEl as HTMLElement).scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  // 2 秒后渐变淡出黄色边缘
  setTimeout(() => {
    const highlights = container.querySelectorAll('.search-highlight-pulse')
    highlights.forEach((el) => {
      el.classList.add('search-highlight-fade')
    })
  }, 2000)
}

function onSelectSearchResult(result: SearchResult) {
  const kw = searchQuery.value.trim()
  selectDoc(result.doc.id)
  isSearchFocused.value = false
  searchQuery.value = ''

  // 等待 markdown 渲染完成后执行定位与高亮
  nextTick(() => {
    setTimeout(() => {
      highlightAndScrollInArticle(kw)
    }, 150)
  })
}

// 文章大纲 (TOC)
interface TocItem {
  id: string
  text: string
  level: number
}
const tocList = ref<TocItem[]>([])

function updateToc() {
  nextTick(() => {
    if (!articleContentRef.value) return
    const headings = articleContentRef.value.querySelectorAll('h1, h2, h3')
    const tocs: TocItem[] = []
    headings.forEach((heading, index) => {
      const el = heading as HTMLElement
      const text = el.innerText.trim()
      const level = Number(el.tagName.replace('H', '')) || 2
      if (!el.id) {
        el.id = `heading-${index}-${text.slice(0, 10).replace(/\s+/g, '-')}`
      }
      tocs.push({
        id: el.id,
        text,
        level,
      })
    })
    tocList.value = tocs
  })
}

function scrollToHeading(id: string) {
  const el = document.getElementById(id)
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
}

// 切换文章
function selectDoc(docId: string) {
  currentDocId.value = docId
  mobileDrawerVisible.value = false
  router.replace({ query: { ...route.query, article: docId } })
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

// 上一篇 / 下一篇
const prevDoc = computed(() => {
  const idx = docs.value.findIndex((d) => d.id === currentDoc.value?.id)
  return idx > 0 ? docs.value[idx - 1] : null
})

const nextDoc = computed(() => {
  const idx = docs.value.findIndex((d) => d.id === currentDoc.value?.id)
  return idx >= 0 && idx < docs.value.length - 1 ? docs.value[idx + 1] : null
})

// 处理 Markdown 内容区域内的链接点击事件
function handleArticleClick(event: MouseEvent) {
  const target = (event.target as HTMLElement).closest('a')
  if (!target) return

  const href = target.getAttribute('href')
  if (!href) return

  // 外链：新窗口打开
  if (/^https?:\/\//i.test(href)) {
    target.setAttribute('target', '_blank')
    target.setAttribute('rel', 'noopener noreferrer')
    return
  }

  // 站内跳转链接（例如 /tokens, /wallet, /help?article=...）
  if (href.startsWith('/')) {
    event.preventDefault()
    // 检查是否指向 /help
    if (href.startsWith('/help')) {
      const url = new URL(href, window.location.origin)
      const article = url.searchParams.get('article')
      if (article) {
        selectDoc(article)
        return
      }
    }
    // 其他功能路由：使用 router.push 进行标准路由跳转
    // 若未登录，系统路由守卫会自动拦截并跳转至 /login?redirect=...
    router.push(href)
  }
}

async function loadDocs() {
  loading.value = true
  try {
    const res = await helpApi.list()
    docs.value = res.docs || []
    const queryArticle = route.query.article as string
    if (queryArticle && docs.value.some((d) => d.id === queryArticle)) {
      currentDocId.value = queryArticle
    } else if (docs.value.length > 0) {
      currentDocId.value = docs.value[0].id
    }
  } catch {
    docs.value = []
  } finally {
    loading.value = false
    updateToc()
  }
}

// 监听路由 query 变化
watch(
  () => route.query.article,
  (newArticle) => {
    if (typeof newArticle === 'string' && newArticle && newArticle !== currentDocId.value) {
      currentDocId.value = newArticle
    }
  },
)

watch(renderedHtml, () => {
  updateToc()
})

onMounted(loadDocs)
</script>

<template>
  <div class="min-h-screen bg-canvas text-ink flex flex-col" @click="isSearchFocused = false">
    <!-- 顶栏 Header -->
    <header class="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-line bg-card/90 px-4 backdrop-blur sm:px-8">
      <div class="flex items-center gap-3">
        <!-- 移动端抽屉开关 -->
        <button
          type="button"
          class="rounded p-1.5 text-ink-muted hover:bg-canvas hover:text-ink lg:hidden"
          @click="mobileDrawerVisible = true"
        >
          <el-icon :size="20"><Operation /></el-icon>
        </button>

        <div class="flex cursor-pointer items-center gap-2" @click="router.push('/')">
          <SiteLogo size="md" />
          <span class="font-bold text-lg text-ink">{{ site.title }}</span>
          <span class="rounded bg-brand-50 px-2 py-0.5 text-xs font-semibold text-brand-600">
            帮助中心
          </span>
        </div>
      </div>

      <div class="flex items-center gap-6">
        <!-- 搜索框与实时下拉结果 -->
        <div class="relative w-56 sm:w-80" @click.stop>
          <el-input
            v-model="searchQuery"
            placeholder="搜索文档与教程内容..."
            clearable
            prefix-icon="Search"
            size="default"
            @focus="isSearchFocused = true"
          />

          <!-- 搜索下拉弹窗 -->
          <transition name="el-zoom-in-top">
            <div
              v-if="isSearchFocused && searchQuery.trim()"
              class="absolute left-0 right-0 top-full mt-2 max-h-96 overflow-y-auto rounded-xl border border-line bg-card p-2 shadow-card z-50"
            >
              <div v-if="searchResults.length > 0" class="space-y-1">
                <div class="px-2.5 py-1 text-xs font-semibold text-ink-muted">
                  找到 {{ searchResults.length }} 篇相关文章
                </div>
                <div
                  v-for="res in searchResults"
                  :key="res.doc.id"
                  class="cursor-pointer rounded-lg p-2.5 text-left transition hover:bg-canvas"
                  @click="onSelectSearchResult(res)"
                >
                  <div class="flex items-center justify-between">
                    <span
                      class="font-medium text-sm text-ink"
                      v-html="highlightSearchText(res.doc.title, searchQuery)"
                    />
                    <span class="rounded bg-canvas px-1.5 py-0.5 text-xs text-ink-muted">
                      {{ res.doc.category }}
                    </span>
                  </div>
                  <div
                    v-if="res.snippet"
                    class="mt-1 line-clamp-2 text-xs text-ink-muted leading-relaxed"
                    v-html="highlightSearchText(res.snippet, searchQuery)"
                  />
                </div>
              </div>
              <div v-else class="py-6 text-center text-xs text-ink-muted">
                未找到包含「{{ searchQuery }}」的文档内容
              </div>
            </div>
          </transition>
        </div>

        <!-- 主题切换与操作区 -->
        <div class="flex items-center gap-2.5">
          <!-- 亮色/暗色/跟随系统调节 -->
          <el-dropdown trigger="click" @command="chooseTheme">
            <el-button circle text size="default">
              <el-icon :size="18"><component :is="themeIcon" /></el-icon>
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="light" :class="{ 'text-brand-600': theme.mode === 'light' }">
                  <el-icon><Sunny /></el-icon> 亮色
                </el-dropdown-item>
                <el-dropdown-item command="dark" :class="{ 'text-brand-600': theme.mode === 'dark' }">
                  <el-icon><Moon /></el-icon> 暗色
                </el-dropdown-item>
                <el-dropdown-item command="system" :class="{ 'text-brand-600': theme.mode === 'system' }">
                  <el-icon><Monitor /></el-icon> 跟随系统
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>

          <template v-if="auth.isLoggedIn">
            <el-button type="primary" size="default" @click="router.push('/')">
              进入工作台
            </el-button>
          </template>
          <template v-else>
            <el-button size="default" @click="router.push('/login')">
              登录
            </el-button>
            <el-button type="primary" size="default" @click="router.push('/register')">
              注册
            </el-button>
          </template>
        </div>
      </div>
    </header>

    <!-- 主体内容区 -->
    <div v-loading="loading" class="mx-auto flex w-full max-w-7xl flex-1 px-4 sm:px-6 lg:px-8">
      <!-- 桌面端左侧导航栏 -->
      <aside class="hidden w-64 shrink-0 border-r border-line py-6 pr-4 lg:block">
        <div class="sticky top-22 space-y-6">
          <div v-for="category in docCategories" :key="category.name" class="space-y-1">
            <div class="flex items-center gap-2 px-2 text-xs font-semibold uppercase tracking-wider text-ink-muted">
              <el-icon><component :is="category.icon" /></el-icon>
              <span>{{ category.name }}</span>
            </div>
            <ul class="mt-2 space-y-1">
              <li v-for="item in category.items" :key="item.id">
                <button
                  type="button"
                  class="flex w-full items-center justify-between rounded-md px-3 py-2 text-left text-sm font-medium transition-colors"
                  :class="[
                    currentDoc?.id === item.id
                      ? 'bg-brand-50 text-brand-600 font-semibold'
                      : 'text-ink-soft hover:bg-canvas hover:text-ink',
                  ]"
                  @click="selectDoc(item.id)"
                >
                  <span class="truncate">{{ item.title }}</span>
                  <el-icon v-if="currentDoc?.id === item.id" :size="14"><ArrowRight /></el-icon>
                </button>
              </li>
            </ul>
          </div>
          <div v-if="docCategories.length === 0" class="py-8 text-center text-xs text-ink-muted">
            暂无文档分类
          </div>
        </div>
      </aside>

      <!-- 移动端侧边抽屉 -->
      <el-drawer v-model="mobileDrawerVisible" title="文档目录" direction="ltr" size="260px">
        <div class="space-y-6">
          <div v-for="category in docCategories" :key="category.name" class="space-y-1">
            <div class="flex items-center gap-2 px-2 text-xs font-semibold uppercase tracking-wider text-ink-muted">
              <el-icon><component :is="category.icon" /></el-icon>
              <span>{{ category.name }}</span>
            </div>
            <ul class="mt-2 space-y-1">
              <li v-for="item in category.items" :key="item.id">
                <button
                  type="button"
                  class="flex w-full items-center justify-between rounded-md px-3 py-2 text-left text-sm font-medium transition-colors"
                  :class="[
                    currentDoc?.id === item.id
                      ? 'bg-brand-50 text-brand-600 font-semibold'
                      : 'text-ink-soft hover:bg-canvas hover:text-ink',
                  ]"
                  @click="selectDoc(item.id)"
                >
                  <span class="truncate">{{ item.title }}</span>
                </button>
              </li>
            </ul>
          </div>
        </div>
      </el-drawer>

      <!-- 文章阅读核心区 -->
      <main class="flex-1 py-8 lg:px-10">
        <template v-if="currentDoc">
          <!-- 面包屑与分类标识 -->
          <div class="mb-4 flex items-center gap-2 text-xs text-ink-muted">
            <span>帮助中心</span>
            <span>/</span>
            <span>{{ currentDoc.category }}</span>
          </div>

          <!-- 文章说明与描述 -->
          <div v-if="currentDoc.description" class="mb-6 rounded-lg border border-brand-200 bg-brand-50/50 p-4 text-sm text-brand-700 dark:border-brand-200/20 dark:text-brand-300">
            {{ currentDoc.description }}
          </div>

          <!-- Markdown HTML 渲染区（监听内部链接点击） -->
          <article
            ref="articleContentRef"
            class="markdown-body max-w-none text-ink"
            @click="handleArticleClick"
            v-html="renderedHtml"
          />

          <!-- 上一篇 / 下一篇导航卡片 -->
          <div class="mt-12 flex flex-col gap-4 border-t border-line pt-6 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <button
                v-if="prevDoc"
                type="button"
                class="group flex flex-col text-left transition-colors"
                @click="selectDoc(prevDoc.id)"
              >
                <span class="text-xs text-ink-muted">上一篇</span>
                <span class="mt-1 flex items-center gap-1 font-medium text-brand-600 group-hover:underline">
                  <el-icon><ArrowLeft /></el-icon>
                  {{ prevDoc.title }}
                </span>
              </button>
            </div>
            <div>
              <button
                v-if="nextDoc"
                type="button"
                class="group flex flex-col text-right transition-colors"
                @click="selectDoc(nextDoc.id)"
              >
                <span class="text-xs text-ink-muted">下一篇</span>
                <span class="mt-1 flex items-center gap-1 font-medium text-brand-600 group-hover:underline">
                  {{ nextDoc.title }}
                  <el-icon><ArrowRight /></el-icon>
                </span>
              </button>
            </div>
          </div>
        </template>
        <template v-else>
          <div class="py-20 text-center text-ink-muted">
            暂无可阅读的帮助文档
          </div>
        </template>
      </main>

      <!-- 桌面端右侧大纲 (TOC) -->
      <aside v-if="tocList.length > 0" class="hidden w-56 shrink-0 py-8 pl-6 xl:block">
        <div class="sticky top-22">
          <div class="text-xs font-semibold uppercase tracking-wider text-ink-muted">本页大纲</div>
          <ul class="mt-3 space-y-2 border-l border-line pl-3 text-xs">
            <li v-for="toc in tocList" :key="toc.id">
              <a
                :href="`#${toc.id}`"
                class="block truncate text-ink-muted hover:text-brand-600 transition-colors"
                :class="{ 'pl-2': toc.level === 3, 'font-medium text-ink-soft': toc.level === 2 }"
                @click.prevent="scrollToHeading(toc.id)"
              >
                {{ toc.text }}
              </a>
            </li>
          </ul>
        </div>
      </aside>
    </div>
  </div>
</template>

<style scoped>
/* 深度美化 Markdown 渲染正文 */
:deep(.markdown-body) {
  line-height: 1.75;
  font-size: 0.95rem;
}

:deep(.markdown-body h1) {
  font-size: 1.85rem;
  font-weight: 800;
  margin-bottom: 1.5rem;
  color: var(--c-ink);
  border-bottom: 1px solid var(--c-line);
  padding-bottom: 0.5rem;
}

:deep(.markdown-body h2) {
  font-size: 1.35rem;
  font-weight: 700;
  margin-top: 2rem;
  margin-bottom: 1rem;
  color: var(--c-ink);
  scroll-margin-top: 5rem;
}

:deep(.markdown-body h3) {
  font-size: 1.1rem;
  font-weight: 600;
  margin-top: 1.5rem;
  margin-bottom: 0.75rem;
  color: var(--c-ink);
  scroll-margin-top: 5rem;
}

:deep(.markdown-body p) {
  margin-bottom: 1rem;
  color: var(--c-ink-soft);
}

:deep(.markdown-body ul) {
  list-style-type: disc;
  padding-left: 1.5rem;
  margin-bottom: 1rem;
}

:deep(.markdown-body ol) {
  list-style-type: decimal;
  padding-left: 1.5rem;
  margin-bottom: 1rem;
}

:deep(.markdown-body li) {
  margin-bottom: 0.35rem;
  color: var(--c-ink-soft);
}

:deep(.markdown-body a) {
  color: var(--c-brand-600);
  font-weight: 500;
  text-decoration: underline;
  text-underline-offset: 3px;
  cursor: pointer;
  transition: opacity 0.2s;
}

:deep(.markdown-body a:hover) {
  opacity: 0.8;
}

:deep(.markdown-body blockquote) {
  border-left: 4px solid var(--c-brand-500);
  background-color: var(--c-brand-50);
  color: var(--c-ink);
  padding: 0.75rem 1rem;
  margin: 1.25rem 0;
  border-radius: 0 8px 8px 0;
}

:deep(.markdown-body pre) {
  background-color: #151821;
  border: 1px solid var(--c-line);
  color: #f8fafc;
  padding: 1rem;
  border-radius: 10px;
  overflow-x: auto;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 0.875rem;
  margin: 1.25rem 0;
}

:deep(.markdown-body code) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  background-color: var(--c-canvas);
  border: 1px solid var(--c-line);
  padding: 0.15rem 0.4rem;
  border-radius: 6px;
  font-size: 0.875em;
  color: var(--c-brand-600);
}

:deep(.markdown-body pre code) {
  background-color: transparent;
  border: none;
  padding: 0;
  color: inherit;
}

:deep(.markdown-body table) {
  width: 100%;
  border-collapse: collapse;
  margin: 1.5rem 0;
}

:deep(.markdown-body th),
:deep(.markdown-body td) {
  border: 1px solid var(--c-line);
  padding: 0.6rem 0.9rem;
  text-align: left;
}

:deep(.markdown-body th) {
  background-color: var(--c-card-soft);
  color: var(--c-ink);
  font-weight: 600;
}

/* 搜索关键字跳转定位高亮：黄色边缘 + 微光，2秒渐变消失 */
:deep(.search-highlight-pulse) {
  display: inline-block;
  padding: 0 4px;
  margin: 0 1px;
  border-radius: 4px;
  border: 2px solid #eab308;
  background-color: rgba(250, 204, 21, 0.25);
  box-shadow: 0 0 10px rgba(234, 179, 8, 0.45);
  transition: all 1.8s cubic-bezier(0.4, 0, 0.2, 1);
}

:deep(.search-highlight-pulse.search-highlight-fade) {
  border-color: transparent;
  background-color: transparent;
  box-shadow: none;
}
</style>
