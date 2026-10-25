"""Budget setup conversation: total per month, then how to split it.

Runs on the first /start, with /setup, or from the ✏️ button under /budget.
Progress lives in context.user_data["setup"]; every button starts with "su|".
"""

from __future__ import annotations

import asyncio
import re

from telegram import InlineKeyboardButton as Btn, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import ContextTypes

import sheets
import stats
from categories import CATEGORY_NAMES, EMOJI, SHORT

# Share of the total for each category, from a typical student budget (no rent).
SPLIT = {
    "Groceries": 0.50, "Eating Out": 0.125, "Housing": 0, "Transport": 0.075, "Studies": 0.025,
    "Phone & Subscriptions": 0.05, "Health & Care": 0.05, "Household": 0.05, "Clothing": 0.025,
    "Leisure": 0.075, "Travel": 0, "Admin & Fees": 0, "Other": 0.025,
}
TOTAL_CHOICES = [100, 150, 200, 250, 300, 400, 500, 600]
NUMBER = re.compile(r"^\s*€?\s*(\d{1,6}(?:[.,]\d{1,2})?)\s*(?:€|e|eur|euros?)?\s*$", re.I)


def auto_split(total: int) -> dict[str, int]:
    step = 5 if total >= 100 else 1
    split = {c: int(round(total * SPLIT[c] / step) * step) for c in CATEGORY_NAMES}
    split["Groceries"] += total - sum(split.values())  # rounding leftovers
    return split


def _state(context) -> dict:
    return context.user_data.setdefault("setup", {"total": 0, "split": {c: 0 for c in CATEGORY_NAMES}})


def _left(st: dict) -> int:
    return st["total"] - sum(st["split"].values())


def _kb(rows) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(rows)


async def _show(update_or_query, text: str, markup=None):
    """Edit the current setup message when coming from a button, else send a new one."""
    if hasattr(update_or_query, "edit_message_text"):
        try:
            await update_or_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
        except BadRequest as e:
            if "not modified" not in str(e):
                raise
    else:
        await update_or_query.effective_message.reply_text(text, parse_mode=ParseMode.HTML,
                                                           reply_markup=markup)


# ---------------------------------------------------------------- screens

def total_screen(first_time: bool) -> tuple[str, InlineKeyboardMarkup]:
    intro = ("👋 <b>Welcome!</b> I'm your money buddy 💸\n"
             "Let's set up your budget. It takes 30 seconds.\n\n" if first_time else "")
    text = (intro + "💶 <b>How much can you spend per month?</b>\n"
            "<i>Everything you pay yourself: food, transport, fun… "
            "Leave out rent if someone else pays it.</i>")
    buttons = [Btn(f"€{n}", callback_data=f"su|t|{n}") for n in TOTAL_CHOICES]
    rows = [buttons[i:i + 4] for i in range(0, len(buttons), 4)]
    rows.append([Btn("✍️ Type another amount", callback_data="su|tt")])
    if not first_time:
        rows.append([Btn("❌ Cancel", callback_data="su|cancel")])
    else:
        rows.append([Btn("⏭️ Later", callback_data="su|later")])
    return text, _kb(rows)


def split_choice_screen(total: int) -> tuple[str, InlineKeyboardMarkup]:
    text = (f"Nice, <b>€{total}</b> per month (≈ {stats.eur(total / 30)}/day) 👌\n\n"
            "<b>How do you want to split it?</b>\n"
            "🤖 <b>Split it for me:</b> a typical student split. You can tweak it after.\n"
            "✍️ <b>Choose myself:</b> I'll ask category by category.")
    return text, _kb([[Btn("🤖 Split it for me", callback_data="su|auto")],
                      [Btn("✍️ Choose myself", callback_data="su|man")],
                      [Btn("⬅️ Change total", callback_data="su|total")]])


def review_screen(st: dict) -> tuple[str, InlineKeyboardMarkup]:
    total, split = st["total"], st["split"]
    assigned = sum(split.values())
    left = total - assigned
    if left == 0:
        status = f"Assigned: €{assigned} ✅ Perfect!"
    elif left > 0:
        status = f"Assigned: €{assigned}. <b>€{left} left</b> to place 👇"
    else:
        status = f"Assigned: €{assigned}. <b>€{-left} over</b> your total ⚠️"
    lines = [f"🎯 <b>Your budget: €{total}/month</b>", status, ""]
    for c in CATEGORY_NAMES:
        amount = split[c]
        if amount:
            share = amount / total if total else 0
            lines.append(f"{EMOJI[c]} {c}: <b>€{amount}</b>  <i>{share:.0%}</i>")
    zeros = [EMOJI[c] for c in CATEGORY_NAMES if not split[c]]
    if zeros:
        lines.append(f"\n<i>No budget: {' '.join(zeros)}</i>")
    lines.append("\nTap a category to change it.")
    buttons = [Btn(f"{EMOJI[c]} {SHORT[c]} €{split[c]}", callback_data=f"su|e|{i}")
               for i, c in enumerate(CATEGORY_NAMES)]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows.append([Btn("🤖 Auto split", callback_data="su|auto"),
                 Btn("💶 Change total", callback_data="su|total")])
    rows.append([Btn("✅ Save my budget", callback_data="su|save")])
    return "\n".join(lines), _kb(rows)


