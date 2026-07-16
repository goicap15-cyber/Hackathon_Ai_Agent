"""
agent_backend/data_tools/tool_search.py

4 tools chuyên biệt — bot chính gọi vào đây để tìm data.

Tool 1: tool_search_id     → tìm theo ID chính xác (O(1))
Tool 2: tool_search_text   → FTS full-text, trả TẤT CẢ kết quả match
Tool 3: tool_get_schema    → xem cấu trúc DB (bảng nào, cột nào, bao nhiêu records)
Tool 4: tool_get_db_stats  → tóm tắt ngắn gọn cho LLM context
"""

import json
import unicodedata
from .db_engine import new_conn, strip_diacritics, _cache


# ─── FTS query builder ───────────────────────────────────────────────────────

def _build_fts_query(text: str) -> str:
    """
    Xây dựng FTS5 query an toàn:
    - Wrap từng word trong dấu ngoặc kép để match exact word
    - Bỏ ký tự đặc biệt của FTS5
    VD: 'Lê Khánh Duy' → '"Lê" "Khánh" "Duy"'
    """
    fts_special = set('*^"()OR AND NOT')
    cleaned = "".join(c if c not in fts_special else " " for c in text)
    words = [w for w in cleaned.split() if w and len(w) >= 2]
    if not words:
        return '""'
    return " ".join(f'"{w}"' for w in words)


# ─── Tool 1: ID Search ───────────────────────────────────────────────────────

def tool_search_id(id_value: str) -> dict:
    """
    Tìm record theo ID chính xác.
    Thử theo thứ tự:
      1. Match exact trên record_id column
      2. FTS match toàn bộ id_value (bắt các ID nằm trong fields khác)
    
    Returns:
        {"found": bool, "table": str, "record": dict, "trace": str}
    """
    conn = new_conn()
    cur  = conn.cursor()
    clean_id = id_value.strip()

    # Bước 1: exact match trên record_id
    cur.execute("""
        SELECT table_name, record_id, record_json
        FROM fts_records WHERE record_id = ? LIMIT 1
    """, (clean_id,))
    row = cur.fetchone()

    if not row:
        # Bước 2: FTS search (ID có thể nằm trong field không phải record_id)
        fts_q = f'"{clean_id}"'
        try:
            cur.execute("""
                SELECT table_name, record_id, record_json
                FROM fts_records WHERE search_text MATCH ? LIMIT 1
            """, (fts_q,))
            row = cur.fetchone()
        except Exception:
            row = None

    conn.close()

    if row:
        return {
            "found":  True,
            "table":  row["table_name"],
            "id":     row["record_id"],
            "record": json.loads(row["record_json"]),
            "trace":  f"ID match: '{clean_id}' in table '{row['table_name']}'"
        }
    return {"found": False, "table": None, "id": None, "record": None,
            "trace": f"ID '{clean_id}' not found"}


# ─── Tool 2: Full-Text Search ────────────────────────────────────────────────

