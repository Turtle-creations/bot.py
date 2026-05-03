import os
import time
from threading import Thread

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    Defaults,
    MessageHandler,
    filters,
)
from zoneinfo import ZoneInfo

from config import TELEGRAM_TOKEN
from db.database import database
from handlers.admin_v3 import (
    admin_command,
    admin_callback_handler,
    admin_photo_handler,
    admin_text_router,
    check_admin_command,
)
from handlers.pdf_v2 import pdf_callback_handler
from handlers.premium_v2 import premium_status_command, subscribe_premium_handler
from handlers.quiz_v3 import quiz_callback_handler, quiz_command
from handlers.menu_v3 import menu_callback_handler, start_command
from handlers.support_v1 import support_text_router
from services.bootstrap_service import bootstrap_application
from services.notification_service_db import notification_service
from utils.logging_utils import get_logger, setup_logging
from webhook_server import app as webhook_app

logger = get_logger(__name__)
INDIA_TZ = ZoneInfo("Asia/Kolkata")


async def error_handler(update, context):
    logger.exception(
        "Unhandled error while processing update | update_id=%s update_type=%s effective_user_id=%s effective_chat_id=%s error=%r",
        getattr(update, "update_id", None),
        type(update).__name__ if update is not None else None,
        getattr(getattr(update, "effective_user", None), "id", None),
        getattr(getattr(update, "effective_chat", None), "id", None),
        context.error,
        exc_info=context.error,
    )


async def _log_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return

    logger.info(
        "Callback query received | update_id=%s user_id=%s chat_id=%s data=%s inline_message_id=%s",
        update.update_id,
        getattr(query.from_user, "id", None),
        getattr(getattr(query.message, "chat", None), "id", None),
        query.data,
        query.inline_message_id,
    )


async def _log_command_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message or not message.text:
        return

    logger.info(
        "Command received | update_id=%s user_id=%s chat_id=%s text=%s",
        update.update_id,
        getattr(update.effective_user, "id", None),
        getattr(update.effective_chat, "id", None),
        message.text,
    )


def _resolve_bot_token() -> str:
    token = os.environ.get("TOKEN") or os.environ.get("BOT_TOKEN") or TELEGRAM_TOKEN
    if not token:
        raise RuntimeError("Telegram bot token is missing.")
    return token


def _start_keep_alive_server():
    port = int(os.environ.get("PORT", "10000"))
    thread = Thread(
        target=webhook_app.run,
        kwargs={"host": "0.0.0.0", "port": port, "use_reloader": False},
        daemon=True,
    )
    thread.start()
    logger.info("Flask server started | host=0.0.0.0 port=%s", port)
    return thread


def build_application() -> Application:
    setup_logging()
    logger.info("Bot build start")
    database.initialize()
    bootstrap_application()

    application = (
        Application.builder()
        .token(_resolve_bot_token())
        .defaults(Defaults(tzinfo=INDIA_TZ))
        .build()
    )

    application.add_error_handler(error_handler)
    application.add_handler(CallbackQueryHandler(_log_callback_query), group=-1)
    application.add_handler(MessageHandler(filters.COMMAND, _log_command_update), group=-1)
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("quiz", quiz_command))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CommandHandler("checkadmin", check_admin_command))
    application.add_handler(CommandHandler("premium_status", premium_status_command))

    application.add_handler(CallbackQueryHandler(menu_callback_handler, pattern=r"^(menu:|profile:|help:|leaderboard:|support:)"))
    application.add_handler(CallbackQueryHandler(subscribe_premium_handler, pattern=r"^premium:"))
    application.add_handler(CallbackQueryHandler(admin_callback_handler, pattern=r"^admin:"))
    application.add_handler(CallbackQueryHandler(pdf_callback_handler, pattern=r"^pdf:"))
    application.add_handler(CallbackQueryHandler(quiz_callback_handler, pattern=r"^quiz:"))

    application.add_handler(MessageHandler(filters.PHOTO, admin_photo_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_text_router), group=0)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, support_text_router), group=1)

    notification_service.register_jobs(application)
    logger.info("Bot build complete | handlers_registered=1 notification_jobs_ready=1")
    return application


def main():
    logger.info("Bot main start")
    flask_thread = _start_keep_alive_server()
    try:
        application = build_application()
        logger.info("Quiz bot is starting | polling_about_to_start=1")
        logger.info("Calling application.run_polling()")
        application.run_polling(drop_pending_updates=True)
        logger.info("application.run_polling() returned normally")
    except Exception:
        logger.exception("Bot startup/polling failed; keeping Flask server alive for Render")
        while flask_thread.is_alive():
            time.sleep(60)


if __name__ == "__main__":
    main()
