import { useCallback, useEffect, useMemo, useState, type CSSProperties, type ReactNode } from 'react'
import {
  addEquityEvent, deleteEquityEvent, getEquityAudit, getEquityAuditEntry, getEquityEvents, getEquityStock, getEquitySummary,
  refreshEquity, setEquityYahooSymbol, updateEquityEvent,
  type EquityAudit, type EquityEvent, type EquityEventInput, type EquityEventKind, type EquityIssue,
  type EquityStock, type EquityStockDetail, type EquitySummary,
} from '../api'
import { T, fmt, fmtFull, pnlColor, signed } from '../theme'
import { Tile } from './HoldingsKpis'
import KpiSection, { LineItem } from './KpiSection'
import { btn, Card, Field, input, label, Modal, smallBtn } from './ui'

type Tab = 'dividends' | 'stocks' | 'audit' | 'actions'
const TABS: { id: Tab; label: string }[] = [
  { id: 'dividends', label: 'Dividends' }, { id: 'stocks', label: 'Stocks' }, { id: 'audit', label: 'Audit' },
  { id: 'actions', label: 'Corporate actions' },
]
const KIND_HELP: Record<EquityEventKind, string> = {
  SPLIT: 'Face-value split: new shares for old (5:1 turns 10 shares into 50). Cost per share falls in proportion.',
  BONUS: 'Free shares: new for every old held (1:1 doubles 10 shares to 20).',
  BUYBACK: 'Shares accepted in a tender buyback, at the buyback price.',
  TRANSFER_OUT: 'Shares moved out of this demat (gift, other broker). Leave price blank to move them out at cost.',
  IPO: 'Shares allotted in an IPO, at the issue price.',
  TRANSFER_IN: 'Shares moved into this demat. Leave price blank if the cost is unknown (they are then left out of XIRR).',
  ADJUST: 'Any other correction: positive adds shares, negative removes them.',
  DEMERGER: 'The new company’s shares: new per old held, and the % of the parent’s cost that moves to it.',
  MERGER: 'This stock becomes the target: new target shares per old shares held. Cost carries over.',
  RENAME: 'The exchange renamed the symbol: history under the old name continues under the new one.',
}
const RATIO_KINDS: EquityEventKind[] = ['SPLIT', 'BONUS', 'DEMERGER', 'MERGER']
const QTY_KINDS: EquityEventKind[] = ['BUYBACK', 'TRANSFER_OUT', 'IPO', 'TRANSFER_IN', 'ADJUST', 'DEMERGER', 'MERGER']
const PRICE_KINDS: EquityEventKind[] = ['BUYBACK', 'TRANSFER_OUT', 'IPO', 'TRANSFER_IN', 'ADJUST']
const TARGET_KINDS: EquityEventKind[] = ['DEMERGER', 'MERGER', 'RENAME']
const START_FY = 'FY2023-24'

const levelColor = (l: EquityIssue['level']) => (l === 'error' ? T.negative : l === 'warning' ? T.warn : T.muted)
const pct = (v: number | null | undefined) => (v == null ? '—' : `${v.toFixed(1)}%`)
const dayBefore = (d: string) => { const x = new Date(d + 'T00:00:00Z'); x.setUTCDate(x.getUTCDate() - 1); return x.toISOString().slice(0, 10) }
const th: CSSProperties = { ...label, fontSize: 10.5, padding: '8px 10px', textAlign: 'right', fontWeight: 600, whiteSpace: 'nowrap', position: 'sticky', top: 0, background: T.surface }
const td: CSSProperties = { padding: '6px 10px', fontSize: 12.5, textAlign: 'right', whiteSpace: 'nowrap' }
const tdl: CSSProperties = { ...td, textAlign: 'left' }

function urlTab(): Tab {
  const t = new URLSearchParams(location.search).get('tab')
  return TABS.some(x => x.id === t) ? (t as Tab) : 'dividends'
}

const num = { fontVariantNumeric: 'tabular-nums' } as const
const tileSub = { fontSize: 12, color: T.muted } as const

function Meter({ pct, color, title }: { pct: number; color: string; title: string }) {
  return (
    <div title={title} style={{ height: 6, borderRadius: 3, background: T.surface2, marginTop: 6, overflow: 'hidden' }}>
      <div style={{ width: `${Math.max(0, Math.min(100, pct))}%`, height: '100%', background: color, borderRadius: 3 }} />
    </div>
  )
}

