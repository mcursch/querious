"""FastAPI application — Querious chatbot backend.

Endpoints
---------
POST /chat   JSON ``{session_id, message}`` → SSE stream
GET  /health Liveness probe; reports whether both DB files exist
GET  /       Serves static/index.html (when present)
"""

import json
import os

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse, ServerSentEvent

from app import chatbot, db

app = FastAPI(title="Querious")


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    session_id: str
    message: str


@app.post("/chat")
async def chat(request: ChatRequest):
    """Run the agentic loop and stream SSE events to the client."""

    async def event_stream():
        for event_type, event_data in chatbot.chat_stream(
            request.session_id, request.message
        ):
            yield ServerSentEvent(
                data=json.dumps(event_data),
                event=event_type,
            )

    return EventSourceResponse(event_stream())


@app.get("/health")
async def health():
    """Liveness probe.  Checks whether both SQLite DB files are present."""
    acme_present = os.path.exists(db.get_acme_db_path())
    embeddings_present = os.path.exists(db.get_embeddings_db_path())
    return JSONResponse(
        {
            "status": "ok",
            "acme_db": acme_present,
            "embeddings_db": embeddings_present,
        }
    )


# ---------------------------------------------------------------------------
# Static UI (optional — only mounted when static/ directory exists)
# ---------------------------------------------------------------------------

_static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.isdir(_static_dir):  # pragma: no cover
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="static")
