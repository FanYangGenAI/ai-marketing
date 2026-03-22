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
