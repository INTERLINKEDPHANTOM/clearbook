from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
from pandas.errors import EmptyDataError, ParserError


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
    if not file_path.exists() or file_path.stat().st_size == 0:
        raise ValueError("File appears to be empty or unreadable")

    try:
        dataframe = pd.read_csv(file_path, encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("File has unsupported encoding. Please upload UTF-8 CSV.") from exc
    except EmptyDataError as exc:
        raise ValueError("File appears to be empty or unreadable") from exc
    except ParserError as exc:
        raise ValueError("CSV file is malformed and could not be parsed") from exc
    except Exception as exc:
        raise ValueError("File appears to be empty or unreadable") from exc

    if dataframe.empty:
        raise ValueError("File appears to be empty or unreadable")

    dataframe.columns = [str(column).strip() for column in dataframe.columns]
    if not dataframe.columns.any() or any(
        not column or column.startswith("Unnamed:") for column in dataframe.columns
    ):
        raise ValueError("File is missing required columns")

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
