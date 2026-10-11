import { describe, expect, it } from 'vitest'
import {
  OTP_LENGTH,
  applyBackspace,
  applyInput,
  applyPaste,
  isComplete,
  sanitizeOtp,
} from '@/utils/otpCode'

describe('otpCode', () => {
  it('keeps only digits up to the code length', () => {
    expect(sanitizeOtp(' 12-34 56 78 ')).toBe('123456')
    expect(sanitizeOtp(null)).toBe('')
  })

  it('fills boxes in order and advances focus', () => {
    expect(applyInput('', 0, '4')).toEqual({ code: '4', focusIndex: 1 })
    expect(applyInput('4', 1, '7')).toEqual({ code: '47', focusIndex: 2 })
  })

  it('cannot skip ahead of the first empty box', () => {
    expect(applyInput('4', 4, '9')).toEqual({ code: '49', focusIndex: 2 })
  })

  it('replaces a digit in place when a filled box is retyped', () => {
    expect(applyInput('123456', 2, '9')).toEqual({
      code: '129456',
      focusIndex: 3,
    })
  })

  it('ignores non-digit input', () => {
    expect(applyInput('12', 2, 'x')).toEqual({ code: '12', focusIndex: 2 })
  })

  it('treats a multi-digit value as a paste or autofill', () => {
    expect(applyInput('', 0, '123456')).toEqual({
      code: '123456',
      focusIndex: 5,
    })
    expect(applyPaste('9', 3, '12 34-56')).toEqual({
      code: '912345',
      focusIndex: 5,
    })
  })

  it('removes the digit in the box, or the previous one when the box is empty', () => {
    expect(applyBackspace('123', 1)).toEqual({ code: '13', focusIndex: 1 })
    expect(applyBackspace('123', 3)).toEqual({ code: '12', focusIndex: 2 })
    expect(applyBackspace('', 0)).toEqual({ code: '', focusIndex: 0 })
  })

  it('reports completion only for a full code', () => {
    expect(OTP_LENGTH).toBe(6)
    expect(isComplete('12345')).toBe(false)
    expect(isComplete('123456')).toBe(true)
  })

  it('supports other lengths', () => {
    expect(applyPaste('', 0, '12345678', 4)).toEqual({
      code: '1234',
      focusIndex: 3,
    })
  })
})
