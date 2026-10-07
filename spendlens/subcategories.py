"""Sub-categories: default set, note -> sub-category rules and the DB migration.

Rules match a pattern at the start of a word inside the (lower-cased) expense note. When
several rules match, the one that appears earliest wins (so "veg+fruits" maps to the first
item), ties go to the longer pattern. Rules of type 'exact' (created from the Admin review
screen) always win.
"""
import re
import sqlite3

# category name -> [(sub-category name, [patterns])]; order = display order
SEED = {
    "Rent / EMI": [
        ("Rent", ["rent", "zolo", "broker"]),
        ("Maintenance", ["maintai"]),
    ],
    "Utilities": [
        ("Electricity", ["electric"]),
        ("Internet & Phone", ["internet", "phone", "mobile", "broadband"]),
        ("OTT & Subscriptions", ["netflix", "prime", "youtube", "jio cinema", "naukri", "aws", "digibox", "movie"]),
        ("Insurance", ["hdfc life", "max life", "lic", "insurance", "premium payment", "sneha max"]),
        ("Water & Gas", ["water", "gas", "lpg", "indane"]),
        ("Car care", ["car"]),
        ("Home & personal", ["ac ", "tv ", "blanket", "maid", "parlor", "hair", "marcelus", "snabot"]),
    ],
    "Assistance": [
        ("Maid & Cook", ["maid", "cook"]),
        ("Salon & Grooming", ["haircut", "hair cut", "massag", "hair"]),
        ("Gas & Water", ["lpg", "gas", "water"]),
        ("Repairs & Cleaning", ["repair", "plumb", "electrition", "carpent", "tailor", "cleaning", "chimney", "fridge",
                                "induction", "mixer", "washing", "iron", "battery", "bathroom", "urban"]),
        ("Printing & Documents", ["print", "adhar", "copy"]),
        ("Car & Travel", ["car", "petrol", "uber", "parking"]),
    ],
    "Transport": [
        ("Fuel", ["petrol", "diesel"]),
        ("Cab & Auto", ["cab", "auto", "uber", "ola", "toto", "pool car"]),
        ("Parking & Toll", ["parking", "toll"]),
        ("Flights", ["flight"]),
        ("Train & Bus", ["train", "bus", "ticket", "kuli", "how-tata", "tata-how"]),
        ("Car maintenance", ["car", "puc", "servic", "tier", "tyre", "jump", "repair", "rat spray", "insurance", "policy"]),
        ("Other travel", ["market", "travel", "transport", "pm mall", "eco park", "hotel", "home", "courrier", "office", "laddu"]),
    ],
    "Milk": [
        ("Milk", ["milk"]),
        ("Curd, paneer & ghee", ["curd", "paneer", "panner", "ghee", "butter"]),
        ("Other", ["yogabar"]),
    ],
    "Groceries": [
        ("Staples & pantry", ["grocer", "grocert", "grocry", "grocrry", "daal", "ata", "rice", "oil", "masala", "sugar", "sugerfree",
                              "oats", "muse", "muys", "kell", "millet", "maggie", "biscuit", "bread", "honey", "tea", "kesar",
                              "kismis", "dry fruits", "pista", "khakhra", "khakhara", "choclate", "chocolate", "breakfast",
                              "lunch", "protein", "sezwan", "monthly", "mustard", "restaurant", "machurian", "food"]),
        ("Online delivery", ["amazon", "zepto", "blinkit", "bbnow", "bb ", "big basket", "jio", "swiggy", "spencer", "ratnadeep",
                             "vishal", "reliance", "patanjali", "more"]),
        ("Fruits & veg", ["fruit", "veg", "sabji", "banana", "mango", "coconut", "salad"]),
        ("Dairy", ["milk", "curd", "paneer", "panner", "butter", "ghee"]),
        ("Meat & eggs", ["chicken", "egg", "fish", "mutton"]),
        ("Household", ["detergent", "soap", "jhadu", "garbage", "gargabe", "tissue", "tooth", "tiles", "hit", "liq", "dishwash",
                       "hand wash", "surf", "diaper", "water"]),
    ],
    "Fruits + Veg": [
        ("Fruits", ["fruit", "mango", "banana"]),
        ("Vegetables", ["veg", "salad", "sabji"]),
        ("Other", ["icecream", "coco water"]),
    ],
    "Egg / Chicken": [
        ("Egg", ["egg"]),
        ("Chicken", ["chicken"]),
        ("Fish & mutton", ["fish", "mutton"]),
        ("Other", ["licious", "curd", "eat out", "office food"]),
    ],
    "Eat Out / Order": [
        ("Office food", ["office"]),
        ("Food delivery", ["swiggy", "swggy", "zomato", "order", "blinkit"]),
        ("Cafe & snacks", ["ice cream", "icecream", "coffee", "cake", "chai", "tea", "juice", "coconut water", "samosa", "bhuja",
                           "momo", "pani puri", "golgappa", "vadapav", "kachori", "dhokla", "burger", "pizza", "kfc", "mcdonal",
                           "waffle", "haldiram", "choclate", "bread", "sourdough"]),
        ("Sweets", ["sweet", "rasgula", "rasganga", "jalabi", "ganguram", "pachugopal", "laddu"]),
        ("Dining out", ["eat out", "eatout", "eat outside", "dine", "dining", "biryani", "dosa", "idli", "idly", "udupi", "dabh",
                        "dhaba", "dhab", "restaurant", "nh1", "westin", "bbq", "legend", "cafe", "rameswaram", "madrasi", "sher",
                        "gupta", "litti", "daal", "friends", "anniversary", "birtday", "celebration", "food", "canteen", "lunch",
                        "breakfast", "outside", "patna", "indor", "ready to cook", "egg", "train", "udupi"]),
    ],
    "Shopping / Clothing": [
        ("Clothing", ["cloth", "dress", "shirt", "tshirt", "t-shirt", "pant", "jeans", "pyjama", "sweat", "sweter", "saree", "chudi",
                      "leggin", "vest", "inner", "socks", "jogger", "myntra", "zudio", "meesho", "meeso", "smitten", "hrx", "holi"]),
        ("Footwear & accessories", ["shoe", "slipper", "watch", "belt", "jewel", "neckle", "necklace", "earing", "bangle", "ghoongro",
                                    "bag", "suitcase", "makeup", "kushals", "sree"]),
        ("Electronics & gadgets", ["headphone", "mouse", "keyoard", "keyboard", "power bank", "laptop", "ups", "induction", "geyser"]),
        ("Home & kitchen", ["organizer", "door mat", "curtain", "bedsheet", "mattress", "pooja", "hanger", "veg cutter", "jhadu",
                            "table cloth", "mandir", "water bottle", "soap", "vishal", "vmart"]),
        ("Kids & gifts", ["toy", "stroller", "play", "gift", "first cry", "rakhi", "diaper"]),
        ("Returns & refunds", ["refund", "return"]),
    ],
    "School Fees": [
        ("Tuition & fees", ["school fee", "fees", "dps", "admission", "school", "anaya fees", "anaya school"]),
        ("Activities", ["dance", "swimming", "annual day"]),
        ("School transport", ["school transport", "transport", "transfport"]),
        ("Uniform & books", ["uniform", "dress", "dess", "copy", "book", "vest", "sports dress"]),
    ],
    "Doctor & Medicine": [
        ("Medicine", ["medic", "insulin", "insuline", "inuline", "injection", "p kit", "melatonin", "l cart", "vitamin", "eye drop",
                      "cream", "boldcare", "horlic", "whey", "protein", "alo vera", "moistur", "moister", "coconut oil", "why protein"]),
        ("Doctor visit", ["doctor", "doc ", "doc+", "gynic", "hospital", "speech", "skin doc", "ortho", "booking", "mummy fracture",
                          "mouth ulcer"]),
        ("Tests & scans", ["blood test", "scan", "test", "oxymeter", "eye check"]),
        ("Dentist", ["dentist", "teeth"]),
        ("Vaccination", ["vaccin", "vacine"]),
        ("Baby needs", ["babu milk", "bbu milk", "baby milk", "milk powder", "milk", "diaper", "wipes", "creap", "cream baby", "pillow"]),
        ("Insurance & claims", ["insurance", "claim"]),
        ("Eye care", ["eye glass", "eyeglass", "eye"]),
    ],
    "Miscellaneous": [
        ("Gifts & occasions", ["gift", "diwali", "puja", "pooja", "birthday", "donat", "funeral", "sindoor", "agarbati", "rakhi",
                               "ladu", "laddu", "mela", "chanda", "help someone"]),
        ("Personal (Choti)", ["choti", "miss", "maskara"]),
        ("EMI, fees & taxes", ["emi", "fees", "charges", "income tax", "smallcase", "marcellus", "marcelus", "zerodha", "ipo", "fee"]),
        ("Entertainment & hobbies", ["movie", "game", "swimming", "badminton", "puzzle", "toy", "play", "jhula", "jula", "gym", "course",
                                     "durga", "cycle", "time prime", "timepass"]),
        ("Home & gadgets", ["fan", "pump", "battery", "geyser", "fridge", "mouse", "keyboard", "keyoard", "usb", "torch", "jar",
                            "jet spray", "water filter", "vacuum", "kitchen", "chop", "tyre", "helmet", "umbrella", "bag", "bottle",
                            "glass cleaner", "garbage", "zip lock", "mobile", "earphone", "headphone", "iron", "cover", "mattress",
                            "gadda", "ups", "speed post", "couries", "cochroach", "insect", "acid", "cell phone", "tab", "comb",
                            "laptop", "pad", "file", "oil dispensor", "paint", "desk", "rechargable", "wrapper", "fryer", "sold"]),
        ("Kids & school", ["anaya", "babu", "copy", "book", "pencil", "drawing", "chart", "paper", "tiffin", "chappal", "shoe", "baby"]),
        ("Other", ["miscellenious", "others", "unknown", "not sure", "balance of", "chalan", "chips", "color", "hotel", "shifting"]),
    ],
}


