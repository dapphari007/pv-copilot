// Small reusable presentational components shared across pages.

export function Card({ title, children, right }) {
  return (
    <div className="card">
      {(title || right) && (
        <div className="card-head">
          {title && <h3>{title}</h3>}
          {right}
        </div>
      )}
      {children}
    </div>
  )
}

export function Kv({ k, v }) {
  return (
    <div className="kv">
      <span>{k}</span>
      <b>{v || '—'}</b>
    </div>
  )
}

export function Badge({ kind = 'gray', children }) {
  return <span className={`badge ${kind}`}>{children}</span>
}

export function SeriousBadge({ value }) {
  const serious = value === 'Serious'
  return <span className={`badge ${serious ? 'red' : 'green'}`}>{value || '—'}</span>
}

export function Pills({ items }) {
  return (
    <div className="pills">
      {items.filter(Boolean).map((p, i) => <span className="pill" key={i}>{p}</span>)}
    </div>
  )
}

export function Spinner({ label = 'Working…' }) {
  return (
    <div className="spinner">
      <div className="dot" /><div className="dot" /><div className="dot" />
      <span>{label}</span>
    </div>
  )
}

export function Empty({ icon = '📭', children }) {
  return <div className="empty"><div className="empty-icon">{icon}</div><p>{children}</p></div>
}

export function Banner({ kind = 'info', children }) {
  return <div className={`banner ${kind}`}>{children}</div>
}
