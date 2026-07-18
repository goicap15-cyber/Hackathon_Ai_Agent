# agent_backend/meeting_service.py
import os
import json
import logging
import time
from google import genai
from dotenv import load_dotenv
from pypdf import PdfReader

# Load env variables
load_dotenv()

logger = logging.getLogger("agent_backend.meeting_service")

# Data directory for storing uploaded document state
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DATA_DIR, exist_ok=True)
DOC_STORE_PATH = os.path.join(DATA_DIR, "document_store.json")

def get_gemini_client():
    """Get the configured GenAI Client."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not found in environment variables.")
    return genai.Client(api_key=api_key)

def ensure_pages_extracted(doc_data: dict) -> dict:
    """Ensure pages are extracted and stored in doc_data for the frontend to render."""
    if doc_data.get("pages"):
        return doc_data
        
    import re
    safe_filename = re.sub(r'[^a-zA-Z0-9._-]', '_', doc_data.get("filename", ""))
    pdf_path = os.path.join(DATA_DIR, "documents", f"{safe_filename}.pdf")
    
    pages = []
    if os.path.exists(pdf_path):
        try:
            reader = PdfReader(pdf_path)
            for i, page in enumerate(reader.pages):
                text = page.extract_text()
                if text:
                    pages.append({
                        "page_num": i + 1,
                        "text": text.strip()
                    })
        except Exception as e:
            logger.error(f"Failed to dynamically extract PDF text: {e}")
            
    if not pages:
        pages = [{"page_num": 1, "text": "Không thể trích xuất văn bản từ tài liệu này để hiển thị."}]
        
    doc_data["pages"] = pages
    return doc_data

def get_current_document() -> dict:
    """Retrieve the current document metadata and analysis."""
    if not os.path.exists(DOC_STORE_PATH):
        return {}
    try:
        with open(DOC_STORE_PATH, "r", encoding="utf-8") as f:
            doc_data = json.load(f)
            return ensure_pages_extracted(doc_data)
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
    Upload the document using Files API, then perform structured analysis using Interactions API.
    """
    client = get_gemini_client()
    
    # Upload file
    logger.info(f"Uploading {filename} to Gemini Files API...")
    uploaded_file = client.files.upload(file=file_path)
    
    # Wait for file to process if it's large
    file_info = client.files.get(name=uploaded_file.name)
    while file_info.state.name == 'PROCESSING':
        logger.info('File is still processing, retrying in 5 seconds...')
        time.sleep(5)
        file_info = client.files.get(name=uploaded_file.name)
        
    if file_info.state.name == 'FAILED':
        raise ValueError("File processing failed on Gemini servers.")

    prompt = """Bạn là một chuyên gia phân tích văn bản pháp lý, quy hoạch hành chính và tài liệu cuộc họp của Chính phủ Việt Nam.
Hãy phân tích tài liệu cuộc họp sau đây.

Hãy phân tích toàn bộ văn bản và trả về một kết quả JSON duy nhất có cấu trúc chính xác như sau:
{
  "summary": {
    "context": "Bối cảnh của văn bản (tại sao văn bản này được ban hành, căn cứ pháp lý, vấn đề cần giải quyết)",
    "main_content": "Nội dung chính của văn bản (tóm tắt các điều khoản, kế hoạch, chương trình hành động cốt lõi)",
    "decision_points": "Các điểm quyết định (những mốc quan trọng, phê duyệt, chỉ tiêu bắt buộc cần lưu ý)",
    "impact": "Tác động (ảnh hưởng của văn bản này đến kinh tế, xã hội, các sở ban ngành liên quan)"
  },
  "agenda": [
    {
      "time_slot": "Khoảng thời gian hoặc thứ tự thảo luận đề xuất (VD: '08:00 - 08:30' hoặc 'Phần 1')",
      "topic": "Đầu việc hoặc nội dung cụ thể cần đưa ra thảo luận và thông qua tại cuộc họp",
      "presenter": "Người trình bày hoặc đơn vị phụ trách đề xuất (trích xuất hoặc gợi ý dựa trên nội dung)",
      "reference_pages": [2, 4] // Các trang tài liệu liên quan đến đầu việc thảo luận này
    }
  ],
  "terminology": [
    {
      "term": "Thuật ngữ chuyên ngành, pháp lý hoặc hành chính (VD: 'kinh phí sự nghiệp', 'quy chuẩn kỹ thuật', 'chủ trương đầu tư')",
      "definition": "Định nghĩa hoặc giải thích ngắn gọn, dễ hiểu bằng tiếng Việt dành cho cán bộ",
      "pages": [1, 3] // Danh sách số các trang xuất hiện thuật ngữ này
    }
  ],
  "suggested_questions": [
    "Câu hỏi phản biện thứ 1 dành cho lãnh đạo/cán bộ thảo luận",
    "Câu hỏi phản biện thứ 2..."
  ],
  "suggested_regulations": [
    {
      "title": "Tên văn bản pháp luật, quy chuẩn, nghị quyết liên quan quốc gia hoặc của tỉnh Điện Biên",
      "description": "Lý do liên quan trực tiếp và tóm tắt ngắn gọn nội dung quy định hỗ trợ đối chiếu"
    }
  ]
}

Yêu cầu cụ thể:
1. NGÔN NGỮ KẾT QUẢ: Toàn bộ kết quả phân tích trong cấu trúc JSON BẮT BUỘC phải được viết bằng TIẾNG VIỆT tự nhiên, chuẩn mực hành chính Việt Nam, kể cả khi tài liệu đầu vào bằng TIẾNG ANH.
2. Trích xuất ít nhất 3-6 nội dung thảo luận cốt lõi cho agenda.
3. Tìm và giải thích **ít nhất 10 thuật ngữ chuyên ngành**. Ghi rõ số trang chính xác mà thuật ngữ đó xuất hiện.
4. Tự động tạo **ít nhất 5 câu hỏi tư duy phản biện** chất lượng cao bằng tiếng Việt dựa trên nội dung tài liệu.
5. Gợi ý **ít nhất 3-5 văn bản pháp luật hoặc quy định liên quan**.
6. KẾT QUẢ TRẢ VỀ PHẢI LÀ CHUỖI JSON HỢP LỆ.
"""

    logger.info("Sending document to Gemini Interactions API for structured analysis...")
    
    interaction = client.interactions.create(
        model="gemini-3.1-flash-lite",
        input=[
            {"type": "document", "uri": uploaded_file.uri, "mime_type": uploaded_file.mime_type},
            {"type": "text", "text": prompt}
        ]
    )
    
    response_text = interaction.output_text
    response_text = response_text.strip()
    if response_text.startswith("```json"):
        response_text = response_text[7:]
    elif response_text.startswith("```"):
        response_text = response_text[3:]
    if response_text.endswith("```"):
        response_text = response_text[:-3]
    response_text = response_text.strip()
    
    analysis = json.loads(response_text)
    logger.info("Successfully analyzed document via Gemini Native Vision.")
    
    # Extract text locally for frontend rendering
    pages = []
    try:
        reader = PdfReader(file_path)
        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if text:
                pages.append({
                    "page_num": i + 1,
                    "text": text.strip()
                })
    except Exception as e:
        logger.error(f"Failed to extract PDF text locally for frontend: {e}")
        # Add a dummy page if it fails so the frontend doesn't crash completely
        if not pages:
            pages = [{"page_num": 1, "text": "Không thể trích xuất văn bản từ tài liệu này để hiển thị."}]
            
    # Save to store
    doc_data = {
        "filename": filename,
        "file_uri": uploaded_file.uri,
        "mime_type": uploaded_file.mime_type,
        "file_name_gemini": uploaded_file.name,
        "last_interaction_id": interaction.id,
        "analysis": analysis,
        "pages": pages
    }
    save_current_document(doc_data)
    
    # Save to documents library
    try:
        import re
        import shutil
        docs_dir = os.path.join(DATA_DIR, "documents")
        os.makedirs(docs_dir, exist_ok=True)
        safe_filename = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)
        
        # Save JSON metadata
        lib_path = os.path.join(docs_dir, f"{safe_filename}.json")
        with open(lib_path, "w", encoding="utf-8") as f:
            json.dump(doc_data, f, ensure_ascii=False, indent=2)
            
        # Save the actual PDF file for future re-uploads
        pdf_path = os.path.join(docs_dir, f"{safe_filename}.pdf")
        if file_path != pdf_path:
            shutil.copy2(file_path, pdf_path)
            
        logger.info(f"Saved document and metadata to library: {safe_filename}")
    except Exception as e:
        logger.error(f"Failed to save document to library: {e}")
        
    return doc_data

