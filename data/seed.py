"""Faker-based seeder for acme.db. Deterministic with Faker.seed(42)."""
import random
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from faker import Faker

fake = Faker()
Faker.seed(42)
random.seed(42)

DB_PATH = Path(__file__).parent / "acme.db"


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    PRAGMA foreign_keys = ON;

    CREATE TABLE IF NOT EXISTS customers (
        id          INTEGER PRIMARY KEY,
        name        TEXT NOT NULL,
        email       TEXT NOT NULL UNIQUE,
        phone       TEXT,
        city        TEXT,
        state       TEXT,
        signup_date TEXT,
        tier        TEXT NOT NULL DEFAULT 'standard'
    );

    CREATE TABLE IF NOT EXISTS users (
        id          INTEGER PRIMARY KEY,
        name        TEXT NOT NULL,
        email       TEXT NOT NULL UNIQUE,
        department  TEXT,
        role        TEXT,
        hire_date   TEXT,
        is_active   INTEGER NOT NULL DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS products (
        id              INTEGER PRIMARY KEY,
        sku             TEXT NOT NULL UNIQUE,
        name            TEXT NOT NULL,
        category        TEXT,
        price           REAL NOT NULL,
        cost            REAL NOT NULL,
        stock_qty       INTEGER NOT NULL DEFAULT 0,
        is_discontinued INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS orders (
        id           INTEGER PRIMARY KEY,
        customer_id  INTEGER NOT NULL REFERENCES customers(id),
        order_date   TEXT NOT NULL,
        status       TEXT NOT NULL DEFAULT 'pending',
        sales_rep_id INTEGER REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS order_items (
        id          INTEGER PRIMARY KEY,
        order_id    INTEGER NOT NULL REFERENCES orders(id),
        product_id  INTEGER NOT NULL REFERENCES products(id),
        quantity    INTEGER NOT NULL DEFAULT 1,
        unit_price  REAL NOT NULL
    );

    CREATE TABLE IF NOT EXISTS invoices (
        id             INTEGER PRIMARY KEY,
        order_id       INTEGER NOT NULL UNIQUE REFERENCES orders(id),
        invoice_number TEXT NOT NULL UNIQUE,
        issue_date     TEXT NOT NULL,
        due_date       TEXT NOT NULL,
        amount         REAL NOT NULL,
        status         TEXT NOT NULL DEFAULT 'draft'
    );

    CREATE TABLE IF NOT EXISTS payments (
        id           INTEGER PRIMARY KEY,
        invoice_id   INTEGER NOT NULL REFERENCES invoices(id),
        payment_date TEXT NOT NULL,
        amount       REAL NOT NULL,
        method       TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS support_tickets (
        id          INTEGER PRIMARY KEY,
        customer_id INTEGER NOT NULL REFERENCES customers(id),
        order_id    INTEGER REFERENCES orders(id),
        assigned_to INTEGER REFERENCES users(id),
        created_at  TEXT NOT NULL,
        subject     TEXT NOT NULL,
        status      TEXT NOT NULL DEFAULT 'open',
        priority    TEXT NOT NULL DEFAULT 'medium'
    );
    """)


def seed(conn: sqlite3.Connection) -> None:
    today = date.today()
    three_years_ago = today - timedelta(days=3 * 365)
    two_years_ago = today - timedelta(days=2 * 365)

    # ------------------------------------------------------------------
    # Customers (~300)
    # ------------------------------------------------------------------
    states = [
        "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
        "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
        "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
        "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
        "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    ]
    tiers = ["standard"] * 14 + ["premium"] * 5 + ["enterprise"] * 1

    customers = []
    for i in range(300):
        signup = fake.date_between(start_date=three_years_ago, end_date=today)
        customers.append((
            fake.name(),
            fake.unique.email(),
            fake.phone_number()[:20],
            fake.city(),
            random.choice(states),
            signup.isoformat(),
            random.choice(tiers),
        ))

    conn.executemany(
        "INSERT INTO customers (name,email,phone,city,state,signup_date,tier) VALUES (?,?,?,?,?,?,?)",
        customers,
    )

    # ------------------------------------------------------------------
    # Users (~40 employees)
    # ------------------------------------------------------------------
    departments = {
        "Sales": ["Sales Rep", "Account Executive", "Sales Manager"],
        "Support": ["Support Agent", "Senior Support Specialist", "Support Manager"],
        "Engineering": ["Software Engineer", "Senior Engineer", "Engineering Lead"],
        "Finance": ["Accountant", "Financial Analyst", "CFO"],
        "Warehouse": ["Warehouse Associate", "Inventory Manager", "VP of Operations"],
    }

    users = []
    for dept, roles in departments.items():
        for _ in range(8):
            hire = fake.date_between(
                start_date=date(2015, 1, 1), end_date=today - timedelta(days=30)
            )
            users.append((
                fake.name(),
                fake.unique.email().replace("@", f"_{dept.lower()}@").split("@")[0]
                + "@acmeoutfitters.example",
                dept,
                random.choice(roles),
                hire.isoformat(),
                1 if random.random() > 0.1 else 0,
            ))

    conn.executemany(
        "INSERT INTO users (name,email,department,role,hire_date,is_active) VALUES (?,?,?,?,?,?)",
        users,
    )

    # ------------------------------------------------------------------
    # Products (~60)
    # ------------------------------------------------------------------
    categories = {
        "Camping": [
            ("TrailLite 2 Tent", 249.99), ("AlpineShield 4P Tent", 449.99),
            ("BaseCamp 6 Tent", 349.99), ("SkyView Tarp", 89.99),
            ("Sleeping Pad Pro", 79.99), ("Camp Lantern", 39.99),
            ("Cook Set Deluxe", 59.99), ("Camp Chair", 49.99),
            ("Cooler 45L", 129.99), ("Hammock Ultra", 69.99),
            ("Fire Starter Kit", 19.99), ("Bear Canister", 74.99),
        ],
        "Hiking": [
            ("DayHiker 20L Pack", 89.99), ("TrailRunner 45L Pack", 179.99),
            ("Expedition 65L Pack", 279.99), ("Trekking Poles", 64.99),
            ("Hydration Bladder 2L", 29.99), ("Trail Gaiters", 44.99),
            ("Dry Bag Set", 34.99), ("Navigation Compass", 24.99),
            ("First Aid Kit", 29.99), ("Headlamp Pro", 49.99),
        ],
        "Climbing": [
            ("Climbing Harness", 89.99), ("Belay Device", 34.99),
            ("Carabiner 6-Pack", 44.99), ("Climbing Helmet", 79.99),
            ("Chalk Bag", 19.99), ("Rock Shoes", 129.99),
            ("Climbing Rope 60m", 199.99), ("Crash Pad", 249.99),
        ],
        "Apparel": [
            ("Rain Jacket", 149.99), ("Fleece Pullover", 89.99),
            ("Hiking Pants", 74.99), ("Merino Base Layer", 64.99),
            ("Sun Hat", 29.99), ("Gloves Liner", 24.99),
            ("Down Vest", 119.99), ("Trail Running Shorts", 44.99),
            ("Wool Socks 3-Pack", 24.99), ("Balaclava", 19.99),
        ],
        "Accessories": [
            ("CanisterLite Stove", 44.99), ("WhisperFlame Stove", 79.99),
            ("LiquidFuel Pro Stove", 149.99), ("Water Filter", 39.99),
            ("Trekking Pole Tips", 9.99), ("Pack Rain Cover", 19.99),
            ("Stuff Sack 10L", 14.99), ("Insulated Bottle 32oz", 29.99),
            ("Emergency Bivy", 24.99), ("Sunscreen SPF50", 14.99),
        ],
    }

    products = []
    sku_counter = 1
    for cat, items in categories.items():
        for name, price in items:
            cost = round(price * random.uniform(0.35, 0.55), 2)
            sku = f"ACM-{cat[:3].upper()}-{sku_counter:03d}"
            products.append((
                sku, name, cat, price, cost,
                random.randint(0, 200),
                1 if random.random() < 0.05 else 0,
            ))
            sku_counter += 1

    conn.executemany(
        "INSERT INTO products (sku,name,category,price,cost,stock_qty,is_discontinued) VALUES (?,?,?,?,?,?,?)",
        products,
    )

    customer_ids = [r[0] for r in conn.execute("SELECT id FROM customers").fetchall()]
    product_rows = conn.execute("SELECT id, price FROM products").fetchall()
    support_user_ids = [
        r[0]
        for r in conn.execute(
            "SELECT id FROM users WHERE department='Support'"
        ).fetchall()
    ]
    sales_user_ids = [
        r[0]
        for r in conn.execute(
            "SELECT id FROM users WHERE department='Sales'"
        ).fetchall()
    ]

    # ------------------------------------------------------------------
    # Orders (~800) + order_items (~2000) + invoices + payments
    # ------------------------------------------------------------------
    order_statuses = ["pending", "shipped", "delivered", "cancelled", "returned"]
    order_status_weights = [0.05, 0.15, 0.60, 0.12, 0.08]
    invoice_statuses = ["draft", "sent", "paid", "overdue", "void"]
    payment_methods = ["card", "ach", "check", "paypal"]

    invoice_num = 1
    for _ in range(800):
        cust_id = random.choice(customer_ids)
        order_dt = fake.date_time_between(
            start_date=two_years_ago, end_date=datetime.now()
        )
        status = random.choices(order_statuses, weights=order_status_weights)[0]
        sales_rep = random.choice(sales_user_ids) if random.random() > 0.3 else None

        conn.execute(
            "INSERT INTO orders (customer_id,order_date,status,sales_rep_id) VALUES (?,?,?,?)",
            (cust_id, order_dt.isoformat(), status, sales_rep),
        )
        order_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # 1–4 items per order
        num_items = random.randint(1, 4)
        selected = random.sample(product_rows, min(num_items, len(product_rows)))
        total = 0.0
        for prod_id, unit_price in selected:
            qty = random.randint(1, 5)
            conn.execute(
                "INSERT INTO order_items (order_id,product_id,quantity,unit_price) VALUES (?,?,?,?)",
                (order_id, prod_id, qty, unit_price),
            )
            total += qty * unit_price

        # Tax
        total = round(total * 1.08, 2)

        # Invoice (not for cancelled orders)
        if status != "cancelled":
            issue_dt = order_dt.date() + timedelta(days=1)
            due_dt = issue_dt + timedelta(days=30)

            if status == "delivered":
                inv_status = random.choices(
                    ["paid", "overdue", "sent"], weights=[0.70, 0.15, 0.15]
                )[0]
            elif status == "returned":
                inv_status = "void"
            else:
                inv_status = random.choice(["draft", "sent"])

            conn.execute(
                "INSERT INTO invoices (order_id,invoice_number,issue_date,due_date,amount,status) "
                "VALUES (?,?,?,?,?,?)",
                (
                    order_id,
                    f"INV-{issue_dt.year}-{invoice_num:05d}",
                    issue_dt.isoformat(),
                    due_dt.isoformat(),
                    total,
                    inv_status,
                ),
            )
            inv_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            invoice_num += 1

            # Payments for paid invoices
            if inv_status == "paid":
                pay_dt = issue_dt + timedelta(days=random.randint(1, 29))
                conn.execute(
                    "INSERT INTO payments (invoice_id,payment_date,amount,method) VALUES (?,?,?,?)",
                    (inv_id, pay_dt.isoformat(), total, random.choice(payment_methods)),
                )

    # ------------------------------------------------------------------
    # Support tickets (~200)
    # ------------------------------------------------------------------
    ticket_statuses = ["open", "in_progress", "resolved", "closed"]
    ticket_priorities = ["low", "medium", "high", "urgent"]
    ticket_subjects = [
        "Order not received",
        "Damaged item on arrival",
        "Return request",
        "Wrong item shipped",
        "Billing question",
        "Warranty claim",
        "Account access issue",
        "Product defect report",
        "Shipping delay inquiry",
        "Refund status",
    ]

    for _ in range(200):
        cust_id = random.choice(customer_ids)
        created = fake.date_time_between(start_date=two_years_ago, end_date=datetime.now())
        # Random order for this customer (or None)
        order_rows = conn.execute(
            "SELECT id FROM orders WHERE customer_id=? LIMIT 5", (cust_id,)
        ).fetchall()
        order_id = random.choice(order_rows)[0] if order_rows and random.random() > 0.3 else None

        # Get customer tier
        tier = conn.execute(
            "SELECT tier FROM customers WHERE id=?", (cust_id,)
        ).fetchone()[0]

        # Premium/enterprise tickets skew toward open/in_progress
        if tier in ("premium", "enterprise"):
            st = random.choices(
                ticket_statuses, weights=[0.35, 0.30, 0.20, 0.15]
            )[0]
            pri = random.choices(
                ticket_priorities, weights=[0.1, 0.3, 0.4, 0.2]
            )[0]
        else:
            st = random.choices(
                ticket_statuses, weights=[0.25, 0.20, 0.30, 0.25]
            )[0]
            pri = random.choices(
                ticket_priorities, weights=[0.2, 0.4, 0.3, 0.1]
            )[0]

        assigned = random.choice(support_user_ids) if st != "open" else None

        conn.execute(
            "INSERT INTO support_tickets "
            "(customer_id,order_id,assigned_to,created_at,subject,status,priority) "
            "VALUES (?,?,?,?,?,?,?)",
            (
                cust_id,
                order_id,
                assigned,
                created.isoformat(),
                random.choice(ticket_subjects),
                st,
                pri,
            ),
        )


def main() -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        create_schema(conn)
        seed(conn)
        conn.commit()
        print(f"Database created at {DB_PATH}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
