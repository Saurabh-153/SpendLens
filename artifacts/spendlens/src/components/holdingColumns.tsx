import type { CSSProperties, ReactNode } from 'react'
import type { ColumnLayout, Holding } from '../api'
import { T, fmt, pnlColor, signed } from '../theme'
import { displayName, titleCase } from '../names'

// The Holdings table is drawn from COLUMNS below. To add a column, add one entry to that list: header, cell, group-row cell,
// and when it shows are all in the entry, so nothing else in the table needs touching.

export type SortKey = 'present' | 'invested' | 'pl' | 'pl_pct' | 'name'
export interface GroupTotals { name: string; items: Holding[]; invested: number; present: number; pl: number; pct: number }
interface Ctx { group: string; total: number; color?: string }

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

const pill = (c: string): CSSProperties => ({ display: 'inline-block', fontSize: 11, fontWeight: 600, padding: '2px 8px', borderRadius: 999, whiteSpace: 'nowrap', color: c, background: `color-mix(in srgb, ${c} 16%, transparent)` })

/** Gain in rupees with the return as a pill (red-toned below -25%). */
function GainCell({ pl, p }: { pl: number; p: number }) {
  return (
    <div style={{ display: 'inline-flex', flexDirection: 'column', alignItems: 'flex-end', gap: 3 }}>
      <b style={{ color: pnlColor(pl), fontWeight: 600 }}>{signed(pl)}</b>
      <span style={pill(pnlColor(p))}>{pct(p)}</span>
    </div>
  )
}

/** An amount with a thin bar and the percentage it is of the whole portfolio. */
function WithShare({ value, part, total }: { value: string; part: number; total: number }) {
  const p = total ? (part / total) * 100 : 0
  return (
    <div style={{ display: 'inline-flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4 }}>
      <span>{value}</span>
      <span style={{ width: 84, height: 4, borderRadius: 2, background: T.border, overflow: 'hidden' }}>
        <i style={{ display: 'block', width: `${Math.min(100, p * 2.5)}%`, height: '100%', background: T.accent, borderRadius: 2 }} />
      </span>
      <span style={{ ...small, color: T.muted, fontSize: 11 }}>{p.toFixed(1)}%</span>
    </div>
  )
}

/** 52-week low to high as a track: the dot is today's price, the bar is your average buy price. */
function RangeBar({ h }: { h: Holding }) {
  const span = h.week52_high - h.week52_low || 1
  const at = (v: number) => `${Math.max(0, Math.min(100, ((v - h.week52_low) / span) * 100))}%`
  const buy = buyPrice(h)
  return (
    <div style={{ width: 130, marginLeft: 'auto', textAlign: 'left' }} title={`Today ₹${money(h.cmp)}${buy != null ? ` · your average buy ₹${money(buy)}` : ''}`}>
      <div style={{ position: 'relative', height: 4, borderRadius: 2, background: T.border, margin: '8px 0 4px' }}>
        {buy != null && <b style={{ position: 'absolute', top: -4, left: at(buy), width: 4, height: 12, borderRadius: 2, background: T.text, transform: 'translateX(-2px)' }} />}
        <u style={{ position: 'absolute', top: -2, left: at(h.cmp), width: 8, height: 8, borderRadius: '50%', border: `2px solid ${T.accent}`, background: T.surface, transform: 'translateX(-4px)', textDecoration: 'none' }} />
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: T.muted }}>
        <span>{money(h.week52_low, 0)}</span><span>{money(h.week52_high, 0)}</span>
      </div>
    </div>
  )
}

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
      const soon = h.maturity && h.present > 0 && new Date(h.maturity + 'T00:00:00').getTime() - Date.now() <= 90 * 864e5
      return <><div style={{ fontWeight: 500 }} title={h.name}>{displayName(h).name}{soon && <span style={{ ...pill(T.warn), marginLeft: 8 }}>{new Date(h.maturity + 'T00:00:00').getTime() < Date.now() ? 'matured' : 'matures'} {monthYear(h.maturity)}</span>}</div>{meta && <div style={sub}>{meta}</div>}</>
    },
    groupStyle: { textAlign: 'left', fontWeight: 700 },
    groupCell: (g, c) => <>
      <span style={{ display: 'inline-block', width: 14, color: T.muted, fontSize: 10 }}>{c.expanded ? '▼' : '▶'}</span>
      {c.color && <i style={{ display: 'inline-block', width: 10, height: 10, borderRadius: 3, background: c.color, marginRight: 8 }} />}
      {g.name} <span style={{ color: T.muted, fontWeight: 400, fontSize: 12, marginLeft: 6 }}>{g.items.length} holdings</span>
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
    cell: h => h.asset_type === 'EQ' && h.week52_high > 0 && <RangeBar h={h} />,
  },
  {
    key: 'invested', wide: true, heads: [{ label: 'Amount Invested', sort: 'invested' }],
    cellStyle: () => ({ color: T.muted }), cell: h => fmt(h.invested),
    groupStyle: { color: T.muted }, groupCell: g => fmt(g.invested),
  },
  {
    key: 'value', heads: [{ label: 'Current Value', sort: 'present' }],
    cellStyle: () => ({ fontWeight: 600 }), cell: (h, c) => <WithShare value={fmt(h.present)} part={h.present} total={c.total} />,
    cellTip: (h, c) => `${c.total ? ((h.present / c.total) * 100).toFixed(1) : 0}% of portfolio`,
    groupStyle: { fontWeight: 700 }, groupCell: (g, c) => <WithShare value={fmt(g.present)} part={g.present} total={c.total} />,
  },
  {
    key: 'gain',
    heads: [{ label: 'Gain/Loss ₹', sort: 'pl', title: 'Sort by gain in ₹' }, { label: 'Return %', sort: 'pl_pct', title: 'Sort by gain in %' }],
    cell: h => h.asset_type === 'CASH' ? <span style={{ color: T.muted }}>–</span> : <GainCell pl={h.pl} p={h.pl_pct} />,
    groupCell: g => <GainCell pl={g.pl} p={g.pct} />,
  },
]
