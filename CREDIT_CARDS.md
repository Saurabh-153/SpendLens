# Credit-card profit module

The SpendLens **Cards** page. See [ROADMAP.md](ROADMAP.md) for everything else.

**Status: C0, C1 and the core of C2 are built**, plus the statement importer that was
planned for C4 (it came first because the statements were to hand). Five cards on four bills
are loaded: the CASHBACK SBI Card, the Amazon Pay ICICI card, two ICICI Sapphiro cards that share
one bill, and the BOB Eterna card. An *All cards* usage view sits above the per-card pages. Working today: PDF import for both
banks with validation and de-duplication, an earn engine with per-card reward classes and
refund clawback, merchant corrections, the fee-waiver and utilisation meters, the leakage
report, and **when to pay** (below). Still to do: the best-card recommender (which card for
this spend, now that there are two to choose between), milestones, points and redemption (C3).

## Objective

Maximise, per card per year:

```
net profit = rewards earned + benefits realised − annual fee − interest paid
```

…and never put a rupee on the wrong card. Four levers, all in scope: the earn rate on
each spend, fee versus milestone value, the value you actually get per point, and the
float and credit-score safety.

## How card spend gets in

Rows arrive by **statement import**: PDFs are browsed for or dropped on the Cards page,
each is validated against its own "Purchases & Other Debits" total, and de-duplicated by
a row hash, so re-importing an overlapping statement adds nothing. The PDF password is
supplied per upload and never stored, and the PDF itself is not kept.

**Parsing is per bank, not general.** A reader is a detector plus a parser in the
`PARSERS` registry (`spendlens/cards.py`): SBI Card and ICICI Bank exist. Unknown formats are
rejected, or — if the user opts in and `ANTHROPIC_API_KEY` is set — read by Claude, whose
output must pass the same arithmetic check (transactions sum to the statement's own
purchases figure) before anything is saved. A format Claude has read successfully is a
good candidate for a proper hand-written reader, which is free, instant and private.

They land in `card_txns`, **not** in `expenses`. This is a change from the original
plan, which had card spend going into `expenses` with a `card_id`. The imported
statements cover months whose expenses are already entered by hand, so merging them
would double count the same spending — ₹3.88L of it. Linking the two becomes its own
explicit step with de-duplication against the existing rows, once the `accounts` model
from Phase 1A exists.

A card is also an `accounts` row of kind `card` (Phase 1A), so its outstanding balance
counts against net worth like any other liability.

## When to pay

A card lends you the money from the day you spend until the bill's **due date**, free. Paying
the day the bill arrives, or paying as you go, hands that float back. So the best day to pay
is the due date, less a safety margin. The two errors are not symmetric:

    one day early costs   amount x rate / 365                  a few rupees
    one day late costs    a fee + ~45% a year on the whole cycle   hundreds

which is why the default margin is a day, not zero, and why the date steps back off a weekend
(a payment made on a Saturday or Sunday may not be credited until Monday).

**What it needs: a billing cycle** - the statement day and the days from there to the due
date. They are read where a statement prints them (SBI: statement on the 11th, due exactly 20
days later, in all ten statements) and otherwise *assumed and marked as such*. A wrong due
date gives a wrong pay date, so an unverified cycle is flagged until you confirm it.

**What it measures.** Payments are matched to spends oldest first. For each rupee: the days of
credit actually used, the days available (spend to due date), and the days earlier than the
best date it was paid. The money value is `amount x days early x rate / 365`, where *rate is
what your idle cash would earn* (default 7%, a liquid fund; a savings account is nearer 3%),
not what the card charges. A payment made before the spend exists is a genuine pre-payment and
keeps its own early date; credits dated before the first spend are ignored, because they pay a
balance from before the data begins.

**What your statements showed.** Both cards are paid within about five days of spending, out of
roughly 33-35 days available:

| | SBI Cashback | Amazon Pay ICICI |
|---|---|---|
| Free credit actually used | 5 of 33 days | 4 of 35 days |
| Paid earlier than the best day | ~28 days | ~28 days |
| Float given away | ~₹2,400 a year | ~₹630 a year |
| Cycle | read from statements (verified) | assumed, 16th + 20 days (unverified) |

