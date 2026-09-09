/** 兑换码分享链接：兑换码只放在 URL fragment 中，不发送给服务端。 */

export const REDEEM_SHARE_PATH = '/share/redeem'
export const PENDING_REDEEM_CODE_KEY = 'stqb_pending_redeem_code'

export function buildRedeemShareUrl(origin: string, code: string): string {
  const normalizedOrigin = origin.trim().replace(/\/+$/, '')
  const normalizedCode = code.trim()
  return `${normalizedOrigin}${REDEEM_SHARE_PATH}#code=${encodeURIComponent(normalizedCode)}`
}

export function readRedeemCodeFromHash(hash: string): string {
  const value = hash.startsWith('#') ? hash.slice(1) : hash
  return new URLSearchParams(value).get('code')?.trim() || ''
}
