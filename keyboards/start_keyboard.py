from telegram import InlineKeyboardMarkup, InlineKeyboardButton

def start_menu():

    keyboard = [
        [InlineKeyboardButton("🎯 Start Quiz", callback_data="start_quiz")],

        [
            InlineKeyboardButton("👤 Profile", callback_data="profile"),
            InlineKeyboardButton("🏆 Leaderboard", callback_data="leaderboard")
        ],

        [InlineKeyboardButton("📢 Updates", callback_data="updates&notifications")],
        [InlineKeyboardButton("💎 Premium", callback_data="premium")],
        [InlineKeyboardButton("📄 PDFs", callback_data="pdfs")]
    ]

    return InlineKeyboardMarkup(keyboard)