/** 后端数据契约的 TypeScript 类型定义（与 FastAPI 响应字段严格对齐）。 */

/** 角色标识由后端角色目录动态维护，系统内置角色只是其中三个记录。 */
export type Role = string
export type InviteRewardMode = 'inviter' | 'invitee' | 'both'

export interface User {
  user_id: string
  username: string
  display_name: string
  role: Role
  role_name?: string
  role_is_system?: boolean
  permissions?: string[]
  status: string
  email: string | null
  points: number
  invite_code: string
  invited_by: string
  created_at: number
}

export interface ManagedUser extends User {
  usage_count: number
}

export interface Billing {
  local_hit: number
  web_search: number
  llm_fallback: number
  invite_bonus_points?: number
  invite_reward_mode?: InviteRewardMode
}

export interface PointsPolicy {
  default_user_points: number
  invite_bonus_points: number
  invite_reward_mode: InviteRewardMode
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
  token_description?: string
  token_key_mask?: string
  token_label?: string
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
  client_ip?: string
  options?: string | string[] | null
  context?: {
    options?: string[]
    image_urls?: string[]
    option_image_urls?: Record<string, string>
    input_flags?: string[]
    error_code?: string | null
    error_message?: string | null
  }
  context_json?: string
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

export interface PermissionDefinition {
  key: string
  group: string
  group_label: string
  label: string
  description: string
  icon: string
}

export interface RolePermission {
  role_id: string
  name: string
  description: string
  permissions: string[]
  is_system: boolean
  created_at: number
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

export type NotificationCenterSource = 'notification' | 'announcement'

export interface NotificationCenterItem {
  item_id: string
  source: NotificationCenterSource
  level: string
  category: string
  title: string
  content: string
  read: boolean
  pinned: boolean
  created_at: number
  updated_at: number
  expires_at: number
}

export type AnnouncementLevel = 'info' | 'success' | 'warning' | 'danger'
/** 公告受众为 all 或后端角色目录中的任意稳定角色标识。 */
export type AnnouncementAudience = string
export type AnnouncementStatus = 'draft' | 'published' | 'archived'

export interface AnnouncementAudienceOption {
  value: AnnouncementAudience
  label: string
}

export interface Announcement {
  announcement_id: string
  title: string
  content: string
  level: AnnouncementLevel
  audience: AnnouncementAudience
  status: AnnouncementStatus
  pinned: boolean
  starts_at: number
  ends_at: number
  created_by: string
  created_at: number
  updated_at: number
  published_at: number
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
    requires_permissions: string[]
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
  site_title?: string
  site_logo_url?: string
  site_logo_urls?: {
    original: string
    lg: string
    md: string
    sm: string
  }
  smart_proto_enabled?: string
  custom_proto_header?: string
  default_user_points?: string
  invite_bonus_points?: string
  invite_reward_mode?: InviteRewardMode
  manual_grant_default_points?: string
  redeem_code_default_points?: string
  image_generation_points?: string
  image_generation_max_active_jobs?: string
  image_generation_daily_limit?: string
  image_generation_retention_days?: string
  answer_retry_times?: string
  registration_enabled?: string
  registration_email_mode?: 'optional' | 'required' | 'verified'
  email_verification_enabled?: string
  smtp_host?: string
  smtp_port?: string
  smtp_security?: string
  smtp_username?: string
  smtp_password_configured?: boolean
  smtp_from_email?: string
  smtp_from_name?: string
  email_code_ttl_minutes?: string
  email_code_cooldown_seconds?: string
  email_code_daily_limit?: string
  email_code_ip_hourly_limit?: string
  email_code_max_attempts?: string
  [key: string]: any
}

export type ProjectUpdateState =
  | 'unavailable'
  | 'idle'
  | 'failed'

export interface ProjectUpdateRelease {
  version: string
  tag: string
  name: string
  body: string
  published_at: string
  html_url: string
  image: string
  image_digest: string
  build_sha: string
}

export interface ProjectUpdateStatus {
  available: boolean
  repository: string
  current_version: string
  build_sha: string
  build_type: string
  latest_version: string
  has_update: boolean
  checked_at: number
  state: ProjectUpdateState
  message: string
  error: string
  release: ProjectUpdateRelease | null
}

export interface EmailDomainWhitelist {
  domains: string[]
}

export interface SiteConfig {
  site_title: string
  site_logo_url: string
  site_logo_urls?: {
    original: string
    lg: string
    md: string
    sm: string
  }
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

/** 文本生图模型、任务、资产与调用追溯的数据契约。 */
export type ImageGenerationJobStatus =
  | 'queued'
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'rejected'
  | 'cancelled'
  | 'deleted'

export type ImageGenerationProvider =
  | 'gemini-native'
  | 'openai-images'
  | 'openai-compatible-images'
  | 'openai-chat-image'

export type ImageGenerationMode =
  | 'text_to_image'
  | 'image_edit'
  | 'masked_edit'
  | 'multi_reference'

export type ImageGenerationInputRole = 'source' | 'reference' | 'mask'

export interface ImageGenerationInputReference {
  source_kind: 'uploaded' | 'generated'
  source_id: string
  source_job_id?: string
  role: ImageGenerationInputRole
}

export interface ImageGenerationInputAsset {
  input_id: string
  user_id: string
  kind: 'source' | 'mask' | string
  mime_type: string
  width: number
  height: number
  byte_size: number
  created_at: number
  expires_at: number
  deleted_at: number
}

export interface ImageGenerationInputCapabilities {
  available_modes: ImageGenerationMode[]
  verified_operations: string[]
  max_input_images: number
  mask_mode: 'guided' | 'native' | 'none' | string
  requires_capability_test: boolean
}

export interface ImageGenerationOutputOptions {
  size?: string
  aspect_ratio?: string
  image_size?: string
  mode?: 'model-controlled'
}

export type ImageGenerationOutputCapabilities =
  | {
      kind: 'gemini'
      aspect_ratios: string[]
      image_sizes: string[]
    }
  | {
      kind: 'openai-images'
      preset_sizes: string[]
      allow_custom_size: boolean
      custom_size_constraints: {
        min_width: number
        max_width: number
        min_height: number
        max_height: number
        step: number
        min_pixels: number
        max_pixels: number
      }
    }
  | {
      kind: 'compatible-images'
      preset_sizes: string[]
      allow_custom_size: false
    }
  | { kind: 'model-controlled' | 'unavailable' }

export interface ImageGenerationModel {
  model_id: string
  name: string
  provider: ImageGenerationProvider | string
  base_url: string
  model: string
  api_key_configured: boolean
  timeout_seconds: number
  status: 'active' | 'inactive' | string
  capabilities: string[]
  protocol_config: Record<string, unknown>
  created_at: number
  updated_at: number
}

export interface ImageGenerationAsset {
  asset_id: string
  job_id: string
  mime_type: string
  width: number
  height: number
  byte_size: number
  created_at: number
  deleted_at: number
}

export interface ImageGenerationJob {
  job_id: string
  user_id: string
  username: string
  prompt: string
  mode: ImageGenerationMode
  size: string
  output: ImageGenerationOutputOptions
  model_id: string
  model_name: string
  status: ImageGenerationJobStatus
  points_cost: number
  error_code: string
  error_message: string
  created_at: number
  started_at: number
  completed_at: number
  updated_at: number
  expires_at: number
  assets: ImageGenerationAsset[]
}

export interface ImageGenerationCapabilities {
  available: boolean
  model_name: string
  provider: ImageGenerationProvider | ''
  sizes: string[]
  output: ImageGenerationOutputCapabilities
  input: ImageGenerationInputCapabilities
  points_per_image: number
  max_active_jobs: number
  daily_limit: number
  retention_days: number
  balance: number
}

export interface ImageGenerationTrace {
  trace_id: string
  job_id: string
  model_id: string
  model_name: string
  provider: string
  phase: string
  provider_request_id: string
  ok: boolean
  elapsed_ms: number
  error_code: string
  error: string
  created_at: number
}

export interface ImageGenerationStats {
  total_jobs: number
  queued_jobs: number
  running_jobs: number
  succeeded_jobs: number
  failed_jobs: number
  rejected_jobs: number
  cancelled_jobs: number
  deleted_jobs: number
  avg_elapsed_ms: number
}

/** /query 在线搜题的成功结果。 */
export interface QueryResultPayload {
  ok: true
  request_id: string | null
  query: {
    title: string
    type: string
    options: string[]
    image_urls?: string[]
    option_image_urls?: Record<string, string>
  }
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
