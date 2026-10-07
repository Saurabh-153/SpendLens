import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  archiveSubcategory, createSubcategory, deleteSubcategory, getCategories, getReview, getSubcategories, mapReview,
  reorderSubcategories, restoreSubcategory, updateSubcategory,
  type Category, type ReviewItem, type Subcategory,
} from '../../api'
import { currentMonth, monthLabel, shiftMonth } from '../../months'
import { T, fmtFull } from '../../theme'
import { AdminHeader, dangerBtn, smallBtn, btn, Card, Field, input, label, Modal } from '../ui'

type Tab = 'active' | 'archived' | 'review'

export default function Subcategories() {
  const [cats, setCats] = useState<Category[]>([])
  const [allSubs, setAllSubs] = useState<Subcategory[]>([])
  const [review, setReview] = useState<ReviewItem[]>([])
  const [catId, setCatId] = useState<number | null>(null)
  const [tab, setTab] = useState<Tab>(() => (new URLSearchParams(location.search).get('tab') === 'review' ? 'review' : 'active'))
  const [msg, setMsg] = useState<{ text: string; error?: boolean } | null>(null)
  const [dialog, setDialog] = useState<{ kind: 'add' } | { kind: 'edit' | 'archive' | 'delete'; sub: Subcategory } | null>(null)
  const [reviewCat, setReviewCat] = useState<number | 0>(0)
  const [pick, setPick] = useState<Record<string, number>>({})

  const load = useCallback(async () => {
    try {
      const [c, s, r] = await Promise.all([getCategories(), getSubcategories(), getReview()])
      const usable = c.filter(x => x.status !== 'scheduled')
      setCats(usable); setAllSubs(s); setReview(r)
      setCatId(id => id ?? usable.find(x => s.some(y => y.category_id === x.id))?.id ?? usable[0]?.id ?? null)
    } catch (e) { setMsg({ text: (e as Error).message, error: true }) }
  }, [])
  useEffect(() => { load() }, [load])

  const run = async (p: Promise<unknown>, ok?: string) => {
    try { await p; setMsg(ok ? { text: ok } : null); await load() } catch (e) { setMsg({ text: (e as Error).message, error: true }) }
  }

  const subs = useMemo(() => allSubs.filter(s => s.category_id === catId), [allSubs, catId])
  const shown = subs.filter(s => (tab === 'archived' ? s.status === 'archived' : s.status !== 'archived'))
  const reviewShown = review.filter(r => !reviewCat || r.category_id === reviewCat)
  const tabBtn = (id: Tab, text: string, n: number) => (
    <button key={id} onClick={() => setTab(id)} style={{
      background: 'none', border: 'none', cursor: 'pointer', padding: '10px 16px', fontSize: 13.5, fontWeight: 500,
      color: tab === id ? T.text : T.muted, borderBottom: `2px solid ${tab === id ? T.accent : 'transparent'}`,
    }}>{text} <span style={{ opacity: 0.6 }}>({n})</span></button>
  )

  const move = (s: Subcategory, dir: -1 | 1) => {
    const ids = allSubs.map(x => x.id)
    const group = shown.map(x => x.id)
    const i = group.indexOf(s.id), j = i + dir
    if (j < 0 || j >= group.length) return
    const a = ids.indexOf(group[i]), b = ids.indexOf(group[j]);
    [ids[a], ids[b]] = [ids[b], ids[a]]
    run(reorderSubcategories(ids))
  }

  return (
    <div>
      <AdminHeader title="Sub-categories" hint="Break a category down (Transport into Fuel, Cab & Auto, Parking). Archiving works like categories: history never changes." />

      <div style={{ display: 'flex', gap: 4, borderBottom: `1px solid ${T.border}`, marginBottom: 16, alignItems: 'center' }}>
        {tabBtn('active', 'Active', subs.filter(s => s.status !== 'archived').length)}
        {tabBtn('archived', 'Archived', subs.filter(s => s.status === 'archived').length)}
        {tabBtn('review', 'Needs review', review.length)}
        <div style={{ flex: 1 }} />
        {tab !== 'review' && <button style={{ ...btn(true), marginBottom: 6 }} disabled={!catId} onClick={() => setDialog({ kind: 'add' })}>+ Add sub-category</button>}
      </div>

      {tab !== 'review' ? (
        <label style={{ display: 'inline-block', marginBottom: 14 }}>
          <div style={{ ...label, marginBottom: 5 }}>Category</div>
          <select style={{ ...input, width: 240 }} value={catId ?? ''} onChange={e => setCatId(Number(e.target.value))}>
            {cats.map(c => <option key={c.id} value={c.id}>{c.icon} {c.name} ({allSubs.filter(s => s.category_id === c.id && s.status !== 'archived').length})</option>)}
          </select>
        </label>
      ) : (
        <label style={{ display: 'inline-block', marginBottom: 14 }}>
          <div style={{ ...label, marginBottom: 5 }}>Show category</div>
          <select style={{ ...input, width: 240 }} value={reviewCat} onChange={e => setReviewCat(Number(e.target.value))}>
            <option value={0}>All categories ({review.length})</option>
            {cats.filter(c => review.some(r => r.category_id === c.id)).map(c => (
              <option key={c.id} value={c.id}>{c.icon} {c.name} ({review.filter(r => r.category_id === c.id).length})</option>
            ))}
          </select>
        </label>
      )}

      {msg && <div style={{ fontSize: 12.5, marginBottom: 12, color: msg.error ? T.negative : T.positive }}>{msg.text}</div>}

      {tab !== 'review' && (
        <Card style={{ padding: 0, overflow: 'hidden' }}>
          {shown.length === 0 && <div style={{ padding: 20, color: T.muted, fontSize: 13 }}>No {tab} sub-categories for this category.</div>}
          {shown.map((s, i) => (
            <div key={s.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '9px 16px', borderTop: i ? `1px solid ${T.hairline}` : undefined }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 600, fontSize: 13.5 }}>{s.name}</div>
                <div style={{ fontSize: 11.5, color: T.muted, marginTop: 2 }}>
                  {s.start_month > '0000-00' && <>from {monthLabel(s.start_month)} · </>}
                  {s.end_month ? <>last month {monthLabel(s.end_month)}</> : <>no end month</>}
                  {s.has_data ? '' : ' · unused'}
                </div>
              </div>
              {tab === 'active' && !s.end_month && (
                <>
                  <button style={smallBtn} onClick={() => move(s, -1)}>↑</button>
                  <button style={smallBtn} onClick={() => move(s, 1)}>↓</button>
                </>
              )}
              <button style={smallBtn} onClick={() => setDialog({ kind: 'edit', sub: s })}>Rename</button>
              {s.end_month && <button style={smallBtn} onClick={() => run(restoreSubcategory(s.id), `${s.name} restored`)}>Restore</button>}
              {!s.end_month && <button style={smallBtn} onClick={() => setDialog({ kind: 'archive', sub: s })}>Archive</button>}
              {!s.has_data && <button style={dangerBtn} onClick={() => setDialog({ kind: 'delete', sub: s })}>Delete</button>}
            </div>
          ))}
        </Card>
      )}

      {tab === 'review' && (
        <Card style={{ padding: 0, overflow: 'hidden' }}>
          <div style={{ padding: '12px 18px', fontSize: 12.5, color: T.muted }}>
            These entries could not be matched automatically. Choosing a sub-category applies to every entry with the same note and is remembered for future entries.
          </div>
          {reviewShown.length === 0 && <div style={{ padding: 20, color: T.positive, fontSize: 13 }}>Nothing left to review.</div>}
          {reviewShown.map(r => {
            const key = `${r.category_id}|${r.note}`
            const options = allSubs.filter(s => s.category_id === r.category_id && s.status !== 'archived')
            return (
              <div key={key} style={{ display: 'grid', gridTemplateColumns: '150px 1fr 70px 100px 200px 70px', gap: 10, alignItems: 'center', padding: '9px 16px', borderTop: `1px solid ${T.hairline}`, fontSize: 13 }}>
                <span style={{ color: T.muted }}>{r.category}</span>
                <span style={{ fontWeight: 600 }}>{r.note || <i style={{ color: T.muted, fontWeight: 400 }}>(no note)</i>}</span>
                <span style={{ color: T.muted, textAlign: 'right' }}>{r.count}×</span>
                <span style={{ textAlign: 'right' }}>{r.total < 0 ? '-' : ''}{fmtFull(r.total)}</span>
                <select style={input} value={pick[key] ?? ''} onChange={e => setPick({ ...pick, [key]: Number(e.target.value) })}>
                  <option value="">Choose…</option>
                  {options.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
                <button style={{ ...btn(true), padding: '6px 10px', fontSize: 12, opacity: pick[key] ? 1 : 0.5 }} disabled={!pick[key]}
                  onClick={() => run(mapReview(r.category_id, r.note, pick[key]).then(x => setMsg({ text: `${x.updated} entr${x.updated === 1 ? 'y' : 'ies'} updated` })))}>Map</button>
              </div>
            )
          })}
        </Card>
      )}

      {dialog?.kind === 'add' && catId && (
        <NameDialog title="Add sub-category" withStart onClose={() => setDialog(null)}
          onSave={(name, start) => { setDialog(null); run(createSubcategory(catId, name, start), 'Sub-category added') }} />
      )}
      {dialog?.kind === 'edit' && (
        <NameDialog title="Rename sub-category" initial={dialog.sub.name} onClose={() => setDialog(null)}
          onSave={name => { const s = dialog.sub; setDialog(null); run(updateSubcategory(s.id, name), 'Renamed (applies to every month)') }} />
      )}
      {dialog?.kind === 'archive' && (
        <ArchiveDialog sub={dialog.sub} onClose={() => setDialog(null)}
          onConfirm={async month => {
            const s = dialog.sub
            setDialog(null)
            try {
              const r = await archiveSubcategory(s.id, month)
              setMsg({ text: `${s.name} archived from ${monthLabel(month)}.` + (r.months_with_data_after ? ` ${r.months_with_data_after} later month(s) already hold entries and keep showing it.` : '') })
              await load()
            } catch (e) { setMsg({ text: (e as Error).message, error: true }) }
          }} />
      )}
      {dialog?.kind === 'delete' && (
        <Modal title="Delete sub-category?" onClose={() => setDialog(null)}>
          <p style={{ fontSize: 13, color: T.muted, marginBottom: 16 }}><b style={{ color: T.text }}>{dialog.sub.name}</b> has never been used, so it can be removed completely.</p>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
            <button style={btn()} onClick={() => setDialog(null)}>Cancel</button>
            <button style={{ ...btn(), background: T.danger, borderColor: T.danger, color: '#fff' }}
              onClick={() => { const id = dialog.sub.id; setDialog(null); run(deleteSubcategory(id), 'Deleted') }}>Delete</button>
          </div>
        </Modal>
      )}
    </div>
  )
}

