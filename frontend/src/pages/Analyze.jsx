import { useState } from 'react'
import { api } from '../api.js'
import { Card, Kv, Badge, SeriousBadge, Spinner, Banner } from '../components/ui.jsx'

export default function Analyze({ status }) {
  const [narrative, setNarrative] = useState('')
  const [caseId, setCaseId] = useState('PV-2026-00125')
  const [reportDate, setReportDate] = useState('06-Jun-2026')
  const [file, setFile] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)

  const sample = 'A 45-year-old female experienced severe skin rash and fever after taking ' +
    'Amoxicillin 500 mg orally for a bacterial infection. She was hospitalized and the drug was discontinued.'

  async function analyze() {
    setLoading(true); setError(''); setResult(null)
    try {
      const res = file
        ? await api.analyzeUpload(file, caseId, reportDate)
        : await api.analyze(narrative, caseId, reportDate)
      setResult(res)
    } catch (e) { setError(String(e)) } finally { setLoading(false) }
  }

  const a = result?.analysis, e = result?.entities

  return (
    <div className="page">
      <section className="hero">
        <div className="grid-bg" /><div className="glow" />
        <div className="hero-inner">
          <span className="eyebrow">✦ Pharmacovigilance AI Copilot</span>
          <h1>Turn an adverse-event narrative<br />into a structured safety report.</h1>
          <p>Extract safety entities, retrieve similar FAERS cases with semantic search,
             and generate an AI seriousness &amp; causality assessment — in seconds.</p>
          <div className="pills">
            <span className="pill">FDA FAERS 2026Q1</span>
            <span className="pill">RAG · 397K cases</span>
            <span className="pill">{status?.llm_available ? status.llm_model : 'rule-based'}</span>
            <span className="pill">ICH E2A</span>
          </div>
        </div>
      </section>

      <Card title="Case input" right={
        <button className="link" onClick={() => setNarrative(sample)}>Use sample</button>
      }>
        <label>Adverse event narrative</label>
        <textarea rows={6} value={narrative} onChange={(ev) => setNarrative(ev.target.value)}
          placeholder="Describe the patient, drug, dose, reaction, and outcome…" />
        <div className="row">
          <div>
            <label>Or upload (TXT/PDF/DOCX)</label>
            <input type="file" accept=".txt,.pdf,.docx"
              onChange={(ev) => setFile(ev.target.files?.[0] || null)} />
          </div>
          <div><label>Case ID</label>
            <input value={caseId} onChange={(ev) => setCaseId(ev.target.value)} /></div>
          <div><label>Report Date</label>
            <input value={reportDate} onChange={(ev) => setReportDate(ev.target.value)} /></div>
        </div>
        <button className="primary" disabled={loading || (!narrative.trim() && !file)} onClick={analyze}>
          {loading ? 'Analyzing…' : '🔬 Analyze Case'}
        </button>
        {loading && <Spinner label="Extracting · retrieving · analyzing…" />}
        {error && <Banner kind="error">{error}</Banner>}
      </Card>

      {result && (
        <>
          <div className="stat-row">
            <div className="stat"><span>Seriousness</span><SeriousBadge value={a.seriousness} /></div>
            <div className="stat"><span>Causality</span><Badge kind="blue">{a.causality}</Badge></div>
            <div className="stat"><span>Confidence</span><b>{Number(a.confidence_score).toFixed(2)}</b></div>
            <div className="stat"><span>Similar cases</span><b>{result.retrieved.length}</b></div>
            <div className="stat"><span>Engine</span><b>{a.analysis_source}</b></div>
          </div>

          <div className="cols">
            <Card title="Extracted entities">
              <div className="grid">
                <Kv k="Drug" v={e.drug} /><Kv k="Age" v={e.age} />
                <Kv k="Gender" v={e.gender} /><Kv k="Weight" v={e.weight} />
                <Kv k="Dosage" v={e.dosage} /><Kv k="Route" v={e.route} />
              </div>
              <p><b>All reported drugs:</b> {(e.all_drugs || []).join(', ') || e.drug || '—'}</p>
              <p><b>Adverse events:</b> {(e.adverse_events || []).join(', ') || '—'}</p>
              <p><b>Indication:</b> {e.indication || '—'}</p>
            </Card>

            <Card title="AI analysis">
              <p>{a.summary}</p>
              <p className="muted"><b>Rationale:</b> {a.seriousness_rationale}</p>
              <b>Medical insights</b>
              <ul>{(a.medical_insights || []).map((x, i) => <li key={i}>{x}</li>)}</ul>
              <b>Safety observations</b>
              <ul>{(a.safety_observations || []).map((x, i) => <li key={i}>{x}</li>)}</ul>
            </Card>
          </div>

          <Card title={`Similar historical FAERS cases (${result.retrieved.length})`}>
            {result.retrieved.map((c, i) => (
              <details key={i}>
                <summary>
                  <span>id {c.primaryid}</span>
                  <Badge kind="gray">sim {Number(c.similarity).toFixed(2)}</Badge>
                  {c.seriousness && <Badge kind={c.seriousness === 'Serious' ? 'red' : 'green'}>{c.seriousness}</Badge>}
                </summary>
                <p>{c.narrative}</p>
              </details>
            ))}
          </Card>

          <Card title="Structured report">
            <div className="final">{result.report.final_classification}</div>
            {result.id ? (
              <div className="downloads">
                <a href={api.reportUrl(result.id, 'pdf')}>📄 PDF</a>
                <a href={api.reportUrl(result.id, 'xlsx')}>📊 Excel</a>
                <a href={api.reportUrl(result.id, 'json')}>🧾 JSON</a>
              </div>
            ) : <Banner kind="warn">Saving failed — downloads unavailable.</Banner>}
          </Card>
        </>
      )}
    </div>
  )
}
