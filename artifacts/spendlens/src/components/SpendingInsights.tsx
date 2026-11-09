import { useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import {
  getDashboard, getForecast, getReminderCalendar,
  type DashboardCategory, type DashboardData, type Forecast, type GridCategory, type MonthlyGrid, type ReminderCalendar,
} from '../api'
import { currentMonth, monthLabel, shiftMonth } from '../months'
import { MONTHS, T, fmt, fmtFull } from '../theme'
import { Tile } from './HoldingsKpis'
import { card } from './ui'

// The Spending dashboard, now part of the Expense page: KPI tiles above the sheet (SpendingKpis) and the month's
// insights below it (SpendingInsights). Both read one set of numbers from useSpending, for the sheet's month.

export interface Spending { d: DashboardData; fc: Forecast | null; next: Forecast | null; cal: ReminderCalendar | null }

/** The month's dashboard, forecast and reminders. `version` changes whenever the sheet reloads, so an edit shows here too. */
export function useSpending(month: string, version: unknown): Spending | null {
  const [s, setS] = useState<Spending | null>(null)
  useEffect(() => {
    let live = true
    const isCurrent = month === currentMonth()
    Promise.all([
      getDashboard(month),
      getForecast(month).catch(() => null),
      isCurrent ? getForecast(shiftMonth(month, 1)).catch(() => null) : Promise.resolve(null),
      isCurrent ? getReminderCalendar(month).catch(() => null) : Promise.resolve(null),
    ]).then(([d, fc, next, cal]) => { if (live) setS({ d, fc, next, cal }) }).catch(() => { if (live) setS(null) })
    return () => { live = false }
  }, [month, version])
  return s && s.d.month === month ? s : null
}

const sub = { fontSize: 12, color: T.muted } as const
const strong = { color: T.text, fontWeight: 600, fontVariantNumeric: 'tabular-nums' } as const
const signedFull = (v: number) => `${v < 0 ? '−' : '+'}${fmtFull(Math.abs(v))}`
const tone = (good: boolean | null) => (good == null ? T.muted : good ? T.positive : T.negative)

function Pill({ text, color }: { text: string; color: string }) {
  return <span style={{ alignSelf: 'flex-start', marginTop: 4, fontSize: 11, fontWeight: 600, padding: '2px 8px', borderRadius: 999, color, background: `color-mix(in srgb, ${color} 16%, transparent)` }}>{text}</span>
}

function Meter({ pct, color, mark, title }: { pct: number; color: string; mark?: number; title: string }) {
  return (
    <div title={title} style={{ position: 'relative', height: 6, borderRadius: 3, background: T.surface2, marginTop: 6 }}>
      <div style={{ position: 'absolute', inset: '0 auto 0 0', width: `${Math.max(0, Math.min(100, pct))}%`, background: color, borderRadius: 3 }} />
      {mark != null && <div style={{ position: 'absolute', top: -3, bottom: -3, left: `${Math.min(100, mark)}%`, width: 2, background: T.text, opacity: 0.6 }} />}
    </div>
  )
}

/** Where the month stands: days gone, the pace line, what to expect. Shared by the tiles and the insights. */
function facts(s: Spending, month: string) {
  const d = s.d
  const days = d.daily.length
  const now = currentMonth()
  const isCurrent = month === now, isFuture = month > now
  const elapsed = isCurrent ? Math.min(days, new Date().getDate()) : isFuture ? 0 : days
  const spent = d.total_spent, cap = d.budget_cap
  const pace = cap * (elapsed / days)
  const model = isCurrent && s.fc?.available && s.fc.total ? s.fc.total : null
  const projected = model ? model.p50 : isCurrent && elapsed > 0 ? Math.round((spent / elapsed) * days) : spent
  // a single day far above the rest (rent day) would flatten every other day, so the day charts leave it out
  const sorted = d.daily.slice(0, Math.max(elapsed, 1)).slice().sort((a, b) => b - a)
  const outlier = sorted[0] > 0 && sorted[0] > 3 * (sorted[1] || 0) && sorted[0] > 0.25 * spent ? sorted[0] : null
  return { days, isCurrent, isFuture, elapsed, spent, cap, pace, model, projected, outlier }
}

// ---------------------------------------------------------------- the tiles above the sheet

const COMPACT_KEY = 'spendlens.kpisCompact'

export function SpendingKpis({ s, month }: { s: Spending; month: string }) {
  const [compact, setCompact] = useState(() => { try { return localStorage.getItem(COMPACT_KEY) === '1' } catch { return false } })
  const flip = () => setCompact(c => { try { localStorage.setItem(COMPACT_KEY, c ? '0' : '1') } catch { /* storage unavailable */ } return !c })
  const d = s.d
  const f = facts(s, month)
  const { days, isCurrent, isFuture, elapsed, spent, cap, pace, projected } = f
  const left = cap - spent, remaining = days - elapsed
  const planPct = d.income ? (d.savings_amount / d.income) * 100 : 0
  const saveBase = isCurrent ? projected : spent
  const savePct = d.income ? ((d.income - saveBase) / d.income) * 100 : 0

  const noSpend = d.daily.slice(0, elapsed).filter(v => v === 0).length
  const prevNoSpend = d.prev_daily.filter(v => v === 0).length

  // weekend against weekday, per day, leaving out the outlier day
  const [y, m] = month.split('-').map(Number)
  let we = 0, wd = 0, nwe = 0, nwd = 0
  d.daily.slice(0, elapsed).forEach((v, i) => {
    if (f.outlier != null && v === f.outlier) return
    const dow = new Date(y, m - 1, i + 1).getDay()
    if (dow === 0 || dow === 6) { we += v; nwe++ } else { wd += v; nwd++ }
  })
  const weAvg = nwe ? we / nwe : 0, wdAvg = nwd ? wd / nwd : 0

  const today = new Date().getDate()
  const bills = (s.cal?.occurrences ?? []).filter(o => o.amount > 0 && o.state !== 'done' && o.day >= today && o.day <= today + 7).sort((a, b) => a.day - b.day)
  const billsTotal = bills.reduce((t, o) => t + o.amount, 0)

  const mover = d.categories.filter(c => c.spent - c.prev_spent > 0).sort((a, b) => (b.spent - b.prev_spent) - (a.spent - a.prev_spent))[0]
  const moverTarget = mover ? (mover.target_pct / 100) * d.income : 0

  const paceText = Math.abs(spent - pace) <= cap * 0.03 ? 'On pace' : spent > pace ? `Ahead of pace ${signedFull(spent - pace)}` : `Under pace ${signedFull(spent - pace)}`
  const head = (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 6 }}>
      <span style={{ fontSize: 11, letterSpacing: 0.6, textTransform: 'uppercase', color: T.muted, fontWeight: 600 }}>This month</span>
      <button type="button" onClick={flip} style={{ border: 'none', background: 'none', cursor: 'pointer', color: T.accent, fontSize: 12.5, fontWeight: 600, padding: '2px 4px' }}>
        {compact ? 'Show all KPIs' : 'Show less'}
      </button>
    </div>
  )
  if (compact) {
    const item = (label: string, value: ReactNode) => <span style={{ color: T.muted }}>{label} <b style={strong}>{value}</b></span>
    return (
      <>
        {head}
        <section aria-label="Spending KPIs" style={{ ...card, padding: '10px 14px', display: 'flex', alignItems: 'center', gap: '8px 18px', flexWrap: 'wrap', fontSize: 13 }}>
          {item('Spent', <>{fmtFull(spent)}<span style={{ color: T.muted, fontWeight: 400 }}> of {fmt(cap)}</span></>)}
          {isCurrent && <Pill text={paceText} color={Math.abs(spent - pace) <= cap * 0.03 ? T.muted : tone(spent <= pace)} />}
          {isCurrent && left > 0 && remaining > 0 && item('Safe to spend', `${fmtFull(left / remaining)}/day`)}
          {isCurrent && elapsed > 0 && item('Projected', <span style={{ color: projected > cap ? T.negative : T.text }}>{fmt(projected)}</span>)}
          {item('Savings', <span style={{ color: tone(savePct >= planPct) }}>{savePct.toFixed(0)}%</span>)}
          {isCurrent && s.cal && item('Bills in 7 days', fmt(billsTotal))}
        </section>
      </>
    )
  }
  return (
    <>
    {head}
    <section aria-label="Spending KPIs" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: 12 }}>
      <Tile name="Spent" value={fmtFull(spent)}>
        <div style={sub}>of {fmtFull(cap)} budget{d.total_cashback > 0 && <> · {fmtFull(d.total_cashback)} cashback</>}</div>
        <Meter pct={cap ? (spent / cap) * 100 : 0} color={spent > cap ? T.negative : T.accent} mark={isCurrent ? (elapsed / days) * 100 : undefined} title="Spent against the budget; the mark is where you would be today on pace" />
        {isCurrent
          ? <Pill text={paceText} color={Math.abs(spent - pace) <= cap * 0.03 ? T.muted : tone(spent <= pace)} />
          : !isFuture && <Pill text={left >= 0 ? `${fmtFull(left)} under budget` : `${fmtFull(-left)} over budget`} color={tone(left >= 0)} />}
      </Tile>

      {isCurrent ? (
        <Tile name="Safe to spend" value={left > 0 && remaining > 0 ? <>{fmtFull(left / remaining)}<small style={{ fontSize: 14, color: T.muted, fontWeight: 600 }}> /day</small></> : <span style={{ color: T.negative }}>{fmtFull(Math.max(0, left))}</span>}>
          <div style={sub}>{left > 0 ? <>{fmtFull(left)} left for the next {remaining} day{remaining === 1 ? '' : 's'}</> : 'The budget is used up'}</div>
        </Tile>
      ) : (
        <Tile name={left >= 0 ? 'Left unspent' : 'Overspent'} value={<span style={{ color: tone(left >= 0) }}>{fmtFull(Math.abs(left))}</span>}>
          <div style={sub}>{d.income ? ((Math.abs(left) / d.income) * 100).toFixed(1) : 0}% of income</div>
        </Tile>
      )}

      {isCurrent && elapsed > 0 ? (
        <Tile name="Projected month-end" value={<span style={{ color: projected > cap ? T.negative : T.text }}>{fmtFull(projected)}</span>}>
          {f.model && <div style={sub}>likely {fmt(f.model.p10)} – {fmt(f.model.p90)}</div>}
          {cap > 0 && <Pill text={projected <= cap ? `${fmtFull(cap - projected)} under the cap` : `${fmtFull(projected - cap)} over the cap`} color={tone(projected <= cap)} />}
        </Tile>
      ) : (
        <Tile name={`Against ${monthLabel(d.prev_month).split(' ')[0]}`} value={d.prev_total > 0 ? <span style={{ color: tone(spent <= d.prev_total) }}>{signedFull(spent - d.prev_total)}</span> : '—'}>
          <div style={sub}>{d.prev_total > 0 ? <>{fmtFull(d.prev_total)} spent then</> : 'Nothing logged that month'}</div>
        </Tile>
      )}

      <Tile name="Savings rate" value={<span style={{ color: tone(savePct >= planPct) }}>{savePct.toFixed(0)}%</span>}>
        <div style={sub}>{isCurrent ? 'projected' : 'of income'} · plan {planPct.toFixed(0)}%</div>
        <div style={sub}><b style={strong}>{fmtFull(d.income - saveBase)}</b> saved{isCurrent ? ' at this pace' : ''}</div>
        <Meter pct={savePct} color={tone(savePct >= planPct)} mark={planPct} title="Savings rate; the mark is your plan" />
      </Tile>

      {!isFuture && (
        <Tile name="No-spend days" value={<>{noSpend}<small style={{ fontSize: 14, color: T.muted, fontWeight: 600 }}> of {elapsed}</small></>}>
          <div style={sub}>Days with nothing logged</div>
          <div style={sub}>{monthLabel(d.prev_month).split(' ')[0]}: <b style={strong}>{prevNoSpend}</b> in the whole month</div>
        </Tile>
      )}

      {nwe > 0 && nwd > 0 && wdAvg > 0 && (
        <Tile name="Weekend effect" value={`${(weAvg / wdAvg).toFixed(1)}×`}>
          <div style={sub}>A weekend day costs <b style={strong}>{fmtFull(weAvg)}</b>, a weekday <b style={strong}>{fmtFull(wdAvg)}</b></div>
          {f.outlier != null && <div style={sub}>Leaves out the {fmt(f.outlier)} day</div>}
        </Tile>
      )}

      {isCurrent && s.cal && (
        <Tile name="Bills in the next 7 days" value={fmtFull(billsTotal)}>
          <div style={sub}>{bills.length ? <>{bills.length} due · next <b style={strong}>{bills[0].name}</b> on the {bills[0].day}</> : 'Nothing due this week'}</div>
          <div style={sub}>From your calendar reminders</div>
        </Tile>
      )}

      {mover && (
        <Tile name="Biggest change" value={<span style={{ color: T.negative }}>{signedFull(mover.spent - mover.prev_spent)}</span>}>
          <div style={sub}>{mover.icon} <b style={strong}>{mover.name}</b> vs {monthLabel(d.prev_month).split(' ')[0]}{mover.prev_spent > 0 ? ` (+${Math.round((mover.spent / mover.prev_spent - 1) * 100)}%)` : ''}</div>
          {moverTarget > 0 && mover.spent > moverTarget && <Pill text={`Over its target by ${fmtFull(mover.spent - moverTarget)}`} color={T.warn} />}
        </Tile>
      )}
    </section>
    </>
  )
}