def tool_search_text(query: str, limit: int = 20, table_filter: str = None) -> dict:
    """
    FTS full-text search — tìm TẤT CẢ records chứa từ/cụm trong query.
    Hoạt động với mọi cột, mọi bảng, không khai báo schema.

    Chiến lược 3 tầng:
      1. FTS MATCH toàn cụm (chính xác nhất)
      2. Nếu không có → FTS MATCH bản không dấu
      3. Nếu vẫn không có → FTS MATCH từng từ riêng lẻ (rộng nhất)

    Args:
        query:        Chuỗi tìm kiếm tự nhiên ('Lê Khánh Duy', 'nợ 10 tỷ'...)
        limit:        Số kết quả tối đa (default 20)
        table_filter: Giới hạn trong 1 bảng cụ thể (optional)

    Returns:
        {"query", "strategy_used", "total_found", "results": [{"table","id","record"}]}
    """
    conn = new_conn()
    cur  = conn.cursor()

    def _run(fts_q: str):
        try:
            if table_filter:
                cur.execute("""
                    SELECT table_name, record_id, record_json, rank
                    FROM fts_records
                    WHERE search_text MATCH ? AND table_name = ?
                    ORDER BY rank LIMIT ?
                """, (fts_q, table_filter, limit))
            else:
                cur.execute("""
                    SELECT table_name, record_id, record_json, rank
                    FROM fts_records
                    WHERE search_text MATCH ?
                    ORDER BY rank LIMIT ?
                """, (fts_q, limit))
            return cur.fetchall()
        except Exception:
            return []

    results = []
    strategy = ""

    # Tầng 1: exact phrase
    fts_full = _build_fts_query(query)
    rows = _run(fts_full)
    if rows:
        strategy = "exact_phrase"
        results = rows
    else:
        # Tầng 2: không dấu
        ascii_q = strip_diacritics(query)
        fts_ascii = _build_fts_query(ascii_q)
        if fts_ascii != fts_full:
            rows = _run(fts_ascii)
            if rows:
                strategy = "ascii_fallback"
                results = rows

    if not results:
        # Tầng 3: OR giữa các từ (rộng nhất, ưu tiên kết quả có nhiều từ match)
        words = [w for w in query.split() if len(w) >= 2]
        if words:
            fts_or = " OR ".join(f'"{w}"' for w in words)
            rows = _run(fts_or)
            if rows:
                strategy = "any_word"
                results = rows

    conn.close()

    output = []
    for row in results:
        output.append({
            "table":  row["table_name"],
            "id":     row["record_id"],
            "record": json.loads(row["record_json"]),
        })

    return {
        "query":          query,
        "strategy_used":  strategy or "no_match",
        "total_found":    len(output),
        "results":        output,
    }


# ─── Tool 3: Schema Info ─────────────────────────────────────────────────────

def tool_get_schema(top_n: int = 15) -> dict:
    """
    Trả về cấu trúc DB: bảng nào, cột nào, bao nhiêu records, 1 record mẫu.
    Dùng để LLM biết DB có gì khi user hỏi câu tổng quát.
    """
    conn = new_conn()
    cur  = conn.cursor()
    cur.execute("""
        SELECT table_name, record_count, field_names, sample_json
        FROM db_schema ORDER BY record_count DESC LIMIT ?
    """, (top_n,))
    rows = conn.execute("SELECT SUM(record_count), COUNT(*) FROM db_schema").fetchone()
    total_records = rows[0] or 0
    total_tables  = rows[1] or 0
    conn.close()

    tables = []
    for r in cur.fetchall():
        tables.append({
            "table":       r["table_name"],
            "count":       r["record_count"],
            "fields":      json.loads(r["field_names"]),
            "sample":      json.loads(r["sample_json"]),
        })

    return {
        "total_records": total_records,
        "total_tables":  total_tables,
        "tables":        tables,
    }


# ─── Tool 4: DB Stats summary ────────────────────────────────────────────────

def tool_get_db_stats() -> str:
    """
    Tóm tắt ngắn gọn trạng thái DB — dùng làm context header cho LLM.
    VD: 'DB: 237,299 records | 33 bảng | customers(2000), interactions(10000)...'
    """
    stats = _cache
    total_r = stats.get("total_records", 0)
    total_t = stats.get("total_tables",  0)

    if total_r == 0:
        return "DB chưa được load hoặc trống."

    conn = new_conn()
    cur  = conn.cursor()
    cur.execute("""
        SELECT table_name, record_count, field_names
        FROM db_schema ORDER BY record_count DESC LIMIT 8
    """)
    rows = cur.fetchall()
    conn.close()

    table_summaries = []
    for r in rows:
        fields = json.loads(r["field_names"])[:4]
        table_summaries.append(f"{r['table_name']}({r['record_count']:,})[{','.join(fields)}]")

    return (
        f"DB: {total_r:,} records | {total_t} bảng\n"
        + "\n".join(f"  • {s}" for s in table_summaries)
        + (f"\n  ... và {total_t - len(rows)} bảng khác" if total_t > len(rows) else "")
    )