These are worth having and modest: at a 7% rate the whole SBI saving is about ₹200 a month, and
at a savings-account rate it is under half that. The point is not the amount; it is that the
change costs nothing and removes a decision. The ICICI figure is smaller mainly because most
spend moved to the SBI card in late 2025, and its pay dates rest on an assumed cycle.

## Data model

| Table | What it holds |
|---|---|
| `cards` | issuer, network, name, last 4, credit limit, statement day, due day, annual fee, fee-waiver spend, anniversary month, points currency, your own ₹-per-point valuation, status (`active` / `downgrade` / `closed`) |
| `card_reward_rules` | per card: scope (category, MCC, merchant, online vs offline, or all), earn as % cashback or points per ₹100, **cap per cycle / month / year**, minimum transaction, exclusions, `valid_from` / `valid_to` |
| `card_milestones` | spend threshold, period, the benefit, your ₹ value for it, achieved flag |
| `card_statements` | cycle, total, due date, paid date and amount, interest charged, points earned — the anchor that imported rows reconcile against |
| `card_points` | balance in lots with expiry dates |
| `card_redemptions` | what was redeemed, for what, and the realised ₹ per point |

Reward rules are **effective-dated**, exactly like `category_targets`, because issuers
change terms and last year's cashback must stay last year's cashback. Exclusions matter
more than they look: rent, fuel, wallet loads, insurance, government and education
payments are commonly excluded or capped, and a model without them overstates earnings.

## Engines

**1. Earn engine.** Walks a cycle's transactions in date order, applies the matching
rule, and tracks cap consumption as it goes, writing points or rupees earned per
transaction. Cap-aware ordering is the hard part and is exactly where a spreadsheet
gives the wrong answer.

**2. Best-card recommender.** Input: amount, category or merchant, date. Output: a
ranked list by **marginal** earn — what the next rupee earns given the caps already
used this cycle — tie-broken by progress towards the fee waiver, proximity to a
milestone, and float days. This is the screen that gets used daily.

**3. Leakage report.** For every past transaction, what was earned versus what the best
card you already held would have earned. Ranked by merchant and category, so the fix is
one habit rather than a spreadsheet lookup per purchase.

**4. Fee versus value P&L.** Per card per year: rewards plus benefits realised minus the
fee, with a **keep / downgrade / close** verdict and the renewal date. Answers the one
question most people get wrong by never asking it.

**5. Points and redemption.** Balances, lots about to expire, ₹ per point by redemption
path, and a warning when a redemption would fall below your own valuation.

**6. Float and safety.** Which card gives the longest interest-free period for a given
date; a due-date calendar with "pay by" reminders; utilisation per card and overall,
with a suggested pre-statement-date paydown to protect the credit score; and the
minimum-due interest trap shown in rupees rather than as a percentage.

## The dashboard

One page, four rows.

- **Hero** — ₹ earned this financial year and the effective % on card spend, against
  what was achievable.
- **Use this card** — pick a category or type an amount, get the card and the reason.
- **Per-card tiles** — net profit this year, fee-waiver progress bar, utilisation.
- **Attention** — points expiring, the due-date calendar, and the top five leakages
  with the rupee value of fixing each.

## Phases

| | Scope | Why here |
|---|---|---|
| **C0** | `cards` table, `card_id` on expenses, tag spends to a card, dues as a liability | Useful on day one and unblocks everything else |
| **C1** | Reward rules, the earn engine, "₹ earned" and the leakage report | The core of the module |
| **C2** | Best-card recommender, float and due-date calendar, utilisation guard | The daily-use surface |
| **C3** | Fees, milestones, points, redemption valuation, keep / close verdict | The annual decisions |
| **C4** | Card-statement importer (CSV, then PDF) with reconciliation against C1's computed points | Shares Phase 1B's importer framework, which is why it comes last |

## The ICICI account: four numbers, two cards, one bill

Six yearly statements (FY2020-FY2025, downloaded twice, so twelve files) cover one ICICI account.
Reading them settled three things the first ICICI card had not.

- **A statement is per account, not per card.** It has a section per card number plus an
  account-level `0000` section. Four numbers appear: ...7000, ...7018, ...4005 and ...5007.
