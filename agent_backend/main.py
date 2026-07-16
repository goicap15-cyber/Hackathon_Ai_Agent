# agent_backend/main.py
from fastapi import FastAPI, HTTPException, status, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Any, Optional
import os
import logging
import datetime
import httpx
import json

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# ─── True AI Agent ───────────────────────────────────────────────────────────
from agent_backend.agent_loop import run_agent

logger = logging.getLogger("agent_backend.main")
logging.basicConfig(level=logging. INFO)

app = FastAPI(title="AI Agent CRM Co-Pilot", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

AUDIT_LOG_PATH = os.path.join(os.path.dirname(__file__), "audit.log")

# Base URL of the downstream CRM backend. Centralised so it is easy to change
# and can be overridden through an environment variable in different envs.
CRM_BASE_URL = os.getenv("CRM_BASE_URL", "http://127.0.0.1:8001").rstrip("/")


# ─── Models ──────────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str
    customer_id: Optional[str] = None
    rm_name: str = "Nguyễn Phương Linh"


# ─── Helpers ─────────────────────────────────────────────────────────────────
def log_audit(rm_name: str, action: str, details: str) -> None:
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] RM: {rm_name} | Action: {action} | Details: {details}\n")
    except OSError as exc:
        # Auditing must never break the main request flow.
        logger.warning("Failed to write audit log: %s", exc)


def _parse_response(response: httpx. Response) -> Any:
    """Return JSON body when possible, otherwise fall back to raw text."""
    try:
        return response.json()
    except (json. JSONDecodeError, ValueError):
        return {"status_code": response.status_code, "content": response.text}


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.get("/api/audit-logs")
def get_audit_logs():
    if not os.path.exists(AUDIT_LOG_PATH):
        return []
    with open(AUDIT_LOG_PATH, "r", encoding="utf-8") as f:
        return [line.strip() for line in f.readlines()[-50:]]


@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    """
    True AI Agent endpoint.
    LLM tự quyết định gọi tool nào để tìm data — không có heuristic code.
    """
    result = await run_agent(
        user_message=request.message,
        prev_customer_id=request.customer_id or "",
        rm_name=request.rm_name,
    )

    log_audit(
        rm_name=request.rm_name,
        action="Agent Chat",
        details=f"Query: '{request.message}' | Ctx: {request.customer_id}",
    )

    return result


@app.post("/api/upload-database")
async def upload_database_proxy(append: bool = False, file: UploadFile = File(...)):
    async with httpx. AsyncClient(timeout=300.0) as client:
        try:
            content = await file.read()
            files = {
                "file": (
                    file.filename,
                    content,
                    file.content_type or "application/octet-stream",
                )
            }
            response = await client.post(
                f"{CRM_BASE_URL}/api/upload-database",
                params={"append": append},
                files=files,
            )
            return _parse_response(response)
        except httpx. HTTPError as exc:
            logger.exception("Upload proxy failed")
            raise HTTPException(
                status_code=status. HTTP_502_BAD_GATEWAY,
                detail=f"Lỗi upload: {exc}",
            )


@app.delete("/api/upload-database")
async def delete_database_proxy():
    async with httpx. AsyncClient(timeout=60.0) as client:
        try:
            response = await client.delete(f"{CRM_BASE_URL}/api/database")
            return _parse_response(response)
        except httpx. HTTPError as exc:
            logger.exception("Delete DB proxy failed")
            raise HTTPException(
                status_code=status. HTTP_502_BAD_GATEWAY,
                detail=f"Lỗi xóa DB: {exc}",
            )


@app.get("/api/crm/{path:path}")
async def crm_proxy_get(path: str, request: Request):
    async with httpx. AsyncClient(timeout=30.0) as client:
        try:
            url = f"{CRM_BASE_URL}/{path}"
            params = dict(request.query_params)
            response = await client.get(url, params=params)
            return _parse_response(response)
        except httpx. HTTPError as exc:
            logger.exception("CRM GET proxy failed for %s", path)
            raise HTTPException(status_code=status. HTTP_502_BAD_GATEWAY, detail=str(exc))


@app.post("/api/crm/{path:path}")
async def crm_proxy_post(path: str, request: Request):
    async with httpx. AsyncClient(timeout=30.0) as client:
        try:
            body = await request.json()
            response = await client.post(f"{CRM_BASE_URL}/{path}", json=body)
            return _parse_response(response)
        except httpx. HTTPError as exc:
            logger.exception("CRM POST proxy failed for %s", path)
            raise HTTPException(status_code=status. HTTP_502_BAD_GATEWAY, detail=str(exc))


@app.put("/api/crm/{path:path}")
async def crm_proxy_put(path: str, request: Request):
    async with httpx. AsyncClient(timeout=30.0) as client:
        try:
            body = await request.json()
            response = await client.put(f"{CRM_BASE_URL}/{path}", json=body)
            return _parse_response(response)
        except httpx. HTTPError as exc:
            logger.exception("CRM PUT proxy failed for %s", path)
            raise HTTPException(status_code=status. HTTP_502_BAD_GATEWAY, detail=str(exc))


# ─── Static frontend ─────────────────────────────────────────────────────────
_FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
if os.path.isdir(_FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=_FRONTEND_DIR), name="static")

    @app.get("/")
    async def serve_index():
        return FileResponse(os.path.join(_FRONTEND_DIR, "index.html"))

    @app.get("/{filename}")
    async def serve_file(filename: str):
        fp = os.path.join(_FRONTEND_DIR, filename)
        if os.path.isfile(fp):
            return FileResponse(fp)
        return FileResponse(os.path.join(_FRONTEND_DIR, "index.html"))
