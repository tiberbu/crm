import { describe, expect, it } from 'vitest'
import { tokenBalance, tokenBalanceText } from '@/utils/tokenBalance'

describe('tokenBalance', () => {
  it('shows the live balance only when metering reports one', () => {
    expect(
      tokenBalanceText(
        { token_balance: { status: 'ok', balance: 48250 } },
        ' tokens',
      ),
    ).toBe('48,250 tokens')
    expect(
      tokenBalance({ token_balance: { status: 'ok', balance: '12.5' } }),
    ).toEqual({ known: true, value: 12.5 })
  })

  it('treats a metered facility with no grant as zero', () => {
    expect(
      tokenBalanceText({ token_balance: { status: 'not_metered' } }, ' tokens'),
    ).toBe('0 tokens')
  })

  it('never reports zero when there is no live balance', () => {
    expect(tokenBalanceText({}, ' tokens')).toBe('Not reported')
    expect(tokenBalanceText({ token_balance: null })).toBe('Not reported')
    expect(tokenBalanceText({ token_balance: { status: 'unavailable' } })).toBe(
      'Unavailable',
    )
    expect(tokenBalance({}).known).toBe(false)
  })
})
