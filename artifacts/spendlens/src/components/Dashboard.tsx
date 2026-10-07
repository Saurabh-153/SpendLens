import { useEffect, useState } from 'react'
import { getDashboard, getForecast, type DashboardData, type Forecast } from '../api'
import { currentMonth, monthLabel, shiftMonth } from '../months'
import MonthPicker from './MonthPicker'
import { MONTHS, T, fmt, fmtFull } from '../theme'
import ExposureDashboard from './ExposureDashboard'
import PortfolioDashboard from './PortfolioDashboard'
import { Card, accentStyle, label } from './ui'

type Tab = 'expense' | 'portfolio' | 'exposure'

export default function Dashboard() {
  const [tab, setTab] = useState<Tab>(() => (['portfolio', 'exposure'].includes(new URLSearchParams(location.search).get('tab') ?? '') ? new URLSearchParams(location.search).get('tab') as Tab : 'expense'))
  const tabBtn = (id: Tab, text: string) => (
    <button onClick={() => setTab(id)} style={{
      background: 'none', border: 'none', borderBottom: `2px solid ${tab === id ? T.accent : 'transparent'}`,
      color: tab === id ? T.text : T.muted, padding: '12px 18px', fontSize: 13.5, fontWeight: 'var(--display-weight, 500)' as unknown as number, cursor: 'pointer', fontFamily: 'var(--font-display, inherit)',
    }}>{text}</button>
  )
  return (
    <div style={{ padding: 20 }}>
      <div style={{ borderBottom: `1px solid ${T.hairline}`, marginBottom: 24 }}>
        {tabBtn('expense', 'Spending')}
        {tabBtn('portfolio', 'Wealth')}
        {tabBtn('exposure', 'Asset Mix')}
      </div>
      {tab === 'expense' ? <ExpenseDashboard /> : tab === 'portfolio' ? <PortfolioDashboard /> : <ExposureDashboard />}
    </div>
  )
}

const title = (t: string, right?: string) => (
  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
    <span style={{ ...label, fontSize: 12.5, letterSpacing: 0.8 }}>{t}</span>
    {right && <span style={{ ...label, fontSize: 10.5 }}>{right}</span>}
  </div>
)

function Kpi({ name, children, sub, extra, accent = T.accent }: { name: string; children: React.ReactNode; sub: React.ReactNode; extra?: React.ReactNode; accent?: string }) {
  return (
    <Card style={{ padding: '14px 18px', ...accentStyle(accent) }}>
      <div style={label}>{name}</div>
      <div style={{ fontFamily: 'var(--font-display, inherit)', fontSize: 26, fontWeight: 700, margin: '4px 0 2px' }}>{children}</div>
      <div style={{ fontSize: 11.5, color: T.muted }}>{sub}</div>
      {extra}
    </Card>
  )
}

const chip = (text: string, tone: 'good' | 'bad' | 'neutral'): React.ReactNode => (
  <span style={{
    display: 'inline-block', marginTop: 8, fontSize: 11, fontWeight: 600, padding: '3px 9px', borderRadius: 10,
    color: tone === 'good' ? T.positive : tone === 'bad' ? T.negative : T.muted,
    background: tone === 'good' ? 'rgba(34,197,94,.14)' : tone === 'bad' ? 'rgba(244,63,94,.14)' : T.surface2,
  }}>{text}</span>
)

const signedFull = (v: number) => `${v < 0 ? '−' : '+'}${fmtFull(Math.abs(v))}`

function cumulative(a: number[], upTo = a.length): number[] {
  let s = 0
  return a.slice(0, upTo).map(v => (s += v))
}