// ---------------------------------------------------------------- the insights below the sheet

const panel: CSSProperties = { ...card, padding: '16px 18px', minWidth: 0, height: '100%', boxSizing: 'border-box' }
const row = (min: number): CSSProperties => ({ display: 'grid', gridTemplateColumns: `repeat(auto-fit, minmax(${min}px, 1fr))`, gap: 14, alignItems: 'stretch' })

function Panel({ title, hint, children, style }: { title: string; hint?: string; children: ReactNode; style?: CSSProperties }) {
  return (
    <section style={{ ...panel, ...style }}>
      <h3 style={{ fontSize: 15, margin: 0 }}>{title}</h3>
      {hint && <p style={{ color: T.muted, fontSize: 12.5, margin: '2px 0 12px', lineHeight: 1.5 }}>{hint}</p>}
      {children}
    </section>
  )
}

export function SpendingInsights({ s, month, grid, onPickDay, onReview }: {
  s: Spending; month: string; grid: MonthlyGrid; onPickDay: (day: number) => void; onReview: () => void
}) {
  const d = s.d
  const f = facts(s, month)
  return (
    <section id="spending-insights" aria-label={`Insights for ${monthLabel(month)}`} style={{ display: 'flex', flexDirection: 'column', gap: 14, marginTop: 10, scrollMarginTop: 120 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
        <h2 style={{ fontSize: 17, fontWeight: 700, margin: 0 }}>Insights for {monthLabel(month)}</h2>
        <span style={{ fontSize: 12.5, color: T.muted }}>each category against its target, with six months of history</span>
        <button type="button" onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
          style={{ border: 'none', background: 'none', cursor: 'pointer', color: T.accent, fontSize: 12.5, fontWeight: 600, padding: '2px 4px' }}>↑ Sheet</button>
      </div>
      <CategoryCards d={d} />
      <div style={row(340)}>
        <DailyRhythm s={s} f={f} grid={grid} month={month} onPickDay={onPickDay} />
        {s.next?.available && s.next.total && <NextMonth f={s.next} />}
      </div>
      <div style={row(340)}>
        <Panel title="Pace" hint={`${f.isCurrent ? `Day ${f.elapsed} of ${f.days}. ` : ''}Point at the chart to see a day's numbers.`}>
          <Pace s={s} f={f} />
        </Panel>
        <Panel title="12 months" hint="Green is within budget, red is over. The line is the cap.">
          <Trend d={d} month={month} />
        </Panel>
      </div>
      <div style={row(340)}>
        <Panel title="Worth a look" hint="Things you can act on.">
          <Looks d={d} f={f} onReview={onReview} />
        </Panel>
        <Panel title="Largest expenses" hint="This month.">
          {d.top_expenses.length === 0 && <div style={{ fontSize: 12.5, color: T.muted }}>Nothing logged yet.</div>}
          {d.top_expenses.map((e, i) => (
            <div key={i} style={{ display: 'grid', gridTemplateColumns: '52px minmax(0, 1fr) auto', gap: 10, alignItems: 'baseline', padding: '7px 0', borderTop: i ? `1px solid ${T.hairline}` : undefined, fontSize: 13 }}>
              <span style={{ color: T.muted, fontSize: 12 }}>{Number(e.date.slice(8))} {MONTHS[Number(e.date.slice(5, 7)) - 1].slice(0, 3)}</span>
              <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{e.icon} {e.subcategory ?? e.category}{e.note && <span style={{ color: T.muted }}> · {e.note}</span>}</span>
              <b style={{ fontVariantNumeric: 'tabular-nums' }}>{fmtFull(e.amount)}</b>
            </div>
          ))}
        </Panel>
      </div>
    </section>
  )
}

/** One card per category, all the same size: a ring against the target, six months of history and the change from last month. */
function CategoryCards({ d }: { d: DashboardData }) {
  const cats = useMemo(() => d.categories.filter(c => c.spent !== 0 || c.prev_spent !== 0).sort((a, b) => b.spent - a.spent), [d])
  const topSub = useMemo(() => {
    const m = new Map<number, { name: string; spent: number }>()
    for (const s of d.subcategories) { if (s.subcategory_id != null && !m.has(s.category_id)) m.set(s.category_id, { name: s.name, spent: s.spent }) }
    return m
  }, [d])
  if (!cats.length) return <div style={{ ...card, padding: 16, color: T.muted, fontSize: 13 }}>Nothing logged this month yet.</div>
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(230px, 1fr))', gridAutoRows: '1fr', gap: 12 }}>
      {cats.map(c => <CategoryCard key={c.id} c={c} d={d} top={topSub.get(c.id)} />)}
    </div>
  )
}

