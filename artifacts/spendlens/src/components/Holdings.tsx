import { useCallback, useEffect, useMemo, useState } from 'react'
import { createHolding, deleteHolding, getHoldingColumns, getHoldingGroups, getHoldings, portfolioCsvUrl, updateHolding, type ColumnLayout, type Holding, type HoldingGroup, type HoldingInput } from '../api'
import { HOLDING_TYPES, T, fmt, fmtFull, pnlColor, signed } from '../theme'
import { displayName } from '../names'
import { layoutColumns, monthYear, pct, tagsOf, td, type SortKey } from './holdingColumns'
import { btn, card, Field, input, label, Modal } from './ui'
import { CardChip, paletteAt } from '../cardColors'

// MF / FD / PF / cash are entered as amounts (stored as qty 1 × amounts); EQ and gold as quantity × price.
const DIRECT = ['MF', 'FD', 'PF', 'CASH']
const OTHER = 'Others'

const grpOf = (h: Holding) => h.grp || OTHER

function useNarrow(px = 700) {
  const q = `(max-width:${px}px)`
  const [narrow, setNarrow] = useState(() => window.matchMedia(q).matches)
  useEffect(() => {
    const m = window.matchMedia(q), f = () => setNarrow(m.matches)
    m.addEventListener('change', f)
    return () => m.removeEventListener('change', f)
  }, [q])
  return narrow
}

function Kpi({ name, children, sub }: { name: string; children: React.ReactNode; sub?: React.ReactNode }) {
  return (
    <div style={{ ...card, padding: '16px 18px' }}>
      <div style={label}>{name}</div>
      <div style={{ fontFamily: 'var(--font-display, inherit)', fontSize: 26, fontWeight: 700, marginTop: 6, letterSpacing: -0.3 }}>{children}</div>
      {sub && <div style={{ fontSize: 12, color: T.muted, marginTop: 4 }}>{sub}</div>}
    </div>
  )
}

