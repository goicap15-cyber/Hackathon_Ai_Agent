"""
agent_backend/agent_loop.py

True AI Agent với Tool Use / Function Calling.
LLM tự quyết định gọi tool nào — không có heuristic code.

Flow:
  User message → LLM (với tools) → tool call → execute → kết quả → LLM → trả lời

Supports (theo thứ tự ưu tiên):
  - 9Flare Claude API (primary) — OpenAI-compatible
  - Gemini native function calling (fallback 1)
  - Claude qua Beeknoee proxy (fallback 2)
  - OpenRouter với structured JSON output (fallback 3)
"""

import os
import json
import asyncio
import httpx
import google.generativeai as genai
from google.generativeai import protos
from dotenv import load_dotenv

from agent_backend.data_tools import (
    tool_search_text,
    tool_search_id,
    tool_get_db_stats,
    tool_get_schema,
)
from agent_backend.data_tools.db_engine import ensure_index
from agent_backend.security.rbac import mask_records, mask_record

load_dotenv()
GEMINI_API_KEY      = os.getenv("GEMINI_API_KEY")
OPENROUTER_API_KEY  = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL    = os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-chat-v3-0324:free")
ANTHROPIC_API_KEY   = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_BASE_URL  = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/")
ANTHROPIC_MODEL     = os.getenv("ANTHROPIC_MODEL", "claude-opus-4-5")
# 9Flare — ưu tiên số 1
FLARE_API_KEY       = os.getenv("FLARE_API_KEY")
FLARE_BASE_URL      = os.getenv("FLARE_BASE_URL", "https://9flare.com/api/v1").rstrip("/")
FLARE_MODEL         = os.getenv("FLARE_MODEL", "pro/claude-sonnet-4-5")

# Giới hạn số vòng lặp tool multi-turn cho mỗi agent
MAX_TOOL_ITERATIONS = int(os.getenv('MAX_TOOL_ITERATIONS', '6'))

# Thông báo khi chạm giới hạn số vòng lặp tool
_LIMIT_REACHED_MSG = (
    "Yêu cầu của bạn khá phức tạp và cần nhiều bước xử lý hơn mức cho phép. "
    "Vui lòng chia nhỏ câu hỏi thành các phần đơn giản hơn để tôi có thể hỗ trợ bạn tốt hơn."
)

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# ─── System prompt ───────────────────────────────────────────────────────────
AGENT_SYSTEM_PROMPT = """\
Bạn là chuyên viên AI hỗ trợ tra cứu và phân tích dữ liệu doanh nghiệp.
Bạn có quyền truy cập vào cơ sở dữ liệu thông qua các công cụ tìm kiếm.

NGUYÊN TẮC:
- Luôn dùng công cụ để tìm thông tin trước khi trả lời.
- Trả lời bằng tiếng Việt tự nhiên như một chuyên viên tư vấn.
- KHÔNG dùng thuật ngữ kỹ thuật: không JSON, field, schema, null, array, object.
- KHÔNG hiển thị code hay dấu ngoặc kỹ thuật.
- Nếu tìm thấy nhiều người cùng tên: liệt kê ngắn gọn và hỏi lại.
- Nếu không tìm thấy: thông báo lịch sự và gợi ý cách tìm khác.
- Chỉ dùng thông tin từ kết quả công cụ, không bịa đặt.
"""

