"""
Deterministic Faker seeder for acme.db.

Row-count targets
-----------------
customers       ~300
users            ~40
products         ~60
orders          ~800
order_items    ~2000
invoices        ~750
payments        ~600
support_tickets ~200

Reproducibility: Faker.seed(42) + random.seed(42) → identical output on every run.
"""

import random
import sqlite3
from datetime import datetime, timedelta

from faker import Faker

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TAX_RATE = 0.08  # 8 % applied consistently to every invoice

CUSTOMER_TIERS = ["standard", "premium", "enterprise"]
TIER_WEIGHTS   = [0.60, 0.30, 0.10]

DEPARTMENTS = ["Sales", "Support", "Engineering", "Finance", "Warehouse"]
DEPT_SIZES  = {"Sales": 10, "Support": 10, "Engineering": 8, "Finance": 7, "Warehouse": 5}
DEPT_ROLES  = {
    "Sales":       ["Sales Rep", "Account Executive", "Sales Manager"],
    "Support":     ["Support Agent", "Support Lead", "Customer Success Manager"],
    "Engineering": ["Software Engineer", "DevOps Engineer", "QA Engineer"],
    "Finance":     ["Accountant", "Finance Analyst", "Controller"],
    "Warehouse":   ["Warehouse Associate", "Inventory Manager", "Shipping Coordinator"],
}

PRODUCT_CATEGORIES = ["Camping", "Hiking", "Climbing", "Apparel", "Accessories"]

# (name_template, category, (price_lo, price_hi), cost_fraction)
# Templates are cycled / shuffled to reach ~60 unique products.
PRODUCT_TEMPLATES = [
    ("{adj} Alpine Tent {size}",        "Camping",     (120,  600), 0.45),
    ("{adj} Base Camp Tent {size}",     "Camping",     ( 80,  400), 0.45),
    ("{adj} Sleeping Bag {temp}F",      "Camping",     ( 60,  350), 0.40),
    ("{adj} Camp Stove {model}",        "Camping",     ( 30,  150), 0.35),
    ("{adj} Camping Lantern {model}",   "Camping",     ( 20,   80), 0.35),
    ("{adj} Trekking Poles {model}",    "Hiking",      ( 40,  200), 0.40),
    ("{adj} Daypack {vol}L",            "Hiking",      ( 50,  250), 0.40),
    ("{adj} Hydration Pack {vol}L",     "Hiking",      ( 60,  200), 0.40),
    ("{adj} Trail Shoes {model}",       "Hiking",      ( 80,  200), 0.45),
    ("{adj} Hiking Boots {model}",      "Hiking",      (120,  350), 0.45),
    ("{adj} Climbing Harness {model}",  "Climbing",    ( 50,  200), 0.40),
    ("{adj} Climbing Shoes {model}",    "Climbing",    ( 60,  200), 0.45),
    ("{adj} Carabiner Set {model}",     "Climbing",    ( 20,   80), 0.30),
    ("{adj} Climbing Helmet {model}",   "Climbing",    ( 60,  200), 0.40),
    ("{adj} Belay Device {model}",      "Climbing",    ( 20,   80), 0.30),
    ("{adj} Base Layer Top {model}",    "Apparel",     ( 40,  120), 0.35),
    ("{adj} Fleece Jacket {model}",     "Apparel",     ( 80,  250), 0.40),
    ("{adj} Rain Jacket {model}",       "Apparel",     (100,  350), 0.40),
    ("{adj} Sun Hat {model}",           "Apparel",     ( 20,   60), 0.30),
    ("{adj} Trekking Shorts {model}",   "Apparel",     ( 40,  100), 0.35),
    ("{adj} Wool Gloves {model}",       "Accessories", ( 20,   80), 0.35),
    ("{adj} Stuff Sack {vol}L",         "Accessories", ( 10,   40), 0.30),
    ("{adj} Water Filter {model}",      "Accessories", ( 30,  150), 0.35),
    ("{adj} First Aid Kit {model}",     "Accessories", ( 20,   80), 0.35),
    ("{adj} Headlamp {model}",          "Accessories", ( 25,  100), 0.35),
]

TENT_SIZES = ["1-Person", "2-Person", "3-Person", "4-Person", "6-Person"]
TEMPS      = ["-20", "0", "15", "30", "45"]
MODELS     = ["Pro", "Elite", "Sport", "Classic", "Ultra", "Lite", "Plus", "Max"]
VOLUMES    = [10, 15, 20, 25, 30, 40, 50, 65, 75]
ADJS       = ["Summit", "Trail", "Peak", "Alpine", "Ridge", "Canyon", "Glacier", "Apex"]

