"""Turn a free-form Telegram message into transactions.

Two parsers share one output format:
- parse_local: built-in rules, free, handles "bread 1.2, milk 0.9 @Lidl".
- parse_with_claude: used when ANTHROPIC_API_KEY is set; understands any phrasing
  ("spent 12 at the kebab place yesterday with cash") and falls back to
  parse_local on any error.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import config
from categories import (
    CATEGORY_NAMES, INCOME_KEYWORDS, INCOME_NAMES, KEYWORDS, PAYMENT_METHODS, STORES,
    SUBCATEGORIES, valid_subcategory,
)

log = logging.getLogger(__name__)

INTENTS = ["add", "today", "week", "month", "budget", "undo", "help", "other"]


@dataclass
class Transaction:
    item: str
    amount: float
    category: str
    subcategory: str
    type: str = "Expense"  # "Expense" or "Income"
    store: str = ""
    payment: str = config.DEFAULT_PAYMENT
    date: date = field(default_factory=lambda: datetime.now(config.TIMEZONE).date())
    note: str = ""
    source: str = "rules"


@dataclass
class ParseResult:
    intent: str
    transactions: list[Transaction]
    reply: str = ""


# ---------------------------------------------------------------- local rules

NUMBER_RE = re.compile(r"(?<![\w])(\d+(?:[.,]\d{1,2})?)(?![\d])")
QUANTITY_AFTER = re.compile(r"^\s*(x\b|kg\b|g\b|l\b|ml\b|cl\b|pcs?\b|pieces?\b)", re.I)
FILLER = {
    "i", "bought", "buy", "paid", "pay", "spent", "spend", "for", "on", "a", "an", "the", "some",
    "got", "received", "of", "at", "from", "with", "my", "euro", "euros", "eur", "€",
    "j'ai", "jai", "acheté", "achete", "payé", "paye", "pour", "de", "des", "du", "le", "la",
    "les", "un", "une", "reçu", "recu", "dépensé", "depense", "en",
}
STORE_RE = re.compile(r"(?:@|\b(?:at|from|chez)\s+)([\w&'é\- ]+?)(?=$|[,;\n]|\s+(?:with|by|in|cash|card|yesterday|today|hier)\b)", re.I)
PAYMENT_WORDS = {
    "Cash": ["cash", "espèces", "especes", "liquide"],
    "Card": ["card", "carte", "cb", "by card", "credit card"],
}
INCOME_RE = re.compile(r"^\s*\+")


def _match_keywords(text: str, table: dict) -> tuple[str, str] | None:
    """Return (category, subcategory) of the longest keyword found in text."""
    best, best_len = None, 0
    for (cat, sub), words in table.items():
        for kw in words:
            if len(kw) > best_len and re.search(r"(?<![\w])" + re.escape(kw.strip()), text):
                best, best_len = (cat, sub), len(kw)
    return best


def categorize(text: str, store: str = "") -> tuple[str, str]:
    low = text.lower()
    found = _match_keywords(low, KEYWORDS)
    if found:
        return found
    if store.lower() in {"lidl", "aldi", "carrefour", "leclerc", "auchan", "intermarché",
                         "intermarche", "monoprix", "franprix", "casino", "super u",
                         "hyper u", "netto", "grand frais", "biocoop", "naturalia"}:
        return "Groceries", "Pantry Staples"
    if store.lower() == "pharmacie":
        return "Health & Care", "Pharmacy"
    return "Other", "Other"


def _extract_date(text: str, today: date) -> tuple[date, str]:
    rules = [
        (r"\b(day before yesterday|avant[- ]hier)\b", 2),
        (r"\b(yesterday|hier)\b", 1),
        (r"\b(today|aujourd'hui)\b", 0),
    ]
    for pattern, days in rules:
        if re.search(pattern, text, re.I):
            return today - timedelta(days=days), re.sub(pattern, " ", text, flags=re.I)
    m = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", text)
    if m:
        d, mth = int(m.group(1)), int(m.group(2))
        y = int(m.group(3)) if m.group(3) else today.year
        y = y + 2000 if y < 100 else y
        try:
            return date(y, mth, d), text.replace(m.group(0), " ")
        except ValueError:
            pass
    return today, text


def _extract_store(text: str) -> tuple[str, str]:
    m = STORE_RE.search(text)
    if m:
        return m.group(1).strip().title(), text.replace(m.group(0), " ")
    low = text.lower()
    for s in STORES:
        if re.search(r"(?<![\w])" + re.escape(s) + r"(?![\w])", low):
            return s.title(), re.sub(re.escape(s), " ", text, flags=re.I)
    return "", text


def _extract_payment(text: str) -> tuple[str, str]:
    for method, words in PAYMENT_WORDS.items():
        for w in sorted(words, key=len, reverse=True):
            pattern = r"(?:\b(?:by|with|en|par)\s+)?\b" + re.escape(w) + r"\b"
            if re.search(pattern, text, re.I):
                return method, re.sub(pattern, " ", text, flags=re.I)
    return config.DEFAULT_PAYMENT, text


def _pick_amount(chunk: str) -> tuple[float | None, str]:
    """Find the price in a chunk; skip quantities like '2x' or '1kg'."""
    candidates = []
    for m in NUMBER_RE.finditer(chunk):
        after = chunk[m.end():]
        before = chunk[:m.start()]
        if QUANTITY_AFTER.match(after) or re.search(r"(?<![\w])x\s*$", before, re.I):
            continue
        euro = after.lstrip().startswith(("€", "eur", "e ")) or after.strip().lower() == "e" \
            or before.rstrip().endswith("€")
        candidates.append((euro, m))
    if not candidates:
        return None, chunk
    euro_hits = [m for euro, m in candidates if euro]
    m = euro_hits[0] if euro_hits else candidates[-1][1]
    amount = float(m.group(1).replace(",", "."))
    rest = chunk[:m.start()] + " " + chunk[m.end():]
    rest = re.sub(r"€|\beuros?\b|\beur\b|(?<=\s)e\b", " ", rest, flags=re.I)
    return amount, rest


def _clean_item(text: str) -> str:
    text = re.sub(r"(?<![\w])(\d+\s*x|x\s*\d+)(?![\w])", " ", text, flags=re.I)
    words = [w for w in re.split(r"\s+", text.strip(" -+:.!?")) if w and w.lower() not in FILLER]
    item = " ".join(words).strip(" -+:.")
    return item[:1].upper() + item[1:] if item else ""


def parse_local(text: str, today: date | None = None) -> ParseResult:
    today = today or datetime.now(config.TIMEZONE).date()
    when, text2 = _extract_date(text, today)
    store, text2 = _extract_store(text2)
    payment, text2 = _extract_payment(text2)

    chunks = [c for c in re.split(r",(?!\d)|[\n;]+|\s+and\s+|\s+et\s+|\s+&\s+", text2) if c.strip()]
    transactions: list[Transaction] = []
    pending: list[str] = []  # items without a price, merged into the next priced item
    for chunk in chunks:
        is_income = bool(INCOME_RE.match(chunk))
        amount, rest = _pick_amount(chunk)
        item = _clean_item(rest)
        if amount is None:
            if item:
                pending.append(item)
            continue
        if pending:
            item = " & ".join(pending + ([item] if item else []))
            pending = []
        if not item:
            item = "Purchase" if not is_income else "Income"
        income_match = _match_keywords(item.lower(), INCOME_KEYWORDS)
        if is_income or (income_match and not _match_keywords(item.lower(), KEYWORDS)):
            cat, sub = income_match or ("Other Income", "Other")
            transactions.append(Transaction(item=item, amount=amount, category=cat, subcategory=sub,
                                            type="Income", payment=payment, date=when))
        else:
            cat, sub = categorize(item, store)
            transactions.append(Transaction(item=item, amount=amount, category=cat, subcategory=sub,
                                            store=store, payment=payment, date=when))

    if transactions:
        return ParseResult("add", transactions)

    low = text.lower()
    for intent, words in [
        ("undo", ["undo", "delete last", "annuler", "remove last"]),
        ("budget", ["budget", "left", "reste"]),
        ("today", ["today", "aujourd"]),
        ("week", ["week", "semaine"]),
        ("month", ["month", "mois"]),
        ("help", ["help", "aide", "how do", "comment"]),
    ]:
        if any(w in low for w in words):
            return ParseResult(intent, [])
    return ParseResult("other", [], "I couldn't find a price in that. Try: bread 1.20, milk 0.95")


# ---------------------------------------------------------------- Claude

def _category_guide() -> str:
    lines = ["Expense categories (category: subcategories):"]
    lines += [f"- {c}: {', '.join(SUBCATEGORIES[c])}" for c in CATEGORY_NAMES]
    lines.append("Income categories (category: subcategories):")
    lines += [f"- {c}: {', '.join(SUBCATEGORIES[c])}" for c in INCOME_NAMES]
    return "\n".join(lines)


SYSTEM_PROMPT = f"""You are the input parser of a personal budget bot for a university student living in France. \
The student sends short, informal Telegram messages in English or French (sometimes mixed, sometimes with typos). \
Your job is to turn each message into structured records for their Google Sheet, or to recognise that the message is a question or command instead.

