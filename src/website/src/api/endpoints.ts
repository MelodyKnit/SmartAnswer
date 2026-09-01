/** 平台业务接口封装。所有函数返回已解包的数据片段。 */
import http, { api } from './http'
import type {
  Announcement,
  AnnouncementAudience,
  AnnouncementAudienceOption,
  AnnouncementLevel,
  AnnouncementStatus,
  EmailDomainWhitelist,
  ApiToken,
  Billing,
  DashboardSummary,
  ProjectUpdateStatus,
  Feedback,
  ImportScript,
  ImageGenerationCapabilities,
  ImageGenerationInputAsset,
  ImageGenerationInputReference,
  ImageGenerationJob,
  ImageGenerationMode,
  ImageGenerationModel,
  ImageGenerationOutputOptions,
  ImageGenerationStats,
  ImageGenerationTrace,
  LlmCallStat,
  LlmCallTrace,
  LlmModel,
  LlmRuntimeConfig,
  ManagedUser,
  NotificationItem,
  NotificationCenterItem,
  NotificationCenterSource,
  OcsConfig,
  PermissionDefinition,
  PointsPolicy,
  QueryResultPayload,
  QuestionRecord,
  RankingItem,
  RedeemCode,
  RolePermission,
  RuntimeEvent,
  SiteConfig,
  UsageAudit,
  SystemConfig,
  TokenImportScriptResponse,
  User,
  UsageLog,
  WalletChange,
  WalletOrder,
  WalletSummary,
  Workbench,
} from './types'

/* ---------------- 认证 ---------------- */
export const authApi = {
  register: (body: {
    username: string
    password: string
    email?: string
    email_code?: string
    invite_code?: string
  }) => api.post<{ ok: true; user: User }>('/auth/register', body),
  sendEmailVerificationCode: (body: { email: string; purpose?: 'register' }) =>
    api.post<{ ok: true; message: string; cooldown_seconds: number }>('/auth/email-verification-codes', {
      purpose: 'register',
      ...body,
    }),
  registerStatus: () =>
    api.get<{
      ok: true
      registration_enabled: boolean
      config_enabled: boolean
      first_user_allowed: boolean
      email_registration_mode: 'optional' | 'required' | 'verified'
      email_verification_enabled: boolean
      email_required: boolean
    }>('/auth/register-status'),
  login: (body: { username: string; password: string; remember: boolean }) =>
    api.post<{ ok: true; user: User; token: string; expires_in: number }>('/auth/login', body),
  session: () => api.get<{ ok: true; user: User }>('/auth/session'),
  logout: () => api.post<{ ok: true }>('/auth/logout'),
  resetRequest: (username: string) =>
    api.post<{ ok: true; message: string }>('/auth/reset-request', { username }),
  resetConfirm: (body: { username: string; token: string; new_password: string }) =>
    api.post<{ ok: true; message: string }>('/auth/reset-confirm', body),
}

/* ---------------- 用户中心 ---------------- */
export const userApi = {
  me: () => api.get<{ ok: true; user: User; billing: Billing; wallet: WalletSummary }>('/users/me'),
  list: () => api.get<{ ok: true; users: ManagedUser[] }>('/users'),
  update: (
    username: string,
    body: {
      role?: string
      points?: number
      status?: string
      unlimited_expires_at?: number
    },
  ) =>
    api.patch<{ ok: true; user: User }>(`/users/${encodeURIComponent(username)}`, body),
  updateProfile: (display_name: string) =>
    api.patch<{ ok: true; user: User }>('/users/me/profile', { display_name }),
  ensureInviteCode: () => api.post<{ ok: true; user: User }>('/users/me/invite-code'),
  changePassword: (body: { old_password: string; new_password: string }) =>
    api.post<{ ok: true; message: string }>('/users/me/password', body),
  batchDelete: (usernames: string[]) =>
    api.post<{ ok: true; deleted: string[]; skipped: { username: string; reason: string }[] }>(
      '/users/batch-delete',
      { usernames },
    ),
}

/* ---------------- 在线搜题 ---------------- */
export const queryApi = {
  search: (body: {
    raw_text?: string
    title?: string
    options?: string[]
    type?: string
    image_urls?: string[]
  }) =>
    api.post<QueryResultPayload>('/query', body),
}

/* ---------------- 运行状态 / 系统日志 ---------------- */
export const systemApi = {
  status: () => api.get<Record<string, unknown>>('/status'),
  recentEvents: (params?: { start_date?: string; end_date?: string }) =>
    api.get<{ ok: true; events: RuntimeEvent[] }>('/debug/recent', params),
  usageAudit: (date?: string) =>
    api.get<{ ok: true; audit: UsageAudit }>('/debug/usage-audit', date ? { date } : {}),
}

