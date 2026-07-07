import type { LlmCallTrace } from '@/api/types'

export const phaseLabel: Record<string, string> = {
  answer: '模型作答',
  answer_with_evidence: '证据作答',
  verify_answer: '答案自检',
  verify_answer_with_evidence: '证据复核',
  model_request: '模型请求',
  model_decode: '响应解码',
  model_parse: '答案解析',
  web_search: '联网检索',
  failover: '主备降级',
}

export function traceOutputLabel(row: LlmCallTrace) {
  if (row.phase === 'web_search') {
    const count = row.evidence?.length || 0
    return count > 0 ? `命中 ${count} 条证据` : '未命中证据'
  }
  return row.candidate_answer || row.response_text || '—'
}

export function traceResultLabel(row: LlmCallTrace) {
  if (!row.ok) {
    return '失败'
  }
  if (row.phase === 'web_search') {
    return (row.evidence?.length || 0) > 0 ? '有证据' : '无证据'
  }
  return '成功'
}

export function traceResultType(row: LlmCallTrace) {
  if (!row.ok) {
    return 'danger'
  }
  if (row.phase === 'web_search' && !(row.evidence?.length || 0)) {
    return 'warning'
  }
  return 'success'
}

export function traceCandidateLabel(row: LlmCallTrace) {
  if (row.phase === 'web_search') {
    return '不适用'
  }
  return row.candidate_answer || '—'
}
