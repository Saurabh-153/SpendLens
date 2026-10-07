import type { CSSProperties, ReactNode } from 'react'
import type { ColumnLayout, Holding } from '../api'
import { T, fmt, pnlColor, signed } from '../theme'
import { displayName, titleCase } from '../names'

// The Holdings table is drawn from COLUMNS below. To add a column, add one entry to that list: header, cell, group-row cell,
// and when it shows are all in the entry, so nothing else in the table needs touching.

export type SortKey = 'present' | 'invested' | 'pl' | 'pl_pct' | 'name'
export interface GroupTotals { name: string; items: Holding[]; invested: number; present: number; pl: number; pct: number }
interface Ctx { group: string; total: number }

export interface Column {
  key: string
  /** Header lines (stacked when more than one). `sort` makes a line clickable; `title` is its tooltip. */
  heads: { label: string; sort?: SortKey; title?: string }[]
  /** A holding's cell. */
  cell: (h: Holding, c: Ctx) => ReactNode
  cellStyle?: (h: Holding) => CSSProperties
  cellTip?: (h: Holding, c: Ctx) => string
  /** The group header row's cell; empty when left out. */
  groupCell?: (g: GroupTotals, c: Ctx & { expanded: boolean }) => ReactNode
  groupStyle?: CSSProperties
  align?: 'left'
  /** Only on wide screens (hidden on phones). */
  wide?: boolean
  /** Shown only when this is true for the rows on screen. Default: always. */
  when?: (rows: Holding[]) => boolean
  /** Always shown, and never emptied for a group (the Name column). */
  locked?: boolean
}

/** Admin's choice of columns: the saved order first, columns it has not seen yet (new in code) after, minus the hidden ones. */
export function layoutColumns(layout: ColumnLayout): Column[] {
  const rank = (c: Column) => { const i = layout.order.indexOf(c.key); return i < 0 ? layout.order.length : i }
  return COLUMNS.map((c, i) => ({ c, i })).sort((a, b) => rank(a.c) - rank(b.c) || a.i - b.i).map(x => x.c)
    .filter(c => c.locked || !layout.hidden.includes(c.key))
}
export const columnLabel = (c: Column) => c.heads.map(h => h.label).join(' / ')

export const pct = (n: number) => `${n >= 0 ? '+' : ''}${n.toFixed(1)}%`
export const monthYear = (iso: string) => new Date(iso + 'T00:00:00').toLocaleDateString('en-IN', { month: 'short', year: 'numeric' })
export const tagsOf = (h: Holding) => (h.tags || '').split(',').map(t => t.trim()).filter(Boolean)

