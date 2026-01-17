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

    # ⚡ Fast animation (edit-based)
    msg = await update.message.reply_text("🔐 Initializing secure channel…")
    await asyncio.sleep(0.4)
    await msg.edit_text("🔐 Secure channel initialized…\n🧠 OSINT modules online")
    await asyncio.sleep(0.4)
    await msg.edit_text(
        "🔐 Secure channel initialized…\n"
        "🧠 OSINT modules online\n"
        "🗄️ Database synchronized"
    )
    await asyncio.sleep(0.4)
    await msg.edit_text(
        "🔐 Secure channel initialized…\n"
        "🧠 OSINT modules online\n"
        "🗄️ Database synchronized\n"
        "🚀 System ready for query"
    )
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

# ================= ADMIN =================
def is_admin(update):
    return update.effective_user.username == ADMIN_USERNAME

async def add_credits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    uid, amt = int(context.args[0]), int(context.args[1])
    users.update_one({"_id": uid}, {"$inc": {"credits": amt}}, upsert=True)
    await update.message.reply_text(f"✅ Added {amt} credits to {uid}")

async def remove_credits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    uid, amt = int(context.args[0]), int(context.args[1])
    users.update_one({"_id": uid}, {"$inc": {"credits": -amt}})
    await update.message.reply_text(f"✅ Removed {amt} credits from {uid}")

async def unlimited(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    uid = int(context.args[0])
    mode = context.args[1].lower()
    users.update_one({"_id": uid}, {"$set": {"unlimited": mode == "on"}})
    await update.message.reply_text(f"✅ Unlimited {mode.upper()} for {uid}")

# ================= BOT =================
app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("add", add_credits))
app.add_handler(CommandHandler("remove", remove_credits))
app.add_handler(CommandHandler("unlimited", unlimited))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search))

app.run_polling()
