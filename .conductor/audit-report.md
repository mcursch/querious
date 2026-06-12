# Conductor audit — ai_chatbot_tool

**36 findings** (15 blocker, 13 major, 8 minor)

## 🔴 Currently broken (12)

- **[blocker] Imports `ChatSession` and `TurnResult` classes that do not exist in `app.chatbot`** — `tests/test_acceptance_docs.py`
  - `app/chatbot.py` has no `ChatSession` or `TurnResult` classes; it only exposes the `get_response_stream` coroutine. All 8 tests in this module fail to collect with ImportError.
  - _Fix:_ Implement `ChatSession` (a synchronous wrapper holding history state) and `TurnResult` (a dataclass with `text`, `sources`, and `tool_calls` fields) in `app/chatbot.py`, or redesign the tests to use the existing async interface.
- **[blocker] Imports non-existent names `run_chat` and `_content_blocks_to_dicts` from `app.chatbot`** — `tests/test_chatbot.py`
  - `app/chatbot.py` exports `get_response_stream` and `_blocks_to_history`. The test module references `run_chat` and `_content_blocks_to_dicts`, neither of which exists, causing an ImportError that prevents all 12 tests from collecting.
  - _Fix:_ Rename the public API in `app/chatbot.py` to `run_chat` and `_content_blocks_to_dicts`, or update the test imports to use the real names.
- **[blocker] Imports non-existent name `_validate_query` from `app.db`** — `tests/test_db_safety.py`
  - The test file imports `_validate_query` and `_enforce_limit` from `app.db`, but the actual function in that module is named `_validate_sql`. The entire test module (13 tests) fails to collect with ImportError.
  - _Fix:_ Rename `_validate_sql` in `app/db.py` to `_validate_query`, or update the import in the test file to match the real name.
- **[blocker] Imports `chunk_document`, `_count_tokens`, `TARGET_TOKENS`, `MAX_TOKENS` that do not exist in `app.rag`** — `tests/test_rag.py`
  - `app/rag.py` contains only `search`, `_embed_query`, and `_blob_to_vec`. The heading-aware chunker, token counter, and token-size constants are implemented in `scripts/build_index.py` (as `chunk_markdown`, `MAX_CHARS`, etc.) and were never added to `app/rag.py`. All 14 tests fail to collect with ImportError.
  - _Fix:_ Move or re-expose the chunking logic from `scripts/build_index.py` into `app/rag.py` with the names `chunk_document`, `_count_tokens`, `TARGET_TOKENS`, and `MAX_TOKENS` that the tests expect.
- **[major] `QUERIOUS_DATA_DIR` env var set by conftest is never read by any app module** — `tests/conftest.py`
  - `conftest.py` writes a temp-dir path to `os.environ['QUERIOUS_DATA_DIR']` and seeds a fresh SQLite database there for test isolation. However `app/db.py`, `app/rag.py`, and `app/main.py` all hardcode their DB paths as `Path(__file__).parent.parent / 'data' / ...` and never consult this env var. Tests that rely on fixture-injected data therefore hit the real production databases in `data/`, breaking isolation.
  - _Fix:_ In `app/db.py`, `app/rag.py`, and `app/main.py`, compute the data-directory path as `Path(os.environ.get('QUERIOUS_DATA_DIR', Path(__file__).parent.parent / 'data'))` so the fixture override is honoured.
- **[major] `run_sql` imported from `app.tools` does not exist as a public name** — `tests/test_acceptance_selfcorrect.py`
  - Two tests do `from app.tools import run_sql` inside the function body at runtime, but the function is private (`_run_sql`). Both tests fail with `ImportError` when executed.
  - _Fix:_ Either expose `_run_sql` as a public `run_sql` function in `app/tools.py`, or update the test imports to use `_run_sql`.
- **[major] `_validate_sql` raises `ValueError` but tests expect it to return an error string** — `tests/test_db_safety.py`
  - Even if the import name mismatch were fixed, `app.db._validate_sql` raises `ValueError` on invalid input rather than returning an error string. Every test in `TestValidateQuery` that passes an invalid query calls `_validate_query(...)` and expects a non-None string return value, so they would all fail with an uncaught `ValueError` instead of an assertion.
  - _Fix:_ Change `_validate_sql` to return `None` on success and an error string on failure (removing the `raise ValueError` calls), or update the tests to use `pytest.raises(ValueError)`.
