"""Outline building: turn ingested resources into a slide outline.

Two paths produce the same :class:`Outline` structure:

* LLM path (offline Ollama or online API): the model reads the retrieved,
  numbered RAG context for the topic (or a ranked digest on the legacy
  path) and returns a structured JSON outline.
* Extractive path (no model): built from the retrieved chunks only, or
  from per resource ranked sentences on the legacy path. Always works,
  fully offline.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .ingest import Resource
from .llm import extract_json, rank_sentences, split_sentences

MAX_BULLET_CHARS = 180
MAX_BULLETS_PER_SLIDE = 5


@dataclass
class Slide:
    title: str
    bullets: list[str] = field(default_factory=list)
    notes: str = ""
    sources: list[str] = field(default_factory=list)
    kind: str = "content"  # title | section | content | closing


@dataclass
class Outline:
    title: str
    subtitle: str = ""
    slides: list[Slide] = field(default_factory=list)


def _digest(resources: list[Resource], topic: str, char_budget: int = 14000) -> str:
    """A ranked, size-bounded digest of all resources for the LLM prompt."""
    parts = []
    used = 0
    for resource in resources:
        sentences = split_sentences(resource.text)
        ranked = rank_sentences(sentences, topic=topic, top_k=30)
        body = "\n".join(ranked)
        header = f"### SOURCE [{resource.origin_label}] ({resource.kind})"
        chunk = f"{header}\n{body}"
        if used + len(chunk) > char_budget:
            chunk = chunk[: char_budget - used]
        if chunk.strip():
            parts.append(chunk)
            used += len(chunk)
        if used >= char_budget:
            break
    return "\n\n".join(parts)


_SYSTEM_PROMPT = """You are a presentation architect. You build clear, faithful slide outlines strictly from the provided sources. Never invent facts that are not in the sources. Respond with ONE JSON object only, no commentary."""

_USER_TEMPLATE = """Build a presentation outline on the topic: "{topic}"

Target slide count for content slides: about {slides}.
Audience: {audience}
Language of the output: {language}

SOURCES:
{digest}

Return JSON with exactly this shape:
{{
  "title": "presentation title",
  "subtitle": "one-line subtitle",
  "slides": [
    {{
      "title": "slide title",
      "bullets": ["short bullet, max 20 words", "..."],
      "notes": "1-2 sentence speaker note",
      "sources": ["origin label copied from a SOURCE header"]
    }}
  ]
}}

Rules: at most {max_bullets} bullets per slide, group related points into sections logically, keep every claim traceable to the sources, and end with a slide of key takeaways or conclusions."""


def _sanitize_outline(data: dict, fallback_title: str) -> Outline:
    slides = []
    for raw in data.get("slides", []):
        if not isinstance(raw, dict):
            continue
        bullets = []
        for bullet in raw.get("bullets", []):
            text = re.sub(r"\s+", " ", str(bullet)).strip(" -•\t")
            if text:
                bullets.append(text[:MAX_BULLET_CHARS])
        if not bullets:
            continue
        slides.append(
            Slide(
                title=str(raw.get("title", "Untitled")).strip() or "Untitled",
                bullets=bullets[:MAX_BULLETS_PER_SLIDE],
                notes=str(raw.get("notes", "")).strip(),
                sources=[str(s) for s in raw.get("sources", []) if str(s).strip()],
            )
        )
    return Outline(
        title=str(data.get("title", "")).strip() or fallback_title,
        subtitle=str(data.get("subtitle", "")).strip(),
        slides=slides,
    )


_RAG_USER_TEMPLATE = """Build a presentation outline on the topic: "{topic}"

Target slide count for content slides: about {slides}.
Audience: {audience}
Language of the output: {language}

Answer based on the retrieved context below only. The context was
retrieved from the user's own resources by vector search for this topic,
so it is the most relevant material available. Every claim in the
outline must be traceable to a context block.

[Context]
{context}
[End of context]

Question / Topic: {topic}

Return JSON with exactly this shape:
{{
  "title": "presentation title",
  "subtitle": "one-line subtitle",
  "slides": [
    {{
      "title": "slide title",
      "bullets": ["short bullet, max 20 words", "..."],
      "notes": "1-2 sentence speaker note",
      "sources": ["origin label copied from a context block header"]
    }}
  ]
}}

