const API_BASE = '/spendlens/api'

async function req<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    cache: 'no-store',
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    if (res.status === 401 && path !== '/auth/login') window.dispatchEvent(new Event('spendlens:signed-out'))   // the session ended: App shows the sign-in screen
    const detail = await res.json().catch(() => null)
    const d = detail?.detail   // FastAPI sends a list of {msg, loc} when a request fails validation
    throw new Error(Array.isArray(d) ? d.map((e: { msg?: string }) => e.msg).join('; ') : d ?? `Request failed (${res.status})`)
  }
  return res.json()
}

export interface GridEntry { id: number; subcategory_id: number | null; amount: number; note: string; cashback: number }
export interface GridCell { amount: number; cashback: number; note: string; expense_id: number; entries: GridEntry[] }
export interface Subcategory {
  id: number; category_id: number; name: string; sort_order: number; start_month: string; end_month: string | null
  archived?: boolean // month-filtered lists: shown only because it holds data that month
  status?: 'active' | 'scheduled' | 'archived'; has_data?: boolean
}
export interface SubTotal { subcategory_id: number | null; total: number }
export interface GridCategory {
  id: number; name: string; icon: string; color: string; target_pct: number
  archived: boolean; sort_order: number; total: number; cashback: number
  days: Record<string, GridCell>; subs: SubTotal[]
}
export interface MonthlyGrid {
  month: string; days: number; categories: GridCategory[]; subcategories: Subcategory[]
  total_spent: number; total_cashback: number; income: number; budget_cap: number
}

export interface DashboardCategory { id: number; name: string; icon: string; color: string; target_pct: number; spent: number; pct: number; prev_spent: number; history: number[] }
export interface DashboardData {
  month: string; income: number; budget_cap: number; total_spent: number; total_cashback: number
  biggest_cat: { name: string; icon: string } | null; biggest_cat_amt: number; extra_saving: number
  daily: number[]; trend: { month: string; total: number; budget_cap: number }[]; categories: DashboardCategory[]
  savings_amount: number; next_month: string; next_total: number; prev2_month: string; prev2_total: number; prev_month: string; prev_total: number; prev_daily: number[]; unassigned_count: number
  top_expenses: { date: string; amount: number; note: string; category: string; icon: string; subcategory: string | null }[]
  subcategories: { category_id: number; subcategory_id: number | null; name: string; spent: number }[]
}

export interface Holding {
  id: number; name: string; ticker: string; asset_type: string; sector: string
  qty: number; buy_price: number; cmp: number; notes: string; tags: string; exposure: string
  grp: string; sip_amount: number; sip_day: number; maturity: string
  rate: number; start_date: string; compounding: string; rd: number; credits: string; manual: number; auto: boolean
  invested: number; present: number; pl: number; pl_pct: number; units_held: number | null; nav: number; week52_low: number; week52_high: number
}
export type HoldingInput = Pick<Holding, 'name' | 'ticker' | 'asset_type' | 'sector' | 'qty' | 'buy_price' | 'cmp' | 'notes' | 'tags' | 'exposure' | 'grp' | 'sip_amount' | 'sip_day' | 'maturity' | 'rate' | 'start_date' | 'compounding' | 'rd' | 'credits' | 'manual'>

export type DbKind = 'postgresql' | 'sqlite'
export interface DbStatus {
  primary: DbKind; mode: 'normal' | 'read-only-fallback'; switching: boolean; can_switch: boolean
  mirror: { path_name: string; updated_at: string | null; last_error: string | null } | null
  copy: { to: DbKind; updated_at: string | null; last_error: string | null } | null
}
export const getStatus = () => req<DbStatus>('/status')
export const switchDatabase = (to: DbKind) => req<DbStatus>('/database/switch', 'POST', { to })

export interface DbCard {
  kind: DbKind; name: string; role: 'main' | 'copy'; reachable: boolean; latency_ms?: number | null
  rows?: number | null; tables?: number | null; size_bytes?: number | null; where?: string
  last_save_at?: string | null; updated_at?: string | null; last_error?: string | null
}
export interface SyncRun {
  id: number; at: string; direction: string; trigger: string; ok: boolean; error: string | null; duration_ms: number | null
  rows_total: number | null; tables_total: number | null; rows_added: number | null; rows_changed: number | null
  rows_removed: number | null; tables_changed: number | null
}
export interface Abnormality { level: 'critical' | 'warning' | 'info'; title: string; detail: string }
export interface DbTableRow {
  name: string; area: string; main_rows: number | null; copy_rows: number | null
  last_change: [number, number, number]; compared_match: boolean | null
}
export interface DbOverview extends Omit<DbStatus, 'copy'> {
  main: DbCard; copy: DbCard | null
  kpis: null | {
    last_sync: Pick<SyncRun, 'at' | 'direction' | 'trigger' | 'ok' | 'error' | 'duration_ms'> | null
    in_sync: { rows: number | null; tables: number; matching: number }
    today: { syncs: number; failed: number; rows_changed: number; tables_changed: number }
    health_7d: { syncs: number; failed: number; rows_changed: number; tables_changed: number; rate: number | null }
    pending: number
  }
  tables: DbTableRow[]
  last_compare: { at: string; ok: boolean; differs: number; pending: number } | null
  abnormalities: Abnormality[]
}
export interface DbSwitch { id: number; at: string; from_kind: DbKind; to_kind: DbKind; ok: boolean; error: string | null; rows_total: number | null; tables_total: number | null; pause_ms: number }
export interface DbHistory { days: { date: string; syncs: number; failed: number; rows_changed: number }[]; runs: SyncRun[]; switches: DbSwitch[]; keep_days: number }
export interface DbCompare { at: string; ok: boolean; pending: number; differs: number; tables: { name: string; area: string; main_rows: number; copy_rows: number | null; match: boolean }[] }
export const getDbOverview = () => req<DbOverview>('/database/overview')
export const getDbHistory = (days = 14) => req<DbHistory>(`/database/history?days=${days}`)
export const compareDatabases = () => req<DbCompare>('/database/compare', 'POST')

