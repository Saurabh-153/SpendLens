import { useEffect, useState } from 'react'
import { getPortfolioKpis, type BandPoint, type PerfRow, type PortfolioKpis } from '../api'
import { T, fmt, pnlColor, signed } from '../theme'
import { Card, accentStyle, label } from './ui'
import { CardChip } from '../cardColors'
import { useGroupColor } from '../groupColors'

const title = (t: string, right?: string) => (
  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
    <span style={{ ...label, fontSize: 12.5, letterSpacing: 0.8 }}>{t}</span>
    {right && <span style={{ ...label, fontSize: 10.5 }}>{right}</span>}
  </div>
)

function Kpi({ name, value, sub, color, accent }: { name: string; value: React.ReactNode; sub: React.ReactNode; color?: string; accent?: string }) {
  return (
    <Card style={{ padding: '14px 18px', ...accentStyle(accent ?? color ?? T.accent) }}>
      <div style={label}>{name}</div>
      <div style={{ fontFamily: 'var(--font-display, inherit)', fontSize: 26, fontWeight: 700, margin: '4px 0 2px', color }}>{value}</div>
      <div style={{ fontSize: 12, color: T.muted }}>{sub}</div>
    </Card>
  )
}

const bar = (pct: number, color: string, h = 6) => (
  <div style={{ height: h, borderRadius: h, background: T.surface2, overflow: 'hidden' }}>
    <div style={{ width: `${Math.max(0, Math.min(100, pct))}%`, height: '100%', background: color, borderRadius: h }} />
  </div>
)

const probColor = (p: number) => (p >= 80 ? T.positive : p >= 50 ? T.warn : T.negative)

function Fan({ band, cons, goals }: { band: BandPoint[]; cons: BandPoint[]; goals: { year: number; target_amount: number; name: string }[] }) {
  const W = 640, H = 220, L = 52, B = 26
  const max = Math.max(...band.map(b => b.p50)) * 1.3
  const x = (i: number) => L + (i / (band.length - 1)) * (W - L - 8)
  const y = (v: number) => 8 + (1 - Math.min(v, max) / max) * (H - B - 8)
  const line = (k: 'p10' | 'p50' | 'p90', b = band) => b.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p[k]).toFixed(1)}`).join('')
  const back = band.map((_, i) => { const j = band.length - 1 - i; return `L${x(j).toFixed(1)},${y(band[j].p10).toFixed(1)}` }).join('')
  const ticks = [0, 0.5, 1].map(f => f * max)
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: 'block' }}>
      {ticks.map(t => (
        <g key={t}>
          <line x1={L} x2={W - 8} y1={y(t)} y2={y(t)} stroke={T.hairline} />
          <text x={L - 6} y={y(t) + 4} textAnchor="end" fontSize="10" fill={T.muted}>{fmt(t)}</text>
        </g>
      ))}
      <path d={`${line('p90')}${back}Z`} fill={T.accent} opacity="0.16" />
      <path d={line('p50', cons)} fill="none" stroke={T.warn} strokeWidth="1.5" strokeDasharray="4 4" />
      <path d={line('p50')} fill="none" stroke={T.accent} strokeWidth="2.2" />
      {band.map((p, i) => (i % 4 === 0 ? <text key={p.year} x={x(i)} y={H - 8} textAnchor="middle" fontSize="10" fill={T.muted}>{p.year}</text> : null))}
      {goals.map(g => {
        const i = band.findIndex(b => b.year === g.year)
        if (i < 0) return null
        return (
          <g key={g.name}>
            <line x1={x(i)} x2={x(i)} y1={8} y2={H - B} stroke={T.negative} strokeDasharray="2 3" opacity="0.6" />
            <circle cx={x(i)} cy={y(g.target_amount)} r="3.5" fill={T.negative} />
          </g>
        )
      })}
    </svg>
  )
}

function PerfList({ rows, empty }: { rows: PerfRow[]; empty: string }) {
  if (!rows.length) return <div style={{ color: T.muted, fontSize: 13 }}>{empty}</div>
  return (
    <div style={{ display: 'grid', gap: 10 }}>
      {rows.map(r => (
        <div key={r.name} style={{ display: 'flex', justifyContent: 'space-between', gap: 10, fontSize: 13 }}>
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.name}</span>
          <span style={{ color: pnlColor(r.pl), fontWeight: 600, whiteSpace: 'nowrap' }}>
            {signed(r.pl_pct, x => `${x.toFixed(1)}%`)} <span style={{ color: T.muted, fontWeight: 400 }}>· {signed(r.pl)}</span>
          </span>
        </div>
      ))}
    </div>
  )
}

function Row({ l, v, warn }: { l: string; v: string; warn?: boolean }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
      <span style={{ color: T.muted }}>{l}</span>
      <span style={{ fontWeight: 600, textAlign: 'right', color: warn ? T.warn : T.text }}>{v}</span>
    </div>
  )
}

function Trend({ h }: { h: PortfolioKpis['history'] }) {
  const W = 900, H = 140
  const lo = Math.min(...h.map(p => Math.min(p.total, p.invested))) * 0.98
  const hi = Math.max(...h.map(p => p.total)) * 1.02
  const x = (i: number) => (i / (h.length - 1)) * W
  const y = (v: number) => 8 + (1 - (v - lo) / (hi - lo || 1)) * (H - 16)
  const path = (k: 'total' | 'invested') => h.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p[k]).toFixed(1)}`).join('')
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" preserveAspectRatio="none" style={{ display: 'block', height: 140 }}>
      <path d={path('invested')} fill="none" stroke={T.muted} strokeDasharray="4 4" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
      <path d={path('total')} fill="none" stroke={T.accent2} strokeWidth="2.2" vectorEffect="non-scaling-stroke" />
    </svg>
  )
}

