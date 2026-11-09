import { useMemo, useState, type PointerEvent } from 'react'
import type { PortfolioKpis } from '../api'
import { T, fmt, signed } from '../theme'
import { useNarrow } from '../useNarrow'
import { Card, label } from './ui'
import { CardHead, Chip, MON, Stat, Tip, TipRow, chipGroup, hairCursor, legend, niceTicks, statGrid, useWidth } from './chartKit'
import CorpusCard from './CorpusCard'
import CommitmentsCard from './CommitmentsCard'

const title = (t: string, right?: string) => (
  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
    <span style={{ ...label, fontSize: 12.5, letterSpacing: 0.8 }}>{t}</span>
    {right && <span style={{ ...label, fontSize: 10.5 }}>{right}</span>}
  </div>
)

const dayMon = (d: Date) => `${d.getDate()} ${MON[d.getMonth()]}`
const dayMonYear = (d: Date) => `${dayMon(d)} ${d.getFullYear()}`
const parseDay = (s: string) => { const [y, m, d] = s.split('-').map(Number); return new Date(y, m - 1, d) }
const pctText = (n: number) => `${n >= 0 ? '+' : ''}${n.toFixed(1)}%`

const RANGES: [string, number][] = [['1M', 30], ['3M', 91], ['6M', 182], ['1Y', 365]]