- **[major] Mock patches `anthropic.Anthropic.messages.create` but chatbot uses `AsyncAnthropic.messages.stream`** — `tests/test_e2e_sse.py`
  - Both `test_e2e_sse.py` and `test_acceptance_selfcorrect.py` patch `anthropic.Anthropic` and configure `messages.create.side_effect` with scripted responses. However `app/chatbot.py` instantiates `anthropic.AsyncAnthropic` and calls `messages.stream()` as an async context manager. The mock has zero effect; every test that depends on scripted LLM responses receives a real auth-failure error and fails.
  - _Fix:_ Change the test patches to `patch('app.chatbot.anthropic.AsyncAnthropic')` and configure `messages.stream` to return an async context manager that yields the scripted events.
- **[major] `test_health_both_dbs_present` accesses `body['acme_db']` but endpoint nests status under `body['databases']`** — `tests/test_e2e_sse.py`
  - The `/health` endpoint returns `{"status": ..., "databases": {"acme_db": ..., "embeddings_db": ...}}`. The test asserts `body['acme_db']` directly, which raises `KeyError` because the key is at `body['databases']['acme_db']`.
  - _Fix:_ Change the test assertions to `body['databases']['acme_db']` and `body['databases']['embeddings_db']`, or flatten the health response to put the DB flags at the top level.
- **[minor] Model identifier is `claude-opus-4-5` instead of the spec-required `claude-opus-4-8`** — `app/chatbot.py`
  - The `MODEL` constant on line 32 is set to `claude-opus-4-5`. The project spec explicitly mandates `claude-opus-4-8`. Using an incorrect model ID will cause API errors if `claude-opus-4-5` is not a valid model name, or silently use a different model than intended.
  - _Fix:_ Change `MODEL = 'claude-opus-4-5'` to `MODEL = 'claude-opus-4-8'` in `app/chatbot.py`.
- **[minor] `faker` is missing from `requirements.txt`** — `requirements.txt`
  - `data/seed.py` and `scripts/init_db.py` depend on the `Faker` library (as mandated by the spec), but `faker` is absent from `requirements.txt`. A fresh `pip install -r requirements.txt` will not install it, making the seeder fail with `ModuleNotFoundError`.
  - _Fix:_ Add `faker` to `requirements.txt`.
- **[minor] `ask()` helper extracts text using wrong SSE payload key `'delta'` instead of `'text'`** — `tests/test_acceptance_sql.py`
  - The chatbot emits SSE text events whose data payload is `{"text": "..."}`. The `ask()` helper collects `full_text` by calling `e.get('delta', '')` on each text event. Since no key named `delta` exists in the payload, `full_text` is always empty even when the API responds correctly, causing the content-assertion tests to fail silently.
  - _Fix:_ Change `e.get('delta', '')` to `e.get('text', '')` in the `ask()` function in `test_acceptance_sql.py`.

## 🧩 Unfinished / needs implementing (12)

- **[blocker] `ChatSession` and `TurnResult` classes imported but never implemented in `app/chatbot.py`** — `tests/test_acceptance_docs.py`
  - The acceptance test imports `ChatSession` and `TurnResult` from `app.chatbot`, but neither class exists. The chatbot module is built around the standalone async generator `get_response_stream` rather than a session-object API. Confirmed `ImportError` at pytest collection time.
  - _Fix:_ Implement a `ChatSession` class wrapping `get_response_stream` that maintains history internally and returns a `TurnResult` dataclass capturing `text`, `sources`, and `tool_calls` fields, as the acceptance tests expect.
- **[blocker] Test imports `run_chat` and `_content_blocks_to_dicts` which do not exist in `app/chatbot.py`** — `tests/test_chatbot.py`
  - The test file imports `run_chat` and `_content_blocks_to_dicts` from `app.chatbot`, but the module exports `get_response_stream` and `_blocks_to_history` respectively. Running pytest confirms an `ImportError` at collection time, making all 14 chatbot unit tests uncollectable.
  - _Fix:_ Either rename `get_response_stream` to `run_chat` and `_blocks_to_history` to `_content_blocks_to_dicts` in `app/chatbot.py`, or update the imports in the test file to match the actual names. The test also patches `app.chatbot.execute_tool` but the module-level name is `tools.execute_tool`, which would need a corresponding fix.
- **[blocker] Test imports non-existent function `_validate_query` — should be `_validate_sql`** — `tests/test_db_safety.py`
  - The test module imports `_validate_query` and `_enforce_limit` from `app.db`, but `app/db.py` defines `_validate_sql` (not `_validate_query`). This causes an `ImportError` at collection time, confirmed by running pytest: all 14 tests in this file cannot be collected.
  - _Fix:_ Rename `_validate_sql` to `_validate_query` in `app/db.py` (and update the single internal call site), or update the import in `tests/test_db_safety.py` to match the existing name.
