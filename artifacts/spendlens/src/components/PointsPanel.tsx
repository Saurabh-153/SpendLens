import { T, fmt, fmtFull } from '../theme'
import { Card, label } from './ui'

const th = { color: T.muted, fontSize: 10.5, textTransform: 'uppercase', letterSpacing: 0.6 } as const
const monthLabel = (iso: string) => new Date(iso).toLocaleDateString('en-IN', { month: 'short', year: '2-digit' })

interface Props {
  p: {
    earned: number; value: number; per_100: number; balance: number | null; redeem_at: number; unit: string; on_lines: number
    months: { period_to: string; earned: number; value: number }[]
  }
  value: number   // rupees per point
}

/** Reward points as the statements print them: nothing here is estimated except what a point is worth. */
export default function PointsPanel({ p, value }: Props) {
  const short = p.balance != null ? Math.max(p.redeem_at - p.balance, 0) : null
  const max = Math.max(...p.months.map(m => m.earned), 1)
  return (
    <Card style={{ padding: 20, marginBottom: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 12 }}>
        <span style={{ ...label, fontSize: 12.5, letterSpacing: 0.8 }}>Reward {p.unit}</span>
        <span style={{ ...label, fontSize: 10.5, textTransform: 'none' }}>read from the statements</span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 22 }}>
        <div>
          {p.balance != null && (
            <div style={{ marginBottom: 14 }}>
              <div style={{ ...label, marginBottom: 4 }}>Balance now</div>
              <div style={{ fontFamily: 'var(--font-display, inherit)', fontSize: 24, fontWeight: 700 }}>{p.balance.toLocaleString('en-IN')} <span style={{ fontSize: 13, color: T.muted, fontWeight: 500 }}>{p.unit} · {fmtFull(Math.round(p.balance * value))}</span></div>
              {p.redeem_at > 0 && (
                <div style={{ fontSize: 12, color: short ? T.warn : T.positive, marginTop: 2 }}>
                  {short ? `${short.toLocaleString('en-IN')} more to reach the ${p.redeem_at.toLocaleString('en-IN')} needed to redeem` : 'Enough to redeem'}
                </div>
              )}
            </div>
          )}
          <div style={{ fontSize: 12.5 }}>
            <b>{p.earned.toLocaleString('en-IN')}</b> {p.unit} earned in total, worth <b>{fmtFull(Math.round(p.value))}</b> at ₹{value} each,
            which is {p.per_100.toFixed(1)} for every ₹100 spent.
          </div>
          {p.earned > p.on_lines && (
            <div style={{ fontSize: 11.5, color: T.muted, marginTop: 6 }}>
              {(p.earned - p.on_lines).toLocaleString('en-IN')} of those are bonus or adjustment points that the statements
              give in total but do not attach to a purchase.
            </div>
          )}
        </div>
        <div>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
            <thead>
              <tr style={th}>
                <th style={{ textAlign: 'left', padding: '4px 0' }}>Statement</th>
                <th style={{ textAlign: 'right' }}>{p.unit}</th><th style={{ textAlign: 'right' }}>Worth</th>
              </tr>
            </thead>
            <tbody>
              {[...p.months].reverse().map(m => (
                <tr key={m.period_to} style={{ borderTop: `1px solid ${T.hairline}` }}>
                  <td style={{ padding: '6px 0' }}>
                    {monthLabel(m.period_to)}
                    <span style={{ display: 'inline-block', height: 5, width: `${(m.earned / max) * 60}px`, background: T.accent, borderRadius: 3, marginLeft: 8, verticalAlign: 'middle' }} />
                  </td>
                  <td style={{ textAlign: 'right' }}>{m.earned.toLocaleString('en-IN')}</td>
                  <td style={{ textAlign: 'right', color: T.positive }}>{fmt(m.value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div style={{ fontSize: 11.5, color: T.muted, marginTop: 14, paddingTop: 12, borderTop: `1px solid ${T.hairline}` }}>
        The {p.unit} are the bank's own figures. Their rupee value (₹{value} each) is the assumption: it is not on the statements.
      </div>
    </Card>
  )
}
