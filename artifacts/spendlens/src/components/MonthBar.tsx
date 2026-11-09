import { useEffect, useMemo, useState, type CSSProperties, type ReactNode } from 'react'
import { getDataMonths } from '../api'
import { currentMonth, shiftMonth } from '../months'
import { MONTHS, T } from '../theme'

export type ExpenseView = 'sheet' | 'calendar'

const NAV_H = 48   // the app's top navigation, which this bar sits under

/** The Expense page's bar: stays under the top navigation while the page scrolls. The month is the title (its two parts
 *  are drop-downs, so any month is two clicks away), with ‹ › beside it and Today when another month is shown. One month
 *  serves both the Sheet and the Calendar. `right` holds the view's own actions. */
export default function MonthBar({ month, onMonth, view, onView, right }: {
  month: string; onMonth: (m: string) => void; view: ExpenseView; onView: (v: ExpenseView) => void; right?: ReactNode
}) {
  const [withData, setWithData] = useState<Set<string>>(new Set())
  useEffect(() => { getDataMonths().then(m => setWithData(new Set(m))).catch(() => setWithData(new Set())) }, [])
  const year = month.slice(0, 4), mon = Number(month.slice(5))
  const years = useMemo(() => {
    const ys = new Set([...withData].map(m => m.slice(0, 4)))
    ys.add(currentMonth().slice(0, 4))
    ys.add(year)
    return [...ys].sort()
  }, [withData, year])

  const arrow: CSSProperties = {
    width: 28, height: 28, borderRadius: 7, border: `1px solid ${T.border}`, background: T.surface, color: T.text,
    fontSize: 15, lineHeight: 1, cursor: 'pointer', flexShrink: 0,
  }
  const title: CSSProperties = {
    appearance: 'none', WebkitAppearance: 'none', border: 'none', background: 'transparent', color: T.text, cursor: 'pointer',
    fontFamily: 'var(--font-display, inherit)', fontSize: 16, fontWeight: 650, padding: '4px 4px', borderRadius: 6, outline: 'none',
    fieldSizing: 'content',   // as wide as the chosen month, not the longest one (browsers without it fall back to the longest)
  } as CSSProperties
  return (
    <div style={{
      position: 'sticky', top: NAV_H, zIndex: 40, background: `color-mix(in srgb, ${T.bg} 92%, transparent)`,
      backdropFilter: 'blur(8px)', WebkitBackdropFilter: 'blur(8px)', borderBottom: `1px solid ${T.border}`,
    }}>
      <div style={{ padding: '10px 24px', display: 'flex', alignItems: 'center', gap: '10px 14px', flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <button type="button" style={arrow} aria-label="Previous month" title="Previous month ( [ )" onClick={() => onMonth(shiftMonth(month, -1))}>‹</button>
          <select aria-label="Month" style={{ ...title, marginLeft: 4 }} value={mon} onChange={e => onMonth(`${year}-${String(e.target.value).padStart(2, '0')}`)}>
            {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
          </select>
          <select aria-label="Year" style={{ ...title, marginRight: 4 }} value={year} onChange={e => onMonth(`${e.target.value}-${String(mon).padStart(2, '0')}`)}>
            {years.map(y => <option key={y}>{y}</option>)}
          </select>
          <button type="button" style={arrow} aria-label="Next month" title="Next month ( ] )" onClick={() => onMonth(shiftMonth(month, 1))}>›</button>
          {month !== currentMonth() && (
            <button type="button" onClick={() => onMonth(currentMonth())} style={{
              marginLeft: 6, border: 'none', cursor: 'pointer', borderRadius: 8, padding: '6px 10px', fontSize: 12.5, fontWeight: 600,
              color: T.accent, background: `color-mix(in srgb, ${T.accent} 14%, transparent)`,
            }}>Today</button>
          )}
        </div>
        <div role="tablist" aria-label="Expense view" style={{ display: 'flex', gap: 2, background: T.surface2, borderRadius: 8, padding: 3 }}>
          {(['sheet', 'calendar'] as const).map(v => (
            <button key={v} type="button" role="tab" aria-selected={view === v} onClick={() => onView(v)} style={{
              border: 'none', cursor: 'pointer', borderRadius: 6, padding: '5px 12px', fontSize: 13, fontWeight: 500,
              background: view === v ? T.surface : 'transparent', color: view === v ? T.text : T.muted,
            }}>{v === 'sheet' ? 'Sheet' : 'Calendar'}</button>
          ))}
        </div>
        <div style={{ flex: 1 }} />
        {right}
      </div>
    </div>
  )
}
