"""baseline: every table that predates Alembic, plus a new database's starter data

On a database that already has these tables (the live SQLite file, which was stamped at this revision, or an old
pre-Alembic file that database.init_db() has just brought up to date) this creates only what is missing and seeds
nothing. On an EMPTY database (a new SQLite file, or PostgreSQL) it builds the whole pre-Alembic schema - in the
shape the next three revisions produce, which then see their work already done - and the same starter rows
init_db() used to insert: settings, categories and their targets, the budget, a sample month of expenses, the
sub-category defaults and rules, and the first credit card.

Tables 0a3ec7a2c0e3 creates (holding_snapshots, portfolio_snapshots, portfolio_plan) are left to it.

Revision ID: 218d401380ff
Revises:
Create Date: 2026-10-08 00:39:12.256135

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from db.ddl import int_or_float, now_text, sync_sequences, table_names, today_text


# revision identifiers, used by Alembic.
revision: str = '218d401380ff'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _d(v):
    """A literal server default."""
    return sa.text(repr(v)) if isinstance(v, str) else sa.text(str(v))


def _id():
    return sa.Column("id", sa.Integer(), primary_key=True)


def _tables(bind):
    m = sa.MetaData()
    T, I, F = sa.Text, sa.Integer, sa.Float
    ai = {"sqlite_autoincrement": True}
    now = now_text(bind)

    sa.Table("app_prefs", m,
             sa.Column("key", T(), primary_key=True),
             sa.Column("value", T(), nullable=False, server_default=_d("")))
    sa.Table("budget_history", m,
             sa.Column("from_month", T()),
             sa.Column("income", F(), nullable=False),
             sa.Column("savings_amount", F(), nullable=False),
             sa.Column("id", I(), nullable=False),
             sa.Column("user_id", I(), nullable=False, server_default=_d(1)),
             sa.PrimaryKeyConstraint("id", name="pk_budget_history"),
             sa.UniqueConstraint("user_id", "from_month", name="uq_budget_history_user_month"))
    sa.Table("card_accounts", m, _id(),
             sa.Column("issuer", T(), server_default=_d("")),
             sa.Column("label", T(), server_default=_d("")),
             sa.Column("user_id", I(), nullable=False, server_default=_d(1)), **ai)
    sa.Table("card_merchant_rules", m, _id(),
             sa.Column("card_id", I()),
             sa.Column("pattern", T(), nullable=False),
             sa.Column("match_type", T(), server_default=_d("contains")),
             sa.Column("cls", T(), nullable=False),
             sa.Column("created_at", T(), server_default=now),
             sa.Column("user_id", I(), nullable=False, server_default=_d(1)), **ai)
    sa.Table("cards", m, _id(),
             sa.Column("user_id", I(), server_default=_d(1)),
             sa.Column("name", T(), nullable=False),
             sa.Column("issuer", T(), server_default=_d("")),
             sa.Column("network", T(), server_default=_d("")),
             sa.Column("last4", T(), server_default=_d("")),
             sa.Column("credit_limit", F(), server_default=_d(0)),
             sa.Column("cash_limit", F(), server_default=_d(0)),
             sa.Column("statement_day", I(), server_default=_d(0)),
             sa.Column("due_day", I(), server_default=_d(0)),
             sa.Column("annual_fee", F(), server_default=_d(0)),
             sa.Column("fee_waiver_spend", F(), server_default=_d(0)),
             sa.Column("rate_online", F(), server_default=_d(0)),
             sa.Column("rate_offline", F(), server_default=_d(0)),
             sa.Column("cashback_cap", F(), server_default=_d(0)),
             sa.Column("status", T(), server_default=_d("active")),
             sa.Column("notes", T(), server_default=_d("")),
             sa.Column("profile", T(), server_default=_d("generic")),
             sa.Column("rates", T(), server_default=_d("{}")),
             sa.Column("grace_days", I(), server_default=_d(20)),
             sa.Column("pay_buffer_days", I(), server_default=_d(1)),
             sa.Column("float_rate", F(), server_default=_d(7)),
             sa.Column("cycle_verified", I(), server_default=_d(0)),
             sa.Column("account_id", I()),
             sa.Column("perks_seeded", I(), server_default=_d(0)),
             sa.Column("color", T(), server_default=_d("")),
             sa.Column("sort_order", I(), server_default=_d(0)), **ai)
    sa.Table("card_perks", m, _id(),
             sa.Column("card_id", I(), sa.ForeignKey("cards.id"), nullable=False),
             sa.Column("kind", T(), nullable=False, server_default=_d("other")),
             sa.Column("title", T(), nullable=False),
             sa.Column("detail", T(), server_default=_d("")),
             sa.Column("value_yr", F(), server_default=_d(0)),
             sa.Column("source", T(), server_default=_d("")),
             sa.Column("checked", I(), server_default=_d(0)),
             sa.Column("sort", I(), server_default=_d(0)),
             sa.Column("updated", T(), server_default=_d("")),
             sa.Index("idx_card_perks_card", "card_id"), **ai)
    sa.Table("card_statements", m, _id(),
             sa.Column("card_id", I(), sa.ForeignKey("cards.id"), nullable=False),
             sa.Column("period_from", T()),
             sa.Column("period_to", T(), nullable=False),
             sa.Column("stmt_date", T()),
             sa.Column("due_date", T()),
             sa.Column("total_due", F(), server_default=_d(0)),
             sa.Column("min_due", F(), server_default=_d(0)),
             sa.Column("purchases", F(), server_default=_d(0)),
             sa.Column("credits", F(), server_default=_d(0)),
             sa.Column("fees", F(), server_default=_d(0)),
             sa.Column("available_credit", F(), server_default=_d(0)),
             sa.Column("cashback_reported", F()),
             sa.Column("cashback_calc", F()),
             sa.Column("file", T(), server_default=_d("")),
             sa.Column("imported_at", T(), server_default=now),
             sa.Column("kind", T(), server_default=_d("cycle")),
             sa.Column("points_earned", I()),
             sa.Column("points_balance", I()),
             sa.UniqueConstraint("card_id", "period_to"), **ai)
    sa.Table("card_txns", m, _id(),
             sa.Column("card_id", I(), sa.ForeignKey("cards.id"), nullable=False),
             sa.Column("statement_id", I(), sa.ForeignKey("card_statements.id")),
             sa.Column("row_hash", T(), nullable=False, unique=True),
             sa.Column("tx_date", T(), nullable=False),
             sa.Column("detail", T(), server_default=_d("")),
             sa.Column("merchant", T(), server_default=_d("")),
             sa.Column("city", T(), server_default=_d("")),
             sa.Column("amount", F(), nullable=False),
             sa.Column("dc", T(), server_default=_d("D")),
             sa.Column("emi", I(), server_default=_d(0)),
             sa.Column("is_spend", I(), server_default=_d(1)),
             sa.Column("cls", T(), server_default=_d("")),
             sa.Column("cashback", F(), server_default=_d(0)),
             sa.Column("capped", I(), server_default=_d(0)),
             sa.Column("kind", T(), server_default=_d("")),
             sa.Column("ref", T(), server_default=_d("")),
             sa.Column("ccy", T(), server_default=_d("")),
             sa.Column("points", I(), server_default=_d(0)),
             sa.Column("category", T(), server_default=_d("")),
             sa.Index("idx_card_txns_card_date", "card_id", "tx_date"), **ai)
    sa.Table("categories", m, _id(),
             sa.Column("name", T(), nullable=False),
             sa.Column("icon", T(), server_default=_d("📦")),
             sa.Column("color", T(), server_default=_d("#64748b")),
             sa.Column("target_pct", int_or_float(), server_default=_d(0)),
             sa.Column("hint", T(), server_default=_d("")),
             sa.Column("visible", I(), server_default=_d(1)),
             sa.Column("sort_order", I(), server_default=_d(99)),
             sa.Column("start_month", T(), nullable=False, server_default=_d("0000-00")),
             sa.Column("end_month", T()),
             sa.Column("user_id", I(), server_default=_d(1)), **ai)
    sa.Table("category_targets", m,
             sa.Column("category_id", I(), sa.ForeignKey("categories.id"), nullable=False, autoincrement=False),
             sa.Column("from_month", T(), nullable=False),
             sa.Column("target_pct", int_or_float(), nullable=False, server_default=_d(0)),
             sa.PrimaryKeyConstraint("category_id", "from_month"))
    sa.Table("subcategories", m, _id(),
             sa.Column("category_id", I(), sa.ForeignKey("categories.id"), nullable=False),
             sa.Column("name", T(), nullable=False),
             sa.Column("sort_order", I(), nullable=False, server_default=_d(99)),
             sa.Column("start_month", T(), nullable=False, server_default=_d("0000-00")),
             sa.Column("end_month", T()),
             sa.Column("user_id", I(), server_default=_d(1)), **ai)
    sa.Table("subcategory_rules", m, _id(),
             sa.Column("category_id", I(), sa.ForeignKey("categories.id"), nullable=False),
             sa.Column("pattern", T(), nullable=False),
             sa.Column("match_type", T(), nullable=False, server_default=_d("contains")),
             sa.Column("subcategory_id", I(), sa.ForeignKey("subcategories.id"), nullable=False),
             sa.Column("user_id", I(), server_default=_d(1)), **ai)
    sa.Table("expenses", m, _id(),
             sa.Column("category_id", I(), sa.ForeignKey("categories.id"), nullable=False),
             sa.Column("user_id", I(), server_default=_d(1)),
             sa.Column("date", T(), nullable=False),
             sa.Column("amount", F(), nullable=False),
             sa.Column("note", T(), server_default=_d("")),
             sa.Column("cashback", F(), server_default=_d(0)),
             sa.Column("created_at", T(), server_default=now),
             sa.Column("subcategory_id", I(), sa.ForeignKey("subcategories.id")), **ai)
    sa.Table("holding_groups", m, _id(),
             sa.Column("name", T(), nullable=False, unique=True),
             sa.Column("sort_order", I(), server_default=_d(0)),
             sa.Column("hidden_columns", T(), server_default=_d("")),
             sa.Column("user_id", I(), server_default=_d(1)), **ai)
    sa.Table("holdings", m, _id(),
             sa.Column("name", T(), nullable=False),
             sa.Column("ticker", T(), server_default=_d("")),
             sa.Column("asset_type", T(), nullable=False, server_default=_d("EQ")),
             sa.Column("sector", T(), server_default=_d("")),
             sa.Column("qty", F(), server_default=_d(0)),
             sa.Column("buy_price", F(), server_default=_d(0)),
             sa.Column("cmp", F(), server_default=_d(0)),
             sa.Column("week52_low", F(), server_default=_d(0)),
             sa.Column("week52_high", F(), server_default=_d(0)),
             sa.Column("notes", T(), server_default=_d("")),
             sa.Column("visible", I(), server_default=_d(1)),
             sa.Column("created_at", T(), server_default=today_text(bind)),
             sa.Column("grp", T(), server_default=_d("")),
             sa.Column("sip_amount", F(), server_default=_d(0)),
             sa.Column("maturity", T(), server_default=_d("")),
             sa.Column("sip_day", I(), server_default=_d(0)),
             sa.Column("sip_applied", T(), server_default=_d("")),
             sa.Column("rate", F(), server_default=_d(0)),
             sa.Column("start_date", T(), server_default=_d("")),
             sa.Column("compounding", T(), server_default=_d("Q")),
             sa.Column("rd", I(), server_default=_d(0)),
             sa.Column("credits", T(), server_default=_d("")),
             sa.Column("manual", I(), server_default=_d(0)),
             sa.Column("scheme_code", T(), server_default=_d("")),
             sa.Column("units", F(), server_default=_d(0)),
             sa.Column("nav", F(), server_default=_d(0)),
             sa.Column("auto_price", I(), server_default=_d(0)),
             sa.Column("price_date", T(), server_default=_d("")),
             sa.Column("price_note", T(), server_default=_d("")),
             sa.Column("tags", T(), server_default=_d("")),
             sa.Column("exposure", T(), server_default=_d("")),
             sa.Column("user_id", I(), server_default=_d(1)), **ai)
    sa.Table("portfolio_goals", m, _id(),
             sa.Column("user_id", I(), nullable=False),
             sa.Column("name", sa.String(), nullable=False),
             sa.Column("target_amount", F(), nullable=False),
             sa.Column("target_year", I(), nullable=False))
    sa.Table("price_history", m,
             sa.Column("holding_id", I(), primary_key=True, autoincrement=False),
             sa.Column("price_date", sa.String(), primary_key=True),
             sa.Column("price", F()))
    sa.Table("price_runs", m, _id(),
             sa.Column("ran_at", sa.String()),
             sa.Column("ok", I()),
             sa.Column("updated", I()),
             sa.Column("failed", I()),
             sa.Column("detail", sa.String()))
    sa.Table("schema_migrations", m,
             sa.Column("version", I(), primary_key=True, autoincrement=False),
             sa.Column("name", T(), nullable=False),
             sa.Column("applied_at", T(), nullable=False, server_default=now))
    sa.Table("settings", m,
             sa.Column("income", I(), server_default=_d(245000)),
             sa.Column("savings_target", I(), server_default=_d(44)),
             sa.Column("currency", T(), server_default=_d("INR")),
             sa.Column("fiscal_year_start", T(), server_default=_d("April")),
             sa.Column("date_format", T(), server_default=_d("DD/MM/YYYY")),
             sa.Column("price_source", T(), server_default=_d("Manual Entry")),
             sa.Column("auto_refresh", T(), server_default=_d("Disabled (manual)")),
             sa.Column("user_id", I(), nullable=False, autoincrement=False),
             sa.PrimaryKeyConstraint("user_id", name="pk_settings"))
    sa.Table("sip_log", m, _id(),
             sa.Column("holding_id", I()),
             sa.Column("holding_name", T()),
             sa.Column("month", T()),
             sa.Column("sip_date", T()),
             sa.Column("amount", F()),
             sa.Column("applied_at", T(), server_default=now),
             sa.Column("user_id", I(), server_default=_d(1)), **ai)
    sa.Table("transactions", m, _id(),
             sa.Column("holding_id", I()),
             sa.Column("name", sa.String()),
             sa.Column("tx_date", sa.String(), nullable=False),
             sa.Column("kind", sa.String(), nullable=False),
             sa.Column("qty", F()),
             sa.Column("price", F()),
             sa.Column("amount", F()),
             sa.Column("fees", F()),
             sa.Column("realized", F()),
             sa.Column("note", sa.String()),
             sa.Column("source", sa.String()),
             sa.Column("applied", I()),
             sa.Column("user_id", I()))
    return m


def _seed(bind, m):
    """The starter rows init_db() inserted into a brand-new database, with the same values."""
    from db import seed
    from subcategories import SEED as SUB_SEED, match_rules

    t = m.tables
    bind.execute(t["settings"].insert(), [{"user_id": 1}])
    bind.execute(t["categories"].insert(), [
        {"id": cid, "name": name, "icon": icon, "color": color, "target_pct": pct, "hint": hint,
         "visible": int(visible), "sort_order": order, "end_month": None if visible else seed.HIDDEN_END_MONTH}
        for cid, name, icon, color, pct, hint, visible, order in seed.CATEGORIES])
    bind.execute(t["category_targets"].insert(), [
        {"category_id": c[0], "from_month": "0000-00", "target_pct": c[4]} for c in seed.CATEGORIES])
    bind.execute(t["budget_history"].insert(), [
        {"id": 1, "user_id": 1, "from_month": "0000-00", "income": seed.SETTINGS_INCOME,
         "savings_amount": seed.SETTINGS_INCOME * seed.SETTINGS_SAVINGS_TARGET / 100.0}])

    cb_date, cb_cat, cb_amount, cb = seed.FEB_2025_CASHBACK
    expenses = []
    for cat_id, days in seed.FEB_2025_AMOUNTS.items():
        for day, amount in days.items():
            d = f"2025-02-{day:02d}"
            expenses.append({"category_id": cat_id, "user_id": 1, "date": d, "amount": amount,
                             "note": seed.FEB_2025_NOTES.get(cat_id, {}).get(day, ""),
                             "cashback": cb if (d, cat_id, amount) == (cb_date, cb_cat, cb_amount) else 0})
    bind.execute(t["expenses"].insert(), expenses)

    subs, rules = t["subcategories"], t["subcategory_rules"]
    names = {c[1]: c[0] for c in seed.CATEGORIES}
    for cat_name, entries in SUB_SEED.items():
        cid = names.get(cat_name)
        if cid is None:
            continue
        for order, (sub_name, patterns) in enumerate(entries, start=1):
            sid = bind.execute(subs.insert().values(category_id=cid, name=sub_name, sort_order=order)).inserted_primary_key[0]
            if patterns:
                bind.execute(rules.insert(), [{"category_id": cid, "pattern": p, "match_type": "contains", "subcategory_id": sid}
                                              for p in patterns])
    # map the sample expenses to sub-categories by their notes, as the first sub-category migration did
    by_cat = {}
    for r in bind.execute(sa.select(rules.c.category_id, rules.c.pattern, rules.c.match_type, rules.c.subcategory_id)
                          .order_by(rules.c.id)).mappings():
        by_cat.setdefault(r["category_id"], []).append(dict(r))
    ex = t["expenses"]
    for eid, cid, note in bind.execute(sa.select(ex.c.id, ex.c.category_id, ex.c.note).order_by(ex.c.id)).all():
        sid = match_rules(by_cat.get(cid, []), note)
        if sid:
            bind.execute(ex.update().where(ex.c.id == eid).values(subcategory_id=sid))

    card = dict(seed.SBI_CARD)
    account_id = bind.execute(t["card_accounts"].insert().values(issuer=card["issuer"], label=card["name"])).inserted_primary_key[0]
    bind.execute(t["cards"].insert().values(account_id=account_id, **card))

    bind.execute(t["schema_migrations"].insert(), [{"version": v, "name": n} for v, n in seed.LEGACY_MIGRATIONS])
    sync_sequences(bind, ["categories", "budget_history"])


def upgrade() -> None:
    bind = op.get_bind()
    existing = table_names(bind)
    fresh = "categories" not in existing
    m = _tables(bind)
    missing = [tbl for name, tbl in m.tables.items() if name not in existing]
    if missing:
        m.create_all(bind, tables=missing, checkfirst=True)
    if fresh:
        _seed(bind, m)


def downgrade() -> None:
    bind = op.get_bind()
    existing = table_names(bind)
    m = _tables(bind)
    # 0a3ec7a2c0e3's downgrade leaves these two in their pre-Alembic shape; at the base they go with the rest.
    for name in ("portfolio_snapshots", "portfolio_plan"):
        if name in existing:
            op.drop_table(name)
    m.drop_all(bind, tables=[tbl for name, tbl in m.tables.items() if name in existing], checkfirst=True)
