import { describe, expect, it } from 'vitest'
import { getContractSigningError } from '@/utils/contractSigningErrors'

describe('getContractSigningError', () => {
  it('never exposes the API path or exception type', () => {
    const result = getContractSigningError({
      exc_type: 'ValidationError',
      message: '/api/method/crm.api.contracts.request_otp ValidationError',
    })

    expect(result.message).not.toContain('/api/method')
    expect(result.message).not.toContain('ValidationError')
    expect(result.retryable).toBe(true)
  })

  it('explains an inactive link without exposing server details', () => {
    const result = getContractSigningError(
      {
        exc_type: 'AuthenticationError',
        messages: ['This signing link has expired.'],
      },
      'otp',
    )

    expect(result.kind).toBe('link')
    expect(result.message).toBe('This signing link is no longer active.')
    expect(result.retryable).toBe(false)
  })

  it('gives a clear outcome when a signer has already completed the step', () => {
    const result = getContractSigningError(
      {
        exc_type: 'ValidationError',
        messages: ['This signing slot has already been completed.'],
      },
      'otp',
    )

    expect(result.kind).toBe('completed')
    expect(result.retryable).toBe(false)
  })

  it('does not call a declined invitation completed', () => {
    const result = getContractSigningError(
      {
        exc_type: 'ValidationError',
        messages: ['This signing invitation is no longer active.'],
      },
      'otp',
    )

    expect(result.kind).toBe('inactive')
    expect(result.message).toContain('new signing link')
    expect(result.retryable).toBe(false)
  })

  it('explains an unavailable legacy status without claiming it was signed', () => {
    const result = getContractSigningError(
      {
        exc_type: 'ValidationError',
        messages: ['This signing invitation is not ready yet.'],
      },
      'otp',
    )

    expect(result.kind).toBe('not-ready')
    expect(result.message).not.toContain('already')
    expect(result.retryable).toBe(false)
  })

  it('turns rate limiting into an actionable wait message', () => {
    const result = getContractSigningError(
      {
        exc_type: 'PermissionError',
        messages: ['Too many requests. Please wait before trying again.'],
      },
      'otp',
    )

    expect(result.kind).toBe('rate-limit')
    expect(result.retryable).toBe(true)
  })
})
