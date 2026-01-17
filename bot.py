import os, re, asyncio, requests
from datetime import datetime
from pymongo import MongoClient
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    MessageHandler, ContextTypes, filters
)

# ================= ENV =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
API_URL = os.getenv("API_URL")
API_KEY = os.getenv("API_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

# ================= DB =================
client = MongoClient(MONGO_URI)
db = client["ghost_eye"]
users = db["users"]
protected = db["protected_numbers"]

# ================= HELPERS =================
def is_admin(uid: int):
    return uid == ADMIN_ID

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
    return

# ================= SEARCH =================
async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    uid = update.effective_user.id

    if not re.fullmatch(r"[6-9]\d{9}", text):
        await update.message.reply_text("❌ Invalid mobile number")
        return

    if protected.find_one({"number": text}):
        await update.message.reply_text("❌ This number is protected and cannot be searched.")
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
        }, timeout=10)
        data = r.json()
    except:
        await update.message.reply_text("⚠️ API error")
        return

    if not data.get("success"):
        await update.message.reply_text("❌ No data found")
        return

    if not user.get("unlimited"):
        users.update_one({"_id": uid}, {"$inc": {"credits": -1}})
        remaining = user["credits"] - 1
    else:
        remaining = "Unlimited"

    await update.message.reply_text(
        f"✅ Search successful\n"
        f"💳 Remaining credits: {remaining}\n\n"
        f"```json\n{data}\n```",
        parse_mode="Markdown"
    )

# ================= ADMIN COMMANDS =================
async def add_credit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    uid, amt = int(context.args[0]), int(context.args[1])
    users.update_one({"_id": uid}, {"$inc": {"credits": amt}}, upsert=True)
    await update.message.reply_text("✅ Credits added")

async def remove_credit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    uid, amt = int(context.args[0]), int(context.args[1])
    users.update_one({"_id": uid}, {"$inc": {"credits": -amt}})
    await update.message.reply_text("✅ Credits removed")

async def unlimited(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    uid = int(context.args[0])
    state = context.args[1].lower() == "on"
    users.update_one({"_id": uid}, {"$set": {"unlimited": state}}, upsert=True)
    await update.message.reply_text(f"✅ Unlimited {'enabled' if state else 'disabled'}")

async def protect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    num = context.args[0]
    protected.update_one({"number": num}, {"$set": {"number": num}}, upsert=True)
    await update.message.reply_text("✅ Number protected")

async def unprotect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    num = context.args[0]
    protected.delete_one({"number": num})
    await update.message.reply_text("✅ Number unprotected")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    msg = " ".join(context.args)
    for u in users.find():
        try:
            await context.bot.send_message(u["_id"], msg)
        except:
            pass
    await update.message.reply_text("✅ Broadcast sent")

# ================= BOT =================
app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("add", add_credit))
app.add_handler(CommandHandler("remove", remove_credit))
app.add_handler(CommandHandler("unlimited", unlimited))
app.add_handler(CommandHandler("protect", protect))
app.add_handler(CommandHandler("unprotect", unprotect))
app.add_handler(CommandHandler("broadcast", broadcast))

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search))

app.run_polling()
