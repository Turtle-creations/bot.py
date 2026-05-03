<<<<<<< HEAD
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

=======
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

>>>>>>> 72286ff2e6294b7e17af827ebd9e336761c26627
    return InlineKeyboardMarkup(keyboard)