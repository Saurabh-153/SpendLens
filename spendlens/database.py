import sqlite3
import os
import shutil
from datetime import date, datetime

# SPENDLENS_DB points the whole app at another file. Used by the test suite so it never
# touches your real data; leave it unset for normal use.
DB_PATH = os.environ.get("SPENDLENS_DB") or os.path.join(os.path.dirname(__file__), "spendlens_v2.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def current_month():
    return date.today().strftime("%Y-%m")


def prev_month(m):
    y, mo = map(int, m.split("-"))
    mo -= 1
    if mo == 0:
        y, mo = y - 1, 12
    return f"{y}-{mo:02d}"


def next_month(m):
    y, mo = map(int, m.split("-"))
    mo += 1
    if mo == 13:
        y, mo = y + 1, 1
    return f"{y}-{mo:02d}"


def categories_for_month(db, month):
    """Categories to show in a month, with the target valid for that month.

    A category is shown if the month is inside [start_month, end_month] OR it has
    expenses in that month, so recorded data is never hidden. `archived` marks a
    category shown only because of its data.
    """
    rows = db.execute("""
        SELECT c.*,
          COALESCE((SELECT t.target_pct FROM category_targets t
                    WHERE t.category_id=c.id AND t.from_month<=? ORDER BY t.from_month DESC LIMIT 1), 0) AS month_target,
          EXISTS(SELECT 1 FROM expenses e WHERE e.category_id=c.id AND e.date LIKE ?) AS month_has_data
        FROM categories c ORDER BY c.sort_order, c.id""", (month, f"{month}-%")).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        in_range = d["start_month"] <= month and (d["end_month"] is None or month <= d["end_month"])
        if in_range or d.pop("month_has_data"):
            d["target_pct"] = d.pop("month_target")
            d["archived"] = not in_range
            out.append(d)
    return out


def budget_for_month(db, month):
    """Salary and savings (both in rupees) valid for a month; budget cap = salary - savings."""
    row = db.execute("""SELECT income, savings_amount FROM budget_history
                        WHERE from_month<=? ORDER BY from_month DESC LIMIT 1""", (month,)).fetchone()
    if row is None:
        row = db.execute("SELECT income, savings_amount FROM budget_history ORDER BY from_month LIMIT 1").fetchone()
    return {"income": row["income"], "savings_amount": row["savings_amount"],
            "budget_cap": row["income"] - row["savings_amount"]}


def category_allowed_in_month(db, category_id, month):
    return any(c["id"] == category_id and not c["archived"] for c in categories_for_month(db, month))


def _migrate_holdings(conn):
    """Group, monthly SIP and maturity date on holdings (idempotent)."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(holdings)")}
    for name, ddl in (("grp", "TEXT DEFAULT ''"), ("sip_amount", "REAL DEFAULT 0"), ("maturity", "TEXT DEFAULT ''"), ("sip_day", "INTEGER DEFAULT 0"), ("sip_applied", "TEXT DEFAULT ''"), ("rate", "REAL DEFAULT 0"), ("start_date", "TEXT DEFAULT ''"), ("compounding", "TEXT DEFAULT 'Q'"), ("rd", "INTEGER DEFAULT 0"), ("credits", "TEXT DEFAULT ''"), ("manual", "INTEGER DEFAULT 0"), ("scheme_code", "TEXT DEFAULT ''"), ("units", "REAL DEFAULT 0"), ("nav", "REAL DEFAULT 0"), ("auto_price", "INTEGER DEFAULT 0"), ("price_date", "TEXT DEFAULT ''"), ("price_note", "TEXT DEFAULT ''"), ("tags", "TEXT DEFAULT ''"), ("exposure", "TEXT DEFAULT ''")):
        if name not in cols:
            conn.execute(f"ALTER TABLE holdings ADD COLUMN {name} {ddl}")
    conn.execute("CREATE TABLE IF NOT EXISTS sip_log (id INTEGER PRIMARY KEY AUTOINCREMENT, holding_id INTEGER, holding_name TEXT, month TEXT, sip_date TEXT, amount REAL, applied_at TEXT DEFAULT (datetime('now')))")
    # Admin-managed groups; an empty holdings.grp means the built-in "Others" bucket
    conn.execute("CREATE TABLE IF NOT EXISTS holding_groups (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, sort_order INTEGER DEFAULT 0)")
    if conn.execute("SELECT COUNT(*) FROM holding_groups").fetchone()[0] == 0:
        rows = conn.execute("SELECT grp FROM holdings WHERE grp<>'' GROUP BY grp ORDER BY SUM(qty*cmp) DESC").fetchall()
        conn.executemany("INSERT INTO holding_groups (name, sort_order) VALUES (?,?)", [(r[0], i) for i, r in enumerate(rows)])
    # Holdings-table columns a group leaves empty (comma-separated column keys); Admin sets it per group
    if "hidden_columns" not in [r[1] for r in conn.execute("PRAGMA table_info(holding_groups)")]:
        conn.execute("ALTER TABLE holding_groups ADD COLUMN hidden_columns TEXT DEFAULT ''")
        # these groups used to be matched by name in the UI
        conn.execute("UPDATE holding_groups SET hidden_columns='units,buy' WHERE name LIKE '%emergency%' OR name LIKE '%liquid%' OR name LIKE '%fixed%'")
    conn.execute("CREATE TABLE IF NOT EXISTS app_prefs (key TEXT PRIMARY KEY, value TEXT NOT NULL DEFAULT '')")


def _migrate_admin(conn):
    """Add category lifecycle + effective-dated targets/budget (idempotent)."""
    c = conn.cursor()
    cols = {r[1] for r in c.execute("PRAGMA table_info(categories)")}
    if "start_month" not in cols:
        bak = sqlite3.connect(DB_PATH.replace(".db", ".pre-admin.bak"))
        conn.backup(bak)
        bak.close()
        c.execute("ALTER TABLE categories ADD COLUMN start_month TEXT NOT NULL DEFAULT '0000-00'")
        c.execute("ALTER TABLE categories ADD COLUMN end_month TEXT")
        for cid, in c.execute("SELECT id FROM categories WHERE visible=0").fetchall():
            last = c.execute("SELECT MAX(substr(date,1,7)) FROM expenses WHERE category_id=?", (cid,)).fetchone()[0]
            c.execute("UPDATE categories SET end_month=? WHERE id=?", (last or "2024-01", cid))
    c.executescript("""
        CREATE TABLE IF NOT EXISTS category_targets (
            category_id INTEGER NOT NULL REFERENCES categories(id),
            from_month TEXT NOT NULL,
            target_pct INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (category_id, from_month)
        );
        CREATE TABLE IF NOT EXISTS budget_history (
            from_month TEXT PRIMARY KEY,
            income REAL NOT NULL,
            savings_amount REAL NOT NULL
        );
    """)
    # savings used to be a % of income; it is now an amount (budget cap = salary - savings)
    bcols = {r[1] for r in c.execute("PRAGMA table_info(budget_history)")}
    if "savings_target" in bcols:
        c.execute("ALTER TABLE budget_history ADD COLUMN savings_amount REAL") if "savings_amount" not in bcols else None
        c.execute("UPDATE budget_history SET savings_amount = income * savings_target / 100.0 WHERE savings_amount IS NULL")
        c.execute("ALTER TABLE budget_history DROP COLUMN savings_target")
    c.execute("""INSERT INTO category_targets (category_id, from_month, target_pct)
                 SELECT id, '0000-00', target_pct FROM categories
                 WHERE id NOT IN (SELECT category_id FROM category_targets)""")
    if c.execute("SELECT COUNT(*) FROM budget_history").fetchone()[0] == 0:
        c.execute("""INSERT INTO budget_history (from_month, income, savings_amount)
                     SELECT '0000-00', income, income * savings_target / 100.0 FROM settings WHERE id=1""")


# ---------------------------------------------------------------------------
# Versioned migrations
#
# Everything above this point is an older, idempotent "re-check the columns every
# start-up" style migration. Those stay as the baseline (version 1); all new schema
# work is a numbered step here, applied once and recorded in `schema_migrations`.
#
# Rules for a step: it takes an open connection, is written to be safe if interrupted,
# and never silently drops data the user could still want. A timestamped copy of the
# database is taken before the first pending step of a run.
# ---------------------------------------------------------------------------

def _table_exists(conn, name):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def _columns(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def _add_column(conn, table, name, ddl):
    """Add a column unless it is already there. Skips tables that don't exist yet."""
    if _table_exists(conn, table) and name not in _columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


def _m001_baseline(conn):
    """No-op. Marks the pre-migration schema (init_db + the _migrate_* helpers) as version 1."""


def _m002_drop_unused_tables(conn):
    """Remove tables nothing has ever read: left over from abandoned features.

    `price_alerts` returns as a real feature later, with a schema of its own.
    """
    for t in ("users", "rebalance_targets", "price_alerts"):
        conn.execute(f"DROP TABLE IF EXISTS {t}")


def _m003_user_id_columns(conn):
    """Add `user_id` ahead of multi-user support, so adding login later is not a rewrite.

    Only tables with a surrogate `id` are done here. The key/value and
    effective-dated-by-month tables (`portfolio_plan`, `budget_history`,
    `category_targets`, `price_history`) need their primary keys widened instead,
    which belongs with the login work itself.
    """
    for t in ("categories", "subcategories", "subcategory_rules", "holdings",
              "holding_groups", "transactions", "portfolio_goals", "sip_log"):
        _add_column(conn, t, "user_id", "INTEGER DEFAULT 1")


def _m004_credit_cards(conn):
    """Credit cards, their statements, transactions and classification rules.

    Card spend is deliberately kept out of `expenses`: the imported statements overlap
    months whose expenses are already entered by hand, so merging them would double
    count. Linking the two is a later, explicit step with its own de-duplication.
    """
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER DEFAULT 1,
            name TEXT NOT NULL,
            issuer TEXT DEFAULT '',
            network TEXT DEFAULT '',
            last4 TEXT DEFAULT '',
            credit_limit REAL DEFAULT 0,
            cash_limit REAL DEFAULT 0,
            statement_day INTEGER DEFAULT 0,
            due_day INTEGER DEFAULT 0,
            annual_fee REAL DEFAULT 0,
            fee_waiver_spend REAL DEFAULT 0,   -- annual spend that waives the fee
            rate_online REAL DEFAULT 0,        -- % cashback on an online spend
            rate_offline REAL DEFAULT 0,       -- % cashback on a card-present spend
            cashback_cap REAL DEFAULT 0,       -- most that can be earned in one cycle
            status TEXT DEFAULT 'active',      -- active / downgrade / closed
            notes TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS card_statements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            card_id INTEGER NOT NULL REFERENCES cards(id),
            period_from TEXT, period_to TEXT NOT NULL,
            stmt_date TEXT, due_date TEXT,
            total_due REAL DEFAULT 0, min_due REAL DEFAULT 0,
            purchases REAL DEFAULT 0, credits REAL DEFAULT 0, fees REAL DEFAULT 0,
            available_credit REAL DEFAULT 0,
            cashback_reported REAL,            -- what the statement actually paid
            cashback_calc REAL,                -- what the rules say it should have paid
            file TEXT DEFAULT '',
            imported_at TEXT DEFAULT (datetime('now')),
            UNIQUE (card_id, period_to)
        );

        CREATE TABLE IF NOT EXISTS card_txns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            card_id INTEGER NOT NULL REFERENCES cards(id),
            statement_id INTEGER REFERENCES card_statements(id),
            row_hash TEXT NOT NULL UNIQUE,     -- de-duplicates overlapping statements
            tx_date TEXT NOT NULL,
            detail TEXT DEFAULT '',            -- the raw statement line
            merchant TEXT DEFAULT '', city TEXT DEFAULT '',
            amount REAL NOT NULL,
            dc TEXT DEFAULT 'D',               -- D = spend, C = payment or credit
            emi INTEGER DEFAULT 0,             -- converted to EMI on the statement
            is_spend INTEGER DEFAULT 1,        -- 0 for payments, fees and the cashback credit
            cls TEXT DEFAULT '',               -- online / offline / excluded
            cashback REAL DEFAULT 0,
            capped INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_card_txns_card_date ON card_txns(card_id, tx_date);

        CREATE TABLE IF NOT EXISTS card_merchant_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            card_id INTEGER,                   -- NULL applies to every card
            pattern TEXT NOT NULL,
            match_type TEXT DEFAULT 'contains',-- contains / prefix / regex
            cls TEXT NOT NULL,                 -- online / offline / excluded
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)
    # The card these statements belong to, with the terms printed on them.
    if conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0] == 0:
        conn.execute("""INSERT INTO cards
            (name, issuer, network, last4, credit_limit, cash_limit, statement_day, due_day,
             annual_fee, fee_waiver_spend, rate_online, rate_offline, cashback_cap, notes)
            VALUES ('CASHBACK SBI Card', 'SBI Card', '', '82', 400000, 120000, 11, 1,
                    999, 200000, 5, 1, 5000, ?)""",
                     ("Fee waived on 2L spend in the preceding year. The per-cycle cap is a "
                      "setting: the statements never reached it, so it could not be measured.",))


