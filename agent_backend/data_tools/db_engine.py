"""
agent_backend/data_tools/db_engine.py

SQLite FTS5 engine — universal schema-agnostic search engine.

Tư duy:
- Không hardcode tên cột hay tên bảng
- Index TẤT CẢ giá trị string + số từ MỌI bảng vào 1 FTS virtual table
- Tự động rebuild khi unified_db.json thay đổi (mtime check)
- Thread-safe rebuild (lock), multi-reader safe (SQLite WAL mode)
- Lưu cả bản ASCII không dấu → tìm kiếm linh hoạt (duy = dúy = dùy)
"""

import sqlite3
import json
import os
import unicodedata
import threading

# ─── Paths ──────────────────────────────────────────────────────────────────
_BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "mock_crm"))
UNIFIED_DB_PATH = os.path.join(_BASE, "unified_db.json")
SQLITE_DB_PATH  = os.path.join(_BASE, "unified_db.sqlite")

# ─── Cache state ─────────────────────────────────────────────────────────────
_rebuild_lock = threading.Lock()
_cache = {"mtime": -1.0, "total_records": 0, "total_tables": 0}


# ─── Helpers ─────────────────────────────────────────────────────────────────

def strip_diacritics(text: str) -> str:
    """'Lê Khánh Duy' → 'Le Khanh Duy'  (dùng cho fallback search)"""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def record_to_search_text(record: dict) -> str:
    """
    Trích xuất toàn bộ nội dung có thể tìm kiếm từ 1 record,
    bất kể cấu trúc lồng nhau hay tên cột.
    Lưu cả bản gốc (có dấu) + bản ASCII (không dấu).
    """
    parts: list[str] = []

    def extract(obj):
        if isinstance(obj, str) and obj.strip():
            s = obj.strip()
            parts.append(s)
            ascii_ver = strip_diacritics(s)
            if ascii_ver != s:
                parts.append(ascii_ver)          # VD: "Huy" → thêm "Huy" (đã same, skip)
        elif isinstance(obj, (int, float)) and obj == obj:  # skip NaN
            parts.append(str(obj))               # Lưu số → tìm "10000000000" được
        elif isinstance(obj, dict):
            for v in obj.values():
                extract(v)
        elif isinstance(obj, list):
            for item in obj:
                extract(item)

    extract(record)
    return " ".join(parts)


def get_primary_id(record: dict) -> str:
    """Heuristic: tìm field ID chính của record (bất kỳ schema)."""
    id_hints = ["_id", "id_", "_code", "_no", "_num", "_ma", "ma_"]
    for k, v in record.items():
        if isinstance(v, str) and any(h in k.lower() for h in id_hints):
            return v
    # Fallback: giá trị string đầu tiên
    for v in record.values():
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


# ─── Index Builder ───────────────────────────────────────────────────────────

def rebuild_index() -> dict:
    """
    Đọc unified_db.json và build SQLite FTS5 index.
    Trả về stats: {total_records, total_tables}.
    """
    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")   # cho phép multi-reader
    conn.execute("PRAGMA synchronous=NORMAL") # faster writes
    cur = conn.cursor()

    # FTS5 virtual table — search_text là cột được index
    cur.execute("DROP TABLE IF EXISTS fts_records")
    cur.execute("""
        CREATE VIRTUAL TABLE fts_records USING fts5(
            table_name   UNINDEXED,
            record_id    UNINDEXED,
            record_json  UNINDEXED,
            search_text,
            tokenize = 'unicode61 remove_diacritics 0'
        )
    """)

    # Schema info table — để show DB overview cho LLM
    cur.execute("DROP TABLE IF EXISTS db_schema")
    cur.execute("""
        CREATE TABLE db_schema (
            table_name   TEXT PRIMARY KEY,
            record_count INTEGER,
            field_names  TEXT,   -- JSON array of field names
            sample_json  TEXT    -- 1 record mẫu
        )
    """)

    # ─── Load và index ──────────────────────────────────────────────────────
    try:
        with open(UNIFIED_DB_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        conn.close()
        return {"total_records": 0, "total_tables": 0, "error": str(e)}

    fts_batch:    list[tuple] = []
    schema_batch: list[tuple] = []

    def index_table(table_name: str, records: list):
        if not records:
            return
        count = 0
        for rec in records:
            if not isinstance(rec, dict):
                continue
            search_text = record_to_search_text(rec)
            rec_id      = get_primary_id(rec)
            rec_json    = json.dumps(rec, ensure_ascii=False)
            fts_batch.append((table_name, rec_id, rec_json, search_text))
            count += 1

        sample = records[0] if records else {}
        fields = list(sample.keys()) if isinstance(sample, dict) else []
        schema_batch.append((
            table_name,
            count,
            json.dumps(fields, ensure_ascii=False),
            json.dumps(sample, ensure_ascii=False),
        ))

    if isinstance(data, list):
        index_table("(flat)", data)
    elif isinstance(data, dict):
        # Nếu là cấu trúc lồng như {"metadata": ..., "data": {"customers": [...]}}
        target_dict = data.get("data", data) if isinstance(data.get("data"), dict) else data
        for tbl, rows in target_dict.items():
            if isinstance(rows, list):
                index_table(tbl, rows)

    # Bulk insert
    cur.executemany("INSERT INTO fts_records VALUES (?,?,?,?)", fts_batch)
    cur.executemany("INSERT OR REPLACE INTO db_schema VALUES (?,?,?,?)", schema_batch)
    conn.commit()
    conn.close()

    return {"total_records": len(fts_batch), "total_tables": len(schema_batch)}


# ─── Public API ──────────────────────────────────────────────────────────────

def ensure_index() -> dict:
    """
    Kiểm tra mtime của unified_db.json.
    Nếu thay đổi → rebuild index (thread-safe).
    Trả về cache stats.
    """
    try:
        mtime = os.path.getmtime(UNIFIED_DB_PATH)
    except FileNotFoundError:
        mtime = -1.0

    if mtime != _cache["mtime"]:
        with _rebuild_lock:
            if mtime != _cache["mtime"]:  # double-check inside lock
                stats = rebuild_index()
                _cache["mtime"]         = mtime
                _cache["total_records"] = stats.get("total_records", 0)
                _cache["total_tables"]  = stats.get("total_tables", 0)

    return _cache.copy()


def new_conn() -> sqlite3.Connection:
    """Mở connection mới đến SQLite DB (lightweight, safe for concurrent reads)."""
    ensure_index()
    conn = sqlite3.connect(SQLITE_DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn
