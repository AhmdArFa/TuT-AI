"""Retrieval Augmented Generation pipeline for MRPG.

This module implements the classic two phase RAG architecture that the
generator is built on:

Phase 1, ingestion and indexing (designed to run OFFLINE):
    Source Documents (PDF, DOCX, PPTX, TXT, MD, HTML, APIs)
        -> Document Loader / Extractor        (mrpg.ingest)
        -> Text Splitter / Chunker            (chunk_resources)
        -> Embedding Model                    (offline, online or TF-IDF)
        -> Vector Store                       (in memory, JSON persistable)

Phase 2, query processing and response generation (ONLINE or OFFLINE):
    Topic / Query
        -> Query embedding (same model as indexing)
        -> Vector Search / Retrieval (cosine similarity, top-k chunks
           with source metadata and scores)
        -> Prompt Augmentation (retrieved context, numbered [1], [2]...)
        -> LLM (Ollama offline, OpenAI-compatible online, or the
           extractive engine when no model is available)
        -> Presentation outline grounded in the retrieved context

Embeddings are pluggable, mirroring the TuT AI sovereign design:

* ``offline``: Ollama embeddings on the local machine, default model
  ``nomic-embed-text``. Nothing leaves the device.
* ``online``: any OpenAI-compatible embeddings endpoint.
* ``tfidf``: a pure Python TF-IDF embedder. Zero network, zero GPU,
  always available, and the guaranteed fallback in ``auto`` mode.

The vector store persists to a JSON index directory so phase 1 can run
once, offline, and phase 2 can reuse the index later, online or offline,
without re-ingesting or re-embedding the sources.
"""

from __future__ import annotations

import json
import math
import os
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import requests

from .ingest import Resource
from .llm import LLMError, _tokens, split_sentences

# ---------------------------------------------------------------------------
# Chunking (Text Splitter)
# ---------------------------------------------------------------------------


@dataclass
class Chunk:
    """One retrievable text chunk, with full source provenance."""

    chunk_id: int
    text: str
    source: str  # file path or URL
    origin_label: str  # short label used in slide citations
    kind: str  # pdf | docx | pptx | text | web
    block_index: int = 0  # which extracted block (page / section) it came from
    doc_title: str = ""  # title of the document this chunk belongs to

    def metadata(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "source": self.source,
            "origin_label": self.origin_label,
            "kind": self.kind,
            "block_index": self.block_index,
            "doc_title": self.doc_title,
        }


def _split_block(block: str, chunk_size: int, overlap: int) -> list[str]:
    """Split one text block into sentence aware chunks with overlap."""
    sentences = split_sentences(block)
    if not sentences:
        text = block.strip()
        return [text] if text else []
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for sentence in sentences:
        if current and current_len + len(sentence) > chunk_size:
            chunks.append(" ".join(current))
            # carry the tail sentences forward as the overlap window
            tail: list[str] = []
            tail_len = 0
            for prev in reversed(current):
                if tail_len + len(prev) > overlap and tail:
                    break
                tail.insert(0, prev)
                tail_len += len(prev)
            current, current_len = tail, tail_len
        current.append(sentence)
        current_len += len(sentence)
    if current:
        chunks.append(" ".join(current))
    # very long single sentences fall back to hard character windows
    final: list[str] = []
    for chunk in chunks:
        if len(chunk) <= chunk_size * 1.6:
            final.append(chunk)
            continue
        step = max(1, chunk_size - overlap)
        for start in range(0, len(chunk), step):
            final.append(chunk[start : start + chunk_size])
    return [c for c in final if c.strip()]


def chunk_resource(
    resource: Resource,
    start_id: int = 0,
    chunk_size: int = 900,
    overlap: int = 150,
) -> list[Chunk]:
    """Chunk one ingested resource, preserving its origin on every chunk."""
    chunks: list[Chunk] = []
    next_id = start_id
    for block_index, block in enumerate(resource.blocks):
        for piece in _split_block(block, chunk_size, overlap):
            chunks.append(
                Chunk(
                    chunk_id=next_id,
                    text=piece,
                    source=resource.source,
                    origin_label=resource.origin_label,
                    kind=resource.kind,
                    block_index=block_index,
                    doc_title=resource.title or resource.origin_label,
                )
            )
            next_id += 1
    return chunks


