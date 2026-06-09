import { api } from '../api.js'
import { Card, Badge, SeriousBadge } from './ui.jsx'

function KvGrid({ data }) {
  return (
    <div className="grid">
      {Object.entries(data).map(([k, v]) => (
        <div className="kv" key={k}><span>{k}</span><b>{String(v ?? '—') || '—'}</b></div>
      ))}
    </div>
  )
}

export default function ReportView({ report, id }) {
  if (!report) return null
  const serious = report.case_information?.Seriousness === 'Serious'
  const sa = report.seriousness_assessment || {}
  const ca = report.causality_assessment || {}

  return (
    <div>
      <div className="stat-row">
        <div className="stat"><span>Case ID</span><b>{report.case_information?.['Case ID']}</b></div>
        <div className="stat"><span>Patient ID</span><b>{report.case_information?.['Patient ID'] || '—'}</b></div>
        <div className="stat"><span>Seriousness</span><SeriousBadge value={report.case_information?.Seriousness} /></div>
        <div className="stat"><span>Causality</span><Badge kind="blue">{ca.Assessment || '—'}</Badge></div>
        <div className="stat"><span>Confidence</span><b>{Number(ca['Confidence Score'] || 0).toFixed(2)}</b></div>
      </div>

      <div className="cols">
        <Card title="Patient Information">
          <KvGrid data={report.patient_information || {}} />
          <p><b>Medical history:</b> {(report.medical_history || []).join(', ') || 'None reported'}</p>
        </Card>
        <Card title="Suspected Drug (Primary Suspect)">
          <KvGrid data={report.suspected_drug || {}} />
        </Card>
      </div>

      <Card title={`All Drug Information (${(report.all_drugs || []).length})`}>
        <table className="table">
          <thead><tr><th>Drug Name</th><th>Dose</th><th>Route</th><th>Role</th></tr></thead>
          <tbody>
            {(report.all_drugs || []).map((d, i) => (
              <tr key={i}>
                <td><b>{d['Drug Name']}</b></td><td>{d.Dose}</td>
                <td>{d.Route}</td><td><Badge kind={d.Role?.includes('Primary') ? 'red' : 'gray'}>{d.Role}</Badge></td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Card title="Adverse Event Details"><KvGrid data={report.adverse_event || {}} /></Card>

      <Card title="AI Narrative Summary">
        <p style={{ lineHeight: 1.7 }}>{report.ai_narrative_summary || '—'}</p>
      </Card>

      <div className="cols">
        <Card title="Seriousness Assessment">
          <div className="badges">
            {['Death', 'Life Threatening', 'Hospitalization', 'Disability', 'Congenital Anomaly', 'Medically Important']
              .map((k) => <Badge key={k} kind={sa[k] === 'Yes' ? 'red' : 'gray'}>{k}: {sa[k] || 'No'}</Badge>)}
          </div>
          <p className="muted">{sa.Rationale}</p>
        </Card>
        <Card title="Causality Assessment">
          <p><b>{ca.Assessment}</b> (confidence {Number(ca['Confidence Score'] || 0).toFixed(2)})</p>
          <p className="muted">{ca.Justification}</p>
        </Card>
      </div>

      <Card title="AI Safety Insights">
        <ul>{(report.ai_safety_insights || []).map((x, i) => <li key={i}>{x}</li>)}</ul>
      </Card>

      <Card title={`Similar Historical Cases (${(report.similar_cases || []).length})`}>
        {(report.similar_cases || []).map((c, i) => (
          <details key={i}>
            <summary>
              <span>id {c.case_id}</span>
              <Badge kind="gray">sim {Number(c.similarity).toFixed(2)}</Badge>
              {c.drug_match && <Badge kind="green">drug match</Badge>}
              {(c.reaction_match || []).length > 0 && <Badge kind="blue">reaction match</Badge>}
            </summary>
            <p>{c.snippet}</p>
          </details>
        ))}
      </Card>

      <Card title="Downloads">
        <div className="final">{report.final_classification}</div>
        {id && (
          <div className="downloads">
            <a href={api.reportUrl(id, 'pdf')}>📄 PDF</a>
            <a href={api.reportUrl(id, 'xlsx')}>📊 Excel</a>
            <a href={api.reportUrl(id, 'json')}>🧾 JSON</a>
          </div>
        )}
      </Card>
    </div>
  )
}
