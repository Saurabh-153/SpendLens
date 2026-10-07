import { useState } from 'react'
import type { GridCategory, GridEntry, Subcategory } from '../api'
import { MONTHS, T, fmtFull } from '../theme'
import { btn, Field, input, label, Modal } from './ui'

const subsFor = (subs: Subcategory[], categoryId: number, keepIds: (number | null)[] = []) =>
  subs.filter(s => s.category_id === categoryId && (!s.archived || keepIds.includes(s.id)))

function SubSelect({ value, options, onChange, none = '— no sub-category —' }: {
  value: number | null; options: Subcategory[]; onChange: (v: number | null) => void; none?: string
}) {
  return (
    <select style={input} value={value ?? ''} onChange={e => onChange(e.target.value ? Number(e.target.value) : null)}>
      <option value="">{none}</option>
      {options.map(s => <option key={s.id} value={s.id}>{s.name}{s.archived ? ' (archived)' : ''}</option>)}
    </select>
  )
}

interface Line { id: number | null; subcategory_id: number | null; amount: string; note: string }

/** Edit every entry of one category/day: sub-category + amount + note per line. */
export function CellEditor({ category, day, month, entries, subs, onClose, onSave }: {
  category: GridCategory; day: number; month: string; entries: GridEntry[]; subs: Subcategory[]
  onClose: () => void
  onSave: (lines: { id: number | null; subcategory_id: number | null; amount: number; note: string }[]) => void
}) {
  const [lines, setLines] = useState<Line[]>(
    entries.length
      ? entries.map(e => ({ id: e.id, subcategory_id: e.subcategory_id, amount: String(e.amount), note: e.note }))
      : [{ id: null, subcategory_id: null, amount: '', note: '' }],
  )
  const patch = (i: number, p: Partial<Line>) => setLines(ls => ls.map((l, j) => (j === i ? { ...l, ...p } : l)))
  const total = lines.reduce((s, l) => s + (parseFloat(l.amount) || 0), 0)
  const [y, m] = month.split('-').map(Number)
  const submit = () => onSave(lines
    .filter(l => parseFloat(l.amount))
    .map(l => ({ id: l.id, subcategory_id: l.subcategory_id, amount: parseFloat(l.amount), note: l.note })))

  return (
    <Modal title={`${category.icon} ${category.name} · ${day} ${MONTHS[m - 1]} ${y}`} onClose={onClose}>
      <form onSubmit={e => { e.preventDefault(); submit() }}>
        {lines.map((l, i) => (
          <div key={i} style={{ display: 'grid', gridTemplateColumns: '1fr 96px 28px', gap: 8, marginBottom: 8, alignItems: 'start' }}>
            <div>
              <SubSelect value={l.subcategory_id} onChange={v => patch(i, { subcategory_id: v })}
                options={subsFor(subs, category.id, [l.subcategory_id])} />
              <input style={{ ...input, marginTop: 6, fontSize: 12 }} placeholder="Note (optional)" value={l.note}
                onChange={e => patch(i, { note: e.target.value })} />
            </div>
            <input style={input} type="number" step="any" placeholder="₹" autoFocus={i === 0} value={l.amount}
              onChange={e => patch(i, { amount: e.target.value })} />
            <button type="button" title="Remove line" style={{ ...btn(), padding: '6px 0', color: T.danger }}
              onClick={() => setLines(ls => (ls.length > 1 ? ls.filter((_, j) => j !== i) : [{ id: null, subcategory_id: null, amount: '', note: '' }]))}>×</button>
          </div>
        ))}
        <button type="button" style={{ ...btn(), fontSize: 12, padding: '5px 10px', marginBottom: 14 }}
          onClick={() => setLines(ls => [...ls, { id: null, subcategory_id: null, amount: '', note: '' }])}>+ Add line</button>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, fontSize: 13 }}>
          <span style={{ ...label }}>Day total</span>
          <b>{total < 0 ? '-' : ''}{fmtFull(total)}</b>
        </div>
        <div style={{ fontSize: 11.5, color: T.muted, marginBottom: 12 }}>Lines with no amount are removed; clearing every line empties the cell.</div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button type="button" style={btn()} onClick={onClose}>Cancel</button>
          <button type="submit" style={btn(true)}>Save</button>
        </div>
      </form>
    </Modal>
  )
}

