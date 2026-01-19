import os
import re
import json
import asyncio
import requests
from datetime import datetime, date, time

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    CallbackQueryHandler,
    filters,
)
from pymongo import MongoClient

# ================= CONFIG =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

API_URL = "https://mynkapi.amit1100941.workers.dev/api"
API_KEY = os.getenv("API_KEY")

# ================= DB =================
mongo = MongoClient(MONGO_URI)
db = mongo["ghost_eye"]
users = db["users"]
protected = db["protected"]

# ================= GLOBAL =================
broadcast_state = {
    "running": False,
    "sent": 0,
    "failed": 0,
    "total": 0,
    "progress_msg": None,
}

# ================= HELPERS =================
def is_admin(uid: int) -> bool:
    return uid == ADMIN_ID

def is_valid_number(text: str) -> bool:
    return re.fullmatch(r"[6-9]\d{9}", text) is not None

# ================= DAILY CREDIT JOB =================
async def daily_credit_job(context: ContextTypes.DEFAULT_TYPE):
    for u in users.find({"unlimited": {"$ne": True}}):
        users.update_one(
            {"_id": u["_id"]},
            {"$inc": {"credits": 1}}
        )
        try:
            await context.bot.send_message(
                u["_id"],
                "🎁 Daily Free Credit!\n\n"
                "You have received 1 free credit.\n"
                "Send /start to check your balance."
            )
        except:
            pass

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    if not users.find_one({"_id": uid}):
        users.insert_one({
            "_id": uid,
            "credits": 2,
            "unlimited": False,
            "created_at": datetime.utcnow()
        })

    user = users.find_one({"_id": uid})
    credits = "Unlimited" if user.get("unlimited") else user.get("credits", 0)

    await update.message.reply_text(
        "🌐 Welcome to Ghost Eye OSINT 🌐\n\n"
        f"👤 UserID: {uid}\n"
        f"💳 Credits: {credits}\n\n"
        "💡 Send number to fetch details\n\n"
        "• Number (without +91)\n"
        "• Name / Address\n"
        "• Operator / Circle\n"
        "• Alt Numbers\n"
        "• Vehicle / UPI / Etc"
    )

# ================= SEARCH =================
async def search_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    uid = update.effective_user.id

    if not text.isdigit():
        return

    if not is_valid_number(text):
        await update.message.reply_text("❌ Invalid number\n\nExample:\n92865xxxxx")
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

    broadcast_state.update({
        "running": True,
        "sent": 0,
        "failed": 0,
        "total": users.count_documents({}),
        "progress_msg": None,
    })

    msg = await update.message.reply_text(
        "📢 Broadcast mode ON\nSend text or photo",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🛑 Cancel Broadcast", callback_data="cancel_broadcast")]
        ])
    )
    broadcast_state["progress_msg"] = msg

async def broadcast_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not broadcast_state["running"]:
        return
    if update.message.text and update.message.text.startswith("/"):
        return

    text = update.message.caption or update.message.text
    photo = update.message.photo[-1].file_id if update.message.photo else None

    for u in users.find():
        if not broadcast_state["running"]:
            break
        try:
            if photo:
                await context.bot.send_photo(u["_id"], photo=photo, caption=text)
            else:
                await context.bot.send_message(u["_id"], text)
            broadcast_state["sent"] += 1
        except:
            broadcast_state["failed"] += 1
        await asyncio.sleep(0.05)

    broadcast_state["running"] = False
    await broadcast_state["progress_msg"].edit_text(
        f"✅ Broadcast finished\nSent: {broadcast_state['sent']}\nFailed: {broadcast_state['failed']}"
    )

async def cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    broadcast_state["running"] = False
    await update.callback_query.edit_message_text("🛑 Broadcast cancelled")

# ================= ADMIN =================
async def add_credit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    uid, amt = map(int, context.args)
    users.update_one({"_id": uid}, {"$inc": {"credits": amt}}, upsert=True)
    await update.message.reply_text("✅ Credits added")

async def remove_credit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    uid, amt = map(int, context.args)
    users.update_one({"_id": uid}, {"$inc": {"credits": -amt}})
    await update.message.reply_text("✅ Credits removed")

async def unlimited(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    uid = int(context.args[0])
    mode = context.args[1].lower() == "on"
    users.update_one({"_id": uid}, {"$set": {"unlimited": mode}})
    await update.message.reply_text("✅ Unlimited updated")

async def protect_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    protected.insert_one({"number": context.args[0]})
    await update.message.reply_text("✅ Number protected")

async def unprotect_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    protected.delete_one({"number": context.args[0]})
    await update.message.reply_text("✅ Number unprotected")

# ================= MAIN =================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("broadcast", broadcast_start))
    app.add_handler(CommandHandler("add", add_credit))
    app.add_handler(CommandHandler("remove", remove_credit))
    app.add_handler(CommandHandler("unlimited", unlimited))
    app.add_handler(CommandHandler("protect", protect_number))
    app.add_handler(CommandHandler("unprotect", unprotect_number))
    app.add_handler(CallbackQueryHandler(cancel_broadcast, pattern="cancel_broadcast"))

    # handlers
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_handler))
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, broadcast_content))

    # daily job (12:00 AM)
    app.job_queue.run_daily(
        daily_credit_job,
        time=time(hour=0, minute=0, second=0)
    )

    app.run_polling()

if __name__ == "__main__":
    main()