# ─── Tool definitions ────────────────────────────────────────────────────────
GEMINI_TOOLS = [
    protos. Tool(function_declarations=[
        protos. FunctionDeclaration(
            name="search_records",
            description=(
                "Tìm kiếm bất kỳ bản ghi nào trong cơ sở dữ liệu theo tên người, "
                "từ khóa, địa điểm, sản phẩm, hoặc bất kỳ giá trị nào. "
                "Dùng khi user hỏi về một người, sự kiện, giao dịch, sản phẩm..."
            ),
            parameters=protos. Schema(
                type=protos. Type. OBJECT,
                properties={
                    "query": protos. Schema(
                        type=protos. Type. STRING,
                        description="Từ khóa tìm kiếm. VD: 'Lê Khánh Huy', 'CUS_000514', 'vay mua nhà', 'Hà Nội'"
                    ),
                    "limit": protos. Schema(
                        type=protos. Type. INTEGER,
                        description="Số kết quả tối đa trả về (mặc định 20)"
                    ),
                },
                required=["query"]
            )
        ),
        protos. FunctionDeclaration(
            name="lookup_by_id",
            description=(
                "Tra cứu bản ghi theo mã ID chính xác. "
                "Dùng khi user cung cấp mã cụ thể như CUS_001, EVT_003, INT_004..."
            ),
            parameters=protos. Schema(
                type=protos. Type. OBJECT,
                properties={
                    "id": protos. Schema(
                        type=protos. Type. STRING,
                        description="Mã ID cần tra cứu. VD: CUS_000514, EVT_003933"
                    ),
                },
                required=["id"]
            )
        ),
        protos. FunctionDeclaration(
            name="get_database_overview",
            description=(
                "Xem tổng quan cơ sở dữ liệu: có bao nhiêu bảng, bảng nào, bao nhiêu bản ghi, "
                "các cột có trong dữ liệu. Dùng khi user hỏi về cấu trúc dữ liệu hoặc muốn biết "
                "hệ thống có thể hỗ trợ gì."
            ),
            parameters=protos. Schema(
                type=protos. Type. OBJECT,
                properties={}
            )
        ),
    ])
]

# ─── Tool executor ───────────────────────────────────────────────────────────
def execute_tool(tool_name: str, tool_args: dict, role: str = 'auditor') -> str:
    """Thực thi tool call và trả về kết quả dạng string."""
    try:
        if tool_name == "search_records":
            query = tool_args.get("query", "").strip()
            limit = int(tool_args.get("limit", 20))
            if not query:
                return "Vui lòng cung cấp từ khóa tìm kiếm."
            result = tool_search_text(query, limit=limit)
            if result["total_found"] == 0:
                return f"Không tìm thấy bản ghi nào khớp với '{query}' trong cơ sở dữ liệu."
            records = [r["record"] for r in result["results"]]
            records = mask_records(records, role)
            return json.dumps({
                "total_found": result["total_found"],
                "records": records
            }, ensure_ascii=False, indent=2)

        elif tool_name == "lookup_by_id":
            id_val = tool_args.get("id", "").strip()
            if not id_val:
                return "Vui lòng cung cấp mã ID cần tra cứu."
            result = tool_search_id(id_val)
            if not result["found"]:
                return f"Không tìm thấy bản ghi với mã '{id_val}'."
            return json.dumps(mask_record(result["record"], role), ensure_ascii=False, indent=2)

        elif tool_name == "get_database_overview":
            schema = tool_get_schema(top_n=10)
            overview = {
                "total_records": schema["total_records"],
                "total_tables": schema["total_tables"],
                "tables": [
                    {
                        "name": t["table"],
                        "record_count": t["count"],
                        "fields": t["fields"][:8]
                    }
                    for t in schema["tables"]
                ]
            }
            return json.dumps(overview, ensure_ascii=False, indent=2)

        return f"Tool '{tool_name}' không tồn tại."
    except Exception as e:
        return f"Lỗi khi thực thi tool {tool_name}: {str(e)}"


