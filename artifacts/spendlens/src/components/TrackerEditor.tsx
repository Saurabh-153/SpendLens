import { useEffect, useMemo, useState } from 'react'
import {
  createTracker, deleteTracker, getCategories, getReminders, getSubcategories, getTrackers, updateTracker,
  type Category, type Reminder, type Subcategory, type Tracker, type TrackerCostLink, type TrackerPause,
} from '../api'
import { T } from '../theme'
import { REMINDER_PALETTE, Swatches } from './reminderUi'
import { btn, dangerBtn, Field, input, label, Modal, smallBtn } from './ui'

export const TRACKER_WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const PAUSES: { id: TrackerPause; text: string }[] = [{ id: 'vacation', text: 'Vacations' }, { id: 'IN', text: 'India holidays' }, { id: 'US', text: 'US holidays' }]

/** 'Mon, Wed, Fri', or 'any day' when all seven count. */
export function weekdayText(days: number[]): string {
  return days.length === 7 ? 'any day' : [...days].sort().map(d => TRACKER_WEEKDAYS[d]).join(', ')
}

const toggleBtn = (on: boolean) => ({
  ...smallBtn, background: on ? T.accent : T.surface2, borderColor: on ? T.accent : T.border, color: on ? '#fff' : T.muted,
})

/** Add or edit one tracker: what it is, how often, which days count, what pauses it, and what money it is tied to. */
export default function TrackerEditor({ tracker, nextColour, onClose, onSaved }: {
  tracker: Tracker | null; nextColour?: string; onClose: () => void; onSaved: (message: string) => void
}) {
  const [name, setName] = useState(tracker?.name ?? '')
  const [colour, setColour] = useState(tracker?.color ?? nextColour ?? REMINDER_PALETTE[4])
  const [target, setTarget] = useState(String(tracker?.target_per_week ?? 3))
  const [weekdays, setWeekdays] = useState<number[]>(tracker?.weekdays ?? [0, 1, 2, 3, 4, 5, 6])
  const [pause, setPause] = useState<TrackerPause[]>(tracker?.pause_on ?? [])
  const [links, setLinks] = useState<TrackerCostLink[]>(tracker?.cost_links ?? [])
  const [bill, setBill] = useState<number | null>(tracker?.bill_reminder_id ?? null)
  const [cats, setCats] = useState<Category[]>([])
  const [subs, setSubs] = useState<Subcategory[]>([])
  const [rems, setRems] = useState<Reminder[]>([])
  const [adding, setAdding] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)

  useEffect(() => {
    Promise.all([getCategories(), getSubcategories(), getReminders()])
      .then(([c, s, r]) => { setCats(c.filter(x => x.status !== 'scheduled')); setSubs(s); setRems(r) })
      .catch(e => setError((e as Error).message))
  }, [])

  const catName = useMemo(() => new Map(cats.map(c => [c.id, c.name])), [cats])
  const subName = useMemo(() => new Map(subs.map(s => [s.id, s.name])), [subs])
  const linkText = (l: TrackerCostLink) => `${catName.get(l.category_id) ?? 'Category'}${l.subcategory_id ? ` › ${subName.get(l.subcategory_id) ?? 'Sub-category'}` : ''}`
  const linkKey = (l: TrackerCostLink) => `${l.category_id}:${l.subcategory_id ?? 0}`
  const has = new Set(links.map(linkKey))

  const flip = <V,>(list: V[], v: V) => (list.includes(v) ? list.filter(x => x !== v) : [...list, v])

  const addLink = (value: string) => {
    setAdding('')
    if (!value) return
    const [c, s] = value.split(':').map(Number)
    const l = { category_id: c, subcategory_id: s || null }
    if (!has.has(linkKey(l))) setLinks([...links, l])
  }

  const save = async () => {
    const trimmed = name.trim(), n = Number(target)
    if (!trimmed) return setError('Give the tracker a name.')
    if (!Number.isInteger(n) || n < 1 || n > 7) return setError('The target is a whole number of days a week, 1 to 7.')
    if (!weekdays.length) return setError('Pick at least one day it counts on.')
    const body = { name: trimmed, color: colour, target_per_week: n, weekdays: [...weekdays].sort(), pause_on: pause, cost_links: links, bill_reminder_id: bill }
    setBusy(true); setError('')
    try {
      if (tracker) await updateTracker(tracker.id, body); else await createTracker(body)
      onSaved(tracker ? 'Tracker updated' : 'Tracker added')
    } catch (e) { setError((e as Error).message); setBusy(false) }
  }

  const remove = async () => {
    if (!tracker) return
    setBusy(true); setError('')
    try { await deleteTracker(tracker.id); onSaved(`${tracker.name} deleted`) } catch (e) { setError((e as Error).message); setBusy(false) }
  }

  return (
    <Modal title={tracker ? 'Edit tracker' : 'Add tracker'} onClose={onClose}>
      <form onSubmit={e => { e.preventDefault(); save() }}>
        <Field name="Name"><input style={input} autoFocus value={name} placeholder="e.g. Gym, Office, Cooked at home" onChange={e => setName(e.target.value)} /></Field>
        <Field name="Colour"><Swatches value={colour} onChange={setColour} /></Field>
        <Field name="Target, days a week">
          <input style={{ ...input, width: 90 }} type="number" min={1} max={7} value={target} onChange={e => setTarget(e.target.value)} />
        </Field>
        <div role="group" aria-label="Counts on" style={{ marginBottom: 12 }}>
          <div style={{ ...label, marginBottom: 5 }}>Counts on</div>
          <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
            {TRACKER_WEEKDAYS.map((d, i) => (
              <button key={d} type="button" aria-pressed={weekdays.includes(i)} style={toggleBtn(weekdays.includes(i))} onClick={() => setWeekdays(flip(weekdays, i))}>{d}</button>
            ))}
          </div>
        </div>
        <div role="group" aria-label="Pause on" style={{ marginBottom: 12 }}>
          <div style={{ ...label, marginBottom: 5 }}>Pause on</div>
          <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
            {PAUSES.map(p => (
              <button key={p.id} type="button" aria-pressed={pause.includes(p.id)} style={toggleBtn(pause.includes(p.id))} onClick={() => setPause(flip(pause, p.id))}>{p.text}</button>
            ))}
          </div>
          <div style={{ fontSize: 11.5, color: T.muted, marginTop: 5, lineHeight: 1.5 }}>Paused days lower the week’s goal instead of counting as missed.</div>
        </div>
        <div style={{ marginBottom: 12 }}>
          <div style={{ ...label, marginBottom: 5 }}>Link spending</div>
          {links.length > 0 && (
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 6 }}>
              {links.map(l => (
                <span key={linkKey(l)} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12, background: T.surface2, border: `1px solid ${T.border}`, borderRadius: 999, padding: '3px 4px 3px 10px' }}>
                  {linkText(l)}
                  <button type="button" aria-label={`Remove ${linkText(l)}`} onClick={() => setLinks(links.filter(x => linkKey(x) !== linkKey(l)))}
                    style={{ border: 'none', background: 'transparent', color: T.muted, cursor: 'pointer', fontSize: 14, lineHeight: 1, padding: '0 4px' }}>×</button>
                </span>
              ))}
            </div>
          )}
          <select style={input} aria-label="Add spending to link" value={adding} onChange={e => addLink(e.target.value)}>
            <option value="">+ Add a category or sub-category…</option>
            {cats.map(c => [
              <option key={`c${c.id}`} value={`${c.id}:0`} disabled={has.has(`${c.id}:0`)}>{c.icon} {c.name} (all)</option>,
              ...subs.filter(s => s.category_id === c.id).map(s => (
                <option key={`s${s.id}`} value={`${c.id}:${s.id}`} disabled={has.has(`${c.id}:${s.id}`)}>{'   '}{s.name}</option>
              )),
            ])}
          </select>
          <div style={{ fontSize: 11.5, color: T.muted, marginTop: 5, lineHeight: 1.5 }}>
            Powers the “what a {name.trim() || 'tracker'} day costs” card: this spending on ticked days against the other days it counts on.
          </div>
        </div>
        <Field name="Cost per visit bill (optional)">
          <select style={input} value={bill ?? ''} onChange={e => setBill(e.target.value ? Number(e.target.value) : null)}>
            <option value="">None</option>
            {rems.map(r => <option key={r.id} value={r.id}>{r.name}{r.amount ? ` · ₹${Math.round(r.amount).toLocaleString('en-IN')}` : ''}</option>)}
          </select>
        </Field>
        {error && <div role="alert" style={{ color: T.negative, fontSize: 12.5, marginBottom: 10 }}>{error}</div>}
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          {tracker && !confirmDelete && <button type="button" style={dangerBtn} disabled={busy} onClick={() => setConfirmDelete(true)}>Delete</button>}
          {tracker && confirmDelete && (
            <>
              <span style={{ fontSize: 12.5, color: T.muted }}>Delete it and every tick?</span>
              <button type="button" style={{ ...dangerBtn, background: T.danger, color: '#fff', borderColor: T.danger }} disabled={busy} onClick={remove}>Yes, delete</button>
              <button type="button" style={smallBtn} onClick={() => setConfirmDelete(false)}>Keep</button>
            </>
          )}
          <div style={{ flex: 1 }} />
          <button type="button" style={btn()} onClick={onClose}>Cancel</button>
          <button type="submit" style={{ ...btn(true), opacity: busy ? 0.6 : 1 }} disabled={busy}>{tracker ? 'Save' : 'Add tracker'}</button>
        </div>
      </form>
    </Modal>
  )
}

