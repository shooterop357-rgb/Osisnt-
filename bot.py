import os, re, asyncio, requests
from datetime import datetime
from pymongo import MongoClient
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    MessageHandler, ContextTypes, filters
)

# ================= ENV =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_URL = os.getenv("API_URL")
API_KEY = os.getenv("API_KEY")
MONGO_URI = os.getenv("MONGO_URI")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")

# ================= DB =================
client = MongoClient(MONGO_URI)
db = client["ghost_eye"]
users = db["users"]

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id

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
        credits = data["credits"]

    # 🔐 Intro (auto delete)
    intro = (
        "🔐 Secure channel initialized…\n"
        "🧠 OSINT modules online\n"
        "🗄️ Database synchronized\n"
        "🚀 System ready for query"
    )
    intro_msg = await update.message.reply_text(intro)
    await asyncio.sleep(3)
    await intro_msg.delete()

    # Welcome screen
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
        return

    # No credits
    if not user.get("unlimited") and user["credits"] <= 0:
        btn = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "💳 Buy Credits",
                url=f"https://t.me/{ADMIN_USERNAME}"
            )
        ]])
        await update.message.reply_text(
            "❌ No credits left\n💳 Buy more credits to continue\n👇 Tap the button below",
            reply_markup=btn
        )
        return

    # Number validation
    if not re.fullmatch(r"[6-9]\d{9}", text):
        await update.message.reply_text("❌ Invalid mobile number")
        return

    # API call
    try:
        r = requests.get(
            API_URL,
            params={
                "key": API_KEY,
                "type": "mobile",
                "term": text
            },
            timeout=10
        )
        data = r.json()
    except:
        await update.message.reply_text("⚠️ API error, try again")
        return

    if not data.get("success") or not data.get("result"):
        await update.message.reply_text("❌ No data found")
        return

    # Deduct credit ONLY on success
    if not user.get("unlimited"):
        users.update_one(
            {"_id": uid},
            {"$inc": {"credits": -1}}
        )
        remaining = user["credits"] - 1
    else:
        remaining = "Unlimited"

    await update.message.reply_text(
        f"✅ Search successful\n"
        f"💳 Remaining credits: {remaining}\n\n"
        f"{data['result']}"
    )

# ================= BROADCAST =================
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender = update.effective_user

    if sender.username != ADMIN_USERNAME:
        await update.message.reply_text("❌ Unauthorized")
        return

    if not context.args:
        await update.message.reply_text("⚠️ Usage:\n/broadcast your message")
        return

    message = " ".join(context.args)
    sent = 0
    failed = 0

    for u in users.find({}):
        try:
            await context.bot.send_message(
                chat_id=u["_id"],
                text=message
            )
            sent += 1
        except:
            failed += 1

    await update.message.reply_text(
        f"✅ Broadcast completed\n"
        f"📤 Sent: {sent}\n"
        f"❌ Failed: {failed}"
    )

# ================= BOT =================
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("broadcast", broadcast))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search))
app.run_polling()