def _m005_card_profiles_and_cycles(conn):
    """Make the card tables work for more than one issuer, and add the billing cycle.

    - `cards.profile` picks the reward classes and rules (SBI Cashback, Amazon Pay ICICI...),
      `rates` holds the percent per class as JSON, replacing the SBI-only online/offline pair.
    - `statement_day` + `grace_days` define the billing cycle, which is what the
      "when to pay" calculation needs; `cycle_verified` records whether they were read from
      a statement or are still an assumption. `pay_buffer_days` is the safety margin before
      the due date; `float_rate` is what the money earns while it is not yet paid.
    - `card_txns.kind` separates spend from payments, EMI parts, fees and refunds, so spend
      and what the bank bills are no longer the same thing.
    """
    for col, ddl in (("profile", "TEXT DEFAULT 'generic'"), ("rates", "TEXT DEFAULT '{}'"),
                     ("grace_days", "INTEGER DEFAULT 20"), ("pay_buffer_days", "INTEGER DEFAULT 1"),
                     ("float_rate", "REAL DEFAULT 7"), ("cycle_verified", "INTEGER DEFAULT 0")):
        _add_column(conn, "cards", col, ddl)
    _add_column(conn, "card_statements", "kind", "TEXT DEFAULT 'cycle'")  # cycle / year
    _add_column(conn, "card_txns", "kind", "TEXT DEFAULT ''")
    _add_column(conn, "card_txns", "ref", "TEXT DEFAULT ''")

    # The SBI card seeded by migration 4: its terms, now as data rather than columns.
    conn.execute("""UPDATE cards SET profile='sbi_cashback', grace_days=20, cycle_verified=1,
                    rates='{"online": 5, "offline": 1, "excluded": 0}'
                    WHERE issuer='SBI Card' AND profile='generic'""")

    # Classify the rows already stored.
    conn.execute("""UPDATE card_txns SET kind = CASE
                      WHEN is_spend=1 THEN 'spend'
                      WHEN dc='C' AND UPPER(detail) LIKE '%PAYMENT RECEIVED%' THEN 'payment'
                      WHEN dc='C' AND UPPER(detail) LIKE '%CASHBACK%' THEN 'cashback'
                      WHEN dc='C' THEN 'refund'
                      ELSE 'fee' END
                    WHERE kind=''""")


