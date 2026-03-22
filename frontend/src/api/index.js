/**
 * API client for AI Marketing backend.
 * All functions return parsed JSON (throws on error).
 */

async function apiFetch(url) {
  const res = await fetch(url)
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`API ${url} → ${res.status}: ${text}`)
  }
  return res.json()
}

async function apiPost(url, body = {}) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`API POST ${url} → ${res.status}: ${text}`)
  }
  return res.json()
}

export async function getProducts() {
  const data = await apiFetch('/api/products')
  return data.products || []
}

export async function getDates(product) {
  return apiFetch(`/api/products/${encodeURIComponent(product)}/dates`)
}

export async function getState(product, date) {
  return apiFetch(`/api/products/${encodeURIComponent(product)}/${date}/state`)
}

export async function getPackage(product, date) {
  return apiFetch(`/api/products/${encodeURIComponent(product)}/${date}/package`)
}

export async function getAudit(product, date) {
  return apiFetch(`/api/products/${encodeURIComponent(product)}/${date}/audit`)
}

export async function getFile(product, date, path) {
  return apiFetch(
    `/api/products/${encodeURIComponent(product)}/${date}/file?path=${encodeURIComponent(path)}`
  )
}

export async function getAssets(product) {
  return apiFetch(`/api/products/${encodeURIComponent(product)}/assets`)
}

export async function getMemory(product, platform) {
  return apiFetch(
    `/api/products/${encodeURIComponent(product)}/memory/${encodeURIComponent(platform)}`
  )
}

export async function getConfig(product) {
  return apiFetch(`/api/products/${encodeURIComponent(product)}/config`)
}

export async function getRunStatus(product) {
  return apiFetch(`/api/products/${encodeURIComponent(product)}/run/status`)
}

// ── 写操作 ────────────────────────────────────────────────────────────────────

export async function createProduct(name, userBrief = '') {
  return apiPost('/api/products', { name, user_brief: userBrief })
}

export async function listProductDocuments(product) {
  return apiFetch(`/api/products/${encodeURIComponent(product)}/documents`)
}

/**
 * Upload PRD file; backend writes to docs/ and sets product_config.json prd_path.
 * @param {File} file
 */
export async function uploadProductPrd(product, file) {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(
    `/api/products/${encodeURIComponent(product)}/documents/prd`,
    { method: 'POST', body: form }
  )
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`Upload PRD → ${res.status}: ${text}`)
  }
  return res.json()
}

/**
 * Upload reference files to docs/materials/.
 * @param {File[]} files
 */
export async function uploadProductAttachments(product, files) {
  if (!files.length) return { status: 'ok', paths: [] }
  const form = new FormData()
  for (const f of files) {
    form.append('files', f)
  }
  const res = await fetch(
    `/api/products/${encodeURIComponent(product)}/documents/attachments`,
    { method: 'POST', body: form }
  )
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`Upload attachments → ${res.status}: ${text}`)
  }
  return res.json()
}

export async function updateConfig(product, updates) {
  return apiPost(`/api/products/${encodeURIComponent(product)}/config`, updates)
}

export async function runPipeline(product, todayNote = '') {
  return apiPost(`/api/products/${encodeURIComponent(product)}/run`, { today_note: todayNote })
}

export async function submitFeedback(product, date, action, reason = '') {
  return apiPost(
    `/api/products/${encodeURIComponent(product)}/${date}/feedback`,
    { action, reason }
  )
}

/**
 * Build the URL to serve an image from the backend.
 * Handles both forward and backward slashes.
 */
export function imageUrl(path) {
  if (!path) return ''
  // Normalize backslashes
  const normalized = path.replace(/\\/g, '/')
  return `/api/images?path=${encodeURIComponent(normalized)}`
}
