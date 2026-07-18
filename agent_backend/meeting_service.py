# agent_backend/meeting_service.py
import os
import json
import logging
import httpx
import google.generativeai as genai
from agent_backend.document_processor import parse_document
from dotenv import load_dotenv

# Load env variables
load_dotenv()

logger = logging.getLogger("agent_backend.meeting_service")

# Data directory for storing uploaded document state
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DATA_DIR, exist_ok=True)
DOC_STORE_PATH = os.path.join(DATA_DIR, "document_store.json")

def get_gemini_model():
    """Get the configured GenerativeModel instance."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not found in environment variables.")
    genai.configure(api_key=api_key)
    return genai.GenerativeModel('gemini-2.5-flash')

async def call_openrouter(system_prompt: str, user_prompt: str) -> str:
    """Call OpenRouter completions API."""
    api_key = os.getenv("OPENROUTER_API_KEY")
    model = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3-8b-instruct:free")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY not found in environment variables.")
        
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://127.0.0.1:8000",
        "X-Title": "Paperless Meetings AI Agent"
    }
    
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    }
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            json=payload,
            headers=headers
        )
        response.raise_for_status()
        data = response.json()
        if "error" in data:
            raise ValueError(f"OpenRouter API Error: {data['error'].get('message')}")
        if "choices" not in data:
            raise ValueError(f"OpenRouter response missing choices. Full response: {data}")
        return data["choices"][0]["message"]["content"]

def get_current_document() -> dict:
    """Retrieve the current document metadata and analysis."""
    if not os.path.exists(DOC_STORE_PATH):
        return {}
    try:
        with open(DOC_STORE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error reading document store: {e}")
        return {}

def save_current_document(doc_data: dict):
    """Save the current document metadata and analysis to disk."""
    try:
        with open(DOC_STORE_PATH, "w", encoding="utf-8") as f:
            json.dump(doc_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Error writing to document store: {e}")
        raise e

async def process_and_analyze_document(file_path: str, filename: str) -> dict:
    """
    Parse the document page by page, extract text, 
    and request OpenRouter (or Gemini) to generate summary, terms, and questions in one shot.
    """
    # 1. Parse document text page by page
    pages = parse_document(file_path)
    if not pages:
        raise ValueError("Tài liệu không có nội dung hoặc không thể đọc được.")

    # 2. Combine document text with page markers
    # Tối ưu hóa hiệu năng: Với tài liệu dài (> 15 trang), chỉ gửi 12 trang đầu và 3 trang cuối cho LLM phân tích.
    # Việc này giúp giảm số lượng token đáng kể, tăng tốc độ xử lý AI lên gấp nhiều lần và tránh bị timeout.
    if len(pages) <= 15:
        analysis_pages = pages
    else:
        analysis_pages = pages[:12] + pages[-3:]

    full_text_with_pages = []
    for p in analysis_pages:
        full_text_with_pages.append(f"[Bắt đầu Trang {p['page_num']}]\n{p['text']}\n[Kết thúc Trang {p['page_num']}]")
    combined_text = "\n\n".join(full_text_with_pages)
    
    if len(pages) > 15:
        combined_text += f"\n\n[Lưu ý hệ thống: Tài liệu này có tổng cộng {len(pages)} trang. Phần nội dung ở giữa đã được lược bớt để tối ưu hóa hiệu năng phân tích.]"

    # 3. Call OpenRouter/Gemini to perform structured analysis
    prompt = f"""Bạn là một chuyên gia phân tích văn bản pháp lý, quy hoạch hành chính và tài liệu cuộc họp của Chính phủ Việt Nam.
Hãy phân tích tài liệu cuộc họp sau đây (có gắn dấu mốc trang dạng "[Bắt đầu Trang X]" và "[Kết thúc Trang X]").

