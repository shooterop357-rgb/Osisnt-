import os
import re
import json
import asyncio
import requests
from datetime import datetime
from pymongo import MongoClient

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# ================= ENV =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_URL = os.getenv("API_URL")
API_KEY = os.getenv("API_KEY")
MONGO_URI = os.getenv("MONGO_URI")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")

if not all([BOT_TOKEN, API_URL, API_KEY, MONGO_URI, ADMIN_USERNAME]):
    raise RuntimeError("Missing required environment variables")

# ================= DB =================
client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
db = client["ghost_eye"]
users = db["users"]

# ================= BOOT SEQUENCE =================
async def boot_sequence(update: Update):
    steps = [
        "🔐 Secure channel initialized…",
        "🔐 Secure channel initialized…\n🧠 OSINT modules online",
        "🔐 Secure channel initialized…\n🧠 OSINT modules online\n🗄️ Database synchronized",
        "🔐 Secure channel initialized…\n🧠 OSINT modules online\n🗄️ Database synchronized\n🚀 System ready for query"
    ]

    msg = await update.message.reply_text("🔄 Initializing…")
    for step in steps:
        await asyncio.sleep(0.8)
        await msg.edit_text(step)

    await asyncio.sleep(1.5)
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
        credits = 2
    else:
        credits = user.get("credits", 0)

    await boot_sequence(update)

    welcome = (
        "🌐 Welcome to Our OSINT Bot 🌐\n\n"
        f"👤 UserID : {uid}\n"
        f"💳 Credit : {credits}\n\n"
        "💡 Send me query, and I will fetch all\n"
        "available details for you.\n\n"
        "• Number (without +91)\n"
        "• Name / Address\n"
        "• Operator / Circle\n"
        "• Alt Numbers\n"
        "• Vehicle / UPI / Etc…"
    )
    await update.message.reply_text(welcome)

# ================= SEARCH =================
async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    uid = update.effective_user.id

    user = users.find_one({"_id": uid})
    if not user:
        await update.message.reply_text("⚠️ Please use /start first")
        return

    if not user.get("unlimited") and user.get("credits", 0) <= 0:
        btn = InlineKeyboardMarkup([[
            InlineKeyboardButton("💳 Buy Credits", url=f"https://t.me/{ADMIN_USERNAME}")
        ]])
        await update.message.reply_text(
            "❌ No credits left\n💳 Buy more credits to continue",
            reply_markup=btn
        )
        return

    if not re.fullmatch(r"[6-9]\d{9}", text):
        await update.message.reply_text("❌ Invalid mobile number")
        return

    try:
        resp = requests.get(
            API_URL,
            params={
                "key": API_KEY,
                "type": "mobile",
                "term": text
            },
            timeout=10
        )
        data = resp.json()
    except Exception:
        await update.message.reply_text("⚠️ API error, try again later")
        return

    if not data.get("success") or not data.get("result"):
        await update.message.reply_text("❌ No data found")
        return

    # Deduct credit only on success
    if not user.get("unlimited"):
        users.update_one({"_id": uid}, {"$inc": {"credits": -1}})
        remaining = user.get("credits", 0) - 1
    else:
        remaining = "Unlimited"

    # ===== JSON STYLE RESULT =====
    cleaned = []
    for r in data["result"]:
        cleaned.append({
            "mobile": r.get("mobile"),
            "name": r.get("name"),
            "fname": r.get("fname") or r.get("father_name"),
            "address": r.get("address", "").replace("!", " ").replace("  ", " "),
            "alt": r.get("alt") or r.get("alt_mobile"),
            "circle": r.get("circle"),
            "id": r.get("id") or r.get("id_number"),
            "email": r.get("email", "")
        })

    pretty_json = json.dumps(cleaned, indent=2, ensure_ascii=False)

    await update.message.reply_text(
        f"✅ Search successful\n💳 Remaining credits: {remaining}\n\n"
        f"```json\n{pretty_json}\n```",
        parse_mode="Markdown"
    )

# ================= BROADCAST =================
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender = update.effective_user

    if not sender.username or sender.username.lower() != ADMIN_USERNAME.lower():
        await update.message.reply_text("❌ Unauthorized")
        return

    if not context.args:
        await update.message.reply_text("⚠️ Usage:\n/broadcast your message")
        return

    message = " ".join(context.args)
    sent = failed = 0

    for u in users.find({}):
        try:
            await context.bot.send_message(chat_id=u["_id"], text=message)
            sent += 1
        except:
            failed += 1

    await update.message.reply_text(
        f"✅ Broadcast completed\n📤 Sent: {sent}\n❌ Failed: {failed}"
    )

# ================= BOT =================
app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("broadcast", broadcast))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search))

app.run_polling()
