# ClearBook Day 1 Handoff

## Snapshot
- Date: 2026-04-24
- Workspace root: /home/primal/Desktop/clearbook,store
- Project root: /home/primal/Desktop/clearbook,store/clearbook
- Scope completed: Day 1 only

## 1) Every file created and exact path

1. /home/primal/Desktop/clearbook,store/clearbook/backend/main.py
2. /home/primal/Desktop/clearbook,store/clearbook/backend/models.py
3. /home/primal/Desktop/clearbook,store/clearbook/backend/parsers/csv_parser.py
4. /home/primal/Desktop/clearbook,store/clearbook/backend/parsers/excel_parser.py
5. /home/primal/Desktop/clearbook,store/clearbook/backend/parsers/invoice_parser.py
6. /home/primal/Desktop/clearbook,store/clearbook/backend/requirements.txt
7. /home/primal/Desktop/clearbook,store/clearbook/backend/ai/analyzer.py
8. /home/primal/Desktop/clearbook,store/clearbook/backend/reports/pdf_generator.py
9. /home/primal/Desktop/clearbook,store/clearbook/frontend/index.html
10. /home/primal/Desktop/clearbook,store/clearbook/backend/__init__.py
11. /home/primal/Desktop/clearbook,store/clearbook/backend/parsers/__init__.py
12. /home/primal/Desktop/clearbook,store/clearbook/backend/ai/__init__.py
13. /home/primal/Desktop/clearbook,store/clearbook/backend/reports/__init__.py

Created directories:
- /home/primal/Desktop/clearbook,store/clearbook/uploads
- /home/primal/Desktop/clearbook,store/clearbook/backend
- /home/primal/Desktop/clearbook,store/clearbook/backend/parsers
- /home/primal/Desktop/clearbook,store/clearbook/backend/ai
- /home/primal/Desktop/clearbook,store/clearbook/backend/reports
- /home/primal/Desktop/clearbook,store/clearbook/frontend

## 2) Complete code of each file

### /home/primal/Desktop/clearbook,store/clearbook/backend/main.py
~~~python
from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware

from backend.models import UploadPreviewResponse
from backend.parsers.csv_parser import parse_csv
from backend.parsers.excel_parser import parse_excel
from backend.parsers.invoice_parser import parse_invoice_pdf

MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024
UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {
    ".csv": "csv",
    ".xls": "excel",
    ".xlsx": "excel",
    ".pdf": "pdf",
}

ALLOWED_CONTENT_TYPES = {
    ".csv": {
        "text/csv",
        "application/csv",
        "application/vnd.ms-excel",
        "application/octet-stream",
    },
    ".xls": {
        "application/vnd.ms-excel",
        "application/octet-stream",
    },
    ".xlsx": {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/octet-stream",
    },
    ".pdf": {
        "application/pdf",
        "application/octet-stream",
    },
}


def _cors_origins() -> list[str]:
    raw_origins = os.getenv("CLEARBOOK_CORS_ORIGINS", "*").strip()
    if raw_origins == "*":
        return ["*"]
    return [origin.strip() for origin in raw_origins.split(",") if origin.strip()]


app = FastAPI(
    title="ClearBook API",
    version="0.1.0",
    description="Day 1 API for file upload and parsing preview.",
)

cors_origins = _cors_origins()
allow_credentials = cors_origins != ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}


def _validate_file_type(upload_file: UploadFile) -> tuple[str, str]:
    if not upload_file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required.",
        )

    suffix = Path(upload_file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS.keys()))
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file extension. Allowed: {allowed}",
        )

    content_type = (upload_file.content_type or "").lower()
    allowed_types = ALLOWED_CONTENT_TYPES.get(suffix, set())
    if content_type and content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"Invalid content type '{content_type}' for {suffix}. "
                f"Allowed: {', '.join(sorted(allowed_types))}"
            ),
        )

    return suffix, ALLOWED_EXTENSIONS[suffix]


