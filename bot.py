import os
import re
import json
import asyncio
import requests
from datetime import datetime, date

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

def apply_daily_credit(uid: int):
    today = date.today().isoformat()
    user = users.find_one({"_id": uid})
    if user and user.get("last_daily") != today:
        users.update_one(
            {"_id": uid},
            {"$inc": {"credits": 1}, "$set": {"last_daily": today}}
        )
        return True
    return False

def progress_bar(done, total, size=20):
    filled = int(size * done / total) if total else 0
    return "█" * filled + "░" * (size - filled)

# ================= INTRO =================
async def hacker_intro(update: Update):
    steps = [
        "🔐 Secure channel initialized…",
        "🧠 OSINT modules online",
        "🗄️ Database synchronized",
        "🚀 Ghost Eye core loaded",
    ]
    msg = await update.message.reply_text("⌛ Initializing…")
    for s in steps:
        await asyncio.sleep(0.3)
        await msg.edit_text(s)
    await msg.delete()

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

    daily = apply_daily_credit(uid)
    await hacker_intro(update)

    user = users.find_one({"_id": uid})
    credits = "Unlimited" if user.get("unlimited") else user.get("credits", 0)

    msg = (
        "🌐 Welcome to Ghost Eye OSINT 🌐\n\n"
        f"👤 UserID: {uid}\n"
        f"💳 Credits: {credits}\n\n"
        "💡 Send number to fetch details\n\n"
        "• Number (without +91)\n"
        "• Name / Address\n"
        "• Operator / Circle\n"
        "• Alt Numbers\n"
        "• Vehicle / UPI / E"
    )

    if daily:
        msg += "\n\n🎁 You received 1 daily free credit"

    await update.message.reply_text(msg)

# ================= SEARCH =================
async def search_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    uid = update.effective_user.id

    # silent ignore non-numeric
    if not text.isdigit():
        return

    if not is_valid_number(text):
        await update.message.reply_text(
            "❌ Invalid number\n\nExample:\n92865xxxxx"
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

    user = users.find_one({"_id": uid})
    remaining = "Unlimited" if user.get("unlimited") else user.get("credits", 0)

    await update.message.reply_text(
        f"✅ Search successful\n💳 Remaining: {remaining}\n\n"
        f"```json\n{json.dumps(result, indent=4, ensure_ascii=False)}\n```",
        parse_mode="Markdown"
    )

# ================= GLOBAL =================
broadcast_state = {
    "running": False,
    "sent": 0,
    "failed": 0,
    "total": 0,
    "progress_msg": None,
}

# ================= BROADCAST START =================
async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    if broadcast_state["running"]:
        await update.message.reply_text("⚠️ Broadcast already running")
        return

    broadcast_state.update({
        "running": True,
        "sent": 0,
        "failed": 0,
        "total": users.count_documents({}),
        "progress_msg": None,
    })

    msg = await update.message.reply_text(
        "📢 Broadcast mode ON\n\n➡️ Send text or photo to broadcast",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🛑 Cancel Broadcast", callback_data="cancel_broadcast")]
        ])
    )
    broadcast_state["progress_msg"] = msg

# ================= BROADCAST CONTENT =================
async def broadcast_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 🔒 HARD GUARD
    if not is_admin(update.effective_user.id):
        return
    if not broadcast_state["running"]:
        return

    text = update.message.caption or update.message.text
    photo = update.message.photo[-1].file_id if update.message.photo else None

    for u in users.find():
        # 🛑 STOP IMMEDIATELY IF CANCELLED
        if not broadcast_state["running"]:
            break

        try:
            if photo:
                await context.bot.send_photo(
                    chat_id=u["_id"],
                    photo=photo,
                    caption=text
                )
            else:
                await context.bot.send_message(
                    chat_id=u["_id"],
                    text=text
                )
            broadcast_state["sent"] += 1
        except:
            broadcast_state["failed"] += 1

        # 📊 Progress update
        done = broadcast_state["sent"]
        total = broadcast_state["total"]
        percent = int((done / total) * 100) if total else 0
        bar_len = 20
        filled = int(bar_len * percent / 100)
        bar = "█" * filled + "░" * (bar_len - filled)

        if broadcast_state["progress_msg"]:
            try:
                await broadcast_state["progress_msg"].edit_text(
                    f"📢 Broadcasting…\n\n"
                    f"{bar} {percent}%\n"
                    f"Sent: {done} / {total}\n"
                    f"Failed: {broadcast_state['failed']}",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🛑 Cancel Broadcast", callback_data="cancel_broadcast")]
                    ])
                )
            except:
                pass

        await asyncio.sleep(0.05)

    # ✅ CLEAN FINISH (only if not cancelled)
    if broadcast_state["running"]:
        broadcast_state["running"] = False
        if broadcast_state["progress_msg"]:
            await broadcast_state["progress_msg"].edit_text(
                f"✅ Broadcast finished\n\n"
                f"Sent: {broadcast_state['sent']}\n"
                f"Failed: {broadcast_state['failed']}"
            )

# ================= CANCEL BROADCAST =================
async def cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    broadcast_state["running"] = False
    await update.callback_query.answer("Broadcast stopped")
    await update.callback_query.edit_message_text("🛑 Broadcast cancelled")

# ================= MAIN =================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("broadcast", broadcast_start))
    app.add_handler(CallbackQueryHandler(cancel_broadcast, pattern="cancel_broadcast"))

    # 🔹 Search FIRST (numbers never break)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_handler))

    # 🔹 Broadcast content LAST
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, broadcast_content))

    app.run_polling()

if __name__ == "__main__":
    main()