def ensure_file_on_gemini(doc_data: dict) -> dict:
    """Check if file still exists on Gemini (48h expiry). If not, re-upload from local storage."""
    if not doc_data.get("file_name_gemini"):
        return doc_data
        
    client = get_gemini_client()
    try:
        # Check if file exists
        client.files.get(name=doc_data["file_name_gemini"])
        return doc_data
    except Exception as e:
        logger.info(f"File {doc_data['file_name_gemini']} not found on Gemini or expired. Re-uploading... ({e})")
        
        import re
        safe_filename = re.sub(r'[^a-zA-Z0-9._-]', '_', doc_data.get("filename", ""))
        pdf_path = os.path.join(DATA_DIR, "documents", f"{safe_filename}.pdf")
        
        if not os.path.exists(pdf_path):
            logger.error(f"Local PDF file not found at {pdf_path}. Cannot re-upload.")
            return doc_data
            
        try:
            # Re-upload
            uploaded_file = client.files.upload(file=pdf_path)
            
            # Wait for processing
            file_info = client.files.get(name=uploaded_file.name)
            while file_info.state.name == 'PROCESSING':
                time.sleep(2)
                file_info = client.files.get(name=uploaded_file.name)
                
            if file_info.state.name == 'FAILED':
                logger.error("Re-uploaded file processing failed on Gemini servers.")
                return doc_data
                
            # Update doc_data
            doc_data["file_uri"] = uploaded_file.uri
            doc_data["file_name_gemini"] = uploaded_file.name
            # Reset interaction ID since it's a new file upload session
            doc_data["last_interaction_id"] = None
            
            save_current_document(doc_data)
            
            # Also update the library json
            lib_path = os.path.join(DATA_DIR, "documents", f"{safe_filename}.json")
            with open(lib_path, "w", encoding="utf-8") as f:
                json.dump(doc_data, f, ensure_ascii=False, indent=2)
                
            logger.info(f"Successfully re-uploaded document. New URI: {uploaded_file.uri}")
        except Exception as upload_err:
            logger.error(f"Failed to re-upload document: {upload_err}")
            
    return doc_data