/* ---------------- API 令牌 ---------------- */
export const tokenApi = {
  list: () => api.get<{ ok: true; tokens: ApiToken[] }>('/tokens'),
  create: (description: string, quotaLimit = -1, rejectLowConfidence = false, minAnswerConfidence = 0) =>
    api.post<{ ok: true; token: string; token_info: ApiToken; ocs_config: OcsConfig }>('/tokens', {
      description,
      quota_limit: quotaLimit,
      reject_low_confidence: rejectLowConfidence,
      min_answer_confidence: minAnswerConfidence,
    }),
  revoke: (tokenId: string) =>
    api.post<{ ok: true; token: ApiToken }>(`/tokens/${encodeURIComponent(tokenId)}/revoke`),
  update: (tokenId: string, description: string, quotaLimit = -1, rejectLowConfidence = false, minAnswerConfidence = 0) =>
    api.post<{ ok: true; token: ApiToken }>(`/tokens/${encodeURIComponent(tokenId)}`, {
      description,
      quota_limit: quotaLimit,
      reject_low_confidence: rejectLowConfidence,
      min_answer_confidence: minAnswerConfidence,
    }),
  delete: (tokenId: string) =>
    api.delete<{ ok: true; message: string }>(`/tokens/${encodeURIComponent(tokenId)}`),
  importScript: (tokenId?: string) =>
    api.get<{ ok: true } & TokenImportScriptResponse>('/tokens/import-script', tokenId ? { token_id: tokenId } : {}),
  copyValue: (tokenId: string) =>
    api.post<{ ok: true; token_id: string; token: string }>(
      `/tokens/${encodeURIComponent(tokenId)}/copy-value`,
    ),
  shareLink: (tokenId: string) =>
    api.post<{ ok: true; token_id: string; share_url: string }>(
      `/tokens/${encodeURIComponent(tokenId)}/share-link`,
    ),
}

/* ---------------- 无状态 API Key 分享 ---------------- */
export const shareApi = {
  apikeyTemplate: () =>
    api.get<{
      ok: true
      template_id: string
      script: string
      ocs_config: OcsConfig
    }>('/shares/apikey-template'),
}

/* ---------------- 使用记录 / 反馈 / 看板 ---------------- */
export const usageApi = {
  logs: (params: {
    username?: string
    keyword?: string
    token_id?: string
    page?: number
    limit?: number
  } = {}) =>
    api.get<{ ok: true; logs: UsageLog[]; total: number }>('/usage-logs', params),
  summary: (days = 30, scope?: 'self' | 'global') =>
    api.get<{ ok: true; summary: DashboardSummary }>('/dashboard/summary', {
      days,
      ...(scope ? { scope } : {}),
    }),
}

export const feedbackApi = {
  list: (params: {
    username?: string
    status?: string
    category?: string
    page?: number
    limit?: number
  } = {}) =>
    api.get<{ ok: true; feedbacks: Feedback[]; total: number }>('/feedback', params),
  create: (body: {
    usage_log_id?: string | null
    category?: string
    title: string
    content: string
    image_urls?: string[]
  }) => api.post<{ ok: true; feedback: Feedback }>('/feedback', body),
  resolve: (
    feedbackId: string,
    body: {
      status?: string
      admin_note?: string
      corrected_answer?: string
      reward_points?: number
    },
  ) =>
    api.patch<{ ok: true; feedback: Feedback; granted_points: number }>(
      `/feedback/${encodeURIComponent(feedbackId)}`,
      body,
    ),
}

/* ---------------- 工作台 / 排行 / 消息 ---------------- */
export const dashboardApi = {
  workbench: (scope?: 'self' | 'global') =>
    api.get<{ ok: true; workbench: Workbench }>('/dashboard/workbench', scope ? { scope } : {}),
  rankings: (params: {
    days?: number
    limit?: number
    dimension?: string
    scope?: 'self' | 'global'
  } = {}) =>
    api.get<{ ok: true; rankings: RankingItem[] }>('/dashboard/rankings', params),
}

export const notificationApi = {
  list: (params: { status?: string; limit?: number } = {}) =>
    api.get<{ ok: true; notifications: NotificationItem[] }>('/notifications', params),
  read: (id: string) =>
    api.post<{ ok: true; notification: NotificationItem }>(
      `/notifications/${encodeURIComponent(id)}/read`,
    ),
  readAll: () => api.post<{ ok: true; count: number }>('/notifications/read-all'),
}