Hãy phân tích toàn bộ văn bản và trả về một kết quả JSON duy nhất có cấu trúc chính xác như sau:
{{
  "summary": {{
    "context": "Bối cảnh của văn bản (tại sao văn bản này được ban hành, căn cứ pháp lý, vấn đề cần giải quyết)",
    "main_content": "Nội dung chính của văn bản (tóm tắt các điều khoản, kế hoạch, chương trình hành động cốt lõi)",
    "decision_points": "Các điểm quyết định (những mốc quan trọng, phê duyệt, chỉ tiêu bắt buộc cần lưu ý)",
    "impact": "Tác động (ảnh hưởng của văn bản này đến kinh tế, xã hội, các sở ban ngành liên quan)"
  }},
  "agenda": [
    {{
      "time_slot": "Khoảng thời gian hoặc thứ tự thảo luận đề xuất (VD: '08:00 - 08:30' hoặc 'Phần 1')",
      "topic": "Đầu việc hoặc nội dung cụ thể cần đưa ra thảo luận và thông qua tại cuộc họp",
      "presenter": "Người trình bày hoặc đơn vị phụ trách đề xuất (trích xuất hoặc gợi ý dựa trên nội dung)",
      "reference_pages": [2, 4] // Các trang tài liệu liên quan đến đầu việc thảo luận này
    }}
  ],
  "terminology": [
    {{
      "term": "Thuật ngữ chuyên ngành, pháp lý hoặc hành chính (VD: 'kinh phí sự nghiệp', 'quy chuẩn kỹ thuật', 'chủ trương đầu tư')",
      "definition": "Định nghĩa hoặc giải thích ngắn gọn, dễ hiểu bằng tiếng Việt dành cho cán bộ",
      "pages": [1, 3] // Danh sách số các trang xuất hiện thuật ngữ này
    }}
  ],
  "suggested_questions": [
    "Câu hỏi phản biện thứ 1 dành cho lãnh đạo/cán bộ thảo luận",
    "Câu hỏi phản biện thứ 2..."
  ],
  "suggested_regulations": [
    {{
      "title": "Tên văn bản pháp luật, quy chuẩn, nghị quyết liên quan quốc gia hoặc của tỉnh Điện Biên (VD: 'Luật Giao dịch điện tử 2023', 'Nghị định 130/2018/NĐ-CP')",
      "description": "Lý do liên quan trực tiếp và tóm tắt ngắn gọn nội dung quy định hỗ trợ đối chiếu"
    }}
  ]
}}

Yêu cầu cụ thể:
1. NGÔN NGỮ KẾT QUẢ: Toàn bộ kết quả phân tích trong cấu trúc JSON trên (summary, agenda, terminology, suggested_questions, suggested_regulations) BẮT BUỘC phải được viết bằng TIẾNG VIỆT tự nhiên, chuẩn mực hành chính Việt Nam, kể cả khi tài liệu cuộc họp đầu vào bằng TIẾNG ANH.
2. Phần "agenda": Trích xuất khoảng 3-5 nội dung thảo luận chính từ tài liệu hành chính để lập khung lịch trình cuộc họp.
3. Phần "terminology": Tìm và giải thích cô đọng **khoảng 5 thuật ngữ chuyên ngành quan trọng nhất** xuất hiện trong tài liệu. Ghi rõ số trang chính xác mà thuật ngữ đó xuất hiện.
4. Phần "suggested_questions": Tự động tạo **khoảng 3 câu hỏi tư duy phản biện sắc bén nhất** bằng tiếng Việt dựa trên nội dung tài liệu để cán bộ chất vấn.
5. Phần "suggested_regulations": Gợi ý **khoảng 2-3 văn bản pháp luật hoặc quy định liên quan** của Việt Nam cần tham khảo đối chiếu.