def normalize(note):
    return re.sub(r"\s+", " ", (note or "").strip().lower())


def load_rules(db, category_id):
    return db.execute("SELECT pattern, match_type, subcategory_id FROM subcategory_rules WHERE category_id=?",
                      (category_id,)).fetchall()


def match_rules(rules, note):
    """Return the sub-category id a note maps to, or None."""
    n = normalize(note)
    if not n:
        return None
    for r in rules:
        if r["match_type"] == "exact" and r["pattern"] == n:
            return r["subcategory_id"]
    best = None  # (index, -length, sub id)
    for r in rules:
        if r["match_type"] != "contains":
            continue
        m = re.search(r"(?<![a-z0-9])" + re.escape(r["pattern"]), n)
        if m:
            key = (m.start(), -len(r["pattern"]))
            if best is None or key < best[0]:
                best = (key, r["subcategory_id"])
    return best[1] if best else None


def apply_rules(db, only_unmapped=True):
    """(Re)map expenses by note. Returns number of expenses updated."""
    where = "WHERE subcategory_id IS NULL" if only_unmapped else ""
    rows = db.execute(f"SELECT id, category_id, note FROM expenses {where}").fetchall()
    cache, updated = {}, 0
    for r in rows:
        if r["category_id"] not in cache:
            cache[r["category_id"]] = load_rules(db, r["category_id"])
        sid = match_rules(cache[r["category_id"]], r["note"])
        if sid:
            db.execute("UPDATE expenses SET subcategory_id=? WHERE id=?", (sid, r["id"]))
            updated += 1
    return updated