def _m006_card_accounts(conn):
    """Billing accounts: cards that share one bill.

    A card number and a billing account are different things. Two ICICI cards can be settled
    by one bill and one set of payments (payments were posted under one card while settling
    both), so the due date, the payments and therefore the "when to pay" answer belong to the
    *account*, while spend and rewards belong to the card. Every existing card starts in an
    account of its own; importing a statement that lists several cards joins their accounts.
    """
    conn.execute("""CREATE TABLE IF NOT EXISTS card_accounts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        issuer TEXT DEFAULT '',
                        label TEXT DEFAULT '')""")
    _add_column(conn, "cards", "account_id", "INTEGER")
    for cid, issuer, name in conn.execute("SELECT id, issuer, name FROM cards WHERE account_id IS NULL").fetchall():
        cur = conn.execute("INSERT INTO card_accounts (issuer, label) VALUES (?,?)", (issuer, name))
        conn.execute("UPDATE cards SET account_id=? WHERE id=?", (cur.lastrowid, cid))


def _m007_card_txn_currency(conn):
    """Remember which card transactions were in a foreign currency (a card can pay more on them)."""
    _add_column(conn, "card_txns", "ccy", "TEXT DEFAULT ''")


def _m008_reward_points(conn):
    """Some statements print reward points: per transaction, and as a total with the closing balance.
    Reading them beats estimating them from a rate."""
    _add_column(conn, "card_txns", "points", "INTEGER DEFAULT 0")
    _add_column(conn, "card_statements", "points_earned", "INTEGER")
    _add_column(conn, "card_statements", "points_balance", "INTEGER")


