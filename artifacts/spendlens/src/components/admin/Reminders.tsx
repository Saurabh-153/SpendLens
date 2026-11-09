import { useCallback, useEffect, useState } from 'react'
import {
  createReminderCategory, deleteReminderCategory, getReminderCategories, getReminders, getReminderSettings, getReminderSips, getTrackers, getVacations,
  reorderTrackers, setReminderSipVisibility, updateReminder, updateReminderCategory, updateReminderSettings,
  type Reminder, type ReminderCategory, type ReminderSettings, type SipVisibility, type Tracker, type Vacation,
} from '../../api'
import { T, fmtFull } from '../../theme'
import ReminderEditor from '../ReminderEditor'
import TrackerEditor, { weekdayText } from '../TrackerEditor'
import VacationEditor from '../VacationEditor'
import { Swatches, Switch, REMINDER_PALETTE, REPEAT_TEXT, ord, parseTime, vacationRange } from '../reminderUi'
import { AdminHeader, btn, Card, dangerBtn, Field, input, Modal, smallBtn } from '../ui'

type Msg = { text: string; error?: boolean } | null

export default function Reminders() {
  const [cats, setCats] = useState<ReminderCategory[]>([])
  const [rems, setRems] = useState<Reminder[]>([])
  const [settings, setSettings] = useState<ReminderSettings | null>(null)
  const [sips, setSips] = useState<SipVisibility[]>([])
  const [vacations, setVacations] = useState<Vacation[]>([])
  const [vacEdit, setVacEdit] = useState<Vacation | 'new' | null>(null)
  const [trackers, setTrackers] = useState<Tracker[]>([])
  const [trackEdit, setTrackEdit] = useState<Tracker | 'new' | null>(null)
  const [timeText, setTimeText] = useState('')
  const [msg, setMsg] = useState<Msg>(null)
  const [catDialog, setCatDialog] = useState<ReminderCategory | 'new' | null>(null)
  const [deleting, setDeleting] = useState<ReminderCategory | null>(null)
  const [editing, setEditing] = useState<Reminder | 'new' | null>(null)

  const load = useCallback(() => Promise.all([getReminderCategories(), getReminders(), getReminderSettings(), getReminderSips(), getVacations(), getTrackers().catch(() => [] as Tracker[])])
    .then(([c, r, s, p, v, t]) => {
      setCats(c); setRems(r); setSettings(s); setTimeText(s.nudge_time); setSips(p)
      setVacations([...v].sort((a, b) => a.start_date.localeCompare(b.start_date))); setTrackers([...t].sort((a, b) => a.sort_order - b.sort_order))
    })
    .catch(e => setMsg({ text: e.message, error: true })), [])
  useEffect(() => { load() }, [load])

  const run = async (p: Promise<unknown>, ok?: string) => {
    try { await p; setMsg(ok ? { text: ok } : null); await load() } catch (e) { setMsg({ text: (e as Error).message, error: true }) }
  }

  const moveTracker = (i: number, dir: -1 | 1) => {
    const j = i + dir
    if (j < 0 || j >= trackers.length) return
    const ids = trackers.map(t => t.id);
    [ids[i], ids[j]] = [ids[j], ids[i]]
    run(reorderTrackers(ids))
  }

  const saveTime = () => {
    if (!settings) return
    const t = parseTime(timeText)
    if (!t) { setTimeText(settings.nudge_time); setMsg({ text: 'Use a 24-hour time such as 21:00.', error: true }); return }
    if (t !== settings.nudge_time) run(updateReminderSettings({ nudge_time: t }), `Nudge set to ${t}`)
    else setTimeText(t)
  }

  return (
    <div>
      <AdminHeader title="Reminders" hint="Bills, card dates and SIPs shown on the Expense calendar and in the calendar link you subscribe to."
        action={<button style={btn(true)} onClick={() => setEditing('new')}>+ Add reminder</button>} />

      {msg && <div role={msg.error ? 'alert' : 'status'} style={{ fontSize: 12.5, marginBottom: 12, color: msg.error ? T.negative : T.positive }}>{msg.text}</div>}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 16, alignItems: 'start', marginBottom: 16 }}>
        <Card>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <h3 style={{ fontSize: 15, flex: 1 }}>Categories</h3>
            <button style={smallBtn} onClick={() => setCatDialog('new')}>+ Add category</button>
          </div>
          <p style={{ color: T.muted, fontSize: 12.5, marginBottom: 10, lineHeight: 1.5 }}>Group reminders any way you like. The colour is used on the calendar.</p>
          {cats.map((c, i) => (
            <CategoryRow key={`${c.id}:${c.name}`} cat={c} first={i === 0} last={cats.length < 2}
              onColour={() => setCatDialog(c)}
              onRename={name => run(updateReminderCategory(c.id, { name }), 'Renamed')}
              onDelete={() => setDeleting(c)} />
          ))}
        </Card>

        <Card>
          <h3 style={{ fontSize: 15, marginBottom: 4 }}>Evening nudge</h3>
          <p style={{ color: T.muted, fontSize: 12.5, marginBottom: 12, lineHeight: 1.5 }}>A daily event in your calendar that asks you to log the day’s expenses.</p>
          {settings && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <Switch checked={settings.nudge_on} label="Evening nudge on"
                onChange={v => run(updateReminderSettings({ nudge_on: v }), v ? 'Nudge on' : 'Nudge off')} />
              <span style={{ flex: 1, fontSize: 13 }}>Remind me at</span>
              <input style={{ ...input, width: 84 }} aria-label="Nudge time, 24 hour" value={timeText} disabled={!settings.nudge_on}
                onChange={e => setTimeText(e.target.value)} onBlur={saveTime} onKeyDown={e => { if (e.key === 'Enter') saveTime() }} />
            </div>
          )}
        </Card>

        <Card>
          <h3 style={{ fontSize: 15, marginBottom: 4 }}>SIPs in reminders</h3>
          <p style={{ color: T.muted, fontSize: 12.5, marginBottom: 10, lineHeight: 1.5 }}>
            Turn a SIP off to leave it out of the calendar and the calendar link. Holdings still applies it every month.
          </p>
          {sips.length === 0 && <div style={{ fontSize: 12.5, color: T.muted }}>No SIPs are set on the Holdings page.</div>}
          {sips.map((s, i) => (
            <div key={s.holding_id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '7px 0', borderTop: i ? `1px solid ${T.hairline}` : undefined, opacity: s.show ? 1 : 0.55 }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13, overflowWrap: 'anywhere' }}>{s.label}</div>
                <div style={{ fontSize: 11.5, color: T.muted, marginTop: 1 }}>{fmtFull(s.amount)} · {ord(s.day)} of the month</div>
              </div>
              <Switch checked={s.show} label={`${s.label} in reminders`}
                onChange={v => run(setReminderSipVisibility(s.holding_id, v), v ? `${s.label} shown in reminders` : `${s.label} hidden from reminders`)} />
            </div>
          ))}
        </Card>

        <Card>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <h3 style={{ fontSize: 15, flex: 1 }}>Vacations</h3>
            <button style={smallBtn} onClick={() => setVacEdit('new')}>+ Add vacation</button>
          </div>
          <p style={{ color: T.muted, fontSize: 12.5, marginBottom: 10, lineHeight: 1.5 }}>
            Every day of a trip is tinted on the calendar and the trip is added to the calendar link.
          </p>
          {vacations.length === 0 && <div style={{ fontSize: 12.5, color: T.muted }}>No vacations yet.</div>}
          {vacations.map((v, i) => (
            <div key={v.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '7px 0', borderTop: i ? `1px solid ${T.hairline}` : undefined }}>
              <span style={{ width: 10, height: 10, borderRadius: '50%', background: v.color, flexShrink: 0 }} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13, overflowWrap: 'anywhere' }}>{v.name}</div>
                <div style={{ fontSize: 11.5, color: T.muted, marginTop: 1 }}>{vacationRange(v.start_date, v.end_date)}</div>
              </div>
              <button style={smallBtn} onClick={() => setVacEdit(v)}>Edit</button>
            </div>
          ))}
        </Card>
      </div>

      <Card style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
          <h3 style={{ fontSize: 15, flex: 1 }}>Trackers</h3>
          <button style={smallBtn} onClick={() => setTrackEdit('new')}>+ Add tracker</button>
        </div>
        <p style={{ color: T.muted, fontSize: 12.5, marginBottom: 10, lineHeight: 1.5 }}>
          Tick boxes on every calendar day, such as Gym or Office, with their progress shown above the calendar.
        </p>
        {trackers.length === 0 && <div style={{ fontSize: 12.5, color: T.muted }}>No trackers yet.</div>}
        {trackers.map((t, i) => (
          <div key={t.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '7px 0', borderTop: i ? `1px solid ${T.hairline}` : undefined }}>
            <span style={{ width: 12, height: 12, borderRadius: 3, background: t.color, flexShrink: 0 }} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13.5, fontWeight: 600, overflowWrap: 'anywhere' }}>{t.name}</div>
              <div style={{ fontSize: 11.5, color: T.muted, marginTop: 1 }}>
                {t.target_per_week}× a week · {weekdayText(t.weekdays)}{t.cost_links.length ? ' · linked to spending' : ''}
              </div>
            </div>
            <button style={smallBtn} title="Move up" aria-label={`Move ${t.name} up`} disabled={i === 0} onClick={() => moveTracker(i, -1)}>↑</button>
            <button style={smallBtn} title="Move down" aria-label={`Move ${t.name} down`} disabled={i === trackers.length - 1} onClick={() => moveTracker(i, 1)}>↓</button>
            <button style={smallBtn} onClick={() => setTrackEdit(t)}>Edit</button>
          </div>
        ))}
      </Card>

      <Card>
        <h3 style={{ fontSize: 15, marginBottom: 4 }}>All reminders</h3>
        {cats.map(c => {
          const list = rems.filter(r => r.category_id === c.id).sort((a, b) => a.day - b.day)
          return (
            <div key={c.id}>
              <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: 0.6, textTransform: 'uppercase', color: T.muted, margin: '14px 0 2px' }}>{c.name} · {list.length}</div>
              {list.length === 0 && <div style={{ fontSize: 12.5, color: T.muted, padding: '6px 0' }}>No reminders in this category.</div>}
              {list.map((r, i) => (
                <div key={r.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0', borderTop: i ? `1px solid ${T.hairline}` : undefined, opacity: r.enabled ? 1 : 0.55 }}>
                  <span style={{ width: 10, height: 10, borderRadius: '50%', background: c.color, flexShrink: 0 }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13.5, fontWeight: 600 }}>{r.name}</div>
                    <div style={{ fontSize: 11.5, color: T.muted, marginTop: 1 }}>
                      {REPEAT_TEXT[r.repeat]} · {ord(r.day)}{r.amount ? ` · ${fmtFull(r.amount)}` : ''}{r.expense_category_id ? ' · auto-ticks' : ''}
                    </div>
                  </div>
                  <Switch checked={r.enabled} label={`${r.name} on`} onChange={v => run(updateReminder(r.id, { enabled: v }), v ? `${r.name} on` : `${r.name} paused`)} />
                  <button style={smallBtn} onClick={() => setEditing(r)}>Edit</button>
                </div>
              ))}
            </div>
          )
        })}
      </Card>

      {catDialog && (
        <CategoryDialog cat={catDialog === 'new' ? null : catDialog} onClose={() => setCatDialog(null)}
          onSave={(name, color) => {
            const c = catDialog
            setCatDialog(null)
            run(c === 'new' ? createReminderCategory({ name, color }) : updateReminderCategory(c.id, { name, color }),
              c === 'new' ? 'Category added' : 'Category updated')
          }} />
      )}
      {deleting && (
        <DeleteCategoryDialog cat={deleting} others={cats.filter(c => c.id !== deleting.id)} onClose={() => setDeleting(null)}
          onDelete={opts => { const c = deleting; setDeleting(null); run(deleteReminderCategory(c.id, opts), `${c.name} deleted`) }} />
      )}
      {editing && (
        <ReminderEditor reminder={editing === 'new' ? null : editing} categories={cats} onClose={() => setEditing(null)}
          onSaved={text => { setEditing(null); setMsg({ text }); load() }} />
      )}
      {trackEdit && (
        <TrackerEditor tracker={trackEdit === 'new' ? null : trackEdit} nextColour={REMINDER_PALETTE[(trackers.length + 4) % REMINDER_PALETTE.length]}
          onClose={() => setTrackEdit(null)} onSaved={text => { setTrackEdit(null); setMsg({ text }); load() }} />
      )}
      {vacEdit && (
        <VacationEditor vacation={vacEdit === 'new' ? null : vacEdit} defaultFrom={new Date().toLocaleDateString('en-CA')} onClose={() => setVacEdit(null)}
          onSaved={text => { setVacEdit(null); setMsg({ text }); load() }} />
      )}
    </div>
  )
}

