# -*- coding: utf-8 -*-

import html

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from keyboards.app_keyboards import back_to_main_keyboard, support_cancel_keyboard
from services.support_service_db import support_service
from services.user_service_db import now_iso, user_service
from utils.logging_utils import get_logger


logger = get_logger(__name__)


def _set_support_mode(context: ContextTypes.DEFAULT_TYPE, enabled: bool):
    if enabled:
        context.user_data["support_mode"] = True
    else:
        context.user_data.pop("support_mode", None)


async def start_support_flow(message, context: ContextTypes.DEFAULT_TYPE):
    _set_support_mode(context, True)
    await message.reply_text(
        (
            "<b>Customer Support</b>\n\n"
            "Please send your problem or question. Our support team will receive it."
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=support_cancel_keyboard(),
    )


async def cancel_support_flow(message, context: ContextTypes.DEFAULT_TYPE):
    _set_support_mode(context, False)
    await message.reply_text(
        "Support request cancelled.",
        reply_markup=back_to_main_keyboard(),
    )


async def support_text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.effective_message:
        return

    user = user_service.ensure_user(update.effective_user)
    message = update.effective_message
    text = (message.text or "").strip()
    if not text:
        return

    logger.info(
        "Support text router received | user_id=%s support_mode=%s admin_mode=%s question_wizard=%s text=%s",
        user["user_id"],
        bool(context.user_data.get("support_mode")),
        context.user_data.get("admin_mode"),
        bool(context.user_data.get("question_wizard")),
        text,
    )

    if user_service.is_admin(user["user_id"]):
        if user["user_id"] not in support_service.get_support_admin_ids():
            return
        if context.user_data.get("admin_mode") or context.user_data.get("question_wizard"):
            return
        notification_wizard = context.user_data.get("notification_wizard")
        if notification_wizard and notification_wizard.get("step") == "message":
            return

        reply_to = message.reply_to_message
        if not reply_to:
            return

        ticket = support_service.get_ticket_by_admin_message(message.chat_id, reply_to.message_id)
        if not ticket:
            ticket_id = support_service.extract_ticket_id_from_text(reply_to.text or reply_to.caption)
            if ticket_id:
                ticket = support_service.get_ticket_by_id(ticket_id)
        if not ticket:
            return

        await context.bot.send_message(
            chat_id=ticket["user_id"],
            text=(
                "<b>Support Team Reply</b>\n\n"
                f"{html.escape(text)}"
            ),
            parse_mode=ParseMode.HTML,
        )
        support_service.mark_replied(ticket["support_id"], text)
        await message.reply_text("Support reply sent to the user.")
        logger.info(
            "Support reply delivered | support_id=%s user_id=%s admin_id=%s",
            ticket["support_id"],
            ticket["user_id"],
            user["user_id"],
        )
        return

    if not context.user_data.get("support_mode"):
        return

    if text.lower() == "cancel":
        await cancel_support_flow(message, context)
        return

    support_id = support_service.create_ticket(user, text)
    admin_chat_ids = support_service.get_support_admin_ids()
    timestamp = now_iso()
    logger.info(
        "support_message_received | support_id=%s user_id=%s admin_targets=%s",
        support_id,
        user["user_id"],
        len(admin_chat_ids),
    )
    admin_text = (
        "<b>New Customer Support Message</b>\n\n"
        f"<b>Ticket ID:</b> {support_id}\n"
        f"<b>User ID:</b> {user['user_id']}\n"
        f"<b>Username:</b> {html.escape(user.get('username') or 'N/A')}\n"
        f"<b>Full Name:</b> {html.escape(user.get('full_name') or 'N/A')}\n"
        f"<b>Timestamp:</b> {html.escape(timestamp)}\n\n"
        f"<b>Message:</b>\n{html.escape(text)}\n\n"
        "Reply to this message to answer the user through the bot."
    )

    first_forwarded = False
    for admin_chat_id in admin_chat_ids:
        try:
            admin_message = await context.bot.send_message(
                chat_id=admin_chat_id,
                text=admin_text,
                parse_mode=ParseMode.HTML,
            )
            if not first_forwarded:
                support_service.attach_admin_message(support_id, admin_chat_id, admin_message.message_id)
                first_forwarded = True
            logger.info(
                "support_message_forwarded_to_admin | support_id=%s user_id=%s admin_chat_id=%s",
                support_id,
                user["user_id"],
                admin_chat_id,
            )
        except Exception:
            logger.exception(
                "support_message_forward_failed | support_id=%s user_id=%s admin_chat_id=%s",
                support_id,
                user["user_id"],
                admin_chat_id,
            )

    if not admin_chat_ids:
        logger.warning("Support ticket not forwarded | support_id=%s reason=no_admin_configured", support_id)

    _set_support_mode(context, False)
    await message.reply_text(
        "✅ Your message has been sent to support.",
        reply_markup=back_to_main_keyboard(),
    )
