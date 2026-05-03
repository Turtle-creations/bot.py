# -*- coding: utf-8 -*-

import html
import secrets
import sqlite3
from pathlib import Path

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from config import BASE_DIR, DATABASE_PATH, DEFAULT_QUESTION_TIME, IMAGE_DIR, SUPREME_ADMIN_ID
from db.database import database
from keyboards.app_keyboards import (
    admin_exam_keyboard,
    admin_keyboard,
    admin_question_search_keyboard,
    admin_set_keyboard,
    admin_user_keyboard,
    back_to_main_keyboard,
    confirm_keyboard,
    correct_answer_keyboard,
    notification_delete_confirm_keyboard,
    notification_detail_keyboard,
    notification_hour_keyboard,
    notification_minute_keyboard,
    notification_schedule_keyboard,
    notification_weekday_keyboard,
    saved_notifications_keyboard,
    skip_image_keyboard,
)
from services.exam_service_db import exam_service
from services.notification_service_db import DAY_LABELS, notification_service
from services.payment_service_db import payment_service
from services.premium_service_db import premium_service
from services.user_service_db import user_service
from utils.logging_utils import get_logger


logger = get_logger(__name__)

ADD_ADMIN_UPSERT_SQL = """
INSERT INTO users (
    user_id,
    username,
    full_name,
    is_admin,
    created_at,
    updated_at
)
VALUES (?, NULL, ?, 1, datetime('now'), datetime('now'))
ON CONFLICT(user_id) DO UPDATE SET
    is_admin = 1,
    updated_at = datetime('now')
""".strip()


def _is_supreme_admin(user_id: int) -> bool:
    return user_service.is_supreme_admin(user_id)


def _is_admin(user_id: int) -> bool:
    return user_service.is_admin(user_id)


def _can_manage_admins(user_id: int) -> bool:
    return False


def _admin_keyboard_for(user_id: int):
    return admin_keyboard(can_manage_admins=_can_manage_admins(user_id))


def _extract_target_user_id(message) -> int | None:
    text = (message.text or "").strip()
    if text.isdigit():
        return int(text)

    forwarded_user = getattr(message, "forward_from", None)
    if forwarded_user:
        return forwarded_user.id

    forward_origin = getattr(message, "forward_origin", None)
    sender_user = getattr(forward_origin, "sender_user", None)
    if sender_user:
        return sender_user.id

    return None


def _validate_target_user_id(message) -> tuple[int | None, str | None]:
    text = (message.text or "").strip()
    if not text and not getattr(message, "forward_from", None) and not getattr(message, "forward_origin", None):
        return None, "Invalid Telegram ID."

    target_user_id = _extract_target_user_id(message)
    if not target_user_id:
        return None, "Invalid Telegram ID."

    return target_user_id, None


def _validate_numeric_telegram_user_id(message) -> tuple[int | None, str | None]:
    raw_text = message.text or ""
    normalized_text = "".join(raw_text.split())

    if not normalized_text or not normalized_text.isdigit():
        return None, "Invalid Telegram ID"

    return int(normalized_text), None


def _fetch_user_row_for_debug(user_id: int | None) -> dict | None:
    if user_id is None:
        return None

    with database.connection() as conn:
        row = conn.execute(
            """
            SELECT user_id, username, full_name, is_admin, is_premium,
                   premium_expires_at, score, quiz_played,
                   correct_answers, wrong_answers, updated_at
            FROM users
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()

    return dict(row) if row else None


def _users_table_exists_for_debug() -> bool:
    with database.connection() as conn:
        row = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = 'users'
            """
        ).fetchone()
    return bool(row)


def _format_add_admin_debug_message(debug: dict) -> str:
    lines = [
        "<b>Add Admin Debug</b>",
        "",
        f"1. current_user_id: <code>{html.escape(str(debug.get('current_user_id')))}</code>",
        f"2. SUPREME_ADMIN_ID: <code>{html.escape(str(debug.get('supreme_admin_id')))}</code>",
        f"3. is_supreme_admin: <code>{html.escape(str(debug.get('is_supreme_admin')))}</code>",
        f"4. target_user_id: <code>{html.escape(str(debug.get('target_user_id')))}</code>",
        f"5. DB path: <code>{html.escape(str(debug.get('db_path')))}</code>",
        f"6. users table exists: <code>{html.escape(str(debug.get('users_table_exists')))}</code>",
        f"7. target row before add: <code>{html.escape(str(debug.get('target_row_before')))}</code>",
        f"8. SQL executed: <code>{html.escape(str(debug.get('sql_executed')))}</code>",
        f"9. target row after add: <code>{html.escape(str(debug.get('target_row_after')))}</code>",
        f"10. final is_admin(target_user_id): <code>{html.escape(str(debug.get('final_is_admin')))}</code>",
    ]

    if debug.get("error"):
        lines.extend(
            [
                "",
                f"<b>Error:</b> <code>{html.escape(str(debug['error']))}</code>",
            ]
        )

    return "\n".join(lines)


def _admin_save_context(
    *,
    admin_user_id: int,
    state: str,
    input_text: str | None,
) -> dict:
    return {
        "admin_user_id": admin_user_id,
        "state": state,
        "input_text": input_text,
        "db_path": str(DATABASE_PATH),
    }


def _truncate_debug_value(value, limit: int = 500) -> str:
    text = str(value)
    if len(text) <= limit:
        return text
    return f"{text[:limit - 3]}..."


async def _send_admin_save_debug(message, **details):
    logger.info(
        "Admin save debug | %s",
        " ".join(
            f"{key}={_truncate_debug_value(value)}"
            for key, value in details.items()
        ),
    )