export const getGrid = (month: string) => req<MonthlyGrid>(`/expenses/monthly-grid?month=${month}`)
export interface ForecastRange { p10: number; p50: number; p90: number }
export interface ForecastCategory extends ForecastRange {
  id: number; name: string; icon: string; fixed: boolean; reliable: boolean; spent: number
  mae_model: number | null; mae_base: number | null
}
export interface Forecast {
  month: string; mode: 'in_progress' | 'future' | 'past'; elapsed: number; days: number; budget_cap: number; history_months: number
  available: boolean; reason?: string
  total?: ForecastRange; categories?: ForecastCategory[]
  backtest?: { months: number; mape_model: number | null; mape_base: number | null }
  model_beats_baseline?: boolean
}
export const getForecast = (month: string) => req<Forecast>(`/forecast?month=${month}`)
export const getDashboard = (month: string) => req<DashboardData>(`/dashboard?month=${month}`)
export const addExpense = (category_id: number, date: string, amount: number, subcategory_id: number | null = null, note = '') =>
  req('/expenses', 'POST', { category_id, date, amount, subcategory_id, note })
export interface EntryInput { id: number | null; subcategory_id: number | null; amount: number; note: string }
export const setCellEntries = (category_id: number, date: string, entries: EntryInput[]) =>
  req('/expenses/cell-entries', 'PUT', { category_id, date, entries })
export const setRange = (category_id: number, month: string, start_day: number, end_day: number, amount: number, subcategory_id: number | null = null, mode: 'add' | 'replace' = 'replace', note = '') =>
  req('/expenses/range', 'POST', { category_id, month, start_day, end_day, amount, subcategory_id, mode, note })

export const getHoldings = () => req<Holding[]>('/holdings')
export const createHolding = (h: HoldingInput) => req<Holding>('/holdings', 'POST', h)
export const updateHolding = (id: number, h: HoldingInput) => req<Holding>(`/holdings/${id}`, 'PUT', h)
export const deleteHolding = (id: number) => req(`/holdings/${id}`, 'DELETE')
export const portfolioCsvUrl = `${API_BASE}/export/portfolio`
export const mfReportPdfUrl = (id: number) => `${API_BASE}/mf/reports/${id}/pdf`

export interface Category {
  id: number; name: string; icon: string; color: string; target_pct: number; hint: string
  sort_order: number; start_month: string; end_month: string | null
  status: 'active' | 'scheduled' | 'archived'; has_data: boolean
  archived?: boolean // only on month-filtered lists: shown only because of its data
}
export interface CategoryInput { name: string; icon: string; color: string; hint: string }
export interface BudgetEntry { from_month: string; income: number; savings_amount: number }
export interface TargetEntry { from_month: string; target_pct: number }

export const getCategories = (month?: string) => req<Category[]>(month ? `/categories?month=${month}` : '/categories')
export const createCategory = (c: CategoryInput & { start_month: string; target_pct: number }) => req<Category>('/categories', 'POST', c)
export const updateCategory = (id: number, c: CategoryInput) => req<Category>(`/categories/${id}`, 'PUT', c)
export const archiveCategory = (id: number, from_month: string) =>
  req<Category & { months_with_data_after: number }>(`/categories/${id}/archive`, 'POST', { from_month })
export const restoreCategory = (id: number) => req<Category>(`/categories/${id}/restore`, 'POST')
export const deleteCategory = (id: number) => req(`/categories/${id}`, 'DELETE')
export interface CategoryUsage { entries: number; total: number; first: string | null; last: string | null; months: number; subcategories: number; target_changes: number; can_delete: boolean }
export const getCategoryUsage = (id: number) => req<CategoryUsage>(`/categories/${id}/usage`)
export const reorderCategories = (ids: number[]) => req('/categories/reorder', 'PUT', { ids })
export const getCategoryTargets = (id: number) => req<TargetEntry[]>(`/categories/${id}/targets`)
export const setCategoryTarget = (id: number, from_month: string, target_pct: number) =>
  req(`/categories/${id}/target`, 'PUT', { from_month, target_pct })
export const getBudgetHistory = () => req<BudgetEntry[]>('/budget')
export const setBudget = (b: BudgetEntry) => req('/budget', 'PUT', b)

export interface ReviewItem { category_id: number; category: string; note: string; count: number; total: number }
export const getSubcategories = (opts: { category_id?: number; month?: string } = {}) => {
  const q = new URLSearchParams()
  if (opts.category_id) q.set('category_id', String(opts.category_id))
  if (opts.month) q.set('month', opts.month)
  return req<Subcategory[]>(`/subcategories${q.size ? `?${q}` : ''}`)
}
export const createSubcategory = (category_id: number, name: string, start_month: string) =>
  req<Subcategory>('/subcategories', 'POST', { category_id, name, start_month })
export const updateSubcategory = (id: number, name: string) => req<Subcategory>(`/subcategories/${id}`, 'PUT', { name })
export const archiveSubcategory = (id: number, from_month: string) =>
  req<Subcategory & { months_with_data_after: number }>(`/subcategories/${id}/archive`, 'POST', { from_month })
export const deleteSubcategory = (id: number) => req(`/subcategories/${id}`, 'DELETE')
export const getReview = () => req<ReviewItem[]>('/subcategories/review')
export const mapReview = (category_id: number, note: string, subcategory_id: number) =>
  req<{ updated: number }>('/subcategories/review/map', 'POST', { category_id, note, subcategory_id })

export const getDataMonths = () => req<string[]>('/expenses/months')

