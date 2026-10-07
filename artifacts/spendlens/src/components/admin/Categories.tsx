import { useCallback, useEffect, useState } from 'react'
import {
  archiveCategory, createCategory, deleteCategory, getCategories, getCategoryUsage, reorderCategories, restoreCategory, updateCategory,
  type Category, type CategoryUsage,
} from '../../api'
import { currentMonth, monthLabel, shiftMonth } from '../../months'
import { T, fmtFull } from '../../theme'
import { AdminHeader, dangerBtn, smallBtn, btn, Card, Field, input, label, Modal } from '../ui'

type Tab = 'active' | 'scheduled' | 'archived'
const TAB_TEXT: Record<Tab, string> = { active: 'Active', scheduled: 'Scheduled', archived: 'Archived' }
const EMOJIS = ['🏠', '⚡', '🛒', '🥛', '🍽️', '🚗', '💊', '🎒', '🛍️', '🎁', '✈️', '📱', '💼', '🐶', '🏋️', '📦']

export default function Categories() {
  const [cats, setCats] = useState<Category[]>([])
  const [tab, setTab] = useState<Tab>('active')
  const [msg, setMsg] = useState<{ text: string; error?: boolean } | null>(null)
  const [editing, setEditing] = useState<Category | 'new' | null>(null)
  const [archiving, setArchiving] = useState<Category | null>(null)
  const [deleting, setDeleting] = useState<Category | null>(null)

  const load = useCallback(() => getCategories().then(setCats).catch(e => setMsg({ text: e.message, error: true })), [])
  useEffect(() => { load() }, [load])

  const run = async (p: Promise<unknown>, ok?: string) => {
    try { await p; setMsg(ok ? { text: ok } : null); await load() } catch (e) { setMsg({ text: (e as Error).message, error: true }) }
  }

  const shown = cats.filter(c => c.status === tab)
  const today = currentMonth()

  const move = (c: Category, dir: -1 | 1) => {
    const ids = cats.map(x => x.id)
    const group = shown.map(x => x.id)
    const i = group.indexOf(c.id), j = i + dir
    if (j < 0 || j >= group.length) return
    // swap the two neighbours in the full ordering, leave everything else in place
    const a = ids.indexOf(group[i]), b = ids.indexOf(group[j]);
    [ids[a], ids[b]] = [ids[b], ids[a]]
    run(reorderCategories(ids))
  }

  return (
    <div>
      <AdminHeader title="Categories" hint="Archiving hides a category from a month onward. Earlier months keep their amounts."
        action={<button style={btn(true)} onClick={() => setEditing('new')}>+ Add category</button>} />

      <div style={{ display: 'flex', gap: 4, borderBottom: `1px solid ${T.border}`, marginBottom: 16 }}>
        {(Object.keys(TAB_TEXT) as Tab[]).map(t => (
          <button key={t} onClick={() => setTab(t)} style={{
            background: 'none', border: 'none', cursor: 'pointer', padding: '10px 16px', fontSize: 13.5, fontWeight: 500,
            color: tab === t ? T.text : T.muted, borderBottom: `2px solid ${tab === t ? T.accent : 'transparent'}`,
          }}>{TAB_TEXT[t]} <span style={{ opacity: 0.6 }}>({cats.filter(c => c.status === t).length})</span></button>
        ))}
      </div>

      {msg && <div style={{ fontSize: 12.5, marginBottom: 12, color: msg.error ? T.negative : T.positive }}>{msg.text}</div>}

      <Card style={{ padding: 0, overflow: 'hidden' }}>
        {shown.length === 0 && <div style={{ padding: 20, color: T.muted, fontSize: 13 }}>No {tab} categories.</div>}
        {shown.map((c, i) => (
          <div key={c.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '9px 16px', borderTop: i ? `1px solid ${T.hairline}` : undefined }}>
            <span style={{ width: 9, height: 9, borderRadius: '50%', background: c.color, flexShrink: 0 }} />
            <span style={{ fontSize: 18, width: 26 }}>{c.icon}</span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 600, fontSize: 13.5 }}>{c.name}</div>
              <div style={{ fontSize: 11.5, color: T.muted, marginTop: 2 }}>
                {c.start_month > '0000-00' && <>from {monthLabel(c.start_month)} · </>}
                {c.end_month ? <>last month {monthLabel(c.end_month)}</> : <>no end month</>}
                {' · '}target {c.target_pct.toFixed(2)}%{c.hint && <> · {c.hint}</>}
              </div>
            </div>
            {tab === 'active' && !c.end_month && (
              <>
                <button style={smallBtn} title="Move up" onClick={() => move(c, -1)}>↑</button>
                <button style={smallBtn} title="Move down" onClick={() => move(c, 1)}>↓</button>
              </>
            )}
            <button style={smallBtn} onClick={() => setEditing(c)}>Edit</button>
            {c.end_month && (c.status === 'archived' || c.end_month >= today) && (
              <button style={smallBtn} onClick={() => run(restoreCategory(c.id), `${c.name} restored`)}>Restore</button>
            )}
            {!c.end_month && c.status !== 'archived' && (
              <button style={smallBtn} onClick={() => setArchiving(c)}>Archive</button>
            )}
            <button style={dangerBtn} onClick={() => setDeleting(c)}>Delete</button>
          </div>
        ))}
      </Card>

      {editing && (
        <CategoryDialog category={editing === 'new' ? null : editing} onClose={() => setEditing(null)}
          onSave={async input => {
            const target = editing
            setEditing(null)
            await run(
              target === 'new' ? createCategory(input) : updateCategory(target.id, input),
              target === 'new' ? 'Category added' : 'Category updated',
            )
          }} />
      )}
      {archiving && (
        <ArchiveDialog category={archiving} onClose={() => setArchiving(null)}
          onConfirm={async month => {
            const c = archiving
            setArchiving(null)
            try {
              const r = await archiveCategory(c.id, month)
              setMsg({ text: `${c.name} archived from ${monthLabel(month)}.` + (r.months_with_data_after ? ` ${r.months_with_data_after} later month(s) already contain entries and will still show it.` : '') })
              await load()
            } catch (e) { setMsg({ text: (e as Error).message, error: true }) }
          }} />
      )}
      {deleting && (
        <DeleteDialog category={deleting} onClose={() => setDeleting(null)}
          onDelete={() => { const id = deleting.id; setDeleting(null); run(deleteCategory(id), 'Category deleted') }}
          onArchive={() => { const c = deleting; setDeleting(null); setArchiving(c) }} />
      )}
    </div>
  )
}