def _save_upload_temporarily(upload_file: UploadFile, suffix: str) -> tuple[Path, str, int]:
    generated_name = f"{uuid4().hex}{suffix}"
    destination = UPLOAD_DIR / generated_name

    total_size = 0
    chunk_size = 1024 * 1024

    with destination.open("wb") as output_file:
        while True:
            chunk = upload_file.file.read(chunk_size)
            if not chunk:
                break
            total_size += len(chunk)

            if total_size > MAX_UPLOAD_SIZE_BYTES:
                output_file.close()
                destination.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="File exceeds 10MB size limit.",
                )

            output_file.write(chunk)

    if total_size == 0:
        destination.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    upload_file.file.seek(0)
    return destination, generated_name, total_size


def _parse_file(file_type: str, file_path: Path) -> dict:
    if file_type == "csv":
        return parse_csv(file_path)
    if file_type == "excel":
        return parse_excel(file_path)
    if file_type == "pdf":
        return parse_invoice_pdf(file_path)

    raise HTTPException(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail="Unsupported file type.",
    )


@app.post("/upload", response_model=UploadPreviewResponse, status_code=status.HTTP_201_CREATED)
def upload_file(file: UploadFile = File(...)) -> UploadPreviewResponse:
    suffix, file_type = _validate_file_type(file)
    saved_path, saved_name, size_bytes = _save_upload_temporarily(file, suffix)

    try:
        parsed_data = _parse_file(file_type=file_type, file_path=saved_path)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to parse uploaded file: {exc}",
        ) from exc

    return UploadPreviewResponse(
        filename=file.filename,
        saved_as=saved_name,
        file_type=file_type,
        size_bytes=size_bytes,
        parsed_data=parsed_data,
    )
~~~

### /home/primal/Desktop/clearbook,store/clearbook/backend/models.py
~~~python
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class UploadPreviewResponse(BaseModel):
    filename: str
    saved_as: str
    file_type: Literal["csv", "excel", "pdf"]
    size_bytes: int = Field(..., ge=1, le=10 * 1024 * 1024)
    parsed_data: dict[str, Any]
~~~

### /home/primal/Desktop/clearbook,store/clearbook/backend/parsers/csv_parser.py
~~~python
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


def _normalize_value(value: Any) -> Any:
    if value is None:
        return None

    if hasattr(value, "item"):
        try:
            value = value.item()
        except Exception:
            pass

    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass

    return value


def parse_csv(file_path: Path, preview_rows: int = 20) -> dict[str, Any]:
    dataframe = pd.read_csv(file_path)
    dataframe.columns = [str(column).strip() for column in dataframe.columns]
    dataframe = dataframe.where(pd.notna(dataframe), None)

    preview_records = dataframe.head(preview_rows).to_dict(orient="records")
    preview_records = [
        {key: _normalize_value(value) for key, value in row.items()}
        for row in preview_records
    ]

    return {
        "columns": list(dataframe.columns),
        "row_count": int(len(dataframe)),
        "preview": preview_records,
    }
~~~

### /home/primal/Desktop/clearbook,store/clearbook/backend/parsers/excel_parser.py
~~~python
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from openpyxl import load_workbook


def _normalize_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def parse_excel(file_path: Path, preview_rows: int = 20) -> dict[str, Any]:
    workbook = load_workbook(filename=file_path, data_only=True, read_only=True)

    try:
        worksheet = workbook.active
        row_iterator = worksheet.iter_rows(values_only=True)

        header_row = next(row_iterator, None)
        if header_row is None:
            return {
                "columns": [],
                "row_count": 0,
                "preview": [],
            }

        headers: list[str] = []
        for index, value in enumerate(header_row, start=1):
            if value is None or not str(value).strip():
                headers.append(f"column_{index}")
            else:
                headers.append(str(value).strip())

        preview: list[dict[str, Any]] = []
        row_count = 0

        for row in row_iterator:
            row_count += 1
            if len(preview) >= preview_rows:
                continue

            normalized_row = list(row)
            if len(normalized_row) < len(headers):
                normalized_row.extend([None] * (len(headers) - len(normalized_row)))

            preview.append(
                {
                    headers[i]: _normalize_value(normalized_row[i])
                    for i in range(len(headers))
                }
            )

        return {
            "columns": headers,
            "row_count": row_count,
            "preview": preview,
        }
    finally:
        workbook.close()
~~~