# ─── Gemini Agent (primary) ──────────────────────────────────────────────────
async def _run_gemini_agent(
    user_message: str,
    context_hint: str = "",
    max_iters: int = MAX_TOOL_ITERATIONS
) -> tuple[str, list[str]]:
    """
    Agent loop dùng Gemini function calling.
    Trả về (response_text, trace_logs).
    """
    trace_logs: list[str] = []

    system_prompt = AGENT_SYSTEM_PROMPT
    if context_hint:
        system_prompt += f"\nNGỮ CẢNH HỘI THOẠI TRƯỚC:\n{context_hint}"

    agent_model = genai. GenerativeModel(
        model_name="gemini-2.0-flash",
        system_instruction=system_prompt,
        tools=GEMINI_TOOLS,
        generation_config={"temperature": 0.3}
    )

    # Khởi tạo messages
    messages: list = [{"role": "user", "parts": [user_message]}]

    for iteration in range(max_iters):
        response = await asyncio.to_thread(
            agent_model.generate_content, messages
        )

        # Kiểm tra function calls trong response
        tool_calls = []
        text_parts = []
        for part in response.candidates[0].content.parts:
            if part.function_call and part.function_call.name:
                tool_calls.append(part.function_call)
            elif hasattr(part, "text") and part.text:
                text_parts.append(part.text)

        if not tool_calls:
            # LLM đưa ra câu trả lời cuối
            final_text = " ".join(text_parts) or response.text
            trace_logs.append(f"✅ Gemini agent hoàn thành sau {iteration + 1} vòng")
            return final_text, trace_logs

        # Có tool calls — thực thi từng tool
        # Thêm model turn vào messages
        messages.append(response.candidates[0].content)

        # Thực thi tools và build response parts
        function_response_parts = []
        for fc in tool_calls:
            tool_name = fc.name
            tool_args = dict(fc.args) if fc.args else {}
            trace_logs.append(f"🔧 Tool: {tool_name}({json.dumps(tool_args, ensure_ascii=False)})")

            result = execute_tool(tool_name, tool_args, role='auditor')
            trace_logs.append(f"📊 Kết quả: {result[:150]}...")

            function_response_parts.append(
                protos. Part(
                    function_response=protos. FunctionResponse(
                        name=tool_name,
                        response={"result": result}
                    )
                )
            )

        # Gửi kết quả tool về cho LLM
        messages.append(protos. Content(parts=function_response_parts, role="user"))

    # Chạm giới hạn số vòng lặp tool
    trace_logs.append(f"⚠️ Gemini agent đạt giới hạn {max_iters} vòng lặp tool")
    return _LIMIT_REACHED_MSG, trace_logs


# ─── OpenRouter Fallback Agent (structured JSON) ─────────────────────────────
async def _run_openrouter_agent(
    user_message: str,
    context_hint: str = "",
    max_iters: int = MAX_TOOL_ITERATIONS
) -> tuple[str, list[str]]:
    """
    Fallback agent dùng OpenRouter với structured JSON approach.
    Works với bất kỳ LLM nào (không cần function calling support).
    """
    trace_logs: list[str] = []

    system_prompt = (
        AGENT_SYSTEM_PROMPT + "\n\n"
        "CÁCH DÙNG TOOLS:\n"
        "Khi cần tìm thông tin, BẮT BUỘC output ĐÚNG định dạng JSON sau (không thêm gì khác):\n"
        "{\"tool\": \"search_records\", \"args\": {\"query\": \"tên hoặc từ khóa\"}}\n"
        "hoặc: {\"tool\": \"lookup_by_id\", \"args\": {\"id\": \"mã ID\"}}\n"
        "hoặc: {\"tool\": \"get_database_overview\", \"args\": {}}\n\n"
        "Sau khi nhận kết quả tool, trả lời bình thường bằng tiếng Việt.\n"
        "Nếu đã có đủ thông tin, trả lời ngay không cần gọi tool."
    )
    if context_hint:
        system_prompt += f"\n\nNGỮ CẢNH TRƯỚC:\n{context_hint}"

    conversation = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://127.0.0.1:8000",
        "X-Title": "CRM AI Agent"
    }

    async with httpx. AsyncClient(timeout=60.0) as client:
        for iteration in range(max_iters):
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                json={"model": OPENROUTER_MODEL, "messages": conversation},
                headers=headers
            )
            if resp.status_code != 200:
                trace_logs.append(f"⚠️ OpenRouter error {resp.status_code}: {resp.text[:200]}")
                break

            resp_json = resp.json()
            # Kiểm tra response hợp lệ trước khi parse
            if "choices" not in resp_json or not resp_json["choices"]:
                err_msg = resp_json.get("error", {}).get("message", str(resp_json))
                trace_logs.append(f"⚠️ OpenRouter response không hợp lệ: {err_msg[:200]}")
                break
            choice_msg = resp_json["choices"][0].get("message", {})
            content = (choice_msg.get("content") or "").strip()
            if not content:
                trace_logs.append("⚠️ OpenRouter trả về content rỗng, dừng.")
                break
            trace_logs.append(f"🤖 LLM [{iteration+1}]: {content[:200]}")

            # Thử parse tool call từ JSON
            tool_call = None
            # Tìm JSON block trong response
            start = content.find("{")
            end   = content.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    candidate = json.loads(content[start:end])
                    if "tool" in candidate and "args" in candidate:
                        tool_call = candidate
                except json. JSONDecodeError:
                    pass

            if not tool_call:
                # Không có tool call → đây là câu trả lời cuối
                trace_logs.append(f"✅ OpenRouter agent hoàn thành sau {iteration + 1} vòng")
                return content, trace_logs

            # Thực thi tool
            tool_name = tool_call["tool"]
            tool_args = tool_call.get("args", {})
            trace_logs.append(f"🔧 Tool: {tool_name}({json.dumps(tool_args, ensure_ascii=False)})")

            result = execute_tool(tool_name, tool_args, role='auditor')
            trace_logs.append(f"📊 Kết quả: {result[:150]}...")

            # Thêm vào conversation
            conversation.append({"role": "assistant", "content": content})
            conversation.append({
                "role": "user",
                "content": f"Kết quả từ tool {tool_name}:\n{result}\n\nBây giờ hãy trả lời câu hỏi của người dùng."
            })
        else:
            # Chạm giới hạn số vòng lặp tool (loop kết thúc mà không break)
            trace_logs.append(f"⚠️ OpenRouter agent đạt giới hạn {max_iters} vòng lặp tool")
            return _LIMIT_REACHED_MSG, trace_logs

    return "Xin lỗi, không thể xử lý yêu cầu.", trace_logs


