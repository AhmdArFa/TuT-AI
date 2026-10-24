# Multi-Resource Presentation Generator (MRPG)

Build a polished PowerPoint presentation from **many resources at once**: local
files and web pages, online and offline. MRPG is a full **Retrieval Augmented
Generation (RAG)** pipeline: it ingests every source, chunks and embeds it into
a vector index, retrieves the chunks that actually match your topic, and only
then asks a model (or the built in extractive engine) to build the deck, so
every slide is grounded in retrieved context and cites its sources.

It was built for the **TuT AI** sovereign platform (DEPI PPTX project): the
indexing phase runs offline by design, generation runs offline on a local
Ollama model or online through any OpenAI-compatible API, and the extractive
fallback guarantees a deck even with no model, no GPU, and no network at all.

## The RAG architecture

The pipeline follows the classic two phase RAG design:

**Phase 1, Document Ingestion and Indexing (offline)**

```
Source Documents (PDF, DOCX, PPTX, TXT, MD, HTML pages, APIs)
  -> Document Loader / Extractor      clean text, origin preserved
  -> Text Splitter / Chunker          sentence aware chunks, with overlap
  -> Embedding Model                  offline, online, or TF-IDF
  -> Vector Database                  cosine index, saved to disk as JSON
```

**Phase 2, Query Processing and Response Generation (online or offline)**

```
Topic / Query
  -> Embedding Model (same model as indexing)
  -> Vector Search / Retrieval        top-k chunks, with scores and metadata
  -> Prompt Augmentation              retrieved context, numbered [1], [2]...
  -> Large Language Model             Ollama (offline) or OpenAI-compatible (online)
     or the extractive engine         when no model is available
  -> Response Generation              a native, editable .pptx deck
```

Because the index is saved to disk, phase 1 runs **once, offline**, and phase 2
reuses it later, online or offline, without re-ingesting or re-embedding a
single document.

## Features

- **Multi-resource ingestion**: PDF, DOCX, PPTX, TXT, and Markdown files, plus
  web pages by URL, mixed freely in one run.
- **Real retrieval, not just ranking**: sentence aware chunking with overlap,
  pluggable embeddings, and a cosine similarity vector store.
- **Pluggable embeddings**
  - `offline`: Ollama embeddings (default model `nomic-embed-text`, the TuT AI
    sovereign choice). Nothing leaves the machine.
  - `online`: any OpenAI-compatible embeddings endpoint.
  - `tfidf`: pure Python TF-IDF embedder. Zero network, zero GPU, always works.
  - `auto`: follows the generation engine, falls back to TF-IDF on any failure.
