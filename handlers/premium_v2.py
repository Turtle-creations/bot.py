from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from keyboards.app_keyboards import payment_link_keyboard, premium_keyboard, premium_plan_keyboard
from services.payment_service_db import SUBSCRIPTION_PLANS, payment_service
from services.premium_service_db import premium_service
from services.user_service_db import user_service
from utils.formatters import format_premium_text


def _payment_unavailable_text(user: dict, missing_vars: list[str]) -> str:
    if user_service.is_admin(user["user_id"]):
        missing_text = ", ".join(missing_vars)
        return (
            "<b>Payment configuration error</b>\n\n"
            "Razorpay checkout is disabled because required env vars are missing.\n"
            f"<code>{missing_text}</code>"
        )

    return (
        "<b>Payments temporarily unavailable</b>\n\n"
        "Premium checkout is not configured correctly yet. Please contact the admin."
    )


async def premium_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = user_service.ensure_user(update.effective_user)
    await update.effective_message.reply_text(payment_service.premium_status_text(user))


async def subscribe_premium_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = user_service.ensure_user(query.from_user)
    data = query.data

    if data == "premium:view":
        quiz_access_text = "All quiz sets" if premium_service.is_premium(user["user_id"]) else "Unlocked sets only"
        if premium_service.is_premium(user["user_id"]):
            pdf_text = "Unlimited"
        else:
            pdf_text = "1" if user_service.can_generate_free_pdf(user) else "0"
        await query.message.reply_text(
            format_premium_text(
                premium_service.status_text(user),
                quiz_access_text,
                pdf_text,
                0,
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=premium_keyboard(),
        )
        return

    if data in {"premium:subscribe", "premium:coming_soon"}:
        missing_vars = payment_service.get_missing_configuration()
        if missing_vars:
            await query.message.reply_text(
                _payment_unavailable_text(user, missing_vars),
                parse_mode=ParseMode.HTML,
            )
            return

        await query.message.reply_text(
            (
                "<b>Premium Plans</b>\n\n"
                "Choose a plan to generate your Razorpay checkout link."
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=premium_plan_keyboard(),
        )
        return

    if data.startswith("premium:plan:"):
        missing_vars = payment_service.get_missing_configuration()
        if missing_vars:
            await query.message.reply_text(
                _payment_unavailable_text(user, missing_vars),
                parse_mode=ParseMode.HTML,
            )
            return

        plan_type = data.split("premium:plan:", 1)[1]
        plan = SUBSCRIPTION_PLANS.get(plan_type)
        if not plan:
            await query.message.reply_text("Invalid premium plan selected.")
            return

        order = await payment_service.create_order(user["user_id"], plan_type)
        await query.message.reply_text(
            (
                "<b>Premium Checkout</b>\n\n"
                f"Plan: <b>{plan['name']}</b>\n"
                f"Amount: <b>INR {plan['amount'] / 100:.2f}</b>\n\n"
                "Tap the button below to open Razorpay checkout. Premium will activate only after payment verification succeeds."
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=payment_link_keyboard(order["payment_url"]),
        )
        return
