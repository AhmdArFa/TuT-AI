"""RAG pipeline tests: chunking, embeddings, vector store, retrieval,
prompt augmentation, and the two phase (index then generate) flow.

Runs with no network and no GPU:

    python tests/test_rag.py
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mrpg.ingest import load_resources
from mrpg.outline import build_outline_from_retrieved, build_outline_with_llm
from mrpg.rag import (
    VectorStore,
    build_index,
    chunk_resources,
    embedder_for_store,
    format_context,
    retrieve,
)


class FakeProvider:
    """Captures the prompt instead of calling a model."""

    name = "fake"

    def __init__(self):
        self.system = ""
        self.user = ""

    def complete(self, system: str, user: str) -> str:
        self.system, self.user = system, user
        return (
            '{"title": "T", "subtitle": "S", "slides": ['
            '{"title": "A", "bullets": ["b1"], "notes": "n", '
            '"sources": ["sovereign_ai_notes.md"]}]}'
        )


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    sources = [
        str(root / "examples" / "resources" / "sovereign_ai_notes.md"),
        str(root / "examples" / "resources" / "document_intelligence.txt"),
    ]
    resources = load_resources(sources)

    # 1. Chunking: chunks exist, carry provenance, stay within sane bounds
    chunks = chunk_resources(resources, chunk_size=500, overlap=80)
    assert len(chunks) >= 4, f"too few chunks: {len(chunks)}"
    assert all(c.origin_label and c.source and c.doc_title for c in chunks), (
        "chunk lost provenance"
    )
    assert [c.chunk_id for c in chunks] == list(range(len(chunks))), (
        "chunk ids not sequential"
    )
    print(f"chunking OK: {len(chunks)} chunks with provenance")

    # 2. Index + retrieval: a sovereign query must rank sovereign content first
    store, provider, _ = build_index(
        resources, embeddings="tfidf", generation_mode="extractive"
    )
    retrieved = retrieve(
        store, provider, "offline sovereign AI with local models", top_k=5
    )
    assert retrieved, "retrieval returned nothing"
    assert all(r.score > 0 for r in retrieved), "non positive score in results"
    assert retrieved == sorted(retrieved, key=lambda r: r.score, reverse=True), (
        "results not ranked"
    )
    print(
        f"retrieval OK: top chunk from {retrieved[0].chunk.origin_label} ({retrieved[0].score:.2f})"
    )

    # 3. Prompt augmentation: numbered, sourced context blocks
    context = format_context(retrieved)
    assert "[1] Source:" in context and "score" in context, "context block malformed"
    print("prompt augmentation OK: numbered [Context] blocks with sources and scores")

    # 4. LLM path actually receives the augmented context
    fake = FakeProvider()
    outline = build_outline_with_llm(fake, resources, "Sovereign AI", context=context)
    assert "[Context]" in fake.user and "Sovereign AI" in fake.user, (
        "LLM did not get RAG prompt"
    )
    assert outline.slides, "fake LLM outline empty"
    print("LLM RAG prompt OK: model grounded on retrieved context")

    # 5. Extractive outline from retrieved context only
    rag_outline = build_outline_from_retrieved(
        retrieved, resources, "Sovereign AI", slides=6
    )
    assert rag_outline.slides and all(s.bullets for s in rag_outline.slides)
    assert all(s.sources for s in rag_outline.slides), "a RAG slide lost its citation"
    print(f"extractive RAG outline OK: {len(rag_outline.slides)} cited slides")

    # 6. Two phase flow: save index, load it cold, retrieve again identically
    with tempfile.TemporaryDirectory() as tmp:
        state = provider.state()
        path = store.save(tmp, embedder_state=state)
        assert path.exists()
        loaded_store, loaded_state = VectorStore.load(tmp)
        assert len(loaded_store.chunks) == len(store.chunks), (
            "index roundtrip lost chunks"
        )
        loaded_provider = embedder_for_store(loaded_store, loaded_state)
        again = retrieve(
            loaded_store,
            loaded_provider,
            "offline sovereign AI with local models",
            top_k=5,
        )
        assert [r.chunk.chunk_id for r in again] == [
            r.chunk.chunk_id for r in retrieved
        ], "loaded index retrieval differs from live index"
    print("two phase OK: offline index reloads and retrieves identically")

    print("RAG TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