function CategoryDialog({ category, onClose, onSave }: {
  category: Category | null; onClose: () => void
  onSave: (c: { name: string; icon: string; color: string; hint: string; start_month: string; target_pct: number }) => void
}) {
  const [name, setName] = useState(category?.name ?? '')
  const [icon, setIcon] = useState(category?.icon ?? '📦')
  const [color, setColor] = useState(category?.color ?? '#6c63ff')
  const [hint, setHint] = useState(category?.hint ?? '')
  const [start, setStart] = useState(currentMonth())
  const [target, setTarget] = useState('0')

  return (
    <Modal title={category ? 'Edit category' : 'Add category'} onClose={onClose}>
      <Field name="Name"><input style={input} autoFocus value={name} onChange={e => setName(e.target.value)} /></Field>
      <Field name="Icon">
        <input style={{ ...input, marginBottom: 8 }} value={icon} onChange={e => setIcon(e.target.value)} />
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
          {EMOJIS.map(e => (
            <button key={e} type="button" onClick={() => setIcon(e)} style={{ ...btn(), padding: '3px 7px', fontSize: 16, borderColor: icon === e ? T.accent : T.border }}>{e}</button>
          ))}
        </div>
      </Field>
      <Field name="Colour">
        <input type="color" value={color} onChange={e => setColor(e.target.value)} style={{ width: 54, height: 32, background: 'none', border: `1px solid ${T.border}`, borderRadius: 6 }} />
      </Field>
      <Field name="Description (optional)"><input style={input} value={hint} onChange={e => setHint(e.target.value)} /></Field>
      {!category && (
        <div style={{ display: 'flex', gap: 10 }}>
          <div style={{ flex: 1 }}><Field name="Starts from"><input style={input} type="month" value={start} onChange={e => setStart(e.target.value)} /></Field></div>
          <div style={{ flex: 1 }}><Field name="Target % of income"><input style={input} type="number" min={0} max={100} value={target} onChange={e => setTarget(e.target.value)} /></Field></div>
        </div>
      )}
      <div style={{ ...label, textTransform: 'none', letterSpacing: 0, fontWeight: 400, marginBottom: 14, lineHeight: 1.5 }}>
        {category
          ? 'Name, icon and colour are labels: changes show in every month, no amounts change.'
          : 'Earlier months will not show this category.'}
      </div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
        <button style={btn()} onClick={onClose}>Cancel</button>
        <button style={{ ...btn(true), opacity: name.trim() && start ? 1 : 0.5 }} disabled={!name.trim() || !start}
          onClick={() => onSave({ name: name.trim(), icon: icon || '📦', color, hint: hint.trim(), start_month: start, target_pct: Math.min(100, Math.max(0, parseInt(target) || 0)) })}>
          Save
        </button>
      </div>
    </Modal>
  )
}

