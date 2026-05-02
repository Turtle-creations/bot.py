<<<<<<< HEAD
from telegram import InlineKeyboardMarkup, InlineKeyboardButton


# -------- EXAM KEYBOARD --------
def exam_keyboard(exams, prefix="exam"):

    buttons = []

    for e in exams:
        buttons.append([
            InlineKeyboardButton(
                text=e["name"],
                callback_data=f"{prefix}|{e['name']}"
            )
        ])

    return InlineKeyboardMarkup(buttons)


# -------- SET KEYBOARD --------
def set_keyboard(sets, prefix="set"):

    buttons = []

    for s in sets:
        buttons.append([
            InlineKeyboardButton(
                text=s["name"],
                callback_data=f"{prefix}|{s['name']}"
            )
        ])

    return InlineKeyboardMarkup(buttons)


# -------- QUESTION COUNT --------
def question_count_keyboard():

    buttons = [
        [
            
            InlineKeyboardButton("20", callback_data="quiz_count|20")
        ],
        [
            InlineKeyboardButton("50", callback_data="quiz_count|50"),
            InlineKeyboardButton("100", callback_data="quiz_count|100")
        ]
    ]

=======
from telegram import InlineKeyboardMarkup, InlineKeyboardButton


# -------- EXAM KEYBOARD --------
def exam_keyboard(exams, prefix="exam"):

    buttons = []

    for e in exams:
        buttons.append([
            InlineKeyboardButton(
                text=e["name"],
                callback_data=f"{prefix}|{e['name']}"
            )
        ])

    return InlineKeyboardMarkup(buttons)


# -------- SET KEYBOARD --------
def set_keyboard(sets, prefix="set"):

    buttons = []

    for s in sets:
        buttons.append([
            InlineKeyboardButton(
                text=s["name"],
                callback_data=f"{prefix}|{s['name']}"
            )
        ])

    return InlineKeyboardMarkup(buttons)


# -------- QUESTION COUNT --------
def question_count_keyboard():

    buttons = [
        [
            
            InlineKeyboardButton("20", callback_data="quiz_count|20")
        ],
        [
            InlineKeyboardButton("50", callback_data="quiz_count|50"),
            InlineKeyboardButton("100", callback_data="quiz_count|100")
        ]
    ]

>>>>>>> 72286ff2e6294b7e17af827ebd9e336761c26627
    return InlineKeyboardMarkup(buttons)