import { useEffect, useState } from 'react'
import { api, setToken } from '../api.js'
import { Banner } from './ui.jsx'

const ROLES = [
  { v: 'admin', l: 'Admin' },
  { v: 'pv_associate', l: 'PV Associate' },
  { v: 'viewer', l: 'Viewer' },
]

export default function Login({ onLogin }) {
  const [providers, setProviders] = useState({ google: false, microsoft: false })
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [role, setRole] = useState('pv_associate')
  const [error, setError] = useState('')

  useEffect(() => { api.providers().then(setProviders).catch(() => {}) }, [])

  async function devLogin() {
    setError('')
    try {
      const { token, user } = await api.login(email.trim(), name.trim(), role)
      setToken(token)
      onLogin(user)
    } catch (e) { setError(String(e)) }
  }

  return (
    <div className="login-wrap">
      <div className="login-card">
        <div className="brand" style={{ justifyContent: 'center', marginBottom: '.4rem' }}>
          <span className="mark">💊</span>PV<b>Copilot</b>
        </div>
        <p className="muted" style={{ textAlign: 'center', marginTop: 0 }}>
          Sign in to the Pharmacovigilance AI Copilot
        </p>

        <div className="oauth-row">
          <a className={`oauth-btn ${providers.google ? '' : 'disabled'}`}
             href={providers.google ? api.oauthUrl('google') : undefined}>
            <span></span> Continue with Google
          </a>
          <a className={`oauth-btn ${providers.microsoft ? '' : 'disabled'}`}
             href={providers.microsoft ? api.oauthUrl('microsoft') : undefined}>
            <span>⊞</span> Continue with Microsoft
          </a>
        </div>
        {(!providers.google || !providers.microsoft) && (
          <p className="muted" style={{ fontSize: '.74rem', textAlign: 'center' }}>
            OAuth providers activate once their client id/secret are configured in <code>.env</code>.
          </p>
        )}

        <div className="divider"><span>or sign in directly</span></div>

        <label>Email</label>
        <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@org.com" />
        <label>Name</label>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Your name" />
        <label>Role</label>
        <div className="seg">
          {ROLES.map((r) => (
            <button key={r.v} className={role === r.v ? 'on' : ''} onClick={() => setRole(r.v)}>{r.l}</button>
          ))}
        </div>
        <button className="primary" style={{ width: '100%', justifyContent: 'center' }}
          disabled={!email.trim()} onClick={devLogin}>Sign in</button>
        {error && <Banner kind="error">{error}</Banner>}
      </div>
    </div>
  )
}
