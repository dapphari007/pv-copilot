// Client for the rebuilt multi-patient PV API (proxied at /api in dev).
const BASE = '/api'

export function getToken() { return localStorage.getItem('pv-token') || '' }
export function setToken(t) { t ? localStorage.setItem('pv-token', t) : localStorage.removeItem('pv-token') }

function authHeaders(extra = {}) {
  const t = getToken()
  return t ? { ...extra, Authorization: `Bearer ${t}` } : extra
}

async function jget(path) {
  const res = await fetch(BASE + path, { headers: authHeaders() })
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`)
  return res.json()
}
async function jpost(path, body) {
  const res = await fetch(BASE + path, {
    method: 'POST', headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`)
  return res.json()
}

export const api = {
  // auth
  providers: () => jget('/auth/providers'),
  login: (email, name, role) => jpost('/auth/login', { email, name, role }),
  me: () => jget('/auth/me'),
  logout: () => jpost('/auth/logout', {}),
  oauthUrl: (provider) => `${BASE}/auth/${provider}/login`,
  users: () => jget('/auth/users'),
  setRole: (email, role) => jpost('/auth/users/role', { email, role }),
  // pipeline
  status: () => jget('/status'),
  analyzeText: (text, reportDate = '') => jpost('/analyze-text', { text, report_date: reportDate }),
  upload: async (files, reportDate = '') => {
    const form = new FormData()
    for (const f of files) form.append('files', f)
    const res = await fetch(`${BASE}/upload?report_date=${encodeURIComponent(reportDate)}`,
      { method: 'POST', headers: authHeaders(), body: form })
    if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`)
    return res.json()
  },
  dashboard: (uploadId) => jget(`/dashboard/${uploadId}`),
  cases: (uploadId, seriousness, search) => {
    const q = new URLSearchParams()
    if (uploadId) q.set('upload_id', uploadId)
    if (seriousness) q.set('seriousness', seriousness)
    if (search) q.set('search', search)
    return jget(`/cases?${q}`)
  },
  history: (search) => jget(`/history${search ? `?search=${encodeURIComponent(search)}` : ''}`),
  getCase: (id) => jget(`/cases/${id}`),
  reportUrl: (id, fmt) => `${BASE}/cases/${id}/report.${fmt}`,
  zipUrl: (uploadId) => `${BASE}/uploads/${uploadId}/reports.zip`,
}