def _reset_question_wizard(context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("question_wizard", None)
    context.user_data.pop("pending_question_image", None)


def _reset_delete_question_state(context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("delete_question_matches", None)
    context.user_data.pop("delete_question_selected_id", None)


def _reset_notification_state(context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("notification_wizard", None)
    context.user_data.pop("notification_delete_id", None)


def _reset_admin_callback_state(context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("admin_callback_tokens", None)
    context.user_data.pop("admin_processed_tokens", None)


def _new_admin_callback_token(context: ContextTypes.DEFAULT_TYPE, scope: str) -> str:
    tokens = context.user_data.setdefault("admin_callback_tokens", {})
    token = secrets.token_hex(4)
    tokens[scope] = token
    return token


def _claim_admin_callback_token(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    scope: str,
    token: str,
) -> bool:
    tokens = context.user_data.setdefault("admin_callback_tokens", {})
    processed = context.user_data.setdefault("admin_processed_tokens", set())

    if tokens.get(scope) != token:
        return False

    token_key = f"{scope}:{token}"
    if token_key in processed:
        return False

    processed.add(token_key)
    return True


async def _parse_tokenized_admin_callback(
    query,
    data: str,
    *,
    expected_section: str,
    expected_action: str | None = None,
) -> tuple[str | None, int | None]:
    logger.info(
        "Admin callback received | section=%s action=%s callback_data=%s",
        expected_section,
        expected_action,
        data,
    )

    parts = data.split(":")

    # New format: admin:<section>:<action>:<token>:<id>
    if len(parts) == 5:
        prefix, section, action, token, item_id_text = parts
        if (
            prefix != "admin"
            or section != expected_section
            or (expected_action is not None and action != expected_action)
        ):
            logger.warning(
                "Admin callback invalid format | expected=%s:%s callback_data=%s",
                expected_section,
                expected_action,
                data,
            )
            await query.message.reply_text("This action is no longer valid. Please try again.")
            return None, None

        if not item_id_text.isdigit():
            logger.warning(
                "Admin callback invalid id | expected=%s:%s callback_data=%s",
                expected_section,
                expected_action,
                data,
            )
            await query.message.reply_text("This action is no longer valid. Please try again.")
            return None, None

        return token, int(item_id_text)

    # Backward compatibility: admin:<section>:<token>:<id>
    if len(parts) == 4:
        prefix, section, token_or_action, item_id_text = parts
        if prefix != "admin" or section != expected_section:
            logger.warning(
                "Admin callback invalid legacy format | expected=%s:%s callback_data=%s",
                expected_section,
                expected_action,
                data,
            )
            await query.message.reply_text("This action is no longer valid. Please try again.")
            return None, None

        if not item_id_text.isdigit():
            logger.warning(
                "Admin callback invalid legacy id | expected=%s:%s callback_data=%s",
                expected_section,
                expected_action,
                data,
            )
            await query.message.reply_text("This action is no longer valid. Please try again.")
            return None, None

        if expected_action is not None and token_or_action == expected_action:
            return None, int(item_id_text)

        return token_or_action, int(item_id_text)

    logger.warning(
        "Admin callback unexpected part count | expected=4_or_5 actual=%s callback_data=%s",
        len(parts),
        data,
    )
    await query.message.reply_text("This action is no longer valid. Please try again.")
    return None, None


async def _parse_token_only_admin_callback(
    query,
    data: str,
    *,
    expected_section: str,
) -> str | None:
    logger.info(
        "Admin callback received | section=%s callback_data=%s",
        expected_section,
        data,
    )

    parts = data.split(":")
    if len(parts) != 3:
        logger.warning(
            "Admin callback unexpected part count | expected=3 actual=%s callback_data=%s",
            len(parts),
            data,
        )
        await query.message.reply_text("This action is no longer valid. Please try again.")
        return None

    prefix, section, token = parts
    if prefix != "admin" or section != expected_section:
        logger.warning(
            "Admin callback invalid token-only format | expected=%s callback_data=%s",
            expected_section,
            data,
        )
        await query.message.reply_text("This action is no longer valid. Please try again.")
        return None

    return token


async def _parse_simple_admin_callback_value(
    query,
    data: str,
    *,
    expected_section: str,
    expected_action: str,
) -> str | None:
    logger.info(
        "Admin callback received | section=%s action=%s callback_data=%s",
        expected_section,
        expected_action,
        data,
    )

    parts = data.split(":")
    if len(parts) != 4:
        logger.warning(
            "Admin callback unexpected part count | expected=4 actual=%s callback_data=%s",
            len(parts),
            data,
        )
        await query.message.reply_text("This action is no longer valid. Please try again.")
        return None

    prefix, section, action, value = parts
    if prefix != "admin" or section != expected_section or action != expected_action:
        logger.warning(
            "Admin callback invalid simple format | expected=%s:%s callback_data=%s",
            expected_section,
            expected_action,
            data,
        )
        await query.message.reply_text("This action is no longer valid. Please try again.")
        return None

    return value


async def _parse_delete_question_callback(query, data: str):
    print("DELETE CALLBACK DATA:", data)

    parts = data.split(":")
    if len(parts) != 5:
        await query.answer("Invalid callback data", show_alert=True)
        return None

    prefix, action_group, action_type, token, question_id_text = parts
    if prefix != "admin" or action_group != "delete_question":
        await query.answer("Invalid callback data", show_alert=True)
        return None

    if action_type not in {"select", "confirm", "cancel"}:
        await query.answer("Invalid callback data", show_alert=True)
        return None

    try:
        question_id = int(question_id_text)
    except (TypeError, ValueError):
        await query.answer("Invalid question selection", show_alert=True)
        return None

    return {
        "action_type": action_type,
        "token": token,
        "question_id": question_id,
    }


async def _parse_notification_callback(query, data: str):
    print("NOTIFICATION CALLBACK:", data)

    parts = data.split(":")
    if len(parts) != 4:
        await query.answer("Invalid notification action", show_alert=True)
        return None

    prefix, section, action, notification_id_text = parts
    if prefix != "admin" or section != "notify":
        await query.answer("Invalid notification action", show_alert=True)
        return None

    if action not in {"view", "delete", "confirm_delete", "cancel_delete", "test_send"}:
        await query.answer("Invalid notification action", show_alert=True)
        return None

    try:
        notification_id = int(notification_id_text)
    except (TypeError, ValueError):
        await query.answer("Invalid notification", show_alert=True)
        return None

    return {
        "action": action,
        "notification_id": notification_id,
    }


async def _show_notification_menu(message):
        await message.reply_text(
        (
            "<b>🔔 Schedule Notifications</b>\n\n"
            "Choose how you want to manage engagement notifications."
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=notification_schedule_keyboard(),
    )


def _build_notification_list_text(notifications: list[dict]) -> str:
    lines = ["<b>📋 Saved Notifications</b>", ""]

    for item in notifications:
        preview = item["message"]
        if len(preview) > 90:
            preview = f"{preview[:87]}..."
        preview = html.escape(preview)

        schedule_line = f"<b>#{item['notification_id']}</b> {item['kind'].title()} at {item.get('send_time') or '--:--'}"
        if item["kind"] == "weekly" and item.get("days_text"):
            schedule_line += f" on {html.escape(item['days_text'])}"

        lines.append(schedule_line)
        lines.append(preview)
        lines.append("")

    return "\n".join(lines).strip()


async def _show_saved_notifications(message):
    notifications = notification_service.list_schedules()
    if not notifications:
        await message.reply_text(
            "⚠️ No saved notifications found.",
            reply_markup=notification_schedule_keyboard(),
        )
        return

    await message.reply_text(
        _build_notification_list_text(notifications),
        parse_mode=ParseMode.HTML,
        reply_markup=saved_notifications_keyboard(notifications),
    )


async def _show_notification_details(message, notification_id: int):
    notification = notification_service.get_schedule(notification_id)
    if not notification:
        await message.reply_text("❌ Notification not found.")
        return

    preview = html.escape(notification["message"])
    lines = [
        "<b>📩 Notification Details</b>",
        "",
        f"<b>ID:</b> {notification['notification_id']}",
        f"<b>Type:</b> {notification['kind'].title()}",
        f"<b>Time:</b> {notification.get('send_time') or '--:--'}",
        f"<b>Status:</b> {'Active' if notification.get('is_active') else 'Inactive'}",
    ]
    if notification["kind"] == "weekly" and notification.get("days_text"):
        lines.append(f"<b>Days:</b> {html.escape(notification['days_text'])}")
    lines.extend(["", preview])

    await message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=notification_detail_keyboard(notification_id),
    )


async def _show_notification_delete_confirmation(message, notification_id: int):
    notification = notification_service.get_schedule(notification_id)
    if not notification:
        await message.reply_text("❌ Notification not found.")
        return

    preview = notification["message"]
    if len(preview) > 120:
        preview = f"{preview[:117]}..."

    lines = [
        "<b>🗑 Delete Notification</b>",
        "",
        f"Type: {notification['kind'].title()}",
        f"Time: {notification.get('send_time') or '--:--'}",
    ]
    if notification["kind"] == "weekly" and notification.get("days_text"):
        lines.append(f"Days: {notification['days_text']}")
    lines.extend(["", html.escape(preview)])

    await message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=notification_delete_confirm_keyboard(notification_id),
    )


def _build_premium_prices_text() -> str:
    lines = ["<b>💰 Current Premium Prices</b>", ""]
    for item in payment_service.list_premium_prices():
        lines.append(
            f"<b>{item['key']}</b> ({html.escape(item['name'])}) - ₹{item['amount_rupees']:.2f}"
        )
    return "\n".join(lines)


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = user_service.ensure_user(update.effective_user)
    if not user_service.is_admin(user["user_id"]):
        await update.effective_message.reply_text("❌ You are not allowed to open the admin panel.")
        return

    context.user_data["admin_mode"] = None
    context.user_data.pop("selected_exam_id", None)
    context.user_data.pop("selected_set_id", None)
    _reset_question_wizard(context)
    _reset_delete_question_state(context)
    _reset_notification_state(context)
    _reset_admin_callback_state(context)
    await update.effective_message.reply_text(
        "<b>⚙️ Admin Panel</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=_admin_keyboard_for(user["user_id"]),
    )


async def check_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.effective_message:
        return

    requester = user_service.ensure_user(update.effective_user)
    if not user_service.is_admin(requester["user_id"]):
        await update.effective_message.reply_text("❌ You are not allowed to use this command.")
        return

    if not context.args:
        await update.effective_message.reply_text("Usage: /checkadmin <telegram_id>")
        return

    target_text = (context.args[0] or "").strip()
    if not target_text.isdigit():
        await update.effective_message.reply_text("Invalid Telegram ID.")
        return

    target_user_id = int(target_text)
    admin_debug = user_service.get_admin_debug_info(target_user_id)

    await update.effective_message.reply_text(
        (
            "<b>Admin Check</b>\n\n"
            f"<b>User ID:</b> {target_user_id}\n"
            f"<b>User exists:</b> {'Yes' if admin_debug['exists'] else 'No'}\n"
            f"<b>is_admin column:</b> {admin_debug['is_admin_column']}\n"
            f"<b>is_supreme_admin:</b> {'Yes' if admin_debug['is_supreme_admin'] else 'No'}\n"
            f"<b>Final access allowed:</b> {'Yes' if admin_debug['final_access_allowed'] else 'No'}"
        ),
        parse_mode=ParseMode.HTML,
    )


async def admin_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_service.ensure_user(query.from_user)
    if not _is_admin(query.from_user.id):
        await query.message.reply_text("❌ Admin access only.")
        return

    data = query.data

    if data == "admin:panel":
        context.user_data["admin_mode"] = None
        context.user_data.pop("selected_exam_id", None)
        context.user_data.pop("selected_set_id", None)
        _reset_question_wizard(context)
        _reset_delete_question_state(context)
        _reset_notification_state(context)
        _reset_admin_callback_state(context)
        await query.message.reply_text(
            "<b>⚙️ Admin Panel</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=_admin_keyboard_for(query.from_user.id),
        )
        return

    if data in {"admin:schedule", "admin:notify:menu"}:
        context.user_data["admin_mode"] = None
        _reset_notification_state(context)
        await _show_notification_menu(query.message)
        return

    if data == "admin:test_payment_order":
        await query.message.reply_text(
            (
                "Payment system under testing.\n"
                "Live checkout is temporarily disabled in this deploy-ready build."
            )
        )
        return

    if data == "admin:notify:daily":
        context.user_data["admin_mode"] = None
        context.user_data["notification_wizard"] = {
            "kind": "daily",
            "step": "hour",
            "selected_days": [],
        }
        await query.message.reply_text(
            "<b>📅 Daily Notification</b>\n\nStep 1 of 2: Select the hour.",
            parse_mode=ParseMode.HTML,
            reply_markup=notification_hour_keyboard(),
        )
        return

    if data == "admin:notify:weekly":
        context.user_data["admin_mode"] = None
        context.user_data["notification_wizard"] = {
            "kind": "weekly",
            "step": "days",
            "selected_days": [],
        }
        await query.message.reply_text(
            "<b>🗓 Weekly Notification</b>\n\nStep 1 of 3: Select one or more weekdays.",
            parse_mode=ParseMode.HTML,
            reply_markup=notification_weekday_keyboard([]),
        )
        return

    if data == "admin:notify:view":
        await _show_saved_notifications(query.message)
        return

    if data.startswith("admin:notify:day:"):
        wizard = context.user_data.get("notification_wizard")
        if not wizard or wizard.get("kind") != "weekly" or wizard.get("step") != "days":
            return

        try:
            day_text = await _parse_simple_admin_callback_value(
                query,
                data,
                expected_section="notify",
                expected_action="day",
            )
            if day_text is None:
                return
            day_value = int(day_text)
        except (TypeError, ValueError):
            return

        selected_days = set(wizard.get("selected_days", []))
        if day_value in selected_days:
            selected_days.remove(day_value)
        else:
            selected_days.add(day_value)
        wizard["selected_days"] = sorted(selected_days)

        await query.message.reply_text(
            "<b>🗓 Weekly Notification</b>\n\nStep 1 of 3: Select one or more weekdays.",
            parse_mode=ParseMode.HTML,
            reply_markup=notification_weekday_keyboard(wizard["selected_days"]),
        )
        return

    if data == "admin:notify:days_done":
        wizard = context.user_data.get("notification_wizard")
        if not wizard or wizard.get("kind") != "weekly" or wizard.get("step") != "days":
            return

        selected_days = wizard.get("selected_days", [])
        if not selected_days:
            await query.answer("Select at least one day", show_alert=True)
            return

        wizard["step"] = "hour"
        day_names = ", ".join(DAY_LABELS[day] for day in selected_days)
        await query.message.reply_text(
            (
                "<b>🗓 Weekly Notification</b>\n\n"
                f"Selected days: {day_names}\n"
                "Step 2 of 3: Select the hour."
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=notification_hour_keyboard(),
        )
        return

    if data.startswith("admin:notify:hour:"):
        wizard = context.user_data.get("notification_wizard")
        if not wizard or wizard.get("step") != "hour":
            return

        hour = await _parse_simple_admin_callback_value(
            query,
            data,
            expected_section="notify",
            expected_action="hour",
        )
        if hour is None:
            return
        wizard["hour"] = hour
        wizard["step"] = "minute"
        await query.message.reply_text(
            (
                f"<b>{'📅' if wizard['kind'] == 'daily' else '🗓'} {'Daily' if wizard['kind'] == 'daily' else 'Weekly'} Notification</b>\n\n"
                "Select the minute."
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=notification_minute_keyboard(hour),
        )
        return

    if data.startswith("admin:notify:minute:"):
        wizard = context.user_data.get("notification_wizard")
        if not wizard or wizard.get("step") != "minute":
            return

        minute = await _parse_simple_admin_callback_value(
            query,
            data,
            expected_section="notify",
            expected_action="minute",
        )
        if minute is None:
            return
        wizard["send_time"] = f"{wizard['hour']}:{minute}"
        wizard["step"] = "message"
        context.user_data["admin_mode"] = "notification_message"

        day_line = ""
        if wizard["kind"] == "weekly":
            day_names = ", ".join(DAY_LABELS[day] for day in wizard.get("selected_days", []))
            day_line = f"\nDays: {day_names}"

        await query.message.reply_text(
            (
                f"<b>{'📅' if wizard['kind'] == 'daily' else '🗓'} {'Daily' if wizard['kind'] == 'daily' else 'Weekly'} Notification</b>\n\n"
                f"Time: {wizard['send_time']}{day_line}\n\n"
                "Step 3: Send the notification message.\n\n"
                "You can use placeholders like {name}, {username}, and {first_name}."
            ),
            parse_mode=ParseMode.HTML,
        )
        return

    if data.startswith("admin:notify:view:") or data.startswith("admin:notify:delete:") or data.startswith("admin:notify:confirm_delete:") or data.startswith("admin:notify:cancel_delete:") or data.startswith("admin:notify:test_send:"):
        parsed = await _parse_notification_callback(query, data)
        if not parsed:
            return

        notification_id = parsed["notification_id"]
        action = parsed["action"]

        if action == "view":
            await _show_notification_details(query.message, notification_id)
            return

        if action == "delete":
            await _show_notification_delete_confirmation(query.message, notification_id)
            return

        if action == "test_send":
            ok, result_message = await notification_service.send_notification_now(notification_id)
            await query.message.reply_text(
                f"Scheduled notification queued. {result_message}" if ok else result_message
            )
            await _show_notification_details(query.message, notification_id)
            return

        if action == "confirm_delete":
            deleted = notification_service.delete_schedule(notification_id)
            if deleted:
                await query.message.reply_text("✅ Notification deleted")
            else:
                await query.message.reply_text("❌ Notification not found")
            await _show_saved_notifications(query.message)
            return

        await _show_notification_details(query.message, notification_id)
        return

    if data == "admin:add_exam":
        context.user_data["admin_mode"] = "add_exam"
        context.user_data.pop("selected_exam_id", None)
        context.user_data.pop("selected_set_id", None)
        _reset_question_wizard(context)
        logger.info(
            "Admin add exam flow opened | admin_user_id=%s state=%s db_path=%s",
            query.from_user.id,
            "add_exam",
            DATABASE_PATH,
        )
        await query.message.reply_text(
            "<b>➕ Add Exam</b>\n\nSend exam name.",
            parse_mode=ParseMode.HTML,
        )
        await _send_admin_save_debug(
            query.message,
            state="add_exam",
            input="button:admin:add_exam",
            save_function_called=False,
            db_path=DATABASE_PATH,
            db_row_created=None,
            saved_item=None,
            error=None,
        )
        return

    if data == "admin:add_question":
        exams = exam_service.get_exams()
        if not exams:
            await query.message.reply_text("⚠️ No exams found. Add an exam first.")
            return

        context.user_data["admin_mode"] = None
        context.user_data["question_wizard"] = {"step": "exam"}
        token = _new_admin_callback_token(context, "qadd_exam")
        await query.message.reply_text(
            "<b>➕ Add Question</b>\n\nStep 1 of 7: Select exam.",
            parse_mode=ParseMode.HTML,
            reply_markup=admin_exam_keyboard(exams, f"admin:qadd_exam:{token}"),
        )
        await _send_admin_save_debug(
            query.message,
            state="question_wizard:exam",
            input="button:admin:add_question",
            save_function_called=False,
            db_path=DATABASE_PATH,
            db_row_created=None,
            saved_item={"exam_count": len(exams)},
            error=None,
        )
        return

    if data == "admin:add_set":
        exams = exam_service.get_exams()
        if not exams:
            await query.message.reply_text("⚠️ No exams found. Add an exam first.")
            return

        context.user_data["admin_mode"] = "add_set_select_exam"
        token = _new_admin_callback_token(context, "add_set_exam")
        await query.message.reply_text(
            "<b>➕ Add Set</b>\n\nStep 1 of 2: Select exam.",
            parse_mode=ParseMode.HTML,
            reply_markup=admin_exam_keyboard(exams, f"admin:add_set_exam:{token}"),
        )
        await _send_admin_save_debug(
            query.message,
            state="add_set_select_exam",
            input="button:admin:add_set",
            save_function_called=False,
            db_path=DATABASE_PATH,
            db_row_created=None,
            saved_item={"exam_count": len(exams)},
            error=None,
        )
        return

    if data.startswith("admin:add_set_exam:"):
        token, exam_id = await _parse_tokenized_admin_callback(
            query,
            data,
            expected_section="add_set_exam",
        )
        if exam_id is None:
            return
        if token and not _claim_admin_callback_token(context, scope="add_set_exam", token=token):
            return

        context.user_data["selected_exam_id"] = exam_id
        context.user_data["admin_mode"] = "add_set_name"
        await query.message.reply_text(
            "<b>➕ Add Set</b>\n\nStep 2 of 2: Send set name.",
            parse_mode=ParseMode.HTML,
        )
        await _send_admin_save_debug(
            query.message,
            state="add_set_name",
            input=f"selected_exam_id={exam_id}",
            save_function_called=False,
            db_path=DATABASE_PATH,
            db_row_created=None,
            saved_item=exam_service.get_exam(exam_id),
            error=None,
        )
        return

    if data == "admin:delete_set":
        exams = exam_service.get_exams()
        if not exams:
            await query.message.reply_text("⚠️ No exams found.")
            return

        context.user_data["admin_mode"] = "delete_set_select_exam"
        token = _new_admin_callback_token(context, "delete_set_exam")
        await query.message.reply_text(
            "<b>🗑 Delete Set</b>\n\nStep 1 of 3: Select exam.",
            parse_mode=ParseMode.HTML,
            reply_markup=admin_exam_keyboard(exams, f"admin:delete_set_exam:{token}"),
        )
        return

    if data.startswith("admin:delete_set_exam:"):
        token, exam_id = await _parse_tokenized_admin_callback(
            query,
            data,
            expected_section="delete_set_exam",
        )
        if exam_id is None:
            return
        if token and not _claim_admin_callback_token(context, scope="delete_set_exam", token=token):
            return

        sets_ = exam_service.get_sets(exam_id)
        if not sets_:
            await query.message.reply_text("⚠️ No sets found for this exam.")
            return

        context.user_data["selected_exam_id"] = exam_id
        context.user_data["admin_mode"] = "delete_set_select_set"
        next_token = _new_admin_callback_token(context, "delete_set_pick")
        await query.message.reply_text(
            "<b>🗑 Delete Set</b>\n\nStep 2 of 3: Select set.",
            parse_mode=ParseMode.HTML,
            reply_markup=admin_set_keyboard(sets_, f"admin:delete_set_pick:{next_token}"),
        )
        return

    if data.startswith("admin:delete_set_pick:"):
        token, set_id = await _parse_tokenized_admin_callback(
            query,
            data,
            expected_section="delete_set_pick",
        )
        if set_id is None:
            return
        if token and not _claim_admin_callback_token(context, scope="delete_set_pick", token=token):
            return

        context.user_data["selected_set_id"] = set_id
        context.user_data["admin_mode"] = "delete_set_confirm"
        confirm_token = _new_admin_callback_token(context, "delete_set_confirm")
        await query.message.reply_text(
            "<b>🗑 Delete Set</b>\n\nStep 3 of 3: Confirm delete.",
            parse_mode=ParseMode.HTML,
            reply_markup=confirm_keyboard(f"admin:delete_set_confirm:{confirm_token}"),
        )
        return

    if data.startswith("admin:delete_set_confirm:"):
        token = await _parse_token_only_admin_callback(
            query,
            data,
            expected_section="delete_set_confirm",
        )
        if token is None:
            return
        if not _claim_admin_callback_token(context, scope="delete_set_confirm", token=token):
            return

        set_id = context.user_data.get("selected_set_id")
        if not set_id:
            await query.message.reply_text("❌ No set selected.")
            return

        exam_service.delete_set(set_id)
        context.user_data["admin_mode"] = None
        context.user_data.pop("selected_set_id", None)
        await query.message.reply_text("✅ Set deleted successfully.")
        return

    if data == "admin:lock_set":
        exams = exam_service.get_exams()
        if not exams:
            await query.message.reply_text("⚠️ No exams found.")
            return

        context.user_data["admin_mode"] = "lock_set_select_exam"
        token = _new_admin_callback_token(context, "lock_set_exam")
        await query.message.reply_text(
            "<b>🔒 Lock Set</b>\n\nStep 1 of 2: Select exam.",
            parse_mode=ParseMode.HTML,
            reply_markup=admin_exam_keyboard(exams, f"admin:lock_set_exam:{token}"),
        )
        return

    if data.startswith("admin:lock_set_exam:"):
        token, exam_id = await _parse_tokenized_admin_callback(
            query,
            data,
            expected_section="lock_set_exam",
        )
        if exam_id is None:
            return
        if token and not _claim_admin_callback_token(context, scope="lock_set_exam", token=token):
            return

        sets_ = exam_service.get_sets(exam_id)
        if not sets_:
            await query.message.reply_text("⚠️ No sets found for this exam.")
            return

        context.user_data["admin_mode"] = "lock_set_select_set"
        next_token = _new_admin_callback_token(context, "lock_set_pick")
        await query.message.reply_text(
            "<b>🔒 Lock Set</b>\n\nStep 2 of 2: Select set.",
            parse_mode=ParseMode.HTML,
            reply_markup=admin_set_keyboard(sets_, f"admin:lock_set_pick:{next_token}"),
        )
        return

    if data.startswith("admin:lock_set_pick:"):
        token, set_id = await _parse_tokenized_admin_callback(
            query,
            data,
            expected_section="lock_set_pick",
        )
        if set_id is None:
            return
        if token and not _claim_admin_callback_token(context, scope="lock_set_pick", token=token):
            return

        set_ = exam_service.set_set_premium_locked(set_id, True)
        context.user_data["admin_mode"] = None
        if not set_:
            await query.message.reply_text("❌ Set not found.")
            return

        await query.message.reply_text(
            f"✅ Set locked for premium users only: {html.escape(set_['title'])}",
            parse_mode=ParseMode.HTML,
        )
        return

    if data == "admin:unlock_set":
        exams = exam_service.get_exams()
        if not exams:
            await query.message.reply_text("⚠️ No exams found.")
            return

        context.user_data["admin_mode"] = "unlock_set_select_exam"
        token = _new_admin_callback_token(context, "unlock_set_exam")
        await query.message.reply_text(
            "<b>🔓 Unlock Set</b>\n\nStep 1 of 2: Select exam.",
            parse_mode=ParseMode.HTML,
            reply_markup=admin_exam_keyboard(exams, f"admin:unlock_set_exam:{token}"),
        )
        return

    if data.startswith("admin:unlock_set_exam:"):
        token, exam_id = await _parse_tokenized_admin_callback(
            query,
            data,
            expected_section="unlock_set_exam",
        )
        if exam_id is None:
            return
        if token and not _claim_admin_callback_token(context, scope="unlock_set_exam", token=token):
            return

        sets_ = exam_service.get_sets(exam_id)
        if not sets_:
            await query.message.reply_text("⚠️ No sets found for this exam.")
            return

        context.user_data["admin_mode"] = "unlock_set_select_set"
        next_token = _new_admin_callback_token(context, "unlock_set_pick")
        await query.message.reply_text(
            "<b>🔓 Unlock Set</b>\n\nStep 2 of 2: Select set.",
            parse_mode=ParseMode.HTML,
            reply_markup=admin_set_keyboard(sets_, f"admin:unlock_set_pick:{next_token}"),
        )
        return

    if data.startswith("admin:unlock_set_pick:"):
        token, set_id = await _parse_tokenized_admin_callback(
            query,
            data,
            expected_section="unlock_set_pick",
        )
        if set_id is None:
            return
        if token and not _claim_admin_callback_token(context, scope="unlock_set_pick", token=token):
            return

        set_ = exam_service.set_set_premium_locked(set_id, False)
        context.user_data["admin_mode"] = None
        if not set_:
            await query.message.reply_text("❌ Set not found.")
            return

        await query.message.reply_text(
            f"✅ Set unlocked for free users: {html.escape(set_['title'])}",
            parse_mode=ParseMode.HTML,
        )
        return

    if data == "admin:delete_question":
        context.user_data["admin_mode"] = "delete_question_search"
        _reset_delete_question_state(context)
        await query.message.reply_text(
            "<b>🗑 Delete Question</b>\n\nSend full or partial question text to search.",
            parse_mode=ParseMode.HTML,
        )
        return

    if data.startswith("admin:delete_question:"):
        parsed = await _parse_delete_question_callback(query, data)
        if not parsed:
            return

        action_type = parsed["action_type"]
        token = parsed["token"]
        question_id = parsed["question_id"]

        if action_type == "select":
            if not _claim_admin_callback_token(context, scope="delete_question_select", token=token):
                return

            question = exam_service.get_question(question_id)
            if not question:
                await query.message.reply_text("❌ Question not found.")
                return

            context.user_data["delete_question_selected_id"] = question_id
            preview = question["question_text"]
            if len(preview) > 240:
                preview = f"{preview[:237]}..."
            confirm_token = _new_admin_callback_token(context, "delete_question_confirm")
            cancel_token = _new_admin_callback_token(context, "delete_question_cancel")
            await query.message.reply_text(
                (
                    "<b>🗑 Delete Question</b>\n\n"
                    "Are you sure you want to delete this question?\n\n"
                    f"<i>{html.escape(preview)}</i>"
                ),
                parse_mode=ParseMode.HTML,
                reply_markup=confirm_keyboard(
                    f"admin:delete_question:confirm:{confirm_token}:{question_id}",
                    f"admin:delete_question:cancel:{cancel_token}:{question_id}",
                ),
            )
            return

        if action_type == "cancel":
            if not _claim_admin_callback_token(context, scope="delete_question_cancel", token=token):
                return

            context.user_data["admin_mode"] = None
            _reset_delete_question_state(context)
            await query.message.reply_text(
                "<b>⚙️ Admin Panel</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=_admin_keyboard_for(query.from_user.id),
            )
            return

        if not _claim_admin_callback_token(context, scope="delete_question_confirm", token=token):
            return

        selected_question_id = context.user_data.get("delete_question_selected_id")
        if selected_question_id != question_id:
            await query.message.reply_text("❌ This delete action is no longer valid.")
            return

        deleted = exam_service.delete_question(question_id)
        context.user_data["admin_mode"] = None
        _reset_delete_question_state(context)
        await query.message.reply_text(
            "✅ Question deleted successfully." if deleted else "❌ Question not found."
        )
        return

    if data == "admin:add_admin":
        if not _can_manage_admins(query.from_user.id):
            await query.message.reply_text("You are not allowed")
            return

        context.user_data["admin_mode"] = "add_admin"
        await query.message.reply_text(
            "<b>👥 Add Admin</b>\n\nSend the target user's Telegram ID.",
            parse_mode=ParseMode.HTML,
        )
        return

    if data == "admin:remove_admin":
        if not _can_manage_admins(query.from_user.id):
            await query.message.reply_text("You are not allowed to manage admins.")
            return

        context.user_data["admin_mode"] = "remove_admin"
        await query.message.reply_text(
            "<b>🚫 Remove Admin</b>\n\nSend the target admin's Telegram ID.",
            parse_mode=ParseMode.HTML,
        )
        return

    if data == "admin:view_admins":
        if not _can_manage_admins(query.from_user.id):
            await query.message.reply_text("You are not allowed to manage admins.")
            return

        admins = user_service.list_admins()
        lines = ["<b>🛡 Admin List</b>", ""]
        for item in admins:
            role = "Supreme Admin" if _is_supreme_admin(item["user_id"]) else "Admin"
            lines.append(
                f"{item['user_id']} - {html.escape(item.get('full_name') or 'Unknown')} ({role})"
            )
        await query.message.reply_text(
            "\n".join(lines),
            parse_mode=ParseMode.HTML,
            reply_markup=back_to_main_keyboard(),
        )
        return

    if data.startswith("admin:qadd_exam:"):
        token, exam_id = await _parse_tokenized_admin_callback(
            query,
            data,
            expected_section="qadd_exam",
        )
        if exam_id is None:
            return
        if token and not _claim_admin_callback_token(context, scope="qadd_exam", token=token):
            return

        sets_ = exam_service.get_sets(exam_id)
        if not sets_:
            await query.message.reply_text("⚠️ No sets found for this exam. Add a set first.")
            return

        context.user_data["question_wizard"] = {
            "step": "set",
            "exam_id": exam_id,
        }
        next_token = _new_admin_callback_token(context, "qadd_set")
        await query.message.reply_text(
            "<b>➕ Add Question</b>\n\nStep 2 of 7: Select set.",
            parse_mode=ParseMode.HTML,
            reply_markup=admin_set_keyboard(sets_, f"admin:qadd_set:{next_token}"),
        )
        await _send_admin_save_debug(
            query.message,
            state="question_wizard:set",
            input=f"selected_exam_id={exam_id}",
            save_function_called=False,
            db_path=DATABASE_PATH,
            db_row_created=None,
            saved_item={"exam": exam_service.get_exam(exam_id), "set_count": len(sets_)},
            error=None,
        )
        return

    if data.startswith("admin:qadd_set:"):
        token, set_id = await _parse_tokenized_admin_callback(
            query,
            data,
            expected_section="qadd_set",
        )
        if set_id is None:
            return
        if token and not _claim_admin_callback_token(context, scope="qadd_set", token=token):
            return

        wizard = context.user_data.get("question_wizard", {})
        wizard["set_id"] = set_id
        wizard["step"] = "question"
        context.user_data["question_wizard"] = wizard
        await query.message.reply_text(
            "<b>➕ Add Question</b>\n\nStep 3 of 7: Send question text.",
            parse_mode=ParseMode.HTML,
        )
        await _send_admin_save_debug(
            query.message,
            state="question_wizard:question",
            input=f"selected_set_id={set_id}",
            save_function_called=False,
            db_path=DATABASE_PATH,
            db_row_created=None,
            saved_item=exam_service.get_set(set_id),
            error=None,
        )
        return

    if data.startswith("admin:qadd_correct:"):
        wizard = context.user_data.get("question_wizard")
        if not wizard or wizard.get("step") != "correct_answer":
            await query.message.reply_text("⚠️ No correct-answer step is active right now.")
            return

        token, selected_index = await _parse_tokenized_admin_callback(
            query,
            data,
            expected_section="qadd_correct",
        )
        if selected_index is None:
            return
        if token and not _claim_admin_callback_token(context, scope="qadd_correct", token=token):
            return

        selected_index = selected_index - 1
        options = wizard.get("options", [])
        if selected_index < 0 or selected_index >= len(options):
            await query.message.reply_text("❌ Invalid correct answer selection.")
            return

        wizard["correct_option"] = options[selected_index]
        wizard["step"] = "image"
        skip_token = _new_admin_callback_token(context, "qadd_skip_image")
        await query.message.reply_text(
            "Step 6 of 7: Send optional image path, upload a photo, or press skip.",
            reply_markup=skip_image_keyboard(f"admin:qadd_skip_image:{skip_token}"),
        )
        await _send_admin_save_debug(
            query.message,
            state="question_wizard:image",
            input=f"correct_option={wizard['correct_option']}",
            save_function_called=False,
            db_path=DATABASE_PATH,
            db_row_created=None,
            saved_item={"options": wizard.get("options", [])},
            error=None,
        )
        return

    if data.startswith("admin:qadd_skip_image:"):
        wizard = context.user_data.get("question_wizard")
        if not wizard or wizard.get("step") != "image":
            await query.message.reply_text("⚠️ No image step is active right now.")
            return

        token = await _parse_token_only_admin_callback(
            query,
            data,
            expected_section="qadd_skip_image",
        )
        if token is None:
            return
        if not _claim_admin_callback_token(context, scope="qadd_skip_image", token=token):
            return

        wizard["image_path"] = None
        wizard["step"] = "time"
        await query.message.reply_text("Step 7 of 7: Send optional timer in seconds, or type `skip`.")
        await _send_admin_save_debug(
            query.message,
            state="question_wizard:time",
            input="skip_image",
            save_function_called=False,
            db_path=DATABASE_PATH,
            db_row_created=None,
            saved_item={"image_path": None},
            error=None,
        )
        return

    action = data.split(":", 1)[1]
    context.user_data["admin_mode"] = None
    prompts = {
        "add_exam": "➕ Send exam title",
        "delete_exam": "🗑 Send exam ID",
        "broadcast": "📢 Send the broadcast message",
        "upgrade_premium": "💎 Send: user_id | days",
        "downgrade_premium": "↩️ Send user_id",
        "change_premium_price": "💰 Send: plan_key | amount\nValid plan keys: week_1, month_1, month_3",
    }

    if action in prompts:
        _reset_notification_state(context)
        context.user_data["admin_mode"] = action
        _reset_question_wizard(context)
        await query.message.reply_text(prompts[action])
        return

    if action == "view_exams":
        exams = exam_service.get_exams()
        if not exams:
            await query.message.reply_text("⚠️ No exams found.", reply_markup=back_to_main_keyboard())
            return

        lines = ["<b>📚 Exams</b>\n"]
        for exam in exams:
            lines.append(
                f"{exam['exam_id']}. {exam['title']} | sets={exam['set_count']} | questions={exam['question_count']}"
            )

        await query.message.reply_text(
            "\n".join(lines),
            parse_mode=ParseMode.HTML,
            reply_markup=back_to_main_keyboard(),
        )
        return

    if action == "view_premium":
        premium_users = premium_service.list_premium_users()
        if not premium_users:
            await query.message.reply_text(
                "⚠️ No active premium users found.",
                reply_markup=back_to_main_keyboard(),
            )
            return

        lines = ["<b>👑 Premium Users</b>\n"]
        for item in premium_users:
            lines.append(
                f"{item['user_id']} - {item['full_name']} - expires {item['premium_expires_at']}"
            )

        await query.message.reply_text(
            "\n".join(lines),
            parse_mode=ParseMode.HTML,
            reply_markup=back_to_main_keyboard(),
        )
        return

    if action == "view_premium_prices":
        await query.message.reply_text(
            _build_premium_prices_text(),
            parse_mode=ParseMode.HTML,
            reply_markup=back_to_main_keyboard(),
        )
        return


async def admin_text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return

    user_service.ensure_user(update.effective_user)
    if not _is_admin(update.effective_user.id):
        return

    notification_wizard = context.user_data.get("notification_wizard")
    if notification_wizard and notification_wizard.get("step") == "message":
        await _handle_notification_message(update, context, notification_wizard)
        return

    if context.user_data.get("question_wizard"):
        await _handle_question_wizard_text(update, context)
        return

    mode = context.user_data.get("admin_mode")
    if not mode or not update.effective_message:
        return

    text = (update.effective_message.text or "").strip()
    admin_user_id = update.effective_user.id
    logger.info(
        "Admin text router received | admin_user_id=%s state=%s selected_exam_id=%s selected_set_id=%s has_question_wizard=%s input_text=%s db_path=%s",
        admin_user_id,
        mode,
        context.user_data.get("selected_exam_id"),
        context.user_data.get("selected_set_id"),
        bool(context.user_data.get("question_wizard")),
        text,
        DATABASE_PATH,
    )
    await _send_admin_save_debug(
        update.effective_message,
        state=mode,
        input=text,
        save_function_called=False,
        db_path=DATABASE_PATH,
        db_row_created=None,
        saved_item=None,
        error=None,
    )

    try:
        if mode == "add_exam":
            if not exam_service.exam_storage_ready():
                logger.error(
                    "Exam save failed | admin_user_id=%s state=%s reason=table_missing db_path=%s",
                    admin_user_id,
                    mode,
                    DATABASE_PATH,
                )
                await _send_admin_save_debug(
                    update.effective_message,
                    state=mode,
                    input=text,
                    save_function_called=False,
                    db_path=DATABASE_PATH,
                    db_row_created=None,
                    saved_item=None,
                    error="DB table missing",
                )
                await update.effective_message.reply_text("DB table missing")
                return
            if not text:
                await _send_admin_save_debug(
                    update.effective_message,
                    state=mode,
                    input=text,
                    save_function_called=False,
                    db_path=DATABASE_PATH,
                    db_row_created=None,
                    saved_item=None,
                    error="empty exam title",
                )
                await update.effective_message.reply_text("Exam save failed")
                return

            await _send_admin_save_debug(
                update.effective_message,
                state=mode,
                input=text,
                save_function_called="exam_service.add_exam",
                db_path=DATABASE_PATH,
                db_row_created=None,
                saved_item=None,
                error=None,
            )
            result = exam_service.add_exam(text)
            logger.info(
                "Exam save success | admin_user_id=%s state=%s db_path=%s row_id=%s record=%s",
                admin_user_id,
                mode,
                DATABASE_PATH,
                result["row_id"],
                result["record"],
            )
            await _send_admin_save_debug(
                update.effective_message,
                state=mode,
                input=text,
                save_function_called="exam_service.add_exam",
                db_path=DATABASE_PATH,
                db_row_created=result["row_id"],
                saved_item=result["record"],
                error=None,
            )
            await update.effective_message.reply_text(
                f"Saved exam: <code>{html.escape(str(result['record']))}</code>",
                parse_mode=ParseMode.HTML,
            )
            await update.effective_message.reply_text("✅ Exam created successfully.")

        elif mode == "delete_exam":
            exam_service.delete_exam(int(text))
            await update.effective_message.reply_text("✅ Exam deleted successfully.")

        elif mode == "add_set_name":
            exam_id = context.user_data.get("selected_exam_id")
            if not exam_id:
                logger.warning(
                    "Set save failed | admin_user_id=%s state=%s reason=invalid_state db_path=%s",
                    admin_user_id,
                    mode,
                    DATABASE_PATH,
                )
                await _send_admin_save_debug(
                    update.effective_message,
                    state=mode,
                    input=text,
                    save_function_called=False,
                    db_path=DATABASE_PATH,
                    db_row_created=None,
                    saved_item=None,
                    error="Invalid state",
                )
                await update.effective_message.reply_text("Invalid state")
            elif not text:
                await _send_admin_save_debug(
                    update.effective_message,
                    state=mode,
                    input=text,
                    save_function_called=False,
                    db_path=DATABASE_PATH,
                    db_row_created=None,
                    saved_item={"exam_id": exam_id},
                    error="empty set title",
                )
                await update.effective_message.reply_text("Set save failed")
            else:
                if not exam_service.exam_storage_ready():
                    logger.error(
                        "Set save failed | admin_user_id=%s state=%s reason=table_missing db_path=%s",
                        admin_user_id,
                        mode,
                        DATABASE_PATH,
                    )
                    await _send_admin_save_debug(
                        update.effective_message,
                        state=mode,
                        input=text,
                        save_function_called=False,
                        db_path=DATABASE_PATH,
                        db_row_created=None,
                        saved_item={"exam_id": exam_id},
                        error="DB table missing",
                    )
                    await update.effective_message.reply_text("DB table missing")
                    return

                await _send_admin_save_debug(
                    update.effective_message,
                    state=mode,
                    input=text,
                    save_function_called="exam_service.add_set",
                    db_path=DATABASE_PATH,
                    db_row_created=None,
                    saved_item={"exam_id": exam_id},
                    error=None,
                )
                result = exam_service.add_set(exam_id, text)
                logger.info(
                    "Set save success | admin_user_id=%s state=%s input_text=%s db_path=%s row_id=%s exam_id=%s record=%s",
                    admin_user_id,
                    mode,
                    text,
                    DATABASE_PATH,
                    result["row_id"],
                    exam_id,
                    result["record"],
                )
                await _send_admin_save_debug(
                    update.effective_message,
                    state=mode,
                    input=text,
                    save_function_called="exam_service.add_set",
                    db_path=DATABASE_PATH,
                    db_row_created=result["row_id"],
                    saved_item=result["record"],
                    error=None,
                )
                await update.effective_message.reply_text(
                    f"Saved set: <code>{html.escape(str(result['record']))}</code>",
                    parse_mode=ParseMode.HTML,
                )
                context.user_data.pop("selected_exam_id", None)
                await update.effective_message.reply_text("✅ Set created successfully.")

        elif mode == "delete_question_search":
            if not text:
                await update.effective_message.reply_text("❌ Question text is required.")
                return

            matches = exam_service.find_questions_by_text(text)
            if not matches:
                await update.effective_message.reply_text("❌ Question not found.")
                return

            context.user_data["delete_question_matches"] = [item["question_id"] for item in matches]
            token = _new_admin_callback_token(context, "delete_question_select")
            await update.effective_message.reply_text(
                "<b>🗑 Matching Questions</b>\n\nSelect the question you want to delete.",
                parse_mode=ParseMode.HTML,
                reply_markup=admin_question_search_keyboard(
                    matches,
                    f"admin:delete_question:select:{token}",
                ),
            )
            return

        elif mode == "broadcast":
            queued, result_message = await notification_service.queue_broadcast(text, source="admin_broadcast")
            await update.effective_message.reply_text(
                f"Broadcast queued. {result_message}" if queued else result_message
            )

        elif mode == "add_admin":
            current_user_id = update.effective_user.id
            is_supreme = _can_manage_admins(current_user_id)
            debug_details = {
                "current_user_id": current_user_id,
                "supreme_admin_id": SUPREME_ADMIN_ID,
                "is_supreme_admin": is_supreme,
                "target_user_id": None,
                "db_path": str(DATABASE_PATH),
                "users_table_exists": None,
                "target_row_before": None,
                "sql_executed": ADD_ADMIN_UPSERT_SQL,
                "target_row_after": None,
                "final_is_admin": None,
                "error": None,
            }
            if not is_supreme:
                logger.warning(
                    "Add admin denied | current_user_id=%s is_supreme_admin=%s",
                    current_user_id,
                    is_supreme,
                )
                await update.effective_message.reply_text("You are not allowed")
                return

            target_user_id, validation_error = _validate_numeric_telegram_user_id(update.effective_message)
            debug_details["target_user_id"] = target_user_id
            storage_ready = user_service.admin_storage_ready()
            users_table_exists = _users_table_exists_for_debug()
            debug_details["users_table_exists"] = users_table_exists
            target_row_before = _fetch_user_row_for_debug(target_user_id)
            debug_details["target_row_before"] = target_row_before
            target_exists_before = bool(target_row_before)
            logger.info(
                "Add admin debug | current_user_id=%s supreme_admin_id=%s is_supreme_admin=%s target_user_id=%s db_path=%s users_table_exists=%s target_row_before=%s sql_executed=%s",
                current_user_id,
                SUPREME_ADMIN_ID,
                is_supreme,
                target_user_id,
                DATABASE_PATH,
                users_table_exists,
                target_row_before,
                ADD_ADMIN_UPSERT_SQL,
            )
            if not storage_ready:
                debug_details["error"] = "admin_storage_not_ready"
                logger.error(
                    "Add admin debug failure | current_user_id=%s target_user_id=%s error=%s",
                    current_user_id,
                    target_user_id,
                    debug_details["error"],
                )
                await update.effective_message.reply_text("Database error")
                await update.effective_message.reply_text(
                    _format_add_admin_debug_message(debug_details),
                    parse_mode=ParseMode.HTML,
                )
                return
            if validation_error:
                debug_details["error"] = validation_error
                logger.warning(
                    "Add admin debug validation | current_user_id=%s target_user_id=%s error=%s",
                    current_user_id,
                    target_user_id,
                    validation_error,
                )
                await update.effective_message.reply_text(validation_error)
                await update.effective_message.reply_text(
                    _format_add_admin_debug_message(debug_details),
                    parse_mode=ParseMode.HTML,
                )
                return
            if target_user_id == current_user_id:
                logger.warning(
                    "Add admin rejected | current_user_id=%s target_user_id=%s reason=self_promotion",
                    current_user_id,
                    target_user_id,
                )
                debug_details["error"] = "self_promotion_denied"
                await update.effective_message.reply_text("You are not allowed")
                await update.effective_message.reply_text(
                    _format_add_admin_debug_message(debug_details),
                    parse_mode=ParseMode.HTML,
                )
                return

            logger.info(
                "Add admin target lookup | current_user_id=%s target_user_id=%s user_exists=%s target_is_admin=%s",
                current_user_id,
                target_user_id,
                target_exists_before,
                user_service.is_admin(target_user_id),
            )
            if user_service.is_admin(target_user_id):
                debug_details["target_row_after"] = _fetch_user_row_for_debug(target_user_id)
                debug_details["final_is_admin"] = user_service.is_admin(target_user_id)
                await update.effective_message.reply_text("This user is already admin")
                await update.effective_message.reply_text(
                    _format_add_admin_debug_message(debug_details),
                    parse_mode=ParseMode.HTML,
                )
                return

            try:
                result, db_result = user_service.promote_to_admin(target_user_id)
                debug_details["target_row_after"] = _fetch_user_row_for_debug(target_user_id)
                debug_details["final_is_admin"] = user_service.is_admin(target_user_id)
                logger.info(
                    "Add admin DB result | current_user_id=%s target_user_id=%s user_exists=%s is_supreme_admin=%s db_result=%s result_exists=%s target_exists_after=%s target_row_after=%s final_is_admin=%s",
                    current_user_id,
                    target_user_id,
                    target_exists_before,
                    is_supreme,
                    db_result,
                    bool(result),
                    bool(user_service.get_user(target_user_id)),
                    debug_details["target_row_after"],
                    debug_details["final_is_admin"],
                )
            except RuntimeError as exc:
                debug_details["error"] = str(exc)
                debug_details["target_row_after"] = _fetch_user_row_for_debug(target_user_id)
                debug_details["final_is_admin"] = user_service.is_admin(target_user_id) if target_user_id else None
                logger.exception(
                    "Add admin storage failure | current_user_id=%s target_user_id=%s",
                    current_user_id,
                    target_user_id,
                )
                await update.effective_message.reply_text("Database error")
                await update.effective_message.reply_text(
                    _format_add_admin_debug_message(debug_details),
                    parse_mode=ParseMode.HTML,
                )
                return
            except Exception as exc:
                debug_details["error"] = f"{type(exc).__name__}: {exc}"
                debug_details["target_row_after"] = _fetch_user_row_for_debug(target_user_id)
                debug_details["final_is_admin"] = user_service.is_admin(target_user_id) if target_user_id else None
                logger.exception(
                    "Add admin database error | current_user_id=%s target_user_id=%s",
                    current_user_id,
                    target_user_id,
                )
                await update.effective_message.reply_text("Database error")
                await update.effective_message.reply_text(
                    _format_add_admin_debug_message(debug_details),
                    parse_mode=ParseMode.HTML,
                )
                return

            if db_result in {"already_admin", "supreme_admin"}:
                await update.effective_message.reply_text("This user is already admin")
            elif db_result not in {"updated", "inserted"} or not result:
                debug_details["error"] = f"unexpected_db_result={db_result}"
                await update.effective_message.reply_text("Database error")
            else:
                await update.effective_message.reply_text("Admin added successfully.")

            await update.effective_message.reply_text(
                _format_add_admin_debug_message(debug_details),
                parse_mode=ParseMode.HTML,
            )

        elif mode == "remove_admin":
            if not _can_manage_admins(update.effective_user.id):
                await update.effective_message.reply_text("You are not allowed to manage admins.")
                return

            target_user_id = _extract_target_user_id(update.effective_message)
            if not target_user_id:
                await update.effective_message.reply_text("Invalid user ID.")
                return
            if _is_supreme_admin(target_user_id) or target_user_id == update.effective_user.id:
                await update.effective_message.reply_text("Supreme Admin cannot be removed.")
                return

            if not user_service.is_admin(target_user_id):
                await update.effective_message.reply_text("Admin not found.")
                return

            result = user_service.demote_admin(target_user_id)
            if not result:
                await update.effective_message.reply_text("Admin not found.")
            else:
                await update.effective_message.reply_text(
                    f"✅ {result.get('full_name') or target_user_id} is no longer an admin."
                )

        elif mode == "upgrade_premium":
            user_id_text, days_text = [part.strip() for part in text.split("|", 1)]
            result = premium_service.upgrade_user(int(user_id_text), int(days_text))
            if not result:
                await update.effective_message.reply_text("❌ User not found.")
            else:
                await update.effective_message.reply_text(
                    f"✅ Premium activated for {result['full_name']} until {result['premium_expires_at']}."
                )

        elif mode == "downgrade_premium":
            result = premium_service.downgrade_user(int(text))
            await update.effective_message.reply_text(
                f"✅ Premium removed for {result['full_name']}."
            )

        elif mode == "change_premium_price":
            if "|" not in text:
                await update.effective_message.reply_text(
                    "❌ Invalid format. Send: plan_key | amount"
                )
                return

            plan_type_text, amount_text = [part.strip() for part in text.split("|", 1)]
            result = payment_service.update_premium_price(plan_type_text, amount_text)
            await update.effective_message.reply_text(
                (
                    f"✅ Premium price updated for {result['display_plan_type']}.\n"
                    f"New amount: ₹{result['amount_rupees']:.2f}"
                )
            )
            await update.effective_message.reply_text(
                _build_premium_prices_text(),
                parse_mode=ParseMode.HTML,
                reply_markup=_admin_keyboard_for(update.effective_user.id),
            )
            return

    except ValueError as exc:
        await update.effective_message.reply_text(f"❌ {exc}")
    except sqlite3.OperationalError as exc:
        logger.exception(
            "Admin DB operational failure | mode=%s user_id=%s db_path=%s",
            mode,
            update.effective_user.id,
            DATABASE_PATH,
        )
        await _send_admin_save_debug(
            update.effective_message,
            state=mode,
            input=text,
            save_function_called=False,
            db_path=DATABASE_PATH,
            db_row_created=None,
            saved_item=None,
            error=f"{type(exc).__name__}: {exc}",
        )
        error_messages = {
            "add_exam": "Exam save failed",
            "add_set_name": "Set save failed",
        }
        await update.effective_message.reply_text(
            "DB table missing" if "no such table" in str(exc).lower() else error_messages.get(mode, "DB table missing")
        )
    except sqlite3.IntegrityError:
        logger.exception("Admin DB integrity failure | mode=%s user_id=%s", mode, update.effective_user.id)
        await _send_admin_save_debug(
            update.effective_message,
            state=mode,
            input=text,
            save_function_called=False,
            db_path=DATABASE_PATH,
            db_row_created=None,
            saved_item=None,
            error="IntegrityError",
        )
        error_messages = {
            "add_exam": "Exam save failed",
            "add_set_name": "Set save failed",
        }
        await update.effective_message.reply_text(error_messages.get(mode, "DB table missing"))
    except Exception as exc:
        logger.exception("Admin action failed | mode=%s user_id=%s", mode, update.effective_user.id)
        await _send_admin_save_debug(
            update.effective_message,
            state=mode,
            input=text,
            save_function_called=False,
            db_path=DATABASE_PATH,
            db_row_created=None,
            saved_item=None,
            error=f"{type(exc).__name__}: {exc}",
        )
        error_messages = {
            "add_exam": "Exam save failed",
            "add_set_name": "Set save failed",
        }
        await update.effective_message.reply_text(error_messages.get(mode, f"❌ Admin action failed: {exc}"))
    finally:
        if mode not in {"delete_question_search", "notification_message"}:
            context.user_data["admin_mode"] = None


async def _handle_notification_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    wizard: dict,
):
    message = update.effective_message
    text = (message.text or "").strip()
    if not text:
        await message.reply_text("❌ Notification message cannot be empty.")
        return

    notification_service.create_schedule(
        wizard["kind"],
        text,
        wizard["send_time"],
        days_of_week=wizard.get("selected_days", []),
    )

    schedule_bits = [wizard["kind"].title(), wizard["send_time"]]
    if wizard["kind"] == "weekly":
        day_names = ", ".join(DAY_LABELS[day] for day in wizard.get("selected_days", []))
        schedule_bits.append(day_names)

    _reset_notification_state(context)
    context.user_data["admin_mode"] = None

    await message.reply_text(
        (
            "✅ Notification saved successfully.\n\n"
            f"Schedule: {' | '.join(schedule_bits)}\n"
            "This message will be sent directly to each user's chat."
        )
    )
    await _show_notification_menu(message)


async def admin_photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not _is_admin(update.effective_user.id):
        return

    wizard = context.user_data.get("question_wizard")
    if not wizard or wizard.get("step") != "image":
        return

    photo = update.effective_message.photo[-1]
    file = await photo.get_file()

    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    relative_path = Path("data") / "images" / f"{photo.file_unique_id}.jpg"
    absolute_path = BASE_DIR / relative_path
    await file.download_to_drive(str(absolute_path))

    wizard["image_path"] = str(relative_path).replace("\\", "/")
    wizard["step"] = "time"
    await _send_admin_save_debug(
        update.effective_message,
        state="question_wizard:time",
        input=f"photo:{wizard['image_path']}",
        save_function_called=False,
        db_path=DATABASE_PATH,
        db_row_created=None,
        saved_item=wizard,
        error=None,
    )
    await update.effective_message.reply_text(
        "Step 7 of 7: Send optional timer in seconds, or type `skip`."
    )


async def _handle_question_wizard_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    wizard = context.user_data.get("question_wizard", {})
    text = (message.text or "").strip()
    step = wizard.get("step")
    await _send_admin_save_debug(
        message,
        state=f"question_wizard:{step}",
        input=text,
        save_function_called=False,
        db_path=DATABASE_PATH,
        db_row_created=None,
        saved_item=wizard,
        error=None,
    )

    if step == "question":
        if not text:
            await message.reply_text("❌ Question text cannot be empty.")
            return

        wizard["question_text"] = text
        wizard["options"] = []
        wizard["step"] = "option_1"
        await message.reply_text("Step 4 of 7: Send option 1.")
        return

    if step in {"option_1", "option_2", "option_3", "option_4"}:
        option_number = int(step.split("_")[1])
        if not text:
            await message.reply_text(f"❌ You missed option {option_number}")
            return

        wizard.setdefault("options", []).append(text)
        if option_number < 4:
            wizard["step"] = f"option_{option_number + 1}"
            await message.reply_text(f"Step 4 of 7: Send option {option_number + 1}.")
        else:
            wizard["step"] = "correct_answer"
            token = _new_admin_callback_token(context, "qadd_correct")
            await message.reply_text(
                "Step 5 of 7: Select the correct answer.",
                reply_markup=correct_answer_keyboard(wizard["options"], f"admin:qadd_correct:{token}"),
            )
        return

    if step == "image":
        if text.lower() == "skip":
            wizard["image_path"] = None
            wizard["step"] = "time"
            await message.reply_text("Step 7 of 7: Send optional timer in seconds, or type `skip`.")
            return

        candidate = Path(text)
        if not candidate.is_absolute():
            candidate = BASE_DIR / text

        if not candidate.exists():
            await message.reply_text("❌ Image file not found.")
            return

        try:
            wizard["image_path"] = str(candidate.relative_to(BASE_DIR)).replace("\\", "/")
        except ValueError:
            wizard["image_path"] = str(candidate)

        wizard["step"] = "time"
        await message.reply_text("Step 7 of 7: Send optional timer in seconds, or type `skip`.")
        return

    if step == "time":
        if text.lower() == "skip":
            wizard["time_limit"] = DEFAULT_QUESTION_TIME
        else:
            try:
                wizard["time_limit"] = int(text)
            except ValueError:
                await message.reply_text("❌ Invalid format for time.")
                return

            if wizard["time_limit"] <= 0:
                await message.reply_text("❌ Invalid format for time.")
                return

        await _finalize_question_creation(
            message,
            context,
            wizard,
            admin_user_id=update.effective_user.id,
        )


async def _finalize_question_creation(
    message,
    context: ContextTypes.DEFAULT_TYPE,
    wizard: dict,
    *,
    admin_user_id: int,
):
    if not exam_service.exam_storage_ready():
        logger.error(
            "Question save failed | admin_user_id=%s state=question_wizard reason=table_missing db_path=%s",
            admin_user_id,
            DATABASE_PATH,
        )
        await _send_admin_save_debug(
            message,
            state="question_wizard:save",
            input=wizard.get("question_text"),
            save_function_called=False,
            db_path=DATABASE_PATH,
            db_row_created=None,
            saved_item=wizard,
            error="DB table missing",
        )
        await message.reply_text("DB table missing")
        return

    required_fields = ("exam_id", "set_id", "question_text", "correct_option", "time_limit")
    missing_fields = [field for field in required_fields if not wizard.get(field)]
    options = wizard.get("options", [])
    if missing_fields or len(options) != 4:
        logger.warning(
            "Question save failed | admin_user_id=%s state=question_wizard reason=invalid_state missing_fields=%s options=%s db_path=%s wizard=%s",
            admin_user_id,
            missing_fields,
            options,
            DATABASE_PATH,
            wizard,
        )
        _reset_question_wizard(context)
        await _send_admin_save_debug(
            message,
            state="question_wizard:save",
            input=wizard.get("question_text"),
            save_function_called=False,
            db_path=DATABASE_PATH,
            db_row_created=None,
            saved_item=wizard,
            error=f"Invalid state: missing_fields={missing_fields} options_count={len(options)}",
        )
        await message.reply_text("Invalid state")
        return

    logger.info(
        "Question save requested | admin_user_id=%s state=question_wizard input_text=%s db_path=%s wizard=%s",
        admin_user_id,
        wizard.get("question_text"),
        DATABASE_PATH,
        wizard,
    )
    await _send_admin_save_debug(
        message,
        state="question_wizard:save",
        input=wizard.get("question_text"),
        save_function_called="exam_service.add_question",
        db_path=DATABASE_PATH,
        db_row_created=None,
        saved_item=wizard,
        error=None,
    )
    try:
        result = exam_service.add_question(
            exam_id=wizard["exam_id"],
            set_id=wizard["set_id"],
            question_text=wizard["question_text"],
            options=wizard["options"],
            correct_option=wizard["correct_option"],
            image_path=wizard.get("image_path"),
            time_limit=wizard["time_limit"],
        )
    except sqlite3.OperationalError as exc:
        logger.exception(
            "Question save failed | admin_user_id=%s state=question_wizard reason=operational_error db_path=%s error=%s",
            admin_user_id,
            DATABASE_PATH,
            exc,
        )
        await _send_admin_save_debug(
            message,
            state="question_wizard:save",
            input=wizard.get("question_text"),
            save_function_called="exam_service.add_question",
            db_path=DATABASE_PATH,
            db_row_created=None,
            saved_item=wizard,
            error=f"{type(exc).__name__}: {exc}",
        )
        await message.reply_text("DB table missing" if "no such table" in str(exc).lower() else "Question save failed")
        return
    except sqlite3.IntegrityError as exc:
        logger.exception(
            "Question save failed | admin_user_id=%s state=question_wizard reason=integrity_error db_path=%s error=%s",
            admin_user_id,
            DATABASE_PATH,
            exc,
        )
        await _send_admin_save_debug(
            message,
            state="question_wizard:save",
            input=wizard.get("question_text"),
            save_function_called="exam_service.add_question",
            db_path=DATABASE_PATH,
            db_row_created=None,
            saved_item=wizard,
            error=f"{type(exc).__name__}: {exc}",
        )
        await message.reply_text("Question save failed")
        return
    except Exception as exc:
        logger.exception(
            "Question save failed | admin_user_id=%s state=question_wizard reason=exception db_path=%s error=%s",
            admin_user_id,
            DATABASE_PATH,
            exc,
        )
        await _send_admin_save_debug(
            message,
            state="question_wizard:save",
            input=wizard.get("question_text"),
            save_function_called="exam_service.add_question",
            db_path=DATABASE_PATH,
            db_row_created=None,
            saved_item=wizard,
            error=f"{type(exc).__name__}: {exc}",
        )
        await message.reply_text("Question save failed")
        return
    logger.info(
        "Question save success | admin_user_id=%s state=question_wizard db_path=%s row_id=%s record=%s",
        admin_user_id,
        DATABASE_PATH,
        result["row_id"],
        result["record"],
    )
    await _send_admin_save_debug(
        message,
        state="question_wizard:save",
        input=wizard.get("question_text"),
        save_function_called="exam_service.add_question",
        db_path=DATABASE_PATH,
        db_row_created=result["row_id"],
        saved_item=result["record"],
        error=None,
    )

    _reset_question_wizard(context)
    await message.reply_text(
        f"Saved question: <code>{html.escape(str(result['record']))}</code>",
        parse_mode=ParseMode.HTML,
    )
    await message.reply_text(
        "✅ Question added successfully.",
        reply_markup=_admin_keyboard_for(admin_user_id),
    )
