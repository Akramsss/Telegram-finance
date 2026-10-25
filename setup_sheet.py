"""Build (or rebuild) the budget spreadsheet: tabs, formulas, formatting and charts.

Run once after connecting the service account:  python setup_sheet.py
Safe to run again: your Transactions and Budgets are kept; Dashboard, Weekly and
Monthly are rebuilt from scratch.
"""

from __future__ import annotations

import gspread

import config
import sheets
from categories import (
    CATEGORY_NAMES, DEFAULT_BUDGETS, EMOJI, INCOME_NAMES, PAYMENT_METHODS, SUBCATEGORIES,
)
from sheets import BUDGET_SHEET, TX_HEADERS, TX_SHEET

N = len(CATEGORY_NAMES)
BUDGET_LAST = N + 1  # budgets live in Budgets!A2:C{BUDGET_LAST}
EUR = "€#,##0.00"

# Shorthand for ranges on the Transactions tab
T = {c: f"{TX_SHEET}!${c}$2:${c}" for c in "ABCDEFGHIJKLMN"}
SPENT = f'SUMIFS({T["F"]},{T["D"]},"Expense"'
INCOME = f'SUMIFS({T["F"]},{T["D"]},"Income"'
WEEK_START = "(TODAY()-WEEKDAY(TODAY(),3))"
BUDGET_TOTAL = f"SUM({BUDGET_SHEET}!$C$2:$C${BUDGET_LAST})"


def rgb(hex_color: str) -> dict:
    h = hex_color.lstrip("#")
    return {"red": int(h[0:2], 16) / 255, "green": int(h[2:4], 16) / 255, "blue": int(h[4:6], 16) / 255}


def grid(sheet_id: int, r0: int, r1: int, c0: int, c1: int) -> dict:
    """0-based, end-exclusive grid range."""
    return {"sheetId": sheet_id, "startRowIndex": r0, "endRowIndex": r1,
            "startColumnIndex": c0, "endColumnIndex": c1}


def fmt(sheet_id, r0, r1, c0, c1, **cell) -> dict:
    fields = []
    if "numberFormat" in cell:
        fields.append("userEnteredFormat.numberFormat")
    if "backgroundColor" in cell:
        fields.append("userEnteredFormat.backgroundColor")
    if "textFormat" in cell:
        fields.append("userEnteredFormat.textFormat")
    if "horizontalAlignment" in cell:
        fields.append("userEnteredFormat.horizontalAlignment")
    if "verticalAlignment" in cell:
        fields.append("userEnteredFormat.verticalAlignment")
    if "wrapStrategy" in cell:
        fields.append("userEnteredFormat.wrapStrategy")
    if "padding" in cell:
        fields.append("userEnteredFormat.padding")
    return {"repeatCell": {"range": grid(sheet_id, r0, r1, c0, c1),
                           "cell": {"userEnteredFormat": cell}, "fields": ",".join(fields)}}


def money(sheet_id, r0, r1, c0, c1) -> dict:
    return fmt(sheet_id, r0, r1, c0, c1, numberFormat={"type": "CURRENCY", "pattern": EUR})


def widths(sheet_id: int, sizes: list[tuple[int, int, int]]) -> list[dict]:
    return [{"updateDimensionProperties": {
        "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": a, "endIndex": b},
        "properties": {"pixelSize": px}, "fields": "pixelSize"}} for a, b, px in sizes]


def header_style(sheet_id: int, ncols: int, color: str = "#343A40") -> dict:
    return fmt(sheet_id, 0, 1, 0, ncols, backgroundColor=rgb(color),
               textFormat={"bold": True, "foregroundColor": rgb("#FFFFFF")},
               verticalAlignment="MIDDLE")


def freeze(sheet_id: int, rows: int = 1, cols: int = 0) -> dict:
    return {"updateSheetProperties": {
        "properties": {"sheetId": sheet_id,
                       "gridProperties": {"frozenRowCount": rows, "frozenColumnCount": cols}},
        "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount"}}


def chart(sheet_id: int, row: int, col: int, w: int, h: int, spec: dict) -> dict:
    return {"addChart": {"chart": {"spec": spec, "position": {"overlayPosition": {
        "anchorCell": {"sheetId": sheet_id, "rowIndex": row, "columnIndex": col},
        "widthPixels": w, "heightPixels": h}}}}}


