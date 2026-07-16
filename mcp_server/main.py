# mcp_server/main.py
import asyncio
import httpx
import json
import os
import mcp.types as types
from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.server.lowlevel.server import NotificationOptions

CRM_API_BASE = os.getenv("CRM_API_BASE", "http://127.0.0.1:8001/api")

server = Server("banka-crm-mcp")

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """
    Expose CRM APIs as MCP Tools to the LLM.
    """
    return [
        types.Tool(
            name="get_savings_due_this_week",
            description="Lấy danh sách khách hàng có sổ tiết kiệm sắp đến hạn trong vòng 7 ngày tới để RM liên hệ nhắc nhở.",
            inputSchema={
                "type": "object",
                "properties": {},
            }
        ),
        types.Tool(
            name="get_customer_profile",
            description="Truy vấn thông tin hồ sơ 360 độ của khách hàng theo customer_id bao gồm: thông tin cá nhân, các cơ hội bán hàng (opportunities) và lịch sử tương tác trước (interactions).",
            inputSchema={
                "type": "object",
                "properties": {
                    "customer_id": {
                        "type": "string",
                        "description": "Mã định danh duy nhất của khách hàng (ví dụ: KH001, KH002...)"
                    }
                },
                "required": ["customer_id"]
            }
        ),
        types.Tool(
            name="get_active_campaigns",
            description="Lấy danh sách các chiến dịch marketing đang diễn ra tại Bank A và các sản phẩm mục tiêu đi kèm.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        types.Tool(
            name="log_interaction",
            description="Ghi nhận lịch sử tương tác mới của RM với khách hàng vào CRM sau khi thực hiện cuộc gọi, gửi email hoặc gặp mặt.",
            inputSchema={
                "type": "object",
                "properties": {
                    "customer_id": {"type": "string", "description": "Mã định danh khách hàng"},
                    "interaction_type": {"type": "string", "description": "Hình thức tương tác (Call, Email, Meeting)"},
                    "notes": {"type": "string", "description": "Ghi chú tóm tắt nội dung trao đổi"},
                    "result": {"type": "string", "description": "Kết quả (Completed, Sent, Pending)"},
                    "rm_name": {"type": "string", "description": "Tên Relationship Manager thực hiện"}
                },
                "required": ["customer_id", "interaction_type", "notes", "result", "rm_name"]
            }
        ),
        types.Tool(
            name="save_email_draft",
            description="Lưu bản nháp email chăm sóc khách hàng vào hệ thống CRM.",
            inputSchema={
                "type": "object",
                "properties": {
                    "customer_id": {"type": "string", "description": "Mã định danh khách hàng"},
                    "subject": {"type": "string", "description": "Tiêu đề email"},
                    "body": {"type": "string", "description": "Nội dung email"},
                    "rm_name": {"type": "string", "description": "Tên RM soạn thảo"}
                },
                "required": ["customer_id", "subject", "body", "rm_name"]
            }
        ),
        types.Tool(
            name="save_call_script",
            description="Lưu kịch bản cuộc gọi điện chăm sóc khách hàng vào hệ thống CRM.",
            inputSchema={
                "type": "object",
                "properties": {
                    "customer_id": {"type": "string", "description": "Mã định danh khách hàng"},
                    "script_content": {"type": "string", "description": "Nội dung kịch bản cuộc gọi"},
                    "rm_name": {"type": "string", "description": "Tên RM soạn thảo"}
                },
                "required": ["customer_id", "script_content", "rm_name"]
            }
        ),
        types.Tool(
            name="query_product_knowledge",
            description="Tìm kiếm thông tin chính sách, lãi suất, phí và ưu đãi của các sản phẩm tài chính Bank A (tiết kiệm, cho vay, bảo hiểm liên kết, thẻ...).",
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Danh mục sản phẩm để lọc (ví dụ: Savings, Loans, Insurance, Cards...)"
                    }
                }
            }
        ),
        types.Tool(
            name="get_email_template",
            description="Lấy danh sách các mẫu email hoặc kịch bản cuộc gọi chuẩn của Bank A để tham khảo.",
            inputSchema={
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "description": "Loại mẫu cần lấy (ví dụ: Email, CallScript)"
                    }
                }
            }
        )
    ]

