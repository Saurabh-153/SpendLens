import { useMemo, type ReactNode } from 'react'
import type { ExposureData, Holding, PortfolioKpis } from '../api'
import { MIX, colorOf } from '../exposure'
import { T, fmt, pnlColor, signed } from '../theme'
import { card, label } from './ui'
import KpiSection, { LineItem } from './KpiSection'

const num = { fontVariantNumeric: 'tabular-nums' } as const

export function Tile({ name, value, children }: { name: string; value: ReactNode; children?: ReactNode }) {
  return (
    <div style={{ ...card, padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0 }}>
      <div style={label}>{name}</div>
      <div style={{ fontFamily: 'var(--font-display, inherit)', fontSize: 26, fontWeight: 700, letterSpacing: -0.3, lineHeight: 1.15, ...num }}>{value}</div>
      {children}
    </div>
  )
}

const sub = { fontSize: 12, color: T.muted } as const
const SIP_ROWS = [['Equity', 'Equity'], ['Debt', 'Fixed income'], ['Gold', 'Gold']] as const

function Meter({ pct, color, title }: { pct: number; color: string; title: string }) {
  return (
    <div title={title} style={{ height: 6, borderRadius: 3, background: T.surface2, marginTop: 6, overflow: 'hidden' }}>
      <div style={{ width: `${Math.max(0, Math.min(100, pct))}%`, height: '100%', background: color, borderRadius: 3 }} />
    </div>
  )
}

