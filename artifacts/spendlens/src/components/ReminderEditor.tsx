import { useEffect, useMemo, useState } from 'react'
import {
  createReminder, deleteReminder, getCategories, getSubcategories, updateReminder,
  type Category, type Reminder, type ReminderCategory, type ReminderRepeat, type Subcategory,
} from '../api'
import { currentMonth } from '../months'
import { MONTHS, T } from '../theme'
import { btn, dangerBtn, Field, input, Modal } from './ui'
import { REPEAT_TEXT } from './reminderUi'

/** Add or edit one reminder. Used from Settings and from the calendar's day panel. */
export default function ReminderEditor({ reminder, defaultDay, defaultCategoryId, categories, onClose, onSaved }: {
  reminder: Reminder | null; defaultDay?: number; defaultCategoryId?: number; categories: ReminderCategory[]
  onClose: () => void; onSaved: (message: string) => void
}) {
  const firstManual = categories.find(c => c.kind === null) ?? categories[0]
  const [name, setName] = useState(reminder?.name ?? '')
  const [catId, setCatId] = useState(reminder?.category_id ?? defaultCategoryId ?? firstManual?.id ?? 0)
  const [amount, setAmount] = useState(String(reminder?.amount ?? 0))
  const [day, setDay] = useState(String(reminder?.day ?? defaultDay ?? new Date().getDate()))
  const [repeat, setRepeat] = useState<ReminderRepeat>(reminder?.repeat ?? 'monthly')
  const [month, setMonth] = useState(reminder?.month ?? Number(currentMonth().slice(5)))
  const [expCat, setExpCat] = useState<number | ''>(reminder?.expense_category_id ?? '')
  const [expSub, setExpSub] = useState<number | ''>(reminder?.expense_subcategory_id ?? '')
  const [expCats, setExpCats] = useState<Category[]>([])
  const [subs, setSubs] = useState<Subcategory[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)

  useEffect(() => {
    getCategories().then(setExpCats).catch(() => setExpCats([]))
    getSubcategories().then(setSubs).catch(() => setSubs([]))
  }, [])

  const catChoices = useMemo(() => expCats.filter(c => c.status !== 'archived' || c.id === expCat), [expCats, expCat])
  const subChoices = useMemo(
    () => subs.filter(s => s.category_id === expCat && (s.status !== 'archived' || s.id === expSub)),
    [subs, expCat, expSub])

  const save = async () => {
    const trimmed = name.trim()
    const d = parseInt(day, 10)
    const a = parseFloat(amount)
    if (!trimmed) return setError('Give the reminder a name.')
    if (!(d >= 1 && d <= 31)) return setError('Day must be between 1 and 31.')
    if (!Number.isFinite(a) || a < 0) return setError('Amount must be 0 or more.')
    if (!catId) return setError('Pick a category.')
    const body = {
      category_id: catId, name: trimmed, amount: a, day: d, repeat, month: repeat === 'monthly' ? null : month,
      enabled: reminder?.enabled ?? true, note: reminder?.note ?? '',
      expense_category_id: expCat === '' ? null : expCat, expense_subcategory_id: expCat === '' || expSub === '' ? null : expSub,
      source_key: reminder?.source_key ?? null,
    }
    setBusy(true); setError('')
    try {
      if (reminder) await updateReminder(reminder.id, body); else await createReminder(body)
      onSaved(reminder ? 'Reminder updated' : 'Reminder added')
    } catch (e) { setError((e as Error).message); setBusy(false) }
  }

  const remove = async () => {
    if (!reminder) return
    setBusy(true); setError('')
    try { await deleteReminder(reminder.id); onSaved(`${reminder.name} deleted`) } catch (e) { setError((e as Error).message); setBusy(false) }
  }

  return (
    <Modal title={reminder ? 'Edit reminder' : 'Add reminder'} onClose={onClose}>
      <form onSubmit={e => { e.preventDefault(); save() }}>
        <Field name="Name"><input style={input} autoFocus value={name} placeholder="e.g. Car insurance" onChange={e => setName(e.target.value)} /></Field>
        <Field name="Category">
          <select style={input} value={catId} onChange={e => setCatId(Number(e.target.value))}>
            {categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </Field>
        <div style={{ display: 'flex', gap: 10 }}>
          <div style={{ flex: 1 }}><Field name="Amount (₹, 0 for none)"><input style={input} type="number" min={0} step="any" value={amount} onChange={e => setAmount(e.target.value)} /></Field></div>
          <div style={{ flex: 1 }}><Field name="Day of month"><input style={input} type="number" min={1} max={31} value={day} onChange={e => setDay(e.target.value)} /></Field></div>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <div style={{ flex: 1 }}>
            <Field name="Repeats">
              <select style={input} value={repeat} onChange={e => setRepeat(e.target.value as ReminderRepeat)}>
                {(Object.keys(REPEAT_TEXT) as ReminderRepeat[]).map(r => <option key={r} value={r}>{REPEAT_TEXT[r]}</option>)}
              </select>
            </Field>
          </div>
          <div style={{ flex: 1, visibility: repeat === 'monthly' ? 'hidden' : 'visible' }}>
            <Field name={repeat === 'quarterly' ? 'Starting in' : 'In month'}>
              <select style={input} value={month} onChange={e => setMonth(Number(e.target.value))} disabled={repeat === 'monthly'}>
                {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m.slice(0, 3)}</option>)}
              </select>
            </Field>
          </div>
        </div>
        <div style={{ borderTop: `1px solid ${T.hairline}`, margin: '4px 0 12px', paddingTop: 12 }}>
          <div style={{ fontSize: 12, color: T.muted, marginBottom: 8, lineHeight: 1.5 }}>
            Track against an expense to tick this off automatically once a matching entry is logged. Optional.
          </div>
          <div style={{ display: 'flex', gap: 10 }}>
            <div style={{ flex: 1 }}>
              <Field name="Expense category">
                <select style={input} value={expCat} onChange={e => { setExpCat(e.target.value ? Number(e.target.value) : ''); setExpSub('') }}>
                  <option value="">None</option>
                  {catChoices.map(c => <option key={c.id} value={c.id}>{c.icon} {c.name}</option>)}
                </select>
              </Field>
            </div>
            <div style={{ flex: 1 }}>
              <Field name="Sub-category">
                <select style={input} value={expSub} disabled={expCat === ''} onChange={e => setExpSub(e.target.value ? Number(e.target.value) : '')}>
                  <option value="">Any</option>
                  {subChoices.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
              </Field>
            </div>
          </div>
        </div>
        {error && <div role="alert" style={{ color: T.negative, fontSize: 12.5, marginBottom: 10 }}>{error}</div>}
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          {reminder && !confirmDelete && <button type="button" style={dangerBtn} disabled={busy} onClick={() => setConfirmDelete(true)}>Delete</button>}
          {reminder && confirmDelete && (
            <>
              <span style={{ fontSize: 12.5, color: T.muted }}>Delete this reminder?</span>
              <button type="button" style={{ ...dangerBtn, background: T.danger, color: '#fff', borderColor: T.danger }} disabled={busy} onClick={remove}>Yes, delete</button>
              <button type="button" style={smallCancel} onClick={() => setConfirmDelete(false)}>Keep</button>
            </>
          )}
          <div style={{ flex: 1 }} />
          <button type="button" style={btn()} onClick={onClose}>Cancel</button>
          <button type="submit" style={{ ...btn(true), opacity: busy ? 0.6 : 1 }} disabled={busy}>{reminder ? 'Save' : 'Add reminder'}</button>
        </div>
      </form>
    </Modal>
  )
}

const smallCancel = { ...btn(), padding: '4px 10px', fontSize: 12 }
