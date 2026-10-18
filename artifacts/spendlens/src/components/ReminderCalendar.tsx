import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import {
  createReminder, deleteReminder, getReminderCalendar, getReminderCategories, getReminders, getReminderSuggestions, moveReminder, setTrackerDay,
  type OccurrenceState, type Reminder, type ReminderCalendar as CalendarData, type ReminderCategory, type ReminderOccurrence, type ReminderSuggestion,
  type CalendarTracker, type Holiday, type Vacation,
} from '../api'
import { currentMonth, monthLabel, shiftMonth } from '../months'
import { MONTHS, T, fmtFull } from '../theme'
import MonthPicker from './MonthPicker'
import ReminderEditor from './ReminderEditor'
import SipEditor from './SipEditor'
import { TrackerManager } from './TrackerEditor'
import TrackerKpis from './TrackerKpis'
import VacationEditor from './VacationEditor'
import { REMINDER_PALETTE, ord, vacationRange } from './reminderUi'
import { btn, card, Modal, smallBtn } from './ui'

const pad = (n: number) => String(n).padStart(2, '0')
const HIDDEN_KEY = 'spendlens.reminderHidden'
const TRACKER_HIDDEN_KEY = 'spendlens.trackerHidden'
const DRAG_TYPE = 'application/x-spendlens-reminder'
const LOG_KEY = 'spendlens.reminderLog'
const SHOW_KEY = 'spendlens.reminderShow'
const VACATION_COLOUR = REMINDER_PALETTE[6]
const NUDGE_COLOUR = '#38bdf8'
const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const FULL_WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']

function readHidden(key = HIDDEN_KEY): Set<number> {
  try { return new Set(JSON.parse(localStorage.getItem(key) ?? '[]') as number[]) } catch { return new Set() }
}
const isStored = (o: ReminderOccurrence) => !o.auto && o.reminder_id != null

/** What a tick box needs from the calendar: the visible trackers, their (optimistic) state per day, and the toggle. */
interface TickProps {
  trackers: CalendarTracker[]; isDone: (t: CalendarTracker, d: number) => boolean; onTick: (t: CalendarTracker, d: number) => void
}
/** Drag-and-drop state shared by every cell. */
interface DragProps {
  dropDay: number | null; onDragStart: (o: ReminderOccurrence) => void; onDragEnd: () => void
  onDragOverDay: (d: number) => boolean; onDropDay: (d: number) => void
}
function readLog(): boolean {
  try { return localStorage.getItem(LOG_KEY) !== 'off' } catch { return true }
}
interface ShowKinds { india: boolean; us: boolean; vacations: boolean }
function readShow(): ShowKinds {
  try {
    const v = JSON.parse(localStorage.getItem(SHOW_KEY) ?? '{}') as Partial<ShowKinds>
    return { india: v.india !== false, us: v.us !== false, vacations: v.vacations !== false }
  } catch { return { india: true, us: true, vacations: true } }
}
interface DayInfo { hols: Holiday[]; vacs: Vacation[] }
const holColour = (h: Holiday) => (h.country === 'IN' ? 'var(--hol-in)' : 'var(--hol-us)')
const holCountry = (h: Holiday) => (h.country === 'IN' ? 'India' : 'US')

/** Soft cell tint: the vacation's colour wins; a day that is a holiday in both countries is split diagonally. */
function cellTint(info: DayInfo | undefined): string | undefined {
  if (!info) return undefined
  const mix = (c: string) => `color-mix(in srgb, ${c} 22%, transparent)`
  const flat = (c: string) => `linear-gradient(${mix(c)}, ${mix(c)})`
  if (info.vacs.length) return flat(info.vacs[0].color)
  const india = info.hols.some(h => h.country === 'IN'), us = info.hols.some(h => h.country === 'US')
  if (india && us) return `linear-gradient(135deg, ${mix('var(--hol-in)')} 50%, ${mix('var(--hol-us)')} 50%)`
  if (india) return flat('var(--hol-in)')
  if (us) return flat('var(--hol-us)')
  return undefined
}

interface HistoryRow { key: string; name: string; day: number; detail: string; suggestion: ReminderSuggestion | null; kept: Reminder | null }
const daysIn = (month: string) => new Date(Number(month.slice(0, 4)), Number(month.slice(5)), 0).getDate()

function Marker({ state, colour }: { state: OccurrenceState; colour: string }) {
  const base: CSSProperties = { width: 12, height: 12, borderRadius: '50%', flexShrink: 0, display: 'grid', placeItems: 'center', fontSize: 8, lineHeight: 1 }
  if (state === 'done') return <span aria-label="Matched" style={{ ...base, background: colour, color: T.surface }}>✓</span>
  if (state === 'missing') return <span aria-label="Nothing logged" style={{ ...base, boxShadow: `inset 0 0 0 1.5px ${T.warn}`, color: T.warn, fontWeight: 700 }}>!</span>
  if (state === 'up') return <span aria-label="Coming up" style={{ ...base, boxShadow: `inset 0 0 0 1.5px ${colour}` }} />
  if (state === 'info') return <span aria-label="Information" style={{ ...base, border: `1.5px dashed ${colour}` }} />
  return <span style={{ ...base, width: 7, height: 7, margin: '0 2.5px', background: colour }} />
}

