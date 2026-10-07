# SpendLens monetization plan

Drafted Oct 2026. Based on [ROADMAP.md](../ROADMAP.md), [CREDIT_CARDS.md](../CREDIT_CARDS.md),
`spendlens/app.py`, `spendlens/routes/api.py` and the card modules.

## 1. Where the app stands

**What's worth paying for:** the **Cards module**. Indian finance apps already track expenses and
portfolios for free (INDmoney, Kuvera, CRED, Fold, Axio), so nobody will pay for those parts. Very
few products do what this one does:

- read SBI, ICICI, HDFC, Amex and BOB statements and check them against each statement's own totals
- show what each card earned against what it could have earned (the leakage report)
- tell you the best day to pay, and track fee-waiver progress
- suggest which card to use for a purchase (`card_advisor.py`)

People who juggle several reward cards (the TechnoFino and CardExpert crowd) count rewards in
rupees and already pay for tools. **Lead with Cards; expenses and portfolio come along as free
extras.**

**What blocks selling it today:**

| Blocker | Evidence |
|---|---|
| Only one user, no login | `user_id` columns exist (migration 3), but `cards.py` and `portfolio.py` never filter by them, and `api.py` hardcodes `user_id=1` |
| The API is open to anyone | `allow_origins=["*"]` and no auth in `app.py`. Fine on localhost, not on the internet |
| SQLite file, one process, background scheduler in the same process | `app.py` starts `start_scheduler` inside the web process |
| Card rules are written for the owner's own cards | Hand-written rate table in `card_advisor.py`, the Rubyx/Sapphiro panels, card-number inference rules |
| Claude statement fallback runs on the owner's API key | Every unknown statement a user uploads would cost money |
| No legal or billing layer | No privacy policy, consent, payments or plan limits |

## 2. Revenue model (in priority order)

### A. Freemium subscription — the main income

| | Free | Pro (about ₹149/month or ₹999/year) |
|---|---|---|
| Expense grid, budgets, dashboard | ✓ | ✓ |
| Cards | 1 card, last 3 statements | Unlimited cards and history |
| Leakage report, best-card advice, when to pay, fee P&L | Teaser: the total ₹ shown, details blurred | Full |
| Portfolio, XIRR, goals | Basic | Monte Carlo, tax (Phase 2), rebalancing |
| Claude reader for unknown statement formats | ✗ | Fair-use quota |
| Export, alerts, monthly digest | ✗ | ✓ |

The pitch writes itself because the app already measures it: *"Pro found ₹4,200 of missed rewards
on your cards last year."* Put that number on the paywall.

### B. Credit-card referral commissions — fits the product best

The leakage report already knows "you would earn ₹X more on card Y". Add a "cards you don't hold"
comparison and link out through issuer affiliate programmes or aggregators such as BankKaro or
EarnKaro. They typically pay ₹500–3,000 per approved card. One approval can be worth more than a
year of Pro.

- **Rule:** the ranking must be the same with or without a commission. Label sponsored links, and
  never let commission change the order. Users stay because they trust the leakage report, and a
  ranking bent by commissions would lose that trust.
- This is a referral link only. Taking applications directly starts to look like DSA work and
  brings RBI questions.

### C. Later, optional business sales

A statement-parsing API, or a white-label rewards engine for fintechs. Look at this only once the
parser covers 10 or more banks.

### Not worth it

- Ads: they kill trust in a finance app.
- Selling or "anonymising" user data: a legal problem under the DPDP Act and a reputation risk.
- Investment tips: needs SEBI RIA registration (the roadmap already excludes recommending securities).

## 3. What to build, in phases

### M0: Make it safe to host (about 3–4 weeks). Nothing can be sold before this.

1. **Auth:** email + OTP or Google sign-in using an established library (fastapi-users, or a
   provider such as Clerk or Supabase Auth). Store sessions in httpOnly cookies.
2. **Per-user data separation everywhere:** one `get_current_user` dependency, and every query in
   `cards.py`, `portfolio.py`, `ledger.py` and the rest filters by `user_id`. Add a test that
   creates two users and checks that neither can read the other's data on any of the ~80
   endpoints. This is the biggest single piece of work.
3. **Move to Postgres** behind the existing DB layer (already Phase 4 in the roadmap). Run the
   price scheduler as a separate worker or cron job. Prices are shared across users, so fetch
   them once.
