import { useState } from 'react'
import { createVacation, deleteVacation, updateVacation, type Vacation } from '../api'
import { T } from '../theme'
import { btn, dangerBtn, Field, input, Modal } from './ui'
import { REMINDER_PALETTE, Swatches } from './reminderUi'

/** Add or edit one vacation. Used from Settings and from the calendar's day panel. */
export default function VacationEditor({ vacation, defaultFrom, onClose, onSaved }: {
  vacation: Vacation | null; defaultFrom?: string; onClose: () => void; onSaved: (message: string) => void
}) {
  const start = vacation?.start_date ?? defaultFrom ?? ''
  const [name, setName] = useState(vacation?.name ?? '')
  const [from, setFrom] = useState(start)
  const [to, setTo] = useState(vacation?.end_date ?? start)
  const [toTouched, setToTouched] = useState(!!vacation)
  const [colour, setColour] = useState(vacation?.color ?? REMINDER_PALETTE[6])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const changeFrom = (v: string) => { setFrom(v); if (!toTouched || to < v) setTo(v) }

  const save = async () => {
    const trimmed = name.trim()
    if (!trimmed) return setError('Give the vacation a name.')
    if (!from || !to) return setError('Pick both dates.')
    if (to < from) return setError('The last day cannot be before the first day.')
    const body = { name: trimmed, start_date: from, end_date: to, color: colour }
    setBusy(true); setError('')
    try {
      if (vacation) await updateVacation(vacation.id, body); else await createVacation(body)
      onSaved(vacation ? 'Vacation updated' : 'Vacation added')
    } catch (e) { setError((e as Error).message); setBusy(false) }
  }

  const remove = async () => {
    if (!vacation) return
    setBusy(true); setError('')
    try { await deleteVacation(vacation.id); onSaved(`${vacation.name} deleted`) } catch (e) { setError((e as Error).message); setBusy(false) }
  }

  return (
    <Modal title={vacation ? 'Edit vacation' : 'Add vacation'} onClose={onClose}>
      <form onSubmit={e => { e.preventDefault(); save() }}>
        <Field name="Name"><input style={input} autoFocus value={name} placeholder="e.g. Goa trip" onChange={e => setName(e.target.value)} /></Field>
        <div style={{ display: 'flex', gap: 10 }}>
          <div style={{ flex: 1 }}><Field name="From"><input style={input} type="date" value={from} onChange={e => changeFrom(e.target.value)} /></Field></div>
          <div style={{ flex: 1 }}><Field name="To"><input style={input} type="date" min={from || undefined} value={to} onChange={e => { setTo(e.target.value); setToTouched(true) }} /></Field></div>
        </div>
        <Field name="Colour"><Swatches value={colour} onChange={setColour} /></Field>
        <div style={{ fontSize: 12, color: T.muted, lineHeight: 1.5, margin: '2px 0 12px' }}>
          Every day in the range is tinted on the calendar and the trip appears in the calendar link.
        </div>
        {error && <div role="alert" style={{ color: T.negative, fontSize: 12.5, marginBottom: 10 }}>{error}</div>}
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          {vacation && !confirmDelete && <button type="button" style={dangerBtn} disabled={busy} onClick={() => setConfirmDelete(true)}>Delete</button>}
          {vacation && confirmDelete && (
            <>
              <span style={{ fontSize: 12.5, color: T.muted }}>Delete this vacation?</span>
              <button type="button" style={{ ...dangerBtn, background: T.danger, color: '#fff', borderColor: T.danger }} disabled={busy} onClick={remove}>Yes, delete</button>
              <button type="button" style={smallCancel} onClick={() => setConfirmDelete(false)}>Keep</button>
            </>
          )}
          <div style={{ flex: 1 }} />
          <button type="button" style={btn()} onClick={onClose}>Cancel</button>
          <button type="submit" style={{ ...btn(true), opacity: busy ? 0.6 : 1 }} disabled={busy}>{vacation ? 'Save' : 'Add vacation'}</button>
        </div>
      </form>
    </Modal>
  )
}

const smallCancel = { ...btn(), padding: '4px 10px', fontSize: 12 }
