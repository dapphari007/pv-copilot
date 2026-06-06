import { useEffect, useState } from 'react'
import { api } from './api.js'
import Analyze from './pages/Analyze.jsx'
import History from './pages/History.jsx'
import Settings from './pages/Settings.jsx'

const NAV = [
  { key: 'analyze', label: 'Analyze', icon: '🔬' },
  { key: 'history', label: 'History', icon: '🗂️' },
  { key: 'settings', label: 'Settings', icon: '⚙️' },
]

export default function App() {
  const [page, setPage] = useState('analyze')
  const [status, setStatus] = useState(null)

  function refreshStatus() { api.status().then(setStatus).catch(() => {}) }
  useEffect(() => { refreshStatus() }, [])

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="logo">💊</div>
          <div>
            <div className="brand-title">PV Copilot</div>
            <div className="brand-sub">Pharmacovigilance AI</div>
          </div>
        </div>

        <nav>
          {NAV.map((n) => (
            <button key={n.key} className={`nav ${page === n.key ? 'active' : ''}`}
              onClick={() => setPage(n.key)}>
              <span className="nav-ic">{n.icon}</span>{n.label}
            </button>
          ))}
        </nav>

        <div className="side-status">
          <div className={`dotc ${status ? 'up' : 'down'}`} />
          {status ? 'API connected' : 'API offline'}
          {status && (
            <ul>
              <li>LLM · <b>{status.llm_available ? 'Groq' : 'fallback'}</b></li>
              <li>DB · <b>{status.settings?.vector_backend}</b></li>
              <li>Model · <b>{status.settings?.embedding_model}</b></li>
              <li>Engine · <b>{status.settings?.rag_engine}</b></li>
              <li>Cases · <b>{status.case_count}</b></li>
            </ul>
          )}
        </div>
        <div className="side-foot">FDA FAERS 2026Q1 · decision-support only</div>
      </aside>

      <main className="content">
        <header className="topbar">
          <h1>{NAV.find((n) => n.key === page)?.label}</h1>
          <div className="topbar-pills">
            {status && <>
              <span className="pill">{status.llm_model}</span>
              <span className="pill">{status.settings?.vector_backend} · {status.settings?.embedding_model}</span>
            </>}
          </div>
        </header>

        {page === 'analyze' && <Analyze status={status} />}
        {page === 'history' && <History />}
        {page === 'settings' && <Settings status={status} onSaved={refreshStatus} />}
      </main>
    </div>
  )
}