function ArchiveDialog({ category, onClose, onConfirm }: { category: Category; onClose: () => void; onConfirm: (month: string) => void }) {
  const next = shiftMonth(currentMonth(), 1)
  const [month, setMonth] = useState(next > category.start_month ? next : shiftMonth(category.start_month, 1))
  return (
    <Modal title={`Archive ${category.name}`} onClose={onClose}>
      <Field name="Hide from">
        <input style={input} type="month" min={shiftMonth(category.start_month === '0000-00' ? '2000-01' : category.start_month, 1)} value={month} onChange={e => setMonth(e.target.value)} />
      </Field>
      <p style={{ fontSize: 12.5, color: T.muted, lineHeight: 1.6, marginBottom: 16 }}>
        {month ? <>
          The category stays visible, with all its amounts, in <b style={{ color: T.text }}>{monthLabel(shiftMonth(month, -1))}</b> and every earlier month,
          and disappears from <b style={{ color: T.text }}>{monthLabel(month)}</b> onward. The default is next month so this month's entries stay complete.
          You can restore it any time.
        </> : 'Pick a month.'}
      </p>
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
        <button style={btn()} onClick={onClose}>Cancel</button>
        <button style={{ ...btn(true), opacity: month ? 1 : 0.5 }} disabled={!month} onClick={() => onConfirm(month)}>Archive</button>
      </div>
    </Modal>
  )
}

const dayText = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) : '')

/** Asks what a category holds before anything is deleted. One with expenses is never deleted (they would be left
 *  without a category): the dialog says how much is in it and offers to archive it instead. */
function DeleteDialog({ category, onClose, onDelete, onArchive }: { category: Category; onClose: () => void; onDelete: () => void; onArchive: () => void }) {
  const [u, setU] = useState<CategoryUsage | null>(null)
  const [error, setError] = useState('')
  const [typed, setTyped] = useState('')
  useEffect(() => { getCategoryUsage(category.id).then(setU).catch(e => setError(e.message)) }, [category.id])

  return (
    <Modal title={u && u.entries > 0 ? `${category.name} has expenses` : 'Delete category?'} onClose={onClose}>
      {error && <p style={{ color: T.negative, fontSize: 13 }}>{error}</p>}
      {!u && !error && <p style={{ color: T.muted, fontSize: 13 }}>Checking what it holds…</p>}
      {u && u.entries > 0 && (
        <>
          <div style={{ background: 'rgba(245,158,11,.1)', border: `1px solid ${T.warn}55`, borderRadius: 8, padding: '10px 12px', fontSize: 13, marginBottom: 12 }}>
            <b>{u.entries}</b> expense{u.entries === 1 ? '' : 's'} totalling <b>{fmtFull(u.total)}</b>, across {u.months} month{u.months === 1 ? '' : 's'}
            {u.first && <> ({dayText(u.first)} to {dayText(u.last)})</>}.
          </div>
          <p style={{ fontSize: 13, color: T.muted, marginBottom: 16 }}>
            It can't be deleted: those expenses would be left with no category and drop out of every month, dashboard and total.
            Archive it instead. Archiving hides it from the month you choose onward and keeps every earlier month exactly as it was.
          </p>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
            <button style={btn()} onClick={onClose}>Cancel</button>
            {category.status !== 'archived' && !category.end_month && <button style={btn(true)} onClick={onArchive}>Archive instead…</button>}
          </div>
        </>
      )}
      {u && u.entries === 0 && (
        <>
          <p style={{ fontSize: 13, color: T.muted, marginBottom: 10 }}>
            <b style={{ color: T.text }}>{category.name}</b> has no expenses in any month, so it can be removed completely.
            {(u.subcategories > 0 || u.target_changes > 0) && <> This also removes its {[u.subcategories > 0 && `${u.subcategories} sub-categor${u.subcategories === 1 ? 'y' : 'ies'}`, u.target_changes > 0 && `target history (${u.target_changes} entr${u.target_changes === 1 ? 'y' : 'ies'})`].filter(Boolean).join(' and ')}.</>}
            {' '}This can't be undone.
          </p>
          <p style={{ fontSize: 12.5, color: T.muted, marginBottom: 6 }}>Type the name to confirm:</p>
          <input autoFocus style={{ ...input, marginBottom: 16 }} value={typed} placeholder={category.name} onChange={e => setTyped(e.target.value)} />
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
            <button style={btn()} onClick={onClose}>Cancel</button>
            <button style={{ ...btn(), background: T.danger, borderColor: T.danger, color: '#fff', opacity: typed.trim().toLowerCase() === category.name.toLowerCase() ? 1 : 0.4 }}
              disabled={typed.trim().toLowerCase() !== category.name.toLowerCase()} onClick={onDelete}>Delete</button>
          </div>
        </>
      )}
    </Modal>
  )
}
