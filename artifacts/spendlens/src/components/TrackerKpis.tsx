import { useState } from 'react'
import type { CalendarTracker } from '../api'
import { T, fmtFull } from '../theme'
import { card } from './ui'

const STATUS = {
  good: { text: 'On track', colour: T.positive },
  warn: { text: 'Slightly behind', colour: T.warn },
  bad: { text: 'Behind', colour: T.negative },
} as const

const facts = { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px 12px', fontSize: 12, color: T.muted } as const
const num = { color: T.text, fontWeight: 600, fontVariantNumeric: 'tabular-nums' } as const

const COMPACT_KEY = 'spendlens.trackerKpisCompact'

/** One card per tracker above the calendar, plus a 'what a day costs' card for every tracker linked to spending.
 *  "Show less" folds them into one line per tracker, as the Sheet does with its KPIs; the choice is remembered. */
export default function TrackerKpis({ trackers }: { trackers: CalendarTracker[] }) {
  const [compact, setCompact] = useState(() => { try { return localStorage.getItem(COMPACT_KEY) === '1' } catch { return false } })
  const flip = () => setCompact(c => { try { localStorage.setItem(COMPACT_KEY, c ? '0' : '1') } catch { /* storage unavailable */ } return !c })
  if (!trackers.length) return null
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 6 }}>
        <span style={{ fontSize: 11, letterSpacing: 0.6, textTransform: 'uppercase', color: T.muted, fontWeight: 600 }}>Trackers this month</span>
        <button type="button" onClick={flip} style={{ border: 'none', background: 'none', cursor: 'pointer', color: T.accent, fontSize: 12.5, fontWeight: 600, padding: '2px 4px' }}>
          {compact ? 'Show all' : 'Show less'}
        </button>
      </div>
      {compact ? (
        <section aria-label="Tracker KPIs" style={{ ...card, padding: '10px 14px', display: 'flex', alignItems: 'center', gap: '8px 22px', flexWrap: 'wrap', fontSize: 13 }}>
          {trackers.map(t => <TrackerLine key={t.id} t={t} />)}
        </section>
      ) : (
        <div aria-label="Tracker KPIs" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: 12 }}>
          {trackers.map(t => <TrackerCard key={t.id} t={t} />)}
          {trackers.filter(t => t.kpi.cost).map(t => <CostCard key={`cost-${t.id}`} t={t} />)}
        </div>
      )}
    </div>
  )
}

/** A tracker in one line: done of goal, this week, its status and (when linked to spending) what a day costs. */
function TrackerLine({ t }: { t: CalendarTracker }) {
  const k = t.kpi, s = STATUS[k.status], c = k.cost
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
      <i style={{ width: 10, height: 10, borderRadius: 3, background: t.color }} />
      <b style={{ fontWeight: 600 }}>{t.name}</b>
      <span style={{ color: T.muted }}><b style={num}>{k.count}</b> of {k.month_goal} · week <b style={num}>{k.this_week.done}/{k.this_week.goal}</b></span>
      <span style={{ fontSize: 11, fontWeight: 600, padding: '2px 8px', borderRadius: 999, color: s.colour, background: `${s.colour}22` }}>{s.text}</span>
      {c && <span style={{ color: T.muted }}>a day costs <b style={{ ...num, color: c.diff > 0 ? T.warn : T.positive }}>{c.diff >= 0 ? '+' : '−'}{fmtFull(Math.abs(c.diff))}</b></span>}
    </span>
  )
}

