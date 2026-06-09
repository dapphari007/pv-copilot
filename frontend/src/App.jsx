import { useEffect, useState } from 'react'
import { api, getToken, setToken } from './api.js'
import Upload from './pages/Upload.jsx'
import History from './pages/History.jsx'
import Login from './components/Login.jsx'
import { Badge } from './components/ui.jsx'
import { IconAnalyze, IconHistory, IconSun, IconMoon } from './components/icons.jsx'

const NAV = [
  { key: 'upload', label: 'Upload & Analyze', Icon: IconAnalyze },
  { key: 'history', label: 'History', Icon: IconHistory },
]
const ROLE_LABEL = { admin: 'Admin', pv_associate: 'PV Associate', viewer: 'Viewer' }

export default function App() {
  const [page, setPage] = useState('upload')
  const [user, setUser] = useState(null)
  const [ready, setReady] = useState(false)
  const [theme, setTheme] = useState(() => localStorage.getItem('pv-theme') || 'light')

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('pv-theme', theme)
  }, [theme])

  useEffect(() => {
    // OAuth callback: ?token=... -> store and clean the URL
    const params = new URLSearchParams(window.location.search)
    const t = params.get('token')
    if (t) { setToken(t); window.history.replaceState({}, '', window.location.pathname) }
    if (getToken()) {
      api.me().then(setUser).catch(() => setToken('')).finally(() => setReady(true))
    } else { setReady(true) }
  }, [])

  function logout() { api.logout().catch(() => {}); setToken(''); setUser(null) }

  if (!ready) return null
  if (!user) return <Login onLogin={setUser} />

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
            <span className="status-pill">{user.name || user.sub}
              <Badge kind="blue">{ROLE_LABEL[user.role] || user.role}</Badge></span>
            <button className="theme-toggle" title="Toggle theme"
              onClick={() => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))}>
              {theme === 'dark' ? <IconSun width={17} height={17} /> : <IconMoon width={17} height={17} />}
            </button>
            <button className="chip" onClick={logout} style={{ margin: 0 }}>Logout</button>
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
