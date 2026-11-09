import { useMemo, type ReactNode } from 'react'
import type { Holding } from '../api'
import { displayName } from '../names'
import { T, pnlColor } from '../theme'
import { pct } from './holdingColumns'
import { card } from './ui'

function Side({ title, hint, children }: { title: string; hint: string; children: ReactNode }) {
  return (
    <section style={{ ...card, padding: '14px 16px' }}>
      <h2 style={{ fontSize: 15, marginBottom: 2 }}>{title}</h2>
      <p style={{ color: T.muted, fontSize: 12.5, margin: '2px 0 8px', lineHeight: 1.5 }}>{hint}</p>
      {children}
    </section>
  )
}

const line = (i: number) => ({ display: 'flex', gap: 10, alignItems: 'baseline', padding: '7px 0', borderTop: i ? `1px solid ${T.hairline}` : undefined, fontSize: 13 }) as const

/** The column beside the Holdings table: what to act on, who moved most, and how spread out the money is. */
export default function HoldingsSide({ holdings, total, notes }: { holdings: Holding[]; total: number; notes: string[] }) {
  const s = useMemo(() => {
    const graded = holdings.filter(h => h.asset_type !== 'CASH' && h.invested > 0).sort((a, b) => b.pl_pct - a.pl_pct)
    const n = Math.min(3, Math.floor(graded.length / 2))
    const top = [...holdings].sort((a, b) => b.present - a.present)
    const locked = holdings.filter(h => h.asset_type === 'PF').reduce((x, h) => x + h.present, 0)
    const rated = holdings.filter(h => h.rate > 0 && h.present > 0)
    const rv = rated.reduce((x, h) => x + h.present, 0)
    return {
      best: graded.slice(0, n), worst: graded.slice(graded.length - n).reverse(), top,
      top5: top.slice(0, 5).reduce((x, h) => x + h.present, 0), locked,
      rate: rv ? rated.reduce((x, h) => x + h.rate * h.present, 0) / rv : null,
    }
  }, [holdings])
  if (!holdings.length) return null
  const share = (v: number) => (total ? ((v / total) * 100).toFixed(1) : '0.0')
  const perf = (h: Holding, i: number) => (
    <div key={h.id} style={line(i)}>
      <div style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={h.name}>{displayName(h).name}</div>
      <b style={{ color: pnlColor(h.pl_pct), fontVariantNumeric: 'tabular-nums' }}>{pct(h.pl_pct)}</b>
    </div>
  )
  const kv = (name: string, value: string) => (
    <div key={name} style={{ display: 'flex', justifyContent: 'space-between', gap: 12, padding: '4px 0', fontSize: 13 }}>
      <span style={{ color: T.muted }}>{name}</span><b style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{value}</b>
    </div>
  )
  return (
    <>
      {notes.length > 0 && (
        <Side title="Worth a look" hint="Things you can act on.">
          {notes.map((n, i) => <div key={n} style={line(i)}><span style={{ color: T.warn }}>●</span><div style={{ flex: 1, minWidth: 0 }}>{n}</div></div>)}
        </Side>
      )}
      {s.best.length > 0 && (
        <Side title="Best and worst" hint="By return since you bought.">
          {s.best.map(perf)}
          <div style={{ height: 6 }} />
          {s.worst.map(perf)}
        </Side>
      )}
      <Side title="Concentration" hint="How spread out the money is.">
        {s.top[0] && kv('Largest holding', `${displayName(s.top[0]).name.split(' - ')[0]} · ${share(s.top[0].present)}%`)}
        {kv('Top 5 together', `${share(s.top5)}%`)}
        {s.locked > 0 && kv('Locked (provident fund)', `${share(s.locked)}%`)}
        {s.rate != null && kv('Average fixed rate', `${s.rate.toFixed(1)}%`)}
      </Side>
    </>
  )
}
