"""Summaries, budget checks and chart images for the bot's replies."""

from __future__ import annotations

import calendar
import io
from collections import defaultdict
from datetime import date, timedelta

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from categories import CATEGORY_NAMES, EMOJI, label  # noqa: E402
from sheets import Row  # noqa: E402


def eur(x: float) -> str:
    return f"-€{-x:,.2f}" if x < 0 else f"€{x:,.2f}"


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def month_start(d: date) -> date:
    return d.replace(day=1)


def prev_month(d: date) -> date:
    return (month_start(d) - timedelta(days=1)).replace(day=1)


def in_range(rows: list[Row], start: date, end: date, kind: str = "Expense") -> list[Row]:
    """Rows with start <= date < end."""
    return [r for r in rows if r.type == kind and start <= r.date < end]


def by_category(rows: list[Row]) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    for r in rows:
        totals[r.category] += r.amount
    return dict(sorted(totals.items(), key=lambda kv: kv[1], reverse=True))


def bar(fraction: float, width: int = 10) -> str:
    filled = min(width, round(fraction * width))
    return "█" * filled + "░" * (width - filled)


def status_dot(spent: float, budget: float) -> str:
    if budget <= 0:
        return "⚪"
    if spent >= budget:
        return "🔴"
    if spent >= 0.8 * budget:
        return "🟠"
    return "🟢"


# ---------------------------------------------------------------- text reports

def period_summary(rows: list[Row], title: str, start: date, end: date,
                   compare: tuple[str, date, date] | None = None) -> str:
    spent_rows = in_range(rows, start, end)
    income = sum(r.amount for r in in_range(rows, start, end, "Income"))
    total = sum(r.amount for r in spent_rows)
    lines = [f"<b>{title}</b>", f"💸 Spent: <b>{eur(total)}</b> ({len(spent_rows)} purchases)"]
    if income:
        lines.append(f"💰 Income: {eur(income)}  ·  Balance: {eur(income - total)}")
    if compare:
        name, cs, ce = compare
        before = sum(r.amount for r in in_range(rows, cs, ce))
        if before:
            change = (total - before) / before * 100
            arrow = "📈" if change > 0 else "📉"
            lines.append(f"{arrow} {change:+.0f}% vs {name} ({eur(before)})")
    cats = by_category(spent_rows)
    if cats:
        lines.append("")
        for cat, amount in cats.items():
            share = amount / total * 100 if total else 0
            lines.append(f"{label(cat)}: {eur(amount)} <i>({share:.0f}%)</i>")
        top = sorted(spent_rows, key=lambda r: r.amount, reverse=True)[:3]
        lines.append("")
        lines.append("🔝 Biggest: " + ", ".join(f"{r.item} {eur(r.amount)}" for r in top))
    return "\n".join(lines)


def today_report(rows: list[Row], today: date) -> str:
    items = in_range(rows, today, today + timedelta(days=1))
    total = sum(r.amount for r in items)
    if not items:
        return "📅 <b>Today</b>\nNothing spent yet today. 👌"
    lines = [f"📅 <b>Today</b> — {eur(total)}"]
    lines += [f"• {r.item} — {eur(r.amount)} <i>({r.category})</i>" for r in items]
    return "\n".join(lines)


def week_report(rows: list[Row], today: date) -> str:
    start = week_start(today)
    return period_summary(rows, f"🗓️ This week (since Mon {start:%d %b})", start,
                          start + timedelta(days=7),
                          ("same days last week", start - timedelta(days=7), today - timedelta(days=6)))


def month_report(rows: list[Row], month: date, today: date) -> str:
    start = month_start(month)
    days_in_month = calendar.monthrange(start.year, start.month)[1]
    end = start + timedelta(days=days_in_month)
    is_current = start == month_start(today)
    pm = prev_month(start)
    # Compare to the same number of days last month when the month is still running.
    cmp_end = pm + timedelta(days=(today - start).days + 1) if is_current else start
    text = period_summary(rows, f"📆 {start:%B %Y}", start, end, ("last month", pm, cmp_end))
    if is_current:
        total = sum(r.amount for r in in_range(rows, start, end))
        daily = total / today.day
        text += (f"\n\n📊 Daily average: {eur(daily)}"
                 f"\n🔮 Projected month total: {eur(daily * days_in_month)}")
    return text