def migrate(conn, db_path):
    """Create tables, seed defaults and map history (idempotent)."""
    old_factory = conn.row_factory
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS subcategories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER NOT NULL REFERENCES categories(id),
            name TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 99,
            start_month TEXT NOT NULL DEFAULT '0000-00',
            end_month TEXT
        );
        CREATE TABLE IF NOT EXISTS subcategory_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER NOT NULL REFERENCES categories(id),
            pattern TEXT NOT NULL,
            match_type TEXT NOT NULL DEFAULT 'contains',
            subcategory_id INTEGER NOT NULL REFERENCES subcategories(id)
        );
    """)
    cols = {r[1] for r in c.execute("PRAGMA table_info(expenses)")}
    first_run = "subcategory_id" not in cols
    if first_run:
        conn.commit()
        bak = sqlite3.connect(db_path.replace(".db", ".pre-subcat.bak"))
        conn.backup(bak)
        bak.close()
        c.execute("ALTER TABLE expenses ADD COLUMN subcategory_id INTEGER REFERENCES subcategories(id)")
    if c.execute("SELECT COUNT(*) FROM subcategories").fetchone()[0] == 0:
        for cat_name, subs in SEED.items():
            cat = c.execute("SELECT id FROM categories WHERE name=?", (cat_name,)).fetchone()
            if not cat:
                continue
            for order, (sub_name, patterns) in enumerate(subs, start=1):
                sid = c.execute("INSERT INTO subcategories (category_id, name, sort_order) VALUES (?,?,?)",
                                (cat["id"], sub_name, order)).lastrowid
                for p in patterns:
                    c.execute("INSERT INTO subcategory_rules (category_id, pattern, match_type, subcategory_id) VALUES (?,?,?,?)",
                              (cat["id"], p, "contains", sid))
    if first_run:
        apply_rules(conn)
    conn.row_factory = old_factory


def subcategory_status(sub, today):
    if sub["start_month"] > today:
        return "scheduled"
    if sub["end_month"] is not None and sub["end_month"] < today:
        return "archived"
    return "active"


def subcategories_for_month(db, month, category_id=None):
    """Sub-categories to offer/show in a month: inside their [start, end] range, or holding data that month."""
    where = "WHERE s.category_id=?" if category_id else ""
    params = [f"{month}-%"] + ([category_id] if category_id else [])
    rows = db.execute(f"""
        SELECT s.*, EXISTS(SELECT 1 FROM expenses e WHERE e.subcategory_id=s.id AND e.date LIKE ?) AS month_has_data
        FROM subcategories s {where} ORDER BY s.category_id, s.sort_order, s.id""", params).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        in_range = d["start_month"] <= month and (d["end_month"] is None or month <= d["end_month"])
        if in_range or d.pop("month_has_data"):
            d["archived"] = not in_range
            out.append(d)
    return out


def sub_allowed(db, category_id, sub_id, month, keep_sub_id=None):
    """True if `sub_id` belongs to the category and is active in `month` (or is the entry's current value)."""
    row = db.execute("SELECT * FROM subcategories WHERE id=?", (sub_id,)).fetchone()
    if not row or row["category_id"] != category_id:
        return False
    if sub_id == keep_sub_id:
        return True
    return row["start_month"] <= month and (row["end_month"] is None or month <= row["end_month"])
