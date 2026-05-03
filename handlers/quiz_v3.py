# -*- coding: utf-8 -*-

import asyncio
import html

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from config import BASE_DIR
from keyboards.app_keyboards import exam_keyboard, question_count_keyboard, quiz_question_keyboard, set_keyboard
from services.exam_service_db import exam_service
from services.premium_service_db import premium_service
from services.quiz_service_runtime import quiz_service
from services.user_service_db import user_service
from utils.formatters import format_question_text, resolve_image_path
from utils.logging_utils import get_logger


logger = get_logger(__name__)


async def quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_service.ensure_user(update.effective_user)
    exams = exam_service.get_exams()

    if not exams:
        await update.effective_message.reply_text("⚠️ No exams are available right now.")
        return

    await update.effective_message.reply_text(
        "<b>🎯 Select an exam</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=exam_keyboard(exams),
    )


async def quiz_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = user_service.ensure_user(query.from_user)

    parts = query.data.split(":")
    action = parts[1]

    if action == "noop":
        return

    if action == "exam":
        exam_id = int(parts[2])
        sets_ = exam_service.get_sets(exam_id)
        if not sets_:
            await query.message.reply_text("⚠️ No sets are available for this exam.")
            return

        await query.message.reply_text(
            "<b>🎯 Select a set</b>",
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
                "⚠️ Unable to start quiz. Please make sure the set contains questions."
            )
            return

        await query.message.reply_text(
            "<b>🎯 Select question count</b>",
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
                "⚠️ Unable to start quiz. Please make sure the set contains questions."
            )
            return

        logger.info("Question loaded | user_id=%s initial_load=1", user["user_id"])
        await _send_current_question(query.message, user["user_id"], context)
        return

    current = quiz_service.get_current_question(user["user_id"])
    session = quiz_service.get_session(user["user_id"])
    if not current or not session:
        await query.message.reply_text("⚠️ No active quiz session found.")
        return

    if action in {"pick", "skip", "pause", "resume", "end"}:
        question_id = int(parts[2])
        question_token = parts[3]
        if not quiz_service.validate_question_callback(
            user["user_id"],
            question_id=question_id,
            question_token=question_token,
            message_id=query.message.message_id,
        ):
            return

    if action == "pick":
        selected_index = int(parts[4])
        if not quiz_service.mark_callback_processed(
            user["user_id"],
            action_key=f"pick:{question_id}:{question_token}:{selected_index}",
        ):
            return
        await complete_question(
            context,
            user["user_id"],
            action="answer",
            selected_index=selected_index,
        )
        return

    if action == "skip":
        if not quiz_service.mark_callback_processed(
            user["user_id"],
            action_key=f"skip:{question_id}:{question_token}",
        ):
            return
        await complete_question(context, user["user_id"], action="skip")
        return

    if action == "pause":
        if not quiz_service.mark_callback_processed(
            user["user_id"],
            action_key=f"pause:{question_id}:{question_token}",
        ):
            return

        ok, feedback = quiz_service.pause_quiz(user["user_id"])
        if not ok:
            return

        await _render_question(context, user["user_id"], extra_feedback=feedback)
        return

    if action == "resume":
        if not quiz_service.mark_callback_processed(
            user["user_id"],
            action_key=f"resume:{question_id}:{question_token}",
        ):
            return

        ok, feedback = quiz_service.resume_quiz(user["user_id"])
        if not ok:
            return

        await _render_question(context, user["user_id"], extra_feedback=feedback)
        _start_countdown(context, user["user_id"])
        return

    if action == "end":
        if not quiz_service.mark_callback_processed(
            user["user_id"],
            action_key=f"end:{question_id}:{question_token}",
        ):
            return
        summary = quiz_service.end_quiz(user["user_id"])
        if not summary:
            return
        await _send_summary_to_chat(context, session["question_chat_id"], summary, "❌ Quiz ended.")


async def _send_current_question(message, user_id: int, context: ContextTypes.DEFAULT_TYPE):
    await _render_new_question(message, user_id, context)
    _start_countdown(context, user_id)


