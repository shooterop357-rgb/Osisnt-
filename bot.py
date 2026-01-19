import os
import json
import re
import asyncio
import requests
from datetime import datetime, date
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
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

# ================= DB =================
mongo = MongoClient(MONGO_URI)
db = mongo["ghost_eye"]
users = db["users"]
protected = db["protected"]

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
            {
                "$inc": {"credits": 1},
                "$set": {"last_daily": today}
            }
        )
        return True
    return False

# ================= BOOT =================
async def boot_sequence(update: Update):
    steps = [
        "🔐 Secure channel initialized…",
        "🧠 OSINT modules online",
        "🗄️ Database synchronized",
        "🚀 System ready",
    ]
    msg = await update.message.reply_text("🔄 Initializing…")
    for s in steps:
        await asyncio.sleep(0.3)
        await msg.edit_text(s)
    await msg.delete()

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

    await boot_sequence(update)

    user = users.find_one({"_id": uid})
    credits = "Unlimited" if user.get("unlimited") else user.get("credits", 0)

    msg = (
        f"🌐 Ghost Eye OSINT\n\n"
        f"👤 UserID: {uid}\n"
        f"💳 Credits: {credits}\n"
    )

    if daily_added:
        msg += "\n🎁 You received 1 daily free credit"

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
        keyboard = [[InlineKeyboardButton("💳 Buy Credits", url="https://t.me/Frx_Shooter")]]
        await update.message.reply_text(
            "❌ No credits left",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
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

# ================= ADMIN =================
async def broadcast_btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    try:
        text, btn_text, btn_url = " ".join(context.args).split("|")
    except:
        await update.message.reply_text(
            "❌ Format:\n/broadcast_btn message | button text | https://link"
        )
        return

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(btn_text.strip(), url=btn_url.strip())]
    ])

    for u in users.find():
        try:
            await context.bot.send_message(u["_id"], text.strip(), reply_markup=markup)
        except:
            pass

    await update.message.reply_text("✅ Broadcast sent with button")

# ================= MAIN =================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("broadcast_btn", broadcast_btn))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_handler))

    app.run_polling()

if __name__ == "__main__":
    main()
