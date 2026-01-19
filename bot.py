import os
import re
import json
import asyncio
import requests
from datetime import datetime, date, time
from zoneinfo import ZoneInfo

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from pymongo import MongoClient

# ================= CONFIG =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

API_URL = "https://mynkapi.amit1100941.workers.dev/api"
API_KEY = os.getenv("API_KEY")

IST = ZoneInfo("Asia/Kolkata")

# ================= DB =================
mongo = MongoClient(MONGO_URI)
db = mongo["ghost_eye"]
users = db["users"]
protected = db["protected"]

# ================= BROADCAST STATE =================
broadcast_state = {
    "running": False,
    "cancelled": False,
    "sent": 0,
    "failed": 0,
    "total": 0,
}

# ================= HELPERS =================
def is_admin(uid: int) -> bool:
    return uid == ADMIN_ID

def is_valid_number(text: str) -> bool:
    return bool(re.fullmatch(r"[6-9]\d{9}", text))

def progress_bar(done, total, size=20):
    filled = int(size * done / total) if total else 0
    return "█" * filled + "░" * (size - filled)

# ================= HACKER INTRO =================
async def hacker_intro(update: Update):
    await update.message.reply_text(
        "🔐 Ghost Eye OSINT Initialized\n"
        "🧠 Modules Loaded\n"
        "🗄️ Database Synced\n"
        "🚀 System Online"
    )

# ================= DAILY CREDIT JOB =================
async def daily_credit_job(context: ContextTypes.DEFAULT_TYPE):
    today = date.today().isoformat()
    for user in users.find():
        if user.get("last_daily") == today:
            continue

        users.update_one(
            {"_id": user["_id"]},
            {"$inc": {"credits": 1}, "$set": {"last_daily": today}}
        )

        try:
            await context.bot.send_message(
                user["_id"],
                "🎁 You received 1 free daily credit\n\nType /start to claim"
            )
        except:
            pass

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    if not users.find_one({"_id": uid}):
        users.insert_one({
            "_id": uid,
            "credits": 0,
            "unlimited": False,
            "created_at": datetime.utcnow()
        })

    await hacker_intro(update)

    user = users.find_one({"_id": uid})
    credits = "Unlimited" if user.get("unlimited") else user.get("credits", 0)

    await update.message.reply_text(
        "🌐 Welcome to Ghost Eye OSINT 🌐\n\n"
        f"👤 UserID: {uid}\n"
        f"💳 Credits: {credits}\n\n"
        "💡 Send number to fetch details\n\n"
        "Example:\n92865xxxxx"
    )

# ================= SEARCH =================
async def search_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if broadcast_state["running"]:
        return

    text = update.message.text.strip()
    uid = update.effective_user.id

    if not text.isdigit():
        return

    if not is_valid_number(text):
        await update.message.reply_text(
            "❌ Invalid Format\n\nExample:\n92865xxxxx"
        )
        return

    if protected.find_one({"number": text}):
        await update.message.reply_text("❌ This number is protected")
        return

    user = users.find_one({"_id": uid})
    if not user:
        return

    if not user.get("unlimited") and user.get("credits", 0) <= 0:
        await update.message.reply_text("❌ No credits left")
        return

    try:
        r = requests.get(API_URL, params={
            "key": API_KEY,
            "type": "mobile",
            "term": text
        }, timeout=15)
        data = r.json()
    except:
        await update.message.reply_text("❌ API error")
        return

    result = data.get("result", [])
    if not result:
        await update.message.reply_text("⚠️ No data found\n💳 Credit not deducted")
        return

    if not user.get("unlimited"):
        users.update_one({"_id": uid}, {"$inc": {"credits": -1}})

    await update.message.reply_text(
        f"```json\n{json.dumps(result, indent=4, ensure_ascii=False)}\n```",
        parse_mode="Markdown"
    )