function CategoryRow({ cat, first, last, onColour, onRename, onDelete }: {
  cat: ReminderCategory; first: boolean; last: boolean; onColour: () => void; onRename: (name: string) => void; onDelete: () => void
}) {
  const [name, setName] = useState(cat.name)
  const commit = () => {
    const n = name.trim()
    if (!n) { setName(cat.name); return }
    if (n !== cat.name) onRename(n)
  }
  const reason = cat.kind ? 'Filled in automatically from your Cards or Portfolio, so it can be renamed but not deleted' : last ? 'Keep at least one category' : ''
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 0', borderTop: first ? undefined : `1px solid ${T.hairline}` }}>
      <button onClick={onColour} title="Change colour" aria-label={`Change colour of ${cat.name}`}
        style={{ width: 16, height: 16, borderRadius: '50%', background: cat.color, border: 'none', cursor: 'pointer', flexShrink: 0, padding: 0 }} />
      <input aria-label="Category name" value={name} onChange={e => setName(e.target.value)}
        onBlur={e => { commit(); e.currentTarget.style.background = 'transparent'; e.currentTarget.style.borderColor = 'transparent' }}
        onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); if (e.key === 'Escape') setName(cat.name) }}
        style={{ ...input, background: 'transparent', borderColor: 'transparent', padding: '5px 6px', flex: 1, minWidth: 0 }}
        onFocus={e => { e.currentTarget.style.background = T.surface2; e.currentTarget.style.borderColor = T.border }} />
      <span style={{ fontSize: 12, color: T.muted, minWidth: 18, textAlign: 'right' }} title="Reminders in this category">{cat.reminder_count}</span>
      <button style={{ ...dangerBtn, opacity: reason ? 0.4 : 1, cursor: reason ? 'not-allowed' : 'pointer' }} disabled={!!reason} title={reason || 'Delete category'}
        aria-label={`Delete ${cat.name}`} onClick={onDelete}>🗑</button>
    </div>
  )
}