export const notificationCenterApi = {
  list: (
    params: {
      status?: '' | 'read' | 'unread'
      source?: '' | NotificationCenterSource
      limit?: number
    } = {},
  ) =>
    api.get<{
      ok: true
      items: NotificationCenterItem[]
      unread_count: number
      total: number
    }>('/notification-center', params),
  read: (source: NotificationCenterSource, id: string) =>
    api.post<{ ok: true; item: NotificationCenterItem }>(
      `/notification-center/${encodeURIComponent(source)}/${encodeURIComponent(id)}/read`,
    ),
  readAll: () => api.post<{ ok: true; count: number }>('/notification-center/read-all'),
}

/* ---------------- 公告 ---------------- */
export const announcementApi = {
  list: (params: {
    keyword?: string
    status?: string
    level?: string
    audience?: string
    page?: number
    limit?: number
  } = {}) =>
    api.get<{
      ok: true
      announcements: Announcement[]
      audience_options: AnnouncementAudienceOption[]
      total: number
      page: number
      limit: number
    }>('/announcements', params),
  active: (limit = 10) =>
    api.get<{ ok: true; announcements: Announcement[] }>('/announcements/active', { limit }),
  create: (body: {
    title: string
    content: string
    level: AnnouncementLevel
    audience: AnnouncementAudience
    status: AnnouncementStatus
    pinned: boolean
    starts_at?: number
    ends_at?: number
  }) => api.post<{ ok: true; announcement: Announcement }>('/announcements', body),
  update: (
    announcementId: string,
    body: Partial<{
      title: string
      content: string
      level: AnnouncementLevel
      audience: AnnouncementAudience
      status: AnnouncementStatus
      pinned: boolean
      starts_at: number
      ends_at: number
    }>,
  ) =>
    api.patch<{ ok: true; announcement: Announcement }>(
      `/announcements/${encodeURIComponent(announcementId)}`,
      body,
    ),
  archive: (announcementId: string) =>
    api.delete<{ ok: true; announcement_id: string; status: string }>(
      `/announcements/${encodeURIComponent(announcementId)}`,
    ),
}

/* ---------------- 计费 / 系统配置 ---------------- */
export const billingApi = {
  get: () => api.get<{ ok: true; billing: Billing }>('/billing'),
  update: (body: Partial<Billing>) => api.patch<{ ok: true; billing: Billing }>('/billing', body),
  pointsPolicy: () => api.get<{ ok: true; points_policy: PointsPolicy }>('/points-policy'),
}

export const systemConfigApi = {
  get: () => api.get<{ ok: true; config: SystemConfig }>('/system-config'),
  update: (body: Record<string, string>) =>
    api.patch<{ ok: true; config: SystemConfig; reload_required: boolean }>('/system-config', body),
  emailDomainWhitelist: () =>
    api.get<{ ok: true } & EmailDomainWhitelist>('/system/email-domain-whitelist'),
  updateEmailDomainWhitelist: (domains: string[]) =>
    api.put<{ ok: true } & EmailDomainWhitelist>('/system/email-domain-whitelist', { domains }),
}

export const projectUpdateApi = {
  status: () => api.get<{ ok: true; update: ProjectUpdateStatus }>('/project-update/status'),
  check: () => api.post<{ ok: true; update: ProjectUpdateStatus }>('/project-update/check'),
}

export const siteConfigApi = {
  get: () => api.get<{ ok: true } & SiteConfig>('/site-config'),
}

/* ---------------- 钱包 / 兑换码 ---------------- */
export const walletApi = {
  me: () => api.get<{ ok: true; wallet: WalletSummary }>('/wallet/me'),
  orders: (params: { source?: string; page?: number; limit?: number } = {}) =>
    api.get<{ ok: true; orders: WalletOrder[]; total: number }>('/wallet/orders', params),
  changes: (params: {
    username?: string
    kind?: string
    source?: string
    page?: number
    limit?: number
  } = {}) =>
    api.get<{ ok: true; orders: WalletOrder[]; changes?: WalletChange[]; total: number }>(
      '/wallet/changes',
      params,
    ),
  grant: (body: {
    username: string
    kind?: 'points' | 'days'
    points?: number
    days?: number
  }) => api.post<{ ok: true; order: WalletOrder }>('/wallet/grants', body),
  redeemCodes: () => api.get<{ ok: true; redeem_codes: RedeemCode[] }>('/wallet/redeem-codes'),
  createRedeemCode: (body: {
    kind: 'points' | 'days'
    points?: number
    days?: number
    max_uses?: number
    expires_at?: number
    code?: string
    count?: number
  }) => api.post<{ ok: true; redeem_code: RedeemCode }>('/wallet/redeem-codes', body),
  redeem: (code: string) =>
    api.post<{ ok: true; order: WalletOrder; wallet: WalletSummary; user?: User }>('/wallet/redeem', { code }),
}