def budget_report(rows: list[Row], budgets: dict[str, float], today: date) -> str:
    start = month_start(today)
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    spent = by_category(in_range(rows, start, today + timedelta(days=1)))
    total_budget = sum(budgets.values())
    total_spent = sum(spent.values())
    days_left = days_in_month - today.day + 1
    lines = [f"🎯 <b>Budget — {today:%B}</b>",
             f"{bar(total_spent / total_budget if total_budget else 0)} "
             f"{eur(total_spent)} / {eur(total_budget)}",
             f"Left: <b>{eur(total_budget - total_spent)}</b> for {days_left} days "
             f"(≈ {eur(max(0, total_budget - total_spent) / days_left)}/day)", ""]
    for cat in CATEGORY_NAMES:
        b, s = budgets.get(cat, 0), spent.get(cat, 0)
        if b <= 0 and s == 0:
            continue
        if b > 0:
            lines.append(f"{status_dot(s, b)} {EMOJI[cat]} {cat}: {eur(s)} / {eur(b)} "
                         f"— {eur(b - s)} left")
        else:
            lines.append(f"⚪ {EMOJI[cat]} {cat}: {eur(s)} (no budget set)")
    return "\n".join(lines)


def budget_alerts(rows: list[Row], budgets: dict[str, float], categories: set[str],
                  added: dict[str, float], today: date) -> list[str]:
    """Warn when this message pushed a category past 80% or 100% of its budget."""
    start = month_start(today)
    spent = by_category(in_range(rows, start, today + timedelta(days=366)))
    alerts = []
    for cat in categories:
        b = budgets.get(cat, 0)
        if b <= 0:
            continue
        after = spent.get(cat, 0)
        before = after - added.get(cat, 0)
        if before < b <= after:
            alerts.append(f"🔴 <b>{label(cat)} is over budget</b>: {eur(after)} / {eur(b)}")
        elif before < 0.8 * b <= after:
            alerts.append(f"🟠 <b>{label(cat)}</b> has used {after / b:.0%} of its budget "
                          f"({eur(b - after)} left this month)")
    return alerts


def insights(rows: list[Row], today: date) -> list[str]:
    """Short tips comparing this month to last month, per category."""
    start = month_start(today)
    pm = prev_month(start)
    days = (today - start).days + 1
    now = by_category(in_range(rows, start, today + timedelta(days=1)))
    before = by_category(in_range(rows, pm, pm + timedelta(days=days)))
    tips = []
    for cat, amount in now.items():
        old = before.get(cat, 0)
        if old >= 5 and amount >= 1.4 * old:
            tips.append(f"💡 {label(cat)} is up {amount / old - 1:.0%} vs the same point last month.")
        elif old >= 10 and amount <= 0.6 * old:
            tips.append(f"👏 {label(cat)} is down {1 - amount / old:.0%} vs last month. Nice!")
    return tips[:3]


# ---------------------------------------------------------------- charts

COLORS = ["#4C6EF5", "#12B886", "#FAB005", "#FA5252", "#7950F2", "#15AABF",
          "#FD7E14", "#82C91E", "#E64980", "#868E96", "#228BE6", "#40C057", "#BE4BDB"]


def category_chart(rows: list[Row], title: str, budgets: dict[str, float] | None = None) -> io.BytesIO | None:
    cats = by_category(rows)
    if not cats:
        return None
    names = list(cats)[::-1]
    values = [cats[n] for n in names]
    fig, ax = plt.subplots(figsize=(7, 0.55 * len(names) + 1.4), dpi=130)
    color_of = {c: COLORS[i % len(COLORS)] for i, c in enumerate(CATEGORY_NAMES)}
    ax.barh(names, values, color=[color_of.get(n, "#868E96") for n in names])
    if budgets:
        for i, n in enumerate(names):
            if budgets.get(n, 0) > 0:
                ax.plot([budgets[n]] * 2, [i - 0.4, i + 0.4], color="#212529", lw=2)
    for i, v in enumerate(values):
        ax.text(v, i, f"  €{v:.2f}", va="center", fontsize=9)
    ax.set_title(title, fontsize=12, weight="bold", loc="left")
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_xlabel("€" + ("   (black line = monthly budget)" if budgets else ""))
    ax.set_xlim(0, max(values + [budgets.get(n, 0) for n in names] if budgets else values) * 1.25)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return buf


def weekly_trend_chart(rows: list[Row], today: date, weeks: int = 8) -> io.BytesIO | None:
    start = week_start(today) - timedelta(weeks=weeks - 1)
    labels, totals = [], []
    for i in range(weeks):
        ws = start + timedelta(weeks=i)
        labels.append(ws.strftime("%d %b"))
        totals.append(sum(r.amount for r in in_range(rows, ws, ws + timedelta(days=7))))
    if not any(totals):
        return None
    fig, ax = plt.subplots(figsize=(7, 3.2), dpi=130)
    ax.bar(labels, totals, color=["#ADB5BD"] * (weeks - 1) + ["#4C6EF5"])
    avg = sum(totals[:-1]) / max(1, weeks - 1)
    ax.axhline(avg, color="#FA5252", ls="--", lw=1, label=f"Average €{avg:.0f}")
    ax.set_title("Spending per week", fontsize=12, weight="bold", loc="left")
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False)
    ax.tick_params(axis="x", labelsize=8)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return buf
