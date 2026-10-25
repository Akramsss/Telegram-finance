"""Telegram bot: send what you spent, tap a category, it lands in your Google Sheet.

Several people can use it; each one has their own sheet (see users.py).
Run with:  python bot.py
"""

from __future__ import annotations

import asyncio
import functools
import html
import logging
import re
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta

from telegram import (
    BotCommand, BotCommandScopeChat, ForceReply, InlineKeyboardButton as Btn, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, Update,
)
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler,
    PicklePersistence, filters,
)

import config
import fun
import onboarding
import sheets
import stats
import users
from categories import (
    CATEGORY_NAMES, EMOJI, INCOME_NAMES, SHORT, SUB_EMOJI, SUBCATEGORIES, label, sub_label,
)
from parser import ParseResult, Transaction, parse_message

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("bot")

MENU = ReplyKeyboardMarkup(
    [["📅 Today", "🗓️ Week", "📆 Month"], ["🎯 Budget", "🧾 Last", "↩️ Undo"]],
    resize_keyboard=True, is_persistent=True, input_field_placeholder="Type an amount… e.g. 4.50",
)

HELP = """<b>How it works</b> 🤖

<b>1.</b> Type the amount 👉 <code>4.50</code>
<b>2.</b> Tap a category, then the exact thing
<b>3.</b> Done ✅ (tap ✏️ to add a name if you like)

Money coming in? Start with a plus 👉 <code>+250</code>

<b>Lazy mode</b> 😎 type it all at once and I'll guess the category:
• <code>kebab 8 cash</code>
• <code>milk 0.95, eggs 2.49 @Lidl</code>
• <code>yesterday CROUS 3.30</code>

Use the buttons below the chat for your stats.
Change your budget any time with /setup ✏️  ·  Open your sheet with /sheet 📊
I also send a report every Sunday evening and on the 1st of the month. 📬"""

AMOUNT_ONLY = re.compile(r"^\s*(\+)?\s*€?\s*(\d{1,6}(?:[.,]\d{1,2})?)\s*(?:€|e|eur|euros?)?\s*$", re.I)


def now() -> datetime:
    return datetime.now(config.TIMEZONE)


def today() -> date:
    return now().date()


async def run(fn, *args, **kwargs):
    """Run a blocking Google Sheets call without freezing the bot."""
    return await asyncio.to_thread(fn, *args, **kwargs)