export interface HoldingGroup { id: number; name: string; count: number; present: number; hidden_columns: string[] }
export interface HoldingGroups { groups: HoldingGroup[]; others: { count: number; present: number } }
export const getHoldingGroups = () => req<HoldingGroups>('/holding-groups')
export const createHoldingGroup = (name: string) => req('/holding-groups', 'POST', { name })
export const renameHoldingGroup = (id: number, name: string) => req(`/holding-groups/${id}`, 'PUT', { name })
export const setGroupHiddenColumns = (id: number, keys: string[]) => req<{ ok: true }>(`/holding-groups/${id}/hidden-columns`, 'PUT', { keys })
export interface ColumnLayout { order: string[]; hidden: string[] }
export const getHoldingColumns = () => req<ColumnLayout>('/holding-columns')
export const saveHoldingColumns = (l: ColumnLayout) => req<{ ok: true }>('/holding-columns', 'PUT', l)
export const deleteHoldingGroup = (id: number) => req<{ moved: number }>(`/holding-groups/${id}`, 'DELETE')
export const moveHoldings = (ids: number[], grp: string) => req('/holdings/move', 'POST', { ids, grp })
export const setHoldingSip = (id: number, sip_amount: number, sip_day: number) => req(`/holdings/${id}/sip`, 'PUT', { sip_amount, sip_day })
export interface SipLogRow { id: number; holding_name: string; month: string; sip_date: string; amount: number }
export const getSipLog = () => req<SipLogRow[]>('/sip-log')

/** large: paid from the corpus (simulated). small / recurring: paid from the monthly set-aside (`commitments`). */
export type GoalKind = 'large' | 'small' | 'recurring'
export interface PortfolioGoal {
  id: number; name: string; target_amount: number; target_year: number; kind: GoalKind; target_month: number | null
  // recurring only: repeats every N months from target_month/target_year, rising yearly, until end_year
  every_months: number; end_year: number | null; escalation_pct: number; category_id: number | null; subcategory_id: number | null
}
export interface CommitPayment { goal_id: number; name: string; kind: 'small' | 'recurring'; month: string; amount: number }
export interface SmallGoalPlan { id: number; name: string; month: string; amount: number; months_left: number; per_month: number }
export interface RecurringPlan {
  id: number; name: string; every_months: number; month: number; escalation_pct: number; end_year: number | null
  next: { month: string; amount: number } | null; yearly: { year: number; amount: number }[]
  link: string | null; spent: number | null; planned: number | null; since: string | null
}
export interface Commitments {
  months: number; start: string; set_aside: number; top_up: number
  income: number; spend: number; sip: number; surplus: number
  payments: CommitPayment[]; small: SmallGoalPlan[]; recurring: RecurringPlan[]
}
export interface GoalResult extends PortfolioGoal { probability: number; conservative: number }
export interface BandPoint { year: number; p10: number; p50: number; p90: number }
export interface DriftRow { group: string; value: number; actual_pct: number; target_pct: number; drift_pct: number; trade: number }
export interface PerfRow { name: string; type: string; invested: number; present: number; pl: number; pl_pct: number }
export interface PortfolioKpis {
  total: number; invested: number; pl: number; pl_pct: number
  returns: { xirr: number | null; span_days: number; change: number | null; change_pct: number | null; since: string | null }
  sip: { monthly: number; yearly: number; by_mix: { Equity: number; Gold: number; Debt: number }; pct_of_portfolio: number; savings_rate: number | null; income: number }
  safety: { emergency: number; monthly_spend: number; cover_months: number | null }
  locked_pct: number
  groups: Record<string, { present: number; invested: number; sip: number; count: number }>
  drift: DriftRow[]
  concentration: {
    top: { name: string; pct: number } | null; top5_pct: number; over_10: { name: string; pct: number }[]
    sectors: { sector: string; value: number; pct: number }[]
    ranked: { name: string; type: string; value: number; pct: number }[] // the 10 largest positions (folios merged)
  }
  performers: { best: PerfRow[]; worst: PerfRow[] }
  fixed: {
    avg_rate: number | null; rated_value: number; maturing: { name: string; date: string; value: number }[]
    ladder: { name: string; date: string; value: number; rate: number | null }[] // maturities in the next 5 years
  }
  liquidity: { instant: number; days: number; fixed: number; locked: number } // value by how fast it can be reached
  history: { date: string; total: number; invested: number }[]
  forecast: { band: BandPoint[]; conservative_band: BandPoint[]; start: number; monthly_sip: number; goals: GoalResult[]; paths: number } | null
  extra_sip_needed: number
  commitments: Commitments
  prices: { last_ok: string | null; auto_count: number }
  ledger: { xirr: number | null; covered_pct: number; fy: string; dividends: number; realized: number }
}
export interface PortfolioPlan {
  targets: Record<string, number>
  assumptions: { stepup: number; groups: Record<string, { ret: number; vol: number }> }
  goals: PortfolioGoal[]
  groups: string[]
}
export interface ExposureRow {
  name: string; present: number; invested: number; pl: number; pl_pct: number; pct: number; count: number
  target: number | null; drift: number | null; add: number | null
}
export interface ExposureData {
  total: number; exposures: ExposureRow[]; targets: Record<string, number>
  by_group: { group: string; values: Record<string, number> }[]
  tags: { tag: string; present: number; count: number; pct: number; exposure: string }[]
}
export const getExposure = () => req<ExposureData>('/portfolio/exposure')

type Mix3 = Record<'Equity' | 'Gold' | 'Debt', number>
export interface MixData {
  targets: Mix3; returns: Mix3; years: number; reach_years: number; stepup: number
  current: { total: number; value: Mix3; pct: Mix3 }
  sip: { total: number; by: Record<keyof Mix3, { amt: number; pct: number; items: { id: number; name: string; ticker: string; asset_type: string; grp: string; amt: number }[] }> }
  plan: null | {
    reach_month: number | null; reach_date: string | null; reachable: boolean; wanted_months: number
    earliest_month: number | null; earliest_date: string | null
    recommended: Record<keyof Mix3, { amt: number; pct: number; delta: number }>
    after: Record<keyof Mix3, { amt: number; pct: number }>; end_mix: Mix3; horizon_months: number
  }
  path: { m: number; date: string; rec: Mix3; cur: Mix3; sip_rec: Mix3 | null; sip_cur: Mix3 | null }[]
  forecast: { year: number; months: number; values: Mix3; total: number; pct: Mix3; current_total: number }[]
}
export const getMix = () => req<MixData>('/portfolio/mix')
export const saveMixPlan = (p: { targets: Mix3; returns: Mix3; years: number; reach_years: number }) => req('/portfolio/mix-plan', 'PUT', p)
export const getPortfolioKpis = () => req<PortfolioKpis>('/portfolio/kpis')
export const getPortfolioPlan = () => req<PortfolioPlan>('/portfolio/plan')
export const savePortfolioPlan = (p: { targets?: Record<string, number>; assumptions?: PortfolioPlan['assumptions'] }) => req('/portfolio/plan', 'PUT', p)
export const addGoal = (g: Omit<PortfolioGoal, 'id'>) => req('/portfolio/goals', 'POST', g)
export const updateGoal = (id: number, g: Omit<PortfolioGoal, 'id'>) => req(`/portfolio/goals/${id}`, 'PUT', g)
export const deleteGoal = (id: number) => req(`/portfolio/goals/${id}`, 'DELETE')

