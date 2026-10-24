"""LLM providers: offline (Ollama), online (OpenAI-compatible), extractive.

The generator never hard-depends on a network or a GPU:

* ``offline`` mode talks to a local Ollama server (the TuT way: sovereign,
  data never leaves the machine).
* ``online`` mode talks to any OpenAI-compatible chat API.
* ``extractive`` mode needs no model at all: it ranks sentences with a
  TF-IDF style scorer and builds a faithful, citation-preserving outline.
  It is the guaranteed fallback in ``auto`` mode.
"""

from __future__ import annotations

import json
import math
import os
import re
from collections import Counter

import requests


class LLMError(RuntimeError):
    """Raised when a provider cannot produce a completion."""


class OllamaProvider:
    """Local inference through Ollama (default http://localhost:11434)."""

    name = "ollama"

    def __init__(
        self, model: str | None = None, host: str | None = None, timeout: int = 300
    ):
        self.model = model or os.environ.get("MRPG_OLLAMA_MODEL", "qwen3:8b")
        self.host = (
            host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        ).rstrip("/")
        self.timeout = timeout

    def complete(self, system: str, user: str) -> str:
        try:
            response = requests.post(
                f"{self.host}/api/chat",
                json={
                    "model": self.model,
                    "stream": False,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json()["message"]["content"]
        except Exception as exc:  # network down, model missing, bad payload
            raise LLMError(f"Ollama completion failed: {exc}") from exc


class OpenAICompatibleProvider:
    """Any OpenAI-compatible chat completions endpoint."""

    name = "openai-compatible"

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: int = 180,
    ):
        self.model = model or os.environ.get("MRPG_ONLINE_MODEL", "gpt-4o-mini")
        self.base_url = (
            base_url
            or os.environ.get("MRPG_ONLINE_BASE_URL", "https://api.openai.com/v1")
        ).rstrip("/")
        self.api_key = api_key or os.environ.get("MRPG_ONLINE_API_KEY", "")
        self.timeout = timeout

    def complete(self, system: str, user: str) -> str:
        if not self.api_key:
            raise LLMError("MRPG_ONLINE_API_KEY is not set for online mode.")
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": 0.3,
                },
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
        except Exception as exc:
            raise LLMError(f"Online completion failed: {exc}") from exc


_WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)
_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "are",
    "was",
    "were",
    "has",
    "have",
    "had",
    "will",
    "would",
    "can",
    "could",
    "should",
    "into",
    "its",
    "it's",
    "they",
    "them",
    "then",
    "than",
    "but",
    "not",
    "all",
    "any",
    "في",
    "من",
    "إلى",
    "على",
    "أن",
    "إن",
    "ما",
    "لا",
    "هو",
    "هي",
    "كان",
    "يكون",
    "ذلك",
    "هذه",
    "هذا",
    "مع",
    "عن",
    "بعد",
    "قبل",
    "عند",
    "لدى",
}


def _tokens(text: str) -> list[str]:
    return [
        t.lower()
        for t in _WORD_RE.findall(text)
        if len(t) > 2 and t.lower() not in _STOPWORDS
    ]


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?؟])\s+|\n+", text)
    return [p.strip() for p in parts if len(p.strip()) >= 30]


def rank_sentences(sentences: list[str], topic: str = "", top_k: int = 40) -> list[str]:
    """Rank sentences by TF-IDF style salience plus topic overlap."""
    if not sentences:
        return []
    docs = [_tokens(s) for s in sentences]
    doc_freq: Counter = Counter()
    for doc in docs:
        doc_freq.update(set(doc))
    total = len(docs)
    topic_terms = set(_tokens(topic))

    def score(index: int) -> float:
        doc = docs[index]
        if not doc:
            return 0.0
        freq = Counter(doc)
        value = 0.0
        for term, count in freq.items():
            idf = math.log((total + 1) / (doc_freq[term] + 1)) + 1.0
            value += count * idf
            if term in topic_terms:
                value += 2.0 * idf
        return value / (len(doc) ** 0.7)

    ranked = sorted(range(len(sentences)), key=score, reverse=True)[:top_k]
    return [sentences[i] for i in sorted(ranked)]


def extract_json(text: str) -> dict:
    """Pull the first JSON object out of a model response."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else None
    if candidate is None:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise LLMError("Model response did not contain a JSON object.")
        candidate = text[start : end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise LLMError(f"Model returned invalid JSON: {exc}") from exc


def get_provider(mode: str, **kwargs):
    """Resolve a provider by mode name."""
    if mode == "offline":
        return OllamaProvider(
            **{k: v for k, v in kwargs.items() if k in {"model", "host"}}
        )
    if mode == "online":
        return OpenAICompatibleProvider(
            **{k: v for k, v in kwargs.items() if k in {"model", "base_url", "api_key"}}
        )
    raise ValueError(f"Unknown provider mode: {mode}")