function NameDialog({ title, initial = '', withStart, onClose, onSave }: {
  title: string; initial?: string; withStart?: boolean; onClose: () => void; onSave: (name: string, start: string) => void
}) {
  const [name, setName] = useState(initial)
  const [start, setStart] = useState(currentMonth())
  return (
    <Modal title={title} onClose={onClose}>
      <form onSubmit={e => { e.preventDefault(); if (name.trim()) onSave(name.trim(), start) }}>
        <Field name="Name"><input style={input} autoFocus value={name} onChange={e => setName(e.target.value)} /></Field>
        {withStart && <Field name="Starts from"><input style={input} type="month" value={start} onChange={e => setStart(e.target.value)} /></Field>}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button type="button" style={btn()} onClick={onClose}>Cancel</button>
          <button type="submit" style={{ ...btn(true), opacity: name.trim() && start ? 1 : 0.5 }} disabled={!name.trim() || !start}>Save</button>
        </div>
      </form>
    </Modal>
  )
}

function ArchiveDialog({ sub, onClose, onConfirm }: { sub: Subcategory; onClose: () => void; onConfirm: (m: string) => void }) {
  const next = shiftMonth(currentMonth(), 1)
  const [month, setMonth] = useState(next > sub.start_month ? next : shiftMonth(sub.start_month, 1))
  return (
    <Modal title={`Archive ${sub.name}`} onClose={onClose}>
      <Field name="Hide from"><input style={input} type="month" value={month} onChange={e => setMonth(e.target.value)} /></Field>
      <p style={{ fontSize: 12.5, color: T.muted, lineHeight: 1.6, marginBottom: 16 }}>
        {month ? <>Stays available, with its amounts, up to <b style={{ color: T.text }}>{monthLabel(shiftMonth(month, -1))}</b>; cannot be chosen for new entries from <b style={{ color: T.text }}>{monthLabel(month)}</b>. Restore any time.</> : 'Pick a month.'}
      </p>
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
        <button style={btn()} onClick={onClose}>Cancel</button>
        <button style={{ ...btn(true), opacity: month ? 1 : 0.5 }} disabled={!month} onClick={() => onConfirm(month)}>Archive</button>
      </div>
    </Modal>
  )
}
