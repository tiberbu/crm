function stripMarkup(value) {
  return String(value || '')
    .replace(/<[^>]*>/g, ' ')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&amp;/g, '&')
    .replace(/\s+/g, ' ')
    .trim()
}

function errorValue(err) {
  return err && typeof err === 'object' && 'value' in err ? err.value : err
}

function serverMessage(err) {
  const value = errorValue(err)
  if (!value) return ''
  if (Array.isArray(value.messages) && value.messages.length)
    return value.messages.map(stripMarkup).filter(Boolean).join('\n')
  if (value._server_messages) {
    try {
      const messages = JSON.parse(value._server_messages)
      if (Array.isArray(messages)) {
        return messages
          .map((message) => {
            try {
              return stripMarkup(JSON.parse(message).message || message)
            } catch {
              return stripMarkup(message)
            }
          })
          .filter(Boolean)
          .join('\n')
      }
    } catch {
      return stripMarkup(value._server_messages)
    }
  }
  if (typeof value === 'string') return stripMarkup(value)
  return stripMarkup(value.message || value.exception || value.exc || '')
}

export function readableError(err) {
  return serverMessage(err) || 'Something went wrong. Please try again.'
}

export function getErrorPresentation(err) {
  const value = errorValue(err)
  const message = readableError(value)
  const haystack = `${message} ${value?.exc_type || ''} ${value?.status || ''}`.toLowerCase()

  if (/not whitelisted|whitelist|method not found|deployment|service unavailable/.test(haystack)) {
    return {
      kind: 'configuration',
      title: 'Finance service is not available',
      message: 'The Finance API is not available in this deployment.',
      nextStep: 'Ask an administrator to reload the Finance app services and verify the deployed revision.',
      retryable: false,
      reference: value?.request_id || value?.exc_type || '',
    }
  }
  if (/permission|not permitted|unauthori[sz]ed|forbidden|access denied|role required/.test(haystack)) {
    return {
      kind: 'permission',
      title: 'You do not have Finance access',
      message: 'Finance Workspace requires the Accounts User or Accounts Manager role.',
      nextStep: 'Ask your administrator to assign the required native ERPNext role.',
      retryable: false,
      reference: value?.request_id || '',
    }
  }
  if (/mandatory|missing|required|invalid|validation|cannot be empty/.test(haystack)) {
    return {
      kind: 'validation',
      title: 'Review the required fields',
      message,
      nextStep: 'Correct the highlighted fields and submit again.',
      retryable: false,
      reference: value?.request_id || '',
    }
  }
  if (/already exists|duplicate|already generated|idempot/.test(haystack)) {
    return {
      kind: 'duplicate',
      title: 'This operation already exists',
      message,
      nextStep: 'Open the existing native document and continue from there.',
      retryable: false,
      reference: value?.request_id || '',
    }
  }
  if (/closed period|fiscal period|period is closed|posting date/.test(haystack)) {
    return {
      kind: 'period',
      title: 'The accounting period is closed',
      message,
      nextStep: 'Choose an allowed posting date or ask an Accounts Manager to review the period.',
      retryable: false,
      reference: value?.request_id || '',
    }
  }
  if (/timeout|timed out|network|fetch failed|502|503|504|temporar/.test(haystack)) {
    return {
      kind: 'transient',
      title: 'Finance service could not be reached',
      message,
      nextStep: 'Check the connection and retry when the service is available.',
      retryable: true,
      reference: value?.request_id || '',
    }
  }
  return {
    kind: 'unknown',
    title: 'Finance operation could not be completed',
    message,
    nextStep: 'Review the source document and try again. Contact Finance support if the problem persists.',
    retryable: true,
    reference: value?.request_id || '',
  }
}