# ================= BROADCAST =================
async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    if broadcast_state["running"]:
        await update.message.reply_text("⚠️ Broadcast already running")
        return

    broadcast_state.update({
        "running": True,
        "cancelled": False,
        "sent": 0,
        "failed": 0,
        "total": users.count_documents({}),
    })

    await update.message.reply_text(
        "📢 Broadcast Mode Enabled\n\nSend message or photo to broadcast.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✖️ Cancel Broadcast", callback_data="cancel_broadcast")]
        ])
    )

async def broadcast_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not broadcast_state["running"]:
        return
    if update.message.text and update.message.text.startswith("/"):
        return

    text = update.message.caption or update.message.text
    photo = update.message.photo[-1].file_id if update.message.photo else None

    progress = await update.message.reply_text("📢 Broadcasting…")

    for u in users.find():
        if not broadcast_state["running"] or broadcast_state["cancelled"]:
            break

        try:
            if photo:
                await context.bot.send_photo(u["_id"], photo=photo, caption=text)
            else:
                await context.bot.send_message(u["_id"], text)
            broadcast_state["sent"] += 1
        except:
            broadcast_state["failed"] += 1

        bar = progress_bar(broadcast_state["sent"], broadcast_state["total"])
        percent = int((broadcast_state["sent"] / broadcast_state["total"]) * 100)

        try:
            await progress.edit_text(
                f"📢 Broadcasting…\n\n"
                f"{bar} {percent}%\n"
                f"Sent: {broadcast_state['sent']} / {broadcast_state['total']}\n"
                f"Failed: {broadcast_state['failed']}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✖️ Cancel Broadcast", callback_data="cancel_broadcast")]
                ])
            )
        except:
            pass

        await asyncio.sleep(0.05)

    broadcast_state["running"] = False

    if broadcast_state["cancelled"]:
        await progress.edit_text("✖️ Broadcast cancelled")
    else:
        await progress.edit_text(
            f"✅ Broadcast finished\n\n"
            f"Sent: {broadcast_state['sent']}\n"
            f"Failed: {broadcast_state['failed']}"
        )

async def cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("Cancelling…")
    broadcast_state["cancelled"] = True
    broadcast_state["running"] = False

# ================= ADMIN =================
async def add_credit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update.effective_user.id):
        uid, amt = map(int, context.args)
        users.update_one({"_id": uid}, {"$inc": {"credits": amt}}, upsert=True)
        await update.message.reply_text("✅ Credits added")

async def remove_credit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update.effective_user.id):
        uid, amt = map(int, context.args)
        users.update_one({"_id": uid}, {"$inc": {"credits": -amt}})
        await update.message.reply_text("✅ Credits removed")

async def unlimited(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update.effective_user.id):
        uid = int(context.args[0])
        mode = context.args[1].lower() == "on"
        users.update_one({"_id": uid}, {"$set": {"unlimited": mode}})
        await update.message.reply_text("✅ Unlimited updated")

async def protect_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update.effective_user.id):
        protected.insert_one({"number": context.args[0]})
        await update.message.reply_text("✅ Number protected")

async def unprotect_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update.effective_user.id):
        protected.delete_one({"number": context.args[0]})
        await update.message.reply_text("✅ Number unprotected")

# ================= MAIN =================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("broadcast", broadcast_start))
    app.add_handler(CommandHandler("add", add_credit))
    app.add_handler(CommandHandler("remove", remove_credit))
    app.add_handler(CommandHandler("unlimited", unlimited))
    app.add_handler(CommandHandler("protect", protect_number))
    app.add_handler(CommandHandler("unprotect", unprotect_number))
    app.add_handler(CallbackQueryHandler(cancel_broadcast, pattern="cancel_broadcast"))

    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, broadcast_content))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_handler))

    app.job_queue.run_daily(
        daily_credit_job,
        time=time(9, 0, tzinfo=IST)
    )

    app.run_polling()

if __name__ == "__main__":
    main()
