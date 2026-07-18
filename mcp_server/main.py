# mcp_server/main.py
import asyncio
import json
import os
import mcp.types as types
from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.server.lowlevel.server import NotificationOptions

server = Server("paperless-meetings-mcp")

def _read_current_document():
    path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "agent_backend", "data", "document_store.json"))
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """Expose document processing tools as MCP Tools to the LLM."""
    return [
        types.Tool(
            name="search_in_document",
            description="Tìm kiếm từ khóa hoặc cụm từ trong tài liệu cuộc họp hiện tại. Trả về các phân đoạn văn bản và số trang tương ứng.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Từ khóa hoặc cụm từ cần tìm (ví dụ: 'kinh phí', 'Điện Biên', 'quy hoạch')"
                    }
                },
                "required": ["query"]
            }
        ),
        types.Tool(
            name="get_page_content",
            description="Lấy toàn bộ nội dung chữ của một trang cụ thể trong tài liệu cuộc họp (1-indexed).",
            inputSchema={
                "type": "object",
                "properties": {
                    "page_num": {
                        "type": "integer",
                        "description": "Số trang cần lấy (bắt đầu từ 1)"
                    }
                },
                "required": ["page_num"]
            }
        ),
        types.Tool(
            name="get_terminology_details",
            description="Tra cứu định nghĩa và các trang chứa một thuật ngữ chuyên ngành đã được trích xuất từ tài liệu.",
            inputSchema={
                "type": "object",
                "properties": {
                    "term": {
                        "type": "string",
                        "description": "Thuật ngữ cần tra cứu (ví dụ: 'kinh phí sự nghiệp')"
                    }
                },
                "required": ["term"]
            }
        )
    ]

@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """Execute document search and content retrieval tools."""
    try:
        if name == "search_in_document":
            doc = _read_current_document()
            if not doc:
                return [types.TextContent(type="text", text="Không có tài liệu nào hiện đang được mở.")]
            query = arguments.get("query", "").lower()
            results = []
            for p in doc.get("pages", []):
                if query in p.get("text", "").lower():
                    text = p["text"]
                    idx = text.lower().find(query)
                    start = max(0, idx - 150)
                    end = min(len(text), idx + len(query) + 150)
                    snippet = text[start:end].replace("\n", " ")
                    results.append(f"- [Trang {p['page_num']}]: ... {snippet} ...")
            if not results:
                return [types.TextContent(type="text", text=f"Không tìm thấy kết quả nào chứa '{query}' trong tài liệu.")]
            return [types.TextContent(type="text", text="\n".join(results[:10]))]

        elif name == "get_page_content":
            doc = _read_current_document()
            if not doc:
                return [types.TextContent(type="text", text="Không có tài liệu nào hiện đang được mở.")]
            try:
                page_num = int(arguments.get("page_num", 1))
            except ValueError:
                return [types.TextContent(type="text", text="Số trang không hợp lệ.")]
            for p in doc.get("pages", []):
                if p["page_num"] == page_num:
                    return [types.TextContent(type="text", text=f"--- NỘI DUNG TRANG {page_num} ---\n{p['text']}")]
            return [types.TextContent(type="text", text=f"Không tìm thấy trang {page_num} trong tài liệu.")]

        elif name == "get_terminology_details":
            doc = _read_current_document()
            if not doc:
                return [types.TextContent(type="text", text="Không có tài liệu nào hiện đang được mở.")]
            term = arguments.get("term", "").lower()
            terms_list = doc.get("analysis", {}).get("terminology", [])
            for t in terms_list:
                if t.get("term", "").lower() == term:
                    pages_str = ", ".join(map(str, t.get("pages", [])))
                    return [types.TextContent(type="text", text=f"Thuật ngữ: {t.get('term')}\nĐịnh nghĩa: {t.get('definition')}\nXuất hiện tại trang: {pages_str}")]
            return [types.TextContent(type="text", text=f"Không tìm thấy thuật ngữ '{term}' trong bộ thuật ngữ của tài liệu.")]

        else:
            raise ValueError(f"Không tìm thấy tool: {name}")

    except Exception as e:
        return [types.TextContent(type="text", text=f"Lỗi xử lý MCP Tool: {str(e)}")]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="paperless-meetings-mcp",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    NotificationOptions(tools_changed=True),
                    {}
                )
            )
        )

if __name__ == "__main__":
    asyncio.run(main())
