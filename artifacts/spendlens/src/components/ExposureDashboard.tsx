import { useCallback, useEffect, useState } from 'react'
import { getExposure, type ExposureData } from '../api'
import { MIX, colorOf } from '../exposure'
import { T, fmt, pnlColor, signed } from '../theme'
import MixPlan from './MixPlan'
import { Card, label } from './ui'

const EXPOSURES: readonly string[] = MIX
const GAP = 2 // surface-coloured gap between adjacent fills

const title = (t: string, right?: string) => (
  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 14 }}>
    <span style={{ ...label, fontSize: 12.5, letterSpacing: 0.8 }}>{t}</span>
    {right && <span style={{ ...label, fontSize: 10.5 }}>{right}</span>}
  </div>
)
const swatch = (c: string) => <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: 2, background: c, marginRight: 7 }} />
const pct1 = (n: number) => `${n.toFixed(1)}%`

function Donut({ rows, total, active, onPick }: { rows: ExposureData['exposures']; total: number; active: string | null; onPick: (n: string | null) => void }) {
  const R = 70, W = 22, C = 2 * Math.PI * R
  let offset = 0
  return (
    <svg viewBox="0 0 200 200" width="100%" style={{ maxWidth: 220, display: 'block', margin: '0 auto' }} role="img"
      aria-label={`Allocation by exposure: ${rows.map(r => `${r.name} ${r.pct}%`).join(', ')}`}>
      <g transform="rotate(-90 100 100)">
        {rows.filter(r => r.present > 0).map(r => {
          const len = (r.present / total) * C
          const el = (
            <circle key={r.name} cx="100" cy="100" r={R} fill="none" stroke={colorOf(r.name)} strokeWidth={active === r.name ? W + 4 : W}
              strokeDasharray={`${Math.max(len - GAP, 0.5)} ${C}`} strokeDashoffset={-offset} style={{ cursor: 'pointer', opacity: active && active !== r.name ? 0.35 : 1 }}
              onMouseEnter={() => onPick(r.name)} onMouseLeave={() => onPick(null)}>
              <title>{`${r.name}: ${fmt(r.present)} (${pct1(r.pct)})`}</title>
            </circle>
          )
          offset += len
          return el
        })}
      </g>
      <text x="100" y="95" textAnchor="middle" fontSize="11" fill={T.muted}>Net worth</text>
      <text x="100" y="116" textAnchor="middle" fontSize="19" fontWeight="700" fill={T.text}>{fmt(total)}</text>
    </svg>
  )
}

