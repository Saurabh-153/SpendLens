import type { RubyxBenefits } from '../api'
import { T, fmt, fmtFull } from '../theme'
import { Card, label } from './ui'

const th = { color: T.muted, fontSize: 10.5, textTransform: 'uppercase', letterSpacing: 0.6 } as const
const quarterLabel = (q: string) => `${q.slice(5)} ${q.slice(0, 4)}`   // "2025 Q3" -> "Q3 2025"

const title = (t: string, right?: string) => (
  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 12 }}>
    <span style={{ ...label, fontSize: 12.5, letterSpacing: 0.8 }}>{t}</span>
    {right && <span style={{ ...label, fontSize: 10.5, textTransform: 'none' }}>{right}</span>}
  </div>
)

/** What an ICICI premium card gives beyond points: the yearly milestone, lounge access, and what redeeming costs.
 *  Every figure here is estimated from the bank's published terms and the statements, not read from a statement. */
export default function RubyxPanel({ b }: { b: RubyxBenefits }) {
  const m = b.milestone
  const cur = m.current
  const into = cur.spend >= m.threshold ? cur.spend - (cur.next_at - 100000) : cur.spend
  const span = cur.spend >= m.threshold ? 100000 : m.threshold
  const pct = Math.min(Math.max(into / span, 0), 1) * 100
  const lounge = b.lounge

  return (
    <Card style={{ padding: 20, marginBottom: 16 }}>
      {title(`${b.name} benefits`, 'estimated from the bank\'s published terms')}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 22 }}>

        <div>
          <div style={{ ...label, marginBottom: 6 }}>Yearly milestone</div>
          <div style={{ fontSize: 12.5, marginBottom: 4 }}>
            {fmtFull(cur.spend)} this financial year
            <span style={{ color: T.muted }}> · next: {m.base.toLocaleString('en-IN')} points at {fmt(m.threshold)}, then +{m.step.toLocaleString('en-IN')} per extra ₹1L (up to {m.cap.toLocaleString('en-IN')})</span>
          </div>
          <div style={{ height: 8, background: T.surface2, borderRadius: 4, overflow: 'hidden', margin: '6px 0' }}>
            <div style={{ width: `${pct}%`, height: '100%', background: T.accent, borderRadius: 4 }} />
          </div>
          <div style={{ fontSize: 11.5, color: T.muted, marginBottom: 10 }}>
            {fmt(cur.to_go)} more reaches {cur.next_points.toLocaleString('en-IN')} points
            ({fmtFull(Math.round(cur.next_points * b.point_value))}).
          </div>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
            <thead>
              <tr style={th}>
                <th style={{ textAlign: 'left', padding: '4px 0' }}>Year</th><th style={{ textAlign: 'right' }}>Spend</th>
                <th style={{ textAlign: 'right' }}>Bonus</th>
              </tr>
            </thead>
            <tbody>
              {m.years.slice(0, 6).map(y => {
                const short = m.threshold - y.spend
                const close = y.points === 0 && short > 0 && short <= m.threshold * 0.1
                return (
                  <tr key={y.fy} style={{ borderTop: `1px solid ${T.hairline}` }}>
                    <td style={{ padding: '6px 0' }}>{y.fy}</td>
                    <td style={{ textAlign: 'right' }}>{fmt(y.spend)}</td>
                    <td style={{ textAlign: 'right', color: y.points ? T.positive : close ? T.warn : T.muted }}>
                      {y.points ? `${y.points.toLocaleString('en-IN')} pts · ${fmtFull(Math.round(y.value))}` : close ? `${fmtFull(Math.round(short))} short` : '—'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        <div>
          <div style={{ ...label, marginBottom: 6 }}>Lounge access</div>
          <div style={{ fontSize: 12.5, marginBottom: 8 }}>
            {lounge.visits} domestic visits a quarter when {lounge.lag ? "the previous quarter's" : 'the quarter\'s'} spend {lounge.lag ? 'is over' : 'reaches'} {fmt(lounge.threshold)}. Also: {lounge.extra}.
          </div>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
            <thead>
              <tr style={th}>
                <th style={{ textAlign: 'left', padding: '4px 0' }}>Quarter</th><th style={{ textAlign: 'right' }}>Spend</th>
                <th style={{ textAlign: 'right' }}>Entitled</th><th style={{ textAlign: 'right' }}>Swipes</th>
              </tr>
            </thead>
            <tbody>
              {lounge.quarters.map(q => (
                <tr key={q.quarter} style={{ borderTop: `1px solid ${T.hairline}` }}>
                  <td style={{ padding: '6px 0' }}>{quarterLabel(q.quarter)}</td>
                  <td style={{ textAlign: 'right', color: q.earns_next ? T.positive : T.text }} title={q.earns_next ? `Earns ${lounge.visits} visits next quarter` : 'Under the threshold'}>
                    {fmt(q.spend)}{q.earns_next ? ' ✓' : ''}
                  </td>
                  <td style={{ textAlign: 'right', color: q.entitled ? T.positive : T.muted }}>{q.entitled ? `${lounge.visits} visits` : '—'}</td>
                  <td style={{ textAlign: 'right', color: T.muted }}>{q.swipes || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div style={{ fontSize: 11.5, color: T.muted, marginTop: 8 }}>
            {lounge.lag ? "A tick means that quarter's spend earns visits in the next one. " : "A tick means the quarter reached the threshold. The bank's page does not say whether the same or the next quarter's visits are unlocked, so this assumes the same. "}Swipes are the ₹2 lounge-entry
            charges on the statement, which is what the card shows when it is presented, not a count of visits.
          </div>
        </div>

        <div>
          <div style={{ ...label, marginBottom: 6 }}>Redeeming points</div>
          <div style={{ fontSize: 12.5 }}>
            Each redemption costs {fmtFull(Math.round(b.redemptions.per_redemption))} (₹99 handling fee plus GST).
            {b.redemptions.count > 0
              ? <> You have paid <b>{fmtFull(Math.round(b.redemptions.cost))}</b> over {b.redemptions.count} redemption{b.redemptions.count === 1 ? '' : 's'}.</>
              : ' None on the statements yet.'}
          </div>
          <div style={{ fontSize: 11.5, color: T.muted, marginTop: 8 }}>
            At ₹{b.point_value} a point, a fee of ₹117 is the value of about {Math.round(b.redemptions.per_redemption / b.point_value)} points,
            so redeeming a small balance gives most of it away: let points build up and redeem once.
          </div>
        </div>
      </div>
      <div style={{ fontSize: 11.5, color: T.muted, marginTop: 14, paddingTop: 12, borderTop: `1px solid ${T.hairline}` }}>
        Years are financial years (April to March); the bank may count the milestone from your card anniversary
        instead, and decides what counts as eligible spend. Only fuel is published as earning nothing, so treat a
        near miss as too close to call. The value of a point (₹{b.point_value}) is not on the bank's page: change it
        under Edit by scaling the reward rates.
      </div>
    </Card>
  )
}
