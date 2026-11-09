import { useEffect, useMemo, useState, type CSSProperties } from 'react'
import { getHoldings, getMfAnalysis, mfReportPdfUrl, type MfAnalysisData, type MfAnomalyRow, type MfChange, type MfMove, type MfMoves, type MfPositionStatus, type MfReport, type MfTrends } from '../api'
import { ANOMALY_RULES, METRIC, METRICS, SCORED, grade, scoreOf, type Grade, type MetricGroup } from '../mfMetrics'
import { aggregateMoves, mergeFolios, sampleAnomalies, sampleCoverage, sampleFunds, sampleOverlap, sampleTrends, type Series } from '../mfSample'
import { T, fmt } from '../theme'
import { Tile } from './HoldingsKpis'
import KpiSection, { LineItem } from './KpiSection'
import { Card, label } from './ui'

/** MF Analysis: your mutual funds month by month from the AMC factsheets that Claude Code reads (`/mf-factsheets`).
 *  With factsheets imported, everything here is real; before that the fund list is your Holdings and the numbers are
 *  sample data (mfSample.ts). A fund held in several folios is shown once. */

type Tab = 'scorecard' | 'buying' | 'trends' | 'anomalies' | 'overlap' | 'crosscheck' | 'parameters'
const TABS: { id: Tab; label: string }[] = [
  { id: 'scorecard', label: 'Scorecard' }, { id: 'buying', label: 'Factsheet analysis' }, { id: 'trends', label: 'Trends' },
  { id: 'anomalies', label: 'Anomalies' }, { id: 'overlap', label: 'Overlap' }, { id: 'crosscheck', label: 'Morningstar check' },
  { id: 'parameters', label: 'Parameters' },
]
const GRADE_COLOR: Record<Grade, string> = { good: T.positive, ok: T.warn, bad: T.negative }
const SEV_COLOR = { high: T.negative, medium: T.warn, low: T.muted }
const STATUS: Record<MfPositionStatus, { label: string; color: string }> = {
  new: { label: 'New position', color: T.positive }, added: { label: 'Added', color: T.positive },
  trimmed: { label: 'Trimmed', color: T.warn }, exited: { label: 'Exited', color: T.negative }, held: { label: 'Unchanged', color: T.muted },
}
const num = { fontVariantNumeric: 'tabular-nums' } as const
const sub = { fontSize: 12, color: T.muted } as const
const th: CSSProperties = { ...label, fontSize: 10.5, padding: '8px 10px', textAlign: 'right', fontWeight: 600, whiteSpace: 'nowrap', position: 'sticky', top: 0, background: T.surface }
const td: CSSProperties = { padding: '6px 10px', fontSize: 12.5, textAlign: 'right', whiteSpace: 'nowrap', ...num }
const tdl: CSSProperties = { ...td, textAlign: 'left' }
const monthName = (m: string) => new Date(`${m}-01T00:00:00`).toLocaleDateString('en-IN', { month: 'short', year: 'numeric' })
const shortName = (s: string, n = 3) => s.split(' ').slice(0, n).join(' ')
/** "Parag Parikh Flexi Cap Fund (Folio: 1)" -> "Parag Parikh Flexi Cap": the words that tell funds apart. */
const fundLabel = (s: string) => s.replace(/\(.*?\)/g, ' ').replace(/\b(fund|direct|regular|plan|growth|option|idcw)\b/gi, ' ').replace(/\s+/g, ' ').trim() || s

/** One fund as every tab sees it, whether it came from the factsheets or from the sample generator. */
interface ViewFund {
  name: string; amc: string; category: string; value: number; held: boolean
  latest: Record<string, number | null>
  series: Record<Series, { month: string; value: number }[]>
  manager: string; managerYears: number | null
  capMix: { large: number | null; mid: number | null; small: number | null }
  score: number | null; trends: MfTrends; latestMonth: string | null; asOn: string
  reports: MfReport[]
}
interface View {
  real: boolean; funds: ViewFund[]; anomalies: MfAnomalyRow[]; overlap: MfAnalysisData['overlap']
  coverage: MfAnalysisData['coverage']; moves: MfMoves; latestMonth: string | null
  unmatched: MfAnalysisData['unmatched_holdings']; sources: MfAnalysisData['sources']
}

function realView(d: MfAnalysisData, showAll: boolean): View {
  const funds = d.funds.filter(f => showAll || f.held || !d.funds.some(x => x.held)).map(f => ({
    name: f.name, amc: f.amc, category: f.category || '—', value: f.value, held: f.held, latest: f.latest, series: f.series,
    manager: f.manager, managerYears: f.manager_years, capMix: f.cap_mix, score: scoreOf(f.latest), trends: f.trends,
    latestMonth: f.latest_month, asOn: f.as_on, reports: f.reports ?? [],
  }))
  return { real: true, funds, anomalies: d.anomalies.filter(a => funds.some(f => f.name === a.fund)), overlap: d.overlap,
    coverage: d.coverage, moves: d.market_moves, latestMonth: d.latest_month, unmatched: d.unmatched_holdings, sources: d.sources }
}

function sampleView(held: { name: string; value: number }[]): View {
  const raw = sampleFunds(mergeFolios(held))
  const funds: ViewFund[] = raw.map(f => ({
    name: f.name, amc: f.amc, category: f.category, value: f.value, held: true, latest: f.latest,
    series: Object.fromEntries(Object.entries(f.series).map(([k, v]) => [k, v.map((value, i) => ({ month: f.months[i], value }))])) as ViewFund['series'],
    manager: f.manager, managerYears: f.managerYears, capMix: f.capMix, score: f.score, trends: sampleTrends(f), latestMonth: f.months[f.months.length - 1], asOn: '', reports: [],
  }))
  return { real: false, funds, anomalies: sampleAnomalies(raw), overlap: sampleOverlap(raw), coverage: sampleCoverage(raw),
    moves: aggregateMoves(funds), latestMonth: raw[0]?.months[raw[0].months.length - 1] ?? null, unmatched: [], sources: [] }
}

