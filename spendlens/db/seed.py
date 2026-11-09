"""Starter data a brand-new database gets: categories, a sample month (Feb 2025) of expenses and the first credit card.

Used by the baseline Alembic revision (every new database) and by database.init_db() (old pre-Alembic SQLite files).
"""

# id, name, icon, colour, target %, hint, visible, sort order
CATEGORIES = [
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

# Hidden categories get this end month when nothing was ever spent in them (as the admin migration did).
HIDDEN_END_MONTH = "2024-01"

# Feb 2025: {category id: {day: amount}} and the note on each of those entries.
FEB_2025_AMOUNTS = {
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
FEB_2025_NOTES = {
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
# The one Feb 2025 entry that earned cashback: (date, category id, amount, cashback)
FEB_2025_CASHBACK = ("2025-02-11", 1, 4262, 1575)

# settings defaults; the savings figure became an amount: income * savings_target / 100
SETTINGS_INCOME = 245000
SETTINGS_SAVINGS_TARGET = 44

# The first card, with the terms printed on its statements.
SBI_CARD = {
    "name": "CASHBACK SBI Card", "issuer": "SBI Card", "network": "", "last4": "82",
    "credit_limit": 400000, "cash_limit": 120000, "statement_day": 11, "due_day": 1,
    "annual_fee": 999, "fee_waiver_spend": 200000, "rate_online": 5, "rate_offline": 1, "cashback_cap": 5000,
    "notes": ("Fee waived on 2L spend in the preceding year. The per-cycle cap is a "
              "setting: the statements never reached it, so it could not be measured."),
    "profile": "sbi_cashback", "grace_days": 20, "cycle_verified": 1,
    "rates": '{"online": 5, "offline": 1, "excluded": 0}',
}

# The pre-Alembic numbered migrations, recorded as applied on a database built by the baseline revision.
LEGACY_MIGRATIONS = [
    (1, "baseline"), (2, "drop-unused-tables"), (3, "user-id-columns"), (4, "credit-cards"),
    (5, "card-profiles-and-cycles"), (6, "card-accounts"), (7, "card-txn-currency"), (8, "reward-points"),
    (9, "txn-category"), (10, "card-perks"), (11, "card-color"), (12, "card-sort-order"),
]
