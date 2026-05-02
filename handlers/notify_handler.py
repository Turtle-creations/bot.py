from telegram import Update
from telegram.ext import ContextTypes
import json
import os

from config import ADMINS

FILE = "data/notifications.json"

# ---------------- SAVE NOTIFICATION ----------------
def save_notification(message):
    data = {"message": message}

    os.makedirs("data", exist_ok=True)

    with open(FILE, "w") as f:
        json.dump(data, f)


# ---------------- GET NOTIFICATION ----------------
def get_notification():

    if not os.path.exists(FILE):
        return None

    with open(FILE, "r") as f:
        data = json.load(f)

    return data.get("message")


# ---------------- /notify COMMAND ----------------
async def notify_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.message.from_user.id

    if user_id not in ADMINS:
        await update.message.reply_text("❌ You are not admin")
        return

    # ✅ enable notify mode
    context.user_data["notify_mode"] = True

    await update.message.reply_text("📢 Send notification message")


# ---------------- HANDLE TEXT ----------------
async def notify_text(update: Update, context: ContextTypes.DEFAULT_TYPE):

    # ❌ run only in notify mode
    if not context.user_data.get("notify_mode"):
        return

    text = update.message.text

    save_notification(text)

    # ✅ reset mode
    context.user_data["notify_mode"] = False

    await update.message.reply_text("✅ Notification updated")
