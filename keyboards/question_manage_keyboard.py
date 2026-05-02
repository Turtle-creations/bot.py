from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def question_manage_keyboard():
    keyboard = [
        [InlineKeyboardButton("📄 View Questions", callback_data="view_questions")],
        [InlineKeyboardButton("❌ Delete Question", callback_data="delete_question")]
    ]
    return InlineKeyboardMarkup(keyboard)