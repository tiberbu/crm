/** Pure display helpers for the opt-in "Optional services and hardware" list. */

const NAMED_ENTITIES = {
  amp: '&',
  lt: '<',
  gt: '>',
  quot: '"',
  apos: "'",
  nbsp: ' ',
  ndash: '–',
  mdash: '—',
}

/** Decode HTML entities (named subset + numeric) into plain characters. */
export function decodeEntities(value) {
  return String(value ?? '').replace(
    /&(#x[0-9a-f]+|#\d+|[a-z]+);/gi,
    (match, code) => {
      if (code[0] === '#') {
        const n =
          code[1].toLowerCase() === 'x'
            ? parseInt(code.slice(2), 16)
            : parseInt(code.slice(1), 10)
        return Number.isFinite(n) && n > 0 && n <= 0x10ffff
          ? String.fromCodePoint(n)
          : match
      }
      return NAMED_ENTITIES[code.toLowerCase()] ?? match
    },
  )
}

/**
 * Item Text Editor HTML → one line of plain text. Block tags and <br> become
 * spaces, other tags are dropped, entities are decoded and whitespace collapsed.
 * The result is rendered as text (never v-html), so it cannot inject markup.
 */
export function htmlToText(value) {
  const withoutTags = String(value ?? '')
    .replace(/<(br|\/p|\/div|\/li|\/h[1-6])\s*\/?>/gi, ' ')
    .replace(/<[^>]*>/g, '')
  return decodeEntities(withoutTags).replace(/\s+/g, ' ').trim()
}

/** The row shown for one optional service: plain label, and a detail only when it adds something. */
export function optionalServiceDisplay(item) {
  const label = htmlToText(item?.item_name) || String(item?.item_code ?? '')
  const description = htmlToText(item?.description)
  const detail =
    description && description.toLowerCase() !== label.toLowerCase()
      ? description
      : ''
  return { ...item, label, detail }
}