/** The reminders calendar: a Monday-first month grid, a day panel, and the side cards (coming up, found in history, subscribe). */
export default function ReminderCalendar({ headerExtra }: { headerExtra?: ReactNode }) {
  const [month, setMonth] = useState(currentMonth)
  const [data, setData] = useState<CalendarData | null>(null)
  const [nextData, setNextData] = useState<CalendarData | null>(null)
  const [cats, setCats] = useState<ReminderCategory[]>([])
  const [rems, setRems] = useState<Reminder[]>([])
  const [suggestions, setSuggestions] = useState<ReminderSuggestion[]>([])
  const [selDay, setSelDay] = useState(() => new Date().getDate())
  const [hidden, setHidden] = useState<Set<number>>(readHidden)
  const [logOn, setLogOn] = useState(readLog)
  const [show, setShow] = useState(readShow)
  const [vacEditor, setVacEditor] = useState<{ vacation: Vacation | null; from?: string } | null>(null)
  const [editor, setEditor] = useState<{ reminder: Reminder | null; day?: number } | null>(null)
  const [sipEdit, setSipEdit] = useState<ReminderOccurrence | null>(null)
  const [msg, setMsg] = useState<{ text: string; error?: boolean } | null>(null)
  const [copied, setCopied] = useState('')
  const [trackerHidden, setTrackerHidden] = useState<Set<number>>(() => readHidden(TRACKER_HIDDEN_KEY))
  const [ticks, setTicks] = useState<Map<string, boolean>>(new Map())   // optimistic tick state until the reload lands
  const [manage, setManage] = useState(false)
  const [dropDay, setDropDay] = useState<number | null>(null)
  const [moving, setMoving] = useState<{ occ: ReminderOccurrence; day: number; error?: string; busy?: boolean } | null>(null)
  const dragged = useRef<ReminderOccurrence | null>(null)
  const seq = useRef(0)
  const urlRef = useRef<HTMLDivElement | null>(null)

  const load = useCallback(async () => {
    const mine = ++seq.current
    try {
      const [d, c, r, s] = await Promise.all([
        getReminderCalendar(month), getReminderCategories(), getReminders(), getReminderSuggestions().catch(() => [] as ReminderSuggestion[]),
      ])
      const todayDay = d.today.startsWith(month) ? Number(d.today.slice(8)) : 0
      const next = todayDay && todayDay + 14 > daysIn(month) ? await getReminderCalendar(shiftMonth(month, 1)).catch(() => null) : null
      if (mine !== seq.current) return
      setData(d); setCats(c); setRems(r); setSuggestions(s); setNextData(next)
    } catch (e) { if (mine === seq.current) setMsg({ text: (e as Error).message, error: true }) }
  }, [month])
  useEffect(() => { load() }, [load])

  const run = async (p: Promise<unknown>, ok?: string) => {
    try { await p; setMsg(ok ? { text: ok } : null); await load() } catch (e) { setMsg({ text: (e as Error).message, error: true }) }
  }

  const changeMonth = (m: string) => { setMonth(m); setSelDay(m === currentMonth() ? new Date().getDate() : 1) }
  const toggleCat = (id: number) => setHidden(h => {
    const n = new Set(h)
    if (n.has(id)) n.delete(id); else n.add(id)
    try { localStorage.setItem(HIDDEN_KEY, JSON.stringify([...n])) } catch { /* storage unavailable */ }
    return n
  })
  const toggleLog = () => setLogOn(v => {
    try { localStorage.setItem(LOG_KEY, v ? 'off' : 'on') } catch { /* storage unavailable */ }
    return !v
  })

  const toggleShow = (k: keyof ShowKinds) => setShow(v => {
    const n = { ...v, [k]: !v[k] }
    try { localStorage.setItem(SHOW_KEY, JSON.stringify(n)) } catch { /* storage unavailable */ }
    return n
  })

  const toggleTracker = (id: number) => setTrackerHidden(h => {
    const n = new Set(h)
    if (n.has(id)) n.delete(id); else n.add(id)
    try { localStorage.setItem(TRACKER_HIDDEN_KEY, JSON.stringify([...n])) } catch { /* storage unavailable */ }
    return n
  })
  const allTrackers = data?.trackers ?? []
  const trackers = useMemo(() => (data?.trackers ?? []).filter(t => !trackerHidden.has(t.id)), [data, trackerHidden])
  const doneSets = useMemo(() => new Map((data?.trackers ?? []).map(t => [t.id, new Set(t.done_days)])), [data])
  const isDone = (t: CalendarTracker, d: number) => ticks.get(`${t.id}:${d}`) ?? doneSets.get(t.id)?.has(d) ?? false

  const onTick = async (t: CalendarTracker, d: number) => {
    const key = `${t.id}:${d}`, next = !isDone(t, d)
    const clear = () => setTicks(m => { const n = new Map(m); n.delete(key); return n })
    setTicks(m => new Map(m).set(key, next))
    try {
      await setTrackerDay(t.id, `${month}-${pad(d)}`, next)
      await load()
      clear()
    } catch (e) {
      clear()
      setMsg({ text: `${t.name} on ${d} ${MONTHS[Number(month.slice(5)) - 1].slice(0, 3)}: ${(e as Error).message}`, error: true })
    }
  }

  const drag: DragProps = {
    dropDay,
    onDragStart: o => { dragged.current = o },
    onDragEnd: () => { dragged.current = null; setDropDay(null) },
    onDragOverDay: d => {
      if (!dragged.current) return false
      if (dropDay !== d) setDropDay(d)
      return true
    },
    onDropDay: d => {
      const o = dragged.current
      dragged.current = null; setDropDay(null)
      if (o && o.day !== d) setMoving({ occ: o, day: d })
    },
  }
  const confirmMove = async (scope: 'all' | 'month') => {
    if (!moving?.occ.reminder_id) return
    const { occ, day } = moving
    setMoving({ ...moving, busy: true, error: undefined })
    try {
      await moveReminder(occ.reminder_id!, { month, day, scope })
      setMoving(null)
      setMsg({ text: scope === 'all' ? `${occ.name} moved to the ${ord(day)} of every month` : `${occ.name} moved to ${day} ${monthLabel(month)} only` })
      setSelDay(day)
      await load()
    } catch (e) { setMoving({ occ, day, error: (e as Error).message }) }
  }

  const catById = useMemo(() => new Map(cats.map(c => [c.id, c])), [cats])
  const nudgeShown = !!data?.nudge.on && logOn
  const todayIso = data?.today ?? ''
  const todayDay = todayIso.startsWith(month) ? Number(todayIso.slice(8)) : 0
  const monthDays = daysIn(month)
  const first = (new Date(Number(month.slice(0, 4)), Number(month.slice(5)) - 1, 1).getDay() + 6) % 7

  const byDay = useMemo(() => {
    const m = new Map<number, ReminderOccurrence[]>()
    for (const o of data?.occurrences ?? []) {
      if (hidden.has(o.category_id)) continue
      const list = m.get(o.day) ?? []
      list.push(o)
      m.set(o.day, list)
    }
    return m
  }, [data, hidden])
  const logged = useMemo(() => new Set(data?.logged_days ?? []), [data])
  const dayInfo = useMemo(() => {
    const m = new Map<number, DayInfo>()
    const at = (d: number) => { let e = m.get(d); if (!e) { e = { hols: [], vacs: [] }; m.set(d, e) } return e }
    for (const h of data?.holidays ?? []) {
      if (!h.date.startsWith(month) || !(h.country === 'IN' ? show.india : show.us)) continue
      at(Number(h.date.slice(8))).hols.push(h)
    }
    if (show.vacations) {
      for (const v of data?.vacations ?? []) {
        for (let d = 1; d <= monthDays; d++) { const iso = `${month}-${pad(d)}`; if (iso >= v.start_date && iso <= v.end_date) at(d).vacs.push(v) }
      }
    }
    for (const e of m.values()) e.hols.sort((a, b) => a.country.localeCompare(b.country))
    return m
  }, [data, show, month, monthDays])

  const weeks = Math.ceil((first + monthDays) / 7)
  const weekSums = useMemo(() => {
    const sums: number[] = Array(weeks).fill(0)
    for (const [d, list] of byDay) sums[Math.floor((first + d - 1) / 7)] += list.reduce((s, o) => s + o.amount, 0)
    return sums
  }, [byDay, first, weeks])
  const maxSum = Math.max(1, ...weekSums)

  const upcoming = useMemo(() => {
    if (!todayDay || !data) return []
    const [y, m, d] = todayIso.split('-').map(Number)
    const from = new Date(y, m - 1, d).getTime(), to = from + 14 * 86400000
    const out: { o: ReminderOccurrence; date: Date }[] = []
    for (const src of [data, nextData]) {
      if (!src) continue
      const sy = Number(src.month.slice(0, 4)), sm = Number(src.month.slice(5))
      for (const o of src.occurrences) {
        if (!o.amount || hidden.has(o.category_id)) continue
        const date = new Date(sy, sm - 1, o.day)
        if (date.getTime() >= from && date.getTime() <= to) out.push({ o, date })
      }
    }
    return out.sort((a, b) => a.date.getTime() - b.date.getTime())
  }, [data, nextData, hidden, todayDay, todayIso])

  const billsCat = cats.find(c => c.kind === null) ?? cats[0]
  const keptByKey = useMemo(() => new Map(rems.filter(r => r.source_key).map(r => [r.source_key!, r])), [rems])
  const historyRows = useMemo<HistoryRow[]>(() => {
    const rows: HistoryRow[] = suggestions.map(s => ({
      key: s.key, name: s.name, day: s.day, suggestion: s, kept: null,
      detail: `${ord(s.day)} · ${s.min_amount === s.max_amount ? fmtFull(s.min_amount) : `${fmtFull(s.min_amount)} to ${fmtFull(s.max_amount)}`} · ${s.months} months`,
    }))
    for (const r of keptByKey.values()) rows.push({ key: r.source_key!, name: r.name, day: r.day, suggestion: null, kept: r, detail: `${ord(r.day)}${r.amount ? ` · ${fmtFull(r.amount)}` : ''}` })
    return rows.sort((a, b) => a.day - b.day)
  }, [suggestions, keptByKey])

  const keep = (s: ReminderSuggestion) => {
    if (!billsCat) { setMsg({ text: 'Add a reminder category first.', error: true }); return }
    run(createReminder({
      category_id: billsCat.id, name: s.name, amount: s.amount, day: s.day, repeat: 'monthly', month: null, enabled: true,
      note: 'Added from your history', expense_category_id: s.category_id, expense_subcategory_id: s.subcategory_id, source_key: s.key,
    }), `${s.name} added`)
  }

  const feedTypes = [...cats.filter(c => !hidden.has(c.id)).map(c => String(c.id)), ...(nudgeShown ? ['log'] : [])]
  const feedUrl = `${window.location.origin}/spendlens/api/calendar.ics?types=${feedTypes.join(',') || 'none'}`
  const copy = async () => {
    try { await navigator.clipboard.writeText(feedUrl); setCopied('Copied') } catch {
      const el = urlRef.current
      if (el) { const r = document.createRange(); r.selectNodeContents(el); const s = getSelection(); s?.removeAllRanges(); s?.addRange(r) }
      setCopied('Selected. Press Ctrl+C')
    }
  }

  const selItems = byDay.get(selDay) ?? []
  const selInfo = dayInfo.get(selDay)
  const selTotal = selItems.reduce((s, o) => s + o.amount, 0)
  const selDate = new Date(Number(month.slice(0, 4)), Number(month.slice(5)) - 1, selDay)
  const selIso = `${month}-${pad(selDay)}`
  const storedFor = (o: ReminderOccurrence) => (o.reminder_id != null && !o.auto ? rems.find(r => r.id === o.reminder_id) ?? null : null)
  const sourceText = (o: ReminderOccurrence) => {
    const k = catById.get(o.category_id)?.kind
    return o.auto ? (k === 'card' ? 'from Cards' : k === 'sip' ? 'from Portfolio' : 'automatic') : ''
  }

  const pill = (active: boolean, colour: string, text: string, onClick: () => void, title?: string, disabled?: boolean, square?: boolean) => (
    <button key={`${square ? 't' : 'c'}-${text}`} type="button" onClick={onClick} aria-pressed={active} disabled={disabled} title={title}
      style={{ display: 'inline-flex', alignItems: 'center', gap: 7, border: `1px solid ${T.border}`, background: T.surface, color: T.text, borderRadius: 999,
        padding: '6px 12px', fontSize: 12.5, fontWeight: 500, cursor: disabled ? 'not-allowed' : 'pointer', opacity: active ? 1 : 0.5 }}>
      <i style={{ width: 9, height: 9, borderRadius: square ? 2 : '50%', background: active ? colour : 'transparent', boxShadow: active ? undefined : `inset 0 0 0 1.5px ${colour}` }} />
      {text}
    </button>
  )

  return (
    <div style={{ padding: '20px 24px' }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 14, flexWrap: 'wrap' }}>
        {headerExtra}
        <MonthPicker month={month} onChange={changeMonth} />
        <div style={{ flex: 1 }} />
        {msg && <span role={msg.error ? 'alert' : 'status'} style={{ fontSize: 12.5, color: msg.error ? T.negative : T.positive }}>{msg.text}</span>}
        <button style={btn()} onClick={() => setManage(true)}>Manage trackers</button>
        <button style={btn(true)} onClick={() => setEditor({ reminder: null, day: selDay })}>+ Add reminder</button>
      </div>

      <TrackerKpis trackers={trackers} />

      <div role="group" aria-label="Show" style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 12 }}>
        {cats.map(c => pill(!hidden.has(c.id), c.color, c.name, () => toggleCat(c.id)))}
        {allTrackers.map(t => pill(!trackerHidden.has(t.id), t.color, t.name, () => toggleTracker(t.id), undefined, false, true))}
        {pill(nudgeShown, NUDGE_COLOUR, 'Log expenses', toggleLog,
          data && !data.nudge.on ? 'The evening nudge is off. Turn it on in Settings > Reminders.' : undefined, !!data && !data.nudge.on)}
        {pill(show.india, 'var(--hol-in)', 'India holidays', () => toggleShow('india'))}
        {pill(show.us, 'var(--hol-us)', 'US holidays', () => toggleShow('us'))}
        {pill(show.vacations, VACATION_COLOUR, 'Vacations', () => toggleShow('vacations'))}
      </div>

      <div className="rc-layout">
        <section aria-label={monthLabel(month)} style={{ ...card, overflow: 'hidden' }}>
          <div className="rc-grid">
            {WEEKDAYS.map(d => <div key={d} style={{ padding: 8, fontSize: 11, letterSpacing: 0.6, textTransform: 'uppercase', color: T.muted, borderBottom: `1px solid ${T.border}` }}>{d}</div>)}
            <div className="rc-rail" style={{ padding: 8, fontSize: 11, letterSpacing: 0.6, textTransform: 'uppercase', color: T.muted, borderBottom: `1px solid ${T.border}`, textAlign: 'right' }}>Out</div>
            {Array.from({ length: weeks }, (_, w) => (
              <WeekRow key={w} week={w} first={first} monthDays={monthDays} byDay={byDay} catById={catById} selDay={selDay} todayDay={todayDay}
                nudgeShown={nudgeShown} logged={logged} todayIso={todayIso} month={month} dayInfo={dayInfo} sum={weekSums[w]} maxSum={maxSum} onSelect={setSelDay}
                tick={{ trackers, isDone, onTick }} drag={drag} />
            ))}
          </div>

          <div style={{ borderTop: `1px solid ${T.border}`, padding: '14px 16px 16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 6 }}>
              <h3 style={{ fontSize: 16, flex: 1, minWidth: 160 }}>
                {FULL_WEEKDAYS[selDate.getDay()]} {selDay} {monthLabel(month).split(' ')[0]}{selDay === todayDay ? ' · today' : ''}{selTotal ? ` · ${fmtFull(selTotal)} going out` : ''}
              </h3>
              <button style={smallBtn} onClick={() => setVacEditor({ vacation: null, from: selIso })}>+ Add vacation</button>
              <button style={smallBtn} onClick={() => setEditor({ reminder: null, day: selDay })}>+ Add reminder</button>
            </div>
            {selInfo && (selInfo.hols.length > 0 || selInfo.vacs.length > 0) && (
              <div style={{ marginBottom: 6 }}>
                {selInfo.hols.map((h, i) => (
                  <div key={`${h.country}-${h.name}`} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '7px 0', borderTop: i ? `1px solid ${T.border}` : undefined }}>
                    <i style={{ width: 12, height: 12, borderRadius: 3, flexShrink: 0, background: `color-mix(in srgb, ${holColour(h)} 35%, transparent)`, boxShadow: `inset 0 0 0 1.5px ${holColour(h)}` }} />
                    <div style={{ flex: 1, minWidth: 0, fontSize: 13.5 }}>{h.name}</div>
                    <div style={{ fontSize: 12, color: T.muted }}>{holCountry(h)} holiday</div>
                  </div>
                ))}
                {selInfo.vacs.map((v, i) => (
                  <div key={v.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '7px 0', borderTop: i || selInfo.hols.length ? `1px solid ${T.border}` : undefined }}>
                    <i style={{ width: 12, height: 12, borderRadius: 3, flexShrink: 0, background: `color-mix(in srgb, ${v.color} 35%, transparent)`, boxShadow: `inset 0 0 0 1.5px ${v.color}` }} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 13.5 }}>{v.name}</div>
                      <div style={{ fontSize: 12, color: T.muted }}>Vacation · {vacationRange(v.start_date, v.end_date)}</div>
                    </div>
                    <button style={smallBtn} onClick={() => setVacEditor({ vacation: v })}>Edit</button>
                  </div>
                ))}
              </div>
            )}
            {selItems.length === 0 && <div style={{ fontSize: 12, color: T.muted, lineHeight: 1.55 }}>Nothing due.{nudgeShown ? ` The ${data?.nudge.time} nudge still asks you to log the day.` : ''}</div>}
            {selItems.map((o, i) => {
              const cat = catById.get(o.category_id), stored = storedFor(o), src = sourceText(o)
              const funds = o.sources?.length ? [...o.sources.reduce((m, s) => m.set(s.label, (m.get(s.label) ?? 0) + s.amount), new Map<string, number>())] : []
              return (
                <div key={o.key} style={{ borderTop: i ? `1px solid ${T.border}` : undefined, padding: '8px 0' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <Marker state={o.state} colour={cat?.color ?? T.muted} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 13.5 }}>{o.name}</div>
                      <div style={{ fontSize: 12, color: T.muted }}>
                        {[funds.length ? cat?.name : o.note || cat?.name, o.estimated ? 'estimated' : '', o.moved ? 'moved for this month only' : '', src].filter(Boolean).join(' · ')}
                      </div>
                    </div>
                    {o.amount > 0 && <div style={{ fontSize: 13, fontVariantNumeric: 'tabular-nums' }}>{o.estimated ? '~' : ''}{fmtFull(o.amount)}</div>}
                    {stored && <button style={smallBtn} onClick={() => setEditor({ reminder: stored })}>Edit</button>}
                    {o.auto && o.sources?.length ? <button style={smallBtn} onClick={() => setSipEdit(o)}>Edit</button> : null}
                  </div>
                  {funds.length > 1 && (
                    <div style={{ margin: '6px 0 2px 22px', fontSize: 12.5 }}>
                      {funds.map(([label, amount]) => (
                        <div key={label} style={{ display: 'flex', gap: 10, padding: '2px 0' }}>
                          <span style={{ flex: 1, minWidth: 0, color: T.muted }}>{label}</span>
                          <span style={{ fontVariantNumeric: 'tabular-nums' }}>{fmtFull(amount)}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
            {nudgeShown && selIso <= todayIso && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0', borderTop: selItems.length ? `1px solid ${T.border}` : undefined, fontSize: 13 }}>
                <i style={{ width: 9, height: 9, borderRadius: '50%', margin: '0 1.5px', flexShrink: 0, background: logged.has(selDay) ? NUDGE_COLOUR : 'transparent', boxShadow: `inset 0 0 0 1.5px ${NUDGE_COLOUR}` }} />
                {logged.has(selDay) ? 'Day logged' : 'Nothing logged this day'}
              </div>
            )}
          </div>

          <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', padding: '10px 16px 14px', color: T.muted, fontSize: 12, borderTop: `1px solid ${T.border}` }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><Marker state="done" colour={T.muted} /> a matching expense was logged</span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><Marker state="up" colour={T.muted} /> coming up</span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><Marker state="missing" colour={T.warn} /> due, nothing logged</span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><Marker state="info" colour={T.muted} /> information only</span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><Marker state="unlinked" colour={T.muted} /> not tracked against an expense</span>
            {([['var(--hol-in)', 'India holiday'], ['var(--hol-us)', 'US holiday'], [VACATION_COLOUR, 'vacation']] as const).map(([c, text]) => (
              <span key={text} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                <i style={{ width: 12, height: 12, borderRadius: 3, background: `color-mix(in srgb, ${c} 35%, transparent)`, boxShadow: `inset 0 0 0 1.5px ${c}` }} /> {text}
              </span>
            ))}
          </div>
        </section>

        <aside style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <SideCard title="Coming up" hint="Next 14 days, money going out.">
            {!todayDay && <div style={{ fontSize: 12, color: T.muted }}>Switch to the current month to see what is coming up.</div>}
            {todayDay > 0 && upcoming.length === 0 && <div style={{ fontSize: 12, color: T.muted }}>Nothing due in the next two weeks.</div>}
            {upcoming.map(({ o, date }, i) => {
              const diff = Math.round((date.getTime() - new Date(Number(todayIso.slice(0, 4)), Number(todayIso.slice(5, 7)) - 1, Number(todayIso.slice(8))).getTime()) / 86400000)
              return (
                <div key={`${date.getTime()}-${o.key}`} style={{ display: 'grid', gridTemplateColumns: '42px 1fr auto', gap: 10, alignItems: 'center', padding: '7px 0', borderTop: i ? `1px solid ${T.border}` : undefined }}>
                  <div style={{ fontSize: 11, color: T.muted, textAlign: 'center', lineHeight: 1.3 }}>
                    <b style={{ display: 'block', fontSize: 15, color: T.text }}>{date.getDate()}</b>{diff === 0 ? 'today' : `in ${diff}d`}
                  </div>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 500 }}>{o.name}</div>
                    <div style={{ fontSize: 11.5, color: T.muted }}>{catById.get(o.category_id)?.name}</div>
                  </div>
                  <div style={{ fontSize: 13, fontVariantNumeric: 'tabular-nums' }}>{o.estimated ? '~' : ''}{fmtFull(o.amount)}</div>
                </div>
              )
            })}
          </SideCard>

          <SideCard title="Found in your history" hint="These repeat every month. Keep the ones you want as reminders.">
            {historyRows.length === 0 && <div style={{ fontSize: 12, color: T.muted }}>No repeating expenses found yet.</div>}
            {historyRows.map((row, i) => (
              <div key={row.key} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '7px 0', borderTop: i ? `1px solid ${T.border}` : undefined }}>
                <div style={{ flex: 1, minWidth: 0, fontSize: 13 }}>
                  {row.name}
                  <div style={{ fontSize: 11.5, color: T.muted }}>{row.detail}</div>
                </div>
                <button aria-pressed={!!row.kept} style={{ ...smallBtn, ...(row.kept ? { background: T.accent, borderColor: T.accent, color: '#fff' } : {}) }}
                  onClick={() => (row.kept ? run(deleteReminder(row.kept.id), `${row.name} removed from reminders`) : keep(row.suggestion!))}>
                  {row.kept ? 'Kept' : 'Keep'}
                </button>
              </div>
            ))}
          </SideCard>

          <SideCard title="Subscribe" hint="Add this link once in Apple Calendar, Outlook or Google Calendar. It follows the toggles above.">
            <div ref={urlRef} style={{ fontFamily: 'ui-monospace, monospace', fontSize: 11.5, background: T.surface2, border: `1px solid ${T.border}`, borderRadius: 8, padding: '9px 10px', wordBreak: 'break-all', lineHeight: 1.5 }}>{feedUrl}</div>
            <div style={{ display: 'flex', gap: 8, marginTop: 10, alignItems: 'center' }}>
              <button style={btn(true)} onClick={copy}>Copy link</button>
              <span aria-live="polite" style={{ fontSize: 12, color: T.muted }}>{copied}</span>
            </div>
            <div style={{ fontSize: 11.5, color: T.muted, lineHeight: 1.55, marginTop: 8 }}>
              Evening nudge at {data?.nudge.time ?? '21:00'}. Google Calendar only reads public links, so for Google import the downloaded file instead.
            </div>
          </SideCard>
        </aside>
      </div>

      {sipEdit?.sources && (
        <SipEditor title={sipEdit.name} sources={sipEdit.sources} onClose={() => setSipEdit(null)}
          onSaved={text => { setSipEdit(null); setMsg({ text }); load() }} />
      )}
      {vacEditor && (
        <VacationEditor vacation={vacEditor.vacation} defaultFrom={vacEditor.from} onClose={() => setVacEditor(null)}
          onSaved={text => { setVacEditor(null); setMsg({ text }); load() }} />
      )}
      {editor && (
        <ReminderEditor reminder={editor.reminder} defaultDay={editor.day} categories={cats} onClose={() => setEditor(null)}
          onSaved={text => { setEditor(null); setMsg({ text }); load() }} />
      )}
      {manage && <TrackerManager onClose={() => setManage(false)} onChanged={text => { setMsg({ text }); load() }} />}
      {moving && (
        <Modal title={`Move ${moving.occ.name} to ${moving.day} ${MONTHS[Number(month.slice(5)) - 1].slice(0, 3)}`} onClose={() => setMoving(null)}>
          <p style={{ fontSize: 13, color: T.muted, lineHeight: 1.55, marginBottom: 14 }}>
            Move it to the {ord(moving.day)} from now on, or only for {monthLabel(month)}? A move for one month leaves the usual day as it is.
          </p>
          {moving.error && <div role="alert" style={{ color: T.negative, fontSize: 12.5, marginBottom: 10 }}>{moving.error}</div>}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, flexWrap: 'wrap' }}>
            <button type="button" style={btn()} onClick={() => setMoving(null)}>Cancel</button>
            <button type="button" style={btn()} disabled={moving.busy} onClick={() => confirmMove('month')}>Only {MONTHS[Number(month.slice(5)) - 1]}</button>
            <button type="button" style={{ ...btn(true), opacity: moving.busy ? 0.6 : 1 }} disabled={moving.busy} autoFocus onClick={() => confirmMove('all')}>Every month</button>
          </div>
        </Modal>
      )}
    </div>
  )
}

