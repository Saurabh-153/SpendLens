"""Baseline expense forecasting (Phase A): robust statistics, no ML library.

Per category the estimate for a month is the median of the last 6 months with data, nudged
towards the same month last year when that exists. The range is the 10th-90th percentile of
those months. For the month in progress, fixed items (steady every month) are expected at
their usual amount and variable ones blend the month-to-date run rate with the median.
A backtest replays past months using only earlier data and compares against the naive
"same as last month" guess, so the UI can say when the model is actually better.
"""
import calendar
import math
from datetime import date

from database import budget_for_month, categories_for_month

WINDOW = 6          # months of history behind an estimate
MIN_HISTORY = 3     # months needed before we forecast at all
BACKTEST_MONTHS = 12
SEASONAL_WEIGHT = 0.3


def _pct(vals, q):
    s = sorted(vals)
    k = (len(s) - 1) * q
    f = int(k)
    c = min(f + 1, len(s) - 1)
    return s[f] + (s[c] - s[f]) * (k - f)


def _median(vals):
    return _pct(vals, 0.5)


def _history(db, before):
    """{month: {category_id: total}} for months < `before` that hold any spend."""
    hist = {}
    for r in db.execute(
        "SELECT substr(date,1,7) AS ym, category_id, SUM(amount) AS t FROM expenses "
        "WHERE substr(date,1,7) < ? GROUP BY ym, category_id", (before,)
    ).fetchall():
        hist.setdefault(r["ym"], {})[r["category_id"]] = r["t"]
    return {m: c for m, c in hist.items() if sum(c.values()) > 0}


def _estimate(hist, months, cid, target):
    """(p50, p10, p90, fixed) for one category from the months listed (oldest first)."""
    vals = [hist[m].get(cid, 0) for m in months[-WINDOW:]]
    if not vals:
        return 0.0, 0.0, 0.0, False
    mean = sum(vals) / len(vals)
    fixed = False
    if len(vals) >= 4 and mean > 0 and sum(1 for v in vals if v > 0) >= len(vals) - 1:
        sd = math.sqrt(sum((v - mean) ** 2 for v in vals) / len(vals))
        fixed = sd / mean < 0.12 and (vals[-1] > 0)
    if fixed:
        # steady items (rent, EMI, fees) change in steps, so the latest amount is the best guess
        est = vals[-1]
        return est, min(est, _pct(vals, 0.1)), max(est, _pct(vals, 0.9)), True
    med = _median(vals)
    ly_key = f"{int(target[:4]) - 1}-{target[5:]}"
    est = med
    if ly_key in hist and len(vals) >= 3:
        est = (1 - SEASONAL_WEIGHT) * med + SEASONAL_WEIGHT * hist[ly_key].get(cid, 0)
    lo, hi = min(_pct(vals, 0.1), est), max(_pct(vals, 0.9), est)
    return est, lo, hi, fixed


def _backtest(hist, cids):
    months = sorted(hist)
    tested = [m for i, m in enumerate(months) if i >= MIN_HISTORY + 1][-BACKTEST_MONTHS:]
    cat = {c: {"m": [], "b": []} for c in cids}
    tot = {"m": [], "b": [], "ape_m": [], "ape_b": []}
    for t in tested:
        prior = [m for m in months if m < t]
        est_total = 0.0
        for c in cids:
            est = _estimate(hist, prior, c, t)[0]
            actual = hist[t].get(c, 0)
            base = hist[prior[-1]].get(c, 0)
            cat[c]["m"].append(abs(est - actual))
            cat[c]["b"].append(abs(base - actual))
            est_total += est
        actual_total = sum(hist[t].values())
        base_total = sum(hist[prior[-1]].values())
        tot["m"].append(abs(est_total - actual_total))
        tot["b"].append(abs(base_total - actual_total))
        if actual_total:
            tot["ape_m"].append(abs(est_total - actual_total) / actual_total)
            tot["ape_b"].append(abs(base_total - actual_total) / actual_total)
    avg = lambda a: sum(a) / len(a) if a else None
    per_cat = {c: {"mae_model": avg(v["m"]), "mae_base": avg(v["b"]), "n": len(v["m"])} for c, v in cat.items()}
    summary = {"months": len(tested), "mape_model": avg(tot["ape_m"]), "mape_base": avg(tot["ape_b"])}
    return per_cat, summary


def build_forecast(db, month, today=None):
    """Forecast for `month`, using only data from earlier months plus month-to-date spend."""
    today = today or date.today()
    days = calendar.monthrange(int(month[:4]), int(month[5:]))[1]
    cur = f"{today.year:04d}-{today.month:02d}"
    if month == cur:
        elapsed, mode = min(days, today.day), "in_progress"
    elif month > cur:
        elapsed, mode = 0, "future"
    else:
        elapsed, mode = days, "past"

    hist = _history(db, month)
    months = sorted(hist)
    budget = budget_for_month(db, month)
    base = {"month": month, "mode": mode, "elapsed": elapsed, "days": days, "budget_cap": round(budget["budget_cap"]),
            "history_months": len(months)}
    if len(months) < MIN_HISTORY:
        return {**base, "available": False, "reason": f"Needs at least {MIN_HISTORY} months of earlier data"}

    cats = categories_for_month(db, month)
    cids = [c["id"] for c in cats]
    per_cat, summary = _backtest(hist, cids)

    spent_now = {r["category_id"]: r["t"] for r in db.execute(
        "SELECT category_id, SUM(amount) AS t FROM expenses WHERE date LIKE ? GROUP BY category_id", (f"{month}-%",)).fetchall()}

    w = elapsed / days if mode == "in_progress" else 0.0
    out, sq_lo, sq_hi, total = [], 0.0, 0.0, 0.0
    for c in cats:
        cid = c["id"]
        est, lo, hi, fixed = _estimate(hist, months, cid, month)
        spent = spent_now.get(cid, 0.0) if mode == "in_progress" else 0.0
        if mode == "in_progress":
            if fixed:
                proj = spent if spent >= 0.9 * est else est
            else:
                run_rate = spent / elapsed * days if elapsed else est
                proj = max(spent, w * run_rate + (1 - w) * est)
            scale = 1 - w
            p_lo = max(spent, proj - (est - lo) * scale)
            p_hi = proj + (hi - est) * scale
        else:
            proj, p_lo, p_hi = est, lo, hi
        bt = per_cat.get(cid, {})
        reliable = bool(bt.get("n", 0) >= 3 and bt["mae_base"] is not None and bt["mae_model"] <= bt["mae_base"])
        total += proj
        sq_lo += (proj - p_lo) ** 2
        sq_hi += (p_hi - proj) ** 2
        if proj > 0 or spent > 0:
            out.append({"id": cid, "name": c["name"], "icon": c["icon"], "fixed": fixed, "reliable": reliable,
                        "spent": round(spent), "p10": round(p_lo), "p50": round(proj), "p90": round(p_hi),
                        "mae_model": None if bt.get("mae_model") is None else round(bt["mae_model"]),
                        "mae_base": None if bt.get("mae_base") is None else round(bt["mae_base"])})
    out.sort(key=lambda r: -r["p50"])
    return {**base, "available": True,
            "total": {"p10": round(total - math.sqrt(sq_lo)), "p50": round(total), "p90": round(total + math.sqrt(sq_hi))},
            "categories": out, "backtest": summary,
            "model_beats_baseline": bool(summary["mape_model"] is not None and summary["mape_base"] is not None
                                         and summary["mape_model"] <= summary["mape_base"])}
