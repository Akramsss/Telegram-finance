# 💸 Money Buddy: a Telegram budget bot for students

**Type what you spend. Tap a category. Done.**
Every expense goes into your own Google Sheet, with a live dashboard, budgets, charts, weekly reports and a bit of fun along the way. 🔥

```
You:   4.50

Bot:   💶 €4.50 — what was it?
       [⚡ 🥖 Bread & Grains] [⚡ 🎓 CROUS / University]
       [🛒 Groceries] [🍽️ Eating out] [🚌 Transport] ...

You:   *taps 🛒 Groceries → 🥖 Bread & Grains*

Bot:   ✅ €4.50 → 🥖 Bread & Grains
       Carbs secured 🥖

       🛒 Groceries in October
       ██░░░░░░░░ €23.40 / €100.00
       🔥 5-day streak

       [✏️ Name it] [📅 Yesterday] [💵 Cash]
       [🏷️ Change] [↩️ Undo]
```

---

## ✨ Features

**Logging that takes 2 seconds**
- **Amount + 2 taps:** type `4.50`, pick a category, then the exact thing.
- **⚡ Quick picks:** your most used subcategories appear first, so common purchases take 1 tap.
- **Lazy mode:** type `kebab 8 cash` or `milk 0.95, eggs 2.49 @Lidl` and it's saved with a smart guess, in English or French.
- **Income:** `+250` shows CAF / APL, scholarship, family, job…
- **One-tap fixes:** ✏️ name it · 📅 move to yesterday · 💵 cash or card · 🏷️ change category · ↩️ undo.

**A budget that sets itself up**
- On the first `/start`, the bot asks for your **monthly budget** and how to split it: 🤖 automatically or ✍️ category by category.
- Live budget bars after every entry, alerts at 80% and 100%, and a ✏️ button to change it any time.

**Stats without opening anything**
- A menu under the chat: 📅 Today · 🗓️ Week · 📆 Month · 🎯 Budget · 🧾 Last · ↩️ Undo
- Chart images in Telegram, comparisons with last week and last month, a daily average and a month-end projection.
- 📬 An automatic **weekly report** (Sunday 20:00), a **monthly report** (on the 1st) and an evening reminder if you logged nothing.

**A Google Sheet that builds itself**
- **Dashboard:** spent / left / daily average / projection, a progress bar per category, top items and stores, and 3 charts.
- **Transactions**, **Budgets**, **Weekly** (12 weeks) and **Monthly** (12 months) tabs, all formula-driven.

**Made for students in France 🇫🇷**
- 13 expense categories and 60 subcategories: CROUS, Navigo, CAF / APL, halal butcher, titre de séjour, mutuelle…
- Euros, the Paris time zone, and English or French input.

**Personality 🎉**
- Reactions for every subcategory ("Fridge restocked 🧊", "Kebab o'clock? 🌯").
- Gentle roasts when you overspend ("Your wallet is crying a little 🥲").
- 🔥 Logging streaks with milestones at 3, 7, 14, 30 and 100 days.

**Multi-user and private**
- Each person has **their own sheet, budget, streak and reports**. Nobody sees anyone else's data.
- Strangers can only tap **🙋 Request access**. The admin approves or declines with a button.

---

## 🚀 Quick start

> Every step explained click by click: **[SETUP.md](SETUP.md)**

You need: a Mac (or any computer with Python 3.11+), a Telegram account and a Google account.

```bash
# 1. Install
cd ~/Desktop/Telegram-finance
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 2. Configure (fill in the values; see the table below)
cp .env.example .env
open -e .env
#    + put your Google robot key in this folder as service_account.json

# 3. Build your Google Sheet (tabs, formulas, charts)
.venv/bin/python setup_sheet.py

# 4. Run the bot
.venv/bin/python bot.py
```

Then open your bot in Telegram and send `/start`.

---

## ⚙️ Configuration (`.env`)

| Setting | Required | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | ✅ | From @BotFather |
| `ALLOWED_USER_IDS` | ✅ | Telegram IDs separated by commas. **The first one is the admin.** Leave it empty at first; `/start` tells you your ID. |
| `SPREADSHEET_ID` | ✅ | The admin's sheet: a full link or just the ID |
| `GOOGLE_CREDENTIALS_FILE` | | Robot key file (default `service_account.json`) |
| `ANTHROPIC_API_KEY` | | Optional. Lets Claude understand any free-form message. |
| `CLAUDE_MODEL` | | Default `claude-opus-5-5`. Use `claude-haiku-5-5` for about 1/40 of the cost. |
| `TIMEZONE` | | Default `Europe/Paris` |
| `DEFAULT_PAYMENT` | | `Card` or `Cash` (default `Card`) |
| `WEEKLY_REPORT` · `MONTHLY_REPORT` · `DAILY_REMINDER` | | `true` or `false` (default `true`) |
| `DAILY_REMINDER_TIME` | | Default `21:30` |

---

## 💬 Commands

The bot publishes these in Telegram's **Menu** button automatically.

| Command | What it does |
|---|---|
| `/start` | Welcome, connect your sheet, or set up your budget |
| `/today` · `/week` · `/month` | Spending summaries, with charts (`/month 2026-09` for a past month) |
| `/budget` | What's left per category, with a ✏️ button to change it |
| `/last` | Your last 10 entries |
| `/undo` | Remove your last entry |
| `/setup` | Set or change your monthly budget |
| `/categories` | All categories and subcategories |
| `/report` | Your weekly report right now |
| `/sheet` | Link to your Google Sheet |
| `/help` | How to use the bot |
| `/users` 👑 | *Admin only:* users, linked sheets and pending requests |
| `/remove ID` 👑 | *Admin only:* remove someone's access (their sheet is kept) |