export const td: CSSProperties = { padding: '11px 14px', textAlign: 'right', fontSize: 13, whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums' }
export const sub: CSSProperties = { fontSize: 11, color: T.muted, marginTop: 3 }
const small: CSSProperties = { fontSize: 11, fontWeight: 400 }

const ord = (d: number) => `${d}${[11, 12, 13].includes(d % 100) ? 'th' : ['th', 'st', 'nd', 'rd'][d % 10] ?? 'th'}`
// A tag the name or the group already says ("Small Cap Fund" on "Axis Small Cap Fund") adds nothing to the row.
const squash = (s: string) => s.toLowerCase().replace(/\(.*?\)/g, '').replace(/\bfund\b/g, '').replace(/[^a-z0-9]/g, '')
const shownTags = (h: Holding, group: string) => tagsOf(h).filter(t => t.toLowerCase() !== group.toLowerCase() && (!squash(t) || !squash(h.name).includes(squash(t))))
const money = (n: number, digits = 2) => n.toLocaleString('en-IN', { maximumFractionDigits: digits })

const buyPrice = (h: Holding) => (h.units_held && h.units_held > 0 ? h.invested / h.units_held : null)
// Where the average buy price sits against the stock's 52-week range: below the low is green, inside it amber, above the high red.
const buyZone = (h: Holding) => {
  const p = buyPrice(h)
  return h.asset_type !== 'EQ' || p == null || !(h.week52_high > 0) ? undefined : p < h.week52_low ? T.positive : p > h.week52_high ? T.negative : T.warn
}
const lastPrice = (h: Holding) => h.asset_type === 'MF' ? (h.nav > 0 ? `NAV ₹${money(h.nav, 4)}` : '')
  : ['EQ', 'GOLD'].includes(h.asset_type) && h.cmp > 0 ? `@ ₹${money(h.cmp)}` : ''

function holdingMeta(h: Holding, group: string) {
  const { folio } = displayName(h)
  const bank = ['FD', 'PF', 'CASH'].includes(h.asset_type) && h.sector && h.sector.toLowerCase() !== group.toLowerCase() ? titleCase(h.sector) : ''
  const showTicker = ['EQ', 'GOLD'].includes(h.asset_type) && h.ticker && !/^SGB/.test(h.ticker)
  return [showTicker ? h.ticker : '', folio, ...shownTags(h, group), bank,
    h.rate ? `${h.rate}%${!h.auto && h.manual ? ' · manual' : ''}` : '', h.maturity ? `closes ${monthYear(h.maturity)}` : '',
    h.sip_amount ? `SIP ${fmt(h.sip_amount)}${h.sip_day ? ` on ${ord(h.sip_day)}` : ''}` : '', h.notes].filter(Boolean).join(' · ')
}

export const COLUMNS: Column[] = [
  {
    key: 'name', align: 'left', locked: true, heads: [{ label: 'Name', sort: 'name' }],
    cellStyle: () => ({ textAlign: 'left', paddingLeft: 32, whiteSpace: 'normal', maxWidth: 360 }),
    cell: (h, c) => {
      const meta = holdingMeta(h, c.group)
      return <><div style={{ fontWeight: 500 }} title={h.name}>{displayName(h).name}</div>{meta && <div style={sub}>{meta}</div>}</>
    },
    groupStyle: { textAlign: 'left', fontWeight: 700 },
    groupCell: (g, c) => <>
      <span style={{ display: 'inline-block', width: 14, color: T.muted, fontSize: 10 }}>{c.expanded ? '▼' : '▶'}</span>
      {g.name} <span style={{ color: T.muted, fontWeight: 400, fontSize: 12 }}>{g.items.length} · {c.total ? ((g.present / c.total) * 100).toFixed(1) : 0}%</span>
    </>,
  },
  {
    key: 'units', heads: [{ label: 'Units Held' }],
    cellStyle: () => ({ color: T.muted }),
    cell: h => <>
      {h.units_held != null && money(h.units_held, 4)}
      {lastPrice(h) && <div style={{ ...sub, fontWeight: 400 }}>{lastPrice(h)}</div>}
    </>,
  },
  {
    key: 'buy', wide: true,
    heads: [{ label: 'Avg Buy Price', title: 'Invested ÷ units held. Stocks: green = below 52W low, amber = within range, red = above 52W high' }],
    cellStyle: h => ({ color: buyZone(h) ?? T.muted, fontWeight: buyZone(h) ? 600 : undefined }),
    cell: h => buyPrice(h) != null && `₹${money(buyPrice(h)!)}`,
  },
  {
    key: 'range', wide: true, heads: [{ label: '52W Low | High' }], when: rows => rows.some(h => h.asset_type === 'EQ'),
    cellStyle: () => ({ color: T.muted }),
    cell: h => h.asset_type === 'EQ' && h.week52_high > 0 && <>₹{money(h.week52_low)} <span style={{ opacity: 0.5 }}>|</span> {money(h.week52_high)}</>,
  },
  {
    key: 'invested', wide: true, heads: [{ label: 'Amount Invested', sort: 'invested' }],
    cellStyle: () => ({ color: T.muted }), cell: h => fmt(h.invested),
    groupStyle: { color: T.muted }, groupCell: g => fmt(g.invested),
  },
  {
    key: 'value', heads: [{ label: 'Current Value', sort: 'present' }],
    cellStyle: () => ({ fontWeight: 600 }), cell: h => fmt(h.present),
    cellTip: (h, c) => `${c.total ? ((h.present / c.total) * 100).toFixed(1) : 0}% of portfolio`,
    groupStyle: { fontWeight: 700 }, groupCell: g => fmt(g.present),
  },
  {
    key: 'gain',
    heads: [{ label: 'Gain/Loss ₹', sort: 'pl', title: 'Sort by gain in ₹' }, { label: 'Return %', sort: 'pl_pct', title: 'Sort by gain in %' }],
    cellStyle: h => ({ color: pnlColor(h.pl), fontWeight: 600 }),
    cell: h => <>{signed(h.pl)}<div style={small}>{pct(h.pl_pct)}</div></>,
    groupCell: g => <span style={{ color: pnlColor(g.pl), fontWeight: 600 }}>{signed(g.pl)}<div style={small}>{pct(g.pct)}</div></span>,
  },
]
