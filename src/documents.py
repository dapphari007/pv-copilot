"""Shared text extraction from uploaded documents (TXT / PDF / DOCX)."""
from __future__ import annotations

import io


def read_document(data: bytes, name: str) -> str:
    """Extract plain text from uploaded file bytes by extension."""
    lower = (name or "").lower()
    if lower.endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    if lower.endswith(".docx"):
        import docx

        document = docx.Document(io.BytesIO(data))
        return "\n".join(p.text for p in document.paragraphs)
    return data.decode("utf-8", errors="replace")
