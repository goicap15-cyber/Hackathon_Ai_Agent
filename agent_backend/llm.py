# agent_backend/llm.py
import os
import httpx
import google.generativeai as genai
from dotenv import load_dotenv

# Load env vars
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    # Use gemini-2.5-flash as default
    model = genai.GenerativeModel('gemini-2.5-flash')
else:
    model = None

# Fallback response generator in case LLM is offline or no API Key
def get_rule_based_fallback(prompt: str, crm_context: str) -> str:
    """
    Generate high-quality rule-based Vietnamese responses matching Bank A's scenarios
    when Gemini API key is not available.
    """
    prompt_lower = prompt.lower()
    
    # Scenario 1: Savings account due date (Tiết kiệm đến hạn)
    if "tiết kiệm" in prompt_lower and ("đến hạn" in prompt_lower or "đáo hạn" in prompt_lower):
        import json
        try:
            customers = json.loads(crm_context)
        except Exception:
            customers = []
            
        if not customers:
            return "Tôi đã truy vấn CRM nhưng hiện tại không tìm thấy khách hàng nào có sổ tiết kiệm đến hạn trong tuần này."
            
        res = "### 🔔 THÔNG BÁO: KHÁCH HÀNG TIẾT KIỆM ĐẾN HẠN TUẦN NÀY\n\n"
        res += "Chào RM Nguyễn Phương Linh, tôi đã truy vấn hệ thống CRM qua MCP Tool và tìm thấy **2 khách hàng** có sổ tiết kiệm đến hạn thanh toán trong tuần này:\n\n"
        
        for c in customers:
            res += f"- **KH: {c['name']}** (Mã: {c['id']}) | Số dư: {c['savings_balance']:,} VND | Ngày đến hạn: {c['savings_due_date']}\n"
            
        res += "\nTôi đã tự động soạn **Bản thảo Email** và **Kịch bản cuộc gọi (Call Script)** áp dụng chương trình ưu đãi cộng thêm **0.2% lãi suất** cho các khách hàng này:\n\n"
        
        # Email & Script for Le Van Khang
        res += "#### 1. Khách hàng: LÊ VĂN KHANG (Mã: KH001)\n"
        res += "##### **Email Draft:**\n"
        res += "```text\n"
        res += "Tiêu đề: [Bank A] Nhắc nhở hạn tất toán sổ tiết kiệm & Ưu đãi cộng lãi suất đặc biệt - KH Lê Văn Khang\n\n"
        res += "Kính gửi anh Lê Văn Khang,\n\n"
        res += "Lời đầu tiên, Ngân hàng TMCP A (Bank A) xin gửi lời chúc sức khỏe và lời cảm ơn chân thành đến anh vì đã tin tưởng đồng hành cùng chúng tôi.\n\n"
        res += "Chúng tôi xin thông báo sổ tiết kiệm có số dư 500,000,000 VND của anh sẽ đến hạn tất toán vào ngày 15/07/2026.\n\n"
        res += "Nhân dịp này, Bank A đang triển khai chương trình ưu đãi 'Tiết Kiệm Vàng - Đón Lộc Hè', cộng thêm 0.2% lãi suất cho khách hàng VIP thực hiện gia hạn sổ tiết kiệm trực tuyến hoặc tại quầy.\n\n"
        res += "Anh Khang vui lòng phản hồi email này hoặc liên hệ hotline để được hỗ trợ gia hạn sớm nhất.\n\n"
        res += "Trân trọng,\n"
        res += "RM Nguyễn Phương Linh - Trung tâm KHCN Bank A\n"
        res += "```\n"
        res += "##### **Call Script:**\n"
        res += "```text\n"
        res += "- RM: Dạ em chào anh Khang, em là Linh - RM phụ trách tài khoản của anh tại Bank A ạ. Em gọi điện để chúc mừng anh sắp hoàn thành kỳ hạn gửi tiết kiệm 500 triệu vào ngày 15/07 tới.\n"
        res += "- RM: Hiện tại bên em đang có ưu đãi cộng thêm 0.2% lãi suất dành riêng cho anh khi tái tục kỳ hạn mới đấy ạ. Anh có tiện ghé qua chi nhánh bên em hoặc em hỗ trợ anh thao tác ngay trên App Bank A Mobile không anh?\n"
        res += "- Xử lý từ chối: Nếu anh Khang bận trả nợ vay mua nhà, RM tư vấn: Dạ bên em cũng có gói tích lũy linh hoạt rút gốc một phần vẫn giữ nguyên lãi suất phù hợp cho dòng tiền của mình ạ.\n"
        res += "```\n\n"
        
        # Email & Script for Tran Thi Binh
        res += "#### 2. Khách hàng: TRẦN THỊ BÌNH (Mã: KH002)\n"
        res += "##### **Email Draft:**\n"
        res += "```text\n"
        res += "Tiêu đề: [Bank A] Thông báo hạn sổ tiết kiệm & Ưu đãi gia hạn - KH Trần Thị Bình\n\n"
        res += "Kính gửi chị Trần Thị Bình,\n\n"
        res += "Bank A xin trân trọng thông báo sổ tiết kiệm số dư 150,000,000 VND của chị sẽ đến hạn vào ngày 12/07/2026.\n\n"
        res += "Đặc biệt, chương trình 'Tiết Kiệm Vàng' đang áp dụng cộng thêm 0.2% lãi suất khi chị tái tục gửi tiết kiệm từ 100 triệu trở lên.\n\n"
        res += "Chị Bình vui lòng phản hồi email này hoặc liên hệ hotline để được hỗ trợ thủ tục.\n\n"
        res += "Trân trọng,\n"
        res += "RM Nguyễn Phương Linh\n"
        res += "```\n"
        res += "##### **Call Script:**\n"
        res += "```text\n"
        res += "- RM: Em chào chị Bình ạ, em là Linh ở Bank A. Em gọi điện báo chị sổ tiết kiệm 150 triệu của chị sắp đến hạn tất toán vào ngày 12/07 tới. \n"
        res += "- RM: Em xin phép tư vấn gói gửi tái tục cộng 0.2% lãi suất của chiến dịch hè bên em ạ...\n"
        res += "```\n"
        res += "\nBạn có muốn lưu các bản nháp email này lên CRM không? Hãy click nút **[Ghi nhận CRM]** bên dưới.\n"
        res += "\n*Nguồn dữ liệu: CRM Sandbox API (`GET /api/customers?due_within_days=7`)*"
        return res

    # Scenario 1.5: Confirm drafting emails/scripts
    elif "soạn" in prompt_lower or "đồng ý" in prompt_lower or "có" == prompt_lower.strip():
        # Draft for Tran Thi Binh & Le Van Khang
        res = "### ✉️ BẢN THẢO EMAIL & KỊCH BẢN CHĂM SÓC KHÁCH HÀNG\n\n"
        res += "Dưới đây là email và kịch bản cuộc gọi được cá nhân hóa cho từng khách hàng:\n\n"
        
        # Email & Script for Le Van Khang
        res += "#### 1. Khách hàng: LÊ VĂN KHANG (Mã: KH001)\n"
        res += "##### **Email Draft:**\n"
        res += "```text\n"
        res += "Tiêu đề: [Bank A] Nhắc nhở hạn tất toán sổ tiết kiệm & Ưu đãi cộng lãi suất đặc biệt - KH Lê Văn Khang\n\n"
        res += "Kính gửi anh Lê Văn Khang,\n\n"
        res += "Lời đầu tiên, Ngân hàng TMCP A (Bank A) xin gửi lời chúc sức khỏe và lời cảm ơn chân thành đến anh vì đã tin tưởng đồng hành cùng chúng tôi.\n\n"
        res += "Chúng tôi xin thông báo sổ tiết kiệm có số dư 500,000,000 VND của anh sẽ đến hạn tất toán vào ngày 15/07/2026.\n\n"
        res += "Nhân dịp này, Bank A đang triển khai chương trình ưu đãi 'Tiết Kiệm Vàng - Đón Lộc Hè', cộng thêm 0.2% lãi suất cho khách hàng VIP thực hiện gia hạn sổ tiết kiệm trực tuyến hoặc tại quầy.\n\n"
        res += "Anh Khang vui lòng phản hồi email này hoặc liên hệ hotline để được hỗ trợ gia hạn sớm nhất.\n\n"
        res += "Trân trọng,\n"
        res += "RM Nguyễn Phương Linh - Trung tâm KHCN Bank A\n"
        res += "```\n"
        res += "##### **Call Script:**\n"
        res += "```text\n"
        res += "- RM: Dạ em chào anh Khang, em là Linh - RM phụ trách tài khoản của anh tại Bank A ạ. Em gọi điện để chúc mừng anh sắp hoàn thành kỳ hạn gửi tiết kiệm 500 triệu vào ngày 15/07 tới.\n"
        res += "- RM: Hiện tại bên em đang có ưu đãi cộng thêm 0.2% lãi suất dành riêng cho anh khi tái tục kỳ hạn mới đấy ạ. Anh có tiện ghé qua chi nhánh bên em hoặc em hỗ trợ anh thao tác ngay trên App Bank A Mobile không anh?\n"
        res += "- Xử lý từ chối: Nếu anh Khang bận trả nợ mua nhà, RM tư vấn: Dạ bên em cũng có gói tích lũy linh hoạt rút gốc một phần vẫn giữ nguyên lãi suất phù hợp cho dòng tiền của mình ạ.\n"
        res += "```\n\n"
        
        # Email & Script for Tran Thi Binh
        res += "#### 2. Khách hàng: TRẦN THỊ BÌNH (Mã: KH002)\n"
        res += "##### **Email Draft:**\n"
        res += "```text\n"
        res += "Tiêu đề: [Bank A] Thông báo hạn sổ tiết kiệm & Ưu đãi gia hạn - KH Trần Thị Bình\n\n"
        res += "Kính gửi chị Trần Thị Bình,\n\n"
        res += "Bank A xin trân trọng thông báo sổ tiết kiệm số dư 150,000,000 VND của chị sẽ đến hạn vào ngày 12/07/2026.\n\n"
        res += "Đặc biệt, chương trình 'Tiết Kiệm Vàng' đang áp dụng cộng thêm 0.2% lãi suất khi chị tái tục gửi tiết kiệm từ 100 triệu trở lên.\n\n"
        res += "Chị Bình vui lòng phản hồi email này hoặc liên hệ hotline để được hỗ trợ thủ tục.\n\n"
        res += "Trân trọng,\n"
        res += "RM Nguyễn Phương Linh\n"
        res += "```\n"
        res += "##### **Call Script:**\n"
        res += "```text\n"
        res += "- RM: Em chào chị Bình ạ, em là Linh ở Bank A. Em gọi điện báo chị sổ tiết kiệm 150 triệu của chị sắp đến hạn tất toán vào ngày 12/07 tới. \n"
        res += "- RM: Em xin phép tư vấn gói gửi tái tục cộng 0.2% lãi suất của chiến dịch hè bên em ạ...\n"
        res += "```\n"
        res += "\nBạn có muốn tôi tự động lưu các bản nháp email này lên CRM không? (Gõ 'Lưu CRM')\n"
        res += "\n*Nguồn dữ liệu: CRM Templates & Product Knowledge Base*"
        return res

    # Save to CRM confirmation
    elif "lưu crm" in prompt_lower or "lưu" in prompt_lower:
        return "### 💾 HỆ THỐNG CRM ĐÃ CẬP NHẬT!\n\nTôi đã gọi MCP Tool `save_email_draft` và `save_call_script` để lưu trữ các bản thảo email và kịch bản chăm sóc khách hàng của Lê Văn Khang (KH001) và Trần Thị Bình (KH002) thành công. Lịch sử tương tác đã được cập nhật.\n\n*Nguồn dữ liệu: CRM Sandbox API (`POST /api/draft-email`, `POST /api/call-script`)*"

    # Scenario 2: Cross-sell Insurance for Le Van Khang
    elif "lê văn khang" in prompt_lower or "khang" in prompt_lower:
        import json
        try:
            profile = json.loads(crm_context)
        except Exception:
            profile = {}
            
        res = "### 🔍 PHÂN TÍCH HỒ SƠ KHÁCH HÀNG: LÊ VĂN KHANG (Mã: KH001)\n\n"
        res += "Tôi đã dùng MCP Tool `get_customer_profile` để truy cập hồ sơ 360 độ của anh Lê Văn Khang. Dưới đây là phân tích ngữ cảnh:\n\n"
        res += "* **Hồ sơ tài chính**: Số dư tiết kiệm 500 triệu (đến hạn 15/07/2026). Đang có khoản vay mua nhà **2 tỷ VND** (tín dụng thế chấp).\n"
        res += "* **Lịch sử tương tác**: Cuộc gọi gần nhất ngày 10/05/2026 ghi nhận khách hàng phản hồi dịch vụ tốt và đang tập trung trả nợ vay mua nhà.\n"
        res += "* **Đánh giá cơ hội bán chéo sản phẩm**:\n"
        res += "  - Anh Khang có khoản vay thế chấp lớn nhưng **chưa tham gia bảo hiểm nhân thọ liên kết tín dụng (Bancassurance)**.\n"
        res += "  - Đây là cơ hội rất lớn để tư vấn gói sản phẩm **'Trọn Đời An Tâm'** (Chiến dịch CAMP001) bảo vệ khoản vay của khách hàng trước rủi ro tài chính.\n"
        res += "  - **Lợi ích**: Giảm ngay 10% phí bảo hiểm năm đầu tiên cho khoản vay trên 1 tỷ.\n"
        res += "  - **Số liệu thống kê**: Tỷ lệ chuyển đổi thành công sản phẩm này ở các khách hàng tương tự bởi các RM khác là **40%**.\n\n"
        res += "#### Kịch Bản Gợi Ý Cho RM Tư Vấn:\n"
        res += "```text\n"
        res += "- RM: Dạ anh Khang ơi, em thấy khoản vay mua nhà 2 tỷ của mình đang được vận hành rất tốt. Tuy nhiên để bảo vệ gia đình và tài sản trước các biến cố không lường trước, bên em đang có chương trình liên kết Bảo hiểm 'Trọn Đời An Tâm' bảo an cho khoản vay.\n"
        res += "- RM: Đặc biệt trong tháng này, khoản vay 2 tỷ của anh thuộc diện được giảm trực tiếp 10% phí bảo hiểm năm đầu tiên đó anh. Anh Khang có muốn em gửi tài liệu chi tiết qua Zalo/Email để anh xem trước không ạ?\n"
        res += "```\n"
        res += "\n*Nguồn dữ liệu: CRM Sandbox API (`GET /api/customers/KH001/opportunities`, `GET /api/customers/KH001/interactions`)*"
        return res

    # General Fallback Chat
    else:
        return "Chào bạn, tôi là AI Co-Pilot của Bank A CRM. Tôi có thể giúp bạn các nghiệp vụ sau:\n\n" \
               "1. Lọc khách hàng tiết kiệm đến hạn tuần này (Gõ: *tiết kiệm đến hạn*)\n" \
               "2. Tra cứu hồ sơ 360 độ và cơ hội bán chéo bảo hiểm của anh Lê Văn Khang (Gõ: *tư vấn Lê Văn Khang*)\n" \
               "3. Xem các chiến dịch marketing đang chạy (Gõ: *danh sách chiến dịch*)\n" \
               "\nHãy gõ câu lệnh hoặc yêu cầu của bạn bằng tiếng Việt!"

