/** 后端数据契约的 TypeScript 类型定义（与 FastAPI 响应字段严格对齐）。 */

export type Role = 'superadmin' | 'admin' | 'user'

export interface User {
  user_id: string
  username: string
  display_name: string
  role: Role
  status: string
  email: string | null
  points: number
  invite_code: string
  invited_by: string
  created_at: number
}

export interface Billing {
  local_hit: number
  web_search: number
  llm_fallback: number
}

export interface PointsPolicy {
  default_user_points: number
  invite_bonus_points: number
  manual_grant_default_points: number
  redeem_code_default_points: number
}

export interface WalletSummary {
  user_id: string
  username: string
  points: number
}

export interface ApiToken {
  token_id: string
  user_id?: string
  key_mask: string
  description: string
  status: string
  created_at: number
  last_used_at: number
  usage_count: number
  quota_limit?: number
  quota_used?: number
  reject_low_confidence?: boolean
  min_answer_confidence?: number
}

export interface OcsConfigItem {
  name: string
  url: string
  headers?: Record<string, string>
  [key: string]: unknown
}

export type OcsConfig = OcsConfigItem[]

export interface UsageLog {
  log_id: string
  user_id: string
  username: string
  token_id: string | null
  title: string
  question_type: string
  resolution_mode: string
  answer: string | null
  confidence: number
  points_cost: number
  provider: string
  elapsed_ms: number
  created_at: number
  request_id?: string
  options?: string | string[] | null
  question_id?: string | null
  source_name?: string
  source_type?: string
  source_id?: string
  source_url?: string
}

export interface Feedback {
  feedback_id: string
  user_id: string
  username: string
  usage_log_id: string | null
  category: string
  title: string
  content: string
  image_urls: string[]
  status: string
  admin_note: string
  corrected_answer: string
  reward_points: number
  handled_by: string
  handled_at: number
  created_at: number
  question_id?: string | null
  question_title?: string
  question_type?: string
  answer_snapshot?: string | null
  resolution_mode?: string
  confidence?: number
  request_id?: string
  source_name?: string
  source_type?: string
  source_id?: string
  source_url?: string
  context?: Record<string, unknown>
}

export interface WalletOrder {
  order_id: string
  user_id: string
  username: string
  kind: string
  points_delta: number
  source: string
  source_id: string | null
  status: string
  created_by: string
  created_at: number
}

export interface WalletChange {
  change_id?: string
  order_id?: string
  user_id?: string
  username?: string
  points_delta: number
  balance_after?: number
  source: string
  source_id?: string | null
  remark?: string
  created_by?: string
  created_at: number
}

export interface RedeemCode {
  code_id: string
  code: string
  kind: string
  points: number
  max_uses: number
  used_uses: number
  status: string
  created_by: string
  created_at: number
  expires_at: number
}

export interface ImportScript {
  script_id: string
  name: string
  integration_id: string | null
  token_id: string | null
  target: string
  content: string
  status: string
  created_at: number
  updated_at: number
  description?: string
  requires_token?: boolean
  tags?: string[]
  builtin?: boolean
  is_default?: boolean
  ocs_config?: OcsConfig
}

export interface RolePermission {
  role_id: string
  permissions: string[]
  updated_at: number
}

export interface NotificationItem {
  notification_id: string
  user_id: string | null
  level: string
  category: string
  title: string
  content: string
  read: boolean
  created_at: number
}

export interface RankingItem {
  rank: number
  label: string
  count: number
}

export interface TrendPoint {
  date: string
  count: number
}

export interface Workbench {
  scope: 'self' | 'global'
  hero: { title: string; subtitle: string; badges: string[] }
  quick_actions: {
    key: string
    label: string
    path: string
    action: 'navigate' | 'copy_import_script'
    requires_role: Role
  }[]
  overview: {
    today_calls: number
    success_rate: number
    avg_response_seconds: number
    remaining_points: number
  }
  trend: { days: number; items: TrendPoint[] }
  question_distribution: Record<string, number>
  ranking_preview: RankingItem[]
  notifications_preview: NotificationItem[]
  service_status: { api: string; search_provider: string; llm_model: string }
}

export interface DashboardSummary {
  scope: 'self' | 'global'
  days: number
  points_used: number
  query_count: number
  resolution_modes: Record<string, number>
  trend: { date: string; query_count: number; points_used: number }[]
}