- **[blocker] E2E and self-correction tests mock `anthropic.Anthropic.messages.create` but the app uses `anthropic.AsyncAnthropic.messages.stream`** — `tests/test_e2e_sse.py`
  - Both `test_e2e_sse.py` and `test_acceptance_selfcorrect.py` patch `anthropic.Anthropic` and set up `mock_client.messages.create.side_effect`. However, `app/chatbot.py` instantiates `anthropic.AsyncAnthropic` and calls `client.messages.stream(...)`. The mock target is the wrong class and the wrong method, so the mock never intercepts anything. Confirmed by test failure: the app uses the real async client, which errors without an API key; the SSE stream returns only a `done` event with an error, failing all four assertions in `test_sse_all_event_types_present`.
  - _Fix:_ Change the patch target to `app.chatbot.anthropic.AsyncAnthropic` and mock `messages.stream` as an async context manager yielding stream events, matching the actual call site in `chatbot.py`.
- **[blocker] Test imports `chunk_document`, `_count_tokens`, `TARGET_TOKENS`, `MAX_TOKENS` which are absent from `app/rag.py`** — `tests/test_rag.py`
  - The RAG unit tests import four names — `chunk_document`, `_count_tokens`, `TARGET_TOKENS`, and `MAX_TOKENS` — from `app.rag`, but none of them are defined there. The module only exposes `search`, `_embed_query`, and `_blob_to_vec`. Running pytest confirms an `ImportError` at collection time, blocking all 13 tests.
  - _Fix:_ Move the `chunk_markdown` function from `scripts/build_index.py` into `app/rag.py`, rename it `chunk_document`, and add the `_count_tokens`, `TARGET_TOKENS`, and `MAX_TOKENS` constants so the module matches what both the tests and `build_index.py` need.
- **[major] SQL keyword validation bypassed when forbidden keywords are adjacent to parentheses without whitespace** — `app/db.py`
  - The `_validate_sql` function detects forbidden keywords by splitting on whitespace and checking membership. Tokens like `(DELETE`, `(UPDATE`, or `(INSERT` are not equal to `DELETE`, `UPDATE`, or `INSERT`, so queries such as `WITH x AS(DELETE FROM customers)SELECT 1` and `SELECT * FROM(INSERT INTO customers VALUES(...))` pass validation. Verified with a Python REPL: all three bypass variants returned without raising `ValueError`. The spec's safety rule 2 is partially violated (mitigated only by the read-only connection at the SQLite layer).
  - _Fix:_ Replace the whitespace-split membership check with a regex word-boundary search: `re.search(r'\b' + kw + r'\b', upper)` to correctly catch keywords regardless of adjacent punctuation.
- **[major] `/health` response nests DB flags under a `databases` key but test expects them at the top level** — `app/main.py`
  - The `/health` handler returns `{"status": "ok", "databases": {"acme_db": bool, "embeddings_db": bool}}`, but `test_health_both_dbs_present` accesses `body["acme_db"]` and `body["embeddings_db"]` directly, producing a `KeyError: 'acme_db'`. Confirmed by running pytest.
  - _Fix:_ Either flatten the health response so `acme_db` and `embeddings_db` are top-level keys, or update the test to access `body["databases"]["acme_db"]`. The test comment implies the flat structure was intended.
- **[major] `QUERIOUS_DATA_DIR` env var set in conftest but never read by `app/db.py` or `app/rag.py`** — `tests/conftest.py`
  - The `setup_test_data` fixture creates hermetic SQLite databases in a temp directory and exports `QUERIOUS_DATA_DIR` intending the app to use them. But `app/db.py` and `app/rag.py` both compute their paths at module load time using `Path(__file__).parent.parent / 'data' / ...` and never consult this environment variable. All tests that rely on the fixture for isolation actually point at the repo's real `data/` directory (or fail if it does not exist).
  - _Fix:_ Add a `QUERIOUS_DATA_DIR` check in `app/db.py` and `app/rag.py` (e.g. `Path(os.environ.get('QUERIOUS_DATA_DIR', _ROOT / 'data'))`) so the path can be overridden in tests.
- **[major] Tests import public `run_sql` from `app.tools` but only the private `_run_sql` exists; also checks for non-existent `row_count` key** — `tests/test_acceptance_selfcorrect.py`
  - Two tests do `from app.tools import run_sql`, but the function is named `_run_sql` in `app/tools.py`. Both fail with `ImportError`. Additionally, even if the import were fixed, the test asserts `"row_count" in good` but `_run_sql` returns `{"rows": ..., "count": ...}` — the key is `count`, not `row_count`.
  - _Fix:_ Expose `_run_sql` as a public `run_sql` in `app/tools.py`, and fix the test assertion to use the `count` key instead of `row_count`.
