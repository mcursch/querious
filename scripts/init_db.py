#!/usr/bin/env python3
"""
scripts/init_db.py

Create the acme.db schema and seed it with deterministic Faker data.
Run from the project root:
    python scripts/init_db.py
"""
import os
import sys
import sqlite3
import random
from datetime import date, datetime, timedelta
from pathlib import Path

try:
    from faker import Faker
except ImportError:
    print("ERROR: faker not installed. Run: pip install faker", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).parent.parent
DB_PATH = ROOT / "data" / "acme.db"

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE customers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    email       TEXT    UNIQUE NOT NULL,
    phone       TEXT,
    city        TEXT,
    state       TEXT,
    signup_date TEXT,
    tier        TEXT    DEFAULT 'standard'
);

CREATE TABLE users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    email       TEXT    UNIQUE NOT NULL,
    department  TEXT,
    role        TEXT,
    hire_date   TEXT,
    is_active   INTEGER DEFAULT 1
);

CREATE TABLE products (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    sku             TEXT    UNIQUE NOT NULL,
    name            TEXT    NOT NULL,
    category        TEXT,
    price           REAL,
    cost            REAL,
    stock_qty       INTEGER DEFAULT 0,
    is_discontinued INTEGER DEFAULT 0
);

CREATE TABLE orders (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id  INTEGER REFERENCES customers(id),
    order_date   TEXT,
    status       TEXT,
    sales_rep_id INTEGER REFERENCES users(id)
);

CREATE TABLE order_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id    INTEGER REFERENCES orders(id),
    product_id  INTEGER REFERENCES products(id),
    quantity    INTEGER,
    unit_price  REAL
);

CREATE TABLE invoices (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id       INTEGER UNIQUE REFERENCES orders(id),
    invoice_number TEXT UNIQUE,
    issue_date     TEXT,
    due_date       TEXT,
    amount         REAL,
    status         TEXT DEFAULT 'draft'
);

CREATE TABLE payments (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id   INTEGER REFERENCES invoices(id),
    payment_date TEXT,
    amount       REAL,
    method       TEXT
);

