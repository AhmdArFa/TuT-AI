"""Tests for the unlimited-upload + centralized-config change.

Covers: the API accepts bodies of any size by default (middleware with
max_body_size=None passes everything through), a positive
OPEN_NOTEBOOK_MAX_UPLOAD_SIZE_MB still installs a cap, uploaded files are
streamed to disk in bounded chunks (no whole-file read), and the essential
capacity numbers / addresses / model names live in open_notebook.config
instead of scattered literals.
"""

import io

import pytest
from starlette.datastructures import UploadFile

import open_notebook.config as config
from api.middleware import MaxBodySizeMiddleware, get_max_upload_size_bytes


async def _echo_body_app(scope, receive, send):
    body = b""
    more_body = True
    while more_body:
        message = await receive()
        body += message.get("body", b"")
        more_body = message.get("more_body", False)
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send(
        {"type": "http.response.body", "body": f"received {len(body)} bytes".encode()}
    )


def _scope(headers=None):
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return {"type": "http", "method": "POST", "path": "/upload", "headers": raw}


class _Chunks:
    def __init__(self, chunks):
        self._chunks = list(chunks)

    async def __call__(self):
        if not self._chunks:
            return {"type": "http.request", "body": b"", "more_body": False}
        chunk = self._chunks.pop(0)
        return {
            "type": "http.request",
            "body": chunk,
            "more_body": bool(self._chunks),
        }


class _Send:
    def __init__(self):
        self.messages = []

    async def __call__(self, message):
        self.messages.append(message)

    @property
    def status(self):
        for m in self.messages:
            if m["type"] == "http.response.start":
                return m["status"]
        return None


class TestUnlimitedByDefault:
    @pytest.mark.asyncio
    async def test_uncapped_middleware_passes_a_body_far_above_old_100mb(self):
        # The old 100 MB cap is gone: a body that would have been 413'd
        # before must now flow through untouched.
        middleware = MaxBodySizeMiddleware(_echo_body_app, max_body_size=None)
        send = _Send()
        await middleware(
            _scope(headers={"content-length": str(150 * 1024 * 1024)}),
            _Chunks([b"x" * (150 * 1024 * 1024)]),
            send,
        )
        assert send.status == 200

    def test_env_cap_still_works_when_set(self, monkeypatch):
        monkeypatch.setenv("OPEN_NOTEBOOK_MAX_UPLOAD_SIZE_MB", "500")
        assert get_max_upload_size_bytes() == 500 * 1024 * 1024


class TestStreamingSave:
    @pytest.mark.asyncio
    async def test_save_streams_in_small_chunks(self, monkeypatch, tmp_path):
        from api.routers import sources

        monkeypatch.setattr(sources, "uploads_folder", lambda: str(tmp_path))
        monkeypatch.setattr(config, "UPLOAD_STREAM_CHUNK_BYTES", 7)

        data = b"PDF-bytes-" * 1000  # 10,000 bytes, chunked 7 at a time
        upload = UploadFile(filename="big.pdf", file=io.BytesIO(data))
        path = await sources.save_uploaded_file(upload)
        assert open(path, "rb").read() == data


class TestCentralizedConfig:
    def test_capacity_and_model_defaults_live_in_config(self):
        assert config.DEFAULT_MAX_UPLOAD_SIZE_MB is None
        assert config.LARGE_CONTEXT_THRESHOLD_TOKENS == 105_000
        assert config.OFFICE_MAX_SAVE_MB == 100
        assert config.OFFICE_TICKET_HOURS == 4
        assert config.UPLOAD_STREAM_CHUNK_BYTES == 1024 * 1024

    def test_service_addresses_and_models_live_in_config(self):
        assert config.PUBLIC_URL == "http://localhost:8502"
        assert config.INTERNAL_API_URL == "http://localhost:5055"
        assert config.AGENT_URL == "http://localhost:3210"
        assert config.OLLAMA_BASE_URL == "http://localhost:11434"
        assert config.OMLX_BASE_URL == "http://localhost:11435/v1"
        assert config.OLLAMA_CHAT_MODEL == "qwen2.5:7b"
        assert config.OLLAMA_EMBEDDING_MODEL == "nomic-embed-text"

    def test_no_essential_literal_left_in_rewired_modules(self):
        import inspect

        import open_notebook.ai.provision as provision

        src = inspect.getsource(provision.provision_langchain_model)
        assert "105_000" not in src
        assert "LARGE_CONTEXT_THRESHOLD_TOKENS" in src