/** The KPI tiles above the tabs, in the Holdings style; "Show less" folds them into one line (remembered). */
function LedgerKpis({ sum, audit, onAudit }: { sum: EquitySummary; audit: EquityAudit | null; onAudit: () => void }) {
  const k = sum.kpis
  const ic = sum.issue_counts
  const held = sum.stocks.filter(s => s.status === 'held')
  const up = held.filter(s => (s.unrealized ?? 0) > 0).length
  const down = held.filter(s => (s.unrealized ?? 0) < 0).length
  const onCost = k.invested ? (k.unrealized / k.invested) * 100 : 0
  const last4 = sum.dividends.quarters.slice(-4)
  const trailing = last4.reduce((t, q) => t + (sum.dividends.totals_by_quarter[q] ?? 0), 0)
  const yieldPct = k.value ? (trailing / k.value) * 100 : null
  const checks = audit?.holdings_checks ?? []
  const recColor = ic.error ? T.negative : T.positive
  const pctText = (n: number) => `${n >= 0 ? '+' : '−'}${Math.abs(n).toFixed(1)}%`
  const line = (
    <>
      <LineItem label="Value">{fmt(k.value)}</LineItem>
      <LineItem label="Unrealised" color={pnlColor(k.unrealized)}>{signed(k.unrealized)} ({pctText(onCost)})</LineItem>
      <LineItem label="Realised" color={pnlColor(k.realized)}>{signed(k.realized)}</LineItem>
      <LineItem label={`Dividends ${sum.current_fy}`}>{fmt(k.dividends_fy)}</LineItem>
      {k.xirr != null && <LineItem label="XIRR">{k.xirr.toFixed(1)}%</LineItem>}
      <LineItem label="Reconciliation" color={recColor}>{ic.error ? `${ic.error} to fix` : 'all match'}</LineItem>
    </>
  )
  return (
    <KpiSection storageKey="spendlens.ledgerKpisCompact" label="Stock ledger" line={line}>
      <section aria-label="Stock ledger KPIs" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: 12 }}>
        <Tile name="Current value" value={fmt(k.value)}>
          <div style={tileSub}>Invested <b style={{ color: T.text, ...num }}>{fmt(k.invested)}</b> · {k.held_count} stocks held</div>
          <Meter pct={held.length ? (up / held.length) * 100 : 0} color={T.positive} title="Share of held stocks in profit" />
        </Tile>
        <Tile name="Unrealised gain"
          value={<span style={{ color: pnlColor(k.unrealized) }}>{signed(k.unrealized)} <span style={{ fontSize: 14, fontWeight: 600 }}>{pctText(onCost)}</span></span>}>
          <div style={tileSub}><span style={{ color: T.positive }}>{up} up</span> · <span style={{ color: T.negative }}>{down} down</span> · on cost</div>
        </Tile>
        <Tile name="Realised gains" value={<span style={{ color: pnlColor(k.realized) }}>{signed(k.realized)}</span>}>
          <div style={tileSub}>All time · {k.exited_count} stocks exited</div>
          <div style={tileSub}>FIFO lots, before brokerage and tax</div>
        </Tile>
        <Tile name={`Dividends ${sum.current_fy}`} value={fmt(k.dividends_fy)}>
          <div style={tileSub}>Last 4 quarters <b style={{ color: T.text, ...num }}>{fmt(trailing)}</b>{yieldPct != null && <> · yield <b style={{ color: T.text, ...num }}>{yieldPct.toFixed(2)}%</b></>}</div>
          <div style={tileSub}>All time <b style={{ color: T.text, ...num }}>{fmt(k.dividends_total)}</b></div>
        </Tile>
        <Tile name="Annual return (XIRR)" value={k.xirr != null ? `${k.xirr.toFixed(1)}%` : '–'}>
          <div style={tileSub}>Including dividends · price only <b style={{ color: T.text, ...num }}>{pct(k.xirr_ex_div)}</b></div>
          {k.xirr_coverage_pct != null && <>
            <div style={tileSub}>Covers {k.xirr_coverage_pct}% of current value</div>
            <Meter pct={k.xirr_coverage_pct} color={T.accent} title="Share of current value with a known cost" />
          </>}
        </Tile>
        <div onClick={onAudit} style={{ cursor: 'pointer', display: 'grid' }} title="Open the Audit tab">
          <Tile name="Reconciliation" value={<span style={{ color: recColor }}>{ic.error ? `${ic.error} to fix` : 'All match'}</span>}>
            <div style={tileSub}>{ic.warning} warnings · share counts checked against every statement</div>
            {checks.map(c => <div key={c.account} style={tileSub}>{c.account}: {c.matched}/{c.total} holdings match ({c.as_of})</div>)}
          </Tile>
        </div>
      </section>
    </KpiSection>
  )
}

function Seg<V extends string>({ value, options, onChange }: { value: V; options: { id: V; label: string }[]; onChange: (v: V) => void }) {
  return (
    <div style={{ display: 'inline-flex', border: `1px solid ${T.hairline}`, borderRadius: 8, overflow: 'hidden' }}>
      {options.map(o => (
        <button key={o.id} onClick={() => onChange(o.id)} style={{
          padding: '5px 11px', fontSize: 12.5, border: 'none', cursor: 'pointer',
          background: value === o.id ? T.accent : 'transparent', color: value === o.id ? '#fff' : T.muted, fontWeight: value === o.id ? 600 : 400,
        }}>{o.label}</button>
      ))}
    </div>
  )
}

