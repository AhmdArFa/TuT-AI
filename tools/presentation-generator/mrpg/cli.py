"""Command line interface for the Multi-Resource Presentation Generator.

The generator runs the two RAG phases from its architecture:

  Phase 1, ingestion and indexing (offline by design):
      python -m mrpg index --resources a.pdf b.docx https://example.org/x \
          --index-dir ./index

  Phase 2, query and generation (online OR offline, same index):
      python -m mrpg generate --topic "Sovereign AI" --load-index ./index \
          --mode offline --out deck.pptx
      python -m mrpg generate --topic "Sovereign AI" --load-index ./index \
          --mode online --out deck.pptx

The classic one shot form still works and runs both phases in one run:

  python -m mrpg --topic "Sovereign AI" --resources a.pdf b.docx \
      --mode auto --out deck.pptx

Generation modes:
  auto       try the selected engine, fall back to extractive on any failure
  offline    local Ollama model only (sovereign, nothing leaves the machine)
  online     OpenAI-compatible API only
  extractive no model at all: outline built from retrieved context only

Embedding modes (for indexing and retrieval):
  auto       follow the engine, with a guaranteed TF-IDF fallback
  offline    Ollama embeddings (default model nomic-embed-text)
  online     OpenAI-compatible embeddings
  tfidf      pure Python TF-IDF, zero network, always available
"""

from __future__ import annotations

import argparse
import sys

from .deck import render_deck
from .ingest import load_resources
from .llm import LLMError, get_provider
from .outline import (
    build_outline_extractive,
    build_outline_from_retrieved,
    build_outline_with_llm,
)
from .rag import (
    TfidfEmbedding,
    VectorStore,
    build_index,
    embedder_for_store,
    format_context,
    retrieve,
)

ENGINE_TO_MODE = {"offline": "offline", "online": "online"}


def _generation_mode(args) -> str:
    if args.mode == "extractive":
        return "extractive"
    if args.mode in ENGINE_TO_MODE:
        return args.mode
    return args.engine  # auto -> chosen engine


def _prepare_retrieval(args, resources):
    """Run phase 1 (or load a saved index) and phase 2 retrieval.

    Returns (retrieved_chunks, resources_for_titles). When a saved index
    is loaded, lightweight resource stubs are rebuilt from the index so
    slide titles and citations still resolve.
    """
    if getattr(args, "load_index", None):
        store, state = VectorStore.load(args.load_index)
        provider = embedder_for_store(
            store, state, generation_mode=_generation_mode(args)
        )
        retrieved = retrieve(store, provider, args.topic, top_k=args.top_k)
        print(
            f"[mrpg] Loaded index: {len(store.chunks)} chunks "
            f"(embeddings: {store.embedding_name}/{store.embedding_model})"
        )
        stubs = []
        seen = set()
        for chunk in store.chunks:
            if chunk.origin_label not in seen:
                seen.add(chunk.origin_label)
                stubs.append(
                    type(
                        "ResourceStub",
                        (),
                        {
                            "origin_label": chunk.origin_label,
                            "title": chunk.doc_title or chunk.origin_label,
                            "kind": chunk.kind,
                            "source": chunk.source,
                        },
                    )()
                )
        return retrieved, stubs

    gen_mode = _generation_mode(args)
    store, provider, chunks = build_index(
        resources,
        embeddings=args.embeddings,
        generation_mode=gen_mode,
        chunk_size=args.chunk_size,
        overlap=args.chunk_overlap,
    )
    print(
        f"[mrpg] Indexed {len(chunks)} chunks from {len(resources)} resource(s) "
        f"(embeddings: {store.embedding_name}/{store.embedding_model})"
    )
    if getattr(args, "index_dir", None):
        state = provider.state() if isinstance(provider, TfidfEmbedding) else {}
        path = store.save(args.index_dir, embedder_state=state)
        print(f"[mrpg] Index saved: {path}")
    retrieved = retrieve(store, provider, args.topic, top_k=args.top_k)
    return retrieved, resources


def _build_outline(args, resources):
    retrieved, title_resources = [], resources
    if not args.no_rag:
        retrieved, title_resources = _prepare_retrieval(args, resources)
        if retrieved:
            top = ", ".join(
                f"{r.chunk.origin_label} ({r.score:.2f})" for r in retrieved[:3]
            )
            print(f"[mrpg] Retrieved {len(retrieved)} chunks. Top: {top}")

    if args.mode == "extractive":
        if retrieved:
            return (
                build_outline_from_retrieved(
                    retrieved, title_resources, args.topic, slides=args.slides
                ),
                "extractive (RAG)",
            )
        return build_outline_extractive(
            resources, args.topic, slides=args.slides
        ), "extractive"

    provider = get_provider(
        ENGINE_TO_MODE[args.mode if args.mode != "auto" else args.engine],
        model=args.model,
    )
    context = format_context(retrieved) if retrieved else None
    try:
        outline = build_outline_with_llm(
            provider,
            resources,
            args.topic,
            slides=args.slides,
            audience=args.audience,
            language=args.language,
            context=context,
        )
        return outline, provider.name + (" (RAG)" if context else "")
    except (LLMError, ValueError) as exc:
        if args.mode != "auto":
            raise
        print(
            f"[mrpg] Engine failed ({exc}); falling back to extractive mode.",
            file=sys.stderr,
        )
        if retrieved:
            return (
                build_outline_from_retrieved(
                    retrieved, title_resources, args.topic, slides=args.slides
                ),
                "extractive (RAG)",
            )
        return build_outline_extractive(
            resources, args.topic, slides=args.slides
        ), "extractive"