function TrackerCard({ t }: { t: CalendarTracker }) {
  const k = t.kpi, s = STATUS[k.status]
  const goal = Math.max(1, k.month_goal)
  const maxWeek = Math.max(1, ...k.per_week.map(w => Math.max(w.done, w.goal)))
  return (
    <section style={{ ...card, padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 8, minWidth: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ width: 14, height: 14, borderRadius: 4, background: t.color, flexShrink: 0 }} />
        <b style={{ fontSize: 15, flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{t.name}</b>
        <span style={{ fontSize: 11, fontWeight: 600, padding: '2px 8px', borderRadius: 999, color: s.colour, background: `${s.colour}22` }}>{s.text}</span>
      </div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap' }}>
        <strong style={{ fontSize: 30, lineHeight: 1, fontVariantNumeric: 'tabular-nums', fontFamily: 'var(--font-display, inherit)' }}>{k.count}</strong>
        <span style={{ color: T.muted, fontSize: 12.5 }}>of {k.month_goal} days this month · on pace for {k.projected}</span>
      </div>
      <div title="Done so far against the month's goal. The mark is where you would be by today on target."
        style={{ position: 'relative', height: 6, borderRadius: 3, background: T.surface2 }}>
        <i style={{ position: 'absolute', inset: '0 auto 0 0', width: `${Math.min(100, (k.count / goal) * 100)}%`, background: t.color, borderRadius: 3 }} />
        <u style={{ position: 'absolute', top: -2, bottom: -2, width: 2, left: `${Math.min(100, (k.expected_by_today / goal) * 100)}%`, background: T.text, opacity: 0.55 }} />
      </div>
      <div style={facts}>
        <span>This week <b style={num}>{k.this_week.done} / {k.this_week.goal}</b></span>
        <span>Weeks on target <b style={num}>{k.weeks_on_target} / {k.complete_weeks}</b></span>
        <span>Week streak <b style={num}>{k.week_streak}</b></span>
        <span>Target <b style={num}>{t.target_per_week}× a week</b></span>
      </div>
      <div aria-label="Ticks per week" style={{ display: 'flex', gap: 4, alignItems: 'flex-end', height: 30 }}>
        {k.per_week.map((w, i) => (
          <div key={w.start_day} title={`Week ${i + 1} (${w.start_day} to ${w.end_day}): ${w.done} of ${w.goal}`}
            style={{ flex: 1, height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'flex-end', alignItems: 'center', gap: 2 }}>
            <i style={{ display: 'block', width: '100%', minHeight: 2, height: `${(w.done / maxWeek) * 100}%`, borderRadius: '3px 3px 0 0', background: t.color, opacity: w.done >= w.goal ? 0.9 : 0.35 }} />
            <small style={{ fontSize: 9.5, color: T.muted }}>W{i + 1}</small>
          </div>
        ))}
      </div>
      {k.cost_per_visit && (
        <div style={facts}>
          <span style={{ gridColumn: '1 / -1' }}>Cost per visit <b style={num}>{fmtFull(k.cost_per_visit.per_visit)}</b> · {k.cost_per_visit.bill_name} {fmtFull(k.cost_per_visit.amount)}/month</span>
        </div>
      )}
    </section>
  )
}

function CostCard({ t }: { t: CalendarTracker }) {
  const c = t.kpi.cost!
  return (
    <section style={{ ...card, padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 8, minWidth: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ width: 14, height: 14, borderRadius: 4, background: T.warn, flexShrink: 0 }} />
        <b style={{ fontSize: 15, flex: 1 }}>What a {t.name} day costs</b>
      </div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap' }}>
        <strong style={{ fontSize: 30, lineHeight: 1, color: c.diff > 0 ? T.warn : T.positive, fontVariantNumeric: 'tabular-nums', fontFamily: 'var(--font-display, inherit)' }}>
          {c.diff >= 0 ? '+' : '−'}{fmtFull(Math.abs(c.diff))}
        </strong>
        <span style={{ color: T.muted, fontSize: 12.5 }}>a day, against the other days it counts on</span>
      </div>
      <p style={{ margin: 0, fontSize: 12.5, color: T.muted, lineHeight: 1.5 }}>
        The linked spending averaged <b style={num}>{fmtFull(c.avg_on)}</b> on {c.n_on} ticked day{c.n_on === 1 ? '' : 's'},
        against <b style={num}>{fmtFull(c.avg_off)}</b> on {c.n_off} other day{c.n_off === 1 ? '' : 's'}.
      </p>
    </section>
  )
}