/** The calendar's 'Manage trackers' dialog: the list, with add and edit going through TrackerEditor. */
export function TrackerManager({ onClose, onChanged }: { onClose: () => void; onChanged: (message: string) => void }) {
  const [list, setList] = useState<Tracker[]>([])
  const [error, setError] = useState('')
  const [edit, setEdit] = useState<Tracker | 'new' | null>(null)
  const load = () => getTrackers().then(t => setList([...t].sort((a, b) => a.sort_order - b.sort_order))).catch(e => setError((e as Error).message))
  useEffect(() => { load() }, [])

  if (edit) {
    return (
      <TrackerEditor tracker={edit === 'new' ? null : edit} nextColour={REMINDER_PALETTE[(list.length + 4) % REMINDER_PALETTE.length]}
        onClose={() => setEdit(null)} onSaved={m => { setEdit(null); onChanged(m); load() }} />
    )
  }
  return (
    <Modal title="Manage trackers" onClose={onClose}>
      {error && <div role="alert" style={{ color: T.negative, fontSize: 12.5, marginBottom: 10 }}>{error}</div>}
      {list.length === 0 && !error && <p style={{ fontSize: 13, color: T.muted, marginBottom: 12 }}>No trackers yet. Add one for anything you want to tick off by day, such as Gym or Office.</p>}
      {list.map((t, i) => (
        <div key={t.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0', borderTop: i ? `1px solid ${T.hairline}` : undefined }}>
          <span style={{ width: 12, height: 12, borderRadius: 3, background: t.color, flexShrink: 0 }} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 13.5, fontWeight: 600 }}>{t.name}</div>
            <div style={{ fontSize: 11.5, color: T.muted }}>{t.target_per_week}× a week · {weekdayText(t.weekdays)}</div>
          </div>
          <button type="button" style={smallBtn} onClick={() => setEdit(t)}>Edit</button>
        </div>
      ))}
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 14 }}>
        <button type="button" style={btn()} onClick={() => setEdit('new')}>+ Add tracker</button>
        <button type="button" style={btn(true)} onClick={onClose}>Done</button>
      </div>
    </Modal>
  )
}
