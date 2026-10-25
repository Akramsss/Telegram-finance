"""The bot's personality: reactions, roasts, streaks."""

from __future__ import annotations

import random
from datetime import date, timedelta

QUIPS = {
    "Groceries": ["Fridge restocked 🧊", "Chef mode: ON 👨‍🍳", "Home cooking = smart money 💪",
                  "Supplies secured 🛒"],
    "Eating Out": ["Bon appétit! 😋", "Cooking can wait 😄", "Treat yourself (a little) 🍽️",
                   "Delicious decisions 🤤"],
    "Housing": ["Roof over your head ✅", "Adulting level: expert 🏠", "Home sweet home 🔑"],
    "Transport": ["Vroom vroom 🚌", "Places to go! 🗺️", "On the move 🚀"],
    "Studies": ["Investing in your brain 🧠", "Future you says thanks 🎓", "Knowledge unlocked 📚"],
    "Phone & Subscriptions": ["Stay connected 📶", "Subscriptions add up, keep an eye 👀",
                              "Binge responsibly 📺"],
    "Health & Care": ["Health is wealth 💚", "Self-care ✨", "Glow-up in progress 💅"],
    "Household": ["Sparkling clean ✨", "Home looking fresh 🧽", "Domestic legend 🏆"],
    "Clothing": ["Looking sharp 😎", "Fit check ✅", "Drip acquired 💧"],
    "Leisure": ["Life is for living 🎉", "Fun budget doing its job 🥳", "Good times 🕺"],
    "Travel": ["Bon voyage ✈️", "Adventure awaits 🌍", "Passport ready 🧳"],
    "Admin & Fees": ["Paperwork paid. Ugh. 📄", "Bureaucracy defeated 🛡️", "Adulting tax paid 🫠"],
    "Other": ["Noted! 📝", "Got it 👍", "Filed away 🗂️"],
}

SUB_QUIPS = {
    "Bread & Grains": ["Carbs secured 🥖"],
    "Snacks & Sweets": ["Snack attack! 🍫", "A little treat never hurt 🍪"],
    "Fast Food": ["Fast food, fast money 🍔", "Kebab o'clock? 🌯"],
    "CROUS / University": ["Best value meal in France 🎓"],
    "Café & Bakery": ["Caffeine is a need, not a want ☕", "Croissant-powered 🥐"],
    "Delivery": ["Delivery fees are sneaky 👀", "Couch mode activated 🛋️"],
    "Rent": ["Biggest bill of the month: done ✅"],
    "Sport & Gym": ["Gains incoming 💪"],
    "Gifts": ["Generous soul 🎁"],
    "Fruits & Vegetables": ["Your body says thank you 🥦", "Vitamins loaded 🍎"],
}

INCOME_QUIPS = ["Money in! 🤑", "Ka-ching! 💰", "Payday vibes 🕺", "Wallet: refilled 💸"]

OVER_BUDGET = ["Your wallet is crying a little 🥲", "Budget? What budget? 😅",
               "Slow down, big spender 🐢", "Houston, we have a budget problem 🚀"]
NEAR_BUDGET = ["Careful, getting close 👀", "Easy does it 🤏", "Yellow light ahead 🟡"]

STREAK_MILESTONES = {
    3: "3 days in a row! Habit forming 🌱",
    7: "One full week of tracking! 🏅",
    14: "Two weeks straight. Budget pro 💼",
    30: "30-DAY STREAK! Legendary 👑",
    60: "60 days. You're unstoppable 🦾",
    100: "100 DAYS!!! 🎆🎆🎆",
}


# A seed (the transaction ID) keeps the same reaction when a message is re-drawn.
def quip(category: str, sub: str = "", income: bool = False, seed: str = "") -> str:
    rng = random.Random(seed or None)
    if income:
        return rng.choice(INCOME_QUIPS)
    return rng.choice(SUB_QUIPS.get(sub, []) + QUIPS.get(category, QUIPS["Other"]))


def budget_mood(spent: float, budget: float, seed: str = "") -> str:
    rng = random.Random(seed or None)
    if budget <= 0:
        return ""
    if spent >= budget:
        return rng.choice(OVER_BUDGET)
    if spent >= 0.8 * budget:
        return rng.choice(NEAR_BUDGET)
    return ""


def streak(days_with_entries: set[date], today: date) -> int:
    """Consecutive days with at least one entry, ending today."""
    n, d = 0, today
    while d in days_with_entries:
        n += 1
        d -= timedelta(days=1)
    return n


def streak_line(n: int) -> str:
    if n in STREAK_MILESTONES:
        return f"🔥 <b>{STREAK_MILESTONES[n]}</b>"
    if n >= 2:
        return f"🔥 {n}-day streak"
    return ""