function Spark({ points }: { points: number[] }) {
  if (points.length < 2) return null
  const W = 200, H = 36
  const lo = Math.min(...points), hi = Math.max(...points)
  const x = (i: number) => (i / (points.length - 1)) * (W - 6) + 3
  const y = (v: number) => 5 + (1 - (v - lo) / (hi - lo || 1)) * (H - 10)
  const d = points.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p).toFixed(1)}`).join('')
  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label="Net worth, last 30 days" style={{ display: 'block', width: '100%', height: 36, marginTop: 4 }}>
      <path d={`${d}L${x(points.length - 1)},${H}L${x(0)},${H}Z`} fill={T.accent} opacity="0.12" />
      <path d={d} fill="none" stroke={T.accent} strokeWidth="2" vectorEffect="non-scaling-stroke" />
      <circle cx={x(points.length - 1)} cy={y(points[points.length - 1])} r="3" fill={T.accent} />
    </svg>
  )
}

/** The next SIP date among all holdings that have a SIP day, as '5 Nov'. */
function nextSip(holdings: Holding[]): string | null {
  const days = [...new Set(holdings.filter(h => h.sip_amount > 0 && h.sip_day > 0).map(h => h.sip_day))].sort((a, b) => a - b)
  if (!days.length) return null
  const now = new Date()
  let at = new Date(now.getFullYear(), now.getMonth(), days.find(d => d > now.getDate()) ?? days[0])
  if (at.getDate() <= now.getDate() && at.getMonth() === now.getMonth()) at = new Date(now.getFullYear(), now.getMonth() + 1, days[0])
  return at.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
}

/** The four KPI tiles and the allocation bar above the Holdings table. The tiles draw at once from the holdings; the
 *  portfolio KPIs (trend, XIRR, income, emergency cover) and the allocation targets fill in when they arrive. */
export default function HoldingsKpis({ holdings, totals, k, ex }: { k: PortfolioKpis | null; ex: ExposureData | null; holdings: Holding[]; totals: { invested: number; present: number; sip: number; pnl: number; pct: number } }) {
  const up = useMemo(() => holdings.filter(h => h.pl > 0).length, [holdings])
  const down = useMemo(() => holdings.filter(h => h.pl < 0).length, [holdings])
  const trend = useMemo(() => (k?.history ?? []).slice(-30).map(p => p.total), [k])
  const next = useMemo(() => nextSip(holdings), [holdings])

  const r = k?.returns
  const xirr = k ? (k.ledger.covered_pct >= 50 && k.ledger.xirr != null ? k.ledger.xirr : k.returns.xirr) : null
  const cover = k?.safety.cover_months ?? null
  const coverColor = cover == null ? T.muted : cover >= 6 ? T.positive : cover >= 3 ? T.warn : T.negative
  // the four tiles of the second row need the portfolio KPIs and the target split
  const spend = k?.safety.monthly_spend ?? 0
  const fiTarget = spend * 12 * 25
  const fiPct = fiTarget > 0 ? (totals.present / fiTarget) * 100 : null
  const goals = k?.forecast?.goals ?? []
  const onTrack = goals.filter(g => g.probability >= 70).length
  const weakest = goals.length ? goals.reduce((a, b) => (b.probability < a.probability ? b : a)) : null
  const rebal = (ex?.exposures ?? []).filter(e => e.target != null)
  const move = rebal.reduce((sum, e) => sum + Math.max(0, e.add ?? 0), 0)
  const worst = rebal.length ? rebal.reduce((a, b) => (Math.abs(b.drift ?? 0) > Math.abs(a.drift ?? 0) ? b : a)) : null
  const coverNote = cover == null ? '' : cover >= 6 ? 'Comfortable' : cover >= 3 ? 'Build it up' : 'Low'
  const split = k?.sip.by_mix

  const pctText = (n: number) => `${n >= 0 ? '+' : '−'}${Math.abs(n).toFixed(1)}%`
  const line = (
    <>
      <LineItem label="Net worth">{fmt(totals.present)}</LineItem>
      {r?.change != null && <LineItem label="30 days" color={pnlColor(r.change)}>{signed(r.change)}</LineItem>}
      <LineItem label="Gain" color={pnlColor(totals.pnl)}>{signed(totals.pnl)} ({pctText(totals.pct)})</LineItem>
      {xirr != null && <LineItem label="XIRR">{xirr.toFixed(1)}%</LineItem>}
      <LineItem label="SIP">{fmt(totals.sip)}/mo{split && <> (equity {fmt(split.Equity)})</>}</LineItem>
      {cover != null && <LineItem label="Safety net" color={coverColor}>{cover.toFixed(1)} months</LineItem>}
      {fiPct != null && <LineItem label="Independence">{fiPct.toFixed(0)}%</LineItem>}
      {worst && <LineItem label="Rebalance" color={move > 0 ? T.warn : T.positive}>{move > 0 ? fmt(move) : 'none'}</LineItem>}
      {goals.length > 0 && <LineItem label="Goals on track">{onTrack} of {goals.length}</LineItem>}
    </>
  )
  return (
    <KpiSection storageKey="spendlens.holdingKpisCompact" label="Portfolio" line={line}>
      <section aria-label="Portfolio KPIs" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: 12 }}>
        <Tile name="Net worth" value={fmt(totals.present)}>
          <div style={sub}>
            Invested <b style={{ color: T.text, ...num }}>{fmt(totals.invested)}</b>
            {r?.change != null && <> · <span style={{ color: pnlColor(r.change), ...num }}>{signed(r.change)} ({r.change_pct}%) in 30 days</span></>}
          </div>
          <Spark points={trend} />
        </Tile>

        <Tile name="Total gain"
          value={<span style={{ color: pnlColor(totals.pnl) }}>{signed(totals.pnl)} <span style={{ fontSize: 14, fontWeight: 600 }}>{signed(totals.pct, x => `${x.toFixed(1)}%`)}</span></span>}>
          {xirr != null && <div style={sub}>Annual return (XIRR) <b style={{ color: T.text, ...num }}>{xirr.toFixed(1)}%</b></div>}
          <div style={sub}>{holdings.length} holdings · <span style={{ color: T.positive }}>{up} up</span> · <span style={{ color: T.negative }}>{down} down</span></div>
          <Meter pct={holdings.length ? (up / holdings.length) * 100 : 0} color={T.positive} title="Share of holdings in profit" />
        </Tile>

        <Tile name="Monthly SIP" value={<>{fmt(totals.sip)}<small style={{ fontSize: 14, color: T.muted, fontWeight: 600 }}> /mo</small></>}>
          {split && SIP_ROWS.map(([key, name]) => (
            <div key={key} title={key === 'Debt' ? 'PF, FD, debt and liquid funds, emergency fund and cash' : undefined} style={{ ...sub, display: 'flex', justifyContent: 'space-between', gap: 8 }}>
              <span>{name}</span><b style={{ color: T.text, ...num }}>{fmt(split[key])}</b>
            </div>
          ))}
          <div style={sub}>{next ? <>Next SIP <b style={{ color: T.text }}>{next}</b> · </> : null}{holdings.filter(h => h.sip_amount > 0).length} running</div>
        </Tile>

        <Tile name="Safety net"
          value={cover == null ? '–' : <span style={{ color: coverColor }}>{cover.toFixed(1)}<small style={{ fontSize: 14, color: T.muted, fontWeight: 600 }}> months</small></span>}>
          {k && <div style={sub}>{fmt(k.safety.emergency)} emergency fund{k.safety.monthly_spend > 0 && <> · you spend <b style={{ color: T.text, ...num }}>{fmt(k.safety.monthly_spend)}</b>/mo</>}</div>}
          {cover != null && <div style={sub}><b style={{ color: coverColor }}>{coverNote}</b> · aim for 6 months</div>}
          {cover != null && <Meter pct={(cover / 6) * 100} color={coverColor} title="Months covered, out of 6" />}
        </Tile>

        {k && (
          <Tile name={`Income ${k.ledger.fy}`} value={fmt(k.ledger.dividends + k.ledger.realized)}>
            <div style={sub}>Dividends <b style={{ color: T.text, ...num }}>{fmt(k.ledger.dividends)}</b> · realised gains <b style={{ color: T.text, ...num }}>{fmt(k.ledger.realized)}</b></div>
            <div style={sub}>This financial year so far</div>
          </Tile>
        )}
        {fiPct != null && (
          <Tile name="Financial independence" value={<>{fiPct.toFixed(0)}<small style={{ fontSize: 14, color: T.muted, fontWeight: 600 }}>% there</small></>}>
            <div style={sub}>Net worth ÷ 25 × your yearly spend of {fmt(spend * 12)}</div>
            <div style={sub}>Target <b style={{ color: T.text, ...num }}>{fmt(fiTarget)}</b></div>
            <Meter pct={fiPct} color={T.accent} title="Progress to 25 times yearly spending" />
          </Tile>
        )}
        {worst && (
          <Tile name="Rebalance needed" value={move > 0 ? fmt(move) : 'None'}>
            <div style={sub}>{move > 0 ? 'To move to reach your target mix' : 'You are on your target mix'}</div>
            {Math.abs(worst.drift ?? 0) >= 2 && <div style={sub}>{worst.name} is {Math.abs(worst.drift ?? 0).toFixed(1)} points {(worst.drift ?? 0) > 0 ? 'over' : 'under'} target</div>}
          </Tile>
        )}
        {goals.length > 0 && weakest && (
          <Tile name="Goals on track" value={`${onTrack} of ${goals.length}`}>
            <div style={sub}>At least a 70% chance of being funded</div>
            <div style={sub}>Weakest: <b style={{ color: T.text }}>{weakest.name}</b> {weakest.probability}%</div>
          </Tile>
        )}
      </section>
    </KpiSection>
  )
}

/** The allocation bar with target marks, shown on the Portfolio tab. */
export function Allocation({ ex }: { ex: ExposureData }) {
  const rows = MIX.map(name => ex.exposures.find(e => e.name === name)).filter((e): e is NonNullable<typeof e> => !!e)
  let acc = 0
  const ticks = rows.slice(0, -1).map(e => { acc += e.target ?? 0; return acc })
  const hasTargets = rows.some(e => e.target != null)
  return (
    <section aria-label="Allocation" style={{ ...card, padding: '14px 16px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap', alignItems: 'baseline' }}>
        <h2 style={{ fontSize: 15 }}>Allocation against your plan</h2>
        <span style={{ fontSize: 12, color: T.muted }}>{hasTargets ? 'Marks show your target split. ' : ''}Cash counts as Debt.</span>
      </div>
      <div role="img" aria-label="Allocation" style={{ position: 'relative', display: 'flex', height: 18, margin: '22px 0 8px', borderRadius: 6 }}>
        {rows.map((e, i) => (
          <span key={e.name} title={`${e.name} ${e.pct.toFixed(1)}%`} style={{
            width: `${e.pct}%`, background: colorOf(e.name),
            borderRadius: i === 0 ? '6px 0 0 6px' : i === rows.length - 1 ? '0 6px 6px 0' : 0,
          }} />
        ))}
        {hasTargets && ticks.map(t => (
          <span key={t} style={{ position: 'absolute', top: -7, bottom: -7, left: `${t}%`, width: 2, background: T.text, opacity: 0.7 }}>
            <em style={{ position: 'absolute', top: -14, left: '50%', transform: 'translateX(-50%)', fontSize: 10, fontStyle: 'normal', color: T.muted, whiteSpace: 'nowrap' }}>{Math.round(t)}%</em>
          </span>
        ))}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: '8px 16px', marginTop: 10, fontSize: 12.5 }}>
        {rows.map(e => {
          const off = e.drift ?? 0, on = e.target == null || Math.abs(off) < 2
          return (
            <div key={e.name} style={{ display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap', minWidth: 0 }}>
              <i style={{ width: 10, height: 10, borderRadius: 3, background: colorOf(e.name), flexShrink: 0, alignSelf: 'center' }} />
              <b>{e.name}</b><span style={num}>{e.pct.toFixed(1)}%</span>
              {e.target != null && (
                <span style={{ color: T.muted, fontSize: 11.5 }}>
                  target {e.target}% · {on ? <span style={{ color: T.positive }}>on target</span>
                    : <span style={{ color: T.warn }}>{off > 0 ? 'over by ' : 'short by '}{fmt(Math.abs(e.add ?? (off / 100) * ex.total))}</span>}
                </span>
              )}
            </div>
          )
        })}
      </div>
    </section>
  )
}