export default function Ledger() {
  const [account, setAccount] = useState('ALL')
  const [tab, setTabState] = useState<Tab>(urlTab)
  const [sum, setSum] = useState<EquitySummary | null>(null)
  const [audit, setAudit] = useState<EquityAudit | null>(null)
  const [events, setEvents] = useState<EquityEvent[]>([])
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [editing, setEditing] = useState<{ id?: number; init: Partial<EquityEventInput> } | null>(null)
  const [detail, setDetail] = useState<string | null>(null)

  const setTab = (t: Tab) => {
    const u = new URL(location.href)
    u.searchParams.set('tab', t)
    history.replaceState(null, '', u)
    setTabState(t)
  }
  const load = useCallback(() => {
    Promise.all([getEquitySummary(account), getEquityAudit(account), getEquityEvents()])
      .then(([s, a, e]) => { setSum(s); setAudit(a); setEvents(e.events); setError('') })
      .catch(e => setError(e.message))
  }, [account])
  useEffect(load, [load])

  const refresh = () => {
    setBusy(true); setNotice('')
    refreshEquity().then(r => { setNotice(`Refresh: ${r.summary}`); load() }).catch(e => setError(e.message)).finally(() => setBusy(false))
  }
  const saveEvent = (id: number | undefined, e: EquityEventInput) =>
    (id ? updateEquityEvent(id, e) : addEquityEvent(e)).then(() => { setEditing(null); load() })

  if (!sum) return <div style={{ padding: 20, color: error ? T.negative : T.muted }}>{error || 'Loading…'}</div>
  const empty = sum.accounts.length === 0
  const lastRefresh = audit?.log.find(l => l.kind === 'refresh')

  return (
    <div style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px 14px', flexWrap: 'wrap' }}>
        <h1 style={{ fontSize: 20, fontWeight: 700 }}>Ledger</h1>
        {sum.accounts.length > 1 && (
          <Seg value={account} onChange={setAccount} options={[{ id: 'ALL', label: 'All' }, ...sum.accounts.map(a => ({ id: a, label: a }))]} />
        )}
        <div style={{ flex: 1 }} />
        <span style={{ fontSize: 11.5, color: T.muted }}>{lastRefresh ? `Refreshed ${lastRefresh.at.slice(0, 16)} UTC` : 'Not refreshed yet'}</span>
        <button style={btn()} disabled={busy || empty} onClick={refresh} title="Fetch prices, splits and dividends from Yahoo and reconcile them with your statements">
          {busy ? 'Refreshing…' : '↻ Refresh'}
        </button>
      </div>
      {error && <div style={{ color: T.negative, fontSize: 12.5 }}>{error}</div>}
      {notice && <div style={{ color: T.muted, fontSize: 12.5 }}>{notice}</div>}

      {empty ? (
        <Card style={{ padding: 24, maxWidth: 640 }}>
          <div style={{ fontWeight: 600, marginBottom: 8 }}>No broker data yet</div>
          <div style={{ fontSize: 13, color: T.muted, lineHeight: 1.6 }}>
            Put your Zerodha Console files in a folder with one sub-folder per demat account (tradebook/SK, tradebook/SS): the equity
            <b> tradebooks</b>, <b>dividend</b> statements and the <b>holdings</b> statement. Stop the backend, run{' '}
            <code>python spendlens/import_broker.py tradebook</code>, and start it again. The data is stored in SpendLens, so the files can be deleted.
          </div>
        </Card>
      ) : (
        <>
          <LedgerKpis sum={sum} audit={audit} onAudit={() => setTab('audit')} />
          <div role="tablist" style={{ display: 'flex', gap: 4, borderBottom: `1px solid ${T.border}`, overflowX: 'auto' }}>
            {TABS.map(t => (
              <button key={t.id} role="tab" aria-selected={tab === t.id} onClick={() => setTab(t.id)} style={{
                border: 'none', background: 'transparent', padding: '10px 16px', fontSize: 14, fontWeight: 600, cursor: 'pointer', whiteSpace: 'nowrap', marginBottom: -1,
                color: tab === t.id ? T.text : T.muted, borderBottom: `2px solid ${tab === t.id ? T.accent : 'transparent'}`,
              }}>
                {t.label}
                {t.id === 'audit' && sum.issue_counts.error > 0 && <span style={{ marginLeft: 6, color: T.negative, fontWeight: 700 }}>{sum.issue_counts.error}</span>}
              </button>
            ))}
          </div>
          {tab === 'dividends' && <Dividends sum={sum} />}
          {tab === 'stocks' && <Stocks sum={sum} onOpen={setDetail} onRefresh={refresh} busy={busy} refreshedAt={lastRefresh?.at ?? null} />}
          {tab === 'audit' && <Coverage sum={sum} />}
          {tab === 'audit' && audit && <AuditView audit={audit} onFix={init => setEditing({ init })} onOpen={setDetail} onReload={load} />}
          {tab === 'actions' && <Actions events={events} onEdit={(id, init) => setEditing({ id, init })} onDelete={id => deleteEquityEvent(id).then(load).catch(e => setError(e.message))} />}
        </>
      )}

      {editing && <EventDialog id={editing.id} init={editing.init} accounts={sum.accounts} onClose={() => setEditing(null)} onSave={saveEvent} />}
      {detail && <StockDialog symbol={detail} account={account} onClose={() => setDetail(null)} onFix={init => { setDetail(null); setEditing({ init }) }} />}
    </div>
  )
}

function Coverage({ sum }: { sum: EquitySummary }) {
  return (
    <Card style={{ padding: '12px 16px' }}>
      <div style={{ ...label, marginBottom: 6 }}>Data coverage</div>
      {Object.entries(sum.coverage).map(([a, c]) => (
        <div key={a} style={{ fontSize: 12.5, color: T.muted, padding: '2px 0' }}>
          <b style={{ color: T.text }}>{a}</b> · dividend statements to {c.statement_to ?? '—'} (Yahoo fills after that) · last trade {c.last_trade ?? '—'}
        </div>
      ))}
      <div style={{ fontSize: 11.5, color: T.muted, marginTop: 8, lineHeight: 1.5 }}>
        XIRR counts every buy as money out, every sale, buyback and dividend as money in, and today’s value as the last inflow.
        Brokerage and taxes are not in the tradebook, so returns are slightly higher than net. Dividends are gross (before TDS).
      </div>
    </Card>
  )
}

