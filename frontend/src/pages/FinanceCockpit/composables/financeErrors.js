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
  const message = serverMessage(err)
  if (!message) return 'Finance could not complete this request.'
  if (/not whitelisted|whitelist|method not found|crm\.finance\.api|frappe|erpnext/i.test(message)) {
    return 'This Finance action is not available yet. Ask an administrator to finish the Finance Workspace deployment.'
  }
  if (/attributeerror|typeerror|traceback|has no attribute|unexpected keyword/i.test(message)) {
    return 'The request used an unsupported format. Refresh the page and try again.'
  }
  return message
}

export function getErrorPresentation(err) {
  const value = errorValue(err)
  const serverText = serverMessage(value)
  const message = readableError(value)
  const haystack = `${serverText} ${value?.exc_type || ''} ${value?.status || ''}`.toLowerCase()

  if (/not whitelisted|whitelist|method not found|deployment|service unavailable/.test(haystack)) {
    return {
      kind: 'configuration',
      title: 'Finance service is not available',
      message: 'This Finance action is not available yet.',
      nextStep: 'Ask an administrator to finish the Finance Workspace deployment, then refresh this page.',
      retryable: false,
      reference: value?.request_id || value?.exc_type || '',
    }
  }
  if (/permission|not permitted|unauthori[sz]ed|forbidden|access denied|role required/.test(haystack)) {
    return {
      kind: 'permission',
      title: 'You do not have Finance access',
      message: 'Finance Workspace requires the Accounts User or Accounts Manager role.',
      nextStep: 'Ask your administrator to assign Accounts User or Accounts Manager access, then sign in again.',
      retryable: false,
      reference: value?.request_id || '',
    }
  }
  if (/attributeerror|typeerror|traceback|has no attribute|unexpected keyword/.test(haystack)) {
    return {
      kind: 'request',
      title: 'The request could not be understood',
      message: 'Some information sent by the page was in an unsupported format.',
      nextStep: 'Refresh the page and try again. If it continues, contact Finance support and include the reference below.',
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
      message: 'A matching record already exists, so nothing new was created.',
      nextStep: 'Open the existing record and continue from there.',
      retryable: false,
      reference: value?.request_id || '',
    }
  }
  if (/closed period|fiscal period|period is closed|posting date/.test(haystack)) {
    return {
      kind: 'period',
      title: 'The accounting period is closed',
      message: 'The selected posting date is not available for accounting entries.',
      nextStep: 'Choose an allowed posting date or ask an Accounts Manager to review the period.',
      retryable: false,
      reference: value?.request_id || '',
    }
  }
  if (/timeout|timed out|network|fetch failed|502|503|504|temporar/.test(haystack)) {
    return {
      kind: 'transient',
      title: 'Finance is temporarily unavailable',
      message: 'The request did not reach Finance successfully.',
      nextStep: 'Check your connection and try again in a moment.',
      retryable: true,
      reference: value?.request_id || '',
    }
  }
  return {
    kind: 'unknown',
    title: 'Finance could not complete this request',
    message,
    nextStep: 'Review the record, then try again. Contact Finance support if the problem continues.',
    retryable: true,
    reference: value?.request_id || '',
  }
}
