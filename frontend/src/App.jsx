import { useEffect, useState } from 'react'
import { api } from './api.js'
import Upload from './pages/Upload.jsx'
import History from './pages/History.jsx'
import { IconAnalyze, IconHistory, IconSun, IconMoon } from './components/icons.jsx'

const NAV = [
  { key: 'upload', label: 'Upload & Analyze', Icon: IconAnalyze },
  { key: 'history', label: 'History', Icon: IconHistory },
]

export default function App() {
  const [page, setPage] = useState('upload')
  const [status, setStatus] = useState(null)
  const [theme, setTheme] = useState(() => localStorage.getItem('pv-theme') || 'light')

  useEffect(() => { api.status().then(setStatus).catch(() => setStatus(null)) }, [])
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('pv-theme', theme)
  }, [theme])

  return (
    <>
      <div className="nav-wrap">
        <nav className="navbar">
          <div className="brand"><span className="mark">💊</span>PV<b>Copilot</b></div>
          <div className="nav-tabs">
            {NAV.map(({ key, label, Icon }) => (
              <button key={key} className={`nav-tab ${page === key ? 'active' : ''}`}
                onClick={() => setPage(key)}><Icon /><span>{label}</span></button>
            ))}
          </div>
          <div className="nav-right">
            <span className="status-pill">
              <span className={`dotc ${status ? 'up' : 'down'}`} />
              {status ? (status.llm_available ? 'Groq' : 'fallback') : 'offline'}
            </span>
            <button className="theme-toggle" title="Toggle theme"
              onClick={() => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))}>
              {theme === 'dark' ? <IconSun width={17} height={17} /> : <IconMoon width={17} height={17} />}
            </button>
          </div>
        </nav>
      </div>

      <main className="content">
        {page === 'upload' && <Upload />}
        {page === 'history' && <History />}
      </main>
    </>
  )
}
