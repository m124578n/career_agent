"""履歷解析（M1）：把上傳的 PDF / Word / 純文字轉成純文字。"""

import io

from docx import Document
from pypdf import PdfReader


def parse_resume(filename: str, data: bytes) -> str:
    """依副檔名解析履歷檔案，回傳純文字。"""
    name = filename.lower()
    if name.endswith(".pdf"):
        return _parse_pdf(data)
    if name.endswith(".docx"):
        return _parse_docx(data)
    if name.endswith(".txt"):
        return data.decode("utf-8", errors="ignore")
    raise ValueError(f"不支援的履歷格式：{filename}（支援 PDF / DOCX / TXT）")


def _parse_pdf(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    return "\n".join(page.extract_text() or "" for page in reader.pages).strip()


def _parse_docx(data: bytes) -> str:
    doc = Document(io.BytesIO(data))
    return "\n".join(p.text for p in doc.paragraphs).strip()
