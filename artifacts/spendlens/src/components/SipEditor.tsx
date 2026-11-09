import { useState } from 'react'
import { setHoldingSip, type SipSource } from '../api'
import { T } from '../theme'
import { btn, input, Modal } from './ui'

/** Edit the amount and day of the SIPs behind one calendar entry. Saves through the Holdings SIP endpoint. */
export default function SipEditor({ title, sources, onClose, onSaved }: {
  title: string; sources: SipSource[]; onClose: () => void; onSaved: (message: string) => void
}) {
  const [rows, setRows] = useState(() => sources.map(s => ({ ...s, amount: String(s.amount), day: String(s.day) })))
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const patch = (i: number, p: Partial<(typeof rows)[number]>) => setRows(rs => rs.map((r, j) => (j === i ? { ...r, ...p } : r)))

  const save = async () => {
    const changes: { id: number; name: string; amount: number; day: number }[] = []
    for (const [i, r] of rows.entries()) {
      const amount = parseFloat(r.amount), day = parseInt(r.day, 10)
      if (!Number.isFinite(amount) || amount < 0) return setError(`${r.name}: amount must be 0 or more.`)
      const stopped = amount === 0
      if (!stopped && !(day >= 1 && day <= 31)) return setError(`${r.name}: day must be between 1 and 31.`)
      const next = { amount, day: stopped ? 0 : day }
      if (next.amount !== sources[i].amount || next.day !== sources[i].day) changes.push({ id: r.holding_id, name: r.name, ...next })
    }
    if (!changes.length) return onClose()
    setBusy(true); setError('')
    try {
      await Promise.all(changes.map(c => setHoldingSip(c.id, c.amount, c.day)))
      onSaved(changes.length === 1 ? `${changes[0].name} updated` : `${changes.length} SIPs updated`)
    } catch (e) { setError((e as Error).message); setBusy(false) }
  }

  return (
    <Modal title={`Edit ${title}`} onClose={onClose}>
      <form onSubmit={e => { e.preventDefault(); save() }}>
        <div style={{ fontSize: 12, color: T.muted, lineHeight: 1.5, marginBottom: 12 }}>
          Changes are saved to the Holdings page. Set an amount of 0 to stop a SIP; it then disappears from the calendar.
          SIPs you have hidden from reminders are managed in Settings › Reminders.
        </div>
        {rows.map((r, i) => (
          <div key={r.holding_id} style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 110px 70px', gap: 8, alignItems: 'end', marginBottom: 10 }}>
            <div style={{ fontSize: 13, minWidth: 0, overflowWrap: 'anywhere', paddingBottom: 8 }}>{r.name}</div>
            <label style={{ fontSize: 11.5, color: T.muted }}>Amount (₹)
              <input style={{ ...input, marginTop: 3 }} type="number" min={0} step="any" autoFocus={i === 0} value={r.amount} onChange={e => patch(i, { amount: e.target.value })} />
            </label>
            <label style={{ fontSize: 11.5, color: T.muted }}>Day
              <input style={{ ...input, marginTop: 3 }} type="number" min={1} max={31} value={r.day} onChange={e => patch(i, { day: e.target.value })} />
            </label>
          </div>
        ))}
        {error && <div role="alert" style={{ color: T.negative, fontSize: 12.5, marginBottom: 10 }}>{error}</div>}
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <button type="button" style={btn()} onClick={onClose}>Cancel</button>
          <button type="submit" style={{ ...btn(true), opacity: busy ? 0.6 : 1 }} disabled={busy}>Save</button>
        </div>
      </form>
    </Modal>
  )
}
