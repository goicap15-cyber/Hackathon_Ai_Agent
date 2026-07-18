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
import uuid
import shutil
from dotenv import load_dotenv

# Load env variables
load_dotenv()

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# ─── True AI Agent ───────────────────────────────────────────────────────────
from agent_backend.agent_loop import run_agent
from agent_backend.meeting_service import (
    process_and_analyze_document,
    get_current_document,
    save_current_document,
    answer_document_question
)

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
    history: list = []
    role: str = 'rm'


# ─── Helpers ─────────────────────────────────────────────────────────────────
def log_audit(actor_id, action, details, role='', evidence_ids=None, policy_decision='allow') -> None:
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    audit_path = os.path.join(data_dir, "audit.log")
    entry = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "correlation_id": str(uuid.uuid4()),
        "actor_id": actor_id,
        "actor_role": role,
        "action": action,
        "policy_decision": policy_decision,
        "evidence_ids": evidence_ids if evidence_ids is not None else [],
        "details": details,
    }
    try:
        os.makedirs(data_dir, exist_ok=True)
        with open(audit_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
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
        history=request.history,
        role=request.role,
    )

    log_audit(
        actor_id=request.rm_name,
        action="Agent Chat",
        details=f"Query: '{request.message}' | Ctx: {request.customer_id}",
    )

    return result


class MeetingChatRequest(BaseModel):
    message: str
    history: list = []


class SelectDocRequest(BaseModel):
    filename: str


class DeleteDocRequest(BaseModel):
    filename: str


@app.on_event("startup")
def copy_existing_document_to_library():
    # If document_store.json exists, copy it to documents library
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    doc_store = os.path.join(data_dir, "document_store.json")
    docs_dir = os.path.join(data_dir, "documents")
    os.makedirs(docs_dir, exist_ok=True)
    
    if os.path.exists(doc_store):
        try:
            with open(doc_store, "r", encoding="utf-8") as f:
                doc_data = json.load(f)
            filename = doc_data.get("filename")
            if filename:
                import re
                safe_filename = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)
                lib_path = os.path.join(docs_dir, f"{safe_filename}.json")
                if not os.path.exists(lib_path):
                    with open(lib_path, "w", encoding="utf-8") as f:
                        json.dump(doc_data, f, ensure_ascii=False, indent=2)
                    logger.info(f"Copied existing active document {filename} to documents library.")
        except Exception as e:
            logger.error(f"Failed to copy active document to library: {e}")


@app.get("/api/document/list")
def list_documents():
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    docs_dir = os.path.join(data_dir, "documents")
    if not os.path.exists(docs_dir):
        return {"status": "success", "data": []}
    
    file_list = []
    for filename in os.listdir(docs_dir):
        if filename.endswith(".json"):
            path = os.path.join(docs_dir, filename)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    doc_data = json.load(f)
                    file_list.append({
                        "filename": doc_data.get("filename", filename[:-5]),
                        "page_count": len(doc_data.get("pages", []))
                    })
            except Exception:
                pass
    return {"status": "success", "data": file_list}


@app.post("/api/document/select")
def select_document(request: SelectDocRequest):
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    docs_dir = os.path.join(data_dir, "documents")
    import re
    safe_filename = re.sub(r'[^a-zA-Z0-9._-]', '_', request.filename)
    target_path = os.path.join(docs_dir, f"{safe_filename}.json")
    
    if not os.path.exists(target_path):
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu trong thư viện.")
    
    try:
        with open(target_path, "r", encoding="utf-8") as f:
            doc_data = json.load(f)
        # Save as active document
        save_current_document(doc_data)
        return {"status": "success", "data": doc_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi chuyển đổi tài liệu: {str(e)}")


@app.post("/api/document/delete")
def delete_document(request: DeleteDocRequest):
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    docs_dir = os.path.join(data_dir, "documents")
    import re
    safe_filename = re.sub(r'[^a-zA-Z0-9._-]', '_', request.filename)
    target_path = os.path.join(docs_dir, f"{safe_filename}.json")
    
    # Check if this is the active document, if so, delete it from store
    current_doc_path = os.path.join(data_dir, "document_store.json")
    if os.path.exists(current_doc_path):
        try:
            with open(current_doc_path, "r", encoding="utf-8") as f:
                curr = json.load(f)
            if curr.get("filename") == request.filename:
                os.remove(current_doc_path)
        except Exception:
            pass

    if os.path.exists(target_path):
        try:
            os.remove(target_path)
            return {"status": "success", "message": "Đã xoá tài liệu thành công"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Không thể xoá tài liệu: {str(e)}")
    return {"status": "success", "message": "Tài liệu không tồn tại trên máy chủ."}


@app.post("/api/document/upload")
async def upload_document(file: UploadFile = File(...)):
    # Create temp file
    temp_dir = os.path.join(os.path.dirname(__file__), "temp")
    os.makedirs(temp_dir, exist_ok=True)
    temp_path = os.path.join(temp_dir, file.filename)
    
    try:
        # Save upload file
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # Parse & analyze using meeting service
        result = await process_and_analyze_document(temp_path, file.filename)
        return {"status": "success", "data": result["analysis"]}
    except Exception as e:
        logger.exception("Failed to process uploaded file")
        raise HTTPException(status_code=500, detail=f"Lỗi xử lý file: {str(e)}")
    finally:
        # Clean up temp file
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


@app.get("/api/document/current")
def get_current_doc_endpoint():
    doc = get_current_document()
    if not doc:
        return {"status": "empty", "message": "Không có tài liệu nào"}
    return {"status": "success", "data": doc}


@app.post("/api/document/chat")
async def document_chat_endpoint(request: MeetingChatRequest):
    try:
        result = await answer_document_question(request.message, request.history)
        return result
    except Exception as e:
        logger.exception("Failed in document chat Q&A")
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