- **[minor] Model identifier `claude-opus-4-5` does not match the spec's `claude-opus-4-8`** — `app/chatbot.py`
  - The spec specifies the LLM as `claude-opus-4-8`, but `app/chatbot.py` sets `MODEL = "claude-opus-4-5"`. The model IDs are different and will resolve to different model versions.
  - _Fix:_ Update `MODEL` in `app/chatbot.py` to `"claude-opus-4-8"` as specified.
- **[minor] Thinking mode uses `{"type": "enabled"}` instead of the spec-required `{"type": "adaptive"}`** — `app/chatbot.py`
  - The spec calls for `thinking={"type": "adaptive"}` (adaptive thinking), but `app/chatbot.py` passes `thinking={"type": "enabled", "budget_tokens": 8000}` (always-on thinking with a fixed budget). These are different operating modes with different cost and latency profiles.
  - _Fix:_ Change the `thinking` parameter in the `client.messages.stream` call to `{"type": "adaptive"}` to match the spec.
- **[minor] `faker` is absent from `requirements.txt` but required by the seeder and init script** — `requirements.txt`
  - `data/seed.py` and `scripts/init_db.py` both `from faker import Faker`, but `faker` does not appear in `requirements.txt`. A fresh `pip install -r requirements.txt` followed by `python scripts/init_db.py` will fail with `ModuleNotFoundError: No module named 'faker'`.
  - _Fix:_ Add `faker` to `requirements.txt`.

## 🐛 Likely bugs & security (12)

- **[blocker] Import of non-existent `ChatSession` / `TurnResult` prevents all docs-path acceptance tests** — `tests/test_acceptance_docs.py`
  - The module unconditionally imports `ChatSession` and `TurnResult` from `app.chatbot` (after a `skipif` guard that only fires when DB files are absent, not on ImportError). Neither class is implemented anywhere in `app/chatbot.py`, so collection fails with ImportError regardless of DB state.
  - _Fix:_ Implement `ChatSession` and `TurnResult` in `app/chatbot.py` as thin wrappers around `get_response_stream`, or restructure the test to call the streaming API directly.
- **[blocker] Import of non-existent `run_sql` from `app.tools` causes two tests to error** — `tests/test_acceptance_selfcorrect.py`
  - `test_run_sql_returns_error_for_bad_table` and `test_run_sql_succeeds_for_correct_table` both do `from app.tools import run_sql`. The module only exposes the private `_run_sql` and the dispatcher `execute_tool`; there is no public `run_sql`. Both tests raise ImportError.
  - _Fix:_ Either expose a public `run_sql` function in `app/tools.py` that wraps `_run_sql`, or update the tests to call `execute_tool('run_sql', {'query': ...})` instead.
- **[blocker] Import of non-existent `run_chat` / `_content_blocks_to_dicts` breaks all chatbot unit tests** — `tests/test_chatbot.py`
  - The test imports `run_chat` and `_content_blocks_to_dicts` from `app.chatbot`, but those symbols do not exist—the actual names are `get_response_stream` and `_blocks_to_history`. All tests in the file fail at collection with ImportError.
  - _Fix:_ Update the test imports to match the real function names (`get_response_stream`, `_blocks_to_history`), and update all call sites and assertions accordingly.
- **[blocker] Import of non-existent `_validate_query` prevents all SQL-safety tests from running** — `tests/test_db_safety.py`
  - The test module imports `_validate_query` from `app.db`, but the function is named `_validate_sql` in that module. Every test in the file fails with ImportError at collection time, leaving the SQL validation layer completely untested.
  - _Fix:_ Rename the import (and every reference in the test) to `_validate_sql`, or rename the production function to `_validate_query`. Also note the test expects the function to return a string on failure, while the production function raises `ValueError`—that interface gap must be reconciled too.
- **[blocker] E2E and self-correction tests mock the wrong Anthropic client class, so scripted responses never fire** — `tests/test_e2e_sse.py`
  - Both `test_e2e_sse.py` and `test_acceptance_selfcorrect.py` patch `anthropic.Anthropic` and stub `messages.create`, but `app/chatbot.py` instantiates `anthropic.AsyncAnthropic` and calls `messages.stream()`. The patch target does not match, so the mock is never invoked. Confirmed by running the tests: all scripted tool calls are absent and only a `done` event is observed (the server-side exception handler fires because no real credentials are present).
  - _Fix:_ Change the patch target to `anthropic.AsyncAnthropic` and replace `messages.create.side_effect` with an async-compatible mock for `messages.stream` that returns an async context manager producing the scripted content.