/** Net worth vs invested over the snapshots, with a range picker, a you-vs-market split and a below-peak strip. */
function NetWorth({ history }: { history: PortfolioKpis['history'] }) {
  const [ref, W] = useWidth()
  const [days, setDays] = useState(0)
  const [hover, setHover] = useState<number | null>(null)
  const [custom, setCustom] = useState<[number, number] | null>(null)   // a range dragged out on the chart (ms timestamps)
  const [drag, setDrag] = useState<{ a: number; b: number } | null>(null) // the drag in progress, in px
  // Drawdown is measured from the running peak over all history, so a short range can start below the peak.
  const all = useMemo(() => {
    let peak = 0
    return history.map(p => { peak = Math.max(peak, p.total); return { ...p, d: parseDay(p.date), dd: peak ? ((p.total - peak) / peak) * 100 : 0 } })
  }, [history])
  const lastT = +all[all.length - 1].d
  const span = (lastT - +all[0].d) / 864e5
  const inRange = custom ? all.filter(p => +p.d >= custom[0] && +p.d <= custom[1])
    : days ? all.filter(p => (lastT - +p.d) / 864e5 <= days) : all
  const h = inRange.length > 1 ? inRange : all.slice(-2)
  const first = h[0], last = h[h.length - 1]
  const peakAll = all.reduce((a, p) => (p.total > a.total ? p : a))
  const peak = h.reduce((a, p) => (p.total > a.total ? p : a))
  const worst = h.reduce((a, p) => (p.dd < a.dd ? p : a))
  const change = last.total - first.total, added = last.invested - first.invested, market = change - added
  const splitTotal = Math.abs(added) + Math.abs(market) || 1

  const MH = 210, DH = 44, GAP = 46, L = 58, R = 64, T0 = 12  // GAP leaves room for the month labels, then the strip's title row
  const dT = T0 + MH + GAP, H = dT + DH + 4
  const t0 = +first.d, t1 = +last.d
  const x = (d: Date) => L + ((+d - t0) / (t1 - t0 || 1)) * (W - L - R)
  const rawLo = Math.min(...h.map(p => Math.min(p.total, p.invested))), rawHi = Math.max(...h.map(p => p.total))
  const pad = (rawHi - rawLo) * 0.08 || rawHi * 0.02 || 1
  const ticks = niceTicks(rawLo - pad, rawHi + pad)
  const lo = Math.min(rawLo - pad, ticks[0]), hi = Math.max(rawHi + pad, ticks[ticks.length - 1])
  const y = (v: number) => T0 + (1 - (v - lo) / (hi - lo)) * MH
  const total = h.map((p, i) => `${i ? 'L' : 'M'}${x(p.d).toFixed(1)},${y(p.total).toFixed(1)}`).join('')
  // Invested is a step line: money arrives on a day, it doesn't ramp.
  const invested = h.map((p, i) => (i ? `H${x(p.d).toFixed(1)}V${y(p.invested).toFixed(1)}` : `M${x(p.d).toFixed(1)},${y(p.invested).toFixed(1)}`)).join('')
  const band = total + [...h].reverse().map(p => `L${x(p.d).toFixed(1)},${y(p.invested).toFixed(1)}`).join('') + 'Z'
  const ddMin = Math.min(-1, ...h.map(p => p.dd))
  const yd = (v: number) => dT + (v / ddMin) * DH
  const ddPath = `M${x(first.d)},${dT}` + h.map(p => `L${x(p.d).toFixed(1)},${yd(p.dd).toFixed(1)}`).join('') + `L${x(last.d)},${dT}Z`
  const adds = h.filter((p, i) => i > 0 && p.invested - h[i - 1].invested > 1)

  // X ticks: weekly days for a short range, months (every other one past ~7 months) otherwise.
  const xt: [Date, string][] = []
  const spanShown = (t1 - t0) / 864e5
  if (spanShown <= 45) {
    for (const d = new Date(t0); +d <= t1; d.setDate(d.getDate() + 7)) xt.push([new Date(d), dayMon(d)])
  } else {
    const every = spanShown > 400 ? 3 : spanShown > 200 ? 2 : 1
    const d = new Date(t0); d.setDate(1); d.setMonth(d.getMonth() + 1)
    for (; +d <= t1; d.setMonth(d.getMonth() + every)) xt.push([new Date(d), d.getMonth() === 0 ? `Jan ’${String(d.getFullYear()).slice(2)}` : MON[d.getMonth()]])
  }
  let lyTotal = y(last.total), lyInv = y(last.invested)
  if (Math.abs(lyTotal - lyInv) < 16) lyInv = lyTotal + (lyInv >= lyTotal ? 16 : -16)

  const pxOf = (e: PointerEvent<SVGRectElement>) => Math.max(L, Math.min(W - R, e.clientX - e.currentTarget.ownerSVGElement!.getBoundingClientRect().left))
  const onMove = (e: PointerEvent<SVGRectElement>) => {
    const px = pxOf(e)
    if (drag) setDrag({ ...drag, b: px })
    let best = 0
    h.forEach((p, i) => { if (Math.abs(x(p.d) - px) < Math.abs(x(h[best].d) - px)) best = i })
    setHover(best)
  }
  // Drag across the chart to zoom into that stretch; a plain click or tap just shows the readout.
  const onDown = (e: PointerEvent<SVGRectElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId)
    setDrag({ a: pxOf(e), b: pxOf(e) })
    onMove(e)
  }
  const onUp = () => {
    if (drag && Math.abs(drag.b - drag.a) > 8) {
      const at = (px: number) => t0 + ((px - L) / (W - L - R || 1)) * (t1 - t0)
      const lo = at(Math.min(drag.a, drag.b)), hi = at(Math.max(drag.a, drag.b))
      if (all.filter(p => +p.d >= lo && +p.d <= hi).length > 1) { setCustom([lo, hi]); setHover(null) }
    }
    setDrag(null)
  }
  const pick = (d: number) => { setDays(d); setCustom(null); setHover(null) }
  const short = (t: number) => dayMon(new Date(t))
  const hp = hover != null ? h[hover] : null
  const prev = hp ? all[all.indexOf(hp) - 1] : undefined
  const pnl = (n: number) => (n >= 0 ? T.positive : T.negative)

  return (
    <Card>
      <CardHead title="Net worth history">
        <div style={chipGroup}>
          {RANGES.map(([l, d]) => (
            <Chip key={l} on={!custom && days === d} disabled={d >= span} onClick={() => pick(d)}
              title={d >= span ? `Only ${Math.max(1, Math.round(span))} days of history so far` : undefined}>{l}</Chip>
          ))}
          <Chip on={!custom && days === 0} onClick={() => pick(0)}>All</Chip>
          {custom && <Chip on onClick={() => setCustom(null)} title="Clear the dragged range">{short(custom[0])} – {short(custom[1])} ×</Chip>}
        </div>
      </CardHead>
      <div style={statGrid}>
        <Stat l="Net worth now" v={fmt(last.total)} s={dayMonYear(last.d)} />
        <Stat l="Change in range" v={signed(change)} color={pnl(change)} s={`${first.total ? pctText((change / first.total) * 100) : ''} since ${dayMonYear(first.d)}`} />
        <Stat l="Where it came from">
          <div style={{ fontSize: 13.5, fontWeight: 700, marginTop: 6, fontVariantNumeric: 'tabular-nums' }}>
            <span style={{ color: T.accent }}>{signed(added)}</span> you · <span style={{ color: pnl(market) }}>{signed(market)}</span> market
          </div>
          <div style={{ marginTop: 7, height: 6, borderRadius: 6, background: T.surface2, display: 'flex', overflow: 'hidden' }}>
            <div style={{ width: `${(Math.abs(added) / splitTotal) * 100}%`, background: T.accent }} />
            <div style={{ width: `${(Math.abs(market) / splitTotal) * 100}%`, background: pnl(market) }} />
          </div>
        </Stat>
        <Stat l="From peak" v={last.dd < -0.05 ? `${last.dd.toFixed(1)}%` : 'At peak'} color={last.dd < -0.05 ? T.negative : T.positive}
          s={`peak ${fmt(peakAll.total)} on ${dayMonYear(peakAll.d)}`} />
      </div>
      <div ref={ref} style={{ position: 'relative' }}>
        {W > 0 && (
          <svg width={W} height={H} style={{ display: 'block', overflow: 'visible' }}>
            <defs>
              <clipPath id="nw-above"><path d={`${invested}V${T0}H${L}Z`} /></clipPath>
              <clipPath id="nw-below"><path d={`${invested}V${T0 + MH}H${L}Z`} /></clipPath>
              <linearGradient id="nw-dd" x1="0" x2="0" y1="0" y2="1">
                <stop offset="0" stopColor={T.negative} stopOpacity="0.15" /><stop offset="1" stopColor={T.negative} stopOpacity="0.45" />
              </linearGradient>
            </defs>
            {ticks.map(t => (
              <g key={t}>
                <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} stroke={T.hairline} />
                <text x={L - 8} y={y(t) + 4} textAnchor="end" fontSize="10.5" fill={T.muted}>{fmt(t)}</text>
              </g>
            ))}
            {xt.map(([d, s]) => (
              <g key={+d}>
                <line x1={x(d)} x2={x(d)} y1={T0 + MH} y2={T0 + MH + 4} stroke={T.muted} />
                <text x={x(d)} y={T0 + MH + 16} textAnchor="middle" fontSize="10.5" fill={T.muted}>{s}</text>
              </g>
            ))}
            <path d={band} fill={T.positive} opacity="0.14" clipPath="url(#nw-above)" />
            <path d={band} fill={T.negative} opacity="0.2" clipPath="url(#nw-below)" />
            <path d={invested} fill="none" stroke={T.muted} strokeWidth="1.4" strokeDasharray="4 4" />
            <path d={total} fill="none" stroke={T.accent2} strokeWidth="2.2" strokeLinejoin="round" />
            {adds.map(p => <path key={p.date} d={`M${x(p.d)},${T0 + MH - 1}l-3.5,6h7z`} fill={T.accent} />)}
            <circle cx={x(peak.d)} cy={y(peak.total)} r="4" fill={T.surface} stroke={T.accent2} strokeWidth="2" />
            <text x={Math.max(L + 30, Math.min(x(peak.d), W - R - 30))} y={y(peak.total) - 9} textAnchor="middle" fontSize="10" fontWeight="600" fill={T.accent2}>Peak {fmt(peak.total)}</text>
            <circle cx={x(last.d)} cy={y(last.total)} r="3.5" fill={T.accent2} />
            <text x={W - R + 8} y={lyTotal + 4} fontSize="11" fontWeight="700" fill={T.accent2}>{fmt(last.total)}</text>
            <text x={W - R + 8} y={lyInv + 4} fontSize="10.5" fill={T.muted}>{fmt(last.invested)}</text>

            <text x={L} y={dT - 8} fontSize="10" fontWeight="600" letterSpacing="0.5" fill={T.muted}>BELOW PEAK</text>
            {worst.dd < -0.5 && (
              <text x={W - R} y={dT - 8} textAnchor="end" fontSize="10" fontWeight="600" fill={T.negative}>worst {worst.dd.toFixed(1)}% · {dayMon(worst.d)}</text>
            )}
            <line x1={L} x2={W - R} y1={dT} y2={dT} stroke={T.hairline} />
            <text x={L - 8} y={dT + 4} textAnchor="end" fontSize="10" fill={T.muted}>0%</text>
            <text x={L - 8} y={dT + DH + 2} textAnchor="end" fontSize="10" fill={T.muted}>{ddMin.toFixed(1)}%</text>
            <path d={ddPath} fill="url(#nw-dd)" />
            {worst.dd < -0.5 && <circle cx={x(worst.d)} cy={yd(worst.dd)} r="3" fill={T.negative} stroke={T.surface} strokeWidth="1.5" />}
            {hp && <>
              <line x1={x(hp.d)} x2={x(hp.d)} y1={T0} y2={dT + DH} stroke={T.muted} strokeDasharray="2 3" />
              <circle cx={x(hp.d)} cy={y(hp.invested)} r="3.5" fill={T.muted} stroke={T.surface} strokeWidth="1.5" />
              <circle cx={x(hp.d)} cy={y(hp.total)} r="4.5" fill={T.accent2} stroke={T.surface} strokeWidth="2" />
            </>}
            <rect x={L} y={0} width={Math.max(0, W - L - R)} height={H} fill="transparent" style={hairCursor}
              onPointerMove={onMove} onPointerDown={onDown} onPointerUp={onUp} onPointerCancel={() => setDrag(null)}
              onPointerLeave={() => { if (!drag) setHover(null) }} />
            {drag && Math.abs(drag.b - drag.a) > 2 && (
              <rect x={Math.min(drag.a, drag.b)} y={T0} width={Math.abs(drag.b - drag.a)} height={dT + DH - T0}
                fill={T.accent} opacity="0.14" stroke={T.accent} strokeOpacity="0.5" pointerEvents="none" />
            )}
          </svg>
        )}
        {hp && (
          <Tip x={x(hp.d)} w={W} top={6}>
            <div style={{ fontWeight: 600, marginBottom: 2 }}>{dayMonYear(hp.d)}</div>
            <TipRow l="Net worth" v={fmt(hp.total)} bold />
            <TipRow l="Invested" v={fmt(hp.invested)} />
            <TipRow l="Gain" v={`${signed(hp.total - hp.invested)}${hp.invested ? ` (${pctText(((hp.total - hp.invested) / hp.invested) * 100)})` : ''}`} color={pnl(hp.total - hp.invested)} />
            {prev && <TipRow l={`Since ${dayMon(prev.d)}`} v={signed(hp.total - prev.total)} color={pnl(hp.total - prev.total)} />}
            <TipRow l="Below peak" v={hp.dd < -0.05 ? `${hp.dd.toFixed(1)}%` : '—'} />
          </Tip>
        )}
      </div>
      <div style={legend}>
        <span><b style={{ color: T.accent2 }}>━</b> net worth</span>
        <span><b>╌</b> invested (your money in)</span>
        <span><b style={{ color: T.positive }}>▇</b> gain over invested</span>
        <span><b style={{ color: T.accent }}>▲</b> money added</span>
        <span><b style={{ color: T.negative }}>▇</b> below peak</span>
        <span>drag across the chart to pick a range</span>
      </div>
    </Card>
  )
}