# ─── Claude Agent qua Beeknoee Proxy (OpenAI-compatible) ─────────────────
async def _run_claude_agent(
    user_message: str,
    context_hint: str = "",
    max_iters: int = MAX_TOOL_ITERATIONS
) -> tuple[str, list[str]]:
    """
    Agent dùng Claude qua Beeknoee proxy (OpenAI-compatible format).
    Endpoint: ANTHROPIC_BASE_URL/v1/chat/completions
    """
    trace_logs: list[str] = []

    system_prompt = AGENT_SYSTEM_PROMPT
    if context_hint:
        system_prompt += f"\nNGỮ CẢNH HỘI THOẠI TRƯỚC:\n{context_hint}"

    # Định nghĩa tools theo chuẩn OpenAI function calling
    openai_tools = [
        {
            "type": "function",
            "function": {
                "name": "search_records",
                "description": (
                    "Tìm kiếm bất kỳ bản ghi nào trong cơ sở dữ liệu theo tên người, "
                    "từ khóa, địa điểm, sản phẩm, hoặc bất kỳ giá trị nào."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Từ khóa tìm kiếm. VD: 'Lê Văn Khang', 'KH001', 'vay mua nhà'"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Số kết quả tối đa trả về (mặc định 20)"
                        }
                    },
                    "required": ["query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "lookup_by_id",
                "description": "Tra cứu bản ghi theo mã ID chính xác. VD: KH001, OPP002, INT003",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "string",
                            "description": "Mã ID cần tra cứu"
                        }
                    },
                    "required": ["id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_database_overview",
                "description": "Xem tổng quan cơ sở dữ liệu: bảng nào, bao nhiêu bản ghi.",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            }
        }
    ]

    headers = {
        "Authorization": f"Bearer {ANTHROPIC_API_KEY}",
        "Content-Type": "application/json",
    }

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_message},
    ]

    async with httpx. AsyncClient(timeout=60.0) as client:
        for iteration in range(max_iters):
            payload = {
                "model": ANTHROPIC_MODEL,
                "messages": messages,
                "tools": openai_tools,
                "max_tokens": 2048,
            }

            resp = await client.post(
                f"{ANTHROPIC_BASE_URL}/v1/chat/completions",
                json=payload,
                headers=headers
            )

            if resp.status_code == 401:
                raise ValueError("Claude/Beeknoee 401: key không hợp lệ")

            if resp.status_code != 200:
                trace_logs.append(f"⚠️ Beeknoee error {resp.status_code}: {resp.text[:200]}")
                break

            data     = resp.json()
            choice   = data["choices"][0]
            message  = choice["message"]
            finish   = choice.get("finish_reason", "")

            tool_calls = message.get("tool_calls") or []

            if not tool_calls or finish == "stop":
                final_text = message.get("content", "") or ""
                trace_logs.append(f"✅ Claude/Beeknoee agent hoàn thành sau {iteration + 1} vòng")
                return final_text.strip(), trace_logs

            # Có tool calls — thực thi
            messages.append(message)

            for tc in tool_calls:
                tool_name = tc["function"]["name"]
                try:
                    tool_args = json.loads(tc["function"].get("arguments", "{}"))
                except json. JSONDecodeError:
                    tool_args = {}

                trace_logs.append(f"🔧 Tool: {tool_name}({json.dumps(tool_args, ensure_ascii=False)})")
                result = execute_tool(tool_name, tool_args, role='auditor')
                trace_logs.append(f"📊 Kết quả: {result[:150]}...")

                messages.append({
                    "role":         "tool",
                    "tool_call_id": tc["id"],
                    "content":      result
                })
        else:
            # Chạm giới hạn số vòng lặp tool (loop kết thúc mà không break)
            trace_logs.append(f"⚠️ Claude/Beeknoee agent đạt giới hạn {max_iters} vòng lặp tool")
            return _LIMIT_REACHED_MSG, trace_logs

    return "Xin lỗi, Claude/Beeknoee không thể xử lý yêu cầu.", trace_logs