- **Three generation modes**
  - `offline`: local LLM through [Ollama](https://ollama.com) (sovereign mode).
  - `online`: any OpenAI-compatible chat API.
  - `extractive`: no model required; the outline is built from the retrieved
    chunks only, with citations on every slide.
  - `auto` (default): tries the chosen engine, falls back to extractive on
    any failure, so a deck is always produced.
- **Citations by construction**: slides record the retrieved sources they were
  built from, and the closing slide lists every resource used.
- **Native editable output**: real PowerPoint files (16:9, themed in the TuT
  navy and gold identity), with speaker notes, not images of slides.

## Installation

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

For offline mode, install Ollama and pull the models, for example:

```bash
ollama pull gemma4:e4b          # chat model used by TuT AI
ollama pull nomic-embed-text    # embedding model
```

## Usage

### Two phase flow (recommended)

```bash
# Phase 1: ingest and index, offline, once
python -m mrpg index \
  --resources notes.md report.pdf https://example.org/article \
  --index-dir ./index --embeddings auto

# Phase 2a: generate OFFLINE from the saved index (sovereign)
python -m mrpg generate --topic "Sovereign Document Intelligence" \
  --load-index ./index --mode offline --out deck_offline.pptx

# Phase 2b: or generate ONLINE from the very same index
MRPG_ONLINE_API_KEY=sk-... python -m mrpg generate \
  --topic "Sovereign Document Intelligence" \
  --load-index ./index --mode online --out deck_online.pptx

# Phase 2c: or with no model at all (extractive, from retrieved context)
python -m mrpg generate --topic "Sovereign Document Intelligence" \
  --load-index ./index --mode extractive --out deck_extractive.pptx
```

### One shot flow

```bash
# Both phases in a single run, saving the index for reuse
python -m mrpg --topic "Quarterly Review" \
  --resources q3_report.docx previous_deck.pptx \
  --mode auto --engine offline --index-dir ./index --out review.pptx

# Fully offline, no model needed anywhere in the pipeline
python -m mrpg --topic "Sovereign Document Intelligence" \
  --resources notes.md report.pdf \
  --mode extractive --embeddings tfidf --out deck.pptx
```

### Options

| Flag | Default | Meaning |
| --- | --- | --- |
| `--topic` | required | Presentation topic, used as the retrieval query |
| `--resources` | required (unless `--load-index`) | File paths and/or URLs |
| `--out` | `presentation.pptx` | Output path |
| `--slides` | `8` | Target number of content slides |
| `--mode` | `auto` | `auto`, `offline`, `online`, or `extractive` |
| `--engine` | `offline` | Engine used by `auto`: `offline` or `online` |
| `--model` | env / provider default | Chat model name override |
| `--embeddings` | `auto` | `auto`, `offline`, `online`, or `tfidf` |
| `--top-k` | `24` | Chunks retrieved for the topic |
| `--chunk-size` | `900` | Chunk size in characters |
| `--chunk-overlap` | `150` | Chunk overlap in characters |
| `--index-dir` | none | Save the built vector index here |
| `--load-index` | none | Generate from a saved index (phase 2 only) |
| `--no-rag` | off | Legacy ranked digest path, without retrieval |
| `--audience` | general professional | Audience hint for the LLM outline |
| `--language` | language of the sources | Output language hint |

### Configuration (environment variables)

| Variable | Used by | Default |
| --- | --- | --- |
| `OLLAMA_HOST` | offline chat + embeddings | `http://localhost:11434` |
| `MRPG_OLLAMA_MODEL` | offline chat | `qwen3:8b` |
| `MRPG_EMBED_MODEL` | offline embeddings | `nomic-embed-text` |
| `MRPG_ONLINE_BASE_URL` | online chat + embeddings | `https://api.openai.com/v1` |
| `MRPG_ONLINE_MODEL` | online chat | `gpt-4o-mini` |
| `MRPG_EMBED_ONLINE_MODEL` | online embeddings | `text-embedding-3-small` |
| `MRPG_ONLINE_API_KEY` | online modes | none (required for online mode) |

## Project structure

```
mrpg/
  ingest.py    resource extraction: files + web, origins preserved
  rag.py       chunking, embeddings, vector store, retrieval, prompt context
  llm.py       chat providers (Ollama, OpenAI-compatible) + sentence ranking
  outline.py   outline building: LLM path on retrieved context + extractive paths
  deck.py      themed PPTX renderer (python-pptx)
  cli.py       command line interface (index / generate / one shot)
examples/
  resources/   two sample resources used by the demo and the tests
tests/
  smoke_test.py  end-to-end legacy test, no network or GPU required
  test_rag.py    RAG pipeline tests: chunking, retrieval, two phase flow
```

## Testing

```bash
python tests/smoke_test.py
python tests/test_rag.py
```

Both suites run anywhere: no network, no GPU, no model downloads.

## Roadmap

- Image extraction from source decks and documents, placed on slides.
- Optional web research step: topic search that gathers URLs automatically.
- Template packs (corporate, academic, pitch) selectable by flag.
- Arabic RTL slide layout support.
- BGE reranker stage between retrieval and prompt augmentation.

## License

MIT
