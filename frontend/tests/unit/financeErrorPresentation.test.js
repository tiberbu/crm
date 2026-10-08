import { describe, expect, it } from 'vitest'
import { getErrorPresentation, readableError } from '../../src/pages/FinanceCockpit/composables/financeErrors.js'

describe('Finance error presentation', () => {
  it('turns the raw whitelist failure into a deployment error without retry', () => {
    const error = {
      message:
        '<details><summary>You are not permitted to access this resource. Login to access</summary>Function <strong>crm.finance.api.get_ar_invoices</strong> is not whitelisted.</details>',
      exc_type: 'PermissionError',
    }

    const presentation = getErrorPresentation(error)

    expect(readableError(error)).toContain('Function crm.finance.api.get_ar_invoices is not whitelisted.')
    expect(presentation.kind).toBe('configuration')
    expect(presentation.retryable).toBe(false)
    expect(presentation.nextStep).toContain('reload')
  })

  it('keeps transient failures retryable', () => {
    const presentation = getErrorPresentation({ message: 'Request timed out' })

    expect(presentation.kind).toBe('transient')
    expect(presentation.retryable).toBe(true)
  })
})
