from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

from backend.ai.analyzer import analyze
from backend.parsers.csv_parser import parse_csv
from backend.parsers.excel_parser import parse_excel
from backend.parsers.invoice_parser import parse_invoice_pdf
from backend.reports.pdf_generator import generate_pdf

load_dotenv()

if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO)

logger = logging.getLogger("clearbook")

MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024
UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads"
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
FRONTEND_INDEX = FRONTEND_DIR / "index.html"
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

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.on_event("startup")
def require_groq_api_key() -> None:
    if not os.getenv("GROQ_API_KEY"):
        logger.error(
            "GROQ_API_KEY is missing. Set GROQ_API_KEY in the environment before starting ClearBook."
        )
        raise SystemExit(1)


@app.get("/", include_in_schema=False)
def serve_frontend() -> FileResponse:
    if not FRONTEND_INDEX.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Frontend index file not found.",
        )
    return FileResponse(FRONTEND_INDEX)


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

    try:
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
    except HTTPException:
        raise
    except OSError as exc:
        destination.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not store uploaded file. Please try again.",
        ) from exc

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


def _safe_delete(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("Failed to delete file '%s': %s", path.name, exc)


def _cleanup_files(paths: list[Path], request_id: str) -> None:
    seen: set[Path] = set()
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        _safe_delete(path)

    if seen:
        logger.info("upload request %s cleanup_complete file_count=%d", request_id, len(seen))


@app.post("/upload")
def upload_file(files: list[UploadFile] = File(...)) -> FileResponse:
    request_id = uuid4().hex[:12]
    combined_entries: list[dict[str, Any]] = []
    input_names: list[str] = []
    saved_paths: list[Path] = []
    uploaded_file_sizes: list[tuple[str, int]] = []
    generated_pdf_path: Path | None = None

    try:
        if not files:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one file is required.",
            )

        for upload in files:
            suffix, file_type = _validate_file_type(upload)
            saved_path, saved_name, size_bytes = _save_upload_temporarily(upload, suffix)
            saved_paths.append(saved_path)

            display_name = upload.filename or saved_name
            uploaded_file_sizes.append((display_name, size_bytes))
            logger.info(
                "upload request %s file='%s' size_bytes=%d",
                request_id,
                display_name,
                size_bytes,
            )

            try:
                parsed_data = _parse_file(file_type=file_type, file_path=saved_path)
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Failed to parse uploaded file '{display_name}': {exc}",
                ) from exc
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        f"Failed to parse uploaded file '{display_name}'. "
                        "Please verify the file and try again."
                    ),
                ) from exc

            input_names.append(display_name)
            combined_entries.append(
                {
                    "filename": upload.filename,
                    "saved_as": saved_name,
                    "file_type": file_type,
                    "size_bytes": size_bytes,
                    "parsed_data": parsed_data,
                }
            )

        combined_payload = {
            "files_processed": len(combined_entries),
            "files": combined_entries,
        }

        try:
            ai_analysis = analyze(combined_payload)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"AI analysis failed: {exc}",
            ) from exc

        try:
            generated_pdf_path = generate_pdf(
                ai_analysis=ai_analysis,
                original_filename=", ".join(input_names),
                files_processed=len(combined_entries),
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Report generation failed: {exc}",
            ) from exc

        if not generated_pdf_path.exists() or generated_pdf_path.stat().st_size == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Report generation failed: generated PDF is empty.",
            )

        logger.info(
            "upload request %s status=succeeded files=%s",
            request_id,
            uploaded_file_sizes,
        )

        return FileResponse(
            path=generated_pdf_path,
            media_type="application/pdf",
            filename="clearbook_report.pdf",
            background=BackgroundTask(_cleanup_files, saved_paths + [generated_pdf_path], request_id),
        )
    except HTTPException as exc:
        logger.warning(
            "upload request %s status=failed files=%s detail=%s",
            request_id,
            uploaded_file_sizes,
            exc.detail,
        )
        _cleanup_files(saved_paths + ([generated_pdf_path] if generated_pdf_path else []), request_id)
        raise
    except Exception as exc:
        logger.exception(
            "upload request %s status=failed files=%s error=%s",
            request_id,
            uploaded_file_sizes,
            exc,
        )
        _cleanup_files(saved_paths + ([generated_pdf_path] if generated_pdf_path else []), request_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected server error while processing upload. Please try again.",
        ) from exc
