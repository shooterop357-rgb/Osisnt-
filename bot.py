import os
import json
import re
import asyncio
import requests
from datetime import datetime

from telegram import Update
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

def is_valid_number(text: str) -> bool:
    return re.fullmatch(r"[6-9]\d{9}", text) is not None

# ================= BOOT SEQUENCE =================
async def boot_sequence(update: Update):
    steps = [
        "🔐 Secure channel initialized…",
        "🔐 Secure channel initialized…\n🧠 OSINT modules online",
        "🔐 Secure channel initialized…\n🧠 OSINT modules online\n🗄️ Database synchronized",
        "🔐 Secure channel initialized…\n🧠 OSINT modules online\n🗄️ Database synchronized\n🚀 System ready for query",
    ]

    msg = await update.message.reply_text("🔄 Initializing…")
    for step in steps:
        await asyncio.sleep(0.35)
        await msg.edit_text(step)

    await asyncio.sleep(0.5)
    await msg.delete()

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    data = users.find_one({"_id": uid})
    if not data:
        users.insert_one({
            "_id": uid,
            "credits": 2,
            "unlimited": False,
            "created_at": datetime.utcnow()
        })
        credits = 2
    else:
        credits = "Unlimited" if data.get("unlimited") else data.get("credits", 0)

    await boot_sequence(update)

    await update.message.reply_text(
        f"🌐 Welcome to Ghost Eye OSINT 🌐\n\n"
        f"👤 UserID: {uid}\n"
        f"💳 Credits: {credits}\n\n"
        f"💡 Send number to fetch details\n\n"
        f"• Number (without +91)\n"
        f"• Name / Address\n"
        f"• Operator / Circle\n"
        f"• Alt Numbers\n"
        f"• Vehicle / UPI / Etc…"
    )

# ================= SEARCH =================
async def search_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    uid = update.effective_user.id

    if not is_valid_number(text):
        return

    # 🔒 Protected number check
    if protected.find_one({"number": text}):
        await update.message.reply_text(
            "❌ This number is protected and cannot be searched."
        )
        return

    user = users.find_one({"_id": uid})
    if not user:
        return

    # 💳 Credit check
    if not user.get("unlimited"):
        if user.get("credits", 0) <= 0:
            keyboard = [
                [InlineKeyboardButton("💳 Buy Credits", url="https://t.me/Frx_Shooter")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                "❌ No credits left\n💳 Buy more credits to continue",
                reply_markup=reply_markup
            )
            return

        # ➖ deduct 1 credit
        users.update_one(
            {"_id": uid},
            {"$inc": {"credits": -1}}
        )

    # 🌐 API request
    params = {
        "key": API_KEY,
        "type": "mobile",
        "term": text
    }

    try:
        r = requests.get(API_URL, params=params, timeout=15)
        data = r.json()
    except Exception:
        await update.message.reply_text("❌ API error.")
        return

    result = data.get("result", [])

    # 🔁 fresh credit fetch
    user = users.find_one({"_id": uid})
    remaining = "Unlimited" if user.get("unlimited") else user.get("credits", 0)

    pretty = json.dumps(result, indent=4, ensure_ascii=False)

    await update.message.reply_text(
        f"✅ Search successful\n"
        f"💳 Remaining: {remaining}\n\n"
        f"JSON\n"
        f"```json\n{pretty}\n```",
        parse_mode="Markdown"
    )

# ================= ADMIN COMMANDS =================
async def add_credit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    uid, amount = map(int, context.args)
    users.update_one({"_id": uid}, {"$inc": {"credits": amount}}, upsert=True)
    await update.message.reply_text("✅ Credits added.")

async def remove_credit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    uid, amount = map(int, context.args)
    users.update_one({"_id": uid}, {"$inc": {"credits": -amount}})
    await update.message.reply_text("✅ Credits removed.")

async def unlimited(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    uid = int(context.args[0])
    mode = context.args[1].lower() == "on"

    users.update_one({"_id": uid}, {"$set": {"unlimited": mode}})
    await update.message.reply_text("✅ Unlimited updated.")

async def protect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    number = context.args[0]
    protected.insert_one({"number": number})
    await update.message.reply_text("✅ Number protected.")

async def unprotect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    number = context.args[0]
    protected.delete_one({"number": number})
    await update.message.reply_text("✅ Number unprotected.")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    msg = " ".join(context.args)
    for u in users.find():
        try:
            await context.bot.send_message(u["_id"], msg)
        except:
            pass

    await update.message.reply_text("✅ Broadcast sent.")

# ================= MAIN =================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_credit))
    app.add_handler(CommandHandler("remove", remove_credit))
    app.add_handler(CommandHandler("unlimited", unlimited))
    app.add_handler(CommandHandler("protect", protect))
    app.add_handler(CommandHandler("unprotect", unprotect))
    app.add_handler(CommandHandler("broadcast", broadcast))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_handler))

    app.run_polling()

if __name__ == "__main__":
    main()
