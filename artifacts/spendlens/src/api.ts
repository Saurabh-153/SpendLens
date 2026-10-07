const API_BASE = '/spendlens/api'

async function req<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
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

export interface DashboardCategory { id: number; name: string; icon: string; color: string; target_pct: number; spent: number; pct: number; prev_spent: number }
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
export const restoreSubcategory = (id: number) => req<Subcategory>(`/subcategories/${id}/restore`, 'POST')
export const deleteSubcategory = (id: number) => req(`/subcategories/${id}`, 'DELETE')
export const reorderSubcategories = (ids: number[]) => req('/subcategories/reorder', 'PUT', { ids })
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

export interface PortfolioGoal { id: number; name: string; target_amount: number; target_year: number }
export interface GoalResult extends PortfolioGoal { probability: number; conservative: number }
export interface BandPoint { year: number; p10: number; p50: number; p90: number }
export interface DriftRow { group: string; value: number; actual_pct: number; target_pct: number; drift_pct: number; trade: number }
export interface PerfRow { name: string; type: string; invested: number; present: number; pl: number; pl_pct: number }
export interface PortfolioKpis {
  total: number; invested: number; pl: number; pl_pct: number
  returns: { xirr: number | null; span_days: number; change: number | null; change_pct: number | null; since: string | null }
  sip: { monthly: number; yearly: number; pct_of_portfolio: number; savings_rate: number | null; income: number }
  safety: { emergency: number; monthly_spend: number; cover_months: number | null }
  locked_pct: number
  groups: Record<string, { present: number; invested: number; sip: number; count: number }>
  drift: DriftRow[]
  concentration: { top: { name: string; pct: number } | null; top5_pct: number; over_10: { name: string; pct: number }[]; sectors: { sector: string; value: number; pct: number }[] }
  performers: { best: PerfRow[]; worst: PerfRow[] }
  fixed: { avg_rate: number | null; rated_value: number; maturing: { name: string; date: string; value: number }[] }
  history: { date: string; total: number; invested: number }[]
  forecast: { band: BandPoint[]; conservative_band: BandPoint[]; start: number; monthly_sip: number; goals: GoalResult[]; paths: number } | null
  extra_sip_needed: number
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

export type TxKind = 'BUY' | 'SELL' | 'DIVIDEND' | 'OPENING'
export interface Tx {
  id: number; holding_id: number | null; name: string; tx_date: string; kind: TxKind; qty: number; price: number
  amount: number; fees: number; realized: number; note: string; source: string; applied: number; fy: string
}
export interface TxInput {
  holding_id: number | null; name?: string; tx_date: string; kind: TxKind; qty?: number; price?: number; amount?: number; fees?: number; note?: string; apply?: number
}
export interface FyRow { fy: string; dividends: number; realized: number; bought: number; sold: number }
export interface HoldingReturn { id: number; name: string; grp: string; type: string; invested: number; present: number; dividends: number; since: string | null; xirr: number | null; covered: boolean }
export interface LedgerSummary {
  fy: FyRow[]; current_fy: string; dividends_total: number; realized_total: number
  xirr: { portfolio: number | null; covered_pct: number; holdings: HoldingReturn[] }
}
export const getTransactions = (q: { kind?: string; fy?: string; holding_id?: number; limit?: number } = {}) => {
  const p = new URLSearchParams()
  Object.entries(q).forEach(([k, v]) => v && p.set(k, String(v)))
  return req<{ total: number; rows: Tx[] }>(`/transactions?${p}`)
}
export const addTransaction = (t: TxInput) => req<{ id: number }>('/transactions', 'POST', t)
export const deleteTransaction = (id: number) => req(`/transactions/${id}`, 'DELETE')
export const getLedgerSummary = () => req<LedgerSummary>('/ledger/summary')

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