export default function Holdings() {
  const [holdings, setHoldings] = useState<Holding[]>([])
  const [error, setError] = useState('')
  const [group, setGroup] = useState('ALL')
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: 'present', dir: -1 })
  const [open, setOpen] = useState<Set<string> | null>(null) // null = default (largest group open)
  const [editing, setEditing] = useState<Holding | 'new' | null>(null)
  const [deleting, setDeleting] = useState<Holding | null>(null)
  const [groupNames, setGroupNames] = useState<string[]>([])
  const [groupInfo, setGroupInfo] = useState<HoldingGroup[]>([])
  const [layout, setLayout] = useState<ColumnLayout>({ order: [], hidden: [] })
  const narrow = useNarrow()

  const load = useCallback(() => {
    getHoldings().then(h => { setHoldings(h); setError('') }).catch(e => setError(e.message))
    getHoldingGroups().then(g => { setGroupNames(g.groups.map(x => x.name)); setGroupInfo(g.groups) }).catch(() => {})
    getHoldingColumns().then(setLayout).catch(() => {})
  }, [])
  useEffect(load, [load])
  const run = (p: Promise<unknown>) => p.then(load).catch(e => setError(e.message))

  const totals = useMemo(() => {
    const invested = holdings.reduce((s, h) => s + h.invested, 0)
    const present = holdings.reduce((s, h) => s + h.present, 0)
    const sip = holdings.reduce((s, h) => s + (h.sip_amount || 0), 0)
    return { invested, present, sip, pnl: present - invested, pct: invested ? ((present - invested) / invested) * 100 : 0 }
  }, [holdings])

  const allTags = useMemo(() => [...new Set(holdings.flatMap(tagsOf))].sort((a, b) => a.localeCompare(b)), [holdings])

  // groups ordered by value, each with its own totals
  const groups = useMemo(() => {
    const m = new Map<string, Holding[]>()
    holdings.forEach(h => m.set(grpOf(h), [...(m.get(grpOf(h)) ?? []), h]))
    return [...m.entries()].map(([name, items]) => {
      const invested = items.reduce((s, h) => s + h.invested, 0)
      const present = items.reduce((s, h) => s + h.present, 0)
      return { name, items, invested, present, pl: present - invested, pct: invested ? ((present - invested) / invested) * 100 : 0 }
    }).sort((a, b) => b.present - a.present)
  }, [holdings])

  // only things you can act on
  const notes = useMemo(() => {
    const out: string[] = []
    const nm = (h: Holding) => displayName(h).name
    holdings.filter(h => totals.present && h.present / totals.present > 0.15)
      .forEach(h => out.push(`${nm(h)} is ${((h.present / totals.present) * 100).toFixed(0)}% of your portfolio`))
    const losers = holdings.filter(h => h.asset_type === 'EQ' && h.pl_pct < -25)
    if (losers.length) out.push(`${losers.length} stock${losers.length > 1 ? 's' : ''} down more than 25%: ${losers.map(nm).join(', ')}`)
    const today = new Date().toISOString().slice(0, 10)
    const soon = new Date(Date.now() + 90 * 864e5).toISOString().slice(0, 10)
    holdings.filter(h => h.maturity && h.maturity <= soon && h.present > 0).sort((a, b) => a.maturity.localeCompare(b.maturity))
      .forEach(h => out.push(`${nm(h).split(' - ')[0]} ${h.maturity < today ? 'matured' : 'matures'} ${monthYear(h.maturity)}${h.maturity < today ? ' – renew or update its value' : ''}`))
    return out
  }, [holdings, totals.present])

  const q = search.trim().toLowerCase()
  const visibleGroups = groups
    .filter(g => group === 'ALL' || g.name === group)
    .map(g => {
      const rows = g.items.filter(h => !q || h.name.toLowerCase().includes(q) || h.sector.toLowerCase().includes(q) || h.ticker.toLowerCase().includes(q) || (h.tags || '').toLowerCase().includes(q))
        .sort((a, b) => (sort.key === 'name' ? a.name.localeCompare(b.name) : a[sort.key] - b[sort.key]) * sort.dir)
      return { ...g, rows }
    })
    .filter(g => g.rows.length)

  const isOpen = (name: string) => (q || group !== 'ALL') ? true : open ? open.has(name) : name === groups[0]?.name
  const toggle = (name: string) => {
    const cur = open ?? new Set(groups.slice(0, 1).map(g => g.name))
    const next = new Set(cur)
    next.has(name) ? next.delete(name) : next.add(name)
    setOpen(next)
  }
  const allOpen = open !== null && open.size === groups.length
  const setSortKey = (key: SortKey) => setSort(s => (s.key === key ? { key, dir: (-s.dir) as 1 | -1 } : { key, dir: key === 'name' ? 1 : -1 }))

  const thStyle: React.CSSProperties = { padding: '10px 14px', fontSize: 11, fontWeight: 600, letterSpacing: 0.6, textTransform: 'uppercase', textAlign: 'right', whiteSpace: 'nowrap', userSelect: 'none' }
  const arrow = (k?: SortKey) => (k && sort.key === k ? (sort.dir === 1 ? ' ↑' : ' ↓') : '')
  const allRows = visibleGroups.flatMap(g => g.rows)
  // a group leaves a column empty; when every group on screen does, the column goes too
  const hiddenIn = (key: string, group: string) => !!groupInfo.find(x => x.name === group)?.hidden_columns.includes(key)
  const cols = layoutColumns(layout).filter(c => c.locked || !visibleGroups.length || !visibleGroups.every(g => hiddenIn(c.key, g.name))).filter(c => (!narrow || !c.wide) && (!c.when || c.when(allRows)))

  return (
    <div style={{ padding: 20 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 12, marginBottom: 14 }}>
        <Kpi name="Net worth" sub={<>Invested {fmt(totals.invested)}{totals.sip > 0 && <> · SIP {fmt(totals.sip)}/mo</>}</>}>{fmt(totals.present)}</Kpi>
        <Kpi name="Total gain" sub={`${holdings.length} holdings`}>
          <span style={{ color: pnlColor(totals.pnl) }}>{signed(totals.pnl)}</span>{' '}
          <span style={{ fontSize: 15, fontWeight: 600, color: pnlColor(totals.pnl) }}>{pct(totals.pct)}</span>
        </Kpi>
      </div>

      {notes.length > 0 && (
        <div style={{ ...card, padding: '12px 16px', marginBottom: 14, fontSize: 12.5 }}>
          <div style={{ ...label, marginBottom: 6 }}>Worth a look</div>
          {notes.map(n => <div key={n} style={{ color: T.muted, padding: '2px 0' }}><span style={{ color: T.warn }}>●</span> {n}</div>)}
        </div>
      )}

      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 12, flexWrap: 'wrap' }}>
        {['ALL', ...groups.map(g => g.name)].map(name => {
          const active = group === name
          const n = name === 'ALL' ? holdings.length : groups.find(g => g.name === name)!.items.length
          // A group keeps its colour by its place in the Admin list of groups, so it is the same whatever the filter.
          const color = paletteAt(Math.max(groupNames.indexOf(name), 0) + (groupNames.includes(name) ? 0 : groups.findIndex(g => g.name === name) + groupNames.length))
          return (
            <button key={name} onClick={() => setGroup(name)} style={{
              display: 'inline-flex', alignItems: 'center', padding: '6px 11px', borderRadius: 18, fontSize: 12.5, fontWeight: 600, cursor: 'pointer',
              border: `1px solid ${active ? (name === 'ALL' ? T.accent : color) : T.border}`,
              borderBottom: name === 'ALL' ? undefined : `3px solid ${color}`,
              background: active ? T.accent : T.surface2, color: active ? '#fff' : T.text,
            }}>
              {name !== 'ALL' && <CardChip color={color} name={name} size={18} />}
              {name === 'ALL' ? 'All' : name} <span style={{ opacity: 0.6, fontWeight: 500, marginLeft: 6 }}>{n}</span>
            </button>
          )
        })}
        <div style={{ flex: 1 }} />
        <input style={{ ...input, width: 170 }} placeholder="Search name, ticker, tag…" value={search} onChange={e => setSearch(e.target.value)} />
        {error && <span style={{ color: T.negative, fontSize: 12 }}>{error}</span>}
        {group === 'ALL' && !q && <button style={btn()} onClick={() => setOpen(allOpen ? new Set() : new Set(groups.map(g => g.name)))}>{allOpen ? 'Collapse all' : 'Expand all'}</button>}
        <a href={portfolioCsvUrl} style={{ ...btn(), textDecoration: 'none' }}>↓ CSV</a>
        <button style={btn(true)} onClick={() => setEditing('new')}>+ Add</button>
      </div>

      <div style={{ ...card, overflowX: 'auto' }}>
        <table style={{ borderCollapse: 'collapse', width: '100%', minWidth: narrow ? 520 : 720 }}>
          <thead>
            <tr>
              {cols.map(c => (
                <th key={c.key} style={{ ...thStyle, textAlign: c.align }}>
                  {c.heads.map(hd => (
                    <span key={hd.label} title={hd.title} onClick={hd.sort ? () => setSortKey(hd.sort!) : undefined}
                      style={{ display: 'block', cursor: hd.sort ? 'pointer' : undefined, color: hd.sort && sort.key === hd.sort ? T.text : T.muted }}>{hd.label}{arrow(hd.sort)}</span>
                  ))}
                </th>
              ))}
            </tr>
                    </thead>
          {visibleGroups.map(g => {
            const expanded = isOpen(g.name)
            const ctx = { group: g.name, total: totals.present }
            return (
              <tbody key={g.name}>
                <tr onClick={() => toggle(g.name)} style={{ cursor: 'pointer', background: T.surface2 }}>
                  {cols.map(c => <td key={c.key} style={{ ...td, ...c.groupStyle }}>{c.groupCell?.(g, { ...ctx, expanded })}</td>)}
                </tr>
                {expanded && g.rows.map(h => (
                  <tr key={h.id} onClick={() => setEditing(h)} style={{ borderTop: `1px solid ${T.hairline}`, cursor: 'pointer' }}
                    onMouseEnter={e => (e.currentTarget.style.background = 'var(--ov-2)')} onMouseLeave={e => (e.currentTarget.style.background = '')}>
                    {cols.map(c => !c.locked && hiddenIn(c.key, g.name)
                      ? <td key={c.key} style={td} />
                      : <td key={c.key} style={{ ...td, ...c.cellStyle?.(h) }} title={c.cellTip?.(h, ctx)}>{c.cell(h, ctx)}</td>)}
                  </tr>
                ))}
              </tbody>
            )
          })}
          {visibleGroups.length === 0 && <tbody><tr><td colSpan={cols.length} style={{ ...td, textAlign: 'center', color: T.muted }}>No holdings found</td></tr></tbody>}
        </table>
      </div>

      {editing && (
        <HoldingDialog holding={editing === 'new' ? null : editing} groups={groupNames} allTags={allTags}
          onClose={() => setEditing(null)}
          onDelete={editing === 'new' ? undefined : () => { setDeleting(editing); setEditing(null) }}
          onSave={input => {
            const id = editing === 'new' ? null : editing.id
            setEditing(null)
            run(id === null ? createHolding(input) : updateHolding(id, input))
          }} />
      )}
      {deleting && (
        <Modal title="Delete holding?" onClose={() => setDeleting(null)}>
          <p style={{ fontSize: 13, color: T.muted, marginBottom: 16 }}>
            Remove <b style={{ color: T.text }}>{displayName(deleting).name}</b> ({fmtFull(deleting.present)}) from your portfolio? This cannot be undone.
          </p>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
            <button style={btn()} onClick={() => setDeleting(null)}>Cancel</button>
            <button style={{ ...btn(), background: T.danger, borderColor: T.danger, color: '#fff' }}
              onClick={() => { const id = deleting.id; setDeleting(null); run(deleteHolding(id)) }}>Delete</button>
          </div>
        </Modal>
      )}
    </div>
  )
}

