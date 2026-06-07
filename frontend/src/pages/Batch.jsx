import { useState } from 'react'
import { api } from '../api.js'
import { Card, SeriousBadge, Spinner, Banner } from '../components/ui.jsx'

function downloadBlob(blob, name) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = name; a.click()
  URL.revokeObjectURL(url)
}

export default function Batch() {
  const [files, setFiles] = useState([])
  const [text, setText] = useState('')
  const [reportDate, setReportDate] = useState('07-Jun-2026')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [results, setResults] = useState(null)

  async function run() {
    setLoading(true); setError(''); setResults(null)
    try {
      const out = []
      if (files.length) out.push(...(await api.analyzeBatch(files, reportDate)).results)
      const narratives = text.split('---').map((s) => s.trim()).filter(Boolean)
      if (narratives.length) out.push(...(await api.analyzeBatchText(narratives, reportDate)).results)
      if (!out.length) { setError('Add at least one file or one narrative.'); return }
      setResults(out)
    } catch (e) { setError(String(e)) } finally { setLoading(false) }
  }

  async function exportAll(fmt) {
    const ids = results.filter((r) => r.ok && r.id).map((r) => r.id)
    if (!ids.length) return
    downloadBlob(await api.batchExport(ids, fmt), `batch_reports.${fmt === 'zip' ? 'zip' : 'xlsx'}`)
  }

  const okCount = results?.filter((r) => r.ok).length || 0
  const seriousCount = results?.filter((r) => r.seriousness === 'Serious').length || 0

  return (
    <div className="page">
      <div className="page-head">
        <h2>Batch Analysis</h2>
        <p>Upload several case documents or paste multiple narratives — processed concurrently.</p>
      </div>

      <Card title="Batch input">
        <label>Upload case documents (TXT / PDF / DOCX) — multiple allowed</label>
        <input type="file" multiple accept=".txt,.pdf,.docx"
          onChange={(e) => setFiles([...e.target.files])} />
        {files.length > 0 && <p className="muted">{files.length} file(s) selected</p>}
        <label>...or paste multiple narratives (separate each case with a line of <code>---</code>)</label>
        <textarea rows={6} value={text} onChange={(e) => setText(e.target.value)}
          placeholder={'Case 1 narrative…\n---\nCase 2 narrative…\n---\nCase 3 narrative…'} />
        <label>Report date</label>
        <input value={reportDate} onChange={(e) => setReportDate(e.target.value)} />
        <button className="primary" disabled={loading || (!files.length && !text.trim())} onClick={run}>
          {loading ? 'Processing…' : '🗃️ Run Batch Analysis'}
        </button>
        {loading && <Spinner label="Analyzing cases concurrently…" />}
        {error && <Banner kind="error">{error}</Banner>}
      </Card>

      {results && (
        <>
          <div className="stat-row">
            <div className="stat"><span>Processed</span><b>{results.length}</b></div>
            <div className="stat"><span>Succeeded</span><b>{okCount}</b></div>
            <div className="stat"><span>Serious</span><b>{seriousCount}</b></div>
          </div>

          <Card title="Results" right={
            <div className="downloads sm">
              <a onClick={() => exportAll('zip')} style={{ cursor: 'pointer' }}>🗜️ All PDFs</a>
              <a onClick={() => exportAll('xlsx')} style={{ cursor: 'pointer' }}>📊 Summary</a>
            </div>
          }>
            <table className="table">
              <thead><tr>
                <th>Case ID</th><th>Source</th><th>Drug</th><th>All Drugs</th>
                <th>Seriousness</th><th>Causality</th><th>Status</th><th>PDF</th>
              </tr></thead>
              <tbody>
                {results.map((r, i) => (
                  <tr key={i}>
                    <td>{r.case_id || r.label}</td>
                    <td>{r.file_name || 'text'}</td>
                    <td>{r.drug || '—'}</td>
                    <td className="muted">{(r.all_drugs || []).join(', ') || '—'}</td>
                    <td>{r.ok ? <SeriousBadge value={r.seriousness} /> : '—'}</td>
                    <td>{r.causality || '—'}</td>
                    <td>{r.ok ? '✅' : <span style={{ color: 'var(--red)' }}>❌ {r.error}</span>}</td>
                    <td>{r.ok && r.id ? <a href={api.reportUrl(r.id, 'pdf')}>PDF</a> : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </>
      )}
    </div>
  )
}