# ─── 9Flare Agent (OpenAI-compatible, ưu tiên số 1) ─────────────────────────────
async def _run_flare_agent(
    user_message: str,
    context_hint: str = "",
    max_iters: int = MAX_TOOL_ITERATIONS
) -> tuple[str, list[str]]:
    """
    Agent dùng 9Flare Claude API (OpenAI-compatible format).
    Endpoint: FLARE_BASE_URL/chat/completions
    """
    trace_logs: list[str] = []

    system_prompt = AGENT_SYSTEM_PROMPT
    if context_hint:
        system_prompt += f"\nNGỮ CẢNH HỘI THOẠI TRƯỚC:\n{context_hint}"

    # Tool definitions theo chuẩn OpenAI function calling
    openai_tools = [
        {
            "type": "function",
            "function": {
                "name": "search_records",
                "description": (
                    "Tìm kiếm bất kỳ bản ghi nào trong cơ sở dữ liệu theo tên người, "
                    "từ khóa, địa điểm, sản phẩm, hoặc bất kỳ giá trị nào."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Từ khóa tìm kiếm. VD: 'Lê Văn Khang', 'KH001', 'vay mua nhà'"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Số kết quả tối đa trả về (mặc định 20)"
                        }
                    },
                    "required": ["query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "lookup_by_id",
                "description": "Tra cứu bản ghi theo mã ID chính xác. VD: CUS_001, EVT_003, INT_004",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "string",
                            "description": "Mã ID cần tra cứu"
                        }
                    },
                    "required": ["id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_database_overview",
                "description": "Xem tổng quan cơ sở dữ liệu: bảng nào, bao nhiêu bản ghi.",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            }
        }
    ]

    headers = {
        "Authorization": f"Bearer {FLARE_API_KEY}",
        "Content-Type": "application/json",
    }

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_message},
    ]

    async with httpx. AsyncClient(timeout=60.0) as client:
        for iteration in range(max_iters):
            payload = {
                "model": FLARE_MODEL,
                "messages": messages,
                "tools": openai_tools,
                "max_tokens": 2048,
            }

            resp = await client.post(
                f"{FLARE_BASE_URL}/chat/completions",
                json=payload,
                headers=headers
            )

            if resp.status_code == 401:
                raise ValueError("9Flare 401: API key không hợp lệ")

            if resp.status_code != 200:
                trace_logs.append(f"⚠️ 9Flare error {resp.status_code}: {resp.text[:200]}")
                break

            data    = resp.json()
            if "choices" not in data or not data["choices"]:
                err_msg = data.get("error", {}).get("message", str(data))
                trace_logs.append(f"⚠️ 9Flare response không hợp lệ: {err_msg[:200]}")
                break

            choice  = data["choices"][0]
            message = choice["message"]
            finish  = choice.get("finish_reason", "")

            tool_calls = message.get("tool_calls") or []

            if not tool_calls or finish == "stop":
                final_text = message.get("content", "") or ""
                trace_logs.append(f"✅ 9Flare agent hoàn thành sau {iteration + 1} vòng")
                return final_text.strip(), trace_logs

            # Có tool calls — thực thi
            messages.append(message)

            for tc in tool_calls:
                tool_name = tc["function"]["name"]
                try:
                    tool_args = json.loads(tc["function"].get("arguments", "{}"))
                except json. JSONDecodeError:
                    tool_args = {}

                trace_logs.append(f"🔧 Tool: {tool_name}({json.dumps(tool_args, ensure_ascii=False)})")
                result = execute_tool(tool_name, tool_args, role='auditor')
                trace_logs.append(f"📊 Kết quả: {result[:150]}...")

                messages.append({
                    "role":         "tool",
                    "tool_call_id": tc["id"],
                    "content":      result
                })
        else:
            # Chạm giới hạn số vòng lặp tool (loop kết thúc mà không break)
            trace_logs.append(f"⚠️ 9Flare agent đạt giới hạn {max_iters} vòng lặp tool")
            return _LIMIT_REACHED_MSG, trace_logs

    return "Xin lỗi, 9Flare không thể xử lý yêu cầu.", trace_logs