- **The bill is shared.** Payments were posted under ...4005 while settling ...5007's spend too
  (...4005 showed ₹18.6L of credits against ₹12.8L billed; ...5007 ₹6.2L billed against ₹0.5L
  paid). Pay-timing per card would have been nonsense, which is why a billing account exists.
- **Which numbers are one card is an inference.** ...7000 became ...7018 on the same day,
  ...7018 stopped on 1 Jan 2022 and ...4005 began 20 days later, with the same Hyderabad
  merchants (the same supermarket, the same fuel station) running across all three. ...5007 began
  in March 2025 while ...4005 was still in use, with Bangalore merchants. So: one card replaced
  twice, and a second, newer card. The window is 120 days because there were 95 days without a
  purchase between ...7000 and ...7018; years later, or overlapping, is a different card.

What it cannot know: the products. Nothing in the file names them, so these cards are *usage
only* until you pick a reward scheme, and no reward is invented. The due date is not printed
either, so the cycle is assumed until confirmed. A card that has not been used for three months
is shown as retired (...4005's last purchase was 5 Dec 2025).

## BOB Eterna: a statement that can be held to the same standard as SBI's

Monthly BOBCARD statements print a statement date and a due date, an at-a-glance block (opening balance,
payments, new purchases, closing balance) and a reward-points summary (opening, earned, redeemed, closing), so the
import is checked the strict way: the lines must add up to the printed totals, and the billing cycle (statement
on the 25th, due 19 days later) is read rather than assumed. The points are printed on every transaction too, so
rewards are *read*. Findings from eight statements and 238 transactions:

- **Two PDF layouts of one statement.** One extracts a field per line; the other extracts one *character* per
  line by default but gives clean columns in layout mode, which `read_pdf` now falls back to automatically.
  Both are flattened into one stream of fields and read by one parser. They agree on every figure and every line
  except one thing: a font quirk prints `UPI-THE_RASAGANGA_VEG_` as `UPI-THE RASAGANGA VEG`, so underscores are
  normalised (on this parser only: another parser's stored row hashes must not change) and the second layout of
  a statement imports nothing new.
- **One statement contradicts itself.** The table layout shows 152 points on a purchase the monthly layout shows
  as 76, putting its line points at 1,107 against a printed total of 1,040. When lines exceed the printed total
  the per-line points are dropped and the printed total kept, so import order cannot change the answer. Points on
  the lines may fall *short* of the total (bonus and adjustment points belong to no line), and that is accepted.
- **Header edge cases that broke the first parse:** a zero opening balance is printed as a bare 0 (three figures,
  not four); a credit balance prints as `-.21` with no leading digit; and with nothing due the header has no DR/CR
  to close it and ran into the first transaction.
- **Earn rates match the terms.** A Rs 4,900 Amazon purchase earned 735 points: 15 per Rs 100, as published for
  online, travel, dining and movies; UPI spends earn about 3 per Rs 100.
- **A missing statement.** The folder had no August statement. That hid the payment of July's bill and showed it
  as Rs 6,377 paid late. Pay timing is now computed within each unbroken run of statements, so a gap cannot
  masquerade as a late payment, and the page names what is missing.

## A correction: the ICICI products (twice)

The two-card ICICI account was first set up as Rubyx because the files sat in a folder called "rubyx", then as
Sapphiro on the user's say-so, then the user's free-text answers contradicted each other ("005 and 007 are
Sapphiro", then "rubyx is 4005, sapphiro are 006 and 007", and no card ends in 006). The statements never name
the product, so every one of those was an unverified assumption applied to live settings. It was settled only by
asking per card number, listing the numbers that really exist:

- **···4005 is Rubyx**, and its earlier numbers ···7018 and ···7000 are the same card re-issued.
- **···5007 is Sapphiro.**
- They share one bill, so one account statement lists both; the "rubyx" folder held that same statement all along.

Both schemes exist in the code, with their own milestone and lounge terms (Rubyx 3,000 points at Rs 3L and 1,500
per further lakh, 2 lounge visits on the previous quarter's spend over Rs 75,000; Sapphiro 4,000 at Rs 4L and 2,000
per lakh, 4 visits on the quarter's own spend of Rs 75,000 or more). With Rubyx on the right card, ···4005's
estimated rewards including milestone bonuses are about Rs 7.6k against Rs 7.3k of EMI interest and fees.

Separately, a re-upload added 228 duplicate rows in testing after a tidy-up changed the description of payment
lines ("THANK" to "THANK YOU") and with it their de-duplication hash. Rows are now pinned by a test, including a
check that every stored row in the real database can still be recognised by the current hash.

## What the first ICICI statements added

The Amazon Pay ICICI statements are not like SBI's. ICICI issues a **yearly transaction list**
(`01/04/2025 TO 31/03/2026`) with no account summary: no purchases total, no limit, no
statement or due date. That broke two assumptions.

- **The arithmetic check had nothing to compare against.** SBI imports are checked against the
  statement's own purchases total. ICICI's check is *coverage* instead: every date-led line
  must parse, or the file is rejected, because a line silently skipped is a missing transaction.
- **EMI conversions are messy, so the parser does not interpret them.** A conversion is booked as
  the purchase, a same-day reversal, then principal, interest and tax month by month; December
  2023 held a re-billed purchase, two conversions and a foreclosure with partial reversals inside
  one week. Pairing every reversal with its purchase would be guessing at intent. The model
  relies on what is always true instead - every line is a billed debit or a credit - so net spend
  = purchases - refunds + EMI instalments, a cash view, and the books close: net spend + fees
  equals payments + cashback + what is still owed, exactly, over five years (₹798 outstanding).

Other findings: the statement day moved from the 12th to the 27th to the 16th across the years,
so no single cycle describes the history; the reward earned is not printed, so it is an
*estimate* from the card's rates and cannot be reconciled; and the Amazon Pay terms (5% on
Amazon with Prime, 2% at partners, 1% elsewhere, uncapped; EMI, fuel, rent, education and
government earn nothing) come from the issuer's published terms, with the partner list the
least certain part.

A bug in the first import was found while reconciling: two genuinely identical same-day lines
(two ₹40 canteen purchases) hashed alike and collapsed into one, so stored spend was ₹97 short
of the statements. Each repeat now gets its own hash, and a test asserts that stored spend
equals the statement total.

## What ten real statements established

Built and calibrated against ten CASHBACK SBI Card statements, Dec 2025 - Sep 2026
(₹3.88L of spend, 481 transactions, ₹16,577 of cashback).

- **EMI conversions still earn cashback.** The statements only reconcile if spends
  converted to EMI are counted, which contradicts the usual "no cashback on EMI"
  summary of the card's terms.
- **The per-cycle cap is not ₹2,000.** One cycle paid ₹2,848, which several comparison
  sites' figure would have made impossible. The real cap was never reached in ten
  months, so it cannot be measured from this data: `cards.cashback_cap` is a setting,
  defaulting to ₹5,000, and the engine applies it in date order.
- **Fees and GST are not transactions.** They appear only in the summary block, so
  parsing transactions alone understates what the statement charged.
- **The statement never says which spend was online.** This is the heart of the problem:
  the 5%-versus-1% split has to be inferred per merchant. The engine classifies by rule
  and always shows its computed total next to what was actually paid, so the error is
  visible rather than hidden. The default rules land within 1.9% over ten months and
  within ₹123 on the worst single month.

A first attempt fitted each merchant's class to the ten cashback totals by
coordinate descent. It reached a near-perfect fit and was discarded: 75 free parameters
against 10 equations is overfitting, and it "learned" that an office canteen was an
online merchant. The shipped rules are the readable ones, with the residual on display.

## The one unavoidable chore

Somebody has to enter the reward rules; no free, reliable feed of Indian card terms
exists. C1 ships a rule form plus a JSON import so a card can be set up in a couple of
minutes, and a starter set is seeded for the cards actually held once that list exists.

## Verification

- The earn engine's computed points for one real past cycle match the points line on
  that statement. That single test validates the rules, the caps and the exclusions at
  once.
- Caps: a synthetic cycle that crosses a cap earns the accelerated rate up to it and the
  base rate after, to the rupee.
- Importing the same statement twice adds no rows, and the imported total equals the
  statement total.
- `pytest` against a copy of the database, `pnpm run typecheck`, `pnpm build`, and the
  dataviz palette validator on the new charts.
