/** 前端展示格式化工具。 */

export function formatDateTime(value?: number | string | null): string {
  if (!value) return '—'
  const date = typeof value === 'number' ? new Date(value * 1000) : new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

export function relativeTime(value?: number | string | null): string {
  if (!value) return '—'
  const time = typeof value === 'number' ? value : Math.floor(new Date(value).getTime() / 1000)
  const diff = Date.now() / 1000 - time
  if (!Number.isFinite(diff)) return '—'
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`
  return `${Math.floor(diff / 86400)}天前`
}

const ANSWER_SOURCE_LABELS: Record<string, string> = {
  exact_match: '精确匹配',
  fuzzy_match: '模糊匹配',
  known_rule: '规则命中',
  ai_cache: 'AI 缓存',
  rag_match: 'RAG 匹配',
  external_source: '外部来源',
  llm_normalized: 'LLM 规范化',
  llm_fallback: 'LLM 兜底',
  fallback: '兜底',
  model_error: '模型错误',
  not_found: '未命中',
}

export function answerSourceLabel(value?: string | null): string {
  return (value && ANSWER_SOURCE_LABELS[value]) || value || '未知'
}

export function resolutionLabel(value?: string | null): string {
  return answerSourceLabel(value)
}

const QUESTION_TYPE_LABELS: Record<string, string> = {
  single: '单选题',
  multiple: '多选题',
  judgement: '判断题',
  completion: '填空题',
  unknown: '未知',
}

export function questionTypeLabel(value?: string | null): string {
  return (value && QUESTION_TYPE_LABELS[value]) || value || '未知'
}

export const FEEDBACK_CATEGORIES = [
  { value: 'wrong_answer', label: '题目答错' },
  { value: 'answer', label: '答题问题' },
  { value: 'system', label: '系统问题' },
  { value: 'suggestion', label: '功能建议' },
  { value: 'other', label: '其他' },
]

const FEEDBACK_CATEGORY_LABELS = Object.fromEntries(FEEDBACK_CATEGORIES.map((item) => [item.value, item.label]))

export function feedbackCategoryLabel(value?: string | null): string {
  return (value && FEEDBACK_CATEGORY_LABELS[value]) || value || '其他'
}

export const FEEDBACK_STATUS_META: Record<string, { label: string; type: 'warning' | 'primary' | 'success' | 'info' }> = {
  open: { label: '待处理', type: 'warning' },
  processing: { label: '处理中', type: 'primary' },
  resolved: { label: '已解决', type: 'success' },
  rejected: { label: '已驳回', type: 'info' },
}

export function feedbackStatusLabel(value?: string | null): string {
  return (value && FEEDBACK_STATUS_META[value]?.label) || value || '待处理'
}

const WALLET_SOURCE_LABELS: Record<string, string> = {
  redeem_code: '兑换码',
  manual_credit: '管理员发放',
  admin_grant: '管理员发放',
  usage_charge: '接口扣费',
  feedback_reward: '反馈奖励',
  invite_bonus: '邀请奖励',
  refund: '退回',
}

export function walletSourceLabel(value?: string | null): string {
  return (value && WALLET_SOURCE_LABELS[value]) || value || '未知'
}
