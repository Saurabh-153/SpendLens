/** What a mutual fund is judged on: one definition per metric, used by the MF Analysis scorecard (grading) and its
 *  Parameters tab (the explanations). The real factsheet scorer will reuse these when it replaces the sample data. */

export type MetricGroup = 'Returns' | 'Risk' | 'Risk-adjusted' | 'Downside protection' | 'Costs & portfolio' | 'Debt funds' | 'People'
export type Grade = 'good' | 'ok' | 'bad'

export interface MetricDef {
  key: string
  label: string
  short: string            // column heading
  group: MetricGroup
  unit: '%' | 'pp' | 'x' | '₹cr' | 'yrs' | ''
  better: 'high' | 'low'
  /** equity thresholds: at or beyond `good` is green, at or beyond `bad` is red, between is amber */
  good?: number
  bad?: number
  what: string             // what it is
  read: string             // how to read it / what good looks like
  source: 'factsheet' | 'computed'   // where the real number will come from
}

export const METRICS: MetricDef[] = [
  // ---- returns
  { key: 'ret1y', label: '1-year return', short: '1Y', group: 'Returns', unit: '%', better: 'high', source: 'computed',
    what: 'Growth of the NAV over the last 12 months.',
    read: 'Too short to judge a fund on its own; compare with the category and benchmark.' },
  { key: 'ret3y', label: '3-year return (CAGR)', short: '3Y', group: 'Returns', unit: '%', better: 'high', good: 15, bad: 10, source: 'computed',
    what: 'Yearly compounded growth of the NAV over 3 years.',
    read: 'The main trailing number for equity funds. Judge it against the benchmark (next column), not in isolation.' },
  { key: 'ret5y', label: '5-year return (CAGR)', short: '5Y', group: 'Returns', unit: '%', better: 'high', good: 14, bad: 10, source: 'computed',
    what: 'Yearly compounded growth over 5 years, a full market cycle in most cases.',
    read: 'Steadier than 1 or 3 years; a fund lagging here has lagged through ups and downs.' },
  { key: 'vsBench3y', label: '3-year return vs benchmark', short: 'vs bench', group: 'Returns', unit: 'pp', better: 'high', good: 1, bad: -1, source: 'computed',
    what: 'The fund’s 3-year CAGR minus its benchmark index’s (total return index, dividends included).',
    read: 'Positive means the manager earned the fee. Persistently negative: an index fund would have done better.' },
  { key: 'rollingBeat', label: 'Rolling 3-year windows beating the benchmark', short: 'Roll beat', group: 'Returns', unit: '%', better: 'high', good: 70, bad: 40, source: 'computed',
    what: 'Of every 3-year period over the last 5–7 years (started each month), the share in which the fund beat its benchmark.',
    read: 'Consistency, without depending on today’s date. Above 70% is consistent; below 40% the outperformance was luck or timing.' },
  { key: 'alpha', label: 'Alpha (Jensen’s)', short: 'Alpha', group: 'Returns', unit: '%', better: 'high', good: 1.5, bad: 0, source: 'factsheet',
    what: 'Return above what the fund’s beta predicts from the benchmark’s return.',
    read: 'The manager’s skill after accounting for market exposure. Positive is good; negative means you paid for underperformance.' },

  // ---- risk
  { key: 'stdDev', label: 'Standard deviation', short: 'Std dev', group: 'Risk', unit: '%', better: 'low', good: 13, bad: 18, source: 'factsheet',
    what: 'How much the fund’s returns swing around their average (annualised, usually from 3 years of monthly returns).',
    read: 'Higher means a bumpier ride. Compare within a category: small caps naturally run higher than large caps.' },
  { key: 'beta', label: 'Beta', short: 'Beta', group: 'Risk', unit: 'x', better: 'low', good: 0.9, bad: 1.05, source: 'factsheet',
    what: 'Sensitivity to the benchmark: 1.0 moves one-for-one, 0.8 moves 8% when the market moves 10%.',
    read: 'Below 1 is defensive. A rising beta month after month can signal the manager is taking more risk.' },
  { key: 'maxDD', label: 'Maximum drawdown', short: 'Max DD', group: 'Risk', unit: '%', better: 'high', good: -25, bad: -35, source: 'computed',
    what: 'The worst fall from a peak to a later low, e.g. −35% in March 2020.',
    read: 'What you actually live through. Smaller (closer to 0) is better; ask whether you could have held through it.' },
  { key: 'downsideDev', label: 'Downside deviation', short: 'Down dev', group: 'Risk', unit: '%', better: 'low', good: 9, bad: 13, source: 'computed',
    what: 'Like standard deviation, but counting only the months with negative returns.',
    read: 'Volatility that hurts. The input to the Sortino ratio.' },

  // ---- risk-adjusted
  { key: 'sharpe', label: 'Sharpe ratio', short: 'Sharpe', group: 'Risk-adjusted', unit: 'x', better: 'high', good: 1, bad: 0.6, source: 'factsheet',
    what: '(Fund return − risk-free rate) ÷ standard deviation: return earned per unit of total risk.',
    read: 'Above 1 is good for equity. Two funds with the same return: the higher Sharpe got there with less risk.' },
  { key: 'sortino', label: 'Sortino ratio', short: 'Sortino', group: 'Risk-adjusted', unit: 'x', better: 'high', good: 1.5, bad: 0.9, source: 'computed',
    what: 'Like Sharpe, but divides by downside deviation, so upside swings are not penalised.',
    read: 'Better than Sharpe for judging funds that claim to protect the downside. Higher is better.' },
  { key: 'treynor', label: 'Treynor ratio', short: 'Treynor', group: 'Risk-adjusted', unit: '%', better: 'high', source: 'factsheet',
    what: '(Fund return − risk-free rate) ÷ beta: return per unit of market risk.',
    read: 'Useful when the fund is one of several in a diversified portfolio, where only market risk matters.' },
  { key: 'infoRatio', label: 'Information ratio', short: 'Info ratio', group: 'Risk-adjusted', unit: 'x', better: 'high', good: 0.5, bad: 0, source: 'computed',
    what: '(Fund return − benchmark return) ÷ tracking error: how consistently the manager beats the index.',
    read: 'Above 0.5 is good, above 1 is excellent. Negative means the active bets are losing.' },
  { key: 'calmar', label: 'Calmar ratio', short: 'Calmar', group: 'Risk-adjusted', unit: 'x', better: 'high', source: 'computed',
    what: 'Yearly return ÷ the maximum drawdown (as a positive number).',
    read: 'Return per unit of worst-case pain. Higher is better.' },

  // ---- downside protection
  { key: 'downCapture', label: 'Downside capture ratio', short: 'Down cap', group: 'Downside protection', unit: '%', better: 'low', good: 85, bad: 100, source: 'computed',
    what: 'In months the benchmark fell, how much the fund fell, as a % of the benchmark’s fall. 80 means −8% when the market fell −10%.',
    read: 'The main “downside protection” measure. Below 100 means it falls less than the market; below 85 is strong protection.' },
  { key: 'upCapture', label: 'Upside capture ratio', short: 'Up cap', group: 'Downside protection', unit: '%', better: 'high', good: 100, bad: 85, source: 'computed',
    what: 'The same for rising months: how much of the market’s gain the fund captured.',
    read: 'The ideal fund has upside capture above 100 and downside capture below 100.' },

  // ---- costs & portfolio
  { key: 'ter', label: 'Expense ratio (TER)', short: 'TER', group: 'Costs & portfolio', unit: '%', better: 'low', good: 0.8, bad: 1.5, source: 'factsheet',
    what: 'The yearly fee taken from the fund’s assets (direct plan).',
    read: 'A certain drag on returns every year. Watch for increases; direct plans are 0.5–1 point cheaper than regular.' },
  { key: 'aum', label: 'Assets under management', short: 'AUM', group: 'Costs & portfolio', unit: '₹cr', better: 'high', source: 'factsheet',
    what: 'The fund’s size.',
    read: 'Very small funds are fragile; very large small/mid-cap funds struggle to deploy money. Watch for sharp outflows.' },
  { key: 'turnover', label: 'Portfolio turnover', short: 'Turnover', group: 'Costs & portfolio', unit: '%', better: 'low', good: 40, bad: 100, source: 'factsheet',
    what: 'How much of the portfolio is bought and sold in a year.',
    read: 'High turnover means hidden trading costs and a risk of drifting from the stated style.' },
  { key: 'top10', label: 'Top-10 holdings', short: 'Top 10', group: 'Costs & portfolio', unit: '%', better: 'low', good: 45, bad: 60, source: 'factsheet',
    what: 'Share of the portfolio in its ten largest stocks.',
    read: 'Higher is more concentrated: bigger wins and bigger losses from a few names.' },
  { key: 'cash', label: 'Cash and equivalents', short: 'Cash', group: 'Costs & portfolio', unit: '%', better: 'low', good: 5, bad: 10, source: 'factsheet',
    what: 'Share held in cash, TREPS and liquid instruments instead of stocks.',
    read: 'A little is normal. A lot means a market-timing call, or money the fund can’t deploy, and drags returns in rallies.' },
  { key: 'capMix', label: 'Market-cap mix vs mandate', short: 'Cap mix', group: 'Costs & portfolio', unit: '%', better: 'high', source: 'factsheet',
    what: 'Large / mid / small-cap split against the SEBI category rule (a large-cap fund must hold at least 80% large caps).',
    read: 'Drift outside the mandate is an anomaly: you are not getting the fund you chose.' },
  { key: 'overlap', label: 'Overlap with your other funds', short: 'Overlap', group: 'Costs & portfolio', unit: '%', better: 'low', source: 'factsheet',
    what: 'Share of the portfolio held in common with another of your funds.',
    read: 'Above 50% you are paying two fees for largely the same portfolio.' },

  // ---- debt
  { key: 'ytm', label: 'Yield to maturity', short: 'YTM', group: 'Debt funds', unit: '%', better: 'high', source: 'factsheet',
    what: 'The yield the portfolio would earn if every bond were held to maturity, before expenses.',
    read: 'The best guide to a debt fund’s future return. A yield far above peers usually means lower credit quality.' },
  { key: 'modDuration', label: 'Modified duration', short: 'Mod dur', group: 'Debt funds', unit: 'yrs', better: 'low', source: 'factsheet',
    what: 'How much the NAV moves for a 1-point change in interest rates (3 years ≈ 3% move).',
    read: 'Interest-rate risk. Match it to how long you will stay invested.' },
  { key: 'avgMaturity', label: 'Average maturity / Macaulay duration', short: 'Maturity', group: 'Debt funds', unit: 'yrs', better: 'low', source: 'factsheet',
    what: 'How long, on average, until the bonds repay (Macaulay duration weights by cash flows).',
    read: 'Longer means more sensitivity to rate changes.' },
  { key: 'credit', label: 'Credit quality', short: 'AAA+Sov', group: 'Debt funds', unit: '%', better: 'high', source: 'factsheet',
    what: 'Share in AAA-rated and sovereign (government) paper.',
    read: 'Default risk. Any downgrade of a holding is an anomaly worth acting on.' },

  // ---- people
  { key: 'managerTenure', label: 'Fund manager and tenure', short: 'Manager', group: 'People', unit: 'yrs', better: 'high', source: 'factsheet',
    what: 'Who runs the fund, and for how long.',
    read: 'A change of manager resets the track record: the past returns were someone else’s.' },
]