export interface PriceRow {
  id: number; name: string; asset_type: string; grp: string; ticker: string; scheme_code: string; units: number; nav: number
  auto_price: number; price_date: string; price_note: string; present: number; invested: number; cmp: number; week52_low: number; week52_high: number
}
export interface PriceRun { id: number; ran_at: string; ok: number; updated: number; failed: number; detail: string }
export interface PricesStatus { last_ok: string | null; stale: boolean; runs: PriceRun[]; holdings: PriceRow[] }
export interface PriceOption { ticker?: string; code?: string; name: string; plan?: string; nav?: number; date?: string }
export const getPricesStatus = () => req<PricesStatus>('/prices/status')
export const refreshPrices = () => req<{ updated: number; failed: number; errors: string[] }>('/prices/refresh', 'POST')
export const setPriceCfg = (id: number, c: { ticker: string; scheme_code: string; units: number; auto_price: number }) => req(`/prices/holding/${id}`, 'PUT', c)
export const suggestPrice = (id: number) => req<{ type: string; options: PriceOption[] }>(`/prices/suggest/${id}`)
export const unitsFromValue = (id: number) => req<{ units: number; nav: number }>(`/prices/units-from-value/${id}`, 'POST')
export const autoMapPrices = () => req<{ mapped: string[]; skipped: string[] }>('/prices/auto-map', 'POST')

// ---------------------------------------------------------------- stock ledger (broker tradebooks, dividends, XIRR)

export type EquityAccount = string   // the user's demat label, e.g. "SK"; "ALL" combines them
export interface EquityStock {
  symbol: string; name: string; status: 'held' | 'exited'; qty: number; invested: number; avg_cost: number | null
  price: number | null; price_date: string; value: number | null; unrealized: number | null; realized: number; dividends: number
  xirr: number | null; xirr_ex_div: number | null; xirr_note: string | null; first_date: string | null; exit_date: string | null
  accounts: Record<string, number>
  /** every sale and priced buyback, as traded */
  sold_qty: number; sale_value: number
  /** the closing sales after the last purchase; null while the stock is held */
  exit_qty: number | null; exit_price: number | null; exit_value: number | null
  /** exited stocks: splits since the exit (shares now per share sold), the exit price on today's basis,
   *  today's price against it, and what the exit shares would be worth today */
  split_factor_since_exit: number | null; exit_price_adj: number | null; change_since_exit_pct: number | null; exit_value_now: number | null
}
export interface DividendRow { symbol: string; status: 'held' | 'exited'; total: number; sources: string[]; by_quarter: Record<string, number>; by_year: Record<string, number> }
export interface EquitySummary {
  accounts: string[]; account: EquityAccount; as_of: string; current_fy: string
  kpis: {
    value: number; invested: number; unrealized: number; realized: number; dividends_total: number; dividends_fy: number
    xirr: number | null; xirr_ex_div: number | null; xirr_coverage_pct: number | null; held_count: number; exited_count: number
  }
  stocks: EquityStock[]
  dividends: { quarters: string[]; years: string[]; rows: DividendRow[]; totals_by_quarter: Record<string, number>; totals_by_year: Record<string, number> }
  coverage: Record<string, { statement_to: string | null; last_trade: string | null }>
  issue_counts: { error: number; warning: number; info: number }
}
export interface EquityIssue {
  level: 'error' | 'warning' | 'info'; kind: string; account: string; symbol: string; date: string; date_to?: string; count?: number
  expected?: number; replay?: number; delta?: number; message: string; hint?: string
}
export interface EquityAuditRow { id: number; at: string; kind: string; account: string; file_name: string; period_from: string; period_to: string; summary: string }
export interface EquityAudit { issues: EquityIssue[]; log: EquityAuditRow[]; holdings_checks: { account: string; as_of: string; total: number; matched: number }[] }
export type EquityEventKind = 'SPLIT' | 'BONUS' | 'BUYBACK' | 'TRANSFER_OUT' | 'IPO' | 'TRANSFER_IN' | 'ADJUST' | 'DEMERGER' | 'MERGER' | 'RENAME'
export interface EquityEventInput {
  account: string; symbol: string; ex_date: string; kind: EquityEventKind; ratio_new: number; ratio_old: number
  qty: number; price: number | null; target_symbol: string; cost_pct: number; note: string
}
export interface EquityEvent extends EquityEventInput { id: number; source: 'manual' | 'yahoo' | 'builtin' }
export interface EquityTimelineRow { date: string; account: string; kind: string; qty: number; price: number | null; amount: number; qty_after: number; note: string }
export interface EquityStockDetail {
  symbol: string; timeline: EquityTimelineRow[]; events: EquityEvent[]
  dividends: { date: string; account: string; qty: number; dps: number; amount: number; source: string }[]
}
export interface EquityRefreshResult {
  summary: string; fetched: number; failed: number; errors: { symbol: string; error: string }[]; splits_added: [string, string, string][]
  dividends_added: number; dividends_updated: number; dividends_removed: number; warnings: number; ran_at: string
}
const acct = (a: EquityAccount) => `account=${encodeURIComponent(a || 'ALL')}`
export const getEquitySummary = (a: EquityAccount) => req<EquitySummary>(`/equity/summary?${acct(a)}`)
export const getEquityAudit = (a: EquityAccount) => req<EquityAudit>(`/equity/audit?${acct(a)}`)
export const getEquityAuditEntry = (id: number) => req<EquityAuditRow & { detail: unknown }>(`/equity/audit/${id}`)
export const getEquityStock = (symbol: string, a: EquityAccount) => req<EquityStockDetail>(`/equity/stock/${encodeURIComponent(symbol)}?${acct(a)}`)

