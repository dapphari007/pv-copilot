// Client for the rebuilt multi-patient PV API (proxied at /api in dev).
const BASE = '/api'

async function jget(path) {
  const res = await fetch(BASE + path)
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`)
  return res.json()
}
async function jpost(path, body) {
  const res = await fetch(BASE + path, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`)
  return res.json()
}

export const api = {
  status: () => jget('/status'),
  analyzeText: (text, reportDate = '') => jpost('/analyze-text', { text, report_date: reportDate }),
  upload: async (files, reportDate = '') => {
    const form = new FormData()
    for (const f of files) form.append('files', f)
    const res = await fetch(`${BASE}/upload?report_date=${encodeURIComponent(reportDate)}`,
      { method: 'POST', body: form })
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
