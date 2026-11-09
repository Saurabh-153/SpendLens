import { useCallback, useEffect, useState } from 'react'
import { decideAccessRequest, getAccessRequests, type AccessRequest } from '../../api'
import { useAuth } from '../../auth'
import { T } from '../../theme'
import { AdminHeader, btn, Card, dangerBtn, input } from '../ui'

const day = (s: string | null) => (s ? s.slice(0, 10) : '')
const STATUS_COLOR = { pending: T.warn, approved: T.positive, rejected: T.danger }

export default function AccessRequests() {
  const { refresh } = useAuth()
  const [rows, setRows] = useState<AccessRequest[]>([])
  const [notes, setNotes] = useState<Record<number, string>>({})
  const [error, setError] = useState('')

  const load = useCallback(() => getAccessRequests().then(setRows).catch(e => setError(e.message)), [])
  useEffect(() => { load() }, [load])

  const decide = async (r: AccessRequest, approve: boolean) => {
    try {
      await decideAccessRequest(r.id, approve, notes[r.id] ?? '')
      setError(''); await load(); await refresh()   // refresh() updates the pending badge on the admin button
    } catch (e) { setError((e as Error).message) }
  }

  const pending = rows.filter(r => r.status === 'pending')
  const decided = rows.filter(r => r.status !== 'pending')

  return (
    <div>
      <AdminHeader title="Access requests" hint="Users ask for a module they do not have; approving turns it on straight away." />
      {error && <p style={{ color: T.danger, fontSize: 12.5, marginBottom: 10 }}>{error}</p>}
      <Card style={{ marginBottom: 20 }}>
        <div style={{ fontWeight: 700, marginBottom: 10 }}>Waiting for approval ({pending.length})</div>
        {pending.length === 0 && <p style={{ color: T.muted, fontSize: 13 }}>Nothing is waiting.</p>}
        {pending.map(r => (
          <div key={r.id} style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 10, padding: '10px 0', borderTop: `1px solid ${T.hairline}` }}>
            <div style={{ flex: '1 1 240px', minWidth: 0 }}>
              <div style={{ fontWeight: 600 }}>{r.user_name || r.user_email} <span style={{ color: T.muted, fontWeight: 400 }}>wants</span> {r.module}</div>
              <div style={{ color: T.muted, fontSize: 12 }}>{r.user_email} · {day(r.created_at)}{r.note ? ` · "${r.note}"` : ''}</div>
            </div>
            <input style={{ ...input, flex: '1 1 160px', width: 'auto' }} placeholder="Note (optional)" value={notes[r.id] ?? ''} onChange={e => setNotes(n => ({ ...n, [r.id]: e.target.value }))} />
            <button style={btn(true)} onClick={() => decide(r, true)}>Approve</button>
            <button style={dangerBtn} onClick={() => decide(r, false)}>Reject</button>
          </div>
        ))}
      </Card>
      <Card>
        <div style={{ fontWeight: 700, marginBottom: 10 }}>History</div>
        {decided.length === 0 && <p style={{ color: T.muted, fontSize: 13 }}>No decisions yet.</p>}
        {decided.map(r => (
          <div key={r.id} style={{ display: 'flex', gap: 10, padding: '8px 0', borderTop: `1px solid ${T.hairline}`, fontSize: 13 }}>
            <span style={{ color: STATUS_COLOR[r.status], width: 80, fontWeight: 600 }}>{r.status}</span>
            <span style={{ flex: 1 }}>{r.user_email} · {r.module}{r.decision_note ? <span style={{ color: T.muted }}> · {r.decision_note}</span> : null}</span>
            <span style={{ color: T.muted }}>{day(r.decided_at)}</span>
          </div>
        ))}
      </Card>
    </div>
  )
}
