# Setup guide

There are two parts:

- **Part A — for you (the owner/admin):** set the bot up once on your Mac (about 15 minutes).
- **Part B — for other people:** how a friend joins your bot (about 2 minutes, no technical steps).

> 🔒 **Never paste your tokens or keys in any chat** (including with Claude).
> They only go in `.env` and `service_account.json` on your Mac.

---

# Part A — Owner setup (once)

## A1 — Telegram bot token (2 min)

1. In Telegram, search for **@BotFather** (blue check mark) and open it.
2. Send `/newbot`.
3. Give it a name, e.g. `My Budget`.
4. Give it a username that ends in `bot`, e.g. `akram_budget_bot`.
5. BotFather replies with a token like `123456789:AAH...`. **Copy it** for step A4.

You don't need to set up commands in BotFather: the bot publishes its own menu when it starts.

## A2 — Google service account (8 min)

This is a free "robot account" that the bot uses to write to sheets. One robot works for every user.

1. Go to <https://console.cloud.google.com> and sign in with your Google account.
2. At the top, click the project picker → **New project** → name it `telegram-finance` → **Create**. Make sure it's selected.
3. In the search bar, type **Google Sheets API** → open it → **Enable**.
   Do the same for **Google Drive API**.
4. In the search bar, type **Service accounts** → open it → **+ Create service account**.
   - Name: `budget-bot` → **Create and continue**
   - Skip the roles (click **Continue**, then **Done**).
5. Click the new service account → **Keys** tab → **Add key** → **Create new key** → **JSON** → **Create**.
6. Rename the downloaded file to **`service_account.json`** and move it into `Desktop/Telegram-finance/`.
7. Copy the service account's **email** (`budget-bot@...iam.gserviceaccount.com`) for step A3.

## A3 — Your Google Sheet (2 min)

1. Go to <https://sheets.new> to create an empty sheet, e.g. **My Student Budget**.
2. Click **Share** → paste the robot email → **Editor** → untick "Notify people" → **Share**.
3. Make sure **General access** says **Restricted**, not "Anyone with the link".
4. Copy the link from the address bar for step A4.

## A4 — Fill in `.env`

```bash
cd ~/Desktop/Telegram-finance && cp .env.example .env && open -e .env
```

Fill in:

| Setting | What to put |
|---|---|
| `TELEGRAM_BOT_TOKEN` | the token from A1 |
| `SPREADSHEET_ID` | the sheet link from A3 (the full link works) |
| `ALLOWED_USER_IDS` | **your** Telegram ID first. Add more IDs after a comma if you like: `8525690518, 5016470578`. Leave it empty the first time; the bot will tell you your ID. |
| `ANTHROPIC_API_KEY` | optional, see below |

Save and close.

**The first ID is the admin** (you). The admin approves new users, sees `/users` and `/remove`, and `SPREADSHEET_ID` is the admin's sheet.

## A5 — Build your sheet and start the bot

Build your sheet (tabs, formulas, charts):

```bash
cd ~/Desktop/Telegram-finance && .venv/bin/python setup_sheet.py
```

Start the bot:

```bash
cd ~/Desktop/Telegram-finance && .venv/bin/python bot.py
```

1. In Telegram, open your bot and send `/start`.
   - If `ALLOWED_USER_IDS` is empty, the bot replies with your ID. Put it in `.env`, then restart the bot (**Ctrl + C**, then run it again).
2. Send `/start` again. The bot walks you through **your monthly budget** (pick a total, then let it split it or choose yourself).
3. Type `4.50`, tap a category, and see it land in your sheet 🎉

> The bot only works while this Terminal window is open and your Mac is awake.
> To stop the Mac from sleeping while it runs: `caffeinate -i .venv/bin/python bot.py`

### Optional: Claude AI for free-form messages

Without a key, the bot understands `4.50` + buttons, and messages like `kebab 8 cash` or `milk 0.95, eggs 2.49 @Lidl`.
With a key from <https://console.anthropic.com>, it understands any phrasing.
Put `ANTHROPIC_API_KEY=...` and `CLAUDE_MODEL=claude-haiku-5-5` in `.env`. That's about €0.10 a month per person.
You pay for every user's messages.

---

# Part B — Adding other people

Each person gets **their own Google Sheet, budget, streak and reports**. Nobody sees anyone else's spending.

### How a friend joins

1. They open your bot in Telegram (send them its link, e.g. `t.me/akram_budget_bot`) and press **Start**.
2. They see 🔒 *This bot is private* and tap **🙋 Request access**.
3. **You** get a message with **✅ Approve / ❌ Decline**. Tap Approve.
   (Or, if you put their ID in `ALLOWED_USER_IDS` beforehand, they're already in.)
4. The bot asks them to connect their own sheet:
   - create an empty sheet at <https://sheets.new>
   - **Share** it as **Editor** with the robot email (the bot shows it; tap to copy)
   - paste the sheet link in the chat
5. The bot builds their dashboard and charts (about 20 seconds), then runs their budget setup. Done!

### Admin commands (only you see them)

| Command | What it does |
|---|---|
| `/users` | Everyone who has access, whether they've linked a sheet, and pending requests |
| `/remove 123456789` | Removes someone's access. Their Google Sheet is not touched. |

---

# All commands

The bot shows these automatically in Telegram's **Menu** button.
Most people only need the buttons at the bottom of the chat (📅 Today · 🗓️ Week · 📆 Month · 🎯 Budget · 🧾 Last · ↩️ Undo).

| Command | What it does |
|---|---|
| `/start` | Welcome, connect your sheet, or set up your budget the first time |
| `/today` | What you spent today |
| `/week` | This week by category, with a chart |
| `/month` | This month, with a chart (`/month 2026-09` for a past month) |
| `/budget` | What's left in each budget, with a ✏️ button to change it |
| `/last` | Your last 10 entries |
| `/undo` | Remove your last entry |
| `/setup` | Set or change your monthly budget |
| `/categories` | All categories and subcategories |
| `/report` | Your weekly report right now |
| `/sheet` | Link to your Google Sheet |
| `/help` | How to use the bot |

**Typing (no command needed):**

| You type | What happens |
|---|---|
| `4.50` | Buttons to pick a category, then the exact thing |
| `+250` | Money coming in: CAF, scholarship, family, job… |
| `kebab 8 cash` | Saved right away with a guessed category (🏷️ to change it) |
| `milk 0.95, eggs 2.49 @Lidl` | Several items at once, with the store |
| `yesterday CROUS 3.30` | Saved on yesterday's date |

---

# Your sheet

| Tab | What it is |
|---|---|
| **Dashboard** | This month at a glance: spent, left, daily average, projection, progress bars, top items and stores, charts |
| **Transactions** | One row per entry, written by the bot. You can edit or delete rows by hand. |
| **Budgets** | Your monthly budget per category. Change it with `/setup` in Telegram or in column C. |
| **Weekly** | The last 12 weeks by category |
| **Monthly** | The last 12 months: spent, income, saved |

To look at a past month on the Dashboard, type it in cell **C3** (e.g. `2026-09`).
To go back to the current month, type `=TEXT(TODAY(),"yyyy-mm")` in C3.

---

# Security in one minute

- `.env` (bot token) and `service_account.json` (robot key) are the only secrets. Never share or upload them.
- The robot's email is **not** secret. It's safe to show to users.
- If a secret ever leaks: get a new token in @BotFather with `/revoke`, and in Google Cloud go to Service accounts → Keys, delete the key and create a new one.
- Keep your sheets' General access set to **Restricted**.
