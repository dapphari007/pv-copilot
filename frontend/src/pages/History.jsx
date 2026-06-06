import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { Card, Kv, SeriousBadge, Spinner, Empty, Banner } from '../components/ui.jsx'

export default function History() {
  const [rows, setRows] = useState(null)
  const [selected, setSelected] = useState(null)
  const [detail, setDetail] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => { refresh() }, [])
  function refresh() {
    api.history().then(setRows).catch((e) => setError(String(e)))
  }
  function open(id) {
    setSelected(id); setDetail(null)
    api.getCase(id).then(setDetail).catch((e) => setError(String(e)))
  }

  if (error) return <div className="page"><Banner kind="error">{error}</Banner></div>
  if (!rows) return <div className="page"><Spinner label="Loading history…" /></div>

  return (
    <div className="page">
      <div className="page-head">
        <h2>Case History</h2>
        <p>{rows.length} case(s) stored locally (SQLite). Click a row to review.</p>
      </div>

      {rows.length === 0 ? (
        <Empty icon="🗂️">No cases yet — analyze one to populate history.</Empty>
      ) : (
        <Card>
          <table className="table">
            <thead><tr>
              <th>When</th><th>Case ID</th><th>Drug</th><th>Seriousness</th>
              <th>Causality</th><th>Source</th><th>Backend</th><th></th>
            </tr></thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.id} className={selected === c.id ? 'sel' : ''}>
                  <td className="mono">{c.created_at?.replace('T', ' ').slice(0, 16)}</td>
                  <td>{c.case_id || '—'}</td>
                  <td>{c.drug || '—'}</td>
                  <td><SeriousBadge value={c.seriousness} /></td>
                  <td>{c.causality || '—'}</td>
                  <td>{c.source}</td>
                  <td className="mono">{c.vector_backend}/{c.embedding_model}</td>
                  <td><button className="link" onClick={() => open(c.id)}>Open</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {selected && (
        detail ? (
          <Card title={`Case ${detail.case_id || detail.id.slice(0, 8)}`} right={
            <div className="downloads sm">
              <a href={api.reportUrl(detail.id, 'pdf')}>PDF</a>
              <a href={api.reportUrl(detail.id, 'xlsx')}>Excel</a>
              <a href={api.reportUrl(detail.id, 'json')}>JSON</a>
            </div>
          }>
            <div className="grid">
              <Kv k="Seriousness" v={detail.analysis?.seriousness} />
              <Kv k="Causality" v={detail.analysis?.causality} />
              <Kv k="Confidence" v={Number(detail.analysis?.confidence_score || 0).toFixed(2)} />
              <Kv k="Source file" v={detail.file_name || 'manual'} />
            </div>
            <p className="muted"><b>Prompt:</b> {detail.prompt}</p>
            <p><b>AI summary:</b> {detail.report?.ai_narrative_summary}</p>
          </Card>
        ) : <Spinner label="Loading case…" />
      )}
    </div>
  )
}
