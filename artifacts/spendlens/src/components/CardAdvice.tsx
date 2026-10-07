import { useEffect, useState } from 'react'
import { getCardAdvice, type CardAdvice } from '../api'
import { T, fmt } from '../theme'
import { Card, label } from './ui'
import { CardChip, dotStyle } from '../cardColors'

const th = { color: T.muted, fontSize: 10.5, textTransform: 'uppercase', letterSpacing: 0.6, fontWeight: 600 } as const
const pct = (n: number) => `${Number.isInteger(n) ? n : n.toFixed(2).replace(/0$/, '')}%`

/** Which card for which kind of spend. Rates are the issuers' published terms (marked where assumed or measured);
 *  "left behind" prices the last 12 months of real spend against the best card for it. */
export default function CardAdviceCard() {
  const [d, setD] = useState<CardAdvice | null>(null)
  const [open, setOpen] = useState(false)
  useEffect(() => { getCardAdvice().then(setD).catch(() => setD(null)) }, [])
  if (!d) return null
  const rows = d.purposes.filter(p => p.best || p.spend_12m > 0)
  const mark = (conf: string) => (conf === 'published' ? '' : conf === 'observed' ? ' · measured' : ' · assumed')

  return (
    <Card style={{ padding: 20, marginBottom: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 6, gap: 12, flexWrap: 'wrap' }}>
        <span style={{ ...label, fontSize: 12.5, letterSpacing: 0.8 }}>Which card for what</span>
        <span style={{ ...label, fontSize: 10.5, textTransform: 'none' }}>highest reward rate; closed cards left out</span>
      </div>
      <div style={{ fontSize: 13.5, marginBottom: 14 }}>
        {d.totals.missed_12m >= 100
          ? <>Using the best card for each purpose would have earned about <b style={{ color: T.positive }}>{fmt(d.totals.missed_12m)}</b> more in the last 12 months
            ({fmt(d.totals.earned_12m)} earned of {fmt(d.totals.best_12m)} possible).</>
          : <>You are earning nearly all that your cards allow: {fmt(d.totals.earned_12m)} of {fmt(d.totals.best_12m)} possible in 12 months.</>}
      </div>

      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ textAlign: 'left' }}>
              <th style={th}>Spend on</th><th style={th}>Use</th><th style={{ ...th, textAlign: 'right' }}>Rate</th>
              <th style={th}>Otherwise</th><th style={{ ...th, textAlign: 'right' }}>12 months</th><th style={{ ...th, textAlign: 'right' }}>Left behind</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(p => (
              <tr key={p.id} style={{ borderTop: `1px solid ${T.border}` }}>
                <td style={{ padding: '8px 8px 8px 0' }} title={p.examples}>{p.label}</td>
                <td style={{ padding: '8px 8px 8px 0', fontWeight: 600 }}>
                  {p.best ? <><CardChip color={p.best.color} name={p.best.name} size={17} />{p.best.name.replace(/ ···\d+$/, '')}
                    {p.best.also.length > 0 && <span style={{ color: T.muted, fontWeight: 400 }}> or {p.best.also.map(n => n.replace(/ ···\d+$/, '')).join(', ')}</span>}
                    {p.best.note && <div style={{ color: T.muted, fontWeight: 400, fontSize: 11 }}>{p.best.note}{mark(p.best.conf)}</div>}</>
                    : <span style={{ color: T.muted, fontWeight: 400 }}>no card earns here</span>}
                </td>
                <td style={{ padding: 8, textAlign: 'right' }}>{p.best ? pct(p.best.rate) : '—'}</td>
                <td style={{ padding: 8, color: T.muted }}>{p.next ? <><span style={dotStyle(p.next.color, 8)} />{p.next.name.replace(/ ···\d+$/, '')} {pct(p.next.rate)}</> : '—'}</td>
                <td style={{ padding: 8, textAlign: 'right' }}>{p.spend_12m > 0 ? fmt(p.spend_12m) : '—'}</td>
                <td style={{ padding: '8px 0 8px 8px', textAlign: 'right', color: p.missed_12m >= 100 ? T.warn : T.muted }}>{p.missed_12m >= 1 ? fmt(p.missed_12m) : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {d.exceptions.length > 0 && (
        <div style={{ fontSize: 12, color: T.muted, marginTop: 12 }}>
          Exceptions: {d.exceptions.map(e => `${e.merchant} on ${e.card.replace(/ Credit Card$/, '')} (${pct(e.rate)})`).join(' · ')}
        </div>
      )}

      <button onClick={() => setOpen(!open)} style={{ background: 'none', border: 'none', color: T.accent, cursor: 'pointer', fontSize: 12, padding: '10px 0 0' }}>
        {open ? 'Hide' : 'Show'} what each card is for, and the assumptions
      </button>
      {open && (
        <div style={{ marginTop: 10, fontSize: 12.5 }}>
          {d.cards.map(c => (
            <div key={c.id} style={{ padding: '7px 0', borderTop: `1px solid ${T.border}` }}>
              <b><CardChip color={c.color} name={c.name} size={17} />{c.name.replace(/ ···\d+$/, '')}</b>
              <span style={{ color: T.muted }}> · {c.best_for.length ? `best for ${c.best_for.join(', ')}` : 'not the best at anything: keep it for its benefits'}</span>
              {c.note && <div style={{ color: T.muted, fontSize: 11.5 }}>{c.note}</div>}
            </div>
          ))}
          <div style={{ color: T.muted, fontSize: 11.5, marginTop: 8 }}>
            Rates are percent of spend in rupees, from each issuer's published terms (marked "assumed" where I had to choose). Values used: {d.assumptions.join('; ')}.
            Monthly caps, milestone bonuses, lounge access and annual fees are not in the rates. Purposes are matched from the merchant name, so an odd one can land in "everything else".
          </div>
        </div>
      )}
    </Card>
  )
}
