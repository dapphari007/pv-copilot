import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { Card, SeriousBadge, Spinner, Empty, Banner } from '../components/ui.jsx'
import ReportView from '../components/ReportView.jsx'

export default function History() {
  const [rows, setRows] = useState(null)
  const [search, setSearch] = useState('')
  const [openId, setOpenId] = useState(null)
  const [detail, setDetail] = useState(null)
  const [error, setError] = useState('')

  function load(q = '') { api.history(q).then(setRows).catch((e) => setError(String(e))) }
  useEffect(() => { load() }, [])

  function open(id) {
    setOpenId(id); setDetail(null)
    api.getCase(id).then(setDetail).catch((e) => setError(String(e)))
  }

  if (error) return <div className="page"><Banner kind="error">{error}</Banner></div>
  if (!rows) return <div className="page"><Spinner label="Loading history…" /></div>

  return (
    <div className="page">
      <div className="page-head">
        <h2>Case History</h2>
        <p>All processed patient cases. Search by Case ID, Patient ID, or drug.</p>
      </div>

      <Card>
        <div className="viewer-bar">
          <input style={{ maxWidth: 360 }} placeholder="Search Case ID / Patient ID / drug…"
            value={search} onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && load(search)} />
          <button className="chip" onClick={() => load(search)}>Search</button>
        </div>
        {rows.length === 0 ? (
          <Empty icon="🗂️">No cases yet — process a document on the Upload page.</Empty>
        ) : (
          <table className="table">
            <thead><tr>
              <th>Case ID</th><th>Patient ID</th><th>Date</th><th>Seriousness</th>
              <th>Suspected Drug</th><th>Outcome</th><th></th>
            </tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className={openId === r.id ? 'sel' : ''}>
                  <td>{r.case_id}</td><td>{r.patient_id || '—'}</td>
                  <td className="mono">{r.created_at?.replace('T', ' ').slice(0, 16)}</td>
                  <td><SeriousBadge value={r.seriousness} /></td>
                  <td>{r.suspected_drug || '—'}</td><td>{r.outcome || '—'}</td>
                  <td><button className="link" onClick={() => open(r.id)}>Open</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      {openId && (detail ? <ReportView report={detail.report} id={detail.id} />
        : <Spinner label="Loading report…" />)}
    </div>
  )
}
