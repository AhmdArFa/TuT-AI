"""MCP bridge: MCIT AI and the Craft engines as tools for Tut Agent.

Tut Agent (MCIT-Agent) connects to ``POST /api/mcp`` (MCP Streamable HTTP,
JSON responses) with the user's agent token (``/api/auth/agent-token``).
Every tool runs as that user, inside their private database, library and
Craft workspace, so the agent can only see and change what the user owns.

Unrestricted Craft MCP calls are deliberately not exposed: some upstream
engines can read absolute paths outside their configured workspace. Studio
uses fixed, server-controlled CLI invocations instead.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any, Awaitable, Callable, Dict, List, Optional, cast

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from loguru import logger

from api.auth import current_account
from open_notebook.config import AGENT_URL, PUBLIC_URL
from open_notebook.craft.pipelines import Mode
from open_notebook.domain.notebook import Note, Notebook, text_search, vector_search
from open_notebook.exports import storage

router = APIRouter(tags=["mcp"])

PROTOCOL = "2025-03-26"
Tool = Callable[[Dict[str, Any]], Awaitable[Any]]


def _schema(props: Dict[str, Any], required: List[str]) -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": props,
        "required": required,
        "additionalProperties": False,
    }


S = {"type": "string"}


async def notebooks_list(_: Dict[str, Any]):
    items = await Notebook.get_all(order_by="updated desc")
    return [
        {"id": n.id, "name": n.name, "description": n.description}
        for n in items
        if not n.archived
    ]


async def notebook_read(a: Dict[str, Any]):
    nb = await Notebook.get(a["notebook_id"])
    sources = await nb.get_sources()
    notes = await nb.get_notes(include_content=True)
    return {
        "id": nb.id,
        "name": nb.name,
        "description": nb.description,
        "sources": [{"id": s.id, "title": s.title} for s in sources],
        "notes": [
            {"id": n.id, "title": n.title, "content": (n.content or "")[:4000]}
            for n in notes
        ],
    }


async def knowledge_search(a: Dict[str, Any]):
    ids = [a["notebook_id"]] if a.get("notebook_id") else None
    limit = int(a.get("limit") or 8)
    try:
        rows = await vector_search(a["query"], limit, True, True, notebook_ids=ids)
    except Exception:
        rows = await text_search(a["query"], limit, True, True, notebook_ids=ids)
    return rows


async def note_create(a: Dict[str, Any]):
    nb = await Notebook.get(a["notebook_id"])
    note = Note(
        title=a.get("title") or "Tut Agent note", content=a["content"], note_type="ai"
    )
    await note.save()
    await note.add_to_notebook(nb.id or "")
    return {"id": note.id}


async def files_list(_: Dict[str, Any]):
    return [
        {
            "id": f.id,
            "filename": f.filename,
            "format": f.format,
            "title": f.title,
            "notebook": f.notebook_name,
        }
        for f in storage.list_files()
    ]


def _public(path: str) -> str:
    base = PUBLIC_URL.rstrip("/")
    return base + path


_MIME_TYPES = {
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
    "png": "image/png",
    "svg": "image/svg+xml",
    "txt": "text/plain",
}


def _assign_tut_file_to_user(
    tut_file_id: str, target_username: Optional[str] = None
) -> None:
    """Assign file ownership in TuT Agent PostgreSQL database to the requesting user."""
    try:
        import os

        import psycopg2

        db_url = os.getenv(
            "TUT_DATABASE_URL",
            "postgresql://postgres:0cd9e3504ca9077d8b4f2e134371117b4204c113958d568aa3358f7b12bae6ed@tut-postgres:5432/tut_agent",
        )
        with psycopg2.connect(db_url) as conn:
            with conn.cursor() as cur:
                target_user_id = None
                if target_username:
                    cur.execute(
                        "SELECT id FROM users WHERE email = %s OR email LIKE %s OR username = %s LIMIT 1",
                        (
                            f"{target_username}@mcit.local",
                            f"{target_username}@%",
                            target_username,
                        ),
                    )
                    row = cur.fetchone()
                    if row:
                        target_user_id = row[0]

                if not target_user_id:
                    # Resolve to active user in tut_agent database
                    cur.execute(
                        "SELECT id FROM users ORDER BY (email = 'admin@mcit.local') DESC, created_at DESC LIMIT 1"
                    )
                    row = cur.fetchone()
                    if row:
                        target_user_id = row[0]

                if target_user_id:
                    cur.execute(
                        "UPDATE files SET user_id = %s, visibility = 'public' WHERE id = %s",
                        (target_user_id, tut_file_id),
                    )
                    conn.commit()
                    logger.info(
                        f"Assigned TuT file {tut_file_id} to user {target_user_id} ({target_username or 'active'}) with public visibility"
                    )
                else:
                    cur.execute(
                        "UPDATE files SET visibility = 'public' WHERE id = %s",
                        (tut_file_id,),
                    )
                    conn.commit()
    except Exception as ex:
        logger.warning(f"Could not assign TuT file {tut_file_id} to user: {ex}")


async def _sync_file_to_tut_agent(
    filename: str, file_path: Any, mime_type: str, target_username: Optional[str] = None
) -> Optional[str]:
    """Upload a generated file to TuT Agent S3 storage and register it in TuT Agent database."""
    try:
        import time
        from pathlib import Path

        import httpx

        p = Path(str(file_path))
        if not p.exists():
            return None
        data = p.read_bytes()
        size = len(data)
        pathname = f"files/studio/{int(time.time())}_{filename}"

        headers = {
            "x-api-key": "sk-lh-mcitstudio000001",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            presign_url = (
                "http://tut-agent:3210/trpc/lambda/upload.createS3PreSignedUrl?batch=1"
            )
            presign_res = await client.post(
                presign_url,
                headers=headers,
                json={"0": {"json": {"pathname": pathname, "size": size}}},
            )
            if presign_res.status_code != 200:
                logger.warning(f"TuT Agent presign failed: {presign_res.status_code}")
                return None
            presigned_url = presign_res.json()[0]["result"]["data"]["json"]

            put_url = presigned_url.replace(
                "localhost:9000", "tut-storage:9000"
            ).replace("127.0.0.1:9000", "tut-storage:9000")
            put_res = await client.put(
                put_url,
                content=data,
                headers={
                    "Host": "localhost:9000",
                    "Content-Type": mime_type,
                    "Content-Length": str(size),
                },
            )
            if put_res.status_code != 200:
                logger.warning(f"TuT Agent S3 PUT failed: {put_res.status_code}")
                return None

            create_url = "http://tut-agent:3210/trpc/lambda/file.createFile?batch=1"
            create_res = await client.post(
                create_url,
                headers=headers,
                json={
                    "0": {
                        "json": {
                            "fileType": mime_type,
                            "hash": f"studio_{int(time.time() * 1000)}",
                            "name": filename,
                            "size": size,
                            "url": pathname,
                            "metadata": {"filename": filename, "path": pathname},
                        }
                    }
                },
            )
            if create_res.status_code != 200:
                logger.warning(f"TuT Agent createFile failed: {create_res.status_code}")
                return None

            tut_id = create_res.json()[0]["result"]["data"]["json"].get("id")
            logger.info(f"File {filename} synced to TuT Agent as {tut_id}")
            if tut_id:
                _assign_tut_file_to_user(tut_id, target_username)
            return tut_id
    except Exception as e:
        logger.warning(f"Failed to sync {filename} to TuT Agent: {e}")
        return None


async def studio_produce(a: Dict[str, Any]):
    """Generate professional presentations, documents, spreadsheets, and infographics directly in chat."""
    import asyncio

    from open_notebook.craft.pipelines import PRESETS, canonical
    from open_notebook.exports.content import StudioOptions
    from open_notebook.exports.produce import produce
    from open_notebook.tut import jobs

    feature = canonical(a.get("feature") or a.get("preset") or "")
    if feature not in PRESETS:
        raise ValueError(
            "Unknown document feature: use presentation, report, infograph or spreadsheet"
        )
    mode = a.get("mode") or "dark"
    if mode not in ("dark", "light"):
        raise ValueError("Unknown mode: use dark or light")
    template = a.get("template") or (
        "custom"
        if (a.get("design") or a.get("design_style") or a.get("theme_preset"))
        else "default"
    )

    # Smart notebook resolution
    nb_id = a.get("notebook_id")
    if not nb_id or str(nb_id).strip().lower() in ("default", "none", "null", ""):
        nbs = await Notebook.get_all(order_by="updated desc")
        active = [n for n in nbs if not n.archived]
        with_sources = []
        for n in active:
            srcs = await n.get_sources()
            if srcs:
                with_sources.append((n, srcs))

        inst_text = (a.get("instructions") or "").lower()
        matched = None
        if inst_text and with_sources:
            for n, srcs in with_sources:
                words = [w for w in inst_text.split() if len(w) > 3]
                if any(
                    w in n.name.lower()
                    or any(w in (s.title or "").lower() for s in srcs)
                    for w in words
                ):
                    matched = n
                    break
        if matched:
            nb_id = matched.id
        elif with_sources:
            nb_id = with_sources[0][0].id
        elif active:
            nb_id = active[0].id
        else:
            new_nb = Notebook(
                name="Tut Agent Studio",
                description="Auto-created notebook for Studio generations",
            )
            await new_nb.save()
            nb_id = new_nb.id
    else:
        try:
            await Notebook.get(nb_id)
        except Exception:
            nbs = await Notebook.get_all(order_by="updated desc")
            active = [n for n in nbs if not n.archived]
            if active:
                nb_id = active[0].id
            else:
                new_nb = Notebook(
                    name="Tut Agent Studio",
                    description="Auto-created notebook for Studio generations",
                )
                await new_nb.save()
                nb_id = new_nb.id

    instructions = (
        a.get("instructions")
        or "Comprehensive executive briefing and strategic analysis."
    )

    opts = StudioOptions(
        theme=mode,
        instructions=instructions,
        length=a.get("length") or "medium",
        slide_count=int(a.get("slide_count") or 8),
        template=template,
        theme_preset=a.get("theme_preset"),
        primary_color=a.get("primary_color"),
        accent_color=a.get("accent_color"),
        bg_color=a.get("bg_color"),
        text_color=a.get("text_color"),
        design_style=a.get("design_style"),
        diagram_type=a.get("diagram_type"),
        custom_svg=a.get("custom_svg"),
        blueprint=a.get("blueprint"),
    )

    async def work(run):
        await produce(
            run,
            nb_id,
            feature,
            cast(Mode, mode),
            opts,
            design=a.get("design") or a.get("design_style"),
        )

    run = jobs.start("studio", work, feature="studio")

    # Strictly wait for generation completion (up to 580s)
    wait_sec = min(int(a.get("wait_seconds") or 580), 580)
    if run.task:
        try:
            await asyncio.wait_for(asyncio.shield(run.task), timeout=float(wait_sec))
        except asyncio.TimeoutError:
            logger.warning(f"Generation task timed out after {wait_sec}s")
        except Exception as e:
            logger.warning(f"Generation task exception: {e}")

    if run.status != "completed":
        errors = [e.get("message") for e in run.events if e.get("type") == "error"]
        err_msg = (
            errors[0] if errors else f"Generation task ended with status '{run.status}'"
        )
        raise ValueError(f"Document generation failed: {err_msg}")

    # Synchronize each generated file to Tut Agent's S3 files library and database
    files = []
    file_lines = []
    for e in run.events:
        if e.get("type") != "file":
            continue
        item_meta = e["file"]
        f_id = item_meta["id"]
        f_name = item_meta["filename"]
        f_ext = item_meta.get("format") or f_name.rsplit(".", 1)[-1].lower()
        mime = _MIME_TYPES.get(f_ext, "application/octet-stream")

        stored_item = storage.get_file(f_id)
        tut_id = None
        if stored_item and stored_item.path.exists():
            tut_id = await _sync_file_to_tut_agent(f_name, stored_item.path, mime)
            if tut_id:
                storage.update_meta(f_id, tut_id=tut_id)

        open_url = _public(f"/files?open={f_id}&edit=true")
        dl_url = _public(f"/api/studio/files/{f_id}/download")
        tut_preview = f"/f/{tut_id}" if tut_id else open_url
        tut_dl = f"{AGENT_URL.rstrip('/')}/f/{tut_id}?download=1" if tut_id else dl_url

        files.append(
            {
                **item_meta,
                "mcit_file_id": f_id,
                "tut_file_id": tut_id,
                "preview_url": tut_preview,
                "tut_download_url": tut_dl,
                "open_url": open_url,
                "download_url": dl_url,
            }
        )
        file_lines.append(
            f"- **[{f_name}]({tut_preview})** *(Click to preview)* — [Download]({tut_dl}) — [Open in ONLYOFFICE Editor]({open_url})"
        )

    deliver_summary = "\n".join(file_lines)
    return {
        "status": "success",
        "files": files,
        "markdown_presentation": deliver_summary,
        "deliver_as": (
            "The document has been successfully generated and saved to your Files & Docs page in TuT Agent! "
            "Present the files directly to the user in chat using these Markdown links so clicking them opens the preview in the right collapsible panel without leaving the chat:\n"
            f"{deliver_summary}"
        ),
    }


async def generate_visual_blueprint(a: Dict[str, Any]):
    """Generate pure vector system architecture blueprints directly from topology graph definitions (nodes, edges, layout algorithms)."""
    import re

    from open_notebook.craft.runner import run_cli
    from open_notebook.craft.studio import job_dir
    from open_notebook.craft.studio.blueprint import (
        parse_blueprint_spec,
        render_blueprint_svg,
    )
    from open_notebook.exports import storage
    from open_notebook.exports.content import StudioDocument, StudioOptions

    topology = a.get("topology") or a.get("blueprint") or a
    mode = a.get("mode") or "dark"
    if mode not in ("dark", "light"):
        mode = "dark"

    default_title = a.get("title") or "Network Architecture Blueprint"
    spec = parse_blueprint_spec(topology, default_title=default_title)
    if not spec.nodes and a.get("nodes"):
        spec = parse_blueprint_spec(a, default_title=default_title)

    if a.get("style_override"):
        spec.metadata["style_override"] = a["style_override"]
    if a.get("design_style"):
        spec.metadata["design_style"] = a["design_style"]

    work = job_dir()
    svg, h = render_blueprint_svg(spec, mode)
    stem = re.sub(r"[^A-Za-z0-9]+", "-", spec.title).strip("-")[:60] or "blueprint"

    src = work / f"{stem}.svg"
    src.write_text(svg, "utf-8")
    png_path = work / f"{stem}.png"
    pdf_path = work / f"{stem}.pdf"

    try:
        await run_cli(
            "vectorcraft",
            ["convert", str(src), str(png_path), "--scale", "1"],
            cwd=work,
        )
        await run_cli("vectorcraft", ["convert", str(src), str(pdf_path)], cwd=work)
    except Exception as ex:
        logger.warning(f"VectorCraft conversion error: {ex}")

    doc = StudioDocument(
        kind="infographic",
        title=spec.title,
        subtitle=spec.subtitle,
        summary=spec.subtitle,
        diagram_type="blueprint",
        options=StudioOptions(theme=mode, diagram_type="blueprint"),
    )
    doc_id = storage.save_document(doc)

    nb_id = a.get("notebook_id")
    files = []
    file_lines = []

    outputs = [
        ("svg", svg.encode("utf-8"), src),
        ("png", png_path.read_bytes() if png_path.exists() else None, png_path),
        ("pdf", pdf_path.read_bytes() if pdf_path.exists() else None, pdf_path),
    ]

    for ext, data, p in outputs:
        if not data:
            continue
        item = storage.store_bytes(
            doc, ext, data, notebook_id=nb_id, document_id=doc_id
        )
        storage.update_meta(
            item.id,
            preset=f"blueprint:{mode}",
            engine="vectorcraft",
            theme=mode,
        )
        stored_item = storage.get_file(item.id) or item
        tut_id = None
        mime = _MIME_TYPES.get(ext, "application/octet-stream")
        if stored_item and stored_item.path.exists():
            tut_id = await _sync_file_to_tut_agent(
                stored_item.filename, stored_item.path, mime
            )
            if tut_id:
                storage.update_meta(stored_item.id, tut_id=tut_id)

        open_url = _public(f"/files?open={stored_item.id}&edit=true")
        dl_url = _public(f"/api/studio/files/{stored_item.id}/download")
        tut_preview = f"/f/{tut_id}" if tut_id else open_url
        tut_dl = f"{AGENT_URL.rstrip('/')}/f/{tut_id}?download=1" if tut_id else dl_url

        item_meta = stored_item.model_dump()
        files.append(
            {
                **item_meta,
                "mcit_file_id": stored_item.id,
                "tut_file_id": tut_id,
                "preview_url": tut_preview,
                "tut_download_url": tut_dl,
                "open_url": open_url,
                "download_url": dl_url,
            }
        )
        file_lines.append(
            f"- **[{stored_item.filename}]({tut_preview})** *(Click to preview)* — [Download]({tut_dl}) — [Open in Editor]({open_url})"
        )

    deliver_summary = "\n".join(file_lines)
    return {
        "status": "success",
        "title": spec.title,
        "nodes_count": len(spec.nodes),
        "edges_count": len(spec.edges),
        "layout_algorithm": spec.layout_algorithm,
        "files": files,
        "markdown_presentation": deliver_summary,
        "deliver_as": (
            "The Generative Blueprint has been mathematically synthesized and saved to your Files & Docs page in TuT Agent! "
            "Present the files directly to the user in chat using these Markdown links so clicking them opens the preview in the right collapsible panel without leaving the chat:\n"
            f"{deliver_summary}"
        ),
    }


async def studio_status(a: Dict[str, Any]):
    """Status of a job owned by this account, including the same file records as Files."""
    import asyncio

    from open_notebook.tut import jobs

    run = jobs.get_run(a["job_id"])
    if run is None:
        raise ValueError("Studio job not found")

    wait = a.get("wait", True)
    if wait and run.status == "running" and run.task:
        try:
            await asyncio.wait_for(
                asyncio.shield(run.task),
                timeout=min(int(a.get("wait_seconds", 30)), 60),
            )
        except (asyncio.TimeoutError, Exception):
            pass

    events = run.events
    errors = [e["message"] for e in events if e["type"] == "error"]
    steps = [
        e.get("title") or e.get("message")
        for e in events
        if e["type"] in ("step", "progress") and (e.get("title") or e.get("message"))
    ]
    files = [
        {
            **e["file"],
            "open_url": _public(f"/files?open={e['file']['id']}"),
            "download_url": _public(f"/api/studio/files/{e['file']['id']}/download"),
        }
        for e in events
        if e["type"] == "file"
    ]
    return {
        "job_id": run.id,
        "status": run.status,
        "errors": errors,
        "usage": run.usage,
        "files": files,
        "steps": steps[-40:],
        "next": "Call studio_status again later." if run.status == "running" else None,
        "deliver_as": "When completed, show each file as [filename](open_url) and [Download](download_url). Report any audit_issues.",
    }


async def skills_list(_: Dict[str, Any]):
    from open_notebook.craft.kit import skills as kit_skills

    return kit_skills.index()


async def skill_read(a: Dict[str, Any]):
    from open_notebook.craft.kit import skills as kit_skills

    return {"name": a["name"], "content": kit_skills.read(a["name"])}


async def file_info(a: Dict[str, Any]):
    fid = str(a.get("file_id") or "").strip()
    item = storage.get_file(fid)
    if not item:
        raise ValueError(
            f"File '{fid}' not found in the library. "
            f"To generate a new document, call 'generate_document' instead."
        )
    return item.model_dump() | {
        "open_url": _public(f"/files?open={item.id}"),
        "download_url": _public(f"/api/studio/files/{item.id}/download"),
    }


async def file_rename(a: Dict[str, Any]):
    fid = str(a.get("file_id") or "").strip()
    item = storage.get_file(fid)
    if not item:
        raise ValueError(f"File '{fid}' not found in the library.")
    stem = re.sub(r"[^\w .()-]+", "", a["name"]).strip()[:80] or item.title
    storage.update_meta(item.id, filename=f"{stem}.{item.format}", title=stem)
    return storage.get_file(item.id).model_dump()  # type: ignore[union-attr]


async def file_delete(a: Dict[str, Any]):
    fid = str(a.get("file_id") or "").strip()
    if not storage.delete_file(fid):
        raise ValueError(f"File '{fid}' not found in the library.")
    return {"deleted": fid}


def _find_slide_title_shape(slide: Any, is_cover: bool = False) -> Any:
    """Find the title shape on a PowerPoint slide (native placeholder or custom textbox)."""
    if getattr(slide.shapes, "title", None) is not None:
        return slide.shapes.title
    text_shapes = [
        sh for sh in slide.shapes if sh.has_text_frame and sh.text_frame.text.strip()
    ]
    if not text_shapes:
        return None
    if is_cover:
        for sh in text_shapes:
            top_in = sh.top.inches if sh.top else 0
            if 2.5 <= top_in <= 3.8:
                return sh
    # Standard content slide title (y: ~0.7 in PptxGenJS / templates)
    for sh in text_shapes:
        top_in = sh.top.inches if sh.top else 0
        if 0.65 <= top_in <= 1.6:
            return sh
    # Section slide title (y: ~3.45)
    for sh in text_shapes:
        top_in = sh.top.inches if sh.top else 0
        if 3.2 <= top_in <= 4.0:
            return sh
    # Cover title fallback
    for sh in text_shapes:
        top_in = sh.top.inches if sh.top else 0
        if 2.5 <= top_in <= 3.8:
            return sh
    return text_shapes[0]


async def file_read_content(a: Dict[str, Any]):
    """Inspect structured document contents: slides, titles, bullets, notes, paragraphs, tables, or spreadsheet sheets."""
    fid = str(a.get("file_id") or "").strip()
    item = storage.get_file(fid)
    if not item or not item.path.exists():
        raise ValueError(
            f"File '{fid}' not found in library. "
            f"Do NOT call file_read_content to create documents. "
            f"To CREATE a new presentation, document, report, or spreadsheet, call the 'generate_document' tool."
        )

    ext = item.format.lower()
    if ext == "pptx":
        try:
            import pptx

            prs = pptx.Presentation(str(item.path))
            slides_data = []
            for idx, slide in enumerate(prs.slides, 1):
                title = ""
                t_shape = _find_slide_title_shape(slide, is_cover=(idx == 1))
                if t_shape and t_shape.text_frame and t_shape.text_frame.text:
                    title = t_shape.text_frame.text.strip()

                texts = []
                for shape in slide.shapes:
                    if shape.has_text_frame and shape != t_shape:
                        for paragraph in shape.text_frame.paragraphs:
                            t = paragraph.text.strip()
                            if t and t != title and t not in texts:
                                texts.append(t)
                notes = ""
                if slide.has_notes_slide and slide.notes_slide.notes_text_frame:
                    notes = slide.notes_slide.notes_text_frame.text.strip()
                slides_data.append(
                    {
                        "slide_index": idx,
                        "title": title,
                        "content": texts,
                        "notes": notes,
                    }
                )
            return {
                "file_id": item.id,
                "filename": item.filename,
                "format": "pptx",
                "slide_count": len(prs.slides),
                "slides": slides_data,
            }
        except Exception as e:
            raise ValueError(f"Failed to read presentation: {e}")

    elif ext == "docx":
        try:
            import docx

            doc = docx.Document(str(item.path))
            paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
            tables_data = []
            for t in doc.tables:
                rows = []
                for row in t.rows:
                    rows.append([cell.text.strip() for cell in row.cells])
                if rows:
                    tables_data.append(rows)
            return {
                "file_id": item.id,
                "filename": item.filename,
                "format": "docx",
                "paragraph_count": len(paragraphs),
                "paragraphs": paragraphs[:100],
                "tables": tables_data,
            }
        except Exception as e:
            raise ValueError(f"Failed to read document: {e}")

    elif ext == "xlsx":
        try:
            import openpyxl

            wb = openpyxl.load_workbook(str(item.path), data_only=True)
            sheets_data = {}
            for name in wb.sheetnames:
                ws = wb[name]
                sample = []
                for row in ws.iter_rows(values_only=True, max_row=40):
                    if any(row):
                        sample.append([str(c) if c is not None else "" for c in row])
                sheets_data[name] = {
                    "max_row": ws.max_row,
                    "max_col": ws.max_column,
                    "rows": sample,
                }
            return {
                "file_id": item.id,
                "filename": item.filename,
                "format": "xlsx",
                "sheets": sheets_data,
            }
        except Exception as e:
            raise ValueError(f"Failed to read spreadsheet: {e}")

    else:
        try:
            text = item.path.read_text("utf-8", errors="replace")
            return {
                "file_id": item.id,
                "filename": item.filename,
                "format": ext,
                "content": text[:20000],
            }
        except Exception as e:
            raise ValueError(f"Failed to read file: {e}")


async def file_edit_content(a: Dict[str, Any]):
    """Edit the contents, slides, text, or structure of any file in the library."""
    fid = str(a.get("file_id") or "").strip()
    item = storage.get_file(fid)
    if not item or not item.path.exists():
        raise ValueError(
            f"File '{fid}' not found in library. You cannot edit a document before it is created. "
            f"To CREATE a new presentation, document, report, or spreadsheet, call the 'generate_document' tool FIRST."
        )

    action = a.get("action", "update_slide")
    ext = item.format.lower()
    import io

    if ext == "pptx":
        import pptx
        from pptx.util import Inches

        prs = pptx.Presentation(str(item.path))
        slide_idx = int(a.get("slide_index") or 1) - 1

        if action == "update_slide":
            if not (0 <= slide_idx < len(prs.slides)):
                raise ValueError(
                    f"Slide index {slide_idx + 1} out of range (1-{len(prs.slides)})"
                )
            slide = prs.slides[slide_idx]
            t_shape = _find_slide_title_shape(slide, is_cover=(slide_idx == 0))

            if a.get("title"):
                if t_shape:
                    t_shape.text_frame.text = str(a["title"])
                else:
                    new_t = slide.shapes.add_textbox(
                        Inches(0.75), Inches(0.7), Inches(11.0), Inches(0.9)
                    )
                    new_t.text_frame.text = str(a["title"])
                    t_shape = new_t

            if a.get("bullets"):
                bullets = (
                    a["bullets"]
                    if isinstance(a["bullets"], list)
                    else [str(a["bullets"])]
                )
                body_shape = None
                for s in slide.shapes:
                    top_in = s.top.inches if s.top else 0
                    if s.has_text_frame and s != t_shape and top_in >= 1.8:
                        body_shape = s
                        break
                if not body_shape:
                    for s in slide.shapes:
                        if s.has_text_frame and s != t_shape:
                            body_shape = s
                            break
                if not body_shape:
                    body_shape = slide.shapes.add_textbox(
                        Inches(0.75), Inches(2.0), Inches(11.0), Inches(4.5)
                    )

                tf = body_shape.text_frame
                tf.clear()
                for idx, b in enumerate(bullets):
                    p = tf.paragraphs[0] if idx == 0 else tf.add_paragraph()
                    p.text = str(b)

            if (
                a.get("notes")
                and slide.has_notes_slide
                and slide.notes_slide.notes_text_frame
            ):
                slide.notes_slide.notes_text_frame.text = str(a["notes"])

        elif action == "add_slide":
            layout = (
                prs.slide_layouts[1]
                if len(prs.slide_layouts) > 1
                else prs.slide_layouts[0]
            )
            new_slide = prs.slides.add_slide(layout)
            t_shape = _find_slide_title_shape(new_slide)
            if a.get("title"):
                if t_shape:
                    t_shape.text_frame.text = str(a["title"])
                else:
                    t_shape = new_slide.shapes.add_textbox(
                        Inches(0.75), Inches(0.7), Inches(11.0), Inches(0.9)
                    )
                    t_shape.text_frame.text = str(a["title"])
            if a.get("bullets"):
                bullets = (
                    a["bullets"]
                    if isinstance(a["bullets"], list)
                    else [str(a["bullets"])]
                )
                body_shape = None
                for s in new_slide.shapes:
                    if s.has_text_frame and s != t_shape:
                        body_shape = s
                        break
                if not body_shape:
                    body_shape = new_slide.shapes.add_textbox(
                        Inches(0.75), Inches(2.0), Inches(11.0), Inches(4.5)
                    )
                tf = body_shape.text_frame
                tf.clear()
                for idx, b in enumerate(bullets):
                    p = tf.paragraphs[0] if idx == 0 else tf.add_paragraph()
                    p.text = str(b)

        elif action == "delete_slide":
            if not (0 <= slide_idx < len(prs.slides)):
                raise ValueError(f"Slide index {slide_idx + 1} out of range")
            rId = prs.slides._sldIdLst[slide_idx].rId
            prs.part.drop_rel(rId)
            del prs.slides._sldIdLst[slide_idx]

        buf = io.BytesIO()
        prs.save(buf)
        updated = storage.update_file(item.id, buf.getvalue())
        return {
            "file_id": item.id,
            "filename": item.filename,
            "version": updated.version if updated else item.version + 1,
            "action": action,
            "status": "success",
            "open_url": _public(f"/files?open={item.id}&edit=true"),
            "download_url": _public(f"/api/studio/files/{item.id}/download"),
            "deliver_as": (
                f"Successfully updated **[{item.filename}]({_public(f'/files?open={item.id}&edit=true')})**! "
                f"[View / Edit in ONLYOFFICE]({_public(f'/files?open={item.id}&edit=true')}) — [Download]({_public(f'/api/studio/files/{item.id}/download')})"
            ),
        }

    elif ext == "docx":
        import docx

        doc = docx.Document(str(item.path))
        if action == "append_text":
            doc.add_paragraph(str(a.get("text", "")))
        elif action == "update_heading":
            doc.add_heading(str(a.get("title", "")), level=int(a.get("level") or 1))
        elif a.get("text"):
            doc.add_paragraph(str(a["text"]))

        buf = io.BytesIO()
        doc.save(buf)
        updated = storage.update_file(item.id, buf.getvalue())
        return {
            "file_id": item.id,
            "filename": item.filename,
            "version": updated.version if updated else item.version + 1,
            "action": action,
            "status": "success",
            "open_url": _public(f"/files?open={item.id}&edit=true"),
            "download_url": _public(f"/api/studio/files/{item.id}/download"),
            "deliver_as": (
                f"Successfully updated **[{item.filename}]({_public(f'/files?open={item.id}&edit=true')})**! "
                f"[View / Edit in ONLYOFFICE]({_public(f'/files?open={item.id}&edit=true')}) — [Download]({_public(f'/api/studio/files/{item.id}/download')})"
            ),
        }

    elif ext == "xlsx":
        import openpyxl

        wb = openpyxl.load_workbook(str(item.path))
        sheet_name = a.get("sheet_name") or wb.sheetnames[0]
        ws = wb[sheet_name]
        if a.get("cell") and a.get("value") is not None:
            ws[str(a["cell"])] = a["value"]
        elif a.get("row_values") and isinstance(a["row_values"], list):
            ws.append(a["row_values"])

        buf = io.BytesIO()
        wb.save(buf)
        updated = storage.update_file(item.id, buf.getvalue())
        return {
            "file_id": item.id,
            "filename": item.filename,
            "version": updated.version if updated else item.version + 1,
            "action": action,
            "status": "success",
            "open_url": _public(f"/files?open={item.id}&edit=true"),
            "download_url": _public(f"/api/studio/files/{item.id}/download"),
            "deliver_as": (
                f"Successfully updated **[{item.filename}]({_public(f'/files?open={item.id}&edit=true')})**! "
                f"[View / Edit in ONLYOFFICE]({_public(f'/files?open={item.id}&edit=true')}) — [Download]({_public(f'/api/studio/files/{item.id}/download')})"
            ),
        }

    else:
        if a.get("text") is not None:
            storage.update_file(item.id, str(a["text"]).encode("utf-8"))
            return {
                "file_id": item.id,
                "filename": item.filename,
                "status": "success",
                "open_url": _public(f"/files?open={item.id}"),
                "download_url": _public(f"/api/studio/files/{item.id}/download"),
            }
        raise ValueError(f"Editing not supported for format: {ext}")


async def file_open_editor(a: Dict[str, Any]):
    """Open or get the live ONLYOFFICE collaborative editor URL for any document."""
    fid = str(a.get("file_id") or "").strip()
    item = storage.get_file(fid)
    if not item or not item.path.exists():
        # Smart fallback: if file does not exist, auto-generate the document so the user/agent is never blocked
        logger.info(f"file_open_editor: '{fid}' not found in library. Attempting auto-generation fallback...")
        low = fid.lower()
        if any(ext in low for ext in [".pptx", "presentation", "slide", "deck"]):
            feat = "presentation"
        elif any(ext in low for ext in [".xlsx", ".csv", "sheet", "spreadsheet", "grid"]):
            feat = "spreadsheet"
        elif any(ext in low for ext in [".png", ".svg", "infograph", "sketch", "blueprint"]):
            feat = "infograph"
        elif any(ext in low for ext in [".docx", ".pdf", "report", "doc"]):
            feat = "report"
        else:
            feat = "presentation"

        clean_topic = re.sub(r"\.(pptx|docx|xlsx|png|pdf)$", "", fid, flags=re.IGNORECASE).replace("_", " ").replace("-", " ").strip()
        if not clean_topic or clean_topic.lower() in ("presentation", "report", "spreadsheet", "infograph", "document", "file"):
            clean_topic = f"Executive briefing and comprehensive overview"

        try:
            prod_res = await studio_produce({"feature": feat, "instructions": clean_topic})
            files = prod_res.get("files") or []
            if files:
                new_fid = files[0].get("mcit_file_id") or files[0].get("id")
                item = storage.get_file(new_fid)
        except Exception as gen_err:
            logger.warning(f"file_open_editor auto-generate fallback failed: {gen_err}")

        if not item or not item.path.exists():
            raise ValueError(
                f"File '{fid}' not found in library. "
                f"To CREATE a new presentation, document, report, spreadsheet, or infographic, "
                f"call the 'generate_document' tool with feature='presentation' (or 'report' / 'spreadsheet' / 'infograph')."
            )

    open_url = _public(f"/files?open={item.id}&edit=true")
    dl_url = _public(f"/api/studio/files/{item.id}/download")
    return {
        "file_id": item.id,
        "filename": item.filename,
        "format": item.format,
        "editor_url": open_url,
        "download_url": dl_url,
        "deliver_as": (
            f"You can view and edit **[{item.filename}]({open_url})** live in the ONLYOFFICE editor: "
            f"[Open ONLYOFFICE Editor]({open_url}) — [Download Directly]({dl_url})"
        ),
    }


TOOLS: Dict[str, Dict[str, Any]] = {
    "notebooks_list": {
        "fn": notebooks_list,
        "description": "List the user's notebooks.",
        "schema": _schema({}, []),
    },
    "notebook_read": {
        "fn": notebook_read,
        "description": "Read a notebook: its sources and notes.",
        "schema": _schema({"notebook_id": S}, ["notebook_id"]),
    },
    "knowledge_search": {
        "fn": knowledge_search,
        "description": "Search the user's sources and notes (optionally one notebook).",
        "schema": _schema(
            {"query": S, "notebook_id": S, "limit": {"type": "integer"}}, ["query"]
        ),
    },
    "note_create": {
        "fn": note_create,
        "description": "Save a note into a notebook.",
        "schema": _schema(
            {"notebook_id": S, "title": S, "content": S}, ["notebook_id", "content"]
        ),
    },
    "files_list": {
        "fn": files_list,
        "description": "List the user's generated files.",
        "schema": _schema({}, []),
    },
    "generate_document": {
        "fn": studio_produce,
        "description": (
            "PRIMARY TOOL TO CREATE/GENERATE DOCUMENTS: Generate any professional document directly in chat: "
            "presentation (.pptx + .pdf), formal report (.docx + .pdf), spreadsheet (.xlsx), or sketchnote infographic (.png + .pdf). "
            "The file is generated immediately and automatically saved to your Files & Docs page in Tut Agent. "
            "ALWAYS call this tool FIRST whenever the user asks to generate, create, make, build, draft, or export any presentation, "
            "deck, document, report, spreadsheet, or infographic. "
            "Do NOT call file_open_editor, file_edit_content, or skills_list before generating — call this tool directly! "
            "You have full creative freedom: choose slide_count (4 to 30), theme_preset ('red_white', 'royal_navy', 'emerald', 'dark', 'light', 'custom'), "
            "custom colors (primary_color, accent_color, bg_color, text_color), and design_style ('bold', 'corporate', 'creative', 'minimalist', 'academic'). "
            "Do NOT say you sent a request to Studio or ask the user to wait. Deliver the preview and download links directly."
        ),
        "schema": _schema(
            {
                "feature": {
                    "type": "string",
                    "enum": ["presentation", "report", "infograph", "spreadsheet"],
                    "description": "Document type: presentation (slides), report (document), spreadsheet (data sheet), or infograph (sketchnote).",
                },
                "instructions": {
                    "type": "string",
                    "description": "Detailed topic, outline, content points, numbers, or specific instructions for generating the document.",
                },
                "notebook_id": {
                    "type": "string",
                    "description": "Optional notebook ID to source material from. If omitted, uses active notebook matching topic.",
                },
                "slide_count": {
                    "type": "integer",
                    "minimum": 4,
                    "maximum": 30,
                    "description": "Total slides for presentation (4 to 30 slides, default: 8).",
                },
                "length": {
                    "type": "string",
                    "enum": ["short", "medium", "long"],
                    "description": "Length of report (short=3 sections, medium=5 sections, long=8 sections).",
                },
                "mode": {
                    "type": "string",
                    "enum": ["dark", "light"],
                    "description": "Theme mode: 'dark' (Midnight Noir) or 'light' (White Noir).",
                },
                "theme_preset": {
                    "type": "string",
                    "enum": [
                        "dark",
                        "light",
                        "red_white",
                        "royal_navy",
                        "emerald",
                        "custom",
                    ],
                    "description": "Theme preset: 'red_white' (Crimson Executive / Red & White), 'dark' (Midnight Noir), 'light' (White Noir), 'royal_navy' (Deep Navy & Gold), 'emerald' (Sovereign Green & Gold), or 'custom'.",
                },
                "primary_color": {
                    "type": "string",
                    "description": "Custom primary / accent color (hex, e.g. '#C00000' for red or '#E50914').",
                },
                "accent_color": {
                    "type": "string",
                    "description": "Custom accent highlight color (hex, e.g. '#FFD700' for gold).",
                },
                "bg_color": {
                    "type": "string",
                    "description": "Custom slide background color (hex, e.g. '#FFFFFF' for white).",
                },
                "text_color": {
                    "type": "string",
                    "description": "Custom text color (hex, e.g. '#111827' for dark charcoal).",
                },
                "design_style": {
                    "type": "string",
                    "enum": ["corporate", "minimalist", "bold", "academic", "creative"],
                    "description": "Visual design style direction.",
                },
                "template": {
                    "type": "string",
                    "enum": ["default", "custom"],
                    "description": "Template style ('default' or 'custom').",
                },
                "design": {
                    "type": "string",
                    "description": "Optional design direction (e.g. 'compact', 'royal accent', 'data first').",
                },
                "diagram_type": {
                    "type": "string",
                    "enum": [
                        "sketchnote",
                        "architecture",
                        "network",
                        "quadrant",
                        "cycle",
                        "blueprint",
                        "custom_svg",
                    ],
                    "description": "For infographics: choose visual architecture archetype ('blueprint' for generative mathematical graph blueprint, 'architecture' for layered system tiers, 'network' for abstract topology/threat graph, 'quadrant' for 2x2 matrix, 'cycle' for flywheel, 'sketchnote' for doodle sketchnote, or 'custom_svg' for programmatic SVG).",
                },
                "custom_svg": {
                    "type": "string",
                    "description": "Raw programmatic SVG string when generating custom vector graphics or charts.",
                },
                "blueprint": {
                    "type": "object",
                    "description": "Structured topology graph definition for Generative Blueprint Engine: {type, layout_algorithm ('force_directed_spring'|'hierarchical'|'circular'|'grid'), nodes: [{id, label, role, color}], edges: [{source, target, weight, style: 'directional_flow'|'governance_constraint', label}], metadata: {source_document, style_override}}.",
                },
            },
            ["feature"],
        ),
    },
    "studio_produce": {
        "fn": studio_produce,
        "description": (
            "PRIMARY TOOL TO CREATE/GENERATE DOCUMENTS: Generate any professional document directly in chat: "
            "presentation (.pptx + .pdf), formal report (.docx + .pdf), spreadsheet (.xlsx), or sketchnote infographic (.png + .pdf). "
            "The file is generated immediately and automatically saved to your Files & Docs page in Tut Agent. "
            "ALWAYS call this tool FIRST whenever the user asks to create, draft, build, generate, or export a file, "
            "presentation, slide deck, report, spreadsheet, or infographic in chat. "
            "Do NOT call file_open_editor, file_edit_content, or skills_list before generating — call this tool directly! "
            "Deliver the preview and download links directly to the user."
        ),
        "schema": _schema(
            {
                "feature": {
                    "type": "string",
                    "enum": ["presentation", "report", "infograph", "spreadsheet"],
                    "description": "Document type: presentation (slides), report (document), spreadsheet (data sheet), or infograph (sketchnote).",
                },
                "instructions": {
                    "type": "string",
                    "description": "Detailed topic, outline, content points, numbers, or specific instructions for generating the document.",
                },
                "notebook_id": {
                    "type": "string",
                    "description": "Optional notebook ID to source material from. If omitted, uses the active notebook or creates one.",
                },
                "slide_count": {
                    "type": "integer",
                    "minimum": 4,
                    "maximum": 30,
                    "description": "Total slides for presentation (4 to 30 slides, default: 8).",
                },
                "length": {
                    "type": "string",
                    "enum": ["short", "medium", "long"],
                    "description": "Length of report (short=3 sections, medium=5 sections, long=8 sections).",
                },
                "mode": {
                    "type": "string",
                    "enum": ["dark", "light"],
                    "description": "Theme mode: 'dark' (Midnight Noir) or 'light' (White Noir).",
                },
                "theme_preset": {
                    "type": "string",
                    "enum": [
                        "dark",
                        "light",
                        "red_white",
                        "royal_navy",
                        "emerald",
                        "custom",
                    ],
                    "description": "Theme preset: 'red_white' (Crimson Executive / Red & White), 'dark' (Midnight Noir), 'light' (White Noir), 'royal_navy' (Deep Navy & Gold), 'emerald' (Sovereign Green & Gold), or 'custom'.",
                },
                "primary_color": {
                    "type": "string",
                    "description": "Custom primary / accent color (hex, e.g. '#C00000' for red or '#E50914').",
                },
                "accent_color": {
                    "type": "string",
                    "description": "Custom accent highlight color (hex, e.g. '#FFD700' for gold).",
                },
                "bg_color": {
                    "type": "string",
                    "description": "Custom slide background color (hex, e.g. '#FFFFFF' for white).",
                },
                "text_color": {
                    "type": "string",
                    "description": "Custom text color (hex, e.g. '#111827' for dark charcoal).",
                },
                "design_style": {
                    "type": "string",
                    "enum": ["corporate", "minimalist", "bold", "academic", "creative"],
                    "description": "Visual design style direction.",
                },
                "template": {
                    "type": "string",
                    "enum": ["default", "custom"],
                    "description": "Template style ('default' or 'custom').",
                },
                "design": {
                    "type": "string",
                    "description": "Optional design direction (e.g. 'compact', 'royal accent', 'data first').",
                },
                "diagram_type": {
                    "type": "string",
                    "enum": [
                        "sketchnote",
                        "architecture",
                        "network",
                        "quadrant",
                        "cycle",
                        "blueprint",
                        "custom_svg",
                    ],
                    "description": "For infographics: choose visual architecture archetype ('blueprint' for generative mathematical graph blueprint, 'architecture' for layered system tiers, 'network' for abstract topology/threat graph, 'quadrant' for 2x2 matrix, 'cycle' for flywheel, 'sketchnote' for doodle sketchnote, or 'custom_svg' for programmatic SVG).",
                },
                "custom_svg": {
                    "type": "string",
                    "description": "Raw programmatic SVG string when generating custom vector graphics or charts.",
                },
                "blueprint": {
                    "type": "object",
                    "description": "Structured topology graph definition for Generative Blueprint Engine: {type, layout_algorithm ('force_directed_spring'|'hierarchical'|'circular'|'grid'), nodes: [{id, label, role, color}], edges: [{source, target, weight, style: 'directional_flow'|'governance_constraint', label}], metadata: {source_document, style_override}}.",
                },
            },
            ["feature"],
        ),
    },
    "generate_visual_blueprint": {
        "fn": generate_visual_blueprint,
        "description": (
            "Generative Blueprint Engine: generate pure vector system architecture blueprints directly from topology graph definitions. "
            "Supports both 'pure_vector_geometric' and 'handwritten_sketch' / 'whiteboard' visual styles via 'style_override'. "
            "Pass a structured JSON topology defining nodes, edges, layout algorithm ('force_directed_spring', 'hierarchical', 'circular', 'grid'), "
            "and style_override ('handwritten_sketch' for authentic hand-drawn whiteboard sketch with Caveat script font, or 'pure_vector_geometric'). "
            "Bypasses static visual templates and mathematically solves node coordinates and vector geometry. "
            "Generates .svg, .png, and .pdf files instantly and automatically saves them to Files & Docs in Tut Agent with ONLYOFFICE preview."
        ),
        "schema": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "description": "Output architecture type (e.g. 'NetworkArchitecture', 'SystemTopology', 'DataMesh').",
                },
                "style_override": {
                    "type": "string",
                    "enum": [
                        "handwritten_sketch",
                        "whiteboard",
                        "chalkboard",
                        "pure_vector_geometric",
                    ],
                    "description": "Visual rendering style: 'handwritten_sketch' / 'whiteboard' (authentic hand-drawn whiteboard sketch with Caveat script font and wobbly strokes) or 'pure_vector_geometric' (clean futuristic digital blueprint).",
                },
                "title": {
                    "type": "string",
                    "description": "Main title of the architectural blueprint.",
                },
                "subtitle": {
                    "type": "string",
                    "description": "Subtitle or context description.",
                },
                "layout_algorithm": {
                    "type": "string",
                    "enum": [
                        "force_directed_spring",
                        "hierarchical",
                        "circular",
                        "grid",
                    ],
                    "description": "Mathematical layout algorithm solver: 'force_directed_spring' (organic physical simulation), 'hierarchical' (DAG layered flow), 'circular' (concentric radial orbits), or 'grid' (orthogonal matrix).",
                },
                "nodes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {
                                "type": "string",
                                "description": "Unique node ID (e.g. 'N1')",
                            },
                            "label": {
                                "type": "string",
                                "description": "Display name of component",
                            },
                            "role": {
                                "type": "string",
                                "description": "Role: 'Core', 'Input', 'AI', 'Storage', 'Governance', 'Security', 'Gateway', 'Output'",
                            },
                            "color": {
                                "type": "string",
                                "description": "Hex color code",
                            },
                            "description": {
                                "type": "string",
                                "description": "Brief metric or subtitle",
                            },
                        },
                        "required": ["id", "label"],
                    },
                    "description": "List of system component nodes.",
                },
                "edges": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "source": {
                                "type": "string",
                                "description": "Source node ID",
                            },
                            "target": {
                                "type": "string",
                                "description": "Target node ID",
                            },
                            "weight": {
                                "type": "number",
                                "description": "Relationship weight / strength (0.1 to 1.0)",
                            },
                            "style": {
                                "type": "string",
                                "enum": [
                                    "directional_flow",
                                    "governance_constraint",
                                    "bidirectional",
                                    "dashed",
                                    "solid",
                                ],
                                "description": "Connection style",
                            },
                            "label": {
                                "type": "string",
                                "description": "Optional label along connector line",
                            },
                        },
                        "required": ["source", "target"],
                    },
                    "description": "List of interconnections and relationship flows between nodes.",
                },
                "mode": {
                    "type": "string",
                    "enum": ["dark", "light"],
                    "description": "Theme mode: 'dark' (Midnight Noir) or 'light' (White Noir).",
                },
                "metadata": {
                    "type": "object",
                    "description": "Metadata such as source_document, style_override, etc.",
                },
                "notebook_id": {
                    "type": "string",
                    "description": "Optional notebook ID to link files to.",
                },
            },
            "required": ["nodes", "edges"],
            "additionalProperties": True,
        },
    },
    "studio_status": {
        "fn": studio_status,
        "description": "Poll a Studio job you started. Returns live steps, usage, errors, audit issues and links to the completed files. Poll again while running.",
        "schema": _schema({"job_id": S}, ["job_id"]),
    },
    "skills_list": {
        "fn": skills_list,
        "description": "Optional reference list of MCIT document styling guides. NOTE: To create or generate documents, call 'generate_document' directly; do NOT call skills_list first.",
        "schema": _schema({}, []),
    },
    "skill_read": {
        "fn": skill_read,
        "description": "Read an optional document styling guide for reference. NOTE: To create or generate documents, call 'generate_document' directly; do NOT call skill_read first.",
        "schema": _schema({"name": S}, ["name"]),
    },
    "file_info": {
        "fn": file_info,
        "description": "Details and links for an EXISTING file in the library. Do NOT call this tool to generate new files; use 'generate_document' instead.",
        "schema": _schema({"file_id": S}, ["file_id"]),
    },
    "file_read_content": {
        "fn": file_read_content,
        "description": "Inspect and read the structured contents of an EXISTING presentation (.pptx), report (.docx), or spreadsheet (.xlsx) in the user's library. NOTE: To create new files, call 'generate_document'.",
        "schema": _schema({"file_id": S}, ["file_id"]),
    },
    "file_edit_content": {
        "fn": file_edit_content,
        "description": "Directly edit or modify an EXISTING presentation (.pptx), report (.docx), or spreadsheet (.xlsx) in the user's library. Modify slide titles, bullets, notes, add/remove slides, update document paragraphs, or edit spreadsheet cells. Updates the file and keeps ONLYOFFICE viewer in sync. NOTE: To create a new file from scratch, call 'generate_document'.",
        "schema": _schema(
            {
                "file_id": S,
                "action": {
                    "type": "string",
                    "enum": [
                        "update_slide",
                        "add_slide",
                        "delete_slide",
                        "append_text",
                        "update_heading",
                        "update_cell",
                    ],
                    "description": "Action to perform on the document.",
                },
                "slide_index": {
                    "type": "integer",
                    "description": "1-based slide index for presentations.",
                },
                "title": S,
                "bullets": {
                    "type": "array",
                    "items": S,
                    "description": "List of bullet points for the slide.",
                },
                "notes": S,
                "text": S,
                "sheet_name": S,
                "cell": S,
                "value": S,
            },
            ["file_id", "action"],
        ),
    },
    "file_open_editor": {
        "fn": file_open_editor,
        "description": "Open or get the live ONLYOFFICE collaborative editor link for an EXISTING document in the user's library, allowing real-time in-browser visual editing side-by-side with the agent. NOTE: To CREATE a new document, call 'generate_document' instead.",
        "schema": _schema({"file_id": S}, ["file_id"]),
    },
    "file_rename": {
        "fn": file_rename,
        "description": "Rename a file in the user's library.",
        "schema": _schema({"file_id": S, "name": S}, ["file_id", "name"]),
    },
    "file_delete": {
        "fn": file_delete,
        "description": "Delete a file from the user's library.",
        "schema": _schema({"file_id": S}, ["file_id"]),
    },
}


def _ok(rid: Any, result: Any) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def _err(rid: Any, code: int, message: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}


async def _handle(msg: Dict[str, Any]) -> Dict[str, Any] | None:
    method, rid, params = msg.get("method"), msg.get("id"), msg.get("params") or {}
    if rid is None:  # notification
        return None
    if method == "initialize":
        return _ok(
            rid,
            {
                "protocolVersion": PROTOCOL,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "tut-ai", "title": "TuT AI", "version": "1.0"},
                "instructions": (
                    "DOCUMENT GENERATION RULES FOR TUT AGENT:\n"
                    "1. When the user asks to generate, create, make, build, draft, or export ANY presentation, "
                    "slide deck, report, Word document, spreadsheet, or infographic: ALWAYS call the 'generate_document' "
                    "tool FIRST as your primary action.\n"
                    "2. Do NOT call 'file_open_editor', 'file_edit_content', 'file_read_content', or 'file_info' to create files — "
                    "those tools are strictly for files that already exist in the user's library.\n"
                    "3. Do NOT call 'skills_list' or 'skill_read' when generating documents — call 'generate_document' directly.\n"
                    "4. After 'generate_document' finishes, deliver the returned Markdown preview and download links directly to the user in chat.\n"
                ),
            },
        )
    if method == "ping":
        return _ok(rid, {})
    if method == "tools/list":
        return _ok(
            rid,
            {
                "tools": [
                    {
                        "name": n,
                        "description": t["description"],
                        "inputSchema": t["schema"],
                    }
                    for n, t in TOOLS.items()
                ]
            },
        )
    if method == "tools/call":
        tool_name = params.get("name", "")
        tool_args = params.get("arguments") or {}
        logger.info(f"MCP tool call: {tool_name} with args: {tool_args}")
        tool = TOOLS.get(tool_name)
        if not tool:
            return _err(rid, -32602, f"Unknown tool: {tool_name}")
        try:
            data = await tool["fn"](tool_args)
            text = data if isinstance(data, str) else json.dumps(data, default=str)
            return _ok(
                rid, {"content": [{"type": "text", "text": text}], "isError": False}
            )
        except Exception as e:
            logger.warning(f"MCP tool {tool_name} failed: {type(e).__name__}: {e}")
            return _ok(
                rid,
                {
                    "content": [
                        {"type": "text", "text": str(e)[:500] or type(e).__name__}
                    ],
                    "isError": True,
                },
            )
    return _err(rid, -32601, "Method not found")


@router.post("/mcp")
async def mcp_endpoint(request: Request):
    current_account(request)
    body = await request.json()
    headers = {
        "Mcp-Session-Id": request.headers.get("mcp-session-id") or uuid.uuid4().hex
    }
    if isinstance(body, list):
        replies = [r for r in [await _handle(m) for m in body] if r is not None]
        return (
            JSONResponse(replies, headers=headers)
            if replies
            else Response(status_code=202, headers=headers)
        )
    reply = await _handle(body)
    if reply is None:
        return Response(status_code=202, headers=headers)
    return JSONResponse(reply, headers=headers)


@router.get("/mcp")
async def mcp_stream_unsupported():
    return Response(status_code=405)
