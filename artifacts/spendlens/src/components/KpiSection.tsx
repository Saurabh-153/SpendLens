import { useState, type ReactNode } from 'react'
import { T } from '../theme'
import { card } from './ui'

/** A block of KPI tiles that folds into one line, the way the Expense sheet's KPIs do. `storageKey` remembers the choice
 *  per place; `line` is what the one-line view shows, `children` the tiles. */
export default function KpiSection({ storageKey, label, line, children }: { storageKey: string; label: string; line: ReactNode; children: ReactNode }) {
  const [compact, setCompact] = useState(() => { try { return localStorage.getItem(storageKey) === '1' } catch { return false } })
  const flip = () => setCompact(c => { try { localStorage.setItem(storageKey, c ? '0' : '1') } catch { /* storage unavailable */ } return !c })
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 6 }}>
        <span style={{ fontSize: 11, letterSpacing: 0.6, textTransform: 'uppercase', color: T.muted, fontWeight: 600 }}>{label}</span>
        <button type="button" onClick={flip} style={{ border: 'none', background: 'none', cursor: 'pointer', color: T.accent, fontSize: 12.5, fontWeight: 600, padding: '2px 4px' }}>
          {compact ? 'Show all KPIs' : 'Show less'}
        </button>
      </div>
      {compact
        ? <section aria-label={label} style={{ ...card, padding: '10px 14px', display: 'flex', alignItems: 'center', gap: '8px 20px', flexWrap: 'wrap', fontSize: 13 }}>{line}</section>
        : children}
    </div>
  )
}

/** One "Label value" pair in the one-line view. */
export function LineItem({ label, children, color }: { label: string; children: ReactNode; color?: string }) {
  return <span style={{ color: T.muted, whiteSpace: 'nowrap' }}>{label} <b style={{ color: color ?? T.text, fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>{children}</b></span>
}