export default function ExposureDashboard() {
  const [d, setD] = useState<ExposureData | null>(null)
  const [error, setError] = useState('')
  const [active, setActive] = useState<string | null>(null)

  const load = useCallback(() => { getExposure().then(x => { setD(x); setError('') }).catch(e => setError(e.message)) }, [])
  useEffect(load, [load])

  if (!d) return <div style={{ color: error ? T.negative : T.muted }}>{error || 'Loading…'}</div>
  const rows = d.exposures
  const hasTargets = rows.some(r => r.target != null)
  const maxTag = Math.max(...d.tags.map(t => t.present), 1)
  return (
    <div>
      {error && <div style={{ color: T.negative, fontSize: 12.5, marginBottom: 10 }}>{error}</div>}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12, marginBottom: 16 }}>
        {rows.map(r => (
          <Card key={r.name} style={{ padding: '14px 18px', borderTop: `3px solid ${colorOf(r.name)}` }}>
            <div style={label}>{r.name}</div>
            <div style={{ fontFamily: 'var(--font-display, inherit)', fontSize: 24, fontWeight: 700, margin: '4px 0 2px' }}>{pct1(r.pct)}</div>
            <div style={{ fontSize: 12, color: T.muted }}>{fmt(r.present)} · {r.count} holding{r.count === 1 ? '' : 's'}</div>
          </Card>
        ))}
      </div>

      <MixPlan />

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: 16, marginBottom: 16 }}>
        <Card style={{ padding: 20 }}>
          {title('Allocation by exposure', 'debt includes cash')}
          <Donut rows={rows} total={d.total} active={active} onPick={setActive} />
          <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: 16, fontSize: 12.5 }}>
            <thead>
              <tr style={{ color: T.muted, fontSize: 10.5, textTransform: 'uppercase', letterSpacing: 0.6 }}>
                <th style={{ textAlign: 'left', padding: '4px 0' }}>Exposure</th><th style={{ textAlign: 'right' }}>Value</th>
                <th style={{ textAlign: 'right' }}>Share</th>{hasTargets && <th style={{ textAlign: 'right' }}>Target</th>}<th style={{ textAlign: 'right' }}>Gain</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(r => (
                <tr key={r.name} style={{ borderTop: `1px solid ${T.hairline}`, opacity: active && active !== r.name ? 0.45 : 1 }}
                  onMouseEnter={() => setActive(r.name)} onMouseLeave={() => setActive(null)}>
                  <td style={{ padding: '7px 0' }}>{swatch(colorOf(r.name))}{r.name}</td>
                  <td style={{ textAlign: 'right' }}>{fmt(r.present)}</td>
                  <td style={{ textAlign: 'right' }}>{pct1(r.pct)}</td>
                  {hasTargets && (
                    <td style={{ textAlign: 'right', color: T.muted }} title={r.add != null ? `${r.add >= 0 ? 'Add' : 'Trim'} ${fmt(Math.abs(r.add))} to reach target` : ''}>
                      {r.target != null ? `${r.target}%` : '—'}
                      {r.drift != null && <span style={{ color: Math.abs(r.drift) >= 5 ? T.warn : T.muted }}> ({r.drift > 0 ? '+' : ''}{r.drift})</span>}
                    </td>
                  )}
                  <td style={{ textAlign: 'right', color: pnlColor(r.pl) }}>{signed(r.pl)} <span style={{ fontSize: 11 }}>{r.pl_pct > 0 ? '+' : ''}{r.pl_pct}%</span></td>
                </tr>
              ))}
            </tbody>
          </table>
          {hasTargets && <div style={{ fontSize: 11.5, color: T.muted, marginTop: 10 }}>Targets are set in Admin → Goals &amp; targets.</div>}
        </Card>

        <Card style={{ padding: 20 }}>
          {title('Exposure by group', 'where each sits')}
          {d.by_group.map(g => {
            const sum = Object.values(g.values).reduce((a, b) => a + b, 0)
            return (
              <div key={g.group} style={{ marginBottom: 14 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12.5, marginBottom: 5 }}>
                  <span>{g.group}</span><span style={{ color: T.muted }}>{fmt(sum)} · {pct1(d.total ? (sum / d.total) * 100 : 0)}</span>
                </div>
                <div style={{ display: 'flex', height: 10, gap: GAP, borderRadius: 3, overflow: 'hidden' }}>
                  {[...EXPOSURES, ...Object.keys(g.values).filter(k => !EXPOSURES.includes(k))].filter(e => g.values[e] > 0).map(e => (
                    <div key={e} title={`${g.group} · ${e}: ${fmt(g.values[e])} (${pct1((g.values[e] / sum) * 100)})`}
                      style={{ width: `${(g.values[e] / sum) * 100}%`, background: colorOf(e), opacity: active && active !== e ? 0.35 : 1 }}
                      onMouseEnter={() => setActive(e)} onMouseLeave={() => setActive(null)} />
                  ))}
                </div>
              </div>
            )
          })}
          <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', marginTop: 8, fontSize: 11.5, color: T.muted }}>
            {rows.map(r => <span key={r.name}>{swatch(colorOf(r.name))}{r.name}</span>)}
          </div>
          <div style={{ fontSize: 11.5, color: T.muted, marginTop: 10 }}>
            A group is where the money is held; the colours show what it is really invested in.
          </div>
        </Card>
      </div>

      <Card style={{ padding: 20, marginBottom: 16 }}>
        {title('Themes and sectors', 'extra tags · can overlap')}
        {d.tags.length === 0 && <div style={{ fontSize: 12.5, color: T.muted }}>No tags yet. Add them in the holding dialog.</div>}
        {d.tags.slice(0, 14).map(t => (
          <div key={t.tag} style={{ display: 'grid', gridTemplateColumns: 'minmax(110px, 190px) 1fr 120px', gap: 12, alignItems: 'center', padding: '4px 0', fontSize: 12.5 }}>
            <span>{t.tag} <span style={{ color: T.muted, fontSize: 11 }}>{t.count}</span></span>
            <div style={{ height: 8, background: T.surface2, borderRadius: 4, overflow: 'hidden' }} title={`${t.tag}: ${fmt(t.present)} (${pct1(t.pct)})`}>
              <div style={{ width: `${(t.present / maxTag) * 100}%`, height: '100%', background: colorOf(t.exposure), borderRadius: 4 }} />
            </div>
            <span style={{ textAlign: 'right', color: T.muted }}>{fmt(t.present)} · {pct1(t.pct)}</span>
          </div>
        ))}
        <div style={{ fontSize: 11.5, color: T.muted, marginTop: 8 }}>Bar colour is the tag's main exposure. A holding with two tags counts under both, so shares do not add up to 100%.</div>
      </Card>
    </div>
  )
}