def src(rng: dict) -> dict:
    return {"sourceRange": {"sources": [rng]}}


# ---------------------------------------------------------------- tabs

def ensure_transactions(book: gspread.Spreadsheet) -> tuple[gspread.Worksheet, bool]:
    try:
        ws = book.worksheet(TX_SHEET)
        if ws.row_values(1) != TX_HEADERS:
            ws.update(range_name="A1", values=[TX_HEADERS])
        return ws, False
    except gspread.WorksheetNotFound:
        ws = book.add_worksheet(TX_SHEET, rows=5000, cols=len(TX_HEADERS))
        ws.update(range_name="A1", values=[TX_HEADERS])
        return ws, True


def ensure_budgets(book: gspread.Spreadsheet) -> tuple[gspread.Worksheet, bool]:
    try:
        return book.worksheet(BUDGET_SHEET), False
    except gspread.WorksheetNotFound:
        pass
    ws = book.add_worksheet(BUDGET_SHEET, rows=40, cols=10)
    rows = [["Category", "Icon", "Monthly budget (€)", "Weekly ≈", "Subcategories"]]
    for i, cat in enumerate(CATEGORY_NAMES):
        r = i + 2
        rows.append([cat, EMOJI[cat], DEFAULT_BUDGETS[cat], f"=C{r}*12/52",
                     ", ".join(SUBCATEGORIES[cat])])
    rows.append(["Total", "", f"=SUM(C2:C{BUDGET_LAST})", f"=C{BUDGET_LAST + 1}*12/52", ""])
    ws.update(range_name="A1", values=rows, value_input_option="USER_ENTERED")
    ws.update(range_name="G1", values=[["✏️ Change the amounts in column C. The dashboard and the bot use them automatically. "
                      "0 = no budget for that category."]])
    lists = [["Income categories", "Payment methods", "All categories"]]
    all_cats = CATEGORY_NAMES + INCOME_NAMES
    for i in range(len(all_cats)):
        lists.append([INCOME_NAMES[i] if i < len(INCOME_NAMES) else "",
                      PAYMENT_METHODS[i] if i < len(PAYMENT_METHODS) else "",
                      all_cats[i]])
    ws.update(range_name="G3", values=lists)
    return ws, True


def rebuild(book: gspread.Spreadsheet, title: str, rows: int, cols: int) -> gspread.Worksheet:
    try:
        book.del_worksheet(book.worksheet(title))
    except gspread.WorksheetNotFound:
        pass
    return book.add_worksheet(title, rows=rows, cols=cols)


# ---------------------------------------------------------------- content

def weekly_values() -> list[list]:
    head = ["Week starting", "Week", "Total spent", "Weekly budget"] + CATEGORY_NAMES
    rows = [head]
    for r in range(2, 14):
        row = [f"={WEEK_START}-7*(13-ROW())",
               f'="W"&TEXT(ISOWEEKNUM(A{r}),"00")&" · "&TEXT(A{r},"dd mmm")',
               f'={SPENT},{T["B"]},">="&$A{r},{T["B"]},"<"&($A{r}+7))',
               f"={BUDGET_TOTAL}*12/52"]
        for c in range(N):
            col = gspread.utils.rowcol_to_a1(1, 5 + c).rstrip("1")
            row.append(f'={SPENT},{T["B"]},">="&$A{r},{T["B"]},"<"&($A{r}+7),{T["G"]},{col}$1)')
        rows.append(row)
    return rows


def monthly_values() -> list[list]:
    head = ["Month", "Spent", "Income", "Saved", "Budget"] + CATEGORY_NAMES
    rows = [head]
    for r in range(2, 14):
        row = [f'=TEXT(EDATE(TODAY(),-(13-ROW())),"yyyy-mm")',
               f'={SPENT},{T["M"]},$A{r})',
               f'={INCOME},{T["M"]},$A{r})',
               f"=C{r}-B{r}",
               f"={BUDGET_TOTAL}"]
        for c in range(N):
            col = gspread.utils.rowcol_to_a1(1, 6 + c).rstrip("1")
            row.append(f'={SPENT},{T["M"]},$A{r},{T["G"]},{col}$1)')
        rows.append(row)
    return rows


