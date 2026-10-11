// Pure editing rules for a segmented one-time-code input. The code is always a
// contiguous run of digits, so a box can never be filled before the one on its left.

export const OTP_LENGTH = 6

export function sanitizeOtp(value, length = OTP_LENGTH) {
  return String(value ?? '')
    .replace(/\D/g, '')
    .slice(0, length)
}

function result(code, length, focus) {
  return { code, focusIndex: Math.max(0, Math.min(focus, length - 1)) }
}

// Typing or autofill into box `index`. A multi-digit value is treated as a paste.
export function applyInput(code, index, typed, length = OTP_LENGTH) {
  const digits = sanitizeOtp(typed, length)
  if (!digits) return result(sanitizeOtp(code, length), length, index)
  if (digits.length > 1) return applyPaste(code, index, digits, length)
  const current = sanitizeOtp(code, length)
  const position = Math.min(index, current.length)
  const next = (
    current.slice(0, position) +
    digits +
    current.slice(position + 1)
  ).slice(0, length)
  return result(next, length, position + 1)
}

export function applyBackspace(code, index, length = OTP_LENGTH) {
  const current = sanitizeOtp(code, length)
  if (index < current.length) {
    return result(
      current.slice(0, index) + current.slice(index + 1),
      length,
      index,
    )
  }
  const previous = Math.max(0, current.length - 1)
  return result(current.slice(0, previous), length, previous)
}

export function applyPaste(code, index, pasted, length = OTP_LENGTH) {
  const current = sanitizeOtp(code, length)
  const position = Math.min(index, current.length)
  const next = sanitizeOtp(
    current.slice(0, position) + sanitizeOtp(pasted, length),
    length,
  )
  return result(next, length, next.length)
}

export function isComplete(code, length = OTP_LENGTH) {
  return sanitizeOtp(code, length).length === length
}