Tài liệu cần phân tích:
{combined_text}
"""

    analysis = None
    openrouter_key = os.getenv("OPENROUTER_API_KEY")

    if openrouter_key:
        try:
            logger.info("Sending document text to OpenRouter for structured analysis...")
            response_text = await call_openrouter(
                system_prompt="Bạn là một chuyên gia phân tích tài liệu chính phủ. Hãy trả về kết quả dưới dạng JSON có cấu trúc chính xác theo yêu cầu.",
                user_prompt=prompt
            )
            # Clean markdown JSON formatting if any
            response_text = response_text.strip()
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            elif response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            response_text = response_text.strip()
            
            analysis = json.loads(response_text)
            logger.info("Successfully analyzed document via OpenRouter.")
        except Exception as e:
            logger.error(f"OpenRouter analysis failed: {e}. Falling back to Gemini...")

    if not analysis:
        # Fallback to Gemini if OpenRouter key is missing or failed
        try:
            model = get_gemini_model()
            logger.info("Sending document text to Gemini for structured analysis...")
            
            response = model.generate_content(
                prompt,
                generation_config={"response_mime_type": "application/json"}
            )
            analysis = json.loads(response.text)
            logger.info("Successfully analyzed document via Gemini.")
        except Exception as e:
            logger.error(f"Gemini analysis failed: {e}")
            raise e

    # Save to store
    doc_data = {
        "filename": filename,
        "pages": pages,
        "analysis": analysis
    }
    save_current_document(doc_data)
    
    # Save to documents library
    try:
        import re
        docs_dir = os.path.join(DATA_DIR, "documents")
        os.makedirs(docs_dir, exist_ok=True)
        safe_filename = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)
        lib_path = os.path.join(docs_dir, f"{safe_filename}.json")
        with open(lib_path, "w", encoding="utf-8") as f:
            json.dump(doc_data, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved document to library: {lib_path}")
    except Exception as e:
        logger.error(f"Failed to save document to library: {e}")
        
    return doc_data

async def answer_document_question(question: str, history: list = []) -> dict:
    """
    Answer a question grounded on the current document, citing specific pages.
    """
    doc_data = get_current_document()
    if not doc_data or not doc_data.get("pages"):
        return {
            "answer": "Hiện tại chưa có tài liệu nào được tải lên. Vui lòng tải tài liệu lên trước.",
            "citations": []
        }

    # Format pages for grounding context
    pages_text = []
    for p in doc_data["pages"]:
        pages_text.append(f"[Trang {p['page_num']}]\n{p['text']}")
    document_context = "\n\n".join(pages_text)

    # Convert chat history to text
    history_context = ""
    for msg in history:
        role = "Cán bộ" if msg.get("role") == "user" else "Trợ lý"
        history_context += f"{role}: {msg.get('message')}\n"

    prompt = f"""Bạn là Trợ lý AI phục vụ cuộc họp của Sở Khoa học và Công nghệ tỉnh Điện Biên (GovTech Assistant).
Nhiệm vụ của bạn là trả lời các câu hỏi của cán bộ dựa trên tài liệu họp được cung cấp dưới đây.

TÀI LIỆU HỌP:
{document_context}

LỊCH SỬ HỘI THOẠI GẦN ĐÂY:
{history_context}

CÂU HỎI MỚI CỦA CÁN BỘ:
{question}

HƯỚNG DẪN TRẢ LỜI:
1. BẮT BUỘC trả lời bằng TIẾNG VIỆT lịch sự, nghiêm túc, chuẩn mực hành chính nhà nước. Nếu tài liệu họp được cung cấp bằng TIẾNG ANH, hãy dịch và giải thích nội dung thông tin sang tiếng Việt chính xác và dễ hiểu cho cán bộ.
2. Chỉ trả lời dựa trên thông tin có trong TÀI LIỆU HỌP được cung cấp. Nếu thông tin không có trong tài liệu, hãy trả lời lịch sự rằng "Tài liệu được cung cấp không đề cập đến nội dung này". Không tự bịa đặt thông tin.
3. BẮT BUỘC phải trích dẫn số trang cụ thể nơi bạn lấy thông tin. Định dạng trích dẫn trong câu trả lời dạng [Trang X] (ví dụ: "...chỉ tiêu này cần đạt 80% [Trang 12]").
4. Hãy trả về một cấu trúc JSON như sau:
{{
  "answer": "Nội dung câu trả lời của bạn bằng tiếng Việt, có kèm trích dẫn [Trang X] trong văn bản",
  "citations": [X, Y] // Mảng các số trang được trích dẫn (ví dụ: [12, 14])
}}
"""

    try:
        model = get_gemini_model()
        response = model.generate_content(
            prompt,
            generation_config={"response_mime_type": "application/json"}
        )
        return json.loads(response.text)
    except Exception as e:
        logger.error(f"Error answering document Q&A: {e}")
        return {
            "answer": f"Đã xảy ra lỗi khi tìm câu trả lời: {str(e)}",
            "citations": []
        }