async def answer_document_question_stream(question: str, history: list = []):
    """
    Stream the answer for a chat question using Native Vision context.
    """
    client = get_gemini_client()
    doc_data = get_current_document()
    
    if not doc_data.get("file_name_gemini"):
        yield "Lỗi: Không tìm thấy tài liệu gốc trên hệ thống. Vui lòng tải lên lại tài liệu."
        return

    # Format history
    history_text = ""
    for msg in history:
        role_name = "Cán bộ" if msg.get("role") == "user" else "Hệ thống"
        history_text += f"{role_name}: {msg.get('message')}\n"

    prompt = f"""CÂU HỎI MỚI CỦA CÁN BỘ:
{question}

LỊCH SỬ HỘI THOẠI TRƯỚC ĐÓ:
{history_text}

HƯỚNG DẪN TRẢ LỜI:
1. BẮT BUỘC trả lời bằng TIẾNG VIỆT lịch sự, nghiêm túc, chuẩn mực hành chính nhà nước.
2. Chỉ trả lời dựa trên thông tin có trong TÀI LIỆU HỌP đã cung cấp ở đầu phiên. Không tự bịa đặt thông tin.
3. BẮT BUỘC phải trích dẫn số trang cụ thể nơi bạn lấy thông tin. Định dạng trích dẫn trong câu trả lời dạng [Trang X] (ví dụ: "...chỉ tiêu này cần đạt 80% [Trang 12]").
4. Trả về định dạng Markdown. TUYỆT ĐỐI KHÔNG trả về JSON.
"""

    try:
        logger.info("Sending Streaming Q&A to Gemini 3.5 Flash")
        
        # Get the file object from Gemini
        file_obj = client.files.get(name=doc_data["file_name_gemini"])
        
        response = client.models.generate_content_stream(
            model="gemini-3.1-flash-lite",
            contents=[
                file_obj,
                prompt
            ]
        )
        
        for chunk in response:
            if chunk.text:
                yield chunk.text
                
    except Exception as e:
        logger.error(f"Error answering document question (stream): {e}")
        yield f"\n\n[Lỗi hệ thống khi phân tích tài liệu: {str(e)}]"