def dashboard_values() -> list[dict]:
    # C3 may hold text ("2026-09") or a date if Sheets converts what was typed; TEXT() handles both.
    m = 'TEXT($C$3,"yyyy-mm")'
    month_spent = f"{SPENT},{T['M']},{m})"
    prev_month = f'TEXT(EDATE(DATEVALUE({m}&"-01"),-1),"yyyy-mm")'
    days_in_month = f'DAY(EOMONTH(DATEVALUE({m}&"-01"),0))'
    data = [
        ("B1", [["💸 My Student Budget"]]),
        ("B2", [["Filled automatically by your Telegram bot. Type another month in C3 (e.g. 2026-09) to look back."]]),
        ("B3", [["Month", '=TEXT(TODAY(),"yyyy-mm")']]),
        ("B5", [["💸 Spent", "🎯 Budget", "✅ Left", "📊 Used", "📅 Daily average", "🔮 Projected", "💰 Income"]]),
        ("B6", [[f"={month_spent}",
                 f"={BUDGET_TOTAL}",
                 "=C6-B6",
                 "=IFERROR(B6/C6,0)",
                 f'=B6/IF({m}=TEXT(TODAY(),"yyyy-mm"),DAY(TODAY()),{days_in_month})',
                 f"=F6*{days_in_month}",
                 f"={INCOME},{T['M']},{m})"]]),
        ("B8", [["☀️ Today", "🗓️ This week", "⏮️ Last week", "🐷 Saved", "🧾 Purchases", "🔝 Biggest", "↕️ vs last month"]]),
        ("B9", [[f"={SPENT},{T['B']},TODAY())",
                 f'={SPENT},{T["B"]},">="&{WEEK_START})',
                 f'={SPENT},{T["B"]},">="&({WEEK_START}-7),{T["B"]},"<"&{WEEK_START})',
                 "=H6-B6",
                 f'=COUNTIFS({T["M"]},{m},{T["D"]},"Expense")',
                 f'=IFERROR(MAXIFS({T["F"]},{T["M"]},{m},{T["D"]},"Expense"),0)',
                 f'=IFERROR(B6/({SPENT},{T["M"]},{prev_month}))-1,"—")']]),
        ("B11", [["Spending by category"]]),
        ("B12", [["Category", "Budget", "Spent", "Left", "Used", "Progress", "Status"]]),
    ]
    table = []
    for i in range(N + 1):
        r = 13 + i
        if i < N:
            br = i + 2
            name = f'={BUDGET_SHEET}!$B{br}&"  "&{BUDGET_SHEET}!$A{br}'
            budget = f"={BUDGET_SHEET}!$C{br}"
            spent = f"={month_spent[:-1]},{T['G']},{BUDGET_SHEET}!$A{br})"
        else:
            name, budget, spent = "Total", f"=SUM(C13:C{r - 1})", f"=SUM(D13:D{r - 1})"
        table.append([
            name, budget, spent, f"=C{r}-D{r}",
            f'=IF(N(C{r})>0,D{r}/C{r},"")',
            f'=IF(N(C{r})>0,SPARKLINE(MIN(D{r}/C{r},1),{{"charttype","bar";"max",1;"color1",'
            f'IF(D{r}>=C{r},"#E03131",IF(D{r}>=0.8*C{r},"#F08C00","#2F9E44"))}}),"")',
            f'=IF(N(C{r})=0,IF(D{r}>0,"⚪ No budget","—"),IF(D{r}>=C{r},"🔴 Over",'
            f'IF(D{r}>=0.8*C{r},"🟠 Careful","🟢 On track")))',
        ])
    data.append(("B13", table))

    top = 13 + N + 2  # first row after the table + one blank row
    q = f"{TX_SHEET}!$B$2:$N"
    month_filter = f"D = 'Expense' and M = '\"&{m}&\"'"
    data += [
        (f"B{top}", [["🛒 Top items", "", "🏪 Top stores", "", "💳 Payment"]]),
        (f"B{top + 1}", [[f'=IFERROR(QUERY({q},"select E, sum(F) where {month_filter} '
                          f"group by E order by sum(F) desc limit 5 label E 'Item', sum(F) 'Total'\",0),"
                          f'"No purchases yet")']]),
        (f"D{top + 1}", [[f'=IFERROR(QUERY({q},"select I, sum(F) where {month_filter} and I <> \'\' '
                          f"group by I order by sum(F) desc limit 5 label I 'Store', sum(F) 'Total'\",0),"
                          f'"—")']]),
        (f"F{top + 1}", [[f'=IFERROR(QUERY({q},"select J, sum(F) where {month_filter} '
                          f"group by J order by sum(F) desc label J 'Payment', sum(F) 'Total'\",0),"
                          f'"—")']]),
        (f"B{top + 8}", [["🧾 Latest entries"]]),
        (f"B{top + 9}", [[f'=IFERROR(QUERY({q},"select B, E, F, G, D where B is not null '
                          f"order by B desc, C desc limit 12 label B 'Date', E 'Item', F 'Amount', "
                          f"G 'Category', D 'Type'\",0),\"No entries yet\")"]]),
    ]
    return [{"range": f"Dashboard!{a1}", "values": v} for a1, v in data]


