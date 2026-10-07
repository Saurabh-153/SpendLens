import { Fragment, useEffect, useState } from 'react'
import { getMix, type MixData } from '../api'
import { MIX, colorOf } from '../exposure'
import { displayName } from '../names'
import { T, fmt } from '../theme'
import { Card, label } from './ui'

const GAP = 2
const monthLabel = (iso: string) => new Date(iso + 'T00:00:00').toLocaleDateString('en-IN', { month: 'short', year: 'numeric' })
const swatch = (c: string) => <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: 2, background: c, marginRight: 7 }} />
const title = (t: string, right?: string) => (
  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 14 }}>
    <span style={{ ...label, fontSize: 12.5, letterSpacing: 0.8 }}>{t}</span>
    {right && <span style={{ ...label, fontSize: 10.5 }}>{right}</span>}
  </div>
)
const th: React.CSSProperties = { textAlign: 'right', padding: '4px 0 4px 12px', fontWeight: 600 }
const ratio = (m: Record<string, number>) => MIX.map(e => Math.round(m[e])).join(' / ')

function PathChart({ d }: { d: MixData }) {
  const [hover, setHover] = useState<number | null>(null)
  const W = 640, H = 250, L = 34, R = 10, Tp = 10, B = 24
  const n = d.path.length - 1
  const x = (i: number) => L + (i / n) * (W - L - R)
  const y = (p: number) => Tp + (1 - p / 100) * (H - Tp - B)
  const line = (get: (i: number) => number) => d.path.map((_, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(get(i)).toFixed(1)}`).join(' ')
  const reach = d.plan?.reach_month ?? null
  const years = d.path.filter(p => p.m % 12 === 0 && p.m > 0)
  const at = hover ?? (reach ?? n)
  const pt = d.path[Math.min(at, n)]
  return (
    <>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" style={{ display: 'block' }}
        aria-label={`Share of Equity, Gold and Debt over time. Target ${ratio(d.targets)}${reach != null ? `, reached ${monthLabel(d.plan!.reach_date!)}` : ''}`}
        onMouseLeave={() => setHover(null)}
        onMouseMove={e => {
          const r = e.currentTarget.getBoundingClientRect()
          const px = ((e.clientX - r.left) / r.width) * W
          setHover(Math.max(0, Math.min(n, Math.round(((px - L) / (W - L - R)) * n))))
        }}>
        {[0, 25, 50, 75, 100].map(p => (
          <g key={p}>
            <line x1={L} x2={W - R} y1={y(p)} y2={y(p)} stroke={T.hairline} strokeWidth="1" />
            <text x={L - 6} y={y(p) + 3.5} textAnchor="end" fontSize="10" fill={T.muted}>{p}%</text>
          </g>
        ))}
        {years.map(p => <text key={p.m} x={x(p.m)} y={H - 6} textAnchor="middle" fontSize="10" fill={T.muted}>{p.date.slice(0, 4)}</text>)}
        {MIX.map(e => <line key={'t' + e} x1={L} x2={W - R} y1={y(d.targets[e])} y2={y(d.targets[e])} stroke={colorOf(e)} strokeWidth="1" strokeDasharray="4 4" opacity="0.7" />)}
        {MIX.map(e => <path key={'c' + e} d={line(i => d.path[i].cur[e])} fill="none" stroke={colorOf(e)} strokeWidth="1" opacity="0.35" />)}
        {MIX.map(e => <path key={'r' + e} d={line(i => d.path[i].rec[e])} fill="none" stroke={colorOf(e)} strokeWidth="2" strokeLinejoin="round" />)}
        {reach != null && reach > 0 && (
          <g>
            <line x1={x(reach)} x2={x(reach)} y1={Tp} y2={H - B} stroke={T.muted} strokeWidth="1" strokeDasharray="2 3" />
            {hover != null && hover !== reach && <text x={x(reach)} y={Tp + 9} textAnchor={reach > n * 0.7 ? 'end' : 'start'} dx={reach > n * 0.7 ? -5 : 5} fontSize="10.5" fill={T.muted}>Target reached {monthLabel(d.plan!.reach_date!)}</text>}
          </g>
        )}
        {(hover != null || (reach != null && reach > 0)) && (() => {
          const i = Math.min(hover ?? reach!, n)
          const q = d.path[i]
          const right = i < n * 0.7
          let prev = -99
          const items = [...MIX].sort((p1, p2) => y(q.rec[p1]) - y(q.rec[p2])).map(e => {
            const ly = Math.max(y(q.rec[e]), prev + 14, Tp + 28)
            prev = ly
            return { e, ly }
          })
          const total = q.sip_rec ? MIX.reduce((t, e) => t + q.sip_rec![e], 0) : 0
          const head = `${i === reach ? 'Target reached · ' : ''}${monthLabel(q.date)}${total ? ` · SIP ${fmt(total)}/mo` : ''}`
          const hw = head.length * 6 + 12
          return (
            <g>
              <line x1={x(i)} x2={x(i)} y1={Tp} y2={H - B} stroke={T.muted} strokeWidth="1" />
              <rect x={right ? x(i) + 8 : x(i) - 8 - hw} y={Tp - 2} width={hw} height="15" rx="3" fill={T.surface2} />
              <text x={(right ? x(i) + 8 : x(i) - 8 - hw) + 6} y={Tp + 9} fontSize="10.5" fontWeight="600" fill={T.text}>{head}</text>
              {items.map(({ e, ly }) => {
                const txt = q.sip_rec ? `${fmt(q.sip_rec[e])}/mo` : `${q.rec[e].toFixed(1)}%`
                const w = txt.length * 6.2 + 10
                const bx = right ? x(i) + 8 : x(i) - 8 - w
                return (
                  <g key={e}>
                    <circle cx={x(i)} cy={y(q.rec[e])} r="3.5" fill={colorOf(e)} stroke={T.surface} strokeWidth="2" />
                    <rect x={bx} y={ly - 9} width={w} height="14" rx="3" fill={T.surface} opacity="0.92" stroke={colorOf(e)} strokeWidth="1" />
                    <text x={bx + 5} y={ly + 1.5} fontSize="10.5" fill={T.text}>{txt}</text>
                  </g>
                )
              })}
            </g>
          )
        })()}
      </svg>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 16px', fontSize: 12, marginTop: 8 }}>
        <span style={{ color: T.muted }}>{monthLabel(pt.date)}:</span>
        {MIX.map(e => <span key={e}>{swatch(colorOf(e))}{e} <b>{pt.rec[e].toFixed(1)}%</b> <span style={{ color: T.muted }}>(target {d.targets[e]}%)</span></span>)}
      </div>
      <div style={{ fontSize: 11.5, color: T.muted, marginTop: 8 }}>
        Solid: mix if you follow the suggested SIP split. Faint: mix if SIPs stay as they are. Dashed: target. Where the vertical line crosses each line, the label is the SIP per month for that exposure; hover to move it.
      </div>
    </>
  )
}

export default function MixPlan() {
  const [d, setD] = useState<MixData | null>(null)
  const [error, setError] = useState('')
  useEffect(() => { getMix().then(setD).catch(e => setError(e.message)) }, [])
  if (!d) return error ? <div style={{ color: T.negative, fontSize: 12.5, marginBottom: 12 }}>{error}</div> : null

  const p = d.plan
  const noSip = d.sip.total <= 0
  const last = d.forecast[d.forecast.length - 1]

  let note = ''
  if (!p) note = ''
  else if (noSip) note = 'No SIPs are set, so the mix can only move through returns. Add SIP amounts on the Holdings page to plan a move.'
  else if (p.reach_month === 0) note = `Your mix is already within half a point of ${ratio(d.targets)}. Keep splitting new SIPs in that ratio.`
  else if (!p.reachable) note = `The ratio ${ratio(d.targets)} cannot be reached with SIPs alone: some exposure is already above its target and only selling would fix that. The suggested split gets as close as possible (${ratio(p.end_mix)} after ${Math.round(p.horizon_months / 12)} years).`
  else {
    const tooSoon = p.wanted_months < (p.earliest_month ?? 0)
    note = `Follow the suggested split and your mix reaches ${ratio(d.targets)} in ${monthLabel(p.reach_date!)} (${p.reach_month} months). ${tooSoon
      ? `You asked for ${d.reach_years} years, which is too soon: ${monthLabel(p.earliest_date!)} is the earliest possible.`
      : `The earliest possible is ${monthLabel(p.earliest_date!)}, which needs a sharper change.`} After that, split new SIPs ${ratio(d.targets)}.`
  }

  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: 16, marginBottom: 16 }}>
        <Card style={{ padding: 20 }}>
          {title('Monthly SIP split', `${fmt(d.sip.total)} / month`)}
          <div style={{ display: 'flex', height: 12, gap: GAP, borderRadius: 3, overflow: 'hidden', background: T.surface2 }}>
            {MIX.filter(e => d.sip.by[e].amt > 0).map(e => (
              <div key={e} title={`${e}: ${fmt(d.sip.by[e].amt)} (${d.sip.by[e].pct}%)`} style={{ width: `${d.sip.by[e].pct}%`, background: colorOf(e) }} />
            ))}
          </div>
          <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: 14, fontSize: 12.5 }}>
            <thead>
              <tr style={{ color: T.muted, fontSize: 10.5, textTransform: 'uppercase', letterSpacing: 0.6 }}>
                <th style={{ ...th, textAlign: 'left', paddingLeft: 0 }}>Exposure</th><th style={th}>Now</th><th style={th}>Share</th><th style={th}>Suggested</th><th style={th}>Change</th>
              </tr>
            </thead>
            <tbody>
              {MIX.map(e => {
                const rec = p?.recommended[e]
                return (<Fragment key={e}>
                  <tr style={{ borderTop: `1px solid ${T.hairline}` }}>
                    <td style={{ padding: '7px 0' }}>{swatch(colorOf(e))}{e}</td>
                    <td style={{ textAlign: 'right' }}>{fmt(d.sip.by[e].amt)}</td>
                    <td style={{ textAlign: 'right', color: T.muted }}>{d.sip.by[e].pct}%</td>
                    <td style={{ textAlign: 'right', fontWeight: 600 }}>{rec && !noSip ? `${fmt(rec.amt)} · ${rec.pct}%` : '—'}</td>
                    <td style={{ textAlign: 'right', color: rec && rec.delta !== 0 ? (rec.delta > 0 ? T.positive : T.negative) : T.muted }}>
                      {rec && !noSip ? (rec.delta === 0 ? '–' : `${rec.delta > 0 ? '+' : '−'}${fmt(Math.abs(rec.delta))}`) : '—'}
                    </td>
                  </tr>
                  {d.sip.by[e].items.map(i => {
                    const n = displayName(i)
                    return (
                      <tr key={i.id} style={{ color: T.muted, fontSize: 12 }}>
                        <td style={{ padding: '3px 0 3px 15px', maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={i.name}>
                          {n.name}{n.folio && <span style={{ fontSize: 11 }}> · {n.folio}</span>}
                        </td>
                        <td style={{ textAlign: 'right' }}>{fmt(i.amt)}</td>
                        <td style={{ textAlign: 'right' }}>{d.sip.by[e].amt ? Math.round((i.amt / d.sip.by[e].amt) * 100) : 0}%</td>
                        <td colSpan={2} />
                      </tr>
                    )
                  })}
                </Fragment>)
              })}
            </tbody>
          </table>
          {note && <div style={{ fontSize: 12.5, marginTop: 14, lineHeight: 1.5 }}>{note}</div>}
          <div style={{ fontSize: 11.5, color: T.muted, marginTop: 8 }}>
            Nothing is sold: only where new SIPs go changes. SIPs rise {d.stepup}% a year, returns {MIX.map(e => `${e} ${d.returns[e]}%`).join(', ')}. Change the target in Admin → Goals &amp; targets.
          </div>
        </Card>

        <Card style={{ padding: 20 }}>
          {title('Path to target', `target ${ratio(d.targets)}`)}
          {d.path.length > 1 ? <PathChart d={d} /> : <div style={{ fontSize: 12.5, color: T.muted }}>Nothing to chart yet.</div>}
        </Card>
      </div>

      {d.forecast.length > 0 && p && (
        <Card style={{ padding: 20 }}>
          {title('Forecast', 'if you follow the suggested split')}
          {last && (
            <div style={{ display: 'flex', gap: 28, flexWrap: 'wrap', marginBottom: 14 }}>
              <div><div style={label}>In {last.year}</div><div style={{ fontFamily: 'var(--font-display, inherit)', fontSize: 24, fontWeight: 700 }}>{fmt(last.total)}</div></div>
              <div><div style={label}>If SIPs stay as now</div><div style={{ fontFamily: 'var(--font-display, inherit)', fontSize: 24, fontWeight: 700, color: T.muted }}>{fmt(last.current_total)}</div></div>
              <div><div style={label}>Mix then</div><div style={{ fontFamily: 'var(--font-display, inherit)', fontSize: 24, fontWeight: 700 }}>{ratio(last.pct)}</div></div>
            </div>
          )}
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5, minWidth: 560 }}>
              <thead>
                <tr style={{ color: T.muted, fontSize: 10.5, textTransform: 'uppercase', letterSpacing: 0.6 }}>
                  <th style={{ ...th, textAlign: 'left', paddingLeft: 0 }}>Year</th>
                  {MIX.map(e => <th key={e} style={th}>{e}</th>)}
                  <th style={th}>Total</th><th style={th}>Mix</th><th style={th}>SIPs unchanged</th>
                </tr>
              </thead>
              <tbody>
                {d.forecast.map(f => (
                  <tr key={f.year} style={{ borderTop: `1px solid ${T.hairline}` }}>
                    <td style={{ padding: '6px 0' }}>{f.year}</td>
                    {MIX.map(e => <td key={e} style={{ textAlign: 'right' }}>{fmt(f.values[e])}</td>)}
                    <td style={{ textAlign: 'right', fontWeight: 600 }}>{fmt(f.total)}</td>
                    <td style={{ textAlign: 'right', color: T.muted }}>{ratio(f.pct)}</td>
                    <td style={{ textAlign: 'right', color: T.muted }}>{fmt(f.current_total)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div style={{ fontSize: 11.5, color: T.muted, marginTop: 10 }}>An estimate from the expected returns set in Admin, not a promise. Re-check every few months as markets move the mix.</div>
        </Card>
      )}
    </div>
  )
}
