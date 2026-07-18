# agent_backend/document_processor.py
import os
import pypdf
import docx
import logging

logger = logging.getLogger("agent_backend.document_processor")

def parse_pdf(file_path: str) -> list[dict]:
    """Parse PDF page by page."""
    try:
        reader = pypdf.PdfReader(file_path)
        pages = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            pages.append({
                "page_num": i + 1,
                "text": text
            })
        logger.info(f"Successfully parsed PDF: {file_path} with {len(pages)} pages.")
        return pages
    except Exception as e:
        logger.error(f"Error parsing PDF {file_path}: {e}")
        raise e

def parse_docx(file_path: str) -> list[dict]:
    """Parse DOCX approximating pages (every ~500 words or by paragraph chunks)."""
    try:
        doc = docx.Document(file_path)
        pages = []
        current_paragraphs = []
        current_word_count = 0
        page_num = 1

        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                continue
            words = text.split()
            current_paragraphs.append(text)
            current_word_count += len(words)

            # Split page if it exceeds 500 words
            if current_word_count >= 500:
                pages.append({
                    "page_num": page_num,
                    "text": "\n".join(current_paragraphs)
                })
                current_paragraphs = []
                current_word_count = 0
                page_num += 1

        # Add remaining text
        if current_paragraphs:
            pages.append({
                "page_num": page_num,
                "text": "\n".join(current_paragraphs)
            })

        logger.info(f"Successfully parsed DOCX: {file_path} into {len(pages)} page chunks.")
        return pages
    except Exception as e:
        logger.error(f"Error parsing DOCX {file_path}: {e}")
        raise e

def parse_document(file_path: str) -> list[dict]:
    """Extract text from PDF or DOCX file."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        return parse_pdf(file_path)
    elif ext in [".docx", ".doc"]:
        return parse_docx(file_path)
    else:
        raise ValueError(f"Unsupported file format: {ext}")