export default function PortfolioDashboard() {
  const [k, setK] = useState<PortfolioKpis | null>(null)
  const [error, setError] = useState('')
  useEffect(() => { getPortfolioKpis().then(setK).catch(e => setError(e.message)) }, [])
  const groupColor = useGroupColor(k ? k.drift.map(d => d.group) : [])
  if (!k) return <div style={{ color: error ? T.negative : T.muted }}>{error || 'Loading…'}</div>

  const r = k.returns
  const x = k.ledger.covered_pct >= 50 && k.ledger.xirr != null ? k.ledger.xirr : r.xirr
  const cover = k.safety.cover_months, f = k.forecast
  const coverColor = cover == null ? T.muted : cover >= 6 ? T.positive : cover >= 3 ? T.warn : T.negative
  const grid = (min: number): React.CSSProperties => ({ display: 'grid', gridTemplateColumns: `repeat(auto-fit, minmax(${min}px, 1fr))`, gap: 18, alignItems: 'start', marginBottom: 18 })
  const goToPlan = () => {
    const u = new URL(location.href)
    u.searchParams.set('page', 'admin')
    u.searchParams.set('tool', 'portfolio-plan')
    location.href = u.toString()
  }

  return (
    <>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 18 }}>
        <h2 style={{ fontSize: 20, fontWeight: 700 }}>Wealth</h2>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, fontSize: 12.5 }}>
          <span style={{ color: T.muted }}>
            {k.prices.auto_count > 0 ? `${k.prices.auto_count} holdings priced daily${k.prices.last_ok ? ` · updated ${new Date(k.prices.last_ok).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}` : ''}` : 'Daily prices are off'}
          </span>
          <button onClick={goToPlan} style={{ background: 'none', border: 'none', color: T.accent, cursor: 'pointer', fontSize: 13 }}>Edit goals &amp; targets →</button>
        </div>
      </div>

      <div style={grid(200)}>
        <Kpi accent={T.accent} name="Net worth" value={fmt(k.total)}
          sub={r.change != null ? <span style={{ color: pnlColor(r.change) }}>{signed(r.change)} ({r.change_pct}%) in 30 days</span> : `tracking since ${r.since}`} />
        <Kpi name="Gain" value={signed(k.pl)} color={pnlColor(k.pl)} sub={`${k.pl_pct}% on ${fmt(k.invested)} invested`} />
        <Kpi accent="#38bdf8" name="XIRR" value={x != null ? `${x}%` : '—'} color={x != null ? pnlColor(x) : T.muted}
          sub={k.ledger.covered_pct >= 50 && k.ledger.xirr != null ? `from dated flows · ${k.ledger.covered_pct}% covered`
            : r.xirr != null ? `from daily snapshots · ${Math.round(r.span_days / 30)} months`
            : `add opening dates in Ledger (${k.ledger.covered_pct}% covered)`} />
        <Kpi accent="#2dd4bf" name={`Income ${k.ledger.fy}`} value={fmt(k.ledger.dividends)} color={T.positive}
          sub={k.ledger.realized ? `dividends · realised ${signed(k.ledger.realized)}` : 'dividends received'} />
        <Kpi accent={T.warn} name="Investing" value={`${fmt(k.sip.monthly)}/mo`}
          sub={`${k.sip.pct_of_portfolio}% of portfolio a year${k.sip.savings_rate != null ? ` · ${k.sip.savings_rate}% of income` : ''}`} />
        <Kpi name="Emergency cover" value={cover != null ? `${cover} mo` : '—'} color={coverColor}
          sub={`${fmt(k.safety.emergency)} vs ${fmt(k.safety.monthly_spend)}/mo spend`} />
      </div>

      {f && (
        <div style={grid(420)}>
          <Card>
            {title('Goals: chance of being fully funded', `${f.paths} simulations`)}
            <div style={{ display: 'grid', gap: 14 }}>
              {f.goals.map(g => (
                <div key={g.id}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 5 }}>
                    <span><b style={{ fontWeight: 600 }}>{g.name}</b> <span style={{ color: T.muted }}>· {g.target_year} · {fmt(g.target_amount)}</span></span>
                    <span style={{ fontWeight: 700, color: probColor(g.probability) }}>{g.probability}%</span>
                  </div>
                  {bar(g.probability, probColor(g.probability))}
                  <div style={{ fontSize: 11, color: T.muted, marginTop: 3 }}>
                    with returns 3 points lower and flat SIPs: <span style={{ color: probColor(g.conservative) }}>{g.conservative}%</span>
                  </div>
                </div>
              ))}
            </div>
            <div style={{ fontSize: 12, color: T.muted, marginTop: 14, lineHeight: 1.5 }}>
              {k.extra_sip_needed > 0
                ? `Adding about ${fmt(k.extra_sip_needed)} a month would lift every goal to 70% or better.`
                : 'At today\'s SIPs every goal clears 70%. The emergency fund is kept out of goal money.'}
            </div>
          </Card>
          <Card>
            {title('Corpus after goals', 'P10 to P90 range')}
            <Fan band={f.band} cons={f.conservative_band}
              goals={f.goals.map(g => ({ year: g.target_year, target_amount: g.target_amount, name: g.name }))} />
            <div style={{ display: 'flex', gap: 16, fontSize: 11.5, color: T.muted, marginTop: 6, flexWrap: 'wrap' }}>
              <span><b style={{ color: T.accent }}>━</b> middle case</span>
              <span><b style={{ color: T.warn }}>╌</b> lower-returns case</span>
              <span style={{ color: T.negative }}>● goal payout</span>
              <span>shaded: 10th to 90th percentile</span>
            </div>
          </Card>
        </div>
      )}

      <div style={grid(420)}>
        <Card>
          {title('Allocation vs target', 'by group · colours match Holdings')}
          <div style={{ display: 'grid', gap: 14 }}>
            {k.drift.filter(d => d.value > 0 || d.target_pct > 0).map(d => {
              const off = Math.abs(d.drift_pct) >= 3
              return (
                <div key={d.group}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 5 }}>
                    <span style={{ fontWeight: 600, display: 'inline-flex', alignItems: 'center' }}><CardChip color={groupColor(d.group)} name={d.group} size={18} />{d.group}&nbsp;<span style={{ color: T.muted, fontWeight: 400 }}>· {fmt(d.value)}</span></span>
                    <span><b>{d.actual_pct}%</b> <span style={{ color: T.muted }}>/ {d.target_pct}%</span></span>
                  </div>
                  <div style={{ position: 'relative' }}>
                    {bar(d.actual_pct, groupColor(d.group))}
                    <div style={{ position: 'absolute', left: `${Math.min(d.target_pct, 100)}%`, top: -3, height: 12, width: 2, background: T.text, opacity: 0.7 }} />
                  </div>
                  {off && (
                    <div style={{ fontSize: 11.5, color: T.warn, marginTop: 3 }}>
                      {d.trade > 0 ? `${Math.abs(d.drift_pct)} pts under: direct about ${fmt(d.trade)} here` : `${Math.abs(d.drift_pct)} pts over: about ${fmt(-d.trade)} above target`}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </Card>
        <Card>
          {title('Risk & safety')}
          <div style={{ display: 'grid', gap: 12, fontSize: 13 }}>
            {k.concentration.top && <Row l="Largest position" v={`${k.concentration.top.pct}% · ${k.concentration.top.name}`} warn={k.concentration.top.pct > 15} />}
            <Row l="Top 5 positions" v={`${k.concentration.top5_pct}% of portfolio`} warn={k.concentration.top5_pct > 60} />
            <Row l="Locked in provident funds" v={`${k.locked_pct}%`} />
            {k.fixed.avg_rate != null && <Row l="Fixed-income yield" v={`${k.fixed.avg_rate}% on ${fmt(k.fixed.rated_value)}`} />}
            {k.fixed.maturing.map(m => <Row key={m.name} l="Maturing within a year" v={`${m.name} · ${m.date} · ${fmt(m.value)}`} />)}
          </div>
          {k.concentration.sectors.length > 0 && (
            <>
              <div style={{ ...label, margin: '18px 0 10px' }}>Equity by sector</div>
              <div style={{ display: 'grid', gap: 8 }}>
                {k.concentration.sectors.slice(0, 6).map(s => (
                  <div key={s.sector} style={{ display: 'grid', gridTemplateColumns: '110px 1fr 40px', gap: 10, alignItems: 'center', fontSize: 12 }}>
                    <span style={{ color: T.muted, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.sector}</span>
                    {bar(s.pct, T.accent, 5)}
                    <span style={{ textAlign: 'right' }}>{s.pct}%</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </Card>
      </div>

      <div style={grid(420)}>
        <Card>{title('Best performers', 'equity, funds, gold')}<PerfList rows={k.performers.best} empty="Nothing yet" /></Card>
        <Card>{title('Laggards')}<PerfList rows={k.performers.worst} empty="No holding is below cost" /></Card>
      </div>

      <Card>
        {title('Net worth history', k.history.length > 1 ? `${k.history.length} snapshots` : '')}
        {k.history.length > 1
          ? <Trend h={k.history} />
          : <div style={{ color: T.muted, fontSize: 13 }}>A snapshot is saved each day you open the app. The curve, 30-day change and XIRR build from here.</div>}
      </Card>
    </>
  )
}