function CategoryCard({ c, d, top }: { c: DashboardCategory; d: DashboardData; top?: { name: string; spent: number } }) {
  const target = (c.target_pct / 100) * d.income
  const ratio = target > 0 ? c.spent / target : d.total_spent ? c.spent / d.total_spent : 0
  const over = target > 0 && c.spent > target
  const colour = c.color || T.accent
  const R = 21, C = 2 * Math.PI * R
  const hist = c.history?.length ? c.history : [c.spent]
  const max = Math.max(...hist, target, 1)
  const delta = c.spent - c.prev_spent
  const ell: CSSProperties = { whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }
  return (
    <div style={{ ...card, padding: '13px 14px', display: 'flex', flexDirection: 'column', gap: 8, minWidth: 0, boxSizing: 'border-box' }}>
      <div style={{ display: 'grid', gridTemplateColumns: '52px minmax(0, 1fr)', gap: 12, alignItems: 'center' }}>
        <svg width="52" height="52" viewBox="0 0 52 52" role="img" aria-label={target > 0 ? `${Math.round(ratio * 100)}% of target` : `${Math.round(ratio * 100)}% of the month's spend`}>
          <circle cx="26" cy="26" r={R} fill="none" stroke={T.surface2} strokeWidth="6" />
          <circle cx="26" cy="26" r={R} fill="none" stroke={over ? T.negative : colour} strokeWidth="6" strokeLinecap="round"
            strokeDasharray={`${Math.min(1, Math.max(0, ratio)) * C} ${C}`} transform="rotate(-90 26 26)" />
          <text x="26" y="31" textAnchor="middle" fontSize="15">{c.icon}</text>
        </svg>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontWeight: 650, fontSize: 13, ...ell }} title={c.name}>{c.name}</div>
          <div style={{ fontSize: 17, fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>{fmtFull(c.spent)}</div>
          <div style={{ fontSize: 11.5, color: over ? T.negative : T.muted, ...ell }}>
            {target > 0 ? `${Math.round(ratio * 100)}% of ${fmt(target)} target` : `${Math.round(ratio * 100)}% of the month's spend`}
          </div>
        </div>
      </div>
      <div style={{ fontSize: 11.5, color: T.muted, ...ell }} title={top ? `${top.name}: ${fmtFull(top.spent)}` : undefined}>
        {top ? <>Top: <b style={{ color: T.text, fontWeight: 600 }}>{top.name}</b> {fmt(top.spent)}</> : ' '}
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, marginTop: 'auto' }}>
        <svg width="86" height="24" viewBox="0 0 86 24" role="img" aria-label={`Last six months: ${hist.map(v => fmt(v)).join(', ')}`}>
          {target > 0 && <line x1="0" x2="86" y1={22 - (target / max) * 20} y2={22 - (target / max) * 20} stroke={T.muted} strokeDasharray="2 3" strokeOpacity="0.6" />}
          <path d={hist.map((v, i) => `${i ? 'L' : 'M'}${(hist.length > 1 ? (i / (hist.length - 1)) * 80 : 40) + 2},${(22 - (v / max) * 20).toFixed(1)}`).join('')} fill="none" stroke={colour} strokeWidth="1.8" />
          <circle cx={82} cy={22 - (hist[hist.length - 1] / max) * 20} r="2.6" fill={colour} />
        </svg>
        <span style={{ fontSize: 11, fontWeight: 600, padding: '2px 8px', borderRadius: 999, whiteSpace: 'nowrap',
          color: delta > 0 ? T.warn : T.positive, background: `color-mix(in srgb, ${delta > 0 ? T.warn : T.positive} 16%, transparent)` }}>
          {c.prev_spent === 0 && c.spent > 0 ? 'New this month' : `${signedFull(delta)} vs ${monthLabel(d.prev_month).split(' ')[0].slice(0, 3)}`}
        </span>
      </div>
    </div>
  )
}