export const METRIC = Object.fromEntries(METRICS.map(m => [m.key, m])) as Record<string, MetricDef>

/** The columns the Scorecard grades (others are explained in Parameters but not scored). */
export const SCORED = ['ret3y', 'ret5y', 'vsBench3y', 'rollingBeat', 'stdDev', 'beta', 'sharpe', 'sortino', 'downCapture', 'upCapture', 'maxDD', 'ter', 'turnover', 'top10', 'cash']

export function grade(key: string, v: number | null | undefined): Grade | null {
  const m = METRIC[key]
  if (v == null || !m || m.good == null || m.bad == null) return null
  const hi = m.better === 'high'
  if (hi ? v >= m.good : v <= m.good) return 'good'
  if (hi ? v <= m.bad : v >= m.bad) return 'bad'
  return 'ok'
}

export const GRADE_POINTS: Record<Grade, number> = { good: 100, ok: 60, bad: 20 }

export const ANOMALY_RULES: { key: string; label: string; why: string }[] = [
  { key: 'manager', label: 'Fund manager changed', why: 'The track record belonged to someone else; watch the next 2–3 factsheets.' },
  { key: 'ter', label: 'Expense ratio up ≥ 0.10 pp', why: 'A permanent cut in your return.' },
  { key: 'aum', label: 'AUM down ≥ 15% in a month', why: 'Heavy redemptions can force selling.' },
  { key: 'beta', label: 'Beta or std dev up > 20%', why: 'The fund is taking more risk than before.' },
  { key: 'rank', label: 'Category rank down two quartiles', why: 'A sharp relative slide.' },
  { key: 'mandate', label: 'Market-cap mix outside the mandate', why: 'Style drift: not the fund you chose.' },
  { key: 'cash', label: 'Cash ≥ 2× its 12-month average', why: 'A timing call, or money it cannot deploy.' },
  { key: 'concentration', label: 'Top-10 holdings up ≥ 10 pp', why: 'More riding on fewer stocks.' },
  { key: 'credit', label: 'Credit downgrade in a debt holding', why: 'Default risk rose; check the exposure.' },
  { key: 'rolling', label: '3-year rolling return below the benchmark for 6 months running', why: 'Sustained underperformance, not a blip.' },
]

/** 0–100: the average of the graded scorecard cells (good 100, watch 60, weak 20); null when nothing can be graded. */
export function scoreOf(latest: Record<string, number | null | undefined>): number | null {
  const gs = SCORED.map(k => grade(k, latest[k])).filter((g): g is Grade => g != null)
  return gs.length ? Math.round(gs.reduce((s, g) => s + GRADE_POINTS[g], 0) / gs.length) : null
}