4. **Seed new users empty and generic.** Today's seed is the owner's own categories and data.
5. **Security:**
   - Restrict CORS to the app's own domain, add rate limiting and CSRF protection.
   - Encrypt the database and backups.
   - Keep the current rule: statement PDFs and their passwords are never stored. Say so
     publicly, because it is a selling point.
6. **Account controls:** export everything, plus delete-my-account (a real delete, not a hidden flag).

### M1: Turn the owner's cards into a general card catalog (about 3 weeks)

1. Move the hardcoded rates into a `card_products` catalog with effective-dated
   `card_reward_rules`. `CREDIT_CARDS.md` already designs this. Seed the 30–40 most popular
   Indian cards (HDFC Infinia, Regalia and Millennia, SBI Cashback, Axis Ace, Atlas and Magnus,
   Amazon Pay ICICI, Flipkart Axis, IDFC, and so on).
2. Onboarding: "Which cards do you hold?" Users pick from the catalog, then upload a statement and
   see their leakage within 2 minutes.
3. Add an admin screen for keeping the catalog current. Issuers change terms every quarter, and
   stale rules would erode trust. This is the ongoing cost of running the product, and also what
   keeps competitors out.
4. Turn the one-off panels (Rubyx, card-number inference) into general rules, or keep them out of
   the multi-user build.

### M2: Billing and plan limits (about 2 weeks)

1. **Razorpay Subscriptions.** It supports UPI AutoPay and cards, and Stripe is hard to get in
   India. GST invoices.
2. Tables: `plans`, `subscriptions`, `entitlements`, and webhook-driven state with a grace period.
3. One `require(feature)` dependency on the backend and a `<Paywall>` component on the frontend.
   Keep feature names in one table, in line with the "one number, one home" rule.
4. **Claude cost control:** a monthly quota per user on the LLM statement reader. Log tokens per
   user. When the same unknown format comes up often, write a proper parser for it, which is free
   to run.

### M3: Launch essentials (about 2 weeks, can overlap with M2)

- **Legal:** privacy policy, terms, refund policy and recorded consent. The DPDP Act 2023 rules
  (notified Nov 2025) are phasing in, and a named grievance contact is required. A small fintech
  lawyer review costs ₹15–30k and is worth it.
- A landing page with a free "statement health check": upload one statement, see the leakage,
  sign up to keep it.
- Product analytics (PostHog), error tracking (Sentry), uptime monitoring and automated backups.
- Make it work on phones as a PWA. The Telegram bot plan
  ([telegram-expense-bot-plan.md](telegram-expense-bot-plan.md)) can become a Pro feature once it
  runs on the hosted server rather than a home PC.

### M4: Grow and add referral income (ongoing)

- A "cards you don't hold" comparison with affiliate links (model B), and a disclosure page.
- Retention emails: the monthly digest, "pay card X by Friday", "points expiring". Reminders that
  save money are the strongest reason to renew.
- More bank parsers (Axis, Kotak, IDFC, AU, IndusInd). Every new parser makes the product more
  useful to more people.
- Annual "card renewal verdict" emails (keep, downgrade or close), which push people towards the
  annual plan.

## 4. Updates to the roadmap's "Deliberately not doing"

| Item | Still right? |
|---|---|
| Account Aggregator | Still skip. It needs a licensed partner, and statement upload is the privacy pitch |
| Buy/sell recommendations | Still skip (SEBI) |
| Native mobile app | Skip; a PWA is enough |
| **New:** take card applications directly | Skip; only link out to issuers or aggregators |
| **New:** store statement PDFs | Never |

## 5. Risks

1. **Trust:** users won't upload financial statements to an unknown app. Answer with "statements
   are never stored", a clear security page, and possibly a self-hosted Pro version.
2. **Catalog maintenance:** one stale reward rule produces a wrong leakage figure and a refund
   request. Budget a few hours a week for it.
3. **Low willingness to pay in India:** expect roughly 1–3% of free users to convert. Referral
   commissions may earn more than subscriptions, which is why model B is planned early.
4. **Scope creep:** the roadmap's Phases 1–3 are a lot of work. Ship M0–M3 with Cards as the paid
   product, then go back to the roadmap.

## 6. Suggested order

**M0 → M1 → M2 + M3 → soft launch to about 50 card enthusiasts (free Pro for feedback) → M4.**
About 10–12 weeks of focused work to the first paying user.

## Open decisions

1. **Hosted SaaS or a paid self-hosted version?** Self-hosted skips most of M0 and the privacy
   risk, but limits growth.
2. **Should referral commissions be part of the model?** It changes whether M1 needs data on cards
   users don't hold.
