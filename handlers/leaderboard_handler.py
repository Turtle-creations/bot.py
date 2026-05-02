from telegram import Update
from telegram.ext import ContextTypes

from services.user_service import get_top_users, get_badge


async def leaderboard_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    users = get_top_users(10)

    if not users:
        await update.message.reply_text("⚠ No users yet")
        return

    msg = "🏆 Leaderboard (Top 10)\n\n"

    for i, u in enumerate(users, 1):

        badge = get_badge(u["score"])

        msg += (
            f"{i}. {u['name']} - {u['score']} pts {badge}\n"
        )

    await update.message.reply_text(msg)