- **[blocker] Import of non-existent `chunk_document` / token constants from `app.rag` breaks all RAG unit tests** — `tests/test_rag.py`
  - The test imports `chunk_document`, `_count_tokens`, `TARGET_TOKENS`, and `MAX_TOKENS` from `app.rag`, but `app/rag.py` only exposes `search()`. The chunking logic (`chunk_markdown`, `split_text`) lives in `scripts/build_index.py` and is never imported into the app package. All tests fail at collection with ImportError.
  - _Fix:_ Move (or re-export) `chunk_markdown`/`split_text` and the token-estimation helper into `app/rag.py` so the app module and the test agree on where these symbols live.
- **[major] SQL keyword validation bypassed when keyword is adjacent to a parenthesis** — `app/db.py`
  - `_validate_sql` checks forbidden keywords with `kw in upper.split()`, which splits only on whitespace. A keyword immediately preceded by `(` — such as `(UPDATE` or `(DELETE` — never equals the bare keyword string, so CTEs like `WITH t AS (UPDATE customers SET name='x' WHERE 1=0)` and `WITH t AS (DELETE FROM customers)` both pass validation. Confirmed live: neither raises a ValueError.
  - _Fix:_ Replace the `split()`-based check with a regex word-boundary search, e.g. `re.search(r'\b' + kw + r'\b', upper)`, so keywords are caught regardless of surrounding punctuation.
- **[major] `_enforce_limit` wraps queries that have a trailing semicolon, producing invalid SQL** — `app/db.py`
  - `_validate_sql` strips the trailing `;` for its own validation but does not modify the `sql` variable. `execute_query` then passes the original (semicolon-bearing) string to `_enforce_limit`, which wraps it as `SELECT * FROM (SELECT * FROM t;) _q LIMIT 200`. SQLite rejects this with `near ";": syntax error`. Confirmed live.
  - _Fix:_ At the start of `execute_query` (or inside `_enforce_limit`), strip the trailing semicolon from `sql` before calling `_enforce_limit`, e.g. `sql = sql.rstrip().rstrip(';')`.
- **[major] `QUERIOUS_DATA_DIR` env var set by test fixture is never read by app code — test DB isolation is broken** — `tests/conftest.py`
  - The `setup_test_data` fixture sets `QUERIOUS_DATA_DIR` to a temporary directory intending to redirect all DB access to test data. Neither `app/db.py` nor `app/rag.py` reads this variable; both hard-code their DB paths via `Path(__file__).parent.parent / 'data'`. The fixture has zero effect: any test that actually reaches DB code will silently target the real (gitignored, likely absent) production files.
  - _Fix:_ Make `DB_PATH` in `app/db.py` and `EMBEDDINGS_DB` in `app/rag.py` read `os.environ.get('QUERIOUS_DATA_DIR')` when set, falling back to the current computed path.
- **[major] Health-check test asserts wrong JSON key path, always raises `KeyError`** — `tests/test_e2e_sse.py`
  - `test_health_both_dbs_present` asserts `body['acme_db']` and `body['embeddings_db']` at the top level of the JSON response, but the `/health` endpoint nests those booleans under `body['databases']['acme_db']` and `body['databases']['embeddings_db']`. Running the test confirms a `KeyError: 'acme_db'` failure.
  - _Fix:_ Update the assertions to `body['databases']['acme_db']` and `body['databases']['embeddings_db']`, matching the actual response structure in `app/main.py`.
- **[minor] Wrong model ID — `claude-opus-4-5` used instead of spec-required `claude-opus-4-8`** — `app/chatbot.py`
  - The `MODEL` constant is set to `"claude-opus-4-5"`, but the spec explicitly requires `"claude-opus-4-8"`. These are distinct model versions with different capability and pricing characteristics; the deployed chatbot does not match the intended spec.
  - _Fix:_ Change `MODEL = "claude-opus-4-5"` to `MODEL = "claude-opus-4-8"` in `app/chatbot.py`.
- **[minor] Unbounded `_conversation_histories` dict allows memory exhaustion via arbitrary session IDs** — `app/main.py`
  - The module-level `_conversation_histories` dict grows indefinitely: any caller can create a new entry by sending a unique `session_id`. There is no TTL, eviction, or size cap. A client (or accidental test loop) generating many unique session IDs will grow the dict until the process runs out of memory.
  - _Fix:_ Use an LRU cache (e.g. `functools.lru_cache` on a factory, or `cachetools.TTLCache`) capped at a reasonable number of sessions, or add a maximum-age TTL to evict stale sessions.

