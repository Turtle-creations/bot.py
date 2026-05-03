from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from config import BASE_DIR
from keyboards.app_keyboards import answer_keyboard, exam_keyboard, question_count_keyboard, set_keyboard
from services.exam_service_db import exam_service
from services.premium_service_db import premium_service
from services.quiz_service_runtime import quiz_service
from services.user_service_db import user_service
from utils.formatters import format_question_text, resolve_image_path


async def quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_service.ensure_user(update.effective_user)
    exams = exam_service.get_exams()

    if not exams:
        await update.effective_message.reply_text("No exams are available right now.")
        return

    await update.effective_message.reply_text(
        "<b>Select an exam</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=exam_keyboard(exams),
    )


async def quiz_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = user_service.ensure_user(query.from_user)

    parts = query.data.split(":")
    action = parts[1]

    if action == "exam":
        exam_id = int(parts[2])
        sets_ = exam_service.get_sets(exam_id)
        if not sets_:
            await query.message.reply_text("No sets are available for this exam.")
            return

        await query.message.reply_text(
            "<b>Select a set</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=set_keyboard(
                exam_id,
                sets_,
                show_lock_icons=not (
                    premium_service.is_premium(user["user_id"]) or user_service.is_admin(user["user_id"])
                ),
            ),
        )
        return

    if action == "set":
        exam_id = int(parts[2])
        set_id = int(parts[3])
        if not quiz_service.can_access_set(user["user_id"], set_id):
            await query.message.reply_text(
                "This set is available for premium users only. Please upgrade to access."
            )
            return

        total_questions = len(exam_service.get_questions(set_id))
        counts = quiz_service.get_available_question_counts(user, total_questions)
        if not counts:
            await query.message.reply_text(
                "Unable to start quiz. Please make sure the set contains questions."
            )
            return

        await query.message.reply_text(
            "<b>Select question count</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=question_count_keyboard(counts, exam_id, set_id),
        )
        return

    if action == "count":
        set_id = int(parts[3])
        count = int(parts[4])
        if not quiz_service.can_access_set(user["user_id"], set_id):
            await query.message.reply_text(
                "This set is available for premium users only. Please upgrade to access."
            )
            return

        session = quiz_service.start_session(user["user_id"], set_id, count)

        if not session:
            await query.message.reply_text(
                "Unable to start quiz. Please make sure the set contains questions."
            )
            return

        await _send_current_question(query.message, user["user_id"])
        return

    if action == "answer":
        question_id = int(parts[2])
        selected = parts[3]
        current = quiz_service.get_current_question(user["user_id"])

        if not current or current["question_id"] != question_id:
            await query.message.reply_text("This question is no longer active.")
            return

        result = quiz_service.answer_question(user["user_id"], selected)
        if not result:
            await query.message.reply_text("No active quiz session found.")
            return

        correct, correct_option = result

        if correct:
            await query.message.reply_text("Correct answer. +1 point")
        else:
            await query.message.reply_text(f"Wrong answer. Correct option: {correct_option}")

        await _send_current_question(query.message, user["user_id"])


async def _send_current_question(message, user_id: int):
    question = quiz_service.get_current_question(user_id)

    if not question:
        user = user_service.get_user(user_id)
        quiz_service.finish_session(user_id)
        await message.reply_text(
            (
                "<b>Quiz finished</b>\n\n"
                f"<b>Score:</b> {user['score']:.2f}\n"
                f"<b>Correct:</b> {user['correct_answers']}\n"
                f"<b>Wrong:</b> {user['wrong_answers']}"
            ),
            parse_mode=ParseMode.HTML,
        )
        return

    index, total = quiz_service.session_progress(user_id)
    text = format_question_text(question, index, total)
    image_path = resolve_image_path(question.get("image_path"), BASE_DIR)

    if image_path:
        with image_path.open("rb") as image_stream:
            await message.reply_photo(
                photo=image_stream,
                caption=text,
                parse_mode=ParseMode.HTML,
                reply_markup=answer_keyboard(question["question_id"]),
            )
    else:
        await message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=answer_keyboard(question["question_id"]),
        )
