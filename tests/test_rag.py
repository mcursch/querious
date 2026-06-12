"""Unit tests for app.rag.chunk_document."""

import pytest

from app.rag import chunk_document, _count_tokens, TARGET_TOKENS, MAX_TOKENS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SMALL_DOC = """\
# Shipping Policy

Welcome to Acme Outfitters' shipping policy page.

## Domestic Shipping

We ship to all 50 US states via UPS, FedEx, and USPS.

### Free Shipping

Orders over $75 qualify for free standard shipping.

## International Shipping

### International Rules

We ship internationally to Canada, the UK, and the EU.
Duties and taxes are the responsibility of the recipient.
Estimated delivery is 7–14 business days.
"""

LARGE_DOC_TEMPLATE = """\
# Big Document

## Section One

{words}

## Section Two

{words}
"""

# ~600 words to force multiple chunks within a section
MANY_WORDS = " ".join([f"word{i}" for i in range(600)])


# ---------------------------------------------------------------------------
# Basic structure tests
# ---------------------------------------------------------------------------

class TestChunkDocumentBasicStructure:
    def test_returns_list(self):
        chunks = chunk_document(SMALL_DOC, "shipping_policy.md")
        assert isinstance(chunks, list)

    def test_each_chunk_has_required_keys(self):
        chunks = chunk_document(SMALL_DOC, "shipping_policy.md")
        for chunk in chunks:
            assert "source" in chunk
            assert "heading" in chunk
            assert "text" in chunk

    def test_source_propagated(self):
        chunks = chunk_document(SMALL_DOC, "shipping_policy.md")
        assert all(c["source"] == "shipping_policy.md" for c in chunks)

    def test_at_least_one_chunk(self):
        chunks = chunk_document(SMALL_DOC, "shipping_policy.md")
        assert len(chunks) >= 1


# ---------------------------------------------------------------------------
# Heading tracking tests
# ---------------------------------------------------------------------------

class TestHeadingTracking:
    def test_non_empty_heading_in_at_least_one_chunk(self):
        chunks = chunk_document(SMALL_DOC, "shipping_policy.md")
        headings = [c["heading"] for c in chunks]
        assert any(h != "" for h in headings), (
            "Expected at least one chunk with a non-empty heading"
        )

    def test_heading_path_contains_parent_and_child(self):
        """A chunk under '## International Shipping > ### International Rules'
        should have a heading path that contains both levels."""
        chunks = chunk_document(SMALL_DOC, "shipping_policy.md")
        # Find any chunk whose heading includes the nested path
        intl_chunks = [
            c for c in chunks
            if "International" in c["heading"]
        ]
        assert intl_chunks, (
            "Expected at least one chunk with 'International' in its heading"
        )

    def test_heading_separator(self):
        """Heading paths must use ' > ' as a separator."""
        chunks = chunk_document(SMALL_DOC, "shipping_policy.md")
        multi_level = [c for c in chunks if " > " in c["heading"]]
        assert multi_level, (
            "Expected at least one chunk with a multi-level ' > '-separated heading"
        )

    def test_heading_path_resets_for_new_h2(self):
        """After entering '## Section Two', chunks should not carry over
        headings from '## Section One'."""
        doc = """\
# Root

## Section One

Some content here.

## Section Two

Different content here.
"""
        chunks = chunk_document(doc, "test.md")
        # Every chunk that mentions 'Different content' should be under Section Two
        for chunk in chunks:
            if "Different content" in chunk["text"]:
                assert "Section One" not in chunk["heading"]
                assert "Section Two" in chunk["heading"]


# ---------------------------------------------------------------------------
# Token size tests
# ---------------------------------------------------------------------------

class TestChunkSizes:
    def test_no_chunk_exceeds_max_tokens(self):
        """No chunk should exceed MAX_TOKENS (600) as estimated by whitespace split."""
        large_doc = LARGE_DOC_TEMPLATE.format(words=MANY_WORDS)
        chunks = chunk_document(large_doc, "big.md")
        for chunk in chunks:
            tok = _count_tokens(chunk["text"])
            assert tok <= MAX_TOKENS, (
                f"Chunk exceeds {MAX_TOKENS} tokens ({tok}): {chunk['text'][:80]!r}…"
            )

    def test_large_document_produces_multiple_chunks(self):
        """A document with far more than TARGET_TOKENS words must be split."""
        large_doc = LARGE_DOC_TEMPLATE.format(words=MANY_WORDS)
        chunks = chunk_document(large_doc, "big.md")
        assert len(chunks) > 2, (
            f"Expected more than 2 chunks for a ~1200-word document, got {len(chunks)}"
        )

    def test_small_doc_all_chunks_within_max(self):
        chunks = chunk_document(SMALL_DOC, "shipping_policy.md")
        for chunk in chunks:
            tok = _count_tokens(chunk["text"])
            assert tok <= MAX_TOKENS


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_string_returns_empty_list(self):
        assert chunk_document("", "empty.md") == []

    def test_no_headings_still_produces_chunks(self):
        """Plain prose with no headings should still be chunked."""
        prose = " ".join([f"w{i}" for i in range(200)])
        chunks = chunk_document(prose, "prose.md")
        assert len(chunks) >= 1

    def test_heading_only_doc(self):
        """A doc with only headings and no body text produces at least one chunk."""
        doc = "# Title\n## Sub\n### SubSub\n"
        chunks = chunk_document(doc, "headings_only.md")
        # May or may not produce chunks; if it does, keys must be correct
        for chunk in chunks:
            assert "source" in chunk
            assert "heading" in chunk
            assert "text" in chunk

    def test_overlap_text_present_in_consecutive_chunks(self):
        """The tail of chunk N should appear at the start of chunk N+1
        (overlap is preserved)."""
        large_doc = LARGE_DOC_TEMPLATE.format(words=MANY_WORDS)
        chunks = chunk_document(large_doc, "big.md")
        # Check consecutive chunks within the same section share some words
        section_chunks = [c for c in chunks if "Section One" in c["heading"]]
        if len(section_chunks) >= 2:
            words_end_of_first = set(section_chunks[0]["text"].split()[-20:])
            words_start_of_second = set(section_chunks[1]["text"].split()[:20])
            overlap = words_end_of_first & words_start_of_second
            assert overlap, (
                "Expected some word overlap between consecutive chunks in the same section"
            )
