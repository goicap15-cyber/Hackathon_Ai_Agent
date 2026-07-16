# agent_backend/main.py
from fastapi import FastAPI, HTTPException, status, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
import os
import datetime
import httpx
import json

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# ─── True AI Agent ───────────────────────────────────────────────────────────
from agent_backend.agent_loop import run_agent

app = FastAPI(title="AI Agent CRM Co-Pilot", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

AUDIT_LOG_PATH = os.path.join(os.path.dirname(__file__), "audit.log")


# ─── Models ──────────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message:     str
    customer_id: Optional[str] = None
    rm_name:     str = "Nguyễn Phương Linh"


# ─── Helpers ─────────────────────────────────────────────────────────────────
def log_audit(rm_name: str, action: str, details: str):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] RM: {rm_name} | Action: {action} | Details: {details}\n")


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.get("/api/audit-logs")
def get_audit_logs():
    if not os.path.exists(AUDIT_LOG_PATH):
        return []
    with open(AUDIT_LOG_PATH, "r", encoding="utf-8") as f:
        return [l.strip() for l in f.readlines()[-50:]]


@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    """
    True AI Agent endpoint.
    LLM tự quyết định gọi tool nào de tim data — không có heuristic code.
    """
    result = await run_agent(
        user_message=request.message,
        prev_customer_id=request.customer_id or "",
        rm_name=request.rm_name,
    )

    log_audit(
        rm_name=request.rm_name,
        action="Agent Chat",
        details=f"Query: '{request.message}' | Ctx: {request.customer_id}"
    )

    return result


@app.post("/api/upload-database")
async def upload_database_proxy(append: bool = False, file: UploadFile = File(...)):
    async with httpx.AsyncClient(timeout=300.0) as client:
        try:
            content = await file.read()
            files = {"file": (file.filename, content, file.content_type or "application/octet-stream")}
            response = await client.post(
                "http://127.0.0.1:8001/api/upload-database",
                params={"append": append},
                files=files
            )
            return response.json()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Loi upload: {str(e)}")


@app.delete("/api/upload-database")
async def delete_database_proxy():
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.delete("http://127.0.0.1:8001/api/database")
            return response.json()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Loi xoa DB: {str(e)}")


@app.get("/api/crm/{path:path}")
async def crm_proxy_get(path: str, request: Request):
    async with httpx.AsyncClient() as client:
        try:
            url = f"http://127.0.0.1:8001/{path}"
            params = dict(request.query_params)
            response = await client.get(url, params=params, timeout=30.0)
            return response.json()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/crm/{path:path}")
async def crm_proxy_post(path: str, request: Request):
    async with httpx.AsyncClient() as client:
        try:
            body = await request.json()
            response = await client.post(
                f"http://127.0.0.1:8001/{path}", json=body, timeout=30.0
            )
            return response.json()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/crm/{path:path}")
async def crm_proxy_put(path: str, request: Request):
    async with httpx.AsyncClient() as client:
        try:
            body = await request.json()
            response = await client.put(
                f"http://127.0.0.1:8001/{path}", json=body, timeout=30.0
            )
            return response.json()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


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