### /home/primal/Desktop/clearbook,store/clearbook/backend/parsers/invoice_parser.py
~~~python
from __future__ import annotations

from pathlib import Path
from typing import Any

from pypdf import PdfReader


def parse_invoice_pdf(
    file_path: Path,
    preview_chars: int = 2000,
    max_pages_for_preview: int = 3,
) -> dict[str, Any]:
    reader = PdfReader(str(file_path))

    extracted_pages: list[str] = []
    for page in reader.pages[:max_pages_for_preview]:
        extracted_pages.append((page.extract_text() or "").strip())

    preview_text = " ".join(part for part in extracted_pages if part)
    preview_text = " ".join(preview_text.split())

    return {
        "page_count": len(reader.pages),
        "preview_text": preview_text[:preview_chars],
        "truncated": len(preview_text) > preview_chars,
    }
~~~

### /home/primal/Desktop/clearbook,store/clearbook/backend/requirements.txt
~~~text
fastapi>=0.111,<1.0
uvicorn[standard]>=0.30,<1.0
python-multipart>=0.0.9,<1.0
pandas>=2.2,<3.0
openpyxl>=3.1,<4.0
pypdf>=4.2,<6.0
~~~

### /home/primal/Desktop/clearbook,store/clearbook/backend/ai/analyzer.py
~~~python
from __future__ import annotations

from typing import Any


def analyze_with_groq(payload: dict[str, Any]) -> dict[str, Any]:
    raise NotImplementedError("Day 2: Groq integration will be implemented here.")
~~~

### /home/primal/Desktop/clearbook,store/clearbook/backend/reports/pdf_generator.py
~~~python
from __future__ import annotations

from typing import Any


def generate_report_pdf(data: dict[str, Any], output_path: str) -> str:
    raise NotImplementedError("Day 2: PDF report generation will be implemented here.")
~~~

