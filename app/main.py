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
from pathlib import Path

# Anchor all file references to the project root, not the process CWD
_ROOT = Path(__file__).parent.parent

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

# Load .env before anything else so ANTHROPIC_API_KEY / VOYAGE_API_KEY are set
load_dotenv()

from app.chatbot import get_response_stream  # noqa: E402 (must be after load_dotenv)

# ---------------------------------------------------------------------------
# Per-session conversation history
# Key: session_id (str)
# Value: list of message dicts (mutated in-place by the chatbot loop)
# ---------------------------------------------------------------------------
_conversation_histories: dict[str, list] = {}

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
    history = _conversation_histories.setdefault(request.session_id, [])

    async def _event_generator():
        try:
            async for event in get_response_stream(history, request.message):
                yield event
        except Exception as exc:  # noqa: BLE001
            # Surface errors to the client as a done event with an error field
            # so the UI isn't left in a spinning state.
            yield {
                "event": "done",
                "data": json.dumps({"error": str(exc)}),
            }

    return EventSourceResponse(_event_generator())
