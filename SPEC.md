# Querious — Specification

An AI chatbot that answers questions about a fictional company (**Acme Outfitters**) by combining
RAG over company documentation with direct, read-only SQL access to the company database — so users
can get answers "in a technical way" even when no dedicated API endpoint exists for the question.

---

## 1. Overview

| Item | Decision |
|---|---|
| App name | **Querious** |
| Fake company | **Acme Outfitters** (outdoor gear retailer) |
| Backend | Python 3.10+ / FastAPI |
| LLM | Claude Opus 4.8 (`claude-opus-4-8`), adaptive thinking, agentic tool loop |
| Database | SQLite (relational data; opened read-only for the bot) |
| Embeddings | Voyage AI (`voyage-3.5`) |
| Vector store | SQLite (chunk text + embedding blobs, cosine similarity in Python) |
| UI | Minimal static HTML/JS chat page with SSE streaming + visible tool calls |
| Data seeding | Python + Faker |

### Core behaviors

1. **RAG path** — unstructured questions ("what's our return policy?") are answered by embedding
   the query, retrieving top-k document chunks, and citing source files.
2. **SQL path** — structured questions ("all unpaid invoices for Texas customers over $500") are
   answered by Claude reading the schema, writing a `SELECT`, executing it via a read-only tool,
   and summarizing the rows. No dedicated endpoint required.
3. **Combined** — the bot may use both paths in one turn (e.g. policy + matching records).
4. **Self-correction** — SQL errors are returned to Claude as tool results so it can fix and retry.

---

## 2. Project structure

```
ai_chatbot_tool/
├── SPEC.md                  # this file
├── app/
│   ├── main.py              # FastAPI app, /chat SSE endpoint, serves static UI
│   ├── chatbot.py           # Claude agentic loop (tools, history, streaming)
│   ├── tools.py             # Tool definitions: search_docs, get_schema, run_sql
│   ├── rag.py               # Chunking, Voyage embedding, cosine retrieval
│   └── db.py                # SQLite access (read-only URI connection for the bot)
├── data/
│   ├── seed.py              # Faker-based seeder
│   ├── docs/                # markdown docs for RAG (authored, see §5)
│   ├── acme.db              # SQLite DB (generated — gitignored)
│   └── embeddings.db        # vector store (generated — gitignored)
├── static/
│   └── index.html           # chat UI (vanilla JS, SSE, tool-call indicators)
├── scripts/
│   ├── init_db.py           # create schema + run seeder
│   └── build_index.py       # chunk docs → Voyage embeddings → embeddings.db
├── requirements.txt
├── .env.example             # ANTHROPIC_API_KEY, VOYAGE_API_KEY
└── .gitignore
```

---

## 3. Database schema (data/acme.db)

All tables seeded with Faker; row counts chosen so cross-table queries are interesting.

### customers (~300 rows)
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| name | TEXT | |
| email | TEXT | unique |
| phone | TEXT | |
| city | TEXT | |
| state | TEXT | US state code |
| signup_date | TEXT | ISO date, last 3 years |
| tier | TEXT | `standard` / `premium` / `enterprise` |

### users (~40 rows — Acme employees)
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| name | TEXT | |
| email | TEXT | @acmeoutfitters.example |
| department | TEXT | Sales / Support / Engineering / Finance / Warehouse |
| role | TEXT | |
| hire_date | TEXT | ISO date |
| is_active | INTEGER | 0/1 |

### products (~60 rows)
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| sku | TEXT | unique, e.g. `ACM-TENT-001` |
| name | TEXT | outdoor gear: tents, packs, stoves, apparel… |
| category | TEXT | Camping / Hiking / Climbing / Apparel / Accessories |
| price | REAL | |
| cost | REAL | < price |
| stock_qty | INTEGER | |
| is_discontinued | INTEGER | 0/1 |

### orders (~800 rows)
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| customer_id | INTEGER FK → customers | |
| order_date | TEXT | ISO datetime, last 2 years |
| status | TEXT | `pending` / `shipped` / `delivered` / `cancelled` / `returned` |
| sales_rep_id | INTEGER FK → users | nullable (web orders) |

### order_items (~2000 rows)
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| order_id | INTEGER FK → orders | |
| product_id | INTEGER FK → products | |
| quantity | INTEGER | 1–5 |
| unit_price | REAL | product price at time of order |

### invoices (~750 rows — one per non-cancelled order)
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| order_id | INTEGER FK → orders | unique |
| invoice_number | TEXT | `INV-2025-00042` style |
| issue_date | TEXT | ISO date |
| due_date | TEXT | issue + 30 days |
| amount | REAL | sum of order items (+ tax) |
| status | TEXT | `draft` / `sent` / `paid` / `overdue` / `void` |

### payments (~600 rows — for paid/partially-paid invoices)
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| invoice_id | INTEGER FK → invoices | |
| payment_date | TEXT | ISO date |
| amount | REAL | |
| method | TEXT | `card` / `ach` / `check` / `paypal` |

### support_tickets (~200 rows)
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| customer_id | INTEGER FK → customers | |
| order_id | INTEGER FK → orders | nullable |
| assigned_to | INTEGER FK → users | Support dept |
| created_at | TEXT | ISO datetime |
| subject | TEXT | |
| status | TEXT | `open` / `in_progress` / `resolved` / `closed` |
| priority | TEXT | `low` / `medium` / `high` / `urgent` |

**Seeding rules:** deterministic (`Faker.seed(42)`) so the dataset is reproducible; referential
integrity enforced; invoice/payment amounts must reconcile with order items so financial
questions have correct answers.

---

## 4. RAG pipeline