// ---------------------------------------------------------------- MF analysis (from factsheets read by Claude Code)

export type MfPositionStatus = 'new' | 'added' | 'trimmed' | 'exited' | 'held'
export interface MfTrendRow {
  stock: string; isin: string; sector: string; status: MfPositionStatus
  /** shares: real buying / selling; weight: only the % of the fund was printed, which also moves with price */
  basis: 'shares' | 'weight'
  from_pct: number | null; to_pct: number | null; weight_change: number
  from_qty: number | null; to_qty: number | null; qty_change_pct: number | null
  /** e.g. a split / bonus: the share counts were compared after adjusting for it */
  note?: string
}
export interface MfChange { from: string; to: string; rows: MfTrendRow[]; counts: Record<MfPositionStatus, number>; basis: 'shares' | 'weight' | null }
export interface MfTrends { years: (MfChange & { year: string })[]; latest: MfChange | null; months_with_holdings: string[] }
export interface MfMove {
  stock: string; isin: string; sector: string; buying: string[]; selling: string[]; new_in: string[]; exited_from: string[]
  weight_change: number; net: number
}
export interface MfMoves { funds: number; latest: MfMove[]; by_year: Record<string, MfMove[]> }
export interface MfApiFund {
  key: string; name: string; plan: string; amc: string; amfi_code: string; category: string; benchmark: string
  held: boolean; value: number; months: string[]; latest_month: string
  latest: Record<string, number | null>
  series: Record<'ter' | 'aum' | 'beta' | 'sharpe' | 'top10' | 'cash' | 'rolling3y', { month: string; value: number }[]>
  manager: string; manager_years: number | null; managers: { name: string; since: string }[]; as_on: string
  cap_mix: { large: number | null; mid: number | null; small: number | null }
  holdings_count: number; trends: MfTrends
  reports: MfReport[]
}
export interface MfCheck { metric: string; factsheet: number | string | null; morningstar: number | string | null; diff: number | null; status: 'ok' | 'differs' | 'info' | 'missing'; note: string }
/** A Morningstar fund report, stored to cross-check the AMC's factsheet (month = its portfolio date). */
export interface MfReport {
  id: number; has_pdf: boolean; source: string; scheme: string; report_date: string; month: string; compared_month: string | null; file: string
  rating_stars: number | null; risk: Record<string, number | null>
  trailing: Record<string, { fund: number; benchmark: number; category: number }>
  allocation: Record<string, number | null>; top10: { name: string; pct: number }[]; equity_holdings: number | null
  manager: string; net_assets_cr: number | null; expense_ratio: number | null; checks: MfCheck[]
}
export interface MfAnomalyRow { severity: 'high' | 'medium' | 'low'; month: string; fund: string; rule: string; detail: string }
export interface MfAnalysisData {
  has_data: boolean; funds: MfApiFund[]; anomalies: MfAnomalyRow[]
  overlap: { a: string; b: string; pct: number; shared: string[]; count?: number; partial?: boolean }[]
  coverage: { amc: string; months: { month: string; loaded: boolean }[] }[]
  unmatched_holdings: { name: string; scheme_code: string }[]
  latest_month: string | null
  sources: { month: string; file: string; kind: string; amc: string; funds: number; notes: string; imported_at: string }[]
  market_moves: MfMoves
}
export const getMfAnalysis = () => req<MfAnalysisData>('/mf/analysis')
export const getEquityEvents = () => req<{ events: EquityEvent[]; kinds: EquityEventKind[] }>('/equity/events')
export const addEquityEvent = (e: EquityEventInput) => req<{ id: number }>('/equity/events', 'POST', e)
export const updateEquityEvent = (id: number, e: EquityEventInput) => req<{ ok: true }>(`/equity/events/${id}`, 'PUT', e)
export const deleteEquityEvent = (id: number) => req<{ ok: true }>(`/equity/events/${id}`, 'DELETE')
export const setEquityYahooSymbol = (symbol: string, yahoo_symbol: string) => req<{ ok: true }>(`/equity/securities/${encodeURIComponent(symbol)}`, 'PUT', { yahoo_symbol })
export const refreshEquity = () => req<EquityRefreshResult>('/equity/refresh', 'POST')

// ---------------------------------------------------------------- credit cards