def edit_screen(st: dict, ci: int) -> tuple[str, InlineKeyboardMarkup]:
    c = CATEGORY_NAMES[ci]
    left = _left(st)
    left_text = f"€{left} left to place" if left >= 0 else f"€{-left} over total"
    text = f"{EMOJI[c]} <b>{c}</b>: €{st['split'][c]} per month\n<i>{left_text}</i>"
    rows = [[Btn("−10", callback_data=f"su|a|{ci}|-10"), Btn("−5", callback_data=f"su|a|{ci}|-5"),
             Btn("+5", callback_data=f"su|a|{ci}|5"), Btn("+10", callback_data=f"su|a|{ci}|10")],
            [Btn("€0", callback_data=f"su|a|{ci}|zero"), Btn("✍️ Type", callback_data=f"su|et|{ci}")]]
    if left > 0:
        rows[1].insert(1, Btn(f"+ all left (€{left})", callback_data=f"su|a|{ci}|{left}"))
    rows.append([Btn("⬅️ Back to list", callback_data="su|r")])
    return text, _kb(rows)


def guided_screen(st: dict, ci: int) -> tuple[str, InlineKeyboardMarkup]:
    c = CATEGORY_NAMES[ci]
    left = _left(st)
    suggested = auto_split(st["total"])[c]
    text = (f"<b>{ci + 1}/{len(CATEGORY_NAMES)}</b> · {EMOJI[c]} <b>{c}</b>\n"
            f"How much per month? <i>€{left} left</i>")
    rows = []
    if 0 < suggested <= max(left, 0):
        rows.append([Btn(f"💡 €{suggested} (suggested)", callback_data=f"su|g|{ci}|{suggested}")])
    options = [v for v in (5, 10, 15, 20, 30, 50, 75, 100, 150) if v <= left and v != suggested][:8]
    buttons = [Btn(f"€{v}", callback_data=f"su|g|{ci}|{v}") for v in options]
    rows += [buttons[i:i + 4] for i in range(0, len(buttons), 4)]
    last = [Btn("€0 / skip", callback_data=f"su|g|{ci}|0"), Btn("✍️ Type", callback_data=f"su|gt|{ci}")]
    if left > 0:
        last.insert(1, Btn(f"All left €{left}", callback_data=f"su|g|{ci}|{left}"))
    rows.append(last)
    rows.append([Btn("⏩ Skip the rest", callback_data="su|r")])
    return text, _kb(rows)


# ---------------------------------------------------------------- entry points

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE, first_time: bool = False):
    context.user_data["setup"] = {"total": 0, "split": {c: 0 for c in CATEGORY_NAMES},
                                  "first_time": first_time}
    await _show(update, *total_screen(first_time))


