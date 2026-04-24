from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any
from uuid import uuid4

from weasyprint import HTML


UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _to_float(value: Any) -> float:
        try:
                return float(value)
        except (TypeError, ValueError):
                return 0.0


def _build_category_rows(category_breakdown: dict[str, Any]) -> str:
        if not category_breakdown:
                return '<tr><td colspan="2">No category data available.</td></tr>'

        rows: list[str] = []
        for key, value in category_breakdown.items():
                label = escape(str(key))
                amount = _to_float(value)
                rows.append(f"<tr><td>{label}</td><td>{amount:,.2f}</td></tr>")
        return "".join(rows)


def _build_anomalies_list(anomalies: list[Any]) -> str:
        if not anomalies:
                return "<li>No anomalies detected.</li>"

        items: list[str] = []
        for anomaly in anomalies:
                if isinstance(anomaly, dict):
                        reason = anomaly.get("reason") or "No reason provided"
                        date = anomaly.get("date") or "Unknown date"
                        description = anomaly.get("description") or "Unknown item"
                        amount = anomaly.get("amount")
                        amount_display = f" ({amount})" if amount is not None else ""
                        text = f"{date} - {description}{amount_display}: {reason}"
                else:
                        text = str(anomaly)
                items.append(f"<li>{escape(text)}</li>")

        return "".join(items)


