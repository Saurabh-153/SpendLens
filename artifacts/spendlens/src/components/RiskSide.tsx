import { useState, type ReactNode } from 'react'
import type { PortfolioKpis } from '../api'
import { colorOf } from '../exposure'
import { T, fmt } from '../theme'
import { Card, label } from './ui'
import { MON, spread, useWidth } from './chartKit'

// What counts as a risk. Emergency-fund cover, rebalancing, goals and the sector bars are left out on purpose: the
// Portfolio KPI strip, the Rebalance card and Themes and sectors on the same tab already show them.
const LIMITS = { position: [10, 15], top5: [60, 75], sector: [25, 35], locked: [40, 55] } as const
type Status = 'ok' | 'watch' | 'act' | 'info'
const grade = (v: number, [ok, watch]: readonly [number, number]): Status => (v <= ok ? 'ok' : v <= watch ? 'watch' : 'act')
const STATUS: Record<Status, { color: string; text: string }> = {
  ok: { color: T.positive, text: 'OK' }, watch: { color: T.warn, text: 'Watch' }, act: { color: T.negative, text: 'Act' }, info: { color: T.accent, text: 'Plan' },
}
const SPEED = [
  { key: 'instant', name: 'Instant', hint: 'cash', color: '#22c55e' },
  { key: 'days', name: 'Within days', hint: 'shares, funds, gold', color: '#38bdf8' },
  { key: 'fixed', name: 'Deposits', hint: 'breakable, with a penalty', color: '#f59e0b' },
  { key: 'locked', name: 'Locked', hint: 'provident funds', color: '#94a3b8' },
] as const
const pct1 = (n: number) => `${n.toFixed(1)}%`
const dmy = (s: string) => { const [y, m, d] = s.split('-').map(Number); return `${d} ${MON[m - 1]} ${y}` }
const linkBtn = { background: 'none', border: 'none', color: T.accent, cursor: 'pointer', fontSize: 12, padding: 0, justifySelf: 'start' as const, textAlign: 'left' as const }

const head = (t: string, right?: ReactNode) => (
  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'baseline', marginBottom: 12, flexWrap: 'wrap' }}>
    <span style={{ ...label, fontSize: 12.5, letterSpacing: 0.8 }}>{t}</span>
    {right && <span style={{ fontSize: 11, color: T.muted }}>{right}</span>}
  </div>
)
const subHead = (t: string, right?: ReactNode) => (
  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'baseline', margin: '0 0 8px' }}>
    <span style={{ ...label, color: T.text }}>{t}</span>{right && <span style={{ fontSize: 10.5, color: T.muted }}>{right}</span>}
  </div>
)

/** One check as a compact row; the fix line only shows when the check needs attention. */
function Check({ s, name, value, detail, fix }: { s: Status; name: string; value: string; detail?: string; fix: string }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'auto minmax(0, 1fr) auto', gap: '2px 9px', alignItems: 'baseline', padding: '8px 0', borderTop: `1px solid ${T.hairline}` }}>
      <span title={STATUS[s].text} style={{ width: 8, height: 8, borderRadius: '50%', background: STATUS[s].color, alignSelf: 'center' }} />
      <span style={{ fontSize: 13 }}>{name}</span>
      <span style={{ fontSize: 13.5, fontWeight: 700, fontVariantNumeric: 'tabular-nums', color: s === 'ok' ? T.text : STATUS[s].color }}>{value}</span>
      {detail && <span style={{ gridColumn: '2 / 4', fontSize: 11.5, color: T.muted, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={detail}>{detail}</span>}
      {s !== 'ok' && <span style={{ gridColumn: '2 / 4', fontSize: 11.5, color: STATUS[s].color, lineHeight: 1.4 }}>{fix}</span>}
    </div>
  )
}

/** Ranked bars with a limit marker; anything past the limit turns amber. */
function Ranked({ rows, limit }: { rows: { name: string; pct: number; value: number; color?: string }[]; limit: number }) {
  const max = Math.max(limit * 1.25, ...rows.map(r => r.pct))
  return (
    <div style={{ display: 'grid', gap: 7 }}>
      {rows.map(r => (
        <div key={r.name} title={`${r.name}: ${fmt(r.value)} (${pct1(r.pct)})`}
          style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 42%) 1fr 42px', gap: 8, alignItems: 'center', fontSize: 12 }}>
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.name}</span>
          <span style={{ position: 'relative', height: 7, borderRadius: 4, background: T.surface2 }}>
            <span style={{ position: 'absolute', inset: '0 auto 0 0', width: `${(r.pct / max) * 100}%`, borderRadius: 4, background: r.pct > limit ? T.warn : (r.color ?? T.accent) }} />
            <span style={{ position: 'absolute', top: -3, bottom: -3, left: `${(limit / max) * 100}%`, width: 0, borderLeft: `1.5px dashed ${T.muted}` }} />
          </span>
          <span style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums', fontWeight: r.pct > limit ? 700 : 400, color: r.pct > limit ? T.warn : T.text }}>{pct1(r.pct)}</span>
        </div>
      ))}
    </div>
  )
}

