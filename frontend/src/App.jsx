import { useEffect, useState } from 'react'
import { api } from './api.js'

export default function App() {
  const [status, setStatus] = useState(null)
  const [narrative, setNarrative] = useState('')
  const [caseId, setCaseId] = useState('PV-2026-00125')
  const [reportDate, setReportDate] = useState('06-Jun-2026')
  const [file, setFile] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)

  useEffect(() => {
    api.status().then(setStatus).catch((e) => setError(String(e)))
  }, [])

  async function analyze() {
    setLoading(true); setError(''); setResult(null)
    try {
      const res = file
        ? await api.analyzeUpload(file, caseId, reportDate)
        : await api.analyze(narrative, caseId, reportDate)
      setResult(res)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }

  const a = result?.analysis
  const e = result?.entities
  const serious = a?.seriousness === 'Serious'

  return (
    <div className="wrap">
      <header className="hero">
        <h1>💊 Pharmacovigilance AI Copilot</h1>
        <p>React UI · extract safety entities, retrieve similar FAERS cases, and
           generate an AI adverse-event report.</p>
        {status && (
          <div className="pills">
            <span className="pill">LLM: {status.llm_available ? status.llm_model : 'fallback'}</span>
            <span className="pill">Backend: {status.settings?.vector_backend}</span>
            <span className="pill">Model: {status.settings?.embedding_model}</span>
            <span className="pill">Engine: {status.settings?.rag_engine}</span>
            <span className="pill">Cases: {status.case_count}</span>
          </div>
        )}
      </header>

      <section className="card">
        <label>Adverse event narrative</label>
        <textarea rows={6} value={narrative} onChange={(ev) => setNarrative(ev.target.value)}
          placeholder="e.g. A 45-year-old female experienced severe skin rash and fever after taking Amoxicillin 500 mg orally..." />
        <div className="row">
          <div>
            <label>Or upload (TXT/PDF/DOCX)</label>
            <input type="file" accept=".txt,.pdf,.docx"
              onChange={(ev) => setFile(ev.target.files?.[0] || null)} />
          </div>
          <div>
            <label>Case ID</label>
            <input value={caseId} onChange={(ev) => setCaseId(ev.target.value)} />
          </div>
          <div>
            <label>Report Date</label>
            <input value={reportDate} onChange={(ev) => setReportDate(ev.target.value)} />
          </div>
        </div>
        <button className="primary" disabled={loading || (!narrative.trim() && !file)} onClick={analyze}>
          {loading ? 'Analyzing…' : '🔬 Analyze Case'}
        </button>
        {error && <div className="error">{error}</div>}
      </section>

      {result && (
        <section className="results">
          <div className="card">
            <h3>Extracted entities</h3>
            <div className="grid">
              <Kv k="Drug" v={e.drug} />
              <Kv k="Age" v={e.age} />
              <Kv k="Gender" v={e.gender} />
              <Kv k="Weight" v={e.weight} />
            </div>
            <p><b>Adverse events:</b> {(e.adverse_events || []).join(', ') || '—'}</p>
          </div>

          <div className="card">
            <h3>AI analysis</h3>
            <div className="badges">
              <span className={serious ? 'badge red' : 'badge green'}>
                Seriousness: {a.seriousness}
              </span>
              <span className="badge blue">Causality: {a.causality}</span>
              <span className="badge gray">Confidence: {Number(a.confidence_score).toFixed(2)}</span>
            </div>
            <p>{a.summary}</p>
            <b>Medical insights</b>
            <ul>{(a.medical_insights || []).map((x, i) => <li key={i}>{x}</li>)}</ul>
            <b>Safety observations</b>
            <ul>{(a.safety_observations || []).map((x, i) => <li key={i}>{x}</li>)}</ul>
            <small>Engine: {a.analysis_source} · Retrieved: {a.retrieved_case_count}</small>
          </div>

          <div className="card">
            <h3>Similar FAERS cases ({result.retrieved.length})</h3>
            {result.retrieved.map((c, i) => (
              <details key={i}>
                <summary>id {c.primaryid} · similarity {Number(c.similarity).toFixed(2)}</summary>
                <p>{c.narrative}</p>
              </details>
            ))}
          </div>

          <div className="card">
            <h3>Download report</h3>
            <p className="final">{result.report.final_classification}</p>
            {result.id ? (
              <div className="downloads">
                <a href={api.reportUrl(result.id, 'pdf')}>📄 PDF</a>
                <a href={api.reportUrl(result.id, 'xlsx')}>📊 Excel</a>
                <a href={api.reportUrl(result.id, 'json')}>🧾 JSON</a>
              </div>
            ) : <small>Saving failed — downloads unavailable.</small>}
          </div>
        </section>
      )}
    </div>
  )
}

function Kv({ k, v }) {
  return <div className="kv"><span>{k}</span><b>{v || '—'}</b></div>
}