# ─── Public API ───────────────────────────────────────────────────────────────
async def run_agent(
    user_message: str,
    prev_customer_id: str = "",
    rm_name: str = ""
) -> dict:
    """
    Entry point chính cho chat_endpoint.
    Tự động chọn Gemini (function calling) hoặc OpenRouter (structured JSON).

    Returns:
        {
            "response": str,
            "trace_logs": list[str],
            "tool_called": str,
            "matched_customer_id": str,
            "action_required": str | None
        }
    """
    # Đảm bảo FTS index đã sẵn sàng
    db_stats = ensure_index()
    trace_logs: list[str] = [
        f"SQLite FTS: {db_stats['total_records']:,} records / {db_stats['total_tables']} tables"
    ]

    # Ngữ cảnh cuộc hội thoại trước (nếu có)
    context_hint = ""
    if prev_customer_id and prev_customer_id != "N/A":
        context_hint = f"Cuộc hội thoại trước đang nói về bản ghi có mã: {prev_customer_id}"

    # Chạy agent theo thứ tự ưu tiên
    response_text = ""
    agent_trace:  list[str] = []

    # ★ Ưu tiên 1: 9Flare Claude API
    if FLARE_API_KEY:
        try:
            response_text, agent_trace = await _run_flare_agent(
                user_message, context_hint
            )
            trace_logs.append(f"✅ Engine: 9Flare ({FLARE_MODEL})")
        except Exception as e:
            trace_logs.append(f"⚠️ 9Flare agent lỗi: {e} — thử Gemini")

    # ★ Dự phòng 2: Gemini Function Calling
    if not response_text and GEMINI_API_KEY:
        try:
            response_text, agent_trace = await _run_gemini_agent(
                user_message, context_hint
            )
            trace_logs.append("✅ Engine: Gemini Function Calling")
        except Exception as e:
            trace_logs.append(f"⚠️ Gemini agent lỗi: {e} — thử Beeknoee")

    # ★ Dự phòng 3: Beeknoee/Claude proxy
    if not response_text and ANTHROPIC_API_KEY:
        try:
            response_text, agent_trace = await _run_claude_agent(
                user_message, context_hint
            )
            trace_logs.append("✅ Engine: Claude (Beeknoee) Tool Use")
        except Exception as e:
            trace_logs.append(f"⚠️ Claude agent lỗi: {e} — thử OpenRouter")

    # ★ Dự phòng 4: OpenRouter
    if not response_text and OPENROUTER_API_KEY:
        try:
            response_text, agent_trace = await _run_openrouter_agent(
                user_message, context_hint
            )
            trace_logs.append("✅ Engine: OpenRouter Structured JSON")
        except Exception as e:
            trace_logs.append(f"⚠️ OpenRouter agent lỗi: {e}")

    if not response_text:
        response_text = "Hệ thống tạm thời không khả dụng. Vui lòng thử lại sau."

    trace_logs.extend(agent_trace)

    # Xác định action_required từ response
    msg_lower = user_message.lower()
    action_required = (
        "email" if any(k in msg_lower for k in ["soạn", "email", "thư", "mail"])
        else "call" if any(k in msg_lower for k in ["gọi", "script", "kịch bản", "call"])
        else None
    )

    return {
        "response":             response_text,
        "trace_logs":           trace_logs,
        "tool_called":          "agent",
        "matched_customer_id":  prev_customer_id or "N/A",
        "action_required":      action_required,
    }