function Dividends({ sum }: { sum: EquitySummary }) {
  const [by, setBy] = useState<'quarter' | 'year'>('quarter')
  const [show, setShow] = useState<'all' | 'held' | 'exited'>('all')
  const [from, setFrom] = useState(() => (sum.dividends.years.includes(START_FY) ? START_FY : sum.dividends.years[0] ?? START_FY))
  const d = sum.dividends
  const cols = (by === 'quarter' ? d.quarters : d.years).filter(c => c.slice(0, 9) >= from)
  const rows = d.rows
    .filter(r => show === 'all' || r.status === show)
    .map(r => ({ ...r, sel: cols.reduce((s, c) => s + ((by === 'quarter' ? r.by_quarter : r.by_year)[c] ?? 0), 0) }))
    .filter(r => r.sel > 0)
    .sort((a, b) => b.sel - a.sel)
  const totals = by === 'quarter' ? d.totals_by_quarter : d.totals_by_year
  const shownTotal = (c: string) => rows.reduce((s, r) => s + ((by === 'quarter' ? r.by_quarter : r.by_year)[c] ?? 0), 0)
  return (
    <>
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center', marginBottom: 12 }}>
        <Seg value={by} onChange={setBy} options={[{ id: 'quarter', label: 'By quarter' }, { id: 'year', label: 'By year' }]} />
        <Seg value={show} onChange={setShow} options={[{ id: 'all', label: 'All' }, { id: 'held', label: 'Held' }, { id: 'exited', label: 'Exited' }]} />
        <label style={{ fontSize: 12.5, color: T.muted }}>From{' '}
          <select style={{ ...input, width: 'auto', padding: '4px 8px', fontSize: 12.5 }} value={from} onChange={e => setFrom(e.target.value)}>
            {d.years.map(y => <option key={y}>{y}</option>)}
          </select>
        </label>
        <span style={{ fontSize: 11.5, color: T.muted }}>Indian financial year: Q1 = Apr–Jun. <span style={{ color: T.accent }}>*</span> includes rows fetched from Yahoo.</span>
      </div>
      <Card style={{ padding: 0, overflow: 'auto', maxHeight: '70vh' }}>
        <table style={{ borderCollapse: 'collapse', width: '100%' }}>
          <thead><tr>
            <th style={{ ...th, textAlign: 'left', left: 0, zIndex: 2 }}>Stock</th>
            {cols.map(c => <th key={c} style={th}>{by === 'quarter' ? `FY${c.slice(4, 9)} ${c.slice(-2)}` : c}</th>)}
            <th style={th}>Total</th>
          </tr></thead>
          <tbody>
            {rows.map(r => {
              const vals = by === 'quarter' ? r.by_quarter : r.by_year
              return (
                <tr key={r.symbol} style={{ borderTop: `1px solid ${T.hairline}` }}>
                  <td style={{ ...tdl, position: 'sticky', left: 0, background: T.surface, fontWeight: 600 }}>
                    {r.symbol}{r.sources.includes('yahoo') && <span style={{ color: T.accent }}>*</span>}
                    {r.status === 'exited' && <span style={{ color: T.muted, fontWeight: 400, fontSize: 11 }}> · exited</span>}
                  </td>
                  {cols.map(c => <td key={c} style={{ ...td, color: vals[c] ? T.text : T.muted }}>{vals[c] ? fmtFull(vals[c]) : '·'}</td>)}
                  <td style={{ ...td, fontWeight: 600 }}>{fmtFull(r.sel)}</td>
                </tr>
              )
            })}
            {rows.length === 0 && <tr><td style={{ ...tdl, color: T.muted }} colSpan={cols.length + 2}>No dividends in this range.</td></tr>}
          </tbody>
          {rows.length > 0 && <tfoot><tr style={{ borderTop: `2px solid ${T.hairline}` }}>
            <td style={{ ...tdl, position: 'sticky', left: 0, background: T.surface, fontWeight: 700 }}>Total</td>
            {cols.map(c => <td key={c} style={{ ...td, fontWeight: 700 }} title={show === 'all' ? undefined : `All stocks: ${fmtFull(totals[c] ?? 0)}`}>{fmtFull(shownTotal(c))}</td>)}
            <td style={{ ...td, fontWeight: 700 }}>{fmtFull(rows.reduce((s, r) => s + r.sel, 0))}</td>
          </tr></tfoot>}
        </table>
      </Card>
    </>
  )
}

type StockCol = { key: string; head: string; left?: boolean; cell: (s: EquityStock) => ReactNode; title?: (s: EquityStock) => string | undefined }

