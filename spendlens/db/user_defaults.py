"""Starter data for a newly created user: the default categories and targets, sub-categories with their matching
rules, a placeholder budget and the reminder categories the calendar needs. The owner's own starter data (their goals,
a sample month, the first card) is not copied - a new person starts with an empty ledger.
"""
from . import seed
from .engine import SessionLocal
from .models import (BudgetHistory, Category, CategoryTarget, ReminderCategory, ReminderSettings, Settings, Subcategory,
                     SubcategoryRule)

# Shown until they set their own in Admin > Targets & Budget.
PLACEHOLDER_INCOME = 50000
PLACEHOLDER_SAVINGS = 10000

REMINDER_CATEGORIES = [("Bills & EMI", "#f5b942", None, 1), ("Card dates", "#fb7185", "card", 2), ("SIPs", "#3ecf8e", "sip", 3)]


def seed_user(user_id):
    """Idempotent: does nothing if this user already has categories. Uses its own unscoped session so the rows get
    exactly `user_id`, whoever (an admin) is making the request."""
    from subcategories import SEED as SUB_SEED

    with SessionLocal() as s:
        if s.query(Category.id).filter(Category.user_id == user_id).first():
            return
        s.add(Settings(user_id=user_id))
        s.add(BudgetHistory(user_id=user_id, from_month="0000-00", income=PLACEHOLDER_INCOME, savings_amount=PLACEHOLDER_SAVINGS))
        by_name = {}
        for _id, name, icon, color, pct, hint, visible, order in seed.CATEGORIES:
            c = Category(user_id=user_id, name=name, icon=icon, color=color, target_pct=pct, hint=hint,
                         visible=int(visible), sort_order=order, end_month=None if visible else seed.HIDDEN_END_MONTH)
            s.add(c)
            by_name[name] = c
        s.flush()
        for c in by_name.values():
            s.add(CategoryTarget(category_id=c.id, from_month="0000-00", target_pct=c.target_pct))
        for cat_name, entries in SUB_SEED.items():
            cat = by_name.get(cat_name)
            if cat is None:
                continue
            for order, (sub_name, patterns) in enumerate(entries, start=1):
                sub = Subcategory(user_id=user_id, category_id=cat.id, name=sub_name, sort_order=order)
                s.add(sub)
                s.flush()
                s.add_all([SubcategoryRule(user_id=user_id, category_id=cat.id, pattern=p, match_type="contains", subcategory_id=sub.id)
                           for p in patterns])
        for name, color, kind, order in REMINDER_CATEGORIES:
            s.add(ReminderCategory(user_id=user_id, name=name, color=color, kind=kind, sort_order=order))
        s.add(ReminderSettings(user_id=user_id))
        s.commit()