Rules: at most {max_bullets} bullets per slide, group related points into sections logically, keep every claim traceable to the context, and end with a slide of key takeaways or conclusions."""


def build_outline_with_llm(
    provider,
    resources: list[Resource],
    topic: str,
    slides: int = 8,
    audience: str = "general professional audience",
    language: str = "the language of the sources",
    context: str | None = None,
) -> Outline:
    """Build an outline with an LLM.

    When ``context`` is provided (the RAG path), the prompt is augmented
    with the retrieved, numbered context blocks instead of a ranked
    digest of the raw resources.
    """
    if context:
        prompt = _RAG_USER_TEMPLATE.format(
            topic=topic,
            slides=slides,
            audience=audience,
            language=language,
            context=context,
            max_bullets=MAX_BULLETS_PER_SLIDE,
        )
    else:
        prompt = _USER_TEMPLATE.format(
            topic=topic,
            slides=slides,
            audience=audience,
            language=language,
            digest=_digest(resources, topic),
            max_bullets=MAX_BULLETS_PER_SLIDE,
        )
    raw = provider.complete(_SYSTEM_PROMPT, prompt)
    outline = _sanitize_outline(extract_json(raw), fallback_title=topic)
    if not outline.slides:
        raise ValueError("The model returned an outline with no usable slides.")
    return outline


def build_outline_from_retrieved(
    retrieved,
    resources: list[Resource],
    topic: str,
    slides: int = 8,
) -> Outline:
    """Extractive outline built ONLY from retrieved chunks (RAG, no LLM).

    Retrieved chunks are grouped by source in retrieval order, their
    strongest sentences become the bullets, and every slide keeps the
    citation of the chunk it came from. This is the no model path of
    phase 2: retrieval grounds the deck even when no LLM is available.
    """
    outline = Outline(
        title=topic,
        subtitle="Generated from retrieved context across multiple resources",
    )
    by_source: dict[str, list] = {}
    order: list[str] = []
    for item in retrieved:
        label = item.chunk.origin_label
        if label not in by_source:
            by_source[label] = []
            order.append(label)
        by_source[label].append(item)
    if not order:
        raise ValueError("Retrieval returned no context to build an outline from.")

    per_source = max(1, slides // max(1, len(order)))
    titles = {r.origin_label: (r.title or r.origin_label) for r in resources}
    for label in order:
        items = by_source[label]
        sentences: list[str] = []
        seen: set[str] = set()
        for item in items:
            for sentence in split_sentences(item.chunk.text):
                key = sentence[:80].lower()
                if key not in seen:
                    seen.add(key)
                    sentences.append(sentence)
        ranked = rank_sentences(
            sentences, topic=topic, top_k=per_source * MAX_BULLETS_PER_SLIDE
        )
        if not ranked:
            continue
        section_title = titles.get(label, label)
        for start in range(
            0,
            min(len(ranked), per_source * MAX_BULLETS_PER_SLIDE),
            MAX_BULLETS_PER_SLIDE,
        ):
            group = ranked[start : start + MAX_BULLETS_PER_SLIDE]
            bullets = []
            for sentence in group:
                text = re.sub(r"\s+", " ", sentence).strip()
                if len(text) > MAX_BULLET_CHARS:
                    text = text[: MAX_BULLET_CHARS - 1].rsplit(" ", 1)[0] + "..."
                bullets.append(text)
            slide_title = (
                section_title if start == 0 else f"{section_title} (continued)"
            )
            outline.slides.append(
                Slide(
                    title=slide_title,
                    bullets=bullets,
                    notes=f"Retrieved from {label} by vector search for: {topic}.",
                    sources=[label],
                )
            )
    if not outline.slides:
        raise ValueError("Retrieved context produced no usable slides.")
    outline.slides.append(
        Slide(
            title="Key Takeaways",
            bullets=[s.bullets[0] for s in outline.slides[:4] if s.bullets],
            notes="Summary of the strongest retrieved point from each section.",
            sources=list(order),
        )
    )
    return outline


def build_outline_extractive(
    resources: list[Resource],
    topic: str,
    slides: int = 8,
) -> Outline:
    """Deterministic outline: one section per resource, ranked sentences."""
    outline = Outline(
        title=topic, subtitle="Generated from multiple resources (extractive mode)"
    )
    per_resource = max(1, slides // max(1, len(resources)))
    for resource in resources:
        sentences = split_sentences(resource.text)
        ranked = rank_sentences(
            sentences, topic=topic, top_k=per_resource * MAX_BULLETS_PER_SLIDE
        )
        if not ranked:
            continue
        section_title = resource.title or resource.origin_label
        for start in range(
            0,
            min(len(ranked), per_resource * MAX_BULLETS_PER_SLIDE),
            MAX_BULLETS_PER_SLIDE,
        ):
            group = ranked[start : start + MAX_BULLETS_PER_SLIDE]
            bullets = []
            for sentence in group:
                text = re.sub(r"\s+", " ", sentence).strip()
                if len(text) > MAX_BULLET_CHARS:
                    text = text[: MAX_BULLET_CHARS - 1].rsplit(" ", 1)[0] + "..."
                bullets.append(text)
            slide_title = (
                section_title if start == 0 else f"{section_title} (continued)"
            )
            outline.slides.append(
                Slide(
                    title=slide_title,
                    bullets=bullets,
                    notes=f"Extracted from {resource.origin_label}.",
                    sources=[resource.origin_label],
                )
            )
    if not outline.slides:
        raise ValueError("Could not extract any slides from the provided resources.")
    outline.slides.append(
        Slide(
            title="Key Takeaways",
            bullets=[s.bullets[0] for s in outline.slides[:4] if s.bullets],
            notes="Summary of the strongest point from each section.",
            sources=[r.origin_label for r in resources],
        )
    )
    return outline