export type CardClass = string  // reward class ids differ per card: online / offline, or amazon / partner ...
export interface Card {
  id: number; name: string; issuer: string; network: string; last4: string; profile: string
  credit_limit: number; cash_limit: number; statement_day: number; grace_days: number
  pay_buffer_days: number; float_rate: number; cycle_verified: number
  annual_fee: number; fee_waiver_spend: number; cashback_cap: number
  status: string; notes: string
  account_id?: number
  numbers?: string[]    // every card number it has had, oldest first (a re-issued card keeps one entry)
  members?: number[]    // the ids behind those numbers
  last_used?: string
  color?: string        // its own colour (see cardColors.ts)
}
export interface CardStatement {
  id: number; kind: 'cycle' | 'year'; period_from: string; period_to: string; stmt_date: string; due_date: string | null
  total_due: number; min_due: number; purchases: number; credits: number; fees: number
  available_credit: number; cashback_reported: number | null; cashback_calc: number | null; file: string
}
export interface CardMonth {
  period_to: string; spend: number; cashback: number; reported: boolean; calc: number; rate: number
  due: number | null; fees: number | null; due_date: string | null
}
export interface CardYear { fy: string; spend: number; cashback: number; fees: number }
export interface CardMerchant { name: string; spend: number; count: number; cashback: number; cls: CardClass; rate: number; emi: number }
export interface CardLeak { name: string; spend: number; cls: CardClass; missed: number }
export interface PayCycle {
  statement: string; due: string; pay_on: string; billed: number; paid: number
  early_days: number | null; forgone: number; late: number
}
export interface PayDates { statement: string; due: string; pay_on: string; days_to_pay: number }
export interface PayInfo {
  statement_day: number; grace_days: number; buffer: number; rate: number
  verified: boolean; needs_cycle: boolean; data_through: string | null; stale: boolean
  shared_with?: string[]   // other cards settled by the same bill
  missing_statements?: string[]   // statements the sequence needs but the data lacks
  expected_bill?: number; outstanding?: number
  habit?: {
    paid: number; days_credit_used: number; days_credit_available: number; days_early: number
    forgone: number; forgone_per_year: number; late_amount: number; on_time_pct: number; span_days: number
    cycles: PayCycle[]
  }
  upcoming?: (PayDates & { days_kept: number; kept_value: number })[]
  previous?: PayDates
  last_bill?: PayDates & { amount: number }
}
export interface RubyxBenefits {
  kind: 'rubyx' | 'sapphiro'; name: string; point_value: number
  milestone: {
    threshold: number; base: number; step: number; cap: number
    years: { fy: string; spend: number; points: number; value: number }[]
    current: { fy: string; spend: number; points: number; next_at: number; to_go: number; next_points: number }
  }
  lounge: { threshold: number; visits: number; lag: number; extra: string; quarters: { quarter: string; spend: number; earns_next: boolean; entitled: boolean; swipes: number }[] }
  redemptions: { count: number; cost: number; per_redemption: number }
}
export interface CardDashboard {
  card: (Card & { rates: Record<string, number>; numbers: string[]; members: number[] }) | null
  profile: { classes: { id: string; label: string; rate: number }[]; emi_earns: boolean; has_leaks: boolean; rewards: boolean; point_value: number; earned_label: string | null }
  categories: { name: string; spend: number; count: number; pct: number }[]
  benefits: RubyxBenefits | null
  points: {
    earned: number; value: number; per_100: number; balance: number | null; redeem_at: number; unit: string; on_lines: number
    months: { period_to: string; earned: number; value: number }[]
  } | null
  today: string
  totals: {
    statements: number; transactions: number; spend: number; gross_spend: number; refunds: number
    earned: number; earned_is_estimate: boolean; cashback_calc: number; cashback_paid: number | null
    effective_rate: number; best_possible: number; fees_paid: number; net_profit: number
    avg_monthly_spend: number; since: string | null; through: string | null
    spend_12m: number; emi: number; milestone_bonus?: number
  }
  by_class: Record<string, { spend: number; count: number; pct: number; cashback: number; points?: number }>
  merchants: CardMerchant[]
  leaks: CardLeak[]
  months: CardMonth[]
  years: CardYear[]
  latest: CardStatement | null
  pay: PayInfo
  fee: { annual_fee: number; waiver_spend: number; year_spend: number; progress: number; waived: boolean; short_by: number } | null
  utilisation: number | null
}
export interface CardImportFile {
  file: string; ok: boolean; error?: string; parser?: string; card?: string; card_id?: number; period_to?: string
  cards?: { card: string; card_id: number; period_to: string; spend: number; rows: number; added: number }[]
  spend?: number; rows?: number; added?: number; skipped?: number; cashback?: number | null
}
export interface CardMerchantRule { id: number; card_id: number | null; pattern: string; match_type: string; cls: string; created_at: string }
export interface CardSettings {
  name?: string; profile?: string
  credit_limit: number; annual_fee: number; fee_waiver_spend: number; cashback_cap: number
  rates: Record<string, number>; statement_day: number; grace_days: number; pay_buffer_days: number; float_rate: number
}

export const getCards = () => req<Card[]>('/cards')
export const getCardDashboard = (cardId?: number) => req<CardDashboard>(`/cards/dashboard${cardId ? `?card_id=${cardId}` : ''}`)
export interface CardParsers { formats: string[]; llm_available: boolean }
export const getCardParsers = () => req<CardParsers>('/cards/parsers')
/** Multipart, so it cannot go through `req` (which sends JSON). */
export async function uploadCardStatements(files: File[], password: string, useLlm: boolean) {
  const body = new FormData()
  files.forEach(f => body.append('files', f))
  body.append('password', password)
  body.append('use_llm', String(useLlm))
  const res = await fetch(`${API_BASE}/cards/upload`, { method: 'POST', body })
  if (!res.ok) {
    const detail = await res.json().catch(() => null)
    throw new Error(detail?.detail ?? `Request failed (${res.status})`)
  }
  return (await res.json()) as { files: CardImportFile[] }
}
export const getCardRules = (cardId?: number) => req<CardMerchantRule[]>(`/cards/merchant-rules${cardId ? `?card_id=${cardId}` : ''}`)
export const setCardMerchantRule = (pattern: string, cls: string, cardId?: number) =>
  req<{ ok: true }>('/cards/merchant-rule', 'POST', { pattern, cls, card_id: cardId ?? null })
export const deleteCardRule = (id: number) => req(`/cards/merchant-rules/${id}`, 'DELETE')
export const saveCardSettings = (id: number, s: CardSettings) => req<{ ok: true }>(`/cards/${id}`, 'PUT', s)

export interface OverviewCard {
  id: number; color: string; name: string; numbers: string[]; profile: string; status: string
  issuer: string; network: string; credit_limit: number; annual_fee: number; fee_waiver_spend: number
  since: string | null; through: string | null; spend: number; spend_12m: number
  transactions: number; avg_ticket: number; emi: number; emi_share: number
  fees: number; fees_share: number; earned: number; earned_is_estimate: boolean; rewards: boolean
  top_merchant: { name: string; spend: number } | null; shared_with: string[]
}
export interface OverviewPay {
  card_id: number; name: string; cards: string[]; statement: string; due: string; pay_on: string
  days_to_pay: number; verified: boolean; stale: boolean; expected: number; issued: boolean
}
export interface CardsOverview {
  today: string; cards: OverviewCard[]
  years: { fy: string; by_card: Record<string, number>; total: number }[]
  pay: OverviewPay[]
  totals: { spend: number; spend_12m: number; fees: number; cards: number; active_cards: number }
}
export const getCardsOverview = () => req<CardsOverview>('/cards/overview')