const WEEK = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

/** The month day by day: a small calendar shaded by spend (green = nothing spent), the day's biggest category as a dot,
 *  bills from the reminders as a top mark, and beside it three facts and the weekday averages. Clicking a day lists its
 *  entries and points the sheet at that date. */
function DailyRhythm({ s, f, grid, month, onPickDay }: {
  s: Spending; f: ReturnType<typeof facts>; grid: MonthlyGrid; month: string; onPickDay: (day: number) => void
}) {
  const d = s.d
  const [pick, setPick] = useState<number | null>(null)
  useEffect(() => setPick(null), [month])
  const [y, m] = month.split('-').map(Number)
  const { elapsed, outlier, days, cap, spent, isCurrent } = f
  const first = (new Date(y, m - 1, 1).getDay() + 6) % 7
  const max = Math.max(1, ...d.daily.slice(0, elapsed).filter(v => outlier == null || v !== outlier))
  const today = isCurrent ? new Date().getDate() : 0
  const mon = MONTHS[m - 1].slice(0, 3)

  const amountOn = (c: GridCategory, day: number) => c.days[String(day)]?.amount ?? 0
  const topCat = (day: number) => grid.categories.reduce<GridCategory | null>((best, c) => (amountOn(c, day) > 0 && (!best || amountOn(c, day) > amountOn(best, day)) ? c : best), null)
  const bills = new Map<number, string[]>()
  for (const o of s.cal?.occurrences ?? []) if (o.amount > 0) bills.set(o.day, [...(bills.get(o.day) ?? []), o.name])

  // the facts
  let big = 0, streak = 0, best = 0
  for (let day = 1; day <= elapsed; day++) {
    const v = d.daily[day - 1]
    if ((outlier == null || v !== outlier) && v > 0 && (!big || v > d.daily[big - 1])) big = day
    streak = v === 0 ? streak + 1 : 0
    best = Math.max(best, streak)
  }
  const noSpend = d.daily.slice(0, elapsed).filter(v => v === 0).length
  const avg = elapsed ? (spent - (outlier ?? 0)) / elapsed : 0
  const allow = days ? (cap - (outlier ?? 0)) / days : 0
  const bigCat = big ? topCat(big) : null

  // weekday averages, leaving out the outlier day
  const sum = [0, 0, 0, 0, 0, 0, 0], n = [0, 0, 0, 0, 0, 0, 0]
  d.daily.slice(0, elapsed).forEach((v, i) => {
    if (outlier != null && v === outlier) return
    const k = (new Date(y, m - 1, i + 1).getDay() + 6) % 7
    sum[k] += v; n[k]++
  })
  const wavg = sum.map((t, i) => (n[i] ? t / n[i] : 0)), wmax = Math.max(1, ...wavg)

  const choose = (day: number) => { setPick(day); onPickDay(day) }
  const picked = pick ? grid.categories.filter(c => amountOn(c, pick) !== 0) : []
  const fact = (label: string, value: ReactNode, note: ReactNode, color?: string) => (
    <div style={{ background: T.surface2, borderRadius: 9, padding: '8px 10px', minWidth: 0 }}>
      <div style={{ fontSize: 11, color: T.muted, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{label}</div>
      <div style={{ fontSize: 15, fontWeight: 700, fontVariantNumeric: 'tabular-nums', color }}>{value}</div>
      <div style={{ fontSize: 11, color: T.muted, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{note}</div>
    </div>
  )

  return (
    <Panel title="Daily rhythm" hint={`Darker days cost more, green days had no spending. The dot is the day's biggest category${s.cal ? ', a top mark is a bill from your reminders' : ''}.${outlier != null ? ` The ${fmt(outlier)} day is left out of the shading.` : ''}`}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 22, alignItems: 'flex-start' }}>
        <div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 34px)', gap: 4 }}>
            {WEEK.map(w => <div key={w} style={{ fontSize: 10, color: T.muted, textAlign: 'center', textTransform: 'uppercase', letterSpacing: 0.4 }}>{w.slice(0, 2)}</div>)}
            {Array.from({ length: first }, (_, i) => <div key={`e${i}`} />)}
            {d.daily.map((v, i) => {
              const day = i + 1, future = day > elapsed
              const a = outlier != null && v === outlier ? 1 : Math.min(1, v / max)
              const tc = future ? null : topCat(day)
              const bill = bills.get(day)
              const look: CSSProperties = future
                ? { background: 'transparent', border: `1px dashed ${T.border}`, color: T.muted, cursor: 'default' }
                : v === 0 ? { background: `color-mix(in srgb, ${T.positive} 16%, transparent)`, color: T.text }
                : { background: `color-mix(in srgb, ${T.accent} ${Math.round(14 + a * 72)}%, ${T.surface})`, color: a > 0.55 ? '#fff' : T.text }
              return (
                <button key={day} type="button" disabled={future} onClick={() => choose(day)}
                  title={`${day} ${mon}: ${future ? 'to come' : fmtFull(v)}${bill ? ` · bill: ${bill.join(', ')}` : ''}`}
                  aria-label={`${day} ${mon}, ${future ? 'to come' : v === 0 ? 'no spending' : fmtFull(v)}`}
                  style={{
                    position: 'relative', width: 34, height: 34, borderRadius: 7, border: 'none', padding: '3px 4px', font: 'inherit', fontSize: 10.5, fontWeight: 600,
                    textAlign: 'left', lineHeight: 1, verticalAlign: 'top', cursor: 'pointer', ...look,
                    outline: pick === day ? `2px solid ${T.text}` : undefined, outlineOffset: 1,
                    boxShadow: day === today ? `inset 0 0 0 2px ${T.accent}` : undefined,
                  }}>
                  {day}
                  {tc && <i style={{ position: 'absolute', right: 4, bottom: 4, width: 6, height: 6, borderRadius: '50%', background: tc.color || T.accent, boxShadow: `0 0 0 1.5px ${T.surface}` }} />}
                  {bill && <span style={{ position: 'absolute', right: 3, top: 2, fontSize: 8, color: T.warn }}>●</span>}
                </button>
              )
            })}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 10.5, color: T.muted, marginTop: 10, flexWrap: 'wrap' }}>
            less
            {[20, 50, 86].map(p => <i key={p} style={{ width: 12, height: 9, borderRadius: 2, background: `color-mix(in srgb, ${T.accent} ${p}%, ${T.surface})` }} />)}
            more · <i style={{ width: 12, height: 9, borderRadius: 2, background: `color-mix(in srgb, ${T.positive} 16%, transparent)` }} /> none
          </div>
        </div>

        <div style={{ flex: '1 1 240px', minWidth: 0 }}>
          {elapsed > 0 && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 8, marginBottom: 14 }}>
              {fact('Biggest day', big ? fmt(d.daily[big - 1]) : '—', big ? `${big} ${mon}${bigCat ? ` · ${bigCat.name}` : ''}` : 'nothing yet')}
              {fact('No-spend streak', `${best} day${best === 1 ? '' : 's'}`, `${noSpend} no-spend day${noSpend === 1 ? '' : 's'}`)}
              {fact('Average a day', fmtFull(avg), `budget allows ${fmtFull(allow)}`, avg > allow ? T.warn : T.positive)}
            </div>
          )}
          <div style={{ display: 'grid', gridTemplateColumns: '30px minmax(0, 1fr) 62px', gap: '7px 10px', alignItems: 'center', fontSize: 12 }}>
            {WEEK.map((w, i) => [
              <span key={`l${w}`} style={{ color: T.muted }}>{w}</span>,
              <span key={`b${w}`} style={{ height: 8, borderRadius: 4, background: T.surface2, overflow: 'hidden' }}>
                <i style={{ display: 'block', height: '100%', width: `${(wavg[i] / wmax) * 100}%`, borderRadius: 4, background: i >= 5 ? T.warn : T.accent }} />
              </span>,
              <span key={`v${w}`} style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{fmtFull(wavg[i])}</span>,
            ])}
          </div>
        </div>
      </div>
      <div style={{ marginTop: 12, fontSize: 12.5, padding: '9px 11px', borderRadius: 9, background: T.surface2, minHeight: 18 }}>
        {pick == null ? <span style={{ color: T.muted }}>Click a day to see what was spent and find it in the sheet.</span> : (
          <>
            <b style={{ fontWeight: 650 }}>{new Date(y, m - 1, pick).toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'short' })}</b>
            {' · '}
            {picked.length ? <>{fmtFull(d.daily[pick - 1])} — {picked.map((c, i) => <span key={c.id}>{i ? ' · ' : ''}{c.icon} {c.name} <b>{fmtFull(amountOn(c, pick))}</b></span>)}</> : 'no spending'}
            {bills.get(pick) && <> · bill due: {bills.get(pick)!.join(', ')}</>}
          </>
        )}
      </div>
    </Panel>
  )
}