async def _render_new_question(message, user_id: int, context: ContextTypes.DEFAULT_TYPE):
    question = quiz_service.get_current_question(user_id)
    session = quiz_service.get_session(user_id)

    if not question or not session:
        summary = quiz_service.close_session(user_id, "completed")
        await _send_summary(message, summary)
        return

    index, total = quiz_service.session_progress(user_id)
    await message.reply_text(
        format_question_text(question, index, total),
        parse_mode=ParseMode.HTML,
    )

    image_path = resolve_image_path(question.get("image_path"), BASE_DIR)
    if image_path:
        try:
            with image_path.open("rb") as image_stream:
                image_message = await message.reply_photo(photo=image_stream)
            quiz_service.set_image_message(user_id, image_message.message_id)
        except Exception:
            quiz_service.set_image_message(user_id, None)
    else:
        quiz_service.set_image_message(user_id, None)

    question_message = await message.reply_text(
        _question_message_text(quiz_service.remaining_seconds(user_id)),
        parse_mode=ParseMode.HTML,
        reply_markup=quiz_question_keyboard(
            question["options"],
            question["question_id"],
            session["active_question_token"],
        ),
    )
    quiz_service.set_question_message(user_id, question_message.chat_id, question_message.message_id)


async def _send_current_question_by_chat(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int,
):
    question = quiz_service.get_current_question(user_id)
    session = quiz_service.get_session(user_id)
    if not question or not session:
        return

    index, total = quiz_service.session_progress(user_id)
    await context.bot.send_message(
        chat_id=chat_id,
        text=format_question_text(question, index, total),
        parse_mode=ParseMode.HTML,
    )

    image_path = resolve_image_path(question.get("image_path"), BASE_DIR)
    if image_path:
        try:
            with image_path.open("rb") as image_stream:
                image_message = await context.bot.send_photo(chat_id=chat_id, photo=image_stream)
            quiz_service.set_image_message(user_id, image_message.message_id)
        except Exception:
            quiz_service.set_image_message(user_id, None)
    else:
        quiz_service.set_image_message(user_id, None)

    question_message = await context.bot.send_message(
        chat_id=chat_id,
        text=_question_message_text(quiz_service.remaining_seconds(user_id)),
        parse_mode=ParseMode.HTML,
        reply_markup=quiz_question_keyboard(
            question["options"],
            question["question_id"],
            session["active_question_token"],
        ),
    )
    quiz_service.set_question_message(user_id, question_message.chat_id, question_message.message_id)


async def _render_question(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    *,
    extra_feedback: str | None = None,
):
    session = quiz_service.get_session(user_id)
    question = quiz_service.get_current_question(user_id)
    if not session or not question:
        return

    text = _question_message_text(quiz_service.remaining_seconds(user_id), extra_feedback=extra_feedback)
    try:
        await context.bot.edit_message_text(
            chat_id=session["question_chat_id"],
            message_id=session["question_message_id"],
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=quiz_question_keyboard(
                question["options"],
                question["question_id"],
                session["active_question_token"],
                paused=session.get("paused", False),
            ),
        )
    except Exception:
        return


async def _render_locked_question(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    feedback: str,
    correct_answer: str,
):
    session = quiz_service.get_session(user_id)
    if not session:
        return

    text = _question_message_text(
        0,
        extra_feedback=_completion_feedback_text(feedback, correct_answer),
    )
    try:
        # Keep the question text message above visible, but remove action buttons
        # from the control message once the question is completed.
        await context.bot.edit_message_text(
            chat_id=session["question_chat_id"],
            message_id=session["question_message_id"],
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=None,
        )
    except Exception:
        return


