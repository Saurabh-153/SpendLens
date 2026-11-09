import { useEffect, useState } from 'react'
import { getStatus, type DbStatus } from '../api'
import { T } from '../theme'

function ago(iso: string | null | undefined): string {
  if (!iso) return 'an unknown time'
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000)
  if (!Number.isFinite(mins)) return 'an unknown time'
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins} min ago`
  const hrs = Math.round(mins / 60)
  if (hrs < 24) return `${hrs} h ago`
  return new Date(iso).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}

/** Shown on every page while PostgreSQL is down and the app is serving its read-only SQLite copy. */
export default function DatabaseBanner() {
  const [status, setStatus] = useState<DbStatus | null>(null)
  useEffect(() => {
    let live = true
    const poll = () => getStatus().then(s => { if (live) setStatus(s) }).catch(() => {})
    poll()
    const id = setInterval(poll, 60000)
    return () => { live = false; clearInterval(id) }
  }, [])
  if (status?.mode !== 'read-only-fallback') return null
  return (
    <div role="status" style={{
      display: 'flex', alignItems: 'center', gap: 10, padding: '9px 20px', fontSize: 13, lineHeight: 1.45,
      background: `${T.warn}1f`, borderBottom: `1px solid ${T.warn}66`, color: T.text,
    }}>
      <span aria-hidden="true" style={{ width: 8, height: 8, borderRadius: '50%', background: T.warn, flexShrink: 0 }} />
      <span>
        <b>PostgreSQL is unavailable</b>: you're viewing a read-only copy from {ago(status.mirror?.updated_at)}.
        Changes are disabled until it reconnects.
      </span>
    </div>
  )
}
