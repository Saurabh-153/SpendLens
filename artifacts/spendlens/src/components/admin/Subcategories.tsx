import { useCallback, useEffect, useState } from 'react'
import { getCategories, getReview, getSubcategories, mapReview, type Category, type ReviewItem, type Subcategory } from '../../api'
import { T, fmtFull } from '../../theme'
import { AdminHeader, btn, Card, input, label } from '../ui'

export default function Subcategories() {
  const [cats, setCats] = useState<Category[]>([])
  const [allSubs, setAllSubs] = useState<Subcategory[]>([])
  const [review, setReview] = useState<ReviewItem[]>([])
  const [msg, setMsg] = useState<{ text: string; error?: boolean } | null>(null)
  const [reviewCat, setReviewCat] = useState<number | 0>(0)
  const [pick, setPick] = useState<Record<string, number>>({})

  const load = useCallback(async () => {
    try {
      const [c, s, r] = await Promise.all([getCategories(), getSubcategories(), getReview()])
      setCats(c.filter(x => x.status !== 'scheduled')); setAllSubs(s); setReview(r)
    } catch (e) { setMsg({ text: (e as Error).message, error: true }) }
  }, [])
  useEffect(() => { load() }, [load])

  const run = async (p: Promise<unknown>) => {
    try { await p; await load() } catch (e) { setMsg({ text: (e as Error).message, error: true }) }
  }

  const reviewShown = review.filter(r => !reviewCat || r.category_id === reviewCat)

  return (
    <div>
      <AdminHeader title="Review entries" hint="Manage sub-categories under Categories. Entries that could not be matched to one automatically are listed here." />

      <label style={{ display: 'inline-block', marginBottom: 14 }}>
        <div style={{ ...label, marginBottom: 5 }}>Show category</div>
        <select style={{ ...input, width: 240 }} value={reviewCat} onChange={e => setReviewCat(Number(e.target.value))}>
          <option value={0}>All categories ({review.length})</option>
          {cats.filter(c => review.some(r => r.category_id === c.id)).map(c => (
            <option key={c.id} value={c.id}>{c.icon} {c.name} ({review.filter(r => r.category_id === c.id).length})</option>
          ))}
        </select>
      </label>

      {msg && <div style={{ fontSize: 12.5, marginBottom: 12, color: msg.error ? T.negative : T.positive }}>{msg.text}</div>}

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
    </div>
  )
}