function NextMonth({ f }: { f: Forecast }) {
  const t = f.total!
  const cap = f.budget_cap
  const cats = (f.categories ?? []).slice(0, 6)
  const bt = f.backtest
  return (
    <Card style={{ marginTop: 24 }}>
      {title(`Forecast · ${monthLabel(f.month)}`, 'likely range = middle 80% of outcomes')}
      <div style={{ display: 'flex', gap: 40, flexWrap: 'wrap', alignItems: 'flex-start' }}>
        <div style={{ minWidth: 200 }}>
          <div style={{ fontFamily: 'var(--font-display, inherit)', fontSize: 26, fontWeight: 700 }}>{fmtFull(t.p50)}</div>
          <div style={{ fontSize: 11.5, color: T.muted, marginTop: 2 }}>likely {fmt(t.p10)} – {fmt(t.p90)}</div>
          {cap > 0 && chip(t.p50 <= cap ? `${fmtFull(cap - t.p50)} under the ${fmt(cap)} cap` : `${fmtFull(t.p50 - cap)} over the ${fmt(cap)} cap`, t.p50 <= cap ? 'good' : 'bad')}
        </div>
        <div style={{ flex: 1, minWidth: 300, display: 'grid', gap: 8, fontSize: 12.5 }}>
          {cats.map(c => (
            <div key={c.id} style={{ display: 'grid', gridTemplateColumns: '1fr 80px 120px', gap: 12, alignItems: 'baseline' }}>
              <span>{c.icon} {c.name}{c.fixed && <span style={{ color: T.muted, fontSize: 10.5 }}> · fixed</span>}</span>
              <span style={{ textAlign: 'right', fontWeight: 600 }}>{fmt(c.p50)}</span>
              <span style={{ textAlign: 'right', color: T.muted, fontSize: 11 }}>{c.reliable || c.fixed ? `${fmt(c.p10)} – ${fmt(c.p90)}` : 'low confidence'}</span>
            </div>
          ))}
        </div>
      </div>
      {bt && bt.mape_model != null && bt.mape_base != null && (
        <div style={{ fontSize: 11, color: T.muted, marginTop: 14 }}>
          Backtest on the last {bt.months} months: this model is off by {(bt.mape_model * 100).toFixed(0)}% on average vs {(bt.mape_base * 100).toFixed(0)}% for “same as last month”
          {f.model_beats_baseline ? '.' : ' — treat as a rough guide.'}
        </div>
      )}
    </Card>
  )
}