def chunk_resources(
    resources: list[Resource],
    chunk_size: int = 900,
    overlap: int = 150,
) -> list[Chunk]:
    """Chunk many resources into one flat, id ordered chunk list."""
    all_chunks: list[Chunk] = []
    for resource in resources:
        all_chunks.extend(
            chunk_resource(
                resource,
                start_id=len(all_chunks),
                chunk_size=chunk_size,
                overlap=overlap,
            )
        )
    return all_chunks


# ---------------------------------------------------------------------------
# Embedding models
# ---------------------------------------------------------------------------

Vector = dict[int, float]  # sparse vector: dimension -> weight


def _normalize(vec: Vector) -> Vector:
    norm = math.sqrt(sum(v * v for v in vec.values()))
    if norm == 0:
        return vec
    return {k: v / norm for k, v in vec.items()}


def _dense_to_sparse(values: list[float]) -> Vector:
    return {i: float(v) for i, v in enumerate(values) if v != 0.0}


def cosine(a: Vector, b: Vector) -> float:
    """Cosine similarity between two sparse (already normalized) vectors."""
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b.get(k, 0.0) for k, v in a.items())


class TfidfEmbedding:
    """Pure Python TF-IDF embedder. Always available, fully offline."""

    name = "tfidf"

    def __init__(self):
        self.vocab: dict[str, int] = {}
        self.idf: dict[str, float] = {}

    def fit(self, texts: list[str]) -> "TfidfEmbedding":
        docs = [_tokens(t) for t in texts]
        doc_freq: Counter = Counter()
        for doc in docs:
            doc_freq.update(set(doc))
        self.vocab = {term: i for i, term in enumerate(sorted(doc_freq))}
        total = max(1, len(docs))
        self.idf = {
            term: math.log((total + 1) / (count + 1)) + 1.0
            for term, count in doc_freq.items()
        }
        return self

    def embed(self, texts: list[str]) -> list[Vector]:
        if not self.vocab:
            raise LLMError("TF-IDF embedder used before fit().")
        vectors = []
        for text in texts:
            freq = Counter(t for t in _tokens(text) if t in self.vocab)
            vec = {
                self.vocab[term]: count * self.idf[term] for term, count in freq.items()
            }
            vectors.append(_normalize(vec))
        return vectors

    def state(self) -> dict:
        return {"vocab": self.vocab, "idf": self.idf}

    def load_state(self, state: dict) -> "TfidfEmbedding":
        self.vocab = {str(k): int(v) for k, v in state.get("vocab", {}).items()}
        self.idf = {str(k): float(v) for k, v in state.get("idf", {}).items()}
        return self


class OllamaEmbedding:
    """Local embeddings through Ollama (sovereign, offline)."""

    name = "ollama-embeddings"

    def __init__(
        self, model: str | None = None, host: str | None = None, timeout: int = 120
    ):
        self.model = model or os.environ.get("MRPG_EMBED_MODEL", "nomic-embed-text")
        self.host = (
            host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        ).rstrip("/")
        self.timeout = timeout

    def available(self) -> bool:
        try:
            response = requests.get(f"{self.host}/api/tags", timeout=2)
            return response.status_code == 200
        except Exception:
            return False

    def embed(self, texts: list[str]) -> list[Vector]:
        try:
            response = requests.post(
                f"{self.host}/api/embed",
                json={"model": self.model, "input": texts},
                timeout=self.timeout,
            )
            response.raise_for_status()
            embeddings = response.json()["embeddings"]
            return [_normalize(_dense_to_sparse(e)) for e in embeddings]
        except Exception:
            pass  # fall through to the legacy per text endpoint
        vectors = []
        for text in texts:
            try:
                response = requests.post(
                    f"{self.host}/api/embeddings",
                    json={"model": self.model, "prompt": text},
                    timeout=self.timeout,
                )
                response.raise_for_status()
                vectors.append(
                    _normalize(_dense_to_sparse(response.json()["embedding"]))
                )
            except Exception as exc:
                raise LLMError(f"Ollama embedding failed: {exc}") from exc
        return vectors


