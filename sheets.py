"""Read and write a user's Google Sheet. All calls are blocking; the bot runs them in a thread.

Every function takes `sid`, the spreadsheet ID of the user being served.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import date, datetime

import gspread

import config
from categories import CATEGORY_NAMES, DEFAULT_BUDGETS
from parser import Transaction

TX_SHEET = "Transactions"
BUDGET_SHEET = "Budgets"
TX_HEADERS = ["ID", "Date", "Time", "Type", "Item", "Amount", "Category", "Subcategory",
              "Store", "Payment", "Note", "Week", "Month", "Added via"]


@dataclass
class Row:
    id: str
    date: date
    type: str
    item: str
    amount: float
    category: str
    subcategory: str
    store: str
    payment: str


_gc: gspread.Client | None = None
_books: dict[str, gspread.Spreadsheet] = {}
_budget_cache: dict[str, tuple[float, dict[str, float]]] = {}


def client() -> gspread.Client:
    global _gc
    if _gc is None:
        _gc = gspread.service_account(filename=str(config.GOOGLE_CREDENTIALS_FILE))
    return _gc


def robot_email() -> str:
    """The service account address people share their sheet with."""
    return json.loads(config.GOOGLE_CREDENTIALS_FILE.read_text())["client_email"]


def book(sid: str) -> gspread.Spreadsheet:
    if sid not in _books:
        _books[sid] = client().open_by_key(sid)
    return _books[sid]


def sheet_url(sid: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{sid}/edit"


def extract_id(text: str) -> str | None:
    """Pull the spreadsheet ID out of a pasted link (or a bare ID)."""
    text = text.strip()
    if "/d/" in text:
        return text.split("/d/")[1].split("/")[0].split("?")[0] or None
    if len(text) > 30 and all(c.isalnum() or c in "-_" for c in text):
        return text
    return None


def _safe_text(value: str) -> str:
    """Stop text like '=...' or '+...' from being read as a formula."""
    return "'" + value if value[:1] in ("=", "+", "-", "@") else value


def add_transactions(sid: str, items: list[Transaction]) -> list[str]:
    """Append transactions and return their IDs."""
    now = datetime.now(config.TIMEZONE)
    batch = now.strftime("%Y%m%d%H%M%S")
    rows, ids = [], []
    for i, t in enumerate(items):
        tx_id = f"{batch}-{i + 1}"
        iso = t.date.isocalendar()
        rows.append([
            tx_id,
            t.date.isoformat(),
            now.strftime("%H:%M"),
            t.type,
            _safe_text(t.item),
            t.amount,
            t.category,
            t.subcategory,
            _safe_text(t.store),
            t.payment,
            _safe_text(t.note),
            f"{iso.year}-W{iso.week:02d}",
            "'" + t.date.strftime("%Y-%m"),
            t.source,
        ])
        ids.append(tx_id)
    book(sid).worksheet(TX_SHEET).append_rows(rows, value_input_option="USER_ENTERED",
                                              table_range="A1")
    return ids


def read_transactions(sid: str) -> list[Row]:
    values = book(sid).worksheet(TX_SHEET).get(
        "A2:N",
        value_render_option=gspread.utils.ValueRenderOption.unformatted,
        date_time_render_option=gspread.utils.DateTimeOption.formatted_string,
    )
    rows = []
    for v in values:
        v = list(v) + [""] * (14 - len(v))
        if not v[0] or v[5] in ("", None):
            continue
        try:
            d = date.fromisoformat(str(v[1])[:10])
            amount = float(v[5])
        except (ValueError, TypeError):
            continue
        rows.append(Row(str(v[0]), d, v[3] or "Expense", str(v[4]), amount,
                        str(v[6]), str(v[7]), str(v[8]), str(v[9])))
    return rows


def delete_transactions(sid: str, ids: list[str]) -> int:
    ws = book(sid).worksheet(TX_SHEET)
    col = ws.col_values(1)
    targets = sorted((i + 1 for i, v in enumerate(col) if v in ids), reverse=True)
    for row_number in targets:
        ws.delete_rows(row_number)
    return len(targets)


def delete_last_row(sid: str) -> Row | None:
    ws = book(sid).worksheet(TX_SHEET)
    col = ws.col_values(1)
    if len(col) <= 1:
        return None
    rows = read_transactions(sid)
    last = rows[-1] if rows else None
    ws.delete_rows(len(col))
    return last


def _row_number(ws: gspread.Worksheet, tx_id: str) -> int | None:
    col = ws.col_values(1)
    return col.index(tx_id) + 1 if tx_id in col else None


def update_category(sid: str, tx_id: str, category: str, subcategory: str) -> bool:
    ws = book(sid).worksheet(TX_SHEET)
    r = _row_number(ws, tx_id)
    if r is None:
        return False
    ws.update(range_name=f"G{r}:H{r}", values=[[category, subcategory]], value_input_option="RAW")
    return True


def get_row(sid: str, tx_id: str) -> Row | None:
    return next((r for r in read_transactions(sid) if r.id == tx_id), None)


def update_fields(sid: str, tx_id: str, item: str | None = None, when: date | None = None,
                  payment: str | None = None) -> Row | None:
    """Edit one saved transaction and return it as it now stands."""
    ws = book(sid).worksheet(TX_SHEET)
    r = _row_number(ws, tx_id)
    if r is None:
        return None
    data = []
    if item is not None:
        data.append({"range": f"E{r}", "values": [[_safe_text(item)]]})
    if when is not None:
        iso = when.isocalendar()
        data += [{"range": f"B{r}", "values": [[when.isoformat()]]},
                 {"range": f"L{r}:M{r}", "values": [[f"{iso.year}-W{iso.week:02d}",
                                                     "'" + when.strftime("%Y-%m")]]}]
    if payment is not None:
        data.append({"range": f"J{r}", "values": [[payment]]})
    if data:
        ws.batch_update(data, value_input_option="USER_ENTERED")
    return get_row(sid, tx_id)


def save_budgets(sid: str, split: dict[str, float]) -> None:
    """Write monthly budgets into the Budgets tab, matching rows by category name."""
    ws = book(sid).worksheet(BUDGET_SHEET)
    names = [r[0] if r else "" for r in ws.get("A2:A40")]
    data = [{"range": f"C{i + 2}", "values": [[split[n]]]} for i, n in enumerate(names) if n in split]
    ws.batch_update(data, value_input_option="USER_ENTERED")
    _budget_cache.pop(sid, None)


def budgets(sid: str, max_age: float = 300) -> dict[str, float]:
    """Monthly budget per category, read from the Budgets tab (cached 5 minutes)."""
    cached = _budget_cache.get(sid)
    if cached and time.time() - cached[0] < max_age:
        return cached[1]
    result = dict(DEFAULT_BUDGETS)
    try:
        values = book(sid).worksheet(BUDGET_SHEET).get(
            "A2:C40", value_render_option=gspread.utils.ValueRenderOption.unformatted)
        for v in values:
            if len(v) >= 3 and v[0] in CATEGORY_NAMES:
                try:
                    result[v[0]] = float(v[2] or 0)
                except (TypeError, ValueError):
                    pass
    except gspread.WorksheetNotFound:
        pass
    _budget_cache[sid] = (time.time(), result)
    return result