function Stocks({ sum, onOpen, onRefresh, busy, refreshedAt }: {
  sum: EquitySummary; onOpen: (s: string) => void; onRefresh: () => void; busy: boolean; refreshedAt: string | null
}) {
  const [show, setShow] = useState<'held' | 'exited' | 'all'>('held')
  const rows = useMemo(() => {
    const r = sum.stocks.filter(s => show === 'all' || s.status === show)
    return r.sort((a, b) => (a.status !== b.status ? (a.status === 'held' ? -1 : 1)
      : a.status === 'held' ? (b.value ?? 0) - (a.value ?? 0) : (b.exit_date ?? '').localeCompare(a.exit_date ?? '')))
  }, [sum, show])
  const x = (s: EquityStock, v: number | null) => (v != null ? <span style={{ color: pnlColor(v) }}>{v.toFixed(1)}%</span>
    : <span style={{ color: T.muted }} title={s.xirr_note ?? 'Needs at least 30 days of history'}>—</span>)
  const dash = <span style={{ color: T.muted }}>—</span>
  const q = (v: number | null) => (v ? +v.toFixed(3) : dash)
  const C: Record<string, StockCol> = {
    stock: { key: 'stock', head: 'Stock', left: true, title: s => s.name,
      cell: s => <b>{s.symbol}{s.xirr_note && <span style={{ color: T.warn }} title={s.xirr_note}> ⚠</span>}</b> },
    qty: { key: 'qty', head: 'Qty', cell: s => q(s.qty), title: s => Object.entries(s.accounts).map(([a, n]) => `${a}: ${n}`).join(' · ') || undefined },
    avg: { key: 'avg', head: 'Avg cost', cell: s => (s.avg_cost != null ? s.avg_cost.toFixed(2) : dash) },
    invested: { key: 'invested', head: 'Invested', cell: s => (s.invested ? fmt(s.invested) : dash) },
    price: { key: 'price', head: 'Price', cell: s => <span style={{ color: T.muted }}>{s.price != null ? s.price.toFixed(2) : '—'}</span>, title: s => s.price_date || undefined },
    value: { key: 'value', head: 'Value', cell: s => (s.value ? fmt(s.value) : dash) },
    unreal: { key: 'unreal', head: 'Unrealised', cell: s => (s.unrealized != null && s.status === 'held' ? <span style={{ color: pnlColor(s.unrealized) }}>{signed(s.unrealized)}</span> : dash) },
    exitQty: { key: 'exitQty', head: 'Exit qty', cell: s => q(s.exit_qty), title: () => 'Shares sold in the closing sales, after the last purchase' },
    exitPrice: { key: 'exitPrice', head: 'Exit price', cell: s => (s.exit_price == null ? dash : <>{s.exit_price.toFixed(2)}
      {s.split_factor_since_exit != null && s.split_factor_since_exit !== 1 && s.exit_price_adj != null && <span style={{ color: T.muted, fontSize: 11 }}> ({s.exit_price_adj.toFixed(2)} adj.)</span>}</>),
      title: s => 'Average price of the closing sales, weighted by quantity' + (s.split_factor_since_exit && s.split_factor_since_exit !== 1 ? `; ${s.split_factor_since_exit}× shares after later splits, so ${s.exit_price_adj} on today’s basis` : '') },
    priceNow: { key: 'priceNow', head: 'Price now', cell: s => (s.price != null ? s.price.toFixed(2) : dash), title: s => (s.price_date ? `Yahoo close ${s.price_date}` : 'Run Refresh prices') },
    sinceExit: { key: 'sinceExit', head: 'Since exit', cell: s => (s.change_since_exit_pct == null ? dash
      : <span style={{ color: pnlColor(s.change_since_exit_pct), fontWeight: 600 }}>{s.change_since_exit_pct > 0 ? '+' : ''}{s.change_since_exit_pct.toFixed(1)}%</span>),
      title: () => 'Today’s price against the exit price (adjusted for later splits)' },
    valueNow: { key: 'valueNow', head: 'Value now', cell: s => (s.exit_value_now == null ? dash : <>{fmt(s.exit_value_now)}
      {s.exit_value != null && <span style={{ color: pnlColor(s.exit_value_now - s.exit_value), fontSize: 11 }}> {signed(s.exit_value_now - s.exit_value)}</span>}</>),
      title: () => 'The exit shares at today’s price, and the difference from what the sale brought in' },
    exitValue: { key: 'exitValue', head: 'Exit value', cell: s => (s.exit_value ? fmt(s.exit_value) : dash) },
    sold: { key: 'sold', head: 'Sold (all time)', cell: s => (s.sold_qty ? <>{+s.sold_qty.toFixed(3)} <span style={{ color: T.muted }}>· {fmt(s.sale_value)}</span></> : dash), title: () => 'Every sale and buyback, as traded (counts before a split are not adjusted)' },
    realized: { key: 'realized', head: 'Realised', cell: s => (s.realized ? <span style={{ color: pnlColor(s.realized) }}>{signed(s.realized)}</span> : dash) },
    divs: { key: 'divs', head: 'Dividends', cell: s => (s.dividends ? <span style={{ color: T.positive }}>{fmtFull(s.dividends)}</span> : dash) },
    xirr: { key: 'xirr', head: 'XIRR', cell: s => <b>{x(s, s.xirr)}</b> },
    xex: { key: 'xex', head: 'Price only', cell: s => x(s, s.xirr_ex_div) },
    since: { key: 'since', head: 'Since', cell: s => <span style={{ color: T.muted }}>{s.first_date ?? '—'}</span> },
    exited: { key: 'exited', head: 'Exited', cell: s => <span style={{ color: T.muted }}>{s.exit_date ?? ''}</span> },
  }
  const layout = {
    held: ['stock', 'qty', 'avg', 'invested', 'price', 'value', 'unreal', 'realized', 'divs', 'xirr', 'xex', 'sold', 'since'],
    exited: ['stock', 'since', 'exited', 'exitQty', 'exitPrice', 'priceNow', 'sinceExit', 'exitValue', 'valueNow', 'realized', 'divs', 'xirr', 'xex', 'sold'],
    all: ['stock', 'qty', 'avg', 'invested', 'value', 'unreal', 'exitQty', 'exitPrice', 'exitValue', 'realized', 'divs', 'xirr', 'xex', 'since', 'exited'],
  }[show]
  const cols = layout.map(k => C[k])
  return (
    <>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 12, flexWrap: 'wrap' }}>
        <Seg value={show} onChange={setShow} options={[{ id: 'held', label: `Held (${sum.kpis.held_count})` }, { id: 'exited', label: `Exited (${sum.kpis.exited_count})` }, { id: 'all', label: 'All' }]} />
        {show !== 'held' && (
          <button style={{ ...btn(), padding: '5px 11px', fontSize: 12.5, opacity: busy ? 0.6 : 1 }} disabled={busy} onClick={onRefresh}
            title="Fetch today’s prices (and splits, dividends) from Yahoo">{busy ? 'Refreshing…' : '↻ Refresh prices'}</button>
        )}
        {show !== 'held' && refreshedAt && <span style={{ fontSize: 11.5, color: T.muted }}>prices {refreshedAt.slice(0, 16)} UTC</span>}
        <span style={{ fontSize: 11.5, color: T.muted }}>
          Click a stock for its full history. Exit = the closing sales after the last purchase (price is their average). XIRR “price only” leaves dividends out.
        </span>
      </div>
      <Card style={{ padding: 0, overflow: 'auto', maxHeight: '70vh' }}>
        <table style={{ borderCollapse: 'collapse', width: '100%' }}>
          <thead><tr>{cols.map(c => <th key={c.key} style={c.left ? { ...th, textAlign: 'left' } : th}>{c.head}</th>)}</tr></thead>
          <tbody>
            {rows.map(s => (
              <tr key={s.symbol} onClick={() => onOpen(s.symbol)} style={{ borderTop: `1px solid ${T.hairline}`, cursor: 'pointer' }}>
                {cols.map(c => <td key={c.key} style={c.left ? tdl : td} title={c.title?.(s)}>{c.cell(s)}</td>)}
              </tr>
            ))}
            {rows.length === 0 && <tr><td style={{ ...tdl, color: T.muted }} colSpan={cols.length}>No stocks here.</td></tr>}
          </tbody>
          {show === 'exited' && rows.length > 0 && (
            <tfoot><tr style={{ borderTop: `2px solid ${T.hairline}` }}>
              {cols.map(c => {
                const total = c.key === 'exitValue' ? rows.reduce((t, s) => t + (s.exit_value ?? 0), 0)
                  : c.key === 'valueNow' ? rows.reduce((t, s) => t + (s.exit_value_now ?? 0), 0)
                  : c.key === 'realized' ? rows.reduce((t, s) => t + s.realized, 0)
                  : c.key === 'divs' ? rows.reduce((t, s) => t + s.dividends, 0) : null
                return <td key={c.key} style={{ ...(c.left ? tdl : td), fontWeight: 700 }}>
                  {c.key === 'stock' ? 'Total' : total == null ? '' : c.key === 'realized' ? <span style={{ color: pnlColor(total) }}>{signed(total)}</span> : fmt(total)}
                </td>
              })}
            </tr></tfoot>
          )}
        </table>
      </Card>
    </>
  )
}