CREATE TABLE support_tickets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER REFERENCES customers(id),
    order_id    INTEGER REFERENCES orders(id),
    assigned_to INTEGER REFERENCES users(id),
    created_at  TEXT,
    subject     TEXT,
    status      TEXT DEFAULT 'open',
    priority    TEXT DEFAULT 'medium'
);
"""

# ---------------------------------------------------------------------------
# Seed data constants
# ---------------------------------------------------------------------------

US_STATES = [
    'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
    'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
    'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
    'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
    'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY',
]

TIERS = ['standard'] * 5 + ['premium'] * 3 + ['enterprise']

DEPARTMENTS = ['Sales', 'Support', 'Engineering', 'Finance', 'Warehouse']
ROLES = {
    'Sales':       ['Account Executive', 'Sales Manager', 'Sales Representative'],
    'Support':     ['Support Agent', 'Support Lead', 'Customer Success Manager'],
    'Engineering': ['Software Engineer', 'DevOps Engineer', 'QA Engineer', 'Data Engineer'],
    'Finance':     ['Accountant', 'Financial Analyst', 'Controller', 'Accounts Receivable'],
    'Warehouse':   ['Warehouse Associate', 'Inventory Manager', 'Shipping Coordinator',
                    'Receiving Specialist'],
}

# All 60 products (sku, name, category, price, cost)
PRODUCTS = [
    # Tents - Camping
    ('ACM-TENT-001', 'Trailhead 2-Person Tent',       'Camping',     249.99, 120.00),
    ('ACM-TENT-002', 'Summit 4-Person Tent',           'Camping',     399.99, 180.00),
    ('ACM-TENT-003', 'Ultralight Solo Tent',           'Camping',     349.99, 160.00),
    ('ACM-TENT-004', 'Base Camp 6-Person Tent',        'Camping',     549.99, 240.00),
    ('ACM-TENT-005', 'Expedition 3-Person Tent',       'Camping',     299.99, 135.00),
    ('ACM-TENT-006', 'Weekend Warrior Tent',           'Camping',     179.99,  80.00),
    ('ACM-TENT-007', 'Storm Shield 2-Person Tent',     'Camping',     449.99, 200.00),
    ('ACM-TENT-008', 'Family Dome 8-Person Tent',      'Camping',     649.99, 290.00),
    ('ACM-TENT-009', 'Bivy Sack Pro',                  'Camping',     149.99,  65.00),
    ('ACM-TENT-010', 'Tarp Shelter Ultralight',        'Camping',      89.99,  35.00),
    # Backpacks - Hiking
    ('ACM-PACK-001', 'Ridgeline 45L Backpack',         'Hiking',      189.99,  85.00),
    ('ACM-PACK-002', 'Summit 65L Backpack',            'Hiking',      249.99, 110.00),
    ('ACM-PACK-003', 'Daypack 20L',                    'Hiking',       79.99,  32.00),
    ('ACM-PACK-004', 'Ultralight 35L Pack',            'Hiking',      219.99,  95.00),
    ('ACM-PACK-005', 'Kids Hiking Pack 15L',           'Hiking',       59.99,  24.00),
    ('ACM-PACK-006', 'Trail Runner Vest 10L',          'Hiking',      129.99,  55.00),
    ('ACM-PACK-007', 'Expedition 80L Backpack',        'Hiking',      329.99, 145.00),
    ('ACM-PACK-008', 'Hydration Pack 2L',              'Hiking',       69.99,  28.00),
    ('ACM-PACK-009', 'Travel Duffel 40L',              'Hiking',       89.99,  38.00),
    ('ACM-PACK-010', "Summit 55L Women's Pack",        'Hiking',      239.99, 105.00),
    # Stoves - Camping
    ('ACM-STOV-001', 'Canister Stove Micro',           'Camping',      39.99,  15.00),
    ('ACM-STOV-002', 'Liquid Fuel Stove Pro',          'Camping',     129.99,  55.00),
    ('ACM-STOV-003', 'Wood Gasifier Stove',            'Camping',      79.99,  30.00),
    ('ACM-STOV-004', 'Integrated Cook System',         'Camping',      99.99,  42.00),
    ('ACM-STOV-005', 'Wind Burner Stove',              'Camping',     149.99,  65.00),
    # Climbing
    ('ACM-CLMB-001', 'Climbing Harness Sport',         'Climbing',     79.99,  32.00),
    ('ACM-CLMB-002', 'Climbing Harness Alpine',        'Climbing',    119.99,  50.00),
    ('ACM-CLMB-003', 'Quickdraw Set 6-Pack',           'Climbing',     89.99,  38.00),
    ('ACM-CLMB-004', 'Belay Device ATC',               'Climbing',     24.99,   9.00),
    ('ACM-CLMB-005', 'Locking Carabiner HMS',          'Climbing',     19.99,   7.50),
    ('ACM-CLMB-006', 'Climbing Helmet Shield',         'Climbing',     89.99,  38.00),
    ('ACM-CLMB-007', 'Rock Climbing Shoes Low',        'Climbing',    109.99,  45.00),
    ('ACM-CLMB-008', 'Rock Climbing Shoes High',       'Climbing',    139.99,  58.00),
    ('ACM-CLMB-009', 'Chalk Bag Pro',                  'Climbing',     29.99,  11.00),
    ('ACM-CLMB-010', 'Dynamic Rope 10mm 60m',          'Climbing',    199.99,  85.00),
    # Apparel
    ('ACM-APRL-001', 'Merino Base Layer Top',          'Apparel',      89.99,  38.00),
    ('ACM-APRL-002', 'Merino Base Layer Bottom',       'Apparel',      79.99,  32.00),
    ('ACM-APRL-003', 'Softshell Jacket',               'Apparel',     169.99,  72.00),
    ('ACM-APRL-004', 'Hardshell Rain Jacket',          'Apparel',     279.99, 120.00),
    ('ACM-APRL-005', 'Down Puffy Jacket',              'Apparel',     249.99, 105.00),
    ('ACM-APRL-006', 'Hiking Pants Convertible',       'Apparel',      89.99,  38.00),
    ('ACM-APRL-007', 'Fleece Mid Layer',               'Apparel',     129.99,  55.00),
    ('ACM-APRL-008', 'Sun Hoody UPF50',                'Apparel',      69.99,  28.00),
    ('ACM-APRL-009', 'Wool Hiking Socks 3-Pack',       'Apparel',      39.99,  15.00),
    ('ACM-APRL-010', 'Trail Running Shorts',           'Apparel',      59.99,  24.00),
    # Accessories
    ('ACM-ACCS-001', 'Trekking Poles Carbon',          'Accessories', 149.99,  62.00),
    ('ACM-ACCS-002', 'Trekking Poles Aluminum',        'Accessories',  79.99,  32.00),
    ('ACM-ACCS-003', 'Headlamp 350 Lumens',            'Accessories',  49.99,  19.00),
    ('ACM-ACCS-004', 'Headlamp 700 Lumens',            'Accessories',  79.99,  32.00),
    ('ACM-ACCS-005', 'Water Filter Straw',             'Accessories',  29.99,  11.00),
    ('ACM-ACCS-006', 'Water Filter Pump',              'Accessories',  89.99,  38.00),
    ('ACM-ACCS-007', 'First Aid Kit Comprehensive',    'Accessories',  49.99,  20.00),
    ('ACM-ACCS-008', 'Navigation Compass',             'Accessories',  39.99,  15.00),
    ('ACM-ACCS-009', 'Sleeping Bag 20F',               'Accessories', 199.99,  85.00),
    ('ACM-ACCS-010', 'Sleeping Pad Foam',              'Accessories',  39.99,  15.00),
    ('ACM-ACCS-011', 'Sleeping Pad Inflatable',        'Accessories', 129.99,  55.00),
    ('ACM-ACCS-012', 'Bear Canister 615 cu in',        'Accessories',  79.99,  32.00),
    ('ACM-ACCS-013', 'Sunglasses Polarized',           'Accessories',  79.99,  32.00),
    ('ACM-ACCS-014', 'Gaiters Trail Low',              'Accessories',  49.99,  20.00),
    ('ACM-ACCS-015', 'Camp Mug Insulated',             'Accessories',  24.99,   9.00),
]

ORDER_STATUSES   = ['pending', 'shipped', 'delivered', 'cancelled', 'returned']
ORDER_WEIGHTS    = [0.07, 0.18, 0.55, 0.12, 0.08]   # ~12% cancelled, ~8% returned
INVOICE_STATUSES = ['draft', 'sent', 'paid', 'overdue', 'void']
INVOICE_WEIGHTS  = [0.04, 0.16, 0.56, 0.18, 0.06]
PAYMENT_METHODS  = ['card', 'ach', 'check', 'paypal']
TICKET_STATUSES  = ['open', 'in_progress', 'resolved', 'closed']
TICKET_WEIGHTS   = [0.20, 0.15, 0.30, 0.35]
TICKET_PRIORITIES = ['low', 'medium', 'high', 'urgent']
TICKET_P_WEIGHTS  = [0.25, 0.45, 0.22, 0.08]

TICKET_SUBJECTS = [
    "Order has not arrived",
    "Wrong item received",
    "Return label not working",
    "Damaged item on arrival",
    "Request for invoice copy",
    "Question about warranty coverage",
    "Item out of stock — ETA?",
    "Billing discrepancy on account",
    "Need to change shipping address",
    "Refund not received",
    "Product defect after first use",
    "Bulk order pricing inquiry",
    "Exchange request",
    "Cannot log in to account",
    "Missing item from multi-item order",
    "Shipping delay — urgent restock needed",
    "Question about return policy for used gear",
    "Sales tax exemption certificate submission",
    "Requesting account tier upgrade",
    "Need size/fit recommendation",
]


def weighted_choice(choices, weights):
    return random.choices(choices, weights=weights, k=1)[0]


def main():
    fake = Faker()
    Faker.seed(42)
    random.seed(42)

    # Ensure data directory exists
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Remove existing DB
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA_SQL)

    today = date.today()
    three_yrs_ago = today - timedelta(days=3 * 365)
    five_yrs_ago  = today - timedelta(days=5 * 365)
    two_yrs_ago   = today - timedelta(days=2 * 365)

    # ------------------------------------------------------------------
    # 1. Customers (~300)
    # ------------------------------------------------------------------
    print("  Seeding customers...")
    customers = []
    emails_seen = set()
    while len(customers) < 300:
        email = fake.email()
        if email in emails_seen:
            continue
        emails_seen.add(email)
        signup = fake.date_between(start_date=three_yrs_ago, end_date=today)
        customers.append((
            fake.name(),
            email,
            fake.phone_number()[:20],
            fake.city(),
            random.choice(US_STATES),
            signup.isoformat(),
            weighted_choice(TIERS, [5, 5, 5, 3, 3, 3, 2, 2, 1]),
        ))
    conn.executemany(
        "INSERT INTO customers (name,email,phone,city,state,signup_date,tier) VALUES (?,?,?,?,?,?,?)",
        customers,
    )
    conn.commit()
    customer_ids = [row[0] for row in conn.execute("SELECT id FROM customers").fetchall()]

    # ------------------------------------------------------------------
    # 2. Users (~40 — Acme employees)
    # ------------------------------------------------------------------
    print("  Seeding users...")
    users = []
    user_emails_seen = set()
    support_user_ids = []  # filled after insert

    dept_distribution = (
        ['Sales'] * 10 + ['Support'] * 8 + ['Engineering'] * 12 +
        ['Finance'] * 6 + ['Warehouse'] * 4
    )
    random.shuffle(dept_distribution)
    dept_distribution = dept_distribution[:40]

    for dept in dept_distribution:
        first = fake.first_name()
        last  = fake.last_name()
        email = f"{first.lower()}.{last.lower()}@acmeoutfitters.example"
        # ensure unique email
        suffix = 1
        base_email = email
        while email in user_emails_seen:
            email = f"{base_email.split('@')[0]}{suffix}@acmeoutfitters.example"
            suffix += 1
        user_emails_seen.add(email)
        hire = fake.date_between(start_date=five_yrs_ago, end_date=today)
        users.append((
            f"{first} {last}",
            email,
            dept,
            random.choice(ROLES[dept]),
            hire.isoformat(),
            1 if random.random() > 0.08 else 0,
        ))
    conn.executemany(
        "INSERT INTO users (name,email,department,role,hire_date,is_active) VALUES (?,?,?,?,?,?)",
        users,
    )
    conn.commit()

    all_user_rows = conn.execute("SELECT id, department FROM users").fetchall()
    all_user_ids = [r[0] for r in all_user_rows]
    support_user_ids = [r[0] for r in all_user_rows if r[1] == 'Support']
    sales_user_ids   = [r[0] for r in all_user_rows if r[1] == 'Sales']
    # Fallback: if no support users generated, use all users
    if not support_user_ids:
        support_user_ids = all_user_ids
    if not sales_user_ids:
        sales_user_ids = all_user_ids

    # ------------------------------------------------------------------
    # 3. Products (60 — deterministic list)
    # ------------------------------------------------------------------
    print("  Seeding products...")
    product_rows = []
    for sku, name, category, price, cost in PRODUCTS:
        stock  = random.randint(0, 150)
        discontinued = 1 if random.random() < 0.08 else 0
        product_rows.append((sku, name, category, price, cost, stock, discontinued))
    conn.executemany(
        "INSERT INTO products (sku,name,category,price,cost,stock_qty,is_discontinued) "
        "VALUES (?,?,?,?,?,?,?)",
        product_rows,
    )
    conn.commit()

    product_rows_db = conn.execute("SELECT id, price FROM products").fetchall()
    product_ids     = [r[0] for r in product_rows_db]
    product_prices  = {r[0]: r[1] for r in product_rows_db}

    # ------------------------------------------------------------------
    # 4. Orders (~800)
    # ------------------------------------------------------------------
    print("  Seeding orders...")
    order_rows = []
    for _ in range(800):
        cid  = random.choice(customer_ids)
        odt  = fake.date_time_between(start_date=two_yrs_ago, end_date=datetime.now())
        status = weighted_choice(ORDER_STATUSES, ORDER_WEIGHTS)
        # 40% of orders have a sales rep (rest are web orders)
        rep_id = random.choice(sales_user_ids) if random.random() < 0.40 else None
        order_rows.append((cid, odt.isoformat(timespec='seconds'), status, rep_id))
    conn.executemany(
        "INSERT INTO orders (customer_id,order_date,status,sales_rep_id) VALUES (?,?,?,?)",
        order_rows,
    )
    conn.commit()
    order_db_rows = conn.execute("SELECT id, status FROM orders").fetchall()
    all_order_ids       = [r[0] for r in order_db_rows]
    non_cancelled_ids   = [r[0] for r in order_db_rows if r[1] != 'cancelled']

    # ------------------------------------------------------------------
    # 5. Order items (~2000; avg ~2.5 per order)
    # ------------------------------------------------------------------
    print("  Seeding order_items...")
    item_rows = []
    order_totals = {}  # order_id -> subtotal
    for oid in all_order_ids:
        n_items = random.choices([1, 2, 3, 4, 5], weights=[30, 35, 20, 10, 5])[0]
        chosen_products = random.sample(product_ids, min(n_items, len(product_ids)))
        subtotal = 0.0
        for pid in chosen_products:
            qty        = random.randint(1, 5)
            unit_price = round(product_prices[pid], 2)
            item_rows.append((oid, pid, qty, unit_price))
            subtotal  += qty * unit_price
        order_totals[oid] = round(subtotal, 2)
    conn.executemany(
        "INSERT INTO order_items (order_id,product_id,quantity,unit_price) VALUES (?,?,?,?)",
        item_rows,
    )
    conn.commit()

    # ------------------------------------------------------------------
    # 6. Invoices (~750 — one per non-cancelled order)
    # ------------------------------------------------------------------
    print("  Seeding invoices...")
    invoice_rows = []
    for seq, oid in enumerate(non_cancelled_ids, start=1):
        # Parse order date to get issue_date
        order_date_str = conn.execute(
            "SELECT order_date FROM orders WHERE id=?", (oid,)
        ).fetchone()[0]
        order_date = datetime.fromisoformat(order_date_str).date()
        issue_date = order_date + timedelta(days=1)
        due_date   = issue_date + timedelta(days=30)
        subtotal   = order_totals.get(oid, 0.0)
        amount     = round(subtotal * 1.08, 2)   # +8% tax
        inv_status = weighted_choice(INVOICE_STATUSES, INVOICE_WEIGHTS)
        invoice_number = f"INV-{issue_date.year}-{seq:05d}"
        invoice_rows.append((
            oid, invoice_number, issue_date.isoformat(),
            due_date.isoformat(), amount, inv_status,
        ))
    conn.executemany(
        "INSERT INTO invoices (order_id,invoice_number,issue_date,due_date,amount,status) "
        "VALUES (?,?,?,?,?,?)",
        invoice_rows,
    )
    conn.commit()

    # ------------------------------------------------------------------
    # 7. Payments (~600 — for paid/partially-paid invoices)
    # ------------------------------------------------------------------
    print("  Seeding payments...")
    invoice_db = conn.execute(
        "SELECT id, issue_date, amount, status FROM invoices"
    ).fetchall()

    payment_rows = []
    for inv_id, issue_str, amount, inv_status in invoice_db:
        if inv_status == 'paid':
            # Full payment
            pay_date = (
                datetime.fromisoformat(issue_str).date()
                + timedelta(days=random.randint(1, 28))
            )
            method = random.choice(PAYMENT_METHODS)
            payment_rows.append((inv_id, pay_date.isoformat(), round(amount, 2), method))
        elif inv_status in ('sent', 'overdue'):
            # ~50% chance of a partial payment
            if random.random() < 0.50:
                partial = round(amount * random.uniform(0.3, 0.75), 2)
                pay_date = (
                    datetime.fromisoformat(issue_str).date()
                    + timedelta(days=random.randint(1, 45))
                )
                method = random.choice(PAYMENT_METHODS)
                payment_rows.append((inv_id, pay_date.isoformat(), partial, method))
    conn.executemany(
        "INSERT INTO payments (invoice_id,payment_date,amount,method) VALUES (?,?,?,?)",
        payment_rows,
    )
    conn.commit()

    # ------------------------------------------------------------------
    # 8. Support tickets (~200)
    # ------------------------------------------------------------------
    print("  Seeding support_tickets...")
    ticket_rows = []
    # Use a subset of order ids for tickets with order references
    order_ids_with_tickets = random.sample(all_order_ids, min(120, len(all_order_ids)))
    ticket_order_ids = iter(order_ids_with_tickets)

    for i in range(200):
        cid     = random.choice(customer_ids)
        # ~60% of tickets are linked to an order
        if i < 120:
            try:
                oid = next(ticket_order_ids)
            except StopIteration:
                oid = None
        else:
            oid = None
        agent   = random.choice(support_user_ids)
        created = fake.date_time_between(start_date=two_yrs_ago, end_date=datetime.now())
        subject = random.choice(TICKET_SUBJECTS)
        status  = weighted_choice(TICKET_STATUSES, TICKET_WEIGHTS)
        priority = weighted_choice(TICKET_PRIORITIES, TICKET_P_WEIGHTS)
        ticket_rows.append((
            cid, oid, agent,
            created.isoformat(timespec='seconds'),
            subject, status, priority,
        ))
    conn.executemany(
        "INSERT INTO support_tickets "
        "(customer_id,order_id,assigned_to,created_at,subject,status,priority) "
        "VALUES (?,?,?,?,?,?,?)",
        ticket_rows,
    )
    conn.commit()

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    tables = [
        'customers', 'users', 'products', 'orders',
        'order_items', 'invoices', 'payments', 'support_tickets',
    ]
    print()
    print("  acme.db row counts:")
    for t in tables:
        n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"    {t:<20} {n:>6}")

    conn.close()
    print(f"\n  ✓ acme.db created at {DB_PATH}")


if __name__ == "__main__":
    main()