/** Parse "5" or "5-12" into an inclusive day range, or null if invalid. */
function parseDays(text: string, max: number): [number, number] | null {
  const m = text.trim().match(/^(\d{1,2})\s*(?:[-–]\s*(\d{1,2}))?$/)
  if (!m) return null
  const from = Number(m[1]), to = m[2] ? Number(m[2]) : from
  return from >= 1 && to <= max && from <= to ? [from, to] : null
}

/** One dialog for a single expense or the same amount over a range of days ("5-12"). */
export function AddDialog({ cats, subs, days, defaultDay, initialCat, initialSub, onClose, onSave }: {
  cats: GridCategory[]; subs: Subcategory[]; days: number; defaultDay: number; initialCat?: number; initialSub?: number | null; onClose: () => void
  onSave: (v: { cat: number; from: number; to: number; amount: number; sub: number | null; note: string; replace: boolean }) => void
}) {
  const startCat = cats.some(c => c.id === initialCat) ? initialCat! : cats[0]?.id ?? 0
  const [cat, setCat] = useState(startCat)
  const [sub, setSub] = useState<number | null>(
    initialSub != null && subsFor(subs, startCat).some(s => s.id === initialSub) ? initialSub : null)
  const [dayText, setDayText] = useState(String(defaultDay))
  const [amount, setAmount] = useState('')
  const [note, setNote] = useState('')
  const [replace, setReplace] = useState(false)
  const amt = parseFloat(amount)
  const range = parseDays(dayText, days)
  const count = range ? range[1] - range[0] + 1 : 0
  const valid = Number.isFinite(amt) && amt > 0 && !!range
  return (
    <Modal title="Add expense" onClose={onClose}>
      <form onSubmit={e => { e.preventDefault(); if (valid && range) onSave({ cat, from: range[0], to: range[1], amount: amt, sub, note, replace }) }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          <Field name="Category">
            <select style={input} value={cat} onChange={e => { setCat(Number(e.target.value)); setSub(null) }}>
              {cats.map(c => <option key={c.id} value={c.id}>{c.icon} {c.name}</option>)}
            </select>
          </Field>
          <Field name="Sub-category"><SubSelect value={sub} onChange={setSub} options={subsFor(subs, cat)} none="—" /></Field>
          <Field name="Amount (₹)"><input style={input} type="number" step="any" autoFocus value={amount} onChange={e => setAmount(e.target.value)} /></Field>
          <Field name="Day or range">
            <input style={{ ...input, borderColor: dayText && !range ? T.negative : T.border }} placeholder="5  or  5-12" value={dayText}
              onChange={e => setDayText(e.target.value)} />
          </Field>
        </div>
        <Field name="Note (optional)"><input style={input} value={note} onChange={e => setNote(e.target.value)} /></Field>
        {count > 1 && (
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5, color: T.muted, marginBottom: 10 }}>
            <input type="checkbox" checked={replace} onChange={e => setReplace(e.target.checked)} />
            Replace existing {sub == null ? 'entries' : 'entries of this sub-category'} on those days (otherwise add on top)
          </label>
        )}
        <div style={{ fontSize: 12, color: valid ? T.muted : T.negative, marginBottom: 12, minHeight: 16 }}>
          {!range ? `Enter a day 1-${days}, or a range like 5-12` : valid ? `${count} day${count > 1 ? 's' : ''} × ${fmtFull(amt)} = ${fmtFull(amt * count)}` : ''}
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button type="button" style={btn()} onClick={onClose}>Cancel</button>
          <button type="submit" style={{ ...btn(true), opacity: valid ? 1 : 0.5 }} disabled={!valid}>Add</button>
        </div>
      </form>
    </Modal>
  )
}