export interface AdminCard {
  id: number; color: string; name: string; issuer: string; numbers: string[]; members: number[]; profile: string; scheme: string
  status: 'active' | 'closed'; since: string | null; last_used: string | null
  spend: number; transactions: number; statements: number; shared_with: string[]
  network: string; notes: string; credit_limit: number; annual_fee: number; fee_waiver_spend: number
  statement_day: number; grace_days: number; cycle_verified: boolean
}
export type CardPatch = Partial<Pick<AdminCard, 'name' | 'status' | 'issuer' | 'network' | 'notes' | 'profile' | 'credit_limit' | 'annual_fee' | 'fee_waiver_spend' | 'statement_day' | 'grace_days' | 'color'>> & { last4?: string }
export interface CardAdvice {
  totals: { spend_12m: number; earned_12m: number; best_12m: number; missed_12m: number }
  purposes: { id: string; label: string; examples: string; spend_12m: number; earned_12m: number; missed_12m: number; nothing_earns: boolean
    best: { card_id: number; color: string; name: string; rate: number; note: string; conf: string; also: string[] } | null
    next: { card_id: number; color: string; name: string; rate: number; note: string } | null }[]
  exceptions: { merchant: string; card: string; rate: number }[]
  cards: { id: number; color: string; name: string; best_for: string[]; never_best: boolean; note: string }[]
  assumptions: string[]
}
export const getCardAdvice = () => req<CardAdvice>('/cards/advice')
/** Add a card by hand; it appears on the Cards page at once. */
export const createCard = (body: { name: string; profile: string; last4: string; issuer: string }) => req<AdminCard>('/cards', 'POST', body)
export const getCardsAdmin = () => req<AdminCard[]>('/cards/admin')
/** Rename a card, or mark it closed / active. A card is never deleted. */
export const saveCardOrder = (ids: number[]) => req<{ ids: number[] }>('/cards/order', 'PUT', { ids })
export const patchCard = (id: number, body: CardPatch) => req<AdminCard>(`/cards/${id}`, 'PATCH', body)

export interface Perk { id: number; card_id: number; kind: string; title: string; detail: string; value_yr: number; source: string; checked: boolean; updated: string }
export interface Perks { kinds: { id: string; label: string }[]; perks: Perk[]; to_check: number; value_yr: number }
export const getPerks = (cardId: number) => req<Perks>(`/cards/${cardId}/perks`)
export const addPerk = (cardId: number, body: Partial<Perk>) => req<Perks>(`/cards/${cardId}/perks`, 'POST', body)
export const updatePerk = (id: number, body: Partial<Perk>) => req<Perks>(`/cards/perks/${id}`, 'PATCH', body)
export const deletePerk = (id: number) => req<Perks>(`/cards/perks/${id}`, 'DELETE')

export interface ReminderCategory { id: number; name: string; color: string; kind: 'card' | 'sip' | null; sort_order: number; reminder_count: number }
export type ReminderRepeat = 'monthly' | 'quarterly' | 'yearly'
export interface Reminder {
  id: number; category_id: number; name: string; amount: number; day: number; repeat: ReminderRepeat; month: number | null
  enabled: boolean; note: string; expense_category_id: number | null; expense_subcategory_id: number | null; source_key: string | null
}
export type ReminderInput = Omit<Reminder, 'id'>
export type OccurrenceState = 'done' | 'missing' | 'up' | 'info' | 'unlinked'
export interface SipSource { holding_id: number; name: string; label: string; amount: number; day: number }
export interface ReminderOccurrence {
  key: string; reminder_id: number | null; category_id: number; name: string; amount: number; day: number
  state: OccurrenceState; note: string; auto: boolean; estimated: boolean
  sources?: SipSource[]   // SIP groups only: the holdings behind the occurrence
  moved?: boolean         // this month's date was moved away from the reminder's usual day
}
export interface Holiday { date: string; day: number; country: 'IN' | 'US'; name: string }
export interface Vacation { id: number; name: string; start_date: string; end_date: string; color: string }
export type VacationInput = Omit<Vacation, 'id'>
export interface ReminderCalendar {
  month: string; today: string; occurrences: ReminderOccurrence[]; logged_days: number[]; nudge: { on: boolean; time: string }
  holidays?: Holiday[]; vacations?: Vacation[]   // vacations overlapping the month, with their full (unclipped) dates
  trackers?: CalendarTracker[]
}
export interface ReminderSuggestion {
  key: string; name: string; category_id: number; subcategory_id: number | null; day: number; amount: number
  min_amount: number; max_amount: number; months: number; window: string; last_seen: string
}
export interface ReminderSettings { nudge_on: boolean; nudge_time: string }

