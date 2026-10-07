import { useEffect, useRef, useState } from 'react'
import CardAdviceCard from './CardAdvice'
import { getCardsOverview, saveCardOrder, type CardsOverview, type OverviewCard } from '../api'
import { T, fmt, fmtFull } from '../theme'
import { Card, label } from './ui'
import { cardColor, CardChip } from '../cardColors'
import CreditCardFace from './CreditCardFace'

const GAP = 2

const monthYear = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString('en-IN', { month: 'short', year: 'numeric' }) : '—')
const dayLabel = (iso: string) => new Date(iso).toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short' })
const pct1 = (n: number) => `${n.toFixed(1)}%`
const th = { color: T.muted, fontSize: 10.5, textTransform: 'uppercase', letterSpacing: 0.6 } as const

const title = (t: string, right?: string) => (
  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 14 }}>
    <span style={{ ...label, fontSize: 12.5, letterSpacing: 0.8 }}>{t}</span>
    {right && <span style={{ ...label, fontSize: 10.5, textTransform: 'none' }}>{right}</span>}
  </div>
)

/** How long ago a card was last used, in words; a card untouched for a quarter is called retired. */
function idle(through: string | null, today: string) {
  if (!through) return { text: 'never used', retired: false }
  const days = Math.round((new Date(today).getTime() - new Date(through).getTime()) / 864e5)
  if (days <= 45) return { text: 'in use', retired: false }
  const months = Math.round(days / 30)
  return { text: `not used for ${months} month${months === 1 ? '' : 's'}`, retired: days > 90 }
}

