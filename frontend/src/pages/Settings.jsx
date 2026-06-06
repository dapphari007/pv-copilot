import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { Card, Spinner, Banner } from '../components/ui.jsx'

// Top-K is kept functional (sent on save) but hidden from the UI for simplicity.
// Flip to true to expose the slider again.
const SHOW_TOPK = false

export default function Settings({ status, onSaved }) {
  const [settings, setSettings] = useState(null)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => { api.getSettings().then(setSettings).catch((e) => setError(String(e))) }, [])

  function set(key, value) { setSettings((s) => ({ ...s, [key]: value })); setSaved(false) }

  async function save() {
    try {
      const next = await api.saveSettings(settings)
      setSettings(next); setSaved(true); onSaved?.()
    } catch (e) { setError(String(e)) }
  }

  if (error) return <div className="page"><Banner kind="error">{error}</Banner></div>
  if (!settings || !status) return <div className="page"><Spinner label="Loading settings…" /></div>

  const models = status.embedding_models || {}
  const faissBuilt = new Set(status.vector_backends?.faiss_models || [])
  const milvusBuilt = new Set(status.vector_backends?.milvus_models || [])
  const builtFor = (backend) => (backend === 'milvus' ? milvusBuilt : faissBuilt)

  return (
    <div className="page">
      <div className="page-head">
        <h2>Settings</h2>
        <p>Vector backend, embedding model, and RAG engine. Applies to every new analysis.</p>
      </div>

      <div className="stat-row">
        <div className="stat"><span>Groq LLM</span><b>{status.llm_available ? 'available' : 'fallback'}</b></div>
        <div className="stat"><span>FAISS models</span><b>{faissBuilt.size}</b></div>
        <div className="stat"><span>Milvus</span><b>{status.vector_backends?.milvus_installed ? 'installed' : 'no'}</b></div>
        <div className="stat"><span>Stored cases</span><b>{status.case_count}</b></div>
      </div>

      <Card title="Configuration">
        <label>Vector database</label>
        <div className="seg">
          {['faiss', 'milvus'].map((b) => (
            <button key={b} className={settings.vector_backend === b ? 'on' : ''}
              onClick={() => set('vector_backend', b)}>{b}</button>
          ))}
        </div>

        <label>Embedding model</label>
        <div className="opts">
          {Object.entries(models).map(([key, m]) => (
            <button key={key} className={`opt ${settings.embedding_model === key ? 'on' : ''}`}
              onClick={() => set('embedding_model', key)}>
              <b>{m.label}</b>
              <span>{m.dim}d · {builtFor(settings.vector_backend).has(key) ? '✅ built' : '⏳ not built'}</span>
            </button>
          ))}
        </div>

        <label>RAG engine</label>
        <div className="seg">
          {['Native', 'LangChain'].map((e) => (
            <button key={e} className={settings.rag_engine === e ? 'on' : ''}
              onClick={() => set('rag_engine', e)}>{e}</button>
          ))}
        </div>

        {SHOW_TOPK && (
          <>
            <label>Similar cases to retrieve (Top-K): <b>{settings.top_k}</b></label>
            <input type="range" min="1" max="15" value={settings.top_k}
              onChange={(ev) => set('top_k', Number(ev.target.value))} />
          </>
        )}

        <button className="primary" onClick={save}>💾 Save settings</button>
        {saved && <Banner kind="ok">Settings saved.</Banner>}
        {!builtFor(settings.vector_backend).has(settings.embedding_model) && (
          <Banner kind="warn">
            No <code>{settings.embedding_model}</code> index in <code>{settings.vector_backend}</code>.
            Build it before analyzing with this combination.
          </Banner>
        )}
      </Card>
    </div>
  )
}