export const getReminderCategories = () => req<ReminderCategory[]>('/reminder-categories')
export const createReminderCategory = (c: { name: string; color: string }) => req<ReminderCategory>('/reminder-categories', 'POST', c)
export const updateReminderCategory = (id: number, c: { name?: string; color?: string }) => req<ReminderCategory>(`/reminder-categories/${id}`, 'PUT', c)
export const deleteReminderCategory = (id: number, opts: { move_to?: number; delete_reminders?: boolean } = {}) => {
  const q = new URLSearchParams()
  if (opts.move_to) q.set('move_to', String(opts.move_to))
  if (opts.delete_reminders) q.set('delete_reminders', 'true')
  return req(`/reminder-categories/${id}${q.size ? `?${q}` : ''}`, 'DELETE')
}
export const getReminders = () => req<Reminder[]>('/reminders')
export const createReminder = (r: ReminderInput) => req<Reminder>('/reminders', 'POST', r)
export const updateReminder = (id: number, r: Partial<ReminderInput>) => req<Reminder>(`/reminders/${id}`, 'PUT', r)
export const deleteReminder = (id: number) => req(`/reminders/${id}`, 'DELETE')
export const getReminderCalendar = (month: string) => req<ReminderCalendar>(`/reminders/calendar?month=${month}`)
export const getReminderSuggestions = () => req<ReminderSuggestion[]>('/reminders/suggestions')
export const getReminderSettings = () => req<ReminderSettings>('/reminders/settings')
export interface SipVisibility { holding_id: number; name: string; label: string; amount: number; day: number; show: boolean }
export const getReminderSips = () => req<SipVisibility[]>('/reminders/sips')
export const setReminderSipVisibility = (holdingId: number, show: boolean) => req<SipVisibility>(`/reminders/sips/${holdingId}`, 'PUT', { show })
export const updateReminderSettings = (s: Partial<ReminderSettings>) => req<ReminderSettings>('/reminders/settings', 'PUT', s)

export const getVacations = () => req<Vacation[]>('/vacations')
export const createVacation = (v: VacationInput) => req<Vacation>('/vacations', 'POST', v)
export const updateVacation = (id: number, v: Partial<VacationInput>) => req<Vacation>(`/vacations/${id}`, 'PUT', v)
export const deleteVacation = (id: number) => req(`/vacations/${id}`, 'DELETE')

export type TrackerPause = 'vacation' | 'IN' | 'US'
export interface TrackerCostLink { category_id: number; subcategory_id: number | null }
export interface Tracker {
  id: number; name: string; color: string; target_per_week: number; weekdays: number[]   // 0 = Monday
  pause_on: TrackerPause[]; bill_reminder_id: number | null; cost_links: TrackerCostLink[]; sort_order: number
}
export type TrackerInput = Omit<Tracker, 'id' | 'sort_order'>
export interface TrackerWeek { start_day: number; end_day: number; done: number; goal: number }
export interface TrackerKpi {
  count: number; month_goal: number; expected_by_today: number; projected: number; status: 'good' | 'warn' | 'bad'
  this_week: { done: number; goal: number }; weeks_on_target: number; complete_weeks: number; week_streak: number; per_week: TrackerWeek[]
  cost: null | { avg_on: number; avg_off: number; n_on: number; n_off: number; diff: number }
  cost_per_visit: null | { bill_name: string; amount: number; per_visit: number }
}
export interface CalendarTracker {
  id: number; name: string; color: string; target_per_week: number; weekdays: number[]; pause_on: TrackerPause[]
  done_days: number[]; scheduled_days: number[]; kpi: TrackerKpi
}
export const getTrackers = () => req<Tracker[]>('/trackers')
export const createTracker = (t: TrackerInput) => req<Tracker>('/trackers', 'POST', t)
export const updateTracker = (id: number, t: Partial<TrackerInput>) => req<Tracker>(`/trackers/${id}`, 'PUT', t)
export const deleteTracker = (id: number) => req(`/trackers/${id}`, 'DELETE')
export const reorderTrackers = (ids: number[]) => req('/trackers/reorder', 'PUT', { ids })
export const setTrackerDay = (id: number, date: string, done: boolean) => req(`/trackers/${id}/days/${date}`, 'PUT', { done })
export const moveReminder = (id: number, m: { month: string; day: number; scope: 'all' | 'month' }) => req<Reminder>(`/reminders/${id}/move`, 'PUT', m)

// ---- sign-in, modules and access requests
export type ModuleId = 'expense' | 'holdings' | 'ledger' | 'cards'
export interface ModuleInfo { id: ModuleId; label: string; description: string }
export interface AccessRequest {
  id: number; user_id: number; module: ModuleId; note: string; status: 'pending' | 'approved' | 'rejected'
  created_at: string; decided_by: number | null; decided_at: string | null; decision_note: string
  user_email?: string; user_name?: string
}
export interface Me {
  id: number; email: string; name: string; role: 'admin' | 'user'; is_active: boolean; created_at: string
  modules: ModuleId[]; all_modules: ModuleInfo[]; requests: AccessRequest[]; pending_requests: number
}
export interface AdminUser {
  id: number; email: string; name: string; role: 'admin' | 'user'; is_active: boolean; created_at: string
  modules: ModuleId[]; pending?: ModuleId[]
}
export const login = (email: string, password: string) => req<Me>('/auth/login', 'POST', { email, password })
export const logout = () => req('/auth/logout', 'POST')
export const getMe = () => req<Me>('/auth/me')
export const changePassword = (current_password: string, new_password: string) => req('/auth/password', 'POST', { current_password, new_password })
/** Forgotten password: the server accepts this only from the computer it runs on. */
export const resetPasswordLocal = (email: string, new_password: string, code: string) => req<{ ok: true }>('/auth/reset-local', 'POST', { email, new_password, code })
export const requestAccess = (module: ModuleId, note: string) => req<AccessRequest>('/access/requests', 'POST', { module, note })
export const getAdminUsers = () => req<{ modules: ModuleInfo[]; users: AdminUser[] }>('/admin/users')
export const createAdminUser = (u: { email: string; name: string; password: string; role: 'admin' | 'user'; modules: ModuleId[] }) => req<AdminUser>('/admin/users', 'POST', u)
export const updateAdminUser = (id: number, u: { name?: string; role?: 'admin' | 'user'; is_active?: boolean; password?: string }) => req<AdminUser>(`/admin/users/${id}`, 'PATCH', u)
export const setUserModules = (id: number, modules: ModuleId[]) => req<AdminUser>(`/admin/users/${id}/modules`, 'PUT', { modules })
export const getAccessRequests = (status?: AccessRequest['status']) => req<AccessRequest[]>(`/admin/access/requests${status ? `?status=${status}` : ''}`)
export const decideAccessRequest = (id: number, approve: boolean, note: string) => req<AccessRequest>(`/admin/access/requests/${id}/${approve ? 'approve' : 'reject'}`, 'POST', { note })
