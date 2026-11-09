// A standalone copy of the Terms the user is accepting, built from the snapshot the session
// hashed, so the saved file is exactly what was agreed. The CSP blocks scripts and remote loads
// when the file is opened from disk.
const CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src data:"

function escapeHtml(value) {
  return String(value ?? '').replace(
    /[&<>"']/g,
    (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[ch],
  )
}

export function termsFileName(documentName) {
  const slug = String(documentName || 'terms-and-conditions')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
  return `${slug || 'terms-and-conditions'}.html`
}

export function termsDocument(snapshot, savedOn) {
  const title = escapeHtml(snapshot?.document || 'Terms and Conditions')
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="${CSP}">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${title}</title>
<style>
body { font: 15px/1.6 system-ui, sans-serif; color: #1f2933; max-width: 760px; margin: 40px auto; padding: 0 20px; }
header { border-bottom: 1px solid #d9dde3; margin-bottom: 24px; padding-bottom: 12px; }
header p { color: #5f6b7a; font-size: 12px; margin: 4px 0 0; word-break: break-all; }
@media print { body { margin: 0; } }
</style>
</head>
<body>
<header>
<h1>${title}</h1>
<p>Saved ${escapeHtml(savedOn)} during facility onboarding.</p>
<p>Reference: ${escapeHtml(snapshot?.content_hash)}</p>
</header>
<main>
${snapshot?.rendered_html || ''}
</main>
</body>
</html>
`
}