function SideCard({ title, hint, children }: { title: string; hint: string; children: ReactNode }) {
  return (
    <section style={{ ...card, padding: '14px 16px' }}>
      <h2 style={{ fontSize: 16, marginBottom: 2 }}>{title}</h2>
      <p style={{ color: T.muted, fontSize: 12.5, margin: '2px 0 10px', lineHeight: 1.5 }}>{hint}</p>
      {children}
    </section>
  )
}

function WeekRow({ week, first, monthDays, byDay, catById, selDay, todayDay, nudgeShown, logged, todayIso, month, dayInfo, sum, maxSum, onSelect, tick, drag }: {
  week: number; first: number; monthDays: number; byDay: Map<number, ReminderOccurrence[]>; catById: Map<number, ReminderCategory>
  selDay: number; todayDay: number; nudgeShown: boolean; logged: Set<number>; todayIso: string; month: string; dayInfo: Map<number, DayInfo>
  sum: number; maxSum: number; onSelect: (d: number) => void; tick: TickProps; drag: DragProps
}) {
  const monthShort = MONTHS[Number(month.slice(5)) - 1].slice(0, 3)
  const rowStart = Math.max(1, week * 7 - first + 1)
  return (
    <>
      {Array.from({ length: 7 }, (_, c) => {
        const d = week * 7 + c - first + 1
        if (d < 1 || d > monthDays) return <div key={c} className="rc-cell out" />
        const items = byDay.get(d) ?? []
        const isToday = d === todayDay
        const iso = `${month}-${pad(d)}`
        const past = iso <= todayIso
        const future = !!todayIso && iso > todayIso
        const info = dayInfo.get(d)
        const names = [...(info?.hols ?? []).map(h => `${holCountry(h)}: ${h.name}`), ...(info?.vacs ?? []).map(v => `${v.name} (${vacationRange(v.start_date, v.end_date)})`)]
        const tint = cellTint(info)
        return (
          <div key={c} role="button" tabIndex={0} className={`rc-cell${d === selDay ? ' sel' : ''}${drag.dropDay === d ? ' drop' : ''}`}
            onClick={() => onSelect(d)}
            onKeyDown={e => { if (e.target === e.currentTarget && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); onSelect(d) } }}
            onDragOver={e => { if (drag.onDragOverDay(d)) { e.preventDefault(); e.dataTransfer.dropEffect = 'move' } }}
            onDrop={e => { e.preventDefault(); drag.onDropDay(d) }}
            title={names.length ? names.join('\n') : undefined}
            style={tint ? ({ '--rc-tint': tint } as CSSProperties) : undefined}
            aria-label={`${d} ${monthLabel(month)}, ${items.length} reminder${items.length === 1 ? '' : 's'}${names.length ? `, ${names.join(', ')}` : ''}`}>
            <span style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 12, color: T.muted, fontVariantNumeric: 'tabular-nums' }}>
              {isToday ? <b style={{ background: T.accent, color: '#fff', borderRadius: 999, padding: '1px 7px', fontWeight: 500 }}>{d}</b> : <span>{d}</span>}
              {nudgeShown && (past || isToday) && (
                <span className={isToday ? 'rc-pulse' : undefined} aria-hidden="true"
                  style={{ width: 9, height: 9, borderRadius: '50%', boxShadow: `inset 0 0 0 1.5px ${NUDGE_COLOUR}`, background: logged.has(d) ? NUDGE_COLOUR : 'transparent' }} />
              )}
            </span>
            {info?.hols.map(h => <span key={`${h.country}-${h.name}`} className="rc-hol" style={{ color: holColour(h) }}>{h.name}</span>)}
            {info?.vacs.filter(v => c === 0 || iso === (v.start_date > `${month}-01` ? v.start_date : `${month}-01`)).map(v => (
              <span key={v.id} className="rc-hol" style={{ color: `color-mix(in srgb, ${v.color} 55%, var(--text))` }}>{v.name}</span>
            ))}
            <span className="rc-chips">
              {items.slice(0, 3).map(o => {
                const colour = catById.get(o.category_id)?.color ?? T.muted
                const movable = isStored(o)
                return (
                  <span key={o.key} className={`rc-chip${movable ? ' rc-drag' : ''}`} draggable={movable || undefined}
                    title={movable ? `${o.name} · drag to another day` : undefined}
                    onDragStart={movable ? e => {
                      e.stopPropagation()
                      e.dataTransfer.setData(DRAG_TYPE, o.key); e.dataTransfer.setData('text/plain', o.name); e.dataTransfer.effectAllowed = 'move'
                      drag.onDragStart(o)
                    } : undefined}
                    onDragEnd={movable ? drag.onDragEnd : undefined}
                    style={{ background: `${colour}24`, boxShadow: o.state === 'missing' ? `inset 0 0 0 1px ${T.warn}` : undefined }}>
                    <Marker state={o.state} colour={colour} />
                    <span className="rc-chip-name">{o.name}</span>
                    {o.moved && <span title="Moved for this month only" aria-label="Moved for this month only" style={{ fontSize: 10, color: T.muted }}>↷</span>}
                    {o.amount > 0 && <span className="rc-chip-amt">{o.estimated ? '~' : ''}{fmtFull(o.amount)}</span>}
                  </span>
                )
              })}
              {items.length > 3 && <span style={{ fontSize: 11, color: T.muted, paddingLeft: 6 }}>+{items.length - 3} more</span>}
            </span>
            {tick.trackers.length > 0 && (
              <span className="rc-ticks">
                {tick.trackers.map(t => {
                  const done = tick.isDone(t, d), scheduled = t.scheduled_days.includes(d)
                  return (
                    <button key={t.id} type="button" role="checkbox" aria-checked={done} disabled={future} className="rc-tick"
                      aria-label={`${t.name}, ${d} ${monthShort}`}
                      title={`${t.name}${future ? ' · future day' : done ? ' · done' : ' · not done'}${scheduled ? '' : ' · not a counted day'}`}
                      onClick={e => { e.stopPropagation(); tick.onTick(t, d) }} onKeyDown={e => e.stopPropagation()}
                      style={{ '--tc': t.color, opacity: future ? 0.3 : scheduled ? 1 : 0.4 } as CSSProperties}>
                      {done ? '✓' : ''}
                    </button>
                  )
                })}
              </span>
            )}
          </div>
        )
      })}
      <div className="rc-rail" style={{ borderTop: `1px solid ${T.border}`, padding: 8, display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 6, alignItems: 'flex-end' }}>
        {sum > 0 ? (
          <>
            <b style={{ fontSize: 11.5, fontWeight: 500, fontVariantNumeric: 'tabular-nums' }}>{fmtFull(sum)}</b>
            <span style={{ width: '100%', height: 5, borderRadius: 3, background: T.surface2, overflow: 'hidden' }}>
              <i style={{ display: 'block', height: '100%', width: `${Math.round((sum / maxSum) * 100)}%`, background: T.accent, borderRadius: 3 }} />
            </span>
          </>
        ) : <b style={{ fontSize: 11.5, fontWeight: 400, color: T.muted }}>–</b>}
        <small style={{ color: T.muted, fontSize: 10, letterSpacing: 0.5, textTransform: 'uppercase' }}>week {week + 1}</small>
        {tick.trackers.map(t => {
          const w = t.kpi.per_week.find(x => x.start_day <= rowStart && rowStart <= x.end_day)
          if (!w) return null
          const met = w.goal > 0 && w.done >= w.goal
          return (
            <span key={t.id} title={`${t.name}: ${w.done} of ${w.goal} this week`}
              style={{ display: 'flex', alignItems: 'center', gap: 5, width: '100%', fontSize: 11, fontVariantNumeric: 'tabular-nums' }}>
              <i style={{ width: 8, height: 8, borderRadius: 2, background: t.color, flexShrink: 0 }} />
              <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: T.muted }}>{t.name}</span>
              <span style={{ color: met ? T.positive : T.text, fontWeight: met ? 600 : 400 }}>{w.done}/{w.goal}</span>
            </span>
          )
        })}
      </div>
    </>
  )
}
