import { useCallback, useEffect, useState } from 'react'
import { getHoldingColumns, getHoldingGroups, saveHoldingColumns, setGroupHiddenColumns, type ColumnLayout, type HoldingGroup } from '../../api'
import { T } from '../../theme'
import { AdminHeader, Card, label, smallBtn } from '../ui'
import { COLUMNS, columnLabel, layoutColumns } from '../holdingColumns'

// Which columns the Holdings table shows and in what order, and which groups leave a column empty.
// The list comes from COLUMNS, so a column added in code appears here by itself.
export default function HoldingColumnsTool() {
  const [layout, setLayout] = useState<ColumnLayout>({ order: [], hidden: [] })
  const [groups, setGroups] = useState<HoldingGroup[]>([])
  const [error, setError] = useState('')

  const load = useCallback(() => {
    Promise.all([getHoldingColumns(), getHoldingGroups()]).then(([l, g]) => { setLayout(l); setGroups(g.groups); setError('') }).catch(e => setError(e.message))
  }, [])
  useEffect(load, [load])
  const run = (p: Promise<unknown>) => p.then(load).catch(e => setError(e.message))

  // every column in its current order, hidden ones included
  const all = layoutColumns({ order: layout.order, hidden: [] })
  const save = (order: string[], hidden: string[]) => run(saveHoldingColumns({ order, hidden }))
  const toggle = (key: string) => save(all.map(c => c.key), layout.hidden.includes(key) ? layout.hidden.filter(k => k !== key) : [...layout.hidden, key])
  const move = (i: number, d: -1 | 1) => {
    const keys = all.map(c => c.key); [keys[i], keys[i + d]] = [keys[i + d], keys[i]]
    save(keys, layout.hidden)
  }
  const toggleInGroup = (g: HoldingGroup, key: string) =>
    run(setGroupHiddenColumns(g.id, g.hidden_columns.includes(key) ? g.hidden_columns.filter(k => k !== key) : [...g.hidden_columns, key]))

  const optional = COLUMNS.filter(c => !c.locked)
  return (
    <div>
      <AdminHeader title="Holdings columns" hint="Choose the columns of the Holdings table and their order. A column added in the code shows up here by itself." />
      {error && <div style={{ fontSize: 12.5, marginBottom: 12, color: T.negative }}>{error}</div>}

      <div style={{ ...label, marginBottom: 8 }}>Columns</div>
      <Card style={{ padding: 0, overflow: 'hidden' }}>
        {all.map((c, i) => (
          <div key={c.key} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '9px 16px', borderTop: i ? `1px solid ${T.hairline}` : undefined, fontSize: 13.5 }}>
            <input type="checkbox" disabled={c.locked} checked={c.locked || !layout.hidden.includes(c.key)} onChange={() => toggle(c.key)} />
            <span style={{ flex: 1, color: c.locked || !layout.hidden.includes(c.key) ? T.text : T.muted }}>
              {columnLabel(c)}{c.locked && <span style={{ color: T.muted, fontSize: 11.5 }}> · always shown</span>}
            </span>
            <button style={{ ...smallBtn, opacity: i ? 1 : 0.4 }} disabled={!i} onClick={() => move(i, -1)}>↑</button>
            <button style={{ ...smallBtn, opacity: i < all.length - 1 ? 1 : 0.4 }} disabled={i === all.length - 1} onClick={() => move(i, 1)}>↓</button>
          </div>
        ))}
      </Card>

      <div style={{ ...label, margin: '22px 0 4px' }}>Show per group</div>
      <div style={{ fontSize: 12, color: T.muted, marginBottom: 8 }}>Untick a column to leave its cells empty for that group, e.g. units for a liquid fund.</div>
      <Card style={{ padding: 0, overflowX: 'auto' }}>
        <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 13 }}>
          <thead>
            <tr>
              <th style={{ ...label, textAlign: 'left', padding: '10px 16px' }}>Group</th>
              {optional.map(c => <th key={c.key} style={{ ...label, padding: '10px 12px', textAlign: 'center', whiteSpace: 'nowrap' }}>{columnLabel(c)}</th>)}
            </tr>
          </thead>
          <tbody>
            {groups.map(g => (
              <tr key={g.id} style={{ borderTop: `1px solid ${T.hairline}` }}>
                <td style={{ padding: '8px 16px', fontWeight: 600 }}>{g.name}</td>
                {optional.map(c => (
                  <td key={c.key} style={{ textAlign: 'center', padding: '8px 12px' }}>
                    <input type="checkbox" checked={!g.hidden_columns.includes(c.key)} onChange={() => toggleInGroup(g, c.key)} />
                  </td>
                ))}
              </tr>
            ))}
            {groups.length === 0 && <tr><td style={{ padding: 16, color: T.muted }}>No groups yet.</td></tr>}
          </tbody>
        </table>
      </Card>
    </div>
  )
}
