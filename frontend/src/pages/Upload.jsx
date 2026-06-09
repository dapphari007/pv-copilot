import { useMemo, useState } from 'react'
import { api } from '../api.js'
import { Card, Spinner, Banner } from '../components/ui.jsx'
import ReportView from '../components/ReportView.jsx'

const SAMPLE = `PATIENT INFORMATION
Patient ID: P-001
A 67-year-old male with hypertension and type 2 diabetes was treated with Metformin 1000 mg (primary suspect), Aspirin 75 mg and Atorvastatin 20 mg. He developed severe lactic acidosis and acute kidney injury and was hospitalized.

PATIENT INFORMATION
Patient ID: P-002
A 45-year-old female received Amoxicillin 500 mg for bacterial sinusitis and developed a severe skin rash and angioedema.`

export default function Upload() {
  const [files, setFiles] = useState([])
  const [text, setText] = useState('')
  const [reportDate, setReportDate] = useState('09-Jun-2026')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)
  const [filter, setFilter] = useState('all')   // all | Serious | Non-Serious
  const [idx, setIdx] = useState(0)

  async function run() {
    setLoading(true); setError(''); setResult(null); setFilter('all'); setIdx(0)
    try {
      const res = files.length
        ? await api.upload(files, reportDate)
        : await api.analyzeText(text, reportDate)
      setResult(res)
    } catch (e) { setError(String(e)) } finally { setLoading(false) }
  }

  const filtered = useMemo(() => {
    if (!result) return []
    if (filter === 'all') return result.cases
    return result.cases.filter((c) => c.seriousness === filter)
  }, [result, filter])

  function pick(f) { setFilter(f); setIdx(0) }
  const current = filtered[idx]

  return (
    <div className="page">
      <section className="hero">
        <div className="grid-bg" /><div className="glow" />
        <div className="hero-inner">
          <span className="eyebrow">✦ Pharmacovigilance AI Copilot</span>
          <h1>Process safety documents into<br />structured PV case reports.</h1>
          <p>Upload medical documents or paste narratives — the system detects every
             patient case, extracts drugs &amp; reactions, and generates regulatory reports.</p>
        </div>
      </section>

      <Card title="Upload / Analyze" right={
        <button className="link" onClick={() => setText(SAMPLE)}>Use sample (2 patients)</button>
      }>
        <label>Upload case documents (TXT / PDF / DOCX) — multiple allowed</label>
        <input type="file" multiple accept=".txt,.pdf,.docx"
          onChange={(e) => setFiles([...e.target.files])} />
        {files.length > 0 && <p className="muted">{files.length} file(s) selected</p>}
        <label>...or paste narrative(s)</label>
        <textarea rows={7} value={text} onChange={(e) => setText(e.target.value)}
          placeholder="Paste one or more patient narratives…" />
        <label>Report date</label>
        <input value={reportDate} onChange={(e) => setReportDate(e.target.value)} />
        <button className="primary" disabled={loading || (!files.length && !text.trim())} onClick={run}>
          {loading ? 'Processing…' : '🔬 Process Documents'}
        </button>
        {loading && <Spinner label="Detecting cases · extracting · retrieving · analyzing…" />}
        {error && <Banner kind="error">{error}</Banner>}
      </Card>

      {result && (
        <>
          <div className="stat-row">
            <div className="stat"><span>Documents</span><b>{result.documents_processed}</b></div>
            <div className="stat"><span>Cases Found</span><b>{result.cases_found}</b></div>
            <div className="stat"><span>Reports</span><b>{result.reports_generated}</b></div>
            <button className={`stat clickable ${filter === 'Serious' ? 'sel' : ''}`}
              onClick={() => pick('Serious')}>
              <span>Serious Cases</span><b style={{ color: 'var(--red)' }}>{result.serious_cases}</b></button>
            <button className={`stat clickable ${filter === 'Non-Serious' ? 'sel' : ''}`}
              onClick={() => pick('Non-Serious')}>
              <span>Non-Serious</span><b style={{ color: 'var(--green)' }}>{result.non_serious_cases}</b></button>
          </div>

          <div className="viewer-bar">
            <div>
              <button className={`chip ${filter === 'all' ? 'on' : ''}`} onClick={() => pick('all')}>All ({result.cases.length})</button>
              <button className={`chip ${filter === 'Serious' ? 'on' : ''}`} onClick={() => pick('Serious')}>Serious ({result.serious_cases})</button>
              <button className={`chip ${filter === 'Non-Serious' ? 'on' : ''}`} onClick={() => pick('Non-Serious')}>Non-Serious ({result.non_serious_cases})</button>
            </div>
            <a className="link" href={api.zipUrl(result.upload_id)}>⬇ Download All Reports (ZIP)</a>
          </div>

          {filtered.length === 0 ? (
            <Card><p className="muted">No {filter} cases in this upload.</p></Card>
          ) : (
            <>
              <div className="pager">
                <button className="chip" disabled={idx === 0} onClick={() => setIdx(idx - 1)}>← Previous</button>
                <b>Patient Report {idx + 1} of {filtered.length}</b>
                <button className="chip" disabled={idx >= filtered.length - 1} onClick={() => setIdx(idx + 1)}>Next →</button>
              </div>
              <ReportView report={current.report} id={current.id} />
            </>
          )}
        </>
      )}
    </div>
  )
}
