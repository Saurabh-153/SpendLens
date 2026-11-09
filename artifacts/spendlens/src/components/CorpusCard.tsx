import { useState, type CSSProperties, type PointerEvent } from 'react'
import type { BandPoint, PortfolioKpis } from '../api'
import { T, fmt } from '../theme'
import { Card } from './ui'
import {
  CardHead, Callout, Chip, KIND_COLOR, MON, Stat, Tip, TipRow, chipGroup, hairCursor, labelStep, legend, niceTicks, probColor, spread, statGrid, useWidth,
} from './chartKit'

const INFLATION = 0.06  // for the "today's ₹" view
const CARD_W = 150, CARD_GAP = 8

type Forecast = NonNullable<PortfolioKpis['forecast']>

/** Large goals and the corpus: the P10–P90 fan, middle and lower-returns lines, one numbered badge per goal above the
 *  plot (spread so badges never touch) and a lane of goal cards under it, each at its payout year. */
export default function CorpusCard({ f, extraSip }: { f: Forecast; extraSip: number }) {
  const [ref, W] = useWidth()
  const [show, setShow] = useState({ band: true, cons: true, real: false })
  const [goalId, setGoalId] = useState<number | null>(null)
  const [hoverGoal, setHoverGoal] = useState<number | null>(null)
  const [hoverYear, setHoverYear] = useState<number | null>(null)
  const y0 = f.band[0].year, y1 = f.band[f.band.length - 1].year
  const defl = (v: number, yr: number) => (show.real ? v / (1 + INFLATION) ** (yr - y0) : v)
  const b: BandPoint[] = f.band.map(p => ({ year: p.year, p10: defl(p.p10, p.year), p50: defl(p.p50, p.year), p90: defl(p.p90, p.year) }))
  const cons = new Map(f.conservative_band.map(p => [p.year, defl(p.p50, p.year)]))
  const goals = f.goals.filter(g => g.target_year >= y0 && g.target_year <= y1).sort((a, c) => a.target_year - c.target_year || a.id - c.id)
  const num = new Map(goals.map((g, i) => [g.id, i + 1]))
  const last = b[b.length - 1], consLast = cons.get(last.year) ?? 0
  const sel = goals.find(g => g.id === goalId)
  const lit = hoverGoal ?? goalId

  const MH = 240, L = 58, R = 70, BADGE = 24, T0 = BADGE + 8, H = T0 + MH + 24
  const x = (yr: number) => L + ((yr - y0) / (y1 - y0 || 1)) * (W - L - R)
  const ticks = niceTicks(0, Math.max(1, ...b.map(p => (show.band ? p.p90 : p.p50)), ...[...cons.values()]) * 1.05)
  const hi = ticks[ticks.length - 1]
  const y = (v: number) => T0 + (1 - Math.max(0, v) / hi) * MH
  const line = (pts: { year: number; v: number }[]) => pts.map((p, i) => `${i ? 'L' : 'M'}${x(p.year).toFixed(1)},${y(p.v).toFixed(1)}`).join('')
  const of = (k: 'p10' | 'p50' | 'p90') => b.map(p => ({ year: p.year, v: p[k] }))
  const area = line(of('p90')) + [...b].reverse().map(p => `L${x(p.year).toFixed(1)},${y(p.p10).toFixed(1)}`).join('') + 'Z'
  const dry = b.find((p, i) => i > 0 && p.p10 <= 0 && b[i - 1].p10 > 0)
  const step = labelStep((W - L - R) / (y1 - y0 || 1))
  const years = b.filter(p => (p.year - y0) % step === 0).map(p => p.year)
  if (x(y1) - x(years[years.length - 1]) >= 34) years.push(y1)
  // Right-edge labels, pushed apart so they never stack.
  const edge = [{ v: last.p50, t: fmt(last.p50), color: T.accent, bold: true },
    ...(show.band ? [{ v: last.p90, t: fmt(last.p90), color: T.muted, bold: false }] : []),
    ...(show.cons ? [{ v: consLast, t: fmt(consLast), color: T.warn, bold: false }] : [])].sort((a, c) => y(a.v) - y(c.v))
  const edgeY = spread(edge.map(e => y(e.v)), 14, T0 + 4, T0 + MH)
  const gx = goals.map(g => x(g.target_year))
  const badgeX = spread(gx, 22, L + 10, W - R - 10)
  // Lane of goal cards: at their payout year when they fit side by side, otherwise a plain grid.
  const asList = goals.length * (CARD_W + CARD_GAP) > W
  const cardX = asList ? [] : spread(gx.map(v => v - CARD_W / 2), CARD_W + CARD_GAP, 0, W - CARD_W)

  const hov = hoverYear == null ? null : b.find(p => p.year === hoverYear)
  const onMove = (e: PointerEvent<SVGRectElement>) => {
    const px = e.clientX - e.currentTarget.ownerSVGElement!.getBoundingClientRect().left
    setHoverYear(Math.max(y0, Math.min(y1, Math.round(y0 + ((px - L) / (W - L - R)) * (y1 - y0)))))
  }
  const pick = (id: number) => setGoalId(id === goalId ? null : id)
  const onTrack = goals.filter(g => g.probability >= 70).length
  const weakest = goals.reduce<(typeof goals)[number] | null>((a, g) => (!a || g.probability < a.probability ? g : a), null)

  const si = sel ? b.findIndex(p => p.year === sel.target_year) : -1
  const summary = sel && si >= 0 ? <>
    <Stat l={`${num.get(sel.id)} · ${sel.name}`} v={fmt(defl(sel.target_amount, sel.target_year))} s={`paid out in ${sel.target_year}`} />
    <Stat l="Chance it's fully funded" v={`${sel.probability}%`} color={probColor(sel.probability)} s={`${sel.conservative}% with lower returns`} />
    <Stat l="Corpus before payout" v={fmt(b[Math.max(0, si - 1)].p50)} s={`middle case, ${b[Math.max(0, si - 1)].year}`} />
    <Stat l="Corpus after payout" v={fmt(b[si].p50)} s={`bad case ${fmt(b[si].p10)}`} />
  </> : <>
    {goals.length > 0 && <Stat l="Large goals on track" v={`${onTrack} of ${goals.length}`} color={onTrack === goals.length ? T.positive : T.warn} s="70% chance or better" />}
    <Stat l={`Corpus in ${last.year}`} v={fmt(last.p50)} s="middle case, after every goal" />
    <Stat l="Likely range" v={<span style={{ fontSize: 15 }}>{fmt(last.p10)} – {fmt(last.p90)}</span>} s="8 in 10 simulations land here" />
    <Stat l="Lower-returns case" v={fmt(consLast)} color={T.warn} s="returns 3 points lower, flat SIPs" />
  </>

  const goalCard = (g: (typeof goals)[number], style: CSSProperties) => {
    const on = lit === g.id
    return (
      <button key={g.id} onClick={() => pick(g.id)} onPointerEnter={() => setHoverGoal(g.id)} onPointerLeave={() => setHoverGoal(null)}
        aria-pressed={goalId === g.id} style={{
          ...style, boxSizing: 'border-box', border: `1px solid ${on ? KIND_COLOR.large : T.border}`, background: on ? T.surface : T.surface2,
          borderRadius: 9, padding: '8px 10px', font: 'inherit', fontSize: 12, color: T.text, textAlign: 'left', cursor: 'pointer', display: 'grid', gap: 4, minWidth: 0,
        }}>
        <span style={{ display: 'flex', gap: 6, alignItems: 'center', minWidth: 0 }}>
          <span style={{ flex: 'none', width: 17, height: 17, borderRadius: '50%', background: KIND_COLOR.large, color: '#fff', fontSize: 10, fontWeight: 700, lineHeight: '17px', textAlign: 'center' }}>{num.get(g.id)}</span>
          <b style={{ fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={g.name}>{g.name}</b>
        </span>
        <span style={{ fontSize: 11, color: T.muted, fontVariantNumeric: 'tabular-nums' }}>{g.target_month ? `${MON[g.target_month - 1]} ` : ''}{g.target_year} · {fmt(defl(g.target_amount, g.target_year))}</span>
        <span style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', fontVariantNumeric: 'tabular-nums' }}>
          <strong style={{ fontSize: 17, color: probColor(g.probability) }}>{g.probability}%</strong>
          <span style={{ fontSize: 10.5, color: T.muted }}>low returns <b style={{ color: probColor(g.conservative) }}>{g.conservative}%</b></span>
        </span>
        <span style={{ position: 'relative', height: 5, borderRadius: 5, background: T.border, overflow: 'hidden' }}>
          <i style={{ position: 'absolute', inset: '0 auto 0 0', width: `${g.conservative}%`, background: probColor(g.conservative), opacity: 0.4 }} />
          <i style={{ position: 'absolute', left: 0, top: 0, height: '55%', width: `${g.probability}%`, background: probColor(g.probability), borderRadius: 5 }} />
        </span>
      </button>
    )
  }

  return (
    <Card>
      <CardHead title="Large goals & corpus" sub={`${f.paths.toLocaleString('en-IN')} simulations · paid from investments`}>
        <div style={chipGroup}>
          <Chip on={show.band} onClick={() => setShow(s => ({ ...s, band: !s.band }))}>Range</Chip>
          <Chip on={show.cons} onClick={() => setShow(s => ({ ...s, cons: !s.cons }))}>Lower returns</Chip>
          <Chip on={show.real} onClick={() => setShow(s => ({ ...s, real: !s.real }))}>Today's ₹</Chip>
        </div>
      </CardHead>
      <div style={statGrid}>{summary}</div>
      <div ref={ref} style={{ position: 'relative' }}>
        {W > 0 && (
          <svg width={W} height={H} style={{ display: 'block', overflow: 'visible' }}>
            {ticks.map(t => (
              <g key={t}>
                <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} stroke={T.hairline} />
                <text x={L - 8} y={y(t) + 4} textAnchor="end" fontSize="10.5" fill={T.muted}>{t ? fmt(t) : '₹0'}</text>
              </g>
            ))}
            {years.map(yr => <text key={yr} x={x(yr)} y={T0 + MH + 17} textAnchor="middle" fontSize="10.5" fill={T.muted}>{yr}</text>)}
            {show.band && <>
              <path d={area} fill={T.accent} opacity="0.16" />
              <path d={line(of('p90'))} fill="none" stroke={T.accent} strokeWidth="1" opacity="0.5" />
              <path d={line(of('p10'))} fill="none" stroke={T.accent} strokeWidth="1" opacity="0.5" />
            </>}
            {show.cons && <path d={line(b.map(p => ({ year: p.year, v: cons.get(p.year) ?? 0 })))} fill="none" stroke={T.warn} strokeWidth="1.6" strokeDasharray="4 4" />}
            <path d={line(of('p50'))} fill="none" stroke={T.accent} strokeWidth="2.4" strokeLinejoin="round" />
            {show.band && dry && (
              <g>
                <circle cx={x(dry.year)} cy={y(0)} r="4" fill={T.negative} />
                <text x={Math.min(x(dry.year) + 6, W - R - 130)} y={y(0) - 7} fontSize="10" fontWeight="600" fill={T.negative}>bad case runs out {dry.year}</text>
              </g>
            )}
            {edge.map((e, i) => <text key={i} x={W - R + 8} y={edgeY[i] + 4} fontSize="10.5" fontWeight={e.bold ? 700 : 400} fill={e.color}>{e.t}</text>)}
            {hov && <>
              <line x1={x(hov.year)} x2={x(hov.year)} y1={T0} y2={T0 + MH} stroke={T.muted} strokeDasharray="2 3" />
              <circle cx={x(hov.year)} cy={y(hov.p50)} r="4.5" fill={T.accent} stroke={T.surface} strokeWidth="2" />
            </>}
            <rect x={L} y={T0} width={Math.max(0, W - L - R)} height={MH} fill="transparent" style={hairCursor}
              onPointerMove={onMove} onPointerDown={onMove} onPointerLeave={() => setHoverYear(null)} />
            {goals.map((g, i) => {
              const on = lit === g.id, dim = lit != null && !on
              return (
                <g key={g.id} style={{ cursor: 'pointer' }} opacity={dim ? 0.35 : 1} onClick={() => pick(g.id)}
                  onPointerEnter={() => setHoverGoal(g.id)} onPointerLeave={() => setHoverGoal(null)}>
                  <path d={`M${badgeX[i]},${BADGE - 2}L${gx[i]},${T0}L${gx[i]},${T0 + MH}`} fill="none" stroke={KIND_COLOR.large} strokeDasharray="2 3" opacity={on ? 0.95 : 0.5} />
                  <circle cx={badgeX[i]} cy={BADGE / 2} r={on ? 10.5 : 9} fill={KIND_COLOR.large} />
                  <text x={badgeX[i]} y={BADGE / 2 + 3.5} textAnchor="middle" fontSize="10" fontWeight="700" fill="#fff">{i + 1}</text>
                  <circle cx={gx[i]} cy={y(defl(g.target_amount, g.target_year))} r={on ? 5.5 : 4} fill={KIND_COLOR.large} stroke={T.surface} strokeWidth="1.5" />
                </g>
              )
            })}
          </svg>
        )}
        {hov && (
          <Tip x={x(hov.year)} w={W} top={T0 + 6}>
            <div style={{ fontWeight: 600, marginBottom: 2 }}>End of {hov.year}{show.real ? " · today's ₹" : ''}</div>
            {show.band && <TipRow l="Good case (P90)" v={fmt(hov.p90)} />}
            <TipRow l="Middle case" v={fmt(hov.p50)} bold />
            {show.band && <TipRow l="Bad case (P10)" v={hov.p10 <= 0 ? 'runs out' : fmt(hov.p10)} color={hov.p10 <= 0 ? T.negative : undefined} />}
            {show.cons && <TipRow l="Lower returns" v={fmt(cons.get(hov.year) ?? 0)} color={T.warn} />}
            {goals.filter(g => g.target_year === hov.year).map(g => (
              <TipRow key={g.id} l={<span style={{ color: KIND_COLOR.large }}>{num.get(g.id)} · {g.name} ({g.probability}%)</span>} v={`−${fmt(defl(g.target_amount, hov.year))}`} color={KIND_COLOR.large} />
            ))}
          </Tip>
        )}
      </div>
      {goals.length > 0 && (asList
        ? <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: CARD_GAP, marginTop: 10 }}>{goals.map(g => goalCard(g, {}))}</div>
        : (
          <div style={{ position: 'relative', height: 118, marginTop: 2 }}>
            <svg width={W} height={14} style={{ position: 'absolute', top: 0, left: 0, overflow: 'visible' }}>
              {goals.map((g, i) => <path key={g.id} d={`M${gx[i]},0L${gx[i]},4L${cardX[i] + CARD_W / 2},13`} fill="none" stroke={KIND_COLOR.large} opacity="0.5" />)}
            </svg>
            {goals.map((g, i) => goalCard(g, { position: 'absolute', top: 14, left: cardX[i], width: CARD_W }))}
          </div>
        ))}
      {goals.length > 0 && (extraSip > 0
        ? <Callout tone={T.warn} icon="!">Adding about <b>{fmt(extraSip)} a month</b> to SIPs would lift every large goal to 70% or better.{weakest ? <> <b>{weakest.name}</b> is the weakest at {weakest.probability}%.</> : null} The emergency fund is kept out of goal money.</Callout>
        : <Callout tone={T.positive} icon="✓">At today's SIPs every large goal clears 70%. The emergency fund is kept out of goal money.</Callout>)}
      <div style={legend}>
        <span><b style={{ color: T.accent }}>━</b> middle case</span>
        <span><b style={{ color: T.warn }}>╌</b> returns 3 points lower, flat SIPs</span>
        <span>shaded: 1 in 10 worse (P10) to 1 in 10 better (P90)</span>
        <span><b style={{ color: KIND_COLOR.large }}>●</b> large goal payout</span>
        {show.real && <span>today's ₹ at {INFLATION * 100}% inflation</span>}
      </div>
    </Card>
  )
}
