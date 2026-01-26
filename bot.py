import os
import re
import json
import asyncio
import requests
from datetime import datetime, date, time
from zoneinfo import ZoneInfo

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
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
API_KEY = os.getenv("API_KEY")

ADMIN_IDS = set(
    int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()
)

API_URL = "https://mynkapi.amit1100941.workers.dev/api"
IST = ZoneInfo("Asia/Kolkata")

# ================= DB =================
mongo = MongoClient(MONGO_URI)
db = mongo["ghost_eye"]
users = db["users"]
protected = db["protected"]

# ================= BROADCAST STATE =================
broadcast_state = {
    "awaiting_content": False,
    "sent": 0,
    "failed": 0,
}

# ================= HELPERS =================
def is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS

def is_valid_number(text: str) -> bool:
    digits = re.sub(r"\D", "", text)
    return len(digits) == 10 and digits[0] in "6789"

def clean_number(text: str) -> str:
    return re.sub(r"\D", "", text)[-10:]

def split_text(text, limit=4096):
    return [text[i:i+limit] for i in range(0, len(text), limit)]

async def safe_reply(update: Update, text: str):
    await update.message.chat.send_action(ChatAction.TYPING)
    if len(text) <= 4096:
        await update.message.reply_text(text)
    else:
        for part in split_text(text):
            await update.message.reply_text(part)

# ================= HACKER INTRO =================
async def hacker_intro(update: Update):
    msg = await update.message.reply_text("🔐 Initializing Ghost Eye OSINT")
    await asyncio.sleep(0.4)
    await msg.edit_text("🧠 Loading Modules")
    await asyncio.sleep(0.4)
    await msg.edit_text("🗄️ Syncing Database")
    await asyncio.sleep(0.4)
    await msg.edit_text("🌐 Connecting Services")
    await asyncio.sleep(0.4)
    await msg.edit_text("🚀 System Online")
    return msg

# ================= DAILY CREDIT =================
async def daily_credit_job(context: ContextTypes.DEFAULT_TYPE):
    today = date.today().isoformat()
    expiry = "Today 11:59 PM IST"

    for user in users.find():
        if user.get("last_daily") == today:
            continue

        users.update_one(
            {"_id": user["_id"]},
            {"$set": {"credits": 1, "last_daily": today}}
        )

        try:
            await context.bot.send_message(
                user["_id"],
                "🎁 Daily Free Credit Added\n\n"
                "💳 +1 Credit\n"
                f"⏳ Expires: {expiry}"
            )
        except:
            pass

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    broadcast_state["awaiting_content"] = False

    if not users.find_one({"_id": uid}):
        users.insert_one({
            "_id": uid,
            "credits": 1,
            "unlimited": False,
            "created_at": datetime.utcnow()
        })

    intro_msg = await hacker_intro(update)
    await asyncio.sleep(0.8)
    await intro_msg.delete()

    user = users.find_one({"_id": uid})
    credits = "Unlimited" if user.get("unlimited") else user.get("credits", 0)

    await update.message.reply_text(
        "🌐 Welcome to Ghost Eye OSINT 🌐\n\n"
        f"👤 UserID: {uid}\n"
        f"💳 Credits: {credits}\n\n"
        "💡 Send number to fetch details"
    )

# ================= SEARCH =================
async def search_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if broadcast_state["awaiting_content"]:
        return

    text = update.message.text.strip()
    uid = update.effective_user.id

    if not is_valid_number(text):
        await update.message.reply_text("❌ Please send a valid 10 digit number")
        return

    number = clean_number(text)

    if protected.find_one({"number": number}):
        await update.message.reply_text("❌ This number is protected")
        return

    user = users.find_one({"_id": uid})
    if not user:
        return

    # 🔥 CREDIT OVER FIX (INLINE BUTTON)
    if not user.get("unlimited") and user.get("credits", 0) <= 0:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💳 Buy Credits", url="https://t.me/Frx_Shooter")]
        ])

        await update.message.reply_text(
            "❌ No credits left\n\n"
            "💳 Buy more credits\n"
            "📩 Contact: Frx_Shooter",
            reply_markup=keyboard
        )
        return

    await update.message.chat.send_action(ChatAction.TYPING)

    try:
        r = requests.get(API_URL, params={
            "key": API_KEY,
            "type": "mobile",
            "term": number
        }, timeout=15)
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

    credits_left = "Unlimited" if user.get("unlimited") else user.get("credits", 0)
    json_text = json.dumps(result, indent=2, ensure_ascii=False)

    # 🔥 JOHNSON / JSON FIX
    response = (
        "✅ Search successful\n"
        f"💳 Remaining: {credits_left}\n\n"
        "```json\n"
        f"{json_text}\n"
        "```"
    )

    await safe_reply(update, response)

# ================= BROADCAST =================
async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    broadcast_state["awaiting_content"] = True
    broadcast_state["sent"] = 0
    broadcast_state["failed"] = 0

    await update.message.reply_text(
        "📢 Broadcast Mode ON\n\nSend text or photo to broadcast."
    )

async def broadcast_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not broadcast_state["awaiting_content"]:
        return
    if not is_admin(update.effective_user.id):
        return

    broadcast_state["awaiting_content"] = False

    text = update.message.caption or update.message.text
    photo = update.message.photo[-1].file_id if update.message.photo else None

    progress = await update.message.reply_text("📡 Broadcasting started…")

    for user in users.find():
        if user["_id"] == update.effective_user.id:
            continue
        try:
            if photo:
                await context.bot.send_photo(user["_id"], photo=photo, caption=text)
            else:
                await context.bot.send_message(user["_id"], text)
            broadcast_state["sent"] += 1
        except:
            broadcast_state["failed"] += 1

        await asyncio.sleep(0.05)

    await progress.edit_text(
        "✅ Broadcast Finished\n\n"
        f"📤 Sent: {broadcast_state['sent']}\n"
        f"❌ Failed: {broadcast_state['failed']}"
    )

# ================= ADMIN =================
async def add_credit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update.effective_user.id):
        uid, amt = map(int, context.args)
        users.update_one({"_id": uid}, {"$inc": {"credits": amt}}, upsert=True)
        await update.message.reply_text("✅ Credits added")

async def unlimited(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update.effective_user.id):
        uid = int(context.args[0])
        users.update_one({"_id": uid}, {"$set": {"unlimited": True}})
        await update.message.reply_text("✅ Unlimited enabled")

# ================= MAIN =================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("broadcast", broadcast_start))
    app.add_handler(CommandHandler("add", add_credit))
    app.add_handler(CommandHandler("unlimited", unlimited))

    app.add_handler(
        MessageHandler(filters.TEXT | filters.PHOTO, broadcast_content),
        group=0
    )

    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, search_handler),
        group=1
    )

    app.job_queue.run_daily(
        daily_credit_job,
        time=time(9, 0, tzinfo=IST)
    )

    app.run_polling()

if __name__ == "__main__":
    main()
