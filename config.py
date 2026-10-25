"""Settings loaded from the private .env file."""

import os
import re
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _get(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


TELEGRAM_BOT_TOKEN = _get("TELEGRAM_BOT_TOKEN")
# One or more Telegram IDs, separated by commas or spaces. The first one is the admin:
# they approve new users, and SPREADSHEET_ID below is their sheet.
ALLOWED_USER_IDS = [int(x) for x in re.split(r"[,\s]+", _get("ALLOWED_USER_IDS") or _get("ALLOWED_USER_ID"))
                    if x.isdigit()]
ADMIN_ID = ALLOWED_USER_IDS[0] if ALLOWED_USER_IDS else 0

GOOGLE_CREDENTIALS_FILE = BASE_DIR / _get("GOOGLE_CREDENTIALS_FILE", "service_account.json")
# Accept either the bare ID or the full sheet link pasted from the browser.
SPREADSHEET_ID = _get("SPREADSHEET_ID").strip("'\"")
if "/d/" in SPREADSHEET_ID:
    SPREADSHEET_ID = SPREADSHEET_ID.split("/d/")[1].split("/")[0]

# Optional: with a key, free-form messages are understood by Claude.
# Without it, the built-in parser handles "item price" style messages.
ANTHROPIC_API_KEY = _get("ANTHROPIC_API_KEY")
CLAUDE_MODEL = _get("CLAUDE_MODEL", "claude-opus-5-5")

TIMEZONE = ZoneInfo(_get("TIMEZONE", "Europe/Paris"))
DEFAULT_PAYMENT = _get("DEFAULT_PAYMENT", "Card")

WEEKLY_REPORT = _get("WEEKLY_REPORT", "true").lower() == "true"
MONTHLY_REPORT = _get("MONTHLY_REPORT", "true").lower() == "true"
DAILY_REMINDER = _get("DAILY_REMINDER", "true").lower() == "true"
DAILY_REMINDER_TIME = _get("DAILY_REMINDER_TIME", "21:30")


def check() -> list[str]:
    """Return a list of missing settings, empty when everything is ready."""
    missing = []
    if not TELEGRAM_BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not SPREADSHEET_ID:
        missing.append("SPREADSHEET_ID")
    if not GOOGLE_CREDENTIALS_FILE.exists():
        missing.append(f"Google key file ({GOOGLE_CREDENTIALS_FILE.name})")
    return missing
