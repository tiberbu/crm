import { describe, expect, it } from 'vitest'
import {
  decodeEntities,
  htmlToText,
  optionalServiceDisplay,
} from '@/utils/optionalServices'

describe('decodeEntities', () => {
  it('decodes named and numeric entities', () => {
    expect(decodeEntities('A &amp; B &#8212; C &#x2014; &quot;D&quot;')).toBe(
      'A & B — C — "D"',
    )
  })
  it('leaves unknown entities untouched', () => {
    expect(decodeEntities('&bogus; &#0;')).toBe('&bogus; &#0;')
  })
})

describe('htmlToText', () => {
  it('strips tags and collapses whitespace', () => {
    expect(htmlToText('<div><p>One</p><p>Two<br>Three</p></div>')).toBe(
      'One Two Three',
    )
  })
  it('handles empty values', () => {
    expect(htmlToText(null)).toBe('')
    expect(htmlToText(undefined)).toBe('')
  })
  it('keeps decoded angle brackets as text, not markup', () => {
    expect(htmlToText('&lt;b&gt;bold&lt;/b&gt;')).toBe('<b>bold</b>')
  })
})

describe('optionalServiceDisplay', () => {
  it('drops a description that only repeats the name', () => {
    const row = optionalServiceDisplay({
      item_code: 'X',
      item_name: 'Implementation &amp; Training',
      description: '<div>Implementation &amp; Training</div>',
    })
    expect(row.label).toBe('Implementation & Training')
    expect(row.detail).toBe('')
    expect(row.item_code).toBe('X')
  })
  it('keeps a distinct description as plain text', () => {
    const row = optionalServiceDisplay({
      item_code: 'Y',
      item_name: 'Laptop',
      description: '<p>14&quot; business laptop</p>',
    })
    expect(row.detail).toBe('14" business laptop')
  })
  it('falls back to the item code without a name', () => {
    expect(optionalServiceDisplay({ item_code: 'Z' }).label).toBe('Z')
  })
})
