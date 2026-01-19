import os
import re
import json
import asyncio
import requests
from datetime import datetime, date

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
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
    "total": 0
}

# ================= HELPERS =================
def is_admin(uid: int) -> bool:
    return uid == ADMIN_ID

def normalize_number(text: str):
    text = re.sub(r"\s+", "", text).replace("+", "")
    if text.startswith("91") and len(text) == 12:
        text = text[2:]
    if re.fullmatch(r"[6-9]\d{9}", text):
        return text
    return None

def apply_daily_credit(uid: int):
    today = date.today().isoformat()
    user = users.find_one({"_id": uid})
    if not user:
        return False

    if user.get("last_daily") != today:
        users.update_one(
            {"_id": uid},
            {"$inc": {"credits": 1}, "$set": {"last_daily": today}}
        )
        return True
    return False

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    user = users.find_one({"_id": uid})
    if not user:
        users.insert_one({
            "_id": uid,
            "credits": 2,
            "unlimited": False,
            "created_at": datetime.utcnow()
        })

    daily_added = apply_daily_credit(uid)
    user = users.find_one({"_id": uid})
    credits = "Unlimited" if user.get("unlimited") else user.get("credits", 0)

    msg = (
        "🌐 Welcome to Ghost Eye OSINT 🌐\n\n"
        f"👤 UserID: {uid}\n"
        f"💳 Credits: {credits}\n\n"
        "💡 Send a mobile number to fetch details\n\n"
        "• Indian Number (auto-detect)\n"
        "• Name / Address\n"
        "• Operator / Circle\n"
        "• Alternate Numbers\n"
        "• Vehicle / UPI / Other linked data"
    )

    if daily_added:
        msg += "\n\n🎁 You received 1 daily free credit"

    await update.message.reply_text(msg)

# ================= SEARCH =================
async def search_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip()
    uid = update.effective_user.id

    number = normalize_number(raw)
    if not number:
        await update.message.reply_text("❌ Invalid number format")
        return

    if protected.find_one({"number": number}):
        await update.message.reply_text("❌ This number is protected")
        return

    user = users.find_one({"_id": uid})
    if not user:
        return

    if not user.get("unlimited") and user.get("credits", 0) <= 0:
        await update.message.reply_text("❌ No credits left")
        return

    params = {
        "key": API_KEY,
        "type": "mobile",
        "term": number
    }

    try:
        r = requests.get(API_URL, params=params, timeout=15)
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

    pretty = json.dumps(result, indent=4, ensure_ascii=False)
    await update.message.reply_text(
        f"✅ Search successful\n"
        f"💳 Remaining: {remaining}\n\n"
        f"```json\n{pretty}\n```",
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
        "total": users.count_documents({})
    })

    context.user_data["awaiting_broadcast"] = True

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛑 Cancel Broadcast", callback_data="cancel_broadcast")]
    ])

    await update.message.reply_text(
        f"📢 Broadcast started\nTotal users: {broadcast_state['total']}",
        reply_markup=keyboard
    )

async def broadcast_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_broadcast"):
        return

    context.user_data["awaiting_broadcast"] = False

    text = update.message.caption or update.message.text
    photo = update.message.photo[-1].file_id if update.message.photo else None

    for u in users.find():
        if not broadcast_state["running"]:
            break
        try:
            if photo:
                await context.bot.send_photo(
                    u["_id"],
                    photo=photo,
                    caption=text,
                    parse_mode=None
                )
            else:
                await context.bot.send_message(
                    u["_id"],
                    text,
                    parse_mode=None
                )
            broadcast_state["sent"] += 1
        except:
            broadcast_state["failed"] += 1

        await asyncio.sleep(0.05)

    broadcast_state["running"] = False

    await update.message.reply_text(
        f"✅ Broadcast finished\n"
        f"Sent: {broadcast_state['sent']}\n"
        f"Failed: {broadcast_state['failed']}"
    )

async def cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    broadcast_state["running"] = False
    await update.callback_query.answer("Broadcast cancelled")
    await update.callback_query.edit_message_text("🛑 Broadcast stopped")

# ================= MAIN =================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("broadcast", broadcast_start))
    app.add_handler(CallbackQueryHandler(cancel_broadcast, pattern="cancel_broadcast"))
    app.add_handler(MessageHandler(filters.PHOTO | (filters.TEXT & ~filters.COMMAND), broadcast_content))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_handler))

    app.run_polling()

if __name__ == "__main__":
    main()