def _m009_txn_category(conn):
    """The issuer's own spend category on a transaction (Amex prints one on every charge)."""
    _add_column(conn, "card_txns", "category", "TEXT DEFAULT ''")


def _m010_card_perks(conn):
    """Each card's benefits, written down and editable (see card_perks.py)."""
    conn.execute("""CREATE TABLE IF NOT EXISTS card_perks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        card_id INTEGER NOT NULL REFERENCES cards(id),
        kind TEXT NOT NULL DEFAULT 'other',
        title TEXT NOT NULL,
        detail TEXT DEFAULT '',
        value_yr REAL DEFAULT 0,          -- what you reckon it is worth a year, in rupees (optional)
        source TEXT DEFAULT '',
        checked INTEGER DEFAULT 0,        -- you have confirmed it against the card's own terms
        sort INTEGER DEFAULT 0,
        updated TEXT DEFAULT ''
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_card_perks_card ON card_perks(card_id)")
    _add_column(conn, "cards", "perks_seeded", "INTEGER DEFAULT 0")


def _m011_card_color(conn):
    """A colour a card is shown in, chosen by you; empty means the app picks one that no other card uses."""
    _add_column(conn, "cards", "color", "TEXT DEFAULT ''")


def _m012_card_sort_order(conn):
    """Where you dragged a card to on the Cards page; 0 for a card you have not placed, which keeps the default order."""
    _add_column(conn, "cards", "sort_order", "INTEGER DEFAULT 0")


MIGRATIONS = [
    (1, "baseline", _m001_baseline),
    (2, "drop-unused-tables", _m002_drop_unused_tables),
    (3, "user-id-columns", _m003_user_id_columns),
    (4, "credit-cards", _m004_credit_cards),
    (5, "card-profiles-and-cycles", _m005_card_profiles_and_cycles),
    (6, "card-accounts", _m006_card_accounts),
    (7, "card-txn-currency", _m007_card_txn_currency),
    (8, "reward-points", _m008_reward_points),
    (9, "txn-category", _m009_txn_category),
    (10, "card-perks", _m010_card_perks),
    (11, "card-color", _m011_card_color),
    (12, "card-sort-order", _m012_card_sort_order),
]


def _backup_db(tag):
    """Copy the database file next to itself. Returns the path, or None if there is nothing to copy."""
    if not os.path.exists(DB_PATH) or os.path.getsize(DB_PATH) == 0:
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = DB_PATH.replace(".db", f".{tag}-{stamp}.bak")
    shutil.copy2(DB_PATH, path)
    return path


def pending_migrations(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS schema_migrations (
                        version INTEGER PRIMARY KEY,
                        name TEXT NOT NULL,
                        applied_at TEXT NOT NULL DEFAULT (datetime('now')))""")
    done = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
    return [m for m in MIGRATIONS if m[0] not in done]