function cumulative(a: number[], upTo = a.length) { let s = 0; return a.slice(0, upTo).map(v => (s += v)) }

/** A round step for about four gridlines up to `max`: 1, 2 or 5 times a power of ten. */
function niceStep(max: number) {
  const raw = max / 4, p = 10 ** Math.floor(Math.log10(raw || 1)), n = raw / p
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * p
}

/** Spending so far against the budget line and last month, with ₹ and day axes. Pointing at the chart shows that
 *  day's numbers. The drawing is measured in real pixels so its labels stay the size of the page's text. */
function Pace({ s, f }: { s: Spending; f: ReturnType<typeof facts> }) {
  const d = s.d
  const { days, elapsed, spent, cap, isCurrent, model } = f
  const box = useRef<HTMLDivElement>(null)
  const [w, setW] = useState(0)
  const [hover, setHover] = useState<number | null>(null)
  useEffect(() => {
    const el = box.current
    if (!el) return
    const measure = () => setW(Math.floor(el.clientWidth))
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const cur = cumulative(d.daily, isCurrent ? elapsed : days), prev = cumulative(d.prev_daily)
  const top = Math.max(1, cap, ...cur, ...prev, ...(model ? [model.p90] : []))
  const step = niceStep(top), yMax = Math.ceil(top / step) * step
  const W = Math.max(300, w), H = 200, L = 50, R = 12, TP = 10, B = 24
  const x = (day: number) => L + ((day - 1) / Math.max(1, days - 1)) * (W - L - R)
  const y = (v: number) => TP + (1 - v / yMax) * (H - TP - B)
  const line = (a: number[]) => a.map((v, i) => `${i ? 'L' : 'M'}${x(i + 1).toFixed(1)},${y(v).toFixed(1)}`).join('')
  const colour = spent > cap ? T.negative : T.accent
  const forecastAt = (day: number) => (model && day > elapsed ? spent + ((model.p50 - spent) * (day - elapsed)) / Math.max(1, days - elapsed) : null)
  const yTicks = Array.from({ length: Math.round(yMax / step) + 1 }, (_, i) => i * step)
  const xTicks = [...new Set([1, 5, 10, 15, 20, 25, days])].filter(t => t <= days)
  const [yy, mm] = d.month.split('-').map(Number)
  const mon = MONTHS[mm - 1].slice(0, 3)

  const pick = (e: React.MouseEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect()
    const px = ((e.clientX - r.left) / r.width) * W
    setHover(Math.min(days, Math.max(1, Math.round(((px - L) / (W - L - R)) * (days - 1)) + 1)))
  }
  const tip = hover == null ? null : [
    { label: 'This month', value: hover <= cur.length ? cur[hover - 1] : null, color: colour },
    { label: 'Forecast', value: forecastAt(hover), color: T.accent },
    { label: 'Budget line', value: (cap * hover) / days, color: T.muted },
    { label: monthLabel(d.prev_month).split(' ')[0], value: hover <= prev.length ? prev[hover - 1] : null, color: T.muted },
  ].filter(t => t.value != null)

  return (
    <div ref={box} style={{ position: 'relative', minHeight: H }}>
      {w > 0 && (
        <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" style={{ display: 'block' }} aria-label="Spending pace"
          onMouseMove={pick} onMouseLeave={() => setHover(null)}>
          {yTicks.map(v => (
            <g key={v}>
              <line x1={L} x2={W - R} y1={y(v)} y2={y(v)} stroke={T.hairline} />
              <text x={L - 8} y={y(v) + 4} textAnchor="end" fontSize="11" fill={T.muted}>{fmt(v)}</text>
            </g>
          ))}
          {xTicks.map(t => <text key={t} x={x(t)} y={H - 6} textAnchor="middle" fontSize="11" fill={T.muted}>{t}</text>)}
          <line x1={x(1)} y1={y(cap / days)} x2={x(days)} y2={y(cap)} stroke={T.muted} strokeWidth="1.5" strokeDasharray="5 4" />
          {prev.length > 1 && <path d={line(prev)} fill="none" stroke={T.muted} strokeOpacity="0.45" strokeWidth="1.5" />}
          {cur.length > 1 && <path d={`${line(cur)}L${x(cur.length)},${y(0)}L${x(1)},${y(0)}Z`} fill={colour} fillOpacity="0.14" />}
          {cur.length > 1 && <path d={line(cur)} fill="none" stroke={colour} strokeWidth="2.5" />}
          {model && elapsed > 0 && elapsed < days && (
            <>
              <polygon points={`${x(elapsed)},${y(spent)} ${x(days)},${y(model.p90)} ${x(days)},${y(model.p10)}`} fill={T.accent} fillOpacity="0.12" />
              <line x1={x(elapsed)} y1={y(spent)} x2={x(days)} y2={y(model.p50)} stroke={T.accent} strokeWidth="2" strokeDasharray="2 4" />
            </>
          )}
          {isCurrent && elapsed > 0 && hover == null && <line x1={x(elapsed)} y1={TP} x2={x(elapsed)} y2={H - B} stroke={T.text} strokeOpacity="0.25" />}
          {hover != null && (
            <>
              <line x1={x(hover)} y1={TP} x2={x(hover)} y2={H - B} stroke={T.text} strokeOpacity="0.45" />
              {tip!.map(t => <circle key={t.label} cx={x(hover)} cy={y(t.value!)} r="3.5" fill={t.color} stroke={T.surface} strokeWidth="1.5" />)}
            </>
          )}
          <rect x={L} y={TP} width={W - L - R} height={H - TP - B} fill="transparent" />
        </svg>
      )}
      {hover != null && tip && (
        <div style={{
          position: 'absolute', top: 6, pointerEvents: 'none', zIndex: 2, minWidth: 150,
          ...(x(hover) > W / 2 ? { right: W - x(hover) + 10 } : { left: x(hover) + 10 }),
          background: T.surface, border: `1px solid ${T.border}`, borderRadius: 8, padding: '7px 10px', fontSize: 12, boxShadow: '0 4px 14px rgba(0,0,0,.18)',
        }}>
          <div style={{ fontWeight: 650, marginBottom: 4 }}>{new Date(yy, mm - 1, hover).toLocaleDateString('en-IN', { weekday: 'short' })} {hover} {mon}</div>
          {tip.map(t => (
            <div key={t.label} style={{ display: 'flex', justifyContent: 'space-between', gap: 14 }}>
              <span style={{ color: T.muted, display: 'inline-flex', alignItems: 'center', gap: 6 }}><i style={{ width: 8, height: 8, borderRadius: '50%', background: t.color }} />{t.label}</span>
              <b style={{ fontVariantNumeric: 'tabular-nums' }}>{fmtFull(t.value!)}</b>
            </div>
          ))}
          {hover <= cur.length && <div style={{ color: T.muted, marginTop: 4 }}>spent that day {fmtFull(d.daily[hover - 1])}</div>}
        </div>
      )}
      <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', fontSize: 11, color: T.muted, marginTop: 6 }}>
        <span><b style={{ color: colour }}>━</b> this month</span>
        <span>┅ budget line {fmtFull(cap)}</span>
        {model && <span><b style={{ color: T.accent }}>┅</b> forecast</span>}
        {d.prev_total > 0 && <span style={{ opacity: 0.7 }}>━ {monthLabel(d.prev_month)}</span>}
      </div>
    </div>
  )
}

function Trend({ d, month }: { d: DashboardData; month: string }) {
  const max = Math.max(1, ...d.trend.map(t => Math.max(t.total, t.budget_cap)))
  return (
    <>
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 6, height: 132 }}>
        {d.trend.map(t => {
          const over = t.total > t.budget_cap
          return (
            <div key={t.month} title={`${monthLabel(t.month)}: ${fmtFull(t.total)} of ${fmtFull(t.budget_cap)}`} style={{ flex: 1, position: 'relative', height: '100%', display: 'flex', alignItems: 'flex-end' }}>
              <div style={{ width: '100%', minHeight: t.total ? 2 : 0, height: `${(t.total / max) * 100}%`, borderRadius: '4px 4px 0 0', background: over ? T.negative : T.accent2, opacity: t.month === month ? 1 : 0.5 }} />
              <div style={{ position: 'absolute', left: 0, right: 0, bottom: `${(t.budget_cap / max) * 100}%`, height: 2, background: over ? T.negative : T.muted, opacity: 0.8 }} />
            </div>
          )
        })}
      </div>
      <div style={{ display: 'flex', gap: 6, marginTop: 6, fontSize: 10, color: T.muted }}>
        {d.trend.map(t => <span key={t.month} style={{ flex: 1, textAlign: 'center' }}>{MONTHS[Number(t.month.slice(5)) - 1].slice(0, 3)}</span>)}
      </div>
    </>
  )
}