/* ---------------- 导入脚本 ---------------- */
export const importScriptApi = {
  list: () => api.get<{ ok: true; scripts: ImportScript[] }>('/import-scripts'),
  get: (id: string) =>
    api.get<{ ok: true; script: ImportScript }>(`/import-scripts/${encodeURIComponent(id)}`),
  create: (body: {
    name: string
    description?: string
    target?: string
    content?: string
    script_template?: string
    config_items?: Record<string, unknown>[]
    ocs_config?: OcsConfig
    requires_token?: boolean
    tags?: string[]
    is_default?: boolean
    status?: string
  }) => api.post<{ ok: true; script: ImportScript }>('/import-scripts', body),
  generate: (body: {
    name: string
    token_id?: string | null
    target: string
    include_test_snippet: boolean
  }) => api.post<{ ok: true; script: ImportScript }>('/import-scripts/generate', body),
  remove: (id: string) => api.delete<{ ok: true }>(`/import-scripts/${encodeURIComponent(id)}`),
}

/* ---------------- 角色权限 ---------------- */
export const roleApi = {
  list: () =>
    api.get<{ ok: true; roles: RolePermission[]; permission_catalog: PermissionDefinition[] }>('/roles'),
  permissions: (roleId: string) =>
    api.get<{ ok: true; role: RolePermission }>(
      `/roles/${encodeURIComponent(roleId)}/permissions`,
    ),
  setPermissions: (roleId: string, permissions: string[]) =>
    api.put<{ ok: true; role: RolePermission }>(
      `/roles/${encodeURIComponent(roleId)}/permissions`,
      { permissions },
    ),
  create: (body: { role_id: string; name: string; description: string; permissions: string[] }) =>
    api.post<{ ok: true; role: RolePermission }>('/roles', body),
  update: (
    roleId: string,
    body: { name?: string; description?: string; permissions?: string[] },
  ) => api.patch<{ ok: true; role: RolePermission }>(`/roles/${encodeURIComponent(roleId)}`, body),
  remove: (roleId: string) =>
    api.delete<{ ok: true; role_id: string; deleted: boolean }>(
      `/roles/${encodeURIComponent(roleId)}`,
    ),
}

export const questionApi = {
  list: (params: {
    page?: number
    limit?: number
    question_id?: string
    keyword?: string
    type?: string
    source?: string
    status?: string
    updated_start_date?: string
    updated_end_date?: string
    subject?: string
    topic?: string
    question_type?: string
  } = {}) =>
    api.get<{
      ok: true
      total: number
      page: number
      limit: number
      questions: QuestionRecord[]
      all_types: string[]
      all_sources: string[]
    }>('/questions', params),
  reindex: () => api.post<{ ok: true; indexed_count: number }>('/questions/reindex'),
  update: (
    questionId: string,
    body: {
      title_raw?: string
      question_type?: string
      options_raw?: string[]
      answer_raw?: string
      explanation?: string
      subject?: string
      tags?: string[]
    },
  ) =>
    api.patch<{ ok: true; question: QuestionRecord }>(
      `/questions/${encodeURIComponent(questionId)}`,
      body,
    ),
  remove: (questionId: string) =>
    api.delete<{ ok: true; question_id: string; status: string }>(
      `/questions/${encodeURIComponent(questionId)}`,
    ),
}

/* ---------------- 大模型配置 / 调用追溯 ---------------- */
export const llmApi = {
  runtimeConfig: () => api.get<{ ok: true; config: LlmRuntimeConfig }>('/llm-runtime-config'),
  updateRuntimeConfig: (body: Record<string, string>) =>
    api.patch<{ ok: true; config: LlmRuntimeConfig }>('/llm-runtime-config', body),
  models: () => api.get<{ ok: true; models: LlmModel[] }>('/llm-models'),
  createModel: (body: Record<string, unknown>) =>
    api.post<{ ok: true; model: LlmModel }>('/llm-models', body),
  updateModel: (modelId: string, body: Record<string, unknown>) =>
    api.patch<{ ok: true; model: LlmModel }>(`/llm-models/${encodeURIComponent(modelId)}`, body),
  deleteModel: (modelId: string) =>
    api.delete<{ ok: true }>(`/llm-models/${encodeURIComponent(modelId)}`),
  testModel: (modelId: string) =>
    api.post<{
      ok: boolean
      elapsed_ms: number
      error?: string
      candidate_answer?: string
      answer_text?: string
      explanation?: string
      confidence?: number
    }>(`/llm-models/${encodeURIComponent(modelId)}/test`),
  stats: () => api.get<{ ok: true; stats: LlmCallStat[] }>('/llm-stats'),
  traces: (params: {
    request_id?: string
    model_id?: string
    phase?: string
    page?: number
    limit?: number
  } = {}) =>
    api.get<{ ok: true; traces: LlmCallTrace[]; total: number }>('/llm-traces', params),
}

