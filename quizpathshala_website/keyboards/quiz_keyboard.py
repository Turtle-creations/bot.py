<<<<<<< HEAD
from telegram import InlineKeyboardMarkup, InlineKeyboardButton


# -------- QUESTION OPTIONS KEYBOARD --------

def question_keyboard(options):

    keyboard = []

    for opt in options:
        keyboard.append([
            InlineKeyboardButton(opt, callback_data=f"ans|{opt}")
        ])

    return InlineKeyboardMarkup(keyboard)


# -------- QUESTION COUNT KEYBOARD --------

def question_count_keyboard():

    keyboard = [
        [
            InlineKeyboardButton("10", callback_data="quiz_count|10"),
            InlineKeyboardButton("20", callback_data="quiz_count|20")
        ],
        [
            InlineKeyboardButton("50", callback_data="quiz_count|50"),
            InlineKeyboardButton("100", callback_data="quiz_count|100")
        ]
    ]

    return InlineKeyboardMarkup(keyboard)

    #----------------new start stop keyboard-----------------
def control_keyboard():
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton

    keyboard = [
        [
            InlineKeyboardButton("⏸ Pause", callback_data="quiz_pause"),
            InlineKeyboardButton("▶ Resume", callback_data="quiz_resume")
        ]
    ]

=======
from telegram import InlineKeyboardMarkup, InlineKeyboardButton


# -------- QUESTION OPTIONS KEYBOARD --------

def question_keyboard(options):

    keyboard = []

    for opt in options:
        keyboard.append([
            InlineKeyboardButton(opt, callback_data=f"ans|{opt}")
        ])

    return InlineKeyboardMarkup(keyboard)


# -------- QUESTION COUNT KEYBOARD --------

def question_count_keyboard():

    keyboard = [
        [
            InlineKeyboardButton("10", callback_data="quiz_count|10"),
            InlineKeyboardButton("20", callback_data="quiz_count|20")
        ],
        [
            InlineKeyboardButton("50", callback_data="quiz_count|50"),
            InlineKeyboardButton("100", callback_data="quiz_count|100")
        ]
    ]

    return InlineKeyboardMarkup(keyboard)

    #----------------new start stop keyboard-----------------
def control_keyboard():
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton

    keyboard = [
        [
            InlineKeyboardButton("⏸ Pause", callback_data="quiz_pause"),
            InlineKeyboardButton("▶ Resume", callback_data="quiz_resume")
        ]
    ]

>>>>>>> 72286ff2e6294b7e17af827ebd9e336761c26627
    return InlineKeyboardMarkup(keyboard)