# Project Rules and Target Specifications: Paperless Meetings

This project is transitioning from a bank CRM assistant to the **Paperless Meetings** GovTech assistant for the Department of Science and Technology of Dien Bien province (Sở Khoa học và Công nghệ tỉnh Điện Biên).

## 📌 Core Requirements

1. **Smart Summarization**:
   - Upload PDF/Word files (40+ pages).
   - Return structured summary containing: Context (Bối cảnh), Main Content (Nội dung chính), Decision Points (Điểm quyết định), and Impact (Tác động).
   - Must complete analysis in `< 60 seconds`.

2. **Highlight & Explain Terminology**:
   - Auto-detect at least 10 specialized terms (legal, administrative, technical).
   - Provide brief, easy-to-understand Vietnamese definitions and note the pages where they appear.
   - Interactive document reader allows scrolling to the page and highlighting the term when clicked.

3. **Suggested Questions**:
   - Auto-generate at least 5 high-quality critical-thinking questions to help officials prepare for discussions.
   - Propose related files or reference regulations.

4. **Document-Grounded Q&A**:
   - Natural Vietnamese chat about the document.
   - AI answers must cite specific pages or sections.

5. **Architecture & Deliverables**:
   - Architecture document and 1-page deck covering processing model, data sources, and real deployment roadmap at the People's Committee.

---

## 🏗️ Architecture Design & Changes (To be implemented when requested)

### Backend (`agent_backend`)
- Add `pypdf` and `python-docx` for document parsing.
- Implement `/api/upload` endpoint to receive documents and extract page-by-page text.
- Implement endpoints: `/api/summary`, `/api/terms`, `/api/questions` to serve the parsed data.
- Modify `/api/chat` to include document context.

### MCP Server (`mcp_server`)
- Clean up old CRM tools.
- Add document tools:
  - `search_in_document(query)`
  - `get_page_content(page_num)`
  - `get_terminology_details(term)`

### Frontend (`frontend`)
- Change visual theme to GovTech style (dark glassmorphism, elegant deep green and neon/gold accents).
- Implement a two-column layout:
  - **Left column**: Document Reader (page-by-page navigation) + tabs for Smart Summary, Terminology definitions (with page-jump links), and Suggested Questions.
  - **Right column**: Chat widget + live API/MCP trace console.

---

## 🚫 Critical Instructions
- Do not start the CRM server on port 8001; run only the main backend on port 8000.
- Do not modify source code until the user explicitly requests to proceed.