async def edit_current(target, context: ContextTypes.DEFAULT_TYPE, sid: str):
    """Open the review screen with the budgets currently in the sheet."""
    current = await asyncio.to_thread(sheets.budgets, sid, 0)
    split = {c: int(round(current.get(c, 0))) for c in CATEGORY_NAMES}
    context.user_data["setup"] = {"total": sum(split.values()), "split": split}
    await _show(target, *review_screen(context.user_data["setup"]))


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Handle a typed number while setup is waiting for one. Returns True if consumed."""
    st = context.user_data.get("setup")
    if not st or not st.get("awaiting"):
        return False
    m = NUMBER.match(update.effective_message.text or "")
    if not m:
        await update.effective_message.reply_text("🔢 Just a number please, like <code>180</code>",
                                                  parse_mode=ParseMode.HTML)
        return True
    value = int(round(float(m.group(1).replace(",", "."))))
    awaiting = st.pop("awaiting")
    if awaiting == "total":
        if value <= 0:
            st["awaiting"] = "total"
            await update.effective_message.reply_text("🤔 It has to be more than €0. Try again:")
            return True
        st["total"] = value
        await _show(update, *split_choice_screen(value))
    elif awaiting.startswith("g:"):
        ci = int(awaiting[2:])
        st["split"][CATEGORY_NAMES[ci]] = value
        await _next_guided(update, st, ci)
    elif awaiting.startswith("e:"):
        ci = int(awaiting[2:])
        st["split"][CATEGORY_NAMES[ci]] = value
        await _show(update, *review_screen(st))
    return True


async def _next_guided(target, st: dict, ci: int):
    if ci + 1 < len(CATEGORY_NAMES) and _left(st) > 0:
        await _show(target, *guided_screen(st, ci + 1))
    else:
        await _show(target, *review_screen(st))


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE, sid: str, menu=None):
    query = update.callback_query
    parts = query.data.split("|")[1:]
    action = parts[0]
    st = _state(context)
    st.pop("awaiting", None)

    if action == "t":
        st["total"] = int(parts[1])
        await query.answer()
        await _show(query, *split_choice_screen(st["total"]))

    elif action == "tt":
        st["awaiting"] = "total"
        await query.answer()
        await _show(query, "✍️ Type your monthly budget in euros, like <code>180</code>")

    elif action == "total":
        await query.answer()
        await _show(query, *total_screen(st.get("first_time", False)))

    elif action == "auto":
        if not st["total"]:
            await query.answer("Pick a total first")
            await _show(query, *total_screen(st.get("first_time", False)))
            return
        st["split"] = auto_split(st["total"])
        await query.answer("Split done 🤖")
        await _show(query, *review_screen(st))

    elif action == "man":
        st["split"] = {c: 0 for c in CATEGORY_NAMES}
        await query.answer()
        await _show(query, *guided_screen(st, 0))

    elif action == "g":
        ci, value = int(parts[1]), int(parts[2])
        st["split"][CATEGORY_NAMES[ci]] = value
        await query.answer()
        await _next_guided(query, st, ci)

    elif action == "gt":
        st["awaiting"] = f"g:{parts[1]}"
        await query.answer()
        c = CATEGORY_NAMES[int(parts[1])]
        await _show(query, f"✍️ How much for {EMOJI[c]} <b>{c}</b>? Type a number, like <code>35</code>")

    elif action == "e":
        await query.answer()
        await _show(query, *edit_screen(st, int(parts[1])))

    elif action == "a":
        ci, delta = int(parts[1]), parts[2]
        c = CATEGORY_NAMES[ci]
        st["split"][c] = 0 if delta == "zero" else max(0, st["split"][c] + int(delta))
        await query.answer(f"€{st['split'][c]}")
        await _show(query, *edit_screen(st, ci))

    elif action == "et":
        st["awaiting"] = f"e:{parts[1]}"
        await query.answer()
        c = CATEGORY_NAMES[int(parts[1])]
        await _show(query, f"✍️ How much for {EMOJI[c]} <b>{c}</b>? Type a number, like <code>35</code>")

    elif action == "r":
        await query.answer()
        await _show(query, *review_screen(st))

    elif action == "save":
        await query.answer("Saving…")
        await asyncio.to_thread(sheets.save_budgets, sid, st["split"])
        context.user_data["onboarded"] = True
        total = sum(st["split"].values())
        context.user_data.pop("setup", None)
        lines = [f"✅ <b>Budget saved: €{total}/month</b>",
                 f"That's about {stats.eur(total / 30)} a day or {stats.eur(total * 12 / 52)} a week.", ""]
        lines += [f"{EMOJI[c]} {c}: €{v}" for c, v in st["split"].items() if v]
        lines += ["", "🚀 Now just type what you spend, like <code>4.50</code>, and tap a category.",
                  "Change it any time with /setup or the ✏️ button under 🎯 Budget."]
        await _show(query, "\n".join(lines))
        if menu is not None:
            await query.message.reply_text("Your shortcuts are below 👇", reply_markup=menu)

    elif action == "later":
        context.user_data["onboarded"] = True
        context.user_data.pop("setup", None)
        await query.answer()
        await _show(query, "👍 No problem! I'm using the default budget for now. "
                           "Set yours any time with /setup.")
        if menu is not None:
            await query.message.reply_text("Type an amount like <code>4.50</code> to start 🚀",
                                           parse_mode=ParseMode.HTML, reply_markup=menu)

    elif action == "edit":
        await query.answer()
        await edit_current(query, context, sid)

    elif action == "cancel":
        context.user_data.pop("setup", None)
        await query.answer("Cancelled")
        await _show(query, "❌ Budget setup cancelled. Nothing changed.")

    else:
        await query.answer()

