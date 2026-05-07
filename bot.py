import logging
import asyncio
import gspread
from datetime import datetime
from google.oauth2.service_account import Credentials
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
 
# ─── CONFIG ────────────────────────────────────────────────────────────────
TOKEN = "8605176090:AAFYbY-rgBeUWogs64-gxUpKGJD5sM3sFR4"          # BotFather token
SHEET_ID = "117fSdv3qujSEDU7b3vaMAagO50ozANTdH7PNUH-MYos"    # From the Google Sheet URL
CREDS_FILE = "credentials.json"       # Downloaded from Google Cloud
 
# ─── LOGGING ───────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
 
# ─── GOOGLE SHEETS SETUP ───────────────────────────────────────────────────
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
 
def get_sheet():
    creds = Credentials.from_service_account_file(CREDS_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(SHEET_ID).sheet1
    if sheet.row_count == 0 or sheet.cell(1, 1).value != "chat_id":
        sheet.clear()
        sheet.append_row(["chat_id", "time", "task", "added_on"])
    return sheet
 
# ─── SHEETS HELPERS ────────────────────────────────────────────────────────
def load_tasks(chat_id):
    sheet = get_sheet()
    all_rows = sheet.get_all_records()
    tasks = [
        {"time": r["time"], "task": r["task"], "row": i + 2}
        for i, r in enumerate(all_rows)
        if str(r["chat_id"]) == str(chat_id)
    ]
    return sorted(tasks, key=lambda x: x["time"])
 
def save_task(chat_id, time, task):
    sheet = get_sheet()
    sheet.append_row([
        str(chat_id), time, task,
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ])
 
def delete_task_by_index(chat_id, index):
    tasks = load_tasks(chat_id)
    if index < 0 or index >= len(tasks):
        return False, None
    row_number = tasks[index]["row"]
    removed = tasks[index]
    sheet = get_sheet()
    sheet.delete_rows(row_number)
    return True, removed
 
def clear_all_tasks(chat_id):
    sheet = get_sheet()
    all_rows = sheet.get_all_records()
    rows_to_delete = [
        i + 2 for i, r in enumerate(all_rows)
        if str(r["chat_id"]) == str(chat_id)
    ]
    for row_num in reversed(rows_to_delete):
        sheet.delete_rows(row_num)
 
def format_schedule(chat_id):
    tasks = load_tasks(chat_id)
    if not tasks:
        return "📭 Your schedule is empty. Use /add to add tasks."
    lines = "\n".join(
        f"{i+1}. 🕐 `{t['time']}` — {t['task']}"
        for i, t in enumerate(tasks)
    )
    return f"📅 *Your Schedule:*\n\n{lines}"
 
# ─── CONVERSATION STATES ───────────────────────────────────────────────────
AWAIT_TIME, AWAIT_TASK, AWAIT_DELETE = range(3)
 
# ─── COMMANDS ──────────────────────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name
    await update.message.reply_text(
        f"👋 Hello *{name}*! I'm your *Schedule Bot* 🗓️\n\n"
        "Your tasks are saved in *Google Sheets* — safe forever!\n\n"
        "*Commands:*\n"
        "📋 /schedule — View your schedule\n"
        "➕ /add — Add a new task\n"
        "❌ /delete — Delete a task\n"
        "🗑 /clear — Clear entire schedule\n"
        "❓ /help — Help",
        parse_mode="Markdown"
    )
 
async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "*Schedule Bot Help* 🤖\n\n"
        "📋 /schedule — View all tasks\n"
        "➕ /add — Add a task\n"
        "❌ /delete — Remove a task\n"
        "🗑 /clear — Delete all tasks\n\n"
        "All data is stored in *Google Sheets* 📊\n"
        "Reminders fire every hour automatically! ⏰",
        parse_mode="Markdown"
    )
 
