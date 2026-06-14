"""
Querious — FastAPI application entry point.

Routes
------
GET  /           Serves static/index.html
GET  /health     Liveness check; verifies both DB files exist
POST /chat       Accepts {session_id, message}; returns an SSE stream
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

# Anchor all file references to the project root, not the process CWD
_ROOT = Path(__file__).parent.parent

from cachetools import TTLCache
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

# Load .env before anything else so ANTHROPIC_API_KEY / VOYAGE_API_KEY are set
load_dotenv()

from app.chatbot import run_chat  # noqa: E402 (must be after load_dotenv)

# ---------------------------------------------------------------------------
# Per-session conversation history
# Key: session_id (str)
# Value: list of message dicts (mutated in-place by the chatbot loop)
#
# Bounded by a TTLCache so the dict cannot grow without limit in a long-running
# process.  At most MAX_SESSIONS entries are kept; an entry is evicted if it
# has not been accessed within SESSION_TTL seconds (1 hour).
# ---------------------------------------------------------------------------
_MAX_SESSIONS: int = 1000
_SESSION_TTL: int = 3600  # seconds

_conversation_histories: TTLCache = TTLCache(maxsize=_MAX_SESSIONS, ttl=_SESSION_TTL)
_histories_lock = threading.Lock()

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="Querious", description="AI chatbot for Acme Outfitters")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/")
async def serve_index() -> FileResponse:
    """Serve the static chat UI."""
    index_path = _ROOT / "static" / "index.html"
    return FileResponse(index_path, media_type="text/html")


@app.get("/health")
async def health() -> JSONResponse:
    """
    Liveness + readiness check.

    Returns 200 when both database files are present, 503 otherwise.
    """
    acme_db = _ROOT / "data" / "acme.db"
    embeddings_db = _ROOT / "data" / "embeddings.db"

    acme_ok = acme_db.exists()
    embeddings_ok = embeddings_db.exists()

    payload = {
        "status": "ok" if (acme_ok and embeddings_ok) else "degraded",
        "databases": {
            "acme_db": acme_ok,
            "embeddings_db": embeddings_ok,
        },
    }
    status_code = 200 if (acme_ok and embeddings_ok) else 503
    return JSONResponse(content=payload, status_code=status_code)


@app.get("/schema")
async def schema() -> JSONResponse:
    """Return the database schema (tables, columns, row counts) for the UI sidebar."""
    from app import db

    try:
        return JSONResponse(content={"tables": db.get_schema_structured()})
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(content={"error": str(exc)}, status_code=503)


class ChatRequest(BaseModel):
    session_id: str
    message: str


@app.post("/chat")
async def chat(request: ChatRequest) -> EventSourceResponse:
    """
    Accept a user message for a given session and stream the assistant's
    response as Server-Sent Events.

    SSE event types emitted:
        text        — assistant text delta
        tool_start  — {name, input} when a tool call begins
        tool_end    — {name, summary} when a tool call completes
        done        — turn complete; stream ends after this event
    """
    with _histories_lock:
        history = _conversation_histories.setdefault(request.session_id, [])

    async def _event_generator():
        try:
            async for event in run_chat(history, request.message):
                event_type = event["type"]
                if event_type == "text":
                    yield {"event": "text", "data": json.dumps({"text": event["text"]})}
                elif event_type == "tool_start":
                    yield {
                        "event": "tool_start",
                        "data": json.dumps({"name": event["name"], "input": event["input"]}),
                    }
                elif event_type == "tool_end":
                    yield {
                        "event": "tool_end",
                        "data": json.dumps({"name": event["name"], "summary": event["summary"]}),
                    }
                elif event_type == "done":
                    yield {"event": "done", "data": "{}"}
        except Exception as exc:  # noqa: BLE001
            # Surface errors to the client as a done event with an error field
            # so the UI isn't left in a spinning state.
            yield {
                "event": "done",
                "data": json.dumps({"error": str(exc)}),
            }

    return EventSourceResponse(_event_generator())