Currency is always euros. Amounts are prices actually paid; if a quantity and a unit price are both given \
("3 yogurts at 0.50"), record the total paid (1.50). If several items share one total, record one transaction with the items joined by " & ".

Each transaction needs:
- type: "Expense" or "Income" (money received: CAF/APL, scholarship, family, job, refunds, selling something).
- item: a short, clean name in English with a capital first letter (e.g. "Chicken breast", "Navigo pass"). Keep brand names.
- category and subcategory: pick from the lists below; the subcategory must belong to the chosen category. Halal butcher items go under Meat, Poultry & Fish. Meals at CROUS or the university go under Eating Out / CROUS / University.
- store: the shop or place if mentioned, else "".
- payment: one of {", ".join(PAYMENT_METHODS)}. Use "{config.DEFAULT_PAYMENT}" unless the message says otherwise.
- date: YYYY-MM-DD, resolving words like "yesterday" or "hier" against today's date given in the message. Default to today.
- note: anything else worth keeping, else "".

intent:
- "add" when the message records spending or income (transactions must be non-empty).
- "today", "week", "month", "budget" when the student asks how much they spent or how much budget is left for that period.
- "undo" when they want to remove the last entry; "help" when they ask how to use the bot.
- "other" for anything else.
For every intent except "add", transactions must be an empty list.

