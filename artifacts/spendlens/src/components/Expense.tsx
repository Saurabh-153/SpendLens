import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { addExpense, getGrid, getReview, setCellEntries, setRange, type GridCategory, type MonthlyGrid } from '../api'
import { currentMonth, shiftMonth } from '../months'
import { T, fmt, fmtFull } from '../theme'
import { AddDialog, CellEditor } from './ExpenseDialogs'
import MonthPicker from './MonthPicker'
import { btn, card, input } from './ui'

const pad = (n: number) => String(n).padStart(2, '0')
const DEFAULTS_KEY = 'spendlens.addDefaults'
const CAT_W_KEY = 'spendlens.categoryColumnWidth'
const CAT_W_DEFAULT = 210, CAT_W_MIN = 150, CAT_W_MAX = 420
const DAY_W = 46, DAY_W_EMPTY = 30   // the least a date column needs: with spend, and with none that month

function readDefaults(): { cat?: number; sub?: number | null } {
  try { return JSON.parse(localStorage.getItem(DEFAULTS_KEY) ?? '{}') } catch { return {} }
}
function saveDefaults(cat: number, sub: number | null) {
  try { localStorage.setItem(DEFAULTS_KEY, JSON.stringify({ cat, sub })) } catch { /* storage unavailable */ }
}

const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

function daysLeft(month: string, days: number): number {
  const now = new Date()
  const cur = `${now.getFullYear()}-${pad(now.getMonth() + 1)}`
  if (month === cur) return days - now.getDate()
  return month < cur ? 0 : days
}

interface Cell { catId: number; day: number }