# ---------------------------------------------------------------- formatting

def dashboard_format(sid: int, weekly_id: int, monthly_id: int) -> list[dict]:
    last = 12 + N  # 0-based index of the Total row
    top = 13 + N + 2
    tile_bg, label_color = rgb("#F1F3F5"), rgb("#868E96")
    reqs = [
        {"updateSheetProperties": {"properties": {"sheetId": sid, "gridProperties": {"hideGridlines": True}},
                                   "fields": "gridProperties.hideGridlines"}},
        *widths(sid, [(0, 1, 24), (1, 2, 190), (2, 8, 118), (8, 9, 24)]),
        fmt(sid, 0, 1, 1, 8, textFormat={"bold": True, "fontSize": 22, "foregroundColor": rgb("#212529")}),
        fmt(sid, 1, 2, 1, 8, textFormat={"italic": True, "foregroundColor": label_color}),
        fmt(sid, 2, 3, 1, 2, textFormat={"bold": True}),
        fmt(sid, 2, 3, 2, 3, backgroundColor=rgb("#FFF3BF"), textFormat={"bold": True},
            horizontalAlignment="CENTER", numberFormat={"type": "DATE", "pattern": "yyyy-mm"}),
        # KPI tiles
        fmt(sid, 4, 6, 1, 8, backgroundColor=tile_bg, horizontalAlignment="CENTER"),
        fmt(sid, 7, 9, 1, 8, backgroundColor=tile_bg, horizontalAlignment="CENTER"),
        fmt(sid, 4, 5, 1, 8, textFormat={"fontSize": 9, "foregroundColor": label_color}),
        fmt(sid, 7, 8, 1, 8, textFormat={"fontSize": 9, "foregroundColor": label_color}),
        fmt(sid, 5, 6, 1, 8, textFormat={"fontSize": 16, "bold": True}),
        fmt(sid, 8, 9, 1, 8, textFormat={"fontSize": 14, "bold": True}),
        money(sid, 5, 6, 1, 4), money(sid, 5, 6, 5, 8),
        fmt(sid, 5, 6, 4, 5, numberFormat={"type": "PERCENT", "pattern": "0%"}),
        money(sid, 8, 9, 0, 5), money(sid, 8, 9, 6, 7),
        fmt(sid, 8, 9, 5, 6, numberFormat={"type": "NUMBER", "pattern": "0"}),
        fmt(sid, 8, 9, 7, 8, numberFormat={"type": "PERCENT", "pattern": "+0%;-0%;0%"}),
        # Category table
        fmt(sid, 10, 11, 1, 8, textFormat={"bold": True, "fontSize": 13}),
        fmt(sid, 11, 12, 1, 8, backgroundColor=rgb("#343A40"),
            textFormat={"bold": True, "foregroundColor": rgb("#FFFFFF")}),
        money(sid, 12, last + 1, 2, 5),
        fmt(sid, 12, last + 1, 5, 6, numberFormat={"type": "PERCENT", "pattern": "0%"}),
        fmt(sid, last, last + 1, 1, 8, backgroundColor=rgb("#E9ECEF"), textFormat={"bold": True}),
        {"addBanding": {"bandedRange": {"range": grid(sid, 12, last, 1, 8), "rowProperties": {
            "firstBandColor": rgb("#FFFFFF"), "secondBandColor": rgb("#F8F9FA")}}}},
        {"addConditionalFormatRule": {"index": 0, "rule": {
            "ranges": [grid(sid, 12, last + 1, 4, 5)],
            "booleanRule": {"condition": {"type": "NUMBER_LESS", "values": [{"userEnteredValue": "0"}]},
                            "format": {"textFormat": {"foregroundColor": rgb("#E03131"), "bold": True}}}}}},
        # Top lists and latest entries
        fmt(sid, top - 1, top, 1, 8, textFormat={"bold": True, "fontSize": 13}),
        fmt(sid, top, top + 1, 1, 8, textFormat={"bold": True, "foregroundColor": label_color}),
        money(sid, top, top + 6, 2, 3), money(sid, top, top + 6, 4, 5), money(sid, top, top + 6, 6, 7),
        fmt(sid, top + 7, top + 8, 1, 8, textFormat={"bold": True, "fontSize": 13}),
        fmt(sid, top + 8, top + 9, 1, 6, textFormat={"bold": True, "foregroundColor": label_color}),
        fmt(sid, top + 9, top + 21, 1, 2, numberFormat={"type": "DATE", "pattern": "ddd dd mmm"}),
        money(sid, top + 9, top + 21, 3, 4),
        # Charts
        chart(sid, 2, 9, 560, 360, {
            "title": "Where your money went", "subtitle": "Selected month",
            "pieChart": {"legendPosition": "RIGHT_LEGEND", "pieHole": 0.5,
                         "domain": src(grid(sid, 12, last, 1, 2)),
                         "series": src(grid(sid, 12, last, 3, 4))}}),
        chart(sid, 21, 9, 560, 320, {
            "title": "Last 12 weeks", "basicChart": {
                "chartType": "COMBO", "legendPosition": "BOTTOM_LEGEND", "headerCount": 1,
                "axis": [{"position": "LEFT_AXIS", "title": "€"}],
                "domains": [{"domain": src(grid(weekly_id, 0, 13, 1, 2))}],
                "series": [
                    {"series": src(grid(weekly_id, 0, 13, 2, 3)), "targetAxis": "LEFT_AXIS",
                     "type": "COLUMN", "color": rgb("#4C6EF5")},
                    {"series": src(grid(weekly_id, 0, 13, 3, 4)), "targetAxis": "LEFT_AXIS",
                     "type": "LINE", "color": rgb("#E03131")}]}}),
        chart(sid, 38, 9, 560, 320, {
            "title": "Last 12 months", "basicChart": {
                "chartType": "COMBO", "legendPosition": "BOTTOM_LEGEND", "headerCount": 1,
                "axis": [{"position": "LEFT_AXIS", "title": "€"}],
                "domains": [{"domain": src(grid(monthly_id, 0, 13, 0, 1))}],
                "series": [
                    {"series": src(grid(monthly_id, 0, 13, 1, 2)), "targetAxis": "LEFT_AXIS",
                     "type": "COLUMN", "color": rgb("#4C6EF5")},
                    {"series": src(grid(monthly_id, 0, 13, 2, 3)), "targetAxis": "LEFT_AXIS",
                     "type": "COLUMN", "color": rgb("#2F9E44")},
                    {"series": src(grid(monthly_id, 0, 13, 4, 5)), "targetAxis": "LEFT_AXIS",
                     "type": "LINE", "color": rgb("#E03131")}]}}),
    ]
    return reqs