function urlTab(): Tab {
  const t = new URLSearchParams(location.search).get('tab')
  return TABS.some(x => x.id === t) ? (t as Tab) : 'scorecard'
}

function fmtMetric(key: string, v: number | null | undefined) {
  if (v == null) return '—'
  const u = METRIC[key]?.unit
  if (u === '₹cr') return `₹${Math.round(v).toLocaleString('en-IN')} cr`
  if (u === '%') return `${v.toFixed(Math.abs(v) >= 100 ? 0 : 1)}%`
  if (u === 'pp') return `${v > 0 ? '+' : ''}${v.toFixed(1)} pp`
  if (u === 'x') return v.toFixed(2)
  if (u === 'yrs') return `${v.toFixed(1)} y`
  return String(v)
}
const shares = (q: number | null) => (q == null ? '—' : q >= 1e7 ? `${(q / 1e7).toFixed(2)} cr` : q >= 1e5 ? `${(q / 1e5).toFixed(2)} L` : Math.round(q).toLocaleString('en-IN'))

function Spark({ points, color = T.accent, h = 42 }: { points: number[]; color?: string; h?: number }) {
  if (points.length < 2) return <div style={{ ...sub, height: h, display: 'flex', alignItems: 'center' }}>Needs two factsheets</div>
  const W = 220
  const lo = Math.min(...points), hi = Math.max(...points)
  const x = (i: number) => (i / (points.length - 1)) * (W - 6) + 3
  const y = (v: number) => 5 + (1 - (v - lo) / (hi - lo || 1)) * (h - 10)
  const d = points.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p).toFixed(1)}`).join('')
  return (
    <svg viewBox={`0 0 ${W} ${h}`} preserveAspectRatio="none" role="img" style={{ display: 'block', width: '100%', height: h }}>
      <path d={`${d}L${x(points.length - 1)},${h}L${x(0)},${h}Z`} fill={color} opacity="0.12" />
      <path d={d} fill="none" stroke={color} strokeWidth="2" vectorEffect="non-scaling-stroke" />
      <circle cx={x(points.length - 1)} cy={y(points[points.length - 1])} r="3" fill={color} />
    </svg>
  )
}

function Seg<V extends string>({ value, options, onChange }: { value: V; options: { id: V; label: string }[]; onChange: (v: V) => void }) {
  return (
    <div style={{ display: 'inline-flex', border: `1px solid ${T.hairline}`, borderRadius: 8, overflow: 'hidden', flexWrap: 'wrap' }}>
      {options.map(o => (
        <button key={o.id} onClick={() => onChange(o.id)} style={{
          padding: '5px 11px', fontSize: 12.5, border: 'none', cursor: 'pointer',
          background: value === o.id ? T.accent : 'transparent', color: value === o.id ? '#fff' : T.muted, fontWeight: value === o.id ? 600 : 400,
        }}>{o.label}</button>
      ))}
    </div>
  )
}

const select: CSSProperties = { padding: '6px 10px', borderRadius: 8, border: `1px solid ${T.border}`, background: T.surface, color: T.text, fontSize: 13, maxWidth: '100%' }

export default function MfAnalysis() {
  const [tab, setTabState] = useState<Tab>(urlTab)
  const [held, setHeld] = useState<{ name: string; value: number }[] | null>(null)
  const [data, setData] = useState<MfAnalysisData | null>(null)
  const [showAll, setShowAll] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    getMfAnalysis().then(setData).catch(e => setError(e.message))
    getHoldings().then(h => setHeld(h.filter(x => x.asset_type === 'MF' && x.present > 0).map(x => ({ name: x.name, value: x.present }))))
      .catch(e => { setError(e.message); setHeld([]) })
  }, [])
  const view = useMemo(() => (data?.has_data ? realView(data, showAll) : held ? sampleView(held) : null), [data, held, showAll])
  const setTab = (t: Tab) => {
    const u = new URL(location.href)
    u.searchParams.set('tab', t)
    history.replaceState(null, '', u)
    setTabState(t)
  }
  if (!view) return <div style={{ padding: 20, color: error ? T.negative : T.muted }}>{error || 'Loading…'}</div>
  const others = data?.has_data ? data.funds.filter(f => !f.held).length : 0

  return (
    <div style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px 14px', flexWrap: 'wrap' }}>
        <h1 style={{ fontSize: 20, fontWeight: 700 }}>MF Analysis</h1>
        {view.real ? (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12, color: T.muted, border: `1px solid ${T.border}`, background: T.surface, borderRadius: 999, padding: '4px 10px' }}>
            <i style={{ width: 7, height: 7, borderRadius: '50%', background: T.positive }} />
            factsheets to {view.latestMonth ? monthName(view.latestMonth) : '—'} · {view.sources.length} files
          </span>
        ) : (
          <span title="The fund list is your Holdings; the numbers are sample data until factsheets are read"
            style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12, color: T.warn, border: `1px solid ${T.warn}66`, background: `${T.warn}14`, borderRadius: 999, padding: '4px 10px', fontWeight: 600 }}>
            Preview · sample data
          </span>
        )}
        <div style={{ flex: 1 }} />
        {error && <span style={{ color: T.negative, fontSize: 12 }}>{error}</span>}
        {others > 0 && (
          <label style={{ fontSize: 12.5, color: T.muted, display: 'inline-flex', gap: 6, alignItems: 'center', cursor: 'pointer' }}>
            <input type="checkbox" checked={showAll} onChange={e => setShowAll(e.target.checked)} />
            also show {others} other funds in the factsheets
          </label>
        )}
      </div>
      {!view.real && (
        <div style={sub}>
          To fill this with real numbers, keep the factsheets and portfolio disclosures in <code>fund_fact_sheet/</code> and run
          {' '}<code>/mf-factsheets</code> in Claude Code.{held && held.length === 0 ? ' No mutual funds in Holdings yet, so four example funds are shown.' : ''}
        </div>
      )}
      {view.real && view.unmatched.length > 0 && (
        <div style={sub}>Not in any factsheet yet: {view.unmatched.map(u => u.name).join(' · ')}</div>
      )}

      <Kpis view={view} />

      <div role="tablist" style={{ display: 'flex', gap: 4, borderBottom: `1px solid ${T.border}`, overflowX: 'auto' }}>
        {TABS.map(t => (
          <button key={t.id} role="tab" aria-selected={tab === t.id} onClick={() => setTab(t.id)} style={{
            border: 'none', background: 'transparent', padding: '10px 16px', fontSize: 14, fontWeight: 600, cursor: 'pointer', whiteSpace: 'nowrap', marginBottom: -1,
            color: tab === t.id ? T.text : T.muted, borderBottom: `2px solid ${tab === t.id ? T.accent : 'transparent'}`,
          }}>
            {t.label}{t.id === 'anomalies' && view.anomalies.length > 0 && <span style={{ marginLeft: 6, color: T.warn }}>{view.anomalies.length}</span>}
          </button>
        ))}
      </div>

      {tab === 'scorecard' && <Scorecard funds={view.funds} />}
      {tab === 'buying' && <Buying view={view} />}
      {tab === 'trends' && <Trends funds={view.funds} />}
      {tab === 'anomalies' && <Anomalies list={view.anomalies} />}
      {tab === 'overlap' && <Overlap funds={view.funds} pairs={view.overlap} />}
      {tab === 'crosscheck' && <CrossCheck funds={view.funds} real={view.real} />}
      {tab === 'parameters' && <Parameters />}
    </div>
  )
}

function Kpis({ view }: { view: View }) {
  const funds = view.funds
  const total = funds.reduce((s, f) => s + f.value, 0)
  const ter = total ? funds.reduce((s, f) => s + f.value * (f.latest.ter ?? 0), 0) / total : 0
  const scored = funds.filter(f => f.score != null)
  const weakest = scored.length ? scored.reduce((a, b) => ((b.score ?? 0) < (a.score ?? 0) ? b : a)) : null
  const overlapAvg = view.overlap.length ? view.overlap.reduce((s, o) => s + o.pct, 0) / view.overlap.length : null
  const top = view.moves.latest.find(m => m.net > 0)
  const line = (
    <>
      <LineItem label="Funds">{funds.length}</LineItem>
      {view.latestMonth && <LineItem label="Latest factsheet">{monthName(view.latestMonth)}</LineItem>}
      <LineItem label="Anomalies" color={view.anomalies.length ? T.warn : T.positive}>{view.anomalies.length}</LineItem>
      <LineItem label="Avg TER">{ter.toFixed(2)}%</LineItem>
      {overlapAvg != null && <LineItem label="Avg overlap">{overlapAvg.toFixed(0)}%</LineItem>}
      {top && <LineItem label="Most bought">{top.stock} ({top.buying.length} funds)</LineItem>}
    </>
  )
  return (
    <KpiSection storageKey="spendlens.mfKpisCompact" label="Mutual funds" line={line}>
      <section aria-label="MF KPIs" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: 12 }}>
        <Tile name="Funds tracked" value={funds.length}>
          <div style={sub}>Worth <b style={{ color: T.text, ...num }}>{fmt(total)}</b> · each fund once, folios combined</div>
          <div style={sub}>{[...new Set(funds.map(f => f.category))].join(' · ')}</div>
        </Tile>
        <Tile name="Latest factsheet" value={view.latestMonth ? monthName(view.latestMonth) : '–'}>
          <div style={sub}>{view.real ? `${view.sources.length} files read so far` : '12 months of sample history per fund'}</div>
        </Tile>
        <Tile name="Anomalies this month" value={<span style={{ color: view.anomalies.length ? T.warn : T.positive }}>{view.anomalies.length}</span>}>
          <div style={sub}>{ANOMALY_RULES.length} rules checked month over month</div>
        </Tile>
        <Tile name="Weighted expense ratio" value={`${ter.toFixed(2)}%`}>
          <div style={sub}>About <b style={{ color: T.text, ...num }}>{fmt(total * ter / 100)}</b> a year in fees</div>
        </Tile>
        {top && (
          <Tile name="Most bought last month" value={<span style={{ fontSize: 20 }}>{top.stock}</span>}>
            <div style={sub}>{top.buying.length} of your funds added it{top.new_in.length ? ` · new in ${top.new_in.length}` : ''}</div>
            <div style={sub}>{top.sector}</div>
          </Tile>
        )}
        {weakest && (
          <Tile name="Weakest fund" value={<span style={{ color: T.negative }}>{weakest.score}<small style={{ fontSize: 14, color: T.muted, fontWeight: 600 }}> /100</small></span>}>
            <div style={sub} title={weakest.name}>{weakest.name}</div>
            {overlapAvg != null && <div style={sub}>Average overlap between your funds {overlapAvg.toFixed(0)}%</div>}
          </Tile>
        )}
      </section>
    </KpiSection>
  )
}

function Scorecard({ funds }: { funds: ViewFund[] }) {
  const rows = [...funds].sort((a, b) => (b.score ?? -1) - (a.score ?? -1))
  const cols = ['ret1y', ...SCORED, 'aum']
  return (
    <>
      <div style={sub}>Each cell is graded against typical equity thresholds: <b style={{ color: T.positive }}>good</b> · <b style={{ color: T.warn }}>watch</b> · <b style={{ color: T.negative }}>weak</b>.
        Hover a heading for what it means; the Parameters tab explains all of them. “—” is not printed in the factsheet (or needs NAV history).</div>
      <Card style={{ padding: 0, overflow: 'auto', maxHeight: '70vh' }}>
        <table style={{ borderCollapse: 'collapse', width: '100%' }}>
          <thead><tr>
            <th style={{ ...th, textAlign: 'left', left: 0, zIndex: 2 }}>Fund</th>
            <th style={th}>Score</th><th style={{ ...th, textAlign: 'left' }}>Category</th><th style={{ ...th, textAlign: 'left' }}>Fund manager</th><th style={th}>As on</th>
            {cols.map(k => <th key={k} style={th} title={`${METRIC[k].label}: ${METRIC[k].what}`}>{METRIC[k].short}</th>)}
          </tr></thead>
          <tbody>
            {rows.map(f => (
              <tr key={f.name} style={{ borderTop: `1px solid ${T.hairline}` }}>
                <td style={{ ...tdl, position: 'sticky', left: 0, background: T.surface, fontWeight: 600, maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis' }} title={f.name}>{f.name}</td>
                <td style={{ ...td, fontWeight: 700, color: f.score == null ? T.muted : f.score >= 70 ? T.positive : f.score >= 50 ? T.warn : T.negative }}>{f.score ?? '—'}</td>
                <td style={{ ...tdl, color: T.muted }}>{f.category}</td>
                <td style={{ ...tdl, whiteSpace: 'normal', minWidth: 160, maxWidth: 240 }} title={f.managerYears != null ? `longest tenure ${f.managerYears.toFixed(1)} years` : undefined}>{f.manager || '—'}</td>
                <td style={{ ...td, color: T.muted }}>{f.asOn || (f.latestMonth ? monthName(f.latestMonth) : '—')}</td>
                {cols.map(k => {
                  const v = f.latest[k], g = /debt/i.test(f.category) ? null : grade(k, v)
                  return <td key={k} style={{ ...td, color: g ? GRADE_COLOR[g] : v == null ? T.muted : T.text, fontWeight: g === 'bad' ? 600 : 400 }}>{fmtMetric(k, v)}</td>
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      <div style={sub}>Score = the average of the graded cells (good 100, watch 60, weak 20). Debt funds are shown ungraded here; they are judged on YTM, duration and credit quality instead.</div>
    </>
  )
}

// ---------------------------------------------------------------- Factsheet analysis: the buying trend

function Buying({ view }: { view: View }) {
  const [mode, setMode] = useState<'fund' | 'across'>('fund')
  return (
    <>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        <Seg value={mode} onChange={setMode} options={[{ id: 'fund', label: 'By fund' }, { id: 'across', label: 'Across your funds' }]} />
        <span style={sub}>Stocks only (CDs, T-bills, bonds and cash roll over monthly and are left out); splits and bonuses are adjusted. What each fund bought and sold, comparing its portfolio between factsheets: over each calendar year (from the previous year’s last factsheet), or the latest month.</span>
      </div>
      {mode === 'fund' ? <ByFund funds={view.funds} /> : <Across moves={view.moves} />}
    </>
  )
}

function periods(t: MfTrends) {
  const out: { id: string; label: string; change: MfChange }[] = []
  if (t.latest) out.push({ id: 'latest', label: `Latest (${monthName(t.latest.to)})`, change: t.latest })
  for (const y of [...t.years].reverse()) out.push({ id: y.year, label: y.year, change: y })
  return out
}

function ByFund({ funds }: { funds: ViewFund[] }) {
  const [name, setName] = useState(funds[0]?.name ?? '')
  const f = funds.find(x => x.name === name) ?? funds[0]
  const ps = f ? periods(f.trends) : []
  const [pid, setPid] = useState<string>('')
  const [hideHeld, setHideHeld] = useState(true)
  const p = ps.find(x => x.id === pid) ?? ps.find(x => x.id !== 'latest') ?? ps[0]
  if (!f) return null
  if (!p) return <div style={sub}>{f.name}: needs holdings from at least two factsheets or portfolio disclosures.</div>
  const c = p.change
  const rows = c.rows.filter(r => !hideHeld || r.status !== 'held')
  const sectors = new Map<string, number>()
  for (const r of c.rows) sectors.set(r.sector || 'Other', (sectors.get(r.sector || 'Other') ?? 0) + r.weight_change)
  const sectorRows = [...sectors.entries()].filter(([, v]) => Math.abs(v) >= 0.05).sort((a, b) => b[1] - a[1])
  return (
    <>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        <select style={select} value={f.name} onChange={e => { setName(e.target.value); setPid('') }}>
          {funds.map(x => <option key={x.name}>{x.name}</option>)}
        </select>
        <Seg value={p.id} onChange={setPid} options={ps.map(x => ({ id: x.id, label: x.label }))} />
        <label style={{ fontSize: 12.5, color: T.muted, display: 'inline-flex', gap: 6, alignItems: 'center', cursor: 'pointer' }}>
          <input type="checkbox" checked={hideHeld} onChange={e => setHideHeld(e.target.checked)} /> hide unchanged
        </label>
      </div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <span style={sub}>{monthName(c.from)} → {monthName(c.to)}:</span>
        {(Object.keys(STATUS) as MfPositionStatus[]).map(s => (
          <span key={s} style={{ fontSize: 12.5, padding: '3px 10px', borderRadius: 999, border: `1px solid ${STATUS[s].color}55`, color: STATUS[s].color, background: `${STATUS[s].color}12` }}>
            {STATUS[s].label} <b>{c.counts[s]}</b>
          </span>
        ))}
        <span style={{ ...sub, marginLeft: 4 }}>
          {c.basis === 'shares' ? 'Based on share counts: real buying and selling.'
            : 'Based on weight (% of the fund) only: a weight also moves with the stock’s price. Portfolio disclosures with share counts make this exact.'}
        </span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 3fr) minmax(220px, 1fr)', gap: 12, alignItems: 'start' }}>
        <Card style={{ padding: 0, overflow: 'auto', maxHeight: '64vh' }}>
          <table style={{ borderCollapse: 'collapse', width: '100%' }}>
            <thead><tr>
              <th style={{ ...th, textAlign: 'left' }}>Stock</th><th style={{ ...th, textAlign: 'left' }}>Sector</th><th style={{ ...th, textAlign: 'left' }}>Change</th>
              <th style={th}>Weight {monthName(c.from)}</th><th style={th}>Weight {monthName(c.to)}</th><th style={th}>± pp</th>
              <th style={th}>Shares then</th><th style={th}>Shares now</th><th style={th}>Shares ±</th>
            </tr></thead>
            <tbody>
              {rows.map(r => (
                <tr key={r.isin || r.stock} style={{ borderTop: `1px solid ${T.hairline}` }}>
                  <td style={{ ...tdl, fontWeight: 600 }} title={r.isin}>{r.stock}</td>
                  <td style={{ ...tdl, color: T.muted }}>{r.sector || '—'}</td>
                  <td style={{ ...tdl, color: STATUS[r.status].color, fontWeight: 600 }} title={r.note || undefined}>{STATUS[r.status].label}{r.note ? <span style={{ color: T.muted, fontWeight: 400 }}> (split)</span> : null}{r.basis === 'weight' && r.status !== 'new' && r.status !== 'exited' ? <span style={{ color: T.muted, fontWeight: 400 }}> (weight)</span> : null}</td>
                  <td style={td}>{r.from_pct == null ? '—' : `${r.from_pct.toFixed(2)}%`}</td>
                  <td style={td}>{r.to_pct == null ? '—' : `${r.to_pct.toFixed(2)}%`}</td>
                  <td style={{ ...td, color: r.weight_change > 0 ? T.positive : r.weight_change < 0 ? T.negative : T.muted }}>{r.weight_change > 0 ? '+' : ''}{r.weight_change.toFixed(2)}</td>
                  <td style={{ ...td, color: T.muted }}>{shares(r.from_qty)}</td>
                  <td style={td}>{shares(r.to_qty)}</td>
                  <td style={{ ...td, fontWeight: 600, color: (r.qty_change_pct ?? 0) > 0 ? T.positive : (r.qty_change_pct ?? 0) < 0 ? T.negative : T.muted }}>
                    {r.qty_change_pct == null ? (r.status === 'new' ? 'new' : r.status === 'exited' ? 'sold out' : '—') : `${r.qty_change_pct > 0 ? '+' : ''}${r.qty_change_pct.toFixed(1)}%`}
                  </td>
                </tr>
              ))}
              {rows.length === 0 && <tr><td style={{ ...tdl, color: T.muted }} colSpan={9}>No changes in this period.</td></tr>}
            </tbody>
          </table>
        </Card>
        <Card style={{ padding: '12px 14px' }}>
          <div style={{ ...label, marginBottom: 6 }}>Sector shift (pp of the fund)</div>
          {sectorRows.length === 0 && <div style={sub}>No sector moved.</div>}
          {sectorRows.map(([s, v]) => {
            const maxAbs = Math.max(...sectorRows.map(([, x]) => Math.abs(x)), 0.01)
            return (
              <div key={s} style={{ display: 'grid', gridTemplateColumns: '90px 1fr 48px', gap: 8, alignItems: 'center', fontSize: 12, padding: '3px 0' }}>
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={s}>{s}</span>
                <div style={{ height: 8, background: T.surface2, borderRadius: 4, position: 'relative' }}>
                  <div style={{ position: 'absolute', top: 0, bottom: 0, borderRadius: 4, background: v >= 0 ? T.positive : T.negative,
                    left: v >= 0 ? '50%' : `${50 - (Math.abs(v) / maxAbs) * 50}%`, width: `${(Math.abs(v) / maxAbs) * 50}%` }} />
                </div>
                <span style={{ textAlign: 'right', color: v >= 0 ? T.positive : T.negative, ...num }}>{v > 0 ? '+' : ''}{v.toFixed(2)}</span>
              </div>
            )
          })}
        </Card>
      </div>
    </>
  )
}

function Across({ moves }: { moves: MfMoves }) {
  const options = [{ id: 'latest', label: 'Latest month' }, ...Object.keys(moves.by_year).sort().reverse().map(y => ({ id: y, label: y }))]
  const [pid, setPid] = useState(options[1]?.id ?? 'latest')
  const [side, setSide] = useState<'buying' | 'selling'>('buying')
  const list: MfMove[] = pid === 'latest' ? moves.latest : moves.by_year[pid] ?? []
  const rows = list.filter(m => (side === 'buying' ? m.buying.length > 0 : m.selling.length > 0))
    .sort((a, b) => (side === 'buying' ? b.buying.length - a.buying.length || b.weight_change - a.weight_change : b.selling.length - a.selling.length || a.weight_change - b.weight_change))
  const names = (xs: string[]) => xs.map(x => shortName(x)).join(', ')
  return (
    <>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        <Seg value={pid} onChange={setPid} options={options} />
        <Seg value={side} onChange={setSide} options={[{ id: 'buying', label: 'Being bought' }, { id: 'selling', label: 'Being sold' }]} />
        <span style={sub}>Across {moves.funds} funds. A stock several of your funds buy at once is a crowded bet: more of your money rides on it than any one fund shows.</span>
      </div>
      <Card style={{ padding: 0, overflow: 'auto', maxHeight: '64vh' }}>
        <table style={{ borderCollapse: 'collapse', width: '100%' }}>
          <thead><tr>
            <th style={{ ...th, textAlign: 'left' }}>Stock</th><th style={{ ...th, textAlign: 'left' }}>Sector</th>
            <th style={th}>{side === 'buying' ? 'Funds buying' : 'Funds selling'}</th><th style={th}>Net</th><th style={th}>Σ weight ± pp</th>
            <th style={{ ...th, textAlign: 'left' }}>{side === 'buying' ? 'New position in' : 'Sold out of'}</th>
            <th style={{ ...th, textAlign: 'left' }}>{side === 'buying' ? 'Added by' : 'Trimmed by'}</th>
          </tr></thead>
          <tbody>
            {rows.map(m => {
              const first = side === 'buying' ? m.new_in : m.exited_from
              const rest = (side === 'buying' ? m.buying : m.selling).filter(x => !first.includes(x))
              return (
                <tr key={m.isin || m.stock} style={{ borderTop: `1px solid ${T.hairline}` }}>
                  <td style={{ ...tdl, fontWeight: 600 }}>{m.stock}</td>
                  <td style={{ ...tdl, color: T.muted }}>{m.sector || '—'}</td>
                  <td style={{ ...td, fontWeight: 700, color: side === 'buying' ? T.positive : T.negative }}>{(side === 'buying' ? m.buying : m.selling).length}</td>
                  <td style={{ ...td, color: m.net > 0 ? T.positive : m.net < 0 ? T.negative : T.muted }}>{m.net > 0 ? '+' : ''}{m.net}</td>
                  <td style={{ ...td, color: m.weight_change >= 0 ? T.positive : T.negative }}>{m.weight_change > 0 ? '+' : ''}{m.weight_change.toFixed(2)}</td>
                  <td style={{ ...tdl, whiteSpace: 'normal', minWidth: 160 }}>{names(first) || '—'}</td>
                  <td style={{ ...tdl, whiteSpace: 'normal', minWidth: 160, color: T.muted }}>{names(rest) || '—'}</td>
                </tr>
              )
            })}
            {rows.length === 0 && <tr><td style={{ ...tdl, color: T.muted }} colSpan={7}>Nothing in this period.</td></tr>}
          </tbody>
        </table>
      </Card>
    </>
  )
}

// ---------------------------------------------------------------- other tabs

const TREND: { key: Series; label: string; unit: string; better: 'high' | 'low' }[] = [
  { key: 'rolling3y', label: '3-year return (each factsheet)', unit: '%', better: 'high' },
  { key: 'sharpe', label: 'Sharpe ratio', unit: '', better: 'high' },
  { key: 'beta', label: 'Beta', unit: '', better: 'low' },
  { key: 'ter', label: 'Expense ratio', unit: '%', better: 'low' },
  { key: 'aum', label: 'AUM (₹ cr)', unit: '', better: 'high' },
  { key: 'top10', label: 'Top-10 holdings', unit: '%', better: 'low' },
  { key: 'cash', label: 'Cash', unit: '%', better: 'low' },
]

function Trends({ funds }: { funds: ViewFund[] }) {
  const [name, setName] = useState(funds[0]?.name ?? '')
  const f = funds.find(x => x.name === name) ?? funds[0]
  if (!f) return null
  const cm = f.capMix
  return (
    <>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        <select style={select} value={f.name} onChange={e => setName(e.target.value)}>
          {funds.map(x => <option key={x.name}>{x.name}</option>)}
        </select>
        <span style={sub}>{f.category} · {f.amc || '—'}{f.manager && <> · manager {f.manager}{f.managerYears != null && `, ${f.managerYears < 1 ? 'new' : `${f.managerYears.toFixed(1)} years`}`}</>}
          {cm.large != null && ` · large ${cm.large}% / mid ${cm.mid ?? '—'}% / small ${cm.small ?? '—'}%`}</span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 12 }}>
        {TREND.map(t => {
          const s = f.series[t.key] ?? []
          const n = s.length
          const last = s[n - 1]?.value, prev = s[n - 2]?.value
          const delta = last != null && prev != null ? last - prev : null
          const worse = delta != null && (t.better === 'high' ? delta < 0 : delta > 0)
          const show = (v: number) => (t.key === 'aum' ? Math.round(v).toLocaleString('en-IN') : v.toFixed(2)) + t.unit
          return (
            <Card key={t.key} style={{ padding: '12px 14px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 8 }}>
                <span style={label}>{t.label}</span>
                {delta != null && <span style={{ fontSize: 12, color: Math.abs(delta) < 1e-9 ? T.muted : worse ? T.negative : T.positive, ...num }}>
                  {delta >= 0 ? '+' : ''}{t.key === 'aum' ? Math.round(delta).toLocaleString('en-IN') : delta.toFixed(2)}{t.unit} m/m
                </span>}
              </div>
              <div style={{ fontSize: 20, fontWeight: 700, margin: '2px 0 4px', ...num }}>{last == null ? '—' : show(last)}</div>
              <Spark points={s.map(p => p.value)} color={worse ? T.warn : T.accent} />
              {n > 1 && <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10.5, color: T.muted, marginTop: 2 }}>
                <span>{monthName(s[0].month)}</span><span>{monthName(s[n - 1].month)}</span>
              </div>}
            </Card>
          )
        })}
      </div>
    </>
  )
}

function Anomalies({ list }: { list: MfAnomalyRow[] }) {
  return (
    <>
      <Card style={{ padding: 0 }}>
        {list.length === 0 && <div style={{ padding: 14, fontSize: 13, color: T.positive }}>No anomalies in the latest factsheets.</div>}
        {list.map((a, i) => (
          <div key={i} style={{ display: 'flex', gap: 10, padding: '10px 14px', borderTop: i ? `1px solid ${T.hairline}` : 'none', alignItems: 'flex-start', flexWrap: 'wrap' }}>
            <span style={{ width: 8, height: 8, borderRadius: 4, background: SEV_COLOR[a.severity], marginTop: 6, flexShrink: 0 }} />
            <div style={{ flex: 1, minWidth: 220 }}>
              <div style={{ fontSize: 13 }}><b>{a.rule}</b> · {a.fund}</div>
              <div style={{ fontSize: 12, color: T.muted, marginTop: 2 }}>{a.detail}</div>
            </div>
            <span style={{ fontSize: 11.5, color: T.muted }}>{monthName(a.month)} · {a.severity}</span>
          </div>
        ))}
      </Card>
      <div style={{ ...label, marginTop: 4 }}>Rules checked every month</div>
      <Card style={{ padding: '6px 14px' }}>
        {ANOMALY_RULES.map(r => (
          <div key={r.key} style={{ fontSize: 12.5, padding: '5px 0', borderBottom: `1px solid ${T.hairline}` }}>
            <b>{r.label}</b> <span style={{ color: T.muted }}>· {r.why}</span>
          </div>
        ))}
      </Card>
    </>
  )
}

function Overlap({ funds, pairs }: { funds: ViewFund[]; pairs: View['overlap'] }) {
  const inPairs = new Set(pairs.flatMap(p => [p.a, p.b]))
  const eq = funds.filter(f => inPairs.has(f.name))
  const pairOf = (a: string, b: string) => pairs.find(p => (p.a === a && p.b === b) || (p.a === b && p.b === a))
  const pct = (a: string, b: string) => pairOf(a, b)?.pct
  const heat = (v: number) => (v >= 50 ? T.negative : v >= 30 ? T.warn : T.positive)
  const top = [...pairs].sort((a, b) => b.pct - a.pct).slice(0, 5)
  if (eq.length < 2 || pairs.length === 0) return <div style={sub}>Overlap needs at least two equity funds with holdings.</div>
  return (
    <>
      <Card style={{ padding: 0, overflow: 'auto' }}>
        <table style={{ borderCollapse: 'collapse' }}>
          <thead><tr><th style={{ ...th, textAlign: 'left' }} />{eq.map(f => <th key={f.name} style={{ ...th, whiteSpace: 'normal', maxWidth: 120, textAlign: 'center' }} title={f.name}>{fundLabel(f.name)}</th>)}</tr></thead>
          <tbody>
            {eq.map(r => (
              <tr key={r.name} style={{ borderTop: `1px solid ${T.hairline}` }}>
                <td style={{ ...tdl, fontWeight: 600 }} title={r.name}>{fundLabel(r.name)}</td>
                {eq.map(c => {
                  const v = r.name === c.name ? null : pct(r.name, c.name)
                  const part = r.name !== c.name && pairOf(r.name, c.name)?.partial
                  return <td key={c.name} style={{ ...td, textAlign: 'center', minWidth: 74, color: v == null ? T.muted : heat(v), background: v == null ? T.surface2 : `${heat(v)}14`, fontWeight: 600 }}>
                    {v == null ? '—' : `${v}%${part ? '*' : ''}`}
                  </td>
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      <div style={sub}>
        Common holdings: for every stock two funds both hold, the smaller of the two weights, added up. Stocks are matched by ISIN, or by company name
        where a factsheet prints no ISIN. Equity funds only (arbitrage and debt funds are left out). Above 50% you are paying two fees for much the same portfolio.
        {pairs.some(p => p.partial) && <> <b>*</b> at least one of the two funds is known only by its top holdings (its factsheet prints just the top 10), so the real overlap is at least this.</>}
      </div>
      <div style={{ ...label, marginTop: 4 }}>Most overlapping pairs</div>
      <Card style={{ padding: '6px 14px' }}>
        {top.map(p => (
          <div key={p.a + p.b} style={{ fontSize: 12.5, padding: '6px 0', borderBottom: `1px solid ${T.hairline}` }}>
            <b style={{ color: heat(p.pct) }}>{p.pct}%{p.partial ? '*' : ''}</b> · {fundLabel(p.a)} ↔ {fundLabel(p.b)}{p.count != null && <span style={{ color: T.muted }}> · {p.count} stocks in common</span>}{p.shared.length > 0 && <span style={{ color: T.muted }}> · shared: {p.shared.join(', ')}</span>}
          </div>
        ))}
      </Card>
    </>
  )
}

const dec = (x: number, d: number) => x.toLocaleString('en-IN', { minimumFractionDigits: d, maximumFractionDigits: d })
const CHECK_COLOR = { ok: T.positive, differs: T.negative, info: T.muted, missing: T.warn } as const
const CHECK_LABEL = { ok: 'matches', differs: 'differs', info: 'different basis', missing: 'not in factsheet' } as const

/** Morningstar fund reports (morningstarreport*.pdf, imported by import_mf.py) against the AMC's factsheet for the
 *  same portfolio month: one report per fund per month, newest first. */
function CrossCheck({ funds, real }: { funds: ViewFund[]; real: boolean }) {
  const withReports = funds.filter(f => f.reports.length > 0)
  const [name, setName] = useState(withReports[0]?.name ?? '')
  const f = withReports.find(x => x.name === name) ?? withReports[0]
  const [date, setDate] = useState('')
  if (!real || !f) {
    return (
      <Card style={{ padding: '12px 16px' }}>
        <div style={{ fontSize: 13, lineHeight: 1.6 }}>
          No Morningstar reports yet. Save a fund's Morningstar report PDF (<code>morningstarreport….pdf</code>) into <code>fund_fact_sheet/</code> and run{' '}
          <code>import_mf.py fund_fact_sheet</code> (or <code>/mf-factsheets</code> in Claude Code). Each one is stored by fund and month and compared with that
          month's factsheet here; the PDF can then be deleted.
        </div>
      </Card>
    )
  }
  const r = f.reports.find(x => x.report_date === date) ?? f.reports[0]
  const v = (x: number | string | null) => (x == null ? '—' : typeof x === 'number' ? dec(x, 2) : x)
  const counts = r.checks.reduce<Record<string, number>>((a, c) => ({ ...a, [c.status]: (a[c.status] ?? 0) + 1 }), {})
  const trailing = ['3m', '6m', '1y', '3y', '5y'].filter(k => r.trailing[k])
  return (
    <>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        <select style={select} value={f.name} onChange={e => { setName(e.target.value); setDate('') }}>
          {withReports.map(x => <option key={x.name} value={x.name}>{fundLabel(x.name)}</option>)}
        </select>
        <Seg value={r.report_date} onChange={setDate} options={f.reports.map(x => ({ id: x.report_date, label: monthName(x.month || x.report_date.slice(0, 7)) }))} />
        <span style={sub}>
          Morningstar report of {r.report_date} (portfolio {r.month || '—'}) vs the factsheet of {r.compared_month ? monthName(r.compared_month) : '—'}
          {r.compared_month && r.month && r.compared_month !== r.month && <b style={{ color: T.warn }}> · factsheet for {monthName(r.month)} not loaded yet</b>}
          {' · '}{counts.ok ?? 0} match, {counts.differs ?? 0} differ
        </span>
      </div>
      <Card style={{ padding: 0, overflow: 'auto' }}>
        <table style={{ borderCollapse: 'collapse', width: '100%' }}>
          <thead><tr>{['Figure', 'Factsheet', 'Morningstar', 'Gap', 'Check', 'Why they can differ'].map((h, i) => <th key={h} style={{ ...th, textAlign: i === 0 || i >= 4 ? 'left' : 'right' }}>{h}</th>)}</tr></thead>
          <tbody>
            {r.checks.map(c => (
              <tr key={c.metric} style={{ borderTop: `1px solid ${T.hairline}` }}>
                <td style={{ ...tdl, fontWeight: 600 }}>{c.metric}</td>
                <td style={{ ...td, whiteSpace: 'normal', maxWidth: 260 }}>{v(c.factsheet)}</td>
                <td style={{ ...td, whiteSpace: 'normal', maxWidth: 200 }}>{v(c.morningstar)}</td>
                <td style={{ ...td, color: T.muted }}>{c.diff == null ? '' : `${c.diff > 0 ? '+' : ''}${dec(c.diff, 2)}`}</td>
                <td style={{ ...tdl, color: CHECK_COLOR[c.status], fontWeight: 600 }}>{CHECK_LABEL[c.status]}</td>
                <td style={{ ...tdl, color: T.muted, whiteSpace: 'normal', minWidth: 220 }}>{c.note}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 12, alignItems: 'start' }}>
        <Card style={{ padding: '12px 16px' }}>
          <div style={{ ...label, marginBottom: 6 }}>Morningstar trailing returns %</div>
          <table style={{ borderCollapse: 'collapse', width: '100%' }}>
            <thead><tr>{['', 'Fund', 'Benchmark', 'Category'].map(h => <th key={h} style={{ ...th, background: 'transparent' }}>{h}</th>)}</tr></thead>
            <tbody>
              {trailing.map(k => {
                const t = r.trailing[k]
                return (
                  <tr key={k} style={{ borderTop: `1px solid ${T.hairline}` }}>
                    <td style={tdl}>{k}</td>
                    <td style={{ ...td, fontWeight: 600, color: t.fund >= t.benchmark ? T.positive : T.negative }}>{dec(t.fund, 2)}</td>
                    <td style={td}>{dec(t.benchmark, 2)}</td><td style={td}>{dec(t.category, 2)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </Card>
        <Card style={{ padding: '12px 16px' }}>
          <div style={{ ...label, marginBottom: 6 }}>Morningstar risk (3 years)</div>
          {Object.entries(r.risk).filter(([, x]) => x != null).map(([k, x]) => (
            <div key={k} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12.5, padding: '4px 0', borderTop: `1px solid ${T.hairline}` }}>
              <span>{k.replace(/_/g, ' ')}</span><b style={num}>{dec(x as number, 2)}</b>
            </div>
          ))}
          <div style={{ ...sub, marginTop: 6 }}>
            {r.equity_holdings != null && <>{r.equity_holdings} stocks · </>}
            {r.allocation.stocks != null && <>stocks {dec(r.allocation.stocks, 1)}% · cash {dec(r.allocation.cash ?? 0, 1)}% · </>}
            manager {r.manager || '—'}
          </div>
        </Card>
        <Card style={{ padding: '12px 16px' }}>
          <div style={{ ...label, marginBottom: 6 }}>Morningstar top 10 ({dec(r.top10.reduce((a, h) => a + h.pct, 0), 1)}%)</div>
          {r.top10.map(h => (
            <div key={h.name} style={{ display: 'flex', justifyContent: 'space-between', gap: 8, fontSize: 12.5, padding: '3px 0', borderTop: `1px solid ${T.hairline}` }}>
              <span>{h.name}</span><span style={num}>{dec(h.pct, 2)}%</span>
            </div>
          ))}
        </Card>
      </div>
      {r.has_pdf && (
        <Card style={{ padding: 0, overflow: 'hidden' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, padding: '10px 16px', borderBottom: `1px solid ${T.hairline}` }}>
            <div style={label}>Morningstar report · {monthName(r.month || r.report_date.slice(0, 7))} · {r.report_date}</div>
            <a href={mfReportPdfUrl(r.id)} target="_blank" rel="noreferrer" style={{ fontSize: 12.5, color: T.accent }}>Open in new tab</a>
          </div>
          <iframe key={r.id} title={`Morningstar report ${r.report_date}`} src={mfReportPdfUrl(r.id)} style={{ width: '100%', height: '80vh', border: 0, display: 'block' }} />
        </Card>
      )}
    </>
  )
}

const GROUPS: MetricGroup[] = ['Returns', 'Risk', 'Risk-adjusted', 'Downside protection', 'Costs & portfolio', 'Debt funds', 'People']

function Parameters() {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: 12, alignItems: 'start' }}>
      {GROUPS.map(g => (
        <Card key={g} style={{ padding: '12px 16px' }}>
          <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 6 }}>{g}</div>
          {METRICS.filter(m => m.group === g).map(m => (
            <div key={m.key} style={{ padding: '7px 0', borderTop: `1px solid ${T.hairline}` }}>
              <div style={{ fontSize: 13, fontWeight: 600 }}>
                {m.label}
                <span style={{ fontWeight: 400, fontSize: 11, color: T.muted }}> · {m.better === 'high' ? 'higher is better' : 'lower is better'}
                  {m.good != null && m.bad != null && ` · good ${fmtMetric(m.key, m.good)}, weak ${fmtMetric(m.key, m.bad)}`}
                  {' · '}{m.source === 'factsheet' ? 'from the factsheet' : 'computed from NAV history'}</span>
              </div>
              <div style={{ fontSize: 12.5, marginTop: 2 }}>{m.what}</div>
              <div style={{ fontSize: 12, color: T.muted, marginTop: 2 }}>{m.read}</div>
            </div>
          ))}
        </Card>
      ))}
    </div>
  )
}