export default function CardsOverviewPage({ onPick }: { onPick: (id: number) => void }) {
  const [d, setD] = useState<CardsOverview | null>(null)
  const [error, setError] = useState('')
  const load = () => getCardsOverview().then(setD).catch(e => setError(e.message))
  useEffect(() => { load() }, [])
  const dragId = useRef<number | null>(null)
  const [over, setOver] = useState<number | null>(null)

  /** Drop the dragged card where another one sits: it takes that place and the cards between shift along. */
  const drop = (targetId: number) => {
    const from = dragId.current
    dragId.current = null; setOver(null)
    if (!d || from === null || from === targetId) return
    // The dragged card takes the target's place: moving down it lands after it, moving up before it.
    const ids = d.cards.map(c => c.id)
    const was = ids.indexOf(from), at = ids.indexOf(targetId)
    ids.splice(was, 1)
    ids.splice(at, 0, from)
    const byId = new Map(d.cards.map(c => [c.id, c]))
    setD({ ...d, cards: ids.map(i => byId.get(i)!) })
    saveCardOrder(ids).catch(e => { setError(e.message); load() })
  }

  if (!d) return <div style={{ color: error ? T.negative : T.muted, padding: '8px 0' }}>{error || 'Loading…'}</div>
  const color = (id: number) => cardColor(d.cards.find(c => c.id === id)?.color)
  const totalCost = d.totals.fees
  const maxFy = Math.max(...d.years.map(y => y.total), 1)
  const nextPay = d.pay[0]

  return (
    <div>
      {/* The headline numbers */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: 12, marginBottom: 16 }}>
        {[
          { name: 'Spent, all time', value: fmt(d.totals.spend), sub: `across ${d.totals.cards} cards`, c: T.accent },
          { name: 'Last 12 months', value: fmt(d.totals.spend_12m), sub: 'net of refunds', c: T.accent2 },
          { name: 'Fees and interest', value: fmtFull(totalCost), sub: d.totals.spend ? `${pct1(totalCost / d.totals.spend * 100)} of spend` : '', c: T.warn },
          {
            name: 'Next bill to pay', value: nextPay ? dayLabel(nextPay.pay_on) : '—',
            sub: nextPay ? `${nextPay.days_to_pay >= 0 ? `in ${nextPay.days_to_pay} days` : 'passed'} · ${nextPay.cards.join(' + ')}` : 'no billing cycle yet', c: T.positive,
          },
        ].map(k => (
          <Card key={k.name} style={{ padding: '14px 18px', borderTop: `3px solid ${k.c}` }}>
            <div style={label}>{k.name}</div>
            <div style={{ fontFamily: 'var(--font-display, inherit)', fontSize: 24, fontWeight: 700, margin: '4px 0 2px' }}>{k.value}</div>
            <div style={{ fontSize: 12, color: T.muted }}>{k.sub}</div>
          </Card>
        ))}
      </div>

      {/* Each card */}
      {error && <div style={{ color: T.negative, fontSize: 12.5, marginBottom: 10 }}>Could not save the card order: {error}</div>}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: 16, marginBottom: 16 }}>
        {d.cards.map(c => (
          <div key={c.id} draggable title="Drag to reorder"
            onDragStart={e => { dragId.current = c.id; e.dataTransfer.effectAllowed = 'move' }}
            onDragOver={e => { e.preventDefault(); if (over !== c.id) setOver(c.id) }}
            onDragLeave={() => setOver(o => (o === c.id ? null : o))}
            onDrop={e => { e.preventDefault(); drop(c.id) }}
            onDragEnd={() => { dragId.current = null; setOver(null) }}
            style={{ borderRadius: 16, outline: over === c.id && dragId.current !== c.id ? `2px dashed ${T.accent}` : '2px solid transparent', outlineOffset: 3 }}>
            <CardTile c={c} today={d.today} color={color(c.id)} onPick={onPick} />
          </div>
        ))}
      </div>

      {/* Spend by financial year, split by card */}
      <Card style={{ padding: 20, marginBottom: 16 }}>
        {title('Spend by financial year', 'net of refunds')}
        <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', marginBottom: 12, fontSize: 11.5, color: T.muted }}>
          {d.cards.map(c => <span key={c.id} style={{ opacity: c.status === 'closed' ? 0.5 : 1 }}><CardChip color={c.color} name={c.name} size={16} />{c.name}{c.status === 'closed' ? ' (closed)' : ''}</span>)}
        </div>
        {d.years.map(y => (
          <div key={y.fy} style={{ display: 'grid', gridTemplateColumns: '64px 1fr 84px', gap: 12, alignItems: 'center', padding: '5px 0', fontSize: 12.5 }}>
            <span>{y.fy}</span>
            <div style={{ display: 'flex', height: 12, gap: GAP, width: `${(y.total / maxFy) * 100}%`, minWidth: 6 }}>
              {d.cards.filter(c => (y.by_card[String(c.id)] ?? 0) > 0).map(c => (
                <div key={c.id} title={`${c.name}: ${fmt(y.by_card[String(c.id)])}`}
                  style={{ flex: y.by_card[String(c.id)], background: color(c.id), borderRadius: 2 }} />
              ))}
            </div>
            <span style={{ textAlign: 'right' }}>{fmt(y.total)}</span>
          </div>
        ))}
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5, marginTop: 14 }}>
          <thead>
            <tr style={th}>
              <th style={{ textAlign: 'left', padding: '4px 0' }}>Year</th>
              {d.cards.map(c => <th key={c.id} style={{ textAlign: 'right' }}>{c.name.replace('ICICI Bank ', '')}</th>)}
              <th style={{ textAlign: 'right' }}>Total</th>
            </tr>
          </thead>
          <tbody>
            {d.years.map(y => (
              <tr key={y.fy} style={{ borderTop: `1px solid ${T.hairline}` }}>
                <td style={{ padding: '6px 0' }}>{y.fy}</td>
                {d.cards.map(c => {
                  const v = y.by_card[String(c.id)]
                  return <td key={c.id} style={{ textAlign: 'right', color: v ? T.text : T.muted }}>{v ? fmt(v) : '—'}</td>
                })}
                <td style={{ textAlign: 'right', fontWeight: 600 }}>{fmt(y.total)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <CardAdviceCard />

      {/* When to pay, every bill in one place */}
      <Card style={{ padding: 20, marginBottom: 16 }}>
        {title('When to pay', 'one line per bill; cards on the same bill are paid together')}
        {d.pay.length === 0 && <div style={{ fontSize: 12.5, color: T.muted }}>No billing cycle is known yet. Open a card and confirm its cycle.</div>}
        {d.pay.map(p => (
          <div key={p.card_id} style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: 12, padding: '9px 0', borderTop: `1px solid ${T.hairline}`, alignItems: 'baseline' }}>
            <div>
              <div style={{ fontSize: 14, fontWeight: 600 }}>{p.cards.join(' + ')}</div>
              <div style={{ fontSize: 11.5, color: T.muted }}>
                {p.issued ? 'issued' : 'next'} statement {dayLabel(p.statement)} · due {dayLabel(p.due)}
                {!p.verified && <span style={{ color: T.warn }}> · cycle assumed</span>}
                {p.stale && <span style={{ color: T.warn }}> · data is old</span>}
              </div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: 15, fontWeight: 700 }}>Pay {p.issued ? `${fmtFull(p.expected)} on ` : ''}{dayLabel(p.pay_on)}</div>
              <div style={{ fontSize: 11.5, color: T.muted }}>{p.days_to_pay >= 0 ? `in ${p.days_to_pay} days` : 'date passed'}</div>
            </div>
          </div>
        ))}
        <div style={{ fontSize: 11.5, color: T.muted, marginTop: 10 }}>
          The best day is the due date less a safety margin, never a weekend. Paying early gives away free credit;
          paying late costs a fee plus interest on the whole cycle.
        </div>
      </Card>
    </div>
  )
}