def weekly_format(sid: int) -> list[dict]:
    ncols = 4 + N
    return [
        header_style(sid, ncols), freeze(sid, 1, 2),
        fmt(sid, 1, 13, 0, 1, numberFormat={"type": "DATE", "pattern": "dd/mm/yyyy"}),
        money(sid, 1, 13, 2, ncols),
        fmt(sid, 12, 13, 0, ncols, backgroundColor=rgb("#E7F5FF"), textFormat={"bold": True}),
        *widths(sid, [(0, 2, 120), (2, ncols, 115)]),
        chart(sid, 14, 0, 900, 380, {
            "title": "Weekly spending by category", "basicChart": {
                "chartType": "COLUMN", "stackedType": "STACKED", "legendPosition": "RIGHT_LEGEND",
                "headerCount": 1, "domains": [{"domain": src(grid(sid, 0, 13, 1, 2))}],
                "series": [{"series": src(grid(sid, 0, 13, c, c + 1)), "targetAxis": "LEFT_AXIS"}
                           for c in range(4, ncols)]}}),
    ]


def monthly_format(sid: int) -> list[dict]:
    ncols = 5 + N
    return [
        header_style(sid, ncols), freeze(sid, 1, 1),
        money(sid, 1, 13, 1, ncols),
        fmt(sid, 12, 13, 0, ncols, backgroundColor=rgb("#E7F5FF"), textFormat={"bold": True}),
        {"addConditionalFormatRule": {"index": 0, "rule": {
            "ranges": [grid(sid, 1, 13, 3, 4)],
            "booleanRule": {"condition": {"type": "NUMBER_LESS", "values": [{"userEnteredValue": "0"}]},
                            "format": {"textFormat": {"foregroundColor": rgb("#E03131")}}}}}},
        *widths(sid, [(0, 1, 90), (1, ncols, 115)]),
        chart(sid, 14, 0, 900, 380, {
            "title": "Monthly spending by category", "basicChart": {
                "chartType": "COLUMN", "stackedType": "STACKED", "legendPosition": "RIGHT_LEGEND",
                "headerCount": 1, "domains": [{"domain": src(grid(sid, 0, 13, 0, 1))}],
                "series": [{"series": src(grid(sid, 0, 13, c, c + 1)), "targetAxis": "LEFT_AXIS"}
                           for c in range(5, ncols)]}}),
    ]