function fixFor(i: EquityIssue): Partial<EquityEventInput> | null {
  const base = { account: i.account, symbol: i.symbol }
  const d = i.delta ?? 0
  if (i.kind === 'oversold') return { ...base, kind: 'IPO', qty: d, ex_date: dayBefore(i.date), note: 'shares the tradebook does not show' }
  if (i.kind === 'qty_mismatch' || i.kind === 'holding_mismatch') {
    if (d > 0) return { ...base, kind: i.replay ? 'ADJUST' : 'TRANSFER_IN', qty: d, ex_date: dayBefore(i.date) }
    if (d < 0) return { ...base, kind: 'BUYBACK', qty: -d, ex_date: dayBefore(i.date) }
  }
  return null
}

function AuditView({ audit, onFix, onOpen, onReload }: { audit: EquityAudit; onFix: (e: Partial<EquityEventInput>) => void; onOpen: (s: string) => void; onReload: () => void }) {
  const [level, setLevel] = useState<'error' | 'warning' | 'info' | 'all'>(() => (audit.issues.some(i => i.level === 'error') ? 'error' : 'all'))
  const [entry, setEntry] = useState<{ title: string; body: unknown } | null>(null)
  const list = audit.issues.filter(i => level === 'all' || i.level === level)
  const setYahoo = (sym: string) => {
    const y = prompt(`Yahoo symbol for ${sym} (e.g. ${sym}.NS, or the new name if it was renamed)`, `${sym}.NS`)
    if (y != null) setEquityYahooSymbol(sym, y).then(onReload)
  }
  return (
    <>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap', marginBottom: 12 }}>
        <Seg value={level} onChange={setLevel} options={[
          { id: 'error', label: `Errors (${audit.issues.filter(i => i.level === 'error').length})` },
          { id: 'warning', label: `Warnings (${audit.issues.filter(i => i.level === 'warning').length})` },
          { id: 'info', label: 'Info' }, { id: 'all', label: 'All' }]} />
        {audit.holdings_checks.map(c => (
          <span key={c.account} style={{ fontSize: 12, color: c.matched === c.total ? T.positive : T.negative }}>
            {c.account}: {c.matched}/{c.total} holdings match the statement of {c.as_of}
          </span>
        ))}
      </div>
      <Card style={{ padding: 0, marginBottom: 18 }}>
        {list.length === 0 && <div style={{ padding: 14, fontSize: 13, color: T.positive }}>Nothing here: every share count the statements show is explained by the history.</div>}
        {list.map((i, n) => {
          const fix = fixFor(i)
          return (
            <div key={n} style={{ display: 'flex', gap: 10, padding: '9px 14px', borderTop: n ? `1px solid ${T.hairline}` : 'none', alignItems: 'flex-start', flexWrap: 'wrap' }}>
              <span style={{ width: 8, height: 8, borderRadius: 4, background: levelColor(i.level), marginTop: 6, flexShrink: 0 }} />
              <div style={{ flex: 1, minWidth: 220 }}>
                <div style={{ fontSize: 13 }}>
                  {i.account && <b>{i.account} · </b>}
                  {i.symbol && <a onClick={() => onOpen(i.symbol)} style={{ color: T.accent, cursor: 'pointer', fontWeight: 600 }}>{i.symbol}</a>} {i.message}
                </div>
                {i.hint && <div style={{ fontSize: 12, color: T.muted, marginTop: 2 }}>{i.hint}</div>}
              </div>
              {fix && <button style={smallBtn} onClick={() => onFix(fix)}>Fix…</button>}
              {i.kind === 'cost_unknown' && <button style={smallBtn} onClick={() => onOpen(i.symbol)}>Show events</button>}
              {i.kind === 'no_price' && <button style={smallBtn} onClick={() => setYahoo(i.symbol)}>Set Yahoo symbol</button>}
            </div>
          )
        })}
      </Card>
      <div style={{ ...label, marginBottom: 6 }}>History of imports, refreshes and edits</div>
      <Card style={{ padding: 0, overflow: 'auto', maxHeight: 420 }}>
        <table style={{ borderCollapse: 'collapse', width: '100%' }}>
          <thead><tr><th style={{ ...th, textAlign: 'left' }}>When (UTC)</th><th style={{ ...th, textAlign: 'left' }}>What</th><th style={{ ...th, textAlign: 'left' }}>Account</th><th style={{ ...th, textAlign: 'left' }}>File / period</th><th style={{ ...th, textAlign: 'left' }}>Result</th></tr></thead>
          <tbody>
            {audit.log.map(l => (
              <tr key={l.id} style={{ borderTop: `1px solid ${T.hairline}`, cursor: 'pointer' }}
                onClick={() => getEquityAuditEntry(l.id).then(e => setEntry({ title: `${e.kind} · ${e.at}`, body: e.detail }))}>
                <td style={{ ...tdl, color: T.muted }}>{l.at.slice(0, 16)}</td>
                <td style={tdl}>{l.kind}</td>
                <td style={tdl}>{l.account}</td>
                <td style={{ ...tdl, color: T.muted }}>{l.file_name}{l.period_from ? ` (${l.period_from} → ${l.period_to})` : ''}</td>
                <td style={{ ...tdl, whiteSpace: 'normal' }}>{l.summary}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      {entry && (
        <Modal title={entry.title} onClose={() => setEntry(null)}>
          <pre style={{ fontSize: 11.5, maxHeight: '60vh', overflow: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{JSON.stringify(entry.body, null, 1)}</pre>
        </Modal>
      )}
    </>
  )
}

function eventText(e: EquityEvent) {
  if (RATIO_KINDS.includes(e.kind) && e.ratio_new) return `${e.ratio_new}:${e.ratio_old}${e.target_symbol ? ` → ${e.target_symbol}` : ''}${e.kind === 'DEMERGER' ? ` · ${e.cost_pct}% of cost` : ''}`
  if (e.kind === 'RENAME') return `→ ${e.target_symbol}`
  return `${e.qty} sh${e.price != null ? ` @ ₹${e.price}` : ' · cost unknown'}`
}

function Actions({ events, onEdit, onDelete }: { events: EquityEvent[]; onEdit: (id: number | undefined, init: Partial<EquityEventInput>) => void; onDelete: (id: number) => void }) {
  const [q, setQ] = useState('')
  const list = events.filter(e => !q || e.symbol.includes(q.toUpperCase()) || e.target_symbol.includes(q.toUpperCase()))
    .sort((a, b) => b.ex_date.localeCompare(a.ex_date))
  return (
    <>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 12, flexWrap: 'wrap' }}>
        <input style={{ ...input, width: 180 }} placeholder="Filter by symbol" value={q} onChange={e => setQ(e.target.value)} />
        <div style={{ flex: 1 }} />
        <button style={btn(true)} onClick={() => onEdit(undefined, {})}>+ Add action</button>
      </div>
      <div style={{ fontSize: 12, color: T.muted, marginBottom: 10, maxWidth: 820 }}>
        Things that change a share count outside the tradebook. Refresh adds splits from Yahoo; built-in ones cover what Yahoo misses.
        An action with no account applies to every account that held the stock.
      </div>
      <Card style={{ padding: 0, overflow: 'auto' }}>
        <table style={{ borderCollapse: 'collapse', width: '100%' }}>
          <thead><tr>{['Date', 'Type', 'Stock', 'Account', 'Detail', 'Note', 'Source', ''].map(h => <th key={h} style={{ ...th, textAlign: 'left' }}>{h}</th>)}</tr></thead>
          <tbody>
            {list.map(e => (
              <tr key={e.id} style={{ borderTop: `1px solid ${T.hairline}` }}>
                <td style={tdl}>{e.ex_date}</td>
                <td style={{ ...tdl, fontWeight: 600, fontSize: 11.5 }}>{e.kind}</td>
                <td style={tdl}>{e.symbol}</td>
                <td style={tdl}>{e.account || 'all'}</td>
                <td style={tdl}>{eventText(e)}</td>
                <td style={{ ...tdl, color: T.muted, whiteSpace: 'normal', maxWidth: 320 }}>{e.note}</td>
                <td style={{ ...tdl, color: T.muted }}>{e.source}</td>
                <td style={tdl}>
                  {e.source !== 'builtin' && <>
                    <button style={{ ...smallBtn, marginRight: 6 }} onClick={() => onEdit(e.id, e)}>Edit</button>
                    <button style={smallBtn} onClick={() => { if (confirm(`Delete ${e.kind} ${e.symbol} ${e.ex_date}?`)) onDelete(e.id) }}>Delete</button>
                  </>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </>
  )
}

function EventDialog({ id, init, accounts, onClose, onSave }: {
  id?: number; init: Partial<EquityEventInput>; accounts: string[]; onClose: () => void; onSave: (id: number | undefined, e: EquityEventInput) => Promise<void>
}) {
  const [e, setE] = useState<EquityEventInput>({
    account: '', symbol: '', ex_date: '', kind: 'SPLIT', ratio_new: 0, ratio_old: 0, qty: 0, price: null, target_symbol: '', cost_pct: 0, note: '', ...init,
  })
  const [err, setErr] = useState('')
  const set = (p: Partial<EquityEventInput>) => setE({ ...e, ...p })
  const num = (v: string) => (v === '' ? 0 : Number(v))
  return (
    <Modal title={id ? 'Edit corporate action' : 'Add corporate action'} onClose={onClose}>
      <Field name="Type">
        <select style={input} value={e.kind} onChange={x => set({ kind: x.target.value as EquityEventKind })}>
          {(Object.keys(KIND_HELP) as EquityEventKind[]).map(k => <option key={k} value={k}>{k.replace('_', ' ').toLowerCase()}</option>)}
        </select>
      </Field>
      <div style={{ fontSize: 12, color: T.muted, margin: '-4px 0 10px' }}>{KIND_HELP[e.kind]}</div>
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        <Field name="Stock symbol"><input style={input} value={e.symbol} onChange={x => set({ symbol: x.target.value.toUpperCase() })} /></Field>
        <Field name="Ex / effective date"><input style={input} type="date" value={e.ex_date} onChange={x => set({ ex_date: x.target.value })} /></Field>
        <Field name="Account">
          <select style={input} value={e.account} onChange={x => set({ account: x.target.value })}>
            <option value="">All accounts</option>{accounts.map(a => <option key={a}>{a}</option>)}
          </select>
        </Field>
      </div>
      {RATIO_KINDS.includes(e.kind) && (
        <div style={{ display: 'flex', gap: 10 }}>
          <Field name="New"><input style={input} type="number" value={e.ratio_new || ''} onChange={x => set({ ratio_new: num(x.target.value) })} /></Field>
          <Field name="for old"><input style={input} type="number" value={e.ratio_old || ''} onChange={x => set({ ratio_old: num(x.target.value) })} /></Field>
        </div>
      )}
      {TARGET_KINDS.includes(e.kind) && <Field name="New / target symbol"><input style={input} value={e.target_symbol} onChange={x => set({ target_symbol: x.target.value.toUpperCase() })} /></Field>}
      {e.kind === 'DEMERGER' && <Field name="% of parent cost moving to the new company"><input style={input} type="number" value={e.cost_pct || ''} onChange={x => set({ cost_pct: num(x.target.value) })} /></Field>}
      {QTY_KINDS.includes(e.kind) && (
        <div style={{ display: 'flex', gap: 10 }}>
          <Field name={RATIO_KINDS.includes(e.kind) ? 'Shares received (blank = from ratio)' : 'Shares'}><input style={input} type="number" value={e.qty || ''} onChange={x => set({ qty: num(x.target.value) })} /></Field>
          {PRICE_KINDS.includes(e.kind) && <Field name="Price per share (blank = unknown)"><input style={input} type="number" value={e.price ?? ''} onChange={x => set({ price: x.target.value === '' ? null : Number(x.target.value) })} /></Field>}
        </div>
      )}
      <Field name="Note"><input style={input} value={e.note} onChange={x => set({ note: x.target.value })} /></Field>
      {err && <div style={{ color: T.negative, fontSize: 12.5, marginBottom: 8 }}>{err}</div>}
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
        <button style={btn()} onClick={onClose}>Cancel</button>
        <button style={btn(true)} onClick={() => onSave(id, e).catch(x => setErr(x.message))}>Save</button>
      </div>
    </Modal>
  )
}

function StockDialog({ symbol, account, onClose, onFix }: { symbol: string; account: string; onClose: () => void; onFix: (e: Partial<EquityEventInput>) => void }) {
  const [d, setD] = useState<EquityStockDetail | null>(null)
  const [err, setErr] = useState('')
  useEffect(() => { getEquityStock(symbol, account).then(setD).catch(e => setErr(e.message)) }, [symbol, account])
  return (
    <Modal title={symbol} onClose={onClose}>
      {!d ? <div style={{ color: err ? T.negative : T.muted }}>{err || 'Loading…'}</div> : (
        <div style={{ maxHeight: '70vh', overflow: 'auto' }}>
          <div style={{ display: 'flex', alignItems: 'center', marginBottom: 6 }}>
            <div style={{ ...label, flex: 1 }}>Trades and actions</div>
            <button style={smallBtn} onClick={() => onFix({ symbol })}>+ Action</button>
          </div>
          <table style={{ borderCollapse: 'collapse', width: '100%', marginBottom: 14 }}>
            <thead><tr>{['Date', 'Acct', 'What', 'Qty', 'Price', 'Holding'].map(h => <th key={h} style={{ ...th, position: 'static' }}>{h}</th>)}</tr></thead>
            <tbody>
              {d.timeline.map((t, i) => (
                <tr key={i} style={{ borderTop: `1px solid ${T.hairline}` }} title={t.note}>
                  <td style={tdl}>{t.date}</td><td style={td}>{t.account}</td>
                  <td style={{ ...td, color: t.kind === 'BUY' ? T.accent : t.kind === 'SELL' ? T.warn : T.muted }}>{t.kind}{t.note ? ' ·' : ''}</td>
                  <td style={td}>{(q => (q > 0 ? '+' : q < 0 ? '-' : '') + +Math.abs(q).toFixed(3))(t.kind === 'SELL' ? -t.qty : t.qty)}</td>
                  <td style={td}>{t.price != null ? t.price.toFixed(2) : ''}</td>
                  <td style={{ ...td, fontWeight: 600 }}>{+t.qty_after.toFixed(3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div style={{ ...label, marginBottom: 6 }}>Dividends</div>
          <table style={{ borderCollapse: 'collapse', width: '100%' }}>
            <thead><tr>{['Ex-date', 'Acct', 'Shares', '₹/share', 'Amount', 'Source'].map(h => <th key={h} style={{ ...th, position: 'static' }}>{h}</th>)}</tr></thead>
            <tbody>
              {d.dividends.map((x, i) => (
                <tr key={i} style={{ borderTop: `1px solid ${T.hairline}` }}>
                  <td style={tdl}>{x.date}</td><td style={td}>{x.account}</td><td style={td}>{x.qty}</td><td style={td}>{x.dps}</td>
                  <td style={{ ...td, fontWeight: 600 }}>{fmtFull(x.amount)}</td><td style={{ ...td, color: T.muted }}>{x.source}</td>
                </tr>
              ))}
              {d.dividends.length === 0 && <tr><td style={{ ...tdl, color: T.muted }} colSpan={6}>None.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </Modal>
  )
}