def generate_pdf(ai_analysis: dict, original_filename: str, files_processed: int = 1) -> Path:
        if not isinstance(ai_analysis, dict) or not ai_analysis:
                raise ValueError("AI analysis result is empty or malformed")

        if not isinstance(original_filename, str) or not original_filename.strip():
                original_filename = "Unknown source"

        if not isinstance(files_processed, int) or files_processed < 1:
                files_processed = 1

        if not any(
                key in ai_analysis
                for key in ("total_income", "total_expenses", "category_breakdown", "date_range", "anomalies")
        ):
                raise ValueError("AI analysis result is missing required fields")

        total_income = _to_float(ai_analysis.get("total_income"))
        total_expenses = _to_float(ai_analysis.get("total_expenses"))
        net = total_income - total_expenses

        date_range = ai_analysis.get("date_range") or {}
        start_date = date_range.get("start_date") or "N/A"
        end_date = date_range.get("end_date") or "N/A"

        category_breakdown = ai_analysis.get("category_breakdown")
        if not isinstance(category_breakdown, dict):
                category_breakdown = {}

        anomalies = ai_analysis.get("anomalies")
        if not isinstance(anomalies, list):
                anomalies = []

        category_rows = _build_category_rows(category_breakdown)
        anomaly_items = _build_anomalies_list(anomalies)
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        html = f"""
        <!doctype html>
        <html>
            <head>
                <meta charset=\"utf-8\" />
                <style>
                                        @page {{ size: A4; margin: 30mm 16mm 24mm; }}
                                        body {{ font-family: Arial, sans-serif; color: #0f172a; font-size: 12px; margin: 0; }}
                    h1 {{ font-size: 24px; margin: 0 0 12px; }}
                    h2 {{ font-size: 16px; margin: 22px 0 8px; border-bottom: 1px solid #cbd5e1; padding-bottom: 4px; }}
                                        .report-content {{ position: relative; z-index: 2; }}
                    .summary-grid {{ width: 100%; border-collapse: collapse; }}
                    .summary-grid td {{ padding: 6px 8px; border: 1px solid #e2e8f0; }}
                    .summary-grid td:first-child {{ background: #f8fafc; width: 35%; font-weight: bold; }}
                    table {{ width: 100%; border-collapse: collapse; }}
                    th, td {{ border: 1px solid #e2e8f0; padding: 8px; text-align: left; }}
                    th {{ background: #f1f5f9; }}
                    ul {{ margin: 6px 0 0 18px; }}
                                        .header {{ position: fixed; top: -18mm; left: 0; right: 0; height: 14mm; z-index: 10; }}
                                        .header-inner {{ display: table; width: 100%; border-bottom: 1px solid #dbe4ee; padding-bottom: 4px; }}
                                        .header-left, .header-right {{ display: table-cell; vertical-align: middle; }}
                                        .header-right {{ text-align: right; font-size: 10px; color: #64748b; }}
                                        .logo-mark {{ color: #1a3c5e; font-weight: 700; font-size: 18px; margin-right: 6px; }}
                                        .logo-name {{ color: #1a3c5e; font-size: 15px; font-weight: 600; }}
                                        .footer {{ position: fixed; bottom: -16mm; left: 0; right: 0; font-size: 10px; color: #475569; z-index: 10; }}
                                        .footer-line {{ border-top: 1px solid #cbd5e1; padding-top: 6px; display: table; width: 100%; }}
                                        .footer-left, .footer-right {{ display: table-cell; vertical-align: middle; }}
                                        .footer-right {{ text-align: right; }}
                                        .watermark-layer {{
                                                position: fixed;
                                                top: 0;
                                                left: 0;
                                                right: 0;
                                                bottom: 0;
                                                z-index: 1;
                                                pointer-events: none;
                                        }}
                                        .watermark-text {{
                                                position: absolute;
                                                color: #94a3b8;
                                                opacity: 0.08;
                                                font-size: 40px;
                                                font-weight: 700;
                                                transform: rotate(-32deg);
                                                white-space: nowrap;
                                        }}
                                        .page-break {{ page-break-before: always; }}
                                        .brand-page {{
                                                page-break-before: always;
                                                min-height: 230mm;
                                                display: table;
                                                width: 100%;
                                                text-align: center;
                                                position: relative;
                                                z-index: 2;
                                        }}
                                        .brand-page-inner {{ display: table-cell; vertical-align: middle; }}
                                        .brand-logo {{ color: #1a3c5e; font-size: 92px; font-weight: 700; line-height: 1; margin: 0; }}
                                        .brand-name {{ color: #1a3c5e; font-size: 44px; font-weight: 600; margin: 8px 0 14px; }}
                                        .brand-tagline {{ font-size: 20px; color: #334155; margin: 0 0 28px; }}
                                        .brand-cta {{ font-size: 16px; color: #334155; margin: 0 0 10px; }}
                                        .brand-link a {{ color: #1d4ed8; font-size: 18px; text-decoration: underline; }}
                </style>
            </head>
            <body>
                                <div class=\"watermark-layer\">
                                        <div class=\"watermark-text\" style=\"top: 12%; left: -4%;\">ClearBook</div>
                                        <div class=\"watermark-text\" style=\"top: 28%; left: 30%;\">ClearBook</div>
                                        <div class=\"watermark-text\" style=\"top: 44%; left: 2%;\">ClearBook</div>
                                        <div class=\"watermark-text\" style=\"top: 60%; left: 36%;\">ClearBook</div>
                                        <div class=\"watermark-text\" style=\"top: 76%; left: 8%;\">ClearBook</div>
                                </div>

                                <div class=\"header\">
                                        <div class=\"header-inner\">
                                                <div class=\"header-left\"><span class=\"logo-mark\">CB</span><span class=\"logo-name\">ClearBook</span></div>
                                                <div class=\"header-right\">clearbook.store</div>
                                        </div>
                                </div>

                                <div class=\"footer\">
                                        <div class=\"footer-line\">
                                                <div class=\"footer-left\">Generated by ClearBook · clearbook.store</div>
                                                <div class=\"footer-right\">{escape(generated_at.split(' ')[0])}</div>
                                        </div>
                                </div>

                                <div class=\"report-content\">
                                <h1>ClearBook Financial Analysis Report ({files_processed} files processed)</h1>

                <h2>Summary</h2>
                <table class=\"summary-grid\">
                    <tr><td>Total Income</td><td>{total_income:,.2f}</td></tr>
                    <tr><td>Total Expenses</td><td>{total_expenses:,.2f}</td></tr>
                    <tr><td>Net</td><td>{net:,.2f}</td></tr>
                    <tr><td>Date Range</td><td>{escape(str(start_date))} to {escape(str(end_date))}</td></tr>
                </table>

                <h2>Category Breakdown</h2>
                <table>
                    <thead>
                        <tr><th>Category</th><th>Amount</th></tr>
                    </thead>
                    <tbody>
                        {category_rows}
                    </tbody>
                </table>

                <h2>Anomalies</h2>
                <ul>
                    {anomaly_items}
                </ul>
                                </div>

                                <div class=\"brand-page\">
                                        <div class=\"brand-page-inner\">
                                                <p class=\"brand-logo\">CB</p>
                                                <p class=\"brand-name\">ClearBook</p>
                                                <p class=\"brand-tagline\">Your messy finances, made clear.</p>
                                                <p class=\"brand-cta\">Want clean financial reports for your business?</p>
                                                <p class=\"brand-link\"><a href=\"https://clearbook.store\">Visit clearbook.store</a></p>
                                        </div>
                                </div>
            </body>
        </html>
        """

        output_path = UPLOAD_DIR / f"{uuid4().hex}.pdf"
        try:
                HTML(string=html).write_pdf(str(output_path))
        except Exception as exc:
                raise ValueError("Unable to generate PDF from analysis results") from exc

        if not output_path.exists() or output_path.stat().st_size == 0:
                raise ValueError("Generated report is empty or unreadable")

        return output_path
