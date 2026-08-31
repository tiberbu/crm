/**
 * Convert Frappe errors from the public contract-signing API into messages a
 * signer can act on. Frappe's request client puts the endpoint and exception
 * type in `error.message`; that is useful for diagnostics but must never be
 * shown in the guest-facing signing portal.
 */

const GENERIC_MESSAGES = {
  otp: {
    heading: 'We could not send your verification code',
    message:
      'Your signing link is still safe. Please try again to receive a new code.',
    hint: 'If this keeps happening, ask the contract issuer to send a fresh link.',
  },
  contract: {
    heading: 'We could not load the contract',
    message: 'Please try again. Your signing link has not been used.',
    hint: 'If this keeps happening, ask the contract issuer to send a fresh link.',
  },
  sign: {
    heading: 'We could not save your signature',
    message: 'Your signature has not been submitted. Please try again.',
    hint: 'If this keeps happening, ask the contract issuer for help.',
  },
  verify: {
    heading: 'We could not verify that code',
    message: 'Check the latest code in your email or phone and try again.',
    hint: 'You can request a new code when the current code expires.',
  },
}

function errorText(error) {
  const messages = Array.isArray(error?.messages) ? error.messages : []
  return [...messages, error?.exc, error?.message]
    .filter((value) => typeof value === 'string')
    .join(' ')
    .trim()
}

function details(phase) {
  return { ...GENERIC_MESSAGES[phase] }
}

/**
 * @param {unknown} error Frappe UI resource error
 * @param {'otp'|'verify'|'contract'|'sign'} phase
 * @returns {{heading: string, message: string, hint: string, retryable: boolean, kind: string}}
 */
export function getContractSigningError(error, phase = 'otp') {
  const fallback = details(GENERIC_MESSAGES[phase] ? phase : 'otp')
  const type = String(error?.exc_type || error?.exception || '')
  const text = errorText(error)
  const normalized = text.toLowerCase()

  if (
    (type === 'DoesNotExistError' || type === 'NotFoundError') &&
    phase !== 'verify'
  ) {
    return {
      heading: 'Link invalid or expired',
      message: 'This signing link is no longer active.',
      hint: 'Ask the contract issuer to send you a new signing link.',
      retryable: false,
      kind: 'link',
    }
  }

  if (
    type === 'AuthenticationError' &&
    phase !== 'verify' &&
    /session expired/.test(normalized)
  ) {
    return {
      heading: 'Your verification session has expired',
      message: 'Please refresh this page to request a new verification code.',
      hint: 'Your signing link is still safe to use.',
      retryable: false,
      kind: 'session',
    }
  }

  if (
    type === 'AuthenticationError' &&
    phase !== 'verify' &&
    /(invalid|expired|verification failed|signing link)/.test(normalized)
  ) {
    return {
      heading: 'Link invalid or expired',
      message: 'This signing link is no longer active.',
      hint: 'Ask the contract issuer to send you a new signing link.',
      retryable: false,
      kind: 'link',
    }
  }

  if (/already (been )?(completed|signed)|signing slot/.test(normalized)) {
    return {
      heading: 'This signing step is already complete',
      message: 'This link has already been used for this signing step.',
      hint: 'No further action is needed. Contact the contract issuer if you expected to sign again.',
      retryable: false,
      kind: 'completed',
    }
  }

  if (/declined|no longer active/.test(normalized)) {
    return {
      heading: 'This signing invitation is no longer active',
      message: 'Ask the contract issuer to send you a new signing link.',
      hint: 'The contract issuer can review this signing step and resend it.',
      retryable: false,
      kind: 'inactive',
    }
  }

  if (/not ready yet|review the contract/.test(normalized)) {
    return {
      heading: 'This signing link is not ready yet',
      message: 'The contract issuer needs to review this signing step first.',
      hint: 'Please contact the contract issuer so they can make it available.',
      retryable: false,
      kind: 'not-ready',
    }
  }

  if (
    type === 'PermissionError' &&
    /(too many|rate|request)/.test(normalized)
  ) {
    return {
      heading: 'Please wait a moment',
      message: 'There have been several requests in a short time.',
      hint: 'Wait about a minute, then try again.',
      retryable: true,
      kind: 'rate-limit',
    }
  }

  if (/csrf|session expired/.test(normalized)) {
    return {
      heading: 'Your signing session needs to be refreshed',
      message: 'Please try again to continue signing.',
      hint: 'If this keeps happening, ask the contract issuer to send a fresh link.',
      retryable: true,
      kind: 'session',
    }
  }

  if (/network|failed to fetch|timeout|offline|connection/.test(normalized)) {
    return {
      ...fallback,
      retryable: true,
      kind: 'network',
    }
  }

  return {
    ...fallback,
    retryable: true,
    kind: 'server',
  }
}
