import { useCallback, useEffect, useState } from 'react'
import { getExposure, type ExposureData, type PortfolioKpis } from '../api'
import { colorOf } from '../exposure'
import { T, fmt, pnlColor, signed } from '../theme'
import MixPlan from './MixPlan'
import { Card, label } from './ui'
import { useNarrow } from '../useNarrow'
import TodayVsTarget from './TodayVsTarget'
import RiskSide from './RiskSide'


const title = (t: string, right?: string) => (
  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 14 }}>
    <span style={{ ...label, fontSize: 12.5, letterSpacing: 0.8 }}>{t}</span>
    {right && <span style={{ ...label, fontSize: 10.5 }}>{right}</span>}
  </div>
)
const pct1 = (n: number) => `${n.toFixed(1)}%`

export default function AllocationTab({ k }: { k: PortfolioKpis | null }) {
  const [d, setD] = useState<ExposureData | null>(null)
  const [error, setError] = useState('')
  const [active, setActive] = useState<string | null>(null)
  const stacked = useNarrow(1040)
  const narrow = useNarrow(680)   // the columns sit above the rows on a phone

  const load = useCallback(() => { getExposure().then(x => { setD(x); setError('') }).catch(e => setError(e.message)) }, [])
  useEffect(load, [load])

  if (!d) return <div style={{ color: error ? T.negative : T.muted }}>{error || 'Loading…'}</div>
  const rows = d.exposures
  const hasTargets = rows.some(r => r.target != null)
  const maxTag = Math.max(...d.tags.map(t => t.present), 1)
  const rebalance = rows.filter(r => r.target != null)
  // Shown beside the Forecast at 35% width (see MixPlan), or on its own when there is no forecast yet.
  const themes = (
    <Card style={{ padding: 20, marginBottom: 0 }}>
    {title('Themes and sectors', 'extra tags · can overlap')}
    {d.tags.length === 0 && <div style={{ fontSize: 12.5, color: T.muted }}>No tags yet. Add them in the holding dialog.</div>}
    {/* One grid for every row, so the bars start and end at the same place whatever the label or amount width. */}
    <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(40px, 34%) max-content max-content', columnGap: 8, rowGap: 8, alignItems: 'center', fontSize: 12.5 }}>
      {d.tags.slice(0, 14).map(t => (
        <div key={t.tag} style={{ display: 'contents' }}>
          <span style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={t.tag}>{t.tag} <span style={{ color: T.muted, fontSize: 11 }}>{t.count}</span></span>
          <div style={{ height: 8, background: T.surface2, borderRadius: 4, overflow: 'hidden' }} title={`${t.tag}: ${fmt(t.present)} (${pct1(t.pct)})`}>
            <div style={{ width: `${(t.present / maxTag) * 100}%`, height: '100%', background: colorOf(t.exposure), borderRadius: 4 }} />
          </div>
          <span style={{ textAlign: 'right', color: T.muted, fontSize: 11.5, whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums' }}>{fmt(t.present)}</span>
          <span style={{ textAlign: 'right', fontSize: 11.5, whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums' }}>{pct1(t.pct)}</span>
        </div>
      ))}
    </div>
    <div style={{ fontSize: 11.5, color: T.muted, marginTop: 8 }}>Bar colour is the tag's main exposure. A holding with two tags counts under both, so shares do not add up to 100%.</div>
    </Card>
  )
  return (
    <div style={{ display: 'grid', gridTemplateColumns: stacked ? 'minmax(0, 1fr)' : 'minmax(0, 1fr) 300px', gap: 16, alignItems: 'start' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16, minWidth: 0 }}>
        {error && <div style={{ color: T.negative, fontSize: 12.5 }}>{error}</div>}
        <Card style={{ padding: '16px 18px' }}>
          {title('Where your money sits', hasTargets ? 'left today · right your target' : 'debt includes cash')}
          <div style={{ display: 'grid', gridTemplateColumns: narrow ? 'minmax(0, 1fr)' : 'auto minmax(0, 1fr)', gap: 28, alignItems: 'center', justifyItems: narrow ? 'center' : undefined }}>
            <TodayVsTarget rows={rows} active={active} onPick={setActive} />
            <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0, width: '100%' }}>
              {rows.map((r, i) => {
                const on = r.drift == null || Math.abs(r.drift) < 2
                const tone = on ? T.positive : T.warn
                return (
                  <div key={r.name} onMouseEnter={() => setActive(r.name)} onMouseLeave={() => setActive(null)} style={{
                    display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) auto', gap: '4px 16px', alignItems: 'center', padding: '11px 6px', borderRadius: 8,
                    borderTop: i ? `1px solid ${T.hairline}` : undefined, background: active === r.name ? 'var(--ov-2)' : undefined, transition: 'background .15s',
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, fontWeight: 600, minWidth: 0 }}>
                      <i style={{ width: 10, height: 10, borderRadius: 3, background: colorOf(r.name), flexShrink: 0 }} />
                      {r.name}
                      <span style={{ fontWeight: 400, color: T.muted, fontSize: 12 }}>{pct1(r.pct)}{r.target != null ? ` · target ${r.target}%` : ''}</span>
                    </div>
                    <div style={{ textAlign: 'right', fontSize: 13, fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>
                      {fmt(r.present)}
                      <div style={{ fontWeight: 400, fontSize: 11.5, color: pnlColor(r.pl) }}>{signed(r.pl)} gain</div>
                    </div>
                    {r.target != null && (
                      <div style={{ gridColumn: '1 / -1' }}>
                        <span style={{ display: 'inline-block', fontSize: 11, fontWeight: 600, padding: '1px 8px', borderRadius: 999, color: tone, background: `color-mix(in srgb, ${tone} 16%, transparent)` }}>
                          {on ? 'On target' : `${r.drift! > 0 ? 'Over by' : 'Short by'} ${fmt(Math.abs(r.add ?? 0))}`}
                        </span>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
          {hasTargets && <div style={{ fontSize: 11.5, color: T.muted, marginTop: 10 }}>Targets are set in Admin → Goals &amp; targets.</div>}
        </Card>

        <MixPlan beside={themes} />
      </div>

      <aside style={{ display: 'flex', flexDirection: 'column', gap: 14, minWidth: 0 }}>
        {rebalance.length > 0 && (
          <Card style={{ padding: '14px 16px' }}>
            <h2 style={{ fontSize: 15, marginBottom: 2 }}>Rebalance</h2>
            <p style={{ color: T.muted, fontSize: 12.5, margin: '2px 0 8px', lineHeight: 1.5 }}>
              What it takes to get back to {rebalance.map(r => r.target).join(' / ')} by buying or selling today. Or reach it without selling by following the SIP split.
            </p>
            {rebalance.map((r, i) => {
              const on = Math.abs(r.drift ?? 0) < 2
              return (
                <div key={r.name} style={{ display: 'flex', gap: 10, alignItems: 'center', padding: '7px 0', borderTop: i ? `1px solid ${T.hairline}` : undefined, fontSize: 13 }}>
                  <i style={{ width: 9, height: 9, borderRadius: '50%', background: colorOf(r.name), flexShrink: 0 }} />
                  <div style={{ flex: 1, minWidth: 0 }}>{r.name}<div style={{ fontSize: 11.5, color: T.muted }}>{pct1(r.pct)} now · target {r.target}%</div></div>
                  <b style={{ color: on ? T.positive : T.warn, fontVariantNumeric: 'tabular-nums' }}>{on ? 'On target' : `${(r.add ?? 0) > 0 ? 'Add' : 'Trim'} ${fmt(Math.abs(r.add ?? 0))}`}</b>
                </div>
              )
            })}
          </Card>
        )}
        {k?.liquidity && <RiskSide k={k} />}
      </aside>
    </div>
  )
}