function ExpenseDashboard() {
  const [month, setMonth] = useState(currentMonth)
  const [d, setD] = useState<DashboardData | null>(null)
  const [error, setError] = useState('')
  const [open, setOpen] = useState<number | null>(null)
  const [fc, setFc] = useState<Forecast | null>(null)
  const [next, setNext] = useState<Forecast | null>(null)

  useEffect(() => {
    getDashboard(month).then(x => { setD(x); setError('') }).catch(e => setError(e.message))
    setFc(null); setNext(null)
    getForecast(month).then(setFc).catch(() => setFc(null))
    if (month === currentMonth()) getForecast(shiftMonth(month, 1)).then(setNext).catch(() => setNext(null))
  }, [month])

  const header = (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
      <h2 style={{ fontSize: 20, fontWeight: 700 }}>Spending</h2>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <MonthPicker month={month} onChange={setMonth} />
      </div>
    </div>
  )
  if (!d) return <>{header}<div style={{ color: error ? T.negative : T.muted }}>{error || 'Loading…'}</div></>

  const spent = d.total_spent
  const cap = d.budget_cap
  const days = d.daily.length
  const now = currentMonth()
  const isCurrent = month === now
  const isFuture = month > now
  const elapsed = isCurrent ? Math.min(days, new Date().getDate()) : isFuture ? 0 : days
  const remainingDays = days - elapsed
  const pace = cap * (elapsed / days)
  const paceDiff = spent - pace
  const left = cap - spent
  const modelProj = isCurrent && fc?.available && fc.total ? fc.total : null
  const projected = modelProj ? modelProj.p50 : isCurrent && elapsed > 0 ? Math.round((spent / elapsed) * days) : spent
  const saved = d.income - spent
  const savedPct = d.income ? (saved / d.income) * 100 : 0
  const planPct = d.income ? (d.savings_amount / d.income) * 100 : 0

  // category rows: over-target first (largest overshoot), then by spend
  const rows = d.categories
    .filter(c => c.spent !== 0)
    .map(c => {
      const target = (c.target_pct / 100) * d.income
      return { ...c, target, delta: c.target_pct > 0 ? c.spent - target : 0 }
    })
    .sort((a, b) => (b.delta > 0 ? 1 : 0) - (a.delta > 0 ? 1 : 0) || (b.delta > 0 && a.delta > 0 ? b.delta - a.delta : b.spent - a.spent))
  const rowMax = Math.max(1, ...rows.map(r => Math.max(r.spent, r.target)))
  const catColor = (r: { color: string }) => r.color || T.accent   // the colour chosen in Admin → Categories

  // spend pace chart
  const curCum = cumulative(d.daily, isCurrent ? elapsed : days)
  const prevCum = cumulative(d.prev_daily)
  const yMax = Math.max(1, cap, ...curCum, ...prevCum, ...(isCurrent && fc?.available && fc.total ? [fc.total.p90] : []))
  const W = 600, H = 150
  const x = (i: number, n: number) => (n <= 1 ? 0 : (i / (n - 1)) * W)
  const y = (v: number) => H - 8 - (v / yMax) * (H - 20)
  const poly = (a: number[], n: number) => a.map((v, i) => `${x(i, n).toFixed(1)},${y(v).toFixed(1)}`).join(' ')

  // worth a look
  const looks: React.ReactNode[] = []
  const overs = rows.filter(r => r.delta > 0).slice(0, 2)
  overs.forEach(r => looks.push(<span key={`o${r.id}`}><b>{r.icon} {r.name}</b> is {Math.round((r.delta / r.target) * 100)}% over target ({signedFull(r.delta)})</span>))
  if (isCurrent && elapsed > 0 && cap > 0 && projected > cap) looks.push(<span key="proj">At this pace you will end <b>{fmtFull(projected - cap)}</b> over the budget cap</span>)
  const jump = rows.filter(r => r.prev_spent > 0 && r.spent > r.prev_spent * 1.5 && r.spent - r.prev_spent > 0.02 * d.income && !overs.some(o => o.id === r.id))[0]
  if (jump) looks.push(<span key="jump"><b>{jump.icon} {jump.name}</b> is up {signedFull(jump.spent - jump.prev_spent)} on last month</span>)
  if (d.unassigned_count > 0) looks.push(<span key="un"><b>{d.unassigned_count}</b> entries have no sub-category (Admin → Sub-categories → Needs review)</span>)

  const maxT = Math.max(1, ...d.trend.map(t => Math.max(t.total, t.budget_cap)))

  return (
    <>
      {header}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 16, marginBottom: 24 }}>
        <Kpi accent={spent > cap ? T.negative : T.accent} name="Spent" sub={<>of {fmtFull(cap)} budget{d.total_cashback > 0 && <> · {fmtFull(d.total_cashback)} cashback</>}</>}
          extra={<>
            <div style={{ position: 'relative', height: 6, background: T.surface2, borderRadius: 3, marginTop: 10 }}>
              <div style={{ height: '100%', width: `${Math.min(100, cap ? (spent / cap) * 100 : 0)}%`, background: spent > cap ? T.negative : T.accent, borderRadius: 3 }} />
              {isCurrent && <div title="Where you should be today" style={{ position: 'absolute', top: -3, left: `${(elapsed / days) * 100}%`, width: 2, height: 12, background: T.text, opacity: 0.7 }} />}
            </div>
            {isCurrent
              ? chip(Math.abs(paceDiff) <= cap * 0.03 ? 'On pace' : paceDiff > 0 ? `Ahead of pace ${signedFull(paceDiff)}` : `Under pace ${signedFull(paceDiff)}`, Math.abs(paceDiff) <= cap * 0.03 ? 'neutral' : paceDiff > 0 ? 'bad' : 'good')
              : isFuture ? null : chip(left >= 0 ? `${fmtFull(left)} under budget` : `${fmtFull(-left)} over budget`, left >= 0 ? 'good' : 'bad')}
          </>}>
          {fmtFull(spent)}
        </Kpi>

        <Kpi accent={left >= 0 ? T.accent2 : T.negative} name={isCurrent || isFuture ? 'Left to spend' : left >= 0 ? 'Left unspent' : 'Overspent'}
          sub={isCurrent && remainingDays > 0 && left > 0 ? `${fmtFull(left / remainingDays)} / day for ${remainingDays} days` : isCurrent && left <= 0 ? 'Budget used up' : `${d.income ? ((Math.abs(left) / d.income) * 100).toFixed(1) : 0}% of salary`}>
          <span style={{ color: left >= 0 ? T.text : T.negative }}>{left < 0 ? '−' : ''}{fmtFull(Math.abs(left))}</span>
        </Kpi>

        {isCurrent && elapsed > 0 ? (
          <Kpi accent={projected > cap ? T.negative : T.warn} name="Projected month-end" sub={<>{cap ? `${projected <= cap ? fmtFull(cap - projected) + ' under' : fmtFull(projected - cap) + ' over'} the budget cap` : ''}{modelProj && <><br />likely {fmt(modelProj.p10)} – {fmt(modelProj.p90)}</>}</>}>
            <span style={{ color: projected > cap ? T.negative : T.text }}>{fmtFull(projected)}</span>
          </Kpi>
        ) : (
          <Kpi accent="#38bdf8" name="vs other months" sub={undefined}
            extra={<div style={{ display: 'grid', gap: 6, marginTop: 6, fontSize: 12 }}>
              {[
                { m: d.prev_month, t: d.prev_total },
                { m: d.prev2_month, t: d.prev2_total },
                ...(d.next_total > 0 && d.next_month <= now ? [{ m: d.next_month, t: d.next_total }] : []),
              ].map(o => o.t > 0 && (
                <div key={o.m} style={{ display: 'grid', gridTemplateColumns: '52px 1fr auto', gap: 8, alignItems: 'baseline' }}>
                  <span style={{ color: T.muted }}>{monthLabel(o.m).split(' ')[0].slice(0, 3)} {o.m.slice(2, 4)}</span>
                  <span>{fmtFull(o.t)}</span>
                  <span style={{ color: spent > o.t ? T.negative : T.positive, fontWeight: 600 }}>{signedFull(spent - o.t)} <span style={{ fontWeight: 400 }}>({spent > o.t ? '+' : ''}{(((spent - o.t) / o.t) * 100).toFixed(0)}%)</span></span>
                </div>
              ))}
            </div>}>
            <span style={{ fontSize: 14, color: T.muted, fontWeight: 400 }}>this month's spend vs…</span>
          </Kpi>
        )}

        <Kpi accent={savedPct >= planPct ? T.positive : T.negative} name="Savings rate" sub={`${fmtFull(saved)} saved · plan ${planPct.toFixed(0)}% (${fmtFull(d.savings_amount)})`}
          extra={isCurrent ? <div style={{ fontSize: 11, color: T.muted, marginTop: 2 }}>if you spend nothing more</div> : undefined}>
          <span style={{ color: savedPct >= planPct ? T.positive : T.negative }}>{savedPct.toFixed(0)}%</span>
        </Kpi>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(420px, 1fr))', gap: 24, alignItems: 'start' }}>
        <Card>
          {title('Where it went', 'tick = target · click for sub-categories')}
          <div style={{ display: 'grid', gap: 4 }}>
            {rows.map(r => {
              const isOpen = open === r.id
              const subs = d.subcategories.filter(s => s.category_id === r.id && s.spent !== 0).sort((a, b) => b.spent - a.spent)
              return (
                <div key={r.id}>
                  <div onClick={() => setOpen(isOpen ? null : r.id)} style={{ display: 'grid', gridTemplateColumns: '130px 1fr 150px', alignItems: 'center', gap: 12, fontSize: 12.5, padding: '7px 4px', cursor: 'pointer', borderRadius: 6 }}>
                    <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      <span style={{ color: T.muted, display: 'inline-block', width: 12, fontSize: 9 }}>{isOpen ? '▼' : '▶'}</span>{r.icon} {r.name}
                    </span>
                    <span style={{ position: 'relative', height: 9, background: T.surface2, borderRadius: 5 }}>
                      <span style={{ display: 'block', height: '100%', width: `${(Math.abs(r.spent) / rowMax) * 100}%`, background: `linear-gradient(90deg, ${catColor(r)}99, ${catColor(r)})`, borderRadius: 5, boxShadow: r.delta > 0 ? `0 0 0 1.5px ${T.negative}` : 'none' }} />
                      {r.target > 0 && <span style={{ position: 'absolute', top: -3, left: `${(r.target / rowMax) * 100}%`, width: 2, height: 15, background: T.text, opacity: 0.7 }} />}
                    </span>
                    <span style={{ textAlign: 'right' }}>
                      {fmtFull(r.spent)} <span style={{ color: T.muted }}>· {spent ? Math.round((r.spent / spent) * 100) : 0}%</span>
                      <div style={{ fontSize: 10.5, color: r.delta > 0 ? T.negative : T.muted }}>
                        {r.target_pct > 0
                          ? `${r.delta > 0 ? signedFull(r.delta) + ' over' : fmtFull(-r.delta) + ' under'} target (${r.target_pct.toFixed(2)}%)`
                          : r.prev_spent > 0 ? `${signedFull(r.spent - r.prev_spent)} vs last month` : 'no target'}
                      </div>
                    </span>
                  </div>
                  {isOpen && (
                    <div style={{ display: 'grid', gap: 8, padding: '4px 4px 10px 26px' }}>
                      {subs.length === 0 && <span style={{ color: T.muted, fontSize: 12 }}>No sub-category data</span>}
                      {subs.map(s => (
                        <div key={s.subcategory_id ?? 'none'} style={{ display: 'grid', gridTemplateColumns: '1fr 110px', fontSize: 12, gap: 12 }}>
                          <span style={{ color: s.subcategory_id == null ? T.muted : T.text }}>{s.name}</span>
                          <span style={{ textAlign: 'right', color: T.muted }}>{fmtFull(s.spent)} · {r.spent ? Math.round((s.spent / r.spent) * 100) : 0}%</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
            {rows.length === 0 && <span style={{ color: T.muted, fontSize: 12 }}>No spending this month</span>}
          </div>
        </Card>

        <div style={{ display: 'grid', gap: 24 }}>
          <Card>
            {title('Pace', isCurrent ? `day ${elapsed} of ${days}` : monthLabel(month))}
            <svg viewBox={`0 0 ${W} ${H}`} width="100%" preserveAspectRatio="none" style={{ display: 'block', height: 140 }}>
              <line x1={0} y1={y(0)} x2={W} y2={y(cap)} stroke={T.muted} strokeWidth="1.5" strokeDasharray="5 4" vectorEffect="non-scaling-stroke" />
              {prevCum.length > 1 && <polyline points={poly(prevCum, prevCum.length)} fill="none" stroke={T.muted} strokeOpacity="0.45" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />}
              <defs><linearGradient id="paceFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={spent > cap ? T.negative : T.accent} stopOpacity="0.35" /><stop offset="100%" stopColor={spent > cap ? T.negative : T.accent} stopOpacity="0" /></linearGradient></defs>
              {curCum.length > 1 && <polygon points={`${x(0, days)},${y(0)} ${poly(curCum, days)} ${x(curCum.length - 1, days)},${y(0)}`} fill="url(#paceFill)" />}
              {curCum.length > 1 && <polyline points={poly(curCum, days)} fill="none" stroke={spent > cap ? T.negative : T.accent} strokeWidth="2.5" vectorEffect="non-scaling-stroke" />}
              {modelProj && elapsed > 0 && elapsed < days && (
                <>
                  <polygon points={`${x(elapsed - 1, days)},${y(spent)} ${W},${y(modelProj.p90)} ${W},${y(modelProj.p10)}`} fill={T.accent} fillOpacity="0.12" />
                  <line x1={x(elapsed - 1, days)} y1={y(spent)} x2={W} y2={y(modelProj.p50)} stroke={T.accent} strokeWidth="2" strokeDasharray="2 4" vectorEffect="non-scaling-stroke" />
                </>
              )}
              {isCurrent && elapsed > 0 && <line x1={x(elapsed - 1, days)} y1={0} x2={x(elapsed - 1, days)} y2={H - 8} stroke={T.text} strokeOpacity="0.25" vectorEffect="non-scaling-stroke" />}
            </svg>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 8, fontSize: 10.5, color: T.muted }}>
              <span>1</span><span>{Math.round(days / 2)}</span><span>{days}</span>
            </div>
            <div style={{ display: 'flex', gap: 16, marginTop: 10, fontSize: 11, color: T.muted, flexWrap: 'wrap' }}>
              <span><span style={{ color: T.accent }}>━</span> this month</span>
              <span>┅ budget cap {fmtFull(cap)}</span>
              {modelProj && <span><span style={{ color: T.accent }}>┅</span> forecast</span>}
              {d.prev_total > 0 && <span><span style={{ opacity: 0.5 }}>━</span> {monthLabel(d.prev_month)}</span>}
            </div>
          </Card>

          <Card>
            {title('12 months', 'green = within budget · red = over · tick = budget cap')}
            <div style={{ display: 'flex', alignItems: 'flex-end', gap: 6, height: 120 }}>
              {d.trend.map(t => (
                <div key={t.month} onClick={() => setMonth(t.month)} title={`${monthLabel(t.month)}: ${fmtFull(t.total)} of ${fmtFull(t.budget_cap)}`}
                  style={{ flex: 1, position: 'relative', height: '100%', display: 'flex', alignItems: 'flex-end', cursor: 'pointer' }}>
                  <div style={{ width: '100%', minHeight: t.total ? 2 : 0, height: `${(t.total / maxT) * 100}%`, borderRadius: '4px 4px 0 0',
                    background: t.total > t.budget_cap ? T.negative : T.accent2, opacity: t.month === month ? 1 : 0.5,
                    boxShadow: t.month === month ? `0 0 14px ${t.total > t.budget_cap ? T.negative : T.accent2}66` : 'none' }} />
                  <div style={{ position: 'absolute', left: 0, right: 0, bottom: `${(t.budget_cap / maxT) * 100}%`, height: 2, background: t.total > t.budget_cap ? T.negative : T.muted, opacity: 0.8 }} />
                </div>
              ))}
            </div>
            <div style={{ display: 'flex', gap: 6, marginTop: 8, fontSize: 10, color: T.muted }}>
              {d.trend.map(t => <span key={t.month} style={{ flex: 1, textAlign: 'center' }}>{MONTHS[Number(t.month.slice(5)) - 1].slice(0, 3)}</span>)}
            </div>
          </Card>
        </div>
      </div>

      {next?.available && next.total && <NextMonth f={next} />}

      {(looks.length > 0 || d.top_expenses.length > 0) && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(420px, 1fr))', gap: 24, marginTop: 24, alignItems: 'start' }}>
          <Card>
            {title('Worth a look')}
            <div style={{ display: 'grid', gap: 10, fontSize: 13 }}>
              {looks.map((l, i) => <div key={i}>• {l}</div>)}
              {looks.length === 0 && <span style={{ color: T.muted, fontSize: 12 }}>Nothing unusual this month.</span>}
            </div>
          </Card>
          <Card>
            {title('Largest expenses')}
            <div style={{ display: 'grid', gap: 10, fontSize: 13 }}>
              {d.top_expenses.map((e, i) => (
                <div key={i} style={{ display: 'grid', gridTemplateColumns: '48px 1fr 90px', gap: 10, alignItems: 'baseline' }}>
                  <span style={{ color: T.muted, fontSize: 12 }}>{Number(e.date.slice(8))} {MONTHS[Number(e.date.slice(5, 7)) - 1].slice(0, 3)}</span>
                  <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {e.icon} {e.subcategory ?? e.category}{e.note && <span style={{ color: T.muted }}> · {e.note}</span>}
                  </span>
                  <span style={{ textAlign: 'right', fontWeight: 600 }}>{fmtFull(e.amount)}</span>
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}
    </>
  )
}