def _start_countdown(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    session = quiz_service.get_session(user_id)
    if not session:
        return
    task = asyncio.create_task(_countdown_loop(context, user_id, session["active_question_token"]))
    quiz_service.set_countdown_task(user_id, task)


async def _countdown_loop(context: ContextTypes.DEFAULT_TYPE, user_id: int, question_token: str):
    last_value = None
    try:
        while True:
            session = quiz_service.get_session(user_id)
            question = quiz_service.get_current_question(user_id)
            if not session or not question:
                return
            if session.get("active_question_token") != question_token:
                return
            if session.get("paused") or session.get("question_locked"):
                return

            remaining = quiz_service.remaining_seconds(user_id)
            if remaining != last_value:
                await _render_question(context, user_id)
                last_value = remaining

            if remaining <= 0:
                await complete_question(
                    context,
                    user_id,
                    action="timeout",
                    expected_question_token=question_token,
                )
                return

            await asyncio.sleep(1)
    except asyncio.CancelledError:
        return


async def complete_question(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    *,
    action: str,
    selected_index: int | None = None,
    expected_question_token: str | None = None,
):
    session = quiz_service.get_session(user_id)
    if not session:
        return
    if expected_question_token and session.get("active_question_token") != expected_question_token:
        return

    result = quiz_service.complete_question(
        user_id,
        action=action,
        selected_index=selected_index,
    )
    if not result:
        return

    await _render_locked_question(
        context,
        user_id,
        result["feedback"],
        result["correct_answer"],
    )

    delay_seconds = 1.5 if action == "answer" else 1.0
    quiz_service.set_advance_task(
        user_id,
        asyncio.create_task(
            load_next_question(
                context,
                user_id,
                expected_question_token=result["question_token"],
                delay_seconds=delay_seconds,
            )
        ),
    )


async def load_next_question(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    *,
    expected_question_token: str | None = None,
    delay_seconds: float = 0,
):
    try:
        session = quiz_service.get_session(user_id)
        current_task = asyncio.current_task()
        if session:
            advance_task = session.get("advance_task")
            if advance_task and advance_task is not current_task and not advance_task.done():
                advance_task.cancel()
            session["advance_task"] = None

        if delay_seconds:
            await asyncio.sleep(delay_seconds)

        session = quiz_service.get_session(user_id)
        if not session:
            return
        if expected_question_token and session.get("active_question_token") != expected_question_token:
            return
        if not session.get("question_locked"):
            return

        logger.info("Next question triggered | user_id=%s source=shared_loader", user_id)
        await _advance_to_next_question(context, user_id)
    except asyncio.CancelledError:
        return


async def _advance_to_next_question(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    session = quiz_service.get_session(user_id)
    if not session:
        return

    chat_id = session["question_chat_id"]
    next_exists = quiz_service.move_to_next_question(user_id)
    if next_exists:
        logger.info("Question loaded | user_id=%s next_question=1", user_id)
        await _send_current_question_by_chat(context, chat_id, user_id)
        _start_countdown(context, user_id)
    else:
        summary = quiz_service.close_session(user_id, "completed")
        await _send_summary_by_chat(context, chat_id, summary)


async def _send_summary(message, summary: dict):
    await message.reply_text(
        _summary_text("🏁 Quiz finished", summary),
        parse_mode=ParseMode.HTML,
    )


async def _send_summary_by_chat(context: ContextTypes.DEFAULT_TYPE, chat_id: int, summary: dict):
    await context.bot.send_message(
        chat_id=chat_id,
        text=_summary_text("🏁 Quiz finished", summary),
        parse_mode=ParseMode.HTML,
    )


async def _send_summary_to_chat(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    summary: dict,
    title: str,
):
    await context.bot.send_message(
        chat_id=chat_id,
        text=_summary_text(title, summary),
        parse_mode=ParseMode.HTML,
    )


def _question_message_text(
    remaining_seconds: int,
    *,
    extra_feedback: str | None = None,
) -> str:
    parts = ["<b>Choose one option.</b>", f"⏳ {remaining_seconds}s left"]
    if extra_feedback:
        parts.extend(["", extra_feedback])
    return "\n".join(parts)


def _completion_feedback_text(feedback: str, correct_answer: str) -> str:
    return (
        f"{feedback}\n"
        f"<b>Correct answer:</b> {html.escape(correct_answer)}"
    )


def _summary_text(title: str, summary: dict) -> str:
    return (
        f"<b>{title}</b>\n\n"
        f"<b>Score:</b> {summary['score']:.2f}\n"
        f"<b>Accuracy:</b> {summary['accuracy']:.2f}%\n"
        f"<b>✅ Correct answers:</b> {summary['correct']}\n"
        f"<b>❌ Wrong answers:</b> {summary['wrong']}\n"
        f"<b>Negative marking applied:</b> -{summary['negative_marking']:.2f}"
    )
