from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from keyboards.app_keyboards import back_to_main_keyboard, exam_keyboard, main_menu_keyboard
from handlers.support_v1 import cancel_support_flow, start_support_flow
from services.exam_service_db import exam_service
from services.user_service_db import user_service
from utils.formatters import format_help_text, format_leaderboard, format_profile
from utils.logging_utils import get_logger


logger = get_logger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = user_service.ensure_user(update.effective_user)
    has_admin_access = user_service.is_admin(user["user_id"])
    logger.info(
        "Start command admin check | current_user_id=%s is_admin=%s",
        user["user_id"],
        has_admin_access,
    )

    await update.effective_message.reply_text(
        (
            "<b>🎯 Welcome to Quiz Bot</b>\n\n"
            "Practice exam sets, track your score, generate PDFs, and manage premium access from one place."
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_keyboard(has_admin_access),
    )


async def menu_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = user_service.ensure_user(query.from_user)
    has_admin_access = user_service.is_admin(user["user_id"])
    data = query.data

    if data == "menu:main":
        await query.message.reply_text(
            "<b>🏠 Main Menu</b>\nChoose an option below.",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu_keyboard(has_admin_access),
        )
        return

    if data == "menu:quiz":
        exams = exam_service.get_exams()
        if not exams:
            await query.message.reply_text(
                "⚠️ No exams are available right now.",
                reply_markup=back_to_main_keyboard(),
            )
            return

        await query.message.reply_text(
            "<b>🎯 Select an exam</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=exam_keyboard(exams),
        )
        return

    if data == "profile:view":
        await query.message.reply_text(
            format_profile(user),
            parse_mode=ParseMode.HTML,
            reply_markup=back_to_main_keyboard(),
        )
        return

    if data == "leaderboard:view":
        await query.message.reply_text(
            format_leaderboard(user_service.get_leaderboard()),
            parse_mode=ParseMode.HTML,
            reply_markup=back_to_main_keyboard(),
        )
        return

    if data == "help:view":
        await query.message.reply_text(
            format_help_text(),
            parse_mode=ParseMode.HTML,
            reply_markup=back_to_main_keyboard(),
        )
        return

    if data == "support:start":
        await start_support_flow(query.message, context)
        return

    if data == "support:cancel":
        await cancel_support_flow(query.message, context)
        return
