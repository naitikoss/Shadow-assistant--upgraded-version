"""
Google Sheets integration for the report section (requirement 11).

Two destinations, matching the two retention tiers:
- GOOGLE_SHEETS_SHORT_TERM_ID / _RANGE -> day-to-day tasks
- GOOGLE_SHEETS_LONG_TERM_ID  / _RANGE -> standing / recurring tasks,
  growth-tracking entries

Each row: [date, task_title, status, notes, retention, logged_at]
"""
import datetime as dt
import httpx
from .config import (
    GOOGLE_SHEETS_SHORT_TERM_ID, GOOGLE_SHEETS_SHORT_TERM_RANGE,
    GOOGLE_SHEETS_LONG_TERM_ID, GOOGLE_SHEETS_LONG_TERM_RANGE,
    FEATURES,
)
from .google_auth import get_access_token

_API = "https://sheets.googleapis.com/v4/spreadsheets"


async def _append_row(spreadsheet_id: str, a1_range: str, row: list):
    if not FEATURES.get("google_sheets_reports") or not spreadsheet_id:
        return
    token = await get_access_token()
    if not token:
        return
    url = f"{_API}/{spreadsheet_id}/values/{a1_range}:append"
    params = {"valueInputOption": "USER_ENTERED", "insertDataOption": "INSERT_ROWS"}
    headers = {"Authorization": f"Bearer {token}"}
    body = {"values": [row]}
    async with httpx.AsyncClient(timeout=15) as client:
        await client.post(url, headers=headers, params=params, json=body)


async def log_task_report(report_date: str, task_title: str, status: str, notes: str, retention: str):
    """retention: 'short' -> ShortTerm sheet, 'long' -> LongTerm sheet."""
    row = [report_date, task_title, status, notes, retention, dt.datetime.utcnow().isoformat()]
    if retention == "long":
        await _append_row(GOOGLE_SHEETS_LONG_TERM_ID, GOOGLE_SHEETS_LONG_TERM_RANGE, row)
    else:
        await _append_row(GOOGLE_SHEETS_SHORT_TERM_ID, GOOGLE_SHEETS_SHORT_TERM_RANGE, row)
