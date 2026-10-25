"""Who may use the bot and which Google Sheet belongs to whom.

Stored in bot_data (saved to bot_state.pickle):
  users:   {telegram_id: {"name": str, "sheet": spreadsheet_id | None}}
  pending: {telegram_id: name}   access requests waiting for the admin
  removed: {telegram_id}          IDs from .env the admin removed with /remove
"""

from __future__ import annotations

import asyncio
import html
import logging

import gspread
from telegram import InlineKeyboardButton as Btn, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

import config
import setup_sheet
import sheets

log = logging.getLogger(__name__)


def registry(bot_data: dict) -> dict[int, dict]:
    """The user table, with everyone listed in .env added on first use."""
    users = bot_data.setdefault("users", {})
    removed = bot_data.setdefault("removed", set())
    for uid in config.ALLOWED_USER_IDS:
        if uid not in removed:
            users.setdefault(uid, {"name": "", "sheet": None})
    admin = users.get(config.ADMIN_ID)
    if admin is not None and not admin["sheet"] and config.SPREADSHEET_ID:
        admin["sheet"] = config.SPREADSHEET_ID
    return users


def is_allowed(bot_data: dict, uid: int) -> bool:
    return uid in registry(bot_data)


def sheet_of(bot_data: dict, uid: int) -> str | None:
    user = registry(bot_data).get(uid)
    return user["sheet"] if user else None


def with_sheets(bot_data: dict) -> list[tuple[int, str]]:
    return [(uid, u["sheet"]) for uid, u in registry(bot_data).items() if u["sheet"]]


def display_name(user) -> str:
    name = " ".join(x for x in (user.first_name, user.last_name) if x) or "Someone"
    return name + (f" (@{user.username})" if user.username else "")


# ---------------------------------------------------------------- strangers

async def stranger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    pending = uid in context.bot_data.get("pending", {})
    text = (f"🔒 <b>This bot is private.</b>\nYour Telegram ID: <code>{uid}</code>\n\n"
            + ("⏳ Your access request was sent. You'll get a message when it's approved."
               if pending else "Want to use it to track your own spending?"))
    markup = None if pending else InlineKeyboardMarkup([[Btn("🙋 Request access", callback_data="ua|req")]])
    await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | None:
    """Access buttons ("ua|..."). Returns a user ID when someone was just approved."""
    query = update.callback_query
    parts = query.data.split("|")
    action = parts[1]
    me = query.from_user

    if action == "req":
        pending = context.bot_data.setdefault("pending", {})
        if is_allowed(context.bot_data, me.id):
            await query.answer("You already have access 🎉")
            return None
        if me.id in pending:
            await query.answer("Already sent ⏳")
            return None
        pending[me.id] = display_name(me)
        await query.answer("Request sent 📨")
        await query.edit_message_text(
            "📨 Request sent! You'll get a message here when it's approved.")
        if config.ADMIN_ID:
            await context.bot.send_message(
                config.ADMIN_ID,
                f"🙋 <b>{html.escape(pending[me.id])}</b> wants to use your budget bot.\n"
                f"ID: <code>{me.id}</code>",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[
                    Btn("✅ Approve", callback_data=f"ua|ok|{me.id}"),
                    Btn("❌ Decline", callback_data=f"ua|no|{me.id}")]]))
        return None

    if me.id != config.ADMIN_ID:
        await query.answer()
        return None

    uid = int(parts[2])
    name = context.bot_data.setdefault("pending", {}).pop(uid, str(uid))
    if action == "ok":
        context.bot_data.setdefault("removed", set()).discard(uid)
        registry(context.bot_data).setdefault(uid, {"name": name, "sheet": None})
        await query.answer("Approved ✅")
        await query.edit_message_text(f"✅ Approved <b>{html.escape(name)}</b>. "
                                      "They'll now connect their own sheet.", parse_mode=ParseMode.HTML)
        await context.bot.send_message(uid, "🎉 <b>You're in!</b> Welcome to the budget bot 💸",
                                       parse_mode=ParseMode.HTML)
        await ask_for_sheet(context, uid)
        return uid
    if action == "no":
        await query.answer("Declined")
        await query.edit_message_text(f"❌ Declined {html.escape(name)}.", parse_mode=ParseMode.HTML)
        await context.bot.send_message(uid, "Sorry, your access request was declined. 🙏")
    return None


