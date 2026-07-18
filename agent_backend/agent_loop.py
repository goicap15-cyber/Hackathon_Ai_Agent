# agent_backend/agent_loop.py
import os
import json
import logging
import datetime
import re
import httpx
import google.generativeai as genai
from google.generativeai import protos
from dotenv import load_dotenv

# Load env variables
load_dotenv()

logger = logging.getLogger("agent_backend.agent_loop")

# Get API key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# Tool definitions for Gemini
DOCUMENT_TOOLS = [
    protos.Tool(function_declarations=[
        protos.FunctionDeclaration(
            name="search_in_document",
            description="Tìm kiếm từ khóa hoặc cụm từ trong tài liệu cuộc họp hiện tại. Trả về các phân đoạn văn bản và số trang tương ứng.",
            parameters=protos.Schema(
                type=protos.Type.OBJECT,
                properties={
                    "query": protos.Schema(
                        type=protos.Type.STRING,
                        description="Từ khóa hoặc cụm từ cần tìm (ví dụ: 'kinh phí', 'Điện Biên', 'quy hoạch')"
                    )
                },
                required=["query"]
            )
        ),
        protos.FunctionDeclaration(
            name="get_page_content",
            description="Lấy toàn bộ nội dung chữ của một trang cụ thể trong tài liệu cuộc họp (1-indexed).",
            parameters=protos.Schema(
                type=protos.Type.OBJECT,
                properties={
                    "page_num": protos.Schema(
                        type=protos.Type.INTEGER,
                        description="Số trang cần lấy (bắt đầu từ 1)"
                    )
                },
                required=["page_num"]
            )
        ),
        protos.FunctionDeclaration(
            name="get_terminology_details",
            description="Tra cứu định nghĩa và các trang chứa một thuật ngữ chuyên ngành đã được trích xuất từ tài liệu.",
            parameters=protos.Schema(
                type=protos.Type.OBJECT,
                properties={
                    "term": protos.Schema(
                        type=protos.Type.STRING,
                        description="Thuật ngữ cần tra cứu (ví dụ: 'kinh phí sự nghiệp')"
                    )
                },
                required=["term"]
            )
        )
    ])
]

def _read_current_document():
    path = os.path.abspath(os.path.join(os.path.dirname(__file__), "data", "document_store.json"))
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def _read_all_documents():
    data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "data"))
    docs_dir = os.path.join(data_dir, "documents")
    documents = []
    if os.path.exists(docs_dir):
        for filename in os.listdir(docs_dir):
            if filename.endswith(".json"):
                try:
                    with open(os.path.join(docs_dir, filename), "r", encoding="utf-8") as f:
                        documents.append(json.load(f))
                except Exception:
                    pass
    # Fallback to single active document if library folder is empty
    if not documents:
        current = _read_current_document()
        if current:
            documents.append(current)
    return documents

def execute_local_tool(name: str, args: dict) -> str:
    """Execute document tools locally, mimicking the MCP server execution."""
    all_docs = _read_all_documents()
    if not all_docs:
        return "Lỗi: Hiện chưa có tài liệu nào được nạp lên hệ thống."

    if name == "search_in_document":
        query = args.get("query", "").lower()
        if not query:
            return "Lỗi: Vui lòng cung cấp từ khóa cần tìm."
        results = []
        for doc in all_docs:
            doc_name = doc.get("filename", "Tài liệu")
            for p in doc.get("pages", []):
                if query in p.get("text", "").lower():
                    text = p["text"]
                    idx = text.lower().find(query)
                    start = max(0, idx - 150)
                    end = min(len(text), idx + len(query) + 150)
                    snippet = text[start:end].replace("\n", " ")
                    results.append(f"- [{doc_name} - Trang {p['page_num']}]: ... {snippet} ...")
        if not results:
            return f"Không tìm thấy kết quả nào chứa '{query}' trong tài liệu."
        return "\n".join(results[:8])

    elif name == "get_page_content":
        try:
            page_num = int(args.get("page_num", 1))
        except (ValueError, TypeError):
            return "Lỗi: Số trang không hợp lệ."
        filename = args.get("filename")
        
        target_doc = None
        if filename:
            for d in all_docs:
                if d.get("filename") == filename:
                    target_doc = d
                      
        if not target_doc:
            current_active = _read_current_document()
            active_filename = current_active.get("filename") if current_active else ""
            for d in all_docs:
                if d.get("filename") == active_filename:
                    target_doc = d
                    break
            if not target_doc:
                target_doc = all_docs[0]
                
        for p in target_doc.get("pages", []):
            if p["page_num"] == page_num:
                return f"--- NỘI DUNG TRANG {page_num} ({target_doc['filename']}) ---\n{p['text']}"
        return f"Không tìm thấy trang {page_num} trong tài liệu '{target_doc['filename']}'."

    elif name == "get_terminology_details":
        term = args.get("term", "").lower()
        if not term:
            return "Lỗi: Vui lòng cung cấp thuật ngữ cần tra cứu."
        for doc in all_docs:
            terms_list = doc.get("analysis", {}).get("terminology", [])
            for t in terms_list:
                if t.get("term", "").lower() == term:
                    pages_str = ", ".join(map(str, t.get("pages", [])))
                    return f"Tài liệu: {doc.get('filename')}\nThuật ngữ: {t.get('term')}\nĐịnh nghĩa: {t.get('definition')}\nXuất hiện tại trang: {pages_str}"
        return f"Không tìm thấy thuật ngữ '{term}' trong các tài liệu."

    return f"Lỗi: Không tìm thấy tool {name}."