### /home/primal/Desktop/clearbook,store/clearbook/frontend/index.html
~~~html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ClearBook Upload</title>
  <style>
    :root {
      --bg: #f7f9fc;
      --card: #ffffff;
      --text: #0f172a;
      --muted: #475569;
      --accent: #0ea5e9;
      --accent-2: #0369a1;
      --border: #cbd5e1;
      --danger: #b91c1c;
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      min-height: 100vh;
      font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
      background: linear-gradient(180deg, #eef6ff 0%, var(--bg) 60%);
      color: var(--text);
      display: grid;
      place-items: center;
      padding: 20px;
    }

    .container {
      width: min(720px, 100%);
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 14px;
      box-shadow: 0 12px 30px rgba(2, 6, 23, 0.08);
      padding: 22px;
    }

    h1 {
      margin: 0 0 8px;
      font-size: 1.4rem;
    }

    p {
      margin: 0 0 16px;
      color: var(--muted);
    }

    .dropzone {
      border: 2px dashed var(--border);
      border-radius: 12px;
      padding: 30px 16px;
      text-align: center;
      cursor: pointer;
      transition: border-color 0.2s ease, background 0.2s ease;
      background: #f8fbff;
    }

    .dropzone.dragover {
      border-color: var(--accent);
      background: #edf8ff;
    }

    .dropzone strong {
      display: block;
      margin-bottom: 8px;
    }

    .file-info {
      margin-top: 10px;
      color: var(--muted);
      font-size: 0.95rem;
      min-height: 1.2em;
    }

    .actions {
      margin-top: 16px;
      display: flex;
      gap: 10px;
    }

    button {
      border: none;
      border-radius: 10px;
      background: var(--accent);
      color: #fff;
      font-size: 0.95rem;
      font-weight: 600;
      padding: 11px 16px;
      cursor: pointer;
      transition: background 0.2s ease;
    }

    button:hover { background: var(--accent-2); }
    button:disabled {
      cursor: not-allowed;
      opacity: 0.65;
    }

    .status {
      margin-top: 14px;
      font-size: 0.93rem;
      color: var(--muted);
      min-height: 1.2em;
    }

    .status.error { color: var(--danger); }

    pre {
      margin-top: 16px;
      background: #0b1220;
      color: #dbeafe;
      border-radius: 10px;
      padding: 14px;
      max-height: 320px;
      overflow: auto;
      font-size: 0.85rem;
    }

    @media (max-width: 640px) {
      .container { padding: 16px; }
      .dropzone { padding: 24px 12px; }
      .actions { flex-direction: column; }
      button { width: 100%; }
    }
  </style>
</head>
<body>
  <main class="container">
    <h1>ClearBook File Upload</h1>
    <p>Upload one CSV, Excel, or PDF file (max 10MB) to preview parsed data.</p>

    <div id="dropzone" class="dropzone" role="button" tabindex="0">
      <strong>Drag and drop your file here</strong>
      <span>or click to select</span>
      <div id="fileInfo" class="file-info"></div>
    </div>

    <div class="actions">
      <button id="uploadBtn" disabled>Submit</button>
    </div>

    <div id="status" class="status"></div>
    <pre id="result" hidden></pre>

    <input id="fileInput" type="file" accept=".csv,.xls,.xlsx,.pdf" hidden>
  </main>

  <script>
    const API_URL = "http://localhost:8000/upload";
    const MAX_SIZE = 10 * 1024 * 1024;

    const dropzone = document.getElementById("dropzone");
    const fileInput = document.getElementById("fileInput");
    const uploadBtn = document.getElementById("uploadBtn");
    const fileInfo = document.getElementById("fileInfo");
    const status = document.getElementById("status");
    const result = document.getElementById("result");

    let selectedFile = null;

    function setStatus(message, isError = false) {
      status.textContent = message;
      status.classList.toggle("error", isError);
    }

    function updateSelection(file) {
      const allowed = [".csv", ".xls", ".xlsx", ".pdf"];
      const extension = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();

      if (!allowed.includes(extension)) {
        selectedFile = null;
        uploadBtn.disabled = true;
        fileInfo.textContent = "";
        setStatus("Invalid file type. Use CSV, XLS, XLSX, or PDF.", true);
        return;
      }

      if (file.size > MAX_SIZE) {
        selectedFile = null;
        uploadBtn.disabled = true;
        fileInfo.textContent = "";
        setStatus("File exceeds 10MB.", true);
        return;
      }

      selectedFile = file;
      uploadBtn.disabled = false;
      fileInfo.textContent = file.name + " (" + (file.size / 1024).toFixed(1) + " KB)";
      setStatus("Ready to upload.");
      result.hidden = true;
    }

    dropzone.addEventListener("click", () => fileInput.click());
    dropzone.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        fileInput.click();
      }
    });

    dropzone.addEventListener("dragover", (event) => {
      event.preventDefault();
      dropzone.classList.add("dragover");
    });

    dropzone.addEventListener("dragleave", () => {
      dropzone.classList.remove("dragover");
    });

    dropzone.addEventListener("drop", (event) => {
      event.preventDefault();
      dropzone.classList.remove("dragover");
      if (event.dataTransfer.files.length) {
        updateSelection(event.dataTransfer.files[0]);
      }
    });

    fileInput.addEventListener("change", () => {
      if (fileInput.files.length) {
        updateSelection(fileInput.files[0]);
      }
    });

    uploadBtn.addEventListener("click", async () => {
      if (!selectedFile) {
        setStatus("Select a file first.", true);
        return;
      }

      uploadBtn.disabled = true;
      setStatus("Uploading and parsing...");

      try {
        const formData = new FormData();
        formData.append("file", selectedFile);

        const response = await fetch(API_URL, {
          method: "POST",
          body: formData,
        });

        const payload = await response.json();

        if (!response.ok) {
          throw new Error(payload.detail || "Upload failed.");
        }

        setStatus("Upload successful.");
        result.textContent = JSON.stringify(payload, null, 2);
        result.hidden = false;
      } catch (error) {
        setStatus(error.message || "Unexpected error.", true);
        result.hidden = true;
      } finally {
        uploadBtn.disabled = false;
      }
    });
  </script>
</body>
</html>
~~~

### /home/primal/Desktop/clearbook,store/clearbook/backend/__init__.py
~~~text
(empty file)
~~~

### /home/primal/Desktop/clearbook,store/clearbook/backend/parsers/__init__.py
~~~text
(empty file)
~~~

