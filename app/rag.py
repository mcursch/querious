"""RAG pipeline: chunking, embedding, and retrieval for Querious."""

from __future__ import annotations

import re
from typing import TypedDict


# ---------------------------------------------------------------------------
# Token estimation (whitespace-based, no external NLP library)
# ---------------------------------------------------------------------------

def _count_tokens(text: str) -> int:
    """Estimate token count by splitting on whitespace."""
    return len(text.split())


# ---------------------------------------------------------------------------
# Heading-aware markdown chunker
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)")

TARGET_TOKENS = 500
OVERLAP_TOKENS = 50
MAX_TOKENS = 600  # hard ceiling; individual paragraphs that exceed this are split


class Chunk(TypedDict):
    source: str
    heading: str
    text: str


def _heading_path(stack: list[str | None]) -> str:
    """Build a ' > '-joined path from the non-None heading stack entries."""
    return " > ".join(h for h in stack if h is not None)


def _flush_chunk(
    buffer: list[str],
    source: str,
    heading: str,
    chunks: list[Chunk],
) -> None:
    """Append the current buffer as a chunk (if non-empty)."""
    text = "\n".join(buffer).strip()
    if text:
        chunks.append({"source": source, "heading": heading, "text": text})


def chunk_document(text: str, source: str) -> list[Chunk]:
    """Split a markdown string into heading-aware chunks.

    Each chunk is a dict with keys:
        source  – the document filename / identifier passed in
        heading – ' > '-joined heading path at the start of the chunk
                  (e.g. 'Shipping Policy > International Rules')
        text    – chunk content (may include the heading lines themselves)

    Token counts use a simple whitespace split; no external NLP library.
    Target chunk size is ~500 tokens with ~50-token overlap; no chunk
    exceeds 600 tokens.
    """
    chunks: list[Chunk] = []

    # heading_stack[0] = current H1 title, [1] = H2, …, [5] = H6
    heading_stack: list[str | None] = [None] * 6

    buffer: list[str] = []        # lines accumulated for the current chunk
    buffer_tokens: int = 0
    # The heading path that was active when the current buffer started
    chunk_heading: str = ""

    def flush() -> None:
        nonlocal buffer, buffer_tokens, chunk_heading
        _flush_chunk(buffer, source, chunk_heading, chunks)
        # Keep last ~OVERLAP_TOKENS tokens as overlap for the next chunk
        overlap_lines: list[str] = []
        overlap_tok = 0
        for line in reversed(buffer):
            line_tok = _count_tokens(line)
            if overlap_tok + line_tok > OVERLAP_TOKENS:
                break
            overlap_lines.insert(0, line)
            overlap_tok += line_tok
        buffer = overlap_lines
        buffer_tokens = overlap_tok
        # Update the heading for the next chunk to the current heading path
        chunk_heading = _heading_path(heading_stack)

    # Pre-process: split any line that exceeds TARGET_TOKENS into word-based
    # sub-lines so that a single oversized paragraph cannot push a chunk past
    # MAX_TOKENS (overlap headings + a 600-word line, for example).
    raw_lines = text.splitlines()
    lines: list[str] = []
    for raw in raw_lines:
        if _count_tokens(raw) > TARGET_TOKENS and not _HEADING_RE.match(raw):
            words = raw.split()
            for start in range(0, len(words), TARGET_TOKENS):
                lines.append(" ".join(words[start : start + TARGET_TOKENS]))
        else:
            lines.append(raw)

    i = 0
    while i < len(lines):
        line = lines[i]
        m = _HEADING_RE.match(line)

        if m:
            level = len(m.group(1))  # 1-6
            title = m.group(2).strip()

            # Flush the current buffer before switching headings (only if
            # the buffer already has content; avoids empty leading chunks)
            if buffer_tokens > 0:
                flush()

            # Update the heading stack: set the current level, clear deeper ones
            heading_stack[level - 1] = title
            for deeper in range(level, 6):
                heading_stack[deeper] = None

            # Record the new heading for the chunk that is about to start
            chunk_heading = _heading_path(heading_stack)

            # Add the heading line itself to the buffer
            line_tok = _count_tokens(line)
            buffer.append(line)
            buffer_tokens += line_tok
        else:
            line_tok = _count_tokens(line)

            # If adding this line would push us well past the target, flush first
            if buffer_tokens + line_tok > TARGET_TOKENS and buffer_tokens > 0:
                flush()
                # After flush, the overlap lines are already in the buffer.
                # If this single line is itself huge, we may need to split it
                # (fall through and add it anyway; a hard split is done below).

            buffer.append(line)
            buffer_tokens += line_tok

            # Hard split: if a single run of text is over MAX_TOKENS, emit
            # immediately (prevents pathological paragraphs from breaking the cap)
            if buffer_tokens > MAX_TOKENS:
                flush()

        i += 1

    # Flush any remaining content
    if buffer_tokens > 0:
        flush()

    return chunks