def _add_common(parser, resources_required: bool = True):
    parser.add_argument(
        "--topic", required=True, help="Presentation topic / title seed."
    )
    parser.add_argument(
        "--resources",
        nargs="+",
        required=resources_required,
        help="Local files (PDF, DOCX, PPTX, TXT, MD) and/or web URLs.",
    )
    parser.add_argument("--out", default="presentation.pptx", help="Output .pptx path.")
    parser.add_argument(
        "--slides", type=int, default=8, help="Target number of content slides."
    )
    parser.add_argument(
        "--mode",
        choices=["auto", "offline", "online", "extractive"],
        default="auto",
        help="Generation mode (default: auto).",
    )
    parser.add_argument(
        "--engine",
        choices=["offline", "online"],
        default="offline",
        help="Engine used when --mode auto (default: offline via Ollama).",
    )
    parser.add_argument(
        "--model", default=None, help="Override the model name for the engine."
    )
    parser.add_argument("--audience", default="general professional audience")
    parser.add_argument("--language", default="the language of the sources")
    parser.add_argument(
        "--embeddings",
        choices=["auto", "offline", "online", "tfidf"],
        default="auto",
        help="Embedding model family for indexing and retrieval (default: auto).",
    )
    parser.add_argument(
        "--top-k", type=int, default=24, help="Chunks retrieved for the topic."
    )
    parser.add_argument(
        "--chunk-size", type=int, default=900, help="Chunk size in characters."
    )
    parser.add_argument(
        "--chunk-overlap", type=int, default=150, help="Chunk overlap in characters."
    )
    parser.add_argument(
        "--index-dir",
        default=None,
        help="Save the built vector index here for reuse (phase 1 output).",
    )
    parser.add_argument(
        "--load-index",
        default=None,
        help="Load a saved vector index instead of ingesting resources (phase 2).",
    )
    parser.add_argument(
        "--no-rag",
        action="store_true",
        help="Legacy path: ranked digest instead of chunk, embed, retrieve.",
    )


def _run_index(argv) -> int:
    parser = argparse.ArgumentParser(
        prog="mrpg index",
        description="Phase 1: ingest and index resources (offline by design).",
    )
    parser.add_argument("--resources", nargs="+", required=True)
    parser.add_argument(
        "--index-dir", required=True, help="Where to save the vector index."
    )
    parser.add_argument(
        "--embeddings",
        choices=["auto", "offline", "online", "tfidf"],
        default="auto",
    )
    parser.add_argument("--chunk-size", type=int, default=900)
    parser.add_argument("--chunk-overlap", type=int, default=150)
    args = parser.parse_args(argv)

    resources = load_resources(args.resources)
    store, provider, chunks = build_index(
        resources,
        embeddings=args.embeddings,
        generation_mode="offline",
        chunk_size=args.chunk_size,
        overlap=args.chunk_overlap,
    )
    state = provider.state() if isinstance(provider, TfidfEmbedding) else {}
    path = store.save(args.index_dir, embedder_state=state)
    print(f"[mrpg] Ingested {len(resources)} resource(s), indexed {len(chunks)} chunks")
    print(f"[mrpg] Embeddings: {store.embedding_name}/{store.embedding_model}")
    print(f"[mrpg] Index saved: {path}")
    return 0


def _run_generate(argv) -> int:
    parser = argparse.ArgumentParser(
        prog="mrpg generate",
        description="Phase 2 (or one shot): generate a presentation, online or offline.",
    )
    _add_common(parser, resources_required=False)
    args = parser.parse_args(argv)
    if not args.resources and not args.load_index:
        parser.error("generate needs --resources and/or --load-index")

    resources = load_resources(args.resources) if args.resources else []
    if resources:
        print(f"[mrpg] Ingested {len(resources)} resource(s):")
        for resource in resources:
            print(
                f"  - [{resource.kind}] {resource.origin_label} ({len(resource.text)} chars)"
            )

    outline, engine_used = _build_outline(args, resources)
    output = render_deck(outline, args.out)
    print(f"[mrpg] Engine: {engine_used}")
    print(
        f"[mrpg] Deck written: {output} ({len(outline.slides)} content slides + title + closing)"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "index":
        return _run_index(argv[1:])
    if argv and argv[0] == "generate":
        return _run_generate(argv[1:])
    return _run_generate(argv)


if __name__ == "__main__":
    raise SystemExit(main())
