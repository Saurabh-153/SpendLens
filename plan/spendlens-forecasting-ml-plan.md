# SpendLens – Forecasting & ML plan

Status of this document: planning notes for future work. Phase A is built; everything else is not started.

This is **Phase 5** of the wider product roadmap in [ROADMAP.md](../ROADMAP.md): the models here get
much better data once statement import (roadmap Phase 1B) lands, so the phases below sit after it.

## Where things stand

| Phase | What | Status |
|---|---|---|
| A | Statistical baseline forecast, backtest, dashboard cards | **Done** |
| A+ | Lumpy / annual payments handled separately | Planned (next) |
| B | Real time-series / ML models, anomaly detection | Not started |
| C | Stored forecasts, accuracy tracking, suggestions in Admin | Not started |

### Phase A – what exists today
- Code: `spendlens/forecast.py`; endpoint `GET /forecast?month=` in `spendlens/routes/api.py`; UI in `artifacts/spendlens/src/components/Dashboard.tsx` (Projected month-end, Pace chart dotted line, Forecast card); client `getForecast` in `src/api.ts`.
- Nothing is trained or stored: the numbers are recomputed from `spendlens_v2.db` on every request.
- Per category: median of the last 6 months with data, 30% nudged toward the same month last year; steady items (e.g. Rent, CV < 0.12) use their latest amount. Range = 10th–90th percentile of those months.
- Month in progress: fixed items at their usual amount; variable items blend the month-to-date run rate with the median (weight = share of month elapsed).
- Backtest: replays up to 12 past months using only earlier data and compares with "same as last month". Categories where the model does not beat that baseline show "low confidence". Needs ≥ 3 months of earlier data.
- Measured (Oct-26): total error ≈ 17% vs 24% for the naive guess; Nov-26 ≈ 20% vs 23%.
- Constants at the top of `forecast.py`: `WINDOW`, `MIN_HISTORY`, `BACKTEST_MONTHS`, `SEASONAL_WEIGHT`.

### Known weakness (found in Oct-26)
School Fees: ₹1,00,000 in Oct-24 and ₹87,500 in Oct-25, ~₹5–15k in other months. The seasonal blend turns this into a ₹27k estimate, which is neither outcome and inflates the month total by ~₹20k. Low salary-minus-saving caps (e.g. Oct-26 ₹91,993 vs typical spend ₹1.0–1.25L) also make every projection look "over".

---

## Phase A+ – lumpy / annual payments (do this first)
Goal: a big annual bill must not distort the "typical month" number, but must still be visible.

1. Detect lumpy items per category: a month whose amount is > 3× the category's median (and above a minimum, e.g. 2% of salary).
2. Seasonal recurrence: if the same calendar month had a lumpy payment in ≥ 1 earlier year, mark it "expected this month".
3. Remove lumpy months from the median/percentile window (and from the seasonal blend) so the regular estimate is clean.
4. Return them separately: `lumpy: [{category, expected_amount, seen_in: ['2024-10','2025-10'], paid_this_month: bool}]`.
5. UI: Projected month-end shows the regular figure; a line beneath says e.g. "+ School Fees ~₹88k possible (paid Oct 2024, 2025)". Forecast card shows "without / with" totals. Once the payment is logged it becomes part of actual spend.
6. Backtest must score the regular part and the lumpy flag (hit / miss) separately.

Acceptance: Oct-26 regular projection ≈ ₹1.15–1.2L; the lumpy line is shown; no category estimate is a blend of "small" and "huge".

## Phase B – ML models
Data reality: ~34 months, 12–19 categories, ~2.5k expense rows. Too little for deep learning; prefer simple, well-calibrated models and always compare with the baseline in the backtest. A model ships only if it beats the baseline on the rolling backtest.

### B1. Monthly per-category model
- Candidates: ETS / Holt-Winters or seasonal-naive (`statsmodels`), regularised linear / gradient boosting (`scikit-learn`) as challenger.
- Features: month of year, lag 1–3 and rolling 3/6-month mean, days in month, salary / bonus month flag, lumpy flag, number of weekend days, previous-year same month.
- Pooling: one model across categories with category as a feature (more data per model) vs one per category; test both.
- Output: P10 / P50 / P90 (quantile regression or conformal intervals from backtest residuals).

### B2. Daily model for the month in progress
- Predict the rest of the month: gradient boosting on weekday, day of month, category, fixed-item due dates (rent on the 1st etc.), plus spend so far.
- Replaces the run-rate blend once it beats it in the backtest.

### B3. Anomaly detection
- Flag a category/day outside its usual range (robust z-score / IQR first; Isolation Forest only if needed).
- Feeds the dashboard "Worth a look" list.

### B4. Optional later
- Sub-category level forecasts (data is thinner – only after review queue is cleared).
- Salary / bonus forecast to project the budget cap.
- Savings projection ("at this pace you save ₹X by year end").

## Phase C – productisation
- New module layout: `spendlens/forecast/` (features, models, backtest, service) replacing the single file; keep `build_forecast()` as the entry point so the API and UI do not change.
- Storage in `spendlens_v2.db`:
  - `forecasts(month, category_id, p10, p50, p90, model, trained_at)`
  - `forecast_scores(month, model, mape, mae, baseline_mape)`
- Trained model files (if any) in `spendlens/models/` (git-ignored); retrain when data changes or monthly, via a lightweight job – never block a page load.
- Accuracy tracking: when a month closes, compare the stored forecast with actual and show "forecast was within 4%" on the dashboard.
- UI: dotted projection with range on the Pace chart (exists), next-month card (exists), target suggestions in Admin → Targets ("Groceries averaged 6.1% of salary; target is 5%"), per-category confidence.
- Dependencies are added to `spendlens/requirements.txt` only when a model needs them (`numpy`, `scikit-learn`, `statsmodels`); document in README.

## Evaluation rules (all phases)
- Rolling-origin backtest only – never train on the future. Metrics: MAPE and MAE for total and per category, interval coverage (P10–P90 should contain ~80% of actuals).
- Baselines to beat: same as last month, median of last 3, seasonal naive.
- Show low-confidence categories instead of hiding them; do not show a forecast with fewer than 3 months of history.
- Months with blank data are treated as missing, not zero.

## Data quality items to settle before Phase B
- Negative entries (e.g. School Fees −₹7,500 in Jun/Jul-25 – refunds?) – decide how they are treated.
- Imported future months (Nov/Dec-26) are in the database; keep them out of training for earlier months.
- One-off events (festival, travel, medical) – optional tag so they can be excluded from "typical" estimates.
- Fixed items list: auto-detected today (only Rent / EMI); allow a manual "fixed" flag per category in Admin if auto-detection misses (EMIs, subscriptions).

## Open questions
1. Is a ₹ annual payment (school fee) the only lumpy item, or also insurance, taxes, travel?
2. Should the budget-cap comparison use the plain cap, or cap plus expected lumpy payments?
3. Category-level forecasts only, or sub-category level too?
4. How often should models retrain (on demand, nightly, monthly)?