function NextMonth({ f }: { f: Forecast }) {
  const t = f.total!, cap = f.budget_cap
  const cats = (f.categories ?? []).slice(0, 5)
  const bt = f.backtest
  return (
    <Panel style={{ height: 'auto', flex: 1 }} title={`Next month · ${monthLabel(f.month)}`} hint="Likely range is the middle 80% of outcomes.">
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap', marginBottom: 10 }}>
        <span style={{ fontSize: 22, fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>{fmtFull(t.p50)}</span>
        <span style={{ fontSize: 12, color: T.muted }}>likely {fmt(t.p10)} – {fmt(t.p90)}</span>
        {cap > 0 && <Pill text={t.p50 <= cap ? `${fmtFull(cap - t.p50)} under the cap` : `${fmtFull(t.p50 - cap)} over the cap`} color={tone(t.p50 <= cap)} />}
      </div>
      <div style={{ display: 'grid', gap: 6, fontSize: 12.5 }}>
        {cats.map(c => (
          <div key={c.id} style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 70px 100px', gap: 10, alignItems: 'baseline' }}>
            <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{c.icon} {c.name}{c.fixed && <span style={{ color: T.muted, fontSize: 10.5 }}> · fixed</span>}</span>
            <b style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{fmt(c.p50)}</b>
            <span style={{ textAlign: 'right', color: T.muted, fontSize: 11 }}>{c.reliable || c.fixed ? `${fmt(c.p10)} – ${fmt(c.p90)}` : 'low confidence'}</span>
          </div>
        ))}
      </div>
      {bt && bt.mape_model != null && bt.mape_base != null && (
        <div style={{ fontSize: 11.5, color: T.muted, marginTop: 12 }}>
          Backtest on the last {bt.months} months: off by {(bt.mape_model * 100).toFixed(0)}% on average, against {(bt.mape_base * 100).toFixed(0)}% for "same as last month"{f.model_beats_baseline ? '.' : ', so treat it as a rough guide.'}
        </div>
      )}
    </Panel>
  )
}

function Looks({ d, f, onReview }: { d: DashboardData; f: ReturnType<typeof facts>; onReview: () => void }) {
  const looks: ReactNode[] = []
  const rows = d.categories.filter(c => c.spent !== 0).map(c => { const target = (c.target_pct / 100) * d.income; return { ...c, target, delta: c.target_pct > 0 ? c.spent - target : 0 } })
  rows.filter(r => r.delta > 0).sort((a, b) => b.delta - a.delta).slice(0, 2)
    .forEach(r => looks.push(<span key={`o${r.id}`}><b>{r.icon} {r.name}</b> is {Math.round((r.delta / r.target) * 100)}% over target ({signedFull(r.delta)})</span>))
  if (f.isCurrent && f.elapsed > 0 && f.cap > 0 && f.projected > f.cap) looks.push(<span key="proj">At this pace you will end <b>{fmtFull(f.projected - f.cap)}</b> over the budget cap</span>)
  const jump = rows.find(r => r.prev_spent > 0 && r.spent > r.prev_spent * 1.5 && r.spent - r.prev_spent > 0.02 * d.income && r.delta <= 0)
  if (jump) looks.push(<span key="jump"><b>{jump.icon} {jump.name}</b> is up {signedFull(jump.spent - jump.prev_spent)} on last month</span>)
  if (d.unassigned_count > 0) looks.push(
    <span key="un" style={{ display: 'flex', alignItems: 'center', gap: 10, justifyContent: 'space-between', flexWrap: 'wrap' }}>
      <span><b>{d.unassigned_count}</b> {d.unassigned_count === 1 ? 'entry has' : 'entries have'} no sub-category</span>
      <button type="button" onClick={onReview} style={{ border: `1px solid ${T.border}`, background: T.surface2, color: T.text, borderRadius: 7, padding: '4px 10px', fontSize: 12, cursor: 'pointer' }}>Review →</button>
    </span>)
  if (!looks.length) return <div style={{ fontSize: 12.5, color: T.muted }}>Nothing unusual this month.</div>
  return (
    <>
      {looks.map((l, i) => (
        <div key={i} style={{ display: 'flex', gap: 10, padding: '7px 0', borderTop: i ? `1px solid ${T.hairline}` : undefined, fontSize: 13 }}>
          <span style={{ color: T.warn }}>●</span><div style={{ flex: 1, minWidth: 0 }}>{l}</div>
        </div>
      ))}
    </>
  )
}
