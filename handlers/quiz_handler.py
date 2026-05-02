<<<<<<< HEAD
from telegram import Update
from telegram.ext import ContextTypes
import asyncio
import random

from services.quiz_service import (
    start_quiz,
    get_current_question,
    check_answer,
    is_time_over,
    next_question,
    user_sessions
)

from services.exam_service import get_exam_id_by_name, get_all_exams
from services.set_service import get_sets

from keyboards.quiz_select_keyboard import (
    exam_keyboard,
    set_keyboard,
    question_count_keyboard
)
from keyboards.quiz_keyboard import question_keyboard
from utils.helpers import is_double_click

# -------- START QUIZ --------
async def start_quiz_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    exams = get_all_exams()

    if not exams:
        await update.message.reply_text("⚠ No exams available")
        return

    await update.message.reply_text(
        "📚 Select Exam:",
        reply_markup=exam_keyboard(exams)
    )

# -------- EXAM SELECT --------
async def exam_select_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    exam_name = query.data.split("|")[1]
    context.user_data["exam_name"] = exam_name

    exam_id = get_exam_id_by_name(exam_name)
    sets = get_sets(exam_id)

    if not sets:
        await query.message.reply_text("⚠ No sets found")
        return

    await query.message.reply_text(
        f"📂 {exam_name} → Select Set:",
        reply_markup=set_keyboard(sets)
    )

# -------- SET SELECT --------
async def set_select_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    set_name = query.data.split("|")[1]
    context.user_data["set_name"] = set_name

    await query.message.reply_text(
        "📊 Select number of questions:",
        reply_markup=question_count_keyboard()
    )

# -------- QUESTION COUNT --------
async def question_count_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    count = int(query.data.split("|")[1])
    context.user_data["question_limit"] = count

    await query.message.reply_text(
        f"✅ {count} questions selected\n\nStarting quiz..."
    )

    await start_quiz_dynamic(update, context)

# -------- START QUIZ --------
async def start_quiz_dynamic(update, context):

    user_id = update.effective_user.id

    exam_name = context.user_data.get("exam_name")
    set_name = context.user_data.get("set_name")

    if not exam_name or not set_name:
        await update.effective_message.reply_text("❌ Please select exam & set first")
        return

    exam_id = get_exam_id_by_name(exam_name)
    sets = get_sets(exam_id)

    selected_set = None
    for s in sets:
        if s["name"].lower() == set_name.lower():
            selected_set = s

    if not selected_set:
        await update.effective_message.reply_text("❌ Set not found")
        return

    all_questions = selected_set.get("questions", [])

    if not all_questions:
        await update.effective_message.reply_text("⚠ No questions found")
        return

    limit = context.user_data.get("question_limit", 10)

    questions = random.sample(
        all_questions,
        min(limit, len(all_questions))
    )

    start_quiz(user_id, questions)

    await send_question(update, context)

# -------- SEND QUESTION --------
async def send_question(update, context):

    user_id = update.effective_user.id
    message = update.effective_message

    q = get_current_question(user_id)

    if not q:
        session = user_sessions[user_id]

        await message.reply_text(
            f"""🏁 Finished!

✅ Correct: {session['score']}
❌ Wrong: {session['wrong']}
📊 Total: {len(session['questions'])}
"""
        )
        return

    session = user_sessions[user_id]

    session["answered"] = False
    session["timer_running"] = True

    msg = await message.reply_text(
        f"⏱ {q.get('time',30)} sec\n\n❓ {q['question']}",
        reply_markup=question_keyboard(q["options"])
    )

    session["last_message"] = msg

    # 🔥 TIMER START
    asyncio.create_task(timer_checker(context, user_id))

# -------- TIMER --------
async def timer_checker(context, user_id):

    await asyncio.sleep(1)

    if user_id not in user_sessions:
        return

    session = user_sessions[user_id]

    if session.get("answered"):
        return

    if is_time_over(user_id):

        session["timer_running"] = False

        q = get_current_question(user_id)

        try:
            old_msg = session.get("last_message")
            if old_msg:
                await old_msg.edit_reply_markup(reply_markup=None)
        except:
            pass

        if q:
            await old_msg.reply_text(
                f"⏰ Time's up!\n\n✅ Correct: {q['answer']}"
            )

        next_question(user_id)

        await send_question(old_msg, context)

    else:
        await timer_checker(context, user_id)

# -------- ANSWER HANDLER (🔥 FIXED) --------
async def answer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    # 🔒 double click protection
    if is_double_click(context, "answer_click", 1):
        return

    user_id = query.from_user.id

    if user_id not in user_sessions:
        return

    session = user_sessions[user_id]

    # ❌ already answered
    if session.get("answered"):
        return

    if is_time_over(user_id):
        await query.message.reply_text("⏰ Time over! Answer ignored")
        return

    data = query.data

    if not data.startswith("ans|"):
        return

    selected = data.split("|")[1]

    correct, answer = check_answer(user_id, selected)

    # 🔥 STOP TIMER
    session["answered"] = True
    session["timer_running"] = False

    # 🔥 REMOVE BUTTONS
    try:
        old_msg = session.get("last_message")
        if old_msg:
            await old_msg.edit_reply_markup(reply_markup=None)
    except:
        pass

    if correct:
        await query.message.reply_text("✅ Correct (+1)")
    else:
        await query.message.reply_text(
            f"❌ Wrong (-0.25)\n\n✅ Correct: {answer}"
        )

    next_question(user_id)