async def show_schedule(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Loading your schedule...")
    await update.message.reply_text(
        format_schedule(update.effective_chat.id),
        parse_mode="Markdown"
    )
 
async def clear(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Clearing your schedule...")
    clear_all_tasks(update.effective_chat.id)
    await update.message.reply_text("🗑 Your schedule has been cleared!")
 
# ─── ADD TASK ──────────────────────────────────────────────────────────────
async def add_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "➕ *Add a new task*\n\n"
        "Enter the time for this task:\n"
        "Format: `HH:MM` (e.g., `09:00`, `14:30`)",
        parse_mode="Markdown"
    )
    return AWAIT_TIME
 
async def add_time(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        datetime.strptime(text, "%H:%M")
    except ValueError:
        await update.message.reply_text(
            "⚠️ Invalid format. Please use HH:MM (e.g., `09:00`):",
            parse_mode="Markdown"
        )
        return AWAIT_TIME
    ctx.user_data["time"] = text
    await update.message.reply_text(
        f"✅ Time set to *{text}*\n\nNow enter the task description:",
        parse_mode="Markdown"
    )
    return AWAIT_TASK
 
async def add_task(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    task = update.message.text.strip()
    time = ctx.user_data["time"]
    await update.message.reply_text("⏳ Saving to Google Sheets...")
    save_task(chat_id, time, task)
    await update.message.reply_text(
        f"✅ Task saved!\n\n🕐 *{time}* — {task}\n\nUse /schedule to view all tasks.",
        parse_mode="Markdown"
    )
    return ConversationHandler.END
 
# ─── DELETE TASK ───────────────────────────────────────────────────────────
async def delete_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text("⏳ Loading tasks...")
    tasks = load_tasks(chat_id)
    if not tasks:
        await update.message.reply_text("📭 No tasks to delete.")
        return ConversationHandler.END
    await update.message.reply_text(
        format_schedule(chat_id) + "\n\nEnter the *number* of the task to delete:",
        parse_mode="Markdown"
    )
    return AWAIT_DELETE
 
async def delete_task(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    try:
        num = int(update.message.text.strip())
        await update.message.reply_text("⏳ Deleting...")
        success, removed = delete_task_by_index(chat_id, num - 1)
        if success:
            await update.message.reply_text(
                f"✅ Deleted: 🕐 *{removed['time']}* — {removed['task']}",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("⚠️ Invalid number. Try /delete again.")
    except ValueError:
        await update.message.reply_text("⚠️ Please enter a valid number.")
    return ConversationHandler.END
 
async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END
 
# ─── HOURLY REMINDER ───────────────────────────────────────────────────────
async def hourly_reminder(app):
    now = datetime.now()
    current_hour = now.strftime("%H")
    time_label = now.strftime("%H:00")
    sheet = get_sheet()
    all_rows = sheet.get_all_records()
    chat_ids = set(str(r["chat_id"]) for r in all_rows)
    for chat_id in chat_ids:
        tasks = load_tasks(chat_id)
        due = [t for t in tasks if t["time"].startswith(current_hour + ":")]
        if not due:
            continue
        task_lines = "\n".join(f"• 🕐 `{t['time']}` — {t['task']}" for t in due)
        try:
            await app.bot.send_message(
                chat_id=int(chat_id),
                text=(
                    f"⏰ *Schedule Reminder* — {time_label}\n\n"
                    f"You have the following task(s) this hour:\n\n"
                    f"{task_lines}\n\nStay on track! 💪"
                ),
                parse_mode="Markdown"
            )
        except Exception as e:
            logging.error(f"Reminder failed for {chat_id}: {e}")
 
# ─── MAIN ──────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(TOKEN).build()
 
    add_conv = ConversationHandler(
        entry_points=[CommandHandler("add", add_start)],
        states={
            AWAIT_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_time)],
            AWAIT_TASK: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_task)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    delete_conv = ConversationHandler(
        entry_points=[CommandHandler("delete", delete_start)],
        states={
            AWAIT_DELETE: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_task)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
 
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("schedule", show_schedule))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(add_conv)
    app.add_handler(delete_conv)
 
    scheduler = AsyncIOScheduler()
    scheduler.add_job(hourly_reminder, trigger="cron", minute=0, args=[app])
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
 
    scheduler.start()
 
    print("🤖 Schedule Bot running with Google Sheets storage!")
    app.run_polling()
 
if __name__ == "__main__":
    main()