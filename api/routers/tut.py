"""Per-user connection to the Tut Agent runtime.

Saving the personal Tut key connects both directions for that person:
Studio drafts through their Tut runtime, and their Tut Agent gets the MCIT AI
tools (notebooks, knowledge search, the four Studio features, document skills
and files) as a personal MCP connector holding their own MCIT AI token.
"""

import os

import httpx
from fastapi import APIRouter, HTTPException, Request
from loguru import logger
from pydantic import BaseModel

from api.auth import current_account
from open_notebook import accounts
from open_notebook.config import INTERNAL_API_URL
from open_notebook.tut import client

router = APIRouter(prefix="/tut", tags=["tut"])


class Connection(BaseModel):
    key: str


async def connect_tools(account: accounts.Account) -> dict:
    """Give the person's Tut Agent the MCIT AI tools (idempotent)."""
    base = (os.getenv("TUT_AGENT_INTERNAL_URL") or "").rstrip("/")
    admin = os.getenv("MCIT_ADMIN_BOOTSTRAP_TOKEN") or ""
    api = INTERNAL_API_URL.rstrip("/")
    if not base or not admin:
        return {"tools": "not_configured"}
    session = accounts.issue_session(account, hours=24 * 90, scope="mcp")
    email = f"{account.username}@{os.getenv('MCIT_EMAIL_DOMAIN') or 'mcit.local'}"
    try:
        async with httpx.AsyncClient(timeout=60) as http:
            r = await http.post(
                f"{base}/webapi/mcit/admin/connect-mcp",
                headers={"x-mcit-bootstrap-token": admin},
                json={"sub": account.id, "email": email, "token": session["token"], "url": f"{api}/api/mcp"},
            )
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if r.status_code >= 400:
            logger.warning(f"Tut tool connection failed for {account.username}: {r.status_code} {data.get('error')}")
            return {"tools": "error", "detail": data.get("error")}
        return {"tools": "connected" if data.get("linked") else "pending_first_sign_in", "count": data.get("tools")}
    except httpx.HTTPError as e:
        logger.warning(f"Tut tool connection failed for {account.username}: {e}")
        return {"tools": "unreachable"}


async def auto_connect_all_accounts() -> None:
    """Connect Tut Agent MCP tools for all registered accounts."""
    try:
        accs = await accounts.list_accounts()
        for acc in accs:
            if acc.active:
                await connect_tools(acc)
    except Exception as e:
        logger.warning(f"Tut Agent auto-connect failed: {e}")


@router.get("/connection")
async def connection_status(request: Request):
    if not await client.connected():
        try:
            await client.save_key(client.DEFAULT_FALLBACK_KEY)
            await connect_tools(current_account(request))
        except Exception as e:
            logger.debug(f"Auto-connect on status check: {e}")
    return {"connected": await client.connected()}


@router.put("/connection")
async def connect(body: Connection, request: Request):
    try:
        await client.save_key(body.key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    tools = await connect_tools(current_account(request))
    await accounts.audit("tut.connected", actor=current_account(request).id, detail=tools)
    return {"connected": True, **tools}


@router.post("/connection/tools")
async def reconnect_tools(request: Request):
    """Re-link the MCIT AI tools in Tut Agent (for example after the first Tut sign-in)."""
    return await connect_tools(current_account(request))


@router.delete("/connection")
async def disconnect():
    await client.remove_key()
    return {"connected": False}