ORDER_STATUSES      = ["pending", "shipped", "delivered", "cancelled", "returned"]
ORDER_STATUS_WEIGHTS = [0.10, 0.15, 0.56, 0.07, 0.12]  # ~7 % cancelled → ~93 % → ~744 invoices

INVOICE_STATUSES      = ["paid", "sent", "overdue", "draft", "void"]
INVOICE_STATUS_WEIGHTS = [0.63, 0.15, 0.12, 0.07, 0.03]  # ~63 % paid → ~471 paid invoices

PAYMENT_METHODS = ["card", "ach", "check", "paypal"]

TICKET_STATUSES        = ["open", "in_progress", "resolved", "closed"]
TICKET_PRIORITIES      = ["low", "medium", "high", "urgent"]
TICKET_PRIORITY_WEIGHTS = [0.30, 0.40, 0.20, 0.10]

TICKET_SUBJECTS = [
    "Order not received",
    "Wrong item shipped",
    "Damaged product on arrival",
    "Return/exchange request",
    "Billing question",
    "Product defect under warranty",
    "Missing items in shipment",
    "Shipping delay inquiry",
    "Refund not processed",
    "Account access issue",
    "Product sizing question",
    "Warranty claim submission",
    "Price match request",
    "Gift order issue",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _render_product_name(template: str) -> str:
    """Fill {adj}, {size}, {temp}, {vol}, {model} placeholders."""
    name = template
    name = name.replace("{adj}",   random.choice(ADJS))
    name = name.replace("{size}",  random.choice(TENT_SIZES))
    name = name.replace("{temp}",  random.choice(TEMPS))
    name = name.replace("{vol}",   str(random.choice(VOLUMES)))
    name = name.replace("{model}", random.choice(MODELS))
    return name


def _cents(amount_float: float) -> int:
    """Convert a dollar float rounded to 2 dp into an integer number of cents."""
    return round(amount_float * 100)


def _dollars(cents: int) -> float:
    """Convert integer cents back to a 2-dp dollar float."""
    return round(cents / 100, 2)


# ---------------------------------------------------------------------------
# Main seeder
# ---------------------------------------------------------------------------

def seed(db_path: str = "data/acme.db") -> None:
    fake = Faker()
    Faker.seed(42)
    random.seed(42)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.cursor()

    # Fixed reference "now" so all date ranges are identical on every run.
    now = datetime(2026, 6, 1, 12, 0, 0)

    # -----------------------------------------------------------------------
    # 1. customers  (~300)
    # -----------------------------------------------------------------------
    three_years_ago = now - timedelta(days=3 * 365)
    customer_rows = []
    seen_emails: set = set()
    for _ in range(300):
        while True:
            email = fake.email()
            if email not in seen_emails:
                seen_emails.add(email)
                break
        signup = fake.date_between(
            start_date=three_years_ago.date(), end_date=now.date()
        )
        tier = random.choices(CUSTOMER_TIERS, TIER_WEIGHTS)[0]
        customer_rows.append((
            fake.name(),
            email,
            fake.phone_number(),
            fake.city(),
            fake.state_abbr(),
            signup.isoformat(),
            tier,
        ))
    cur.executemany(
        "INSERT INTO customers(name,email,phone,city,state,signup_date,tier) VALUES (?,?,?,?,?,?,?)",
        customer_rows,
    )
    customer_ids = list(range(1, 301))

    # -----------------------------------------------------------------------
    # 2. users  (~40)
    # -----------------------------------------------------------------------
    user_rows = []
    seen_user_emails: set = set()
    dept_id_ranges: dict = {}  # dept -> list of user ids

    uid = 1
    for dept, count in DEPT_SIZES.items():
        dept_ids = []
        for _ in range(count):
            while True:
                username = fake.user_name()
                email = f"{username}@acmeoutfitters.example"
                if email not in seen_user_emails:
                    seen_user_emails.add(email)
                    break
            role      = random.choice(DEPT_ROLES[dept])
            hire_date = fake.date_between(start_date="-6y", end_date=now.date())
            is_active = 1 if random.random() > 0.10 else 0
            user_rows.append((
                fake.name(),
                email,
                dept,
                role,
                hire_date.isoformat(),
                is_active,
            ))
            dept_ids.append(uid)
            uid += 1
        dept_id_ranges[dept] = dept_ids

    cur.executemany(
        "INSERT INTO users(name,email,department,role,hire_date,is_active) VALUES (?,?,?,?,?,?)",
        user_rows,
    )

    sales_user_ids   = dept_id_ranges["Sales"]    # 10 ids
    support_user_ids = dept_id_ranges["Support"]  # 10 ids

    # -----------------------------------------------------------------------
    # 3. products  (~60)
    # -----------------------------------------------------------------------
    product_rows   = []
    product_prices = []  # parallel list, indexed 0-based → product_id = index+1
    category_seq: dict = {}  # category_abbr -> counter for SKU generation
    used_names: set = set()

    # Expand template list to ensure we can produce 60 distinct entries.
    expanded = PRODUCT_TEMPLATES * 4
    random.shuffle(expanded)

    for tmpl_name, category, (price_lo, price_hi), cost_frac in expanded:
        if len(product_rows) >= 60:
            break
        name = _render_product_name(tmpl_name)
        if name in used_names:
            continue
        used_names.add(name)

        abbr = category[:4].upper()
        category_seq[abbr] = category_seq.get(abbr, 0) + 1
        sku   = f"ACM-{abbr}-{category_seq[abbr]:03d}"
        price = round(random.uniform(price_lo, price_hi), 2)
        cost  = round(price * cost_frac * random.uniform(0.85, 1.00), 2)
        stock = random.randint(0, 200)
        is_disc = 1 if random.random() < 0.05 else 0

        product_rows.append((sku, name, category, price, cost, stock, is_disc))
        product_prices.append(price)

    cur.executemany(
        "INSERT INTO products(sku,name,category,price,cost,stock_qty,is_discontinued) VALUES (?,?,?,?,?,?,?)",
        product_rows,
    )
    product_ids = list(range(1, len(product_rows) + 1))

    # -----------------------------------------------------------------------
    # 4. orders  (~800)
    # -----------------------------------------------------------------------
    two_years_ago = now - timedelta(days=2 * 365)
    order_rows   = []
    order_status_map: dict = {}  # order_id (1-based) -> status

    for i in range(800):
        cid    = random.choice(customer_ids)
        odate  = fake.date_time_between(start_date=two_years_ago, end_date=now)
        status = random.choices(ORDER_STATUSES, ORDER_STATUS_WEIGHTS)[0]
        # ~60 % of orders have a sales rep (the rest are web/direct orders)
        srep   = random.choice(sales_user_ids) if random.random() < 0.60 else None
        order_rows.append((cid, odate.isoformat(sep=" ", timespec="seconds"), status, srep))
        order_status_map[i + 1] = status

    cur.executemany(
        "INSERT INTO orders(customer_id,order_date,status,sales_rep_id) VALUES (?,?,?,?)",
        order_rows,
    )
    order_ids = list(range(1, 801))

    # -----------------------------------------------------------------------
    # 5. order_items  (~2000, avg ~2.5 per order)
    # -----------------------------------------------------------------------
    item_rows: list = []
    # order_id -> list of (product_id, quantity, unit_price)
    order_line_items: dict = {}

    for oid in order_ids:
        # Weighted distribution gives E[n] ≈ 2.5
        n = random.choices([1, 2, 3, 4, 5], weights=[20, 35, 25, 15, 5])[0]
        chosen_pids = random.sample(product_ids, min(n, len(product_ids)))
        lines = []
        for pid in chosen_pids:
            qty        = random.randint(1, 5)
            unit_price = product_prices[pid - 1]
            item_rows.append((oid, pid, qty, unit_price))
            lines.append((pid, qty, unit_price))
        order_line_items[oid] = lines

    cur.executemany(
        "INSERT INTO order_items(order_id,product_id,quantity,unit_price) VALUES (?,?,?,?)",
        item_rows,
    )

    # -----------------------------------------------------------------------
    # 6. invoices  (~750 — one per non-cancelled order)
    # -----------------------------------------------------------------------
    invoice_rows: list   = []
    # invoice_id (1-based) -> amount in cents (int) for lossless arithmetic
    inv_amount_cents: dict = {}
    inv_status_map: dict   = {}
    inv_issue_date: dict   = {}

    inv_seq = 0
    for oid in order_ids:
        if order_status_map[oid] == "cancelled":
            continue

        inv_seq += 1
        inv_id = inv_seq

        # Amount = subtotal × (1 + TAX_RATE), rounded to 2 dp
        subtotal_cents = sum(
            _cents(qty * unit_price)
            for _, qty, unit_price in order_line_items[oid]
        )
        amount_cents = round(subtotal_cents * (1 + TAX_RATE))
        amount       = _dollars(amount_cents)

        odate_str  = order_rows[oid - 1][1]          # "YYYY-MM-DD HH:MM:SS"
        odate      = datetime.fromisoformat(odate_str)
        issue_date = (odate + timedelta(days=random.randint(0, 3))).date()
        due_date   = issue_date + timedelta(days=30)

        year       = issue_date.year
        inv_number = f"INV-{year}-{inv_seq:05d}"
        inv_status = random.choices(INVOICE_STATUSES, INVOICE_STATUS_WEIGHTS)[0]

        invoice_rows.append((
            oid,
            inv_number,
            issue_date.isoformat(),
            due_date.isoformat(),
            amount,
            inv_status,
        ))
        inv_amount_cents[inv_id] = amount_cents
        inv_status_map[inv_id]   = inv_status
        inv_issue_date[inv_id]   = issue_date

    cur.executemany(
        "INSERT INTO invoices(order_id,invoice_number,issue_date,due_date,amount,status) VALUES (?,?,?,?,?,?)",
        invoice_rows,
    )

    # -----------------------------------------------------------------------
    # 7. payments  (~600)
    #
    # Rules:
    #   • Only create payments for 'paid' invoices (and a subset of 'overdue').
    #   • For every 'paid' invoice: SUM(payments.amount) == invoice.amount exactly.
    #     We use integer-cent arithmetic to guarantee this — no floating-point drift.
    #   • Some paid invoices are split across 2 payments; the remainder is computed
    #     in cents so split_cents + remainder_cents == amount_cents by construction.
    #   • A random sample of 'overdue' invoices gets one partial payment (< amount).
    # -----------------------------------------------------------------------
    payment_rows: list = []

    paid_ids    = [iid for iid, s in inv_status_map.items() if s == "paid"]
    overdue_ids = [iid for iid, s in inv_status_map.items() if s == "overdue"]

    # Paid invoices: ~25 % get 2 payments (split), rest get 1.
    for iid in paid_ids:
        a_cents    = inv_amount_cents[iid]
        issue_date = inv_issue_date[iid]
        if random.random() < 0.20 and a_cents > 1:
            # Split into two parts that sum exactly to a_cents.
            frac = random.uniform(0.30, 0.70)
            p1_cents = max(1, round(a_cents * frac))
            p2_cents = a_cents - p1_cents          # exact by construction
            for p_cents in (p1_cents, p2_cents):
                pay_date = (issue_date + timedelta(days=random.randint(1, 30))).isoformat()
                payment_rows.append((
                    iid,
                    pay_date,
                    _dollars(p_cents),
                    random.choice(PAYMENT_METHODS),
                ))
        else:
            pay_date = (issue_date + timedelta(days=random.randint(1, 30))).isoformat()
            payment_rows.append((
                iid,
                pay_date,
                _dollars(a_cents),
                random.choice(PAYMENT_METHODS),
            ))

    # Overdue invoices: a random sample gets a single partial payment to boost count.
    overdue_sample = random.sample(overdue_ids, min(50, len(overdue_ids)))
    for iid in overdue_sample:
        a_cents    = inv_amount_cents[iid]
        issue_date = inv_issue_date[iid]
        partial_cents = max(1, round(a_cents * random.uniform(0.20, 0.75)))
        pay_date = (issue_date + timedelta(days=random.randint(1, 30))).isoformat()
        payment_rows.append((
            iid,
            pay_date,
            _dollars(partial_cents),
            random.choice(PAYMENT_METHODS),
        ))

    cur.executemany(
        "INSERT INTO payments(invoice_id,payment_date,amount,method) VALUES (?,?,?,?)",
        payment_rows,
    )

    # -----------------------------------------------------------------------
    # 8. support_tickets  (~200)
    # -----------------------------------------------------------------------
    ticket_rows = []
    for _ in range(200):
        cid      = random.choice(customer_ids)
        # 70 % of tickets are linked to a specific order
        oid      = random.choice(order_ids) if random.random() < 0.70 else None
        assigned = random.choice(support_user_ids)
        created  = fake.date_time_between(start_date=two_years_ago, end_date=now)
        subject  = random.choice(TICKET_SUBJECTS)
        status   = random.choice(TICKET_STATUSES)
        priority = random.choices(TICKET_PRIORITIES, TICKET_PRIORITY_WEIGHTS)[0]
        ticket_rows.append((
            cid,
            oid,
            assigned,
            created.isoformat(sep=" ", timespec="seconds"),
            subject,
            status,
            priority,
        ))

    cur.executemany(
        "INSERT INTO support_tickets(customer_id,order_id,assigned_to,created_at,subject,status,priority) VALUES (?,?,?,?,?,?,?)",
        ticket_rows,
    )

    # -----------------------------------------------------------------------
    # Commit and report
    # -----------------------------------------------------------------------
    conn.commit()

    print("Row counts:")
    for table in [
        "customers", "users", "products", "orders", "order_items",
        "invoices", "payments", "support_tickets",
    ]:
        n = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table:20s}: {n:>6,}")

    conn.close()
