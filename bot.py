import os, re, asyncio, requests
from datetime import datetime
from pymongo import MongoClient
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    MessageHandler, ContextTypes, filters
)

# ================= ENV =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_URL = os.getenv("API_URL")
API_KEY = os.getenv("API_KEY")
MONGO_URI = os.getenv("MONGO_URI")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")  # without @

# ================= DB =================
client = MongoClient(MONGO_URI)
db = client["ghost_eye"]
users = db["users"]
protected = db["protected_numbers"]

# ================= ADMIN CHECK =================
def is_admin(update: Update):
    return update.effective_user.username == ADMIN_USERNAME

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
        await asyncio.sleep(0.35)
        await msg.edit_text(step)
    await asyncio.sleep(0.6)
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
        credits = "Unlimited" if user.get("unlimited") else user.get("credits", 0)

    await boot_sequence(update)

    await update.message.reply_text(
        f"🌐 **Welcome to Ghost Eye OSINT** 🌐\n\n"
        f"👤 **UserID:** `{uid}`\n"
        f"💳 **Credits:** `{credits}`\n\n"
        "💡 Send number to fetch details\n\n"
        "• Number (without +91)\n"
        "• Name / Address\n"
        "• Operator / Circle\n"
        "• Alt Numbers\n"
        "• Vehicle / UPI / Etc…",
        parse_mode="Markdown"
    )

# ================= SEARCH =================
async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    number = update.message.text.strip()
    uid = update.effective_user.id

    if not re.fullmatch(r"[6-9]\d{9}", number):
        await update.message.reply_text("❌ Invalid mobile number")
        return

    if protected.find_one({"number": number}):
        await update.message.reply_text(
            "❌ This number is protected and cannot be searched."
        )
        return

    user = users.find_one({"_id": uid})
    if not user:
        return

    if not user.get("unlimited") and user.get("credits", 0) <= 0:
        btn = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "💳 Buy Credits",
                url=f"https://t.me/{ADMIN_USERNAME}"
            )
        ]])
        await update.message.reply_text(
            "❌ No credits left\nBuy more credits to continue",
            reply_markup=btn
        )
        return

    try:
        r = requests.get(API_URL, params={
            "key": API_KEY,
            "type": "mobile",
            "term": number
        }, timeout=10)
        data = r.json()
    except:
        await update.message.reply_text("⚠️ API error")
        return

    if not data:
        await update.message.reply_text("❌ No data found")
        return

    if not user.get("unlimited"):
        users.update_one({"_id": uid}, {"$inc": {"credits": -1}})
        remaining = user["credits"] - 1
    else:
        remaining = "Unlimited"

    await update.message.reply_text(
        f"✅ **Search successful**\n"
        f"💳 **Remaining credits:** `{remaining}`\n\n"
        f"```json\n{data}\n```",
        parse_mode="Markdown"
    )

# ================= CREDITS =================
async def add_credits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    uid = int(context.args[0])
    credits = int(context.args[1])
    users.update_one({"_id": uid}, {"$inc": {"credits": credits}}, upsert=True)
    await update.message.reply_text("✅ Credits added")

async def remove_credits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    uid = int(context.args[0])
    credits = int(context.args[1])
    users.update_one({"_id": uid}, {"$inc": {"credits": -credits}})
    await update.message.reply_text("✅ Credits removed")

# ================= UNLIMITED =================
async def unlimited(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    uid = int(context.args[0])
    state = context.args[1].lower() == "on"
    users.update_one({"_id": uid}, {"$set": {"unlimited": state}})
    await update.message.reply_text(
        f"♾️ Unlimited {'enabled' if state else 'disabled'}"
    )

# ================= PROTECTION =================
async def protect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return

    action = context.args[0].lower()

    if action == "add":
        num = context.args[1]
        protected.update_one({"number": num}, {"$set": {"number": num}}, upsert=True)
        await update.message.reply_text("🔒 Number protected")

    elif action == "remove":
        num = context.args[1]
        protected.delete_one({"number": num})
        await update.message.reply_text("🔓 Number unprotected")

    elif action == "list":
        nums = [x["number"] for x in protected.find()]
        await update.message.reply_text(
            "🔒 Protected Numbers:\n" + ("\n".join(nums) if nums else "None")
        )

# ================= BOT =================
app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("add", add_credits))
app.add_handler(CommandHandler("remove", remove_credits))
app.add_handler(CommandHandler("unlimited", unlimited))
app.add_handler(CommandHandler("protect", protect))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search))

app.run_polling()