/** Deposit maturities over the next five years on one time axis. Amount labels are spread apart; when there are too
 *  many to fit they are left off (the list underneath has every one). */
function Ladder({ rows }: { rows: PortfolioKpis['fixed']['ladder'] }) {
  const [ref, W] = useWidth()
  const now = new Date(), t0 = +now, t1 = +new Date(now.getFullYear() + 5, now.getMonth(), now.getDate())
  const L = 6, R = 6, axisY = 28, LABEL_W = 52
  const x = (s: string) => { const [y, m, d] = s.split('-').map(Number); return L + ((+new Date(y, m - 1, d) - t0) / (t1 - t0)) * (W - L - R) }
  const maxV = Math.max(...rows.map(r => r.value), 1)
  const xs = rows.map(r => x(r.date))
  const labels = rows.length * LABEL_W <= W - L - R
  const lx = spread(xs, LABEL_W, L + LABEL_W / 2, W - R - LABEL_W / 2)
  return (
    <div ref={ref}>
      {W > 0 && (
        <svg width={W} height={labels ? 56 : 44} style={{ display: 'block', overflow: 'visible' }}>
          <g transform={labels ? undefined : 'translate(0,-12)'}>
            <line x1={L} x2={W - R} y1={axisY} y2={axisY} stroke={T.hairline} strokeWidth="2" />
            {[0, 1, 2, 3, 4, 5].map(i => {
              const xx = L + (i / 5) * (W - L - R)
              return <g key={i}><line x1={xx} x2={xx} y1={axisY - 3} y2={axisY + 3} stroke={T.muted} />
                {i % (W < 260 ? 2 : 1) === 0 || i === 5
                  ? <text x={xx} y={axisY + 15} textAnchor={i === 0 ? 'start' : i === 5 ? 'end' : 'middle'} fontSize="9.5" fill={T.muted}>{i === 0 ? 'Now' : `’${String(now.getFullYear() + i).slice(2)}`}</text>
                  : null}</g>
            })}
            {rows.map((r, i) => (
              <g key={`${r.name}${r.date}`}>
                <title>{r.name} · {dmy(r.date)} · {fmt(r.value)}{r.rate ? ` · ${r.rate}%` : ''}</title>
                {labels && <line x1={xs[i]} x2={lx[i]} y1={axisY - 4} y2={12} stroke={T.warn} opacity="0.5" />}
                <circle cx={xs[i]} cy={axisY} r={3 + Math.sqrt(r.value / maxV) * 4} fill={T.warn} opacity="0.85" />
                {labels && <text x={lx[i]} y={9} textAnchor="middle" fontSize="9.5" fontWeight="600" fill={T.text}>{fmt(r.value)}</text>}
              </g>
            ))}
          </g>
        </svg>
      )}
    </div>
  )
}