def sid_of(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str | None:
    """The spreadsheet ID of whoever sent this update."""
    return users.sheet_of(context.bot_data, update.effective_user.id)


def member(fn):
    """Only let approved users with a linked sheet through."""
    @functools.wraps(fn)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        uid = update.effective_user.id
        if not users.is_allowed(context.bot_data, uid):
            await users.stranger(update, context)
        elif not sid_of(update, context):
            await users.ask_for_sheet(context, uid)
        else:
            await fn(update, context)
    return wrapper


async def send(update: Update, text: str, **kwargs):
    return await update.effective_message.reply_text(
        text, parse_mode=ParseMode.HTML, disable_web_page_preview=True, **kwargs)


async def send_chart(context: ContextTypes.DEFAULT_TYPE, chat_id: int, image, caption: str = ""):
    if image:
        await context.bot.send_photo(chat_id, image, caption=caption[:1024] or None,
                                     parse_mode=ParseMode.HTML)


async def safe_edit(query, text: str, markup=None):
    try:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
    except BadRequest as e:  # "message is not modified" when nothing changed
        if "not modified" not in str(e):
            raise


def parse_amount(text: str) -> tuple[int, bool] | None:
    """'4.50' -> (450, False); '+250' -> (25000, True); anything else -> None."""
    m = AMOUNT_ONLY.match(text)
    if not m:
        return None
    cents = round(float(m.group(2).replace(",", ".")) * 100)
    return (cents, bool(m.group(1))) if cents > 0 else None


def eur_cents(cents: int) -> str:
    return stats.eur(cents / 100)


# ---------------------------------------------------------------- keyboards

def quick_picks(rows: list[sheets.Row], limit: int = 4) -> list[tuple[str, str]]:
    """Most used (category, subcategory) pairs over the last 60 days."""
    since = today() - timedelta(days=60)
    counts = Counter((r.category, r.subcategory) for r in rows
                     if r.type == "Expense" and r.date >= since and r.category in SUBCATEGORIES
                     and r.subcategory in SUBCATEGORIES[r.category])
    return [pair for pair, n in counts.most_common(limit) if n >= 2]


def category_keyboard(cents: int, picks: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows = []
    quick = [Btn(f"⚡ {sub_label(sub)}",
                 callback_data=f"ps|{cents}|{CATEGORY_NAMES.index(cat)}|{SUBCATEGORIES[cat].index(sub)}")
             for cat, sub in picks]
    rows += [quick[i:i + 2] for i in range(0, len(quick), 2)]
    cats = [Btn(f"{EMOJI[c]} {SHORT[c]}", callback_data=f"pc|{cents}|{i}")
            for i, c in enumerate(CATEGORY_NAMES)]
    rows += [cats[i:i + 3] for i in range(0, len(cats), 3)]
    rows.append([Btn("💰 It's income", callback_data=f"pin|{cents}"),
                 Btn("❌ Cancel", callback_data="px")])
    return InlineKeyboardMarkup(rows)


def sub_keyboard(cents: int, ci: int) -> InlineKeyboardMarkup:
    subs = SUBCATEGORIES[CATEGORY_NAMES[ci]]
    buttons = [Btn(sub_label(s), callback_data=f"ps|{cents}|{ci}|{si}") for si, s in enumerate(subs)]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows.append([Btn("⬅️ Back", callback_data=f"pb|{cents}")])
    return InlineKeyboardMarkup(rows)


def income_keyboard(cents: int) -> InlineKeyboardMarkup:
    buttons = []
    for ii, cat in enumerate(INCOME_NAMES):
        for si, sub in enumerate(SUBCATEGORIES[cat]):
            text = sub_label(sub) if len(SUBCATEGORIES[cat]) > 1 else f"{EMOJI[cat]} {cat}"
            buttons.append(Btn(text, callback_data=f"pi|{cents}|{ii}|{si}"))
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows.append([Btn("💸 It's an expense", callback_data=f"pb|{cents}"),
                 Btn("❌ Cancel", callback_data="px")])
    return InlineKeyboardMarkup(rows)


def saved_keyboard(r: sheets.Row) -> InlineKeyboardMarkup:
    named = r.item and r.item != r.subcategory
    first = [
        Btn("✏️ Rename" if named else "✏️ Name it", callback_data=f"nm|{r.id}"),
        Btn("📅 Today" if r.date != today() else "📅 Yesterday", callback_data=f"dt|{r.id}"),
        Btn("💳 Card" if r.payment == "Cash" else "💵 Cash", callback_data=f"pm|{r.id}"),
    ]
    second = [Btn("↩️ Undo", callback_data=f"undo|{r.id.rsplit('-', 1)[0]}|1")]
    if r.type == "Expense":
        second.insert(0, Btn("🏷️ Change", callback_data=f"chcat|{r.id}"))
    return InlineKeyboardMarkup([first, second])


# ---------------------------------------------------------------- saved message

def render_saved(r: sheets.Row, rows: list[sheets.Row], budgets: dict[str, float]) -> str:
    t = today()
    if r.type == "Income":
        lines = [f"💰 <b>+{stats.eur(r.amount)}</b> → {sub_label(r.subcategory)}"]
        reaction = fun.quip(r.category, income=True, seed=r.id)
    else:
        lines = [f"✅ <b>{stats.eur(r.amount)}</b> → {sub_label(r.subcategory)}"]
        reaction = fun.quip(r.category, r.subcategory, seed=r.id)
    if r.item and r.item != r.subcategory:
        lines.append(f"📝 {html.escape(r.item)}")
    meta = []
    if r.store:
        meta.append(f"📍 {html.escape(r.store)}")
    if r.payment == "Cash":
        meta.append("💵 Cash")
    if r.date != t:
        meta.append(f"📅 {'Yesterday' if r.date == t - timedelta(days=1) else f'{r.date:%a %d %b}'}")
    if meta:
        lines.append(" · ".join(meta))
    lines.append(f"<i>{reaction}</i>")

    if r.type == "Expense":
        start = stats.month_start(t)
        spent = sum(x.amount for x in stats.in_range(rows, start, t + timedelta(days=1))
                    if x.category == r.category)
        budget = budgets.get(r.category, 0)
        if budget > 0:
            lines.append(f"\n{EMOJI.get(r.category, '')} {r.category} in {t:%B}\n"
                         f"{stats.bar(spent / budget)} {stats.eur(spent)} / {stats.eur(budget)}")
            mood = fun.budget_mood(spent, budget, seed=r.id)
            if mood:
                lines.append(f"<b>{mood}</b>")
        else:
            lines.append(f"\n{EMOJI.get(r.category, '')} {r.category} in {t:%B}: {stats.eur(spent)}")

    streak_text = fun.streak_line(fun.streak({x.date for x in rows}, t))
    if streak_text:
        lines.append(streak_text)
    return "\n".join(lines)


async def show_saved(target, sid: str, tx_id: str, context: ContextTypes.DEFAULT_TYPE | None = None,
                     chat_id: int | None = None, message_id: int | None = None):
    """Draw (or re-draw) the confirmation for one saved transaction."""
    rows, budgets = await asyncio.gather(run(sheets.read_transactions, sid), run(sheets.budgets, sid))
    r = next((x for x in rows if x.id == tx_id), None)
    if r is None:
        text, markup = "🤷 That entry isn't in the sheet anymore.", None
    else:
        text, markup = render_saved(r, rows, budgets), saved_keyboard(r)
    if chat_id and message_id and context:
        try:
            await context.bot.edit_message_text(text, chat_id=chat_id, message_id=message_id,
                                                parse_mode=ParseMode.HTML, reply_markup=markup)
        except BadRequest as e:
            if "not modified" not in str(e):
                raise
    elif hasattr(target, "edit_message_text"):
        await safe_edit(target, text, markup)
    else:
        await target.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)


# ---------------------------------------------------------------- commands

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not config.ADMIN_ID:
        await send(update, f"👋 Hi! Your Telegram user ID is <code>{user.id}</code>.\n\n"
                           "Put it in the <code>.env</code> file as "
                           f"<code>ALLOWED_USER_IDS={user.id}</code>, then restart the bot.")
        return
    if not users.is_allowed(context.bot_data, user.id):
        await users.stranger(update, context)
        return
    record = users.registry(context.bot_data)[user.id]
    record["name"] = record["name"] or users.display_name(user)
    name = html.escape(user.first_name or "friend")
    if not sid_of(update, context):
        await send(update, f"👋 Hey {name}! I'm your money buddy 💸")
        await users.ask_for_sheet(context, user.id)
        return
    if not context.user_data.get("onboarded"):
        await onboarding.start(update, context, first_time=True)
        return
    await send(update, f"👋 Hey {name}! I'm your money buddy 💸\n\n" + HELP, reply_markup=MENU)


async def cmd_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await onboarding.start(update, context)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send(update, HELP, reply_markup=MENU)


async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = await run(sheets.read_transactions, sid_of(update, context))
    await send(update, stats.today_report(rows, today()))


async def cmd_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = await run(sheets.read_transactions, sid_of(update, context))
    t = today()
    await send(update, stats.week_report(rows, t))
    start = stats.week_start(t)
    await send_chart(context, update.effective_chat.id,
                     stats.category_chart(stats.in_range(rows, start, start + timedelta(days=7)),
                                          "This week by category"))


async def cmd_month(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = today()
    month = t
    if context.args:
        try:
            month = datetime.strptime(context.args[0], "%Y-%m").date()
        except ValueError:
            await send(update, "Use the format <code>/month 2026-09</code>")
            return
    sid = sid_of(update, context)
    rows, budgets = await asyncio.gather(run(sheets.read_transactions, sid), run(sheets.budgets, sid))
    await send(update, stats.month_report(rows, month, t))
    start = stats.month_start(month)
    end = (start + timedelta(days=32)).replace(day=1)
    await send_chart(context, update.effective_chat.id,
                     stats.category_chart(stats.in_range(rows, start, end),
                                          f"{start:%B %Y} by category", budgets))


async def cmd_budget(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sid = sid_of(update, context)
    rows, budgets = await asyncio.gather(run(sheets.read_transactions, sid), run(sheets.budgets, sid))
    t = today()
    text = stats.budget_report(rows, budgets, t)
    tips = stats.insights(rows, t)
    if tips:
        text += "\n\n" + "\n".join(tips)
    await send(update, text, reply_markup=InlineKeyboardMarkup(
        [[Btn("✏️ Change my budget", callback_data="su|edit")]]))


async def cmd_last(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = await run(sheets.read_transactions, sid_of(update, context))
    if not rows:
        await send(update, "Nothing yet! Type an amount like <code>4.50</code> to start 🚀")
        return
    lines = ["🧾 <b>Last 10 entries</b>"]
    for r in rows[-10:][::-1]:
        sign = "+" if r.type == "Income" else ""
        name = r.item if r.item and r.item != r.subcategory else r.subcategory
        lines.append(f"{r.date:%d/%m} · {sub_label(r.subcategory)} — {sign}{stats.eur(r.amount)}"
                     + (f" <i>({html.escape(name)})</i>" if name != r.subcategory else ""))
    await send(update, "\n".join(lines))


async def cmd_undo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sid = sid_of(update, context)
    batch = context.user_data.pop("last_batch", None)
    if batch:
        n = await run(sheets.delete_transactions, sid, batch)
        await send(update, f"↩️ Poof! Removed your last entry ({n} item{'s' if n != 1 else ''}). 🪄")
        return
    row = await run(sheets.delete_last_row, sid)
    if row:
        await send(update, f"↩️ Poof! Removed {html.escape(row.item)} — {stats.eur(row.amount)} 🪄")
    else:
        await send(update, "Nothing to undo 🤷")


async def cmd_sheet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send(update, f'📊 <a href="{sheets.sheet_url(sid_of(update, context))}">Open your budget sheet</a>')


async def cmd_categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    budgets = await run(sheets.budgets, sid_of(update, context))
    lines = ["🏷️ <b>Categories</b> (monthly budget)"]
    for cat in CATEGORY_NAMES:
        b = budgets.get(cat, 0)
        lines.append(f"{label(cat)} — {stats.eur(b) if b else 'no budget'}\n"
                     f"   {' '.join(sub_label(s) for s in SUBCATEGORIES[cat])}")
    lines.append("\nChange budgets with /setup or in the <b>Budgets</b> tab of your sheet.")
    await send(update, "\n".join(lines))


async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await weekly_report_for(context, update.effective_user.id, sid_of(update, context))


MENU_ACTIONS = {
    "📅 Today": cmd_today, "🗓️ Week": cmd_week, "📆 Month": cmd_month,
    "🎯 Budget": cmd_budget, "🧾 Last": cmd_last, "↩️ Undo": cmd_undo,
}


# ---------------------------------------------------------------- incoming text

async def ask_category(update: Update, sid: str, cents: int, income: bool):
    if income:
        await send(update, f"💰 <b>+{eur_cents(cents)}</b> coming in! Where from?",
                   reply_markup=income_keyboard(cents))
        return
    rows = await run(sheets.read_transactions, sid)
    await send(update, f"💶 <b>{eur_cents(cents)}</b> — what was it?",
               reply_markup=category_keyboard(cents, quick_picks(rows)))


def _to_rows(ids: list[str], items: list[Transaction]) -> list[sheets.Row]:
    return [sheets.Row(i, t.date, t.type, t.item, t.amount, t.category, t.subcategory,
                       t.store, t.payment) for i, t in zip(ids, items)]


def _multi_confirmation(items: list[Transaction], rows_after: list[sheets.Row]) -> str:
    t = today()
    total = sum(x.amount for x in items if x.type == "Expense")
    lines = [f"✅ Saved {len(items)} things — <b>{stats.eur(total)}</b>"]
    for x in items:
        sign = "+" if x.type == "Income" else ""
        lines.append(f"{SUB_EMOJI.get(x.subcategory, '•')} {html.escape(x.item)} — {sign}{stats.eur(x.amount)}")
    first = items[0]
    meta = [f"📍 {html.escape(first.store)}"] if first.store else []
    if first.payment == "Cash":
        meta.append("💵 Cash")
    if first.date != t:
        meta.append(f"📅 {first.date:%a %d %b}")
    if meta:
        lines.append(" · ".join(meta))
    spent_today = sum(r.amount for r in stats.in_range(rows_after, t, t + timedelta(days=1)))
    lines.append(f"\n<i>{fun.quip(first.category, first.subcategory, first.type == 'Income')}</i>"
                 f"\nToday so far: {stats.eur(spent_today)}")
    return "\n".join(lines)


async def save_typed(update: Update, context: ContextTypes.DEFAULT_TYPE, sid: str,
                     items: list[Transaction]):
    """Lazy mode: the message already had words, so save with the guessed category."""
    rows_before, budgets = await asyncio.gather(run(sheets.read_transactions, sid),
                                                run(sheets.budgets, sid))
    ids = await run(sheets.add_transactions, sid, items)
    context.user_data["last_batch"] = ids
    rows_after = rows_before + _to_rows(ids, items)

    if len(items) == 1:
        r = rows_after[-1]
        await send(update, render_saved(r, rows_after, budgets), reply_markup=saved_keyboard(r))
        return

    batch = ids[0].rsplit("-", 1)[0]
    await send(update, _multi_confirmation(items, rows_after),
               reply_markup=InlineKeyboardMarkup([[Btn("↩️ Undo all", callback_data=f"undo|{batch}|{len(ids)}")]]))
    added: dict[str, float] = defaultdict(float)
    for x in items:
        if x.type == "Expense" and stats.month_start(x.date) == stats.month_start(today()):
            added[x.category] += x.amount
    alerts = stats.budget_alerts(rows_after, budgets, set(added), added, today())
    if alerts:
        await send(update, "\n".join(alerts))


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.effective_message.text or "").strip()
    if not text:
        return
    uid = update.effective_user.id
    if not users.is_allowed(context.bot_data, uid):
        await users.stranger(update, context)
        return

    # Approved but no sheet yet: this message should be their sheet link
    linked = await users.handle_link_text(update, context)
    if linked == "linked":
        await onboarding.start(update, context, first_time=True)
        return
    if linked == "handled":
        return
    sid = sid_of(update, context)

    if text in MENU_ACTIONS:
        context.user_data.pop("naming", None)
        context.user_data.get("setup", {}).pop("awaiting", None)
        context.args = []
        await MENU_ACTIONS[text](update, context)
        return

    if await onboarding.handle_text(update, context):
        return

    amount = parse_amount(text)
    naming = context.user_data.pop("naming", None)
    if naming and amount is None:
        tx_id, chat_id, message_id = naming
        await run(sheets.update_fields, sid, tx_id, item=text[:80])
        await show_saved(None, sid, tx_id, context, chat_id, message_id)
        await send(update, f"✏️ Got it: <b>{html.escape(text[:80])}</b> 👍")
        return

    if amount:
        await ask_category(update, sid, *amount)
        return

    await context.bot.send_chat_action(update.effective_chat.id, "typing")
    result: ParseResult = await parse_message(text)
    if result.intent == "add":
        await save_typed(update, context, sid, result.transactions)
        return
    handler = {"today": cmd_today, "week": cmd_week, "month": cmd_month,
               "budget": cmd_budget, "undo": cmd_undo, "help": cmd_help}.get(result.intent)
    if handler:
        context.args = []
        await handler(update, context)
    else:
        await send(update, "🤔 Hmm, I didn't catch that.\nJust type an amount like <code>4.50</code> "
                           "and tap a category!")


# ---------------------------------------------------------------- buttons

async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.data.startswith("ua|"):  # access requests work for strangers too
        await users.on_button(update, context)
        return
    sid = sid_of(update, context)
    if not sid:
        await query.answer("Connect your sheet first 📄")
        return
    if query.data.startswith("su|"):
        await onboarding.on_button(update, context, sid, menu=MENU)
        return
    parts = query.data.split("|")
    action = parts[0]

    # Picking a category for a typed amount
    if action == "pc":
        cents, ci = int(parts[1]), int(parts[2])
        cat = CATEGORY_NAMES[ci]
        await query.answer()
        await safe_edit(query, f"💶 <b>{eur_cents(cents)}</b> › {EMOJI[cat]} {cat} — which one?",
                        sub_keyboard(cents, ci))

    elif action == "pb":
        cents = int(parts[1])
        await query.answer()
        rows = await run(sheets.read_transactions, sid)
        await safe_edit(query, f"💶 <b>{eur_cents(cents)}</b> — what was it?",
                        category_keyboard(cents, quick_picks(rows)))

    elif action == "pin":
        cents = int(parts[1])
        await query.answer()
        await safe_edit(query, f"💰 <b>+{eur_cents(cents)}</b> coming in! Where from?",
                        income_keyboard(cents))

    elif action == "px":
        await query.answer("Cancelled")
        await safe_edit(query, "❌ Cancelled. Nothing saved.")

    elif action in ("ps", "pi"):
        key = (query.message.chat_id, query.message.message_id)
        done = context.bot_data.setdefault("saved_msgs", set())
        if len(done) > 500:
            done.clear()
        if key in done:  # a fast double tap must not save twice
            await query.answer()
            return
        done.add(key)
        cents, ci, si = int(parts[1]), int(parts[2]), int(parts[3])
        if action == "ps":
            cat, ttype = CATEGORY_NAMES[ci], "Expense"
        else:
            cat, ttype = INCOME_NAMES[ci], "Income"
        sub = SUBCATEGORIES[cat][si]
        await query.answer("Saved ✅")
        tx = Transaction(item=sub, amount=cents / 100, category=cat, subcategory=sub, type=ttype,
                         date=today(), source="buttons")
        ids = await run(sheets.add_transactions, sid, [tx])
        context.user_data["last_batch"] = ids
        await show_saved(query, sid, ids[0])

    # Editing a saved entry
    elif action == "nm":
        await query.answer()
        context.user_data["naming"] = (parts[1], query.message.chat_id, query.message.message_id)
        await query.message.reply_text("✏️ What was it? Type a name:", reply_markup=ForceReply(
            input_field_placeholder="e.g. baguette, kebab, Navigo…"))

    elif action == "dt":
        await query.answer()
        r = await run(sheets.get_row, sid, parts[1])
        if r:
            new_date = today() - timedelta(days=1) if r.date == today() else today()
            await run(sheets.update_fields, sid, r.id, when=new_date)
        await show_saved(query, sid, parts[1])

    elif action == "pm":
        await query.answer()
        r = await run(sheets.get_row, sid, parts[1])
        if r:
            await run(sheets.update_fields, sid, r.id, payment="Card" if r.payment == "Cash" else "Cash")
        await show_saved(query, sid, parts[1])

    elif action == "undo":
        await query.answer("Undone")
        batch, n = parts[1], int(parts[2])
        ids = [f"{batch}-{i + 1}" for i in range(n)]
        deleted = await run(sheets.delete_transactions, sid, ids)
        if context.user_data.get("last_batch") == ids:
            context.user_data.pop("last_batch")
        await safe_edit(query, "↩️ <s>" + query.message.text_html.split("\n")[0] + "</s>\n"
                        + ("Poof! Removed from your sheet 🪄" if deleted else "Already removed."))

    # Changing the category of a saved entry
    elif action == "chcat":
        await query.answer()
        tx_id = parts[1]
        buttons = [Btn(f"{EMOJI[c]} {SHORT[c]}", callback_data=f"setcat|{tx_id}|{i}")
                   for i, c in enumerate(CATEGORY_NAMES)]
        rows = [buttons[i:i + 3] for i in range(0, len(buttons), 3)]
        rows.append([Btn("⬅️ Keep it", callback_data=f"keep|{tx_id}")])
        await query.edit_message_reply_markup(InlineKeyboardMarkup(rows))

    elif action == "setcat":
        await query.answer()
        tx_id, ci = parts[1], int(parts[2])
        subs = SUBCATEGORIES[CATEGORY_NAMES[ci]]
        if len(subs) == 1:
            await run(sheets.update_category, sid, tx_id, CATEGORY_NAMES[ci], subs[0])
            await show_saved(query, sid, tx_id)
            return
        buttons = [Btn(sub_label(s), callback_data=f"setsub|{tx_id}|{ci}|{si}")
                   for si, s in enumerate(subs)]
        rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
        rows.append([Btn("⬅️ Back", callback_data=f"chcat|{tx_id}")])
        await query.edit_message_reply_markup(InlineKeyboardMarkup(rows))

    elif action == "setsub":
        await query.answer("Updated 🏷️")
        tx_id, ci, si = parts[1], int(parts[2]), int(parts[3])
        cat = CATEGORY_NAMES[ci]
        await run(sheets.update_category, sid, tx_id, cat, SUBCATEGORIES[cat][si])
        await show_saved(query, sid, tx_id)

    elif action == "keep":
        await query.answer()
        await show_saved(query, sid, parts[1])

    else:
        await query.answer()


# ---------------------------------------------------------------- scheduled (every user)

async def for_each_user(context: ContextTypes.DEFAULT_TYPE, job):
    """Run a scheduled job for every user; one failing sheet must not stop the others."""
    for uid, sid in users.with_sheets(context.bot_data):
        try:
            await job(context, uid, sid)
        except Forbidden:
            log.info("User %s blocked the bot, skipping", uid)
        except Exception:
            log.exception("Scheduled job failed for user %s", uid)


async def weekly_report_for(context: ContextTypes.DEFAULT_TYPE, uid: int, sid: str):
    rows, budgets = await asyncio.gather(run(sheets.read_transactions, sid), run(sheets.budgets, sid))
    t = today()
    text = "📬 <b>Your weekly report</b>\n\n" + stats.week_report(rows, t)
    text += "\n\n" + stats.budget_report(rows, budgets, t)
    tips = stats.insights(rows, t)
    if tips:
        text += "\n\n" + "\n".join(tips)
    days = fun.streak({x.date for x in rows}, t)
    if days >= 2:
        text += f"\n\n🔥 Logging streak: {days} days. Keep it going!"
    await context.bot.send_message(uid, text, parse_mode=ParseMode.HTML)
    await send_chart(context, uid, stats.weekly_trend_chart(rows, t))


async def monthly_report_for(context: ContextTypes.DEFAULT_TYPE, uid: int, sid: str):
    rows, budgets = await asyncio.gather(run(sheets.read_transactions, sid), run(sheets.budgets, sid))
    t = today()
    last = stats.prev_month(t)
    text = "📬 <b>Your monthly report</b>\n\n" + stats.month_report(rows, last, t)
    spent = sum(r.amount for r in stats.in_range(rows, last, stats.month_start(t)))
    total_budget = sum(budgets.values())
    if total_budget:
        diff = total_budget - spent
        text += (f"\n\n🎯 Budget {stats.eur(total_budget)} → "
                 + (f"saved <b>{stats.eur(diff)}</b> 🎉🎉 Proud of you!" if diff >= 0
                    else f"over by <b>{stats.eur(-diff)}</b> 😬 New month, fresh start 💪"))
    await context.bot.send_message(uid, text, parse_mode=ParseMode.HTML)
    await send_chart(context, uid,
                     stats.category_chart(stats.in_range(rows, last, stats.month_start(t)),
                                          f"{last:%B %Y} by category", budgets))


async def daily_reminder_for(context: ContextTypes.DEFAULT_TYPE, uid: int, sid: str):
    rows = await run(sheets.read_transactions, sid)
    t = today()
    if any(r.date == t for r in rows):
        return
    days = fun.streak({x.date for x in rows}, t - timedelta(days=1))
    nudge = (f"Don't lose your 🔥 {days}-day streak!" if days >= 2
             else "Did you buy anything today?")
    await context.bot.send_message(
        uid,
        f"🌙 {nudge}\nJust type the amount, like <code>4.50</code>. "
        "If you spent nothing, enjoy your no-spend day 🧘",
        parse_mode=ParseMode.HTML)


async def weekly_report(context: ContextTypes.DEFAULT_TYPE):
    await for_each_user(context, weekly_report_for)


async def monthly_report(context: ContextTypes.DEFAULT_TYPE):
    await for_each_user(context, monthly_report_for)


async def daily_reminder(context: ContextTypes.DEFAULT_TYPE):
    await for_each_user(context, daily_reminder_for)


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    log.exception("Error while handling an update", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(
            "⚠️ Oops, I couldn't reach Google Sheets. Nothing was saved. Try again in a moment.")


# ---------------------------------------------------------------- main

USER_COMMANDS = [
    BotCommand("start", "Start / welcome"),
    BotCommand("today", "What I spent today"),
    BotCommand("week", "This week by category"),
    BotCommand("month", "This month (or /month 2026-09)"),
    BotCommand("budget", "What's left in my budgets"),
    BotCommand("last", "My last 10 entries"),
    BotCommand("undo", "Remove my last entry"),
    BotCommand("setup", "Set or change my monthly budget"),
    BotCommand("categories", "List of categories"),
    BotCommand("report", "Weekly report now"),
    BotCommand("sheet", "Open my Google Sheet"),
    BotCommand("help", "How to use the bot"),
]
ADMIN_COMMANDS = [
    BotCommand("users", "👑 List users and pending requests"),
    BotCommand("remove", "👑 Remove a user: /remove ID"),
]


async def post_init(app: Application):
    """Publish the command menu and the profile text people see before pressing Start."""
    try:
        await app.bot.set_my_commands(USER_COMMANDS)
        if config.ADMIN_ID:
            await app.bot.set_my_commands(USER_COMMANDS + ADMIN_COMMANDS,
                                          scope=BotCommandScopeChat(config.ADMIN_ID))
        await app.bot.set_my_short_description("💸 Track your spending in 2 taps. Your own Google Sheet budget.")
        await app.bot.set_my_description(
            "💸 Your money buddy!\n\nType what you spend (like 4.50), tap a category, done. "
            "Everything goes into your own Google Sheet with a dashboard, charts, budgets, "
            "weekly reports and streaks 🔥\n\nThis bot is private: press Start to request access.")
    except Exception:  # menus are nice to have; never block startup on them
        log.exception("Could not publish the command menu")

def main():
    missing = config.check()
    if missing:
        raise SystemExit("Missing settings: " + ", ".join(missing) + "\nSee SETUP.md.")

    # Persistence keeps users, their sheets, setup progress, etc. across restarts.
    app = (Application.builder().token(config.TELEGRAM_BOT_TOKEN)
           .persistence(PicklePersistence(filepath=config.BASE_DIR / "bot_state.pickle"))
           .connect_timeout(20).read_timeout(30).get_updates_read_timeout(40)
           .post_init(post_init).build())
    app.add_handler(CommandHandler("start", cmd_start))

    if not config.ADMIN_ID:
        log.warning("ALLOWED_USER_IDS is not set: send /start to the bot to get your ID.")
    else:
        for name, fn in [("help", cmd_help), ("setup", cmd_setup), ("today", cmd_today),
                         ("week", cmd_week), ("month", cmd_month), ("budget", cmd_budget),
                         ("last", cmd_last), ("undo", cmd_undo), ("sheet", cmd_sheet),
                         ("report", cmd_report), ("categories", cmd_categories)]:
            app.add_handler(CommandHandler(name, member(fn)))
        app.add_handler(CommandHandler("users", users.cmd_users))
        app.add_handler(CommandHandler("remove", users.cmd_remove))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, on_text))
        app.add_handler(CallbackQueryHandler(on_button))

        jq = app.job_queue
        tz = config.TIMEZONE
        if config.WEEKLY_REPORT:
            jq.run_daily(weekly_report, time(20, 0, tzinfo=tz), days=(0,))  # 0 = Sunday
        if config.MONTHLY_REPORT:
            jq.run_monthly(monthly_report, time(9, 0, tzinfo=tz), day=1)
        if config.DAILY_REMINDER:
            h, m = (int(x) for x in config.DAILY_REMINDER_TIME.split(":"))
            jq.run_daily(daily_reminder, time(h, m, tzinfo=tz))

    app.add_error_handler(on_error)
    log.info("Bot is running. Press Ctrl+C to stop.")
    # Keep retrying if the network is down at startup (Wi-Fi waking up, etc.)
    app.run_polling(allowed_updates=Update.ALL_TYPES, bootstrap_retries=-1)


if __name__ == "__main__":
    main()