export default function OutlookTab({ k }: { k: PortfolioKpis | null }) {
  const stacked = useNarrow(1040)
  if (!k) return <div style={{ color: T.muted }}>Loading…</div>
  const f = k.forecast
  const goToPlan = () => {
    const u = new URL(location.href)
    u.searchParams.set('page', 'admin')
    u.searchParams.set('tool', 'portfolio-plan')
    location.href = u.toString()
  }
  return (
    <div style={{ display: 'grid', gridTemplateColumns: stacked ? 'minmax(0, 1fr)' : 'minmax(0, 1fr) 300px', gap: 16, alignItems: 'start' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16, minWidth: 0 }}>
        {f && f.band.length > 1 && <CorpusCard f={f} extraSip={k.extra_sip_needed} />}
        {k.commitments && <CommitmentsCard c={k.commitments} onEdit={goToPlan} />}
        {k.history.length > 1
          ? <NetWorth history={k.history} />
          : (
            <Card>
              {title('Net worth history')}
              <div style={{ color: T.muted, fontSize: 13 }}>A snapshot is saved each day you open the app. The curve, 30-day change and XIRR build from here.</div>
            </Card>
          )}
      </div>

      <aside style={{ display: 'flex', flexDirection: 'column', gap: 14, minWidth: 0 }}>
        {/* Placeholder: the side column is kept (as on the other tabs) for future goal and forecast insights. */}
        <div style={{ border: `1.5px dashed ${T.border}`, borderRadius: 'var(--radius, 10px)', padding: '22px 16px', textAlign: 'center', color: T.muted, fontSize: 12.5, lineHeight: 1.5 }}>
          <div style={{ ...label, marginBottom: 6 }}>Coming soon</div>
          More goal and forecast insights will appear here.
        </div>
        <button onClick={goToPlan} style={{ background: 'none', border: 'none', color: T.accent, cursor: 'pointer', fontSize: 13, textAlign: 'left', padding: 0 }}>Edit goals &amp; targets →</button>
      </aside>
    </div>
  )
}