/* ---------------- 生图与私有图片编辑 ---------------- */
export const imageGenerationApi = {
  capabilities: () =>
    api.get<{ ok: true; capabilities: ImageGenerationCapabilities }>('/image-generation-capabilities'),
  inferSize: (prompt: string) =>
    api.post<{ ok: true; output: ImageGenerationOutputOptions; explanation: string }>(
      '/image-generation-infer-size',
      { prompt },
    ),
  create: (body: {
    prompt: string
    size?: string
    mode?: ImageGenerationMode
    input_assets?: ImageGenerationInputReference[]
    output?: ImageGenerationOutputOptions
    idempotency_key: string
  }) =>
    api.post<{ ok: true; job: ImageGenerationJob; idempotent_replay: boolean }>(
      '/image-generations',
      body,
    ),
  uploadInput: async (file: File, kind: 'source' | 'mask') => {
    const form = new FormData()
    form.append('image', file)
    const response = await http.post<{ ok: true; asset: ImageGenerationInputAsset }>(
      `/image-generation-inputs?kind=${encodeURIComponent(kind)}`,
      form,
    )
    return response.data
  },
  inputs: (params: { page?: number; limit?: number } = {}) =>
    api.get<{
      ok: true
      assets: ImageGenerationInputAsset[]
      total: number
      page: number
      limit: number
    }>('/image-generation-inputs', params),
  inputContent: async (inputId: string): Promise<Blob> => {
    const response = await http.get<Blob>(
      `/image-generation-inputs/${encodeURIComponent(inputId)}/content`,
      { responseType: 'blob' },
    )
    return response.data
  },
  deleteInput: (inputId: string) =>
    api.delete<{ ok: true; asset: ImageGenerationInputAsset }>(
      `/image-generation-inputs/${encodeURIComponent(inputId)}`,
    ),
  list: (params: { status?: string; page?: number; limit?: number; user_id?: string } = {}) =>
    api.get<{ ok: true; jobs: ImageGenerationJob[]; total: number; page: number; limit: number }>(
      '/image-generations',
      params,
    ),
  detail: (jobId: string) =>
    api.get<{ ok: true; job: ImageGenerationJob }>(
      `/image-generations/${encodeURIComponent(jobId)}`,
    ),
  delete: (jobId: string) =>
    api.delete<{ ok: true; job: ImageGenerationJob }>(
      `/image-generations/${encodeURIComponent(jobId)}`,
    ),
  assetContent: async (jobId: string, assetId: string): Promise<Blob> => {
    const response = await http.get<Blob>(
      `/image-generations/${encodeURIComponent(jobId)}/assets/${encodeURIComponent(assetId)}/content`,
      { responseType: 'blob' },
    )
    return response.data
  },
  models: () => api.get<{ ok: true; models: ImageGenerationModel[] }>('/image-generation-models'),
  createModel: (body: Record<string, unknown>) =>
    api.post<{ ok: true; model: ImageGenerationModel }>('/image-generation-models', body),
  updateModel: (modelId: string, body: Record<string, unknown>) =>
    api.patch<{ ok: true; model: ImageGenerationModel }>(
      `/image-generation-models/${encodeURIComponent(modelId)}`,
      body,
    ),
  deleteModel: (modelId: string) =>
    api.delete<{ ok: true }>(`/image-generation-models/${encodeURIComponent(modelId)}`),
  testModel: (
    modelId: string,
    operation: 'text_to_image' | 'whole_edit' | 'masked_edit' | 'multi_reference' = 'text_to_image',
  ) =>
    api.post<{ ok: boolean; operation: string; elapsed_ms: number; error?: string }>(
      `/image-generation-models/${encodeURIComponent(modelId)}/test`,
      { operation },
    ),
  stats: () => api.get<{ ok: true; stats: ImageGenerationStats }>('/image-generation-stats'),
  traces: (params: { job_id?: string; model_id?: string; page?: number; limit?: number } = {}) =>
    api.get<{ ok: true; traces: ImageGenerationTrace[]; total: number; page: number; limit: number }>(
      '/image-generation-traces',
      params,
    ),
}
