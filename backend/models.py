from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class UploadPreviewResponse(BaseModel):
    filename: str
    saved_as: str
    file_type: Literal["csv", "excel", "pdf"]
    size_bytes: int = Field(..., ge=1, le=10 * 1024 * 1024)
    parsed_data: dict[str, Any]
    ai_analysis: dict[str, Any] | None = None