- **Chunking:** heading-aware markdown splitting, target ~500 tokens per chunk, ~50-token overlap.
  Each chunk stores: source filename, heading path, chunk text.
- **Embedding:** Voyage AI `voyage-3.5`, batched. Query embeddings use `input_type="query"`,
  document embeddings use `input_type="document"`.
- **Storage:** `embeddings.db` (SQLite): `chunks(id, source, heading, text, embedding BLOB)`.
  Embeddings stored as float32 numpy bytes.
- **Retrieval:** cosine similarity over all chunks (dataset is small — brute force is fine),
  return top-5 with source attribution.
- **Rebuild:** `scripts/build_index.py` is idempotent (drop + rebuild).

---

## 5. Documents to author (data/docs/)

Written so they contain facts NOT in the database (and vice versa), making the bot's
tool-choice visible. ~12 files:

1. `employee_handbook.md` — PTO policy, remote work rules, expense limits, code of conduct
2. `return_refund_policy.md` — 30-day returns, exclusions, refund timelines, restocking fees
3. `shipping_policy.md` — carriers, zones, free-shipping threshold, international rules
4. `warranty_policy.md` — per-category warranty terms, claim process
5. `pricing_tiers.md` — standard/premium/enterprise customer tier benefits & discounts
6. `sla.md` — support response-time commitments by ticket priority and customer tier
7. `product_guide_tents.md` — tent line specs, materials, care instructions
8. `product_guide_packs.md` — backpack line, fit guide, volume guidance
9. `product_guide_stoves.md` — stove line, fuel types, safety notes
10. `onboarding_guide.md` — new-employee onboarding checklist, systems access
11. `security_policy.md` — data handling, password rules, incident reporting
12. `company_overview.md` — history, mission, locations, org structure

---

## 6. Chatbot design

### Model & API
- `claude-opus-4-8`, `thinking={"type": "adaptive"}`, streaming responses.
- Manual agentic loop (not the SDK tool-runner) so tool events can be streamed to the UI.
- Conversation history kept server-side per session id; full history sent each turn.

### Tools

| Tool | Input | Behavior |
|---|---|---|
| `search_docs` | `query: str` | Embed query → top-5 chunks → return text + sources |
| `get_schema` | (none) | Return CREATE TABLE statements + row counts for all tables |
| `run_sql` | `query: str` | Validate, execute read-only, return rows as JSON (≤200 rows) |

### run_sql safety (required, in this order)
1. Connection opened with SQLite URI `file:data/acme.db?mode=ro` — writes impossible at the
   connection level.
2. Single statement only; must start with `SELECT` (or `WITH ... SELECT`); reject semicolon-chained
   statements and PRAGMA/ATTACH.
3. `LIMIT 200` enforced (wrap query if absent).
4. 5-second execution timeout via SQLite progress handler.
5. Errors returned as `is_error: true` tool results so Claude can self-correct.

### System prompt (essence)
- You are Querious, the internal assistant for Acme Outfitters.
- Use `search_docs` for policy/handbook/product-documentation questions.
- For data questions (counts, lists, lookups, aggregations), call `get_schema` first if you
  haven't seen the schema this conversation, then `run_sql`.
- Cite document sources; show the SQL you ran when summarizing query results.
- If a query errors, fix it and retry rather than giving up.

---

## 7. API & UI

### Endpoints
| Route | Method | Behavior |
|---|---|---|
| `/` | GET | Serves `static/index.html` |
| `/chat` | POST | `{session_id, message}` → SSE stream |
| `/health` | GET | Liveness + checks both DB files exist |

### SSE event types streamed to the UI
- `text` — assistant text delta
- `tool_start` — `{name, input}` (UI renders "🔍 searching docs…" / "🗄️ running SQL: …")
- `tool_end` — `{name, summary}` (e.g. "5 chunks" / "37 rows")
- `done` — turn complete

### UI requirements
- Single page, vanilla JS, no build step.
- Message bubbles; tool calls rendered inline as collapsible chips between text segments.
- SQL queries shown in a code block inside the tool chip.
- Enter to send; disabled input while streaming.

---

## 8. Environment & dependencies

`.env` (see `.env.example`):
```
ANTHROPIC_API_KEY=...
VOYAGE_API_KEY=...
```

`requirements.txt` (approximate):
```
fastapi
uvicorn[standard]
anthropic
voyageai
faker
numpy
python-dotenv
sse-starlette
```

---

## 9. Build phases & verification

| Phase | Deliverable | Verify by |
|---|---|---|
| 1 | Schema + seeder + authored docs | `sqlite3 data/acme.db` spot queries; row counts; FK integrity |
| 2 | RAG indexer + retrieval | Standalone retrieval test: known question → expected doc surfaces |
| 3 | Chatbot loop + tools | CLI smoke test: one docs question, one SQL question, one combined |
| 4 | FastAPI + chat UI | Browser test; tool chips render; streaming works |
| 5 | End-to-end QA | Question set covering docs-only, SQL-only, combined, SQL self-correction |

### Acceptance test questions
1. "What is the return policy on used tents?" → docs path, cites `return_refund_policy.md`
2. "How many customers do we have in California?" → SQL path
3. "List all overdue invoices over $500 with the customer name and state" → SQL with JOINs
4. "Do premium customers get faster support, and how many open tickets do they have right now?" → combined (SLA doc + SQL)
5. "What's our best-selling product category by revenue this year?" → SQL aggregation
6. Deliberately ambiguous table name in a question → bot checks schema / self-corrects

---

## 10. Out of scope (for now)

- Authentication / multi-user accounts
- Write operations of any kind through the bot
- Production deployment, Docker, CI
- Embedding-store ANN indexing (brute force is sufficient at this scale)