### /home/primal/Desktop/clearbook,store/clearbook/backend/ai/__init__.py
~~~text
(empty file)
~~~

### /home/primal/Desktop/clearbook,store/clearbook/backend/reports/__init__.py
~~~text
(empty file)
~~~

## 3) What each file does

- backend/main.py: FastAPI app, CORS setup, health route, upload route, validation, temporary file save, parser dispatch.
- backend/models.py: Pydantic response schema for upload preview payload.
- backend/parsers/csv_parser.py: CSV parsing via pandas and preview JSON construction.
- backend/parsers/excel_parser.py: Excel parsing via openpyxl and preview JSON construction.
- backend/parsers/invoice_parser.py: PDF text extraction preview via pypdf.
- backend/requirements.txt: Day 1 backend dependencies.
- backend/ai/analyzer.py: Day 2 placeholder for Groq analysis integration.
- backend/reports/pdf_generator.py: Day 2 placeholder for generated report PDFs.
- frontend/index.html: Minimal drag and drop upload page posting to backend.
- backend/__init__.py: Python package marker.
- backend/parsers/__init__.py: Python package marker.
- backend/ai/__init__.py: Python package marker.
- backend/reports/__init__.py: Python package marker.

## 4) What is working and what is not

### Working
- FastAPI backend compiles and starts.
- Health endpoint exists at GET /health.
- Upload endpoint exists at POST /upload.
- Accepts CSV, XLS, XLSX, PDF.
- 10MB file size limit enforced server side while streaming write.
- Extension and MIME validation included.
- Uploads are saved to uploads with UUID filenames.
- CSV and Excel are parsed into clean JSON preview.
- PDF parser returns text preview and page count.
- Frontend supports drag/drop, click select, submit, and JSON result display.

### Not working yet or not implemented (by design for Day 1)
- Groq API integration is not implemented.
- llama-3.3-70b-versatile model usage is not implemented yet.
- Clean report PDF generation is not implemented yet.
- No auth, DB, queue, or background workers.
- No test suite yet.

## 5) Dependencies or packages used

From backend/requirements.txt:
- fastapi>=0.111,<1.0
- uvicorn[standard]>=0.30,<1.0
- python-multipart>=0.0.9,<1.0
- pandas>=2.2,<3.0
- openpyxl>=3.1,<4.0
- pypdf>=4.2,<6.0

Standard library modules used:
- os
- pathlib
- uuid
- datetime
- decimal
- typing

Frontend packages:
- none (plain HTML/CSS/JS)

## 6) Manual setup required

### Required setup
1. Ensure Python 3 is installed.
2. Create and activate a virtual environment.
3. Install backend dependencies.
4. Run backend server from project root.
5. Open frontend/index.html in browser.

### Commands
~~~bash
cd /home/primal/Desktop/clearbook,store/clearbook
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r backend/requirements.txt
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
~~~

### Optional env var
- CLEARBOOK_CORS_ORIGINS
  - Default: *
  - Example production value:
~~~bash
export CLEARBOOK_CORS_ORIGINS="https://app.clearbook.com,https://admin.clearbook.com"
~~~

### Folder requirements
- uploads directory must be writable by backend process.
- It is auto-created by backend/main.py if missing.

## Verified status at handoff
- Backend Python files compile successfully.
- Temporary __pycache__ directories were removed.
- Final files currently present:

1. ./backend/ai/analyzer.py
2. ./backend/ai/__init__.py
3. ./backend/__init__.py
4. ./backend/main.py
5. ./backend/models.py
6. ./backend/parsers/csv_parser.py
7. ./backend/parsers/excel_parser.py
8. ./backend/parsers/__init__.py
9. ./backend/parsers/invoice_parser.py
10. ./backend/reports/__init__.py
11. ./backend/reports/pdf_generator.py
12. ./backend/requirements.txt
13. ./frontend/index.html

## Next AI continuation targets
1. Implement Groq integration in backend/ai/analyzer.py using llama-3.3-70b-versatile.
2. Call analyzer from backend/main.py after parsing.
3. Implement report PDF generation in backend/reports/pdf_generator.py.
4. Add automated tests for /upload and parsers.
