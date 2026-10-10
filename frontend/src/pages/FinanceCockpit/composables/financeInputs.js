/**
 * Normalize a record selected from a Combobox before sending it to the server.
 * Different Combobox implementations return either the option value or the
 * complete option object; API endpoints always receive the record name.
 */
export function recordName(value) {
  if (typeof value === 'string') return value.trim()
  if (value && typeof value === 'object') {
    const name = value.value || value.name
    return typeof name === 'string' ? name.trim() : ''
  }
  return ''
}