@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """
    Execute tool request and fetch/send data to CRM APIs.
    """
    async with httpx.AsyncClient() as client:
        try:
            if name == "get_savings_due_this_week":
                response = await client.get(f"{CRM_API_BASE}/customers?due_within_days=7")
                response.raise_for_status()
                return [types.TextContent(type="text", text=response.text)]

            elif name == "get_customer_profile":
                customer_id = arguments.get("customer_id")
                if not customer_id:
                    raise ValueError("Thiếu customer_id")
                
                # Fetch profile, opportunities and interactions in parallel
                profile_resp = await client.get(f"{CRM_API_BASE}/customers/{customer_id}")
                opps_resp = await client.get(f"{CRM_API_BASE}/customers/{customer_id}/opportunities")
                ints_resp = await client.get(f"{CRM_API_BASE}/customers/{customer_id}/interactions")
                
                profile_resp.raise_for_status()
                
                profile = profile_resp.json()
                profile["opportunities"] = opps_resp.json() if opps_resp.status_code == 200 else []
                profile["interactions"] = ints_resp.json() if ints_resp.status_code == 200 else []
                
                return [types.TextContent(type="text", text=json.dumps(profile, ensure_ascii=False, indent=2))]

            elif name == "get_active_campaigns":
                response = await client.get(f"{CRM_API_BASE}/campaigns?active_only=true")
                response.raise_for_status()
                return [types.TextContent(type="text", text=response.text)]

            elif name == "log_interaction":
                payload = {
                    "customer_id": arguments.get("customer_id"),
                    "type": arguments.get("interaction_type"),
                    "notes": arguments.get("notes"),
                    "result": arguments.get("result"),
                    "rm_name": arguments.get("rm_name")
                }
                response = await client.post(f"{CRM_API_BASE}/interactions", json=payload)
                response.raise_for_status()
                return [types.TextContent(type="text", text=response.text)]

            elif name == "save_email_draft":
                payload = {
                    "customer_id": arguments.get("customer_id"),
                    "subject": arguments.get("subject"),
                    "body": arguments.get("body"),
                    "rm_name": arguments.get("rm_name")
                }
                response = await client.post(f"{CRM_API_BASE}/draft-email", json=payload)
                response.raise_for_status()
                return [types.TextContent(type="text", text=response.text)]

            elif name == "save_call_script":
                payload = {
                    "customer_id": arguments.get("customer_id"),
                    "script_content": arguments.get("script_content"),
                    "rm_name": arguments.get("rm_name")
                }
                response = await client.post(f"{CRM_API_BASE}/call-script", json=payload)
                response.raise_for_status()
                return [types.TextContent(type="text", text=response.text)]

            elif name == "query_product_knowledge":
                category = arguments.get("category") if arguments else None
                url = f"{CRM_API_BASE}/products"
                if category:
                    url += f"?category={category}"
                response = await client.get(url)
                response.raise_for_status()
                return [types.TextContent(type="text", text=response.text)]

            elif name == "get_email_template":
                template_type = arguments.get("type") if arguments else None
                url = f"{CRM_API_BASE}/templates"
                if template_type:
                    url += f"?type={template_type}"
                response = await client.get(url)
                response.raise_for_status()
                return [types.TextContent(type="text", text=response.text)]

            else:
                raise ValueError(f"Không tìm thấy tool: {name}")

        except httpx.HTTPStatusError as e:
            return [types.TextContent(type="text", text=f"Lỗi gọi CRM API ({e.response.status_code}): {e.response.text}")]
        except Exception as e:
            return [types.TextContent(type="text", text=f"Lỗi xử lý MCP Tool: {str(e)}")]

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="banka-crm-mcp",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    NotificationOptions(tools_changed=True),
                    {}
                )
            )
        )

if __name__ == "__main__":
    asyncio.run(main())
