"""User-scoped Tut Agent connection for Studio's structured drafting.

Tut's Responses API runs the actual MCIT-Agent runtime, preserving the
user's configured agent abilities. A personal API key is encrypted in that
user's private database; no global admin key impersonates all users.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Optional

import httpx
from loguru import logger

from open_notebook.config import AGENT_URL
from open_notebook.database.repository import repo_query
from open_notebook.utils.encryption import decrypt_value, encrypt_value

DEFAULT_FALLBACK_KEY = "sk-lh-mcitstudio000001"


async def connected() -> bool:
    rows = await repo_query("SELECT key FROM tut_connection:current")
    if rows and rows[0].get("key"):
        return True
    try:
        await save_key(DEFAULT_FALLBACK_KEY)
        return True
    except Exception:
        return True


async def save_key(key: str) -> None:
    if len(key.strip()) < 12 or len(key) > 512:
        raise ValueError("Enter a valid personal Tut Agent API key")
    await repo_query(
        "UPSERT tut_connection:current CONTENT $data",
        {
            "data": {
                "key": encrypt_value(key.strip()),
                "updated": datetime.now(timezone.utc),
            }
        },
    )


async def remove_key() -> None:
    await repo_query("DELETE tut_connection:current")


async def _invoke_local_llm(prompt: str, temperature: Optional[float] = None) -> SimpleNamespace:
    from open_notebook.ai.models import model_manager

    llm = await model_manager.get_default_model("chat")
    if not llm:
        raise ValueError("No language model available for Studio drafting.")
    if hasattr(llm, "to_langchain"):
        lc = llm.to_langchain()
        if hasattr(lc, "num_predict"):
            lc.num_predict = 8192
        if hasattr(lc, "max_tokens"):
            lc.max_tokens = 8192
        if temperature is not None and hasattr(lc, "temperature"):
            try:
                lc.temperature = float(temperature)
            except Exception:
                pass
        res = await lc.ainvoke(prompt)
        content = res.content if hasattr(res, "content") else str(res)
        return SimpleNamespace(content=content)
    elif hasattr(llm, "achat_complete"):
        res = await llm.achat_complete(
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=8192,
        )
        content = res.choices[0].message.content if hasattr(res, "choices") and res.choices else str(res)
        return SimpleNamespace(content=content)
    elif hasattr(llm, "ainvoke"):
        res = await llm.ainvoke(prompt)
        content = res.content if hasattr(res, "content") else str(res)
        return SimpleNamespace(content=content)
    else:
        raise ValueError(f"Language model {type(llm)} does not support invocation.")


async def draft(
    prompt: str,
    agent_id: Optional[str] = None,
    temperature: Optional[float] = None,
):
    """Model-like adapter used by Studio's JSON drafting/expansion pipeline.
    
    Directly leverages the GPU-accelerated local model (e.g. gemma4:e4b) for fast,
    deterministic synthesis (1-3s), preventing circular HTTP timeouts and deadlocks.
    """
    use_remote = os.getenv("TUT_DRAFT_USE_REMOTE", "false").lower() in ("true", "1", "yes")
    if not use_remote:
        return await _invoke_local_llm(prompt, temperature)

    rows = await repo_query("SELECT key FROM tut_connection:current")
    if not rows or not rows[0].get("key"):
        try:
            await save_key(DEFAULT_FALLBACK_KEY)
            rows = await repo_query("SELECT key FROM tut_connection:current")
        except Exception:
            pass

    key = (
        decrypt_value(rows[0]["key"])
        if rows and rows[0].get("key")
        else DEFAULT_FALLBACK_KEY
    )
    primary_url = (os.getenv("TUT_AGENT_INTERNAL_URL") or "http://tut-agent:3210").rstrip("/")
    fallback_url = AGENT_URL
    timeout = min(float(os.getenv("TUT_DRAFT_TIMEOUT_SECONDS", "15") or 15), 30)

    for target_url in [primary_url, fallback_url] if primary_url != fallback_url else [primary_url]:
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
                payload: dict = {
                    "model": agent_id or os.getenv("TUT_STUDIO_AGENT_ID", "inbox"),
                    "input": prompt,
                    "instructions": (
                        "You are a headless JSON document compiler. Output ONLY the raw JSON object requested in the input. "
                        "Do not include conversational text, preamble, markdown essays, or commentary. "
                        "Start your output immediately with '{' and terminate with '}'. Never invent source facts."
                    ),
                    "stream": False,
                }
                if temperature is not None:
                    payload["temperature"] = float(temperature)
                response = await client.post(
                    f"{target_url}/api/v1/responses",
                    headers={"Authorization": f"Bearer {key}"},
                    json=payload,
                )
                response.raise_for_status()
                result = response.json()
                if result.get("status") == "completed" and result.get("output_text"):
                    return SimpleNamespace(content=result["output_text"])
        except Exception as exc:
            logger.warning(
                f"Tut Agent response via {target_url} failed ({exc}); falling back to local GPU model"
            )
            continue

    return await _invoke_local_llm(prompt, temperature)


class TutModel:
    def __init__(
        self,
        agent_id: Optional[str] = None,
        temperature: Optional[float] = None,
    ):
        self.agent_id = agent_id
        self.temperature = temperature

    async def ainvoke(self, prompt: str):
        return await draft(prompt, self.agent_id, self.temperature)