# ---------------------------------------------------------------- linking a sheet

def sheet_instructions() -> str:
    return ("📄 <b>Let's connect your own Google Sheet</b> (2 minutes)\n\n"
            "1️⃣ Create an empty sheet: https://sheets.new\n"
            "2️⃣ Click <b>Share</b> and add this email as <b>Editor</b>:\n"
            f"<code>{html.escape(sheets.robot_email())}</code>\n<i>(tap it to copy)</i>\n"
            "3️⃣ Copy the sheet's link from your browser and paste it here 👇\n\n"
            "I'll build the dashboard, charts and everything else for you ✨")


async def ask_for_sheet(context: ContextTypes.DEFAULT_TYPE, uid: int):
    await context.bot.send_message(uid, sheet_instructions(), parse_mode=ParseMode.HTML,
                                   disable_web_page_preview=True)


async def handle_link_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str | None:
    """For an approved user without a sheet: try the pasted link.

    Returns "linked" when the sheet is ready, "handled" when the message was used
    (instructions re-sent or an error shown), or None when the user already has a sheet.
    """
    uid = update.effective_user.id
    if sheet_of(context.bot_data, uid):
        return None
    msg = update.effective_message
    sid = sheets.extract_id(msg.text or "")
    if not sid:
        await msg.reply_text(sheet_instructions(), parse_mode=ParseMode.HTML,
                             disable_web_page_preview=True)
        return "handled"
    owners = [u for u, s in with_sheets(context.bot_data) if s == sid and u != uid]
    if owners:
        await msg.reply_text("🚫 That sheet is already used by someone else. Please create a new one.")
        return "handled"

    await msg.reply_text("⏳ Building your sheet… (about 20 seconds)")
    try:
        title = await asyncio.to_thread(setup_sheet.build, sid, log.info)
    except (gspread.exceptions.SpreadsheetNotFound, gspread.exceptions.APIError,
            PermissionError) as e:
        log.warning("Could not open sheet for %s: %s", uid, e)
        await msg.reply_text(
            "🔒 I can't open that sheet yet.\nMake sure you shared it with\n"
            f"<code>{html.escape(sheets.robot_email())}</code>\nas <b>Editor</b>, then paste the link again.",
            parse_mode=ParseMode.HTML)
        return "handled"
    user = registry(context.bot_data)[uid]
    user["sheet"] = sid
    user["name"] = user["name"] or display_name(update.effective_user)
    await msg.reply_text(f'✅ <b>"{html.escape(title)}" is ready!</b>\n'
                         f'<a href="{sheets.sheet_url(sid)}">Open your sheet</a>',
                         parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    return "linked"


# ---------------------------------------------------------------- admin commands

async def cmd_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != config.ADMIN_ID:
        return
    lines = ["👥 <b>Users</b>"]
    for uid, u in registry(context.bot_data).items():
        role = " 👑" if uid == config.ADMIN_ID else ""
        sheet = "📄 sheet linked" if u["sheet"] else "⏳ no sheet yet"
        lines.append(f"• {html.escape(u['name'] or 'Unknown')}{role} · <code>{uid}</code> · {sheet}")
    pending = context.bot_data.get("pending", {})
    if pending:
        lines.append("\n⏳ <b>Waiting for approval</b>")
        lines += [f"• {html.escape(n)} · <code>{uid}</code>" for uid, n in pending.items()]
    lines.append("\nRemove someone with <code>/remove ID</code>")
    await update.effective_message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def cmd_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != config.ADMIN_ID:
        return
    if not context.args or not context.args[0].isdigit():
        await update.effective_message.reply_text("Use: /remove 123456789 (see /users for IDs)")
        return
    uid = int(context.args[0])
    if uid == config.ADMIN_ID:
        await update.effective_message.reply_text("You can't remove yourself 😄")
        return
    user = registry(context.bot_data).pop(uid, None)
    context.bot_data.setdefault("removed", set()).add(uid)
    if user is None:
        await update.effective_message.reply_text("That ID isn't a user.")
        return
    await update.effective_message.reply_text(
        f"🗑️ Removed {html.escape(user['name'] or str(uid))}. Their Google Sheet is untouched.",
        parse_mode=ParseMode.HTML)