function CardTile({ c, today, color, onPick }: { c: OverviewCard; today: string; color: string; onPick: (id: number) => void }) {
  const use = idle(c.through, today)
  const was = c.numbers.slice(0, -1)
  return (
    <CreditCardFace color={color} issuer={c.issuer} name={c.name} last4={c.numbers[c.numbers.length - 1]} network={c.network} status={c.status} onClick={() => onPick(c.id)}
      hero={
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', gap: 12, width: '100%' }}>
          <div>
            <div style={{ ...label, fontSize: 9.5, color: 'inherit', opacity: 0.65 }}>Last 12 months</div>
            <div style={{ fontFamily: 'var(--font-display, inherit)', fontSize: 28, fontWeight: 700, lineHeight: 1.1 }}>{fmt(c.spend_12m)}</div>
          </div>
          <div style={{ textAlign: 'right' }}>
            <div style={{ ...label, fontSize: 9.5, color: 'inherit', opacity: 0.65 }}>Spent, all time</div>
            <div style={{ fontSize: 15, fontWeight: 700 }}>{fmt(c.spend)}</div>
          </div>
        </div>
      }>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: '6px 10px' }}>
        <Stat name="Transactions" value={`${c.transactions}`} sub={`avg ${fmt(c.avg_ticket)}`} />
        <Stat name="On EMI" value={c.emi ? fmt(c.emi) : '—'} sub={c.emi ? `${pct1(c.emi_share)} of spend` : undefined} />
        <Stat name="Fees and interest" value={c.fees ? fmtFull(c.fees) : '—'} sub={c.fees ? `${pct1(c.fees_share)} of spend` : undefined} warn={c.fees_share > 1} />
        {c.rewards
          ? <Stat name={c.earned_is_estimate ? 'Rewards (est.)' : 'Cashback'} value={fmtFull(c.earned)} />
          : <Stat name="Top merchant" value={c.top_merchant ? c.top_merchant.name : '—'} sub={c.top_merchant ? fmt(c.top_merchant.spend) : undefined} />}
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, fontSize: 9.5, opacity: 0.7, marginTop: 7, lineHeight: 1.35 }}>
        <span>
          {c.credit_limit ? `Limit ${fmt(c.credit_limit)}` : 'Limit not set'}{c.annual_fee ? ` · Fee ${fmt(c.annual_fee)}${c.fee_waiver_spend ? `, waived at ${fmt(c.fee_waiver_spend)}` : ''}` : ''}
          {' · '}{monthYear(c.since)} to {monthYear(c.through)}
          {was.length > 0 && <> · earlier ···{was.slice().reverse().join(', ···')}</>}
          {c.shared_with.length > 0 && <> · shares bill with {c.shared_with.join(', ')}</>}
        </span>
        <span style={{ whiteSpace: 'nowrap', fontWeight: use.retired ? 700 : 400, color: use.retired ? T.warn : undefined }}>{c.status === 'closed' ? 'closed' : use.text}</span>
      </div>
    </CreditCardFace>
  )
}

function Stat({ name, value, sub, warn }: { name: string; value: string; sub?: string; warn?: boolean }) {
  return (
    <div style={{ minWidth: 0 }}>
      <div style={{ ...label, fontSize: 8.5, color: 'inherit', opacity: 0.65, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{name}</div>
      <div style={{ fontSize: 12.5, fontWeight: 700, color: warn ? T.warn : 'inherit', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={value}>{value}</div>
      {sub && <div style={{ fontSize: 9, opacity: 0.7, whiteSpace: 'nowrap' }}>{sub}</div>}
    </div>
  )
}