class OpenAIEmbedding:
    """Embeddings from any OpenAI-compatible endpoint (online)."""

    name = "openai-embeddings"

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: int = 120,
    ):
        self.model = model or os.environ.get(
            "MRPG_EMBED_ONLINE_MODEL", "text-embedding-3-small"
        )
        self.base_url = (
            base_url
            or os.environ.get("MRPG_ONLINE_BASE_URL", "https://api.openai.com/v1")
        ).rstrip("/")
        self.api_key = api_key or os.environ.get("MRPG_ONLINE_API_KEY", "")
        self.timeout = timeout

    def embed(self, texts: list[str]) -> list[Vector]:
        if not self.api_key:
            raise LLMError("MRPG_ONLINE_API_KEY is not set for online embeddings.")
        try:
            response = requests.post(
                f"{self.base_url}/embeddings",
                json={"model": self.model, "input": texts},
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = sorted(response.json()["data"], key=lambda d: d["index"])
            return [_normalize(_dense_to_sparse(d["embedding"])) for d in data]
        except Exception as exc:
            raise LLMError(f"Online embedding failed: {exc}") from exc


def resolve_embedding_provider(requested: str, generation_mode: str):
    """Resolve the embedding provider, with a guaranteed TF-IDF fallback.

    ``requested`` is one of: auto, offline, online, tfidf.
    ``generation_mode`` is the outline engine mode: offline, online or
    extractive. In auto mode the embedder follows the engine: online
    engines prefer online embeddings (when a key exists), offline engines
    prefer local Ollama embeddings (when the server answers), and every
    failure falls back to TF-IDF so indexing always succeeds.
    """
    if requested == "tfidf":
        return TfidfEmbedding()
    if requested == "offline":
        provider = OllamaEmbedding()
        if not provider.available():
            raise LLMError("Ollama is not reachable for offline embeddings.")
        return provider
    if requested == "online":
        return OpenAIEmbedding()
    # auto
    if generation_mode == "online" and os.environ.get("MRPG_ONLINE_API_KEY"):
        return OpenAIEmbedding()
    if generation_mode in {"offline", "auto"}:
        provider = OllamaEmbedding()
        if provider.available():
            return provider
    return TfidfEmbedding()


# ---------------------------------------------------------------------------
# Vector store
# ---------------------------------------------------------------------------


@dataclass
class RetrievedChunk:
    chunk: Chunk
    score: float


@dataclass
class VectorStore:
    """In memory cosine similarity store, persistable as a JSON index."""

    chunks: list[Chunk] = field(default_factory=list)
    vectors: list[Vector] = field(default_factory=list)
    embedding_name: str = ""
    embedding_model: str = ""

    def add(self, chunks: list[Chunk], vectors: list[Vector]) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("chunks and vectors must have the same length")
        self.chunks.extend(chunks)
        self.vectors.extend(vectors)

    def search(self, query_vector: Vector, top_k: int = 24) -> list[RetrievedChunk]:
        scored = [
            RetrievedChunk(chunk=chunk, score=cosine(query_vector, vector))
            for chunk, vector in zip(self.chunks, self.vectors)
        ]
        scored.sort(key=lambda r: r.score, reverse=True)
        return [r for r in scored[:top_k] if r.score > 0]

    def save(self, index_dir: str | Path, embedder_state: dict | None = None) -> Path:
        directory = Path(index_dir)
        directory.mkdir(parents=True, exist_ok=True)
        payload = {
            "format": "mrpg-index-v1",
            "embedding_name": self.embedding_name,
            "embedding_model": self.embedding_model,
            "embedder_state": embedder_state or {},
            "chunks": [
                {
                    **chunk.metadata(),
                    "text": chunk.text,
                    "vector": {str(k): v for k, v in vector.items()},
                }
                for chunk, vector in zip(self.chunks, self.vectors)
            ],
        }
        path = directory / "index.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    @classmethod
    def load(cls, index_dir: str | Path) -> tuple["VectorStore", dict]:
        path = Path(index_dir) / "index.json"
        if not path.exists():
            raise FileNotFoundError(f"No MRPG index found at {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        store = cls(
            embedding_name=payload.get("embedding_name", ""),
            embedding_model=payload.get("embedding_model", ""),
        )
        for raw in payload.get("chunks", []):
            chunk = Chunk(
                chunk_id=int(raw["chunk_id"]),
                text=raw["text"],
                source=raw["source"],
                origin_label=raw["origin_label"],
                kind=raw["kind"],
                block_index=int(raw.get("block_index", 0)),
                doc_title=raw.get("doc_title", ""),
            )
            vector = {int(k): float(v) for k, v in raw.get("vector", {}).items()}
            store.add([chunk], [vector])
        return store, payload.get("embedder_state", {})


# ---------------------------------------------------------------------------
# Pipeline: index (phase 1) and retrieve (phase 2)
# ---------------------------------------------------------------------------


def build_index(
    resources: list[Resource],
    embeddings: str = "auto",
    generation_mode: str = "offline",
    chunk_size: int = 900,
    overlap: int = 150,
) -> tuple[VectorStore, object, list[Chunk]]:
    """Phase 1: chunk, embed and index all resources."""
    chunks = chunk_resources(resources, chunk_size=chunk_size, overlap=overlap)
    if not chunks:
        raise ValueError("The provided resources produced no chunks to index.")
    provider = resolve_embedding_provider(embeddings, generation_mode)
    if isinstance(provider, TfidfEmbedding):
        provider.fit([c.text for c in chunks])
    vectors = provider.embed([c.text for c in chunks])
    store = VectorStore(
        embedding_name=getattr(provider, "name", "unknown"),
        embedding_model=getattr(provider, "model", "tfidf"),
    )
    store.add(chunks, vectors)
    return store, provider, chunks


def embedder_for_store(
    store: VectorStore, embedder_state: dict, generation_mode: str = "offline"
):
    """Rebuild a query embedder compatible with a loaded index."""
    if store.embedding_name == TfidfEmbedding.name:
        return TfidfEmbedding().load_state(embedder_state)
    if store.embedding_name == OllamaEmbedding.name:
        return OllamaEmbedding(model=store.embedding_model or None)
    if store.embedding_name == OpenAIEmbedding.name:
        return OpenAIEmbedding(model=store.embedding_model or None)
    # unknown index origin: safest query path is a TF-IDF refit is impossible,
    # so fall back to the provider family named by the index, else TF-IDF.
    return resolve_embedding_provider("auto", generation_mode)


def retrieve(
    store: VectorStore,
    provider,
    query: str,
    top_k: int = 24,
) -> list[RetrievedChunk]:
    """Phase 2 retrieval: embed the query, cosine search the store."""
    query_vector = provider.embed([query])[0]
    return store.search(query_vector, top_k=top_k)


def format_context(retrieved: list[RetrievedChunk]) -> str:
    """Prompt augmentation block: retrieved context, numbered and sourced.

    This is the exact [Context] a model is instructed to ground on:
    every block carries its number, its source label and its score.
    """
    blocks = []
    for index, item in enumerate(retrieved, start=1):
        chunk = item.chunk
        blocks.append(
            f"[{index}] Source: {chunk.origin_label} ({chunk.kind}), score {item.score:.3f}\n{chunk.text}"
        )
    return "\n\n".join(blocks)
