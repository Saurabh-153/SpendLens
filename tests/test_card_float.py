"""The "when to pay" engine. Every expected value here is worked out by hand in the test,
not taken from the code, so a wrong formula cannot agree with itself."""
from datetime import date, timedelta

import pytest

import card_float as cf

D = date


# ------------------------------------------------------------------ the calendar

def test_statement_on_or_after_includes_the_statement_day():
    assert cf.statement_on_or_after(D(2026, 9, 11), 11) == D(2026, 9, 11), "a spend on the statement day is on that bill"
    assert cf.statement_on_or_after(D(2026, 9, 10), 11) == D(2026, 9, 11)
    assert cf.statement_on_or_after(D(2026, 9, 12), 11) == D(2026, 10, 11)


def test_statement_rolls_over_the_year_and_clamps_short_months():
    assert cf.statement_on_or_after(D(2026, 12, 20), 11) == D(2027, 1, 11)
    assert cf.statement_on_or_after(D(2026, 2, 5), 31) == D(2026, 2, 28), "day 31 in February is the 28th"
    assert cf.statement_on_or_after(D(2028, 2, 5), 31) == D(2028, 2, 29), "and the 29th in a leap year"


def test_pay_on_is_buffer_days_before_due():
    assert cf.pay_on(D(2026, 10, 1), 1) == D(2026, 9, 30)      # a Thursday -> Wednesday
    assert cf.pay_on(D(2026, 10, 1), 0) == D(2026, 10, 1)


@pytest.mark.parametrize("due,buffer,expected", [
    (D(2026, 10, 31), 1, D(2026, 10, 30)),   # due Saturday, buffer 1 -> Friday
    (D(2026, 11, 1), 1, D(2026, 10, 30)),    # due Sunday, one day before is Saturday -> Friday
    (D(2026, 11, 2), 1, D(2026, 10, 30)),    # due Monday, one day before is Sunday -> Friday
    (D(2026, 10, 31), 0, D(2026, 10, 30)),   # due Saturday, no buffer -> still Friday
])
def test_pay_on_never_lands_on_a_weekend(due, buffer, expected):
    assert cf.pay_on(due, buffer) == expected
    assert cf.pay_on(due, buffer).weekday() < 5


# ------------------------------------------------------------------ pairing

def test_payments_settle_the_oldest_charge_first():
    charges = [(D(2026, 1, 1), 100), (D(2026, 1, 5), 50)]
    credits = [(D(2026, 1, 10), 120, False)]
    pairs, owing = cf.pair_payments(charges, credits)
    assert [(p[0], p[2]) for p in pairs] == [(D(2026, 1, 1), 100), (D(2026, 1, 5), 20)]
    assert owing == 30, "50 - 20 of the second charge is still unpaid"


def test_a_payment_can_be_split_across_charges_and_a_charge_across_payments():
    charges = [(D(2026, 1, 1), 100)]
    credits = [(D(2026, 1, 3), 30, False), (D(2026, 1, 9), 70, False)]
    pairs, owing = cf.pair_payments(charges, credits)
    assert sorted((p[1], p[2]) for p in pairs) == [(D(2026, 1, 3), 30), (D(2026, 1, 9), 70)]
    assert owing == 0


def test_a_prepayment_keeps_its_own_early_date():
    """Paid before the spend existed: it settles the next charge but the money left on the 2nd."""
    pairs, owing = cf.pair_payments([(D(2026, 1, 1), 10), (D(2026, 1, 20), 100)],
                                    [(D(2026, 1, 2), 100, False)])
    # 10 settles the first charge, the other 90 waits and is matched to the Jan 20 charge
    assert (D(2026, 1, 20), D(2026, 1, 2), 90) in [(p[0], p[1], p[2]) for p in pairs]
    assert owing == 10


def test_credits_before_the_first_charge_are_ignored():
    """They pay a balance from before the data begins; treating them as prepayments would be wrong."""
    pairs, owing = cf.pair_payments([(D(2026, 3, 1), 100)], [(D(2026, 2, 1), 100, False)])
    assert pairs == [] and owing == 100


def test_statement_dates_ride_along_with_the_charge():
    pairs, _ = cf.pair_payments([(D(2026, 1, 11), 100, D(2026, 1, 11))], [(D(2026, 1, 15), 100, False)])
    assert pairs[0][4] == D(2026, 1, 11)


def test_no_charges_is_not_an_error():
    assert cf.pair_payments([], [(D(2026, 1, 1), 5, False)]) == ([], 0.0)


# ------------------------------------------------------------------ the habit and what it costs

SDAY, GRACE, BUF, RATE = 11, 20, 1, 7.0


def one_bill(paid_on, amount=10000.0, spent=D(2026, 1, 5)):
    """A single spend on 5 Jan: statement 11 Jan, due 31 Jan, best day Thu 29 Jan (buffer 1)."""
    pairs, _ = cf.pair_payments([(spent, amount)], [(paid_on, amount, False)])
    return cf.habit(pairs, SDAY, GRACE, BUF, RATE)