reply: for "other", one short friendly sentence explaining what you can do; otherwise "".

{_category_guide()}"""

ALL_SUBCATEGORIES = sorted({s for subs in SUBCATEGORIES.values() for s in subs})

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": INTENTS},
        "transactions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["Expense", "Income"]},
                    "item": {"type": "string"},
                    "amount": {"type": "number"},
                    "category": {"type": "string", "enum": CATEGORY_NAMES + INCOME_NAMES},
                    "subcategory": {"type": "string", "enum": ALL_SUBCATEGORIES},
                    "store": {"type": "string"},
                    "payment": {"type": "string", "enum": PAYMENT_METHODS},
                    "date": {"type": "string"},
                    "note": {"type": "string"},
                },
                "required": ["type", "item", "amount", "category", "subcategory", "store",
                             "payment", "date", "note"],
                "additionalProperties": False,
            },
        },
        "reply": {"type": "string"},
    },
    "required": ["intent", "transactions", "reply"],
    "additionalProperties": False,
}

_client = None


def _get_client():
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


def _to_transaction(raw: dict, today: date) -> Transaction | None:
    try:
        amount = round(float(raw["amount"]), 2)
    except (KeyError, TypeError, ValueError):
        return None
    if amount <= 0:
        return None
    ttype = raw.get("type", "Expense")
    category = raw.get("category", "")
    valid = INCOME_NAMES if ttype == "Income" else CATEGORY_NAMES
    if category not in valid:
        category = "Other Income" if ttype == "Income" else categorize(raw.get("item", ""))[0]
    try:
        when = date.fromisoformat(raw.get("date", ""))
        if abs((when - today).days) > 366:
            when = today
    except ValueError:
        when = today
    payment = raw.get("payment") if raw.get("payment") in PAYMENT_METHODS else config.DEFAULT_PAYMENT
    return Transaction(
        item=(raw.get("item") or "Purchase").strip()[:80],
        amount=amount,
        category=category,
        subcategory=valid_subcategory(category, raw.get("subcategory", "")),
        type=ttype,
        store=(raw.get("store") or "").strip()[:40],
        payment=payment,
        date=when,
        note=(raw.get("note") or "").strip()[:120],
        source="claude",
    )


async def parse_with_claude(text: str, today: date) -> ParseResult:
    import anthropic

    client = _get_client()
    response = await client.beta.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=4000,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": f"Today is {today.isoformat()} ({today.strftime('%A')}).\n\nMessage:\n{text}",
        }],
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    if response.stop_reason in ("refusal", "max_tokens"):
        raise anthropic.AnthropicError(f"Claude stopped early: {response.stop_reason}")
    payload = json.loads(next(b.text for b in response.content if b.type == "text"))
    transactions = [t for t in (_to_transaction(r, today) for r in payload["transactions"]) if t]
    intent = payload.get("intent", "other")
    if intent == "add" and not transactions:
        intent = "other"
    return ParseResult(intent, transactions, payload.get("reply", ""))


async def parse_message(text: str) -> ParseResult:
    today = datetime.now(config.TIMEZONE).date()
    if config.ANTHROPIC_API_KEY:
        try:
            return await parse_with_claude(text, today)
        except Exception:  # network, quota, bad output: never lose the user's entry
            log.exception("Claude parsing failed, using built-in rules")
    return parse_local(text, today)