async def run_agent(
    user_message: str,
    prev_customer_id: str = "",
    rm_name: str = "",
    history: list = None,
    role: str = 'admin',
) -> dict:
    """
    Paperless Meetings Agent Loop.
    Uses OpenRouter (primary if configured) or Gemini function calling.
    Returns structured results for the frontend with trace logs.
    """
    trace_logs = []
    
    all_docs = _read_all_documents()
    if not all_docs:
        return {
            "answer": "Chào bạn, hiện tại hệ thống chưa có tài liệu nào được nạp. Vui lòng tải tài liệu họp lên trước.",
            "trace": ["⚠️ Chưa có tài liệu nào được nạp"],
            "citations": []
        }

    # 1. Primary: Use OpenRouter if configured
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    if openrouter_key:
        try:
            # Clean stop words and tokenize query for Vietnamese density scoring
            stop_words = {"là", "gì", "nào", "bao", "nhiêu", "của", "và", "để", "thì", "mà", "cho", "ở", "trong", "trên", "dưới", "tôi", "này", "cơ", "hội", "tại", "sao", "được", "có", "về", "cụ", "thể"}
            orig_words = [w.lower().strip(",.?!()\"'") for w in user_message.split()]
            orig_words = [w for w in orig_words if w and w not in stop_words and len(w) > 1]
            
            # Bilingual keyword expansion for English documents
            vi_to_en = {
                "tác": ["impact", "effect"],
                "động": ["impact", "effect", "action"],
                "kinh": ["economic", "economy"],
                "tế": ["economic", "economy"],
                "quy": ["scale", "size"],
                "mô": ["scale", "size"],
                "huấn": ["train", "training"],
                "luyện": ["train", "training"],
                "đánh": ["evaluate", "evaluation", "benchmark", "test"],
                "giá": ["evaluate", "evaluation", "benchmark", "test"],
                "an": ["safety", "safe"],
                "toàn": ["safety", "safe"],
                "kiến": ["architecture"],
                "trúc": ["architecture"],
                "sơ": ["diagram", "figure", "table", "chart"],
                "đồ": ["diagram", "figure", "table", "chart"],
                "ảnh": ["image", "figure", "photo"],
                "hình": ["image", "figure", "photo"],
                "thuật": ["term", "terminology"],
                "ngữ": ["term", "terminology"],
                "tóm": ["summary", "abstract"],
                "tắt": ["summary", "abstract"],
                "cuộc": ["meeting"],
                "họp": ["meeting"],
                "báo": ["report", "paper"],
                "cáo": ["report", "paper"],
                "quyết": ["decision"],
                "định": ["decision"],
                "chi": ["cost", "expense", "budget"],
                "phí": ["cost", "expense", "budget"]
            }
            words = list(orig_words)
            for w in orig_words:
                if w in vi_to_en:
                    words.extend(vi_to_en[w])
            
            # Formulate query for trace logs
            search_query = " ".join(orig_words[:4]) or user_message
            trace_logs.append(f"🔧 Searching library for query: '{search_query}'")
            
            # Parse page numbers from query (e.g., "trang 4", "trang số 4", "page 4")
            page_matches = re.findall(r'(?:trang|page|trang số)\s*(\d+)', user_message.lower())
            explicit_pages = [int(p) for p in page_matches]
            
            # Score pages across all library documents based on keyword match density
            page_scores = []
            for doc in all_docs:
                doc_name = doc.get("filename", "Tài liệu")
                for p in doc.get("pages", []):
                    text_lower = p.get("text", "").lower()
                    score = 0
                    for w in words:
                        score += text_lower.count(w)
                    
                    # Boost score if page number is explicitly requested and matches page_num
                    if p.get("page_num") in explicit_pages:
                        score += 500
                        
                    if score > 0:
                        page_scores.append((doc_name, p["page_num"], p["text"], score))
            
            # Sort pages by match density descending
            page_scores.sort(key=lambda x: x[3], reverse=True)
            pages_found = page_scores[:4]
            
            # Fallback if no matching page is found
            if not pages_found:
                first_doc = all_docs[0]
                first_page = first_doc.get("pages", [{}])[0]
                pages_found = [(first_doc.get("filename", "Tài liệu"), first_page.get("page_num", 1), first_page.get("text", ""), 0)]
                
            trace_logs.append(f"📊 Response: found matches: {[f'{d} - Trang {p}' for d, p, _, _ in pages_found]}")
            
            # Fetch page content for top matching pages
            context_parts = []
            citations = []
            for doc_name, p_num, text, score in pages_found:
                trace_logs.append(f"🔧 Reading: '{doc_name}' - Trang {p_num} (Score: {score})")
                context_parts.append(f"[Tài liệu: {doc_name}, Trang {p_num}]\n{text}")
                citations.append(f"{doc_name} - Trang {p_num}")
                
            context_text = "\n\n".join(context_parts)
            
            system_instruction = f"""Bạn là Trợ lý AI phục vụ cuộc họp của Sở Khoa học và Công nghệ tỉnh Điện Biên (GovTech Agent).
Nhiệm vụ của bạn là giải đáp thắc mắc của cán bộ dựa trên các tài liệu họp trong thư viện dưới đây.

TÀI LIỆU HỌP:
{context_text}

QUY TẮC:
1. Chỉ trả lời dựa trên thông tin có trong TÀI LIỆU HỌP được cung cấp. Nếu không có, hãy trả lời lịch sự là thông tin không đề cập trong tài liệu.
2. Trả lời bằng tiếng Việt chuẩn mực hành chính nhà nước.
3. BẮT BUỘC phải trích dẫn tên tài liệu và số trang nơi lấy thông tin dưới dạng [Tên_tài_liệu - Trang X] (ví dụ: "...đạt 80% [gemini_paper.pdf - Trang 12]").
4. HỖ TRỢ LẬP AGENDA & BIÊN BẢN HỌP: Khi cán bộ yêu cầu lập lịch trình (Agenda) hoặc biên bản cuộc họp (Meeting Minutes), bạn hãy trích xuất các thông tin chính, phân vai người trình bày cụ thể, các đầu việc cần thảo luận/thống nhất, trình bày dưới dạng bảng hành chính Việt Nam chuyên nghiệp, rõ ràng và trích dẫn số trang tham chiếu cụ thể.
"""
            
            # Build conversation history
            history_text = ""
            if history:
                for msg in history[-5:]:
                    msg_role = "Cán bộ" if msg.get("role") == "user" else "Trợ lý"
                    history_text += f"{msg_role}: {msg.get('message')}\n"
                    
            user_prompt = f"{history_text}Cán bộ: {user_message}\nTrợ lý:"
            
            headers = {
                "Authorization": f"Bearer {openrouter_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://127.0.0.1:8000",
                "X-Title": "Paperless Meetings AI Agent"
            }
            payload = {
                "model": os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3-8b-instruct:free"),
                "messages": [
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": user_prompt}
                ]
            }
            
            logger.info("Sending Q&A request to OpenRouter...")
            async with httpx.AsyncClient(timeout=45.0) as client:
                resp = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    json=payload,
                    headers=headers
                )
                resp.raise_for_status()
                data = resp.json()
                if "error" in data:
                    raise ValueError(f"OpenRouter API Error: {data['error'].get('message')}")
                if "choices" not in data:
                    raise ValueError(f"OpenRouter response missing choices. Full response: {data}")
                answer = data["choices"][0]["message"]["content"]
                
                # Check for explicit page citations in answer text
                text_citations = list(map(int, re.findall(r'\[Trang\s+(\d+)\]', answer)))
                if text_citations:
                    citations = list(set(text_citations))
                    
                return {
                    "answer": answer.strip(),
                    "trace": trace_logs,
                    "citations": citations
                }
        except Exception as e:
            logger.error(f"OpenRouter agent loop failed: {e}. Falling back to Gemini...")
            trace_logs.append(f"⚠️ OpenRouter lỗi: {e}. Đang chuyển sang Gemini...")

    # 2. Secondary: Use Gemini Function Calling if available
    # Build system prompt for GovTech assistant
    system_instruction = f"""Bạn là Trợ lý AI phục vụ cuộc họp của Sở Khoa học và Công nghệ tỉnh Điện Biên (GovTech Agent).
Nhiệm vụ của bạn là hỗ trợ cán bộ chuẩn bị họp bằng cách tra cứu, tìm kiếm và giải đáp dựa trên tài liệu họp hiện tại: '{doc.get("filename", "Tài liệu cuộc họp")}'.

QUY TẮC:
1. Luôn ưu tiên sử dụng các công cụ (search_in_document, get_page_content, get_terminology_details) để tra cứu thông tin trước khi trả lời.
2. BẮT BUỘC trả lời bằng tiếng Việt lịch sự, chuẩn mực hành chính nhà nước. Nếu tài liệu cuộc họp là tiếng Anh, hãy tự động biên dịch các phân đoạn tìm được sang tiếng Việt để trả lời cán bộ.
3. Chỉ trả lời dựa trên thông tin tìm thấy từ các công cụ trong tài liệu cuộc họp. Không tự bịa đặt thông tin.
4. BẮT BUỘC phải trích dẫn số trang cụ thể nơi lấy thông tin. Định dạng trích dẫn trong câu trả lời dạng [Trang X] (ví dụ: "...đạt 80% ngân sách [Trang 12]").
5. Trình bày rõ ràng, dễ đọc, sử dụng gạch đầu dòng khi cần thiết.
6. HỖ TRỢ LẬP AGENDA & BIÊN BẢN HỌP: Khi cán bộ yêu cầu lập lịch trình (Agenda) hoặc biên bản cuộc họp (Meeting Minutes), bạn hãy trích xuất các thông tin chính, phân vai cụ thể, các đầu việc cần thảo luận, trình bày dưới dạng bảng hành chính Việt Nam chuyên nghiệp, rõ ràng và trích dẫn số trang tham chiếu cụ thể.
"""

    if not GEMINI_API_KEY:
        # Local fallback if Gemini API key is missing
        trace_logs.append("⚠️ API Key không khả dụng. Sử dụng bộ quy tắc nội bộ.")
        return {
            "response": "Thiếu GEMINI_API_KEY. Vui lòng cấu hình API Key để trợ lý AI cuộc họp hoạt động.",
            "trace_logs": trace_logs,
            "citations": []
        }

    try:
        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            system_instruction=system_instruction,
            tools=DOCUMENT_TOOLS,
            generation_config={"temperature": 0.2}
        )

        # Build message history matching Gemini API
        messages = []
        if history:
            for msg in history[-10:]:
                g_role = "model" if msg.get("role") == "ai" else "user"
                messages.append({"role": g_role, "parts": [msg.get("message", "")]})
        
        messages.append({"role": "user", "parts": [user_message]})

        # Run up to 4 turns of tool use
        final_response = ""
        citations = []
        
        for turn in range(4):
            logger.info(f"Gemini Turn {turn + 1}...")
            response = model.generate_content(messages)
            
            # Check for function calls
            tool_calls = []
            text_parts = []
            
            # Parse parts
            if response.candidates and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if part.function_call and part.function_call.name:
                        tool_calls.append(part.function_call)
                    elif hasattr(part, "text") and part.text:
                        text_parts.append(part.text)

            if not tool_calls:
                final_response = " ".join(text_parts) or response.text
                break

            # Add assistant turn with tool calls to history
            messages.append(response.candidates[0].content)

            # Process tool calls
            for tc in tool_calls:
                tool_name = tc.name
                tool_args = dict(tc.args)
                
                trace_logs.append(f"🔧 Calling MCP Tool: {tool_name}({json.dumps(tool_args, ensure_ascii=False)})")
                
                # Execute tool locally
                result_text = execute_local_tool(tool_name, tool_args)
                
                trace_logs.append(f"📊 Response: {result_text[:120]}...")
                
                # Keep track of citations
                if tool_name == "get_page_content":
                    try:
                        citations.append(int(tool_args.get("page_num", 1)))
                    except Exception:
                        pass
                
                # Add tool response to history
                # Formulate a response part matching Google's protobuf format
                tool_response_part = protos.Part(
                    function_response=protos.FunctionResponse(
                        name=tool_name,
                        response={"result": result_text}
                    )
                )
                messages.append(protos.Content(role="function", parts=[tool_response_part]))

        # Parse citations from text if tool didn't explicitly capture it
        text_citations = re.findall(r'\[Trang\s+(\d+)\]', final_response)
        for tc in text_citations:
            try:
                citations.append(int(tc))
            except Exception:
                pass
                
        # Remove duplicate citations
        citations = list(set(citations))

        return {
            "answer": final_response,
            "trace": trace_logs,
            "citations": citations
        }

    except Exception as e:
        logger.exception("Error in run_agent loop")
        return {
            "answer": f"Xin lỗi, trợ lý cuộc họp gặp sự cố kỹ thuật: {str(e)}",
            "trace": trace_logs + [f"❌ Error: {str(e)}"],
            "citations": []
        }