def test_paying_on_the_best_day_costs_nothing():
    h = one_bill(D(2026, 1, 29))                 # due 31 Jan (Sat) - buffer 1 = 30 Jan (Fri)
    assert cf.pay_on(D(2026, 1, 31), BUF) == D(2026, 1, 30)
    h = one_bill(D(2026, 1, 30))
    assert h["forgone"] == 0 and h["days_early"] == 0 and h["late_amount"] == 0
    assert h["on_time_pct"] == 100.0


def test_paying_immediately_costs_exactly_the_float_given_away():
    """Spent and paid on 5 Jan; best day is 30 Jan: 25 days early. 10,000 x 25 days x 7% / 365."""
    h = one_bill(D(2026, 1, 5))
    assert h["days_early"] == 25.0
    assert h["forgone"] == pytest.approx(10000 * 25 * 7 / 36500, abs=0.01)   # = 47.95
    assert h["days_credit_used"] == 0 and h["days_credit_available"] == 26.0   # 5 Jan -> due 31 Jan
    assert h["on_time_pct"] == 0.0


def test_paying_after_the_due_date_is_flagged_late_and_costs_no_float():
    h = one_bill(D(2026, 2, 3))
    assert h["late_amount"] == 10000
    assert h["forgone"] == 0, "paying late wastes no float; it costs interest, reported separately"
    assert h["days_early"] < 0


def test_refunds_and_cashback_are_not_counted_as_payments():
    """A refund settles a charge for free; only money out of your own pocket has a float cost."""
    pairs, _ = cf.pair_payments([(D(2026, 1, 5), 1000)], [(D(2026, 1, 6), 1000, True)])
    h = cf.habit(pairs, SDAY, GRACE, BUF, RATE)
    assert h["paid"] == 0 and h["forgone"] == 0


def test_the_yearly_figure_scales_by_the_span():
    # two spends 100 days apart, both paid at once: the history spans 100 days
    charges = [(D(2026, 1, 5), 10000), (D(2026, 4, 15), 10000)]
    credits = [(D(2026, 1, 5), 10000, False), (D(2026, 4, 15), 10000, False)]
    pairs, _ = cf.pair_payments(charges, credits)
    h = cf.habit(pairs, SDAY, GRACE, BUF, RATE)
    assert h["span_days"] == 100
    assert h["forgone_per_year"] == pytest.approx(h["forgone"] * 365 / 100, abs=0.02)


def test_cycles_are_listed_newest_first_with_their_pay_dates():
    charges = [(D(2026, 1, 5), 100), (D(2026, 2, 5), 200)]
    credits = [(D(2026, 1, 6), 100, False), (D(2026, 2, 6), 200, False)]
    h = cf.habit(cf.pair_payments(charges, credits)[0], SDAY, GRACE, BUF, RATE)
    assert [c["statement"] for c in h["cycles"]] == ["2026-02-11", "2026-01-11"]
    assert h["cycles"][0]["due"] == "2026-03-03" and h["cycles"][0]["billed"] == 200


# ------------------------------------------------------------------ the forward calendar

def test_upcoming_gives_statement_due_and_pay_dates_in_order():
    up = cf.upcoming(D(2026, 10, 4), 11, 20, 1, 7.0, expected=36500, n=3)
    assert [u["statement"] for u in up] == ["2026-10-11", "2026-11-11", "2026-12-11"]
    first = up[0]
    assert first["due"] == "2026-10-31"
    assert first["pay_on"] == "2026-10-30"                      # Saturday due date -> Friday
    assert first["days_to_pay"] == 26
    # the bill is available the day after the statement (12 Oct): 18 days before 30 Oct
    assert first["days_kept"] == 18
    assert first["kept_value"] == pytest.approx(36500 * 18 * 7 / 36500, abs=0.01)   # = 126


def test_upcoming_on_the_statement_day_counts_that_statement():
    assert cf.upcoming(D(2026, 10, 11), 11, 20, 1, 7.0)[0]["statement"] == "2026-10-11"


def test_previous_is_the_last_issued_statement():
    p = cf.previous(D(2026, 10, 4), 11, 20, 1)
    assert p["statement"] == "2026-09-11" and p["due"] == "2026-10-01" and p["pay_on"] == "2026-09-30"
    assert p["days_to_pay"] == -4, "the pay date was four days ago"


def test_previous_on_the_statement_day_steps_back_one_more():
    assert cf.previous(D(2026, 10, 11), 11, 20, 1)["statement"] == "2026-09-11"


def test_a_zero_expected_bill_values_nothing():
    assert cf.upcoming(D(2026, 10, 4), 11, 20, 1, 7.0, expected=0)[0]["kept_value"] == 0
