import asyncio
import json
import re
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
import os

# ================= CONFIG =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
API_URL = os.getenv("API_URL")
API_KEY = os.getenv("API_KEY")

# ================= DB =================
mongo = MongoClient(MONGO_URI)
db = mongo["ghost_eye"]
users = db["users"]
protected_numbers = db["protected_numbers"]

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

    await asyncio.sleep(0.6)
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

    welcome = (
        "👁️ **Ghost Eye OSINT** 👁️\n\n"
        f"👤 **UserID:** `{uid}`\n"
        f"💳 **Credits:** `{credits}`\n\n"
        "💡 Send number to fetch details\n\n"
        "• Number (without +91)\n"
        "• Name / Address\n"
        "• Operator / Circle\n"
        "• Alt Numbers\n"
        "• Vehicle / UPI / Etc…"
    )

    await update.message.reply_text(welcome, parse_mode="Markdown")

# ================= CREDIT CHECK =================
def can_use(uid):
    user = users.find_one({"_id": uid})
    if not user:
        return False, 0

    if user.get("unlimited"):
        return True, "Unlimited"

    if user.get("credits", 0) > 0:
        return True, user["credits"]

    return False, 0

# ================= SEARCH =================
async def search_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    uid = update.effective_user.id

    if not re.fullmatch(r"\d{10}", text):
        await update.message.reply_text("❌ Invalid mobile number")
        return

    # Protected check
    if protected_numbers.find_one({"number": text}):
        await update.message.reply_text(
            "❌ This number is protected and cannot be searched."
        )
        return

    allowed, credits = can_use(uid)
    if not allowed:
        await update.message.reply_text(
            "❌ No credits left\n💳 Buy more credits to continue"
        )
        return

    # API CALL
    params = {
        "key": API_KEY,
        "type": "mobile",
        "term": text
    }

    res = requests.get(API_URL, params=params, timeout=20)
    data = res.json()

    raw_results = data.get("result", [])

    if not raw_results:
        await update.message.reply_text("❌ No data found")
        return

    # CLEAN RESULT (IMPORTANT FIX)
    clean = []
    for r in raw_results:
        clean.append({
            "mobile": r.get("mobile"),
            "name": r.get("name"),
            "father_name": r.get("father_name"),
            "address": r.get("address"),
            "alt_mobile": r.get("alt_mobile"),
            "circle": r.get("circle"),
            "email": r.get("email"),
        })

    # Deduct credit
    user = users.find_one({"_id": uid})
    if not user.get("unlimited"):
        users.update_one({"_id": uid}, {"$inc": {"credits": -1}})
        remaining = user["credits"] - 1
    else:
        remaining = "Unlimited"

    pretty = json.dumps(clean, indent=2, ensure_ascii=False)

    await update.message.reply_text(
        f"✅ Search successful\n"
        f"💳 Remaining credits: {remaining}\n\n"
        f"```json\n{pretty}\n```",
        parse_mode="Markdown"
    )

# ================= ADMIN: ADD =================
async def add_credit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    try:
        uid = int(context.args[0])
        amt = int(context.args[1])
        users.update_one({"_id": uid}, {"$inc": {"credits": amt}}, upsert=True)
        await update.message.reply_text("✅ Credits added")
    except:
        await update.message.reply_text("Usage: /add <user_id> <credits>")

# ================= ADMIN: REMOVE =================
async def remove_credit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    try:
        uid = int(context.args[0])
        amt = int(context.args[1])
        users.update_one({"_id": uid}, {"$inc": {"credits": -amt}})
        await update.message.reply_text("✅ Credits removed")
    except:
        await update.message.reply_text("Usage: /remove <user_id> <credits>")

# ================= UNLIMITED =================
async def unlimited(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    uid = int(context.args[0])
    state = context.args[1].lower()

    if state == "on":
        users.update_one({"_id": uid}, {"$set": {"unlimited": True}})
        await update.message.reply_text("✅ Unlimited enabled")
    elif state == "off":
        users.update_one({"_id": uid}, {"$set": {"unlimited": False}})
        await update.message.reply_text("❌ Unlimited disabled")

# ================= PROTECT NUMBER =================
async def protect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    num = context.args[0]
    protected_numbers.insert_one({"number": num})
    await update.message.reply_text("🔐 Number protected")

async def unprotect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    num = context.args[0]
    protected_numbers.delete_one({"number": num})
    await update.message.reply_text("🔓 Number unprotected")

# ================= BROADCAST =================
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    msg = " ".join(context.args)
    for u in users.find():
        try:
            await context.bot.send_message(u["_id"], msg)
        except:
            pass

    await update.message.reply_text("📢 Broadcast sent")

# ================= MAIN =================
app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("add", add_credit))
app.add_handler(CommandHandler("remove", remove_credit))
app.add_handler(CommandHandler("unlimited", unlimited))
app.add_handler(CommandHandler("protect", protect))
app.add_handler(CommandHandler("unprotect", unprotect))
app.add_handler(CommandHandler("broadcast", broadcast))

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_number))

app.run_polling()
