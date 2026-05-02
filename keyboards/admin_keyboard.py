from telegram import InlineKeyboardMarkup, InlineKeyboardButton

def admin_menu():

    keyboard = [

        [InlineKeyboardButton("➕ Add Exam", callback_data="add_exam")],
        [InlineKeyboardButton("📄 View Exams", callback_data="view_exams")],
        [InlineKeyboardButton("🗑 Delete Exam", callback_data="delete_exam")],

        [InlineKeyboardButton("➕ Add Set", callback_data="add_set")],
        [InlineKeyboardButton("📄 View Sets", callback_data="view_sets")],
        [InlineKeyboardButton("🗑 Delete Set", callback_data="delete_set")],

        # ✅ FIX HERE (comma added)
        [
            InlineKeyboardButton("➕ Add Question", callback_data="add_question"),
            InlineKeyboardButton("📄 View Questions", callback_data="view_questions")
        ],

        [InlineKeyboardButton("🗑 Delete Question", callback_data="delete_question")],
        [InlineKeyboardButton("💎 Grant Premium", callback_data="grant_premium")],
        [InlineKeyboardButton("📋 View Premium Users", callback_data="view_premium")]

    ]

    return InlineKeyboardMarkup(keyboard)
