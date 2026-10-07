import { useCallback, useEffect, useState } from 'react'
import { addPerk, deletePerk, getPerks, updatePerk, type Perk, type Perks } from '../api'
import { T, fmt } from '../theme'
import { btn, Field, input, label, smallBtn } from './ui'

const blank = { kind: 'other', title: '', detail: '', value_yr: '', source: '' }

/** A card's benefits, written down so a decision about it can be made from one place. Read-only on the card's page;
 *  with `editable` (Admin) you can add, reword, tick off or remove entries. An entry that came from published terms is
 *  marked "to check" until you confirm it, because issuers change terms. */
export default function CardPerks({ cardId, editable = false }: { cardId: number; editable?: boolean }) {
  const [d, setD] = useState<Perks | null>(null)
  const [error, setError] = useState('')
  const [edit, setEdit] = useState<{ id: number | 'new'; f: typeof blank } | null>(null)

  const load = useCallback(() => { getPerks(cardId).then(setD).catch(e => setError(e.message)) }, [cardId])
  useEffect(load, [load])

  const run = async (p: Promise<Perks>) => {
    try { setD(await p); setEdit(null); setError('') } catch (e) { setError((e as Error).message) }
  }
  if (!d) return <div style={{ color: error ? T.negative : T.muted, fontSize: 12.5 }}>{error || 'Loading…'}</div>

  const form = (id: number | 'new', f: typeof blank) => (
    <div style={{ background: T.surface2, borderRadius: 8, padding: 12, margin: '6px 0' }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: 10 }}>
        <Field name="Kind">
          <select style={input} value={f.kind} onChange={e => setEdit({ id, f: { ...f, kind: e.target.value } })}>
            {d.kinds.map(k => <option key={k.id} value={k.id}>{k.label}</option>)}
          </select>
        </Field>
        <Field name="Benefit"><input autoFocus style={input} maxLength={120} value={f.title} onChange={e => setEdit({ id, f: { ...f, title: e.target.value } })} placeholder="e.g. 4 lounge visits a year" /></Field>
        <Field name="Worth a year (₹, optional)"><input style={input} inputMode="numeric" value={f.value_yr} onChange={e => setEdit({ id, f: { ...f, value_yr: e.target.value.replace(/\D/g, '') } })} /></Field>
        <Field name="Where it is from"><input style={input} maxLength={160} value={f.source} onChange={e => setEdit({ id, f: { ...f, source: e.target.value } })} placeholder="card terms, welcome letter…" /></Field>
      </div>
      <Field name="Details, conditions, caps"><input style={input} maxLength={600} value={f.detail} onChange={e => setEdit({ id, f: { ...f, detail: e.target.value } })} /></Field>
      <button style={btn(true)} onClick={() => {
        const body = { kind: f.kind, title: f.title, detail: f.detail, source: f.source, value_yr: Number(f.value_yr || 0) }
        run(id === 'new' ? addPerk(cardId, { ...body, source: f.source || 'Added by you' }) : updatePerk(id, body))
      }}>Save</button>{' '}
      <button style={btn()} onClick={() => setEdit(null)}>Cancel</button>
    </div>
  )

  const row = (p: Perk) => (
    edit?.id === p.id ? <div key={p.id}>{form(p.id, edit.f)}</div> : (
      <div key={p.id} style={{ display: 'flex', justifyContent: 'space-between', gap: 12, padding: '7px 0', borderTop: `1px solid ${T.border}` }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 13.5, fontWeight: 600 }}>
            {p.title}
            {!p.checked && <span title="From published or built-in terms. Confirm it against your card's own terms."
              style={{ marginLeft: 8, fontSize: 10, color: T.warn, border: `1px solid ${T.warn}`, borderRadius: 10, padding: '0 7px', fontWeight: 600 }}>TO CHECK</span>}
            {p.value_yr > 0 && <span style={{ marginLeft: 8, fontSize: 11.5, color: T.positive, fontWeight: 500 }}>about {fmt(p.value_yr)} a year</span>}
          </div>
          {p.detail && <div style={{ fontSize: 12.5, color: T.muted, marginTop: 2 }}>{p.detail}</div>}
          {p.source && <div style={{ fontSize: 11, color: T.muted, opacity: 0.8, marginTop: 2 }}>{p.source}</div>}
        </div>
        {editable && (
          <div style={{ display: 'flex', gap: 5, alignItems: 'flex-start', flexShrink: 0 }}>
            {!p.checked && <button style={smallBtn} onClick={() => run(updatePerk(p.id, { checked: true }))}>Mark checked</button>}
            <button style={smallBtn} onClick={() => setEdit({ id: p.id, f: { kind: p.kind, title: p.title, detail: p.detail, source: p.source, value_yr: p.value_yr ? String(p.value_yr) : '' } })}>Edit</button>
            <button style={smallBtn} onClick={() => { if (confirm(`Remove "${p.title}" from this card's benefits?`)) run(deletePerk(p.id)) }}>Remove</button>
          </div>
        )}
      </div>
    )
  )

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 10, flexWrap: 'wrap', marginBottom: 6 }}>
        <span style={{ ...label, fontSize: 12.5, letterSpacing: 0.8 }}>Benefits</span>
        <span style={{ fontSize: 11.5, color: T.muted }}>
          {d.perks.length === 0 ? 'none written down yet' : <>{d.perks.length} written down{d.to_check > 0 && <> · <span style={{ color: T.warn }}>{d.to_check} to check</span></>}{d.value_yr > 0 && ` · about ${fmt(d.value_yr)} a year in perks`}</>}
        </span>
      </div>
      {error && <div style={{ color: T.negative, fontSize: 12.5, marginBottom: 6 }}>{error}</div>}
      {d.kinds.map(k => {
        const items = d.perks.filter(p => p.kind === k.id)
        return items.length === 0 ? null : (
          <div key={k.id} style={{ marginTop: 10 }}>
            <div style={{ ...label, fontSize: 10.5 }}>{k.label}</div>
            {items.map(row)}
          </div>
        )
      })}
      {editable && (edit?.id === 'new' ? form('new', edit.f) : (
        <button style={{ ...smallBtn, marginTop: 12 }} onClick={() => setEdit({ id: 'new', f: { ...blank } })}>+ Add a benefit</button>
      ))}
      {!editable && d.perks.length === 0 && <div style={{ fontSize: 12.5, color: T.muted }}>Add this card's benefits in Admin → Cards.</div>}
    </div>
  )
}