def transactions_format(sid: int, budgets_title: str, first_time: bool, nrows: int) -> list[dict]:
    ncols = len(TX_HEADERS)
    all_cats = len(CATEGORY_NAMES) + len(INCOME_NAMES)
    reqs = [
        header_style(sid, ncols), freeze(sid, 1, 0),
        fmt(sid, 1, nrows, 1, 2, numberFormat={"type": "DATE", "pattern": "yyyy-mm-dd"}),
        money(sid, 1, nrows, 5, 6),
        *widths(sid, [(0, 1, 130), (1, 2, 95), (2, 3, 55), (3, 4, 75), (4, 5, 200), (5, 6, 85),
                      (6, 8, 160), (8, 10, 100), (10, 11, 180), (11, 14, 85)]),
        {"setDataValidation": {"range": grid(sid, 1, nrows, 3, 4), "rule": {
            "condition": {"type": "ONE_OF_LIST", "values": [{"userEnteredValue": "Expense"},
                                                             {"userEnteredValue": "Income"}]},
            "showCustomUi": True, "strict": False}}},
        {"setDataValidation": {"range": grid(sid, 1, nrows, 6, 7), "rule": {
            "condition": {"type": "ONE_OF_RANGE", "values": [
                {"userEnteredValue": f"={budgets_title}!$I$4:$I${3 + all_cats}"}]},
            "showCustomUi": True, "strict": False}}},
        {"setDataValidation": {"range": grid(sid, 1, nrows, 9, 10), "rule": {
            "condition": {"type": "ONE_OF_LIST",
                          "values": [{"userEnteredValue": p} for p in PAYMENT_METHODS]},
            "showCustomUi": True, "strict": False}}},
    ]
    if first_time:
        reqs += [
            {"addBanding": {"bandedRange": {"range": grid(sid, 0, nrows, 0, ncols), "rowProperties": {
                "headerColor": rgb("#343A40"), "firstBandColor": rgb("#FFFFFF"),
                "secondBandColor": rgb("#F8F9FA")}}}},
            {"addConditionalFormatRule": {"index": 0, "rule": {
                "ranges": [grid(sid, 1, nrows, 0, ncols)],
                "booleanRule": {"condition": {"type": "CUSTOM_FORMULA",
                                              "values": [{"userEnteredValue": '=$D2="Income"'}]},
                                "format": {"textFormat": {"foregroundColor": rgb("#2B8A3E")}}}}}},
            {"setBasicFilter": {"filter": {"range": grid(sid, 0, nrows, 0, ncols)}}},
        ]
    return reqs


