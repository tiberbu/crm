import { describe, expect, it } from 'vitest'
import { recordName } from '../../src/pages/FinanceCockpit/composables/financeInputs.js'

describe('Finance request input normalization', () => {
  it('accepts a combobox record name', () => {
    expect(recordName('SINV-0001')).toBe('SINV-0001')
  })

  it('extracts a record name from a combobox option object', () => {
    expect(recordName({ label: 'SINV-0001 · Customer', value: 'SINV-0001' })).toBe('SINV-0001')
    expect(recordName({ name: 'SINV-0002' })).toBe('SINV-0002')
  })

  it('does not send objects without a record name to the API', () => {
    expect(recordName({ label: 'Incomplete option' })).toBe('')
    expect(recordName(null)).toBe('')
  })
})
