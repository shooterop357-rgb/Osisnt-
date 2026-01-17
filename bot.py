import os, re, asyncio, json, requests
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
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME").replace("@", "")

# ================= DB =================
client = MongoClient(MONGO_URI)
db = client["ghost_eye"]
users = db["users"]
protected = db["protected_numbers"]

# ================= HELPERS =================
def is_admin(update: Update):
    return update.effective_user.username and \
           update.effective_user.username.lower() == ADMIN_USERNAME.lower()

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

    # 🔥 BOOT SEQUENCE (same message edit)
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

    welcome = (
        "🌐 **Welcome to Ghost Eye OSINT** 🌐\n\n"
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

# ================= SEARCH =================
async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    uid = update.effective_user.id

    user = users.find_one({"_id": uid})
    if not user:
        return

    # 🔒 PROTECTED NUMBER CHECK
    if protected.find_one({"number": text}):
        await update.message.reply_text(
            "❌ This number is protected and cannot be searched."
        )
        return

    if not user.get("unlimited") and user.get("credits", 0) <= 0:
        btn = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "💳 Buy Credits",
                url=f"https://t.me/{ADMIN_USERNAME}"
            )
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
        r = requests.get(
            API_URL,
            params={"key": API_KEY, "type": "mobile", "term": text},
            timeout=10
        )
        data = r.json()
    except:
        await update.message.reply_text("⚠️ API error")
        return

    if not data.get("result"):
        await update.message.reply_text("❌ No data found")
        return

    if not user.get("unlimited"):
        users.update_one({"_id": uid}, {"$inc": {"credits": -1}})
        remaining = user["credits"] - 1
    else:
        remaining = "Unlimited"

    cleaned = []
    for r in data["result"]:
        cleaned.append({
            "mobile": r.get("mobile"),
            "name": r.get("name"),
            "fname": r.get("fname") or r.get("father_name"),
            "address": r.get("address", "").replace("!", " "),
            "alt": r.get("alt") or r.get("alt_mobile"),
            "circle": r.get("circle"),
            "id": r.get("id") or r.get("id_number"),
            "email": r.get("email", "")
        })

    pretty = json.dumps(cleaned, indent=2, ensure_ascii=False)

    await update.message.reply_text(
        f"✅ **Search successful**\n"
        f"💳 Remaining: `{remaining}`\n\n"
        f"```json\n{pretty}\n```",
        parse_mode="Markdown"
    )

# ================= BROADCAST =================
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
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

# ================= PROTECT COMMAND =================
async def protect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("❌ Unauthorized")
        return

    if len(context.args) < 1:
        await update.message.reply_text(
            "Usage:\n/protect add <number>\n/protect remove <number>\n/protect list"
        )
        return

    action = context.args[0].lower()

    if action == "add" and len(context.args) == 2:
        number = context.args[1]
        protected.update_one(
            {"number": number},
            {"$set": {"number": number}},
            upsert=True
        )
        await update.message.reply_text(f"🔒 Number protected:\n{number}")

    elif action == "remove" and len(context.args) == 2:
        number = context.args[1]
        protected.delete_one({"number": number})
        await update.message.reply_text(f"🔓 Protection removed:\n{number}")

    elif action == "list":
        nums = list(protected.find())
        if not nums:
            await update.message.reply_text("No protected numbers.")
            return
        msg = "🔐 Protected Numbers:\n\n"
        for n in nums:
            msg += f"• {n['number']}\n"
        await update.message.reply_text(msg)

    else:
        await update.message.reply_text(
            "Usage:\n/protect add <number>\n/protect remove <number>\n/protect list"
        )

# ================= BOT =================
app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("broadcast", broadcast))
app.add_handler(CommandHandler("protect", protect))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search))

app.run_polling()