def budgets_format(sid: int) -> list[dict]:
    return [
        header_style(sid, 5), freeze(sid, 1, 0),
        money(sid, 1, BUDGET_LAST + 1, 2, 4),
        fmt(sid, 1, BUDGET_LAST, 2, 3, backgroundColor=rgb("#FFF3BF"), textFormat={"bold": True}),
        fmt(sid, BUDGET_LAST, BUDGET_LAST + 1, 0, 5, backgroundColor=rgb("#E9ECEF"), textFormat={"bold": True}),
        fmt(sid, 0, 1, 6, 7, textFormat={"italic": True, "foregroundColor": rgb("#868E96")}),
        fmt(sid, 2, 3, 6, 9, textFormat={"bold": True}),
        fmt(sid, 1, BUDGET_LAST, 4, 5, wrapStrategy="WRAP"),
        *widths(sid, [(0, 1, 170), (1, 2, 50), (2, 4, 130), (4, 5, 380), (5, 6, 30), (6, 9, 150)]),
    ]


# ---------------------------------------------------------------- main

def build(sid: str, log=print) -> str:
    """Create or refresh all tabs of one spreadsheet. Returns its title."""
    book = sheets.client().open_by_key(sid)
    log(f"Connected to: {book.title}")

    book.batch_update({"requests": [{"updateSpreadsheetProperties": {
        "properties": {"locale": "en_IE", "timeZone": str(config.TIMEZONE)},
        "fields": "locale,timeZone"}}]})

    tx, tx_new = ensure_transactions(book)
    budgets, budgets_new = ensure_budgets(book)
    monthly = rebuild(book, "Monthly", 40, 5 + N)
    weekly = rebuild(book, "Weekly", 40, 4 + N)
    dash = rebuild(book, "Dashboard", 80, 18)
    log("Tabs ready: Dashboard, Transactions, Budgets, Weekly, Monthly")

    # Remove the empty default tab ("Sheet1", "Feuille 1", ...)
    ours = {TX_SHEET, BUDGET_SHEET, "Monthly", "Weekly", "Dashboard"}
    for ws in book.worksheets():
        if ws.title not in ours and not any(ws.get_all_values()):
            book.del_worksheet(ws)

    book.values_batch_update({"valueInputOption": "USER_ENTERED", "data": [
        {"range": "Weekly!A1", "values": weekly_values()},
        {"range": "Monthly!A1", "values": monthly_values()},
        *dashboard_values(),
    ]})
    log("Formulas written")

    order = [dash, tx, budgets, weekly, monthly]
    requests = [{"updateSheetProperties": {"properties": {"sheetId": ws.id, "index": i},
                                           "fields": "index"}} for i, ws in enumerate(order)]
    colors = ["#4C6EF5", "#343A40", "#F08C00", "#12B886", "#7950F2"]
    requests += [{"updateSheetProperties": {"properties": {"sheetId": ws.id, "tabColor": rgb(c)},
                                            "fields": "tabColor"}} for ws, c in zip(order, colors)]
    requests += transactions_format(tx.id, BUDGET_SHEET, tx_new, tx.row_count)
    if budgets_new:
        requests += budgets_format(budgets.id)
    requests += weekly_format(weekly.id)
    requests += monthly_format(monthly.id)
    requests += dashboard_format(dash.id, weekly.id, monthly.id)
    book.batch_update({"requests": requests})
    log("Formatting and charts done")
    return book.title


def main():
    """Rebuild the owner's sheet (SPREADSHEET_ID), or the sheet given as an argument."""
    import sys
    missing = [m for m in config.check() if m != "TELEGRAM_BOT_TOKEN"]
    sid = sheets.extract_id(sys.argv[1]) if len(sys.argv) > 1 else config.SPREADSHEET_ID
    if missing and not (sid and config.GOOGLE_CREDENTIALS_FILE.exists()):
        raise SystemExit("Missing settings: " + ", ".join(missing) + "\nSee SETUP.md.")
    build(sid)
    print(f"\n✅ Your sheet is ready: {sheets.sheet_url(sid)}")


if __name__ == "__main__":
    main()
