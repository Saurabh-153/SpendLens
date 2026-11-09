import { useState, type PointerEvent } from 'react'
import type { Commitments, RecurringPlan } from '../api'
import { T, fmt } from '../theme'
import { Card, label } from './ui'
import {
  CardHead, Callout, Chip, KIND_COLOR, MON, Stat, Tip, TipRow, chipGroup, hairCursor, legend, niceTicks, spread, statGrid, useWidth,
} from './chartKit'

const mi = (ym: string) => { const [y, m] = ym.split('-').map(Number); return y * 12 + m - 1 }
const monYr = (i: number) => `${MON[i % 12]} ’${String(Math.floor(i / 12)).slice(2)}`
const ymLabel = (ym: string) => monYr(mi(ym))

/** Small goals and recurring expenses over the next 24 months, paid from one steady monthly set-aside. Two views:
 *  the pot (rises by the set-aside, drops at each payment) and the monthly outflow against the set-aside line. */
export default function CommitmentsCard({ c, onEdit }: { c: Commitments; onEdit: () => void }) {
  const [ref, W] = useWidth()
  const [view, setView] = useState<'pot' | 'flow'>('pot')
  const [lit, setLit] = useState<number | null>(null)
  const [hoverK, setHoverK] = useState<number | null>(null)
  const now = mi(c.start), N = c.months
  const atK = (k: number) => c.payments.filter(p => mi(p.month) === now + k)

  if (!c.small.length && !c.recurring.length) {
    return (
      <Card>
        <CardHead title="Small goals & yearly expenses" />
        <div style={{ color: T.muted, fontSize: 13, lineHeight: 1.5 }}>
          Add small goals (a phone, a trip) or yearly expenses (school fees, the trip home, insurance) and they are planned here
          from one monthly set-aside, apart from the corpus. Recurring expenses can be linked to an expense category to compare planned with spent.
        </div>
        <button onClick={onEdit} style={{ background: 'none', border: 'none', color: T.accent, cursor: 'pointer', fontSize: 13, padding: 0, marginTop: 10 }}>Add in Goals &amp; targets →</button>
      </Card>
    )
  }

  // Pot balance after each month's payments, starting from the top-up.
  const pot: number[] = [c.top_up]
  for (let k = 1; k <= N; k++) pot.push(pot[k - 1] + c.set_aside - atK(k).reduce((s, p) => s + p.amount, 0))
  const yearRec = c.payments.filter(p => p.kind === 'recurring' && mi(p.month) <= now + 12).reduce((s, p) => s + p.amount, 0)
  const next = c.payments[0]
  const usePct = c.surplus > 0 ? Math.round((c.set_aside / c.surplus) * 100) : null

  const L = 58, R = 14, T0 = 10, MH = 170
  const H = T0 + MH + (view === 'pot' ? 48 : 24)
  const x = (k: number) => L + (k / N) * (W - L - R)
  const monthStep = W < 520 ? 6 : 3
  const monthTicks = Array.from({ length: Math.floor(N / monthStep) + 1 }, (_, i) => i * monthStep)
  const potPts: [number, number][] = [[0, pot[0]]]
  let bal = pot[0]
  for (let k = 1; k <= N; k++) {
    bal += c.set_aside
    potPts.push([k, bal])
    const out = atK(k).reduce((s, p) => s + p.amount, 0)
    if (out) { bal -= out; potPts.push([k, bal]) }
  }
  const flow = Array.from({ length: N + 1 }, (_, k) => ({
    small: atK(k).filter(p => p.kind === 'small').reduce((s, p) => s + p.amount, 0),
    rec: atK(k).filter(p => p.kind === 'recurring').reduce((s, p) => s + p.amount, 0),
  }))
  const top = view === 'pot' ? Math.max(1, ...potPts.map(p => p[1])) : Math.max(c.set_aside, ...flow.map(f => f.small + f.rec))
  const ticks = niceTicks(0, top * 1.08), hi = ticks[ticks.length - 1]
  const y = (v: number) => T0 + (1 - Math.max(0, v) / hi) * MH
  const potPath = potPts.map(([k, v], i) => `${i ? 'L' : 'M'}${x(k).toFixed(1)},${y(v).toFixed(1)}`).join('')
  // Payment dots under the axis, one row per kind, spread so none touch.
  const rows = (['small', 'recurring'] as const).map((kind, r) => {
    const ps = c.payments.filter(p => p.kind === kind && mi(p.month) - now >= 1)
    return { kind, y: T0 + MH + 28 + r * 13, ps, xs: spread(ps.map(p => x(mi(p.month) - now)), 11, L, W - R) }
  })
  const bw = (W - L - R) / N
  const onMove = (e: PointerEvent<SVGRectElement>) => {
    const px = e.clientX - e.currentTarget.ownerSVGElement!.getBoundingClientRect().left
    setHoverK(Math.max(1, Math.min(N, Math.round(((px - L) / (W - L - R)) * N))))
  }

  const spark = (r: RecurringPlan) => {
    const ys = r.yearly, mx = Math.max(1, ...ys.map(v => v.amount)), w = 74, h = 20, sw = w / Math.max(ys.length, 1)
    return (
      <svg width={w} height={h} aria-label="yearly cost">
        {ys.map((v, i) => <rect key={v.year} x={i * sw + 0.5} y={h - (v.amount / mx) * h} width={Math.max(1, sw - 1.5)} height={(v.amount / mx) * h} fill={KIND_COLOR.recurring} opacity={i ? 0.45 : 0.9}><title>{v.year}: {fmt(v.amount)}</title></rect>)}
      </svg>
    )
  }
  const rowStyle = (on: boolean) => ({
    display: 'grid', gridTemplateColumns: 'auto minmax(0, 1fr) auto', gap: 10, alignItems: 'center', padding: '8px 10px', borderRadius: 8,
    background: T.surface2, fontSize: 12.5, boxShadow: on ? `inset 0 0 0 1px ${T.text}` : 'none',
  })
  const icon = (name: string, color: string) => (
    <span style={{ width: 26, height: 26, borderRadius: 7, display: 'grid', placeItems: 'center', fontSize: 11, fontWeight: 700, color: '#fff', background: color }}>{name.trim()[0]?.toUpperCase()}</span>
  )
  const muted = { color: T.muted, fontSize: 11, fontVariantNumeric: 'tabular-nums' as const }

  return (
    <Card>
      <CardHead title="Small goals & yearly expenses" sub={`next ${N} months · paid from a monthly set-aside`}>
        <div style={chipGroup}>
          <Chip on={view === 'pot'} onClick={() => setView('pot')}>Pot</Chip>
          <Chip on={view === 'flow'} onClick={() => setView('flow')}>Monthly outflow</Chip>
        </div>
      </CardHead>
      <div style={statGrid}>
        <Stat l="Set aside each month" v={fmt(c.set_aside)} color={KIND_COLOR.small} s="covers everything below on time" />
        <Stat l="Top up now" v={c.top_up ? fmt(c.top_up) : 'None'} color={c.top_up ? T.warn : T.positive}
          s={c.top_up && next ? `so ${next.name} in ${ymLabel(next.month)} is covered` : 'the pot builds up in time'} />
        <Stat l="Yearly expenses" v={fmt(yearRec)} color={KIND_COLOR.recurring} s={`${c.recurring.length} item${c.recurring.length === 1 ? '' : 's'}, next 12 months`} />
        {next && <Stat l="Next payment" v={fmt(next.amount)} s={`${next.name} · ${ymLabel(next.month)}`} />}
      </div>
      {usePct != null && (
        <div style={{ display: 'grid', gap: 5, marginBottom: 14 }}>
          <div style={{ ...muted, display: 'flex', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
            <span>Monthly surplus {fmt(c.surplus)} (income {fmt(c.income)} − spend {fmt(c.spend)} − SIPs {fmt(c.sip)})</span>
            <b style={{ color: usePct > 80 ? T.negative : usePct > 50 ? T.warn : T.positive }}>set-aside uses {usePct}%</b>
          </div>
          <div style={{ display: 'flex', height: 10, borderRadius: 5, overflow: 'hidden', background: T.surface2 }}>
            <i style={{ width: `${Math.min(100, usePct)}%`, background: KIND_COLOR.small }} />
            <i style={{ width: `${Math.max(0, 100 - usePct)}%`, background: T.positive, opacity: 0.35 }} />
          </div>
          <div style={muted}>{c.surplus - c.set_aside >= 0 ? `${fmt(c.surplus - c.set_aside)} a month still free to invest or spend` : `${fmt(c.set_aside - c.surplus)} a month more than the surplus`}</div>
        </div>
      )}
      {c.surplus <= 0 && <Callout tone={T.negative} icon="!">Average spending and SIPs already use the whole income, so the set-aside has to come from somewhere else.</Callout>}

      <div ref={ref} style={{ position: 'relative', marginTop: 4 }}>
        {W > 0 && (
          <svg width={W} height={H} style={{ display: 'block', overflow: 'visible' }}>
            {ticks.map(t => (
              <g key={t}>
                <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} stroke={T.hairline} />
                <text x={L - 8} y={y(t) + 4} textAnchor="end" fontSize="10.5" fill={T.muted}>{t ? fmt(t) : '₹0'}</text>
              </g>
            ))}
            {monthTicks.map(k => (
              <text key={k} x={view === 'pot' ? x(k) : x(Math.max(k, 1)) - bw / 2} y={T0 + MH + 15} textAnchor="middle" fontSize="10.5" fill={T.muted}>
                {(now + k) % 12 === 0 || k === 0 ? monYr(now + k) : MON[(now + k) % 12]}
              </text>
            ))}
            {view === 'pot' ? <>
              <path d={`${potPath}L${x(N)},${y(0)}L${x(0)},${y(0)}Z`} fill={KIND_COLOR.small} opacity="0.12" />
              <path d={potPath} fill="none" stroke={KIND_COLOR.small} strokeWidth="2" strokeLinejoin="round" />
              <text x={L - 8} y={rows[0].y + 4} textAnchor="end" fontSize="10" fill={KIND_COLOR.small}>goals</text>
              <text x={L - 8} y={rows[1].y + 4} textAnchor="end" fontSize="10" fill={KIND_COLOR.recurring}>yearly</text>
              {rows.map(r => r.ps.map((p, i) => {
                const on = lit === p.goal_id, px = x(mi(p.month) - now)
                return (
                  <g key={`${r.kind}${p.goal_id}${p.month}`} opacity={lit != null && !on ? 0.3 : 1}>
                    <title>{p.name} · {ymLabel(p.month)} · {fmt(p.amount)}</title>
                    {on && <line x1={px} x2={px} y1={T0} y2={T0 + MH} stroke={KIND_COLOR[r.kind]} strokeDasharray="2 3" />}
                    <line x1={px} x2={r.xs[i]} y1={T0 + MH} y2={r.y - 4} stroke={KIND_COLOR[r.kind]} opacity="0.45" />
                    <circle cx={r.xs[i]} cy={r.y} r={on ? 5.5 : 4} fill={KIND_COLOR[r.kind]} />
                  </g>
                )
              }))}
            </> : <>
              {flow.slice(1).map((f, i) => {
                const k = i + 1, left = x(k - 1) + 2, w = Math.max(1, bw - 4)
                const on = lit != null && atK(k).some(p => p.goal_id === lit)
                return (f.rec || f.small) ? (
                  <g key={k} opacity={lit != null && !on ? 0.3 : 1}>
                    {f.rec > 0 && <rect x={left} y={y(f.rec)} width={w} height={y(0) - y(f.rec)} rx="2" fill={KIND_COLOR.recurring} opacity="0.85" />}
                    {f.small > 0 && <rect x={left} y={y(f.rec + f.small)} width={w} height={y(f.rec) - y(f.rec + f.small)} rx="2" fill={KIND_COLOR.small} opacity="0.85" />}
                  </g>
                ) : null
              })}
              <line x1={L} x2={W - R} y1={y(c.set_aside)} y2={y(c.set_aside)} stroke={T.text} strokeDasharray="5 4" />
              <text x={W - R} y={y(c.set_aside) - 5} textAnchor="end" fontSize="10.5" fontWeight="600" fill={T.text}>set aside {fmt(c.set_aside)}/mo</text>
            </>}
            {hoverK != null && <line x1={view === 'pot' ? x(hoverK) : x(hoverK) - bw / 2} x2={view === 'pot' ? x(hoverK) : x(hoverK) - bw / 2} y1={T0} y2={T0 + MH} stroke={T.muted} strokeDasharray="2 3" />}
            <rect x={L} y={T0} width={Math.max(0, W - L - R)} height={MH} fill="transparent" style={hairCursor}
              onPointerMove={onMove} onPointerDown={onMove} onPointerLeave={() => setHoverK(null)} />
          </svg>
        )}
        {hoverK != null && (
          <Tip x={view === 'pot' ? x(hoverK) : x(hoverK) - bw / 2} w={W} top={8}>
            <div style={{ fontWeight: 600, marginBottom: 2 }}>{monYr(now + hoverK)}</div>
            <TipRow l="Pot after payments" v={fmt(pot[hoverK])} bold color={pot[hoverK] < 0 ? T.negative : undefined} />
            {atK(hoverK).map(p => <TipRow key={`${p.goal_id}`} l={<span style={{ color: KIND_COLOR[p.kind] }}>{p.name}</span>} v={`−${fmt(p.amount)}`} />)}
            {!atK(hoverK).length && <TipRow l="No payments" v="" />}
          </Tip>
        )}
      </div>
      <div style={legend}>
        {view === 'pot'
          ? <><span><b style={{ color: KIND_COLOR.small }}>━</b> pot: rises by the set-aside, drops at each payment</span><span><b style={{ color: KIND_COLOR.small }}>●</b> small goal</span><span><b style={{ color: KIND_COLOR.recurring }}>●</b> yearly expense</span></>
          : <><span><b style={{ color: KIND_COLOR.recurring }}>▇</b> yearly expenses</span><span><b style={{ color: KIND_COLOR.small }}>▇</b> small goals</span><span>╌ steady monthly set-aside</span></>}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 18, marginTop: 14 }}>
        {c.small.length > 0 && (
          <div style={{ minWidth: 0 }}>
            <div style={{ ...label, marginBottom: 8 }}>Small goals</div>
            <div style={{ display: 'grid', gap: 6 }}>
              {c.small.map(g => (
                <div key={g.id} style={rowStyle(lit === g.id)} onPointerEnter={() => setLit(g.id)} onPointerLeave={() => setLit(null)}>
                  {icon(g.name, KIND_COLOR.small)}
                  <span style={{ minWidth: 0 }}>
                    <b style={{ fontWeight: 600 }}>{g.name}</b><br />
                    <span style={muted}>{ymLabel(g.month)} · {g.months_left >= 1 ? `${g.months_left} months · ${fmt(g.per_month)}/mo` : <b style={{ color: T.warn }}>due now</b>}</span>
                  </span>
                  <span style={{ fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>{fmt(g.amount)}</span>
                </div>
              ))}
            </div>
          </div>
        )}
        {c.recurring.length > 0 && (
          <div style={{ minWidth: 0 }}>
            <div style={{ ...label, marginBottom: 8 }}>Yearly expenses · planned vs spent</div>
            <div style={{ display: 'grid', gap: 6 }}>
              {c.recurring.map(r => {
                const plan = r.planned ?? r.next?.amount ?? 0
                const over = r.spent != null && plan > 0 && r.spent > plan
                return (
                  <div key={r.id} style={rowStyle(lit === r.id)} onPointerEnter={() => setLit(r.id)} onPointerLeave={() => setLit(null)}>
                    {icon(r.name, KIND_COLOR.recurring)}
                    <span style={{ minWidth: 0 }}>
                      <b style={{ fontWeight: 600 }}>{r.name}</b>
                      {r.link && <span style={{ fontSize: 10.5, padding: '1px 6px', borderRadius: 4, border: `1px solid ${T.border}`, color: T.muted, marginLeft: 6 }}>{r.link}</span>}
                      <br />
                      <span style={muted}>
                        {r.every_months === 12 ? `every ${MON[r.month - 1]}` : `every ${r.every_months} months`}
                        {r.escalation_pct ? ` · +${r.escalation_pct}% a year` : ''}{r.end_year ? ` · until ${r.end_year}` : ''}
                        {r.next ? ` · next ${fmt(r.next.amount)} in ${ymLabel(r.next.month)}` : ' · ended'}
                      </span>
                      {r.spent != null && (
                        <span style={{ display: 'grid', gap: 3, marginTop: 5 }}>
                          <span style={{ position: 'relative', height: 6, borderRadius: 5, background: T.border, overflow: 'hidden' }}>
                            <i style={{ position: 'absolute', inset: '0 auto 0 0', width: `${plan ? Math.min(100, (r.spent / plan) * 100) : 0}%`, background: over ? T.negative : KIND_COLOR.recurring, borderRadius: 5 }} />
                          </span>
                          <span style={muted}>
                            spent {fmt(r.spent)}{plan ? ` of ${fmt(plan)}` : ''} since {r.since ? ymLabel(r.since.slice(0, 7)) : ''}
                            {over && <b style={{ color: T.negative }}> · {fmt(r.spent - plan)} over plan</b>}
                          </span>
                        </span>
                      )}
                    </span>
                    <span style={{ display: 'grid', justifyItems: 'end', gap: 2 }}>
                      {spark(r)}
                      {r.yearly.length > 0 && <span style={muted}>{r.yearly[0].year}–{r.yearly[r.yearly.length - 1].year}</span>}
                    </span>
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </div>
    </Card>
  )
}