function HoldingDialog({ holding, groups, allTags, onClose, onSave, onDelete }: {
  holding: Holding | null; groups: string[]; allTags: string[]; onClose: () => void; onSave: (h: HoldingInput) => void; onDelete?: () => void
}) {
  const [name, setName] = useState(holding?.name ?? '')
  const [ticker, setTicker] = useState(holding?.ticker ?? '')
  const [sector, setSector] = useState(holding?.sector ?? '')
  const [grp, setGrp] = useState(holding?.grp ?? '')
  const [type, setType] = useState(holding?.asset_type ?? 'EQ')
  const [notes, setNotes] = useState(holding?.notes ?? '')
  const [tags, setTags] = useState(holding?.tags ?? '')
  const [exposure, setExposure] = useState(holding?.exposure === 'Cash' ? 'Debt' : holding?.exposure ?? '')
  const [sip, setSip] = useState(holding?.sip_amount ? String(holding.sip_amount) : '')
  const [sipDay, setSipDay] = useState(holding?.sip_day ? String(holding.sip_day) : '')
  const [maturity, setMaturity] = useState(holding?.maturity ?? '')
  const [rate, setRate] = useState(holding?.rate ? String(holding.rate) : '')
  const [startDate, setStartDate] = useState(holding?.start_date ?? '')
  const [comp, setComp] = useState(holding?.compounding || 'Q')
  const [manual, setManual] = useState(!!holding?.manual)
  const [credits, setCredits] = useState(holding?.credits ?? '')
  const [rd, setRd] = useState(!!holding?.rd)
  const [fixedOpen, setFixedOpen] = useState(false)
  const direct = DIRECT.includes(type)
  const cash = type === 'CASH'
  const [qty, setQty] = useState(String(holding?.qty ?? ''))
  // For priced types these are per-unit prices; for direct types they are invested / present totals.
  const [a, setA] = useState(String(DIRECT.includes(holding?.asset_type ?? '') ? holding?.invested ?? '' : holding?.buy_price ?? ''))
  const [b, setB] = useState(String(DIRECT.includes(holding?.asset_type ?? '') ? holding?.present ?? '' : holding?.cmp ?? ''))

  // amounts and per-unit prices mean different things: keep what was typed unless the entry style changes
  const changeType = (t: string) => { if (DIRECT.includes(t) !== direct) { setA(''); setB('') } setType(t) }
  const n = (s: string) => parseFloat(s) || 0
  const present = direct ? n(b) : n(qty) * n(b)
  const invested = cash ? present : direct ? n(a) : n(qty) * n(a)
  const canFixed = type !== 'EQ' && type !== 'GOLD'
  const showFixed = canFixed && (type === 'FD' || type === 'PF' || n(rate) > 0 || fixedOpen)
  const auto = showFixed && !manual && n(rate) > 0 && !!startDate
  const rdOn = auto && rd && n(sip) > 0
  const pnl = present - invested
  const tagList = tags.split(',').map(t => t.trim()).filter(Boolean)
  const toggleTag = (t: string) => setTags((tagList.includes(t) ? tagList.filter(x => x !== t) : [...tagList, t]).join(', '))
  const field = (name: string, value: string, set: (v: string) => void, type = 'number', autoFocus = false) => (
    <Field name={name}><input style={input} type={type} value={value} autoFocus={autoFocus} onChange={e => set(e.target.value)} /></Field>
  )
  const hint: React.CSSProperties = { fontSize: 11.5, color: T.muted, margin: '-4px 0 10px' }

  return (
    <Modal title={holding ? 'Edit holding' : 'Add holding'} onClose={onClose}>
      {field('Name', name, setName, 'text')}
      <div style={{ display: 'flex', gap: 10 }}>
        <div style={{ flex: 1 }}>
          <Field name="Type">
            <select style={input} value={type} onChange={e => changeType(e.target.value)}>
              {HOLDING_TYPES.map(t => <option key={t}>{t}</option>)}
            </select>
          </Field>
        </div>
        <div style={{ flex: 1 }}>
          <Field name="Group">
            <select style={input} value={grp} onChange={e => setGrp(e.target.value)}>
              <option value="">{OTHER}</option>
              {groups.map(g => <option key={g}>{g}</option>)}
            </select>
          </Field>
        </div>
      </div>
      {(type === 'EQ' || type === 'GOLD' || ['FD', 'PF', 'CASH'].includes(type)) && (
        <div style={{ display: 'flex', gap: 10 }}>
          {(type === 'EQ' || type === 'GOLD') && <div style={{ flex: 1 }}>{field('Ticker', ticker, setTicker, 'text')}</div>}
          {['FD', 'PF', 'CASH'].includes(type) && <div style={{ flex: 1 }}>{field('Bank / institution', sector, setSector, 'text')}</div>}
        </div>
      )}
      {cash ? (
        field('Amount (₹)', b, setB, 'number', !!holding)
      ) : direct ? (
        <div style={{ display: 'flex', gap: 10 }}>
          <div style={{ flex: 1 }}>{rdOn ? <Field name="Invested"><div style={{ ...input, color: T.muted }}>Auto (deposits)</div></Field> : field('Invested (₹)', a, setA)}</div>
          <div style={{ flex: 1 }}>{auto ? <Field name="Present value"><div style={{ ...input, color: T.muted }}>Auto-calculated</div></Field> : field('Present value (₹)', b, setB, 'number', !!holding)}</div>
        </div>
      ) : (
        <>
          {field('Quantity', qty, setQty)}
          <div style={{ display: 'flex', gap: 10 }}>
            <div style={{ flex: 1 }}>{field('Avg buy price (₹)', a, setA)}</div>
            <div style={{ flex: 1 }}>{field('Current price (₹)', b, setB, 'number', !!holding)}</div>
          </div>
        </>
      )}
      {!cash && (
        <div style={{ display: 'flex', gap: 10 }}>
          <div style={{ flex: 1 }}>{field('Monthly SIP (₹)', sip, setSip)}</div>
          {n(sip) > 0 && <div style={{ flex: 1 }}>{field('SIP day (1-31)', sipDay, setSipDay)}</div>}
        </div>
      )}
      {showFixed ? (
        <>
          <div style={{ display: 'flex', gap: 10 }}>
            <div style={{ flex: 1 }}>{field('Interest rate (% p.a.)', rate, setRate)}</div>
            <div style={{ flex: 1 }}>
              <Field name="Compounding">
                <select style={input} value={comp} onChange={e => setComp(e.target.value)}>
                  <option value="Q">Quarterly</option><option value="A">Annual</option><option value="S">Simple</option><option value="Y">Credited yearly (cumulative FD)</option>
                </select>
              </Field>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 10 }}>
            <div style={{ flex: 1 }}>{field('Opening date', startDate, setStartDate, 'date')}</div>
            <div style={{ flex: 1 }}>{field('Closing date', maturity, setMaturity, 'date')}</div>
          </div>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5, marginBottom: 10, cursor: 'pointer' }}>
            <input type="checkbox" checked={manual} onChange={e => setManual(e.target.checked)} />
            Manual value – switch off auto-calculation and keep the present value I type
          </label>
          {comp === 'Y' && (
            <Field name="Interest credited so far (date, amount – one per line)">
              <textarea style={{ ...input, height: 70, resize: 'vertical' }} value={credits} placeholder="2024-05-31, 13759" onChange={e => setCredits(e.target.value)} />
            </Field>
          )}
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5, marginBottom: 10, cursor: 'pointer' }}>
            <input type="checkbox" checked={rd} onChange={e => setRd(e.target.checked)} />
            Recurring deposit – the monthly SIP is deposited from the opening date, each deposit earning interest from its own date
          </label>
          <div style={{ fontSize: 11.5, color: T.muted, margin: '-4px 0 12px' }}>
            {auto ? 'Present value is calculated from the invested amount, rate and dates (it stops growing at the closing date).' : 'Add a rate and opening date to calculate the present value automatically.'}
          </div>
        </>
      ) : canFixed && (
        <button type="button" style={{ ...btn(), padding: '4px 10px', fontSize: 12, marginBottom: 12 }} onClick={() => setFixedOpen(true)}>+ Fixed-rate return</button>
      )}
      <details open={!!(holding?.notes || holding?.tags || holding?.exposure)} style={{ marginBottom: 12 }}>
        <summary style={{ cursor: 'pointer', fontSize: 12.5, color: T.muted, marginBottom: 10 }}>Classification &amp; notes</summary>
        <Field name="Exposure">
          <select style={input} value={exposure} onChange={e => setExposure(e.target.value)}>
            <option value="">Auto</option>
            {['Equity', 'Gold', 'Debt'].map(x => <option key={x}>{x}</option>)}
          </select>
        </Field>
        <div style={hint}>What the money is really in (cash counts as Debt). Auto guesses from the type and name.</div>
        <Field name="Tags">
          <input style={input} value={tags} placeholder="e.g. Pharma" onChange={e => setTags(e.target.value)} />
        </Field>
        {allTags.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, margin: '-4px 0 10px' }}>
            {allTags.map(t => (
              <button key={t} type="button" onClick={() => toggleTag(t)} style={{
                padding: '1px 7px', borderRadius: 4, fontSize: 11, cursor: 'pointer', background: tagList.includes(t) ? T.accent : 'transparent',
                color: tagList.includes(t) ? '#fff' : T.muted, border: `1px solid ${tagList.includes(t) ? T.accent : T.border}`,
              }}>{t}</button>
            ))}
          </div>
        )}
        <div style={hint}>Extra labels such as sector or theme. Click an existing tag to reuse it.</div>
        {field('Notes', notes, setNotes, 'text')}
      </details>
      {!cash && (
        <div style={{ fontSize: 12.5, marginBottom: 14, color: pnlColor(pnl) }}>
          Gain: {signed(pnl, fmtFull)} ({(invested ? (pnl / invested) * 100 : 0).toFixed(2)}%)
        </div>
      )}
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
        {onDelete && <button style={{ ...btn(), color: T.danger, borderColor: T.dangerBorder, marginRight: 'auto' }} onClick={onDelete}>Delete</button>}
        <button style={btn()} onClick={onClose}>Cancel</button>
        <button style={{ ...btn(true), opacity: name.trim() ? 1 : 0.5 }} disabled={!name.trim()}
          onClick={() => onSave({
            name: name.trim(), ticker: type === 'EQ' || type === 'GOLD' ? ticker.trim() : '', sector: ['FD', 'PF', 'CASH'].includes(type) ? sector.trim() : holding?.sector ?? '',
            asset_type: type, notes: notes.trim(), exposure, tags: tagList.join(', '),
            grp: grp.trim(), sip_amount: cash ? 0 : n(sip), sip_day: !cash && n(sip) > 0 ? Math.min(31, Math.max(0, Math.round(n(sipDay)))) : 0, maturity: showFixed ? maturity : '', rate: showFixed ? n(rate) : 0, start_date: showFixed ? startDate : '', compounding: comp, rd: showFixed && rd ? 1 : 0, credits: showFixed && comp === 'Y' ? credits.trim() : '', manual: showFixed && manual ? 1 : 0,
            qty: direct ? 1 : n(qty), buy_price: cash ? n(b) : n(a), cmp: n(b),
          })}>Save</button>
      </div>
    </Modal>
  )
}