def run_migrations(conn):
    """Apply every migration not yet recorded. Returns the list of names applied."""
    pending = pending_migrations(conn)
    if not pending:
        return []
    # Fresh database: init_db just built it, so there is nothing worth backing up.
    fresh = conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0] == 0
    if not fresh:
        _backup_db(f"pre-v{pending[-1][0]}")
    applied = []
    for version, name, fn in pending:
        fn(conn)
        conn.execute("INSERT INTO schema_migrations (version, name) VALUES (?,?)", (version, name))
        conn.commit()
        applied.append(name)
    return applied


def schema_version(conn):
    if not _table_exists(conn, "schema_migrations"):
        return 0
    return conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_migrations").fetchone()[0]


def init_db():
    conn = get_db()
    c = conn.cursor()

    c.executescript("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            income INTEGER DEFAULT 245000,
            savings_target INTEGER DEFAULT 44,
            currency TEXT DEFAULT 'INR',
            fiscal_year_start TEXT DEFAULT 'April',
            date_format TEXT DEFAULT 'DD/MM/YYYY',
            price_source TEXT DEFAULT 'Manual Entry',
            auto_refresh TEXT DEFAULT 'Disabled (manual)'
        );

        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            icon TEXT DEFAULT '📦',
            color TEXT DEFAULT '#64748b',
            target_pct INTEGER DEFAULT 0,
            hint TEXT DEFAULT '',
            visible INTEGER DEFAULT 1,
            sort_order INTEGER DEFAULT 99
        );

        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER NOT NULL REFERENCES categories(id),
            user_id INTEGER DEFAULT 1,
            date TEXT NOT NULL,
            amount REAL NOT NULL,
            note TEXT DEFAULT '',
            cashback REAL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS holdings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            ticker TEXT DEFAULT '',
            asset_type TEXT NOT NULL DEFAULT 'EQ',
            sector TEXT DEFAULT '',
            qty REAL DEFAULT 0,
            buy_price REAL DEFAULT 0,
            cmp REAL DEFAULT 0,
            week52_low REAL DEFAULT 0,
            week52_high REAL DEFAULT 0,
            notes TEXT DEFAULT '',
            visible INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (date('now'))
        );

    """)

    # Seed settings
    c.execute("INSERT OR IGNORE INTO settings (id) VALUES (1)")

    # Starter data goes into a brand-new database only. It used to be re-inserted on every start, so a category you
    # deleted (the app lets you delete one that never had an expense) came straight back the next time the server ran.
    fresh = c.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 0

    # Seed categories
    cats = [
        (1,  "Rent / EMI",          "🏠", "#6c63ff", 15, "Home rent or loan EMI",                True,  1),
        (2,  "Utilities",           "⚡", "#38bdf8", 4,  "Electricity, internet, OTT, insurance", True,  2),
        (3,  "Savings / Investment","📈", "#22c55e", 0,  "SIP, FD, PPF — tracked separately",    True,  3),
        (4,  "Assistance",          "🧹", "#a78bfa", 1,  "Maid, ironing, dry clean",              True,  4),
        (5,  "Transport",           "🚗", "#fb923c", 2,  "Petrol, cab, train tickets",            True,  5),
        (6,  "Travel / Vacation",   "✈️", "#34d399", 2,  "Trips, hotels (not daily transport)",   False, 6),
        (7,  "Milk",                "🥛", "#e2e8f0", 3,  "Daily delivery, curd",                  True,  7),
        (8,  "Groceries",           "🛒", "#4ade80", 3,  "Big Basket, Patanjali, local",          True,  8),
        (9,  "Fruits + Veg",        "🥦", "#86efac", 3,  "Fresh produce",                         True,  9),
        (10, "Egg / Chicken",       "🥚", "#fde68a", 3,  "Licious, local market",                 True,  10),
        (11, "Eat Out / Order",     "🍽️","#f472b6", 2,  "Swiggy, Zomato, café",                  True,  11),
        (12, "Children / Baby",     "👶", "#93c5fd", 3,  "Diapers, baby milk, formula",           True,  12),
        (13, "School Fees",         "🏫", "#fbbf24", 5,  "Tuition, bus, activity",                True,  13),
        (14, "Shopping / Clothing", "🛍️","#e879f9", 2,  "Apparel, footwear",                     True,  14),
        (15, "Personal Care",       "💆", "#f9a8d4", 1,  "Salon, haircut, skincare",              False, 15),
        (16, "Electronics",         "💻", "#60a5fa", 1,  "Gadgets, appliances (one-off)",         False, 16),
        (17, "Gifts / Occasions",   "🎁", "#fb7185", 1,  "Birthdays, festivals, weddings",        False, 17),
        (18, "Doctor & Medicine",   "💊", "#ef4444", 4,  "OPD, medicines, tests, health",         True,  18),
        (19, "Miscellaneous",       "📦", "#64748b", 1,  "Catch-all — keep this small",           True,  19),
    ]
    for cat in (cats if fresh else []):
        c.execute("""INSERT OR IGNORE INTO categories
            (id, name, icon, color, target_pct, hint, visible, sort_order) VALUES (?,?,?,?,?,?,?,?)""", cat)

    # Seed Feb 2025 expenses
    expense_data = {
        1:  {1:32000,11:4262},
        2:  {2:5000,5:493,10:1543,13:199,24:1418,28:1819},
        4:  {2:2500,11:855,13:899,17:300,20:160},
        5:  {11:1990,12:1284,17:910,20:200},
        7:  {1:93,2:166,3:180,4:93,5:93,6:93,7:93,8:93,9:690,10:321,11:94,12:94,13:94,14:161,15:94,16:406,17:94,18:47,19:93,20:93,21:93,22:93,23:202,24:93,25:93,26:93,27:93,28:93},
        8:  {6:795,7:221,8:70,9:221,13:1528,18:535,27:3627},
        9:  {2:744,5:510,6:230,8:480,9:114,13:401,17:282,18:143,20:660,23:421,26:55,27:150,28:196},
        10: {12:230,17:404,18:425,19:290,24:230,28:353},
        11: {1:525,2:35,3:80,4:35,5:35,7:621,9:35,13:360,14:40,15:275,16:35,17:50,18:35,26:35},
        14: {1:1338,11:1071,24:1185},
        18: {3:442,10:234,13:456,14:2047,18:237,19:1200,20:1525,21:1500,22:368,23:973,26:4700,27:1400},
        19: {5:2995,25:40},
    }
    subs = {
        1: {11:"Maintain"},
        2: {2:"Health Ins",5:"Prime",10:"Electricity",13:"Netflix",24:"Phone EMI",28:"LIC"},
        4: {2:"Maid",11:"LPG",13:"Urban Co",17:"Haircut",20:"Hair Cut"},
        5: {11:"Train",12:"Hotel",17:"Cab+Air",20:"Cab"},
        8: {6:"Grocery",7:"Grocery",8:"Grocery",9:"Patanjali",13:"Grocery",18:"Grocery",27:"Grocery"},
        9: {9:"Fruits",13:"Fruits",17:"Fruits+Veg",18:"Fruits+Veg",20:"Fruits+Veg",23:"Fruits",26:"IceCream",27:"Coco Water",28:"Veg"},
        10:{12:"Egg",17:"Licious",18:"Licious",19:"Eat Out",24:"Egg",28:"Chicken"},
        11:{2:"Office",3:"Office",4:"Office",5:"Office",7:"Biryani",9:"Office",13:"Dosa",14:"Coffee",15:"Dosa",16:"Eat Out",17:"Office",18:"Office",26:"Office"},
        14:{1:"First Cry",11:"Makeup",24:"Watch"},
        18:{3:"Babu Milk",10:"Wipes",13:"Diaper",14:"Mummy",18:"Babu Milk",19:"Skin Doc",20:"Medicine",21:"Medicine",22:"Medicine",23:"Babu Dr",26:"Blood Test",27:"Milk"},
        19:{5:"Vacuum",25:"Color"},
    }

    existing = c.execute("SELECT COUNT(*) FROM expenses WHERE date LIKE '2025-02-%'").fetchone()[0]
    if fresh and existing == 0:
        for cat_id, days in expense_data.items():
            for day, amt in days.items():
                date = f"2025-02-{day:02d}"
                note = subs.get(cat_id, {}).get(day, "")
                c.execute("INSERT INTO expenses (category_id, user_id, date, amount, note, cashback) VALUES (?,1,?,?,?,?)",
                          (cat_id, date, amt, note, 0))

    # Cashback entries
    if fresh and c.execute("SELECT COUNT(*) FROM expenses WHERE cashback > 0").fetchone()[0] == 0:
        c.execute("UPDATE expenses SET cashback=1575 WHERE date='2025-02-11' AND category_id=1 AND amount=4262")

    conn.commit()
    _migrate_admin(conn)
    _migrate_holdings(conn)
    conn.commit()
    from subcategories import migrate as migrate_subcategories
    migrate_subcategories(conn, DB_PATH)
    conn.commit()
    run_migrations(conn)  # numbered steps; everything above is version 1
    conn.close()