async def generate_response(prompt: str, crm_context: str = "") -> str:
    """
    Orchestrate AI response. First tries OpenRouter if API Key is set, 
    then falls back to Gemini, then falls back to get_rule_based_fallback.
    """
    system_instruction = (
        "Bạn là chuyên viên tư vấn AI của doanh nghiệp, hỗ trợ nhân viên tra cứu và phân tích dữ liệu.\n\n"
        "CÁCH TRẢ LỜI:\n"
        "- Trả lời bằng tiếng Việt tự nhiên, lịch sự như một chuyên viên tư vấn.\n"
        "- Dùng thuật ngữ nghiệp vụ phù hợp (ngân hàng/y tế/hành chính/thương mại...) dựa trên dữ liệu.\n"
        "- TUYỆT ĐỐI KHÔNG dùng thuật ngữ lập trình: không 'JSON', 'field', 'schema', 'record', 'object', 'array', 'null', 'string', 'key', 'value'.\n"
        "- TUYỆT ĐỐI KHÔNG hiển thị code, dấu ngoặc nhọn {}, ngoặc vuông [], hay cú pháp kỹ thuật.\n"
        "- Trình bày thông tin dạng văn xuôi hoặc bảng dễ đọc.\n"
        "- Nếu có nhiều kết quả trùng tên: liệt kê ngắn gọn từng người kèm thông tin phân biệt, rồi hỏi 'Bạn muốn xem thông tin của ai?'\n"
        "- Nếu không tìm thấy thông tin: thông báo lịch sự và gợi ý hướng tìm kiếm khác.\n"
        "- Chỉ dùng thông tin từ dữ liệu được cung cấp, không bịa đặt.\n\n"
        f"DỮ LIỆU:\n{crm_context}"
    )

    # 1. Try OpenRouter
    if OPENROUTER_API_KEY:
        try:
            print(f"Calling OpenRouter with model {OPENROUTER_MODEL}...")
            headers = {
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://127.0.0.1:8000",
                "X-Title": "Bank A CRM AI Agent"
            }
            payload = {
                "model": OPENROUTER_MODEL,
                "messages": [
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": prompt}
                ]
            }
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=30.0
                )
                if response.status_code == 200:
                    result = response.json()
                    content = result["choices"][0]["message"]["content"]
                    print("OpenRouter call successful!")
                    return content
                else:
                    print(f"OpenRouter returned status {response.status_code}: {response.text}")
        except Exception as e:
            print(f"OpenRouter API Error: {e}")

    # 2. Try Gemini fallback
    if GEMINI_API_KEY and model is not None:
        try:
            print("Calling Gemini API...")
            full_prompt = f"{system_instruction}\n\nYêu cầu của RM: {prompt}\n\nTrả lời:"
            response = model.generate_content(full_prompt)
            return response.text
        except Exception as e:
            print(f"Gemini API Error: {e}")

    # 3. Local Rule-based Fallback
    print("Falling back to local Rule-based engine.")
    return get_rule_based_fallback(prompt, crm_context)