export interface UsageAudit {
  date: string
  timezone: string
  evidence_status: string
  gaps: string[]
  usage_logs: {
    count: number
    resolution_modes: Record<string, number>
  }
  api_tokens: {
    usage_count_total: number
    quota_used_total: number
    daily_count_available: boolean
  }
  runtime_logs: {
    query_event_count: number
    malformed_line_count: number
  }
  diff: {
    usage_logs_vs_runtime_queries: number
  }
}

export interface SystemConfig {
  smart_proto_enabled?: string
  custom_proto_header?: string
  default_user_points?: string
  invite_bonus_points?: string
  manual_grant_default_points?: string
  redeem_code_default_points?: string
  answer_retry_times?: string
  registration_enabled?: string
  [key: string]: string | boolean | undefined
}

export interface LlmRuntimeConfig {
  llm_fallback?: string
  llm_explain?: string
  allow_known_rules?: string
  no_local_bank_mode?: string
  search_first?: string
  self_consistency_repeats?: string
  web_search_provider?: string
  web_search_configs?: string
  search_proxy?: string
  llm_proxy?: string
  google_search_api_key_configured?: boolean
  google_search_cx_configured?: boolean
  baidu_search_api_key_configured?: boolean
  llm_cache_enabled?: string
  llm_cache_min_confidence?: string
  llm_cache_min_confirmations?: string
  [key: string]: string | boolean | undefined
}

export type PlaywrightSearchEngine = 'bing' | 'baidu' | 'google' | 'duckduckgo'

export type WebSearchProviderTemplate = 'duckduckgo' | 'google' | 'baidu' | 'playwright'

export interface WebSearchConfig {
  id: string
  name: string
  provider: WebSearchProviderTemplate
  search_engine?: PlaywrightSearchEngine | ''
  api_key?: string
  cx?: string
  proxy_url?: string
  status: 'active' | 'inactive'
  api_key_configured?: boolean
  builtin?: boolean
}

export interface LlmModel {
  model_id: string
  name: string
  base_url: string
  model: string
  api_key?: string
  role: string
  priority: number
  stream: boolean
  max_completion_tokens: number
  timeout_seconds: number
  status: string
  api_key_configured?: boolean
  created_at?: number
  updated_at?: number
}

export interface LlmCallStat {
  model_id?: string | null
  model_name?: string | null
  total_calls: number
  ok_calls: number
  error_calls: number
  avg_elapsed_ms: number
}

export interface LlmCallTraceEvidence {
  title?: string
  url?: string
  snippet?: string
}

export interface LlmCallTrace {
  trace_id?: string
  request_id?: string | null
  model_id?: string | null
  model_name?: string | null
  provider?: string | null
  base_url?: string | null
  phase: string
  question_title?: string | null
  candidate_answer?: string | null
  confidence: number
  ok: boolean
  elapsed_ms: number
  error?: string | null
  prompt?: string | null
  response_text?: string | null
  evidence?: LlmCallTraceEvidence[]
  created_at: number
}

/** /query 在线搜题的成功结果。 */
export interface QueryResultPayload {
  ok: true
  request_id: string | null
  query: { title: string; type: string; options: string[] }
  result: {
    candidate_answer: string | null
    answer_text: string | null
    explanation: string | null
    confidence: number
    resolution_mode: string
    review_required: boolean
  }
  sources: {
    source_name: string
    source_type: string
    source_id: string | null
    source_url: string | null
    score: number
  }[]
  debug: Record<string, string>
}

/** 运行时事件（/debug/recent），用于系统日志页。 */
export interface RuntimeEvent {
  ts: string
  event: string
  [key: string]: unknown
}

export interface TokenImportScriptResponse {
  mode: 'direct' | 'select_token'
  token_id?: string
  token_option?: ApiToken
  token_options?: ApiToken[]
  script?: string
  ocs_config?: OcsConfig
  requires_local_secret?: boolean
}

export interface QuestionRecord {
  question_id: string
  title_raw: string
  question_type: string
  options_raw: string[]
  answer_raw: string | null
  explanation: string | null
  subject: string
  chapter: string | null
  tags: string[]
  source_name: string
  source_url: string
  source_license: string
  source_split: string
  source_record_path: string
  passage: string | null
  metadata: Record<string, string>
  status?: string
  confidence?: number
  created_at?: number
  updated_at?: number
}
