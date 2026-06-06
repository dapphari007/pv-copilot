// Thin client for the FastAPI backend (proxied at /api in dev).
const BASE = '/api'

async function jsonFetch(path, options = {}) {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const detail = await res.text()
    throw new Error(`${res.status}: ${detail}`)
  }
  return res.json()
}

export const api = {
  status: () => jsonFetch('/status'),
  analyze: (narrative, caseId, reportDate) =>
    jsonFetch('/analyze', {
      method: 'POST',
      body: JSON.stringify({ narrative, case_id: caseId, report_date: reportDate }),
    }),
  analyzeUpload: async (file, caseId, reportDate) => {
    const form = new FormData()
    form.append('file', file)
    const qs = new URLSearchParams({ case_id: caseId, report_date: reportDate })
    const res = await fetch(`${BASE}/analyze/upload?${qs}`, { method: 'POST', body: form })
    if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`)
    return res.json()
  },
  history: () => jsonFetch('/history'),
  reportUrl: (rowId, fmt) => `${BASE}/cases/${rowId}/report.${fmt}`,
}
