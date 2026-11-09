/** SAMPLE DATA for the MF Analysis preview. Every number here is generated from the fund's name, so the page looks
 *  realistic and stays stable between visits, but none of it is real. Delete this file when factsheet import lands. */
import type { MfChange, MfMoves, MfMove, MfPositionStatus, MfTrendRow, MfTrends } from './api'
import { GRADE_POINTS, SCORED, grade } from './mfMetrics'

export type Series = 'ter' | 'aum' | 'beta' | 'sharpe' | 'top10' | 'cash' | 'rolling3y'
export interface MfFund {
  name: string; amc: string; category: string; value: number
  months: string[]                       // YYYY-MM, oldest first
  series: Record<Series, number[]>
  latest: Record<string, number | null>
  manager: string; managerYears: number
  capMix: { large: number; mid: number; small: number }
  score: number
}
export interface MfAnomaly { severity: 'high' | 'medium' | 'low'; month: string; fund: string; rule: string; detail: string }
export interface MfOverlap { a: string; b: string; pct: number; shared: string[]; count?: number; partial?: boolean }

const STOCKS = ['HDFC Bank', 'ICICI Bank', 'Reliance', 'Infosys', 'TCS', 'Bharti Airtel', 'L&T', 'Axis Bank', 'Kotak Bank', 'ITC', 'SBI', 'M&M', 'Sun Pharma', 'Bajaj Finance']
const MANAGERS = ['R. Mehta', 'S. Iyer', 'A. Kapoor', 'N. Rao', 'P. Shah', 'K. Menon', 'V. Joshi', 'D. Bose']
const SAMPLE_FUNDS = ['Parag Parikh Flexi Cap Fund', 'HDFC Mid-Cap Opportunities Fund', 'ICICI Prudential Bluechip Fund', 'Nippon India Small Cap Fund']

function seed(text: string) {
  let h = 2166136261
  for (let i = 0; i < text.length; i++) { h ^= text.charCodeAt(i); h = Math.imul(h, 16777619) }
  return () => { h += 0x6d2b79f5; let t = h; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296 }
}
const between = (r: () => number, lo: number, hi: number) => lo + (hi - lo) * r()
const r2 = (n: number) => Math.round(n * 100) / 100

export function categoryOf(name: string) {
  const n = name.toLowerCase()
  if (/liquid|overnight|money market|debt|bond|gilt|duration|credit|corporate/.test(n)) return 'Debt'
  if (/small/.test(n)) return 'Small Cap'
  if (/mid/.test(n)) return 'Mid Cap'
  if (/bluechip|large|top 100|nifty 50|sensex/.test(n)) return 'Large Cap'
  if (/elss|tax/.test(n)) return 'ELSS'
  if (/index|nifty|etf/.test(n)) return 'Index'
  if (/hybrid|balanced|advantage|asset allocation|multi asset/.test(n)) return 'Hybrid'
  return 'Flexi Cap'
}

