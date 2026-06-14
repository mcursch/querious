# Querious

An AI assistant for a fictional outdoor-gear company, **Acme Outfitters**. It answers
questions two ways and decides which to use on the fly:

- **RAG** over company documents (policies, handbooks, product guides) — for unstructured
  knowledge, with source citations.
- **Live SQL** against the company database — it writes and runs a read-only `SELECT` to
  answer data questions **even when no API endpoint exists for them**. Ask "which sales rep
  has the highest margin?" and it queries the schema directly instead of needing a custom
  report.

It's powered by Claude (Opus 4.8) running an agentic tool loop, with a streaming chat UI
that shows every tool call (and the SQL) as it happens.

---

## Quickstart

Prerequisites: Python 3.10+, and two API keys — [Anthropic](https://console.anthropic.com)
and [Voyage AI](https://dashboard.voyageai.com) (Voyage has a free tier).

```bash
# 1. Install dependencies into a virtualenv
make install

# 2. Add your API keys
cp .env.example .env        # then edit .env:
#   ANTHROPIC_API_KEY=sk-ant-...
#   VOYAGE_API_KEY=pa-...

# 3. Build the data (seeds acme.db + embeds the docs into embeddings.db)
make setup

# 4. Run it
make run                    # http://localhost:8000
```

Open http://localhost:8000 and ask away. (No `make`? See [run.sh](run.sh) / the commands below.)

---

## Task runner

`make` targets (the npm-run equivalent):

| Command | Description |
|---|---|
| `make install` | Create `.venv` and install dependencies |
| `make setup` | Build the databases (seed + embed) |
| `make run` | Start the server on `0.0.0.0:8000` (override `HOST`/`PORT`) |
| `make dev` | Start with auto-reload |
| `make test` | Run the test suite |
| `make stop` | Stop a running server |
| `make clean` | Remove generated databases and caches |

`./run.sh` (with optional `--reload` / extra uvicorn args) does the same as `make run`.

---

## Try these

- **Docs:** "What's our return policy on used tents?"
- **SQL:** "How many customers do we have in California?"
- **Chart:** "Show me a bar chart of products in each category"
- **JOIN + CSV:** "List overdue invoices over $500 with the customer name and state" → download the result as CSV
- **Combined (docs + live data):** "Do premium customers get faster support per our SLA, and how many open tickets are there?"

The chat UI also has a **📊 Schema** button (see every table the bot can query) and renders
inline charts when the model emits one.

---

## How it works

```
Browser (static/index.html, SSE)
        │  POST /chat
        ▼
FastAPI (app/main.py) ── per-session history (TTL cache)
        │
        ▼
Agentic loop (app/chatbot.py) ── Claude Opus 4.8, adaptive thinking, prompt caching
        │  tools (app/tools.py)
        ├── search_docs → RAG retrieval (app/rag.py → Voyage embeddings, cosine search)
        ├── get_schema  → table/column DDL + row counts (app/db.py)
        └── run_sql     → validated, read-only SELECT (app/db.py)
```

**SQL safety:** the database is opened read-only (`mode=ro`); queries are validated to be a
single `SELECT`/`WITH` (no `INSERT`/`UPDATE`/`DELETE`/`PRAGMA`/…), capped at 200 rows, and
time-limited. Failed queries are returned to the model so it can self-correct.

---

## Layout

```
app/        FastAPI app, agentic loop, tools, RAG, DB access
data/       seed.py (Faker seeder), docs/ (12 markdown docs); acme.db + embeddings.db are generated
scripts/    init_db.py (schema + seed), build_index.py (chunk + embed)
static/     index.html (chat UI)
tests/      unit + live acceptance tests
setup.py    one-shot data build (init_db + build_index)
```

See [SPEC.md](SPEC.md) for the full design.

---

## Testing

```bash
make test
```

Unit/integration tests run offline. The live acceptance tests (which call the real model
against the seeded data) run automatically when `ANTHROPIC_API_KEY` and the databases are
present, and skip otherwise.

---

## Notes

- Generated databases (`data/acme.db`, `data/embeddings.db`) are git-ignored — rebuild with
  `make setup`.
- On the Voyage free tier (no payment method) embedding is rate-limited to 3 req/min;
  `build_index.py` throttles and retries to stay within it. Adding a payment method (the 200M
  free tokens still apply) makes index builds fast.
