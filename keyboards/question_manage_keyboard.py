<<<<<<< HEAD
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def question_manage_keyboard():
    keyboard = [
        [InlineKeyboardButton("📄 View Questions", callback_data="view_questions")],
        [InlineKeyboardButton("❌ Delete Question", callback_data="delete_question")]
    ]
=======
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def question_manage_keyboard():
    keyboard = [
        [InlineKeyboardButton("📄 View Questions", callback_data="view_questions")],
        [InlineKeyboardButton("❌ Delete Question", callback_data="delete_question")]
    ]
>>>>>>> 72286ff2e6294b7e17af827ebd9e336761c26627
    return InlineKeyboardMarkup(keyboard)