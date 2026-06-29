from __future__ import annotations

import io


def parse_resume(filename: str, data: bytes) -> str:
    """依副檔名解析履歷檔，回純文字。支援 PDF / TXT。"""
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        return _parse_pdf(data)
    if name.endswith(".txt"):
        return data.decode("utf-8", errors="ignore").strip()
    raise ValueError(f"不支援的履歷格式：{filename}（支援 PDF / TXT）")


def _parse_pdf(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\n".join(page.extract_text() or "" for page in reader.pages).strip()