function CategoryDialog({ cat, onClose, onSave }: { cat: ReminderCategory | null; onClose: () => void; onSave: (name: string, color: string) => void }) {
  const [name, setName] = useState(cat?.name ?? '')
  const [color, setColor] = useState(cat?.color ?? REMINDER_PALETTE[0])
  return (
    <Modal title={cat ? 'Edit category' : 'Add category'} onClose={onClose}>
      <form onSubmit={e => { e.preventDefault(); if (name.trim()) onSave(name.trim(), color) }}>
        <Field name="Name"><input style={input} autoFocus value={name} placeholder="e.g. Insurance, School" onChange={e => setName(e.target.value)} /></Field>
        <Field name="Colour"><Swatches value={color} onChange={setColor} /></Field>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 6 }}>
          <button type="button" style={btn()} onClick={onClose}>Cancel</button>
          <button type="submit" style={{ ...btn(true), opacity: name.trim() ? 1 : 0.5 }} disabled={!name.trim()}>{cat ? 'Save' : 'Add category'}</button>
        </div>
      </form>
    </Modal>
  )
}

function DeleteCategoryDialog({ cat, others, onClose, onDelete }: {
  cat: ReminderCategory; others: ReminderCategory[]; onClose: () => void
  onDelete: (opts: { move_to?: number; delete_reminders?: boolean }) => void
}) {
  const [mode, setMode] = useState<'move' | 'delete'>('move')
  const [to, setTo] = useState(others[0]?.id ?? 0)
  const n = cat.reminder_count
  return (
    <Modal title={`Delete ${cat.name}?`} onClose={onClose}>
      {n === 0 ? (
        <p style={{ fontSize: 13, color: T.muted, marginBottom: 16 }}><b style={{ color: T.text }}>{cat.name}</b> has no reminders, so it can be removed straight away.</p>
      ) : (
        <div style={{ marginBottom: 16 }}>
          <p style={{ fontSize: 13, color: T.muted, marginBottom: 12 }}><b style={{ color: T.text }}>{cat.name}</b> has {n} reminder{n === 1 ? '' : 's'}. What should happen to {n === 1 ? 'it' : 'them'}?</p>
          <label style={{ display: 'block', fontSize: 13, marginBottom: 8 }}>
            <input type="radio" name="mv" checked={mode === 'move'} onChange={() => setMode('move')} /> Move to{' '}
            <select style={{ ...input, width: 'auto', marginLeft: 6 }} value={to} disabled={mode !== 'move'} onChange={e => setTo(Number(e.target.value))}>
              {others.map(o => <option key={o.id} value={o.id}>{o.name}</option>)}
            </select>
          </label>
          <label style={{ display: 'block', fontSize: 13 }}>
            <input type="radio" name="mv" checked={mode === 'delete'} onChange={() => setMode('delete')} /> Delete {n === 1 ? 'it' : 'them'} as well
          </label>
        </div>
      )}
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
        <button style={btn()} onClick={onClose}>Cancel</button>
        <button style={{ ...btn(), background: T.danger, borderColor: T.danger, color: '#fff' }}
          onClick={() => onDelete(n === 0 ? {} : mode === 'move' ? { move_to: to } : { delete_reminders: true })}>Delete category</button>
      </div>
    </Modal>
  )
}
