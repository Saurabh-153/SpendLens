import { useEffect, useMemo, useState } from 'react'
import { getDataMonths } from '../api'
import { currentMonth, shiftMonth } from '../months'
import { MONTHS } from '../theme'
import { btn, input } from './ui'

/** ‹ Month  Year › - the year list only offers years that hold data (plus the current and selected year). */
export default function MonthPicker({ month, onChange }: { month: string; onChange: (m: string) => void }) {
  const [withData, setWithData] = useState<Set<string>>(new Set())
  useEffect(() => { getDataMonths().then(m => setWithData(new Set(m))).catch(() => setWithData(new Set())) }, [])

  const year = month.slice(0, 4)
  const mon = Number(month.slice(5))
  const years = useMemo(() => {
    const ys = new Set([...withData].map(m => m.slice(0, 4)))
    ys.add(currentMonth().slice(0, 4))
    ys.add(year)
    return [...ys].sort()
  }, [withData, year])

  return (
    <>
      <button style={{ ...btn(), padding: '7px 11px' }} title="Previous month" onClick={() => onChange(shiftMonth(month, -1))}>‹</button>
      <select style={{ ...input, width: 'auto', fontWeight: 600 }} value={mon} onChange={e => onChange(`${year}-${String(e.target.value).padStart(2, '0')}`)}>
        {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
      </select>
      <select style={{ ...input, width: 'auto', fontWeight: 600 }} value={year} onChange={e => onChange(`${e.target.value}-${String(mon).padStart(2, '0')}`)}>
        {years.map(y => <option key={y}>{y}</option>)}
      </select>
      <button style={{ ...btn(), padding: '7px 11px' }} title="Next month" onClick={() => onChange(shiftMonth(month, 1))}>›</button>
    </>
  )
}
