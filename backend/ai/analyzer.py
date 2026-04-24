from __future__ import annotations

import json
import os
from typing import Any

from dotenv import load_dotenv
from groq import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    Groq,
    PermissionDeniedError,
    RateLimitError,
)

MODEL_NAME = "llama-3.3-70b-versatile"

load_dotenv()


def _extract_json(content: str) -> dict[str, Any]:
    stripped = content.strip()
    if not stripped:
        return {}

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(stripped[start : end + 1])
        raise


def _normalize_analysis(data: dict[str, Any]) -> dict[str, Any]:
    category_breakdown = data.get("category_breakdown")
    if not isinstance(category_breakdown, dict):
        category_breakdown = {}

    date_range = data.get("date_range")
    if not isinstance(date_range, dict):
        date_range = {"start_date": None, "end_date": None}
    else:
        date_range = {
            "start_date": date_range.get("start_date"),
            "end_date": date_range.get("end_date"),
        }

    anomalies = data.get("anomalies")
    if not isinstance(anomalies, list):
        anomalies = []

    return {
        "total_income": data.get("total_income"),
        "total_expenses": data.get("total_expenses"),
        "category_breakdown": category_breakdown,
        "date_range": date_range,
        "anomalies": anomalies,
    }


def analyze(parsed_data: dict[str, Any]) -> dict[str, Any]:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set.")

    client = Groq(api_key=api_key)

    system_prompt = (
        "You are a financial analysis assistant. "
        "Return only valid JSON with this exact top-level schema: "
        "{"
        '"total_income": number|null, '
        '"total_expenses": number|null, '
        '"category_breakdown": object, '
        '"date_range": {"start_date": string|null, "end_date": string|null}, '
        '"anomalies": array'
        "}."
    )

    user_prompt = (
        "Analyze this parsed financial data and extract: total income, total expenses, "
        "category breakdown, date range, and any anomalies (unexpected spikes, duplicates, "
        "negative values where unusual, outliers, or missing critical fields).\n\n"
        f"parsed_data:\n{json.dumps(parsed_data, ensure_ascii=True, default=str)}"
    )

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            temperature=0.1,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            timeout=30.0,
        )
    except APITimeoutError as exc:
        raise RuntimeError("Groq API timed out. Please try again.") from exc
    except RateLimitError as exc:
        raise RuntimeError("Groq API rate limit reached. Please retry shortly.") from exc
    except (AuthenticationError, PermissionDeniedError) as exc:
        raise RuntimeError("Groq API authentication failed. Check GROQ_API_KEY.") from exc
    except APIConnectionError as exc:
        raise RuntimeError("Could not connect to Groq API. Please try again.") from exc
    except APIStatusError as exc:
        raise RuntimeError(f"Groq API request failed with status {exc.status_code}.") from exc
    except Exception as exc:
        raise RuntimeError("Unexpected Groq API error during analysis.") from exc

    if not response.choices or response.choices[0].message is None:
        raise RuntimeError("Groq API returned an empty response.")

    content = response.choices[0].message.content
    if not content or not content.strip():
        raise RuntimeError("Groq API returned an empty response.")

    try:
        raw_analysis = _extract_json(content)
    except Exception as exc:
        raise RuntimeError("Groq API returned malformed analysis content.") from exc

    if not raw_analysis:
        raise RuntimeError("Groq API returned an empty analysis payload.")

    return _normalize_analysis(raw_analysis)