async def answer_document_question(question: str, history: list = []) -> dict:
    """
    Answer a question grounded on the current document, using previous interaction ID.
    """
    doc_data = get_current_document()
    if not doc_data or not doc_data.get("file_uri"):
        return {
            "answer": "Hiện tại chưa có tài liệu nào được tải lên. Vui lòng tải tài liệu lên trước.",
            "citations": []
        }

    # Ensure file hasn't expired on Gemini
    doc_data = ensure_file_on_gemini(doc_data)

    client = get_gemini_client()
    
    prompt = f"""CÂU HỎI MỚI CỦA CÁN BỘ:
{question}

HƯỚNG DẪN TRẢ LỜI:
1. BẮT BUỘC trả lời bằng TIẾNG VIỆT lịch sự, nghiêm túc, chuẩn mực hành chính nhà nước.
2. Chỉ trả lời dựa trên thông tin có trong TÀI LIỆU HỌP đã cung cấp ở đầu phiên. Không tự bịa đặt thông tin.
3. BẮT BUỘC phải trích dẫn số trang cụ thể nơi bạn lấy thông tin. Định dạng trích dẫn trong câu trả lời dạng [Trang X] (ví dụ: "...chỉ tiêu này cần đạt 80% [Trang 12]").
4. Hãy trả về một cấu trúc JSON như sau:
{{
  "answer": "Nội dung câu trả lời của bạn bằng tiếng Việt, có kèm trích dẫn [Trang X] trong văn bản",
  "citations": [X, Y] // Mảng các số trang được trích dẫn (ví dụ: [12, 14])
}}
"""

    try:
        logger.info(f"Sending Q&A to Gemini. Previous Interaction ID: {doc_data.get('last_interaction_id')}")
        
        interaction_kwargs = {
            "model": "gemini-3.1-flash-lite",
            "input": [{"type": "text", "text": prompt}]
        }
        
        # If we have a previous interaction ID, use it for context caching.
        if doc_data.get("last_interaction_id"):
            interaction_kwargs["previous_interaction_id"] = doc_data["last_interaction_id"]
        else:
            # Fallback if no interaction ID is present
            interaction_kwargs["input"].insert(0, {
                "type": "document",
                "uri": doc_data["file_uri"],
                "mime_type": doc_data["mime_type"]
            })
            
        interaction = client.interactions.create(**interaction_kwargs)
        
        # Update the interaction ID for the next turn
        doc_data["last_interaction_id"] = interaction.id
        save_current_document(doc_data)
        
        response_text = interaction.output_text
        response_text = response_text.strip()
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        elif response_text.startswith("```"):
            response_text = response_text[3:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
        response_text = response_text.strip()
            
        return json.loads(response_text)
    except Exception as e:
        logger.error(f"Error answering document Q&A: {e}")
        return {
            "answer": f"Đã xảy ra lỗi khi tìm câu trả lời: {str(e)}",
            "citations": []
        }