/** Risk & safety for the side column: the checks, then concentration, then how reachable the money is. */
export default function RiskSide({ k }: { k: PortfolioKpis }) {
  const [allPos, setAllPos] = useState(false)
  const [allMat, setAllMat] = useState(false)
  const c = k.concentration, liq = k.liquidity, total = Object.values(liq).reduce((s, v) => s + v, 0) || 1
  const lockedPct = (liq.locked / total) * 100
  const topSector = c.sectors[0]
  const checks: { s: Status; name: string; value: string; detail?: string; fix: string }[] = []
  if (c.top) checks.push({ s: grade(c.top.pct, LIMITS.position), name: 'Largest position', value: pct1(c.top.pct), detail: c.top.name,
    fix: c.over_10.length > 1 ? `${c.over_10.length} holdings are over 10%. Keep any one under 10%.` : 'Keep any one holding under 10%.' })
  checks.push({ s: grade(c.top5_pct, LIMITS.top5), name: 'Top 5 holdings', value: pct1(c.top5_pct), fix: 'Spread money wider: under 60% keeps one bad year from hurting everything.' })
  if (topSector) checks.push({ s: grade(topSector.pct, LIMITS.sector), name: 'Largest sector', value: pct1(topSector.pct), detail: `${topSector.sector} · share of equity`,
    fix: 'Keep a single sector under 25% of your shares.' })
  checks.push({ s: grade(lockedPct, LIMITS.locked), name: 'Locked away', value: pct1(lockedPct), detail: `${fmt(liq.locked)} in provident funds`,
    fix: 'Fine for retirement, but goal money should stay reachable.' })
  if (k.fixed.maturing.length) {
    const v = k.fixed.maturing.reduce((s, m) => s + m.value, 0)
    checks.push({ s: 'info', name: 'Maturing in a year', value: fmt(v), detail: `${k.fixed.maturing.length} deposit${k.fixed.maturing.length > 1 ? 's' : ''} · first ${dmy(k.fixed.maturing[0].date)}`,
      fix: 'Decide where it goes next so it does not sit idle.' })
  }
  const count = (s: Status) => checks.filter(x => x.s === s).length
  const positions = allPos ? c.ranked : c.ranked.slice(0, 5)
  const ladder = k.fixed.ladder
  const matRows = allMat ? ladder : ladder.slice(0, 3)
  const assetColor = (t: string) => colorOf(t === 'GOLD' ? 'Gold' : t === 'FD' || t === 'PF' || t === 'CASH' ? 'Debt' : 'Equity')

  return <>
    <Card>
      {head('Risk & safety', (
        <span style={{ display: 'inline-flex', gap: 8, fontWeight: 600 }}>
          {(['ok', 'watch', 'act'] as const).map(s => <span key={s} style={{ color: count(s) ? STATUS[s].color : T.muted }}>{count(s)} {STATUS[s].text}</span>)}
        </span>
      ))}
      <div style={{ marginTop: -8 }}>{checks.map(x => <Check key={x.name} {...x} />)}</div>
    </Card>

    <Card>
      {head('Concentration', 'sectors: see Themes and sectors')}
      {subHead('Biggest positions', `┆ 10% · ${c.over_10.length} over`)}
      <Ranked rows={positions.map(r => ({ ...r, color: assetColor(r.type) }))} limit={LIMITS.position[0]} />
      {c.ranked.length > 5 && <button style={{ ...linkBtn, marginTop: 6 }} onClick={() => setAllPos(v => !v)}>{allPos ? 'Show top 5' : `Show top ${c.ranked.length}`}</button>}
    </Card>

    <Card>
      {head('Reach & maturities')}
      {subHead('How fast you can get your money')}
      <div role="img" aria-label="Value by how fast it can be reached" style={{ display: 'flex', height: 12, borderRadius: 6, overflow: 'hidden', background: T.surface2 }}>
        {SPEED.map(sp => liq[sp.key] > 0 && <span key={sp.key} title={`${sp.name}: ${fmt(liq[sp.key])}`} style={{ width: `${(liq[sp.key] / total) * 100}%`, background: sp.color }} />)}
      </div>
      <div style={{ display: 'grid', gap: 5, marginTop: 9 }}>
        {SPEED.map(sp => (
          <div key={sp.key} title={sp.hint} style={{ display: 'grid', gridTemplateColumns: 'auto minmax(0, 1fr) auto', gap: 8, alignItems: 'center', fontSize: 12 }}>
            <span style={{ width: 8, height: 8, borderRadius: 2, background: sp.color }} />
            <span>{sp.name} <span style={{ color: T.muted, fontSize: 11 }}>· {sp.hint}</span></span>
            <span style={{ fontVariantNumeric: 'tabular-nums' }}>{fmt(liq[sp.key])} <span style={{ color: T.muted }}>{Math.round((liq[sp.key] / total) * 100)}%</span></span>
          </div>
        ))}
      </div>
      <div style={{ height: 16 }} />
      {subHead('Maturities · next 5 years', k.fixed.avg_rate != null ? `earning ${k.fixed.avg_rate}%` : undefined)}
      {ladder.length ? <>
        <Ladder rows={ladder} />
        <div style={{ display: 'grid', gap: 5, marginTop: 4 }}>
          {matRows.map(m => (
            <div key={`${m.name}${m.date}`} style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) auto', gap: 8, fontSize: 12 }}>
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={m.name}>{m.name}<br /><span style={{ color: T.muted, fontSize: 11 }}>{dmy(m.date)}{m.rate ? ` · ${m.rate}%` : ''}</span></span>
              <span style={{ fontVariantNumeric: 'tabular-nums', fontWeight: 600 }}>{fmt(m.value)}</span>
            </div>
          ))}
          {ladder.length > 3 && <button style={linkBtn} onClick={() => setAllMat(v => !v)}>{allMat ? 'Show fewer' : `Show all ${ladder.length}`}</button>}
        </div>
      </> : <div style={{ fontSize: 12, color: T.muted }}>No deposits maturing in the next five years.</div>}
    </Card>
  </>
}