=======
from telegram import Update
from telegram.ext import ContextTypes
import asyncio
import random

from services.quiz_service import (
    start_quiz,
    get_current_question,
    check_answer,
    is_time_over,
    next_question,
    user_sessions
)

from services.exam_service import get_exam_id_by_name, get_all_exams
from services.set_service import get_sets

from keyboards.quiz_select_keyboard import (
    exam_keyboard,
    set_keyboard,
    question_count_keyboard
)
from keyboards.quiz_keyboard import question_keyboard
from utils.helpers import is_double_click

# -------- START QUIZ --------
async def start_quiz_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    exams = get_all_exams()

    if not exams:
        await update.message.reply_text("⚠ No exams available")
        return

    await update.message.reply_text(
        "📚 Select Exam:",
        reply_markup=exam_keyboard(exams)
    )

# -------- EXAM SELECT --------
async def exam_select_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    exam_name = query.data.split("|")[1]
    context.user_data["exam_name"] = exam_name

    exam_id = get_exam_id_by_name(exam_name)
    sets = get_sets(exam_id)

    if not sets:
        await query.message.reply_text("⚠ No sets found")
        return

    await query.message.reply_text(
        f"📂 {exam_name} → Select Set:",
        reply_markup=set_keyboard(sets)
    )

# -------- SET SELECT --------
async def set_select_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    set_name = query.data.split("|")[1]
    context.user_data["set_name"] = set_name

    await query.message.reply_text(
        "📊 Select number of questions:",
        reply_markup=question_count_keyboard()
    )

# -------- QUESTION COUNT --------
async def question_count_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    count = int(query.data.split("|")[1])
    context.user_data["question_limit"] = count

    await query.message.reply_text(
        f"✅ {count} questions selected\n\nStarting quiz..."
    )

    await start_quiz_dynamic(update, context)

# -------- START QUIZ --------
async def start_quiz_dynamic(update, context):

    user_id = update.effective_user.id

    exam_name = context.user_data.get("exam_name")
    set_name = context.user_data.get("set_name")

    if not exam_name or not set_name:
        await update.effective_message.reply_text("❌ Please select exam & set first")
        return

    exam_id = get_exam_id_by_name(exam_name)
    sets = get_sets(exam_id)

    selected_set = None
    for s in sets:
        if s["name"].lower() == set_name.lower():
            selected_set = s

    if not selected_set:
        await update.effective_message.reply_text("❌ Set not found")
        return

    all_questions = selected_set.get("questions", [])

    if not all_questions:
        await update.effective_message.reply_text("⚠ No questions found")
        return

    limit = context.user_data.get("question_limit", 10)

    questions = random.sample(
        all_questions,
        min(limit, len(all_questions))
    )

    start_quiz(user_id, questions)

    await send_question(update, context)

# -------- SEND QUESTION --------
async def send_question(update, context):

    user_id = update.effective_user.id
    message = update.effective_message

    q = get_current_question(user_id)

    if not q:
        session = user_sessions[user_id]

        await message.reply_text(
            f"""🏁 Finished!

✅ Correct: {session['score']}
❌ Wrong: {session['wrong']}
📊 Total: {len(session['questions'])}
"""
        )
        return

    session = user_sessions[user_id]

    session["answered"] = False
    session["timer_running"] = True

    msg = await message.reply_text(
        f"⏱ {q.get('time',30)} sec\n\n❓ {q['question']}",
        reply_markup=question_keyboard(q["options"])
    )

    session["last_message"] = msg

    # 🔥 TIMER START
    asyncio.create_task(timer_checker(context, user_id))

# -------- TIMER --------
async def timer_checker(context, user_id):

    await asyncio.sleep(1)

    if user_id not in user_sessions:
        return

    session = user_sessions[user_id]

    if session.get("answered"):
        return

    if is_time_over(user_id):

        session["timer_running"] = False

        q = get_current_question(user_id)

        try:
            old_msg = session.get("last_message")
            if old_msg:
                await old_msg.edit_reply_markup(reply_markup=None)
        except:
            pass

        if q:
            await old_msg.reply_text(
                f"⏰ Time's up!\n\n✅ Correct: {q['answer']}"
            )

        next_question(user_id)

        await send_question(old_msg, context)

    else:
        await timer_checker(context, user_id)

# -------- ANSWER HANDLER (🔥 FIXED) --------
async def answer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    # 🔒 double click protection
    if is_double_click(context, "answer_click", 1):
        return

    user_id = query.from_user.id

    if user_id not in user_sessions:
        return

    session = user_sessions[user_id]

    # ❌ already answered
    if session.get("answered"):
        return

    if is_time_over(user_id):
        await query.message.reply_text("⏰ Time over! Answer ignored")
        return

    data = query.data

    if not data.startswith("ans|"):
        return

    selected = data.split("|")[1]

    correct, answer = check_answer(user_id, selected)

    # 🔥 STOP TIMER
    session["answered"] = True
    session["timer_running"] = False

    # 🔥 REMOVE BUTTONS
    try:
        old_msg = session.get("last_message")
        if old_msg:
            await old_msg.edit_reply_markup(reply_markup=None)
    except:
        pass

    if correct:
        await query.message.reply_text("✅ Correct (+1)")
    else:
        await query.message.reply_text(
            f"❌ Wrong (-0.25)\n\n✅ Correct: {answer}"
        )

    next_question(user_id)

>>>>>>> 72286ff2e6294b7e17af827ebd9e336761c26627
    await send_question(update, context)