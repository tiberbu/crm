import { describe, expect, it } from 'vitest'
import { getErrorPresentation, readableError } from '../../src/pages/FinanceCockpit/composables/financeErrors.js'

describe('Finance error presentation', () => {
  it('turns a technical deployment failure into a clear action without exposing internals', () => {
    const error = {
      message:
        '<details><summary>You are not permitted to access this resource. Login to access</summary>Function <strong>crm.finance.api.get_ar_invoices</strong> is not whitelisted.</details>',
      exc_type: 'PermissionError',
    }

    const presentation = getErrorPresentation(error)

    expect(readableError(error)).not.toContain('crm.finance.api')
    expect(readableError(error)).toContain('Finance action is not available yet')
    expect(presentation.kind).toBe('configuration')
    expect(presentation.retryable).toBe(false)
    expect(presentation.nextStep).toContain('refresh')
  })

  it('keeps transient failures retryable', () => {
    const presentation = getErrorPresentation({ message: 'Request timed out' })

    expect(presentation.kind).toBe('transient')
    expect(presentation.retryable).toBe(true)
  })

  it('turns the dictionary lower crash into a useful next step', () => {
    const presentation = getErrorPresentation({
      message: "AttributeError: 'dict' object has no attribute 'lower'",
      exc_type: 'AttributeError',
    })

    expect(presentation.kind).toBe('request')
    expect(presentation.title).toBe('The request could not be understood')
    expect(presentation.message).not.toContain('AttributeError')
    expect(presentation.nextStep).toContain('Refresh')
    expect(presentation.retryable).toBe(false)
  })
})
