from __future__ import annotations

from pathlib import Path
from typing import Any

from pypdf import PdfReader


def parse_invoice_pdf(
    file_path: Path,
    preview_chars: int = 2000,
    max_pages_for_preview: int = 3,
) -> dict[str, Any]:
    if not file_path.exists() or file_path.stat().st_size == 0:
        raise ValueError("File appears to be empty or unreadable")

    try:
        reader = PdfReader(str(file_path))
    except Exception as exc:
        raise ValueError("File appears to be malformed or unreadable") from exc

    if len(reader.pages) == 0:
        raise ValueError("File appears to be empty or unreadable")

    extracted_pages: list[str] = []
    try:
        for page in reader.pages[:max_pages_for_preview]:
            extracted_pages.append((page.extract_text() or "").strip())
    except Exception as exc:
        raise ValueError("File appears to be malformed or unreadable") from exc

    preview_text = " ".join(part for part in extracted_pages if part)
    preview_text = " ".join(preview_text.split())

    if not preview_text:
        raise ValueError("File appears to be empty, unreadable, or missing required fields")

    return {
        "page_count": len(reader.pages),
        "preview_text": preview_text[:preview_chars],
        "truncated": len(preview_text) > preview_chars,
    }