export default function Expense({ onNavigate }: { onNavigate: (page: 'admin', tool: string, tab?: string) => void }) {
  const [month, setMonth] = useState(currentMonth)
  const [grid, setGrid] = useState<MonthlyGrid | null>(null)
  const [error, setError] = useState('')
  const [sel, setSel] = useState<Cell | null>(null)
  const [quick, setQuick] = useState<(Cell & { text: string }) | null>(null)
  const [editing, setEditing] = useState<Cell | null>(null)
  const [expanded, setExpanded] = useState<Set<number>>(new Set())
  const [adding, setAdding] = useState(false)
  const [reviewCount, setReviewCount] = useState(0)

  const load = useCallback(() => {
    getGrid(month).then(g => { setGrid(g); setError('') }).catch(e => setError(e.message))
    getReview().then(r => setReviewCount(r.reduce((s, x) => s + x.count, 0))).catch(() => setReviewCount(0))
  }, [month])
  useEffect(load, [load])

  const run = useCallback((p: Promise<unknown>) => p.then(load).catch(e => setError(e.message)), [load])

  const cats: GridCategory[] = useMemo(() => grid?.categories ?? [], [grid])

  // The Category column can be dragged wider or narrower (double-click resets it). Whatever it gives up or takes is
  // shared equally by the date columns, so the grid always fills its box. The width is remembered in this browser.
  const [catW, setCatW] = useState(() => {
    try { const v = Number(localStorage.getItem(CAT_W_KEY)); return v >= CAT_W_MIN && v <= CAT_W_MAX ? v : CAT_W_DEFAULT } catch { return CAT_W_DEFAULT }
  })
  const [boxW, setBoxW] = useState(0)
  const boxRef = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    const el = boxRef.current
    if (!el) return
    const ro = new ResizeObserver(() => setBoxW(el.clientWidth))
    ro.observe(el)
    setBoxW(el.clientWidth)
    return () => ro.disconnect()
  }, [grid])
  useEffect(() => { try { localStorage.setItem(CAT_W_KEY, String(catW)) } catch { /* private window */ } }, [catW])
  const startResize = (e: React.MouseEvent) => {
    e.preventDefault()
    const x0 = e.clientX, w0 = catW
    const move = (ev: MouseEvent) => setCatW(Math.min(CAT_W_MAX, Math.max(CAT_W_MIN, w0 + ev.clientX - x0)))
    const up = () => { window.removeEventListener('mousemove', move); window.removeEventListener('mouseup', up); document.body.style.cursor = '' }
    document.body.style.cursor = 'col-resize'
    window.addEventListener('mousemove', move)
    window.addEventListener('mouseup', up)
  }
  const dayNums = useMemo(() => Array.from({ length: grid?.days ?? 0 }, (_, i) => i + 1), [grid])
  const total = useMemo(() => cats.reduce((s, c) => s + c.total, 0), [cats])
  const dailyTotals = useMemo(
    () => dayNums.map(d => cats.reduce((s, c) => s + (c.days[d]?.amount ?? 0), 0)),
    [cats, dayNums],
  )

  // ---- saving a cell from the grid (quick typing, Delete key)
  const saveCell = useCallback((catId: number, day: number, amount: number) => {
    const cat = cats.find(c => c.id === catId)
    if (!cat) return
    const entries = cat.days[day]?.entries ?? []
    if (entries.length > 1) { setEditing({ catId, day }); return }   // several lines: use the full editor
    const date = `${month}-${pad(day)}`
    if (!amount) run(setCellEntries(catId, date, []))
    else if (entries.length === 1) run(setCellEntries(catId, date, [{ id: entries[0].id, subcategory_id: entries[0].subcategory_id, amount, note: entries[0].note }]))
    else run(setCellEntries(catId, date, [{ id: null, subcategory_id: null, amount, note: '' }]))
  }, [cats, month, run])

  const quickRef = useRef(quick)
  quickRef.current = quick
  const commitQuick = useCallback((q: Cell & { text: string }) => {
    if (!quickRef.current) return   // already committed (Enter followed by blur)
    quickRef.current = null
    setQuick(null)
    const value = parseFloat(q.text)
    const existing = cats.find(c => c.id === q.catId)?.days[q.day]?.amount ?? 0
    const next = Number.isFinite(value) ? value : 0
    if (next === existing) return
    saveCell(q.catId, q.day, next)
  }, [cats, saveCell])

  // ---- keyboard: N add, [ ] month, arrows move, digits type, Enter details, Delete clears, Esc deselect
  const keyState = useRef({ sel, quick, editing, adding, cats, grid, month })
  keyState.current = { sel, quick, editing, adding, cats, grid, month }
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const k = keyState.current
      const t = e.target as HTMLElement
      if (['INPUT', 'SELECT', 'TEXTAREA'].includes(t.tagName) || k.editing || k.adding || e.metaKey || e.ctrlKey || e.altKey || !k.grid) return
      if (e.key === 'n' || e.key === 'N') { e.preventDefault(); setAdding(true); return }
      if (e.key === '[') { setMonth(m => shiftMonth(m, -1)); setSel(null); return }
      if (e.key === ']') { setMonth(m => shiftMonth(m, 1)); setSel(null); return }
      if (e.key === 'Escape') { setSel(null); return }
      if (!k.sel) return
      const idx = k.cats.findIndex(c => c.id === k.sel!.catId)
      const move = (dc: number, dd: number) => {
        e.preventDefault()
        const c = k.cats[Math.min(k.cats.length - 1, Math.max(0, idx + dc))]
        setSel({ catId: c.id, day: Math.min(k.grid!.days, Math.max(1, k.sel!.day + dd)) })
      }
      if (e.key === 'ArrowLeft') move(0, -1)
      else if (e.key === 'ArrowRight') move(0, 1)
      else if (e.key === 'ArrowUp') move(-1, 0)
      else if (e.key === 'ArrowDown') move(1, 0)
      else if (e.key === 'Enter') { e.preventDefault(); setEditing(k.sel) }
      else if (e.key === 'Delete' || e.key === 'Backspace') { e.preventDefault(); saveCell(k.sel.catId, k.sel.day, 0) }
      else if (/^[0-9.\-]$/.test(e.key)) { e.preventDefault(); setQuick({ ...k.sel, text: e.key }) }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [saveCell])

  if (!grid) return <div style={{ padding: 20, color: error ? T.negative : T.muted }}>{error || 'Loading…'}</div>

  const savings = grid.income - total
  const left = daysLeft(month, grid.days)
  const openCats = cats.filter(c => !c.archived)
  const defaults = readDefaults()
  const toggle = (id: number) => setExpanded(s => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n })
  const usedPct = grid.budget_cap ? Math.min(100, (total / grid.budget_cap) * 100) : 0
  const editingCat = editing ? cats.find(c => c.id === editing.catId) : undefined

  /** Sub-category rows of a category: its sub-categories with spend (or still active) + Unassigned if any. */
  const subRows = (cat: GridCategory) => {
    const totals = new Map(cat.subs.map(s => [s.subcategory_id, s.total]))
    const rows = grid.subcategories
      .filter(s => s.category_id === cat.id && (totals.has(s.id) || !s.archived))
      .map(s => ({ id: s.id as number | null, name: s.name }))
    if (totals.has(null)) rows.push({ id: null, name: 'Unassigned' })
    return rows.map(r => ({
      ...r,
      total: totals.get(r.id) ?? 0,
      perDay: dayNums.map(d => (cat.days[d]?.entries ?? []).filter(e => e.subcategory_id === r.id).reduce((s, e) => s + e.amount, 0)),
    }))
  }

  // Every other day column is a shade lighter, so the eye can follow a date down the grid. It is a faint overlay
  // that sits on top of whatever the cell already shows (a category tint, the header, the totals row).
  // Today's column gets a yellow wash instead, from the header down to the daily total.
  const todayDay = month === currentMonth() ? new Date().getDate() : 0
  const band = (d: number): React.CSSProperties => (d === todayDay ? { backgroundImage: 'linear-gradient(rgba(250,204,21,0.10), rgba(250,204,21,0.05))' } : d % 2 === 0 ? { backgroundImage: 'linear-gradient(var(--ov-3), var(--ov-3))' } : {})
  const slim = (d: number): React.CSSProperties => (dailyTotals[d - 1] === 0 ? { padding: '9px 2px' } : {})
  const th: React.CSSProperties = { position: 'sticky', top: 0, zIndex: 2, backgroundColor: T.surface2, padding: '10px 6px', fontSize: 11, fontWeight: 600, color: T.muted, textAlign: 'center' }
  // The category column and the Actual / Target columns are a shade apart from the date columns, so the grid reads as
  // three bands: what it is, when, and how it compares.
  const SIDE_BG = T.sideBg
  const END_W = 66   // width of each of the two right-hand columns (Actual, Target)
  // Column widths: each date column has the least it needs, and the rest of the box is shared out equally among them.
  const dayBase = (d: number) => (dailyTotals[d - 1] === 0 ? DAY_W_EMPTY : DAY_W)
  const baseSum = dayNums.reduce((t, d) => t + dayBase(d), 0)
  const extra = Math.max(0, boxW - catW - 2 * END_W - baseSum) / Math.max(1, dayNums.length)
  const tableW = catW + 2 * END_W + baseSum + extra * dayNums.length
  const stickyRight = (bg: string, right = 0): React.CSSProperties => ({ position: 'sticky', right, zIndex: 1, background: bg, boxShadow: `-8px 0 8px -8px var(--shadow)` })

  return (
    <div style={{ padding: '20px 24px' }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 14, flexWrap: 'wrap' }}>
        <MonthPicker month={month} onChange={m => { setMonth(m); setSel(null) }} />
        <div style={{ flex: 1 }} />
        {error && <span style={{ color: T.negative, fontSize: 12 }}>{error}</span>}
        {reviewCount > 0 && (
          <button onClick={() => onNavigate('admin', 'subcategories', 'review')}
            style={{ ...btn(), fontSize: 12, padding: '6px 10px', color: T.warn, background: 'rgba(245,158,11,.1)', borderColor: 'transparent' }}>
            {reviewCount} entries need a sub-category →
          </button>
        )}
        <button style={btn(true)} title="Shortcut: N" onClick={() => setAdding(true)}>+ Add expense</button>
      </div>

      <div style={{ ...card, padding: '12px 18px', display: 'flex', alignItems: 'center', gap: 28, flexWrap: 'wrap', marginBottom: 14 }}>
        <div style={{ flex: '1 1 260px' }}>
          <div style={{ fontSize: 13 }}>
            <b style={{ fontFamily: 'var(--font-display, inherit)', fontSize: 18 }}>{fmtFull(total)}</b>
            <span style={{ color: T.muted }}> spent of {fmtFull(grid.budget_cap)}</span>
          </div>
          <div style={{ height: 4, background: T.surface2, borderRadius: 2, marginTop: 8, overflow: 'hidden' }}>
            <div style={{ height: '100%', width: `${usedPct}%`, background: total > grid.budget_cap ? T.negative : `linear-gradient(90deg, ${T.accent}, ${T.accent2})`, borderRadius: 2 }} />
          </div>
        </div>
        <Stat label="Saved" value={`${savings < 0 ? '-' : ''}${fmtFull(savings)}`} color={savings >= 0 ? T.positive : T.negative} />
        <Stat label="Days left" value={String(left)} />
        {grid.total_cashback > 0 && <Stat label="Cashback" value={fmtFull(grid.total_cashback)} color={T.positive} />}
      </div>

      <div ref={boxRef} style={{ ...card, overflow: 'auto', maxHeight: 'calc(100vh - 235px)' }}>
        <table style={{ borderCollapse: 'collapse', tableLayout: 'fixed', width: tableW, fontSize: 12 }}>
          <colgroup>
            <col style={{ width: catW }} />
            {dayNums.map(d => <col key={d} style={{ width: dayBase(d) + extra }} />)}
            <col style={{ width: END_W }} /><col style={{ width: END_W }} />
          </colgroup>
          <thead>
            <tr>
              <th style={{ ...th, left: 0, zIndex: 3, textAlign: 'left', paddingLeft: 14 }}>
                Category
                <div onMouseDown={startResize} onDoubleClick={() => setCatW(CAT_W_DEFAULT)} title="Drag to resize · double-click to reset"
                  style={{ position: 'absolute', top: 0, right: -4, width: 9, height: '100%', cursor: 'col-resize', zIndex: 5, display: 'flex', justifyContent: 'center' }}>
                  <div style={{ width: 2, height: '100%', background: 'var(--ov-5)' }} />
                </div>
              </th>
              {dayNums.map(d => <th key={d} title={d === todayDay ? 'Today' : undefined} style={{ ...th, ...slim(d), ...band(d), ...(d === todayDay ? { color: T.today, boxShadow: `inset 0 -2px 0 ${T.today}` } : {}) }}>
                {d === todayDay && <div style={{ position: 'absolute', top: 1, left: '50%', transform: 'translateX(-50%)', width: 0, height: 0, borderLeft: '5px solid transparent', borderRight: '5px solid transparent', borderTop: `7px solid ${T.today}`, filter: 'drop-shadow(0 0 3px rgba(250,204,21,.7))' }} />}
                <div style={d === todayDay ? { fontWeight: 800 } : undefined}>{d}</div>
                <div style={{ fontSize: 9, fontWeight: 400, color: d === todayDay ? T.today : T.muted }}>{WEEKDAYS[new Date(Number(month.slice(0, 4)), Number(month.slice(5, 7)) - 1, d).getDay()]}</div>
              </th>)}
              <th style={{ ...th, ...stickyRight(T.surface2, END_W), top: 0, zIndex: 3 }} title="What you spent, as a % of salary (the same basis as Target), with the rupee amount below. Red when over target.">Actual</th>
              <th style={{ ...th, ...stickyRight(T.surface2), top: 0, zIndex: 3 }} title="The target, as a % of salary, with the rupee amount below">Target</th>
            </tr>
          </thead>
          <tbody>
            {cats.map(cat => {
              // Spent as a share of salary: the same basis as the Target column, so the two can be compared directly.
              const pct = grid.income ? (cat.total / grid.income) * 100 : 0
              const over = cat.target_pct > 0 && pct > cat.target_pct
              const isOpen = expanded.has(cat.id)
              const rows = isOpen ? subRows(cat) : []
              const empty = cat.total === 0
              const rowBg = over ? 'rgba(244,63,94,.07)' : undefined
              return (
                <Fragment key={cat.id}>
                  <tr style={{ borderTop: `1px solid ${T.hairline}`, background: rowBg, opacity: cat.archived ? 0.7 : empty ? 0.6 : 1 }}>
                    <td style={{ position: 'sticky', left: 0, zIndex: 1, background: SIDE_BG, padding: empty ? '6px 14px' : '9px 14px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', fontWeight: 500, boxShadow: `inset 3px 0 0 ${cat.color}` }}>
                      <button onClick={() => toggle(cat.id)} title={isOpen ? 'Hide sub-categories' : 'Show sub-categories'}
                        style={{ background: 'none', border: 'none', color: T.muted, cursor: 'pointer', width: 16, fontSize: 10, marginRight: 4 }}>
                        {isOpen ? '▼' : '▶'}
                      </button>
                      {cat.icon} <span style={{ marginLeft: 4 }}>{cat.name}</span>
                      {cat.archived && <span style={{ marginLeft: 8, fontSize: 10, color: T.muted, borderRadius: 4, padding: '1px 5px', background: T.surface2 }}>archived</span>}
                    </td>
                    {dayNums.map(d => {
                      const cell = cat.days[d]
                      const amt = cell?.amount ?? 0
                      const multi = (cell?.entries.length ?? 0) > 1
                      const isSel = sel?.catId === cat.id && sel.day === d
                      const isQuick = quick?.catId === cat.id && quick.day === d
                      return (
                        <td key={d}
                          onClick={() => { if (isSel) setEditing({ catId: cat.id, day: d }); else { setQuick(null); setSel({ catId: cat.id, day: d }) } }}
                          onDoubleClick={() => setEditing({ catId: cat.id, day: d })}
                          title={cell ? cell.entries.map(e => `${grid.subcategories.find(s => s.id === e.subcategory_id)?.name ?? 'Unassigned'}: ${fmtFull(e.amount)}${e.note ? ` (${e.note})` : ''}`).join('\n') : undefined}
                          style={{ ...slim(d), ...band(d), textAlign: 'center', cursor: 'pointer', padding: empty ? '6px 4px' : '9px 4px', fontWeight: 400, backgroundColor: amt ? `${cat.color}2b` : undefined, outline: isSel ? `1.5px solid ${T.accent}` : undefined, outlineOffset: -1.5 }}>
                          {isQuick ? (
                            <input autoFocus inputMode="decimal" value={quick!.text} onChange={e => setQuick({ ...quick!, text: e.target.value })}
                              onFocus={e => e.target.setSelectionRange(e.target.value.length, e.target.value.length)}
                              onBlur={() => commitQuick(quick!)}
                              onKeyDown={e => {
                                if (e.key === 'Enter') { e.preventDefault(); commitQuick(quick!) }
                                else if (e.key === 'Escape') { setQuick(null) }
                                else if (e.key === 'Tab') { e.preventDefault(); const q = quick!; commitQuick(q); setSel({ catId: q.catId, day: Math.min(grid.days, q.day + 1) }) }
                              }}
                              style={{ ...input, width: 58, padding: '5px 4px', textAlign: 'center', borderColor: T.accent }} />
                          ) : (
                            <>{amt ? fmt(amt) : ''}{multi && <sup style={{ color: T.muted, marginLeft: 1 }}>{cell.entries.length}</sup>}</>
                          )}
                        </td>
                      )
                    })}
                    <td style={{ ...stickyRight(SIDE_BG, END_W), textAlign: 'center', lineHeight: 1.25, color: over ? T.negative : T.text, fontWeight: 400 }}>
                      {cat.total ? `${pct.toFixed(2)}%` : <span style={{ color: T.muted, fontWeight: 400 }}>—</span>}
                      {cat.total ? <div style={{ fontSize: 9.5, fontWeight: 400, opacity: 0.8 }}>{fmt(cat.total)}</div> : null}
                    </td>
                    <td style={{ ...stickyRight(SIDE_BG), textAlign: 'center', color: T.muted, lineHeight: 1.25 }}>
                      {cat.target_pct.toFixed(2)}%
                      {cat.target_pct > 0 && <div style={{ fontSize: 9.5, opacity: 0.75 }} title="The target in rupees: its % of this month's salary">{fmt((cat.target_pct / 100) * grid.income)}</div>}
                    </td>
                  </tr>
                  {rows.map(r => (
                    <tr key={`${cat.id}-${r.id}`} style={{ background: 'var(--ov-1)', color: T.muted, borderTop: '1px solid var(--ov-6)' }}>
                      <td style={{ position: 'sticky', left: 0, zIndex: 1, background: SIDE_BG, padding: '6px 14px 6px 48px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', fontSize: 11.5, boxShadow: 'inset 0 1px 0 var(--ov-6)' }}>
                        {r.name}
                      </td>
                      {r.perDay.map((v, i) => <td key={i} style={{ ...slim(i + 1), ...band(i + 1), textAlign: 'center', fontSize: 11 }}>{v ? fmt(v) : ''}</td>)}
                      <td style={{ ...stickyRight(SIDE_BG, END_W), boxShadow: '-8px 0 8px -8px var(--shadow), inset 0 1px 0 var(--ov-6)', textAlign: 'center', fontSize: 11, lineHeight: 1.25 }}>
                        {r.total ? <>{grid.income ? `${((r.total / grid.income) * 100).toFixed(2)}%` : ''}<div style={{ fontSize: 9.5, opacity: 0.8 }}>{fmt(r.total)}</div></> : '—'}
                      </td>
                      <td style={{ ...stickyRight(SIDE_BG), boxShadow: '-8px 0 8px -8px var(--shadow), inset 0 1px 0 var(--ov-6)' }} />
                    </tr>
                  ))}
                </Fragment>
              )
            })}
            <tr style={{ borderTop: `1px solid ${T.hairline}`, fontWeight: 400 }}>
              <td style={{ position: 'sticky', left: 0, background: T.surface2, padding: '9px 14px', fontWeight: 600 }}>Daily total</td>
              {dailyTotals.map((v, i) => <td key={i} style={{ ...slim(i + 1), ...band(i + 1), textAlign: 'center', backgroundColor: T.surface2, color: v ? T.text : T.muted }}>{v ? fmt(v) : ''}</td>)}
              <td style={{ ...stickyRight(T.surface2, END_W), textAlign: 'center', lineHeight: 1.25 }}>
                {grid.income ? `${((total / grid.income) * 100).toFixed(2)}%` : ''}<div style={{ fontSize: 9.5, fontWeight: 400, opacity: 0.8 }}>{fmt(total)}</div>
              </td>
              <td style={{ ...stickyRight(T.surface2), textAlign: 'center', lineHeight: 1.25, color: T.muted }}>
                {grid.categories.reduce((t, c) => t + c.target_pct, 0).toFixed(2)}%<div style={{ fontSize: 9.5, fontWeight: 400, opacity: 0.8 }}>{fmt((grid.categories.reduce((t, c) => t + c.target_pct, 0) / 100) * grid.income)}</div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div style={{ marginTop: 10, fontSize: 11.5, color: T.muted }}>
        Click a cell, then type an amount · Enter for details · Del clears · ←↑↓→ move · N new expense · [ ] change month
      </div>

      {editing && editingCat && (
        <CellEditor category={editingCat} day={editing.day} month={month} subs={grid.subcategories}
          entries={editingCat.days[editing.day]?.entries ?? []} onClose={() => setEditing(null)}
          onSave={lines => { const e = editing; setEditing(null); run(setCellEntries(e.catId, `${month}-${pad(e.day)}`, lines)) }} />
      )}
      {adding && (
        <AddDialog cats={openCats} subs={grid.subcategories} days={grid.days} onClose={() => setAdding(false)}
          defaultDay={month === currentMonth() ? new Date().getDate() : 1} initialCat={defaults.cat} initialSub={defaults.sub ?? null}
          onSave={v => {
            setAdding(false)
            saveDefaults(v.cat, v.sub)
            if (v.from === v.to) run(addExpense(v.cat, `${month}-${pad(v.from)}`, v.amount, v.sub, v.note))
            else run(setRange(v.cat, month, v.from, v.to, v.amount, v.sub, v.replace ? 'replace' : 'add', v.note))
          }} />
      )}
    </div>
  )
}

function Stat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div>
      <div style={{ fontSize: 11, color: T.muted, marginBottom: 2 }}>{label}</div>
      <div style={{ fontFamily: 'var(--font-display, inherit)', fontSize: 16, fontWeight: 600, color: color ?? T.text }}>{value}</div>
    </div>
  )
}
