import assert from 'node:assert/strict'
import test from 'node:test'
import { buildRedeemShareUrl, readRedeemCodeFromHash } from '../../src/website/src/utils/redeem-share.ts'

test('兑换码分享链接只使用 fragment 并正确编码兑换码', () => {
  const url = buildRedeemShareUrl('https://example.test/', ' VIP_A+B#1 ')

  assert.equal(url, 'https://example.test/share/redeem#code=VIP_A%2BB%231')
  assert.equal(url.includes('?code='), false)
  assert.equal(readRedeemCodeFromHash('#code=VIP_A%2BB%231'), 'VIP_A+B#1')
})