**What you can type:**

| You type | Result |
|---|---|
| `4.50` | Category buttons |
| `+250` | Income buttons |
| `kebab 8 cash` | Saved with a guessed category |
| `milk 0.95, eggs 2.49 @Lidl` | Several items, with the store |
| `yesterday CROUS 3.30` · `j'ai payé 12€ pour un tacos hier` | Dated entries, English or French |

---

## 👥 Adding friends

1. They open your bot and press **Start**, then tap **🙋 Request access**.
2. You get **✅ Approve / ❌ Decline** in Telegram.
3. They create an empty sheet, **share it as Editor** with the robot email the bot shows them, and paste the link.
4. The bot builds their dashboard (about 20 seconds) and runs their budget setup. 🎉

---

## 🗂️ Project structure

```
Telegram-finance/
├── bot.py            # Telegram handlers: tap flow, commands, buttons, scheduled reports
├── users.py          # Access requests, admin approval, linking each user's sheet
├── onboarding.py     # Budget setup conversation (/setup)
├── parser.py         # Free text → transactions (built-in rules, or Claude if a key is set)
├── categories.py     # Categories, subcategories, emojis, keywords (EN/FR), default budgets
├── sheets.py         # Google Sheets read/write, per user
├── setup_sheet.py    # Builds a sheet: tabs, formulas, formatting, charts
├── stats.py          # Summaries, budget alerts, insights, chart images
├── fun.py            # Reactions, roasts, streaks
├── config.py         # Settings from .env
├── SETUP.md          # Step-by-step setup guide
├── requirements.txt
├── .env.example      # Settings template (copy to .env)
│
├── .env                  # 🔒 your secrets (never share)
├── service_account.json  # 🔒 Google robot key (never share)
└── bot_state.pickle      # users, linked sheets, setup progress (created by the bot)
```

### How it works

```
 Telegram ──► bot.py ──► users.py (allowed? which sheet?)
                │
                ├─ "4.50" ───────► buttons ──► sheets.py ──► that user's Google Sheet
                ├─ "kebab 8" ────► parser.py (rules / Claude) ──┘
                ├─ /week, /budget ► stats.py ──► text + chart image
                └─ scheduler ────► weekly / monthly / reminder, for every user
```

- The **Transactions** tab is the single source of truth. Every other tab is built from formulas on it.
- The **Budgets** tab holds the amounts, and both the bot and the Dashboard read it. You can edit it from Telegram or in the sheet.
- One **Google service account** (the "robot") writes to every user's sheet. Users share their sheet with its email.

---

## 🔒 Security

- **Only approved people** can use the bot. Every message and button tap is checked against their Telegram ID, which can't be faked.
- **There's no server to attack.** The bot only makes outgoing connections to Telegram and Google, and opens no ports.
- **Text is saved as text.** Formula injection like `=IMPORTXML(...)` is neutralised.
- **The only secrets are `.env` and `service_account.json`.** Never share or upload them; `.gitignore` already excludes them.
  The robot key can edit **every user's** sheet, so protect it carefully.
- **The robot email is not secret.** It's safe to show to users.
- **If a secret leaks:** in @BotFather, use `/revoke` for a new token. In Google Cloud, go to Service accounts → Keys, delete the key and create a new one. Users don't need to redo anything.
- **Admin privacy:** the bot never reveals who the admin is, and admin commands are invisible to other users.

---

## 🛠️ Troubleshooting

| Problem | Fix |
|---|---|
| `APIError … Page introuvable / Page not found` | `SPREADSHEET_ID` is wrong. Paste the full sheet link; the bot extracts the ID. |
| `Timed out` at startup | A temporary network problem. The bot now keeps retrying on its own. |
| `invalid literal for int()` | Use `ALLOWED_USER_IDS=111, 222` (numbers separated by commas). |
| "I can't open that sheet yet" | The sheet isn't shared with the robot email as **Editor**. |
| The bot doesn't answer | Is `bot.py` still running in Terminal? Is the Mac awake? (`caffeinate -i .venv/bin/python bot.py`) |
| `Conflict: terminated by other getUpdates` | The bot is running twice. Close the other Terminal window. |
| The menu commands don't show | Restart the bot, then close and reopen the chat in Telegram. |
| The Dashboard shows the wrong month | Cell C3 holds the month. Type `=TEXT(TODAY(),"yyyy-mm")` to follow the current month. |

Rebuilding a sheet is always safe. It keeps Transactions and Budgets:
```bash
.venv/bin/python setup_sheet.py                 # your sheet
.venv/bin/python setup_sheet.py <sheet link>    # any other sheet shared with the robot
```

---

## 💰 Costs

| | Cost |
|---|---|
| Telegram bot, Google Sheets, Google Cloud service account | **Free** |
| Running on your Mac | **Free** (the Mac must stay on) |
| Optional: Claude free-form parsing | About €0.10 per user per month with `claude-haiku-5-5` |
| Optional: an always-on server | Free to about €5 per month |

---

## 🗺️ Ideas for later

- ☁️ Host it 24/7 on a small server, so it works when the Mac is off
- 📸 Scan receipt photos
- 🎤 Voice messages ("I spent 3 euros on bread")
- 🔁 Recurring expenses (phone plan, subscriptions) added automatically
- 🎯 Savings goals with progress bars
- 👫 Shared budgets for roommates

---

<sub>Built with Python, [python-telegram-bot](https://python-telegram-bot.org), [gspread](https://docs.gspread.org) and matplotlib. Optional AI parsing by [Claude](https://www.anthropic.com).</sub>