/** The 12 months of factsheets up to last month (an AMC publishes early the next month). */
export function sampleMonths(today = new Date()) {
  const out: string[] = []
  for (let i = 12; i >= 1; i--) {
    const d = new Date(today.getFullYear(), today.getMonth() - i, 1)
    out.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`)
  }
  return out
}

function walk(r: () => number, n: number, start: number, step: number, lo: number, hi: number) {
  const out = [start]
  for (let i = 1; i < n; i++) out.push(Math.min(hi, Math.max(lo, out[i - 1] + (r() - 0.5) * 2 * step)))
  return out
}

export function sampleFund(name: string, value: number, months: string[]): MfFund {
  const r = seed(name)
  const category = categoryOf(name)
  const debt = category === 'Debt'
  const risky = category === 'Small Cap' ? 1.35 : category === 'Mid Cap' ? 1.2 : category === 'Large Cap' || category === 'Index' ? 0.9 : 1
  const n = months.length
  const series: Record<Series, number[]> = {
    ter: walk(r, n, debt ? between(r, 0.15, 0.5) : between(r, 0.45, 1.2), 0.02, 0.1, 2.2),
    aum: walk(r, n, between(r, 4000, 60000), 1500, 800, 90000),
    beta: walk(r, n, debt ? between(r, 0.1, 0.3) : between(r, 0.78, 1.05) * (risky > 1 ? 1.05 : 1), 0.02, 0.05, 1.5),
    sharpe: walk(r, n, debt ? between(r, 0.6, 1.4) : between(r, 0.6, 1.5), 0.05, 0.1, 2.5),
    top10: walk(r, n, debt ? between(r, 30, 55) : between(r, 32, 58), 1, 15, 80),
    cash: walk(r, n, debt ? between(r, 2, 8) : between(r, 2, 7), 0.6, 0, 25),
    rolling3y: walk(r, n, debt ? between(r, 6, 8) : between(r, 11, 22) * risky, 0.5, -5, 40),
  }
  // a few deliberate events, so the Anomalies tab has something to show
  const ev = r()
  if (ev < 0.3) series.ter[n - 1] = series.ter[n - 2] + between(r, 0.1, 0.3)
  else if (ev < 0.5) series.cash[n - 1] = Math.max(10, series.cash.slice(0, -1).reduce((a, b) => a + b, 0) / (n - 1) * 2.4)
  else if (ev < 0.65) series.aum[n - 1] = series.aum[n - 2] * 0.8
  else if (ev < 0.8) series.top10[n - 1] = series.top10[n - 4] + 11
  const managerChanged = r() < 0.25
  const ret3y = debt ? between(r, 6, 7.8) : between(r, 11, 21) * risky
  const bench = debt ? 7 : 14 * risky
  const large = category === 'Large Cap' ? between(r, 74, 92) : category === 'Small Cap' ? between(r, 5, 20) : category === 'Mid Cap' ? between(r, 10, 25) : between(r, 45, 75)
  const small = category === 'Small Cap' ? between(r, 65, 85) : between(r, 2, 18)
  const latest: Record<string, number | null> = {
    ret1y: r2(debt ? between(r, 6, 8) : between(r, -6, 28) * risky),
    ret3y: r2(ret3y), ret5y: r2(debt ? between(r, 5.5, 7.5) : between(r, 10, 22) * risky),
    vsBench3y: r2(ret3y - bench),
    rollingBeat: Math.round(debt ? between(r, 40, 85) : between(r, 25, 95)),
    alpha: r2(between(r, -2, 5)),
    stdDev: r2(debt ? between(r, 0.5, 3) : between(r, 11, 17) * risky),
    beta: r2(series.beta[n - 1]), sharpe: r2(series.sharpe[n - 1]),
    sortino: r2(series.sharpe[n - 1] * between(r, 1.2, 1.8)),
    downCapture: Math.round(debt ? between(r, 20, 60) : between(r, 70, 108) * (risky > 1 ? 1.05 : 1)),
    upCapture: Math.round(debt ? between(r, 30, 70) : between(r, 82, 118)),
    maxDD: r2(debt ? -between(r, 0.5, 3) : -between(r, 18, 34) * risky),
    ter: r2(series.ter[n - 1]), aum: Math.round(series.aum[n - 1]),
    turnover: Math.round(between(r, 15, 110)), top10: r2(series.top10[n - 1]), cash: r2(series.cash[n - 1]),
    ytm: debt ? r2(between(r, 6.6, 7.8)) : null, modDuration: debt ? r2(between(r, 0.1, 6)) : null,
    credit: debt ? Math.round(between(r, 70, 100)) : null,
  }
  const grades = SCORED.map(k => grade(k, latest[k])).filter(g => g != null)
  const score = grades.length ? Math.round(grades.reduce((s, g) => s + GRADE_POINTS[g!], 0) / grades.length) : 0
  return {
    name, value, category, months, series, latest, score,
    amc: name.split(/\s+/).slice(0, name.toLowerCase().startsWith('icici') || name.toLowerCase().startsWith('aditya') ? 2 : 1).join(' '),
    manager: MANAGERS[Math.floor(r() * MANAGERS.length)] + (managerChanged ? ' (new)' : ''),
    managerYears: managerChanged ? 0.2 : r2(between(r, 1.5, 11)),
    capMix: { large: Math.round(large), small: Math.round(small), mid: Math.max(0, 100 - Math.round(large) - Math.round(small)) },
  }
}

export function sampleFunds(holdings: { name: string; value: number }[], months = sampleMonths()) {
  const list = holdings.length ? holdings : SAMPLE_FUNDS.map((name, i) => ({ name, value: [420000, 260000, 180000, 120000][i] }))
  return list.map(h => sampleFund(h.name, h.value, months))
}

export function sampleAnomalies(funds: MfFund[]): MfAnomaly[] {
  const out: MfAnomaly[] = []
  for (const f of funds) {
    const n = f.months.length, m = f.months[n - 1], s = f.series
    const avg = (xs: number[]) => xs.reduce((a, b) => a + b, 0) / xs.length
    if (f.manager.endsWith('(new)')) out.push({ severity: 'high', month: m, fund: f.name, rule: 'Fund manager changed', detail: `Now run by ${f.manager.replace(' (new)', '')}; the past record was someone else’s.` })
    if (s.ter[n - 1] - s.ter[n - 2] >= 0.1) out.push({ severity: 'medium', month: m, fund: f.name, rule: 'Expense ratio up', detail: `TER ${s.ter[n - 2].toFixed(2)}% → ${s.ter[n - 1].toFixed(2)}% (+${(s.ter[n - 1] - s.ter[n - 2]).toFixed(2)} pp).` })
    if (s.aum[n - 1] <= s.aum[n - 2] * 0.85) out.push({ severity: 'medium', month: m, fund: f.name, rule: 'AUM fell sharply', detail: `₹${Math.round(s.aum[n - 2]).toLocaleString('en-IN')} cr → ₹${Math.round(s.aum[n - 1]).toLocaleString('en-IN')} cr in a month.` })
    const cashAvg = avg(s.cash.slice(0, -1))
    if (s.cash[n - 1] >= cashAvg * 2 && s.cash[n - 1] >= 5) out.push({ severity: 'medium', month: m, fund: f.name, rule: 'Cash pile-up', detail: `Cash ${s.cash[n - 1].toFixed(1)}%, ${(s.cash[n - 1] / cashAvg).toFixed(1)}× its 12-month average.` })
    if (s.top10[n - 1] - s.top10[n - 4] >= 10) out.push({ severity: 'low', month: m, fund: f.name, rule: 'More concentrated', detail: `Top-10 holdings ${s.top10[n - 4].toFixed(0)}% → ${s.top10[n - 1].toFixed(0)}% in 3 months.` })
    if (s.beta[n - 1] > s.beta[n - 4] * 1.2) out.push({ severity: 'low', month: m, fund: f.name, rule: 'Beta jumped', detail: `Beta ${s.beta[n - 4].toFixed(2)} → ${s.beta[n - 1].toFixed(2)} in 3 months.` })
    if (f.category === 'Large Cap' && f.capMix.large < 80) out.push({ severity: 'high', month: m, fund: f.name, rule: 'Outside its mandate', detail: `Large caps ${f.capMix.large}% (SEBI minimum 80% for a large-cap fund); small caps ${f.capMix.small}%.` })
    if ((f.latest.rollingBeat ?? 100) < 40) out.push({ severity: 'medium', month: m, fund: f.name, rule: 'Lagging its benchmark', detail: `Beat the benchmark in only ${f.latest.rollingBeat}% of rolling 3-year windows.` })
  }
  const rank = { high: 0, medium: 1, low: 2 }
  return out.sort((a, b) => rank[a.severity] - rank[b.severity])
}

export function sampleOverlap(funds: MfFund[]): MfOverlap[] {
  const out: MfOverlap[] = []
  for (let i = 0; i < funds.length; i++) for (let j = i + 1; j < funds.length; j++) {
    const a = funds[i], b = funds[j]
    const r = seed(a.name + '|' + b.name)
    const debt = a.category === 'Debt' || b.category === 'Debt'
    const same = a.category === b.category
    const pct = debt ? Math.round(between(r, 0, 4)) : Math.round(same ? between(r, 45, 75) : between(r, 12, 45))
    const shared = debt ? [] : [...STOCKS].sort(() => r() - 0.5).slice(0, 3)
    out.push({ a: a.name, b: b.name, pct, shared })
  }
  return out
}

/** Which AMC factsheets are "loaded" per month, for the coverage grid (the latest month has a gap or two). */
export function sampleCoverage(funds: MfFund[]) {
  const amcs = [...new Set(funds.map(f => f.amc))].sort()
  const months = funds[0]?.months.slice(-6) ?? []
  return amcs.map(amc => {
    const r = seed(amc)
    return { amc, months: months.map((m, i) => ({ month: m, loaded: !(i === months.length - 1 && r() < 0.35) })) }
  })
}

// ---------------------------------------------------------------- buying trend (sample) and folio merging


const UNIVERSE = [...STOCKS, 'Titan', 'Asian Paints', 'Maruti Suzuki', 'HCL Tech', 'UltraTech Cement', 'Trent', 'Zomato', 'Persistent Systems',
  'Max Healthcare', 'Dixon Technologies', 'Coforge', 'Indian Hotels', 'PB Fintech', 'Cholamandalam Finance', 'Federal Bank', 'APL Apollo']
const SECTOR: Record<string, string> = {
  'HDFC Bank': 'Banks', 'ICICI Bank': 'Banks', 'Axis Bank': 'Banks', 'Kotak Bank': 'Banks', SBI: 'Banks', 'Federal Bank': 'Banks',
  Infosys: 'IT', TCS: 'IT', 'HCL Tech': 'IT', 'Persistent Systems': 'IT', Coforge: 'IT', Reliance: 'Energy', 'Bharti Airtel': 'Telecom',
  'Bajaj Finance': 'Finance', 'Cholamandalam Finance': 'Finance', 'PB Fintech': 'Finance', 'Sun Pharma': 'Pharma', 'Max Healthcare': 'Healthcare',
}

function sampleChange(r: () => number, names: string[], from: string, to: string): MfChange {
  const rows: MfTrendRow[] = names.map(stock => {
    const x = r()
    const status: MfPositionStatus = x < 0.14 ? 'new' : x < 0.42 ? 'added' : x < 0.62 ? 'trimmed' : x < 0.72 ? 'exited' : 'held'
    const q0 = Math.round(between(r, 2, 90)) * 100000
    const chg = status === 'added' ? between(r, 4, 60) : status === 'trimmed' ? -between(r, 4, 45) : between(r, -0.8, 0.8)
    const q1 = status === 'exited' ? null : status === 'new' ? Math.round(between(r, 2, 40)) * 100000 : Math.round(q0 * (1 + chg / 100))
    const w0 = status === 'new' ? null : r2(between(r, 0.6, 7))
    const w1 = status === 'exited' ? null : r2(status === 'new' ? between(r, 0.5, 2.5) : (w0 ?? 0) * (1 + chg / 100) * between(r, 0.9, 1.12))
    return { stock, isin: '', sector: SECTOR[stock] ?? 'Other', status, basis: 'shares', from_pct: w0, to_pct: w1,
      weight_change: r2((w1 ?? 0) - (w0 ?? 0)), from_qty: status === 'new' ? null : q0, to_qty: q1,
      qty_change_pct: status === 'new' || status === 'exited' ? null : Math.round(chg * 10) / 10 }
  })
  const order: Record<MfPositionStatus, number> = { new: 0, added: 1, trimmed: 2, exited: 3, held: 4 }
  rows.sort((a, b) => order[a.status] - order[b.status] || Math.abs(b.qty_change_pct ?? b.weight_change * 10) - Math.abs(a.qty_change_pct ?? a.weight_change * 10))
  const counts = { new: 0, added: 0, trimmed: 0, exited: 0, held: 0 }
  rows.forEach(x => counts[x.status]++)
  return { from, to, rows, counts, basis: 'shares' }
}

/** Sample position changes per calendar year in the fund's months, and for the latest month. */
export function sampleTrends(f: MfFund): MfTrends {
  const r = seed(f.name + '#trend')
  const pool = [...UNIVERSE].sort(() => r() - 0.5).slice(0, 16)
  const years = [...new Set(f.months.map(m => m.slice(0, 4)))]
  const out: MfTrends = { years: [], latest: null, months_with_holdings: f.months }
  for (const y of years) {
    const inside = f.months.filter(m => m.startsWith(y)), before = f.months.filter(m => m.slice(0, 4) < y)
    const from = before.length ? before[before.length - 1] : inside[0], to = inside[inside.length - 1]
    if (from !== to) out.years.push({ year: y, ...sampleChange(r, pool, from, to) })
  }
  const n = f.months.length
  if (n > 1) out.latest = sampleChange(r, pool.slice(0, 12), f.months[n - 2], f.months[n - 1])
  return out
}

/** Across funds: which stocks several of them are buying or selling (same rule as the server's market_moves). */
export function aggregateMoves(funds: { name: string; trends: MfTrends }[]): MfMoves {
  const agg = (changes: [string, MfChange][]) => {
    const by = new Map<string, MfMove>()
    for (const [fname, ch] of changes) for (const x of ch.rows) {
      if (x.status === 'held') continue
      const k = x.isin || x.stock.toLowerCase()
      const a = by.get(k) ?? { stock: x.stock, isin: x.isin, sector: x.sector, buying: [], selling: [], new_in: [], exited_from: [], weight_change: 0, net: 0 }
      a.weight_change = r2(a.weight_change + x.weight_change)
      ;(x.status === 'new' || x.status === 'added' ? a.buying : a.selling).push(fname)
      if (x.status === 'new') a.new_in.push(fname)
      if (x.status === 'exited') a.exited_from.push(fname)
      by.set(k, a)
    }
    const rows = [...by.values()]
    rows.forEach(a => { a.net = a.buying.length - a.selling.length })
    return rows.sort((a, b) => b.net - a.net || b.weight_change - a.weight_change || a.stock.localeCompare(b.stock))
  }
  const years = [...new Set(funds.flatMap(f => f.trends.years.map(y => y.year)))].sort()
  return {
    funds: funds.length,
    latest: agg(funds.filter(f => f.trends.latest).map(f => [f.name, f.trends.latest!] as [string, MfChange])),
    by_year: Object.fromEntries(years.map(y => [y, agg(funds.flatMap(f => f.trends.years.filter(t => t.year === y).map(t => [f.name, t] as [string, MfChange])))])),
  }
}

/** One entry per scheme: holdings of the same fund in several folios (or growth / direct spellings) are merged and
 *  their values added. The key ignores plan / option words and punctuation, like the server's scheme_key. */
export function mergeFolios<T extends { name: string; value: number }>(rows: T[]): { name: string; value: number }[] {
  const key = (s: string) => s.toLowerCase().replace(/\(?\s*folio\b[^)]*\)?/g, ' ').replace(/\b(fund|scheme|plan|option|growth|direct|regular|idcw|dividend|the)\b/g, ' ')
    .replace(/[^a-z0-9]+/g, ' ').trim()
  const by = new Map<string, { name: string; value: number }>()
  for (const r of rows) {
    const k = key(r.name)
    const cur = by.get(k)
    if (cur) cur.value += r.value
    else by.set(k, { name: r.name, value: r.value })
  }
  return [...by.values()]
}
