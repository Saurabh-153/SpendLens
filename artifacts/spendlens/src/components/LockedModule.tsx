import { useState } from 'react'
import { requestAccess, type ModuleId } from '../api'
import { useAuth } from '../auth'
import { T } from '../theme'
import { btn, card, input } from './ui'

const fmtDate = (s: string) => s.slice(0, 10)

/** Shown instead of a module the signed-in user has not been given: explains it and lets them ask the admin. */
export default function LockedModule({ module }: { module: ModuleId }) {
  const { me, refresh } = useAuth()
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const info = me?.all_modules.find(m => m.id === module)
  const mine = (me?.requests ?? []).filter(r => r.module === module)
  const pending = mine.find(r => r.status === 'pending')
  const last = mine.find(r => r.status === 'rejected')

  const send = async () => {
    setBusy(true); setError('')
    try { await requestAccess(module, note); setNote(''); await refresh() } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }

  return (
    <div style={{ display: 'flex', justifyContent: 'center', padding: '60px 20px' }}>
      <div style={{ ...card, padding: 28, width: 440, maxWidth: '100%', textAlign: 'center' }}>
        <div style={{ fontSize: 40 }}>🔒</div>
        <h2 style={{ fontSize: 20, fontWeight: 700, margin: '8px 0 6px' }}>{info?.label ?? module} is not enabled</h2>
        <p style={{ color: T.muted, fontSize: 13, lineHeight: 1.5, marginBottom: 18 }}>{info?.description}</p>
        {pending ? (
          <p style={{ fontSize: 13.5 }}>⏳ Your request from {fmtDate(pending.created_at)} is waiting for an admin to approve it.</p>
        ) : (
          <>
            {last && <p style={{ color: T.warn, fontSize: 12.5, marginBottom: 12 }}>Your last request was declined{last.decision_note ? `: ${last.decision_note}` : '.'}</p>}
            <textarea style={{ ...input, minHeight: 64, resize: 'vertical', marginBottom: 12 }} placeholder="Why do you need it? (optional)" maxLength={500}
              value={note} onChange={e => setNote(e.target.value)} />
            {error && <p style={{ color: T.danger, fontSize: 12.5, marginBottom: 12 }}>{error}</p>}
            <button style={{ ...btn(true), width: '100%', opacity: busy ? 0.6 : 1 }} disabled={busy} onClick={send}>Request access</button>
          </>
        )}
      </div>
    </div>
  )
}
